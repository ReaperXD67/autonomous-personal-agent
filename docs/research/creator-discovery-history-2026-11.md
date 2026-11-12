# Creator discovery history — focused upstream comparison

Observed 12 November 2026. Decision: a small original PostgreSQL guard reusing
Hermes's canonical identities and existing locks. No upstream code, dependency
or additional skill pack was copied or installed.

| Source/version | Exact license and maintenance evidence | Fit and decision |
|---|---|---|
| [PostgreSQL 17 locking documentation](https://www.postgresql.org/docs/17/explicit-locking.html) | [PostgreSQL License](https://www.postgresql.org/about/licence/); 17 is supported. Hermes already pins PostgreSQL 17/pgvector 0.8.1 by image digest. | **Adapt:** transaction advisory locks, consistent order and fresh reads after waits. MVCC reads alone cannot serialize a concurrent writer. Reuse the existing runtime; no new service. |
| [listmonk commit 32078ede6d87c83f4948cc592c76bee91d629f0b](https://github.com/knadh/listmonk/tree/32078ede6d87c83f4948cc592c76bee91d629f0b) | [GNU AGPL version 3](https://github.com/knadh/listmonk/blob/32078ede6d87c83f4948cc592c76bee91d629f0b/LICENSE) inspected at that commit. Official repository was unarchived and last pushed November 12 at 02:15 UTC when checked. | **Defer integration/copying:** [subscriber SQL](https://github.com/knadh/listmonk/blob/32078ede6d87c83f4948cc592c76bee91d629f0b/queries/subscribers.sql) keeps global blocklist separate from per-list subscriptions and preserves it during upsert. This supports a global identity boundary, but Hermes holds are preservation instructions, not unsubscribes. Adding a second Go/PostgreSQL mailing application and AGPL source would add lifecycle/licensing/data migration cost without solving native immutable-draft protection. No code reused. |
| Hermes `2f583dc3764b1e19f1f006ed95119a9818a9990d` | Existing MIT repository and reviewed implementation. | **Reuse:** canonical `research_identity`, sorted creator-email/profile/platform locks, issued payload hashes, durable draft/action/reply tables and count-only audit. Keep active-only explicit research semantics separate. |

The expected benefit is narrow: routine bulk saves preserve known existing work
after expiry/failure or across campaigns. This does not promise more coverage,
replies, users or faster sends.

Measured proof: current main failed the new expired/failed cross-campaign insert
assertion. The changed implementation passed twenty-one PostgreSQL scenario groups,
including nine global-history groups and original research regressions, plus 32
focused unit tests. Real
writer-budget/sender waits ran against a network-isolated disposable database,
with no provider, model or SMTP operation. Full-stack verification and deployment
remain separate release gates; see ADR-0046 and the engineering log.
