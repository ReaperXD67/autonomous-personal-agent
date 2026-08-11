from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.models import ApprovalDecision, TaskCreate
from app.policy import initial_status, requires_approval


class TaskNotFoundError(LookupError):
    pass


class InvalidTaskStateError(RuntimeError):
    pass


class Database:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            yield connection

    def check(self) -> bool:
        with self.connect() as connection:
            return connection.execute("SELECT 1 AS ok").fetchone()["ok"] == 1

    @staticmethod
    def _append_audit(
        connection: psycopg.Connection[Any],
        *,
        correlation_id: UUID,
        task_id: UUID | None,
        actor_type: str,
        actor_id: str,
        action: str,
        risk_level: str,
        approval_status: str,
        execution_status: str,
        tool_name: str | None = None,
        input_metadata: dict[str, Any] | None = None,
        result_metadata: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_events (
                correlation_id, task_id, actor_type, actor_id, tool_name, action,
                risk_level, approval_status, execution_status, input_metadata,
                result_metadata, error_code, error_message, redacted
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
            """,
            (
                correlation_id,
                task_id,
                actor_type,
                actor_id,
                tool_name,
                action,
                risk_level,
                approval_status,
                execution_status,
                Jsonb(input_metadata or {}),
                Jsonb(result_metadata or {}),
                error_code,
                error_message[:1000] if error_message else None,
            ),
        )

    @staticmethod
    def _add_outbox(connection: psycopg.Connection[Any], task: dict[str, Any]) -> None:
        connection.execute(
            """
            INSERT INTO task_outbox (task_id, correlation_id, topic, payload)
            VALUES (%s, %s, 'task.ready', %s)
            ON CONFLICT (task_id, topic) DO NOTHING
            """,
            (
                task["id"],
                task["correlation_id"],
                Jsonb(
                    {
                        "task_id": str(task["id"]),
                        "correlation_id": str(task["correlation_id"]),
                    }
                ),
            ),
        )

    def create_task(self, request: TaskCreate) -> dict[str, Any]:
        status = initial_status(request.risk_level)
        with self.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO agent_tasks (
                    title, kind, payload, risk_level, status, requested_by, idempotency_key
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING *
                """,
                (
                    request.title,
                    request.kind,
                    Jsonb(request.payload),
                    request.risk_level.value,
                    status,
                    request.requested_by,
                    request.idempotency_key,
                ),
            ).fetchone()
            if row is None:
                if request.idempotency_key is None:
                    raise RuntimeError("Task insert returned no row without idempotency conflict")
                existing = connection.execute(
                    "SELECT * FROM agent_tasks WHERE idempotency_key = %s",
                    (request.idempotency_key,),
                ).fetchone()
                if existing is None:
                    raise RuntimeError("Idempotency conflict row was not found")
                return existing

            approval = (
                "required" if requires_approval(request.risk_level) else "not_required"
            )
            self._append_audit(
                connection,
                correlation_id=row["correlation_id"],
                task_id=row["id"],
                actor_type="user",
                actor_id=request.requested_by,
                tool_name=request.kind,
                action="task.created",
                risk_level=request.risk_level.value,
                approval_status=approval,
                execution_status=row["status"],
                input_metadata={"kind": request.kind, "payload_keys": sorted(request.payload)},
            )
            if row["status"] == "queued":
                self._add_outbox(connection, row)
            connection.commit()
            return row

    def get_task(self, task_id: UUID) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_tasks WHERE id = %s", (task_id,)
            ).fetchone()
        if row is None:
            raise TaskNotFoundError(str(task_id))
        return row

    def decide_task(self, task_id: UUID, request: ApprovalDecision) -> dict[str, Any]:
        with self.connect() as connection:
            task = connection.execute(
                "SELECT * FROM agent_tasks WHERE id = %s FOR UPDATE", (task_id,)
            ).fetchone()
            if task is None:
                raise TaskNotFoundError(str(task_id))
            if task["status"] != "pending_approval":
                raise InvalidTaskStateError(f"Task is {task['status']}, not pending_approval")

            next_status = "queued" if request.decision == "approved" else "rejected"
            approved_by = request.actor if request.decision == "approved" else None
            connection.execute(
                """
                INSERT INTO task_approvals (task_id, decision, actor, reason)
                VALUES (%s, %s, %s, %s)
                """,
                (task_id, request.decision, request.actor, request.reason),
            )
            row = connection.execute(
                """
                UPDATE agent_tasks
                SET status = %s,
                    approved_by = %s,
                    approved_at = CASE WHEN %s = 'approved' THEN now() ELSE NULL END,
                    completed_at = CASE WHEN %s = 'rejected' THEN now() ELSE NULL END
                WHERE id = %s
                RETURNING *
                """,
                (next_status, approved_by, request.decision, request.decision, task_id),
            ).fetchone()
            self._append_audit(
                connection,
                correlation_id=row["correlation_id"],
                task_id=row["id"],
                actor_type="approver",
                actor_id=request.actor,
                tool_name=row["kind"],
                action=f"task.{request.decision}",
                risk_level=row["risk_level"],
                approval_status=request.decision,
                execution_status=row["status"],
                input_metadata={"reason_provided": request.reason is not None},
            )
            if row["status"] == "queued":
                self._add_outbox(connection, row)
            connection.commit()
            return row

    def transition_to_running(self, task_id: UUID) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                UPDATE agent_tasks
                SET status = 'running', started_at = now(), attempt_count = attempt_count + 1
                WHERE id = %s AND status = 'queued'
                RETURNING *
                """,
                (task_id,),
            ).fetchone()
            if row is not None:
                self._append_audit(
                    connection,
                    correlation_id=row["correlation_id"],
                    task_id=row["id"],
                    actor_type="worker",
                    actor_id="foundation-worker",
                    tool_name=row["kind"],
                    action="task.started",
                    risk_level=row["risk_level"],
                    approval_status="approved" if row["approved_by"] else "not_required",
                    execution_status="running",
                )
            connection.commit()
            return row

    def complete_task(self, task_id: UUID, output: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                UPDATE agent_tasks
                SET status = 'succeeded', output = %s, completed_at = now()
                WHERE id = %s AND status = 'running'
                RETURNING *
                """,
                (Jsonb(output), task_id),
            ).fetchone()
            if row is None:
                raise InvalidTaskStateError("Task was not running during completion")
            self._append_audit(
                connection,
                correlation_id=row["correlation_id"],
                task_id=row["id"],
                actor_type="worker",
                actor_id="foundation-worker",
                tool_name=row["kind"],
                action="task.succeeded",
                risk_level=row["risk_level"],
                approval_status="approved" if row["approved_by"] else "not_required",
                execution_status="succeeded",
                result_metadata={"output_keys": sorted(output)},
            )
            connection.commit()
            return row

    def fail_task(self, task_id: UUID, code: str, message: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                UPDATE agent_tasks
                SET status = 'failed', error_code = %s, error_message = %s, completed_at = now()
                WHERE id = %s AND status = 'running'
                RETURNING *
                """,
                (code[:100], message[:1000], task_id),
            ).fetchone()
            if row is None:
                raise InvalidTaskStateError("Task was not running during failure")
            self._append_audit(
                connection,
                correlation_id=row["correlation_id"],
                task_id=row["id"],
                actor_type="worker",
                actor_id="foundation-worker",
                tool_name=row["kind"],
                action="task.failed",
                risk_level=row["risk_level"],
                approval_status="approved" if row["approved_by"] else "not_required",
                execution_status="failed",
                error_code=code,
                error_message=message,
            )
            connection.commit()
            return row

    def pending_outbox(self, limit: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT id, task_id, correlation_id, topic, payload, attempt_count
                FROM task_outbox
                WHERE published_at IS NULL
                ORDER BY created_at
                LIMIT %s
                """,
                (limit,),
            ).fetchall()

    def mark_outbox_published(self, event_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE task_outbox
                SET published_at = now(), attempt_count = attempt_count + 1, last_error = NULL
                WHERE id = %s AND published_at IS NULL
                """,
                (event_id,),
            )
            connection.commit()

    def mark_outbox_failed(self, event_id: int, message: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE task_outbox
                SET attempt_count = attempt_count + 1, last_error = %s
                WHERE id = %s AND published_at IS NULL
                """,
                (message[:1000], event_id),
            )
            connection.commit()

    def status_counts(self) -> dict[str, int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT status, count(*)::int AS count FROM agent_tasks GROUP BY status"
            ).fetchall()
        return {row["status"]: row["count"] for row in rows}
