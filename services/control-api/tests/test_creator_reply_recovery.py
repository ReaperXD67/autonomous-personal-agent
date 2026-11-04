"""Explicit recovery is one new bounded preparation, never an automatic model retry."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError

from app.creator_reply_draft_models import CreatorReplyDraftCreate
from app.creator_reply_draft_routes import retry_reply_draft
from app.creator_reply_draft_store import KIND, CreatorReplyDraftStore, reply_recovery_status

NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)


def source():
    draft_id = uuid4()
    return ({"id": draft_id, "attempt_number": 1, "retry_of_id": None, "status": "failed",
             "error_code": "CREATOR_REPLY_DRAFT_MODEL_UNAVAILABLE", "model_copy": None,
             "subject": None, "body": None, "draft_digest": None,
             "expires_at": NOW + timedelta(hours=1)},
            {"kind": KIND, "payload": {"reply_draft_id": str(draft_id)}, "status": "failed",
             "completed_at": NOW - timedelta(minutes=6), "cancellation_requested_at": None})


def status(row, task, failed=True, **changes):
    flags = {"scope_enabled": True, "context_matches": True, "suppressed": False, **changes}
    return reply_recovery_status(row, task, failed, NOW, **flags)


def test_only_actual_failed_local_model_source_becomes_eligible_after_cooldown():
    row, task = source()
    assert status(row, task) == (True, NOW - timedelta(minutes=1), None)
    assert status(row, task, failed=False)[2] == "not_model_failure"
    task["completed_at"] = NOW - timedelta(minutes=4)
    assert status(row, task) == (False, NOW + timedelta(minutes=1), "cooldown")


@pytest.mark.parametrize("mutation", [
    {"status": "ready"}, {"status": "queued"}, {"error_code": "CREATOR_REPLY_DRAFT_OUTPUT_INVALID"},
    {"error_code": "CREATOR_REPLY_DRAFT_CONTEXT_CHANGED"}, {"body": "PRIVATE_RETAINED_COPY"},
    {"model_copy": {}}, {"draft_digest": "a" * 64},
])
def test_non_model_failure_or_retained_copy_is_not_recoverable(mutation):
    row, task = source()
    assert status({**row, **mutation}, task)[2] == "not_model_failure"


@pytest.mark.parametrize("mutation", [
    {"status": "cancelled"}, {"status": "running"}, {"status": "succeeded"},
    {"completed_at": None}, {"cancellation_requested_at": NOW}, {"kind": "marketing.creator_draft"},
    {"payload": {"reply_draft_id": str(uuid4())}},
])
def test_active_cancelled_wrong_or_unfinished_source_task_cannot_authorize_recovery(mutation):
    row, task = source()
    assert status(row, {**task, **mutation})[2] == "not_model_failure"


@pytest.mark.parametrize(("flags", "reason"), [
    ({"scope_enabled": False}, "scope_disabled"),
    ({"context_matches": False}, "context_changed"),
    ({"suppressed": True}, "suppressed"),
    ({"child_exists": True}, "recovery_exists"),
    ({"budget_available": False}, "preparation_limit"),
])
def test_current_scope_evidence_suppression_dedup_and_budget_fences(flags, reason):
    row, task = source()
    assert status(row, task, **flags)[2] == reason


def test_expired_source_and_second_attempt_cannot_escape_the_original_lifetime_or_chain():
    row, task = source()
    assert status({**row, "expires_at": NOW}, task)[2] == "expired"
    assert status({**row, "attempt_number": 2, "retry_of_id": uuid4()}, task)[2] == "attempt_limit"


@pytest.mark.parametrize("allowed", [[], [uuid4()]])
def test_recovery_route_keeps_default_off_exact_campaign_scope(allowed):
    store = Mock()
    request = SimpleNamespace(app=SimpleNamespace(
        state=SimpleNamespace(creator_reply_drafts=store),
    ))
    with patch("app.creator_reply_draft_routes.get_settings", return_value=SimpleNamespace(
        creator_reply_draft_campaign_ids=allowed,
    )), pytest.raises(HTTPException) as refusal:
        retry_reply_draft(request, Response(), uuid4(), uuid4(), uuid4(), CreatorReplyDraftCreate(
            actor="synthetic-owner", body_digest="a" * 64,
        ))
    assert refusal.value.status_code == 409
    store.queue_reply_draft_retry.assert_not_called()


def test_bound_recovery_post_returns_only_summary_and_never_copy_or_send_action():
    campaign, reply, original = uuid4(), uuid4(), uuid4()
    store = Mock()
    store.queue_reply_draft_retry.return_value = {
        "id": uuid4(), "attempt_number": 2, "retry_of_id": original, "status": "queued",
        "subject": "Private subject", "body": "PRIVATE_BODY", "model_copy": {},
        "sending_authority": False,
    }
    request = SimpleNamespace(app=SimpleNamespace(
        state=SimpleNamespace(creator_reply_drafts=store),
    ))
    payload = CreatorReplyDraftCreate(actor="synthetic-owner", body_digest="a" * 64)
    response = Response()
    with patch("app.creator_reply_draft_routes.get_settings", return_value=SimpleNamespace(
        creator_reply_draft_campaign_ids=[campaign],
    )):
        result = retry_reply_draft(request, response, campaign, reply, original, payload)
    store.queue_reply_draft_retry.assert_called_once_with(campaign, reply, original, payload)
    assert response.headers["cache-control"] == "no-store"
    assert result["retry_of_id"] == original and result["sending_authority"] is False
    assert not {"subject", "body", "model_copy"} & result.keys()
    store.plan_outreach_email.assert_not_called()


@pytest.mark.parametrize("extra", [{"force": True}, {"attempt_number": 2}, {"expires_at": "later"}])
def test_recovery_request_cannot_supply_force_attempt_or_expiry(extra):
    with pytest.raises(ValidationError):
        CreatorReplyDraftCreate(actor="synthetic-owner", body_digest="a" * 64, **extra)


@pytest.mark.parametrize("task_status", ["failed", "cancelled", "dead_lettered"])
@pytest.mark.parametrize("suppressed", [False, True])
def test_context_projection_is_evidence_currentness_not_task_success(task_status, suppressed):
    row = {"task_id": uuid4(), "prospect_id": uuid4(), "campaign_id": uuid4(),
           "reply_id": uuid4(), "status": "queued", "attempt_number": 1,
           "input_snapshot": {"contact": {}}, "input_hash": "a" * 64,
           "expires_at": NOW + timedelta(hours=1)}
    task = {"status": task_status, "error_code": "MODEL_FAILURE", "now": NOW}
    prospect = {"contact_authorized_at": None, "suppressed_at": None,
                "contact_email": "fixture@example.invalid"}
    connection = Mock()
    records = (task, prospect, {"id": uuid4()}, {"id": uuid4()})
    connection.execute.side_effect = [Mock(fetchone=Mock(return_value=value)) for value in records]
    with (patch("app.creator_reply_draft_store.contact_is_suppressed", return_value=suppressed),
          patch("app.creator_reply_draft_store.complete_reply_body", return_value=True),
          patch("app.creator_reply_draft_store.reply_draft_snapshot", return_value={}),
          patch("app.creator_reply_draft_store.reply_model_context", return_value={}),
          patch("app.creator_reply_draft_store.canonical_hash", return_value="a" * 64)):
        result = CreatorReplyDraftStore._view_reply_draft(Mock(), connection, row)
    assert result["context_current"] is (not suppressed)
    assert result["status"] == ("cancelled" if task_status == "cancelled" else "failed")
    assert result["retry_eligible"] is False and result["sending_authority"] is False
