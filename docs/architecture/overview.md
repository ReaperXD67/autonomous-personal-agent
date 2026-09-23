# Architecture overview

## Goals

Foundation favors explicit boundaries over premature features:

1. every task has durable identity and state;
2. high-impact execution requires exact approval or explicit bounded delegation;
3. transient queues cannot become authoritative memory;
4. upstream agent/model products remain replaceable;
5. tools are granted per-agent, not globally;
6. local Docker behavior maps cleanly to a single-host KVM VPS.

## Planes

### Control plane

Control API accepts authenticated requests, classifies risk, and atomically
creates durable task, audit, and outbox records for eligible work. It does not
execute tools.

### Execution plane

The outbox dispatcher reliably bridges durable PostgreSQL intent to Redis.
Workers claim queue messages and perform allowlisted capabilities. The
foundation worker implements `foundation.echo` and bounded `foundation.wait`.
The dispatcher also reconciles immutable workflow dependency graphs in
PostgreSQL. Ready steps become ordinary policy-classified tasks in the same
transaction as their step binding and audit; it executes no tools itself.
Result checks, concurrency limits, cancellation, and deadlines govern further
dispatch. Published queue signals can be reconstructed from durable queued
tasks; delivery generations fence stale acknowledgments.
The dedicated career worker implements allowlisted fresh discovery, verified
free-only hosted drafting with local fallback, and official YouTube creator
discovery while using the
same lifecycle, policy, and audit model. YouTube tasks carry only campaign IDs;
the restricted API key exists only in this egress-enabled worker.
The isolated action worker handles reviewed browser and email side effects only
after an exact approval digest has entered the durable queue.
Career Play grants can authorize those exact digests within a frozen, expiring
scope. PostgreSQL stores the grant, preparation records, rolling budget and
normalized application target ledger. The action worker rechecks the grant at
the receipt boundary. See [ADR-0022](../decisions/ADR-0022-scoped-career-autopilot-and-reply-tracking.md).
Gmail reply tracking runs in the research worker with read-only OAuth and a
selected label. Only that worker receives Gmail refresh credentials. Career
email preparation receives sender metadata and pacing policy; SMTP credentials
remain in the existing control/action boundary, not the research worker.

### Data plane

PostgreSQL is system of record for tasks, approvals, audit events, memory, and
embeddings, plus career profiles, opportunities, and drafts. Redis carries
reconstructible ready queues and future cache state.
Losing Redis may delay work but must not erase authoritative history.
External-action envelopes, form preflights, and side-effect receipts also live
in PostgreSQL so approval and duplicate prevention survive a crash.
External SMTP approvals also reserve durable send slots with rolling volume
limits, same-domain spacing, and jitter, preventing queue or VPS recovery bursts.
Inference invocations retain requested/selected route, token, latency, privacy,
fallback, status, and cost metadata but never prompt or output text.
Creator campaigns, channel prospects, public-contact provenance, durable
suppression, outreach/action links, reply classifications, and attributed
results use the same authority.
YouTube prospects also retain bounded research dossiers in PostgreSQL: public
business-contact candidates, source evidence, explained fit, creative ideas,
and gaps. Candidates never update recipient authorization. Campaign scans and
single-prospect refresh use the existing discovery task and worker budget.

### Agent and model plane

Hermes is the agent brain. OmniRoute is its primary model gateway. They run in
the `agent` profile, use official pinned images, and remain outside the trusted
control/data core.
Hermes can reach OmniRoute on isolated `model` network but cannot reach
PostgreSQL or Redis directly.

Deterministic discovery, filtering, and scoring spend no tokens. Hermes uses an
ordered OmniRoute `free/default` → OpenRouter `openrouter/free` → internal Qwen
chain. The Ollama daemon is supervised, but Qwen weights load only at the final
fallback and expire after idle time. Career drafts also have a narrow direct
OpenRouter strict-free path ordered by opportunity score/freshness and bounded
by PostgreSQL. General Hermes fallback calls are outside that ledger and must be
bounded by the provider-side key policy.

The career worker has a separate, narrow OpenRouter adapter because it can
enforce exact live-catalog `:free` and zero-price invariants before résumé data
leaves the host. It intersects the catalog with active zero-retention endpoints,
ranks the remaining candidates by bounded live benchmark metadata and declared
capabilities, and sends one primary plus at most three provider-supported
fallbacks. It requests no-training/zero-retention endpoints, verifies the actual
selected model and returned cost, and validates the task schema. Empty or
invalid structured output cools that route and receives a separately reserved
attempt through the next ranked model before internal Ollama.

### Tool plane

MCP server candidates live in a curated registry. Profiles select capabilities;
permission policy adds risk and approval requirements. No MCP server is enabled
by default during foundation phase.

## Reviewed proposals and feature evidence

The research worker handles `planning.propose` under a medium-risk allowlisted
capability. PostgreSQL stores selected context and a server-generated inventory.
The model selects opaque actions only; deterministic compilation fixes kinds,
payloads, dependencies, and checks. A successful proposal does not execute its
children. Digest-bound operator adoption creates the immutable workflow and its
proposal link atomically, after revalidating current context. The existing
OpenRouter/Ollama path and ledger account for planner inference too.

The private API also stores strictly bounded operator feature-test metadata in
PostgreSQL. Browser clients read prerequisites, scopes, and evidence timestamps;
only bearer-authenticated operator scripts can publish reports. No runtime host
directory is mounted into the API. Report booleans describe the last test, and
verification labels become stale after 24 hours.

Career and creator scheduler transactions now include both schedule advancement
and task/policy/audit/outbox creation. Rollback leaves the occurrence due; locked
rows prevent duplicate issuance by concurrent scheduler workers.

## Quality attributes

The action worker also handles the fixed-config, medium-risk, single-attempt
`communications.smtp_check` diagnostic through the existing task/outbox path.
It sends no email and returns only transport/TLS/authentication evidence.
External actions revalidate owned leases, cancellation, frozen context, and
contact authority at the submission boundary. SMTP acceptance is committed
before best-effort cleanup and cannot be downgraded by a later task failure.
The approval transaction reserves an external-SMTP release time and the worker
rechecks it before the receipt. Mailpit remains immediate. No new service,
dependency, or host authority is introduced.

- **Reproducibility:** images and Python dependencies are release-pinned.
- **Least privilege:** loopback ports, internal data network, non-root read-only app images.
- **Auditability:** correlation IDs link request, task, approval, worker, and audit events.
- **Portability:** Compose is shared by Docker Desktop/WSL2 and future Linux VPS.
- **Recoverability:** Redis is reconstructible; checksummed PostgreSQL dumps pass
  a disposable restore drill through application code.
- **Extensibility:** new workers and tools integrate through task/policy boundaries.
