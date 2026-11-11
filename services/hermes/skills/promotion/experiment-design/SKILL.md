---
name: experiment-design
description: Design small organic growth experiments and evaluate matched-window activation evidence without inventing statistical winners.
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [marketing, measurement, experiments]
---

# Organic experiment design

Prepare a private experiment specification or analyze supplied data. This skill
grants no rollout, tracking deployment, account, posting, email or spending
authority. Respect the owner's release and mailing holds.

State the observed problem, audience, one change, expected mechanism and primary
activation event. Choose a guardrail such as signup failure, confusing reward
expectations, complaints or moderation rejection. Predefine observation windows,
minimum useful sample, exclusion rules, decision date and stop conditions.

Use the existing campaign/channel/creative link convention when available.
Design only the events needed for the decision: eligible visit, action start,
confirmed completion and later return, with clear definitions and deduplication.
Keep personal data out of UTMs. New analytics services, pixels and account
connections are separate work, not prerequisites silently installed by this skill.

Report raw counts before rates. Numerator and denominator must cover the same
closed time window and eligible cohort. Pending activation/return windows are
pending, not failures. Reconcile totals independently and preserve missing or
unreliable tracking as unknown. SMTP acceptance, clicks, first gameplay and
retention are different events.

If traffic cannot support an informative randomized test, recommend a small
qualitative usability check or sequential pilot and state its confounders. Do
not peek repeatedly and stop on a convenient fluctuation. Define what evidence
would justify scale, revise or stop; treat a low-volume result as directional.
No guaranteed virality, causal uplift or revenue should be inferred from sparse
observations or an attractive creative score.
