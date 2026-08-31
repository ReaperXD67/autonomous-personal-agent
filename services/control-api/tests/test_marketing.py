from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app import marketing
from app.marketing import (
    build_promotion_kit,
    campaign_suggestions,
    choose_initial_variant,
    compose_initial_email,
    compose_paid_offer_email,
    fetch_youtube_creators,
    score_creator,
)
from app.marketing_models import MarketingCampaignCreate, MarketingProspectCreate


def campaign() -> dict[str, object]:
    return {
        "id": UUID("11111111-1111-1111-1111-111111111111"),
        "name": "KarixMC creator pilot",
        "product_name": "KarixMC",
        "product_url": "https://karixmc.pl/",
        "privacy_url": "https://karixmc.pl/privacy",
        "product_summary": (
            "a verified Minecraft reward network where active play earns portable points"
        ),
        "target_audience": "Minecraft players and server owners",
        "viewer_offer": "we can provide free pilot points for your viewers",
        "creator_offer": "we can provide free campaign points for your server",
        "paid_offer_enabled": True,
        "paid_offer_details": "we can discuss a paid video, Short, or stream segment",
        "sender_name": "Aman from KarixMC",
        "discovery_queries": ["Minecraft SMP", "Minecraft server review"],
        "relevance_language": "en",
        "region_code": None,
        "min_subscribers": 1000,
        "max_subscribers": 250000,
        "max_video_age_days": 120,
        "results_per_query": 10,
        "adaptive_mode": True,
    }


def prospect() -> dict[str, object]:
    return {
        "id": UUID("22222222-2222-2222-2222-222222222222"),
        "platform": "youtube",
        "display_name": "Block Builder",
        "tracking_code": "abc123",
        "latest_content_title": "I tested a new Minecraft SMP",
        "contact_source_url": "https://example.com/contact",
    }


def test_campaign_requires_https_and_a_described_paid_offer() -> None:
    fields = campaign()
    fields.pop("id")
    fields.pop("adaptive_mode")
    fields.update(
        {
            "schedule_hours": 24,
            "active": False,
            "requested_by": "tester",
        }
    )
    MarketingCampaignCreate.model_validate(fields)
    with pytest.raises(ValidationError, match="HTTPS"):
        MarketingCampaignCreate.model_validate({**fields, "product_url": "http://example.test"})
    with pytest.raises(ValidationError, match="paid offer"):
        MarketingCampaignCreate.model_validate({**fields, "paid_offer_details": ""})
    with pytest.raises(ValidationError, match="relevance_language"):
        MarketingCampaignCreate.model_validate({**fields, "relevance_language": "eng"})


def test_contact_authorization_requires_complete_public_provenance() -> None:
    valid = {
        "campaign_id": UUID("11111111-1111-1111-1111-111111111111"),
        "platform": "youtube",
        "display_name": "Block Builder",
        "profile_url": "https://www.youtube.com/channel/channel-id",
        "contact_email": "business@example.test",
        "contact_source_url": "https://example.test/contact",
        "contact_basis_note": "Public business contact reviewed for one relevant proposal",
        "authorize_contact": True,
        "requested_by": "tester",
    }
    MarketingProspectCreate.model_validate(valid)
    with pytest.raises(ValidationError, match="email, its public source"):
        MarketingProspectCreate.model_validate({**valid, "contact_source_url": None})


def test_initial_email_is_specific_truthful_and_contains_an_opt_out() -> None:
    subject, body = compose_initial_email(campaign(), prospect(), "viewer_value")
    assert "KarixMC" in subject
    assert "verified Minecraft reward network" in body
    assert "free pilot points" in body
    assert "There is no obligation to endorse it" in body
    assert "utm_content=abc123" in body
    assert "https://example.com/contact" in body
    assert "do not contact" in body
    assert "no one has done" not in body.casefold()


def test_paid_offer_is_explicitly_the_final_follow_up() -> None:
    _subject, body = compose_paid_offer_email(campaign(), prospect())
    assert "paid video" in body
    assert "final outreach message" in body
    assert "agreed in writing" in body


def test_promotion_kit_is_truthful_deterministic_and_attributable() -> None:
    kit = build_promotion_kit(campaign())
    assert kit == build_promotion_kit(campaign())
    assert len(kit["assets"]) == 5
    assert kit["campaign_id"] == campaign()["id"]
    assert all("verified Minecraft reward network" in item["body"] for item in kit["assets"])
    assert all("a a verified" not in item["body"] for item in kit["assets"])
    for asset in kit["assets"]:
        assert "utm_id=11111111-1111-1111-1111-111111111111" in asset["tracking_url"]
        assert "utm_campaign=karixmc-creator-pilot" in asset["tracking_url"]
        assert f"utm_content={asset['key']}" in asset["tracking_url"]
        assert asset["tracking_url"] in asset["body"]
    assert "disclose" in kit["disclosure_reminder"].casefold()


def test_creator_scoring_rewards_target_range_and_recent_activity() -> None:
    score, reasons = score_creator(
        audience_size=12000,
        content_published_at=datetime(2026, 8, 20, tzinfo=UTC),
        minimum_audience=1000,
        maximum_audience=250000,
        now=datetime(2026, 8, 28, tzinfo=UTC),
    )
    assert score == 100
    assert "audience is inside" in " ".join(reasons)
    assert "within 30 days" in " ".join(reasons)


def test_youtube_discovery_uses_public_metadata_and_never_invents_contact_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_read(path: str, parameters: dict[str, str | int]) -> dict[str, object]:
        assert parameters["key"] == "restricted-key"
        if path.endswith("/search"):
            return {
                "items": [
                    {
                        "id": {"videoId": "video-1"},
                        "snippet": {
                            "channelId": "channel-1",
                            "channelTitle": "Block Builder",
                            "title": "Minecraft server review",
                            "publishedAt": "2026-08-20T00:00:00Z",
                        },
                    }
                ]
            }
        return {
            "items": [
                {
                    "id": "channel-1",
                    "snippet": {"title": "Block Builder"},
                    "statistics": {
                        "subscriberCount": "12000",
                        "hiddenSubscriberCount": False,
                    },
                }
            ]
        }

    monkeypatch.setattr(marketing, "_read_youtube_json", fake_read)
    found = fetch_youtube_creators(
        "restricted-key",
        campaign(),
        now=datetime(2026, 8, 28, tzinfo=UTC),
    )
    assert len(found) == 1
    assert found[0]["external_id"] == "channel-1"
    assert found[0]["audience_size"] == 12000
    assert found[0]["profile_url"].startswith("https://www.youtube.com/channel/")
    assert "contact_email" not in found[0]


def test_adaptation_waits_for_evidence_then_preserves_exploration() -> None:
    prospect_id = UUID("22222222-2222-2222-2222-222222222220")
    sparse = [
        {"variant": "viewer_value", "sent": 4, "positive": 2},
        {"variant": "creator_pilot", "sent": 3, "positive": 0},
    ]
    _variant, reason = choose_initial_variant(prospect_id, sparse, adaptive_mode=True)
    assert "threshold not met" in reason

    measured = [
        {"variant": "viewer_value", "sent": 20, "positive": 8},
        {"variant": "creator_pilot", "sent": 20, "positive": 2},
    ]
    variant, reason = choose_initial_variant(prospect_id, measured, adaptive_mode=True)
    assert variant == "viewer_value"
    assert "Adaptive winner" in reason


def test_suggestions_stop_scaling_when_suppression_is_high() -> None:
    suggestions = campaign_suggestions(
        {
            "emails_sent": 20,
            "replies": 4,
            "positive_replies": 1,
            "questions": 1,
            "declined_unpaid": 2,
            "suppressed": 3,
        },
        [
            {"variant": "viewer_value", "sent": 10, "positive": 1},
            {"variant": "creator_pilot", "sent": 10, "positive": 0},
        ],
    )
    compliance = [item for item in suggestions if item["kind"] == "compliance"]
    assert compliance and compliance[0]["priority"] == "stop"
