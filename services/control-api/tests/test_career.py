from datetime import UTC, datetime, timedelta

import pytest

from app.career import (
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
