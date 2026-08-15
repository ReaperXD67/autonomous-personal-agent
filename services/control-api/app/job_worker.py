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

from app.career import (
    fetch_arbeitnow,
    fetch_ashby,
    fetch_greenhouse,
    generate_application_draft,
    score_opportunity,
)
from app.career_store import CareerStore
from app.logging_config import configure_logging
from app.settings import get_settings
from app.worker import LeaseHeartbeat, TaskInterruptedError

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("job-worker")
stopping = False


def _stop(_signum: int, _frame: FrameType | None) -> None:
    global stopping
    stopping = True


def healthcheck() -> int:
    try:
        database = CareerStore(settings.database_url)
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        healthy = database.check() and bool(client.ping())
        client.close()
        return 0 if healthy else 1
    except Exception:
        return 1


def _check_interrupted(interrupt: threading.Event | None) -> None:
    if interrupt is not None and interrupt.is_set():
        raise TaskInterruptedError("Career task execution was interrupted")


def execute_career_task(
    task: dict[str, object],
    database: CareerStore,
    interrupt: threading.Event | None = None,
) -> dict[str, object]:
    payload = task["payload"]
    if not isinstance(payload, dict):
        raise ValueError("Career task payload must be an object")
    profile_id = UUID(str(payload["profile_id"]))

    if task["kind"] == "career.search":
        profile = database.get_profile(profile_id, include_resume=True)
        source_config = profile["source_config"]
        fetched: list[dict[str, object]] = []
        source_errors: list[str] = []
        sources_attempted = 0
        sources_succeeded = 0

        if source_config.get("arbeitnow"):
            if database.recent_profile_scan_count(profile_id) <= 4:
                sources_attempted += 1
                try:
                    fetched.extend(fetch_arbeitnow())
                    sources_succeeded += 1
                except Exception as exc:
                    source_errors.append(f"arbeitnow: {type(exc).__name__}")
            else:
                source_errors.append("arbeitnow: daily public API limit respected")
        for board in source_config.get("ashby_boards", []):
            _check_interrupted(interrupt)
            sources_attempted += 1
            try:
                fetched.extend(fetch_ashby(board))
                sources_succeeded += 1
            except Exception as exc:
                source_errors.append(f"ashby/{board}: {type(exc).__name__}")
        for board in source_config.get("greenhouse_boards", []):
            _check_interrupted(interrupt)
            sources_attempted += 1
            try:
                fetched.extend(fetch_greenhouse(board))
                sources_succeeded += 1
            except Exception as exc:
                source_errors.append(f"greenhouse/{board}: {type(exc).__name__}")

        if sources_attempted == 0:
            raise ValueError("Career profile has no enabled job sources")
        if sources_succeeded == 0:
            raise RuntimeError("Every configured job source failed")

        matches = []
        for job in fetched:
            _check_interrupted(interrupt)
            scored = score_opportunity(job, profile)
            if scored is not None:
                matches.append(scored)
        save_result = database.save_opportunities(profile_id, matches)
        return {
            "handler": "career.search",
            "profile_id": str(profile_id),
            "sources_succeeded": sources_succeeded,
            "fetched": len(fetched),
            "matched": len(matches),
            "new": save_result["new"],
            "updated": save_result["updated"],
            "source_warnings": source_errors,
        }

    if task["kind"] == "career.application_draft":
        opportunity_id = UUID(str(payload["opportunity_id"]))
        context = database.get_draft_context(opportunity_id, profile_id)
        _check_interrupted(interrupt)
        content = generate_application_draft(context, settings.local_model)
        _check_interrupted(interrupt)
        database.save_application_draft(
            opportunity_id=opportunity_id,
            profile_id=profile_id,
            task_id=UUID(str(task["id"])),
            model=settings.local_model,
            content=content,
        )
        return {
            "handler": "career.application_draft",
            "profile_id": str(profile_id),
            "opportunity_id": str(opportunity_id),
            "model": settings.local_model,
            "draft_created": True,
        }

    raise ValueError("Capability is not implemented in career worker")


def _schedule_due_profiles(database: CareerStore) -> None:
    for profile in database.claim_due_profiles():
        try:
            database.create_scheduled_search(profile)
            logger.info(
                "career scan scheduled",
                extra={"action": "career.scan_scheduled", "profile_id": str(profile["id"])},
            )
        except Exception:
            database.defer_profile(profile["id"])
            logger.exception(
                "career scan scheduling failed",
                extra={"action": "career.schedule_failed", "profile_id": str(profile["id"])},
            )


def run() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    database = CareerStore(settings.database_url)
    client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=settings.worker_poll_seconds + 2,
    )
    worker_id = f"career:{socket.gethostname()}:{os.getpid()}"[:120]
    next_schedule_check = 0.0
    logger.info("career worker started", extra={"action": "startup"})

    while not stopping:
        if time.monotonic() >= next_schedule_check:
            _schedule_due_profiles(database)
            next_schedule_check = time.monotonic() + settings.career_scheduler_seconds
        try:
            item = client.brpop(settings.job_queue_key, timeout=settings.worker_poll_seconds)
        except redis.exceptions.TimeoutError:
            item = None
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
                    "discarded stale career queue item",
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
                output = execute_career_task(task, database, heartbeat.interrupt)
            if heartbeat.reason == "cancel_requested":
                result = database.finalize_cancellation(task_id, lease_id)
            elif heartbeat.reason is not None:
                logger.warning(
                    "career task stopped after lease ownership was lost",
                    extra={"task_id": str(task_id), "action": "task.lease_lost"},
                )
                continue
            else:
                result = database.complete_task(task_id, lease_id, output)
            logger.info(
                "career task finished",
                extra={
                    "task_id": str(task_id),
                    "correlation_id": str(result["correlation_id"]),
                    "action": f"task.{result['status']}",
                },
            )
        except TaskInterruptedError:
            if task_id is not None and lease_id is not None and heartbeat is not None:
                if heartbeat.reason == "cancel_requested":
                    database.finalize_cancellation(task_id, lease_id)
                else:
                    logger.warning(
                        "career task interrupted after lease monitor failure",
                        extra={"task_id": str(task_id), "action": "task.lease_lost"},
                    )
        except Exception as exc:
            logger.exception("career task execution failed", extra={"action": "task.failed"})
            if task_id is not None and lease_id is not None:
                try:
                    database.fail_task(task_id, lease_id, "CAREER_EXECUTION_FAILED", str(exc))
                except Exception:
                    logger.exception(
                        "failed to persist career task failure",
                        extra={"action": "audit.failed"},
                    )

    client.close()
    logger.info("career worker stopped", extra={"action": "shutdown"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    if args.healthcheck:
        raise SystemExit(healthcheck())
    run()


if __name__ == "__main__":
    main()
