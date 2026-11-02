from copy import deepcopy
from datetime import UTC, datetime

import pytest
from test_career_autopilot import NOW as AUTOPILOT_NOW
from test_career_autopilot import opportunity, profile, run

from app import career_autopilot
from app.application_browser import canonical_hash
from app.career import SCORING_POLICY_VERSION
from app.career_autopilot import PROFILE_SCOPE_FIELDS, eligibility_reason, profile_hash
from app.career_eligibility import (
    ELIGIBILITY_POLICY_VERSION,
    MAX_EXCERPT,
    MAX_REQUIREMENTS,
    assess_eligibility,
    eligibility_blocker,
)

NOW = datetime(2026, 11, 2, tzinfo=UTC)


def assess(posting, resume="Built Python APIs and PostgreSQL projects.", **facts):
    return assess_eligibility({"resume_text": resume, **facts},
                              {"description": posting, "location": "India"}, now=NOW)


def codes(report):
    return {finding["code"] for finding in report["findings"]}


@pytest.mark.parametrize("posting", [
    "Must have 3+ years of professional experience.",
    "Requirements\nAt least three years of commercial experience with Python.",
    "Qualifications\n5 years of experience in distributed systems.",
    "3-5 years of software development experience.",
    "Minimum 6 months of industry experience required.",
    "Internship applicants must have 2 years of professional experience.",
])
def test_positive_mandatory_tenure_needs_explicit_matching_resume_evidence(posting):
    report = assess(posting)
    assert codes(report) == {"mandatory_tenure_unverified"}
    assert report["disposition"] == "review_required" and report["model_calls"] == 0
    assert report["findings"][0]["requirement_excerpt"] in posting


@pytest.mark.parametrize("resume", [
    "B.Sc Computer Science 2024-2028. Built Python projects.",
    "Intern role: January 2025-January 2026. Freelance work: January 2025-January 2026.",
    "Four years of academic project experience in Python.",
    "Three years of internship experience with Python.",
])
def test_overlapping_dates_education_and_project_tenure_are_never_aggregated(resume):
    assert "mandatory_tenure_unverified" in codes(assess(
        "Must have 2 years of professional experience.", resume,
    ))


@pytest.mark.parametrize(("posting", "resume"), [
    ("At least 3 years of professional experience required.",
     "I have 4 years of professional experience."),
    ("Must have 2 years of commercial experience in Python.",
     "I have three years of commercial experience in Python."),
    ("Minimum 6 months of professional experience required.",
     "I have one year of professional experience."),
])
def test_explicit_current_summary_can_support_same_narrow_minimum(posting, resume):
    report = assess(posting, resume)
    assert not codes(report)
    assert report["requirements"][0]["status"] == "supported"


def test_tenure_in_one_language_does_not_prove_required_years_in_another():
    report = assess("Must have 3 years of professional experience in Python.",
                    "I have 5 years of professional experience in Java. Built a Python project.")
    assert "mandatory_tenure_unverified" in codes(report)


@pytest.mark.parametrize("posting", [
    "0-2 years of experience required. Freshers welcome.",
    "Minimum zero to two years of professional experience.",
    "Between 0 and 2 years of experience required.",
    "No prior experience required.", "Experience is not required.",
    "A completed degree is not required.", "You do not need a bachelor's degree.",
    "Qualifications\nA bachelor's degree is not essential.",
    "Three years of experience are not mandatory.",
    "3 years of Python experience preferred.",
    "Preferred qualifications\n3 years of professional experience.\nMaster's degree.",
    "Preferred qualifications\nYou have 3 years of professional experience.",
    "Nice-to-have: Completed bachelor's degree.",
    "Qualifications\n3 years of experience preferred.\nPython projects welcome.",
    "Top-tier universities are preferred.",
    "Bachelor's degree from a preferred school is optional.",
    "Our company has 10 years of professional experience. Build APIs with us.",
    "The contract lasts 3 years. Experience with Python is useful.",
    "Visa sponsorship is available.",
])
def test_zero_experience_negated_preferences_and_employer_history_do_not_block(posting):
    assert not codes(assess(posting))


def test_zero_lower_bound_does_not_remove_another_mandatory_degree():
    report = assess("0-2 years of experience required; completed B.Tech degree required.")
    assert codes(report) == {"mandatory_degree_unverified"}


@pytest.mark.parametrize("resume", [
    "B.Sc Computer Science 2024-2028.",
    "Currently pursuing a B.Tech degree.",
    "I have not completed a bachelor's degree.",
    "Expected to be awarded a bachelor's degree in 2028.",
    "Graduated with a bachelor's degree in 2028.",
])
def test_completed_degree_is_not_inferred_from_attendance_future_dates_or_negation(resume):
    assert "mandatory_degree_unverified" in codes(assess(
        "Bachelor's degree required.", resume,
    ))


def test_specific_degree_equivalence_is_not_inferred_and_preferences_do_not_weaken_requirement():
    resume = "Graduated with B.Sc Computer Science in 2024."
    assert "mandatory_degree_unverified" in codes(assess("B.Tech required.", resume))
    assert not codes(assess("Bachelor's degree in Computer Science required.", resume))
    assert "mandatory_degree_unverified" in codes(assess(
        "Bachelor's degree required (preferred universities listed separately).",
    ))
    assert "mandatory_degree_unverified" in codes(assess(
        "Bachelor's degree or equivalent experience required.",
        "Built academic Python projects for four years.",
    ))


def test_degree_alternatives_and_additional_preferred_degree_are_distinct():
    resume = "Completed a bachelor's degree in Computer Science in 2024."
    assert not codes(assess("Bachelor's or master's degree required.", resume))
    assert not codes(assess("Bachelor's degree required, master's degree preferred.", resume))
    assert "mandatory_degree_unverified" in codes(assess(
        "Bachelor's and master's degrees required.", resume,
    ))


@pytest.mark.parametrize(("posting", "resume", "blocked"), [
    ("Only 2027 graduates may apply.", "Expected graduation: 2028.", True),
    ("Must be graduating in 2027 or 2028.", "Expected graduation: 2028.", False),
    ("Requirements\nGraduation batch 2028.", "B.Sc 2024-2028.", True),
    ("Only 2028 graduates may apply.", "Graduation: 2024. Launched a project in 2028.", True),
    ("2028 graduates preferred.", "B.Sc 2024-2028.", False),
])
def test_graduation_cohort_needs_explicit_graduation_evidence(posting, resume, blocked):
    report = assess(posting, resume)
    assert ("mandatory_graduation_batch_unverified" in codes(report)) is blocked


def test_enrollment_needs_explicit_current_status_and_is_not_a_completed_degree_requirement():
    posting = "Must be currently enrolled in a bachelor's program."
    assert not codes(assess(posting, "Currently pursuing B.Sc Computer Science."))
    assert codes(assess(posting, "B.Sc Computer Science 2024-2028.")) == {
        "mandatory_enrollment_unverified",
    }
    assert codes(assess("Must be a university student.", "Completed B.Sc in 2024.")) == {
        "mandatory_enrollment_unverified",
    }


@pytest.mark.parametrize("posting", [
    "Must be authorized to work in India.",
    "Must be eligible to work in India without sponsorship.",
    "We cannot provide visa sponsorship.",
    "Visa sponsorship is not available.",
])
def test_india_confirmation_is_strictly_typed_and_only_satisfies_india_general_checks(posting):
    fact = {"india_authorized_without_sponsorship": True}
    assert not codes(assess(posting, eligibility_facts=fact))
    for value in (None, False, "true", 1):
        assert "mandatory_work_authorization_unverified" in codes(assess(
            posting, eligibility_facts={"india_authorized_without_sponsorship": value},
            locations=["India"], application_identity={"location": "India"},
        ))


@pytest.mark.parametrize(("posting", "location"), [
    ("Must be authorized to work in the United States.", "United States"),
    ("Must be authorized to work.", "Remote worldwide"),
    ("No visa sponsorship is available.", "Remote"),
    ("Indian citizens only.", "India"),
    ("Must hold permanent resident status in India.", "India"),
    ("Must hold a valid work permit in India.", "India"),
])
def test_india_fact_never_proves_foreign_ambiguous_or_specific_legal_status(posting, location):
    report = assess_eligibility({"resume_text": "Python projects.", "eligibility_facts": {
        "india_authorized_without_sponsorship": True,
    }}, {"description": posting, "location": location}, now=NOW)
    assert "mandatory_work_authorization_unverified" in codes(report)


def test_authorization_evidence_cannot_come_from_location_or_negative_statements():
    job = "Must be authorized to work in the United States."
    assert "mandatory_work_authorization_unverified" in codes(assess(
        job, "Located in the United States. Not authorized to work in the United States.",
    ))
    assert not codes(assess(job, "I am authorized to work in the United States."))
    assert not codes(assess("No visa sponsorship is available.",
                           "I do not require visa sponsorship in India."))


def test_report_is_bounded_exact_and_does_not_expose_resume_or_trust_draft_claims():
    candidate = {"resume_text": "Private synthetic credential. Python projects.",
                 "quality_report": {"disposition": "checks_passed"}}
    job = {"description": "Requirements\nMust have 3 years of professional experience."}
    before = deepcopy((candidate, job))
    report = assess_eligibility(candidate, job, now=NOW)
    assert (candidate, job) == before
    assert all(item["excerpt"] in job["description"] for item in report["requirements"])
    assert "Private synthetic credential" not in str(report)
    long = assess("Requirements\n" + "Must have 3 years of experience. " * 1000)
    assert "qualification_scan_incomplete" in codes(long)
    assert len(long["requirements"]) <= MAX_REQUIREMENTS
    assert all(len(item["requirement_excerpt"]) <= MAX_EXCERPT for item in long["findings"])
    assert eligibility_blocker(candidate, job, now=NOW).startswith("Mandatory qualification review")


def test_policy_version_and_explicit_facts_invalidate_old_grants_without_changing_fit():
    candidate = profile()
    old_hash = canonical_hash({
        "scoring_policy_version": SCORING_POLICY_VERSION,
        "profile": {key: candidate.get(key) for key in PROFILE_SCOPE_FIELDS},
    })
    assert profile_hash(candidate) != old_hash
    authorized = run(candidate)
    role = {**opportunity(), "description": "Python PostgreSQL Docker. Must have 3 years of "
            "professional experience."}
    assert "Mandatory qualification review" in eligibility_reason(
        authorized, candidate, role, now=AUTOPILOT_NOW,
    )
    assert "Profile changed" in eligibility_reason({**authorized, "profile_hash": old_hash},
                                                  candidate, role, now=AUTOPILOT_NOW)
    assert profile_hash(candidate) != profile_hash({**candidate, "eligibility_facts": {
        "india_authorized_without_sponsorship": True,
    }})


def test_changing_eligibility_policy_version_alone_changes_grant_hash(monkeypatch):
    before = profile_hash(profile())
    monkeypatch.setattr(career_autopilot, "ELIGIBILITY_POLICY_VERSION",
                        ELIGIBILITY_POLICY_VERSION + 1)
    assert before != profile_hash(profile())


@pytest.mark.parametrize("resume", [
    "I do not have 5 years of professional experience.",
    "I hope to have 5 years of professional experience.",
    "I have 2 years of professional experience in Python and 5 years in Java.",
])
def test_negation_future_or_mixed_duration_statements_do_not_prove_matching_tenure(resume):
    assert "mandatory_tenure_unverified" in codes(assess(
        "Must have 3 years of professional experience in Python.", resume,
    ))


@pytest.mark.parametrize("posting", [
    "Bachelor of Engineering required.", "B.E. required.", "BE required.",
    "Completed bachelor's degree in information systems required.",
])
def test_specific_degree_or_field_does_not_accept_an_unrelated_completed_degree(posting):
    assert "mandatory_degree_unverified" in codes(assess(
        posting, "Graduated with B.Sc Computer Science in 2024.",
    ))


def test_course_completion_is_not_a_completed_degree():
    assert "mandatory_degree_unverified" in codes(assess(
        "Bachelor's degree required.", "Completed a bachelor's level course in Python.",
    ))


def test_preferred_school_does_not_remove_an_otherwise_mandatory_degree():
    assert "mandatory_degree_unverified" in codes(assess(
        "Qualifications\nBachelor's degree from a preferred school.",
    ))


def test_negated_or_unrelated_graduation_year_does_not_establish_cohort():
    for resume in ("I am not graduating in 2028.", "I plan to apply to 2028 graduate jobs.",
                   "I mentored the 2028 graduate cohort.", "I applied for 2028 graduate jobs."):
        assert "mandatory_graduation_batch_unverified" in codes(assess(
            "Only 2028 graduates may apply.", resume,
        ))


@pytest.mark.parametrize("posting", [
    "Indian citizens only.", "Must be a permanent resident in India.",
    "Must hold a valid work permit in India.", "Must have an H1B visa in the United States.",
])
def test_generic_resume_authorization_does_not_prove_a_specific_legal_status(posting):
    assert "mandatory_work_authorization_unverified" in codes(assess(
        posting, "I am authorized to work in India and the United States.",
    ))


def test_no_sponsorship_evidence_is_jurisdiction_specific():
    report = assess("We cannot provide visa sponsorship.",
                    "I do not require visa sponsorship in the United States.")
    assert "mandatory_work_authorization_unverified" in codes(report)
    assert "mandatory_work_authorization_unverified" in codes(assess(
        "We cannot provide visa sponsorship.", "I do not require visa sponsorship.",
    ))


def test_us_pronoun_does_not_turn_india_requirement_into_foreign_authorization():
    candidate = {"resume_text": "Python projects.", "eligibility_facts": {
        "india_authorized_without_sponsorship": True,
    }}
    assert not codes(assess_eligibility(candidate, {
        "description": "You must be authorized to work with us.", "location": "India",
    }))
    assert not codes(assess_eligibility(candidate, {
        "description": "Candidates must not require visa sponsorship.", "location": "India",
    }))


def test_one_country_resume_statement_does_not_establish_multijurisdiction_authorization():
    report = assess("Must be authorized to work in India and the United States.",
                    "I am authorized to work in India.")
    assert "mandatory_work_authorization_unverified" in codes(report)


def test_india_general_confirmation_does_not_establish_employment_visa():
    report = assess("Must be authorized to work in India on an Employment visa.",
                    eligibility_facts={"india_authorized_without_sponsorship": True})
    assert "mandatory_work_authorization_unverified" in codes(report)


@pytest.mark.parametrize("separator", [" and at least ", " and ", ", "])
def test_one_experience_waiver_does_not_remove_another_mandatory_tenure(separator):
    report = assess("No Java experience is required" + separator
                    + "3+ years of professional Python experience is mandatory.")
    assert "mandatory_tenure_unverified" in codes(report)
    assert "mandatory_tenure_unverified" in codes(assess(
        "At least 3 years of professional Python experience is mandatory "
        "and no Java experience is required.",
    ))


@pytest.mark.parametrize("degree", ["B.Tech", "Bachelor of Technology", "B.E."])
def test_specific_field_is_checked_for_abbreviated_and_full_degree_names(degree):
    assert "mandatory_degree_unverified" in codes(assess(
        f"{degree} in Chemical Engineering required.",
        "Completed B.Tech in Computer Science in 2024.",
    ))


def test_completed_course_does_not_convert_an_unfinished_degree_to_completed():
    report = assess("Bachelor's degree required.",
                    "Completed a Python course while studying for a bachelor's degree.")
    assert "mandatory_degree_unverified" in codes(report)


@pytest.mark.parametrize("value", ["0", "0-2", "0–2 years", "0 to 2 years", "0+", "Any",
                                  "Any experience", "null", "None", ""])
def test_yc_zero_or_unconstrained_experience_preserves_fresher_internship_eligibility(value):
    report = assess_eligibility({"resume_text": "Python projects."}, {
        "source": "yc",
        "description": "Internship.\nDeclared YC constraints:\nminExperience: " + value,
    })
    assert not codes(report)


@pytest.mark.parametrize("value", ["3+", "2", "3 years", "Senior", "Any senior applicant"])
def test_yc_positive_or_opaque_experience_requires_review_without_inventing_a_unit(value):
    report = assess_eligibility({"resume_text": "Python projects 2024-2028."}, {
        "source": "yc", "description": "Python role.\nminExperience: " + value,
    })
    assert codes(report) == {"mandatory_tenure_unverified"}
    assert report["findings"][0]["requirement_excerpt"] == "minExperience: " + value


def test_yc_natural_years_accept_only_explicit_tenure_not_opaque_numbers_or_attendance():
    candidate = {"resume_text": "I have 4 years of professional experience."}
    assert not codes(assess_eligibility(candidate, {
        "source": "yc", "description": "Python role.\nminExperience: 3 years",
    }))
    assert "mandatory_tenure_unverified" in codes(assess_eligibility(candidate, {
        "source": "yc", "description": "Python role.\nminExperience: 3+",
    }))


@pytest.mark.parametrize("value", ["2", "Senior", "Graduated", "2028"])
def test_yc_school_year_remains_review_when_meaning_or_current_status_is_unknown(value):
    report = assess_eligibility({"resume_text": "B.Sc 2024-2028. Expected graduation: 2028."}, {
        "source": "yc", "description": "Internship.\nminSchoolYear: " + value,
    })
    assert codes(report) == {"mandatory_enrollment_unverified"}
    assert report["findings"][0]["requirement_excerpt"] == "minSchoolYear: " + value


@pytest.mark.parametrize("value", ["0", "Any", "null", "None", ""])
def test_yc_absent_or_unconstrained_school_year_does_not_block(value):
    assert not codes(assess_eligibility({"resume_text": "Python projects."}, {
        "source": "yc", "description": "Internship.\nminSchoolYear: " + value,
    }))


def test_machine_constraint_interpretation_is_specific_to_yc_source():
    assert not codes(assess_eligibility({"resume_text": "Python projects."}, {
        "source": "ashby", "description": "Example source data: minExperience: 3+",
    }))


def test_empty_yc_value_does_not_consume_the_next_constraint_line():
    assert not codes(assess_eligibility({"resume_text": "Python projects."}, {
        "source": "yc", "description": "Internship.\nminExperience:\nminSchoolYear: 0",
    }))
    report = assess_eligibility({"resume_text": "Python projects."}, {
        "source": "yc", "description": "Internship.\nminExperience:\nminSchoolYear: Senior",
    })
    assert codes(report) == {"mandatory_enrollment_unverified"}
