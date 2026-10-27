from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.career_tracking import GmailSyncError
from app.creator_automation import (
    automation_campaign_hash,
    classify_creator_reply,
    correlate_creator_reply,
    creator_eligibility_reason,
    creator_key,
    run_block_reason,
    validate_creator_automation,
)
from app.creator_automation_gmail import execute_creator_gmail_sync
from app.creator_automation_models import CreatorAutomationStart

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def campaign():
    return {
        "outreach_mode": "paid",
        "paid_offer_details": "Discuss an individual revenue share",
        "handoff_discord": "karixai",
        "min_subscribers": 0,
        "max_subscribers": 10000000,
        "max_video_age_days": 120,
        "country_mode": "any",
        "language_mode": "any",
    }


def creator():
    return {
        "platform": "youtube",
        "external_id": "UCabCD",
        "audience_size": 100,
        "latest_content_published_at": NOW - timedelta(days=1),
        "intelligence": {"topics": ["Minecraft"], "geography": {}},
    }


def run(**changes):
    return {
        "state": "running",
        "expires_at": NOW + timedelta(hours=1),
        "campaign_hash": automation_campaign_hash(campaign()),
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"max_initials_per_day": 0},
        {"max_initials_per_day": 11},
        {"expires_in_hours": 0},
        {"expires_in_hours": 169},
        {"unrestricted": True},
    ],
)
def test_grant_is_finite_and_rejects_unknown_authority(changes):
    with pytest.raises(ValidationError):
        CreatorAutomationStart(actor="operator", **changes)


def test_defaults_do_not_include_automatic_handoff():
    request = CreatorAutomationStart(actor="operator")
    assert request.max_initials_per_day == 3
    assert request.expires_in_hours == 24
    assert request.auto_handoff is False


@pytest.mark.parametrize("state", ["paused", "expired", "blocked"])
def test_stopped_grants_cannot_send(state):
    assert run_block_reason(run(state=state), campaign(), NOW)


def test_expiry_boundary_and_changed_terms_revoke_grant():
    assert run_block_reason(run(), campaign(), NOW) is None
    assert "expired" in run_block_reason(run(expires_at=NOW), campaign(), NOW)
    assert "changed" in run_block_reason(run(), {**campaign(), "handoff_discord": "other"}, NOW)
    assert "changed" in run_block_reason(run(), {**campaign(), "max_subscribers": 10}, NOW)
    assert "changed" in run_block_reason(run(), {**campaign(), "paid_offer_details": "new"}, NOW)


def test_scan_time_and_schedule_do_not_revoke_message_scope():
    assert automation_campaign_hash(campaign()) == automation_campaign_hash(
        {**campaign(), "last_scan_at": "changed", "next_scan_at": "changed", "active": True},
    )


def test_channel_ids_are_case_sensitive_and_names_do_not_determine_identity():
    assert creator_key(creator()) != creator_key({**creator(), "external_id": "UCABCD"})
    assert creator_key(creator()) == creator_key({**creator(), "display_name": "changed"})


def test_observed_minecraft_content_and_current_targeting_are_required():
    assert creator_eligibility_reason(campaign(), creator(), NOW) is None
    assert "Minecraft" in creator_eligibility_reason(
        campaign(),
        {**creator(), "intelligence": {"topics": ["Gaming"]}},
        NOW,
    )
    assert "unknown" in creator_eligibility_reason(
        campaign(),
        {**creator(), "audience_size": None},
        NOW,
    )
    assert "recent" in creator_eligibility_reason(
        campaign(),
        {**creator(), "latest_content_published_at": None},
        NOW,
    )
    assert "scope" in creator_eligibility_reason(
        {**campaign(), "country_mode": "strict", "target_country": "PL"},
        creator(),
        NOW,
    )


@pytest.mark.parametrize(
    "text",
    [
        "Not interested",
        "Please unsubscribe",
        "Don't contact me again",
        "Sounds good but stop emailing",
        "Remove me from the list",
        "Thanks, please do not contact me again",
        "‘do not contact’",
        "I'm not interested",
        "I'm not saying do not contact, but please stop emailing me",
    ],
)
def test_opt_out_has_priority_over_positive_keywords(text):
    assert classify_creator_reply({"snippet": text}) == "do_not_contact"


@pytest.mark.parametrize(
    "quoted_history",
    [
        "On Fri, 16 October 2026, Operator wrote: Please reply ‘do not contact’ to opt out.",
        "> If you do not want another message, reply ‘do not contact’ and we will suppress "
        "this address immediately.",
        "-----Original Message----- Please reply 'do not contact' to opt out.",
        "---------- Forwarded message ---------- Please unsubscribe.",
        "Begin forwarded message: Please unsubscribe.",
        "From: operator@example.test Sent: Friday Please unsubscribe.",
        "If you do not want another message, reply ‘do not contact’ and we will suppress "
        "this address immediately.",
    ],
)
def test_interested_reply_with_quoted_opt_out_footer_is_not_suppressed(quoted_history):
    assert classify_creator_reply({"snippet": f"Yes, interested! {quoted_history}"}) == "interested"


@pytest.mark.parametrize(
    "text",
    [
        "I'm not saying do not contact",
        "I'm not saying, do not contact",
        "I don't want to unsubscribe",
        "You said reply ‘do not contact’ to opt out",
        "Your email says, 'do not contact'",
        "What happens if I reply ‘do not contact’?",
    ],
)
def test_mentioned_or_negated_opt_out_instruction_requires_review(text):
    assert classify_creator_reply({"snippet": text}) != "do_not_contact"


def test_direct_opt_out_before_quoted_positive_reply_still_wins():
    assert classify_creator_reply({
        "snippet": "Please stop emailing. On Friday, Operator wrote: Interested in collaboration?"
    }) == "do_not_contact"


def test_positive_classification_is_only_a_suggestion_from_snippet():
    assert classify_creator_reply({"snippet": "Interested. What percentage?"}) == "interested"
    assert (
        classify_creator_reply({"subject": "Interested in paid promotion", "snippet": ""})
        == "needs_review"
    )
    assert classify_creator_reply({"snippet": "What is the earning period?"}) == "question"


@pytest.mark.parametrize(
    "text",
    [
        "Nie jestem zainteresowany.",
        "Niestety nie jestem zainteresowana.",
        "Nie jesteśmy zainteresowani.",
        "Proszę nie pisać więcej.",
        "Proszę nie kontaktuj się ze mną.",
        "Nie wysyłajcie mi więcej maili.",
        "Usuń mnie z listy.",
        "Wypiszcie mnie.",
        "Nie chcę kolejnych wiadomości.",
        "Brzmi dobrze, ale proszę nie pisz do mnie więcej.",
        "Dzięki, nie jestem zainteresowany.",
        "Prosze nie pisac wiecej.",
    ],
)
def test_explicit_polish_opt_outs_take_priority(text):
    assert classify_creator_reply({"snippet": text}) == "do_not_contact"


@pytest.mark.parametrize(
    "history",
    [
        "W dniu 27 października 2026 Damian napisał: Proszę nie pisać więcej.",
        "Dnia 27 października Damian napisała: Nie jestem zainteresowana.",
        "Użytkownik Damian napisał: Do not contact.",
        "----- Wiadomość oryginalna ----- Nie jestem zainteresowany.",
        "----- Przekazana wiadomość ----- Please unsubscribe.",
        "Od: Damian Wysłano: wtorek Please unsubscribe.",
        "Od: Damian\nWysłano: wtorek\nPlease unsubscribe.",
        "Jeśli nie chcesz takich wiadomości, odpisz „do not contact”.",
    ],
)
def test_polish_quote_headers_and_flattened_footer_cannot_become_opt_outs(history):
    message = {"snippet": f"Jestem zainteresowany! {history}"}
    original = message.copy()
    assert classify_creator_reply(message) == "interested"
    assert message == original


@pytest.mark.parametrize(
    "text",
    [
        "I might be interested if the owner agrees a fixed fee.",
        "I'm not sure I am interested.",
        "I don't think it sounds good.",
        "If interested, you said to send details.",
        "Interested? I have not decided.",
        "I am interested only if there is a fixed fee.",
        "I am interested, but I'm not sure.",
        "Interested, but I haven't decided yet.",
        "Sounds good, however not for this channel.",
        "Byłbym zainteresowany, jeśli uzgodnimy stałą stawkę.",
        "Nie wiem, czy jestem zainteresowany.",
        "Jestem zainteresowana, jeśli ustalimy warunki.",
        "Jestem zainteresowany, ale tylko za stałą stawkę.",
        "Jestem zainteresowany, ale nie jestem pewien.",
        "Brzmi dobrze, jednak jeszcze nie zdecydowałem.",
        "Czy jesteście zainteresowani?",
        "Napisałeś, że jesteśmy zainteresowani.",
    ],
)
def test_negated_conditional_or_questioned_interest_is_not_a_positive_hint(text):
    assert classify_creator_reply({"snippet": text}) != "interested"


@pytest.mark.parametrize(
    "text",
    [
        "Jestem zainteresowany.",
        "Jesteśmy zainteresowane.",
        "Brzmi ciekawie!",
        "Porozmawiajmy.",
        "Prześlij mi szczegóły.",
        "Chętnie nawiążę współpracę.",
        "Nie miałem czasu odpisać. Jestem zainteresowany.",
        "I was not sure before, but I am interested.",
    ],
)
def test_asserted_english_and_polish_interest_remains_a_reviewable_hint(text):
    assert classify_creator_reply({"snippet": text}) == "interested"


@pytest.mark.parametrize(
    "text",
    [
        "Jaki procent proponujecie?",
        "Ile tygodni trwa rozliczenie",
        "Jak rozliczacie zarobki",
        "Jaki jest budżet",
    ],
)
def test_polish_commercial_questions_remain_questions(text):
    assert classify_creator_reply({"snippet": text}) == "question"


@pytest.mark.parametrize("text", ["Interested, but how much?", "Jestem zainteresowany, ale ile?"])
def test_interest_with_a_commercial_question_remains_a_question(text):
    assert classify_creator_reply({"snippet": text}) == "question"


@pytest.mark.parametrize(
    "text",
    [
        "Nie mówię, że nie jestem zainteresowany.",
        "Nie mówię, nie pisz.",
        "Nie proszę, żebyście usunęli mnie z listy.",
        "W instrukcji napisano: odpisz 'do not contact'.",
        "Napisałeś, żeby odpowiedzieć 'do not contact'.",
        "Napisaliście, nie pisz do mnie.",
        "Nie chcę się wypisać.",
    ],
)
def test_polish_mentions_and_negated_opt_outs_require_review(text):
    assert classify_creator_reply({"snippet": text}) != "do_not_contact"


def test_polish_actual_opt_out_before_quoted_positive_signal_stays_terminal():
    assert classify_creator_reply({
        "snippet": "Proszę nie pisać. W dniu 27 października Damian napisał: Brzmi dobrze!"
    }) == "do_not_contact"


def test_reply_match_requires_exact_address_subject_and_time():
    prospect_id = uuid4()
    sent = [
        {
            "prospect_id": prospect_id,
            "recipient": "creator@example.test",
            "subject": "Minecraft collaboration",
            "sent_at": NOW,
        }
    ]
    reply = {
        "sender": "creator@example.test",
        "subject": "Re: Minecraft collaboration",
        "received_at": NOW + timedelta(minutes=1),
    }
    assert correlate_creator_reply(reply, sent)[0] == prospect_id
    for changes in (
        {"sender": "other@example.test"},
        {"subject": "Different conversation"},
        {"received_at": NOW - timedelta(seconds=1)},
    ):
        assert correlate_creator_reply({**reply, **changes}, sent)[0] is None
    assert correlate_creator_reply(reply, sent + [{**sent[0], "prospect_id": uuid4()}])[0] is None


@pytest.mark.parametrize("prefix", ["Odp: ", "PD: ", "Odp: Re: PD: ", "re: ODP: "])
def test_polish_reply_prefixes_preserve_exact_creator_correlation(prefix):
    prospect_id = uuid4()
    sent = [{
        "prospect_id": prospect_id, "recipient": "creator@example.test",
        "subject": "Pomysł na współpracę", "sent_at": NOW,
    }]
    reply = {
        "sender": "creator@example.test", "subject": prefix + "Pomysł na współpracę",
        "received_at": NOW + timedelta(minutes=1),
    }
    assert correlate_creator_reply(reply, sent)[0] == prospect_id
    assert correlate_creator_reply({**reply, "sender": "other@example.test"}, sent)[0] is None
    assert correlate_creator_reply({**reply, "received_at": NOW - timedelta(seconds=1)}, sent)[0] \
        is None


def test_unreviewed_mail_blocks_even_individually_approved_marketing_actions():
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = {"pending": 1}
    reason = validate_creator_automation(
        connection,
        {
            "private_context": {
                "marketing": {"campaign_id": str(uuid4())},
            }
        },
    )
    assert "Review new creator replies" in reason


def test_unbound_automation_scope_never_creates_authority():
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = None
    reason = validate_creator_automation(
        connection,
        {
            "id": uuid4(),
            "context_hash": "abc",
            "private_context": {
                "creator_automation": {"run_id": str(uuid4())},
            },
        },
    )
    assert "reservation" in reason


def test_gmail_cannot_run_when_disabled():
    settings = Mock(creator_gmail_enabled=False)
    with pytest.raises(GmailSyncError, match="disabled"):
        execute_creator_gmail_sync({}, Mock(), settings)


def test_gmail_requires_separate_explicit_label_and_mailbox():
    settings = Mock(
        creator_gmail_enabled=True,
        creator_gmail_mailbox="operator@example.test",
        gmail_creator_label="Hermes/Careers",
        gmail_career_label="Hermes/Careers",
    )
    with pytest.raises(GmailSyncError, match="separate"):
        execute_creator_gmail_sync({}, Mock(), settings)


def test_gmail_wrong_account_stops_before_listing_or_persistence():
    settings = Mock(
        creator_gmail_enabled=True,
        creator_gmail_mailbox="operator@example.test",
        gmail_creator_label="Hermes/Creators",
        gmail_career_label="Hermes/Careers",
    )
    store = Mock()
    task = {"payload": {"campaign_id": str(uuid4())}}
    with patch("app.creator_automation_gmail.GmailReadClient") as client:
        client.return_value.mailbox.return_value = "different@example.test"
        with pytest.raises(GmailSyncError, match="does not match"):
            execute_creator_gmail_sync(task, store, settings)
        client.return_value.list_messages.assert_not_called()
        store.save_gmail.assert_not_called()
