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

## EXP-016 — Promotion-kit API and browser observation

Date: 2026-08-31

Method: rebuild the local control plane, call the authenticated promotion-kit
endpoint for the existing inactive KarixMC campaign, and use a real Playwright
browser to authenticate to the loopback dashboard and open the kit. No external
post, email, creator discovery request, or provider credential was used.

Observed:

- readiness reported Docker and the control dashboard healthy while correctly
  reporting YouTube discovery and real SMTP as unconfigured;
- the endpoint returned five assets and all five URLs contained campaign ID,
  source, medium, campaign, and content attribution parameters;
- the first browser render exposed a repeated article (`a a verified`) caused
  by composing around a summary that already included its article;
- after correcting the templates and adding a regression assertion, the rebuilt
  isolated suite passed Ruff and 62 tests in 1.80 seconds;
- the authenticated dialog rendered all five copy actions and Playwright
  reported zero console errors or warnings; and
- complete lifecycle verification passed builds, six-service health, safe and
  approval paths, lease retry/exhaustion, queued/running cancellation, and
  dead-letter inspection.

Result: deterministic generation, attribution completeness, the authenticated
API, and dashboard interaction passed locally. External discovery and inbox
delivery remain unverified because no YouTube or SMTP credential is configured.

## EXP-017 — Creator-specific no-egress workflow proof

Date: 2026-09-05

Method: run `scripts/promotion.ps1 -LocalTest` against the real control plane and
isolated Mailpit worker. Create an inactive synthetic campaign and authorized
`.test` prospect, build its kit, prepare/approve one deterministic introduction,
record a synthetic opt-out, try another plan, inspect aggregate results, and
delete the exact campaign records. Separately rerun the broader side-effect
smoke after updating its inference-ledger cleanup order.

Observed:

- Creator email task `7bfcd01d-f5de-4c40-8ef9-10bd722d280e` succeeded through
  Mailpit; its unique generated subject appeared in the local inbox.
- The kit contained five distinct tracking URLs. Campaign results recorded one
  delivered email and one suppression, and the API refused another plan with
  HTTP 409 after authorization was withdrawn.
- The running test worker reported `mailpit`, internal host/sender settings,
  and empty SMTP username/password. No YouTube task was queued and no external
  email was sent.
- Cleanup left zero `local-creator-outreach-smoke` campaigns. The first broad
  side-effect rerun revealed one restrictive inference-ledger reference; after
  correcting the order and removing that exact synthetic run, the second broad
  smoke passed and left zero `local-side-effect-smoke` profiles.
- The final rebuilt verification image passed Ruff and 64 tests in 0.63 seconds.
  Complete lifecycle verification also passed. Both configured KarixMC URLs
  returned HTTP 200.

Result: the creator campaign, copy, exact approval, local delivery, metrics,
opt-out enforcement, credential isolation, and cleanup paths passed. The
workstation key is loaded but live YouTube discovery, real SMTP authentication,
and provider-inbox delivery were not tested.

## EXP-018 — Full local release and private-VPS portability proof

Date: 2026-09-07

Method: rebuild and run the creator-specific and broad side-effect smokes; run
the full readiness gate with configured inference; authenticate a real Chromium
session and open the Promotion kit; exercise web hardening; syntax-check every
PowerShell/Bash script; probe VPS secret initialization in an isolated temporary
directory; and execute the Linux backup/restore commands against local Docker.

Observed:

- Creator smoke generated five attributed assets, delivered one exact message
  to Mailpit, enforced opt-out suppression, made no discovery request/external
  send, and cleaned up its campaign.
- Broad side-effect smoke completed one fake ATS submission and one Mailpit
  email, then refused a second application using its durable receipt.
- Rebuilt Ruff/Pytest passed 67 tests. The complete readiness result passed core
  lifecycle, disposable restore, doctor, OmniRoute `free/default`, local Qwen on
  the NVIDIA GPU, and Hermes. OpenRouter was skipped because it is unconfigured.
- Chromium rendered the authenticated campaign and five-channel kit with zero
  console errors/warnings. OpenAPI returned 404 and an untrusted Host returned
  400.
- The Bash backup checksum and disposable restore passed with 8 migrations, 150
  tasks, 487 audit events, and zero orphan audits. The initializer generated a
  production/loopback configuration and refused a second overwrite attempt.
- Docker Desktop startup required recoverable relocation of exact stale
  inference/secrets socket directories; no project or durable Docker data was
  deleted.

Result: the Windows workstation and Linux-oriented repository commands are
locally validated for a private deployment. An actual VPS, external SMTP inbox,
live YouTube scan, encrypted off-host retention, and public-production identity
controls were not tested and are not implied.

## EXP-019 — Managed hierarchy pre-release validation

Date: 2026-09-08

Method: recover the stopped Docker engine without deleting durable data; render
the base and NVIDIA Compose models; probe the managed configuration on a fresh
named volume; run repository, lifecycle, provider, local-model, side-effect, and
creator-specific smokes; then exercise the automatic browser session in Chromium.

Observed:

- Base and all-profile NVIDIA Compose configurations rendered successfully.
- Every PowerShell and Bash script parsed, `git diff --check` passed, and the
  changed Python and dashboard JavaScript passed syntax checks.
- A direct browser-auth unit smoke proved one-use bootstrap consumption, signed
  session validation, and cross-origin rejection without printing any token.
- Docker Desktop 4.78 was initially stopped and its backend rejected malformed
  transient AF_UNIX state. With Docker and WSL stopped, the exact `Docker\\run`
  directory was moved to a recoverable timestamped sibling. Docker recreated it
  and engine 29.5.3 started; images, named volumes, source, and secrets were not
  reset.
- The fresh-volume probe passed with a non-root UID 10000 copier and a readable
  `0600` managed route file. Rebuilt Ruff/Pytest passed 73 tests in 1.05 seconds,
  and the complete lifecycle verification passed all task-state paths.
- Doctor proved the configured order and Qwen-unloaded state. OmniRoute listed
  79 models and served the `free/default` canary; managed Hermes returned exactly
  `HERMES_READY_OK` through that primary. The explicit Qwen canary
  returned `LOCAL_MODEL_OK`, used the RTX 4070 Laptop GPU with all 37 model layers
  offloaded, and unloaded afterward. A false CPU selection observed on the first
  attempt was traced to PowerShell pipeline exit-status handling and corrected.
- Normal safe startup made all 12 required services healthy while `ollama ps`
  remained empty. The broad safe-side-effect proof passed fake application,
  Mailpit delivery, and duplicate refusal; the creator proof passed campaign,
  exact introduction, five attributed assets, and suppression without egress.
- Chromium consumed a one-use code, scrubbed the URL fragment, remained signed
  in after reload, submitted a CSRF-protected task that reached `Succeeded`, and
  reported zero console errors or warnings.

Result: the local implementation is validated for private single-operator use.
The secondary OpenRouter route remains prepared but cannot be called until the
operator supplies its key. Live YouTube discovery, real SMTP delivery, and an
actual VPS remain deliberately unclaimed external proofs.

## Experiment 24 — Durable dependency plans and lost-signal recovery

Date: 2026-09-09

Method: rebuild the containerized runtime/tests, run the full lifecycle gate,
apply all migrations to a fresh disposable PostgreSQL database for workflow
failure/concurrency probes, test queue recovery in a synthetic schema, and
exercise the workflow dashboard in Chromium.

Observed:

- Ruff and 110 tests passed; the final full verification test phase took 0.87 s.
- Twelve workflow scenario groups passed, including six simultaneous
  reconcilers with exactly four task/outbox rows, no partial writes after an
  injected dispatch failure, approval rejection, evidence mismatch, cancellation,
  on-time and late completion, and invalidated capability quarantine.
- Queued signal replay passed while preserving approval, due-time, attempt,
  ownership, and generation boundaries. The disposable database and synthetic
  schema were removed successfully.
- Existing lifecycle smokes passed safe execution, explicit approval, retry,
  exhaustion, queued/running cancellation, and dead-letter inspection.
- Twelve mocked UI paths passed. Live Chromium completed a four-step workflow
  with four exact output checks, retained its signed HttpOnly session on reload,
  navigated task audit, rendered at 390 px without horizontal overflow, and
  reported zero page errors. Synthetic live test records were removed.
- The rebuilt side-effect runtime passed fake-ATS submission, Mailpit delivery,
  and duplicate refusal without application/email egress.

Result: bounded multi-step coordination and queued-signal reconstruction are
verified locally without new executor privileges. These measurements do not
establish model intelligence, general-purpose planning quality, or real external
application/email compatibility.

## Experiment 25 — Live OpenRouter contract and semantic-failover proof

Date: 2026-09-10

Method: reproduce the user-key smoke with raw provider envelopes kept out of
logs; query the official model/ZDR inventories; run corrected PowerShell and
rebuilt Python canaries; exercise OmniRoute independently; run a synthetic full
career draft; then execute repository, inference, and Compose gates.

Observed:

- The original completion failed before inference because seven fallback models
  exceeded the provider's maximum of three. After capping that field, the next
  request failed because none of the benchmark leaders matched the combined ZDR
  policy.
- The live active-ZDR/free/text intersection contained two routes, both without
  published benchmark values. The corrected script and rebuilt Python adapter
  each returned the exact harmless marker through
  `inclusionai/ling-3.0-flash-fin:free` at reported cost zero.
- OmniRoute `free/default` independently returned the exact canary and reported
  `aphrodite/TheDrummer/Cydonia-24B-v4.3` from its 79-route catalog.
- A synthetic full draft fetched 100 listings and matched 39. The first hosted
  output was schema-invalid and the second was empty; both were rejected and
  recorded before local Qwen completed the structured draft.
- Unit coverage proves dynamic benchmark order, ZDR intersection, the four-route
  provider cap, retention of one viable hosted route before local fallback,
  semantic second-model selection, and failed-model attribution for empty
  completions. Final Ruff/Pytest passed 116 tests; Compose rendering, complete
  lifecycle/workflow/queue verification, agent doctor, OmniRoute canary,
  PowerShell parsing, and whitespace checks passed.

Result: the credential and strict-free provider canary are operational, and the
complete draft path remains available when current privacy-compatible hosted
quality is insufficient. This does not establish hosted full-draft quality or
future provider availability.

## Experiment 26 — Local feature proof and reviewed goal planning (2026-09-11)

Method: run the existing workstation/runtime gate before changes, exercise the
implemented domain flows, add isolated PostgreSQL fault/concurrency probes,
execute an accounted model proposal through the normal API/worker/adoption path,
then run the fresh integrated gate and desktop/mobile browser checks.

Initial observations:

- Baseline runtime checks passed: core 58.26 s, disposable restore 9.59 s,
  environment/agent doctor 12.01 s, OmniRoute 23.05 s, strict-free OpenRouter
  6.11 s, local Qwen GPU response 130.28 s, Hermes 28.60 s. Qwen was unloaded
  after the check. These are observed end-to-end wall times, not model benchmarks.
- The baseline career smoke fetched 100 public jobs, matched 20, and produced a
  hosted draft in 14.83 s through `inclusionai/ling-3.0-flash-vl:free` / Novita.
  Local application/email fixtures passed in 35.09 s; creator campaign/local
  outreach/outcome checks passed in 9.75 s.
- The bounded YouTube probe used one query and `maxResults=1`, discovered and
  persisted one candidate, then cleaned the synthetic campaign. It completed in
  1.84 s and collected/sent no email. This proves that request, not broad discovery
  completeness or future quota/provider availability.
- The first live planner proof completed in 8.49 s including checks, proposal,
  explicit adoption, and actual workflow result. Its OpenRouter/Novita invocation
  reported 480 total tokens, zero cost, and 2,075 ms model latency. The durable
  synthetic task, proposal, workflow, and inference rows remain for audit and
  shared quota accounting.
- Isolated scheduler verification passed six scenario groups covering injected
  rollback, concurrent issuance, repeated polls, and conflicting idempotency keys
  for both career and creator schedules. No live queue/provider was used.
- Early integrated gates failed at Ruff before execution verification, first on
  readiness formatting and then on one overlong regression-test line. Those
  attempts were stopped and never published as successful evidence. Formatting
  and prerequisite regressions were corrected before the fresh gate.

Result scope: these observations establish bounded local workflows and specific
configured provider requests. They do not establish AGI, broad task generality,
model quality superiority, real SMTP delivery, universal ATS compatibility, or
future runtime availability.

Final integrated run: all 13 checks passed without skips and were published via
the authenticated API as run `04a0c84e-4182-41d2-a9ca-f23f1300f2c9`.

| Check | Observed seconds |
|---|---:|
| Core, including 162 tests and lifecycle/transaction probes | 62.60 |
| Restore | 9.77 |
| Environment/agent doctor | 11.12 |
| OmniRoute | 0.84 |
| Attested-free OpenRouter | 5.51 |
| Local Qwen GPU canary and lifecycle | 217.90 |
| Hermes | 19.27 |
| Career discovery and draft | 21.77 |
| Local application/email side effects | 41.93 |
| Creator outreach | 8.83 |
| Bounded YouTube discovery | 2.54 |
| Live model proposal and adopted workflow | 7.61 |
| Scheduler transaction probes | 2.16 |

A follow-up restore after the migration-version bookkeeping correction passed
all 12 migrations, 213 tasks, 707 audit records, and zero orphan audits in 8.87 s.
The browser proof passed 15 behavior groups, all 10 views at 390px, and zero page
errors. Illustrative screenshots use labeled synthetic data; actual execution
evidence comes from the live API/worker/SQL proofs, not those fixtures.

## Planned experiments

- Compare `qwen3:8b` local latency and tool-call reliability against one remote
  free route using the same harmless task set.
- Record route availability, throttling, latency, and human-intervention rate.
- Evaluate Prime Agent only inside a disposable worktree/container with a fixed
  token/time/tool budget.
