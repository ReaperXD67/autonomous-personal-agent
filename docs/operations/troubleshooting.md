# Troubleshooting

## Compose reports a missing variable

Run `./scripts/init-env.ps1`. Do not paste secrets into `docker-compose.yml`.

## Control API is unhealthy

```powershell
docker compose ps
docker compose logs --tail=200 control-api postgres redis
Invoke-RestMethod http://127.0.0.1:8080/health/ready
```

Readiness reports PostgreSQL and Redis separately. Common causes: stale `.env`
after volume initialization, port collision, or insufficient Docker resources.

## PostgreSQL password changed but volume already exists

PostgreSQL bootstrap variables apply only during first initialization. Restore
the old password, rotate it inside PostgreSQL deliberately, or restore into a
new verified volume. Do not delete the volume to make the error disappear.

## Worker queue does not drain

Check worker health/logs, Redis health, and task status. Only `queued` tasks run.
High-risk tasks require `/decision`. A stale queue entry is intentionally
discarded when PostgreSQL state is not `queued`.

## OmniRoute healthy but Hermes cannot infer

Container health proves process readiness, not provider onboarding. Create a
scoped inference key in OmniRoute, update ignored `.env`, configure Hermes
custom provider/base URL, then restart Hermes. Never commit rendered config.

## OpenRouter is enabled but drafts use local Qwen

Run `./scripts/openrouter.ps1` to inspect non-secret key tier and the current
verified free order, then `./scripts/openrouter.ps1 -Smoke`. Common intentional
fallback reasons are the local daily cap, the account-wide OpenRouter free
quota, no provider satisfying both no-training and ZDR, upstream saturation, or
invalid model JSON. The dashboard **Settings** card and the latest
`inference_invocations.error_code` show the route outcome without prompt text.

Do not fix availability by changing an ID to a paid model, allowing provider
data collection without reviewing résumé privacy, disabling cost checks, or
supplying a management key. Free inventory changes; catalog refresh drops
missing or non-zero-cost entries. Keep local Ollama running for continuity.

## Docker Desktop file sharing

Project should reside in a Docker-accessible Windows directory. Named volumes
avoid most bind-mount performance issues; only database bootstrap SQL is bound
read-only from source.
