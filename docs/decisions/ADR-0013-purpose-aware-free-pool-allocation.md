# ADR-0013 — Purpose-aware free inference pool allocation

Status: Accepted

## Context

The system has three inference mechanisms with different guarantees: OmniRoute
aggregates separately enrolled provider free tiers for Hermes, the career worker
can call OpenRouter directly with exact free/cost checks, and Ollama provides
private local continuity. Treating them as one interchangeable pool would hide
quota ownership and could let two consumers exhaust the same account outside
the authoritative local budget.

The previous committed Hermes example used generic `auto` even though the live
route and smoke used `free/default`. Automatic career preparation also selected
new opportunities in source arrival order, not by expected value.

## Decision

- Keep model-free work model-free: discovery, freshness filtering, matching,
  scoring, scheduling, and form preflight stay deterministic.
- Route Hermes planning/chat through OmniRoute `free/default`; do not use generic
  `auto` as a zero-spend policy boundary.
- Add internal Ollama `qwen3:8b` as Hermes' ordered provider-failure fallback.
- Reserve direct OpenRouter for career application drafts. Retain live exact
  `:free`/zero-price admission, ordered quality fallback, returned zero-cost
  validation, privacy filters, and the atomic PostgreSQL daily cap.
- Do not put the same OpenRouter account in OmniRoute by default. Add a doctor
  warning if both direct OpenRouter and an OmniRoute OpenRouter route are seen.
- Sort new matches by score and then freshness before choosing the bounded
  automatic-preparation set.

## Alternatives

- Route everything through OmniRoute: rejected because the pinned automatic
  free filter is fail-open and responses do not provide the direct adapter's
  exact cost attestation or shared PostgreSQL reservation.
- Route all work through OpenRouter: rejected because general chat would consume
  the same account-wide allowance needed for high-value career drafts.
- Route all work locally: remains a privacy option, but wastes already available
  hosted free capacity and provides weaker reasoning on the observed 8 GB GPU.
- Configure OpenRouter both directly and inside OmniRoute: rejected by default
  because local usage views would undercount the account-wide upstream quota.

## Consequences

The pools degrade independently and OpenRouter's bounded allowance is directed
to the strongest/freshest career matches. Hermes retains useful free hosted
reasoning and local continuity without receiving the career key. The doctor can
detect configuration drift, but it cannot prove all third-party account usage.
OmniRoute provider additions and free-tier terms still require operator review,
and no hosted service is guaranteed to remain free or available.
