"""Bounded, unauthenticated YC discovery; application execution is never enabled.

Observed public HTML contract, 2026-11-02:
https://www.ycombinator.com/companies/clickpe/jobs
https://www.ycombinator.com/companies/aviator/jobs/aaMaqQu-software-engineering-intern
The rendered company links and public Inertia job identities are cross-checked.
Only the matching JobPosting JSON-LD datePosted establishes publication. For
example, the Aviator detail still declares 2022-03-03T00:59:42Z despite appearing
in a "recently" index. createdAt/lastActive and showDirectApply are not authority;
the latter can accompany an account.ycombinator.com authentication applyUrl.
This is an original parser for public pages, not a versioned provider API.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.career import USER_AGENT, _normalize_employment_type, _plain_text

ROOT = "https://www.ycombinator.com"
LIST_LIMIT, DETAIL_LIMIT, MAX_BYTES = 50, 10, 2 * 1024 * 1024
COMPANY = re.compile(r"[a-z0-9][a-z0-9-]{0,99}\Z")
POSTING = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}\Z")
INSTANT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z")


class _Blocked(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        raise _Blocked("YC public redirect refused")


def _canonical(value: Any, company: str, *, detail: bool) -> str | None:
    if (not isinstance(value, str) or len(value) > 2048 or "\\" in value
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.query or parsed.fragment or parsed.username is not None
                or parsed.password is not None or parsed.port not in {None, 443}
                or (parsed.netloc and (parsed.scheme != "https"
                                      or parsed.hostname != "www.ycombinator.com"))
                or (not parsed.netloc and (parsed.scheme or not value.startswith("/")))):
            return None
    except ValueError:
        return None
    prefix = f"/companies/{company}/jobs"
    if not detail:
        return ROOT + prefix if parsed.path == prefix else None
    if not parsed.path.startswith(prefix + "/"):
        return None
    posting = parsed.path[len(prefix) + 1:]
    return ROOT + prefix + "/" + posting if POSTING.fullmatch(posting) else None


def _read_public(company: str, posting: str | None = None) -> str:
    if not COMPANY.fullmatch(company) or (posting is not None and not POSTING.fullmatch(posting)):
        raise ValueError("Invalid YC company or posting identity")
    url = f"{ROOT}/companies/{company}/jobs" + (f"/{posting}" if posting else "")
    request = Request(  # noqa: S310 - fixed HTTPS origin and validated path identities
        url, headers={"Accept": "text/html", "User-Agent": USER_AGENT},
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=12) as response:
            if response.geturl() != url:
                raise _Blocked("YC public endpoint changed")
            if response.headers.get("Content-Type", "").split(";", 1)[0].lower() != "text/html":
                raise ValueError("YC returned an unexpected public content type")
            raw = response.read(MAX_BYTES + 1)
    except HTTPError as exc:
        if exc.code in {401, 403, 429}:
            raise _Blocked("YC public access blocked or rate limited") from None
        raise RuntimeError("YC public request failed") from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError("YC public request failed") from None
    if len(raw) > MAX_BYTES:
        raise ValueError("YC public response exceeded the size limit")
    try:
        return raw.decode("utf-8")
    except UnicodeError:
        raise ValueError("YC public response was not valid UTF-8") from None


class _Page(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.pages: list[str] = []
        self.links: set[str] = set()
        self.schemas: list[str] = []
        self.script: list[str] | None = None
        self.feed(source)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if "data-page" in values:
            self.pages.append(values["data-page"] or "")
        if tag == "a" and values.get("href"):
            self.links.add(str(values["href"]))
        if tag == "script" and str(values.get("type") or "").lower() == "application/ld+json":
            self.script = []

    def handle_data(self, data: str) -> None:
        if self.script is not None:
            self.script.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.script is not None:
            self.schemas.append("".join(self.script))
            self.script = None

    def props(self, company: str) -> dict[str, Any]:
        if len(self.pages) != 1:
            raise ValueError("YC public page metadata is missing or ambiguous")
        try:
            page = json.loads(self.pages[0])
            props = page["props"]
            if (not isinstance(props, dict) or not isinstance(props.get("company"), dict)
                    or props["company"].get("slug") != company):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise ValueError("YC public company identity did not match") from None
        if props.get("signedIn") is True or props.get("currentUser") is not None:
            raise _Blocked("YC returned account content instead of a public page")
        return props


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or not INSTANT.fullmatch(value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _text(value: Any, limit: int = 300) -> str:
    return _plain_text(value, limit=limit).strip() if isinstance(value, str) else ""


def _countries(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result = []
    for item in values[:20]:
        name = item.get("name") if isinstance(item, dict) else item
        if name := _text(name, 80):
            result.append({"IN": "India", "US": "United States"}.get(name, name))
    return list(dict.fromkeys(result))


def _normalize(page: _Page, company: str, candidate: dict[str, Any], now: datetime,
               max_age_hours: int) -> tuple[dict[str, Any] | None, str]:
    props = page.props(company)
    job, employer = props.get("job"), props["company"]
    url = candidate["url"]
    if (not isinstance(job, dict) or type(job.get("id")) is not int
            or job.get("id") != candidate["id"]
            or _canonical(job.get("url"), company, detail=True) != url
            or job.get("companyUrl") != f"/companies/{company}"
            or job.get("isIncomplete") is True):
        raise ValueError("YC detail posting identity did not match the list")
    schemas = []
    for source in page.schemas[:20]:
        try:
            data = json.loads(source)
        except ValueError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes[:50]:
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph", [])
            children = [node] + (graph if isinstance(graph, list) else [])
            for schema in children[:50]:
                if (isinstance(schema, dict) and schema.get("@type") == "JobPosting"
                        and _canonical(schema.get("url"), company, detail=True) == url):
                    schemas.append(schema)
    if len(schemas) != 1:
        raise ValueError("YC matching JobPosting metadata is missing or ambiguous")
    schema = schemas[0]
    organization = schema.get("hiringOrganization")
    title, name = _text(job.get("title")), _text(employer.get("name"), 240)
    if (not title or not name or _text(schema.get("title")) != title
            or not isinstance(organization, dict) or _text(organization.get("name"), 240) != name):
        raise ValueError("YC posting title or employer identity did not match")
    published = _instant(schema.get("datePosted"))
    if published is None:
        return None, "unknown_date"
    age = (now - published).total_seconds() / 3600
    if age < 0:
        return None, "future_date"
    if age > max_age_hours:
        return None, "stale_date"
    if "validThrough" in schema:
        valid_until = _instant(schema["validThrough"])
        if valid_until is None:
            raise ValueError("YC posting expiry metadata is invalid")
        if valid_until <= now:
            return None, "closed"
    description = _text(schema.get("description"), 98000)
    if not description:
        raise ValueError("YC posting description is missing")
    declared = {key: _text(job.get(key), 300) for key in (
        "location", "visa", "minExperience", "minSchoolYear", "type",
    )}
    requirements = _countries(schema.get("applicantLocationRequirements"))
    remote = schema.get("jobLocationType") == "TELECOMMUTE"
    location = ("Remote (" + "; ".join(requirements) + ")"
                if remote and requirements else declared["location"])
    location = re.sub(r"\bIN\b", "India", location)
    constraints = "\n".join(f"{key}: {value}" for key, value in declared.items()
                            if value and key != "visa")
    if declared["visa"]:
        constraints += "\nPlatform visa requirement: " + declared["visa"] + "."
    if requirements:
        constraints += "\nRemote applicant locations: " + "; ".join(requirements)
    suffix = "\n\nDeclared YC constraints:\n" + constraints
    return {
        "source": "yc", "source_key": f"{company}:{job['id']}", "company": name,
        "title": title, "location": location[:300], "remote": remote,
        "employment_type": _normalize_employment_type(declared["type"]),
        "description": description[:100000 - len(suffix)] + suffix,
        "source_url": url, "apply_url": url, "published_at": published,
        "published_at_basis": "published", "publication_field": "JobPosting.datePosted",
        "submission_supported": False, "submission_mode": "manual",
        "source_constraints": {**declared, "applicant_locations": requirements},
    }, "returned"


def fetch_yc(
    company: str, *, max_age_hours: int = 72, now: datetime | None = None,
    checkpoint: Callable[[], None] | None = None, coverage: dict[str, Any] | None = None,
    search_titles: list[str] | None = None, detail_limit: int = DETAIL_LIMIT,
) -> list[dict[str, Any]]:
    """Read one public company list and at most ten relevant details, without accounts."""
    if (not isinstance(company, str) or not COMPANY.fullmatch(company)
            or type(max_age_hours) is not int or not 1 <= max_age_hours <= 168
            or type(detail_limit) is not int or not 0 <= detail_limit <= DETAIL_LIMIT):
        raise ValueError("Choose a reviewed YC slug, freshness window and detail budget")
    now = now or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("YC freshness checks require a timezone-aware current time")
    check = checkpoint or (lambda: None)
    stats: dict[str, Any] = {
        "provider": "yc", "board": company, "listed": 0, "reported_total": None,
        "observed_list_records": 0, "coverage_scope": "single_company_public_page",
        "details_fetched": 0, "detail_failures": 0, "list_failures": 0, "invalid_list_records": 0,
        "returned": 0, "unknown_date": 0, "future_date": 0, "stale_date": 0, "closed": 0,
        "truncated": True, "blocked": False, "list_limit": LIST_LIMIT, "detail_limit": detail_limit,
        "submission_supported": False, "model_calls": 0,
        "title_priority_applied": bool(search_titles),
    }
    completed = False
    try:
        check()
        try:
            listing = _Page(_read_public(company))
            props = listing.props(company)
            if (_canonical(props.get("jobsUrl"), company, detail=False)
                    != f"{ROOT}/companies/{company}/jobs"
                    or not isinstance(props.get("jobPostings"), list)):
                raise ValueError("YC returned an invalid public job list")
        except (RuntimeError, ValueError, RecursionError) as exc:
            stats["list_failures"] = 1
            stats["blocked"] = isinstance(exc, _Blocked)
            raise
        raw = props["jobPostings"]
        # Public HTML exposes this page's records, not a documented complete-board total.
        stats.update(listed=min(len(raw), LIST_LIMIT), observed_list_records=len(raw))
        links = {_canonical(link, company, detail=True) for link in listing.links}
        seen, seen_urls, candidates = set(), set(), []
        for item in raw[:LIST_LIMIT]:
            url = (_canonical(item.get("url"), company, detail=True)
                   if isinstance(item, dict) else None)
            if (not url or url not in links or type(item.get("id")) is not int
                    or not 0 < item["id"] < 2**63 or not _text(item.get("title"))):
                stats["invalid_list_records"] += 1
                continue
            if item["id"] in seen:
                continue
            if url in seen_urls:
                stats["invalid_list_records"] += 1
                continue
            seen.add(item["id"])
            seen_urls.add(url)
            candidates.append({"id": item["id"], "url": url, "title": _text(item["title"])})
        titles = [_text(value, 120).casefold() for value in (search_titles or [])[:20]
                  if isinstance(value, str) and value.strip()]
        tokens = {token for title in titles for token in re.findall(r"[a-z0-9+#]+", title)
                  if len(token) > 2}

        def priority(item: dict[str, Any]) -> tuple[bool, int]:
            title = item["title"].casefold()
            overlap = tokens & set(re.findall(r"[a-z0-9+#]+", title))
            return any(term in title for term in titles), len(overlap)

        if titles:
            candidates = [item for item in candidates if any(priority(item))]
            candidates.sort(key=priority, reverse=True)
        stats["truncated"] = len(raw) > LIST_LIMIT or len(candidates) > detail_limit
        result = []
        for candidate in candidates[:detail_limit]:
            check()
            stats["details_fetched"] += 1
            try:
                source = _read_public(company, candidate["url"].rsplit("/", 1)[-1])
            except _Blocked:
                stats["detail_failures"] += 1
                stats["blocked"] = True
                break
            except (ValueError, RuntimeError):
                stats["detail_failures"] += 1
                continue
            check()
            try:
                row, reason = _normalize(_Page(source), company, candidate, now, max_age_hours)
            except _Blocked:
                stats["detail_failures"] += 1
                stats["blocked"] = True
                break
            except (ValueError, RuntimeError, RecursionError):
                stats["detail_failures"] += 1
                continue
            stats[reason] += 1
            if row is not None:
                result.append(row)
        completed = True
        return result
    finally:
        stats["truncated"] = bool(not completed or stats["truncated"] or stats["detail_failures"]
                                  or stats["invalid_list_records"])
        if coverage is not None:
            coverage.update(stats)
