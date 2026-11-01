import threading
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import UUID, uuid4, uuid5

import pytest
from pydantic import ValidationError

from app.application_browser import canonical_hash
from app.creator_draft_batch_store import (
    KIND,
    LIMITS,
    CreatorDraftBatchCreate,
    CreatorDraftBatchStore,
    batch_items,
    creator_identity_keys,
)
from app.creator_draft_store import CreatorDraftStore
from app.models import TaskCreate
from app.policy import RiskLevel, effective_risk
from app.store import InvalidTaskStateError
from app.worker import TaskInterruptedError


def reservation(size=3):
    namespace = uuid4()
    identities = [uuid4() for _ in range(size)]
    return {
        "campaign_id": str(uuid4()), "requested_limit": size, "campaign_hash": "a" * 64,
        "items": [{"prospect_id": str(identity), "input_hash": "b" * 64,
                   "child_idempotency_key": str(uuid5(namespace, str(identity)))}
                  for identity in identities],
    }


def owned_task():
    now = datetime.now(UTC)
    return {
        "id": uuid4(), "kind": KIND, "status": "running", "lease_id": uuid4(),
        "lease_expires_at": now + timedelta(minutes=5), "created_at": now,
        "cancellation_requested_at": None, "payload": reservation(),
    }


@pytest.mark.parametrize("limit", [0, 6, True, "3", 2.5])
def test_batch_request_requires_an_explicit_small_integer_limit(limit):
    with pytest.raises(ValidationError):
        CreatorDraftBatchCreate(actor="fixture", idempotency_key=uuid4(), limit=limit)


def test_batch_default_and_policy_grant_preparation_without_email_authority():
    request = CreatorDraftBatchCreate(actor="fixture", idempotency_key=uuid4())
    task = TaskCreate(title="Prepare drafts", kind=KIND, requested_by=request.actor)
    assert request.limit == 3
    assert effective_risk(task.kind, task.risk_level) == RiskLevel.MEDIUM
    assert LIMITS == {
        "max_batch": 5, "drafts_per_rolling_day": 30,
        "drafts_per_prospect_per_rolling_day": 3, "messages_sent": 0, "approvals_created": 0,
    }
    with pytest.raises(ValidationError):
        CreatorDraftBatchCreate(actor="fixture", idempotency_key=uuid4(), auto_send=True)


@pytest.mark.parametrize("change", [
    lambda value: value.update(items=[]),
    lambda value: value.update(requested_limit=True),
    lambda value: value.update(requested_limit=6),
    lambda value: value.update(items=value["items"] * 2),
    lambda value: value["items"][1].update(prospect_id=value["items"][0]["prospect_id"]),
    lambda value: value["items"][1].update(
        child_idempotency_key=value["items"][0]["child_idempotency_key"],
    ),
    lambda value: value["items"][0].update(input_hash="not-a-hash"),
    lambda value: value["items"][0].update(contact_email="never-in-a-task@example.test"),
    lambda value: value.update(campaign_id="not-an-id"),
    lambda value: value.update(unbounded=True),
])
def test_malformed_or_duplicate_reservations_are_refused(change):
    payload = reservation()
    change(payload)
    with pytest.raises(InvalidTaskStateError):
        batch_items(payload)


def test_issued_audit_binds_the_current_canonical_payload():
    task = owned_task()
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = {"exists": 1}
    assert CreatorDraftBatchStore._issued_batch(connection, task)
    assert connection.execute.call_args.args[1] == (
        task["id"], "creator.draft_batch.created", canonical_hash(task["payload"]),
    )


def test_stopped_reservations_count_but_materialized_children_are_not_counted_twice():
    payload = reservation(3)
    parent = {"payload": payload, "payload_hash": canonical_hash(payload),
              "requested_by": "fixture"}
    materialized = payload["items"][0]
    connection = Mock()
    connection.execute.side_effect = [
        Mock(fetchone=lambda: {"total": 27, "creator": 1}),
        Mock(fetchall=lambda: [parent]),
        Mock(fetchall=lambda: [{
            "idempotency_key": UUID(materialized["child_idempotency_key"]),
            "prospect_id": UUID(materialized["prospect_id"]),
            "requested_by": "fixture", "input_hash": materialized["input_hash"],
        }]),
    ]
    prospect_id = UUID(payload["items"][1]["prospect_id"])
    counts = CreatorDraftStore._draft_budget_counts(connection, prospect_id)
    assert counts == {"total": 29, "creator": 2}


def test_modified_parent_payload_does_not_supply_reservation_authority():
    payload = reservation(1)
    parent = {"payload": payload, "payload_hash": "0" * 64, "requested_by": "fixture"}
    connection = Mock()
    connection.execute.return_value.fetchall.return_value = [parent]
    assert CreatorDraftStore._draft_reservations(connection) == {}
    assert connection.execute.call_count == 1


def test_canonical_identity_keys_share_channels_or_exact_addresses_without_name_merging():
    left = {"platform": "youtube", "external_id": "UC-one", "display_name": "Same name",
            "profile_url": "https://youtube.com/channel/UC-one/",
            "contact_email": "Creator@Example.test"}
    same_channel = {**left, "contact_email": "new@example.test"}
    shared_address = {**left, "external_id": "UC-two", "profile_url": "https://other.test/",
                      "contact_email": "creator@example.test"}
    unrelated = {**shared_address, "contact_email": "other@example.test"}
    assert creator_identity_keys(left) & creator_identity_keys(same_channel)
    assert creator_identity_keys(left) & creator_identity_keys(shared_address)
    assert not creator_identity_keys(left) & creator_identity_keys(unrelated)


@pytest.mark.parametrize("change", [
    {"status": "cancelled"}, {"cancellation_requested_at": datetime.now(UTC)},
    {"lease_expires_at": datetime.now(UTC) - timedelta(seconds=1)},
    {"created_at": datetime.now(UTC) - timedelta(days=1, seconds=1)},
    {"kind": "marketing.creator_draft"},
])
def test_batch_ownership_refuses_stopped_expired_or_unrelated_tasks(change):
    task = owned_task()
    task.update(change)
    connection = Mock()
    connection.execute.side_effect = [Mock(fetchone=lambda: task),
                                      Mock(fetchone=lambda: {"value": datetime.now(UTC)})]
    store = CreatorDraftBatchStore.__new__(CreatorDraftBatchStore)
    with pytest.raises(InvalidTaskStateError, match="valid execution lease"):
        store._owned_batch(connection, task["id"], task["lease_id"])


def test_generic_parent_task_cannot_issue_children_without_the_server_audit():
    task = owned_task()
    connection = Mock()
    connection.execute.side_effect = [Mock(fetchone=lambda: task),
                                      Mock(fetchone=lambda: {"value": datetime.now(UTC)}),
                                      Mock(fetchone=lambda: None)]
    store = CreatorDraftBatchStore.__new__(CreatorDraftBatchStore)
    with pytest.raises(InvalidTaskStateError, match="server-issued"):
        store._owned_batch(connection, task["id"], task["lease_id"])


def test_interruption_prevents_any_parent_or_child_work():
    task = owned_task()
    store = CreatorDraftBatchStore.__new__(CreatorDraftBatchStore)
    store.batch_context = Mock()
    store._queue_reserved_child = Mock()
    interrupt = threading.Event()
    interrupt.set()
    with pytest.raises(TaskInterruptedError):
        store.execute_batch(task, interrupt)
    store.batch_context.assert_not_called()
    store._queue_reserved_child.assert_not_called()


def test_execution_reports_partial_skips_and_never_prepares_an_email():
    task = owned_task()
    store = CreatorDraftBatchStore.__new__(CreatorDraftBatchStore)
    store.batch_context = Mock(return_value=task)
    store._queue_reserved_child = Mock(side_effect=[
        {"status": "queued", "draft_id": str(uuid4())},
        {"status": "skipped", "reason": "DRAFT_CONTEXT_CHANGED"},
        {"status": "skipped", "reason": "DRAFT_NO_LONGER_ELIGIBLE"},
    ])
    store.plan_outreach_email = Mock()
    output = store.execute_batch(task)
    assert output["queued_count"] == 1 and output["skipped_count"] == 2
    assert output["limits"]["messages_sent"] == output["limits"]["approvals_created"] == 0
    assert [call.args[2] for call in store._queue_reserved_child.call_args_list] == (
        task["payload"]["items"]
    )
    store.plan_outreach_email.assert_not_called()
