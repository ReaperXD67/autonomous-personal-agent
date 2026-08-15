# ADR-0007 — Durable execution lifecycle and restore policy

Status: Accepted

## Context

Crash recovery prevented tasks from remaining permanently `running`, but a
long handler could outlive its lease, a stale worker had no unique ownership
token, retries were immediate, cancellation was absent, exhausted work looked
like an ordinary failure, and backups had no automated restore evidence.

## Decision

- Give every claim a unique PostgreSQL lease ID and worker identity.
- Renew long-running leases periodically; refuse completion from a stale lease.
- Derive a minimum risk from the allowlisted capability and permit callers only
  to escalate it.
- Support immediate queued cancellation and cooperative running cancellation.
- Delay recovered claims exponentially within configured bounds.
- Represent exhausted claims as `dead_lettered` and expose authenticated
  inspection without automatic replay.
- Use forward migrations normally. For incompatible rollback, restore a verified
  dump into a new database and switch only after validation; never restore over
  the live database first.

## Alternatives

- Depend on process shutdown hooks and fixed long leases.
- Retry immediately until a generic failure status.
- Let cancellation kill containers.
- Restore backups directly over the authoritative database.
- Introduce a queue framework before these semantics are stable.

## Reasoning

Lease ownership prevents split-brain completion. Cooperative cancellation keeps
the database/audit path authoritative and avoids turning container control into
an application capability. Bounded backoff protects dependencies from retry
storms. Explicit dead letters preserve operator visibility. Disposable restore
validation proves recoverability without risking live state.

## Consequences

Long handlers must observe the interruption signal and stay within the heartbeat
contract. Dead letters require human diagnosis before any future replay API.
Backups are proven restorable locally but still require user-owned encryption,
off-host storage, scheduling, retention, and alerts for production RPO/RTO.
