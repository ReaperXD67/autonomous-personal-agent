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
