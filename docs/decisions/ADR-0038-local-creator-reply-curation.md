# ADR-0038 — Local, draft-only creator reply curation

- Date: 2026-11-04
- Status: Accepted; validation and live draft proof are separate gates
- Extends: ADR-0030 and ADR-0037

## Context

Complete reply evidence removes manual email copying, but the next response can
still be repetitive or miss a creator's supplied Discord contact. The owner
requested automatic curation while explicitly withholding replies to two current
conversations. Draft preparation must therefore be independent of classification,
contact authorization and sending.

## Decision

Add one small governed `marketing.creator_reply_draft` capability to the existing
job worker. PostgreSQL owns immutable private evidence, the issued task binding,
model invocation, status, digest and copy. Redis remains reconstructible transport.
No new runtime, framework, dependency, OAuth permission or external account is
required. Reuse the existing bounded local inference transport and usage ledger.

`CREATOR_REPLY_DRAFT_CAMPAIGN_IDS` is a separate, default-empty JSON allowlist of
at most ten distinct campaign UUIDs. Explicit draft requests and automatic
curation after a complete labeled sync enforce the same selection. The worker
also checks current opt-in before and after local inference. A mailbox or
body-capture configuration alone does not enable response generation. A completed
read examines at most the newest thirty complete replies and may queue at most
three eligible drafts; generation runs as separate tasks.

Require a complete saved reply with the exact body digest, matched campaign,
contact and prior accepted outreach. Freeze the campaign/contact/evidence context.
Deduplicate the same reply evidence rather than regenerate on every sync. Failed,
cancelled and pending preparations remain counted in the existing shared rolling
thirty/day and three/prospect preparation allowance, alongside introductions and
batch reservations. A failed model output is not replaced with manual/template
copy or silently repeated.

Private inbound text stays on the configured local model path; it cannot enter a
hosted inference fallback. Treat authored and quoted text as untrusted data. The
model selects only issued response modes. Server-owned rendering supplies concise
English/Polish text and the reviewed owner contact. Recognizable shared Discord
details can be acknowledged; missing business contact details can be requested.
A paid-promotion policy is not acceptance of the offer. Copy cannot invent a
rate, fee, fixed earnings, accepted friend request or agreed commercial terms.
Unclear evidence may remain without a draft. Schema validity is not proof of
correct interpretation, so the owner still reviews the complete source and copy.

Creation and completion recheck the issued task, current owned lease,
cancellation, suppression and frozen context. Routine task outputs, overview and
audit contain safe identifiers/status/counts rather than private message content.
Authenticated detail exposes saved source and copy as text, never active markup.

This capability has no SMTP preparation, approval, semantic-review or account
mutation path. A response draft cannot clear a pending reply, confirm interest,
renew a send grant or restore contact authorization. An owner conversation hold
cancels pending actions and withdraws contact authorization while preserving
provenance and truthful review state. It is distinct from recipient opt-out
suppression and requires explicit owner resumption.

## Consequences and proof

The useful autonomy is bounded preparation: monitoring can continue and the owner
can inspect a relevant next step without sending anything. Drafts are retained
even when sending is withheld. Initial introduction drafts and reply drafts are
different record types; existing exact-action APIs cannot accept a reply draft as
an introduction or an approval.

Required checks cover campaign scope, digest/context drift, task forgery,
duplicate scheduling, shared budget exhaustion, local-only routing, invalid model
output, quoted/negative/conditional evidence, cancellation and suppression after
inference, private rendering and no external action creation. A real local draft
response is required before claiming generation works. No test establishes a
guaranteed reply, collaboration, inbox placement or commercial outcome.

See the [upstream comparison](../research/creator-reply-draft-curation-2026-11.md) for
provenance and deferred framework alternatives.
