from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import redis
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.responses import Response as FastAPIResponse

from app.action_models import (
    ApplicationPlanCreate,
    EmailActionCreate,
    ExternalActionView,
)
from app.action_store import ActionPreparationError, ActionStore
from app.auth import require_api_token
from app.career_models import (
    AuditEventView,
    CareerProfileCreate,
    CareerProfileUpdate,
    CareerProfileView,
    OpportunityStateUpdate,
    OpportunityView,
)
from app.career_store import (
    CareerProfileNotFoundError,
    CareerStore,
    OpportunityNotFoundError,
)
from app.logging_config import configure_logging
from app.models import ApprovalDecision, TaskCancellation, TaskCreate, TaskView
from app.policy import RiskLevel
from app.settings import get_settings
from app.store import Database, InvalidTaskStateError, TaskNotFoundError

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("control-api")
dashboard_html = (Path(__file__).parent / "web" / "index.html").read_text(encoding="utf-8")
dashboard_css = (Path(__file__).parent / "web" / "app.css").read_text(encoding="utf-8")
dashboard_javascript = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.database = Database(settings.database_url)
    application.state.career = CareerStore(settings.database_url)
    application.state.actions = ActionStore(settings.database_url)
    application.state.redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("control plane starting", extra={"action": "startup"})
    yield
    application.state.redis.close()
    logger.info("control plane stopped", extra={"action": "shutdown"})


app = FastAPI(
    title="Autonomous Personal Agent Control Plane",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


def _correlation_id(value: str | None) -> UUID:
    try:
        return UUID(value) if value else uuid4()
    except ValueError:
        return uuid4()


@app.middleware("http")
async def request_context(request: Request, call_next):
    started = time.perf_counter()
    correlation_id = _correlation_id(request.headers.get("x-correlation-id"))
    request.state.correlation_id = correlation_id
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "unhandled request failure",
            extra={"correlation_id": str(correlation_id), "action": request.url.path},
        )
        raise
    response.headers["x-correlation-id"] = str(correlation_id)
    response.headers["x-content-type-options"] = "nosniff"
    response.headers["x-frame-options"] = "DENY"
    response.headers["referrer-policy"] = "no-referrer"
    response.headers["permissions-policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["content-security-policy"] = (
        "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'none'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'"
    )
    logger.info(
        "request completed",
        extra={
            "correlation_id": str(correlation_id),
            "action": f"{request.method} {request.url.path}",
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return response


def _database(request: Request) -> Database:
    return request.app.state.database


def _redis(request: Request) -> redis.Redis:
    return request.app.state.redis


def _career(request: Request) -> CareerStore:
    return request.app.state.career


def _actions(request: Request) -> ActionStore:
    return request.app.state.actions


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> str:
    return dashboard_html


@app.get("/assets/app.css", include_in_schema=False)
def dashboard_styles() -> FastAPIResponse:
    return FastAPIResponse(content=dashboard_css, media_type="text/css")


@app.get("/assets/app.js", include_in_schema=False)
def dashboard_script() -> FastAPIResponse:
    return FastAPIResponse(content=dashboard_javascript, media_type="text/javascript")


@app.get("/favicon.ico", include_in_schema=False, status_code=status.HTTP_204_NO_CONTENT)
def dashboard_favicon() -> None:
    return None


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready")
def ready(request: Request, response: Response) -> dict[str, Any]:
    checks: dict[str, bool] = {"postgres": False, "redis": False}
    try:
        checks["postgres"] = _database(request).check()
    except Exception:
        logger.warning("postgres readiness failed", extra={"action": "readiness"})
    try:
        checks["redis"] = bool(_redis(request).ping())
    except Exception:
        logger.warning("redis readiness failed", extra={"action": "readiness"})
    is_ready = all(checks.values())
    response.status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if is_ready else "not_ready", "checks": checks}


@app.get("/v1/system/status", dependencies=[Depends(require_api_token)])
def system_status(request: Request) -> dict[str, Any]:
    return {
        "service": "control-api",
        "version": "0.1.0",
        "environment": settings.environment,
        "task_counts": _database(request).status_counts(),
        "queue_depth": _redis(request).llen(settings.task_queue_key),
        "job_queue_depth": _redis(request).llen(settings.job_queue_key),
        "action_queue_depth": _redis(request).llen(settings.action_queue_key),
    }


@app.get("/metrics", response_class=PlainTextResponse, dependencies=[Depends(require_api_token)])
def metrics(request: Request) -> str:
    counts = _database(request).status_counts()
    lines = [
        "# HELP autonomous_agent_info Static service information.",
        "# TYPE autonomous_agent_info gauge",
        'autonomous_agent_info{service="control-api",version="0.1.0"} 1',
        "# HELP autonomous_agent_queue_depth Ready task queue depth.",
        "# TYPE autonomous_agent_queue_depth gauge",
        f"autonomous_agent_queue_depth {_redis(request).llen(settings.task_queue_key)}",
        "# HELP autonomous_agent_job_queue_depth Ready career-task queue depth.",
        "# TYPE autonomous_agent_job_queue_depth gauge",
        f"autonomous_agent_job_queue_depth {_redis(request).llen(settings.job_queue_key)}",
        "# HELP autonomous_agent_action_queue_depth Ready external-action queue depth.",
        "# TYPE autonomous_agent_action_queue_depth gauge",
        f"autonomous_agent_action_queue_depth {_redis(request).llen(settings.action_queue_key)}",
        "# HELP autonomous_agent_tasks_total Tasks by current status.",
        "# TYPE autonomous_agent_tasks_total gauge",
    ]
    lines.extend(
        f'autonomous_agent_tasks_total{{status="{task_status}"}} {count}'
        for task_status, count in sorted(counts.items())
    )
    return "\n".join(lines) + "\n"


@app.post(
    "/v1/tasks",
    response_model=TaskView,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_token)],
)
def create_task(request: Request, payload: TaskCreate) -> dict[str, Any]:
    return _database(request).create_task(payload)


@app.get(
    "/v1/tasks",
    response_model=list[TaskView],
    dependencies=[Depends(require_api_token)],
)
def list_tasks(
    request: Request,
    task_status: str | None = Query(default=None, alias="status", max_length=30),
    kind_prefix: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict[str, Any]]:
    return _database(request).list_tasks(
        task_status=task_status, kind_prefix=kind_prefix, limit=limit
    )


@app.get(
    "/v1/audit-events",
    response_model=list[AuditEventView],
    dependencies=[Depends(require_api_token)],
)
def list_audit_events(
    request: Request,
    task_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict[str, Any]]:
    return _database(request).list_audit_events(task_id=task_id, limit=limit)


@app.post(
    "/v1/career/profiles",
    response_model=CareerProfileView,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_token)],
)
def create_career_profile(
    request: Request, payload: CareerProfileCreate
) -> dict[str, Any]:
    return _career(request).create_profile(payload)


@app.get(
    "/v1/career/profiles",
    response_model=list[CareerProfileView],
    dependencies=[Depends(require_api_token)],
)
def list_career_profiles(request: Request) -> list[dict[str, Any]]:
    return _career(request).list_profiles()


@app.put(
    "/v1/career/profiles/{profile_id}",
    response_model=CareerProfileView,
    dependencies=[Depends(require_api_token)],
)
def update_career_profile(
    request: Request, profile_id: UUID, payload: CareerProfileUpdate
) -> dict[str, Any]:
    try:
        return _career(request).update_profile(profile_id, payload)
    except CareerProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Career profile not found") from exc


@app.post(
    "/v1/career/profiles/{profile_id}/scan",
    response_model=TaskView,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_token)],
)
def scan_career_profile(request: Request, profile_id: UUID) -> dict[str, Any]:
    try:
        profile = _career(request).get_profile(profile_id)
    except CareerProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Career profile not found") from exc
    return _database(request).create_task(
        TaskCreate(
            title=f"Scan fresh jobs for {profile['name']}",
            kind="career.search",
            payload={"profile_id": str(profile_id), "trigger": "manual"},
            risk_level=RiskLevel.LOW,
            requested_by="dashboard:career",
            idempotency_key=f"career-manual-scan:{profile_id}:{uuid4()}",
        )
    )


@app.get(
    "/v1/career/opportunities",
    response_model=list[OpportunityView],
    dependencies=[Depends(require_api_token)],
)
def list_career_opportunities(
    request: Request,
    profile_id: UUID | None = None,
    opportunity_status: str | None = Query(default=None, alias="status", max_length=30),
    limit: int = Query(default=100, ge=1, le=300),
) -> list[dict[str, Any]]:
    return _career(request).list_opportunities(
        profile_id=profile_id, opportunity_status=opportunity_status, limit=limit
    )


@app.patch(
    "/v1/career/opportunities/{opportunity_id}",
    response_model=OpportunityView,
    dependencies=[Depends(require_api_token)],
)
def update_career_opportunity(
    request: Request, opportunity_id: UUID, payload: OpportunityStateUpdate
) -> dict[str, Any]:
    try:
        return _career(request).update_opportunity_state(opportunity_id, payload)
    except OpportunityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Opportunity not found") from exc


@app.post(
    "/v1/career/opportunities/{opportunity_id}/draft",
    response_model=TaskView,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_token)],
)
def draft_career_application(request: Request, opportunity_id: UUID) -> dict[str, Any]:
    try:
        opportunity = _career(request).get_opportunity(opportunity_id)
    except OpportunityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Opportunity not found") from exc
    return _database(request).create_task(
        TaskCreate(
            title=f"Prepare truthful application draft for {opportunity['title']}",
            kind="career.application_draft",
            payload={
                "profile_id": str(opportunity["profile_id"]),
                "opportunity_id": str(opportunity_id),
            },
            risk_level=RiskLevel.MEDIUM,
            requested_by="dashboard:career",
            idempotency_key=f"career-draft:{opportunity_id}:{uuid4()}",
        )
    )


@app.post(
    "/v1/career/opportunities/{opportunity_id}/preflight",
    response_model=TaskView,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_token)],
)
def preflight_career_application(request: Request, opportunity_id: UUID) -> dict[str, Any]:
    try:
        opportunity = _career(request).get_opportunity(opportunity_id)
    except OpportunityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Opportunity not found") from exc
    return _database(request).create_task(
        TaskCreate(
            title="Inspect an official application form",
            kind="career.application_preflight",
            payload={
                "profile_id": str(opportunity["profile_id"]),
                "opportunity_id": str(opportunity_id),
                "trigger": "manual",
            },
            risk_level=RiskLevel.MEDIUM,
            requested_by="dashboard:career",
            idempotency_key=f"career-preflight:{opportunity_id}:{uuid4()}",
        )
    )


@app.post(
    "/v1/career/opportunities/{opportunity_id}/submit-plan",
    response_model=ExternalActionView,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_token)],
)
def plan_career_application(
    request: Request, opportunity_id: UUID, payload: ApplicationPlanCreate
) -> dict[str, Any]:
    try:
        return _actions(request).create_application_action(opportunity_id, payload)
    except OpportunityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Opportunity not found") from exc
    except ActionPreparationError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "missing_fields": exc.missing_fields},
        ) from exc


@app.post(
    "/v1/external-actions/email",
    response_model=ExternalActionView,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_token)],
)
def plan_email_action(request: Request, payload: EmailActionCreate) -> dict[str, Any]:
    if settings.mail_transport == "disabled" or not settings.smtp_from:
        raise HTTPException(status_code=409, detail="Configure an email transport first")
    return _actions(request).create_email_action(payload, sender=settings.smtp_from)


@app.get(
    "/v1/external-actions",
    response_model=list[ExternalActionView],
    dependencies=[Depends(require_api_token)],
)
def list_external_actions(
    request: Request,
    action_status: str | None = Query(default=None, alias="status", max_length=40),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict[str, Any]]:
    return _actions(request).list_external_actions(
        action_status=action_status, limit=limit
    )


@app.get(
    "/v1/tasks/dead-letters",
    response_model=list[TaskView],
    dependencies=[Depends(require_api_token)],
)
def list_dead_letters(
    request: Request, limit: int = Query(default=50, ge=1, le=200)
) -> list[dict[str, Any]]:
    return _database(request).list_dead_letters(limit)


@app.get(
    "/v1/tasks/{task_id}",
    response_model=TaskView,
    dependencies=[Depends(require_api_token)],
)
def get_task(request: Request, task_id: UUID) -> dict[str, Any]:
    try:
        return _database(request).get_task(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@app.post(
    "/v1/tasks/{task_id}/cancel",
    response_model=TaskView,
    dependencies=[Depends(require_api_token)],
)
def cancel_task(
    request: Request,
    task_id: UUID,
    cancellation: TaskCancellation,
) -> dict[str, Any]:
    try:
        return _database(request).cancel_task(task_id, cancellation)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except InvalidTaskStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/v1/tasks/{task_id}/decision",
    response_model=TaskView,
    dependencies=[Depends(require_api_token)],
)
def decide_task(
    request: Request,
    task_id: UUID,
    decision: ApprovalDecision,
) -> dict[str, Any]:
    database = _database(request)
    try:
        task = database.decide_task(task_id, decision)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except InvalidTaskStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return task
