from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.creator_automation import (
    automation_campaign_hash,
    classify_creator_reply,
    correlate_creator_reply,
    creator_eligibility_reason,
    creator_key,
    creator_mailbox_is_fresh,
    pending_reply_reason,
    run_block_reason,
)
from app.creator_automation_models import CreatorAutomationStart, CreatorReplyReview
from app.creator_learning import suggested_feedback_tags
from app.creator_outreach_stop import CreatorOutreachStopMixin, outreach_stop_reason
from app.creator_reply_deferral import CreatorReplyDeferralMixin
from app.marketing_models import MarketingEmailPlanCreate
from app.marketing_store import (
    MarketingCampaignNotFoundError,
    MarketingOutreachError,
    MarketingStore,
)
from app.models import ApprovalDecision, TaskCancellation, TaskCreate
from app.store import InvalidTaskStateError

BODY_VERSION = "creator-gmail-body-v1"
BODY_FIELDS = (
    "body_status", "body_format", "body_digest", "body_version", "body_attempt_count",
    "body_attempted_at", "body_fetched_at", "body_error_code", "reviewed_body_digest",
)
BODY_FAILURE_CODES = {
    "CREATOR_REPLY_BODY_UNAVAILABLE", "CREATOR_REPLY_BODY_IDENTITY_CHANGED",
    "CREATOR_REPLY_BODY_CAPTURE_INELIGIBLE", "CREATOR_REPLY_BODY_OVERSIZE",
    "CREATOR_REPLY_BODY_UNSUPPORTED", "CREATOR_REPLY_BODY_INVALID",
}


def reply_body_digest(reply: dict[str, Any]) -> str:
    """Bind the complete representation to its original mailbox/message identity."""
    material = {key: str(reply.get(key) or "") for key in (
        "campaign_id", "gmail_message_id", "gmail_thread_id", "sender", "subject",
        "body_text", "body_format", "body_version", "body_mailbox_key", "body_label_name",
    )}
    material["received_at"] = reply["received_at"].isoformat()
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def complete_reply_body(reply: dict[str, Any]) -> bool:
    return bool(
        reply.get("body_status") == "complete" and reply.get("body_text")
        and reply.get("body_version") == BODY_VERSION
        and reply.get("body_format") in {"plain", "html"}
        and reply.get("body_digest") == reply_body_digest(reply)
    )


def reply_capture_summary(reply: dict[str, Any]) -> dict[str, Any]:
    return {"id": reply["id"], **{key: reply.get(key) for key in BODY_FIELDS}}


def authored_body_view(text: str) -> str:
    """A case-preserving reading aid; the complete body remains the review evidence."""
    marker = re.search(
        r"(?im)(?:\bon\s+[^\n]{1,220}?\bwrote\s*:|"
        r"\b(?:w dniu|dnia)\s+[^\n]{1,220}?\b(?:napisał|napisała|napisano)\s*:|"
        r"^\s*>|^-{2,}\s*(?:original|forwarded|wiadomość oryginalna)\s*(?:message)?\s*-{2,})",
        text,
    )
    return (text[:marker.start()] if marker else text).strip()


def lock_automation(connection: Any) -> None:
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('creator-automation', 0))")


class CreatorAutomationStore(CreatorReplyDeferralMixin, CreatorOutreachStopMixin, MarketingStore):
    def _audit_automation(
        self,
        connection: Any,
        campaign_id: UUID,
        action: str,
        actor: str,
        *,
        run_id: UUID | None = None,
        task_id: UUID | None = None,
        **metadata: Any,
    ) -> None:
        delegated = action in {"creator.automation.started", "creator.automation.authorized"}
        self._append_audit(
            connection,
            correlation_id=uuid4(),
            task_id=task_id,
            actor_type="agent" if actor == "creator-worker" else "user",
            actor_id=actor,
            tool_name="marketing.creator_automation",
            action=action,
            risk_level="high" if delegated else "medium",
            approval_status="scoped_authorization" if delegated else "not_required",
            execution_status="recorded",
            input_metadata={
                "campaign_id": str(campaign_id),
                "run_id": str(run_id) if run_id else None,
                **metadata,
            },
        )

    def start(
        self, campaign_id: UUID, request: CreatorAutomationStart, *, monitor_gmail: bool = False
    ) -> dict[str, Any]:
        with self.connect() as connection:
            lock_automation(connection)
            campaign = connection.execute(
                "SELECT * FROM marketing_campaigns WHERE id = %s FOR SHARE",
                (campaign_id,),
            ).fetchone()
            if campaign is None:
                raise MarketingCampaignNotFoundError(str(campaign_id))
            if reason := outreach_stop_reason(campaign):
                raise MarketingOutreachError(reason)
            if (
                campaign.get("outreach_mode") != "paid"
                or not campaign["paid_offer_enabled"]
                or not campaign["paid_offer_details"]
            ):
                raise MarketingOutreachError("Save a paid-promotion campaign with its offer first")
            if not campaign.get("handoff_email") and not campaign.get("handoff_discord"):
                raise MarketingOutreachError("Save your owner email or Discord contact first")
            connection.execute(
                "UPDATE creator_automation_runs SET state = 'paused', paused_at = now() "
                "WHERE campaign_id = %s AND state = 'running'",
                (campaign_id,),
            )
            run = connection.execute(
                """INSERT INTO creator_automation_runs
                (campaign_id,state,campaign_hash,max_initials_per_day,auto_handoff,
                 monitor_gmail,authorized_by,expires_at)
                VALUES (%s,'running',%s,%s,%s,%s,%s,now()+make_interval(hours => %s))
                RETURNING *""",
                (
                    campaign_id,
                    automation_campaign_hash(campaign),
                    request.max_initials_per_day,
                    request.auto_handoff,
                    monitor_gmail,
                    request.actor,
                    request.expires_in_hours,
                ),
            ).fetchone()
            self._audit_automation(
                connection,
                campaign_id,
                "creator.automation.started",
                request.actor,
                run_id=run["id"],
                max_initials_per_day=request.max_initials_per_day,
                auto_handoff=request.auto_handoff,
                expires_at=run["expires_at"].isoformat(),
            )
            connection.commit()
        self._cancel_stopped_packets()
        return self._public_run(run)

    def pause(self, campaign_id: UUID, actor: str) -> dict[str, bool]:
        self.get_campaign(campaign_id)
        with self.connect() as connection:
            lock_automation(connection)
            # A boundary already holding a run share lock may finish before Pause commits.
            rows = connection.execute(
                "UPDATE creator_automation_runs SET state='paused', paused_at=now(), "
                "reason='Paused by operator' WHERE campaign_id=%s AND state='running' RETURNING id",
                (campaign_id,),
            ).fetchall()
            for row in rows:
                self._audit_automation(
                    connection, campaign_id, "creator.automation.paused", actor, run_id=row["id"]
                )
            connection.commit()
        self._cancel_stopped_packets()
        return {"paused": True}

    def _cancel_stopped_packets(self) -> None:
        # Finish the run transaction first: the side-effect boundary locks its task
        # before its run. Holding a run lock while cancelling tasks would invert that order.
        with self.connect() as connection:
            packets = connection.execute(
                """SELECT a.task_id FROM external_actions a
                JOIN creator_automation_runs r
                  ON a.private_context->'creator_automation'->>'run_id'=r.id::text
                WHERE a.status='pending_approval'
                  AND (r.state<>'running' OR r.expires_at<=now())
                  AND NOT EXISTS (SELECT 1 FROM creator_automation_actions x WHERE x.action_id=a.id)
                ORDER BY a.created_at LIMIT 50""",
            ).fetchall()
        for packet in packets:
            try:
                self.cancel_task(
                    packet["task_id"],
                    TaskCancellation(
                        actor="creator-automation",
                        reason="Unapproved creator grant stopped or expired",
                    ),
                )
            except InvalidTaskStateError:
                # A concurrent operator decision or completed action is never overwritten.
                continue

    @staticmethod
    def _public_run(run: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in run.items() if key != "campaign_hash"}

    def overview(self, campaign_id: UUID) -> dict[str, Any]:
        campaign = self.get_campaign(campaign_id)
        with self.connect() as connection:
            runs = connection.execute(
                """SELECT r.*, (SELECT count(*) FROM creator_automation_actions a
                   WHERE a.campaign_id=r.campaign_id AND a.stage='initial'
                   AND a.created_at>now()-interval '24 hours') AS used_today
                   FROM creator_automation_runs r WHERE campaign_id=%s
                   ORDER BY created_at DESC LIMIT 20""",
                (campaign_id,),
            ).fetchall()
            replies = connection.execute(
                "SELECT id,campaign_id,gmail_message_id,gmail_thread_id,sender,subject,snippet,"
                "received_at,prospect_id,suggested_classification,match_reason,needs_review,"
                "reviewed_by,reviewed_at,reviewed_classification,created_at,body_status,"
                "body_format,body_digest,body_version,body_attempt_count,body_attempted_at,"
                "body_fetched_at,body_error_code,reviewed_body_digest "
                "FROM creator_reply_messages WHERE campaign_id=%s AND needs_review "
                "ORDER BY received_at DESC LIMIT 100",
                (campaign_id,),
            ).fetchall()
            counts = connection.execute(
                "SELECT count(*) AS pending_reply_count FROM creator_reply_messages "
                "WHERE campaign_id=%s AND needs_review",
                (campaign_id,),
            ).fetchone()
            sync = connection.execute(
                "SELECT last_sync_at,last_complete_at FROM creator_gmail_sync_state "
                "WHERE campaign_id=%s",
                (campaign_id,),
            ).fetchone()
            failure = connection.execute(
                "SELECT COALESCE(completed_at,dead_lettered_at) AS last_failure_at "
                "FROM agent_tasks WHERE kind='marketing.gmail_sync' "
                "AND status IN ('failed','dead_lettered') AND payload->>'campaign_id'=%s "
                "AND COALESCE(completed_at,dead_lettered_at) IS NOT NULL "
                "ORDER BY COALESCE(completed_at,dead_lettered_at) DESC LIMIT 1",
                (str(campaign_id),),
            ).fetchone()
            sync = {"last_sync_at": None, "last_complete_at": None, **(sync or {}),
                    "last_failure_at": failure["last_failure_at"] if failure else None}
            reply_drafts = connection.execute(
                "SELECT d.id,d.reply_id,d.prospect_id,d.task_id,d.created_at,d.expires_at,"
                "d.reply_body_digest,d.draft_digest,CASE WHEN d.status='queued' "
                "AND t.status='cancelled' THEN 'cancelled' WHEN d.status='queued' "
                "AND t.status IN ('failed','dead_lettered') THEN 'failed' "
                "ELSE d.status END AS status,"
                "(p.contact_authorized_at IS NOT NULL AND p.suppressed_at IS NULL AND NOT EXISTS "
                "(SELECT 1 FROM creator_contact_suppressions s "
                "WHERE s.email=lower(p.contact_email))) "
                "AS contact_authorized,false AS sending_authority FROM creator_reply_drafts d "
                "JOIN agent_tasks t ON t.id=d.task_id "
                "JOIN marketing_prospects p ON p.id=d.prospect_id "
                "WHERE d.campaign_id=%s ORDER BY d.created_at DESC,d.id LIMIT 30", (campaign_id,),
            ).fetchall()
        public = [self._public_run(run) for run in runs]
        for reply in replies:
            reply["suggested_feedback_tags"] = suggested_feedback_tags(reply["snippet"])
        return {
            "outreach_stop": {key: campaign.get(key) for key in (
                "outreach_paused", "outreach_epoch", "outreach_stopped_at",
                "outreach_stopped_by", "outreach_stop_reason",
            )},
            "run": public[0] if public else None,
            "runs": public,
            "pending_replies": replies,
            **counts,
            "gmail_sync": sync,
            "reply_drafts": reply_drafts,
            "reply_deferral_count": self.reply_deferral_count(campaign_id),
        }

    def queue_reply_draft_curation(self, task, campaign_id):
        from app.creator_reply_draft_store import CreatorReplyDraftStore

        return CreatorReplyDraftStore(self._dsn).queue_automatic_reply_drafts(task, campaign_id)

    def schedule(self, *, gmail_enabled: bool) -> list[dict[str, Any]]:
        scheduled = []
        with self.connect() as connection:
            lock_automation(connection)
            connection.execute(
                "UPDATE creator_automation_runs SET state='expired', "
                "reason='Authorization expired' "
                "WHERE state='running' AND expires_at <= now()",
            )
            if gmail_enabled:
                # A sender's reply may arrive after a send grant expires. Continue read-only
                # monitoring of recent conversations without renewing any sending authority.
                mail_campaigns = connection.execute(
                    """SELECT c.id FROM marketing_campaigns c
                    WHERE (EXISTS (SELECT 1 FROM creator_automation_runs r
                                   WHERE r.campaign_id=c.id AND r.state='running'
                                     AND r.monitor_gmail)
                        OR EXISTS (SELECT 1 FROM marketing_outreach_messages m
                                   JOIN marketing_prospects p ON p.id=m.prospect_id
                                   JOIN external_actions a ON a.id=m.action_id
                                   WHERE p.campaign_id=c.id AND a.status='succeeded'
                                     AND a.executed_at>now()-interval '180 days'))
                    AND NOT EXISTS (SELECT 1 FROM agent_tasks t
                                    WHERE t.kind='marketing.gmail_sync'
                                      AND t.payload->>'campaign_id'=c.id::text
                                      AND (t.status IN ('queued','running')
                                           OR t.created_at>now()-interval '5 minutes'))
                    ORDER BY (SELECT max(t.created_at) FROM agent_tasks t
                              WHERE t.kind='marketing.gmail_sync'
                              AND t.payload->>'campaign_id'=c.id::text) NULLS FIRST,c.id
                    LIMIT 10""",
                ).fetchall()
                for campaign in mail_campaigns:
                    task = self._create_task_record(
                        connection,
                        TaskCreate(
                            title="Read labeled creator replies",
                            kind="marketing.gmail_sync",
                            payload={"campaign_id": str(campaign["id"])},
                            requested_by="scheduler:creator-replies",
                            idempotency_key=f"creator-replies:{campaign['id']}:{uuid4()}",
                        ),
                    )
                    scheduled.append({"task_id": task["id"]})
            runs = connection.execute(
                "SELECT * FROM creator_automation_runs WHERE state='running' "
                "AND next_tick_at<=now() ORDER BY next_tick_at LIMIT 10 FOR UPDATE SKIP LOCKED",
            ).fetchall()
            for run in runs:
                kinds = ["marketing.creator_automation"]
                for kind in kinds:
                    recent = connection.execute(
                        "SELECT 1 FROM agent_tasks WHERE kind=%s AND payload->>'campaign_id'=%s "
                        "AND (status IN ('queued','running') OR created_at>now()-interval "
                        "'5 minutes') LIMIT 1",
                        (kind, str(run["campaign_id"])),
                    ).fetchone()
                    if recent:
                        continue
                    task = self._create_task_record(
                        connection,
                        TaskCreate(
                            title=(
                                "Read labeled creator replies"
                                if kind == "marketing.gmail_sync"
                                else "Reconcile bounded paid creator outreach"
                            ),
                            kind=kind,
                            payload={
                                "campaign_id": str(run["campaign_id"]),
                                "run_id": str(run["id"]),
                            },
                            requested_by="scheduler:creator-automation",
                            idempotency_key=f"creator-tick:{kind}:{run['id']}:{uuid4()}",
                        ),
                    )
                    scheduled.append({"task_id": task["id"]})
                connection.execute(
                    "UPDATE creator_automation_runs SET next_tick_at=now()+interval '5 minutes' "
                    "WHERE id=%s",
                    (run["id"],),
                )
            connection.commit()
        self._cancel_stopped_packets()
        return scheduled

    @staticmethod
    def _check_task(connection: Any, task: dict[str, Any], kind: str) -> None:
        valid = connection.execute(
            "SELECT 1 FROM agent_tasks WHERE id=%s AND lease_id=%s AND kind=%s "
            "AND status='running' AND cancellation_requested_at IS NULL "
            "AND lease_expires_at>clock_timestamp() AND payload->>'campaign_id'=%s "
            "AND (%s<>'marketing.creator_automation' OR payload->>'run_id'=%s) FOR SHARE",
            (
                task["id"],
                task["lease_id"],
                kind,
                str(task["payload"]["campaign_id"]),
                kind,
                str(task["payload"].get("run_id", "")),
            ),
        ).fetchone()
        if not valid:
            raise MarketingOutreachError(
                "Creator task lease or campaign binding is no longer valid"
            )

    def execute(self, task: dict[str, Any], *, sender: str) -> dict[str, Any]:
        campaign_id = UUID(str(task["payload"]["campaign_id"]))
        run_id = UUID(str(task["payload"]["run_id"]))
        if not sender:
            raise MarketingOutreachError("Configure the SMTP sender before automatic outreach")
        with self.connect() as connection:
            self._check_task(connection, task, "marketing.creator_automation")
            run = connection.execute(
                "SELECT * FROM creator_automation_runs WHERE id=%s AND campaign_id=%s",
                (run_id, campaign_id),
            ).fetchone()
            if not run:
                raise MarketingOutreachError("Creator run does not belong to this campaign")
            campaign = connection.execute(
                "SELECT * FROM marketing_campaigns WHERE id=%s",
                (campaign_id,),
            ).fetchone()
            reason = run_block_reason(run, campaign) or pending_reply_reason(
                connection, campaign_id
            )
            if run["monitor_gmail"] and not creator_mailbox_is_fresh(connection, campaign_id):
                reason = reason or "Waiting for a recent completed creator mailbox sync"
            if reason:
                connection.execute(
                    "UPDATE creator_automation_runs SET reason=%s, state=CASE "
                    "WHEN state='running' AND campaign_hash<>%s THEN 'blocked' ELSE state END "
                    "WHERE id=%s",
                    (reason, automation_campaign_hash(campaign), run_id),
                )
                connection.commit()
                return {
                    "handler": "marketing.creator_automation",
                    "authorized": 0,
                    "reason": reason,
                }
            prospects = connection.execute(
                """SELECT p.* FROM marketing_prospects p WHERE p.campaign_id=%s
                   AND p.platform='youtube' AND p.contact_authorized_at IS NOT NULL
                   AND p.suppressed_at IS NULL
                   AND NOT EXISTS (SELECT 1 FROM creator_contact_suppressions s
                                   WHERE s.email=lower(p.contact_email))
                   AND ((p.status='interested' AND %s AND EXISTS (
                            SELECT 1 FROM marketing_outcomes o WHERE o.prospect_id=p.id
                            AND o.classification='interested'
                            AND length(trim(COALESCE(o.note,'')))>0))
                        OR (p.status IN ('qualified','discovered')
                            AND p.intelligence->'topics' @> '["Minecraft"]'::jsonb
                            AND p.audience_size BETWEEN %s AND %s
                            AND p.latest_content_published_at BETWEEN
                                now()-make_interval(days => %s) AND now()
                            AND (%s<>'strict' OR p.intelligence->'geography'->>'country_code'=%s)
                            AND (%s<>'strict' OR
                                p.intelligence->'geography'->>'language_code'=%s OR
                                p.intelligence->'geography'->>'language_code' LIKE %s)))
                   AND NOT EXISTS (SELECT 1 FROM creator_automation_actions x
                       WHERE (lower(x.recipient)=lower(p.contact_email)
                              OR x.creator_key=p.platform||':'||p.external_id)
                         AND x.stage=CASE WHEN p.status='interested'
                                         THEN 'handoff' ELSE 'initial' END)
                   AND NOT EXISTS (SELECT 1 FROM marketing_outreach_messages m
                       JOIN external_actions a ON a.id=m.action_id
                       JOIN marketing_prospects sent ON sent.id=m.prospect_id
                       WHERE (lower(a.private_context->>'recipient')=lower(p.contact_email)
                           OR lower(rtrim(sent.profile_url,'/'))=lower(rtrim(p.profile_url,'/'))
                           OR (sent.platform=p.platform AND sent.external_id=p.external_id))
                         AND (p.status<>'interested' OR m.stage='handoff')
                         AND a.status IN ('pending_approval','queued','executing',
                                          'succeeded','ambiguous')
                         AND NOT (a.status='pending_approval' AND COALESCE(
                           a.private_context->'creator_automation'->>'run_id'=%s,false)))
                   ORDER BY CASE WHEN p.status='interested' THEN 0 ELSE 1 END,
                            p.relevance_score DESC,p.id LIMIT 100""",
                (
                    campaign_id,
                    run["auto_handoff"],
                    campaign["min_subscribers"],
                    campaign["max_subscribers"],
                    campaign["max_video_age_days"],
                    campaign["country_mode"],
                    campaign["target_country"],
                    campaign["language_mode"],
                    campaign["target_language"],
                    (campaign["target_language"] or "") + "-%",
                    str(run_id),
                ),
            ).fetchall()
            used = connection.execute(
                "SELECT count(*) AS n FROM creator_automation_actions WHERE campaign_id=%s "
                "AND stage='initial' AND created_at>now()-interval '24 hours'",
                (campaign_id,),
            ).fetchone()["n"]
        authorized, reasons = 0, []
        initials_remaining = max(0, run["max_initials_per_day"] - used)
        for prospect in prospects:
            stage = "handoff" if prospect["status"] == "interested" else "initial"
            if stage == "handoff" and not run["auto_handoff"]:
                continue
            if authorized >= 10:
                break
            if stage == "initial":
                if initials_remaining <= 0:
                    reasons.append("Rolling daily introduction allowance reached")
                    break
                reason = creator_eligibility_reason(campaign, prospect)
                if reason:
                    reasons.append(reason)
                    continue
            try:
                # Recovery can reuse this run's exact packet after a crash before approval.
                with self.connect() as connection:
                    existing = connection.execute(
                        """SELECT a.* FROM external_actions a
                        JOIN marketing_outreach_messages m ON m.action_id=a.id
                        WHERE m.prospect_id=%s AND m.stage=%s AND a.status='pending_approval'
                        AND a.private_context->'creator_automation'->>'run_id'=%s
                        ORDER BY a.created_at DESC LIMIT 1""",
                        (prospect["id"], stage, str(run_id)),
                    ).fetchone()
                action = existing or self.plan_outreach_email(
                    prospect["id"],
                    MarketingEmailPlanCreate(
                        actor=f"creator-automation:{run_id}",
                        stage=stage,
                        approval_window_minutes=1440,
                    ),
                    sender=sender,
                    automation_context={"run_id": str(run_id)},
                )
                if self._authorize(task, run_id, prospect["id"], action, stage):
                    authorized += 1
                    if stage == "initial":
                        initials_remaining -= 1
            except (MarketingOutreachError, ValueError) as exc:
                # Reasons are fixed local guard errors, never inbound message contents.
                reasons.append(str(exc)[:300])
        reason = (
            f"Authorized {authorized} exact messages within the run scope"
            if authorized
            else reasons[0]
            if reasons
            else "No eligible authorized creators need a message"
        )
        with self.connect() as connection:
            self._check_task(connection, task, "marketing.creator_automation")
            connection.execute(
                "UPDATE creator_automation_runs SET reason=%s WHERE id=%s", (reason, run_id)
            )
            connection.commit()
        return {
            "handler": "marketing.creator_automation",
            "authorized": authorized,
            "reason": reason,
        }

    def _authorize(
        self,
        task: dict[str, Any],
        run_id: UUID,
        prospect_id: UUID,
        action: dict[str, Any],
        stage: str,
    ) -> bool:
        from app.creator_automation import validate_creator_automation

        with self.connect() as connection:
            lock_automation(connection)
            self._check_task(connection, task, "marketing.creator_automation")
            # Match the final side-effect lock order (task/action, then campaign/prospect).
            # A concurrent operator decision must not leave us holding the campaign while
            # waiting for a worker that owns this action's task and needs that campaign.
            packet = connection.execute(
                "SELECT a.* FROM agent_tasks t JOIN external_actions a ON a.task_id=t.id "
                "WHERE a.id=%s AND t.id=%s AND t.status='pending_approval' "
                "AND a.status='pending_approval' FOR UPDATE OF t,a",
                (action["id"], action["task_id"]),
            ).fetchone()
            if not packet or packet["context_hash"] != action["context_hash"]:
                raise MarketingOutreachError("Exact creator packet was already decided or changed")
            run = connection.execute(
                "SELECT * FROM creator_automation_runs WHERE id=%s", (run_id,)
            ).fetchone()
            if (
                not run
                or str(run_id) != str(task["payload"].get("run_id"))
                or str(run["campaign_id"]) != str(task["payload"]["campaign_id"])
            ):
                raise MarketingOutreachError("Creator task is outside this run's campaign scope")
            campaign = connection.execute(
                "SELECT * FROM marketing_campaigns WHERE id=%s FOR SHARE",
                (run["campaign_id"],),
            ).fetchone()
            reason = run_block_reason(run, campaign) or pending_reply_reason(
                connection,
                run["campaign_id"],
            )
            if reason:
                raise MarketingOutreachError(reason)
            prospect = connection.execute(
                "SELECT * FROM marketing_prospects WHERE id=%s FOR SHARE",
                (prospect_id,),
            ).fetchone()
            marketing = action["private_context"].get("marketing", {})
            if marketing.get("variant") == "ai_reviewed_initial":
                raise MarketingOutreachError("AI introductions require individual exact approval")
            if (
                not prospect
                or prospect["campaign_id"] != run["campaign_id"]
                or marketing.get("prospect_id") != str(prospect_id)
                or marketing.get("campaign_id") != str(run["campaign_id"])
                or marketing.get("stage") != stage
            ):
                raise MarketingOutreachError("Exact creator packet is outside this run's scope")
            if prospect["suppressed_at"] or not prospect["contact_authorized_at"]:
                raise MarketingOutreachError("Creator contact is no longer authorized")
            if stage == "handoff":
                if not run["auto_handoff"] or prospect["status"] != "interested":
                    raise MarketingOutreachError(
                        "Owner handoff needs reviewed interest and authority"
                    )
                if not connection.execute(
                    "SELECT 1 FROM marketing_outcomes WHERE prospect_id=%s "
                    "AND classification='interested' AND length(trim(COALESCE(note,'')))>0 LIMIT 1",
                    (prospect_id,),
                ).fetchone():
                    raise MarketingOutreachError("Record interested reply evidence before handoff")
            elif prospect["status"] not in {"discovered", "qualified"}:
                raise MarketingOutreachError(
                    "Creator reply state no longer permits an introduction"
                )
            elif reason := creator_eligibility_reason(campaign, prospect):
                raise MarketingOutreachError(reason)
            used = connection.execute(
                "SELECT count(*) AS n FROM creator_automation_actions WHERE campaign_id=%s "
                "AND stage='initial' AND created_at>now()-interval '24 hours'",
                (run["campaign_id"],),
            ).fetchone()["n"]
            if stage == "initial" and used >= run["max_initials_per_day"]:
                raise MarketingOutreachError("Rolling daily introduction allowance reached")
            prior = connection.execute(
                """SELECT 1 FROM marketing_outreach_messages m
                JOIN external_actions a ON a.id=m.action_id
                JOIN marketing_prospects p ON p.id=m.prospect_id
                WHERE m.stage=%s AND a.id<>%s
                AND a.status IN ('queued','executing','succeeded','ambiguous')
                AND (lower(a.public_context->>'recipient')=lower(%s)
                     OR (p.platform=%s AND p.external_id=%s) OR p.profile_url=%s) LIMIT 1""",
                (
                    stage,
                    action["id"],
                    prospect["contact_email"],
                    prospect["platform"],
                    prospect["external_id"],
                    prospect["profile_url"],
                ),
            ).fetchone()
            if prior:
                raise MarketingOutreachError(
                    "This creator or address already has that outreach stage"
                )
            inserted = connection.execute(
                """INSERT INTO creator_automation_actions
                (action_id,run_id,campaign_id,prospect_id,stage,recipient,creator_key,context_hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING action_id""",
                (
                    action["id"],
                    run_id,
                    run["campaign_id"],
                    prospect_id,
                    stage,
                    prospect["contact_email"],
                    creator_key(prospect),
                    action["context_hash"],
                ),
            ).fetchone()
            if not inserted:
                return False
            reason = validate_creator_automation(connection, action)
            if reason:
                raise MarketingOutreachError(reason)
            self.decide_task(
                action["task_id"],
                ApprovalDecision(
                    decision="approved",
                    actor=f"creator-automation:{run_id}",
                    reason=f"Within creator scope authorized by {run['authorized_by']}",
                ),
                connection=connection,
            )
            self._audit_automation(
                connection,
                run["campaign_id"],
                "creator.automation.authorized",
                run["authorized_by"],
                run_id=run_id,
                task_id=task["id"],
                action_id=str(action["id"]),
                stage=stage,
            )
            self._check_task(connection, task, "marketing.creator_automation")
            connection.commit()
        return True

    def queue_reply_sync(self, campaign_id: UUID, actor: str) -> dict[str, Any]:
        self.get_campaign(campaign_id)
        with self.connect() as connection:
            lock_automation(connection)
            task = self._queue_reply_sync(connection, campaign_id, actor)
            connection.commit()
        return task

    def _queue_reply_sync(self, connection, campaign_id, actor):
        existing = connection.execute(
            "SELECT * FROM agent_tasks WHERE kind='marketing.gmail_sync' "
            "AND payload->>'campaign_id'=%s AND (status IN ('queued','running') "
            "OR created_at>now()-interval '1 minute') ORDER BY created_at DESC LIMIT 1",
            (str(campaign_id),),
        ).fetchone()
        return existing or self._create_task_record(connection, TaskCreate(
            title="Read labeled creator replies", kind="marketing.gmail_sync",
            payload={"campaign_id": str(campaign_id)}, requested_by=actor,
            idempotency_key=f"creator-mail:{campaign_id}:{uuid4()}",
        ))

    def get_reply(self, campaign_id, reply_id):
        self.get_campaign(campaign_id)
        with self.connect() as connection:
            reply = connection.execute(
                "SELECT * FROM creator_reply_messages WHERE id=%s AND campaign_id=%s",
                (reply_id, campaign_id),
            ).fetchone()
        if not reply:
            raise MarketingOutreachError("Creator reply not found in this campaign")
        body_valid = complete_reply_body(reply)
        result = {key: value for key, value in reply.items() if key not in {
            "body_text", "body_mailbox_key", "body_label_name", "body_capture_task_id",
            "body_capture_lease_id",
        }}
        result.update(
            body_text=reply["body_text"] if body_valid else "",
            authored_text=authored_body_view(reply["body_text"]) if body_valid else "",
            body_complete=body_valid, authored_view_is_heuristic=True,
        )
        return result

    @staticmethod
    def _body_capture_eligible(connection, reply):
        if not reply["needs_review"] or not reply["prospect_id"]:
            return False
        prospect = connection.execute(
            "SELECT contact_email,suppressed_at,status FROM marketing_prospects "
            "WHERE id=%s AND campaign_id=%s FOR SHARE",
            (reply["prospect_id"], reply["campaign_id"]),
        ).fetchone()
        if (not prospect or prospect["suppressed_at"] or prospect["status"] in {
                "suppressed", "handed_off", "converted", "bounced",
            } or not prospect["contact_email"]
                or prospect["contact_email"].casefold() != reply["sender"].casefold()):
            return False
        sent = connection.execute(
            "SELECT m.prospect_id,a.public_context->>'recipient' AS recipient,"
            "a.public_context->>'subject' AS subject,a.executed_at AS sent_at "
            "FROM marketing_outreach_messages m JOIN external_actions a ON a.id=m.action_id "
            "WHERE m.prospect_id=%s AND a.status='succeeded' AND a.executed_at IS NOT NULL "
            "ORDER BY a.executed_at DESC LIMIT 2000", (reply["prospect_id"],),
        ).fetchall()
        matched, _ = correlate_creator_reply(reply, sent)
        return matched == reply["prospect_id"]

    def queue_reply_body_read(self, campaign_id, reply_id, actor):
        self.get_campaign(campaign_id)
        with self.connect() as connection:
            lock_automation(connection)
            reply = connection.execute(
                "SELECT * FROM creator_reply_messages WHERE id=%s AND campaign_id=%s FOR UPDATE",
                (reply_id, campaign_id),
            ).fetchone()
            if not reply or not self._body_capture_eligible(connection, reply):
                raise MarketingOutreachError("Read requires an unreviewed matched creator reply")
            if reply["body_status"] == "complete":
                raise MarketingOutreachError(
                    "Complete creator reply snapshots cannot be recaptured",
                )
            timing = connection.execute(
                "SELECT clock_timestamp() AS now, %s::timestamptz IS NULL OR "
                "%s::timestamptz<=clock_timestamp()-interval '5 minutes' AS retry_due",
                (reply["body_attempted_at"], reply["body_attempted_at"]),
            ).fetchone()
            if reply["body_attempt_count"] >= 3 or not timing["retry_due"]:
                raise MarketingOutreachError(
                    "Full reply reads allow three attempts, five minutes apart",
                )
            if reply["body_status"] == "reading" and connection.execute(
                "SELECT 1 FROM agent_tasks WHERE id=%s AND status='running' "
                "AND lease_id=%s AND cancellation_requested_at IS NULL "
                "AND lease_expires_at>clock_timestamp()",
                (reply["body_capture_task_id"], reply["body_capture_lease_id"]),
            ).fetchone():
                raise MarketingOutreachError("A governed full reply read is already running")
            reply = connection.execute(
                "UPDATE creator_reply_messages SET body_status='missing' WHERE id=%s RETURNING *",
                (reply_id,),
            ).fetchone()
            task = self._queue_reply_sync(connection, campaign_id, actor)
            self._audit_automation(connection, campaign_id, "creator.reply.read_requested", actor,
                                   task_id=task["id"], reply_id=str(reply_id))
            connection.commit()
        return {"task": task, "capture": reply_capture_summary(reply)}

    def _body_state(self, connection, task, state):
        self._check_task(connection, task, "marketing.gmail_sync")
        current = connection.execute(
            "SELECT * FROM creator_gmail_sync_state WHERE campaign_id=%s FOR SHARE",
            (state["campaign_id"],),
        ).fetchone()
        if (str(task["payload"]["campaign_id"]) != str(state["campaign_id"])
                or not current or any(current[key] != state[key] for key in (
                    "mailbox_key", "label_name", "revision",
                ))):
            raise MarketingOutreachError("Creator mailbox state changed before full reply capture")

    def finalize_reply_sync(self, task, state):
        with self.connect() as connection:
            lock_automation(connection)
            self._body_state(connection, task, state)
            self._check_task(connection, task, "marketing.gmail_sync")
            connection.execute(
                "UPDATE creator_gmail_sync_state SET last_complete_at=CASE "
                "WHEN page_token IS NULL AND pending_message_ids='[]'::jsonb "
                "THEN clock_timestamp() ELSE last_complete_at END WHERE campaign_id=%s",
                (state["campaign_id"],),
            )
            self._check_task(connection, task, "marketing.gmail_sync")
            connection.commit()

    def body_capture_candidates(self, task, state, limit):
        with self.connect() as connection:
            self._body_state(connection, task, state)
            return connection.execute(
                "SELECT r.id FROM creator_reply_messages r "
                "JOIN marketing_prospects p ON p.id=r.prospect_id AND p.campaign_id=r.campaign_id "
                "LEFT JOIN agent_tasks owner ON owner.id=r.body_capture_task_id "
                "AND owner.lease_id=r.body_capture_lease_id AND owner.status='running' "
                "AND owner.cancellation_requested_at IS NULL "
                "AND owner.lease_expires_at>clock_timestamp() "
                "WHERE r.campaign_id=%s AND r.needs_review "
                "AND (r.body_status='missing' OR (r.body_status='reading' AND owner.id IS NULL)) "
                "AND r.body_attempt_count<3 AND (r.body_attempted_at IS NULL OR "
                "r.body_attempted_at<=clock_timestamp()-interval '5 minutes') "
                "AND p.suppressed_at IS NULL AND p.status NOT IN "
                "('suppressed','handed_off','converted','bounced') "
                "AND lower(p.contact_email)=lower(r.sender) "
                "ORDER BY r.received_at,r.id LIMIT %s",
                (state["campaign_id"], min(3, max(0, limit))),
            ).fetchall()

    def claim_reply_body(self, task, state, reply_id):
        with self.connect() as connection:
            lock_automation(connection)
            self._body_state(connection, task, state)
            reply = connection.execute(
                "SELECT * FROM creator_reply_messages WHERE id=%s AND campaign_id=%s FOR UPDATE",
                (reply_id, state["campaign_id"]),
            ).fetchone()
            if (not reply or reply["body_status"] not in {"missing", "reading"}
                    or reply["body_attempt_count"] >= 3
                    or not self._body_capture_eligible(connection, reply)):
                return None
            if reply["body_status"] == "reading" and connection.execute(
                "SELECT 1 FROM agent_tasks WHERE id=%s AND lease_id=%s AND status='running' "
                "AND cancellation_requested_at IS NULL AND lease_expires_at>clock_timestamp()",
                (reply["body_capture_task_id"], reply["body_capture_lease_id"]),
            ).fetchone():
                return None
            reply = connection.execute(
                "UPDATE creator_reply_messages SET body_status='reading',"
                "body_attempt_count=body_attempt_count+1,body_attempted_at=clock_timestamp(),"
                "body_capture_task_id=%s,body_capture_lease_id=%s "
                "WHERE id=%s AND (body_attempted_at IS NULL OR "
                "body_attempted_at<=clock_timestamp()-interval '5 minutes') RETURNING *",
                (task["id"], task["lease_id"], reply_id),
            ).fetchone()
            self._check_task(connection, task, "marketing.gmail_sync")
            connection.commit()
            return reply

    def save_reply_body(self, task, state, claim, result, message=None):
        with self.connect() as connection:
            lock_automation(connection)
            self._body_state(connection, task, state)
            reply = connection.execute(
                "SELECT * FROM creator_reply_messages WHERE id=%s AND campaign_id=%s FOR UPDATE",
                (claim["id"], state["campaign_id"]),
            ).fetchone()
            if (not reply or not reply["needs_review"] or reply["body_status"] != "reading"
                    or reply["body_capture_task_id"] != task["id"]
                    or reply["body_capture_lease_id"] != task["lease_id"]
                    or reply["body_attempt_count"] != claim["body_attempt_count"]):
                raise MarketingOutreachError("Full reply capture no longer owns its snapshot")
            keys = ("gmail_message_id", "gmail_thread_id", "sender", "subject", "received_at")
            if any(reply[key] != claim[key] for key in keys):
                raise MarketingOutreachError("Creator reply identity changed before capture")
            status = result["status"]
            text, form, error = "", None, "CREATOR_REPLY_BODY_UNAVAILABLE"
            if status == "complete":
                if (not message or any(message[key] != reply[key] for key in keys)
                        or not self._body_capture_eligible(connection, reply)):
                    status, error = "unavailable", "CREATOR_REPLY_BODY_IDENTITY_CHANGED"
                elif (not isinstance(result["text"], str) or not result["text"]
                      or len(result["text"]) > 24000 or result["format"] not in {"plain", "html"}):
                    raise MarketingOutreachError("Invalid complete creator reply representation")
                else:
                    text, form, error = result["text"], result["format"], None
            elif status in {"unavailable", "oversize", "unsupported"}:
                error = {"oversize": "CREATOR_REPLY_BODY_OVERSIZE",
                         "unsupported": "CREATOR_REPLY_BODY_UNSUPPORTED"}.get(status, error)
                if result.get("error_code") in BODY_FAILURE_CODES:
                    error = result["error_code"]
            else:
                raise MarketingOutreachError("Unsupported creator reply body capture result")
            evidence = {**reply, "body_text": text, "body_format": form,
                        "body_version": BODY_VERSION, "body_mailbox_key": state["mailbox_key"],
                        "body_label_name": state["label_name"]}
            digest = reply_body_digest(evidence) if status == "complete" else None
            self._check_task(connection, task, "marketing.gmail_sync")
            updated = connection.execute(
                "UPDATE creator_reply_messages SET body_status=%s,body_text=%s,body_format=%s,"
                "body_digest=%s,body_version=%s,body_fetched_at=CASE WHEN %s='complete' "
                "THEN clock_timestamp() ELSE NULL END,"
                "body_error_code=%s,body_mailbox_key=%s,body_label_name=%s WHERE id=%s RETURNING *",
                (status, text, form, digest, BODY_VERSION, status, error,
                 state["mailbox_key"], state["label_name"], reply["id"]),
            ).fetchone()
            self._audit_automation(
                connection, state["campaign_id"], "creator.reply.body_captured", "creator-worker",
                task_id=task["id"], reply_id=str(reply["id"]), body_status=status,
                body_digest=digest, body_attempt_count=updated["body_attempt_count"],
            )
            self._check_task(connection, task, "marketing.gmail_sync")
            connection.commit()
        return reply_capture_summary(updated)

    def gmail_context(self, campaign_id: UUID, mailbox_key: str, label: str) -> dict[str, Any]:
        self.get_campaign(campaign_id)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO creator_gmail_sync_state(campaign_id,mailbox_key,label_name) "
                "VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (campaign_id, mailbox_key, label),
            )
            state = connection.execute(
                "SELECT * FROM creator_gmail_sync_state WHERE campaign_id=%s FOR UPDATE",
                (campaign_id,),
            ).fetchone()
            if state["mailbox_key"] != mailbox_key:
                raise MarketingOutreachError("Creator Gmail mailbox differs from recorded identity")
            if state["label_name"] != label:
                state = connection.execute(
                    "UPDATE creator_gmail_sync_state SET label_name=%s,page_token=NULL, "
                    "pending_message_ids='[]'::jsonb,last_complete_at=NULL,revision=revision+1 "
                    "WHERE campaign_id=%s RETURNING *",
                    (label, campaign_id),
                ).fetchone()
            connection.commit()
        return state

    def known_reply_ids(self, campaign_id: UUID, ids: list[str]) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT gmail_message_id FROM creator_reply_messages WHERE campaign_id=%s "
                "AND gmail_message_id=ANY(%s)",
                (campaign_id, ids),
            ).fetchall()
        return {row["gmail_message_id"] for row in rows}

    def save_gmail(
        self,
        task: dict[str, Any],
        state: dict[str, Any],
        messages: list[dict[str, Any]],
        *,
        cursor: str | None,
        pending: list[str],
        mark_complete: bool = True,
    ) -> dict[str, int]:
        campaign_id = UUID(str(task["payload"]["campaign_id"]))
        with self.connect() as connection:
            lock_automation(connection)
            self._check_task(connection, task, "marketing.gmail_sync")
            # Serialize new reply evidence with the final creator send boundary.
            connection.execute(
                "SELECT id FROM marketing_campaigns WHERE id=%s FOR UPDATE", (campaign_id,)
            )
            current = connection.execute(
                "SELECT * FROM creator_gmail_sync_state WHERE campaign_id=%s FOR UPDATE",
                (campaign_id,),
            ).fetchone()
            if not current or current["revision"] != state["revision"]:
                raise MarketingOutreachError("A concurrent mailbox sync changed the cursor")
            sent = connection.execute(
                """SELECT m.prospect_id,a.public_context->>'recipient' AS recipient,
                   a.public_context->>'subject' AS subject,a.updated_at AS sent_at
                   FROM marketing_outreach_messages m JOIN external_actions a ON a.id=m.action_id
                   JOIN marketing_prospects p ON p.id=m.prospect_id
                   WHERE p.campaign_id=%s AND a.status='succeeded'
                   ORDER BY a.updated_at DESC LIMIT 2000""",
                (campaign_id,),
            ).fetchall()
            foreign_sent = connection.execute(
                """SELECT m.prospect_id,p.campaign_id,
                   a.public_context->>'recipient' AS recipient,
                   a.public_context->>'subject' AS subject,a.executed_at AS sent_at
                   FROM marketing_outreach_messages m JOIN external_actions a ON a.id=m.action_id
                   JOIN marketing_prospects p ON p.id=m.prospect_id
                   WHERE a.status='succeeded' AND a.executed_at IS NOT NULL
                     AND lower(a.public_context->>'recipient')=ANY(%s)
                   ORDER BY a.executed_at DESC LIMIT 2000""",
                ([message["sender"].casefold() for message in messages],),
            ).fetchall()
            foreign_campaigns = {
                str(row["prospect_id"]): row["campaign_id"] for row in foreign_sent
            }
            inserted, suppressed, ignored_foreign = 0, 0, 0
            for message in messages:
                prospect_id, reason = correlate_creator_reply(message, sent)
                classification = classify_creator_reply(message)
                if classification == "do_not_contact":
                    suppressed += self._suppress_address(connection, message["sender"])
                matched_global, _ = correlate_creator_reply(message, foreign_sent)
                if (
                    matched_global is not None
                    and foreign_campaigns[str(matched_global)] != campaign_id
                ):
                    # One shared custom label can serve several campaigns. A confident
                    # foreign match must not become an unrelated campaign's review blocker.
                    ignored_foreign += 1
                    continue
                saved = connection.execute(
                    """INSERT INTO creator_reply_messages
                    (campaign_id,gmail_message_id,gmail_thread_id,sender,subject,snippet,received_at,
                     prospect_id,suggested_classification,match_reason,needs_review)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true)
                    ON CONFLICT DO NOTHING RETURNING id""",
                    (
                        campaign_id,
                        message["gmail_message_id"],
                        message["gmail_thread_id"],
                        message["sender"],
                        message["subject"],
                        message["snippet"],
                        message["received_at"],
                        prospect_id,
                        classification,
                        reason,
                    ),
                ).fetchone()
                if not saved:
                    continue
                inserted += 1
            connection.execute(
                "UPDATE creator_gmail_sync_state SET page_token=%s,pending_message_ids=%s, "
                "revision=revision+1,last_sync_at=now(),last_complete_at=CASE WHEN %s "
                "THEN now() ELSE last_complete_at END WHERE campaign_id=%s",
                (cursor, Jsonb(pending), mark_complete and not cursor and not pending, campaign_id),
            )
            self._audit_automation(
                connection,
                campaign_id,
                "creator.replies.synced",
                "creator-worker",
                task_id=task["id"],
                inserted=inserted,
                suppressed=suppressed,
                ignored_foreign=ignored_foreign,
            )
            self._check_task(connection, task, "marketing.gmail_sync")
            connection.commit()
        return {"inserted": inserted, "suppressed": suppressed, "ignored_foreign": ignored_foreign}

    @staticmethod
    def _suppress_address(connection: Any, sender: str) -> int:
        # Match the final delivery boundary's prospect -> recipient lock order.
        # Career and ordinary email sends share the recipient lock even though
        # they have no marketing prospect row to serialize an opt-out against.
        sender = sender.strip().casefold()
        rows = connection.execute(
            "UPDATE marketing_prospects SET status='suppressed',suppressed_at=now(), "
            "suppression_reason='Recipient requested no further outreach', "
            "contact_authorized_at=NULL,contact_authorized_by=NULL "
            "WHERE lower(contact_email)=lower(%s) AND suppressed_at IS NULL RETURNING id",
            (sender,),
        ).fetchall()
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"creator-email:{sender}",),
        )
        connection.execute(
            "INSERT INTO creator_contact_suppressions(email,reason) VALUES (lower(%s),%s) "
            "ON CONFLICT(email) DO NOTHING",
            (sender, "Recipient requested no further outreach"),
        )
        return len(rows)

    def review_reply(
        self, campaign_id: UUID, reply_id: UUID, request: CreatorReplyReview
    ) -> dict[str, Any]:
        with self.connect() as connection:
            lock_automation(connection)
            reply = connection.execute(
                "SELECT * FROM creator_reply_messages WHERE id=%s AND campaign_id=%s FOR UPDATE",
                (reply_id, campaign_id),
            ).fetchone()
            if not reply:
                raise MarketingOutreachError("Creator reply not found in this campaign")
            if not reply["needs_review"]:
                raise MarketingOutreachError("This creator reply was already reviewed")
            classification = request.classification
            if classification in {"interested", "question", "declined_unpaid"} and (
                not complete_reply_body(reply) or request.body_digest != reply["body_digest"]
            ):
                raise MarketingOutreachError("Review needs the complete current reply body digest")
            prospect_id = request.prospect_id or reply["prospect_id"]
            if classification == "ignore":
                prospect_id = reply["prospect_id"]
            if classification != "ignore":
                prospect = connection.execute(
                    "SELECT * FROM marketing_prospects WHERE id=%s AND campaign_id=%s FOR UPDATE",
                    (prospect_id, campaign_id),
                ).fetchone()
                if (
                    not prospect
                    or not prospect["contact_email"]
                    or prospect["contact_email"].casefold() != reply["sender"].casefold()
                ):
                    raise MarketingOutreachError(
                        "Select the campaign creator with this exact address"
                    )
                if classification in {"do_not_contact", "bounced"}:
                    self._suppress_address(connection, reply["sender"])
                else:
                    if prospect["suppressed_at"] or prospect["status"] in {
                        "handed_off",
                        "converted",
                    }:
                        raise MarketingOutreachError(
                            "Suppressed or handed-off creators stay terminal"
                        )
                    if not connection.execute(
                        "SELECT 1 FROM marketing_outreach_messages m JOIN external_actions a "
                        "ON a.id=m.action_id WHERE m.prospect_id=%s AND a.status='succeeded' "
                        "AND a.updated_at<=%s LIMIT 1",
                        (prospect_id, reply["received_at"]),
                    ).fetchone():
                        raise MarketingOutreachError("A reply requires a prior successful outreach")
                    connection.execute(
                        "UPDATE marketing_prospects SET status=%s WHERE id=%s",
                        (classification, prospect_id),
                    )
                connection.execute(
                    "INSERT INTO marketing_outcomes"
                    "(prospect_id,classification,note,recorded_by,feedback_tags) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (
                        prospect_id,
                        classification,
                        (request.note.strip() or reply["snippet"] or "Reviewed creator reply")[
                            :4000
                        ],
                        request.actor,
                        Jsonb(request.feedback_tags),
                    ),
                )
            updated = connection.execute(
                "UPDATE creator_reply_messages SET needs_review=false,reviewed_by=%s, "
                "reviewed_at=now(),reviewed_classification=%s,prospect_id=%s,"
                "reviewed_body_digest=%s "
                "WHERE id=%s RETURNING *",
                (request.actor, classification, prospect_id,
                 reply["body_digest"] if complete_reply_body(reply) else None, reply_id),
            ).fetchone()
            self._audit_automation(
                connection,
                campaign_id,
                "creator.reply.reviewed",
                request.actor,
                reply_id=str(reply_id),
                classification=classification,
                body_digest=reply["body_digest"] if complete_reply_body(reply) else None,
            )
            connection.commit()
        return {key: value for key, value in updated.items() if key not in {
            "body_text", "body_mailbox_key", "body_label_name", "body_capture_task_id",
            "body_capture_lease_id",
        }}
