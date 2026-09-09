"""Exercise durable workflow transactions in an empty, disposable PostgreSQL database.

The PowerShell launcher supplies migration sources through stdin. No Redis queue,
inference provider, external tool, production workflow, or production task is used.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import psycopg
from app.models import ApprovalDecision, TaskCancellation
from app.workflow_models import WorkflowCreate
from app.workflow_store import WorkflowConflictError, WorkflowStore
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def step(key, *, dependencies=(), risk="low", expected=None):
    return {
        "key": key,
        "title": f"Synthetic {key}",
        "kind": "foundation.echo",
        "payload": {"message": key},
        "depends_on": list(dependencies),
        "risk_level": risk,
        "expect_output": expected or {},
    }


def plan(steps, **options):
    return WorkflowCreate.model_validate({
        "title": "Disposable workflow integration probe",
        "requested_by": "workflow-smoke",
        "steps": steps,
        **options,
    })


def view(store, workflow):
    result = store.get_workflow(workflow["id"])
    return result, {item["key"]: item for item in result["steps"]}


def finish(store, task_id, output=None):
    claim = store.transition_to_running(task_id, 60, "workflow-smoke")
    check(claim is not None, "Synthetic task could not acquire its lease")
    return store.complete_task(task_id, claim["lease_id"], output or {"ok": True})


def count(store, table, workflow_id=None):
    with store.connect() as connection:
        query = sql.SQL("SELECT count(*) AS value FROM {}").format(sql.Identifier(table))
        params = ()
        if workflow_id is not None:
            query += sql.SQL(" WHERE workflow_id = %s")
            params = (workflow_id,)
        return connection.execute(query, params).fetchone()["value"]


def outbox_count(store, task_id):
    with store.connect() as connection:
        return connection.execute(
            "SELECT count(*) AS value FROM task_outbox WHERE task_id = %s", (task_id,),
        ).fetchone()["value"]


def expire(store, workflow):
    with store.connect() as connection:
        connection.execute(
            "UPDATE agent_workflows SET deadline_at = now() - interval '1 second' WHERE id = %s",
            (workflow["id"],),
        )


def exercise(dsn):
    store = WorkflowStore(dsn)
    passed = []

    # Deliberately submit a non-topological fork/join graph. A fresh store models
    # a process restart while child state remains solely in PostgreSQL.
    dag = store.create_workflow(plan([
        step("join", dependencies=("left", "right")),
        step("left", dependencies=("seed",)),
        step("right", dependencies=("seed",)),
        step("seed", expected={"ready": True}),
    ], max_parallel=2))
    store.reconcile_workflows()
    _, steps = view(store, dag)
    check(steps["seed"]["task_status"] == "queued", "Root was not queued")
    check(all(steps[key]["task_id"] is None for key in ("left", "right", "join")),
          "A dependent step ran before its prerequisite")
    finish(store, steps["seed"]["task_id"], {"ready": True})
    store = WorkflowStore(dsn)
    store.reconcile_workflows()
    _, steps = view(store, dag)
    check(all(steps[key]["task_status"] == "queued" for key in ("left", "right")),
          "Fork did not dispatch its independent branches")
    check(steps["join"]["task_id"] is None, "Join dispatched before both branches")
    finish(store, steps["left"]["task_id"])
    store.reconcile_workflows()
    _, steps = view(store, dag)
    check(steps["join"]["task_id"] is None, "Join dispatched after only one branch")
    finish(store, steps["right"]["task_id"])
    store.reconcile_workflows()
    _, steps = view(store, dag)
    finish(store, steps["join"]["task_id"])
    store.reconcile_workflows()
    check(view(store, dag)[0]["status"] == "succeeded", "Completed DAG did not succeed")
    passed.append("dependency ordering, fork/join, PostgreSQL restart recovery")

    capped = store.create_workflow(plan([step("a"), step("b"), step("c")], max_parallel=1))
    for key in ("a", "b", "c"):
        store.reconcile_workflows()
        _, steps = view(store, capped)
        check(sum(item["status"] == "dispatched" for item in steps.values()) == 1,
              "Parallelism cap was exceeded")
        check(steps[key]["task_status"] == "queued", "Ready order was not stable")
        finish(store, steps[key]["task_id"])
    store.reconcile_workflows()
    check(view(store, capped)[0]["status"] == "succeeded", "Serial workflow did not finish")
    passed.append("parallelism cap")

    evidence = store.create_workflow(plan([
        step("grandchild", dependencies=("child",)),
        step("child", dependencies=("source",)),
        step("source", expected={"verified": True}),
        step("independent"),
    ], max_parallel=2))
    store.reconcile_workflows()
    _, steps = view(store, evidence)
    finish(store, steps["source"]["task_id"], {"verified": False})
    finish(store, steps["independent"]["task_id"])
    store.reconcile_workflows()
    result, steps = view(store, evidence)
    check(result["status"] == "failed", "Failed output evidence did not fail its workflow")
    check(steps["source"]["error_code"] == "OUTPUT_CHECK_FAILED", "Output failure was not explained")
    check(all(steps[key]["status"] == "skipped" and steps[key]["task_id"] is None
              for key in ("child", "grandchild")), "Failed evidence allowed descendant execution")
    check(steps["independent"]["status"] == "succeeded", "Independent branch was incorrectly skipped")
    passed.append("output evidence failure and transitive dependency suppression")

    for decision in ("approved", "rejected"):
        approval = store.create_workflow(plan([
            step("review", risk="high"), step("after", dependencies=("review",)),
        ]))
        store.reconcile_workflows()
        _, steps = view(store, approval)
        task_id = steps["review"]["task_id"]
        check(steps["review"]["task_status"] == "pending_approval", "Elevated risk bypassed approval")
        check(outbox_count(store, task_id) == 0, "Unapproved task reached the outbox")
        check(store.transition_to_running(task_id, 60, "workflow-smoke") is None,
              "An unapproved task acquired a worker lease")
        store.decide_task(task_id, ApprovalDecision(decision=decision, actor="workflow-smoke"))
        check(outbox_count(store, task_id) == (1 if decision == "approved" else 0),
              "Approval outbox behavior was incorrect")
        if decision == "approved":
            finish(store, task_id)
            store.reconcile_workflows()
            _, steps = view(store, approval)
            finish(store, steps["after"]["task_id"])
        store.reconcile_workflows()
        result, steps = view(store, approval)
        check(result["status"] == ("succeeded" if decision == "approved" else "failed"),
              "Workflow did not respect the approval decision")
        if decision == "rejected":
            check(steps["after"]["task_id"] is None, "Rejected step allowed a dependent task")
    passed.append("policy approval, rejected approval, and approval-only outbox publication")

    request = plan([step("only")], idempotency_key=f"workflow-smoke-{uuid4().hex}")
    first = store.create_workflow(request)
    check(store.create_workflow(request)["id"] == first["id"], "Identical retry duplicated workflow")
    mismatch = request.model_copy(update={"title": "Different synthetic plan"})
    try:
        store.create_workflow(mismatch)
    except WorkflowConflictError:
        pass
    else:
        raise AssertionError("A changed plan reused the same idempotency key")
    store.cancel_workflow(first["id"], TaskCancellation(actor="workflow-smoke"))
    passed.append("idempotent retry and changed-plan conflict")

    cancellation = TaskCancellation(actor="workflow-smoke", reason="Synthetic cancellation")
    queued = store.create_workflow(plan([
        step("queued"), step("approval", risk="high"), step("not_dispatched"),
    ], max_parallel=2))
    store.reconcile_workflows()
    result = store.cancel_workflow(queued["id"], cancellation)
    check(result["status"] == "cancelled", "Queued/pending cancellation did not complete")
    check(all(item["status"] == "cancelled" for item in result["steps"]),
          "Cancellation left unfinished steps")
    for item in result["steps"]:
        if item["task_id"] is not None:
            check(store.get_task(item["task_id"])["status"] == "cancelled", "Child was not cancelled")
            check(outbox_count(store, item["task_id"]) == 0, "Cancelled child retained queue intent")
    passed.append("queued, approval-pending, and undispatched cancellation")

    running = store.create_workflow(plan([step("running"), step("after", dependencies=("running",))]))
    store.reconcile_workflows()
    _, steps = view(store, running)
    claim = store.transition_to_running(steps["running"]["task_id"], 60, "workflow-smoke")
    result = store.cancel_workflow(running["id"], cancellation)
    check(result["status"] == "cancelling", "Running cancellation did not wait for worker acknowledgement")
    check(store.heartbeat_task(claim["id"], claim["lease_id"], 60) == "cancel_requested",
          "Worker did not observe cancellation")
    check(store.complete_task(claim["id"], claim["lease_id"], {"ok": True})["status"] == "cancelled",
          "Late worker success escaped cancellation")
    store.reconcile_workflows()
    check(view(store, running)[0]["status"] == "cancelled", "Acknowledged cancellation did not finish")
    passed.append("running cancellation and late-success fencing")

    deadline = store.create_workflow(plan([step("expired")]))
    expire(store, deadline)
    store.reconcile_workflows()
    result, steps = view(store, deadline)
    check(result["status"] == "timed_out" and steps["expired"]["task_id"] is None,
          "An expired workflow dispatched a child")
    deadline_running = store.create_workflow(plan([step("active")]))
    store.reconcile_workflows()
    _, steps = view(store, deadline_running)
    claim = store.transition_to_running(steps["active"]["task_id"], 60, "workflow-smoke")
    expire(store, deadline_running)
    store.reconcile_workflows()
    check(view(store, deadline_running)[0]["status"] == "cancelling", "Deadline ignored a running child")
    store.finalize_cancellation(claim["id"], claim["lease_id"])
    store.reconcile_workflows()
    check(view(store, deadline_running)[0]["status"] == "timed_out", "Deadline cause was lost")
    passed.append("deadline before dispatch and during a worker lease")

    completed_early = store.create_workflow(plan([step("early")]))
    store.reconcile_workflows()
    _, steps = view(store, completed_early)
    early_task_id = steps["early"]["task_id"]
    finish(store, early_task_id)
    # Narrow only this disposable fixture's deadline to immediately after its
    # real completion, proving delayed reconciliation without a 60-second sleep.
    with store.connect() as connection:
        connection.execute(
            """UPDATE agent_workflows SET deadline_at =
               (SELECT completed_at FROM agent_tasks WHERE id = %s) + interval '1 microsecond'
               WHERE id = %s""", (early_task_id, completed_early["id"]),
        )
        check(connection.execute(
            "SELECT deadline_at < clock_timestamp() AS expired FROM agent_workflows WHERE id = %s",
            (completed_early["id"],),
        ).fetchone()["expired"], "Early-completion fixture was not reconciled after its deadline")
    store.reconcile_workflows()
    check(view(store, completed_early)[0]["status"] == "succeeded",
          "Delayed reconciliation incorrectly timed out an on-time completion")

    completed_late = store.create_workflow(plan([step("late")]))
    store.reconcile_workflows()
    _, steps = view(store, completed_late)
    expire(store, completed_late)
    finish(store, steps["late"]["task_id"])
    store.reconcile_workflows()
    result, steps = view(store, completed_late)
    check(result["status"] == "timed_out" and steps["late"]["task_status"] == "succeeded",
          "Late task completion incorrectly let the workflow succeed")
    passed.append("on-time completion with delayed reconciliation and late terminal completion")

    concurrent = store.create_workflow(plan([step(f"step{index}") for index in range(4)], max_parallel=4))
    tasks_before_dispatch = count(store, "agent_tasks")
    outbox_before_dispatch = count(store, "task_outbox")
    barrier = Barrier(6)

    def reconcile_concurrently(_):
        peer = WorkflowStore(dsn)
        barrier.wait(timeout=10)
        return peer.reconcile_workflows()

    with ThreadPoolExecutor(max_workers=6) as executor:
        list(executor.map(reconcile_concurrently, range(6)))
    _, steps = view(store, concurrent)
    bindings = [item["task_id"] for item in steps.values()]
    check(None not in bindings and len(set(bindings)) == 4, "Concurrent dispatch duplicated or missed children")
    check(count(store, "agent_tasks") - tasks_before_dispatch == 4
          and count(store, "task_outbox") - outbox_before_dispatch == 4,
          "Concurrent dispatch left unbound duplicate tasks or outbox rows")
    with store.connect() as connection:
        total = connection.execute(
            """SELECT count(*) AS value FROM task_outbox o JOIN workflow_steps s ON s.task_id = o.task_id
               WHERE s.workflow_id = %s""", (concurrent["id"],),
        ).fetchone()["value"]
    check(total == 4, "Concurrent dispatch duplicated outbox intent")
    store.cancel_workflow(concurrent["id"], cancellation)
    passed.append("six concurrent reconcilers without duplicate children or outbox rows")

    class FailingDispatchStore(WorkflowStore):
        def _create_task_record(self, connection, request):
            record = super()._create_task_record(connection, request)
            if request.payload["message"] == "fail_second":
                raise RuntimeError("INJECTED_WORKFLOW_DISPATCH_FAILURE")
            return record

    rollback = store.create_workflow(plan([step("first"), step("fail_second")]))
    tables = ("agent_tasks", "task_outbox", "audit_events")
    before = {table: count(store, table) for table in tables}
    try:
        FailingDispatchStore(dsn).reconcile_workflows()
    except RuntimeError as error:
        check(str(error) == "INJECTED_WORKFLOW_DISPATCH_FAILURE", "Unexpected dispatch exception")
    else:
        raise AssertionError("Injected dispatch failure was not exercised")
    check(before == {table: count(store, table) for table in tables},
          "Failed dispatch committed partial tasks, outbox rows, or audit events")
    _, steps = view(store, rollback)
    check(all(item["status"] == "pending" and item["task_id"] is None for item in steps.values()),
          "Failed dispatch committed partial step bindings")
    store.reconcile_workflows()
    _, steps = view(store, rollback)
    check(all(item["task_id"] is not None for item in steps.values()), "Rollback recovery did not redispatch")
    store.cancel_workflow(rollback["id"], cancellation)
    passed.append("atomic task/outbox/audit/step rollback and subsequent recovery")

    retired = store.create_workflow(plan([
        step("grandchild", dependencies=("child",)),
        step("child", dependencies=("retired",)),
        step("retired"),
    ]))
    unaffected = store.create_workflow(plan([step("valid")]))
    # Simulate a persisted capability retired by a later policy version. This
    # mutation is confined to the empty disposable probe database.
    with store.connect() as connection:
        connection.execute(
            "UPDATE workflow_steps SET kind = %s WHERE workflow_id = %s AND key = %s",
            ("retired.synthetic_capability", retired["id"], "retired"),
        )
    tasks_before_quarantine = count(store, "agent_tasks")
    store.reconcile_workflows()
    _, steps = view(store, retired)
    check(steps["retired"]["status"] == "failed"
          and steps["retired"]["error_code"] == "STEP_POLICY_REJECTED"
          and steps["retired"]["task_id"] is None,
          "Invalid persisted capability was not quarantined before task creation")
    _, valid_steps = view(store, unaffected)
    check(valid_steps["valid"]["task_status"] == "queued", "Invalid plan blocked an unrelated workflow")
    check(count(store, "agent_tasks") - tasks_before_quarantine == 1,
          "Quarantined workflow created an executable child")
    finish(store, valid_steps["valid"]["task_id"])
    store.reconcile_workflows()
    result, steps = view(store, retired)
    check(result["status"] == "failed"
          and all(steps[key]["status"] == "skipped" and steps[key]["task_id"] is None
                  for key in ("child", "grandchild")),
          "Quarantined capability did not suppress its transitive descendants")
    check(view(store, unaffected)[0]["status"] == "succeeded", "Unrelated valid workflow did not complete")
    passed.append("retired capability quarantine, descendant suppression, and unrelated workflow continuity")

    with store.connect() as connection:
        unfinished = connection.execute(
            "SELECT count(*) AS value FROM agent_workflows WHERE status IN ('running', 'cancelling')",
        ).fetchone()["value"]
        orphaned = connection.execute(
            """SELECT count(*) AS value FROM audit_events a LEFT JOIN agent_tasks t ON t.id = a.task_id
               WHERE a.task_id IS NOT NULL AND t.id IS NULL""",
        ).fetchone()["value"]
    check(unfinished == 0 and orphaned == 0, "Probe left unfinished workflows or orphaned audit events")
    return passed


def main():
    # The launcher provides source text only. Credentials remain inside the
    # control-api container and are never included in command arguments/output.
    migrations = globals().get("MIGRATIONS")
    if migrations is None:
        migration_root = Path(__file__).resolve().parents[1] / "config" / "postgres" / "init"
        migrations = [path.read_text(encoding="utf-8") for path in sorted(migration_root.glob("*.sql"))]
    check(bool(migrations), "No migration sources were provided")
    source_dsn = os.environ["DATABASE_URL"]
    source_database = conninfo_to_dict(source_dsn).get("dbname")
    probe_database = f"workflow_probe_{uuid4().hex}"
    check(re.fullmatch(r"workflow_probe_[0-9a-f]{32}", probe_database) is not None
          and probe_database != source_database, "Unsafe disposable database name")
    maintenance_dsn = make_conninfo(source_dsn, dbname="postgres", connect_timeout=10)
    probe_dsn = make_conninfo(source_dsn, dbname=probe_database, connect_timeout=10)
    created = False
    try:
        with psycopg.connect(maintenance_dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                sql.Identifier(probe_database),
            ))
            created = True
        with psycopg.connect(probe_dsn, autocommit=True) as connection:
            for migration in migrations:
                connection.execute(migration)
        results = exercise(probe_dsn)
    finally:
        if created:
            # Drop only the exact random database created by this invocation.
            with psycopg.connect(maintenance_dsn, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(probe_database)))
    print(f"Workflow PostgreSQL smoke passed: {len(results)} scenario groups; disposable database removed")
    for result in results:
        print(f"  PASS {result}")


if __name__ == "__main__":
    main()
