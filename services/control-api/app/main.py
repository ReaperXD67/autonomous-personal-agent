from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import redis
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse

from app.auth import require_api_token
from app.logging_config import configure_logging
from app.models import ApprovalDecision, TaskCancellation, TaskCreate, TaskView
from app.settings import get_settings
from app.store import Database, InvalidTaskStateError, TaskNotFoundError

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("control-api")


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.database = Database(settings.database_url)
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
