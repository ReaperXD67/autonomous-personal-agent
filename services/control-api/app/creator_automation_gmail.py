"""Read only the deployment-selected creator label; no mailbox writes or body fetches."""

from __future__ import annotations

import hashlib
import threading
from typing import Any
from uuid import UUID

from app.career_tracking import (
    MAX_GET,
    GmailReadClient,
    GmailResourceGoneError,
    GmailSyncError,
    normalize_message,
)


def execute_creator_gmail_sync(
    task: dict[str, Any], store: Any, settings: Any, interrupt: threading.Event | None = None
) -> dict[str, Any]:
    if not settings.creator_gmail_enabled:
        raise GmailSyncError("Creator Gmail integration is disabled")
    if not settings.creator_gmail_mailbox or not settings.gmail_creator_label:
        raise GmailSyncError("Configure an explicit creator mailbox identity and custom label")
    if settings.gmail_creator_label == settings.gmail_career_label:
        raise GmailSyncError("Creator replies require a separate Gmail label")

    def checkpoint() -> None:
        if interrupt is not None and interrupt.is_set():
            raise GmailSyncError("Creator Gmail sync was interrupted")

    campaign_id = UUID(str(task["payload"]["campaign_id"]))
    store.get_campaign(campaign_id)
    checkpoint()
    client = GmailReadClient(
        settings.gmail_client_id, settings.gmail_client_secret, settings.gmail_refresh_token
    )
    mailbox = client.mailbox()
    if mailbox != settings.creator_gmail_mailbox.casefold():
        raise GmailSyncError("Gmail mailbox does not match the configured creator mailbox")
    label = settings.gmail_creator_label
    label_id = client.label_id(label)
    state = store.gmail_context(campaign_id, hashlib.sha256(mailbox.encode()).hexdigest(), label)
    pending, cursor = list(state["pending_message_ids"]), state["page_token"]
    if not pending:
        checkpoint()
        pending, cursor = client.list_messages(label_id, cursor)
    known = store.known_reply_ids(campaign_id, pending)
    remaining = [item for item in pending if item not in known]
    messages, consumed = [], []
    for message_id in remaining[:MAX_GET]:
        checkpoint()
        try:
            raw = client.message(message_id)
        except GmailResourceGoneError:
            consumed.append(message_id)
            continue
        message = normalize_message(raw, expected_id=message_id, label_id=label_id, mailbox=mailbox)
        consumed.append(message_id)
        if message:
            messages.append(message)
    pending = [item for item in remaining if item not in consumed]
    checkpoint()
    result = store.save_gmail(task, state, messages, cursor=cursor, pending=pending)
    return {
        "handler": "marketing.gmail_sync",
        **result,
        "fetched": len(consumed),
        "pending": len(pending),
        "more_pages": bool(cursor),
        "mailbox_modified": False,
    }
