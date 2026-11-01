# ADR-0030 — Grounded creator plans and preparation-only batches

- Date: 2026-11-02
- Status: Accepted
- Extends: ADR-0026 and ADR-0029; replaces free-copy generation for new drafts only

## Context

The November 1 launch returned nineteen model drafts from twenty-four requests,
but exact source/product review retained only one AI email and used twenty-three
manual replacements. The failures included invented verification/features,
descriptions of unseen video contents and poor wording. These operator findings
are not creator feedback. Existing JSON schemas, lexical checks and correction
retries constrained form without establishing truth. Preparing creators one at
a time also required repetitive operator work.

The [primary-source comparison](../research/creator-grounded-generation-2026-11.md)
identified finite output choices, context validation and authored rendering as
useful patterns. Another agent framework or prose self-critic would add execution
or inference costs without supplying missing product evidence.

## Decision

New immutable contexts carry `drafting_contract=creator-grounded-plan-v2`.
The model returns only the issued `evidence_id` and an offered `angle_id`, with
strict schema, membership and duplicate-key validation. Recorded title keywords
offer possible content angles; they do not establish actual video contents,
audience preference or product/server support. The server writes the opening,
optional independent proposal and operator explanation in authored EN/PL wording.
It quotes the recorded title and links its source, retaining the reviewed product
brief, commercial terms and existing English source/privacy/opt-out footer.

Store the selected plan and provenance binding source title/URL, generation
language, context digest and campaign digest with the existing draft. Save and
preparation rederive and compare complete copy. Rendering also refuses changed
source/campaign bindings. Legacy contexts retain their parser and exact messages;
there is no rewrite or digest migration. Unsupported explicit languages remain
refused. Local v2 selection disables reasoning output, caps generation at 512
tokens and retains one separately accounted invalid-output correction. Fixed
`CREATOR_DRAFT_OUTPUT_INVALID` and `CREATOR_DRAFT_MODEL_UNAVAILABLE` errors
distinguish contract failure from unavailable response. Neither creates fallback
prose or authorization.

Add the medium-risk `marketing.creator_draft_batch` capability to the existing
research worker and policy/task/audit/outbox path. A parent reserves at most five
eligible reviewed contacts, three by default, with stable membership, input
hashes and UUID5 child idempotency keys. A genuine creation audit binds the
canonical payload hash; caller-created generic tasks cannot inherit authority.
Each child draft/task/outbox and its per-item outcome commit atomically. Resume
reuses existing children and terminal skips. Context, targeting, suppression,
identity and valid lease are rechecked after waits; cancellation stops remaining
issuance without recalling independently queued children.

Use the existing PostgreSQL preparation lock and tables. Actual drafts plus
genuine unmaterialized reservations share thirty preparations per rolling day
and three per prospect. Cancelled/failed parents retain reservations; their own
matching children consume them without double counting. Batch-only identity
deduplication covers canonical channel/profile identity and exact normalized
business email across current drafts, genuine reservations and the selected set,
including other campaigns. The parent makes no model call and creates no
external packet, approval or contact/send grant. Each child retains ordinary
inference accounting and exact individual message review. Add no dependency,
service, migration, model route or credential scope.

## Consequences

The model has a smaller factual surface and operators can queue preparation
without repetitive per-creator requests. Authored proposals trade free-form
variation for explicit source boundaries and more dependable wording. A source
title can still be misleading, a brief inaccurate, or an offered angle unsuitable.
Complete-message review remains necessary; no result promises creator interest,
replies, income or fully unattended arbitrary-AI outreach.

Validation must cover allowed/forged plans, source/campaign/language bindings,
stored-copy tampering, legacy context/digest preservation, stable batch replay,
cross-campaign deduplication, skips, cancellation/lease waits and concurrent shared
budgets without external packets. The journal and Experiment 39 record the
synthetic, interface and real inference measurements actually completed.
