"""Pure scope checks and final fences for individually approved career outreach."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.application_browser import canonical_hash
from app.career_application_quality import application_quality_blocker
from app.career_autopilot import eligibility_reason, opportunity_hash, target_key


def contact_snapshot(contact: dict[str, Any]) -> dict[str, Any]:
    snapshot = {key: contact.get(key) for key in (
        "email", "kind", "source_url", "evidence_quote", "basis_note", "reviewed_by",
        "profile_hash", "opportunity_hash", "reviewed_at", "expires_at",
    )}
    return {key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in snapshot.items()}


def contact_scope_error(contact: dict[str, Any], profile: dict[str, Any],
                        opportunity: dict[str, Any], now: datetime) -> str | None:
    if contact.get("revoked_at") is not None:
        return "Career contact review was revoked"
    if opportunity_hash(opportunity) != contact["opportunity_hash"]:
        return "Job details changed; review the public contact again"
    # Use the same current deterministic fit and source-publication checks as Apply.
    # A historical stored score never grants outreach authority.
    return eligibility_reason({
        "state": "running", "expires_at": contact["expires_at"],
        "profile_hash": contact["profile_hash"],
        "max_age_hours": min(72, profile["max_age_hours"]),
        "min_score": max(75, profile["min_score"]),
    }, profile, opportunity, now)


def sender_identity_error(profile: dict[str, Any], sender: str) -> str | None:
    chosen = str((profile.get("application_identity") or {}).get("email") or "").strip()
    if not sender or not chosen or sender.strip().casefold() != chosen.casefold():
        return "Connect an SMTP sender matching this career profile's application email"
    return None


def email_content_error(body: str) -> str | None:
    if re.search(r"\b(?:attach(?:ed|ing|ments?)|enclos(?:ed|ure))\b", body, re.I):
        return "This email has no attachments; remove the attachment claim from the draft"
    return None


def guard_career_contact_action(
    connection: Any, action: dict[str, Any], *, acquire_locks: bool = True,
) -> None:
    from app.action_store import SideEffectGuardError

    packet = action["private_context"].get("career_contact")
    if packet is None:
        return
    if not isinstance(packet, dict) or action["action_type"] != "communications.email_send":
        raise SideEffectGuardError("Invalid career contact action scope")
    ledger = connection.execute(
        "SELECT * FROM career_contact_actions WHERE action_id = %s", (action["id"],),
    ).fetchone()
    if ledger is None or str(ledger["contact_id"]) != packet.get("contact_id"):
        raise SideEffectGuardError("Career contact action has no matching durable ledger")
    contact = connection.execute(
        ("SELECT * FROM career_contacts WHERE id = %s FOR SHARE" if acquire_locks else
         "SELECT * FROM career_contacts WHERE id = %s"), (ledger["contact_id"],),
    ).fetchone()
    opportunity = connection.execute(
        ("SELECT * FROM job_opportunities WHERE id = %s FOR SHARE" if acquire_locks else
         "SELECT * FROM job_opportunities WHERE id = %s"), (ledger["opportunity_id"],),
    ).fetchone()
    profile = connection.execute(
        ("SELECT * FROM career_profiles WHERE id = %s FOR SHARE" if acquire_locks else
         "SELECT * FROM career_profiles WHERE id = %s"), (ledger["profile_id"],),
    ).fetchone()
    if contact is None or profile is None or opportunity is None:
        raise SideEffectGuardError("Career contact source records are missing")
    if (packet.get("snapshot") != contact_snapshot(contact)
            or action["private_context"].get("recipient") != contact["email"]
            or ledger["recipient"] != contact["email"]
            or str(action.get("opportunity_id")) != str(contact["opportunity_id"])
            or contact["profile_id"] != profile["id"]
            or contact["opportunity_id"] != opportunity["id"]
            or opportunity["profile_id"] != profile["id"]
            or ledger.get("target_key") != target_key(opportunity["apply_url"])):
        raise SideEffectGuardError("Reviewed career contact packet changed after approval")
    error = sender_identity_error(profile, action["private_context"].get("sender", ""))
    if error:
        raise SideEffectGuardError(error)
    error = email_content_error(str(action["private_context"].get("body") or ""))
    if error:
        raise SideEffectGuardError(error)
    draft = connection.execute(
        ("SELECT content FROM job_application_drafts WHERE id = %s "
         "AND opportunity_id = %s FOR SHARE" if acquire_locks else
         "SELECT content FROM job_application_drafts WHERE id = %s AND opportunity_id = %s"),
        (packet.get("draft_id"), opportunity["id"]),
    ).fetchone()
    if draft is None or canonical_hash(draft["content"]) != packet.get("draft_sha256"):
        raise SideEffectGuardError("Career outreach draft changed after approval")
    error = application_quality_blocker(
        {**opportunity, "resume_text": profile["resume_text"]}, draft["content"],
    )
    if error:
        raise SideEffectGuardError(error)
    # Refresh time after every potentially waiting row lock.
    now = connection.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
    error = contact_scope_error(contact, profile, opportunity, now)
    if error:
        raise SideEffectGuardError(error)
