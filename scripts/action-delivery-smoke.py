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
from app.action_store import (
    ActionStore, EmailPacingDeferred, ExternalActionNotFoundError, SideEffectGuardError,
)
from app.email_pacing import EmailPacingPolicy
from app.models import ApprovalDecision, TaskCancellation
from psycopg import sql
from psycopg.conninfo import make_conninfo


def overdue_pacing_proof(paced, scoped_dsn):
    # Age only the synthetic earlier smoke receipt, then emulate several approved
    # reservations becoming overdue together after a worker outage.
    with paced.connect() as connection:
        connection.execute("UPDATE side_effect_receipts SET started_at=clock_timestamp()-"
                           "interval '25 hours',completed_at=clock_timestamp()-interval '25 hours'")
        connection.execute("UPDATE outbound_email_schedule SET scheduled_for=clock_timestamp()-"
                           "interval '25 hours',completed_at=clock_timestamp()-interval '25 hours'")
    actions = [paced.create_email_action(EmailActionCreate(
        recipient="backlog@example.test", subject=f"Overdue synthetic {uuid4()}",
        body="Synthetic overdue queue recovery; no SMTP is opened.", actor="action-delivery-smoke",
        approval_window_minutes=1440,
    ), sender="synthetic-sender@example.test") for _ in range(4)]
    for action in actions:
        paced.decide_task(action["task_id"], ApprovalDecision(
            decision="approved", actor="action-delivery-smoke",
        ))
    with paced.connect() as connection:
        connection.execute("UPDATE outbound_email_schedule SET scheduled_for=clock_timestamp()-"
                           "interval '8 hours' WHERE action_id=ANY(%s)",
                           ([action["id"] for action in actions],))
        connection.execute("UPDATE agent_tasks SET next_attempt_at=clock_timestamp()-"
                           "interval '8 hours' WHERE id=ANY(%s)",
                           ([action["task_id"] for action in actions],))
    # A looser current configuration cannot relax the packet's frozen300s domain gap.
    executing = ActionStore(scoped_dsn, email_pacing_policy=EmailPacingPolicy(60, 60, 10, 50, 0))
    tasks = [executing.transition_to_running(action["task_id"], 120, "action-delivery-smoke")
             for action in actions]
    fingerprints = [hashlib.sha256(f"overdue:{action['id']}".encode()).hexdigest()
                    for action in actions]
    with executing.connect() as connection:
        before = connection.execute(
            "SELECT id,context_hash,public_context,private_context,expires_at "
            "FROM external_actions WHERE id=ANY(%s) ORDER BY id",
            ([action["id"] for action in actions],),
        ).fetchall()

    def attempt(index):
        try:
            executing.begin_side_effect(tasks[index]["id"], fingerprints[index],
                                        tasks[index]["lease_id"])
            return "executing", index
        except EmailPacingDeferred:
            return "deferred", index

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, (0, 1)))
    assert sorted(state for state, _ in outcomes) == ["deferred", "executing"]
    winner = next(index for state, index in outcomes if state == "executing")
    deferred = next(index for state, index in outcomes if state == "deferred")
    with executing.connect() as connection:
        # An unresolved send stays conservative even when its start appears old.
        connection.execute("UPDATE side_effect_receipts SET started_at=clock_timestamp()-"
                           "interval '25 hours' WHERE task_id=%s", (tasks[winner]["id"],))
    assert attempt(2)[0] == "deferred"
    executing.complete_side_effect(tasks[winner]["id"], fingerprints[winner], "synthetic-backlog")
    with executing.connect() as connection:
        actual = connection.execute("SELECT completed_at FROM side_effect_receipts WHERE task_id=%s",
                                    (tasks[winner]["id"],)).fetchone()["completed_at"]
        task = connection.execute("SELECT * FROM agent_tasks WHERE id=%s",
                                  (tasks[deferred]["id"],)).fetchone()
        schedule = connection.execute("SELECT * FROM outbound_email_schedule WHERE task_id=%s",
                                      (task["id"],)).fetchone()
        outbox = connection.execute("SELECT * FROM task_outbox WHERE task_id=%s",
                                    (task["id"],)).fetchone()
        assert task["status"] == "queued" and task["attempt_count"] == 0
        assert task["lease_id"] is None and task["lease_expires_at"] is None
        assert task["error_code"] is None and task["completed_at"] is None
        assert schedule["status"] == "scheduled"
        assert schedule["scheduled_for"] == task["next_attempt_at"] == outbox["available_at"]
        assert outbox["published_at"] is None and outbox["generation"] >= 2
        assert not connection.execute("SELECT 1 FROM side_effect_receipts WHERE task_id=%s",
                                      (task["id"],)).fetchone()
        assert connection.execute(
            "SELECT id,context_hash,public_context,private_context,expires_at "
            "FROM external_actions WHERE id=ANY(%s) ORDER BY id",
            ([action["id"] for action in actions],),
        ).fetchall() == before
        # Its old reservation and old receipt start cannot outweigh real acceptance.
        connection.execute("UPDATE outbound_email_schedule SET scheduled_for=clock_timestamp()-"
                           "interval '8 hours' WHERE task_id=%s", (task["id"],))
        connection.execute("UPDATE agent_tasks SET next_attempt_at=clock_timestamp()-"
                           "interval '8 hours' WHERE id=%s", (task["id"],))
    task = executing.transition_to_running(tasks[deferred]["id"], 120, "action-delivery-smoke")
    try:
        executing.begin_side_effect(task["id"], fingerprints[deferred], task["lease_id"])
    except EmailPacingDeferred as error:
        assert error.next_attempt_at >= actual + timedelta(seconds=300)
    else:
        raise AssertionError("Old reservation bypassed actual frozen-domain acceptance spacing")
    # Newly approved slots also account for the real acceptance, not its old slot.
    fresh = executing.create_email_action(EmailActionCreate(
        recipient="new@example.test", subject=f"Actual-aware {uuid4()}",
        body="Synthetic actual-aware approval.", actor="action-delivery-smoke",
        approval_window_minutes=1440,
    ), sender="synthetic-sender@example.test")
    executing.decide_task(fresh["task_id"], ApprovalDecision(
        decision="approved", actor="action-delivery-smoke",
    ))
    with executing.connect() as connection:
        assert connection.execute("SELECT scheduled_for FROM outbound_email_schedule WHERE action_id=%s",
                                  (fresh["id"],)).fetchone()["scheduled_for"] > actual
        # An ambiguous result still consumes its completion-time gap and rolling budget.
        connection.execute("UPDATE side_effect_receipts SET status='ambiguous' WHERE task_id=%s",
                           (tasks[winner]["id"],))
        connection.execute("UPDATE outbound_email_schedule SET status='ambiguous' WHERE task_id=%s",
                           (tasks[winner]["id"],))
        connection.execute("UPDATE external_actions SET expires_at=clock_timestamp()+"
                           "interval '2 seconds' WHERE id=%s", (actions[3]["id"],))
        expiry_before = connection.execute("SELECT expires_at FROM external_actions WHERE id=%s",
                                           (actions[3]["id"],)).fetchone()["expires_at"]
    try:
        executing.begin_side_effect(tasks[3]["id"], fingerprints[3], tasks[3]["lease_id"])
    except SideEffectGuardError as error:
        assert "no send window before the approval expires" in str(error)
    else:
        raise AssertionError("Pacing extended an approval without a safe remaining send window")
    with executing.connect() as connection:
        assert connection.execute("SELECT expires_at FROM external_actions WHERE id=%s",
                                  (actions[3]["id"],)).fetchone()["expires_at"] == expiry_before
        assert not connection.execute("SELECT 1 FROM side_effect_receipts WHERE task_id=%s",
                                      (tasks[3]["id"],)).fetchone()
    for table, field, fragment in (
        ("agent_tasks", "lease_expires_at", "task lease has expired"),
        ("external_actions", "expires_at", "action has expired"),
    ):
        waiting = executing.create_email_action(EmailActionCreate(
            recipient="waiting@example.test", subject=f"Global wait {uuid4()}",
            body="Synthetic global-lock expiry; no SMTP.", actor="action-delivery-smoke",
            approval_window_minutes=1440,
        ), sender="synthetic-sender@example.test")
        executing.decide_task(waiting["task_id"], ApprovalDecision(
            decision="approved", actor="action-delivery-smoke",
        ))
        with executing.connect() as connection:
            connection.execute("UPDATE outbound_email_schedule SET scheduled_for=clock_timestamp()-"
                               "interval '1 hour' WHERE action_id=%s", (waiting["id"],))
            connection.execute("UPDATE agent_tasks SET next_attempt_at=clock_timestamp()-"
                               "interval '1 hour' WHERE id=%s", (waiting["task_id"],))
        claimed = executing.transition_to_running(waiting["task_id"], 120, "action-delivery-smoke")
        with ThreadPoolExecutor(max_workers=1) as executor:
            with executing.connect() as blocker:
                blocker.execute(sql.SQL(
                    "UPDATE {} SET {}=clock_timestamp()+interval '0.4 seconds' WHERE id=%s",
                ).format(sql.Identifier(table), sql.Identifier(field)),
                    (claimed["id"] if table == "agent_tasks" else waiting["id"],))
                blocker.commit()
                blocker.execute("SELECT pg_advisory_xact_lock(%s,%s)", (1212502605, 1))
                future = executor.submit(executing.begin_side_effect, claimed["id"],
                                         uuid4().hex * 2, claimed["lease_id"])
                time.sleep(0.6)
                blocker.commit()
            try:
                future.result(timeout=10)
            except SideEffectGuardError as error:
                assert fragment in str(error)
            else:
                raise AssertionError("Global pacing lock wait bypassed expiry")
        with executing.connect() as connection:
            assert not connection.execute("SELECT 1 FROM side_effect_receipts WHERE task_id=%s",
                                          (claimed["id"],)).fetchone()


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

        overdue_pacing_proof(paced, scoped_dsn)

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
        print("Action delivery guards passed: atomic approval and actual-receipt pacing, "
              "overdue recovery/concurrent send deferral without retry consumption, "
              "unresolved/accepted/ambiguous boundaries, frozen limits and no-slot expiry, "
              "lease/cancellation/hash fences, "
              "expiry after locks, receipt rollback, durable acceptance, failure semantics, "
              "public lookup; no SMTP")
    finally:
        with psycopg.connect(source_dsn) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    main()
