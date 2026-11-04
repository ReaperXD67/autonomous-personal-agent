"""Draft-only routes and native scheduling cannot acquire email authority."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Response
from test_creator_reply_bodies import settings as gmail_settings
from test_creator_reply_bodies import sync_fixture

from app.creator_automation_gmail import execute_creator_gmail_sync
from app.creator_reply_draft_models import CreatorReplyDraftCreate
from app.creator_reply_draft_routes import create_reply_draft, list_reply_drafts
from app.models import TaskCreate
from app.policy import RiskLevel, capability_max_attempts, effective_risk
from app.settings import ConfigurationError, get_settings


def test_reply_draft_capability_has_medium_risk_one_attempt_and_no_side_effect():
    request = TaskCreate(title="Synthetic reply curation", kind="marketing.creator_reply_draft",
                         requested_by="synthetic")
    assert effective_risk(request.kind, RiskLevel.LOW) == RiskLevel.MEDIUM
    assert capability_max_attempts(request.kind) == 1


@pytest.mark.parametrize("allowed", [[], [uuid4()]])
def test_explicit_route_is_default_off_and_exact_campaign_scoped(allowed):
    campaign = uuid4()
    store = Mock()
    request = SimpleNamespace(app=SimpleNamespace(
        state=SimpleNamespace(creator_reply_drafts=store),
    ))
    with patch("app.creator_reply_draft_routes.get_settings", return_value=SimpleNamespace(
        creator_reply_draft_campaign_ids=allowed,
    )), pytest.raises(HTTPException) as failure:
        create_reply_draft(request, Response(), campaign, uuid4(), CreatorReplyDraftCreate(
            actor="synthetic", body_digest="a" * 64,
        ))
    assert failure.value.status_code == 409
    store.queue_reply_draft.assert_not_called()


def test_post_returns_summary_while_private_get_returns_saved_copy_without_generation():
    campaign, reply = uuid4(), uuid4()
    stored = {"id": uuid4(), "status": "ready", "subject": "Private subject",
              "body": "PRIVATE_SAVED_COPY", "model_copy": {"private": True}}
    store = Mock()
    store.queue_reply_draft.return_value = stored
    store.list_reply_drafts.return_value = [stored]
    request = SimpleNamespace(app=SimpleNamespace(
        state=SimpleNamespace(creator_reply_drafts=store),
    ))
    with patch("app.creator_reply_draft_routes.get_settings", return_value=SimpleNamespace(
        creator_reply_draft_campaign_ids=[campaign],
    )):
        post = create_reply_draft(request, Response(), campaign, reply, CreatorReplyDraftCreate(
            actor="synthetic", body_digest="a" * 64,
        ))
    assert not {"subject", "body", "model_copy"} & post.keys()
    store.reset_mock()
    response = Response()
    assert list_reply_drafts(request, response, campaign, reply) == [stored]
    assert response.headers["cache-control"] == "no-store"
    store.queue_reply_draft.assert_not_called()


@pytest.mark.parametrize("enabled", [False, True])
def test_native_curation_runs_only_after_complete_sync_and_explicit_opt_in(enabled):
    task, store, client = sync_fixture(metadata_count=1)
    runtime = gmail_settings()
    runtime.creator_reply_draft_campaign_ids = (
        [UUID(task["payload"]["campaign_id"])] if enabled else []
    )
    store.queue_reply_draft_curation.return_value = {"created": 2, "existing": 0, "skipped": 0}
    with patch("app.creator_automation_gmail.CreatorGmailReadClient", return_value=client):
        result = execute_creator_gmail_sync(task, store, runtime)
    assert result["reply_drafts_created"] == (2 if enabled else 0)
    if enabled:
        names = [call[0] for call in store.mock_calls]
        assert names.index("finalize_reply_sync") < names.index("queue_reply_draft_curation")
    else:
        store.queue_reply_draft_curation.assert_not_called()
    store.plan_outreach_email.assert_not_called()
    store.review_reply.assert_not_called()


@pytest.mark.parametrize("unfinished", ["pending", "cursor"])
def test_incomplete_metadata_page_never_queues_native_reply_drafts(unfinished):
    task, store, client = sync_fixture(metadata_count=21 if unfinished == "pending" else 0)
    if unfinished == "cursor":
        client.list_messages.return_value = (["known"], "nextpage")
    runtime = gmail_settings()
    runtime.creator_reply_draft_campaign_ids = [UUID(task["payload"]["campaign_id"])]
    with patch("app.creator_automation_gmail.CreatorGmailReadClient", return_value=client):
        result = execute_creator_gmail_sync(task, store, runtime)
    store.finalize_reply_sync.assert_called_once()
    store.queue_reply_draft_curation.assert_not_called()
    assert result["reply_drafts_created"] == 0
    assert result["pending"] > 0 if unfinished == "pending" else result["more_pages"]


def test_curation_scope_settings_are_bounded_and_default_off(monkeypatch):
    monkeypatch.delenv("CREATOR_REPLY_DRAFT_CAMPAIGN_IDS", raising=False)
    runtime = type(get_settings()).from_environment()
    assert runtime.creator_reply_draft_campaign_ids == ()
    campaign = uuid4()
    assert replace(runtime, creator_reply_draft_campaign_ids=(campaign,)).validate() is None
    with pytest.raises(ConfigurationError):
        replace(runtime, creator_reply_draft_campaign_ids=(campaign, campaign)).validate()
