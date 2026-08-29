# System evolution

## v0.1 — Secure foundation (2026-08-11)

The project began with a containerized control API, policy gate, PostgreSQL,
pgvector, Redis, outbox dispatcher, deterministic worker, audit trail, and
disabled-by-default MCP catalog. PostgreSQL became authoritative because task and
approval state must survive queue and process failure. Hermes and OmniRoute were
kept optional so credentials were not required for the core stack.

## v0.2 — Dependency and delivery hardening (2026-08-12)

Dependency advisories were closed and Redis/outbox failure recovery was exercised.
The architecture retained a small explicit worker instead of adopting a queue
framework before retry, scheduling, and lease requirements were understood.

## v0.3 — Recoverable execution and hybrid free inference (2026-08-12)

A one-shot migration gate now applies versioned SQL before runtime services
start. Worker claims receive durable leases; the dispatcher requeues expired
claims within a three-attempt budget and records recovery/exhaustion audit events.
This closes the permanent `running` state left by a worker crash.

Inference evolved into a hybrid design: OmniRoute remains the primary free-tier
gateway, while pinned Ollama provides an optional no-token-cost local fallback.
The local model is intentionally modest because the observed 8 GB GPU cannot run
current Nemotron 3 agentic checkpoints responsibly. Prime Agent remains a future
isolated coding worker rather than a second privileged orchestrator.

## v0.4 — Owned execution lifecycle and proven restore (2026-08-15)

Task claims now carry unique lease IDs and worker identities. Heartbeats renew
long work, stale workers cannot commit, cancellation is durable and cooperative,
retries use bounded exponential delay, and exhausted claims become authenticated
dead-letter records. Capability policy establishes a minimum risk instead of
trusting caller labels.

Backups now receive checksum sidecars and a restore drill validates a randomly
named disposable database through both SQL invariants and application code
before removing it. Local Qwen3 8B also progressed from prepared to verified on
GPU.

## v0.5 — Enforced supply-chain evidence (2026-08-15)

The already-required CI check now reviews dependency changes, scans the clean
repository for vulnerabilities, secrets, and misconfiguration, scans the built
runtime image, and emits an SPDX JSON SBOM. Every action is pinned to an
immutable commit. This turns prior asynchronous advisory monitoring into a merge
gate without granting SARIF or package-write permissions.

Release signing remains deferred until the project has a registry and trusted
OIDC identity. Local-only tags are not presented as signed releases.

## v0.6 — Unified workstation readiness evidence (2026-08-15)

A single no-skip readiness gate now composes the control-plane lifecycle,
disposable restore, environment doctor, remote free route, local GPU model, and
Hermes route into one pass/fail result. Its ignored JSON report contains only
sanitized check metadata. Cached local models are reused by default to avoid
coupling a valid offline inference path to registry availability; exact response
and GPU-placement verification remain required.

## v0.7 — Private command center and career missions (2026-08-15)

The control API now serves a same-origin private web command center for missions,
fresh opportunities, tasks, approvals, and audit activity. PostgreSQL remains
authoritative for career profiles, source-attributed opportunities, and local
application packs. A dedicated career worker is the only core worker with
outbound access; its job-source hosts, redirects, sizes, timeouts, and public ATS
board slugs are bounded.

Active profiles persist their next run and create scheduled work through the
same policy, audit, transactional outbox, lease, and retry path as user-created
tasks. Résumé text does not enter task payloads, queue envelopes, audit metadata,
or public source requests. Local Qwen creates structured truthful preparation
packs, but no generic job-form submit capability exists. The system records a
user-completed application only after the user submits on the official site.

## v0.8 — Exact approval-bound external actions (2026-08-25)

Career autonomy now extends through automatic draft and supported-form
preparation. Lever joins the reviewed public discovery sources. A dedicated
Playwright/SMTP worker executes only frozen external-action envelopes after an
unexpired approval is bound to the same SHA-256 context digest. PostgreSQL owns
form preflights, action state, approval binding, and a receipt inserted
immediately before the irreversible boundary. Application/email tasks receive
one attempt; replay is refused and post-boundary uncertainty becomes explicit
`ambiguous` state.

The browser is a disposable non-root container without a personal profile,
host mount, Docker socket, or broad URL authority. It resolves routine identity
fields but stops on unknown required answers, CAPTCHA, login, multi-step forms,
and form changes. Email endpoints and senders are deployment configuration, not
task input. A fake ATS and Mailpit profile provide a deterministic no-egress
proof. The dashboard token moved from session storage to page memory.

This is more autonomous preparation, not blanket authorization. Real external
actions still require exact approval; generic browser/MCP access, OAuth email
read, site accounts, and production identity/ingress remain outside this
boundary.

## v0.9 — Governed creator outreach and bounded learning (2026-08-28)

The command center now models KarixMC promotion as durable campaigns, public
creator prospects, exact email stages, reply classifications, suppression, and
attributed placement results. The existing egress research worker can discover
public YouTube channels through the official API with a worker-only restricted
key; it does not discover email addresses. Contact provenance, a written basis,
and operator authorization are required before any plan exists.

Introduction, manual question answer, and one conditional paid-option message
all reuse the exact-action SMTP boundary. The worker revalidates address,
authorization, suppression, and reply state immediately before the receipt, so
a later opt-out cancels an earlier approval. “No/do not contact” and bounces are
durable terminal states; only an explicitly recorded unpaid-only decline can
unlock one final paid draft.

Adaptation is deliberately narrow: two fixed truthful introductions use balanced
assignment until both have ten deliveries. A material positive-reply lead can
shift future drafts to 80/20 exploitation/exploration. Results and suggestions
are evidence-bearing operator aids, not permission for the agent to change code,
policy, contacts, offers, budgets, approvals, or sending authority.

## Next architectural pressure

Per-user OIDC/step-up identity, VPS egress enforcement, reconciliation tooling
for ambiguous provider state, real-ATS compatibility fixtures, scoped inbound
OAuth mail/reply classification, first-party KarixMC attribution import,
encrypted off-host backups, and the policy-bound Hermes adapter are next.
