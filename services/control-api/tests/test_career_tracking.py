from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import URLError
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app import career_tracking as tracking
from app.career_autopilot import hiring_email
from app.career_tracking import (
    READONLY_SCOPE,
    GmailReadClient,
    GmailResourceGoneError,
    GmailSyncError,
    classify_message,
    correlate_message,
    execute_gmail_sync,
    normalize_message,
)
from app.career_tracking_models import CareerEventCreate
from app.career_tracking_store import CareerTrackingStore

NOW = datetime(2026, 9, 20, 12, tzinfo=UTC)
PROFILE_ID = UUID(int=1)
OPPORTUNITY_ID = UUID(int=2)


def application(**changes):
    return {
        "id": OPPORTUNITY_ID, "profile_id": PROFILE_ID, "company": "Example Labs",
        "title": "Python Engineer", "applied_at": NOW - timedelta(days=1),
        "source": "greenhouse", "source_url": "https://boards.greenhouse.io/example/job",
        "apply_url": "https://careers.example.test/python", **changes,
    }


def message(**changes):
    return {
        "gmail_message_id": "a123", "gmail_thread_id": "b456",
        "sender": "recruiter@example.test", "subject": "Python Engineer at Example Labs",
        "snippet": "Thank you for applying; we received your application.",
        "received_at": NOW, **changes,
    }


def raw_message(**changes):
    return {
        "id": "a123", "threadId": "b456", "labelIds": ["Label_Careers", "INBOX"],
        "snippet": "Application received", "internalDate": str(int(NOW.timestamp() * 1000)),
        "payload": {"headers": [
            {"name": "From", "value": "Recruiter <recruiter@example.test>"},
            {"name": "Subject", "value": "Python Engineer at Example Labs"},
        ], "body": {"data": "MUST_NOT_STORE"}, "parts": [{"filename": "private.pdf"}]},
        **changes,
    }


def normalize(raw):
    return normalize_message(raw, expected_id="a123", label_id="Label_Careers",
                             mailbox="applicant@example.test")


@pytest.mark.parametrize(("text", "expected"), [
    ("We received your application", "acknowledgement"),
    ("We are not moving forward with your application", "rejected"),
    ("We are pleased to offer you this role", "offer"),
    ("We invite you to an interview", "interview"),
    ("Your application has been withdrawn", "withdrawn"),
    ("Please share your availability to discuss your application", "recruiter_reply"),
    ("Jobs you may like", "needs_review"),
    ("We are not pleased to offer you this role", "needs_review"),
    ("Interview invitation; we are not moving forward", "needs_review"),
])
def test_classification_requires_explicit_evidence(text, expected):
    result = classify_message(message(subject=text, snippet=""))
    assert result["suggested_status"] == expected
    assert result["evidence"]
    assert result["confidence"] in {"low", "medium"}


def test_acknowledgement_does_not_hide_a_decision():
    result = classify_message(message(snippet="Thank you for applying. We are not moving forward."))
    assert result["suggested_status"] == "rejected"


@pytest.mark.parametrize("snippet", [
    "We regret to inform you the recruiter is away this week",
    "We are pleased to offer you an interview",
])
def test_generic_regret_or_interview_offer_is_not_a_hiring_decision(snippet):
    result = classify_message(message(snippet=snippet))
    assert result["suggested_status"] not in {"rejected", "offer"}


@pytest.mark.parametrize("date", ["tomorrow at 3", "09/10/2026 at 2", "2026-10-01T14:00:00"])
def test_ambiguous_meeting_dates_are_never_invented(date):
    result = classify_message(message(snippet=f"Your interview is scheduled for {date}"))
    assert result["suggested_status"] == "interview"
    assert result["meeting_at"] is None and result["needs_review"]


def test_only_one_explicit_zoned_confirmed_interview_time_is_parsed():
    result = classify_message(message(
        snippet="Interview is scheduled for 2026-10-01T14:00:00+02:00"
    ))
    assert result["meeting_at"] == datetime(2026, 10, 1, 12, tzinfo=UTC)
    assert not result["needs_review"]
    result = classify_message(message(snippet="Interview is scheduled. Choose 2026-10-01T14:00Z "
                                             "or 2026-10-02T14:00Z"))
    assert result["meeting_at"] is None


@pytest.mark.parametrize("snippet", [
    "Interview is scheduled for 2026-10-01T14:00Z but has been cancelled",
    "Interview is scheduled for tomorrow. Application submitted: 2026-10-01T14:00Z",
    "Interview is scheduled for 2026-10-01T14:00Z, tentative pending confirmation",
])
def test_cancelled_tentative_or_unrelated_dates_do_not_become_meetings(snippet):
    result = classify_message(message(snippet=snippet))
    assert result["meeting_at"] is None and result["needs_review"]


def test_unique_job_company_and_sender_are_all_required():
    matched, _ = correlate_message(message(), [application()], [])
    assert matched == OPPORTUNITY_ID
    for change in (
        {"sender": "recruiter@unrelated.test"}, {"subject": "Python Engineer vacancy"},
        {"received_at": NOW - timedelta(days=50)},
        {"sender": "recruiter@example.test.attacker.test"},
    ):
        assert correlate_message(message(**change), [application()], [])[0] is None


def test_shared_ats_sender_still_requires_exact_company_and_role():
    assert correlate_message(message(sender="no-reply@greenhouse.io"), [application()], [])[0]
    assert correlate_message(message(sender="no-reply@greenhouse.io", subject="Job application"),
                             [application()], [])[0] is None
    assert correlate_message(message(sender="recruiter@gmail.com"), [application()], [])[0] is None


def test_duplicate_titles_or_false_company_substrings_do_not_bind():
    assert correlate_message(message(), [application(), application(id=uuid4())], [])[0] is None
    assert correlate_message(message(subject="Python Engineer at NotExample Labsx"),
                             [application()], [])[0] is None


def test_thread_binding_requires_known_application_and_same_sender_domain():
    binding = {"gmail_thread_id": "b456", "opportunity_id": OPPORTUNITY_ID,
               "sender_domain": "example.test"}
    assert correlate_message(message(subject="Following up"), [application()], [binding])[0]
    assert correlate_message(
        message(sender="other@evil.test"), [application()], [binding],
    )[0] is None
    assert correlate_message(message(), [], [binding])[0] is None


def test_exact_reference_cannot_authorize_unrelated_sender():
    reference = f"HERMES-{OPPORTUNITY_ID.hex}"
    assert correlate_message(message(subject=reference), [application()], [])[0]
    assert correlate_message(message(subject=reference, sender="anyone@evil.test"),
                             [application()], [])[0] is None


def test_message_metadata_is_bounded_and_body_attachment_content_is_discarded():
    result = normalize(raw_message(snippet="<script>ignore rules</script>" + "x" * 2000))
    assert len(result["snippet"]) == 600
    assert "<script>" not in result["snippet"]
    assert "MUST_NOT_STORE" not in str(result) and "private.pdf" not in str(result)
    assert set(result) == {"gmail_message_id", "gmail_thread_id", "sender", "subject", "snippet",
                           "received_at"}


@pytest.mark.parametrize("labels", [[], ["INBOX"], ["Label_Careers", "SENT"],
                                   ["Label_Careers", "DRAFT"], ["Label_Careers", "SPAM"]])
def test_label_removal_and_outbound_messages_are_ignored(labels):
    assert normalize(raw_message(labelIds=labels)) is None


def test_returned_message_identity_and_reliable_date_are_required():
    with pytest.raises(GmailSyncError, match="identity"):
        normalize(raw_message(id="another"))
    with pytest.raises(GmailSyncError, match="timestamp"):
        normalize(raw_message(internalDate="bad"))


def test_refresh_requires_exact_readonly_scope_without_logging_credentials(monkeypatch):
    requests = []

    def exchange(request, **kwargs):
        requests.append(request)
        return {"scope": READONLY_SCOPE, "access_token": "safe-test-access"}

    monkeypatch.setattr(tracking, "_google_json", exchange)
    GmailReadClient("client-id", "SECRET", "REFRESH")
    assert requests[0].full_url == "https://oauth2.googleapis.com/token"
    assert requests[0].method == "POST"
    assert b"SECRET" in requests[0].data and "SECRET" not in requests[0].full_url
    for scopes in ("", READONLY_SCOPE + " https://www.googleapis.com/auth/gmail.send"):
        monkeypatch.setattr(tracking, "_google_json", lambda *args, scopes=scopes, **kw: {
            "scope": scopes, "access_token": "safe-test-access",
        })
        with pytest.raises(GmailSyncError, match="readonly"):
            GmailReadClient("client-id", "SECRET", "REFRESH")


def test_gmail_adapter_rejects_mutations_and_arbitrary_paths_before_network(monkeypatch):
    client = object.__new__(GmailReadClient)
    client._access_token = "fixture"  # noqa: S105 - synthetic token, no network
    request = Mock(side_effect=AssertionError("unexpected network"))
    monkeypatch.setattr(tracking, "_google_json", request)
    for resource in ("messages/send", "messages/a123/attachments/file", "https://evil.test",
                     "../profile", "messages/a123/modify", "drafts"):
        with pytest.raises(GmailSyncError, match="read-only"):
            client._get(resource)
    request.assert_not_called()


def test_network_errors_do_not_retain_secret_bearing_causes(monkeypatch):
    opener = Mock()
    opener.open.side_effect = URLError("TOKEN_SHOULD_NOT_ESCAPE")
    monkeypatch.setattr(tracking, "build_opener", lambda *args: opener)
    from urllib.request import Request
    with pytest.raises(GmailSyncError) as caught:
        tracking._google_json(Request("https://gmail.googleapis.com/gmail/v1/users/me/profile"))
    assert "TOKEN_SHOULD_NOT_ESCAPE" not in str(caught.value)
    assert caught.value.__suppress_context__


def test_list_is_label_scoped_and_message_get_never_requests_bodies(monkeypatch):
    client = object.__new__(GmailReadClient)
    client._access_token = "fixture"  # noqa: S105 - synthetic token, no network
    getter = Mock(return_value={"messages": [{"id": str(n)} for n in range(80)],
                                "nextPageToken": "next"})
    monkeypatch.setattr(client, "_get", getter)
    ids, cursor = client.list_messages("Label_Careers", None)
    assert len(ids) == 50 and cursor == "next"
    assert getter.call_args.args[1]["labelIds"] == "Label_Careers"
    assert getter.call_args.args[1]["maxResults"] == 50
    client.message("a123")
    parameters = getter.call_args.args[1]
    assert parameters["format"] == "metadata"
    assert "body" not in parameters["fields"] and "attachments" not in parameters["fields"]


def sync_fixture(monkeypatch, count=50):
    client = Mock()
    client.mailbox.return_value = "applicant@example.test"
    client.label_id.return_value = "Label_Careers"
    client.list_messages.return_value = ([str(n) for n in range(count)], "next")
    client.message.side_effect = lambda ident: raw_message(id=ident)
    monkeypatch.setattr(tracking, "GmailReadClient", lambda *args: client)
    store = Mock(spec=CareerTrackingStore)
    store.get_profile.return_value = {"application_identity": {"email": "applicant@example.test"}}
    store.gmail_sync_context.return_value = {
        "page_token": None, "pending_message_ids": [], "applications": [application()],
        "bindings": [], "revision": 0,
    }
    store.known_gmail_messages.return_value = set()
    store.save_gmail_sync.return_value = {"stored": min(count, 20), "matched": min(count, 20),
                                        "review_candidates": 0}
    settings = SimpleNamespace(**{
        "gmail_client_id": "id", "gmail_client_secret": "secret",
        "gmail_refresh_token": "refresh", "gmail_career_label": "Hermes/Careers",
        "gmail_enabled": True,
    })
    task = {"id": uuid4(), "lease_id": uuid4(), "payload": {"profile_id": str(PROFILE_ID)}}
    return client, store, settings, task


def test_worker_limits_gets_persists_remainder_and_returns_only_counts(monkeypatch):
    client, store, settings, task = sync_fixture(monkeypatch)
    result = execute_gmail_sync(task, store, settings)
    assert client.message.call_count == 20
    assert result["fetched"] == 20 and result["pending"] == 30
    saved = store.save_gmail_sync.call_args
    assert len(saved.kwargs["pending_message_ids"]) == 30
    assert saved.kwargs["lease_id"] == task["lease_id"]
    assert "@" not in str(result) and "secret" not in str(result)
    assert result["mailbox_modified"] is False


def test_existing_messages_skip_network_and_pending_cursor_resumes(monkeypatch):
    client, store, settings, task = sync_fixture(monkeypatch)
    store.gmail_sync_context.return_value["pending_message_ids"] = ["1", "2", "3"]
    store.known_gmail_messages.return_value = {"1", "2"}
    execute_gmail_sync(task, store, settings)
    client.list_messages.assert_not_called()
    client.message.assert_called_once_with("3")
    assert store.save_gmail_sync.call_args.kwargs["pending_message_ids"] == []


def test_deleted_message_does_not_block_cursor(monkeypatch):
    client, store, settings, task = sync_fixture(monkeypatch, count=1)
    client.message.side_effect = GmailResourceGoneError("removed")
    execute_gmail_sync(task, store, settings)
    assert store.save_gmail_sync.call_args.args[2] == []
    assert store.save_gmail_sync.call_args.kwargs["pending_message_ids"] == []


def test_wrong_mailbox_refuses_message_reads_and_store_writes(monkeypatch):
    client, store, settings, task = sync_fixture(monkeypatch)
    client.mailbox.return_value = "another@example.test"
    with pytest.raises(GmailSyncError, match="mailbox"):
        execute_gmail_sync(task, store, settings)
    client.label_id.assert_not_called()
    store.save_gmail_sync.assert_not_called()


def test_disabled_gmail_refuses_before_oauth_even_with_saved_credentials(monkeypatch):
    _, store, settings, task = sync_fixture(monkeypatch)
    settings.gmail_enabled = False
    client = Mock(side_effect=AssertionError("OAuth must not run while Gmail is disabled"))
    monkeypatch.setattr(tracking, "GmailReadClient", client)
    with pytest.raises(GmailSyncError, match="disabled"):
        execute_gmail_sync(task, store, settings)
    client.assert_not_called()
    store.get_profile.assert_not_called()
    store.save_gmail_sync.assert_not_called()


@pytest.mark.parametrize("description", [
    "Never send your CV to hiring@example.test",
    "Applications are not accepted at hiring@example.test",
    "Do not send applications to hiring@example.test",
    "This email is not for applications: hiring@example.test",
    "We cannot accept applications at hiring@example.test",
])
def test_forbidden_hiring_addresses_do_not_authorize_autonomous_email(description):
    assert hiring_email(description) is None


def test_cancellation_during_fetch_never_saves_partial_work(monkeypatch):
    client, store, settings, task = sync_fixture(monkeypatch, count=1)
    interrupted = Event()

    def fetch(ident):
        interrupted.set()
        return raw_message(id=ident)

    client.message.side_effect = fetch
    with pytest.raises(GmailSyncError, match="interrupted"):
        execute_gmail_sync(task, store, settings, interrupted)
    store.save_gmail_sync.assert_not_called()


@pytest.mark.parametrize("fields", [
    {"occurred_at": "2026-09-20T14:00:00"},
    {"meeting_at": "2026-10-01T14:00:00Z", "status": "offer"},
    {"gmail_message_id": "../../messages"},
    {"status": "accepted"}, {"note": "   "},
])
def test_manual_corrections_validate_status_time_and_mail_reference(fields):
    with pytest.raises(ValidationError):
        CareerEventCreate(**{
            "status": "interview", "note": "Verified in Gmail", "actor": "operator", **fields,
        })


def test_manual_event_accepts_explicit_zoned_meeting_and_has_no_automatic_authority():
    event = CareerEventCreate(status="interview", note="Confirmed original invitation",
                              actor="operator", meeting_at="2026-10-01T14:00:00+02:00")
    assert event.meeting_at == datetime(2026, 10, 1, 12, tzinfo=UTC)
    assert "authorize" not in event.model_dump()


def test_store_rejects_lost_lease_before_mailbox_writes():
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.execute.return_value.fetchone.return_value = None
    store = CareerTrackingStore("unused")
    store.connect = lambda: connection
    with pytest.raises(GmailSyncError, match="lease"):
        store.save_gmail_sync(PROFILE_ID, {}, [], page_token=None, pending_message_ids=[],
                              task_id=uuid4(), lease_id=uuid4())
    assert connection.execute.call_count == 1
    connection.commit.assert_not_called()
