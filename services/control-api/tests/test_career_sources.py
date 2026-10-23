from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app import career, job_worker
from app.auth import require_api_token
from app.career import fetch_lever
from app.career_models import CareerSourceConfig
from app.career_source_routes import resolve_source, router
from app.career_sources import CareerSourceResolve, resolve_career_source
from app.marketing_store import MarketingStore


@pytest.mark.parametrize("url,provider,key,board,posting", [
    ("https://jobs.ashbyhq.com/example", "ashby", "ashby_boards", "example", None),
    ("https://jobs.ashbyhq.com/Example/role-1/application?utm_source=linkedin#form",
     "ashby", "ashby_boards", "Example", "https://jobs.ashbyhq.com/Example/role-1"),
    ("https://job-boards.greenhouse.io/example/jobs/123?gh_src=yc",
     "greenhouse", "greenhouse_boards", "example",
     "https://job-boards.greenhouse.io/example/jobs/123"),
    ("https://boards.greenhouse.io/example", "greenhouse", "greenhouse_boards", "example", None),
    ("https://boards.greenhouse.io/embed/job_app?for=example&token=123",
     "greenhouse", "greenhouse_boards", "example",
     "https://job-boards.greenhouse.io/example/jobs/123"),
    ("https://boards.greenhouse.io/embed/job_board?for=example",
     "greenhouse", "greenhouse_boards", "example", None),
    ("https://jobs.lever.co/example/role-1/apply?lever-source=LinkedIn",
     "lever", "lever_boards", "example", "https://jobs.lever.co/example/role-1"),
    ("https://jobs.eu.lever.co/example/role-1", "lever", "lever_eu_boards", "example",
     "https://jobs.eu.lever.co/example/role-1"),
])
def test_resolves_reviewed_employer_links_without_model_or_network(
    url, provider, key, board, posting,
):
    result = resolve_career_source(url)
    assert (result.provider, result.source_config_key, result.board, result.posting_url) == (
        provider, key, board, posting,
    )
    assert result.fetch_performed is False and result.model_calls == 0
    assert result.scope == "employer_board"
    assert "entire employer board" in result.notice
    assert "?" not in result.board_url and "#" not in result.board_url


@pytest.mark.parametrize("url", [
    "http://jobs.ashbyhq.com/example", "https://jobs.ashbyhq.com.evil.test/example",
    "https://jobs.ashbyhq.com@evil.test/example", "https://evil@jobs.ashbyhq.com/example",
    "https://jobs.ashbyhq.com:444/example", "https://127.0.0.1/example",
    "https://jobs.ashbyhq.com/example%2fother", "https://jobs.ashbyhq.com/../example",
    "https://jobs.ashbyhq.com/example\\other", "https://jobs.ashbyhq.com/ex\nample",
    "https://jobs.ashbyhq.com/", "https://jobs.lever.co/example/role/extra/again",
    "https://boards.greenhouse.io/example/123", "https://boards.greenhouse.io/embed/job_app",
    "https://boards.greenhouse.io/embed/job_app?for=example&for=other&token=123",
    "https://boards.greenhouse.io/embed/job_app?for=example&token=123&token=456",
    "https://jobs.lever.co/example/role/application", "https://jobs.ashbyhq.com/example/role/apply",
])
def test_rejects_unreviewed_origins_and_ambiguous_paths(url):
    with pytest.raises(ValueError):
        resolve_career_source(url)


@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/jobs/view/123", "https://www.ycombinator.com/companies/example/jobs",
    "https://www.workatastartup.com/jobs/123",
])
def test_platform_links_have_actionable_employer_import_guidance(url):
    with pytest.raises(ValueError, match="employer's application link"):
        resolve_career_source(url)


def test_config_normalizes_urls_and_slugs_before_persisting():
    config = CareerSourceConfig(
        arbeitnow=False,
        ashby_boards=["Example", "https://jobs.ashbyhq.com/example/role-1", "Other"],
        greenhouse_boards=["https://job-boards.greenhouse.io/green/jobs/123"],
        lever_boards=["https://jobs.lever.co/global/role-1"],
        lever_eu_boards=["https://jobs.eu.lever.co/europe/role-2"],
    )
    assert config.ashby_boards == ["Example", "Other"]
    assert config.greenhouse_boards == ["green"]
    assert config.lever_boards == ["global"]
    assert config.lever_eu_boards == ["europe"]
    assert CareerSourceConfig(arbeitnow=False, lever_eu_boards=["europe"]).lever_eu_boards
    with pytest.raises(ValidationError, match="lever_eu_boards"):
        CareerSourceConfig(lever_boards=["https://jobs.eu.lever.co/europe"])
    with pytest.raises(ValidationError, match="30 employer boards"):
        CareerSourceConfig(ashby_boards=[f"board-{index}" for index in range(31)])
    with pytest.raises(ValidationError):
        CareerSourceConfig(ashby_boards=["x" * 101])


def test_resolver_endpoint_requires_authentication_and_returns_no_fetch_claim():
    assert router.routes[0].dependencies[0].dependency is require_api_token
    result = resolve_source(CareerSourceResolve(url="https://jobs.ashbyhq.com/example/role-1"))
    assert result.source_config_key == "ashby_boards" and result.fetch_performed is False
    with pytest.raises(HTTPException) as exc:
        resolve_source(CareerSourceResolve(url="https://www.linkedin.com/jobs/view/123"))
    assert exc.value.status_code == 422 and "not connected" in exc.value.detail


def test_eu_lever_reads_exact_reviewed_region_and_keeps_region_identity(monkeypatch):
    requested = []

    def read(url):
        requested.append(url)
        return [{
            "id": "role-1", "createdAt": datetime.now(UTC).isoformat(),
            "hostedUrl": "https://jobs.eu.lever.co/example/role-1",
            "applyUrl": "https://jobs.eu.lever.co/example/role-1/apply",
            "text": "Engineering Intern", "categories": {"commitment": "Intern"},
        }]

    monkeypatch.setattr(career, "_read_json", read)
    rows = fetch_lever("example", region="eu")
    assert requested == ["https://api.eu.lever.co/v0/postings/example?mode=json"]
    assert rows[0]["source_key"] == "eu:role-1"
    assert rows[0]["source"] == "lever" and rows[0]["employment_type"] == "Intern"
    assert fetch_lever("example") == []  # global board cannot claim EU listings
    assert fetch_lever("other", region="eu") == []  # cross-board links are rejected
    with pytest.raises(ValueError, match="region"):
        fetch_lever("example", region="unreviewed")
    assert "api.eu.lever.co" in career.SOURCE_HOSTS


def test_eu_only_source_is_scanned_through_existing_career_task(monkeypatch):
    store = Mock(spec=MarketingStore)
    profile_id = uuid4()
    store.get_profile.return_value = {
        "source_config": {"arbeitnow": False, "lever_eu_boards": ["example"]},
        "resume_text": "",
    }
    store.save_opportunities.return_value = {"new": 0, "updated": 0, "auto_prepare_ids": []}
    fetch = Mock(return_value=[])
    monkeypatch.setattr(job_worker, "fetch_lever", fetch)
    output = job_worker.execute_career_task({
        "kind": "career.search", "payload": {"profile_id": str(profile_id)},
    }, store)
    fetch.assert_called_once_with("example", region="eu")
    assert output["sources_succeeded"] == 1
    store.save_opportunities.assert_called_once_with(profile_id, [])
    store.create_task.assert_not_called()
