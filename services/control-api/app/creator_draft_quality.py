"""Read-only editorial observations; never a quality score or sending decision."""

from __future__ import annotations

import re
from typing import Any

REPORT_VERSION = "creator-draft-review-v1"
REVIEW_LIMITATIONS = (
    "Only public metadata was observed. Check the title-to-idea connection; "
    "this report cannot establish what a video contains.",
    "Accuracy, natural wording, translation and creator fit require human review. "
    "Absence of a wording marker does not establish good copy or likely interest.",
    "Review the whole rendered email and commercial terms before exact approval. "
    "This report neither changes the saved draft nor grants sending authority.",
)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _feedback_claim(rationale: str) -> bool:
    pattern = (
        r"\bfeedback\s+(?:shows|suggests|supports|indicates|confirms)\b|"
        r"\b(?:based on|aligns? with|aligned with|reflects?)\s+"
        r"(?:\w+\s+){0,5}feedback\b|\bfeedback alignment\b"
    )
    for match in re.finditer(pattern, rationale, re.I):
        preceding = re.split(r"[.!?;,:]", rationale[:match.start()])[-1][-70:]
        if not re.search(
            r"\b(?:no|not|never|without|zero)\b(?:\s+[\w']+){0,5}\s*$", preceding, re.I,
        ):
            return True
    return False


def creator_draft_quality_report(row: dict[str, Any]) -> dict[str, Any]:
    """Observe the immutable stored copy, not live settings or private contact data.

    Counts and wording markers are explainable editorial hints. There is no
    semantic classifier, model call, mutable learning, approval or persistence.
    """
    context = _object(row.get("model_context"))
    campaign = _object(_object(row.get("input_snapshot")).get("campaign"))
    copy = _object(row.get("model_copy"))
    body = _text(row.get("body"))
    hook, idea, rationale = (_text(copy.get(key)) for key in (
        "hook", "content_idea", "rationale",
    ))
    available = bool(hook and body)
    language = _text(campaign.get("target_language")).lower()
    language = language if re.fullmatch(r"[a-z]{2,3}(?:-[a-z]{2,8})?", language) else None
    findings: list[dict[str, str]] = []

    def note(code: str, message: str, *, severity: str = "warning") -> None:
        findings.append({"code": code, "severity": severity, "message": message})

    if not available:
        note("COPY_UNAVAILABLE", "A complete rendered model draft is not available to inspect.",
             severity="info")
    else:
        if language and language.split("-")[0] != "en" and campaign.get("language_mode") in {
            "prefer", "strict",
        }:
            note("CAMPAIGN_LANGUAGE_MISMATCH", "The current AI path writes English, while the "
                 "stored campaign requests another language. Review or translate the exact copy.")
        if len(body.split()) > 250:
            note("RENDERED_EMAIL_LONG", "The rendered email exceeds 250 words, including its "
                 "terms and footer. Consider shortening it while preserving required information.")
        # Inspect model suggestions only. A quoted title can legitimately contain
        # numbers, questions or wording that must not become a claim by Hermes.
        suggestions = " ".join((hook, idea))
        if re.search(r"\b(?:i|we)(?:['’]ve| have)?\s+(?:watched|enjoyed|loved)\b|"
                     r"\bbeen following\b", suggestions, re.I):
            note("VIEWING_CLAIM_MARKER", "The suggestions contain a viewing or fan claim. "
                 "Only public metadata was observed; inspect and remove unsupported claims.")
        if re.search(r"\b(?:your|the|this)\s+(?:latest\s+)?(?:video|upload|episode)\s+"
                     r"(?:shows?|showed|demonstrates?|reveals?|highlights?|highlighted)\b",
                     suggestions, re.I):
            note("VIDEO_CONTENT_CLAIM_MARKER", "The suggestions describe video contents. "
                 "A recorded title alone does not establish those contents.")
        if re.search(r"\b(?:your|the)\s+(?:minecraft\s+)?(?:channel|content|videos?)\s+"
                     r"(?:is|are|seems?(?: like)?|looks?(?: like)?|would be)\s+"
                     r"(?:a\s+)?(?:great|good|perfect|nice)\s+fit\b", hook, re.I):
            note("GENERIC_OPENING_MARKER", "The opening contains a generic fit phrase. "
                 "Check whether it explains a specific connection to the recorded topic.")
        samples = _object(_object(context.get("learning_summary")).get("samples"))
        reviewed = samples.get("reviewed_creators")
        if type(reviewed) is int and reviewed == 0 and _feedback_claim(rationale):
            note("FEEDBACK_CLAIM_WITHOUT_REVIEWS", "The rationale invokes feedback, but its "
                 "stored learning snapshot contains zero reviewed creators.")
        evidence = context.get("evidence")
        reference = _object(evidence[0]) if isinstance(evidence, list) and evidence else {}
        source_url = _text(reference.get("url"))
        if not source_url or source_url not in body:
            note("SOURCE_REFERENCE_MISSING", "The rendered email does not contain its "
                 "recorded source link. Inspect the evidence citation.")
        paragraphs = [paragraph for paragraph in body.split("\n\n")
                      if not paragraph.lstrip().startswith("Public video reference:")]
        next_step = "\n".join(paragraphs)
        if not re.search(r"\b(?:would|could|are|do|can)\s+you\b[^\n?]{0,170}\?|"
                         r"\b(?:please|feel free to)\s+(?:reply|share|let (?:me|us) know)\b",
                         next_step, re.I):
            note("NEXT_STEP_NOT_DETECTED", "No supported English reply question or request "
                 "was detected outside the video citation. Review the next step manually.")
    return {
        "version": REPORT_VERSION,
        "available": available,
        "generated_language": "en",
        "campaign_language": language,
        "rendered_word_count": len(body.split()) if body else None,
        "model_word_count": len((hook + " " + idea).split()) if copy else None,
        "findings": findings,
        "review_limitations": list(REVIEW_LIMITATIONS),
        "human_review_required": True,
        "sending_authority": False,
    }
