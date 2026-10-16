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


class CreatorReplyReview(CreatorAutomationActor):
    prospect_id: UUID | None = None
    classification: Literal[
        "interested", "question", "declined_unpaid", "do_not_contact", "bounced", "ignore"
    ]
    note: str = Field(default="", max_length=3000)
    feedback_tags: list[CreatorFeedbackTag] = Field(default_factory=list, max_length=8)

    @field_validator("feedback_tags")
    @classmethod
    def unique_feedback_tags(cls, tags: list[CreatorFeedbackTag]) -> list[CreatorFeedbackTag]:
        return list(dict.fromkeys(tags))
