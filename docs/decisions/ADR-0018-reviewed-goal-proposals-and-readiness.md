# ADR-0018: Reviewed goal proposals and recorded feature readiness

- Status: Accepted
- Date: 2026-09-11
- Extends: ADR-0016 bounded durable workflows; ADR-0017 model routing

## Context

Users need an understandable path from an outcome to existing capabilities.
An unconstrained model tool loop would weaken the reviewed execution boundary,
while container health cannot tell an operator which feature has been proven.
Career and creator schedulers also advanced their next occurrence before task
creation, leaving a crash window that could skip a due scan.

## Decision

Add `planning.propose` as a medium-risk capability executed by the existing
research worker through policy, task, audit, outbox, and owned lease handling.
PostgreSQL stores the selected context, server-generated action inventory,
proposal, digest, expiry, and adoption link. The model sees only the supplied
goal and opaque action descriptions. It cannot invent task payloads, IDs,
dependencies, tools, or recipients. Schema validation compiles at most eight
sequential steps from that inventory. Hosted inference reuses the strict-free
ledger/failover; local mode uses the existing Ollama network and model. An
explicit fixed demo is labeled as a template and never masquerades as inference.

The operator reviews the proposal and submits its digest. Adoption locks the
task then proposal, checks successful completion/expiry/current context, and
creates the immutable workflow and adoption link in one transaction. Retried
adoption returns the existing workflow. Planning cannot send email, submit an
application, or recursively plan; workflow children retain all existing controls.

Expose feature prerequisites and historical operator test evidence in the same
private dashboard. A bearer-only endpoint accepts a strictly allowlisted report
with no arbitrary logs or user content and persists it in PostgreSQL. Browser
sessions can read evidence but cannot assert a test run. A verified label expires
after 24 hours; fixture and real-service scopes remain explicit. This is operator
attestation, not a signed build certificate or continuous liveness measurement.

Career and creator scheduling now select due rows with `FOR UPDATE SKIP LOCKED`,
create policy/task/audit/outbox records, and advance the schedule in one bounded
batch transaction. Failure preserves the due occurrence; conflicting idempotency
keys cannot consume it. No service, dependency, privileged mount, or external
authority is added.

## Consequences

The product gains reviewed goal translation, guided navigation, reproducible
readiness evidence, and crash-safe recurring scans. It remains a bounded local
agent, not AGI, a general executor, or autonomous self-improvement. Dynamic
replanning, unselected new context, general memory retrieval, generic MCP and
coding, multi-user identity, real SMTP proof, and broad ATS compatibility remain
separate work. A model can still misinterpret intent, so proposal review is
necessary even when its executable actions are constrained correctly.
