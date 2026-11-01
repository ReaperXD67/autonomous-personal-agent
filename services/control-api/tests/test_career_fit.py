from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app import career_autopilot
from app.application_browser import canonical_hash
from app.career import SCORING_POLICY_VERSION, diagnose_opportunity, score_opportunity
from app.career_autopilot import PROFILE_SCOPE_FIELDS, eligibility_reason, profile_hash
from app.career_store import CareerStore
from app.marketing_store import MarketingStore

NOW = datetime(2026, 11, 2, 12, tzinfo=UTC)


def profile(**changes):
    return {
        "desired_titles": ["Software Engineer"], "skills": ["Python", "PostgreSQL", "Docker"],
        "required_keywords": [], "excluded_keywords": ["Senior"], "locations": ["India"],
        "remote_only": False, "employment_types": ["FullTime"], "max_age_hours": 72,
        "min_score": 75, "active": True, **changes,
    }


def job(**changes):
    return {
        "source": "ashby", "company": "Synthetic", "title": "Software Engineer",
        "description": "Build Python, PostgreSQL and Docker services.", "location": "India",
        "remote": False, "employment_type": "FullTime", "status": "new",
        "published_at": NOW - timedelta(hours=1), "published_at_basis": "published",
        "source_url": "https://jobs.ashbyhq.com/synthetic/role-1",
        "apply_url": "https://jobs.ashbyhq.com/synthetic/role-1/application", **changes,
    }


@pytest.mark.parametrize("age", [1, 25, 49, 71, 72])
def test_equally_relevant_roles_keep_fit_throughout_the_authorized_age_window(age):
    result = score_opportunity(job(published_at=NOW - timedelta(hours=age)), profile(), now=NOW)
    assert result is not None and result["score"] >= 75
    reference = score_opportunity(job(), profile(), now=NOW)
    assert result["score"] == reference["score"]
    assert result["fit_report"]["publication"]["within_window"]
    assert result["fit_report"]["model_calls"] == 0


@pytest.mark.parametrize("posted,reason", [
    (NOW + timedelta(microseconds=1), "future_date"),
    (NOW - timedelta(hours=72, microseconds=1), "outside_freshness_window"),
    (None, "invalid_date"), ("2026-11-02T12:00Z", "invalid_date"),
    (datetime(2026, 11, 2), "invalid_date"),
])
def test_date_diagnostics_preserve_hard_freshness_and_reject_unparsed_dates(posted, reason):
    report = diagnose_opportunity(job(published_at=posted), profile(), now=NOW)
    assert report["filter_reason"] == reason
    assert not report["publication"]["within_window"]
    assert score_opportunity(job(published_at=posted), profile(), now=NOW) is None


@pytest.mark.parametrize("saved,description,matched", [
    ("Java", "Build JavaScript clients", False),
    ("SQL", "Use NoSQL and SQLite", False),
    ("React", "Build reactive systems", False),
    ("Python", "Use PyTorch tooling", False),
    ("Python", "Use Python3 services", True),
    ("PostgreSQL", "Operate Postgres databases", True),
    ("Next.js", "Build NextJS websites", True),
    ("C++", "Write C++ services", True),
    ("LLM", "Deploy large language models", True),
])
def test_skills_use_literal_boundaries_and_only_explicit_aliases(saved, description, matched):
    report = diagnose_opportunity(job(description=description), profile(skills=[saved]), now=NOW)
    assert report["components"]["skills"]["matched"] == ([saved] if matched else [])


def test_alias_duplicates_cannot_inflate_the_skill_component():
    report = diagnose_opportunity(job(description="Use JavaScript and Postgres."), profile(
        skills=["JavaScript", "JS", "PostgreSQL", "Postgres"],
    ), now=NOW)
    assert report["components"]["skills"]["matched"] == ["JavaScript", "PostgreSQL"]
    assert report["components"]["skills"]["points"] < 33


def test_missing_terms_are_observation_gaps_and_do_not_invent_candidate_requirements():
    report = diagnose_opportunity(job(), profile(skills=["Python", "Kubernetes"]), now=NOW)
    assert report["components"]["skills"]["unobserved"] == ["Kubernetes"]
    assert "not inferred candidate gaps" in report["limitations"]
    assert not any(key in report for key in ("experience_years", "education", "work_authorization"))


def test_required_keyword_boundary_cannot_infer_java_from_javascript():
    report = diagnose_opportunity(
        job(description="JavaScript, Python, Postgres and Docker"),
        profile(required_keywords=["Java"]), now=NOW,
    )
    assert report["filter_reason"] == "missing_required_keywords"
    assert report["hard_filters"]["missing_required_keywords"] == ["Java"]


def test_unknown_publication_provenance_does_not_gain_verified_status_from_a_fit_score():
    report = diagnose_opportunity(job(published_at_basis="updated"), profile(), now=NOW)
    assert report["publication"]["basis"] == "updated"
    candidate = profile()
    run = {"state": "running", "expires_at": NOW + timedelta(hours=1),
           "profile_hash": profile_hash(candidate), "max_age_hours": 72, "min_score": 75}
    assert "verified posting date" in eligibility_reason(
        run, candidate, job(published_at_basis="updated"), now=NOW,
    )


def test_legacy_grants_cannot_silently_inherit_changed_scoring_semantics():
    candidate = profile()
    legacy_hash = canonical_hash({key: candidate.get(key) for key in PROFILE_SCOPE_FIELDS})
    assert legacy_hash != profile_hash(candidate)
    run = {"state": "running", "expires_at": NOW + timedelta(hours=1),
           "profile_hash": legacy_hash, "max_age_hours": 72, "min_score": 75}
    assert "Profile changed" in eligibility_reason(run, candidate, job(), now=NOW)


def test_policy_version_change_invalidates_an_existing_grant(monkeypatch):
    candidate = profile()
    monkeypatch.setattr(career_autopilot, "SCORING_POLICY_VERSION", SCORING_POLICY_VERSION - 1)
    old_hash = profile_hash(candidate)
    monkeypatch.setattr(career_autopilot, "SCORING_POLICY_VERSION", SCORING_POLICY_VERSION)
    assert old_hash != profile_hash(candidate)


def test_current_fit_projection_strips_internal_preferences_and_preserves_historical_score():
    row = {**job(), "score": 64, "matching_preferences": profile()}
    result = CareerStore._opportunity_projection(row)
    assert "matching_preferences" not in result
    assert result["score"] == 64
    assert result["fit_report"]["score"] >= 75
    assert result["fit_report"]["version"] == SCORING_POLICY_VERSION


def test_search_diagnostics_account_for_every_normalized_record_without_model_calls(monkeypatch):
    from app import job_worker

    class Clock:
        @staticmethod
        def now(_timezone):
            return NOW

    records = [job(), job(published_at=NOW - timedelta(hours=73)),
               job(location="Remote — United States", remote=True),
               job(title="Office Administrator"), job(description="Documentation only"),
               job(title="Senior Software Engineer")]
    store = Mock(spec=MarketingStore)
    store.get_profile.return_value = {
        **profile(), "source_config": {"arbeitnow": False, "ashby_boards": ["synthetic"]},
        "resume_text": "",
    }
    store.save_opportunities.return_value = {"new": 1, "updated": 0, "auto_prepare_ids": []}
    monkeypatch.setattr(job_worker, "fetch_ashby", lambda _board: records)
    monkeypatch.setattr(job_worker, "datetime", Clock)
    output = job_worker.execute_career_task({
        "kind": "career.search", "payload": {"profile_id": str(uuid4())},
    }, store)
    assert output["filter_counts"]["matched"] == 1
    for reason in ("outside_freshness_window", "location_mismatch", "title_mismatch",
                   "below_fit_threshold", "excluded_keyword"):
        assert output["filter_counts"][reason] == 1
    assert sum(output["filter_counts"].values()) == output["fetched"] == len(records)
    assert output["sources_attempted"] == output["sources_succeeded"] == 1
    assert output["diagnostics_scope"] == "normalized_source_records"
    assert output["model_calls"] == 0 and output["scoring_version"] == SCORING_POLICY_VERSION
    assert "resume_text" not in output
    store.create_task.assert_not_called()
