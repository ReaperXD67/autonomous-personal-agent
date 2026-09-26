"""Bounded public-source history; past observations never become current authority."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.creator_intelligence import (
    BUSINESS_CONTEXT,
    CHANNEL_ID,
    EMAIL,
    NEGATIVE_CONTEXT,
    _fold,
    plain_text,
    public_video_id,
    public_youtube_identity,
)

MAX_CONTACT_HISTORY = 20
CONTACT_HISTORY_DAYS = 30


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else None


def _with_history(
    intelligence: dict[str, Any], history: list[dict[str, str]],
) -> dict[str, Any]:
    expires_at = None
    if history:
        earliest = min(datetime.fromisoformat(item["last_seen_at"]) for item in history)
        expires_at = (earliest + timedelta(days=CONTACT_HISTORY_DAYS)).isoformat()
    return {**intelligence, "contact_history": history, "contact_history_expires_at": expires_at}


def _observation(
    item: Any, *, now: datetime, historical: bool,
) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    last_seen = _timestamp(item.get("last_seen_at") if historical else item.get("observed_at"))
    first_seen = _timestamp(item.get("observed_at") if historical else
                            item.get("first_observed_at", item.get("observed_at")))
    if (last_seen is None or first_seen is None or first_seen > last_seen or last_seen > now
            or last_seen <= now - timedelta(days=CONTACT_HISTORY_DAYS)):
        return None
    email, source = item.get("email"), item.get("source_url")
    if not isinstance(email, str) or not isinstance(source, str):
        return None
    if EMAIL.fullmatch(email) is None or len(email) > 254 or ".." in email:
        return None
    try:
        if public_video_id(source) is None:
            public_youtube_identity(source)
    except ValueError:
        return None
    evidence = plain_text(item.get("evidence"), 320)
    folded = _fold(evidence)
    if not BUSINESS_CONTEXT.search(folded) or NEGATIVE_CONTEXT.search(folded):
        return None
    # This is an already-extracted, flattened excerpt, not another raw description.
    # The original label may be outside the raw scanner's relative-email window.
    # A long address can also be clipped at the excerpt's fixed 320-character edge.
    exact = any(match.group().casefold() == email.casefold() for match in EMAIL.finditer(evidence))
    clipped = len(evidence) == 320 and any(
        len(evidence) - start >= 8 and email.casefold().startswith(evidence[start:].casefold())
        for start in range(len(evidence))
    )
    if not exact and not clipped:
        return None
    return {
        "email": email, "source_url": source, "evidence": evidence,
        "observed_at": first_seen.isoformat(), "last_seen_at": last_seen.isoformat(),
        "status": "historical_unreviewed",
    }


def merge_contact_history(
    previous: dict[str, Any], current: dict[str, Any], *, now: datetime | None = None,
) -> dict[str, Any]:
    """Retain absent source pairs for <=30 days, keyed by email and exact source URL.

    The caller must hold the prospect row lock and enforce suppression/identity
    guards. Neither input is mutated and no reviewed contact fields are read.
    """
    reference = now or datetime.now(UTC)
    channel = current.get("source_channel_id")
    same_channel = (
        isinstance(channel, str) and CHANNEL_ID.fullmatch(channel) is not None
        and previous.get("source_channel_id") == channel
    )
    old = previous if same_channel else {}
    observations: dict[tuple[str, str], dict[str, str]] = {}
    for field, limit, historical in (
        ("contact_history", MAX_CONTACT_HISTORY, True), ("contact_candidates", 5, False),
    ):
        items = old.get(field)
        if not isinstance(items, list):
            continue
        for item in items[:limit]:
            observation = _observation(item, now=reference, historical=historical)
            if observation is None:
                continue
            key = (observation["email"].casefold(), observation["source_url"])
            existing = observations.get(key)
            if existing is not None:
                earliest = min(existing["observed_at"], observation["observed_at"])
                if existing["last_seen_at"] > observation["last_seen_at"]:
                    observation = dict(existing)
                observation["observed_at"] = earliest
            observations[key] = observation

    candidates = []
    current_items = current.get("contact_candidates")
    current_items = current_items[:5] if isinstance(current_items, list) else []
    seen_current = set()
    for candidate in current_items:
        observation = _observation(candidate, now=reference, historical=False)
        if observation is None:
            continue
        key = (observation["email"].casefold(), observation["source_url"])
        if key in seen_current:
            continue
        seen_current.add(key)
        prior = observations.pop(key, None)
        first_seen = observation["observed_at"]
        if prior is not None:
            first_seen = min(first_seen, prior["observed_at"])
        candidates.append({
            "email": observation["email"], "source_url": observation["source_url"],
            "evidence": observation["evidence"], "observed_at": observation["last_seen_at"],
            "first_observed_at": first_seen, "status": "unreviewed",
        })
    history = sorted(
        observations.values(),
        key=lambda item: (item["last_seen_at"], item["source_url"], item["email"].casefold()),
        reverse=True,
    )[:MAX_CONTACT_HISTORY]
    return _with_history({**current, "contact_candidates": candidates}, history)


def trim_contact_history(
    intelligence: dict[str, Any], *, now: datetime | None = None,
) -> dict[str, Any]:
    """Filter only the history field; never silently age reviewed/manual contacts."""
    if "contact_history" not in intelligence:
        return dict(intelligence)
    reference = now or datetime.now(UTC)
    items = intelligence.get("contact_history")
    items = items[:MAX_CONTACT_HISTORY] if isinstance(items, list) else []
    history = []
    seen = set()
    for item in items:
        observation = _observation(item, now=reference, historical=True)
        if observation is None:
            continue
        key = (observation["email"].casefold(), observation["source_url"])
        if key not in seen:
            history.append(observation)
            seen.add(key)
    return _with_history(intelligence, history)
