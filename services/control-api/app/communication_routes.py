"""Private communication setup metadata; diagnostics execute only as audited tasks."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.action_models import ExternalActionView
from app.action_store import ExternalActionNotFoundError
from app.auth import require_api_token
from app.models import TaskCreate, TaskView
from app.policy import RiskLevel
from app.settings import get_settings

router = APIRouter(dependencies=[Depends(require_api_token)])


class SmtpCheckCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requested_by: str = Field(min_length=1, max_length=120)


@router.post(
    "/v1/communications/smtp-check", response_model=TaskView,
    status_code=status.HTTP_201_CREATED,
)
def check_smtp(request: Request, payload: SmtpCheckCreate):
    return request.app.state.database.create_task(TaskCreate(
        title="Check configured email connection without sending a message",
        kind="communications.smtp_check", payload={}, risk_level=RiskLevel.MEDIUM,
        requested_by=payload.requested_by,
    ))


def _public_check_output(output: object) -> dict[str, object]:
    if not isinstance(output, dict):
        return {}
    result: dict[str, object] = {}
    allowed_values = {
        "handler": ("communications.smtp_check",),
        "transport": ("disabled", "mailpit", "smtp"),
        "tls_mode": ("none", "ssl", "starttls"),
    }
    for key, values in allowed_values.items():
        value = output.get(key)
        if isinstance(value, str) and value in values:
            result[key] = value
    for key in ("authenticated", "checked"):
        value = output.get(key)
        if isinstance(value, bool):
            result[key] = value
    return result


@router.get("/v1/communications/status")
def communication_status(request: Request):
    runtime = get_settings()
    with request.app.state.database.connect() as connection:
        check = connection.execute(
            """SELECT id, status, completed_at, output, error_code FROM agent_tasks
               WHERE kind = 'communications.smtp_check' ORDER BY created_at DESC LIMIT 1""",
        ).fetchone()
    if check:
        check = {**check, "output": _public_check_output(check["output"])}
    return {"transport": runtime.mail_transport, "sender_configured": bool(runtime.smtp_from),
            "latest_check": check}


@router.get("/v1/external-actions/{action_id}", response_model=ExternalActionView)
def get_external_action(request: Request, action_id: UUID):
    try:
        return request.app.state.actions.get_external_action(action_id)
    except ExternalActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="External action not found") from exc
