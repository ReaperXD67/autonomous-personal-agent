import io
import json
from datetime import UTC, datetime
from urllib.error import HTTPError

import pytest

from app import marketing
from app.marketing import YouTubeRequestLimitError, fetch_youtube_creators

NOW = datetime(2026, 9, 26, tzinfo=UTC)
CAMPAIGN = {
    "product_name": "KarixMC", "min_subscribers": 1000, "max_subscribers": 250000,
    "max_video_age_days": 120, "discovery_queries": ["Minecraft SMP"],
    "results_per_query": 25, "relevance_language": "pl", "region_code": "PL",
}


def channel_id(index):
    return f"UC{index:022}"


def video_id(index):
    return f"{index:011}"


def search_item(index):
    return {
        "id": {"videoId": video_id(index)},
        "snippet": {"channelId": channel_id(index), "channelTitle": "Minecraft creator",
                    "title": "Minecraft SMP server", "publishedAt": NOW.isoformat()},
    }


def metadata(path, parameters):
    ids = parameters["id"].split(",")
    assert len(ids) <= 50
    if path.endswith("channels"):
        return {"items": [{
            "id": identity,
            "snippet": {"country": "PL", "title": "Minecraft creator", "description":
                        f"Business: creator{identity[2:]}@example.test"},
            "statistics": {"subscriberCount": "12000"},
        } for identity in ids]}
    return {"items": [{
        "id": identity, "snippet": {
            "channelId": channel_id(int(identity)), "title": "Minecraft SMP server",
            "publishedAt": NOW.isoformat(), "defaultAudioLanguage": "pl",
        },
    } for identity in ids]}


def test_pages_are_fair_across_queries_and_follow_tokens_even_after_short_page(monkeypatch):
    searches = []

    def read(path, parameters):
        if not path.endswith("search"):
            return metadata(path, parameters)
        query, token = parameters["q"], parameters.get("pageToken")
        searches.append((query, token))
        number = {None: 0, "next-1": 1, "next-2": 2}[token]
        index = number if query == "Minecraft A" else number + 2
        page = {"items": [search_item(index)], "pageInfo": {"totalResults": 1_000_000}}
        if number < 2:
            page["nextPageToken"] = f"next-{number + 1}"
        return page

    monkeypatch.setattr(marketing, "_read_youtube_json", read)
    stats = {}
    found = fetch_youtube_creators("key", {
        **CAMPAIGN, "discovery_queries": ["Minecraft A", "Minecraft B"],
        "search_pages_per_query": 3,
    }, now=NOW, selection_stats=stats)
    assert searches == [(query, token) for token in (None, "next-1", "next-2")
                        for query in ("Minecraft A", "Minecraft B")]
    assert len(found) == 5 and stats["duplicate_channels"] == 1
    assert stats["search_requests"] == stats["search_pages"] == stats["search_results"] == 6
    assert stats["queries_exhausted"] == 2 and stats["queries_incomplete"] == 0
    assert stats["channels_enriched"] == stats["videos_enriched"] == 5
    assert stats["queries_page_limited"] == 0
    assert all(type(value) is int for value in stats.values())
    assert all("contact_email" not in item and "contact_authorized_at" not in item
               for item in found)
    assert all(item["intelligence"]["contact_candidates"][0]["status"] == "unreviewed"
               for item in found)


def test_untrusted_high_limits_cannot_exceed_nine_searches_and_225_channels(monkeypatch):
    calls = []
    searches = 0

    def read(path, parameters):
        nonlocal searches
        calls.append(path)
        if not path.endswith("search"):
            return metadata(path, parameters)
        searches += 1
        assert parameters["maxResults"] == 25
        return {
            "items": [search_item(searches * 100 + index) for index in range(100)],
            "nextPageToken": f"page-{searches}",
        }

    monkeypatch.setattr(marketing, "_read_youtube_json", read)
    stats = {}
    found = fetch_youtube_creators("key", {
        **CAMPAIGN, "discovery_queries": [f"Minecraft {index}" for index in range(30)],
        "results_per_query": 1000, "search_pages_per_query": 1000,
    }, now=NOW, selection_stats=stats)
    assert len(found) == stats["channel_limit"] == 225
    assert searches == stats["search_request_limit"] == 9
    assert stats["queries_page_limited"] == stats["queries_incomplete"] == 3
    assert stats["queries_exhausted"] == 0
    assert stats["channel_requests"] == stats["video_requests"] == 5
    assert len(calls) == 19
    assert stats["channels_enriched"] == stats["videos_enriched"] == 225


def test_duplicate_queries_spend_once_and_default_remains_one_page(monkeypatch):
    calls = []

    def read(path, parameters):
        calls.append(path)
        return {"items": [], "nextPageToken": "more"}

    monkeypatch.setattr(marketing, "_read_youtube_json", read)
    stats = {}
    assert fetch_youtube_creators("key", {
        **CAMPAIGN, "discovery_queries": ["Minecraft SMP"] * 3,
    }, selection_stats=stats) == []
    assert calls == ["/youtube/v3/search"]
    assert stats["query_count"] == stats["search_requests"] == stats["queries_page_limited"] == 1
    assert stats["queries_exhausted"] == 0


@pytest.mark.parametrize("token", ["bad\nvalue", "x" * 1025, ["not a string"], "ą"])
def test_invalid_page_tokens_stop_safely_without_persisting_them(monkeypatch, token):
    calls = []

    def read(path, parameters):
        calls.append(path)
        return {"items": [], "nextPageToken": token}

    monkeypatch.setattr(marketing, "_read_youtube_json", read)
    stats = {}
    assert fetch_youtube_creators("key", {**CAMPAIGN, "search_pages_per_query": 3},
                                  selection_stats=stats) == []
    assert calls == ["/youtube/v3/search"]
    assert stats["pagination_errors"] == stats["queries_incomplete"] == 1
    assert all(type(value) is int for value in stats.values())


def test_repeated_page_token_stops_before_cycle_and_counts_duplicate_channels(monkeypatch):
    calls = []

    def read(path, parameters):
        if not path.endswith("search"):
            return metadata(path, parameters)
        calls.append(parameters.get("pageToken"))
        return {"items": [search_item(0)], "nextPageToken": "same-token"}

    monkeypatch.setattr(marketing, "_read_youtube_json", read)
    stats = {}
    found = fetch_youtube_creators("key", {**CAMPAIGN, "search_pages_per_query": 3},
                                   now=NOW, selection_stats=stats)
    assert calls == [None, "same-token"] and len(found) == 1
    assert stats["pagination_errors"] == stats["duplicate_channels"] == 1
    assert stats["queries_exhausted"] == 0


def test_denied_initial_reservation_makes_no_network_call(monkeypatch):
    monkeypatch.setattr(marketing, "_read_youtube_json", lambda *args: pytest.fail("network call"))
    stats = {}
    assert fetch_youtube_creators("key", CAMPAIGN, selection_stats=stats,
                                  reserve_search_request=lambda: False) == []
    assert stats["search_budget_exhausted"] == 1
    assert stats["search_requests"] == stats["queries_started"] == 0
    assert stats["queries_incomplete"] == 1


def test_shared_budget_stop_preserves_already_observed_strict_poland_prospects(monkeypatch):
    events = []
    reservations = 0

    def reserve():
        nonlocal reservations
        reservations += 1
        events.append("reserve")
        return reservations <= 2

    def read(path, parameters):
        events.append(path.rsplit("/", 1)[-1])
        if not path.endswith("search"):
            return metadata(path, parameters)
        return {"items": [search_item(reservations)], "nextPageToken": "more"}

    monkeypatch.setattr(marketing, "_read_youtube_json", read)
    stats = {}
    found = fetch_youtube_creators("key", {
        **CAMPAIGN, "discovery_queries": ["Minecraft A", "Minecraft B", "Minecraft C"],
        "search_pages_per_query": 3, "country_mode": "strict", "target_country": "PL",
    }, now=NOW, selection_stats=stats, reserve_search_request=reserve)
    assert events == ["reserve", "search", "reserve", "search", "reserve", "channels", "videos"]
    assert len(found) == 2 and stats["search_requests"] == 2
    assert stats["search_budget_exhausted"] == 1 and stats["quota_exhausted"] == 0
    assert stats["queries_incomplete"] == 3
    assert all(item["intelligence"]["geography"]["country_code"] == "PL" for item in found)


@pytest.mark.parametrize("status,reason,quota,rate", [
    (403, "quotaExceeded", True, False), (403, "dailyLimitExceeded", True, False),
    (403, "userRateLimitExceeded", False, True), (429, "unknown", False, True),
])
def test_provider_limit_errors_are_classified_without_leaking_body_or_key(
    monkeypatch, status, reason, quota, rate,
):
    provider_value = "synthetic-provider-redaction-fixture"

    class Opener:
        def open(self, request, timeout):
            body = json.dumps({"error": {
                "message": provider_value, "errors": [{"reason": reason}],
            }})
            raise HTTPError(request.full_url, status, provider_value, {}, io.BytesIO(body.encode()))

    monkeypatch.setattr(marketing, "build_opener", lambda *args: Opener())
    with pytest.raises(YouTubeRequestLimitError) as caught:
        marketing._read_youtube_json("/youtube/v3/search", {"key": provider_value})
    assert caught.value.quota_exhausted is quota and caught.value.rate_limited is rate
    assert provider_value not in str(caught.value)
    assert "googleapis" not in str(caught.value)
    assert caught.value.__suppress_context__


def test_quota_failure_does_not_retry_queries_or_start_enrichment(monkeypatch):
    calls = []

    def read(path, parameters):
        calls.append(path)
        if len(calls) == 1:
            return {"items": [search_item(0)], "nextPageToken": "more"}
        raise YouTubeRequestLimitError(quota_exhausted=True)

    monkeypatch.setattr(marketing, "_read_youtube_json", read)
    stats = {}
    found = fetch_youtube_creators("key", {
        **CAMPAIGN, "discovery_queries": ["Minecraft A", "Minecraft B", "Minecraft C"],
        "search_pages_per_query": 3,
    }, now=NOW, selection_stats=stats)
    assert calls == ["/youtube/v3/search"] * 2 and len(found) == 1
    assert stats["quota_exhausted"] == stats["search_failures"] == 1
    assert stats["search_pages"] == 1 and stats["channel_requests"] == stats["video_requests"] == 0
    assert stats["queries_incomplete"] == 3
    assert found[0]["intelligence"]["enrichment_status"] == "partial"


def test_quota_during_channel_enrichment_keeps_verified_batch_and_no_more_requests(monkeypatch):
    calls = []
    searches = 0
    channel_batches = 0

    def read(path, parameters):
        nonlocal searches, channel_batches
        calls.append(path)
        if path.endswith("search"):
            searches += 1
            return {"items": [search_item(searches * 25 + index) for index in range(25)]}
        if path.endswith("channels"):
            channel_batches += 1
            if channel_batches == 2:
                raise YouTubeRequestLimitError(quota_exhausted=True)
        return metadata(path, parameters)

    monkeypatch.setattr(marketing, "_read_youtube_json", read)
    stats = {}
    found = fetch_youtube_creators("key", {
        **CAMPAIGN, "discovery_queries": ["Minecraft A", "Minecraft B", "Minecraft C"],
        "country_mode": "strict", "target_country": "PL",
    }, now=NOW, selection_stats=stats)
    assert len(found) == 50 and stats["reviewed"] == 75
    assert stats["excluded_country_unknown"] == 25
    assert stats["quota_exhausted"] == stats["enrichment_failures"] == 1
    assert stats["channel_requests"] == 2 and stats["video_requests"] == 0
    assert stats["channels_enriched"] == 50 and len(calls) == 5


def test_rate_limit_during_video_enrichment_stops_remaining_batches(monkeypatch):
    searches = 0

    def read(path, parameters):
        nonlocal searches
        if path.endswith("search"):
            searches += 1
            return {"items": [search_item(searches * 25 + index) for index in range(25)]}
        if path.endswith("videos"):
            raise YouTubeRequestLimitError(rate_limited=True)
        return metadata(path, parameters)

    monkeypatch.setattr(marketing, "_read_youtube_json", read)
    stats = {}
    found = fetch_youtube_creators("key", {
        **CAMPAIGN, "discovery_queries": ["Minecraft A", "Minecraft B", "Minecraft C"],
    }, now=NOW, selection_stats=stats)
    assert len(found) == 75 and stats["video_requests"] == 1
    assert stats["rate_limited"] == stats["enrichment_failures"] == 1
    assert stats["videos_enriched"] == 0


def test_search_failure_keeps_previous_results_and_marks_incomplete_coverage(monkeypatch):
    searches = 0

    def read(path, parameters):
        nonlocal searches
        if not path.endswith("search"):
            return metadata(path, parameters)
        searches += 1
        if searches == 2:
            raise RuntimeError("Untrusted provider diagnostic")
        return {"items": [search_item(0)]}

    monkeypatch.setattr(marketing, "_read_youtube_json", read)
    stats = {}
    found = fetch_youtube_creators("key", {
        **CAMPAIGN, "discovery_queries": ["Minecraft A", "Minecraft B", "Minecraft C"],
    }, now=NOW, selection_stats=stats)
    assert len(found) == 1 and stats["search_failures"] == 1
    assert stats["queries_exhausted"] == 1 and stats["queries_incomplete"] == 2
    assert stats["channel_requests"] == stats["video_requests"] == 1
    assert "Untrusted" not in json.dumps(stats)


def test_malformed_results_are_counted_and_not_given_false_country_evidence(monkeypatch):
    def read(path, parameters):
        if path.endswith("search"):
            return {"items": [None, [], {}, {"id": {}, "snippet": {}}, search_item(0)]}
        return {"items": "invalid list"}

    monkeypatch.setattr(marketing, "_read_youtube_json", read)
    stats = {}
    found = fetch_youtube_creators("key", CAMPAIGN, now=NOW, selection_stats=stats)
    assert len(found) == 1 and stats["invalid_results"] == 4
    assert stats["search_results"] == 5 and stats["enrichment_failures"] == 2
    assert stats["channels_enriched"] == stats["videos_enriched"] == 0
    assert found[0]["intelligence"]["geography"]["country_code"] is None


def test_missing_search_result_list_is_failure_not_exhaustive_empty_search(monkeypatch):
    monkeypatch.setattr(marketing, "_read_youtube_json", lambda *args: {})
    stats = {}
    assert fetch_youtube_creators("key", CAMPAIGN, selection_stats=stats) == []
    assert stats["search_failures"] == stats["search_requests"] == 1
    assert stats["search_pages"] == stats["queries_exhausted"] == 0
    assert stats["queries_incomplete"] == 1


@pytest.mark.parametrize("interrupt_at", [1, 2, 3, 4, 5, 6, 7])
def test_cancellation_propagates_before_each_search_or_metadata_batch(monkeypatch, interrupt_at):
    checkpoints = 0
    searches = 0
    requests = 0

    class Cancelled(RuntimeError):
        pass

    def checkpoint():
        nonlocal checkpoints
        checkpoints += 1
        if checkpoints == interrupt_at:
            raise Cancelled("Task cancelled")

    def read(path, parameters):
        nonlocal searches, requests
        requests += 1
        if path.endswith("search"):
            searches += 1
            return {"items": [search_item(searches * 25 + index) for index in range(25)]}
        return metadata(path, parameters)

    monkeypatch.setattr(marketing, "_read_youtube_json", read)
    with pytest.raises(Cancelled):
        fetch_youtube_creators("key", {
            **CAMPAIGN, "discovery_queries": ["Minecraft A", "Minecraft B", "Minecraft C"],
        }, now=NOW, checkpoint=checkpoint)
    assert requests == interrupt_at - 1


def test_cancellation_does_not_reserve_a_search_call(monkeypatch):
    class Cancelled(RuntimeError):
        pass

    def checkpoint():
        raise Cancelled("Task cancelled")

    with pytest.raises(Cancelled):
        fetch_youtube_creators(
            "key", CAMPAIGN, checkpoint=checkpoint,
            reserve_search_request=lambda: pytest.fail("reserved after cancellation"),
        )
