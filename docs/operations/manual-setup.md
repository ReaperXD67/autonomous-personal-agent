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

The OpenRouter free-only adapter, managed Hermes fallback position, ordered
fallback tests, usage ledger, and UI are implemented. On 2026-09-10, the
user-owned inference key passed the harmless live smoke through
`inclusionai/ling-3.0-flash-fin:free` at provider-reported cost zero. This proves
the direct governed provider path, not a forced end-to-end Hermes failover. A
synthetic full career draft later exercised both strict-ZDR candidates; the
first returned schema-invalid output, the second returned empty output, and the
audited chain correctly completed through local Qwen. Hosted draft quality is
therefore not claimed from the canary alone.

On 2026-08-25, the isolated side-effect smoke used a synthetic candidate and
local fixtures to prepare and execute one exact application, deliver one exact
email to Mailpit, and refuse a second application after finding the durable
receipt. The Playwright and Mailpit images are installed locally. This verifies
the mechanism, not every real employer form or an external mailbox.

## First personal career mission

This is the only personal-data input needed for the current workflow:

1. Run `./scripts/open-dashboard.ps1 -SideEffectsTest`.
2. Confirm the dashboard opens as connected. The one-use URL fragment is
   exchanged automatically; no token paste or clipboard cleanup is needed.
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

## KarixMC creator outreach

Real creator discovery requires a user-owned Google Cloud project with YouTube
Data API v3 enabled and a restricted API key in ignored `YOUTUBE_API_KEY`.
External delivery also requires the SMTP setup below. Neither account, key, nor
provider terms are created automatically.

On this workstation, the readiness check on 2026-09-05 found a non-placeholder
YouTube key in ignored `.env`; final validation loaded it into a healthy
`job-worker`, but no real SMTP transport is configured. Presence/loading is not
live discovery proof. The key must still be exercised by one deliberate
campaign scan and checked for the intended provider-side API restriction
without exposing it.

After creating those user-owned credentials, the remaining local activation is
guided and secret-safe:

```powershell
./scripts/promotion.ps1
./scripts/promotion.ps1 -LocalTest
./scripts/promotion.ps1 -ConfigureYouTube
./scripts/promotion.ps1 -ConfigureGmail
./scripts/promotion.ps1 -OpenDashboard
```

Run the local test before configuring external mail. It sends only to Mailpit,
makes no YouTube discovery request, omits saved SMTP credentials from its test
containers, and cleans up its synthetic campaign records. The two credential
prompts are hidden. The YouTube key is tested before it is saved; Gmail delivery
is not claimed until one approved message reaches an inbox you own. Run commands
separately so failures never require re-entering an already validated credential.

After adding the key, recreate the core stack, open **Creator campaigns**, and
run one scan. Channel/video results prove discovery; container health alone does
not. The API does not return creator emails. Add only a reviewed public business
contact, source URL, and basis note, then approve each exact email separately.
Reply reading/classification, compensation, contracts/disclosures, point grants,
and placement-result entry remain manual. See
[creator outreach operations](creator-outreach.md).

## Real email transport

The local Mailpit path needs no account. To send real mail, the user must choose
a provider and create its SMTP/OAuth credential under that provider's terms.
The current implementation supports authenticated SMTP with verified TLS:

1. Run `./scripts/promotion.ps1 -ConfigureSMTP` for local prompts and a hidden
   credential entry. Alternatively put `MAIL_TRANSPORT=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`,
   `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_TLS_MODE=starttls` (or `ssl`) in
   ignored deployment secrets.
2. Run `./scripts/up.ps1 -SideEffects` to recreate the isolated executor.
3. Run `./scripts/promotion.ps1 -CheckSMTP` to check the configured connection,
   TLS, and authentication through an audited task without sending mail.
4. Review and approve one authorized message's exact sender/recipient/subject/body.
   Inspect the durable SMTP acceptance separately from recipient inbox delivery;
   an owned test inbox can establish the latter for that one message.

Gmail and Microsoft also expose OAuth send APIs, but OAuth consent and token
storage are not implemented here. Do not weaken account security by automating
interactive login or storing a personal browser profile in the action worker.

## First private VPS

Repository work is prepared, but these host/account actions require the owner:

1. Provision a dedicated supported 64-bit Linux VPS. Use SSH keys, a non-root
   deploy user, disabled root/password login, automatic security updates, NTP,
   and a provider firewall that admits SSH only from trusted source addresses.
2. Install Docker Engine and the Compose plugin from Docker's official package
   repository. Keep the Docker socket local and accessible only to trusted
   operators; Docker access is effectively host-root authority.
3. Clone the repository, check out the exact reviewed release commit/tag, run
   `./scripts/vps-init-env.sh`, and keep `.env` mode `600`.
4. On a new host, run `./scripts/vps-up.sh --bootstrap-omniroute`, tunnel port
   20128, complete OmniRoute onboarding, and securely add its scoped inference
   key plus a dedicated OpenRouter inference key to `.env`. Rotate any key after
   suspected terminal/log exposure.
5. Run `./scripts/vps-preflight.sh` and resolve every failure. Review its two
   host-owned warnings rather than treating them as machine-proven.
6. Start the full stack with `./scripts/vps-up.sh`. It always includes Hermes,
   OmniRoute, OpenRouter fallback configuration, and an idle Ollama daemon.
   `--local-model` is only an explicit Qwen canary. Set
   `VPS_SIDE_EFFECTS_ENABLED=true` only after TLS SMTP is ready.
7. Install boot/recovery management with `./scripts/vps-install-service.sh`,
   then confirm `hermes.service` and `hermes-model-health.timer` are enabled.
8. Run `./scripts/vps-backup.sh` and `./scripts/vps-restore-drill.sh`; then
   configure encrypted off-host transfer, retention, scheduling, and alerts.
9. Reach the dashboard only through SSH/WireGuard/Tailscale. With SSH, use
   `ssh -L 8080:127.0.0.1:8080 deploy@YOUR_VPS`, then run
   `./scripts/vps-dashboard-login.sh` and open its one-use URL; no domain or
   public TLS is required for this private profile.
10. Configure health/disk/queue/task-failure alerts and write down the rollback
    commit plus the side-effect reconciliation procedure before daily use.

The private single-user alpha can be used after those checks and the relevant
provider proofs pass. Public or multi-user availability remains blocked on
OIDC/RBAC, rate limits/body limits, TLS, step-up identity, centralized secret
management, signed releases, and an incident-response runbook.

## Current free-pool allocation

| Work | Route | Why |
|---|---|---|
| Job/creator discovery, freshness, matching, scoring, preflight | Deterministic code | Zero tokens and reproducible decisions |
| General Hermes planning/chat | OmniRoute `free/default` → OpenRouter `openrouter/free` → internal Qwen | Ordered availability fallback; general OpenRouter calls are outside the career ledger |
| Highest-score/freshest career drafts | Direct strict OpenRouter `:free` chain when enabled | Live price and returned-cost attestation plus a PostgreSQL daily cap |
| Any hosted quota/outage/privacy failure | Internal `qwen3:8b` | No provider quota and résumé stays local |

Do not separately connect the same OpenRouter account inside OmniRoute unless
you intentionally accept a third consumer of its account-wide quota. The
explicit Hermes fallback and career adapter already share that account, while
only career calls participate in the PostgreSQL reservation counter. The
“1.53B free tokens” shown in OmniRoute material is a theoretical sum across many
separately enrolled provider tiers, not a credit grant from OmniRoute. The last
observed workstation catalog had 40 concrete OVHfree routes and no OpenRouter
route inside OmniRoute.

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

The `PROCESSOR` column should show GPU use during the canary. The internal
OpenAI-compatible URL is `http://ollama:11434/v1`. Hermes uses it only after
OmniRoute and the explicit OpenRouter free fallback fail. Normal agent startup
supervises Ollama and caches Qwen but does not load its weights;
`local-model.ps1` deliberately exercises the route and unloads it afterward.
Do not publish port 11434 and do not switch the primary to generic `auto`.

## Path B — enable the ranked OpenRouter free chain

Do not send the key in chat. Create a dedicated normal inference key in the
OpenRouter dashboard; do not create or supply a management key. Give the key the
lowest practical spend limit/expiry that fits your use so an upstream policy
mistake cannot consume the account balance freely.

```powershell
./scripts/openrouter.ps1 -Configure
./scripts/openrouter.ps1 -Smoke
```

`-Configure` reads the key through a hidden prompt, validates it with `/key`,
fetches the current catalog, prints only non-secret tier/limit/model metadata,
and writes the key to ignored `.env`. The default selector intersects exact
zero-cost `:free` text models with the live active-ZDR endpoint inventory, then
ranks by the catalog's intelligence/coding/agentic benchmark fields with
capability/context tie-breakers. An explicit `OPENROUTER_MODEL_PRIORITY` remains
the operator override. `-Smoke` sends one primary plus at most three fallbacks,
keeps no-training/ZDR filters, and refuses success unless OpenRouter reports
exact zero cost. Career drafts also treat empty/schema-invalid output as a
failure, cool that model, and reserve a separate attempt for the next-ranked
candidate before using local Qwen. The safe default is 40 local reservations below the shared
50-request allowance. If the account has purchased at least USD 10 in total,
configure the documented 1,000-request tier explicitly and preserve 100
requests of headroom:

```powershell
./scripts/openrouter.ps1 -Configure -ConfirmTenCreditsPurchased
```

Do not infer that threshold merely because the account has some balance:
`/key.is_free_tier` only reports whether credits were ever purchased, not the
amount, and querying all-time purchases requires a management key that this
agent deliberately refuses.

After a draft, open **Settings** and verify the actual model, provider, privacy
mode, fallback attempt, tokens, and zero recorded credits. Free model inventory,
endpoint privacy, availability, and benchmark metadata are volatile. On
2026-09-10 the strict privacy intersection contained two eligible routes; both
lacked published benchmark values, so capability/context and a stable tie-break
determined their order. Switching models helps model/provider-specific limits,
but it does not bypass the shared account-wide free quota; local Qwen is the
final route.

The same key is available to Hermes for its second interactive route. Those
general calls do not reserve from the career worker's PostgreSQL counter, so
apply a provider-side limit and monitor total key usage. Do not also add the
account inside OmniRoute unless you deliberately accept another uncoordinated
consumer. Never rely on `auto/<category>:free` as a hard spend boundary in
OmniRoute 3.8.49 because its tier filtering is documented as fail-open when no
candidates match.

## Path C — add or replace another OmniRoute free-tier provider

1. Open <http://127.0.0.1:20128>.
2. Sign in to the existing local administrator account.
3. Use the live free-tier catalog to connect providers whose current terms you
   accept. Prefer no-card and explicit free-forever options; quotas can change.
4. Add a Nemotron route from a provider offering it at no charge if available.
5. Create a scoped inference-only endpoint key.
6. Put it in ignored `.env` as `OMNIROUTE_API_KEY`. Never paste it into Git,
   documentation, logs, or chat.
7. Run `./scripts/agent-smoke.ps1`.

Keep Hermes on `free/default`. OmniRoute's per-request budget header accepts a
positive budget and applies only to automatic routing; it is not an exact-zero
attestation for this project's persisted route. If a newly added provider can
charge, create and validate an explicit provider-only free combo before putting
it anywhere in the Hermes path.

## Reconfigure Hermes (optional)

Hermes is already connected to OmniRoute and returned `HERMES_OK`. Use these
steps only to repair it or switch the route:

1. Run `docker compose --profile agent exec hermes hermes setup`.
2. Select a custom OpenAI-compatible provider.
3. Use `http://omniroute:20128/v1`, model `free/default`, and the scoped
   OmniRoute key for the primary path.
4. Keep ordered fallbacks: OpenRouter `openrouter/free` first, then the reviewed
   custom endpoint `http://ollama:11434/v1` with model `qwen3:8b`.
5. Keep command approval enabled.
6. Do not mount the host filesystem or Docker socket.
7. Test a harmless read-only prompt before adding messaging or MCP tools.

Normal startup rewrites the private Hermes config from the committed template,
so manual changes are repair-only and will not become deployment policy.

## Accounts intentionally not automated

- Telegram bot creation and user allowlisting
- Email/Google/GitHub OAuth consent
- Google Cloud/YouTube Data API enablement, key creation, restriction, quota,
  and acceptance of YouTube API terms
- Provider sign-up and acceptance of provider terms
- VPS purchase, DNS, TLS, WireGuard, and backup destination
- job-site accounts, screening/legal/consent answers, CAPTCHA/identity checks,
  and each exact final application approval
- Any secret, recovery code, payment method, or identity verification
- Creator consent/contact-law review, sponsorship terms/disclosures, payment,
  public posting, and KarixMC point issuance

Those actions carry identity, legal, financial, or external-state consequences
and must remain user-owned.
