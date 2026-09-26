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

## v0.10 — Attested free hosted inference with local continuity (2026-08-29)

Career drafting can now opt into a narrow OpenRouter adapter without making a
hosted key a core-stack requirement. The worker discovers the current text
catalog, accepts only exact `:free` IDs whose prompt/completion/request prices
are zero, applies a configurable quality order, and gives OpenRouter an explicit
cross-model fallback chain. The actual selected model must remain in that chain
and the completion must report zero cost or its output is rejected.

Résumé privacy changed from an unconditional local-only boundary to an explicit
operator choice. Hosted routing is disabled by default, requests no-training
and zero-retention endpoints, and falls back locally rather than silently
weakening those filters. Only the career worker receives the OpenRouter key.
Hermes continues through OmniRoute; external-action authorization is unchanged.

PostgreSQL now atomically reserves the local hosted-request allowance and owns
route/provider/model, tokens, latency, fallback, privacy, status, and cost
metadata. Prompts, résumés, job text, completions, and keys are absent from that
ledger. Dashboard settings and metrics make the actual route and zero-cost claim
inspectable. The live hosted path remains prepared/unverified until a user-owned
inference key passes the harmless smoke.

## v0.11 — Purpose-aware free-pool allocation (2026-08-29)

Inference is now allocated by purpose instead of treating every free endpoint as
one fungible pool. Deterministic discovery, scoring, and preflight use no LLM.
Hermes' committed primary is OmniRoute `free/default`, with internal Qwen as its
ordered provider-failure fallback. The direct strict-free OpenRouter path stays
exclusive to career drafts so general agent traffic cannot consume its
account-wide allowance outside PostgreSQL's reservation ledger.

Automatic preparation now prioritizes new matches by score and freshness before
spending its bounded draft capacity. The agent doctor inspects current
OmniRoute ownership, enforces the live Hermes primary, verifies the local
fallback shape, and warns about OpenRouter overlap. This preserves the exact
cost/privacy attestation boundary from v0.10 while using the available gateway
pool for general reasoning and the private GPU for continuity.

## v0.12 — Promotion readiness and attribution kit (2026-08-31)

Creator campaigns now expose deterministic, campaign-derived promotion assets
for YouTube descriptions/community posts, Discord, Reddit/community use, and
partner newsletters/blogs. Each asset has a stable first-party UTM URL with a
campaign UUID and content key. Generation is authenticated but read-only,
requires no model/provider, and cannot publish externally.

A single promotion command reports Docker, dashboard, YouTube discovery, SMTP,
and kit readiness without printing secrets. Hidden prompts validate and store a
restricted YouTube key or configure Gmail STARTTLS in ignored `.env`; the same
command can start Docker Desktop, launch the side-effect profile, copy the
private dashboard token, and open the UI. Account creation, Google consent,
provider-side key restrictions, contact/legal review, exact email approval,
inbox delivery proof, and public posting remain user-owned boundaries.

## v0.13 — Creator-specific local proof and test credential isolation (2026-09-05)

Promotion activation now has a dedicated no-egress smoke that creates an
inactive synthetic campaign and authorized synthetic contact, generates all
five attributed assets, prepares and approves one exact creator introduction to
Mailpit, records a synthetic opt-out, proves suppression blocks another plan,
checks campaign metrics, and removes its own durable records.

Mailpit-mode startup now explicitly removes any configured SMTP username and
password before Compose creates the test containers, then restores the caller's
process environment. Promotion readiness distinguishes saved credentials from
the configuration actually loaded by running workers and never treats a healthy
container as proof of real provider delivery. The production authorization
boundary is unchanged: YouTube discovery, contact qualification, each send,
inbox proof, replies, terms, and public placement remain operator-controlled.

## v0.14 — Private VPS release path (2026-09-07)

The first hosted boundary is now explicitly private and single-operator. Linux
commands generate owner-only production secrets, refuse unsafe or dirty Compose
deployments, start the core, prove both queued and approval-gated task paths, and
create/restore checksummed PostgreSQL dumps. Host-header validation and disabled
OpenAPI discovery narrow the web surface. The dashboard and OmniRoute remain
loopback-only and are reached through SSH/WireGuard/Tailscale.

This does not reclassify the product as public production. Host hardening,
encrypted off-host transfer, alerts, provider credentials/proofs, and external
action reconciliation remain deployment-owned. Public ingress still requires
OIDC/RBAC, rate/body limits, TLS, step-up identity, centralized secrets, signed
releases, and incident response.

## v0.15 — Managed model hierarchy and private browser sessions (2026-09-08)

Hermes now receives a deployment-owned ordered route on every start:
OmniRoute `free/default`, OpenRouter `openrouter/free`, then internal Qwen3 8B.
The agent profile supervises an empty Ollama daemon and ensures the model is
cached, but it does not load Qwen weights. The first final-fallback request
loads them, and Ollama unloads them after the configured idle period. Explicit
local-model mode is now a canary that unloads on completion. This preserves the
no-Docker-socket boundary while making the final route available without a
special normal-startup flag.

Dashboard startup no longer places the service bearer token on the clipboard or
inside browser JavaScript. A bearer-authenticated launcher mints a 90-second
one-use fragment, which the same-origin page removes and exchanges for a signed
HttpOnly SameSite session. Cookie-authenticated writes require exact origin and
an HMAC-derived CSRF header. Bearer auth remains for scripts and recovery.

The private VPS lifecycle is now boot managed. Compose restart policies recover
containers, `hermes.service` starts and retries the full stack after Docker, and
a persistent timer checks route order and all three providers every 15 minutes.
This extends private single-operator operability; it does not provide public or
multi-user identity. General Hermes OpenRouter calls also sit outside the career
worker's PostgreSQL quota ledger, so inference-only provider limits and external
account monitoring remain deployment requirements.

## v0.16 — Bounded durable workflow coordination (2026-09-09)

The existing dispatcher now coordinates immutable PostgreSQL dependency graphs.
Ready steps enter the existing policy/task/audit/outbox transaction; the agent
does not gain a second execution channel. A plan permits at most 32 steps, four
task slots, and one day. Exact top-level result checks distinguish successful
execution from expected evidence. Failed dependencies skip descendants while
independent branches finish. Cancellation and deadlines use owned cooperative
task cancellation and remain visibly pending until every child is terminal.

Workflow-managed career handlers suppress implicit preparation/action children,
so their bounded plan does not expand into hidden tasks. Raw external send and
submit are excluded; future model-generated plans must use the same immutable
API and approval boundaries. The Hermes adapter, dynamic replanning, safe memory
retrieval, and general-purpose scheduling remain future work.

PostgreSQL also reconstructs stale queued signals after Redis loss or a
pre-claim worker crash. Outbox generations fence old acknowledgments and
expired workers cannot revive a lease or persist a failure. No new service,
dependency, host access, model route, or external authority was introduced.

## v0.17 — Policy-aware model ranking and semantic failover (2026-09-10)

The governed career OpenRouter adapter now builds its order from current
zero-cost text catalog entries and, under the default privacy mode, the live
active-ZDR endpoint inventory. An explicit operator order still wins; otherwise
bounded intelligence/coding/agentic benchmark metadata determines quality, with
declared capabilities and context as tie-breakers. Benchmark data changes order
only and cannot override price, privacy, selected-model, or returned-cost checks.

OpenRouter's current API allows one primary plus three fallback models, so every
wire request is capped at four routes even if an older environment requests a
larger discovery pool. HTTP 200 is no longer treated as sufficient model
success: empty or application-schema-invalid output records a failed reserved
attempt, cools that route for 15 minutes, and tries the next ranked model under
a separate daily reservation. Exhausted or policy-incompatible hosted routes
still end at local Qwen.

The interactive provider hierarchy is unchanged: OmniRoute `free/default`,
OpenRouter's capability-filtered free router, then lazy local Qwen. This avoids
fabricating a cross-provider benchmark where OmniRoute exposes no equivalent
quality telemetry, and avoids the pinned `auto/*:free` fail-open cost behavior.
No new service, key scope, tool authority, database schema, or host access was
introduced.

## v0.18 — Reviewed goal proposals and usable local evidence (2026-09-11)

The existing research worker now prepares model-authored goal proposals through
the policy/task/audit/outbox and inference-ledger paths. A server-owned inventory
limits the model to opaque action keys from explicitly selected context. The
compiler fixes payloads and sequential dependencies, and reviewed digest-bound
adoption creates the immutable workflow and proposal link atomically. Owned
leases fence stale proposal writes. The fixed local demo is visibly a template.
No generic tools, raw send/submit, new service, dependency, or host authority are
introduced. Dynamic replanning and the Hermes control-plane adapter remain future work.

Career and creator schedules now advance in the same PostgreSQL transaction as
their task, audit, and outbox creation. Rollback preserves due work and locked
rows serialize concurrent schedulers. This closes the pre-task crash gap.

The dashboard now guides an operator from a next action to goals, reviewed plans,
features, and results. Historical feature-test metadata is stored in PostgreSQL
through a bearer-only endpoint, rather than a host-mounted report directory.
Browser sessions can read scopes/prerequisites/evidence but cannot attest tests.
Readiness proof expires after 24 hours and distinguishes fixtures from external
deployment proof. The project remains a private local alpha with bounded autonomy.

## v0.19 — Reviewed creator delivery and honest SMTP evidence (2026-09-12)

The existing action worker now checks SMTP connectivity through a fixed-config,
medium-risk, single-attempt task with normal policy/audit/outbox dispatch. It
returns timestamped TLS/authentication evidence without sending mail. A local
setup command writes SMTP fields atomically and keeps secrets out of the UI.

The final external-action boundary now rechecks current lease ownership,
cancellation, expiry after lock waits, frozen contexts, and contact authority.
Connection failures precede receipt creation; confirmed SMTP acceptance is
committed before cleanup and is preserved through later task failure. Uncertain
external state still needs reconciliation; exactly-once SMTP is not claimed.

Creator introductions can use explicit personal copy with the existing exact
review, sequence, suppression, and footer rules. Manual copy is excluded from
template A/B learning. The dashboard links historical exact messages, places
approval inside full-packet review, and distinguishes mail-server acceptance
from inbox delivery. No service, schema, dependency, model route, or host access
was added; this remains a bounded private local alpha.

## v0.20 — Durable low-volume email release (2026-09-16)

Exact email approval now also reserves a PostgreSQL release time under a
serialized transaction. The schedule applies global and same-recipient-domain
spacing, rolling hourly and daily caps, and deterministic jitter. The task and
outbox inherit that time, while the action worker requires the due reservation
at the final side-effect boundary. Cancellation and pre-boundary failure release
unused capacity; acceptance and uncertain handoff remain counted. Recovery
cannot collapse approved messages into a burst.

External SMTP defaults to 15 minutes globally, 30 minutes for the same domain,
three messages per rolling hour, and twelve per rolling day. Mailpit remains
immediate. The dashboard exposes the active policy and each future release time.
Messages now carry an RFC 5322 date and sender-domain message ID, and SMTP
receives the exact approved envelope sender/recipient.

This is a reputation and abuse boundary, not a delivery promise. SPF, DKIM,
DMARC, sender alignment, domain/IP reputation, complaints, bounces, recipient
relevance, and working unsubscribe processes remain deployment/provider work.
Hermes remains a one-to-one approval-gated outreach tool, not a bulk mailer.

## v0.21 — Evidence-backed YouTube research (2026-09-19)

The research worker now derives bounded business-contact candidates from public
official-API channel/video descriptions, with source excerpts and timestamps.
PostgreSQL stores an additive research dossier alongside each prospect, including
fit factors, observed content, creative concepts, a suggested opening line, and
explicit gaps. Campaign scans and per-prospect refresh use the existing policy,
task, audit, and discovery budget. No new model route or service is introduced.

Candidate discovery is separated from recipient authorization. The dashboard
focuses new research on YouTube and offers search, contact filters, source review,
and formula-safe CSV export. Selecting a candidate pre-fills an unchecked review
form; exact-send approval, suppression, and pacing retain their authority.
Source descriptions never instruct tools. Real research exports remain local
and ignored. See ADR-0021 for limits and the engineering journal for validation.

## Next architectural pressure

Live OpenRouter onboarding/fallback proof, per-user OIDC/step-up identity, VPS egress enforcement, reconciliation tooling
for ambiguous provider state, real-ATS compatibility fixtures, scoped inbound
OAuth mail/reply classification, first-party KarixMC attribution import,
encrypted off-host backups, and the policy-bound Hermes adapter are next.


## 2026-09-23 - Scoped career delegation, reply tracking and creator geography

ADR-0022 adds expiring Play grants to the existing exact-action path. PostgreSQL
owns scope, per-run preparation, shared rolling application reservations and
per-profile normalized target deduplication. The research scheduler creates
ordinary classified tasks; exact approvals are attributed to the grant. The
isolated action worker rechecks the grant before acquiring a side-effect receipt.
Pause/profile changes/expiry block new receipt acquisition, while ambiguous
remote outcomes retain their reservation. Hiring emails require explicit job
contact evidence and run-bound draft provenance, and share the same application
cap. SMTP credentials were not added to the research worker.

Gmail read-only OAuth is confined to the research worker and a selected label;
bounded metadata/cursors and sourced application events live in PostgreSQL.
Configured tracking continues for recent applications after Play expires.
No calendar booking or autonomous mail reply is implied. Remotive is opt-in with
shared request reservations; update timestamps do not qualify as posting dates.
YouTube campaigns gain independent country/language rules, declared metadata
provenance, strict unknown exclusion, current-criteria projection and a stale-scan
fence. Neither discovery nor geography grants contact authorization.

## 2026-09-26 — Bounded creator expansion and complete exports

ADR-0023 introduces an authoritative per-request YouTube search ledger with
cross-campaign rolling and per-task limits. Campaigns select up to three pages
per query; partial provider outcomes and search coverage are retained. Research
still enters the existing policy, task, audit and cancellation path.

Complete authenticated CSV exports use a read-only PostgreSQL snapshot and
bounded cursor batches, independent of the paged dashboard. Coverage counts
distinguish declared eligibility, unknown country, public contact availability,
authorization, suppression and evidence needing refresh. Strict targeting now
also applies to empty legacy dossiers. No contact grant, inference route, runtime
service or outbound messaging authority changes.

## 2026-09-26 — Career preparation and progress correction

Preparation allowance is separated from the durable application reservation
budget. PostgreSQL retains a per-profile daily preparation bound across Play
runs and a smaller per-run bound, including failed preparation. Existing profile
locking serializes reservations. The selected application cap remains unchanged.
Migration 019 adds an exact-action foreign key to prepared items and backfills
only known authorization links. Progress can follow preparation-only packets
through later manual action outcomes without inferring an approval or a match.

## 2026-09-26 — Creator contact source continuity

ADR-0024 adds bounded, dated source history within existing PostgreSQL dossiers.
Row locks preserve observations through concurrent refreshes; matching uses the
same canonical channel plus email/source pair. Historical evidence remains
separate from current candidates, expires after 30 days and has a persisted
deadline for bounded worker housekeeping. Reads exclude expired history at once.
No new external capability, provider, model route or outreach grant is introduced.
