from app.policy import (
    RiskLevel,
    capability_max_attempts,
    effective_risk,
    initial_status,
    requires_approval,
)


def test_only_high_impact_risks_require_approval() -> None:
    assert requires_approval(RiskLevel.LOW) is False
    assert requires_approval(RiskLevel.MEDIUM) is False
    assert requires_approval(RiskLevel.HIGH) is True
    assert requires_approval(RiskLevel.DESTRUCTIVE) is True


def test_initial_status_follows_approval_policy() -> None:
    assert initial_status(RiskLevel.LOW) == "queued"
    assert initial_status(RiskLevel.HIGH) == "pending_approval"


def test_caller_can_escalate_but_not_lower_capability_risk() -> None:
    assert effective_risk("foundation.echo", RiskLevel.HIGH) == RiskLevel.HIGH
    assert effective_risk("foundation.wait", RiskLevel.LOW) == RiskLevel.MEDIUM
    assert effective_risk("career.search", RiskLevel.LOW) == RiskLevel.LOW
    assert effective_risk("career.application_draft", RiskLevel.LOW) == RiskLevel.MEDIUM
    assert effective_risk("career.application_submit", RiskLevel.LOW) == RiskLevel.HIGH
    assert effective_risk("communications.email_send", RiskLevel.LOW) == RiskLevel.HIGH


def test_side_effects_are_never_automatically_retried() -> None:
    assert capability_max_attempts("career.application_submit") == 1
    assert capability_max_attempts("communications.email_send") == 1
    assert capability_max_attempts("career.application_preflight") == 3
