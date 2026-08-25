# ADR-0010 — Exact, approval-bound external actions

Status: Accepted

## Context

Application submission and email delivery change external state under the user's
identity. A generic “allow submissions” switch cannot express the employer,
form, answers, résumé revision, recipient, subject, or body being authorized.
Queue delivery is at least once, so a crash around the final network operation
can also create duplicates.

## Decision

- Keep every real application submission and email send high risk. Preparation,
  inspection, matching, drafting, and scheduling may remain automatic.
- Persist an immutable exact-action envelope in PostgreSQL. Its SHA-256 digest
  covers the action type and both reviewable and private execution context.
- Bind the approval record, task payload, expiry, and worker execution guard to
  that same digest. A changed résumé, draft, form signature, sender, or action
  context invalidates execution instead of silently widening approval.
- Execute external writes only in a dedicated container. The browser receives
  no personal browser profile, host mount, Docker socket, or arbitrary URL. The
  SMTP endpoint comes from deployment configuration, never task input.
- Insert a durable side-effect receipt immediately before the irreversible
  browser click or SMTP handoff. Consequential tasks have one attempt. A receipt
  blocks all automatic retries; a failure after the boundary becomes
  `ambiguous` and requires investigation.
- Support only reviewed single-page Greenhouse, Ashby, and Lever hosted forms.
  CAPTCHA, login, multi-step flows, missing legal/consent answers, unknown
  required questions, and changed forms stop before submission.
- Provide Mailpit and a local application fixture as an isolated verification
  profile. They are test sinks, not production integrations.

## Alternatives

- Automatically approve all submissions and outbound email.
- Let an LLM browse arbitrary sites and decide what answers or consent to give.
- Retry failed submits through the normal worker attempt budget.
- Give Hermes, a personal browser profile, or an MCP server direct submit/send
  access outside the control plane.

## Reasoning

The intelligent adapter should remove mechanical work, not erase authorization.
Exact plans make the remaining decision concrete and fast while preventing a
stale or modified action from borrowing a broad approval. A pre-side-effect
receipt turns uncertainty into a visible state instead of a second application.
Narrow ATS support is auditable and testable; generic web automation is not.

## Consequences

The agent can continuously discover fresh jobs, draft tailored material,
inspect supported forms, resolve routine identity fields, and prepare a
one-click exact action. It can execute immediately after approval. It cannot
truthfully be called zero-click for real applications or email, and unsupported
forms require user handling. Real SMTP credentials and private VPS ingress
remain deployment inputs.
