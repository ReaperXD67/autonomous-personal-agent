"""Bounded creator-copy learning from reviewed evidence, never commercial authority."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from app.creator_reply_text import authored_reply_text

FEEDBACK_TAGS = (
    "too_generic",
    "unclear_offer",
    "unclear_revenue_share",
    "prefers_fixed_fee",
    "weak_content_fit",
    "unclear_attribution",
    "too_long",
    "unclear_next_step",
)
PAID_VARIANTS = ("content_first", "terms_first", "concise")
MIN_REVIEWED_CREATORS = 3
MIN_SENT_PER_VARIANT = 10

_GUIDANCE = {
    "too_generic": ("content_first", "Lead with one relevant, cited Minecraft video or topic."),
    "unclear_offer": ("terms_first", "State the collaboration format and what remains to agree."),
    "unclear_revenue_share": (
        "terms_first",
        "Clarify the negotiated percentage, earning period and revenue basis.",
    ),
    "prefers_fixed_fee": (
        None,
        "Ask the owner to review compensation preferences; do not promise or change payment.",
    ),
    "weak_content_fit": (
        "content_first",
        "Review creator relevance and use only observed content evidence.",
    ),
    "unclear_attribution": (
        "terms_first",
        "Explain that attribution, reporting and payout terms need owner agreement.",
    ),
    "too_long": ("concise", "Shorten the next draft while preserving terms and the opt-out."),
    "unclear_next_step": (
        "concise",
        "End with one clear question and explain the owner-contact handoff.",
    ),
}


def suggested_feedback_tags(text: str) -> list[str]:
    """Untrusted inbound text can suggest labels, but cannot update learning by itself."""
    if not isinstance(text, str):
        return []
    text = authored_reply_text(text, limit=4000)
    patterns = {
        "too_generic": r"\b(?:too generic|generic (?:pitch|email)|copy[- ]paste[dt]?|impersonal|"
        r"(?:zbyt|za) ogoln[yae]|kopiuj[- ]wklej|bez personalizacji)\b",
        "unclear_offer": r"\b(?:unclear offer|what (?:exactly )?(?:are you offering|is the offer)|"
        r"don't understand (?:the |your )?offer|niejasna oferta|"
        r"co (?:dokladnie )?oferujecie|nie rozumiem (?:tej |waszej )?oferty)\b",
        "unclear_revenue_share": r"\b(?:how (?:does|would) (?:the )?revenue shar\w* work|"
        r"what (?:percentage|earning window)|unclear revenue shar\w*|"
        r"jaki procent|ile tygodni|jak dziala (?:podzial|udzial w) (?:zarobk\w*|zysk\w*))\b",
        "prefers_fixed_fee": r"\b(?:prefer (?:a )?fixed fee|fixed fee only|"
        r"only (?:accept|do|work with) (?:a )?fixed fee|"
        r"(?:wole|preferuje) stal[ae] (?:stawke|wynagrodzenie)|"
        r"tylko (?:za )?stal[ae] (?:stawka|stawke|wynagrodzenie))\b",
        "weak_content_fit": r"\b(?:not (?:a )?(?:good )?fit for (?:my|our) (?:channel|audience)|"
        r"(?:my|our) (?:channel|audience) (?:isn't|is not) about minecraft|"
        r"nie pasuje do (?:mojego|naszego) (?:kanalu|widz\w*)|"
        r"(?:moj|nasz) kanal nie jest o minecraft)\b",
        "unclear_attribution": r"\b(?:how (?:will|would|do) you (?:track|attribute)|"
        r"unclear attribution|how (?:are|is) (?:the )?"
        r"(?:revenue|earnings|sales) (?:tracked|attributed)|"
        r"jak (?:bedziecie )?(?:mierzyc|sledzic|przypisywac|rozliczac)|"
        r"jak (?:mierzycie|sledzicie|przypisujecie|rozliczacie)|"
        r"jak sprawdzimy (?:wyniki|zarobki|przychod))\b",
        "too_long": r"\b(?:too long|too much text|shorten (?:the |your )?(?:email|pitch)|"
        r"(?:za|zbyt) dlug[aiy]|za duzo tekstu|skroc(?:cie)? (?:mail|wiadomosc|oferte))\b",
        "unclear_next_step": r"\b(?:what (?:should|do) (?:i|we) do next|"
        r"unclear next step|who (?:should|do) (?:i|we) contact|"
        r"co (?:mam|mamy) (?:zrobic )?dalej|"
        r"z kim (?:mam|mamy) sie skontaktowac|jaki (?:jest )?kolejny krok)\b",
    }
    suggestions = []
    for tag in FEEDBACK_TAGS:
        for match in re.finditer(patterns[tag], text):
            preceding = text[max(0, match.start() - 45) : match.start()]
            # "Not too long" and "I don't prefer a fixed fee" are not objections.
            # Intentional negation inside "not a fit" is part of its own reviewed hint.
            clause = re.split(r"[.!?;,:]|\b(?:but|ale|jednak)\b", preceding)[-1]
            if re.search(
                r"\b(?:not|never|no|isn't|aren't|wasn't|don't|doesn't|nie|nigdy)"
                r"(?:\s+[\w']+){0,4}\s*$",
                clause,
            ):
                continue
            suggestions.append(tag)
            break
    return suggestions


def _variant_metrics(variants: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    by_name = {}
    invalid = False
    for row in variants[:100]:
        name = row.get("variant")
        if name not in PAID_VARIANTS:
            continue
        values = [row.get(key, 0) for key in ("sent", "replies", "positive")]
        if (
            name in by_name
            or any(type(value) is not int or value < 0 for value in values)
            or values[1] > values[0]
            or values[2] > values[1]
        ):
            invalid = True
            continue
        sent, replies, positive = values
        by_name[name] = {
            "variant": name,
            "sent": sent,
            "replies": replies,
            "positive": positive,
            "positive_rate": positive / sent if sent else None,
        }
    return [
        by_name.get(
            name, {"variant": name, "sent": 0, "replies": 0, "positive": 0, "positive_rate": None}
        )
        for name in PAID_VARIANTS
    ], invalid


def creator_learning_insights(
    outcomes: list[dict[str, Any]], variants: list[dict[str, Any]]
) -> dict[str, Any]:
    """Aggregate explicit operator-reviewed outcome tags; repeats never inflate samples.

    Callers supply marketing outcome records, not raw Gmail candidates. A defensive
    needs_review/reviewed/source check also rejects accidentally mixed unreviewed evidence.
    """
    creators: set[str] = set()
    positives: set[str] = set()
    tag_creators: dict[str, set[str]] = {tag: set() for tag in FEEDBACK_TAGS}
    variant_creators: dict[str, set[str]] = {variant: set() for variant in PAID_VARIANTS}
    for outcome in outcomes:
        prospect_id = outcome.get("prospect_id")
        if (
            not prospect_id
            or outcome.get("needs_review") is True
            or outcome.get("reviewed") is False
            or (outcome.get("source") == "gmail" and not outcome.get("reviewed_by"))
        ):
            continue
        creator = str(prospect_id)
        creators.add(creator)
        if outcome.get("classification") in {"interested", "converted", "promotion_published"}:
            positives.add(creator)
        tags = outcome.get("feedback_tags", [])
        if not isinstance(tags, list):
            continue
        for tag in tags:
            if not isinstance(tag, str) or tag not in tag_creators:
                continue
            tag_creators[tag].add(creator)
            variant = _GUIDANCE[tag][0]
            if variant:
                variant_creators[variant].add(creator)

    metrics, invalid_metrics = _variant_metrics(variants)
    recommendations = [
        {
            "tag": tag,
            "creators": len(tag_creators[tag]),
            "message": _GUIDANCE[tag][1],
            "variant": _GUIDANCE[tag][0],
            "enough_evidence": len(tag_creators[tag]) >= MIN_REVIEWED_CREATORS,
        }
        for tag in FEEDBACK_TAGS
        if tag_creators[tag]
    ]
    recommended_variant, evidence_source = None, "balanced"
    reason = "Balanced draft variants; not enough reviewed feedback or measured comparison yet"
    if not invalid_metrics and all(row["sent"] >= MIN_SENT_PER_VARIANT for row in metrics):
        ranked = sorted(metrics, key=lambda row: row["positive_rate"], reverse=True)
        winner, runner_up = ranked[:2]
        left = winner["positive"] * runner_up["sent"]
        right = runner_up["positive"] * winner["sent"]
        # Cross multiplication preserves exact 5 percentage point / 1.5x thresholds.
        if 100 * (left - right) >= 5 * winner["sent"] * runner_up["sent"] and 2 * left >= 3 * right:
            recommended_variant, evidence_source = winner["variant"], "measured_variant"
            reason = (
                f"Observed positive-reply rate {winner['positive_rate']:.1%} for "
                f"{winner['variant']} versus {runner_up['positive_rate']:.1%} for "
                f"{runner_up['variant']}; each variant has at least {MIN_SENT_PER_VARIANT} sends"
            )
    if recommended_variant is None:
        ranked_feedback = sorted(
            PAID_VARIANTS, key=lambda name: len(variant_creators[name]), reverse=True
        )
        leading, second = ranked_feedback[:2]
        count = len(variant_creators[leading])
        if count >= MIN_REVIEWED_CREATORS and count > len(variant_creators[second]):
            recommended_variant, evidence_source = leading, "reviewed_feedback"
            reason = (
                f"{count} distinct creators supplied reviewed feedback supporting "
                f"{leading}; this is a copy hypothesis, not a measured performance win"
            )

    return {
        "samples": {
            "reviewed_creators": len(creators),
            "positive_creators": len(positives),
            "tagged_creators": len(set().union(*tag_creators.values())),
        },
        "feedback_counts": {tag: len(tag_creators[tag]) for tag in FEEDBACK_TAGS},
        "recommendations": recommendations,
        "recommended_variant": recommended_variant,
        "evidence_source": evidence_source,
        "reason": reason,
        "variants": metrics,
        "invalid_metrics": invalid_metrics,
        "minimum_reviewed_creators": MIN_REVIEWED_CREATORS,
        "minimum_sent_per_variant": MIN_SENT_PER_VARIANT,
        "caveat": (
            "Small, observational samples can reflect creator mix or timing. "
            "Replies and acceptance are never guaranteed. Only future draft wording changes; "
            "compensation, contact "
            "authority, sending limits and approvals remain fixed."
        ),
    }


def choose_paid_variant(
    prospect_id: UUID,
    outcomes: list[dict[str, Any]],
    variants: list[dict[str, Any]],
    *,
    adaptive_mode: bool = True,
) -> tuple[str, str]:
    bucket = int(prospect_id.hex[-8:], 16)
    insights = creator_learning_insights(outcomes, variants)
    recommended = insights["recommended_variant"] if adaptive_mode else None
    if recommended:
        if bucket % 10 < 8:
            return recommended, insights["reason"]
        alternatives = [variant for variant in PAID_VARIANTS if variant != recommended]
        return alternatives[bucket % len(alternatives)], (
            "Bounded draft exploration alongside the evidence-backed copy recommendation"
        )
    return PAID_VARIANTS[bucket % len(PAID_VARIANTS)], (
        insights["reason"] if adaptive_mode else "Adaptive copy disabled; balanced draft assignment"
    )
