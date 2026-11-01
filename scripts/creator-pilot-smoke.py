#!/usr/bin/env python3
"""Disposable PostgreSQL proof for bounded API research; no provider or send request."""

from __future__ import annotations

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from app.application_browser import canonical_hash
from app.creator_pilot import DAILY_CREATORS, KIND, campaign_snapshot
from app.creator_pilot_store import CreatorPilotCreate, CreatorPilotStore
from app.marketing_models import MarketingCampaignCreate, MarketingProspectCreate
from app.marketing_store import MarketingOutreachError
from app.models import TaskCancellation, TaskCreate
from app.store import InvalidTaskStateError
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb


def check(value, message):
    if not value:
        raise AssertionError(message)


def blocked(call, exception, fragment):
    try:
        call()
    except exception as exc:
        check(fragment in str(exc), f"Wrong refusal boundary: {exc}")
    else:
        raise AssertionError(f"Expected refusal: {fragment}")


def fixture(store, count=1, authorize=False):
    campaign = store.create_campaign(MarketingCampaignCreate(
        name="Synthetic pilot research", product_name="FixtureCraft",
        product_url="https://example.test/", privacy_url="https://example.test/privacy",
        product_summary="A synthetic Minecraft server directory.",
        target_audience="Minecraft players", viewer_offer="Explore servers",
        creator_offer="An optional server exploration", sender_name="Synthetic",
        paid_offer_enabled=False,
        discovery_queries=["Minecraft"], requested_by="creator-pilot-smoke",
    ))
    prospects = []
    for index in range(count):
        channel = "UC" + uuid4().hex[:22]
        prospect = store.create_prospect(MarketingProspectCreate(
            campaign_id=campaign["id"], platform="youtube", external_id=channel,
            profile_url=f"https://www.youtube.com/channel/{channel}",
            display_name=f"Synthetic Creator {index}", audience_size=10000,
            contact_email=f"{uuid4().hex}@example.test" if authorize else None,
            contact_source_url=f"https://www.youtube.com/channel/{channel}" if authorize else None,
            contact_basis_note="Synthetic public business fixture only" if authorize else None,
            authorize_contact=authorize, requested_by="creator-pilot-smoke",
        ))
        with store.connect() as connection:
            prospect = connection.execute(
                "UPDATE marketing_prospects SET intelligence=%s WHERE id=%s RETURNING *",
                (Jsonb({"topics": ["Minecraft", "Servers"]}), prospect["id"]),
            ).fetchone()
        prospects.append(prospect)
    return campaign, prospects


def create(store, campaign, limit=1):
    return store.create_pilot(campaign["id"], CreatorPilotCreate(
        actor="creator-pilot-smoke", idempotency_key=uuid4(), limit=limit,
    ))


def claim(store, task):
    owned = store.transition_to_running(task["id"], 300, "creator-pilot-smoke")
    check(owned is not None, "Pilot task could not be claimed")
    return owned


def cancel(store, task):
    store.cancel_task(task["id"], TaskCancellation(
        actor="creator-pilot-smoke", reason="Synthetic validation cleanup",
    ))


def exercise(dsn):
    store = CreatorPilotStore(dsn)
    groups = []
    campaign, prospects = fixture(store, 2)
    request = CreatorPilotCreate(actor="creator-pilot-smoke", idempotency_key=uuid4(), limit=2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        copies = list(executor.map(lambda _: store.create_pilot(campaign["id"], request), range(2)))
    task = copies[0]
    check(copies[0]["id"] == copies[1]["id"], "Concurrent retry created duplicate task")
    check(task["status"] == "queued" and task["risk_level"] == "low", "Wrong task policy")
    check(len(task["payload"]["prospect_ids"]) == 2, "Wrong bounded candidate reservation")
    check(store.latest_pilot(campaign["id"])["id"] == task["id"], "Latest pilot missing")
    with store.connect() as connection:
        check(connection.execute("SELECT 1 FROM task_outbox WHERE task_id=%s",
                                 (task["id"],)).fetchone(), "Missing durable task outbox")
        check(connection.execute("SELECT count(*) AS n FROM audit_events WHERE task_id=%s "
                                 "AND action='creator.pilot.created'",
                                 (task["id"],)).fetchone()["n"] == 1, "Duplicate reservation audit")
    blocked(lambda: create(store, campaign), MarketingOutreachError, "active pilot")
    blocked(lambda: store.create_pilot(campaign["id"], request.model_copy(update={"limit": 1})),
            MarketingOutreachError, "Idempotency")
    groups.append("Concurrent idempotency creates one policy task, reservation audit and outbox")

    owned = claim(store, task)
    issued, _, _ = store.pilot_context(owned["id"], owned["lease_id"], prospects[0]["id"])
    check(issued["id"] == owned["id"], "Owned reservation did not resolve")
    forged = store.create_task(TaskCreate(
        title="Synthetic forged pilot", kind=KIND, payload=owned["payload"],
        requested_by="creator-pilot-smoke",
    ))
    forged = claim(store, forged)
    blocked(lambda: store.pilot_context(forged["id"], forged["lease_id"]),
            InvalidTaskStateError, "server-issued")
    cancel(store, owned)
    blocked(lambda: store.pilot_context(owned["id"], owned["lease_id"]),
            InvalidTaskStateError, "valid execution lease")
    groups.append("Generic caller tasks and cancelled work cannot reuse a research reservation")

    changed_campaign, _changed_prospects = fixture(store)
    changed = claim(store, create(store, changed_campaign))
    with store.connect() as connection:
        connection.execute("UPDATE marketing_campaigns SET max_video_age_days=30 WHERE id=%s",
                           (changed_campaign["id"],))
    blocked(lambda: store.pilot_context(changed["id"], changed["lease_id"]),
            InvalidTaskStateError, "targeting changed")
    identity_campaign, identity_prospects = fixture(store)
    identity = claim(store, create(store, identity_campaign))
    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET profile_url=%s WHERE id=%s",
                           ("https://www.youtube.com/channel/UC" + "z" * 22,
                            identity_prospects[0]["id"]))
    blocked(lambda: store.pilot_context(identity["id"], identity["lease_id"],
                                       identity_prospects[0]["id"]),
            InvalidTaskStateError, "identity or outreach")
    groups.append("Frozen campaign targeting and creator identity are rechecked during execution")

    save_campaign, saved_prospects = fixture(store, 2, authorize=True)
    saved_task = claim(store, create(store, save_campaign, 2))
    original = saved_prospects[0]
    research = {
        "audience_size": 11000, "latest_content_title": "Minecraft server exploration",
        "latest_content_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "latest_content_published_at": None, "relevance_score": 80,
        "relevance_reasons": ["Synthetic server topic"],
        "intelligence": {"topics": ["Minecraft", "Servers"], "contact_candidates": []},
    }
    _, refreshed = store.save_pilot_research(
        saved_task["id"], saved_task["lease_id"], original["id"], research,
    )
    authority_fields = (
        "contact_email", "contact_source_url", "contact_basis_note",
        "contact_authorized_at", "contact_authorized_by",
    )
    check(all(refreshed[key] == original[key] for key in authority_fields),
          "Research changed contact authorization")
    check(refreshed["audience_size"] == 11000, "Fresh public evidence was not persisted")
    unreserved = prospects[0]["id"]
    blocked(lambda: store.save_pilot_research(
        saved_task["id"], saved_task["lease_id"], unreserved, research,
    ), InvalidTaskStateError, "not reserved")
    groups.append("Research saves evidence without changing reviewed contact or send authority")

    expiry_campaign, expiry_prospects = fixture(store)
    expiry_task = claim(store, create(store, expiry_campaign))
    with store.connect() as connection:
        connection.execute("UPDATE agent_tasks SET lease_expires_at=clock_timestamp()+"
                           "interval '0.5 seconds' WHERE id=%s", (expiry_task["id"],))
    with ThreadPoolExecutor(max_workers=1) as executor:
        with store.connect() as blocker:
            blocker.execute("SELECT id FROM marketing_prospects WHERE id=%s FOR UPDATE",
                            (expiry_prospects[0]["id"],))
            future = executor.submit(store.save_pilot_research,
                                     expiry_task["id"], expiry_task["lease_id"],
                                     expiry_prospects[0]["id"], research)
            time.sleep(0.8)
            blocker.commit()
        blocked(lambda: future.result(timeout=10), InvalidTaskStateError, "valid execution lease")
    with store.connect() as connection:
        row = connection.execute("SELECT audience_size FROM marketing_prospects WHERE id=%s",
                                 (expiry_prospects[0]["id"],)).fetchone()
        check(row["audience_size"] == 10000, "Expired worker changed evidence")
    groups.append("Lease expiry while waiting for a creator row rolls back evidence writes")

    race_campaign, _ = fixture(store, 2)
    def competing_request(_):
        try:
            return create(store, race_campaign, 2)
        except MarketingOutreachError as exc:
            check("active pilot" in str(exc), "Unexpected concurrent failure")
            return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        raced = list(executor.map(competing_request, range(2)))
    check(sum(item is not None for item in raced) == 1, "Concurrent batches duplicated research")
    groups.append("Different simultaneous requests cannot start overlapping campaign batches")

    rotation_campaign, rotation_prospects = fixture(store, 3)
    preferred_ids = [row["id"] for row in rotation_prospects[:2]]
    with store.connect() as connection:
        connection.execute(
            "UPDATE marketing_prospects SET relevance_score=100,"
            "intelligence=intelligence || %s WHERE id=ANY(%s)",
            (Jsonb({"contact_candidates": [{"email": "fixture@example.test"}]}), preferred_ids),
        )
    first_batch = create(store, rotation_campaign, 2)
    check(set(first_batch["payload"]["prospect_ids"]) == set(map(str, preferred_ids)),
          "Initial research did not preserve contact/relevance priority")
    cancel(store, first_batch)
    unseen_batch = create(store, rotation_campaign)
    check(unseen_batch["payload"]["prospect_ids"] == [str(rotation_prospects[2]["id"])],
          "A cancelled reservation starved a never-attempted creator")
    failed = claim(store, unseen_batch)
    store.fail_task(failed["id"], failed["lease_id"], "SYNTHETIC_PROVIDER", "Fixture only")
    oldest_batch = create(store, rotation_campaign)
    oldest_id = min(map(str, preferred_ids))
    check(oldest_batch["payload"]["prospect_ids"] == [oldest_id],
          "Repeat research did not prefer the oldest server-issued reservation")
    cancel(store, oldest_batch)
    next_oldest = create(store, rotation_campaign)
    check(next_oldest["payload"]["prospect_ids"] == [
        next(str(identity) for identity in preferred_ids if str(identity) != oldest_id),
    ], "A repeated creator starved the other oldest reservation")
    cancel(store, next_oldest)
    groups.append("Sequential batches rotate unseen then oldest attempts after cancellation/failure")

    for change in ("audit_hash", "campaign", "profile", "expired"):
        history_campaign, history_prospects = fixture(store, 2)
        favored = history_prospects[0]
        with store.connect() as connection:
            connection.execute("UPDATE marketing_prospects SET relevance_score=100 WHERE id=%s",
                               (favored["id"],))
        recorded = create(store, history_campaign)
        check(recorded["payload"]["prospect_ids"] == [str(favored["id"])],
              "History fixture did not reserve the preferred creator")
        cancel(store, recorded)
        with store.connect() as connection:
            if change == "audit_hash":
                connection.execute(
                    "UPDATE audit_events SET input_metadata=jsonb_set(input_metadata,"
                    "'{payload_hash}',%s) WHERE task_id=%s AND action='creator.pilot.created'",
                    (Jsonb("0" * 64), recorded["id"]),
                )
            elif change == "campaign":
                connection.execute("UPDATE marketing_campaigns SET max_video_age_days=30 "
                                   "WHERE id=%s", (history_campaign["id"],))
            elif change == "profile":
                connection.execute("UPDATE marketing_prospects SET profile_url=%s WHERE id=%s",
                                   ("https://www.youtube.com/channel/UC" + "x" * 22,
                                    favored["id"]))
            else:
                connection.execute("UPDATE audit_events SET occurred_at=now()-interval '25 hours' "
                                   "WHERE task_id=%s AND action='creator.pilot.created'",
                                   (recorded["id"],))
        following = create(store, history_campaign)
        check(following["payload"]["prospect_ids"] == [str(favored["id"])],
              f"Invalid {change} history changed current creator priority")
        cancel(store, following)
    groups.append("Wrong audit hashes and changed campaign/profile or expired history cannot rank")

    generic_campaign, generic_prospects = fixture(store, 2)
    favored = generic_prospects[0]
    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET relevance_score=100 WHERE id=%s",
                           (favored["id"],))
    generic_payload = {
        "campaign_id": str(generic_campaign["id"]), "requested_limit": 1,
        "reservation_id": str(uuid4()),
        "campaign_hash": canonical_hash(campaign_snapshot(generic_campaign)),
        "prospect_ids": [str(favored["id"])],
        "profile_urls": {str(favored["id"]): favored["profile_url"]},
    }
    generic = store.create_task(TaskCreate(
        title="Synthetic unissued research history", kind=KIND,
        payload=generic_payload, requested_by="creator-pilot-smoke",
    ))
    cancel(store, generic)
    legitimate = create(store, generic_campaign)
    check(legitimate["payload"]["prospect_ids"] == [str(favored["id"])],
          "A generic task without a server-issued reservation influenced rank")
    cancel(store, legitimate)
    groups.append("Generic caller payloads without issued audit evidence do not consume fairness")

    large_campaign, large_prospects = fixture(store, 2)
    favored, beyond_prefix = large_prospects
    with store.connect() as connection:
        connection.execute("UPDATE marketing_prospects SET relevance_score=100 WHERE id=%s",
                           (favored["id"],))
        connection.execute(
            "INSERT INTO marketing_prospects "
            "(campaign_id,platform,external_id,display_name,profile_url,relevance_score,intelligence) "
            "SELECT %s,'youtube','UC'||substr(md5(%s||n::text),1,22),"
            "'Synthetic unrelated '||n::text,"
            "'https://www.youtube.com/channel/UC'||substr(md5(%s||n::text),1,22),100,%s "
            "FROM generate_series(1,499) AS n",
            (large_campaign["id"], str(large_campaign["id"]), str(large_campaign["id"]),
             Jsonb({"topics": ["Travel"]})),
        )
        check(connection.execute("SELECT count(*) AS n FROM marketing_prospects WHERE "
                                 "campaign_id=%s", (large_campaign["id"],)).fetchone()["n"] == 501,
              "Large selection fixture did not exceed the bounded candidate prefix")
    first_large = create(store, large_campaign)
    check(first_large["payload"]["prospect_ids"] == [str(favored["id"])],
          "Large fixture did not initially preserve relevance")
    cancel(store, first_large)
    next_large = create(store, large_campaign)
    check(next_large["payload"]["prospect_ids"] == [str(beyond_prefix["id"])],
          "Bounded selection starved the eligible creator beyond the old 500-row prefix")
    cancel(store, next_large)
    groups.append("A 501-creator pool advances past the former high-relevance candidate prefix")

    budget_campaign, _ = fixture(store, 10)
    with store.connect() as connection:
        used = connection.execute(
            "SELECT sum((input_metadata->>'batch_size')::int) AS n FROM audit_events "
            "WHERE action='creator.pilot.created' AND occurred_at>now()-interval '24 hours'",
        ).fetchone()["n"]
    remaining = DAILY_CREATORS - used
    while remaining:
        reserved = min(10, remaining)
        budget_task = create(store, budget_campaign, reserved)
        cancel(store, budget_task)
        remaining -= reserved
    blocked(lambda: create(store, budget_campaign), MarketingOutreachError, "thirty creator")
    groups.append("Cancelled and failed work retain the thirty-creator rolling reservation budget")

    with store.connect() as connection:
        check(connection.execute("SELECT count(*) AS n FROM marketing_outreach_messages")
              .fetchone()["n"] == 0, "Research created an outreach packet")
        check(connection.execute("SELECT count(*) AS n FROM external_actions")
              .fetchone()["n"] == 0, "Research created a side-effect action")
    return groups


def main():
    migrations = globals().get("MIGRATIONS")
    if migrations is None:
        folder = Path(__file__).resolve().parents[1] / "config" / "postgres" / "init"
        migrations = [path.read_text(encoding="utf-8") for path in sorted(folder.glob("*.sql"))]
    source = os.environ["DATABASE_URL"]
    name = "creator_pilot_probe_" + uuid4().hex
    check(re.fullmatch(r"creator_pilot_probe_[0-9a-f]{32}", name)
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
        print(f"Creator pilot PostgreSQL proof passed: {len(groups)} scenario groups")
        for group in groups:
            print(f"  PASS {group}")
    finally:
        if created:
            with psycopg.connect(maintenance, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            print("Disposable pilot database removed; no HTTP, SMTP or model request")


if __name__ == "__main__":
    main()
