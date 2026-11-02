from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.marketing_store import MarketingStore


def packet(identity="existing"):
    return {
        "platform": "youtube", "external_id": identity, "display_name": "Fixture",
        "profile_url": "https://www.youtube.com/@fixture", "audience_size": 100,
        "latest_content_title": "Minecraft", "latest_content_url": None,
        "latest_content_published_at": None, "discovery_query": "Minecraft",
        "relevance_score": 75, "relevance_reasons": [], "intelligence": {},
    }


def persistence_store(*, protected=True, existing_changes=None):
    existing = {
        "id": uuid4(), "profile_url": packet()["profile_url"], "suppressed_at": None,
        "status": "discovered", "intelligence": {}, **(existing_changes or {}),
    }
    connection = Mock()
    mutations = []
    summary = []

    def execute(query, parameters):
        if query.startswith("SELECT id, updated_at FROM marketing_campaigns"):
            return Mock(fetchone=lambda: {"id": uuid4(), "updated_at": datetime.now(UTC)})
        if "SELECT id, profile_url, suppressed_at" in query:
            return Mock(fetchone=lambda: existing if parameters[2] == "existing" else None)
        if "INSERT INTO marketing_prospects" in query:
            mutations.append(parameters[2])
            return Mock(rowcount=1)
        if query.startswith("UPDATE marketing_campaigns SET last_scan_at"):
            summary.append(parameters[0].obj)
            return Mock(rowcount=1)
        raise AssertionError("Unexpected persistence query")

    connection.execute.side_effect = execute
    store = MarketingStore.__new__(MarketingStore)
    store.connect = Mock(return_value=nullcontext(connection))
    store._discovery_evidence_protected = Mock(return_value=protected)
    store._append_audit = Mock()
    return store, connection, existing, mutations, summary


def test_bulk_scan_preserves_active_existing_evidence_and_still_discovers_new_creators():
    store, connection, existing, mutations, summary = persistence_store()
    result = store.save_discovered_prospects(uuid4(), [packet(), packet("brand_new")])
    assert result == {"new": 1, "updated": 0}
    assert mutations == ["brand_new"]
    store._discovery_evidence_protected.assert_called_once_with(connection, existing["id"])
    assert summary == [{"protected_count": 1}]
    assert store._append_audit.call_args.kwargs["result_metadata"] == {"protected_count": 1}
    connection.commit.assert_called_once()


def test_unprotected_existing_creator_refreshes_and_aggregate_count_cannot_be_forged():
    store, _, _, mutations, summary = persistence_store(protected=False)
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
def test_identity_and_suppression_guards_run_before_active_evidence_selection(changes):
    store, _, _, mutations, summary = persistence_store(existing_changes=changes)
    assert store.save_discovered_prospects(uuid4(), [packet()]) == {"new": 0, "updated": 0}
    assert mutations == [] and summary == [{"protected_count": 0}]
    store._discovery_evidence_protected.assert_not_called()
    store._append_audit.assert_not_called()
