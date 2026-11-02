import json
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app import job_worker
from app.career_models import CareerEligibilityFacts, CareerProfileUpdate, CareerSourceConfig
from app.career_store import CareerStore
from app.marketing_store import MarketingStore


def test_yc_can_be_the_only_discovery_source() -> None:
    config = CareerSourceConfig(arbeitnow=False, yc_companies=[
        "https://www.ycombinator.com/companies/peakflo/jobs",
    ])
    assert config.yc_companies == ["peakflo"]


@pytest.mark.parametrize("value", ["true", "false", 1, 0, [], {}])
def test_screening_confirmation_requires_a_real_boolean(value) -> None:
    with pytest.raises(ValidationError):
        CareerEligibilityFacts(india_authorized_without_sponsorship=value)


def test_old_profile_update_does_not_request_fact_replacement() -> None:
    request = CareerProfileUpdate(
        name="Test mission", candidate_name="Alex Rivera", desired_titles=["Software Engineer"],
        source_config={"arbeitnow": False, "yc_companies": ["peakflo"]}, actor="test:owner",
    )
    assert request.eligibility_facts is None
    assert CareerEligibilityFacts().india_authorized_without_sponsorship is None


def test_current_qualification_projection_discards_private_resume_evidence() -> None:
    row = {
        "title": "Software Engineer", "company": "Example", "location": "India",
        "description": "Requirements: Must have three years of professional Python experience.",
        "source": "lever", "source_url": "https://jobs.lever.co/example/role",
        "apply_url": "https://jobs.lever.co/example/role", "remote": False,
        "published_at": datetime.now(UTC), "published_at_basis": "published",
        "eligibility_evidence": {
            "resume_text": "PRIVATE_RESUME_SENTINEL\nBuilt Python projects with Docker.",
            "eligibility_facts": {"india_authorized_without_sponsorship": True},
        },
    }
    projected = CareerStore._opportunity_projection(row)
    assert projected["eligibility"]["disposition"] == "review_required"
    encoded = json.dumps(projected, default=str)
    assert "PRIVATE_RESUME_SENTINEL" not in encoded
    assert "eligibility_evidence" not in projected
    assert "resume_text" not in encoded
    assert projected["eligibility"]["model_calls"] == 0


@pytest.mark.parametrize(("consumed", "failed_company", "expected_limits"), [
    ([10, 10, 0, 0], None, [10, 10, 0, 0]),
    ([7, 10, 3, 0, 0], 0, [10, 10, 3, 0, 0]),
    ([0, 10, 10, 0], 0, [10, 10, 10, 0]),
])
def test_worker_yc_budget_is_shared_across_companies_failures_and_list_only_scans(
    monkeypatch, consumed, failed_company, expected_limits,
) -> None:
    """A failed detail still spends capacity; a failed list spends no detail calls."""
    companies = [f"company-{index}" for index in range(len(consumed))]
    profile_id = uuid4()
    store = Mock(spec=MarketingStore)
    store.get_profile.return_value = {
        "source_config": {"arbeitnow": False, "yc_companies": companies},
        "resume_text": "", "max_age_hours": 72, "desired_titles": ["Software Engineer"],
    }
    store.save_opportunities.return_value = {"new": 0, "updated": 0, "auto_prepare_ids": []}
    observed = []
    hosted = Mock()
    local = Mock(side_effect=AssertionError("A source scan must not use inference"))

    def fetch(company, **kwargs):
        index = len(observed)
        assert company == companies[index]
        assert kwargs["max_age_hours"] == 72
        assert kwargs["search_titles"] == ["Software Engineer"]
        assert consumed[index] <= kwargs["detail_limit"]
        kwargs["checkpoint"]()
        observed.append(kwargs["detail_limit"])
        failed = index == failed_company
        kwargs["coverage"].update({
            "provider": "yc", "board": company, "details_fetched": consumed[index],
            "detail_failures": consumed[index] if failed else 0,
            "list_failures": int(failed and not consumed[index]),
            "detail_limit": kwargs["detail_limit"], "model_calls": 0,
        })
        if failed:
            raise RuntimeError("Synthetic source failure after reporting consumed capacity")
        return []

    monkeypatch.setattr(job_worker, "fetch_yc", fetch)
    monkeypatch.setattr(job_worker, "openrouter_client", hosted)
    monkeypatch.setattr(job_worker, "generate_application_draft_with_usage", local)
    result = job_worker.execute_career_task({
        "kind": "career.search", "payload": {"profile_id": str(profile_id)},
    }, store)
    assert observed == expected_limits
    assert sum(item["details_fetched"] for item in result["source_coverage"]) == 20
    assert len(result["source_coverage"]) == len(companies)
    assert result["sources_attempted"] == len(companies)
    assert result["sources_succeeded"] == len(companies) - int(failed_company is not None)
    assert len(result["source_warnings"]) == int(failed_company is not None)
    assert result["model_calls"] == 0 and result["fetched"] == 0
    assert observed[-1] == 0, "Later companies still get bounded list-only discovery"
    assert all(item["model_calls"] == 0 for item in result["source_coverage"])
    assert hosted.method_calls == []
    local.assert_not_called()
    store.start_inference_invocation.assert_not_called()
    store.create_task.assert_not_called()
