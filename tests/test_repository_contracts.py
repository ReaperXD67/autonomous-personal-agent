from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_compose_does_not_publish_data_store_ports() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "ports" not in compose["services"]["postgres"]
    assert "ports" not in compose["services"]["redis"]


def test_only_loopback_ports_are_published() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    for service in compose["services"].values():
        for port in service.get("ports", []):
            assert str(port).startswith("127.0.0.1:")


def test_every_long_running_service_has_healthcheck() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    for name, service in compose["services"].items():
        if name not in {"test", "migrate"}:
            assert "healthcheck" in service, name


def test_transactional_outbox_is_wired_into_runtime() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    schema = (ROOT / "config/postgres/init/001_schema.sql").read_text(encoding="utf-8")
    assert "dispatcher" in compose["services"]
    assert "task_outbox" in schema


def test_migrations_gate_runtime_startup() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "migrate" in compose["services"]
    for name in ("control-api", "dispatcher", "worker"):
        dependency = compose["services"][name]["depends_on"]["migrate"]
        assert dependency["condition"] == "service_completed_successfully"


def test_worker_lease_migration_is_present() -> None:
    migration = ROOT / "config/postgres/init/003_worker_leases.sql"
    assert migration.exists()
    source = migration.read_text(encoding="utf-8")
    assert "lease_expires_at" in source
    assert "max_attempts" in source


def test_execution_lifecycle_migration_and_smoke_are_present() -> None:
    migration = ROOT / "config/postgres/init/004_execution_lifecycle.sql"
    smoke = ROOT / "scripts/lifecycle-smoke.ps1"
    assert migration.exists()
    assert smoke.exists()
    source = migration.read_text(encoding="utf-8")
    for field in ("lease_id", "next_attempt_at", "cancellation_requested_at", "dead_lettered"):
        assert field in source


def test_restore_drill_uses_a_disposable_database() -> None:
    source = (ROOT / "scripts/restore-drill.ps1").read_text(encoding="utf-8")
    assert "agent_restore_" in source
    assert "dropdb" in source
    assert "RESTORE_DATABASE" in source


def test_repository_agent_guidance_enforces_engineering_records() -> None:
    guidance = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for required in (
        "ENGINEERING_JOURNAL.md",
        "SYSTEM_EVOLUTION.md",
        "EXPERIMENT_LOG.md",
        "scripts/verify.ps1",
    ):
        assert required in guidance


def test_env_example_contains_placeholders_not_common_secret_prefixes() -> None:
    content = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "CHANGE_ME" in content
    for prefix in ("ghp_", "sk-", "xoxb-", "AKIA"):
        assert prefix not in content


def test_accepted_starlette_advisory_surfaces_are_not_used() -> None:
    application_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "services/control-api/app").glob("*.py")
    )
    forbidden_surfaces = (
        "StaticFiles",
        "FileResponse",
        "HTTPEndpoint",
        ".form(",
        "request.url.hostname",
    )
    for surface in forbidden_surfaces:
        assert surface not in application_source
