from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import signal
import smtplib
import socket
import ssl
import tempfile
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from types import FrameType
from urllib.parse import urlparse
from uuid import UUID

import redis

from app.action_store import ActionStore
from app.application_browser import (
    inspect_application_form,
    submit_application_form,
)
from app.logging_config import configure_logging
from app.settings import Settings, get_settings
from app.worker import LeaseHeartbeat, TaskInterruptedError

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("action-worker")
stopping = False


def _stop(_signum: int, _frame: FrameType | None) -> None:
    global stopping
    stopping = True


def healthcheck() -> int:
    try:
        database = ActionStore(settings.database_url)
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        healthy = database.check() and bool(client.ping())
        client.close()
        return 0 if healthy else 1
    except Exception:
        return 1


def _send_email(
    action: dict[str, object], database: ActionStore, runtime: Settings
) -> dict[str, object]:
    if runtime.mail_transport == "disabled":
        raise RuntimeError("Email transport is disabled")
    context = action["private_context"]
    if not isinstance(context, dict):
        raise ValueError("Email action context is invalid")
    if context["sender"] != runtime.smtp_from:
        raise RuntimeError("Configured sender changed after email approval")

    message = EmailMessage()
    message["From"] = str(context["sender"])
    message["To"] = str(context["recipient"])
    message["Subject"] = str(context["subject"])
    message_id = make_msgid(idstring=str(action["id"]), domain="hermes.local")
    message["Message-ID"] = message_id
    message.set_content(str(context["body"]))
    fingerprint = hashlib.sha256(
        f"communications.email_send:{action['context_hash']}".encode()
    ).hexdigest()

    database.begin_side_effect(UUID(str(action["task_id"])), fingerprint)
    if runtime.smtp_tls_mode == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            runtime.smtp_host,
            runtime.smtp_port,
            timeout=30,
            context=ssl.create_default_context(),
        )
    else:
        client = smtplib.SMTP(runtime.smtp_host, runtime.smtp_port, timeout=30)
    try:
        client.ehlo()
        if runtime.smtp_tls_mode == "starttls":
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        if runtime.smtp_username:
            client.login(runtime.smtp_username, runtime.smtp_password)
        refused = client.send_message(message)
        if refused:
            raise RuntimeError("SMTP server refused the recipient")
    finally:
        try:
            client.quit()
        except smtplib.SMTPException:
            client.close()
    database.complete_side_effect(UUID(str(action["task_id"])), fingerprint, message_id)
    return {
        "handler": "communications.email_send",
        "action_id": str(action["id"]),
        "message_id": message_id,
        "transport": runtime.mail_transport,
    }


def execute_action_task(
    task: dict[str, object], database: ActionStore, runtime: Settings
) -> dict[str, object]:
    payload = task["payload"]
    if not isinstance(payload, dict):
        raise ValueError("Action task payload must be an object")
    task_id = UUID(str(task["id"]))

    if task["kind"] == "career.application_preflight":
        opportunity_id = UUID(str(payload["opportunity_id"]))
        opportunity = database.get_opportunity(opportunity_id)
        result = inspect_application_form(opportunity["apply_url"], runtime.environment)
        database.save_preflight(
            opportunity_id=opportunity_id,
            task_id=task_id,
            result=result,
        )
        auto_action = database.try_create_automatic_application_action(opportunity_id)
        return {
            "handler": "career.application_preflight",
            "opportunity_id": str(opportunity_id),
            "field_count": len(result["fields"]),
            "blocked_reason": result["blocked_reason"],
            "automatic_approval_task_created": auto_action is not None,
        }

    action = database.get_action_for_execution(task_id)
    if payload.get("action_id") != str(action["id"]):
        raise ValueError("Task points to a different external action")

    if task["kind"] == "communications.email_send":
        return _send_email(action, database, runtime)

    if task["kind"] == "career.application_submit":
        material = database.get_application_execution_material(action)
        public_context = action["public_context"]
        private_context = action["private_context"]
        fingerprint = hashlib.sha256(
            f"career.application_submit:{action['opportunity_id']}".encode()
        ).hexdigest()
        with tempfile.TemporaryDirectory(prefix="hermes-action-") as temporary:
            result = submit_application_form(
                url=str(public_context["apply_url"]),
                environment=runtime.environment,
                expected_signature=str(public_context["preflight_signature"]),
                expected_submit_label=str(public_context["submit_label"]),
                values=private_context["resolved_values"],
                resume_text=material["resume_text"],
                candidate_name=material["candidate_name"],
                temp_directory=Path(temporary),
                begin_side_effect=lambda: database.begin_side_effect(task_id, fingerprint),
            )
        reference = str(result["final_url"])
        database.complete_side_effect(task_id, fingerprint, reference)
        return {
            "handler": "career.application_submit",
            "action_id": str(action["id"]),
            "confirmation_detected": result["confirmation_detected"],
            "final_host": urlparse(reference).hostname,
        }

    raise ValueError("Capability is not implemented in action worker")


def run() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    database = ActionStore(settings.database_url)
    client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=settings.worker_poll_seconds + 2,
    )
    worker_id = f"action:{socket.gethostname()}:{os.getpid()}"[:120]
    logger.info("action worker started", extra={"action": "startup"})

    while not stopping:
        try:
            item = client.brpop(
                settings.action_queue_key, timeout=settings.worker_poll_seconds
            )
        except redis.exceptions.TimeoutError:
            item = None
        if item is None:
            continue

        task_id: UUID | None = None
        lease_id: UUID | None = None
        heartbeat: LeaseHeartbeat | None = None
        kind: str | None = None
        try:
            envelope = json.loads(item[1])
            task_id = UUID(envelope["task_id"])
            task = database.transition_to_running(
                task_id, settings.worker_lease_seconds, worker_id
            )
            if task is None:
                logger.warning(
                    "discarded stale action queue item",
                    extra={"task_id": str(task_id), "action": "task.discarded"},
                )
                continue
            kind = task["kind"]
            lease_id = task["lease_id"]
            with LeaseHeartbeat(
                database,
                task_id,
                lease_id,
                settings.worker_lease_seconds,
                settings.worker_heartbeat_seconds,
            ) as heartbeat:
                output = execute_action_task(task, database, settings)
            if heartbeat.reason == "cancel_requested":
                result = database.finalize_cancellation(task_id, lease_id)
            elif heartbeat.reason is not None:
                logger.warning(
                    "action task stopped after lease ownership was lost",
                    extra={"task_id": str(task_id), "action": "task.lease_lost"},
                )
                continue
            else:
                result = database.complete_task(task_id, lease_id, output)
            logger.info(
                "action task finished",
                extra={
                    "task_id": str(task_id),
                    "correlation_id": str(result["correlation_id"]),
                    "action": f"task.{result['status']}",
                },
            )
        except TaskInterruptedError:
            if (
                task_id is not None
                and lease_id is not None
                and heartbeat is not None
                and heartbeat.reason == "cancel_requested"
            ):
                database.finalize_cancellation(task_id, lease_id)
        except Exception as exc:
            logger.exception("action task failed", extra={"action": "task.failed"})
            if task_id is not None and lease_id is not None:
                if kind in {"career.application_submit", "communications.email_send"}:
                    try:
                        database.fail_external_action(task_id, str(exc))
                    except Exception:
                        logger.exception(
                            "failed to persist external action state",
                            extra={"action": "external_action.audit_failed"},
                        )
                try:
                    database.fail_task(
                        task_id, lease_id, "ACTION_EXECUTION_FAILED", str(exc)
                    )
                except Exception:
                    logger.exception(
                        "failed to persist action task failure",
                        extra={"action": "audit.failed"},
                    )

    client.close()
    logger.info("action worker stopped", extra={"action": "shutdown"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    if args.healthcheck:
        raise SystemExit(healthcheck())
    run()


if __name__ == "__main__":
    main()
