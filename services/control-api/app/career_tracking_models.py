from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TrackingStatus = Literal[
    "submitted", "acknowledgement", "recruiter_reply", "interview", "rejected",
    "offer", "withdrawn", "needs_review",
]
TRACKING_STATUSES = (
    "submitted", "acknowledgement", "recruiter_reply", "interview", "rejected",
    "offer", "withdrawn", "needs_review",
)


class CareerEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TrackingStatus
    note: str = Field(min_length=3, max_length=1000)
    actor: str = Field(min_length=1, max_length=120)
    occurred_at: datetime | None = None
    meeting_at: datetime | None = None
    gmail_message_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,128}$")

    @field_validator("note", "actor")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 3:
            raise ValueError("Provide a meaningful actor or review note")
        return cleaned

    @field_validator("occurred_at", "meeting_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Dates must include an explicit time zone")
        return value.astimezone(UTC) if value else None

    @model_validator(mode="after")
    def validate_dates(self) -> CareerEventCreate:
        if self.meeting_at is not None and self.status != "interview":
            raise ValueError("Only interview events may include a meeting time")
        if self.occurred_at and self.occurred_at > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("An observed event cannot occur in the future")
        return self
