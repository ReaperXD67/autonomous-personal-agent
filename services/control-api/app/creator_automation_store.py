from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.creator_automation import (
    automation_campaign_hash,
    classify_creator_reply,
    correlate_creator_reply,
    creator_eligibility_reason,
    creator_key,
    pending_reply_reason,
    run_block_reason,
)
from app.creator_automation_models import CreatorAutomationStart, CreatorReplyReview
from app.creator_learning import suggested_feedback_tags
from app.marketing_models import MarketingEmailPlanCreate
from app.marketing_store import (
    MarketingCampaignNotFoundError,
    MarketingOutreachError,
    MarketingStore,
)
from app.models import ApprovalDecision, TaskCancellation, TaskCreate
from app.store import InvalidTaskStateError


def lock_automation(connection: Any) -> None:
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('creator-automation', 0))")


class CreatorAutomationStore(MarketingStore):
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
        self.get_campaign(campaign_id)
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
                "SELECT * FROM creator_reply_messages WHERE campaign_id=%s AND needs_review "
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
        public = [self._public_run(run) for run in runs]
        for reply in replies:
            reply["suggested_feedback_tags"] = suggested_feedback_tags(reply["snippet"])
        return {
            "run": public[0] if public else None,
            "runs": public,
            "pending_replies": replies,
            **counts,
            "gmail_sync": sync,
        }

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
            if (
                run["monitor_gmail"]
                and not connection.execute(
                    "SELECT 1 FROM creator_gmail_sync_state WHERE campaign_id=%s "
                    "AND last_complete_at>now()-interval '30 minutes'",
                    (campaign_id,),
                ).fetchone()
            ):
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
            existing = connection.execute(
                "SELECT * FROM agent_tasks WHERE kind='marketing.gmail_sync' "
                "AND payload->>'campaign_id'=%s AND (status IN ('queued','running') "
                "OR created_at>now()-interval '1 minute') ORDER BY created_at DESC LIMIT 1",
                (str(campaign_id),),
            ).fetchone()
            task = existing or self._create_task_record(
                connection,
                TaskCreate(
                    title="Read labeled creator replies",
                    kind="marketing.gmail_sync",
                    payload={"campaign_id": str(campaign_id)},
                    requested_by=actor,
                    idempotency_key=f"creator-mail:{campaign_id}:{uuid4()}",
                ),
            )
            connection.commit()
        return task

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
                (cursor, Jsonb(pending), not cursor and not pending, campaign_id),
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
        connection.execute(
            "INSERT INTO creator_contact_suppressions(email,reason) VALUES (lower(%s),%s) "
            "ON CONFLICT(email) DO NOTHING",
            (sender, "Recipient requested no further outreach"),
        )
        rows = connection.execute(
            "UPDATE marketing_prospects SET status='suppressed',suppressed_at=now(), "
            "suppression_reason='Recipient requested no further outreach', "
            "contact_authorized_at=NULL,contact_authorized_by=NULL "
            "WHERE lower(contact_email)=lower(%s) AND suppressed_at IS NULL RETURNING id",
            (sender,),
        ).fetchall()
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
                "reviewed_at=now(),reviewed_classification=%s,prospect_id=%s "
                "WHERE id=%s RETURNING *",
                (request.actor, classification, prospect_id, reply_id),
            ).fetchone()
            self._audit_automation(
                connection,
                campaign_id,
                "creator.reply.reviewed",
                request.actor,
                reply_id=str(reply_id),
                classification=classification,
            )
            connection.commit()
        return updated
