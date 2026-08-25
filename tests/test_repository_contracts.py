import re
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
    for name in ("control-api", "dispatcher", "worker", "job-worker", "action-worker"):
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


def test_career_workflow_has_isolated_egress_worker_and_durable_schema() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    worker = compose["services"]["worker"]
    job_worker = compose["services"]["job-worker"]
    assert "edge" not in worker["networks"]
    assert set(job_worker["networks"]) == {"edge", "data", "model"}
    assert job_worker["command"] == ["python", "-m", "app.job_worker"]
    migration = ROOT / "config/postgres/init/005_career_workflow.sql"
    assert migration.exists()
    source = migration.read_text(encoding="utf-8")
    for table in ("career_profiles", "job_opportunities", "job_application_drafts"):
        assert table in source


def test_dashboard_is_packaged_without_forbidden_static_file_surfaces() -> None:
    index = ROOT / "services/control-api/app/web/index.html"
    script = ROOT / "services/control-api/app/web/app.js"
    assert index.exists() and script.exists()
    assert "Hermes Command Center" in index.read_text(encoding="utf-8")
    javascript = script.read_text(encoding="utf-8")
    assert "sessionStorage" not in javascript
    for dangerous_sink in ("innerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert dangerous_sink not in javascript


def test_external_actions_use_isolated_pinned_workers_and_exact_receipts() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    action_worker = compose["services"]["action-worker"]
    assert set(action_worker["networks"]) == {"edge", "data"}
    assert action_worker["read_only"] is True
    assert action_worker["cap_drop"] == ["ALL"]
    assert "profiles" in action_worker
    assert not action_worker.get("volumes")
    assert "@sha256:" in compose["services"]["mailpit"]["image"]
    migration = (
        ROOT / "config/postgres/init/006_exact_external_actions.sql"
    ).read_text(encoding="utf-8")
    for table in (
        "external_actions",
        "side_effect_receipts",
        "job_application_preflights",
    ):
        assert table in migration
    source = (ROOT / "services/control-api/app/action_store.py").read_text(
        encoding="utf-8"
    )
    assert "action_context_hash" in source
    assert "retry refused" in source


def test_action_image_scan_exceptions_are_exact_and_expiring() -> None:
    ignores = yaml.safe_load((ROOT / ".trivyignore.yaml").read_text(encoding="utf-8"))
    entries = ignores["vulnerabilities"]
    assert {entry["id"] for entry in entries} == {
        "GHSA-6v7p-g79w-8964",
        "CVE-2025-47273",
    }
    assert all(entry.get("purls") and entry.get("expired_at") for entry in entries)
    dockerfile = (ROOT / "services/action-worker/Dockerfile").read_text(encoding="utf-8")
    assert "rm -rf /tmp/uv-cache" in dockerfile


def test_restore_drill_uses_a_disposable_database() -> None:
    source = (ROOT / "scripts/restore-drill.ps1").read_text(encoding="utf-8")
    assert "agent_restore_" in source
    assert "dropdb" in source
    assert "RESTORE_DATABASE" in source


def test_readiness_gate_covers_every_configured_runtime_path() -> None:
    source = (ROOT / "scripts/readiness.ps1").read_text(encoding="utf-8")
    for required in (
        "verify.ps1",
        "restore-drill.ps1",
        "doctor.ps1",
        "agent-smoke.ps1",
        "local-model.ps1",
        "HERMES_READY_OK",
        "runtime/readiness",
    ):
        assert required in source


def test_local_model_smoke_reuses_a_verified_cached_model() -> None:
    source = (ROOT / "scripts/local-model.ps1").read_text(encoding="utf-8")
    assert "ollama list" in source
    assert "modelInstalled" in source
    assert "ForcePull" in source


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


def test_ci_actions_are_immutable_and_security_gates_are_required() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    action_refs = re.findall(r"uses:\s+[^\s@]+@([^\s#]+)", workflow)
    assert action_refs
    assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs)
    for required in (
        "dependency-review-action",
        "aquasecurity/trivy-action",
        "anchore/sbom-action",
        "scanners: vuln,secret,misconfig",
        "version: v0.74.0",
        "control-api-sbom",
        "action-worker-sbom",
        "trivyignores: .trivyignore.yaml",
    ):
        assert required in workflow
