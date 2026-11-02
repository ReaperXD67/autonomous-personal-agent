import html
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from app import career_yc as yc

NOW = datetime(2026, 11, 2, 12, tzinfo=UTC)


def job(identifier=1, title="Backend Engineer Intern", **changes):
    return {"id": identifier, "title": title, "url": f"/companies/example/jobs/T{identifier}-role",
            "companyUrl": "/companies/example", "location": "IN / Remote (IN)",
            "type": "Internship", "visa": "US citizenship/visa not required",
            "minSchoolYear": "Any", "minExperience": "Any (new grads ok)",
            "createdAt": "1 hour", "lastActive": "just now",
            "applyUrl": "https://account.ycombinator.com/authenticate?continue=private",
            "isIncomplete": False, **changes}


def page(props, schemas=None, links=()):
    payload = html.escape(json.dumps({"props": {"currentUser": None, "signedIn": False, **props}}),
                          quote=True)
    anchors = "".join(f'<a href="{html.escape(link, quote=True)}">Role</a>' for link in links)
    scripts = "".join('<script type="application/ld+json">' + json.dumps(schema) + '</script>'
                      for schema in (schemas or []))
    return f'<div data-page="{payload}">{anchors}</div>{scripts}'


def listing(jobs=None, *, extra_links=(), **props):
    jobs = [job()] if jobs is None else jobs
    return page({"company": {"slug": "example", "name": "Example Ltd"},
                 "jobsUrl": "/companies/example/jobs", "jobPostings": jobs, **props},
                links=[item["url"] for item in jobs if isinstance(item, dict)] + list(extra_links))


def schema(posting=None, **changes):
    posting = posting or job()
    return {"@type": "JobPosting", "url": yc.ROOT + posting["url"], "title": posting["title"],
            "hiringOrganization": {"name": "Example Ltd"}, "datePosted": NOW.isoformat(),
            "description": "<p>Build Python APIs and learn PostgreSQL through mentored work.</p>",
            "employmentType": "INTERN", "jobLocationType": "TELECOMMUTE",
            "applicantLocationRequirements": {"@type": "Country", "name": "IN"}, **changes}


def detail(posting=None, *, schemas=None, **props):
    posting = posting or job()
    return page({"company": {"slug": "example", "name": "Example Ltd"},
                 "job": posting, "showDirectApply": True, **props},
                schemas=[schema(posting)] if schemas is None else schemas)


def source(monkeypatch, list_page=None, details=None):
    requests = []

    def read(company, posting=None):
        requests.append((company, posting))
        value = ((listing() if list_page is None else list_page) if posting is None
                 else (details or {}).get(posting, detail()))
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(yc, "_read_public", read)
    return requests


def test_public_detail_uses_exact_publication_and_keeps_submission_manual(monkeypatch):
    requests = source(monkeypatch)
    coverage = {}
    result = yc.fetch_yc("example", now=NOW, coverage=coverage)
    assert requests == [("example", None), ("example", "T1-role")]
    row = result[0]
    assert row["source"] == "yc" and row["source_key"] == "example:1"
    assert row["source_url"] == row["apply_url"] == yc.ROOT + job()["url"]
    assert row["published_at"] == NOW and row["published_at_basis"] == "published"
    assert row["publication_field"] == "JobPosting.datePosted"
    assert row["submission_supported"] is False and row["submission_mode"] == "manual"
    assert row["location"] == "Remote (India)" and row["remote"] is True
    assert row["employment_type"] == "Intern" and "<p>" not in row["description"]
    assert "Platform visa requirement: US citizenship/visa not required." in row["description"]
    assert row["source_constraints"]["minSchoolYear"] == "Any"
    assert coverage["model_calls"] == 0 and coverage["returned"] == 1
    assert not coverage["truncated"] and not coverage["submission_supported"]


@pytest.mark.parametrize("date,reason", [
    (None, "unknown_date"), ("yesterday", "unknown_date"), ("2026-11-02", "unknown_date"),
    ("2026-11-02T11:00:00", "unknown_date"), (True, "unknown_date"),
    ((NOW + timedelta(seconds=1)).isoformat(), "future_date"),
    ((NOW - timedelta(hours=72, seconds=1)).isoformat(), "stale_date"),
    ("2022-03-03T00:59:42Z", "stale_date"),  # Observed Aviator public JSON-LD counterexample.
])
def test_only_exact_zoned_dateposted_can_qualify_not_relative_list_age(monkeypatch, date, reason):
    source(monkeypatch, details={"T1-role": detail(schemas=[schema(datePosted=date)])})
    coverage = {}
    assert yc.fetch_yc("example", now=NOW, coverage=coverage) == []
    assert coverage[reason] == 1
    assert coverage["detail_failures"] == 0


def test_exact_window_boundary_and_non_utc_offsets_are_preserved(monkeypatch):
    date = "2026-10-30T17:30:00+05:30"
    source(monkeypatch, details={"T1-role": detail(schemas=[schema(datePosted=date)])})
    assert yc.fetch_yc("example", now=NOW)[0]["published_at"] == NOW - timedelta(hours=72)


@pytest.mark.parametrize("changes", [
    {"job": job(id=2)}, {"job": job(id=True)}, {"job": job(url="/companies/other/jobs/T1-role")},
    {"job": job(companyUrl="/companies/other")}, {"job": job(isIncomplete=True)},
    {"company": {"slug": "other", "name": "Example Ltd"}}, {"signedIn": True},
    {"currentUser": {"id": 10}},
])
def test_detail_identity_and_public_account_boundary_are_rechecked(monkeypatch, changes):
    source(monkeypatch, details={"T1-role": detail(**changes)})
    coverage = {}
    assert yc.fetch_yc("example", now=NOW, coverage=coverage) == []
    assert coverage["detail_failures"] == 1 and coverage["truncated"]


@pytest.mark.parametrize("schemas", [
    [], [schema(url=yc.ROOT + "/companies/other/jobs/T1-role")],
    [schema(title="Another title")], [schema(hiringOrganization={"name": "Other Ltd"})],
    [schema(), schema()], [schema(description="")], [schema(validThrough="yesterday")],
])
def test_matching_unambiguous_jobposting_metadata_is_required(monkeypatch, schemas):
    source(monkeypatch, details={"T1-role": detail(schemas=schemas)})
    coverage = {}
    assert yc.fetch_yc("example", now=NOW, coverage=coverage) == []
    assert coverage["detail_failures"] == 1


def test_related_schema_does_not_supply_the_primary_job_date(monkeypatch):
    related = schema(url=yc.ROOT + "/companies/example/jobs/Other-role")
    source(monkeypatch, details={"T1-role": detail(schemas=[{
        "@graph": [related, schema(datePosted="2022-03-03T00:59:42Z")],
    }])})
    assert yc.fetch_yc("example", now=NOW) == []


def test_declared_remote_country_overrides_misleading_india_title_and_location(monkeypatch):
    posting = job(title="Engineer - India", visa="US citizen/visa only")
    source(monkeypatch, listing([posting]), {"T1-role": detail(posting, schemas=[schema(
        posting, applicantLocationRequirements=[{"name": "US"}],
    )])})
    row = yc.fetch_yc("example", now=NOW)[0]
    assert row["location"] == "Remote (United States)"
    assert row["source_constraints"]["location"] == "IN / Remote (IN)"
    assert "US citizen/visa only" in row["description"]


def test_hybrid_or_office_role_is_not_inferred_remote_and_expired_jobs_are_rejected(monkeypatch):
    posting = job(location="Bengaluru, IN / Hybrid")
    source(monkeypatch, listing([posting]), {"T1-role": detail(posting, schemas=[schema(
        posting, jobLocationType="HYBRID", applicantLocationRequirements=None,
    )])})
    row = yc.fetch_yc("example", now=NOW)[0]
    assert row["remote"] is False and "India" in row["location"]
    source(monkeypatch, details={"T1-role": detail(schemas=[schema(validThrough=NOW.isoformat())])})
    coverage = {}
    assert yc.fetch_yc("example", now=NOW, coverage=coverage) == [] and coverage["closed"] == 1


def test_apply_destination_is_not_followed_even_when_showdirectapply_is_true(monkeypatch):
    posting = job(applyUrl="http://127.0.0.1/private")
    requests = source(monkeypatch, details={"T1-role": detail(posting)})
    row = yc.fetch_yc("example", now=NOW)[0]
    assert len(requests) == 2 and row["apply_url"] == yc.ROOT + job()["url"]
    assert not row["submission_supported"]


def test_list_and_detail_budgets_and_title_priority_are_explicit(monkeypatch):
    jobs = [job(n, title="Sales Manager") for n in range(1, 51)]
    jobs[40] = job(41, title="Backend Engineer Intern")
    requests = source(monkeypatch, listing(jobs), {"T41-role": detail(jobs[40])})
    coverage = {}
    assert len(yc.fetch_yc("example", now=NOW, search_titles=["Backend Engineer"],
                           coverage=coverage)) == 1
    assert requests == [("example", None), ("example", "T41-role")]
    jobs = [job(n) for n in range(1, 81)]
    details = {f"T{n}-role": detail(job(n)) for n in range(1, 11)}
    requests = source(monkeypatch, listing(jobs), details)
    yc.fetch_yc("example", now=NOW, coverage=coverage)
    assert len(requests) == 11 and coverage["listed"] == 50
    assert coverage["observed_list_records"] == 80 and coverage["reported_total"] is None
    assert coverage["coverage_scope"] == "single_company_public_page"
    assert coverage["details_fetched"] == 10 and coverage["truncated"]


@pytest.mark.parametrize("limit", [0, 1, 3])
def test_scan_wide_caller_budget_can_reduce_or_exhaust_detail_reads(monkeypatch, limit):
    jobs = [job(n) for n in range(1, 6)]
    requests = source(monkeypatch, listing(jobs), {
        f"T{n}-role": detail(job(n)) for n in range(1, 6)
    })
    coverage = {}
    assert len(yc.fetch_yc("example", now=NOW, detail_limit=limit, coverage=coverage)) == limit
    assert len(requests) == limit + 1
    assert coverage["details_fetched"] == limit and coverage["detail_limit"] == limit
    assert coverage["listed"] == 5 and coverage["truncated"]


@pytest.mark.parametrize("limit", [-1, 11, True, "3"])
def test_invalid_caller_budget_does_not_reach_the_provider(monkeypatch, limit):
    read = Mock(side_effect=AssertionError("Must not fetch"))
    monkeypatch.setattr(yc, "_read_public", read)
    with pytest.raises(ValueError):
        yc.fetch_yc("example", now=NOW, detail_limit=limit)
    read.assert_not_called()


@pytest.mark.parametrize("url", [
    "https://evil.test/companies/example/jobs/T1-role",
    "https://www.ycombinator.com.evil.test/companies/example/jobs/T1-role",
    "https://user:pass@www.ycombinator.com/companies/example/jobs/T1-role",
    "//evil.test/companies/example/jobs/T1-role", "/companies/other/jobs/T1-role",
    "/companies/example/jobs/T1-role/extra", "/companies/example/jobs/T1%2frole",
    "/companies/example/jobs/T1-role?redirect=evil", "/companies/example/jobs/T1-role#apply",
])
def test_unreviewed_source_paths_never_become_network_destinations(monkeypatch, url):
    requests = source(monkeypatch, listing([job(url=url)]))
    coverage = {}
    assert yc.fetch_yc("example", now=NOW, coverage=coverage) == []
    assert requests == [("example", None)] and coverage["invalid_list_records"] == 1


def test_duplicate_links_do_not_spend_calls_and_blocked_details_stop_the_board(monkeypatch):
    requests = source(monkeypatch, listing([job(), job()]))
    assert len(yc.fetch_yc("example", now=NOW)) == 1 and len(requests) == 2
    requests = source(monkeypatch, listing([job(), job(2)]), {
        "T1-role": yc._Blocked("YC public access blocked"),
    })
    coverage = {}
    assert yc.fetch_yc("example", now=NOW, coverage=coverage) == []
    assert requests == [("example", None), ("example", "T1-role")]
    assert coverage["blocked"] and coverage["detail_failures"] == 1 and coverage["truncated"]


def test_detail_failure_is_partial_but_cancellation_after_a_read_propagates(monkeypatch):
    source(monkeypatch, details={"T1-role": RuntimeError("Provider down")})
    coverage = {}
    assert yc.fetch_yc("example", now=NOW, coverage=coverage) == []
    assert coverage["detail_failures"] == 1 and coverage["truncated"]
    source(monkeypatch)
    interrupt = Mock(side_effect=[None, None, RuntimeError("Interrupted")])
    with pytest.raises(RuntimeError, match="Interrupted"):
        yc.fetch_yc("example", now=NOW, checkpoint=interrupt, coverage=coverage)
    assert coverage["truncated"] and coverage["returned"] == 0


def test_missing_list_or_login_page_is_not_reported_as_an_empty_success(monkeypatch):
    source(monkeypatch, '<form action="/login">Sign in</form>')
    coverage = {}
    with pytest.raises(ValueError):
        yc.fetch_yc("example", now=NOW, coverage=coverage)
    assert coverage["list_failures"] == 1 and coverage["truncated"]
    source(monkeypatch, listing([]))
    assert yc.fetch_yc("example", now=NOW, coverage=coverage) == []
    assert coverage["list_failures"] == 0 and not coverage["truncated"]


@pytest.mark.parametrize("changes", [
    {"company": {"slug": "other", "name": "Example Ltd"}},
    {"jobsUrl": "/companies/other/jobs"}, {"jobPostings": {}},
])
def test_wrong_company_or_malformed_index_is_a_source_failure(monkeypatch, changes):
    source(monkeypatch, listing(**changes))
    coverage = {}
    with pytest.raises(ValueError):
        yc.fetch_yc("example", now=NOW, coverage=coverage)
    assert coverage["list_failures"] == 1 and coverage["truncated"]


def test_public_index_record_must_have_a_matching_rendered_link(monkeypatch):
    index = page({"company": {"slug": "example", "name": "Example Ltd"},
                  "jobsUrl": "/companies/example/jobs", "jobPostings": [job()]})
    requests = source(monkeypatch, index)
    coverage = {}
    assert yc.fetch_yc("example", now=NOW, coverage=coverage) == []
    assert requests == [("example", None)] and coverage["invalid_list_records"] == 1


def test_description_bound_keeps_the_literal_platform_visa_constraint(monkeypatch):
    posting = job(visa="US citizen/visa only")
    source(monkeypatch, details={"T1-role": detail(posting, schemas=[schema(
        description="Long public description. " * 10000,
    )])})
    row = yc.fetch_yc("example", now=NOW)[0]
    assert len(row["description"]) <= 100000
    assert "Platform visa requirement: US citizen/visa only." in row["description"]


def test_transport_is_fixed_origin_bounded_and_never_uses_account_headers(monkeypatch):
    requests = []

    class Response:
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __init__(self, url):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return self.url

        def read(self, limit):
            assert limit == yc.MAX_BYTES + 1
            return b"<html></html>"

    class Opener:
        def open(self, request, timeout):
            assert timeout == 12
            assert {key.casefold() for key, _ in request.header_items()} == {"accept", "user-agent"}
            requests.append(request.full_url)
            return Response(request.full_url)

    monkeypatch.setattr(yc, "build_opener", lambda *_args: Opener())
    yc._read_public("example")
    yc._read_public("example", "T1-role")
    assert requests == [yc.ROOT + "/companies/example/jobs",
                        yc.ROOT + "/companies/example/jobs/T1-role"]
    with pytest.raises(yc._Blocked, match="refused"):
        yc._NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test")
    with pytest.raises(ValueError):
        yc._read_public("../private")
    with pytest.raises(ValueError):
        yc._read_public("example", "T1/role")
    monkeypatch.setattr(Response, "read", lambda *_args: b"x" * (yc.MAX_BYTES + 1))
    with pytest.raises(ValueError, match="size limit"):
        yc._read_public("example")
    monkeypatch.setattr(Response, "geturl", lambda _self: "https://account.ycombinator.com/login")
    with pytest.raises(yc._Blocked, match="endpoint"):
        yc._read_public("example")


@pytest.mark.parametrize("status", [401, 403, 429])
def test_access_block_is_terminal_and_provider_response_is_withheld(monkeypatch, status):
    opener = Mock()
    opener.open.side_effect = HTTPError(yc.ROOT, status, "PRIVATE_RESPONSE", {}, None)
    monkeypatch.setattr(yc, "build_opener", lambda *_args: opener)
    with pytest.raises(yc._Blocked, match="blocked or rate limited") as caught:
        yc._read_public("example")
    assert "PRIVATE_RESPONSE" not in str(caught.value)
    opener.open.assert_called_once()


@pytest.mark.parametrize("company,age", [("../secret", 72), ("example", 0), ("example", 169),
                                        ("example", True)])
def test_invalid_configuration_never_fetches(monkeypatch, company, age):
    read = Mock(side_effect=AssertionError("Must not fetch"))
    monkeypatch.setattr(yc, "_read_public", read)
    with pytest.raises(ValueError):
        yc.fetch_yc(company, max_age_hours=age, now=NOW)
    read.assert_not_called()
