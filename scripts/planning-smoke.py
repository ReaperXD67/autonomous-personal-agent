#!/usr/bin/env python3
"""Prove planner transactions, or use --live for an accounted local-API model proof."""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

import psycopg
from app.models import TaskCancellation, TaskCreate
from app.planning import execute_planning_task
from app.planning_models import ModelPlanChoice, PlanAdopt, PlanCreate
from app.planning_store import PlanConflictError, PlanContextError, PlanningStore
from app.settings import get_settings
from app.store import InvalidTaskStateError
from app.worker import execute_foundation_task
from psycopg import sql
from psycopg.conninfo import make_conninfo


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def expect_error(error_type, operation):
    try:
        operation()
    except error_type:
        return
    raise AssertionError(f"Expected {error_type.__name__}")


def exercise(dsn):
    store = PlanningStore(dsn)
    request = PlanCreate(
        goal="Synthetic workflow verification", requested_by="planner-smoke", mode="demo",
        idempotency_key=f"planner-smoke-{uuid4()}",
    )
    plan = store.create_plan(request)
    check(store.create_plan(request)["id"] == plan["id"], "Goal idempotency did not hold")
    expect_error(PlanConflictError, lambda: store.create_plan(
        request.model_copy(update={"goal": "Different synthetic goal"})
    ))
    expect_error(PlanContextError, lambda: store.create_plan(PlanCreate(
        goal="Unknown context", requested_by="planner-smoke", profile_id=uuid4(),
    )))
    running = store.transition_to_running(plan["task_id"], 120, "planner-smoke")
    output = execute_planning_task(running, store, get_settings())
    check(output["source"] == "template", "Demo did not identify its template source")
    check(store.get_plan(plan["id"])["status"] == "queued", "Unfinished task became adoptable")
    duplicate_output = execute_planning_task(running, store, get_settings())
    check(duplicate_output["proposal_status"] == "ready", "Saved proposal was not reused")
    store.complete_task(plan["task_id"], running["lease_id"], output)
    ready = store.get_plan(plan["id"])
    adoption = PlanAdopt(actor="planner-smoke", plan_digest=ready["plan_digest"])
    expect_error(PlanConflictError, lambda: store.adopt_plan(plan["id"], PlanAdopt(
        actor="planner-smoke", plan_digest="0" * 64,
    )))

    original_create = store._create_workflow_record

    def rollback_probe(connection, specification):
        original_create(connection, specification)
        raise RuntimeError("Synthetic adoption rollback")

    store._create_workflow_record = rollback_probe
    expect_error(RuntimeError, lambda: store.adopt_plan(plan["id"], adoption))
    store._create_workflow_record = original_create
    check(store.get_plan(plan["id"])["status"] == "ready", "Failed adoption mutated the proposal")
    check(len(store.list_workflows()) == 0, "Failed adoption leaked an executable workflow")

    barrier = Barrier(2)

    def adopt_concurrently():
        barrier.wait(timeout=10)
        return PlanningStore(dsn).adopt_plan(plan["id"], adoption)["id"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.submit(adopt_concurrently), executor.submit(adopt_concurrently)
        workflow_id = first.result(timeout=20)
        check(second.result(timeout=20) == workflow_id, "Concurrent adoption duplicated work")
    check(len(store.list_workflows()) == 1, "Adoption created more than one workflow")
    store.reconcile_workflows()
    workflow = store.get_workflow(workflow_id)
    child = store.transition_to_running(workflow["steps"][0]["task_id"], 30, "planner-smoke")
    store.complete_task(child["id"], child["lease_id"], execute_foundation_task(child))
    store.reconcile_workflows()
    check(store.get_workflow(workflow_id)["status"] == "succeeded", "Adopted demo did not execute")

    forged = store.create_task(TaskCreate(
        title="Synthetic forged planner link", kind="planning.propose",
        payload={"plan_id": str(plan["id"])}, requested_by="planner-smoke",
    ))
    forged_claim = store.transition_to_running(forged["id"], 30, "planner-smoke")
    expect_error(PlanContextError, lambda: execute_planning_task(forged_claim, store, get_settings()))

    stale = store.create_plan(request.model_copy(update={"idempotency_key": None}))
    stale_claim = store.transition_to_running(stale["task_id"], 30, "planner-smoke")
    with store.connect() as connection:
        connection.execute(
            "UPDATE agent_tasks SET lease_expires_at = now() - interval '1 second' WHERE id = %s",
            (stale["task_id"],),
        )
    choice = ModelPlanChoice(supported=True, action_keys=["verify_runtime"], summary="Synthetic")
    expect_error(InvalidTaskStateError, lambda: store.save_proposal(
        plan_id=stale["id"], task_id=stale["task_id"], lease_id=stale_claim["lease_id"],
        choice=choice, source="template", selected_model=None,
    ))

    cancelled = store.create_plan(request.model_copy(update={"idempotency_key": None}))
    store.cancel_task(cancelled["task_id"], TaskCancellation(actor="planner-smoke"))
    check(store.get_plan(cancelled["id"])["status"] == "failed", "Cancellation was not projected")

    expired = store.create_plan(request.model_copy(update={"idempotency_key": None}))
    claim = store.transition_to_running(expired["task_id"], 30, "planner-smoke")
    output = execute_planning_task(claim, store, get_settings())
    store.complete_task(claim["id"], claim["lease_id"], output)
    expired = store.get_plan(expired["id"])
    with store.connect() as connection:
        connection.execute(
            "UPDATE goal_plans SET expires_at = now() - interval '1 second' WHERE id = %s",
            (expired["id"],),
        )
    expect_error(PlanConflictError, lambda: store.adopt_plan(expired["id"], PlanAdopt(
        actor="planner-smoke", plan_digest=expired["plan_digest"],
    )))
    print("Planner SQL passed: bounds, exact review, rollback, concurrent adoption, leases, cancellation")


def isolated():
    source_dsn = os.environ["DATABASE_URL"]
    schema = f"planner_smoke_{uuid4().hex}"
    dsn = make_conninfo(source_dsn, options=f"-csearch_path={schema},public")
    with psycopg.connect(source_dsn) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        with psycopg.connect(dsn) as connection:
            for table in (
                "agent_tasks", "task_outbox", "audit_events", "task_approvals", "external_actions",
                "career_profiles", "job_opportunities", "marketing_campaigns", "agent_workflows",
                "workflow_steps", "goal_plans",
            ):
                connection.execute(sql.SQL("CREATE TABLE {} (LIKE {} INCLUDING ALL)").format(
                    sql.Identifier(schema, table), sql.Identifier("public", table),
                ))
        exercise(dsn)
    finally:
        with psycopg.connect(source_dsn) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def api(path, body=None):
    # Fixed loopback API; paths use server-returned UUIDs only.
    request = Request(
        "http://127.0.0.1:8000" + path,
        headers={"Authorization": "Bearer " + os.environ["CONTROL_API_TOKEN"],
                 "Content-Type": "application/json"},
        data=None if body is None else json.dumps(body).encode("utf-8"),
        method="GET" if body is None else "POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"Local planner API returned HTTP {exc.code}") from None


def live():
    plan = api("/v1/plans", {
        "goal": "Verify the durable workflow runtime with its available runtime check.",
        "requested_by": "planner-live-smoke", "mode": "model",
        "idempotency_key": f"planner-live-{uuid4()}",
    })
    plan_id = UUID(plan["id"])
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        plan = api(f"/v1/plans/{plan_id}")
        if plan["status"] in {"ready", "unsupported", "failed"}:
            break
        time.sleep(1)
    check(plan["status"] == "ready", f"Live proposal did not become ready: {plan['status']}")
    check(plan["source"] in {"openrouter", "ollama"}, "Live proof must invoke an actual model")
    check(all(step["kind"] == "foundation.echo" for step in plan["workflow_spec"]["steps"]),
          "Live proof may execute only the fixed local runtime check")
    workflow = api(f"/v1/plans/{plan_id}/adopt", {
        "actor": "planner-live-smoke", "plan_digest": plan["plan_digest"],
    })
    workflow_id = UUID(workflow["id"])
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        workflow = api(f"/v1/workflows/{workflow_id}")
        if workflow["status"] not in {"running", "cancelling"}:
            break
        time.sleep(1)
    check(workflow["status"] == "succeeded", "Live reviewed workflow did not succeed")
    print(json.dumps({
        "proof": "planner_live", "plan_id": str(plan_id), "workflow_id": str(workflow_id),
        "source": plan["source"], "selected_model": plan["selected_model"], "status": "passed",
        "retained": "Synthetic task, proposal, workflow, and shared inference-accounting proof",
    }))


if __name__ == "__main__":
    live() if "--live" in sys.argv[1:] else isolated()
