# ADR-0035: Platform discovery and mandatory-qualification review

Status: accepted. Date: 2026-11-02.

## Context

More software/internship discovery must preserve the selected 72-hour window
and résumé truthfulness. A skill score cannot establish mandatory tenure,
education or legal eligibility. LinkedIn and YC references also do not grant
authenticated application capability. Existing reviewed ATS executors already
provide the appropriate control-plane, audit and side-effect boundaries.

## Decision

Add an original bounded reader for public YC company jobs: fixed HTTPS origin,
validated company/posting identities, no redirects or account access, at most
50 links/ten details per company and twenty details per scan. Require matching
posting identity and exact timezone-aware JSON-LD publication evidence. Report
bounded/failed coverage; do not promote observations or relative labels to dates.
YC opportunities remain manual destinations. Retain LinkedIn/YC source URLs
paired with independently observed supported employer ATS URLs using pure,
canonical URL intake. No scraping framework or account bot is installed.

Add a zero-model mandatory-qualification assessment. Explicit mandatory tenure,
completed-degree, enrollment/cohort and legal requirements need explicit evidence
or review. Never aggregate date ranges into experience or infer degree completion.
An optional strict boolean owner fact supports only clear India-only general
authorization without sponsorship. Unknown facts remain unknown. Facts are
stored separately from the résumé, omitted from model drafting context, and
bound with a policy version into the existing expiring Play profile digest.

Selection, automatic preparation, scoped authorization and final execution use
the same gate. Public reports expose only public posting excerpts and fixed
findings; private evidence is removed from API projections. Manual review remains
possible. Migration 027 keeps PostgreSQL authoritative for facts/source identity;
older source-constraint migrations cannot narrow it on replay.

## Consequences

The one-to-ten rolling-day limit is unchanged as an implementation ceiling;
operators may authorize ten without loosening quality or freshness. Existing
grants require renewal after this policy upgrade. Conservative parsing may send
eligible roles for review and cannot guarantee complete semantic understanding.
Public page structure may change and read failures are reported. Native
LinkedIn/YC account applications, arbitrary company forms and new email sender
accounts remain unconnected. No new service, production dependency, model call,
OAuth scope or submission destination is introduced.
