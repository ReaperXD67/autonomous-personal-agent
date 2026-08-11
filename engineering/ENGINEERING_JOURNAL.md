# Engineering journal

Date: 2026-08-11

## Step 1 — Inspect workspace and execution environment

### What I changed

No project files changed during inspection. Confirmed workspace was empty and
not a Git repository, then initialized `main` only after inspection.

### Why

Starting from observed state prevents overwriting user work and establishes a
factual baseline.

### Alternatives considered

Assume a blank repository from folder appearance; clone/create remote first.

### Why this approach was selected

Git status, hidden-file listing, remotes, tool versions, and account state are
more reliable than assumptions.

### Files affected

`.git/` was initialized after inspection; no source file existed.

### Validation

Ran file listing, `git status`, `git remote -v`, Docker Engine/Compose versions,
GitHub CLI auth status, and account repository listing.

### Result

Passed. Docker Engine 29.5.3 and Compose 5.1.4 were available. GitHub CLI was
authenticated as `ReaperXD67`. No existing `autonomous-personal-agent` remote
was found.

### Risks / follow-ups

Remote repository still needs creation only after local validation.

### Decision

Build foundation from zero in current workspace on branch `main`.

## Step 2 — Verify Hermes, OmniRoute, and MCP contracts

### What I changed

No runtime integration was enabled. Researched upstream source, releases,
Compose/Dockerfiles, configuration, health behavior, and local Docker MCP catalog.

### Why

Brief prohibits invented image names, environment variables, and interfaces.

### Alternatives considered

Use mutable `latest`; vendor upstream source; omit integrations entirely.

### Why this approach was selected

Official releases and published multi-arch images provide reproducible optional
boundaries without coupling core boot to external credentials.

### Files affected

Research later informed `docker-compose.yml`, `services/hermes/`,
`services/omniroute/`, `mcp/`, and `docs/mcp-catalog.md`.

### Validation

Inspected official GitHub repositories and release tags; inspected Docker
manifests; queried Docker MCP Toolkit `v0.42.2` catalog and server metadata.

### Result

Passed. Selected Hermes `v2026.8.3` manifest
`sha256:167883…`; OmniRoute `3.8.49` manifest `sha256:92c768…`. Confirmed Hermes
custom model config supports `${ENV_VAR}` expansion and OmniRoute exposes an
OpenAI-compatible `/v1` interface.

### Risks / follow-ups

Upstream behavior can change at new versions. Docker MCP catalog `latest` is
mutable; recorded catalog/image digests must be re-verified on update.

### Decision

Pin release and digest; keep profile optional; keep MCP disabled by default.

## Step 3 — Implement control and execution planes

### What I changed

Created authenticated FastAPI control service, outbox dispatcher, and worker.
Added task creation, status, approval/rejection, readiness, metrics, structured
logs, correlation IDs, transactional queue intent, atomic task claims,
deterministic echo capability, and redacted audit writes that share each state
transition transaction.

### Why

Foundation needs a real policy and lifecycle seam—not placeholder directories—so
future agents cannot bypass durable approval/audit flow.

### Alternatives considered

Documentation-only API; one process containing API/worker; Celery/RQ immediately.

### Why this approach was selected

Small explicit code keeps dependencies and magic low. Same image can run separate
API/dispatcher/worker processes. PostgreSQL outbox closes the database-to-Redis
commit gap; Redis protocol remains replaceable when retry/scheduling requirements
mature.

### Files affected

`services/control-api/app/`, `services/control-api/Dockerfile`,
`services/control-api/pyproject.toml`, `services/control-api/uv.lock`, tests.

### Validation

Dependency resolution completed inside official uv container. Static/runtime
validation is recorded in later steps after commands actually run.

### Result

Implementation complete; live validation pending at this journal point.

### Risks / follow-ups

Worker lease/recovery, dead-letter/retry policy, rate limits, per-user auth, and
derived minimum risk remain future work.

### Decision

Expose only `foundation.echo` until capability-specific policies exist.

## Step 4 — Implement durable data and Compose boundaries

### What I changed

Added PostgreSQL/pgvector schema for tasks, approvals, audit events, memory, and
transactional outbox delivery; password-protected Redis; health-gated Compose
services; internal networks; named volumes; non-root read-only app runtime;
loopback-only published ports; optional pinned Hermes/OmniRoute services.

### Why

Database lifecycle, persistence, backups, upgrades, and privileges must remain
independent from application deployments. Queue state must not become memory.

### Alternatives considered

SQLite for everything; Redis as task authority; expose databases for debugging;
single container.

### Why this approach was selected

PostgreSQL + pgvector matches durable memory trajectory. Redis serves transient
delivery. Separate internal networks prevent Hermes from directly reaching data.

### Files affected

`docker-compose.yml`, `config/postgres/init/001_schema.sql`, root configuration.

### Validation

Repository contract tests and live Compose validation are recorded later.

### Result

Implementation complete; live validation pending at this journal point.

### Risks / follow-ups

Bootstrap SQL is suitable for new databases; production needs a migration
runner. Data roles are not yet split into API/worker/read-only audit roles.

### Decision

Use PostgreSQL as authority, Redis as reconstructible transport/cache.

## Step 5 — Design MCP registry and permissions

### What I changed

Created curated registry, research/browser/coding/admin profiles, default-deny
policy, exact catalog/image digests, MCP security model, and evaluation record.

### Why

MCP servers are high-impact code and credentials. Intentional per-agent grants
are safer and more legible than global tool discovery.

### Alternatives considered

Enable Docker Dynamic MCP; install all popular servers; embed stdio packages in
Hermes; mount Docker socket.

### Why this approach was selected

Policy-first registry preserves provenance and future automation without granting
unreviewed runtime power.

### Files affected

`mcp/`, `docs/mcp-catalog.md`, `docs/security/mcp-security.md`.

### Validation

Queried catalog for Playwright, Fetch, Filesystem, GitHub, PostgreSQL,
Sequential Thinking, Brave/DuckDuckGo candidates. Recorded exact available
images and rejection reasons.

### Result

Passed as design/catalog validation. No MCP server was enabled or started.

### Risks / follow-ups

Need policy renderer/gateway, SSRF control, sandbox mounts, scoped credentials,
and one safe read test per enabled server.

### Decision

All MCP entries remain `enabled: false`.

## Step 6 — Add developer experience and public documentation

### What I changed

Added random secret bootstrap, lifecycle/health/smoke/test scripts, Make targets,
CI workflow, dependency updates, README, architecture, operations, security,
ADRs, roadmap, and integration guidance.

### Why

An operable, truthful project is more valuable than undocumented infrastructure.
Windows users should not memorize Compose invocations.

### Alternatives considered

Make-only workflow; README-only docs; full monitoring/CI platform now.

### Why this approach was selected

PowerShell is native to target workstation; Make remains optional. Focused docs
and minimal CI support current scope without premature systems.

### Files affected

`README.md`, `scripts/`, `docs/`, `.github/`, `Makefile`, project metadata.

### Validation

Pending static and live validation below.

### Result

Implementation complete; validation pending.

### Risks / follow-ups

PowerShell wrappers need continual parity with Compose. CI security scans are
documented future gates, not yet enforced.

### Decision

Keep commands thin and Compose authoritative.

## Step 7 — Validate core behavior and failure recovery

### What I changed

Closed the PostgreSQL-to-Redis delivery gap with a transactional outbox and
separate dispatcher. Added a repository contract for this runtime boundary.

### Why

Publishing directly after committing a task can lose the ready signal if Redis
or the API process fails in between. Durable intent must exist before transient
delivery.

### Alternatives considered

Direct publish with retries in the API; make Redis authoritative; periodic scan
of all queued tasks without delivery records.

### Why this approach was selected

An outbox gives an inspectable retry record and atomic task/audit/delivery intent
without adding a queue framework. Worker state transitions make at-least-once
delivery safe.

### Files affected

`config/postgres/init/`, `services/control-api/app/store.py`,
`services/control-api/app/dispatcher.py`, `docker-compose.yml`, scripts, tests,
CI, and architecture documentation.

### Validation

- `docker compose config --quiet` passed.
- Runtime/test images built from clean updated context.
- Ruff passed and Pytest reported `10 passed`.
- Core health reported PostgreSQL, Redis, control API, dispatcher, and worker healthy.
- Smoke tasks completed: safe `a6c81704-db61-46e3-94aa-69eb87fb5620` and
  approved high-risk `b7616910-2449-4356-b2b0-bb10108f903c`.
- Stopped Redis, submitted task `12ed1092-7431-445e-a6a2-d489b85a60d4`,
  observed one unpublished PostgreSQL outbox row, restarted Redis, and observed
  the same task succeed with its row marked published.
- Replayed that request with the same idempotency key; API returned the original
  task and PostgreSQL retained one task plus one outbox row.
- Unauthenticated system-status request returned HTTP 401.

### Result

Passed. Observed database totals after testing: 5 succeeded tasks, 17 audit
events, 2 approval records, and 3/3 published outbox rows with zero pending.
Migrations `001_foundation` and `002_transactional_outbox`, pgcrypto `1.3`, and
vector `0.8.1` were present.

### Risks / follow-ups

Dispatcher delivery is intentionally at least once. Production still needs
worker leases, bounded retry/dead-letter policy, and an automated migration
runner.

### Decision

Keep PostgreSQL authoritative and treat duplicate Redis signals as safe transport
events.

## Step 8 — Validate persistence, backup, and optional upstream images

### What I changed

No further runtime behavior changed. Corrected the Hermes health command to its
absolute upstream path and removed the unauthenticated Hermes dashboard binding.

### Why

Optional integrations must be honestly runnable without bypassing upstream
security guards. Persistent state must survive ordinary lifecycle commands.

### Alternatives considered

Disable the Hermes dashboard security check; claim inference readiness without a
provider key; recreate volumes during validation.

### Why this approach was selected

Image health is separable from model onboarding. Preserving upstream auth rules
and user data is safer than making a demo look complete.

### Files affected

`docker-compose.yml`, Hermes/OmniRoute integration docs, and backup guidance.

### Validation

- Optional OmniRoute `3.8.49` and Hermes `v2026.8.3` images reached healthy state.
- A full Compose down/up preserved 5 tasks, 17 audits, 2 approvals, and 3 outbox
  rows in the same named PostgreSQL and Redis volumes.
- PostgreSQL backup produced `agent-20260811T165619Z.dump` (16,280 bytes) with
  SHA-256 `6b390b21002e8d2def2590ad842523b87fe1400c5c0a5673462aa57bf2a68353`.

### Result

Passed for image health, core persistence, and backup creation. Model inference
was not tested because OmniRoute provider onboarding and a scoped API key are
intentionally user-owned steps.

### Risks / follow-ups

Backup restore still needs a disposable-database drill. Hermes dashboard needs an
upstream-supported auth provider before publication.

### Decision

Keep optional integrations labeled prepared, not fully configured.

## Final Implementation Summary

Implemented a reproducible, secure foundation: authenticated task API,
approval-gated lifecycle, transactional audit/outbox records, at-least-once queue
delivery, allowlisted worker, PostgreSQL/pgvector memory schema, Redis transport,
container hardening, health/metrics/logging, Windows operations, backups, CI,
ADRs, threat model, roadmap, and a disabled-by-default curated MCP policy.

Deliberately not implemented: real email/job/browser/coding actions, public UI,
production authentication, model-provider credentials, unrestricted MCP, or
self-modification. Those features require the phase gates in `docs/roadmap.md`.

Key decisions: container-first local development; PostgreSQL as authority; Redis
as reconstructible transport; high-impact approval before outbox creation;
per-agent default-deny tools; upstream Hermes/OmniRoute behind optional pinned
profiles; no Docker socket or public database ports.

Validation observed: Compose model and builds pass, Ruff passes, 10 tests pass,
core and optional containers are healthy, safe/approved/recovery flows pass,
idempotency holds, unauthorized access is rejected, data survives restart, and a
checksummed PostgreSQL backup exists. Remaining production gaps are recorded
without claiming completion.
