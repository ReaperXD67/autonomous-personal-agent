# Component boundaries

## Implemented components

### Control API

Responsibilities: authentication, request validation, correlation IDs, risk
policy, task persistence, approval decisions, transactional outbox writes,
career mission/opportunity APIs, the same-origin private dashboard, readiness,
and minimal Prometheus-format metrics. It does not call LLMs or arbitrary tools.
OpenAPI discovery is disabled and Starlette validates the Host header against
the deployment allowlist. The Linux private-VPS bootstrap fixes that allowlist
to `localhost,127.0.0.1`; public hostnames are outside the current profile.

### Outbox dispatcher

Reads unpublished PostgreSQL outbox rows, publishes task identities to Redis,
and marks delivery. A crash after publish may duplicate a ready signal; worker
state transition makes that harmless. A crash before publish leaves a durable
row for retry. It also reconciles expired worker leases: unfinished tasks are
requeued with exponential delay until their bounded attempt budget is exhausted,
then become inspectable dead letters. Cancellation requests on an abandoned
claim are finalized during the same reconciliation. Every outcome is audited.

### Worker

Consumes Redis queue, atomically transitions `queued → running` with a unique
lease ID and worker identity, executes an allowlisted handler, renews long-task
leases on a bounded heartbeat, and stores result/error plus audit in the same
database transaction. A stale worker cannot complete a lease it no longer owns.
Cancellation is cooperative while running and immediate before claim. Stale
queue messages are discarded when PostgreSQL state is not `queued`.

### Career worker

Consumes a separate career-ready queue but claims the same durable tasks and
leases. It schedules due active profiles through the control-plane database
policy/outbox path, reads only reviewed public Arbeitnow/Ashby/Greenhouse/Lever APIs,
scores fresh listings deterministically, and persists opportunities. Draft tasks
prefer a live-ranked OpenRouter chain only after every candidate passes exact
`:free`, text-modality, and zero-price catalog checks. Requests use ordered
cross-model fallback plus no-training/ZDR provider filters; the returned model
and zero cost are revalidated. On quota, privacy-filter, malformed-output, or
availability failure, the worker sends the selected job plus stored résumé to
internal Ollama. It has outbound edge, data, and model networks but no host
mount, Docker socket, or published port.

New matches are ordered by score and then publication time before the bounded
auto-prepare set is chosen, so hosted free reservations are spent on the
strongest, freshest opportunities rather than source arrival order.

The same bounded egress runtime handles `marketing.creator_discovery`. It calls
only the fixed YouTube Data API host with a deployment-provided restricted key,
bounded queries/results, strict safe search, and response/time limits. It stores
public channel/video evidence but no discovered contact email. Reuse avoids a
new service while lifecycle and network privileges are identical; the API key
is not passed to other application services.

### Action worker

Consumes a separate external-action queue. Playwright runs in a release/digest-
pinned image as the unprivileged `pwuser`, with a read-only root filesystem,
no capabilities, no host/browser-profile mount, no Docker socket, and no
published port. It preflights or submits only reviewed ATS URLs and aborts every
cross-host browser request. SMTP uses deployment-fixed transport settings; task
input cannot select a server or sender. Exact-context approval, expiry, current
résumé/draft hashes, current form signature, and a durable receipt are checked
before a final click or send. Consequential tasks have no automatic retry.

For creator email the worker also locks and revalidates the prospect's public-
contact authorization, exact address, suppression, and reply state immediately
before the receipt. A later opt-out invalidates an earlier approval.
The `side-effects-test` profile replaces the transport with internal Mailpit and
explicitly removes any deployment SMTP username/password from the test
containers before creator or generic side-effect smoke execution.

### PostgreSQL + pgvector

Owns durable tasks, approvals, audit events, outbox rows, career profiles,
opportunities, application drafts, memory records, embeddings, and inference
invocation metadata. Inference rows reserve the local hosted-call budget and
store only route/provider/model, tokens, latency, fallback, privacy, status,
error code, and provider-reported cost—never prompts, résumés, or completions.
Schema is initialized and upgraded by a one-shot migration service before the
runtime starts. PostgreSQL lifecycle stays independent
from application images, upgrades, and backups.

### Ollama / Qwen

The agent profile supervises an internal-only Ollama daemon; `local-model` is an
explicit canary profile, not a normal-startup requirement. The endpoint has no
published host port and no access to PostgreSQL or Redis. Normal startup may
cache the default Qwen3 8B Q4 artifact but does not load its weights. Ollama
loads it only on the first final-fallback request and releases it after the
configured idle period. This avoids Docker-socket access while keeping the
model itself lazy.

### Redis

Owns transient ready queue and future cache/scheduling signals. Password auth
and AOF reduce accidental loss, but Redis remains non-authoritative.

## Optional upstream components

### Hermes

Nous Research Hermes Agent is optional orchestrator/brain. Foundation does not
fork or fake its APIs. Release `v2026.8.3` is verified from official repository
and Docker image. Its routed one-shot inference passed locally. Its reviewed
primary is OmniRoute `free/default`, its second route is OpenRouter
`openrouter/free`, and internal `qwen3:8b` is the last-resort fallback. A
networkless one-shot service renders this committed order into the private
Hermes volume at startup. Manual approval remains configured; MCP and messaging
remain unprovisioned.

### OmniRoute

OmniRoute is optional OpenAI-compatible model routing gateway. Release `3.8.49`
is verified from official repository and Docker image. Dashboard binds to
loopback, secrets stay in `.env`, and inference key enforcement is enabled. Its
authenticated catalog and `free/default` inference path passed locally.
The explicit Hermes OpenRouter fallback can share an account with the direct
career adapter, but general interactive calls are outside the career worker's
PostgreSQL reservation ledger. Provider-side key limits therefore remain
required.

## Planned components

- generic read-only browser tooling behind stronger network egress policy;
- email read/classify and provider OAuth adapters;
- coding worker isolated per repository/worktree;
- MCP policy adapter translating registry decisions to runtime grants;
- Telegram interface calling the control API;
- OpenTelemetry collector and dashboard stack when operational load warrants it.

## Boundary rule

External interfaces may evolve. Adapters must translate upstream contracts into
this project's task, approval, and audit model; upstream tools never receive
direct unrestricted database or host access.
