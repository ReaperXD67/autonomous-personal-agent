from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.action_models import ApplicationPlanCreate
from app.application_browser import EXTERNAL_APPLICATION_HOSTS


class CareerPlay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1, max_length=120)
    mode: Literal["prepare", "apply"] = "prepare"
    max_applications_per_day: int = Field(default=3, ge=1, le=10)
    min_score: int = Field(default=75, ge=0, le=100)
    max_age_hours: int = Field(default=72, ge=1, le=168)
    allowed_hosts: list[str] = Field(
        default_factory=lambda: sorted(EXTERNAL_APPLICATION_HOSTS), max_length=5
    )
    expires_in_hours: int = Field(default=24, ge=1, le=168)
    answers: dict[str, str | bool] = Field(default_factory=dict, max_length=100)
    include_cold_email: bool = False

    @field_validator("allowed_hosts")
    @classmethod
    def validate_hosts(cls, hosts: list[str]) -> list[str]:
        normalized = sorted({host.strip().lower() for host in hosts})
        if any(host not in EXTERNAL_APPLICATION_HOSTS for host in normalized):
            raise ValueError("Choose supported application hosts without paths or wildcards")
        return normalized

    @field_validator("answers")
    @classmethod
    def validate_answers(cls, answers: dict[str, str | bool]) -> dict[str, str | bool]:
        return ApplicationPlanCreate.validate_answers(answers)

    @model_validator(mode="after")
    def check_scope(self) -> CareerPlay:
        if self.mode == "apply" and not self.allowed_hosts and not self.include_cold_email:
            raise ValueError("Automatic applications need at least one selected destination")
        return self


class CareerPause(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1, max_length=120)
