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
from app.creator_pilot import DAILY_CREATORS, KIND
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

    changed_campaign, changed_prospects = fixture(store)
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

    budget_campaign, _ = fixture(store, 10)
    with store.connect() as connection:
        used = connection.execute(
            "SELECT sum((input_metadata->>'batch_size')::int) AS n FROM audit_events "
            "WHERE action='creator.pilot.created'",
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
