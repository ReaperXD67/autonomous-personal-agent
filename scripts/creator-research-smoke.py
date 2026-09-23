"""Prove research persistence and authority isolation in a disposable database."""

import os
import re
from pathlib import Path
from uuid import uuid4

import psycopg
from app.marketing_models import (
    MarketingCampaignCreate, MarketingCampaignUpdate, MarketingProspectCreate,
    MarketingProspectUpdate,
)
from app.marketing_store import MarketingOutreachError, MarketingStore
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


def check(condition, message):
    if not condition:
        raise AssertionError(message)


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
        "intelligence": {"schema_version": 1, "contact_candidates": [{
            "email": "candidate@example.test", "source_url": profile_url,
            "evidence": "Business: candidate@example.test", "status": "unreviewed",
        }]},
    }
    check(store.save_discovered_prospects(campaign["id"], [research])["new"] == 1,
          "Research prospect was not inserted")
    prospect = store.list_prospects(campaign_id=campaign["id"], prospect_status=None, limit=10)[0]
    check(all(prospect["intelligence"].get(key) == value
              for key, value in research["intelligence"].items()), "Dossier was not persisted")
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
    check(not edited["intelligence"] and edited["latest_content_url"] is None
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
    return ["JSONB dossier persisted without authority", "identity edits clear stale evidence and resist rescan rebinding",
            "refresh preserves reviewed contact and identity",
            "suppression blocks scan updates and direct refresh",
            "current Poland eligibility and stale campaign scan fence"]


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
        results = exercise(probe_dsn)
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
