# ADR-0022: Scoped career Play authorization and Gmail reply tracking

September 26 clarification: preparation has a separate allowance of 20
opportunities per profile per rolling day and twice the selected application
cap per run (up to 20). Failed attempts remain counted. Actual submission
reservations keep the user's selected cap and final guards. Migration 019 links
prepared items directly to exact actions; links convey no authorization.

- Status: Accepted
- Date: 2026-09-23
- Supersedes: the per-click-only career approval requirement in ADR-0009/0010;
  exact action digests, receipts, risk classification, and marketing approval remain.

## Decision

The authenticated user can start a bounded preparation or application run.
Apply mode authorizes a frozen profile, selected reviewed ATS hosts, a minimum
fit score, verified posting-age window, rolling 24-hour cap, explicit screening
answers, and expiry. Optional hiring emails use a single explicitly published
recruitment address in the selected job description and the configured sender.
This grant cannot authorize arbitrary browser activity or general cold outreach.

PostgreSQL owns grants, preparation items, per-profile target deduplication, and
action reservations. The research scheduler creates ordinary policy-classified
draft/preflight tasks. Completed run-bound material becomes an exact high-risk
action. Within the grant, a transaction reserves the shared application budget,
records a digest-bound approval attributed to the run, and publishes the ordinary
outbox signal. Existing manual exact-action review remains available.

At the receipt boundary the isolated action worker rechecks the active grant,
expiry, profile, job fingerprint, fresh posting date, fit and destination.
Pausing prevents subsequent receipt acquisition; an action already handed to
the remote service cannot be recalled. Unknown required answers, unsupported
forms, login and CAPTCHA require review. Ambiguous external outcomes consume
the reservation and never retry automatically. New Play runs cannot reset the
rolling cap or the per-profile normalized target ledger.

Greenhouse `updated_at` is labelled as an update, never a posting date. Such
records remain research-only for automatic application purposes. Remotive is
optional, retains original attribution, and reserves at most four public API
requests per rolling day across all missions, with at least one minute spacing.

Gmail is a separate low-risk read capability. OAuth refresh credentials exist
only in the research worker. The adapter requires Gmail read-only scope, checks
mailbox identity against the application profile, and reads only the configured
operator-created label. Bounded metadata pages and cursors persist in PostgreSQL;
raw messages, attachments, and OAuth credentials are excluded from API results
and audit. Inbox signals never execute instructions or send replies. Uncertain
correlation and interview dates require review, with manual corrections retained
as history. Reply polling continues for applications from the previous 180 days
after an application run expires or is paused while Gmail tracking is enabled.

Creator country selection uses declared YouTube channel-country metadata.
Language has separate channel/video metadata and provenance. Strict selection
excludes unknowns; current campaign criteria are applied when reading saved
dossiers. A campaign timestamp fence prevents an old scan overwriting results
after its criteria change. Geography does not authorize outreach.

## Consequences

This is an explicit, expiring delegation, not a policy bypass. API and UI must
show the scope before Play. Profile changes pause the run. No self-modifying
policy, inferred legal answers, invented resume facts, or fabricated job dates
are allowed. Gmail scope is mailbox-wide at Google, although this adapter reads
only the selected label. The user must keep that label intentionally scoped.

YC, LinkedIn, and Discord are discovery entry points with honest connection
status. Users can add supported employer board slugs found there. Their login
sessions, APIs, message permissions, and application flows are not represented
as connected. Live external application, SMTP and Gmail verification require
the user's actual profile and configured accounts; fixture success is separate.
