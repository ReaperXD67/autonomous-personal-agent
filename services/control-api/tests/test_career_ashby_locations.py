from datetime import UTC, datetime

from app import career


def profile(**changes):
    return {
        "desired_titles": ["Software Engineer"], "skills": ["Python", "PostgreSQL"],
        "required_keywords": [], "excluded_keywords": [], "locations": ["India"],
        "employment_types": ["FullTime"], "remote_only": False,
        "max_age_hours": 72, "min_score": 0, **changes,
    }


def raw_job(**changes):
    return {
        "title": "Software Engineer", "location": "San Francisco",
        "address": {"postalAddress": {"addressCountry": "USA"}},
        "descriptionPlain": "Build Python and PostgreSQL services.",
        "publishedAt": datetime.now(UTC).isoformat(), "employmentType": "FullTime",
        "jobUrl": "https://jobs.ashbyhq.com/example/123",
        "applyUrl": "https://jobs.ashbyhq.com/example/123/application",
        "isRemote": False, "workplaceType": "OnSite", **changes,
    }


def fetch(monkeypatch, raw):
    monkeypatch.setattr(career, "_read_json", lambda _url: {"jobs": [raw]})
    return career.fetch_ashby("example")[0]


def test_explicit_secondary_india_location_can_match_without_weakening_country_gate(monkeypatch):
    job = fetch(monkeypatch, raw_job(secondaryLocations=[{
        "location": "Bengaluru", "address": {"addressCountry": "IND"},
    }]))
    assert job["location"] == "San Francisco, United States | Bengaluru, India"
    assert career.score_opportunity(job, profile()) is not None
    assert not job["remote"] and job["published_at_basis"] == "published"


def test_primary_structured_country_is_retained_without_description_inference(monkeypatch):
    job = fetch(monkeypatch, raw_job(location="Bengaluru", address={
        "postalAddress": {"addressCountry": "IN"},
    }))
    assert job["location"] == "Bengaluru, India"
    assert career.score_opportunity(job, profile()) is not None


def test_us_remote_and_description_worldwide_claim_do_not_manufacture_india_location(monkeypatch):
    job = fetch(monkeypatch, raw_job(
        location="Remote - United States", isRemote=True, workplaceType="Remote",
        descriptionPlain="Our products serve people worldwide. Build Python services.",
        secondaryLocations=[{"location": "California", "address": {"addressCountry": "USA"}}],
    ))
    assert career.score_opportunity(job, profile()) is None


def test_hybrid_is_not_fully_remote_even_when_provider_isremote_flag_is_true(monkeypatch):
    job = fetch(monkeypatch, raw_job(
        location="Bengaluru, India", address={}, workplaceType="Hybrid", isRemote=True,
    ))
    assert not job["remote"]
    assert career.score_opportunity(job, profile(remote_only=True)) is None


def test_malformed_secondary_shapes_are_ignored_and_duplicate_locations_collapse(monkeypatch):
    job = fetch(monkeypatch, raw_job(secondaryLocations=[
        "India", None, {"location": "San Francisco", "address": {"addressCountry": "USA"}},
        {"location": ["India"]},
    ]))
    assert job["location"] == "San Francisco, United States"
    assert career.score_opportunity(job, profile()) is None
    assert len(career._ashby_location({
        "location": "x" * 1000, "secondaryLocations": [{"location": "y" * 1000}] * 100,
    })) <= 300
