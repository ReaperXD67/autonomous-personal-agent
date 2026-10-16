from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import require_api_token
from app.creator_automation_models import (
    CreatorAutomationActor,
    CreatorAutomationStart,
    CreatorReplyReview,
)
from app.marketing_store import MarketingCampaignNotFoundError, MarketingOutreachError
from app.settings import get_settings

router = APIRouter(prefix="/v1/marketing", dependencies=[Depends(require_api_token)])


def _http_error(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=404 if isinstance(exc, MarketingCampaignNotFoundError) else 409, detail=str(exc)
    )


@router.get("/campaigns/{campaign_id}/automation")
def overview(request: Request, campaign_id: UUID) -> dict[str, Any]:
    settings = get_settings()
    try:
        result = request.app.state.creator_automation.overview(campaign_id)
    except MarketingCampaignNotFoundError as exc:
        raise _http_error(exc) from exc
    return {
        **result,
        "readiness": {
            "gmail_configured": settings.creator_gmail_enabled,
            "smtp_configured": settings.mail_transport != "disabled",
        },
    }


@router.post("/campaigns/{campaign_id}/automation/start", status_code=201)
def start(request: Request, campaign_id: UUID, payload: CreatorAutomationStart) -> dict[str, Any]:
    settings = get_settings()
    try:
        if settings.mail_transport == "disabled":
            raise MarketingOutreachError(
                "Connect an SMTP sender before authorizing creator outreach"
            )
        return request.app.state.creator_automation.start(
            campaign_id,
            payload,
            monitor_gmail=settings.creator_gmail_enabled,
        )
    except (MarketingCampaignNotFoundError, MarketingOutreachError) as exc:
        raise _http_error(exc) from exc


@router.post("/campaigns/{campaign_id}/automation/pause")
def pause(request: Request, campaign_id: UUID, payload: CreatorAutomationActor) -> dict[str, bool]:
    try:
        return request.app.state.creator_automation.pause(campaign_id, payload.actor)
    except MarketingCampaignNotFoundError as exc:
        raise _http_error(exc) from exc


@router.post("/campaigns/{campaign_id}/replies/sync", status_code=202)
def sync(request: Request, campaign_id: UUID, payload: CreatorAutomationActor) -> dict[str, Any]:
    try:
        if not get_settings().creator_gmail_enabled:
            raise MarketingOutreachError("Configure the read-only creator Gmail adapter first")
        return request.app.state.creator_automation.queue_reply_sync(campaign_id, payload.actor)
    except (MarketingCampaignNotFoundError, MarketingOutreachError) as exc:
        raise _http_error(exc) from exc


@router.post("/campaigns/{campaign_id}/replies/{reply_id}/review")
def review(
    request: Request, campaign_id: UUID, reply_id: UUID, payload: CreatorReplyReview
) -> dict[str, Any]:
    try:
        return request.app.state.creator_automation.review_reply(campaign_id, reply_id, payload)
    except MarketingOutreachError as exc:
        raise _http_error(exc) from exc
