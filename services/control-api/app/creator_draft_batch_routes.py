from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import require_api_token
from app.creator_draft_batch_store import (
    CreatorDraftBatchCreate,
    CreatorDraftBatchNotFoundError,
    CreatorDraftBatchView,
)
from app.marketing_store import MarketingCampaignNotFoundError, MarketingOutreachError

router = APIRouter(prefix="/v1/marketing", dependencies=[Depends(require_api_token)])


@router.post("/campaigns/{campaign_id}/draft-batches",
             response_model=CreatorDraftBatchView, status_code=201)
def create_batch(request: Request, campaign_id: UUID, payload: CreatorDraftBatchCreate):
    try:
        return request.app.state.creator_draft_batches.create_batch(campaign_id, payload)
    except MarketingCampaignNotFoundError as exc:
        raise HTTPException(404, "Campaign not found") from exc
    except MarketingOutreachError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/campaigns/{campaign_id}/draft-batches", response_model=CreatorDraftBatchView | None)
def latest_batch(request: Request, campaign_id: UUID):
    try:
        return request.app.state.creator_draft_batches.latest_batch(campaign_id)
    except MarketingCampaignNotFoundError as exc:
        raise HTTPException(404, "Campaign not found") from exc


@router.get("/draft-batches/{task_id}", response_model=CreatorDraftBatchView)
def get_batch(request: Request, task_id: UUID):
    try:
        return request.app.state.creator_draft_batches.get_batch(task_id)
    except CreatorDraftBatchNotFoundError as exc:
        raise HTTPException(404, "Creator draft batch not found") from exc
