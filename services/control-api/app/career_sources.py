"""Resolve public employer-board links locally, without following untrusted URLs."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, ConfigDict, Field

BOARD_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}\Z")
POSTING_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,159}\Z")
REVIEWED_HOSTS = {
    "jobs.ashbyhq.com": ("ashby", "ashby_boards"),
    "boards.greenhouse.io": ("greenhouse", "greenhouse_boards"),
    "job-boards.greenhouse.io": ("greenhouse", "greenhouse_boards"),
    "jobs.lever.co": ("lever", "lever_boards"),
    "jobs.eu.lever.co": ("lever", "lever_eu_boards"),
}


class CareerSourceResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)


class ResolvedCareerSource(BaseModel):
    provider: Literal["ashby", "greenhouse", "lever"]
    board: str
    source_config_key: Literal[
        "ashby_boards", "greenhouse_boards", "lever_boards", "lever_eu_boards",
    ]
    board_url: str
    posting_url: str | None
    scope: Literal["employer_board"] = "employer_board"
    fetch_performed: Literal[False] = False
    model_calls: Literal[0] = 0
    notice: str = (
        "Adds the entire employer board. Save the mission and run a scan for current listings. "
        "Recognizing this URL does not verify the employer or submit an application."
    )


def resolve_career_source(value: str) -> ResolvedCareerSource:
    """Strip tracking parameters and derive only a fixed public-API board identity."""
    url = value.strip()
    if (not url or len(url) > 2048 or "\\" in url
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url)):
        raise ValueError("Paste one HTTPS employer board or job URL")
    try:
        parsed = urlparse(url)
        valid_origin = (parsed.scheme == "https" and parsed.hostname in REVIEWED_HOSTS
                        and parsed.username is None and parsed.password is None
                        and parsed.port in {None, 443})
    except ValueError:
        raise ValueError("Paste a valid HTTPS employer board or job URL") from None
    host = parsed.hostname or ""
    if host in {"linkedin.com", "www.linkedin.com", "ycombinator.com",
                "www.ycombinator.com", "workatastartup.com", "www.workatastartup.com"}:
        raise ValueError(
            "Open the employer's application link and paste its Ashby, Greenhouse or Lever URL. "
            "LinkedIn and Y Combinator account applications are not connected."
        )
    if not valid_origin:
        raise ValueError(
            "Use a reviewed Ashby, Greenhouse or Lever employer URL. "
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
    return ResolvedCareerSource(
        provider=provider, board=board, source_config_key=config_key,
        board_url=board_url, posting_url=posting_url,
    )


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
