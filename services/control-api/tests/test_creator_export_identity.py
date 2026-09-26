import csv
import io

import pytest

from app.creator_export import channel_identity, creator_csv

OLD_CHANNEL = "UC" + "a" * 22
CURRENT_CHANNEL = "UC" + "b" * 22
CURRENT_PROFILE = f"https://www.youtube.com/channel/{CURRENT_CHANNEL}"


def exported(row):
    value = {"id": "saved-prospect", "display_name": "Creator", **row}
    text = "".join(creator_csv([value], include_excluded=True)).lstrip("\ufeff")
    return list(csv.DictReader(io.StringIO(text)))[0]


def test_imported_handle_exports_verified_channel_not_arbitrary_import_identity():
    row = {
        "external_id": "manual-shortlist-17", "profile_url": "https://youtube.com/@creator",
        "intelligence": {"source_channel_id": CURRENT_CHANNEL},
    }
    result = exported(row)
    assert result["channel_id"] == CURRENT_CHANNEL
    assert result["creator_id"] == "saved-prospect"
    assert result["outreach_authorized"] == "false"
    assert row["external_id"] == "manual-shortlist-17"


def test_profile_edit_cannot_export_old_canonical_source_key_as_new_channel_identity():
    # Profile edits intentionally preserve external_id, but clear its research.
    row = {"external_id": OLD_CHANNEL, "profile_url": CURRENT_PROFILE, "intelligence": {}}
    assert exported(row)["channel_id"] == CURRENT_CHANNEL


def test_changed_handle_without_fresh_research_exports_unknown_id_not_old_source_key():
    row = {
        "external_id": OLD_CHANNEL, "profile_url": "https://youtube.com/@different_creator",
        "intelligence": {},
    }
    assert exported(row)["channel_id"] == ""


def test_invalid_research_identity_falls_back_to_current_canonical_profile_only():
    row = {
        "external_id": "manual-source", "profile_url": CURRENT_PROFILE,
        "intelligence": {"source_channel_id": "../not-a-channel"},
    }
    assert channel_identity(row) == CURRENT_CHANNEL


@pytest.mark.parametrize("profile", [
    "https://youtube.com/@creator", "https://youtube.com.evil.test/channel/" + CURRENT_CHANNEL,
    "https://attacker@youtube.com/channel/" + CURRENT_CHANNEL,
    CURRENT_PROFILE + "?redirect=elsewhere", "https://[malformed",
])
def test_unresolved_or_untrusted_profile_does_not_turn_old_external_key_into_evidence(profile):
    assert channel_identity({"profile_url": profile, "external_id": OLD_CHANNEL}) == ""
