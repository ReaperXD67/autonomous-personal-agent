#!/usr/bin/env python3
"""Disposable PostgreSQL proof; never contacts a creator, mailbox, model, or SMTP server."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import psycopg
from app.action_store import SideEffectGuardError
from app.creator_automation import creator_mailbox_is_fresh
from app.creator_automation_gmail import execute_creator_gmail_sync
from app.creator_automation_models import CreatorAutomationStart, CreatorReplyReview
from app.creator_automation_store import CreatorAutomationStore
from app.creator_draft_content import parse_model_copy
from app.creator_draft_models import CreatorDraftCreate
from app.creator_draft_store import CreatorDraftStore
from app.creator_reply_content import parse_reply_model_copy, reply_response_schema
from app.creator_reply_draft_models import CreatorReplyDraftCreate
from app.creator_reply_draft_store import (
    CreatorReplyDraftConflictError,
    CreatorReplyDraftStore,
)
from app.email_pacing import EmailPacingPolicy
from app.marketing_models import (
    MarketingCampaignCreate,
    MarketingEmailPlanCreate,
    MarketingOutcomeCreate,
    MarketingProspectCreate,
)
from app.marketing_store import MarketingOutreachError
from app.models import ApprovalDecision, TaskCancellation, TaskCreate
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb


def check(value, message):
    if not value:
        raise AssertionError(message)


def campaign(store, *, count=1, cap=3, handoff=False, authorized=True, shared_email=None):
    row = store.create_campaign(MarketingCampaignCreate(
        name="Synthetic Minecraft outreach", product_name="FixtureCraft",
        product_url="https://example.test/", privacy_url="https://example.test/privacy",
        product_summary="Synthetic Minecraft creator promotion fixture, no public campaign.",
        target_audience="Minecraft players", viewer_offer="Try the synthetic fixture",
        creator_offer="Discuss an optional collaboration", paid_offer_enabled=True,
        paid_offer_details="A revenue-share percentage and earning window agreed individually",
        outreach_mode="paid", handoff_discord="karixai", sender_name="Synthetic Operator",
        discovery_queries=["Minecraft"], min_subscribers=0, max_subscribers=1000000,
        requested_by="creator-automation-smoke", active=False,
    ))
    prospects = []
    for _ in range(count):
        channel = "UC" + uuid4().hex[:22]
        prospect = store.create_prospect(MarketingProspectCreate(
            campaign_id=row["id"], platform="youtube", external_id=channel,
            profile_url=f"https://www.youtube.com/channel/{channel}",
            display_name="Synthetic Minecraft Creator", audience_size=10,
            contact_email=shared_email or f"{uuid4().hex}@example.test",
            contact_source_url=f"https://www.youtube.com/channel/{channel}",
            contact_basis_note="Synthetic operator-reviewed public business contact",
            authorize_contact=authorized, requested_by="creator-automation-smoke",
        ))
        with store.connect() as connection:
            connection.execute(
                "UPDATE marketing_prospects SET intelligence=%s, "
                "latest_content_published_at=now()-interval '1 day' WHERE id=%s",
                (Jsonb({"topics": ["Minecraft"], "geography": {}}), prospect["id"]),
            )
            connection.commit()
        prospects.append(prospect)
    run = store.start(row["id"], CreatorAutomationStart(
        actor="creator-automation-smoke", max_initials_per_day=cap, auto_handoff=handoff,
    ))
    return row, run, prospects


def task_for(store, campaign_id, run_id=None, kind="marketing.creator_automation"):
    payload = {"campaign_id": str(campaign_id)}
    if run_id:
        payload["run_id"] = str(run_id)
    queued = store.create_task(TaskCreate(title="Synthetic creator task", kind=kind, payload=payload,
                                        requested_by="creator-automation-smoke"))
    return store.transition_to_running(queued["id"], 300, "creator-automation-smoke")


def actions(store, campaign_id):
    with store.connect() as connection:
        return connection.execute(
            "SELECT a.*,m.prospect_id,m.stage FROM external_actions a "
            "JOIN marketing_outreach_messages m ON m.action_id=a.id "
            "JOIN marketing_prospects p ON p.id=m.prospect_id WHERE p.campaign_id=%s "
            "ORDER BY a.created_at", (campaign_id,),
        ).fetchall()


def accept_fixture(store, action):
    claimed = store.transition_to_running(action["task_id"], 300, "creator-automation-smoke")
    fingerprint = hashlib.sha256(str(action["id"]).encode()).hexdigest()
    store.begin_side_effect(claimed["id"], fingerprint, claimed["lease_id"])
    store.complete_side_effect(claimed["id"], fingerprint, "synthetic-no-SMTP")
    store.complete_task(claimed["id"], claimed["lease_id"], {"fixture": True})


def capture_fixture_body(store, task, state, reply, text):
    current = store.gmail_context(state["campaign_id"], state["mailbox_key"], state["label_name"])
    claim = store.claim_reply_body(task, current, reply["id"])
    check(claim, "Synthetic full-body capture did not acquire its owned claim")
    store.save_reply_body(task, current, claim, {
        "status": "complete", "text": text, "format": "plain", "error_code": None,
    }, reply)
    return store.get_reply(state["campaign_id"], reply["id"])


def expect_boundary_block(store, action, text):
    claimed = store.transition_to_running(action["task_id"], 300, "creator-automation-smoke")
    check(claimed, "Action could not be claimed for boundary test")
    try:
        store.begin_side_effect(claimed["id"], uuid4().hex * 2, claimed["lease_id"])
    except SideEffectGuardError as exc:
        check(text in str(exc), f"Unexpected boundary error: {exc}")
    else:
        raise AssertionError("Revoked creator grant crossed the side-effect boundary")


def expect_pacing_wait_refusal(store, action, fragment):
    with store.connect() as connection:
        connection.execute("UPDATE outbound_email_schedule SET scheduled_for=clock_timestamp()-"
                           "interval '1 hour' WHERE action_id=%s", (action["id"],))
        connection.execute("UPDATE agent_tasks SET next_attempt_at=clock_timestamp()-"
                           "interval '1 hour' WHERE id=%s", (action["task_id"],))
    claimed = store.transition_to_running(action["task_id"], 300, "creator-pacing-smoke")
    with store.connect() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
        blocker.execute("SELECT pg_advisory_xact_lock(%s,%s)", (1212502605, 1))
        future = pool.submit(store.begin_side_effect, claimed["id"], uuid4().hex * 2,
                             claimed["lease_id"])
        try:
            deadline, blocked = time.monotonic() + 2, False
            while not future.done() and time.monotonic() < deadline:
                blocker.execute("SELECT pg_stat_clear_snapshot()")
                blocked = blocker.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                    "WHERE datname=current_database() AND application_name='creator-pacing-expiry' "
                    "AND pid<>pg_backend_pid() AND wait_event_type='Lock' "
                    "AND wait_event='advisory') AS blocked",
                ).fetchone()["blocked"]
                if blocked:
                    break
                time.sleep(0.02)
            check(blocked, "Creator boundary failed to reach the real global pacing wait")
            time.sleep(3.1)
        finally:
            blocker.commit()
        try:
            future.result(timeout=10)
        except SideEffectGuardError as error:
            check(fragment in str(error), f"Wrong post-pacing time-boundary refusal: {error}")
        else:
            raise AssertionError("Expired creator evidence or authority crossed global pacing")
    with store.connect() as connection:
        check(not connection.execute("SELECT 1 FROM side_effect_receipts WHERE task_id=%s",
                                     (claimed["id"],)).fetchone(),
              "Expired creator scope acquired a side-effect receipt")
        check(connection.execute("SELECT status FROM external_actions WHERE id=%s",
                                 (action["id"],)).fetchone()["status"] == "queued",
              "Post-wait time refusal rewrote the exact queued packet")


def exercise_pacing_time_guards(dsn):
    scoped = make_conninfo(dsn, application_name="creator-pacing-expiry")
    store = CreatorAutomationStore(scoped, email_pacing_policy=EmailPacingPolicy(60, 60, 3, 12, 0))
    for case, fragment in (
        ("run", "authorization expired"),
        ("gmail", "monitoring needs a recent completed sync"),
        ("publication", "recent published content is required"),
    ):
        c, run, prospects = campaign(store)
        if case == "publication":
            with store.connect() as connection:
                connection.execute("UPDATE marketing_prospects SET latest_content_published_at="
                                   "clock_timestamp()-make_interval(days=>%s)+interval '3 seconds' "
                                   "WHERE id=%s", (c["max_video_age_days"], prospects[0]["id"]))
        store.execute(task_for(store, c["id"], run["id"]), sender="sender@example.test")
        action = actions(store, c["id"])[0]
        with store.connect() as connection:
            if case == "run":
                connection.execute("UPDATE creator_automation_runs SET expires_at="
                                   "clock_timestamp()+interval '3 seconds' WHERE id=%s", (run["id"],))
            if case == "gmail":
                connection.execute("UPDATE creator_automation_runs SET monitor_gmail=true WHERE id=%s",
                                   (run["id"],))
                connection.execute("INSERT INTO creator_gmail_sync_state "
                                   "(campaign_id,mailbox_key,label_name,last_complete_at) "
                                   "VALUES (%s,%s,'Hermes/Creators',clock_timestamp()-"
                                   "interval '30 minutes'+interval '3 seconds')",
                                   (c["id"], "f" * 64))
        expect_pacing_wait_refusal(store, action, fragment)

    drafts = CreatorDraftStore(scoped, email_pacing_policy=EmailPacingPolicy(60, 60, 3, 12, 0))
    c, _, prospects = campaign(store)
    prospect = prospects[0]
    with drafts.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET latest_content_title='Minecraft session',"
                           "latest_content_url='https://www.youtube.com/watch?v=abcdefghijk',"
                           "last_seen_at=clock_timestamp()-interval '7 days'+interval '3 seconds' "
                           "WHERE id=%s", (prospect["id"],))
    row = drafts.create_draft(prospect["id"], CreatorDraftCreate(
        actor="creator-pacing-smoke", idempotency_key=uuid4(),
    ))
    task = drafts.transition_to_running(row["task_id"], 300, "creator-pacing-smoke")
    owned = drafts.get_draft_for_execution(row["id"], task["id"], task["lease_id"])
    copy = parse_model_copy(json.dumps({"evidence_id": "sample_video", "angle_id": "first_session"}),
                            owned["model_context"])
    saved = drafts.save_draft(draft_id=row["id"], task_id=task["id"], lease_id=task["lease_id"],
                              copy=copy, source="ollama", selected_model="synthetic-no-inference")
    drafts.complete_task(task["id"], task["lease_id"], {"synthetic": True})
    action = drafts.plan_outreach_email(prospect["id"], MarketingEmailPlanCreate(
        actor="creator-pacing-smoke", stage="initial", ai_draft_id=row["id"],
        ai_draft_digest=saved["draft_digest"],
    ), sender="sender@example.test")
    drafts.decide_task(action["task_id"], ApprovalDecision(decision="approved", actor="fixture"))
    expect_pacing_wait_refusal(drafts, action, "research changed or expired")


def exercise_reply_bodies(store):
    groups = []
    c, run, _ = campaign(store, count=2, cap=2)
    store.execute(task_for(store, c["id"], run["id"]), sender="sender@example.test")
    sent = actions(store, c["id"])
    for action in sent:
        accept_fixture(store, action)
    task = task_for(store, c["id"], kind="marketing.gmail_sync")
    mailbox, label = "operator@example.test", "Hermes/Creators"
    mailbox_key = hashlib.sha256(mailbox.encode()).hexdigest()
    state = store.gmail_context(c["id"], mailbox_key, label)
    received = datetime.fromtimestamp(int(time.time() * 1000) / 1000, UTC)
    messages = [{"gmail_message_id": f"body{i}", "gmail_thread_id": f"bodythread{i}",
                 "sender": action["public_context"]["recipient"],
                 "subject": "Re: " + action["public_context"]["subject"],
                 "snippet": "A metadata preview for review", "received_at": received}
                for i, action in enumerate(sent)]
    store.save_gmail(task, state, messages, cursor=None, pending=[], mark_complete=False)
    before = {row["gmail_message_id"]: row for row in store.overview(c["id"])["pending_replies"]}
    check(store.gmail_context(c["id"], mailbox_key, label)["last_complete_at"] is None,
          "Metadata progress incorrectly marked a full sync complete")
    private_text = "Tak, chętnie porozmawiam.\nOn Tue, someone wrote:\nSynthetic quoted invitation"

    def raw(message, *, different_sender=False):
        return {"id": message["gmail_message_id"], "threadId": message["gmail_thread_id"],
                "labelIds": ["BodyLabel"], "snippet": message["snippet"],
                "internalDate": str(int(message["received_at"].timestamp() * 1000)),
                "payload": {"mimeType": "text/plain", "headers": [
                    {"name": "From", "value": ("other@example.test" if different_sender
                                                else message["sender"])},
                    {"name": "Subject", "value": message["subject"]}],
                    "body": {"size": len(private_text.encode()), "data":
                             base64.urlsafe_b64encode(private_text.encode()).decode().rstrip("=")}}}

    client = Mock()
    client.mailbox.return_value = mailbox
    client.label_id.return_value = "BodyLabel"
    client.list_messages.side_effect = lambda *_: ([m["gmail_message_id"] for m in messages], None)
    client.full_message.side_effect = lambda message_id: raw(next(
        message for message in messages if message["gmail_message_id"] == message_id))
    settings = SimpleNamespace(
        creator_gmail_enabled=True, creator_gmail_mailbox=mailbox,
        gmail_creator_label=label, gmail_career_label="Hermes/Careers",
        gmail_client_id=None, gmail_client_secret=None, gmail_refresh_token=None,
        creator_gmail_full_reply_campaign_ids=[c["id"]],
    )
    with patch("app.creator_automation_gmail.CreatorGmailReadClient", return_value=client):
        result = execute_creator_gmail_sync(task, store, settings)
    check(result["body_complete"] == 2 and result["fetched"] == 0,
          "Known metadata rows were skipped instead of backfilled")
    client.message.assert_not_called()
    summary = store.overview(c["id"])
    check(summary["gmail_sync"]["last_complete_at"] is not None,
          "Successful bounded body phase did not finalize monitoring")
    for row in summary["pending_replies"]:
        prior = before[row["gmail_message_id"]]
        check(all(row[key] == prior[key] for key in (
            "id", "created_at", "snippet", "received_at", "needs_review", "prospect_id",
        )), "Backfill rewrote original reply evidence or review state")
        check("body_text" not in row, "Routine overview leaked full body text")
        detail = store.get_reply(c["id"], row["id"])
        check(detail["body_complete"] and detail["body_text"] == private_text
              and detail["authored_text"] == "Tak, chętnie porozmawiam.",
              "Private complete/case-preserving reply view is incorrect")
        try:
            store.queue_reply_body_read(c["id"], row["id"], "synthetic-reader")
        except MarketingOutreachError:
            pass
        else:
            raise AssertionError("Complete body snapshot was recaptured")
    check(private_text not in json.dumps(result), "Task output leaked body text")
    with store.connect() as connection:
        audit = connection.execute(
            "SELECT input_metadata,result_metadata FROM audit_events WHERE task_id=%s",
            (task["id"],),
        ).fetchall()
    check(private_text not in json.dumps(audit, default=str), "Audit leaked full body text")
    detail = store.get_reply(c["id"], summary["pending_replies"][0]["id"])
    for digest in (None, "0" * 64):
        try:
            store.review_reply(c["id"], detail["id"], CreatorReplyReview(
                actor="synthetic-reader", classification="question", body_digest=digest,
            ))
        except MarketingOutreachError:
            pass
        else:
            raise AssertionError("Semantic reply review accepted a missing or stale body digest")
    reviewed = store.review_reply(c["id"], detail["id"], CreatorReplyReview(
        actor="synthetic-reader", classification="question", body_digest=detail["body_digest"],
    ))
    check(reviewed["reviewed_body_digest"] == detail["body_digest"] and "body_text" not in reviewed,
          "Review did not retain its exact body digest or leaked body text")
    check(len(actions(store, c["id"])) == 2, "Reply capture/review created sending authority")
    groups.append("Existing reply backfill preserves identity, private bodies and exact review digest")

    messages.append({**messages[0], "gmail_message_id": "body-bad"})
    state = store.gmail_context(c["id"], mailbox_key, label)
    store.save_gmail(task, state, [messages[-1]], cursor=None, pending=[], mark_complete=False)
    client.full_message.side_effect = lambda _: raw(messages[-1], different_sender=True)
    for attempt in range(1, 4):
        with patch("app.creator_automation_gmail.CreatorGmailReadClient", return_value=client):
            execute_creator_gmail_sync(task, store, settings)
        bad = next(row for row in store.overview(c["id"])["pending_replies"]
                   if row["gmail_message_id"] == "body-bad")
        check(bad["body_status"] == "unavailable" and bad["body_attempt_count"] == attempt,
              "Changed full-message identity was not refused with a durable attempt")
        check(not store.get_reply(c["id"], bad["id"])["body_text"], "Incomplete text leaked")
        client.full_message.reset_mock()
        with patch("app.creator_automation_gmail.CreatorGmailReadClient", return_value=client):
            execute_creator_gmail_sync(task, store, settings)
        client.full_message.assert_not_called()
        try:
            store.queue_reply_body_read(c["id"], bad["id"], "synthetic-reader")
        except MarketingOutreachError:
            pass
        else:
            raise AssertionError("Retry bypassed its five-minute cooldown")
        with store.connect() as connection:
            connection.execute("UPDATE creator_reply_messages SET body_attempted_at="
                               "clock_timestamp()-interval '6 minutes' WHERE id=%s", (bad["id"],))
            connection.commit()
        if attempt < 3:
            requested = store.queue_reply_body_read(c["id"], bad["id"], "synthetic-reader")
            check(requested["task"]["kind"] == "marketing.gmail_sync",
                  "Explicit retry bypassed the existing capability")
    try:
        store.queue_reply_body_read(c["id"], bad["id"], "synthetic-reader")
    except MarketingOutreachError:
        pass
    else:
        raise AssertionError("Explicit retry reset the three-attempt allowance")
    groups.append("Identity failures stay incomplete; only bounded explicit read retries consume attempts")

    messages.append({**messages[0], "gmail_message_id": "body-crash"})
    state = store.gmail_context(c["id"], mailbox_key, label)
    store.save_gmail(task, state, [messages[-1]], cursor=None, pending=[], mark_complete=False)
    state = store.gmail_context(c["id"], mailbox_key, label)
    crashed_row = next(row for row in store.overview(c["id"])["pending_replies"]
                       if row["gmail_message_id"] == "body-crash")
    abandoned = store.claim_reply_body(task, state, crashed_row["id"])
    with store.connect() as connection:
        connection.execute("UPDATE agent_tasks SET lease_expires_at=clock_timestamp()-"
                           "interval '1 second' WHERE id=%s", (task["id"],))
        connection.execute("UPDATE creator_reply_messages SET body_attempted_at="
                           "clock_timestamp()-interval '6 minutes' WHERE id=%s", (crashed_row["id"],))
        connection.commit()
    replacement = task_for(store, c["id"], kind="marketing.gmail_sync")
    candidates = store.body_capture_candidates(replacement, state, 3)
    check(crashed_row["id"] in {row["id"] for row in candidates},
          "An abandoned reading claim was permanently starved")
    reclaimed = store.claim_reply_body(replacement, state, crashed_row["id"])
    check(reclaimed["body_attempt_count"] == 2, "Crash recovery reset the attempt budget")
    capture = {"status": "complete", "text": private_text, "format": "plain", "error_code": None}
    store.save_reply_body(replacement, state, reclaimed, capture, messages[-1])
    try:
        store.save_reply_body(task, state, abandoned, capture, messages[-1])
    except MarketingOutreachError as exc:
        check("lease" in str(exc), "Abandoned owner was rejected for an unrelated reason")
    else:
        raise AssertionError("Abandoned owner overwrote a reclaimed complete snapshot")
    check(store.get_reply(c["id"], crashed_row["id"])["body_complete"],
          "Stale owner changed the reclaimed body")
    groups.append("Expired reading claims recover within budget; abandoned owners cannot save")

    messages.append({**messages[0], "gmail_message_id": "body-cancel"})
    state = store.gmail_context(c["id"], mailbox_key, label)
    store.save_gmail(replacement, state, [messages[-1]], cursor=None, pending=[], mark_complete=False)
    state = store.gmail_context(c["id"], mailbox_key, label)
    prior_complete = state["last_complete_at"]
    cancelled_row = next(row for row in store.overview(c["id"])["pending_replies"]
                         if row["gmail_message_id"] == "body-cancel")
    cancelled_claim = store.claim_reply_body(replacement, state, cancelled_row["id"])
    with store.connect() as connection:
        connection.execute("UPDATE agent_tasks SET cancellation_requested_at=clock_timestamp() "
                           "WHERE id=%s", (replacement["id"],))
        connection.commit()
    for operation in (
        lambda: store.save_reply_body(replacement, state, cancelled_claim, capture, messages[-1]),
        lambda: store.finalize_reply_sync(replacement, state),
    ):
        try:
            operation()
        except MarketingOutreachError as exc:
            check("lease" in str(exc), "Cancelled capture was rejected for an unrelated reason")
        else:
            raise AssertionError("Cancelled capture persisted body or marked monitoring complete")
    current = store.gmail_context(c["id"], mailbox_key, label)
    check(current["last_complete_at"] == prior_complete
          and not store.get_reply(c["id"], cancelled_row["id"])["body_text"],
          "Failed capture changed full-body evidence or completion freshness")
    groups.append("Cancelled capture cannot persist partial text or advance monitor completion")
    return groups


def exercise_mailbox_failure_hold(store):
    c, _, _ = campaign(store)
    state = store.gmail_context(c["id"], "b" * 64, "Hermes/Creators")
    first = task_for(store, c["id"], kind="marketing.gmail_sync")
    store.finalize_reply_sync(first, state)
    store.complete_task(first["id"], first["lease_id"], {"fixture": True})
    with store.connect() as connection:
        check(creator_mailbox_is_fresh(connection, c["id"]), "Initial complete sync was not fresh")
    failed = task_for(store, c["id"], kind="marketing.gmail_sync")
    failed = store.fail_task(failed["id"], failed["lease_id"],
                             "MARKETING_EXECUTION_FAILED", "Fixed synthetic Gmail failure")
    check(failed["status"] in {"failed", "dead_lettered"}, "Synthetic sync did not fail terminally")
    queued = store.create_task(TaskCreate(
        title="Synthetic newer queued Gmail read", kind="marketing.gmail_sync",
        payload={"campaign_id": str(c["id"])}, requested_by="creator-automation-smoke",
    ))
    check(queued["status"] == "queued", "Synthetic newer sync is not queued")
    sync = store.overview(c["id"])["gmail_sync"]
    check(sync["last_failure_at"] == failed["completed_at"]
          and sync["last_failure_at"] > sync["last_complete_at"],
          "Safe overview hid a failure behind recent success or newer queued work")
    check("error_message" not in sync, "Overview exposed a raw sync failure")
    with store.connect() as connection:
        check(not creator_mailbox_is_fresh(connection, c["id"]),
              "A known sync failure did not immediately block automatic Gmail freshness")
    recovered = task_for(store, c["id"], kind="marketing.gmail_sync")
    current = store.gmail_context(c["id"], "b" * 64, "Hermes/Creators")
    store.finalize_reply_sync(recovered, current)
    sync = store.overview(c["id"])["gmail_sync"]
    check(sync["last_complete_at"] >= sync["last_failure_at"]
          and sync["last_failure_at"] == failed["completed_at"],
          "Completed recovery lost failure history or failed to supersede it")
    with store.connect() as connection:
        check(creator_mailbox_is_fresh(connection, c["id"]),
              "A later owned complete sync did not restore freshness")
    return "Known failed sync overrides fresh timestamp and queued work until owned complete recovery"


def exercise_reply_draft_curation(store):
    c, run, _ = campaign(store, count=2, cap=2)
    store.execute(task_for(store, c["id"], run["id"]), sender="sender@example.test")
    accepted = actions(store, c["id"])
    for action in accepted:
        accept_fixture(store, action)
    sync_task = task_for(store, c["id"], kind="marketing.gmail_sync")
    state = store.gmail_context(c["id"], "c" * 64, "Hermes/Creators")
    replies = []
    for index, action in enumerate(accepted):
        current = store.gmail_context(c["id"], "c" * 64, "Hermes/Creators")
        message = {"gmail_message_id": f"curation{index}", "gmail_thread_id": f"curation-thread{index}",
                   "sender": action["public_context"]["recipient"],
                   "subject": "Re: " + action["public_context"]["subject"],
                   "snippet": "Synthetic curation preview", "received_at": datetime.now(UTC)}
        store.save_gmail(sync_task, current, [message], cursor=None, pending=[])
        reply = next(row for row in store.overview(c["id"])["pending_replies"]
                     if row["gmail_message_id"] == message["gmail_message_id"])
        detail = capture_fixture_body(store, sync_task, state, reply,
                                      "Yes, happy to discuss. Please share your Discord contact.")
        replies.append(detail)
    store.review_reply(c["id"], replies[0]["id"], CreatorReplyReview(
        actor="synthetic-reader", classification="interested", body_digest=replies[0]["body_digest"],
    ))
    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET contact_authorized_at=NULL,"
                           "contact_authorized_by=NULL WHERE campaign_id=%s", (c["id"],))
        before_actions = connection.execute("SELECT count(*) AS n FROM external_actions").fetchone()["n"]
        before_approvals = connection.execute("SELECT count(*) AS n FROM task_approvals").fetchone()["n"]
        connection.commit()
    curator = CreatorReplyDraftStore(store._dsn)
    queued = curator.queue_automatic_reply_drafts(sync_task, c["id"])
    check(queued["created"] == 2, "Reviewed/held and unreviewed replies were not both curated")
    check(curator.queue_automatic_reply_drafts(sync_task, c["id"])["created"] == 0,
          "Repeated sync duplicated the same curation evidence")
    first = curator.list_reply_drafts(c["id"], replies[0]["id"])[0]
    second = curator.list_reply_drafts(c["id"], replies[1]["id"])[0]
    check(not first["contact_authorized"] and not first["sending_authority"],
          "Draft-only curation reauthorized a held contact")
    same = curator.queue_reply_draft(c["id"], replies[0]["id"], CreatorReplyDraftCreate(
        actor="synthetic-owner", body_digest=replies[0]["body_digest"],
    ))
    check(same["id"] == first["id"], "Operator request bypassed automatic evidence deduplication")
    forged = store.create_task(TaskCreate(
        title="Synthetic forged reply curation", kind="marketing.creator_reply_draft",
        payload={"reply_draft_id": str(first["id"])}, requested_by="synthetic-forgery-proof",
    ))
    forged = store.transition_to_running(forged["id"], 300, "synthetic-forgery-proof")
    try:
        curator.get_reply_draft_for_execution(first["id"], forged["id"], forged["lease_id"])
    except CreatorReplyDraftConflictError:
        pass
    else:
        raise AssertionError("Generic task acquired a privileged reply draft snapshot")
    task = store.transition_to_running(first["task_id"], 300, "synthetic-reply-worker")
    check(task["max_attempts"] == 1, "Reply curation can repeat after a worker crash")
    row = curator.get_reply_draft_for_execution(first["id"], task["id"], task["lease_id"])
    with ThreadPoolExecutor(max_workers=2) as executor:
        reservations = list(executor.map(lambda _: curator.start_reply_inference_invocation(
            draft_id=first["id"], task_id=task["id"], lease_id=task["lease_id"],
            requested_model="synthetic-local-model",
        ), range(2)))
    check(sum(value is not None for value in reservations) == 1,
          "Concurrent workers reserved more than one local reply invocation")
    invocation = next(value for value in reservations if value is not None)
    curator.complete_inference_invocation(
        invocation, selected_model="synthetic-local-model", selected_provider="ollama",
        prompt_tokens=1, completion_tokens=1, total_tokens=2, cost=0, latency_ms=1, fallback_attempt=1,
    )
    schema = reply_response_schema(row["model_context"])
    plan = {key: value["enum"][0] for key, value in schema["properties"].items()}
    copy = parse_reply_model_copy(json.dumps(plan), row["model_context"])
    curator.save_reply_draft(draft_id=first["id"], task_id=task["id"], lease_id=task["lease_id"],
                             copy=copy, selected_model="synthetic-local-model")
    store.complete_task(task["id"], task["lease_id"], {"fixture": True, "sending_authority": False})
    ready = curator.list_reply_drafts(c["id"], replies[0]["id"])[0]
    check(ready["status"] == "ready" and ready["body"] and ready["context_current"]
          and not ready["sending_authority"], "Private reply draft was not retained safely")
    overview = store.overview(c["id"])
    check(len(overview["reply_drafts"]) == 2
          and all("body" not in item and "subject" not in item for item in overview["reply_drafts"]),
          "Reviewed creator draft is undiscoverable or overview leaked private copy")
    with store.connect() as connection:
        check(connection.execute("SELECT count(*) AS n FROM external_actions").fetchone()["n"]
              == before_actions, "Curation created an SMTP packet")
        check(connection.execute("SELECT count(*) AS n FROM task_approvals").fetchone()["n"]
              == before_approvals, "Curation approved an action")
        audit = connection.execute("SELECT input_metadata,result_metadata FROM audit_events "
                                   "WHERE task_id=%s", (first["task_id"],)).fetchall()
        check(ready["body"] not in json.dumps(audit, default=str), "Curation audit leaked private copy")
        for _ in range(2):
            connection.execute("INSERT INTO creator_email_drafts(campaign_id,prospect_id,requested_by,"
                               "idempotency_key,status,input_snapshot,input_hash,model_context) "
                               "VALUES (%s,%s,'synthetic-budget',%s,'failed','{}',%s,'{}')",
                               (c["id"], first["prospect_id"], uuid4(), uuid4().hex))
        connection.execute("UPDATE marketing_campaigns SET sender_name='Changed synthetic sender' "
                           "WHERE id=%s", (c["id"],))
        connection.commit()
        counts = CreatorDraftStore._draft_budget_counts(connection, first["prospect_id"])
        check(counts["creator"] == 3, "Initial and reply preparation attempts do not share budget")
    try:
        curator.queue_reply_draft(c["id"], replies[0]["id"], CreatorReplyDraftCreate(
            actor="synthetic-owner", body_digest=replies[0]["body_digest"],
        ))
    except CreatorReplyDraftConflictError as exc:
        check("limit" in str(exc), "Shared budget refused for an unrelated reason")
    else:
        raise AssertionError("Reply curation ignored consumed initial/failed preparation budget")
    second_task = store.transition_to_running(second["task_id"], 300, "synthetic-reply-worker")
    try:
        curator.get_reply_draft_for_execution(second["id"], second_task["id"], second_task["lease_id"])
    except CreatorReplyDraftConflictError:
        pass
    else:
        raise AssertionError("Changed campaign crossed frozen reply curation context")
    stale = curator.list_reply_drafts(c["id"], replies[0]["id"])[0]
    check(not stale["context_current"] and stale["body"] == ready["body"],
          "Context mutation erased history or presented stale copy as current")
    return ["Held reviewed/unreviewed reply drafts deduplicate, stay private and create no email authority",
            "Reply task/audit/context fences, one local invocation and shared failed budgets are durable"]


def exercise_reply_draft_recovery(store):
    c, run, _ = campaign(store)
    store.execute(task_for(store, c["id"], run["id"]), sender="sender@example.test")
    action = actions(store, c["id"])[0]
    accept_fixture(store, action)
    sync_task = task_for(store, c["id"], kind="marketing.gmail_sync")
    state = store.gmail_context(c["id"], "a" * 64, "Hermes/Creators")
    message = {"gmail_message_id": "recovery-source", "gmail_thread_id": "recovery-thread",
               "sender": action["public_context"]["recipient"],
               "subject": "Re: " + action["public_context"]["subject"],
               "snippet": "Synthetic recovery preview", "received_at": datetime.now(UTC)}
    store.save_gmail(sync_task, state, [message], cursor=None, pending=[])
    reply = store.overview(c["id"])["pending_replies"][0]
    detail = capture_fixture_body(store, sync_task, state, reply,
                                  "Please share your Discord contact to discuss.")
    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET contact_authorized_at=NULL,"
                           "contact_authorized_by=NULL WHERE campaign_id=%s", (c["id"],))
        connection.commit()
    curator = CreatorReplyDraftStore(store._dsn)
    request = CreatorReplyDraftCreate(actor="synthetic-owner", body_digest=detail["body_digest"])
    original = curator.queue_reply_draft(c["id"], reply["id"], request)
    task = store.transition_to_running(original["task_id"], 300, "synthetic-recovery-worker")
    invocation = curator.start_reply_inference_invocation(
        draft_id=original["id"], task_id=task["id"], lease_id=task["lease_id"],
        requested_model="synthetic-local-model",
    )
    curator.fail_inference_invocation(invocation, "CREATOR_LOCAL_TIMEOUT")
    curator.fail_reply_draft(original["id"], task["id"], task["lease_id"],
                             "CREATOR_REPLY_DRAFT_MODEL_UNAVAILABLE")
    store.fail_task(task["id"], task["lease_id"], "MARKETING_EXECUTION_FAILED", "Synthetic timeout")
    scope = SimpleNamespace(creator_reply_draft_campaign_ids=[c["id"]])
    with patch("app.creator_reply_draft_store.get_settings", return_value=scope):
        try:
            curator.queue_reply_draft_retry(c["id"], reply["id"], original["id"], request)
        except CreatorReplyDraftConflictError as exc:
            check("cooldown" in str(exc), "Recovery cooldown refused for an unrelated reason")
        else:
            raise AssertionError("A fresh model failure bypassed the recovery cooldown")
        with store.connect() as connection:
            # Simulate elapsed time and a pre-migration creation audit before recording the baseline.
            failure_at = datetime.now(UTC) - timedelta(minutes=6)
            connection.execute("UPDATE agent_tasks SET completed_at=%s WHERE id=%s",
                               (failure_at, task["id"]))
            connection.execute("UPDATE inference_invocations SET completed_at=%s WHERE id=%s",
                               (failure_at, invocation))
            connection.execute("UPDATE audit_events SET input_metadata=input_metadata-"
                               "'attempt_number'-'retry_of_id' WHERE task_id=%s AND action=%s",
                               (task["id"], "creator.reply_draft.created"))
            connection.commit()

        def source_evidence():
            with store.connect() as connection:
                return [connection.execute(query, (identity,)).fetchall() for query, identity in (
                    ("SELECT * FROM creator_reply_drafts WHERE id=%s", original["id"]),
                    ("SELECT * FROM agent_tasks WHERE id=%s", task["id"]),
                    ("SELECT * FROM inference_invocations WHERE id=%s", invocation),
                    ("SELECT * FROM audit_events WHERE task_id=%s ORDER BY occurred_at,id", task["id"]),
                )]

        before = source_evidence()
        retained = curator.list_reply_drafts(c["id"], reply["id"])[0]
        check(retained["context_current"] and retained["retry_eligible"]
              and retained["status"] == "failed", "Model failure misstated unchanged source context")
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: curator.queue_reply_draft_retry(
                c["id"], reply["id"], original["id"], request,
            ), range(2)))
        child = results[0]
        check(child["id"] == results[1]["id"] and child["attempt_number"] == 2
              and child["retry_of_id"] == original["id"], "Concurrent recovery duplicated lineage")
        check(child["expires_at"] == original["expires_at"]
              and child["input_hash"] == original["input_hash"] and not child["sending_authority"]
              and not child["contact_authorized"], "Recovery changed expiry/context or contact authority")
        check(curator.queue_reply_draft(c["id"], reply["id"], request)["id"] == child["id"]
              and curator.queue_automatic_reply_drafts(sync_task, c["id"])["created"] == 0,
              "Default/native curation created a hidden recovery attempt")
        try:
            curator.queue_reply_draft_retry(c["id"], reply["id"], child["id"], request)
        except CreatorReplyDraftConflictError:
            pass
        else:
            raise AssertionError("A recovery child created a third attempt")
        running = store.transition_to_running(child["task_id"], 300, "synthetic-recovery-worker")
        curator.get_reply_draft_for_execution(child["id"], running["id"], running["lease_id"])
        recovery_invocation = curator.start_reply_inference_invocation(
            draft_id=child["id"], task_id=running["id"], lease_id=running["lease_id"],
            requested_model="synthetic-local-model",
        )
        check(recovery_invocation and recovery_invocation != invocation,
              "Recovery reused or reset the original invocation")
        curator.fail_inference_invocation(recovery_invocation, "CREATOR_REPLY_DRAFT_INTERRUPTED")
        store.cancel_task(running["id"], TaskCancellation(actor="synthetic-owner"))
        store.finalize_cancellation(running["id"], running["lease_id"])
        with store.connect() as connection:
            counts = CreatorDraftStore._draft_budget_counts(connection, original["prospect_id"])
        check(counts["creator"] == 2, "Failed/cancelled recovery attempts escaped shared preparation budget")
        check(source_evidence() == before, "Recovery mutated original task/draft/ledger/audit evidence")
        check(len(actions(store, c["id"])) == 1,
              "Draft-only recovery created an email action")
    return "Explicit model-failure recovery is linked, idempotent, budgeted and preserves original evidence"


def exercise(dsn):
    store = CreatorAutomationStore(dsn)
    groups = []
    c, run, prospects = campaign(store, count=3, cap=1)
    with ThreadPoolExecutor(max_workers=2) as executor:
        scheduled = list(executor.map(lambda _: store.schedule(gmail_enabled=False), range(2)))
    check(sum(map(len, scheduled)) == 1, "Concurrent scheduler duplicated an occurrence")
    with store.connect() as connection:
        queued = connection.execute(
            "SELECT * FROM agent_tasks WHERE id=%s", (next(item for batch in scheduled for item in batch)["task_id"],),
        ).fetchone()
        check(queued["risk_level"] == "medium" and queued["status"] == "queued",
              "Automation task bypassed policy")
    task = store.transition_to_running(queued["id"], 300, "creator-automation-smoke")
    result = store.execute(task, sender="sender@example.test")
    check(result["authorized"] == 1, "Daily allowance not honored")
    result = store.execute(task, sender="sender@example.test")
    check(result["authorized"] == 0 and len(actions(store, c["id"])) == 1,
          "Retry created extra automatic packets")
    with store.connect() as connection:
        approval = connection.execute(
            "SELECT ap.action_context_hash,a.context_hash,t.risk_level FROM task_approvals ap "
            "JOIN agent_tasks t ON t.id=ap.task_id JOIN external_actions a ON a.task_id=t.id",
        ).fetchone()
        check(approval["action_context_hash"] == approval["context_hash"]
              and approval["risk_level"] == "high", "Exact high-risk digest approval absent")
    store.pause(c["id"], "creator-automation-smoke")
    expect_boundary_block(store, actions(store, c["id"])[0], "paused")
    groups.append("Atomic scheduler, exact high-risk approval, rolling cap, replay and Pause boundary")

    c, run, _ = campaign(store, authorized=False)
    result = store.execute(task_for(store, c["id"], run["id"]), sender="sender@example.test")
    check(result["authorized"] == 0 and not actions(store, c["id"]),
          "Discovery or automation granted contact authority")
    groups.append("Unreviewed public contacts cannot receive automatic email")

    shared = f"{uuid4().hex}@example.test"
    c1, r1, _ = campaign(store, shared_email=shared)
    store.execute(task_for(store, c1["id"], r1["id"]), sender="sender@example.test")
    c2, r2, _ = campaign(store, shared_email=shared)
    result = store.execute(task_for(store, c2["id"], r2["id"]), sender="sender@example.test")
    check(result["authorized"] == 0, "Shared address received duplicate campaign authorization")
    groups.append("Cross-campaign shared-address duplicate refusal")

    c, run, _ = campaign(store)
    store.execute(task_for(store, c["id"], run["id"]), sender="sender@example.test")
    with store.connect() as connection:
        connection.execute("UPDATE creator_automation_runs SET expires_at=now() WHERE id=%s",
                           (run["id"],))
        connection.commit()
    expect_boundary_block(store, actions(store, c["id"])[0], "expired")
    c, run, _ = campaign(store)
    store.execute(task_for(store, c["id"], run["id"]), sender="sender@example.test")
    with store.connect() as connection:
        connection.execute("UPDATE marketing_campaigns SET handoff_discord='changed' WHERE id=%s",
                           (c["id"],))
        connection.commit()
    expect_boundary_block(store, actions(store, c["id"])[0], "campaign packet changed")
    groups.append("Expiry and campaign/owner-contact mutation block previously approved actions")

    c, run, prospects = campaign(store, handoff=True)
    automation_task = task_for(store, c["id"], run["id"])
    store.execute(automation_task, sender="sender@example.test")
    initial = actions(store, c["id"])[0]
    accept_fixture(store, initial)
    gmail_task = task_for(store, c["id"], kind="marketing.gmail_sync")
    state = store.gmail_context(c["id"], "f" * 64, "Hermes/Creators")
    message = {"gmail_message_id": "msg1", "gmail_thread_id": "thread1",
               "sender": prospects[0]["contact_email"],
               "subject": "Re: " + initial["public_context"]["subject"],
               "snippet": "Interested, please connect me with the owner.",
               "received_at": datetime.now(UTC) + timedelta(seconds=1)}
    saved = store.save_gmail(gmail_task, state, [message], cursor=None, pending=[])
    check(saved["inserted"] == 1, "Inbound candidate was not persisted")
    result = store.execute(automation_task, sender="sender@example.test")
    check(result["authorized"] == 0 and "Review" in result["reason"],
          "Unreviewed positive snippet authorized handoff")
    reply = store.overview(c["id"])["pending_replies"][0]
    check(reply["prospect_id"] == prospects[0]["id"], "Exact address/subject reply was not matched")
    reply = capture_fixture_body(store, gmail_task, state, reply, message["snippet"])
    store.review_reply(c["id"], reply["id"], CreatorReplyReview(
        actor="creator-automation-smoke", prospect_id=prospects[0]["id"], classification="interested",
        body_digest=reply["body_digest"],
    ))
    result = store.execute(automation_task, sender="sender@example.test")
    check(result["authorized"] == 1, "Reviewed interest did not authorize the bounded handoff")
    handoff = actions(store, c["id"])[-1]
    check(handoff["stage"] == "handoff" and "karixai" in handoff["public_context"]["body"],
          "Handoff did not use frozen owner Discord")
    accept_fixture(store, handoff)
    check(store.get_prospect(prospects[0]["id"])["status"] == "handed_off",
          "Accepted handoff did not stop the automatic conversation")
    check(store.execute(automation_task, sender="sender@example.test")["authorized"] == 0,
          "Handed-off creator received another automatic message")
    fresh = store.gmail_context(c["id"], "f" * 64, "Hermes/Creators")
    check(store.save_gmail(gmail_task, fresh, [message], cursor=None, pending=[])["inserted"] == 0,
          "Mailbox replay duplicated message history")
    groups.append("Positive reply review, matching, one owner handoff, terminal state and Gmail replay")

    c, run, prospects = campaign(store)
    store.execute(task_for(store, c["id"], run["id"]), sender="sender@example.test")
    gmail_task = task_for(store, c["id"], kind="marketing.gmail_sync")
    state = store.gmail_context(c["id"], "e" * 64, "Hermes/Creators")
    message = {**message, "gmail_message_id": "optout1", "sender": prospects[0]["contact_email"],
               "subject": "Unsubscribe", "snippet": "Please do not contact me again"}
    check(store.save_gmail(gmail_task, state, [message], cursor=None, pending=[])["suppressed"] == 1,
          "Unmatched opt-out did not suppress the address immediately")
    expect_boundary_block(store, actions(store, c["id"])[0], "suppressed")
    try:
        store.save_gmail(gmail_task, state, [], cursor=None, pending=[])
    except MarketingOutreachError:
        pass
    else:
        raise AssertionError("Stale mailbox cursor was accepted")
    groups.append("Immediate opt-out suppression, pre-send fence and stale mailbox cursor refusal")

    with store.connect() as connection:
        suppression = connection.execute(
            "SELECT 1 FROM creator_contact_suppressions WHERE email=%s",
            (prospects[0]["contact_email"],),
        ).fetchone()
        check(suppression, "Opt-out did not create durable address suppression")
    try:
        campaign(store, shared_email=prospects[0]["contact_email"])
    except MarketingOutreachError:
        pass
    else:
        raise AssertionError("A later campaign authorized a durably suppressed address")
    groups.append("Durable opt-out also blocks new future campaign prospects")

    c, run, _ = campaign(store)
    store.execute(task_for(store, c["id"], run["id"]), sender="sender@example.test")
    action = actions(store, c["id"])[0]
    claimed = store.transition_to_running(action["task_id"], 300, "creator-automation-smoke")
    with ThreadPoolExecutor(max_workers=1) as executor:
        with store.connect() as connection:
            connection.execute("SELECT id FROM marketing_campaigns WHERE id=%s FOR UPDATE",
                               (c["id"],))
            connection.execute(
                "INSERT INTO creator_reply_messages(campaign_id,gmail_message_id,gmail_thread_id,"
                "sender,subject,snippet,received_at,suggested_classification,match_reason) "
                "VALUES (%s,'concurrent1','thread1','other@example.test','Question','What?',"
                "now(),'question','Synthetic race proof')", (c["id"],),
            )
            future = executor.submit(store.begin_side_effect, claimed["id"], uuid4().hex * 2,
                                     claimed["lease_id"])
            time.sleep(0.1)
            check(not future.done(), "Boundary ignored the campaign evidence lock")
            connection.commit()
        try:
            future.result(timeout=10)
        except SideEffectGuardError as exc:
            check("Review new creator replies" in str(exc), "Concurrent reply failed wrong guard")
        else:
            raise AssertionError("Concurrent reply crossed the side-effect receipt boundary")
    groups.append("Concurrent reply commit is observed after the final campaign row-lock wait")

    c, run, _ = campaign(store)
    store.execute(task_for(store, c["id"], run["id"]), sender="sender@example.test")
    accept_fixture(store, actions(store, c["id"])[0])
    store.pause(c["id"], "creator-automation-smoke")
    store.schedule(gmail_enabled=True)
    with store.connect() as connection:
        mailbox_task = connection.execute(
            "SELECT kind,risk_level FROM agent_tasks WHERE kind='marketing.gmail_sync' "
            "AND payload->>'campaign_id'=%s", (str(c["id"]),),
        ).fetchone()
        check(mailbox_task and mailbox_task["risk_level"] == "low",
              "Recent sent conversation lost read-only reply monitoring after Pause")
    check(store.overview(c["id"])["run"]["state"] == "paused",
          "Reply monitoring renewed sending authority")
    groups.append("Read-only monitoring continues after Pause without renewing send authority")

    c, run, prospects = campaign(store)
    prepared = store.plan_outreach_email(prospects[0]["id"], MarketingEmailPlanCreate(
        actor="creator-automation-smoke", stage="initial"), sender="sender@example.test",
        automation_context={"run_id": str(run["id"])})
    store.pause(c["id"], "creator-automation-smoke")
    check(actions(store, c["id"])[0]["status"] == "cancelled",
          "Pause left an unapproved stale-grant packet blocking a new run")
    replacement = store.start(c["id"], CreatorAutomationStart(actor="creator-automation-smoke"))
    task = task_for(store, c["id"], replacement["id"])
    tampered = {**task, "payload": {**task["payload"], "run_id": str(run["id"])}}
    try:
        store.execute(tampered, sender="sender@example.test")
    except MarketingOutreachError:
        pass
    else:
        raise AssertionError("Source task payload could be rebound to a different run")
    check(store.execute(task, sender="sender@example.test")["authorized"] == 1,
          "A new grant could not prepare a fresh packet after unapproved cancellation")
    groups.append("Stopped unapproved packets are cancelled and source-task run binding is enforced")

    c, run, prospects = campaign(store)
    with store.connect() as connection:
        connection.execute(
            """INSERT INTO marketing_prospects(campaign_id,platform,external_id,display_name,
               profile_url,audience_size,contact_email,contact_source_url,contact_basis_note,
               contact_authorized_at,contact_authorized_by,status,relevance_score,intelligence,
               latest_content_published_at)
               SELECT campaign_id,platform,external_id||'-'||g,display_name,
                      profile_url||'-'||g,audience_size,contact_email,contact_source_url,
                      contact_basis_note,contact_authorized_at,contact_authorized_by,
                      'interested',100,intelligence,latest_content_published_at
               FROM marketing_prospects CROSS JOIN generate_series(1,110) g WHERE id=%s""",
            (prospects[0]["id"],),
        )
        connection.commit()
    check(store.execute(task_for(store, c["id"], run["id"]),
                        sender="sender@example.test")["authorized"] == 1,
          "Disabled handoffs in the first page starved an eligible introduction")
    groups.append("More than one page of ineligible candidates cannot starve eligible outreach")

    c, run, prospects = campaign(store)
    prepared = store.plan_outreach_email(prospects[0]["id"], MarketingEmailPlanCreate(
        actor="creator-automation-smoke", stage="initial"), sender="sender@example.test",
        automation_context={"run_id": str(run["id"])})
    task = task_for(store, c["id"], run["id"])
    with store.connect() as connection:
        connection.execute("UPDATE agent_tasks SET lease_expires_at=clock_timestamp()+"
                           "interval '300 milliseconds' WHERE id=%s", (task["id"],))
        connection.commit()
    with ThreadPoolExecutor(max_workers=1) as executor:
        with store.connect() as connection:
            connection.execute("SELECT id FROM marketing_campaigns WHERE id=%s FOR UPDATE",
                               (c["id"],))
            future = executor.submit(store._authorize, task, run["id"], prospects[0]["id"],
                                     prepared, "initial")
            time.sleep(0.5)
            connection.commit()
        try:
            future.result(timeout=10)
        except MarketingOutreachError as exc:
            check("lease" in str(exc), "Expired source task failed the wrong guard")
        else:
            raise AssertionError("Source lease expiry during a row-lock wait authorized an action")
    with store.connect() as connection:
        check(not connection.execute("SELECT 1 FROM creator_automation_actions WHERE action_id=%s",
                                     (prepared["id"],)).fetchone(),
              "Expired source lease left an irreversible grant reservation")
    groups.append("Source lease expiry during a row wait rolls back authorization and reservation")

    c, run, prospects = campaign(store, count=4, cap=3)
    task = task_for(store, c["id"], run["id"])
    check(store.execute(task, sender="sender@example.test")["authorized"] == 3,
          "Learning fixture did not create the bounded initial sample")
    sent = actions(store, c["id"])
    for action in sent:
        accept_fixture(store, action)
    for action in sent[:2]:
        store.record_outcome(action["prospect_id"], MarketingOutcomeCreate(
            classification="question", note="Synthetic reviewed revenue-share question",
            feedback_tags=["unclear_revenue_share"], actor="creator-learning-smoke",
        ))
    third = sent[2]
    gmail_task = task_for(store, c["id"], kind="marketing.gmail_sync")
    state = store.gmail_context(c["id"], "d" * 64, "Hermes/Creators")
    message = {"gmail_message_id": "learning1", "gmail_thread_id": "learning-thread",
               "sender": third["public_context"]["recipient"],
               "subject": "Re: " + third["public_context"]["subject"],
               "snippet": "What percentage are you offering?",
               "received_at": datetime.now(UTC) + timedelta(seconds=1)}
    store.save_gmail(gmail_task, state, [message], cursor=None, pending=[])
    reply = store.overview(c["id"])["pending_replies"][0]
    check("unclear_revenue_share" in reply["suggested_feedback_tags"],
          "Inbound evidence did not expose a reviewable feedback suggestion")
    check(store.campaign_results(c["id"])[0]["learning"]["recommended_variant"] is None,
          "Unreviewed third reply changed the learning recommendation")
    reply = capture_fixture_body(store, gmail_task, state, reply, message["snippet"])
    store.review_reply(c["id"], reply["id"], CreatorReplyReview(
        actor="creator-learning-smoke", prospect_id=third["prospect_id"], classification="question",
        feedback_tags=["unclear_revenue_share"],
        body_digest=reply["body_digest"],
    ))
    learning = store.campaign_results(c["id"])[0]["learning"]
    check(learning["recommended_variant"] == "terms_first"
          and learning["evidence_source"] == "reviewed_feedback"
          and learning["feedback_counts"]["unclear_revenue_share"] == 3,
          "Three distinct reviewed feedback records did not explain the copy recommendation")
    unsent = next(p for p in prospects if p["id"] not in {a["prospect_id"] for a in sent})
    adapted = store.plan_outreach_email(unsent["id"], MarketingEmailPlanCreate(
        actor="creator-learning-smoke", stage="initial"), sender="sender@example.test")
    selection = adapted["public_context"]["marketing"]["selection_reason"]
    check("reviewed feedback" in selection or "exploration" in selection,
          "Next exact draft did not retain its learning explanation")
    check(adapted["status"] == "pending_approval", "Learning bypassed exact-action approval")
    check(store.get_campaign(c["id"])["paid_offer_details"] == c["paid_offer_details"],
          "Learning mutated commercial terms")
    groups.append("Reviewed manual/Gmail feedback explains future copy without altering terms/approval")

    own, own_run, _own_prospects = campaign(store)
    other, other_run, _ = campaign(store)
    for current, current_run in ((own, own_run), (other, other_run)):
        store.execute(task_for(store, current["id"], current_run["id"]),
                      sender="sender@example.test")
        accept_fixture(store, actions(store, current["id"])[0])
    original = actions(store, own["id"])[0]
    message = {"gmail_message_id": "sharedlabel1", "gmail_thread_id": "shared-thread",
               "sender": original["public_context"]["recipient"],
               "subject": "Re: " + original["public_context"]["subject"],
               "snippet": "Interested in hearing more",
               "received_at": datetime.now(UTC) + timedelta(seconds=1)}
    other_task = task_for(store, other["id"], kind="marketing.gmail_sync")
    for current, sync_task in ((own, task_for(store, own["id"], kind="marketing.gmail_sync")),
                               (other, other_task)):
        state = store.gmail_context(current["id"], "b" * 64, "Hermes/Creators")
        store.save_gmail(sync_task, state, [message], cursor=None, pending=[])
    check(store.overview(own["id"])["pending_reply_count"] == 1,
          "Own campaign lost its matched labeled reply")
    check(store.overview(other["id"])["pending_reply_count"] == 0,
          "Known foreign-campaign reply blocked unrelated campaign automation")
    fresh = store.gmail_context(other["id"], "b" * 64, "Hermes/Creators")
    optout = {**message, "gmail_message_id": "sharedlabel-optout", "snippet": "Unsubscribe"}
    result = store.save_gmail(other_task, fresh, [optout], cursor=None, pending=[])
    check(result["ignored_foreign"] == 1 and result["suppressed"] == 1,
          "Foreign-campaign filtering swallowed a global opt-out")
    fresh = store.gmail_context(other["id"], "b" * 64, "Hermes/Creators")
    unknown = {**message, "gmail_message_id": "unmatched-label", "sender": "new@example.test"}
    store.save_gmail(other_task, fresh, [unknown], cursor=None, pending=[])
    check(store.overview(other["id"])["pending_reply_count"] == 1,
          "Truly unmatched labeled reply was silently discarded")
    groups.append("Shared Gmail label routes known campaign replies and preserves opt-outs/uncertainty")

    c, run, prospects = campaign(store)
    prepared = store.plan_outreach_email(prospects[0]["id"], MarketingEmailPlanCreate(
        actor="creator-automation-smoke", stage="initial"), sender="sender@example.test",
        automation_context={"run_id": str(run["id"])})
    task = task_for(store, c["id"], run["id"])
    with ThreadPoolExecutor(max_workers=1) as executor:
        with store.connect() as owner:
            owner.execute("SELECT id FROM agent_tasks WHERE id=%s FOR UPDATE",
                          (prepared["task_id"],))
            future = executor.submit(store._authorize, task, run["id"], prospects[0]["id"],
                                     prepared, "initial")
            time.sleep(0.1)
            with store.connect() as observer:
                observer.execute("SELECT id FROM marketing_campaigns WHERE id=%s FOR UPDATE NOWAIT",
                                 (c["id"],))
                observer.commit()
            store.decide_task(prepared["task_id"], ApprovalDecision(
                decision="approved", actor="creator-smoke-operator", reason="Synthetic race probe",
            ), connection=owner)
            owner.commit()
        try:
            future.result(timeout=10)
        except MarketingOutreachError as exc:
            check("already decided" in str(exc), "Operator race failed the wrong guard")
        else:
            raise AssertionError("Concurrent operator decision was overwritten")
    groups.append("Operator approval races share task-before-campaign lock order without deadlock")

    c, run, prospects = campaign(store)
    store.execute(task_for(store, c["id"], run["id"]), sender="sender@example.test")
    action = actions(store, c["id"])[0]
    claimed = store.transition_to_running(action["task_id"], 300, "creator-automation-smoke")
    with ThreadPoolExecutor(max_workers=1) as executor:
        with store.connect() as writer:
            writer.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                           (f"creator-email:{prospects[0]['contact_email'].lower()}",))
            writer.execute("INSERT INTO creator_contact_suppressions(email,reason) VALUES(%s,%s)",
                           (prospects[0]["contact_email"], "Synthetic cross-campaign manual opt-out"))
            future = executor.submit(store.begin_side_effect, claimed["id"], uuid4().hex * 2,
                                     claimed["lease_id"])
            time.sleep(0.1)
            check(not future.done(), "Final boundary ignored a concurrent recipient suppression")
            writer.commit()
        try:
            future.result(timeout=10)
        except SideEffectGuardError as exc:
            check("suppressed" in str(exc), "Recipient suppression race failed wrong guard")
        else:
            raise AssertionError("Committed cross-campaign opt-out crossed the final boundary")
    groups.append("Global manual opt-out committed during recipient-lock wait blocks delivery")

    c, run, prospects = campaign(store)
    store.execute(task_for(store, c["id"], run["id"]), sender="sender@example.test")
    with ThreadPoolExecutor(max_workers=1) as executor:
        with store.connect() as writer:
            writer.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended('creator-automation',0))")
            writer.execute("INSERT INTO creator_contact_suppressions(email,reason) VALUES(%s,%s)",
                           (prospects[0]["contact_email"], "Synthetic concurrent Gmail opt-out"))
            future = executor.submit(store.record_outcome, prospects[0]["id"],
                                     MarketingOutcomeCreate(classification="do_not_contact",
                                         actor="creator-automation-smoke", note="Manual opt-out"))
            time.sleep(0.1)
            check(not future.done(), "Manual opt-out ignored the shared suppression writer lock")
            writer.execute("SELECT id FROM marketing_prospects WHERE id=%s FOR UPDATE NOWAIT",
                           (prospects[0]["id"],))
            store._suppress_address(writer, prospects[0]["contact_email"])
            writer.commit()
        try:
            future.result(timeout=10)
        except MarketingOutreachError as exc:
            check("already suppressed" in str(exc), "Concurrent manual opt-out failed wrong guard")
        else:
            raise AssertionError("Concurrent manual opt-out ignored committed Gmail suppression")
    groups.append("Manual and Gmail opt-outs share writer-before-prospect lock order")
    exercise_pacing_time_guards(dsn)
    groups.append("Global pacing waits recheck creator run, Gmail/publication freshness and AI research TTL")
    groups.extend(exercise_reply_bodies(store))
    groups.append(exercise_mailbox_failure_hold(store))
    groups.extend(exercise_reply_draft_curation(store))
    groups.append(exercise_reply_draft_recovery(store))
    return groups


def main():
    migrations = globals().get("MIGRATIONS")
    if migrations is None:
        folder = Path(__file__).resolve().parents[1] / "config" / "postgres" / "init"
        migrations = [path.read_text(encoding="utf-8") for path in sorted(folder.glob("*.sql"))]
    source = os.environ["DATABASE_URL"]
    name = "creator_automation_probe_" + uuid4().hex
    check(re.fullmatch(r"creator_automation_probe_[0-9a-f]{32}", name)
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
            store = CreatorAutomationStore(dsn)
            legacy_email = f"legacy-{uuid4().hex}@example.test"
            with store.connect() as connection:
                prior = connection.execute(
                    """INSERT INTO marketing_prospects(campaign_id,platform,external_id,
                       display_name,profile_url,contact_email,status,suppressed_at,suppression_reason)
                       SELECT id,'youtube',%s,'Legacy suppressed creator',
                              'https://youtube.com/channel/legacy',%s,'suppressed',now(),
                              'Legacy operator-recorded opt-out'
                       FROM marketing_campaigns LIMIT 1 RETURNING campaign_id""",
                    (uuid4().hex, legacy_email),
                ).fetchone()
                connection.commit()
            with psycopg.connect(dsn, autocommit=True) as connection:
                for migration in migrations:
                    connection.execute(migration)
            try:
                store.create_prospect(MarketingProspectCreate(
                    campaign_id=prior["campaign_id"], platform="youtube", external_id=uuid4().hex,
                    profile_url="https://youtube.com/channel/legacy-new", display_name="New alias",
                    contact_email=legacy_email, contact_source_url="https://example.test/business",
                    contact_basis_note="Synthetic attempted reauthorization of old opt-out",
                    authorize_contact=True, requested_by="creator-automation-smoke",
                ))
            except MarketingOutreachError:
                pass
            else:
                raise AssertionError("Migration failed to preserve legacy opt-outs globally")
            groups.append("Legacy per-prospect opt-outs backfill durable global address suppression")
            groups.append("All migrations replay with durable handoff, grants and reply evidence")
        print(f"Creator automation PostgreSQL proof passed: {len(groups)} scenario groups")
        for group in groups:
            print(f"  PASS {group}")
    finally:
        if created:
            with psycopg.connect(maintenance, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            print("Disposable creator database removed; no HTTP, SMTP, model or browser request")


if __name__ == "__main__":
    main()
