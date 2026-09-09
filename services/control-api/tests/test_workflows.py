from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.policy import RiskLevel
from app.workflow_models import WorkflowCreate, WorkflowStepCreate, output_matches


def plan():
    return {
        "title": "Evidence-based fork and join", "requested_by": "test",
        "steps": [
            {"key": "join", "title": "Join", "kind": "foundation.echo",
             "depends_on": ["left", "right"]},
            {"key": "left", "title": "Left", "kind": "foundation.echo"},
            {"key": "right", "title": "Right", "kind": "foundation.wait"},
        ],
    }


def test_accepts_out_of_order_dag_and_derives_risk():
    parsed = WorkflowCreate.model_validate(plan())
    assert parsed.steps[2].risk_level == RiskLevel.MEDIUM
    assert parsed.steps[2].payload == {"seconds": 1.0}


@pytest.mark.parametrize("case", ["duplicate", "missing", "self", "cycle", "duplicate_edge"])
def test_rejects_invalid_dependency_graphs(case):
    data = plan()
    if case == "duplicate":
        data["steps"][1]["key"] = "right"
    elif case == "missing":
        data["steps"][0]["depends_on"] = ["absent"]
    elif case == "self":
        data["steps"][1]["depends_on"] = ["left"]
    elif case == "cycle":
        data["steps"][1]["depends_on"] = ["join"]
    else:
        data["steps"][0]["depends_on"] = ["left", "left"]
    with pytest.raises(ValidationError):
        WorkflowCreate.model_validate(data)


@pytest.mark.parametrize(
    "kind", ["communications.email_send", "career.application_submit", "shell"]
)
def test_workflows_cannot_grant_side_effects_or_unknown_tools(kind):
    data = plan()
    data["steps"][1]["kind"] = kind
    with pytest.raises(ValidationError):
        WorkflowCreate.model_validate(data)


@pytest.mark.parametrize("field,value", [
    ("max_parallel", 0), ("max_parallel", 5), ("max_parallel", True),
    ("timeout_seconds", 59), ("timeout_seconds", 86401),
])
def test_resource_limits_are_enforced(field, value):
    data = plan()
    data[field] = value
    with pytest.raises(ValidationError):
        WorkflowCreate.model_validate(data)


def test_rejects_unbounded_steps_and_payloads():
    data = plan()
    data["steps"] = [dict(data["steps"][1], key=f"step{i}") for i in range(33)]
    with pytest.raises(ValidationError):
        WorkflowCreate.model_validate(data)
    for payload in [{"workflow_managed": False}, {"message": "a" * 2001}]:
        with pytest.raises(ValidationError):
            WorkflowStepCreate(key="x", title="X", kind="foundation.echo", payload=payload)
    for seconds in [float("nan"), float("inf"), -1, 61]:
        with pytest.raises(ValidationError):
            WorkflowStepCreate(key="x", title="X", kind="foundation.wait",
                               payload={"seconds": seconds})


def test_plan_hash_is_canonical_and_includes_evidence():
    data = plan()
    first = WorkflowCreate.model_validate(data)
    data["idempotency_key"] = "some-other-request"
    assert WorkflowCreate.model_validate(data).canonical_spec() == first.canonical_spec()
    changed = deepcopy(data)
    changed["steps"][1]["expect_output"] = {"echo": "verified"}
    assert WorkflowCreate.model_validate(changed).canonical_spec() != first.canonical_spec()


def test_output_checks_do_not_coerce_or_execute_data():
    assert output_matches({"draft_created": True, "blocked_reason": None},
                          {"draft_created": True, "blocked_reason": None})
    assert not output_matches({}, {"missing": None})
    assert not output_matches({"ok": 1}, {"ok": True})
    assert not output_matches({"ok": True}, {"ok": 1})
    assert not output_matches({"count": "2"}, {"count": 2})
    assert not output_matches({"nested": {"value": "x"}}, {"nested.value": "x"})
    assert output_matches(None, {})


def test_identifiers_and_expectations_are_bounded():
    with pytest.raises(ValidationError):
        WorkflowStepCreate(key="x", title="X", kind="career.application_draft",
                           payload={"profile_id": "invalid", "opportunity_id": "invalid"})
    with pytest.raises(ValidationError):
        WorkflowStepCreate(key="x", title="X", kind="foundation.echo",
                           expect_output={"x": {"expression": "anything"}})
