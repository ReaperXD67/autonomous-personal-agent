from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreatorReplyDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1, max_length=120)
    body_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CreatorReplyDraftView(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: UUID
    campaign_id: UUID
    reply_id: UUID
    prospect_id: UUID
    task_id: UUID
    requested_by: str
    status: Literal["queued", "ready", "failed", "cancelled"]
    reply_body_digest: str
    input_hash: str
    source: Literal["ollama"] | None = None
    selected_model: str | None = None
    copy_content: dict[str, Any] | None = Field(default=None, alias="model_copy")
    subject: str | None = None
    body: str | None = None
    draft_digest: str | None = None
    error_code: str | None = None
    created_at: datetime
    expires_at: datetime
    contact_authorized: bool
    context_current: bool
    sending_authority: Literal[False] = False
    send_hold_reason: str
