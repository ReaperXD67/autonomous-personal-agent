# Complementary job-search research — 2026-11-02

Observed from canonical repositories, license files, source code and provider
documentation. No upstream application was installed or executed, and no
private résumé, mailbox or provider credential was supplied to these projects.
Stars, indexed crawl dates and upstream success claims are not validation.

## Inspected projects

| Project and inspected commit | License actually inspected | Maintenance observed | Decision for Hermes |
|---|---|---|---|
| [JobSpy](https://github.com/speedyapply/JobSpy/tree/68b88d6909a2342ad75fbb945c4204a3a7ed6665) | MIT, copyright Cullen Watson, 2023 | Commit 2026-10-27; not archived; `pyproject.toml` version 1.4.1 | **Adapt** explicit typed country/employment/date contracts; **defer** adding its scraper runtime |
| [JobNavigator](https://github.com/vesaias/JobNavigator/tree/f18178d01fef2efe85ecb997ba19fa351e6164fd) | MIT, JobNavigator Contributors, 2026 | Commit 2026-11-01; not archived; recent source retry/telemetry fixes | **Adapt** separate normalized identity, source coverage and fit/availability checks; keep Hermes policy and PostgreSQL |
| [Job-Ops](https://github.com/DaKheera47/job-ops/tree/7fac74fc709aa64ba7b590042757101e39c5ec60) | GNU AGPLv3 **plus Commons Clause v1.0**, with a no-selling condition | Release commit 0.14.0 on 2026-10-27; repository pushed 2026-10-30 | **Defer code reuse**; its license is not ordinary MIT or unmodified AGPL. Use only general workflow observations |
| [Reactive Resume](https://github.com/reactive-resume/reactive-resume/tree/4bf278971c2f8ae21e01b316309d214a04d8b7dd) | MIT, Amruth Pillai, 2026 | Commit 2026-11-01; not archived; parser/export tests present | **Adapt** source/master résumé preservation and extracted-PDF-text verification; **defer** adopting its application stack |
| [FresherFlow India Jobs and Internships](https://github.com/FresherFlow/India-Jobs-Internships/tree/656d1c2d321c41fe3f8830e20557023b81a3630c) | No license identified in repository metadata or inspected root tree | Feed regeneration 2026-11-01 | **Defer vendoring code/data**; use as a lead to independently inspect employer pages. Its added date is not employer publication evidence |
| [internscan](https://github.com/vishnunandan555/internscan/tree/ef731792e338ffad0afb41c1aecee4ac22a604de) | No license identified in repository metadata or inspected tree | Automated closure sync 2026-11-01; public adapter/test files | **Defer code/data copying**; independently implement provenance-aware availability and use employer URLs as research leads |
| [Ever Jobs](https://github.com/ever-jobs/ever-jobs/tree/171651b5bea9ea554c8486282a141c7ae5772463) | MIT, Ever Co. LTD, 2026 | Default-branch commit 2026-10-26; pushed 2026-11-01; not archived | **Adapt** source-specific normalized adapters with common output; **defer** its NestJS/Nx service/monorepo |

License details above describe inspected files, not a legal conclusion about
every transitive component. No code was copied from these repositories.

## Findings that change implementation choices

1. **Fit and freshness must be separate.** Hermes's previous ranking awarded
   25/17/9 points for age. A single exact title plus five matching skills scored
   80 within a day, 72 after a day and 64 after two days before other preferences.
   A 75-point automatic-application threshold therefore excluded otherwise
   identical two-day roles inside a 72-hour authorization. Freshness should
   remain a separate source-evidence eligibility condition; explain rejection
   counts and components rather than claiming a fit percentage predicts hiring.
2. **A transport library is not an authorization boundary.** JobSpy's inspected
   dependencies include requests, BeautifulSoup, pandas, Pydantic, curl_cffi and
   markdownify. JobNavigator additionally brings an ORM, scheduler, Playwright,
   PDF tooling, model SDKs and an authenticated LinkedIn dependency. Hermes
   already has those lifecycle and policy responsibilities. These stacks would
   add maintenance and outbound access without proving application quality.
3. **Preserve posting identity.** JobNavigator's
   `backend/scraper/_shared/dedup.py` preserves provider identity parameters while
   removing tracking noise; its source filters also reject navigation content.
   A URL is not interchangeable with a company name or a title. Hermes retains
   its exact provider/board/posting identity and durable application ledger.
4. **Distinguish failed reads from closure.** internscan's `scraper/store.py`
   retains first-seen history and marks missing postings closed only when that
   employer's fetch succeeded. A source timeout must not close a job, advance its
   publication timestamp, or silently count as a complete search.
5. **Check what the ATS can read.** Reactive Resume's
   `packages/resume/src/ats-pdf/rules/parseability.ts` inspects extracted text and
   image-heavy pages; its import code rejects truncated extraction. Its
   application-copy tests preserve the base résumé when tailoring. A visually
   attractive PDF alone does not establish readable text or truthful content.
6. **Prefer one bounded official adapter to a new platform.** Ever Jobs's
   `packages/plugins/source-ats-smartrecruiters` and the India registry in
   internscan pointed to a provider capability absent from Hermes. The
   implementation here follows the provider's own contract independently,
   without importing either project's runtime or source.

## SmartRecruiters: chosen narrow adaptation

[Official Posting API endpoints](https://developers.smartrecruiters.com/docs/endpoints)
document public GET routes for one company's active listing page and posting
detail, with `releasedDate` and optional country filtering. Detail content is
published/re-published by the employer; that timestamp is publication evidence,
not proof of the original creation date or a genuine employer.

The original Hermes adapter makes at most one 50-item list read and ten detail
reads per configured board, prioritizes target-title metadata before the detail
budget, and reports partial coverage and failed details. It constructs only
fixed provider URLs, refuses redirects, and ignores returned `ref`/`applyUrl`
values. Public source content never supplies another network destination.
Declared India preference can narrow the public discovery query; it does not
infer residence, nationality or work authorization.

Source configuration and lookup accept reviewed SmartRecruiters board links.
The database source check is expanded by migration 025; replay of the older
016 constraint cannot narrow it again. Automatic submission authority and the
browser host allowlist are unchanged. These opportunities remain discoverable
and draftable, with manual application on the original portal.

Focused, networkless adapter/intake tests cover publication provenance,
stale/future/closed jobs, provider/identity mismatch, bounded reads, partial
failure, interruption, deterministic title priority and manual-only source
status. Fixture success is separate from a real provider canary.

## Independently observed employer entry points

These are source-directory facts, not recommended applications or verified
vacancies. No date below claims that an individual job was recently posted.

| Employer | Provider and source configuration | Primary observation on 2026-11-02 |
|---|---|---|
| PhonePe | `smartrecruiters_boards: ["PHONEPELIMITED"]` | [Provider-hosted employer page](https://careers.smartrecruiters.com/PHONEPELIMITED) displays the employer and Indian locations; automatic submission is unsupported |
| Freshworks | `smartrecruiters_boards: ["Freshworks"]` | [Provider-hosted employer page](https://careers.smartrecruiters.com/Freshworks) displays Bengaluru among locations; automatic submission is unsupported |
| Meesho | `lever_boards: ["meesho"]` | [Employer board](https://jobs.lever.co/meesho) displays India locations and engineering categories; verify each role's level and date |
| CRED | `lever_boards: ["cred"]` | [Employer board](https://jobs.lever.co/cred) displays Bengaluru roles, including cloud/security engineering; no internship availability inferred |
| Razorpay | `greenhouse_boards: ["razorpaysoftwareprivatelimited"]` | [Employer board](https://job-boards.greenhouse.io/razorpaysoftwareprivatelimited) displays an AI Builder role and Bengaluru positions; a source update remains distinct from publication |
| Sarvam | `ashby_boards: ["sarvam"]` | [ATS portal](https://jobs.ashbyhq.com/sarvam) responds with its JavaScript shell; actual listings and publication dates need the governed public API scan |
| Composio | `ashby_boards: ["composio"]` | [ATS portal](https://jobs.ashbyhq.com/composio) responds with its JavaScript shell; no currently open position is certified by that response |

The Swiggy SmartRecruiters page could not be read with the research browser, so
it is not listed as an independently verified working source here. Generic
career portals, login-only flows, guessed email addresses and CAPTCHA bypasses
are not substituted for source evidence.

## Deferred work

- Broad JobSpy/account scraping needs a source-specific terms, egress, quota
  and live compatibility review; no scraper is installed merely for coverage.
- Full resume-editor adoption would introduce a second application and model
  configuration; small truthfulness and PDF-readability checks fit Hermes better.
- Unlicensed feed redistribution and Job-Ops code copying remain deferred.
- More sources do not demonstrate better match quality, successful submission,
  delivery, interview rate or market leadership. Record measured outcomes after
  real authorized executions instead of adopting upstream marketing claims.

## LinkedIn and YC follow-up: 2026-11-02

The pinned JobSpy/JobNavigator comparisons above still favor explicit source
contracts and provenance over importing another scraper/runtime. No upstream
code or dependency was copied for this follow-up. The original public YC parser
uses observed company-page identity plus matching posting JSON-LD. The public
[Aviator internship](https://www.ycombinator.com/companies/aviator/jobs/aaMaqQu-software-engineering-intern)
demonstrated why a visible job link is insufficient: its exact publication was
2022-03-03. Account application URLs also appeared alongside `directApply`.
Only exact, timezone-aware matching `datePosted` can qualify a new listing.

LinkedIn public search returned rate limiting during research; no retry/proxy or
authenticated scraper was substituted. Its [automated-access guidance](https://www.linkedin.com/robots.txt)
and [partner access documentation](https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access)
do not provide Hermes a generic native application API. The adopted path is a
canonical platform reference paired with an independently observed supported
employer ATS URL. Native LinkedIn/YC submissions stay manual.

An independent twenty-company YC sample exposed 42 engineering roles but no
verified suitable posting inside the selected 72 hours. Relative added times and
search-engine crawl dates were not treated as publication. Research leads with
unknown exact dates, mandatory availability questions or unsupported company
forms were not submitted. These observations are coverage evidence, not a claim
that no suitable jobs exist elsewhere or a measurement of adapter accuracy.


## Additional early-career employer research

Independent official ATS pages also identified [Ontic](https://jobs.ashbyhq.com/ontic)
(UI/backend associate roles, Pune, 0–2 years including projects),
[Neuron7](https://jobs.lever.co/neuron7) (frontend apprentice, Bengaluru, specified
2026 graduation), [AHEAD](https://jobs.lever.co/thinkahead) (India apprentice,
explicit degree/CGPA conditions), [Quadric](https://jobs.ashbyhq.com/quadric)
(kernel/compiler internships naming Pune among secondary locations, with US
preference and specific C++/architecture requirements), and
[Commure](https://jobs.ashbyhq.com/commure) (indexed India software-engineer
posting requiring a current detail check). These are discovery entry points;
no qualification, availability or publication date is inferred from search
indexing. They were added through the ordinary profile/run APIs for a governed
scan. Indexed junior links returning 404 and roles whose actual location was US
were excluded rather than presented as fresh Indian opportunities.
