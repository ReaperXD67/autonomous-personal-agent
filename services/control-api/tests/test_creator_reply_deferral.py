"""Bounded reply deferral never supplies contact or sending authority."""

from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError

from app.auth import require_api_token
from app.creator_automation import pending_reply_reason
from app.creator_automation_models import CreatorAutomationActor, CreatorReplyDeferralCreate
from app.creator_automation_routes import (
    create_reply_deferral,
    list_reply_deferrals,
    revoke_reply_deferral,
    router,
)
from app.creator_reply_deferral import (
    _exact_ai_initial,
    _new_target_reason,
    deferred_pending_reply_allowed,
)
from app.marketing_models import MarketingCampaignUpdate, MarketingEmailPlanCreate
from app.marketing_store import MarketingCampaignNotFoundError, MarketingOutreachError


def request(**changes):
    return {
        "actor": "synthetic-owner",
        "idempotency_key": uuid4(),
        "body_digest": "a" * 64,
        "prospect_ids": [uuid4()],
        "reason": "Owner explicitly defers this complete commercial reply",
        "confirmation": "defer this reply for reviewed new initials",
        **changes,
    }


@pytest.mark.parametrize("changes", [
    {"prospect_ids": []},
    {"prospect_ids": [uuid4() for _ in range(4)]},
    {"expires_in_hours": 0},
    {"expires_in_hours": 25},
    {"expires_in_hours": True},
    {"expires_in_hours": "24"},
    {"body_digest": "A" * 64},
    {"body_digest": "a" * 63},
    {"body_digest": None},
    {"confirmation": "approve all emails"},
    {"confirmation": "Defer this reply for reviewed new initials"},
    {"reason": "short"},
    {"reason": "x" * 1001},
    {"actor": ""},
    {"unrestricted": True},
    {"risk_level": "low"},
    {"auto_approve": True},
    {"auto_handoff": True},
    {"stage": "handoff"},
    {"template_authority": True},
    {"sender": "different@example.test"},
])
def test_deferral_request_rejects_broad_or_malformed_authority(changes):
    with pytest.raises(ValidationError):
        CreatorReplyDeferralCreate(**request(**changes))


def test_deferral_request_requires_distinct_finite_membership_and_confirmation():
    identity = uuid4()
    with pytest.raises(ValidationError):
        CreatorReplyDeferralCreate(**request(prospect_ids=[identity, identity]))
    without_confirmation = request()
    without_confirmation.pop("confirmation")
    with pytest.raises(ValidationError):
        CreatorReplyDeferralCreate(**without_confirmation)
    saved = CreatorReplyDeferralCreate(**request(prospect_ids=[uuid4() for _ in range(3)]))
    assert len(saved.prospect_ids) == 3 and saved.expires_in_hours == 24
    assert saved.model_config["extra"] == "forbid"


def test_deferral_cannot_be_smuggled_into_campaign_or_email_scope():
    assert "reply_deferral" not in MarketingCampaignUpdate.model_fields
    assert "reply_deferral" not in MarketingEmailPlanCreate.model_fields
    assert "reply_deferral_id" not in MarketingEmailPlanCreate.model_fields
    for model in (MarketingCampaignUpdate, MarketingEmailPlanCreate):
        assert model.model_config["extra"] == "forbid"


def test_bound_routes_preserve_campaign_reply_and_owner_identity():
    store = Mock()
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(creator_automation=store)))
    campaign, reply, deferral = uuid4(), uuid4(), uuid4()
    payload = CreatorReplyDeferralCreate(**request())
    create_reply_deferral(req, campaign, reply, payload)
    store.create_reply_deferral.assert_called_once_with(campaign, reply, payload)
    response = Response()
    list_reply_deferrals(req, response, campaign, reply)
    store.list_reply_deferrals.assert_called_once_with(campaign, reply)
    assert response.headers["Cache-Control"] == "no-store"
    revoke_reply_deferral(req, campaign, reply, deferral, CreatorAutomationActor(actor="owner"))
    store.revoke_reply_deferral.assert_called_once_with(campaign, reply, deferral, "owner")
    assert not store.review_reply.called and not store.plan_outreach_email.called


def test_deferral_routes_inherit_authenticated_control_plane_dependency():
    paths = [route for route in router.routes if "/deferrals" in route.path]
    assert len(paths) == 3
    assert all(any(item.call is require_api_token for item in route.dependant.dependencies)
               for route in paths)


@pytest.mark.parametrize("error,status", [
    (MarketingCampaignNotFoundError("missing"), 404),
    (MarketingOutreachError("source changed"), 409),
])
def test_deferral_conflicts_are_not_reported_as_authorization(error, status):
    store = Mock()
    store.create_reply_deferral.side_effect = error
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(creator_automation=store)))
    with pytest.raises(HTTPException) as caught:
        create_reply_deferral(req, uuid4(), uuid4(), CreatorReplyDeferralCreate(**request()))
    assert caught.value.status_code == status


@pytest.mark.parametrize("changes", [
    {"action_type": "career.application_submit"},
    {"stage": "handoff"},
    {"stage": "question_reply"},
    {"variant": "paid_content_first"},
    {"variant": "manual_initial"},
    {"creator_automation": {}},
    {"draft_id": "not-a-draft"},
])
def test_markers_alone_cannot_create_ai_or_delegated_send_authority(changes):
    private = {"marketing": {"stage": changes.get("stage", "initial"),
                             "variant": changes.get("variant", "ai_reviewed_initial")}}
    if "creator_automation" in changes:
        private["creator_automation"] = changes["creator_automation"]
    action = {"action_type": changes.get("action_type", "communications.email_send"),
              "private_context": private,
              "public_context": {"marketing": {**private["marketing"],
                                                "draft_id": changes.get("draft_id")}}}
    connection = Mock()
    assert not _exact_ai_initial(connection, action, {}, {})
    connection.execute.assert_not_called()


def test_missing_immutable_binding_never_selects_another_available_deferral():
    connection = Mock()
    assert not deferred_pending_reply_allowed(connection, uuid4(), {"private_context": {
        "marketing": {"stage": "initial", "variant": "ai_reviewed_initial",
                      "prospect_id": str(uuid4())},
    }})
    connection.execute.assert_not_called()


def test_background_or_generic_calls_cannot_use_an_action_specific_exception():
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = {"pending": True}
    with patch("app.creator_reply_deferral.deferred_pending_reply_allowed",
               return_value=True) as guard:
        assert pending_reply_reason(connection, uuid4())
        guard.assert_not_called()
        action = {"private_context": {"marketing": {"reply_deferral_id": str(uuid4())}}}
        assert pending_reply_reason(connection, uuid4(), action) is None
        guard.assert_called_once()


def new_target():
    return {"id": uuid4(), "status": "discovered", "suppressed_at": None,
            "contact_authorized_at": "synthetic-reviewed", "contact_email": "new@example.test"}


def test_historical_candidate_address_suppression_cannot_hide_behind_a_new_contact():
    target = new_target()
    with patch("app.creator_reply_deferral._identity_keys", return_value=(
        [["email", "new@example.test"], ["email", "old@example.test"]], [target],
    )), patch("app.creator_reply_deferral.contact_is_suppressed",
              side_effect=lambda connection, email: email == "old@example.test"):
        assert "suppressed business address" in _new_target_reason(Mock(), target, [])


def test_prior_action_recipient_is_checked_after_a_prospect_contact_changed():
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = {"used": True}
    target = new_target()
    with patch("app.creator_reply_deferral._identity_keys", return_value=(
        [["email", "old@example.test"]], [target],
    )), patch("app.creator_reply_deferral.contact_is_suppressed", return_value=False):
        assert "prior or pending outreach" in _new_target_reason(connection, target, [])
    query, values = connection.execute.call_args.args
    assert "lower(a.private_context->>'recipient')=ANY" in query
    assert "old@example.test" in values[1]


def test_batch_membership_still_reserves_a_candidate_when_no_external_action_exists():
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = None
    target = new_target()
    with patch("app.creator_reply_deferral._identity_keys", return_value=([], [target])), \
            patch("app.creator_reply_deferral.contact_is_suppressed", return_value=False), \
            patch("app.creator_draft_store.CreatorDraftStore._draft_reservations",
                  return_value={"issued": (target["id"], uuid4())}):
        assert "batch reservation" in _new_target_reason(connection, target, [])
