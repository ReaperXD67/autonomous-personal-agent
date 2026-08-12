# Free agent stack assessment — 2026-08-12

## Conclusion

Use Hermes as the personal cognitive runtime, OmniRoute as the OpenAI-compatible
router, PostgreSQL/Redis as platform-owned state, and the control plane as the
non-bypassable policy boundary. Add Ollama only as an offline/local fallback.
Do not run multiple unrestricted orchestrators against the same host.

"Free" has three separate meanings:

1. The software license permits self-hosting.
2. Model inference has no per-token charge.
3. Compute, electricity, storage, network, and a future VPS have no cost.

This repository can make (1) true and can achieve (2) with local inference or
provider free tiers. It cannot guarantee (3). Provider quotas and terms can
change, and a 24/7 VPS is not normally free.

## Verified selections

| Component | Decision | Cost reality | Evidence |
|---|---|---|---|
| Hermes Agent | Primary orchestrator | MIT software; model/tool providers may cost money | Official repository documents memory, skills, scheduling, subagents, and MIT licensing: <https://github.com/NousResearch/hermes-agent> |
| OmniRoute | Primary router | MIT software; aggregates both free and paid providers | Official README documents an OpenAI-compatible endpoint, free providers, and routing: <https://github.com/diegosouzapw/OmniRoute> |
| Ollama | Optional local inference | No token bill; uses local GPU, disk, and electricity | Official Docker image and API: <https://github.com/ollama/ollama>; GPU/parallel-memory guidance: <https://docs.ollama.com/faq> |
| Qwen3 8B Q4 | Local fallback | 5.2 GB model download; fits the observed 8 GB GPU only with constrained context/concurrency | Official Ollama artifact: <https://ollama.com/library/qwen3:8b> |
| Prime Agent | Future isolated coding worker | MIT harness, but still requires a model provider or local endpoint | Official repository: <https://github.com/PrimeIntellect-ai/prime-agent> |
| NVIDIA Nemotron 3 | Remote routed model on this laptop | Open weights do not make the required GPU free | Official Super card lists 8× H100-80GB for BF16: <https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16>; Nano Omni still lists 21 GB for NVFP4: <https://huggingface.co/nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16> |

## Hardware finding

Observed locally on 2026-08-12:

```text
NVIDIA GeForce RTX 4070 Laptop GPU
8188 MiB VRAM
```

Therefore Nemotron 3 Nano Omni, Super, and Ultra are not responsible local
defaults. Use a free hosted route through OmniRoute when available. The local
profile instead uses `qwen3:8b` Q4 with one loaded model, one parallel request,
and an 8K context. This is useful for private, offline, short tasks. It is not a
frontier coding model and the short context is a real limitation.

## Why Prime Agent is not enabled directly

Prime Agent has valuable persistent goals, schedules, subagents, autonomous
budgets, and a reviewable refinement history. Its official warning also states
that model-generated Python and project commands run with the user's permissions
and that its worker/kernel processes are not a security sandbox. It should
eventually run as a disposable coding worker with a dedicated worktree, resource
limits, no host credentials, and draft-PR-only output. It should not replace the
platform policy engine or receive the Docker socket.

## Sources and freshness

Research used primary project repositories, official model cards, Docker
documentation, and official Ollama documentation on 2026-08-12. Free-provider
availability is intentionally not hard-coded here because it is unstable. Use
OmniRoute's live free-tier catalog and verify provider terms before connecting an
account.
