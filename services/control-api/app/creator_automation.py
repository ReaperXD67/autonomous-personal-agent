"""Creator scope checks; neither model prose nor mailbox evidence grants authority."""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.application_browser import canonical_hash
from app.career_tracking import bounded_text
from app.creator_intelligence import assess_creator_geography
from app.marketing import campaign_outreach_hash


def automation_campaign_hash(campaign: dict[str, Any]) -> str:
    return canonical_hash(
        {
            "outreach": campaign_outreach_hash(campaign),
            "targeting": {
                key: campaign.get(key)
                for key in (
                    "discovery_queries",
                    "min_subscribers",
                    "max_subscribers",
                    "max_video_age_days",
                    "country_mode",
                    "target_country",
                    "language_mode",
                    "target_language",
                )
            },
        }
    )


def creator_key(prospect: dict[str, Any]) -> str:
    # YouTube discovery uses canonical channel IDs; the profile URL remains a fallback
    # for operator-imported creators. Never collapse unrelated display names.
    return f"{prospect['platform']}:{prospect['external_id']}"


def creator_eligibility_reason(
    campaign: dict[str, Any], prospect: dict[str, Any], now: datetime | None = None
) -> str | None:
    now = now or datetime.now(UTC)
    intelligence = prospect.get("intelligence") or {}
    if prospect.get("platform") != "youtube" or "Minecraft" not in intelligence.get("topics", []):
        return "Automatic outreach requires observed Minecraft content evidence on YouTube"
    audience = prospect.get("audience_size")
    if (
        audience is None
        or not campaign["min_subscribers"] <= audience <= campaign["max_subscribers"]
    ):
        return "Creator audience evidence is outside the campaign scope or unknown"
    published = prospect.get("latest_content_published_at")
    if (
        published is None
        or published > now
        or published < now - timedelta(days=campaign["max_video_age_days"])
    ):
        return "Refresh creator research: recent published content is required"
    if not assess_creator_geography(campaign, intelligence.get("geography", {}))["eligible"]:
        return "Creator country or language evidence is outside the selected scope"
    return None


def run_block_reason(
    run: dict[str, Any], campaign: dict[str, Any], now: datetime | None = None
) -> str | None:
    now = now or datetime.now(UTC)
    if run["state"] != "running":
        return "Creator automation is paused or blocked"
    if run["expires_at"] <= now:
        return "Creator automation authorization expired"
    if campaign.get("outreach_mode") != "paid":
        return "Automatic introductions require a paid-promotion campaign"
    if automation_campaign_hash(campaign) != run["campaign_hash"]:
        return "Campaign or owner handoff details changed; authorize a new run"
    return None


def pending_reply_reason(connection: Any, campaign_id: Any) -> str | None:
    if connection.execute(
        "SELECT 1 FROM creator_reply_messages WHERE campaign_id = %s AND needs_review LIMIT 1",
        (campaign_id,),
    ).fetchone():
        return "Review new creator replies before automatic outreach continues"
    return None


def validate_creator_automation(connection: Any, action: dict[str, Any]) -> str | None:
    marketing = action["private_context"].get("marketing")
    if isinstance(marketing, dict):
        reason = pending_reply_reason(connection, marketing.get("campaign_id"))
        if reason:
            return reason
    scope = action["private_context"].get("creator_automation")
    if scope is None:
        return None
    if not isinstance(scope, dict) or not scope.get("run_id"):
        return "Creator automation scope is invalid"
    reservation = connection.execute(
        "SELECT * FROM creator_automation_actions WHERE action_id = %s",
        (action["id"],),
    ).fetchone()
    if (
        not reservation
        or str(reservation["run_id"]) != scope["run_id"]
        or reservation["context_hash"] != action["context_hash"]
    ):
        return "Creator automation exact-action reservation is absent or changed"
    run = connection.execute(
        "SELECT * FROM creator_automation_runs WHERE id = %s FOR SHARE",
        (scope["run_id"],),
    ).fetchone()
    campaign = connection.execute(
        "SELECT * FROM marketing_campaigns WHERE id = %s",
        (reservation["campaign_id"],),
    ).fetchone()
    if not run or not campaign:
        return "Creator automation scope no longer exists"
    now = connection.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
    reason = run_block_reason(run, campaign, now) or pending_reply_reason(
        connection,
        reservation["campaign_id"],
    )
    if reason:
        return reason
    prospect = connection.execute(
        "SELECT * FROM marketing_prospects WHERE id=%s", (reservation["prospect_id"],)
    ).fetchone()
    if not prospect:
        return "Creator no longer exists"
    if reservation["stage"] == "initial":
        reason = creator_eligibility_reason(campaign, prospect, now)
        if reason:
            return reason
    if reservation["stage"] == "handoff" and not run["auto_handoff"]:
        return "Automatic owner handoff was not authorized"
    if run["monitor_gmail"]:
        fresh = connection.execute(
            "SELECT 1 FROM creator_gmail_sync_state WHERE campaign_id = %s "
            "AND last_complete_at > clock_timestamp() - interval '30 minutes'",
            (run["campaign_id"],),
        ).fetchone()
        if not fresh:
            return "Creator mailbox monitoring needs a recent completed sync"
    return None


def _authored_reply_text(snippet: Any) -> str:
    """Discard recognizable quoted history, including flattened Gmail snippets."""
    text = html.unescape(bounded_text(snippet, 600)).casefold().replace("’", "'")
    text = text.replace("‘", "'").replace("“", '"').replace("”", '"')
    quoted_tail = re.search(
        r"(?:\bon\s+[^\n]{1,220}?\bwrote\s*:|"
        r"-{2,}\s*(?:original|forwarded) message\s*-{2,}|"
        r"\bbegin forwarded message\s*:|(?:^|\s)>\s|"
        r"\bfrom:\s*[^\n]{1,150}?\bsent:\s*)",
        text,
    )
    if quoted_tail:
        text = text[: quoted_tail.start()]
    # Our footer may survive without quotation markers when Gmail flattens history.
    text = re.sub(
        r"if you do not want another message,\s*reply\s*['\"]?do not contact['\"]?"
        r"(?:\s+and we will suppress this address immediately\.?)?",
        "",
        text,
    )
    return text.strip()


def _direct_opt_out(text: str) -> bool:
    # Mere mentions of opt-out instructions are evidence for review, not an objection.
    for clause in re.split(r"[.!?;]|\b(?:but|and|so)\b", text):
        if re.search(
            r"\b(?:not|never|don't|do not)\s+(?:saying|say|asking|ask|mean|meaning|"
            r"requesting|request|want to)\b|"
            r"\b(?:reply|say|says|said|wrote|write|type|instruction|instructions)\b",
            clause,
        ):
            continue
        if re.search(
            r"(?:^|,)\s*['\"]?\s*(?:please\s+|kindly\s+)?(?:"
            r"unsubscribe\b|remove me\b|do not contact\b|don't contact\b|"
            r"stop emailing\b|stop contacting\b|no more emails\b|"
            r"(?:(?:i'm|i am|we're|we are)\s+)?not interested\b)",
            clause,
        ):
            return True
    return False


def classify_creator_reply(message: dict[str, Any]) -> str:
    """A hint for operator review; only conservative opt-outs take immediate effect."""
    # Subject may quote our own pitch, so positive signals use the inbound snippet only.
    text = _authored_reply_text(message.get("snippet", ""))
    if _direct_opt_out(text):
        return "do_not_contact"
    if re.search(
        r"\b(?:interested|sounds good|let.s discuss|send (?:me |us )?"
        r"(?:the )?(?:details|rates)|happy to collaborate)\b",
        text,
    ):
        return "interested"
    if "?" in text or re.search(r"\b(?:what is|how much|budget|rates|pricing)\b", text):
        return "question"
    return "needs_review"


def correlate_creator_reply(
    message: dict[str, Any], sent: list[dict[str, Any]]
) -> tuple[Any | None, str]:
    def subject(value: str) -> str:
        return re.sub(r"^(?:(?:re|fw|fwd):\s*)+", "", value.strip(), flags=re.I).casefold()

    matches = {
        str(row["prospect_id"]): row["prospect_id"]
        for row in sent
        if row["recipient"].casefold() == message["sender"].casefold()
        and message["received_at"] >= row["sent_at"]
        and subject(row["subject"]) == subject(message["subject"])
    }
    if len(matches) == 1:
        return next(iter(matches.values())), "Exact contacted address and outreach subject"
    return None, "No unique sent-message match; review the creator and reply"
