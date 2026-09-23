from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.application_browser import EXTERNAL_APPLICATION_HOSTS
from app.career_autopilot import (
    allowed_url,
    eligibility_reason,
    hiring_email,
    opportunity_hash,
    profile_hash,
    target_key,
)
from app.career_autopilot_models import CareerPlay

NOW = datetime(2026, 9, 23, 12, tzinfo=UTC)
HOST = "jobs.ashbyhq.com"
URL = f"https://{HOST}/example/role-1"


def profile():
    return {
        "candidate_name": "Test Candidate", "resume_text": "Python and PostgreSQL projects",
        "application_identity": {"email": "candidate@example.test"},
        "desired_titles": ["Software Engineer"], "skills": ["Python", "PostgreSQL", "Docker"],
        "required_keywords": ["Python"], "excluded_keywords": ["Senior", "Staff"],
        "locations": ["India", "Remote"], "remote_only": True, "employment_types": ["FullTime"],
        "source_config": {"arbeitnow": False, "ashby_boards": ["example"]},
        "max_age_hours": 72, "min_score": 45,
    }


def opportunity():
    return {
        "company": "Example", "title": "Software Engineer", "location": "Remote — India",
        "description": "Build Python, PostgreSQL and Docker services.", "remote": True,
        "employment_type": "FullTime", "source": "ashby", "source_url": URL,
        "apply_url": URL, "published_at": NOW - timedelta(minutes=30),
        "published_at_basis": "published", "status": "new", "score": 100,
    }


def run(candidate=None, **overrides):
    fields = {
        "state": "running", "expires_at": NOW + timedelta(hours=1),
        "profile_hash": profile_hash(candidate or profile()), "max_age_hours": 72,
        "min_score": 45, "allowed_hosts": [HOST], "mode": "apply",
    }
    fields.update(overrides)
    return fields


def test_eligible_role_uses_current_content_not_previously_stored_score():
    assert eligibility_reason(run(), profile(), opportunity(), now=NOW) is None
    stale_score = {**opportunity(), "description": "No relevant technical evidence", "score": 100}
    assert "fit threshold" in eligibility_reason(run(), profile(), stale_score, now=NOW)
    restricted = {**opportunity(), "location": "Remote — United States", "score": 100}
    assert "fit threshold" in eligibility_reason(run(), profile(), restricted, now=NOW)


@pytest.mark.parametrize("state", ["paused", "expired", "completed", "cancelled"])
def test_nonrunning_states_never_authorize_another_action(state):
    assert "paused or expired" in eligibility_reason(
        run(state=state), profile(), opportunity(), now=NOW,
    )


def test_pausing_the_mission_blocks_even_a_still_running_run():
    assert "paused" in eligibility_reason(
        run(), {**profile(), "active": False}, opportunity(), now=NOW,
    )


@pytest.mark.parametrize("expiry", [NOW, NOW - timedelta(microseconds=1)])
def test_authorization_expiry_is_exclusive(expiry):
    assert "expired" in eligibility_reason(
        run(expires_at=expiry), profile(), opportunity(), now=NOW,
    )


@pytest.mark.parametrize("hours", [1, 72])
def test_exact_freshness_boundary_is_inclusive_and_one_microsecond_older_is_excluded(hours):
    candidate = {**profile(), "max_age_hours": hours}
    authorized = run(candidate, max_age_hours=hours)
    at_boundary = {**opportunity(), "published_at": NOW - timedelta(hours=hours)}
    assert eligibility_reason(authorized, candidate, at_boundary, now=NOW) is None
    older = {**at_boundary, "published_at": at_boundary["published_at"] - timedelta(microseconds=1)}
    assert "posting window" in eligibility_reason(authorized, candidate, older, now=NOW)


@pytest.mark.parametrize("basis", ["updated", "unknown", None])
def test_updated_and_unknown_timestamps_cannot_authorize_automatic_application(basis):
    role = {**opportunity(), "published_at_basis": basis}
    assert "verified posting date" in eligibility_reason(run(), profile(), role, now=NOW)


@pytest.mark.parametrize("posted", [NOW + timedelta(microseconds=1), None, "2026-09-23T11:30:00Z"])
def test_future_or_unparsed_dates_are_not_verified_fresh_posts(posted):
    role = {**opportunity(), "published_at": posted}
    assert "posting window" in eligibility_reason(run(), profile(), role, now=NOW)


@pytest.mark.parametrize("status", ["applied", "dismissed"])
def test_previously_applied_or_dismissed_opportunities_are_excluded(status):
    assert "dismissed or already applied" in eligibility_reason(
        run(), profile(), {**opportunity(), "status": status}, now=NOW,
    )


@pytest.mark.parametrize("field,value", [
    ("resume_text", "Changed résumé"), ("candidate_name", "Another Candidate"),
    ("application_identity", {"email": "other@example.test"}),
    ("desired_titles", ["Designer"]), ("locations", ["United States"]),
    ("required_keywords", ["Kubernetes"]), ("source_config", {"remotive": True}),
    ("max_age_hours", 168), ("min_score", 0),
])
def test_changed_candidate_or_preferences_require_new_authorization(field, value):
    candidate = {**profile(), field: value}
    assert "Profile changed" in eligibility_reason(run(), candidate, opportunity(), now=NOW)


def test_profile_hash_ignores_operational_bookkeeping_and_is_order_independent():
    original = profile()
    reordered = dict(reversed(list(original.items())))
    assert profile_hash(original) == profile_hash(reordered)
    assert profile_hash(original) == profile_hash({
        **original, "last_scan_at": NOW, "next_scan_at": NOW, "updated_at": NOW,
    })


@pytest.mark.parametrize("field,value", [
    ("company", "Another Employer"), ("title", "Senior Software Engineer"),
    ("description", "Send credentials elsewhere"), ("apply_url", URL + "-another"),
    ("published_at_basis", "updated"), ("published_at", NOW - timedelta(hours=7)),
])
def test_job_scope_hash_changes_when_action_relevant_details_change(field, value):
    changed = {**opportunity(), field: value}
    assert opportunity_hash(changed) != opportunity_hash(opportunity())


def test_job_hash_ignores_mutable_scoring_and_datetime_serialization_is_stable():
    original = opportunity()
    changed = deepcopy(original)
    changed.update({"score": 55, "score_reasons": ["changed"], "last_seen_at": NOW})
    assert opportunity_hash(changed) == opportunity_hash(original)
    serialized = {**original, "published_at": original["published_at"].isoformat()}
    assert opportunity_hash(serialized) == opportunity_hash(original)


@pytest.mark.parametrize("url", [
    URL.replace("https:", "http:"), URL.replace(HOST, HOST + ".evil.test"),
    URL.replace(HOST, "evil@" + HOST), URL.replace(HOST, HOST + ":8443"),
    URL.replace(HOST, "@" + HOST), URL.replace(HOST, ":@" + HOST),
    URL + "#different-form", "https://[broken", "javascript:alert(1)",
])
def test_application_scope_rejects_nonhttps_other_hosts_credentials_ports_and_fragments(url):
    assert not allowed_url(url, [HOST])


def test_application_scope_is_exact_allowlist_and_allows_standard_https_port():
    assert allowed_url(URL, [HOST])
    assert allowed_url(URL.replace(HOST, HOST + ":443"), [HOST])
    assert not allowed_url(URL, [])
    assert not allowed_url(URL, ["*.ashbyhq.com"])


def test_target_deduplication_ignores_tracking_order_fragment_and_trailing_slash():
    first = URL + "/?jobId=123&utm_source=campaign&ref=board&source=search#details"
    second = URL + "?jobId=123"
    assert target_key(first) == target_key(second)
    assert target_key(URL + "?team=eng&jobId=123") == target_key(URL + "?jobId=123&team=eng")
    assert target_key(URL + "?jobId=124") != target_key(second)
    assert target_key(URL + "-another?jobId=123") != target_key(second)


def test_equivalent_default_https_ports_cannot_bypass_target_deduplication():
    assert target_key(URL) == target_key(URL.replace(HOST, HOST + ":443"))


def test_hiring_email_requires_one_explicit_public_destination():
    assert hiring_email("To apply, send your CV to Jobs@example.test.") == "jobs@example.test"
    assert hiring_email("Hiring email: jobs@example.test. Send your CV to JOBS@example.test.") \
        == "jobs@example.test"
    assert hiring_email("Send applications to jobs@example.test or careers@example.test.") is None
    assert hiring_email("Apply through the careers site; no email address is published.") is None


@pytest.mark.parametrize("description", [
    "Questions: info@example.test",
    "Do not email applications to jobs@example.test. Apply online only.",
    "Applications are closed. jobs@example.test",
    "We do not accept CVs by email: jobs@example.test",
    "Apply online. For general questions: info@example.test",
    "Apply online; privacy requests: privacy@example.test",
    "Send resume questions to support@example.test",
    "Recruiting system messages come from no-reply@example.test",
])
def test_hiring_email_rejects_negative_closed_unrelated_and_nonhiring_addresses(description):
    assert hiring_email(description) is None


def test_play_defaults_to_preparation_with_bounded_authority():
    request = CareerPlay(actor="tester")
    assert request.mode == "prepare" and not request.include_cold_email
    assert request.max_age_hours == 72 and request.expires_in_hours == 24
    assert set(request.allowed_hosts) == EXTERNAL_APPLICATION_HOSTS
    assert request.max_applications_per_day == 3


@pytest.mark.parametrize("changes", [
    {"max_applications_per_day": 0}, {"max_applications_per_day": 11},
    {"max_age_hours": 0}, {"max_age_hours": 169}, {"expires_in_hours": 169},
    {"min_score": 101}, {"mode": "apply", "allowed_hosts": []},
    {"allowed_hosts": ["*.ashbyhq.com"]},
    {"allowed_hosts": ["https://jobs.ashbyhq.com"]}, {"allowed_hosts": ["evil.test"]},
    {"answers": {"question": "x" * 4001}}, {"unreviewed_field": True},
])
def test_play_rejects_unbounded_or_unspecified_destinations(changes):
    with pytest.raises(ValidationError):
        CareerPlay(actor="tester", **changes)


def test_play_scope_normalizes_supported_hosts_and_requires_explicit_email_opt_in():
    request = CareerPlay(actor="tester", mode="apply", allowed_hosts=[HOST.upper(), HOST])
    assert request.allowed_hosts == [HOST]
    email_only = CareerPlay(actor="tester", mode="apply", include_cold_email=True, allowed_hosts=[])
    assert email_only.include_cold_email and not email_only.allowed_hosts
