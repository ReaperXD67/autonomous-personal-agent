# Component boundaries

## Implemented components

### Control API

Responsibilities: authentication, request validation, correlation IDs, risk
policy, task persistence, approval decisions, transactional outbox writes,
readiness, and minimal Prometheus-format metrics. It does not call LLMs or
arbitrary tools.

### Outbox dispatcher

Reads unpublished PostgreSQL outbox rows, publishes task identities to Redis,
and marks delivery. A crash after publish may duplicate a ready signal; worker
state transition makes that harmless. A crash before publish leaves a durable
row for retry. It also reconciles expired worker leases: unfinished tasks are
requeued until their bounded attempt budget is exhausted, with every outcome
written to the audit trail.

### Worker

Consumes Redis queue, atomically transitions `queued → running` with a durable
lease, executes an
allowlisted handler, and stores result/error plus audit in the same database
transaction. Stale queue messages are discarded when PostgreSQL state is not
`queued`. Current handlers are short; long-running tools still need periodic
heartbeat renewal before they are enabled.

### PostgreSQL + pgvector

Owns durable tasks, approvals, audit events, outbox rows, memory records, and embeddings.
Schema is initialized and upgraded by a one-shot migration service before the
runtime starts. PostgreSQL lifecycle stays independent
from application images, upgrades, and backups.

### Ollama (optional)

The `local-model` profile provides a GPU-backed, internal-only OpenAI-compatible
endpoint. It has no published host port and no access to PostgreSQL or Redis.
The default Qwen3 8B Q4 model is a constrained offline fallback, not the main
reasoning route.

### Redis

Owns transient ready queue and future cache/scheduling signals. Password auth
and AOF reduce accidental loss, but Redis remains non-authoritative.

## Prepared upstream components

### Hermes

Nous Research Hermes Agent is optional orchestrator/brain. Foundation does not
fork or fake its APIs. Release `v2026.8.3` is verified from official repository
and Docker image. Manual approval remains configured; MCP and messaging remain
unprovisioned.

### OmniRoute

OmniRoute is optional OpenAI-compatible model routing gateway. Release `3.8.49`
is verified from official repository and Docker image. Dashboard binds to
loopback, secrets stay in `.env`, and inference key enforcement is enabled.

## Planned components

- scheduler that creates durable tasks before publishing queue messages;
- browser worker with disposable sessions and domain policy;
- email worker split into read/classify, draft, and send permissions;
- coding worker isolated per repository/worktree;
- MCP policy adapter translating registry decisions to runtime grants;
- Telegram and web interfaces calling the control API;
- OpenTelemetry collector and dashboard stack when operational load warrants it.

## Boundary rule

External interfaces may evolve. Adapters must translate upstream contracts into
this project's task, approval, and audit model; upstream tools never receive
direct unrestricted database or host access.
