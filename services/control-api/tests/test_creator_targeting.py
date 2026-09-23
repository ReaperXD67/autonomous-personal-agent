from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app import marketing
from app.creator_intelligence import assess_creator_geography, build_creator_intelligence
from app.marketing_models import MarketingCampaignCreate
from app.marketing_store import MarketingOutreachError, MarketingStore

NOW = datetime(2026, 9, 23, tzinfo=UTC)
CAMPAIGN = {
    "name": "Poland creator pilot", "product_name": "KarixMC",
    "product_url": "https://karixmc.pl/", "privacy_url": "https://karixmc.pl/privacy",
    "product_summary": "A Minecraft community reward network",
    "target_audience": "Minecraft creators", "viewer_offer": "An optional product trial",
    "creator_offer": "An optional product trial", "paid_offer_enabled": False,
    "sender_name": "Aman", "discovery_queries": ["Minecraft Polska"],
    "relevance_language": "pl", "region_code": "PL", "results_per_query": 25,
    "min_subscribers": 1000, "max_subscribers": 250000, "max_video_age_days": 120,
    "country_mode": "strict", "target_country": "PL", "requested_by": "tester",
}


def channel_id(index):
    return f"UC{index:022}"


def source(index):
    return f"https://www.youtube.com/channel/{channel_id(index)}"


def provider(monkeypatch, countries, *, audio=None, metadata=None, titles=None):
    def read(path, parameters):
        if path.endswith("search"):
            assert parameters["regionCode"] == "PL"
            assert parameters["relevanceLanguage"] == "pl"
            return {"items": [{
                "id": {"videoId": f"{index:011}"},
                "snippet": {
                    "channelId": channel_id(index), "channelTitle": "Polski Twórca",
                    "title": "Polska Minecraft serwer SMP", "publishedAt": NOW.isoformat(),
                },
            } for index in range(len(countries))]}
        if path.endswith("channels"):
            return {"items": [{
                "id": channel_id(index),
                "snippet": {"title": "Polski Twórca", "country": country},
                "statistics": {"subscriberCount": "25000"},
            } for index, country in enumerate(countries)]}
        return {"items": [{
            "id": f"{index:011}",
            "snippet": {
                "channelId": channel_id(index), "title": titles[index] if titles else
                "Minecraft server SMP", "publishedAt": NOW.isoformat(),
                "defaultAudioLanguage": audio[index] if audio else None,
                "defaultLanguage": metadata[index] if metadata else None,
            },
        } for index in range(len(countries))]}

    monkeypatch.setattr(marketing, "_read_youtube_json", read)


def test_country_target_is_separate_from_search_region_and_requires_explicit_mode():
    campaign = MarketingCampaignCreate(**CAMPAIGN)
    assert campaign.country_mode == "strict" and campaign.target_country == "PL"
    legacy = {key: value for key, value in CAMPAIGN.items()
              if key not in {"country_mode", "target_country"}}
    parsed = MarketingCampaignCreate(**legacy)
    assert parsed.region_code == "PL" and parsed.country_mode == "any"
    assert parsed.target_country is None
    for update in (
        {"target_country": None}, {"country_mode": "invented"}, {"target_country": "Poland"},
        {"language_mode": "strict"}, {"target_language": "pl; inject"},
    ):
        with pytest.raises(ValidationError):
            MarketingCampaignCreate(**{**CAMPAIGN, **update})
    normalized = MarketingCampaignCreate(**{
        **CAMPAIGN, "target_country": " pl ", "target_language": " pl-PL ",
        "language_mode": "prefer",
    })
    assert normalized.target_country == "PL" and normalized.target_language == "pl-pl"


def test_strict_poland_excludes_other_unknown_despite_polish_names_and_search(monkeypatch):
    provider(monkeypatch, ["PL", "DE", None, "Poland"], audio=["pl"] * 4)
    summary = {}
    found = marketing.fetch_youtube_creators("key", CAMPAIGN, now=NOW, selection_stats=summary)
    assert len(found) == 1 and found[0]["external_id"] == channel_id(0)
    geography = found[0]["intelligence"]["geography"]
    assert geography["country_code"] == "PL" and geography["country_match"] == "match"
    assert geography["country_source_url"] == source(0)
    assert "Channel declares Poland" in geography["selection_reason"]
    assert summary["reviewed"] == 4 and summary["selected"] == 1 and summary["excluded"] == 3
    assert summary["excluded_country_unknown"] == 2
    assert summary["excluded_country_mismatch"] == 1
    assert "nationality" in " ".join(found[0]["intelligence"]["gaps"])


def test_country_preference_keeps_all_and_prioritizes_declared_match(monkeypatch):
    provider(monkeypatch, ["DE", None, "PL"], titles=[
        "Minecraft server SMP", "Minecraft server SMP", "Minecraft survival",
    ])
    summary = {}
    found = marketing.fetch_youtube_creators(
        "key", {**CAMPAIGN, "country_mode": "prefer"}, now=NOW, selection_stats=summary,
    )
    assert len(found) == 3 and found[0]["external_id"] == channel_id(2)
    assert found[0]["relevance_score"] < found[1]["relevance_score"]
    assert summary["excluded"] == 0


def test_strict_language_uses_actual_audio_over_text_and_handles_regional_tags(monkeypatch):
    provider(monkeypatch, ["PL"] * 4,
             audio=["pl-PL", "en", None, None], metadata=["en", "pl", "pl", None])
    summary = {}
    found = marketing.fetch_youtube_creators("key", {
        **CAMPAIGN, "language_mode": "strict", "target_language": "pl",
    }, now=NOW, selection_stats=summary)
    assert {item["external_id"] for item in found} == {channel_id(0), channel_id(2)}
    geography = found[0]["intelligence"]["geography"]
    assert geography["language_code"] == "pl-pl" and geography["language_source"] == "video_audio"
    assert geography["language_source_url"] == "https://www.youtube.com/watch?v=00000000000"
    assert summary["excluded_language_unknown"] == 1
    assert summary["excluded_language_mismatch"] == 1
    text_record = next(item for item in found if item["external_id"] == channel_id(2))
    assert text_record["intelligence"]["geography"]["language_source"] == "video_metadata"
    assert "does not establish spoken language" in " ".join(text_record["intelligence"]["gaps"])


def test_language_fallback_is_labeled_channel_text_not_audio():
    dossier = build_creator_intelligence({
        **CAMPAIGN, "language_mode": "strict", "target_language": "pl",
    }, {
        "profile_url": source(0), "channel_country": "PL", "channel_language": "pl",
    }, now=NOW)
    geography = dossier["geography"]
    assert geography["eligible"]
    assert geography["language_source"] == "channel_metadata"
    assert geography["language_source_url"] == source(0)
    regional = assess_creator_geography({
        "language_mode": "strict", "target_language": "pl-pl",
    }, {"language_code": "pl", "language_source": "channel_metadata"})
    assert regional["language_match"] == "unknown" and not regional["eligible"]


def test_strict_country_fails_closed_if_optional_channel_enrichment_fails(monkeypatch):
    def read(path, parameters):
        if path.endswith("search"):
            return {"items": [{"id": {"videoId": "00000000000"}, "snippet": {
                "channelId": channel_id(0), "channelTitle": "Polska Minecraft",
            }}]}
        raise RuntimeError("Optional enrichment unavailable")

    monkeypatch.setattr(marketing, "_read_youtube_json", read)
    summary = {}
    assert marketing.fetch_youtube_creators("key", CAMPAIGN, selection_stats=summary) == []
    assert summary["reviewed"] == 1 and summary["excluded_country_unknown"] == 1


def test_direct_refresh_retains_nonmatching_record_as_outside_selection(monkeypatch):
    monkeypatch.setattr(marketing, "_read_youtube_json", lambda *args: {"items": [{
        "id": channel_id(0), "snippet": {"country": "DE", "defaultLanguage": "pl"},
    }]})
    result = marketing.fetch_youtube_prospect("key", CAMPAIGN, {
        "platform": "youtube", "profile_url": source(0), "display_name": "Creator",
    }, now=NOW)
    assert result["external_id"] == channel_id(0)
    assert result["intelligence"]["geography"]["country_match"] == "mismatch"
    assert not result["intelligence"]["geography"]["eligible"]


def test_current_selection_recomputes_after_campaign_edit_without_rewriting_source():
    old_geography = assess_creator_geography({"country_mode": "any"}, {
        "country_code": "DE", "country_source_url": source(0),
    })
    result = MarketingStore._current_targeting({
        "intelligence": {"geography": old_geography, "researched_at": NOW.isoformat()},
        "_campaign_targeting": {"country_mode": "strict", "target_country": "PL"},
    })
    assert "_campaign_targeting" not in result
    assert result["intelligence"]["geography"]["country_code"] == "DE"
    assert not result["intelligence"]["geography"]["eligible"]
    assert old_geography["eligible"]
    assert result["intelligence"]["researched_at"] == NOW.isoformat()


def test_scan_persistence_fences_campaign_changed_during_network_research():
    class Connection:
        def __init__(self):
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, parameters):
            assert "FOR UPDATE" in query
            self.calls += 1
            return self

        def fetchone(self):
            return {"updated_at": NOW}

    connection = Connection()

    class Store(MarketingStore):
        def __init__(self):
            pass

        def connect(self):
            return connection

    with pytest.raises(MarketingOutreachError, match="Campaign changed"):
        Store().save_discovered_prospects(
            "campaign", [], expected_campaign_updated_at=NOW - timedelta(seconds=1),
        )
    assert connection.calls == 1
