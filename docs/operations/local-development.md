# Local development

## Requirements

- Windows 10/11 with WSL2-backed Docker Desktop;
- Docker Engine and Compose plugin;
- PowerShell 5.1+;
- Git only for source control.

No project Python, Node.js, PostgreSQL, Redis, Playwright, or browser install is
required on Windows.

## First boot

```powershell
./scripts/init-env.ps1
docker compose config --quiet
./scripts/up.ps1
./scripts/health.ps1
./scripts/smoke.ps1
```

`init-env.ps1` does not overwrite existing `.env` unless `-Force` is explicit.
`-Force` rotates bootstrap values and can break existing state; use it only with
an intentional credential-rotation plan.

## Test loop

```powershell
./scripts/test.ps1
docker compose build control-api dispatcher worker
docker compose up -d
./scripts/smoke.ps1
```

Test image contains lint/test dependencies; runtime image does not. Repository
contract tests assert data stores have no host ports, published ports bind only
loopback, services have healthchecks, and examples contain no common key forms.

## Logs and status

```powershell
docker compose ps
./scripts/logs.ps1 -Service control-api
./scripts/health.ps1
```

Logs are structured JSON and rotated by Docker. Request bodies and auth headers
are deliberately absent. Use returned `x-correlation-id` to connect API logs to
task/audit records.

## Data reset

`docker compose down` keeps data. `docker compose down --volumes` permanently
deletes project volumes and is never part of normal scripts. Back up first and
verify exact Compose project name before any volume deletion.
