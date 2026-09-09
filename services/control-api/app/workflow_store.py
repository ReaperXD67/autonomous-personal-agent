from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app.models import TaskCancellation, TaskCreate
from app.store import Database, InvalidTaskStateError
from app.workflow_models import WorkflowCreate, WorkflowStepCreate, output_matches

TERMINAL_TASKS = {"succeeded", "failed", "rejected", "cancelled", "dead_lettered"}
TERMINAL_STEPS = {"succeeded", "failed", "skipped", "cancelled"}


class WorkflowNotFoundError(LookupError):
    pass


class WorkflowConflictError(ValueError):
    pass


class WorkflowStore(Database):
    def _audit_workflow(self, connection, workflow, action, *, step=None):
        self._append_audit(
            connection, correlation_id=workflow["correlation_id"],
            task_id=step.get("task_id") if step else None,
            actor_type="orchestrator", actor_id="workflow-reconciler",
            action=action, risk_level=step["risk_level"] if step else "low",
            approval_status="not_applicable", execution_status=workflow["status"],
            input_metadata={"workflow_id": str(workflow["id"])},
            result_metadata={"step_key": step["key"], "status": step["status"]} if step else {},
        )

    @staticmethod
    def _view(connection, workflow):
        steps = connection.execute(
            """SELECT s.*, t.status AS task_status FROM workflow_steps s
               LEFT JOIN agent_tasks t ON t.id = s.task_id
               WHERE workflow_id = %s ORDER BY position""", (workflow["id"],),
        ).fetchall()
        return {**workflow, "steps": steps}

    def create_workflow(self, request: WorkflowCreate) -> dict[str, Any]:
        digest = hashlib.sha256(request.canonical_spec().encode("utf-8")).hexdigest()
        with self.connect() as connection:
            workflow = connection.execute(
                """INSERT INTO agent_workflows
                   (title, objective, requested_by, idempotency_key, specification_hash,
                    max_parallel, timeout_seconds, deadline_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, now() + make_interval(secs => %s))
                   ON CONFLICT (idempotency_key) DO NOTHING RETURNING *""",
                (request.title, request.objective, request.requested_by, request.idempotency_key,
                 digest, request.max_parallel, request.timeout_seconds, request.timeout_seconds),
            ).fetchone()
            if workflow is None:
                workflow = connection.execute(
                    "SELECT * FROM agent_workflows WHERE idempotency_key = %s",
                    (request.idempotency_key,),
                ).fetchone()
                if workflow["specification_hash"] != digest:
                    raise WorkflowConflictError(
                        "Idempotency key already belongs to a different plan"
                    )
                return self._view(connection, workflow)
            for position, step in enumerate(request.steps):
                connection.execute(
                    """INSERT INTO workflow_steps
                       (workflow_id, key, position, title, kind, payload, depends_on,
                        risk_level, expect_output) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (workflow["id"], step.key, position, step.title, step.kind, Jsonb(step.payload),
                     Jsonb(step.depends_on), step.risk_level.value, Jsonb(step.expect_output)),
                )
            self._audit_workflow(connection, workflow, "workflow.created")
            return self._view(connection, workflow)

    def get_workflow(self, workflow_id: UUID) -> dict[str, Any]:
        with self.connect() as connection:
            workflow = connection.execute(
                "SELECT * FROM agent_workflows WHERE id = %s", (workflow_id,),
            ).fetchone()
            if workflow is None:
                raise WorkflowNotFoundError(str(workflow_id))
            return self._view(connection, workflow)

    def list_workflows(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            workflows = connection.execute(
                "SELECT * FROM agent_workflows ORDER BY created_at DESC LIMIT %s", (limit,),
            ).fetchall()
            return [self._view(connection, row) for row in workflows]

    def cancel_workflow(self, workflow_id: UUID, request: TaskCancellation) -> dict[str, Any]:
        with self.connect() as connection:
            workflow = connection.execute(
                "SELECT * FROM agent_workflows WHERE id = %s FOR UPDATE", (workflow_id,),
            ).fetchone()
            if workflow is None:
                raise WorkflowNotFoundError(str(workflow_id))
            if workflow["status"] not in {"running", "cancelling"}:
                if workflow["status"] in {"cancelled", "timed_out"}:
                    return self._view(connection, workflow)
                raise InvalidTaskStateError("Completed workflow cannot be cancelled")
            if workflow["stop_reason"] is None:
                workflow = connection.execute(
                    """UPDATE agent_workflows SET status = 'cancelling', stop_reason = 'cancelled'
                       WHERE id = %s RETURNING *""", (workflow_id,),
                ).fetchone()
                self._audit_workflow(connection, workflow, "workflow.cancellation_requested")
            self._reconcile_one(connection, workflow, cancellation=request)
            return self._view(connection, workflow)

    def reconcile_workflows(self, limit: int = 20) -> int:
        with self.connect() as connection:
            workflows = connection.execute(
                """SELECT * FROM agent_workflows WHERE status IN ('running', 'cancelling')
                   ORDER BY reconciled_at, id LIMIT %s FOR UPDATE SKIP LOCKED""", (limit,),
            ).fetchall()
            for workflow in workflows:
                self._reconcile_one(connection, workflow)
            return len(workflows)

    def _step_state(self, connection, workflow, step, status, error_code=None):
        connection.execute(
            """UPDATE workflow_steps SET status = %s, error_code = %s
               WHERE workflow_id = %s AND key = %s""",
            (status, error_code, workflow["id"], step["key"]),
        )
        step.update(status=status, error_code=error_code)
        self._audit_workflow(connection, workflow, f"workflow.step_{status}", step=step)

    def _reconcile_one(self, connection, workflow, cancellation=None):
        # Every mutator takes workflow -> task locks in this order. Child workers
        # only lock tasks. Creation, bindings, cancellation, and audit share a commit.
        steps = connection.execute(
            "SELECT * FROM workflow_steps WHERE workflow_id = %s ORDER BY position",
            (workflow["id"],),
        ).fetchall()
        tasks = {row["id"]: row for row in connection.execute(
            """SELECT * FROM agent_tasks WHERE id IN
               (SELECT task_id FROM workflow_steps WHERE workflow_id = %s)
               ORDER BY id FOR UPDATE""", (workflow["id"],),
        ).fetchall()}
        for step in steps:
            task = tasks.get(step["task_id"])
            if step["status"] == "dispatched" and task["status"] in TERMINAL_TASKS:
                if task["status"] == "succeeded":
                    passed = output_matches(task["output"], step["expect_output"])
                    self._step_state(connection, workflow, step,
                                     "succeeded" if passed else "failed",
                                     None if passed else "OUTPUT_CHECK_FAILED")
                else:
                    self._step_state(connection, workflow, step,
                                     "cancelled" if task["status"] == "cancelled" else "failed",
                                     task["error_code"] or f"TASK_{task['status'].upper()}")

        current_time = connection.execute("SELECT clock_timestamp() AS value").fetchone()["value"]
        finished_late = any(
            task["completed_at"] is not None and task["completed_at"] > workflow["deadline_at"]
            for task in tasks.values()
        )
        if (workflow["stop_reason"] is None and current_time >= workflow["deadline_at"]
                and (finished_late or not all(s["status"] in TERMINAL_STEPS for s in steps))):
            workflow.update(status="cancelling", stop_reason="timed_out")
            self._audit_workflow(connection, workflow, "workflow.deadline_reached")

        if workflow["stop_reason"]:
            cancellation = cancellation or TaskCancellation(
                actor="workflow-reconciler", reason=workflow["stop_reason"],
            )
            for step in steps:
                if step["status"] == "pending":
                    self._step_state(connection, workflow, step, "cancelled", "WORKFLOW_STOPPED")
                elif step["status"] == "dispatched":
                    task = tasks[step["task_id"]]
                    if task["cancellation_requested_at"] is None:
                        task = self._cancel_task_record(connection, task["id"], cancellation)
                    if task["status"] == "cancelled":
                        self._step_state(
                            connection, workflow, step, "cancelled", "WORKFLOW_STOPPED"
                        )
        else:
            by_key = {step["key"]: step for step in steps}
            # Propagate failures to a fixed point even when the submitted order
            # is not topological. Independent branches are allowed to finish.
            changed = True
            while changed:
                changed = False
                for step in steps:
                    if step["status"] == "pending" and any(
                        by_key[key]["status"] in {"failed", "skipped", "cancelled"}
                        for key in step["depends_on"]
                    ):
                        self._step_state(connection, workflow, step, "skipped", "DEPENDENCY_FAILED")
                        changed = True
            capacity = workflow["max_parallel"] - sum(s["status"] == "dispatched" for s in steps)
            for step in steps:
                if capacity <= 0:
                    break
                if step["status"] != "pending" or not all(
                    by_key[key]["status"] == "succeeded" for key in step["depends_on"]
                ):
                    continue
                # Revalidate the immutable step before granting a capability.
                try:
                    spec = WorkflowStepCreate.model_validate({
                        key: step[key] for key in
                        ("key", "title", "kind", "payload", "depends_on",
                         "risk_level", "expect_output")
                    })
                except (ValidationError, KeyError):
                    # A future policy/schema change can invalidate an older plan.
                    # Quarantine that step without stopping unrelated workflows.
                    self._step_state(connection, workflow, step, "failed", "STEP_POLICY_REJECTED")
                    continue
                task = self._create_task_record(connection, TaskCreate(
                    title=spec.title, kind=spec.kind,
                    payload={**spec.payload, "workflow_managed": True},
                    risk_level=spec.risk_level, requested_by=workflow["requested_by"],
                ))
                connection.execute(
                    "UPDATE workflow_steps SET task_id = %s WHERE workflow_id = %s AND key = %s",
                    (task["id"], workflow["id"], step["key"]),
                )
                step["task_id"] = task["id"]
                self._step_state(connection, workflow, step, "dispatched")
                capacity -= 1

        if all(step["status"] in TERMINAL_STEPS for step in steps):
            workflow["status"] = workflow["stop_reason"] or (
                "succeeded" if all(s["status"] == "succeeded" for s in steps) else "failed"
            )
            workflow["completed_at"] = current_time
            self._audit_workflow(connection, workflow, f"workflow.{workflow['status']}")
        updated = connection.execute(
            """UPDATE agent_workflows SET status = %s, stop_reason = %s,
               completed_at = %s, reconciled_at = now() WHERE id = %s RETURNING updated_at""",
            (workflow["status"], workflow["stop_reason"], workflow["completed_at"], workflow["id"]),
        ).fetchone()
        workflow["updated_at"] = updated["updated_at"]
