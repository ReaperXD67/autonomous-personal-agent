#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

enable_side_effects=false
test_local_model=false
bootstrap_omniroute=false
no_build=false
for argument in "$@"; do
  case "$argument" in
    --side-effects) enable_side_effects=true ;;
    --agent) ;; # compatibility: the full VPS path now always includes Hermes
    --local-model) test_local_model=true ;;
    --bootstrap-omniroute) bootstrap_omniroute=true ;;
    --no-build) no_build=true ;;
    *) printf 'Unknown option: %s\n' "$argument" >&2; exit 2 ;;
  esac
done

"$script_dir/vps-preflight.sh"

env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" .env | tail -n 1
}
if [[ "$(env_value VPS_SIDE_EFFECTS_ENABLED)" == 'true' ]]; then
  enable_side_effects=true
fi
if [[ "$enable_side_effects" == true && "$(env_value MAIL_TRANSPORT)" != 'smtp' ]]; then
  printf '%s\n' '--side-effects requires a complete TLS SMTP configuration in .env' >&2
  exit 1
fi

compose=(docker compose -f docker-compose.yml)
if command -v nvidia-smi >/dev/null 2>&1 &&
    docker info --format '{{json .Runtimes}}' | grep -q '"nvidia"'; then
  compose+=(-f docker-compose.gpu.yml)
  printf '%s\n' 'NVIDIA runtime detected; lazy Qwen fallback will use the GPU.'
else
  printf '%s\n' 'No NVIDIA container runtime detected; lazy Qwen fallback will use CPU.'
fi

build_argument=(--build)
if [[ "$no_build" == true ]]; then build_argument=(--no-build); fi

if [[ "$bootstrap_omniroute" == true ]]; then
  "${compose[@]}" --profile agent up -d "${build_argument[@]}" redis omniroute
  "${compose[@]}" --profile agent ps redis omniroute
  printf '%s\n' 'OMNIROUTE_BOOTSTRAP_READY'
  printf '%s\n' 'Tunnel port 20128, finish OmniRoute onboarding, then add its scoped key and the OpenRouter key to .env.'
  exit 0
fi

omniroute_key="$(env_value OMNIROUTE_API_KEY)"
if [[ -z "$omniroute_key" || "$omniroute_key" == CHANGE_ME* ]]; then
  printf '%s\n' 'Full startup requires completed OmniRoute onboarding and a scoped endpoint key.' >&2
  printf '%s\n' 'Run ./scripts/vps-up.sh --bootstrap-omniroute first on a new host.' >&2
  exit 1
fi
openrouter_key="$(env_value OPENROUTER_API_KEY)"
if [[ -z "$openrouter_key" || "$openrouter_key" == CHANGE_ME* ]]; then
  printf '%s\n' 'Full startup requires a scoped OpenRouter key for the secondary free route.' >&2
  exit 1
fi

compose+=(--profile agent)
if [[ "$enable_side_effects" == true ]]; then compose+=(--profile side-effects); fi

"${compose[@]}" up -d "${build_argument[@]}" --remove-orphans
local_arguments=()
if [[ "$test_local_model" == true ]]; then local_arguments+=(--smoke); fi
"$script_dir/vps-local-model.sh" "${local_arguments[@]}"

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
"$script_dir/vps-model-health.sh"
printf '%s\n' "PRIVATE_VPS_READY at commit $(git rev-parse --short=12 HEAD)"
printf '%s\n' "Connect from your workstation with: ssh -L ${control_port}:127.0.0.1:${control_port} deploy@YOUR_VPS"
printf '%s\n' 'Then run ./scripts/vps-dashboard-login.sh on the VPS and open its one-use URL.'
