import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.career_source_routes import resolve_source
from app.career_sources import (
    CareerDiscoveryLead,
    CareerSourceResolve,
    normalize_source_boards,
    normalize_yc_companies,
    resolve_career_source,
)

ATS = "https://jobs.ashbyhq.com/example/role-1/application?utm_source=linkedin"
LINKEDIN = "https://www.linkedin.com/jobs/view/backend-engineer-at-example-1234567890"
YC = "https://www.ycombinator.com/companies/example/jobs/AbC123-backend-engineer"


@pytest.mark.parametrize("source", [
    LINKEDIN, "https://linkedin.com/jobs/view/1234567890?trk=public_jobs",
    "https://in.linkedin.com:443/jobs/view/backend-engineer-at-example-1234567890/",
])
def test_linkedin_intake_keeps_discovery_identity_and_separately_supplied_ats(source):
    result = resolve_career_source(source, employer_url=ATS)
    assert result.provider == "ashby" and result.source_config_key == "ashby_boards"
    assert result.board == "example" and result.board_url == "https://jobs.ashbyhq.com/example"
    assert result.posting_url == "https://jobs.ashbyhq.com/example/role-1"
    assert result.discovery_platform == "linkedin"
    assert result.discovery_url == "https://www.linkedin.com/jobs/view/1234567890"
    assert result.employer_url == result.posting_url
    assert result.fetch_performed is False and result.model_calls == 0
    assert "entire employer board" in result.notice and "does not connect" in result.notice


def test_linkedin_without_reviewed_employer_link_cannot_create_a_source():
    with pytest.raises(ValueError, match="employer_url"):
        resolve_career_source(LINKEDIN)
    with pytest.raises(HTTPException) as exc:
        resolve_source(CareerSourceResolve(url=LINKEDIN))
    assert exc.value.status_code == 422 and "not connected" in exc.value.detail


@pytest.mark.parametrize("source", [
    "https://www.linkedin.com/jobs/search/?keywords=intern",
    "https://www.linkedin.com/redir/redirect?url=https://jobs.ashbyhq.com/example",
    "https://www.linkedin.com/jobs/view/backend-engineer-without-id",
    "https://www.linkedin.com/jobs/view/role_1234567890",
    "https://www.linkedin.com/jobs/view/1234567890/apply",
    "https://www.linkedin.com/jobs/view/1234567890/extra",
    "https://www.linkedin.com/jobs/view/%31%32%33",
    "https://www.linkedin.com/jobs%2fview/123",
    "https://www.linkedin.com//jobs/view/123",
    "https://uk.linkedin.com/jobs/view/123",
    "https://www.linkedin.com.evil.test/jobs/view/123",
    "https://user:password@www.linkedin.com/jobs/view/123",
    "https://www.linkedin.com:444/jobs/view/123",
    "https://www.linkedin.com/jobs/view/123#apply",
    "https://www.linkedin.com/jobs/view/123#",
    "http://www.linkedin.com/jobs/view/123",
])
def test_platform_intake_rejects_redirects_ambiguous_paths_and_unreviewed_origins(source):
    with pytest.raises(ValueError):
        resolve_career_source(source, employer_url=ATS)


@pytest.mark.parametrize("employer", [
    LINKEDIN, YC, "https://account.ycombinator.com/login",
    "https://example.test/careers", "http://jobs.lever.co/example/role-1",
    "https://user@jobs.lever.co/example/role-1",
    "https://jobs.ashbyhq.com/example/role-1#form",
    "https://jobs.ashbyhq.com/example%2Fother/role-1",
    "https://jobs.ashbyhq.com/example/../other",
    "https://jobs.lever.co/example/role-1;redirect=other",
])
def test_paired_employer_url_cannot_delegate_to_another_platform_or_arbitrary_destination(employer):
    with pytest.raises(ValueError):
        resolve_career_source(LINKEDIN, employer_url=employer)
    with pytest.raises(ValidationError):
        CareerDiscoveryLead(platform="linkedin", source_url=LINKEDIN, employer_url=employer)


@pytest.mark.parametrize("source,posting", [
    ("https://www.ycombinator.com/companies/example", None),
    ("https://ycombinator.com/companies/example/jobs/", None),
    (YC + "?utm_source=public_jobs", YC),
])
def test_direct_yc_source_resolves_public_company_board_with_manual_application_notice(
    source, posting,
):
    result = resolve_career_source(source)
    assert result.provider == "yc" and result.source_config_key == "yc_companies"
    assert result.board == "example"
    assert result.board_url == "https://www.ycombinator.com/companies/example/jobs"
    assert result.posting_url == posting
    assert result.fetch_performed is False and result.model_calls == 0
    assert "submit manually" in result.notice and "verify" in result.notice
    assert result.employer_url is None and result.discovery_platform is None


@pytest.mark.parametrize("source", [
    "https://www.ycombinator.com/jobs/123", "https://account.ycombinator.com/companies/example",
    "https://www.ycombinator.com/companies/Example", "https://www.ycombinator.com/companies/has_underscore",
    "https://www.ycombinator.com/companies/example/jobs/role/extra",
    "https://www.ycombinator.com/companies/example/jobs/role#apply",
    "https://www.ycombinator.com/companies/example%2Fother/jobs/role",
])
def test_yc_invalid_paths_are_rejected(source):
    with pytest.raises(ValueError):
        resolve_career_source(source)


def test_yc_can_preserve_its_exact_discovery_reference_alongside_a_supported_employer_link():
    result = resolve_source(CareerSourceResolve(
        url=YC + "?utm_source=directory", employer_url="https://jobs.lever.co/example/role-1/apply",
    ))
    assert result.provider == "lever" and result.source_config_key == "lever_boards"
    assert result.discovery_platform == "yc" and result.discovery_url == YC
    assert result.employer_url == "https://jobs.lever.co/example/role-1"


def test_discovery_lead_is_a_canonical_reference_without_authority_or_network_claims():
    lead = CareerDiscoveryLead(platform="linkedin", source_url=LINKEDIN + "?trk=jobs",
                               employer_url=ATS)
    assert lead.model_dump() == {
        "platform": "linkedin", "source_url": "https://www.linkedin.com/jobs/view/1234567890",
        "employer_url": "https://jobs.ashbyhq.com/example/role-1",
    }
    yc = CareerDiscoveryLead(platform="yc", source_url="https://ycombinator.com/companies/example/",
                             employer_url="https://jobs.eu.lever.co/example/role-1/apply")
    assert yc.source_url == "https://www.ycombinator.com/companies/example"
    assert yc.employer_url == "https://jobs.eu.lever.co/example/role-1"
    with pytest.raises(ValidationError):
        CareerDiscoveryLead(platform="linkedin", source_url=YC, employer_url=ATS)
    with pytest.raises(ValidationError):
        CareerDiscoveryLead(platform="yc", source_url=LINKEDIN, employer_url=ATS)
    with pytest.raises(ValidationError):
        CareerDiscoveryLead(platform="linkedin", source_url=LINKEDIN, employer_url=ATS,
                            submit_authorized=True)


def test_company_normalization_is_bounded_deduplicated_and_rejects_cross_platform_links():
    assert normalize_yc_companies([
        "Example", "https://www.ycombinator.com/companies/example/jobs", "other-company",
        "https://ycombinator.com/companies/other-company/jobs/P123-role?utm_source=directory", "",
    ]) == ["example", "other-company"]
    for values in (["../example"], [ATS], [LINKEDIN], ["example_unsafe"],
                   ["https://www.ycombinator.com/companies/example/jobs/role/extra"],
                   ["https://www.ycombinator.com/companies/example#jobs"],
                   [f"company-{index}" for index in range(31)]):
        with pytest.raises(ValueError):
            normalize_yc_companies(values)
    with pytest.raises(ValueError, match="yc_companies"):
        normalize_source_boards([YC], config_key="ashby_boards")


def test_an_ats_url_cannot_silently_ignore_a_second_unrelated_employer_url():
    with pytest.raises(ValueError, match="pairs only"):
        resolve_career_source(ATS, employer_url="https://jobs.lever.co/other/role-1")
