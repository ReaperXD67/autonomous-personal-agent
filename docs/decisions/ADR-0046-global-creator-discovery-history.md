# ADR-0046: Preserve global creator history during bulk discovery

Status: Accepted

Date: 2026-11-12

Supersedes ADR-0033's bulk-save expiry rule. Explicit research selection and
intentional single-creator refresh keep their existing behavior.

## Context

The active-draft shield covered an unexpired draft/action for the same prospect
UUID. Expired draft-only work, failed attempts, held replies and another
campaign's business-address alias could receive refreshed research or a new row.
Expiry does not release an owner's hold. Suppressing a held contact, reviving a
packet or hardcoding private creator IDs would misrepresent evidence/authority.

## Decision

Before any bulk prospect insert/update, build a transaction-local global history
index using shipped canonical channel, profile and normalized exact email rules.
Link known aliases transitively through the incoming batch, existing prospects and immutable draft
contact/research snapshots, action contact/recipient snapshots, replies, response
drafts, outcomes, delegated actions, reply deferrals and audit-hash-bound issued
draft/pilot reservations. Include known suppression. Any recorded attempt stays
protected after failure, cancellation, success or expiry. Never match names or
guess an address. Current contact selection alone creates no permanent bulk pin.

Acquire existing pilot-budget, draft-budget and creator-automation locks before
the target campaign and its matching prospect rows. Lock those own rows in UUID
order, then one sorted union of existing sender-identity keys. Re-read global
history after waits; skip candidates whose known aliases expanded beyond the
locked union instead of taking out-of-order locks. Do not row-lock another
campaign's prospects, tasks, drafts, actions or replies.

Protected records retain every stored field, contact permission, reply/copy/digest
and deadline; matching new cross-campaign rows are not inserted. Existing
`protected_count`/aggregate audit count preserved or skipped input candidates.
New/unworked identities retain normal discovery and refresh. The old active-only
helper remains unchanged for explicit research eligibility; intentional explicit
refresh can still invalidate a snapshot.

## Consequences and limits

This is evidence preservation, not an opt-out or sending grant. Shared agency
addresses can preserve multiple channels conservatively. Only observed, retained
bindings can match: new unbound addresses/renamed identities cannot be predicted.
Protection is at database save, not exclusion from every official metadata read.
Fresh aliases propagate within the batch without changing a preserved source;
they are not a claim of knowledge before that metadata was observed. Sequential
duplicate inputs retain accurate insert/update counts and profile ownership.

Reads scale with retained creator history and the incoming batch. No schema,
service, package, provider, account, schedule, quota, model or SMTP-policy change
is added. No private identities or message content enter the aggregate audit.
The source's age is neither extended nor certified.

Required proofs cover expired/failed/withdrawn history, global aliases, frozen old
recipients, old issued reservations, replies/suppression, real draft/sender waits,
expanded-key refusal, new leads and unchanged explicit invalidation. See the
[upstream comparison](../research/creator-discovery-history-2026-11.md).
