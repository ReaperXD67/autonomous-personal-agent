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

## Step 13 — Enforce supply-chain evidence in the required CI check

Date: 2026-08-15

### Objective

Close the automatically achievable portion of the Phase 1 supply-chain gate
without requiring a registry, paid service, or broader GitHub token permission.

### Research and decision

Verified current releases from the official repositories: Trivy action
`v0.36.0`, Trivy `v0.74.0`, Anchore SBOM action `v0.24.0`, GitHub Dependency
Review `v5.0.0`, and Syft `v1.51.0`. Selected full action commit pins rather than
mutable tags. Extended the existing branch-required `validate` job so security
failures cannot be bypassed by merging while an optional workflow fails.

### Implementation

- Added pull-request dependency review with a high-severity failure threshold.
- Added repository vulnerability, secret, and misconfiguration scanning.
- Added high/critical scanning of the built control-plane runtime image.
- Added an SPDX JSON runtime-image SBOM artifact with 14-day retention.
- Added a repository contract that rejects every non-immutable action reference
  and requires the expected scanner/SBOM configuration.
- Allowed only `.github/workflows/ci.yml` through `.dockerignore` so the isolated
  test image can enforce that contract; all other `.github` content stays out.
- Added ADR-0008 and synchronized security, roadmap, README, experiment, and
  evolution records.

### Validation

- Official Trivy `v0.74.0` repository scan: zero high/critical vulnerabilities,
  no reported secret findings, and zero Dockerfile misconfigurations.
- Runtime image scan: zero high/critical Debian or Python package findings.
- Official Syft `v1.51.0` generated SPDX JSON successfully.
- Containerized Ruff and Pytest passed 24 tests in 0.37 seconds.
- GitHub Actions run `31892979230` passed the clean-checkout required job in 55
  seconds and uploaded a 380,063-byte `control-api-sbom` artifact.
- Git diff whitespace validation passed.

### Limitation

Image signing and signature verification remain blocked on a trusted registry
and OIDC/release identity. The project does not claim an unsigned local Docker
tag is a signed release. SBOM artifacts expire after 14 days unless a future
release workflow archives them.

## Step 14 — Add one-command complete workstation readiness

Date: 2026-08-15

### Objective

Replace scattered readiness claims with one repeatable no-skip command that
proves the configured control plane, recovery path, environment, routed model,
local GPU model, and Hermes route and leaves a sanitized machine-readable result.

### Implementation

- Added `scripts/readiness.ps1` and a Make target covering lifecycle
  verification, disposable restore, agent doctor, OmniRoute, local Qwen, and
  Hermes.
- Added optional skip switches for focused diagnosis while documenting that a
  skipped path does not prove complete readiness.
- Added ignored `runtime/readiness/latest.json` output containing only check
  names, statuses, durations, a timestamp, the tested Git commit, and concise
  failure text.
- Changed local-model bootstrap to reuse a matching cached model, download only
  when missing, and expose `-ForcePull` for an intentional refresh.
- Added repository contracts and synchronized README and operations guidance.

### Problem encountered and resolution

The first complete gate found that `ollama pull qwen3:8b` could fail during a
registry/network interruption even though the same 5.2 GB model was fully
installed and runnable. The bootstrap now checks the installed model list first.
The real exact-response and GPU-placement smoke remains mandatory, so reuse does
not weaken inference verification.

### Validation

- The direct cached local-model smoke returned exactly `LOCAL_MODEL_OK` and
  Ollama reported GPU placement.
- The complete no-skip gate then passed all six checks: lifecycle 48.31s,
  restore 5.60s, doctor 2.34s, OmniRoute 0.33s, local Qwen 2.23s, and Hermes
  17.19s.
- The lifecycle verification inside that gate included containerized lint, 26
  passing tests, and real safe, approval, retry, cancellation, and dead-letter
  paths. A final standalone verification pass also succeeded.

### Limitations

This proves the configured local test stack, not production deployment or
external side-effect adapters. Identity, public infrastructure, encrypted
off-host backup, release signing, messaging credentials, and provider terms
remain user-owned gates. The planned Hermes control-plane adapter, telemetry,
memory, scheduler, MCP/browser/coding workers, and messaging/UI features remain
engineering work and are not represented as complete.

## Step 15 — Add the private command center and durable career missions

Date: 2026-08-15

### Objective

Make the first real personal workflow testable from a website: continuously hunt
only fresh jobs/internships, rank them against a user profile, prepare truthful
local application material, let the user switch missions without code changes,
and preserve the existing policy/audit boundary.

### Research and decision

Verified official public interfaces for Arbeitnow, Ashby, and Greenhouse.
Remotive was not enabled because its official public-API documentation says
listings are delayed 24 hours, conflicting with a fresh-only mission. Selected a
same-origin dashboard, a dedicated egress worker, durable PostgreSQL scheduling,
and local Qwen structured drafts. ADR-0009 records why generic application form
submission remains absent and each future side effect must be approval-gated.

### Implementation

- Added a responsive command-center website for missions, fresh opportunities,
  approvals, tasks, and audit timelines. The token is held in tab session storage
  and the API serves external static assets under a self-only CSP.
- Added migration 005 for career profiles, source-attributed opportunities, and
  structured application drafts with indexes, bounds, and cascades.
- Added authenticated profile/opportunity/task/audit APIs without exposing raw
  résumé text in profile responses.
- Added allowlisted Arbeitnow, Ashby, and Greenhouse readers with HTTPS/redirect,
  slug, size, timeout, and freshness controls. Deterministic scoring records its
  evidence.
- Added `career.search` and `career.application_draft` policy capabilities, a
  separate queue, dispatcher routing, and a dedicated hardened career worker.
  Scheduled scans create durable tasks through the same policy/outbox path.
- Added local Ollama structured drafting with prompt-injection instructions,
  résumé-only evidence, output bounds, and no raw résumé in task/audit/source
  payloads.
- Added `open-dashboard.ps1` for the first user run and a disposable
  `career-smoke.ps1` for real live-source and local-model verification.
- Added tests, health/build coverage, ADR/research/operations documentation, and
  synchronized roadmap, architecture, security, README, evolution, and manual
  setup claims.

### Problems encountered and resolution

- Inline dashboard assets conflicted with a strict content-security policy. CSS
  and JavaScript were packaged as same-origin assets so no unsafe CSP exception
  was required.
- The first lint pass found import ordering, line length, typing, and security
  warnings across the new source adapter and tests. Each was corrected before
  live validation.
- A connection retry could use stale dashboard state after a non-auth API error.
  The refresh function now returns an explicit connection result.
- Mission configuration originally allowed every source to be disabled. Schema
  validation now requires at least one reviewed source.

### Validation

- Compose configuration and all runtime/test image builds passed.
- Ruff passed; Pytest passed 33 tests in 1.10 seconds.
- Dashboard HTML/CSS/JavaScript returned HTTP 200 with the expected strict CSP.
- The career smoke fetched 100 live listings, persisted 5 fresh matches, and
  generated a structured application draft with local `qwen3:8b`; its synthetic
  profile was removed using an exact guarded cleanup predicate.
- The full verification gate passed all six service health checks, safe and
  approved tasks, lease retry/exhaustion, queued/running cancellation, and
  dead-letter inspection.
- `doctor.ps1 -Agent` passed, OmniRoute listed 79 models, and `free/default`
  inference passed. Bounded runtime logs contained no traceback, ERROR, CRITICAL,
  or unhandled-request entry. Git whitespace validation passed.

### Security and operational implications

The career worker is the only core execution service with outbound egress and
has no published port, Docker socket, or host mount. Resume content remains
durable private data and must be covered by VPS backup/secrets policy. The web UI
is safe only as a private administrator interface while one service-wide bearer
token exists. Laptop sleep stops schedules; an always-on VPS requires private
ingress, patching, encrypted backups, and enough compute for the selected local
model.

### Not implemented

No application is submitted automatically. There is no generic browser worker,
job-site login/CAPTCHA handling, OIDC/RBAC, public TLS/rate-limited ingress,
email/Telegram adapter, or broad MCP/coding worker. VPS purchase, domain/DNS,
private network, personal résumé content, target-company board selection, and
final submission consent remain user-owned setup.

## Step 16 — Add exact approval-bound application and email execution

Date: 2026-08-25

### Objective

Automate the mechanical work between a fresh job match and an external action
without granting the agent blanket authority to act under the user's identity.
Add a free, reproducible test path and keep every runtime inside the existing
policy, audit, and PostgreSQL authority boundary.

### Research and decision

Reviewed official Greenhouse, Ashby, and Lever job/application interfaces,
Playwright container guidance, Gmail/Microsoft sending boundaries, Mailpit, and
bot-challenge behavior. Public discovery APIs do not confer employer-controlled
direct-submit credentials. Selected a hosted-form adapter with exact approval,
a separate Playwright/SMTP runtime, and durable pre-side-effect receipts.
ADR-0010 records the boundary. CAPTCHA/login bypass, generic personal-browser
automation, and model-inferred legal/consent answers were rejected.

### Implementation

- Added migration 006 for application identity/auto-prepare settings, Lever,
  form preflights, exact external-action envelopes, approval hashes, and unique
  side-effect receipts.
- Added `career.application_preflight`, `career.application_submit`, and
  `communications.email_send` capabilities and a separate action queue/worker.
- Added a release/digest-pinned Playwright image, reviewed ATS URL/request
  policy, disposable contexts, strict field resolution, escaped PDF résumé
  rendering, form-signature revalidation, and one final-click boundary.
- Added deployment-fixed SMTP with validated single recipients, TLS enforcement
  for external transports, fixed sender binding, Message-ID receipts, and no
  retry after the external boundary.
- Added automatic drafting/preflight for capped high-scoring fresh matches and
  Lever discovery. Unknown required answers return to the dashboard.
- Extended the dashboard with identity, auto-prepare, preflight, explicit-answer,
  email-plan, and exact-action review flows. The bearer token moved from tab
  session storage to page memory; DOM construction uses text nodes.
- Added pinned Mailpit and a fake ATS test profile plus
  `side-effect-smoke.ps1`, which uses disposable synthetic records and guarded
  exact cleanup.
- Added action-image Dependabot, Trivy, and SPDX SBOM CI coverage, security
  review, ADR, research, operations, architecture, roadmap, and evolution docs.

### Problems encountered and resolution

- The first Playwright input-submit fallback used a brittle locator. The final
  executor uses one accessible-role match for the exact approved label and
  refuses zero or multiple controls.
- The browser verifier reported a missing favicon. The API now returns an empty
  204 favicon response; the final page reload had zero console errors/warnings.
- Trivy read two fixed high findings from stale third-party SBOM PURLs inherited
  from the Microsoft base even though neither distribution exists in the merged
  runtime. Runtime import/filesystem evidence was recorded; the suppressions are
  exact-PURL only, expire 2026-09-25, and live in the dependency risk register.
  All unsuppressed runtime findings are zero. The uv build cache was also removed
  from the final layer.

### Validation

- `docker compose config --quiet`, JavaScript syntax, PowerShell parse, and
  whitespace checks passed.
- Ruff and Pytest passed 40 tests in the final lifecycle build.
- `scripts/verify.ps1` passed health, safe/approval paths, lease retry and
  exhaustion, queued/running cancellation, and dead-letter inspection.
- The final disposable side-effect smoke generated a local Qwen draft, inspected
  six form fields, executed one fake application, delivered one email to
  Mailpit, and refused the second application because the succeeded receipt
  already existed. No external application/email left Docker and zero synthetic
  career/action records remained.
- Playwright rendered the locked dashboard at loopback with zero console errors
  or warnings.
- Trivy 0.74.0 reported zero unsuppressed high/critical findings across Ubuntu,
  the application Python environment, and the Playwright Node driver.

### Remaining boundary

Real applications and real email have not been universally verified. Every
exact send/submit remains approval-gated. User-owned SMTP/OAuth credentials,
employer-specific questions/terms, logins, CAPTCHA, unsupported multi-step
forms, OIDC/step-up approval, private VPS ingress, egress firewalling,
off-host encrypted backups, and ambiguous-action reconciliation remain manual
or future work. Hermes still does not bypass the control plane, and the generic
Playwright MCP candidate remains disabled.

## Step 17 — Add governed creator outreach and bounded adaptation

Date: 2026-08-29

### Objective

Turn KarixMC promotion into a measurable operator workflow: discover relevant
YouTube creators without harvesting email addresses, record reviewed contact
provenance, prepare the requested introduction/question/paid-option sequence,
show funnel results, and adapt only within evidence-backed fixed variants.

### Research and decision

Reviewed the official YouTube Data API discovery/statistics surfaces and EU
Commission direct-marketing/objection guidance. Selected official API discovery
in the existing egress worker, manual public-business-email qualification,
exact approval for every email, durable suppression, and a fixed two-variant
bandit with an explicit evidence threshold. ADR-0011 records why inbound replies,
public posting, contact scraping, self-modifying prompts/code, and automatic
spending remain outside this milestone.

### Implementation

- Added migration 007 for campaigns, public creator prospects, outreach stages,
  outcomes, attribution, suppression, indexes, and update triggers.
- Added official YouTube discovery with a fixed host/path, strict SafeSearch,
  response bounds, channel statistics, deterministic scoring, a 30-task daily
  guard, and a worker-only optional API key.
- Added authenticated campaign, prospect, result, outcome, scan, and exact email
  planning APIs backed by PostgreSQL and the existing policy/outbox/audit path.
- Added truthful fixed introduction variants, a manual question-answer stage,
  one paid option only after an explicit unpaid-only decline, contact/privacy
  footers, UTM tracking, and per-stage duplicate guards.
- Added pre-SMTP revalidation of the approved address, authorization,
  suppression, and reply state so later objections invalidate pending actions.
- Added a responsive Creator campaigns dashboard with labeled forms, visible
  funnel values, evidence-bearing suggestions, contact provenance, outcomes,
  and results. Adaptation changes only future initial-draft selection after both
  variants have ten deliveries and one leads by at least five percentage points
  and 1.5x; exploitation remains capped at 80 percent.
- Initialized one inactive `KarixMC creator pilot` in the local authoritative
  database. It cannot scan or send until explicitly configured and activated.
- Added operations, security review, ADR, architecture, roadmap, README, manual
  setup, and evolution documentation.

### Problems encountered and resolution

- A rebuilt test image exposed eight line-length failures that a stale earlier
  image had missed. The source was reformatted and the image rebuilt before
  accepting the test result.
- The authenticated browser check exposed an existing PostgreSQL ambiguous-null
  parameter failure in unfiltered task listing. Optional task filters now use
  explicit text casts, with a repository contract regression test.
- Docker Desktop 4.78 initially crashed on inaccessible stale Unix-socket
  entries. Only the verified disposable runtime sockets were removed, WSL was
  reset, optional Docker AI was disabled in the workstation settings, and the
  engine recovered without a factory reset or volume deletion.

### Validation

- `docker compose config --quiet` passed.
- Ruff and Pytest passed 51 tests in 0.71 seconds in the final lifecycle build.
- `scripts/verify.ps1` passed builds, health for all six core services,
  safe/approval paths, lease retry/exhaustion, queued/running cancellation,
  dead-letter inspection, and lifecycle checks.
- The applied migration served campaign, prospect, and result lists over the
  authenticated live API; the previously failing unfiltered task list also
  returned successfully.
- Playwright loaded the authenticated campaign dashboard and initialized pilot
  with zero console errors/warnings. The 375x812 and 812x375 viewports had no
  horizontal overflow, and the labeled campaign dialog rendered successfully.
- The configured KarixMC product and privacy URLs both returned HTTP 200.
- `git diff --check` is required again immediately before publication.

### Remaining boundary

Live YouTube discovery is prepared but unverified because no restricted API key
was used. No creator email was discovered, guessed, or sent. Real SMTP delivery,
reply ingestion/classification, link analytics import, public social posting,
payments/budget authority, creator contracts/disclosure review, regional legal
review, and production KarixMC conversion attribution remain user-owned or
future work.

## Step 18 — Add attested free OpenRouter routing with local continuity

Date: 2026-08-29

### Objective

Use a user-owned OpenRouter account for the strongest currently free hosted
model, move through an ordered fallback chain when a model/provider is
unavailable, prevent accidental paid-model use, preserve private local
continuity, and make the actual route/cost visible to the operator.

### Research and decision

Reviewed official OpenRouter free-limit, model-fallback, free-variant, catalog,
key-info, provider privacy, ZDR, usage accounting, router metadata, and Hermes
integration documentation plus OmniRoute 3.8.49 combo documentation. Confirmed
that free request quota is shared across free models (50/day below the stated
credit threshold; 1,000/day after at least USD 10 purchased), so model switching
improves model-specific availability but does not multiply account quota.

Selected a narrow career-worker OpenRouter adapter. OmniRoute remains Hermes'
general gateway, but its current automatic free-tier filter is documented as
fail-open when no candidates match and therefore cannot be the sole paid-balance
boundary. ADR-0012 records the decision.

### Implementation

- Added live text-catalog discovery and a strict eligibility rule: exact
  `:free` ID plus zero prompt, completion, and request prices.
- Added an overrideable current-quality order led by Nemotron 3 Ultra, native
  ordered cross-model fallback, 15-minute cooldown of models skipped before a
  successful fallback, and local Qwen continuity.
- Defaulted remote résumé requests to provider no-training and zero-retention
  filters. The returned model must map to the verified chain and usage cost must
  be exactly zero before output is accepted.
- Added normal-key status inspection and conservative atomic PostgreSQL daily
  reservations. The default is 40; 900 requires explicit operator confirmation
  of the USD 10 all-time purchase threshold because `/key.is_free_tier` proves
  only that some credits were purchased. The cap cannot account for OpenRouter
  usage outside this deployment; upstream enforcement remains authoritative.
- Added migration 008 and an inference invocation ledger containing only route,
  provider/model, privacy, token, latency, fallback, status, error, and cost
  metadata. It stores no prompt, résumé, job text, completion, or key.
- Added dashboard and Prometheus inference status, including the actual selected
  route and recorded credits. Added a hidden-prompt configuration/status/smoke
  PowerShell command that never accepts the key as a command argument.
- Added unit/contract tests, operations/troubleshooting guidance, current-source
  research, architecture/security updates, roadmap updates, and readiness-gate
  integration.

### Problems encountered and resolution

- The first repository contract test counted a variable name appearing both as
  a Compose key and inside interpolation. It now parses the Compose model and
  proves that only `job-worker` receives the credential.
- The first local status response rendered PostgreSQL zero as `0E-12`; API
  formatting now normalizes zero for an operator-readable dashboard.
- OpenRouter model responses may return a canonical slug instead of the exact
  requested variant. Selection validation now accepts only canonical aliases of
  a catalog-verified free route and still requires returned zero cost.
- Final review found a displaced `else` branch in the unified readiness script;
  the OmniRoute and OpenRouter checks are now independent and the script parses.
  Hosted usage fields are also validated before changing route cooldown state,
  so malformed or non-zero-cost responses retain the original safe route.
- Final official-documentation review found that `/key.is_free_tier=false` does
  not attest the USD 10 purchase threshold. Automatic 900-request selection was
  removed; the safe 40-request default now increases only through an explicit
  non-secret operator assertion, without exposing a management key.
- The first GitHub validation run exposed a fresh-host monotonic-clock edge:
  uptime below the 15-minute key-metadata TTL looked like a warm cache even
  though no metadata had loaded. The cache timestamp now has an explicit
  unloaded sentinel, making cold-start behavior independent of machine uptime.

### Validation

- Live catalog research returned 18 current text `:free` models with zero
  prompt/completion price; no credential or completion was used for that query.
- `docker compose config --quiet` and PowerShell/JavaScript syntax checks passed.
- Ruff and Pytest passed 58 tests in the rebuilt final test image.
- `scripts/verify.ps1` passed builds, six-service core health, safe/approval
  paths, lease retry/exhaustion, queued/running cancellation, dead-letter
  inspection, and lifecycle checks.
- `scripts/doctor.ps1 -Agent` passed; existing OmniRoute exposed 79 models and
  `free/default` returned a live completion through `agent-smoke.ps1`.
- The applied migration served authenticated inference status. A disposable
  career smoke fetched 100 current listings, retained 38 matches, and completed
  the new route through local `ollama/qwen3:8b`; the ledger/UI showed one local
  success and zero recorded credits.
- Playwright authenticated to the dashboard, rendered the Free inference card
  with the actual route, and reported zero console errors or warnings.

### Remaining boundary

No OpenRouter key was supplied, stored, or used, so hosted completion and live
cross-model fallback remain prepared/unverified. The user must create a normal
scoped inference key, set its provider-side spend limit/expiry, run the hidden
configuration prompt and harmless zero-cost smoke, and separately add OpenRouter
to OmniRoute if interactive Hermes sessions should use it. Free model inventory,
shared quota, privacy-compatible endpoint availability, and third-party terms
can change. Local Qwen remains required for guaranteed no-provider continuity.

## Step 19 — Partition free inference pools by purpose and value

Date: 2026-08-29

### Objective

Verify whether OpenRouter and OmniRoute were actually coordinated, prevent
general agent traffic from wasting the career drafting allowance, direct
bounded hosted drafts to the most valuable opportunities, and preserve a fully
free local continuity path.

### Research and decision

Inspected the ignored environment only for boolean/key presence, the
authenticated OmniRoute catalog, sanitized Hermes configuration, existing
OpenRouter adapter, and official upstream routing/quota documentation. The
workstation had OpenRouter disabled with no key. OmniRoute exposed 79 route IDs,
including 40 concrete routes all owned by OVHfree and no OpenRouter route.

Confirmed that OmniRoute's advertised aggregate free-token figure represents
separately enrolled provider tiers, not a gateway-issued credit balance;
OpenRouter's free allowance is account-wide; OmniRoute's budget header is
positive-number/automatic-route scoped; and Hermes supports an ordered custom
fallback chain. ADR-0013 records the purpose-aware allocation.

### Implementation

- Changed the committed Hermes primary from generic `auto` to explicit
  `free/default` and added internal `qwen3:8b` as its custom fallback.
- Recreated Hermes with a non-secret Ollama client-compatibility value and
  rendered the fallback into the existing named volume without exposing its
  configuration or credentials.
- Kept direct strict-free OpenRouter exclusive to career drafts. The same
  account is not intentionally connected to OmniRoute, so Hermes traffic cannot
  bypass the PostgreSQL reservation ledger.
- Extended the agent doctor to report concrete OmniRoute pool ownership, detect
  OpenRouter overlap, enforce the Hermes primary, and inspect the local fallback
  without printing credentials.
- Sorted new opportunities by match score and then freshness before choosing
  the bounded automatic-preparation set.
- Added unit/repository contracts, ADR/research/operations documentation, and
  synchronized architecture, security, roadmap, and system-evolution claims.

### Validation

- All Compose configurations passed.
- The rebuilt Ruff/Pytest image passed 60 tests.
- `scripts/verify.ps1` passed builds, six-service health, safe and approved
  paths, lease recovery/exhaustion, cancellation, and dead-letter inspection.
- `scripts/doctor.ps1 -Agent -LocalModel` reported 40 OVHfree concrete routes,
  no OpenRouter overlap, Hermes `free/default`, the local fallback, and healthy
  GPU-backed Ollama.
- `scripts/agent-smoke.ps1` completed through `free/default`; Hermes returned
  exactly `HERMES_READY_OK`; Qwen returned exactly `LOCAL_MODEL_OK` and reported
  100% GPU placement.

### Remaining boundary

OpenRouter remains prepared but inactive until the user installs a scoped key
and its authenticated smoke reports zero cost. The Hermes fallback configuration
and local endpoint were each verified, but a forced real outage/failover was not
induced against the working provider. Provider terms, quotas, and OmniRoute pool
membership can change; the doctor detects local drift but cannot observe usage
from other devices or applications.

## Step 20 — Make creator promotion activation usable and measurable

Date: 2026-08-31

### Objective

Reduce creator-promotion activation to the few account-owned inputs that cannot
be automated, add useful zero-cost distribution functions before external email
is ready, and prove the result in the real dashboard without weakening the exact
email-approval boundary.

### Research and decision

Reviewed current official YouTube API setup/search quota, Google Analytics UTM,
Google app-password, and Google Workspace SMTP documentation. Selected official
YouTube metadata, fixed TLS SMTP, and first-party UTM links. Rejected account
creation, interactive-login automation, email scraping/enrichment, bulk sending,
and public-posting credentials. No ADR was added because the new generation path
is read-only and preserves ADR-0011's outreach boundary.

### Implementation

- Added an authenticated deterministic promotion-kit endpoint with five assets:
  YouTube description/community, Discord, Reddit/community, and partner
  newsletter/blog copy.
- Derived every asset from the durable reviewed campaign fields and attached a
  distinct URL containing campaign UUID, source, medium, campaign slug,
  source-platform, and content key. Generation has no LLM, quota, egress, or
  mutation path.
- Added a dashboard dialog with reviewed key messages, destination guidance,
  per-asset copy, and complete-kit copy controls. No platform posting client or
  credential was introduced.
- Added `scripts/promotion.ps1` to show secret-safe readiness, validate a hidden
  YouTube key before writing ignored `.env`, configure Gmail STARTTLS through a
  hidden app-password prompt, start Docker Desktop if necessary, and open the
  promotion-capable dashboard with its private token copied rather than printed.
- Synchronized README, roadmap, architecture, security, operations, research,
  system evolution, tests, and measured experiment evidence.

### Problems encountered and resolution

- Docker Desktop 4.78 initially failed before the engine started because two
  transient AF_UNIX runtime endpoints had become invalid Windows reparse points.
  Exact-file deletion was refused by Windows. With Docker fully stopped, only
  the exact `Docker\\run` and `docker-secrets-engine` runtime directories were
  renamed to timestamped, recoverable sibling backups. Docker recreated them;
  images, named volumes, PostgreSQL, and repository data were not removed.
- The first promotion status probe called `/health` instead of the implemented
  `/health/ready`; the command now requires the explicit `ready` response.
- The first real browser render found `a a verified` in three assets because the
  stored product summary already began with an article. Templates were corrected
  and a regression assertion now rejects that phrase.
- The first test command used a previously built test image and still reported
  the old 60-test count. Rebuilding the isolated target ran the actual changed
  tree and exposed Ruff import/line-length findings, which were fixed before the
  final test and lifecycle runs.

### Validation

- PowerShell and JavaScript syntax checks plus `git diff --check` passed.
- The rebuilt isolated Ruff/Pytest image passed 62 tests.
- `docker compose config --quiet` and `scripts/verify.ps1` passed builds,
  six-service health, safe and approval paths, lease retry/exhaustion,
  queued/running cancellation, dead-letter inspection, and lifecycle checks.
- The authenticated endpoint returned five assets for the existing KarixMC
  campaign; all five carried the complete measured UTM field set.
- Playwright authenticated to the real loopback dashboard, opened the Promotion
  kit, rendered all five assets/copy controls, and reported zero console errors
  or warnings.
- The readiness command correctly reported Docker/dashboard ready, the kit
  available, and YouTube/real SMTP unconfigured.

### Remaining boundary

No YouTube API key or external SMTP credential was supplied, stored, or tested.
The user must create/restrict the Google key, enable two-step verification and a
mail credential or choose another TLS SMTP provider, enter both through hidden
prompts, then approve one harmless email to an owned inbox before creator mail.
Business-contact provenance, jurisdiction/terms review, each exact send,
inbound reply classification, sponsorship terms/disclosures, and public posting
remain operator work. First-party KarixMC conversion import is still pending.

## Step 21 — Prove creator outreach locally and isolate test credentials

Date: 2026-09-05

### Objective

Audit what remains before KarixMC creator outreach can be tested, close any
avoidable local-verification gap, and give the operator a truthful setup path
that separates local proof from YouTube discovery and real inbox delivery.

### Research and decision

Re-read the creator implementation, roadmap, architecture, side-effect review,
manual setup, and latest engineering record. Checked current official YouTube
Data API setup/quota documentation and Google app-password guidance. The
ignored workstation environment contained a non-placeholder YouTube key but no
real SMTP configuration. The product and privacy URLs remained reachable.

The generic side-effect smoke proved SMTP mechanics but not the creator-specific
campaign, generated introduction, metrics, or suppression path. Added a focused
no-egress proof rather than weakening the real-send approval boundary. No ADR
was needed because the production capability and authority boundaries did not
change.

### Implementation

- Added `scripts/creator-outreach-smoke.ps1` and
  `promotion.ps1 -LocalTest`. It creates an inactive synthetic campaign and
  authorized `.test` contact, verifies five distinct promotion assets, prepares
  and approves one exact introduction to Mailpit, records an opt-out, proves a
  second plan is refused, checks metrics, and removes its own durable records.
- Changed every Mailpit-mode startup to blank `SMTP_USERNAME` and
  `SMTP_PASSWORD` before Compose resolves the test containers, then restore the
  calling process environment.
- Made promotion status compare saved settings with the actual running worker
  configuration without printing secrets. It now distinguishes a loaded
  YouTube key, stale worker configuration, Mailpit mode, current SMTP mode, and
  the separate owned-inbox proof still required.
- Fixed the older side-effect smoke cleanup to delete linked inference-ledger
  rows before deleting its synthetic task records.
- Added repository contracts plus synchronized README, roadmap, architecture,
  operations, security, test-readiness, and system-evolution documentation.

### Problems encountered and resolution

- Docker Desktop 4.78 could not start because invalid transient
  `dockerInference` and secrets-engine Unix endpoints reappeared. With Docker
  stopped, only the exact local runtime directories were moved to timestamped,
  recoverable siblings; WSL was shut down once so Docker could recreate clean
  endpoints. Images, named volumes, PostgreSQL, and repository data were not
  deleted.
- The first rerun of the broad side-effect smoke passed its actions but cleanup
  hit the inference ledger's restrictive task foreign key. The cleanup order
  was corrected, the exact leftover synthetic profile was removed, and a second
  run left zero matching profiles.
- The first `scripts/test.ps1` invocation used the previous test image and
  reported 62 tests. The test image was explicitly rebuilt; the changed tree
  then ran 63 tests, and the complete verification rebuilt it again.

### Validation

- The creator smoke delivered exact task
  `7bfcd01d-f5de-4c40-8ef9-10bd722d280e` to Mailpit, returned five distinct
  attributed assets, persisted suppression, rejected another plan, and left
  zero disposable creator campaigns.
- Inspection of the running test action worker reported Mailpit transport,
  blank SMTP username/password, the local invalid sender, and no TLS only for
  that internal test mode.
- The corrected broad side-effect smoke passed exact application
  `d65a1fc0-b410-46be-a729-3814e3867224`, local email
  `9e8539b2-88b4-4826-b16a-2c40d3aaa9f9`, and duplicate refusal
  `b160e1e0-c4c0-4fd0-adcf-d2e795a137f4`; zero synthetic career profiles
  remained.
- `https://karixmc.pl/` and `https://karixmc.pl/privacy` both returned HTTP 200.
- The rebuilt isolated suite passed Ruff and 64 tests. `docker compose config
  --quiet`, `scripts/verify.ps1`, PowerShell parsing, and `git diff --check`
  passed.
- Final promotion status reported Docker/dashboard healthy, the saved YouTube
  key loaded in `job-worker`, action execution in isolated Mailpit mode, and real
  SMTP still unconfigured. No live creator-discovery scan or external email was
  performed.

### Remaining boundary

The operator must verify Google-side key restriction, run one deliberate live
campaign scan, choose/configure a TLS mail provider, deliver one approved test
message to an owned inbox, and only then qualify and contact real creators.
Public business-contact provenance and legal review, every exact approval,
reply classification, compensation/contracts/disclosures, point grants,
placement review, and attribution entry remain human-owned. OAuth mail reading
and first-party KarixMC analytics import remain future work.

## Step 22 — Validate the full local product and prepare a private VPS release path

Date: 2026-09-07

### Objective

Rerun the complete local product proof, show the authenticated creator workflow
in a real browser, automate every repository-owned step needed for a safe first
VPS deployment, and distinguish private single-user readiness from unfinished
public-production work.

### Research and decision

Re-read the roadmap, architecture, deployment, security, manual-setup, and
latest engineering records. Applied the FastAPI/frontend security baseline and
checked current official Docker Ubuntu, firewall, daemon, and rootless guidance.
Kept the first VPS interface on loopback behind SSH/WireGuard/Tailscale. Rejected
a public TLS proxy with the current bootstrap bearer token because it would not
provide OIDC/RBAC, rate limiting, revocation, or step-up identity. Recorded the
boundary in ADR-0014.

### Implementation

- Added explicit Host-header validation and disabled `/openapi.json` alongside
  the already-disabled interactive docs.
- Added Linux commands for secret-safe production `.env` creation, fail-closed
  preflight, private stack startup, authenticated safe/approval smoke, owner-only
  checksummed backup, and disposable restore validation.
- Preflight inspects all Compose profiles and refuses dirty checkouts,
  placeholders, broad secret permissions, Mailpit configuration, any published
  port without `127.0.0.1`, host networking, privileged mode, or Docker-socket
  mounts. Host/firewall/backup-alert checks remain explicit warnings.
- Synchronized README, roadmap, architecture, security, deployment, backup,
  readiness, manual-setup, ADR index, Make targets, tests, and system evolution.

### Problems encountered and resolution

Docker Desktop 4.78 again failed before WSL startup because stale AF_UNIX
reparse points prevented its inference and secrets listeners from replacing
their sockets. With Docker fully stopped, the exact transient `Docker\\run`
directory and exact `docker-secrets-engine` directory were moved to timestamped,
recoverable siblings. Docker recreated both. Images, volumes, PostgreSQL, source,
and secrets were not deleted or reset.

An isolated VPS initializer probe exposed that the first placeholder check also
matched the explanatory `CHANGE_ME` comment. The preflight was narrowed to
placeholder assignment lines, and the initializer then passed creation plus
overwrite-refusal checks.

### Validation

- `promotion.ps1 -LocalTest` passed synthetic creator campaign
  `5725b9c7-8658-418b-a44c-cd5b3368afa6`, exact Mailpit introduction task
  `7701a79f-9728-43d6-849a-271063d3428b`, five distinct assets, suppression,
  no-egress assertion, and cleanup.
- The broad side-effect smoke passed fake ATS application
  `a94e5402-855d-48a0-a49a-2d402855a20b`, local email
  `9fb326d0-2229-4b65-8e39-2801d975f801`, and duplicate refusal
  `ce41d58c-fda4-4d4c-bfd2-967a742d4f5e` with no external destination.
- Rebuilt Ruff/Pytest passed 67 tests. PowerShell and Bash parsing, Compose
  rendering, all-profile loopback inspection, and `git diff --check` passed.
- Chromium authenticated without persisting the token, rendered the creator
  campaign and five-channel Promotion kit, and reported zero console errors or
  warnings. `/openapi.json` returned 404 and an untrusted Host returned 400.
- The complete readiness gate passed core lifecycle (46.56 s), disposable
  restore (8.56 s), doctor (9.24 s), OmniRoute (4.41 s), local Qwen GPU
  inference (24.80 s), and Hermes (19.69 s). OpenRouter was correctly skipped
  because it is not configured.
- The Linux backup/restore scripts ran through Git Bash against the local
  containers: checksum verification passed; the disposable restore contained 8
  migrations, 150 tasks, 487 audits, and zero orphan audits, then was removed.
  The VPS initializer passed an isolated create/refuse-overwrite probe.

### Remaining boundary

No actual VPS was supplied, so host hardening, Linux preflight/startup, encrypted
off-host transfer, alert delivery, and rollback remain unverified on the target.
Real creator activation still needs Google-side key restriction proof, one live
YouTube scan, a user-owned TLS SMTP credential, and one approved delivery to an
owned inbox. Real ATS destinations remain compatibility-specific and each final
application/email requires exact approval. Public or multi-user exposure remains
blocked on OIDC/RBAC, rate/body limits, TLS, step-up identity, centralized
secrets, signed releases, and incident response.

## Step 23 — Manage the model hierarchy, local login, and VPS lifecycle

Date: 2026-09-08

### Objective

Make normal local startup one command without explicit Qwen or clipboard flags;
route Hermes through OmniRoute, OpenRouter free, and local Qwen in that order;
keep Qwen weights lazy; and make the private VPS recover after reboot or process
failure without an interactive launch script.

### Research and decision

Re-read the repository architecture, security, operations, roadmap, ADRs, and
latest engineering record. Applied the FastAPI/general frontend security
baseline. Confirmed from upstream Hermes documentation that ordered top-level
fallback providers are supported and from OpenRouter documentation that
`openrouter/free` is its free-model router. ADR-0015 records the chosen boundary:
supervise a small empty Ollama daemon instead of exposing Docker control to
Hermes, load Qwen weights only on the final request, and replace normal bearer
copy/paste with a one-use browser exchange.

### Implementation

- Added a networkless, capability-dropped one-shot configuration service that
  renders the committed OmniRoute `free/default` → OpenRouter
  `openrouter/free` → internal Qwen policy into the private Hermes volume.
- Made the agent profile supervise Ollama on CPU or an automatically selected
  NVIDIA override. Normal startup caches but does not invoke Qwen; explicit
  local-model canaries unload it after success and the idle timeout covers real
  fallback calls.
- Added 90-second one-use browser bootstraps, signed HttpOnly SameSite sessions,
  exact-origin/CSRF enforcement for cookie writes, automatic launcher exchange,
  and retained bearer auth only for scripts/manual recovery.
- Made safe side-effect fixtures independent of model selection and extended
  launcher health checks to the agent and selected action profile.
- Added fail-closed VPS full startup, first-host OmniRoute bootstrap mode,
  provider/route health checks, one-use tunnel login, a managed systemd service,
  and a persistent 15-minute health timer. Compose restart policies remain the
  per-container recovery layer.
- Updated tests, examples, Make targets, README, roadmap, architecture,
  operations, security, ADR index, system evolution, and experiment record.

### Problems encountered and resolution

- An upstream Hermes configuration diagnostic unexpectedly expanded and printed
  the locally configured scoped OmniRoute key. The value was not added to any
  repository file or documentation. It must be rotated in OmniRoute before VPS
  deployment; later inspection uses only named fields and non-secret route
  output.
- A fresh-volume probe first exposed the upstream image's init system failing in
  a read-only one-shot container. An explicit minimal shell entrypoint fixed
  that boundary. The same probe then measured `/opt/data` as UID 10000 mode
  `0700`, so the copier remains non-root UID 10000 and writes the managed config
  mode `0600`; no privilege or Docker-socket mount was added.
- Docker Desktop 4.78 again encountered malformed transient inference and
  secrets-engine endpoints. After Docker and WSL were stopped, the exact
  transient `Docker\\run` directory was moved to a timestamped recoverable
  sibling without deleting images, volumes, source, or secrets. Docker recreated
  it correctly and engine 29.5.3 became available.
- The first full test used a stale test image and repeated an already-fixed import
  ordering report. Rebuilding the test image made the source under test explicit.
  A later fallback canary exposed a separate PowerShell bug: piping
  `nvidia-smi` through `Select-Object` could leave `$LASTEXITCODE` unset, causing
  a false CPU selection. GPU output and exit status are now captured before any
  pipeline in the launcher, doctor, and local-model helper.

### Validation

- Base and NVIDIA/all-profile Compose rendering passed. A disposable fresh named
  volume proved the non-root configuration copier writes a readable `0600`
  managed file containing the ordered hosted/local routes, then the probe volume
  was removed.
- Rebuilt `scripts/test.ps1` passed Ruff and 73 tests in 1.05 seconds.
  `scripts/verify.ps1` passed the same suite plus live safe-task, approval,
  retry/exhaustion, cancellation, and dead-letter paths.
- `scripts/doctor.ps1 -Agent` proved the exact OmniRoute → OpenRouter free →
  Qwen order and found Qwen cached but unloaded. `scripts/agent-smoke.ps1`
  listed 79 routes and completed inference through `free/default`; the managed
  Hermes CLI then returned exactly `HERMES_READY_OK` through its primary route.
- The explicit local fallback returned exactly `LOCAL_MODEL_OK`, Ollama reported
  all 37 model layers offloaded to the RTX 4070 Laptop GPU, and the helper then
  unloaded Qwen. A normal agent plus side-effect-test restart left `ollama ps`
  empty while all 12 required services were healthy.
- A real Chromium session exchanged the one-use launch code, immediately
  removed it from the URL, survived reload through the HttpOnly session, and
  submitted an authenticated task that reached `Succeeded`. Browser console
  errors and warnings were both zero.
- The broad safe side-effect smoke passed one exact fake application, one
  Mailpit message, and duplicate refusal with no egress. The creator-specific
  smoke passed campaign creation, exact Mailpit introduction, five attributed
  assets, opt-out suppression, and no discovery/email egress.

### Remaining boundary

The operator must still create/configure a scoped OpenRouter inference key, rotate
the exposed OmniRoute key, prove one live YouTube campaign scan, restrict the
YouTube key provider-side, configure TLS SMTP, and deliver the first canary only
to an owned inbox. An actual VPS, encrypted off-host backup, alert delivery, and
rollback drill remain target-host proofs; public/multi-user service still needs
OIDC/RBAC, rate limits, TLS, step-up identity, centralized secrets, and incident
response.

## Step 24 — Durable workflows and reconstructible task delivery

Date: 2026-09-09

### Objective

Improve useful autonomy with dependency-aware, bounded plans that retain task
policy, approval, and audit guarantees. Address a discovered reliability gap
where a lost Redis signal or a crash before PostgreSQL claim stranded queued
work. This milestone implements deterministic coordination, not AGI or a
model-driven planner.

### Implementation

- Added migrations 009/010 for immutable workflow/step state and outbox delivery
  generations. Plans allow up to 32 steps, four concurrent task slots, and a
  one-day deadline, with validated DAGs and bounded capability-specific inputs.
- Added authenticated create/list/detail/cancel APIs and dispatcher reconciliation
  under PostgreSQL row locks. Task creation, step binding, outbox, and audit
  share one transaction. Idempotency distinguishes identical requests from
  changed plans.
- Added exact scalar result checks, transitive failure suppression, independent
  branch continuation, approval waiting, cooperative cancellation, late-completion
  deadline checks, and quarantine of steps rejected by a later capability policy.
- Kept workflow-managed career handlers from creating hidden preparation or
  approval tasks. Raw email send and application submit remain outside plans and
  retain the existing exact-action authorization path.
- Added bounded replay of old published signals for due queued tasks, generation
  guards on publisher success/failure, and expired-owner refusal for heartbeat,
  completion, and failure. Refactored cancellation to support caller transactions.
- Added a dashboard workflow composer, safe parallel demo, draft/preflight
  recipe, custom plan editor, progress/step/check inspection, task audit links,
  cancellation, refresh-preserved form state, and mobile layout.
- Made the test command rebuild by default, wired isolated PostgreSQL workflow
  and queue probes into verification and CI, and excluded ignored browser
  artifacts from Docker build context. No runtime dependency or image pin changed.
- Updated README, roadmap, operations, architecture, security, system evolution,
  and ADR-0016. Documented the separately discovered career/creator schedule
  advancement crash gap as remaining work instead of claiming it solved.

### Validation

- Rebuilt containerized Ruff/Pytest passed 110 tests; the final full verification
  invocation reported 0.87 seconds for Pytest. New handler tests prove managed
  workflows suppress hidden children while ordinary career behavior remains.
- `docker compose config --quiet`, `scripts/test.ps1`, `scripts/verify.ps1`,
  changed PowerShell parsing, JavaScript syntax, and `git diff --check` passed.
- Full verification proved safe/approved tasks, lease retry/exhaustion, queued
  and running cancellation, and dead-letter inspection.
- The new workflow probe applied every migration to an empty disposable database
  and passed 12 scenario groups: DAG/fork/join/restart, capacity, evidence failure,
  approvals/rejection, idempotency conflict, cancellation, deadlines, on-time vs.
  late completion, six concurrent reconcilers, atomic rollback, and retired
  capability quarantine. Its database was removed afterward.
- The queue probe passed replay, stale generation refusal, due/approval/lease
  guards, and cancellation rollback in its own synthetic schema, then removed it.
- Chromium passed 12 mocked UI paths and a live four-step demo with four exact
  checks, one-use login/URL scrub, HttpOnly session/reload, task audit navigation,
  390-pixel layout, and zero page errors. Only the probe's synthetic live records
  were removed; screenshots remain in ignored local output.
- The rebuilt isolated action runtime passed the existing fake-ATS submission,
  local Mailpit delivery, and duplicate refusal smoke; no application or email
  left the Docker test network.

### Problems and remaining boundaries

Docker Desktop again failed on malformed transient inference and Secrets Engine
socket directories. With the backend stopped, only those verified transient
directories were preserved as timestamped siblings; engine 29.5.3 then started.
Images, volumes, configuration, and secrets were not deleted. Initial lint found
three long lines, which were corrected. A mounted-source check exposed Windows
executable-bit metadata, so final tests used the rebuilt canonical test image.
The browser probe used its existing shared-memory temporary space after its
small `/tmp` filled; no production container permissions were widened.

The first expanded GitHub runtime gate passed application/unit checks but found
that the recovery smoke read missing database-name/user entries directly from
the minimal CI `.env`, while Compose correctly used defaults. The helper now
uses the same `agent`/`agent_app` defaults. The failure did not involve task or
workflow execution and was not bypassed; CI is rerun with the corrected helper.

Plans remain explicit recipes with fixed inputs. Model-authored planning,
replanning, dynamic result binding, safe memory retrieval, general scheduling,
and the policy-bound Hermes adapter remain future work. Cancellation is
cooperative and cannot undo a handler already in flight. This milestone does
not claim a new model benchmark, live external provider delivery, public
production readiness, or target-VPS validation.

## Step 25 — Repair and harden smart free-model switching

Date: 2026-09-10

### Objective

Diagnose the first user-key OpenRouter HTTP 400, complete a harmless live proof,
and replace the decaying fixed free-model order with a policy-constrained smart
switch. Preserve the established OmniRoute → OpenRouter → lazy-Qwen hierarchy,
the exact-free/cost attestation, résumé privacy, daily accounting, and secret
boundaries.

### Implementation

- Reproduced the 400 without printing the key. OpenRouter's safe error field
  showed that the `models` array now accepts no more than three entries; the old
  request supplied seven. Capped the request at one primary plus three
  fallbacks, including when an existing `.env` still asks to discover eight.
- A second bounded probe showed the highest-ranked catalog models had no
  endpoint matching combined no-training/ZDR policy. Added a cached intersection
  with `/endpoints/zdr`, accepting only active exact `:free` models before a
  prompt can leave the worker.
- Replaced the stale built-in priority with dynamic bounded scoring from the
  catalog's Artificial Analysis intelligence/coding/agentic fields at 50/30/20.
  Declared structured-output, response-format, tool, reasoning, and context
  capabilities break ties. Explicit exact-`:free` operator order remains an
  override; missing benchmark values are missing evidence.
- Added low reasoning effort/exclusion when every candidate supports the portable
  parameter so reasoning-first models retain room for visible structured output.
- Added semantic failover. Empty or application-schema-invalid output is counted
  and audited as a failed reservation, the selected route cools for 15 minutes,
  and the next remaining ranked route receives a separate reservation. This
  prevents a syntactically successful weak response from becoming a draft or
  consuming an unaccounted retry.
- Classified known OpenRouter failures without emitting raw response envelopes,
  account identifiers, prompts, or keys. Made the OmniRoute canary report only
  its bounded selected-model field and safe error classes.
- Added ADR-0017 and synchronized configuration defaults, README, roadmap,
  architecture, security, operations, research, and integration claims. The
  interactive route remains OmniRoute `free/default` first because OmniRoute
  lacks equivalent benchmark telemetry and its automatic free filter can fail
  open; the general OpenRouter router remains random among compatible models.

### Validation

- The original live smoke reproduced HTTP 400 with the provider's three-fallback
  limit. A four-route diagnostic then reached the separate ZDR policy failure.
  The corrected strict-ZDR script returned exactly `OPENROUTER_FREE_OK` through
  `inclusionai/ling-3.0-flash-fin:free` at provider-reported cost zero.
- The rebuilt Python career adapter independently returned the same exact canary,
  selected model, two-route strict-ZDR plan, and zero cost without printing the
  key.
- OmniRoute listed 79 routes and `free/default` returned `ROUTE_OK`, reporting
  `aphrodite/TheDrummer/Cydonia-24B-v4.3` as the concrete selected model.
- A synthetic full career run fetched 100 public listings and matched 39. The
  first strict-ZDR hosted model returned schema-invalid output and the second
  returned empty output; both reservations were recorded, then local
  `qwen3:8b` produced the valid draft. This proves semantic/provider/local
  continuity, not hosted draft quality.
- Rebuilt containerized Ruff/Pytest passed 116 tests including the final
  empty-output attribution and single-hosted-route regressions. Final
  `docker compose config --quiet`, `scripts/test.ps1`, `scripts/verify.ps1`,
  agent doctor, OmniRoute canary, PowerShell parsing, and `git diff --check`
  passed.

### Problems and remaining boundaries

The first ad-hoc test invocation used a nonexistent `-NoBuild` switch; the
documented `scripts/test.ps1` command was then used and passed. Under the strict
privacy defaults, only two active free text endpoints were eligible during the
observation and neither published benchmark values. Their order therefore used
capability/context/stable tie-breaks, and neither produced an acceptable full
synthetic career draft on that run. Local Qwen preserved correctness.

The harmless OpenRouter canary proves authentication, routing, privacy
compatibility, and reported zero cost; it does not prove provider uptime,
benchmark truth, full-draft quality, forced Hermes cross-provider failover, or
future free inventory. The interactive OpenRouter free router remains outside
the career PostgreSQL ledger, so provider-side limits remain required.

## Step 26 — Guided goal planning, feature evidence, and atomic schedules

Date: 2026-09-11

### Objective

Test implemented features locally, turn the dashboard into an understandable
operating flow, add useful bounded autonomy, capture results, and publish a
validated milestone. Preserve private data and exact external-action approval;
do not characterize the system as AGI or claim untested integrations work.

### Implementation

- Added `planning.propose` to the server-derived medium-risk policy and existing
  research queue. PostgreSQL stores request context, action inventory, model
  proposal, digest, expiry, task binding, and adoption link. Model output selects
  only opaque server actions from explicitly chosen context; deterministic
  compilation emits at most eight sequential immutable workflow steps.
- Reused strict-free hosted inference, semantic failover, local Qwen, and the
  PostgreSQL usage ledger. The model receives only the goal and action descriptions,
  never stored résumés, job/contact text, context IDs, or executable payloads.
  An explicit template demo is honestly labeled. Owned leases and task links
  reject forged or stale proposal writes; a cached proposal survives worker retry
  without another model call. Adoption revalidates exact digest/current context
  and creates the workflow and link atomically; concurrent retries return one run.
- Closed the career/creator schedule crash window. Due-row locking, task creation,
  policy, audit, outbox, and next-scan advancement now share a transaction.
  Rollback retains due work, and an idempotency-key conflict cannot consume it.
- Added a Start-here home, context-bound Goal planner, feature readiness page,
  searchable keyboard menu, browser navigation history, labeled mobile navigation,
  next-action guidance, progressive optional forms, and preserved inline validation.
  Corrected existing Close/Cancel buttons that could submit forms or be blocked
  by required-field validation.
- Added fixed-schema feature reports and authenticated publication to PostgreSQL.
  Browser sessions cannot attest tests. Prerequisites and 24-hour evidence freshness
  keep configured, verified, needs-setup, and unavailable states distinct. Only
  check IDs/status/durations/reason codes/timestamps/revision/dirty state and
  allowlisted service/configuration booleans enter the report; no raw logs or data.
- Added reproducible feature, planner, scheduler, Hermes, and bounded YouTube
  probes. Hardened exact model markers, selected free-model/explicit zero-cost
  attestation, native process exit handling, exception-free reports, atomic report
  writes, and post-recreation health sampling. Default verification/CI includes
  isolated planner and scheduler database scenarios.
- Added ADR-0018, the guided operations guide, and synchronized README, roadmap,
  architecture, security, and evolution claims. No new service, dependency,
  credential scope, privileged host mount, or generic execution tool was added.

### Initial observations and corrections

The baseline passed all seven runtime/readiness checks, public career discovery
and hosted drafting, local application/email fixtures, creator workflow/outcomes,
and a bounded official YouTube query. Live goal planning selected the free Ling
route, reported zero cost and 480 total tokens, and completed its explicitly
adopted foundation workflow. Isolated scheduler probes passed six rollback,
concurrency, and conflict scenario groups. Planner SQL probes passed creation,
adoption rollback/concurrency, expiry, forged-link, cancellation, and lease checks.

Early full regression attempts stopped because the readiness module and one new
test line did not yet conform to repository Ruff rules; no successful feature report
was published from those attempts. Independent review corrected model/core prerequisites so
historical successful checks cannot override recorded unavailable services. An
initial baseline report sampled recreated containers before health checks settled;
the runner now waits briefly for that transition before collecting its signals.

### Final validation

- Fresh `feature-test.ps1 -PublishReport` passed all 13 selected checks with no
  skips, from 16:50:17 to 16:57:11 UTC. Report
  `04a0c84e-4182-41d2-a9ca-f23f1300f2c9` was published through the bearer-only API.
  It identifies base revision `a3811ee` with a dirty working tree, honestly
  describing validation of this milestone before commit.
- Compose validation, containerized Ruff and all 162 unit/contract tests,
  `verify.ps1`, workflow 12-scenario proof, scheduler six-scenario proof, isolated
  planner lifecycle/concurrency, lease/cancellation/retry/queue recovery, agent
  doctor, and configured OmniRoute/OpenRouter/Qwen/Hermes canaries passed.
- Public job discovery/drafting, one-query YouTube discovery, local ATS/Mailpit
  approval/execution, creator preparation/outcomes, and live model proposal plus
  explicit adoption completed. Cold Qwen proof took 217.90 seconds this run;
  successful GPU offload/response was observed and the test then unloaded it.
- Corrected migration 012 version bookkeeping and ran a fresh narrow restore:
  all 12 migration versions, 213 tasks, 707 audit rows, zero orphan audits,
  8.87 seconds. Only its disposable restore database was removed.
- Chromium browser proof passed 15 behavior groups and all 10 views at 390px,
  with zero page errors. It covered navigation/history, keyboard menu, forms,
  validation, proposal review/adoption, immutable selected context, and readiness.
  Desktop/mobile screenshots use labeled synthetic examples; README includes
  sample screenshots. A separate live-result capture uses persisted test work.
- Six authenticated live browser checks also passed: one-use bootstrap/URL scrub/
  HttpOnly session, unexecuted demo proposal, explicit adoption through successful
  workflow/output check, task audit, published report display, and reload. No page
  errors occurred. Workflow `0375348f-b571-4634-b890-48dcf1d46869` and its harmless
  synthetic demo records remain inspectable. The live screenshot crops only that
  result dialog; other screenshots are labeled illustrative sample data.
- All PowerShell scripts parsed and `git diff --check` passed. Screenshots and
  raw local proof outputs remain ignored; only explicitly reviewed sample images
  were copied into documentation.

### Remaining boundaries

The live discovery proof is a bounded official YouTube request, not an exhaustive
source test. Local Mailpit and ATS fixtures do not prove external SMTP delivery,
every real ATS, or a deployed VPS. General MCP, Telegram, safe memory retrieval,
coding workers, dynamic replanning, public multi-user identity, and autonomous
model training remain future work. Operator reports are historical attestations,
not cryptographic certification or continuous health monitoring.

## Step 27 — Live creator preparation and reliable SMTP evidence

Date: 2026-09-12

### Implementation

- Recovered the stopped local Docker Desktop after preserving the two exact
  transient socket paths that prevented startup. No volumes or user data were
  removed. The existing Mailpit creator smoke passed before implementation.
- Closed final send/submit lease and cancellation gaps, rehashed frozen contexts,
  and checked expiry after row-lock waits. Stale workers cannot corrupt another
  claim's failure state. Receipt creation now follows SMTP connection/TLS/login;
  known acceptance is durable before cleanup and survives later task failure.
- Added a fixed-config, medium-risk, single-attempt no-send SMTP diagnostic using
  task/policy/audit/outbox dispatch, private allowlisted status, and exact action
  lookup for historical messages. No raw provider protocol text is exposed.
- Added generic SMTP local setup with hidden credential entry and atomic writes
  that preserve literal characters and unrelated settings. Gmail shares the same
  writer. The check helper submits through the control API rather than opening
  its own mail connection.
- Added optional reviewed introduction copy, retained contact/privacy/opt-out
  text even at the maximum body length, and excluded `manual_initial` from
  template A/B learning. Exact approval, duplicate/state, and suppression guards
  remain in force. Paid-offer terms remain campaign-bound.
- Improved setup guidance, historical message/audit links, full-packet approval,
  acceptance/uncertainty wording, mobile digest wrapping, and a rapid dialog
  close/reopen race. Added ADR-0019 and synchronized operational/security claims.

### Validation and observed results

- Initial full tests stopped on two overlong Ruff lines, corrected before the
  successful gate. Compose validation and all 195 unit/contract tests passed;
  the test command took 7.73 seconds including the cached-image rebuild.
- `verify.ps1` passed in 68.44 seconds, including recovery, cancellation/retry,
  workflow 12-scenario proof, scheduler six-scenario proof, planner transactions,
  queue generation recovery, and the newly required delivery database guards.
- Application/email Mailpit proof passed in 31.90 seconds. Personalized creator
  proof passed in 12.24 seconds: exact copy/acceptance, five promotion assets,
  historical lookup, exclusion from template learning, and durable suppression.
- Reproducible secure-setup smoke passed in 1.82 seconds: five literal credential
  round trips in one network-disabled container, generic/Gmail hidden prompts,
  atomic preservation, five invalid-input rejections, and sanitized reporting.
  The real `.env` remained unchanged.
- Chromium passed nine focused email groups, 15 prior dashboard regression groups
  across ten views, and four authenticated live checks with zero page errors.
  Live task `e565b0ab-54d1-43ba-a7a2-72721e63d820` recorded a successful Mailpit
  connection check at 16:50:38 UTC; no login was used and no email was sent by
  that check. The retained screenshot contains only the email setup card.
- All PowerShell scripts parsed and `git diff --check` passed. An independent
  review found no material issue in manual-copy sequencing, analytics isolation,
  footer bounds, or communications policy/dispatch. Private runtime artifacts,
  prepared contact/copy, and credentials are excluded from publication.

### Live outreach boundary

The KarixMC homepage and privacy page returned HTTP 200. One relevant creator's
official website and linked channel provided a public collaboration contact;
that contact was saved to the existing inactive campaign. A concise inquiry is
prepared locally without financial or reward commitments. The user chose an
existing SMTP provider, but its host, sender, and local credential are still
missing. No real send action was created and no creator email was sent. Mailpit
proof establishes local behavior, not external SMTP acceptance or inbox delivery.
