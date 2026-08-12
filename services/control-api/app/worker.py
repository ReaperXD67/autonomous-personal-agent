from __future__ import annotations

import argparse
import json
import logging
import signal
from types import FrameType
from uuid import UUID

import redis

from app.logging_config import configure_logging
from app.settings import get_settings
from app.store import Database

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("worker")
stopping = False


def _stop(_signum: int, _frame: FrameType | None) -> None:
    global stopping
    stopping = True


def healthcheck() -> int:
    try:
        database = Database(settings.database_url)
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        healthy = database.check() and bool(client.ping())
        client.close()
        return 0 if healthy else 1
    except Exception:
        return 1


def execute_foundation_task(task: dict) -> dict:
    if task["kind"] != "foundation.echo":
        raise ValueError("Capability is not implemented in foundation worker")
    message = str(task["payload"].get("message", ""))[:2000]
    return {"echo": message, "handler": "foundation.echo"}


def claim_next(client: redis.Redis) -> tuple[str, str] | None:
    try:
        return client.brpop(settings.task_queue_key, timeout=settings.worker_poll_seconds)
    except redis.exceptions.TimeoutError:
        # redis-py 8 can surface an empty blocking poll as a socket timeout.
        return None


def run() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    database = Database(settings.database_url)
    client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=settings.worker_poll_seconds + 2,
    )
    logger.info("worker started", extra={"action": "startup"})

    while not stopping:
        item = claim_next(client)
        if item is None:
            continue
        task_id: UUID | None = None
        try:
            envelope = json.loads(item[1])
            task_id = UUID(envelope["task_id"])
            task = database.transition_to_running(task_id, settings.worker_lease_seconds)
            if task is None:
                logger.warning(
                    "discarded stale queue item",
                    extra={"task_id": str(task_id), "action": "task.discarded"},
                )
                continue
            output = execute_foundation_task(task)
            task = database.complete_task(task_id, output)
            logger.info(
                "task succeeded",
                extra={
                    "task_id": str(task_id),
                    "correlation_id": str(task["correlation_id"]),
                    "action": "task.succeeded",
                },
            )
        except Exception as exc:
            logger.exception("task execution failed", extra={"action": "task.failed"})
            if task_id is not None:
                try:
                    database.fail_task(task_id, "WORKER_EXECUTION_FAILED", str(exc))
                except Exception:
                    logger.exception(
                        "failed to persist task failure",
                        extra={"action": "audit.failed"},
                    )

    client.close()
    logger.info("worker stopped", extra={"action": "shutdown"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    if args.healthcheck:
        raise SystemExit(healthcheck())
    run()


if __name__ == "__main__":
    main()
