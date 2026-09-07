#!/usr/bin/env bash
set -euo pipefail

umask 077
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
backup_root="$project_root/backups"
mkdir -p -- "$backup_root"
cd "$project_root"

env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" .env | tail -n 1
}
database="$(env_value POSTGRES_DB)"
database="${database:-agent}"
database_user="$(env_value POSTGRES_USER)"
database_user="${database_user:-agent_app}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
requested_path="${1:-$backup_root/agent-$stamp.dump}"
destination="$(realpath -m -- "$requested_path")"
case "$destination" in
  "$backup_root"/*) ;;
  *) printf 'Backup destination must stay inside %s\n' "$backup_root" >&2; exit 1 ;;
esac

if [[ -e "$destination" || -e "$destination.sha256" ]]; then
  printf 'Refusing to overwrite existing backup: %s\n' "$destination" >&2
  exit 1
fi
temporary_path="$(mktemp "$backup_root/.backup.tmp.XXXXXX")"
cleanup() { rm -f -- "$temporary_path"; }
trap cleanup EXIT

docker compose exec -T postgres pg_dump \
  --format=custom --no-owner --no-acl --username "$database_user" "$database" \
  > "$temporary_path"
chmod 600 "$temporary_path"
mv -- "$temporary_path" "$destination"
trap - EXIT

(
  cd "$backup_root"
  sha256sum "$(basename -- "$destination")" > "$(basename -- "$destination").sha256"
  chmod 600 "$(basename -- "$destination").sha256"
)
printf 'Backup created: %s\n' "$destination"
printf '%s\n' 'This local dump is not the off-host copy: encrypt it, transfer it, and run the restore drill.'
