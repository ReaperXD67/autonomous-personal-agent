from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import require_api_token
from app.creator_pilot_store import CreatorPilotCreate
from app.marketing_models import MarketingProspectView
from app.marketing_store import (
    MarketingCampaignNotFoundError,
    MarketingOutreachError,
    MarketingProspectNotFoundError,
)
from app.models import TaskView

router = APIRouter(prefix="/v1/marketing", dependencies=[Depends(require_api_token)])


@router.post("/campaigns/{campaign_id}/pilot-research", response_model=TaskView, status_code=201)
def create_pilot(request: Request, campaign_id: UUID, payload: CreatorPilotCreate):
    try:
        return request.app.state.creator_pilot.create_pilot(campaign_id, payload)
    except MarketingCampaignNotFoundError as exc:
        raise HTTPException(404, "Campaign not found") from exc
    except MarketingOutreachError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/campaigns/{campaign_id}/pilot-research", response_model=TaskView | None)
def latest_pilot(request: Request, campaign_id: UUID):
    try:
        return request.app.state.creator_pilot.latest_pilot(campaign_id)
    except MarketingCampaignNotFoundError as exc:
        raise HTTPException(404, "Campaign not found") from exc


@router.get("/prospects/{prospect_id}", response_model=MarketingProspectView)
def get_prospect(request: Request, prospect_id: UUID):
    try:
        return request.app.state.marketing.get_prospect(prospect_id)
    except MarketingProspectNotFoundError as exc:
        raise HTTPException(404, "Creator not found") from exc
