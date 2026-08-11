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
        if name != "test":
            assert "healthcheck" in service, name


def test_transactional_outbox_is_wired_into_runtime() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    schema = (ROOT / "config/postgres/init/001_schema.sql").read_text(encoding="utf-8")
    assert "dispatcher" in compose["services"]
    assert "task_outbox" in schema


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
