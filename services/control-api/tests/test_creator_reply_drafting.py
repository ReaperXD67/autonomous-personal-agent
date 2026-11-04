import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID, uuid4

import pytest

from app.creator_drafting import CreatorDraftModelError
from app.creator_reply_content import reply_model_context
from app.creator_reply_draft_store import CreatorReplyDraftConflictError
from app.creator_reply_drafting import (
    CreatorReplyDraftModelError,
    execute_creator_reply_draft_task,
    local_reply_completion,
)
from app.worker import TaskInterruptedError


def setup():
    from test_creator_reply_content import fixtures

    draft_id = uuid4()
    task = {"id": uuid4(), "lease_id": uuid4(), "payload": {"reply_draft_id": str(draft_id)}}
    row = {"id": draft_id, "status": "queued", "model_context": reply_model_context(*fixtures())}
    store = Mock()
    store.get_reply_draft_for_execution.return_value = row
    store.start_reply_inference_invocation.return_value = uuid4()
    store.save_reply_draft.return_value = {"status": "ready"}
    return task, row, store, SimpleNamespace(
        local_model="synthetic-local-model",
        creator_reply_draft_campaign_ids=(UUID(row["model_context"]["campaign_id"]),),
    )


def valid_response():
    return json.dumps({"response_mode": "acknowledge_discord_handle"}), {
        "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
    }


def test_one_local_ledgered_selection_saves_private_copy_and_returns_no_body():
    task, row, store, runtime = setup()
    with patch("app.creator_reply_drafting.local_reply_completion",
               return_value=valid_response()) as local:
        result = execute_creator_reply_draft_task(task, store, runtime)
    local.assert_called_once()
    store.start_reply_inference_invocation.assert_called_once()
    assert store.complete_inference_invocation.call_args.kwargs["selected_provider"] == "ollama"
    assert "body" not in result and "model_context" not in result and result["source"] == "ollama"
    saved = store.save_reply_draft.call_args.kwargs["copy"]
    assert saved["provenance"]["body_digest"] == row["model_context"]["reply"]["body_digest"]
    assert "karixai" in saved["body"]


@pytest.mark.parametrize("failure", ["invalid", "unavailable", "budget"])
def test_failure_has_no_repair_fallback_or_ready_copy(failure):
    task, _, store, runtime = setup()
    if failure == "budget":
        store.start_reply_inference_invocation.return_value = None
    with patch("app.creator_reply_drafting.local_reply_completion") as local:
        local.return_value = ("PRIVATE_INVALID_PROSE", valid_response()[1])
        if failure == "unavailable":
            local.side_effect = CreatorDraftModelError("Fixed unavailable")
        with pytest.raises(CreatorReplyDraftModelError) as stopped:
            execute_creator_reply_draft_task(task, store, runtime)
    assert "PRIVATE_INVALID_PROSE" not in str(stopped.value)
    assert local.call_count == (0 if failure == "budget" else 1)
    store.save_reply_draft.assert_not_called()
    store.fail_reply_draft.assert_called_once()


def test_ready_replay_does_not_repeat_inference_and_interrupt_never_saves():
    task, row, store, runtime = setup()
    row["status"] = "ready"
    execute_creator_reply_draft_task(task, store, runtime)
    store.start_reply_inference_invocation.assert_not_called()
    row["status"] = "queued"
    interrupt = threading.Event()
    interrupt.set()
    with pytest.raises(TaskInterruptedError):
        execute_creator_reply_draft_task(task, store, runtime, interrupt)
    store.start_reply_inference_invocation.assert_not_called()
    store.save_reply_draft.assert_not_called()


def test_post_model_interrupt_fences_copy_and_marks_reserved_attempt_interrupted():
    task, _, store, runtime = setup()
    interrupt = threading.Event()

    def finish(*args, **kwargs):
        interrupt.set()
        return valid_response()

    with patch("app.creator_reply_drafting.local_reply_completion", side_effect=finish), \
            pytest.raises(TaskInterruptedError):
        execute_creator_reply_draft_task(task, store, runtime, interrupt)
    store.fail_inference_invocation.assert_called_once()
    store.save_reply_draft.assert_not_called()


def test_removing_campaign_optin_blocks_queued_model_work_without_spending():
    task, _, store, runtime = setup()
    runtime.creator_reply_draft_campaign_ids = ()
    with pytest.raises(CreatorReplyDraftConflictError):
        execute_creator_reply_draft_task(task, store, runtime)
    store.start_reply_inference_invocation.assert_not_called()
    store.save_reply_draft.assert_not_called()


def test_local_transport_uses_only_fixed_internal_json_endpoint_and_never_reasoning():
    _, row, _, runtime = setup()
    response = Mock()
    response.read.return_value = json.dumps({
        "done": True, "done_reason": "stop", "prompt_eval_count": 10, "eval_count": 5,
        "message": {"content": valid_response()[0], "thinking": "PRIVATE_REASONING"},
    }).encode()
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value = response
    with patch("app.creator_reply_drafting.build_opener", return_value=opener):
        content, usage = local_reply_completion(
            [], runtime.local_model, context=row["model_context"],
        )
    request = opener.open.call_args.args[0]
    payload = json.loads(request.data)
    assert request.full_url == "http://ollama:11434/api/chat"
    assert opener.open.call_args.kwargs["timeout"] == 300
    assert payload["think"] is False and payload["options"]["num_predict"] == 512
    assert set(payload["format"]["properties"]) == {"response_mode"}
    assert "PRIVATE_REASONING" not in content and usage["total_tokens"] == 15


def test_incomplete_local_envelope_never_becomes_copy():
    _, row, _, runtime = setup()
    response = Mock()
    response.read.return_value = b'{"done":true,"done_reason":"length","message":{"content":"x"}}'
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value = response
    with patch("app.creator_reply_drafting.build_opener", return_value=opener), \
            pytest.raises(CreatorDraftModelError) as error:
        local_reply_completion([], runtime.local_model, context=row["model_context"])
    assert error.value.code == "CREATOR_LOCAL_INCOMPLETE_RESPONSE"
