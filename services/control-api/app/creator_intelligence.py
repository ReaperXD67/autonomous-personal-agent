"""Bounded, deterministic research from public YouTube metadata, never authority."""

from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}\Z")
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
EMAIL = re.compile(
    r"(?<![\w.+-])[A-Za-z0-9][A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{0,63}"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)
BUSINESS_CONTEXT = re.compile(
    r"\b(?:business(?:\s+(?:inquir\w*|contact|email|mail))?|collab(?:oration)?s?"
    r"|sponsor(?:ship|ships)?|commercial|partnerships?|wspolprac\w*"
    r"|biznesow\w*|reklam\w*)\b"
)
NEGATIVE_CONTEXT = re.compile(
    r"\b(?:no|not|never|don't|do not|cannot|can't|unavailable|declin\w*|closed"
    r"|nie|bez|brak|odmaw\w*)\b|\bnot interested\b"
    r"|\b(?:niedostepn\w*|support|fan\s*mail|personal|private|pomoc|technicz\w*)\b"
)
TOPIC_PATTERNS = (
    ("Minecraft", r"\bminecraft\b"),
    ("Servers", r"\b(?:servers?|serwer\w*)\b"),
    ("Multiplayer / SMP", r"\b(?:smp|multiplayer|multi|lifesteal|anarch\w*)\b"),
    ("Survival", r"\b(?:survival|hardcore|przetrwan\w*)\b"),
    ("Tutorials", r"\b(?:tutorials?|poradnik\w*|how to|jak grac)\b"),
    ("Community", r"\b(?:community|spolecznosc\w*|widz\w*)\b"),
    ("Rewards", r"\b(?:rewards?|nagrod\w*|points|punkty)\b"),
)


def plain_text(value: Any, limit: int = 600) -> str:
    if not isinstance(value, str):
        return ""
    value = html.unescape(value[:12000])
    value = re.sub(r"<[^>]{0,500}>", " ", value)
    value = "".join(
        " " if char.isspace() else char for char in value
        if char.isspace() or not unicodedata.category(char).startswith("C")
    )
    return " ".join(value.split())[:limit]


def _fold(value: str) -> str:
    value = value.casefold().replace("ł", "l")
    return "".join(
        char for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def public_youtube_identity(url: str) -> dict[str, str]:
    """Parse identity only; never fetch a caller-controlled URL."""
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc not in {"www.youtube.com", "youtube.com"}
        or parsed.query or parsed.fragment or parsed.params
    ):
        raise ValueError("Research requires a public YouTube channel or handle URL")
    path = unquote(parsed.path).rstrip("/")
    if path.startswith("/channel/") and CHANNEL_ID.fullmatch(path[9:]):
        return {"id": path[9:]}
    if path.startswith("/@") and re.fullmatch(r"[\w.-]{3,30}", path[2:]):
        return {"forHandle": path[1:]}
    raise ValueError("Research requires a public YouTube channel or handle URL")


def public_video_id(url: Any) -> str | None:
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc not in {"www.youtube.com", "youtube.com"}
        or parsed.path != "/watch" or parsed.fragment or parsed.params
    ):
        return None
    query = parse_qs(parsed.query)
    values = query.get("v", [])
    if set(query) == {"v"} and len(values) == 1 and VIDEO_ID.fullmatch(values[0]):
        return values[0]
    return None


def public_contact_candidates(
    descriptions: list[tuple[str, str]], *, observed_at: datetime
) -> list[dict[str, str]]:
    """Emails need nearby explicit commercial context, never inferred identity/consent."""
    candidates: dict[str, dict[str, str]] = {}
    for description, source_url in descriptions[:2]:
        try:
            public_youtube_identity(source_url)
        except ValueError:
            if public_video_id(source_url) is None:
                continue
        if not isinstance(description, str):
            continue
        # Preserve line boundaries while locating context; summaries do not retain raw text.
        text = html.unescape(description[:12000])
        for match in EMAIL.finditer(text):
            address = match.group().rstrip(".")
            if len(address) > 254 or ".." in address or address.startswith("."):
                continue
            line_start = max(text.rfind("\n", 0, match.start()),
                             text.rfind(";", 0, match.start())) + 1
            line_end = text.find("\n", match.end())
            line_end = len(text) if line_end < 0 else line_end
            context = text[max(line_start, match.start() - 160):min(line_end, match.end() + 80)]
            # A label may occupy the immediately preceding line, but not another email.
            if not BUSINESS_CONTEXT.search(_fold(context)):
                previous = text[max(0, line_start - 120):line_start].strip()
                previous = previous.rsplit("\n", 1)[-1]
                if "@" not in previous:
                    context = previous + " " + context
            folded = _fold(context)
            if not BUSINESS_CONTEXT.search(folded) or NEGATIVE_CONTEXT.search(folded):
                continue
            key = address.casefold()
            if key not in candidates:
                candidates[key] = {
                    "email": address,
                    "source_url": source_url,
                    "evidence": plain_text(context, 320),
                    "observed_at": observed_at.isoformat(),
                    "status": "unreviewed",
                }
            if len(candidates) == 5:
                return list(candidates.values())
    return list(candidates.values())


def content_topics(content: str) -> list[str]:
    folded = _fold(content[:24000])
    return [name for name, pattern in TOPIC_PATTERNS if re.search(pattern, folded)]


def fit_breakdown(
    *, content: str, audience_size: int | None, published_at: datetime | None,
    minimum_audience: int, maximum_audience: int, now: datetime,
) -> list[dict[str, Any]]:
    topics = content_topics(content)
    content_points = (25 if "Minecraft" in topics else 0)
    if "Minecraft" in topics:
        content_points += 10 if "Servers" in topics else 0
        content_points += 10 if any(
            topic in topics for topic in ("Multiplayer / SMP", "Tutorials", "Rewards")
        ) else 0
    content_evidence = (
        "Published metadata mentions: " + ", ".join(topics)
        if topics else "No target content keywords found in the inspected metadata"
    )
    audience_points = 0
    audience_evidence = "Subscriber count is unavailable or hidden"
    if audience_size is not None:
        if minimum_audience <= audience_size <= maximum_audience:
            audience_points = 30
            audience_evidence = "audience is inside the configured creator range"
        elif audience_size < minimum_audience:
            audience_points = 10
            audience_evidence = "audience is below the configured creator range"
        else:
            audience_points = 8
            audience_evidence = "audience is above the configured creator range"
    recency_points = 0
    recency_evidence = "Matching video publication date is unavailable"
    if published_at is not None and published_at <= now:
        age_days = (now - published_at).days
        if age_days <= 30:
            recency_points, recency_evidence = 20, "matching content was published within 30 days"
        elif age_days <= 90:
            recency_points, recency_evidence = 12, "matching content was published within 90 days"
        else:
            recency_points, recency_evidence = 5, "matching content is older than 90 days"
    elif published_at is not None:
        recency_evidence = "Matching video has a future date; activity is not confirmed"
    return [
        {"criterion": "Content relevance", "points": content_points, "max_points": 45,
         "evidence": content_evidence},
        {"criterion": "Audience range", "points": audience_points, "max_points": 30,
         "evidence": audience_evidence},
        {"criterion": "Observed publication", "points": recency_points, "max_points": 20,
         "evidence": recency_evidence},
        {"criterion": "Audience evidence", "points": 5 if audience_size is not None else 0,
         "max_points": 5, "evidence": "Public subscriber count available" if audience_size
         is not None else "No public subscriber count available"},
    ]


def build_creator_intelligence(
    campaign: dict[str, Any], prospect: dict[str, Any], *, now: datetime,
) -> dict[str, Any]:
    channel_description = prospect.get("channel_description", "")
    video_description = prospect.get("video_description", "")
    content = " ".join((
        plain_text(prospect.get("latest_content_title"), 500),
        plain_text(channel_description, 6000), plain_text(video_description, 6000),
    ))
    topics = content_topics(content)
    breakdown = fit_breakdown(
        content=content, audience_size=prospect.get("audience_size"),
        published_at=prospect.get("latest_content_published_at"),
        minimum_audience=campaign["min_subscribers"],
        maximum_audience=campaign["max_subscribers"], now=now,
    )
    descriptions = [(channel_description, prospect["profile_url"])]
    if prospect.get("latest_content_url"):
        descriptions.append((video_description, prospect["latest_content_url"]))
    candidates = public_contact_candidates(descriptions, observed_at=now)
    gaps = ["Audience location, demographics, and willingness to collaborate are unverified."]
    if not candidates:
        gaps.append("No explicit public business email found in the inspected descriptions.")
    else:
        gaps.append("Public email candidates require source review and contact authorization.")
    if prospect.get("audience_size") is None:
        gaps.append("Subscriber count is unavailable or hidden.")
    if not prospect.get("latest_content_published_at"):
        gaps.append("No dated matching video was verified; current activity is unknown.")
    if not prospect.get("channel_enriched"):
        gaps.append("Channel details could not be enriched during this run.")
    if not prospect.get("video_enriched"):
        gaps.append("Full matching-video description and statistics are unavailable.")
        if prospect.get("previous_sample") and not prospect.get("video_identity_mismatch"):
            gaps.append("The saved video reference comes from prior research and was not "
                        "reverified during this run; a later refresh can retry it.")
        elif prospect.get("direct_refresh") and prospect.get("latest_content_url"):
            gaps.append("The saved video URL is unverified and retained for a later retry.")
    if prospect.get("video_identity_mismatch"):
        gaps.append("The supplied video belongs to another channel and was excluded.")
    gaps.append("A matching video is a sample, not proof of the channel's latest upload or reach.")
    recent_videos = []
    if prospect.get("latest_content_url"):
        published = prospect.get("latest_content_published_at")
        recent_videos.append({
            "title": prospect.get("latest_content_title"),
            "url": prospect["latest_content_url"],
            "published_at": published.isoformat() if published else None,
            "view_count": prospect.get("view_count"),
            "like_count": prospect.get("like_count"),
            "comment_count": prospect.get("comment_count"),
            "metadata_status": "observed_this_run" if prospect.get("video_enriched") else
            "previously_observed" if prospect.get("previous_sample") else
            "unverified_reference" if prospect.get("direct_refresh") else "search_result_only",
        })
    product = plain_text(campaign.get("product_name"), 160)
    ideas = []
    if "Minecraft" in topics:
        ideas.append({
            "title": "Creator-led pilot diary",
            "concept": f"Invite the creator to test {product} and show setup, one session, "
                       "and an honest verdict after verifying the product's current features.",
            "why_fit": "Published metadata explicitly mentions Minecraft.",
        })
        if "Servers" in topics or "Multiplayer / SMP" in topics:
            ideas.append({
                "title": "Community server experiment",
                "concept": "Propose one opt-in session with the creator's community; agree on "
                           "the rules and measure participation before discussing expansion.",
                "why_fit": "Observed server or multiplayer topics provide a pilot context.",
            })
            product_summary = _fold(plain_text(campaign.get("product_summary"), 1200))
            portable_rewards = re.search(
                r"\b(?:portable|cross[ -]server|przenosn\w*|miedzy serwerami)\b",
                product_summary,
            ) and re.search(r"\b(?:points|rewards?|punkty|nagrod\w*)\b", product_summary)
            if portable_rewards:
                ideas.append({
                    "title": "One player, two worlds",
                    "concept": f"Propose a {product} progress diary across two consenting, "
                               "participating servers, showing only the reward trail actually "
                               "observed. First verify both servers are eligible and confirm "
                               "the applicable reward rules; promise no unconfigured bonus.",
                    "why_fit": "The campaign describes portable rewards or points, and the "
                               "creator's public metadata mentions servers or multiplayer.",
                })
        if "Tutorials" in topics:
            ideas.append({
                "title": "From setup to first session",
                "concept": "Offer a short walkthrough with explicit prerequisites and limitations; "
                           "let the creator decide whether a tutorial would help their viewers.",
                "why_fit": "Tutorial language appears in the inspected content metadata.",
            })
    else:
        gaps.append("Minecraft relevance needs manual review before proposing a campaign.")
    topic_hook = ", ".join(topics[:3])
    hook = (
        f"Your public content mentions {topic_hook}. Would a small, optional {product} "
        "pilot be relevant to a future video?"
        if "Minecraft" in topics else
        "Review this creator's content fit before drafting a personalized introduction."
    )
    complete = bool(prospect.get("channel_enriched") and prospect.get("video_enriched"))
    confidence = "low"
    if "Minecraft" in topics and prospect.get("channel_enriched"):
        confidence = "high" if complete and prospect.get("audience_size") is not None else "medium"
    return {
        "schema_version": 1, "researched_at": now.isoformat(),
        "source_channel_id": prospect.get("channel_id"),
        "channel_summary": plain_text(channel_description, 500), "topics": topics,
        "fit_breakdown": breakdown, "contact_candidates": candidates,
        "recent_videos": recent_videos, "collaboration_ideas": ideas,
        "personalized_hook": hook, "confidence": confidence, "gaps": gaps,
        "enrichment_status": "complete" if complete else "partial",
    }
