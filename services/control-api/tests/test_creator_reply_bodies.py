"""Creator-only body capture remains inside the original bounded sync/review flow."""

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.career_tracking import GmailReadClient, GmailResourceGoneError, GmailSyncError
from app.creator_automation_gmail import CreatorGmailReadClient, execute_creator_gmail_sync
from app.creator_automation_models import CreatorAutomationActor, CreatorReplyReview
from app.creator_automation_routes import overview, read_reply
from app.creator_automation_store import (
    BODY_VERSION,
    CreatorAutomationStore,
    authored_body_view,
    complete_reply_body,
    reply_body_digest,
)
from app.marketing_store import MarketingOutreachError

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
PRIVATE_BODY = "Yes, let's discuss this.\nProszę zachować polskie znaki: ąęł."


def settings(campaign_id=None):
    synthetic = "synthetic"
    return SimpleNamespace(
        creator_gmail_enabled=True, creator_gmail_mailbox="operator@example.test",
        gmail_creator_label="Hermes/Creators", gmail_career_label="Hermes/Careers",
        gmail_client_id=synthetic, gmail_client_secret=synthetic, gmail_refresh_token=synthetic,
        creator_gmail_full_reply_campaign_ids=[UUID(str(campaign_id))] if campaign_id else [],
        mail_transport="disabled",
    )


def raw_message(message_id="known", **changes):
    value = {
        "id": message_id, "threadId": "thread", "labelIds": ["Label_Creators"],
        "snippet": "A bounded provider preview", "internalDate": str(int(NOW.timestamp() * 1000)),
        "payload": {"mimeType": "text/plain", "headers": [
            {"name": "From", "value": "Creator <creator@example.test>"},
            {"name": "Subject", "value": "Re: Synthetic invitation"},
        ], "body": {"size": len(PRIVATE_BODY.encode()),
                    "data": base64.urlsafe_b64encode(PRIVATE_BODY.encode()).decode().rstrip("=")}},
    }
    value.update(changes)
    return value


def claim(message_id="known"):
    return {
        "id": uuid4(), "gmail_message_id": message_id, "gmail_thread_id": "thread",
        "sender": "creator@example.test", "subject": "Re: Synthetic invitation",
        "received_at": NOW, "body_attempt_count": 1,
    }


def sync_fixture(metadata_count=0):
    task = {"id": uuid4(), "lease_id": uuid4(), "payload": {"campaign_id": str(uuid4())}}
    store = Mock()
    store.gmail_context.return_value = {"campaign_id": task["payload"]["campaign_id"],
                                        "mailbox_key": "f" * 64, "label_name": "Hermes/Creators",
                                        "revision": 1, "pending_message_ids": [],
                                        "page_token": None}
    store.known_reply_ids.return_value = {"known"}
    store.save_gmail.return_value = {"inserted": metadata_count, "suppressed": 0,
                                     "ignored_foreign": 0}
    candidates = [{"id": uuid4()} for _ in range(4)]
    store.body_capture_candidates.return_value = candidates
    store.claim_reply_body.side_effect = lambda *args: claim()
    store.save_reply_body.return_value = {"body_status": "complete"}
    client = Mock()
    client.mailbox.return_value = "operator@example.test"
    client.label_id.return_value = "Label_Creators"
    client.list_messages.return_value = (
        ["known"] + [f"new{i}" for i in range(metadata_count)], None,
    )
    client.message.side_effect = lambda message_id: raw_message(message_id)
    client.full_message.return_value = raw_message()
    return task, store, client


@pytest.mark.parametrize("other_campaign", [False, True])
def test_unenabled_campaigns_sync_metadata_without_any_body_capture(other_campaign):
    task, store, client = sync_fixture(metadata_count=1)
    runtime = settings(uuid4()) if other_campaign else settings()
    with patch("app.creator_automation_gmail.CreatorGmailReadClient", return_value=client):
        output = execute_creator_gmail_sync(task, store, runtime)
    client.message.assert_called_once()
    client.full_message.assert_not_called()
    store.body_capture_candidates.assert_not_called()
    store.claim_reply_body.assert_not_called()
    store.save_reply_body.assert_not_called()
    store.save_gmail.assert_called_once()
    store.finalize_reply_sync.assert_called_once()
    assert output["body_reads"] == output["body_complete"] == 0


@pytest.mark.parametrize("other_campaign", [False, True])
def test_full_read_route_refuses_campaigns_outside_deployment_allowlist(other_campaign):
    campaign_id = uuid4()
    runtime = settings(uuid4()) if other_campaign else settings()
    store = Mock()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(creator_automation=store)))
    with patch("app.creator_automation_routes.get_settings", return_value=runtime), \
            pytest.raises(HTTPException) as failure:
        read_reply(request, campaign_id, uuid4(), CreatorAutomationActor(actor="synthetic-reader"))
    assert failure.value.status_code == 409
    assert "not enabled for this campaign" in failure.value.detail
    store.queue_reply_body_read.assert_not_called()


@pytest.mark.parametrize("enabled", [False, True])
def test_overview_readiness_reports_only_the_explicit_capture_scope(enabled):
    campaign_id = uuid4()
    runtime = settings(campaign_id) if enabled else settings()
    store = Mock()
    store.overview.return_value = {"pending_replies": [], "gmail_sync": {}}
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(creator_automation=store)))
    with patch("app.creator_automation_routes.get_settings", return_value=runtime):
        result = overview(request, campaign_id)
    assert result["readiness"]["full_reply_capture_enabled"] is enabled


@pytest.mark.parametrize(("metadata_count", "full_count"), [(0, 3), (17, 3), (19, 1), (20, 0)])
def test_sync_shares_twenty_get_budget_and_hydrates_known_rows_without_new_authority(
    metadata_count, full_count,
):
    task, store, client = sync_fixture(metadata_count)
    with patch("app.creator_automation_gmail.CreatorGmailReadClient", return_value=client):
        output = execute_creator_gmail_sync(task, store, settings(task["payload"]["campaign_id"]))
    assert client.message.call_count == metadata_count
    assert client.full_message.call_count == full_count
    assert client.message.call_count + client.full_message.call_count <= 20
    assert output["body_reads"] == output["body_complete"] == full_count
    assert output["mailbox_modified"] is False
    assert store.save_gmail.call_args.kwargs["mark_complete"] is False
    store.finalize_reply_sync.assert_called_once()
    assert PRIVATE_BODY not in repr(output)
    if full_count:
        capture = store.save_reply_body.call_args.args[3]
        assert capture["status"] == "complete" and capture["text"] == PRIVATE_BODY
    store.review_reply.assert_not_called()
    store.plan_outreach_email.assert_not_called()
    store.start.assert_not_called()


@pytest.mark.parametrize("mutation", ["sender", "subject", "thread", "date", "label", "sent"])
def test_full_message_identity_and_label_changes_never_persist_text(mutation):
    task, store, client = sync_fixture()
    store.body_capture_candidates.return_value = [{"id": uuid4()}]
    raw = raw_message()
    if mutation == "sender":
        raw["payload"]["headers"][0]["value"] = "different@example.test"
    elif mutation == "subject":
        raw["payload"]["headers"][1]["value"] = "Another conversation"
    elif mutation == "thread":
        raw["threadId"] = "otherthread"
    elif mutation == "date":
        raw["internalDate"] = str(int((NOW + timedelta(seconds=1)).timestamp() * 1000))
    else:
        raw["labelIds"] = [] if mutation == "label" else ["Label_Creators", "SENT"]
    client.full_message.return_value = raw
    with patch("app.creator_automation_gmail.CreatorGmailReadClient", return_value=client), \
            patch("app.creator_automation_gmail.parse_gmail_body") as parse:
        execute_creator_gmail_sync(task, store, settings(task["payload"]["campaign_id"]))
    parse.assert_not_called()
    capture = store.save_reply_body.call_args.args[3]
    assert capture["status"] == "unavailable" and capture["text"] == ""
    assert capture["error_code"] == "CREATOR_REPLY_BODY_IDENTITY_CHANGED"


@pytest.mark.parametrize("error", [GmailResourceGoneError("gone"), GmailSyncError("fixed failure")])
def test_failed_full_reads_are_stamped_without_text_or_network_retries(error):
    task, store, client = sync_fixture()
    store.body_capture_candidates.return_value = [{"id": uuid4()}]
    client.full_message.side_effect = error
    with patch("app.creator_automation_gmail.CreatorGmailReadClient", return_value=client):
        if isinstance(error, GmailResourceGoneError):
            execute_creator_gmail_sync(task, store, settings(task["payload"]["campaign_id"]))
        else:
            with pytest.raises(GmailSyncError, match="fixed failure"):
                execute_creator_gmail_sync(task, store, settings(task["payload"]["campaign_id"]))
            store.finalize_reply_sync.assert_not_called()
    client.full_message.assert_called_once()
    capture = store.save_reply_body.call_args.args[3]
    assert capture["status"] == "unavailable" and capture["text"] == ""


def test_mailbox_recheck_failure_prevents_body_egress():
    task, store, client = sync_fixture()
    client.mailbox.side_effect = ["operator@example.test", "different@example.test"]
    with patch("app.creator_automation_gmail.CreatorGmailReadClient", return_value=client), \
            pytest.raises(GmailSyncError, match="changed"):
        execute_creator_gmail_sync(task, store, settings(task["payload"]["campaign_id"]))
    client.full_message.assert_not_called()
    store.claim_reply_body.assert_not_called()


def test_career_metadata_method_is_unchanged_and_creator_full_method_has_fixed_fields():
    career = GmailReadClient.__new__(GmailReadClient)
    career._get = Mock()
    career.message("known")
    assert career._get.call_args.args[1]["format"] == "metadata"
    creator = CreatorGmailReadClient.__new__(CreatorGmailReadClient)
    creator._get = Mock()
    creator.full_message("known")
    assert creator._get.call_args.args == ("messages/known", {
        "format": "full", "fields": "id,threadId,labelIds,snippet,internalDate,payload",
    })
    with pytest.raises(GmailSyncError):
        creator.full_message("../../another-mailbox")
    creator._get.assert_called_once()


def complete_snapshot():
    reply = {**claim(), "campaign_id": uuid4(), "body_status": "complete",
             "body_text": PRIVATE_BODY, "body_format": "plain", "body_version": BODY_VERSION,
             "body_mailbox_key": hashlib.sha256(b"operator@example.test").hexdigest(),
             "body_label_name": "Hermes/Creators"}
    reply["body_digest"] = reply_body_digest(reply)
    return reply


@pytest.mark.parametrize("field", [
    "body_text", "sender", "subject", "gmail_message_id", "gmail_thread_id",
    "body_mailbox_key", "body_label_name", "body_version", "campaign_id",
])
def test_complete_digest_binds_full_text_and_original_identity(field):
    reply = complete_snapshot()
    assert complete_reply_body(reply)
    reply[field] = "changed"
    assert not complete_reply_body(reply)


def test_authored_view_is_only_a_preserved_case_reading_aid():
    text = "Tak, chętnie.\nOn Tue, someone wrote:\nAn old invitation"
    assert authored_body_view(text) == "Tak, chętnie."
    assert text.endswith("An old invitation")


@pytest.mark.parametrize("digest", ["https://example.test", "A" * 64, "f" * 63])
def test_review_digest_is_not_an_arbitrary_input(digest):
    with pytest.raises(ValidationError):
        CreatorReplyReview(actor="operator", classification="interested", body_digest=digest)


@pytest.mark.parametrize("classification", ["interested", "question", "declined_unpaid"])
@pytest.mark.parametrize("failure", ["missing", "stale", "tampered"])
def test_semantic_review_refuses_missing_stale_or_tampered_capture(classification, failure):
    reply = {**complete_snapshot(), "needs_review": True, "prospect_id": uuid4()}
    digest = reply["body_digest"]
    if failure == "missing":
        reply["body_status"] = "missing"
    elif failure == "stale":
        digest = "0" * 64
    else:
        reply["body_text"] = "Changed full text"
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = reply
    store = CreatorAutomationStore("postgresql://synthetic")
    store.connect = Mock()
    store.connect.return_value.__enter__ = Mock(return_value=connection)
    store.connect.return_value.__exit__ = Mock(return_value=False)
    with pytest.raises(MarketingOutreachError, match="complete current reply body digest"):
        store.review_reply(reply["campaign_id"], reply["id"], CreatorReplyReview(
            actor="operator", classification=classification, body_digest=digest,
        ))
    connection.commit.assert_not_called()
