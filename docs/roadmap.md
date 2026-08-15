# Roadmap

## Phase 0 — foundation (current)

- [x] Containerized control API, worker, PostgreSQL/pgvector, Redis
- [x] Durable task/approval/audit schema
- [x] Transactional outbox with at-least-once Redis delivery
- [x] High-impact approval gate and deterministic smoke capability
- [x] Secure Compose networks, healthchecks, persistent volumes
- [x] Optional release-pinned Hermes/OmniRoute integration
- [x] Curated MCP registry and permission profiles
- [x] Windows scripts, docs, tests, CI-ready structure

## Phase 1 — reliability and production gate

- [x] Startup migration runner applies versioned, idempotent SQL before runtime services
- [x] Migration rollback policy and disposable restore drill
- [x] Worker lease, bounded crash retry, expired-claim reconciliation, and audit events
- [x] Periodic heartbeat for long tools, delayed backoff, cancellation, and dead-letter inspection
- [ ] Per-user OIDC auth, roles, rate limits, step-up approvals
- [ ] OpenTelemetry traces/metrics/log correlation and alerts
- [ ] Encrypted automated backups and restore drill
- [ ] Reverse proxy/TLS/WireGuard deployment profile
- [x] Required SBOM, dependency, vulnerability, secret, and configuration CI gates
- [x] One-command workstation gate for lifecycle, restore, environment, and configured inference paths
- [ ] Signed release images and upstream image-signature verification

## Phase 2 — agent/model integration

- [x] Optional pinned Ollama/Qwen3 8B local fallback with GPU-aware setup script
- [ ] Complete OmniRoute provider onboarding with cost budgets
- [ ] Hermes adapter that creates control-plane tasks instead of bypassing policy
- [ ] Model routing tests, fallback canary, usage/cost audit metadata
- [ ] Safe memory writer/retriever with provenance and deletion policy
- [ ] Scheduler that persists jobs before queue publication

## Phase 3 — curated tools

- [ ] Read-only fetch/search MCP profile with SSRF/egress controls
- [ ] Disposable Playwright worker with domain and download policy
- [ ] Sandboxed filesystem/coding worker per repository worktree
- [ ] GitHub read tools, then draft PR workflow; merge stays approval-gated
- [ ] Read-only database diagnostics role/tool

## Phase 4 — personal workflows

- [ ] Telegram control with pairing and allowlist
- [ ] Email read/classify, then draft, then separately gated send
- [ ] Job discovery/tracking; every submission approval-gated
- [ ] Calendar/Drive/Notion/task-manager integrations by scoped profile
- [ ] Web UI for tasks, approvals, audit timelines, and budgets

## Never autonomous by default

Purchases/transfers, mass communication, job submission, public publishing,
production infrastructure changes, and destructive repository/data operations.

## Evaluated but deliberately deferred

- Prime Agent as a disposable coding worker after sandbox/worktree isolation
- Nemotron 3 local hosting until hardware has enough VRAM; use a reviewed remote
  free route on the current 8 GB GPU
