import pytest

from app.settings import ConfigurationError, Settings


def make_settings(**overrides: object) -> Settings:
    values = {
        "environment": "test",
        "log_level": "INFO",
        "api_token": "x" * 32,
        "database_url": "postgresql://user:pass@db/test",
        "redis_url": "redis://:pass@redis:6379/0",
        "task_queue_key": "agent:tasks:ready",
        "worker_poll_seconds": 5,
        "worker_lease_seconds": 120,
        "worker_heartbeat_seconds": 10,
        "worker_retry_base_seconds": 5,
        "worker_retry_max_seconds": 300,
    }
    values.update(overrides)
    return Settings(**values)


def test_rejects_placeholder_token() -> None:
    with pytest.raises(ConfigurationError, match="placeholder"):
        make_settings(api_token="CHANGE_ME_CONTROL_API_TOKEN").validate()  # noqa: S106


def test_rejects_short_token() -> None:
    with pytest.raises(ConfigurationError, match="at least 32"):
        make_settings(api_token="too-short").validate()  # noqa: S106


def test_accepts_complete_configuration() -> None:
    make_settings().validate()


def test_rejects_unsafe_worker_lease() -> None:
    with pytest.raises(ConfigurationError, match="WORKER_LEASE_SECONDS"):
        make_settings(worker_lease_seconds=10).validate()


def test_rejects_heartbeat_that_cannot_renew_before_half_lease() -> None:
    with pytest.raises(ConfigurationError, match="WORKER_HEARTBEAT_SECONDS"):
        make_settings(worker_heartbeat_seconds=61).validate()


def test_rejects_retry_max_below_retry_base() -> None:
    with pytest.raises(ConfigurationError, match="WORKER_RETRY_MAX_SECONDS"):
        make_settings(worker_retry_base_seconds=30, worker_retry_max_seconds=20).validate()
