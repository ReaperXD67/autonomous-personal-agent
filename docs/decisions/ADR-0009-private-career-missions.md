# ADR-0009 — Private career missions and review-before-submission

Status: Accepted

## Context

Continuous job hunting needs fresh external reads, durable schedules, résumé-
aware preparation, and a usable interface. General browser automation or direct
form submission would introduce credentials, prompt injection, CAPTCHAs,
employer-specific questions, duplicate-side-effect risk, and reputational harm.

## Decision

- Serve a same-origin dashboard from the authenticated control API instead of a
  separate hosted frontend.
- Store mission, opportunity, and draft state in PostgreSQL; use Redis only for
  reconstructible ready signals.
- Route `career.search` and `career.application_draft` through the existing
  policy, task, outbox, lease, and audit path and a dedicated least-privilege
  worker.
- Allow outbound reads only to reviewed no-key job API hosts with validated
  board slugs, redirects, size, and timeout.
- Keep résumé text out of task payloads and public job requests. Generate
  structured application preparation locally through Ollama.
- Do not implement generic form submission. Opening an official link and
  recording a user-completed application are distinct from submission. Any
  future adapter requires an exact high-risk approval and idempotency design.

## Alternatives

- Scrape general job sites with a personal browser profile.
- Allow an LLM to choose arbitrary URLs and submit forms continuously.
- Put schedules only in Redis or an in-process timer.
- Send résumé and job text to whichever free hosted model is currently
  available.

## Reasoning

Same-origin delivery avoids another deployment and credential boundary. Public
ATS APIs provide attributable structured data without account secrets. Durable
mission claims survive restarts and preserve the established authority model.
Local structured inference reduces résumé disclosure and fabrication risk. A
review-before-submit boundary gives useful automation without silently acting as
the user's legal/reputational identity.

## Consequences

The current product discovers, ranks, tracks, and drafts, but does not promise
hands-free application submission. Coverage depends on configured public
sources. The first UI uses one bootstrap bearer token and therefore remains a
private-administrator interface until OIDC/RBAC and rate limiting exist.
