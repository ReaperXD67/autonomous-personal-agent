from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import threading
import time
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


class TaskInterruptedError(RuntimeError):
    pass


class LeaseHeartbeat:
    def __init__(
        self,
        database: Database,
        task_id: UUID,
        lease_id: UUID,
        lease_seconds: int,
        heartbeat_seconds: int,
    ) -> None:
        self._database = database
        self._task_id = task_id
        self._lease_id = lease_id
        self._lease_seconds = lease_seconds
        self._heartbeat_seconds = heartbeat_seconds
        self._stop = threading.Event()
        self.interrupt = threading.Event()
        self.reason: str | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(self._heartbeat_seconds):
            try:
                state = self._database.heartbeat_task(
                    self._task_id, self._lease_id, self._lease_seconds
                )
            except Exception:
                logger.exception(
                    "lease heartbeat failed",
                    extra={"task_id": str(self._task_id), "action": "task.heartbeat_failed"},
                )
                state = "heartbeat_failed"
            if state != "renewed":
                self.reason = state
                self.interrupt.set()
                return

    def __enter__(self) -> LeaseHeartbeat:
        self._thread.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self._stop.set()
        self._thread.join(timeout=self._heartbeat_seconds + 1)


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


def execute_foundation_task(
    task: dict, interrupt: threading.Event | None = None
) -> dict:
    if task["kind"] == "foundation.echo":
        if interrupt is not None and interrupt.is_set():
            raise TaskInterruptedError("Task execution was interrupted")
        message = str(task["payload"].get("message", ""))[:2000]
        return {"echo": message, "handler": "foundation.echo"}
    if task["kind"] == "foundation.wait":
        seconds = float(task["payload"].get("seconds", 1))
        if not 0 <= seconds <= 60:
            raise ValueError("foundation.wait seconds must be between 0 and 60")
        deadline = time.monotonic() + seconds
        while (remaining := deadline - time.monotonic()) > 0:
            if interrupt is not None and interrupt.wait(timeout=min(0.25, remaining)):
                raise TaskInterruptedError("Task execution was interrupted")
            if interrupt is None:
                time.sleep(min(0.25, remaining))
        return {"waited_seconds": seconds, "handler": "foundation.wait"}
    raise ValueError("Capability is not implemented in foundation worker")


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
    worker_id = f"{socket.gethostname()}:{os.getpid()}"[:120]

    while not stopping:
        item = claim_next(client)
        if item is None:
            continue
        task_id: UUID | None = None
        lease_id: UUID | None = None
        heartbeat: LeaseHeartbeat | None = None
        try:
            envelope = json.loads(item[1])
            task_id = UUID(envelope["task_id"])
            task = database.transition_to_running(
                task_id, settings.worker_lease_seconds, worker_id
            )
            if task is None:
                logger.warning(
                    "discarded stale queue item",
                    extra={"task_id": str(task_id), "action": "task.discarded"},
                )
                continue
            lease_id = task["lease_id"]
            with LeaseHeartbeat(
                database,
                task_id,
                lease_id,
                settings.worker_lease_seconds,
                settings.worker_heartbeat_seconds,
            ) as heartbeat:
                output = execute_foundation_task(task, heartbeat.interrupt)
            if heartbeat.reason == "cancel_requested":
                task = database.finalize_cancellation(task_id, lease_id)
            elif heartbeat.reason is not None:
                logger.warning(
                    "task execution stopped after lease ownership was lost",
                    extra={"task_id": str(task_id), "action": "task.lease_lost"},
                )
                continue
            else:
                task = database.complete_task(task_id, lease_id, output)
            logger.info(
                "task finished",
                extra={
                    "task_id": str(task_id),
                    "correlation_id": str(task["correlation_id"]),
                    "action": f"task.{task['status']}",
                },
            )
        except TaskInterruptedError:
            if task_id is not None and lease_id is not None and heartbeat is not None:
                if heartbeat.reason == "cancel_requested":
                    database.finalize_cancellation(task_id, lease_id)
                    logger.info(
                        "task cancelled",
                        extra={"task_id": str(task_id), "action": "task.cancelled"},
                    )
                else:
                    logger.warning(
                        "task interrupted after lease monitor failure",
                        extra={"task_id": str(task_id), "action": "task.lease_lost"},
                    )
        except Exception as exc:
            logger.exception("task execution failed", extra={"action": "task.failed"})
            if task_id is not None and lease_id is not None:
                try:
                    database.fail_task(
                        task_id, lease_id, "WORKER_EXECUTION_FAILED", str(exc)
                    )
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
