#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
cd "$project_root"

docker compose -f docker-compose.yml --profile agent exec -T hermes python - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

import yaml


def json_request(url: str, key: str, max_bytes: int = 4_000_000) -> dict:
    request = Request(
        url,
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    with urlopen(request, timeout=20) as response:
        payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise RuntimeError("provider response exceeded the health-probe limit")
    result = json.loads(payload)
    if not isinstance(result, dict):
        raise RuntimeError("provider returned an invalid health envelope")
    return result


config = yaml.safe_load(Path("/opt/data/config.yaml").read_text(encoding="utf-8"))
fallbacks = config.get("fallback_providers") or []
expected = [
    ("openrouter", "openrouter/free"),
    ("custom", os.environ.get("LOCAL_MODEL", "qwen3:8b")),
]
actual = [(item.get("provider"), item.get("model")) for item in fallbacks]
if config.get("model", {}).get("default") != "free/default" or actual != expected:
    raise RuntimeError("managed model route order is not active")
print("MODEL_ROUTE_OK: OmniRoute -> OpenRouter free -> local Qwen")

omni = json_request("http://omniroute:20128/v1/models", os.environ["OPENAI_API_KEY"])
if not omni.get("data"):
    raise RuntimeError("OmniRoute returned no models")
print("OMNIROUTE_HEALTH_OK")

openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
if not openrouter_key:
    raise RuntimeError("OpenRouter fallback key is not configured")
openrouter = json_request(
    "https://openrouter.ai/api/v1/models?output_modalities=text", openrouter_key
)
if not openrouter.get("data"):
    raise RuntimeError("OpenRouter returned no text models")
print("OPENROUTER_HEALTH_OK")

local = json_request("http://ollama:11434/api/tags", "local-no-auth", 1_000_000)
model = os.environ.get("LOCAL_MODEL", "qwen3:8b")
installed = {
    item.get("name") for item in local.get("models", []) if isinstance(item, dict)
}
if model not in installed:
    raise RuntimeError("configured local fallback model is not cached")
print("OLLAMA_HEALTH_OK: fallback model cached")

loaded = json_request("http://ollama:11434/api/ps", "local-no-auth", 1_000_000)
running = {
    item.get("name") for item in loaded.get("models", []) if isinstance(item, dict)
}
if model in running:
    print("QWEN_LIFECYCLE_OK: loaded by a recent fallback request")
else:
    print("QWEN_LIFECYCLE_OK: cached and unloaded")
PY
