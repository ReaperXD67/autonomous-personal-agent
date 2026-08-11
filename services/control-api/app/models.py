from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.policy import RiskLevel


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    kind: Literal["foundation.echo"] = "foundation.echo"
    payload: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    requested_by: str = Field(min_length=1, max_length=120)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=200)


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    actor: str = Field(min_length=1, max_length=120)
    reason: str | None = Field(default=None, max_length=500)


class TaskView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    correlation_id: UUID
    title: str
    kind: str
    payload: dict[str, Any]
    output: dict[str, Any] | None
    risk_level: RiskLevel
    status: str
    requested_by: str
    approved_by: str | None
    error_code: str | None
    error_message: str | None
    attempt_count: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

