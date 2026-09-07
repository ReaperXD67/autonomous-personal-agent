#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

enable_side_effects=false
enable_agent=false
enable_local_model=false
for argument in "$@"; do
  case "$argument" in
    --side-effects) enable_side_effects=true ;;
    --agent) enable_agent=true ;;
    --local-model) enable_local_model=true ;;
    *) printf 'Unknown option: %s\n' "$argument" >&2; exit 2 ;;
  esac
done

"$script_dir/vps-preflight.sh"

env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" .env | tail -n 1
}
if [[ "$enable_side_effects" == true && "$(env_value MAIL_TRANSPORT)" != 'smtp' ]]; then
  printf '%s\n' '--side-effects requires a complete TLS SMTP configuration in .env' >&2
  exit 1
fi
if [[ "$enable_agent" == true ]]; then
  omniroute_key="$(env_value OMNIROUTE_API_KEY)"
  if [[ -z "$omniroute_key" || "$omniroute_key" == CHANGE_ME* ]]; then
    printf '%s\n' '--agent requires completed OmniRoute onboarding and a scoped endpoint key' >&2
    exit 1
  fi
fi
if [[ "$enable_local_model" == true ]] && ! command -v nvidia-smi >/dev/null 2>&1; then
  printf '%s\n' '--local-model requires a configured NVIDIA container runtime and GPU' >&2
  exit 1
fi

compose=(docker compose)
if [[ "$enable_side_effects" == true ]]; then compose+=(--profile side-effects); fi
if [[ "$enable_agent" == true ]]; then compose+=(--profile agent); fi
if [[ "$enable_local_model" == true ]]; then compose+=(--profile local-model); fi

"${compose[@]}" up -d --build --remove-orphans

control_port="$(env_value CONTROL_API_PORT)"
control_port="${control_port:-8080}"
for _ in $(seq 1 60); do
  if curl --fail --silent --show-error "http://127.0.0.1:${control_port}/health/ready" |
      grep -q '"status":"ready"'; then
    break
  fi
  sleep 2
done
if ! curl --fail --silent "http://127.0.0.1:${control_port}/health/ready" |
    grep -q '"status":"ready"'; then
  printf '%s\n' 'control API did not become ready within 120 seconds' >&2
  "${compose[@]}" ps
  exit 1
fi

"${compose[@]}" ps
"$script_dir/vps-smoke.sh"
printf '%s\n' "PRIVATE_VPS_READY at commit $(git rev-parse --short=12 HEAD)"
printf '%s\n' "Connect from your workstation with: ssh -L ${control_port}:127.0.0.1:${control_port} deploy@YOUR_VPS"
