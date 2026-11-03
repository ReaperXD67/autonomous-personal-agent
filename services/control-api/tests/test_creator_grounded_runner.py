"""Real runner boundaries with synthetic selector responses and no network/model use."""

import json
from unittest.mock import Mock

import pytest
from test_creator_drafting import fixture, setup

from app import creator_drafting
from app.creator_draft_content import grounded_model_context, response_schema
from app.creator_draft_quality import creator_draft_quality_report
from app.creator_learning import creator_learning_insights
from app.settings import get_settings


def grounded_setup():
    task, row, database = setup()
    campaign, prospect = fixture()
    row["model_context"] = grounded_model_context(
        campaign, prospect, creator_learning_insights([], []),
    )
    schema = response_schema(row["model_context"])
    plan = {key: value["enum"][0] for key, value in schema["properties"].items()}
    return task, row, database, plan


def test_selector_uses_non_thinking_small_dynamic_schema_and_records_usage(monkeypatch):
    task, row, database, plan = grounded_setup()
    received = Mock()
    received.read.return_value = json.dumps({
        "done": True, "done_reason": "stop",
        "message": {"content": json.dumps(plan), "thinking": "PRIVATE_MODEL_REASONING"},
        "prompt_eval_count": 100, "eval_count": 20,
    }).encode()
    transport = Mock()
    transport.open.return_value.__enter__ = Mock(return_value=received)
    transport.open.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(creator_drafting, "build_opener", Mock(return_value=transport))
    result = creator_drafting.execute_creator_draft_task(task, database, get_settings())
    request = transport.open.call_args.args[0]
    assert transport.open.call_args.kwargs["timeout"] == 300
    payload = json.loads(request.data)
    assert payload["think"] is False
    assert payload["options"] == {"temperature": 0, "num_predict": 512}
    assert payload["format"] == response_schema(row["model_context"])
    assert result["source"] == "ollama"
    assert database.complete_inference_invocation.call_args.kwargs["total_tokens"] == 120
    saved = database.save_draft.call_args.kwargs["copy"]
    assert saved.plan.model_dump() == plan
    assert "PRIVATE_MODEL_REASONING" not in repr(database.mock_calls)


def test_selector_repair_is_bounded_and_excludes_rejected_prose(monkeypatch):
    task, row, database, plan = grounded_setup()
    complete = Mock(side_effect=[
        (json.dumps({**plan, "hook": "PRIVATE_UNSUPPORTED_CLAIM"}), {}),
        (json.dumps(plan), {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}),
    ])
    monkeypatch.setattr(creator_drafting, "local_draft_completion", complete)
    creator_drafting.execute_creator_draft_task(task, database, get_settings())
    assert complete.call_count == database.start_inference_invocation.call_count == 2
    assert all(call.kwargs["context"] is row["model_context"]
               for call in complete.call_args_list)
    repair = complete.call_args_list[1].args[0][-1]["content"]
    assert "evidence_id and angle_id" in repair
    assert "PRIVATE_UNSUPPORTED_CLAIM" not in repair
    assert "PRIVATE_UNSUPPORTED_CLAIM" not in repr(database.mock_calls)
    database.save_draft.assert_called_once()


def test_invalid_selector_fails_visibly_without_disguised_template_fallback(monkeypatch):
    task, _, database, _ = grounded_setup()
    complete = Mock(return_value=(json.dumps({"evidence_id": "invented", "angle_id": "bad"}), {}))
    monkeypatch.setattr(creator_drafting, "local_draft_completion", complete)
    with pytest.raises(creator_drafting.CreatorDraftOutputError):
        creator_drafting.execute_creator_draft_task(task, database, get_settings())
    assert complete.call_count == 2
    database.save_draft.assert_not_called()
    assert database.fail_draft.call_args.args[-1] == "CREATOR_DRAFT_OUTPUT_INVALID"


def test_selector_transport_failure_does_not_retry_or_create_a_draft(monkeypatch):
    task, _, database, _ = grounded_setup()
    complete = Mock(side_effect=creator_drafting.CreatorDraftModelError("No response"))
    monkeypatch.setattr(creator_drafting, "local_draft_completion", complete)
    with pytest.raises(creator_drafting.CreatorDraftModelError):
        creator_drafting.execute_creator_draft_task(task, database, get_settings())
    complete.assert_called_once()
    database.save_draft.assert_not_called()
    assert database.fail_draft.call_args.args[-1] == "CREATOR_DRAFT_MODEL_UNAVAILABLE"


def test_report_distinguishes_selected_plan_from_model_authored_words(monkeypatch):
    task, row, database, plan = grounded_setup()
    monkeypatch.setattr(creator_drafting, "local_draft_completion", Mock(return_value=(
        json.dumps(plan), {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    )))
    creator_drafting.execute_creator_draft_task(task, database, get_settings())
    copy = database.save_draft.call_args.kwargs["copy"]
    report = creator_draft_quality_report({
        "model_context": row["model_context"], "model_copy": copy.model_dump(),
        "body": copy.hook + "\nCould you discuss a trial?\n"
                + row["model_context"]["evidence"][0]["url"],
    })
    assert report["model_word_count"] == 0
    assert any(finding["code"] == "MODEL_SELECTED_PLAN" for finding in report["findings"])
    assert report["human_review_required"] is True and report["sending_authority"] is False
