# Architecture overview

## Goals

Foundation favors explicit boundaries over premature features:

1. every task has durable identity and state;
2. high-impact execution cannot bypass human approval;
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
The dedicated career worker implements allowlisted fresh discovery, verified
free-only hosted drafting with local fallback, and official YouTube creator
discovery while using the
same lifecycle, policy, and audit model. YouTube tasks carry only campaign IDs;
the restricted API key exists only in this egress-enabled worker.
The isolated action worker handles reviewed browser and email side effects only
after an exact approval digest has entered the durable queue.

### Data plane

PostgreSQL is system of record for tasks, approvals, audit events, memory, and
embeddings, plus career profiles, opportunities, and drafts. Redis carries
reconstructible ready queues and future cache state.
Losing Redis may delay work but must not erase authoritative history.
External-action envelopes, form preflights, and side-effect receipts also live
in PostgreSQL so approval and duplicate prevention survive a crash.
Inference invocations retain requested/selected route, token, latency, privacy,
fallback, status, and cost metadata but never prompt or output text.
Creator campaigns, channel prospects, public-contact provenance, durable
suppression, outreach/action links, reply classifications, and attributed
results use the same authority.

### Agent and model plane

Hermes is the optional agent brain. OmniRoute is its general model gateway. Both run in
an optional profile, use official pinned images, and remain outside the default
trusted core.
Hermes can reach OmniRoute on isolated `model` network but cannot reach
PostgreSQL or Redis directly.

Inference pools are purpose-partitioned. Deterministic discovery, filtering,
and scoring spend no tokens. Hermes uses OmniRoute `free/default`, with internal
Qwen as a provider-failure fallback. Career drafts alone may consume the direct
OpenRouter strict-free pool, ordered by opportunity score/freshness and bounded
by PostgreSQL. The same OpenRouter account is not intentionally configured in
OmniRoute because those two consumers cannot share one authoritative local cap.

The career worker has a separate, narrow OpenRouter adapter because it can
enforce exact live-catalog `:free` and zero-price invariants before résumé data
leaves the host. It requests no-training/zero-retention endpoints, verifies the
actual selected model and returned cost, and falls back to internal Ollama.

### Tool plane

MCP server candidates live in a curated registry. Profiles select capabilities;
permission policy adds risk and approval requirements. No MCP server is enabled
by default during foundation phase.

## Quality attributes

- **Reproducibility:** images and Python dependencies are release-pinned.
- **Least privilege:** loopback ports, internal data network, non-root read-only app images.
- **Auditability:** correlation IDs link request, task, approval, worker, and audit events.
- **Portability:** Compose is shared by Docker Desktop/WSL2 and future Linux VPS.
- **Recoverability:** Redis is reconstructible; checksummed PostgreSQL dumps pass
  a disposable restore drill through application code.
- **Extensibility:** new workers and tools integrate through task/policy boundaries.
