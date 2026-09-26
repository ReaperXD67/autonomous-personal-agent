"""Complete creator research exports, with evidence and no inferred authority."""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from app.creator_contact_history import trim_contact_history
from app.creator_intelligence import CHANNEL_ID, public_youtube_identity

FIELDS = (
    "creator_id", "channel_id", "display_name", "profile_url", "audience_size",
    "fit_score", "confidence", "current_target_eligible", "selection_reason",
    "country_code", "country_source_url", "country_evidence", "language_code",
    "language_source", "language_source_url", "topics", "recorded_contact_email",
    "recorded_contact_source_url", "recorded_contact_basis", "public_contact_candidates",
    "contact_evidence_json", "historical_public_contacts", "historical_contact_evidence_json",
    "contact_status", "outreach_authorized", "suppressed",
    "prospect_status", "sample_video_title", "sample_video_url", "sample_video_published_at",
    "collaboration_ideas_json", "personalized_hook", "research_gaps", "researched_at",
    "first_seen_at", "last_seen_at",
)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value).lower()
    text = str(value)
    # Excel/LibreOffice may ignore leading whitespace before a formula marker.
    if re.match(r"^[\s\x00-\x1f\x7f\ufeff]*[=+\-@]|^[\x00-\x1f\x7f]", text):
        return "'" + text
    return text


def public_contacts(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [candidate for candidate in (row.get("intelligence") or {}).get(
        "contact_candidates", [],
    ) if isinstance(candidate, dict) and candidate.get("email")]


def channel_identity(row: dict[str, Any]) -> str:
    value = (row.get("intelligence") or {}).get("source_channel_id")
    if isinstance(value, str) and CHANNEL_ID.fullmatch(value):
        return value
    try:
        return public_youtube_identity(row["profile_url"]).get("id", "")
    except (ValueError, KeyError):
        return ""


def creator_csv(
    rows: Iterable[dict[str, Any]], *, include_excluded: bool = False, now: datetime | None = None,
) -> Iterator[str]:
    """One row per saved YouTube identity, including creators with no public email."""
    buffer = io.StringIO(newline="")
    reference = now or datetime.now(UTC)
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    yield "\ufeff" + buffer.getvalue()
    for row in rows:
        intelligence = trim_contact_history(row.get("intelligence") or {}, now=reference)
        geo = intelligence.get("geography") or {}
        eligible = geo.get("eligible") is True
        if not include_excluded and not eligible:
            continue
        candidates = public_contacts(row)
        history = intelligence.get("contact_history") or []
        recorded = row.get("contact_email")
        suppressed = bool(row.get("suppressed_at") or row.get("status") in {
            "suppressed", "bounced",
        })
        authorized = bool(recorded and row.get("contact_authorized_at") and not suppressed)
        contact_status = (
            "suppressed" if suppressed else "authorized_recorded_contact" if authorized else
            "public_contact_unreviewed" if recorded or candidates else
            "historical_contact_requires_recheck" if history else "no_public_contact_found"
        )
        values = (
            row["id"], channel_identity(row), row["display_name"], row["profile_url"],
            row.get("audience_size"), row.get("relevance_score"), intelligence.get("confidence"),
            eligible, geo.get("selection_reason"), geo.get("country_code"),
            geo.get("country_source_url"), (
                f"YouTube channel snippet.country declares {geo['country_code']}"
                if geo.get("country_code") else "Country not declared in inspected metadata"
            ), geo.get("language_code"),
            geo.get("language_source"), geo.get("language_source_url"),
            " | ".join(intelligence.get("topics") or []), recorded,
            row.get("contact_source_url"), row.get("contact_basis_note"),
            " | ".join(dict.fromkeys(str(item["email"]) for item in candidates)),
            json.dumps(candidates, ensure_ascii=False),
            " | ".join(dict.fromkeys(str(item["email"]) for item in history)),
            json.dumps(history, ensure_ascii=False), contact_status, authorized, suppressed,
            row.get("status"), row.get("latest_content_title"), row.get("latest_content_url"),
            row.get("latest_content_published_at"),
            json.dumps(intelligence.get("collaboration_ideas") or [], ensure_ascii=False),
            intelligence.get("personalized_hook"), " | ".join(intelligence.get("gaps") or []),
            intelligence.get("researched_at"), row.get("first_seen_at"), row.get("last_seen_at"),
        )
        buffer.seek(0)
        buffer.truncate(0)
        writer.writerow([_cell(value) for value in values])
        yield buffer.getvalue()


def creator_coverage(
    rows: Iterable[dict[str, Any]], *, now: datetime | None = None,
) -> dict[str, int]:
    reference = now or datetime.now(UTC)
    cutoff = reference - timedelta(days=30)
    counts = dict.fromkeys((
        "total", "eligible", "excluded", "country_unknown", "with_public_contact",
        "without_public_contact", "authorized", "suppressed", "needs_refresh",
        "with_historical_contact", "historical_contact_only",
    ), 0)
    for row in rows:
        counts["total"] += 1
        intelligence = trim_contact_history(row.get("intelligence") or {}, now=reference)
        geo = intelligence.get("geography") or {}
        counts["country_unknown"] += int(not geo.get("country_code"))
        if geo.get("eligible") is not True:
            counts["excluded"] += 1
            continue
        counts["eligible"] += 1
        contact = bool(row.get("contact_email") or public_contacts(row))
        counts["with_public_contact" if contact else "without_public_contact"] += 1
        history = bool(intelligence.get("contact_history"))
        counts["with_historical_contact"] += int(history)
        counts["historical_contact_only"] += int(history and not contact)
        suppressed = bool(row.get("suppressed_at") or row.get("status") in {
            "suppressed", "bounced",
        })
        counts["suppressed"] += int(suppressed)
        counts["authorized"] += int(bool(row.get("contact_email") and row.get(
            "contact_authorized_at",
        ) and not suppressed))
        try:
            observed = datetime.fromisoformat(str(intelligence.get("researched_at")))
            stale = observed.tzinfo is None or observed < cutoff
        except ValueError:
            stale = True
        counts["needs_refresh"] += int(stale or intelligence.get("enrichment_status") != "complete")
    return counts
