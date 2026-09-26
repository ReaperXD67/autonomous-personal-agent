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
- [x] Narrow read-only Gmail career-label adapter, durable reply evidence, uncertainty review, and manual interview/outcome recording
- [ ] Configure Gmail OAuth and complete a real labeled-mail canary; broader email/account adapters remain deferred
- [x] Exact approval-gated single-recipient SMTP send adapter and local Mailpit proof
- [x] Final lease/cancellation/context guards, durable SMTP acceptance before cleanup, and audited no-send connection diagnostics
- [x] Secure generic SMTP setup, personalized reviewed introductions, exact-message history, and durable low-volume pacing with acceptance/uncertainty guidance
- [x] Governed creator campaigns with official YouTube discovery, manual contact provenance/reply classification, exact-email sequencing, results, and bounded draft adaptation
- [x] YouTube-focused research dossiers: public business-contact candidates, source evidence, explainable fit, collaboration concepts, per-creator refresh, searchable shortlist, and CSV export
- [x] Explicit country/language targeting with any/prefer/strict modes, Poland-only channel declarations, honest unknowns, and preserved excluded history
- [x] Bounded multi-page creator search with PostgreSQL request reservations, partial/duplicate coverage, complete campaign snapshot exports, pagination, and evidence/contact/recency segmentation
- [x] Deterministic multi-channel promotion kit with campaign-specific UTM attribution and secret-safe activation/status command
- [x] Creator-specific no-egress smoke covering exact introduction delivery, campaign metrics, opt-out suppression, and test-credential isolation
- [x] Fresh-job discovery/tracking from reviewed public sources
- [x] Optional Remotive public feed with attribution and 24-hour-delay disclosure; explicit published/updated/unknown date provenance, all-required-keyword matching, and remote-location constraints
- [x] Local résumé evidence and cover-letter drafting
- [x] First exact approval-gated single-page Greenhouse/Ashby/Lever hosted-form adapter
- [x] Career Play/Pause with prepare/apply modes, explicit expiring scope, trusted ATS hosts, fresh-job and fit gates, shared rolling application limits, profile binding, and duplicate protection
- [x] Opt-in application email only to one hiring address explicitly published in the matched job, sharing the ATS budget and dedupe guard
- [x] Private mission readiness, application preparation/blocker visibility, and durable application/reply/interview/outcome timelines
- [ ] Real external automatic-application and hiring-email canaries with user-configured identity and provider
- [ ] LinkedIn, Y Combinator, and Discord account integrations; use supported employer ATS boards for current discovery rather than browser-account bots
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
Application/email preparation can be automatic. Career Play can authorize exact
application packets under an explicitly selected, finite scope: reviewed hosts,
fresh publication evidence, score, daily cap, optional job-published hiring email,
profile, and expiry. Pause withdraws that run's authority before final submission.
This is not blanket permission to execute tools or message arbitrary contacts.
Manually prepared external actions and creator sends keep individual exact-action
approval. Creator discovery and business-contact extraction may be scheduled, but
contact qualification, creator reply classification, paid terms, and public
placement remain reviewed. Gmail classification is inferred evidence, with
uncertain matches and interview times left for explicit review.

## Evaluated but deliberately deferred

- Prime Agent as a disposable coding worker after sandbox/worktree isolation
- Nemotron 3 local hosting until hardware has enough VRAM; use a reviewed remote
  free route on the current 8 GB GPU
