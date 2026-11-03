import io
import json
from dataclasses import replace
from http.client import HTTPException, IncompleteRead, RemoteDisconnected
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from urllib.request import HTTPHandler, build_opener
from urllib.response import addinfourl

import pytest
from test_creator_grounded_runner import grounded_setup

from app import creator_drafting
from app.creator_draft_store import CreatorDraftConflictError
from app.settings import get_settings


def transport(monkeypatch, *, body=None, open_error=None, read_error=None):
    received = Mock()
    received.read.return_value = body
    if read_error is not None:
        received.read.side_effect = read_error
    opener = Mock()
    opener.open.return_value.__enter__ = Mock(return_value=received)
    opener.open.return_value.__exit__ = Mock(return_value=False)
    if open_error is not None:
        opener.open.side_effect = open_error
    monkeypatch.setattr(creator_drafting, "build_opener", Mock(return_value=opener))
    return opener, received


@pytest.mark.parametrize(("error", "code"), [
    (TimeoutError("PRIVATE_SOCKET_DETAIL"), "CREATOR_LOCAL_TIMEOUT"),
    (URLError(TimeoutError("PRIVATE_SOCKET_DETAIL")), "CREATOR_LOCAL_TIMEOUT"),
    (URLError("PRIVATE_ENDPOINT_DETAIL"), "CREATOR_LOCAL_CONNECTION_FAILED"),
    (ConnectionResetError("PRIVATE_SOCKET_DETAIL"), "CREATOR_LOCAL_CONNECTION_FAILED"),
    (RemoteDisconnected("PRIVATE_SOCKET_DETAIL"), "CREATOR_LOCAL_CONNECTION_FAILED"),
    (HTTPException("PRIVATE_PROTOCOL_DETAIL"), "CREATOR_LOCAL_CONNECTION_FAILED"),
])
@pytest.mark.parametrize("phase", ["open", "read"])
def test_transport_disconnects_are_accounted_and_never_retried(monkeypatch, error, code, phase):
    task, _, database, _ = grounded_setup()
    opener, received = transport(monkeypatch, **{phase + "_error": error})
    with pytest.raises(creator_drafting.CreatorDraftModelError) as caught:
        creator_drafting.execute_creator_draft_task(task, database, get_settings())
    assert opener.open.call_count == database.start_inference_invocation.call_count == 1
    assert opener.open.call_args.kwargs["timeout"] == 300
    assert database.fail_inference_invocation.call_args.args[1] == code
    assert database.fail_draft.call_args.args[-1] == "CREATOR_DRAFT_MODEL_UNAVAILABLE"
    database.complete_inference_invocation.assert_not_called()
    database.save_draft.assert_not_called()
    assert "PRIVATE_" not in str(caught.value) + repr(database.mock_calls)
    assert caught.value.__suppress_context__
    if phase == "read":
        received.read.assert_called_once_with(65537)


def test_incomplete_http_body_records_failure_instead_of_leaving_a_queued_draft(monkeypatch):
    task, _, database, _ = grounded_setup()
    opener, _ = transport(monkeypatch, read_error=IncompleteRead(b"PRIVATE_PARTIAL_BODY", 50))
    with pytest.raises(creator_drafting.CreatorDraftModelError):
        creator_drafting.execute_creator_draft_task(task, database, get_settings())
    assert opener.open.call_count == 1
    assert database.fail_inference_invocation.call_args.args[1] == (
        "CREATOR_LOCAL_INCOMPLETE_RESPONSE"
    )
    assert database.fail_draft.call_args.args[-1] == "CREATOR_DRAFT_MODEL_UNAVAILABLE"
    assert "PRIVATE_PARTIAL_BODY" not in repr(database.mock_calls)
    database.save_draft.assert_not_called()


@pytest.mark.parametrize(("status", "code"), [
    (404, "CREATOR_LOCAL_MODEL_MISSING"),
    (429, "CREATOR_LOCAL_BUSY"), (503, "CREATOR_LOCAL_BUSY"),
    (400, "CREATOR_LOCAL_HTTP_ERROR"), (500, "CREATOR_LOCAL_HTTP_ERROR"),
])
def test_http_failures_use_fixed_codes_without_reading_provider_bodies(monkeypatch, status, code):
    task, _, database, _ = grounded_setup()
    raw = io.BytesIO(b"PRIVATE_PROVIDER_ERROR_BODY")
    error = HTTPError("http://ollama:11434/api/chat", status, "PRIVATE_REASON", {}, raw)
    opener, _ = transport(monkeypatch, open_error=error)
    with pytest.raises(creator_drafting.CreatorDraftModelError) as caught:
        creator_drafting.execute_creator_draft_task(task, database, get_settings())
    assert opener.open.call_count == 1 and raw.tell() == 0
    assert database.fail_inference_invocation.call_args.args[1] == code
    assert "PRIVATE_" not in str(caught.value) + repr(database.mock_calls)
    database.save_draft.assert_not_called()


@pytest.mark.parametrize("completion", [
    {}, {"done": False, "done_reason": "stop"}, {"done": 1, "done_reason": "stop"},
    {"done": True}, {"done": True, "done_reason": "length"},
    {"done": True, "done_reason": "load"}, {"done": True, "done_reason": "unload"},
    {"done": True, "done_reason": {"PRIVATE_REASON": True}},
])
def test_plan_without_completed_generation_does_not_become_a_draft(monkeypatch, completion):
    task, _, database, plan = grounded_setup()
    opener, _ = transport(monkeypatch, body=json.dumps({
        **completion, "message": {"content": json.dumps(plan)},
    }).encode())
    with pytest.raises(creator_drafting.CreatorDraftModelError):
        creator_drafting.execute_creator_draft_task(task, database, get_settings())
    assert opener.open.call_count == 1
    assert database.fail_inference_invocation.call_args.args[1] == (
        "CREATOR_LOCAL_INCOMPLETE_RESPONSE"
    )
    database.save_draft.assert_not_called()
    database.complete_inference_invocation.assert_not_called()


@pytest.mark.parametrize(("body", "code"), [
    (b"PRIVATE_INVALID_JSON", "CREATOR_LOCAL_INVALID_RESPONSE"),
    (b"[]", "CREATOR_LOCAL_INVALID_RESPONSE"),
    (b"[" * 1500 + b"0" + b"]" * 1500, "CREATOR_LOCAL_INVALID_RESPONSE"),
    (b"x" * 65537, "CREATOR_LOCAL_RESPONSE_TOO_LARGE"),
    (b'{"done":true,"done_reason":"stop","message":{}}', "CREATOR_LOCAL_INVALID_RESPONSE"),
])
def test_bounded_invalid_envelopes_never_receive_a_copy_repair_or_save(monkeypatch, body, code):
    task, _, database, _ = grounded_setup()
    opener, received = transport(monkeypatch, body=body)
    with pytest.raises(creator_drafting.CreatorDraftModelError) as caught:
        creator_drafting.execute_creator_draft_task(task, database, get_settings())
    received.read.assert_called_once_with(65537)
    assert opener.open.call_args.kwargs["timeout"] == 300
    assert opener.open.call_count == 1
    assert database.fail_inference_invocation.call_args.args[1] == code
    assert "PRIVATE_" not in str(caught.value) + repr(database.mock_calls)
    database.save_draft.assert_not_called()


def test_local_only_uses_frozen_mode_without_even_planning_a_hosted_request(monkeypatch):
    task, row, database, plan = grounded_setup()
    row["model_context"]["inference_mode"] = "local_only"
    client = Mock()
    client.plan.side_effect = AssertionError("Hosted catalog/plan is forbidden in local-only mode")
    opener, _ = transport(monkeypatch, body=json.dumps({
        "done": True, "done_reason": "stop", "message": {"content": json.dumps(plan)},
        "prompt_eval_count": 40, "eval_count": 10,
    }).encode())
    result = creator_drafting.execute_creator_draft_task(
        task, database, replace(get_settings(), openrouter_local_fallback=False), client=client,
    )
    assert result["source"] == "ollama"
    assert client.mock_calls == []
    assert database.start_inference_invocation.call_count == 1
    reservation = database.start_inference_invocation.call_args.kwargs
    assert reservation["provider"] == "ollama" and reservation["privacy_mode"] == "local_only"
    assert database.complete_inference_invocation.call_args.kwargs["total_tokens"] == 50
    request = opener.open.call_args.args[0]
    assert request.full_url == "http://ollama:11434/api/chat"
    payload = json.loads(request.data)
    assert payload["think"] is False and payload["options"]["num_predict"] == 512
    database.save_draft.assert_called_once()


@pytest.mark.parametrize("mode", [
    "PRIVATE_UNKNOWN_MODE", "https://PRIVATE_ENDPOINT", [], None, False,
])
def test_invalid_frozen_mode_fails_terminally_before_any_egress_or_reservation(monkeypatch, mode):
    task, row, database, _ = grounded_setup()
    row["model_context"]["inference_mode"] = mode
    client = Mock()
    complete = Mock(side_effect=AssertionError("Local request is forbidden for an invalid mode"))
    monkeypatch.setattr(creator_drafting, "local_draft_completion", complete)
    with pytest.raises(CreatorDraftConflictError) as caught:
        creator_drafting.execute_creator_draft_task(task, database, get_settings(), client=client)
    assert "PRIVATE_" not in str(caught.value)
    assert client.mock_calls == []
    complete.assert_not_called()
    database.start_inference_invocation.assert_not_called()
    assert database.fail_draft.call_args.args[-1] == "CREATOR_DRAFT_CONTEXT_CHANGED"
    database.save_draft.assert_not_called()


def test_redirects_are_fixed_failures_with_no_destination_disclosure():
    handler = creator_drafting._NoRedirects()
    with pytest.raises(creator_drafting.CreatorDraftModelError) as caught:
        handler.redirect_request(None, None, 302, "PRIVATE_REASON", {}, "https://PRIVATE_TARGET")
    assert caught.value.code == "CREATOR_LOCAL_REDIRECT_REFUSED"
    assert "PRIVATE_" not in str(caught.value)


def test_local_only_ignores_environment_proxy_without_opening_network(monkeypatch):
    task, row, database, plan = grounded_setup()
    row["model_context"]["inference_mode"] = "local_only"
    for name in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://proxy.invalid:3128")
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
    observed = []

    class NoNetworkHTTP(HTTPHandler):
        def http_open(self, request):
            observed.append((request.host, request.selector))
            body = json.dumps({
                "done": True, "done_reason": "stop", "message": {"content": json.dumps(plan)},
                "prompt_eval_count": 4, "eval_count": 2,
            }).encode()
            response = addinfourl(io.BytesIO(body), {}, request.full_url, 200)
            response.msg = "OK"
            return response

    # Use the real opener and its proxy-routing machinery, replacing only the
    # final socket-capable handler. A default environmental proxy would change
    # request.host to proxy.invalid before reaching this deterministic fake.
    monkeypatch.setattr(creator_drafting, "build_opener", lambda *handlers: build_opener(
        *handlers, NoNetworkHTTP(),
    ))
    creator_drafting.execute_creator_draft_task(task, database, get_settings(), client=Mock())
    assert observed == [("ollama:11434", "/api/chat")]
    assert database.complete_inference_invocation.call_args.kwargs["total_tokens"] == 6
    database.save_draft.assert_called_once()
