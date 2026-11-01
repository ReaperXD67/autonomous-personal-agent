# ADR-0029 — Frozen bilingual drafts and fair research selection

- Date: 2026-11-01
- Status: Accepted
- Extends: ADR-0026 and the bounded creator shortlist capability

## Context

Creator AI drafts always requested English, even when a campaign preferred
Polish. A review warning exposed the mismatch but did not provide a Polish
generation path. Repeated shortlist batches could also select the same
uncontacted, high-ranked creators and spend the research allowance on them.

The [upstream comparison](../research/creator-outreach-systems-2026-11.md)
identified explicit message-language selection and durable batch progress as
useful patterns. A second marketing platform or agent framework would duplicate
existing task, data and sending ownership.

## Decision

Store `output_language` in each new draft's existing immutable model context.
Preferred/strict English or Polish targeting selects the supported base
language; unrestricted selection defaults to English. Missing markers preserve
legacy English behavior. Unsupported explicit languages fail before inference.
Prompting, parsing, rendering and editorial reporting use that frozen contract.

The model supplies an opening and optional idea in the chosen language; its
operator rationale and schema remain English. The server retains control of
the commercial envelope. Product summary, paid-offer description and optional
revenue basis stay operator-reviewed verbatim text. Polish drafting therefore
requires those fields in appropriate reviewed Polish. The existing English
contact-source, privacy and opt-out footer is deliberately retained.

Use genuine `creator.pilot.created` audit history from the preceding 24 hours
to order shortlist candidates. History must match the canonical task payload,
current targeting snapshot and exact creator profile URL. Prefer unattempted
creators, then the least recently attempted; existing public-contact/relevance
priorities break ties. Apply eligibility and this ordering before the bounded
500-candidate selection. Failed and cancelled reservations remain attempted and
consume their existing rolling allowance. Unissued, modified or expired history
cannot alter priority.

Reuse existing PostgreSQL records and locks. Add no service, dependency,
migration, new sending authority or automatic contact qualification. Research
remains limited to ten creators per batch and thirty per rolling day. Model
copy retains individual exact-message approval, frozen context checks, shared
SMTP pacing, duplicate protection and suppression.

## Consequences

Polish campaigns can request matching AI suggestions without silently changing
legacy drafts or translating commercial claims. A language marker and lexical
guards cannot certify fluency, factual fit or creator interest. Complete-copy
review and a real model response remain necessary evidence.

Successive research batches advance within the bounded history window while
preserving idempotency, concurrent issuance and budget controls. This is not a
lifetime coverage cursor or proof that every relevant creator has been found.

Validation must cover English compatibility, Polish rendering and claim guards,
unsupported language refusal, current-context history, cancellation/failure,
concurrency and selection beyond the old candidate prefix. The engineering
journal records the tests and live provider evidence actually completed.
