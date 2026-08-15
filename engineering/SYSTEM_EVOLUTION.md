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

## Next architectural pressure

Per-user identity, rate limits, correlated telemetry, encrypted off-host backup
automation, and a policy-bound Hermes adapter remain the production/readiness
priorities.
