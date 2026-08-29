# Hermes integration boundary

Compose profile `agent` runs official Nous Research image
`nousresearch/hermes-agent:v2026.8.3`, pinned by multi-platform digest. Hermes
state lives in named volume `hermes_data`; no host filesystem or Docker socket
is mounted.

The container receives OmniRoute's internal URL and an API-key placeholder.
After OmniRoute onboarding:

1. Create a scoped OmniRoute inference key from its loopback-only dashboard.
2. Put that key in ignored `.env` as `OMNIROUTE_API_KEY`.
3. Render `config.example.yaml` into Hermes state, or use `hermes setup` inside
   the container and choose custom OpenAI-compatible provider.
4. Keep the primary model at `free/default` and the internal Ollama fallback
   from the template. A generic `auto` route is not this project's spend guard.
5. Restart Hermes and verify a harmless model request.

The intended chain is OmniRoute `free/default` first, then internal
`http://ollama:11434/v1` model `qwen3:8b` on eligible provider failures. Start
both optional profiles for that continuity path. The non-secret
`HERMES_LOCAL_FALLBACK_KEY` value only satisfies OpenAI-client compatibility;
Ollama does not authenticate it.

Approval mode stays manual. MCP stays empty. Terminal, host filesystem, and
external messaging credentials are intentionally not provisioned here.

Dashboard is not published by Compose. Release `v2026.8.3` correctly refuses
non-loopback binding without a registered authentication provider; add a
reviewed override only after configuring password or OAuth authentication.

Upstream source: <https://github.com/NousResearch/hermes-agent/releases/tag/v2026.8.3>
