from __future__ import annotations

from enum import StrEnum


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DESTRUCTIVE = "destructive"


CAPABILITY_RISK: dict[str, RiskLevel] = {
    "foundation.echo": RiskLevel.LOW,
    "foundation.wait": RiskLevel.MEDIUM,
    "career.search": RiskLevel.LOW,
    "career.application_draft": RiskLevel.MEDIUM,
    "career.application_preflight": RiskLevel.MEDIUM,
    "career.application_submit": RiskLevel.HIGH,
    "communications.email_send": RiskLevel.HIGH,
}

SIDE_EFFECT_CAPABILITIES = {
    "career.application_submit",
    "communications.email_send",
}

_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.DESTRUCTIVE: 3,
}


def effective_risk(kind: str, requested: RiskLevel) -> RiskLevel:
    """Return allowlisted capability risk, permitting callers only to escalate it."""
    capability_risk = CAPABILITY_RISK[kind]
    return max((capability_risk, requested), key=_RISK_ORDER.__getitem__)


def requires_approval(risk_level: RiskLevel) -> bool:
    return risk_level in {RiskLevel.HIGH, RiskLevel.DESTRUCTIVE}


def initial_status(risk_level: RiskLevel) -> str:
    return "pending_approval" if requires_approval(risk_level) else "queued"


def capability_max_attempts(kind: str) -> int:
    """Consequential side effects never retry after an ambiguous worker crash."""
    return 1 if kind in SIDE_EFFECT_CAPABILITIES else 3
