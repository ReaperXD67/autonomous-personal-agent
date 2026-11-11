from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.marketing_models import CreatorFeedbackTag


class CreatorAutomationStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1, max_length=120)
    max_initials_per_day: int = Field(default=3, ge=1, le=10)
    expires_in_hours: int = Field(default=24, ge=1, le=168)
    auto_handoff: bool = False


class CreatorAutomationActor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1, max_length=120)


class CreatorOutreachStop(CreatorAutomationActor):
    reason: str = Field(default="Creator mailing stopped by owner", min_length=1, max_length=1000)


class CreatorOutreachResume(CreatorAutomationActor):
    confirmation: Literal["start mailing now"]


class CreatorReplyDeferralCreate(CreatorAutomationActor):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    idempotency_key: UUID
    body_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prospect_ids: list[UUID] = Field(min_length=1, max_length=3)
    expires_in_hours: int = Field(default=24, ge=1, le=24, strict=True)
    reason: str = Field(min_length=10, max_length=1000)
    confirmation: Literal["defer this reply for reviewed new initials"]

    @field_validator("prospect_ids")
    @classmethod
    def distinct_prospects(cls, values):
        if len(values) != len(set(values)) or UUID(int=0) in values:
            raise ValueError("Select one to three distinct saved creator IDs")
        return values


class CreatorReplyReview(CreatorAutomationActor):
    prospect_id: UUID | None = None
    classification: Literal[
        "interested", "question", "declined_unpaid", "do_not_contact", "bounced", "ignore"
    ]
    note: str = Field(default="", max_length=3000)
    feedback_tags: list[CreatorFeedbackTag] = Field(default_factory=list, max_length=8)
    body_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("feedback_tags")
    @classmethod
    def unique_feedback_tags(cls, tags: list[CreatorFeedbackTag]) -> list[CreatorFeedbackTag]:
        return list(dict.fromkeys(tags))
