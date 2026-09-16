from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.email_pacing import (
    EmailPacingPolicy,
    EmailSendSlot,
    next_email_send_at,
    recipient_domain,
)

POLICY = EmailPacingPolicy(
    min_interval_seconds=900,
    domain_min_interval_seconds=1800,
    hourly_limit=3,
    daily_limit=12,
    jitter_seconds=0,
)
NOW = datetime(2026, 9, 16, 10, 0, tzinfo=UTC)
ACTION_ID = UUID("00000000-0000-0000-0000-000000000001")


def slot(minutes: int, domain: str = "one.example") -> EmailSendSlot:
    return EmailSendSlot(NOW + timedelta(minutes=minutes), domain)


def test_pacing_spaces_global_and_same_domain_deliveries() -> None:
    global_next = next_email_send_at(
        now=NOW,
        action_id=ACTION_ID,
        recipient="creator@two.example",
        existing_slots=[slot(0)],
        policy=POLICY,
    )
    domain_next = next_email_send_at(
        now=NOW,
        action_id=ACTION_ID,
        recipient="creator@one.example",
        existing_slots=[slot(0)],
        policy=POLICY,
    )
    assert global_next == NOW + timedelta(minutes=15)
    assert domain_next == NOW + timedelta(minutes=30)


def test_pacing_uses_rolling_hour_and_day_windows() -> None:
    hourly = next_email_send_at(
        now=NOW,
        action_id=ACTION_ID,
        recipient="creator@new.example",
        existing_slots=[slot(-40), slot(-20), slot(0)],
        policy=POLICY,
    )
    daily_policy = EmailPacingPolicy(60, 300, 10, 3, 0)
    daily = next_email_send_at(
        now=NOW,
        action_id=ACTION_ID,
        recipient="creator@new.example",
        existing_slots=[slot(-1200), slot(-600), slot(0)],
        policy=daily_policy,
    )
    assert hourly == NOW + timedelta(minutes=20)
    assert daily == NOW + timedelta(hours=4)


def test_pacing_jitter_is_deterministic_and_normalizes_domains() -> None:
    policy = EmailPacingPolicy(900, 1800, 3, 12, 180)
    first = next_email_send_at(
        now=NOW,
        action_id=ACTION_ID,
        recipient="creator@EXAMPLE.test.",
        existing_slots=[],
        policy=policy,
    )
    second = next_email_send_at(
        now=NOW,
        action_id=ACTION_ID,
        recipient="creator@example.test",
        existing_slots=[],
        policy=policy,
    )
    assert first == second
    assert NOW <= first <= NOW + timedelta(seconds=180)
    assert recipient_domain("creator@EXAMPLE.test.") == "example.test"
