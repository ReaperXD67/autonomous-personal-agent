#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

docker compose exec -T control-api python - <<'PY'
from __future__ import annotations

import json
import os
import time
from urllib.request import Request, urlopen
from uuid import uuid4

BASE_URL = "http://127.0.0.1:8000"
HEADERS = {
    "Authorization": f"Bearer {os.environ['CONTROL_API_TOKEN']}",
    "Content-Type": "application/json",
}


def request(method: str, path: str, body: dict | None = None) -> dict:
    payload = json.dumps(body).encode() if body is not None else None
    with urlopen(
        Request(BASE_URL + path, data=payload, headers=HEADERS, method=method),
        timeout=10,
    ) as response:
        return json.load(response)


def wait_for_task(task_id: str) -> dict:
    for _ in range(60):
        task = request("GET", f"/v1/tasks/{task_id}")
        if task["status"] in {
            "succeeded",
            "failed",
            "rejected",
            "cancelled",
            "dead_lettered",
        }:
            return task
        time.sleep(0.5)
    raise RuntimeError(f"task {task_id} did not finish")


safe = request(
    "POST",
    "/v1/tasks",
    {
        "title": "Private VPS smoke: safe queue path",
        "kind": "foundation.echo",
        "payload": {"message": "vps-core-ok"},
        "risk_level": "low",
        "requested_by": "vps-smoke",
        "idempotency_key": f"vps-safe:{uuid4()}",
    },
)
safe = wait_for_task(safe["id"])
if safe["status"] != "succeeded" or safe["output"]["echo"] != "vps-core-ok":
    raise RuntimeError("safe task path failed")

gated = request(
    "POST",
    "/v1/tasks",
    {
        "title": "Private VPS smoke: approval path",
        "kind": "foundation.echo",
        "payload": {"message": "vps-approval-ok"},
        "risk_level": "high",
        "requested_by": "vps-smoke",
        "idempotency_key": f"vps-gated:{uuid4()}",
    },
)
if gated["status"] != "pending_approval":
    raise RuntimeError("high-risk task bypassed approval")
request(
    "POST",
    f"/v1/tasks/{gated['id']}/decision",
    {
        "decision": "approved",
        "actor": "vps-smoke-approver",
        "reason": "Harmless private deployment validation",
    },
)
gated = wait_for_task(gated["id"])
if gated["status"] != "succeeded" or gated["output"]["echo"] != "vps-approval-ok":
    raise RuntimeError("approved task path failed")

print(f"Safe task passed: {safe['id']}")
print(f"Approval task passed: {gated['id']}")
print("VPS_SMOKE_OK")
PY
