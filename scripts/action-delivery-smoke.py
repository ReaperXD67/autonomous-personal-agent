#!/usr/bin/env python3
"""Exercise delivery guards in an isolated PostgreSQL schema; never open SMTP/browser."""

from __future__ import annotations

import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import psycopg
from app.action_models import EmailActionCreate
from app.action_store import ActionStore, ExternalActionNotFoundError, SideEffectGuardError
from app.email_pacing import EmailPacingPolicy
from app.models import ApprovalDecision, TaskCancellation
from psycopg import sql
from psycopg.conninfo import make_conninfo


def main() -> None:
    source_dsn = os.environ["DATABASE_URL"]
    schema = f"action_delivery_smoke_{uuid4().hex}"
    scoped_dsn = make_conninfo(source_dsn, options=f"-csearch_path={schema},public")
    database = ActionStore(scoped_dsn)
    with psycopg.connect(source_dsn) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    def action_task():
        action = database.create_email_action(
            EmailActionCreate(
                recipient="synthetic@example.test", subject=f"Synthetic {uuid4()}",
                body="Synthetic guard test. No SMTP or browser is opened.",
                actor="action-delivery-smoke",
            ), sender="synthetic-sender@example.test",
        )
        database.decide_task(action["task_id"], ApprovalDecision(
            decision="approved", actor="action-delivery-smoke",
        ))
        task = database.transition_to_running(action["task_id"], 120, "action-delivery-smoke")
        assert task is not None
        fingerprint = hashlib.sha256(f"synthetic:{action['id']}".encode()).hexdigest()
        return action, task, fingerprint

    def reject_boundary(task, fingerprint, *, lease_id=None):
        try:
            database.begin_side_effect(task["id"], fingerprint, lease_id or task["lease_id"])
        except SideEffectGuardError:
            pass
        else:
            raise AssertionError("Unsafe synthetic side-effect boundary was accepted")
        with database.connect() as connection:
            assert connection.execute(
                "SELECT count(*) AS n FROM side_effect_receipts WHERE task_id = %s",
                (task["id"],),
            ).fetchone()["n"] == 0

    try:
        with database.connect() as connection:
            for table in (
                "agent_tasks", "task_outbox", "audit_events", "task_approvals",
                "external_actions", "side_effect_receipts", "outbound_email_schedule",
            ):
                connection.execute(sql.SQL("CREATE TABLE {} (LIKE {} INCLUDING ALL)").format(
                    sql.Identifier(schema, table), sql.Identifier("public", table),
                ))

        paced = ActionStore(
            scoped_dsn,
            email_pacing_policy=EmailPacingPolicy(60, 300, 3, 12, 0),
        )
        paced_actions = [
            paced.create_email_action(
                EmailActionCreate(
                    recipient="paced@example.test",
                    subject=f"Paced synthetic {index}",
                    body="Synthetic pacing proof. No email is sent.",
                    actor="action-delivery-smoke",
                ),
                sender="synthetic-sender@example.test",
            )
            for index in range(2)
        ]
        with ThreadPoolExecutor(max_workers=2) as executor:
            decisions = [
                executor.submit(
                    paced.decide_task,
                    action["task_id"],
                    ApprovalDecision(decision="approved", actor="action-delivery-smoke"),
                )
                for action in paced_actions
            ]
            for decision in decisions:
                decision.result(timeout=10)
        with paced.connect() as connection:
            schedules = connection.execute(
                """
                SELECT task_id, scheduled_for, status
                FROM outbound_email_schedule ORDER BY scheduled_for
                """
            ).fetchall()
        assert len(schedules) == 2
        assert (
            schedules[1]["scheduled_for"] - schedules[0]["scheduled_for"]
            >= timedelta(seconds=300)
        )
        due_action = next(
            action
            for action in paced_actions
            if action["task_id"] == schedules[0]["task_id"]
        )
        due_task = paced.transition_to_running(
            due_action["task_id"], 120, "action-delivery-smoke"
        )
        assert due_task is not None
        paced_fingerprint = hashlib.sha256(
            f"paced:{due_action['id']}".encode()
        ).hexdigest()
        paced.begin_side_effect(
            due_task["id"], paced_fingerprint, due_task["lease_id"]
        )
        paced.complete_side_effect(
            due_task["id"], paced_fingerprint, "synthetic-paced-reference"
        )
        future_action = next(
            action
            for action in paced_actions
            if action["task_id"] == schedules[1]["task_id"]
        )
        paced.cancel_task(
            future_action["task_id"], TaskCancellation(actor="action-delivery-smoke")
        )
        with paced.connect() as connection:
            assert connection.execute(
                "SELECT count(*) AS n FROM outbound_email_schedule WHERE status = 'accepted'"
            ).fetchone()["n"] == 1
            assert connection.execute(
                "SELECT count(*) AS n FROM outbound_email_schedule WHERE status = 'skipped'"
            ).fetchone()["n"] == 1

        action, task, fingerprint = action_task()
        reject_boundary(task, fingerprint, lease_id=uuid4())
        try:
            database.fail_external_action(task["id"], "Synthetic stale worker", uuid4())
        except SideEffectGuardError:
            pass
        else:
            raise AssertionError("Stale worker changed action failure state")
        assert database.get_external_action(action["id"])["status"] == "queued"
        assert "private_context" not in database.get_external_action(action["id"])
        try:
            database.get_external_action(uuid4())
        except ExternalActionNotFoundError:
            pass
        else:
            raise AssertionError("Unknown action lookup did not fail")
        database.cancel_task(task["id"], TaskCancellation(actor="action-delivery-smoke"))
        reject_boundary(task, fingerprint)

        for column in ("public_context", "private_context"):
            action, task, fingerprint = action_task()
            with database.connect() as connection:
                connection.execute(sql.SQL(
                    "UPDATE external_actions SET {} = {} || "
                    "'{{\"body\":\"Changed synthetic content\"}}'::jsonb WHERE id = %s"
                ).format(sql.Identifier(column), sql.Identifier(column)), (action["id"],))
            reject_boundary(task, fingerprint)

        for table, field in (("agent_tasks", "lease_expires_at"),
                             ("external_actions", "expires_at")):
            action, task, fingerprint = action_task()
            # The boundary begins before expiry but waits for the row lock past expiry.
            with ThreadPoolExecutor(max_workers=1) as executor:
                with database.connect() as blocker:
                    blocker.execute(sql.SQL(
                        "UPDATE {} SET {} = clock_timestamp() + interval '1 second' WHERE id = %s"
                    ).format(sql.Identifier(table), sql.Identifier(field)),
                        (task["id"] if table == "agent_tasks" else action["id"],))
                    future = executor.submit(reject_boundary, task, fingerprint)
                    time.sleep(1.2)
                    blocker.commit()
                future.result(timeout=10)

        action, task, fingerprint = action_task()
        database.begin_side_effect(task["id"], fingerprint, task["lease_id"])
        try:
            database.complete_side_effect(task["id"], "0" * 64, "synthetic-reference")
        except SideEffectGuardError:
            pass
        else:
            raise AssertionError("Missing receipt allowed false success")
        assert database.get_external_action(action["id"])["status"] == "executing"
        database.complete_side_effect(task["id"], fingerprint, "synthetic-reference")
        with database.connect() as connection:
            connection.execute(
                "UPDATE agent_tasks SET lease_expires_at = clock_timestamp() - interval '1 second' "
                "WHERE id = %s", (task["id"],),
            )
        assert database.fail_external_action(
            task["id"], "Synthetic failure after durable acceptance", task["lease_id"],
        ) == "succeeded"
        assert database.get_external_action(action["id"])["status"] == "succeeded"
        with database.connect() as connection:
            receipt = connection.execute(
                "SELECT status, external_reference FROM side_effect_receipts WHERE task_id = %s",
                (task["id"],),
            ).fetchone()
            assert receipt == {"status": "succeeded", "external_reference": "synthetic-reference"}

        action, task, fingerprint = action_task()
        assert database.fail_external_action(
            task["id"], "Synthetic failure before boundary", task["lease_id"],
        ) == "failed"
        action, task, fingerprint = action_task()
        database.begin_side_effect(task["id"], fingerprint, task["lease_id"])
        assert database.fail_external_action(
            task["id"], "Synthetic uncertainty after boundary", task["lease_id"],
        ) == "ambiguous"
        print("Action delivery guards passed: atomic pacing, lease/cancellation/hash fences, "
              "expiry after locks, receipt rollback, durable acceptance, failure semantics, "
              "public lookup; no SMTP")
    finally:
        with psycopg.connect(source_dsn) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    main()
