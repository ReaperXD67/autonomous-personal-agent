# ADR-0023: Bounded creator discovery and complete research export

- Status: Accepted
- Date: 2026-09-26

## Decision

Keep the existing `marketing.creator_discovery` policy capability and research
worker. Campaigns may request one to three pages per query, up to three queries
and 25 results per page. Round-robin paging favors query breadth; canonical
channel IDs deduplicate results and opaque continuation tokens are bounded.

PostgreSQL reserves every search request before egress using a shared transaction
lock: 90 requests per rolling 24 hours and nine per task. This cannot be reset by
creating another campaign or restarting a worker. Failure and interruption do
not refund a reservation. Migration 018 conservatively reserves three calls per
attempt for each recently active legacy scan once, retained for a full day from
migration; delayed and retried tasks are included. Removing a disposable fixture
task nulls its ledger reference without refunding the global request count.
The existing task cap remains, including per-creator metadata refreshes.

Provider quota/rate errors stop further requests; partial evidence and integer
coverage counters remain visible. No scheduler, Hermes or direct API caller gets
a provider-key bypass. Search result language/region never establishes country;
strict rules also exclude saved records with empty dossiers.

The authenticated API offers a complete streamed CSV from a read-only,
repeatable-read PostgreSQL cursor, plus full-campaign coverage and stable-order
offset pagination. Full exports include matching creators without contact data,
source evidence, unknowns, suppression and authorization status. Optional excluded
history is explicit. CSV cells neutralize spreadsheet formulas. Page navigation
can see changes between requests; the export itself uses a single snapshot.

## Consequences

Deeper research is measurable and bounded, while large campaigns are no longer
silently truncated by the dashboard. A rolling application budget is deliberately
more conservative than a provider calendar-day quota; other project clients are
outside this ledger. Search coverage remains incomplete by design and exported
public contact candidates never become outreach authorization. No new service,
model, high-impact capability or public contact database is introduced.
