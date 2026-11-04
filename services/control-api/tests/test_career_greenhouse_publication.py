from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from app import career
from app.career import diagnose_opportunity, fetch_greenhouse
from app.career_autopilot import eligibility_reason, profile_hash

NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)
URL = "https://boards.greenhouse.io/example/jobs/42"


def fetch(monkeypatch, **changes):
    posting = {
        "id": 42, "title": "Software Engineer", "absolute_url": URL,
        "updated_at": (NOW - timedelta(hours=1)).isoformat(),
        "location": {"name": "Remote — India"},
        "content": "<p>Build Python, PostgreSQL and Docker services.</p>", **changes,
    }
    read = Mock(return_value={"jobs": [posting]})
    monkeypatch.setattr(career, "_read_json", read)
    rows = fetch_greenhouse("example")
    read.assert_called_once_with(
        "https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true",
    )
    return rows


def profile(**changes):
    return {
        "desired_titles": ["Software Engineer"], "skills": ["Python", "PostgreSQL", "Docker"],
        "resume_text": "Built Python APIs with PostgreSQL and Docker.",
        "locations": ["India"], "remote_only": False, "employment_types": [],
        "max_age_hours": 72, "min_score": 75, **changes,
    }


def run(candidate, **changes):
    return {
        "state": "running", "expires_at": NOW + timedelta(hours=1),
        "profile_hash": profile_hash(candidate), "max_age_hours": 72, "min_score": 75,
        "allowed_hosts": ["boards.greenhouse.io"], "mode": "apply", **changes,
    }


@pytest.mark.parametrize(("first_published", "expected"), [
    ("2026-11-02T12:00:00Z", datetime(2026, 11, 2, 12, tzinfo=UTC)),
    ("2026-11-02T17:30:00+05:30", datetime(2026, 11, 2, 12, tzinfo=UTC)),
    ("2026-11-02T05:00:00-07:00", datetime(2026, 11, 2, 12, tzinfo=UTC)),
    ("2026-11-03T00:15:00+05:30", datetime(2026, 11, 2, 18, 45, tzinfo=UTC)),
    ("2026-11-02T12:00:00.123456Z", datetime(2026, 11, 2, 12, 0, 0, 123456, tzinfo=UTC)),
])
def test_explicit_aware_first_publication_is_preferred_and_normalized(
    monkeypatch, first_published, expected,
):
    row = fetch(monkeypatch, first_published=first_published)[0]
    assert row["published_at"] == expected and row["published_at"].tzinfo is UTC
    assert row["published_at_basis"] == "published"
    assert row["source_url"] == row["apply_url"] == URL


@pytest.mark.parametrize("updated_at", [None, "invalid", False])
def test_valid_first_publication_does_not_depend_on_an_update_timestamp(monkeypatch, updated_at):
    rows = fetch(monkeypatch, first_published="2026-11-02T12:00:00Z", updated_at=updated_at)
    assert len(rows) == 1 and rows[0]["published_at_basis"] == "published"


@pytest.mark.parametrize("first_published", [
    None, True, False, 1793620800, 1793620800.5, "1793620800", {}, [],
    "", "invalid", "2026-11-02", "2026-11-02T12:00:00", "2026-11-02 12:00:00",
    "2026-11-02x12:00:00+00:00", "2026-02-30T12:00:00Z", "2026-11-02T12:00:00+25:00",
    "2026-11-02T12:00:00+00:99", " 2026-11-02T12:00:00Z ",
])
def test_invalid_or_unverified_first_publication_keeps_update_as_history_only(
    monkeypatch, first_published,
):
    row = fetch(monkeypatch, first_published=first_published)[0]
    assert row["published_at"] == NOW - timedelta(hours=1)
    assert row["published_at_basis"] == "updated"
    candidate = profile()
    assert "verified posting date" in eligibility_reason(run(candidate), candidate, row, now=NOW)


def test_missing_first_publication_preserves_existing_update_only_history(monkeypatch):
    row = fetch(monkeypatch)[0]
    assert row["published_at_basis"] == "updated"
    assert row["published_at"] == NOW - timedelta(hours=1)
    assert fetch(monkeypatch, updated_at=None) == []


def test_recent_update_never_revives_an_aged_first_publication(monkeypatch):
    first = NOW - timedelta(hours=120)
    row = fetch(monkeypatch, first_published=first.isoformat())[0]
    assert row["published_at"] == first and row["published_at_basis"] == "published"
    candidate = profile()
    assert diagnose_opportunity(row, candidate, now=NOW)["filter_reason"] == (
        "outside_freshness_window"
    )
    assert "posting window" in eligibility_reason(run(candidate), candidate, row, now=NOW)


def test_future_first_publication_remains_future_for_existing_hard_gates(monkeypatch):
    first = NOW + timedelta(hours=1)
    row = fetch(monkeypatch, first_published=first.isoformat())[0]
    assert row["published_at"] == first
    candidate = profile()
    assert diagnose_opportunity(row, candidate, now=NOW)["filter_reason"] == "future_date"
    assert "posting window" in eligibility_reason(run(candidate), candidate, row, now=NOW)


def test_true_publication_obeys_exact_and_narrower_authorized_age_windows(monkeypatch):
    candidate = profile()
    boundary = fetch(monkeypatch, first_published=(NOW - timedelta(hours=72)).isoformat())[0]
    assert eligibility_reason(run(candidate), candidate, boundary, now=NOW) is None
    assert "posting window" in eligibility_reason(
        run(candidate, max_age_hours=24), candidate, boundary, now=NOW,
    )
    aged = fetch(monkeypatch, first_published=(
        NOW - timedelta(hours=72, microseconds=1)
    ).isoformat())[0]
    assert "posting window" in eligibility_reason(run(candidate), candidate, aged, now=NOW)


def test_publication_evidence_does_not_override_fit_or_mandatory_qualifications(monkeypatch):
    candidate = profile()
    row = fetch(monkeypatch, first_published=(NOW - timedelta(hours=1)).isoformat(),
                content="Build Python services.")[0]
    assert "fit threshold" in eligibility_reason(run(candidate), candidate, row, now=NOW)
    row = fetch(
        monkeypatch, first_published=(NOW - timedelta(hours=1)).isoformat(),
        content="Build Python PostgreSQL Docker. Must be currently enrolled in university.",
    )[0]
    assert "Mandatory qualification review" in eligibility_reason(
        run(candidate), candidate, row, now=NOW,
    )
