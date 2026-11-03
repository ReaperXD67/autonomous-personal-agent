# ADR-0036 — Audited local recovery and versioned creator introductions

- Date: 2026-11-03
- Status: Accepted
- Extends: ADR-0026 and ADR-0030

## Context

A real Creator local request failed after approximately 180 seconds. The saved
generic unavailable diagnostic has no historical load or request-phase evidence,
so a GPU, cold-load or network cause cannot be established retrospectively.
Downloaded weights and a healthy container only prove prerequisites. The local
reader also allowed interrupted response reads to escape normal draft-failure
handling, while timeout, HTTP and malformed responses shared one error.

Automatic routing can choose a hosted model. It therefore cannot reliably
establish local recovery without changing global configuration. The same stack
serves Career work, so a diagnostic should not switch its provider settings.

The existing sampled-title/angle wire already uses non-thinking structured
selection and a 512-token cap. Adding those again would not fix the failure.
Meanwhile new v2 messages always used the same multi-paragraph envelope. Zero
reviewed creator feedback does not establish why recipients have not replied.
The next style must remain an explicitly versioned experiment.

## Decision

Keep the existing drafting capability, workers, tables and inference ledger.

1. Add optional per-draft `inference_mode=auto|local_only`, defaulting to `auto`.
   Freeze explicit local selection in model context and expose it in reads/audit.
   Bind it to idempotency: changing mode under the same request key conflicts.
   Local-only skips every hosted plan/completion call and uses only the configured
   local model at the fixed internal endpoint, bypassing environment HTTP proxies.
   Unknown modes refuse before egress.
   Preparation budgets, owned leases, immutable context and exact approval remain.
2. Use a fixed 300-second grounded local response timeout; retain 180 seconds for
   legacy copy. The real cold canary took 170.384 seconds while a warm request
   took 2.642 seconds, leaving too little cold-start headroom under the original
   window. These are measurements, not proof of the historical failure cause.
   This urllib socket timeout is not a strict task wall-clock deadline. Independent
   heartbeat renewal and post-inference lease/cancellation/context/expiry checks
   remain, with no approval extension. Retain the response-size cap, v2 token cap
   and one separately accounted invalid-selection correction; two local attempts
   can each use the response window. Do not retry transport failures. Classify fixed
   safe timeout, connection, missing-model, busy, HTTP, malformed, oversized and
   incomplete-response errors. Require `done=true` and `done_reason=stop` before
   parsing. Interrupted response reads fail the inference and draft normally;
   raw exceptions, response bodies and reasoning are not diagnostics.
3. New contexts freeze `render_version=creator-concise-permission-v1` and
   `copy_strategy=concise`. Quote the exact selected public title once, retain one
   offered creator-controlled idea, remove duplicate framing and ask one easy
   question about discussing an independent test. Preserve the reviewed product
   summary, paid offer, revenue basis, complete commercial terms and footer.
   Earlier unmarked v2 and legacy messages retain their original bytes/digests.
   Missing or changed frozen context cannot select new rendering by inference
   from prose. Model output remains only issued evidence/angle identifiers.
4. Evaluate recovery through a separately budgeted, normal local-only draft task.
   Preserve the original failed record. Review a real completed local result
   before releasing an operational hold; never mark recovery from health alone.
   The canary creates neither a sending grant nor an email approval.

The existing hourly review, contact qualification, global suppression, actual
receipt pacing and reviewed-interest owner handoff remain authoritative. This
decision adds no generic template approval, follow-up sequence, tracking pixel,
provider account, dependency, schema migration or negotiation authority.

## Consequences and verification

Failures become actionable without being silently retried or disguised as
template copy. Explicit local selection also provides a stricter privacy option.
The original timeout cause can remain unknown even after current generation
recovers; describe those as separate facts.

Tests must cover transport/read failures and terminal state, hosted non-use,
unknown-mode refusal, mode-bound idempotency/audit, stopped-envelope validation,
unchanged old rendering/digests, new EN/PL terms and frozen-context tampering.
Run the complete integration and disposable PostgreSQL proofs before publication.
Real local generation, cold/warm latency and externally accepted outreach remain
separate operational measurements. No test or software pattern guarantees replies.

See the [primary-source comparison](../research/creator-model-recovery-and-permission-outreach-2026-11.md).
