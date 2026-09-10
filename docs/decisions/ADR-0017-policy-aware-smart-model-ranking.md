# ADR-0017 — Policy-aware smart model ranking

Status: Accepted

Date: 2026-09-10

## Context

The first live OpenRouter canary failed even though the key and catalog requests
were valid. The completion sent seven entries in OpenRouter's `models` fallback
array, while the current API permits at most three. Reducing the list exposed a
second failure: the strongest catalog models had no endpoint matching the
request's combined no-training and zero-data-retention policy.

The operator also asked for an automatic “best available, then next best”
switch. Free inventory, endpoint availability, and benchmark metadata change;
a fixed model list cannot remain a reliable quality order. Quality ranking must
not weaken zero-cost or résumé-privacy boundaries.

## Decision

- Preserve the previously requested provider hierarchy for interactive Hermes:
  OmniRoute `free/default`, OpenRouter, then lazy local Qwen. Do not pretend that
  heterogeneous OmniRoute and OpenRouter catalogs have one comparable benchmark
  when OmniRoute does not expose equivalent quality metadata.
- Keep `free/default` instead of OmniRoute's `auto/*` routes as the primary hard
  free boundary. In the pinned OmniRoute release, an empty tier filter can fail
  open; a benchmark label is not authorization to spend.
- For governed career drafting, build a fresh OpenRouter order from models that
  pass exact `:free`, text-modality, and zero catalog-price checks. When ZDR is
  enabled, also require a currently active model entry from `/endpoints/zdr`.
- Prefer an explicit operator model priority when configured. Otherwise use the
  live catalog's bounded Artificial Analysis fields with a transparent score:
  50% intelligence, 30% coding, and 20% agentic. Declared structured-output,
  response-format, tool, and reasoning support plus context length break ties.
  Missing metrics count as missing evidence, not as a high score.
- Send no more than one primary and three fallback models in one OpenRouter
  request. Let OpenRouter fail through those candidates in order and retain the
  existing 15-minute cooldown when a later candidate succeeds.
- Treat an empty or application-schema-invalid HTTP 200 as a model-quality
  failure. Count and audit that reservation, cool the selected route for 15
  minutes, and give the next-ranked remaining model its own reserved request.
- Keep `data_collection=deny` and ZDR enabled by default. If privacy-compatible
  free capacity disappears, fall back to local Qwen instead of silently using a
  stronger retained/training-eligible endpoint.
- Continue validating the selected model and provider-reported zero cost after
  completion. Benchmark and endpoint metadata may affect ordering, never
  authorization.
- Classify known provider errors into bounded internal codes and avoid emitting
  raw provider envelopes, account identifiers, prompts, or credentials.

## Alternatives considered

- Keep the eight-entry request: rejected because OpenRouter returns HTTP 400
  before inference.
- Use `openrouter/free` for governed career drafts: rejected because OpenRouter
  documents random selection after compatibility filtering, not strongest-first
  selection or returned-cost governance.
- Disable ZDR/data-collection restrictions to access stronger benchmark models:
  rejected as an automatic behavior because résumé privacy outranks model score.
- Reorder all providers from a single synthetic score: rejected because the
  current OmniRoute catalog does not expose equivalent benchmark and endpoint
  telemetry, making the comparison false precision.
- Add a privileged always-on router service: rejected for this milestone because
  the narrow existing career adapter can enforce the requirement without a new
  credential-bearing network service or execution path.

## Consequences

The user key can now complete the harmless strict-free/ZDR canary, and provider
contract drift no longer creates an invalid fallback array. The best overall
free benchmark model may be excluded when it has no policy-compatible endpoint;
that is expected fail-closed behavior. A semantic retry can consume another
account-wide free request, so every retry receives another PostgreSQL
reservation. The interactive OpenRouter fallback still uses OpenRouter's
capability-filtered random free router, while the narrower career path has
deterministic benchmark order and PostgreSQL accounting. Local Qwen remains the
final continuity route and stays unloaded until called.
