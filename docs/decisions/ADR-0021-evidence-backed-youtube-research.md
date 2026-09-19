# ADR-0021: Evidence-backed YouTube creator research

Date: 2026-09-19

Status: Accepted. Supersedes ADR-0011 only where discovery excluded published
contact candidates; all contact authorization and exact-send boundaries remain.

## Context

Channel identity and subscriber counts alone do not tell an operator whether a
creator fits KarixMC, how to approach a collaboration, or where a creator has
explicitly published a business contact. Manual collection obscures provenance
and makes the research difficult to refresh.

## Decision

Extend the existing `marketing.creator_discovery` capability in the research
worker. Official YouTube channel/video snippets may yield contact candidates
only when an address has nearby business/collaboration context. These are
unreviewed observations, never recipient authorization. No gated About email,
guessed address, external-site crawl, or arbitrary URL fetch is added.

Store bounded source excerpts, observation timestamps, content/statistics
evidence, deterministic fit explanations, research gaps, suggested collaboration
concepts, and a proposed opening line in PostgreSQL `marketing_prospects.intelligence`.
Do not retain full source descriptions. A campaign scan refreshes research;
an individual prospect can be refreshed through the same policy/task/audit path.
Per-prospect refresh shares the discovery task budget and rechecks campaign
membership, platform, and suppression before fetching and saving.

The dashboard focuses on YouTube, offers search/contact filters and shortlist
export, and exposes evidence separately from proposed ideas. Selecting a
candidate pre-fills a review form; the operator still supplies the basis and
explicit authorization. No automated contact/send authority is granted. Historic
non-YouTube records remain available in storage.

## Consequences

Research is deterministic, requires no new model or provider dependency, and
uses the existing fixed Google API host and restricted worker credential.
Missing metadata or optional enrichment failure is visible as incomplete
research. Subscriber counts, a matched video, and rule-based fit do not establish
audience demographics, sustained engagement, deliverability, or creator interest.

Contact heuristics can miss obfuscated addresses and misattribute an agency or
sponsor address; source review remains necessary. Public descriptions are
untrusted data, never instructions. UI text is escaped and CSV cells are guarded
against formula execution. Refresh does not change approved recipient details,
offers, budgets, capabilities, model routes, or exact-action approval.

Research exports with real contact details stay in ignored local `output/`.
They are not published to the repository. Runtime readiness is established by
tests and harmless requests, not by container health alone.
