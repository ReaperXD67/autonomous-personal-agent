from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app import auth
from app.readiness import FeatureReport, ReadinessStore, feature_catalog, router

TEST_TOKEN = "synthetic-readiness-test-" * 2


def report_payload(*, completed_at=None, statuses=None, signals=None):
    completed_at = completed_at or datetime.now(UTC) - timedelta(seconds=1)
    statuses = statuses or {"core": "passed", "openrouter": "passed", "planning": "passed"}
    return {
        "run_id": str(uuid4()),
        "git_commit": "a" * 40,
        "working_tree_dirty": False,
        "started_at": (completed_at - timedelta(minutes=2)).isoformat(),
        "completed_at": completed_at.isoformat(),
        "checks": [
            {"id": key, "status": value, "duration_seconds": 1.2} for key, value in statuses.items()
        ],
        "signals": {
            "core_online": True,
            "research_worker_online": True,
            "action_worker_online": True,
            "ollama_online": True,
            "hermes_online": True,
            "omniroute_online": True,
            "openrouter_enabled": True,
            "youtube_configured": True,
            "mail_transport": "mailpit",
            "external_smtp_configured": False,
            "local_model_cached": True,
            **(signals or {}),
        },
    }


def catalog_features(payload, counts=None, **kwargs):
    result = feature_catalog(
        FeatureReport.model_validate(payload) if payload else None,
        counts if counts is not None else {"profiles": 1, "resumes": 1, "campaigns": 1},
        **kwargs,
    )
    return result, {feature["id"]: feature for feature in result["features"]}


@pytest.mark.parametrize("location", ["root", "check", "signals"])
def test_report_rejects_unapproved_metadata_fields(location):
    payload = report_payload()
    target = (
        payload
        if location == "root"
        else payload["checks"][0]
        if location == "check"
        else payload["signals"]
    )
    target["raw_provider_response"] = "Synthetic unapproved metadata"
    with pytest.raises(ValidationError, match="Extra inputs"):
        FeatureReport.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "arbitrary_remote_shell"),
        ("status", "operational"),
        ("reason_code", "Provider response containing arbitrary content"),
        ("duration_seconds", float("inf")),
        ("duration_seconds", float("nan")),
        ("duration_seconds", -1),
    ],
)
def test_report_rejects_untrusted_check_values(field, value):
    payload = report_payload()
    payload["checks"][0][field] = value
    with pytest.raises(ValidationError):
        FeatureReport.model_validate(payload)


def test_report_rejects_duplicate_checks_and_non_boolean_signals():
    payload = report_payload()
    payload["checks"].append(payload["checks"][0].copy())
    with pytest.raises(ValidationError, match="only once"):
        FeatureReport.model_validate(payload)
    payload = report_payload()
    payload["signals"]["core_online"] = "true"
    with pytest.raises(ValidationError):
        FeatureReport.model_validate(payload)


@pytest.mark.parametrize("variant", ["naive", "reversed", "future", "too_long"])
def test_report_rejects_invalid_evidence_timestamps(variant):
    payload = report_payload()
    if variant == "naive":
        payload["completed_at"] = "2026-01-01T12:00:00"
    elif variant == "reversed":
        payload["started_at"] = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()
    elif variant == "future":
        payload["completed_at"] = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    else:
        payload["started_at"] = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    with pytest.raises(ValidationError):
        FeatureReport.model_validate(payload)


def test_no_report_never_claims_operational_or_verified_features():
    catalog, features = catalog_features(None)
    assert catalog["last_report"] is None
    assert catalog["stats"]["verified"] == 0
    assert features["future_integrations"]["status"] == "unavailable"
    assert all(feature["evidence"] is None for feature in features.values())


def test_passing_report_links_recorded_evidence_without_exposing_signals():
    payload = report_payload()
    catalog, features = catalog_features(payload)
    assert features["tasks"]["status"] == "verified"
    assert features["tasks"]["evidence"]["run_id"] == payload["run_id"]
    assert features["tasks"]["evidence"]["check_id"] == "core"
    assert "not current availability" in features["tasks"]["reason"]
    assert "signals" not in catalog["last_report"]


def test_failed_and_skipped_checks_do_not_borrow_another_features_proof():
    _, features = catalog_features(
        report_payload(
            statuses={
                "core": "passed",
                "openrouter": "passed",
                "career": "failed",
                "planning": "skipped",
            }
        )
    )
    assert features["tasks"]["status"] == "verified"
    assert features["career_search"]["status"] == "configured"
    assert "recorded check failed" in features["career_search"]["reason"]
    assert features["career_search"]["evidence"] is None
    assert features["planning"]["status"] == "configured"
    assert features["planning"]["evidence"] is None


def test_stale_passes_retain_historical_reference_but_lose_verified_status():
    now = datetime.now(UTC)
    payload = report_payload(completed_at=now - timedelta(hours=25))
    catalog, features = catalog_features(payload, now=now)
    assert catalog["last_report"]["stale"] is True
    assert catalog["stats"]["verified"] == 0
    assert features["tasks"]["evidence"]["run_id"] == payload["run_id"]
    assert "24 hours" in features["tasks"]["reason"]
    assert features["application_drafts"]["status"] == "needs_setup"


def test_prerequisites_override_a_recent_passing_feature_check():
    _, features = catalog_features(
        report_payload(
            statuses={
                "core": "passed",
                "career": "passed",
                "side_effects": "passed",
                "youtube": "passed",
            },
            signals={
                "research_worker_online": False,
                "action_worker_online": False,
                "youtube_configured": False,
            },
        ),
        counts={"profiles": 0, "resumes": 0, "campaigns": 0},
    )
    for key in ("career_search", "application_drafts", "application_submit", "creator_discovery"):
        assert features[key]["status"] == "needs_setup"
        assert any(not requirement["met"] for requirement in features[key]["requirements"])
        assert features[key]["reason"].startswith("Next:")


def test_mailpit_proof_cannot_verify_external_smtp():
    _, features = catalog_features(
        report_payload(
            statuses={"side_effects": "passed", "creator_outreach": "passed"},
            signals={"mail_transport": "smtp", "external_smtp_configured": True},
        )
    )
    assert features["external_email"]["status"] == "configured"
    assert features["external_email"]["evidence"] is None
    assert features["email_test"]["status"] == "needs_setup"


def test_core_prerequisite_overrides_a_previous_success():
    _, features = catalog_features(report_payload(signals={"core_online": False}))
    assert features["tasks"]["status"] == "needs_setup"
    assert features["workflows"]["status"] == "needs_setup"
    assert features["tasks"]["evidence"] is not None


def test_hosted_proof_does_not_satisfy_a_disabled_inference_route():
    _, features = catalog_features(report_payload(
        statuses={"openrouter": "passed", "career": "passed"},
        signals={"openrouter_enabled": False, "ollama_online": False, "local_model_cached": False},
    ))
    assert features["inference"]["status"] == "needs_setup"
    assert features["application_drafts"]["status"] == "needs_setup"


@pytest.mark.parametrize("online,cached", [(False, True), (True, False), (True, True)])
def test_local_proof_requires_both_daemon_and_cached_model(online, cached):
    _, features = catalog_features(report_payload(
        statuses={"local_model": "passed", "career": "passed"},
        signals={
            "openrouter_enabled": False, "ollama_online": online, "local_model_cached": cached,
        },
    ))
    expected = "verified" if online and cached else "needs_setup"
    assert features["inference"]["status"] == expected
    assert features["application_drafts"]["status"] == expected


class ReportConnection:
    def __init__(self):
        self.reports = {}

    def execute(self, query, params):
        if "INSERT INTO feature_test_runs" in query:
            run_id = params[0]
            inserted = run_id not in self.reports
            if inserted:
                self.reports[run_id] = params[-1].obj
            return SimpleNamespace(fetchone=lambda: {"id": run_id} if inserted else None)
        assert "SELECT report FROM feature_test_runs" in query
        return SimpleNamespace(fetchone=lambda: {"report": self.reports[params[0]]})


def test_report_ingestion_is_idempotent_conflict_checked_and_audit_redacted(monkeypatch):
    connection = ReportConnection()
    audits = []
    store = ReadinessStore("unused-test-dsn")

    @contextmanager
    def connect():
        yield connection

    monkeypatch.setattr(store, "connect", connect)
    monkeypatch.setattr(store, "_append_audit", lambda _connection, **event: audits.append(event))
    report = FeatureReport.model_validate(report_payload())
    assert store.record_report(report) == {"run_id": str(report.run_id), "recorded": True}
    assert store.record_report(report)["recorded"] is True
    assert len(audits) == 1
    assert audits[0]["input_metadata"] == {"run_id": str(report.run_id)}
    assert audits[0]["result_metadata"] == {"checks": len(report.checks)}
    changed = report.model_copy(update={"working_tree_dirty": True})
    with pytest.raises(ValueError, match="different evidence"):
        store.record_report(changed)
    assert len(audits) == 1
    assert connection.reports[report.run_id]["working_tree_dirty"] is False


async def asgi_request(application, path, *, method="GET", headers=(), body=None):
    sent = []
    payload = b"" if body is None else json.dumps(body).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json"), *headers],
    }

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message):
        sent.append(message)

    await application(scope, receive, send)
    status = next(message["status"] for message in sent if message["type"] == "http.response.start")
    data = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    return status, json.loads(data)


def test_report_endpoint_requires_bearer_even_with_valid_browser_session_and_csrf(monkeypatch):
    manager = auth.BrowserSessionManager(TEST_TOKEN, 3600)
    session = manager.consume_bootstrap(manager.issue_bootstrap())
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(api_token=TEST_TOKEN))
    monkeypatch.setattr(auth, "get_browser_sessions", lambda: manager)
    recorded = []
    application = FastAPI()
    application.include_router(router)
    application.state.readiness = SimpleNamespace(
        record_report=lambda report: recorded.append(report) or {"recorded": True},
        features=lambda: {"features": []},
    )
    browser_headers = [
        (b"cookie", f"{auth.BROWSER_SESSION_COOKIE}={session.cookie}".encode()),
        (b"origin", b"http://testserver"),
        (b"x-hermes-csrf", session.csrf_token.encode()),
    ]
    payload = report_payload()
    status, _ = asyncio.run(
        asgi_request(application, "/v1/readiness/features", headers=browser_headers)
    )
    assert status == 200
    status, _ = asyncio.run(
        asgi_request(
            application,
            "/v1/readiness/reports",
            method="POST",
            headers=browser_headers,
            body=payload,
        )
    )
    assert status == 401
    status, _ = asyncio.run(
        asgi_request(
            application,
            "/v1/readiness/reports",
            method="POST",
            headers=[(b"authorization", b"Bearer incorrect")],
            body=payload,
        )
    )
    assert status == 403
    assert recorded == []
    status, _ = asyncio.run(
        asgi_request(
            application,
            "/v1/readiness/reports",
            method="POST",
            headers=[(b"authorization", f"Bearer {TEST_TOKEN}".encode())],
            body=payload,
        )
    )
    assert status == 200
    assert len(recorded) == 1


def test_readiness_http_maps_conflicts_and_rejects_unknown_metadata(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(api_token=TEST_TOKEN))
    application = FastAPI()
    application.include_router(router)

    def conflict(_report):
        raise ValueError("This run ID already records different evidence")

    application.state.readiness = SimpleNamespace(record_report=conflict)
    headers = [(b"authorization", f"Bearer {TEST_TOKEN}".encode())]
    status, data = asyncio.run(
        asgi_request(
            application,
            "/v1/readiness/reports",
            method="POST",
            headers=headers,
            body=report_payload(),
        )
    )
    assert status == 409
    assert "different evidence" in data["detail"]
    payload = report_payload()
    payload["unapproved_log"] = "Synthetic text"
    status, _ = asyncio.run(
        asgi_request(
            application, "/v1/readiness/reports", method="POST", headers=headers, body=payload
        )
    )
    assert status == 422
