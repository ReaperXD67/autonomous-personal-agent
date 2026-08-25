from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from psycopg.types.json import Jsonb

from app.action_models import ApplicationIdentity, ApplicationPlanCreate, EmailActionCreate
from app.application_browser import canonical_hash, resolve_application_fields
from app.career_store import CareerStore, OpportunityNotFoundError
from app.models import TaskCreate
from app.policy import RiskLevel


class ActionPreparationError(RuntimeError):
    def __init__(self, message: str, *, missing_fields: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.missing_fields = missing_fields or []


class ExternalActionNotFoundError(LookupError):
    pass


class SideEffectGuardError(RuntimeError):
    pass


class ActionStore(CareerStore):
    def save_preflight(
        self, *, opportunity_id: UUID, task_id: UUID, result: dict[str, Any]
    ) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO job_application_preflights (
                    opportunity_id, task_id, apply_url, final_url, form_signature,
                    fields, submit_label, blocked_reason, has_captcha, has_login
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (task_id) DO UPDATE SET
                    final_url = EXCLUDED.final_url,
                    form_signature = EXCLUDED.form_signature,
                    fields = EXCLUDED.fields,
                    submit_label = EXCLUDED.submit_label,
                    blocked_reason = EXCLUDED.blocked_reason,
                    has_captcha = EXCLUDED.has_captcha,
                    has_login = EXCLUDED.has_login
                RETURNING *
                """,
                (
                    opportunity_id,
                    task_id,
                    result["apply_url"],
                    result["final_url"],
                    result["form_signature"],
                    Jsonb(result["fields"]),
                    result["submit_label"],
                    result["blocked_reason"],
                    result["has_captcha"],
                    result["has_login"],
                ),
            ).fetchone()
            connection.commit()
        return row

    def _application_context(self, opportunity_id: UUID) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    o.id AS opportunity_id, o.profile_id, o.source, o.company,
                    o.title, o.apply_url, p.candidate_name, p.application_identity,
                    p.resume_text, p.auto_prepare,
                    d.id AS draft_id, d.content AS draft_content,
                    pf.id AS preflight_id, pf.final_url, pf.form_signature,
                    pf.fields, pf.submit_label, pf.blocked_reason,
                    pf.has_captcha, pf.has_login, pf.created_at AS preflight_created_at
                FROM job_opportunities o
                JOIN career_profiles p ON p.id = o.profile_id
                LEFT JOIN LATERAL (
                    SELECT id, content FROM job_application_drafts
                    WHERE opportunity_id = o.id ORDER BY created_at DESC LIMIT 1
                ) d ON true
                LEFT JOIN LATERAL (
                    SELECT * FROM job_application_preflights
                    WHERE opportunity_id = o.id ORDER BY created_at DESC LIMIT 1
                ) pf ON true
                WHERE o.id = %s
                """,
                (opportunity_id,),
            ).fetchone()
        if row is None:
            raise OpportunityNotFoundError(str(opportunity_id))
        return row

    def create_application_action(
        self, opportunity_id: UUID, request: ApplicationPlanCreate
    ) -> dict[str, Any]:
        context = self._application_context(opportunity_id)
        if context["preflight_id"] is None:
            raise ActionPreparationError("Inspect the application form before planning submission")
        if context["preflight_created_at"] < datetime.now(UTC) - timedelta(hours=6):
            raise ActionPreparationError("Application preflight is stale; inspect the form again")
        if context["blocked_reason"]:
            raise ActionPreparationError(
                f"Application form requires user handling: {context['blocked_reason']}"
            )
        if not context["form_signature"] or not context["submit_label"]:
            raise ActionPreparationError("Application preflight did not find a final submit form")
        if not context["resume_text"].strip():
            raise ActionPreparationError("A resume is required before planning submission")
        if context["draft_id"] is None:
            raise ActionPreparationError("Generate an application draft before planning submission")
        try:
            identity = ApplicationIdentity.model_validate(context["application_identity"])
        except ValueError as exc:
            raise ActionPreparationError(
                "Complete the application identity in the career mission"
            ) from exc

        cover_letter = str(context["draft_content"].get("cover_letter") or "")
        values, missing = resolve_application_fields(
            context["fields"], identity.model_dump(), cover_letter, request.answers
        )
        if missing:
            raise ActionPreparationError(
                "Required application questions need explicit answers",
                missing_fields=missing,
            )

        resume_hash = hashlib.sha256(context["resume_text"].encode("utf-8")).hexdigest()
        draft_hash = canonical_hash(context["draft_content"])
        public_context = {
            "opportunity_id": str(opportunity_id),
            "company": context["company"],
            "title": context["title"],
            "source": context["source"],
            "apply_host": urlparse(context["final_url"]).hostname,
            "apply_url": context["final_url"],
            "preflight_signature": context["form_signature"],
            "submit_label": context["submit_label"],
            "field_values": values,
            "resume_sha256": resume_hash,
            "draft_sha256": draft_hash,
        }
        private_context = {
            "profile_id": str(context["profile_id"]),
            "preflight_id": str(context["preflight_id"]),
            "draft_id": str(context["draft_id"]),
            "identity": identity.model_dump(),
            "answers": request.answers,
            "resolved_values": values,
            "resume_sha256": resume_hash,
            "draft_sha256": draft_hash,
        }
        return self._create_external_action(
            action_type="career.application_submit",
            opportunity_id=opportunity_id,
            target_display=f"{context['company']} — {context['title']}",
            public_context=public_context,
            private_context=private_context,
            actor=request.actor,
            approval_window_minutes=request.approval_window_minutes,
        )

    def try_create_automatic_application_action(
        self, opportunity_id: UUID
    ) -> dict[str, Any] | None:
        context = self._application_context(opportunity_id)
        if not context["auto_prepare"]:
            return None
        try:
            return self.create_application_action(
                opportunity_id,
                ApplicationPlanCreate(
                    answers={},
                    actor="scheduler:career-auto-prepare",
                    approval_window_minutes=1440,
                ),
            )
        except ActionPreparationError:
            return None

    def create_email_action(
        self, request: EmailActionCreate, *, sender: str
    ) -> dict[str, Any]:
        public_context = {
            "sender": sender,
            "recipient": request.recipient,
            "subject": request.subject,
            "body": request.body,
            "opportunity_id": str(request.opportunity_id) if request.opportunity_id else None,
        }
        return self._create_external_action(
            action_type="communications.email_send",
            opportunity_id=request.opportunity_id,
            target_display=request.recipient,
            public_context=public_context,
            private_context=public_context,
            actor=request.actor,
            approval_window_minutes=request.approval_window_minutes,
        )

    def _create_external_action(
        self,
        *,
        action_type: str,
        opportunity_id: UUID | None,
        target_display: str,
        public_context: dict[str, Any],
        private_context: dict[str, Any],
        actor: str,
        approval_window_minutes: int,
    ) -> dict[str, Any]:
        context_hash = canonical_hash(
            {
                "action_type": action_type,
                "public_context": public_context,
                "private_context": private_context,
            }
        )
        idempotency_key = f"external:{action_type}:{context_hash}"[:200]
        expires_at = datetime.now(UTC) + timedelta(minutes=approval_window_minutes)
        with self.connect() as connection:
            action = connection.execute(
                """
                INSERT INTO external_actions (
                    opportunity_id, action_type, status, target_display,
                    public_context, private_context, context_hash,
                    idempotency_key, expires_at
                ) VALUES (%s, %s, 'pending_approval', %s, %s, %s, %s, %s, %s)
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING *
                """,
                (
                    opportunity_id,
                    action_type,
                    target_display,
                    Jsonb(public_context),
                    Jsonb(private_context),
                    context_hash,
                    idempotency_key,
                    expires_at,
                ),
            ).fetchone()
            if action is None:
                existing = connection.execute(
                    "SELECT * FROM external_actions WHERE idempotency_key = %s",
                    (idempotency_key,),
                ).fetchone()
                if existing is None or existing["task_id"] is None:
                    raise RuntimeError("External action idempotency conflict is incomplete")
                return existing
            task = self._create_task_record(
                connection,
                TaskCreate(
                    title=(
                        "Submit one approved job application"
                        if action_type == "career.application_submit"
                        else "Send one approved email"
                    ),
                    kind=action_type,
                    payload={
                        "action_id": str(action["id"]),
                        "action_digest": context_hash,
                    },
                    risk_level=RiskLevel.HIGH,
                    requested_by=actor,
                    idempotency_key=f"external-action-task:{action['id']}",
                ),
            )
            action = connection.execute(
                "UPDATE external_actions SET task_id = %s WHERE id = %s RETURNING *",
                (task["id"], action["id"]),
            ).fetchone()
            self._append_audit(
                connection,
                correlation_id=task["correlation_id"],
                task_id=task["id"],
                actor_type="system",
                actor_id="external-action-planner",
                tool_name=action_type,
                action="external_action.prepared",
                risk_level="high",
                approval_status="required",
                execution_status="pending_approval",
                input_metadata={
                    "action_id": str(action["id"]),
                    "context_hash": context_hash,
                    "target_type": action_type,
                },
            )
            connection.commit()
        return action

    def list_external_actions(
        self, *, action_status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT id, task_id, opportunity_id, action_type, status,
                       target_display, public_context, context_hash, expires_at,
                       external_reference, last_error, created_at, updated_at, executed_at
                FROM external_actions
                WHERE (%s::text IS NULL OR status = %s)
                ORDER BY created_at DESC LIMIT %s
                """,
                (action_status, action_status, limit),
            ).fetchall()

    def get_action_for_execution(self, task_id: UUID) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM external_actions WHERE task_id = %s", (task_id,)
            ).fetchone()
        if row is None:
            raise ExternalActionNotFoundError(str(task_id))
        return row

    def get_application_execution_material(self, action: dict[str, Any]) -> dict[str, Any]:
        private_context = action["private_context"]
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT p.candidate_name, p.resume_text, d.content AS draft_content
                FROM career_profiles p
                JOIN job_application_drafts d ON d.profile_id = p.id
                WHERE p.id = %s AND d.id = %s
                """,
                (private_context["profile_id"], private_context["draft_id"]),
            ).fetchone()
        if row is None:
            raise SideEffectGuardError("Approved application material no longer exists")
        resume_hash = hashlib.sha256(row["resume_text"].encode("utf-8")).hexdigest()
        if resume_hash != private_context["resume_sha256"]:
            raise SideEffectGuardError("Resume changed after the application was approved")
        if canonical_hash(row["draft_content"]) != private_context["draft_sha256"]:
            raise SideEffectGuardError("Application draft changed after approval")
        return row

    def begin_side_effect(self, task_id: UUID, fingerprint: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT t.status AS task_status, t.approved_by, t.payload,
                       a.*, ap.action_context_hash
                FROM agent_tasks t
                JOIN external_actions a ON a.task_id = t.id
                LEFT JOIN LATERAL (
                    SELECT action_context_hash FROM task_approvals
                    WHERE task_id = t.id AND decision = 'approved'
                    ORDER BY created_at DESC LIMIT 1
                ) ap ON true
                WHERE t.id = %s
                FOR UPDATE OF t, a
                """,
                (task_id,),
            ).fetchone()
            if row is None:
                raise ExternalActionNotFoundError(str(task_id))
            if row["task_status"] != "running" or row["status"] != "queued":
                raise SideEffectGuardError("External action is not in an executable state")
            if not row["approved_by"] or row["action_context_hash"] != row["context_hash"]:
                raise SideEffectGuardError("Exact action approval is missing or mismatched")
            if row["payload"].get("action_digest") != row["context_hash"]:
                raise SideEffectGuardError(
                    "Task action digest does not match durable action context"
                )
            if row["expires_at"] <= datetime.now(UTC):
                raise SideEffectGuardError("Approved external action has expired")
            receipt = connection.execute(
                "SELECT * FROM side_effect_receipts WHERE fingerprint = %s",
                (fingerprint,),
            ).fetchone()
            if receipt is not None:
                raise SideEffectGuardError(
                    f"Side effect already has a {receipt['status']} receipt; retry refused"
                )
            connection.execute(
                """
                INSERT INTO side_effect_receipts (
                    fingerprint, action_id, task_id, status
                ) VALUES (%s, %s, %s, 'executing')
                """,
                (fingerprint, row["id"], task_id),
            )
            action = connection.execute(
                """
                UPDATE external_actions SET status = 'executing'
                WHERE id = %s RETURNING *
                """,
                (row["id"],),
            ).fetchone()
            connection.commit()
        return action

    def complete_side_effect(
        self, task_id: UUID, fingerprint: str, external_reference: str
    ) -> None:
        with self.connect() as connection:
            action = connection.execute(
                """
                UPDATE external_actions
                SET status = 'succeeded', external_reference = %s,
                    executed_at = now(), last_error = NULL
                WHERE task_id = %s AND status = 'executing'
                RETURNING *
                """,
                (external_reference[:500], task_id),
            ).fetchone()
            if action is None:
                raise SideEffectGuardError("Executing external action was not found")
            connection.execute(
                """
                UPDATE side_effect_receipts
                SET status = 'succeeded', external_reference = %s, completed_at = now()
                WHERE fingerprint = %s AND task_id = %s AND status = 'executing'
                """,
                (external_reference[:500], fingerprint, task_id),
            )
            if action["action_type"] == "career.application_submit":
                connection.execute(
                    """
                    UPDATE job_opportunities
                    SET status = 'applied', applied_at = now()
                    WHERE id = %s
                    """,
                    (action["opportunity_id"],),
                )
            connection.commit()

    def fail_external_action(self, task_id: UUID, message: str) -> str:
        with self.connect() as connection:
            action = connection.execute(
                "SELECT * FROM external_actions WHERE task_id = %s FOR UPDATE",
                (task_id,),
            ).fetchone()
            if action is None:
                raise ExternalActionNotFoundError(str(task_id))
            receipt = connection.execute(
                "SELECT * FROM side_effect_receipts WHERE task_id = %s FOR UPDATE",
                (task_id,),
            ).fetchone()
            status = "ambiguous" if receipt is not None else "failed"
            connection.execute(
                "UPDATE external_actions SET status = %s, last_error = %s WHERE id = %s",
                (status, message[:1000], action["id"]),
            )
            if receipt is not None:
                connection.execute(
                    """
                    UPDATE side_effect_receipts
                    SET status = 'ambiguous', completed_at = now()
                    WHERE task_id = %s
                    """,
                    (task_id,),
                )
            connection.commit()
        return status
