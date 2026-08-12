# Manual setup remaining

Everything that can be safely automated without creating accounts or accepting
third-party terms is scripted. The remaining work requires user-owned choices or
credentials.

## Verified current workstation status

On 2026-08-12, OmniRoute already had a scoped key and exposed 79 model routes,
`free/default` completed a live smoke request, and Hermes returned `HERMES_OK`
through that endpoint. Do not repeat provider onboarding unless you want to add
or replace a provider. The local Ollama/Qwen download is the only unfinished
inference setup.

## Path A — completely local inference

This has no token charge and sends prompts only to the local Ollama container.

```powershell
./scripts/local-model.ps1
```

The first run downloads the pinned Ollama image and the `qwen3:8b` Q4 model
(approximately 5.2 GB for the model). Verify GPU placement afterward:

```powershell
docker compose --profile local-model exec ollama ollama ps
```

The `PROCESSOR` column should show GPU use. The internal OpenAI-compatible URL is
`http://ollama:11434/v1`. In OmniRoute, add an Ollama/OpenAI-compatible provider
using that internal URL and model `qwen3:8b`; then include it as the final
fallback in `auto`. Do not publish port 11434.

## Path B — add or replace a stronger free-tier provider

1. Open <http://127.0.0.1:20128>.
2. Finish OmniRoute's local administrator onboarding.
3. Use the live free-tier catalog to connect providers whose current terms you
   accept. Prefer no-card and explicit free-forever options; quotas can change.
4. Add a Nemotron route from a provider offering it at no charge if available.
5. Create a scoped inference-only endpoint key.
6. Put it in ignored `.env` as `OMNIROUTE_API_KEY`. Never paste it into Git,
   documentation, logs, or chat.
7. Run `./scripts/agent-smoke.ps1`.

## Connect Hermes

After either inference path works:

1. Run `docker compose --profile agent exec hermes hermes setup`.
2. Select a custom OpenAI-compatible provider.
3. Use `http://omniroute:20128/v1` and the scoped OmniRoute key for the routed
   path, or `http://ollama:11434/v1` and `qwen3:8b` for local-only use.
4. Keep command approval enabled.
5. Do not mount the host filesystem or Docker socket.
6. Test a harmless read-only prompt before adding messaging or MCP tools.

## Accounts intentionally not automated

- Telegram bot creation and user allowlisting
- Email/Google/GitHub OAuth consent
- Provider sign-up and acceptance of provider terms
- VPS purchase, DNS, TLS, WireGuard, and backup destination
- Any secret, recovery code, payment method, or identity verification

Those actions carry identity, legal, financial, or external-state consequences
and must remain user-owned.
