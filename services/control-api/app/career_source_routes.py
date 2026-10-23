from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_api_token
from app.career_sources import CareerSourceResolve, ResolvedCareerSource, resolve_career_source

router = APIRouter(prefix="/v1/career/sources", dependencies=[Depends(require_api_token)])


@router.post("/resolve", response_model=ResolvedCareerSource)
def resolve_source(payload: CareerSourceResolve) -> ResolvedCareerSource:
    """A pure URL parser: no source request, profile mutation or application authority."""
    try:
        return resolve_career_source(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
