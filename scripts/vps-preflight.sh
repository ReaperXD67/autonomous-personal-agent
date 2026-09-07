#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

failures=0
warnings=0
pass() { printf '[PASS] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; warnings=$((warnings + 1)); }
fail() { printf '[FAIL] %s\n' "$1" >&2; failures=$((failures + 1)); }
env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" .env | tail -n 1
}

if [[ "$(uname -s)" == 'Linux' ]]; then
  pass 'Linux host detected'
else
  fail 'VPS deployment requires Linux'
fi
if [[ "$(id -u)" -eq 0 ]]; then
  fail 'run deployment as a dedicated unprivileged user, not root'
else
  pass 'deployment user is non-root'
fi

for command_name in docker git curl sed grep stat; do
  if command -v "$command_name" >/dev/null 2>&1; then
    pass "$command_name is installed"
  else
    fail "$command_name is required"
  fi
done

if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    pass 'Docker Engine is reachable'
    docker info --format 'Docker {{.ServerVersion}} | CPUs {{.NCPU}} | memory {{.MemTotal}} bytes'
    if docker info --format '{{json .SecurityOptions}}' | grep -q 'rootless'; then
      pass 'Docker rootless mode detected'
    else
      warn 'Docker is rootful; only trusted operators may access its socket'
    fi
  else
    fail 'Docker Engine is not reachable by the deployment user'
  fi
  if docker compose version >/dev/null 2>&1; then
    pass 'Docker Compose plugin is available'
  else
    fail 'Docker Compose v2 plugin is required'
  fi
fi

if [[ ! -f .env ]]; then
  fail 'missing .env; run ./scripts/vps-init-env.sh'
else
  mode="$(stat -c '%a' .env)"
  if (( (8#$mode & 077) == 0 )); then
    pass ".env permissions are owner-only ($mode)"
  else
    fail ".env permissions are too broad ($mode); run chmod 600 .env"
  fi
  if git check-ignore -q .env; then
    pass '.env is ignored by Git'
  else
    fail '.env is not ignored by Git'
  fi
  if grep -Eq '^[A-Z0-9_]+=CHANGE_ME' .env; then
    fail '.env still contains a placeholder'
  else
    pass '.env contains no CHANGE_ME placeholders'
  fi
  if [[ "$(env_value APP_ENV)" == 'production' ]]; then
    pass 'APP_ENV is production'
  else
    fail 'APP_ENV must be production on the VPS'
  fi
  trusted_hosts="$(env_value TRUSTED_HOSTS)"
  if [[ "$trusted_hosts" == 'localhost,127.0.0.1' || "$trusted_hosts" == '127.0.0.1,localhost' ]]; then
    pass 'Host allowlist is private-loopback only'
  else
    fail 'TRUSTED_HOSTS must remain localhost,127.0.0.1 for the private VPS profile'
  fi
  if [[ "$(env_value MAIL_TRANSPORT)" == 'mailpit' ]]; then
    fail 'Mailpit test transport must not be configured on the VPS'
  else
    pass 'Mailpit is not configured for VPS delivery'
  fi
fi

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  fail 'repository checkout is dirty; deploy an exact reviewed commit or release tag'
else
  pass "repository checkout is clean at $(git rev-parse --short=12 HEAD)"
fi

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1 && [[ -f .env ]]; then
  rendered_config="$(mktemp)"
  chmod 600 "$rendered_config"
  cleanup_rendered_config() { rm -f -- "$rendered_config"; }
  trap cleanup_rendered_config EXIT
  compose_model=(
    docker compose
    --profile agent
    --profile local-model
    --profile side-effects
    --profile side-effects-test
  )
  if "${compose_model[@]}" config > "$rendered_config"; then
    pass 'Compose configuration renders successfully'
  else
    fail 'Compose configuration is invalid'
  fi
  published_count="$(grep -c 'published:' "$rendered_config" || true)"
  loopback_count="$(grep -c 'host_ip: 127.0.0.1' "$rendered_config" || true)"
  if [[ "$published_count" -gt 0 && "$published_count" -eq "$loopback_count" ]]; then
    pass "all $published_count declared host ports bind to IPv4 loopback"
  else
    fail 'every published Compose port must have host_ip 127.0.0.1'
  fi
  if grep -Eq '/var/run/docker.sock|network_mode: host|privileged: true' "$rendered_config"; then
    fail 'rendered Compose contains a forbidden privileged host boundary'
  else
    pass 'no Docker socket, host network, or privileged container is configured'
  fi
  rm -f -- "$rendered_config"
  trap - EXIT
fi

warn 'verify SSH key-only login, disabled root/password login, automatic updates, NTP, and provider firewall rules manually'
warn 'create an encrypted off-host backup target and alerting destination before relying on this host'

printf '\nPreflight summary: %s failure(s), %s warning(s)\n' "$failures" "$warnings"
if [[ "$failures" -ne 0 ]]; then
  exit 1
fi
printf '%s\n' 'PREFLIGHT_OK: private VPS application boundary is ready to start.'
