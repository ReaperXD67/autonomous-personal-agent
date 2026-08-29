from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.action_models import _valid_email


def _https_url(value: str | None, *, required: bool = True) -> str | None:
    if value is None:
        if required:
            raise ValueError("An HTTPS URL is required")
        return None
    cleaned = value.strip()
    if not cleaned and not required:
        return None
    parsed = urlparse(cleaned)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("URLs must use HTTPS and must not contain credentials")
    return cleaned


def _clean_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())[:limit]
    return cleaned or None


class MarketingCampaignFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    product_name: str = Field(min_length=1, max_length=160)
    product_url: str
    privacy_url: str
    product_summary: str = Field(min_length=20, max_length=1200)
    target_audience: str = Field(min_length=3, max_length=500)
    viewer_offer: str = Field(min_length=3, max_length=1000)
    creator_offer: str = Field(min_length=3, max_length=1000)
    paid_offer_enabled: bool = True
    paid_offer_details: str | None = Field(default=None, max_length=1200)
    sender_name: str = Field(min_length=1, max_length=160)
    discovery_queries: list[str] = Field(min_length=1, max_length=3)
    relevance_language: str = Field(
        default="en", pattern=r"^(?:[A-Za-z]{2}|zh-(?:Hans|Hant))$"
    )
    region_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    min_subscribers: int = Field(default=1000, ge=0, le=1_000_000_000)
    max_subscribers: int = Field(default=250000, ge=0, le=1_000_000_000)
    max_video_age_days: int = Field(default=120, ge=7, le=365)
    results_per_query: int = Field(default=10, ge=1, le=25)
    schedule_hours: int = Field(default=24, ge=24, le=168)
    adaptive_mode: bool = True
    active: bool = False

    @field_validator("product_url", "privacy_url")
    @classmethod
    def validate_required_url(cls, value: str) -> str:
        result = _https_url(value)
        assert result is not None
        return result

    @field_validator(
        "name",
        "product_name",
        "product_summary",
        "target_audience",
        "viewer_offer",
        "creator_offer",
        "sender_name",
    )
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("This field cannot be blank")
        return cleaned

    @field_validator("paid_offer_details")
    @classmethod
    def clean_paid_offer(cls, value: str | None) -> str | None:
        return _clean_text(value, 1200)

    @field_validator("discovery_queries")
    @classmethod
    def clean_queries(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            query = " ".join(value.strip().split())
            if not 2 <= len(query) <= 160:
                raise ValueError("Each discovery query must contain 2 to 160 characters")
            if query.casefold() not in {item.casefold() for item in cleaned}:
                cleaned.append(query)
        if not cleaned:
            raise ValueError("At least one discovery query is required")
        return cleaned

    @model_validator(mode="after")
    def validate_ranges_and_offer(self) -> MarketingCampaignFields:
        if self.max_subscribers < self.min_subscribers:
            raise ValueError("Maximum subscribers cannot be below the minimum")
        if self.paid_offer_enabled and not self.paid_offer_details:
            raise ValueError("Describe the paid offer before enabling it")
        return self


class MarketingCampaignCreate(MarketingCampaignFields):
    requested_by: str = Field(min_length=1, max_length=120)


class MarketingCampaignUpdate(MarketingCampaignFields):
    actor: str = Field(min_length=1, max_length=120)


class MarketingCampaignView(MarketingCampaignFields):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    next_scan_at: datetime
    last_scan_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class MarketingProspectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: UUID
    platform: Literal[
        "youtube", "twitch", "tiktok", "discord", "minecraft_server", "blog", "other"
    ]
    external_id: str | None = Field(default=None, max_length=500)
    display_name: str = Field(min_length=1, max_length=300)
    profile_url: str
    audience_size: int | None = Field(default=None, ge=0, le=1_000_000_000)
    latest_content_title: str | None = Field(default=None, max_length=500)
    latest_content_url: str | None = None
    contact_email: str | None = None
    contact_source_url: str | None = None
    contact_basis_note: str | None = Field(default=None, max_length=1000)
    authorize_contact: bool = False
    requested_by: str = Field(min_length=1, max_length=120)

    @field_validator("profile_url")
    @classmethod
    def validate_profile_url(cls, value: str) -> str:
        result = _https_url(value)
        assert result is not None
        return result

    @field_validator("latest_content_url", "contact_source_url")
    @classmethod
    def validate_optional_url(cls, value: str | None) -> str | None:
        return _https_url(value, required=False)

    @field_validator("contact_email")
    @classmethod
    def validate_optional_email(cls, value: str | None) -> str | None:
        return _valid_email(value) if value else None

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        cleaned = _clean_text(value, 300)
        if not cleaned:
            raise ValueError("Display name cannot be blank")
        return cleaned

    @field_validator("latest_content_title", "contact_basis_note")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return _clean_text(value, 1000)

    @model_validator(mode="after")
    def validate_contact_authorization(self) -> MarketingProspectCreate:
        contact_fields = (
            self.contact_email,
            self.contact_source_url,
            self.contact_basis_note,
        )
        if self.authorize_contact and not all(contact_fields):
            raise ValueError(
                "Authorized outreach requires an email, its public source, and a basis note"
            )
        if any(contact_fields) and not all(contact_fields):
            raise ValueError("Provide the complete contact provenance or leave all fields blank")
        return self


class MarketingProspectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=300)
    profile_url: str
    audience_size: int | None = Field(default=None, ge=0, le=1_000_000_000)
    contact_email: str | None = None
    contact_source_url: str | None = None
    contact_basis_note: str | None = Field(default=None, max_length=1000)
    authorize_contact: bool = False
    actor: str = Field(min_length=1, max_length=120)

    @field_validator("profile_url")
    @classmethod
    def validate_profile_url(cls, value: str) -> str:
        result = _https_url(value)
        assert result is not None
        return result

    @field_validator("contact_source_url")
    @classmethod
    def validate_contact_source(cls, value: str | None) -> str | None:
        return _https_url(value, required=False)

    @field_validator("contact_email")
    @classmethod
    def validate_optional_email(cls, value: str | None) -> str | None:
        return _valid_email(value) if value else None

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        cleaned = _clean_text(value, 300)
        if not cleaned:
            raise ValueError("Display name cannot be blank")
        return cleaned

    @field_validator("contact_basis_note")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return _clean_text(value, 1000)

    @model_validator(mode="after")
    def validate_contact_authorization(self) -> MarketingProspectUpdate:
        fields = (self.contact_email, self.contact_source_url, self.contact_basis_note)
        if self.authorize_contact and not all(fields):
            raise ValueError(
                "Authorized outreach requires an email, its public source, and a basis note"
            )
        if any(fields) and not all(fields):
            raise ValueError("Provide the complete contact provenance or leave all fields blank")
        return self


class MarketingOutcomeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: Literal[
        "question",
        "declined_unpaid",
        "interested",
        "converted",
        "do_not_contact",
        "bounced",
        "promotion_published",
    ]
    note: str | None = Field(default=None, max_length=4000)
    promotion_url: str | None = None
    attributed_views: int = Field(default=0, ge=0, le=2_000_000_000)
    attributed_clicks: int = Field(default=0, ge=0, le=2_000_000_000)
    attributed_signups: int = Field(default=0, ge=0, le=2_000_000_000)
    attributed_server_owners: int = Field(default=0, ge=0, le=2_000_000_000)
    viewer_points_issued: int = Field(default=0, ge=0, le=9_000_000_000_000)
    actor: str = Field(min_length=1, max_length=120)

    @field_validator("promotion_url")
    @classmethod
    def validate_promotion_url(cls, value: str | None) -> str | None:
        return _https_url(value, required=False)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()[:4000] or None


class MarketingEmailPlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Literal["initial", "question_reply", "paid_offer"]
    subject: str | None = Field(default=None, max_length=240)
    body: str | None = Field(default=None, max_length=20000)
    actor: str = Field(min_length=1, max_length=120)
    approval_window_minutes: int = Field(default=1440, ge=5, le=1440)

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if "\r" in value or "\n" in value:
            raise ValueError("Email subject must not contain line breaks")
        return " ".join(value.strip().split()) or None

    @field_validator("body")
    @classmethod
    def clean_body(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def validate_manual_reply(self) -> MarketingEmailPlanCreate:
        if self.stage == "question_reply" and not (self.subject and self.body):
            raise ValueError("Question replies require a manually reviewed subject and body")
        if self.stage != "question_reply" and (self.subject or self.body):
            raise ValueError("Initial and paid-offer copy is generated from the campaign packet")
        return self


class MarketingProspectView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    campaign_id: UUID
    platform: str
    external_id: str
    display_name: str
    profile_url: str
    audience_size: int | None
    latest_content_title: str | None
    latest_content_url: str | None
    latest_content_published_at: datetime | None
    discovery_query: str | None
    relevance_score: int
    relevance_reasons: list[str]
    contact_email: str | None
    contact_source_url: str | None
    contact_basis_note: str | None
    contact_authorized_at: datetime | None
    contact_authorized_by: str | None
    status: str
    tracking_code: str
    suppressed_at: datetime | None
    suppression_reason: str | None
    latest_message: dict[str, Any] | None = None
    latest_outcome: dict[str, Any] | None = None
    sent_message_count: int = 0
    first_seen_at: datetime
    last_seen_at: datetime
    updated_at: datetime


class MarketingResultsView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    campaign_id: UUID
    campaign_name: str
    metrics: dict[str, int | float]
    variants: list[dict[str, Any]]
    suggestions: list[dict[str, Any]]
