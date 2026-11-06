# ADR-0042: Reserve an explicit creator research shortlist

Status: Accepted

Date: 2026-11-06

## Context

The existing bounded pilot endpoint rotates its own saved candidate pool. An
operator may already have reviewed one promising creator while other high-ranked
records are excluded from the current outreach cycle. Refreshing a larger batch
just to reach that creator spends research allowance and can touch evidence the
operator intended to preserve. A targeted provider call outside the control
plane would bypass the issued reservation and audit boundary.

## Decision

Add optional distinct `prospect_ids` to the existing pilot-research request.
Their count supplies an omitted limit; an explicit limit must match. Preserve
the existing automatic selector when IDs are omitted. Explicit requests reserve
exactly their ordered identities or refuse the whole selection. Replays bind
that same selection, actor and campaign through the existing idempotency and
canonical payload audit.

Targets must be saved, uncontacted, unsuppressed YouTube Minecraft candidates in
the selected campaign. Cross-campaign canonical channel/profile and known email
matches protect conversations, active draft/packet evidence and issued research
or draft reservations. Reuse the draft-budget lock and existing protection
helpers, with checks at creation, execution checkpoints and save. Fresh contact
observations are checked before persistence as well. Researching stale evidence
does not require prior contact authorization or an already-fresh sample.

The existing ten-creator cap, thirty-creator rolling allowance, failed/cancelled
reservation accounting, lease, campaign snapshot, three-upload bound and native
four-request research path remain. No generic task payload, manual provider
call, template send or additional account authority is introduced.

## Consequences

Operators can refresh a small reviewed selection without padding a batch or
repeating discovery. HTTP 409 requires reviewing current state; no creator is
silently substituted and no allowance is reset. A completed research task still
requires fresh Minecraft evidence, business-contact review, contact authorization,
an exact draft review and normal approval before email. Published metadata and
research completion do not establish interest or guarantee a reply.

The dashboard continues using automatic selection. No new service, dependency,
database schema, inference route or SMTP setting is needed. This extends the
bounded research operation described in [ADR-0041](ADR-0041-recent-creator-evidence.md).
