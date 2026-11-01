from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from app.action_models import EmailActionCreate
from app.action_store import ActionPreparationError, ActionStore
from app.application_browser import canonical_hash
from app.career_application_quality import application_quality_blocker
from app.career_autopilot import opportunity_hash, profile_hash, target_key
from app.career_contact_models import CareerContactCreate, CareerContactEmailPlan
from app.career_contacts import (
    contact_scope_error,
    contact_snapshot,
    email_content_error,
    sender_identity_error,
)
from app.career_store import OpportunityNotFoundError
from app.marketing import contact_is_suppressed


class CareerContactNotFoundError(LookupError):
    pass


class CareerContactStore(ActionStore):
    @staticmethod
    def _audit_contact(connection: Any, contact: dict[str, Any], actor: str,
                       action: str) -> None:
        ActionStore._append_audit(
            connection, correlation_id=uuid4(), task_id=None, actor_type="user",
            actor_id=actor, action=action, risk_level="medium", approval_status="not_required",
            execution_status="succeeded", tool_name="career.contact_review",
            input_metadata={"contact_id": str(contact["id"]),
                            "opportunity_id": str(contact["opportunity_id"]),
                            "kind": contact["kind"]},
        )

    @staticmethod
    def _job_profile(connection: Any, opportunity_id: UUID) -> tuple[dict, dict]:
        opportunity = connection.execute(
            "SELECT * FROM job_opportunities WHERE id = %s FOR SHARE", (opportunity_id,),
        ).fetchone()
        if opportunity is None:
            raise OpportunityNotFoundError(str(opportunity_id))
        profile = connection.execute(
            "SELECT * FROM career_profiles WHERE id = %s FOR SHARE",
            (opportunity["profile_id"],),
        ).fetchone()
        return opportunity, profile

    def list_contacts(self, opportunity_id: UUID) -> list[dict[str, Any]]:
        with self.connect() as connection:
            self._job_profile(connection, opportunity_id)
            return connection.execute(
                "SELECT c.*, a.action_id FROM career_contacts c "
                "LEFT JOIN career_contact_actions a ON a.contact_id = c.id "
                "WHERE c.opportunity_id = %s ORDER BY c.reviewed_at DESC LIMIT 100",
                (opportunity_id,),
            ).fetchall()

    def review_contact(self, opportunity_id: UUID,
                       request: CareerContactCreate) -> dict[str, Any]:
        with self.connect() as connection:
            opportunity, profile = self._job_profile(connection, opportunity_id)
            now = connection.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
            provisional = {
                "profile_hash": profile_hash(profile),
                "opportunity_hash": opportunity_hash(opportunity),
                "expires_at": now + timedelta(hours=request.validity_hours),
            }
            error = contact_scope_error(provisional, profile, opportunity, now)
            if error:
                raise ActionPreparationError(error)
            if contact_is_suppressed(connection, request.email):
                raise ActionPreparationError("This address is durably suppressed")
            row = connection.execute(
                "INSERT INTO career_contacts (profile_id, opportunity_id, email, kind, "
                "source_url, evidence_quote, basis_note, reviewed_by, profile_hash, "
                "opportunity_hash, reviewed_at, expires_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                (profile["id"], opportunity_id, request.email, request.kind,
                 request.source_url, request.evidence_quote, request.basis_note,
                 request.reviewed_by, provisional["profile_hash"],
                 provisional["opportunity_hash"], now, provisional["expires_at"]),
            ).fetchone()
            self._audit_contact(connection, row, request.reviewed_by, "career.contact_reviewed")
            connection.commit()
            return row

    def revoke_contact(self, contact_id: UUID, actor: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "UPDATE career_contacts SET revoked_at = COALESCE(revoked_at, now()), "
                "revoked_by = COALESCE(revoked_by, %s) WHERE id = %s RETURNING *",
                (actor, contact_id),
            ).fetchone()
            if row is None:
                raise CareerContactNotFoundError(str(contact_id))
            self._audit_contact(connection, row, actor, "career.contact_revoked")
            connection.commit()
            return row

    def prepare_contact_email(self, contact_id: UUID, request: CareerContactEmailPlan,
                              *, sender: str) -> dict[str, Any]:
        with self.connect() as connection:
            # One first contact per profile + canonical job + address, even if a
            # source is imported twice or the operator reviews another contact row.
            contact = connection.execute(
                "SELECT * FROM career_contacts WHERE id = %s FOR SHARE", (contact_id,),
            ).fetchone()
            if contact is None:
                raise CareerContactNotFoundError(str(contact_id))
            opportunity, profile = self._job_profile(connection, contact["opportunity_id"])
            target = target_key(opportunity["apply_url"])
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"career-contact:{profile['id']}:{target}:{contact['email']}",),
            )
            now = connection.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
            error = contact_scope_error(contact, profile, opportunity, now)
            error = error or sender_identity_error(profile, sender)
            if error:
                raise ActionPreparationError(error)
            if contact_is_suppressed(connection, contact["email"]):
                raise ActionPreparationError("This address is durably suppressed")
            prior = connection.execute(
                "SELECT action_id FROM career_contact_actions "
                "WHERE profile_id = %s AND target_key = %s AND recipient = %s",
                (profile["id"], target, contact["email"]),
            ).fetchone()
            if prior:
                raise ActionPreparationError(
                    "A career contact action already exists for this job/address"
                )
            duplicate = connection.execute(
                "SELECT id FROM external_actions WHERE opportunity_id = %s "
                "AND action_type = 'communications.email_send' "
                "AND lower(private_context->>'recipient') = %s "
                "AND status IN ('pending_approval','queued','executing','succeeded','ambiguous') "
                "LIMIT 1", (opportunity["id"], contact["email"]),
            ).fetchone()
            if duplicate:
                raise ActionPreparationError(
                    "An active or completed email already exists for this job/address"
                )
            draft = connection.execute(
                "SELECT id, content FROM job_application_drafts WHERE opportunity_id = %s "
                "ORDER BY created_at DESC LIMIT 1 FOR SHARE", (opportunity["id"],),
            ).fetchone()
            if draft is None:
                raise ActionPreparationError(
                    "Generate and verify the career application draft first"
                )
            error = application_quality_blocker(
                {**opportunity, "resume_text": profile["resume_text"]}, draft["content"],
            )
            if error:
                raise ActionPreparationError(error)
            # The draft read can wait for a concurrent generation transaction.
            now = connection.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
            error = contact_scope_error(contact, profile, opportunity, now)
            if error:
                raise ActionPreparationError(error)
            body = str(draft["content"].get("cover_letter") or "").strip()
            error = email_content_error(body)
            if error:
                raise ActionPreparationError(error)
            identity = profile.get("application_identity") or {}
            portfolio = identity.get("portfolio_url") or identity.get("github_url")
            if portfolio:
                body += f"\n\nPortfolio: {portfolio}"
            reference = f"HERMES-{opportunity['id'].hex}"
            body += f"\n\nRole: {opportunity['source_url']}\nApplication reference: {reference}"
            email = EmailActionCreate(
                recipient=contact["email"], subject=" ".join(
                    f"{reference} | {opportunity['company']}: {opportunity['title']}".split()
                )[:240], body=body, actor=request.actor, opportunity_id=opportunity["id"],
                approval_window_minutes=request.approval_window_minutes,
            )
            public = {"sender": sender, "recipient": email.recipient,
                      "subject": email.subject, "body": email.body,
                      "opportunity_id": str(opportunity["id"]),
                      "contact_source_url": contact["source_url"],
                      "contact_kind": contact["kind"]}
            packet = {"contact_id": str(contact_id), "snapshot": contact_snapshot(contact),
                      "draft_id": str(draft["id"]),
                      "draft_sha256": canonical_hash(draft["content"])}
            action = self._create_external_action(
                action_type="communications.email_send", opportunity_id=opportunity["id"],
                target_display=contact["email"], public_context=public,
                private_context={**public, "career_contact": packet}, actor=request.actor,
                approval_window_minutes=request.approval_window_minutes, connection=connection,
            )
            connection.execute(
                "INSERT INTO career_contact_actions(action_id,contact_id,profile_id,"
                "opportunity_id,recipient,target_key) VALUES (%s,%s,%s,%s,%s,%s)",
                (action["id"], contact_id, profile["id"], opportunity["id"],
                 contact["email"], target),
            )
            connection.commit()
            return action
