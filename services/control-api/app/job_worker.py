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
from typing import Any
from uuid import UUID

import redis

from app.career import (
    application_draft_messages,
    fetch_arbeitnow,
    fetch_ashby,
    fetch_greenhouse,
    fetch_lever,
    generate_application_draft_with_usage,
    parse_application_draft,
    prioritize_opportunities,
    score_opportunity,
)
from app.inference import OpenRouterError, OpenRouterFreeClient, OpenRouterPlan
from app.logging_config import configure_logging
from app.marketing import fetch_youtube_creators
from app.marketing_store import MarketingStore
from app.models import TaskCreate
from app.planning import execute_planning_task
from app.planning_store import PlanningStore
from app.policy import RiskLevel
from app.settings import get_settings
from app.worker import LeaseHeartbeat, TaskInterruptedError

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("job-worker")
stopping = False
openrouter_client = (
    OpenRouterFreeClient(
        api_key=settings.openrouter_api_key,
        priority=settings.openrouter_model_priority,
        max_models=settings.openrouter_max_models,
        free_daily_allowance=settings.openrouter_free_daily_allowance,
        daily_request_cap=settings.openrouter_daily_request_cap,
        data_collection=settings.openrouter_data_collection,
        zdr=settings.openrouter_zdr,
    )
    if settings.openrouter_enabled
    else None
)


def _stop(_signum: int, _frame: FrameType | None) -> None:
    global stopping
    stopping = True


def healthcheck() -> int:
    try:
        database = MarketingStore(settings.database_url)
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        healthy = database.check() and bool(client.ping())
        client.close()
        return 0 if healthy else 1
    except Exception:
        return 1


def _check_interrupted(interrupt: threading.Event | None) -> None:
    if interrupt is not None and interrupt.is_set():
        raise TaskInterruptedError("Research task execution was interrupted")


def execute_career_task(
    task: dict[str, object],
    database: MarketingStore,
    interrupt: threading.Event | None = None,
) -> dict[str, object]:
    payload = task["payload"]
    if not isinstance(payload, dict):
        raise ValueError("Research task payload must be an object")

    if task["kind"] == "planning.propose":
        return execute_planning_task(
            task, PlanningStore(settings.database_url), settings,
            client=openrouter_client, interrupt=interrupt,
        )

    if task["kind"] == "marketing.creator_discovery":
        campaign_id = UUID(str(payload["campaign_id"]))
        if database.recent_marketing_scan_count() > 30:
            raise RuntimeError("Daily YouTube discovery task limit reached")
        campaign = database.get_campaign(campaign_id)
        _check_interrupted(interrupt)
        prospects = fetch_youtube_creators(settings.youtube_api_key, campaign)
        _check_interrupted(interrupt)
        saved = database.save_discovered_prospects(campaign_id, prospects)
        return {
            "handler": "marketing.creator_discovery",
            "campaign_id": str(campaign_id),
            "queries": len(campaign["discovery_queries"]),
            "discovered": len(prospects),
            "new": saved["new"],
            "updated": saved["updated"],
            "contact_emails_discovered": 0,
        }

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
        for board in source_config.get("lever_boards", []):
            _check_interrupted(interrupt)
            sources_attempted += 1
            try:
                fetched.extend(fetch_lever(board))
                sources_succeeded += 1
            except Exception as exc:
                source_errors.append(f"lever/{board}: {type(exc).__name__}")

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
        # save_opportunities selects the first bounded set for automatic
        # preparation, so rank before persistence instead of spending scarce
        # hosted free calls in provider arrival order.
        matches = prioritize_opportunities(matches)
        save_result = database.save_opportunities(profile_id, matches)
        auto_prepared = 0
        if profile["resume_text"].strip() and not payload.get("workflow_managed"):
            for opportunity_id in save_result["auto_prepare_ids"]:
                _check_interrupted(interrupt)
                database.create_task(
                    TaskCreate(
                        title="Prepare a truthful application pack",
                        kind="career.application_draft",
                        payload={
                            "profile_id": str(profile_id),
                            "opportunity_id": str(opportunity_id),
                            "trigger": "auto_prepare",
                        },
                        risk_level=RiskLevel.MEDIUM,
                        requested_by="scheduler:career-auto-prepare",
                        idempotency_key=f"career-auto-draft:{opportunity_id}",
                    )
                )
                database.create_task(
                    TaskCreate(
                        title="Inspect an official application form",
                        kind="career.application_preflight",
                        payload={
                            "profile_id": str(profile_id),
                            "opportunity_id": str(opportunity_id),
                            "trigger": "auto_prepare",
                        },
                        risk_level=RiskLevel.MEDIUM,
                        requested_by="scheduler:career-auto-prepare",
                        idempotency_key=f"career-auto-preflight:{opportunity_id}",
                    )
                )
                auto_prepared += 1
        return {
            "handler": "career.search",
            "profile_id": str(profile_id),
            "sources_succeeded": sources_succeeded,
            "fetched": len(fetched),
            "matched": len(matches),
            "new": save_result["new"],
            "updated": save_result["updated"],
            "auto_prepared": auto_prepared,
            "source_warnings": source_errors,
        }

    if task["kind"] == "career.application_draft":
        opportunity_id = UUID(str(payload["opportunity_id"]))
        task_id = UUID(str(task["id"]))
        context = database.get_draft_context(opportunity_id, profile_id)
        _check_interrupted(interrupt)
        content: dict[str, Any] | None = None
        selected_model = settings.local_model
        selected_provider = "ollama"
        fallback_attempt = 1
        route_warning: str | None = None

        if openrouter_client is not None:
            try:
                plan = openrouter_client.plan()
                remaining_models = plan.models
                route_offset = 0
                while remaining_models and content is None:
                    attempt_plan = OpenRouterPlan(
                        models=remaining_models,
                        daily_limit=plan.daily_limit,
                        free_tier=plan.free_tier,
                    )
                    invocation_id = database.start_inference_invocation(
                        task_id=task_id,
                        purpose="career.application_draft",
                        provider="openrouter",
                        requested_models=attempt_plan.models,
                        privacy_mode=openrouter_client.privacy_mode,
                        daily_limit=attempt_plan.daily_limit,
                    )
                    if invocation_id is None:
                        route_warning = "OPENROUTER_LOCAL_DAILY_CAP_REACHED"
                        break
                    try:
                        remote = openrouter_client.complete(
                            application_draft_messages(context), attempt_plan
                        )
                        try:
                            content = parse_application_draft(remote.content)
                        except ValueError:
                            database.fail_inference_invocation(
                                invocation_id, "OPENROUTER_DRAFT_INVALID"
                            )
                            route_warning = "OPENROUTER_DRAFT_INVALID"
                            openrouter_client.reject_model(remote.selected_route)
                            selected_index = remaining_models.index(
                                remote.selected_route
                            )
                            route_offset += selected_index + 1
                            remaining_models = remaining_models[selected_index + 1 :]
                            continue
                        database.complete_inference_invocation(
                            invocation_id,
                            selected_model=remote.selected_model,
                            selected_provider=remote.selected_provider,
                            prompt_tokens=remote.prompt_tokens,
                            completion_tokens=remote.completion_tokens,
                            total_tokens=remote.total_tokens,
                            cost=remote.cost,
                            latency_ms=remote.latency_ms,
                            fallback_attempt=remote.fallback_attempt,
                        )
                        selected_model = remote.selected_model
                        selected_provider = remote.selected_provider or "openrouter"
                        fallback_attempt = (
                            route_offset
                            + attempt_plan.models.index(remote.selected_route)
                            + 1
                        )
                    except OpenRouterError as exc:
                        database.fail_inference_invocation(invocation_id, exc.code)
                        route_warning = exc.code
                        if exc.failed_model in remaining_models:
                            openrouter_client.reject_model(exc.failed_model)
                            selected_index = remaining_models.index(exc.failed_model)
                            route_offset += selected_index + 1
                            remaining_models = remaining_models[selected_index + 1 :]
                            continue
                        break
            except OpenRouterError as exc:
                route_warning = exc.code

        if content is None:
            if openrouter_client is not None and not settings.openrouter_local_fallback:
                raise RuntimeError(
                    f"OpenRouter free route failed without local fallback: {route_warning}"
                )
            local_invocation_id = database.start_inference_invocation(
                task_id=task_id,
                purpose="career.application_draft",
                provider="ollama",
                requested_models=(settings.local_model,),
                privacy_mode="local_only",
            )
            if local_invocation_id is None:
                raise RuntimeError("Could not reserve the local inference invocation")
            local_started = time.monotonic()
            try:
                content, local_usage = generate_application_draft_with_usage(
                    context, settings.local_model
                )
            except Exception:
                database.fail_inference_invocation(
                    local_invocation_id, "LOCAL_MODEL_COMPLETION_FAILED"
                )
                raise
            database.complete_inference_invocation(
                local_invocation_id,
                selected_model=settings.local_model,
                selected_provider="ollama",
                prompt_tokens=local_usage["prompt_tokens"],
                completion_tokens=local_usage["completion_tokens"],
                total_tokens=local_usage["total_tokens"],
                cost=0,
                latency_ms=round((time.monotonic() - local_started) * 1000),
                fallback_attempt=1,
            )
        _check_interrupted(interrupt)
        database.save_application_draft(
            opportunity_id=opportunity_id,
            profile_id=profile_id,
            task_id=task_id,
            model=selected_model,
            content=content,
        )
        auto_action = (
            None if payload.get("workflow_managed")
            else database.try_create_automatic_application_action(opportunity_id)
        )
        return {
            "handler": "career.application_draft",
            "profile_id": str(profile_id),
            "opportunity_id": str(opportunity_id),
            "model": selected_model,
            "model_provider": selected_provider,
            "model_fallback_attempt": fallback_attempt,
            "route_warning": route_warning,
            "draft_created": True,
            "automatic_approval_task_created": auto_action is not None,
        }

    raise ValueError("Capability is not implemented in career worker")


def _schedule_due_work(database: MarketingStore) -> None:
    for scope, schedule in (
        ("career", database.schedule_due_profiles),
        ("marketing", database.schedule_due_campaigns),
    ):
        try:
            for scheduled in schedule():
                logger.info(
                    "scheduled task committed",
                    extra={"action": f"{scope}.scheduled", "task_id": str(scheduled["task_id"])},
                )
        except Exception as error:
            # Rollback preserves the due occurrence for the next bounded poll.
            logger.error(
                "scheduler transaction rolled back",
                extra={"action": f"{scope}.schedule_failed", "error_type": type(error).__name__},
            )


def run() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    database = MarketingStore(settings.database_url)
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
            _schedule_due_work(database)
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
        task: dict[str, Any] | None = None
        try:
            envelope = json.loads(item[1])
            task_id = UUID(envelope["task_id"])
            task = database.transition_to_running(
                task_id, settings.worker_lease_seconds, worker_id
            )
            if task is None:
                logger.warning(
                    "discarded stale research queue item",
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
                    "research task stopped after lease ownership was lost",
                    extra={"task_id": str(task_id), "action": "task.lease_lost"},
                )
                continue
            else:
                result = database.complete_task(task_id, lease_id, output)
            logger.info(
                "research task finished",
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
                        "research task interrupted after lease monitor failure",
                        extra={"task_id": str(task_id), "action": "task.lease_lost"},
                    )
        except Exception as exc:
            logger.exception("research task execution failed", extra={"action": "task.failed"})
            if task_id is not None and lease_id is not None:
                try:
                    error_code = (
                        "MARKETING_EXECUTION_FAILED"
                        if task is not None and task["kind"].startswith("marketing.")
                        else "CAREER_EXECUTION_FAILED"
                    )
                    database.fail_task(task_id, lease_id, error_code, str(exc))
                except Exception:
                    logger.exception(
                        "failed to persist research task failure",
                        extra={"action": "audit.failed"},
                    )

    client.close()
    logger.info("research worker stopped", extra={"action": "shutdown"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    if args.healthcheck:
        raise SystemExit(healthcheck())
    run()


if __name__ == "__main__":
    main()
