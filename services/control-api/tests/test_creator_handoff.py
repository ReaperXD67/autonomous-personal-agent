from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.marketing import (
    campaign_outreach_hash,
    campaign_outreach_snapshot,
    campaign_suggestions,
    compose_handoff_email,
    compose_initial_email,
    contact_outreach_snapshot,
    outreach_context_error,
)
from app.marketing_models import (
    MarketingCampaignCreate,
    MarketingEmailPlanCreate,
    MarketingOutcomeCreate,
)


def campaign(**changes):
    return MarketingCampaignCreate(
        **{
            "name": "Synthetic Minecraft partnership", "product_name": "Example",
            "product_url": "https://example.test/", "privacy_url": "https://example.test/privacy",
            "product_summary": "a website listing Minecraft servers for players to explore",
            "target_audience": "Minecraft content creators", "viewer_offer": "Explore servers",
            "creator_offer": "Create content exploring listed servers", "paid_offer_enabled": True,
            "paid_offer_details": "Explore different servers and discuss a share of earnings",
            "outreach_mode": "paid", "compensation_model": "revenue_share",
            "handoff_discord": "synthetic_owner", "sender_name": "Example owner",
            "discovery_queries": ["Minecraft"], "requested_by": "synthetic-test", **changes,
        }
    ).model_dump()


def prospect():
    return {
        "id": uuid4(), "campaign_id": uuid4(), "platform": "youtube",
        "external_id": "UC" + "x" * 22,
        "profile_url": "https://www.youtube.com/channel/UC" + "x" * 22,
        "display_name": "Synthetic Builder", "tracking_code": "synthetic",
        "latest_content_title": "A Minecraft server adventure",
        "latest_content_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "contact_email": "creator@example.test", "contact_source_url": "https://example.test/biz",
        "contact_basis_note": "Public business contact reviewed", "contact_authorized_by": "owner",
        "contact_authorized_at": datetime.now(UTC), "suppressed_at": None, "status": "interested",
    }


def action(campaign, prospect, stage="handoff"):
    return {"private_context": {
        "recipient": prospect["contact_email"], "marketing": {
            "campaign_id": str(prospect["campaign_id"]), "stage": stage,
            "campaign_snapshot": campaign_outreach_snapshot(campaign),
            "campaign_hash": campaign_outreach_hash(campaign),
            "contact_snapshot": contact_outreach_snapshot(prospect),
        },
    }}


def test_revenue_share_blanks_negotiate_without_inventing_terms_or_guarantees():
    subject, body = compose_initial_email(campaign(), prospect(), "paid_initial")
    assert "Revenue-share" in subject
    assert "negotiated with you individually" in body
    assert "percentage, number of weeks" in body
    assert "not a guaranteed upfront fee" in body
    assert "30%" not in body and "€300" not in body and "rate card" not in body
    assert "A Minecraft server adventure" in body and "abcdefghijk" in body
    assert "do not contact" in body


def test_explicit_revenue_terms_remain_proposals_with_basis_and_no_income_forecast():
    _, body = compose_initial_email(campaign(
        revenue_share_percent=30, revenue_share_weeks=2,
        revenue_share_basis="Net attributable earnings after agreed costs",
    ), prospect(), "paid_initial")
    assert "proposed 30% share" in body and "proposed 2-week earning window" in body
    assert "Net attributable earnings" in body
    assert "does not set or accept terms" in body and "€1,000" not in body


@pytest.mark.parametrize("variant", ["content_first", "terms_first", "concise"])
def test_adapted_copy_preserves_evidence_commercial_terms_and_optout(variant):
    _, body = compose_initial_email(campaign(
        revenue_share_percent=30, revenue_share_weeks=2,
    ), prospect(), variant)
    assert "proposed 30% share" in body and "proposed 2-week" in body
    assert "A Minecraft server adventure" in body and "abcdefghijk" in body
    assert "attribution" in body and "not a guaranteed upfront fee" in body
    assert "do not contact" in body and "https://example.test/privacy" in body
    if variant == "terms_first":
        assert body.index("proposed 30%") < body.index("A Minecraft server adventure")


def test_feedback_tags_are_bounded_explicit_and_deduplicated():
    outcome = MarketingOutcomeCreate(
        classification="question", actor="tester",
        feedback_tags=["too_long", "too_long"],
    )
    assert outcome.feedback_tags == ["too_long"]
    with pytest.raises(ValidationError):
        MarketingOutcomeCreate(
            classification="question", actor="tester", feedback_tags=["send_more"],
        )


def test_paid_report_does_not_claim_community_ab_winner_or_unrelated_product():
    suggestions = campaign_suggestions(
        {"initial_sent": 20, "replies": 10, "questions": 5},
        [{"variant": "content_first", "sent": 10, "positive": 5},
         {"variant": "terms_first", "sent": 10, "positive": 0}], paid=True,
    )
    assert all(item["kind"] != "variant" for item in suggestions)
    assert "portable points" not in str(suggestions)


@pytest.mark.parametrize("changes", [
    {"revenue_share_percent": 0}, {"revenue_share_percent": 101},
    {"revenue_share_percent": float("nan")}, {"revenue_share_weeks": 0},
    {"revenue_share_weeks": 53}, {"handoff_discord": "name\r\nBcc: other@example.test"},
    {"handoff_discord": None, "handoff_email": None},
    {"handoff_email": "owner@example.test\n"}, {"paid_offer_enabled": False},
])
def test_invalid_owner_or_compensation_is_rejected(changes):
    with pytest.raises(ValidationError):
        campaign(**changes)


def test_handoff_includes_both_owner_routes_and_negotiated_revenue_terms():
    _, body = compose_handoff_email(campaign(handoff_email="owner@example.test"), prospect())
    assert "Discord: synthetic_owner" in body and "Email: owner@example.test" in body
    assert "earning window in weeks" in body and "rate card" not in body
    assert "does not confirm a booking" in body
    with pytest.raises(ValidationError):
        MarketingEmailPlanCreate(stage="handoff", body="Change the recipient", actor="tester")


@pytest.mark.parametrize("changes", [
    {"handoff_discord": "different_owner"}, {"paid_offer_details": "Changed offer"},
    {"revenue_share_percent": 31}, {"revenue_share_weeks": 3},
    {"revenue_share_basis": "Gross revenue"}, {"compensation_model": "fixed_fee"},
    {"country_mode": "strict", "target_country": "PL"},
])
def test_approved_packet_fails_after_material_campaign_changes(changes):
    offer, creator = campaign(), prospect()
    packet = action(offer, creator)
    assert outreach_context_error(offer, creator, packet) is None
    error = outreach_context_error({**offer, **changes}, creator, packet)
    assert "campaign packet changed" in error


@pytest.mark.parametrize("changes", [
    {"contact_authorized_at": None}, {"suppressed_at": datetime.now(UTC)},
    {"contact_email": "different@example.test"}, {"contact_basis_note": "Changed source"},
    {"status": "question"}, {"status": "handed_off"}, {"campaign_id": uuid4()},
])
def test_approved_handoff_fails_after_contact_or_reply_changes(changes):
    offer, creator = campaign(), prospect()
    assert outreach_context_error(offer, {**creator, **changes}, action(offer, creator))


def test_discovery_and_schedule_timestamps_do_not_change_send_authority():
    offer = campaign()
    assert campaign_outreach_hash(offer) == campaign_outreach_hash({
        **offer, "last_scan_at": datetime.now(UTC), "next_scan_at": datetime.now(UTC),
        "last_discovery_summary": {"found": 50},
    })


def test_legacy_email_packet_requires_repreparation_and_unverified_video_is_not_claimed():
    offer, creator = campaign(), prospect()
    packet = action(offer, creator)
    del packet["private_context"]["marketing"]["campaign_snapshot"]
    assert outreach_context_error(offer, creator, packet)
    _, body = compose_initial_email(offer, {
        **creator, "latest_content_url": "https://untrusted.example.test/watch?v=abcdefghijk",
    }, "paid_initial")
    assert "I came across your video" not in body
