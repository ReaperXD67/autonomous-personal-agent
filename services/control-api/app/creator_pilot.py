"""Bounded API research and explainable pilot ranking; never contact authority."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.creator_intelligence import (
    EMAIL,
    content_topics,
    declared_language,
    plain_text,
    public_contact_candidates,
)
from app.marketing import (
    _parse_youtube_datetime,
    _read_youtube_json,
    _youtube_items,
)

MAX_CREATORS = 10
MAX_UPLOADS = 3
DAILY_CREATORS = 30
KIND = "marketing.creator_pilot"
TARGET_FIELDS = (
    "id", "min_subscribers", "max_subscribers", "max_video_age_days",
    "country_mode", "target_country", "language_mode", "target_language",
)


def campaign_snapshot(campaign):
    return {key: str(campaign[key]) if key == "id" else campaign.get(key)
            for key in TARGET_FIELDS}


def recent_uploads(api_key, channel, *, now, checkpoint):
    """Inspect only the channel's first three upload entries and verify video identity."""
    details = channel.get("contentDetails") or {}
    playlists = details.get("relatedPlaylists") or {}
    playlist_id = playlists.get("uploads")
    result = {"checked_at": now.isoformat(), "status": "unavailable", "videos": []}
    if not isinstance(playlist_id, str) or not re.fullmatch(r"[\w-]{10,100}", playlist_id):
        return result, []
    checkpoint()
    payload = _read_youtube_json("/youtube/v3/playlistItems", {
        "part": "contentDetails", "playlistId": playlist_id,
        "maxResults": MAX_UPLOADS, "key": api_key,
    })
    if not isinstance(payload.get("items"), list):
        raise ValueError("YouTube uploads returned an unexpected result list")
    ids = []
    for item in _youtube_items(payload, MAX_UPLOADS):
        video_id = (item.get("contentDetails") or {}).get("videoId")
        if (isinstance(video_id, str) and re.fullmatch(r"[\w-]{11}", video_id)
                and video_id not in ids):
            ids.append(video_id)
    result["status"] = "observed_this_run"
    if not ids:
        return result, []
    checkpoint()
    payload = _read_youtube_json("/youtube/v3/videos", {
        "part": "snippet,status", "id": ",".join(ids), "key": api_key,
    })
    if not isinstance(payload.get("items"), list):
        raise ValueError("YouTube recent videos returned an unexpected result list")
    contacts = []
    seen = set()
    for item in _youtube_items(payload, MAX_UPLOADS):
        snippet = item.get("snippet") or {}
        video_id = item.get("id")
        published = _parse_youtube_datetime(snippet.get("publishedAt"))
        if (video_id not in ids or video_id in seen
                or snippet.get("channelId") != channel["id"]
                or (item.get("status") or {}).get("privacyStatus") != "public"
                or snippet.get("liveBroadcastContent") == "upcoming"
                or published is None or published > now):
            continue
        seen.add(video_id)
        url = f"https://www.youtube.com/watch?v={video_id}"
        language, language_source = None, None
        for field in ("defaultAudioLanguage", "defaultLanguage"):
            language = declared_language(snippet.get(field))
            if language:
                language_source = field
                break
        result["videos"].append({
            "title": plain_text(snippet.get("title"), 500),
            "url": url, "published_at": published.isoformat(),
            "topics": content_topics(plain_text(snippet.get("title"), 500) + " "
                                     + plain_text(snippet.get("description"), 6000)),
            "language": language, "language_source": language_source,
        })
        contacts.extend(public_contact_candidates(
            [(snippet.get("description", ""), url)], observed_at=now,
        ))
    result["videos"].sort(key=lambda item: item["published_at"], reverse=True)
    return result, contacts


def safe_excerpt(value):
    # Redact before truncation so a short report cannot reveal half an address.
    return plain_text(re.sub(r"\S*@\S*", "[public business email]",
                            EMAIL.sub("[public business email]", str(value or ""))), 220)


def rank_prospect(campaign, prospect, *, now=None, error=False):
    now = now or datetime.now(UTC)
    intelligence = prospect.get("intelligence") or {}
    activity = intelligence.get("activity") or {}
    videos = activity.get("videos") or []
    latest = videos[0] if videos else {}
    dated_matches = [
        video for video in videos if "Minecraft" in video.get("topics", [])
    ]
    # The saved matching sample remains useful even if it is outside the first three.
    if intelligence.get("enrichment_status") == "complete":
        dated_matches.extend(
            video for video in intelligence.get("recent_videos", [])
            if video.get("metadata_status") == "observed_this_run"
            and "Minecraft" in video.get("topics", [])
        )
    dates = [
        date for item in dated_matches
        if (date := _parse_youtube_datetime(item.get("published_at"))) is not None
        and date <= now
    ]
    matching_date = max(dates) if dates else None
    audience = prospect.get("audience_size")
    in_range = (isinstance(audience, int)
                and campaign["min_subscribers"] <= audience <= campaign["max_subscribers"])
    age_limit = min(90, campaign["max_video_age_days"])
    recent = matching_date is not None and (now - matching_date).days <= age_limit
    candidates = [
        candidate for candidate in intelligence.get("contact_candidates", [])
        if candidate.get("observed_at") == intelligence.get("researched_at")
        and candidate.get("email") and candidate.get("source_url")
    ]
    exact_contact = any(
        candidate["email"].casefold() == str(prospect.get("contact_email") or "").casefold()
        and candidate["source_url"] == prospect.get("contact_source_url")
        for candidate in candidates
    )
    authorized = bool(prospect.get("contact_authorized_at") and exact_contact
                      and prospect.get("contact_basis_note"))
    reasons, gaps = [], []
    score = 0
    topics = set(intelligence.get("topics") or [])
    if "Minecraft" in topics or dated_matches:
        score += 25
        reasons.append("Public metadata explicitly mentions Minecraft.")
    else:
        gaps.append("No Minecraft content evidence in the inspected metadata.")
    if any(topic in topics for topic in ("Servers", "Multiplayer / SMP")):
        score += 15
        reasons.append("Server or multiplayer topics fit a server-exploration proposal.")
    if in_range:
        score += 20
        reasons.append("Public subscriber count is inside the campaign range.")
    else:
        gaps.append("Subscriber count is unknown or outside the campaign range.")
    if recent:
        score += 25
        reasons.append(f"Observed Minecraft publication is within {age_limit} days.")
    else:
        gaps.append(f"No observed Minecraft publication within {age_limit} days.")
    if activity.get("status") != "observed_this_run":
        gaps.append("Latest public upload activity could not be checked.")
    if candidates:
        score += 15
        reasons.append("Creator descriptions publish explicit business contact context.")
    else:
        gaps.append("No current explicit public business email evidence found.")
    if not authorized:
        gaps.append("Review the exact business contact and grant owner authorization.")
    geography = intelligence.get("geography") or {}
    if not geography.get("eligible", True):
        gaps.append("Published declarations do not satisfy strict campaign targeting.")
    if error:
        gaps.append("Fresh API research failed; saved evidence was not promoted to a shortlist.")
    eligible = (
        not error and recent and in_range and bool(candidates)
        and activity.get("status") == "observed_this_run"
        and geography.get("eligible", True)
        and prospect.get("status") in {"discovered", "qualified"}
        and not prospect.get("suppressed_at")
    )
    language_video = next((video for video in videos if video.get("language")), {})
    return {
        "prospect_id": str(prospect["id"]), "display_name": prospect["display_name"],
        "score": score, "status": "selected" if eligible and authorized else
        "needs_review" if eligible else "excluded",
        "reasons": reasons, "gaps": gaps, "subscriber_count": audience,
        "last_published_at": latest.get("published_at"),
        "latest_activity_url": latest.get("url"),
        "last_minecraft_published_at": matching_date.isoformat() if matching_date else None,
        "public_business_contact_count": len(candidates), "contact_authorized": authorized,
        "contact_evidence": [
            {"source_url": candidate["source_url"],
             "excerpt": safe_excerpt(candidate.get("evidence"))}
            for candidate in candidates[:5]
        ],
        "observed_language": language_video.get("language"),
        "language_source": language_video.get("language_source"),
    }


def shortlist_order(row: dict[str, Any]):
    return ({"selected": 0, "needs_review": 1, "excluded": 2}[row["status"]],
            -row["score"], row["prospect_id"])
