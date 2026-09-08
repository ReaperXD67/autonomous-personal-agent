# Hermes integration boundary

Compose profile `agent` runs official Nous Research image
`nousresearch/hermes-agent:v2026.8.3`, pinned by multi-platform digest. Hermes
state lives in named volume `hermes_data`; no host filesystem or Docker socket
is mounted.

The container receives OmniRoute's internal URL and scoped provider keys from
ignored environment configuration. A networkless one-shot service copies the
reviewed template into the private Hermes volume before every agent start.
After OmniRoute onboarding:

1. Create a scoped OmniRoute inference key from its loopback-only dashboard.
2. Put that key in ignored `.env` as `OMNIROUTE_API_KEY`.
3. Create a dedicated OpenRouter inference key and put it in ignored `.env` as
   `OPENROUTER_API_KEY`.
4. Start the agent profile; it renders `config.example.yaml` automatically.
5. Keep the primary at `free/default`, followed by `openrouter/free`, then the
   internal Ollama fallback. A generic `auto` route is not the primary policy.
6. Verify the primary and provider-health checks with harmless requests.

The intended chain is OmniRoute `free/default`, OpenRouter `openrouter/free`,
then internal `http://ollama:11434/v1` model `qwen3:8b`. The agent profile
supervises the small Ollama daemon but does not load Qwen during startup; the
first final-fallback request loads weights and the idle timeout unloads them.
`-LocalModel` performs an explicit canary only. The non-secret
`HERMES_LOCAL_FALLBACK_KEY` value only satisfies OpenAI-client compatibility;
Ollama does not authenticate it.

Approval mode stays manual. MCP stays empty. Terminal, host filesystem, and
external messaging credentials are intentionally not provisioned here.

Dashboard is not published by Compose. Release `v2026.8.3` correctly refuses
non-loopback binding without a registered authentication provider; add a
reviewed override only after configuring password or OAuth authentication.

Upstream source: <https://github.com/NousResearch/hermes-agent/releases/tag/v2026.8.3>
