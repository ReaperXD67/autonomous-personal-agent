# Experiment log

Only observed measurements are recorded. Planned experiments stay explicitly
marked as planned.

## EXP-001 — Foundation runtime validation

Date: 2026-08-11

See Engineering Journal Steps 7–8 for task IDs and full evidence. Compose, image
builds, lint, tests, health, approval flow, outbox recovery, persistence, and a
checksummed backup passed. This entry references rather than duplicates those
measurements.

## EXP-002 — Current repository and hardware audit

Date: 2026-08-12

Objective: verify current progress and local inference feasibility.

Observed:

- Git worktree started clean on `main` at `fe70450`.
- Core plus optional Hermes/OmniRoute containers: 7/7 running healthy.
- Existing containerized suite before changes: 14 tests passed in 0.53 seconds.
- GPU: NVIDIA GeForce RTX 4070 Laptop GPU, 8188 MiB VRAM.
- Nemotron 3 Super BF16 official minimum: 8× H100-80GB.
- Nemotron 3 Nano Omni smallest official precision: 21 GB NVFP4.
- Ollama `qwen3:8b` Q4 artifact: 5.2 GB.

Decision: do not download or CPU-offload Nemotron locally. Prepare Qwen3 8B as a
local fallback and prefer remote free-tier Nemotron when available.

## EXP-003 — Worker lease recovery

Date: 2026-08-12

Method: stop the worker, submit a safe echo task, force its PostgreSQL claim to
an expired lease, and observe dispatcher reconciliation before restarting the
worker. Repeat with `attempt_count = max_attempts`.

Observed:

- Retry task `50e59ca8-6883-40d5-bd45-4dd507071034` succeeded on attempt 2.
- Exhaustion task `b3702df9-d78b-40c5-b6cc-fca66152b3ce` failed with
  `WORKER_LEASE_EXHAUSTED` on attempt 3.
- An earlier diagnostic run confirmed the audit sequence `task.created`,
  `task.recovered`, `task.started`, `task.succeeded`.
- The repeatable `scripts/recovery-smoke.ps1` passed.

Result: passed.

## EXP-004 — Free routed inference

Date: 2026-08-12

Observed:

- OmniRoute authenticated model listing returned 79 routes.
- Bare `auto` returned HTTP 400 because its current combo had no eligible
  candidate with a sufficient known context limit.
- Direct OVH free Qwen3 Coder returned HTTP 429 during the test window.
- `free/default` returned a valid completion after the client explicitly set
  `stream: false`.
- Hermes then returned exactly `HERMES_OK` through its configured custom
  OmniRoute endpoint.

Result: free routed inference and the Hermes-to-router path passed. A free tier
is capacity, not an uptime guarantee.

## EXP-005 — Local inference bootstrap

Date: 2026-08-12

The pinned Ollama/Qwen setup was started. A network sample received about 14 MB
in 30 seconds while pulling the approximately 3 GB Ollama image. At that rate,
the runtime plus 5.2 GB model would require hours, so the bounded attempt was
terminated. Docker layer downloads are resumable; no completed image, model, or
inference result is claimed.

Result: setup automation and Compose validation passed; full local download and
inference remain unverified due transfer speed.

## Planned experiments

- Compare `qwen3:8b` local latency and tool-call reliability against one remote
  free route using the same harmless task set.
- Record route availability, throttling, latency, and human-intervention rate.
- Evaluate Prime Agent only inside a disposable worktree/container with a fixed
  token/time/tool budget.
