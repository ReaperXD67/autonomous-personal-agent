# Backup and restore

## What is authoritative

1. PostgreSQL: tasks, approvals, audits, outbox, memory, embeddings.
2. Hermes volume: optional identity, sessions, skills, configuration.
3. OmniRoute volume: optional provider configuration and encrypted credentials.
4. Redis: non-authoritative queue/cache; back up for faster recovery, never as sole record.

## PostgreSQL backup

From project root, create a custom-format dump without PowerShell binary-pipe
corruption:

```powershell
./scripts/backup.ps1
```

Script dumps inside container, copies exact binary to ignored `backups/`, removes
the temporary container file, and writes a `.sha256` sidecar. Encrypt both before
off-host transfer.

## Restore drill

Run the automated drill against a randomly named disposable database, never the
live database:

```powershell
./scripts/restore-drill.ps1
```

The script verifies SHA-256, creates only a checked `agent_restore_<random>`
database, restores without changing ownership, validates migrations, task/audit
linkage and the vector extension, probes it through application database code,
then removes only the disposable database. Migration rollback policy is
roll-forward by default; for incompatible changes, stop writers and restore the
last verified dump into a new database before changing the application target.

## Volume backup

Use a stopped/consistent snapshot or a purpose-built backup container that
mounts one named volume read-only. Encrypt archives because Hermes/OmniRoute
state can contain personal data and credentials. Document image versions with
each archive. Never assume copying live database volume files is a valid
PostgreSQL backup.

## Objectives

Initial proposed RPO: 24 hours; RTO: 4 hours. Restore mechanics are now tested,
but these remain design targets—not SLAs—until encrypted off-host scheduling and
alerting are configured.
