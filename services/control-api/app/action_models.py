from __future__ import annotations

from datetime import datetime
from email.utils import parseaddr
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _valid_email(value: str) -> str:
    cleaned = value.strip()
    display, address = parseaddr(cleaned)
    if display or address != cleaned or len(cleaned) > 320:
        raise ValueError("Enter one plain email address without a display name")
    local, separator, domain = cleaned.rpartition("@")
    if not separator or not local or "." not in domain or any(char.isspace() for char in cleaned):
        raise ValueError("Enter a valid email address")
    return cleaned


def _optional_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())[:limit]
    return cleaned or None


class ApplicationIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    email: str
    phone: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=300)
    linkedin_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _valid_email(value)

    @field_validator("first_name", "last_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @field_validator("phone", "location")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        return _optional_text(value, 300)

    @field_validator("linkedin_url", "github_url")
    @classmethod
    def validate_profile_url(cls, value: str | None) -> str | None:
        cleaned = _optional_text(value, 500)
        if cleaned is None:
            return None
        if not cleaned.startswith("https://"):
            raise ValueError("Profile URLs must use https")
        return cleaned


class ApplicationPlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: dict[str, str | bool] = Field(default_factory=dict, max_length=100)
    actor: str = Field(min_length=1, max_length=120)
    approval_window_minutes: int = Field(default=60, ge=5, le=1440)

    @field_validator("answers")
    @classmethod
    def validate_answers(cls, answers: dict[str, str | bool]) -> dict[str, str | bool]:
        validated: dict[str, str | bool] = {}
        for key, value in answers.items():
            if not key or len(key) > 200:
                raise ValueError("Answer keys must be between 1 and 200 characters")
            if isinstance(value, str):
                value = value.strip()
                if len(value) > 4000:
                    raise ValueError("An application answer exceeded 4000 characters")
            validated[key] = value
        return validated


class EmailActionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient: str
    subject: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1, max_length=20000)
    actor: str = Field(min_length=1, max_length=120)
    opportunity_id: UUID | None = None
    approval_window_minutes: int = Field(default=60, ge=5, le=1440)

    @field_validator("recipient")
    @classmethod
    def validate_recipient(cls, value: str) -> str:
        return _valid_email(value)

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        if "\r" in value or "\n" in value:
            raise ValueError("Email subject must not contain line breaks")
        return " ".join(value.strip().split())

    @field_validator("body")
    @classmethod
    def clean_body(cls, value: str) -> str:
        return value.strip()


class ApplicationPreflightView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    opportunity_id: UUID
    task_id: UUID
    apply_url: str
    final_url: str
    form_signature: str | None
    fields: list[dict[str, Any]]
    submit_label: str | None
    blocked_reason: str | None
    has_captcha: bool
    has_login: bool
    created_at: datetime


class ExternalActionView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    task_id: UUID
    opportunity_id: UUID | None
    action_type: str
    status: str
    target_display: str
    public_context: dict[str, Any]
    context_hash: str
    expires_at: datetime
    external_reference: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    executed_at: datetime | None
