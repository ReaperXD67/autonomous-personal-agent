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

## Step 9 — Publish and govern the public repository

### What I changed

Created `ReaperXD67/autonomous-personal-agent` as a public GitHub repository and
pushed focused core, documentation, CI, and governance commits. Added repository
topics, CODEOWNERS, a security-aware pull-request template, vulnerability alerts,
automated security fixes, private vulnerability reporting, and `main` protection.

### Why

The project is intended as a public portfolio and reusable engineering case
study. Provenance, visible CI, maintainership, and safe contribution defaults are
part of the system rather than afterthoughts.

### Alternatives considered

One squashed initial commit; unprotected direct-push workflow; private repository;
publishing before local validation.

### Why this approach was selected

Focused commits preserve important design milestones. A public, protected default
branch makes the implementation inspectable while keeping future changes behind
the same validation contract.

### Files affected

`.github/CODEOWNERS`, `.github/pull_request_template.md`, README badges, and GitHub
repository settings. Local secret and backup files remained ignored.

### Validation

- Local and remote `main` resolved to the same pushed commit.
- GitHub Actions CI run `31516417578` passed `validate` in 39 seconds.
- Branch protection requires strict `validate`, linear history, and resolved
  conversations; force pushes and deletion are disabled.
- Remote visibility is public and default branch is `main`.

### Result

Passed. Repository is available at
`https://github.com/ReaperXD67/autonomous-personal-agent`.

### Risks / follow-ups

Dependabot immediately opened PRs #1 and #2. They should be reviewed and merged
only after their CI and compatibility evidence are satisfactory.

### Decision

Publish the validated foundation now and evolve autonomy through protected,
reviewable increments.

## Step 10 — Upgrade dependencies and resolve advisory exposure

### What I changed

Updated all direct Python runtime/development dependencies to their tested current
versions, including FastAPI `0.141.1`, redis-py `8.1.0`, and pytest `9.1.1`.
Hardened the worker against redis-py 8 empty-poll timeouts, normalized Windows
Docker source file modes before Ruff, split production/development Dependabot
groups, and added a dependency risk register plus contract test.

### Why

GitHub dependency analysis surfaced seven advisories immediately after initial
publication. A version bump alone was insufficient: the Redis major update
changed blocking-read behavior, and the first regenerated lock retained an older
Starlette even though the patched major line was compatible.

### Alternatives considered

Merge the green bot PR without local runtime testing; dismiss all alerts without
evidence; force an unsupported Starlette version; retain older direct packages.

### Why this approach was selected

Local idle/runtime and outage testing caught a failure that unit/CI tests missed.
A second security update to Starlette `1.3.1` was accepted only after container,
API, and CI compatibility evidence; the regression contract remains defense in
depth.

### Files affected

Python dependency manifest/lock, worker, Dockerfile test stage, worker/repository
tests, Dependabot configuration, security docs, README, and security policy.

### Validation

- Updated images built successfully.
- Ruff passed and Pytest reported `12 passed` on Windows Docker Desktop.
- Worker remained healthy across multiple empty Redis blocking polls.
- Updated-runtime smoke tasks succeeded: `037c335d-1b07-46ef-8164-7e9cc02c39c2`
  and approved `59200ac2-9fcc-43d6-9564-94a340ff5532`.
- Redis-outage task `1718747d-ce19-4e02-aae6-d941bdee4d61` remained in the
  durable outbox while Redis was stopped and succeeded after restart.

### Result

Passed. The pytest advisory is removed by the direct dependency update. Starlette
`1.3.1` then removed all six transitive advisories; live smoke tasks
`768c172c-bf8e-48d9-afbe-06f2a77c2fa3` and
`fdee52c2-0b6e-49d1-aa8c-7fa9edeff5c3` passed on the patched runtime. GitHub's
configured dependency-graph update then marked all seven alerts `fixed`.

### Risks / follow-ups

Keep the defense-in-depth contract aligned with application features and treat
future network-facing dependency advisories as release blockers.

### Decision

Land dependency/security updates only with runtime compatibility evidence; carry
no active advisory exception when a supported patched version passes.

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

Validation observed: Compose model and builds pass, Ruff passes, 12 tests pass,
core and optional containers are healthy, safe/approved/recovery flows pass,
idempotency holds, unauthorized access is rejected, data survives restart, and a
checksummed PostgreSQL backup exists. Remaining production gaps are recorded
without claiming completion.

## Step 11 — Verify progress and add recoverable, free inference foundations

Date: 2026-08-12

### Objective

Verify the existing repository honestly, research current free/self-hosted agent
options, close the most important reliability gap, prepare a realistic free
inference path for the observed hardware, and separate automated work from
user-owned onboarding.

### Investigation

- Inspected Git status/history, repository structure, Compose, application code,
  schema, scripts, tests, roadmap, security records, and existing journal.
- Used the current official Codex manual and primary upstream sources for Hermes
  Agent, OmniRoute, Prime Agent, NVIDIA Nemotron 3, Ollama, Qwen3, and Docker GPU
  support.
- Measured local hardware: RTX 4070 Laptop GPU with 8188 MiB VRAM.
- Verified the pre-change stack: seven containers healthy and 14 tests passed.

### Decision

Keep Hermes as the sole cognitive orchestrator and OmniRoute as the replaceable
model router. Treat Prime Agent as a future disposable coding worker because its
own trust model is not a sandbox. Route Nemotron remotely on this hardware. Add
Qwen3 8B Q4 through optional internal Ollama only as a constrained local
fallback. Implement durable worker leases and a startup migration gate before
adding more autonomous capabilities.

### Why

The official Nemotron 3 Super BF16 card requires 8× H100-80GB and the current
Nano Omni card still lists 21 GB for NVFP4, so local Nemotron would be dishonest
on 8 GB VRAM. The existing worker could leave a task permanently `running` if it
died after claiming.

### Alternatives considered

- CPU-offload Nemotron locally.
- Run Hermes and Prime Agent as peer orchestrators with host permissions.
- Depend only on volatile hosted free tiers.
- Add a full queue framework before requirements stabilize.
- Skip the migration runner and apply schema manually.

### Trade-offs

The local model is private and token-free but weaker and limited to an 8K
configured context. Hosted free routes provide better models but can throttle or
disappear. Lease recovery prevents permanent claims but long-running tools still
need heartbeat renewal and delayed backoff. Production still needs a distinct
migration-owner role and rollback procedure.

### Implementation

- Added a one-shot migration service that gates runtime startup and applied
  migration `003_worker_leases` to existing state.
- Added lease expiry, three-attempt budgets, dispatcher reconciliation, audit
  events, and reusable live recovery smoke tests.
- Added digest-pinned Ollama `0.32.5`, GPU reservation, internal endpoint,
  local-only mode, memory bounds, and setup script.
- Added doctor and agent inference smoke scripts.
- Added root `AGENTS.md` so future coding agents must preserve policy boundaries,
  update engineering records, and run the verified handoff commands.
- Added the required System Evolution and Experiment Log documents, ADR-0006,
  current research, manual setup, and synchronized architecture/roadmap/README.
- Made health checks wait for bounded startup instead of failing on transient
  Docker `starting` state.

### Files changed

Root/Compose: `docker-compose.yml`, `.env.example`, `Makefile`, `README.md`.

Runtime/schema: `services/control-api/app/`, service tests,
`config/postgres/init/001_schema.sql`, and `003_worker_leases.sql`.

Operations: health/up/verify, doctor, agent/local-model, and recovery smoke
PowerShell scripts.

Documentation: architecture, roadmap, ADR-0006, free-stack research, manual and
local operations, System Evolution, Experiment Log, and this journal.

### Validation

- `docker compose config --quiet` passed.
- Runtime/test images rebuilt successfully; Ruff passed; final Pytest: `16 passed`.
- Full `scripts/verify.ps1` passed after the bounded health-wait fix.
- Safe task `f36aca16-40c8-41eb-b25a-92d8e7526754` passed.
- Approval task `5d07cb30-fac3-4d63-bb97-8b9ec7d16597` passed.
- Automated lease retry and exhaustion passed; task IDs are in Experiment Log.
- `scripts/doctor.ps1 -Agent` passed every required check.
- OmniRoute listed 79 routes; `scripts/agent-smoke.ps1` passed through
  `free/default`.
- Hermes returned exactly `HERMES_OK` through the custom endpoint.

### Results

Core infrastructure, real free routed inference, Hermes inference, versioned
migration startup, and worker-crash recovery work. Local Ollama is prepared but
not claimed operational because the download did not finish.

### Problems encountered

- Initial verification checked health too early after migration startup.
- OmniRoute `auto` had no eligible candidate; a direct free route returned 429.
- The first free/default response streamed SSE because `stream: false` was absent.
- Ollama image transfer was too slow for a bounded validation window.

### Resolution

Health now polls within a fixed timeout. Inference smoke uses `free/default`,
requests non-streaming output, and surfaces bounded error details. The local
download was stopped safely and remains resumable through one documented command.

### Security implications

Ollama has no published port, disables cloud features, and receives no database
network. No Docker socket or host workspace is mounted into Hermes/Ollama.
Recovery actions are audited. Prime Agent remains disabled until isolated. The
migration container's database ownership must be split before production.

### Performance implications

Lease reconciliation adds one indexed query per dispatcher loop. Local Qwen is
configured for one model and one parallel request to bound 8 GB VRAM usage. The
8K local context is deliberately constrained.

### Future improvements

Add heartbeat renewal, cancellation, delayed retry/dead-letter inspection,
role-separated migrations, cost/usage audit metadata, a Hermes control-plane
adapter, and an isolated worktree coding-worker evaluation.

## Milestone summary — Reliability and hybrid free inference

Implemented: migrations, lease recovery, repeatable diagnostics, working free
routed/Hermes inference, and optional local inference architecture.

Not implemented: completed local model download, Telegram/email/GitHub accounts,
production identity/TLS, unrestricted MCP, or autonomous coding worker.

Next milestone: Hermes-to-control-plane task adapter plus safe read-only research
tools, after periodic lease heartbeats and per-capability derived risk policies.

## Step 12 — Complete durable execution lifecycle and prove test readiness

Date: 2026-08-15

### Objective

Close the remaining foundation reliability gates that can be completed locally,
prove that authoritative PostgreSQL state is recoverable, re-evaluate the local
model download, and leave an exact list of work that still requires user-owned
identity, infrastructure, or external credentials.

### Investigation

- Confirmed a clean `main` worktree at merge commit `9ae658d` and reviewed the
  directive, roadmap, architecture, security, operations, and latest evidence.
- Compared Phase 1 gaps to the current worker/store/schema behavior.
- Found that crash recovery existed but long work had no heartbeat, claims had
  no unique owner token, retry was immediate, cancellation was absent, exhausted
  tasks appeared as ordinary failures, and restores were still a prose procedure.
- Rechecked the optional stack and found that the previously incomplete Ollama
  download had finished: `qwen3:8b`, 5.2 GB, was present.

### Decision

Implement one bounded reliability milestone before adding real external tools:
owned leases, periodic heartbeat, cooperative cancellation, bounded delayed
retry, explicit dead letters, minimum capability-derived risk, and a disposable
restore drill. Keep dead-letter replay manual and do not introduce a queue
framework while only two deterministic foundation handlers exist.

### Implementation

- Added migration `004_execution_lifecycle` with lease ownership, worker
  identity, retry availability, cancellation metadata, and dead-letter state.
- Added capability minimum-risk policy; callers may escalate but cannot lower
  the allowlisted risk.
- Added a heartbeat monitor and bounded `foundation.wait` handler to exercise
  real long-task behavior. Completion/failure now requires the unique lease ID.
- Added immediate queued cancellation, cooperative running cancellation, audit
  events, delayed exponential recovery, outbox backoff, and authenticated
  `/v1/tasks/dead-letters` inspection.
- Added repeatable lifecycle smoke coverage and extended settings/contracts to
  validate safe heartbeat and retry bounds.
- Added SHA-256 sidecars and `restore-drill.ps1`, which accepts only repository
  backup paths, restores only to a checked random database, validates SQL and
  application invariants, and removes the disposable target.
- Fixed the local-model GPU check for PowerShell environments where a successful
  native pipeline leaves `$LASTEXITCODE` unset. The smoke now requires exact
  `LOCAL_MODEL_OK` and reported GPU placement.
- Added ADR-0007 and synchronized README, roadmap, architecture, security,
  operations, system evolution, experiments, and this journal.

### Problems encountered and resolution

- The first live upgrade failed because the edited bootstrap schema attempted to
  create an index on `task_outbox.available_at` before migration 004 added that
  column to an existing database. The bootstrap index was restored to its
  backward-compatible definition; migration 004 now replaces it after adding
  the column. The next migration run succeeded without deleting data.
- The first unit pass found one import-order lint error. It was corrected and the
  test image rebuilt so Docker did not reuse the previous source snapshot.
- `local-model.ps1` falsely rejected a visible GPU because `$null -ne 0` evaluated
  true when `$LASTEXITCODE` was unset after a successful pipeline. Readiness now
  depends on the actual non-empty GPU query result.

### Validation

- `docker compose config --quiet` and runtime/test image builds passed.
- Ruff passed; Pytest passed 23 tests in the final full run.
- `scripts/verify.ps1` passed API health, safe execution, approval execution,
  delayed retry, dead-letter exhaustion, queued cancellation, running
  cancellation, and dead-letter inspection.
- `scripts/restore-drill.ps1` verified the checksum, 4 migrations, 32 tasks, 105
  audits, vector extension, zero orphan audit links, application readiness, and
  safe removal of its disposable database.
- `scripts/doctor.ps1 -Agent` passed every required check.
- OmniRoute listed 79 routes and `free/default` inference passed.
- Qwen3 8B returned exactly `LOCAL_MODEL_OK`; Ollama reported GPU placement.
- Hermes returned exactly `HERMES_READY_OK` through the configured route.
- No runtime error/traceback was present in control API, dispatcher, or worker
  logs during the tested lifecycle.

### Security and performance implications

Unique lease IDs prevent stale-worker commits after reassignment. Cancellation
stays in the authenticated policy/audit path instead of granting container
control. Capability risk has a trusted minimum. Retry delay is bounded from 5 to
300 seconds by default, and heartbeats run every 10 seconds against a 120-second
lease. Heartbeats update task state without one audit row per interval.

### Not implemented

Per-user OIDC/RBAC, rate limits, step-up identity, OpenTelemetry/alerts,
encrypted off-host scheduled backups, public TLS/WireGuard deployment, enforced
SBOM/vulnerability/signature CI, Hermes task adapter, model cost metadata,
memory APIs, scheduler, MCP/browser/coding workers, Telegram, email, and web UI.
These remain phase-gated rather than being represented by fake integrations.

### Next milestone

Add enforced supply-chain CI and basic telemetry that require no external
account, then implement the Hermes-to-control-plane adapter and budget-aware
model audit metadata before enabling any read-only external tool.
