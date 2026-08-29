from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.action_store import ActionStore
from app.marketing import (
    INITIAL_VARIANTS,
    campaign_suggestions,
    choose_initial_variant,
    compose_initial_email,
    compose_paid_offer_email,
    compose_question_reply,
    percentage,
)
from app.marketing_models import (
    MarketingCampaignCreate,
    MarketingCampaignUpdate,
    MarketingEmailPlanCreate,
    MarketingOutcomeCreate,
    MarketingProspectCreate,
    MarketingProspectUpdate,
)
from app.models import TaskCreate
from app.policy import RiskLevel


class MarketingCampaignNotFoundError(LookupError):
    pass


class MarketingProspectNotFoundError(LookupError):
    pass


class MarketingOutreachError(RuntimeError):
    pass


class MarketingStore(ActionStore):
    def create_campaign(self, request: MarketingCampaignCreate) -> dict[str, Any]:
        correlation_id = uuid4()
        with self.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO marketing_campaigns (
                    name, product_name, product_url, privacy_url, product_summary,
                    target_audience, viewer_offer, creator_offer,
                    paid_offer_enabled, paid_offer_details, sender_name,
                    discovery_queries, relevance_language, region_code,
                    min_subscribers, max_subscribers, max_video_age_days,
                    results_per_query, schedule_hours, adaptive_mode, active,
                    next_scan_at, created_by
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    CASE WHEN %s THEN now() ELSE now() + interval '24 hours' END,
                    %s
                )
                RETURNING *
                """,
                (
                    request.name,
                    request.product_name,
                    request.product_url,
                    request.privacy_url,
                    request.product_summary,
                    request.target_audience,
                    request.viewer_offer,
                    request.creator_offer,
                    request.paid_offer_enabled,
                    request.paid_offer_details,
                    request.sender_name,
                    request.discovery_queries,
                    request.relevance_language,
                    request.region_code,
                    request.min_subscribers,
                    request.max_subscribers,
                    request.max_video_age_days,
                    request.results_per_query,
                    request.schedule_hours,
                    request.adaptive_mode,
                    request.active,
                    request.active,
                    request.requested_by,
                ),
            ).fetchone()
            self._append_audit(
                connection,
                correlation_id=correlation_id,
                task_id=None,
                actor_type="user",
                actor_id=request.requested_by,
                tool_name="marketing.campaign",
                action="marketing.campaign_created",
                risk_level="medium",
                approval_status="not_required",
                execution_status="succeeded",
                input_metadata={
                    "campaign_id": str(row["id"]),
                    "query_count": len(request.discovery_queries),
                    "active": request.active,
                    "adaptive_mode": request.adaptive_mode,
                },
            )
            connection.commit()
        return row

    def list_campaigns(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM marketing_campaigns ORDER BY active DESC, created_at DESC"
            ).fetchall()

    def get_campaign(self, campaign_id: UUID) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM marketing_campaigns WHERE id = %s", (campaign_id,)
            ).fetchone()
        if row is None:
            raise MarketingCampaignNotFoundError(str(campaign_id))
        return row

    def update_campaign(
        self, campaign_id: UUID, request: MarketingCampaignUpdate
    ) -> dict[str, Any]:
        correlation_id = uuid4()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM marketing_campaigns WHERE id = %s FOR UPDATE", (campaign_id,)
            ).fetchone()
            if existing is None:
                raise MarketingCampaignNotFoundError(str(campaign_id))
            next_scan_at = (
                datetime.now(UTC)
                if request.active and not existing["active"]
                else existing["next_scan_at"]
            )
            row = connection.execute(
                """
                UPDATE marketing_campaigns
                SET name = %s, product_name = %s, product_url = %s, privacy_url = %s,
                    product_summary = %s, target_audience = %s, viewer_offer = %s,
                    creator_offer = %s, paid_offer_enabled = %s, paid_offer_details = %s,
                    sender_name = %s, discovery_queries = %s, relevance_language = %s,
                    region_code = %s, min_subscribers = %s, max_subscribers = %s,
                    max_video_age_days = %s, results_per_query = %s, schedule_hours = %s,
                    adaptive_mode = %s, active = %s, next_scan_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    request.name,
                    request.product_name,
                    request.product_url,
                    request.privacy_url,
                    request.product_summary,
                    request.target_audience,
                    request.viewer_offer,
                    request.creator_offer,
                    request.paid_offer_enabled,
                    request.paid_offer_details,
                    request.sender_name,
                    request.discovery_queries,
                    request.relevance_language,
                    request.region_code,
                    request.min_subscribers,
                    request.max_subscribers,
                    request.max_video_age_days,
                    request.results_per_query,
                    request.schedule_hours,
                    request.adaptive_mode,
                    request.active,
                    next_scan_at,
                    campaign_id,
                ),
            ).fetchone()
            self._append_audit(
                connection,
                correlation_id=correlation_id,
                task_id=None,
                actor_type="user",
                actor_id=request.actor,
                tool_name="marketing.campaign",
                action="marketing.campaign_updated",
                risk_level="medium",
                approval_status="not_required",
                execution_status="succeeded",
                input_metadata={
                    "campaign_id": str(campaign_id),
                    "active": request.active,
                    "adaptive_mode": request.adaptive_mode,
                },
            )
            connection.commit()
        return row

    def claim_due_campaigns(self, limit: int = 5) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM marketing_campaigns
                WHERE active = true AND next_scan_at <= now()
                ORDER BY next_scan_at
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            claimed: list[dict[str, Any]] = []
            for row in rows:
                scheduled_for = row["next_scan_at"]
                connection.execute(
                    """
                    UPDATE marketing_campaigns
                    SET next_scan_at = now() + make_interval(hours => schedule_hours)
                    WHERE id = %s
                    """,
                    (row["id"],),
                )
                item = dict(row)
                item["scheduled_for"] = scheduled_for
                claimed.append(item)
            connection.commit()
        return claimed

    def defer_campaign(self, campaign_id: UUID, minutes: int = 15) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE marketing_campaigns
                SET next_scan_at = now() + make_interval(mins => %s)
                WHERE id = %s
                """,
                (minutes, campaign_id),
            )
            connection.commit()

    def create_scheduled_discovery(self, campaign: dict[str, Any]) -> dict[str, Any]:
        scheduled_for = campaign["scheduled_for"].isoformat()
        return self.create_task(
            TaskCreate(
                title=f"Discover Minecraft creators for {campaign['name']}",
                kind="marketing.creator_discovery",
                payload={"campaign_id": str(campaign["id"]), "trigger": "schedule"},
                risk_level=RiskLevel.LOW,
                requested_by="scheduler:marketing",
                idempotency_key=f"marketing-discovery:{campaign['id']}:{scheduled_for}",
            )
        )

    def recent_marketing_scan_count(self, hours: int = 24) -> int:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT count(*)::int AS count FROM agent_tasks
                WHERE kind = 'marketing.creator_discovery'
                  AND created_at >= now() - make_interval(hours => %s)
                """,
                (hours,),
            ).fetchone()
        return row["count"]

    def save_discovered_prospects(
        self, campaign_id: UUID, prospects: list[dict[str, Any]]
    ) -> dict[str, int]:
        inserted = 0
        updated = 0
        with self.connect() as connection:
            campaign = connection.execute(
                "SELECT id FROM marketing_campaigns WHERE id = %s", (campaign_id,)
            ).fetchone()
            if campaign is None:
                raise MarketingCampaignNotFoundError(str(campaign_id))
            for prospect in prospects:
                existing = connection.execute(
                    """
                    SELECT id FROM marketing_prospects
                    WHERE campaign_id = %s AND platform = %s AND external_id = %s
                    """,
                    (campaign_id, prospect["platform"], prospect["external_id"]),
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO marketing_prospects (
                        campaign_id, platform, external_id, display_name, profile_url,
                        audience_size, latest_content_title, latest_content_url,
                        latest_content_published_at, discovery_query, relevance_score,
                        relevance_reasons
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (campaign_id, platform, external_id) DO UPDATE SET
                        display_name = EXCLUDED.display_name,
                        profile_url = EXCLUDED.profile_url,
                        audience_size = EXCLUDED.audience_size,
                        latest_content_title = EXCLUDED.latest_content_title,
                        latest_content_url = EXCLUDED.latest_content_url,
                        latest_content_published_at = EXCLUDED.latest_content_published_at,
                        discovery_query = EXCLUDED.discovery_query,
                        relevance_score = EXCLUDED.relevance_score,
                        relevance_reasons = EXCLUDED.relevance_reasons,
                        last_seen_at = now()
                    """,
                    (
                        campaign_id,
                        prospect["platform"],
                        prospect["external_id"],
                        prospect["display_name"],
                        prospect["profile_url"],
                        prospect["audience_size"],
                        prospect["latest_content_title"],
                        prospect["latest_content_url"],
                        prospect["latest_content_published_at"],
                        prospect["discovery_query"],
                        prospect["relevance_score"],
                        Jsonb(prospect["relevance_reasons"]),
                    ),
                )
                if existing is None:
                    inserted += 1
                else:
                    updated += 1
            connection.execute(
                "UPDATE marketing_campaigns SET last_scan_at = now() WHERE id = %s",
                (campaign_id,),
            )
            connection.commit()
        return {"new": inserted, "updated": updated}

    def create_prospect(self, request: MarketingProspectCreate) -> dict[str, Any]:
        correlation_id = uuid4()
        external_id = request.external_id or hashlib.sha256(
            f"{request.platform}\0{request.profile_url}".encode()
        ).hexdigest()
        authorized_at = datetime.now(UTC) if request.authorize_contact else None
        status = "qualified" if request.authorize_contact else "discovered"
        with self.connect() as connection:
            campaign = connection.execute(
                "SELECT id FROM marketing_campaigns WHERE id = %s", (request.campaign_id,)
            ).fetchone()
            if campaign is None:
                raise MarketingCampaignNotFoundError(str(request.campaign_id))
            row = connection.execute(
                """
                INSERT INTO marketing_prospects (
                    campaign_id, platform, external_id, display_name, profile_url,
                    audience_size, latest_content_title, latest_content_url,
                    relevance_score, relevance_reasons, contact_email,
                    contact_source_url, contact_basis_note, contact_authorized_at,
                    contact_authorized_by, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 50, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (campaign_id, platform, external_id) DO NOTHING
                RETURNING *
                """,
                (
                    request.campaign_id,
                    request.platform,
                    external_id,
                    request.display_name,
                    request.profile_url,
                    request.audience_size,
                    request.latest_content_title,
                    request.latest_content_url,
                    Jsonb(["manually added and awaiting operator qualification"]),
                    request.contact_email,
                    request.contact_source_url,
                    request.contact_basis_note,
                    authorized_at,
                    request.requested_by if request.authorize_contact else None,
                    status,
                ),
            ).fetchone()
            if row is None:
                raise MarketingOutreachError("This prospect already exists in the campaign")
            self._append_audit(
                connection,
                correlation_id=correlation_id,
                task_id=None,
                actor_type="user",
                actor_id=request.requested_by,
                tool_name="marketing.prospect",
                action="marketing.prospect_created",
                risk_level="medium",
                approval_status="not_required",
                execution_status="succeeded",
                input_metadata={
                    "campaign_id": str(request.campaign_id),
                    "prospect_id": str(row["id"]),
                    "platform": request.platform,
                    "contact_authorized": request.authorize_contact,
                },
            )
            connection.commit()
        return self.get_prospect(row["id"])

    def update_prospect(
        self, prospect_id: UUID, request: MarketingProspectUpdate
    ) -> dict[str, Any]:
        correlation_id = uuid4()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM marketing_prospects WHERE id = %s FOR UPDATE", (prospect_id,)
            ).fetchone()
            if existing is None:
                raise MarketingProspectNotFoundError(str(prospect_id))
            if existing["suppressed_at"] is not None and request.authorize_contact:
                raise MarketingOutreachError("A suppressed prospect cannot be re-authorized")
            authorized_at = datetime.now(UTC) if request.authorize_contact else None
            status = (
                existing["status"]
                if existing["status"] not in {"discovered", "qualified"}
                else ("qualified" if request.authorize_contact else "discovered")
            )
            row = connection.execute(
                """
                UPDATE marketing_prospects
                SET display_name = %s, profile_url = %s, audience_size = %s,
                    contact_email = %s, contact_source_url = %s,
                    contact_basis_note = %s, contact_authorized_at = %s,
                    contact_authorized_by = %s, status = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    request.display_name,
                    request.profile_url,
                    request.audience_size,
                    request.contact_email,
                    request.contact_source_url,
                    request.contact_basis_note,
                    authorized_at,
                    request.actor if request.authorize_contact else None,
                    status,
                    prospect_id,
                ),
            ).fetchone()
            self._append_audit(
                connection,
                correlation_id=correlation_id,
                task_id=None,
                actor_type="user",
                actor_id=request.actor,
                tool_name="marketing.prospect",
                action="marketing.prospect_updated",
                risk_level="medium",
                approval_status="not_required",
                execution_status="succeeded",
                input_metadata={
                    "prospect_id": str(prospect_id),
                    "contact_authorized": request.authorize_contact,
                    "contact_source_host": (
                        urlparse(request.contact_source_url).hostname
                        if request.contact_source_url
                        else None
                    ),
                },
            )
            connection.commit()
        return self.get_prospect(row["id"])

    @staticmethod
    def _prospect_select() -> str:
        return """
            SELECT p.*,
                   (
                       SELECT jsonb_build_object(
                           'id', m.id, 'stage', m.stage, 'variant', m.variant,
                           'selection_reason', m.selection_reason,
                           'action_id', a.id, 'task_id', a.task_id,
                           'action_status', a.status, 'created_at', m.created_at
                       )
                       FROM marketing_outreach_messages m
                       JOIN external_actions a ON a.id = m.action_id
                       WHERE m.prospect_id = p.id
                       ORDER BY m.created_at DESC LIMIT 1
                   ) AS latest_message,
                   (
                       SELECT to_jsonb(o.*)
                       FROM marketing_outcomes o
                       WHERE o.prospect_id = p.id
                       ORDER BY o.created_at DESC LIMIT 1
                   ) AS latest_outcome,
                   (
                       SELECT count(*)::int
                       FROM marketing_outreach_messages sent_message
                       JOIN external_actions sent_action
                         ON sent_action.id = sent_message.action_id
                       WHERE sent_message.prospect_id = p.id
                         AND sent_action.status = 'succeeded'
                   ) AS sent_message_count
            FROM marketing_prospects p
        """

    def list_prospects(
        self,
        *,
        campaign_id: UUID | None,
        prospect_status: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return connection.execute(
                self._prospect_select()
                + """
                WHERE (%s::uuid IS NULL OR p.campaign_id = %s)
                  AND (%s::text IS NULL OR p.status = %s)
                ORDER BY
                    CASE WHEN p.suppressed_at IS NULL THEN 0 ELSE 1 END,
                    p.relevance_score DESC, p.first_seen_at DESC
                LIMIT %s
                """,
                (campaign_id, campaign_id, prospect_status, prospect_status, limit),
            ).fetchall()

    def get_prospect(self, prospect_id: UUID) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                self._prospect_select() + " WHERE p.id = %s", (prospect_id,)
            ).fetchone()
        if row is None:
            raise MarketingProspectNotFoundError(str(prospect_id))
        return row

    def _variant_metrics_in_connection(
        self, connection: Any, campaign_id: UUID
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT m.variant,
                   count(*) FILTER (WHERE a.status = 'succeeded')::int AS sent,
                   count(DISTINCT m.prospect_id) FILTER (
                       WHERE a.status = 'succeeded' AND EXISTS (
                           SELECT 1 FROM marketing_outcomes o
                           WHERE o.prospect_id = m.prospect_id
                             AND o.classification IN (
                                 'question', 'declined_unpaid', 'interested',
                                 'converted', 'do_not_contact', 'promotion_published'
                             )
                       )
                   )::int AS replies,
                   count(DISTINCT m.prospect_id) FILTER (
                       WHERE a.status = 'succeeded' AND EXISTS (
                           SELECT 1 FROM marketing_outcomes o
                           WHERE o.prospect_id = m.prospect_id
                             AND o.classification IN (
                                 'interested', 'converted', 'promotion_published'
                             )
                       )
                   )::int AS positive
            FROM marketing_outreach_messages m
            JOIN marketing_prospects p ON p.id = m.prospect_id
            JOIN external_actions a ON a.id = m.action_id
            WHERE p.campaign_id = %s AND m.stage = 'initial'
            GROUP BY m.variant
            """,
            (campaign_id,),
        ).fetchall()
        by_variant = {row["variant"]: dict(row) for row in rows}
        return [
            by_variant.get(name, {"variant": name, "sent": 0, "replies": 0, "positive": 0})
            for name in INITIAL_VARIANTS
        ]

    def plan_outreach_email(
        self,
        prospect_id: UUID,
        request: MarketingEmailPlanCreate,
        *,
        sender: str,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            context = connection.execute(
                """
                SELECT p.*, c.name AS campaign_name, c.product_name, c.product_url,
                       c.privacy_url, c.product_summary, c.target_audience,
                       c.viewer_offer, c.creator_offer, c.paid_offer_enabled,
                       c.paid_offer_details, c.sender_name, c.adaptive_mode
                FROM marketing_prospects p
                JOIN marketing_campaigns c ON c.id = p.campaign_id
                WHERE p.id = %s
                FOR UPDATE OF p
                """,
                (prospect_id,),
            ).fetchone()
            if context is None:
                raise MarketingProspectNotFoundError(str(prospect_id))
            if context["suppressed_at"] is not None or context["status"] in {
                "suppressed",
                "bounced",
            }:
                raise MarketingOutreachError("This contact is suppressed")
            if (
                context["contact_authorized_at"] is None
                or not context["contact_email"]
                or not context["contact_source_url"]
                or not context["contact_basis_note"]
            ):
                raise MarketingOutreachError(
                    "Review and authorize the public business contact before planning email"
                )

            active_stage = connection.execute(
                """
                SELECT a.status FROM marketing_outreach_messages m
                JOIN external_actions a ON a.id = m.action_id
                WHERE m.prospect_id = %s AND m.stage = %s
                  AND a.status IN (
                      'pending_approval', 'queued', 'executing',
                      'succeeded', 'ambiguous'
                  )
                ORDER BY m.created_at DESC LIMIT 1
                """,
                (prospect_id, request.stage),
            ).fetchone()
            if active_stage is not None and request.stage in {"initial", "paid_offer"}:
                raise MarketingOutreachError(
                    f"A {request.stage.replace('_', ' ')} email is already {active_stage['status']}"
                )

            campaign = dict(context)
            campaign["name"] = context["campaign_name"]
            prospect = dict(context)
            if request.stage == "initial":
                if context["status"] not in {"discovered", "qualified"}:
                    raise MarketingOutreachError(
                        "Initial outreach is not valid in this reply state"
                    )
                variants = self._variant_metrics_in_connection(
                    connection, context["campaign_id"]
                )
                variant, selection_reason = choose_initial_variant(
                    prospect_id,
                    variants,
                    adaptive_mode=context["adaptive_mode"],
                )
                subject, body = compose_initial_email(campaign, prospect, variant)
            elif request.stage == "question_reply":
                if context["status"] != "question":
                    raise MarketingOutreachError(
                        "Manual answers are available only after a question is recorded"
                    )
                question_state = connection.execute(
                    """
                    SELECT
                        (
                            SELECT count(*)::int FROM marketing_outcomes
                            WHERE prospect_id = %s AND classification = 'question'
                        ) AS recorded_questions,
                        (
                            SELECT count(*)::int
                            FROM marketing_outreach_messages m
                            JOIN external_actions a ON a.id = m.action_id
                            WHERE m.prospect_id = %s AND m.stage = 'question_reply'
                              AND a.status IN (
                                  'pending_approval', 'queued', 'executing',
                                  'succeeded', 'ambiguous'
                              )
                        ) AS answered_questions
                    """,
                    (prospect_id, prospect_id),
                ).fetchone()
                if question_state["answered_questions"] >= question_state[
                    "recorded_questions"
                ]:
                    raise MarketingOutreachError(
                        "Record a new creator question before preparing another answer"
                    )
                variant = "manual_answer"
                selection_reason = "Operator wrote the answer to the creator's specific question"
                assert request.subject is not None and request.body is not None
                subject, body = compose_question_reply(
                    campaign, prospect, request.subject, request.body
                )
            else:
                if context["status"] != "declined_unpaid":
                    raise MarketingOutreachError(
                        "A paid offer is allowed only after an unpaid-only decline"
                    )
                variant = "paid_final"
                selection_reason = "One final paid option after an unpaid-only decline"
                subject, body = compose_paid_offer_email(campaign, prospect)

            public_context = {
                "sender": sender,
                "recipient": context["contact_email"],
                "subject": subject,
                "body": body,
                "opportunity_id": None,
                "marketing": {
                    "campaign_id": str(context["campaign_id"]),
                    "prospect_id": str(prospect_id),
                    "stage": request.stage,
                    "variant": variant,
                    "selection_reason": selection_reason,
                },
            }
            action = self._create_external_action(
                action_type="communications.email_send",
                opportunity_id=None,
                target_display=context["contact_email"],
                public_context=public_context,
                private_context=public_context,
                actor=request.actor,
                approval_window_minutes=request.approval_window_minutes,
                connection=connection,
            )
            if action["status"] != "pending_approval":
                raise MarketingOutreachError(
                    "An identical outreach action already ended as "
                    f"{action['status']}; review the evidence or revise the manual answer"
                )
            message = connection.execute(
                """
                INSERT INTO marketing_outreach_messages (
                    prospect_id, action_id, stage, variant, selection_reason
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (action_id) DO UPDATE SET action_id = EXCLUDED.action_id
                RETURNING *
                """,
                (prospect_id, action["id"], request.stage, variant, selection_reason),
            ).fetchone()
            task = connection.execute(
                "SELECT correlation_id FROM agent_tasks WHERE id = %s",
                (action["task_id"],),
            ).fetchone()
            self._append_audit(
                connection,
                correlation_id=task["correlation_id"],
                task_id=action["task_id"],
                actor_type="user",
                actor_id=request.actor,
                tool_name="marketing.outreach",
                action="marketing.outreach_prepared",
                risk_level="high",
                approval_status="required",
                execution_status="pending_approval",
                input_metadata={
                    "campaign_id": str(context["campaign_id"]),
                    "prospect_id": str(prospect_id),
                    "message_id": str(message["id"]),
                    "stage": request.stage,
                    "variant": variant,
                },
            )
            connection.commit()
        return action

    def record_outcome(
        self, prospect_id: UUID, request: MarketingOutcomeCreate
    ) -> dict[str, Any]:
        with self.connect() as connection:
            prospect = connection.execute(
                "SELECT * FROM marketing_prospects WHERE id = %s FOR UPDATE", (prospect_id,)
            ).fetchone()
            if prospect is None:
                raise MarketingProspectNotFoundError(str(prospect_id))
            if prospect["suppressed_at"] is not None:
                raise MarketingOutreachError("This prospect is already suppressed")
            message_state = connection.execute(
                """
                SELECT
                    count(*)::int AS planned,
                    count(*) FILTER (WHERE a.status = 'succeeded')::int AS sent
                FROM marketing_outreach_messages m
                JOIN external_actions a ON a.id = m.action_id
                WHERE m.prospect_id = %s
                """,
                (prospect_id,),
            ).fetchone()
            if message_state["planned"] == 0:
                raise MarketingOutreachError("Record an outreach message before its outcome")
            if (
                request.classification not in {"bounced", "do_not_contact"}
                and message_state["sent"] == 0
            ):
                raise MarketingOutreachError(
                    "A reply or promotion result requires a successfully sent message"
                )

            status_map = {
                "question": "question",
                "declined_unpaid": "declined_unpaid",
                "interested": "interested",
                "converted": "converted",
                "promotion_published": "converted",
                "do_not_contact": "suppressed",
                "bounced": "bounced",
            }
            new_status = status_map[request.classification]
            suppression_reason = None
            if request.classification == "do_not_contact":
                suppression_reason = "Recipient objected to further outreach"
            elif request.classification == "bounced":
                suppression_reason = "Delivery bounced; address suppressed"
            suppressed_at = datetime.now(UTC) if suppression_reason else None
            connection.execute(
                """
                INSERT INTO marketing_outcomes (
                    prospect_id, classification, note, promotion_url,
                    attributed_views, attributed_clicks, attributed_signups,
                    attributed_server_owners, viewer_points_issued, recorded_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    prospect_id,
                    request.classification,
                    request.note,
                    request.promotion_url,
                    request.attributed_views,
                    request.attributed_clicks,
                    request.attributed_signups,
                    request.attributed_server_owners,
                    request.viewer_points_issued,
                    request.actor,
                ),
            )
            updated = connection.execute(
                """
                UPDATE marketing_prospects
                SET status = %s,
                    suppressed_at = COALESCE(%s, suppressed_at),
                    suppression_reason = COALESCE(%s, suppression_reason),
                    contact_authorized_at = CASE WHEN %s IS NULL
                        THEN contact_authorized_at ELSE NULL END,
                    contact_authorized_by = CASE WHEN %s IS NULL
                        THEN contact_authorized_by ELSE NULL END
                WHERE id = %s
                RETURNING *
                """,
                (
                    new_status,
                    suppressed_at,
                    suppression_reason,
                    suppressed_at,
                    suppressed_at,
                    prospect_id,
                ),
            ).fetchone()
            self._append_audit(
                connection,
                correlation_id=uuid4(),
                task_id=None,
                actor_type="user",
                actor_id=request.actor,
                tool_name="marketing.outcome",
                action="marketing.outcome_recorded",
                risk_level="medium",
                approval_status="not_required",
                execution_status="recorded",
                input_metadata={
                    "campaign_id": str(updated["campaign_id"]),
                    "prospect_id": str(prospect_id),
                    "classification": request.classification,
                    "suppressed": suppressed_at is not None,
                    "attributed_views": request.attributed_views,
                    "attributed_clicks": request.attributed_clicks,
                    "attributed_signups": request.attributed_signups,
                    "attributed_server_owners": request.attributed_server_owners,
                },
            )
            connection.commit()
        return self.get_prospect(prospect_id)

    def campaign_results(self, campaign_id: UUID | None = None) -> list[dict[str, Any]]:
        campaigns = self.list_campaigns()
        if campaign_id is not None:
            campaigns = [item for item in campaigns if item["id"] == campaign_id]
            if not campaigns:
                raise MarketingCampaignNotFoundError(str(campaign_id))
        results: list[dict[str, Any]] = []
        with self.connect() as connection:
            for campaign in campaigns:
                prospect_metrics = connection.execute(
                    """
                    SELECT
                        count(*)::int AS discovered,
                        count(*) FILTER (
                            WHERE contact_authorized_at IS NOT NULL
                        )::int AS contactable,
                        count(*) FILTER (
                            WHERE EXISTS (
                                SELECT 1 FROM marketing_outcomes o
                                WHERE o.prospect_id = marketing_prospects.id
                                  AND o.classification = 'question'
                            )
                        )::int AS questions,
                        count(*) FILTER (
                            WHERE EXISTS (
                                SELECT 1 FROM marketing_outcomes o
                                WHERE o.prospect_id = marketing_prospects.id
                                  AND o.classification = 'declined_unpaid'
                            )
                        )::int AS declined_unpaid,
                        count(*) FILTER (
                            WHERE EXISTS (
                                SELECT 1 FROM marketing_outcomes o
                                WHERE o.prospect_id = marketing_prospects.id
                                  AND o.classification IN (
                                      'interested', 'converted', 'promotion_published'
                                  )
                            )
                        )::int AS positive_replies,
                        count(*) FILTER (
                            WHERE EXISTS (
                                SELECT 1 FROM marketing_outcomes o
                                WHERE o.prospect_id = marketing_prospects.id
                                  AND o.classification IN (
                                      'converted', 'promotion_published'
                                  )
                            )
                        )::int AS converted,
                        count(*) FILTER (
                            WHERE status IN ('suppressed', 'bounced')
                        )::int AS suppressed,
                        count(*) FILTER (
                            WHERE EXISTS (
                                SELECT 1 FROM marketing_outcomes o
                                WHERE o.prospect_id = marketing_prospects.id
                                  AND o.classification IN (
                                      'question', 'declined_unpaid', 'interested',
                                      'converted', 'do_not_contact', 'promotion_published'
                                  )
                            )
                        )::int AS replies
                    FROM marketing_prospects
                    WHERE campaign_id = %s
                    """,
                    (campaign["id"],),
                ).fetchone()
                message_metrics = connection.execute(
                    """
                    SELECT
                        count(*) FILTER (WHERE a.status = 'succeeded')::int AS emails_sent,
                        count(*) FILTER (
                            WHERE a.status = 'succeeded' AND m.stage = 'initial'
                        )::int AS initial_sent,
                        count(*) FILTER (
                            WHERE a.status = 'succeeded' AND m.stage = 'paid_offer'
                        )::int AS paid_offers_sent
                    FROM marketing_outreach_messages m
                    JOIN marketing_prospects p ON p.id = m.prospect_id
                    JOIN external_actions a ON a.id = m.action_id
                    WHERE p.campaign_id = %s
                    """,
                    (campaign["id"],),
                ).fetchone()
                attribution = connection.execute(
                    """
                    SELECT
                        count(*) FILTER (
                            WHERE o.classification = 'promotion_published'
                        )::int AS promotions_published,
                        COALESCE(sum(o.attributed_views), 0)::bigint AS attributed_views,
                        COALESCE(sum(o.attributed_clicks), 0)::bigint AS attributed_clicks,
                        COALESCE(sum(o.attributed_signups), 0)::bigint AS attributed_signups,
                        COALESCE(sum(o.attributed_server_owners), 0)::bigint
                            AS attributed_server_owners,
                        COALESCE(sum(o.viewer_points_issued), 0)::bigint
                            AS viewer_points_issued
                    FROM marketing_outcomes o
                    JOIN marketing_prospects p ON p.id = o.prospect_id
                    WHERE p.campaign_id = %s
                    """,
                    (campaign["id"],),
                ).fetchone()
                metrics = dict(prospect_metrics)
                metrics.update(message_metrics)
                metrics.update(attribution)
                metrics["response_rate_percent"] = percentage(
                    metrics["replies"], metrics["initial_sent"]
                )
                metrics["positive_reply_rate_percent"] = percentage(
                    metrics["positive_replies"], metrics["initial_sent"]
                )
                metrics["conversion_rate_percent"] = percentage(
                    metrics["converted"], metrics["initial_sent"]
                )
                variants = self._variant_metrics_in_connection(connection, campaign["id"])
                for variant in variants:
                    variant["reply_rate_percent"] = percentage(
                        variant["replies"], variant["sent"]
                    )
                    variant["positive_rate_percent"] = percentage(
                        variant["positive"], variant["sent"]
                    )
                results.append(
                    {
                        "campaign_id": campaign["id"],
                        "campaign_name": campaign["name"],
                        "metrics": metrics,
                        "variants": variants,
                        "suggestions": campaign_suggestions(metrics, variants),
                    }
                )
        return results
