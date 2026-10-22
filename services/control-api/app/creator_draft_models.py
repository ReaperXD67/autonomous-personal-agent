from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreatorDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1, max_length=120)
    idempotency_key: UUID


class CreatorDraftPrepare(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1, max_length=120)
    draft_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    approval_window_minutes: int = Field(default=1440, ge=5, le=1440)


class CreatorModelCopy(BaseModel):
    """Copy suggestions only: the model cannot select recipients, terms or actions."""

    model_config = ConfigDict(extra="forbid", strict=True)
    hook: str = Field(min_length=30, max_length=400)
    content_idea: str = Field(min_length=40, max_length=650)
    rationale: str = Field(min_length=30, max_length=600)
    evidence_ids: list[Literal["sample_video"]] = Field(min_length=1, max_length=1)
    reach_strategy: Literal["small_pilot", "format_choice", "unknown_reach"]

    @field_validator("hook", "content_idea", "rationale", mode="before")
    @classmethod
    def plain_paragraph(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Model copy must contain plain single paragraphs")
        return " ".join(value.split())


class CreatorDraftView(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: UUID
    campaign_id: UUID
    prospect_id: UUID
    task_id: UUID
    status: str
    task_status: str
    source: str | None
    selected_model: str | None
    error_code: str | None
    subject: str | None
    body: str | None
    draft_digest: str | None
    copy_content: dict[str, Any] | None = Field(alias="model_copy")
    evidence: list[dict[str, Any]]
    learning_summary: dict[str, Any]
    quality_notes: list[str]
    created_at: datetime
    expires_at: datetime
    action_id: UUID | None
