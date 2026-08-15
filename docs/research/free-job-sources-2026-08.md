# Free job-source assessment — 2026-08

Only official, public, no-key interfaces were selected for the first career
worker.

| Source | Interface | Freshness evidence | Configuration | Current boundary |
|---|---|---|---|---|
| Arbeitnow | Public job board API | `created_at` | enabled per mission | reviewed host, maximum 100 returned items, original listing retained |
| Ashby | Public Job Posting API | `publishedAt`, `isListed` | exact employer board slug | reviewed API host; listing and apply URLs retained |
| Greenhouse | Job Board API GET | `updated_at` | exact employer board slug | reviewed API host; absolute job URL retained |

Arbeitnow describes its API as free and no-key and asks consumers to link back
to listings. Ashby documents its public posting endpoint and exposes published
time and apply URLs. Greenhouse documents unauthenticated GET access for job
board data. Remotive was evaluated but not enabled for the “fresh only” mission:
its official public-API repository says public jobs are delayed by 24 hours and
requests are limited, which conflicts with a 24-hour freshness goal.

The worker accepts no arbitrary source URL. Scheme, hostname, redirect target,
response size, request timeout, and employer board slug are bounded. One source
failure does not erase results from another. Listings older than the mission's
window or more than 24 hours in the future are rejected. Original source data is
untrusted; it cannot issue tool instructions, and local drafting explicitly
treats job descriptions as data.

This is a practical initial catalog, not a universal aggregator. Employer board
slugs must be chosen by the user, scraping login-gated sites is absent, and the
project does not claim that every job on the internet is covered.
