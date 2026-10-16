#!/usr/bin/env python3
"""Disposable PostgreSQL proof; never contacts a creator, mailbox, model, or SMTP server."""

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
from app.creator_automation_models import CreatorAutomationStart, CreatorReplyReview
from app.creator_automation_store import CreatorAutomationStore
from app.marketing_models import (
    MarketingCampaignCreate,
    MarketingEmailPlanCreate,
    MarketingOutcomeCreate,
    MarketingProspectCreate,
)
from app.marketing_store import MarketingOutreachError
from app.models import ApprovalDecision, TaskCreate
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


def expect_boundary_block(store, action, text):
    claimed = store.transition_to_running(action["task_id"], 300, "creator-automation-smoke")
    check(claimed, "Action could not be claimed for boundary test")
    try:
        store.begin_side_effect(claimed["id"], uuid4().hex * 2, claimed["lease_id"])
    except SideEffectGuardError as exc:
        check(text in str(exc), f"Unexpected boundary error: {exc}")
    else:
        raise AssertionError("Revoked creator grant crossed the side-effect boundary")


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
    store.review_reply(c["id"], reply["id"], CreatorReplyReview(
        actor="creator-automation-smoke", prospect_id=prospects[0]["id"], classification="interested",
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
    store.review_reply(c["id"], reply["id"], CreatorReplyReview(
        actor="creator-learning-smoke", prospect_id=third["prospect_id"], classification="question",
        feedback_tags=["unclear_revenue_share"],
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

    own, own_run, own_prospects = campaign(store)
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
