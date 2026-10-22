#!/usr/bin/env python3
"""Disposable PostgreSQL proof for model-copy provenance; all network/model output is synthetic."""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import patch
from uuid import uuid4

import psycopg
from app.action_store import SideEffectGuardError
from app.creator_draft_content import parse_model_copy
from app.creator_draft_models import CreatorDraftCreate, CreatorDraftView
from app.creator_draft_store import (
    CreatorDraftConflictError,
    CreatorDraftStore,
    lock_draft_for_prepare,
)
from app.marketing_models import MarketingCampaignCreate, MarketingEmailPlanCreate, MarketingProspectCreate
from app.models import ApprovalDecision, TaskCancellation, TaskCreate
from app.store import InvalidTaskStateError
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb


def check(value, message):
    if not value:
        raise AssertionError(message)


def blocked(call, error, fragment):
    try:
        call()
    except error as exc:
        check(fragment in str(exc), f"Wrong boundary: {exc}")
    else:
        raise AssertionError(f"Expected refusal: {fragment}")


def fixture(store):
    campaign = store.create_campaign(MarketingCampaignCreate(
        name="Synthetic AI copy", product_name="FixtureCraft",
        product_url="https://example.test/", privacy_url="https://example.test/privacy",
        product_summary="A synthetic Minecraft server discovery website for validation.",
        target_audience="Minecraft players", viewer_offer="Explore servers",
        creator_offer="Explore an optional pilot", paid_offer_enabled=True,
        paid_offer_details="A server tour with individually discussed terms", outreach_mode="paid",
        compensation_model="revenue_share", handoff_discord="karixai", sender_name="Synthetic",
        discovery_queries=["Minecraft"], requested_by="creator-draft-smoke",
    ))
    channel = "UC" + uuid4().hex[:22]
    prospect = store.create_prospect(MarketingProspectCreate(
        campaign_id=campaign["id"], platform="youtube", external_id=channel,
        profile_url=f"https://www.youtube.com/channel/{channel}", display_name="Synthetic Creator",
        audience_size=10000, contact_email=f"{uuid4().hex}@example.test",
        contact_source_url=f"https://www.youtube.com/channel/{channel}",
        contact_basis_note="Synthetic public-contact fixture only", authorize_contact=True,
        requested_by="creator-draft-smoke",
    ))
    with store.connect() as connection:
        connection.execute(
            "UPDATE marketing_prospects SET intelligence=%s,"
            "latest_content_title='Minecraft server exploration',"
            "latest_content_url='https://www.youtube.com/watch?v=abcdefghijk',"
            "latest_content_published_at=now()-interval '1 day' WHERE id=%s",
            (Jsonb({"topics": ["Minecraft", "Servers"]}), prospect["id"]),
        )
    return campaign, prospect


def create(store, prospect):
    return store.create_draft(
        prospect["id"], CreatorDraftCreate(actor="creator-draft-smoke", idempotency_key=uuid4()),
    )


def claim(store, row):
    task = store.transition_to_running(row["task_id"], 300, "creator-draft-smoke")
    check(task is not None, "Could not claim draft task")
    return task


def save(store, row, task):
    owned = store.get_draft_for_execution(row["id"], task["id"], task["lease_id"])
    copy = parse_model_copy(json.dumps({
        "hook": "Your public Minecraft server exploration title caught my attention.",
        "content_idea": "Perhaps a short trial exploring a server from the website could "
                        "be an optional fit for your own exploration format.",
        "rationale": "The observed server topic supports a small exploratory pilot.",
        "evidence_ids": ["sample_video"], "reach_strategy": "small_pilot",
    }), owned["model_context"])
    return store.save_draft(
        draft_id=row["id"], task_id=task["id"], lease_id=task["lease_id"], copy=copy,
        source="ollama", selected_model="synthetic-test-response",
    )


def ready(store, row):
    task = claim(store, row)
    saved = save(store, row, task)
    store.complete_task(task["id"], task["lease_id"], {"fixture": True})
    return saved


def prepare(store, row):
    return store.plan_outreach_email(
        row["prospect_id"], MarketingEmailPlanCreate(
            stage="initial", actor="creator-draft-smoke", ai_draft_id=row["id"],
            ai_draft_digest=row["draft_digest"],
        ), sender="synthetic@example.test",
    )


def exercise(dsn):
    store = CreatorDraftStore(dsn)
    groups = []
    _, prospect = fixture(store)
    request = CreatorDraftCreate(actor="creator-draft-smoke", idempotency_key=uuid4())
    row = store.create_draft(prospect["id"], request)
    check(store.create_draft(prospect["id"], request)["id"] == row["id"], "Retry created duplicate")
    task = store.get_task(row["task_id"])
    check(task["risk_level"] == "medium" and task["status"] == "queued", "Wrong governed task")
    with store.connect() as connection:
        check(connection.execute("SELECT 1 FROM task_outbox WHERE task_id=%s",
                                 (task["id"],)).fetchone(), "Missing durable outbox")
        check(connection.execute("SELECT 1 FROM audit_events WHERE task_id=%s "
                                 "AND action='creator_draft.created'",
                                 (task["id"],)).fetchone(), "Missing creation audit")
    CreatorDraftView.model_validate(row)
    groups.append("Idempotent draft request creates policy task, durable outbox and audit")

    claimed = claim(store, row)
    save(store, row, claimed)
    check(store.get_draft(row["id"])["status"] == "queued", "Exposed copy before task completion")
    store.complete_task(claimed["id"], claimed["lease_id"], {"fixture": True})
    saved = store.get_draft(row["id"])
    check(saved["status"] == "ready" and "input_snapshot" not in saved, "Bad ready draft view")
    check(saved["source"] == "ollama" and saved["selected_model"] == "synthetic-test-response",
          "Lost synthetic source provenance")
    with ThreadPoolExecutor(max_workers=2) as executor:
        actions = list(executor.map(lambda _: prepare(store, saved), range(2)))
    check(actions[0]["id"] == actions[1]["id"], "Concurrent prepare created duplicate action")
    check(actions[0]["status"] == "pending_approval", "AI copy escaped exact review")
    check(actions[0]["public_context"]["body"] == saved["body"], "Prepared body changed")
    groups.append("Finished copy preserves source and digest; concurrent prepare is exact and unapproved")

    _, prospect2 = fixture(store)
    row2 = ready(store, create(store, prospect2))
    blocked(lambda: store.plan_outreach_email(
        prospect2["id"], MarketingEmailPlanCreate(
            stage="initial", actor="fixture", ai_draft_id=row2["id"], ai_draft_digest="f" * 64,
        ), sender="fixture@example.test",
    ), CreatorDraftConflictError, "digest")
    blocked(lambda: store.plan_outreach_email(
        prospect2["id"], MarketingEmailPlanCreate(
            stage="initial", actor="fixture", ai_draft_id=row2["id"],
            ai_draft_digest=row2["draft_digest"],
        ), sender="fixture@example.test", automation_context={"run_id": str(uuid4())},
    ), RuntimeError, "individual exact approval")
    groups.append("Changed review digest and delegated AI authority are refused")

    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET audience_size=audience_size+1 WHERE id=%s",
                           (prospect2["id"],))
    check(store.get_draft(row2["id"])["status"] == "stale", "Research change not visible")
    blocked(lambda: prepare(store, row2), CreatorDraftConflictError, "research changed")
    groups.append("Research changes invalidate copy before exact preparation")

    _, prospect3 = fixture(store)
    row3 = create(store, prospect3)
    task3 = claim(store, row3)
    with store.connect() as connection:
        connection.execute("UPDATE marketing_campaigns SET product_summary=product_summary || ' New.' "
                           "WHERE id=%s", (row3["campaign_id"],))
    blocked(lambda: save(store, row3, task3), CreatorDraftConflictError, "research changed")
    groups.append("Late model results cannot persist against changed campaign context")

    _, prospect4 = fixture(store)
    row4 = create(store, prospect4)
    task4 = claim(store, row4)
    store.cancel_task(task4["id"], TaskCancellation(actor="fixture", reason="Synthetic cancellation"))
    blocked(lambda: save(store, row4, task4), InvalidTaskStateError, "valid execution lease")
    _, prospect5 = fixture(store)
    row5 = create(store, prospect5)
    task5 = claim(store, row5)
    with ThreadPoolExecutor(max_workers=1) as executor:
        with store.connect() as blocker:
            blocker.execute("SELECT id FROM marketing_prospects WHERE id=%s FOR UPDATE",
                            (prospect5["id"],))
            # Expire while the worker waits on the prospect lock, after its first lease check.
            blocker.execute("UPDATE agent_tasks SET lease_expires_at=clock_timestamp()+"
                            "interval '0.4 seconds' WHERE id=%s", (task5["id"],))
            blocker.commit()
            blocker.execute("SELECT id FROM marketing_prospects WHERE id=%s FOR UPDATE",
                            (prospect5["id"],))
            future = executor.submit(save, store, row5, task5)
            time.sleep(0.6)
            blocker.commit()
        blocked(lambda: future.result(timeout=10), InvalidTaskStateError, "valid execution lease")
    groups.append("Cancellation and lease expiry during row waits fence model persistence")

    _, prospect6 = fixture(store)
    row6 = create(store, prospect6)
    forged = store.create_task(TaskCreate(
        title="Forged draft fixture", kind="marketing.creator_draft",
        payload={"draft_id": str(row6["id"])}, requested_by="fixture",
    ))
    forged = store.transition_to_running(forged["id"], 300, "fixture")
    blocked(lambda: store.get_draft_for_execution(row6["id"], forged["id"], forged["lease_id"]),
            CreatorDraftConflictError, "not linked")
    with store.connect() as connection:
        connection.execute("UPDATE creator_email_drafts SET expires_at=now()-interval '1 second' "
                           "WHERE id=%s", (row6["id"],))
    check(store.get_draft(row6["id"])["status"] == "stale", "Expired copy still eligible")
    groups.append("Forged task links and expiry cannot reuse durable draft authority")

    _, prospect7 = fixture(store)
    row7 = ready(store, create(store, prospect7))
    initial_expiry_passed = Event()

    def observe_initial_expiry(*args):
        result = lock_draft_for_prepare(*args)
        initial_expiry_passed.set()
        return result

    with ThreadPoolExecutor(max_workers=1) as executor, \
            patch("app.creator_draft_store.lock_draft_for_prepare",
                  side_effect=observe_initial_expiry):
        with store.connect() as blocker:
            blocker.execute(
                "UPDATE creator_email_drafts SET expires_at=clock_timestamp()+"
                "interval '3 seconds' WHERE id=%s", (row7["id"],),
            )
            blocker.commit()
            blocker.execute("SELECT id FROM marketing_prospects WHERE id=%s FOR UPDATE",
                            (prospect7["id"],))
            future = executor.submit(prepare, store, row7)
            check(initial_expiry_passed.wait(timeout=2),
                  "Preparation did not reach its pre-lock expiry check")
            time.sleep(3.1)
            blocker.commit()
        blocked(lambda: future.result(timeout=10), CreatorDraftConflictError, "draft expired")
    with store.connect() as connection:
        check(not connection.execute(
            "SELECT 1 FROM marketing_outreach_messages WHERE prospect_id=%s",
            (prospect7["id"],),
        ).fetchone(), "Expired draft created an approval packet after its lock wait")
    groups.append("Draft expiry during preparation row waits cannot create a new approval packet")

    action = actions[0]
    store.decide_task(action["task_id"], ApprovalDecision(decision="approved", actor="fixture"))
    send_task = store.transition_to_running(action["task_id"], 300, "fixture")
    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET latest_content_title='Changed research' "
                           "WHERE id=%s", (prospect["id"],))
    blocked(lambda: store.begin_side_effect(send_task["id"], uuid4().hex * 2, send_task["lease_id"]),
            SideEffectGuardError, "research changed")
    with store.connect() as connection:
        check(not connection.execute("SELECT 1 FROM side_effect_receipts WHERE task_id=%s",
                                     (send_task["id"],)).fetchone(), "Stale copy acquired receipt")
    groups.append("Final SMTP boundary refuses approved copy after its research changes")
    return groups


def main():
    migrations = globals().get("MIGRATIONS")
    if migrations is None:
        folder = Path(__file__).resolve().parents[1] / "config" / "postgres" / "init"
        migrations = [path.read_text(encoding="utf-8") for path in sorted(folder.glob("*.sql"))]
    source = os.environ["DATABASE_URL"]
    name = "creator_draft_probe_" + uuid4().hex
    check(re.fullmatch(r"creator_draft_probe_[0-9a-f]{32}", name)
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
        print(f"Creator AI draft PostgreSQL proof passed: {len(groups)} scenario groups")
        for group in groups:
            print(f"  PASS {group}")
    finally:
        if created:
            with psycopg.connect(maintenance, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            print("Disposable draft database removed; no HTTP, SMTP or model request")


if __name__ == "__main__":
    main()
