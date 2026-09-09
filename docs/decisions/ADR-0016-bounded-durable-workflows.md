# ADR-0016: Bounded durable workflows in the existing dispatcher

- Date: 2026-09-09
- Status: Accepted

## Context

Single tasks already have policy-derived risk, approvals, audit, owned leases,
and bounded recovery. Multi-step coordination needs those same guarantees and
must not introduce an agent-controlled execution or approval bypass. Published
ready signals can also disappear before a durable claim, stranding queued tasks.

## Decision

Store immutable bounded DAG plans and step bindings in PostgreSQL. Reconcile
them in the existing dispatcher under workflow row locks using `SKIP LOCKED`.
Create each ready task through `_create_task_record` in the same transaction as
the step binding and audit. Reuse existing workers and queues. Add no service,
runtime, provider, host access, or dependency.

Limit plans to 32 steps, four simultaneous task slots, and one day. Allow only
existing research/preparation/foundation capabilities. Suppress their implicit
career child tasks when workflow-managed. Preserve policy risk escalation and
manual decisions, and exclude raw email/send and application/submit. Compare
explicit top-level scalar output evidence; never execute result expressions or
interpolate future payloads. Propagate failed dependencies while allowing
independent branches to finish. Cancellation/deadlines stop dispatch and use
the existing cooperative child cancellation path.

Make ready signals reconstructible by rearming old published outbox records
for due queued tasks. Version each rearmed delivery and require matching
generations for publication success/failure. Refuse expired lease renewal and
failure writes. PostgreSQL task state remains the execution authority.

## Consequences

Concurrency, restart, rollback, and failure behavior can be tested with harmless
synthetic tasks and real PostgreSQL, without model inference. Static plans do
not provide general intelligence, automatic replanning, or dynamic dataflow.
The Hermes model-to-control-plane adapter remains future work. External actions
still require their exact envelope and individual approval outside workflows.
Existing task attempts remain the retry budget; a deadline requests interruption
and cannot forcibly undo a completed handler or in-flight external request.
