# ADR-0012 — Verified free OpenRouter routing for résumé drafts

Status: Accepted

## Context

The local Qwen3 8B route is private and predictable but materially weaker than
current large hosted models. The operator has an OpenRouter account and wants
the strongest currently free model first, automatic fallback when a model is
rate-limited or unavailable, and no accidental use of paid balance.

OpenRouter's free-model allowance is account-wide: changing model IDs does not
create another daily quota. Model fallback still improves availability because
individual free models and providers can have separate saturation or outages.
Free inventory and model quality also change, so a fixed unverified model list
would decay quickly.

OmniRoute remains Hermes' general model gateway. Its `auto/*:free` tier filter
is fail-open in the pinned upstream release, however, so it is not a sufficient
hard cost boundary for résumé drafting. Career drafts also need per-request
OpenRouter fallback metadata and an authoritative usage record.

## Decision

- Add a narrow OpenRouter adapter to the existing egress-enabled career worker.
  It is an inference provider adapter, not another agent or tool executor.
- Fetch the live text-model catalog and accept a model only when its exact ID
  ends in `:free` and prompt, completion, and request prices all parse to zero.
- Rank verified candidates by an operator-overridable exact priority, followed
  by structured-output capability and context size. Send a bounded ordered
  chain through OpenRouter's native `models` fallback field. When a later model
  succeeds, cool earlier candidates for 15 minutes so the worker starts with
  the last working point in the sequence instead of paying repeated latency.
- Default to `data_collection=deny` and per-request zero data retention. If
  those policies remove all upstream capacity, use local Qwen instead of
  weakening privacy automatically.
- Reject a successful response unless its selected model belongs to the
  preverified chain and its returned usage cost is exactly zero.
- Reserve every hosted call atomically in PostgreSQL and retain only routing/
  token/cost metadata. Default to 40 reservations below the 50-request shared
  quota; allow 900 only after the operator explicitly confirms OpenRouter's
  USD 10 all-time purchase threshold. `/key.is_free_tier` does not prove that
  amount, and the adapter never accepts the management key needed to query it.
- Keep local Qwen as the continuity route. OpenRouter is opt-in because enabling
  it sends the selected job description and résumé to a hosted service.
- Keep the OpenRouter inference key only in ignored `.env` and the career
  worker. OmniRoute/Hermes onboarding remains a separate operator action.

## Alternatives

- Use `openrouter/free`: rejected as the primary route because selection is
  random and does not implement the requested quality order.
- Use OmniRoute `auto/*:free`: retained for general experimentation, but not as
  a strict cost boundary because the current tier filter is documented as
  fail-open when the filtered pool is empty.
- Configure one static hosted model: rejected because free variants are volatile
  and a single free endpoint has poor availability.
- Remove local inference: rejected because the shared free quota and hosted
  capacity have no availability guarantee.

## Consequences

The career worker becomes the only core application service holding this hosted
inference credential. Résumé data crosses the machine boundary only after an
explicit opt-in. Privacy filtering may make hosted inference less available,
and model fallbacks cannot bypass the account-wide daily free quota. A real key
and harmless completion are still required before the hosted path can be called
operational; unit tests and catalog research alone are not that proof.
