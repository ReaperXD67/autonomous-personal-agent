# ADR-0032: Grounded career drafts and isolated career mail

- Status: accepted
- Date: 2026-11-02

## Context

A real career draft failed the résumé-evidence check because the model rewrote
quotes and proposed unsupported keywords. Career applications also use a
different mailbox from creator outreach. Published hiring contacts outside a
posting need a reviewable source and cannot inherit an ATS application grant.

## Decision

Reuse the finite evidence-selection pattern already validated for creator
drafts. The server offers exact résumé excerpts and supported keyword IDs bound
to the complete résumé digest. The model selects IDs; the server resolves them
into the existing draft fields. A new provenance marker is recomputed during
quality review and the final action guard. Historical drafts are unchanged.

Allow at most one corrective generation for a failed deterministic draft check.
The correction retains the same privacy, provider, task lease, quota and
inference-ledger boundaries. It has a separate reservation and call count;
deterministic quality checks continue to use zero model calls. An unsuccessful
correction leaves an inspectable blocked draft, never a template success.
Free-text cover letters still need substantive review: exact evidence selection
does not prove every sentence or establish applicant eligibility.

Give careers an all-or-none, worker-only Gmail credential namespace and exact
recorded mailbox. The local PKCE helper supports `-Purpose Career`, preserves
creator credentials, checks the returned account, read-only scope and custom
label, and writes ignored configuration atomically. Gmail authorization covers
the mailbox; Hermes restricts metadata reads to the selected label. Consent,
label ingestion and accurate reply matching remain separate proofs.

Add expiring, individually reviewed public hiring/HR/founder contacts linked to
one current job/profile snapshot. Preparing an email freezes source evidence,
recipient and a quality-passed draft into the normal high-risk exact-message
approval path. This does not broaden Play. The configured SMTP sender must match
the application identity. Publication age remains at most 72 hours and fit is
recomputed. Revocation, expiry, changed records, suppression and duplicate sends
are rechecked at the SMTP boundary. Contact emails contain the cover letter and
portfolio/reference; this transport does not attach the résumé.

## Consequences

No new service, framework, model provider or host mount is added. PostgreSQL
remains authoritative for contacts, actions, audit, quotas and reply evidence.
Redis remains transport. Global address suppression now also fences career and
general SMTP paths and serializes with creator opt-out ingestion.

LinkedIn and YC account execution remains unimplemented. Public leads can add
reviewed employer ATS boards; unknown dates, applicant requirements, login,
CAPTCHA and unsupported forms remain review blockers. No new broad scraping or
account access is implied. See the existing [upstream comparison](../research/ai-job-search-adaptation-2026-11.md)
and [ecosystem review](../research/job-search-ecosystem-2026-11.md); no upstream
implementation is copied for this milestone.
