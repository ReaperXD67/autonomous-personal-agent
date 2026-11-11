#!/usr/bin/env python3
"""Synthetic PostgreSQL deferral proof; never connects to any mail provider."""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from app.action_models import EmailActionCreate
from app.action_store import SideEffectGuardError
from app.creator_automation_models import CreatorReplyDeferralCreate
from app.creator_automation_store import (
    BODY_VERSION,
    CreatorAutomationStore,
    reply_body_digest,
)
from app.creator_draft_content import parse_model_copy
from app.creator_draft_models import CreatorDraftCreate
from app.creator_draft_store import CreatorDraftStore
from app.creator_reply_deferral import _scope_hash
from app.email_pacing import EmailPacingPolicy
from app.marketing_models import (
    MarketingCampaignCreate,
    MarketingEmailPlanCreate,
    MarketingProspectCreate,
)
from app.marketing_store import MarketingOutreachError
from app.models import ApprovalDecision, TaskCancellation
from app.store import InvalidTaskStateError
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb


class DeferralStore(CreatorDraftStore, CreatorAutomationStore):
    pass


def check(value, message):
    if not value:
        raise AssertionError(message)


def blocked(call, error, fragment=None):
    try:
        call()
    except error as exc:
        if fragment:
            check(fragment in str(exc), f"Unexpected deferral refusal: {exc}")
    else:
        raise AssertionError("Invalid deferral crossed the reviewed creator boundary")


def prospect(store, campaign, *, address=None, channel=None):
    channel = channel or "UC" + uuid4().hex[:22]
    row = store.create_prospect(MarketingProspectCreate(
        campaign_id=campaign["id"], platform="youtube", external_id=channel,
        profile_url=f"https://www.youtube.com/channel/{channel}",
        display_name="Synthetic Minecraft Creator", audience_size=10000,
        contact_email=address or f"{uuid4().hex}@example.test",
        contact_source_url=f"https://www.youtube.com/channel/{channel}",
        contact_basis_note="Explicit synthetic public business collaboration invitation",
        authorize_contact=True, requested_by="reply-deferral-smoke",
    ))
    with store.connect() as connection:
        connection.execute(
            "UPDATE marketing_prospects SET intelligence=%s,latest_content_title="
            "'Minecraft server exploration',latest_content_url="
            "'https://www.youtube.com/watch?v=abcdefghijk',latest_content_published_at="
            "clock_timestamp()-interval '1 day' WHERE id=%s",
            (Jsonb({"topics": ["Minecraft", "Servers"]}), row["id"]),
        )
    return store.get_prospect(row["id"])


def prepare(store, target, draft=None):
    return store.plan_outreach_email(target["id"], MarketingEmailPlanCreate(
        actor="reply-deferral-smoke", stage="initial",
        **({"ai_draft_id": draft["id"], "ai_draft_digest": draft["draft_digest"]}
           if draft else {}),
    ), sender="operator@example.test")


def approve(store, action):
    return store.decide_task(action["task_id"], ApprovalDecision(
        decision="approved", actor="reply-deferral-smoke",
    ))


def claim_due(store, action):
    with store.connect() as connection:
        connection.execute("UPDATE agent_tasks SET next_attempt_at=clock_timestamp()-"
                           "interval '1 hour' WHERE id=%s", (action["task_id"],))
        connection.execute("UPDATE outbound_email_schedule SET scheduled_for=clock_timestamp()-"
                           "interval '1 hour' WHERE action_id=%s", (action["id"],))
    task = store.transition_to_running(action["task_id"], 300, "reply-deferral-smoke")
    check(task, "Synthetic reviewed action was not claimable")
    return task


def age_synthetic_acceptance(store, action):
    with store.connect() as connection:
        connection.execute("UPDATE outbound_email_schedule SET scheduled_for="
                           "clock_timestamp()-interval '2 hours',completed_at="
                           "clock_timestamp()-interval '2 hours' WHERE action_id=%s", (action["id"],))
        connection.execute("UPDATE side_effect_receipts SET started_at="
                           "clock_timestamp()-interval '2 hours',completed_at="
                           "clock_timestamp()-interval '2 hours' WHERE action_id=%s", (action["id"],))


def ready_draft(store, target):
    row = store.create_draft(target["id"], CreatorDraftCreate(
        actor="reply-deferral-smoke", idempotency_key=uuid4(),
    ))
    task = store.transition_to_running(row["task_id"], 300, "reply-deferral-smoke")
    owned = store.get_draft_for_execution(row["id"], task["id"], task["lease_id"])
    copy = parse_model_copy(json.dumps({"evidence_id": "sample_video",
                                       "angle_id": "first_session"}), owned["model_context"])
    saved = store.save_draft(draft_id=row["id"], task_id=task["id"], lease_id=task["lease_id"],
                             copy=copy, source="ollama", selected_model="synthetic-no-inference")
    # Synthetic ledger evidence exercises the genuine-provider/task binding;
    # the fixture never invokes a model or represents this as a live response.
    with store.connect() as connection:
        connection.execute(
            "INSERT INTO inference_invocations (task_id,purpose,provider,requested_models,"
            "selected_model,selected_provider,privacy_mode,status,completed_at) VALUES (%s,"
            "'marketing.creator_draft','ollama',%s,'synthetic-no-inference','ollama',"
            "'local_only','succeeded',clock_timestamp())",
            (task["id"], Jsonb(["synthetic-no-inference"])),
        )
    store.complete_task(task["id"], task["lease_id"], {"synthetic": True})
    return saved


def insert_reply(store, campaign, held, *, suffix=None):
    row = {
        "campaign_id": campaign["id"], "gmail_message_id": suffix or uuid4().hex,
        "gmail_thread_id": uuid4().hex, "sender": held["contact_email"],
        "subject": "Synthetic commercial policy question", "received_at": datetime.now(UTC),
        "body_text": "Please discuss paid promotion terms directly with the owner.",
        "body_format": "plain", "body_version": BODY_VERSION,
        "body_mailbox_key": "a" * 64, "body_label_name": "Hermes/Creators",
    }
    row["body_digest"] = reply_body_digest(row)
    fields = list(row)
    with store.connect() as connection:
        result = connection.execute(
            "INSERT INTO creator_reply_messages (" + ",".join(fields) +
            ",prospect_id,snippet,suggested_classification,match_reason,body_status,body_fetched_at) "
            "VALUES (" + ",".join(["%s"] * len(fields)) +
            ",%s,'Synthetic complete reply','question','Synthetic accepted-message match',"
            "'complete',clock_timestamp()) RETURNING *",
            (*row.values(), held["id"]),
        ).fetchone()
    return result


def fixture(store, *, count=1):
    campaign = store.create_campaign(MarketingCampaignCreate(
        name="Synthetic bounded reply deferral", product_name="FixtureCraft",
        product_url="https://example.test/", privacy_url="https://example.test/privacy",
        product_summary="A synthetic Minecraft server discovery website for validation.",
        target_audience="Minecraft players", viewer_offer="Explore synthetic servers",
        creator_offer="Discuss an optional independent test", paid_offer_enabled=True,
        paid_offer_details="Revenue share and earning weeks agreed individually",
        outreach_mode="paid", compensation_model="revenue_share",
        handoff_discord="karixai", sender_name="Synthetic owner", discovery_queries=["Minecraft"],
        min_subscribers=0, max_subscribers=250000, max_video_age_days=90,
        requested_by="reply-deferral-smoke", active=False,
    ))
    held = prospect(store, campaign)
    # Establish the earlier successful conversation through the real action store.
    prior = prepare(store, held)
    approve(store, prior)
    claimed = claim_due(store, prior)
    fingerprint = uuid4().hex * 2
    store.begin_side_effect(claimed["id"], fingerprint, claimed["lease_id"])
    store.complete_side_effect(claimed["id"], fingerprint, "synthetic-no-SMTP")
    store.complete_task(claimed["id"], claimed["lease_id"], {"smtp_accepted": True,
                                                               "synthetic": True})
    age_synthetic_acceptance(store, prior)
    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET contact_authorized_at=NULL,"
                           "contact_authorized_by=NULL WHERE id=%s", (held["id"],))
        connection.execute("INSERT INTO creator_gmail_sync_state (campaign_id,mailbox_key,"
                           "label_name,last_complete_at) VALUES (%s,%s,'Hermes/Creators',"
                           "clock_timestamp())", (campaign["id"], "a" * 64))
    reply = insert_reply(store, campaign, held)
    targets = [prospect(store, campaign) for _ in range(count)]
    drafts = [ready_draft(store, target) for target in targets]
    return campaign, held, reply, targets, drafts


def deferral_request(reply, targets, **changes):
    return CreatorReplyDeferralCreate(**{
        "actor": "synthetic-owner", "idempotency_key": uuid4(),
        "body_digest": reply["body_digest"], "prospect_ids": [target["id"] for target in targets],
        "confirmation": "defer this reply for reviewed new initials",
        "reason": "Owner explicitly defers this complete commercial reply for reviewed new initials",
        **changes,
    })


def authorize(store, campaign, reply, targets, **changes):
    return store.create_reply_deferral(campaign["id"], reply["id"],
                                       deferral_request(reply, targets, **changes))


def wait_for_lock(blocker, future, *, kind="advisory"):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not future.done():
        blocker.execute("SELECT pg_stat_clear_snapshot()")
        if blocker.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=current_database() "
            "AND pid<>pg_backend_pid() AND application_name='creator-reply-deferral-smoke' "
            "AND wait_event_type='Lock' AND wait_event=%s) AS waiting", (kind,),
        ).fetchone()["waiting"]:
            return
        time.sleep(0.02)
    raise AssertionError("Reviewed action did not reach its actual global pacing wait")


def nearly_elapsed_scope(store, scope):
    # Advance this isolated fixture's finite clock before binding any packet.
    with store.connect() as connection:
        row = connection.execute(
            "UPDATE creator_reply_deferrals SET created_at=clock_timestamp()-"
            "interval '23 hours',expires_at=clock_timestamp()+interval '3 seconds' "
            "WHERE id=%s RETURNING *", (scope["id"],),
        ).fetchone()
        scope_hash = _scope_hash(row)
        connection.execute("UPDATE creator_reply_deferrals SET scope_hash=%s WHERE id=%s",
                           (scope_hash, scope["id"]))
        connection.execute("UPDATE audit_events SET input_metadata=jsonb_set(input_metadata,"
                           "'{scope_hash}',%s) WHERE action='creator.reply.deferral.created' "
                           "AND input_metadata->>'deferral_id'=%s",
                           (Jsonb(scope_hash), str(scope["id"])))


def exercise(dsn):
    store = DeferralStore(make_conninfo(dsn, application_name="creator-reply-deferral-smoke"),
                          email_pacing_policy=EmailPacingPolicy(60, 60, 10, 50, 0))
    groups = []
    c, held, reply, targets, drafts = fixture(store, count=3)
    blocked(lambda: prepare(store, targets[0], drafts[0]), MarketingOutreachError)
    before = store.get_reply(c["id"], reply["id"])
    blocked(lambda: authorize(store, c, reply, [held]), MarketingOutreachError)
    blocked(lambda: authorize(store, c, reply, targets, body_digest="b" * 64),
            MarketingOutreachError)
    request = deferral_request(reply, targets)
    grant = store.create_reply_deferral(c["id"], reply["id"], request)
    check(grant and grant["id"], "Owner deferral did not persist its finite identity")
    repeated = store.create_reply_deferral(c["id"], reply["id"], request)
    check(repeated["id"] == grant["id"], "Idempotent review created duplicate deferral authority")
    changed = request.model_copy(update={"prospect_ids": [targets[0]["id"]]})
    blocked(lambda: store.create_reply_deferral(c["id"], reply["id"], changed),
            MarketingOutreachError)
    groups.append("Creation requires exact complete digest, fresh finite new identities and idempotent scope")
    actions = [prepare(store, target, draft) for target, draft in zip(targets, drafts, strict=True)]
    for action in actions:
        check(store.get_task(action["task_id"])["status"] == "pending_approval",
              "Deferral silently approved an exact message")
    after = store.get_reply(c["id"], reply["id"])
    check(before == after and after["needs_review"], "Deferral changed captured reply or review")
    check(store.get_prospect(held["id"])["contact_authorized_at"] is None,
          "Deferral restored a held contact")
    groups.append("Three finite AI initials require separate exact approvals; reply and hold preserved")

    blocked(lambda: prepare(store, held), MarketingOutreachError)
    outsider = prospect(store, c)
    outsider_draft = ready_draft(store, outsider)
    blocked(lambda: prepare(store, outsider, outsider_draft), MarketingOutreachError)
    blocked(lambda: prepare(store, outsider), MarketingOutreachError)
    groups.append("Held identities, unlisted prospects and template introductions remain blocked")

    approve(store, actions[2])
    accepted = claim_due(store, actions[2])
    fingerprint = uuid4().hex * 2
    store.begin_side_effect(accepted["id"], fingerprint, accepted["lease_id"])
    store.complete_side_effect(accepted["id"], fingerprint, "synthetic-deferral-no-SMTP")
    store.complete_task(accepted["id"], accepted["lease_id"], {"synthetic": True})
    age_synthetic_acceptance(store, actions[2])
    check(store.get_reply(c["id"], reply["id"])["needs_review"],
          "Valid deferred initial cleared the pending commercial reply")
    groups.append("Valid exact reviewed AI initial acquires one synthetic receipt while reply stays pending")

    # Revoke after exact preparation: neither approval nor final receipt can rely
    # on a deferral that existed only when the packet was created.
    approve(store, actions[0])
    running = claim_due(store, actions[0])
    store.revoke_reply_deferral(c["id"], reply["id"], grant["id"], "synthetic-owner")
    blocked(lambda: approve(store, actions[1]), InvalidTaskStateError)
    blocked(lambda: store.begin_side_effect(running["id"], uuid4().hex * 2, running["lease_id"]),
            SideEffectGuardError)
    groups.append("Revocation fences both prepared approval and already claimed final receipt")

    try:
        replacement = authorize(store, c, reply, targets)
    except MarketingOutreachError:
        replacement = None  # Existing packets may correctly make new membership ineligible.
    if replacement:
        check(replacement["id"] != grant["id"], "Replacement did not retain distinct identity")
    blocked(lambda: approve(store, actions[1]), InvalidTaskStateError)
    groups.append("Replacement deferral cannot revive packets bound to the revoked original")

    for case in ("new_pending", "digest_changed", "expired", "missing_inference", "mailbox_stale",
                 "mailbox_changed"):
        campaign, held, pending, people, copies = fixture(store, count=3)
        scope = authorize(store, campaign, pending, people)
        action = prepare(store, people[0], copies[0])
        unapproved = prepare(store, people[1], copies[1])
        approve(store, action)
        claimed = claim_due(store, action)
        with store.connect() as connection:
            if case == "new_pending":
                insert_reply(store, campaign, held)
            elif case == "digest_changed":
                connection.execute("UPDATE creator_reply_messages SET body_digest=%s WHERE id=%s",
                                   ("b" * 64, pending["id"]))
            elif case == "expired":
                connection.execute("UPDATE creator_reply_deferrals SET created_at="
                                   "clock_timestamp()-interval '2 hours',expires_at="
                                   "clock_timestamp()-interval '1 second' WHERE id=%s",
                                   (scope["id"],))
            elif case == "missing_inference":
                connection.execute("DELETE FROM inference_invocations WHERE task_id=ANY(%s)",
                                   ([copy["task_id"] for copy in copies],))
            elif case == "mailbox_stale":
                connection.execute("UPDATE creator_gmail_sync_state SET last_complete_at="
                                   "clock_timestamp()-interval '31 minutes' WHERE campaign_id=%s",
                                   (campaign["id"],))
            else:
                connection.execute("UPDATE creator_gmail_sync_state SET mailbox_key=%s "
                                   "WHERE campaign_id=%s", ("b" * 64, campaign["id"]))
        blocked(lambda people=people, copies=copies: prepare(store, people[2], copies[2]),
                MarketingOutreachError)
        blocked(lambda unapproved=unapproved: approve(store, unapproved), InvalidTaskStateError)
        blocked(lambda claimed=claimed: store.begin_side_effect(claimed["id"], uuid4().hex * 2,
                                                                claimed["lease_id"]),
                SideEffectGuardError)
        with store.connect() as connection:
            check(not connection.execute("SELECT 1 FROM side_effect_receipts WHERE task_id=%s",
                                         (claimed["id"],)).fetchone(),
                  "Changed reply scope acquired an SMTP receipt")
        groups.append(f"Preparation, approval and final receipt reject {case}; reply stays pending")

    # Expiry must be re-read after the global lock, rather than using transaction
    # start time or a success observed before a potentially long wait.
    for boundary in ("preparation", "approval", "receipt"):
        campaign, _, pending, people, copies = fixture(store)
        scope = authorize(store, campaign, pending, people)
        nearly_elapsed_scope(store, scope)
        if boundary == "preparation":
            with store.connect() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
                blocker.execute("LOCK TABLE external_actions IN SHARE MODE")
                future = pool.submit(prepare, store, people[0], copies[0])
                try:
                    wait_for_lock(blocker, future, kind="relation")
                    time.sleep(3.2)
                finally:
                    blocker.commit()
                blocked(lambda future=future: future.result(timeout=10), MarketingOutreachError)
            check(store.get_draft(copies[0]["id"])["status"] == "ready",
                  "Expired preparation wait left a partially prepared AI draft")
            groups.append("Deferral expiry after real preparation INSERT wait rolls back the packet")
            continue
        action = prepare(store, people[0], copies[0])
        claimed = None
        if boundary == "receipt":
            approve(store, action)
            claimed = claim_due(store, action)
        with store.connect() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
            blocker.execute("SELECT pg_advisory_xact_lock(%s,%s)", (1212502605, 1))
            call = ((lambda action=action: approve(store, action)) if boundary == "approval" else
                    (lambda claimed=claimed: store.begin_side_effect(claimed["id"], uuid4().hex * 2,
                                                                     claimed["lease_id"])))
            future = pool.submit(call)
            try:
                wait_for_lock(blocker, future)
                time.sleep(3.2)
            finally:
                blocker.commit()
            blocked(lambda future=future: future.result(timeout=10),
                    InvalidTaskStateError if boundary == "approval" else SideEffectGuardError)
        groups.append(f"Deferral expiry is rechecked after real {boundary} global pacing wait")

    campaign, _, pending, people, copies = fixture(store)
    scope = authorize(store, campaign, pending, people)
    unrelated = store.create_email_action(EmailActionCreate(
        actor="reply-deferral-smoke", recipient="unrelated@example.test",
        subject="Synthetic pacing reservation", body="Never delivered; fixture only.",
    ), sender="operator@example.test")
    approve(store, unrelated)
    nearly_elapsed_scope(store, scope)
    action = prepare(store, people[0], copies[0])
    blocked(lambda: approve(store, action), InvalidTaskStateError)
    check(store.get_task(action["task_id"])["status"] == "pending_approval",
          "Impossible finite send slot recorded an exact approval")
    store.cancel_task(unrelated["task_id"], TaskCancellation(actor="reply-deferral-smoke",
                                                            reason="Synthetic pacing proof complete"))
    groups.append("Approval refuses a reserved SMTP slot beyond the finite deferral deadline")
    return groups


def main():
    migrations = globals().get("MIGRATIONS")
    if migrations is None:
        folder = Path(__file__).resolve().parents[1] / "config" / "postgres" / "init"
        migrations = [path.read_text(encoding="utf-8") for path in sorted(folder.glob("*.sql"))]
    source = os.environ["DATABASE_URL"]
    name = "creator_reply_deferral_probe_" + uuid4().hex
    check(re.fullmatch(r"creator_reply_deferral_probe_[0-9a-f]{32}", name)
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
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("HTTP forbidden")), \
                patch("smtplib.SMTP", side_effect=AssertionError("SMTP forbidden")), \
                patch("smtplib.SMTP_SSL", side_effect=AssertionError("SMTP forbidden")):
            groups = exercise(dsn)
        print(json.dumps({"creator_reply_deferral": "passed", "groups": groups}, indent=2))
    finally:
        if created:
            with psycopg.connect(maintenance, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            print("Disposable deferral database removed; no HTTP, SMTP, model or browser request")


if __name__ == "__main__":
    main()
