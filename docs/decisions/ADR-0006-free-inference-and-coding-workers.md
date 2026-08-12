# ADR-0006 — Free inference and coding-worker strategy

Status: Accepted

## Context

The platform should minimize recurring cost without confusing open-source
software with free compute. The observed development GPU has 8 GB VRAM. Hermes,
Prime Agent, and Nemotron overlap in agentic capability but have different trust
and hardware requirements.

## Decision

- Keep Hermes as the single cognitive orchestrator.
- Keep OmniRoute as the replaceable inference gateway.
- Provide pinned, profile-gated Ollama with `qwen3:8b` as a local fallback.
- Route models too large for local hardware, including current Nemotron 3
  agentic checkpoints, through explicitly selected free providers.
- Evaluate Prime Agent later as a disposable coding worker behind the control
  plane, never as an unrestricted co-orchestrator.
- Treat provider free tiers as volatile capacity, not an availability guarantee.

## Alternatives

- Run Nemotron locally with CPU/GPU offload.
- Give Hermes and Prime Agent direct host access.
- Depend only on hosted free tiers.
- Replace OmniRoute with hard-coded provider clients.

## Reasoning

Large-model CPU offload would be too slow for an always-on agent and still needs
substantial RAM. Multiple privileged orchestrators enlarge the attack surface and
split audit ownership. Hosted-only free tiers are stronger but can disappear.
The hybrid design preserves privacy and continuity while allowing stronger
remote models when quota exists.

## Consequences

Local output quality and context are limited. Remote free routes require manual
account setup and can be throttled. Prime Agent integration waits for a proper
sandbox/worktree adapter. Model/provider choice remains replaceable at the
OmniRoute boundary.
