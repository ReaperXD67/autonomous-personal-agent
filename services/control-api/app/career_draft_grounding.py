"""Issue bounded résumé choices and resolve model selections without invented quotes.

The inventory is private prompt data, never an external lookup or an inference. Every
issued text value is an exact substring of the supplied résumé. IDs bind the complete
résumé snapshot and the text, so selections cannot be reused against a changed résumé.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

GROUNDING_VERSION = 1
MAX_RESUME_CHARS = 16_000
MAX_EXCERPTS = 28
MAX_EXCERPT_CHARS = 400
MAX_KEYWORDS = 32
_CONTACT = re.compile(
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|https?://\S+|www\.\S+|"
    r"(?:linkedin\.com|github\.com)/\S+|\+?\d[\d ()-]{7,}\d", re.I,
)
_WORDS = re.compile(r"[\w][\w+#.-]{1,35}", re.UNICODE)
_HEADINGS = frozenset({
    "professional work experience", "relevant work experience", "education and qualifications",
    "technical skills and tools", "personal contact information", "professional career summary",
})
_COMMON = frozenset(
    {"about", "after", "also", "an", "and", "are", "as", "at", "be", "been", "build", "built",
     "by", "can", "candidate", "company", "experience", "for", "from", "have", "in", "into", "is",
     "it", "job", "my", "of", "on", "or", "our", "role", "software", "team", "that", "the", "their",
     "these", "this", "to", "using", "was", "we", "were", "will", "with", "work", "you", "your",
     "years"}
)


def _tokens(text: str) -> set[str]:
    return {word.casefold().strip(".-") for word in _WORDS.findall(text)} - _COMMON


def _issued_id(prefix: str, digest: str, text: str) -> str:
    value = hashlib.sha256(f"{GROUNDING_VERSION}:{digest}:{text}".encode()).hexdigest()
    return f"{prefix}_{value[:16]}"


def _source_spans(resume: str) -> list[str]:
    spans: list[str] = []
    for line_match in re.finditer(r"[^\r\n]+", resume):
        line = line_match.group()
        # Contacts are excluded, including a contact appended to an otherwise useful
        # line. Splitting around them retains only exact, non-contact source spans.
        for fragment in _CONTACT.split(line):
            fragment = fragment.strip(" \t|•")
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", fragment):
                remaining = sentence.strip()
                while remaining:
                    boundary = min(len(remaining), MAX_EXCERPT_CHARS)
                    if boundary < len(remaining):
                        boundary = remaining.rfind(" ", 0, boundary + 1) or boundary
                    excerpt = remaining[:boundary].strip()
                    remaining = remaining[boundary:].strip()
                    # Headings, dates, names and isolated contact labels are not
                    # useful evidence. Do not normalize/rewrite retained substrings.
                    words = _WORDS.findall(excerpt)
                    if (len(excerpt) >= 12 and len(words) >= 3 and not excerpt.endswith(":")
                            and excerpt.casefold() not in _HEADINGS
                            and not (excerpt.isupper() and len(words) <= 6)):
                        spans.append(excerpt)
    return list(dict.fromkeys(spans))


def build_grounding_inventory(context: dict[str, Any]) -> dict[str, Any]:
    from app.career_application_quality import inspect_posting

    resume = str(context.get("resume_text") or "")
    digest = hashlib.sha256(resume.encode()).hexdigest()
    visible_resume = resume[:MAX_RESUME_CHARS]
    if len(resume) > MAX_RESUME_CHARS and not resume[MAX_RESUME_CHARS].isspace():
        visible_resume = re.sub(r"\S+$", "", visible_resume)
    posting = inspect_posting(str(context.get("description") or ""))["cleaned_text"]
    relevant = _tokens(f"{context.get('title', '')} {posting[:12000]}")
    candidate_name = str(context.get("candidate_name") or "").strip().casefold()
    spans = [span for span in _source_spans(visible_resume)
             if span.casefold() != candidate_name]
    # Stable source-order ties; evidence is selected for relevance without claiming
    # the résumé proves any requirement or inferred years of experience.
    ranked = sorted(enumerate(spans), key=lambda pair: (
        -len(_tokens(pair[1]) & relevant), pair[0],
    ))
    evidence = [{"id": _issued_id("e", digest, text), "text": text}
                for _, text in ranked[:MAX_EXCERPTS]]

    skills = context.get("skills")
    skill_choices = skills if isinstance(skills, list) else []
    candidates = [skill for skill in skill_choices
                  if isinstance(skill, str) and 1 < len(skill.strip()) <= 80]
    # Job tokens are offered only if the same whole token exists in the résumé.
    # A job requirement alone can therefore never become a candidate keyword.
    candidates.extend(sorted(relevant))
    keywords: list[dict[str, str]] = []
    seen: set[str] = set()
    for candidate in candidates[:300]:
        match = re.search(r"(?<!\w)" + re.escape(candidate.strip()) + r"(?!\w)",
                          visible_resume, re.I)
        if match is None or _CONTACT.search(match.group()):
            continue
        text = match.group()
        if text.casefold() in seen:
            continue
        seen.add(text.casefold())
        keywords.append({"id": _issued_id("k", digest, text), "text": text})
        if len(keywords) == MAX_KEYWORDS:
            break
    return {"version": GROUNDING_VERSION, "resume_sha256": digest,
            "evidence": evidence, "keywords": keywords}


def resolve_grounding(
    content: dict[str, Any], context: dict[str, Any], *, preserve_invalid: bool = False,
) -> dict[str, Any]:
    inventory = build_grounding_inventory(context)
    evidence = {item["id"]: item["text"] for item in inventory["evidence"]}
    keywords = {item["id"]: item["text"] for item in inventory["keywords"]}
    evidence_ids = content["evidence_ids"]
    keyword_ids = content["resume_keyword_ids"]
    errors = []
    if not evidence_ids:
        errors.append("evidence_selection_missing")
    for label, selected, available in (
        ("evidence", evidence_ids, evidence), ("keyword", keyword_ids, keywords),
    ):
        if len(set(selected)) != len(selected):
            errors.append(f"duplicate_{label}_id")
        if any(value not in available for value in selected):
            errors.append(f"unknown_{label}_id")
    if errors and not preserve_invalid:
        raise ValueError("Model draft selected unsupported résumé grounding IDs")
    # Never partially accept a malformed grounding selection. Empty evidence also
    # blocks old consumers which do not yet inspect the grounding provenance.
    safe_evidence_ids = [] if errors else evidence_ids[:]
    safe_keyword_ids = [] if errors else keyword_ids[:]
    return {
        "evidence": [evidence[key] for key in safe_evidence_ids],
        "resume_keywords": [keywords[key] for key in safe_keyword_ids],
        "grounding": {"version": GROUNDING_VERSION,
                      "resume_sha256": inventory["resume_sha256"],
                      "evidence_ids": safe_evidence_ids,
                      "resume_keyword_ids": safe_keyword_ids,
                      "valid": not errors, "errors": errors},
    }


def grounding_is_valid(context: dict[str, Any], content: dict[str, Any]) -> bool:
    """Recompute provenance at review/send time; a saved verdict is not authority."""
    grounding = content.get("grounding")
    if not isinstance(grounding, dict) or grounding.get("valid") is not True:
        return False
    if type(grounding.get("version")) is not int or grounding["version"] != GROUNDING_VERSION:
        return False
    resume = str(context.get("resume_text") or "")
    digest = hashlib.sha256(resume.encode()).hexdigest()
    # Final approval contexts need not include the original profile skill list.
    # Recompute IDs from exact rendered source strings, not a reranked inventory.
    for source_key, id_key, prefix, count_limit, text_limit in (
        ("evidence", "evidence_ids", "e", 6, MAX_EXCERPT_CHARS),
        ("resume_keywords", "resume_keyword_ids", "k", 12, 80),
    ):
        texts, ids = content.get(source_key), grounding.get(id_key)
        if (not isinstance(texts, list) or not isinstance(ids, list)
                or len(texts) != len(ids) or len(texts) > count_limit
                or (source_key == "evidence" and not texts)):
            return False
        if any(not isinstance(text, str) or not text or len(text) > text_limit
               or text not in resume or _CONTACT.search(text) for text in texts):
            return False
        expected = [_issued_id(prefix, digest, text) for text in texts]
        if ids != expected or len(set(expected)) != len(expected):
            return False
    return (grounding.get("resume_sha256") == digest and grounding.get("errors") == [])
