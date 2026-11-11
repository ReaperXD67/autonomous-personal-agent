"""An owner may park one reply for a finite set of exact AI initial packets."""

from __future__ import annotations

from datetime import UTC, timedelta
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.application_browser import canonical_hash
from app.creator_pilot_store import CreatorPilotStore, research_identity
from app.marketing import contact_is_suppressed, contact_outreach_snapshot
from app.marketing_store import MarketingCampaignNotFoundError, MarketingOutreachError

DEFERRAL_CONFIRMATION = "defer this reply for reviewed new initials"
DEFERRAL_VERSION = "creator-reply-deferral-v1"
BOUND_REASON = "The bound owner reply deferral is absent, expired, changed or outside this initial"


def _scope_hash(row):
    return canonical_hash({
        "version": DEFERRAL_VERSION,
        **{key: str(row[key]) for key in ("id", "campaign_id", "reply_id", "idempotency_key")},
        **{key: row[key] for key in (
            "body_digest", "authorized_by", "reason", "duration_hours", "campaign_hash",
            "outreach_epoch", "source_identity", "prospect_identity_hashes",
            "source_mailbox_key", "source_label_name",
        )},
        "prospect_ids": [str(value) for value in row["prospect_ids"]],
        "created_at": row["created_at"].astimezone(UTC).isoformat(),
        "expires_at": row["expires_at"].astimezone(UTC).isoformat(),
    })


def _identity_keys(connection, prospect, *, sender=None):
    aliases = CreatorPilotStore._matching_creators(connection, prospect)
    keys = set()
    for item in [prospect, *aliases]:
        keys.update(research_identity(item)[3])
    if sender:
        keys.add(("email", sender.strip().casefold()))
    return sorted([list(key) for key in keys]), aliases


def _target_binding(connection, prospect):
    keys, aliases = _identity_keys(connection, prospect)
    binding = canonical_hash({"identity": keys, "contact": contact_outreach_snapshot(prospect)})
    return binding, aliases


def _new_target_reason(connection, prospect, source_identity, *, action_id=None):
    from app.creator_draft_store import CreatorDraftStore

    if (prospect["status"] not in {"discovered", "qualified"}
            or prospect.get("suppressed_at") is not None
            or not prospect.get("contact_authorized_at")
            or not prospect.get("contact_email")
            or contact_is_suppressed(connection, prospect["contact_email"])):
        return "Deferral targets require new, authorized, unsuppressed creator contacts"
    keys, aliases = _identity_keys(connection, prospect)
    emails = sorted({key[1] for key in keys if key[0] == "email"})
    if any(contact_is_suppressed(connection, email) for email in emails):
        return "Deferral targets must not reuse a suppressed business address"
    if {tuple(key) for key in keys} & {tuple(key) for key in source_identity}:
        return "The deferred conversation and its identity/address aliases remain excluded"
    alias_ids = sorted({prospect["id"], *(item["id"] for item in aliases)}, key=str)
    if any(item.get("suppressed_at") is not None or item["status"] not in {
        "discovered", "qualified",
    } for item in aliases):
        return "Deferral targets must not reuse another conversation or suppressed identity"
    if connection.execute(
        "SELECT 1 FROM marketing_outreach_messages m "
        "JOIN external_actions a ON a.id=m.action_id "
        "WHERE (m.prospect_id=ANY(%s) OR lower(a.private_context->>'recipient')=ANY(%s)) "
        "AND (%s::uuid IS NULL OR m.action_id<>%s) LIMIT 1",
        (alias_ids, emails, action_id, action_id),
    ).fetchone():
        return "Deferral targets must be new creators without prior or pending outreach"
    reservations = CreatorDraftStore._draft_reservations(connection)
    if set(alias_ids) & {value[0] for value in reservations.values()}:
        return "Deferral targets must not reuse an existing batch reservation"
    return None


def _source_reply(connection, campaign_id, reply_id=None):
    from app.creator_automation import classify_creator_reply
    from app.creator_automation_store import complete_reply_body

    pending = connection.execute(
        "SELECT * FROM creator_reply_messages WHERE campaign_id=%s AND needs_review "
        "ORDER BY id LIMIT 2", (campaign_id,),
    ).fetchall()
    if len(pending) != 1 or (reply_id is not None and pending[0]["id"] != reply_id):
        return None
    reply = pending[0]
    if (not complete_reply_body(reply) or not reply["prospect_id"]
            or classify_creator_reply({"snippet": reply["body_text"]}) == "do_not_contact"
            or contact_is_suppressed(connection, reply["sender"])):
        return None
    prospect = connection.execute(
        "SELECT * FROM marketing_prospects WHERE id=%s AND campaign_id=%s",
        (reply["prospect_id"], campaign_id),
    ).fetchone()
    if (not prospect or str(prospect.get("contact_email") or "").casefold()
            != reply["sender"].casefold()):
        return None
    if not connection.execute(
        "SELECT 1 FROM marketing_outreach_messages m JOIN external_actions a ON a.id=m.action_id "
        "WHERE m.prospect_id=%s AND a.status='succeeded' AND a.executed_at<=%s "
        "AND lower(a.private_context->>'recipient')=lower(%s) LIMIT 1",
        (prospect["id"], reply["received_at"], reply["sender"]),
    ).fetchone():
        return None
    identity, _ = _identity_keys(connection, prospect, sender=reply["sender"])
    return reply, identity


def _scope_current(connection, row, campaign, source):
    from app.creator_automation import automation_campaign_hash, creator_mailbox_is_fresh

    now = connection.execute("SELECT clock_timestamp() AS value").fetchone()["value"]
    if (row["revoked_at"] is not None or row["expires_at"] <= now
            or row["created_at"] > now
            or row["expires_at"] > row["created_at"] + timedelta(hours=24)
            or campaign.get("outreach_paused")
            or row["outreach_epoch"] != campaign.get("outreach_epoch", 0)
            or row["campaign_hash"] != automation_campaign_hash(campaign)
            or row["scope_hash"] != _scope_hash(row)
            or not source or source[0]["body_digest"] != row["body_digest"]
            or source[0]["id"] != row["reply_id"] or source[1] != row["source_identity"]
            or source[0]["body_mailbox_key"] != row["source_mailbox_key"]
            or source[0]["body_label_name"] != row["source_label_name"]
            or not creator_mailbox_is_fresh(connection, campaign["id"])):
        return False
    sync = connection.execute(
        "SELECT mailbox_key,label_name FROM creator_gmail_sync_state WHERE campaign_id=%s",
        (campaign["id"],),
    ).fetchone()
    if (not sync or sync["mailbox_key"] != row["source_mailbox_key"]
            or sync["label_name"] != row["source_label_name"]):
        return False
    return bool(connection.execute(
        "SELECT 1 FROM audit_events WHERE tool_name='marketing.reply_deferral' "
        "AND action='creator.reply.deferral.created' AND actor_type='user' AND actor_id=%s "
        "AND risk_level='high' AND approval_status='scoped_authorization' "
        "AND execution_status='succeeded' "
        "AND input_metadata->>'deferral_id'=%s AND input_metadata->>'scope_hash'=%s LIMIT 1",
        (row["authorized_by"], str(row["id"]), row["scope_hash"]),
    ).fetchone())


def bind_reply_deferral(connection, campaign, prospect):
    """Called only for a newly prepared AI initial, under campaign/prospect locks."""
    rows = connection.execute(
        "SELECT * FROM creator_reply_deferrals WHERE campaign_id=%s "
        "AND %s=ANY(prospect_ids) AND revoked_at IS NULL ORDER BY created_at DESC LIMIT 1",
        (campaign["id"], prospect["id"]),
    ).fetchall()
    if not rows:
        return None
    row = rows[0]
    source = _source_reply(connection, campaign["id"], row["reply_id"])
    if (not _scope_current(connection, row, campaign, source)
            or _new_target_reason(connection, prospect, row["source_identity"])):
        raise MarketingOutreachError(BOUND_REASON)
    binding, _ = _target_binding(connection, prospect)
    if row["prospect_identity_hashes"].get(str(prospect["id"])) != binding:
        raise MarketingOutreachError(BOUND_REASON)
    return row


def prepare_reply_deferral(connection, campaign, prospect, stage, ai_draft):
    # An issued exception narrows preparation; it never makes templates, handoffs
    # or another target eligible merely because one reply was parked.
    pending = connection.execute(
        "SELECT 1 FROM creator_reply_messages WHERE campaign_id=%s AND needs_review LIMIT 1",
        (campaign["id"],),
    ).fetchone()
    if not pending:
        return None
    if stage != "initial" or ai_draft is None:
        raise MarketingOutreachError(BOUND_REASON)
    row = bind_reply_deferral(connection, campaign, prospect)
    if row is None:
        raise MarketingOutreachError(BOUND_REASON)
    return row


def _exact_ai_initial(connection, action, prospect, campaign):
    from app.creator_draft_store import CreatorDraftConflictError, check_draft_context

    private = action["private_context"]
    public = action.get("public_context") or {}
    marketing = private.get("marketing") or {}
    public_marketing = public.get("marketing") or {}
    if (action["action_type"] != "communications.email_send" or "creator_automation" in private
            or marketing.get("stage") != "initial"
            or marketing.get("variant") != "ai_reviewed_initial"
            or public_marketing.get("variant") != "ai_reviewed_initial"
            or any(public_marketing.get(key) != marketing.get(key)
                   for key in ("campaign_id", "prospect_id", "stage"))):
        return False
    try:
        draft_id = UUID(str(public_marketing.get("draft_id")))
    except (TypeError, ValueError):
        return False
    draft = connection.execute(
        "SELECT d.*,t.kind AS _task_kind,t.status AS _task_status,t.payload AS _task_payload "
        "FROM creator_email_drafts d JOIN agent_tasks t ON t.id=d.task_id "
        "WHERE d.id=%s AND d.action_id=%s", (draft_id, action["id"]),
    ).fetchone()
    now = connection.execute("SELECT clock_timestamp() AS value").fetchone()["value"]
    if (not draft or draft["campaign_id"] != campaign["id"]
            or draft["prospect_id"] != prospect["id"] or draft["status"] != "prepared"
            or draft["source"] not in {"openrouter", "ollama"} or not draft["selected_model"]
            or draft["source"] != public_marketing.get("draft_source")
            or draft["draft_digest"] != marketing.get("ai_draft_digest")
            or draft["_task_kind"] != "marketing.creator_draft"
            or draft["_task_status"] != "succeeded"
            or draft["_task_payload"] != {"draft_id": str(draft_id)}
            or draft["expires_at"] <= now
            or draft["model_context"].get("drafting_contract") != "creator-grounded-plan-v2"
            or any(draft[key] != private.get(key) or draft[key] != public.get(key)
                   for key in ("subject", "body"))):
        return False
    try:
        check_draft_context(draft, campaign, prospect)
    except (CreatorDraftConflictError, KeyError, TypeError, ValueError):
        return False
    return bool(connection.execute(
        "SELECT 1 FROM inference_invocations WHERE task_id=%s "
        "AND purpose='marketing.creator_draft' AND status='succeeded' "
        "AND provider=%s AND selected_model=%s LIMIT 1",
        (draft["task_id"], draft["source"], draft["selected_model"]),
    ).fetchone())


def deferred_pending_reply_allowed(connection, campaign_id, action):
    """No reply-row lock: existing reply review owns reply before its prospect."""
    marketing = action["private_context"].get("marketing") or {}
    try:
        bound_id = UUID(str(marketing.get("reply_deferral_id")))
        prospect_id = UUID(str(marketing.get("prospect_id")))
    except (TypeError, ValueError):
        return False
    row = connection.execute(
        "SELECT * FROM creator_reply_deferrals WHERE id=%s AND campaign_id=%s",
        (bound_id, campaign_id),
    ).fetchone()
    if (not row or marketing.get("reply_deferral_hash") != row["scope_hash"]
            or prospect_id not in row["prospect_ids"]):
        return False
    campaign = connection.execute(
        "SELECT * FROM marketing_campaigns WHERE id=%s", (campaign_id,),
    ).fetchone()
    prospect = connection.execute(
        "SELECT * FROM marketing_prospects WHERE id=%s AND campaign_id=%s",
        (prospect_id, campaign_id),
    ).fetchone()
    source = _source_reply(connection, campaign_id, row["reply_id"])
    if (not campaign or not prospect or not _scope_current(connection, row, campaign, source)
            or _new_target_reason(connection, prospect, row["source_identity"],
                                  action_id=action["id"])):
        return False
    binding, _ = _target_binding(connection, prospect)
    return (row["prospect_identity_hashes"].get(str(prospect_id)) == binding
            and _exact_ai_initial(connection, action, prospect, campaign))


def approval_reply_deferral_reason(connection, action, scheduled_for=None):
    marketing = action["private_context"].get("marketing")
    if isinstance(marketing, dict) and marketing.get("reply_deferral_id"):
        if not deferred_pending_reply_allowed(connection, marketing.get("campaign_id"), action):
            return BOUND_REASON
        if scheduled_for is not None:
            row = connection.execute(
                "SELECT expires_at FROM creator_reply_deferrals WHERE id=%s AND campaign_id=%s",
                (marketing["reply_deferral_id"], marketing.get("campaign_id")),
            ).fetchone()
            if not row or scheduled_for >= row["expires_at"]:
                return "The reserved email slot falls outside the bound owner reply deferral"
    elif isinstance(marketing, dict) and connection.execute(
        "SELECT 1 FROM creator_reply_messages WHERE campaign_id=%s AND needs_review LIMIT 1",
        (marketing.get("campaign_id"),),
    ).fetchone():
        return BOUND_REASON
    return None


class CreatorReplyDeferralMixin:
    def _audit_reply_deferral(self, connection, row, actor, action):
        self._append_audit(
            connection, correlation_id=uuid4(), task_id=None,
            actor_type="user", actor_id=actor, tool_name="marketing.reply_deferral",
            action=action, risk_level="high", approval_status="scoped_authorization",
            execution_status="succeeded", input_metadata={
                "campaign_id": str(row["campaign_id"]), "reply_id": str(row["reply_id"]),
                "deferral_id": str(row["id"]), "scope_hash": row["scope_hash"],
                "prospect_count": len(row["prospect_ids"]),
                "expires_at": row["expires_at"].astimezone(UTC).isoformat(),
            },
        )

    @staticmethod
    def _deferral_view(connection, row):
        now = connection.execute("SELECT clock_timestamp() AS value").fetchone()["value"]
        return {**row, "status": "revoked" if row["revoked_at"] else
                "expired" if row["expires_at"] <= now else "issued",
                "sending_authority": False}

    def create_reply_deferral(self, campaign_id, reply_id, request):
        from app.creator_automation import automation_campaign_hash, creator_mailbox_is_fresh

        with self.connect() as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended('creator-automation',0))",
            )
            campaign = connection.execute(
                "SELECT * FROM marketing_campaigns WHERE id=%s FOR UPDATE", (campaign_id,),
            ).fetchone()
            if not campaign:
                raise MarketingCampaignNotFoundError(str(campaign_id))
            prior = connection.execute(
                "SELECT * FROM creator_reply_deferrals WHERE idempotency_key=%s",
                (request.idempotency_key,),
            ).fetchone()
            if prior:
                if (prior["campaign_id"] != campaign_id or prior["reply_id"] != reply_id
                        or prior["authorized_by"] != request.actor
                        or prior["body_digest"] != request.body_digest
                        or prior["prospect_ids"] != request.prospect_ids
                        or prior["reason"] != request.reason
                        or prior["duration_hours"] != request.expires_in_hours):
                    raise MarketingOutreachError("Deferral idempotency belongs to another scope")
                return self._deferral_view(connection, prior)
            source = _source_reply(connection, campaign_id, reply_id)
            if not source or source[0]["body_digest"] != request.body_digest:
                raise MarketingOutreachError(
                    "Deferral requires the sole complete pending reply and its current digest",
                )
            if not creator_mailbox_is_fresh(connection, campaign_id):
                raise MarketingOutreachError(
                    "Creator mailbox monitoring needs a recent complete sync",
                )
            sync = connection.execute(
                "SELECT mailbox_key,label_name FROM creator_gmail_sync_state WHERE campaign_id=%s",
                (campaign_id,),
            ).fetchone()
            if (not sync or sync["mailbox_key"] != source[0]["body_mailbox_key"]
                    or sync["label_name"] != source[0]["body_label_name"]):
                raise MarketingOutreachError(
                    "Deferred reply must match the current mailbox and label",
                )
            if connection.execute(
                "SELECT 1 FROM creator_reply_deferrals WHERE campaign_id=%s "
                "AND reply_id=%s AND revoked_at IS NULL LIMIT 1", (campaign_id, reply_id),
            ).fetchone():
                raise MarketingOutreachError(
                    "Revoke the existing deferral before issuing a new scope",
                )
            prospects = connection.execute(
                "SELECT * FROM marketing_prospects WHERE campaign_id=%s AND id=ANY(%s) "
                "ORDER BY id FOR SHARE", (campaign_id, request.prospect_ids),
            ).fetchall()
            if len(prospects) != len(request.prospect_ids):
                raise MarketingOutreachError("Deferral targets must belong to the bound campaign")
            bindings, occupied = {}, set()
            for prospect in prospects:
                if reason := _new_target_reason(connection, prospect, source[1]):
                    raise MarketingOutreachError(reason)
                keys = {tuple(key) for key in _identity_keys(connection, prospect)[0]}
                if keys & occupied:
                    raise MarketingOutreachError(
                        "Deferral targets share a creator/business identity",
                    )
                occupied.update(keys)
                bindings[str(prospect["id"])] = _target_binding(connection, prospect)[0]
            now = connection.execute("SELECT clock_timestamp() AS value").fetchone()["value"]
            row = {
                "id": uuid4(), "campaign_id": campaign_id, "reply_id": reply_id,
                "body_digest": request.body_digest, "prospect_ids": request.prospect_ids,
                "authorized_by": request.actor, "reason": request.reason,
                "idempotency_key": request.idempotency_key,
                "duration_hours": request.expires_in_hours,
                "created_at": now, "expires_at": now + timedelta(hours=request.expires_in_hours),
                "campaign_hash": automation_campaign_hash(campaign),
                "outreach_epoch": campaign.get("outreach_epoch", 0),
                "source_identity": source[1], "prospect_identity_hashes": bindings,
                "source_mailbox_key": source[0]["body_mailbox_key"],
                "source_label_name": source[0]["body_label_name"],
            }
            row["scope_hash"] = _scope_hash(row)
            row = connection.execute(
                "INSERT INTO creator_reply_deferrals (id,campaign_id,reply_id,body_digest,"
                "prospect_ids,authorized_by,reason,idempotency_key,duration_hours,created_at,"
                "expires_at,campaign_hash,outreach_epoch,source_identity,prospect_identity_hashes,"
                "source_mailbox_key,source_label_name,scope_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                (row["id"], row["campaign_id"], row["reply_id"], row["body_digest"],
                 row["prospect_ids"], row["authorized_by"], row["reason"], row["idempotency_key"],
                 row["duration_hours"], row["created_at"], row["expires_at"], row["campaign_hash"],
                 row["outreach_epoch"], Jsonb(row["source_identity"]),
                 Jsonb(row["prospect_identity_hashes"]), row["source_mailbox_key"],
                 row["source_label_name"], row["scope_hash"]),
            ).fetchone()
            self._audit_reply_deferral(
                connection, row, request.actor, "creator.reply.deferral.created",
            )
            connection.commit()
            return self._deferral_view(connection, row)

    def list_reply_deferrals(self, campaign_id, reply_id):
        self.get_campaign(campaign_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM creator_reply_deferrals WHERE campaign_id=%s AND reply_id=%s "
                "ORDER BY created_at DESC LIMIT 30", (campaign_id, reply_id),
            ).fetchall()
            return [self._deferral_view(connection, row) for row in rows]

    def reply_deferral_count(self, campaign_id):
        with self.connect() as connection:
            return connection.execute(
                "SELECT count(*)::int AS n FROM creator_reply_deferrals WHERE campaign_id=%s "
                "AND revoked_at IS NULL AND expires_at>clock_timestamp()", (campaign_id,),
            ).fetchone()["n"]

    def revoke_reply_deferral(self, campaign_id, reply_id, deferral_id, actor):
        with self.connect() as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended('creator-automation',0))",
            )
            campaign = connection.execute(
                "SELECT id FROM marketing_campaigns WHERE id=%s FOR UPDATE", (campaign_id,),
            ).fetchone()
            if not campaign:
                raise MarketingCampaignNotFoundError(str(campaign_id))
            row = connection.execute(
                "UPDATE creator_reply_deferrals SET "
                "revoked_at=COALESCE(revoked_at,clock_timestamp()),"
                "revoked_by=COALESCE(revoked_by,%s) WHERE id=%s AND campaign_id=%s AND reply_id=%s "
                "RETURNING *", (actor, deferral_id, campaign_id, reply_id),
            ).fetchone()
            if not row:
                raise MarketingOutreachError("Reply deferral was not found in this campaign")
            self._audit_reply_deferral(connection, row, actor, "creator.reply.deferral.revoked")
            connection.commit()
            return self._deferral_view(connection, row)
