from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.application_browser import canonical_hash
from app.career import score_opportunity

PROFILE_SCOPE_FIELDS = (
    "candidate_name",
    "resume_text",
    "application_identity",
    "desired_titles",
    "skills",
    "required_keywords",
    "excluded_keywords",
    "locations",
    "remote_only",
    "employment_types",
    "source_config",
    "max_age_hours",
    "min_score",
)
OPPORTUNITY_SCOPE_FIELDS = (
    "company",
    "title",
    "description",
    "location",
    "remote",
    "employment_type",
    "source",
    "source_url",
    "apply_url",
    "published_at",
    "published_at_basis",
)


def profile_hash(profile: dict[str, Any]) -> str:
    return canonical_hash({key: profile.get(key) for key in PROFILE_SCOPE_FIELDS})


def opportunity_hash(opportunity: dict[str, Any]) -> str:
    values = {key: opportunity.get(key) for key in OPPORTUNITY_SCOPE_FIELDS}
    if isinstance(values.get("published_at"), datetime):
        values["published_at"] = values["published_at"].isoformat()
    return canonical_hash(values)


def target_key(url: str) -> str:
    parsed = urlsplit(url)
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"source", "ref"}
    )
    authority = parsed.netloc.lower()
    if parsed.scheme.lower() == "https" and parsed.port == 443:
        authority = str(parsed.hostname).lower()
    canonical = urlunsplit(
        (parsed.scheme.lower(), authority, parsed.path.rstrip("/"), urlencode(query), "")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def allowed_url(url: str, hosts: list[str]) -> bool:
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in hosts
            and parsed.port in {None, 443}
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
        )
    except ValueError:
        return False


def eligibility_reason(
    run: dict[str, Any],
    profile: dict[str, Any],
    opportunity: dict[str, Any],
    now: datetime | None = None,
) -> str | None:
    now = now or datetime.now(UTC)
    if run["state"] != "running" or run["expires_at"] <= now:
        return "Run is paused or expired"
    if profile.get("active") is False:
        return "Career mission is paused"
    if profile_hash(profile) != run["profile_hash"]:
        return "Profile changed; press Play again to authorize the new preferences"
    if opportunity.get("status") in {"dismissed", "applied"}:
        return "Opportunity is dismissed or already applied"
    if opportunity.get("published_at_basis") != "published":
        return "A verified posting date is required"
    posted = opportunity.get("published_at")
    if (
        not isinstance(posted, datetime)
        or posted > now
        or posted < now - timedelta(hours=run["max_age_hours"])
    ):
        return "Opportunity falls outside the authorized posting window"
    scored = score_opportunity(opportunity, profile, now=now)
    if scored is None or scored["score"] < run["min_score"]:
        return "Opportunity no longer meets the authorized fit threshold"
    return None


def hiring_email(description: str) -> str | None:
    """Only explicitly advertised hiring contacts; never infer address patterns."""
    matches: set[str] = set()
    for match in re.finditer(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,24}", description, re.I):
        context = description[max(0, match.start() - 120) : match.end() + 120]
        if re.search(
            r"do\s+not|don't|never|cannot|can't|no\s+(?:emails?|applications?)|closed|"
            r"not\s+(?:accepting|accepted|for\s+applications?)|"
            r"general\s+(?:questions?|enquiries|inquiries)|support|privacy",
            context,
            re.I,
        ):
            continue
        if re.search(
            r"apply|application|send.{0,30}(?:resume|cv)|careers|hiring|recruit", context, re.I
        ):
            address = match.group().lower()
            if not any(token in address for token in ("noreply", "no-reply", "privacy", "support")):
                matches.add(address)
    return next(iter(matches)) if len(matches) == 1 else None


def lock_profile(connection: Any, profile_id: Any) -> None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"career-autopilot:{profile_id}",)
    )


def guard_autopilot_action(connection: Any, action: dict[str, Any], now: datetime) -> None:
    # Imported here to keep the core decision functions independent of persistence.
    from app.action_store import SideEffectGuardError

    ledger = connection.execute(
        "SELECT * FROM career_autopilot_actions WHERE action_id = %s", (action["id"],)
    ).fetchone()
    if ledger is None:
        return
    lock_profile(connection, ledger["profile_id"])
    run = connection.execute(
        "SELECT * FROM career_autopilot_runs WHERE id = %s FOR UPDATE", (ledger["run_id"],)
    ).fetchone()
    profile = connection.execute(
        "SELECT * FROM career_profiles WHERE id = %s FOR SHARE", (ledger["profile_id"],)
    ).fetchone()
    opportunity = connection.execute(
        "SELECT * FROM job_opportunities WHERE id = %s FOR SHARE", (ledger["opportunity_id"],)
    ).fetchone()
    # Re-read time after locks so expiry cannot pass during a wait.
    now = connection.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
    reason = eligibility_reason(run, profile, opportunity, now)
    if reason or run["mode"] != "apply":
        raise SideEffectGuardError(reason or "Run does not authorize submission")
    if opportunity_hash(opportunity) != ledger["opportunity_hash"]:
        raise SideEffectGuardError("Job details changed after scoped authorization")
    if action["action_type"] == "career.application_submit":
        if not allowed_url(action["public_context"].get("apply_url", ""), run["allowed_hosts"]):
            raise SideEffectGuardError("Application destination is outside the authorized scope")
    elif not run["include_cold_email"] or hiring_email(opportunity["description"]) != action[
        "public_context"
    ].get("recipient"):
        raise SideEffectGuardError("Published hiring email is outside the authorized scope")
    else:
        draft = connection.execute(
            "SELECT content FROM job_application_drafts WHERE id = %s FOR SHARE",
            (action["private_context"].get("career_draft_id"),),
        ).fetchone()
        if draft is None or canonical_hash(draft["content"]) != action["private_context"].get(
            "career_draft_sha256"
        ):
            raise SideEffectGuardError("Career email draft changed after authorization")
