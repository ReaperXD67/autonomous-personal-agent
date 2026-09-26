"""Prove research persistence and authority isolation in a disposable database."""

import os
import re
import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
from app.marketing_models import (
    MarketingCampaignCreate, MarketingCampaignUpdate, MarketingProspectCreate,
    MarketingProspectUpdate,
)
from app.marketing_store import MarketingOutreachError, MarketingStore
from app.creator_export import creator_coverage, creator_csv
from app.models import TaskCreate
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


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
                               "contact_candidates": [{
                                   **research["intelligence"]["contact_candidates"][0],
                                   "source_url": f"https://www.youtube.com/channel/UC{index:022}",
                               }]}} for index in range(601)]
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
    return ["JSONB dossier persisted without authority", "identity edits clear stale evidence and resist rescan rebinding",
            "refresh preserves reviewed contact and identity",
            "suppression blocks scan updates and direct refresh",
            "current Poland eligibility and stale campaign scan fence",
            "601-row snapshot export, 602-row coverage, and stable list pagination",
            "concurrent durable search reservations obey per-task and global limits",
            "source history preserves dates, survives concurrent refresh, expires, and respects identity/suppression"]


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
