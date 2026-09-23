from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.action_models import ApplicationIdentity
from app.action_store import ActionPreparationError
from app.auth import require_api_token
from app.career_autopilot_models import CareerPause, CareerPlay
from app.career_store import CareerProfileNotFoundError
from app.settings import get_settings

router = APIRouter(prefix="/v1/career", dependencies=[Depends(require_api_token)])
SOURCE_CATALOG = [
    {
        "id": "ashby",
        "name": "Ashby",
        "status": "supported",
        "description": "Configured employer boards; public posting dates and inspected forms.",
        "url": "https://jobs.ashbyhq.com/",
    },
    {
        "id": "lever",
        "name": "Lever",
        "status": "supported",
        "description": "Configured employer boards; public posting dates and inspected forms.",
        "url": "https://jobs.lever.co/",
    },
    {
        "id": "greenhouse",
        "name": "Greenhouse",
        "status": "research_only",
        "description": "Feed dates are updates; automatic applications need a posting date.",
        "url": "https://boards.greenhouse.io/",
    },
    {
        "id": "arbeitnow",
        "name": "Arbeitnow",
        "status": "supported",
        "description": "Public discovery; unsupported application destinations require review.",
        "url": "https://www.arbeitnow.com/",
    },
    {
        "id": "remotive",
        "name": "Remotive",
        "status": "supported",
        "description": "Optional remote feed, delayed 24 hours, with original listing attribution.",
        "url": "https://remotive.com/",
    },
    {
        "id": "yc",
        "name": "Y Combinator",
        "status": "import_required",
        "description": "Find a YC company, then add its Ashby, Lever or Greenhouse employer board.",
        "url": "https://www.ycombinator.com/jobs",
    },
    {
        "id": "linkedin",
        "name": "LinkedIn",
        "status": "import_required",
        "description": "Find employers with saved searches, then add supported employer boards.",
        "url": "https://www.linkedin.com/jobs/",
    },
    {
        "id": "discord",
        "name": "Discord",
        "status": "not_connected",
        "description": "Add employer boards from community leads. Discord is not connected.",
        "url": "https://discord.com/",
    },
]


@router.get("/autopilot")
def overview(request: Request, profile_id: UUID | None = None) -> dict[str, Any]:
    settings = get_settings()
    store = request.app.state.career_autopilot
    result = store.overview(profile_id)
    profiles = store.list_profiles()
    readiness = []
    for profile in profiles:
        if profile_id is not None and profile["id"] != profile_id:
            continue
        try:
            ApplicationIdentity.model_validate(profile["application_identity"])
            identity_complete = True
        except ValueError:
            identity_complete = False
        config = profile["source_config"]
        sources = bool(
            config.get("arbeitnow")
            or config.get("remotive")
            or any(config.get(key) for key in ("ashby_boards", "lever_boards", "greenhouse_boards"))
        )
        resume = profile["resume_present"]
        readiness.append(
            {
                "profile_id": profile["id"],
                "resume_present": resume,
                "identity_complete": identity_complete,
                "portfolio_present": bool(
                    (profile["application_identity"] or {}).get("portfolio_url")
                ),
                "sources_enabled": sources,
                "can_prepare": resume and sources,
                "can_apply": resume and sources and identity_complete,
                "gmail_configured": settings.gmail_enabled,
                "smtp_configured": settings.mail_transport != "disabled",
            }
        )
    return {**result, "readiness": readiness, "sources": SOURCE_CATALOG}


@router.post("/profiles/{profile_id}/play", status_code=201)
def play(request: Request, profile_id: UUID, payload: CareerPlay) -> dict[str, Any]:
    try:
        if payload.include_cold_email and get_settings().mail_transport == "disabled":
            raise ActionPreparationError("Connect an SMTP sender before enabling hiring emails")
        return request.app.state.career_autopilot.play(profile_id, payload)
    except CareerProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Career profile not found") from exc
    except ActionPreparationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/profiles/{profile_id}/pause")
def pause(request: Request, profile_id: UUID, payload: CareerPause) -> dict[str, bool]:
    try:
        return request.app.state.career_autopilot.pause(profile_id, payload.actor)
    except CareerProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Career profile not found") from exc
