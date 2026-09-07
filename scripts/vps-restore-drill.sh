#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
backup_root="$project_root/backups"
cd "$project_root"

env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" .env | tail -n 1
}
database="$(env_value POSTGRES_DB)"
database="${database:-agent}"
database_user="$(env_value POSTGRES_USER)"
database_user="${database_user:-agent_app}"

if [[ $# -gt 0 ]]; then
  backup_path="$1"
else
  backup_path="$(find "$backup_root" -maxdepth 1 -type f -name '*.dump' -printf '%T@ %p\n' |
    sort -nr | head -n 1 | cut -d' ' -f2-)"
fi
if [[ -z "${backup_path:-}" || ! -f "$backup_path" ]]; then
  printf '%s\n' 'No backup dump is available for the restore drill.' >&2
  exit 1
fi
resolved_backup="$(realpath -e -- "$backup_path")"
case "$resolved_backup" in
  "$backup_root"/*) ;;
  *) printf 'Restore drill accepts dumps only from %s\n' "$backup_root" >&2; exit 1 ;;
esac
checksum_path="$resolved_backup.sha256"
if [[ ! -f "$checksum_path" ]]; then
  printf 'Missing checksum sidecar: %s\n' "$checksum_path" >&2
  exit 1
fi
(
  cd "$backup_root"
  sha256sum --check "$(basename -- "$checksum_path")"
)

suffix="$(openssl rand -hex 6)"
restore_database="agent_restore_$suffix"
if [[ ! "$restore_database" =~ ^agent_restore_[0-9a-f]{12}$ || "$restore_database" == "$database" ]]; then
  printf '%s\n' 'Generated restore database name failed its safety check.' >&2
  exit 1
fi
created=false
cleanup() {
  if [[ "$created" == true ]]; then
    docker compose exec -T postgres psql -X -A -t -U "$database_user" -d postgres \
      -v ON_ERROR_STOP=1 -c \
      "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$restore_database' AND pid <> pg_backend_pid();" \
      >/dev/null || true
    docker compose exec -T postgres dropdb --if-exists --username "$database_user" "$restore_database" \
      >/dev/null || true
  fi
}
trap cleanup EXIT

docker compose exec -T postgres createdb --username "$database_user" --template template0 "$restore_database"
created=true
docker compose exec -T postgres pg_restore --exit-on-error --no-owner --no-acl \
  --username "$database_user" --dbname "$restore_database" < "$resolved_backup"

scalar() {
  docker compose exec -T postgres psql -X -A -t -U "$database_user" \
    -d "$restore_database" -v ON_ERROR_STOP=1 -c "$1" | tr -d '[:space:]'
}
[[ "$(scalar "SELECT count(*) FROM pg_extension WHERE extname='vector';")" == '1' ]]
migration_count="$(scalar 'SELECT count(*) FROM schema_migrations;')"
task_count="$(scalar 'SELECT count(*) FROM agent_tasks;')"
audit_count="$(scalar 'SELECT count(*) FROM audit_events;')"
orphan_count="$(scalar 'SELECT count(*) FROM audit_events a LEFT JOIN agent_tasks t ON t.id=a.task_id WHERE a.task_id IS NOT NULL AND t.id IS NULL;')"
if [[ "$migration_count" -lt 4 || "$orphan_count" -ne 0 ]]; then
  printf '%s\n' 'Restored database invariants failed.' >&2
  exit 1
fi

probe='import os
from urllib.parse import urlsplit, urlunsplit
from app.store import Database
parts = urlsplit(os.environ["DATABASE_URL"])
url = urlunsplit((parts.scheme, parts.netloc, "/" + os.environ["RESTORE_DATABASE"], "", ""))
raise SystemExit(0 if Database(url).check() else "application database readiness failed")'
docker compose run --rm --no-deps -e "RESTORE_DATABASE=$restore_database" \
  control-api python -c "$probe"

printf 'Restore drill passed: %s\n' "$(basename -- "$resolved_backup")"
printf 'Disposable database: %s\n' "$restore_database"
printf 'Migrations: %s; tasks: %s; audits: %s; orphan audits: 0\n' \
  "$migration_count" "$task_count" "$audit_count"
