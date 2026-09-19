from unittest.mock import Mock
from uuid import uuid4

import pytest

from app import job_worker
from app.marketing_store import MarketingStore


def research_context():
    campaign_id, prospect_id = uuid4(), uuid4()
    store = Mock(spec=MarketingStore)
    store.recent_marketing_scan_count.return_value = 1
    store.get_campaign.return_value = {"discovery_queries": ["Minecraft SMP"]}
    store.get_prospect.return_value = {
        "id": prospect_id, "campaign_id": campaign_id,
        "platform": "youtube", "suppressed_at": None,
        "profile_url": "https://www.youtube.com/@fixture",
    }
    task = {
        "kind": "marketing.creator_discovery",
        "payload": {"campaign_id": str(campaign_id), "prospect_id": str(prospect_id)},
    }
    return store, task, prospect_id


def test_single_creator_refresh_is_accounted_and_never_authorizes(monkeypatch):
    store, task, prospect_id = research_context()
    result = {"intelligence": {
        "enrichment_status": "complete",
        "contact_candidates": [{"email": "business@example.test", "status": "unreviewed"}],
    }}
    fetch = Mock(return_value=result)
    monkeypatch.setattr(job_worker, "fetch_youtube_prospect", fetch)
    output = job_worker.execute_career_task(task, store)
    store.save_prospect_research.assert_called_once_with(
        prospect_id, result,
        expected_profile_url=store.get_prospect.return_value["profile_url"],
        expected_campaign_id=store.get_prospect.return_value["campaign_id"],
    )
    store.save_discovered_prospects.assert_not_called()
    assert output["queries"] == 0
    assert output["contact_candidates_unreviewed"] == 1
    assert output["contact_authorizations_granted"] == 0
    assert output["research_complete"] == 1


@pytest.mark.parametrize("change", [
    {"campaign_id": uuid4()}, {"platform": "other"}, {"suppressed_at": "2026-09-19"},
])
def test_creator_refresh_refuses_invalid_scope_before_network(monkeypatch, change):
    store, task, _ = research_context()
    store.get_prospect.return_value.update(change)
    fetch = Mock()
    monkeypatch.setattr(job_worker, "fetch_youtube_prospect", fetch)
    with pytest.raises(ValueError):
        job_worker.execute_career_task(task, store)
    fetch.assert_not_called()


def test_refresh_shares_daily_discovery_limit(monkeypatch):
    store, task, _ = research_context()
    store.recent_marketing_scan_count.return_value = 31
    fetch = Mock()
    monkeypatch.setattr(job_worker, "fetch_youtube_prospect", fetch)
    with pytest.raises(RuntimeError, match="Daily YouTube"):
        job_worker.execute_career_task(task, store)
    fetch.assert_not_called()
