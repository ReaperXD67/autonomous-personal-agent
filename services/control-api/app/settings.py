from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is unsafe or missing."""


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    log_level: str
    api_token: str
    database_url: str
    redis_url: str
    task_queue_key: str
    job_queue_key: str
    action_queue_key: str
    worker_poll_seconds: int
    worker_lease_seconds: int
    worker_heartbeat_seconds: int
    worker_retry_base_seconds: int
    worker_retry_max_seconds: int
    career_scheduler_seconds: int
    local_model: str
    mail_transport: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from: str
    smtp_tls_mode: str

    @classmethod
    def from_environment(cls) -> Settings:
        settings = cls(
            environment=os.getenv("APP_ENV", "development").strip().lower(),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            api_token=os.getenv("CONTROL_API_TOKEN", "").strip(),
            database_url=os.getenv("DATABASE_URL", "").strip(),
            redis_url=os.getenv("REDIS_URL", "").strip(),
            task_queue_key=os.getenv("TASK_QUEUE_KEY", "agent:tasks:ready").strip(),
            job_queue_key=os.getenv("JOB_QUEUE_KEY", "agent:jobs:ready").strip(),
            action_queue_key=os.getenv("ACTION_QUEUE_KEY", "agent:actions:ready").strip(),
            worker_poll_seconds=int(os.getenv("WORKER_POLL_SECONDS", "5")),
            worker_lease_seconds=int(os.getenv("WORKER_LEASE_SECONDS", "120")),
            worker_heartbeat_seconds=int(os.getenv("WORKER_HEARTBEAT_SECONDS", "10")),
            worker_retry_base_seconds=int(os.getenv("WORKER_RETRY_BASE_SECONDS", "5")),
            worker_retry_max_seconds=int(os.getenv("WORKER_RETRY_MAX_SECONDS", "300")),
            career_scheduler_seconds=int(os.getenv("CAREER_SCHEDULER_SECONDS", "30")),
            local_model=os.getenv("LOCAL_MODEL", "qwen3:8b").strip(),
            mail_transport=os.getenv("MAIL_TRANSPORT", "disabled").strip().lower(),
            smtp_host=os.getenv("SMTP_HOST", "").strip(),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_username=os.getenv("SMTP_USERNAME", "").strip(),
            smtp_password=os.getenv("SMTP_PASSWORD", "").strip(),
            smtp_from=os.getenv("SMTP_FROM", "").strip(),
            smtp_tls_mode=os.getenv("SMTP_TLS_MODE", "starttls").strip().lower(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        missing = [
            name
            for name, value in (
                ("CONTROL_API_TOKEN", self.api_token),
                ("DATABASE_URL", self.database_url),
                ("REDIS_URL", self.redis_url),
                ("TASK_QUEUE_KEY", self.task_queue_key),
                ("JOB_QUEUE_KEY", self.job_queue_key),
                ("ACTION_QUEUE_KEY", self.action_queue_key),
                ("LOCAL_MODEL", self.local_model),
            )
            if not value
        ]
        if missing:
            raise ConfigurationError(f"Missing required settings: {', '.join(missing)}")
        if self.api_token.startswith("CHANGE_ME"):
            raise ConfigurationError("CONTROL_API_TOKEN still contains a placeholder")
        if len(self.api_token) < 32:
            raise ConfigurationError("CONTROL_API_TOKEN must contain at least 32 characters")
        if not 1 <= self.worker_poll_seconds <= 60:
            raise ConfigurationError("WORKER_POLL_SECONDS must be between 1 and 60")
        if not 30 <= self.worker_lease_seconds <= 3600:
            raise ConfigurationError("WORKER_LEASE_SECONDS must be between 30 and 3600")
        if not 1 <= self.worker_heartbeat_seconds <= self.worker_lease_seconds // 2:
            raise ConfigurationError(
                "WORKER_HEARTBEAT_SECONDS must be at least 1 and no more than half the lease"
            )
        if not 1 <= self.worker_retry_base_seconds <= 300:
            raise ConfigurationError("WORKER_RETRY_BASE_SECONDS must be between 1 and 300")
        if not self.worker_retry_base_seconds <= self.worker_retry_max_seconds <= 3600:
            raise ConfigurationError(
                "WORKER_RETRY_MAX_SECONDS must be between the retry base and 3600"
            )
        if not 10 <= self.career_scheduler_seconds <= 300:
            raise ConfigurationError("CAREER_SCHEDULER_SECONDS must be between 10 and 300")
        if self.mail_transport not in {"disabled", "mailpit", "smtp"}:
            raise ConfigurationError("MAIL_TRANSPORT must be disabled, mailpit, or smtp")
        if not 1 <= self.smtp_port <= 65535:
            raise ConfigurationError("SMTP_PORT must be between 1 and 65535")
        if self.smtp_tls_mode not in {"starttls", "ssl", "none"}:
            raise ConfigurationError("SMTP_TLS_MODE must be starttls, ssl, or none")
        if self.mail_transport == "mailpit" and (
            self.smtp_host != "mailpit"
            or self.smtp_tls_mode != "none"
            or not self.smtp_from
        ):
            raise ConfigurationError(
                "Mailpit transport requires host=mailpit, TLS=none, and a sender"
            )
        if self.mail_transport == "smtp":
            if not all((self.smtp_host, self.smtp_username, self.smtp_password, self.smtp_from)):
                raise ConfigurationError(
                    "SMTP transport requires host, username, password, and from address"
                )
            if self.smtp_tls_mode == "none":
                raise ConfigurationError("External SMTP transport must use TLS")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()
