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
from uuid import UUID, uuid4, uuid5

import psycopg
from app.action_store import SideEffectGuardError
from app.application_browser import canonical_hash
from app.creator_draft_batch_store import (
    KIND as BATCH_KIND,
)
from app.creator_draft_batch_store import (
    CreatorDraftBatchCreate,
    CreatorDraftBatchStore,
)
from app.creator_draft_content import model_context, parse_model_copy
from app.creator_draft_models import CreatorDraftCreate, CreatorDraftView
from app.creator_draft_store import (
    CreatorDraftConflictError,
    CreatorDraftStore,
    lock_draft_for_prepare,
)
from app.creator_learning import creator_learning_insights
from app.marketing_models import (
    MarketingCampaignCreate,
    MarketingEmailPlanCreate,
    MarketingProspectCreate,
)
from app.marketing_store import MarketingOutreachError
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


def creator_fixture(store, campaign, *, title="Minecraft server exploration"):
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
            "UPDATE marketing_prospects SET intelligence=%s,latest_content_title=%s,"
            "latest_content_url='https://www.youtube.com/watch?v=abcdefghijk',"
            "latest_content_published_at=now()-interval '1 day' WHERE id=%s",
            (Jsonb({"topics": ["Minecraft", "Servers"]}), title, prospect["id"]),
        )
    return prospect


def fixture(store, *, polish=False):
    campaign = store.create_campaign(MarketingCampaignCreate(
        name="Synthetic AI copy", product_name="FixtureCraft",
        product_url="https://example.test/", privacy_url="https://example.test/privacy",
        product_summary=("katalog serwerów Minecraft do samodzielnego sprawdzenia" if polish else
                         "A synthetic Minecraft server discovery website for validation."),
        target_audience="Minecraft players", viewer_offer="Explore servers",
        creator_offer="Explore an optional pilot", paid_offer_enabled=True,
        paid_offer_details=("Opcjonalny test serwera w wybranym przez Ciebie formacie" if polish else
                            "A server tour with individually discussed terms"), outreach_mode="paid",
        compensation_model="revenue_share", handoff_discord="karixai", sender_name="Synthetic",
        language_mode="prefer" if polish else "any", target_language="pl" if polish else None,
        revenue_share_percent=23 if polish else None, revenue_share_weeks=3 if polish else None,
        revenue_share_basis="przychód przypisany uzgodnionej promocji" if polish else None,
        discovery_queries=["Minecraft"], requested_by="creator-draft-smoke",
    ))
    return campaign, creator_fixture(store, campaign)


def create(store, prospect):
    return store.create_draft(
        prospect["id"], CreatorDraftCreate(actor="creator-draft-smoke", idempotency_key=uuid4()),
    )


def claim(store, row):
    task = store.transition_to_running(row["task_id"], 300, "creator-draft-smoke")
    check(task is not None, "Could not claim draft task")
    return task


def synthetic_copy(context):
    if context.get("drafting_contract") == "creator-grounded-plan-v2":
        wire = {"evidence_id": "sample_video", "angle_id": "first_session"}
        check(any(angle["id"] == wire["angle_id"] for angle in context["angles"]),
              "Synthetic selection is not offered by the frozen server context")
        return parse_model_copy(json.dumps(wire), context)
    return parse_model_copy(json.dumps({
        "hook": "Your public Minecraft server exploration title caught my attention.",
        "content_idea": "Perhaps a short trial exploring a server from the website could "
                        "be an optional fit for your own exploration format.",
        "rationale": "The observed server topic supports a small exploratory pilot.",
        "evidence_ids": ["sample_video"], "reach_strategy": "small_pilot",
    }), context)


def save(store, row, task):
    owned = store.get_draft_for_execution(row["id"], task["id"], task["lease_id"])
    copy = synthetic_copy(owned["model_context"])
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


def batch_fixture(store, count, *, available=None):
    campaign, prospect = fixture(store)
    prospects = [prospect] + [creator_fixture(store, campaign)
                              for _ in range((available or count) - 1)]
    request = CreatorDraftBatchCreate(
        actor="creator-draft-smoke", idempotency_key=uuid4(), limit=count,
    )
    return campaign, prospects, request, store.create_batch(campaign["id"], request)


def batch_children(store, parent):
    keys = [UUID(item["child_idempotency_key"]) for item in parent["payload"]["items"]]
    with store.connect() as connection:
        return connection.execute(
            "SELECT * FROM creator_email_drafts WHERE idempotency_key=ANY(%s) ORDER BY id",
            (keys,),
        ).fetchall()


def external_counts(store):
    with store.connect() as connection:
        return connection.execute(
            "SELECT (SELECT count(*) FROM external_actions) AS packets,"
            "(SELECT count(*) FROM task_approvals) AS approvals,"
            "(SELECT count(*) FROM side_effect_receipts) AS receipts",
        ).fetchone()


def age_preparation_window(store):
    # Separate scenario windows inside this disposable database, never production data.
    with store.connect() as connection:
        connection.execute("UPDATE creator_email_drafts SET created_at=now()-interval '25 hours'")
        connection.execute("UPDATE audit_events SET occurred_at=now()-interval '25 hours' "
                           "WHERE action='creator.draft_batch.created'")


def exercise_batch_budget(store):
    age_preparation_window(store)
    # All stopped reservations below retain their actual current creation times.
    _, _, _, cancelled = batch_fixture(store, 5)
    store.cancel_task(cancelled["task"]["id"], TaskCancellation(
        actor="fixture", reason="Synthetic reserved batch cancellation",
    ))
    _, _, _, failed = batch_fixture(store, 5)
    failed_task = claim(store, {"task_id": failed["task"]["id"]})
    store.fail_task(failed_task["id"], failed_task["lease_id"],
                    "SYNTHETIC_BATCH_FAILURE", "Disposable fixture only")
    check(store.get_task(cancelled["task"]["id"])["status"] == "cancelled"
          and store.get_task(failed_task["id"])["status"] == "failed",
          "Budget proof did not retain actual stopped parent tasks")
    _, _, _, materialized = batch_fixture(store, 5)
    materialized_task = claim(store, {"task_id": materialized["task"]["id"]})
    result = store.execute_batch(materialized_task)
    check(result["queued_count"] == 5, "Materialized reservation fixture did not issue five drafts")
    store.complete_task(materialized_task["id"], materialized_task["lease_id"], result)
    campaign, first = fixture(store)
    for prospect in [first, *[creator_fixture(store, campaign) for _ in range(12)]]:
        create(store, prospect)
    race_campaigns = []
    for _ in range(2):
        race_campaign, _ = fixture(store)
        creator_fixture(store, race_campaign)
        race_campaigns.append(race_campaign)

    def reserve_last_slots(campaign):
        try:
            return store.create_batch(campaign["id"], CreatorDraftBatchCreate(
                actor="creator-draft-smoke", idempotency_key=uuid4(), limit=2,
            ))
        except MarketingOutreachError as exc:
            check("thirty per rolling day" in str(exc), "Unexpected concurrent budget refusal")
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        raced = list(executor.map(reserve_last_slots, race_campaigns))
    winners = [row for row in raced if row is not None]
    check(len(winners) == 1 and len(winners[0]["items"]) == 2,
          "Concurrent reservations failed the remaining-two-slots global budget")
    extra = creator_fixture(store, campaign)
    blocked(lambda: create(store, extra), CreatorDraftConflictError, "thirty per rolling day")
    winner_task = claim(store, {"task_id": winners[0]["task"]["id"]})
    winner_result = store.execute_batch(winner_task)
    check(winner_result["queued_count"] == 2,
          "A fully reserved budget blocked materializing its own final two children")
    store.complete_task(winner_task["id"], winner_task["lease_id"], winner_result)
    blocked(lambda: create(store, extra), CreatorDraftConflictError, "thirty per rolling day")
    replayed = store.get_batch(materialized_task["id"])
    check(replayed["queued_count"] == 5 and len(batch_children(store, materialized_task)) == 5,
          "Budget exhaustion lost already materialized children")
    with store.connect() as connection:
        actual = connection.execute(
            "SELECT count(*) AS n FROM creator_email_drafts "
            "WHERE created_at>now()-interval '24 hours'",
        ).fetchone()["n"]
    check(actual == 20, "Reserved and materialized slots were confused with actual draft rows")


def exercise_batches(dsn):
    store = CreatorDraftBatchStore(dsn)
    groups = []
    before_external = external_counts(store)
    age_preparation_window(store)
    campaign, prospects, request, view = batch_fixture(store, 5, available=7)
    parent = view["task"]
    check(parent["kind"] == BATCH_KIND and parent["risk_level"] == "medium"
          and parent["status"] == "queued", "Batch bypassed the governed medium-risk task path")
    check(len(view["items"]) == view["reserved_count"] == 5,
          "Batch did not preserve the five-item preparation cap")
    for item in parent["payload"]["items"]:
        check(UUID(item["child_idempotency_key"]) == uuid5(
            request.idempotency_key, item["prospect_id"],
        ), "Reserved child identity is not stable across replay")
    creator_fixture(store, campaign)
    check(store.create_batch(campaign["id"], request)["task"] == parent,
          "Idempotent batch replay recomputed membership from a changing pool")
    blocked(lambda: store.create_batch(campaign["id"], CreatorDraftBatchCreate(
        actor="different-actor", idempotency_key=request.idempotency_key, limit=5,
    )), MarketingOutreachError, "Idempotency")
    with store.connect() as connection:
        check(connection.execute("SELECT 1 FROM task_outbox WHERE task_id=%s",
                                 (parent["id"],)).fetchone(), "Batch has no durable outbox")
        issued = connection.execute(
            "SELECT input_metadata,result_metadata FROM audit_events WHERE task_id=%s "
            "AND action='creator.draft_batch.created'", (parent["id"],),
        ).fetchone()
        check(issued["input_metadata"]["payload_hash"] == canonical_hash(parent["payload"])
              and issued["input_metadata"]["batch_size"] == 5,
              "Creation audit is not bound to the complete issued reservation")
        check(issued["result_metadata"] == {"messages_sent": 0, "approvals_created": 0},
              "Draft batch creation implied sending or approval authority")
    groups.append("Bounded batch freezes membership and UUID children through policy, outbox and hash audit")

    owned = claim(store, {"task_id": parent["id"]})
    queue_child = store._queue_reserved_child
    committed = 0

    def crash_after_commit(*args):
        nonlocal committed
        result = queue_child(*args)
        committed += 1
        if committed == 1:
            raise RuntimeError("Synthetic crash after first child commit")
        return result

    with patch.object(store, "_queue_reserved_child", side_effect=crash_after_commit):
        blocked(lambda: store.execute_batch(owned), RuntimeError, "Synthetic crash")
    check(len(batch_children(store, owned)) == 1, "Synthetic crash did not preserve one committed child")
    resumed = store.execute_batch(owned)
    check(resumed["queued_count"] == 5 and resumed["skipped_count"] == 0,
          "Resumed batch did not issue only its frozen remaining children")
    check(store.execute_batch(owned) == resumed, "Repeating a running batch changed child results")
    children = batch_children(store, owned)
    check(len(children) == len({row["task_id"] for row in children}) == 5,
          "Crash replay duplicated a draft or child task")
    check({row["prospect_id"] for row in children} < {row["id"] for row in prospects},
          "Batch did not retain only its selected subset")
    with store.connect() as connection:
        check(connection.execute(
            "SELECT count(*) AS n FROM audit_events WHERE task_id=%s "
            "AND action='creator.draft_batch.item'", (owned["id"],),
        ).fetchone()["n"] == 5, "Resume duplicated per-item durable outcomes")
        for child in children:
            task = store.get_task(child["task_id"])
            check(task["status"] == "queued" and task["risk_level"] == "medium",
                  "Batch child escaped ordinary governed drafting")
            check(connection.execute("SELECT 1 FROM task_outbox WHERE task_id=%s",
                                     (child["task_id"],)).fetchone(), "Child has no durable outbox")
            check(connection.execute(
                "SELECT 1 FROM audit_events WHERE task_id=%s AND action='creator_draft.created'",
                (child["task_id"],),
            ).fetchone(), "Child creation has no durable draft audit")
    store.complete_task(owned["id"], owned["lease_id"], resumed)
    groups.append("Committed child issuance survives interruption and replay without duplicate tasks or audits")

    _, original_creators, _, identity_view = batch_fixture(store, 1)
    original = original_creators[0]
    duplicate_campaign, same_channel = fixture(store)
    same_address = creator_fixture(store, duplicate_campaign)
    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET external_id=%s,profile_url=%s WHERE id=%s",
                           (original["external_id"], original["profile_url"], same_channel["id"]))
        connection.execute("UPDATE marketing_prospects SET contact_email=%s WHERE id=%s",
                           (original["contact_email"], same_address["id"]))

    def duplicate_batch():
        return store.create_batch(duplicate_campaign["id"], CreatorDraftBatchCreate(
            actor="creator-draft-smoke", idempotency_key=uuid4(), limit=2,
        ))

    blocked(duplicate_batch, MarketingOutreachError, "No eligible")
    identity_task = claim(store, {"task_id": identity_view["task"]["id"]})
    identity_result = store.execute_batch(identity_task)
    check(identity_result["queued_count"] == 1, "Identity fixture did not materialize its original draft")
    store.complete_task(identity_task["id"], identity_task["lease_id"], identity_result)
    blocked(duplicate_batch, MarketingOutreachError, "No eligible")
    shared_campaign, shared_first = fixture(store)
    shared_second = creator_fixture(store, shared_campaign)
    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET contact_email=%s WHERE id=%s",
                           (shared_first["contact_email"], shared_second["id"]))
    shared = store.create_batch(shared_campaign["id"], CreatorDraftBatchCreate(
        actor="creator-draft-smoke", idempotency_key=uuid4(), limit=2,
    ))
    check(shared["reserved_count"] == 1,
          "One batch reserved two creator records sharing the same business email")
    with store.connect() as connection:
        check(connection.execute("SELECT count(*) AS n FROM creator_email_drafts "
                                 "WHERE prospect_id=ANY(%s)",
                                 ([same_channel["id"], same_address["id"]],)).fetchone()["n"] == 0,
              "Cross-campaign identity dedup issued a duplicate draft")
    groups.append("Reserved and current drafts deduplicate channels and exact business addresses across campaigns")

    _, _, _, skip_view = batch_fixture(store, 4)
    skip_task = claim(store, {"task_id": skip_view["task"]["id"]})
    skip_items = skip_task["payload"]["items"]
    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET audience_size=audience_size+1 WHERE id=%s",
                           (UUID(skip_items[0]["prospect_id"]),))
        connection.execute("UPDATE marketing_prospects SET suppressed_at=now() WHERE id=%s",
                           (UUID(skip_items[1]["prospect_id"]),))
    create(store, {"id": UUID(skip_items[2]["prospect_id"])})
    skipped = store.execute_batch(skip_task)
    check(skipped["queued_count"] == 1 and skipped["skipped_count"] == 3,
          "Changed research, suppression or an independently queued draft did not skip the item")
    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET audience_size=10000,suppressed_at=NULL "
                           "WHERE id=ANY(%s)", ([UUID(item["prospect_id"]) for item in skip_items[:2]],))
    check(store.execute_batch(skip_task) == skipped and len(batch_children(store, skip_task)) == 1,
          "Terminal per-item skips were reopened after evidence became eligible again")
    store.complete_task(skip_task["id"], skip_task["lease_id"], skipped)
    _, _, _, stale_view = batch_fixture(store, 2)
    stale_task = claim(store, {"task_id": stale_view["task"]["id"]})
    with store.connect() as connection:
        connection.execute("UPDATE marketing_campaigns SET max_subscribers=5000 WHERE id=%s",
                           (UUID(stale_task["payload"]["campaign_id"]),))
    stale_result = store.execute_batch(stale_task)
    check(stale_result["skipped_count"] == 2 and not batch_children(store, stale_task),
          "Changed targeting was allowed to materialize a frozen batch")
    store.complete_task(stale_task["id"], stale_task["lease_id"], stale_result)
    groups.append("Changed evidence, suppression, targeting and current drafts produce durable per-item skips")

    _, _, _, cancel_view = batch_fixture(store, 2)
    cancel_task = claim(store, {"task_id": cancel_view["task"]["id"]})
    store._queue_reserved_child(cancel_task["id"], cancel_task["lease_id"],
                                cancel_task["payload"]["items"][0])
    store.cancel_task(cancel_task["id"], TaskCancellation(
        actor="fixture", reason="Synthetic cancellation after one committed child",
    ))
    blocked(lambda: store.execute_batch(cancel_task), InvalidTaskStateError, "valid execution lease")
    check(len(batch_children(store, cancel_task)) == 1,
          "Cancellation issued remaining children or removed the independently queued child")
    _, expiry_prospects, _, expiry_view = batch_fixture(store, 1)
    expiry_task = claim(store, {"task_id": expiry_view["task"]["id"]})
    with store.connect() as connection:
        connection.execute("UPDATE agent_tasks SET lease_expires_at=clock_timestamp()+"
                           "interval '0.5 seconds' WHERE id=%s", (expiry_task["id"],))
    with ThreadPoolExecutor(max_workers=1) as executor:
        with store.connect() as blocker:
            blocker.execute("SELECT id FROM marketing_prospects WHERE id=%s FOR UPDATE",
                            (expiry_prospects[0]["id"],))
            future = executor.submit(store.execute_batch, expiry_task)
            time.sleep(0.8)
            blocker.commit()
        blocked(lambda: future.result(timeout=10), InvalidTaskStateError, "valid execution lease")
    check(not batch_children(store, expiry_task), "Expired parent lease queued a child after its row wait")
    groups.append("Parent cancellation preserves committed children and lease expiry fences remaining issuance")

    _, _, _, genuine_view = batch_fixture(store, 1)
    genuine = genuine_view["task"]
    forged = store.create_task(TaskCreate(
        title="Synthetic unissued batch", kind=BATCH_KIND, payload=genuine["payload"],
        requested_by="creator-draft-smoke",
    ))
    forged = claim(store, {"task_id": forged["id"]})
    blocked(lambda: store.execute_batch(forged), InvalidTaskStateError, "server-issued")
    with store.connect() as connection:
        connection.execute("UPDATE agent_tasks SET payload=jsonb_set(payload,'{campaign_hash}',%s) "
                           "WHERE id=%s", (Jsonb("f" * 64), genuine["id"]))
    changed = claim(store, {"task_id": genuine["id"]})
    blocked(lambda: store.execute_batch(changed), InvalidTaskStateError, "server-issued")
    check(not batch_children(store, genuine), "Generic or hash-mismatched parent queued a child")
    groups.append("Generic forged parents and changed issued payloads have no child-creation authority")

    _, _, _, creator_cap = batch_fixture(store, 1)
    capped = {"id": UUID(creator_cap["task"]["payload"]["items"][0]["prospect_id"])}
    store.cancel_task(creator_cap["task"]["id"], TaskCancellation(
        actor="fixture", reason="Synthetic stopped reservation still counts",
    ))
    create(store, capped)
    create(store, capped)
    blocked(lambda: create(store, capped), CreatorDraftConflictError, "three per creator")
    groups.append("Stopped batch reservations share the individual three-per-creator preparation limit")

    exercise_batch_budget(store)
    check(external_counts(store) == before_external,
          "Draft batching created an external packet, approval decision or side-effect receipt")
    groups.append("Cancelled, failed and materialized reservations share the rolling thirty-slot concurrent cap")
    groups.append("All batch preparation leaves outgoing packets, approvals and side-effect receipts unchanged")
    return groups


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
    owned = store.get_draft_for_execution(row["id"], claimed["id"], claimed["lease_id"])
    check(owned["model_context"].get("drafting_contract") == "creator-grounded-plan-v2",
          "New drafting did not freeze the grounded selection contract")
    save(store, row, claimed)
    check(store.get_draft(row["id"])["status"] == "queued", "Exposed copy before task completion")
    store.complete_task(claimed["id"], claimed["lease_id"], {"fixture": True})
    saved = store.get_draft(row["id"])
    check(saved["status"] == "ready" and "input_snapshot" not in saved, "Bad ready draft view")
    check(saved["source"] == "ollama" and saved["selected_model"] == "synthetic-test-response",
          "Lost synthetic source provenance")
    check(saved["model_copy"] == synthetic_copy(owned["model_context"]).model_dump(),
          "Saved copy differs from the server-derived evidence selection")
    with ThreadPoolExecutor(max_workers=2) as executor:
        actions = list(executor.map(lambda _: prepare(store, saved), range(2)))
    check(actions[0]["id"] == actions[1]["id"], "Concurrent prepare created duplicate action")
    check(actions[0]["status"] == "pending_approval", "AI copy escaped exact review")
    check(actions[0]["public_context"]["body"] == saved["body"], "Prepared body changed")
    groups.append("Finished copy preserves source and digest; concurrent prepare is exact and unapproved")

    polish_campaign, polish_prospect = fixture(store, polish=True)
    polish_row = create(store, polish_prospect)
    polish_task = claim(store, polish_row)
    polish_owned = store.get_draft_for_execution(
        polish_row["id"], polish_task["id"], polish_task["lease_id"],
    )
    check(polish_owned["model_context"]["output_language"] == "pl",
          "Polish generation language was not stored before model execution")
    polish_copy = synthetic_copy(polish_owned["model_context"])
    store.save_draft(
        draft_id=polish_row["id"], task_id=polish_task["id"], lease_id=polish_task["lease_id"],
        copy=polish_copy, source="ollama", selected_model="synthetic-polish-response",
    )
    store.complete_task(polish_task["id"], polish_task["lease_id"], {"fixture": True})
    with store.connect() as connection:
        polish_before = connection.execute(
            "SELECT model_context,draft_digest,subject,body FROM creator_email_drafts WHERE id=%s",
            (polish_row["id"],),
        ).fetchone()
    polish_view = store.get_draft(polish_row["id"])
    CreatorDraftView.model_validate(polish_view)
    check(polish_view["status"] == "ready" and polish_view["body"].startswith("Cześć "),
          "Completed Polish draft was not rendered in Polish")
    check(polish_view["subject"].startswith("FixtureCraft × Synthetic Creator")
          and "pierwsza sesja" in polish_view["subject"],
          "Polish subject did not identify the product, creator and selected angle")
    for required in (polish_campaign["product_summary"], polish_campaign["paid_offer_details"],
                     polish_campaign["revenue_share_basis"], "23%", "3 tyg.", "Przed publikacją",
                     "przychód czy zysk", "raportowanie i terminy wypłat",
                     polish_campaign["privacy_url"], "do not contact"):
        check(required in polish_view["body"], "Polish rendered envelope lost a required value")
    check(polish_view["quality_report"]["generated_language"] == "pl"
          and not polish_view["quality_report"]["sending_authority"],
          "Polish editorial projection changed language or sending authority")
    check(polish_copy.rationale not in polish_view["body"], "Operator rationale entered email")
    with store.connect() as connection:
        polish_after = connection.execute(
            "SELECT model_context,draft_digest,subject,body FROM creator_email_drafts WHERE id=%s",
            (polish_row["id"],),
        ).fetchone()
    check(polish_before == polish_after, "Draft GET changed the frozen language, digest or copy")
    polish_action = prepare(store, polish_view)
    check(polish_action["status"] == "pending_approval"
          and store.get_task(polish_action["task_id"])["status"] == "pending_approval",
          "Polish copy bypassed exact-message approval")
    check(polish_action["public_context"]["body"] == polish_view["body"]
          and polish_action["public_context"]["subject"] == polish_view["subject"],
          "Polish exact preparation changed the complete rendered message")
    check(store.get_draft(polish_row["id"])["draft_digest"] == polish_before["draft_digest"],
          "Polish exact preparation changed the reviewed digest")
    groups.append("Polish frozen language, deterministic terms, read-only projection and exact review")

    legacy_campaign, legacy_prospect = fixture(store, polish=True)
    legacy_row = create(store, legacy_prospect)
    with store.connect() as connection:
        current_campaign, current_prospect = store._context(connection, legacy_prospect["id"])
        # This disposable row explicitly represents a pre-language-contract v1 record.
        legacy_context = model_context(
            current_campaign, current_prospect, creator_learning_insights([], []),
        )
        legacy_context.pop("output_language", None)
        check("drafting_contract" not in legacy_context,
              "Historical fixture unexpectedly acquired the v2 contract")
        connection.execute("UPDATE creator_email_drafts SET model_context=%s WHERE id=%s",
                           (Jsonb(legacy_context), legacy_row["id"]))
    legacy_saved = ready(store, legacy_row)
    legacy_before = (legacy_saved["model_context"], legacy_saved["subject"],
                     legacy_saved["body"], legacy_saved["draft_digest"])
    legacy_view = store.get_draft(legacy_row["id"])
    check(legacy_view["body"].startswith("Hi ")
          and legacy_view["quality_report"]["generated_language"] == "en",
          "A legacy markerless English draft was translated from current campaign settings")
    with store.connect() as connection:
        legacy_after = connection.execute(
            "SELECT model_context,subject,body,draft_digest FROM creator_email_drafts WHERE id=%s",
            (legacy_row["id"],),
        ).fetchone()
    check(tuple(legacy_after.values()) == legacy_before, "Reading legacy copy rewrote its provenance")
    check(legacy_campaign["target_language"] == "pl", "Legacy language fixture lost its targeting")
    groups.append("Explicit legacy v1 context retains English copy, frozen source and reviewed digest")

    _, tamper_prospect = fixture(store)
    tamper_row = ready(store, create(store, tamper_prospect))
    tamper_before = (tamper_row["body"], tamper_row["draft_digest"])
    with store.connect() as connection:
        connection.execute(
            "UPDATE creator_email_drafts SET model_copy=jsonb_set(model_copy,'{hook}',%s) WHERE id=%s",
            (Jsonb("The platform verifies every Minecraft server before you join."), tamper_row["id"]),
        )
    check(store.get_draft(tamper_row["id"])["status"] == "stale",
          "Stored prose tampering escaped grounded rederivation")
    blocked(lambda: prepare(store, tamper_row), CreatorDraftConflictError, "current evidence checks")
    with store.connect() as connection:
        tamper_after = connection.execute(
            "SELECT body,draft_digest FROM creator_email_drafts WHERE id=%s", (tamper_row["id"],),
        ).fetchone()
        check(tuple(tamper_after.values()) == tamper_before, "Tamper refusal rewrote approved copy")
        check(not connection.execute("SELECT 1 FROM marketing_outreach_messages WHERE prospect_id=%s",
                                     (tamper_prospect["id"],)).fetchone(),
              "Tampered grounded copy created an outgoing packet")
    groups.append("Grounded saved-copy tampering becomes stale without rewriting copy or creating packets")

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
    groups.extend(exercise_batches(dsn))
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
