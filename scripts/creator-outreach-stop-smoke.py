#!/usr/bin/env python3
"""Disposable PostgreSQL stop/restart proof; no SMTP, model or provider requests."""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from app.action_models import EmailActionCreate
from app.action_store import SideEffectGuardError
from app.creator_automation_models import CreatorAutomationStart
from app.creator_automation_store import CreatorAutomationStore
from app.email_pacing import EmailPacingPolicy
from app.marketing_models import (
    MarketingCampaignCreate,
    MarketingEmailPlanCreate,
    MarketingProspectCreate,
)
from app.marketing_store import MarketingOutreachError
from app.models import ApprovalDecision
from app.store import InvalidTaskStateError
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


def check(value, message):
    if not value:
        raise AssertionError(message)


def fixture(store, count=3):
    campaign = store.create_campaign(MarketingCampaignCreate(
        name="Synthetic owner-stop campaign", product_name="FixtureCraft",
        product_url="https://example.test/", privacy_url="https://example.test/privacy",
        product_summary="Synthetic Minecraft promotion fixture, never a public campaign.",
        target_audience="Minecraft players", viewer_offer="Try the synthetic fixture",
        creator_offer="Discuss an independent trial", paid_offer_enabled=True,
        paid_offer_details="Revenue share and earning weeks agreed individually",
        outreach_mode="paid", handoff_discord="karixai", sender_name="Synthetic operator",
        discovery_queries=["Minecraft"], requested_by="creator-stop-smoke", active=True,
    ))
    prospects = []
    for _ in range(count):
        channel = "UC" + uuid4().hex[:22]
        prospects.append(store.create_prospect(MarketingProspectCreate(
            campaign_id=campaign["id"], platform="youtube", external_id=channel,
            profile_url=f"https://www.youtube.com/channel/{channel}",
            display_name="Synthetic Creator", contact_email=f"{uuid4().hex}@example.test",
            contact_source_url=f"https://www.youtube.com/channel/{channel}",
            contact_basis_note="Synthetic fixture public business invitation",
            authorize_contact=True, requested_by="creator-stop-smoke",
        )))
    return campaign, prospects


def prepare(store, prospect):
    return store.plan_outreach_email(prospect["id"], MarketingEmailPlanCreate(
        actor="creator-stop-smoke", stage="initial", approval_window_minutes=60,
    ), sender="operator@example.test")


def approve(store, action):
    return store.decide_task(action["task_id"], ApprovalDecision(
        decision="approved", actor="creator-stop-smoke",
    ))


def claim_due(store, action):
    with store.connect() as connection:
        connection.execute("UPDATE agent_tasks SET next_attempt_at=now()-interval '1 hour' "
                           "WHERE id=%s", (action["task_id"],))
        connection.execute("UPDATE outbound_email_schedule SET scheduled_for=now()-interval "
                           "'1 hour' WHERE action_id=%s", (action["id"],))
        connection.commit()
    return store.transition_to_running(action["task_id"], 300, "creator-stop-smoke")


def blocked(call, exception, fragment):
    try:
        call()
    except exception as exc:
        check(fragment in str(exc), f"Unexpected stop error: {exc}")
    else:
        raise AssertionError("Stopped authority crossed a creator boundary")


def exercise(dsn, migrations):
    groups = []
    store = CreatorAutomationStore(dsn, email_pacing_policy=EmailPacingPolicy(
        min_interval_seconds=60, domain_min_interval_seconds=60,
        hourly_limit=10, daily_limit=50, jitter_seconds=0,
    ))
    campaign, prospects = fixture(store)
    run = store.start(campaign["id"], CreatorAutomationStart(actor="creator-stop-smoke"))
    actions = [prepare(store, prospect) for prospect in prospects]
    approve(store, actions[1])
    approve(store, actions[2])
    running = claim_due(store, actions[2])
    other_campaign, other_prospects = fixture(store, count=1)
    other_action = prepare(store, other_prospects[0])
    unrelated = store.create_email_action(EmailActionCreate(
        recipient="hiring@example.test", subject="Synthetic unrelated email",
        body="An unrelated exact email fixture.", actor="creator-stop-smoke",
    ), sender="operator@example.test")
    result = store.stop_outreach(campaign["id"], "creator-stop-smoke", "Explicit owner stop")
    check(result["cancelled_tasks"] == 2 and result["cancellation_requested_tasks"] == 1,
          "Stop did not cover pending, queued and claimed exact emails")
    with store.connect() as connection:
        records = connection.execute(
            "SELECT a.status AS action_status,t.* FROM external_actions a "
            "JOIN agent_tasks t ON t.id=a.task_id WHERE a.id=ANY(%s)",
            ([item["id"] for item in actions],),
        ).fetchall()
        check(sum(row["status"] == "cancelled" for row in records) == 2,
              "Queued/pending tasks did not durably cancel")
        check(connection.execute("SELECT state FROM creator_automation_runs WHERE id=%s",
                                 (run["id"],)).fetchone()["state"] == "paused",
              "Delegated run survived owner stop")
        outbox_count = connection.execute(
            "SELECT count(*) AS n FROM task_outbox WHERE task_id=ANY(%s)",
            ([actions[0]["task_id"], actions[1]["task_id"]],),
        ).fetchone()["n"]
        check(outbox_count == 0,
              "Cancelled email remained in the durable outbox")
        authorized_count = connection.execute(
            "SELECT count(*) AS n FROM marketing_prospects "
            "WHERE campaign_id=%s AND contact_authorized_at IS NOT NULL "
            "AND suppressed_at IS NULL", (campaign["id"],),
        ).fetchone()["n"]
        check(authorized_count == 3,
              "Owner stop mutated contact authorization/suppression evidence")
    check(store.get_task(other_action["task_id"])["status"] == "pending_approval"
          and store.get_task(unrelated["task_id"])["status"] == "pending_approval",
          "Creator stop touched an unrelated campaign/email")
    check(not store.get_campaign(campaign["id"])["active"], "Native discovery stayed active")
    blocked(lambda: store.begin_side_effect(running["id"], uuid4().hex * 2, running["lease_id"]),
            SideEffectGuardError, "cancellation was requested")
    blocked(lambda: store.start(campaign["id"], CreatorAutomationStart(actor="operator")),
            MarketingOutreachError, "stopped by the owner")
    groups.append("Durable stop cancels scoped emails, fences claims and pauses runs/discovery")

    # Simulate interruption after the stop commit but before any task cleanup.
    campaign2, prospects2 = fixture(store)
    pending = prepare(store, prospects2[0])
    queued = prepare(store, prospects2[1])
    approve(store, queued)
    claimed = claim_due(store, queued)
    with patch.object(store, "cancel_task", side_effect=RuntimeError("Synthetic interruption")):
        blocked(lambda: store.stop_outreach(campaign2["id"], "operator", "Owner stop"),
                RuntimeError, "Synthetic interruption")
    restarted = CreatorAutomationStore(dsn, email_pacing_policy=store._email_pacing_policy)
    blocked(lambda: approve(restarted, pending), InvalidTaskStateError, "stopped by the owner")
    blocked(lambda: restarted.begin_side_effect(
        claimed["id"], uuid4().hex * 2, claimed["lease_id"]),
            SideEffectGuardError, "stopped by the owner")
    with store.connect() as connection:
        check(connection.execute("SELECT count(*) AS n FROM side_effect_receipts "
                                 "WHERE action_id=ANY(%s)",
                                 ([pending["id"], queued["id"]],)).fetchone()["n"] == 0,
              "Stopped action acquired a receipt after simulated restart")
    groups.append("Committed stop survives interrupted cleanup and a fresh store/process")

    restarted.resume_outreach(campaign2["id"], "operator")
    blocked(lambda: approve(restarted, pending), InvalidTaskStateError,
            "old approval cannot resume")
    blocked(lambda: restarted.begin_side_effect(
        claimed["id"], uuid4().hex * 2, claimed["lease_id"]),
            SideEffectGuardError, "old approval cannot resume")
    fresh = prepare(restarted, prospects2[2])
    approve(restarted, fresh)
    check(fresh["private_context"]["marketing"]["outreach_epoch"] == 1,
          "Fresh reviewed email did not bind the current stop epoch")
    check(not restarted.get_campaign(campaign2["id"])["active"],
          "Resume re-enabled discovery without authorization")
    groups.append("Explicit resumption leaves old approvals revoked; new exact review is required")

    # An old stop's cleanup must never cancel packets explicitly authorized after
    # a concurrent resume. Its cleanup selection is bound to the committed epoch.
    campaign_resume, resume_prospects = fixture(store, count=2)
    old_pending = prepare(store, resume_prospects[0])
    original_cancel = store.cancel_task
    new_after_resume = []

    def resume_during_cleanup(task_id, request):
        if not new_after_resume:
            store.resume_outreach(campaign_resume["id"], "new-explicit-owner-start")
            fresh_packet = prepare(store, resume_prospects[1])
            approve(store, fresh_packet)
            new_after_resume.append(fresh_packet)
        return original_cancel(task_id, request)

    with patch.object(store, "cancel_task", side_effect=resume_during_cleanup):
        store.stop_outreach(campaign_resume["id"], "operator", "Owner stop")
    check(store.get_task(old_pending["task_id"])["status"] == "cancelled",
          "Old pending email escaped cleanup")
    check(store.get_task(new_after_resume[0]["task_id"])["status"] == "queued",
          "An old stop cancelled a fresh packet authorized after explicit resumption")
    groups.append("Stop cleanup is epoch-bound across concurrent explicit resumption")

    # Receipt already acquired before stop is preserved and reported honestly.
    campaign3, prospects3 = fixture(store, count=1)
    in_flight = prepare(store, prospects3[0])
    approve(store, in_flight)
    claimed = claim_due(store, in_flight)
    store.begin_side_effect(claimed["id"], uuid4().hex * 2, claimed["lease_id"])
    result = store.stop_outreach(campaign3["id"], "operator", "Owner stop")
    check(result["in_flight_actions"] == 1, "Stop disguised a pre-existing executing receipt")
    groups.append("A pre-existing SMTP boundary remains preserved and is reported as in-flight")

    # Approval owns task/action -> campaign -> global pacing. Stop waits for
    # campaign, commits its fence, then cancels; it never reverses that order.
    campaign4, prospects4 = fixture(store, count=1)
    waiting = prepare(store, prospects4[0])
    with store.connect() as blocker, ThreadPoolExecutor(max_workers=2) as pool:
        blocker.execute("SELECT pg_advisory_xact_lock(%s,%s)", (1212502605, 1))
        approval = pool.submit(approve, store, waiting)
        deadline, saw_wait = time.monotonic() + 5, False
        while time.monotonic() < deadline and not approval.done():
            blocker.execute("SELECT pg_stat_clear_snapshot()")
            saw_wait = blocker.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=current_database() "
                "AND pid<>pg_backend_pid() AND wait_event_type='Lock' "
                "AND query LIKE '%pg_advisory_xact_lock%') AS waiting",
            ).fetchone()["waiting"]
            if saw_wait:
                break
            time.sleep(0.02)
        check(saw_wait, "Approval did not reach its post-campaign pacing wait")
        stopped = pool.submit(store.stop_outreach, campaign4["id"], "operator", "Owner stop")
        blocker.commit()
        approval.result(timeout=10)
        stopped.result(timeout=10)
    check(store.get_task(waiting["task_id"])["status"] == "cancelled",
          "Concurrent approval escaped the committed owner stop")
    groups.append("Approval/pacing and stop locks serialize without deadlock or replay")

    with psycopg.connect(dsn, autocommit=True) as connection:
        for migration in migrations:
            connection.execute(migration)
    persisted = store.get_campaign(campaign4["id"])
    check(persisted["outreach_paused"] and persisted["outreach_epoch"] == 1,
          "Migration replay cleared durable stop authority")
    check(store.get_task(waiting["task_id"])["status"] == "cancelled",
          "Migration replay revived a cancelled exact packet")
    groups.append("Migration replay preserves stop, epoch and cancelled-task history")
    return groups


def main():
    migrations = globals().get("MIGRATIONS")
    if migrations is None:
        folder = Path(__file__).resolve().parents[1] / "config" / "postgres" / "init"
        migrations = [path.read_text(encoding="utf-8") for path in sorted(folder.glob("*.sql"))]
    source = os.environ["DATABASE_URL"]
    name = "creator_stop_probe_" + uuid4().hex
    check(re.fullmatch(r"creator_stop_probe_[0-9a-f]{32}", name)
          and name != conninfo_to_dict(source).get("dbname"), "Unsafe disposable database")
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
        with patch("urllib.request.OpenerDirector.open",
                   side_effect=AssertionError("HTTP forbidden")), \
                patch("smtplib.SMTP", side_effect=AssertionError("SMTP forbidden")), \
                patch("smtplib.SMTP_SSL", side_effect=AssertionError("SMTP forbidden")):
            groups = exercise(dsn, migrations)
        print(json.dumps({"creator_outreach_stop": "passed", "groups": groups}, indent=2))
    finally:
        if created:
            with psycopg.connect(maintenance, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            print("Disposable stop database removed; no HTTP, SMTP, model or browser request")


if __name__ == "__main__":
    main()
