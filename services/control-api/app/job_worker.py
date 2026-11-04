from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import threading
import time
from datetime import UTC, datetime
from types import FrameType
from typing import Any
from uuid import UUID

import redis

from app.career import (
    FILTER_REASONS,
    SCORING_POLICY_VERSION,
    application_draft_messages,
    diagnose_opportunity,
    fetch_arbeitnow,
    fetch_ashby,
    fetch_greenhouse,
    fetch_lever,
    fetch_remotive,
    generate_application_draft_with_usage,
    parse_application_draft,
    prioritize_opportunities,
    score_opportunity,
)
from app.career_autopilot_store import CareerAutopilotStore
from app.career_smartrecruiters import fetch_smartrecruiters, smartrecruiters_country_hint
from app.career_tracking import execute_gmail_sync
from app.career_tracking_store import CareerTrackingStore
from app.career_yc import fetch_yc
from app.creator_automation_gmail import execute_creator_gmail_sync
from app.creator_automation_store import CreatorAutomationStore
from app.creator_draft_batch_store import CreatorDraftBatchStore
from app.creator_draft_store import CreatorDraftStore
from app.creator_drafting import execute_creator_draft_task
from app.creator_pilot_runner import execute_creator_pilot
from app.creator_pilot_store import CreatorPilotStore
from app.creator_reply_draft_store import CreatorReplyDraftStore
from app.creator_reply_drafting import execute_creator_reply_draft_task
from app.inference import OpenRouterError, OpenRouterFreeClient, OpenRouterPlan
from app.logging_config import configure_logging
from app.marketing import fetch_youtube_creators, fetch_youtube_prospect
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

    if task["kind"] == "marketing.creator_draft_batch":
        return CreatorDraftBatchStore(settings.database_url).execute_batch(
            task, interrupt=interrupt,
        )

    if task["kind"] == "marketing.creator_draft":
        return execute_creator_draft_task(
            task, CreatorDraftStore(settings.database_url), settings,
            client=openrouter_client, interrupt=interrupt,
        )

    if task["kind"] == "marketing.creator_reply_draft":
        return execute_creator_reply_draft_task(
            task, CreatorReplyDraftStore(settings.database_url), settings, interrupt=interrupt,
        )

    if task["kind"] == "marketing.creator_pilot":
        return execute_creator_pilot(
            task, CreatorPilotStore(settings.database_url), settings, interrupt=interrupt,
        )

    if task["kind"] == "career.gmail_sync":
        return execute_gmail_sync(
            task, CareerTrackingStore(settings.database_url), settings, interrupt=interrupt,
        )

    if task["kind"] in {"marketing.gmail_sync", "marketing.creator_automation"}:
        automation = CreatorAutomationStore(
            settings.database_url, email_pacing_policy=settings.email_pacing_policy(),
        )
        _check_interrupted(interrupt)
        if task["kind"] == "marketing.gmail_sync":
            return execute_creator_gmail_sync(task, automation, settings, interrupt=interrupt)
        return automation.execute(
            task, sender=(settings.career_email_sender
                          if settings.career_email_transport != "disabled" else ""),
        )

    if task["kind"] == "marketing.creator_discovery":
        campaign_id = UUID(str(payload["campaign_id"]))
        if database.recent_marketing_scan_count() > 30:
            raise RuntimeError("Daily YouTube discovery task limit reached")
        campaign = database.get_campaign(campaign_id)
        _check_interrupted(interrupt)
        if payload.get("prospect_id"):
            prospect_id = UUID(str(payload["prospect_id"]))
            prospect = database.get_prospect(prospect_id)
            if str(prospect["campaign_id"]) != str(campaign_id):
                raise ValueError("Prospect does not belong to this campaign")
            if prospect["platform"] != "youtube" or prospect["suppressed_at"] is not None:
                raise ValueError("Only unsuppressed YouTube prospects can be researched")
            prospects = [fetch_youtube_prospect(
                settings.youtube_api_key, campaign, prospect,
                checkpoint=lambda: _check_interrupted(interrupt),
            )]
            _check_interrupted(interrupt)
            database.save_prospect_research(
                prospect_id, prospects[0], expected_profile_url=prospect["profile_url"],
                expected_campaign_id=campaign_id,
            )
            saved = {"new": 0, "updated": 1}
        else:
            selection_stats: dict[str, int] = {}
            prospects = fetch_youtube_creators(
                settings.youtube_api_key, campaign, selection_stats=selection_stats,
                reserve_search_request=lambda: database.reserve_youtube_search(
                    UUID(str(task["id"])),
                ),
                checkpoint=lambda: _check_interrupted(interrupt),
            )
            _check_interrupted(interrupt)
            saved = database.save_discovered_prospects(
                campaign_id, prospects, selection_stats=selection_stats,
                expected_campaign_updated_at=campaign["updated_at"],
            )
        candidates = sum(
            len(item.get("intelligence", {}).get("contact_candidates", []))
            for item in prospects
        )
        return {
            "handler": "marketing.creator_discovery",
            "campaign_id": str(campaign_id),
            "queries": 0 if payload.get("prospect_id") else len(campaign["discovery_queries"]),
            "discovered": len(prospects),
            "new": saved["new"],
            "updated": saved["updated"],
            "contact_emails_discovered": candidates,
            "contact_candidates_unreviewed": candidates,
            "research_complete": sum(
                item.get("intelligence", {}).get("enrichment_status") == "complete"
                for item in prospects
            ),
            "contact_authorizations_granted": 0,
        }

    profile_id = UUID(str(payload["profile_id"]))

    if task["kind"] == "career.search":
        profile = database.get_profile(profile_id, include_resume=True)
        source_config = profile["source_config"]
        fetched: list[dict[str, object]] = []
        source_errors: list[str] = []
        source_coverage: list[dict[str, Any]] = []
        sources_attempted = 0
        sources_succeeded = 0

        if source_config.get("remotive"):
            source_budget = CareerAutopilotStore(settings.database_url)
            if source_budget.reserve_source_request("remotive"):
                sources_attempted += 1
                try:
                    fetched.extend(fetch_remotive())
                    sources_succeeded += 1
                except Exception as exc:
                    source_errors.append(f"remotive: {type(exc).__name__}")
            else:
                source_errors.append("remotive: global public API request budget respected")

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
        for board in source_config.get("lever_eu_boards", []):
            _check_interrupted(interrupt)
            sources_attempted += 1
            try:
                fetched.extend(fetch_lever(board, region="eu"))
                sources_succeeded += 1
            except Exception as exc:
                source_errors.append(f"lever-eu/{board}: {type(exc).__name__}")
        for board in source_config.get("smartrecruiters_boards", []):
            _check_interrupted(interrupt)
            sources_attempted += 1
            coverage: dict[str, Any] = {}
            try:
                fetched.extend(fetch_smartrecruiters(
                    board, max_age_hours=profile.get("max_age_hours", 168),
                    checkpoint=lambda: _check_interrupted(interrupt), coverage=coverage,
                    country=smartrecruiters_country_hint(profile.get("locations", [])),
                    search_titles=profile.get("desired_titles", []),
                ))
                sources_succeeded += 1
                source_coverage.append(coverage)
            except Exception as exc:
                _check_interrupted(interrupt)
                source_errors.append(f"smartrecruiters/{board}: {type(exc).__name__}")

        yc_detail_budget = 20
        for company in source_config.get("yc_companies", []):
            _check_interrupted(interrupt)
            sources_attempted += 1
            coverage = {}
            try:
                fetched.extend(fetch_yc(
                    company, max_age_hours=profile.get("max_age_hours", 72),
                    checkpoint=lambda: _check_interrupted(interrupt), coverage=coverage,
                    search_titles=profile.get("desired_titles", []),
                    detail_limit=min(10, yc_detail_budget),
                ))
                sources_succeeded += 1
            except Exception as exc:
                _check_interrupted(interrupt)
                source_errors.append(f"yc/{company}: {type(exc).__name__}")
            finally:
                yc_detail_budget = max(
                    0, yc_detail_budget - int(coverage.get("details_fetched") or 0),
                )
                if coverage:
                    source_coverage.append(coverage)

        if sources_attempted == 0:
            raise ValueError("Career profile has no enabled job sources")
        if sources_succeeded == 0:
            raise RuntimeError("Every configured job source failed")

        matches = []
        filter_counts = dict.fromkeys(FILTER_REASONS, 0)
        filter_counts["matched"] = 0
        matching_time = datetime.now(UTC)
        for job in fetched:
            _check_interrupted(interrupt)
            report = diagnose_opportunity(job, profile, now=matching_time)
            if report["filter_reason"]:
                filter_counts[report["filter_reason"]] += 1
                continue
            scored = score_opportunity(job, profile, now=matching_time)
            if scored is not None:
                matches.append(scored)
                filter_counts["matched"] += 1
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
            "sources_attempted": sources_attempted,
            "scoring_version": SCORING_POLICY_VERSION,
            "filter_counts": filter_counts,
            "diagnostics_scope": "normalized_source_records",
            "model_calls": 0,
            "fetched": len(fetched),
            "matched": len(matches),
            "new": save_result["new"],
            "updated": save_result["updated"],
            "auto_prepared": auto_prepared,
            "source_warnings": source_errors,
            "source_coverage": source_coverage,
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
        selected_route: str | None = None

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
                            content = parse_application_draft(
                                remote.content, context, preserve_invalid_grounding=True,
                            )
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
                        selected_route = remote.selected_route
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
        from app.career_application_quality import assess_application_quality

        # This report is derived by the worker, never accepted from model output.
        content["quality_report"] = assess_application_quality(context, content)
        before_codes = {item["code"] for item in content["quality_report"]["findings"]}
        repair_calls = 0
        repair_status = "not_needed"
        # A rewrite cannot fix the source itself. Spend at most one additional
        # invocation on issues the draft can correct, reserving its ledger row
        # before any model request and retaining the reviewable original on failure.
        if before_codes - {"posting_integrity_review", "resume_missing"}:
            _check_interrupted(interrupt)
            repair_provider = "openrouter" if selected_route is not None else "ollama"
            repair_models = (selected_route,) if selected_route else (settings.local_model,)
            repair_id = database.start_inference_invocation(
                task_id=task_id,
                purpose="career.application_draft.repair",
                provider=repair_provider,
                requested_models=repair_models,
                privacy_mode=(openrouter_client.privacy_mode
                              if selected_route and openrouter_client else "local_only"),
                daily_limit=plan.daily_limit if selected_route else None,
            )
            if repair_id is None:
                repair_status = "daily_cap"
            else:
                repair_calls = 1
                repair_started = time.monotonic()
                try:
                    _check_interrupted(interrupt)
                    if selected_route and openrouter_client:
                        # Reuse the already reviewed free route. A quality repair
                        # does not fan out, rerank providers or silently use a paid route.
                        repair_plan = OpenRouterPlan(
                            models=(selected_route,), daily_limit=plan.daily_limit,
                            free_tier=plan.free_tier,
                        )
                        repaired_remote = openrouter_client.complete(
                            application_draft_messages(context, correction=content), repair_plan,
                        )
                        repaired = parse_application_draft(
                            repaired_remote.content, context, preserve_invalid_grounding=True,
                        )
                        repair_usage = {
                            "selected_model": repaired_remote.selected_model,
                            "selected_provider": repaired_remote.selected_provider,
                            "prompt_tokens": repaired_remote.prompt_tokens,
                            "completion_tokens": repaired_remote.completion_tokens,
                            "total_tokens": repaired_remote.total_tokens,
                            "cost": repaired_remote.cost,
                            "latency_ms": repaired_remote.latency_ms,
                            "fallback_attempt": repaired_remote.fallback_attempt,
                        }
                    else:
                        repaired, usage = generate_application_draft_with_usage(
                            context, settings.local_model, correction=content,
                        )
                        repair_usage = {
                            "selected_model": settings.local_model,
                            "selected_provider": "ollama", **usage, "cost": 0,
                            "latency_ms": round((time.monotonic() - repair_started) * 1000),
                            "fallback_attempt": 1,
                        }
                    _check_interrupted(interrupt)
                    repaired["quality_report"] = assess_application_quality(context, repaired)
                    after_codes = {item["code"] for item in repaired["quality_report"]["findings"]}
                except OpenRouterError as exc:
                    database.fail_inference_invocation(repair_id, exc.code)
                    repair_status = "route_unavailable"
                except (ValueError, RuntimeError) as exc:
                    # Cancellation/lease loss still propagates and must never
                    # save a draft or trigger an action after an interrupted call.
                    if isinstance(exc, TaskInterruptedError):
                        database.fail_inference_invocation(repair_id, "TASK_INTERRUPTED")
                        raise
                    database.fail_inference_invocation(
                        repair_id, "APPLICATION_DRAFT_REPAIR_INVALID",
                    )
                    repair_status = "invalid"
                else:
                    database.complete_inference_invocation(repair_id, **repair_usage)
                    if not after_codes or after_codes < before_codes:
                        content = repaired
                        selected_model = repair_usage["selected_model"]
                        selected_provider = repair_usage["selected_provider"] or repair_provider
                        repair_status = "improved"
                    else:
                        repair_status = "still_requires_review"
        elif before_codes:
            repair_status = "source_review_required"
        content["quality_repair"] = {
            "model_calls": repair_calls, "status": repair_status,
            "initial_findings": sorted(before_codes),
        }
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
            "quality_disposition": content["quality_report"]["disposition"],
            "quality_model_calls": 0,
            "quality_repair_model_calls": repair_calls,
            "quality_repair_status": repair_status,
            "automatic_approval_task_created": auto_action is not None,
        }

    raise ValueError("Capability is not implemented in career worker")


def _schedule_due_work(database: MarketingStore) -> None:
    autopilot = CareerAutopilotStore(
        settings.database_url, email_pacing_policy=settings.email_pacing_policy(),
    )
    creators = CreatorAutomationStore(settings.database_url)
    for scope, schedule in (
        ("autopilot", lambda: autopilot.reconcile(
            sender=(settings.career_email_sender
                    if settings.career_email_transport != "disabled" else ""),
        )),
        ("career-replies", autopilot.schedule_mail_sync if settings.gmail_enabled else lambda: []),
        ("career", database.schedule_due_profiles),
        ("marketing", database.schedule_due_campaigns),
        ("creator-automation", lambda: creators.schedule(
            gmail_enabled=settings.creator_gmail_enabled,
        )),
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
    next_contact_history_cleanup = 0.0
    logger.info("career worker started", extra={"action": "startup"})

    while not stopping:
        if time.monotonic() >= next_contact_history_cleanup:
            try:
                trimmed = database.expire_creator_contact_history()
                delay = 30 if trimmed == 250 else 3600
            except Exception as error:
                logger.error(
                    "creator contact history cleanup deferred",
                    extra={"action": "marketing.history_cleanup_failed",
                           "error_type": type(error).__name__},
                )
                delay = 60
            next_contact_history_cleanup = time.monotonic() + delay
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
