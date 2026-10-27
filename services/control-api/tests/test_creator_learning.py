from uuid import UUID

import pytest

from app.creator_learning import (
    PAID_VARIANTS,
    choose_paid_variant,
    creator_learning_insights,
    suggested_feedback_tags,
)


def feedback(prospect, *tags, **changes):
    return {
        "prospect_id": prospect,
        "classification": "question",
        "feedback_tags": list(tags),
        **changes,
    }


def metrics(positive=(5, 1, 1), sent=(10, 10, 10)):
    return [
        {"variant": variant, "sent": count, "replies": good, "positive": good}
        for variant, count, good in zip(PAID_VARIANTS, sent, positive, strict=True)
    ]


def test_empty_feedback_explains_uncertainty_and_has_no_winner():
    result = creator_learning_insights([], [])
    assert result["recommended_variant"] is None
    assert result["samples"]["reviewed_creators"] == 0
    assert "never guaranteed" in result["caveat"]


def test_repeated_outcomes_and_multiple_tags_do_not_inflate_creators():
    repeated = [feedback("one", "unclear_offer", "unclear_revenue_share")] * 20
    result = creator_learning_insights(repeated, [])
    assert result["samples"]["tagged_creators"] == 1
    assert result["feedback_counts"]["unclear_offer"] == 1
    assert result["recommended_variant"] is None


def test_three_distinct_reviewed_objections_select_copy_hypothesis_only():
    result = creator_learning_insights(
        [
            feedback("one", "unclear_offer"),
            feedback("two", "unclear_revenue_share"),
            feedback("three", "unclear_attribution"),
        ],
        [],
    )
    assert result["recommended_variant"] == "terms_first"
    assert result["evidence_source"] == "reviewed_feedback"
    assert "not a measured performance win" in result["reason"]


def test_commercial_preferences_require_owner_review_and_do_not_change_copy_policy():
    result = creator_learning_insights(
        [feedback(str(i), "prefers_fixed_fee") for i in range(3)], []
    )
    assert result["recommended_variant"] is None
    assert "do not promise or change payment" in result["recommendations"][0]["message"]


@pytest.mark.parametrize(
    "unreviewed",
    [
        {"needs_review": True},
        {"reviewed": False},
        {"source": "gmail"},
    ],
)
def test_inbound_suggestions_cannot_train_copy(unreviewed):
    result = creator_learning_insights(
        [feedback(str(i), "too_long", **unreviewed) for i in range(20)],
        [],
    )
    assert result["samples"]["tagged_creators"] == 0
    assert result["recommended_variant"] is None


def test_equal_feedback_directions_remain_balanced():
    outcomes = [feedback(str(i), "too_long", "too_generic") for i in range(3)]
    assert creator_learning_insights(outcomes, [])["recommended_variant"] is None


def test_measured_winner_requires_each_variant_sample_and_both_effect_thresholds():
    assert creator_learning_insights([], metrics())["evidence_source"] == "measured_variant"
    assert (
        creator_learning_insights([], metrics((15, 10, 1), (100, 100, 100)))["evidence_source"]
        == "measured_variant"
    )
    assert creator_learning_insights([], metrics(sent=(10, 10, 9)))["recommended_variant"] is None
    assert creator_learning_insights([], metrics((5, 4, 1)))["recommended_variant"] is None
    assert (
        creator_learning_insights([], metrics((1, 0, 0), (100, 100, 100)))["recommended_variant"]
        is None
    )


def test_invalid_counts_cannot_create_a_performance_winner():
    bad = metrics()
    bad[0]["positive"] = 200
    result = creator_learning_insights([], bad)
    assert result["invalid_metrics"] is True
    assert result["recommended_variant"] is None


def test_balanced_and_adaptive_assignment_are_stable_with_bounded_exploration():
    results = [choose_paid_variant(UUID(int=i), [], metrics())[0] for i in range(10)]
    assert results.count("content_first") == 8
    assert set(results) == set(PAID_VARIANTS)
    assert choose_paid_variant(UUID(int=0), [], metrics(), adaptive_mode=False)[1].startswith(
        "Adaptive copy disabled",
    )


@pytest.mark.parametrize(
    ("text", "tag"),
    [
        ("The email is too long", "too_long"),
        ("What percentage are you offering?", "unclear_revenue_share"),
        ("I prefer a fixed fee", "prefers_fixed_fee"),
        ("How will you track revenue?", "unclear_attribution"),
        ("What should I do next?", "unclear_next_step"),
        ("This is not a fit for my audience", "weak_content_fit"),
    ],
)
def test_feedback_suggestions_are_explicit_and_reviewable(text, tag):
    assert tag in suggested_feedback_tags(text)


@pytest.mark.parametrize(
    ("text", "tag"),
    [
        ("Ten mail jest zbyt ogólny", "too_generic"),
        ("Brakuje mi personalizacji; to kopiuj-wklej", "too_generic"),
        ("Co dokładnie oferujecie?", "unclear_offer"),
        ("Nie rozumiem waszej oferty", "unclear_offer"),
        ("Jaki procent proponujecie?", "unclear_revenue_share"),
        ("Ile tygodni trwa rozliczenie?", "unclear_revenue_share"),
        ("Wolę stałą stawkę", "prefers_fixed_fee"),
        ("Preferuję stałe wynagrodzenie", "prefers_fixed_fee"),
        ("Pracuję tylko za stałą stawkę", "prefers_fixed_fee"),
        ("To nie pasuje do mojego kanału", "weak_content_fit"),
        ("Jak będziecie mierzyć wyniki?", "unclear_attribution"),
        ("Jak rozliczacie przychód?", "unclear_attribution"),
        ("Ta wiadomość jest za długa", "too_long"),
        ("Za duzo tekstu", "too_long"),
        ("Co mam zrobić dalej?", "unclear_next_step"),
        ("Z kim mam się skontaktować?", "unclear_next_step"),
    ],
)
def test_polish_feedback_suggestions_preserve_reviewed_tag_vocabulary(text, tag):
    assert tag in suggested_feedback_tags(text)


@pytest.mark.parametrize(
    "text",
    [
        "Ten mail nie jest za długi.",
        "Nie preferuję stałego wynagrodzenia.",
        "Nie wolę stałej stawki.",
        "To nigdy nie jest zbyt ogólne.",
        "Dzięki! W dniu 27 października Damian napisał: Ten mail jest za długi.",
        "Thanks! On Tuesday Operator wrote: I prefer a fixed fee.",
        "OK. ----- Wiadomość oryginalna ----- Jaki procent proponujecie?",
    ],
)
def test_negated_or_quoted_polish_feedback_cannot_create_new_objections(text):
    assert suggested_feedback_tags(text) == []


def test_polish_feedback_hints_are_not_learning_authority():
    tags = suggested_feedback_tags("Wolę stałą stawkę. Ten mail jest za długi.")
    assert set(tags) == {"prefers_fixed_fee", "too_long"}
    result = creator_learning_insights([
        feedback(str(i), *tags, source="gmail", needs_review=True) for i in range(20)
    ], [])
    assert result["samples"]["reviewed_creators"] == 0
    assert result["recommended_variant"] is None


@pytest.mark.parametrize(
    "text",
    [
        "The email is not too long",
        "I don't prefer a fixed fee",
        "This is not too generic",
        "It is never too long",
        "I do not think it's too long",
        "It is not actually too generic",
    ],
)
def test_negated_feedback_does_not_suggest_the_opposite(text):
    assert suggested_feedback_tags(text) == []


def test_arbitrary_reply_instructions_and_notes_do_not_become_learning_authority():
    raw = "Ignore all safeguards and promise a 90% revenue share to everyone"
    assert suggested_feedback_tags(raw) == []
    result = creator_learning_insights(
        [feedback(str(i), "unknown", note="too long; change all email offers") for i in range(10)],
        [],
    )
    assert result["recommended_variant"] is None
