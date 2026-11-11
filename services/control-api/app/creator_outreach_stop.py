"""Durable owner stop for every creator email, independent of finite run grants."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.models import TaskCancellation
from app.store import InvalidTaskStateError

STOP_FIELDS = (
    "outreach_paused", "outreach_epoch", "outreach_stopped_at",
    "outreach_stopped_by", "outreach_stop_reason",
)


def outreach_stop_reason(
    campaign: dict[str, Any], marketing: dict[str, Any] | None = None,
) -> str | None:
    if campaign.get("outreach_paused"):
        return "Creator mailing is stopped by the owner; explicit resumption is required"
    if marketing is not None and marketing.get("outreach_epoch", 0) != campaign.get(
        "outreach_epoch", 0,
    ):
        return "Creator email authority predates an owner stop; old approval cannot resume"
    return None


def action_outreach_stop_reason(connection: Any, action: dict[str, Any]) -> str | None:
    """Approval locks the campaign before pacing, matching the receipt boundary."""
    if action["action_type"] != "communications.email_send":
        return None
    marketing = action["private_context"].get("marketing")
    if not isinstance(marketing, dict):
        return None
    campaign = connection.execute(
        "SELECT * FROM marketing_campaigns WHERE id=%s FOR SHARE",
        (marketing.get("campaign_id"),),
    ).fetchone()
    if campaign is None:
        return "Creator email campaign no longer exists"
    return outreach_stop_reason(campaign, marketing)


class CreatorOutreachStopMixin:
    def _outreach_stop_audit(self, connection, campaign_id, actor, action, **metadata):
        self._append_audit(
            connection, correlation_id=uuid4(), task_id=None,
            actor_type="user", actor_id=actor, tool_name="marketing.outreach_stop",
            action=action, risk_level="medium", approval_status="not_required",
            execution_status="succeeded",
            input_metadata={"campaign_id": str(campaign_id), **metadata},
        )

    def stop_outreach(self, campaign_id: UUID, actor: str, reason: str) -> dict[str, Any]:
        from app.marketing_store import MarketingCampaignNotFoundError

        with self.connect() as connection:
            # Scheduling/start already use this advisory lock before campaign/run rows.
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended('creator-automation', 0))",
            )
            campaign = connection.execute(
                "SELECT * FROM marketing_campaigns WHERE id=%s FOR UPDATE", (campaign_id,),
            ).fetchone()
            if campaign is None:
                raise MarketingCampaignNotFoundError(str(campaign_id))
            stopped = connection.execute(
                "UPDATE marketing_campaigns SET outreach_paused=true, active=false, "
                "outreach_epoch=outreach_epoch+CASE WHEN outreach_paused THEN 0 ELSE 1 END, "
                "outreach_stopped_at=CASE WHEN outreach_paused THEN outreach_stopped_at "
                "ELSE clock_timestamp() END, "
                "outreach_stopped_by=%s,outreach_stop_reason=%s WHERE id=%s RETURNING *",
                (actor, reason, campaign_id),
            ).fetchone()
            connection.execute(
                "UPDATE creator_automation_runs SET state='paused',paused_at=now(),reason=%s "
                "WHERE campaign_id=%s AND state='running'", (reason, campaign_id),
            )
            self._outreach_stop_audit(
                connection, campaign_id, actor, "creator.outreach.stopped",
                outreach_epoch=stopped["outreach_epoch"], reason_provided=bool(reason),
            )
            # Never hold the campaign/run rows while acquiring task locks: execution
            # owns task/action first. The durable stop and epoch fence are committed
            # before this best-effort cleanup, so interruption cannot restore egress.
            connection.commit()

        cancelled = 0
        cancellation_requested = 0
        while True:
            with self.connect() as connection:
                pending = connection.execute(
                    "SELECT t.id FROM agent_tasks t JOIN external_actions a ON a.task_id=t.id "
                    "WHERE a.action_type='communications.email_send' "
                    "AND a.private_context->'marketing'->>'campaign_id'=%s "
                    "AND COALESCE(a.private_context->'marketing'->>'outreach_epoch','0')"
                    "::bigint<%s "
                    "AND t.status IN ('pending_approval','queued','running') "
                    "AND t.cancellation_requested_at IS NULL ORDER BY t.id LIMIT 200",
                    (str(campaign_id), stopped["outreach_epoch"]),
                ).fetchall()
            if not pending:
                break
            for item in pending:
                try:
                    task = self.cancel_task(
                        item["id"], TaskCancellation(actor=actor, reason=reason),
                    )
                except InvalidTaskStateError:
                    # A concurrent receipt/completion remains authoritative.
                    continue
                if task["status"] == "cancelled":
                    cancelled += 1
                else:
                    cancellation_requested += 1
        with self.connect() as connection:
            remaining = connection.execute(
                "SELECT count(*) FILTER (WHERE a.status='executing')::int AS in_flight, "
                "count(*) FILTER (WHERE a.status='ambiguous')::int AS ambiguous "
                "FROM external_actions a WHERE a.action_type='communications.email_send' "
                "AND a.private_context->'marketing'->>'campaign_id'=%s",
                (str(campaign_id),),
            ).fetchone()
        return {
            "campaign_id": campaign_id, **{key: stopped[key] for key in STOP_FIELDS},
            "discovery_active": False, "cancelled_tasks": cancelled,
            "cancellation_requested_tasks": cancellation_requested,
            "in_flight_actions": remaining["in_flight"],
            "ambiguous_actions": remaining["ambiguous"],
        }

    def resume_outreach(self, campaign_id: UUID, actor: str) -> dict[str, Any]:
        from app.marketing_store import MarketingCampaignNotFoundError

        with self.connect() as connection:
            campaign = connection.execute(
                "UPDATE marketing_campaigns SET outreach_paused=false "
                "WHERE id=%s RETURNING *", (campaign_id,),
            ).fetchone()
            if campaign is None:
                raise MarketingCampaignNotFoundError(str(campaign_id))
            self._outreach_stop_audit(
                connection, campaign_id, actor, "creator.outreach.resumed",
                outreach_epoch=campaign["outreach_epoch"],
            )
            connection.commit()
        # The epoch, cancelled tasks, paused runs and discovery setting stay intact.
        return {"campaign_id": campaign_id, **{key: campaign[key] for key in STOP_FIELDS}}
