# OmniRoute integration boundary

Compose profile `agent` runs official Docker Hub image
`diegosouzapw/omniroute:3.8.49`, pinned by multi-platform digest. Dashboard is
bound to `127.0.0.1` only. State uses named volume `omniroute_data`; Redis uses
database 1 while foundation task queues use database 0.

Bootstrap password and cryptographic secrets come from ignored `.env`.
Inference API-key enforcement is enabled. `scripts/configure-free-models.ps1`
logs into the loopback management API, creates one local Hermes key, and keeps
that key only in ignored `.env`.

## Verified zero-cost route

Run after starting the `agent` profile:

```powershell
./scripts/configure-free-models.ps1
```

The script builds `free/default` from:

- OVHcloud AI's official anonymous OpenAI-compatible endpoint (fast path,
  currently 2 requests/minute per IP per model);
- AI Horde's documented anonymous key (slow volunteer-GPU fallback).

It blocks reverse-engineered web/support-chat providers and routes whose live
behavior contradicts their keyless documentation. On 2026-08-12, live probes
found that Pollinations required authentication and LLM7 rejected its
documented placeholder key, so neither is placed in the active route.

OmniRoute's “1.4B+ free tokens” is an aggregate estimate across many separate
provider free-tier accounts, not a bundled OmniRoute balance. The script does
not create accounts, accept provider terms, bypass KYC, or invent credentials.
Account-backed free tiers can be added later with keys the operator obtains.

Upstream source: <https://github.com/diegosouzapw/OmniRoute/releases/tag/v3.8.49>

References:

- Free-tier estimates: <https://github.com/diegosouzapw/OmniRoute/blob/main/docs/reference/FREE_TIERS.md>
- Pinned provider catalog: <https://github.com/diegosouzapw/OmniRoute/blob/release/v3.8.49/docs/reference/PROVIDER_REFERENCE.md>
