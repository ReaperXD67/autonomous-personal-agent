# ADR-0033 — Actual SMTP pacing and durable pre-receipt deferral

- Date: 2026-11-02
- Status: Accepted
- Extends and corrects: ADR-0020's reservation-only execution check

## Context

Seventeen actual SMTP acceptances occurred from 05:18:23 through 05:19:39 UTC
after worker recovery despite spaced reserved times. The receipt boundary only
required that a reservation was no longer in the future. Multiple overdue slots
could therefore run together, violating configured spacing and the hourly bound.
The preceding 1,216-test/full-verifier checkpoint did not exercise this case.

Durable reservation remains useful for approval capacity and visible release
times, but it does not establish actual execution cadence. The correction must
apply to all paced email, including creator and career messages, without
rewriting approved copy, extending authority or retrying a completed side effect.

## Decision

Use the same global PostgreSQL advisory transaction gate for approval reservation
and `begin_side_effect`. Acquire it after the operation's own task/action/schedule
and any relevant creator locks; do not lock another task or action under it.
Read wall-clock time again after blocking locks. Keep completion outside this
advisory gate to avoid inverse lock ordering.

Approval considers future reservations plus conservative actual receipt/schedule
start and completion evidence. The receipt boundary honors its own reservation
but does not serialize against other unstarted future reservations. It instead
uses actual accepted/ambiguous history, with the latest applicable durable
scheduled/start/completed timestamp, and treats in-flight sending as unresolved.
An unresolved sending receipt always defers further egress until durable
resolution; it is not an available slot just because a lease or old reservation
has elapsed. Keep the rolling 24-hour history and derive global/domain gaps and
hourly/daily bounds from it.

Apply the stricter of the frozen and current policies: larger global/domain
intervals and jitter, smaller hourly/daily caps. Anchor deterministic jitter to
an actual constraint rather than repeatedly adding jitter to each new wall-clock
check. A missed reservation never creates permission for a recovery burst.

When a safe time is later, commit a pre-receipt deferral of the same task: update
its schedule and `next_attempt_at`, requeue it through the existing outbox,
clear its lease, refund the claim attempt and append `email.pacing_deferred`.
Retain the action ID, exact approval hash, complete body and existing expiry.
Create no receipt and submit no email. The dedicated worker outcome leaves the
action approved/queued instead of reporting task success or failure; ordinary
cleanup closes any SMTP connection. Do not occupy a worker with a pacing sleep.

If no safe time fits before the existing approval expires, refuse before creating
a receipt or deferral. Do not extend the packet, replace the message or infer
permission to replay. Receipt idempotency, uncertainty handling, suppression,
context, cancellation and lease fences remain unchanged. Mailpit fixtures remain
immediate. Reuse current tables/services and policy; add no dependency, migration,
provider scope or inference change.

## Consequences and verification

Approval-time release is a lower bound, not a delivery promise. Recovery or a
slow unresolved SMTP operation can move the next attempt later or leave no valid
window. Inspect actual task/receipt state: an action labeled queued can still
have a dead-lettered task. A confirmed zero-receipt blocked task is distinct
from an uncertain post-boundary outcome and is not automatically replaced.

The rebuilt stack passed lint/all 1,226 tests and the complete verifier.
Disposable PostgreSQL proof covered concurrent overdue attempts (one receipt,
one deferral), old unresolved sending, actual completion/ambiguous boundaries,
stricter frozen/current policy, unchanged content/expiry and refunded attempts,
approval after actual acceptance, insufficient remaining time, and lease or
approval expiry while waiting on the shared advisory gate. The journal and
Experiment 41 record the measured scope. This is local synthetic proof of the
deployed correction, not a new external SMTP pacing canary. No pacing test
establishes inbox placement, creator interest, provider approval or a general
response-rate improvement.
