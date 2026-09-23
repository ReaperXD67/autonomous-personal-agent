"""Read-only Gmail metadata, conservative application matching, and visible evidence."""

from __future__ import annotations

import hashlib
import html
import json
import re
import threading
import unicodedata
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from email.utils import parseaddr
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
MAX_LIST = 50
MAX_GET = 20
ATS_SENDERS = {
    "greenhouse": ("greenhouse.io", "greenhouse-mail.io"),
    "lever": ("lever.co",),
    "ashby": ("ashbyhq.com",),
}
SHARED_HOSTS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com",
    "linkedin.com", "indeed.com", "arbeitnow.com", "remotive.com", "remoteok.com",
    "greenhouse.io", "lever.co", "ashbyhq.com", "google.com",
}


class GmailSyncError(RuntimeError):
    pass


class GmailResourceGoneError(GmailSyncError):
    pass


def bounded_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"<[^>]{0,500}>", " ", html.unescape(value[:12000]))
    text = "".join(char for char in text if char.isspace()
                   or not unicodedata.category(char).startswith("C"))
    return " ".join(text.split())[:limit]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        raise GmailSyncError("Gmail redirects are refused")


def _google_json(request: Request, *, limit: int = 1024 * 1024) -> dict[str, Any]:
    parsed = urlparse(request.full_url)
    if parsed.scheme != "https" or parsed.netloc not in {
        "gmail.googleapis.com", "oauth2.googleapis.com",
    }:
        raise GmailSyncError("Unreviewed Gmail endpoint")
    try:
        with build_opener(_NoRedirect()).open(request, timeout=15) as response:
            if response.geturl() != request.full_url:
                raise GmailSyncError("Gmail response changed endpoint")
            raw = response.read(limit + 1)
    except HTTPError as exc:
        if exc.code == 404:
            raise GmailResourceGoneError("Gmail resource is no longer available") from None
        raise GmailSyncError(f"Google request failed with HTTP {exc.code}") from None
    except (URLError, OSError, TimeoutError):
        raise GmailSyncError("Google request failed; check worker configuration") from None
    if len(raw) > limit:
        raise GmailSyncError("Google response exceeded the size limit")
    try:
        data = json.loads(raw)
    except (UnicodeError, ValueError):
        raise GmailSyncError("Google returned invalid metadata") from None
    if not isinstance(data, dict):
        raise GmailSyncError("Google returned unexpected metadata")
    return data


class GmailReadClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str) -> None:
        if not all(value.strip() for value in (client_id, client_secret, refresh_token)):
            raise GmailSyncError("Gmail read-only OAuth credentials are not configured")
        request = Request(
            "https://oauth2.googleapis.com/token",
            data=urlencode({"grant_type": "refresh_token", "client_id": client_id,
                            "client_secret": client_secret,
                            "refresh_token": refresh_token}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST",
        )
        token = _google_json(request, limit=65536)
        scopes = token.get("scope", "")
        if not isinstance(scopes, str) or set(scopes.split()) != {READONLY_SCOPE}:
            raise GmailSyncError("Gmail token must attest exactly the gmail.readonly scope")
        access_token = token.get("access_token")
        if not isinstance(access_token, str) or not access_token or len(access_token) > 8192:
            raise GmailSyncError("Google did not issue a usable access token")
        if any(char.isspace() for char in access_token):
            raise GmailSyncError("Google issued an invalid access token")
        self._access_token = access_token

    def _get(self, resource: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        if resource in {"messages/send", "messages/trash", "messages/modify", "messages/import",
                        "messages/insert", "messages/batchDelete", "messages/batchModify"} or (
            resource not in {"profile", "labels", "messages"} and not re.fullmatch(
                r"messages/[A-Za-z0-9_-]{1,128}", resource,
            )
        ):
            raise GmailSyncError("Only reviewed read-only Gmail resources are supported")
        url = f"https://gmail.googleapis.com/gmail/v1/users/me/{resource}"
        if parameters:
            url += "?" + urlencode(parameters, doseq=True)
        request = Request(url, headers={  # noqa: S310 - fixed HTTPS host and resource allowlist
            "Authorization": f"Bearer {self._access_token}", "Accept": "application/json",
        })
        return _google_json(request)

    def mailbox(self) -> str:
        address = self._get("profile", {"fields": "emailAddress"}).get("emailAddress")
        if not isinstance(address, str) or "@" not in address or len(address) > 320:
            raise GmailSyncError("Gmail mailbox identity was not returned")
        return address.casefold()

    def label_id(self, label_name: str) -> str:
        if not label_name or len(label_name) > 225:
            raise GmailSyncError("Choose one explicit custom Gmail career label")
        labels = self._get("labels", {"fields": "labels(id,name,type)"}).get("labels", [])
        if not isinstance(labels, list):
            raise GmailSyncError("Gmail labels could not be read")
        for label in labels[:10000]:
            if (isinstance(label, dict) and label.get("name") == label_name
                    and label.get("type") == "user"
                    and GMAIL_ID.fullmatch(str(label.get("id", "")))):
                return label["id"]
        raise GmailSyncError("The configured custom career label does not exist in Gmail")

    def list_messages(self, label_id: str, page_token: str | None) -> tuple[list[str], str | None]:
        parameters: dict[str, Any] = {
            "labelIds": label_id, "maxResults": MAX_LIST, "includeSpamTrash": "false",
            "fields": "messages(id),nextPageToken",
        }
        if page_token:
            if len(page_token) > 2048:
                raise GmailSyncError("Gmail page cursor is invalid")
            parameters["pageToken"] = page_token
        result = self._get("messages", parameters)
        items = result.get("messages", [])
        if not isinstance(items, list):
            raise GmailSyncError("Gmail message list is invalid")
        ids = list(dict.fromkeys(
            item["id"] for item in items[:MAX_LIST]
            if isinstance(item, dict) and isinstance(item.get("id"), str)
            and GMAIL_ID.fullmatch(item["id"])
        ))
        cursor = result.get("nextPageToken")
        if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 2048):
            raise GmailSyncError("Gmail page cursor is invalid")
        return ids, cursor or None

    def message(self, message_id: str) -> dict[str, Any]:
        if not GMAIL_ID.fullmatch(message_id):
            raise GmailSyncError("Gmail message identifier is invalid")
        return self._get(f"messages/{message_id}", {
            "format": "metadata", "metadataHeaders": ["From", "Subject"],
            "fields": "id,threadId,labelIds,snippet,internalDate,payload/headers",
        })


def normalize_message(
    raw: dict[str, Any], *, expected_id: str, label_id: str, mailbox: str,
) -> dict[str, Any] | None:
    """Use only bounded metadata; never retrieve body, attachment, or message-provided URL."""
    labels = raw.get("labelIds", [])
    if (not isinstance(labels, list) or label_id not in labels
            or set(labels) & {"SENT", "DRAFT", "SPAM", "TRASH"}):
        return None
    thread_id = raw.get("threadId")
    if raw.get("id") != expected_id or not isinstance(thread_id, str) \
            or not GMAIL_ID.fullmatch(thread_id):
        raise GmailSyncError("Gmail returned mismatched message identity")
    payload = raw.get("payload", {})
    headers = payload.get("headers", []) if isinstance(payload, dict) else []
    if not isinstance(headers, list):
        raise GmailSyncError("Gmail returned invalid headers")
    values: dict[str, str] = {}
    for header in headers[:100]:
        if isinstance(header, dict) and str(header.get("name", "")).casefold() in {
            "from", "subject",
        }:
            name = header["name"].casefold()
            if name in values:
                raise GmailSyncError("Gmail message has ambiguous headers")
            value = header.get("value")
            # From display names use angle brackets for addresses, not HTML markup.
            values[name] = value[:1500] if name == "from" and isinstance(value, str) \
                else bounded_text(value, 1500)
    sender = parseaddr(values.get("from", ""))[1].casefold()
    if not sender or "@" not in sender or len(sender) > 320 or sender == mailbox:
        return None
    timestamp = str(raw.get("internalDate", ""))
    if not re.fullmatch(r"\d{1,15}", timestamp):
        raise GmailSyncError("Gmail message has no reliable reception timestamp")
    try:
        received_at = datetime.fromtimestamp(int(timestamp) / 1000, UTC)
    except (ValueError, OverflowError, OSError):
        raise GmailSyncError("Gmail message has an invalid reception timestamp") from None
    if received_at > datetime.now(UTC) + timedelta(days=1):
        raise GmailSyncError("Gmail message has a future reception timestamp")
    return {
        "gmail_message_id": expected_id, "gmail_thread_id": thread_id, "sender": sender,
        "subject": bounded_text(values.get("subject"), 500),
        "snippet": bounded_text(raw.get("snippet"), 600), "received_at": received_at,
    }


def _contains_phrase(text: str, phrase: str) -> bool:
    words = re.findall(r"\w+", phrase.casefold())
    return bool(words and re.search(r"(?<!\w)" + r"\W+".join(map(re.escape, words))
                                    + r"(?!\w)", text.casefold()))


def _sender_matches(sender: str, application: dict[str, Any]) -> bool:
    domain = sender.rpartition("@")[2]
    if not domain:
        return False
    for host in ATS_SENDERS.get(application.get("source", ""), ()):
        if domain == host or domain.endswith("." + host):
            return True
    for key in ("source_url", "apply_url"):
        parsed = urlparse(application.get(key, ""))
        if parsed.scheme != "https" or parsed.username or parsed.password:
            continue
        host = (parsed.hostname or "").casefold()
        host = re.sub(r"^(?:www|jobs|careers)\.", "", host)
        if not host or "." not in host or any(
            host == shared or host.endswith("." + shared) for shared in SHARED_HOSTS
        ):
            continue
        if domain == host or domain.endswith("." + host):
            return True
    return False


def correlate_message(
    message: dict[str, Any], applications: list[dict[str, Any]], bindings: list[dict[str, Any]],
) -> tuple[UUID | None, str]:
    text = message["subject"] + " " + message["snippet"]
    domain = message["sender"].rpartition("@")[2]
    known = {str(item["id"]): item for item in applications}
    for binding in bindings:
        if binding["gmail_thread_id"] == message["gmail_thread_id"]:
            if (str(binding["opportunity_id"]) in known
                    and binding["sender_domain"] == domain):
                return binding["opportunity_id"], "Exact recorded Gmail thread and sender domain"
            return None, "Recorded thread has a different sender or application; review required"
    matches = []
    for application in applications:
        applied_at = application.get("applied_at")
        if applied_at is None or message["received_at"] < applied_at - timedelta(days=1):
            continue
        if not _sender_matches(message["sender"], application):
            continue
        reference = f"HERMES-{UUID(str(application['id'])).hex}"
        exact_reference = _contains_phrase(text, reference)
        company, title = application.get("company", ""), application.get("title", "")
        exact_role = len(company) >= 3 and len(title) >= 5 \
            and _contains_phrase(text, company) and _contains_phrase(text, title)
        if exact_reference or exact_role:
            matches.append((application["id"], "Exact application reference and sender domain"
                            if exact_reference else "Exact company, job title and sender domain"))
    if len(matches) == 1:
        return matches[0]
    return None, ("Multiple recorded applications match; review required" if matches else
                  "No unique application and sender match; review required")


def classify_message(message: dict[str, Any]) -> dict[str, Any]:
    text = bounded_text(message.get("subject", "") + ". " + message.get("snippet", ""), 1100)
    rules = {
        "rejected": r"\b(?:not (?:be )?(?:moving|proceeding) forward|"
                    r"application (?:was |has been )?"
                    r"(?:unsuccessful|rejected)|decided (?:not to proceed|to pursue other)|"
                    r"unable to offer you (?:the |a )?(?:role|position|job))\b",
        "offer": r"\b(?:offer of employment|(?:pleased|delighted) to offer you "
                 r"(?:the |a |this )?(?:role|position|job)|pleased to extend (?:an? )?offer|"
                 r"your (?:formal |job )?offer letter)\b",
        "interview": r"\b(?:interview invitation|invite you (?:to|for) (?:an? )?interview|"
                     r"schedule (?:an? |your )?interview|interview (?:is |has been )?scheduled|"
                     r"interview confirmation)\b",
        "acknowledgement": r"\b(?:received your application|application (?:has been |was )?"
                           r"received|thank you for applying|thanks for applying)\b",
        "withdrawn": r"\b(?:application (?:has been |was )?withdrawn|"
                     r"confirmed your withdrawal)\b",
    }
    matched = [(status, re.search(pattern, text, re.IGNORECASE))
               for status, pattern in rules.items()]
    matched = [(status, match) for status, match in matched if match]
    # Acknowledgements often accompany decisions; conflicting decisions need review.
    decisive = [(status, match) for status, match in matched if status != "acknowledgement"]
    selected = decisive or matched
    review = len(selected) != 1
    status, match = selected[0] if len(selected) == 1 else ("needs_review", None)
    if match and re.search(r"\b(?:not|never|no|cancel\w*)\b", text[max(0, match.start()-35):
                                                                         match.start()], re.I):
        status, review = "needs_review", True
    if not selected and re.search(r"\b(?:availability|discuss your application|"
                                  r"tell us more|recruiter|hiring team)\b", text, re.I):
        status, review = "recruiter_reply", False
    meeting_at = None
    if status == "interview":
        date_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})\b"
        dates = re.findall(r"\b" + date_pattern, text)
        confirmed = re.search(
            r"\b(?:interview (?:is |has been )?scheduled (?:for |on |at )?|"
            r"interview (?:time|date|confirmation)\s*[:\-]?\s*)(" + date_pattern + ")",
            text, re.I,
        )
        uncertain = re.search(r"\b(?:cancel\w*|reschedul\w*|tentative|not confirmed)\b", text, re.I)
        if len(dates) == 1 and confirmed and not uncertain:
            with suppress(ValueError):
                meeting_at = datetime.fromisoformat(dates[0].replace("Z", "+00:00"))
        review = meeting_at is None
    if match:
        evidence = text[max(0, match.start() - 80):min(len(text), match.end() + 180)]
    else:
        evidence = text[:300] or "No useful subject or snippet was returned"
    return {
        "suggested_status": status, "confidence": "low" if review else "medium",
        "evidence": evidence, "meeting_at": meeting_at, "needs_review": review,
    }


def execute_gmail_sync(task: dict[str, Any], store: Any, settings: Any,
                      interrupt: threading.Event | None = None) -> dict[str, Any]:
    """Run only after a career.gmail_sync task has passed policy and obtained its lease."""
    if not settings.gmail_enabled:
        raise GmailSyncError("Gmail integration is disabled")

    def check_interrupted() -> None:
        if interrupt is not None and interrupt.is_set():
            raise GmailSyncError("Gmail sync interrupted before persistence")

    profile_id = UUID(str(task["payload"]["profile_id"]))
    profile = store.get_profile(profile_id)
    check_interrupted()
    client = GmailReadClient(settings.gmail_client_id, settings.gmail_client_secret,
                             settings.gmail_refresh_token)
    mailbox = client.mailbox()
    expected_mailbox = (profile.get("application_identity") or {}).get("email", "").casefold()
    if mailbox != expected_mailbox:
        raise GmailSyncError("Gmail mailbox must match the career profile application email")
    label_name = settings.gmail_career_label
    label_id = client.label_id(label_name)
    mailbox_key = hashlib.sha256(mailbox.encode()).hexdigest()
    context = store.gmail_sync_context(profile_id, mailbox_key, label_name)
    cursor, pending = context["page_token"], list(context["pending_message_ids"])
    if not pending:
        check_interrupted()
        pending, cursor = client.list_messages(label_id, cursor)
    known = store.known_gmail_messages(profile_id, pending)
    remaining = [message_id for message_id in pending if message_id not in known]
    processed, fetched = [], 0
    consumed = []
    for message_id in remaining[:MAX_GET]:
        check_interrupted()
        fetched += 1
        try:
            raw = client.message(message_id)
        except GmailResourceGoneError:
            consumed.append(message_id)
            continue
        message = normalize_message(raw, expected_id=message_id, label_id=label_id, mailbox=mailbox)
        consumed.append(message_id)
        if message is None:
            continue
        opportunity_id, reason = correlate_message(message, context["applications"],
                                                    context["bindings"])
        classification = classify_message(message)
        if opportunity_id is None:
            classification["needs_review"] = True
        processed.append({**message, **classification, "opportunity_id": opportunity_id,
                          "match_reason": reason})
    pending = [message_id for message_id in remaining if message_id not in consumed]
    check_interrupted()
    result = store.save_gmail_sync(
        profile_id, context, processed, page_token=cursor, pending_message_ids=pending,
        task_id=task["id"], lease_id=task["lease_id"],
    )
    return {"handler": "career.gmail_sync", "profile_id": str(profile_id), "fetched": fetched,
            **result, "pending": len(pending), "more_pages": bool(cursor),
            "mailbox_modified": False}
