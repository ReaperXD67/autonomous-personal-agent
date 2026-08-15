from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.career_models import CareerProfileCreate, CareerProfileUpdate, OpportunityStateUpdate
from app.models import TaskCreate
from app.policy import RiskLevel
from app.store import Database


class CareerProfileNotFoundError(LookupError):
    pass


class OpportunityNotFoundError(LookupError):
    pass


class CareerStore(Database):
    @staticmethod
    def _with_resume_metadata(row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        resume_text = result.pop("resume_text", "") or ""
        result["resume_present"] = bool(resume_text.strip())
        result["resume_characters"] = len(resume_text)
        return result

    def create_profile(self, request: CareerProfileCreate) -> dict[str, Any]:
        correlation_id = uuid4()
        with self.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO career_profiles (
                    name, candidate_name, desired_titles, skills, required_keywords,
                    excluded_keywords, locations, remote_only, employment_types,
                    max_age_hours, min_score, schedule_minutes, source_config,
                    resume_text, active, requested_by, next_scan_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, now()
                )
                RETURNING *
                """,
                (
                    request.name,
                    request.candidate_name,
                    request.desired_titles,
                    request.skills,
                    request.required_keywords,
                    request.excluded_keywords,
                    request.locations,
                    request.remote_only,
                    request.employment_types,
                    request.max_age_hours,
                    request.min_score,
                    request.schedule_minutes,
                    Jsonb(request.source_config.model_dump()),
                    request.resume_text,
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
                tool_name="career.profile",
                action="career.profile_created",
                risk_level="medium",
                approval_status="not_required",
                execution_status="succeeded",
                input_metadata={
                    "profile_id": str(row["id"]),
                    "resume_present": bool(request.resume_text.strip()),
                    "source_types": sorted(
                        key for key, value in request.source_config.model_dump().items() if value
                    ),
                },
            )
            connection.commit()
        return self._with_resume_metadata(row)

    def list_profiles(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM career_profiles ORDER BY active DESC, created_at DESC"
            ).fetchall()
        return [self._with_resume_metadata(row) for row in rows]

    def get_profile(self, profile_id: UUID, *, include_resume: bool = False) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM career_profiles WHERE id = %s", (profile_id,)
            ).fetchone()
        if row is None:
            raise CareerProfileNotFoundError(str(profile_id))
        return row if include_resume else self._with_resume_metadata(row)

    def update_profile(
        self, profile_id: UUID, request: CareerProfileUpdate
    ) -> dict[str, Any]:
        correlation_id = uuid4()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM career_profiles WHERE id = %s FOR UPDATE", (profile_id,)
            ).fetchone()
            if existing is None:
                raise CareerProfileNotFoundError(str(profile_id))
            resume_text = (
                existing["resume_text"] if request.resume_text is None else request.resume_text
            )
            next_scan_at = (
                datetime.now(UTC)
                if request.active and not existing["active"]
                else existing["next_scan_at"]
            )
            row = connection.execute(
                """
                UPDATE career_profiles
                SET name = %s, candidate_name = %s, desired_titles = %s, skills = %s,
                    required_keywords = %s, excluded_keywords = %s, locations = %s,
                    remote_only = %s, employment_types = %s, max_age_hours = %s,
                    min_score = %s, schedule_minutes = %s, source_config = %s,
                    resume_text = %s, active = %s, next_scan_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    request.name,
                    request.candidate_name,
                    request.desired_titles,
                    request.skills,
                    request.required_keywords,
                    request.excluded_keywords,
                    request.locations,
                    request.remote_only,
                    request.employment_types,
                    request.max_age_hours,
                    request.min_score,
                    request.schedule_minutes,
                    Jsonb(request.source_config.model_dump()),
                    resume_text,
                    request.active,
                    next_scan_at,
                    profile_id,
                ),
            ).fetchone()
            self._append_audit(
                connection,
                correlation_id=correlation_id,
                task_id=None,
                actor_type="user",
                actor_id=request.actor,
                tool_name="career.profile",
                action="career.profile_updated",
                risk_level="medium",
                approval_status="not_required",
                execution_status="succeeded",
                input_metadata={
                    "profile_id": str(profile_id),
                    "active": request.active,
                    "resume_replaced": request.resume_text is not None,
                },
            )
            connection.commit()
        return self._with_resume_metadata(row)

    def claim_due_profiles(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM career_profiles
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
                    UPDATE career_profiles
                    SET next_scan_at = now() + make_interval(mins => schedule_minutes)
                    WHERE id = %s
                    """,
                    (row["id"],),
                )
                item = dict(row)
                item["scheduled_for"] = scheduled_for
                claimed.append(item)
            connection.commit()
        return claimed

    def defer_profile(self, profile_id: UUID, minutes: int = 5) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE career_profiles
                SET next_scan_at = now() + make_interval(mins => %s)
                WHERE id = %s
                """,
                (minutes, profile_id),
            )
            connection.commit()

    def create_scheduled_search(self, profile: dict[str, Any]) -> dict[str, Any]:
        scheduled_for = profile["scheduled_for"].isoformat()
        return self.create_task(
            TaskCreate(
                title=f"Scan fresh jobs for {profile['name']}",
                kind="career.search",
                payload={"profile_id": str(profile["id"]), "trigger": "schedule"},
                risk_level=RiskLevel.LOW,
                requested_by="scheduler:career",
                idempotency_key=f"career-scan:{profile['id']}:{scheduled_for}",
            )
        )

    def save_opportunities(
        self, profile_id: UUID, opportunities: list[dict[str, Any]]
    ) -> dict[str, int]:
        inserted = 0
        updated = 0
        with self.connect() as connection:
            for opportunity in opportunities:
                existing = connection.execute(
                    """
                    SELECT id FROM job_opportunities
                    WHERE profile_id = %s AND source = %s AND source_key = %s
                    """,
                    (profile_id, opportunity["source"], opportunity["source_key"]),
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO job_opportunities (
                        profile_id, source, source_key, company, title, location,
                        description, remote, employment_type, source_url, apply_url,
                        published_at, score, score_reasons
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (profile_id, source, source_key) DO UPDATE
                    SET company = EXCLUDED.company,
                        title = EXCLUDED.title,
                        location = EXCLUDED.location,
                        description = EXCLUDED.description,
                        remote = EXCLUDED.remote,
                        employment_type = EXCLUDED.employment_type,
                        source_url = EXCLUDED.source_url,
                        apply_url = EXCLUDED.apply_url,
                        published_at = EXCLUDED.published_at,
                        score = EXCLUDED.score,
                        score_reasons = EXCLUDED.score_reasons,
                        last_seen_at = now()
                    """,
                    (
                        profile_id,
                        opportunity["source"],
                        opportunity["source_key"],
                        opportunity["company"],
                        opportunity["title"],
                        opportunity["location"],
                        opportunity["description"],
                        opportunity["remote"],
                        opportunity.get("employment_type"),
                        opportunity["source_url"],
                        opportunity["apply_url"],
                        opportunity["published_at"],
                        opportunity["score"],
                        Jsonb(opportunity["score_reasons"]),
                    ),
                )
                if existing is None:
                    inserted += 1
                else:
                    updated += 1
            connection.execute(
                "UPDATE career_profiles SET last_scan_at = now() WHERE id = %s",
                (profile_id,),
            )
            connection.commit()
        return {"new": inserted, "updated": updated}

    def list_opportunities(
        self,
        *,
        profile_id: UUID | None,
        opportunity_status: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT o.*, d.content AS latest_draft
                FROM job_opportunities o
                LEFT JOIN LATERAL (
                    SELECT content FROM job_application_drafts
                    WHERE opportunity_id = o.id
                    ORDER BY created_at DESC LIMIT 1
                ) d ON true
                WHERE (%s::uuid IS NULL OR o.profile_id = %s)
                  AND (%s::text IS NULL OR o.status = %s)
                ORDER BY
                    CASE o.status WHEN 'new' THEN 0 WHEN 'shortlisted' THEN 1 ELSE 2 END,
                    o.score DESC, o.published_at DESC
                LIMIT %s
                """,
                (profile_id, profile_id, opportunity_status, opportunity_status, limit),
            ).fetchall()

    def get_opportunity(self, opportunity_id: UUID) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT o.*, d.content AS latest_draft
                FROM job_opportunities o
                LEFT JOIN LATERAL (
                    SELECT content FROM job_application_drafts
                    WHERE opportunity_id = o.id
                    ORDER BY created_at DESC LIMIT 1
                ) d ON true
                WHERE o.id = %s
                """,
                (opportunity_id,),
            ).fetchone()
        if row is None:
            raise OpportunityNotFoundError(str(opportunity_id))
        return row

    def update_opportunity_state(
        self, opportunity_id: UUID, request: OpportunityStateUpdate
    ) -> dict[str, Any]:
        correlation_id = uuid4()
        with self.connect() as connection:
            row = connection.execute(
                """
                UPDATE job_opportunities
                SET status = %s,
                    applied_at = CASE WHEN %s = 'applied' THEN now() ELSE NULL END
                WHERE id = %s
                RETURNING *
                """,
                (request.status, request.status, opportunity_id),
            ).fetchone()
            if row is None:
                raise OpportunityNotFoundError(str(opportunity_id))
            self._append_audit(
                connection,
                correlation_id=correlation_id,
                task_id=None,
                actor_type="user",
                actor_id=request.actor,
                tool_name="career.opportunity",
                action=f"career.opportunity_{request.status}",
                risk_level="high" if request.status == "applied" else "medium",
                approval_status=(
                    "manual_external_action"
                    if request.status == "applied"
                    else "not_required"
                ),
                execution_status="recorded",
                input_metadata={
                    "opportunity_id": str(opportunity_id),
                    "source": row["source"],
                },
            )
            connection.commit()
        result = dict(row)
        result["latest_draft"] = None
        return result

    def get_draft_context(self, opportunity_id: UUID, profile_id: UUID) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    p.candidate_name, p.resume_text, p.skills, p.desired_titles,
                    o.id AS opportunity_id, o.profile_id, o.company, o.title,
                    o.location, o.description, o.score_reasons
                FROM job_opportunities o
                JOIN career_profiles p ON p.id = o.profile_id
                WHERE o.id = %s AND p.id = %s
                """,
                (opportunity_id, profile_id),
            ).fetchone()
        if row is None:
            raise OpportunityNotFoundError(str(opportunity_id))
        if not row["resume_text"].strip():
            raise ValueError("A resume is required before generating an application draft")
        return row

    def save_application_draft(
        self,
        *,
        opportunity_id: UUID,
        profile_id: UUID,
        task_id: UUID,
        model: str,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO job_application_drafts (
                    opportunity_id, profile_id, task_id, model, content
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (task_id) DO UPDATE SET content = EXCLUDED.content
                RETURNING *
                """,
                (opportunity_id, profile_id, task_id, model, Jsonb(content)),
            ).fetchone()
            connection.commit()
        return row

    def recent_profile_scan_count(self, profile_id: UUID, hours: int = 24) -> int:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT count(*)::int AS count FROM agent_tasks
                WHERE kind = 'career.search'
                  AND payload->>'profile_id' = %s
                  AND created_at >= %s
                """,
                (str(profile_id), cutoff),
            ).fetchone()
        return row["count"]
