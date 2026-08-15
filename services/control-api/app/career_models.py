from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SOURCE_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")


def _clean_values(values: list[str], *, limit: int = 40) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = " ".join(value.strip().split())[:120]
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            cleaned.append(item)
    if len(cleaned) > limit:
        raise ValueError(f"No more than {limit} values are allowed")
    return cleaned


class CareerSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arbeitnow: bool = True
    ashby_boards: list[str] = Field(default_factory=list)
    greenhouse_boards: list[str] = Field(default_factory=list)

    @field_validator("ashby_boards", "greenhouse_boards")
    @classmethod
    def validate_board_slugs(cls, values: list[str]) -> list[str]:
        cleaned = _clean_values(values, limit=30)
        if any(not SOURCE_SLUG.fullmatch(value) for value in cleaned):
            raise ValueError(
                "Board names may contain only letters, numbers, underscores, and hyphens"
            )
        return cleaned

    @model_validator(mode="after")
    def require_source(self) -> CareerSourceConfig:
        if not self.arbeitnow and not self.ashby_boards and not self.greenhouse_boards:
            raise ValueError("At least one reviewed career source must be enabled")
        return self


class CareerProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    candidate_name: str = Field(min_length=1, max_length=160)
    desired_titles: list[str] = Field(min_length=1, max_length=20)
    skills: list[str] = Field(default_factory=list, max_length=40)
    required_keywords: list[str] = Field(default_factory=list, max_length=30)
    excluded_keywords: list[str] = Field(default_factory=list, max_length=30)
    locations: list[str] = Field(default_factory=list, max_length=20)
    remote_only: bool = False
    employment_types: list[
        Literal["FullTime", "PartTime", "Intern", "Contract", "Temporary"]
    ] = Field(default_factory=list)
    max_age_hours: int = Field(default=72, ge=1, le=168)
    min_score: int = Field(default=45, ge=0, le=100)
    schedule_minutes: int = Field(default=360, ge=360, le=10080)
    source_config: CareerSourceConfig = Field(default_factory=CareerSourceConfig)
    resume_text: str = Field(default="", max_length=100000)
    active: bool = False
    requested_by: str = Field(min_length=1, max_length=120)

    @field_validator(
        "desired_titles",
        "skills",
        "required_keywords",
        "excluded_keywords",
        "locations",
    )
    @classmethod
    def clean_lists(cls, values: list[str]) -> list[str]:
        return _clean_values(values)


class CareerProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    candidate_name: str = Field(min_length=1, max_length=160)
    desired_titles: list[str] = Field(min_length=1, max_length=20)
    skills: list[str] = Field(default_factory=list, max_length=40)
    required_keywords: list[str] = Field(default_factory=list, max_length=30)
    excluded_keywords: list[str] = Field(default_factory=list, max_length=30)
    locations: list[str] = Field(default_factory=list, max_length=20)
    remote_only: bool = False
    employment_types: list[
        Literal["FullTime", "PartTime", "Intern", "Contract", "Temporary"]
    ] = Field(default_factory=list)
    max_age_hours: int = Field(default=72, ge=1, le=168)
    min_score: int = Field(default=45, ge=0, le=100)
    schedule_minutes: int = Field(default=360, ge=360, le=10080)
    source_config: CareerSourceConfig = Field(default_factory=CareerSourceConfig)
    resume_text: str | None = Field(default=None, max_length=100000)
    active: bool = False
    actor: str = Field(min_length=1, max_length=120)

    @field_validator(
        "desired_titles",
        "skills",
        "required_keywords",
        "excluded_keywords",
        "locations",
    )
    @classmethod
    def clean_lists(cls, values: list[str]) -> list[str]:
        return _clean_values(values)


class CareerProfileView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    name: str
    candidate_name: str
    desired_titles: list[str]
    skills: list[str]
    required_keywords: list[str]
    excluded_keywords: list[str]
    locations: list[str]
    remote_only: bool
    employment_types: list[str]
    max_age_hours: int
    min_score: int
    schedule_minutes: int
    source_config: dict[str, Any]
    active: bool
    requested_by: str
    resume_present: bool
    resume_characters: int
    next_scan_at: datetime
    last_scan_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OpportunityStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["new", "shortlisted", "dismissed", "applied"]
    actor: str = Field(min_length=1, max_length=120)


class OpportunityView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    profile_id: UUID
    source: str
    source_key: str
    company: str
    title: str
    location: str
    description: str
    remote: bool
    employment_type: str | None
    source_url: str
    apply_url: str
    published_at: datetime
    first_seen_at: datetime
    last_seen_at: datetime
    score: int
    score_reasons: list[str]
    status: str
    applied_at: datetime | None
    latest_draft: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class AuditEventView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    occurred_at: datetime
    correlation_id: UUID
    task_id: UUID | None
    actor_type: str
    actor_id: str
    tool_name: str | None
    action: str
    risk_level: str
    approval_status: str
    execution_status: str
    input_metadata: dict[str, Any]
    result_metadata: dict[str, Any]
    error_code: str | None
    error_message: str | None
