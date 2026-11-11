from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.creator_automation import run_block_reason
from app.creator_automation_models import CreatorOutreachResume, CreatorOutreachStop
from app.creator_automation_routes import resume_outreach, stop_outreach
from app.creator_outreach_stop import (
    CreatorOutreachStopMixin,
    action_outreach_stop_reason,
    outreach_stop_reason,
)
from app.marketing import outreach_context_error
from app.marketing_models import MarketingCampaignUpdate
from app.marketing_store import MarketingCampaignNotFoundError
from app.models import ApprovalDecision
from app.store import Database, InvalidTaskStateError


def packet(**changes):
    return {"action_type": "communications.email_send", "private_context": {
        "marketing": {"campaign_id": str(uuid4()), **changes},
    }}


def test_stop_prevents_manual_and_delegated_egress_before_other_context_checks():
    campaign = {"outreach_paused": True, "outreach_epoch": 1}
    action = packet(outreach_epoch=0)
    assert "stopped by the owner" in outreach_context_error(campaign, {}, action)
    assert "stopped by the owner" in run_block_reason({}, campaign)


@pytest.mark.parametrize("recorded", [{}, {"outreach_epoch": 0}, {"outreach_epoch": 1}])
def test_resuming_cannot_revive_a_packet_from_before_the_stop(recorded):
    reason = outreach_stop_reason({"outreach_paused": False, "outreach_epoch": 2}, recorded)
    assert "old approval cannot resume" in reason
    assert outreach_stop_reason({"outreach_paused": False, "outreach_epoch": 2},
                                {"outreach_epoch": 2}) is None


def test_legacy_packet_remains_valid_before_any_stop():
    assert outreach_stop_reason({}, {}) is None


def test_creator_stop_guard_leaves_career_and_unrelated_actions_alone():
    connection = Mock()
    assert action_outreach_stop_reason(connection, {
        "action_type": "communications.email_send", "private_context": {"career": {}},
    }) is None
    assert action_outreach_stop_reason(connection, {
        "action_type": "applications.browser_submit", "private_context": {},
    }) is None
    connection.execute.assert_not_called()


def test_approval_locks_campaign_and_refuses_absent_or_stopped_authority():
    action = packet()
    for campaign, expected in [(None, "no longer exists"),
                               ({"outreach_paused": True}, "stopped by the owner")]:
        connection = Mock()
        connection.execute.return_value.fetchone.return_value = campaign
        assert expected in action_outreach_stop_reason(connection, action)
        query, params = connection.execute.call_args.args
        assert "FOR SHARE" in query
        assert params == (action["private_context"]["marketing"]["campaign_id"],)


def test_stopped_exact_task_cannot_reserve_a_slot_or_record_an_approval():
    task_id = uuid4()
    task = {"id": task_id, "status": "pending_approval", "payload": {"action_digest": "frozen"}}
    action = {**packet(), "context_hash": "frozen",
              "expires_at": datetime.now(UTC) + timedelta(hours=1)}
    connection = Mock()
    connection.execute.return_value.fetchone.side_effect = [
        task, action, {"current_time": datetime.now(UTC)}, {"outreach_paused": True},
    ]
    store = Database("unused")
    store._reserve_email_schedule = Mock()
    with pytest.raises(InvalidTaskStateError, match="stopped by the owner"):
        store.decide_task(task_id, ApprovalDecision(decision="approved", actor="operator"),
                          connection=connection)
    store._reserve_email_schedule.assert_not_called()
    assert not any("INSERT INTO task_approvals" in call.args[0]
                   for call in connection.execute.call_args_list)


@pytest.mark.parametrize("confirmation", ["resume", "start", "", "Start mailing now"])
def test_resume_requires_explicit_start_mailing_confirmation(confirmation):
    with pytest.raises(ValidationError):
        CreatorOutreachResume(actor="operator", confirmation=confirmation)
    assert CreatorOutreachResume(actor="operator", confirmation="start mailing now")


def test_normal_campaign_update_cannot_clear_the_owner_stop():
    assert "outreach_paused" not in MarketingCampaignUpdate.model_fields
    assert "outreach_epoch" not in MarketingCampaignUpdate.model_fields
    assert MarketingCampaignUpdate.model_config["extra"] == "forbid"


def test_stop_and_resume_routes_call_only_the_bound_campaign_store():
    store = Mock()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(creator_automation=store)))
    campaign_id = uuid4()
    stop_outreach(request, campaign_id, CreatorOutreachStop(actor="operator", reason="Owner stop"))
    store.stop_outreach.assert_called_once_with(campaign_id, "operator", "Owner stop")
    resume_outreach(request, campaign_id,
                    CreatorOutreachResume(actor="operator", confirmation="start mailing now"))
    store.resume_outreach.assert_called_once_with(campaign_id, "operator")


class StopFixture(CreatorOutreachStopMixin):
    def __init__(self, *, exists=True):
        self.exists = exists
        self.campaign = {"outreach_paused": False, "outreach_epoch": 0,
                         "outreach_stopped_at": None, "outreach_stopped_by": None,
                         "outreach_stop_reason": None}
        self.tasks = {uuid4(): "queued", uuid4(): "pending_approval", uuid4(): "running"}
        self.requested = set()
        self.stop_committed = False
        self._append_audit = Mock()
        self.run_paused = False

    @contextmanager
    def connect(self):
        yield self

    def commit(self):
        self.stop_committed = self.campaign["outreach_paused"]

    def execute(self, query, params=()):
        value, values = None, []
        if query.startswith("SELECT * FROM marketing_campaigns"):
            value = dict(self.campaign) if self.exists else None
        elif query.startswith("UPDATE marketing_campaigns SET outreach_paused=true"):
            if not self.campaign["outreach_paused"]:
                self.campaign["outreach_epoch"] += 1
            self.campaign.update(outreach_paused=True, active=False,
                                 outreach_stopped_by=params[0], outreach_stop_reason=params[1])
            value = dict(self.campaign)
        elif query.startswith("UPDATE creator_automation_runs"):
            self.run_paused = True
        elif query.startswith("SELECT t.id FROM agent_tasks"):
            values = [{"id": key} for key, status in self.tasks.items()
                      if status in {"queued", "pending_approval", "running"}
                      and key not in self.requested]
        elif query.startswith("SELECT count(*) FILTER"):
            value = {"in_flight": 1, "ambiguous": 2}
        elif query.startswith("UPDATE marketing_campaigns SET outreach_paused=false"):
            self.campaign["outreach_paused"] = False
            value = dict(self.campaign) if self.exists else None
        return Mock(fetchone=Mock(return_value=value), fetchall=Mock(return_value=values))

    def cancel_task(self, task_id, request):
        assert self.stop_committed, "Task locks must follow a committed durable campaign stop"
        self.requested.add(task_id)
        if self.tasks[task_id] != "running":
            self.tasks[task_id] = "cancelled"
        return {"status": self.tasks[task_id]}


def test_stop_commits_fence_before_cancelling_all_task_pages_and_preserves_receipts():
    store = StopFixture()
    result = store.stop_outreach(uuid4(), "operator", "Owner stop")
    assert store.run_paused and not store.campaign["active"]
    assert result["outreach_paused"] and result["outreach_epoch"] == 1
    assert result["cancelled_tasks"] == 2 and result["cancellation_requested_tasks"] == 1
    assert result["in_flight_actions"] == 1 and result["ambiguous_actions"] == 2
    assert store.stop_outreach(uuid4(), "operator", "Still stopped")["outreach_epoch"] == 1
    store.resume_outreach(uuid4(), "operator")
    assert not store.campaign["outreach_paused"] and store.campaign["outreach_epoch"] == 1
    assert not store.campaign["active"] and store.run_paused
    assert all(status in {"cancelled", "running"} for status in store.tasks.values())


def test_stop_unknown_campaign_does_not_cancel_unrelated_tasks():
    store = StopFixture(exists=False)
    with pytest.raises(MarketingCampaignNotFoundError):
        store.stop_outreach(uuid4(), "operator", "Owner stop")
    assert not store.requested and not store.stop_committed
