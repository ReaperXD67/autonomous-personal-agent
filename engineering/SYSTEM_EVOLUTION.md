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

## Next architectural pressure

Long-running capabilities need periodic lease heartbeats, cancellation, delayed
backoff, and dead-letter inspection. Model routing needs verified usage/cost
metadata. Hermes must create control-plane tasks instead of calling high-impact
tools directly.
