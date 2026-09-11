from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from app.workflow_models import WorkflowCreate


class PlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=2000)
    requested_by: str = Field(min_length=1, max_length=120)
    profile_id: UUID | None = None
    opportunity_ids: list[UUID] = Field(default_factory=list, max_length=3)
    campaign_id: UUID | None = None
    mode: Literal["model", "demo"] = "model"
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=200)

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        if not self.goal.strip():
            raise ValueError("A goal is required")
        if len(set(self.opportunity_ids)) != len(self.opportunity_ids):
            raise ValueError("Selected opportunities must be unique")
        if self.opportunity_ids and self.profile_id is None:
            raise ValueError("Select the career profile that owns these opportunities")
        if self.mode == "demo" and (self.profile_id or self.campaign_id or self.opportunity_ids):
            raise ValueError("The local demo uses no career or creator context")
        return self

    def digest(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json", exclude={"idempotency_key"}),
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class ModelPlanChoice(BaseModel):
    """Models may select declared action keys, never write executable task specifications."""

    model_config = ConfigDict(extra="forbid")

    supported: StrictBool
    action_keys: list[str] = Field(max_length=8)
    summary: str = Field(min_length=1, max_length=800)
    limitations: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def validate_choice(self) -> Self:
        if len(set(self.action_keys)) != len(self.action_keys):
            raise ValueError("Planner selected duplicate actions")
        if any(not 1 <= len(key) <= 40 for key in self.action_keys):
            raise ValueError("Planner action key exceeds its limit")
        if any(not 1 <= len(item) <= 500 for item in self.limitations):
            raise ValueError("Planner limitation exceeds its limit")
        if self.supported != bool(self.action_keys):
            raise ValueError("Supported proposals need actions; unsupported proposals cannot act")
        return self


class PlanAdopt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1, max_length=120)
    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class PlanView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    goal: str
    requested_by: str
    mode: str
    status: str
    task_id: UUID
    task_status: str
    source: str | None
    selected_model: str | None
    summary: str | None
    limitations: list[str]
    workflow_spec: dict[str, Any] | None
    plan_digest: str | None
    workflow_id: UUID | None
    error_code: str | None
    created_at: datetime
    expires_at: datetime


def workflow_digest(specification: WorkflowCreate) -> str:
    return hashlib.sha256(specification.canonical_spec().encode("utf-8")).hexdigest()


def parse_plan_choice(content: str, inventory: list[dict[str, Any]]) -> ModelPlanChoice:
    if len(content.encode("utf-8")) > 16000:
        raise ValueError("Planner response exceeded its limit")
    candidate = content.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        candidate = "\n".join(candidate.splitlines()[1:-1]).strip()
    choice = ModelPlanChoice.model_validate_json(candidate)
    allowed = {item["key"] for item in inventory}
    if set(choice.action_keys) - allowed:
        raise ValueError("Planner selected an action outside the authorized context")
    return choice


def compile_workflow(
    request: PlanCreate, choice: ModelPlanChoice, inventory: list[dict[str, Any]]
) -> WorkflowCreate | None:
    if not choice.supported:
        return None
    by_key = {item["key"]: item for item in inventory}
    if set(choice.action_keys) - by_key.keys():
        raise ValueError("Planner selected an action outside the authorized context")
    steps = []
    for position, key in enumerate(choice.action_keys):
        action = by_key[key]
        steps.append({
            "key": key,
            "title": action["title"],
            "kind": action["kind"],
            "payload": action["payload"],
            "expect_output": action["expect_output"],
            "depends_on": [] if position == 0 else [choice.action_keys[position - 1]],
        })
    return WorkflowCreate(
        title="Reviewed goal plan", objective=request.goal, requested_by=request.requested_by,
        max_parallel=1, timeout_seconds=3600, steps=steps,
    )
