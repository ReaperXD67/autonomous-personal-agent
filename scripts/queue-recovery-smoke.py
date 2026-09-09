#!/usr/bin/env python3
"""Run inside the control-api container; exercise only an isolated synthetic schema."""

from __future__ import annotations

import os
from uuid import uuid4

import psycopg
from app.models import TaskCancellation, TaskCreate
from app.policy import RiskLevel
from app.store import Database, InvalidTaskStateError
from psycopg import sql
from psycopg.conninfo import make_conninfo


def main() -> None:
    source_dsn = os.environ["DATABASE_URL"]
    schema = f"queue_recovery_smoke_{uuid4().hex}"
    database = Database(make_conninfo(source_dsn, options=f"-csearch_path={schema},public"))
    with psycopg.connect(source_dsn) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        with database.connect() as connection:
            for table in (
                "agent_tasks",
                "task_outbox",
                "audit_events",
                "task_approvals",
                "external_actions",
            ):
                connection.execute(
                    sql.SQL("CREATE TABLE {} (LIKE {} INCLUDING ALL)").format(
                        sql.Identifier(schema, table), sql.Identifier("public", table)
                    )
                )
        task = database.create_task(
            TaskCreate(title="Synthetic lost ready signal", requested_by="queue-recovery-smoke")
        )
        approval_task = database.create_task(
            TaskCreate(
                title="Synthetic approval remains gated",
                requested_by="queue-recovery-smoke",
                risk_level=RiskLevel.HIGH,
            )
        )
        initial = database.pending_outbox(10)[0]
        database.mark_outbox_published(initial["id"], initial["generation"])
        assert database.recover_queued_tasks() == 0
        with database.connect() as connection:
            connection.execute(
                "UPDATE task_outbox SET published_at = now() - interval '2 minutes' "
                "WHERE task_id = %s",
                (task["id"],),
            )
        assert database.recover_queued_tasks() == 1
        assert database.recover_queued_tasks() == 0
        rearmed = database.pending_outbox(10)[0]
        assert rearmed["id"] == initial["id"]
        assert rearmed["generation"] == initial["generation"] + 1
        database.mark_outbox_published(initial["id"], initial["generation"])
        database.mark_outbox_failed(initial["id"], "Stale sender", generation=initial["generation"])
        assert database.pending_outbox(10) == [rearmed]
        assert database.get_task(approval_task["id"])["status"] == "pending_approval"

        database.mark_outbox_published(rearmed["id"], rearmed["generation"])
        with database.connect() as connection:
            connection.execute(
                "UPDATE task_outbox SET published_at = now() - interval '2 minutes' "
                "WHERE task_id = %s",
                (task["id"],),
            )
            connection.execute(
                "UPDATE agent_tasks SET next_attempt_at = now() + interval '1 day' WHERE id = %s",
                (task["id"],),
            )
        assert database.recover_queued_tasks() == 0
        with database.connect() as connection:
            connection.execute(
                "UPDATE agent_tasks SET next_attempt_at = now() WHERE id = %s", (task["id"],)
            )
        running = database.transition_to_running(task["id"], 30, "queue-recovery-smoke")
        assert running is not None
        assert database.transition_to_running(task["id"], 30, "duplicate-smoke") is None
        assert database.recover_queued_tasks() == 0
        with database.connect() as connection:
            connection.execute(
                "UPDATE agent_tasks SET lease_expires_at = now() - interval '1 second' "
                "WHERE id = %s",
                (task["id"],),
            )
        assert database.heartbeat_task(task["id"], running["lease_id"], 30) == "lost"
        try:
            database.fail_task(task["id"], running["lease_id"], "STALE_OWNER", "Synthetic failure")
        except InvalidTaskStateError:
            pass
        else:
            raise AssertionError("Expired owner persisted a failure")
        assert database.recover_expired_tasks()["recovered"] == 1
        with database.connect() as connection:
            cancelled = database._cancel_task_record(
                connection, task["id"], TaskCancellation(actor="queue-recovery-smoke")
            )
            assert cancelled["status"] == "cancelled"
            connection.rollback()
        assert database.get_task(task["id"])["status"] == "queued"
        assert database.cancel_task(
            task["id"], TaskCancellation(actor="queue-recovery-smoke")
        )["status"] == "cancelled"
        with database.connect() as connection:
            assert connection.execute("SELECT count(*) AS n FROM task_outbox").fetchone()["n"] == 0
        print("Queue recovery passed: replay, generation fences, due/approval/lease gates, rollback")
    finally:
        with psycopg.connect(source_dsn) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    main()
