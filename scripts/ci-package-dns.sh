#!/usr/bin/env bash
# Disposable GitHub-hosted CI only; never configure a local or production host.
set -euo pipefail

if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_OS:-}" != Linux ||
      "${RUNNER_ENVIRONMENT:-}" != github-hosted ]]; then
  printf '%s\n' 'Package DNS repair requires a disposable GitHub-hosted Linux runner.' >&2
  exit 2
fi

pinned_base='mcr.microsoft.com/playwright/python:v1.63.0-noble@sha256:72bd171a9ffc2b4b59532aaa6210e21014d07093120dc25528870c0b840da1f0'
probe_code=$(cat <<'PY'
import json, socket, sys
failed = False
for host in ("azure.archive.ubuntu.com", "security.ubuntu.com", "deb.debian.org"):
    try:
        addresses = sorted({row[4][0] for row in socket.getaddrinfo(host, 80)})
        print(json.dumps({"host": host, "addresses": addresses}), flush=True)
    except OSError as exc:
        failed = True
        print(json.dumps({"host": host, "error": type(exc).__name__}), flush=True)
sys.exit(1 if failed else 0)
PY
)

check_runner() { timeout 25s python3 -c "$probe_code"; }
check_container() {
  timeout 25s docker run --rm --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --entrypoint python3 "$pinned_base" -c "$probe_code"
}

# Pull the same reviewed base needed by the build, without any account credentials.
docker pull "$pinned_base"
if check_runner && check_container; then
  exit 0
fi

# A real failed lookup permits one ephemeral per-link resolver repair. This does
# not alter DNSSEC, TLS, APT signatures, image/package pins or Docker networking.
build_interface=$(ip -4 route show default | awk 'NR == 1 {print $5}')
if [[ ! "$build_interface" =~ ^[a-zA-Z0-9_.:-]+$ ]]; then
  printf '%s\n' 'A valid default IPv4 interface is required for CI DNS repair.' >&2
  exit 2
fi
sudo resolvectl dns "$build_interface" 1.1.1.1 1.0.0.1
sudo resolvectl flush-caches
check_runner
check_container
