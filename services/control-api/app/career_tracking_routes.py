from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.auth import require_api_token
from app.career_store import CareerProfileNotFoundError, OpportunityNotFoundError
from app.career_tracking_models import CareerEventCreate
from app.career_tracking_store import CareerTrackingConflictError, CareerTrackingStore
from app.models import TaskCreate, TaskView
from app.settings import get_settings

router = APIRouter(prefix="/v1/career", dependencies=[Depends(require_api_token)])


def _store(request: Request) -> CareerTrackingStore:
    return request.app.state.career_tracking


@router.get("/tracking")
def tracking(request: Request, profile_id: UUID | None = None,
             limit: int = Query(default=100, ge=1, le=250)) -> dict[str, Any]:
    try:
        return _store(request).tracking(profile_id=profile_id, limit=limit)
    except CareerProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Career profile not found") from exc


@router.post("/opportunities/{opportunity_id}/events", status_code=status.HTTP_201_CREATED)
def record_event(request: Request, opportunity_id: UUID,
                 payload: CareerEventCreate) -> dict[str, Any]:
    try:
        return _store(request).record_application_event(opportunity_id, payload)
    except OpportunityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Career opportunity not found") from exc
    except CareerTrackingConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/profiles/{profile_id}/mail-sync", response_model=TaskView,
             status_code=status.HTTP_201_CREATED)
def sync_mail(request: Request, profile_id: UUID) -> dict[str, Any]:
    if not get_settings().gmail_enabled:
        raise HTTPException(status_code=409, detail="Configure Gmail tracking before syncing")
    try:
        _store(request).get_profile(profile_id)
    except CareerProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Career profile not found") from exc
    return request.app.state.database.create_task(TaskCreate(
        title="Read career-labelled Gmail application replies", kind="career.gmail_sync",
        payload={"profile_id": str(profile_id), "trigger": "manual"},
        requested_by="dashboard:career", idempotency_key=f"career-gmail:{profile_id}:{uuid4()}",
    ))
