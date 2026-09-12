import json
from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app import planning
from app.inference import InferenceResult, OpenRouterError, OpenRouterFreeClient, OpenRouterPlan
from app.planning_models import ModelPlanChoice, PlanCreate, compile_workflow, parse_plan_choice
from app.planning_store import PlanContextError, PlanningStore
from app.settings import get_settings


def inventory():
    return [{
        "key": "verify_runtime", "title": "Verify the durable workflow runtime",
        "kind": "foundation.echo", "payload": {"message": "server-controlled"},
        "expect_output": {"echo": "server-controlled"},
    }]


def response(**overrides):
    return json.dumps({
        "supported": True, "action_keys": ["verify_runtime"],
        "summary": "Propose a runtime check", "limitations": [], **overrides,
    })


def setup_plan(mode="model", status="queued"):
    task_id, plan_id = uuid4(), uuid4()
    task = {"id": task_id, "lease_id": uuid4(), "payload": {"plan_id": str(plan_id)}}
    plan = {
        "id": plan_id, "status": status, "mode": mode, "goal": "Check the workflow runtime",
        "action_inventory": inventory(), "source": "template" if mode == "demo" else "ollama",
    }
    database = Mock(spec=PlanningStore)
    database.get_plan_for_execution.return_value = plan
    database.start_inference_invocation.side_effect = [uuid4(), uuid4(), uuid4()]
    database.save_proposal.return_value = {"status": "ready"}
    return task, plan, database


@pytest.mark.parametrize("overrides", [
    {"opportunity_ids": [uuid4()]},
    {"mode": "demo", "profile_id": uuid4()},
    {"goal": "   "},
])
def test_goal_context_must_be_explicit_and_consistent(overrides):
    with pytest.raises(ValueError):
        PlanCreate.model_validate({"goal": "Test", "requested_by": "test", **overrides})


@pytest.mark.parametrize("changes", [
    {"action_keys": ["communications.email_send"]},
    {"action_keys": ["verify_runtime", "verify_runtime"]},
    {"action_keys": []},
    {"supported": False},
    {"supported": "true"},
    {"payload": {"command": "untrusted command"}},
])
def test_model_cannot_invent_capabilities_or_executable_fields(changes):
    with pytest.raises(ValueError):
        parse_plan_choice(response(**changes), inventory())


def test_compilation_uses_only_server_owned_payload_and_checks():
    request = PlanCreate(goal="Verify the workflow runtime", requested_by="test")
    choice = parse_plan_choice(response(), inventory())
    spec = compile_workflow(request, choice, inventory())
    assert spec.steps[0].payload == {"message": "server-controlled"}
    assert spec.steps[0].expect_output == {"echo": "server-controlled"}
    assert spec.max_parallel == 1
    assert spec.timeout_seconds == 3600
    assert spec.steps[0].risk_level.value == "low"


def test_unsupported_goal_creates_no_executable_plan():
    choice = ModelPlanChoice(
        supported=False, action_keys=[], summary="Sending email is outside this planner",
    )
    assert compile_workflow(PlanCreate(goal="Send email", requested_by="test"), choice, []) is None


def test_model_prompt_excludes_stored_ids_private_data_and_task_payloads():
    task, plan, _database = setup_plan()
    plan.update(resume_text="PRIVATE_RESUME", contact_email="PRIVATE_EMAIL", task_id=task["id"])
    serialized = json.dumps(planning.planning_messages(plan))
    for excluded in ("PRIVATE_RESUME", "PRIVATE_EMAIL", str(task["id"]), "server-controlled"):
        assert excluded not in serialized
    assert "verify_runtime" in serialized


def test_explicit_demo_uses_no_inference_and_is_labeled_template(monkeypatch):
    task, _plan, database = setup_plan(mode="demo")
    generate = Mock(side_effect=AssertionError("Demo must not invoke a model"))
    monkeypatch.setattr(planning, "_model_choice", generate)
    output = planning.execute_planning_task(task, database, get_settings())
    assert output["source"] == "template"
    database.start_inference_invocation.assert_not_called()
    assert database.save_proposal.call_args.kwargs["selected_model"] is None


def test_retry_after_saved_proposal_does_not_spend_another_model_call(monkeypatch):
    task, _plan, database = setup_plan(status="ready")
    generate = Mock(side_effect=AssertionError("Saved proposal must be reused"))
    monkeypatch.setattr(planning, "_model_choice", generate)
    output = planning.execute_planning_task(task, database, get_settings())
    assert output["proposal_status"] == "ready"
    database.save_proposal.assert_not_called()


def test_forged_task_link_is_rejected_before_any_model_call(monkeypatch):
    task, _plan, database = setup_plan()
    database.get_plan_for_execution.side_effect = PlanContextError("Task is not linked")
    generate = Mock()
    monkeypatch.setattr(planning, "_model_choice", generate)
    with pytest.raises(PlanContextError):
        planning.execute_planning_task(task, database, get_settings())
    generate.assert_not_called()


def test_failed_model_does_not_silently_substitute_a_template(monkeypatch):
    task, _plan, database = setup_plan()
    monkeypatch.setattr(planning, "local_plan_completion", Mock(return_value=("invalid", {})))
    with pytest.raises(planning.PlanningModelError, match="valid goal proposal"):
        planning.execute_planning_task(task, database, get_settings())
    database.fail_plan.assert_called_once()
    database.save_proposal.assert_not_called()
    database.fail_inference_invocation.assert_called_once()


def hosted_result(content, model):
    return InferenceResult(
        content=content, selected_model=model, selected_route=model, selected_provider="Synthetic",
        prompt_tokens=1, completion_tokens=2, total_tokens=3, cost=Decimal(0), latency_ms=1,
        fallback_attempt=1,
    )


def test_invalid_hosted_plan_is_accounted_then_next_safe_route_is_used(monkeypatch):
    task, _plan, database = setup_plan()
    client = Mock(spec=OpenRouterFreeClient)
    client.privacy_mode = "no-training/zdr"
    client.plan.return_value = OpenRouterPlan(("first:free", "second:free"), 20, True)
    client.complete.side_effect = [
        hosted_result(response(action_keys=["send_money"]), "first:free"),
        hosted_result(response(), "second:free"),
    ]
    local = Mock(side_effect=AssertionError("Valid hosted plan should not invoke local model"))
    monkeypatch.setattr(planning, "local_plan_completion", local)
    output = planning.execute_planning_task(task, database, get_settings(), client=client)
    assert output["source"] == "openrouter"
    assert database.start_inference_invocation.call_count == 2
    database.fail_inference_invocation.assert_called_once()
    database.complete_inference_invocation.assert_called_once()
    client.reject_model.assert_called_once_with("first:free")
    assert client.complete.call_args.args[1].models == ("second:free",)


def test_hosted_outage_uses_accounted_local_model_without_exposing_error_body(monkeypatch):
    task, _plan, database = setup_plan()
    client = Mock(spec=OpenRouterFreeClient)
    client.privacy_mode = "no-training/zdr"
    client.plan.return_value = OpenRouterPlan(("first:free",), 20, True)
    client.complete.side_effect = OpenRouterError("PRIVATE_PROVIDER_BODY", code="OUTAGE")
    monkeypatch.setattr(planning, "local_plan_completion", Mock(return_value=(response(), {
        "prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3,
    })))
    runtime = replace(get_settings(), openrouter_local_fallback=True)
    output = planning.execute_planning_task(task, database, runtime, client=client)
    assert output["source"] == "ollama"
    assert "PRIVATE_PROVIDER_BODY" not in json.dumps(output)
    providers = [call.kwargs["provider"]
                 for call in database.start_inference_invocation.call_args_list]
    assert providers == ["openrouter", "ollama"]
