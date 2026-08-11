from unittest.mock import Mock

import redis

from app.worker import claim_next


def test_empty_blocking_poll_timeout_is_not_a_worker_failure() -> None:
    client = Mock()
    client.brpop.side_effect = redis.exceptions.TimeoutError("empty blocking poll")

    assert claim_next(client) is None
    client.brpop.assert_called_once()
