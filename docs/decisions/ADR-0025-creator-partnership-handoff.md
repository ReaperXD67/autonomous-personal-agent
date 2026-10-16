# ADR-0025 — Bounded creator partnerships and owner handoff

- Date: 2026-10-16
- Status: Accepted
- Extends: ADR-0011, ADR-0019, ADR-0020, ADR-0021
- Supersedes: ADR-0011's individual-approval-only rule for the narrowly delegated
  generated initial/handoff stages; all other stages retain exact individual review.

## Context

The principal creator workflow is to find Minecraft YouTubers, approach them
about compensated website promotion, identify interest, and connect them with
the owner. Compensation can be a negotiated share of attributable earnings over
an agreed number of weeks. Automatic negotiation, fabricated revenue forecasts,
and open-ended outreach are outside this goal.

## Decision

Extend the existing campaign/prospect/exact-action path. Do not introduce a new
runtime or give the interactive Hermes container mail or database credentials.
Migration 020 adds paid-first campaign settings, explicit compensation terms,
owner contacts, the handoff stage, and terminal handed-off state. Existing
campaigns keep community mode; new dashboard campaigns use the paid partnership
flow and unrestricted country/language selection.

Generated revenue-share copy treats percentages/weeks as proposals and blank
values as individually negotiable. It never derives rates from audience size,
calculates real earnings, agrees a contract, or guarantees payment. The owner
handles earnings definitions, attribution, reporting, and commercial terms.

Migration 021 stores finite run authority, exact-action reservations, reply
evidence and review, suppression, and Gmail cursors in PostgreSQL. Server-defined
policy classifies preparation as medium risk and mail reading as low risk.
All sends remain high-risk digest-bound actions. A run supplies the explicit
operator delegation for eligible generated introductions and optional handoffs;
it cannot approve arbitrary messages or contacts.

Runs default to three introductions/day and 24-hour expiry, with maxima of ten
and seven days. Eligibility includes reviewed contact authority, observed
Minecraft content, known subscriber range, recent publication, current geography,
and suppression checks. Same-creator/recipient stage reservations prevent repeat
outreach across campaigns. Handoffs share existing SMTP pacing and require
reviewed interest. Once SMTP accepts a handoff, the agent's sequence terminates.

Campaign and contact snapshots are frozen into each packet and rechecked at the
receipt boundary, along with current run state, expiry, pending replies, and
required mailbox freshness. Campaign mutations invalidate prior packet authority.
Legacy packets fail closed and require preparation again. Redis remains only
transport; restart recovery cannot create new send authority or refund usage.

Read-only Gmail uses the existing credential compartment in the research worker,
a separate custom creator label, mailbox identity validation, bounded metadata,
durable cursors, and a shared campaign lock against send-boundary checks. Positive
classification is a suggestion requiring review; explicit opt-outs suppress.
Unreviewed replies stop further sending. No source text can select a capability,
redirect a handoff, or approve an action. Discord is an owner-contact string only.

## Consequences

Migration 022 stores bounded operator-reviewed objection tags in existing
marketing outcomes. A pure learning component deduplicates creator evidence,
explains objections and chooses among three fixed paid-copy strategies. Three
reviewed creators can motivate a hypothesis; all strategies need ten sends each
and a five-point/1.5× observed lead before performance preference. An 80/20
assignment retains exploration. Snippet suggestions never enter learning until
reviewed. No weights, code, commercial terms, recipients or authority are learned.
Reports are observational campaign history, not causal estimates or guarantees.

The workflow is useful with deterministic source-grounded preparation and clear
human takeover. It requires contact and positive-interest review; it does not
claim unrestricted end-to-end agent autonomy. Partial metadata can produce false
opt-out detection, and an operator must inspect uncertain replies. OAuth itself
allows mailbox-wide reads even though the adapter restricts the label. SMTP
acceptance remains distinct from inbox delivery. A pause cannot recall an action
already past the receipt boundary, and ambiguous sends are never retried.

Validation is through unit tests, disposable PostgreSQL concurrency/lifecycle
checks, and Mailpit delivery. External sending and real OAuth monitoring remain
unverified until their own canaries complete.
