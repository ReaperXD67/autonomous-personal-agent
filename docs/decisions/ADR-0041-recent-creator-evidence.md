# ADR-0041 — Recent creator discovery and canonical shortlist evidence

Date: 2026-11-06

Status: Accepted

## Context

Relevance-first discovery can repeatedly return old matching samples within a
campaign's configured historical window. The explicit three-upload shortlist
already verifies recent public uploads, but normalization previously ran before
that activity was attached. Its ranking could recognize recent Minecraft
activity while the draft citation and language projection retained an older
sample.

## Decision

Use a recent date-ordered search lane bounded by the smaller of ninety days and
the campaign's publication window. A relevance lane uses the existing campaign
window when the per-query page allowance has capacity. Lanes retain independent
pagination state and share the existing total request cap and PostgreSQL search
reservations. Every query receives its initial recent page before continuation.
A one-page allowance provides recent coverage only.

Revalidate discovery samples against current video metadata before treating them
as current evidence. Partial channel-only records can remain available for review
with their unavailable sample cleared.
Channel identity, public status, upcoming state and actual publication must
agree with the lane's window. Search timestamps alone do not establish these
facts. Coverage and exclusions remain inspectable aggregate evidence.

For explicit recent-activity shortlist research, select the newest qualifying
verified upload whose actual title identifies Minecraft within the smaller of
ninety days and the campaign window. Enrich that selected sample before
normalizing title, URL, publication,
contact provenance and language. Preserve the saved sample when no recent
Minecraft upload qualifies. A contradictory selected-video reread fails research
rather than promoting stale or changed evidence. Contact candidates from that
selected source come from the final reread, so a removed business address cannot
be reintroduced from the earlier uploads response.

Keep the existing provider endpoints, request limits, campaign targeting,
PostgreSQL task/audit path and controlled worker. No new service, dependency,
credential or sending authority is introduced. Approved evidence protection,
exact draft review and owner reply holds continue at their existing boundaries.

## Consequences

Discovery spends part of its existing allowance on recent publications, so it
can inspect fewer relevance continuations. Search and the first three uploads
are bounded samples. Current metadata supports a proposal about an observed
title, while actual content fit and willingness to collaborate remain reviewed.
Previously rendered drafts and approvals are never rewritten by this decision.

See the [primary-source comparison](../research/creator-fresh-evidence-2026-11.md).
