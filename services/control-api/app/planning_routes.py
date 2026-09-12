from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.auth import require_api_token
from app.planning_models import PlanAdopt, PlanCreate, PlanView
from app.planning_store import PlanConflictError, PlanContextError, PlanningStore, PlanNotFoundError
from app.workflow_models import WorkflowView

router = APIRouter(prefix="/v1/plans", dependencies=[Depends(require_api_token)])


def _store(request: Request) -> PlanningStore:
    return request.app.state.planning


@router.post("", response_model=PlanView, status_code=status.HTTP_201_CREATED)
def create_plan(request: Request, payload: PlanCreate):
    try:
        return _store(request).create_plan(payload)
    except PlanConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PlanContextError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[PlanView])
def list_plans(request: Request, limit: int = Query(default=50, ge=1, le=100)):
    return _store(request).list_plans(limit)


@router.get("/{plan_id}", response_model=PlanView)
def get_plan(request: Request, plan_id: UUID):
    try:
        return _store(request).get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Goal proposal not found") from exc


@router.post("/{plan_id}/adopt", response_model=WorkflowView)
def adopt_plan(request: Request, plan_id: UUID, payload: PlanAdopt):
    try:
        return _store(request).adopt_plan(plan_id, payload)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Goal proposal not found") from exc
    except (PlanConflictError, PlanContextError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
