# ADR-0037 — Bounded complete creator-reply evidence

- Date: 2026-11-03
- Status: Accepted; isolated source/scope validation passed, live retrieval pending
- Extends: ADR-0025 and the existing read-only creator Gmail boundary

## Context

Metadata and provider snippets can correlate a reply to a previously accepted
invitation, but cannot establish the full author's intent. Requiring the owner
to paste messages leaves routine private review dependent on a manual step.
The existing exact `gmail.readonly` grant can retrieve parsed message bodies
without broadening OAuth permissions or enabling mailbox writes.

Existing syncs skip known reply IDs. Changing only future metadata reads would
leave already-pending rows without complete evidence. Hydration must preserve
their identity, creation time, review state and campaign linkage.

## Decision

Reuse `marketing.gmail_sync`, its policy/task/audit path, configured mailbox and
custom label. Keep metadata discovery and unique prior-outreach matching first.
Full-body capture requires explicit campaign opt-in through
`CREATOR_GMAIL_FULL_REPLY_CAMPAIGN_IDS`: a JSON array of at most ten distinct
campaign UUIDs, default `[]`. Both automatic hydration and explicit `POST /read`
enforce this allowlist. Other campaigns retain metadata-only syncs; a configured
Gmail account alone does not enable body capture. Readiness exposes
`full_reply_capture_enabled` as configuration evidence, not proof of a successful
read. Disabling future capture does not delete or hide existing captured history
from authenticated detail.

Within the combined `MAX_GET=20` message-read budget, allow at most three
`format=full` reads for pending exact matches, including known metadata-only rows.
Do not expose an arbitrary-message or whole-mailbox body reader.

Check the returned mailbox/label context and the exact message ID, thread ID,
sender, subject and received time against the saved matched record before
storing body evidence. Recheck current task ownership and campaign state after
provider work. Gmail refresh credentials remain worker-only; use the existing
fixed HTTPS host/resource allowlist, no redirects and bounded responses.
Do not modify labels, messages, mailbox settings or credentials.

Use a small standard-library parser over Gmail's MIME JSON. Limit depth to eight,
nodes to sixty-four, decoded content to 128 KiB and text to 24,000 characters.
Use a fixed supported-charset set and strict base64url/charset handling. Prefer
inline plain text and select supported MIME alternatives without duplicating
their text. Exclude attachment parts and embedded-message subtrees; make no
attachment endpoint request, external fetch, link visit or active HTML render.
The bounded full response may contain attachment metadata or inline encoding;
do not decode or persist attachment content.

Missing required text, unsupported structure/charset, malformed encoding and
resource-limit violations must leave evidence incomplete or unavailable.
Never silently truncate it into a complete body or substitute the snippet.
Keep full selected plaintext, digest, status and attempt state separate from
the original metadata/snippet. Preserve complete evidence before deriving any
authored-only hint; quote/signature removal remains a heuristic.

Permit a narrow read retry only for incomplete records: at most three attempts
with a five-minute cooldown, still within the shared per-sync read budget.
Do not repeatedly refetch completed rows, reset their creation time, clear
pending review or overwrite an existing complete body during routine sync.
Aggregate audit/results retain status/counts/digests, never body content.
A known completed read failure newer than the last complete sync blocks sending
readiness and delegated authority until a later complete sync. Configuration or
a newer queued/running task does not clear that failure hold.

Expose complete plaintext only through authenticated campaign/reply detail;
overviews omit it. Render it as text, never trusted markup or tool instructions.
Semantic review must supply the exact stored body digest. Missing, incomplete
or changed evidence refuses review. This enables private review of retrieved
evidence without introducing an automatic positive classifier, negotiation,
handoff or sending authority. Existing suppression, pending-reply blockers and
exact-action approval remain authoritative.

## Consequences and proof

No new SDK, service, provider, account or OAuth scope is needed. PostgreSQL owns
the additional private evidence and its review binding; Redis remains transport.
Read permission is mailbox-wide at Google, while Hermes enforces the narrower
selection and validation. A digest establishes evidence integrity, not sender
authenticity, complete authorship separation or correct interpretation.

Required proof includes MIME/encoding/resource-bound failures, attachment and
embedded-message exclusion, mailbox/label/identity drift, existing-row backfill,
repeat stability, combined budgets, retry cooldown/exhaustion, post-provider
lease/cancellation checks, overview privacy and exact digest-bound review.
Actual retrieval and review of a real reply remain separate live evidence.
Campaign-scope validation and successful live retrieval are not established by
accepting this decision.
Primary-source provenance and deferred alternatives are recorded in the
[research note](../research/creator-full-reply-reading.md).
