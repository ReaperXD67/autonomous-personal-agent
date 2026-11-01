# AI Job Search adaptation — 2026-11-02

The requested reference is
[ai-job-search-dev/ai-job-search](https://github.com/ai-job-search-dev/ai-job-search/tree/7f01d752516d955a694271f75ee5534bc344873a),
inspected at `7f01d752516d955a694271f75ee5534bc344873a` on November 2.
That master commit is dated October 31 and its GitHub CI was successful when
inspected. The latest release endpoint reported `v1.7.3`, published October 19.
Its [license](https://github.com/ai-job-search-dev/ai-job-search/blob/7f01d752516d955a694271f75ee5534bc344873a/LICENSE)
is MIT, copyright 2026 Mads Lorentzen. Recent October 27 source changes addressed
portal installer and configuration safety. Maintenance is observed activity,
not a promise of compatibility or security.

This is chiefly an agent workflow and portal-search toolkit, not a universal
autonomous ATS submitter. Its maintainer's reported application/interview/job
outcomes are an individual case study, not comparative quality measurements.
Hermes retains its PostgreSQL, policy, audit, exact-action and container design.
No upstream code, runtime, dependency or skill pack was copied or installed.

| Inspected source | Useful pattern | Hermes decision |
|---|---|---|
| `.claude/skills/job-application-assistant/04-job-evaluation.md` | Eligibility before weighted fit; explicit strengths, gaps and assumptions | **Adapt:** versioned, age-independent title/skill fit and separate hard-filter evidence. Experience, culture and work eligibility remain unknown unless supplied |
| `.claude/commands/rank.md` | Cheap triage before expensive full preparation | **Adapt:** deterministic ranking, normalized-record exclusion counts and bounded preparation before inference |
| `.claude/commands/apply.md`, `.claude/agents/application-reviewer.md` | Separate writing/review, exact posting/material archive and honest drafted/submitted states | **Adapt:** deterministic résumé-quotation/claim checks before delegated approval and at final receipt; retain immutable PostgreSQL drafts and existing receipts. This is not an independent semantic model reviewer |
| `tools/posting_guard.py` | Remove hidden/invisible/instruction-shaped input and report counts | **Adapt:** original bounded HTML/Unicode/prompt-view sanitization. It never follows links; no claim that sanitization detects every injection |
| `tools/job_key.py`, `tools/rank_state.py` | Stable identities, explicit state transitions and failed-fetch/expiry distinction | **Retain/adapt:** existing provider/board/job identities, shared application deduplication and failed-source coverage; do not replace PostgreSQL with CSV state |
| `.claude/commands/gmail-sync.md` | Source-backed reply suggestions and reviewed outcomes | **Retain:** Hermes's label-scoped read-only metadata adapter, uncertain-match review and durable timeline. Actual selected-mailbox sign-in and reply canary remain prerequisites |
| `.agents/skills/*`, portal CLI installer | Reusable market-specific search skills | **Defer:** Danish-market coverage, Claude/Bun permission configuration and a second tool authority would add maintenance and model cost. Use reviewed official adapters inside the existing worker |
| PDF text-layer verification in the application workflow | Verify the material an ATS reads | **Defer dependency:** browser fixture proves a real synthetic PDF attaches; extracted-PDF text/semantic verification is not implemented or claimed |

The chosen original changes also address a measured Hermes defect: its previous
fit score included posting age, so the same exact-title/five-skill job scored
80, 72 and 64 at one, 25 and 49 hours. A 75-point run could therefore reject
strong jobs inside its own 72-hour freshness scope. Version 2 evaluates fit
independently, retains strict freshness and publication provenance, and
invalidates old grants when the scoring policy changes. Scores remain
heuristics, not hiring probabilities.

See [the complementary repository comparison](job-search-ecosystem-2026-11.md)
for seven other projects, exact licenses, dependency tradeoffs, official
SmartRecruiters documentation and independently observed employer entry points.
Success is evaluated with existing policy/SQL/browser checks and separately
recorded live outcomes; adding sources or code does not establish market leadership.
