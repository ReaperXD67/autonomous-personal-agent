from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.models import TaskCancellation
from app.store import Database, InvalidTaskStateError


def _database_with_connection(connection: Mock) -> Database:
    database = Database("unused")

    @contextmanager
    def connect():
        yield connection

    database.connect = connect
    return database


def test_expired_lease_cannot_be_revived_by_heartbeat() -> None:
    task_id, lease_id = uuid4(), uuid4()
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = {
        "status": "running",
        "lease_id": lease_id,
        "lease_valid": False,
        "cancellation_requested_at": None,
    }
    database = _database_with_connection(connection)

    assert database.heartbeat_task(task_id, lease_id, 30) == "lost"
    connection.commit.assert_not_called()


def test_expired_owner_cannot_persist_task_failure() -> None:
    task_id, lease_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    connection = Mock()
    connection.execute.return_value.fetchone.side_effect = [
        {
            "status": "running",
            "lease_id": lease_id,
            "lease_expires_at": now - timedelta(seconds=1),
            "cancellation_requested_at": None,
        },
        {"now": now},
    ]
    database = _database_with_connection(connection)

    with pytest.raises(InvalidTaskStateError, match="expired before failure"):
        database.fail_task(task_id, lease_id, "TEST_FAILURE", "Synthetic failure")
    connection.commit.assert_not_called()


@pytest.mark.parametrize("status", ["queued", "running", "pending_approval", "cancelled"])
def test_cancellation_helper_preserves_callers_transaction(status: str) -> None:
    task_id = uuid4()
    task = {
        "id": task_id,
        "correlation_id": uuid4(),
        "kind": "foundation.echo",
        "status": status,
        "risk_level": "low",
        "approved_by": None,
    }
    cancelled = {**task, "status": "running" if status == "running" else "cancelled"}
    connection = Mock()
    connection.execute.return_value.fetchone.side_effect = [task, cancelled]
    database = _database_with_connection(connection)

    result = database._cancel_task_record(connection, task_id, TaskCancellation(actor="test"))

    assert result["status"] == cancelled["status"]
    connection.commit.assert_not_called()


@pytest.mark.parametrize("limit,stale_seconds", [(0, 60), (501, 60), (50, 0), (50, 86401)])
def test_queued_recovery_rejects_unbounded_inputs(limit: int, stale_seconds: int) -> None:
    with pytest.raises(ValueError, match="bounded"):
        Database("unused").recover_queued_tasks(limit=limit, stale_seconds=stale_seconds)
