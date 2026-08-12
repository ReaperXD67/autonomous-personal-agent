# Hermes integration boundary

Compose profile `agent` runs official Nous Research image
`nousresearch/hermes-agent:v2026.8.3`, pinned by multi-platform digest. Hermes
state lives in named volume `hermes_data`; no host filesystem or Docker socket
is mounted.

The container receives OmniRoute's internal URL and a local gateway key. For a
zero-cost local route:

1. Start the agent profile: `./scripts/up.ps1 -Agent`.
2. Run `./scripts/configure-free-models.ps1`.
3. The script creates/reuses a scoped OmniRoute key, configures `free/default`,
   sets Hermes' custom endpoint and 64K context guard, then verifies inference.

No model-provider credential is required for the verified OVHcloud + AI Horde
route. `OMNIROUTE_API_KEY` authenticates only Hermes to the local gateway; it is
not a paid provider key.

Approval mode stays manual. MCP stays empty. Terminal, host filesystem, and
external messaging credentials are intentionally not provisioned here.

Dashboard is not published by Compose. Release `v2026.8.3` correctly refuses
non-loopback binding without a registered authentication provider; add a
reviewed override only after configuring password or OAuth authentication.

Upstream source: <https://github.com/NousResearch/hermes-agent/releases/tag/v2026.8.3>
