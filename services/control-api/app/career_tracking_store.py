from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.career_store import CareerProfileNotFoundError, CareerStore, OpportunityNotFoundError
from app.career_tracking import GmailSyncError, correlate_message
from app.career_tracking_models import TRACKING_STATUSES, CareerEventCreate


class CareerTrackingConflictError(RuntimeError):
    pass


class CareerTrackingStore(CareerStore):
    @staticmethod
    def _applications(connection: Any, profile_id: UUID) -> list[dict[str, Any]]:
        return connection.execute(
            """
            SELECT id, profile_id, company, title, source, source_url, apply_url, applied_at
            FROM job_opportunities WHERE profile_id = %s AND applied_at IS NOT NULL
            ORDER BY applied_at DESC LIMIT 2000
            """, (profile_id,),
        ).fetchall()

    def gmail_sync_context(self, profile_id: UUID, mailbox_key: str,
                           label_name: str) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO career_gmail_sync_state (profile_id, mailbox_key, label_name)
                VALUES (%s, %s, %s) ON CONFLICT (profile_id) DO NOTHING
                """, (profile_id, mailbox_key, label_name),
            )
            context = connection.execute(
                "SELECT * FROM career_gmail_sync_state WHERE profile_id = %s FOR UPDATE",
                (profile_id,),
            ).fetchone()
            if context["mailbox_key"] != mailbox_key:
                raise GmailSyncError(
                    "The mailbox differs from this profile's recorded Gmail account"
                )
            if context["label_name"] != label_name:
                # A changed explicit label resets paging, never expands to the whole mailbox.
                context = connection.execute(
                    """UPDATE career_gmail_sync_state SET label_name = %s, page_token = NULL,
                       pending_message_ids = '[]'::jsonb, revision = revision + 1
                       WHERE profile_id = %s RETURNING *""", (label_name, profile_id),
                ).fetchone()
            context["applications"] = self._applications(connection, profile_id)
            context["bindings"] = connection.execute(
                "SELECT * FROM career_gmail_threads WHERE profile_id = %s", (profile_id,),
            ).fetchall()
            connection.commit()
        return context

    def known_gmail_messages(self, profile_id: UUID, message_ids: list[str]) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT gmail_message_id FROM career_gmail_messages "
                "WHERE profile_id = %s AND gmail_message_id = ANY(%s)",
                (profile_id, message_ids),
            ).fetchall()
        return {row["gmail_message_id"] for row in rows}

    @staticmethod
    def _bind_thread(connection: Any, profile_id: UUID, message: dict[str, Any],
                     opportunity_id: UUID, source: str) -> None:
        saved = connection.execute(
            """
            INSERT INTO career_gmail_threads
                (profile_id, gmail_thread_id, opportunity_id, sender_domain, source)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (profile_id, gmail_thread_id) DO UPDATE SET source =
                CASE WHEN career_gmail_threads.source = 'manual'
                     THEN 'manual' ELSE EXCLUDED.source END
            WHERE career_gmail_threads.opportunity_id = EXCLUDED.opportunity_id
              AND career_gmail_threads.sender_domain = EXCLUDED.sender_domain
            RETURNING opportunity_id
            """,
            (profile_id, message["gmail_thread_id"], opportunity_id,
             message["sender"].rpartition("@")[2], source),
        ).fetchone()
        if saved is None:
            raise CareerTrackingConflictError("This Gmail thread has another recorded application")

    def save_gmail_sync(
        self, profile_id: UUID, context: dict[str, Any], messages: list[dict[str, Any]], *,
        page_token: str | None, pending_message_ids: list[str], task_id: UUID, lease_id: UUID,
    ) -> dict[str, int]:
        inserted, matched = 0, 0
        with self.connect() as connection:
            owned = connection.execute(
                """SELECT id FROM agent_tasks WHERE id = %s AND lease_id = %s
                   AND kind = 'career.gmail_sync' AND status = 'running'
                   AND lease_expires_at > clock_timestamp()
                   AND cancellation_requested_at IS NULL FOR UPDATE""", (task_id, lease_id),
            ).fetchone()
            if owned is None:
                raise GmailSyncError("Gmail sync lost its lease or was cancelled before saving")
            state = connection.execute(
                "SELECT * FROM career_gmail_sync_state WHERE profile_id = %s FOR UPDATE",
                (profile_id,),
            ).fetchone()
            if state is None or any(state[key] != context[key] for key in (
                "revision", "mailbox_key", "label_name",
            )):
                raise GmailSyncError("A newer Gmail sync changed the cursor; retry this sync")
            profile = connection.execute(
                "SELECT application_identity FROM career_profiles WHERE id = %s FOR SHARE",
                (profile_id,),
            ).fetchone()
            mailbox = (profile["application_identity"] or {}).get("email", "").casefold()
            if hashlib.sha256(mailbox.encode()).hexdigest() != state["mailbox_key"]:
                raise GmailSyncError("Career profile email changed during Gmail sync")
            applications = self._applications(connection, profile_id)
            bindings = connection.execute(
                "SELECT * FROM career_gmail_threads WHERE profile_id = %s", (profile_id,),
            ).fetchall()
            for message in messages:
                opportunity_id, reason = correlate_message(message, applications, bindings)
                needs_review = message["needs_review"] or opportunity_id is None
                saved = connection.execute(
                    """
                    INSERT INTO career_gmail_messages (
                        profile_id, gmail_message_id, gmail_thread_id, sender, subject, snippet,
                        received_at, opportunity_id, suggested_status, confidence, evidence,
                        match_reason, meeting_at, needs_review
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (profile_id, gmail_message_id) DO NOTHING RETURNING gmail_message_id
                    """,
                    (profile_id, message["gmail_message_id"], message["gmail_thread_id"],
                     message["sender"], message["subject"], message["snippet"],
                     message["received_at"],
                     opportunity_id, message["suggested_status"], message["confidence"],
                     message["evidence"], reason, message["meeting_at"], needs_review),
                ).fetchone()
                if saved is None:
                    continue
                inserted += 1
                if opportunity_id is not None:
                    self._bind_thread(connection, profile_id, message, opportunity_id, "gmail")
                    bindings.append({"gmail_thread_id": message["gmail_thread_id"],
                                     "opportunity_id": opportunity_id,
                                     "sender_domain": message["sender"].rpartition("@")[2]})
                    connection.execute(
                        """
                        INSERT INTO career_application_events (
                            opportunity_id, profile_id, status, source, confidence, evidence,
                            occurred_at, meeting_at, needs_review, gmail_message_id, actor
                        ) VALUES (%s, %s, %s, 'gmail', %s, %s, %s, %s, %s, %s, 'career-worker')
                        ON CONFLICT DO NOTHING
                        """,
                        (opportunity_id, profile_id, message["suggested_status"],
                         message["confidence"], message["evidence"], message["received_at"],
                         message["meeting_at"], needs_review, message["gmail_message_id"]),
                    )
                    matched += 1
            connection.execute(
                """UPDATE career_gmail_sync_state SET page_token = %s, pending_message_ids = %s,
                   revision = revision + 1, last_sync_at = now() WHERE profile_id = %s""",
                (page_token, Jsonb(pending_message_ids), profile_id),
            )
            self._append_audit(
                connection, correlation_id=uuid4(), task_id=task_id, actor_type="agent",
                actor_id="career-worker", tool_name="career.gmail_sync",
                action="career.gmail_synced",
                risk_level="low", approval_status="not_required", execution_status="succeeded",
                input_metadata={"profile_id": str(profile_id)},
                result_metadata={"stored": inserted, "matched": matched,
                                 "review_candidates": inserted - matched},
            )
            connection.commit()
        return {"stored": inserted, "matched": matched, "review_candidates": inserted - matched}

    def record_application_event(self, opportunity_id: UUID,
                                 request: CareerEventCreate) -> dict[str, Any]:
        with self.connect() as connection:
            opportunity = connection.execute(
                "SELECT * FROM job_opportunities WHERE id = %s FOR UPDATE", (opportunity_id,),
            ).fetchone()
            if opportunity is None:
                raise OpportunityNotFoundError(str(opportunity_id))
            profile_id = opportunity["profile_id"]
            if opportunity["applied_at"] is None and request.status != "submitted":
                raise CareerTrackingConflictError("Record the application as submitted first")
            occurred_at = request.occurred_at or datetime.now(UTC)
            needs_review = request.status == "needs_review" or (
                request.status == "interview" and request.meeting_at is None
            )
            if request.gmail_message_id:
                message = connection.execute(
                    """SELECT * FROM career_gmail_messages WHERE profile_id = %s
                       AND gmail_message_id = %s FOR UPDATE""",
                    (profile_id, request.gmail_message_id),
                ).fetchone()
                if message is None:
                    raise CareerTrackingConflictError(
                        "Gmail candidate does not belong to this profile"
                    )
                if message["opportunity_id"] not in (None, opportunity_id):
                    raise CareerTrackingConflictError(
                        "Gmail message belongs to another application"
                    )
                self._bind_thread(connection, profile_id, message, opportunity_id, "manual")
                connection.execute(
                    """UPDATE career_gmail_messages SET opportunity_id = %s, suggested_status = %s,
                       confidence = 'manual', evidence = %s, match_reason = 'Manually reviewed',
                       meeting_at = %s, needs_review = %s
                       WHERE profile_id = %s AND gmail_message_id = %s""",
                    (opportunity_id, request.status, request.note, request.meeting_at,
                     needs_review, profile_id, request.gmail_message_id),
                )
            if request.status == "submitted":
                connection.execute(
                    """UPDATE job_opportunities SET status = 'applied',
                       applied_at = COALESCE(applied_at, %s) WHERE id = %s""",
                    (occurred_at, opportunity_id),
                )
            event = connection.execute(
                """
                INSERT INTO career_application_events (
                    opportunity_id, profile_id, status, source, confidence, evidence, occurred_at,
                    meeting_at, needs_review, gmail_message_id, actor
                ) VALUES (%s, %s, %s, 'manual', 'manual', %s, %s, %s, %s, %s, %s) RETURNING *
                """,
                (opportunity_id, profile_id, request.status, request.note, occurred_at,
                 request.meeting_at, needs_review, request.gmail_message_id, request.actor),
            ).fetchone()
            self._append_audit(
                connection, correlation_id=uuid4(), task_id=None, actor_type="user",
                actor_id=request.actor, tool_name="career.tracking", action="career.event_recorded",
                risk_level="medium", approval_status="not_required", execution_status="recorded",
                input_metadata={"opportunity_id": str(opportunity_id), "status": request.status,
                                "source": "manual", "gmail_candidate_linked":
                                request.gmail_message_id is not None},
            )
            connection.commit()
        return event

    def tracking(self, *, profile_id: UUID | None = None, limit: int = 100) -> dict[str, Any]:
        with self.connect() as connection:
            if profile_id is not None and connection.execute(
                "SELECT id FROM career_profiles WHERE id = %s", (profile_id,),
            ).fetchone() is None:
                raise CareerProfileNotFoundError(str(profile_id))
            applications = connection.execute(
                """
                SELECT o.id AS opportunity_id, o.profile_id, o.company, o.title, o.apply_url,
                       o.applied_at, COALESCE(e.status, 'submitted') AS status,
                       COALESCE(e.source, 'application_record') AS status_source,
                       COALESCE(e.confidence, 'recorded') AS confidence,
                       COALESCE(e.evidence, 'Application submission recorded; response unconfirmed')
                           AS evidence,
                       e.meeting_at, COALESCE(e.needs_review, false) AS needs_review,
                       COALESCE(e.created_at, o.applied_at) AS updated_at,
                       COALESCE((SELECT jsonb_agg(to_jsonb(history)) FROM (
                           SELECT id, status, source, confidence, evidence, occurred_at,
                                  meeting_at, needs_review, gmail_message_id
                           FROM career_application_events WHERE opportunity_id = o.id
                           ORDER BY occurred_at DESC, created_at DESC LIMIT 20
                       ) AS history), '[]'::jsonb) AS events
                FROM job_opportunities o LEFT JOIN LATERAL (
                    SELECT * FROM career_application_events WHERE opportunity_id = o.id
                    ORDER BY occurred_at DESC, created_at DESC LIMIT 1
                ) e ON true
                WHERE o.applied_at IS NOT NULL AND (%s::uuid IS NULL OR o.profile_id = %s)
                ORDER BY COALESCE(e.created_at, o.applied_at) DESC LIMIT %s
                """, (profile_id, profile_id, limit),
            ).fetchall()
            candidates = connection.execute(
                """SELECT profile_id, gmail_message_id, gmail_thread_id, sender, subject, snippet,
                          received_at, suggested_status, confidence, evidence,
                          match_reason, needs_review
                   FROM career_gmail_messages WHERE opportunity_id IS NULL
                     AND (%s::uuid IS NULL OR profile_id = %s)
                   ORDER BY received_at DESC LIMIT %s""", (profile_id, profile_id, limit),
            ).fetchall()
            sync = connection.execute(
                """SELECT profile_id, label_name, last_sync_at,
                          jsonb_array_length(pending_message_ids) AS pending_count
                   FROM career_gmail_sync_state WHERE (%s::uuid IS NULL OR profile_id = %s)""",
                (profile_id, profile_id),
            ).fetchall()
        summary = dict.fromkeys(TRACKING_STATUSES, 0)
        for application in applications:
            summary[application["status"]] += 1
        summary["total"] = len(applications)
        suggestions = []
        if candidates:
            suggestions.append("Review unmatched Gmail messages before assigning an outcome.")
        if any(item["status"] == "interview" and item["needs_review"] for item in applications):
            suggestions.append("Confirm interview dates and time zones in the original message.")
        if len(applications) >= 10 and summary["rejected"] >= 5:
            suggestions.append(
                f"{summary['rejected']} of {len(applications)} displayed applications "
                "currently show rejection. Review role fit and application material; "
                "this does not establish a cause."
            )
        return {"applications": applications, "review_candidates": candidates, "sync": sync,
                "summary": summary, "summary_scope": "displayed_applications",
                "suggestions": suggestions}
