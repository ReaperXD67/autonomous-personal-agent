import csv
import io
from datetime import UTC, datetime, timedelta

import pytest

from app.creator_export import creator_coverage, creator_csv
from app.marketing_models import MarketingCampaignCreate
from app.marketing_store import MarketingStore

NOW = datetime(2026, 9, 26, tzinfo=UTC)


def creator(index=0, **overrides):
    row = {
        "id": str(index), "display_name": "Twórca, Polska", "profile_url": "https://youtube.com/",
        "status": "discovered", "intelligence": {
            "geography": {"eligible": True, "country_code": "PL"},
            "researched_at": NOW.isoformat(), "enrichment_status": "complete",
            "contact_candidates": [{"email": "business@example.test", "status": "unreviewed",
                                    "source_url": "https://youtube.com/", "evidence": "Business"}],
        },
    }
    return {**row, **overrides}


def rows_csv(rows, **kwargs):
    return list(csv.DictReader(io.StringIO("".join(creator_csv(rows, **kwargs)).lstrip("\ufeff"))))


def test_complete_export_streams_past_ui_limit_and_keeps_missing_contacts():
    source = (creator(i, intelligence={"geography": {"eligible": True}}) for i in range(751))
    exported = rows_csv(source)
    assert len(exported) == 751
    assert exported[-1]["creator_id"] == "750"
    assert exported[0]["display_name"] == "Twórca, Polska"
    assert exported[0]["contact_status"] == "no_public_contact_found"
    assert exported[0]["outreach_authorized"] == "false"


@pytest.mark.parametrize("value", [
    "=SUM(1,1)", " +cmd", "\t@cmd", "-1+1", "\runsafe", "\ufeff=SUM(1,1)", "\x00+cmd",
])
def test_csv_neutralizes_formula_injection(value):
    row = creator(display_name=value, latest_content_title=value)
    result = rows_csv([row])[0]
    assert result["display_name"] == "'" + value
    assert result["sample_video_title"] == "'" + value


def test_export_targets_current_rules_and_retains_optout_and_evidence():
    first = creator(suppressed_at=NOW, contact_authorized_at=NOW,
                    contact_email="business@example.test")
    excluded = creator(1, intelligence={"geography": {"eligible": False}})
    result = rows_csv([first, excluded])
    assert len(result) == 1
    assert result[0]["contact_status"] == "suppressed"
    assert result[0]["outreach_authorized"] == "false"
    assert "unreviewed" in result[0]["contact_evidence_json"]
    assert "declares PL" in result[0]["country_evidence"]
    assert len(rows_csv([first, excluded], include_excluded=True)) == 2


def test_empty_intelligence_cannot_bypass_current_strict_country():
    row = {"intelligence": {}, "_campaign_targeting": {
        "country_mode": "strict", "target_country": "PL",
    }}
    projected = MarketingStore._current_targeting(row)
    assert projected["intelligence"]["geography"]["eligible"] is False


def test_coverage_counts_full_current_selection_without_conferring_authority():
    result = creator_coverage([
        creator(), creator(1, intelligence={"geography": {"eligible": True, "country_code": "PL"}}),
        creator(2, intelligence={"geography": {"eligible": False}}),
    ], now=NOW)
    assert result == {"total": 3, "eligible": 2, "excluded": 1, "country_unknown": 1,
                      "with_public_contact": 1, "without_public_contact": 1,
                      "authorized": 0, "suppressed": 0, "needs_refresh": 1,
                      "with_historical_contact": 0, "historical_contact_only": 0}


def test_pages_are_explicitly_bounded():
    field = MarketingCampaignCreate.model_fields["search_pages_per_query"]
    assert field.default == 1


def test_historical_contact_export_keeps_dates_separate_without_current_authority():
    old_date = (NOW - timedelta(days=3)).isoformat()
    history = {"email": "business@example.test", "source_url": "https://www.youtube.com/@fixture",
               "evidence": "Business: business@example.test", "observed_at": old_date,
               "last_seen_at": old_date, "status": "historical_unreviewed"}
    row = creator(intelligence={"geography": {"eligible": True, "country_code": "PL"},
                                "contact_candidates": [], "contact_history": [history]})
    result = rows_csv([row], now=NOW)[0]
    assert result["public_contact_candidates"] == ""
    assert result["historical_public_contacts"] == "business@example.test"
    assert old_date in result["historical_contact_evidence_json"]
    assert result["contact_status"] == "historical_contact_requires_recheck"
    assert result["outreach_authorized"] == "false"
    coverage = creator_coverage([row], now=NOW)
    assert coverage["with_public_contact"] == 0
    assert coverage["historical_contact_only"] == 1
    expired = rows_csv([row], now=NOW + timedelta(days=28))[0]
    assert expired["historical_public_contacts"] == ""
