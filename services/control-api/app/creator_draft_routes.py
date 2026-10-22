from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.action_models import ExternalActionView
from app.auth import require_api_token
from app.creator_draft_models import CreatorDraftCreate, CreatorDraftPrepare, CreatorDraftView
from app.creator_draft_store import CreatorDraftNotFoundError, CreatorDraftStore
from app.marketing_models import MarketingEmailPlanCreate
from app.marketing_store import MarketingOutreachError, MarketingProspectNotFoundError
from app.settings import get_settings

router = APIRouter(prefix="/v1/marketing", dependencies=[Depends(require_api_token)])


def _store(request: Request) -> CreatorDraftStore:
    return request.app.state.creator_drafts


@router.post("/prospects/{prospect_id}/drafts", response_model=CreatorDraftView, status_code=201)
def create_draft(request: Request, prospect_id: UUID, payload: CreatorDraftCreate):
    try:
        return _store(request).create_draft(prospect_id, payload)
    except MarketingProspectNotFoundError as exc:
        raise HTTPException(404, "Creator not found") from exc
    except MarketingOutreachError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/prospects/{prospect_id}/drafts", response_model=list[CreatorDraftView])
def list_drafts(request: Request, prospect_id: UUID):
    try:
        return _store(request).list_drafts(prospect_id)
    except MarketingProspectNotFoundError as exc:
        raise HTTPException(404, "Creator not found") from exc


@router.get("/drafts/{draft_id}", response_model=CreatorDraftView)
def get_draft(request: Request, draft_id: UUID):
    try:
        return _store(request).get_draft(draft_id)
    except CreatorDraftNotFoundError as exc:
        raise HTTPException(404, "Creator draft not found") from exc


@router.post("/drafts/{draft_id}/prepare", response_model=ExternalActionView)
def prepare_draft(request: Request, draft_id: UUID, payload: CreatorDraftPrepare):
    runtime = get_settings()
    if runtime.mail_transport == "disabled" or not runtime.smtp_from:
        raise HTTPException(409, "Configure the email sender before preparing an exact packet")
    try:
        row = _store(request).get_draft(draft_id)
        return _store(request).plan_outreach_email(
            row["prospect_id"], MarketingEmailPlanCreate(
                stage="initial", actor=payload.actor,
                approval_window_minutes=payload.approval_window_minutes,
                ai_draft_id=draft_id, ai_draft_digest=payload.draft_digest,
            ), sender=runtime.smtp_from,
        )
    except (CreatorDraftNotFoundError, MarketingProspectNotFoundError) as exc:
        raise HTTPException(404, "Creator draft not found") from exc
    except MarketingOutreachError as exc:
        raise HTTPException(409, str(exc)) from exc
