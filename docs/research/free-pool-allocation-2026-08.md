# Free inference pool allocation assessment

Date: 2026-08-29

## Finding

OpenRouter and OmniRoute were not actually competing on this workstation.
OpenRouter was disabled and had no key in ignored `.env`. OmniRoute exposed 79
route IDs: 39 automatic/combo IDs and 40 concrete models, all reported as
OVHfree. No OpenRouter-owned route was present.

OmniRoute is a gateway, not the owner of a universal free-token balance. Its
published 1.53-billion-token figure is a theoretical aggregate across roughly
43 provider pools; each provider still requires its own enrollment and terms.
Source: <https://github.com/diegosouzapw/OmniRoute/blob/release/v3.8.50/docs/reference/FREE_TIERS.md>

## Upstream constraints

- OpenRouter's free-model request allowance is account-wide. Switching among
  free models improves availability but does not multiply the shared limit.
  Source: <https://openrouter.ai/docs/api-reference/limits>
- OpenRouter supports ordered cross-model fallback and publishes live model
  pricing/metadata. Sources:
  <https://openrouter.ai/docs/guides/routing/model-fallbacks> and
  <https://openrouter.ai/docs/api/api-reference/models/get-models>
- OpenRouter provider selection can require no data collection and zero data
  retention. Sources:
  <https://openrouter.ai/docs/guides/routing/provider-selection> and
  <https://openrouter.ai/docs/guides/features/zdr>
- OmniRoute `fill-first` drains the first eligible quota before moving through a
  combo. Its per-request budget header requires a positive number, strict
  fallback applies to automatic routing, and the pinned automatic free filter
  is fail-open when no candidate survives. Therefore it does not replace the
  career adapter's exact zero-price plus returned-zero-cost checks. Source:
  <https://github.com/diegosouzapw/OmniRoute/blob/release/v3.8.49/docs/routing/AUTO-COMBO.md>
- Hermes supports an ordered `fallback_providers` chain, including a custom
  OpenAI-compatible endpoint. Eligible provider/rate/connection failures move
  to the next entry for that turn. Source:
  <https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/fallback-providers.md>

## Implemented allocation

| Purpose | First route | Continuity route | Accounting |
|---|---|---|---|
| Discovery, filtering, scoring, preflight | Deterministic code | Not applicable | No model tokens |
| Hermes planning and chat | OmniRoute `free/default` | Internal Ollama `qwen3:8b` | Provider-owned quota; doctor inspects pool ownership |
| Career application drafts | Direct OpenRouter ranked exact `:free` chain, opt-in | Internal Ollama `qwen3:8b` | Atomic PostgreSQL daily reservation and provider-reported zero cost |

The bounded automatic preparation set is now ranked by match score and then
freshness before tasks are created. This directs the scarce hosted career pool
to the highest-value new opportunities. Free-cap exhaustion, hosted privacy
unavailability, or provider failure degrades to local Qwen rather than paid
inference.

The same OpenRouter account should not also be connected to OmniRoute. Calls
made through OmniRoute would consume the same upstream account allowance without
entering the career PostgreSQL ledger. `scripts/doctor.ps1 -Agent` detects and
warns about this overlap.

## Live observation boundary

An authenticated `free/default` metadata probe completed through OmniRoute and
returned token counts, but the response contained no cost field. It therefore
proved availability, not an exact zero-cost receipt. The existing
`agent-smoke.ps1` completion and current all-OVHfree ownership support use of
that route; adding a paid-capable provider requires a fresh route review.

No OpenRouter credential or authenticated completion was available during this
assessment. The direct hosted career path remains prepared, not operational,
until the user installs a scoped inference key and
`./scripts/openrouter.ps1 -Smoke` returns an exact zero-cost result.
