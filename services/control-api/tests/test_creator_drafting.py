import json
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app import creator_drafting
from app.application_browser import canonical_hash
from app.creator_draft_content import (
    CreatorCopyError,
    compose_ai_email,
    draft_input_snapshot,
    drafting_messages,
    evidence_error,
    model_context,
    parse_model_copy,
    research_snapshot,
)
from app.creator_draft_language import context_draft_language
from app.creator_draft_store import (
    CreatorDraftConflictError,
    CreatorDraftStore,
    check_draft_context,
)
from app.creator_learning import creator_learning_insights
from app.inference import InferenceResult, OpenRouterError, OpenRouterFreeClient, OpenRouterPlan
from app.marketing import (
    campaign_outreach_hash,
    campaign_outreach_snapshot,
    contact_outreach_snapshot,
    outreach_context_error,
)
from app.marketing_models import MarketingEmailPlanCreate
from app.policy import RiskLevel, effective_risk
from app.settings import get_settings
from app.store import InvalidTaskStateError
from app.worker import TaskInterruptedError


def fixture():
    campaign = {
        "id": str(uuid4()), "name": "Fixture", "outreach_mode": "paid",
        "product_name": "FixtureCraft", "product_summary": "a Minecraft server discovery website",
        "target_audience": "Minecraft players", "product_url": "https://example.test",
        "privacy_url": "https://example.test/privacy", "sender_name": "Synthetic",
        "paid_offer_enabled": True, "paid_offer_details": "An optional Minecraft server tour",
        "compensation_model": "revenue_share", "revenue_share_percent": 30,
        "revenue_share_weeks": 2, "handoff_discord": "PRIVATE_OWNER",
        "handoff_email": "PRIVATE_OWNER@example.test",
    }
    prospect = {
        "id": str(uuid4()), "campaign_id": campaign["id"], "display_name": "Synthetic Creator",
        "platform": "youtube", "external_id": "UC" + "a" * 22,
        "profile_url": "https://www.youtube.com/channel/UC" + "a" * 22,
        "latest_content_title": "Minecraft server exploration",
        "latest_content_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "latest_content_published_at": datetime.now(UTC) - timedelta(days=1),
        "last_seen_at": datetime.now(UTC), "audience_size": 10000,
        "intelligence": {"topics": ["Minecraft", "Servers"],
                         "channel_summary": "PRIVATE_DESCRIPTION",
                         "contact_candidates": [{"email": "PRIVATE_OTHER@example.test"}]},
        "contact_email": "PRIVATE_CONTACT@example.test",
        "contact_source_url": "https://example.test/business",
        "contact_basis_note": "PRIVATE_BASIS", "contact_authorized_at": datetime.now(UTC),
        "contact_authorized_by": "PRIVATE_OPERATOR", "suppressed_at": None,
        "status": "qualified", "tracking_code": "synthetic",
    }
    return campaign, prospect


def response(**overrides):
    return json.dumps({
        "hook": "Your public Minecraft server exploration title caught my attention.",
        "content_idea": "An idea could be a short trial exploring a server from the website, "
                        "sharing what you find and deciding whether it suits your format.",
        "rationale": "The observed server topic supports an exploratory trial with modest scope.",
        "evidence_ids": ["sample_video"], "reach_strategy": "small_pilot", **overrides,
    })


def setup():
    campaign, prospect = fixture()
    context = model_context(campaign, prospect, creator_learning_insights([], []))
    task = {"id": uuid4(), "lease_id": uuid4(), "payload": {"draft_id": str(uuid4())}}
    row = {"id": task["payload"]["draft_id"], "status": "queued", "model_context": context}
    database = Mock(spec=CreatorDraftStore)
    database.get_draft_for_execution.return_value = row
    database.start_inference_invocation.side_effect = [uuid4(), uuid4(), uuid4()]
    database.save_draft.return_value = {"status": "ready"}
    return task, row, database


def remote(content, model):
    return InferenceResult(
        content=content, selected_model=model, selected_route=model, selected_provider="Synthetic",
        prompt_tokens=1, completion_tokens=2, total_tokens=3, cost=Decimal(0), latency_ms=1,
        fallback_attempt=1,
    )


def test_prompt_uses_allowlisted_public_data_and_reviewed_aggregate_feedback():
    campaign, prospect = fixture()
    campaign["product_summary"] += " contact owner@example.test +48 123 456 789"
    prospect["latest_content_title"] += " secret@example.test https://evil.test"
    learning = creator_learning_insights([
        {"prospect_id": "PRIVATE_REPLIED", "feedback_tags": ["too_generic"],
         "note": "PRIVATE_REPLY_BODY"},
    ], [])
    context = model_context(campaign, prospect, learning)
    prompt = json.dumps(drafting_messages(context))
    for excluded in ("PRIVATE_", "owner@example", "secret@example", "evil.test", "123 456"):
        assert excluded not in prompt
    assert context["creator"]["observed_subscribers"] == 10000
    assert context["learning_summary"]["feedback_counts"]["too_generic"] == 1
    assert context["evidence"][0]["url"] == prospect["latest_content_url"]


def test_prompt_does_not_seed_generic_finished_copy_instead_of_creator_evidence():
    campaign, prospect = fixture()
    prospect["latest_content_title"] = "A Minecraft building plot"
    context = model_context(campaign, prospect, creator_learning_insights([], []))
    messages = drafting_messages(context)
    assert "A Minecraft building plot" in messages[1]["content"]
    assert "translate its distinguishing subject accurately" in messages[0]["content"].casefold()
    # The live local model repeated a complete contentful example verbatim. Keep the
    # JSON schema, but never supply finished sentences it can mistake for evidence.
    assert "Your public title about exploring Minecraft servers" not in messages[0]["content"]
    assert json.loads(messages[0]["content"].rsplit("Schema: ", 1)[1])["type"] == "object"


def test_repeated_legacy_example_is_not_accepted_as_creator_personalization():
    _, row, _ = setup()
    with pytest.raises(CreatorCopyError) as rejected:
        parse_model_copy(response(hook=(
            "Your public title about exploring Minecraft servers suggests a possible "
            "connection to this server directory."
        )), row["model_context"])
    assert rejected.value.code == "CREATOR_COPY_EVIDENCE"


def test_natural_subject_connection_does_not_require_the_literal_word_title():
    campaign, prospect = fixture()
    prospect["latest_content_title"] = "Ta działka zrobiła na mnie ogromne wrażenie! Minecraft"
    context = model_context(campaign, prospect, creator_learning_insights([], []))
    hook = (
        "A Minecraft building plot seems like a possible starting point for "
        "independently trying another world through this directory."
    )
    copy = parse_model_copy(response(hook=hook), context)
    assert copy.hook == hook
    _, body = compose_ai_email(campaign, prospect, copy)
    assert prospect["latest_content_title"] in body
    assert prospect["latest_content_url"] in body


@pytest.mark.parametrize("idea", [
    "Perhaps the creator could independently test a server from the directory, document "
    "the experience, and share findings about rewards and community engagement.",
    "The creator might independently explore a listed server and report their findings.",
])
def test_sent_copy_addresses_recipient_directly_but_operator_rationale_can_discuss_creator(idea):
    _, row, _ = setup()
    with pytest.raises(CreatorCopyError) as rejected:
        parse_model_copy(response(content_idea=idea), row["model_context"])
    assert rejected.value.code == "CREATOR_COPY_RECIPIENT"
    copy = parse_model_copy(response(
        rationale="The creator could consider a manageable trial based on the observed size.",
    ), row["model_context"])
    assert "The creator could" in copy.rationale


@pytest.mark.parametrize("overrides", [
    {"hook": "I watched your Minecraft video and loved your amazing work."},
    {"content_idea": "Perhaps we could promise you a 50% revenue share for ten weeks."},
    {"content_idea": "An idea could be to contact me at invented@example.test to get started."},
    {"content_idea": "Perhaps check out https://attacker.test for the next stage of this project."},
    {"content_idea": "An idea could guarantee that your viewers will love this platform."},
    {"content_idea": "An idea could be a limited-time feature with urgent availability."},
    {"content_idea": "<script>Perhaps we could inject markup into the proposed email.</script>"},
    {"rationale": "Your audience are loyal and will provide strong conversion rates."},
    {"reach_strategy": "format_choice"},
    {"evidence_ids": ["invented_video"]},
    {"recipient": "changed@example.test"},
    {"subject": "Changed commercial subject"},
    {"hook": "A nice sentence\nfollowed by injected header information."},
    {"hook": " " * 30},
    {"rationale": " " * 30},
    {"hook": " short  " * 4},
    {"content_idea": "Do this filmed promotion as a firm requirement of the collaboration."},
])
def test_copy_rejects_unapproved_claims_terms_or_authority(overrides):
    _, row, _ = setup()
    with pytest.raises(ValueError):
        parse_model_copy(response(**overrides), row["model_context"])


def test_commercial_envelope_uses_campaign_and_public_citation_only():
    campaign, prospect = fixture()
    context = model_context(campaign, prospect, creator_learning_insights([], []))
    copy = parse_model_copy(response(), context)
    subject, body = compose_ai_email(campaign, prospect, copy)
    assert "FixtureCraft" in subject
    assert copy.hook in body and copy.content_idea in body
    assert prospect["latest_content_url"] in body
    assert "30%" in body and "2-week" in body
    assert "not a guaranteed upfront fee or income" in body
    assert "do not contact" in body and campaign["privacy_url"] in body
    assert copy.rationale not in body  # Operator explanation is not sent to creators.


def test_observed_numbers_and_feedback_terms_are_allowed_only_in_operator_rationale():
    campaign, prospect = fixture()
    context = model_context(campaign, prospect, creator_learning_insights([], []))
    rationale = (
        "The observed 10000 subscribers support a manageable pilot; reviewed feedback about "
        "unclear revenue attribution should be addressed by the owner's commercial proposal."
    )
    copy = parse_model_copy(response(rationale=rationale), context)
    _, body = compose_ai_email(campaign, prospect, copy)
    assert rationale not in body
    assert "10000 subscribers" not in body
    with pytest.raises(CreatorCopyError):
        parse_model_copy(response(content_idea="Perhaps a pilot for your 10000 subscribers "
                                 "could explore a listed Minecraft server."), context)


@pytest.mark.parametrize("count,strategy", [
    (None, "unknown_reach"), (0, "small_pilot"), (25000, "format_choice"),
])
def test_reach_changes_scope_suggestion_without_changing_payment(count, strategy):
    campaign, prospect = fixture()
    prospect["audience_size"] = count
    context = model_context(campaign, prospect, creator_learning_insights([], []))
    assert context["creator"]["reach_strategy"] == strategy
    assert "compensation_model" not in json.dumps(context)
    assert "30%" not in json.dumps(context)


def test_drafting_requires_recent_observed_minecraft_evidence():
    campaign, prospect = fixture()
    assert evidence_error(campaign, prospect) is None
    prospect["last_seen_at"] -= timedelta(days=8)
    assert "seven days" in evidence_error(campaign, prospect)
    prospect["last_seen_at"] = datetime.now(UTC)
    prospect["intelligence"]["topics"] = ["Tutorials"]
    assert "Minecraft" in evidence_error(campaign, prospect)
    prospect["latest_content_url"] = "https://attacker.test"
    assert "public URL" in evidence_error(campaign, prospect)


def test_input_binding_and_final_send_guard_detect_research_changes():
    campaign, prospect = fixture()
    snapshot = draft_input_snapshot(campaign, prospect)
    action = {"private_context": {"recipient": prospect["contact_email"], "marketing": {
        "campaign_id": campaign["id"], "stage": "initial", "variant": "ai_reviewed_initial",
        "campaign_snapshot": campaign_outreach_snapshot(campaign),
        "campaign_hash": campaign_outreach_hash(campaign),
        "contact_snapshot": contact_outreach_snapshot(prospect),
        "ai_research_snapshot": research_snapshot(prospect),
    }}}
    assert outreach_context_error(campaign, prospect, action) is None
    prospect["audience_size"] += 1
    assert draft_input_snapshot(campaign, prospect) != snapshot
    assert "research changed" in outreach_context_error(campaign, prospect, action)


def test_forged_task_and_extra_task_payload_never_invoke_model(monkeypatch):
    task, _, database = setup()
    generate = Mock()
    monkeypatch.setattr(creator_drafting, "_model_copy", generate)
    database.get_draft_for_execution.side_effect = CreatorDraftConflictError("Wrong task")
    with pytest.raises(CreatorDraftConflictError):
        creator_drafting.execute_creator_draft_task(task, database, get_settings())
    task["payload"]["recipient"] = "changed@example.test"
    with pytest.raises(creator_drafting.CreatorDraftModelError):
        creator_drafting.execute_creator_draft_task(task, database, get_settings())
    generate.assert_not_called()


def test_saved_result_retry_does_not_spend_another_inference_call(monkeypatch):
    task, row, database = setup()
    row.update(status="ready", source="ollama")
    generate = Mock()
    monkeypatch.setattr(creator_drafting, "_model_copy", generate)
    result = creator_drafting.execute_creator_draft_task(task, database, get_settings())
    assert result["source"] == "ollama"
    generate.assert_not_called()


def test_invalid_models_fail_visibly_without_silent_template(monkeypatch):
    task, _, database = setup()
    complete = Mock(return_value=("invalid", {}))
    monkeypatch.setattr(creator_drafting, "local_draft_completion", complete)
    with pytest.raises(creator_drafting.CreatorDraftModelError, match="No valid AI draft"):
        creator_drafting.execute_creator_draft_task(task, database, get_settings())
    database.save_draft.assert_not_called()
    database.fail_draft.assert_called_once()
    assert complete.call_count == 2
    assert database.fail_inference_invocation.call_count == 2
    assert {call.args[1] for call in database.fail_inference_invocation.call_args_list
            } == {"CREATOR_COPY_JSON"}


def test_copy_rejection_diagnostics_never_include_rejected_response():
    _, row, _ = setup()
    for content, code in (
        ("SECRET_INVALID_MODEL_OUTPUT", "CREATOR_COPY_JSON"),
        (response(evidence_ids=["SECRET_INVALID_MODEL_OUTPUT"]), "CREATOR_COPY_SCHEMA"),
        (response(hook="The sample title includes 2026, which the server will cite."),
         "CREATOR_COPY_CONTENT"),
    ):
        with pytest.raises(CreatorCopyError) as rejected:
            parse_model_copy(content, row["model_context"])
        assert rejected.value.code == code
        assert "SECRET_INVALID_MODEL_OUTPUT" not in str(rejected.value)


@pytest.mark.parametrize("changes,code", [
    ({"hook": "This video explores server selection criteria and community engagement."},
     "CREATOR_COPY_EVIDENCE"),
    ({"hook": "The public title caught my attention; the video shows engaging server gameplay."},
     "CREATOR_COPY_EVIDENCE"),
    ({"hook": "This video highlights a Minecraft server experience that resonates with "
              "community-driven gameplay, aligning with the interests of creators focused "
              "on survival and multiplayer worlds."}, "CREATOR_COPY_EVIDENCE"),
    ({"hook": "The upload highlighted the server's friendly and active community."},
     "CREATOR_COPY_EVIDENCE"),
    ({"content_idea": "A creator could use the directory to find high-quality, community-driven "
                      "servers for their audience."}, "CREATOR_COPY_QUALITY"),
    ({"rationale": "This proposal aligns with the platform's verified Minecraft server options."},
     "CREATOR_COPY_QUALITY"),
])
def test_copy_cannot_turn_a_title_into_video_contents_or_server_quality_claims(changes, code):
    _, row, _ = setup()
    with pytest.raises(CreatorCopyError) as rejected:
        parse_model_copy(response(**changes), row["model_context"])
    assert rejected.value.code == code


def test_older_saved_copy_is_stale_when_current_evidence_checks_reject_it():
    campaign, prospect = fixture()
    row = {
        "input_hash": canonical_hash(draft_input_snapshot(campaign, prospect)),
        "model_context": model_context(campaign, prospect, creator_learning_insights([], [])),
        "model_copy": json.loads(response(
            hook="This video explores selection criteria and community engagement.",
        )),
    }
    with pytest.raises(CreatorDraftConflictError, match="current evidence checks"):
        check_draft_context(row, campaign, prospect)


def test_local_copy_repair_is_bounded_accounted_and_preserves_original_evidence(monkeypatch):
    task, row, database = setup()
    complete = Mock(side_effect=[
        (response(hook="Your Minecraft exploration title from 2026 caught my attention."), {}),
        (response(), {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}),
    ])
    monkeypatch.setattr(creator_drafting, "local_draft_completion", complete)
    result = creator_drafting.execute_creator_draft_task(task, database, get_settings())
    assert result["source"] == "ollama"
    assert complete.call_count == database.start_inference_invocation.call_count == 2
    first_messages = complete.call_args_list[0].args[0]
    repair_messages = complete.call_args_list[1].args[0]
    assert repair_messages[:-1] == first_messages == drafting_messages(row["model_context"])
    assert "2026" not in repair_messages[-1]["content"]
    assert "Remove numbers" in repair_messages[-1]["content"]
    database.fail_inference_invocation.assert_called_once()
    assert database.fail_inference_invocation.call_args.args[1] == "CREATOR_COPY_CONTENT"
    assert database.complete_inference_invocation.call_args.kwargs["fallback_attempt"] == 2
    database.save_draft.assert_called_once()


@pytest.mark.parametrize("interrupted", [True, False])
def test_cancellation_or_lease_loss_before_repair_prevents_another_model_call(
    monkeypatch, interrupted,
):
    task, row, database = setup()
    interrupt = threading.Event()

    def rejected(*_):
        if interrupted:
            interrupt.set()
        else:
            database.get_draft_for_execution.side_effect = InvalidTaskStateError("Lease lost")
        return "invalid", {}

    complete = Mock(side_effect=rejected)
    monkeypatch.setattr(creator_drafting, "local_draft_completion", complete)
    with pytest.raises(TaskInterruptedError if interrupted else InvalidTaskStateError):
        creator_drafting.execute_creator_draft_task(
            task, database, get_settings(), interrupt=interrupt,
        )
    complete.assert_called_once()
    database.start_inference_invocation.assert_called_once()
    database.save_draft.assert_not_called()


def test_local_transport_failure_is_distinct_and_not_retried(monkeypatch):
    task, _, database = setup()
    complete = Mock(side_effect=creator_drafting.CreatorDraftModelError("Unavailable"))
    monkeypatch.setattr(creator_drafting, "local_draft_completion", complete)
    with pytest.raises(creator_drafting.CreatorDraftModelError, match="No valid AI draft"):
        creator_drafting.execute_creator_draft_task(task, database, get_settings())
    complete.assert_called_once()
    assert database.fail_inference_invocation.call_args.args[1] == "CREATOR_LOCAL_UNAVAILABLE"
    database.save_draft.assert_not_called()


def test_bad_hosted_copy_is_accounted_and_next_private_free_route_used(monkeypatch):
    task, _, database = setup()
    client = Mock(spec=OpenRouterFreeClient)
    client.privacy_mode = "no-training/zdr"
    client.plan.return_value = OpenRouterPlan(("first:free", "second:free"), 20, True)
    client.complete.side_effect = [
        remote(response(content_idea="Perhaps guarantee a revenue share of 99%."), "first:free"),
        remote(response(), "second:free"),
    ]
    local = Mock()
    monkeypatch.setattr(creator_drafting, "local_draft_completion", local)
    result = creator_drafting.execute_creator_draft_task(
        task, database, get_settings(), client=client,
    )
    assert result["source"] == "openrouter"
    assert database.start_inference_invocation.call_count == 2
    database.fail_inference_invocation.assert_called_once()
    database.complete_inference_invocation.assert_called_once()
    client.reject_model.assert_called_once_with("first:free")
    local.assert_not_called()


def test_provider_outage_uses_accounted_local_and_never_exposes_error_body(monkeypatch):
    task, _, database = setup()
    client = Mock(spec=OpenRouterFreeClient)
    client.privacy_mode = "no-training/zdr"
    client.plan.return_value = OpenRouterPlan(("first:free",), 20, True)
    client.complete.side_effect = OpenRouterError("SECRET_PROVIDER_BODY", code="OUTAGE")
    monkeypatch.setattr(creator_drafting, "local_draft_completion",
                        Mock(return_value=(response(), {
                            "prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3,
                        })))
    result = creator_drafting.execute_creator_draft_task(
        task, database, replace(get_settings(), openrouter_local_fallback=True), client=client,
    )
    assert result["source"] == "ollama"
    assert "SECRET" not in json.dumps(result)
    assert [call.kwargs["provider"] for call in database.start_inference_invocation.call_args_list
            ] == ["openrouter", "ollama"]


def test_creator_local_thinking_is_bounded_and_only_final_copy_is_persisted(monkeypatch):
    task, _, database = setup()
    envelope = {
        "message": {"content": response(), "thinking": "PRIVATE_REASONING_MUST_NOT_ESCAPE"},
        "prompt_eval_count": 80, "eval_count": 120,
    }
    transport = Mock()
    received = Mock()
    received.read.return_value = json.dumps(envelope).encode()
    transport.open.return_value.__enter__ = Mock(return_value=received)
    transport.open.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(creator_drafting, "build_opener", Mock(return_value=transport))
    result = creator_drafting.execute_creator_draft_task(task, database, get_settings())
    request = transport.open.call_args.args[0]
    payload = json.loads(request.data)
    assert request.full_url == "http://ollama:11434/api/chat"
    assert payload["think"] is True and payload["stream"] is False
    assert payload["options"]["num_predict"] == 2048
    assert transport.open.call_args.kwargs["timeout"] == 180
    received.read.assert_called_once_with(65537)
    assert result["source"] == "ollama"
    assert database.complete_inference_invocation.call_args.kwargs["total_tokens"] == 200
    assert "PRIVATE_REASONING_MUST_NOT_ESCAPE" not in repr(database.mock_calls)
    database.save_draft.assert_called_once()


def test_reasoning_without_final_json_never_becomes_saved_creator_copy(monkeypatch):
    task, _, database = setup()
    transport = Mock()
    received = Mock()
    received.read.return_value = json.dumps({
        "message": {"content": "", "thinking": response()},
    }).encode()
    transport.open.return_value.__enter__ = Mock(return_value=received)
    transport.open.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(creator_drafting, "build_opener", Mock(return_value=transport))
    with pytest.raises(creator_drafting.CreatorDraftModelError, match="No valid AI draft"):
        creator_drafting.execute_creator_draft_task(task, database, get_settings())
    assert transport.open.call_count == database.start_inference_invocation.call_count == 2
    database.save_draft.assert_not_called()
    database.complete_inference_invocation.assert_not_called()


def test_cancellation_after_model_reply_prevents_persistence(monkeypatch):
    task, _, database = setup()
    interrupt = threading.Event()

    def complete(*_):
        interrupt.set()
        return response(), {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}

    monkeypatch.setattr(creator_drafting, "local_draft_completion", complete)
    with pytest.raises(TaskInterruptedError):
        creator_drafting.execute_creator_draft_task(
            task, database, get_settings(), interrupt=interrupt,
        )
    database.complete_inference_invocation.assert_called_once()
    database.save_draft.assert_not_called()


def test_lease_loss_after_reservation_refuses_egress(monkeypatch):
    task, row, database = setup()
    database.get_draft_for_execution.side_effect = [
        row, row, InvalidTaskStateError("Lease lost"),
    ]
    complete = Mock()
    monkeypatch.setattr(creator_drafting, "local_draft_completion", complete)
    with pytest.raises(InvalidTaskStateError):
        creator_drafting.execute_creator_draft_task(task, database, get_settings())
    complete.assert_not_called()
    database.fail_inference_invocation.assert_called_once()


@pytest.mark.parametrize("changes", [
    {"ai_draft_id": uuid4()},
    {"ai_draft_digest": "a" * 64},
    {"ai_draft_id": uuid4(), "ai_draft_digest": "a" * 64,
     "subject": "Edited", "body": "Edited body"},
    {"ai_draft_id": uuid4(), "ai_draft_digest": "a" * 64, "stage": "handoff"},
])
def test_ai_prepare_requires_immutable_initial_copy_and_digest(changes):
    with pytest.raises(ValueError):
        MarketingEmailPlanCreate.model_validate({"stage": "initial", "actor": "test", **changes})


def test_capability_cannot_be_downgraded_and_never_grants_email_authority():
    assert effective_risk("marketing.creator_draft", RiskLevel.LOW) == RiskLevel.MEDIUM
    assert effective_risk("communications.email_send", RiskLevel.LOW) == RiskLevel.HIGH


def polish_response(**changes):
    return response(
        **{
            "hook": "Temat odkrywania serwerów Minecraft z Twojego tytułu wydaje się "
                    "możliwym punktem wyjścia do niezależnej próby.",
            "content_idea": "Mógłbyś wybrać serwer z katalogu, samodzielnie sprawdzić dołączenie "
                            "i przed ewentualnym materiałem opisać własne doświadczenia.",
            **changes,
        },
    )


@pytest.mark.parametrize("language,mode,expected", [
    ("pl", "prefer", "pl"), ("pl-pl", "strict", "pl"), ("en-gb", "strict", "en"),
    ("pl", "any", "en"), (None, "any", "en"),
])
def test_campaign_language_freezes_generation_contract_without_model_choice(
    language, mode, expected,
):
    campaign, prospect = fixture()
    campaign.update(target_language=language, language_mode=mode)
    context = model_context(campaign, prospect, creator_learning_insights([], []))
    assert context["output_language"] == context_draft_language(context) == expected
    prompt = drafting_messages(context)[0]["content"]
    assert ("natural Polish" in prompt) is (expected == "pl")
    assert "Do not translate or rewrite campaign terms" in prompt


def test_unsupported_requested_language_is_explicit_and_legacy_context_remains_english():
    campaign, prospect = fixture()
    campaign.update(target_language="fr", language_mode="strict")
    assert "English and Polish only" in evidence_error(campaign, prospect)
    with pytest.raises(ValueError, match="English and Polish only"):
        model_context(campaign, prospect, creator_learning_insights([], []))
    assert context_draft_language({}) == "en"
    _, row, _ = setup()
    row["model_context"]["output_language"] = "PRIVATE_UNSUPPORTED_LANGUAGE"
    with pytest.raises(CreatorCopyError) as rejected:
        parse_model_copy(response(), row["model_context"])
    assert rejected.value.code == "CREATOR_COPY_LANGUAGE"
    assert "PRIVATE_" not in str(rejected.value)


def test_polish_copy_keeps_structured_keys_and_does_not_receive_private_terms_or_contacts():
    campaign, prospect = fixture()
    campaign.update(target_language="pl", language_mode="prefer")
    context = model_context(campaign, prospect, creator_learning_insights([], []))
    prompt = json.dumps(drafting_messages(context), ensure_ascii=False)
    assert "natural Polish" in prompt and "English operator explanation" in prompt
    assert "PRIVATE_" not in prompt
    assert "revenue_share_percent" not in prompt and "30%" not in prompt
    copy = parse_model_copy(polish_response(), context)
    assert copy.evidence_ids == ["sample_video"]
    assert copy.reach_strategy == "small_pilot"
    with pytest.raises(CreatorCopyError) as rejected:
        parse_model_copy(polish_response(output_language="en"), context)
    assert rejected.value.code == "CREATOR_COPY_SCHEMA"


@pytest.mark.parametrize("changes,code", [
    ({"hook": "Obejrzałem Twój film o serwerach Minecraft i świetnie się bawiłem."},
     "CREATOR_COPY_CONTENT"),
    ({"hook": "Ogladalem Twoj film o serwerach Minecraft i bardzo mi sie spodobal."},
     "CREATOR_COPY_CONTENT"),
    ({"content_idea": "Mógłbyś promować katalog, a my gwarantujemy świetne zarobki."},
     "CREATOR_COPY_CONTENT"),
    ({"content_idea": "Mógłbyś rozpocząć promocję za trzydzieści procent przez dwa tygodnie."},
     "CREATOR_COPY_CONTENT"),
    ({"content_idea": "Mógłbyś przygotować film, a my zaproponujemy Ci za niego sto zł."},
     "CREATOR_COPY_CONTENT"),
    ({"content_idea": "Mógłbyś opisać test, a Twoi widzowie na pewno pokochają tę platformę."},
     "CREATOR_COPY_CONTENT"),
    ({"content_idea": "Mógłbyś samodzielnie sprawdzić serwer, a następnie napisz do mnie."},
     "CREATOR_COPY_CONTENT"),
    ({"content_idea": "Mógłbyś od razu opisać najlepsze i zaufane serwery Minecraft z katalogu."},
     "CREATOR_COPY_QUALITY"),
    ({"hook": "Twój film pokazuje przyjazną społeczność na zweryfikowanym serwerze."},
     "CREATOR_COPY_EVIDENCE"),
    ({"content_idea": "Twórca mógłby samodzielnie przetestować serwer i opisać doświadczenia."},
     "CREATOR_COPY_RECIPIENT"),
    ({"content_idea": "Musisz wykonać film według scenariusza i opublikować pozytywną ocenę."},
     "CREATOR_COPY_OPTIONAL"),
    ({"rationale": "The owner should ask the creator: napisz do mnie po szczegóły."},
     "CREATOR_COPY_RATIONALE"),
])
def test_polish_claims_terms_contacts_and_required_promotion_are_refused(changes, code):
    campaign, prospect = fixture()
    campaign.update(target_language="pl", language_mode="strict")
    context = model_context(campaign, prospect, creator_learning_insights([], []))
    with pytest.raises(CreatorCopyError) as rejected:
        parse_model_copy(polish_response(**changes), context)
    assert rejected.value.code == code


def test_polish_contract_does_not_accept_english_optional_copy_as_polish():
    campaign, prospect = fixture()
    campaign.update(target_language="pl", language_mode="strict")
    context = model_context(campaign, prospect, creator_learning_insights([], []))
    with pytest.raises(CreatorCopyError) as rejected:
        parse_model_copy(response(), context)
    assert rejected.value.code == "CREATOR_COPY_OPTIONAL"


def test_polish_commercial_envelope_uses_exact_campaign_terms_not_model_translation():
    campaign, prospect = fixture()
    campaign.update(
        target_language="pl", language_mode="prefer",
        product_summary="katalog serwerów Minecraft do samodzielnego sprawdzenia",
        paid_offer_details="Opcjonalny test serwera w formacie wybranym przez twórcę",
        revenue_share_basis="zarobki przypisane uzgodnionej promocji",
    )
    context = model_context(campaign, prospect, creator_learning_insights([], []))
    copy = parse_model_copy(polish_response(), context)
    subject, body = compose_ai_email(campaign, prospect, copy, output_language="pl")
    assert "udział w zarobkach" in subject
    assert "30%" in body and "2 tygodnie" in body
    assert campaign["product_summary"] in body and campaign["paid_offer_details"] in body
    assert campaign["revenue_share_basis"] in body
    assert "bez gwarantowanej kwoty z góry" in body and "Przed publikacją" in body
    assert "przychód czy zysk" in body and "raportowanie i terminy wypłat" in body
    assert campaign["handoff_discord"] in body and campaign["handoff_email"] in body
    assert "PRIVATE_" not in json.dumps(context)
    assert copy.rationale not in body
    assert prospect["latest_content_url"] in body and campaign["privacy_url"] in body
    assert "do not contact" in body
    assert "Revenue-share" in compose_ai_email(campaign, prospect, copy)[0]


@pytest.mark.parametrize("compensation", ["revenue_share", "fixed_fee"])
def test_polish_envelope_does_not_invent_compensation_or_earning_window(compensation):
    campaign, prospect = fixture()
    campaign.update(compensation_model=compensation, revenue_share_percent=None,
                    revenue_share_weeks=None)
    copy = parse_model_copy(polish_response(), {"output_language": "pl", "creator": {
        "reach_strategy": "small_pilot",
    }})
    _, body = compose_ai_email(campaign, prospect, copy, output_language="pl")
    assert "30%" not in body and "2 tygodnie" not in body
    expected = ("Procent i liczbę tygodni uzgodnimy" if compensation == "revenue_share"
                else "Podaj swoją stawkę i preferowany format")
    assert expected in body


@pytest.mark.parametrize("marker", [None, "en", "pl"])
def test_save_uses_frozen_generation_language_even_when_campaign_targets_polish(
    monkeypatch, marker,
):
    from app import creator_draft_store

    campaign, prospect = fixture()
    campaign.update(target_language="pl", language_mode="prefer")
    context = model_context(campaign, prospect, creator_learning_insights([], []))
    if marker is None:
        context.pop("output_language")
    else:
        context["output_language"] = marker
    copy = parse_model_copy(polish_response() if marker == "pl" else response(), context)
    row = {"id": uuid4(), "status": "queued", "input_hash": "existing-input-hash",
           "model_context": context}
    store = CreatorDraftStore.__new__(CreatorDraftStore)
    connection = Mock()
    store.connect = Mock()
    store.connect.return_value.__enter__ = Mock(return_value=connection)
    store.connect.return_value.__exit__ = Mock(return_value=False)
    store._execution_row = Mock(return_value=(row, campaign, prospect))
    store._audit_draft = Mock()
    compose = Mock(wraps=compose_ai_email)
    monkeypatch.setattr(creator_draft_store, "compose_ai_email", compose)
    store.save_draft(draft_id=row["id"], task_id=uuid4(), lease_id=uuid4(), copy=copy,
                     source="ollama", selected_model="synthetic")
    assert compose.call_args.kwargs["output_language"] == (marker or "en")
    body = connection.execute.call_args.args[1][4]
    assert body.startswith("Cześć" if marker == "pl" else "Hi ")


@pytest.mark.parametrize("language,hook", [
    ("pl", "Mogłeś spotkać hakera w Minecraft, ale KarixMC pomaga sprawdzić bezpieczeństwo "
           "serwera przed dołączeniem. Sprawdź, jak działają oficjalne światy i czy nagrody "
           "są dostępne przed rekomendacją."),
    ("pl", "Mogłeś spotkać hakera w Minecraft, ale FixtureCraft pomaga sprawdzić bezpieczeństwo "
           "serwera przed dołączeniem. Sprawdź, jak działają oficjalne światy i czy nagrody "
           "są dostępne przed rekomendacją."),
    ("pl", "FixtureCraft sprawdza, czy serwery Minecraft są bezpieczne przed dołączeniem."),
    ("pl", "Ta platforma może zweryfikować bezpieczeństwo wybranego serwera Minecraft."),
    ("en", "FixtureCraft helps you check server security before you join a Minecraft world."),
    ("en", "The directory verifies that Minecraft servers are safe before recommending them."),
    ("en", "Our platform provides a security assessment of listed Minecraft servers."),
])
def test_product_security_verification_cannot_be_inferred_from_hacking_titles(language, hook):
    campaign, prospect = fixture()
    campaign.update(target_language=language, language_mode="prefer")
    campaign["product_name"] = "KarixMC" if "KarixMC" in hook else "FixtureCraft"
    prospect["latest_content_title"] = "A hacker on a Minecraft server"
    context = model_context(campaign, prospect, creator_learning_insights([], []))
    text = polish_response(hook=hook) if language == "pl" else response(hook=hook)
    with pytest.raises(CreatorCopyError) as rejected:
        parse_model_copy(text, context)
    assert rejected.value.code == "CREATOR_COPY_QUALITY"
    assert "does not provide server security verification" in str(rejected.value)


@pytest.mark.parametrize("language,idea", [
    ("pl", "Mógłbyś samodzielnie ocenić bezpieczeństwo wybranego serwera Minecraft, "
           "zanim zdecydujesz o własnej rekomendacji."),
    ("en", "You could use FixtureCraft to independently assess server safety before "
           "deciding whether to recommend your own findings."),
    ("pl", "FixtureCraft nie sprawdza bezpieczeństwa serwera; możesz samodzielnie "
           "ocenić wybrane miejsce przed ewentualną rekomendacją."),
    ("en", "The directory does not verify server safety; you could independently "
           "assess the selected server and report your findings."),
])
def test_independent_creator_assessment_and_explicit_platform_limits_remain_allowed(language, idea):
    campaign, prospect = fixture()
    campaign.update(target_language=language, language_mode="prefer")
    prospect["latest_content_title"] = "FixtureCraft verifies server security: a hacker challenge?"
    context = model_context(campaign, prospect, creator_learning_insights([], []))
    text = polish_response(content_idea=idea) if language == "pl" else response(content_idea=idea)
    assert parse_model_copy(text, context).content_idea == idea


def test_saved_unsupported_security_copy_conflicts_without_rewriting_its_snapshot():
    campaign, prospect = fixture()
    campaign.update(target_language="pl", language_mode="prefer")
    row = {
        "input_hash": canonical_hash(draft_input_snapshot(campaign, prospect)),
        "model_context": model_context(campaign, prospect, creator_learning_insights([], [])),
        "model_copy": json.loads(polish_response(
            hook="FixtureCraft pomaga sprawdzić bezpieczeństwo serwera przed dołączeniem.",
        )),
        "draft_digest": "existing-reviewed-digest",
    }
    before = json.dumps(row, sort_keys=True)
    with pytest.raises(CreatorDraftConflictError, match="current evidence checks"):
        check_draft_context(row, campaign, prospect)
    assert json.dumps(row, sort_keys=True) == before
