from __future__ import annotations

from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.application_browser import canonical_hash
from app.creator_contact_history import merge_contact_history
from app.creator_draft_store import CreatorDraftStore
from app.creator_intelligence import CHANNEL_ID, public_youtube_identity
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
    prospect_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=MAX_CREATORS)

    @model_validator(mode="after")
    def explicit_selection(self):
        if self.prospect_ids is not None:
            if len(set(self.prospect_ids)) != len(self.prospect_ids):
                raise ValueError("Explicit creator IDs must be unique")
            if "limit" not in self.model_fields_set:
                self.limit = len(self.prospect_ids)
            elif self.limit != len(self.prospect_ids):
                raise ValueError("Explicit creator IDs must match the requested limit")
        return self


def research_identity(prospect):
    """Known public identity aliases and addresses; none grants contact authority."""
    channels = set()
    if prospect.get("platform") == "youtube":
        for value in (prospect.get("external_id"),
                      (prospect.get("intelligence") or {}).get("source_channel_id")):
            if isinstance(value, str) and CHANNEL_ID.fullmatch(value):
                channels.add(value)
        try:
            identity = public_youtube_identity(prospect.get("profile_url"))
        except (TypeError, ValueError):
            identity = {}
        if identity.get("id"):
            channels.add(identity["id"])
    profile = str(prospect.get("profile_url") or "").strip().rstrip("/").casefold()
    candidates = (prospect.get("intelligence") or {}).get("contact_candidates") or []
    emails = {value.strip().casefold() for value in [
        prospect.get("contact_email"),
        *(candidate.get("email") for candidate in candidates if isinstance(candidate, dict)),
    ] if isinstance(value, str) and value.strip()}
    profiles = {profile} if profile else set()
    if profile.startswith("https://www.youtube.com/"):
        profiles.add(profile.replace("https://www.youtube.com/", "https://youtube.com/", 1))
    elif profile.startswith("https://youtube.com/"):
        profiles.add(profile.replace("https://youtube.com/", "https://www.youtube.com/", 1))
    profiles.update(f"https://www.youtube.com/channel/{channel}".casefold()
                    for channel in channels)
    profiles.update(f"https://youtube.com/channel/{channel}".casefold() for channel in channels)
    keys = ({("channel", channel) for channel in channels}
            | {("profile", value) for value in profiles}
            | {("email", email) for email in emails})
    if prospect.get("platform") and prospect.get("external_id"):
        keys.add(("creator", prospect["platform"], prospect["external_id"]))
    return channels, profiles, emails, keys


class CreatorPilotStore(MarketingStore):
    @staticmethod
    def _explicit_pool_reason(prospect):
        if (prospect.get("platform") != "youtube"
                or prospect.get("status") not in {"discovered", "qualified"}
                or prospect.get("suppressed_at") is not None
                or "Minecraft" not in (prospect.get("intelligence") or {}).get("topics", [])):
            return "Explicit creators require uncontacted, unsuppressed YouTube Minecraft evidence"
        return None

    @staticmethod
    def _matching_creators(connection, prospect):
        channels, profiles, emails, _ = research_identity(prospect)
        return connection.execute(
            "SELECT p.* FROM marketing_prospects p WHERE p.id=%s "
            "OR (p.platform=%s AND p.external_id=%s) "
            "OR (p.platform='youtube' AND (p.external_id=ANY(%s) "
            "OR p.intelligence->>'source_channel_id'=ANY(%s))) "
            "OR lower(rtrim(p.profile_url,'/'))=ANY(%s) "
            "OR lower(p.contact_email)=ANY(%s) "
            "OR EXISTS (SELECT 1 FROM jsonb_array_elements(CASE "
            "WHEN jsonb_typeof(p.intelligence->'contact_candidates')='array' "
            "THEN p.intelligence->'contact_candidates' ELSE '[]'::jsonb END) candidate "
            "WHERE lower(candidate->>'email')=ANY(%s))",
            (prospect["id"], prospect["platform"], prospect.get("external_id"),
             sorted(channels), sorted(channels), sorted(profiles),
             sorted(emails), sorted(emails)),
        ).fetchall()

    def _explicit_ineligibility(self, connection, prospect, *, exclude_task_id=None):
        return self._explicit_group_ineligibility(
            connection, [prospect], exclude_task_id=exclude_task_id,
        )

    def _explicit_group_ineligibility(self, connection, prospects, *, exclude_task_id=None):
        matches = []
        for prospect in prospects:
            reason = self._explicit_pool_reason(prospect)
            if reason:
                return reason
            matches.extend(self._matching_creators(connection, prospect))
        locked_keys = self._lock_explicit_identities(connection, [*prospects, *matches])
        current_matches = [self._matching_creators(connection, prospect) for prospect in prospects]
        # A sender may have committed while the shared identity locks were awaited.
        # Never extend the held union with a newly discovered lower-sorting key.
        current_keys = self._explicit_sender_keys([
            *prospects, *(alias for group in current_matches for alias in group),
        ])
        if not current_keys <= locked_keys:
            return "Creator identity changed while reserving research; review and retry"
        for prospect, aliases in zip(prospects, current_matches, strict=True):
            reason = self._explicit_conflict(
                connection, prospect, aliases, exclude_task_id=exclude_task_id,
            )
            if reason:
                return reason
        return None

    def _explicit_conflict(self, connection, prospect, matches, *, exclude_task_id=None):
        _, _, emails, _ = research_identity(prospect)
        known_emails = set(emails)
        for alias in matches:
            if alias.get("suppressed_at") is not None or alias.get("status") in {
                "suppressed", "bounced",
            }:
                return "Explicit creator or known business address is suppressed"
            known_emails.update(research_identity(alias)[2])
        if any(contact_is_suppressed(connection, email) for email in sorted(known_emails)):
            return "Explicit creator or known business address is suppressed"
        identities = [row["id"] for row in matches]
        if connection.execute(
            "SELECT 1 FROM marketing_outreach_messages m "
            "JOIN external_actions a ON a.id=m.action_id "
            "WHERE m.prospect_id=ANY(%s) OR lower(a.private_context->>'recipient')=ANY(%s) "
            "LIMIT 1", (identities, sorted(emails)),
        ).fetchone():
            return "Explicit creator or business address already has an outreach conversation"
        if any(self._discovery_evidence_protected(connection, identity) for identity in identities):
            return "Explicit creator or business address has protected draft evidence"
        reservations = CreatorDraftStore._draft_reservations(connection)
        if set(identities) & {value[0] for value in reservations.values()}:
            return "Explicit creator or business address has a draft reservation"
        active = connection.execute(
            "SELECT t.id,t.payload,a.input_metadata->>'payload_hash' AS payload_hash "
            "FROM agent_tasks t JOIN audit_events a ON a.task_id=t.id "
            "WHERE t.kind=%s AND t.status IN ('queued','running','pending_approval') "
            "AND a.action='creator.pilot.created' AND (%s::uuid IS NULL OR t.id<>%s)",
            (KIND, exclude_task_id, exclude_task_id),
        ).fetchall()
        for row in active:
            payload = row["payload"]
            reserved = payload.get("prospect_ids") if isinstance(payload, dict) else None
            if (isinstance(reserved, list) and 1 <= len(reserved) <= MAX_CREATORS
                    and all(isinstance(identity, str) for identity in reserved)
                    and row["payload_hash"] == canonical_hash(payload)
                    and set(map(str, identities)) & set(reserved)):
                return "Explicit creator already has an active research reservation"
        return None

    @staticmethod
    def _explicit_sender_keys(prospects):
        keys = set()
        for prospect in prospects:
            channels, profiles, emails, _ = research_identity(prospect)
            keys.update(f"creator-email:{email}" for email in emails)
            keys.update(f"creator-profile:{profile}" for profile in profiles)
            keys.update(f"creator-platform:youtube:{channel}" for channel in channels)
            if prospect.get("platform") and prospect.get("external_id"):
                keys.add(f"creator-platform:{prospect['platform']}:{prospect['external_id']}")
        return keys

    @classmethod
    def _lock_explicit_identities(cls, connection, prospects):
        # Share the sender's namespace; one sorted union is acquired per transaction.
        keys = cls._explicit_sender_keys(prospects)
        for key in sorted(keys):
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))
        return keys

    def _explicit_candidates(self, connection, campaign_id, identities):
        rows = connection.execute(
            "SELECT * FROM marketing_prospects WHERE id=ANY(%s) ORDER BY id FOR UPDATE",
            (identities,),
        ).fetchall()
        by_id = {row["id"]: row for row in rows}
        occupied = set()
        candidates = []
        for identity in identities:
            prospect = by_id.get(identity)
            if prospect is None or prospect["campaign_id"] != campaign_id:
                raise MarketingOutreachError(
                    "An explicit creator is missing or outside this campaign"
                )
            keys = research_identity(prospect)[3]
            if keys & occupied:
                raise MarketingOutreachError(
                    "Explicit creators share a creator or business identity"
                )
            occupied.update(keys)
            candidates.append(prospect)
        reason = self._explicit_group_ineligibility(connection, candidates)
        if reason:
            raise MarketingOutreachError(reason)
        return candidates

    @staticmethod
    def _issued(connection, task):
        return connection.execute(
            "SELECT 1 FROM audit_events WHERE task_id=%s AND action='creator.pilot.created' "
            "AND input_metadata->>'payload_hash'=%s",
            (task["id"], canonical_hash(task["payload"])),
        ).fetchone() is not None

    @staticmethod
    def _recent_reservations(connection, campaign_id, campaign_hash):
        rows = connection.execute(
            "SELECT t.payload,a.input_metadata->>'payload_hash' AS payload_hash, "
            "a.occurred_at FROM agent_tasks t JOIN audit_events a ON a.task_id=t.id "
            "WHERE t.kind=%s AND t.payload->>'campaign_id'=%s "
            "AND a.action='creator.pilot.created' "
            "AND a.occurred_at > now()-interval '24 hours'",
            (KIND, str(campaign_id)),
        ).fetchall()
        # Each real reservation consumes at least one of the shared thirty daily
        # slots. Generic caller tasks and mutated payloads cannot influence rank.
        attempts = {}
        for row in rows:
            payload = row["payload"]
            if (not isinstance(payload, dict)
                    or row["payload_hash"] != canonical_hash(payload)
                    or payload.get("campaign_hash") != campaign_hash):
                continue
            identities, profiles = payload.get("prospect_ids"), payload.get("profile_urls")
            if (not isinstance(identities, list) or not 1 <= len(identities) <= MAX_CREATORS
                    or not isinstance(profiles, dict)):
                continue
            for identity in identities:
                profile = profiles.get(identity) if isinstance(identity, str) else None
                if not isinstance(profile, str):
                    continue
                key = identity, profile
                attempts[key] = max(row["occurred_at"], attempts.get(key, row["occurred_at"]))
        return [
            {"prospect_id": identity, "profile_url": profile, "attempted_at": date.isoformat()}
            for (identity, profile), date in attempts.items()
        ]

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
                        or existing["payload"].get("requested_prospect_ids") != (
                            [str(identity) for identity in request.prospect_ids]
                            if request.prospect_ids is not None else None
                        )
                        or not self._issued(connection, existing)):
                    raise MarketingOutreachError("Idempotency key belongs to another request")
                return existing
            if request.prospect_ids is not None:
                CreatorDraftStore._draft_budget_lock(connection)
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
            campaign_hash = canonical_hash(campaign_snapshot(campaign))
            if request.prospect_ids is not None:
                candidates = self._explicit_candidates(
                    connection, campaign_id, request.prospect_ids,
                )
            else:
                candidates = self._automatic_candidates(connection, campaign_id, campaign_hash,
                                                        request.limit)
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
                "campaign_hash": campaign_hash,
                "prospect_ids": [str(row["id"]) for row in candidates],
                "profile_urls": {str(row["id"]): row["profile_url"] for row in candidates},
            }
            if request.prospect_ids is not None:
                payload["requested_prospect_ids"] = list(map(str, request.prospect_ids))
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

    def _automatic_candidates(self, connection, campaign_id, campaign_hash, limit):
        reservations = self._recent_reservations(connection, campaign_id, campaign_hash)
        rows = connection.execute(
                "SELECT p.*,h.attempted_at AS _last_pilot_at FROM marketing_prospects p "
                "LEFT JOIN jsonb_to_recordset(%s::jsonb) AS h "
                "(prospect_id text,profile_url text,attempted_at timestamptz) "
                "ON h.prospect_id=p.id::text AND h.profile_url=p.profile_url "
                "WHERE campaign_id=%s "
                "AND platform='youtube' AND status IN ('discovered','qualified') "
                "AND suppressed_at IS NULL AND p.intelligence @> %s "
                "AND NOT EXISTS (SELECT 1 FROM creator_contact_suppressions s "
                "WHERE s.email=lower(p.contact_email)) "
                "AND NOT EXISTS (SELECT 1 FROM marketing_outreach_messages m "
                "WHERE m.prospect_id=p.id) "
                "ORDER BY h.attempted_at ASC NULLS FIRST, "
                "CASE WHEN jsonb_typeof(p.intelligence->'contact_candidates')='array' "
                "THEN jsonb_array_length(p.intelligence->'contact_candidates')>0 "
                "ELSE false END DESC, p.relevance_score DESC,p.id LIMIT 500",
                (Jsonb(reservations), campaign_id, Jsonb({"topics": ["Minecraft"]})),
        ).fetchall()
        # Existing intelligence narrows the pool; fresh API metadata determines final rank.
        candidates = [
                row for row in rows
                if "Minecraft" in (row.get("intelligence") or {}).get("topics", [])
                and not contact_is_suppressed(connection, row.get("contact_email"))
        ]
        candidates.sort(key=lambda row: (
                row["_last_pilot_at"] is not None,
                row["_last_pilot_at"].timestamp() if row["_last_pilot_at"] else 0,
                -int(bool((row.get("intelligence") or {}).get("contact_candidates"))),
                -row["relevance_score"], str(row["id"]),
        ))
        candidates = candidates[:limit]
        if not candidates:
            raise MarketingOutreachError(
                "No uncontacted Minecraft candidates; run creator discovery first"
            )
        return candidates

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

    def _context(self, connection, task_id, lease_id, prospect_id=None, *, research=None):
        task = self._owned_task(connection, task_id, lease_id)
        payload = task["payload"]
        if payload.get("requested_prospect_ids") is not None:
            CreatorDraftStore._draft_budget_lock(connection)
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
            if payload.get("requested_prospect_ids") is not None:
                checked = [prospect]
                if research is not None:
                    checked.append({**prospect, **research})
                reason = self._explicit_group_ineligibility(
                    connection, checked, exclude_task_id=task_id,
                )
                if reason:
                    raise InvalidTaskStateError(reason)
        # Campaign/prospect lock waits may outlive the lease.
        self._owned_task(connection, task_id, lease_id)
        return task, campaign, prospect

    def pilot_context(self, task_id, lease_id, prospect_id=None):
        with self.connect() as connection:
            return self._context(connection, task_id, lease_id, prospect_id)

    def save_pilot_research(self, task_id, lease_id, prospect_id, research):
        with self.connect() as connection:
            _, campaign, prospect = self._context(
                connection, task_id, lease_id, prospect_id, research=research,
            )
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
