#!/usr/bin/env python3
"""Disposable PostgreSQL contact proof; no live data or external requests."""
import os
import re
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from app.action_models import EmailActionCreate
from app.action_store import (
    ActionPreparationError,
    SideEffectGuardError,
    guard_email_suppression,
)
from app.career_application_quality import assess_application_quality
from app.career_autopilot import target_key
from app.career_contact_models import CareerContactCreate, CareerContactEmailPlan
from app.career_contact_store import CareerContactStore
from app.career_contacts import guard_career_contact_action
from app.career_models import CareerProfileCreate
from app.creator_automation_store import CreatorAutomationStore
from app.email_pacing import EmailPacingPolicy
from app.models import ApprovalDecision, TaskCreate
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def create_fixture(store, *, profile=None, url=None):
    if profile is None:
        profile = store.create_profile(CareerProfileCreate(
            name="Synthetic contact audit", candidate_name="Synthetic Candidate",
            desired_titles=["Software Engineer"], skills=["Python", "PostgreSQL", "Docker"],
            resume_text="Built Python APIs with PostgreSQL and Docker.",
            application_identity={"first_name": "Synthetic", "last_name": "Candidate",
                                  "email": "candidate@example.test"},
            locations=["India"], min_score=75, max_age_hours=72,
            requested_by="contact-audit", active=True,
        ))
    url = url or f"https://jobs.ashbyhq.com/synthetic/{uuid4().hex}"
    with store.connect() as connection:
        opportunity = connection.execute(
            "INSERT INTO job_opportunities(profile_id,source,source_key,company,title,description,"
            "location,source_url,apply_url,published_at,published_at_basis,score) "
            "VALUES (%s,'ashby',%s,'Synthetic Labs','Software Engineer',"
            "'Build Python, PostgreSQL and Docker APIs.','India',%s,%s,"
            "now() - interval '1 hour','published',100) RETURNING *",
            (profile["id"], uuid4().hex, url, url),
        ).fetchone()
        connection.commit()
    task = store.create_task(TaskCreate(
        title="Synthetic contact evidence draft", kind="career.application_draft",
        payload={"profile_id": str(profile["id"]), "opportunity_id": str(opportunity["id"])},
        requested_by="contact-audit",
    ))
    content = {
            "fit_summary": "Relevant Python API projects.",
            "evidence": ["Built Python APIs with PostgreSQL and Docker."],
            "honest_gaps": [], "resume_keywords": ["Python", "PostgreSQL"],
            "cover_letter": "I built Python APIs with PostgreSQL and Docker. I would welcome "
                            "the opportunity to discuss your engineering role and learn about "
                            "the team's current API requirements.",
        }
    content["quality_report"] = assess_application_quality(
        {**opportunity, "resume_text": "Built Python APIs with PostgreSQL and Docker."}, content,
    )
    draft = store.save_application_draft(
        opportunity_id=opportunity["id"], profile_id=profile["id"], task_id=task["id"],
        model="synthetic-no-inference", content=content,
    )
    contact = store.review_contact(opportunity["id"], CareerContactCreate(
        email="hiring@example.test", kind="hiring", source_url="https://example.test/careers",
        evidence_quote="For engineering careers, email hiring@example.test.",
        basis_note="The primary employer page explicitly requests engineering applications.",
        reviewed_by="contact-audit", attested_primary_source=True,
    ))
    return profile, opportunity, draft, contact


def plan(store, contact):
    try:
        return store.prepare_contact_email(
            contact["id"], CareerContactEmailPlan(actor="contact-audit"),
            sender="candidate@example.test",
        )
    except ActionPreparationError:
        return None


def exercise_pacing_scope_expiry(dsn):
    boundary_name = "career-contact-pacing-expiry"
    paced = CareerContactStore(
        make_conninfo(dsn, application_name=boundary_name),
        email_pacing_policy=EmailPacingPolicy(60, 60, 3, 12, 0),
    )
    _, _, _, contact = create_fixture(paced)
    with paced.connect() as connection:
        connection.execute("UPDATE career_contacts SET expires_at=clock_timestamp()+"
                           "interval '3 seconds' WHERE id=%s", (contact["id"],))
    action = plan(paced, contact)
    check(action is not None, "Could not prepare finite-contact pacing fixture")
    paced.decide_task(action["task_id"], ApprovalDecision(
        decision="approved", actor="contact-audit",
    ))
    task = paced.transition_to_running(action["task_id"], 120, "contact-audit")
    fingerprint = hashlib.sha256(f"contact-expiry:{action['id']}".encode()).hexdigest()
    with paced.connect() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
        blocker.execute("SELECT pg_advisory_xact_lock(%s,%s)", (1212502605, 1))
        future = pool.submit(paced.begin_side_effect, task["id"], fingerprint, task["lease_id"])
        try:
            deadline, blocked = time.monotonic() + 2, False
            while not future.done() and time.monotonic() < deadline:
                blocker.execute("SELECT pg_stat_clear_snapshot()")
                blocked = blocker.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                    "WHERE datname=current_database() AND application_name=%s "
                    "AND pid<>pg_backend_pid() AND wait_event_type='Lock' "
                    "AND wait_event='advisory') AS blocked", (boundary_name,),
                ).fetchone()["blocked"]
                if blocked:
                    break
                time.sleep(0.02)
            check(blocked, "Contact boundary did not pass initial guard and wait for global pacing")
            # The contact validity expires while all original bound rows are held.
            time.sleep(3.1)
        finally:
            blocker.commit()
        try:
            future.result(timeout=5)
        except SideEffectGuardError as error:
            check("expired" in str(error), "Wrong post-pacing contact-scope refusal")
        else:
            raise AssertionError("Global pacing wait outlived contact authority but acquired a receipt")
    with paced.connect() as connection:
        check(not connection.execute("SELECT 1 FROM side_effect_receipts WHERE task_id=%s",
                                     (task["id"],)).fetchone(),
              "Expired contact acquired an SMTP receipt after global wait")
        check(connection.execute("SELECT status FROM external_actions WHERE id=%s",
                                 (action["id"],)).fetchone()["status"] == "queued",
              "Contact-scope refusal changed the exact queued action")


def exercise(dsn):
    store = CareerContactStore(dsn)
    groups = []
    profile, opportunity, _draft, contact = create_fixture(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = list(pool.map(lambda _: plan(store, contact), range(2)))
    actions = [action for action in attempts if action]
    check(len(actions) == 1, "Concurrent duplicate requests did not produce exactly one action")
    action = actions[0]
    with store.connect() as connection:
        task = store.get_task(action["task_id"])
        check(task["status"] == "pending_approval" and task["risk_level"] == "high",
              "Contact plan escaped individual exact approval")
        ledger = connection.execute(
            "SELECT * FROM career_contact_actions WHERE action_id=%s", (action["id"],),
        ).fetchone()
        check(ledger["profile_id"] == profile["id"] and ledger["opportunity_id"] == opportunity["id"],
              "Contact ledger lost its derived profile/opportunity linkage")
        guard_career_contact_action(connection, action)
        foreign = connection.execute(
            "INSERT INTO career_profiles(name,candidate_name,requested_by) "
            "VALUES ('Synthetic foreign profile','Synthetic Candidate','contact-smoke') RETURNING id",
        ).fetchone()
        try:
            with connection.transaction():
                connection.execute(
                    "INSERT INTO career_contacts(profile_id,opportunity_id,email,kind,source_url,"
                    "evidence_quote,basis_note,reviewed_by,profile_hash,opportunity_hash,"
                    "reviewed_at,expires_at) SELECT %s,opportunity_id,email,kind,source_url,"
                    "evidence_quote,basis_note,reviewed_by,profile_hash,opportunity_hash,"
                    "reviewed_at,expires_at FROM career_contacts WHERE id=%s",
                    (foreign["id"], contact["id"]),
                )
        except psycopg.errors.ForeignKeyViolation:
            pass
        else:
            raise AssertionError("Database accepted a contact linked to another profile's job")
    groups.append("Real schema rejects cross-profile contacts; exact approval, ledger and final guard")
    groups.append("Concurrent contact planning creates exactly one action")

    # Imported duplicates with different opportunity IDs share one canonical target.
    p2, o2, _, c2 = create_fixture(store)
    _, _, _, c3 = create_fixture(store, profile=p2, url=o2["apply_url"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = list(pool.map(lambda contact: plan(store, contact), (c2, c3)))
    check(sum(item is not None for item in attempts) == 1,
          "Canonical duplicate opportunity imports created multiple contact actions")
    winner = next(item for item in attempts if item is not None)
    unused_contact = next(item for item in (c2, c3)
                          if str(item["id"]) != winner["private_context"]["career_contact"]["contact_id"])
    extra = store.create_email_action(EmailActionCreate(
        recipient="hiring@example.test", subject="Synthetic duplicate-ledger proof",
        body="Synthetic fixture only; no delivery is authorized.", actor="contact-smoke",
        opportunity_id=unused_contact["opportunity_id"],
    ), sender="candidate@example.test")
    with store.connect() as connection:
        try:
            with connection.transaction():
                connection.execute(
                    "INSERT INTO career_contact_actions(action_id,contact_id,profile_id,"
                    "opportunity_id,recipient,target_key) VALUES (%s,%s,%s,%s,%s,%s)",
                    (extra["id"], unused_contact["id"], p2["id"], unused_contact["opportunity_id"],
                     "hiring@example.test", target_key(o2["apply_url"])),
                )
        except psycopg.errors.UniqueViolation:
            pass
        else:
            raise AssertionError("Database accepted a duplicate canonical job/address ledger")
    groups.append("Canonical duplicate imports serialize; database also rejects duplicate ledger keys")

    store.revoke_contact(contact["id"], "contact-audit")
    with store.connect() as connection:
        try:
            guard_career_contact_action(connection, action)
        except SideEffectGuardError:
            pass
        else:
            raise AssertionError("Revoked contact reached final delivery boundary")
    groups.append("Committed revocation fences an already prepared action")

    exercise_pacing_scope_expiry(dsn)
    groups.append("Contact validity is rechecked after global receipt-pacing waits; no SMTP receipt")

    # Hold a real opt-out transaction open. Any ordinary/career send must wait
    # on the shared recipient lock, then observe committed suppression.
    with store.connect() as optout:
        CreatorAutomationStore._suppress_address(optout, " Hiring@Example.Test ")
        boundary_name = "career-contact-smoke-boundary"
        boundary_store = CareerContactStore(make_conninfo(dsn, application_name=boundary_name))

        def try_boundary():
            with boundary_store.connect() as sender:
                try:
                    guard_email_suppression(sender, {
                        "action_type": "communications.email_send",
                        "private_context": {"recipient": "hiring@example.test"},
                    })
                except SideEffectGuardError:
                    return "suppressed"
                return "allowed"
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(try_boundary)
            try:
                deadline, blocked = time.monotonic() + 5, False
                while not future.done() and time.monotonic() < deadline:
                    optout.execute("SELECT pg_stat_clear_snapshot()")
                    blocked = optout.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE datname = current_database() AND application_name = %s "
                        "AND wait_event_type = 'Lock' AND wait_event = 'advisory') AS blocked",
                        (boundary_name,),
                    ).fetchone()["blocked"]
                    if blocked:
                        break
                    time.sleep(0.02)
                check(blocked, "Final send did not wait for an in-flight Gmail opt-out")
            finally:
                # Release even on assertion failure, before waiting for the executor.
                optout.commit()
            check(future.result(timeout=5) == "suppressed", "Waiting send missed committed opt-out")
    groups.append("Uncommitted Gmail opt-out blocks then rejects a waiting cross-path email boundary")
    return groups


def main():
    migrations = globals().get("MIGRATIONS")
    if migrations is None:
        root = Path(__file__).resolve().parents[1] / "config" / "postgres" / "init"
        migrations = [path.read_text(encoding="utf-8") for path in sorted(root.glob("*.sql"))]
    check(migrations, "No migration sources were provided")
    source = os.environ["DATABASE_URL"]
    name = "career_contact_probe_" + uuid4().hex
    check(re.fullmatch(r"career_contact_probe_[0-9a-f]{32}", name)
          and name != conninfo_to_dict(source).get("dbname"), "Unsafe disposable database name")
    maintenance = make_conninfo(source, dbname="postgres", connect_timeout=10)
    dsn = make_conninfo(source, dbname=name, connect_timeout=10,
                       options="-c statement_timeout=10000 -c lock_timeout=5000")
    created = False
    try:
        with psycopg.connect(maintenance, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
            created = True
        with psycopg.connect(dsn, autocommit=True) as connection:
            for migration in migrations:
                connection.execute(migration)
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("HTTP forbidden")), \
                patch("smtplib.SMTP", side_effect=AssertionError("SMTP forbidden")), \
                patch("smtplib.SMTP_SSL", side_effect=AssertionError("SMTP forbidden")):
            groups = exercise(dsn)
        print(f"Career contact PostgreSQL proof passed: {len(groups)} scenario groups")
        for group in groups:
            print("  PASS " + group)
    finally:
        if created:
            with psycopg.connect(maintenance, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            print("Disposable contact database removed; no external requests or sends")


if __name__ == "__main__":
    main()
