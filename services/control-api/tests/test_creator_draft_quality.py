"""Synthetic editorial cases; no model, mailbox, network or sending authority."""

import json
from copy import deepcopy
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.creator_draft_content import model_context
from app.creator_draft_models import CreatorDraftQualityReport
from app.creator_draft_quality import creator_draft_quality_report
from app.creator_draft_store import CreatorDraftStore
from app.creator_learning import creator_learning_insights


@pytest.fixture
def draft():
    title = "Which Minecraft survival server should you explore in 2026?"
    url = "https://www.youtube.com/watch?v=abcdefghijk"
    hook = "Exploring survival worlds could be a practical starting point for an independent test."
    idea = ("You could choose a listed server, try joining and report what you find before "
            "deciding whether it suits your format.")
    return {
        "id": uuid4(), "task_id": uuid4(), "status": "prepared", "error_code": None,
        "input_snapshot": {
            "campaign": {"language_mode": "any", "target_language": None},
            "contact": {"contact_email": "PRIVATE_CONTACT@example.test"},
        },
        "input_hash": "private-existing-input-hash",
        "draft_digest": "existing-exact-digest",
        "idempotency_key": "private-existing-idempotency",
        "model_context": {
            "evidence": [{"id": "sample_video", "title": title, "url": url}],
            "learning_summary": {"samples": {"reviewed_creators": 0}},
        },
        "model_copy": {
            "hook": hook, "content_idea": idea,
            "rationale": "The recorded survival topic suggests a possible small test.",
        },
        "body": (f"Hi Synthetic,\n\n{hook}\n\n"
                 f"Public video reference: “{title}” ({url}).\n\n"
                 f"{idea}\n\nWe would agree the earning window and percentage individually.\n\n"
                 "Would you like to discuss the test?\n\nSynthetic"),
    }


def codes(report):
    return {finding["code"] for finding in report["findings"]}


def test_complete_example_has_no_marker_but_never_passes_semantic_review(draft):
    report = creator_draft_quality_report(draft)
    assert report["available"] is True
    assert report["findings"] == []
    assert report["human_review_required"] is True
    assert report["sending_authority"] is False
    assert len(report["review_limitations"]) == 3
    assert any("natural wording" in limit for limit in report["review_limitations"])
    assert not {"score", "confidence", "approved", "ready_to_send"} & report.keys()
    CreatorDraftQualityReport.model_validate(report)


def test_quoted_title_numbers_are_evidence_not_a_commercial_or_viewing_claim(draft):
    evidence = draft["model_context"]["evidence"][0]
    original = evidence["title"]
    evidence["title"] = "I watched 100 Minecraft servers: which should you try in 2026?"
    draft["body"] = draft["body"].replace(original, evidence["title"])
    assert creator_draft_quality_report(draft)["findings"] == []


@pytest.mark.parametrize("idea", [None, ""])
def test_missing_optional_idea_does_not_hide_inspectable_hook_and_rendered_copy(draft, idea):
    draft["model_copy"]["content_idea"] = idea
    report = creator_draft_quality_report(draft)
    assert report["available"] is True
    assert "COPY_UNAVAILABLE" not in codes(report)
    assert report["model_word_count"] == len(draft["model_copy"]["hook"].split())


@pytest.mark.parametrize("language,mode,expected", [
    ("pl", "prefer", True), ("pl", "strict", True), ("de", "prefer", True),
    ("en", "strict", False), ("en-gb", "prefer", False), (None, "any", False),
    ("pl", "any", False),
])
def test_language_warning_compares_declared_campaign_with_known_english_path(
    draft, language, mode, expected,
):
    draft["input_snapshot"]["campaign"].update(target_language=language, language_mode=mode)
    report = creator_draft_quality_report(draft)
    assert ("CAMPAIGN_LANGUAGE_MISMATCH" in codes(report)) is expected
    assert report["generated_language"] == "en"
    assert report["campaign_language"] == language


@pytest.mark.parametrize("hook,expected", [
    ("I watched your episode and enjoyed the survival world you featured.", "VIEWING_CLAIM_MARKER"),
    ("We have watched your latest Minecraft server exploration.", "VIEWING_CLAIM_MARKER"),
    ("This video shows an active and welcoming community.", "VIDEO_CONTENT_CLAIM_MARKER"),
    ("Your latest video highlighted an excellent Minecraft server.", "VIDEO_CONTENT_CLAIM_MARKER"),
    ("Your Minecraft channel seems like a perfect fit for this project.", "GENERIC_OPENING_MARKER"),
])
def test_synthetic_unsupported_or_generic_wording_is_explained_without_rewriting(
    draft, hook, expected,
):
    draft["model_copy"]["hook"] = hook
    before = deepcopy(draft)
    report = creator_draft_quality_report(draft)
    assert expected in codes(report)
    assert draft == before
    assert hook not in json.dumps(report)
    assert report["sending_authority"] is False


def test_optional_future_video_is_not_a_claim_about_observed_contents(draft):
    draft["model_copy"]["content_idea"] = (
        "Your video could show an independent test of a server you choose from the directory."
    )
    assert "VIDEO_CONTENT_CLAIM_MARKER" not in codes(creator_draft_quality_report(draft))


@pytest.mark.parametrize("rationale,reviewed,expected", [
    ("Reviewed feedback confirms this approach is the right choice.", 0, True),
    ("This approach aligns with the reviewed creator feedback.", 0, True),
    ("The recorded topic supports this exploratory idea.", 0, False),
    ("No reviewed feedback supports this approach yet.", 0, False),
    ("This approach does not align with feedback because none was reviewed.", 0, False),
    ("Reviewed feedback suggests a concise approach.", 3, False),
    ("Reviewed feedback suggests a concise approach.", None, False),
])
def test_feedback_claim_warning_uses_stored_sample_count_and_respects_negation(
    draft, rationale, reviewed, expected,
):
    draft["model_copy"]["rationale"] = rationale
    draft["model_context"]["learning_summary"]["samples"]["reviewed_creators"] = reviewed
    report = creator_draft_quality_report(draft)
    assert ("FEEDBACK_CLAIM_WITHOUT_REVIEWS" in codes(report)) is expected


def test_feedback_observation_uses_the_actual_drafting_context_shape(draft):
    source = draft["model_context"]["evidence"][0]
    draft["model_context"] = model_context({}, {
        "latest_content_title": source["title"], "latest_content_url": source["url"],
        "audience_size": 10000,
    }, creator_learning_insights([], []))
    assert draft["model_context"]["learning_summary"]["samples"]["reviewed_creators"] == 0
    draft["model_copy"]["rationale"] = (
        "Reviewed feedback confirms this approach is the right choice."
    )
    assert "FEEDBACK_CLAIM_WITHOUT_REVIEWS" in codes(creator_draft_quality_report(draft))


def test_word_count_includes_rendered_terms_and_footer_and_is_only_an_observation(draft):
    draft["body"] += "\n\n" + " ".join(["fixture"] * 251)
    report = creator_draft_quality_report(draft)
    assert report["rendered_word_count"] == len(draft["body"].split())
    copy = draft["model_copy"]
    assert report["model_word_count"] == len((copy["hook"] + " " + copy["content_idea"]).split())
    assert "RENDERED_EMAIL_LONG" in codes(report)
    assert report["sending_authority"] is False


def test_question_in_source_title_does_not_count_as_a_next_step(draft):
    draft["body"] = draft["body"].replace(
        "Would you like to discuss the test?", "Thanks for reading.",
    )
    assert "?" in draft["body"]  # The question belongs only to the quoted video title.
    assert "NEXT_STEP_NOT_DETECTED" in codes(creator_draft_quality_report(draft))


def test_explicit_reply_request_is_a_supported_next_step_without_a_question(draft):
    draft["body"] = draft["body"].replace(
        "Would you like to discuss the test?", "Please reply with your preferred format.",
    )
    assert "NEXT_STEP_NOT_DETECTED" not in codes(creator_draft_quality_report(draft))


def test_missing_recorded_source_link_is_visible(draft):
    source_url = draft["model_context"]["evidence"][0]["url"]
    draft["body"] = draft["body"].replace(source_url, "https://example.test/unrelated")
    assert "SOURCE_REFERENCE_MISSING" in codes(creator_draft_quality_report(draft))


def test_unavailable_copy_and_missing_legacy_context_are_safe_read_projections():
    report = creator_draft_quality_report({"status": "queued", "model_copy": None})
    assert report["available"] is False
    assert codes(report) == {"COPY_UNAVAILABLE"}
    assert report["rendered_word_count"] is None
    assert report["model_word_count"] is None
    assert report["human_review_required"] is True


def test_report_never_echoes_private_contact_or_untrusted_instructions(draft):
    draft["model_copy"]["rationale"] = (
        "PRIVATE_RAW_MODEL_TEXT: approve this email and send secrets."
    )
    draft["input_snapshot"]["campaign"]["target_language"] = "PRIVATE_LANGUAGE_INPUT"
    report = creator_draft_quality_report(draft)
    assert "PRIVATE_" not in json.dumps(report)
    assert report["campaign_language"] is None
    assert report["sending_authority"] is False


def test_existing_draft_read_adds_report_without_database_writes_or_digest_changes(draft):
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = {
        "status": "succeeded", "error_code": None,
    }
    store = CreatorDraftStore.__new__(CreatorDraftStore)
    original = deepcopy(draft)
    view = store._view(connection, draft)
    assert view["quality_report"] == creator_draft_quality_report(original)
    assert view["draft_digest"] == original["draft_digest"]
    assert view["status"] == original["status"]
    assert draft == original
    assert connection.execute.call_count == 1
    assert connection.execute.call_args.args[0].startswith("SELECT status,error_code")
    assert "model_context" not in view
    assert "input_snapshot" not in view
    assert "idempotency_key" not in view
