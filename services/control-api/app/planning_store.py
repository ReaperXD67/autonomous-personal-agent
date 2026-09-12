from __future__ import annotations

import hmac
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from app.career_store import CareerStore
from app.models import TaskCreate
from app.planning_models import (
    ModelPlanChoice,
    PlanAdopt,
    PlanCreate,
    compile_workflow,
    workflow_digest,
)
from app.policy import RiskLevel
from app.store import InvalidTaskStateError
from app.workflow_models import WorkflowCreate
from app.workflow_store import WorkflowStore


class PlanNotFoundError(LookupError):
    pass


class PlanConflictError(ValueError):
    pass


class PlanContextError(ValueError):
    pass


class PlanningStore(CareerStore, WorkflowStore):
    @staticmethod
    def _inventory(connection, request: PlanCreate) -> list[dict[str, Any]]:
        inventory = []

        def add(key, title, kind, payload, expected):
            inventory.append({
                "key": key, "title": title, "kind": kind,
                "payload": payload, "expect_output": expected,
            })

        if request.profile_id:
            profile = connection.execute(
                "SELECT length(trim(resume_text)) > 0 AS has_resume "
                "FROM career_profiles WHERE id = %s", (request.profile_id,),
            ).fetchone()
            if profile is None:
                raise PlanContextError("Selected career profile was not found")
            add("scan_jobs", "Scan fresh jobs for the selected career profile", "career.search",
                {"profile_id": str(request.profile_id)}, {"handler": "career.search"})
            for index, opportunity_id in enumerate(request.opportunity_ids, start=1):
                opportunity = connection.execute(
                    "SELECT id FROM job_opportunities WHERE id = %s AND profile_id = %s",
                    (opportunity_id, request.profile_id),
                ).fetchone()
                if opportunity is None:
                    raise PlanContextError("Selected opportunity does not belong to this profile")
                context = {
                    "profile_id": str(request.profile_id), "opportunity_id": str(opportunity_id),
                }
                if profile["has_resume"]:
                    add(f"draft_{index}", f"Draft materials for selected opportunity {index}",
                        "career.application_draft", context, {"draft_created": True})
                add(f"inspect_{index}", f"Inspect the form for selected opportunity {index}",
                    "career.application_preflight", context, {"blocked_reason": None})
        if request.campaign_id:
            campaign = connection.execute(
                "SELECT id FROM marketing_campaigns WHERE id = %s", (request.campaign_id,),
            ).fetchone()
            if campaign is None:
                raise PlanContextError("Selected creator campaign was not found")
            add("discover_creators", "Discover public creators for the selected campaign",
                "marketing.creator_discovery", {"campaign_id": str(request.campaign_id)},
                {"contact_emails_discovered": 0})
        if not inventory:
            add("verify_runtime", "Verify the durable workflow runtime", "foundation.echo",
                {"message": "GOAL_PLAN_RUNTIME_OK"}, {"echo": "GOAL_PLAN_RUNTIME_OK"})
        return inventory

    def _audit_plan(self, connection, plan, action, *, actor="goal-planner"):
        self._append_audit(
            connection, correlation_id=plan["correlation_id"], task_id=plan["task_id"],
            actor_type="planner", actor_id=actor, tool_name="planning.propose", action=action,
            risk_level="medium", approval_status="not_applicable", execution_status=plan["status"],
            input_metadata={"plan_id": str(plan["id"])},
        )

    @staticmethod
    def _plan_view(connection, plan):
        task = connection.execute(
            "SELECT status, error_code FROM agent_tasks WHERE id = %s", (plan["task_id"],),
        ).fetchone()
        result = {**plan, "task_status": task["status"]}
        if task["status"] in {"failed", "cancelled", "rejected", "dead_lettered"}:
            result["status"] = "failed"
            result["error_code"] = (
                plan["error_code"] or task["error_code"] or "PLAN_TASK_INTERRUPTED"
            )
        elif task["status"] != "succeeded" and plan["status"] in {"ready", "unsupported"}:
            result["status"] = "queued"
        return result

    def create_plan(self, request: PlanCreate) -> dict[str, Any]:
        with self.connect() as connection:
            inventory = self._inventory(connection, request)
            plan = connection.execute(
                """INSERT INTO goal_plans
                   (goal, requested_by, mode, request_context, action_inventory,
                    request_hash, idempotency_key)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (idempotency_key) DO NOTHING RETURNING *""",
                (request.goal, request.requested_by, request.mode,
                 Jsonb(request.model_dump(mode="json", exclude={"idempotency_key"})),
                 Jsonb(inventory), request.digest(), request.idempotency_key),
            ).fetchone()
            if plan is None:
                plan = connection.execute(
                    "SELECT * FROM goal_plans WHERE idempotency_key = %s",
                    (request.idempotency_key,),
                ).fetchone()
                if plan["request_hash"] != request.digest():
                    raise PlanConflictError("Idempotency key belongs to a different goal request")
                return self._plan_view(connection, plan)
            task = self._create_task_record(connection, TaskCreate(
                title="Prepare a reviewable goal proposal", kind="planning.propose",
                payload={"plan_id": str(plan["id"])}, risk_level=RiskLevel.MEDIUM,
                requested_by=request.requested_by,
            ))
            plan = connection.execute(
                "UPDATE goal_plans SET task_id = %s WHERE id = %s RETURNING *",
                (task["id"], plan["id"]),
            ).fetchone()
            self._audit_plan(connection, plan, "plan.created", actor=request.requested_by)
            return self._plan_view(connection, plan)

    def get_plan(self, plan_id: UUID) -> dict[str, Any]:
        with self.connect() as connection:
            plan = connection.execute(
                "SELECT * FROM goal_plans WHERE id = %s", (plan_id,),
            ).fetchone()
            if plan is None:
                raise PlanNotFoundError(str(plan_id))
            return self._plan_view(connection, plan)

    def list_plans(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            plans = connection.execute(
                "SELECT * FROM goal_plans ORDER BY created_at DESC LIMIT %s", (limit,),
            ).fetchall()
            return [self._plan_view(connection, plan) for plan in plans]

    @staticmethod
    def _owned_task(connection, task_id, lease_id):
        task = connection.execute(
            "SELECT * FROM agent_tasks WHERE id = %s FOR UPDATE", (task_id,),
        ).fetchone()
        current = connection.execute("SELECT clock_timestamp() AS value").fetchone()["value"]
        if (task is None or task["kind"] != "planning.propose" or task["status"] != "running"
                or task["lease_id"] != lease_id or task["cancellation_requested_at"] is not None
                or task["lease_expires_at"] is None or task["lease_expires_at"] <= current):
            raise InvalidTaskStateError("Planning task no longer owns a valid execution lease")
        return task

    def get_plan_for_execution(self, plan_id: UUID, task_id: UUID, lease_id: UUID):
        with self.connect() as connection:
            self._owned_task(connection, task_id, lease_id)
            plan = connection.execute(
                "SELECT * FROM goal_plans WHERE id = %s AND task_id = %s", (plan_id, task_id),
            ).fetchone()
            if plan is None:
                raise PlanContextError("Planning task is not linked to this goal proposal")
            return plan

    def save_proposal(
        self, *, plan_id, task_id, lease_id, choice: ModelPlanChoice,
        source: str, selected_model: str | None,
    ):
        with self.connect() as connection:
            self._owned_task(connection, task_id, lease_id)
            plan = connection.execute(
                "SELECT * FROM goal_plans WHERE id = %s AND task_id = %s FOR UPDATE",
                (plan_id, task_id),
            ).fetchone()
            if plan is None or plan["status"] != "queued":
                raise PlanConflictError("Goal proposal is no longer waiting for model output")
            request = PlanCreate.model_validate(plan["request_context"])
            spec = compile_workflow(request, choice, plan["action_inventory"])
            limitations = list(choice.limitations)
            limitations.append("This proposal cannot send, submit, publish, or select new context.")
            if request.opportunity_ids:
                limitations.append("Only the selected existing opportunities are included.")
            plan = connection.execute(
                """UPDATE goal_plans SET status = %s, source = %s, selected_model = %s,
                   summary = %s, limitations = %s, workflow_spec = %s, plan_digest = %s
                   WHERE id = %s RETURNING *""",
                ("ready" if spec else "unsupported", source, selected_model,
                 choice.summary, Jsonb(limitations),
                 Jsonb(spec.model_dump(mode="json")) if spec else None,
                 workflow_digest(spec) if spec else None, plan_id),
            ).fetchone()
            self._audit_plan(connection, plan, f"plan.{plan['status']}")
            return plan

    def fail_plan(self, plan_id, task_id, lease_id, error_code="PLAN_MODEL_UNAVAILABLE"):
        with self.connect() as connection:
            self._owned_task(connection, task_id, lease_id)
            plan = connection.execute(
                """UPDATE goal_plans SET status = 'failed', error_code = %s
                   WHERE id = %s AND task_id = %s AND status = 'queued' RETURNING *""",
                (error_code, plan_id, task_id),
            ).fetchone()
            if plan:
                self._audit_plan(connection, plan, "plan.failed")

    def adopt_plan(self, plan_id: UUID, request: PlanAdopt) -> dict[str, Any]:
        with self.connect() as connection:
            identity = connection.execute(
                "SELECT task_id FROM goal_plans WHERE id = %s", (plan_id,),
            ).fetchone()
            if identity is None:
                raise PlanNotFoundError(str(plan_id))
            # Match the worker's task -> proposal lock order, then create the
            # workflow and adoption link in this same transaction.
            task = connection.execute(
                "SELECT status FROM agent_tasks WHERE id = %s FOR UPDATE", (identity["task_id"],),
            ).fetchone()
            plan = connection.execute(
                "SELECT * FROM goal_plans WHERE id = %s FOR UPDATE", (plan_id,),
            ).fetchone()
            if not plan["plan_digest"] or not hmac.compare_digest(
                request.plan_digest, plan["plan_digest"],
            ):
                raise PlanConflictError("Proposal digest does not match the reviewed plan")
            if plan["status"] == "adopted":
                workflow = connection.execute(
                    "SELECT * FROM agent_workflows WHERE id = %s", (plan["workflow_id"],),
                ).fetchone()
                return self._view(connection, workflow)
            current = connection.execute("SELECT clock_timestamp() AS value").fetchone()["value"]
            if plan["status"] != "ready" or task["status"] != "succeeded":
                raise PlanConflictError("Only a successfully prepared proposal can be adopted")
            if plan["expires_at"] <= current:
                raise PlanConflictError("Proposal expired; prepare a fresh goal proposal")
            try:
                spec = WorkflowCreate.model_validate(plan["workflow_spec"])
                context = PlanCreate.model_validate(plan["request_context"])
                inventory = self._inventory(connection, context)
                expected = compile_workflow(context, ModelPlanChoice(
                    supported=True, action_keys=[step.key for step in spec.steps],
                    summary="Revalidate the selected actions",
                ), inventory)
            except ValueError:
                raise PlanConflictError(
                    "Selected context is no longer valid for this proposal"
                ) from None
            if (expected is None or workflow_digest(spec) != plan["plan_digest"]
                    or workflow_digest(expected) != plan["plan_digest"]):
                raise PlanConflictError("Proposal context or executable specification changed")
            workflow = self._create_workflow_record(connection, spec)
            plan = connection.execute(
                """UPDATE goal_plans SET status = 'adopted', workflow_id = %s,
                   adopted_by = %s WHERE id = %s RETURNING *""",
                (workflow["id"], request.actor, plan_id),
            ).fetchone()
            self._audit_plan(connection, plan, "plan.adopted", actor=request.actor)
            return workflow
