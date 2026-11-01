"""Bounded deterministic checks for untrusted postings and résumé-grounded drafts.

Original implementation informed by ai-job-search's posting-integrity and
application-review workflow; see docs/research for pinned upstream provenance.
These checks expose narrow, inspectable evidence. They do not prove truth.
"""

from __future__ import annotations

import html
import re
import unicodedata
from html.parser import HTMLParser
from typing import Any

QUALITY_VERSION = 1
MAX_POSTING = 100000
MIN_COVER_WORDS = 20
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
         "param", "source", "track", "wbr"}
_DROP = {"script", "style", "noscript", "template", "svg"}
_INVISIBLE = set("\u200b\u200c\u200d\u2060\ufeff\u00ad\u200e\u200f")
_DIRECTIONAL = set("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
_DIRECTIVES = (
    re.compile(r"\b(?:ignore|disregard|override)\b.{0,25}\b(?:previous|prior|system|above)"
               r"\b.{0,25}\b(?:instructions?|prompts?)\b", re.I),
    re.compile(r"(?:<\|(?:system|assistant|developer)|\[INST\]|^\s*"
               r"(?:system|assistant|developer)\s*:\s*(?:you are|ignore|reveal|return))", re.I),
    re.compile(r"^\s*(?:please\s+)?(?:reveal|print|exfiltrate|upload|send)\b.{0,60}"
               r"(?:api[- ]?keys?|private keys?|access tokens?|system prompt|\.env\b)", re.I),
)
_PLACEHOLDER = re.compile(
    r"\[(?:your|insert|company name|candidate name|employer name|name here)[^\]]{0,90}\]"
    r"|\b(?:lorem ipsum|TODO|TBD|your[._]email@)\b", re.I,
)
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?:\s*%|[kKmM])?(?!\w)")
_ACCOMPLISHMENT = re.compile(
    r"\b(?:I|I've|my|we|our)\b.{0,100}\b(?:built|increased|reduced|grew|managed|"
    r"led|achieved|improved|delivered|scaled|processed|generated|saved|automated|served|"
    r"reached|handled|supported|trained|supervised|developed|launched)\b",
    re.I,
)
_TENURE = re.compile(
    r"\b(?:I|I've|my)\b.{0,65}\b(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|"
    r"eight|nine|ten|eleven|twelve)\s*\+?\s*years?\b.{0,35}\bexperience\b", re.I,
)
_REVERSE_TENURE = re.compile(
    r"\b(?:I|I've|my)\b.{0,65}\bexperience\s+(?:of\s+|for\s+|spanning\s+)?"
    r"(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    r"\s*\+?\s*years?\b", re.I,
)
_NUMBER_WORDS = {word: str(index) for index, word in enumerate(
    ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
     "ten", "eleven", "twelve"),
)}
_WORD_METRIC = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    r"(?:\s+(?:hundred|thousand|million|billion))?"
    r"\s+(?:percent|users?|customers?|requests?|projects?|employees?|teams?|"
    r"engineers?|clients?|dollars?|hours?)\b", re.I,
)
_HYPOTHETICAL = re.compile(
    r"\b(?:would|could|hope|plan|aim|want|intend|will|wish|if|unless|not|never)\b", re.I,
)


class _VisiblePosting(HTMLParser):
    """Keep visible data only; never load a URL, stylesheet or attachment."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []
        self.parts: list[str] = []
        self.hidden_blocks = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        style = re.sub(r"/\*.*?\*/", "", attributes.get("style") or "", flags=re.S)
        hidden = (tag in _DROP or "hidden" in attributes
                  or (attributes.get("aria-hidden") or "").casefold() == "true"
                  or re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden|"
                               r"opacity\s*:\s*0(?:\s*[;!]|\s*$)|"
                               r"font-size\s*:\s*0(?:px|pt|em|rem|%)?(?:\s*[;!]|\s*$))",
                               style, re.I) is not None)
        if hidden and not any(item[1] for item in self.stack):
            self.hidden_blocks += 1
        if tag not in _VOID:
            self.stack.append((tag, hidden))
        if not any(item[1] for item in self.stack):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        if not any(item[1] for item in self.stack):
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if not any(item[1] for item in self.stack):
            self.parts.append(data)


def inspect_posting(value: Any) -> dict[str, Any]:
    """Sanitize the model view; return counts rather than malicious excerpts."""
    raw = value[:MAX_POSTING] if isinstance(value, str) else ""
    hidden = 0
    if re.search(r"<(?:html|body|div|span|p|a|script|style|section|li)\b", raw, re.I):
        parser = _VisiblePosting()
        parser.feed(raw)
        parser.close()
        raw, hidden = "".join(parser.parts), parser.hidden_blocks
    raw = html.unescape(raw)
    invisible_count = 0
    directional_count = 0
    cleaned = []
    for index, char in enumerate(raw):
        if char in _DIRECTIONAL:
            directional_count += 1
            continue
        if (char in _INVISIBLE or 0xE0000 <= ord(char) <= 0xE007F
                or 0xE0100 <= ord(char) <= 0xE01EF):
            before, after = raw[max(0, index - 1):index], raw[index + 1:index + 2]
            if (before.isalpha() and after.isalpha()) or ord(char) >= 0xE0000:
                invisible_count += 1
            continue
        if unicodedata.category(char).startswith("C") and char not in "\n\r\t":
            continue
        cleaned.append(char)
    instructions = 0
    lines = []
    for line in "".join(cleaned).splitlines():
        if any(pattern.search(line[:4000]) for pattern in _DIRECTIVES):
            instructions += 1
            continue
        lines.append(" ".join(line.split()))
    text = "\n".join(line for line in lines if line)
    report = {
        "version": 1, "hidden_blocks_removed": hidden,
        "instruction_lines_removed": instructions,
        "invisible_tampering_characters_removed": invisible_count,
        "directional_controls_removed": directional_count,
        "requires_review": bool(instructions or invisible_count or directional_count),
        "model_calls": 0,
    }
    return {"cleaned_text": text, "report": report}


def _fold(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _supported(phrase: str, resume: str) -> bool:
    phrase = _fold(phrase.strip().strip('"\u201c\u201d'))
    return bool(phrase and re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", resume))


def _numeric_words(value: str) -> str:
    return re.sub(r"\b(?:" + "|".join(_NUMBER_WORDS) + r")\b",
                  lambda match: _NUMBER_WORDS[match.group()], _fold(value))


def assess_application_quality(context: dict[str, Any], content: dict[str, Any]) -> dict[str, Any]:
    """Recompute narrow checks from current résumé, posting and exact draft."""
    findings: list[dict[str, str]] = []

    def add(code: str, message: str) -> None:
        if not any(item["code"] == code for item in findings):
            findings.append({"code": code, "severity": "review", "message": message})

    resume = _fold(str(context.get("resume_text") or ""))
    integrity = inspect_posting(context.get("description"))["report"]
    letter = content.get("cover_letter")
    letter = letter if isinstance(letter, str) else ""
    evidence = content.get("evidence")
    evidence = evidence if isinstance(evidence, list) else []
    verified = sum(isinstance(item, str) and _supported(item, resume) for item in evidence[:12])
    word_count = len(letter.split())
    if not resume:
        add("resume_missing", "A current résumé is required for grounding checks")
    if not evidence or not verified:
        add("evidence_missing", "Include at least one direct quotation from the saved résumé")
    if verified != len(evidence):
        add("evidence_not_in_resume", "Some evidence entries are not exact saved-résumé quotations")
    keywords = content.get("resume_keywords")
    if not isinstance(keywords, list) or any(
        not isinstance(item, str) or not _supported(item, resume) for item in keywords[:12]
    ):
        add("unsupported_resume_keyword", "A résumé keyword is not supported by the saved résumé")
    if not letter.strip():
        add("cover_letter_missing", "A completed cover letter is required")
    elif word_count < MIN_COVER_WORDS:
        add("cover_letter_too_short", "Cover letter is below the 20-word usefulness heuristic")
    if word_count > 350:
        add("cover_letter_too_long", "Cover letter exceeds the 350-word preparation limit")
    candidate_text = "\n".join([letter, str(content.get("fit_summary") or ""),
                                *(item for item in evidence[:12] if isinstance(item, str))])
    if _PLACEHOLDER.search(candidate_text):
        add("unfilled_placeholder", "Application copy contains an unfilled placeholder")
    if any(pattern.search(candidate_text) for pattern in _DIRECTIVES):
        add("instruction_like_copy", "Application copy contains instruction-shaped content")
    for sentence in re.split(r"[.!?\n](?=\s|$)", letter):
        accomplishment = _ACCOMPLISHMENT.search(sentence)
        asserted = accomplishment and not _HYPOTHETICAL.search(accomplishment.group())
        if asserted:
            numbers = [match.group() for match in _NUMBER.finditer(sentence)
                       if not _HYPOTHETICAL.search(sentence[:match.start()])]
            word_metrics = [match.group() for match in _WORD_METRIC.finditer(sentence)
                            if not _HYPOTHETICAL.search(sentence[:match.start()])]
            if (any(not _supported(number, resume) for number in numbers)
                    or any(not _supported(_numeric_words(metric), _numeric_words(resume))
                           for metric in word_metrics)):
                add("unsupported_quantified_claim",
                    "A quantified candidate accomplishment has no matching résumé number")
        tenure = _TENURE.search(sentence) or _REVERSE_TENURE.search(sentence)
        if tenure and not _HYPOTHETICAL.search(tenure.group()):
            years = _NUMBER_WORDS.get(tenure.group(1).casefold(), tenure.group(1))
            resume_years = _numeric_words(resume)
            if re.search(r"(?<!\d)" + re.escape(years) + r"\s*\+?\s*years?\b",
                         resume_years) is None:
                add("unsupported_tenure_claim",
                    "A claimed duration of candidate experience is not explicit in the résumé")
    if integrity["requires_review"]:
        add("posting_integrity_review", "Posting contains removed instruction or tampering signals")
    return {
        "version": QUALITY_VERSION,
        "disposition": "review_required" if findings else "checks_passed",
        "word_count": word_count, "evidence_count": len(evidence),
        "verified_evidence_count": verified, "findings": findings,
        "posting_integrity": integrity, "model_calls": 0,
        "limitations": (
            "Mechanical checks do not establish semantic truth, eligibility or writing quality. "
            "Review the complete application and original evidence."
        ),
    }


def application_quality_blocker(
    context: dict[str, Any], content: dict[str, Any], *, require_report: bool = True,
) -> str | None:
    stored = content.get("quality_report")
    if require_report and (
        not isinstance(stored, dict) or stored.get("version") != QUALITY_VERSION
    ):
        return "Generate a current application draft before automatic submission"
    report = assess_application_quality(context, content)
    if report["findings"]:
        return "Application quality review required: " + report["findings"][0]["message"]
    return None
