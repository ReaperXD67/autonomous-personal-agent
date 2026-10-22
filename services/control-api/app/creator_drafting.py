from __future__ import annotations

import json
import threading
import time
from contextlib import suppress
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from app.creator_draft_content import (
    COPY_CORRECTIONS,
    CreatorCopyError,
    drafting_messages,
    parse_model_copy,
)
from app.creator_draft_models import CreatorModelCopy
from app.creator_draft_store import CreatorDraftConflictError, CreatorDraftStore
from app.inference import OpenRouterError, OpenRouterFreeClient, OpenRouterPlan
from app.settings import Settings
from app.store import InvalidTaskStateError
from app.worker import TaskInterruptedError


class CreatorDraftModelError(RuntimeError):
    pass


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CreatorDraftModelError("Local drafting endpoint redirects are disabled")


def local_draft_completion(messages, model):
    request = Request(
        "http://ollama:11434/api/chat", method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        data=json.dumps({
            "model": model, "messages": messages, "stream": False, "think": False,
            "format": CreatorModelCopy.model_json_schema(),
            "options": {"temperature": 0.3, "num_predict": 1100},
        }).encode("utf-8"),
    )
    try:
        with build_opener(_NoRedirects()).open(request, timeout=180) as response:
            body = response.read(65537)
        if len(body) > 65536:
            raise ValueError("Response too large")
        envelope = json.loads(body)
        content = envelope["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("Response content must be text")
        prompt = max(0, int(envelope.get("prompt_eval_count") or 0))
        completion = max(0, int(envelope.get("eval_count") or 0))
        return content, {
            "prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": prompt + completion,
        }
    except (HTTPError, URLError, TimeoutError, KeyError, TypeError, ValueError):
        raise CreatorDraftModelError("Local drafting model returned no valid response") from None


def _checkpoint(task, row, database, interrupt):
    if interrupt is not None and interrupt.is_set():
        raise TaskInterruptedError("Creator drafting was interrupted")
    database.get_draft_for_execution(row["id"], UUID(str(task["id"])), task["lease_id"])


def _model_copy(task, row, database, runtime, client, interrupt):
    context = row["model_context"]
    messages = drafting_messages(context)
    task_id = UUID(str(task["id"]))
    if client is not None:
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
                    + " Recheck every original field rule: the hook explicitly refers to the "
                    "public title, the idea suggests independent testing, and numbers or "
                    "commercial discussion belong only in the operator rationale."
                ),
            }]
        started = time.monotonic()
        try:
            _checkpoint(task, row, database, interrupt)
            content, usage = local_draft_completion(attempt_messages, runtime.local_model)
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
        except CreatorDraftModelError:
            database.fail_inference_invocation(invocation, "CREATOR_LOCAL_UNAVAILABLE")
            break
        database.complete_inference_invocation(
            invocation, selected_model=runtime.local_model, selected_provider="ollama",
            **usage, cost=0, latency_ms=round((time.monotonic() - started) * 1000),
            fallback_attempt=local_attempt,
        )
        return copy, "ollama", runtime.local_model
    raise CreatorDraftModelError(
        "No valid AI draft was produced; review research or choose the explicit template"
    )


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
                else "CREATOR_DRAFT_MODEL_UNAVAILABLE")
        with suppress(InvalidTaskStateError):
            database.fail_draft(draft_id, task_id, task["lease_id"], code)
        raise
