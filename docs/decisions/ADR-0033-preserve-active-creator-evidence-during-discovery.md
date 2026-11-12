# ADR-0033 — Preserve active creator evidence during bulk discovery

- Date: 2026-11-02
- Status: Accepted
- Bulk-save expiry/same-prospect scope superseded by [ADR-0046](ADR-0046-global-creator-discovery-history.md); explicit research behavior remains unchanged.
- Extends: ADR-0021 and ADR-0030

## Context

Creator drafts and exact email packets bind research fields, including observation
time. A scheduled bulk discovery scan could update an already selected creator's
title, publication or observation time behind a ready draft or queued message.
The final research fence would correctly reject the changed context, but routine
background discovery could thereby invalidate work already reviewed for sending.

Ongoing operation also needs a clear separation between native discovery/reply
workers and a scheduled reviewer. The reviewer must retain individual contact,
complete-copy, positive-interest and handoff decisions rather than enabling a
generic template-sending grant.

## Decision

For bulk discovery saves only, inspect protection under the existing campaign
and canonical prospect row locks, after profile and suppression checks. Preserve
the existing research row when either condition holds:

- An unexpired queued/ready draft has a task outside the failed, cancelled,
  rejected and dead-lettered states. A prepared draft additionally needs its
  linked unexpired action in `pending_approval`, `queued`, `executing` or
  `ambiguous` state.
- An independently linked unexpired outreach action is in one of those active
  states, including a manually prepared message.

Do not add locks or writes to task, draft or action rows in this check. New
creators continue to insert, while unprotected existing creators retain normal
bulk refresh behavior. Keep the existing new/updated save result contract;
expose an aggregate `protected_count` in the saved campaign discovery summary and a nonzero
`marketing.discovery_evidence_preserved` audit rather than recording private
creator details in a new ledger.

Expiry and terminal task/action states release that record's protection;
another active protecting record can still preserve the row. Independent action
protection can outlive the original draft's preparation deadline until the
action's own deadline. Do not extend observation timestamps, expiry, approval
authority or send limits. Explicit single-creator refresh remains an intentional
source change and must retain snapshot invalidation. Contact withdrawal,
suppression, campaign edits and final delivery guards remain unchanged.

The continuation uses an hourly reviewer for two privately fixed campaigns,
native daily official discovery and existing eligible five-minute Gmail reads.
At most six new introductions per rolling day combined is an operating scope,
not a new server grant. Existing SMTP/preparation/refresh limits, exact individual
review and PostgreSQL authority remain. No new service, dependency or migration
is introduced.

## Consequences

Routine discovery can find new creators without silently invalidating active
reviewed work. A protected row deliberately retains its reviewed snapshot;
`protected_count` explains why a scan did not replace that evidence. Protection
is not a claim that the source is unchanged, accurate or current forever.

Validation must cover active AI and manual packets, ready/queued drafts,
terminal/expired release, new creator insertion, ownership checks and explicit
refresh invalidation. PostgreSQL lock-wait tests must show that a packet prepared
while discovery waits is protected. The journal and Experiment 41 record actual
combined tests, schedule installation, manual-cycle and delivery results.
