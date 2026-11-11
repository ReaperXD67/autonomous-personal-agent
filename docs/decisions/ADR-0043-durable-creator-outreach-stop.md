# ADR-0043: Stop every creator email at the durable send boundary

Status: Accepted

Date: 2026-11-11

## Context

Pausing a finite creator run withdraws delegated authority but does not revoke
individually approved email packets. Deleting a desktop reviewer schedule also
cannot cancel PostgreSQL tasks. An owner stop must survive process restart,
interrupted cleanup and later resumption without replaying an old approval.

## Decision

Store a creator campaign's stop flag, epoch and owner/audit metadata in
PostgreSQL. The authenticated campaign `/outreach/stop` route commits the stop,
increments the epoch on transition, disables daily discovery and pauses running
grants before cancelling eligible queued/pending email tasks through the existing
task lifecycle. Running tasks receive cancellation requests. Cleanup does not
hold campaign rows while acquiring task locks.

Freeze the current epoch in newly prepared creator email contexts. Preparation,
delegated start, exact approval and the final receipt boundary reject a stopped
campaign; an epoch mismatch also rejects pre-stop packets after resumption. The
final campaign lock serializes the stop with entry into an actual send. Ordinary
campaign edits cannot clear the stop fields.

Resumption is a separate authenticated request requiring the literal
`start mailing now` confirmation. It does not restore cancelled tasks, old
approvals, paused grants or discovery. Existing contact holds, suppression,
complete reply evidence, reviews and unsent drafts are independent and retained.
Career actions and campaigns outside the requested creator IDs are unaffected.

## Consequences and limits

A committed stop blocks unstarted creator sends even if task cleanup is
interrupted or a stale Redis message is replayed. A send already inside the
receipt boundary cannot be recalled; returned in-flight/ambiguous counts remain
distinct from cancellation and acceptance.

This adds migration 031 and no service, dependency, account or SMTP permission.
If the control plane is offline, a saved operator instruction is intent, not a
database cancellation. Keep existing sending workers offline and apply/verify
the scoped stop before restoring egress. Deploying code, applying a migration,
committing the live stop and cancelling live tasks are separate outcomes.
