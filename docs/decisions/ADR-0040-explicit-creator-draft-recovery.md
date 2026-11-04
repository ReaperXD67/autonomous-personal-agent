# ADR-0040 — One explicit recovery for a model-failed response draft

- Date: 2026-11-04
- Status: Accepted; source validation and real recovery remain separate checks
- Extends: ADR-0038

## Context

The first real response-curation pass correctly queued two held conversations,
but both local requests ended during model startup without copy. Diagnostics
observed severe host CPU, page-in and disk pressure. The model fitted GPU memory;
no out-of-memory kill or driver reset was established. The sole cause is unproved.
Reusing the ordinary draft endpoint preserves the failure rather than retrying
the same evidence indefinitely. Recovery needs a bounded, visible operator path.

## Decision

Allow one explicit linked preparation after an original model-unavailable failure.
Keep the original draft, task, inference invocation, audit, digest and expiry
unchanged. The new attempt has its own task and invocation but inherits the
original expiry. It consumes the same shared thirty/day and three/prospect
allowance, including failed/cancelled rows and outstanding batch reservations.
There are at most two preparations per unchanged evidence lineage.

The authenticated campaign/reply/draft-bound `/retry` route requires the actor
and current complete body digest. Require the original terminal failed task,
model-unavailable draft error and a failed local-only Ollama invocation. Refuse
active, ready, cancelled, invalid-output or changed-context sources, suppression,
expired evidence, a third attempt and a request before the five-minute cooldown.
Contact authorization can remain withdrawn because this capability cannot send.

Serialize source task/draft inspection before the shared budget/automation locks,
then recheck campaign/contact/reply context. Enforce lineage uniqueness in
PostgreSQL; repeated or concurrent requests return the same recovery child.
Creation audit and execution bind its attempt number and parent. Retain the
existing one-inference-per-task, local-only routing and final cancellation,
lease, context and expiry guards.

Ordinary preparation and automatic sync return the latest existing attempt;
neither creates a recovery attempt. The UI shows retained failure, lineage,
cooldown and server-derived eligibility. Its explicit recovery control is
separate from read-only polling. No email action, approval, classification,
contact authorization, template fallback or commercial negotiation is added.

## Operations and proof

Address the observed provider/resource issue before requesting recovery. Let
completed isolated test stacks stop and host load settle before a model canary.
A healthy container, available VRAM, queued retry or valid schema is not a real
response. Do not reset failed task state, increase limits or extend deadlines
merely to obtain a result. Do not attribute all pressure to another workload
without evidence, or restart unrelated services to hide a failure.

Required proof covers unchanged originals, concurrent/idempotent recovery,
lineage forgery, cooldown, terminal-state refusals, shared consumed budgets,
context/suppression/expiry changes and zero sending authority. A genuine
governed response and full copy review establish recovery separately.
