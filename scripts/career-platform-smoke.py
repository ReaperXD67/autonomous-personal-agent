#!/usr/bin/env python3
"""Disposable PostgreSQL platform/qualification proof; HTTP and SMTP are forbidden."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from app.action_models import ApplicationPlanCreate
from app.action_store import ActionPreparationError, SideEffectGuardError
from app.career import parse_application_draft
from app.career_application_quality import assess_application_quality
from app.career_autopilot import profile_hash
from app.career_autopilot_models import CareerPlay
from app.career_autopilot_store import CareerAutopilotStore
from app.career_draft_grounding import build_grounding_inventory
from app.career_eligibility import ELIGIBILITY_POLICY_VERSION
from app.career_models import CareerProfileCreate, CareerProfileUpdate
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ACTOR = "career-platform-smoke"
RESUME = "PRIVATE_PLATFORM_RESUME_SENTINEL. Built Python APIs with PostgreSQL and Docker."
BASE_DESCRIPTION = "Build Python APIs with PostgreSQL and Docker."
INDIA_REQUIREMENT = " Must be authorized to work in India without visa sponsorship."
TENURE_REQUIREMENT = " Must have 3 years of professional software engineering experience."


def check(value, message):
    if not value:
        raise AssertionError(message)


def new_profile(store, *, facts=None, auto_prepare=False):
    request = CareerProfileCreate(
        name="Synthetic platform proof", candidate_name="Synthetic Applicant",
        desired_titles=["Python Engineer"], skills=["Python", "PostgreSQL", "Docker"],
        locations=["India"], max_age_hours=72, min_score=75,
        resume_text=RESUME, auto_prepare=auto_prepare,
        application_identity={"first_name": "Synthetic", "last_name": "Applicant",
                              "email": "synthetic@example.test"},
        source_config={
            "arbeitnow": False, "yc_companies": ["https://ycombinator.com/companies/synthetic/jobs"],
            "discovery_leads": [{
                "platform": "linkedin",
                "source_url": "https://in.linkedin.com/jobs/view/synthetic-engineer-1234567890",
                "employer_url": "https://jobs.lever.co/synthetic/12345678-1234-1234-1234-123456789abc",
            }],
        },
        eligibility_facts={} if facts is None else {
            "india_authorized_without_sponsorship": facts,
        }, requested_by=ACTOR,
    )
    return store.create_profile(request), request


def update_profile(store, profile, request, *, facts="omitted"):
    values = request.model_dump(exclude={
        "requested_by", "resume_text", "application_identity", "eligibility_facts",
    })
    if facts != "omitted":
        values["eligibility_facts"] = {"india_authorized_without_sponsorship": facts}
    return store.update_profile(profile["id"], CareerProfileUpdate(**values, actor=ACTOR))


def new_opportunity(store, profile, *, description=BASE_DESCRIPTION, source="greenhouse"):
    key = uuid4().hex
    url = (f"https://www.ycombinator.com/companies/synthetic/jobs/{key}" if source == "yc"
           else f"https://boards.greenhouse.io/synthetic/jobs/{int(key[:12], 16)}")
    item = {
        "source": source, "source_key": key, "company": "Synthetic Labs",
        "title": "Python Engineer", "location": "India", "description": description,
        "remote": False, "employment_type": "FullTime", "source_url": url, "apply_url": url,
        "published_at": datetime.now(UTC) - timedelta(hours=1),
        "published_at_basis": "published", "score": 100, "score_reasons": ["Synthetic fixture"],
    }
    saved = store.save_opportunities(profile["id"], [item])
    check(saved["new"] == 1, "Synthetic opportunity was not inserted through the durable store")
    with store.connect() as connection:
        opportunity = connection.execute(
            "SELECT * FROM job_opportunities WHERE profile_id=%s AND source=%s AND source_key=%s",
            (profile["id"], source, key),
        ).fetchone()
    return opportunity, item, saved


def play(store, profile):
    return store.play(profile["id"], CareerPlay(
        actor=ACTOR, mode="apply", max_applications_per_day=10, min_score=75,
        max_age_hours=72, allowed_hosts=["boards.greenhouse.io"],
    ))


def run_items(store, run):
    with store.connect() as connection:
        return connection.execute(
            "SELECT * FROM career_autopilot_items WHERE run_id=%s", (run["id"],),
        ).fetchall()


def complete_preparation(store, profile, run):
    with store.connect() as connection:
        tasks = connection.execute(
            "SELECT * FROM agent_tasks WHERE payload->>'autopilot_run_id'=%s "
            "AND kind IN ('career.application_draft','career.application_preflight') "
            "AND status='queued' ORDER BY kind", (str(run["id"]),),
        ).fetchall()
    check(len(tasks) == 2, "Eligible synthetic item did not create both policy-routed preparation tasks")
    for queued in tasks:
        task = store.transition_to_running(queued["id"], 300, ACTOR)
        check(task is not None, "Synthetic preparation task could not be claimed")
        opportunity_id = task["payload"]["opportunity_id"]
        if task["kind"] == "career.application_draft":
            context = store.get_draft_context(opportunity_id, profile["id"])
            inventory = build_grounding_inventory(context)
            content = parse_application_draft({
                "cover_letter": "I am applying for the Python Engineer role. I built Python APIs "
                                "with PostgreSQL and Docker. I would welcome a discussion about "
                                "the team's current services and this opportunity.",
                "fit_summary": "Synthetic Python project evidence.",
                "evidence_ids": [inventory["evidence"][0]["id"]], "honest_gaps": [],
                "resume_keyword_ids": [item["id"] for item in inventory["keywords"]
                                       if item["text"] == "Python"],
            }, context)
            content["quality_report"] = assess_application_quality(context, content)
            check(content["quality_report"]["disposition"] == "checks_passed",
                  "Synthetic draft failed real current evidence checks")
            store.save_application_draft(
                opportunity_id=opportunity_id, profile_id=profile["id"], task_id=task["id"],
                model="synthetic-no-inference", content=content,
            )
        else:
            opportunity = store.get_opportunity(opportunity_id)
            store.save_preflight(opportunity_id=opportunity_id, task_id=task["id"], result={
                "apply_url": opportunity["apply_url"], "final_url": opportunity["apply_url"],
                "form_signature": hashlib.sha256(b"synthetic platform form").hexdigest(),
                "fields": [{"key": "email:0", "type": "email", "label": "Email", "required": True}],
                "submit_label": "Submit application", "blocked_reason": None,
                "has_captcha": False, "has_login": False,
            })
        store.complete_task(task["id"], task["lease_id"], {"synthetic": True})


def prepared_fixture(store, *, authorize=False):
    profile, request = new_profile(store, facts=True)
    opportunity, _, _ = new_opportunity(store, profile, description=BASE_DESCRIPTION + INDIA_REQUIREMENT)
    run = play(store, profile)
    store._reconcile_run(run["id"], sender="synthetic@example.test")
    check(len(run_items(store, run)) == 1, "Explicit India fact did not pass the narrow legal gate")
    complete_preparation(store, profile, run)
    action = store.create_application_action(opportunity["id"], ApplicationPlanCreate(actor=ACTOR))
    check(action["status"] == "pending_approval", "Exact fixture action escaped approval")
    if authorize:
        store._authorize(run["id"], run_items(store, run)[0], action)
        action = store.get_external_action(action["id"])
        check(action["status"] == "queued", "Eligible fixture did not gain bounded exact approval")
    return profile, request, opportunity, run, action


def reject_final(store, action, reason):
    task = store.transition_to_running(action["task_id"], 300, ACTOR)
    check(task is not None, "Authorized synthetic action was not claimable")
    fingerprint = hashlib.sha256(f"platform-proof:{action['id']}".encode()).hexdigest()
    try:
        store.begin_side_effect(task["id"], fingerprint, task["lease_id"])
    except SideEffectGuardError as error:
        check(reason in str(error), "Final guard refused for an unrelated reason: " + str(error))
    else:
        raise AssertionError("Invalidated synthetic action acquired a side-effect receipt")
    with store.connect() as connection:
        check(not connection.execute("SELECT 1 FROM side_effect_receipts WHERE task_id=%s",
                                     (task["id"],)).fetchone(),
              "Rejected final boundary left an executable side-effect receipt")


def exercise(dsn, migrations):
    store = CareerAutopilotStore(dsn)
    groups = []
    profile, request = new_profile(store, facts=True)
    check("resume_text" not in profile and profile["resume_present"], "Public profile exposed résumé text")
    expected_source = request.source_config.model_dump()
    private = store.get_profile(profile["id"], include_resume=True)
    check(private["source_config"] == expected_source, "Platform provenance was not durably canonicalized")
    check(private["eligibility_facts"] == {"india_authorized_without_sponsorship": True},
          "Explicit screening fact did not survive profile creation")
    before_hash = profile_hash(private)
    update_profile(store, profile, request)
    preserved = store.get_profile(profile["id"], include_resume=True)
    check(preserved["eligibility_facts"] == private["eligibility_facts"]
          and preserved["resume_text"] == RESUME
          and preserved["application_identity"] == private["application_identity"]
          and preserved["source_config"] == expected_source,
          "Older profile update overwrote an omitted fact, identity, résumé or source reference")
    check(profile_hash(preserved) == before_hash, "Omitted fact changed the current profile scope")
    update_profile(store, profile, request, facts=False)
    changed = store.get_profile(profile["id"], include_resume=True)
    check(changed["eligibility_facts"] == {"india_authorized_without_sponsorship": False}
          and profile_hash(changed) != before_hash, "Explicit fact replacement did not invalidate scope")
    update_profile(store, profile, request, facts=True)
    groups.append("Profile facts, résumé/identity omission preservation and canonical platform provenance persist")

    opportunity, item, _ = new_opportunity(
        store, profile, description=BASE_DESCRIPTION + INDIA_REQUIREMENT, source="yc",
    )
    item["description"] += " Current synthetic publication evidence."
    result = store.save_opportunities(profile["id"], [item])
    check(result["updated"] == 1 and result["new"] == 0, "YC upsert duplicated its durable identity")
    detail = store.get_opportunity(opportunity["id"])
    listing = store.list_opportunities(profile_id=profile["id"], opportunity_status=None, limit=10)
    check(len(listing) == 1 and detail["source"] == "yc" and detail["description"] == item["description"],
          "YC opportunity did not survive update and public reads")
    check(detail["eligibility"]["disposition"] == "no_blocking_requirement"
          and detail["eligibility"]["model_calls"] == 0,
          "Stored explicit India fact did not reach current opportunity qualification projection")
    encoded = json.dumps([detail, listing], default=str)
    check("PRIVATE_PLATFORM_RESUME_SENTINEL" not in encoded and "resume_text" not in encoded
          and "eligibility_evidence" not in encoded and "eligibility_facts" not in encoded,
          "Public opportunity projection leaked private résumé or legal facts")
    with store.connect() as connection:
        audit = connection.execute("SELECT input_metadata FROM audit_events").fetchall()
        check("PRIVATE_PLATFORM_RESUME_SENTINEL" not in json.dumps(audit, default=str),
              "Profile audit metadata leaked résumé text")
    groups.append("YC source upserts once; current public qualification projections omit private résumé/facts")

    migration_025 = next(item for item in migrations if "'025_career_smartrecruiters'" in item)
    migration_027 = next(item for item in migrations if "'027_career_platform_discovery'" in item
                         and "ADD COLUMN IF NOT EXISTS" in item)
    with psycopg.connect(dsn, autocommit=True) as connection:
        for migration in (migration_027, migration_025, migration_027):
            connection.execute(migration)
        check(connection.execute("SELECT count(*) FROM schema_migrations "
                                 "WHERE version='027_career_platform_discovery'").fetchone()[0] == 1,
              "Migration replay duplicated its registry row")
        check(connection.execute("SELECT source FROM job_opportunities WHERE id=%s",
                                 (opportunity["id"],)).fetchone()[0] == "yc",
              "Older 025 replay removed or rejected existing YC source data")
        try:
            with connection.transaction():
                connection.execute("UPDATE job_opportunities SET source='linkedin' WHERE id=%s",
                                   (opportunity["id"],))
        except psycopg.errors.CheckViolation:
            pass
        else:
            raise AssertionError("Discovery reference incorrectly became an executable opportunity source")
    groups.append("027 replays around guarded 025 with existing YC data; unknown/native LinkedIn source stays rejected")

    for facts, description in ((None, INDIA_REQUIREMENT), (False, INDIA_REQUIREMENT),
                               (True, " Must be authorized to work in the United States."),
                               (True, TENURE_REQUIREMENT)):
        candidate, _ = new_profile(store, facts=facts, auto_prepare=True)
        role, _, saved = new_opportunity(store, candidate, description=BASE_DESCRIPTION + description)
        check(not saved["auto_prepare_ids"], "Mandatory requirement consumed legacy draft/inference allowance")
        run = play(store, candidate)
        store._reconcile_run(run["id"], sender="synthetic@example.test")
        check(not run_items(store, run), "Mandatory qualification review consumed delegated preparation")
        projected = store.get_opportunity(role["id"])
        check(projected["eligibility"]["disposition"] == "review_required",
              "A blocked current requirement was hidden from public review")
    groups.append("Unknown/false India fact, foreign legal requirement and mandatory tenure stop both selection paths")

    _, _, role, run, action = prepared_fixture(store)
    with store.connect() as connection:
        connection.execute("UPDATE job_opportunities SET description=description || %s WHERE id=%s",
                           (TENURE_REQUIREMENT, role["id"]))
    try:
        store._authorize(run["id"], run_items(store, run)[0], action)
    except ActionPreparationError as error:
        check("Mandatory qualification review" in str(error), "Approval rejected for an unrelated reason")
    else:
        raise AssertionError("Changed mandatory requirement gained delegated approval")
    with store.connect() as connection:
        check(not connection.execute("SELECT 1 FROM career_autopilot_actions WHERE action_id=%s",
                                     (action["id"],)).fetchone(), "Refused action gained a submission ledger")
        check(not connection.execute("SELECT 1 FROM task_approvals WHERE task_id=%s",
                                     (action["task_id"],)).fetchone(), "Refused action gained exact approval")
    groups.append("A newly mandatory qualification is recomputed before exact delegated approval")

    _, _, role, _, action = prepared_fixture(store, authorize=True)
    with store.connect() as connection:
        connection.execute("UPDATE job_opportunities SET description=description || %s WHERE id=%s",
                           (TENURE_REQUIREMENT, role["id"]))
    reject_final(store, action, "Mandatory qualification review")
    groups.append("Changed mandatory qualification blocks an already approved action at the receipt boundary")

    profile, request, _, _, action = prepared_fixture(store, authorize=True)
    # Keep the mission active so only its changed screening fact invalidates the grant.
    request = request.model_copy(update={"active": True})
    update_profile(store, profile, request, facts=False)
    reject_final(store, action, "Profile changed")
    _, _, _, _, action = prepared_fixture(store, authorize=True)
    with patch("app.career_autopilot.ELIGIBILITY_POLICY_VERSION", ELIGIBILITY_POLICY_VERSION + 1):
        reject_final(store, action, "Profile changed")
    groups.append("Fact changes and qualification-policy version changes invalidate durable grants with zero receipts")
    return groups


def main():
    migrations = globals().get("MIGRATIONS")
    if migrations is None:
        root = Path(__file__).resolve().parents[1] / "config" / "postgres" / "init"
        migrations = [path.read_text(encoding="utf-8") for path in sorted(root.glob("*.sql"))]
    check(migrations, "No migration sources were provided")
    source = os.environ["DATABASE_URL"]
    name = "career_platform_probe_" + uuid4().hex
    check(re.fullmatch(r"career_platform_probe_[0-9a-f]{32}", name)
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
            groups = exercise(dsn, migrations)
        print(f"Career platform PostgreSQL proof passed: {len(groups)} scenario groups")
        for group in groups:
            print("  PASS " + group)
    finally:
        if created:
            with psycopg.connect(maintenance, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            print("Disposable platform database removed; no external requests or sends")


if __name__ == "__main__":
    main()
