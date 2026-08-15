import threading
from unittest.mock import Mock

import pytest
import redis

from app.worker import TaskInterruptedError, claim_next, execute_foundation_task


def test_empty_blocking_poll_timeout_is_not_a_worker_failure() -> None:
    client = Mock()
    client.brpop.side_effect = redis.exceptions.TimeoutError("empty blocking poll")

    assert claim_next(client) is None
    client.brpop.assert_called_once()


def test_foundation_wait_is_bounded() -> None:
    task = {"kind": "foundation.wait", "payload": {"seconds": 61}}
    with pytest.raises(ValueError, match="between 0 and 60"):
        execute_foundation_task(task)


def test_foundation_wait_honors_cooperative_interrupt() -> None:
    interrupt = threading.Event()
    interrupt.set()
    task = {"kind": "foundation.wait", "payload": {"seconds": 1}}
    with pytest.raises(TaskInterruptedError):
        execute_foundation_task(task, interrupt)
