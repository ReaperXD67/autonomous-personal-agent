from __future__ import annotations

import hmac
import json
from uuid import UUID

from psycopg import sql
from psycopg.types.json import Jsonb

from app.application_browser import canonical_hash
from app.creator_draft_content import (
    compose_ai_email,
    draft_digest,
    draft_input_snapshot,
    evidence_error,
    model_context,
    parse_model_copy,
)
from app.creator_draft_models import CreatorDraftCreate
from app.creator_learning import creator_learning_insights
from app.marketing import contact_is_suppressed
from app.marketing_store import (
    MarketingOutreachError,
    MarketingProspectNotFoundError,
    MarketingStore,
)
from app.models import TaskCreate
from app.policy import RiskLevel
from app.store import InvalidTaskStateError


class CreatorDraftNotFoundError(LookupError):
    pass


class CreatorDraftConflictError(MarketingOutreachError):
    pass


def lock_draft_for_prepare(connection, draft_id, prospect_id, digest):
    identity = connection.execute(
        "SELECT task_id FROM creator_email_drafts WHERE id=%s", (draft_id,),
    ).fetchone()
    if identity is None:
        raise CreatorDraftNotFoundError(str(draft_id))
    # Task -> draft -> campaign/prospect, matching completion and cancellation fences.
    task = connection.execute(
        "SELECT status FROM agent_tasks WHERE id=%s FOR UPDATE", (identity["task_id"],),
    ).fetchone()
    row = connection.execute(
        "SELECT * FROM creator_email_drafts WHERE id=%s FOR UPDATE", (draft_id,),
    ).fetchone()
    if (row["prospect_id"] != prospect_id or not row["draft_digest"]
            or not hmac.compare_digest(row["draft_digest"], digest)):
        raise CreatorDraftConflictError("Draft identity or reviewed digest does not match")
    if task["status"] != "succeeded" or row["status"] not in {"ready", "prepared"}:
        raise CreatorDraftConflictError("Only a successfully completed AI draft can be prepared")
    if row["status"] != "prepared":
        now = connection.execute("SELECT clock_timestamp() AS value").fetchone()["value"]
        if row["expires_at"] <= now:
            raise CreatorDraftConflictError("AI draft expired; generate and review a fresh draft")
    return row


def check_draft_context(row, campaign, prospect):
    if canonical_hash(draft_input_snapshot(campaign, prospect)) != row["input_hash"]:
        raise CreatorDraftConflictError(
            "Campaign, contact or research changed; generate and review a fresh AI draft"
        )
    error = evidence_error(campaign, prospect)
    if error:
        raise CreatorDraftConflictError(error)
    if row.get("model_copy") is not None:
        try:
            parse_model_copy(
                json.dumps(row["model_copy"]),
                row["model_context"],
            )
        except ValueError:
            raise CreatorDraftConflictError(
                "AI copy no longer meets current evidence checks; generate a fresh draft"
            ) from None


class CreatorDraftStore(MarketingStore):
    @staticmethod
    def _context(connection, prospect_id, *, lock=False):
        row = connection.execute(
            sql.SQL(
                "SELECT p.*, to_jsonb(c) AS _campaign FROM marketing_prospects p "
                "JOIN marketing_campaigns c ON c.id=p.campaign_id WHERE p.id=%s {}"
            ).format(sql.SQL("FOR UPDATE OF c,p" if lock else "")), (prospect_id,),
        ).fetchone()
        if row is None:
            raise MarketingProspectNotFoundError(str(prospect_id))
        campaign = row.pop("_campaign")
        return campaign, row

    @staticmethod
    def _eligible(connection, campaign, prospect):
        if (prospect["status"] not in {"discovered", "qualified"}
                or prospect["suppressed_at"] is not None
                or contact_is_suppressed(connection, prospect["contact_email"])):
            raise CreatorDraftConflictError(
                "This creator is no longer eligible for an introduction"
            )
        if not all(prospect.get(key) for key in (
            "contact_email", "contact_source_url", "contact_basis_note", "contact_authorized_at",
        )):
            raise CreatorDraftConflictError(
                "Review and authorize the public business contact first"
            )
        error = evidence_error(campaign, prospect)
        if error:
            raise CreatorDraftConflictError(error)

    def _view(self, connection, row):
        task = connection.execute(
            "SELECT status,error_code FROM agent_tasks WHERE id=%s", (row["task_id"],),
        ).fetchone()
        result = {
            **row, "task_status": task["status"],
            "evidence": row["model_context"]["evidence"],
            "learning_summary": row["model_context"]["learning_summary"],
        }
        if task["status"] in {"failed", "cancelled", "rejected", "dead_lettered"}:
            result.update(status="failed", error_code=row["error_code"] or "DRAFT_TASK_INTERRUPTED")
        elif row["status"] == "ready" and task["status"] != "succeeded":
            result["status"] = "queued"
        elif row["status"] in {"queued", "ready"}:
            campaign, prospect = self._context(connection, row["prospect_id"])
            now = connection.execute("SELECT clock_timestamp() AS value").fetchone()["value"]
            try:
                check_draft_context(row, campaign, prospect)
                self._eligible(connection, campaign, prospect)
                if row["expires_at"] <= now:
                    raise CreatorDraftConflictError("Draft expired")
            except CreatorDraftConflictError:
                result.update(status="stale", error_code="DRAFT_CONTEXT_CHANGED")
        # Internal snapshots include contact provenance; they are never returned to clients/model.
        return {key: value for key, value in result.items()
                if key not in {"input_snapshot", "input_hash", "model_context", "idempotency_key"}}

    def _audit_draft(self, connection, row, action, *, actor="creator-drafter"):
        task = connection.execute(
            "SELECT correlation_id FROM agent_tasks WHERE id=%s", (row["task_id"],),
        ).fetchone()
        self._append_audit(
            connection, correlation_id=task["correlation_id"], task_id=row["task_id"],
            actor_type="worker", actor_id=actor, tool_name="marketing.creator_draft",
            action=action, risk_level="medium", approval_status="not_applicable",
            execution_status=row["status"], input_metadata={"draft_id": str(row["id"])},
            result_metadata={"source": row["source"], "error_code": row["error_code"]},
        )

    def create_draft(self, prospect_id: UUID, request: CreatorDraftCreate):
        with self.connect() as connection:
            # Serialize the shared inference preparation cap independently of send budgets.
            connection.execute("SELECT pg_advisory_xact_lock(hashtext('creator-draft-budget'))")
            existing = connection.execute(
                "SELECT * FROM creator_email_drafts WHERE idempotency_key=%s",
                (request.idempotency_key,),
            ).fetchone()
            if existing:
                if (existing["prospect_id"] != prospect_id
                        or existing["requested_by"] != request.actor):
                    raise CreatorDraftConflictError("Idempotency key belongs to another request")
                return self._view(connection, existing)
            campaign, prospect = self._context(connection, prospect_id, lock=True)
            self._eligible(connection, campaign, prospect)
            counts = connection.execute(
                "SELECT count(*) AS total, count(*) FILTER (WHERE prospect_id=%s) AS creator "
                "FROM creator_email_drafts WHERE created_at > now()-interval '24 hours'",
                (prospect_id,),
            ).fetchone()
            if counts["total"] >= 30 or counts["creator"] >= 3:
                raise CreatorDraftConflictError(
                    "AI preparation limit reached: three per creator and thirty per rolling day"
                )
            learning = creator_learning_insights(
                self._feedback_in_connection(connection, campaign["id"]),
                self._variant_metrics_in_connection(connection, campaign["id"], paid=True),
            )
            snapshot = draft_input_snapshot(campaign, prospect)
            row = connection.execute(
                "INSERT INTO creator_email_drafts "
                "(campaign_id,prospect_id,requested_by,idempotency_key,input_snapshot,"
                "input_hash,model_context) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                (prospect["campaign_id"], prospect_id, request.actor, request.idempotency_key,
                 Jsonb(snapshot), canonical_hash(snapshot),
                 Jsonb(model_context(campaign, prospect, learning))),
            ).fetchone()
            task = self._create_task_record(connection, TaskCreate(
                title="Draft a creator-specific introduction for review",
                kind="marketing.creator_draft", payload={"draft_id": str(row["id"])},
                risk_level=RiskLevel.MEDIUM, requested_by=request.actor,
            ))
            row = connection.execute(
                "UPDATE creator_email_drafts SET task_id=%s WHERE id=%s RETURNING *",
                (task["id"], row["id"]),
            ).fetchone()
            self._audit_draft(connection, row, "creator_draft.created", actor=request.actor)
            return self._view(connection, row)

    def get_draft(self, draft_id):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM creator_email_drafts WHERE id=%s", (draft_id,),
            ).fetchone()
            if row is None:
                raise CreatorDraftNotFoundError(str(draft_id))
            return self._view(connection, row)

    def list_drafts(self, prospect_id):
        with self.connect() as connection:
            self._context(connection, prospect_id)
            rows = connection.execute(
                "SELECT * FROM creator_email_drafts WHERE prospect_id=%s "
                "ORDER BY created_at DESC LIMIT 20", (prospect_id,),
            ).fetchall()
            return [self._view(connection, row) for row in rows]

    @staticmethod
    def _owned_task(connection, task_id, lease_id):
        task = connection.execute(
            "SELECT * FROM agent_tasks WHERE id=%s FOR UPDATE", (task_id,),
        ).fetchone()
        now = connection.execute("SELECT clock_timestamp() AS value").fetchone()["value"]
        if (task is None or task["kind"] != "marketing.creator_draft"
                or task["status"] != "running" or task["lease_id"] != lease_id
                or task["cancellation_requested_at"] is not None
                or task["lease_expires_at"] is None or task["lease_expires_at"] <= now):
            raise InvalidTaskStateError("Creator drafting no longer owns a valid execution lease")
        return task

    def _execution_row(self, connection, draft_id, task_id, lease_id):
        self._owned_task(connection, task_id, lease_id)
        row = connection.execute(
            "SELECT * FROM creator_email_drafts WHERE id=%s AND task_id=%s FOR UPDATE",
            (draft_id, task_id),
        ).fetchone()
        if row is None:
            raise CreatorDraftConflictError("Draft is not linked to this task")
        campaign, prospect = self._context(connection, row["prospect_id"], lock=True)
        # Row waits can outlive a lease: recheck with clock_timestamp after all locks.
        self._owned_task(connection, task_id, lease_id)
        now = connection.execute("SELECT clock_timestamp() AS value").fetchone()["value"]
        if row["expires_at"] <= now:
            raise CreatorDraftConflictError("Draft expired before completion")
        check_draft_context(row, campaign, prospect)
        self._eligible(connection, campaign, prospect)
        return row, campaign, prospect

    def get_draft_for_execution(self, draft_id, task_id, lease_id):
        with self.connect() as connection:
            row, _, _ = self._execution_row(connection, draft_id, task_id, lease_id)
            return row

    def save_draft(self, *, draft_id, task_id, lease_id, copy, source, selected_model):
        with self.connect() as connection:
            row, campaign, prospect = self._execution_row(
                connection, draft_id, task_id, lease_id,
            )
            if row["status"] != "queued":
                raise CreatorDraftConflictError("Draft is no longer waiting for model output")
            copy = parse_model_copy(copy.model_dump_json(), row["model_context"])
            subject, body = compose_ai_email(campaign, prospect, copy)
            notes = [
                "Model wrote the hook and optional content idea; "
                "the server supplied terms and footer.",
                "Public metadata only. No claim that Hermes watched the video "
                "or verified audience reach.",
                "Lexical/schema checks passed; human review must still verify "
                "relevance and accuracy.",
                "English draft; exact approval is required. "
                "This draft grants no sending authority.",
            ]
            row = connection.execute(
                "UPDATE creator_email_drafts SET status='ready',source=%s,selected_model=%s,"
                "model_copy=%s,subject=%s,body=%s,draft_digest=%s,quality_notes=%s "
                "WHERE id=%s RETURNING *",
                (source, selected_model, Jsonb(copy.model_dump()), subject, body,
                 draft_digest(row["input_hash"], subject, body, source, selected_model),
                 Jsonb(notes), draft_id),
            ).fetchone()
            self._audit_draft(connection, row, "creator_draft.ready")
            return row

    def fail_draft(self, draft_id, task_id, lease_id, error_code):
        with self.connect() as connection:
            self._owned_task(connection, task_id, lease_id)
            row = connection.execute(
                "UPDATE creator_email_drafts SET status='failed',error_code=%s "
                "WHERE id=%s AND task_id=%s AND status='queued' RETURNING *",
                (error_code, draft_id, task_id),
            ).fetchone()
            if row:
                self._audit_draft(connection, row, "creator_draft.failed")
