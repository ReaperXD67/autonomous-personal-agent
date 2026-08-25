# Free job-source assessment — 2026-08

Only official, public, no-key interfaces were selected for the first career
worker.

| Source | Interface | Freshness evidence | Configuration | Current boundary |
|---|---|---|---|---|
| Arbeitnow | Public job board API | `created_at` | enabled per mission | reviewed host, maximum 100 returned items, original listing retained |
| Ashby | Public Job Posting API | `publishedAt`, `isListed` | exact employer board slug | reviewed API host; listing and apply URLs retained |
| Greenhouse | Job Board API GET | `updated_at` | exact employer board slug | reviewed API host; absolute job URL retained |
| Lever | Public Postings API | `createdAt` | exact employer site slug | reviewed EU/global hosts; hosted apply URL retained |

Arbeitnow describes its API as free and no-key and asks consumers to link back
to listings. [Ashby documents its public posting endpoint](https://developers.ashbyhq.com/docs/public-job-posting-api)
and exposes published time and apply URLs. [Greenhouse documents unauthenticated
GET access](https://developer.greenhouse.io/job-board.html) for job board data.
[Lever documents public postings and hosted apply URLs](https://github.com/lever/postings-api/blob/master/README.md).
Remotive was evaluated but not enabled for the “fresh only” mission:
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

## Submission interface research

The official ATS APIs do not provide a universal applicant-owned submission
token. Greenhouse and Lever direct-POST endpoints require credentials controlled
by the employer, while public Ashby data supplies a hosted `applyUrl`. Therefore
Hermes uses the official hosted form only after an exact preflight and approval;
it does not pretend that public discovery API access grants write access.

The browser runtime is [Playwright Python 1.62](https://playwright.dev/python/docs/docker)
in Microsoft's release/digest-pinned image. The official guidance supports a
non-root user for untrusted browsing; this project also removes capabilities,
keeps the filesystem read-only, and provides no persistent browser profile.
[Mailpit](https://mailpit.axllent.org/docs/install/docker/) is the free local SMTP
sink used to prove message generation without external delivery. Real Gmail or
Microsoft delivery would require user OAuth/SMTP consent; for example, the
[Gmail send API requires OAuth scopes](https://developers.google.com/workspace/gmail/api/guides/sending).
