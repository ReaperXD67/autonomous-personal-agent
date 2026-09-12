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
- [x] Recover lost ready signals from PostgreSQL; fence stale outbox acknowledgments and expired workers
- [x] Durable bounded workflow DAGs, parallel dispatch, explicit result checks, deadlines, cancellation, and restart recovery
- [ ] Per-user OIDC auth, roles, rate limits, step-up approvals
- [ ] OpenTelemetry traces/metrics/log correlation and alerts
- [ ] Encrypted automated backups and restore drill
- [x] Private loopback VPS bootstrap, preflight, smoke, backup, and restore tooling
- [x] Managed VPS boot/recovery service and periodic model-provider health probe
- [ ] Public reverse proxy/TLS/OIDC/rate-limit deployment profile
- [x] Required SBOM, dependency, vulnerability, secret, and configuration CI gates
- [x] One-command workstation gate for lifecycle, restore, environment, and configured inference paths
- [ ] Signed release images and upstream image-signature verification

## Phase 2 — agent/model integration

- [x] Optional pinned Ollama/Qwen3 8B local fallback with GPU-aware setup script
- [x] Managed OmniRoute → OpenRouter free → lazy local Qwen hierarchy
- [ ] Complete OmniRoute provider onboarding with cost budgets
- [ ] Hermes adapter that creates control-plane tasks instead of bypassing policy
- [x] Free-only OpenRouter catalog policy, ordered fallback tests, local continuity, and PostgreSQL usage/cost audit metadata
- [x] Purpose-aware free-pool allocation, top-match reservation priority, Hermes local fallback, and shared-quota drift diagnostics
- [x] Install a scoped OpenRouter inference key and pass the harmless live fallback canary
- [ ] Safe memory writer/retriever with provenance and deletion policy
- [x] Career scheduler persists tasks through the policy/outbox path before queue publication
- [ ] General-purpose scheduler beyond career missions
- [x] Make career/creator schedule advancement atomic with task creation to close the pre-task crash gap
- [x] Policy-bound model planner that proposes reviewed workflows using the immutable plan API

## Phase 3 — curated tools

- [ ] Read-only fetch/search MCP profile with SSRF/egress controls
- [x] Disposable Playwright worker for reviewed ATS forms with domain, request, profile, and download policy
- [ ] General read-only/browser MCP profile with DNS/IP-aware egress proxy
- [ ] Sandboxed filesystem/coding worker per repository worktree
- [ ] GitHub read tools, then draft PR workflow; merge stays approval-gated
- [ ] Read-only database diagnostics role/tool

## Phase 4 — personal workflows

- [ ] Telegram control with pairing and allowlist
- [ ] Email read/classify and OAuth adapters
- [x] Exact approval-gated single-recipient SMTP send adapter and local Mailpit proof
- [x] Final lease/cancellation/context guards, durable SMTP acceptance before cleanup, and audited no-send connection diagnostics
- [x] Secure generic SMTP setup, personalized reviewed introductions, and exact-message history with acceptance/uncertainty guidance
- [x] Governed creator campaigns with official YouTube discovery, manual contact provenance/reply classification, exact-email sequencing, results, and bounded draft adaptation
- [x] Deterministic multi-channel promotion kit with campaign-specific UTM attribution and secret-safe activation/status command
- [x] Creator-specific no-egress smoke covering exact introduction delivery, campaign metrics, opt-out suppression, and test-credential isolation
- [x] Fresh-job discovery/tracking from reviewed public sources
- [x] Local résumé evidence and cover-letter drafting
- [x] First exact approval-gated single-page Greenhouse/Ashby/Lever hosted-form adapter
- [ ] Real-site compatibility suite and additional reviewed ATS adapters
- [ ] Calendar/Drive/Notion/task-manager integrations by scoped profile
- [x] Private web UI for missions, opportunities, tasks, approvals, and audit timelines
- [x] One-use launcher bootstrap and signed HttpOnly private dashboard session
- [x] Private inference route/usage/cost status in the dashboard
- [x] Guided home, goal proposals, searchable navigation, mobile labels, and progressive setup forms
- [x] Feature-by-feature prerequisites and timestamped operator test evidence in PostgreSQL
- [ ] Per-user budget policy and identity

## Never broad or unreviewed by default

Purchases/transfers, mass communication, job submission, public publishing,
production infrastructure changes, and destructive repository/data operations.
Application/email preparation can be automatic; each exact external action
requires its own unexpired approval and cannot borrow a blanket permission.
Creator discovery may be scheduled, but business-contact qualification, every
send, reply classification, paid terms, and public placement remain reviewed.

## Evaluated but deliberately deferred

- Prime Agent as a disposable coding worker after sandbox/worktree isolation
- Nemotron 3 local hosting until hardware has enough VRAM; use a reviewed remote
  free route on the current 8 GB GPU
