#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

smoke=false
if [[ "${1:-}" == '--smoke' ]]; then
  smoke=true
elif [[ $# -gt 0 ]]; then
  printf 'Unknown option: %s\n' "$1" >&2
  exit 2
fi

env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" .env | tail -n 1
}
model="$(env_value LOCAL_MODEL)"
model="${model:-qwen3:8b}"
compose=(docker compose -f docker-compose.yml)
gpu=false
if command -v nvidia-smi >/dev/null 2>&1 &&
    docker info --format '{{json .Runtimes}}' | grep -q '"nvidia"'; then
  compose+=(-f docker-compose.gpu.yml)
  gpu=true
fi

"${compose[@]}" --profile agent up -d --no-build ollama
for _ in $(seq 1 60); do
  state="$("${compose[@]}" --profile agent ps --format '{{.Health}}' ollama 2>/dev/null || true)"
  if [[ "$state" == 'healthy' ]]; then break; fi
  sleep 2
done
if [[ "${state:-}" != 'healthy' ]]; then
  printf '%s\n' 'Ollama daemon did not become healthy.' >&2
  exit 1
fi

installed="$("${compose[@]}" --profile agent exec -T ollama ollama list)"
if ! grep -Eq "^${model//./\\.}[[:space:]]" <<<"$installed"; then
  printf 'Downloading local fallback model %s without loading it...\n' "$model"
  "${compose[@]}" --profile agent exec -T ollama ollama pull "$model"
else
  printf 'Local fallback model is cached: %s\n' "$model"
fi

if [[ "$smoke" == true ]]; then
  response="$("${compose[@]}" --profile agent exec -T ollama ollama run "$model" --think=false \
    'Reply with exactly LOCAL_MODEL_OK and nothing else.')"
  if [[ "${response//$'\r'/}" != 'LOCAL_MODEL_OK' ]]; then
    printf '%s\n' 'Local fallback smoke returned an unexpected response.' >&2
    exit 1
  fi
  placement="$("${compose[@]}" --profile agent exec -T ollama ollama ps)"
  if [[ "$gpu" == true ]] && ! grep -q 'GPU' <<<"$placement"; then
    printf '%s\n' 'Local inference passed but Ollama did not report GPU placement.' >&2
    exit 1
  fi
  "${compose[@]}" --profile agent exec -T ollama ollama stop "$model" >/dev/null
  printf '%s\n' 'LOCAL_MODEL_OK; Qwen was unloaded after the explicit fallback smoke.'
else
  printf '%s\n' 'Qwen remains unloaded until a real final-fallback request arrives.'
fi
