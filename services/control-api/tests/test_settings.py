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
