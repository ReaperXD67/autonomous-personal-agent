from __future__ import annotations

import argparse
import json
import logging
import signal
import time
from types import FrameType

import redis

from app.logging_config import configure_logging
from app.settings import get_settings
from app.store import Database

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("dispatcher")
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


def run() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    database = Database(settings.database_url)
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("outbox dispatcher started", extra={"action": "startup"})

    while not stopping:
        recovery = database.recover_expired_tasks(
            retry_base_seconds=settings.worker_retry_base_seconds,
            retry_max_seconds=settings.worker_retry_max_seconds,
        )
        if any(recovery.values()):
            logger.warning(
                "expired worker leases reconciled",
                extra={"action": "lease.reconciled", **recovery},
            )
        events = database.pending_outbox(limit=50)
        if not events:
            time.sleep(1)
            continue
        for event in events:
            if stopping:
                break
            try:
                queue_key = (
                    settings.action_queue_key
                    if event["topic"] == "action.ready"
                    else (
                        settings.job_queue_key
                        if event["topic"] == "career.ready"
                        else settings.task_queue_key
                    )
                )
                client.lpush(queue_key, json.dumps(event["payload"]))
                database.mark_outbox_published(event["id"])
                logger.info(
                    "outbox event published",
                    extra={
                        "task_id": str(event["task_id"]),
                        "correlation_id": str(event["correlation_id"]),
                        "action": "outbox.published",
                    },
                )
            except Exception as exc:
                database.mark_outbox_failed(
                    event["id"],
                    str(exc),
                    retry_base_seconds=settings.worker_retry_base_seconds,
                    retry_max_seconds=settings.worker_retry_max_seconds,
                )
                logger.exception(
                    "outbox publish failed",
                    extra={
                        "task_id": str(event["task_id"]),
                        "correlation_id": str(event["correlation_id"]),
                        "action": "outbox.failed",
                    },
                )
                time.sleep(1)

    client.close()
    logger.info("outbox dispatcher stopped", extra={"action": "shutdown"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    if args.healthcheck:
        raise SystemExit(healthcheck())
    run()


if __name__ == "__main__":
    main()
