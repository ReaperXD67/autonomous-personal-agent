#!/usr/bin/env python3
"""Disposable PostgreSQL proof of scoped career autonomy; HTTP/SMTP are forbidden."""

from __future__ import annotations

import hashlib
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from app.action_store import SideEffectGuardError
from app.career_autopilot_models import CareerPlay
from app.career_autopilot_store import CareerAutopilotStore
from app.career_models import CareerProfileCreate
from app.career_tracking import GmailSyncError, correlate_message
from app.career_tracking_models import CareerEventCreate
from app.career_tracking_store import CareerTrackingStore
from app.models import TaskCreate
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


def check(value, message):
    if not value:
        raise AssertionError(message)


def create_run(store, *, count=1, cap=3, email=False, duplicate=False):
    profile = store.create_profile(CareerProfileCreate(
        name="Synthetic autonomy proof", candidate_name="Synthetic Applicant",
        desired_titles=["Python Engineer"], skills=["Python"],
        resume_text="Synthetic Applicant. Python engineering fixture; no personal data.",
        application_identity={"first_name": "Synthetic", "last_name": "Applicant",
                              "email": "applicant@example.test"},
        requested_by="autopilot-smoke", active=False,
    ))
    opportunities = []
    with store.connect() as connection:
        for index in range(count):
            suffix = "shared" if duplicate else str(index)
            url = (f"https://careers.example.test/roles/{suffix}" if email else
                   f"https://boards.greenhouse.io/synthetic/jobs/{suffix}")
            description = "Python engineering role; build reliable Python services."
            if email:
                description += " Apply by sending your CV to hiring@example.test."
            opportunity = connection.execute(
                """INSERT INTO job_opportunities (
                    profile_id, source, source_key, company, title, description,
                    source_url, apply_url, published_at, published_at_basis, score
                ) VALUES (%s, 'greenhouse', %s, 'Example Labs', 'Python Engineer', %s,
                          %s, %s, now() - interval '1 hour', 'published', 95) RETURNING *""",
                (profile["id"], f"fixture-{index}", description, url, url),
            ).fetchone()
            opportunities.append(opportunity)
        connection.commit()
    run = store.play(profile["id"], CareerPlay(
        actor="autopilot-smoke", mode="apply", max_applications_per_day=cap, min_score=20,
        max_age_hours=72, allowed_hosts=[] if email else ["boards.greenhouse.io"],
        include_cold_email=email,
    ))
    with store.connect() as connection:
        search = connection.execute(
            "SELECT id, risk_level, status FROM agent_tasks WHERE idempotency_key = %s",
            (f"autopilot-search:{run['id']}",),
        ).fetchone()
        check(search and search["risk_level"] == "low" and search["status"] == "queued",
              "Play did not create a policy-bound search task")
    store._reconcile_run(run["id"], sender="sender@example.test")
    return profile, run, opportunities


def complete_preparation(store, profile, run):
    with store.connect() as connection:
        tasks = connection.execute(
            "SELECT * FROM agent_tasks WHERE payload->>'autopilot_run_id' = %s "
            "AND kind IN ('career.application_draft', 'career.application_preflight') "
            "AND status = 'queued' ORDER BY kind", (str(run["id"]),),
        ).fetchall()
    check(tasks, "Autopilot did not queue any fixture preparation")
    for queued in tasks:
        task = store.transition_to_running(queued["id"], 300, "autopilot-smoke")
        check(task is not None, "Fixture preparation task was not claimable")
        opportunity_id = task["payload"]["opportunity_id"]
        if task["kind"] == "career.application_draft":
            store.save_application_draft(
                opportunity_id=opportunity_id, profile_id=profile["id"], task_id=task["id"],
                model="synthetic-no-inference", content={
                    "cover_letter": "Synthetic application letter for the Python Engineer role.",
                    "fit_summary": "Fixture only", "evidence": [], "honest_gaps": [],
                    "resume_keywords": [],
                },
            )
        else:
            opportunity = store.get_opportunity(opportunity_id)
            store.save_preflight(opportunity_id=opportunity_id, task_id=task["id"], result={
                "apply_url": opportunity["apply_url"], "final_url": opportunity["apply_url"],
                "form_signature": hashlib.sha256(b"synthetic form").hexdigest(),
                "fields": [{"key": "email:0", "type": "email", "label": "Email",
                            "required": True}],
                "submit_label": "Submit application", "blocked_reason": None,
                "has_captcha": False, "has_login": False,
            })
        store.complete_task(task["id"], task["lease_id"], {"synthetic": True})


def items_for(store, run):
    with store.connect() as connection:
        return connection.execute(
            "SELECT * FROM career_autopilot_items WHERE run_id = %s", (run["id"],),
        ).fetchall()


def actions_for(store, run):
    with store.connect() as connection:
        return connection.execute(
            "SELECT a.* FROM external_actions a JOIN career_autopilot_actions ledger "
            "ON ledger.action_id = a.id WHERE ledger.run_id = %s", (run["id"],),
        ).fetchall()


def authorized_fixture(store, *, email=False):
    profile, run, opportunities = create_run(store, email=email)
    complete_preparation(store, profile, run)
    store._reconcile_run(run["id"], sender="sender@example.test")
    actions = actions_for(store, run)
    check(len(actions) == 1 and actions[0]["status"] == "queued", "Scoped action not authorized")
    action = actions[0]
    with store.connect() as connection:
        approval = connection.execute(
            "SELECT action_context_hash FROM task_approvals WHERE task_id = %s",
            (action["task_id"],),
        ).fetchone()
        outbox = connection.execute(
            "SELECT topic FROM task_outbox WHERE task_id = %s", (action["task_id"],),
        ).fetchone()
    check(approval["action_context_hash"] == action["context_hash"], "Exact approval hash missing")
    check(outbox["topic"] == "action.ready", "Authorized action did not enter transactional outbox")
    task = store.transition_to_running(action["task_id"], 300, "autopilot-smoke")
    fingerprint = hashlib.sha256(f"synthetic:{action['id']}".encode()).hexdigest()
    return profile, run, opportunities[0], action, task, fingerprint


def reject_boundary(store, task, fingerprint):
    try:
        store.begin_side_effect(task["id"], fingerprint, task["lease_id"])
    except SideEffectGuardError:
        pass
    else:
        raise AssertionError("Scoped authorization guard allowed a forbidden side effect")
    with store.connect() as connection:
        count = connection.execute(
            "SELECT count(*) AS n FROM side_effect_receipts WHERE task_id = %s", (task["id"],),
        ).fetchone()["n"]
    check(count == 0, "Refused action left an executable side-effect receipt")


def exercise(dsn):
    store = CareerAutopilotStore(dsn)
    groups = []
    for invalidation in ("pause", "expiry", "profile_change", "inactive"):
        profile, run, _, _, task, fingerprint = authorized_fixture(store)
        if invalidation == "pause":
            store.pause(profile["id"], "autopilot-smoke")
        else:
            with store.connect() as connection:
                if invalidation == "expiry":
                    connection.execute("UPDATE career_autopilot_runs SET expires_at = now() "
                                       "- interval '1 second' WHERE id = %s", (run["id"],))
                elif invalidation == "profile_change":
                    connection.execute("UPDATE career_profiles SET resume_text = 'Changed fixture' "
                                       "WHERE id = %s", (profile["id"],))
                else:
                    connection.execute("UPDATE career_profiles SET active = false WHERE id = %s",
                                       (profile["id"],))
                connection.commit()
        reject_boundary(store, task, fingerprint)
    groups.append("Play task, exact hash/outbox, pause, expiry, profile-change and inactivity guards")

    profile, run, _, _, task, fingerprint = authorized_fixture(store)
    with ThreadPoolExecutor(max_workers=1) as executor:
        with store.connect() as blocker:
            blocker.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                            (f"career-autopilot:{profile['id']}",))
            blocker.execute("UPDATE career_autopilot_runs SET expires_at = clock_timestamp() "
                            "+ interval '1 second' WHERE id = %s", (run["id"],))
            waiting = executor.submit(reject_boundary, store, task, fingerprint)
            time.sleep(1.2)
            blocker.commit()
        waiting.result(timeout=20)
    groups.append("Grant expiry is rechecked after waiting on the profile lock")

    for duplicate in (True, False):
        profile, run, _ = create_run(store, count=2, cap=2, duplicate=duplicate)
        complete_preparation(store, profile, run)
        if not duplicate:
            # Lower only the synthetic durable grant after preparation so two completed
            # items contend for one remaining authorization slot, independently of the prep cap.
            with store.connect() as connection:
                connection.execute("UPDATE career_autopilot_runs SET max_applications_per_day = 1 "
                                   "WHERE id = %s", (run["id"],))
                connection.commit()
        with ThreadPoolExecutor(max_workers=2) as executor:
            attempts = [executor.submit(store._advance_item, run["id"], item,
                                        sender="sender@example.test") for item in items_for(store, run)]
            for attempt in attempts:
                attempt.result(timeout=20)
        check(len(actions_for(store, run)) == 1, "Concurrent duplicate/budget guard was bypassed")
        # A fresh grant must not reset profile-wide rolling usage or target deduplication.
        next_run = store.play(profile["id"], CareerPlay(
            actor="autopilot-smoke", mode="apply", max_applications_per_day=1, min_score=20,
            allowed_hosts=["boards.greenhouse.io"],
        ))
        store._reconcile_run(next_run["id"], sender="sender@example.test")
        check(not actions_for(store, next_run), "New Play grant reset the rolling application cap")
    groups.append("Concurrent target deduplication and one-slot budget; rolling limit across grants")

    profile, run, opportunity, action, task, fingerprint = authorized_fixture(store, email=True)
    reference = f"HERMES-{opportunity['id'].hex}"
    check(reference in action["public_context"]["subject"]
          and reference in action["public_context"]["body"], "Career email lacks matchable reference")
    store.begin_side_effect(task["id"], fingerprint, task["lease_id"])
    # Synthetic receipt completion only: HTTP and SMTP constructors are trapped below.
    store.complete_side_effect(task["id"], fingerprint, "synthetic-smtp-acceptance")
    tracking = CareerTrackingStore(dsn)
    tracked = tracking.tracking(profile_id=profile["id"])
    check(tracked["applications"][0]["opportunity_id"] == opportunity["id"],
          "Accepted career email was omitted from application tracking")
    check(tracked["applications"][0]["status"] == "submitted",
          "Synthetic email acceptance did not record submitted state")
    opportunity = store.get_opportunity(opportunity["id"])
    matched, _ = correlate_message({
        "subject": "Re: " + action["public_context"]["subject"], "snippet": "Please share availability",
        "sender": "hiring@example.test", "gmail_thread_id": "reference-fixture",
        "received_at": datetime.now(UTC),
    }, [opportunity], [])
    check(matched == opportunity["id"], "Terse reply cannot correlate by the outgoing reference")
    groups.append("Synthetic career-email acceptance becomes a trackable application")

    _, _, _, action, task, fingerprint = authorized_fixture(store, email=True)
    with store.connect() as connection:
        connection.execute("UPDATE job_application_drafts SET content = '{\"cover_letter\": "
                           "\"Changed fixture\"}'::jsonb WHERE id = %s",
                           (action["private_context"]["career_draft_id"],))
        connection.commit()
    reject_boundary(store, task, fingerprint)
    for email in (False, True):
        profile, run, opportunities = create_run(store, email=email)
        complete_preparation(store, profile, run)
        unrelated = store.create_task(TaskCreate(
            title="Synthetic unrelated draft", kind="career.application_draft",
            payload={"profile_id": str(profile["id"]), "opportunity_id": str(opportunities[0]["id"])},
            requested_by="autopilot-smoke",
        ))
        claimed = store.transition_to_running(unrelated["id"], 300, "autopilot-smoke")
        store.save_application_draft(opportunity_id=opportunities[0]["id"], profile_id=profile["id"],
                                     task_id=claimed["id"], model="synthetic-manual",
                                     content={"cover_letter": "Synthetic draft from outside this run"})
        store.complete_task(claimed["id"], claimed["lease_id"], {"synthetic": True})
        store._reconcile_run(run["id"], sender="sender@example.test")
        check(not actions_for(store, run), "Application borrowed a draft from outside the Play run")
        check(items_for(store, run)[0]["state"] == "needs_review", "Wrong-run draft not flagged")
    exercise_tracking(tracking, profile, opportunities[0])

    _, _, _, action, task, fingerprint = authorized_fixture(store)
    with store.connect() as connection:
        connection.execute("UPDATE job_application_drafts SET content = '{\"cover_letter\": "
                           "\"Changed browser fixture\"}'::jsonb WHERE id = %s",
                           (action["private_context"]["draft_id"],))
        connection.commit()
    try:
        store.get_application_execution_material(action)
    except SideEffectGuardError:
        pass
    else:
        raise AssertionError("Browser executor accepted a changed approved draft")

    profile, run, _ = create_run(store)
    complete_preparation(store, profile, run)
    with store.connect() as connection:
        connection.execute("UPDATE job_application_preflights SET created_at = now() "
                           "- interval '7 hours' WHERE opportunity_id IN "
                           "(SELECT id FROM job_opportunities WHERE profile_id = %s)",
                           (profile["id"],))
        connection.commit()
    store._reconcile_run(run["id"], sender="sender@example.test")
    check(not actions_for(store, run), "Browser application authorized with stale preflight")
    check(items_for(store, run)[0]["state"] == "needs_review", "Stale preflight was not flagged")
    groups.append("Browser/email draft provenance and hash guards; stale browser preflight refusal")
    groups.append("Gmail persistence/replay/cursor fencing, manual correction and cancellation")
    return groups


def exercise_tracking(store, profile, opportunity):
    store.record_application_event(opportunity["id"], CareerEventCreate(
        status="submitted", note="Synthetic submitted fixture", actor="autopilot-smoke"))
    with store.connect() as connection:
        task = connection.execute(
            """INSERT INTO agent_tasks (title,kind,risk_level,status,requested_by,
                   lease_id,lease_expires_at) VALUES ('Synthetic Gmail proof', 'career.gmail_sync',
                   'low','running','autopilot-smoke',gen_random_uuid(),now()+interval '5 minutes')
                   RETURNING *""",
        ).fetchone()
        connection.commit()
    mailbox_key = hashlib.sha256(b"applicant@example.test").hexdigest()
    context = store.gmail_sync_context(profile["id"], mailbox_key, "Hermes/Careers")
    message = {
        "gmail_message_id": "a123", "gmail_thread_id": "b456", "sender": "hr@example.test",
        "subject": "Python Engineer at Example Labs", "snippet": "We received your application",
        "received_at": datetime.now(UTC), "suggested_status": "acknowledgement",
        "confidence": "medium", "evidence": "We received your application",
        "meeting_at": None, "needs_review": False,
    }
    unmatched = dict(message, gmail_message_id="a124", gmail_thread_id="b457",
                     sender="other@unrelated.test")
    result = store.save_gmail_sync(profile["id"], context, [message, unmatched],
        page_token="next", pending_message_ids=["a125"], task_id=task["id"], lease_id=task["lease_id"])
    check(result == {"stored": 2, "matched": 1, "review_candidates": 1},
          "Gmail match/review persistence failed")
    fresh = store.gmail_sync_context(profile["id"], mailbox_key, "Hermes/Careers")
    result = store.save_gmail_sync(profile["id"], fresh, [message, unmatched], page_token=None,
        pending_message_ids=[], task_id=task["id"], lease_id=task["lease_id"])
    check(result["stored"] == 0, "Gmail replay created duplicate messages")
    try:
        store.save_gmail_sync(profile["id"], context, [], page_token=None, pending_message_ids=[],
                             task_id=task["id"], lease_id=task["lease_id"])
    except GmailSyncError:
        pass
    else:
        raise AssertionError("Stale Gmail cursor accepted")
    store.record_application_event(opportunity["id"], CareerEventCreate(
        status="interview", note="Synthetic verified interview time", actor="autopilot-smoke",
        gmail_message_id="a123", meeting_at=datetime.now(UTC) + timedelta(days=7)))
    tracked = store.tracking(profile_id=profile["id"])
    check(tracked["applications"][0]["status_source"] == "manual", "Manual correction lost")
    check(len(tracked["applications"][0]["events"]) == 3, "Original Gmail history lost")
    fresh = store.gmail_sync_context(profile["id"], mailbox_key, "Hermes/Careers")
    with store.connect() as connection:
        connection.execute("UPDATE agent_tasks SET cancellation_requested_at=now() WHERE id=%s",
                           (task["id"],))
        connection.commit()
    try:
        store.save_gmail_sync(profile["id"], fresh, [], page_token=None, pending_message_ids=[],
                             task_id=task["id"], lease_id=task["lease_id"])
    except GmailSyncError:
        pass
    else:
        raise AssertionError("Cancelled Gmail lease accepted")


def main():
    migrations = globals().get("MIGRATIONS")
    if migrations is None:
        root = Path(__file__).resolve().parents[1] / "config" / "postgres" / "init"
        migrations = [path.read_text(encoding="utf-8") for path in sorted(root.glob("*.sql"))]
    check(migrations, "No migration sources were provided")
    source = os.environ["DATABASE_URL"]
    name = "career_autopilot_probe_" + uuid4().hex
    check(re.fullmatch(r"career_autopilot_probe_[0-9a-f]{32}", name)
          and name != conninfo_to_dict(source).get("dbname"), "Unsafe disposable database name")
    maintenance = make_conninfo(source, dbname="postgres", connect_timeout=10)
    dsn = make_conninfo(source, dbname=name, connect_timeout=10)
    created = False
    try:
        with psycopg.connect(maintenance, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                sql.Identifier(name)))
            created = True
        with psycopg.connect(dsn, autocommit=True) as connection:
            for migration in migrations:
                connection.execute(migration)
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("HTTP forbidden")), \
                patch("smtplib.SMTP", side_effect=AssertionError("SMTP forbidden")), \
                patch("smtplib.SMTP_SSL", side_effect=AssertionError("SMTP forbidden")):
            groups = exercise(dsn)
            with psycopg.connect(dsn, autocommit=True) as connection:
                opportunity_id = connection.execute(
                    """INSERT INTO job_opportunities (profile_id, source, source_key, company, title,
                       source_url, apply_url, published_at, published_at_basis, score)
                       SELECT id, 'remotive', 'replay-proof', 'Synthetic Remotive employer',
                       'Python Engineer', 'https://remotive.com/remote-jobs/fixture',
                       'https://remotive.com/remote-jobs/fixture', now(), 'published', 50
                       FROM career_profiles LIMIT 1 RETURNING id""",
                ).fetchone()[0]
                for migration in migrations:
                    connection.execute(migration)
                row = connection.execute("SELECT source FROM job_opportunities WHERE id = %s",
                                         (opportunity_id,)).fetchone()
                check(row == ("remotive",), "Migration replay lost or invalidated Remotive data")
            groups.append("All migrations replay with durable Remotive and application/tracking data")
        print(f"Career autonomy/tracking PostgreSQL proof passed: {len(groups)} scenario groups")
        for group in groups:
            print(f"  PASS {group}")
    finally:
        if created:
            with psycopg.connect(maintenance, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            print("Disposable autonomy database removed; no HTTP, SMTP, model or browser request")


if __name__ == "__main__":
    main()
