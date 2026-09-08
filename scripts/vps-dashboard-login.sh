#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" .env | tail -n 1
}
control_port="$(env_value CONTROL_API_PORT)"
control_port="${control_port:-8080}"
bootstrap="$(docker compose exec -T control-api python - <<'PY'
import json
import os
from urllib.request import Request, urlopen

request = Request(
    "http://127.0.0.1:8000/v1/auth/browser-bootstrap",
    headers={"Authorization": f"Bearer {os.environ['CONTROL_API_TOKEN']}"},
    method="POST",
)
with urlopen(request, timeout=10) as response:
    print(json.load(response)["code"])
PY
)"
if [[ ! "$bootstrap" =~ ^[A-Za-z0-9_-]{32,128}$ ]]; then
  printf '%s\n' 'The control API did not return a valid browser bootstrap.' >&2
  exit 1
fi
printf '%s\n' 'Open this one-use URL through your existing SSH tunnel within 90 seconds:'
printf 'http://127.0.0.1:%s/#bootstrap=%s\n' "$control_port" "$bootstrap"
