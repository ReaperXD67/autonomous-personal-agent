"""Operator-reviewed, job-specific public contacts; never an email finder."""
from __future__ import annotations

import ipaddress
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.action_models import _valid_email


class CareerContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    kind: Literal["hiring", "hr", "founder"]
    source_url: str = Field(min_length=10, max_length=2000)
    evidence_quote: str = Field(min_length=20, max_length=2000)
    basis_note: str = Field(min_length=20, max_length=1000)
    reviewed_by: str = Field(min_length=1, max_length=120)
    attested_primary_source: Literal[True]
    validity_hours: int = Field(default=24, ge=1, le=72)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        address = _valid_email(value).casefold()
        if any(token in address.split("@", 1)[0] for token in (
            "noreply", "no-reply", "privacy", "abuse", "support",
        )):
            raise ValueError("Choose an explicitly published hiring, HR or founder contact")
        return address

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        parsed = urlsplit(value.strip())
        host = parsed.hostname or ""
        if (parsed.scheme != "https" or parsed.port not in {None, 443}
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment or "." not in host or host.endswith((".local", ".localhost"))
                or any(char.isspace() for char in value)):
            raise ValueError("Contact evidence needs a public HTTPS primary-page URL")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return value.strip()
        raise ValueError("Use the employer's public domain rather than an IP address")

    @field_validator("evidence_quote", "basis_note", "reviewed_by")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("A meaningful source review is required")
        return cleaned

    @model_validator(mode="after")
    def evidence_includes_email(self) -> CareerContactCreate:
        addresses = re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,24}",
                               self.evidence_quote, re.I)
        if self.email not in {address.casefold() for address in addresses}:
            raise ValueError("Quote the exact published address; inferred emails are unsupported")
        return self


class CareerContactEmailPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1, max_length=120)
    approval_window_minutes: int = Field(default=60, ge=5, le=1440)


class CareerContactRevoke(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1, max_length=120)
