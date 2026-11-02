"""Resolve public employer-board links locally, without following untrusted URLs."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import ParseResult, parse_qs, urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

BOARD_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}\Z")
POSTING_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,159}\Z")
YC_COMPANY = re.compile(r"[a-z0-9][a-z0-9-]{0,99}\Z")
YC_POSTING = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}\Z")
LINKEDIN_JOB = re.compile(r"/jobs/view/(?:[A-Za-z0-9][A-Za-z0-9_-]{0,199}-)?([0-9]{1,32})/?\Z")
LINKEDIN_HOSTS = {"linkedin.com", "www.linkedin.com", "in.linkedin.com"}
YC_HOSTS = {"ycombinator.com", "www.ycombinator.com"}
REVIEWED_HOSTS = {
    "jobs.ashbyhq.com": ("ashby", "ashby_boards"),
    "boards.greenhouse.io": ("greenhouse", "greenhouse_boards"),
    "job-boards.greenhouse.io": ("greenhouse", "greenhouse_boards"),
    "jobs.lever.co": ("lever", "lever_boards"),
    "jobs.eu.lever.co": ("lever", "lever_eu_boards"),
    "jobs.smartrecruiters.com": ("smartrecruiters", "smartrecruiters_boards"),
    "careers.smartrecruiters.com": ("smartrecruiters", "smartrecruiters_boards"),
    "www.smartrecruiters.com": ("smartrecruiters", "smartrecruiters_boards"),
}


class CareerSourceResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    employer_url: str | None = Field(default=None, min_length=1, max_length=2048)


class ResolvedCareerSource(BaseModel):
    provider: Literal["ashby", "greenhouse", "lever", "smartrecruiters", "yc"]
    board: str
    source_config_key: Literal[
        "ashby_boards", "greenhouse_boards", "lever_boards", "lever_eu_boards",
        "smartrecruiters_boards", "yc_companies",
    ]
    board_url: str
    posting_url: str | None
    discovery_platform: Literal["linkedin", "yc"] | None = None
    discovery_url: str | None = None
    employer_url: str | None = None
    scope: Literal["employer_board"] = "employer_board"
    fetch_performed: Literal[False] = False
    model_calls: Literal[0] = 0
    notice: str = (
        "Adds the entire employer board. Save the mission and run a scan for current listings. "
        "Recognizing this URL does not verify the employer or submit an application."
    )


def _parse_public_url(value: str) -> ParseResult:
    url = value.strip()
    if (not url or len(url) > 2048 or "\\" in url
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url)):
        raise ValueError("Paste one HTTPS employer board or job URL")
    try:
        parsed = urlparse(url)
        valid_origin = (parsed.scheme == "https" and parsed.hostname
                        and parsed.username is None and parsed.password is None
                        and parsed.port in {None, 443} and not parsed.params
                        and "#" not in url and "%" not in parsed.path
                        and "//" not in parsed.path)
    except ValueError:
        raise ValueError("Paste a valid HTTPS employer board or job URL") from None
    if not valid_origin:
        raise ValueError("Use an HTTPS URL without credentials, fragments or encoded paths")
    return parsed


def _linkedin_source_url(parsed: ParseResult) -> str:
    match = LINKEDIN_JOB.fullmatch(parsed.path)
    if parsed.hostname not in LINKEDIN_HOSTS or match is None:
        raise ValueError("Use a direct LinkedIn /jobs/view/ job URL, not a search or redirect link")
    return f"https://www.linkedin.com/jobs/view/{match[1]}"


def _yc_source(parsed: ParseResult) -> tuple[str, str, str | None, str]:
    parts = parsed.path.removesuffix("/").split("/")
    if (parsed.hostname not in YC_HOSTS or len(parts) not in {3, 4, 5}
            or parts[:2] != ["", "companies"] or not YC_COMPANY.fullmatch(parts[2])
            or (len(parts) >= 4 and parts[3] != "jobs")
            or (len(parts) == 5 and not YC_POSTING.fullmatch(parts[4]))):
        raise ValueError("Use a direct YC /companies/company or company/jobs/posting URL")
    board_url = f"https://www.ycombinator.com/companies/{parts[2]}/jobs"
    posting_url = f"{board_url}/{parts[4]}" if len(parts) == 5 else None
    source_url = "https://www.ycombinator.com" + parsed.path.removesuffix("/")
    return parts[2], board_url, posting_url, source_url


def _resolve_employer_source(parsed: ParseResult) -> ResolvedCareerSource:
    host = parsed.hostname or ""
    if host not in REVIEWED_HOSTS:
        raise ValueError(
            "Use a reviewed Ashby, Greenhouse, Lever or SmartRecruiters employer URL. "
            "For a company careers page, copy its supported application link."
        )
    provider, config_key = REVIEWED_HOSTS[host]
    parts = parsed.path.strip("/").split("/")
    # Percent-encoded separators, dot segments and malformed board names never
    # become API paths. No part of the supplied URL is fetched by this resolver.
    if not parts or any(not POSTING_ID.fullmatch(part) for part in parts):
        raise ValueError("The employer board or posting path is not supported")
    posting_id: str | None = None
    if provider == "greenhouse" and parts[0] == "embed":
        if parts not in [["embed", "job_app"], ["embed", "job_board"]]:
            raise ValueError("The Greenhouse embedded path is not supported")
        try:
            parameters = parse_qs(parsed.query, max_num_fields=30)
        except ValueError:
            raise ValueError("The embedded board parameters are invalid") from None
        boards = parameters.get("for", [])
        tokens = parameters.get("token", [])
        if len(boards) != 1 or not BOARD_SLUG.fullmatch(boards[0]):
            raise ValueError("The embedded Greenhouse URL needs one employer board")
        board = boards[0]
        if parts[1] == "job_app":
            if len(tokens) != 1 or not re.fullmatch(r"[0-9]{1,32}", tokens[0]):
                raise ValueError("The embedded Greenhouse URL needs one posting token")
            posting_id = tokens[0]
        canonical_host = "job-boards.greenhouse.io"
    else:
        board = parts[0]
        if not BOARD_SLUG.fullmatch(board):
            raise ValueError("The employer board name is invalid")
        canonical_host = host
        if provider == "greenhouse":
            if len(parts) != 1:
                if (len(parts) not in {3, 4} or parts[1] != "jobs"
                        or not re.fullmatch(r"[0-9]{1,32}", parts[2])
                        or (len(parts) == 4 and parts[3] != "application")):
                    raise ValueError("The Greenhouse board or posting path is not supported")
                posting_id = parts[2]
        elif provider == "smartrecruiters":
            if len(parts) > 2 or (host == "careers.smartrecruiters.com" and len(parts) != 1):
                raise ValueError("The SmartRecruiters board or posting path is not supported")
            canonical_host = "jobs.smartrecruiters.com"
            posting_id = parts[1] if len(parts) == 2 else None
        elif len(parts) != 1:
            suffix = "application" if provider == "ashby" else "apply"
            if len(parts) not in {2, 3} or (len(parts) == 3 and parts[2] != suffix):
                raise ValueError("The employer board or posting path is not supported")
            posting_id = parts[1]
    board_url = f"https://{canonical_host}/{board}"
    posting_url = None
    if posting_id is not None:
        posting_url = (f"{board_url}/jobs/{posting_id}" if provider == "greenhouse"
                       else f"{board_url}/{posting_id}")
    notice = ResolvedCareerSource.model_fields["notice"].default
    if provider == "smartrecruiters":
        notice = (
            "Adds the entire employer board for bounded public discovery. "
            "SmartRecruiters application execution is not connected; submit manually. "
            "Recognizing this URL does not verify the employer."
        )
    return ResolvedCareerSource(
        provider=provider, board=board, source_config_key=config_key,
        board_url=board_url, posting_url=posting_url, notice=notice,
    )


class CareerDiscoveryLead(BaseModel):
    """A reviewed discovery reference; it grants no fetch or submission authority."""

    model_config = ConfigDict(extra="forbid")
    platform: Literal["linkedin", "yc"]
    source_url: str = Field(min_length=1, max_length=2048)
    employer_url: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def normalize_references(self) -> CareerDiscoveryLead:
        parsed = _parse_public_url(self.source_url)
        self.source_url = (_linkedin_source_url(parsed) if self.platform == "linkedin"
                           else _yc_source(parsed)[3])
        employer = _resolve_employer_source(_parse_public_url(self.employer_url))
        self.employer_url = employer.posting_url or employer.board_url
        return self


def resolve_career_source(value: str, employer_url: str | None = None) -> ResolvedCareerSource:
    """Pure intake: retain a public platform reference and a separately observed ATS link."""
    parsed = _parse_public_url(value)
    host = parsed.hostname or ""
    platform: Literal["linkedin", "yc"] | None = None
    source_url: str | None = None
    if host in LINKEDIN_HOSTS:
        platform, source_url = "linkedin", _linkedin_source_url(parsed)
        if employer_url is None:
            raise ValueError(
                "Open the employer's application link and paste its supported ATS URL in "
                "employer_url. LinkedIn account applications are not connected."
            )
    elif host in YC_HOSTS:
        board, board_url, posting_url, source_url = _yc_source(parsed)
        platform = "yc"
        if employer_url is None:
            return ResolvedCareerSource(
                provider="yc", board=board, source_config_key="yc_companies",
                board_url=board_url, posting_url=posting_url,
                notice=(
                    "Adds the YC company's public job board for bounded discovery. "
                    "YC account applications are not connected; submit manually. "
                    "A scan must verify each job's publication date and eligibility."
                ),
            )
    elif employer_url is not None:
        raise ValueError("An employer_url pairs only with a LinkedIn or YC discovery URL")
    elif host in {"workatastartup.com", "www.workatastartup.com"}:
        raise ValueError(
            "Open the employer's application link and paste its supported ATS URL. "
            "Work at a Startup account applications are not connected."
        )
    if platform is None:
        return _resolve_employer_source(parsed)
    employer = _resolve_employer_source(_parse_public_url(str(employer_url)))
    return employer.model_copy(update={
        "discovery_platform": platform, "discovery_url": source_url,
        "employer_url": employer.posting_url or employer.board_url,
        "notice": (
            f"Preserves the {platform} discovery reference and adds the entire employer board. "
            "It does not connect a platform account or submit through LinkedIn or YC. "
            + employer.notice
        ),
    })


def normalize_yc_companies(values: list[str]) -> list[str]:
    if len(values) > 30:
        raise ValueError("No more than 30 YC companies are allowed")
    companies: list[str] = []
    for value in values:
        company = value.strip()
        if not company:
            continue
        if YC_COMPANY.fullmatch(company.casefold()):
            company = company.casefold()
        else:
            company = _yc_source(_parse_public_url(company))[0]
        if company not in companies:
            companies.append(company)
    return companies


def normalize_source_boards(values: list[str], *, config_key: str) -> list[str]:
    if len(values) > 30:
        raise ValueError("No more than 30 employer boards are allowed per source")
    boards: list[str] = []
    seen: set[str] = set()
    for value in values:
        board = value.strip()
        if not board:
            continue
        if not BOARD_SLUG.fullmatch(board):
            resolved = resolve_career_source(board)
            if resolved.source_config_key != config_key:
                raise ValueError(
                    f"This URL belongs in {resolved.source_config_key}; use the matching source"
                )
            board = resolved.board
        if board.casefold() not in seen:
            boards.append(board)
            seen.add(board.casefold())
    return boards
