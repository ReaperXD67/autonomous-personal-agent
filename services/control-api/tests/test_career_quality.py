from datetime import UTC, datetime, timedelta

import pytest

from app.career_autopilot import eligibility_reason, profile_hash
from app.career_quality import assess_opportunity, quality_blocker

NOW = datetime(2026, 10, 23, 12, tzinfo=UTC)
URL = "https://jobs.ashbyhq.com/example/role"


def opportunity(**changes):
    return {
        "source": "ashby", "source_url": URL, "apply_url": URL + "/application",
        "company": "Example", "title": "Python Engineer", "location": "India",
        "description": "Build Python services. Work with our engineering team on reliable "
        "production systems and collaborate with product managers on customer requirements.",
        "remote": True, "employment_type": "FullTime", "status": "new",
        "published_at": NOW - timedelta(hours=1), "published_at_basis": "published", **changes,
    }


@pytest.mark.parametrize("text,code", [
    ("To apply, pay the mandatory application fee before your interview.", "applicant_payment"),
    ("A processing fee is required to reserve your interview.", "applicant_payment"),
    ("Please send the upfront payment to confirm your application.", "applicant_payment"),
    ("Please buy a starter kit from the recruiter.", "applicant_payment"),
    ("No experience required, pay the application fee before your interview.", "applicant_payment"),
    ("Do not delay, pay the registration fee today.", "applicant_payment"),
    ("Pay an application fee and experience is not required.", "applicant_payment"),
    ("We never charge fees but pay a processing fee to apply.", "applicant_payment"),
    ("Applicants must pay 100 USD to start work.", "applicant_payment"),
    ("Pay a fee to apply for this role.", "applicant_payment"),
    ("Share your password so recruiting can verify your account.", "credential_request"),
    ("We never ask for money, but provide your password to apply.", "credential_request"),
    ("Please provide your bank credentials.", "credential_request"),
    ("Send your one-time code to the hiring manager.", "credential_request"),
    ("Upload a passport scan before applying.", "sensitive_identity_request"),
    ("Submit your bank account details with your resume.", "sensitive_identity_request"),
])
def test_specific_applicant_requests_trigger_explainable_review(text, code):
    result = assess_opportunity(opportunity(description=text), now=NOW)
    assert result["disposition"] == "review_required"
    assert code in {signal["code"] for signal in result["signals"]}
    assert quality_blocker(opportunity(description=text), now=NOW).startswith("Job safety review")
    assert result["authenticity"] == "unverified" and result["model_calls"] == 0


@pytest.mark.parametrize("text", [
    "We never ask you to pay an application fee.",
    "Do not share your password or one-time code with recruiters.",
    "We will not request you to submit your bank account details.",
    "Build payments systems for a banking platform using secure password hashing.",
    "Training is provided. We purchase equipment for employees and pay a salary.",
    "Build a payments platform where customers purchase gift cards.",
    "Develop a secure login workflow that lets users submit a password reset request.",
    "We do not ask applicants to pay a processing fee.",
    "An application fee is not required.",
])
def test_anti_scam_disclaimers_and_ordinary_job_domains_are_not_accusations(text):
    result = assess_opportunity(opportunity(description=text), now=NOW)
    assert result["disposition"] == "no_strong_flags"
    assert quality_blocker(opportunity(description=text), now=NOW) is None


def test_negated_disclaimer_cannot_hide_separate_real_fee_request():
    text = "Never share your password. To apply, pay an application fee to the recruiter."
    assert quality_blocker(opportunity(description=text), now=NOW) is not None


@pytest.mark.parametrize("url", [
    "http://jobs.ashbyhq.com/example/role", "https://user@jobs.ashbyhq.com/example/role",
    "https://jobs.ashbyhq.com:8443/example/role", "https://[broken", "javascript:apply()",
    URL + "#changed", "https://jobs.ashbyhq.com /example/role",
    "https://jobs.ashbyhq.com\\@evil.test/example/role",
])
def test_unsafe_urls_require_review_without_fetching_anything(url):
    result = assess_opportunity(opportunity(apply_url=url), now=NOW)
    assert "unsafe_listing_url" in {signal["code"] for signal in result["signals"]}
    assert result["disposition"] == "review_required"


@pytest.mark.parametrize("url,code", [
    ("https://jobs.ashbyhq.com.evil.test/example/role", "ats_destination_mismatch"),
    ("https://jobs.lever.co/example/role", "ats_destination_mismatch"),
    ("https://jobs.ashbyhq.com/another-employer/role", "ats_board_mismatch"),
])
def test_off_provider_and_different_employer_destinations_are_not_trusted(url, code):
    result = assess_opportunity(opportunity(apply_url=url), now=NOW)
    assert code in {signal["code"] for signal in result["signals"]}
    assert result["disposition"] == "review_required"


def test_company_hosted_greenhouse_links_remain_possible_but_unverified():
    url = "https://careers.example.test/job/123"
    result = assess_opportunity(opportunity(
        source="greenhouse", source_url=url, apply_url=url,
    ), now=NOW)
    assert result["disposition"] == "no_strong_flags"
    assert "custom_employer_url" in {signal["code"] for signal in result["signals"]}
    assert result["authenticity"] == "unverified"


def test_forged_ats_source_url_cannot_become_company_hosted_exception():
    result = assess_opportunity(opportunity(
        source_url="https://jobs.ashbyhq.com.evil.test/example/role",
    ), now=NOW)
    assert result["disposition"] == "review_required"
    assert "ats_source_mismatch" in {signal["code"] for signal in result["signals"]}


def test_greenhouse_embedded_application_preserves_the_canonical_board_and_job():
    result = assess_opportunity(opportunity(
        source="greenhouse", source_url="https://job-boards.greenhouse.io/example/jobs/123",
        apply_url="https://boards.greenhouse.io/embed/job_app?for=example&token=123",
    ), now=NOW)
    assert result["disposition"] == "no_strong_flags"


@pytest.mark.parametrize("source,listing,application,code", [
    ("greenhouse", "https://boards.greenhouse.io/embed/job_app?for=example&token=123",
     "https://boards.greenhouse.io/embed/job_app?for=other&token=123", "ats_board_mismatch"),
    ("lever", "https://jobs.lever.co/example/role",
     "https://jobs.eu.lever.co/example/role", "ats_board_mismatch"),
    ("ashby", URL, "https://jobs.ashbyhq.com/example/../other/role", "unsupported_ats_path"),
    ("ashby", URL, "https://jobs.ashbyhq.com/example/another-role", "ats_posting_mismatch"),
])
def test_provider_board_region_and_posting_identity_are_resolved_strictly(
    source, listing, application, code,
):
    result = assess_opportunity(opportunity(
        source=source, source_url=listing, apply_url=application,
    ), now=NOW)
    assert result["disposition"] == "review_required"
    assert code in {signal["code"] for signal in result["signals"]}


def test_consumer_contact_and_sparse_text_are_explained_without_fraud_label():
    result = assess_opportunity(opportunity(description="Apply: founder@gmail.com"), now=NOW)
    assert result["disposition"] == "no_strong_flags"
    assert {signal["code"] for signal in result["signals"]} == {
        "personal_email_contact", "limited_description",
    }


@pytest.mark.parametrize("basis,status", [
    ("published", "published"), ("updated", "publication_unconfirmed"),
    ("unknown", "publication_unconfirmed"), ("forged", "publication_unconfirmed"),
])
def test_timestamp_provenance_does_not_turn_an_update_into_a_new_post(basis, status):
    result = assess_opportunity(opportunity(published_at_basis=basis), now=NOW)
    assert result["publication"]["status"] == status
    assert result["publication"]["age_hours"] == 1
    assert result["authenticity"] == "unverified"


def test_missing_naive_and_future_dates_do_not_claim_verified_freshness():
    for timestamp in (None, "2026-10-23", NOW.replace(tzinfo=None)):
        result = assess_opportunity(opportunity(published_at=timestamp), now=NOW)
        assert result["publication"]["status"] == "unknown"
        assert result["publication"]["age_hours"] is None
    for delta in (timedelta(hours=1), timedelta(microseconds=1)):
        result = assess_opportunity(opportunity(published_at=NOW + delta), now=NOW)
        assert result["publication"]["status"] == "future"


def test_caller_supplied_trust_cannot_bypass_current_content_and_autopilot_gate():
    profile = {
        "candidate_name": "Synthetic", "resume_text": "Python engineer", "active": True,
        "desired_titles": ["Python Engineer"], "skills": ["Python"],
        "required_keywords": [], "excluded_keywords": [], "locations": ["India"],
        "remote_only": False, "employment_types": [], "max_age_hours": 72, "min_score": 0,
    }
    run = {"state": "running", "expires_at": NOW + timedelta(hours=1),
           "profile_hash": profile_hash(profile), "max_age_hours": 72, "min_score": 0}
    safe = opportunity()
    assert eligibility_reason(run, profile, safe, now=NOW) is None
    unsafe = {**safe, "description": "Pay an application fee. Python engineering role.",
              "quality": {"disposition": "no_strong_flags", "authenticity": "verified"}}
    assert "safety review required" in eligibility_reason(run, profile, unsafe, now=NOW)
    assert assess_opportunity(unsafe, now=NOW)["disposition"] == "review_required"
