from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg import sql
from psycopg.types.json import Jsonb

from app.action_models import ApplicationIdentity, ApplicationPlanCreate, EmailActionCreate
from app.action_store import ActionPreparationError, ActionStore
from app.application_browser import canonical_hash
from app.career_autopilot import (
    allowed_url,
    eligibility_reason,
    hiring_email,
    lock_profile,
    opportunity_hash,
    profile_hash,
    target_key,
)
from app.career_autopilot_models import CareerPlay
from app.career_store import CareerProfileNotFoundError
from app.models import ApprovalDecision, TaskCreate

PREPARATION_PROFILE_LIMIT = 20


def preparation_capacity(run: dict[str, Any], profile_used: int, run_used: int) -> int:
    """Bound preparation independently of irreversible application reservations."""
    return max(0, min(
        PREPARATION_PROFILE_LIMIT - profile_used,
        min(PREPARATION_PROFILE_LIMIT, run["max_applications_per_day"] * 2) - run_used,
    ))


def public_run(run: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in run.items() if key not in {"answers", "profile_hash"}}
    result["preparation_limit_24h"] = PREPARATION_PROFILE_LIMIT
    result["run_preparation_limit_24h"] = min(
        PREPARATION_PROFILE_LIMIT, run["max_applications_per_day"] * 2,
    )
    profile_used = run.get("preparation_used_today", 0)
    run_used = run.get("run_preparation_used_today", 0)
    if profile_used >= PREPARATION_PROFILE_LIMIT:
        reason = "Profile preparation limit reached; earlier attempts leave the 24-hour window"
    elif run_used >= result["run_preparation_limit_24h"]:
        reason = "Run preparation limit reached; review prepared actions and blocked attempts"
    else:
        reason = None
    result["preparation_limit_reason"] = reason
    return result


class CareerAutopilotStore(ActionStore):
    def schedule_mail_sync(self) -> list[dict[str, Any]]:
        scheduled = []
        with self.connect() as connection:
            profiles = connection.execute(
                "SELECT DISTINCT profile_id FROM job_opportunities "
                "WHERE applied_at > now() - interval '180 days' UNION "
                "SELECT profile_id FROM career_autopilot_runs WHERE state = 'running'"
            ).fetchall()
        for profile in profiles:
            with self.connect() as connection:
                lock_profile(connection, profile["profile_id"])
                recent = connection.execute(
                    "SELECT 1 FROM agent_tasks WHERE kind = 'career.gmail_sync' "
                    "AND payload->>'profile_id' = %s AND (status IN ('queued', 'running') "
                    "OR created_at > now() - interval '15 minutes') LIMIT 1",
                    (str(profile["profile_id"]),),
                ).fetchone()
                if recent:
                    continue
                task = self._create_task_record(connection, TaskCreate(
                    title="Track replies to recorded applications", kind="career.gmail_sync",
                    payload={"profile_id": str(profile["profile_id"])},
                    requested_by="scheduler:career-replies",
                    idempotency_key=f"career-replies:{profile['profile_id']}:{uuid4()}",
                ))
                connection.commit()
                scheduled.append({"task_id": task["id"]})
        return scheduled

    def reserve_source_request(self, source: str) -> bool:
        with self.connect() as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"career-source:{source}",),
            )
            recent = connection.execute(
                "SELECT count(*) AS n, max(requested_at) AS latest FROM career_source_requests "
                "WHERE source = %s AND requested_at > now() - interval '24 hours'",
                (source,),
            ).fetchone()
            now = connection.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
            if recent["n"] >= 4 or (
                recent["latest"] and (now - recent["latest"]).total_seconds() < 60
            ):
                return False
            connection.execute("INSERT INTO career_source_requests (source) VALUES (%s)", (source,))
            connection.commit()
            return True

    def _audit_run(self, connection: Any, run: dict[str, Any], action: str, actor: str) -> None:
        self._append_audit(
            connection,
            correlation_id=uuid4(),
            task_id=None,
            actor_type="user",
            actor_id=actor,
            action=action,
            risk_level="high" if run["mode"] == "apply" else "low",
            approval_status="scoped_authorization" if run["mode"] == "apply" else "not_required",
            execution_status=run["state"],
            tool_name="career.autopilot",
            input_metadata={
                "run_id": str(run["id"]),
                "profile_id": str(run["profile_id"]),
                "mode": run["mode"],
                "daily_limit": run["max_applications_per_day"],
                "max_age_hours": run["max_age_hours"],
                "min_score": run["min_score"],
                "allowed_hosts": run["allowed_hosts"],
                "include_cold_email": run["include_cold_email"],
                "expires_at": run["expires_at"].isoformat(),
            },
        )

    def play(self, profile_id: UUID, request: CareerPlay) -> dict[str, Any]:
        with self.connect() as connection:
            lock_profile(connection, profile_id)
            profile = connection.execute(
                "SELECT * FROM career_profiles WHERE id = %s FOR UPDATE", (profile_id,)
            ).fetchone()
            if profile is None:
                raise CareerProfileNotFoundError(str(profile_id))
            if not profile["resume_text"].strip():
                raise ActionPreparationError("Save your resume before starting career preparation")
            if request.mode == "apply":
                try:
                    ApplicationIdentity.model_validate(profile["application_identity"])
                except ValueError as exc:
                    raise ActionPreparationError(
                        "Complete your application identity first"
                    ) from exc
            connection.execute(
                "UPDATE career_autopilot_runs SET state = 'paused', paused_at = now() "
                "WHERE profile_id = %s AND state = 'running'",
                (profile_id,),
            )
            # The reconciler owns preparation; the legacy per-scan preparer stays disabled.
            profile = connection.execute(
                "UPDATE career_profiles SET active = true, auto_prepare = false, "
                "max_age_hours = %s, "
                "min_score = %s, next_scan_at = now() + make_interval(mins => schedule_minutes) "
                "WHERE id = %s RETURNING *",
                (request.max_age_hours, request.min_score, profile_id),
            ).fetchone()
            run = connection.execute(
                """INSERT INTO career_autopilot_runs (
                    profile_id, state, mode, profile_hash, min_score, max_age_hours,
                    max_applications_per_day, allowed_hosts, answers, include_cold_email,
                    authorized_by, expires_at
                ) VALUES (%s, 'running', %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          now() + make_interval(hours => %s)) RETURNING *""",
                (
                    profile_id,
                    request.mode,
                    profile_hash(profile),
                    request.min_score,
                    request.max_age_hours,
                    request.max_applications_per_day,
                    Jsonb(request.allowed_hosts),
                    Jsonb(request.answers),
                    request.include_cold_email,
                    request.actor,
                    request.expires_in_hours,
                ),
            ).fetchone()
            self._create_task_record(
                connection,
                TaskCreate(
                    title="Discover fresh jobs for the career Play run",
                    kind="career.search",
                    payload={"profile_id": str(profile_id), "autopilot_run_id": str(run["id"])},
                    requested_by=request.actor,
                    idempotency_key=f"autopilot-search:{run['id']}",
                ),
            )
            self._audit_run(connection, run, "career.autopilot.started", request.actor)
            connection.commit()
            return public_run(run)

    def pause(self, profile_id: UUID, actor: str) -> dict[str, bool]:
        with self.connect() as connection:
            lock_profile(connection, profile_id)
            rows = connection.execute(
                "UPDATE career_autopilot_runs SET state = 'paused', paused_at = now() "
                "WHERE profile_id = %s AND state = 'running' RETURNING *",
                (profile_id,),
            ).fetchall()
            profile = connection.execute(
                "UPDATE career_profiles SET active = false, auto_prepare = false "
                "WHERE id = %s RETURNING id",
                (profile_id,),
            ).fetchone()
            if profile is None:
                raise CareerProfileNotFoundError(str(profile_id))
            for row in rows:
                self._audit_run(connection, row, "career.autopilot.paused", actor)
            connection.commit()
        return {"paused": True}

    def overview(self, profile_id: UUID | None = None) -> dict[str, Any]:
        with self.connect() as connection:
            runs = connection.execute(
                """SELECT r.*, (SELECT count(*) FROM career_autopilot_actions a
                    WHERE a.profile_id = r.profile_id
                      AND a.created_at > now() - interval '24 hours')
                    AS used_today,
                    (SELECT count(*) FROM career_autopilot_items i
                     JOIN career_autopilot_runs history ON history.id = i.run_id
                     WHERE history.profile_id = r.profile_id
                       AND i.created_at > now() - interval '24 hours') AS preparation_used_today,
                    (SELECT count(*) FROM career_autopilot_items i WHERE i.run_id = r.id
                       AND i.created_at > now() - interval '24 hours')
                       AS run_preparation_used_today
                    FROM career_autopilot_runs r
                    WHERE (%s::uuid IS NULL OR r.profile_id = %s)
                    ORDER BY r.created_at DESC LIMIT 50""",
                (profile_id, profile_id),
            ).fetchall()
            items = connection.execute(
                """SELECT i.run_id, i.opportunity_id, i.created_at,
                    CASE WHEN a.status IN ('queued', 'executing', 'succeeded', 'failed',
                                          'ambiguous', 'cancelled', 'expired') THEN a.status
                         WHEN i.state = 'authorized' THEN COALESCE(a.status, i.state)
                         ELSE i.state END AS state,
                    CASE WHEN a.status = 'succeeded' THEN 'Application submission recorded'
                         WHEN a.status IN ('failed', 'ambiguous', 'cancelled')
                         THEN 'Submission needs review; inspect the exact action result'
                         WHEN a.status = 'expired' THEN 'Exact action expired; prepare new material'
                         ELSE i.reason END AS reason,
                    a.id AS action_id, a.status AS action_status,
                    o.company, o.title FROM career_autopilot_items i
                    JOIN career_autopilot_runs r ON r.id = i.run_id
                    JOIN job_opportunities o ON o.id = i.opportunity_id
                    LEFT JOIN external_actions a ON a.id = i.action_id
                    WHERE (%s::uuid IS NULL OR r.profile_id = %s)
                    ORDER BY i.created_at DESC LIMIT 100""",
                (profile_id, profile_id),
            ).fetchall()
        return {"runs": [public_run(run) for run in runs], "items": items}

    def reconcile(self, *, sender: str = "") -> list[dict[str, Any]]:
        with self.connect() as connection:
            runs = connection.execute(
                "SELECT id FROM career_autopilot_runs "
                "WHERE state = 'running' ORDER BY created_at LIMIT 50"
            ).fetchall()
        for summary in runs:
            try:
                self._reconcile_run(summary["id"], sender=sender)
            except Exception as exc:
                # Avoid persisting provider content, resume fields, addresses, or credentials.
                with self.connect() as connection:
                    connection.execute(
                        "UPDATE career_autopilot_runs SET last_error = %s WHERE id = %s",
                        (f"Reconciliation needs attention: {type(exc).__name__}", summary["id"]),
                    )
                    connection.commit()
        return []

    def _reconcile_run(self, run_id: UUID, *, sender: str) -> None:
        with self.connect() as connection:
            run = connection.execute(
                "SELECT * FROM career_autopilot_runs WHERE id = %s", (run_id,)
            ).fetchone()
            lock_profile(connection, run["profile_id"])
            run = connection.execute(
                "SELECT * FROM career_autopilot_runs WHERE id = %s FOR UPDATE", (run_id,)
            ).fetchone()
            if run["state"] != "running":
                return
            profile = connection.execute(
                "SELECT * FROM career_profiles WHERE id = %s FOR SHARE", (run["profile_id"],)
            ).fetchone()
            now = connection.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
            invalid = profile_hash(profile) != run["profile_hash"] or not profile["active"]
            if run["expires_at"] <= now or invalid:
                state = "paused" if invalid else "expired"
                connection.execute(
                    "UPDATE career_autopilot_runs SET state = %s, paused_at = now(), "
                    "last_error = %s WHERE id = %s",
                    (
                        state,
                        "Profile changed; review and press Play again"
                        if invalid
                        else "Run reached its expiry",
                        run_id,
                    ),
                )
                connection.execute(
                    "UPDATE career_profiles SET active = false, auto_prepare = false WHERE id = %s",
                    (profile["id"],),
                )
                self._audit_run(
                    connection,
                    {**run, "state": state},
                    f"career.autopilot.{state}",
                    "scheduler:career-autopilot",
                )
                connection.commit()
                return
            opportunities = connection.execute(
                """SELECT * FROM job_opportunities WHERE profile_id = %s
                    AND status IN ('new', 'shortlisted') AND published_at_basis = 'published'
                    AND published_at >= now() - make_interval(hours => %s)
                    AND score >= %s ORDER BY score DESC, published_at DESC LIMIT 100""",
                (profile["id"], run["max_age_hours"], run["min_score"]),
            ).fetchall()
            prepared = connection.execute(
                "SELECT count(*) AS profile_used, "
                "count(*) FILTER (WHERE i.run_id = %s) AS run_used "
                "FROM career_autopilot_items i JOIN career_autopilot_runs r "
                "ON r.id = i.run_id WHERE r.profile_id = %s "
                "AND i.created_at > now() - interval '24 hours'",
                (run_id, profile["id"]),
            ).fetchone()
            available = preparation_capacity(run, prepared["profile_used"], prepared["run_used"])
            for opportunity in opportunities:
                reason = eligibility_reason(run, profile, opportunity, now)
                browser = allowed_url(opportunity["apply_url"], run["allowed_hosts"])
                contact = (
                    hiring_email(opportunity["description"]) if run["include_cold_email"] else None
                )
                if reason or (not browser and not contact):
                    continue
                item = connection.execute(
                    "SELECT * FROM career_autopilot_items "
                    "WHERE run_id = %s AND opportunity_id = %s",
                    (run_id, opportunity["id"]),
                ).fetchone()
                if item is None and available > 0:
                    connection.execute(
                        "INSERT INTO career_autopilot_items "
                        "(run_id, opportunity_id, opportunity_hash) "
                        "VALUES (%s, %s, %s)",
                        (run_id, opportunity["id"], opportunity_hash(opportunity)),
                    )
                    kinds = ["career.application_draft"]
                    if browser:
                        kinds.append("career.application_preflight")
                    for kind in kinds:
                        self._create_task_record(
                            connection,
                            TaskCreate(
                                title=f"Prepare {opportunity['company']} application"[:200],
                                kind=kind,
                                payload={
                                    "profile_id": str(profile["id"]),
                                    "opportunity_id": str(opportunity["id"]),
                                    "autopilot_run_id": str(run_id),
                                    "workflow_managed": True,
                                },
                                requested_by="scheduler:career-autopilot",
                                idempotency_key=f"autopilot:{run_id}:{opportunity['id']}:{kind}",
                            ),
                        )
                    available -= 1
            connection.commit()
        # Preparation and network execution happen on existing policy-routed worker queues.
        with self.connect() as connection:
            items = connection.execute(
                "SELECT * FROM career_autopilot_items WHERE run_id = %s "
                "AND state IN ('preparing', 'waiting_budget') ORDER BY created_at LIMIT 10",
                (run_id,),
            ).fetchall()
        for item in items:
            self._advance_item(run_id, item, sender=sender)

    def _advance_item(self, run_id: UUID, item: dict[str, Any], *, sender: str) -> None:
        with self.connect() as connection:
            run = connection.execute(
                "SELECT * FROM career_autopilot_runs WHERE id = %s", (run_id,)
            ).fetchone()
            opportunity = connection.execute(
                "SELECT * FROM job_opportunities WHERE id = %s", (item["opportunity_id"],)
            ).fetchone()
            tasks = connection.execute(
                "SELECT id, kind, status FROM agent_tasks WHERE "
                "payload->>'autopilot_run_id' = %s AND "
                "payload->>'opportunity_id' = %s",
                (str(run_id), str(item["opportunity_id"])),
            ).fetchall()
        if not tasks or any(
            task["status"] in {"queued", "running", "pending_approval"} for task in tasks
        ):
            return
        if any(task["status"] != "succeeded" for task in tasks):
            self._item_state(item, "needs_review", "Preparation failed; inspect the task activity")
            return
        if opportunity_hash(opportunity) != item["opportunity_hash"]:
            self._item_state(item, "needs_review", "Job details changed during preparation")
            return
        try:
            if allowed_url(opportunity["apply_url"], run["allowed_hosts"]):
                action = self.create_application_action(
                    opportunity["id"],
                    ApplicationPlanCreate(
                        actor="scheduler:career-autopilot",
                        answers=run["answers"],
                        approval_window_minutes=1440,
                    ),
                )
            else:
                contact = hiring_email(opportunity["description"])
                context = self._application_context(opportunity["id"])
                if not sender or not contact or not run["include_cold_email"]:
                    raise ActionPreparationError(
                        "Configure SMTP and an explicit published hiring email"
                    )
                body = str((context.get("draft_content") or {}).get("cover_letter") or "").strip()
                if not body:
                    raise ActionPreparationError("A completed cover letter is required")
                identity = context["application_identity"]
                portfolio = identity.get("portfolio_url") or identity.get("github_url")
                if portfolio:
                    body += f"\n\nPortfolio: {portfolio}"
                body += f"\n\nRole: {opportunity['source_url']}"
                reference = f"HERMES-{opportunity['id'].hex}"
                body += f"\nApplication reference: {reference}"
                email = EmailActionCreate(
                    recipient=contact, subject=" ".join(
                        f"{reference} | {opportunity['company']}: {opportunity['title']}".split()
                    )[:240], body=body, actor="scheduler:career-autopilot",
                    opportunity_id=opportunity["id"], approval_window_minutes=1440,
                )
                public_context = {
                    "sender": sender,
                    "recipient": email.recipient,
                    "subject": email.subject,
                    "body": email.body,
                    "opportunity_id": str(opportunity["id"]),
                }
                action = self._create_external_action(
                    action_type="communications.email_send",
                    opportunity_id=opportunity["id"],
                    target_display=contact,
                    public_context=public_context,
                    private_context={
                        **public_context,
                        "career_draft_id": str(context["draft_id"]),
                        "career_draft_sha256": canonical_hash(context["draft_content"]),
                    },
                    actor="scheduler:career-autopilot",
                    approval_window_minutes=1440,
                )
            if action["status"] != "pending_approval":
                self._item_state(
                    item, "prepared" if action["status"] in {"queued", "executing", "succeeded"}
                    else "needs_review", "Exact action progressed; inspect its recorded result",
                    action_id=action["id"],
                )
                return
            if action["expires_at"] <= datetime.now(UTC):
                self._item_state(item, "needs_review", "Exact action expired; review again",
                                 action_id=action["id"])
                return
            if run["mode"] == "prepare":
                self._item_state(item, "prepared", "Draft and exact action are ready for review",
                                 action_id=action["id"])
                return
            self._item_state(item, "preparing", "Exact action prepared; checking submission scope",
                             action_id=action["id"])
            self._authorize(run_id, item, action)
        except ActionPreparationError as exc:
            reason = (
                "Required application questions need explicit answers"
                if exc.missing_fields
                else str(exc)
            )
            self._item_state(item, "needs_review", reason[:500])

    def _item_state(self, item: dict[str, Any], state: str, reason: str,
                    *, action_id: UUID | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE career_autopilot_items SET state = %s, reason = %s, "
                "action_id = COALESCE(%s, action_id) "
                "WHERE run_id = %s AND opportunity_id = %s "
                "AND state IN ('preparing', 'waiting_budget')",
                (state, reason, action_id, item["run_id"], item["opportunity_id"]),
            )
            connection.commit()

    def _authorize(self, run_id: UUID, item: dict[str, Any], action: dict[str, Any]) -> None:
        with self.connect() as connection:
            run = connection.execute(
                "SELECT * FROM career_autopilot_runs WHERE id = %s", (run_id,)
            ).fetchone()
            lock_profile(connection, run["profile_id"])
            run = connection.execute(
                "SELECT * FROM career_autopilot_runs WHERE id = %s FOR UPDATE", (run_id,)
            ).fetchone()
            current_item = connection.execute(
                "SELECT state FROM career_autopilot_items "
                "WHERE run_id = %s AND opportunity_id = %s FOR UPDATE",
                (run_id, item["opportunity_id"]),
            ).fetchone()
            if current_item is None or current_item["state"] not in {"preparing", "waiting_budget"}:
                return
            profile = connection.execute(
                "SELECT * FROM career_profiles WHERE id = %s FOR SHARE", (run["profile_id"],)
            ).fetchone()
            opportunity = connection.execute(
                "SELECT * FROM job_opportunities WHERE id = %s FOR SHARE", (item["opportunity_id"],)
            ).fetchone()
            reason = eligibility_reason(run, profile, opportunity)
            if (
                reason
                or run["mode"] != "apply"
                or opportunity_hash(opportunity) != item["opportunity_hash"]
            ):
                raise ActionPreparationError(reason or "Authorization scope changed")
            used = connection.execute(
                "SELECT count(*) AS n FROM career_autopilot_actions "
                "WHERE profile_id = %s AND created_at > now() - interval '24 hours'",
                (profile["id"],),
            ).fetchone()["n"]
            if used >= run["max_applications_per_day"]:
                connection.execute(
                    "UPDATE career_autopilot_items SET state = 'waiting_budget', "
                    "reason = 'Application limit reached; waiting for an earlier reservation "
                    "to leave the rolling 24-hour window' "
                    "WHERE run_id = %s AND opportunity_id = %s",
                    (run_id, item["opportunity_id"]),
                )
                connection.commit()
                return
            # Only this run's freshly prepared material may be approved by its grant.
            execution = connection.execute(
                "SELECT private_context, public_context FROM external_actions WHERE id = %s",
                (action["id"],),
            ).fetchone()
            materials = (
                (
                    ("job_application_drafts", "draft_id"),
                    ("job_application_preflights", "preflight_id"),
                )
                if (action["action_type"] == "career.application_submit")
                else (("job_application_drafts", "career_draft_id"),)
            )
            for table, field in materials:
                origin = connection.execute(
                    sql.SQL(
                        "SELECT t.payload FROM {} d JOIN agent_tasks t "
                        "ON t.id = d.task_id WHERE d.id = %s"
                    ).format(sql.Identifier(table)),
                    (execution["private_context"][field],),
                ).fetchone()
                if not origin or origin["payload"].get("autopilot_run_id") != str(run_id):
                    raise ActionPreparationError("Application material belongs to a different run")
            if action["action_type"] == "career.application_submit" and not allowed_url(
                    execution["public_context"].get("apply_url", ""), run["allowed_hosts"]
            ):
                raise ActionPreparationError(
                    "Final form destination is outside the selected sites"
                )
            prior = connection.execute(
                "SELECT o.apply_url FROM external_actions a JOIN job_opportunities o "
                "ON o.id = a.opportunity_id WHERE o.profile_id = %s "
                "AND a.id <> %s AND a.status IN ('queued', 'executing', 'succeeded', 'ambiguous')",
                (profile["id"], action["id"]),
            ).fetchall()
            if any(
                target_key(row["apply_url"]) == target_key(opportunity["apply_url"])
                for row in prior
            ):
                raise ActionPreparationError(
                    "An application already exists or its outcome needs review"
                )
            inserted = connection.execute(
                """INSERT INTO career_autopilot_actions (
                    action_id, run_id, profile_id, opportunity_id, target_key, opportunity_hash
                ) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING action_id""",
                (
                    action["id"],
                    run_id,
                    profile["id"],
                    opportunity["id"],
                    target_key(opportunity["apply_url"]),
                    item["opportunity_hash"],
                ),
            ).fetchone()
            if not inserted:
                connection.execute(
                    "UPDATE career_autopilot_items SET state = 'needs_review', "
                    "reason = 'Target already reserved; inspect its previous application result' "
                    "WHERE run_id = %s AND opportunity_id = %s", (run_id, opportunity["id"]),
                )
                connection.commit()
                return
            self.decide_task(
                action["task_id"],
                ApprovalDecision(
                    decision="approved",
                    actor=f"autopilot:{run_id}",
                    reason=f"Within Play scope authorized by {run['authorized_by']} (run {run_id})",
                ),
                connection=connection,
            )
            connection.execute(
                "UPDATE career_autopilot_items SET state = 'authorized', "
                "reason = 'Queued within the active Play authorization' "
                "WHERE run_id = %s AND opportunity_id = %s",
                (run_id, opportunity["id"]),
            )
            connection.commit()
