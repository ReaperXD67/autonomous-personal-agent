from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.auth import require_api_token
from app.creator_reply_draft_models import CreatorReplyDraftCreate, CreatorReplyDraftView
from app.marketing_store import MarketingOutreachError
from app.settings import get_settings

router = APIRouter(prefix="/v1/marketing", dependencies=[Depends(require_api_token)])


@router.post("/campaigns/{campaign_id}/replies/{reply_id}/draft",
             response_model=CreatorReplyDraftView, status_code=202)
def create_reply_draft(
    request: Request, response: Response, campaign_id: UUID, reply_id: UUID,
    payload: CreatorReplyDraftCreate,
):
    response.headers["Cache-Control"] = "no-store"
    if campaign_id not in get_settings().creator_reply_draft_campaign_ids:
        raise HTTPException(409, "Reply draft curation is not enabled for this campaign")
    try:
        result = request.app.state.creator_reply_drafts.queue_reply_draft(
            campaign_id, reply_id, payload,
        )
        return {key: value for key, value in result.items()
                if key not in {"subject", "body", "model_copy"}}
    except (MarketingOutreachError, ValueError) as exc:
        raise HTTPException(409, "Reply draft requires current complete unsuppressed evidence "
                            "and available preparation allowance") from exc


@router.get("/campaigns/{campaign_id}/replies/{reply_id}/drafts",
            response_model=list[CreatorReplyDraftView])
def list_reply_drafts(request: Request, response: Response, campaign_id: UUID, reply_id: UUID):
    response.headers["Cache-Control"] = "no-store"
    try:
        return request.app.state.creator_reply_drafts.list_reply_drafts(campaign_id, reply_id)
    except (MarketingOutreachError, ValueError) as exc:
        raise HTTPException(409, "Saved reply drafts are unavailable in this campaign") from exc


@router.post("/campaigns/{campaign_id}/replies/{reply_id}/drafts/{draft_id}/retry",
             response_model=CreatorReplyDraftView, status_code=202)
def retry_reply_draft(
    request: Request, response: Response, campaign_id: UUID, reply_id: UUID, draft_id: UUID,
    payload: CreatorReplyDraftCreate,
):
    response.headers["Cache-Control"] = "no-store"
    if campaign_id not in get_settings().creator_reply_draft_campaign_ids:
        raise HTTPException(409, "Reply draft curation is not enabled for this campaign")
    try:
        result = request.app.state.creator_reply_drafts.queue_reply_draft_retry(
            campaign_id, reply_id, draft_id, payload,
        )
        return {key: value for key, value in result.items()
                if key not in {"subject", "body", "model_copy"}}
    except (MarketingOutreachError, ValueError) as exc:
        raise HTTPException(409, "Recovery requires an eligible original local model failure, "
                            "current evidence, cooldown and preparation allowance") from exc
