from __future__ import annotations

import html
import json
import math
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from app.creator_intelligence import (
    CHANNEL_ID,
    VIDEO_ID,
    build_creator_intelligence,
    fit_breakdown,
    public_video_id,
    public_youtube_identity,
)

YOUTUBE_API_HOST = "www.googleapis.com"
MAX_YOUTUBE_BYTES = 2 * 1024 * 1024
MAX_DISCOVERY_QUERIES = 3
MAX_SEARCH_PAGES = 3
MAX_RESULTS_PER_PAGE = 25
MAX_DISCOVERED_CHANNELS = MAX_DISCOVERY_QUERIES * MAX_SEARCH_PAGES * MAX_RESULTS_PER_PAGE
USER_AGENT = (
    "HermesCreatorScout/0.1 "
    "(+https://github.com/ReaperXD67/autonomous-personal-agent)"
)
INITIAL_VARIANTS = ("viewer_value", "creator_pilot")


class YouTubeRequestLimitError(RuntimeError):
    """A provider-declared limit; callers must stop rather than retry another page."""

    def __init__(self, *, quota_exhausted: bool = False, rate_limited: bool = False):
        super().__init__("YouTube API request limit reached; research stopped")
        self.quota_exhausted = quota_exhausted
        self.rate_limited = rate_limited


def _youtube_limit_error(payload: Any, status: int = 0) -> YouTubeRequestLimitError | None:
    error = payload.get("error") if isinstance(payload, dict) else None
    errors = error.get("errors", []) if isinstance(error, dict) else []
    reasons = {
        item.get("reason") for item in errors[:20]
        if isinstance(item, dict) and isinstance(item.get("reason"), str)
    } if isinstance(errors, list) else set()
    quota = bool(reasons & {"quotaExceeded", "dailyLimitExceeded", "dailyLimitExceededUnreg"})
    rate = status == 429 or bool(reasons & {"rateLimitExceeded", "userRateLimitExceeded"})
    if quota or rate:
        return YouTubeRequestLimitError(quota_exhausted=quota, rate_limited=rate)
    return None


class _YouTubeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.netloc != YOUTUBE_API_HOST:
            raise ValueError("YouTube API redirected outside the reviewed host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read_youtube_json(path: str, parameters: dict[str, str | int]) -> dict[str, Any]:
    if path not in {"/youtube/v3/search", "/youtube/v3/channels", "/youtube/v3/videos"}:
        raise ValueError("YouTube API path is outside the reviewed endpoints")
    url = f"https://{YOUTUBE_API_HOST}{path}?{urlencode(parameters)}"
    request = Request(  # noqa: S310 - exact HTTPS host and API prefix are fixed above
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with build_opener(_YouTubeRedirectHandler()).open(request, timeout=20) as response:
            final = urlparse(response.geturl())
            if final.scheme != "https" or final.netloc != YOUTUBE_API_HOST:
                raise ValueError("YouTube API resolved outside the reviewed host")
            raw = response.read(MAX_YOUTUBE_BYTES + 1)
    except HTTPError as exc:
        try:
            error_payload = json.loads(exc.read(16 * 1024))
        except (ValueError, OSError):
            error_payload = {}
        limit_error = _youtube_limit_error(error_payload, exc.code)
        if limit_error:
            raise limit_error from None
        raise RuntimeError(f"YouTube API request failed with HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError("YouTube API request failed") from None
    if len(raw) > MAX_YOUTUBE_BYTES:
        raise ValueError("YouTube API response exceeded the size limit")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("YouTube API returned invalid JSON") from None
    if not isinstance(payload, dict):
        raise ValueError("YouTube API returned an unexpected response")
    if "error" in payload:
        limit_error = _youtube_limit_error(payload)
        if limit_error:
            raise limit_error
        raise RuntimeError("YouTube API returned an error response")
    return payload


def _parse_youtube_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _bounded_text(value: Any, limit: int) -> str:
    return " ".join(html.unescape(str(value or "")).split())[:limit]


def score_creator(
    *,
    audience_size: int | None,
    content_published_at: datetime | None,
    minimum_audience: int,
    maximum_audience: int,
    content_text: str = "",
    now: datetime | None = None,
) -> tuple[int, list[str]]:
    breakdown = fit_breakdown(
        content=content_text, audience_size=audience_size,
        published_at=content_published_at, minimum_audience=minimum_audience,
        maximum_audience=maximum_audience, now=now or datetime.now(UTC),
    )
    return sum(item["points"] for item in breakdown), [item["evidence"] for item in breakdown]


def _youtube_items(payload: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items[:limit] if isinstance(item, dict)]


def _public_count(value: Any, *, limit: int = 1_000_000_000_000) -> int | None:
    if isinstance(value, bool) or not re.fullmatch(r"\d{1,13}", str(value)):
        return None
    count = int(value)
    return count if count <= limit else None


def _apply_channel(item: dict[str, Any], prospect: dict[str, Any]) -> None:
    snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
    statistics = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
    prospect.update({
        "display_name": _bounded_text(snippet.get("title"), 300) or prospect["display_name"],
        "audience_size": None if statistics.get("hiddenSubscriberCount") else
        _public_count(statistics.get("subscriberCount"), limit=1_000_000_000),
        "channel_description": snippet.get("description", ""),
        "channel_country": snippet.get("country"),
        "channel_language": snippet.get("defaultLanguage"),
        "channel_enriched": True,
    })


def _enrich_videos(
    api_key: str, discovered: dict[str, dict[str, Any]], *,
    request_json: Callable[[str, dict[str, str | int]], dict[str, Any]] | None = None,
    research_stats: dict[str, int] | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> None:
    read = request_json or _read_youtube_json
    by_video = {
        item["video_id"]: item for item in discovered.values() if item.get("video_id")
    }
    ids = list(by_video)[:MAX_DISCOVERED_CHANNELS]
    for start in range(0, len(ids), 50):
        batch = ids[start:start + 50]
        if checkpoint is not None:
            checkpoint()
        try:
            payload = read("/youtube/v3/videos", {
                "part": "snippet,statistics", "id": ",".join(batch), "key": api_key,
            })
            if not isinstance(payload.get("items"), list):
                raise ValueError("YouTube video metadata returned an unexpected result list")
        except YouTubeRequestLimitError:
            if research_stats is not None:
                research_stats["enrichment_failures"] += 1
            break
        except (RuntimeError, ValueError):
            if research_stats is not None:
                research_stats["enrichment_failures"] += 1
            continue
        for video in _youtube_items(payload):
            video_id = video.get("id")
            if not isinstance(video_id, str) or video_id not in batch:
                continue
            snippet = video.get("snippet")
            prospect = by_video[video_id]
            if not isinstance(snippet, dict):
                continue
            if snippet.get("channelId") != prospect["channel_id"]:
                prospect.update({
                    "video_identity_mismatch": True, "video_id": None,
                    "latest_content_url": None, "latest_content_title": None,
                    "latest_content_published_at": None,
                })
                continue
            statistics = video.get("statistics")
            statistics = statistics if isinstance(statistics, dict) else {}
            prospect.update({
                "video_description": snippet.get("description", ""),
                "video_audio_language": snippet.get("defaultAudioLanguage"),
                "video_language": snippet.get("defaultLanguage"),
                "latest_content_title": _bounded_text(snippet.get("title"), 500) or None,
                "latest_content_published_at": _parse_youtube_datetime(snippet.get("publishedAt")),
                "video_enriched": True,
                "view_count": _public_count(statistics.get("viewCount")),
                "like_count": _public_count(statistics.get("likeCount")),
                "comment_count": _public_count(statistics.get("commentCount")),
            })


def _normalize_researched_prospect(
    campaign: dict[str, Any], item: dict[str, Any], reference: datetime,
) -> dict[str, Any]:
    item["profile_url"] = f"https://www.youtube.com/channel/{item['channel_id']}"
    intelligence = build_creator_intelligence(campaign, item, now=reference)
    breakdown = intelligence["fit_breakdown"]
    return {
        "platform": "youtube", "external_id": item["channel_id"],
        "display_name": item["display_name"], "profile_url": item["profile_url"],
        "audience_size": item.get("audience_size"),
        "latest_content_title": item.get("latest_content_title"),
        "latest_content_url": item.get("latest_content_url"),
        "latest_content_published_at": item.get("latest_content_published_at"),
        "discovery_query": item.get("discovery_query"),
        "relevance_score": sum(part["points"] for part in breakdown),
        "relevance_reasons": [part["evidence"] for part in breakdown],
        "intelligence": intelligence,
    }


def fetch_youtube_creators(
    api_key: str,
    campaign: dict[str, Any],
    *,
    now: datetime | None = None,
    selection_stats: dict[str, int] | None = None,
    reserve_search_request: Callable[[], bool] | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> list[dict[str, Any]]:
    if not api_key.strip():
        raise RuntimeError("YouTube discovery requires a restricted API key")
    reference = now or datetime.now(UTC)
    published_after = reference - timedelta(days=campaign["max_video_age_days"])
    discovered: dict[str, dict[str, Any]] = {}

    results_per_page = min(MAX_RESULTS_PER_PAGE, max(1, int(campaign["results_per_query"])))
    pages_per_query = min(MAX_SEARCH_PAGES, max(1, int(campaign.get("search_pages_per_query", 1))))
    queries = list(dict.fromkeys(campaign["discovery_queries"][:MAX_DISCOVERY_QUERIES]))
    research_stats = {
        "query_count": len(queries), "pages_per_query": pages_per_query,
        "results_per_page": results_per_page,
        "search_request_limit": len(queries) * pages_per_query,
        "channel_limit": len(queries) * pages_per_query * results_per_page,
        "search_requests": 0, "search_pages": 0, "search_results": 0,
        "duplicate_channels": 0, "invalid_results": 0, "search_failures": 0,
        "queries_started": 0, "queries_exhausted": 0, "queries_page_limited": 0,
        "pagination_errors": 0, "search_budget_exhausted": 0,
        "quota_exhausted": 0, "rate_limited": 0,
        "channel_requests": 0, "video_requests": 0, "enrichment_failures": 0,
    }

    def read(path: str, parameters: dict[str, str | int]) -> dict[str, Any]:
        counter = {
            "/youtube/v3/search": "search_requests",
            "/youtube/v3/channels": "channel_requests",
            "/youtube/v3/videos": "video_requests",
        }[path]
        research_stats[counter] += 1
        try:
            return _read_youtube_json(path, parameters)
        except YouTubeRequestLimitError as exc:
            research_stats["quota_exhausted"] = int(exc.quota_exhausted)
            research_stats["rate_limited"] = int(exc.rate_limited)
            raise

    # Give every query its first page before spending budget on another page.
    pending: list[tuple[str, str | None, set[str]]] = [(query, None, set()) for query in queries]
    stop_search = False
    for page_index in range(pages_per_query):
        next_pages = []
        for query, token, seen_tokens in pending:
            if checkpoint is not None:
                checkpoint()
            if reserve_search_request is not None and not reserve_search_request():
                research_stats["search_budget_exhausted"] = 1
                stop_search = True
                break
            if page_index == 0:
                research_stats["queries_started"] += 1
            parameters: dict[str, str | int] = {
                "part": "snippet", "type": "video", "q": query,
                "publishedAfter": published_after.isoformat().replace("+00:00", "Z"),
                "safeSearch": "strict", "order": "relevance", "maxResults": results_per_page,
                "relevanceLanguage": campaign["relevance_language"], "key": api_key,
            }
            if campaign.get("region_code"):
                parameters["regionCode"] = campaign["region_code"]
            if token is not None:
                parameters["pageToken"] = token
            try:
                search = read("/youtube/v3/search", parameters)
                if not isinstance(search.get("items"), list):
                    raise ValueError("YouTube search returned an unexpected result list")
            except (RuntimeError, ValueError):
                research_stats["search_failures"] += 1
                stop_search = True
                break
            research_stats["search_pages"] += 1
            for item in search["items"][:results_per_page]:
                research_stats["search_results"] += 1
                snippet = item.get("snippet") if isinstance(item, dict) else None
                identity = item.get("id") if isinstance(item, dict) else None
                if not isinstance(snippet, dict) or not isinstance(identity, dict):
                    research_stats["invalid_results"] += 1
                    continue
                channel_id = str(snippet.get("channelId") or "")
                video_id = str(identity.get("videoId") or "")
                if not CHANNEL_ID.fullmatch(channel_id) or not VIDEO_ID.fullmatch(video_id):
                    research_stats["invalid_results"] += 1
                    continue
                if channel_id in discovered:
                    research_stats["duplicate_channels"] += 1
                    continue
                discovered[channel_id] = {
                    "channel_id": channel_id, "video_id": video_id,
                    "display_name": _bounded_text(snippet.get("channelTitle"), 300)
                    or "Unnamed YouTube channel",
                    "latest_content_title": _bounded_text(snippet.get("title"), 500) or None,
                    "latest_content_url": f"https://www.youtube.com/watch?v={video_id}",
                    "latest_content_published_at": _parse_youtube_datetime(
                        snippet.get("publishedAt")
                    ),
                    "discovery_query": query,
                }
            next_token = search.get("nextPageToken")
            if next_token is None or next_token == "":
                research_stats["queries_exhausted"] += 1
            elif (not isinstance(next_token, str) or len(next_token) > 1024
                  or not all(33 <= ord(char) <= 126 for char in next_token)
                  or next_token in seen_tokens):
                research_stats["pagination_errors"] += 1
            elif page_index + 1 == pages_per_query:
                research_stats["queries_page_limited"] += 1
            else:
                seen_tokens.add(next_token)
                next_pages.append((query, next_token, seen_tokens))
        if stop_search or not next_pages:
            break
        pending = next_pages

    channel_ids = list(discovered)
    for start in range(0, len(channel_ids), 50):
        if research_stats["quota_exhausted"] or research_stats["rate_limited"]:
            break
        batch = channel_ids[start : start + 50]
        if checkpoint is not None:
            checkpoint()
        try:
            channels = read(
                "/youtube/v3/channels",
                {
                    "part": "snippet,statistics",
                    "id": ",".join(batch),
                    "maxResults": len(batch),
                    "key": api_key,
                },
            )
            if not isinstance(channels.get("items"), list):
                raise ValueError("YouTube channel metadata returned an unexpected result list")
        except YouTubeRequestLimitError:
            research_stats["enrichment_failures"] += 1
            break
        except (RuntimeError, ValueError):
            research_stats["enrichment_failures"] += 1
            continue
        for item in _youtube_items(channels):
            channel_id = str(item.get("id") or "")
            if channel_id not in batch:
                continue
            _apply_channel(item, discovered[channel_id])

    if not research_stats["quota_exhausted"] and not research_stats["rate_limited"]:
        _enrich_videos(api_key, discovered, request_json=read, research_stats=research_stats,
                       checkpoint=checkpoint)
    normalized = [
        _normalize_researched_prospect(campaign, item, reference) for item in discovered.values()
    ]
    selected = []
    summary = {
        **research_stats,
        "queries_incomplete": len(queries) - research_stats["queries_exhausted"],
        "channels_enriched": sum(bool(item.get("channel_enriched"))
                                 for item in discovered.values()),
        "videos_enriched": sum(bool(item.get("video_enriched")) for item in discovered.values()),
        "reviewed": len(normalized), "selected": 0, "excluded": 0,
        "country_known": 0, "country_matches": 0, "language_known": 0, "language_matches": 0,
        "excluded_country_unknown": 0, "excluded_country_mismatch": 0,
        "excluded_language_unknown": 0, "excluded_language_mismatch": 0,
    }
    for item in normalized:
        geography = item["intelligence"]["geography"]
        for dimension in ("country", "language"):
            summary[f"{dimension}_known"] += int(geography[f"{dimension}_code"] is not None)
            summary[f"{dimension}_matches"] += int(geography[f"{dimension}_match"] == "match")
        if geography["eligible"]:
            selected.append(item)
        else:
            for reason in geography["excluded_reasons"]:
                summary[f"excluded_{reason}"] += 1
    summary["selected"] = len(selected)
    summary["excluded"] = len(normalized) - len(selected)
    if selection_stats is not None:
        selection_stats.clear()
        selection_stats.update(summary)

    def rank(item: dict[str, Any]) -> tuple[int, int]:
        geography = item["intelligence"]["geography"]
        preference_matches = sum(
            geography[f"{dimension}_mode"] == "prefer"
            and geography[f"{dimension}_match"] == "match"
            for dimension in ("country", "language")
        )
        return preference_matches, item["relevance_score"]

    return sorted(selected, key=rank, reverse=True)


def fetch_youtube_prospect(
    api_key: str, campaign: dict[str, Any], prospect: dict[str, Any], *,
    now: datetime | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Refresh one imported channel through official APIs, with no arbitrary fetch."""
    if not api_key.strip():
        raise RuntimeError("YouTube discovery requires a restricted API key")
    if prospect.get("platform") != "youtube":
        raise ValueError("Creator research supports YouTube prospects only")
    if prospect.get("suppressed_at") or prospect.get("status") in {"suppressed", "bounced"}:
        raise ValueError("Suppressed prospects cannot be researched")
    identity = public_youtube_identity(prospect["profile_url"])
    reference = now or datetime.now(UTC)
    if checkpoint is not None:
        checkpoint()
    response = _read_youtube_json("/youtube/v3/channels", {
        "part": "snippet,statistics", **identity, "maxResults": 1, "key": api_key,
    })
    channels = _youtube_items(response, 1)
    if not channels or not CHANNEL_ID.fullmatch(str(channels[0].get("id", ""))):
        raise RuntimeError("Public YouTube channel was not found")
    channel = channels[0]
    if "id" in identity and channel["id"] != identity["id"]:
        raise RuntimeError("YouTube channel identity did not match")
    previous = prospect.get("intelligence") or {}
    previous_channel = previous.get("source_channel_id")
    if previous_channel and previous_channel != channel["id"]:
        raise RuntimeError("Public handle ownership changed; review the creator profile")
    video_id = public_video_id(prospect.get("latest_content_url"))
    previous_sample = previous_channel == channel["id"] and any(
        sample.get("url") == prospect.get("latest_content_url")
        and sample.get("metadata_status") in {"observed_this_run", "previously_observed"}
        for sample in previous.get("recent_videos", []) if isinstance(sample, dict)
    )
    item = {
        "channel_id": channel["id"], "video_id": video_id,
        "display_name": prospect["display_name"],
        "latest_content_title": prospect.get("latest_content_title") if previous_sample else None,
        "latest_content_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
        "latest_content_published_at": prospect.get("latest_content_published_at")
        if previous_sample else None,
        "previous_sample": previous_sample, "direct_refresh": True, "discovery_query": None,
    }
    _apply_channel(channel, item)
    _enrich_videos(api_key, {channel["id"]: item}, checkpoint=checkpoint)
    return _normalize_researched_prospect(campaign, item, reference)


def tracking_url(campaign: dict[str, Any], prospect: dict[str, Any]) -> str:
    parsed = urlparse(campaign["product_url"])
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "utm_source": prospect["platform"],
            "utm_medium": "creator_outreach",
            "utm_campaign": re.sub(r"[^a-z0-9]+", "-", campaign["name"].casefold()).strip("-")[
                :80
            ],
            "utm_content": prospect["tracking_code"],
        }
    )
    return urlunparse(parsed._replace(query=urlencode(query)))


def organic_tracking_url(
    campaign: dict[str, Any],
    *,
    source: str,
    medium: str,
    content: str,
) -> str:
    """Build one stable first-party attribution URL without calling a provider."""
    parsed = urlparse(campaign["product_url"])
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    slug = re.sub(r"[^a-z0-9]+", "-", campaign["name"].casefold()).strip("-")[:80]
    query.update(
        {
            "utm_id": str(campaign["id"]),
            "utm_source": source,
            "utm_medium": medium,
            "utm_campaign": slug or "creator-campaign",
            "utm_source_platform": source,
            "utm_content": content,
        }
    )
    return urlunparse(parsed._replace(query=urlencode(query)))


def build_promotion_kit(campaign: dict[str, Any]) -> dict[str, Any]:
    """Create truthful copy-and-paste promotion assets from reviewed campaign fields."""
    product = campaign["product_name"]
    summary = campaign["product_summary"].rstrip(".")
    audience = campaign["target_audience"].rstrip(".")
    viewer_offer = campaign["viewer_offer"].rstrip(".")
    creator_offer = campaign["creator_offer"].rstrip(".")

    specifications = (
        (
            "youtube_description",
            "youtube",
            "organic_social",
            "YouTube description",
            f"Try {product}: {summary}.",
            (
                f"{product} is {summary}. It is designed for {audience}.\n\n"
                f"For this pilot, {viewer_offer}.\n\n"
                "Test it here: {url}\n\n"
                f"Privacy information: {campaign['privacy_url']}"
            ),
            "Place below the creator's own honest description; disclose any material relationship.",
        ),
        (
            "youtube_community",
            "youtube",
            "organic_social",
            "YouTube community post",
            f"We are testing {product} with the community",
            (
                f"We are testing {product}, {summary}. "
                f"For this pilot, {viewer_offer}. "
                "Take a look and tell us what is useful or unclear: {url}"
            ),
            "Use only in a community that expects product/pilot posts; invite honest feedback.",
        ),
        (
            "discord_community",
            "discord",
            "community",
            "Discord community post",
            f"{product} community pilot",
            (
                f"We are opening a small {product} pilot for {audience}. "
                f"{product} is {summary}. {viewer_offer.capitalize()}.\n\n"
                "Pilot link: {url}"
            ),
            "Post only with server-owner or moderator permission and in the correct channel.",
        ),
        (
            "reddit_community",
            "reddit",
            "organic_social",
            "Reddit/community post",
            f"Looking for honest feedback on a {product} pilot",
            (
                f"I am working on {product}, {summary}, for {audience}. "
                f"For the current pilot, {viewer_offer}.\n\n"
                "I would value direct feedback from people who try it: {url}"
            ),
            (
                "Read the community's self-promotion rules first; do not repost "
                "where promotion is prohibited."
            ),
        ),
        (
            "partner_newsletter",
            "newsletter",
            "referral",
            "Partner newsletter or blog",
            f"A {product} pilot for Minecraft communities",
            (
                f"{product} is {summary} and is designed for {audience}. "
                f"For participating communities, {creator_offer}. "
                f"For viewers, {viewer_offer}. Learn more: {{url}}"
            ),
            (
                "Give the publisher editorial control and require accurate disclosure "
                "of any compensation or benefit."
            ),
        ),
    )

    assets: list[dict[str, str]] = []
    for key, source, medium, channel, title, body, guidance in specifications:
        url = organic_tracking_url(
            campaign,
            source=source,
            medium=medium,
            content=key,
        )
        assets.append(
            {
                "key": key,
                "channel": channel,
                "title": title,
                "body": body.format(url=url),
                "tracking_url": url,
                "guidance": guidance,
            }
        )

    return {
        "campaign_id": campaign["id"],
        "campaign_name": campaign["name"],
        "product_name": product,
        "product_url": campaign["product_url"],
        "privacy_url": campaign["privacy_url"],
        "key_messages": [
            f"{product} is {summary}.",
            f"It is designed for {audience}.",
            f"Viewer pilot: {viewer_offer}.",
            f"Creator/server pilot: {creator_offer}.",
        ],
        "disclosure_reminder": (
            "Publish only where promotion is allowed. Be accurate, invite honest feedback, "
            "and disclose compensation, free benefits, or other material relationships."
        ),
        "assets": assets,
    }


def _contact_footer(campaign: dict[str, Any], prospect: dict[str, Any]) -> str:
    return (
        "\n\nThis is a one-to-one business collaboration note. "
        f"Contact source: {prospect['contact_source_url']}\n"
        f"Privacy information: {campaign['privacy_url']}\n"
        "If you do not want another message, reply ‘do not contact’ and we will suppress "
        "this address immediately."
    )


def compose_initial_email(
    campaign: dict[str, Any], prospect: dict[str, Any], variant: str
) -> tuple[str, str]:
    if variant not in INITIAL_VARIANTS:
        raise ValueError("Unknown initial outreach variant")
    subject = (
        f"{prospect['display_name']} × {campaign['product_name']} — a viewer reward pilot"
        if variant == "viewer_value"
        else f"Minecraft creator pilot for {prospect['display_name']}"
    )
    recent = (
        f" I found your recent video “{prospect['latest_content_title']}” relevant to the pilot."
        if prospect.get("latest_content_title")
        else ""
    )
    product = (
        f"{campaign['product_name']} is {campaign['product_summary'].rstrip('.')}.",
        f"It is designed for {campaign['target_audience'].rstrip('.')}.",
    )
    if variant == "viewer_value":
        middle = (
            f"For a first pilot, {campaign['viewer_offer'].rstrip('.')}. "
            "If you also run a server, site, or community, "
            f"{campaign['creator_offer'].rstrip('.')}."
        )
    else:
        middle = (
            f"We are inviting a small set of creators to test the model before scaling it. "
            f"{campaign['creator_offer'].rstrip('.')}. "
            f"For your audience, {campaign['viewer_offer'].rstrip('.')}."
        )
    body = (
        f"Hi {prospect['display_name']} team,\n\n"
        f"I’m {campaign['sender_name']} from {campaign['product_name']}.{recent}\n\n"
        f"{product[0]} {product[1]}\n\n"
        f"{middle}\n\n"
        "Would you be open to testing it and, if it is genuinely useful, discussing an honest "
        "video, Short, stream segment, or community post? There is no obligation to endorse it.\n\n"
        f"Pilot link: {tracking_url(campaign, prospect)}\n\n"
        f"Thanks,\n{campaign['sender_name']}"
        f"{_contact_footer(campaign, prospect)}"
    )
    return subject[:240], body[:20000]


def compose_paid_offer_email(
    campaign: dict[str, Any], prospect: dict[str, Any]
) -> tuple[str, str]:
    if not campaign["paid_offer_enabled"] or not campaign.get("paid_offer_details"):
        raise ValueError("This campaign has no approved paid-offer description")
    subject = f"Final follow-up: paid {campaign['product_name']} collaboration"
    body = (
        f"Hi {prospect['display_name']} team,\n\n"
        "Thank you for being clear that an unpaid collaboration is not a fit. "
        f"If compensation was the blocker, {campaign['paid_offer_details'].rstrip('.')}.\n\n"
        "Any scope, fee, disclosure, timing, and deliverables would be agreed in writing before "
        "publication. If that is still not a fit, no reply is needed—this is our final outreach "
        "message.\n\n"
        f"Product: {tracking_url(campaign, prospect)}\n\n"
        f"Thanks,\n{campaign['sender_name']}"
        f"{_contact_footer(campaign, prospect)}"
    )
    return subject[:240], body[:20000]


def compose_reviewed_email(
    campaign: dict[str, Any], prospect: dict[str, Any], subject: str, body: str
) -> tuple[str, str]:
    footer = _contact_footer(campaign, prospect)
    # Reserve space for provenance and opt-out even at the maximum body length.
    return subject[:240], f"{body.strip()[:20000 - len(footer)]}{footer}"


def choose_initial_variant(
    prospect_id: UUID,
    variants: list[dict[str, Any]],
    *,
    adaptive_mode: bool,
) -> tuple[str, str]:
    bucket = int(prospect_id.hex[-8:], 16)
    by_name = {item["variant"]: item for item in variants}
    enough_evidence = all(
        by_name.get(name, {}).get("sent", 0) >= 10 for name in INITIAL_VARIANTS
    )
    if adaptive_mode and enough_evidence:
        rates = {
            name: by_name[name].get("positive", 0) / max(1, by_name[name]["sent"])
            for name in INITIAL_VARIANTS
        }
        ordered = sorted(rates, key=rates.get, reverse=True)
        winner, runner_up = ordered
        winner_rate = rates[winner]
        runner_rate = rates[runner_up]
        decisive = winner_rate >= runner_rate + 0.05 and (
            runner_rate == 0 or winner_rate >= runner_rate * 1.5
        )
        if decisive:
            selected = winner if bucket % 10 < 8 else runner_up
            mode = "winner" if selected == winner else "exploration"
            return (
                selected,
                f"Adaptive {mode}: {winner} leads positive replies after "
                "at least 10 sends per variant",
            )
    selected = INITIAL_VARIANTS[bucket % len(INITIAL_VARIANTS)]
    return selected, "Balanced deterministic A/B assignment; evidence threshold not met"


def campaign_suggestions(
    metrics: dict[str, int | float], variants: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    sent = int(metrics.get("emails_sent", 0))
    replies = int(metrics.get("replies", 0))
    positive = int(metrics.get("positive_replies", 0))
    questions = int(metrics.get("questions", 0))
    declined = int(metrics.get("declined_unpaid", 0))
    suppressed = int(metrics.get("suppressed", 0))
    suggestions: list[dict[str, Any]] = []
    if sent < 10:
        suggestions.append(
            {
                "kind": "sample",
                "priority": "observe",
                "message": f"Collect {10 - sent} more approved sends before changing the pitch.",
                "evidence": f"{sent} SMTP-accepted email(s); minimum comparison sample is 10.",
            }
        )
    elif replies / sent < 0.10:
        suggestions.append(
            {
                "kind": "targeting",
                "priority": "review",
                "message": (
                    "Pause scaling and tighten creator relevance or "
                    "first-line personalization."
                ),
                "evidence": (
                    f"Reply rate is {replies / sent:.1%} across {sent} SMTP-accepted emails."
                ),
            }
        )
    if replies and questions / replies >= 0.40:
        suggestions.append(
            {
                "kind": "clarity",
                "priority": "test",
                "message": (
                    "Test a shorter explanation of verified play, portable points, and funding."
                ),
                "evidence": f"{questions} of {replies} replies were questions.",
            }
        )
    if replies and declined / replies >= 0.50:
        suggestions.append(
            {
                "kind": "offer",
                "priority": "review",
                "message": (
                    "Clarify the pilot workload and prepare a concrete paid scope "
                    "for qualified creators."
                ),
                "evidence": f"{declined} of {replies} replies declined the unpaid pilot.",
            }
        )
    if sent >= 10 and suppressed / sent >= 0.10:
        suggestions.append(
            {
                "kind": "compliance",
                "priority": "stop",
                "message": "Stop new outreach and review contact provenance and targeting.",
                "evidence": f"Suppression/bounce rate is {suppressed / sent:.1%}.",
            }
        )
    qualified = [item for item in variants if item.get("sent", 0) >= 10]
    if len(qualified) == len(INITIAL_VARIANTS):
        ranked = sorted(
            qualified,
            key=lambda item: item.get("positive", 0) / max(1, item["sent"]),
            reverse=True,
        )
        best, second = ranked
        best_rate = best.get("positive", 0) / max(1, best["sent"])
        second_rate = second.get("positive", 0) / max(1, second["sent"])
        if best_rate >= second_rate + 0.05 and (
            second_rate == 0 or best_rate >= second_rate * 1.5
        ):
            suggestions.append(
                {
                    "kind": "variant",
                    "priority": "adapted",
                    "message": f"Prefer {best['variant'].replace('_', ' ')} for 80% of new drafts.",
                    "evidence": (
                        f"Positive reply rate {best_rate:.1%} vs {second_rate:.1%}; "
                        "20% exploration remains."
                    ),
                }
            )
    if sent >= 10 and positive == 0:
        suggestions.append(
            {
                "kind": "validation",
                "priority": "review",
                "message": (
                    "Revisit the offer before sending more; no positive replies are recorded."
                ),
                "evidence": f"0 positive replies across {sent} SMTP-accepted emails.",
            }
        )
    return suggestions


def percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return math.floor((numerator / denominator) * 1000) / 10
