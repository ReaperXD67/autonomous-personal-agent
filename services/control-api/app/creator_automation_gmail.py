"""Read bounded metadata and selected full replies from the configured creator label."""

from __future__ import annotations

import hashlib
import threading
from typing import Any
from uuid import UUID

from app.career_tracking import (
    GMAIL_ID,
    MAX_GET,
    GmailReadClient,
    GmailResourceGoneError,
    GmailSyncError,
    normalize_message,
)
from app.creator_gmail_body import parse_gmail_body

MAX_FULL_READS = 3


class CreatorGmailReadClient(GmailReadClient):
    """Creator-only extension; Career's message() remains metadata-only."""

    def full_message(self, message_id: str) -> dict[str, Any]:
        if not GMAIL_ID.fullmatch(message_id):
            raise GmailSyncError("Creator Gmail message identifier is invalid")
        return self._get(f"messages/{message_id}", {
            "format": "full", "fields": "id,threadId,labelIds,snippet,internalDate,payload",
        })


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
    client = CreatorGmailReadClient(
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
    result = store.save_gmail(
        task, state, messages, cursor=cursor, pending=pending, mark_complete=False,
    )
    state = store.gmail_context(campaign_id, hashlib.sha256(mailbox.encode()).hexdigest(), label)
    body_reads, body_complete, body_unavailable = 0, 0, 0
    remaining_budget = MAX_GET - len(consumed)
    capture_enabled = campaign_id in getattr(settings, "creator_gmail_full_reply_campaign_ids", [])
    if capture_enabled and remaining_budget > 0:
        checkpoint()
        if client.mailbox() != mailbox or client.label_id(label) != label_id:
            raise GmailSyncError("Creator Gmail mailbox or label changed before full reply reads")
        body_limit = min(MAX_FULL_READS, remaining_budget)
        candidates = store.body_capture_candidates(task, state, body_limit)
        for candidate in candidates[:body_limit]:
            checkpoint()
            claim = store.claim_reply_body(task, state, candidate["id"])
            if claim is None:
                continue
            body_reads += 1
            message = None
            try:
                raw = client.full_message(claim["gmail_message_id"])
                message = normalize_message(
                    raw, expected_id=claim["gmail_message_id"], label_id=label_id, mailbox=mailbox,
                )
                keys = ("gmail_message_id", "gmail_thread_id", "sender", "subject", "received_at")
                if message is None or any(message[key] != claim[key] for key in keys):
                    capture = {"status": "unavailable", "text": "", "format": None,
                               "error_code": "CREATOR_REPLY_BODY_IDENTITY_CHANGED"}
                else:
                    capture = parse_gmail_body(raw.get("payload"))
            except GmailResourceGoneError:
                capture = {"status": "unavailable", "text": "", "format": None,
                           "error_code": "CREATOR_REPLY_BODY_UNAVAILABLE"}
            except GmailSyncError:
                checkpoint()
                store.save_reply_body(task, state, claim, {
                    "status": "unavailable", "text": "", "format": None,
                    "error_code": "CREATOR_REPLY_BODY_UNAVAILABLE",
                })
                raise
            checkpoint()
            saved = store.save_reply_body(task, state, claim, capture, message)
            body_complete += int(saved["body_status"] == "complete")
            body_unavailable += int(saved["body_status"] != "complete")
    checkpoint()
    store.finalize_reply_sync(task, state)
    reply_drafts = {"created": 0, "existing": 0, "skipped": 0}
    if (not pending and not cursor
            and campaign_id in getattr(settings, "creator_reply_draft_campaign_ids", [])):
        checkpoint()
        reply_drafts = store.queue_reply_draft_curation(task, campaign_id)
    return {
        "handler": "marketing.gmail_sync",
        **result,
        "fetched": len(consumed),
        "pending": len(pending),
        "more_pages": bool(cursor),
        "body_reads": body_reads,
        "body_complete": body_complete,
        "body_unavailable": body_unavailable,
        "reply_drafts_created": reply_drafts["created"],
        "reply_drafts_existing": reply_drafts["existing"],
        "reply_drafts_skipped": reply_drafts["skipped"],
        "mailbox_modified": False,
    }
