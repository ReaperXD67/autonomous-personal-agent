# Architecture overview

Creator partnerships use the existing marketing and exact-action layers. The
pure `creator_learning` component reads reviewed outcome tags and accepted-send
counts to select fixed draft strategies. PostgreSQL stores the evidence and
selection reason; Gmail snippets are suggestions until reviewed. Adaptation
cannot change commercial terms, scope, limits, approvals, or prepared packets.
The same reviewed aggregates can inform a bounded creator plan. For new v2
drafts, the model selects only server-issued evidence and angle IDs; authored
English/Polish rendering supplies the opening, optional idea, explanation and
commercial envelope. Stored provenance binds the source, language, context and
campaign. Revalidation rederives the copy rather than trusting stored prose.
Legacy contexts retain their original free-copy parser and complete messages.
Every personalized draft still requires individual exact-message review.
Draft reads also compute an editorial report from the stored public context and
rendered copy. It has no persistence, score, model invocation or authorization
effect; metadata-only grounding and natural language still require review.
English/Polish reply hints normalize a bounded authored-text view without
changing stored evidence. Only reviewed tags enter learning; direct opt-outs
retain the existing durable suppression boundary.

Creator draft selection and rendering use `output_language` in the frozen model
context. Preferred/strict English or Polish targeting selects that contract;
unrestricted selection and legacy contexts without a marker remain English.
Unsupported explicit languages are refused before inference. The operator's
product summary, paid-offer wording and optional revenue basis are inserted
verbatim and need review in the intended language. Polish rendering localizes
the server envelope and next step while retaining the standard English
contact-source/privacy/opt-out footer. The language marker describes the
generation contract, not a linguistic quality score or sending decision. Angle
eligibility comes from recorded title keywords; it establishes neither video
contents nor product capabilities. See [ADR-0030](../decisions/ADR-0030-grounded-creator-plans-and-draft-batches.md).

## Goals

Career operations use a versioned fit policy independent of posting age, with
current component/filter projections and zero-model scan diagnostics. Draft
generation records bounded résumé/posting evidence findings; delegated approval
and the final receipt recompute them and recheck expiry after draft-row waits.
Typed document and consent handling remains in the isolated action worker.
Migration 025 extends opportunity provenance for bounded official SmartRecruiters
reads; submission authority remains unchanged. No new service or dependency is
introduced. See [ADR-0031](../decisions/ADR-0031-evidence-backed-career-operations.md)
and [upstream research](../research/ai-job-search-adaptation-2026-11.md).

Foundation favors explicit boundaries over premature features:

1. every task has durable identity and state;
2. high-impact execution requires exact approval or explicit bounded delegation;
3. transient queues cannot become authoritative memory;
4. upstream agent/model products remain replaceable;
5. tools are granted per-agent, not globally;
6. local Docker behavior maps cleanly to a single-host KVM VPS.

## Planes

### Control plane

Control API accepts authenticated requests, classifies risk, and atomically
creates durable task, audit, and outbox records for eligible work. It does not
execute tools.

### Execution plane

The outbox dispatcher reliably bridges durable PostgreSQL intent to Redis.
Workers claim queue messages and perform allowlisted capabilities. The
foundation worker implements `foundation.echo` and bounded `foundation.wait`.
The dispatcher also reconciles immutable workflow dependency graphs in
PostgreSQL. Ready steps become ordinary policy-classified tasks in the same
transaction as their step binding and audit; it executes no tools itself.
Result checks, concurrency limits, cancellation, and deadlines govern further
dispatch. Published queue signals can be reconstructed from durable queued
tasks; delivery generations fence stale acknowledgments.
The dedicated career worker implements allowlisted fresh discovery, verified
free-only hosted drafting with local fallback, and official YouTube creator
discovery and reviewed creator AI drafts while using the
same lifecycle, policy, and audit model. YouTube tasks carry bounded campaign
and creator references; the restricted API key exists only in this egress-enabled
worker. Shortlist batches reserve server-selected creator IDs under a shared
rolling budget before dispatch, then check the issued payload, current identity
and owned lease before each provider request or evidence write.
Research selection uses genuine creation audits from the preceding 24 hours,
bound to their canonical task payload, current targeting snapshot and profile
URL. Never-attempted creators precede oldest-attempted creators, then public
contact evidence and relevance break ties. Eligibility and fair ordering apply
before the 500-candidate cap. Cancelled/failed reservations remain attempted
and budgeted; generic or changed-context task history cannot alter priority.
No new cursor table, migration or service is required.
The isolated action worker handles reviewed browser and email side effects only
after an exact approval digest has entered the durable queue.
Career Play grants can authorize those exact digests within a frozen, expiring
scope. PostgreSQL stores the grant, preparation records, rolling budget and
normalized application target ledger. The action worker rechecks the grant at
the receipt boundary. See [ADR-0022](../decisions/ADR-0022-scoped-career-autopilot-and-reply-tracking.md).
Preparation items use an independent bounded per-profile/per-run allowance;
they do not consume the actual application ledger. Each prepared item retains
its exact action ID so review and later manual outcomes remain traceable.
Gmail reply tracking runs in the research worker with read-only OAuth and a
selected label. Only that worker receives Gmail refresh credentials. Career
email preparation receives sender metadata and pacing policy; SMTP credentials
remain in the existing control/action boundary, not the research worker.

### Data plane

PostgreSQL is system of record for tasks, approvals, audit events, memory, and
embeddings, plus career profiles, opportunities, and drafts. Redis carries
reconstructible ready queues and future cache state.
Losing Redis may delay work but must not erase authoritative history.
External-action envelopes, form preflights, and side-effect receipts also live
in PostgreSQL so approval and duplicate prevention survive a crash.
External SMTP approvals also reserve durable send slots with rolling volume
limits, same-domain spacing, and jitter, preventing queue or VPS recovery bursts.
Inference invocations retain requested/selected route, token, latency, privacy,
fallback, status, and cost metadata but never prompt or output text.
Creator campaigns, channel prospects, public-contact provenance, durable
suppression, outreach/action links, reply classifications, and attributed
results use the same authority.
YouTube prospects also retain bounded research dossiers in PostgreSQL: public
business-contact candidates, source evidence, explained fit, creative ideas,
and gaps. Candidates never update recipient authorization. Campaign scans and
single-prospect refresh use the existing discovery task and worker budget.
Multi-page scans reserve each search in PostgreSQL before provider egress, with
a shared rolling budget and per-task cap. The control API streams full creator
exports from a consistent read-only database snapshot and exposes full-campaign
coverage independently of paged dashboard records. See ADR-0023 for boundaries.
Contact history merges under prospect row locks for the same canonical channel,
keeps original observation dates, expires on read after 30 days and is physically
trimmed by bounded worker housekeeping. It never grants recipient authorization.
See [ADR-0024](../decisions/ADR-0024-dated-creator-contact-history.md).

Paid-first creator campaigns add revenue-share proposals and an owner-contact
handoff to that same path. PostgreSQL stores finite creator run grants, exact
message reservations, reply reviews, cross-campaign suppression, and mailbox
cursors. The research worker prepares generated messages and records delegated
exact approvals; only the isolated action worker sends. It checks campaign and
contact snapshots, remaining run authority, reply state, and duplicate/suppression
evidence before acquiring a receipt. Accepted handoffs terminate the sequence.
Read-only creator Gmail uses a separate label and confirmed mailbox identity;
snippets cannot authorize positive interest. No new service or inference route
is introduced. See [ADR-0025](../decisions/ADR-0025-creator-partnership-handoff.md).

Creator personalized drafts are separate immutable product records in PostgreSQL. They
retain input snapshots, sanitized prompt context, evidence, copy, model route,
expiry and digest; inference audit still omits prompts and outputs. The research
worker executes `marketing.creator_draft`. New contexts carry
`creator-grounded-plan-v2`: the model returns only `evidence_id` and `angle_id`
from offered choices, and the server renders source-grounded copy and fixed
commercial wording. The stored plan and provenance are rederived before save
or preparation; legacy contracts are not migrated. Exact-digest preparation rechecks current
research/contact/campaign context. AI copy cannot use a run's delegated template
approval; the usual action worker retains final delivery authority.
See [ADR-0026](../decisions/ADR-0026-reviewed-creator-ai-drafts.md).

`marketing.creator_draft_batch` is a medium-risk preparation capability handled
by the existing research worker. A parent reserves at most five eligible
reviewed contacts, three by default, with frozen membership, snapshot hashes
and UUID5 child keys. The genuine creation audit binds the complete payload
hash. Each child is issued atomically with its ordinary task, outbox and audit;
durable per-item outcomes preserve skips and committed children on resume.
Current context, targeting, identity, suppression and owned lease are rechecked
after row locks. Batch-only deduplication spans current drafts, genuine
unmaterialized reservations and the selected set across campaigns, using
canonical channel/profile identity and exact normalized business email.

The shared PostgreSQL preparation lock accounts for actual draft rows plus
unmaterialized matching reservations: thirty per rolling day and three per
prospect. Cancelled/failed reservations retain their allowance; their own
matching children materialize without double counting. Parent cancellation
stops remaining issuance without withdrawing independently queued child tasks.
The parent makes no model call and creates no external packet, approval or send
grant; the children use the existing inference path and individual review.
Existing task/audit/draft tables suffice: no new service, migration, dependency
or credential compartment is introduced.

### Agent and model plane

Hermes is the agent brain. OmniRoute is its primary model gateway. They run in
the `agent` profile, use official pinned images, and remain outside the trusted
control/data core.
Hermes can reach OmniRoute on isolated `model` network but cannot reach
PostgreSQL or Redis directly.

Deterministic discovery, filtering, and scoring spend no tokens. Hermes uses an
ordered OmniRoute `free/default` → OpenRouter `openrouter/free` → internal Qwen
chain. The Ollama daemon is supervised, but Qwen weights load only at the final
fallback and expire after idle time. Career drafts also have a narrow direct
OpenRouter strict-free path ordered by opportunity score/freshness and bounded
by PostgreSQL. General Hermes fallback calls are outside that ledger and must be
bounded by the provider-side key policy.

The career worker has a separate, narrow OpenRouter adapter because it can
enforce exact live-catalog `:free` and zero-price invariants before résumé data
leaves the host. It intersects the catalog with active zero-retention endpoints,
ranks the remaining candidates by bounded live benchmark metadata and declared
capabilities, and sends one primary plus at most three provider-supported
fallbacks. It requests no-training/zero-retention endpoints, verifies the actual
selected model and returned cost, and validates the task schema. Empty or
invalid structured output cools that route and receives a separately reserved
attempt through the next ranked model before internal Ollama.

### Tool plane

MCP server candidates live in a curated registry. Profiles select capabilities;
permission policy adds risk and approval requirements. No MCP server is enabled
by default during foundation phase.

## Reviewed proposals and feature evidence

The research worker handles `planning.propose` under a medium-risk allowlisted
capability. PostgreSQL stores selected context and a server-generated inventory.
The model selects opaque actions only; deterministic compilation fixes kinds,
payloads, dependencies, and checks. A successful proposal does not execute its
children. Digest-bound operator adoption creates the immutable workflow and its
proposal link atomically, after revalidating current context. The existing
OpenRouter/Ollama path and ledger account for planner inference too.

The private API also stores strictly bounded operator feature-test metadata in
PostgreSQL. Browser clients read prerequisites, scopes, and evidence timestamps;
only bearer-authenticated operator scripts can publish reports. No runtime host
directory is mounted into the API. Report booleans describe the last test, and
verification labels become stale after 24 hours.

Career and creator scheduler transactions now include both schedule advancement
and task/policy/audit/outbox creation. Rollback leaves the occurrence due; locked
rows prevent duplicate issuance by concurrent scheduler workers.

## Quality attributes

Career drafting now binds server-issued résumé choices to a digest and permits
one separately accounted corrective generation. The existing worker, policy,
lease and inference ledger remain authoritative. Dedicated Career Gmail
credentials keep account selection independent from creator outreach. Reviewed
job-linked public contacts freeze provenance and drafts into normal individual
email approvals; final SMTP checks enforce current identity, scope, suppression
and canonical job/address duplicates. See
[ADR-0032](../decisions/ADR-0032-grounded-career-drafts-and-isolated-mail.md).

Career projections now compute job-risk and publication signals without
inference. The autopilot refuses strong signals before preparation and rechecks
them before its existing final receipt. A pure authenticated source resolver
normalizes reviewed ATS URLs without fetching them; regional Lever discovery
uses separate US/EU public endpoints and source identities. Career Gmail adds a
persisted shortlist outcome and conservative assertion/time checks. The private
dashboard prioritizes recorded outcomes and uncertain matches from loaded data.
No new service, model route or sending authority is introduced. See
[ADR-0027](../decisions/ADR-0027-zero-model-career-intelligence.md).

The action worker also handles the fixed-config, medium-risk, single-attempt
`communications.smtp_check` diagnostic through the existing task/outbox path.
It sends no email and returns only transport/TLS/authentication evidence.
External actions revalidate owned leases, cancellation, frozen context, and
contact authority at the submission boundary. SMTP acceptance is committed
before best-effort cleanup and cannot be downgraded by a later task failure.
The approval transaction reserves an external-SMTP release time and the worker
rechecks it before the receipt. Mailpit remains immediate. No new service,
dependency, or host authority is introduced.

- **Reproducibility:** images and Python dependencies are release-pinned.
- **Least privilege:** loopback ports, internal data network, non-root read-only app images.
- **Auditability:** correlation IDs link request, task, approval, worker, and audit events.
- **Portability:** Compose is shared by Docker Desktop/WSL2 and future Linux VPS.
- **Recoverability:** Redis is reconstructible; checksummed PostgreSQL dumps pass
  a disposable restore drill through application code.
- **Extensibility:** new workers and tools integrate through task/policy boundaries.
