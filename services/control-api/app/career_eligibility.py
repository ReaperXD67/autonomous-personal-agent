"""Narrow mandatory-qualification review, separate from fit and draft truthfulness.

This original lexical gate does not certify eligibility. Only explicit current
résumé statements can support detected requirements; dates, projects and location
never establish aggregate employment tenure, a completed degree or legal status.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.career_application_quality import MAX_POSTING, inspect_posting

ELIGIBILITY_POLICY_VERSION = 1
MAX_CLAUSES = 400
MAX_EXCERPT = 700
MAX_REQUIREMENTS = 24
_NUMBERS = {word: index for index, word in enumerate((
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "twenty",
))}
_NUMBER = r"(?:\d{1,2}(?:\.\d+)?|" + "|".join(_NUMBERS) + r")"
_DURATION = re.compile(
    rf"\b(?P<low>{_NUMBER})\s*(?:(?:[-–—]|to|and)\s*(?P<high>{_NUMBER})\s*)?"
    r"\+?\s*(?:or more\s+)?(?P<unit>years?|yrs?|months?)\b", re.I,
)
_EXPERIENCE = re.compile(
    r"\b(?:experience|expertise|professional|commercial|industry|hands[- ]on|"
    r"developing|building|programming|coding|paid employment)\b", re.I,
)
_PROFESSIONAL = re.compile(r"\b(?:professional|commercial|industry|full[- ]time|paid)\b", re.I)
_HARD = re.compile(
    r"\b(?:must|require[ds]?|requirements?|mandatory|minimum|at least|only|shall|"
    r"need(?:ed|s)?|you (?:have|bring)|we (?:require|expect)|"
    r"(?:candidate|applicant)s? (?:must have|has|have))\b", re.I,
)
_STRICT_HARD = re.compile(r"\b(?:must|require[ds]?|mandatory|minimum|at least|only|shall)\b", re.I)
_SOFT = re.compile(
    r"\b(?:prefer(?:red|ably)?|nice[- ]to[- ]have|desirable|ideally|optional|a plus|bonus)\b",
    re.I,
)
_REQUIRED_HEADER = re.compile(
    r"^(?:(?:minimum|basic|required|essential|job)\s+)?(?:qualifications?|requirements?)"
    r"\s*:?$|^(?:what you(?:'ll| will) need|what you bring|who you are|must[- ]haves?)\s*:?$",
    re.I,
)
_SOFT_HEADER = re.compile(
    r"^(?:preferred qualifications?|nice[- ]to[- ]haves?|bonus(?: points)?|desirable)\s*:?$", re.I,
)
_OTHER_HEADER = re.compile(
    r"^(?:responsibilities|what you(?:'ll| will) do|about(?: us| the company| the role)?|"
    r"benefits|what we offer|equal opportunity|company (?:history|overview))\s*:?$", re.I,
)
_SPLIT = re.compile(
    r"\n+|;|(?<!B\.Sc\.)(?<!B\.Tech\.)(?<!B\.E\.)(?<!M\.Sc\.)"
    r"(?<=[.!?])\s+(?=[A-Z])|\s+\b(?:but|however)\b\s+|"
    r",\s*(?=(?:master|bachelor|ph\.?d|completed degree|preferred|nice[- ]to[- ]have)\b)",
    re.I,
)
_CONJUNCTION = re.compile(
    rf"(?:,\s*|\s+and\s+)(?=(?:at least|must|minimum|"
    rf"{_NUMBER}\s*(?:\+|[-–—]|years?|yrs?|months?)|completed\s+degree|"
    r"bachelor|master|currently enrolled|enrollment required|"
    r"no\s+(?:\w+\s+){0,3}(?:experience|degree))(?=\b|\s))", re.I,
)
_DEGREES = {
    "bachelor": re.compile(r"\b(?:bachelor(?:['’]s)?|undergraduate degree)\b", re.I),
    "bsc": re.compile(r"\bB\.?\s?Sc\b|\bBachelor(?:['’]s)? of Science\b", re.I),
    "btech": re.compile(r"\bB\.?\s?Tech\b|\bBachelor(?:['’]s)? of Technology\b", re.I),
    "beng": re.compile(r"\bB\.E\.?(?=\s|[/,]|$)|(?-i:\bBE\b)|\bBEng\b|"
                       r"\bBachelor(?:['’]s)? of Engineering\b", re.I),
    "master": re.compile(r"\bmaster(?:['’]s)?(?:\s+degree)?\b|\bM\.?\s?(?:Sc|Tech)\b", re.I),
    "phd": re.compile(r"\b(?:Ph\.?D\.?|doctorate|doctoral degree)\b", re.I),
}
_DEGREE = re.compile(
    r"\b(?:degree|bachelor|undergraduate|master|doctorate|doctoral|B\.?\s?(?:Sc|Tech)|"
    r"BEng|Ph\.?D)\b|\bB\.E\.?(?=\s|[/,]|$)|(?-i:\b(?:BE|BS)\b)", re.I,
)
_COMPLETED = re.compile(r"\b(?:graduated|completed|awarded|conferred|earned|obtained|hold|holds)\b",
                        re.I)
_ENROLLMENT = re.compile(
    r"\b(?:currently (?:enrolled|pursuing|studying)|enrolled|pursuing|"
    r"(?:undergraduate|university|college|current) student|student status)\b", re.I,
)
_ENROLLMENT_REQUIREMENT = re.compile(
    r"\b(?:enrolled|enrollment|pursuing|students?|studying)\b", re.I,
)
_GRADUATION = re.compile(r"\b(?:graduat(?:e[sd]?|ing|ion)|batch|class of)\b", re.I)
_COUNTRIES = {
    "india": r"\b(?:India|Indian)\b",
    "us": r"\b(?:United States|American)\b|(?-i:\b(?:USA|US)\b)|\bU\.S\.(?:A\.)?",
    "uk": r"\b(?:United Kingdom|UK|British)\b|\bU\.K\.",
    "canada": r"\b(?:Canada|Canadian)\b",
    "germany": r"\b(?:Germany|German)\b",
    "australia": r"\b(?:Australia|Australian)\b",
    "singapore": r"\bSingapore(?:an)?\b",
    "france": r"\b(?:France|French)\b",
    "netherlands": r"\b(?:Netherlands|Dutch)\b",
}
_AUTH = re.compile(
    r"\b(?:authori[sz](?:ed|ation)|eligible to work|right to work|work permit|"
    r"citizen(?:s|ship)?|permanent resident|visa|sponsor(?:ship)?)\b", re.I,
)
_NO_SPONSOR = re.compile(
    r"\b(?:(?:cannot|can't|do not|don't|will not|unable to)\s+(?:provide|offer|support|"
    r"sponsor)|no\s+(?:visa\s+)?sponsorship|(?:visa\s+)?sponsorship\s+(?:is\s+)?"
    r"(?:not available|not offered|unavailable)|must not require\s+(?:visa\s+)?sponsorship)\b",
    re.I,
)
_YC_CONSTRAINT = re.compile(
    r"^[ \t]*(minExperience|minSchoolYear)[ \t]*:[ \t]*([^\n]*)$", re.I | re.M,
)
_YC_UNCONSTRAINED = frozenset({
    "", "null", "none", "any", "any experience", "any school year", "not required",
    "no experience required", "no prior experience required",
})
_ZERO_MINIMUM = re.compile(
    r"0(?:\.0+)?\s*(?:\+|(?:[-–—]|to|and)\s*\d+(?:\.\d+)?)?\s*"
    r"(?:(?:years?|yrs?|months?)\s*)?(?:(?:of\s+)?experience)?", re.I,
)
_MESSAGES = {
    "mandatory_tenure_unverified": "Explicit résumé evidence does not establish this tenure.",
    "mandatory_degree_unverified": "The required degree or equivalence is not established.",
    "mandatory_graduation_batch_unverified": "The required graduation cohort is not established.",
    "mandatory_enrollment_unverified": "Required current enrollment is not established.",
    "mandatory_work_authorization_unverified": "Required work or citizenship status is unstated.",
    "qualification_scan_incomplete": "The posting exceeds the bounded qualification review.",
}


def _fold(text: str) -> str:
    return " ".join(text.casefold().split())


def _number(value: str) -> float:
    return float(_NUMBERS[value.casefold()]) if value.casefold() in _NUMBERS else float(value)


def _minimum(match: re.Match) -> float:
    value = _number(match["low"])
    return value / 12 if match["unit"].casefold().startswith("month") else value


def _clauses(text: str):
    section = None

    def separate(match: re.Match) -> str:
        # Preserve a zero-lower-bound range such as "between zero and two years".
        if "and" in match[0].casefold() and re.search(
            rf"\b{_NUMBER}$", text[:match.start()].rstrip(), re.I,
        ):
            return match[0]
        return "\n"

    for part in _SPLIT.split(_CONJUNCTION.sub(separate, text)):
        excerpt = part.strip(" \t\r•-*,:")
        if not excerpt:
            continue
        if _REQUIRED_HEADER.fullmatch(excerpt):
            section = "required"
            continue
        if _SOFT_HEADER.fullmatch(excerpt):
            section = "preferred"
            continue
        if _OTHER_HEADER.fullmatch(excerpt):
            section = None
            continue
        heading = re.match(r"^(Requirements?|Qualifications?|Preferred qualifications?)\s*:\s*",
                           excerpt, re.I)
        if heading:
            section = "preferred" if heading[1].casefold().startswith("preferred") else "required"
            excerpt = excerpt[heading.end():].strip()
        yield excerpt, section


def _negated(excerpt: str, noun: str) -> bool:
    return bool(re.search(
        rf"\b(?:no|without|do not need|don't need|need not|not required to have)\b"
        rf".{{0,45}}\b(?:{noun})\b.{{0,30}}\b(?:required|necessary|needed)\b|"
        rf"\b(?:{noun})\b.{{0,30}}\b(?:not required|not necessary|not needed|not mandatory|"
        rf"not essential|optional)\b|"
        rf"\b(?:do not need|don't need|need not|not required to have)\b.{{0,45}}\b(?:{noun})\b",
        excerpt, re.I,
    ))


def _is_hard(excerpt: str, section: str | None, *, bare: bool = False) -> bool:
    explicit = bool(_STRICT_HARD.search(excerpt))
    if section == "preferred" and not explicit:
        return False
    school_preference = re.search(
        r"\bpreferred\s+(?:school|universit|college|institution)|"
        r"\b(?:school|universit\w*|college|institution)\b.{0,20}\bpreferred\b", excerpt, re.I,
    )
    whole_optional = re.search(r"\b(?:optional|desirable|nice[- ]to[- ]have|ideally)\b",
                               excerpt, re.I)
    if _SOFT.search(excerpt) and not explicit and (not school_preference or whole_optional):
        return False
    return bool(_HARD.search(excerpt)) or section == "required" or bare


def _tenure_supported(resume: str, requirement: str, minimum: float) -> bool:
    domain = re.search(r"\b(?:experience|expertise)\s+(?:in|with|using)\s+(.{1,90})",
                       requirement, re.I)
    domains = set(re.findall(r"[a-z0-9+#]+", domain[1].casefold())) if domain else set()
    domains -= {"a", "an", "and", "or", "the", "at", "least", "required", "is", "must", "have"}
    for statement, _ in _clauses(resume[:MAX_POSTING]):
        if not _EXPERIENCE.search(statement):
            continue
        if re.search(r"\b(?:not|no|without|will|would|hope|plan|aim|expected)\b", statement, re.I):
            continue
        if re.search(r"\b(?:project|academic|course|degree|study|university|education)\b",
                     statement, re.I) and not _PROFESSIONAL.search(statement):
            continue
        if domains and re.search(r"\b(?:projects?|academic|course|degree|study|education)\b",
                                 statement, re.I):
            continue
        if _PROFESSIONAL.search(requirement) and not _PROFESSIONAL.search(statement):
            continue
        if re.search(r"\b(?:internship|intern)\b", statement, re.I) and not re.search(
            r"\b(?:internship|intern)\b", requirement, re.I,
        ):
            continue
        observed = set(re.findall(r"[a-z0-9+#]+", statement.casefold()))
        domain_match = (bool(domains & observed) if domain and re.search(r"\bor\b", domain[1], re.I)
                        else domains <= observed)
        durations = list(_DURATION.finditer(statement))
        if domain_match and len(durations) == 1 and _minimum(durations[0]) >= minimum:
            return True
    return False


def _completed_degree_statement(statement: str) -> bool:
    for credential in _DEGREE.finditer(statement):
        for completion in _COMPLETED.finditer(statement):
            between = statement[min(credential.end(), completion.end()):
                                max(credential.start(), completion.start())]
            if len(between) > 70 or re.search(r"\b(?:course|module|semester|project|training)\b",
                                             between, re.I):
                continue
            if completion.end() <= credential.start():
                return True
            tail = statement[completion.end():].strip(" ,:;.!")
            if not tail or re.fullmatch(r"(?:in\s+)?20\d{2}", tail, re.I):
                return True
    return False


def _degree_supported(resume: str, requirement: str, year: int) -> bool:
    wanted = {kind for kind, pattern in _DEGREES.items() if pattern.search(requirement)}
    if not wanted:
        return False
    for statement, _ in _clauses(resume[:MAX_POSTING]):
        if (not _completed_degree_statement(statement) or _ENROLLMENT.search(statement)
                or re.search(r"\b(?:not|incomplete|expected|will|plan|hope)\b", statement, re.I)
                or any(int(value) > year for value in re.findall(r"\b20\d{2}\b", statement))):
            continue
        if (re.search(r"\b(?:course|module|semester|project)\b", statement, re.I)
                and not re.search(r"\bdegree\b", statement, re.I)):
            continue
        observed = {kind for kind, pattern in _DEGREES.items() if pattern.search(statement)}
        if observed & {"bsc", "btech", "beng"}:
            observed.add("bachelor")
        matched = bool((wanted - {"bachelor"}) & observed)
        # A specific B.Tech/B.E./B.Sc. requirement is not met by generic bachelor
        # wording, nor do we decide that the courses or subjects are equivalent.
        specific_bachelor = wanted & {"bsc", "btech", "beng"}
        if not specific_bachelor and "bachelor" in wanted and "bachelor" in observed:
            matched = True
        levels = ({"bachelor"} if wanted & {"bachelor", "bsc", "btech", "beng"} else set())
        levels |= wanted & {"master", "phd"}
        if len(levels) > 1 and not re.search(r"\bor\b|/", requirement, re.I):
            matched = matched and levels <= observed
        subjects = [term for term in ("computer science", "electrical engineering",
                    "mechanical engineering", "mathematics", "statistics", "data science")
                    if term in _fold(requirement)]
        field = re.search(
            r"\b(?:degree|(?:bachelor|master)(?:['’]s)?(?:\s+of\s+(?:science|technology|"
            r"engineering))?|B\.?\s?(?:Sc|Tech)|B\.E\.?|BEng)\s+in\s+(.{1,100})",
            requirement, re.I,
        )
        if field:
            subject = re.split(r"\b(?:is|required|mandatory|from)\b|[.()]",
                               field[1], maxsplit=1, flags=re.I)[0].strip()
            alternatives = [re.split(r"\band\b|,", option, flags=re.I)
                            for option in re.split(r"\bor\b|/", subject, flags=re.I)]
            matched = matched and any(
                all(_fold(term.strip()) in _fold(statement) for term in option if term.strip())
                for option in alternatives if any(term.strip() for term in option)
            )
        subject_match = (all(term in _fold(statement) for term in subjects)
                         if not re.search(r"\bor\b", requirement, re.I)
                         else any(term in _fold(statement) for term in subjects))
        if matched and (not subjects or subject_match):
            return True
    return False


def _graduation_supported(resume: str, requirement: str) -> bool:
    wanted = set(re.findall(r"\b20\d{2}\b", requirement))
    if not wanted:
        return False
    for statement, _ in _clauses(resume[:MAX_POSTING]):
        if re.search(r"\b(?:not|no|would|hope|plan|applied|apply|jobs?|mentored|taught)\b",
                     statement, re.I):
            continue
        years = set(re.findall(
            r"\b(?:graduat(?:e[sd]?|ing|ion)|class of|completion)\b[^\n\d]{0,40}(20\d{2})\b",
            statement, re.I,
        ))
        years.update(re.findall(r"\b(20\d{2})\s+(?:graduate|graduating|graduation)\b",
                                statement, re.I))
        if wanted & years:
            return True
    return False


def _enrollment_supported(resume: str, requirement: str) -> bool:
    for statement, _ in _clauses(resume[:MAX_POSTING]):
        if not _ENROLLMENT.search(statement) or re.search(r"\b(?:not|no longer|formerly)\b",
                                                       statement, re.I):
            continue
        wanted = {kind for kind, pattern in _DEGREES.items() if pattern.search(requirement)}
        observed = {kind for kind, pattern in _DEGREES.items() if pattern.search(statement)}
        if observed & {"bsc", "btech", "beng"}:
            observed.add("bachelor")
        if not wanted or wanted & observed:
            return True
    return False


def _authorization_supported(
    resume: str, requirement: str, location: str, eligibility_facts: Any,
) -> bool:
    requirement_countries = {key for key, pattern in _COUNTRIES.items()
                             if re.search(pattern, requirement, re.I)}
    location_countries = {key for key, pattern in _COUNTRIES.items()
                         if re.search(pattern, location, re.I)}
    india_fact = (isinstance(eligibility_facts, dict)
                  and eligibility_facts.get("india_authorized_without_sponsorship") is True)
    specific_status = re.search(
        r"\b(?:citizens?|citizenship|permanent resident|permit|visa type)\b", requirement, re.I,
    )
    specific_visa = re.search(r"\bvisa\b", re.sub(r"\bvisa sponsorship\b", "", requirement,
                                                 flags=re.I), re.I)
    general_authorization = re.search(r"authori[sz]|eligible to work|right to work",
                                      requirement, re.I)
    no_sponsor = bool(_NO_SPONSOR.search(requirement))
    if re.search(r"\bmust not\b", requirement, re.I) and not no_sponsor:
        return False
    if (india_fact and (requirement_countries | location_countries) == {"india"}
            and not specific_status and not specific_visa
            and (no_sponsor or general_authorization)):
        return True
    countries = requirement_countries or location_countries
    if len(countries) != 1:
        return False
    for statement, _ in _clauses(resume[:MAX_POSTING]):
        stated_countries = {key for key, pattern in _COUNTRIES.items()
                            if re.search(pattern, statement, re.I)}
        if not countries & stated_countries:
            continue
        if no_sponsor:
            if re.search(
                r"\b(?:do not|don't|does not|will not|won't)\s+require\s+(?:visa\s+)?sponsorship\b|"
                r"\b(?:no|without)\s+(?:visa\s+)?sponsorship\s+(?:needed|required)\b",
                statement, re.I,
            ):
                return True
            continue
        if re.search(r"\b(?:not|ineligible|no longer|need|require)\b", statement, re.I):
            continue
        citizenship = bool(re.search(r"\bcitizen(?:s|ship)?\b", requirement, re.I))
        proof = (r"\bcitizen(?:ship)?\b" if citizenship else
                 r"\b(?:authori[sz]ed to work|eligible to work|right to work|valid work permit)\b")
        if re.search(r"\bpermanent resident\b", requirement, re.I):
            proof = r"\bpermanent resident\b"
        elif re.search(r"\bwork permit\b", requirement, re.I):
            proof = r"\bvalid work permit\b"
        elif re.search(r"\bvisa\b", requirement, re.I):
            continue  # Specific visa categories need reviewed legal/screening evidence.
        if re.search(proof, statement, re.I) and any(
            re.search(_COUNTRIES[country], statement, re.I) for country in countries
        ):
            return True
    return False


def assess_eligibility(
    profile: dict[str, Any], opportunity: dict[str, Any], *, now: datetime | None = None,
) -> dict[str, Any]:
    """Return bounded review evidence, never a semantic or legal certification."""
    now = now or datetime.now(UTC)
    raw = opportunity.get("description")
    raw = raw if isinstance(raw, str) else ""
    posting = inspect_posting(raw)["cleaned_text"]
    resume = profile.get("resume_text")
    resume = resume if isinstance(resume, str) else ""
    requirements: list[dict[str, Any]] = []
    findings: list[dict[str, str]] = []
    incomplete = len(raw) > MAX_POSTING

    def add(kind: str, excerpt: str, supported: bool, code: str) -> None:
        nonlocal incomplete
        if any(item["kind"] == kind and item["excerpt"] == excerpt for item in requirements):
            return
        if kind != "bounded_review" and len(requirements) >= MAX_REQUIREMENTS - 1:
            incomplete = True
            return
        requirements.append({"kind": kind, "excerpt": excerpt[:MAX_EXCERPT],
                             "status": "supported" if supported else "review_required",
                             "reason": "Explicit saved evidence matches this narrow check."
                             if supported else _MESSAGES[code]})
        if not supported and len(findings) < MAX_REQUIREMENTS:
            findings.append({"code": code, "severity": "review",
                             "requirement_excerpt": excerpt[:MAX_EXCERPT],
                             "reason": _MESSAGES[code]})

    if opportunity.get("source") == "yc":
        for index, constraint in enumerate(_YC_CONSTRAINT.finditer(posting)):
            if index >= MAX_CLAUSES:
                incomplete = True
                break
            key, value = constraint[1].casefold(), constraint[2].strip()
            if _fold(value) in _YC_UNCONSTRAINED:
                continue
            if len(constraint[0]) > MAX_EXCERPT:
                incomplete = True
            if key == "minexperience":
                if _ZERO_MINIMUM.fullmatch(value):
                    continue
                durations = list(_DURATION.finditer(value))
                # A bare provider value such as "3+" is deliberately opaque:
                # no implied unit, aggregate tenure or degree-year translation.
                supported = (len(durations) == 1 and _minimum(durations[0]) > 0
                             and _tenure_supported(resume, value, _minimum(durations[0])))
                add("professional_tenure", constraint[0].strip(), supported,
                    "mandatory_tenure_unverified")
            elif value != "0":
                add("current_enrollment", constraint[0].strip(), False,
                    "mandatory_enrollment_unverified")

    for index, (excerpt, section) in enumerate(_clauses(posting)):
        if index >= MAX_CLAUSES or len(requirements) >= MAX_REQUIREMENTS:
            incomplete = True
            break
        if len(excerpt) > MAX_EXCERPT:
            incomplete = True
        excerpt = excerpt[:MAX_EXCERPT]
        if re.search(r"^(?:our (?:company|team)|we have|the company|founded)\b", excerpt, re.I):
            continue
        hard = _is_hard(excerpt, section)
        durations = list(_DURATION.finditer(excerpt)) if _EXPERIENCE.search(excerpt) else []
        if durations and not _negated(excerpt, "experience") and _is_hard(
            excerpt, section, bare=durations[0].start() < 12,
        ):
            minimum = max(_minimum(match) for match in durations)
            if minimum > 0:
                add("professional_tenure", excerpt, _tenure_supported(resume, excerpt, minimum),
                    "mandatory_tenure_unverified")
        if (_ENROLLMENT_REQUIREMENT.search(excerpt) and hard
                and not _negated(excerpt, "enrollment|student")):
            add("current_enrollment", excerpt, _enrollment_supported(resume, excerpt),
                "mandatory_enrollment_unverified")
        elif _DEGREE.search(excerpt) and _is_hard(
            excerpt, section, bare=bool(_DEGREE.match(excerpt)),
        ) and not _negated(excerpt, "degree|bachelor|master|education"):
            add("completed_degree", excerpt, _degree_supported(resume, excerpt, now.year),
                "mandatory_degree_unverified")
        if (_GRADUATION.search(excerpt) and re.search(r"\b20\d{2}\b", excerpt)
                and (hard or section == "required" or re.search(r"\bonly\b", excerpt, re.I))):
            add("graduation_cohort", excerpt, _graduation_supported(resume, excerpt),
                "mandatory_graduation_batch_unverified")
        if (_AUTH.search(excerpt) and (hard or _NO_SPONSOR.search(excerpt))
                and not _negated(excerpt, "authorization|citizenship|work permit")):
            add("work_authorization", excerpt,
                _authorization_supported(resume, excerpt, str(opportunity.get("location") or ""),
                                         profile.get("eligibility_facts")),
                "mandatory_work_authorization_unverified")
    if incomplete:
        add("bounded_review", "", False, "qualification_scan_incomplete")
    return {
        "version": ELIGIBILITY_POLICY_VERSION,
        "disposition": "review_required" if findings else "no_blocking_requirement",
        "requirements": requirements, "findings": findings, "model_calls": 0,
        "evaluated_year": now.year, "excerpt_source": "cleaned_posting",
        "limitations": (
            "Narrow lexical mandatory-qualification review, not verified eligibility. "
            "Unrecognized requirements and semantic/legal equivalence need human review. "
            "No aggregate tenure, completed degree or authorization is inferred from dates, "
            "projects, location or draft claims. Only explicit India work-authorization "
            "confirmation supplements résumé evidence for India-only general checks."
        ),
    }


def eligibility_blocker(
    profile: dict[str, Any], opportunity: dict[str, Any], *, now: datetime | None = None,
) -> str | None:
    report = assess_eligibility(profile, opportunity, now=now)
    if report["findings"]:
        return "Mandatory qualification review required: " + report["findings"][0]["reason"]
    return None
