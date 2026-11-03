from __future__ import annotations

import json
import threading
import time
from contextlib import suppress
from http.client import HTTPException, IncompleteRead
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import UUID

from app.creator_draft_content import (
    COPY_CORRECTIONS,
    CreatorCopyError,
    drafting_messages,
    parse_model_copy,
    response_schema,
)
from app.creator_draft_models import CreatorModelCopy
from app.creator_draft_store import CreatorDraftConflictError, CreatorDraftStore
from app.inference import OpenRouterError, OpenRouterFreeClient, OpenRouterPlan
from app.settings import Settings
from app.store import InvalidTaskStateError
from app.worker import TaskInterruptedError

LEGACY_LOCAL_RESPONSE_TIMEOUT_SECONDS = 180
GROUNDED_LOCAL_RESPONSE_TIMEOUT_SECONDS = 300

LOCAL_FAILURE_MESSAGES = {
    "CREATOR_LOCAL_UNAVAILABLE": "Local drafting model returned no valid response",
    "CREATOR_LOCAL_TIMEOUT": "Local drafting exceeded its bounded response timeout",
    "CREATOR_LOCAL_CONNECTION_FAILED": "Local drafting connection was unavailable or disconnected",
    "CREATOR_LOCAL_MODEL_MISSING": "The configured local drafting model was not found",
    "CREATOR_LOCAL_BUSY": "Local drafting endpoint could not accept this bounded request",
    "CREATOR_LOCAL_HTTP_ERROR": "Local drafting endpoint returned an unsuccessful HTTP status",
    "CREATOR_LOCAL_INVALID_RESPONSE": "Local drafting returned an invalid response envelope",
    "CREATOR_LOCAL_INCOMPLETE_RESPONSE": "Local drafting did not finish a complete response",
    "CREATOR_LOCAL_RESPONSE_TOO_LARGE": "Local drafting response exceeded the bounded size",
    "CREATOR_LOCAL_REDIRECT_REFUSED": "Local drafting endpoint redirects are disabled",
}


class CreatorDraftModelError(RuntimeError):
    def __init__(self, message: str, *, code: str = "CREATOR_LOCAL_UNAVAILABLE"):
        self.code = code if code in LOCAL_FAILURE_MESSAGES else "CREATOR_LOCAL_UNAVAILABLE"
        super().__init__(message)


def _local_failure(code: str) -> CreatorDraftModelError:
    return CreatorDraftModelError(LOCAL_FAILURE_MESSAGES[code], code=code)


class CreatorDraftOutputError(CreatorDraftModelError):
    """A model responded, but bounded selection never met the frozen contract."""


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise _local_failure("CREATOR_LOCAL_REDIRECT_REFUSED") from None


def local_draft_completion(messages, model, *, context=None):
    grounded = bool(context and context.get("drafting_contract") == "creator-grounded-plan-v2")
    response_timeout = (GROUNDED_LOCAL_RESPONSE_TIMEOUT_SECONDS if grounded
                        else LEGACY_LOCAL_RESPONSE_TIMEOUT_SECONDS)
    request = Request(
        "http://ollama:11434/api/chat", method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        data=json.dumps({
            "model": model, "messages": messages, "stream": False, "think": not grounded,
            "format": response_schema(context) if context else CreatorModelCopy.model_json_schema(),
            "options": {"temperature": 0 if grounded else 0.3,
                        "num_predict": 512 if grounded else 2048},
        }).encode("utf-8"),
    )
    try:
        with build_opener(ProxyHandler({}), _NoRedirects()).open(
            request, timeout=response_timeout,
        ) as response:
            body = response.read(65537)
        if len(body) > 65536:
            raise _local_failure("CREATOR_LOCAL_RESPONSE_TOO_LARGE")
        envelope = json.loads(body)
        if not isinstance(envelope, dict):
            raise _local_failure("CREATOR_LOCAL_INVALID_RESPONSE")
        if envelope.get("done") is not True or envelope.get("done_reason") != "stop":
            raise _local_failure("CREATOR_LOCAL_INCOMPLETE_RESPONSE")
        # Ollama returns reasoning separately in message.thinking. Only final JSON
        # enters validation, persistence or logs; token accounting includes all work.
        content = envelope["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("Response content must be text")
        prompt = max(0, int(envelope.get("prompt_eval_count") or 0))
        completion = max(0, int(envelope.get("eval_count") or 0))
        return content, {
            "prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": prompt + completion,
        }
    except HTTPError as exc:
        code = ("CREATOR_LOCAL_MODEL_MISSING" if exc.code == 404 else
                "CREATOR_LOCAL_BUSY" if exc.code in {429, 503} else "CREATOR_LOCAL_HTTP_ERROR")
        raise _local_failure(code) from None
    except URLError as exc:
        code = ("CREATOR_LOCAL_TIMEOUT" if isinstance(exc.reason, TimeoutError)
                else "CREATOR_LOCAL_CONNECTION_FAILED")
        raise _local_failure(code) from None
    except TimeoutError:
        raise _local_failure("CREATOR_LOCAL_TIMEOUT") from None
    except IncompleteRead:
        raise _local_failure("CREATOR_LOCAL_INCOMPLETE_RESPONSE") from None
    except (OSError, HTTPException):
        raise _local_failure("CREATOR_LOCAL_CONNECTION_FAILED") from None
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise _local_failure("CREATOR_LOCAL_INVALID_RESPONSE") from None


def _checkpoint(task, row, database, interrupt):
    if interrupt is not None and interrupt.is_set():
        raise TaskInterruptedError("Creator drafting was interrupted")
    database.get_draft_for_execution(row["id"], UUID(str(task["id"])), task["lease_id"])


def _model_copy(task, row, database, runtime, client, interrupt):
    context = row["model_context"]
    inference_mode = context.get("inference_mode", "auto")
    if not isinstance(inference_mode, str) or inference_mode not in {"auto", "local_only"}:
        raise CreatorDraftConflictError("Stored creator inference mode is unsupported")
    grounded = context.get("drafting_contract") == "creator-grounded-plan-v2"
    messages = drafting_messages(context)
    task_id = UUID(str(task["id"]))
    if client is not None and inference_mode == "auto":
        try:
            route = client.plan()
            remaining = route.models
            while remaining:
                _checkpoint(task, row, database, interrupt)
                invocation = database.start_inference_invocation(
                    task_id=task_id, purpose="marketing.creator_draft", provider="openrouter",
                    requested_models=remaining, privacy_mode=client.privacy_mode,
                    daily_limit=route.daily_limit,
                )
                if invocation is None:
                    break
                try:
                    _checkpoint(task, row, database, interrupt)
                    remote = client.complete(messages, OpenRouterPlan(
                        models=remaining, daily_limit=route.daily_limit, free_tier=route.free_tier,
                    ))
                    try:
                        copy = parse_model_copy(remote.content, context)
                    except CreatorCopyError as exc:
                        database.fail_inference_invocation(invocation, exc.code)
                        client.reject_model(remote.selected_route)
                        remaining = remaining[remaining.index(remote.selected_route) + 1:]
                        continue
                    database.complete_inference_invocation(
                        invocation, selected_model=remote.selected_model,
                        selected_provider=remote.selected_provider,
                        prompt_tokens=remote.prompt_tokens,
                        completion_tokens=remote.completion_tokens,
                        total_tokens=remote.total_tokens, cost=remote.cost,
                        latency_ms=remote.latency_ms, fallback_attempt=remote.fallback_attempt,
                    )
                    return copy, "openrouter", remote.selected_model[:240]
                except OpenRouterError as exc:
                    database.fail_inference_invocation(invocation, exc.code)
                    if exc.failed_model not in remaining:
                        break
                    client.reject_model(exc.failed_model)
                    remaining = remaining[remaining.index(exc.failed_model) + 1:]
                except (TaskInterruptedError, InvalidTaskStateError, CreatorDraftConflictError):
                    database.fail_inference_invocation(invocation, "CREATOR_DRAFT_INTERRUPTED")
                    raise
        except OpenRouterError:
            pass
        if not runtime.openrouter_local_fallback:
            raise CreatorDraftModelError("Hosted drafting unavailable; local fallback is disabled")
    repair_code = None
    # One schema/copy repair is allowed, with its own durable invocation and lease checks.
    # Do not persist or echo rejected model output, and do not retry transport failures.
    for local_attempt in range(1, 3):
        _checkpoint(task, row, database, interrupt)
        invocation = database.start_inference_invocation(
            task_id=task_id, purpose="marketing.creator_draft", provider="ollama",
            requested_models=(runtime.local_model,), privacy_mode="local_only",
        )
        if invocation is None:
            raise CreatorDraftModelError("Local drafting could not reserve an inference attempt")
        attempt_messages = messages
        if repair_code is not None:
            attempt_messages = [*messages, {
                "role": "user",
                "content": (
                    "The previous attempt failed the fixed copy contract. Regenerate from the "
                    "same evidence and original schema. " + COPY_CORRECTIONS[repair_code]
                    + (" Return only the offered evidence_id and angle_id. Do not add prose, "
                       "facts, rationale, contacts, terms or new identifiers."
                       if grounded else
                       " Recheck the original rules: connect the recorded subject tentatively, "
                       "suggest independent testing, and keep numbers or commercial discussion "
                       "out of the email fields.")
                ),
            }]
        started = time.monotonic()
        try:
            _checkpoint(task, row, database, interrupt)
            content, usage = (
                local_draft_completion(attempt_messages, runtime.local_model, context=context)
                if grounded else local_draft_completion(attempt_messages, runtime.local_model)
            )
            copy = parse_model_copy(content, context)
        except (TaskInterruptedError, InvalidTaskStateError, CreatorDraftConflictError):
            database.fail_inference_invocation(invocation, "CREATOR_DRAFT_INTERRUPTED")
            raise
        except CreatorCopyError as exc:
            database.fail_inference_invocation(invocation, exc.code)
            repair_code = exc.code
            if local_attempt == 1:
                continue
            break
        except CreatorDraftModelError as exc:
            database.fail_inference_invocation(invocation, exc.code)
            break
        database.complete_inference_invocation(
            invocation, selected_model=runtime.local_model, selected_provider="ollama",
            **usage, cost=0, latency_ms=round((time.monotonic() - started) * 1000),
            fallback_attempt=local_attempt,
        )
        return copy, "ollama", runtime.local_model
    error_type = CreatorDraftOutputError if grounded and repair_code else CreatorDraftModelError
    raise error_type(
        "No valid AI draft was produced; review research or choose the explicit template"
    ) from None


def execute_creator_draft_task(
    task: dict, database: CreatorDraftStore, runtime: Settings,
    client: OpenRouterFreeClient | None = None, interrupt: threading.Event | None = None,
) -> dict:
    payload = task["payload"]
    if not isinstance(payload, dict) or set(payload) != {"draft_id"}:
        raise CreatorDraftModelError("Drafting task must reference exactly one stored draft")
    draft_id, task_id = UUID(str(payload["draft_id"])), UUID(str(task["id"]))
    try:
        row = database.get_draft_for_execution(draft_id, task_id, task["lease_id"])
        if row["status"] == "ready":
            # Crash after persistence cannot spend another inference request.
            return {"handler": "marketing.creator_draft", "draft_id": str(draft_id),
                    "draft_status": "ready", "source": row["source"]}
        if row["status"] != "queued":
            raise CreatorDraftConflictError("Draft is no longer awaiting a model response")
        copy, source, selected_model = _model_copy(
            task, row, database, runtime, client, interrupt,
        )
        _checkpoint(task, row, database, interrupt)
        saved = database.save_draft(
            draft_id=draft_id, task_id=task_id, lease_id=task["lease_id"], copy=copy,
            source=source, selected_model=selected_model,
        )
        return {"handler": "marketing.creator_draft", "draft_id": str(draft_id),
                "draft_status": saved["status"], "source": source}
    except (CreatorDraftModelError, CreatorDraftConflictError) as exc:
        code = ("CREATOR_DRAFT_CONTEXT_CHANGED" if isinstance(exc, CreatorDraftConflictError)
                else "CREATOR_DRAFT_OUTPUT_INVALID" if isinstance(exc, CreatorDraftOutputError)
                else "CREATOR_DRAFT_MODEL_UNAVAILABLE")
        with suppress(InvalidTaskStateError):
            database.fail_draft(draft_id, task_id, task["lease_id"], code)
        raise
