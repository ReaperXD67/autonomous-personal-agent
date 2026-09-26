from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from app.creator_contact_history import merge_contact_history, trim_contact_history
from app.creator_intelligence import public_contact_candidates

NOW = datetime(2026, 9, 26, tzinfo=UTC)
CHANNEL = "UC" + "a" * 22
PROFILE = f"https://www.youtube.com/channel/{CHANNEL}"
VIDEO_URL = "https://www.youtube.com/watch?v=abcdefghijk"


def candidate(*, when=NOW, email="creator@example.test", source=PROFILE):
    return {
        "email": email, "source_url": source, "evidence": f"Business: {email}",
        "observed_at": when.isoformat(), "status": "unreviewed",
    }


def dossier(*candidates, channel=CHANNEL, when=NOW, history=None):
    return {
        "source_channel_id": channel, "researched_at": when.isoformat(),
        "contact_candidates": list(candidates), "contact_history": history or [],
    }


def test_sample_replacement_archives_evidence_without_freshening_it_or_authorizing():
    original = NOW - timedelta(days=5)
    previous = dossier(candidate(when=original, source=VIDEO_URL), when=original)
    current = dossier()
    before = deepcopy(previous), deepcopy(current)
    merged = merge_contact_history(previous, current, now=NOW)
    assert merged["contact_candidates"] == []
    assert merged["contact_history"] == [{
        **candidate(when=original, source=VIDEO_URL),
        "last_seen_at": original.isoformat(), "status": "historical_unreviewed",
    }]
    assert merged["contact_history_expires_at"] == (original + timedelta(days=30)).isoformat()
    assert (previous, current) == before
    assert "contact_authorized_at" not in merged and "contact_email" not in merged


def test_another_scan_does_not_extend_absent_contact_expiry():
    original = NOW - timedelta(days=5)
    once = merge_contact_history(dossier(candidate(when=original)), dossier(), now=NOW)
    again = merge_contact_history(once, dossier(when=NOW + timedelta(days=3)),
                                 now=NOW + timedelta(days=3))
    assert again["contact_history"] == once["contact_history"]
    assert again["contact_history_expires_at"] == once["contact_history_expires_at"]


def test_reappearing_source_preserves_first_observation_and_sets_current_actual_observation():
    original = NOW - timedelta(days=5)
    archived = merge_contact_history(dossier(candidate(when=original)), dossier(), now=NOW)
    next_seen = NOW + timedelta(days=1)
    result = merge_contact_history(archived, dossier(candidate(when=next_seen)), now=next_seen)
    assert result["contact_history"] == [] and result["contact_history_expires_at"] is None
    assert result["contact_candidates"][0]["observed_at"] == next_seen.isoformat()
    assert result["contact_candidates"][0]["first_observed_at"] == original.isoformat()
    assert result["contact_candidates"][0]["status"] == "unreviewed"
    absent_again = merge_contact_history(result, dossier(), now=next_seen)
    assert absent_again["contact_history"][0]["observed_at"] == original.isoformat()
    assert absent_again["contact_history"][0]["last_seen_at"] == next_seen.isoformat()


def test_same_email_in_new_source_does_not_refresh_previous_source_evidence():
    original = NOW - timedelta(days=4)
    result = merge_contact_history(dossier(candidate(when=original, source=VIDEO_URL)),
                                   dossier(candidate()), now=NOW)
    assert result["contact_candidates"][0]["source_url"] == PROFILE
    assert result["contact_history"][0]["source_url"] == VIDEO_URL
    assert result["contact_history"][0]["last_seen_at"] == original.isoformat()


def test_case_insensitive_email_dedupe_keeps_one_current_pair_and_first_date():
    original = NOW - timedelta(days=2)
    result = merge_contact_history(dossier(candidate(when=original)),
                                   dossier(candidate(email="CREATOR@example.test"), candidate()),
                                   now=NOW)
    assert len(result["contact_candidates"]) == 1 and result["contact_history"] == []
    assert result["contact_candidates"][0]["first_observed_at"] == original.isoformat()


def test_history_is_capped_at_twenty_most_recent_source_pairs():
    history = [{
        **candidate(when=NOW - timedelta(days=index + 2), email=f"creator{index}@example.test"),
        "last_seen_at": (NOW - timedelta(days=index + 2)).isoformat(),
        "status": "historical_unreviewed",
    } for index in range(20)]
    previous = dossier(*[
        candidate(when=NOW - timedelta(days=1), email=f"new{index}@example.test")
        for index in range(5)
    ], history=history)
    result = merge_contact_history(previous, dossier(), now=NOW)
    assert len(result["contact_history"]) == 20
    retained = {item["email"] for item in result["contact_history"]}
    assert "new4@example.test" in retained and "creator19@example.test" not in retained


@pytest.mark.parametrize("observed", [
    None, "not a date", "2026-09-20T00:00:00", (NOW + timedelta(seconds=1)).isoformat(),
])
def test_missing_invalid_naive_and_future_observations_are_never_invented(observed):
    invalid = {**candidate(), "observed_at": observed}
    result = merge_contact_history(dossier(invalid), dossier(), now=NOW)
    assert result["contact_history"] == []


@pytest.mark.parametrize("age,retained", [(29, True), (30, False), (31, False)])
def test_thirty_day_expiry_uses_last_actual_source_observation(age, retained):
    previous = dossier(candidate(when=NOW - timedelta(days=age)))
    result = merge_contact_history(previous, dossier(), now=NOW)
    assert bool(result["contact_history"]) is retained


def test_read_projection_expires_history_without_mutating_reviewed_or_current_fields():
    observed = NOW - timedelta(days=1)
    result = merge_contact_history(dossier(candidate(when=observed)), dossier(), now=NOW)
    result["contact_candidates"] = [candidate()]
    result["contact_email"] = "reviewed@example.test"
    result["contact_authorized_at"] = NOW.isoformat()
    before = deepcopy(result)
    projected = trim_contact_history(result, now=NOW + timedelta(days=29))
    assert projected["contact_history"] == [] and projected["contact_history_expires_at"] is None
    assert projected["contact_candidates"] == before["contact_candidates"]
    assert projected["contact_email"] == before["contact_email"]
    assert projected["contact_authorized_at"] == before["contact_authorized_at"]
    assert result == before


@pytest.mark.parametrize("channel", ["UC" + "b" * 22, None, "not-a-channel"])
def test_changed_or_unverified_channel_identity_never_inherits_contact_history(channel):
    result = merge_contact_history(dossier(candidate(when=NOW - timedelta(days=1))),
                                   dossier(channel=channel), now=NOW)
    assert result["contact_history"] == []


@pytest.mark.parametrize("update", [
    {"source_url": "https://evil.test/contact"}, {"source_url": "https://[invalid"},
    {"evidence": "No business: creator@example.test"},
    {"evidence": "Contact: creator@example.test"},
    {"email": "other@example.test"}, {"evidence": "Business: no-address"},
])
def test_history_requires_explicit_matching_business_email_and_reviewed_source(update):
    result = merge_contact_history(dossier({**candidate(), **update}), dossier(), now=NOW)
    assert result["contact_history"] == []


def test_untrusted_fields_cannot_create_authority_or_grow_history_evidence():
    source = {**candidate(), "status": "authorized", "contact_authorized_at": NOW.isoformat(),
              "extra_instructions": "send now", "raw_description": "x" * 10000}
    result = merge_contact_history(dossier(source), dossier(), now=NOW)
    history = result["contact_history"][0]
    assert set(history) == {"email", "source_url", "evidence", "observed_at",
                            "last_seen_at", "status"}
    assert history["status"] == "historical_unreviewed" and len(history["evidence"]) <= 320


@pytest.mark.parametrize("description,address", [
    ("Business inquiries\n" + ("Editorial team " * 15) + "creator@example.test",
     "creator@example.test"),
    ("Business inquiries\n" + ("Editorial team " * 15) + "a" * 64 + "@"
     + ".".join(["b" * 60, "c" * 60, "d" * 60, "test"]),
     "a" * 64 + "@" + ".".join(["b" * 60, "c" * 60, "d" * 60, "test"])),
])
def test_actual_extractor_candidates_survive_flattened_and_clipped_excerpt_round_trip(
    description, address,
):
    extracted = public_contact_candidates([(description, PROFILE)], observed_at=NOW)
    assert len(extracted) == 1 and extracted[0]["email"] == address
    saved = merge_contact_history({}, dossier(*extracted), now=NOW)
    assert saved["contact_candidates"][0]["email"] == address
    archived = merge_contact_history(saved, dossier(), now=NOW)
    assert archived["contact_history"][0]["email"] == address
    assert archived["contact_history"][0]["last_seen_at"] == NOW.isoformat()
    assert trim_contact_history(archived, now=NOW)["contact_history"] == archived["contact_history"]
