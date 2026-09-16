# ADR-0020 — Durable low-volume email pacing

Status: Accepted

Date: 2026-09-16

## Context

Exact approval and duplicate receipts prevent unauthorized or repeated email,
but several individually approved messages could still enter the queue at once.
An in-memory sleep would occupy a worker, disappear on restart, and allow a VPS
recovery burst. Sending slowly also cannot, by itself, guarantee inbox placement;
domain authentication, relevant recipients, opt-outs, complaints, and provider
reputation remain decisive.

## Decision

- Reserve an external-SMTP send time inside the same PostgreSQL transaction that
  records approval and creates the outbox event. An advisory transaction lock
  serializes simultaneous approvals.
- Default to at least 15 minutes between all messages, 30 minutes between
  messages to the same recipient domain, no more than three in any rolling hour
  or twelve in any rolling 24 hours, and zero to three minutes of deterministic
  jitter. Configuration remains bounded and cannot disable external pacing.
- Store the policy snapshot and lifecycle in `outbound_email_schedule`. The task
  and outbox use the reserved time, so Redis loss, process restart, or VPS reboot
  cannot collapse future messages into a burst.
- Refuse approval when the next safe slot would fall outside the exact action's
  expiry. The operator must approve fewer messages and prepare a fresh packet
  later rather than extending stale authorization.
- Revalidate the durable schedule at the irreversible send boundary. Mark a
  cancelled or pre-boundary failed slot skipped, an accepted slot accepted, and
  an uncertain post-boundary slot ambiguous.
- Keep Mailpit immediate. It is an isolated fixture and does not affect sender
  reputation; slowing it would only make local safety tests impractical.
- Emit RFC 5322 `Date`, use the configured sender domain for `Message-ID`, and
  pass the exact approved envelope sender and recipient to SMTP.

## Consequences

Approving several real emails no longer means sending them together. The next
release time is visible in the dashboard and audit metadata, and the schedule
survives recovery. This remains one-to-one, approval-gated outreach—not a bulk
mailer. Hermes does not promise inbox placement, automatically warm a domain,
manage provider DNS, ingest complaints, or provide RFC 8058 HTTPS one-click
unsubscribe. Those require provider/domain setup and, for list mail, a scoped
public unsubscribe service before volume increases.
