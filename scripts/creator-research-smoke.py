"""Prove research persistence and authority isolation in a disposable database."""

import csv
import io
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from app.action_store import SideEffectGuardError
from app.creator_draft_batch_store import (
    CreatorDraftBatchCreate,
    CreatorDraftBatchStore,
)
from app.creator_draft_content import parse_model_copy, research_snapshot
from app.creator_draft_models import CreatorDraftCreate
from app.creator_draft_store import CreatorDraftConflictError, CreatorDraftStore
from app.creator_export import creator_coverage, creator_csv
from app.creator_pilot_store import CreatorPilotCreate, CreatorPilotStore
from app.marketing_models import (
    MarketingCampaignCreate,
    MarketingCampaignUpdate,
    MarketingEmailPlanCreate,
    MarketingProspectCreate,
    MarketingProspectUpdate,
)
from app.marketing_store import MarketingOutreachError, MarketingStore
from app.models import ApprovalDecision, TaskCancellation, TaskCreate
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def legacy_budget(dsn, migration):
    store = MarketingStore(dsn)
    task = store.create_task(TaskCreate(
        title="Delayed legacy scan fixture", kind="marketing.creator_discovery",
        payload={"campaign_id": str(uuid4())}, requested_by="research-smoke",
    ))
    with store.connect() as connection:
        connection.execute(
            "UPDATE agent_tasks SET created_at = now() - interval '2 days', "
            "started_at = now(), attempt_count = 2 WHERE id = %s", (task["id"],),
        )
        connection.execute("DELETE FROM schema_migrations WHERE version = '018_creator_discovery_budget'")
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(migration)
        connection.execute(migration)
    with store.connect() as connection:
        row = connection.execute(
            "SELECT count(*) AS count, min(requested_at) > now() - interval '1 minute' AS recent "
            "FROM marketing_youtube_search_requests WHERE task_id = %s", (task["id"],),
        ).fetchone()
        check(row["count"] == 6 and row["recent"], "Legacy delayed/retried scan was not reserved once")
        # Age only these synthetic reservations so the later concurrency proof has a fresh budget.
        connection.execute(
            "UPDATE marketing_youtube_search_requests SET requested_at = now() - interval '25 hours' "
            "WHERE task_id = %s", (task["id"],),
        )


def exercise_history(store, campaign_request, research):
    campaign = store.create_campaign(MarketingCampaignCreate(
        **{**campaign_request.model_dump(), "name": "Source history proof"},
    ))
    channel = "UC" + "h" * 22
    profile = f"https://www.youtube.com/channel/{channel}"
    observed = datetime.now(UTC)
    first_observed = observed - timedelta(days=10)

    def packet(email=None, when=observed):
        return {
            **research, "external_id": channel, "profile_url": profile,
            "intelligence": {"source_channel_id": channel, "researched_at": when.isoformat(),
                             "contact_candidates": [{
                                 "email": email, "source_url": profile,
                                 "evidence": f"Business: {email}", "observed_at": when.isoformat(),
                                 "status": "unreviewed",
                             }] if email else []},
        }

    store.save_discovered_prospects(campaign["id"], [packet("history@example.test", first_observed)])
    prospect = store.list_prospects(campaign_id=campaign["id"], prospect_status=None, limit=1)[0]
    store.save_discovered_prospects(campaign["id"], [packet()])
    archived = store.get_prospect(prospect["id"])
    check(not archived["intelligence"]["contact_candidates"], "Old source became current")
    history = archived["intelligence"]["contact_history"][0]
    check(history["observed_at"] == history["last_seen_at"] == first_observed.isoformat()
          and history["status"] == "historical_unreviewed", "Historical source was freshened")
    reappeared = store.save_prospect_research(
        prospect["id"], packet("history@example.test"), expected_profile_url=profile,
        expected_campaign_id=campaign["id"],
    )
    current = reappeared["intelligence"]["contact_candidates"][0]
    check(current["first_observed_at"] == first_observed.isoformat()
          and current["observed_at"] == observed.isoformat()
          and not reappeared["intelligence"]["contact_history"], "Reappearance lost source timing")

    def refresh(email):
        store.save_prospect_research(prospect["id"], packet(email), expected_profile_url=profile,
                                    expected_campaign_id=campaign["id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(refresh, ["first@example.test", "second@example.test"]))
    concurrent = store.get_prospect(prospect["id"])
    dossier = concurrent["intelligence"]
    addresses = {item["email"] for item in dossier["contact_candidates"] + dossier["contact_history"]}
    check({"first@example.test", "second@example.test"} <= addresses,
          "Concurrent refresh lost public source evidence")
    check(concurrent["contact_email"] is None and concurrent["contact_authorized_at"] is None,
          "History merge granted contact authority")
    expired = store.expire_creator_contact_history(now=observed + timedelta(days=30))
    check(expired == 1, "Due source history cleanup did not persist")
    with store.connect() as connection:
        durable = connection.execute("SELECT intelligence FROM marketing_prospects WHERE id = %s",
                                     (prospect["id"],)).fetchone()["intelligence"]
    check(durable["contact_history"] == [] and durable["contact_history_expires_at"] is None
          and durable["contact_candidates"], "History expiry removed current evidence or kept old data")

    # Populate history again, then prove suppression and identity edits preserve their boundaries.
    store.save_discovered_prospects(campaign["id"], [packet()])
    before_suppression = store.get_prospect(prospect["id"])["intelligence"]["contact_history"]
    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET suppressed_at = now(), status = 'suppressed' "
                           "WHERE id = %s", (prospect["id"],))
    check(store.save_discovered_prospects(campaign["id"], [packet("blocked@example.test")])["updated"] == 0,
          "Suppression accepted a new history merge")
    check(store.get_prospect(prospect["id"])["intelligence"]["contact_history"] == before_suppression,
          "Suppression changed existing source evidence")
    edited = store.update_prospect(prospect["id"], MarketingProspectUpdate(
        display_name="Changed history fixture", profile_url="https://youtube.com/@new_fixture",
        actor="research-smoke",
    ))
    check(not edited["intelligence"].get("contact_history")
          and not edited["intelligence"].get("contact_candidates"),
          "Identity edit retained the former channel contact evidence")


def exercise_active_evidence(dsn, campaign_request, research):
    store = CreatorDraftStore(dsn)
    campaign = store.create_campaign(MarketingCampaignCreate(
        **{**campaign_request.model_dump(), "name": "Active evidence preservation proof",
           "paid_offer_enabled": True, "paid_offer_details": "An optional synthetic server trial",
           "outreach_mode": "paid", "compensation_model": "revenue_share",
           "handoff_discord": "synthetic_owner"},
    ))

    def creator():
        channel = "UC" + uuid4().hex[:22]
        profile = f"https://www.youtube.com/channel/{channel}"
        prospect = store.create_prospect(MarketingProspectCreate(
            campaign_id=campaign["id"], platform="youtube", external_id=channel,
            display_name="Synthetic protected creator", profile_url=profile,
            contact_email=f"{uuid4().hex}@example.test", contact_source_url=profile,
            contact_basis_note="Synthetic public business source", authorize_contact=True,
            requested_by="research-smoke",
        ))
        evidence = {
            **research, "external_id": channel, "profile_url": profile,
            "intelligence": {"source_channel_id": channel, "topics": ["Minecraft", "Servers"]},
        }
        store.save_prospect_research(
            prospect["id"], evidence, expected_profile_url=profile,
            expected_campaign_id=campaign["id"],
        )
        return store.get_prospect(prospect["id"]), evidence

    def draft(prospect, *, ready=True):
        row = store.create_draft(prospect["id"], CreatorDraftCreate(
            actor="research-smoke", idempotency_key=uuid4(),
        ))
        if ready:
            task = store.transition_to_running(row["task_id"], 300, "research-smoke")
            owned = store.get_draft_for_execution(row["id"], task["id"], task["lease_id"])
            copy = parse_model_copy(json.dumps({
                "evidence_id": "sample_video", "angle_id": "first_session",
            }), owned["model_context"])
            row = store.save_draft(
                draft_id=row["id"], task_id=task["id"], lease_id=task["lease_id"], copy=copy,
                source="ollama", selected_model="synthetic-research-proof",
            )
            store.complete_task(task["id"], task["lease_id"], {"synthetic": True})
        return row

    def prepare(prospect, row=None):
        return store.plan_outreach_email(prospect["id"], MarketingEmailPlanCreate(
            actor="research-smoke", stage="initial",
            **({"ai_draft_id": row["id"], "ai_draft_digest": row["draft_digest"]} if row else {
                "subject": "Synthetic reviewed introduction",
                "body": "A synthetic optional creator collaboration for this disposable proof.",
            }),
        ), sender="synthetic@example.test")

    unprepared, ready_evidence = creator()
    unprepared_row = draft(unprepared)
    approved, approved_evidence = creator()
    approved_row = draft(approved)
    action = prepare(approved, approved_row)
    store.decide_task(action["task_id"], ApprovalDecision(decision="approved", actor="research-smoke"))
    queued, queued_evidence = creator()
    queued_row = draft(queued, ready=False)
    manual, manual_evidence = creator()
    manual_action = prepare(manual)
    prospects = [unprepared, approved, queued, manual]
    evidence = [ready_evidence, approved_evidence, queued_evidence, manual_evidence]
    refreshed = [{**item, "display_name": "Fresh discovery name", "audience_size": 99999,
                  "latest_content_title": "Changed bulk Minecraft sample",
                  "intelligence": {**item["intelligence"], "topics": ["Minecraft", "Survival"]}}
                 for item in evidence]
    new_channel = "UC" + uuid4().hex[:22]
    brand_new = {**research, "external_id": new_channel,
                 "profile_url": f"https://www.youtube.com/channel/{new_channel}",
                 "intelligence": {"source_channel_id": new_channel,
                                  "topics": ["Minecraft"], "contact_candidates": []}}
    before = {item["id"]: store.get_prospect(item["id"]) for item in prospects}
    with store.connect() as connection:
        draft_before = connection.execute(
            "SELECT id,input_snapshot,input_hash,subject,body,draft_digest,model_copy "
            "FROM creator_email_drafts WHERE id=ANY(%s) ORDER BY id",
            ([unprepared_row["id"], approved_row["id"], queued_row["id"]],),
        ).fetchall()
        action_before = connection.execute(
            "SELECT public_context,private_context,context_hash,status FROM external_actions WHERE id=%s",
            (action["id"],),
        ).fetchone()
    check(store.save_discovered_prospects(campaign["id"], [*refreshed, brand_new]) == {
        "new": 1, "updated": 0,
    }, "Bulk rescan changed active research or failed to insert a new creator")
    for prospect in prospects:
        after = store.get_prospect(prospect["id"])
        check(research_snapshot(after) == research_snapshot(before[prospect["id"]]),
              "Bulk rescan changed active research snapshot/last-seen time")
        check(after["intelligence"] == before[prospect["id"]]["intelligence"]
              and after["contact_email"] == before[prospect["id"]]["contact_email"],
              "Bulk rescan changed protected dossier or selected contact")
    with store.connect() as connection:
        check(connection.execute(
            "SELECT id,input_snapshot,input_hash,subject,body,draft_digest,model_copy "
            "FROM creator_email_drafts WHERE id=ANY(%s) ORDER BY id",
            ([unprepared_row["id"], approved_row["id"], queued_row["id"]],),
        ).fetchall() == draft_before, "Bulk rescan rewrote frozen copy or digest")
        check(connection.execute(
            "SELECT public_context,private_context,context_hash,status FROM external_actions WHERE id=%s",
            (action["id"],),
        ).fetchone() == action_before, "Bulk rescan changed exact approved queued action")
        check(connection.execute(
            "SELECT result_metadata FROM audit_events "
            "WHERE action='marketing.discovery_evidence_preserved' "
            "AND input_metadata->>'campaign_id'=%s ORDER BY occurred_at DESC LIMIT 1",
            (str(campaign["id"]),),
        ).fetchone()["result_metadata"]["protected_count"] == 4, "Protected audit count missing")
    check(store.get_campaign(campaign["id"])["last_discovery_summary"]["protected_count"] == 4,
          "Protected scan summary count missing")

    # Status and expiry transitions release only inactive preservation; none authorizes a send.
    with store.connect() as connection:
        for state in ("failed", "cancelled", "rejected", "dead_lettered"):
            connection.execute("UPDATE agent_tasks SET status=%s WHERE id=%s",
                               (state, unprepared_row["task_id"]))
            check(not store._discovery_evidence_protected(connection, unprepared["id"]),
                  "Terminal drafting task retained an evidence pin")
        connection.execute("UPDATE agent_tasks SET status='succeeded' WHERE id=%s",
                           (unprepared_row["task_id"],))
        for state in ("pending_approval", "queued", "executing", "ambiguous"):
            for prospect, active_action in ((manual, manual_action), (approved, action)):
                connection.execute("UPDATE external_actions SET status=%s WHERE id=%s",
                                   (state, active_action["id"]))
                check(store._discovery_evidence_protected(connection, prospect["id"]),
                      "Active manual or prepared outreach state did not preserve evidence")
        for state in ("succeeded", "failed", "rejected", "cancelled"):
            for prospect, active_action in ((manual, manual_action), (approved, action)):
                connection.execute("UPDATE external_actions SET status=%s WHERE id=%s",
                                   (state, active_action["id"]))
                check(not store._discovery_evidence_protected(connection, prospect["id"]),
                      "Finished manual or prepared action retained an evidence pin")
        connection.execute("UPDATE external_actions SET status='queued' WHERE id=%s", (action["id"],))
        connection.execute("UPDATE external_actions SET status='queued',"
                           "expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",
                           (manual_action["id"],))
        check(not store._discovery_evidence_protected(connection, manual["id"]),
              "Expired queued action retained an evidence pin")
        connection.execute("UPDATE creator_email_drafts SET expires_at=clock_timestamp()-"
                           "interval '1 second' WHERE id=%s", (unprepared_row["id"],))
    store.cancel_task(queued_row["task_id"], TaskCancellation(
        actor="research-smoke", reason="Synthetic queued draft cancellation",
    ))
    store.cancel_task(action["task_id"], TaskCancellation(
        actor="research-smoke", reason="Synthetic approved packet cancellation",
    ))
    check(store.save_discovered_prospects(campaign["id"], refreshed) == {"new": 0, "updated": 0},
          "Expiry/cancellation released durable bulk history protection")
    check(store.get_campaign(campaign["id"])["last_discovery_summary"]["protected_count"] == 4,
          "Terminal/expired draft and message history was not counted as preserved")

    # Explicit operator refresh retains the existing invalidation boundary even while pinned.
    explicit, explicit_evidence = creator()
    explicit_row = draft(explicit)
    store.save_prospect_research(
        explicit["id"], {**explicit_evidence, "latest_content_title": "Explicit changed Minecraft"},
        expected_profile_url=explicit["profile_url"], expected_campaign_id=campaign["id"],
    )
    check(store.get_draft(explicit_row["id"])["status"] == "stale",
          "Explicit refresh failed to invalidate ready draft")
    try:
        prepare(explicit, explicit_row)
    except CreatorDraftConflictError:
        pass
    else:
        raise AssertionError("Explicitly refreshed research reused old ready copy")
    explicit_send, send_evidence = creator()
    send_action = prepare(explicit_send, draft(explicit_send))
    store.decide_task(send_action["task_id"], ApprovalDecision(
        decision="approved", actor="research-smoke",
    ))
    store.save_prospect_research(
        explicit_send["id"], {**send_evidence, "latest_content_title": "Explicit post-approval change"},
        expected_profile_url=explicit_send["profile_url"], expected_campaign_id=campaign["id"],
    )
    send_task = store.transition_to_running(send_action["task_id"], 300, "research-smoke")
    try:
        store.begin_side_effect(send_task["id"], uuid4().hex * 2, send_task["lease_id"])
    except SideEffectGuardError as error:
        check("research changed" in str(error), "Wrong final explicit-refresh refusal")
    else:
        raise AssertionError("Final side-effect guard accepted explicitly changed research")
    with store.connect() as connection:
        check(not connection.execute("SELECT 1 FROM side_effect_receipts WHERE action_id=%s",
                                     (send_action["id"],)).fetchone(),
              "Explicitly stale research acquired a side-effect receipt")


def exercise_bulk_history(dsn, campaign_request, research):
    """Global history fence, including real writer/advisory-lock interleavings."""
    campaign_request = MarketingCampaignCreate(**{
        **campaign_request.model_dump(), "paid_offer_enabled": True,
        "paid_offer_details": "An optional synthetic server trial", "outreach_mode": "paid",
        "compensation_model": "revenue_share", "handoff_discord": "fixture_owner",
    })
    store = CreatorDraftStore(dsn)
    source = store.create_campaign(MarketingCampaignCreate(
        **{**campaign_request.model_dump(), "name": "Global history source"},
    ))
    target = store.create_campaign(MarketingCampaignCreate(
        **{**campaign_request.model_dump(), "name": "Global history target"},
    ))

    def packet(channel=None, email=None, **changes):
        channel = channel or "UC" + uuid4().hex[:22]
        profile = f"https://www.youtube.com/channel/{channel}"
        return {**research, "external_id": channel, "profile_url": profile,
                "latest_content_published_at": datetime.now(UTC) - timedelta(days=2),
                "intelligence": {"source_channel_id": channel, "topics": ["Minecraft"],
                                 "contact_candidates": [{
                                     "email": email, "source_url": profile,
                                     "evidence": f"Business collaboration: {email}",
                                     "observed_at": datetime.now(UTC).isoformat(),
                                 }] if email else []}, **changes}

    def creator(campaign=source, *, email=None):
        email = email or f"{uuid4().hex}@example.test"
        evidence = packet(email=email)
        row = store.create_prospect(MarketingProspectCreate(
            campaign_id=campaign["id"], platform="youtube", external_id=evidence["external_id"],
            display_name="Synthetic history creator", profile_url=evidence["profile_url"],
            audience_size=10000, contact_email=email, contact_source_url=evidence["profile_url"],
            contact_basis_note="Synthetic explicit business collaboration source",
            authorize_contact=True, requested_by="research-history-smoke",
        ))
        store.save_prospect_research(row["id"], evidence,
                                    expected_profile_url=row["profile_url"],
                                    expected_campaign_id=campaign["id"])
        return store.get_prospect(row["id"]), evidence

    def historical_attempt(person):
        snapshot = {"contact": {key: person.get(key) for key in (
            "platform", "external_id", "profile_url", "contact_email",
        )}, "research": research_snapshot(person)}
        with store.connect() as connection:
            row = connection.execute(
                "INSERT INTO creator_email_drafts(campaign_id,prospect_id,requested_by,"
                "idempotency_key,input_snapshot,input_hash,model_context,status,error_code,"
                "created_at,expires_at) VALUES (%s,%s,%s,%s,%s,%s,'{}','failed',"
                "'SYNTHETIC_MODEL_FAILURE',now()-interval '3 days',now()-interval '2 days') "
                "RETURNING *", (person["campaign_id"], person["id"], "history-smoke", uuid4(),
                                 Jsonb(snapshot), uuid4().hex * 2),
            ).fetchone()
        return row

    def absent(evidence):
        return not any(row["external_id"] == evidence["external_id"] for row in store.list_prospects(
            campaign_id=target["id"], prospect_status=None, limit=500,
        ))

    held, original = creator()
    historical = historical_attempt(held)
    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET contact_authorized_at=NULL,"
                           "contact_authorized_by=NULL WHERE id=%s", (held["id"],))
    held_before = store.get_prospect(held["id"])
    same_channel = {**original, "display_name": "Must not replace held evidence"}
    brand_new = packet()
    check(store.save_discovered_prospects(target["id"], [same_channel, brand_new]) == {
        "new": 1, "updated": 0,
    }, "Expired/failed cross-campaign draft did not prevent duplicate insertion")
    check(absent(same_channel) and store.get_prospect(held["id"]) == held_before,
          "Held original fields changed or a duplicate was inserted")
    check(store.save_discovered_prospects(source["id"], [same_channel]) == {
        "new": 0, "updated": 0,
    }, "Expired failed attempt allowed same-row refresh")
    with store.connect() as connection:
        check(connection.execute("SELECT * FROM creator_email_drafts WHERE id=%s",
                                 (historical["id"],)).fetchone() == historical,
              "Preservation altered historical failure/copy/context/deadline")

    # The old immutable contact remains a known identity even after a later edit.
    old_address = held["contact_email"]
    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET contact_email=%s,intelligence=%s "
                           "WHERE id=%s", (f"{uuid4().hex}@example.test",
                                           Jsonb({"source_channel_id": held["external_id"]}), held["id"]))
    check(store.save_discovered_prospects(target["id"], [packet(email=old_address)]) == {
        "new": 0, "updated": 0,
    }, "Frozen draft business address was lost after current-contact edit")

    # A same-channel handle row links through canonical source identity, then its
    # www/non-www profile can protect another incoming alias transitively.
    alias, _ = creator()
    handle = "https://www.youtube.com/@SyntheticHistoryAlias"
    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET external_id=%s,profile_url=%s,"
                           "contact_email=NULL,contact_authorized_at=NULL,contact_authorized_by=NULL,"
                           "intelligence=%s WHERE id=%s",
                           ("imported-history-alias", handle,
                            Jsonb({"source_channel_id": held["external_id"]}), alias["id"]))
    incoming_alias = packet(profile_url=handle.replace("www.", "") + "/")
    check(store.save_discovered_prospects(target["id"], [incoming_alias])["new"] == 0,
          "Canonical/handle/host aliases did not preserve history transitively")

    untouched = packet(display_name="Synthetic history creator")
    check(store.save_discovered_prospects(target["id"], [untouched])["new"] == 1,
          "Display-name overlap blocked a genuinely new creator")
    check(store.save_discovered_prospects(target["id"], [{
        **untouched, "latest_content_title": "Fresh untouched Minecraft sample",
    }])["updated"] == 1, "A creator without durable work could not refresh")

    # All-age, audit-bound reservations retain their selected identities. The
    # ordinary rolling preparation/research budgets are not enlarged or reset.
    reservation_campaign = store.create_campaign(MarketingCampaignCreate(
        **{**campaign_request.model_dump(), "name": "Old reservation history"},
    ))
    _, reserved_evidence = creator(reservation_campaign)
    batch_store = CreatorDraftBatchStore(dsn)
    batch = batch_store.create_batch(reservation_campaign["id"], CreatorDraftBatchCreate(
        actor="history-smoke", idempotency_key=uuid4(), limit=1,
    ))
    store.cancel_task(batch["task"]["id"], TaskCancellation(actor="history-smoke", reason="Fixture"))
    with store.connect() as connection:
        connection.execute("UPDATE agent_tasks SET created_at=now()-interval '3 days' WHERE id=%s",
                           (batch["task"]["id"],))
        connection.execute("UPDATE audit_events SET occurred_at=now()-interval '3 days' "
                           "WHERE task_id=%s", (batch["task"]["id"],))
    check(store.save_discovered_prospects(target["id"], [reserved_evidence])["new"] == 0,
          "Stopped/old issued batch reservation lost its identity preservation")
    pilot_campaign = store.create_campaign(MarketingCampaignCreate(
        **{**campaign_request.model_dump(), "name": "Old pilot reservation history"},
    ))
    pilot_person, pilot_evidence = creator(pilot_campaign)
    pilot = CreatorPilotStore(dsn).create_pilot(pilot_campaign["id"], CreatorPilotCreate(
        actor="history-smoke", idempotency_key=uuid4(), prospect_ids=[pilot_person["id"]],
    ))
    store.cancel_task(pilot["id"], TaskCancellation(actor="history-smoke", reason="Fixture"))
    check(store.save_discovered_prospects(target["id"], [pilot_evidence])["new"] == 0,
          "Issued pilot reservation lost cross-campaign preservation")

    # A durable matched/unmatched reply can carry the only observed old address.
    reply_address = f"{uuid4().hex}@example.test"
    with store.connect() as connection:
        reply = connection.execute(
            "INSERT INTO creator_reply_messages(campaign_id,gmail_message_id,gmail_thread_id,"
            "sender,subject,snippet,received_at,suggested_classification,match_reason) "
            "VALUES (%s,%s,%s,%s,'Synthetic reply','Fixture only',now(),'question','Fixture') "
            "RETURNING *", (source["id"], uuid4().hex, uuid4().hex, reply_address),
        ).fetchone()
    check(store.save_discovered_prospects(target["id"], [packet(email=reply_address)])["new"] == 0,
          "Reply-only address allowed a new alias insertion")
    with store.connect() as connection:
        check(connection.execute("SELECT * FROM creator_reply_messages WHERE id=%s",
                                 (reply["id"],)).fetchone() == reply, "Reply evidence was modified")
        connection.execute("INSERT INTO creator_contact_suppressions(email,reason) VALUES (%s,%s)",
                           ("global-history-block@example.test", "Synthetic opt-out"))
    check(store.save_discovered_prospects(target["id"], [
        packet(email="global-history-block@example.test"),
    ])["new"] == 0, "Global business suppression allowed a new duplicate research row")

    def wait_for_lock(blocker, future):
        for _ in range(100):
            if future.done():
                future.result()
                raise AssertionError("Bulk save did not wait at the real PostgreSQL guard")
            blocker.execute("SELECT pg_stat_clear_snapshot()")
            if blocker.execute("SELECT 1 FROM pg_stat_activity WHERE datname=current_database() "
                               "AND pid<>pg_backend_pid() AND wait_event_type='Lock' LIMIT 1").fetchone():
                return
            time.sleep(.05)
        raise AssertionError("No PostgreSQL lock wait was observed")

    # One real writer commits a new attempt while discovery waits at its shared
    # draft budget. No model is executed and no email approval/receipt exists.
    raced, raced_evidence = creator()
    with ThreadPoolExecutor(max_workers=1) as pool, store.connect() as blocker:
        blocker.execute("SELECT pg_advisory_xact_lock(hashtext('creator-draft-budget'))")
        future = pool.submit(store.save_discovered_prospects, target["id"], [raced_evidence])
        wait_for_lock(blocker, future)
        store._create_draft_in_connection(blocker, raced["id"], CreatorDraftCreate(
            actor="history-smoke", idempotency_key=uuid4(),
        ))
        blocker.commit()
        check(future.result(timeout=15)["new"] == 0,
              "Discovery ignored a cross-campaign draft committed during its budget wait")

    # Manual preparation has no draft-budget lock. Its existing sender lock is
    # shared with the bulk guard, and a fresh read after the wait must see it.
    conversation_campaign = store.create_campaign(MarketingCampaignCreate(
        **{**campaign_request.model_dump(), "name": "Sender wait proof without pending reply"},
    ))
    conversation, _ = creator(conversation_campaign)
    candidate = packet(email=conversation["contact_email"])
    with ThreadPoolExecutor(max_workers=1) as pool, store.connect() as blocker:
        blocker.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                        (f"creator-email:{conversation['contact_email']}",))
        future = pool.submit(store.save_discovered_prospects, target["id"], [candidate])
        wait_for_lock(blocker, future)
        writer = MarketingStore(dsn)
        writer.connect = lambda: nullcontext(blocker)
        action = writer.plan_outreach_email(conversation["id"], MarketingEmailPlanCreate(
            actor="history-smoke", stage="initial",
        ), sender="synthetic@example.test")
        blocker.commit()
        check(future.result(timeout=15)["new"] == 0,
              "Discovery ignored a conversation committed during its sender-lock wait")
    with store.connect() as connection:
        check(not connection.execute("SELECT 1 FROM side_effect_receipts WHERE action_id=%s",
                                     (action["id"],)).fetchone(), "Fixture acquired an email receipt")

    # Known alias growth during a wait is skipped, never appended out of order.
    expanding, _ = creator()
    candidate = packet(email=expanding["contact_email"])
    with ThreadPoolExecutor(max_workers=1) as pool, store.connect() as blocker:
        blocker.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                        (f"creator-email:{expanding['contact_email']}",))
        future = pool.submit(store.save_discovered_prospects, target["id"], [candidate])
        wait_for_lock(blocker, future)
        blocker.execute("UPDATE marketing_prospects SET contact_email=%s WHERE id=%s",
                        (f"{uuid4().hex}@example.test", expanding["id"]))
        blocker.commit()
        check(future.result(timeout=15)["new"] == 0,
              "Expanded known aliases were written without the complete lock union")

    # Fresh provider observations are known at save time, even when the held
    # source must not be updated. They protect another alias in the same batch.
    fresh_address = f"{uuid4().hex}@example.test"
    held_before = store.get_prospect(held["id"])
    fresh_held = packet(held["external_id"], fresh_address)
    fresh_alias = packet(email=fresh_address)
    check(store.save_discovered_prospects(target["id"], [fresh_alias, fresh_held]) == {
        "new": 0, "updated": 0,
    }, "Fresh same-batch address on a frozen channel allowed another new alias")
    check(store.get_prospect(held["id"]) == held_before,
          "Transient same-batch alias propagation rewrote the preserved source")

    # Native fetch deduplicates channels, but direct store callers retain the
    # original sequential upsert/count and profile-ownership behavior too.
    duplicate = packet()
    check(store.save_discovered_prospects(target["id"], [duplicate, duplicate]) == {
        "new": 1, "updated": 1,
    }, "Repeated fresh input was incorrectly counted as two inserted creators")
    mismatched = packet()
    check(store.save_discovered_prospects(target["id"], [
        mismatched, {**mismatched, "profile_url": "https://youtube.com/@DifferentFixture"},
    ]) == {"new": 1, "updated": 0}, "A later duplicate rebound the first profile")
    return ["Expired/failed/withdrawn global history preserves all fields and frozen copy",
            "Canonical/handle/business snapshot aliases block cross-campaign inserts",
            "Untouched new/different-name identities still insert and refresh",
            "Old stopped audit-issued batch/pilot reservations remain pinned",
            "Reply-only and globally suppressed addresses preserve evidence",
            "Real draft-budget and sender-lock waits recheck committed durable state",
            "Known alias growth after a wait is skipped without extending the lock union",
            "Fresh same-batch aliases inherit a frozen canonical channel without source writes",
            "Duplicate fresh inputs retain accurate new/update counts and profile ownership"]


def exercise(dsn):
    store = MarketingStore(dsn)
    campaign_request = MarketingCampaignCreate(
        name="Synthetic research proof", product_name="Fixture Product",
        product_url="https://example.test/product", privacy_url="https://example.test/privacy",
        product_summary="A synthetic product for evidence and authorization isolation tests.",
        target_audience="Minecraft creators", viewer_offer="Fixture benefit",
        creator_offer="Fixture pilot", paid_offer_enabled=False, sender_name="Fixture Sender",
        discovery_queries=["Minecraft SMP"], active=False, requested_by="research-smoke",
    )
    campaign = store.create_campaign(campaign_request)
    channel_id = "UC" + "a" * 22
    profile_url = f"https://www.youtube.com/channel/{channel_id}"
    research = {
        "platform": "youtube", "external_id": channel_id,
        "display_name": "Synthetic Creator", "profile_url": profile_url,
        "audience_size": 10000, "latest_content_title": "Minecraft SMP",
        "latest_content_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "latest_content_published_at": None, "discovery_query": "Minecraft SMP",
        "relevance_score": 75, "relevance_reasons": ["Fixture evidence"],
        "intelligence": {"schema_version": 1, "source_channel_id": channel_id,
                         "contact_candidates": [{
            "email": "candidate@example.test", "source_url": profile_url,
            "evidence": "Business: candidate@example.test", "status": "unreviewed",
            "observed_at": datetime.now(UTC).isoformat(),
        }]},
    }
    check(store.save_discovered_prospects(campaign["id"], [research])["new"] == 1,
          "Research prospect was not inserted")
    prospect = store.list_prospects(campaign_id=campaign["id"], prospect_status=None, limit=10)[0]
    check(prospect["intelligence"]["source_channel_id"] == channel_id
          and all(prospect["intelligence"]["contact_candidates"][0].get(key) == value
                  for key, value in research["intelligence"]["contact_candidates"][0].items()),
          "Dossier was not persisted")
    check(prospect["intelligence"]["geography"]["eligible"],
          "Unrestricted campaign unexpectedly excluded the fixture")
    check(prospect["contact_email"] is None and prospect["contact_authorized_at"] is None,
          "Discovery improperly granted contact authority")
    updated_campaign = store.update_campaign(campaign["id"], MarketingCampaignUpdate(
        **{**campaign_request.model_dump(exclude={"requested_by"}),
           "country_mode": "strict", "target_country": "PL", "actor": "research-smoke"},
    ))
    current = store.get_prospect(prospect["id"])
    check(not current["intelligence"]["geography"]["eligible"],
          "Saved unknown-country dossier bypassed current Poland-only criteria")
    try:
        store.save_discovered_prospects(
            campaign["id"], [research], expected_campaign_updated_at=campaign["updated_at"],
        )
    except MarketingOutreachError:
        pass
    else:
        raise AssertionError("Old scan persisted after campaign targeting changed")
    check(updated_campaign["last_discovery_summary"] == {}, "Campaign edit retained old scan counts")
    changed_url = "https://www.youtube.com/channel/UC" + "b" * 22
    edited = store.update_prospect(prospect["id"], MarketingProspectUpdate(
        display_name="Changed Fixture", profile_url=changed_url, actor="research-smoke",
    ))
    check(set(edited["intelligence"]) == {"geography", "gaps"}
          and not edited["intelligence"]["geography"]["eligible"]
          and edited["latest_content_url"] is None
          and edited["relevance_score"] == 0, "Identity edit retained unrelated evidence")
    check(store.save_discovered_prospects(campaign["id"], [research])["updated"] == 0,
          "Rescan rebound an edited profile to the previous identity")
    unchanged = store.get_prospect(prospect["id"])
    check(unchanged["profile_url"] == changed_url, "Rescan replaced the reviewed identity")
    store.update_prospect(prospect["id"], MarketingProspectUpdate(
        display_name="Restored Fixture", profile_url=profile_url, actor="research-smoke",
    ))
    reviewed = store.create_prospect(MarketingProspectCreate(
        campaign_id=campaign["id"], platform="youtube", external_id="reviewed-fixture",
        display_name="Reviewed Fixture", profile_url=profile_url,
        contact_email="reviewed@example.test", contact_source_url=profile_url,
        contact_basis_note="Synthetic fixture only", authorize_contact=True,
        requested_by="research-smoke",
    ))
    refreshed = store.save_prospect_research(
        reviewed["id"], research, expected_profile_url=profile_url,
        expected_campaign_id=campaign["id"],
    )
    check(refreshed["contact_email"] == "reviewed@example.test"
          and refreshed["contact_authorized_at"] == reviewed["contact_authorized_at"]
          and refreshed["external_id"] == reviewed["external_id"],
          "Research changed reviewed identity or contact authority")
    # Seed opt-out state only inside this disposable database. The outreach
    # smoke separately verifies the real message/outcome/suppression sequence.
    with store.connect() as connection:
        connection.execute(
            "UPDATE marketing_prospects SET suppressed_at = now(), status = 'suppressed', "
            "suppression_reason = 'Synthetic opt-out fixture' WHERE id = %s",
            (prospect["id"],),
        )
    check(store.save_discovered_prospects(campaign["id"], [research])["updated"] == 0,
          "Scan overwrote a suppressed creator")
    try:
        store.save_prospect_research(
            prospect["id"], research, expected_profile_url=profile_url,
            expected_campaign_id=campaign["id"],
        )
    except MarketingOutreachError:
        pass
    else:
        raise AssertionError("Suppressed creator accepted a research refresh")
    # Full campaign export has no UI page ceiling and retains a single snapshot.
    exported_campaign = store.create_campaign(MarketingCampaignCreate(
        **{**campaign_request.model_dump(), "name": "Complete export proof"},
    ))
    batch = [{**research, "external_id": f"UC{index:022}",
              "profile_url": f"https://www.youtube.com/channel/UC{index:022}",
              "display_name": f"Creator {index}",
              "intelligence": {**research["intelligence"], "source_channel_id": f"UC{index:022}",
                               "contact_candidates": []}} for index in range(601)]
    store.save_discovered_prospects(exported_campaign["id"], batch)
    check(store.count_prospects(exported_campaign["id"], None) == 601, "Wrong full count")
    pages = [store.list_prospects(campaign_id=exported_campaign["id"], prospect_status=None,
                                limit=250, offset=offset) for offset in (0, 250, 500)]
    check(len({row["id"] for page in pages for row in page}) == 601, "Paged list lost identities")
    snapshot = store.iter_campaign_prospects(exported_campaign["id"])
    first = next(snapshot)
    store.save_discovered_prospects(exported_campaign["id"], [{
        **research, "external_id": "UC" + "z" * 22,
        "profile_url": "https://www.youtube.com/channel/UC" + "z" * 22,
        "intelligence": {"source_channel_id": "UC" + "z" * 22, "contact_candidates": []},
    }])
    csv_rows = list(csv.DictReader(io.StringIO("".join(creator_csv(
        [first, *snapshot],
    )).lstrip("\ufeff"))))
    check(len(csv_rows) == 601, "Export was truncated or changed its snapshot during iteration")
    coverage = creator_coverage(store.iter_campaign_prospects(exported_campaign["id"]))
    check(coverage["total"] == 602 and coverage["authorized"] == 0,
          "Campaign coverage lost records or inferred authority")
    # Independent reservations compete through the shared PostgreSQL lock.
    tasks = [store.create_task(TaskCreate(
        title="Synthetic search budget proof", kind="marketing.creator_discovery",
        payload={"campaign_id": str(campaign["id"])}, requested_by="research-smoke",
    )) for _ in range(11)]
    with store.connect() as connection:
        for task in tasks:
            connection.execute("UPDATE agent_tasks SET status = 'running' WHERE id = %s",
                               (task["id"],))
    def reserve(task):
        return sum(store.reserve_youtube_search(task["id"]) for _ in range(10))
    with ThreadPoolExecutor(max_workers=11) as pool:
        reserved = list(pool.map(reserve, tasks))
    check(sum(reserved) == 90 and max(reserved) <= 9, "Concurrent search budget exceeded limits")
    check(not store.reserve_youtube_search(tasks[0]["id"]), "Budget was not durable")
    exercise_history(store, campaign_request, research)
    exercise_active_evidence(dsn, campaign_request, research)
    global_results = exercise_bulk_history(dsn, campaign_request, research)
    return ["JSONB dossier persisted without authority", "identity edits clear stale evidence and resist rescan rebinding",
            "refresh preserves reviewed contact and identity",
            "suppression blocks scan updates and direct refresh",
            "current Poland eligibility and stale campaign scan fence",
            "601-row snapshot export, 602-row coverage, and stable list pagination",
            "concurrent durable search reservations obey per-task and global limits",
            "source history preserves dates, survives concurrent refresh, expires, and respects identity/suppression",
            "bulk discovery preserves active queued/ready/prepared copy while discovering new creators",
            "active selector shield expires; bulk draft/conversation history remains preserved",
            "explicit research refresh still invalidates ready and approved AI copy before side effects",
            *global_results]


def main():
    # The launcher provides source text only. Credentials remain inside the
    # control-api container and are never included in command arguments/output.
    migrations = globals().get("MIGRATIONS")
    if migrations is None:
        migration_root = Path(__file__).resolve().parents[1] / "config" / "postgres" / "init"
        migrations = [path.read_text(encoding="utf-8") for path in sorted(migration_root.glob("*.sql"))]
    check(bool(migrations), "No migration sources were provided")
    source_dsn = os.environ["DATABASE_URL"]
    source_database = conninfo_to_dict(source_dsn).get("dbname")
    probe_database = f"creator_research_probe_{uuid4().hex}"
    check(re.fullmatch(r"creator_research_probe_[0-9a-f]{32}", probe_database) is not None
          and probe_database != source_database, "Unsafe disposable database name")
    maintenance_dsn = make_conninfo(source_dsn, dbname="postgres", connect_timeout=10)
    probe_dsn = make_conninfo(source_dsn, dbname=probe_database, connect_timeout=10)
    created = False
    try:
        with psycopg.connect(maintenance_dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                sql.Identifier(probe_database),
            ))
            created = True
        with psycopg.connect(probe_dsn, autocommit=True) as connection:
            for migration in migrations:
                connection.execute(migration)
        legacy_budget(probe_dsn, next(source for source in migrations
                                    if "018_creator_discovery_budget" in source))
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("HTTP forbidden")), \
                patch("smtplib.SMTP", side_effect=AssertionError("SMTP forbidden")), \
                patch("smtplib.SMTP_SSL", side_effect=AssertionError("SMTP forbidden")):
            results = exercise(probe_dsn)
        results.append("legacy delayed/retried request accounting and migration replay")
    finally:
        if created:
            # Drop only the exact random database created by this invocation.
            with psycopg.connect(maintenance_dsn, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(probe_database)))
    print(f"Creator research PostgreSQL smoke passed: {len(results)} scenario groups; disposable database removed")
    for result in results:
        print(f"  PASS {result}")


if __name__ == "__main__":
    main()
