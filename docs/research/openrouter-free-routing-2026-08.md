# OpenRouter free-routing assessment — 2026-08-29

## Question

Can the existing agent use today's strongest OpenRouter free models in order,
fall through model-specific failures automatically, protect the operator's paid
balance, and remain usable after hosted quota is exhausted?

## Primary-source findings

- OpenRouter documents 50 free-model requests per day for accounts below its
  credit threshold and 1,000 per day after at least USD 10 of credit purchases.
  That allowance is shared across free models, not a token bucket per model.
  Source: <https://openrouter.ai/docs/faq>
- An ordered `models` array provides cross-model fallback for rate limits,
  downtime, moderation refusal, and context errors. The response `model` is the
  model that actually served the completion.
  Source: <https://openrouter.ai/docs/guides/routing/model-fallbacks>
- A `:free` variant is zero-cost but may have reduced availability. The
  `openrouter/free` router is also free but chooses an available model randomly,
  so it is a continuity option rather than a deterministic quality policy.
  Sources: <https://openrouter.ai/docs/guides/routing/model-variants/free> and
  <https://openrouter.ai/docs/guides/routing/routers/free-router>
- The model catalog exposes IDs, modality, context, supported parameters, and
  per-unit pricing. That permits a runtime allowlist based on current data
  instead of trusting a name or a stale static list.
  Source: <https://openrouter.ai/docs/api/api-reference/models/get-models>
- `data_collection=deny` excludes providers that may store/train on inputs;
  per-request `zdr=true` restricts routing to zero-retention endpoints.
  OpenRouter says its own prompt logging is opt-in, while upstream endpoint
  policies still vary.
  Sources: <https://openrouter.ai/docs/guides/routing/provider-selection>,
  <https://openrouter.ai/docs/guides/features/zdr>, and
  <https://openrouter.ai/docs/guides/privacy/data-collection>
- Completion responses now include token and cost accounting without another
  request. Router metadata can expose the selected endpoint and successful
  fallback attempt without exposing prompt text.
  Sources: <https://openrouter.ai/docs/cookbook/administration/usage-accounting>
  and <https://openrouter.ai/docs/guides/features/router-metadata>
- A normal inference key can query its own limit metadata at `/key`, but
  `is_free_tier` only says whether credits were purchased before and does not
  prove the USD 10 all-time threshold. The credits endpoint can reveal total
  purchases but requires a more powerful management key; the agent should never
  receive that management credential. The higher allowance must therefore be
  an explicit operator assertion.
  Sources: <https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key>
  and <https://openrouter.ai/docs/api/api-reference/credits/get-credits>
- OmniRoute 3.8.49 supports priority/fill-first combos and quota-aware routing,
  but its documented `auto/<category>:<tier>` filtering is fail-open when no
  candidate matches. That behavior is useful for availability but unsuitable as
  the only guarantee that paid routes cannot run.
  Source: <https://github.com/diegosouzapw/OmniRoute/blob/release/v3.8.49/docs/routing/AUTO-COMBO.md>

## Observed catalog

An unauthenticated catalog query on 2026-08-29 returned 18 text models whose IDs
ended in `:free` and whose prompt/completion prices parsed as zero. Notable
current candidates included NVIDIA Nemotron 3 Ultra 550B A55B, GLM 5.2,
Nemotron 3 Super 120B A12B, MiniMax M3, Gemma 4 31B, and Inkling. This is an
observation, not a permanent availability claim; runtime discovery is required.

The default quality order starts with the current OpenRouter free collection's
Nemotron flagship, then uses large reasoning/structured-output alternatives.
Operators can replace the exact priority through an environment variable, but
configuration validation refuses any entry without `:free`.

## Resulting boundary

The hosted adapter is useful for bounded drafting and reasoning, not a free
infinite-compute pool. It cannot create extra quota by rotating model names. The
continuity strategy is therefore hosted quality while the shared allowance is
available, followed by local Qwen with no token bill. Real hosted validation
remains pending until the operator installs a scoped inference key and runs the
harmless smoke command.
