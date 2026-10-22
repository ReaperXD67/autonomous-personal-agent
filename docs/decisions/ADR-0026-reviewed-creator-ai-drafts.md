# ADR-0026 — Bounded creator research and reviewed AI introductions

- Date: 2026-10-20
- Status: Accepted
- Extends: ADR-0025 and the existing strict-free inference policy

## Context

Creator outreach needs a specific, truthful opening and a useful content idea
based on each creator's recorded work. Fixed templates cannot adapt those ideas
to individual content. Giving a model complete emails or send authority would
also let hostile source text influence commercial terms, contacts and actions.
Subscriber count is observable metadata, not a prediction of audience reach,
conversions or an appropriate price.

## Decision

Add `marketing.creator_draft` as a medium-risk capability in the existing
research worker. Requests create a durable task, audit and outbox record through
the control plane. Migration 023 stores the campaign/contact/research snapshot,
sanitized model context, final copy, model identity, expiry and immutable digest
in PostgreSQL. Redis remains transport. No service, dependency, host mount or
direct Hermes execution privilege is added.

Drafting requires an authorized public business contact, observed Minecraft
topic, a valid sampled YouTube video, and research observed within seven days.
Preparation is limited to three requests per creator and thirty globally per
rolling day, separately from sending budgets. Drafts expire after 24 hours.
An idempotency key prevents a retried request from creating another draft.

The prompt includes a bounded product summary, creator display name, sampled
video title/URL, allowlisted topics, observed subscriber count and reviewed
aggregate feedback. Sanitization removes contact details from descriptive
fields. Raw descriptions, recipient addresses, contact provenance and inbox
excerpts are not sent to the model. All metadata is untrusted evidence.

The model may return only a short hook, optional content idea, operator-facing
rationale, fixed evidence reference and the server-selected reach strategy.
Small channels receive a focused-trial suggestion; other known counts leave
format choice to the creator; unknown counts permit no reach assumption.
These strategies never set compensation. Schema, length and lexical checks
reject common invented commercial terms, links, contacts, certainty, personal
endorsements and false claims of having watched the creator. They cannot prove
semantic truth or product fit; exact human review remains necessary.

The hook need not contain a particular English evidence keyword. The server
already inserts the exact observed title and URL into the complete message.
Requiring the literal word `title` rejected accurate, natural references while
accepting unsupported claims that happened to contain it. The validator retains
the existing negative copy checks; it does not treat a keyword as proof of
grounding. The prompt and repair hint must describe that same contract.

The server supplies the subject, greeting, sender, product description,
commercial proposal, call to action, tracked product URL, contact-source,
privacy and opt-out footer. The existing strict-free OpenRouter route retains
privacy filters, zero-cost attestation, per-attempt budget reservations and
usage audit, followed by configured internal Ollama fallback. Invalid output
cannot silently become a template. Invalid local copy permits at most one
regeneration using the original evidence plus a fixed sanitized validation hint.
The rejected text is not persisted or reused in a prompt. Each attempt receives
a fresh inference reservation and lease/cancellation/context checkpoint;
transport failures do not trigger this repair. Template and manual writing
remain separate, explicit dashboard choices.

The existing local creator model may use bounded internal reasoning within its
normal request. Only final message content is validated and saved; the model's
separate reasoning field is ignored and never enters draft records, inference
audit or logs. The visible operator rationale is an explicit output field,
not the internal reasoning trace. Local requests retain the same timeout,
response-size and two-attempt limits, with each attempt accounted separately.
The request uses [Ollama's documented thinking control](https://docs.ollama.com/capabilities/thinking)
for [Qwen3's thinking mode](https://qwenlm.github.io/blog/qwen3/); the installed
model's capability metadata was checked independently of those references.

Preparing a successfully completed draft checks its digest, expiry, current
campaign/contact/research snapshot and eligibility, then creates the ordinary
exact email action. Worker writes and context reads recheck owned task leases,
cancellation and expiry after blocking locks. A crash after saving valid copy
can reuse it without another model invocation. AI messages are excluded from
the bounded run's delegated template authority and template comparison metrics.
They require individual exact-message approval and retain the existing final
send-boundary context, suppression, deduplication and pacing checks.

## API shortlist research

`marketing.creator_pilot` adds a bounded research task to the existing worker.
It refreshes at most ten saved creators using official YouTube API metadata and
up to three recent uploads each, then ranks evidence deterministically.
The global rolling allowance is thirty creator refreshes. Normal task,
idempotency, audit and budget records in PostgreSQL retain authority; no new
table, runtime or interactive-browser permission is needed.

A global transaction lock serializes issuance and budget reservations. The
server selects exact uncontacted saved identities and freezes campaign
targeting, profile URLs and a reservation nonce in the task payload; a creation
audit binds its canonical hash to the task. Generic caller tasks cannot inherit
that reservation. Only one batch may be active per campaign, and failures or
cancellation do not refund the rolling allowance. Worker checkpoints recheck
the issued payload, identity, suppression and owned lease after blocking locks
and before provider requests or evidence persistence. The capability gets one
execution attempt so an ambiguous failure cannot silently repeat a batch.

The report preserves actual publication dates, separately observed timestamps,
declared language, public contact-source evidence, selection reasons and gaps.
It makes no model request, contact authorization, draft or email. An operator
chooses the next contact review or individual draft. The bounded saved pool and
provider failures are not represented as exhaustive discovery.

## Mailbox setup

The local Gmail helper uses built-in PowerShell/.NET, a loopback callback,
random state, S256 PKCE, exact `gmail.readonly` scope and expected mailbox/label
checks. It atomically merges secrets into ignored configuration under the same
process lock used by SMTP setup, preserving unrelated concurrent edits. It
refuses conflicting or unverifiable existing shared career credentials.
SMTP authentication remains a separate integration and is never granted by the
YouTube key or read-only OAuth.

OAuth permits mailbox-wide reading; the runtime's creator-label restriction is
an application boundary. The helper does not create labels, enable a send run,
prove reply ingestion, or bypass Google's consent and account checks.

## Consequences

The operator can inspect source evidence, rationale, exact copy and model route
before sending. Reviewed feedback informs later prompts without training
weights, changing policy, negotiating rates or rewriting approved messages.
Neither personalization nor observational learning guarantees interest,
deliverability, collaborations or income.

The first version supports English paid introductions only. It uses one sampled
video and recorded metadata, not video viewing or full content analysis.
Synthetic model, PostgreSQL and browser tests are distinct from a real model
response, owned-mailbox SMTP delivery and labeled Gmail reply canaries. Each
external integration stays unverified until its own end-to-end proof completes.
