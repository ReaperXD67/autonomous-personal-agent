"""Private local reply curation; no method prepares, approves or sends an email."""

from __future__ import annotations

from contextlib import suppress
from uuid import UUID

from psycopg.types.json import Jsonb

from app.application_browser import canonical_hash
from app.creator_automation import correlate_creator_reply
from app.creator_automation_store import (
    CreatorAutomationStore,
    complete_reply_body,
    lock_automation,
)
from app.creator_draft_store import CreatorDraftStore
from app.creator_reply_content import (
    compose_reply_email,
    reply_model_context,
    validate_reply_copy,
)
from app.creator_reply_draft_models import CreatorReplyDraftCreate
from app.marketing import (
    campaign_outreach_snapshot,
    contact_is_suppressed,
    contact_outreach_snapshot,
)
from app.marketing_store import MarketingOutreachError
from app.models import TaskCreate
from app.store import InvalidTaskStateError

KIND = "marketing.creator_reply_draft"
CREATED = "creator.reply_draft.created"


class CreatorReplyDraftConflictError(MarketingOutreachError):
    pass


def reply_draft_snapshot(campaign, prospect, reply):
    return {
        "campaign_id": str(campaign["id"]), "reply_id": str(reply["id"]),
        "prospect_id": str(prospect["id"]), "reply_body_digest": reply["body_digest"],
        "reply_subject": reply["subject"], "creator_name": prospect["display_name"],
        "campaign": campaign_outreach_snapshot(campaign),
        "contact": contact_outreach_snapshot(prospect),
    }


class CreatorReplyDraftStore(CreatorDraftStore):
    def _reply_context(self, connection, campaign_id, reply_id):
        reply = connection.execute(
            "SELECT * FROM creator_reply_messages WHERE id=%s AND campaign_id=%s FOR UPDATE",
            (reply_id, campaign_id),
        ).fetchone()
        if reply is None or reply["prospect_id"] is None:
            raise CreatorReplyDraftConflictError("Reply has no creator match in this campaign")
        campaign, prospect = self._context(connection, reply["prospect_id"], lock=True)
        if (str(campaign["id"]) != str(campaign_id) or not complete_reply_body(reply)
                or prospect["suppressed_at"] is not None
                or prospect["status"] in {"suppressed", "bounced", "handed_off", "converted"}
                or reply["reviewed_classification"] in {"do_not_contact", "bounced", "ignore"}
                or not prospect["contact_email"]
                or prospect["contact_email"].casefold() != reply["sender"].casefold()
                or contact_is_suppressed(connection, reply["sender"])):
            raise CreatorReplyDraftConflictError("Reply needs complete unsuppressed evidence")
        sent = connection.execute(
            "SELECT m.prospect_id,a.public_context->>'recipient' AS recipient,"
            "a.public_context->>'subject' AS subject,a.executed_at AS sent_at "
            "FROM marketing_outreach_messages m JOIN external_actions a ON a.id=m.action_id "
            "WHERE m.prospect_id=%s AND a.status='succeeded' AND a.executed_at IS NOT NULL "
            "ORDER BY a.executed_at DESC LIMIT 2000", (prospect["id"],),
        ).fetchall()
        if correlate_creator_reply(reply, sent)[0] != prospect["id"]:
            raise CreatorReplyDraftConflictError("Reply has no exact prior accepted outreach match")
        return campaign, prospect, reply

    def _audit_reply_draft(self, connection, row, action, actor):
        task = connection.execute(
            "SELECT correlation_id FROM agent_tasks WHERE id=%s", (row["task_id"],),
        ).fetchone()
        self._append_audit(
            connection, correlation_id=task["correlation_id"], task_id=row["task_id"],
            actor_type="worker" if actor == "creator-reply-worker" else "user", actor_id=actor,
            tool_name=KIND, action=action, risk_level="medium", approval_status="not_required",
            execution_status=row["status"], input_metadata={
                "reply_draft_id": str(row["id"]), "input_hash": row["input_hash"],
                "context_digest": canonical_hash(row["model_context"]),
                "reply_body_digest": row["reply_body_digest"], "sending_authority": False,
            }, result_metadata={"error_code": row["error_code"], "source": row["source"]},
        )

    def _create_reply_draft(self, connection, campaign_id, reply_id, request):
        campaign, prospect, reply = self._reply_context(connection, campaign_id, reply_id)
        if reply["body_digest"] != request.body_digest:
            raise CreatorReplyDraftConflictError("Reply body digest changed before curation")
        snapshot = reply_draft_snapshot(campaign, prospect, reply)
        context = reply_model_context(campaign, prospect, reply)
        input_hash = canonical_hash({"snapshot": snapshot, "model_context": context})
        existing = connection.execute(
            "SELECT * FROM creator_reply_drafts WHERE input_hash=%s", (input_hash,),
        ).fetchone()
        if existing is not None:
            return existing, False
        counts = self._draft_budget_counts(connection, prospect["id"])
        if counts["total"] >= 30 or counts["creator"] >= 3:
            raise CreatorReplyDraftConflictError(
                "AI preparation limit reached: three per creator and thirty per rolling day",
            )
        row = connection.execute(
            "INSERT INTO creator_reply_drafts(campaign_id,reply_id,prospect_id,requested_by,"
            "reply_body_digest,input_snapshot,input_hash,model_context) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (campaign_id, reply_id, prospect["id"], request.actor, reply["body_digest"],
             Jsonb(snapshot), input_hash, Jsonb(context)),
        ).fetchone()
        task = self._create_task_record(connection, TaskCreate(
            title="Curate a private creator reply draft", kind=KIND,
            payload={"reply_draft_id": str(row["id"])}, requested_by=request.actor,
            idempotency_key=f"creator-reply-draft:{input_hash}",
        ))
        row = connection.execute(
            "UPDATE creator_reply_drafts SET task_id=%s WHERE id=%s RETURNING *",
            (task["id"], row["id"]),
        ).fetchone()
        self._audit_reply_draft(connection, row, CREATED, request.actor)
        return row, True

    def queue_reply_draft(self, campaign_id, reply_id, request):
        with self.connect() as connection:
            self._draft_budget_lock(connection)
            lock_automation(connection)
            row, _ = self._create_reply_draft(connection, campaign_id, reply_id, request)
            result = self._view_reply_draft(connection, row)
            connection.commit()
        return result

    def queue_automatic_reply_drafts(self, task, campaign_id):
        counts = {"created": 0, "existing": 0, "skipped": 0}
        with self.connect() as connection:
            self._draft_budget_lock(connection)
            lock_automation(connection)
            CreatorAutomationStore._check_task(connection, task, "marketing.gmail_sync")
            if UUID(str(task["payload"]["campaign_id"])) != campaign_id:
                raise CreatorReplyDraftConflictError("Curation campaign differs from the sync task")
            if not connection.execute(
                "SELECT 1 FROM creator_gmail_sync_state s JOIN agent_tasks t ON t.id=%s "
                "WHERE s.campaign_id=%s AND s.page_token IS NULL "
                "AND s.pending_message_ids='[]'::jsonb AND s.last_complete_at>=t.started_at",
                (task["id"], campaign_id),
            ).fetchone():
                raise CreatorReplyDraftConflictError("Curation needs a completed labeled sync")
            candidates = connection.execute(
                "SELECT id,body_digest FROM creator_reply_messages WHERE campaign_id=%s "
                "AND body_status='complete' AND prospect_id IS NOT NULL "
                "AND (reviewed_classification IS NULL OR reviewed_classification NOT IN "
                "('do_not_contact','bounced','ignore')) ORDER BY received_at DESC,id LIMIT 30",
                (campaign_id,),
            ).fetchall()
            for candidate in candidates:
                if counts["created"] >= 3:
                    break
                try:
                    _, created = self._create_reply_draft(
                        connection, campaign_id, candidate["id"], CreatorReplyDraftCreate(
                            actor="scheduler:creator-reply-drafts",
                            body_digest=candidate["body_digest"],
                        ),
                    )
                    counts["created" if created else "existing"] += 1
                except (CreatorReplyDraftConflictError, ValueError):
                    counts["skipped"] += 1
            CreatorAutomationStore._check_task(connection, task, "marketing.gmail_sync")
            connection.commit()
        return counts

    @staticmethod
    def _owned_reply_task(connection, draft_id, task_id, lease_id):
        task = connection.execute(
            "SELECT * FROM agent_tasks WHERE id=%s FOR UPDATE", (task_id,),
        ).fetchone()
        now = connection.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
        if (not task or task["kind"] != KIND or task["status"] != "running"
                or task["lease_id"] != lease_id or task["cancellation_requested_at"] is not None
                or task["lease_expires_at"] is None or task["lease_expires_at"] <= now
                or task["payload"] != {"reply_draft_id": str(draft_id)}):
            raise InvalidTaskStateError("Reply curation no longer owns its exact execution lease")
        return task

    def _reply_execution_row(self, connection, draft_id, task_id, lease_id):
        self._owned_reply_task(connection, draft_id, task_id, lease_id)
        row = connection.execute(
            "SELECT * FROM creator_reply_drafts WHERE id=%s AND task_id=%s FOR UPDATE",
            (draft_id, task_id),
        ).fetchone()
        if row is None:
            raise CreatorReplyDraftConflictError("Reply draft is not linked to this task")
        lock_automation(connection)
        campaign, prospect, reply = self._reply_context(
            connection, row["campaign_id"], row["reply_id"],
        )
        context = reply_model_context(campaign, prospect, reply)
        snapshot = reply_draft_snapshot(campaign, prospect, reply)
        if (snapshot != row["input_snapshot"] or context != row["model_context"]
                or canonical_hash({"snapshot": snapshot, "model_context": context})
                != row["input_hash"]
                or not connection.execute(
                    "SELECT 1 FROM audit_events WHERE task_id=%s AND action=%s "
                    "AND input_metadata->>'reply_draft_id'=%s "
                    "AND input_metadata->>'input_hash'=%s "
                    "AND input_metadata->>'context_digest'=%s LIMIT 1",
                    (task_id, CREATED, str(draft_id), row["input_hash"], canonical_hash(context)),
                ).fetchone()):
            raise CreatorReplyDraftConflictError("Frozen reply curation context or audit changed")
        self._owned_reply_task(connection, draft_id, task_id, lease_id)
        if row["expires_at"] <= connection.execute(
            "SELECT clock_timestamp() AS now",
        ).fetchone()["now"]:
            raise CreatorReplyDraftConflictError("Reply draft expired before completion")
        return row, campaign, prospect, reply

    def get_reply_draft_for_execution(self, draft_id, task_id, lease_id):
        with self.connect() as connection:
            row, _, _, _ = self._reply_execution_row(connection, draft_id, task_id, lease_id)
            return row

    def start_reply_inference_invocation(
        self, *, draft_id, task_id, lease_id, requested_model,
    ):
        if (not isinstance(requested_model, str) or not requested_model
                or len(requested_model) > 200):
            raise CreatorReplyDraftConflictError("Configured local reply model is invalid")
        with self.connect() as connection:
            self._reply_execution_row(connection, draft_id, task_id, lease_id)
            if connection.execute(
                "SELECT 1 FROM inference_invocations WHERE task_id=%s AND purpose=%s LIMIT 1",
                (task_id, KIND),
            ).fetchone():
                return None
            invocation = connection.execute(
                "INSERT INTO inference_invocations(task_id,purpose,provider,requested_models,"
                "privacy_mode) VALUES (%s,%s,'ollama',%s,'local_only') RETURNING id",
                (task_id, KIND, Jsonb([requested_model])),
            ).fetchone()
            self._owned_reply_task(connection, draft_id, task_id, lease_id)
            connection.commit()
        return invocation["id"]

    def save_reply_draft(self, *, draft_id, task_id, lease_id, copy, selected_model):
        with self.connect() as connection:
            row, campaign, prospect, reply = self._reply_execution_row(
                connection, draft_id, task_id, lease_id,
            )
            if row["status"] != "queued":
                raise CreatorReplyDraftConflictError("Reply draft is no longer awaiting a response")
            copy = validate_reply_copy(copy, row["model_context"])
            subject, body = compose_reply_email(
                campaign, prospect, reply, copy, row["model_context"],
            )
            if (not isinstance(subject, str) or not subject or len(subject) > 600
                    or not isinstance(body, str) or not body or len(body) > 20000):
                raise CreatorReplyDraftConflictError("Reply draft exceeds its fixed copy bounds")
            row = connection.execute(
                "UPDATE creator_reply_drafts SET status='ready',source='ollama',selected_model=%s,"
                "model_copy=%s,subject=%s,body=%s,draft_digest=%s WHERE id=%s RETURNING *",
                (selected_model, Jsonb(copy), subject, body, canonical_hash({
                    "input_hash": row["input_hash"], "copy": copy, "source": "ollama",
                    "selected_model": selected_model,
                }), draft_id),
            ).fetchone()
            self._audit_reply_draft(connection, row, "creator.reply_draft.ready",
                                    "creator-reply-worker")
            self._owned_reply_task(connection, draft_id, task_id, lease_id)
            connection.commit()
        return {"id": row["id"], "status": row["status"], "draft_digest": row["draft_digest"]}

    def fail_reply_draft(self, draft_id, task_id, lease_id, error_code):
        codes = {"CREATOR_REPLY_DRAFT_MODEL_UNAVAILABLE", "CREATOR_REPLY_DRAFT_OUTPUT_INVALID",
                 "CREATOR_REPLY_DRAFT_CONTEXT_CHANGED"}
        if error_code not in codes:
            error_code = "CREATOR_REPLY_DRAFT_MODEL_UNAVAILABLE"
        with self.connect() as connection:
            self._owned_reply_task(connection, draft_id, task_id, lease_id)
            row = connection.execute(
                "UPDATE creator_reply_drafts SET status='failed',error_code=%s "
                "WHERE id=%s AND task_id=%s AND status='queued' RETURNING *",
                (error_code, draft_id, task_id),
            ).fetchone()
            if row is not None:
                self._audit_reply_draft(connection, row, "creator.reply_draft.failed",
                                        "creator-reply-worker")
            connection.commit()

    def _view_reply_draft(self, connection, row):
        task = connection.execute(
            "SELECT status,error_code,clock_timestamp() AS now FROM agent_tasks WHERE id=%s",
            (row["task_id"],),
        ).fetchone()
        prospect = connection.execute(
            "SELECT * FROM marketing_prospects WHERE id=%s", (row["prospect_id"],),
        ).fetchone()
        authorized = bool(prospect and prospect["contact_authorized_at"]
                          and not prospect["suppressed_at"]
                          and contact_outreach_snapshot(prospect)
                          == row["input_snapshot"]["contact"]
                          and not contact_is_suppressed(connection, prospect["contact_email"]))
        campaign = connection.execute(
            "SELECT * FROM marketing_campaigns WHERE id=%s", (row["campaign_id"],),
        ).fetchone()
        reply = connection.execute(
            "SELECT * FROM creator_reply_messages WHERE id=%s", (row["reply_id"],),
        ).fetchone()
        current = False
        if campaign and prospect and reply and complete_reply_body(reply):
            with suppress(ValueError):
                current = canonical_hash({
                    "snapshot": reply_draft_snapshot(campaign, prospect, reply),
                    "model_context": reply_model_context(campaign, prospect, reply),
                }) == row["input_hash"] and row["expires_at"] > task["now"]
        result = {key: value for key, value in row.items()
                  if key not in {"input_snapshot", "model_context"}}
        if row["status"] == "queued" and task["status"] in {"failed", "dead_lettered", "cancelled"}:
            result["status"] = "cancelled" if task["status"] == "cancelled" else "failed"
            result["error_code"] = task["error_code"]
        if row["status"] == "ready":
            copy = validate_reply_copy(row["model_copy"], row["model_context"])
            if (row["subject"] != copy["subject"] or row["body"] != copy["body"]
                    or row["draft_digest"] != canonical_hash({
                        "input_hash": row["input_hash"], "copy": copy, "source": "ollama",
                        "selected_model": row["selected_model"],
                    })):
                raise CreatorReplyDraftConflictError("Stored reply draft digest no longer matches")
        result.update(
            sending_authority=False, contact_authorized=authorized,
            context_current=(current and task["status"] not in {
                "failed", "dead_lettered", "cancelled",
            }),
            send_hold_reason=("Draft-only curation grants no sending authority" if authorized
                              else "Contact authorization is withdrawn; draft only"),
        )
        return result

    def list_reply_drafts(self, campaign_id, reply_id):
        with self.connect() as connection:
            if not connection.execute(
                "SELECT 1 FROM creator_reply_messages WHERE id=%s AND campaign_id=%s",
                (reply_id, campaign_id),
            ).fetchone():
                raise CreatorReplyDraftConflictError("Creator reply not found in this campaign")
            rows = connection.execute(
                "SELECT * FROM creator_reply_drafts WHERE campaign_id=%s AND reply_id=%s "
                "ORDER BY created_at DESC,id LIMIT 30", (campaign_id, reply_id),
            ).fetchall()
            return [self._view_reply_draft(connection, row) for row in rows]
