# ADR-0031: Evidence-backed career operations

- Status: Accepted
- Date: 2026-11-02
- Extends: ADR-0022 and ADR-0027

## Decision

Adapt reviewed upstream workflow concepts into small original components rather
than introducing another job-search platform or agent permission system.
[Research and provenance](../research/ai-job-search-adaptation-2026-11.md) compare
the requested AI Job Search project and seven complementary repositories.

Scoring policy version 2 separates deterministic title/skill fit from publication
age. Explicit aliases and token boundaries replace accidental skill substrings.
Current fit projections expose components and filter reasons without returning
résumés or identity. Every normalized source record contributes one primary
diagnostic outcome. Publication provenance, geography, unknown facts and run
authority remain separate. The profile hash includes scoring policy version,
so older grants cannot silently acquire broader scoring semantics.

Generation records a deterministic quality report from the actual résumé,
posting and draft. Direct résumé quotations and supported keywords are required
for delegated material; narrow checks flag placeholders, conspicuous unsupported
quantified accomplishments/tenure and unusably short or long copy. Cleaned prompt
views remove bounded hidden/invisible/instruction-shaped posting content.
Delegated authorization and the final receipt recompute the report rather than
trusting its stored verdict, then check grant expiry after draft-row lock waits.
Manual exact-action review remains separate; these checks do not prove semantic
truth, fit, eligibility or polished writing.

The form resolver binds documents to an explicit résumé purpose and accepted
PDF type. It never treats every upload as the résumé or guesses employer/legal
questions from identity words. Checkbox/radio answers require explicit booleans;
unknown default-checked controls require review. Default state joins the frozen
form signature, and submission validates the typed answers again before filling
or obtaining a receipt. Unsupported documents require the operator on the
employer portal.

Migration 025 adds read-only SmartRecruiters provenance to existing opportunity
storage. A fixed-origin adapter reads a bounded list/detail budget, reports
partial coverage and uses explicit published/re-published dates. It neither
follows response-provided network URLs nor expands browser submission hosts.
Ashby retains explicit secondary locations and distinguishes hybrid from remote.

## Consequences

PostgreSQL remains authoritative. No runtime, framework, dependency, credential
scope, account bot or sending authority is added. Inference remains restricted
to configured drafting routes; discovery, diagnostics and checks make no model
calls. More matches can result from corrected scoring, but none imply an
application was submitted. Real submission, mailbox reply and delivery evidence
are recorded separately from fixture results. Unsupported ATS forms, unknown
answers and login/CAPTCHA flows continue to stop for review.
