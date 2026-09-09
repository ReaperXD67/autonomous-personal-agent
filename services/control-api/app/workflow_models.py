from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

from app.policy import RiskLevel, effective_risk

type Scalar = StrictStr | StrictInt | StrictFloat | StrictBool | None
type WorkflowKind = Literal[
    "foundation.echo",
    "foundation.wait",
    "career.search",
    "career.application_draft",
    "career.application_preflight",
    "marketing.creator_discovery",
]


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class _Echo(_Payload):
    message: str = Field(default="", max_length=2000)


class _Wait(_Payload):
    seconds: float = Field(default=1, ge=0, le=60)


class _Search(_Payload):
    profile_id: UUID


class _Draft(_Search):
    opportunity_id: UUID


class _Preflight(_Payload):
    opportunity_id: UUID
    profile_id: UUID | None = None


class _Discovery(_Payload):
    campaign_id: UUID


_PAYLOAD_MODELS = {
    "foundation.echo": _Echo,
    "foundation.wait": _Wait,
    "career.search": _Search,
    "career.application_draft": _Draft,
    "career.application_preflight": _Preflight,
    "marketing.creator_discovery": _Discovery,
}


class WorkflowStepCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
    title: str = Field(min_length=1, max_length=200)
    kind: WorkflowKind
    payload: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, max_length=31)
    risk_level: RiskLevel = RiskLevel.LOW
    expect_output: dict[str, Scalar] = Field(default_factory=dict, max_length=8)

    @model_validator(mode="after")
    def validate_step(self) -> Self:
        self.payload = _PAYLOAD_MODELS[self.kind].model_validate(self.payload).model_dump(
            mode="json", exclude_none=True
        )
        self.risk_level = effective_risk(self.kind, self.risk_level)
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("Step dependencies must be unique")
        for key, value in self.expect_output.items():
            if not 1 <= len(key) <= 80 or (isinstance(value, str) and len(value) > 2000):
                raise ValueError("Output check keys or values exceed the size limit")
        return self


class WorkflowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(default="", max_length=2000)
    requested_by: str = Field(min_length=1, max_length=120)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=200)
    max_parallel: int = Field(default=2, ge=1, le=4, strict=True)
    timeout_seconds: int = Field(default=3600, ge=60, le=86400, strict=True)
    steps: list[WorkflowStepCreate] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        keys = {step.key for step in self.steps}
        if len(keys) != len(self.steps):
            raise ValueError("Step keys must be unique")
        if any(set(step.depends_on) - keys for step in self.steps):
            raise ValueError("Every dependency must refer to a step in this workflow")
        resolved: set[str] = set()
        while len(resolved) < len(keys):
            ready = {
                step.key for step in self.steps
                if step.key not in resolved and set(step.depends_on) <= resolved
            }
            if not ready:
                raise ValueError("Workflow dependencies must not contain cycles")
            resolved.update(ready)
        if len(self.model_dump_json().encode("utf-8")) > 65536:
            raise ValueError("Workflow specification must fit within 64 KiB")
        return self

    def canonical_spec(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", exclude={"idempotency_key"}),
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        )


class WorkflowStepView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    title: str
    kind: str
    depends_on: list[str]
    risk_level: RiskLevel
    expect_output: dict[str, Scalar]
    status: str
    task_id: UUID | None
    task_status: str | None
    error_code: str | None


class WorkflowView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    title: str
    objective: str
    requested_by: str
    status: str
    max_parallel: int
    timeout_seconds: int
    created_at: datetime
    updated_at: datetime
    deadline_at: datetime
    completed_at: datetime | None
    steps: list[WorkflowStepView]


def output_matches(output: dict[str, Any] | None, expected: dict[str, Any]) -> bool:
    """Check explicit top-level evidence without executing expressions or coercing types."""
    actual = output or {}
    return all(
        key in actual
        and actual[key] == value
        and isinstance(actual[key], bool) == isinstance(value, bool)
        for key, value in expected.items()
    )
