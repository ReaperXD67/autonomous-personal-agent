# ADR-0039: Greenhouse first-publication evidence

Status: accepted. Date: 2026-11-04.

## Context

The Greenhouse adapter treated every timestamp as an update, even when the public
API supplied its separate `first_published` field. That excluded genuine recent
postings from automatic consideration. Greenhouse documents this field separately
from `updated_at` in its [job contract](https://docs.greenhouse.io/job-board.html),
and it was independently observed on a public employer board. A recent update
alone still cannot establish publication.

## Decision

Prefer an explicit valid timezone-aware ISO `first_published` value as publication
evidence. If it is absent, malformed, timezone-less or the wrong type, preserve
only the existing update evidence when available; never label that fallback as
published. A valid publication date is authoritative over a newer update, including
when it is old or future: the normal hard freshness checks decide eligibility.
No extra provider reads, credentials, endpoint, model call or submission host is added.

## Consequences

Some Greenhouse records can now pass the existing publication gate. Fit, mandatory
qualifications, risk signals, consent, exact-action checks, duplicate protection
and the rolling application cap still apply independently. A fresh research-intern
lead which exposed this issue scored below the saved threshold and lacked explicit
enrollment evidence; its publication date does not authorize an application.
Old update-only history remains ineligible for automatic submission. This clarifies
ADR-0022 rather than treating updates or observation times as publication.
