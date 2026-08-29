from __future__ import annotations

import html
import json
import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

YOUTUBE_API_HOST = "www.googleapis.com"
MAX_YOUTUBE_BYTES = 2 * 1024 * 1024
USER_AGENT = (
    "HermesCreatorScout/0.1 "
    "(+https://github.com/ReaperXD67/autonomous-personal-agent)"
)
INITIAL_VARIANTS = ("viewer_value", "creator_pilot")


class _YouTubeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname != YOUTUBE_API_HOST:
            raise ValueError("YouTube API redirected outside the reviewed host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read_youtube_json(path: str, parameters: dict[str, str | int]) -> dict[str, Any]:
    if not path.startswith("/youtube/v3/"):
        raise ValueError("YouTube API path is outside the reviewed prefix")
    url = f"https://{YOUTUBE_API_HOST}{path}?{urlencode(parameters)}"
    request = Request(  # noqa: S310 - exact HTTPS host and API prefix are fixed above
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with build_opener(_YouTubeRedirectHandler()).open(request, timeout=20) as response:
            final = urlparse(response.geturl())
            if final.scheme != "https" or final.hostname != YOUTUBE_API_HOST:
                raise ValueError("YouTube API resolved outside the reviewed host")
            raw = response.read(MAX_YOUTUBE_BYTES + 1)
    except HTTPError as exc:
        raise RuntimeError(f"YouTube API request failed with HTTP {exc.code}") from None
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("YouTube API request failed") from exc
    if len(raw) > MAX_YOUTUBE_BYTES:
        raise ValueError("YouTube API response exceeded the size limit")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("YouTube API returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("YouTube API returned an unexpected response")
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
    now: datetime | None = None,
) -> tuple[int, list[str]]:
    reference = now or datetime.now(UTC)
    score = 45
    reasons = ["matched a configured Minecraft discovery query"]
    if audience_size is None:
        reasons.append("subscriber count is hidden")
    elif minimum_audience <= audience_size <= maximum_audience:
        score += 30
        reasons.append("audience is inside the configured creator range")
    elif audience_size < minimum_audience:
        score += 10
        reasons.append("audience is below the target range but may suit a small pilot")
    else:
        score += 8
        reasons.append("audience is above the target range")

    if content_published_at is not None:
        age_days = max(0, (reference - content_published_at).days)
        if age_days <= 30:
            score += 20
            reasons.append("matching content was published within 30 days")
        elif age_days <= 90:
            score += 12
            reasons.append("matching content was published within 90 days")
        else:
            score += 5
            reasons.append("matching content is older than 90 days")
    if audience_size is not None:
        score += 5
    return min(100, score), reasons


def fetch_youtube_creators(
    api_key: str,
    campaign: dict[str, Any],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    if not api_key.strip():
        raise RuntimeError("YouTube discovery requires a restricted API key")
    reference = now or datetime.now(UTC)
    published_after = reference - timedelta(days=campaign["max_video_age_days"])
    discovered: dict[str, dict[str, Any]] = {}

    for query in campaign["discovery_queries"]:
        parameters: dict[str, str | int] = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "publishedAfter": published_after.isoformat().replace("+00:00", "Z"),
            "safeSearch": "strict",
            "order": "relevance",
            "maxResults": campaign["results_per_query"],
            "relevanceLanguage": campaign["relevance_language"],
            "key": api_key,
        }
        if campaign.get("region_code"):
            parameters["regionCode"] = campaign["region_code"]
        search = _read_youtube_json("/youtube/v3/search", parameters)
        for item in search.get("items", [])[: campaign["results_per_query"]]:
            if not isinstance(item, dict):
                continue
            snippet = item.get("snippet")
            identity = item.get("id")
            if not isinstance(snippet, dict) or not isinstance(identity, dict):
                continue
            channel_id = str(snippet.get("channelId") or "")
            video_id = str(identity.get("videoId") or "")
            if not channel_id or not video_id or channel_id in discovered:
                continue
            discovered[channel_id] = {
                "channel_id": channel_id,
                "display_name": _bounded_text(snippet.get("channelTitle"), 300)
                or "Unnamed YouTube channel",
                "latest_content_title": _bounded_text(snippet.get("title"), 500) or None,
                "latest_content_url": f"https://www.youtube.com/watch?v={video_id}",
                "latest_content_published_at": _parse_youtube_datetime(
                    snippet.get("publishedAt")
                ),
                "discovery_query": query,
            }

    channel_ids = list(discovered)
    for start in range(0, len(channel_ids), 50):
        batch = channel_ids[start : start + 50]
        channels = _read_youtube_json(
            "/youtube/v3/channels",
            {
                "part": "snippet,statistics",
                "id": ",".join(batch),
                "maxResults": len(batch),
                "key": api_key,
            },
        )
        for item in channels.get("items", []):
            if not isinstance(item, dict):
                continue
            channel_id = str(item.get("id") or "")
            if channel_id not in discovered:
                continue
            snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
            statistics = (
                item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
            )
            hidden = bool(statistics.get("hiddenSubscriberCount"))
            try:
                audience_size = None if hidden else int(statistics.get("subscriberCount"))
            except (TypeError, ValueError):
                audience_size = None
            prospect = discovered[channel_id]
            prospect["display_name"] = (
                _bounded_text(snippet.get("title"), 300) or prospect["display_name"]
            )
            prospect["audience_size"] = audience_size

    normalized: list[dict[str, Any]] = []
    for channel_id, item in discovered.items():
        score, reasons = score_creator(
            audience_size=item.get("audience_size"),
            content_published_at=item["latest_content_published_at"],
            minimum_audience=campaign["min_subscribers"],
            maximum_audience=campaign["max_subscribers"],
            now=reference,
        )
        normalized.append(
            {
                "platform": "youtube",
                "external_id": channel_id,
                "display_name": item["display_name"],
                "profile_url": f"https://www.youtube.com/channel/{channel_id}",
                "audience_size": item.get("audience_size"),
                "latest_content_title": item["latest_content_title"],
                "latest_content_url": item["latest_content_url"],
                "latest_content_published_at": item["latest_content_published_at"],
                "discovery_query": item["discovery_query"],
                "relevance_score": score,
                "relevance_reasons": reasons,
            }
        )
    return sorted(normalized, key=lambda item: item["relevance_score"], reverse=True)


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


def compose_question_reply(
    campaign: dict[str, Any], prospect: dict[str, Any], subject: str, body: str
) -> tuple[str, str]:
    return subject[:240], f"{body.strip()}{_contact_footer(campaign, prospect)}"[:20000]


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
                "evidence": f"{sent} delivered email(s); minimum comparison sample is 10.",
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
                "evidence": f"Reply rate is {replies / sent:.1%} across {sent} delivered emails.",
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
                "evidence": f"0 positive replies across {sent} delivered emails.",
            }
        )
    return suggestions


def percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return math.floor((numerator / denominator) * 1000) / 10
