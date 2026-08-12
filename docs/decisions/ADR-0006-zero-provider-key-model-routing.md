# ADR-0006: Prefer official anonymous inference for the default free route

- Status: Accepted
- Date: 2026-08-12

## Context

OmniRoute catalogs many free tiers, but its token estimate aggregates quotas from
separate provider accounts. It is not a token grant supplied by OmniRoute. Many
large quotas require operator registration, provider terms, KYC, or API keys.
Some cataloged keyless routes automate consumer web or support-chat interfaces;
others no longer match their documented authentication behavior.

The local agent needs a useful default without a card or third-party credential,
while keeping the public repository reproducible and honest about availability.

## Decision

Create an idempotent `free/default` combo in pinned OmniRoute `3.8.49`:

1. Prioritize OVHcloud AI's official anonymous OpenAI-compatible endpoint.
2. Use AI Horde's documented anonymous access as volunteer-GPU fallback.
3. Block reverse-engineered web/support providers and providers with upstream
   terms warnings.
4. Exclude Pollinations and LLM7 because live probes returned authentication
   failures despite keyless catalog guidance on 2026-08-12.
5. Authenticate Hermes to OmniRoute with a generated local-only scoped key. Keep
   it in ignored state and pass it into Hermes over standard input, never a
   command argument or tracked file.
6. Do not automate external account creation, terms acceptance, KYC, billing, or
   credential acquisition. Account-backed free tiers remain operator opt-in.

The repeatable implementation is `scripts/configure-free-models.ps1`. It
configures provider policy, failover, the local gateway key, Hermes, and a live
completion check.

## Alternatives

- Enable every cataloged keyless provider: more apparent capacity, unacceptable
  terms and reliability risk.
- Automatically enroll in large free tiers: cannot lawfully or safely accept
  provider contracts, identity checks, or billing choices for the operator.
- Use one anonymous endpoint only: simpler, but no outage fallback.
- Run a local model: private and predictable after setup, but requires enough
  user-owned compute and is outside this repository's current hardware scope.

## Consequences

The default route requires no model-provider account, card, or API key. It can
still be throttled, slow, unavailable, or changed by upstream operators. AI
Horde fallback does not promise tool-calling support. Production reliability
will require an operator-owned provider credential, suitable local inference,
or both.

References:

- <https://github.com/diegosouzapw/OmniRoute/blob/main/docs/reference/FREE_TIERS.md>
- <https://github.com/diegosouzapw/OmniRoute/blob/release/v3.8.49/docs/reference/PROVIDER_REFERENCE.md>
