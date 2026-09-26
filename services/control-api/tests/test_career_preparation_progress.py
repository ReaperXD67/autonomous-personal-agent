import pytest

from app.career_autopilot_store import preparation_capacity, public_run


@pytest.mark.parametrize("cap,profile_used,run_used,expected", [
    (3, 0, 0, 6),
    (3, 3, 0, 6),  # A previous Prepare run does not exhaust a new Apply run.
    (3, 6, 6, 0),
    (3, 19, 0, 1),
    (3, 20, 0, 0),  # Repeated Play cannot reset the profile preparation budget.
    (3, 25, 0, 0),
    (10, 0, 0, 20),
    (1, 2, 0, 2),
    (1, 2, 2, 0),
])
def test_preparation_has_independent_profile_and_run_limits(
    cap, profile_used, run_used, expected,
):
    run = {"max_applications_per_day": cap, "used_today": cap}
    assert preparation_capacity(run, profile_used, run_used) == expected


def test_public_progress_distinguishes_preparation_from_applications_and_redacts_scope():
    result = public_run({
        "max_applications_per_day": 3, "used_today": 0,
        "preparation_used_today": 7, "run_preparation_used_today": 6,
        "answers": {"private": "screening answer"}, "profile_hash": "private digest",
    })
    assert result["used_today"] == 0
    assert result["preparation_used_today"] == 7
    assert result["run_preparation_used_today"] == 6
    assert result["preparation_limit_24h"] == 20
    assert result["run_preparation_limit_24h"] == 6
    assert "Run preparation limit" in result["preparation_limit_reason"]
    assert "answers" not in result
    assert "profile_hash" not in result


def test_profile_limit_reason_takes_precedence_and_available_run_has_no_budget_warning():
    base = {"max_applications_per_day": 3}
    assert public_run(base)["preparation_limit_reason"] is None
    blocked = public_run({**base, "preparation_used_today": 20, "run_preparation_used_today": 6})
    assert "Profile preparation limit" in blocked["preparation_limit_reason"]
