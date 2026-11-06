from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.application_browser import canonical_hash
from app.creator_draft_store import CreatorDraftStore
from app.creator_pilot import KIND, campaign_snapshot
from app.creator_pilot_store import CreatorPilotCreate, CreatorPilotStore, research_identity
from app.marketing_store import MarketingOutreachError
from app.store import InvalidTaskStateError

CHANNEL = "UCabcdefghijklmnopqrstuv"


def prospect(campaign_id=None, **updates):
    row = {
        "id": uuid4(), "campaign_id": campaign_id or uuid4(), "platform": "youtube",
        "external_id": CHANNEL, "profile_url": f"https://www.youtube.com/channel/{CHANNEL}",
        "status": "discovered", "suppressed_at": None, "contact_email": None,
        "intelligence": {"topics": ["Minecraft"]},
    }
    row.update(updates)
    return row


def test_explicit_ids_infer_limit_and_omission_preserves_automatic_default():
    identities = [uuid4(), uuid4()]
    request = CreatorPilotCreate(actor="fixture", idempotency_key=uuid4(), prospect_ids=identities)
    assert request.limit == 2 and request.prospect_ids == identities
    assert CreatorPilotCreate(actor="fixture", idempotency_key=uuid4()).limit == 5
    assert CreatorPilotCreate(actor="fixture", idempotency_key=uuid4()).prospect_ids is None


@pytest.mark.parametrize("selection", [[], ["not-a-uuid"], [True], [uuid4()] * 2,
                                        [uuid4() for _ in range(11)]])
def test_explicit_ids_are_bounded_unique_uuids(selection):
    with pytest.raises(ValidationError):
        CreatorPilotCreate(actor="fixture", idempotency_key=uuid4(), prospect_ids=selection)


def test_explicit_limit_must_equal_identity_count_when_supplied():
    with pytest.raises(ValidationError, match="match the requested limit"):
        CreatorPilotCreate(actor="fixture", idempotency_key=uuid4(), limit=2,
                           prospect_ids=[uuid4()])


def test_identity_unifies_channel_handle_host_variants_and_known_addresses():
    row = prospect(external_id="imported-handle", profile_url="https://youtube.com/@Builder/",
                   contact_email=" Creator@Example.Test ", intelligence={
                       "source_channel_id": CHANNEL,
                       "contact_candidates": [{"email": "Other@Example.Test"}],
                   })
    channels, profiles, emails, keys = research_identity(row)
    assert channels == {CHANNEL}
    assert {"https://www.youtube.com/@builder", "https://youtube.com/@builder",
            f"https://www.youtube.com/channel/{CHANNEL}".casefold(),
            f"https://youtube.com/channel/{CHANNEL}".casefold()} <= profiles
    assert emails == {"creator@example.test", "other@example.test"}
    assert ("creator", "youtube", "imported-handle") in keys


@pytest.mark.parametrize("mode", ["missing", "foreign", "identity_duplicate", "ineligible"])
def test_explicit_candidates_refuse_the_entire_selection_without_substitution(mode):
    campaign_id = uuid4()
    first = prospect(campaign_id)
    second = prospect(campaign_id, external_id="UC" + "z" * 22,
                      profile_url="https://www.youtube.com/@Another")
    rows = [first, second]
    if mode == "missing":
        rows = [first]
    elif mode == "foreign":
        second["campaign_id"] = uuid4()
    elif mode == "identity_duplicate":
        second["intelligence"]["source_channel_id"] = CHANNEL
    connection = Mock()
    connection.execute.return_value.fetchall.return_value = rows
    store = CreatorPilotStore("unused")
    store._explicit_group_ineligibility = Mock(return_value="Not eligible"
                                              if mode == "ineligible" else None)
    with pytest.raises(MarketingOutreachError):
        store._explicit_candidates(connection, campaign_id, [first["id"], second["id"]])


def test_explicit_candidates_keep_requested_order_instead_of_database_order():
    campaign_id = uuid4()
    first = prospect(campaign_id)
    second = prospect(campaign_id, external_id="UC" + "z" * 22,
                      profile_url="https://www.youtube.com/@Another")
    connection = Mock()
    connection.execute.return_value.fetchall.return_value = [second, first]
    store = CreatorPilotStore("unused")
    store._explicit_group_ineligibility = Mock(return_value=None)
    assert store._explicit_candidates(connection, campaign_id, [first["id"], second["id"]]) == [
        first, second,
    ]


def guard_fixture(monkeypatch, *, conversation=False, protected=False, reserved=False, active=None):
    row = prospect(contact_email="owner@example.test")
    alias = prospect(external_id="alias", profile_url="https://youtube.com/@Alias",
                     intelligence={"source_channel_id": CHANNEL})
    connection = Mock()

    def execute(query, parameters=()):
        if query.startswith("SELECT p.*"):
            return Mock(fetchall=lambda: [row, alias])
        if "JOIN external_actions" in query:
            return Mock(fetchone=lambda: {"exists": 1} if conversation else None)
        if "FROM agent_tasks t JOIN audit_events" in query:
            return Mock(fetchall=lambda: active or [])
        return Mock(fetchone=lambda: None)

    connection.execute.side_effect = execute
    store = CreatorPilotStore("unused")
    store._discovery_evidence_protected = Mock(side_effect=lambda _, identity: (
        protected and identity == alias["id"]
    ))
    monkeypatch.setattr(CreatorDraftStore, "_draft_reservations", Mock(return_value={
        uuid4(): (alias["id"], "fixture", "hash"),
    } if reserved else {}))
    return store, connection, row, alias


@pytest.mark.parametrize("kind,fragment", [
    ("conversation", "conversation"), ("protected", "protected draft"),
    ("reserved", "draft reservation"),
])
def test_explicit_guard_blocks_global_alias_conversations_drafts_and_reservations(
    monkeypatch, kind, fragment,
):
    store, connection, row, _ = guard_fixture(monkeypatch, **{kind: True})
    assert fragment in store._explicit_ineligibility(connection, row)
    conversation_query = next(call for call in connection.execute.call_args_list
                              if "JOIN external_actions" in call.args[0])
    assert "a.private_context->>'recipient'" in conversation_query.args[0]
    assert conversation_query.args[1][1] == ["owner@example.test"]
    queries = [call.args[0] for call in connection.execute.call_args_list]
    assert next(i for i, query in enumerate(queries) if "hashtextextended" in query) < next(
        i for i, query in enumerate(queries) if "JOIN external_actions" in query
    )


def test_explicit_guard_accepts_stale_unauthorized_evidence_and_uses_sorted_sender_locks(
    monkeypatch,
):
    store, connection, row, _ = guard_fixture(monkeypatch)
    assert store._explicit_ineligibility(connection, row) is None
    keys = [call.args[1][0] for call in connection.execute.call_args_list
            if "hashtextextended" in call.args[0]]
    assert keys == sorted(set(keys))
    assert f"creator-platform:youtube:{CHANNEL}" in keys
    assert "creator-platform:youtube:alias" in keys


def test_explicit_guard_rejects_known_candidate_suppression(monkeypatch):
    store, connection, row, _ = guard_fixture(monkeypatch)
    row["contact_email"] = None
    row["intelligence"]["contact_candidates"] = [{"email": "blocked@example.test"}]
    monkeypatch.setattr("app.creator_pilot_store.contact_is_suppressed", Mock(return_value=True))
    assert "suppressed" in store._explicit_ineligibility(connection, row)


def test_explicit_guard_rejects_a_suppressed_canonical_alias_without_target_email(monkeypatch):
    store, connection, row, alias = guard_fixture(monkeypatch)
    row["contact_email"] = None
    alias["status"] = "suppressed"
    assert "suppressed" in store._explicit_ineligibility(connection, row)


def test_explicit_group_acquires_one_sorted_union_for_all_targets_and_aliases():
    first = prospect(contact_email="z@example.test")
    second = prospect(external_id="UC" + "z" * 22,
                      profile_url="https://www.youtube.com/@Another",
                      contact_email="a@example.test")
    bridge = prospect(external_id="imported", profile_url="https://youtube.com/@Bridge")
    store = CreatorPilotStore("unused")
    store._matching_creators = Mock(side_effect=[[first, bridge], [second, bridge],
                                                 [first, bridge], [second, bridge]])
    store._explicit_conflict = Mock(return_value=None)
    connection = Mock()
    assert store._explicit_group_ineligibility(connection, [first, second]) is None
    keys = [call.args[1][0] for call in connection.execute.call_args_list]
    assert keys == sorted(set(keys))
    assert "creator-email:a@example.test" in keys and "creator-email:z@example.test" in keys
    assert store._explicit_conflict.call_count == 2


def test_explicit_group_refuses_new_alias_keys_after_wait_without_extending_held_locks():
    row = prospect()
    changed = prospect(contact_email="new@example.test")
    store = CreatorPilotStore("unused")
    store._matching_creators = Mock(side_effect=[[row], [row, changed]])
    store._explicit_conflict = Mock(return_value=None)
    connection = Mock()
    assert "identity changed" in store._explicit_group_ineligibility(connection, [row])
    locked = [call.args[1][0] for call in connection.execute.call_args_list]
    assert "creator-email:new@example.test" not in locked
    store._explicit_conflict.assert_not_called()


def test_explicit_guard_checks_only_issued_active_pilot_payloads(monkeypatch):
    store, connection, row, alias = guard_fixture(monkeypatch)
    payload = {"prospect_ids": [str(alias["id"])]}
    active = [{"payload": payload, "payload_hash": canonical_hash(payload)}]
    store, connection, row, _ = guard_fixture(monkeypatch, active=active)
    # Bind the existing fixture's alias to this target's canonical identity.
    active[0]["payload"]["prospect_ids"] = [str(row["id"])]
    active[0]["payload_hash"] = canonical_hash(active[0]["payload"])
    assert "active research reservation" in store._explicit_ineligibility(connection, row)
    active[0]["payload_hash"] = "0" * 64
    assert store._explicit_ineligibility(connection, row) is None


def create_fixture(*, existing=None, used=0):
    campaign_id = uuid4()
    campaign = {"id": campaign_id}
    selected = prospect(campaign_id)
    connection = Mock()

    def execute(query, parameters=()):
        if "WHERE idempotency_key=" in query:
            return Mock(fetchone=lambda: existing)
        if "FROM marketing_campaigns" in query:
            return Mock(fetchone=lambda: campaign)
        if "SELECT id FROM agent_tasks" in query:
            return Mock(fetchone=lambda: None)
        if "COALESCE(sum" in query:
            return Mock(fetchone=lambda: {"count": used})
        return Mock()

    connection.execute.side_effect = execute
    store = CreatorPilotStore("unused")
    manager = MagicMock()
    manager.__enter__.return_value = connection
    store.connect = Mock(return_value=manager)
    store._issued = Mock(return_value=True)
    store._explicit_candidates = Mock(return_value=[selected])
    store._automatic_candidates = Mock(return_value=[selected])
    store._append_audit = Mock()
    store._create_task_record = Mock(side_effect=lambda _, request: {
        "id": uuid4(), "kind": request.kind, "payload": request.payload,
        "requested_by": request.requested_by, "correlation_id": uuid4(),
    })
    return store, campaign, selected


def test_explicit_creation_freezes_exact_requested_ids_and_keeps_shared_budget():
    store, campaign, selected = create_fixture()
    request = CreatorPilotCreate(actor="fixture", idempotency_key=uuid4(),
                                 prospect_ids=[selected["id"]])
    task = store.create_pilot(campaign["id"], request)
    assert task["payload"]["requested_prospect_ids"] == [str(selected["id"])]
    assert task["payload"]["prospect_ids"] == [str(selected["id"])]
    store._automatic_candidates.assert_not_called()
    store, campaign, selected = create_fixture(used=30)
    request = request.model_copy(update={"prospect_ids": [selected["id"]]})
    with pytest.raises(MarketingOutreachError, match="thirty creator"):
        store.create_pilot(campaign["id"], request)
    store._create_task_record.assert_not_called()
    store._append_audit.assert_not_called()


def test_automatic_creation_keeps_legacy_payload_and_selection():
    store, campaign, _ = create_fixture()
    request = CreatorPilotCreate(actor="fixture", idempotency_key=uuid4(), limit=1)
    task = store.create_pilot(campaign["id"], request)
    assert "requested_prospect_ids" not in task["payload"]
    store._explicit_candidates.assert_not_called()
    store._automatic_candidates.assert_called_once()


@pytest.mark.parametrize("old_explicit,new_explicit,same_ids,allowed", [
    (False, False, True, True), (True, True, True, True),
    (True, True, False, False), (False, True, True, False), (True, False, True, False),
])
def test_idempotency_binds_targeted_membership_and_preserves_legacy_retries(
    old_explicit, new_explicit, same_ids, allowed,
):
    identity = uuid4()
    request = CreatorPilotCreate(actor="fixture", idempotency_key=uuid4(), limit=1,
                                 prospect_ids=[identity] if new_explicit else None)
    payload = {"campaign_id": "placeholder", "requested_limit": 1,
               "prospect_ids": [str(identity)]}
    if old_explicit:
        payload["requested_prospect_ids"] = [str(identity if same_ids else uuid4())]
    existing = {"kind": KIND, "requested_by": "fixture", "payload": payload}
    store, campaign, _ = create_fixture(existing=existing)
    payload["campaign_id"] = str(campaign["id"])
    if allowed:
        assert store.create_pilot(campaign["id"], request) is existing
    else:
        with pytest.raises(MarketingOutreachError, match="Idempotency"):
            store.create_pilot(campaign["id"], request)
    store._create_task_record.assert_not_called()


def test_explicit_context_rechecks_current_guard_before_return_and_lease_after_waits(monkeypatch):
    store = CreatorPilotStore("unused")
    row = prospect()
    campaign = {"id": row["campaign_id"]}
    task = {"payload": {"campaign_id": str(campaign["id"]),
                        "campaign_hash": canonical_hash(campaign_snapshot(campaign)),
                        "prospect_ids": [str(row["id"])],
                        "requested_prospect_ids": [str(row["id"])],
                        "profile_urls": {str(row["id"]): row["profile_url"]}}}
    connection = Mock()
    connection.execute.side_effect = [Mock(), Mock(fetchone=lambda: campaign),
                                      Mock(fetchone=lambda: row), Mock(fetchone=lambda: None)]
    store._owned_task = Mock(side_effect=[task, InvalidTaskStateError("lease expired after wait")])
    store._explicit_group_ineligibility = Mock(return_value=None)
    monkeypatch.setattr("app.creator_pilot_store.contact_is_suppressed", Mock(return_value=False))
    with pytest.raises(InvalidTaskStateError, match="lease expired after wait"):
        store._context(connection, uuid4(), uuid4(), row["id"], research={
            "intelligence": {"topics": ["Minecraft"], "contact_candidates": [
                {"email": "new@example.test"},
            ]},
        })
    store._explicit_group_ineligibility.assert_called_once()
    grouped = store._explicit_group_ineligibility.call_args.args[1]
    assert len(grouped) == 2
    assert grouped[1]["intelligence"]["contact_candidates"][0]["email"] == "new@example.test"


def test_explicit_save_rechecks_newly_discovered_identity_and_contacts_before_any_update():
    store = CreatorPilotStore("unused")
    row = prospect()
    store._context = Mock(side_effect=InvalidTaskStateError(
        "New address already has a conversation"
    ))
    connection = Mock()
    manager = MagicMock()
    manager.__enter__.return_value = connection
    store.connect = Mock(return_value=manager)
    research = {"intelligence": {"topics": ["Minecraft"], "source_channel_id": CHANNEL,
                                 "contact_candidates": [{"email": "new@example.test"}]}}
    with pytest.raises(InvalidTaskStateError, match="New address"):
        store.save_pilot_research(uuid4(), uuid4(), row["id"], research)
    assert store._context.call_args.kwargs["research"] == research
    connection.execute.assert_not_called()
