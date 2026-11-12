from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app import creator_discovery_history as history_module
from app.creator_discovery_history import HistoryIndex, identity_keys
from app.marketing_store import MarketingStore


def packet(identity="existing", **changes):
    handle = "fixture" if identity == "existing" else f"fixture_{identity}"
    return {
        "platform": "youtube", "external_id": identity, "display_name": "Fixture",
        "profile_url": f"https://www.youtube.com/@{handle}", "audience_size": 100,
        "latest_content_title": "Minecraft", "latest_content_url": None,
        "latest_content_published_at": None, "discovery_query": "Minecraft",
        "relevance_score": 75, "relevance_reasons": [], "intelligence": {}, **changes,
    }


def persistence_store(monkeypatch, *, protected=True, existing_changes=None, histories=None):
    existing = {
        **packet(), "id": uuid4(), "suppressed_at": None,
        "status": "discovered", "intelligence": {}, **(existing_changes or {}),
    }
    connection = Mock()
    mutations = []
    summary = []
    rows_by_identity = {(existing["platform"], existing["external_id"]): existing}
    connection.saved_rows = rows_by_identity
    history = HistoryIndex([(identity_keys(existing), protected)])
    loader = Mock(side_effect=histories) if histories is not None else Mock(return_value=history)
    monkeypatch.setattr(history_module, "load_history", loader)
    monkeypatch.setattr(history_module, "lock_history_writers", Mock())

    def execute(query, parameters=None):
        if query.startswith("SELECT id, updated_at FROM marketing_campaigns"):
            return Mock(fetchone=lambda: {"id": uuid4(), "updated_at": datetime.now(UTC)})
        if query.startswith("SELECT p.* FROM marketing_prospects p"):
            assert "jsonb_to_recordset" in query and "ORDER BY p.id FOR UPDATE" in query
            selected = {(item["platform"], item["external_id"]) for item in parameters[1].obj}
            rows = [row for identity, row in rows_by_identity.items() if identity in selected]
            return Mock(fetchall=lambda: rows)
        if query.startswith("SELECT pg_advisory_xact_lock"):
            return Mock()
        if "INSERT INTO marketing_prospects" in query:
            mutations.append(parameters[2])
            identity = (parameters[1], parameters[2])
            prior = rows_by_identity.get(identity, {})
            saved = {
                **prior, "id": prior.get("id", uuid4()), "campaign_id": parameters[0],
                "platform": parameters[1], "external_id": parameters[2],
                "display_name": parameters[3], "profile_url": parameters[4],
                "audience_size": parameters[5], "latest_content_title": parameters[6],
                "latest_content_url": parameters[7], "latest_content_published_at": parameters[8],
                "discovery_query": parameters[9], "relevance_score": parameters[10],
                "relevance_reasons": parameters[11].obj, "intelligence": parameters[12].obj,
                "status": prior.get("status", "discovered"),
                "suppressed_at": prior.get("suppressed_at"),
            }
            rows_by_identity[identity] = saved
            return Mock(rowcount=1, fetchone=lambda: saved)
        if query.startswith("UPDATE marketing_campaigns SET last_scan_at"):
            summary.append(parameters[0].obj)
            return Mock(rowcount=1)
        raise AssertionError("Unexpected persistence query")

    connection.execute.side_effect = execute
    store = MarketingStore.__new__(MarketingStore)
    store.connect = Mock(return_value=nullcontext(connection))
    store._discovery_evidence_protected = Mock()
    store._append_audit = Mock()
    return store, connection, existing, mutations, summary


def test_bulk_scan_preserves_active_existing_evidence_and_still_discovers_new_creators(monkeypatch):
    store, connection, _, mutations, summary = persistence_store(monkeypatch)
    result = store.save_discovered_prospects(uuid4(), [packet(), packet("brand_new")])
    assert result == {"new": 1, "updated": 0}
    assert mutations == ["brand_new"]
    store._discovery_evidence_protected.assert_not_called()
    history_module.lock_history_writers.assert_called_once_with(connection)
    assert history_module.load_history.call_count == 2
    assert summary == [{"protected_count": 1}]
    assert store._append_audit.call_args.kwargs["result_metadata"] == {"protected_count": 1}
    connection.commit.assert_called_once()


def test_unprotected_existing_creator_refreshes_and_aggregate_count_cannot_be_forged(monkeypatch):
    store, _, _, mutations, summary = persistence_store(monkeypatch, protected=False)
    result = store.save_discovered_prospects(
        uuid4(), [packet()], selection_stats={"fetched": 1, "protected_count": 99},
    )
    assert result == {"new": 0, "updated": 1}
    assert mutations == ["existing"]
    assert summary == [{"fetched": 1, "protected_count": 0}]
    store._append_audit.assert_not_called()


@pytest.mark.parametrize("changes", [
    {"profile_url": "https://www.youtube.com/@changed_fixture"},
    {"suppressed_at": datetime(2026, 11, 2, tzinfo=UTC)},
    {"status": "suppressed"}, {"status": "bounced"},
])
def test_identity_and_suppression_guards_preserve_rows_without_counting_history(
    monkeypatch, changes,
):
    store, _, _, mutations, summary = persistence_store(monkeypatch, existing_changes=changes)
    assert store.save_discovered_prospects(uuid4(), [packet()]) == {"new": 0, "updated": 0}
    assert mutations == [] and summary == [{"protected_count": 0}]
    store._discovery_evidence_protected.assert_not_called()
    store._append_audit.assert_not_called()


def test_frozen_business_alias_prevents_new_cross_campaign_duplicate(monkeypatch):
    frozen = HistoryIndex([({("email", "old-business@example.test")}, True)])
    store, _, _, mutations, summary = persistence_store(monkeypatch, histories=[frozen, frozen])
    incoming = packet("new_alias", contact_email=" OLD-BUSINESS@example.test ")
    assert store.save_discovered_prospects(uuid4(), [incoming]) == {"new": 0, "updated": 0}
    assert mutations == [] and summary == [{"protected_count": 1}]


def test_identity_growth_after_sender_wait_skips_instead_of_locking_late(monkeypatch):
    incoming = packet("new_candidate")
    before = HistoryIndex([(identity_keys(incoming), False)])
    expanded = identity_keys(incoming) | {("email", "newly-known@example.test")}
    after = HistoryIndex([(expanded, False)])
    store, connection, _, mutations, summary = persistence_store(
        monkeypatch, histories=[before, after],
    )
    assert store.save_discovered_prospects(uuid4(), [incoming]) == {"new": 0, "updated": 0}
    assert mutations == [] and summary == [{"protected_count": 1}]
    acquired = [call.args[1][0] for call in connection.execute.call_args_list
                if call.args[0].startswith("SELECT pg_advisory_xact_lock")]
    assert "creator-email:newly-known@example.test" not in acquired
    assert acquired == sorted(acquired)


def test_repeated_brand_new_identity_counts_one_insert_and_one_refresh(monkeypatch):
    store, connection, _, mutations, summary = persistence_store(monkeypatch)
    channel = "UC" + "A" * 22
    first = packet("brand_new", intelligence={
        "source_channel_id": channel,
        "contact_candidates": [{
            "email": "retained@example.test",
            "source_url": f"https://www.youtube.com/channel/{channel}",
            "evidence": "Business inquiries: retained@example.test",
            "observed_at": datetime.now(UTC).isoformat(),
        }],
    })
    second = {**first, "display_name": "Updated public name",
              "intelligence": {"source_channel_id": channel, "contact_candidates": [],
                               "current_marker": "second observation"}}
    assert store.save_discovered_prospects(uuid4(), [first, second]) == {"new": 1, "updated": 1}
    assert mutations == ["brand_new", "brand_new"]
    saved = connection.saved_rows[("youtube", "brand_new")]
    assert saved["display_name"] == "Updated public name"
    assert saved["intelligence"]["current_marker"] == "second observation"
    assert saved["intelligence"]["contact_candidates"] == []
    assert [item["email"] for item in saved["intelligence"]["contact_history"]] == [
        "retained@example.test",
    ]
    assert summary == [{"protected_count": 0}]


def test_repeated_new_identity_cannot_switch_public_profile_within_batch(monkeypatch):
    store, connection, _, mutations, summary = persistence_store(monkeypatch)
    first = packet("brand_new", intelligence={"current_marker": "retained"})
    second = {**first, "profile_url": "https://www.youtube.com/@different",
              "intelligence": {"current_marker": "must not replace"}}
    assert store.save_discovered_prospects(uuid4(), [first, second]) == {"new": 1, "updated": 0}
    assert mutations == ["brand_new"]
    saved = connection.saved_rows[("youtube", "brand_new")]
    assert saved["profile_url"] == first["profile_url"]
    assert saved["intelligence"]["current_marker"] == "retained"
    assert summary == [{"protected_count": 0}]


def test_fresh_shared_business_alias_freezes_entire_batch_before_any_insert(monkeypatch):
    canonical = "UC" + "K" * 22
    durable = HistoryIndex([({("channel", canonical)}, True)])
    baseline = durable.keys({"platform": "youtube", "external_id": canonical})
    store, _, _, mutations, summary = persistence_store(monkeypatch, histories=[durable, durable])
    contact = {"contact_candidates": [{"email": " Fresh@Example.TEST "}]}
    first = packet(canonical, intelligence=contact)
    second = packet("UC" + "C" * 22, intelligence=contact)
    assert store.save_discovered_prospects(uuid4(), [first, second]) == {"new": 0, "updated": 0}
    assert mutations == [] and summary == [{"protected_count": 2}]
    assert durable.keys({"platform": "youtube", "external_id": canonical}) == baseline
    assert not durable.protected(second)
