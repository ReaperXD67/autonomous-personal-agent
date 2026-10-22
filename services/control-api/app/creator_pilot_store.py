from __future__ import annotations

from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from app.application_browser import canonical_hash
from app.creator_contact_history import merge_contact_history
from app.creator_pilot import DAILY_CREATORS, KIND, MAX_CREATORS, campaign_snapshot
from app.marketing import contact_is_suppressed
from app.marketing_store import (
    MarketingCampaignNotFoundError,
    MarketingOutreachError,
    MarketingProspectNotFoundError,
    MarketingStore,
)
from app.models import TaskCreate
from app.store import InvalidTaskStateError


class CreatorPilotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    actor: str = Field(min_length=1, max_length=120)
    idempotency_key: UUID
    limit: int = Field(default=5, ge=1, le=MAX_CREATORS, strict=True)


class CreatorPilotStore(MarketingStore):
    @staticmethod
    def _issued(connection, task):
        return connection.execute(
            "SELECT 1 FROM audit_events WHERE task_id=%s AND action='creator.pilot.created' "
            "AND input_metadata->>'payload_hash'=%s",
            (task["id"], canonical_hash(task["payload"])),
        ).fetchone() is not None

    def create_pilot(self, campaign_id, request):
        with self.connect() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtext('creator-pilot-budget'))")
            key = f"creator-pilot:{request.idempotency_key}"
            existing = connection.execute(
                "SELECT * FROM agent_tasks WHERE idempotency_key=%s", (key,),
            ).fetchone()
            if existing:
                if (existing["kind"] != KIND or existing["requested_by"] != request.actor
                        or existing["payload"].get("campaign_id") != str(campaign_id)
                        or existing["payload"].get("requested_limit") != request.limit
                        or not self._issued(connection, existing)):
                    raise MarketingOutreachError("Idempotency key belongs to another request")
                return existing
            campaign = connection.execute(
                "SELECT * FROM marketing_campaigns WHERE id=%s FOR SHARE", (campaign_id,),
            ).fetchone()
            if campaign is None:
                raise MarketingCampaignNotFoundError(str(campaign_id))
            pending = connection.execute(
                "SELECT id FROM agent_tasks WHERE kind=%s AND payload->>'campaign_id'=%s "
                "AND status IN ('queued','running','pending_approval') LIMIT 1",
                (KIND, str(campaign_id)),
            ).fetchone()
            if pending:
                raise MarketingOutreachError(
                    "This campaign already has an active pilot research task"
                )
            rows = connection.execute(
                "SELECT p.* FROM marketing_prospects p WHERE campaign_id=%s "
                "AND platform='youtube' AND status IN ('discovered','qualified') "
                "AND suppressed_at IS NULL "
                "AND NOT EXISTS (SELECT 1 FROM marketing_outreach_messages m "
                "WHERE m.prospect_id=p.id) "
                "ORDER BY relevance_score DESC, last_seen_at DESC, id LIMIT 500",
                (campaign_id,),
            ).fetchall()
            # Existing intelligence narrows the pool; fresh API metadata determines final rank.
            candidates = [
                row for row in rows
                if "Minecraft" in (row.get("intelligence") or {}).get("topics", [])
                and not contact_is_suppressed(connection, row.get("contact_email"))
            ]
            candidates.sort(key=lambda row: (
                -int(bool((row.get("intelligence") or {}).get("contact_candidates"))),
                -row["relevance_score"], str(row["id"]),
            ))
            candidates = candidates[:request.limit]
            if not candidates:
                raise MarketingOutreachError(
                    "No uncontacted Minecraft candidates; run creator discovery first"
                )
            used = connection.execute(
                "SELECT COALESCE(sum((input_metadata->>'batch_size')::int),0) AS count "
                "FROM audit_events WHERE action='creator.pilot.created' "
                "AND occurred_at > now()-interval '24 hours'",
            ).fetchone()["count"]
            if used + len(candidates) > DAILY_CREATORS:
                raise MarketingOutreachError(
                    "Pilot research limit reached: thirty creator refreshes per rolling day"
                )
            payload = {
                "campaign_id": str(campaign_id), "requested_limit": request.limit,
                "reservation_id": str(uuid4()),
                "campaign_hash": canonical_hash(campaign_snapshot(campaign)),
                "prospect_ids": [str(row["id"]) for row in candidates],
                "profile_urls": {str(row["id"]): row["profile_url"] for row in candidates},
            }
            task = self._create_task_record(connection, TaskCreate(
                title="Research and rank a bounded creator pilot",
                kind=KIND, payload=payload, requested_by=request.actor, idempotency_key=key,
            ))
            # A generic task insert can race the unique key; never bless its caller payload.
            if (task["payload"] != payload or task["kind"] != KIND
                    or task["requested_by"] != request.actor):
                raise MarketingOutreachError("Idempotency key belongs to another request")
            self._append_audit(
                connection, correlation_id=task["correlation_id"], task_id=task["id"],
                actor_type="user", actor_id=request.actor, tool_name=KIND,
                action="creator.pilot.created", risk_level="low", approval_status="not_required",
                execution_status="queued",
                input_metadata={"payload_hash": canonical_hash(payload),
                                "batch_size": len(candidates), "campaign_id": str(campaign_id)},
                result_metadata={"contact_authorizations": 0, "messages_sent": 0},
            )
            return task

    def latest_pilot(self, campaign_id):
        self.get_campaign(campaign_id)
        with self.connect() as connection:
            return connection.execute(
                "SELECT t.* FROM agent_tasks t WHERE kind=%s AND payload->>'campaign_id'=%s "
                "AND EXISTS (SELECT 1 FROM audit_events a WHERE a.task_id=t.id "
                "AND a.action='creator.pilot.created') ORDER BY created_at DESC,id DESC LIMIT 1",
                (KIND, str(campaign_id)),
            ).fetchone()

    def _owned_task(self, connection, task_id, lease_id):
        task = connection.execute(
            "SELECT * FROM agent_tasks WHERE id=%s FOR UPDATE", (task_id,),
        ).fetchone()
        now = connection.execute("SELECT clock_timestamp() AS value").fetchone()["value"]
        if (task is None or task["kind"] != KIND or task["status"] != "running"
                or task["lease_id"] != lease_id or task["cancellation_requested_at"] is not None
                or task["lease_expires_at"] is None or task["lease_expires_at"] <= now):
            raise InvalidTaskStateError("Pilot research no longer owns a valid execution lease")
        if not self._issued(connection, task):
            raise InvalidTaskStateError("Pilot research lacks a server-issued bounded reservation")
        return task

    def _context(self, connection, task_id, lease_id, prospect_id=None):
        task = self._owned_task(connection, task_id, lease_id)
        payload = task["payload"]
        campaign = connection.execute(
            "SELECT * FROM marketing_campaigns WHERE id=%s FOR SHARE",
            (UUID(payload["campaign_id"]),),
        ).fetchone()
        if (campaign is None
                or canonical_hash(campaign_snapshot(campaign)) != payload["campaign_hash"]):
            raise InvalidTaskStateError("Campaign targeting changed during pilot research")
        prospect = None
        if prospect_id is not None:
            if str(prospect_id) not in payload["prospect_ids"]:
                raise InvalidTaskStateError("Creator was not reserved for this pilot")
            prospect = connection.execute(
                "SELECT * FROM marketing_prospects WHERE id=%s FOR UPDATE", (prospect_id,),
            ).fetchone()
            if prospect is None:
                raise MarketingProspectNotFoundError(str(prospect_id))
            if (prospect["campaign_id"] != campaign["id"] or prospect["platform"] != "youtube"
                    or prospect["profile_url"] != payload["profile_urls"][str(prospect_id)]
                    or prospect["suppressed_at"] is not None
                    or prospect["status"] not in {"discovered", "qualified"}
                    or contact_is_suppressed(connection, prospect.get("contact_email"))):
                raise InvalidTaskStateError("Creator identity or outreach eligibility changed")
            if connection.execute(
                "SELECT 1 FROM marketing_outreach_messages WHERE prospect_id=%s LIMIT 1",
                (prospect_id,),
            ).fetchone():
                raise InvalidTaskStateError("Creator already has an outreach packet")
        # Campaign/prospect lock waits may outlive the lease.
        self._owned_task(connection, task_id, lease_id)
        return task, campaign, prospect

    def pilot_context(self, task_id, lease_id, prospect_id=None):
        with self.connect() as connection:
            return self._context(connection, task_id, lease_id, prospect_id)

    def save_pilot_research(self, task_id, lease_id, prospect_id, research):
        with self.connect() as connection:
            _, campaign, prospect = self._context(connection, task_id, lease_id, prospect_id)
            intelligence = merge_contact_history(
                prospect.get("intelligence", {}), research["intelligence"],
            )
            row = connection.execute(
                "UPDATE marketing_prospects SET audience_size=%s,latest_content_title=%s,"
                "latest_content_url=%s,latest_content_published_at=%s,relevance_score=%s,"
                "relevance_reasons=%s,intelligence=%s,last_seen_at=now() WHERE id=%s RETURNING *",
                (research.get("audience_size"), research.get("latest_content_title"),
                 research.get("latest_content_url"), research.get("latest_content_published_at"),
                 research["relevance_score"], Jsonb(research["relevance_reasons"]),
                 Jsonb(intelligence), prospect_id),
            ).fetchone()
            owned = self._owned_task(connection, task_id, lease_id)
            self._append_audit(
                connection, correlation_id=owned["correlation_id"],
                task_id=task_id, actor_type="worker", actor_id="job-worker", tool_name=KIND,
                action="creator.pilot.researched", risk_level="low",
                approval_status="not_required", execution_status="succeeded",
                input_metadata={"prospect_id": str(prospect_id)},
                result_metadata={"contact_authorizations": 0, "messages_sent": 0},
            )
            return campaign, row
