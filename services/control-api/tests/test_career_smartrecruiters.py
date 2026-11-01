from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app import career_smartrecruiters as smart
from app import job_worker
from app.career_autopilot import allowed_url
from app.career_autopilot_routes import overview
from app.career_models import CareerSourceConfig
from app.career_sources import resolve_career_source
from app.marketing_store import MarketingStore

NOW = datetime(2026, 11, 2, 12, tzinfo=UTC)


def listing(identifier="123", **changes):
    return {"id": identifier, "company": {"identifier": "Example", "name": "Example Ltd"},
            "name": "Software Engineer Intern", "releasedDate": NOW.isoformat(), **changes}


def detail(identifier="123", **changes):
    return {**listing(identifier), "active": True,
            "location": {"city": "Bengaluru", "country": "IN"},
            "typeOfEmployment": {"label": "Internship"}, "jobAd": {"sections": {
                "jobDescription": {"text": "<p>Build Python and FastAPI services.</p>"},
                "qualifications": {"text": "<p>Current student; PostgreSQL projects.</p>"},
            }}, "ref": "http://127.0.0.1/private", "applyUrl": "https://evil.test/steal", **changes}


def fake_source(monkeypatch, listings, details=None, total=None):
    requested = []

    def read(board, identifier=None, **_kwargs):
        requested.append((board, identifier))
        if identifier is None:
            return {"content": listings, "totalFound": len(listings) if total is None else total}
        value = (details or {}).get(identifier, detail(identifier))
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(smart, "_read_public", read)
    return requested


def test_normalizes_public_evidence_without_following_provider_urls(monkeypatch):
    requested = fake_source(monkeypatch, [listing()])
    coverage = {}
    rows = smart.fetch_smartrecruiters("Example", now=NOW, coverage=coverage)
    assert requested == [("Example", None), ("Example", "123")]
    assert rows[0]["source"] == "smartrecruiters"
    assert rows[0]["source_key"] == "Example:123"
    assert rows[0]["source_url"] == rows[0]["apply_url"] == (
        "https://jobs.smartrecruiters.com/Example/123")
    assert "India" in rows[0]["location"] and rows[0]["employment_type"] == "Intern"
    assert rows[0]["published_at_basis"] == "published" and rows[0]["published_at"] == NOW
    assert "<p>" not in rows[0]["description"] and "Python" in rows[0]["description"]
    assert coverage["model_calls"] == 0 and not coverage["submission_supported"]
    assert not coverage["truncated"] and coverage["returned"] == 1
    assert not allowed_url(rows[0]["apply_url"], ["jobs.ashbyhq.com"])


@pytest.mark.parametrize("row", [
    listing(releasedDate=None), listing(releasedDate="invalid"),
    listing(releasedDate=(NOW + timedelta(minutes=1)).isoformat()),
    listing(releasedDate=(NOW - timedelta(hours=169)).isoformat()),
    listing(company={"identifier": "Other"}), listing(active=False),
    listing(identifier="../other"),
])
def test_invalid_stale_future_closed_or_cross_company_listings_never_fetch_detail(monkeypatch, row):
    requested = fake_source(monkeypatch, [row])
    assert smart.fetch_smartrecruiters("Example", now=NOW) == []
    assert requested == [("Example", None)]


@pytest.mark.parametrize("changes", [
    {"active": False}, {"company": {"identifier": "Other"}}, {"id": "other"},
    {"releasedDate": "invalid"}, {"releasedDate": (NOW - timedelta(days=8)).isoformat()},
    {"releasedDate": (NOW + timedelta(hours=1)).isoformat()}, {"jobAd": {}},
])
def test_detail_revalidation_and_nonempty_description_are_required(monkeypatch, changes):
    fake_source(monkeypatch, [listing()], {"123": detail(**changes)})
    assert smart.fetch_smartrecruiters("Example", now=NOW) == []


def test_detail_and_page_limits_are_visible_and_duplicate_records_do_not_spend_calls(monkeypatch):
    requested = fake_source(monkeypatch, [listing(str(i)) for i in range(80)], total=800)
    coverage = {}
    rows = smart.fetch_smartrecruiters("Example", now=NOW, coverage=coverage)
    assert len(requested) == 11 and len(rows) == 10
    assert coverage["listed"] == 50 and coverage["truncated"]
    assert coverage["reported_total"] == 800 and coverage["details_fetched"] == 10
    requested = fake_source(monkeypatch, [listing(), listing()])
    assert len(smart.fetch_smartrecruiters("Example", now=NOW)) == 1
    assert len(requested) == 2


def test_oversized_or_inconsistent_provider_pages_never_claim_complete_coverage(monkeypatch):
    fake_source(monkeypatch, [listing(str(i), active=False) for i in range(51)], total=50)
    coverage = {}
    assert smart.fetch_smartrecruiters("Example", now=NOW, coverage=coverage) == []
    assert coverage["truncated"]
    fake_source(monkeypatch, [listing(active=False)], total=0)
    assert smart.fetch_smartrecruiters("Example", now=NOW, coverage=coverage) == []
    assert coverage["truncated"]


def test_requested_titles_are_prioritized_before_the_detail_budget(monkeypatch):
    raw = [listing(str(i), name="Marketing Manager") for i in range(15)]
    raw.append(listing("999", name="Software Engineer Intern"))
    requested = fake_source(monkeypatch, raw)
    coverage = {}
    smart.fetch_smartrecruiters("Example", now=NOW, country="in",
                              search_titles=["Software Engineer"], coverage=coverage)
    assert requested[1] == ("Example", "999")
    assert coverage["country_filter"] == "in" and coverage["title_priority_applied"]


def test_country_hint_never_narrows_mixed_or_unknown_geographic_preferences():
    assert smart.smartrecruiters_country_hint(["India", "Bangalore", "Remote"]) == "in"
    assert smart.smartrecruiters_country_hint(["India", "Singapore"]) is None
    assert smart.smartrecruiters_country_hint(["India", "Worldwide"]) is None
    assert smart.smartrecruiters_country_hint(["Bangalore"]) is None
    assert smart.smartrecruiters_country_hint([]) is None


def test_transport_constructs_only_reviewed_paths_and_refuses_redirects(monkeypatch):
    requested = []

    class Response:
        def __init__(self, url):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return self.url

        def read(self, limit):
            assert limit == smart.MAX_BYTES + 1
            return b'{"content":[]}'

    class Opener:
        def open(self, request, timeout):
            assert timeout == 12
            requested.append(request.full_url)
            return Response(request.full_url)

    monkeypatch.setattr(smart, "build_opener", lambda *_args: Opener())
    smart._read_public("Example", country="in")
    smart._read_public("Example", "123")
    assert requested == [
        "https://api.smartrecruiters.com/v1/companies/Example/postings?limit=50&offset=0&country=in",
        "https://api.smartrecruiters.com/v1/companies/Example/postings/123",
    ]
    with pytest.raises(ValueError, match="refused"):
        smart._NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test")
    with pytest.raises(ValueError):
        smart._read_public("../secret")
    with pytest.raises(ValueError):
        smart._read_public("Example", country="IN&other=bad")


def test_detail_errors_are_partial_coverage_and_interruption_propagates(monkeypatch):
    fake_source(monkeypatch, [listing()], {"123": RuntimeError("Provider unavailable")})
    coverage = {}
    assert smart.fetch_smartrecruiters("Example", now=NOW, coverage=coverage) == []
    assert coverage["detail_failures"] == 1 and coverage["truncated"]
    interrupt = Mock(side_effect=RuntimeError("Interrupted"))
    with pytest.raises(RuntimeError, match="Interrupted"):
        smart.fetch_smartrecruiters("Example", now=NOW, checkpoint=interrupt)


@pytest.mark.parametrize("url", [
    "https://careers.smartrecruiters.com/Example",
    "https://jobs.smartrecruiters.com/Example/123-engineering-intern?utm_source=linkedin",
    "https://www.smartrecruiters.com/Example/123-engineering-intern",
])
def test_source_intake_is_read_only_and_explicitly_manual_submission(url):
    result = resolve_career_source(url)
    assert result.provider == "smartrecruiters"
    assert result.source_config_key == "smartrecruiters_boards"
    assert result.board == "Example" and result.model_calls == 0
    assert "submit manually" in result.notice and not result.fetch_performed
    config = CareerSourceConfig(arbeitnow=False, smartrecruiters_boards=[url])
    assert config.smartrecruiters_boards == ["Example"]
    with pytest.raises(ValidationError, match="matching source"):
        CareerSourceConfig(ashby_boards=[url])


@pytest.mark.parametrize("url", [
    "https://careers.smartrecruiters.com/Example/123",
    "https://jobs.smartrecruiters.com/Example/123/apply",
    "https://jobs.smartrecruiters.com.evil.test/Example",
    "https://jobs.smartrecruiters.com/Example%2fother/123",
])
def test_intake_refuses_unreviewed_smartrecruiters_paths(url):
    with pytest.raises(ValueError):
        resolve_career_source(url)


def test_worker_uses_current_policy_path_and_exposes_partial_source_coverage(monkeypatch):
    store = Mock(spec=MarketingStore)
    profile_id = uuid4()
    store.get_profile.return_value = {
        "source_config": {"arbeitnow": False, "smartrecruiters_boards": ["Example"]},
        "resume_text": "", "max_age_hours": 72,
    }
    store.save_opportunities.return_value = {"new": 0, "updated": 0, "auto_prepare_ids": []}

    def fetch(board, **kwargs):
        assert board == "Example" and kwargs["max_age_hours"] == 72
        kwargs["checkpoint"]()
        kwargs["coverage"].update({"provider": "smartrecruiters", "truncated": True})
        return []

    monkeypatch.setattr(job_worker, "fetch_smartrecruiters", fetch)
    result = job_worker.execute_career_task({
        "kind": "career.search", "payload": {"profile_id": str(profile_id)},
    }, store)
    assert result["sources_succeeded"] == 1
    assert result["source_coverage"][0]["truncated"]
    store.create_task.assert_not_called()


def test_smartrecruiters_only_mission_does_not_claim_automatic_application_readiness(monkeypatch):
    import app.career_autopilot_routes as routes

    store = Mock()
    store.overview.return_value = {"runs": [], "items": []}
    store.list_profiles.return_value = [{
        "id": uuid4(), "resume_present": True,
        "application_identity": {"first_name": "Synthetic", "last_name": "Applicant",
                                 "email": "candidate@example.test"},
        "source_config": {"smartrecruiters_boards": ["Example"], "arbeitnow": False},
    }]
    request = Mock()
    request.app.state.career_autopilot = store
    monkeypatch.setattr(routes, "get_settings", lambda: Mock(gmail_enabled=False,
                                                            mail_transport="disabled"))
    result = overview(request)
    assert result["readiness"][0]["can_prepare"] is True
    assert result["readiness"][0]["can_apply"] is False
