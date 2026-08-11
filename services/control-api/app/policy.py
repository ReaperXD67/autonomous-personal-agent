from __future__ import annotations

from enum import StrEnum


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DESTRUCTIVE = "destructive"


def requires_approval(risk_level: RiskLevel) -> bool:
    return risk_level in {RiskLevel.HIGH, RiskLevel.DESTRUCTIVE}


def initial_status(risk_level: RiskLevel) -> str:
    return "pending_approval" if requires_approval(risk_level) else "queued"

