"""Explainable job-listing checks; signals are evidence, never a fraud verdict."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.career_sources import resolve_career_source

ATS_HOSTS = {
    "ashby": {"jobs.ashbyhq.com"},
    "greenhouse": {"boards.greenhouse.io", "job-boards.greenhouse.io"},
    "lever": {"jobs.lever.co", "jobs.eu.lever.co"},
}
FREE_MAIL_HOSTS = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com"}

# These deliberately require an action directed at the applicant. Words such as
# "payments", "banking" or "security" in an ordinary engineering role are not flags.
PAYMENT_REQUEST = re.compile(
    r"\b(?:pay|send|transfer|deposit|purchase|buy)\b.{0,65}"
    r"\b(?:application fee|registration fee|processing fee|training fee|security deposit|"
    r"starter kit|equipment from|gift cards?|cryptocurrency|crypto deposit|"
    r"up[- ]?front (?:fee|payment))\b|"
    r"\b(?:application|registration|processing|training) fee\b.{0,35}"
    r"\b(?:required|mandatory|payable|must be paid)\b|"
    r"\bpay\b.{0,25}\bfee\b.{0,25}\b(?:to apply|before applying|to start work)\b|"
    r"\b(?:applicants?|candidates?|you)\b.{0,20}"
    r"\b(?:must|need to|have to|are required to) pay\b.{0,45}"
    r"\b(?:to apply|to start work|before starting|before employment)\b",
    re.I,
)
SECRET_REQUEST = re.compile(
    r"\b(?:send|share|provide|submit|upload|disclose|enter)\b.{0,55}"
    r"\b(?:your\s+)?(?:password|one[- ]time (?:password|code)|otp|"
    r"bank (?:login|password|credentials)|credit card (?:number|details)|"
    r"seed phrase|private key)\b",
    re.I,
)
SENSITIVE_REQUEST = re.compile(
    r"\b(?:send|share|provide|submit|upload)\b.{0,45}"
    r"\b(?:bank account (?:number|details)|passport (?:copy|scan)|"
    r"social security number|ssn|aadhaar (?:number|card|copy))\b",
    re.I,
)
NEGATED_PREFIX = re.compile(
    r"\b(?:never|not|no|don't|do not|won't|will not|without)\b"
    r"(?:\s+(?:ever|have|need|require|required|ask|asked|expect|expected|request|requested|"
    r"you|candidates?|applicants?|to|be|any|an?|for|us)){0,10}\s*$",
    re.I,
)
OTHER_SUBJECT = re.compile(
    r"\b(?:users?|customers?|clients?)\s+(?:(?:can|may|must|will|should|to)\s+)?$", re.I,
)


def _requested(pattern: re.Pattern[str], text: str) -> bool:
    # Evaluate clauses separately so an anti-scam disclaimer elsewhere in the
    # posting cannot suppress an actual request. The checks remain conservative.
    text = text[:100000].replace("\u2019", "'")
    for clause in re.split(r"[.!?;,\n]|\b(?:but|however|nevertheless|yet)\b", text, flags=re.I):
        for match in pattern.finditer(clause):
            before = clause[max(0, match.start() - 65):match.start()]
            after = clause[match.end():match.end() + 40]
            negated = (NEGATED_PREFIX.search(before) or re.search(
                r"\b(?:not required|not needed|never required|not payable)\b",
                match.group(), re.I,
            ) or re.match(
                r"\s*(?:(?:is|are|will be|has been)\s+)?"
                r"(?:not|never)\s+(?:required|needed|payable)\b", after, re.I,
            ))
            if not negated and not OTHER_SUBJECT.search(before):
                return True
    return False


def _url_parts(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str) or not value or len(value) > 2048:
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.port not in {None, 443} or parsed.username is not None
                or parsed.password is not None or parsed.fragment
                or "\\" in value or any(char.isspace() for char in value)):
            return None
        return parsed.hostname.casefold(), parsed.path
    except ValueError:
        return None


def assess_opportunity(
    opportunity: dict[str, Any], *, now: datetime | None = None,
) -> dict[str, Any]:
    """Recompute from current public facts; ignore any caller-supplied quality."""
    now = now or datetime.now(UTC)
    signals: list[dict[str, str]] = []

    def add(code: str, severity: str, message: str) -> None:
        signals.append({"code": code, "severity": severity, "message": message})

    description = str(opportunity.get("description") or "")[:100000]
    if _requested(PAYMENT_REQUEST, description):
        add("applicant_payment", "block", "Posting requests an applicant fee or purchase")
    if _requested(SECRET_REQUEST, description):
        add("credential_request", "block", "Posting requests credentials or financial secrets")
    if _requested(SENSITIVE_REQUEST, description):
        add("sensitive_identity_request", "block",
            "Posting requests sensitive identity or bank data")

    source = str(opportunity.get("source") or "")
    source_parts = _url_parts(opportunity.get("source_url"))
    apply_parts = _url_parts(opportunity.get("apply_url"))
    if source_parts is None or apply_parts is None:
        add("unsafe_listing_url", "block",
            "Listing or application URL is not a plain HTTPS destination")
    elif source in ATS_HOSTS:
        expected_hosts = ATS_HOSTS[source]
        if source_parts[0] in expected_hosts:
            if apply_parts[0] not in expected_hosts:
                add("ats_destination_mismatch", "block",
                    "Application leaves the listing's ATS provider")
            else:
                try:
                    listing = resolve_career_source(opportunity["source_url"])
                    application = resolve_career_source(opportunity["apply_url"])
                except ValueError:
                    add("unsupported_ats_path", "block",
                        "Listing or application ATS path cannot be resolved safely")
                else:
                    if (listing.source_config_key, listing.board.casefold()) != (
                        application.source_config_key, application.board.casefold()
                    ):
                        add("ats_board_mismatch", "block",
                            "Listing and application name different employer boards or regions")
                    elif (listing.posting_url and application.posting_url
                          and urlsplit(listing.posting_url).path.rsplit("/", 1)[-1]
                          != urlsplit(application.posting_url).path.rsplit("/", 1)[-1]):
                        add("ats_posting_mismatch", "block",
                            "Listing and application refer to different job postings")
        elif source == "greenhouse":
            add("custom_employer_url", "info",
                "Employer-hosted URL needs independent employer verification")
        else:
            add("ats_source_mismatch", "block",
                "Listing URL does not match its reported ATS provider")

    addresses = re.findall(r"[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,24})", description, re.I)
    if any(domain.casefold() in FREE_MAIL_HOSTS for domain in addresses):
        add("personal_email_contact", "info",
            "Posting includes a consumer-mail address; verify its ownership")
    if len(description.split()) < 15:
        add("limited_description", "info", "Description supplies little evidence about the role")

    basis = opportunity.get("published_at_basis", "unknown")
    basis = basis if basis in {"published", "updated"} else "unknown"
    posted = opportunity.get("published_at")
    age_hours = None
    if isinstance(posted, datetime) and posted.tzinfo is not None:
        age_hours = round((now - posted).total_seconds() / 3600, 2)
    if age_hours is None:
        publication_status = "unknown"
    elif posted > now:
        publication_status = "future"
        add("future_timestamp", "info",
            "Source timestamp is in the future and does not prove freshness")
    else:
        publication_status = "published" if basis == "published" else "publication_unconfirmed"
    if basis != "published":
        add("publication_unconfirmed", "info",
            "An update or observation date does not establish a new posting")

    return {
        "version": 1,
        "disposition": "review_required" if any(s["severity"] == "block" for s in signals)
        else "no_strong_flags",
        "authenticity": "unverified",
        "signals": signals,
        "publication": {"basis": basis, "status": publication_status, "age_hours": age_hours},
        "model_calls": 0,
        "limitations": (
            "Heuristic checks cannot prove an employer or vacancy is genuine or still open."
        ),
    }


def quality_blocker(opportunity: dict[str, Any], *, now: datetime | None = None) -> str | None:
    assessment = assess_opportunity(opportunity, now=now)
    for signal in assessment["signals"]:
        if signal["severity"] == "block":
            return f"Job safety review required: {signal['message']}"
    return None
