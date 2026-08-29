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

## EXP-006 — Owned lease, cancellation, and dead-letter lifecycle

Date: 2026-08-15

Method: rebuild the runtime, apply migration `004_execution_lifecycle`, execute
the full verification suite, force one expired claim below its budget and one at
its budget, cancel one queued task and one 30-second running task, then query the
authenticated dead-letter endpoint.

Observed:

- Containerized Ruff and Pytest passed: 23 tests in 0.72 seconds.
- Safe task `d779250d-f7cd-4c2c-89db-d27547adaabe` succeeded.
- Approval-gated task `d8909278-6d8b-4668-a3f6-85ffc33e91d9` succeeded.
- Expired task `944a8a52-99ac-4f5d-a99f-034405af1d79` succeeded on attempt 2
  after delayed recovery.
- Exhausted task `7cfb86a6-05d4-4d70-b4ff-2fb30e5bfb4c` became
  `dead_lettered` with `WORKER_LEASE_EXHAUSTED`.
- Queued task `a62c4c39-67b6-4d97-8127-1cfdc7b92c3d` cancelled before claim.
- Running task `911c7191-1ee2-43a0-8e8f-121f268c6cec` cooperatively cancelled
  and retained cancellation metadata.

Result: passed.

## EXP-007 — Checksummed disposable restore drill

Date: 2026-08-15

The backup script created `agent-20260815T151336Z.dump` with SHA-256
`f4ad193a09d4ab2bfd43141a6962aa4e6bd1f861b89b751ffc6b36172160e7e2`.
The drill restored it into random database `agent_restore_125a39ff965e`, found 4
migrations, 32 tasks, 105 audit events, the vector extension, and zero orphaned
audit links. Application database readiness passed, then the disposable database
was removed.

Result: passed. Encryption/off-host scheduling is not implied.

## EXP-008 — Local and routed inference readiness

Date: 2026-08-15

Observed:

- Ollama contained `qwen3:8b` at 5.2 GB.
- Qwen3 returned exactly `LOCAL_MODEL_OK` with thinking disabled.
- `ollama ps` reported GPU placement on the RTX 4070 Laptop GPU.
- OmniRoute listed 79 models and `free/default` returned a valid completion.
- Hermes returned exactly `HERMES_READY_OK` through the configured route.

Result: local, routed, and Hermes inference passed. Free-route capacity remains
volatile and the 8K local context remains intentionally constrained.

## EXP-009 — Supply-chain gate baseline

Date: 2026-08-15

Method: use official Trivy `v0.74.0` against the repository and the built
`autonomous-personal-agent/control-api:local` image at high/critical severity,
with fixed findings enforced; generate an SPDX JSON image SBOM with official
Syft `v1.51.0`; rebuild the isolated test container after adding workflow
contracts.

Observed:

- Repository/`uv.lock`: 0 high/critical vulnerabilities.
- Repository secret scan: no findings reported.
- Dockerfile misconfiguration scan: 0 findings.
- Debian 12.15 runtime packages: 0 high/critical vulnerabilities.
- Installed runtime Python packages: 0 high/critical vulnerabilities.
- SPDX JSON generation completed successfully.
- Ruff and Pytest passed; 24 tests in 0.37 seconds.

GitHub Actions run `31892979230` then passed the branch-required clean-checkout
`validate` job in 55 seconds. It produced non-expired artifact
`control-api-sbom` at 380,063 bytes with expiry 2026-08-29.

Result: passed locally and in GitHub CI.

## EXP-010 — Complete workstation readiness gate

Date: 2026-08-15

Method: run the default `scripts/readiness.ps1` with no skip switches after
making the local-model bootstrap reuse an already-installed model unless an
explicit refresh is requested.

Observed:

- Core lifecycle verification passed in 48.31 seconds.
- Checksummed disposable restore passed in 5.60 seconds.
- Environment and optional-agent doctor passed in 2.34 seconds.
- OmniRoute `free/default` inference passed in 0.33 seconds.
- Local Qwen3 8B inference passed on GPU in 2.23 seconds.
- Hermes routed inference passed in 17.19 seconds.
- The first run exposed a transient pull failure despite a complete cached
  model. The gate correctly failed; after the bootstrap fix, the complete
  no-skip rerun passed.

Result: all six configured workstation paths passed. The ignored machine report
is `runtime/readiness/latest.json`; it contains status/timing metadata only.

## EXP-011 — Live career discovery and local application draft

Date: 2026-08-15

Method: start the rebuilt core plus local-model profile, load the command-center
HTML/CSS/JavaScript over loopback, then run `scripts/career-smoke.ps1 -Draft`.
The smoke selected a current public listing title, created an inactive synthetic
profile/resume, queued a real career scan through the policy/outbox path, required
an attributable persisted match, generated a structured draft on local Qwen, and
removed only the exact synthetic profile.

Observed:

- Dashboard HTML, CSS, and JavaScript returned HTTP 200 at 13,823, 17,047, and
  27,206 bytes respectively; the HTML response included the self-only content
  security policy.
- Search task `39407809-2eac-423f-9f82-aee0901897ad` succeeded after fetching
  100 live listings and matching 5 within the synthetic profile's fresh window.
- Draft task `9ea6e366-de07-44a3-b7ac-a30c4ae4a0bd` succeeded with model
  `qwen3:8b`; a non-empty structured fit summary and cover letter were persisted.
- The synthetic career profile and its cascaded opportunities/draft were removed
  by an exact UUID plus `requested_by = 'local-career-smoke'` predicate.

Result: the live no-key discovery and local résumé-to-draft paths passed. This
does not test or claim external application submission.

## EXP-012 — Exact local application/email side-effect proof

Date: 2026-08-25

Method: run `scripts/side-effect-smoke.ps1` against the rebuilt core,
`qwen3:8b`, isolated Playwright worker, fake six-field ATS, and Mailpit. The
script created an inactive synthetic profile/opportunity, generated a real local
draft, preflighted the form, approved the exact application, approved one exact
email, created a second different application plan, and removed only its own
PostgreSQL records. Separately reload the dashboard through Playwright and scan
the final action image with Trivy 0.74.0.

Observed:

- Application task `04b6e586-cdb4-4904-a757-cad5c1cd5915` succeeded and the
  fake ATS returned its confirmation.
- Email task `7fe760a7-a633-4297-b427-93ecfe5e3a05` succeeded through Mailpit;
  the exact unique subject appeared in the local inbox.
- Second application task `9b98105c-1d6e-4aa2-8247-61f033df8487` failed with
  the existing succeeded-receipt refusal; only one application receipt existed.
- The guarded cleanup left zero side-effect-smoke career profiles and zero
  linked external actions.
- The dashboard reload returned the Hermes Command Center at loopback with zero
  browser console errors or warnings.
- Trivy found zero Ubuntu, Playwright Node, or application Python high/critical
  findings after two exact stale base-SBOM PURLs were suppressed. Runtime import
  and filesystem checks found neither attested distribution; both exceptions
  expire 2026-09-25.
- Final container suite passed 40 tests; the complete lifecycle verification
  also passed.

Result: exact approval binding, isolated execution, local email delivery, and
duplicate refusal passed without any real external side effect. Real ATS and
mail-provider compatibility are not implied.

## EXP-013 — Governed creator-outreach control-plane and dashboard proof

Date: 2026-08-29

Method: rebuild the test/control images, run the complete lifecycle gate, apply
migration 007 to the local PostgreSQL volume, call the authenticated task and
marketing list APIs, create one inactive KarixMC campaign through the API, and
inspect the dashboard in a real Chromium session at desktop, 375x812, and
812x375 viewport sizes.

Observed:

- The rebuilt container suite passed Ruff and 51 tests in 0.71 seconds in the
  final lifecycle build.
- Complete verification passed six service health checks, safe and approved
  tasks, lease retry/exhaustion, queued/running cancellation, dead-letter
  inspection, and lifecycle checks.
- Before initialization, authenticated task, campaign, prospect, and result
  list calls returned successfully with 82 tasks and zero marketing rows.
- The API created one inactive adaptive `KarixMC creator pilot` with three
  discovery queries; no discovery task or email action was created.
- The authenticated dashboard rendered the persisted campaign, zero-result
  metrics, discovery-paused state, and 10-send evidence threshold with zero
  console errors or warnings.
- Chromium reported `scrollWidth == innerWidth` at both 375 and 812 CSS pixels.
  The campaign dialog exposed labeled offer, discovery, range, schedule, and
  adaptation controls.
- The configured KarixMC product and privacy URLs both returned HTTP 200.
- CLI reduced-motion emulation was unavailable in this run; the static
  `prefers-reduced-motion` rule was reviewed but is not claimed as an emulated
  browser result.

Result: the migration, authenticated APIs, inactive real campaign record,
dashboard, and bounded local decision logic passed. Live YouTube API discovery,
real SMTP delivery, inbound replies, and KarixMC conversion attribution were not
tested and are not implied.

## EXP-014 — Free catalog and hybrid draft-route observation

Date: 2026-08-29

Observed:

- OpenRouter `GET /api/v1/models?output_modalities=text` returned 18 text models
  whose exact IDs ended in `:free` and whose prompt/completion prices parsed as
  zero at observation time. This did not prove authenticated completion
  availability or ZDR-compatible endpoints.
- The post-migration disposable career smoke fetched 100 current Arbeitnow
  listings, retained 38 against its synthetic zero-threshold target, and
  completed the draft through `ollama/qwen3:8b` because OpenRouter remained
  disabled. The recorded local latency was 47,697 ms and cost was zero.
- After the cold-start cache fix, rebuilt isolated test runs passed 58 tests in
  0.61 and 0.66 seconds. Playwright rendered the authenticated inference status
  with zero console errors/warnings.

Result: live catalog discovery, strict local routing, durable route telemetry,
and UI rendering passed. Authenticated OpenRouter generation did not run.

## EXP-015 — Purpose-aware free-pool and continuity observation

Date: 2026-08-29

Method: inspect the authenticated OmniRoute model catalog and sanitized Hermes
route/fallback fields, run the extended agent doctor, then execute harmless
OmniRoute, Hermes, and local Qwen exact-response probes. No provider credential,
prompt content beyond the canaries, or persisted personal data was printed.

Observed:

- OmniRoute exposed 79 route IDs. Forty were concrete routes and all reported
  `ovhfree` ownership; no OpenRouter route was present.
- Ignored local configuration reported OpenRouter disabled and no key present.
- The extended doctor accepted Hermes primary `free/default`, found exactly one
  internal custom `qwen3:8b` fallback, and reported quota isolation.
- OmniRoute completed the `free/default` canary and Hermes returned exactly
  `HERMES_READY_OK` through its primary route.
- Local `qwen3:8b` returned exactly `LOCAL_MODEL_OK`; Ollama reported a 6.2 GB
  loaded model, 8,192-token context, and 100% GPU placement.
- The rebuilt container suite passed Ruff and 60 tests. Complete lifecycle
  verification passed after rebuilding the changed worker.

Result: current hosted pools are non-overlapping, both primary routes and the
local endpoint work, and the fallback is rendered. A forced provider outage was
not performed, so automatic failover execution itself is not claimed.

## Planned experiments

- Compare `qwen3:8b` local latency and tool-call reliability against one remote
  free route using the same harmless task set.
- Record route availability, throttling, latency, and human-intervention rate.
- Evaluate Prime Agent only inside a disposable worktree/container with a fixed
  token/time/tool budget.
