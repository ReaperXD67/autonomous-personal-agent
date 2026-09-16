from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID


@dataclass(frozen=True, slots=True)
class EmailPacingPolicy:
    min_interval_seconds: int
    domain_min_interval_seconds: int
    hourly_limit: int
    daily_limit: int
    jitter_seconds: int


@dataclass(frozen=True, slots=True)
class EmailSendSlot:
    scheduled_for: datetime
    recipient_domain: str


def recipient_domain(address: str) -> str:
    _local, separator, domain = address.strip().rpartition("@")
    if not separator or not domain:
        raise ValueError("Email recipient domain is missing")
    return domain.rstrip(".").encode("idna").decode("ascii").lower()


def _respect_rolling_limit(
    candidate: datetime,
    scheduled: list[datetime],
    *,
    window: timedelta,
    limit: int,
) -> datetime:
    while True:
        inside = [value for value in scheduled if candidate - window < value <= candidate]
        if len(inside) < limit:
            return candidate
        candidate = min(inside) + window


def next_email_send_at(
    *,
    now: datetime,
    action_id: UUID,
    recipient: str,
    existing_slots: list[EmailSendSlot],
    policy: EmailPacingPolicy,
) -> datetime:
    """Return the next slot after applying global, domain, and rolling caps."""
    domain = recipient_domain(recipient)
    candidate = now
    if existing_slots:
        candidate = max(
            candidate,
            max(slot.scheduled_for for slot in existing_slots)
            + timedelta(seconds=policy.min_interval_seconds),
        )
    same_domain = [
        slot.scheduled_for
        for slot in existing_slots
        if slot.recipient_domain == domain
    ]
    if same_domain:
        candidate = max(
            candidate,
            max(same_domain) + timedelta(seconds=policy.domain_min_interval_seconds),
        )

    scheduled = [slot.scheduled_for for slot in existing_slots]
    candidate = _respect_rolling_limit(
        candidate,
        scheduled,
        window=timedelta(hours=1),
        limit=policy.hourly_limit,
    )
    candidate = _respect_rolling_limit(
        candidate,
        scheduled,
        window=timedelta(hours=24),
        limit=policy.daily_limit,
    )
    if policy.jitter_seconds:
        digest = hashlib.sha256(action_id.bytes).digest()
        jitter = int.from_bytes(digest[:4], "big") % (policy.jitter_seconds + 1)
        candidate += timedelta(seconds=jitter)
    return candidate
