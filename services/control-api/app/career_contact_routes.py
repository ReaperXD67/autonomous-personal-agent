from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.action_store import ActionPreparationError
from app.auth import require_api_token
from app.career_contact_models import (
    CareerContactCreate,
    CareerContactEmailPlan,
    CareerContactRevoke,
)
from app.career_contact_store import CareerContactNotFoundError
from app.career_store import OpportunityNotFoundError
from app.settings import get_settings

router = APIRouter(prefix="/v1/career", dependencies=[Depends(require_api_token)])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, OpportunityNotFoundError):
        return HTTPException(status_code=404, detail="Career opportunity not found")
    if isinstance(exc, CareerContactNotFoundError):
        return HTTPException(status_code=404, detail="Career contact not found")
    return HTTPException(status_code=409, detail=str(exc))


@router.get("/opportunities/{opportunity_id}/contacts")
def contacts(request: Request, opportunity_id: UUID) -> list[dict[str, Any]]:
    try:
        return request.app.state.career_contacts.list_contacts(opportunity_id)
    except OpportunityNotFoundError as exc:
        raise _http_error(exc) from exc


@router.post("/opportunities/{opportunity_id}/contacts", status_code=201)
def review_contact(request: Request, opportunity_id: UUID,
                   payload: CareerContactCreate) -> dict[str, Any]:
    try:
        return request.app.state.career_contacts.review_contact(opportunity_id, payload)
    except (OpportunityNotFoundError, ActionPreparationError) as exc:
        raise _http_error(exc) from exc


@router.post("/contacts/{contact_id}/email-plan", status_code=201)
def email_plan(request: Request, contact_id: UUID,
               payload: CareerContactEmailPlan) -> dict[str, Any]:
    settings = get_settings()
    if settings.mail_transport == "disabled" or not settings.smtp_from:
        raise HTTPException(status_code=409, detail="Connect the career SMTP sender first")
    try:
        return request.app.state.career_contacts.prepare_contact_email(
            contact_id, payload, sender=settings.smtp_from,
        )
    except (CareerContactNotFoundError, OpportunityNotFoundError, ActionPreparationError) as exc:
        raise _http_error(exc) from exc


@router.post("/contacts/{contact_id}/revoke")
def revoke_contact(request: Request, contact_id: UUID,
                   payload: CareerContactRevoke) -> dict[str, Any]:
    try:
        return request.app.state.career_contacts.revoke_contact(contact_id, payload.actor)
    except CareerContactNotFoundError as exc:
        raise _http_error(exc) from exc
