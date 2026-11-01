import pytest

from app.settings import ConfigurationError, Settings, career_gmail_credentials


def make_settings(**overrides: object) -> Settings:
    values = {
        "environment": "test",
        "log_level": "INFO",
        "api_token": "x" * 32,
        "trusted_hosts": ("localhost", "127.0.0.1", "testserver"),
        "dashboard_session_ttl_seconds": 43200,
        "dashboard_cookie_secure": False,
        "database_url": "postgresql://user:pass@db/test",
        "redis_url": "redis://:pass@redis:6379/0",
        "task_queue_key": "agent:tasks:ready",
        "job_queue_key": "agent:jobs:ready",
        "action_queue_key": "agent:actions:ready",
        "worker_poll_seconds": 5,
        "worker_lease_seconds": 120,
        "worker_heartbeat_seconds": 10,
        "worker_retry_base_seconds": 5,
        "worker_retry_max_seconds": 300,
        "career_scheduler_seconds": 30,
        "local_model": "qwen3:8b",
        "openrouter_enabled": False,
        "openrouter_api_key": "",
        "openrouter_model_priority": ("nvidia/example:free", "qwen/example:free"),
        "openrouter_max_models": 8,
        "openrouter_free_daily_allowance": 50,
        "openrouter_daily_request_cap": 900,
        "openrouter_data_collection": "deny",
        "openrouter_zdr": True,
        "openrouter_local_fallback": True,
        "mail_transport": "disabled",
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_username": "",
        "smtp_password": "",
        "smtp_from": "",
        "smtp_tls_mode": "starttls",
        "outbound_email_min_interval_seconds": 900,
        "outbound_email_domain_min_interval_seconds": 1800,
        "outbound_email_hourly_limit": 3,
        "outbound_email_daily_limit": 12,
        "outbound_email_jitter_seconds": 180,
        "youtube_api_key": "",
    }
    values.update(overrides)
    return Settings(**values)


def test_rejects_placeholder_token() -> None:
    with pytest.raises(ConfigurationError, match="placeholder"):
        make_settings(api_token="CHANGE_ME_CONTROL_API_TOKEN").validate()  # noqa: S106


def test_rejects_short_token() -> None:
    with pytest.raises(ConfigurationError, match="at least 32"):
        make_settings(api_token="too-short").validate()  # noqa: S106


def test_rejects_unbounded_or_url_shaped_trusted_hosts() -> None:
    with pytest.raises(ConfigurationError, match="explicit hostnames"):
        make_settings(trusted_hosts=("*",)).validate()
    with pytest.raises(ConfigurationError, match="explicit hostnames"):
        make_settings(trusted_hosts=("https://example.test",)).validate()


def test_accepts_complete_configuration() -> None:
    make_settings().validate()


def test_career_gmail_override_preserves_shared_creator_credentials() -> None:
    settings = make_settings(**{
        "gmail_client_id": "creator-id", "gmail_client_secret": "creator-secret",
        "gmail_refresh_token": "creator-refresh", "gmail_career_client_id": "career-id",
        "gmail_career_client_secret": "career-secret",
        "gmail_career_refresh_token": "career-refresh",
        "gmail_career_mailbox": "career@example.test",
    })
    settings.validate()
    assert career_gmail_credentials(settings, "CAREER@example.test") == (
        "career-id", "career-secret", "career-refresh",
    )
    shared = (settings.gmail_client_id, settings.gmail_client_secret, settings.gmail_refresh_token)
    assert shared == ("creator-id", "creator-secret", "creator-refresh")


def test_career_gmail_retains_legacy_complete_grant() -> None:
    settings = make_settings(**{
        "gmail_client_id": "legacy-id", "gmail_client_secret": "legacy-secret",
        "gmail_refresh_token": "legacy-refresh",
    })
    assert career_gmail_credentials(settings, "career@example.test") == (
        "legacy-id", "legacy-secret", "legacy-refresh",
    )


@pytest.mark.parametrize("overrides", [
    {"gmail_career_client_id": "career-id"},
    {"gmail_career_client_secret": "career-secret"},
    {"gmail_career_refresh_token": "career-refresh"},
    {"gmail_career_client_id": "career-id", "gmail_career_client_secret": "career-secret"},
])
def test_partial_career_gmail_never_borrows_shared_credentials(overrides) -> None:
    settings = make_settings(**{
        "gmail_client_id": "creator-id", "gmail_client_secret": "creator-secret",
        "gmail_refresh_token": "creator-refresh", **overrides,
    })
    with pytest.raises(ConfigurationError, match="configured together"):
        settings.validate()


def test_dedicated_career_gmail_requires_recorded_identity() -> None:
    settings = make_settings(**{
        "gmail_career_client_id": "career-id", "gmail_career_client_secret": "secret",
        "gmail_career_refresh_token": "refresh",
    })
    with pytest.raises(ConfigurationError, match="requires GMAIL_CAREER_MAILBOX"):
        settings.validate()


@pytest.mark.parametrize("mailbox", [
    "Career <career@example.test>", "career@example", "bad\n@example.test",
])
def test_career_gmail_requires_plain_recorded_mailbox(mailbox) -> None:
    with pytest.raises(ConfigurationError, match="one plain email"):
        make_settings(gmail_career_mailbox=mailbox).validate()


def test_career_gmail_recorded_identity_must_match_selected_profile() -> None:
    settings = make_settings(gmail_career_mailbox="career@example.test")
    with pytest.raises(ConfigurationError, match="must match the career profile"):
        career_gmail_credentials(settings, "different@example.test")


def test_career_gmail_environment_is_separate_and_normalizes_identity(monkeypatch) -> None:
    monkeypatch.setenv("CONTROL_API_TOKEN", "x" * 32)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost/0")
    monkeypatch.setenv("GMAIL_CLIENT_ID", "creator-id")
    monkeypatch.setenv("GMAIL_CAREER_CLIENT_ID", "career-id")
    monkeypatch.setenv("GMAIL_CAREER_CLIENT_SECRET", "career-secret")
    monkeypatch.setenv("GMAIL_CAREER_REFRESH_TOKEN", "career-refresh")
    monkeypatch.setenv("GMAIL_CAREER_MAILBOX", " Career@Example.Test ")
    settings = Settings.from_environment()
    assert settings.gmail_client_id == "creator-id"
    assert settings.gmail_career_mailbox == "career@example.test"
    assert career_gmail_credentials(settings) == ("career-id", "career-secret", "career-refresh")


def test_rejects_unbounded_browser_session_lifetime() -> None:
    with pytest.raises(ConfigurationError, match="DASHBOARD_SESSION_TTL_SECONDS"):
        make_settings(dashboard_session_ttl_seconds=120).validate()
    with pytest.raises(ConfigurationError, match="DASHBOARD_SESSION_TTL_SECONDS"):
        make_settings(dashboard_session_ttl_seconds=172800).validate()


def test_rejects_unsafe_worker_lease() -> None:
    with pytest.raises(ConfigurationError, match="WORKER_LEASE_SECONDS"):
        make_settings(worker_lease_seconds=10).validate()


def test_rejects_heartbeat_that_cannot_renew_before_half_lease() -> None:
    with pytest.raises(ConfigurationError, match="WORKER_HEARTBEAT_SECONDS"):
        make_settings(worker_heartbeat_seconds=61).validate()


def test_rejects_retry_max_below_retry_base() -> None:
    with pytest.raises(ConfigurationError, match="WORKER_RETRY_MAX_SECONDS"):
        make_settings(worker_retry_base_seconds=30, worker_retry_max_seconds=20).validate()


def test_rejects_overeager_career_scheduler() -> None:
    with pytest.raises(ConfigurationError, match="CAREER_SCHEDULER_SECONDS"):
        make_settings(career_scheduler_seconds=5).validate()


def test_openrouter_requires_free_models_and_a_key_when_enabled() -> None:
    with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY"):
        make_settings(openrouter_enabled=True).validate()
    with pytest.raises(ConfigurationError, match=":free"):
        make_settings(openrouter_model_priority=("paid/model",)).validate()
    with pytest.raises(ConfigurationError, match="50 or 1000"):
        make_settings(openrouter_free_daily_allowance=900).validate()
    make_settings(openrouter_model_priority=()).validate()


def test_external_smtp_requires_tls_and_complete_credentials() -> None:
    with pytest.raises(ConfigurationError, match="requires host"):
        make_settings(mail_transport="smtp").validate()
    with pytest.raises(ConfigurationError, match="must use TLS"):
        make_settings(
            mail_transport="smtp",
            smtp_host="smtp.example.test",
            smtp_username="user",
            smtp_password="password",  # noqa: S106
            smtp_from="user@example.test",
            smtp_tls_mode="none",
        ).validate()


def test_external_smtp_requires_plain_sender_and_bounded_pacing() -> None:
    valid = {
        "mail_transport": "smtp",
        "smtp_host": "smtp.example.test",
        "smtp_username": "user",
        "smtp_password": "password",  # noqa: S106
        "smtp_from": "user@example.test",
    }
    with pytest.raises(ConfigurationError, match="plain email"):
        make_settings(**{**valid, "smtp_from": "Hermes <user@example.test>"}).validate()
    with pytest.raises(ConfigurationError, match="MIN_INTERVAL_SECONDS"):
        make_settings(**valid, outbound_email_min_interval_seconds=30).validate()
    with pytest.raises(ConfigurationError, match="cannot be below"):
        make_settings(
            **valid,
            outbound_email_min_interval_seconds=1800,
            outbound_email_domain_min_interval_seconds=900,
        ).validate()
    with pytest.raises(ConfigurationError, match="DAILY_LIMIT"):
        make_settings(
            **valid,
            outbound_email_hourly_limit=4,
            outbound_email_daily_limit=3,
        ).validate()
    make_settings(**valid).validate()
