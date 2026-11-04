"""One audited local model selection for a saved reply draft; never a send path."""

from __future__ import annotations

import json
import time
from contextlib import suppress
from http.client import HTTPException, IncompleteRead
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import UUID

from app.creator_drafting import (
    GROUNDED_LOCAL_RESPONSE_TIMEOUT_SECONDS,
    CreatorDraftModelError,
    _local_failure,
    _NoRedirects,
)
from app.creator_reply_content import (
    CreatorReplyCopyError,
    parse_reply_model_copy,
    reply_drafting_messages,
    reply_response_schema,
)
from app.creator_reply_draft_store import CreatorReplyDraftConflictError
from app.store import InvalidTaskStateError
from app.worker import TaskInterruptedError


class CreatorReplyDraftModelError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__("Creator reply drafting stopped without a valid saved model selection")


def local_reply_completion(messages, model, *, context):
    request = Request(
        "http://ollama:11434/api/chat", method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        data=json.dumps({
            "model": model, "messages": messages, "stream": False, "think": False,
            "format": reply_response_schema(context),
            "options": {"temperature": 0, "num_predict": 512},
        }).encode("utf-8"),
    )
    try:
        with build_opener(ProxyHandler({}), _NoRedirects()).open(
            request, timeout=GROUNDED_LOCAL_RESPONSE_TIMEOUT_SECONDS,
        ) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise _local_failure("CREATOR_LOCAL_RESPONSE_TOO_LARGE")
        envelope = json.loads(raw)
        if not isinstance(envelope, dict):
            raise _local_failure("CREATOR_LOCAL_INVALID_RESPONSE")
        if envelope.get("done") is not True or envelope.get("done_reason") != "stop":
            raise _local_failure("CREATOR_LOCAL_INCOMPLETE_RESPONSE")
        content = envelope["message"]["content"]
        if not isinstance(content, str):
            raise _local_failure("CREATOR_LOCAL_INVALID_RESPONSE")
        prompt = max(0, int(envelope.get("prompt_eval_count") or 0))
        completion = max(0, int(envelope.get("eval_count") or 0))
        return content, {"prompt_tokens": prompt, "completion_tokens": completion,
                         "total_tokens": prompt + completion}
    except HTTPError as exc:
        code = ("CREATOR_LOCAL_MODEL_MISSING" if exc.code == 404 else
                "CREATOR_LOCAL_BUSY" if exc.code in {429, 503} else "CREATOR_LOCAL_HTTP_ERROR")
        raise _local_failure(code) from None
    except URLError as exc:
        raise _local_failure("CREATOR_LOCAL_TIMEOUT" if isinstance(exc.reason, TimeoutError)
                             else "CREATOR_LOCAL_CONNECTION_FAILED") from None
    except TimeoutError:
        raise _local_failure("CREATOR_LOCAL_TIMEOUT") from None
    except IncompleteRead:
        raise _local_failure("CREATOR_LOCAL_INCOMPLETE_RESPONSE") from None
    except (OSError, HTTPException):
        raise _local_failure("CREATOR_LOCAL_CONNECTION_FAILED") from None
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise _local_failure("CREATOR_LOCAL_INVALID_RESPONSE") from None


def _checkpoint(task, row, store, runtime, interrupt):
    if interrupt is not None and interrupt.is_set():
        raise TaskInterruptedError("Creator reply drafting was interrupted")
    if UUID(row["model_context"]["campaign_id"]) not in getattr(
        runtime, "creator_reply_draft_campaign_ids", (),
    ):
        raise CreatorReplyDraftConflictError(
            "Local reply drafting is not enabled for this campaign",
        )
    store.get_reply_draft_for_execution(row["id"], UUID(str(task["id"])), task["lease_id"])


def execute_creator_reply_draft_task(task, store, runtime, interrupt=None):
    payload = task.get("payload")
    if not isinstance(payload, dict) or set(payload) != {"reply_draft_id"}:
        raise CreatorReplyDraftModelError("CREATOR_REPLY_DRAFT_CONTEXT_CHANGED")
    try:
        draft_id, task_id = UUID(str(payload["reply_draft_id"])), UUID(str(task["id"]))
    except (ValueError, TypeError, KeyError):
        raise CreatorReplyDraftModelError("CREATOR_REPLY_DRAFT_CONTEXT_CHANGED") from None
    try:
        row = store.get_reply_draft_for_execution(draft_id, task_id, task["lease_id"])
        if row["status"] == "ready":
            return {"handler": "marketing.creator_reply_draft", "reply_draft_id": str(draft_id),
                    "draft_status": "ready", "source": "ollama"}
        if row["status"] != "queued":
            raise CreatorReplyDraftConflictError("Reply draft is not queued")
        context = row["model_context"]
        messages = reply_drafting_messages(context)
        _checkpoint(task, row, store, runtime, interrupt)
        invocation = store.start_reply_inference_invocation(
            draft_id=draft_id, task_id=task_id, lease_id=task["lease_id"],
            requested_model=runtime.local_model,
        )
        if invocation is None:
            raise CreatorReplyDraftModelError("CREATOR_REPLY_DRAFT_MODEL_UNAVAILABLE")
        started = time.monotonic()
        try:
            _checkpoint(task, row, store, runtime, interrupt)
            raw, usage = local_reply_completion(messages, runtime.local_model, context=context)
            copy = parse_reply_model_copy(raw, context)
            _checkpoint(task, row, store, runtime, interrupt)
        except (TaskInterruptedError, InvalidTaskStateError, CreatorReplyDraftConflictError):
            store.fail_inference_invocation(invocation, "CREATOR_REPLY_DRAFT_INTERRUPTED")
            raise
        except CreatorReplyCopyError:
            store.fail_inference_invocation(invocation, "CREATOR_REPLY_DRAFT_OUTPUT_INVALID")
            raise CreatorReplyDraftModelError("CREATOR_REPLY_DRAFT_OUTPUT_INVALID") from None
        except CreatorDraftModelError as exc:
            store.fail_inference_invocation(invocation, exc.code)
            raise CreatorReplyDraftModelError("CREATOR_REPLY_DRAFT_MODEL_UNAVAILABLE") from None
        store.complete_inference_invocation(
            invocation, selected_model=runtime.local_model, selected_provider="ollama",
            **usage, cost=0, latency_ms=round((time.monotonic() - started) * 1000),
            fallback_attempt=1,
        )
        _checkpoint(task, row, store, runtime, interrupt)
        saved = store.save_reply_draft(
            draft_id=draft_id, task_id=task_id, lease_id=task["lease_id"],
            copy=copy, selected_model=runtime.local_model,
        )
        return {"handler": "marketing.creator_reply_draft", "reply_draft_id": str(draft_id),
                "draft_status": saved["status"], "source": "ollama"}
    except (
        CreatorReplyCopyError, CreatorReplyDraftModelError, CreatorReplyDraftConflictError,
    ) as exc:
        code = ("CREATOR_REPLY_DRAFT_CONTEXT_CHANGED" if isinstance(
            exc, (CreatorReplyDraftConflictError, CreatorReplyCopyError),
        ) else exc.code)
        with suppress(InvalidTaskStateError, CreatorReplyDraftConflictError):
            store.fail_reply_draft(draft_id, task_id, task["lease_id"], code)
        raise
