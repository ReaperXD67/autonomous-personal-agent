import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI

from app import auth, communication_routes
from app.action_store import ExternalActionNotFoundError
from app.policy import RiskLevel, capability_max_attempts, effective_risk

TEST_TOKEN = "synthetic-communications-test-" * 2


async def _request(application, path, *, method="GET", headers=(), body=None):
    sent = []
    encoded = json.dumps(body).encode() if body is not None else b""
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "", "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json"), *headers],
    }

    async def receive():
        return {"type": "http.request", "body": encoded, "more_body": False}

    async def send(message):
        sent.append(message)

    await application(scope, receive, send)
    status = next(item["status"] for item in sent if item["type"] == "http.response.start")
    data = b"".join(item.get("body", b"") for item in sent if item["type"] == "http.response.body")
    return status, json.loads(data)


@pytest.fixture
def api(monkeypatch):
    manager = auth.BrowserSessionManager(TEST_TOKEN, 3600)
    session = manager.consume_bootstrap(manager.issue_bootstrap())
    runtime = SimpleNamespace(
        api_token=TEST_TOKEN,
        mail_transport="smtp",
        smtp_from="synthetic-private-sender@example.test",
        outbound_email_min_interval_seconds=900,
        outbound_email_domain_min_interval_seconds=1800,
        outbound_email_hourly_limit=3,
        outbound_email_daily_limit=12,
        outbound_email_jitter_seconds=180,
    )
    monkeypatch.setattr(auth, "get_settings", lambda: runtime)
    monkeypatch.setattr(communication_routes, "get_settings", lambda: runtime)
    monkeypatch.setattr(auth, "get_browser_sessions", lambda: manager)
    application = FastAPI()
    application.include_router(communication_routes.router)
    application.state.database = MagicMock()
    application.state.actions = Mock()
    now = datetime.now(UTC)

    def created(request):
        return {
            **request.model_dump(), "id": uuid4(), "correlation_id": uuid4(), "output": None,
            "status": "queued", "approved_by": None, "error_code": None, "error_message": None,
            "attempt_count": 0, "max_attempts": capability_max_attempts(request.kind),
            "created_at": now, "updated_at": now, "started_at": None, "completed_at": None,
            "lease_expires_at": None, "next_attempt_at": now, "cancellation_requested_at": None,
            "cancellation_requested_by": None, "cancellation_reason": None,
            "dead_lettered_at": None,
        }

    application.state.database.create_task.side_effect = created
    connection = application.state.database.connect.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.return_value = None
    bearer = [(b"authorization", f"Bearer {TEST_TOKEN}".encode())]
    browser = [(b"cookie", f"{auth.BROWSER_SESSION_COOKIE}={session.cookie}".encode()),
               (b"origin", b"http://testserver"),
               (b"x-hermes-csrf", session.csrf_token.encode())]
    return application, connection, bearer, browser


@pytest.mark.parametrize("browser_session", [False, True])
def test_smtp_check_enqueues_only_fixed_medium_risk_single_attempt_task(api, browser_session):
    application, _, bearer, browser = api
    status, result = asyncio.run(_request(
        application, "/v1/communications/smtp-check", method="POST",
        headers=browser if browser_session else bearer, body={"requested_by": "synthetic-operator"},
    ))
    assert status == 201
    assert result["payload"] == {}
    assert result["risk_level"] == "medium"
    assert result["max_attempts"] == 1
    assert result["status"] == "queued"
    request = application.state.database.create_task.call_args.args[0]
    assert request.kind == "communications.smtp_check"
    assert effective_risk(request.kind, RiskLevel.LOW) == RiskLevel.MEDIUM
    assert capability_max_attempts(request.kind) == 1


@pytest.mark.parametrize("variant", ["missing", "invalid_bearer", "missing_csrf", "wrong_origin"])
def test_smtp_check_requires_authentication_and_browser_csrf(api, variant):
    application, _, _, browser = api
    headers = {
        "missing": [], "invalid_bearer": [(b"authorization", b"Bearer incorrect")],
        "missing_csrf": browser[:2],
        "wrong_origin": [browser[0], (b"origin", b"https://other.example.test"), browser[2]],
    }[variant]
    status, _ = asyncio.run(_request(
        application, "/v1/communications/smtp-check", method="POST", headers=headers,
        body={"requested_by": "synthetic-operator"},
    ))
    assert status == (401 if variant == "missing" else 403)
    application.state.database.create_task.assert_not_called()


@pytest.mark.parametrize("extra", [{"smtp_host": "other.example.test"}, {"payload": {}},
                                   {"recipient": "recipient@example.test"}, {"risk_level": "low"}])
def test_smtp_check_rejects_unknown_request_fields(api, extra):
    application, _, bearer, _ = api
    status, _ = asyncio.run(_request(
        application, "/v1/communications/smtp-check", method="POST", headers=bearer,
        body={"requested_by": "synthetic-operator", **extra},
    ))
    assert status == 422
    application.state.database.create_task.assert_not_called()


@pytest.mark.parametrize("output", [None, "private text", ["private text"], 12,
    {"smtp_password": "private value", "handler": "communications.smtp_check",
     "transport": "smtp", "authenticated": True, "tls_mode": "starttls", "checked": True},
    {"handler": {"private": "value"}, "transport": "private text",
     "authenticated": "private text", "tls_mode": ["private text"], "checked": 1},
])
def test_status_exposes_only_allowlisted_transport_proof_without_raw_payload(api, output):
    application, connection, _, browser = api
    check = {"id": uuid4(), "status": "succeeded", "completed_at": datetime.now(UTC),
             "output": output, "error_code": None}
    connection.execute.return_value.fetchone.return_value = check
    status, result = asyncio.run(_request(
        application, "/v1/communications/status", headers=browser[:1],
    ))
    assert status == 200
    assert result["sender_configured"] is True
    assert result["transport"] == "smtp"
    assert result["pacing"] == {
        "enabled": True,
        "minimum_interval_seconds": 900,
        "same_domain_interval_seconds": 1800,
        "hourly_limit": 3,
        "daily_limit": 12,
        "jitter_seconds": 180,
    }
    assert "private" not in json.dumps(result)
    expected = output.copy() if isinstance(output, dict) and output.get("checked") is True else {}
    expected.pop("smtp_password", None)
    assert result["latest_check"]["output"] == expected
    assert check["output"] is output


def test_communication_read_routes_require_auth_and_handle_missing_action(api):
    application, _, bearer, _ = api
    action_id = uuid4()
    application.state.actions.get_external_action.side_effect = ExternalActionNotFoundError()
    for path in ("/v1/communications/status", f"/v1/external-actions/{action_id}"):
        status, _ = asyncio.run(_request(application, path))
        assert status == 401
    application.state.actions.get_external_action.assert_not_called()
    status, result = asyncio.run(_request(
        application, f"/v1/external-actions/{action_id}", headers=bearer,
    ))
    assert status == 404
    assert result == {"detail": "External action not found"}
    application.state.actions.get_external_action.assert_called_once_with(action_id)


def test_exact_action_response_projects_public_fields_only(api):
    application, _, bearer, _ = api
    action_id = uuid4()
    now = datetime.now(UTC)
    application.state.actions.get_external_action.return_value = {
        "id": action_id, "task_id": uuid4(), "opportunity_id": None,
        "action_type": "communications.email_send", "status": "pending_approval",
        "target_display": "recipient@example.test", "public_context": {"subject": "Reviewed"},
        "private_context": {"hidden": "private content"}, "idempotency_key": "private key",
        "context_hash": "a" * 64, "expires_at": now, "external_reference": None,
        "last_error": None, "created_at": now, "updated_at": now, "executed_at": None,
    }
    status, result = asyncio.run(_request(
        application, f"/v1/external-actions/{action_id}", headers=bearer,
    ))
    assert status == 200
    assert result["id"] == str(action_id)
    assert result["public_context"] == {"subject": "Reviewed"}
    assert "private" not in json.dumps(result)
    assert "idempotency_key" not in result
