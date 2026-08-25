# Manual setup remaining

Everything that can be safely automated without creating accounts or accepting
third-party terms is scripted. The remaining work requires user-owned choices or
credentials.

## Verified current workstation status

OmniRoute has a scoped key and exposed 79 model routes, `free/default` completed
a live smoke request, and Hermes returned `HERMES_READY_OK` through that endpoint
again on 2026-08-15. On
2026-08-15, local Qwen3 8B returned exactly `LOCAL_MODEL_OK` and Ollama reported
GPU placement. No inference download or provider onboarding remains required for
basic testing. The complete default `./scripts/readiness.ps1` gate passed all six
configured paths on 2026-08-15; repeat setup only to add or replace a provider.
The career smoke on the same date fetched 100 live public listings, retained 5
fresh matches for its exact synthetic target, and persisted a structured local
Qwen application draft.

On 2026-08-25, the isolated side-effect smoke used a synthetic candidate and
local fixtures to prepare and execute one exact application, deliver one exact
email to Mailpit, and refuse a second application after finding the durable
receipt. The Playwright and Mailpit images are installed locally. This verifies
the mechanism, not every real employer form or an external mailbox.

## First personal career mission

This is the only personal-data input needed for the current workflow:

1. Run `./scripts/open-dashboard.ps1 -LocalModel -SideEffectsTest -CopyToken`.
2. Paste the token into the local dashboard and clear the clipboard.
3. Create a mission with your actual target titles, locations, true skills, and
   plain-text résumé.
4. Choose a freshness window and activate the mission.
5. Optionally add exact employer board slugs from public Ashby, Greenhouse, or Lever
   career URLs. No credential is needed; the system intentionally will not guess
   a company list or scrape login-gated sites.
6. Add actual contact identity, enable auto-prepare only after checking the
   score/cap, and run the local side-effect smoke before a real destination.
7. Review each exact application in **Approvals**. Explicitly answer required
   questions; CAPTCHA, login, and unsupported multi-step forms stay manual.

See [dashboard and career missions](dashboard-and-career.md). The reviewed
single-page adapter and duplicate protection are ready; real-site compatibility
is still destination-specific and never bypasses exact approval.

## Real email transport

The local Mailpit path needs no account. To send real mail, the user must choose
a provider and create its SMTP/OAuth credential under that provider's terms.
The current implementation supports authenticated SMTP with verified TLS:

1. Put `MAIL_TRANSPORT=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`,
   `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_TLS_MODE=starttls` (or `ssl`) in
   ignored deployment secrets.
2. Run `./scripts/up.ps1 -SideEffects` to recreate the isolated executor.
3. Prepare a harmless message to an address you own, review the exact
   sender/recipient/subject/body, approve once, and verify provider delivery.

Gmail and Microsoft also expose OAuth send APIs, but OAuth consent and token
storage are not implemented here. Do not weaken account security by automating
interactive login or storing a personal browser profile in the action worker.

## Path A — completely local inference

This has no token charge and sends prompts only to the local Ollama container.
It is already operational on this workstation; the command is an idempotent
recheck or repair path.

```powershell
./scripts/local-model.ps1
```

If missing, the command downloads the pinned Ollama image and the `qwen3:8b` Q4
model (approximately 5.2 GB for the model). An installed matching model is reused
so temporary registry outages do not disable local testing. Use `-ForcePull`
only when deliberately refreshing it. Verify GPU placement afterward:

```powershell
docker compose --profile local-model exec ollama ollama ps
```

The `PROCESSOR` column should show GPU use. The internal OpenAI-compatible URL is
`http://ollama:11434/v1`. In OmniRoute, add an Ollama/OpenAI-compatible provider
using that internal URL and model `qwen3:8b`; then include it as the final
fallback in `auto`. Do not publish port 11434.

## Path B — add or replace a stronger free-tier provider

1. Open <http://127.0.0.1:20128>.
2. Sign in to the existing local administrator account.
3. Use the live free-tier catalog to connect providers whose current terms you
   accept. Prefer no-card and explicit free-forever options; quotas can change.
4. Add a Nemotron route from a provider offering it at no charge if available.
5. Create a scoped inference-only endpoint key.
6. Put it in ignored `.env` as `OMNIROUTE_API_KEY`. Never paste it into Git,
   documentation, logs, or chat.
7. Run `./scripts/agent-smoke.ps1`.

## Reconfigure Hermes (optional)

Hermes is already connected to OmniRoute and returned `HERMES_OK`. Use these
steps only to repair it or switch the route:

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
- job-site accounts, screening/legal/consent answers, CAPTCHA/identity checks,
  and each exact final application approval
- Any secret, recovery code, payment method, or identity verification

Those actions carry identity, legal, financial, or external-state consequences
and must remain user-owned.
