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
temporary container file, and prints SHA-256. Encrypt dump before off-host
transfer.

## Restore drill

Restore into a separate disposable Compose project/database, never over live
data first:

Copy dump into PostgreSQL container, create a distinct `agent_restore` database,
then run `pg_restore --dbname agent_restore --clean --if-exists --no-owner
--no-acl`. Confirm exact source/destination names before running. A future
restore-check script will automate this without ever targeting live database.

Validate migration table, row counts, task/audit linkage, vector extension,
and application readiness against restored database. Delete test database only
after validation and with exact target confirmed.

## Volume backup

Use a stopped/consistent snapshot or a purpose-built backup container that
mounts one named volume read-only. Encrypt archives because Hermes/OmniRoute
state can contain personal data and credentials. Document image versions with
each archive. Never assume copying live database volume files is a valid
PostgreSQL backup.

## Objectives

Initial proposed RPO: 24 hours; RTO: 4 hours. These are design targets, not met
SLAs, until scheduled encrypted backups and restore drills are automated.
