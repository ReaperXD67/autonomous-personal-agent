import copy
import json
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app import creator_pilot, creator_pilot_runner, marketing
from app.creator_pilot import rank_prospect, recent_uploads, safe_excerpt
from app.creator_pilot_runner import execute_creator_pilot
from app.creator_pilot_store import CreatorPilotCreate, CreatorPilotStore
from app.marketing import YouTubeRequestLimitError
from app.policy import RiskLevel, capability_max_attempts, effective_risk
from app.store import InvalidTaskStateError
from app.worker import TaskInterruptedError

NOW = datetime(2026, 10, 20, tzinfo=UTC)
CHANNEL = "UCabcdefghijklmnopqrstuv"
PROFILE = f"https://www.youtube.com/channel/{CHANNEL}"
VIDEO = "AbCdEfGhI12"
URL = f"https://www.youtube.com/watch?v={VIDEO}"


def fixture():
    campaign = {
        "id": uuid4(), "min_subscribers": 1000, "max_subscribers": 50000,
        "max_video_age_days": 120,
    }
    prospect = {
        "id": uuid4(), "display_name": "Fixture creator", "audience_size": 4000,
        "platform": "youtube", "status": "qualified", "suppressed_at": None,
        "profile_url": PROFILE, "latest_content_url": URL,
        "contact_authorized_at": NOW, "contact_email": "creator@example.test",
        "contact_source_url": URL, "contact_basis_note": "Owner reviewed fixture",
        "intelligence": {
            "researched_at": NOW.isoformat(), "topics": ["Minecraft", "Servers"],
            "enrichment_status": "complete", "geography": {"eligible": True},
            "recent_videos": [],
            "activity": {"status": "observed_this_run", "videos": [{
                "title": "Minecraft servers", "url": URL,
                "published_at": (NOW - timedelta(days=2)).isoformat(),
                "topics": ["Minecraft"], "language": "pl",
                "language_source": "defaultAudioLanguage",
            }]},
            "contact_candidates": [{
                "email": "creator@example.test", "source_url": URL,
                "evidence": "Współpraca: creator@example.test",
                "observed_at": NOW.isoformat(),
            }],
        },
    }
    return campaign, prospect


def channel():
    return {
        "id": CHANNEL, "snippet": {"title": "Fixture creator", "description": "Minecraft"},
        "statistics": {"subscriberCount": "4000"},
        "contentDetails": {"relatedPlaylists": {"uploads": "UUabcdefghijklmnopqrstuv"}},
    }


def video(**changes):
    value = {
        "id": VIDEO, "status": {"privacyStatus": "public"},
        "snippet": {"channelId": CHANNEL, "title": "Minecraft servers",
                    "description": "Business: creator@example.test",
                    "publishedAt": "2026-10-18T00:00:00Z", "defaultAudioLanguage": "pl"},
    }
    value["snippet"].update(changes)
    return value


def test_recent_uploads_use_bounded_endpoints_without_search_or_country_inference(monkeypatch):
    requests = []

    def read(path, parameters):
        requests.append((path, parameters))
        if path.endswith("playlistItems"):
            return {"items": [{"contentDetails": {"videoId": VIDEO}}], "nextPageToken": "ignored"}
        return {"items": [video()]}

    monkeypatch.setattr(creator_pilot, "_read_youtube_json", read)
    checkpoint = Mock()
    activity, contacts = recent_uploads("fixture", channel(), now=NOW, checkpoint=checkpoint)
    assert len(requests) == checkpoint.call_count == 2
    assert requests[0][1]["maxResults"] == 3
    assert [item[0] for item in requests] == ["/youtube/v3/playlistItems", "/youtube/v3/videos"]
    assert activity["videos"][0]["published_at"] == "2026-10-18T00:00:00+00:00"
    assert activity["videos"][0]["language"] == "pl"
    assert contacts[0]["source_url"] == URL
    assert "creator@example.test" not in json.dumps(activity)


@pytest.mark.parametrize("change", [
    {"channelId": "UC" + "z" * 22},
    {"publishedAt": "2027-01-01T00:00:00Z"},
    {"publishedAt": "bad"}, {"liveBroadcastContent": "upcoming"},
])
def test_unowned_future_upcoming_or_undated_uploads_are_not_activity(monkeypatch, change):
    monkeypatch.setattr(creator_pilot, "_read_youtube_json", lambda path, params: {
        "items": [{"contentDetails": {"videoId": VIDEO}}] if path.endswith("playlistItems")
        else [video(**change)],
    })
    activity, contacts = recent_uploads("fixture", channel(), now=NOW, checkpoint=lambda: None)
    assert activity["videos"] == contacts == []


def test_private_or_unrequested_videos_are_not_activity(monkeypatch):
    other = video()
    other["id"] = "x" * 11
    private = video()
    private["status"]["privacyStatus"] = "private"
    monkeypatch.setattr(creator_pilot, "_read_youtube_json", lambda path, params: {
        "items": [{"contentDetails": {"videoId": VIDEO}}] if path.endswith("playlistItems")
        else [private, other],
    })
    activity, contacts = recent_uploads("fixture", channel(), now=NOW, checkpoint=lambda: None)
    assert activity["videos"] == contacts == []


def test_recent_uploads_are_sorted_and_text_language_is_explicit(monkeypatch):
    older, newer = video(), video(publishedAt="2026-10-19T00:00:00Z", defaultAudioLanguage=None,
                                 defaultLanguage="en")
    newer["id"] = "x" * 11
    monkeypatch.setattr(creator_pilot, "_read_youtube_json", lambda path, params: {
        "items": [{"contentDetails": {"videoId": identity}} for identity in [VIDEO, "x" * 11]]
        if path.endswith("playlistItems") else [older, newer],
    })
    activity, _ = recent_uploads("fixture", channel(), now=NOW, checkpoint=lambda: None)
    assert activity["videos"][0]["url"].endswith("x" * 11)
    assert activity["videos"][0]["language_source"] == "defaultLanguage"


def test_fetch_refresh_preserves_matching_sample_and_adds_current_activity(monkeypatch):
    campaign, prospect = fixture()
    requests = []

    def read(path, parameters):
        requests.append(path)
        if path.endswith("channels"):
            return {"items": [channel()]}
        if path.endswith("playlistItems"):
            return {"items": [{"contentDetails": {"videoId": VIDEO}}]}
        return {"items": [video()]}

    monkeypatch.setattr(marketing, "_read_youtube_json", read)
    monkeypatch.setattr(creator_pilot, "_read_youtube_json", read)
    result = marketing.fetch_youtube_prospect(
        "fixture", campaign, prospect, now=NOW, include_recent_activity=True,
    )
    assert len(requests) == 4
    assert result["latest_content_url"] == URL
    assert result["intelligence"]["activity"]["videos"][0]["language"] == "pl"
    assert result["intelligence"]["recent_videos"][0]["topics"] == ["Minecraft", "Servers"]
    assert "contact_authorized_at" not in result


def pilot_refresh(monkeypatch, uploads, *, reread=None, campaign_age=120, checkpoint=None):
    campaign, prospect = fixture()
    campaign["max_video_age_days"] = campaign_age
    old = video(title="Old Minecraft SMP", defaultAudioLanguage="en",
                publishedAt=(NOW - timedelta(days=150)).isoformat())
    old["id"] = "o" * 11
    prospect.update({
        "latest_content_title": old["snippet"]["title"],
        "latest_content_url": f"https://www.youtube.com/watch?v={old['id']}",
        "latest_content_published_at": NOW - timedelta(days=150),
    })
    requests = []

    def read(path, parameters):
        requests.append((path, parameters))
        if path.endswith("channels"):
            return {"items": [channel()]}
        if path.endswith("playlistItems"):
            return {"items": [{"contentDetails": {"videoId": item["id"]}}
                              for item in uploads]}
        if parameters["part"] == "snippet,status":
            return {"items": copy.deepcopy(uploads)}
        if reread is not None:
            return reread(parameters)
        return {"items": [copy.deepcopy(item) for item in [old, *uploads]
                          if item["id"] == parameters["id"]]}

    monkeypatch.setattr(marketing, "_read_youtube_json", read)
    monkeypatch.setattr(creator_pilot, "_read_youtube_json", read)
    result = marketing.fetch_youtube_prospect(
        "fixture", campaign, prospect, now=NOW, include_recent_activity=True,
        checkpoint=checkpoint,
    )
    return result, requests


def test_pilot_promotes_newest_verified_minecraft_citation_and_language_in_four_calls(monkeypatch):
    newer = video(title="Minecraft survival first session",
                  publishedAt=(NOW - timedelta(days=1)).isoformat(),
                  description="Minecraft survival. Business: new@example.test")
    newer["id"] = "n" * 11
    unrelated = video(title="Travel diary", description="Travel only",
                      publishedAt=NOW.isoformat())
    unrelated["id"] = "t" * 11
    checkpoint = Mock()
    result, requests = pilot_refresh(monkeypatch, [video(), newer, unrelated],
                                    checkpoint=checkpoint)
    assert len(requests) == checkpoint.call_count == 4
    assert [path.rsplit("/", 1)[-1] for path, _ in requests] == [
        "channels", "playlistItems", "videos", "videos",
    ]
    assert requests[-1][1]["id"] == newer["id"]
    assert requests[-1][1]["part"] == "snippet,statistics,status"
    assert result["latest_content_url"].endswith(newer["id"])
    assert result["latest_content_title"] == newer["snippet"]["title"]
    assert result["latest_content_published_at"] == NOW - timedelta(days=1)
    intelligence = result["intelligence"]
    assert intelligence["geography"]["language_code"] == "pl"
    assert intelligence["geography"]["language_source_url"] == result["latest_content_url"]
    assert intelligence["recent_videos"][0]["metadata_status"] == "observed_this_run"
    assert intelligence["recent_videos"][0]["url"] == result["latest_content_url"]
    assert "Survival" in intelligence["topics"]
    assert any(candidate["email"] == "new@example.test"
               and candidate["source_url"] == result["latest_content_url"]
               for candidate in intelligence["contact_candidates"])
    assert "contact_authorized_at" not in result and "contact_email" not in result


def test_pilot_description_boilerplate_cannot_promote_or_rank_an_unrelated_title(monkeypatch):
    upload = video(title="Travel diary", description="Minecraft. Business: creator@example.test")
    result, _ = pilot_refresh(monkeypatch, [upload])
    assert result["latest_content_url"].endswith("o" * 11)
    campaign, prospect = fixture()
    prospect["intelligence"] = result["intelligence"]
    assert rank_prospect(campaign, prospect, now=NOW)["status"] == "excluded"
    assert any("No observed Minecraft publication" in gap
               for gap in rank_prospect(campaign, prospect, now=NOW)["gaps"])
    # An observed matching sample also needs its own explicit title evidence.
    prospect["intelligence"]["activity"]["videos"] = []
    prospect["intelligence"]["recent_videos"][0].update({
        "title": "Travel diary", "topics": ["Minecraft"], "published_at": NOW.isoformat(),
    })
    assert rank_prospect(campaign, prospect, now=NOW)["status"] == "excluded"


@pytest.mark.parametrize("replacement", [None, "replacement@example.test"])
def test_pilot_final_selected_description_supersedes_earlier_business_contact(
    monkeypatch, replacement,
):
    selected = video()
    other = video(title="Older Minecraft upload", publishedAt=(NOW - timedelta(days=3)).isoformat(),
                  description="Business: other@example.test")
    other["id"] = "x" * 11
    final = video(description="Minecraft servers" + (
        f". Business: {replacement}" if replacement else ""
    ))
    result, requests = pilot_refresh(monkeypatch, [selected, other],
                                    reread=lambda _: {"items": [final]})
    assert len(requests) == 4
    candidates = result["intelligence"]["contact_candidates"]
    assert not any(candidate["email"] == "creator@example.test" for candidate in candidates)
    assert any(candidate["email"] == "other@example.test"
               and candidate["source_url"].endswith(other["id"]) for candidate in candidates)
    selected_contacts = [candidate["email"] for candidate in candidates
                         if candidate["source_url"] == URL]
    assert selected_contacts == ([replacement] if replacement else [])


def test_pilot_fallback_keeps_observed_contacts_when_legacy_enrichment_returns_no_video(
    monkeypatch,
):
    old_upload = video(publishedAt=(NOW - timedelta(days=150)).isoformat())
    old_upload["id"] = "o" * 11
    result, requests = pilot_refresh(monkeypatch, [old_upload], reread=lambda _: {"items": []})
    assert len(requests) == 4
    assert requests[-1][1]["part"] == "snippet,statistics"
    assert result["latest_content_url"].endswith(old_upload["id"])
    assert any(candidate["email"] == "creator@example.test"
               and candidate["source_url"] == result["latest_content_url"]
               for candidate in result["intelligence"]["contact_candidates"])
    assert "contact_authorized_at" not in result


@pytest.mark.parametrize("change", [
    "unrelated", "old", "future", "private", "upcoming", "unowned", "missing_title",
    "missing_date", "missing_snippet", "missing_status", "malformed_snippet", "malformed_status",
])
def test_pilot_retains_old_sample_when_uploads_cannot_qualify(monkeypatch, change):
    upload = video()
    if change == "unrelated":
        upload["snippet"].update(title="Travel diary", description="Travel only")
    elif change in {"old", "future"}:
        upload["snippet"]["publishedAt"] = (
            NOW + timedelta(days=1) if change == "future" else NOW - timedelta(days=91)
        ).isoformat()
    elif change == "private":
        upload["status"]["privacyStatus"] = "private"
    elif change == "upcoming":
        upload["snippet"]["liveBroadcastContent"] = "upcoming"
    elif change == "unowned":
        upload["snippet"]["channelId"] = "UC" + "z" * 22
    elif change in {"missing_title", "missing_date"}:
        upload["snippet"].pop("title" if change == "missing_title" else "publishedAt")
    elif change in {"missing_snippet", "missing_status"}:
        upload.pop(change.removeprefix("missing_"))
    else:
        upload[change.removeprefix("malformed_")] = "invalid"
    result, requests = pilot_refresh(monkeypatch, [upload])
    assert len(requests) == 4
    assert result["latest_content_url"].endswith("o" * 11)
    assert result["latest_content_title"] == "Old Minecraft SMP"
    assert result["latest_content_published_at"] == NOW - timedelta(days=150)


@pytest.mark.parametrize("campaign_age,age,qualifies", [
    (120, timedelta(days=90), True),
    (120, timedelta(days=90, microseconds=1), False),
    (7, timedelta(days=7), True),
    (7, timedelta(days=7, microseconds=1), False),
])
def test_pilot_promotion_respects_exact_stricter_age_boundary(
    monkeypatch, campaign_age, age, qualifies,
):
    upload = video(publishedAt=(NOW - age).isoformat())
    result, _ = pilot_refresh(monkeypatch, [upload], campaign_age=campaign_age)
    assert result["latest_content_url"].endswith(VIDEO if qualifies else "o" * 11)


@pytest.mark.parametrize("change", [
    "title", "date", "future", "owner", "private", "upcoming", "missing", "snippet", "status",
])
def test_pilot_rejects_selected_upload_metadata_drift_without_returning_research(
    monkeypatch, change,
):
    changed = video()
    if change == "title":
        changed["snippet"]["title"] = "Changed Minecraft title"
    elif change in {"date", "future"}:
        changed["snippet"]["publishedAt"] = (
            NOW + timedelta(days=1) if change == "future" else NOW - timedelta(days=3)
        ).isoformat()
    elif change == "owner":
        changed["snippet"]["channelId"] = "UC" + "z" * 22
    elif change == "private":
        changed["status"]["privacyStatus"] = "private"
    elif change == "upcoming":
        changed["snippet"]["liveBroadcastContent"] = "upcoming"
    elif change in {"snippet", "status"}:
        changed.pop(change)
    with pytest.raises(RuntimeError, match="Selected public Minecraft video"):
        pilot_refresh(monkeypatch, [video()], reread=lambda _: {
            "items": [] if change == "missing" else [changed],
        })


def test_pilot_final_read_failure_and_checkpoint_loss_propagate(monkeypatch):
    def failed_read(_):
        raise YouTubeRequestLimitError(quota_exhausted=True)

    with pytest.raises(YouTubeRequestLimitError):
        pilot_refresh(monkeypatch, [video()], reread=failed_read)
    checkpoint = Mock(side_effect=[None, None, None, InvalidTaskStateError("lease lost")])
    reread = Mock()
    with pytest.raises(InvalidTaskStateError, match="lease lost"):
        pilot_refresh(monkeypatch, [video()], reread=reread, checkpoint=checkpoint)
    reread.assert_not_called()


def test_rank_explains_fit_activity_provenance_and_does_not_expose_email():
    campaign, prospect = fixture()
    result = rank_prospect(campaign, prospect, now=NOW)
    assert result["status"] == "selected"
    assert result["score"] == 100
    assert result["contact_authorized"]
    assert result["last_published_at"] == "2026-10-18T00:00:00+00:00"
    assert result["observed_language"] == "pl"
    assert "creator@example.test" not in json.dumps(result)
    assert result["contact_evidence"][0]["source_url"] == URL


def test_rank_requires_exact_current_business_provenance_and_owner_authority():
    campaign, prospect = fixture()
    prospect["contact_source_url"] = PROFILE
    assert rank_prospect(campaign, prospect, now=NOW)["status"] == "needs_review"
    prospect["intelligence"]["contact_candidates"][0]["observed_at"] = "old"
    assert rank_prospect(campaign, prospect, now=NOW)["status"] == "excluded"


def test_recent_nonminecraft_uploads_do_not_refresh_an_old_matching_sample():
    campaign, prospect = fixture()
    prospect["last_seen_at"] = NOW
    prospect["intelligence"]["activity"]["videos"][0]["topics"] = ["Travel"]
    prospect["intelligence"]["recent_videos"] = [{
        "published_at": (NOW - timedelta(days=150)).isoformat(),
        "metadata_status": "observed_this_run", "topics": ["Minecraft"],
    }]
    result = rank_prospect(campaign, prospect, now=NOW)
    assert result["status"] == "excluded"
    assert any("No observed Minecraft" in gap for gap in result["gaps"])
    prospect["intelligence"]["recent_videos"][0]["published_at"] = NOW.isoformat()
    prospect["intelligence"]["recent_videos"][0]["topics"] = ["Travel"]
    assert rank_prospect(campaign, prospect, now=NOW)["status"] == "excluded"


@pytest.mark.parametrize("change", ["suppressed", "geography", "audience", "api_error"])
def test_rank_excludes_failed_or_ineligible_records(change):
    campaign, prospect = fixture()
    if change == "suppressed":
        prospect["suppressed_at"] = NOW
    elif change == "geography":
        prospect["intelligence"]["geography"]["eligible"] = False
    elif change == "audience":
        prospect["audience_size"] = None
    assert rank_prospect(
        campaign, prospect, now=NOW, error=change == "api_error",
    )["status"] == "excluded"


@pytest.mark.parametrize("limit", [0, 11, True, "2", 1.5])
def test_batch_limits_are_strict(limit):
    with pytest.raises(ValidationError):
        CreatorPilotCreate(actor="fixture", idempotency_key=uuid4(), limit=limit)


def test_pilot_policy_is_allowlisted_bounded_and_cannot_escalate_send_authority():
    assert effective_risk("marketing.creator_pilot", RiskLevel.LOW) == RiskLevel.LOW
    assert capability_max_attempts("marketing.creator_pilot") == 1
    assert CreatorPilotCreate(actor="fixture", idempotency_key=uuid4()).limit == 5
    assert "@" not in safe_excerpt("Business: " + "a" * 60 + "@example.test")


def runner_fixture():
    campaign, prospect = fixture()
    task = {"id": uuid4(), "lease_id": uuid4(), "payload": {
        "campaign_id": str(campaign["id"]), "requested_limit": 1,
        "prospect_ids": [str(prospect["id"])],
    }}
    store = Mock(spec=CreatorPilotStore)
    store.pilot_context.return_value = task, campaign, prospect
    store.save_pilot_research.return_value = campaign, prospect
    return task, store, SimpleNamespace(youtube_api_key="fixture")


def test_runner_fences_before_egress_and_never_swallows_cancel_or_lease_loss(monkeypatch):
    task, store, settings = runner_fixture()
    fetch = Mock()
    monkeypatch.setattr(creator_pilot_runner, "fetch_youtube_prospect", fetch)
    store.pilot_context.side_effect = InvalidTaskStateError("no server reservation")
    with pytest.raises(InvalidTaskStateError):
        execute_creator_pilot(task, store, settings)
    fetch.assert_not_called()
    task, store, settings = runner_fixture()
    fetch.side_effect = InvalidTaskStateError("lease lost at provider checkpoint")
    with pytest.raises(InvalidTaskStateError):
        execute_creator_pilot(task, store, settings)
    store.save_pilot_research.assert_not_called()
    interrupted = threading.Event()
    interrupted.set()
    with pytest.raises(TaskInterruptedError):
        execute_creator_pilot(task, store, settings, interrupt=interrupted)


def test_runner_stops_provider_reads_after_quota_exhaustion_and_returns_safe_gaps(monkeypatch):
    task, store, settings = runner_fixture()
    task["payload"]["prospect_ids"].append(str(uuid4()))
    fetch = Mock(side_effect=YouTubeRequestLimitError(quota_exhausted=True))
    monkeypatch.setattr(creator_pilot_runner, "fetch_youtube_prospect", fetch)
    result = execute_creator_pilot(task, store, settings)
    assert fetch.call_count == 1
    assert result["failed"] == 2 and result["researched"] == 0
    assert result["selected_count"] == 0
    assert result["limits"]["model_requests"] == result["limits"]["messages_sent"] == 0
    store.save_pilot_research.assert_not_called()


def test_runner_success_saves_evidence_without_adding_any_authority(monkeypatch):
    task, store, settings = runner_fixture()
    original = copy.deepcopy(store.pilot_context.return_value[2])
    monkeypatch.setattr(creator_pilot_runner, "fetch_youtube_prospect", Mock(return_value={}))
    result = execute_creator_pilot(task, store, settings)
    assert result["researched"] == 1 and result["failed"] == 0
    assert result["limits"]["contact_authorizations"] == 0
    assert store.pilot_context.return_value[2] == original
    assert store.save_pilot_research.call_count == 1
