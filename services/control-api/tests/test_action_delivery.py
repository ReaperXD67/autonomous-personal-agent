import smtplib
from dataclasses import replace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app import action_worker
from app.action_store import ActionStore, SideEffectGuardError


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Mock]:
    client = Mock(spec=smtplib.SMTP)
    client.sock = Mock()
    client.ehlo.return_value = (250, b"synthetic greeting")
    client.noop.return_value = (250, b"synthetic ok")
    client.send_message.return_value = {}
    constructor = Mock(return_value=client)
    monkeypatch.setattr(action_worker.smtplib, "SMTP", constructor)
    monkeypatch.setattr(action_worker.smtplib, "SMTP_SSL", constructor)
    return client, constructor


def _runtime(**overrides):
    return replace(action_worker.settings, **{
        "mail_transport": "smtp", "smtp_host": "smtp.example.test", "smtp_port": 587,
        "smtp_username": "synthetic-account", "smtp_password": "synthetic-test-value",
        "smtp_from": "sender@example.test", "smtp_tls_mode": "starttls", **overrides,
    })


def _email() -> tuple[dict, dict, Mock]:
    action_id, task_id, lease_id = uuid4(), uuid4(), uuid4()
    action = {
        "id": action_id, "task_id": task_id, "context_hash": "frozen-digest",
        "private_context": {
            "sender": "sender@example.test", "recipient": "recipient@example.test",
            "subject": "Synthetic subject", "body": "Synthetic message.",
        },
    }
    task = {
        "id": task_id, "lease_id": lease_id, "kind": "communications.email_send",
        "payload": {"action_id": str(action_id)},
    }
    database = Mock(spec=ActionStore)
    database.get_action_for_execution.return_value = action
    return task, action, database


@pytest.mark.parametrize("tls_mode", ["starttls", "ssl"])
def test_email_records_acceptance_before_quit_even_when_cleanup_fails(smtp, tls_mode) -> None:
    client, _ = smtp
    events = []
    task, _, database = _email()
    client.login.side_effect = lambda *_: events.append("authenticated")
    database.begin_side_effect.side_effect = lambda *_: events.append("receipt")
    client.send_message.side_effect = lambda *_, **__: events.append("send") or {}
    database.complete_side_effect.side_effect = lambda *_: events.append("accepted")

    def broken_quit():
        events.append("quit")
        raise OSError("Synthetic disconnected socket")

    client.quit.side_effect = broken_quit
    output = action_worker.execute_action_task(task, database, _runtime(smtp_tls_mode=tls_mode))
    assert events == ["authenticated", "receipt", "send", "accepted", "quit"]
    assert output["smtp_accepted"] is True
    assert database.begin_side_effect.call_args.args[2] == task["lease_id"]
    message = client.send_message.call_args.args[0]
    assert message["Date"]
    assert message["Message-ID"].endswith("@example.test>")
    assert client.send_message.call_args.kwargs == {
        "from_addr": "sender@example.test",
        "to_addrs": ["recipient@example.test"],
    }
    client.close.assert_called_once()


def test_email_authentication_failure_never_creates_receipt_or_exposes_response(smtp) -> None:
    client, _ = smtp
    task, _, database = _email()
    client.login.side_effect = smtplib.SMTPAuthenticationError(535, b"private account detail")
    with pytest.raises(RuntimeError, match="authentication failed") as error:
        action_worker.execute_action_task(task, database, _runtime())
    assert "private account" not in str(error.value)
    assert error.value.__suppress_context__
    database.begin_side_effect.assert_not_called()
    client.send_message.assert_not_called()


def test_email_cancelled_or_stale_claim_cannot_send_after_authentication(smtp) -> None:
    client, _ = smtp
    task, _, database = _email()
    database.begin_side_effect.side_effect = SideEffectGuardError("Lease no longer owned")
    with pytest.raises(SideEffectGuardError):
        action_worker.execute_action_task(task, database, _runtime())
    client.login.assert_called_once()
    client.send_message.assert_not_called()
    database.complete_side_effect.assert_not_called()
    client.close.assert_called_once()


def test_email_disconnect_during_send_retains_unconfirmed_boundary(smtp) -> None:
    client, _ = smtp
    task, _, database = _email()
    client.send_message.side_effect = smtplib.SMTPServerDisconnected("private response")
    with pytest.raises(RuntimeError, match="acceptance could not be confirmed"):
        action_worker.execute_action_task(task, database, _runtime())
    database.begin_side_effect.assert_called_once()
    database.complete_side_effect.assert_not_called()


@pytest.mark.parametrize("tls_mode,username", [("starttls", "synthetic"), ("ssl", "synthetic"),
                                              ("none", "")])
def test_smtp_check_uses_fixed_transport_and_no_delivery_commands(smtp, tls_mode, username) -> None:
    client, constructor = smtp
    database = Mock(spec=ActionStore)
    transport = "mailpit" if tls_mode == "none" else "smtp"
    runtime = _runtime(smtp_tls_mode=tls_mode, smtp_username=username, mail_transport=transport)
    output = action_worker.execute_action_task(
        {"id": uuid4(), "kind": "communications.smtp_check", "payload": {}}, database, runtime,
    )
    assert output == {
        "handler": "communications.smtp_check", "transport": transport,
        "authenticated": bool(username), "tls_mode": tls_mode, "checked": True,
    }
    assert constructor.call_args.args == (runtime.smtp_host, runtime.smtp_port)
    assert constructor.call_args.kwargs["timeout"] == 30
    client.noop.assert_called_once()
    for command in ("send_message", "sendmail", "mail", "rcpt", "data"):
        getattr(client, command).assert_not_called()
    database.get_action_for_execution.assert_not_called()
    database.begin_side_effect.assert_not_called()


@pytest.mark.parametrize("payload", [{"recipient": "any@example.test"}, {"smtp_host": "other"}])
def test_smtp_check_rejects_overrides_before_connecting(smtp, payload) -> None:
    _, constructor = smtp
    with pytest.raises(ValueError, match="overrides"):
        action_worker.execute_action_task(
            {"id": uuid4(), "kind": "communications.smtp_check", "payload": payload},
            Mock(spec=ActionStore), _runtime(),
        )
    constructor.assert_not_called()


def test_smtp_check_rejects_disabled_transport_and_failed_noop(smtp) -> None:
    client, constructor = smtp
    with pytest.raises(RuntimeError, match="disabled"):
        action_worker._check_smtp(_runtime(mail_transport="disabled"))
    constructor.assert_not_called()
    client.noop.return_value = (421, b"private response")
    with pytest.raises(RuntimeError, match="check was not accepted"):
        action_worker._check_smtp(_runtime())


def test_smtp_session_cannot_start_next_phase_after_budget_expires(smtp, monkeypatch) -> None:
    client, _ = smtp
    monkeypatch.setattr(action_worker.time, "monotonic", Mock(side_effect=[0, 31]))
    with pytest.raises(RuntimeError, match="connection, TLS, or authentication failed"):
        action_worker._check_smtp(_runtime())
    client.ehlo.assert_not_called()
    client.noop.assert_not_called()


def test_browser_submit_callback_carries_current_task_lease(monkeypatch) -> None:
    task_id, lease_id, action_id = uuid4(), uuid4(), uuid4()
    database = Mock(spec=ActionStore)
    database.get_action_for_execution.return_value = {
        "id": action_id, "opportunity_id": uuid4(),
        "public_context": {"apply_url": "http://application-fixture:8081/apply",
                           "preflight_signature": "synthetic", "submit_label": "Submit"},
        "private_context": {"resolved_values": {}},
    }
    database.get_application_execution_material.return_value = {
        "resume_text": "Synthetic resume", "candidate_name": "Synthetic Candidate",
    }

    def submit(**kwargs):
        kwargs["begin_side_effect"]()
        return {"final_url": "http://application-fixture:8081/thanks",
                "confirmation_detected": True}

    monkeypatch.setattr(action_worker, "submit_application_form", submit)
    output = action_worker.execute_action_task({
        "id": task_id, "lease_id": lease_id, "kind": "career.application_submit",
        "payload": {"action_id": str(action_id)},
    }, database, _runtime())
    assert database.begin_side_effect.call_args.args[::2] == (task_id, lease_id)
    assert output["confirmation_detected"] is True
