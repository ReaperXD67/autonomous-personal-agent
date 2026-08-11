# ADR-0004: Durable approval before high-impact queue publication

- Status: Accepted
- Date: 2026-08-11

## Context

An autonomous worker must not receive a high-impact task and then decide whether
approval existed. Queue replay and process failure make in-memory checks unsafe.

## Decision

Persist task as `pending_approval`. Record approval/rejection in PostgreSQL.
Approval atomically transitions to `queued`, appends the audit event, and writes
a transactional outbox row. A dispatcher publishes the task ID to Redis and
marks the outbox row. Worker atomically accepts only `queued` state. Every task
transition and its correlation-linked, redacted audit event share a transaction.

## Alternatives

- Prompt the user inside worker: ambiguous during retries/disconnects.
- Queue all tasks with an approval flag: leaks high-impact work into execution plane.
- Store approval only in Redis: non-authoritative and vulnerable to eviction/loss.

## Consequences

Approval is traceable and replay-resistant at state-transition level. Queue
delivery is at least once, while PostgreSQL state makes duplicate signals safe.
Future work must add approver identity/MFA, action context hashes, expiry, and
minimum risk derived from tool metadata.
