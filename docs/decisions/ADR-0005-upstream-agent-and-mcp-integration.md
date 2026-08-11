# ADR-0005: Pin upstream agents; keep MCP disabled until policy rendering exists

- Status: Accepted
- Date: 2026-08-11

## Context

Hermes, OmniRoute, and MCP ecosystem evolve quickly. Fabricated APIs or mutable
images would make a portfolio foundation misleading and unsafe. Docker MCP
Toolkit is beta and host-managed.

## Decision

Verify official sources and published images, then pin release tags plus
multi-platform manifest digests. Place Hermes/OmniRoute behind optional profile.
Record curated MCP server digests and profiles, but enable none until runtime
policy adapter, scoped credentials/mounts, and safe tests exist.

## Alternatives

- Clone/build upstream `main`: freshest features, non-reproducible and slow.
- Use `latest`: easy updates, uncontrolled supply-chain/runtime changes.
- Mount Docker socket for MCP discovery: flexible, excessive host privilege.
- Install random MCP packages in Hermes: fast demo, no provenance/isolation.

## Consequences

Core stack runs without external accounts. Agent profile needs manual onboarding.
MCP roadmap is honest but not yet functional. Updates require deliberate digest,
contract, and security review.

