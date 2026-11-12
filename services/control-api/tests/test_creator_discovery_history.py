"""Known aliases preserve evidence without inventing creator contact authority."""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.application_browser import canonical_hash
from app.creator_discovery_history import (
    HistoryIndex,
    identity_keys,
    load_history,
    sender_lock_keys,
)

CHANNEL = "UC" + "A" * 22


def creator(**changes):
    return {
        "id": uuid4(), "platform": "youtube", "external_id": "saved-handle",
        "profile_url": "https://www.youtube.com/@fixture", "intelligence": {}, **changes,
    }


def test_canonical_channel_and_public_profile_variants_share_identity():
    keys = identity_keys(creator(intelligence={"source_channel_id": CHANNEL}))
    assert ("channel", CHANNEL) in keys
    assert ("profile", "https://www.youtube.com/@fixture") in keys
    assert ("profile", "https://youtube.com/@fixture") in keys
    assert ("profile", f"https://youtube.com/channel/{CHANNEL}".casefold()) in keys
    assert HistoryIndex([(keys, True)]).protected({
        "platform": "youtube", "external_id": CHANNEL,
        "profile_url": f"https://youtube.com/channel/{CHANNEL}",
    })


def test_business_addresses_are_trimmed_casefolded_and_names_never_match():
    keys = identity_keys(creator(contact_email=" Business@Example.TEST ", intelligence={
        "contact_candidates": [{"email": " Sponsor@Example.TEST "}],
    }))
    assert {("email", "business@example.test"), ("email", "sponsor@example.test")} <= keys
    assert not HistoryIndex([(keys, True)]).protected({"display_name": "Fixture"})


def test_dated_contact_history_adds_only_valid_bounded_email_aliases():
    history = [{"email": " OLD@Example.TEST "}, {"email": "not an email"}, None]
    history.extend({"email": f"prior-{position}@example.test"} for position in range(19))
    keys = identity_keys(creator(intelligence={"contact_history": history}))
    assert ("email", "old@example.test") in keys
    assert ("email", "not an email") not in keys
    assert ("email", "prior-16@example.test") in keys
    assert ("email", "prior-17@example.test") not in keys


def test_alias_components_are_transitive_when_frozen_group_arrives_first():
    groups = [
        ({("email", "old@example.test")}, True),
        ({("email", "old@example.test"), ("profile", "https://youtube.com/@middle")}, False),
        ({("profile", "https://youtube.com/@middle"), ("channel", CHANNEL)}, False),
    ]
    index = HistoryIndex(groups)
    incoming = {"platform": "youtube", "external_id": CHANNEL}
    assert index.protected(incoming)
    assert {key for keys, _ in groups for key in keys} <= index.keys(incoming)


def test_frozen_old_snapshot_connects_via_prospect_to_new_observation():
    existing = creator(contact_email="new@example.test")
    frozen = {("prospect", str(existing["id"])), ("email", "old@example.test")}
    index = HistoryIndex([(frozen, True), (identity_keys(existing), False)])
    incoming = {"platform": "youtube", "external_id": "new-handle",
                "profile_url": "https://youtube.com/@new-handle"}
    assert index.protected(incoming, existing)
    assert ("email", "old@example.test") in index.keys(incoming, existing)
    assert index.protected({"contact_email": "OLD@example.test"})


@pytest.mark.parametrize("reverse", [False, True])
def test_fresh_batch_aliases_join_frozen_identity_without_mutating_loaded_history(reverse):
    original = HistoryIndex([({("channel", CHANNEL)}, True)])
    frozen_identity = {"platform": "youtube", "external_id": CHANNEL}
    baseline = original.keys(frozen_identity)
    contact = {"contact_candidates": [{"email": " FRESH@Example.TEST "}]}
    first = {**frozen_identity, "intelligence": contact}
    second = {"platform": "youtube", "external_id": "UC" + "C" * 22,
              "intelligence": contact}
    observations = [second, first] if reverse else [first, second]
    assert not original.protected(second)
    augmented = original.with_observations(observations)
    assert augmented is not original
    assert augmented.protected(first) and augmented.protected(second)
    assert ("channel", CHANNEL) in augmented.keys(second)
    assert ("email", "fresh@example.test") in augmented.keys(frozen_identity)
    assert original.keys(frozen_identity) == baseline
    assert not original.protected(second)


def test_loader_preserves_historical_sources_without_status_or_expiry_release():
    saved = creator(status="qualified", suppressed_at=None)
    reserved_id = str(uuid4())
    payload = {"prospect_ids": [reserved_id],
               "profile_urls": {reserved_id: "https://youtube.com/@reserved"}}
    connection = Mock()

    def execute(query):
        # These sources deliberately have no expiry/current-status filter: old
        # drafts, cancelled packets and stopped reservations remain evidence.
        assert "expires_at" not in query and "t.status" not in query and "a.status" not in query
        if query.startswith("SELECT id,platform"):
            rows = [saved]
        elif "FROM creator_email_drafts UNION ALL" in query:
            rows = [{"prospect_id": saved["id"], "input_snapshot": {
                "contact": {"contact_email": "old-draft@example.test"},
            }}]
        elif "FROM external_actions a" in query:
            rows = [{"prospect_id": None, "recipient": "old-action@example.test",
                     "marketing": {"contact_snapshot": {"contact_email": "snapshot@example.test"}}}]
        elif "FROM marketing_outcomes" in query:
            rows = [{"prospect_id": None, "sender": "reply@example.test", "creator_key": None}]
        elif "FROM creator_contact_suppressions" in query:
            rows = [{"email": "suppressed@example.test"}]
        elif "FROM agent_tasks t JOIN audit_events" in query:
            rows = [{"kind": "marketing.creator_pilot", "payload": payload,
                     "payload_hash": canonical_hash(payload)}]
        elif "FROM creator_reply_deferrals" in query:
            rows = [{"prospect_ids": [], "source_identity": [["email", "deferred@example.test"]]}]
        else:
            raise AssertionError(f"Unexpected history query: {query}")
        return Mock(fetchall=lambda: rows)

    connection.execute.side_effect = execute
    index = load_history(connection)
    for address in ["old-draft", "old-action", "snapshot", "reply", "suppressed", "deferred"]:
        assert index.protected({"contact_email": f"{address}@example.test"})
    assert index.protected(saved)
    assert index.protected({"platform": "youtube", "profile_url": "https://www.youtube.com/@reserved"})
    assert not index.protected({"contact_email": "uncontacted@example.test"})


def test_unfrozen_and_genuinely_new_creators_remain_refreshable():
    saved = creator(contact_email="known@example.test", display_name="Shared Name")
    index = HistoryIndex([(identity_keys(saved), False)])
    assert not index.protected(saved)
    assert not index.protected(creator(external_id="new", profile_url="https://youtube.com/@new",
                                       display_name="Shared Name"))
    assert not HistoryIndex([({("email", "old@example.test")}, True)]).protected(saved)


@pytest.mark.parametrize("value", [None, "untrusted", [], 12, False])
def test_non_mapping_observations_have_no_identity(value):
    assert identity_keys(value) == set()


@pytest.mark.parametrize("intelligence", [
    None, "untrusted", [], False,
    {"contact_candidates": "not a list", "contact_history": {}},
    {"source_channel_id": [], "contact_candidates": [None, 4, "bad", {"email": []}]},
])
def test_malformed_intelligence_never_crashes_or_invents_aliases(intelligence):
    row = creator(intelligence=intelligence)
    assert identity_keys(row) == identity_keys({**row, "intelligence": {}})
    assert identity_keys({"platform": [], "external_id": {}, "profile_url": 7,
                          "contact_email": False, "intelligence": intelligence}) == set()


def test_sender_locks_cover_only_exact_known_identity_keys():
    keys = {("prospect", str(uuid4())), ("email", "one@example.test"),
            ("profile", "https://youtube.com/@one"), ("channel", CHANNEL),
            ("creator", "youtube", CHANNEL)}
    assert sender_lock_keys(keys) == {
        "creator-email:one@example.test", "creator-profile:https://youtube.com/@one",
        f"creator-platform:youtube:{CHANNEL}",
    }
