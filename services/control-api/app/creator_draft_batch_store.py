"""Issued, bounded preparation batches. No message preparation or send authority."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from app.application_browser import canonical_hash
from app.creator_automation import creator_eligibility_reason
from app.creator_draft_content import draft_input_snapshot
from app.creator_draft_models import CreatorDraftCreate
from app.creator_draft_store import CreatorDraftConflictError, CreatorDraftStore
from app.marketing import campaign_outreach_hash, outreach_duplicate_action
from app.marketing_store import MarketingCampaignNotFoundError, MarketingOutreachError
from app.models import TaskCreate, TaskView
from app.store import InvalidTaskStateError
from app.worker import TaskInterruptedError

KIND = "marketing.creator_draft_batch"
MAX_BATCH = 5
CREATED = "creator.draft_batch.created"
ITEM_RECORDED = "creator.draft_batch.item"
LIMITS = {
    "max_batch": MAX_BATCH,
    "drafts_per_rolling_day": 30,
    "drafts_per_prospect_per_rolling_day": 3,
    "messages_sent": 0,
    "approvals_created": 0,
}


class CreatorDraftBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    actor: str = Field(min_length=1, max_length=120)
    idempotency_key: UUID
    limit: int = Field(default=3, ge=1, le=MAX_BATCH, strict=True)


class CreatorDraftBatchView(BaseModel):
    task: TaskView
    items: list[dict]
    limits: dict[str, int]
    reserved_count: int
    queued_count: int
    skipped_count: int


class CreatorDraftBatchNotFoundError(LookupError):
    pass


def batch_items(payload):
    """Reject malformed generic tasks before inspecting or issuing any child."""
    if (not isinstance(payload, dict)
            or set(payload) != {"campaign_id", "requested_limit", "campaign_hash", "items"}
            or type(payload["requested_limit"]) is not int
            or not 1 <= payload["requested_limit"] <= MAX_BATCH):
        raise InvalidTaskStateError("Draft batch payload is not a bounded reservation")
    items = payload["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= payload["requested_limit"]:
        raise InvalidTaskStateError("Draft batch exceeds its bounded reservation")
    identities, keys = set(), set()
    try:
        UUID(payload["campaign_id"])
        for value in [payload["campaign_hash"], *(item["input_hash"] for item in items)]:
            if (not isinstance(value, str) or len(value) != 64
                    or any(char not in "0123456789abcdef" for char in value)):
                raise ValueError
        for item in items:
            if set(item) != {"prospect_id", "input_hash", "child_idempotency_key"}:
                raise ValueError
            identity, key = UUID(item["prospect_id"]), UUID(item["child_idempotency_key"])
            if identity in identities or key in keys:
                raise ValueError
            identities.add(identity)
            keys.add(key)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise InvalidTaskStateError("Draft batch contains an invalid reserved identity") from None
    return items


def creator_identity_keys(prospect):
    keys = set()
    if prospect.get("platform") and prospect.get("external_id"):
        keys.add(("creator", prospect["platform"], prospect["external_id"]))
    profile = str(prospect.get("profile_url") or "").strip().rstrip("/").casefold()
    email = str(prospect.get("contact_email") or "").strip().casefold()
    if profile:
        keys.add(("profile", profile))
    if email:
        keys.add(("email", email))
    return keys


class CreatorDraftBatchStore(CreatorDraftStore):
    @staticmethod
    def _issued_batch(connection, task):
        return connection.execute(
            "SELECT 1 FROM audit_events WHERE task_id=%s AND action=%s "
            "AND input_metadata->>'payload_hash'=%s",
            (task["id"], CREATED, canonical_hash(task["payload"])),
        ).fetchone() is not None

    def _owned_batch(self, connection, task_id, lease_id):
        task = connection.execute(
            "SELECT * FROM agent_tasks WHERE id=%s FOR UPDATE", (task_id,),
        ).fetchone()
        now = connection.execute("SELECT clock_timestamp() AS value").fetchone()["value"]
        if (task is None or task["kind"] != KIND or task["status"] != "running"
                or task["lease_id"] != lease_id or task["cancellation_requested_at"] is not None
                or task["lease_expires_at"] is None or task["lease_expires_at"] <= now
                or task["created_at"] + timedelta(hours=24) <= now):
            raise InvalidTaskStateError("Draft batch no longer owns a valid execution lease")
        batch_items(task["payload"])
        if not self._issued_batch(connection, task):
            raise InvalidTaskStateError("Draft batch lacks a server-issued bounded reservation")
        return task

    @staticmethod
    def _has_current_draft(connection, prospect_id, input_hash, *, exclude_key=None):
        return connection.execute(
            "SELECT 1 FROM creator_email_drafts d JOIN agent_tasks t ON t.id=d.task_id "
            "WHERE d.prospect_id=%s AND d.input_hash=%s AND d.expires_at>now() "
            "AND d.status IN ('queued','ready','prepared') "
            "AND t.status NOT IN ('failed','cancelled','rejected','dead_lettered') "
            "AND (%s::uuid IS NULL OR d.idempotency_key<>%s) LIMIT 1",
            (prospect_id, input_hash, exclude_key, exclude_key),
        ).fetchone() is not None

    def _occupied_identities(self, connection, *, exclude_key=None):
        reservations = self._draft_reservations(connection)
        reserved_ids = {value[0] for key, value in reservations.items() if key != exclude_key}
        keys = set()
        if reserved_ids:
            rows = connection.execute(
                "SELECT * FROM marketing_prospects WHERE id=ANY(%s)", (list(reserved_ids),),
            ).fetchall()
            for prospect in rows:
                keys.update(creator_identity_keys(prospect))
        rows = connection.execute(
            "SELECT p.*,to_jsonb(c) AS _campaign,d.input_hash AS _draft_input_hash "
            "FROM creator_email_drafts d JOIN marketing_prospects p ON p.id=d.prospect_id "
            "JOIN marketing_campaigns c ON c.id=p.campaign_id "
            "JOIN agent_tasks t ON t.id=d.task_id "
            "WHERE d.status IN ('queued','ready','prepared') AND d.expires_at>now() "
            "AND t.status NOT IN ('failed','cancelled','rejected','dead_lettered') "
            "AND (%s::uuid IS NULL OR d.idempotency_key<>%s)",
            (exclude_key, exclude_key),
        ).fetchall()
        for prospect in rows:
            campaign = prospect.pop("_campaign")
            draft_hash = prospect.pop("_draft_input_hash")
            if canonical_hash(draft_input_snapshot(campaign, prospect)) == draft_hash:
                keys.update(creator_identity_keys(prospect))
        return keys

    def _batch_eligibility(
        self, connection, campaign, prospect, *, exclude_key=None, occupied=None,
    ):
        self._eligible(connection, campaign, prospect)
        reason = creator_eligibility_reason(campaign, prospect)
        if reason:
            raise CreatorDraftConflictError(reason)
        if outreach_duplicate_action(connection, prospect, "initial") is not None:
            raise CreatorDraftConflictError("Creator already has an outreach conversation")
        snapshot_hash = canonical_hash(draft_input_snapshot(campaign, prospect))
        if self._has_current_draft(
            connection, prospect["id"], snapshot_hash, exclude_key=exclude_key,
        ):
            raise CreatorDraftConflictError("Creator already has a current introduction draft")
        if occupied is None:
            occupied = self._occupied_identities(connection, exclude_key=exclude_key)
        if creator_identity_keys(prospect) & occupied:
            raise CreatorDraftConflictError(
                "Creator or business address already has a draft reservation"
            )
        return snapshot_hash

    def create_batch(self, campaign_id, request):
        with self.connect() as connection:
            self._draft_budget_lock(connection)
            key = f"creator-draft-batch:{request.idempotency_key}"
            existing = connection.execute(
                "SELECT * FROM agent_tasks WHERE idempotency_key=%s", (key,),
            ).fetchone()
            if existing:
                if (existing["kind"] != KIND or existing["requested_by"] != request.actor
                        or existing["payload"].get("campaign_id") != str(campaign_id)
                        or existing["payload"].get("requested_limit") != request.limit
                        or not self._issued_batch(connection, existing)):
                    raise MarketingOutreachError("Idempotency key belongs to another request")
                batch_items(existing["payload"])
                return self._batch_view(connection, existing)
            campaign = connection.execute(
                "SELECT * FROM marketing_campaigns WHERE id=%s FOR UPDATE", (campaign_id,),
            ).fetchone()
            if campaign is None:
                raise MarketingCampaignNotFoundError(str(campaign_id))
            remaining = 30 - self._draft_budget_counts(connection)["total"]
            if remaining <= 0:
                raise MarketingOutreachError("AI preparation limit reached: thirty per rolling day")
            rows = connection.execute(
                "SELECT p.id,(SELECT count(*) FROM creator_email_drafts d "
                "WHERE d.prospect_id=p.id AND d.created_at>now()-interval '24 hours') "
                "AS recent_drafts FROM marketing_prospects p "
                "WHERE p.campaign_id=%s AND p.platform='youtube' "
                "AND p.status IN ('discovered','qualified') AND p.suppressed_at IS NULL "
                "AND p.contact_authorized_at IS NOT NULL AND p.contact_email IS NOT NULL "
                "AND p.intelligence->'topics' @> '[\"Minecraft\"]'::jsonb "
                "AND p.audience_size BETWEEN %s AND %s "
                "AND p.latest_content_published_at BETWEEN "
                "now()-make_interval(days => %s) AND now() "
                "AND p.last_seen_at>now()-interval '7 days' "
                "AND NOT EXISTS (SELECT 1 FROM creator_contact_suppressions s "
                "WHERE s.email=lower(p.contact_email)) "
                "AND (%s<>'strict' OR p.intelligence->'geography'->>'country_code'=%s) "
                "AND (%s<>'strict' OR p.intelligence->'geography'->>'language_code'=%s "
                "OR p.intelligence->'geography'->>'language_code' LIKE %s) "
                "ORDER BY (SELECT max(d.created_at) FROM creator_email_drafts d "
                "WHERE d.prospect_id=p.id) ASC NULLS FIRST,p.relevance_score DESC,p.id LIMIT 500",
                (campaign_id, campaign["min_subscribers"], campaign["max_subscribers"],
                 campaign["max_video_age_days"], campaign["country_mode"],
                 campaign["target_country"], campaign["language_mode"],
                 campaign["target_language"], (campaign["target_language"] or "") + "-%"),
            ).fetchall()
            reservations = self._draft_reservations(connection)
            reserved_ids = {value[0] for value in reservations.values()}
            occupied = self._occupied_identities(connection)
            items = []
            for candidate in rows:
                if candidate["id"] in reserved_ids:
                    continue
                if candidate["recent_drafts"] >= 3:
                    continue
                current_campaign, prospect = self._context(connection, candidate["id"], lock=True)
                try:
                    snapshot_hash = self._batch_eligibility(
                        connection, current_campaign, prospect, occupied=occupied,
                    )
                except CreatorDraftConflictError:
                    continue
                items.append({
                    "prospect_id": str(prospect["id"]), "input_hash": snapshot_hash,
                    "child_idempotency_key": str(uuid5(
                        request.idempotency_key, str(prospect["id"]),
                    )),
                })
                occupied.update(creator_identity_keys(prospect))
                if len(items) >= min(request.limit, remaining):
                    break
            if not items:
                raise MarketingOutreachError(
                    "No eligible reviewed contacts without a current draft or conversation"
                )
            payload = {"campaign_id": str(campaign_id), "requested_limit": request.limit,
                       "campaign_hash": campaign_outreach_hash(campaign), "items": items}
            task = self._create_task_record(connection, TaskCreate(
                title="Prepare a bounded batch of creator drafts for review", kind=KIND,
                payload=payload, requested_by=request.actor, idempotency_key=key,
            ))
            if (task["payload"] != payload or task["kind"] != KIND
                    or task["requested_by"] != request.actor):
                raise MarketingOutreachError("Idempotency key belongs to another request")
            self._append_audit(
                connection, correlation_id=task["correlation_id"], task_id=task["id"],
                actor_type="user", actor_id=request.actor, tool_name=KIND, action=CREATED,
                risk_level="medium", approval_status="not_required", execution_status="queued",
                input_metadata={"payload_hash": canonical_hash(payload), "batch_size": len(items),
                                "campaign_id": str(campaign_id)},
                result_metadata={"messages_sent": 0, "approvals_created": 0},
            )
            return self._batch_view(connection, task)

    def _batch_view(self, connection, task):
        recorded = connection.execute(
            "SELECT input_metadata,result_metadata FROM audit_events "
            "WHERE task_id=%s AND action=%s ORDER BY occurred_at,id",
            (task["id"], ITEM_RECORDED),
        ).fetchall()
        outcomes = {row["input_metadata"]["prospect_id"]: row["result_metadata"]
                    for row in recorded}
        items = []
        for reserved in batch_items(task["payload"]):
            identity = reserved["prospect_id"]
            prospect = connection.execute(
                "SELECT display_name FROM marketing_prospects WHERE id=%s", (UUID(identity),),
            ).fetchone()
            row = connection.execute(
                "SELECT * FROM creator_email_drafts WHERE idempotency_key=%s "
                "AND prospect_id=%s AND requested_by=%s AND input_hash=%s",
                (UUID(reserved["child_idempotency_key"]), UUID(identity), task["requested_by"],
                 reserved["input_hash"]),
            ).fetchone()
            item = {"prospect_id": identity,
                    "display_name": prospect["display_name"] if prospect else "Recorded creator",
                    "draft_id": None, "task_id": None,
                    "status": "reserved", "reason": None}
            if identity in outcomes:
                item.update(outcomes[identity])
            if row is not None:
                view = self._view(connection, row)
                item.update(draft_id=str(row["id"]), task_id=str(row["task_id"]),
                            status=view["status"], reason=view.get("error_code"))
            items.append(item)
        return {
            "task": task, "items": items, "limits": dict(LIMITS),
            "reserved_count": sum(item["status"] == "reserved" for item in items),
            "queued_count": sum(item["status"] == "queued" for item in items),
            "skipped_count": sum(item["status"] == "skipped" for item in items),
        }

    def get_batch(self, task_id):
        with self.connect() as connection:
            task = connection.execute(
                "SELECT * FROM agent_tasks WHERE id=%s AND kind=%s", (task_id, KIND),
            ).fetchone()
            if task is None or not self._issued_batch(connection, task):
                raise CreatorDraftBatchNotFoundError(str(task_id))
            return self._batch_view(connection, task)

    def latest_batch(self, campaign_id):
        self.get_campaign(campaign_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_tasks t WHERE kind=%s AND payload->>'campaign_id'=%s "
                "AND EXISTS (SELECT 1 FROM audit_events a WHERE a.task_id=t.id AND a.action=%s) "
                "ORDER BY created_at DESC,id DESC LIMIT 30", (KIND, str(campaign_id), CREATED),
            ).fetchall()
            for task in rows:
                if self._issued_batch(connection, task):
                    return self._batch_view(connection, task)
            return None

    def batch_context(self, task_id, lease_id):
        with self.connect() as connection:
            return self._owned_batch(connection, task_id, lease_id)

    def _queue_reserved_child(self, task_id, lease_id, item):
        with self.connect() as connection:
            self._draft_budget_lock(connection)
            task = self._owned_batch(connection, task_id, lease_id)
            if item not in batch_items(task["payload"]):
                raise InvalidTaskStateError("Creator was not reserved in this draft batch")
            recorded = connection.execute(
                "SELECT result_metadata FROM audit_events WHERE task_id=%s AND action=%s "
                "AND input_metadata->>'prospect_id'=%s LIMIT 1",
                (task_id, ITEM_RECORDED, item["prospect_id"]),
            ).fetchone()
            if recorded:
                return recorded["result_metadata"]
            campaign, prospect = self._context(connection, UUID(item["prospect_id"]), lock=True)
            # Locks may wait longer than the execution lease. Never issue a child afterwards.
            self._owned_batch(connection, task_id, lease_id)
            result = {"prospect_id": item["prospect_id"], "draft_id": None, "task_id": None,
                      "status": "skipped", "reason": "DRAFT_CONTEXT_CHANGED"}
            if (str(campaign["id"]) == task["payload"]["campaign_id"]
                    and campaign_outreach_hash(campaign) == task["payload"]["campaign_hash"]
                    and canonical_hash(draft_input_snapshot(campaign, prospect))
                    == item["input_hash"]):
                try:
                    self._batch_eligibility(
                        connection, campaign, prospect,
                        exclude_key=UUID(item["child_idempotency_key"]),
                    )
                    row = self._create_draft_in_connection(
                        connection, prospect["id"], CreatorDraftCreate(
                            actor=task["requested_by"],
                            idempotency_key=UUID(item["child_idempotency_key"]),
                        ), reservation_key=UUID(item["child_idempotency_key"]),
                    )
                    if row["input_hash"] != item["input_hash"]:
                        raise CreatorDraftConflictError("Reserved child context changed")
                    result.update(status="queued", reason=None, draft_id=str(row["id"]),
                                  task_id=str(row["task_id"]))
                except CreatorDraftConflictError:
                    result["reason"] = "DRAFT_NO_LONGER_ELIGIBLE"
            self._owned_batch(connection, task_id, lease_id)
            self._append_audit(
                connection, correlation_id=task["correlation_id"], task_id=task_id,
                actor_type="worker", actor_id="creator-draft-batcher", tool_name=KIND,
                action=ITEM_RECORDED, risk_level="medium", approval_status="not_required",
                execution_status=result["status"],
                input_metadata={"prospect_id": item["prospect_id"]}, result_metadata=result,
            )
            return result

    def execute_batch(self, task, interrupt=None):
        task_id, lease_id = UUID(str(task["id"])), UUID(str(task["lease_id"]))

        def checkpoint():
            if interrupt is not None and interrupt.is_set():
                raise TaskInterruptedError("Creator draft preparation was interrupted")
            return self.batch_context(task_id, lease_id)

        issued = checkpoint()
        items = []
        for item in batch_items(issued["payload"]):
            checkpoint()
            items.append(self._queue_reserved_child(task_id, lease_id, item))
        checkpoint()
        return {"handler": KIND, "campaign_id": issued["payload"]["campaign_id"],
                "items": items, "queued_count": sum(item["status"] == "queued" for item in items),
                "skipped_count": sum(item["status"] == "skipped" for item in items),
                "limits": dict(LIMITS),
                "caveat": "Only draft tasks were queued. Review each complete message before "
                          "exact preparation and approval. Cancelling this batch stops remaining "
                          "issuance; already queued drafts require their own cancellation."}
