from datetime import UTC, datetime, timedelta

import pytest

from app import career
from app.career import (
    fetch_arbeitnow,
    fetch_ashby,
    fetch_greenhouse,
    fetch_lever,
    fetch_remotive,
    parse_application_draft,
    prioritize_opportunities,
    score_opportunity,
)
from app.career_models import CareerSourceConfig


def profile(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "desired_titles": ["Software Engineer", "Backend Intern"],
        "skills": ["Python", "PostgreSQL", "Docker"],
        "required_keywords": [],
        "excluded_keywords": ["Senior", "Staff"],
        "locations": ["India", "Remote"],
        "remote_only": False,
        "employment_types": ["FullTime", "Intern"],
        "max_age_hours": 72,
        "min_score": 45,
    }
    values.update(overrides)
    return values


def job(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "source": "ashby",
        "source_key": "role-1",
        "company": "Example",
        "title": "Backend Software Engineer",
        "location": "Remote — India",
        "description": "Build Python services using PostgreSQL and Docker.",
        "remote": True,
        "employment_type": "FullTime",
        "source_url": "https://jobs.ashbyhq.com/example/role-1",
        "apply_url": "https://jobs.ashbyhq.com/example/role-1/apply",
        "published_at": datetime.now(UTC) - timedelta(hours=2),
        "published_at_basis": "published",
    }
    values.update(overrides)
    return values


def test_fresh_evidence_based_match_scores_above_threshold() -> None:
    result = score_opportunity(job(), profile())
    assert result is not None
    assert result["score"] >= 80
    assert "published within 24 hours" in result["score_reasons"]


def test_old_or_excluded_roles_are_rejected() -> None:
    old = job(published_at=datetime.now(UTC) - timedelta(hours=90))
    senior = job(title="Senior Software Engineer")
    assert score_opportunity(old, profile()) is None
    assert score_opportunity(senior, profile()) is None


def test_remote_only_profile_rejects_onsite_role() -> None:
    onsite = job(remote=False, location="Bengaluru, India")
    assert score_opportunity(onsite, profile(remote_only=True)) is None


def test_required_keywords_require_all_evidence_terms():
    assert score_opportunity(job(), profile(required_keywords=["Python", "Kubernetes"])) is None
    assert score_opportunity(job(), profile(required_keywords=["Python", "PostgreSQL"])) is not None


@pytest.mark.parametrize("location", ["Remote — United States", "Remote", "", "Indiana, USA"])
def test_remote_flag_does_not_bypass_geographic_restrictions(location):
    assert score_opportunity(job(location=location), profile(locations=["India", "Remote"])) is None


@pytest.mark.parametrize("location", ["Worldwide", "Remote - Worldwide", "Global", "Anywhere"])
def test_explicit_worldwide_remote_role_can_match_country_preference(location):
    assert score_opportunity(job(location=location), profile(locations=["India"])) is not None


def test_worldwide_text_does_not_override_stated_restrictions_or_onsite_work():
    assert score_opportunity(
        job(location="Worldwide (US only)"), profile(locations=["India"]),
    ) is None
    assert score_opportunity(
        job(location="Worldwide", remote=False), profile(locations=["India"]),
    ) is None
    assert score_opportunity(job(location="Bengaluru, India", remote=False),
                             profile(locations=["India"])) is not None
    assert score_opportunity(job(location="Remote — US"), profile(locations=["Remote"])) is not None


@pytest.mark.parametrize("basis,label", [
    ("updated", "source updated"), ("unknown", "source timestamp"),
])
def test_scoring_does_not_label_update_or_unknown_timestamp_as_publication(basis, label):
    scored = score_opportunity(job(published_at_basis=basis), profile())
    assert scored is not None
    assert f"{label} within 24 hours" in scored["score_reasons"]
    assert "published within 24 hours" not in scored["score_reasons"]
    assert "Original publication time is not confirmed" in " ".join(scored["score_reasons"])


def test_remotive_is_opt_in_and_preserves_attribution_and_restrictions(monkeypatch):
    assert not CareerSourceConfig().remotive
    assert CareerSourceConfig(arbeitnow=False, remotive=True).remotive
    source_url = "https://remotive.com/remote-jobs/software-dev/engineer-123"

    def read(url):
        assert url == "https://remotive.com/api/remote-jobs?limit=100"
        return {"jobs": [{
            "id": 123, "url": source_url, "publication_date": "2026-09-20T12:00:00",
            "title": "Software Engineer", "company_name": "Example",
            "candidate_required_location": "United States", "job_type": "full_time",
            "description": "<p>Python services</p>",
        }]}

    monkeypatch.setattr(career, "_read_json", read)
    rows = fetch_remotive()
    assert len(rows) == 1
    assert rows[0]["source"] == "remotive"
    assert rows[0]["source_url"] == source_url and rows[0]["apply_url"] == source_url
    assert rows[0]["location"] == "United States" and rows[0]["remote"]
    assert rows[0]["employment_type"] == "FullTime"
    assert rows[0]["description"] == "Python services"
    assert rows[0]["published_at_basis"] == "published"


def test_remotive_rejects_missing_dates_off_domain_links_and_bounds_results(monkeypatch):
    valid = {"id": 123, "url": "https://remotive.com/remote-jobs/software-dev/engineer-123",
             "publication_date": "2026-09-20T12:00:00Z"}
    monkeypatch.setattr(career, "_read_json", lambda _url: {"jobs": [
        {**valid, "url": "https://remotive.com.evil.test/remote-jobs/role"},
        {**valid, "url": "https://user:pass@remotive.com/remote-jobs/role"},
        {**valid, "publication_date": ""}, *([valid] * 150),
    ]})
    assert len(fetch_remotive()) == 97


def test_each_source_exposes_timestamp_provenance(monkeypatch):
    timestamp = datetime.now(UTC).isoformat()
    responses = {
        "arbeitnow": {"data": [{"created_at": timestamp,
                                "url": "https://www.arbeitnow.com/jobs/example"}]},
        "ashby": {"jobs": [{"publishedAt": timestamp,
                            "jobUrl": "https://jobs.ashbyhq.com/example/role"}]},
        "greenhouse": {"jobs": [{"updated_at": timestamp,
                                 "absolute_url": "https://boards.greenhouse.io/example/jobs/1"}]},
        "lever": [{"createdAt": timestamp, "hostedUrl": "https://jobs.lever.co/example/role"}],
    }
    for name, fetch, expected_basis in (
        ("arbeitnow", lambda: fetch_arbeitnow(), "published"),
        ("ashby", lambda: fetch_ashby("example"), "published"),
        ("greenhouse", lambda: fetch_greenhouse("example"), "updated"),
        ("lever", lambda: fetch_lever("example"), "published"),
    ):
        monkeypatch.setattr(career, "_read_json", lambda _url, result=responses[name]: result)
        rows = fetch()
        assert len(rows) == 1 and rows[0]["published_at_basis"] == expected_basis


def test_auto_prepare_priority_prefers_score_then_freshness() -> None:
    older = datetime.now(UTC) - timedelta(hours=8)
    newer = datetime.now(UTC) - timedelta(hours=1)
    opportunities = [
        {"source_key": "low", "score": 70, "published_at": newer},
        {"source_key": "older-high", "score": 90, "published_at": older},
        {"source_key": "newer-high", "score": 90, "published_at": newer},
    ]

    ranked = prioritize_opportunities(opportunities)

    assert [item["source_key"] for item in ranked] == [
        "newer-high",
        "older-high",
        "low",
    ]


def test_career_source_config_requires_a_reviewed_source() -> None:
    with pytest.raises(ValueError, match="At least one reviewed career source"):
        CareerSourceConfig(
            arbeitnow=False,
            ashby_boards=[],
            greenhouse_boards=[],
        )


def test_application_draft_parser_accepts_fenced_json_and_bounds_lists() -> None:
    draft = parse_application_draft(
        """```json
        {
          "fit_summary": "evidence based",
          "evidence": ["one"],
          "honest_gaps": [],
          "resume_keywords": ["Python"],
          "cover_letter": "Hello"
        }
        ```"""
    )
    assert draft["fit_summary"] == "evidence based"
    assert draft["resume_keywords"] == ["Python"]
