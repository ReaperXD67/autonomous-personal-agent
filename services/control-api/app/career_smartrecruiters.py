"""Bounded public SmartRecruiters discovery; application execution is not enabled.

Original adapter based on the provider's public Posting API contract:
https://developers.smartrecruiters.com/docs/endpoints
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.career import USER_AGENT, _normalize_employment_type, _parse_datetime, _plain_text
from app.career_sources import BOARD_SLUG

LIST_LIMIT = 50
DETAIL_LIMIT = 10
MAX_BYTES = 2 * 1024 * 1024
POSTING_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}\Z")
API_ROOT = "https://api.smartrecruiters.com/v1/companies/"


def smartrecruiters_country_hint(locations: list[Any]) -> str | None:
    """Narrow only an explicit India-only search, not mixed/unknown preferences."""
    selected = {value.casefold().strip() for value in locations if isinstance(value, str)}
    india_labels = {
        "india", "bengaluru", "bangalore", "mumbai", "pune", "hyderabad", "chennai",
        "delhi", "new delhi", "gurugram", "gurgaon", "noida", "remote",
    }
    return "in" if "india" in selected and selected <= india_labels else None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        raise ValueError("SmartRecruiters redirects are refused")


def _read_public(
    board: str, posting_id: str | None = None, *, country: str | None = None,
) -> Any:
    """Construct only provider-fixed URLs; never follow a returned ref/apply URL."""
    if not BOARD_SLUG.fullmatch(board) or (
        posting_id is not None and not POSTING_ID.fullmatch(posting_id)
    ) or (country is not None and re.fullmatch(r"[a-z]{2}", country) is None):
        raise ValueError("Invalid SmartRecruiters board or posting identity")
    url = f"{API_ROOT}{quote(board, safe='')}/postings"
    url += f"/{quote(posting_id, safe='')}" if posting_id else f"?limit={LIST_LIMIT}&offset=0"
    if country is not None and posting_id is None:
        url += f"&country={country}"
    request = Request(  # noqa: S310 - fixed HTTPS origin and validated path identities
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=12) as response:
            if response.geturl() != url:
                raise ValueError("SmartRecruiters response changed endpoint")
            raw = response.read(MAX_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError):
        raise RuntimeError("SmartRecruiters public request failed") from None
    if len(raw) > MAX_BYTES:
        raise ValueError("SmartRecruiters response exceeded the size limit")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError("SmartRecruiters returned invalid JSON") from None


def fetch_smartrecruiters(
    board: str, *, max_age_hours: int = 168, now: datetime | None = None,
    checkpoint: Callable[[], None] | None = None,
    coverage: dict[str, Any] | None = None,
    country: str | None = None, search_titles: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Read one listing page and at most ten recent details, with visible coverage.

releasedDate is the provider's publication/re-publication evidence. It never
becomes an original creation date or a guarantee that the vacancy is genuine.
"""
    if not BOARD_SLUG.fullmatch(board) or not 1 <= max_age_hours <= 168:
        raise ValueError("Choose a reviewed board and a freshness window up to seven days")
    now = now or datetime.now(UTC)
    check = checkpoint or (lambda: None)
    check()
    payload = _read_public(board, country=country)
    if not isinstance(payload, dict) or not isinstance(payload.get("content"), list):
        raise ValueError("SmartRecruiters returned an invalid posting list")
    raw_list = payload["content"][:LIST_LIMIT]
    total = payload.get("totalFound")
    total = total if isinstance(total, int) and not isinstance(total, bool) and total >= 0 else None
    stats = {
        "provider": "smartrecruiters", "board": board,
        "listed": len(raw_list), "reported_total": total, "details_fetched": 0,
        "detail_failures": 0, "returned": 0,
        "truncated": (total is None or total != len(raw_list)
                      or len(payload["content"]) > LIST_LIMIT),
        "list_limit": LIST_LIMIT, "detail_limit": DETAIL_LIMIT,
        "submission_supported": False, "model_calls": 0,
        "country_filter": country, "title_priority_applied": bool(search_titles),
    }
    candidates = []
    seen = set()
    for posting in raw_list:
        if not isinstance(posting, dict) or posting.get("active") is False:
            continue
        identifier = posting.get("id")
        company = posting.get("company")
        published = _parse_datetime(posting.get("releasedDate"))
        if (not isinstance(identifier, str) or not POSTING_ID.fullmatch(identifier)
                or identifier in seen or not isinstance(company, dict)
                or str(company.get("identifier", "")).casefold() != board.casefold()
                or published is None or not 0 <= (now - published).total_seconds() / 3600
                <= max_age_hours):
            continue
        seen.add(identifier)
        candidates.append((published, identifier, posting))
    titles = [value.casefold().strip()[:120] for value in (search_titles or [])[:20]
              if isinstance(value, str) and value.strip()]
    tokens = {token for title in titles for token in re.findall(r"[a-z0-9+#]+", title)
              if len(token) > 2}

    def priority(item: tuple[datetime, str, dict[str, Any]]) -> tuple[int, int, datetime]:
        title = str(item[2].get("name") or "").casefold()
        overlap = tokens & set(re.findall(r"[a-z0-9+#]+", title))
        return int(any(term in title for term in titles)), len(overlap), item[0]

    candidates.sort(key=priority, reverse=True)
    stats["truncated"] = stats["truncated"] or len(candidates) > DETAIL_LIMIT
    result = []
    for published, identifier, posting in candidates[:DETAIL_LIMIT]:
        check()
        stats["details_fetched"] += 1
        try:
            details = _read_public(board, identifier)
        except (RuntimeError, ValueError):
            stats["detail_failures"] += 1
            continue
        check()
        if not isinstance(details, dict) or details.get("active") is False:
            continue
        company = details.get("company")
        if (str(details.get("id", "")) != identifier or not isinstance(company, dict)
                or str(company.get("identifier", "")).casefold() != board.casefold()):
            continue
        # A detail may be newer than its listing snapshot. Use its date when
        # available and never fall back after an invalid explicit date.
        if "releasedDate" in details:
            published = _parse_datetime(details["releasedDate"])
        if published is None or not 0 <= (now - published).total_seconds() / 3600 <= max_age_hours:
            continue
        job_ad = details.get("jobAd")
        sections = job_ad.get("sections", {}) if isinstance(job_ad, dict) else {}
        if not isinstance(sections, dict):
            sections = {}
        description = "\n\n".join(
            _plain_text(section["text"], limit=25000)
            for key in (
                "companyDescription", "jobDescription", "qualifications", "additionalInformation",
            )
            if isinstance((section := sections.get(key)), dict)
            and isinstance(section.get("text"), str)
        )[:100000]
        if not description.strip():
            stats["detail_failures"] += 1
            continue
        location = details.get("location")
        location = location if isinstance(location, dict) else {}
        employment = details.get("typeOfEmployment")
        employment = employment if isinstance(employment, dict) else {}
        location_text = ", ".join(str(location.get(key) or "").strip()
                                  for key in ("city", "region", "country") if location.get(key))
        # ISO country codes are presentation data, not inferred remote eligibility.
        location_text = re.sub(r"\bIN\b", "India", location_text)
        url = f"https://jobs.smartrecruiters.com/{board}/{identifier}"
        result.append({
            "source": "smartrecruiters", "source_key": f"{board}:{identifier}",
            "company": str(company.get("name") or board)[:240],
            "title": str(details.get("name") or posting.get("name") or "Untitled role")[:300],
            "location": location_text[:300], "description": description,
            "remote": location.get("remote") is True,
            "employment_type": _normalize_employment_type(str(employment.get("label") or "")),
            "source_url": url, "apply_url": url,
            "published_at": published, "published_at_basis": "published",
        })
    stats["returned"] = len(result)
    stats["truncated"] = stats["truncated"] or stats["detail_failures"] > 0
    if coverage is not None:
        coverage.update(stats)
    return result
