# ADR-0045: Defer one reply without clearing review or held contacts

Status: Accepted

Date: 2026-11-11

## Context

One complete commercial-policy reply can remain pending because the existing
semantic categories do not accurately describe it. The owner may want a finite
set of new introductions to proceed while explicitly retaining that conversation
and other contact holds. Clearing review, inventing a classification, changing
campaigns or bypassing the final pending-reply guard would misrepresent authority.

## Decision

Add one authenticated, audited owner-deferral record in PostgreSQL. Creation
requires the current complete reply digest, an explicit confirmation, actor,
reason, idempotency key, one to three new prospect IDs and a deadline of one to
24 hours. Bind the source conversation identity, target identity/contact hashes,
campaign hash and stop epoch, and current mailbox/label context. Require one
matched pending reply and preserve its evidence, review state and contact grants.

Only newly prepared, individually reviewed AI initial packets for the named
targets can freeze the deferral ID and scope hash. Validate the exact record at
preparation, ordinary approval and the locked final receipt, including after
pacing waits. Replacing a deferral does not revive an earlier packet. A changed
digest/context, new pending reply, revoked/expired record, held/source identity,
missing genuine AI provenance or prior conversation refuses the exception.
Stop/epoch, sender, source freshness, suppression, duplicate, budget and pacing
checks remain independent. Templates, delegated runs and handoffs get no deferral.

Use the existing campaign transaction boundary to serialize authority changes
with final execution. Avoid adding a reply-row lock beneath existing prospect/
campaign locks. Database integration tests must exercise expiry and revocation
after waits rather than treating an earlier successful lookup as lasting proof.

## Research and alternatives

Reviewed on November 11: PostgreSQL 17's
[explicit locking documentation](https://www.postgresql.org/docs/17/explicit-locking.html)
and Temporal's maintained
[approval pattern](https://github.com/temporalio/documentation/blob/bb58f40ea3dfff8908e3b801242af768af51befd/docs/design-patterns/approval.mdx).
Temporal preserves decision metadata and timeouts durably; its Python SDK is
[MIT licensed](https://github.com/temporalio/sdk-python/blob/4733537c4a1d523fa1f0081c18512d895f4f88b8/LICENSE).
The observed upstream HEADs were documentation `bb58f40` and SDK `4733537c`;
the maintained official documentation and repository were reachable at review.
Adding its SDK and workflow service would duplicate Hermes's existing durable
task, audit and approval boundaries for this small exception, so defer that
dependency. Adapt the durable, scoped decision pattern using the existing
PostgreSQL implementation. No upstream code or skill pack is copied.

## Consequences and limits

Migration 032 adds policy state, not an email capability or approval. A model
cannot create or approve its own send through this path. The owner must authorize
the specific deferral; general outreach permission does not imply one. Existing
held contacts and unsent response drafts stay intact, and a semantic review is
still a separate decision. Execution can still fail or expire; no packet is
cloned, rewritten or extended to hide that result. Live deferral use, exact
approval and SMTP acceptance are separate operating evidence.
