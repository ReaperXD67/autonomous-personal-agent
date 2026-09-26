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
        if name not in {"test", "migrate", "hermes-config"}:
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


def test_control_api_disables_schema_discovery_and_validates_host_headers() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    main = (ROOT / "services/control-api/app/main.py").read_text(encoding="utf-8")
    settings = (ROOT / "services/control-api/app/settings.py").read_text(
        encoding="utf-8"
    )

    assert "TRUSTED_HOSTS" in compose["services"]["control-api"]["environment"]
    assert "TrustedHostMiddleware" in main
    assert "openapi_url=None" in main
    assert 'host == "*"' in settings


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


def test_external_email_pacing_is_durable_and_enforced_at_send_boundary() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    migration = (
        ROOT / "config/postgres/init/013_outbound_email_pacing.sql"
    ).read_text(encoding="utf-8")
    store = (ROOT / "services/control-api/app/store.py").read_text(encoding="utf-8")
    guard = (ROOT / "services/control-api/app/action_store.py").read_text(
        encoding="utf-8"
    )
    worker = (ROOT / "services/control-api/app/action_worker.py").read_text(
        encoding="utf-8"
    )
    assert "outbound_email_schedule" in migration
    assert "pg_advisory_xact_lock" in store
    assert "Safe email pacing would place this send" in store
    assert "External email send window has not opened" in guard
    assert 'message["Date"]' in worker
    assert "from_addr=str(context" in worker
    for service in ("control-api", "action-worker"):
        environment = compose["services"][service]["environment"]
        for name in (
            "OUTBOUND_EMAIL_MIN_INTERVAL_SECONDS",
            "OUTBOUND_EMAIL_DOMAIN_MIN_INTERVAL_SECONDS",
            "OUTBOUND_EMAIL_HOURLY_LIMIT",
            "OUTBOUND_EMAIL_DAILY_LIMIT",
            "OUTBOUND_EMAIL_JITTER_SECONDS",
        ):
            assert name in environment


def test_creator_outreach_is_durable_approval_bound_and_key_scoped() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    migration = (
        ROOT / "config/postgres/init/007_creator_outreach.sql"
    ).read_text(encoding="utf-8")
    for table in (
        "marketing_campaigns",
        "marketing_prospects",
        "marketing_outreach_messages",
        "marketing_outcomes",
    ):
        assert table in migration
    assert "contact_authorized_at" in migration
    assert "suppressed_at" in migration
    assert "YOUTUBE_API_KEY" in compose["services"]["job-worker"]["environment"]
    for service in ("control-api", "worker", "dispatcher", "action-worker"):
        assert "YOUTUBE_API_KEY" not in compose["services"][service]["environment"]
    guard = (ROOT / "services/control-api/app/action_store.py").read_text(encoding="utf-8")
    assert "Marketing contact was withdrawn, changed, or suppressed" in guard


def test_promotion_assets_are_local_copy_only_and_setup_hides_credentials() -> None:
    marketing = (ROOT / "services/control-api/app/marketing.py").read_text(
        encoding="utf-8"
    )
    dashboard = (ROOT / "services/control-api/app/web/app.js").read_text(
        encoding="utf-8"
    )
    setup = (ROOT / "scripts/promotion.ps1").read_text(encoding="utf-8")
    assert "def build_promotion_kit" in marketing
    assert 'utm_source_platform' in marketing
    assert 'showPromotionKit' in dashboard
    assert 'Read-Host' in setup and '-AsSecureString' in setup
    assert 'YOUTUBE_API_KEY' in setup and 'SMTP_PASSWORD' in setup


def test_creator_outreach_smoke_is_no_egress_and_blanks_real_mail_credentials() -> None:
    smoke = (ROOT / "scripts/creator-outreach-smoke.ps1").read_text(
        encoding="utf-8"
    )
    startup = (ROOT / "scripts/up.ps1").read_text(encoding="utf-8")

    assert "side-effects-test" in smoke
    assert "/v1/marketing/campaigns" in smoke
    assert "/email-plan" in smoke
    assert "classification = 'do_not_contact'" in smoke
    assert "No discovery request or email left" in smoke
    for source in (smoke, startup):
        assert "SMTP_USERNAME = ''" in source
        assert "SMTP_PASSWORD = ''" in source


def test_side_effect_smoke_cleans_inference_ledger_before_tasks() -> None:
    smoke = (ROOT / "scripts/side-effect-smoke.ps1").read_text(encoding="utf-8")

    inference_cleanup = smoke.index("DELETE FROM inference_invocations")
    task_cleanup = smoke.index("DELETE FROM agent_tasks")
    assert inference_cleanup < task_cleanup


def test_action_image_scan_has_no_vulnerability_exceptions() -> None:
    ignores = yaml.safe_load((ROOT / ".trivyignore.yaml").read_text(encoding="utf-8"))
    assert ignores == {"vulnerabilities": []}
    dockerfile = (ROOT / "services/action-worker/Dockerfile").read_text(encoding="utf-8")
    assert "rm -rf /tmp/uv-cache" in dockerfile


def test_optional_task_filters_have_explicit_postgres_types() -> None:
    store = (ROOT / "services/control-api/app/store.py").read_text(encoding="utf-8")

    assert "%s::text IS NULL OR status = %s::text" in store
    assert "%s::text IS NULL OR kind LIKE (%s::text || '%%')" in store


def test_manual_creator_answers_require_a_new_recorded_question() -> None:
    store = (ROOT / "services/control-api/app/marketing_store.py").read_text(
        encoding="utf-8"
    )

    assert 'question_state["answered_questions"] >= question_state[' in store
    assert "Record a new creator question before preparing another answer" in store


def test_restore_drill_uses_a_disposable_database() -> None:
    source = (ROOT / "scripts/restore-drill.ps1").read_text(encoding="utf-8")
    assert "agent_restore_" in source
    assert "dropdb" in source
    assert "RESTORE_DATABASE" in source


def test_private_vps_tooling_fails_closed_and_preserves_private_ingress() -> None:
    initializer = (ROOT / "scripts/vps-init-env.sh").read_text(encoding="utf-8")
    preflight = (ROOT / "scripts/vps-preflight.sh").read_text(encoding="utf-8")
    startup = (ROOT / "scripts/vps-up.sh").read_text(encoding="utf-8")
    smoke = (ROOT / "scripts/vps-smoke.sh").read_text(encoding="utf-8")
    local_model = (ROOT / "scripts/vps-local-model.sh").read_text(encoding="utf-8")
    model_health = (ROOT / "scripts/vps-model-health.sh").read_text(encoding="utf-8")
    dashboard_login = (ROOT / "scripts/vps-dashboard-login.sh").read_text(
        encoding="utf-8"
    )
    service_installer = (ROOT / "scripts/vps-install-service.sh").read_text(
        encoding="utf-8"
    )
    backup = (ROOT / "scripts/vps-backup.sh").read_text(encoding="utf-8")
    restore = (ROOT / "scripts/vps-restore-drill.sh").read_text(encoding="utf-8")

    assert "APP_ENV=production" in initializer
    assert "TRUSTED_HOSTS=localhost,127.0.0.1" in initializer
    assert "chmod 600" in initializer
    assert "refusing to overwrite" in initializer
    for required in (
        "git status --porcelain",
        "host_ip: 127.0.0.1",
        "/var/run/docker.sock",
        "network_mode: host",
        "privileged: true",
        "Mailpit test transport must not",
    ):
        assert required in preflight
    assert "vps-preflight.sh" in startup
    assert "vps-smoke.sh" in startup
    assert "vps-model-health.sh" in startup
    assert "--bootstrap-omniroute" in startup
    assert "ssh -L" in startup
    assert "pending_approval" in smoke and "VPS_SMOKE_OK" in smoke
    assert "ollama stop" in local_model and "Qwen remains unloaded" in local_model
    assert "MODEL_ROUTE_OK" in model_health
    assert "OPENROUTER_HEALTH_OK" in model_health
    assert "v1/auth/browser-bootstrap" in dashboard_login
    assert "#bootstrap=" in dashboard_login
    assert "WantedBy=multi-user.target" in service_installer
    assert "Restart=on-failure" in service_installer
    assert "OnUnitActiveSec=15min" in service_installer
    assert "systemctl enable --now hermes.service" in service_installer
    assert 'case "$destination"' in backup
    assert "agent_restore_" in restore and "dropdb --if-exists" in restore


def test_readiness_gate_covers_every_configured_runtime_path() -> None:
    source = (ROOT / "scripts/readiness.ps1").read_text(encoding="utf-8")
    for required in (
        "verify.ps1",
        "restore-drill.ps1",
        "doctor.ps1",
        "agent-smoke.ps1",
        "openrouter.ps1",
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


def test_powershell_gpu_detection_captures_native_exit_before_pipeline() -> None:
    for relative_path in (
        "scripts/up.ps1",
        "scripts/doctor.ps1",
        "scripts/local-model.ps1",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        capture_index = source.index("$gpuCommandSucceeded = ($LASTEXITCODE -eq 0)")
        selection_index = source.index("$gpu = $gpuOutput | Select-Object -First 1")
        assert capture_index < selection_index
        assert "--format=csv,noheader 2>$null |" not in source


def test_openrouter_route_is_free_only_private_and_audited() -> None:
    settings = (ROOT / "services/control-api/app/settings.py").read_text(encoding="utf-8")
    inference = (ROOT / "services/control-api/app/inference.py").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    compose_model = yaml.safe_load(compose)
    migration = (ROOT / "config/postgres/init/008_free_model_routing.sql").read_text(
        encoding="utf-8"
    )

    assert "must end with :free" in settings
    assert 'model_id.endswith(":free")' in inference
    assert 'cost != 0' in inference
    assert '"data_collection": self._data_collection' in inference
    assert '"zdr": self._zdr' in inference
    assert "OPENROUTER_API_KEY" in compose
    assert "OPENROUTER_API_KEY" in compose_model["services"]["job-worker"]["environment"]
    for service in ("control-api", "worker", "dispatcher", "action-worker"):
        assert "OPENROUTER_API_KEY" not in compose_model["services"][service]["environment"]
    assert "CREATE TABLE IF NOT EXISTS inference_invocations" in migration


def test_hermes_uses_ordered_hosted_routes_then_lazy_local_fallback() -> None:
    config = yaml.safe_load(
        (ROOT / "services/hermes/config.example.yaml").read_text(encoding="utf-8")
    )
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert config["model"]["default"] == "free/default"
    assert config["model"]["base_url"] == "http://omniroute:20128/v1"
    assert config["fallback_providers"] == [
        {
            "provider": "openrouter",
            "model": "openrouter/free",
            "key_env": "OPENROUTER_API_KEY",
        },
        {
            "provider": "custom",
            "model": "qwen3:8b",
            "base_url": "http://ollama:11434/v1",
            "key_env": "HERMES_LOCAL_FALLBACK_KEY",
        }
    ]
    assert (
        compose["services"]["hermes"]["environment"]["HERMES_LOCAL_FALLBACK_KEY"]
        == "local-ollama-no-auth"
    )
    assert "OPENROUTER_API_KEY" in compose["services"]["hermes"]["environment"]
    config_init = compose["services"]["hermes-config"]
    assert config_init["user"] == "10000:10000"
    assert config_init["network_mode"] == "none"
    assert config_init["cap_drop"] == ["ALL"]
    assert config_init["entrypoint"] == ["/bin/sh", "-ec"]
    assert "chmod 0600" in " ".join(config_init["command"])
    assert set(compose["services"]["ollama"]["profiles"]) == {"agent", "local-model"}
    assert compose["services"]["ollama"]["environment"]["OLLAMA_KEEP_ALIVE"]
    assert (
        compose["services"]["hermes"]["depends_on"]["ollama"]["condition"]
        == "service_healthy"
    )


def test_dashboard_uses_one_time_bootstrap_and_http_only_session() -> None:
    auth = (ROOT / "services/control-api/app/auth.py").read_text(encoding="utf-8")
    main = (ROOT / "services/control-api/app/main.py").read_text(encoding="utf-8")
    javascript = (ROOT / "services/control-api/app/web/app.js").read_text(
        encoding="utf-8"
    )
    launcher = (ROOT / "scripts/open-dashboard.ps1").read_text(encoding="utf-8")

    assert "BOOTSTRAP_TTL_SECONDS = 90" in auth
    assert 'httponly=True' in main
    assert 'samesite="strict"' in main
    assert 'headers.get("x-hermes-csrf"' in auth
    assert 'window.history.replaceState' in javascript
    assert 'localStorage' not in javascript and 'sessionStorage' not in javascript
    assert 'v1/auth/browser-bootstrap' in launcher
    assert 'Set-Clipboard' in launcher  # explicit -CopyToken recovery remains available


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
