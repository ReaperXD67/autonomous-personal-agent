from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.models import ApprovalDecision, TaskCancellation, TaskCreate
from app.policy import capability_max_attempts, effective_risk, initial_status, requires_approval


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
        if task["kind"] in {
            "career.application_preflight",
            "career.application_submit",
            "communications.email_send",
        }:
            topic = "action.ready"
        elif task["kind"].startswith("career."):
            topic = "career.ready"
        else:
            topic = "task.ready"
        connection.execute(
            """
            INSERT INTO task_outbox (
                task_id, correlation_id, topic, payload, available_at
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (task_id, topic) DO UPDATE
            SET correlation_id = EXCLUDED.correlation_id,
                payload = EXCLUDED.payload,
                available_at = EXCLUDED.available_at,
                published_at = NULL,
                last_error = NULL
            """,
            (
                task["id"],
                task["correlation_id"],
                topic,
                Jsonb(
                    {
                        "task_id": str(task["id"]),
                        "correlation_id": str(task["correlation_id"]),
                    }
                ),
                task["next_attempt_at"],
            ),
        )

    def _create_task_record(
        self, connection: psycopg.Connection[Any], request: TaskCreate
    ) -> dict[str, Any]:
        risk_level = effective_risk(request.kind, request.risk_level)
        status = initial_status(risk_level)
        row = connection.execute(
            """
            INSERT INTO agent_tasks (
                title, kind, payload, risk_level, status, requested_by,
                idempotency_key, max_attempts
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING *
            """,
            (
                request.title,
                request.kind,
                Jsonb(request.payload),
                risk_level.value,
                status,
                request.requested_by,
                request.idempotency_key,
                capability_max_attempts(request.kind),
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

        approval = "required" if requires_approval(risk_level) else "not_required"
        self._append_audit(
            connection,
            correlation_id=row["correlation_id"],
            task_id=row["id"],
            actor_type="user",
            actor_id=request.requested_by,
            tool_name=request.kind,
            action="task.created",
            risk_level=risk_level.value,
            approval_status=approval,
            execution_status=row["status"],
            input_metadata={"kind": request.kind, "payload_keys": sorted(request.payload)},
        )
        if row["status"] == "queued":
            self._add_outbox(connection, row)
        return row

    def create_task(self, request: TaskCreate) -> dict[str, Any]:
        with self.connect() as connection:
            row = self._create_task_record(connection, request)
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

    def list_tasks(
        self,
        *,
        task_status: str | None = None,
        kind_prefix: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT * FROM agent_tasks
                WHERE (%s IS NULL OR status = %s)
                  AND (%s IS NULL OR kind LIKE (%s || '%%'))
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (task_status, task_status, kind_prefix, kind_prefix, limit),
            ).fetchall()

    def list_audit_events(
        self, *, task_id: UUID | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT * FROM audit_events
                WHERE (%s::uuid IS NULL OR task_id = %s)
                ORDER BY occurred_at DESC
                LIMIT %s
                """,
                (task_id, task_id, limit),
            ).fetchall()

    def list_dead_letters(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT * FROM agent_tasks
                WHERE status = 'dead_lettered'
                ORDER BY dead_lettered_at DESC, updated_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()

    def cancel_task(self, task_id: UUID, request: TaskCancellation) -> dict[str, Any]:
        with self.connect() as connection:
            task = connection.execute(
                "SELECT * FROM agent_tasks WHERE id = %s FOR UPDATE", (task_id,)
            ).fetchone()
            if task is None:
                raise TaskNotFoundError(str(task_id))
            if task["status"] == "cancelled":
                return task
            if task["status"] in {
                "succeeded",
                "failed",
                "rejected",
                "dead_lettered",
            }:
                raise InvalidTaskStateError(f"Task is already {task['status']}")

            immediate = task["status"] in {"pending_approval", "queued"}
            row = connection.execute(
                """
                UPDATE agent_tasks
                SET status = CASE WHEN %s THEN 'cancelled' ELSE status END,
                    cancellation_requested_at = now(),
                    cancellation_requested_by = %s,
                    cancellation_reason = %s,
                    completed_at = CASE WHEN %s THEN now() ELSE completed_at END,
                    lease_expires_at = CASE WHEN %s THEN NULL ELSE lease_expires_at END,
                    lease_id = CASE WHEN %s THEN NULL ELSE lease_id END,
                    claimed_by = CASE WHEN %s THEN NULL ELSE claimed_by END
                WHERE id = %s
                RETURNING *
                """,
                (
                    immediate,
                    request.actor,
                    request.reason,
                    immediate,
                    immediate,
                    immediate,
                    immediate,
                    task_id,
                ),
            ).fetchone()
            if immediate:
                connection.execute("DELETE FROM task_outbox WHERE task_id = %s", (task_id,))
                connection.execute(
                    """
                    UPDATE external_actions
                    SET status = 'cancelled'
                    WHERE task_id = %s AND status IN ('pending_approval', 'queued')
                    """,
                    (task_id,),
                )
            action = "task.cancelled" if immediate else "task.cancellation_requested"
            self._append_audit(
                connection,
                correlation_id=row["correlation_id"],
                task_id=row["id"],
                actor_type="user",
                actor_id=request.actor,
                tool_name=row["kind"],
                action=action,
                risk_level=row["risk_level"],
                approval_status="approved" if row["approved_by"] else "not_required",
                execution_status=row["status"],
                input_metadata={"reason_provided": request.reason is not None},
            )
            connection.commit()
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

            action = connection.execute(
                "SELECT * FROM external_actions WHERE task_id = %s FOR UPDATE",
                (task_id,),
            ).fetchone()
            action_hash = None
            if action is not None:
                action_hash = task["payload"].get("action_digest")
                if action_hash != action["context_hash"]:
                    raise InvalidTaskStateError("Action context changed after it was prepared")
                if request.decision == "approved" and action["expires_at"] <= connection.execute(
                    "SELECT now() AS current_time"
                ).fetchone()["current_time"]:
                    raise InvalidTaskStateError("Action approval window has expired")

            next_status = "queued" if request.decision == "approved" else "rejected"
            approved_by = request.actor if request.decision == "approved" else None
            connection.execute(
                """
                INSERT INTO task_approvals (
                    task_id, decision, actor, reason, action_context_hash
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (task_id, request.decision, request.actor, request.reason, action_hash),
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
            if action is not None:
                connection.execute(
                    """
                    UPDATE external_actions
                    SET status = %s, last_error = NULL
                    WHERE id = %s
                    """,
                    (next_status, action["id"]),
                )
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

    def transition_to_running(
        self, task_id: UUID, lease_seconds: int, worker_id: str
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                UPDATE agent_tasks
                SET status = 'running',
                    started_at = now(),
                    attempt_count = attempt_count + 1,
                    last_heartbeat_at = now(),
                    lease_expires_at = now() + make_interval(secs => %s),
                    lease_id = gen_random_uuid(),
                    claimed_by = %s
                WHERE id = %s AND status = 'queued' AND next_attempt_at <= now()
                RETURNING *
                """,
                (lease_seconds, worker_id, task_id),
            ).fetchone()
            if row is not None:
                self._append_audit(
                    connection,
                    correlation_id=row["correlation_id"],
                    task_id=row["id"],
                    actor_type="worker",
                    actor_id=worker_id,
                    tool_name=row["kind"],
                    action="task.started",
                    risk_level=row["risk_level"],
                    approval_status="approved" if row["approved_by"] else "not_required",
                    execution_status="running",
                )
            connection.commit()
            return row

    def heartbeat_task(self, task_id: UUID, lease_id: UUID, lease_seconds: int) -> str:
        with self.connect() as connection:
            task = connection.execute(
                """
                SELECT status, lease_id, cancellation_requested_at
                FROM agent_tasks WHERE id = %s FOR UPDATE
                """,
                (task_id,),
            ).fetchone()
            if task is None or task["status"] != "running" or task["lease_id"] != lease_id:
                return "lost"
            if task["cancellation_requested_at"] is not None:
                return "cancel_requested"
            connection.execute(
                """
                UPDATE agent_tasks
                SET last_heartbeat_at = now(),
                    lease_expires_at = now() + make_interval(secs => %s)
                WHERE id = %s AND lease_id = %s AND status = 'running'
                """,
                (lease_seconds, task_id, lease_id),
            )
            connection.commit()
            return "renewed"

    def complete_task(
        self, task_id: UUID, lease_id: UUID, output: dict[str, Any]
    ) -> dict[str, Any]:
        with self.connect() as connection:
            task = connection.execute(
                "SELECT * FROM agent_tasks WHERE id = %s FOR UPDATE", (task_id,)
            ).fetchone()
            if (
                task is None
                or task["status"] != "running"
                or task["lease_id"] != lease_id
            ):
                raise InvalidTaskStateError("Worker no longer owns the running task lease")
            if task["cancellation_requested_at"] is not None:
                return self._finalize_cancellation(connection, task, lease_id)
            if task["lease_expires_at"] is None or task["lease_expires_at"] <= connection.execute(
                "SELECT now() AS now"
            ).fetchone()["now"]:
                raise InvalidTaskStateError("Worker task lease expired before completion")

            row = connection.execute(
                """
                UPDATE agent_tasks
                SET status = 'succeeded', output = %s, completed_at = now(),
                    lease_expires_at = NULL, last_heartbeat_at = NULL,
                    lease_id = NULL, claimed_by = NULL
                WHERE id = %s AND lease_id = %s AND status = 'running'
                RETURNING *
                """,
                (Jsonb(output), task_id, lease_id),
            ).fetchone()
            if row is None:
                raise InvalidTaskStateError("Worker lost task lease during completion")
            self._append_audit(
                connection,
                correlation_id=row["correlation_id"],
                task_id=row["id"],
                actor_type="worker",
                actor_id=task["claimed_by"] or "worker",
                tool_name=row["kind"],
                action="task.succeeded",
                risk_level=row["risk_level"],
                approval_status="approved" if row["approved_by"] else "not_required",
                execution_status="succeeded",
                result_metadata={"output_keys": sorted(output)},
            )
            connection.commit()
            return row

    def _finalize_cancellation(
        self,
        connection: psycopg.Connection[Any],
        task: dict[str, Any],
        lease_id: UUID,
    ) -> dict[str, Any]:
        row = connection.execute(
            """
            UPDATE agent_tasks
            SET status = 'cancelled', completed_at = now(),
                lease_expires_at = NULL, last_heartbeat_at = NULL,
                lease_id = NULL, claimed_by = NULL
            WHERE id = %s AND lease_id = %s AND status = 'running'
            RETURNING *
            """,
            (task["id"], lease_id),
        ).fetchone()
        if row is None:
            raise InvalidTaskStateError("Worker lost task lease during cancellation")
        self._append_audit(
            connection,
            correlation_id=row["correlation_id"],
            task_id=row["id"],
            actor_type="worker",
            actor_id=task["claimed_by"] or "foundation-worker",
            tool_name=row["kind"],
            action="task.cancelled",
            risk_level=row["risk_level"],
            approval_status="approved" if row["approved_by"] else "not_required",
            execution_status="cancelled",
        )
        connection.commit()
        return row

    def finalize_cancellation(self, task_id: UUID, lease_id: UUID) -> dict[str, Any]:
        with self.connect() as connection:
            task = connection.execute(
                "SELECT * FROM agent_tasks WHERE id = %s FOR UPDATE", (task_id,)
            ).fetchone()
            if task is None or task["cancellation_requested_at"] is None:
                raise InvalidTaskStateError("Task has no cancellation request")
            return self._finalize_cancellation(connection, task, lease_id)

    def fail_task(
        self, task_id: UUID, lease_id: UUID, code: str, message: str
    ) -> dict[str, Any]:
        with self.connect() as connection:
            task = connection.execute(
                "SELECT * FROM agent_tasks WHERE id = %s FOR UPDATE", (task_id,)
            ).fetchone()
            if (
                task is None
                or task["status"] != "running"
                or task["lease_id"] != lease_id
            ):
                raise InvalidTaskStateError("Worker no longer owns the task during failure")
            if task["cancellation_requested_at"] is not None:
                return self._finalize_cancellation(connection, task, lease_id)
            row = connection.execute(
                """
                UPDATE agent_tasks
                SET status = 'failed', error_code = %s, error_message = %s, completed_at = now(),
                    lease_expires_at = NULL, last_heartbeat_at = NULL,
                    lease_id = NULL, claimed_by = NULL
                WHERE id = %s AND lease_id = %s AND status = 'running'
                RETURNING *
                """,
                (code[:100], message[:1000], task_id, lease_id),
            ).fetchone()
            if row is None:
                raise InvalidTaskStateError("Worker lost the task lease during failure")
            self._append_audit(
                connection,
                correlation_id=row["correlation_id"],
                task_id=row["id"],
                actor_type="worker",
                actor_id=task["claimed_by"] or "worker",
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

    def recover_expired_tasks(
        self,
        limit: int = 50,
        retry_base_seconds: int = 5,
        retry_max_seconds: int = 300,
    ) -> dict[str, int]:
        recovered = 0
        exhausted = 0
        cancelled = 0
        with self.connect() as connection:
            tasks = connection.execute(
                """
                SELECT *
                FROM agent_tasks
                WHERE status = 'running' AND lease_expires_at <= now()
                ORDER BY lease_expires_at
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            for task in tasks:
                approval_status = "approved" if task["approved_by"] else "not_required"
                if task["cancellation_requested_at"] is not None:
                    row = connection.execute(
                        """
                        UPDATE agent_tasks
                        SET status = 'cancelled', completed_at = now(),
                            lease_expires_at = NULL, last_heartbeat_at = NULL,
                            lease_id = NULL, claimed_by = NULL
                        WHERE id = %s AND status = 'running'
                        RETURNING *
                        """,
                        (task["id"],),
                    ).fetchone()
                    if row is None:
                        continue
                    cancelled += 1
                    self._append_audit(
                        connection,
                        correlation_id=row["correlation_id"],
                        task_id=row["id"],
                        actor_type="dispatcher",
                        actor_id="outbox-dispatcher",
                        tool_name=row["kind"],
                        action="task.cancelled",
                        risk_level=row["risk_level"],
                        approval_status=approval_status,
                        execution_status="cancelled",
                    )
                    continue
                if task["attempt_count"] >= task["max_attempts"]:
                    row = connection.execute(
                        """
                        UPDATE agent_tasks
                        SET status = 'dead_lettered', completed_at = now(),
                            dead_lettered_at = now(),
                            lease_expires_at = NULL, last_heartbeat_at = NULL,
                            lease_id = NULL, claimed_by = NULL,
                            error_code = 'WORKER_LEASE_EXHAUSTED',
                            error_message = 'Worker lease expired and retry budget was exhausted'
                        WHERE id = %s AND status = 'running'
                        RETURNING *
                        """,
                        (task["id"],),
                    ).fetchone()
                    if row is None:
                        continue
                    exhausted += 1
                    self._append_audit(
                        connection,
                        correlation_id=row["correlation_id"],
                        task_id=row["id"],
                        actor_type="dispatcher",
                        actor_id="outbox-dispatcher",
                        tool_name=row["kind"],
                        action="task.dead_lettered",
                        risk_level=row["risk_level"],
                        approval_status=approval_status,
                        execution_status="dead_lettered",
                        error_code="WORKER_LEASE_EXHAUSTED",
                        error_message="Worker lease expired and retry budget was exhausted",
                    )
                    continue

                retry_delay = min(
                    retry_max_seconds,
                    retry_base_seconds * (2 ** max(task["attempt_count"] - 1, 0)),
                )
                row = connection.execute(
                    """
                    UPDATE agent_tasks
                        SET status = 'queued', started_at = NULL,
                        lease_expires_at = NULL, last_heartbeat_at = NULL,
                        lease_id = NULL, claimed_by = NULL,
                        next_attempt_at = now() + make_interval(secs => %s),
                        error_code = NULL, error_message = NULL
                    WHERE id = %s AND status = 'running'
                    RETURNING *
                    """,
                    (retry_delay, task["id"]),
                ).fetchone()
                if row is None:
                    continue
                recovered += 1
                self._append_audit(
                    connection,
                    correlation_id=row["correlation_id"],
                    task_id=row["id"],
                    actor_type="dispatcher",
                    actor_id="outbox-dispatcher",
                    tool_name=row["kind"],
                    action="task.recovered",
                    risk_level=row["risk_level"],
                    approval_status=approval_status,
                    execution_status="queued",
                    result_metadata={
                        "attempt_count": row["attempt_count"],
                        "retry_delay_seconds": retry_delay,
                    },
                )
                self._add_outbox(connection, row)
            connection.commit()
        return {"recovered": recovered, "exhausted": exhausted, "cancelled": cancelled}

    def pending_outbox(self, limit: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT id, task_id, correlation_id, topic, payload, attempt_count
                FROM task_outbox
                WHERE published_at IS NULL AND available_at <= now()
                ORDER BY available_at, created_at
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

    def mark_outbox_failed(
        self,
        event_id: int,
        message: str,
        retry_base_seconds: int = 5,
        retry_max_seconds: int = 300,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE task_outbox
                SET attempt_count = attempt_count + 1,
                    last_error = %s,
                    available_at = now() + make_interval(
                        secs => LEAST(%s, %s * power(2, LEAST(attempt_count, 10)))::int
                    )
                WHERE id = %s AND published_at IS NULL
                """,
                (message[:1000], retry_max_seconds, retry_base_seconds, event_id),
            )
            connection.commit()

    def status_counts(self) -> dict[str, int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT status, count(*)::int AS count FROM agent_tasks GROUP BY status"
            ).fetchall()
        return {row["status"]: row["count"] for row in rows}
