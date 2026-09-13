# ADR-0019: SMTP acceptance and connection evidence

Date: 2026-09-12
Status: Accepted
Supersedes: the SMTP failure/cleanup details of ADR-0010; exact approval remains required

## Context

The first live-creator preparation exposed gaps between SMTP setup failures,
uncertain submission, known acceptance, and task completion. A receipt written
before connection/authentication could imply a possible send when no message was
submitted. Cleanup failures could erase known acceptance. The final submission
guard did not recheck the worker's current lease or cancellation request.

## Decision

Keep the existing action worker and PostgreSQL authority. Connect, verify TLS,
and authenticate before acquiring the final side-effect receipt. Immediately
before submission, validate current lease ownership, cancellation, expiry after
lock waits, exact frozen contexts, and contact authority. Commit SMTP acceptance
before best-effort cleanup. Preserve succeeded receipts/actions even if later
task completion fails; fence stale workers from failure writes.

Add `communications.smtp_check` as a medium-risk, single-attempt allowlisted task
with an empty payload, fixed deployment configuration, and ordinary audit/outbox
dispatch. It performs connection/TLS/authentication and NOOP without submitting
mail. Private API and UI expose timestamped allowlisted evidence, never provider
credentials or raw protocol responses. Configure an existing provider through
local hidden prompts with atomic, literal-safe dotenv writes.

Allow explicitly authored initial creator copy under the same exact approval
and sequence rules. Preserve the contact/privacy/opt-out footer and exclude the
`manual_initial` variant from template A/B selection. Paid-offer terms remain
campaign-bound. Exact message lookup makes older reviewed actions inspectable.

## Consequences

No new runtime, dependency, schema, host mount, or provider authority is added.
SMTP acceptance proves the provider accepted a message, not inbox delivery or
reading. A crash between external acceptance and its database commit can still
leave uncertain state; SMTP cannot provide exactly-once delivery here. Operators
must reconcile uncertain sends before preparing another message. Connection
checks are historical evidence for the worker's configuration at that time.
