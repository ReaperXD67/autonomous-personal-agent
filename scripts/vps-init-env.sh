#!/usr/bin/env bash
set -euo pipefail

umask 077
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
example_path="$project_root/.env.example"
target_path="$project_root/.env"

if [[ -e "$target_path" ]]; then
  printf '%s\n' '.env already exists; refusing to overwrite deployment secrets.' >&2
  printf '%s\n' 'Use a reviewed credential-rotation procedure for an existing deployment.' >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  printf '%s\n' 'openssl is required to generate deployment secrets.' >&2
  exit 1
fi

random_hex() {
  openssl rand -hex "$1"
}

control_token="$(random_hex 32)"
postgres_password="$(random_hex 24)"
redis_password="$(random_hex 24)"
omniroute_password="$(random_hex 24)"
omniroute_api_secret="$(random_hex 32)"
omniroute_jwt_secret="$(random_hex 32)"
omniroute_machine_salt="$(random_hex 32)"
temporary_path="$(mktemp "$project_root/.env.tmp.XXXXXX")"
cleanup() {
  rm -f -- "$temporary_path"
}
trap cleanup EXIT

while IFS= read -r line || [[ -n "$line" ]]; do
  case "$line" in
    APP_ENV=*) printf '%s\n' 'APP_ENV=production' ;;
    TRUSTED_HOSTS=*) printf '%s\n' 'TRUSTED_HOSTS=localhost,127.0.0.1' ;;
    CONTROL_API_TOKEN=*) printf 'CONTROL_API_TOKEN=%s\n' "$control_token" ;;
    POSTGRES_PASSWORD=*) printf 'POSTGRES_PASSWORD=%s\n' "$postgres_password" ;;
    REDIS_PASSWORD=*) printf 'REDIS_PASSWORD=%s\n' "$redis_password" ;;
    OMNIROUTE_INITIAL_PASSWORD=*) printf 'OMNIROUTE_INITIAL_PASSWORD=%s\n' "$omniroute_password" ;;
    OMNIROUTE_API_KEY_SECRET=*) printf 'OMNIROUTE_API_KEY_SECRET=%s\n' "$omniroute_api_secret" ;;
    OMNIROUTE_JWT_SECRET=*) printf 'OMNIROUTE_JWT_SECRET=%s\n' "$omniroute_jwt_secret" ;;
    OMNIROUTE_MACHINE_ID_SALT=*) printf 'OMNIROUTE_MACHINE_ID_SALT=%s\n' "$omniroute_machine_salt" ;;
    OMNIROUTE_API_KEY=*) printf '%s\n' 'OMNIROUTE_API_KEY=' ;;
    SMTP_PASSWORD=*) printf '%s\n' 'SMTP_PASSWORD=' ;;
    *) printf '%s\n' "$line" ;;
  esac
done < "$example_path" > "$temporary_path"

chmod 600 "$temporary_path"
mv -- "$temporary_path" "$target_path"
trap - EXIT

printf '%s\n' 'Created ignored .env for a private production-mode VPS.'
printf '%s\n' 'No provider keys or SMTP credential were created; add those manually when needed.'
