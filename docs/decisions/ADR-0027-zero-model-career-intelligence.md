# ADR-0027: Deterministic career triage and employer-board intake

- Status: Accepted
- Date: 2026-10-23
- Extends: ADR-0022; exact-action authorization and receipts remain authoritative.

## Decision

Use explicit, deterministic checks for opportunity risk, provider-board URL
recognition and career-reply triage. Reserve inference for application writing.
The URL resolver accepts only reviewed Ashby, Greenhouse and regional Lever
origins/paths, performs no fetch and grants no account or submission authority.
Mission configuration stores normalized board names. EU Lever uses its separate
official public API and source identity through the existing career worker.

Opportunity projections recompute fixed risk signals from current public facts.
The autopilot refuses strong flags before reserving preparation and checks again
at its final receipt boundary. No caller-supplied trust field is authoritative;
no result certifies authenticity. Freshness remains based on source publication
provenance, never a refreshed observation or update timestamp.

Read-only Gmail classification adds an explicit `shortlisted` outcome with
negation, conditional, contradiction and event-time checks. Migration 024 expands
the existing event/message constraints without reclassifying historical data.
Messages remain untrusted evidence. A dashboard decision queue prioritizes
recorded offers, interviews, shortlists and uncertain matches without model
calls, new notification channels or inbox-triggered actions.

## Consequences

The existing PostgreSQL/policy/task/audit/outbox and worker boundaries remain.
No service, dependency, credential privilege, general browser access or account
integration is added. Supported source discovery does not imply supported form
submission. Source recognition and heuristic checks are not proof of a genuine
employer, current vacancy, real reply or successful external application.

LinkedIn and YC serve as user-discovered entry points to supported employer ATS
boards. Their gated/account application flows and arbitrary founder/HR outreach
remain outside Career Play. Application email still requires one unambiguous
hiring address published in the job and shares existing caps/deduplication.
Free/local drafting consumes tokens and compute; zero calls apply only to the
deterministic stages. Accuracy and market leadership are not established.
