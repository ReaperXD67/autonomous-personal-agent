# OmniRoute integration boundary

Compose profile `agent` runs official Docker Hub image
`diegosouzapw/omniroute:3.8.49`, pinned by multi-platform digest. Dashboard is
bound to `127.0.0.1` only. State uses named volume `omniroute_data`; Redis uses
database 1 while foundation task queues use database 0.

Bootstrap password and cryptographic secrets come from ignored `.env`.
Inference API-key enforcement is enabled. First boot requires dashboard
onboarding at `http://127.0.0.1:20128`; credentials are never committed.

Upstream source: <https://github.com/diegosouzapw/OmniRoute/releases/tag/v3.8.49>

Hermes uses the explicit `free/default` route through this gateway. Career
résumé drafting has a separate narrow OpenRouter adapter because it enforces
live exact `:free`/zero-price and
zero-returned-cost invariants that OmniRoute's fail-open automatic free-tier
filter cannot guarantee. Keep the career OpenRouter account out of OmniRoute by
default: OpenRouter's free allowance is account-wide, while only direct career
calls participate in the PostgreSQL reservation ledger.
`./scripts/doctor.ps1 -Agent` warns if the same pool becomes reachable through
both paths.

OmniRoute does not grant a standalone 1.53-billion-token balance. That figure is
an upstream theoretical aggregate of separately enrolled provider free tiers;
actual usable quota depends on the connected provider accounts. On 2026-08-29
this workstation exposed 40 concrete routes, all owned by OVHfree, and no
OpenRouter route.
