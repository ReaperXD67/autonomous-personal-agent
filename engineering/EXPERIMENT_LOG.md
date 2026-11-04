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
Six further authenticated live browser checks passed with zero page errors:
session bootstrap, proposal isolation, explicit adoption and output success,
audit display, published readiness evidence, and reload persistence. The live
result screenshot captures retained workflow `0375348f-b571-4634-b890-48dcf1d46869`.

## Experiment 27 — Creator delivery guards and SMTP setup (2026-09-12)

Measured on the local Docker Desktop runtime. No external email was sent.

| Check | Observed seconds | Result |
|---|---:|---|
| Baseline creator Mailpit flow | 12.39 | Passed before implementation |
| Containerized Ruff and 195 unit/contract tests | 7.73 | Passed after two line-length fixes |
| Full verification and isolated database guards | 68.44 | Passed |
| Local application/email and duplicate prevention | 31.90 | Passed |
| Personalized creator introduction/outcomes | 12.24 | Passed; manual copy excluded from A/B |
| SMTP setup literal/prompt/reporting smoke | 1.82 | Passed; real environment unchanged |

Focused browser checks passed nine groups; the prior dashboard regression passed
15 groups across ten views. Four authenticated live checks verified bootstrap,
the no-send worker task, timestamped evidence/audit, and reload. All browser runs
reported zero page errors. Task `e565b0ab-54d1-43ba-a7a2-72721e63d820` used Mailpit
without authentication and completed at 16:50:38 UTC. The screenshot is a live
connection-check result; other email-state screenshots are labeled synthetic.

The isolated PostgreSQL proof exercised cancellation, wrong/expired leases,
expiry while waiting for locks, tampered public/private contexts, receipt
rollback, and preserved acceptance. These results establish bounded adapter
behavior. External provider credentials remain absent, and neither external
SMTP acceptance nor recipient delivery has been tested in this experiment.

Post-patch repeat on 2026-09-13: the CI advisory update flagged two existing
Debian PCRE2 findings, so the base received the exact security package update.
Ruff/195 tests passed in 9.41 seconds; full verification passed in 71.94 seconds;
personalized creator proof passed in 14.06 seconds. The live control API reports
`libpcre2-8-0=10.42-1+deb12u1`. Refreshed Trivy 0.74.0 metadata reported zero
high/critical findings with available fixes in that rebuilt image. This does
not establish the separate Ubuntu Playwright package's remediation status.

## Experiment 28 — Restart-safe outbound email pacing (2026-09-16)

Method: add a durable schedule to the exact-action approval transaction; test
the pure rolling-window algorithm and configuration bounds; race two approvals
inside an isolated PostgreSQL schema; run the complete lifecycle/recovery gate;
then execute the real creator workflow against Mailpit.

Observed:

- Final standalone containerized Ruff and 200 unit/contract tests passed in
  1.48 seconds; the repeated integrated gate passed them in 1.75 seconds.
- Compose rendering and the full verification script passed, including workflow,
  scheduler, planner, lease, cancellation, dead-letter, queue-recovery, and
  exact-action database probes.
- Two same-domain approvals issued concurrently produced distinct durable slots
  at least 300 seconds apart under the isolated test policy. The due reservation
  completed as accepted and cancellation marked the future reservation skipped.
  No SMTP connection was opened by that proof.
- Unit scenarios separately verified the production global/domain gaps, rolling
  hour/day behavior, deterministic jitter, sender-domain message ID, RFC 5322
  date, and exact SMTP envelope recipient.
- The rebuilt local creator test delivered one exact introduction to Mailpit,
  verified five promotion assets and durable suppression, removed its synthetic
  data, and confirmed no external discovery request or email.

Result: burst prevention is durable across queue/process/VPS recovery and is
enforced again at the send boundary. The experiment does not establish external
SMTP acceptance, domain authentication, inbox placement, complaint handling, or
future reputation; those remain real-provider canary work.

## Experiment 29 — Bounded creator handoff and reviewed learning (2026-10-16)

Method: execute the Docker lint/test and complete verification gates; exercise
creator automation and migration replay in a disposable PostgreSQL database;
send synthetic creator introduction/handoff messages to Mailpit; render the
actual dashboard sources in networkless Chromium with synthetic fixtures.

Observed: 582 unit/contract tests and the full integration verifier passed,
including nineteen creator-automation groups. Checks covered duplicate concurrent
reservations, pause/expiry/campaign changes, stale worker leases, reply review,
foreign-campaign routing, durable opt-outs, legacy backfill and exact-action
learning. Three distinct reviewed objections produced a terms-first hypothesis;
unreviewed snippet suggestions did not affect learning. Subsequent preparation
preserved the commercial proposal and pending exact approval.

The Mailpit test accepted both the introduction and owner email/Discord handoff,
then refused repeat handoff and suppressed future outreach. Desktop/mobile
browser checks passed without page errors or horizontal overflow. All evidence
was synthetic; no live outreach, mailbox, attribution or revenue experiment ran.
This verifies state transitions and bounded adaptation, not reply-rate lift,
commercial acceptance, statistical significance or provider readiness.

After targeted Debian PCRE2/Perl and Ubuntu OpenSSL package updates, the same
full verifier, desktop/mobile browser checks and Mailpit proof passed again.
Trivy 0.74.0 with its 2026-10-16 database reported zero fixable HIGH/CRITICAL
findings in both final runtime images, with no ignore rules. This is a dated
dependency scan, not a claim that all vulnerabilities are absent.

## Experiment 30 — Reviewed creator AI draft lifecycle and interface (2026-10-20)

Method: run the complete container verification gate and a disposable PostgreSQL
draft proof with synthetic model output; run the actual dashboard sources in the
existing unprivileged
action-worker image, with networking disabled, read-only web sources, a temporary
filesystem and synthetic intercepted API responses. Exercise desktop 1440×1080
and mobile 375×812 viewports.

Observed: lint, 621 unit/contract tests and the complete integration verifier
passed. Nine draft database groups covered idempotent policy dispatch, concurrent
exact preparation, immutable digest checks, refused delegated AI approval, stale
research/campaign context, forged task links and cancellation/lease/expiry changes
during lock waits. Changed research also prevented an approved packet from
crossing the final SMTP boundary. Native loopback OAuth and SMTP setup smoke
checks passed without contacting providers or changing real credentials.

Observed: queued, ready, stale, failed and expired drafts render correctly;
closing and reopening pending work creates no duplicate request. Untrusted
source markup displays as text. Preparation submits the displayed exact digest,
keeps the dialog open on a context conflict, and opens the resulting action for
separate review on success. Template/manual paths remain distinct; owner contact
preservation and explicit run-consent reset also passed. No page errors or
horizontal overflow occurred. Desktop/mobile screenshots were inspected and
remain in ignored local output.

The initial HTTP fixture origin did not expose `crypto.randomUUID`; changing
only the intercepted fixture to HTTPS matched the secure-context behavior of
the real loopback dashboard. The complete check then passed. This is UI behavior
with synthetic responses, not model-quality, provider-delivery or reply-rate
evidence.

The subsequent API-shortlist interface check passed with synthetic task output:
bounded input/default, disabled duplicate queueing, persisted task status,
ranked source evidence, partial-failure counts, safe markup rendering and a
current creator lookup before the separate AI draft review. The mobile capture
was repeated after transient toast/focus overlays cleared; no product layout
change was needed. No real YouTube request or model call was part of this UI test.

## Experiment 31 — Bounded API creator shortlist (2026-10-22)

Method: exercise the existing task/policy/audit route with seven disposable
PostgreSQL scenario groups and a real two-creator research batch. Use only the
official YouTube adapter for channel, sampled video and bounded recent-upload
metadata; do not request a draft, contact grant or external message.

Observed: all seven database groups passed, including concurrent idempotency,
generic-task reservation refusal, frozen targeting and identity, contact-authority
preservation, lease expiry during blocking row locks, one active campaign batch
and the global thirty-creator rolling reservation cap. Cancelled reservations
continued counting. No provider or model request was part of the database proof.

The live task refreshed two creators with zero failures, retaining dated
Minecraft publication evidence and declared Polish language. Both remained in
**Needs review** because their contacts were not authorized. The task recorded
zero model requests, contact authorizations and messages sent. This proves the
bounded research route and its review boundary; it does not measure exhaustive
discovery, subscriber authenticity, audience location, reply rate or sales.

## Experiment 32 — Gmail read-only empty-label canary (2026-10-22)

Method: complete the local Desktop OAuth helper's exact mailbox and label
checks, load the ignored settings into the existing worker, and queue the
campaign's governed `marketing.gmail_sync` task through the control API.

Observed: the initial runtime attempt refreshed its token and verified the
profile and label, then encountered an empty HTTP 204 message-list response.
The client now accepts that empty page only for the exact fixed-host message
collection GET; other empty identity/token/label/message responses remain
errors. A repeated audited sync succeeded with zero fetched, inserted and
pending records, no more pages and `mailbox_modified=false`.

This establishes configured runtime OAuth and empty-label reading. No message
was sent or reply ingested; actual labeled-reply matching, replay protection,
interest review, external SMTP authentication, delivery and inbox receipt still
need their own canaries. The Testing-mode OAuth expiry limit still applies.

## Experiment 33 — Final creator-copy quality and integration checks (2026-10-22)

Method: run governed creator-specific draft requests through the configured
hosted/local route, inspect the returned copy against its evidence, then run
the coherent container lint/unit/full integration gates and harmless agent
health checks after the final repairs.

Observed: hosted rate limiting led to real local Qwen responses. Operator
review rejected unsupported claims and an answer repeating a content-bearing
prompt example. The example was removed and a regression guard added. The
final creator request failed closed on the evidence contract. No usable live
AI pitch or creator send is claimed; the per-creator rolling cap was retained.

All 669 unit/contract tests, lint and the complete verifier passed, including
seven shortlist, nine draft, nineteen creator-automation and twelve career
PostgreSQL groups alongside foundation/workflow/scheduler/planner/action/recovery
checks. Compose validation, whitespace checks, `doctor.ps1 -Agent` and the
general agent route smoke passed. That smoke returned `ROUTE_OK` through
`free/default` using Mistral; it is separate from creator-copy quality.

Result: the research, review and failure boundaries are verified. AI-copy
quality remains experimental; external SMTP and an owned-inbox delivery/reply
canary remain unverified. No reply-rate, collaboration or earnings result was
measured.

## Experiment 34 — Natural creator hooks and bounded local reasoning (2026-10-22)

Method: reproduce the literal-keyword false rejection, remove only the positive
`title` requirement, align the prompt and repair hint, then run the narrow
creator suite and complete container unit/contract suite. After confirming
installed-model capability metadata, request internal reasoning only for local
creator drafting with 2,048 output tokens and unchanged request/attempt limits.

Observed: a natural reference to the recorded Minecraft building-plot subject
passed without containing the literal English keyword. The complete message
retained its exact recorded video title and public URL. All 56 narrow
creator tests and all 676 unit/contract tests passed with lint, including the
existing negative-copy rejections, demonstrated unsupported-content/recipient
patterns, request bounds and final-content-only handling. These results verify the copy
contract, not semantic correctness of arbitrary model output or delivery.

A subsequent governed creator request completed using local `qwen3:8b`.
Review found unsupported video-content and audience inferences and an awkward
third-person filming suggestion. A saved model response is verified, but
usable creator-specific copy remains unverified. No exact email packet was
prepared or message sent by the canary.

One subsequent governed Vixen request with `think:true` passed schema and
current-copy checks through local `qwen3:8b` on its first local attempt.
The inference ledger reported 47,875 ms, 1,433 prompt tokens, 144 completion
tokens and 1,577 total tokens at zero credits. The complete governed task took
about 53.4 seconds including hosted routing. Internal reasoning was not
retained; the visible operator rationale is a separate final-output field.
This single final-JSON probe does not establish a general quality/speed gain,
independently measured internal reasoning, delivery or recipient interest.

Operator review confirmed accurate title-subject translation and a relevant
second-person feature-testing idea. The copy was not approved for sending:
the opening was awkward and its rationale inferred feedback alignment despite
zero reviewed/tagged samples. Usable unedited copy remains unverified; no exact
email action or send was created. No output-quality guarantee follows from
passing the schema or this single reviewed example.

The final coherent verifier passed with all 676 tests/lint, native OAuth and
SMTP setup regressions, nine draft, seven shortlist, nineteen creator-automation and twelve
career PostgreSQL groups, plus existing workflow/scheduler/planner/action/recovery
checks. Compose validation, whitespace checks, `doctor.ps1 -Agent` and the
general `agent-smoke.ps1` route canary passed. Its `ROUTE_OK` result through
`free/default` using Mistral is general route evidence, not creator-copy proof.
A previously rejected saved draft read stale with no linked action. No creator
email was approved, prepared or sent; SMTP credentials remained unsaved.

## Experiment 35 — External SMTP launch proof (2026-10-23)

Method: load owner-saved SMTP configuration into the existing action services,
queue the governed no-send connection check, then prepare and individually
approve one exact message to an inbox owned by the operator.

Observed: the audited external SMTP check succeeded with STARTTLS and
authenticated status true, exercising NOOP without sending mail. The exact test
message was approved, received its normal paced/jittered slot and completed
with durable external SMTP acceptance. The actual received Gmail Inbox copy
carried the configured creator label and matched the receipt Message-ID, body
and test reference. Its received headers reported a three-second delivery
interval. No secret, raw header or recipient data is included in this record.

This was one same-mailbox self-test. It verifies owned-inbox delivery, not
delivery to other providers or creators. The adapter intentionally ignores its
own sender and Sent messages, so it does not establish real incoming creator
reply matching/replay, interest classification or handoff. Pacing, exact review
and normal receipt handling were retained.

Fresh HTTPS requests and a browser check could not reach the configured product
site from this workstation while DNS resolved. Two reviewed Polish exact packets
were individually approved through task decisions, then both paced tasks were
cancelled before their due times when the owner confirmed the site was
unreachable. Read-back confirmed terminal cancellation, with zero creator
sends. Broader campaign automation stays paused with no general send grant.
The workstation timeout does not establish a global outage; the owned-inbox
SMTP result is separate from creator delivery.

A subsequent governed read-only Gmail sync fetched the labeled self-test and
returned zero inserted/pending replies, no further pages, no suppression and
`mailbox_modified=false`. This verifies the live reader's self-mail exclusion;
it does not establish actual creator-reply matching, replay or interest review.

Final container lint and all 676 unit/contract tests passed, as did the complete
native OAuth/SMTP, PostgreSQL and recovery verifier, Compose configuration and
whitespace checks. The running control/action services retained real SMTP,
authentication and pacing afterward; the latest audited connection check was
successful. No inference code or model-quality claim changed. Real incoming
creator-reply matching/replay, handoff and Testing-mode OAuth longevity remain
separate limits.

## Experiment 36 — Creator launch and deterministic editorial/reply checks (2026-10-27)

Method: recheck the product pages, refresh two existing creator dossiers through
the official API, review current contact provenance and approve two fresh manual
Polish exact-message packets with the ordinary pacing and final receipt guards.

Observed: home/privacy returned HTTP 200. Both contacts matched their authorized
current sources and had no suppression. Both creator actions completed with
durable real SMTP acceptance; zero sends remain queued. No broader campaign
grant was started, and the campaign remains paused. These are delivery-path
observations, not creator inbox/response or unedited AI-copy quality evidence.

A separate five-creator shortlist returned partial completion: four researched,
one failed, zero selected and four requiring contact review. Saved evidence for
the failed request was not promoted. The task reported zero model requests,
messages sent and contact authorizations. No extra creator send is claimed.

Synthetic no-egress evaluation covered title numbers, viewing/content claims,
generic openings, language mismatch, zero-reviewed-feedback rationale, citation,
next step and length observations, missing optional copy, private-data exclusion
and unchanged digests/read-only behavior. Lint and all 88 combined draft/quality
tests passed. A running-API read of an existing stale draft also exposed the
language-mismatch observation with human review required and no sending authority;
it made no model call, write or preparation. The separate English/Polish reply/learning suite passed 154 cases
covering normalization, quotes, negation, conditional interest, objections and
reviewed-only learning. These are contract checks, not measured response rates.
The pre-image-hardening coherent gate passed lint/all 910 tests and the complete verifier:
native OAuth/SMTP setup, lifecycle/workflow/scheduler/research, 19 creator-
automation, nine draft, seven shortlist and 13 career PostgreSQL groups, both
networkless UI proofs, planner, delivery guards and queue recovery. Compose
configuration and whitespace checks passed. No inference behavior changed.

The clean pull-request CI subsequently stopped at the runtime-image scan on
CVE-2026-84782 in Debian `libssl3`/`openssl` at `3.0.20-1~deb12u2`. The fixed
signed-repository candidate was `3.0.22-1~deb12u2`. An isolated exact-base install
upgraded only those two existing packages, added/removed none, passed
`apt-get check`, and Python `ssl` reported OpenSSL 3.0.22. Adding those exact
pins to the existing shared PCRE2/Perl patch produced four existing-package
upgrades with no additions/removals. No base digest, dependency or vulnerability
ignore changed. Post-patch lint/all 910 tests and the complete verifier passed
again across the native, PostgreSQL, UI, lifecycle, delivery and recovery groups.
The rebuilt research worker reported OpenSSL 3.0.22 with hostname checking
enabled. An automatic governed Gmail task created after that runtime rebuild
succeeded with one fetched, zero inserted/pending and no mailbox modification.
The first local action-image Trivy attempt reached its five-minute timeout
without a valid report. A later Trivy 0.74.0 control-image scan with exact CI
flags passed with zero fixable high/critical findings; clean CI passed that scan.

The valid action-image scan then found fixable HIGH CVE-2026-112940 in system
filelock 3.32.5. Installed metadata traced filelock and orphan python-discovery
1.6.0 to removed virtualenv, with neither in project locks/imports or the isolated
application environment. The isolated action rebuild removed both before pip
self-removal, reported no broken system requirements and preserved all 11 locked
application dependencies. No upgrade, dependency, ignore or base digest changed.
The rebuilt image passed 44 existing repository/delivery tests, networkless SMTP
diagnostic/override/stale-lease guards with zero delivery calls and desktop/mobile
creator UI proof. System/application interpreter checks found all four removed
provisioning modules absent and no filelock consumers, with Playwright 1.63.0 and
the 11 application dependencies intact. Final lint/all 910 tests and the complete
verifier passed after the cleanup across all native, PostgreSQL, lifecycle, UI,
delivery and recovery groups. Trivy 0.74.0 scanned the isolated action review
image with exact CI flags and returned zero fixable high/critical findings.
Identity comparison showed matching RootFS layers/runtime configuration with
the Compose action image except for added Compose labels, not matching OCI
identities. The final Compose action runtime passed a governed real SMTP
STARTTLS/authentication/NOOP check with no email. Required CI image scans remain
release gates.

The networkless creator-review UI proof passed at desktop/mobile sizes using
the existing isolated action image. It checked malicious finding text escaping,
an absent-report fallback, unchanged copy and exact-digest preparation/conflicts,
and no overflow or console errors. Screenshots remain in ignored local output.

A governed Gmail sync failed HTTP 400, and the local helper confirmed the old
refresh grant's `invalid_grant`. Native OAuth smoke passed the explicit renewal
exception and refusal cases without provider access. Same-client read-only
renewal subsequently completed, verified the expected mailbox/label and saved
credentials atomically. The fresh governed sync succeeded with one fetched,
zero inserted/pending, no more pages, no suppression and `mailbox_modified=false`.
This is reader recovery/self-mail exclusion evidence; Google publishing status
and Testing-mode longevity were unchanged. Actual incoming-reply
matching/replay and handoff remain unverified. No new model call was used to
evaluate these changes.

## Experiment 37 — Expanded reviewed creator queue (2026-10-27)

Method: use the existing campaign, official API research, public business-contact
review and individual exact-message approval for additional manual Polish
introductions. Commercial terms, Poland targeting and all sending controls stay
unchanged; no runtime or implementation change is part of this experiment.

Observed at 2026-10-27 15:50:12 UTC (21:20:12 IST): ten additional unique contacts
and manual messages passed review and individual exact approval in batches of
four and six. Including the original two-message pilot, twelve invitations had
three durable SMTP acceptances and nine queued actions, with zero failed or
awaiting approval in that scope. Only one of the expanded ten was accepted at
this checkpoint; queued actions are not sent emails. There was no general send
grant, automatic contact qualification or automatic handoff.

Ordinary spacing, rolling caps, jitter and 24-hour expiry were retained. The
remaining reservations ran from October 27 16:16:47 UTC (21:46:47 IST) through
18:56:10 UTC (October 28 00:26:10 IST). These are reserved release times, not
guaranteed executions or inbox arrival.

The bounded ten-creator refresh completed with nine researched and one failed;
seven required contact review and three were excluded, including the failure.
The separate three-query discovery scan, configured for up to 225 raw results,
completed 53 creator dossiers: 20 new and 33 updated, with 17 public contact
candidates and zero automatic contact authorizations. Coverage moved from 342
prospects/71 with public business contacts to 362/75; neither candidate count
establishes sending authority.

Fresh home/privacy checks returned HTTP 200. The monitored Gmail read completed
at 15:49:59 UTC with zero pending reply-review records at the checkpoint. SMTP
acceptance, later bounces, original-message review and confirmed interest remain
separate measures. The operational-handoff run passed container lint and all 910
tests, followed by the complete native, lifecycle, PostgreSQL, UI, delivery and
queue-recovery verifier. No new model-quality or response-rate benchmark is
claimed.

## Experiment 38 — Bilingual drafting and research progress (2026-11-01)

Method: extend the existing constrained draft context with an English/Polish
generation contract and use hash-linked, current-target/profile reservation
history for successive shortlist selection. Preserve exact review, commercial
wording, the standard English contact/privacy/opt-out footer, research limits
and sending guards. Evaluate these small original adaptations in the existing
containers; the upstream comparison does not establish improved reply rates.

The operational baseline after restoring Docker confirmed twelve of twelve
previous invitations with durable SMTP acceptance, zero queued and zero failed
in that scope. A governed labeled read completed on November 1 at 17:07 UTC
(22:37 IST) with zero pending reply reviews. This confirms recorded sending and
current label reading; it does not measure inbox placement or confirmed interest.

Docker startup was recovered by preserving stale runtime IPC parent folders
and creating fresh endpoints, without resetting Docker volumes or WSL user data.
The restored engine reported 29.5.3. Container lint and all 940 tests passed,
followed by the complete native, lifecycle, PostgreSQL, UI, planner, delivery and
recovery verifier. Its ten draft PostgreSQL groups include Polish rendering;
eleven shortlist groups include current issued history and a 501-candidate
fixture. The official skill manifest validator passed in a read-only no-network
container. These synthetic proofs establish their tested contracts, not real
creator-copy quality or improved response rates.

Fresh product home/privacy checks returned HTTP 200. A further governed Gmail
sync fetched one message, inserted zero, left zero pending, had no further pages
and made no mailbox modification. This continues owned self-mail exclusion
evidence, without establishing an actual creator reply. Agent doctor checks and
the agent smoke passed; a real 32-token `ROUTE_OK` canary used `free/default` and
reported `Mistral-Small-3.2-24B-Instruct-2506`. That route canary did not exercise
local Qwen; a later actual Polish draft completed through Ollama `qwen3:8b`.
Operator review withheld preparation and sending approval after finding an
unsupported product security claim despite an empty finding list. Real Polish
generation is therefore verified, while usable unedited copy and any response-rate benefit
remain unverified. No creator-feedback outcome was invented from this review.

The owner-requested local daily SMTP bound was set to twenty-four through the
shared atomic configuration writer. The repository default remains twelve;
local three/hour, global/domain gaps and jitter were retained. After a controlled
reload, runtime status confirmed twenty-four/day, three/hour, 900-second global
and 1,800-second same-domain spacing with 180-second jitter. This is capacity
selection, with no measured claim that twenty-four messages were sent or that a
larger batch increases response rate.

Fresh governed discovery completed 66 dossiers, adding 25 and updating 41, with
fourteen public business-contact candidates and zero automatic authorizations.
A bounded ten-creator shortlist task was issued; issuance is not a completed
refresh or send. Source inspection and a healthy container alone do not
establish model quality or interested creators.

Further Polish discovery completed forty dossiers, adding twelve and updating
twenty-eight, with ten public contact candidates. The initial unrestricted-country
English campaign discovery added 123 prospects and found twenty-two public contact
candidates. Its next scan researched 147, adding 102 and updating 45, with
twenty-nine public contact candidates. The workspace held 650 prospect records
across campaigns. Twenty-four launch recipients were selected from
twenty-five qualified candidates; the original canary was excluded. The English
selection retained declared English or unknown language and a 250,000-subscriber
maximum, with existing Polish country targeting still strict. Twenty-four
contacts then received individual API authorization and twenty-four draft tasks
were requested, sixteen English and eight Polish. Two temporary replicas of the
existing research worker used distinct hostname leases and the same durable
budgets. All twenty-four model tasks finished: nineteen returned copy and five
failed with `CREATOR_DRAFT_MODEL_UNAVAILABLE`; all nineteen successful results
reported local Ollama `qwen3:8b`. Exact source/product review retained
one AI draft and used twenty-three explicit manual replacements; unsupported
feature, verification and video-content claims were rejected. These operator
decisions are not creator feedback or evidence of model self-learning. Each of
the twenty-four distinct invitations then received individual exact approval,
and the ordinary single research worker was restored.

The published instruction-only skill was installed through the official helper
from commit `8dd39bf768ce47aa68c5ec9927002ab9e619a3dd`, and both installed files'
SHA-256 hashes matched their source. Its availability does not grant runtime
execution or sending authority.

The subsequent narrow copy/quality suite passed 133 tests, including fifteen
added regressions for the actor-specific English/Polish platform-security
refusal, bounded correction and historical-copy/editorial-digest behavior. The
actual old bad draft was subsequently stale with the marker, its body/digest
unchanged, and its live preparation request returned HTTP 409 with no outgoing
packet. This is refusal evidence, not a creator-feedback observation.

Initial pull-request CI passed functional and control-image checks but failed
the isolated action-image security gate for `libbrotli1` CVE-2026-111497. The
exact Ubuntu `1.1.0-2ubuntu0.1` update upgraded one package in isolation, with
zero additions/removals, a successful dependency check and decoder-library load.
The combined OpenSSL/Brotli installation upgraded three expected packages and
added/removed none. The rebuilt runtime passed lint/all 955 tests and the full
native, PostgreSQL, UI, planner, delivery and recovery verifier. Agent doctor
and a repeated real Mistral `ROUTE_OK` smoke passed. Clean pull-request CI at
`fc13af6` subsequently passed the functional, repository and both rebuilt-image
scan/SBOM gates, without new vulnerability ignores.

Both campaigns completed governed Gmail reads at 17:58 UTC (23:28 IST), with
zero pending reply reviews. At 18:00:55.394895 UTC (23:30:55 IST) on November 1,
the first new invitation's action and task succeeded on attempt one, with an
SMTP Message-ID and no last error. The measured launch checkpoint is one new
SMTP acceptance and twenty-three paced actions queued, separate from the twelve
previous acceptances. Automatic monitoring subsequently completed English and
Polish reads at 18:01:20 and 18:03:24 UTC, both with zero pending replies and no
active sending run. This establishes the recent-conversation scheduler path,
without actual creator-response evidence. The final reserved release is November 2 at 04:44:57 UTC
(10:14:57 IST), conditional on the running worker, final guards and 24-hour packet
expiry. Confirmed creator interest and owner handoffs remain zero. SMTP acceptance
does not prove inbox placement; no reply-rate or revenue improvement was measured.

## Experiment 39 — Grounded creator plans and preparation batches (2026-11-02)

Method: respond to the November 1 source/product review with a smaller model
contract. New drafts accept only issued evidence/angle IDs, then use authored
English/Polish rendering and frozen source/context/campaign provenance. Compare
this path with synthetic regressions derived from the observed free-copy failure
classes, retaining legacy snapshots, deterministic terms and exact approval.
Separately exercise preparation-only batches through the existing PostgreSQL
task/outbox/audit path, including concurrency and durable reservations.

The preceding launch returned nineteen local-Qwen copies and five unavailable
results from twenty-four tasks; final review retained one exact AI email and
used twenty-three manual replacements. Intermediate review snapshots included
queued drafts, so their rejection reasons do not establish a clean semantic
failure rate. No creator-feedback outcome is inferred from operator copy review.

Observed development checks: the extended disposable-database script passed
container Ruff and a read-only, network-isolated import check with synthetic
settings. The actual creator interface passed networkless desktop/mobile checks
for draft-queue controls, selected-plan/source provenance and unchanged exact
individual preparation. These checks make no provider or SMTP request. After
the actual combined image build, container lint and all 1,049 tests passed via
`./scripts/test.ps1 -SkipBuild`. The complete verifier subsequently passed all
twenty-one disposable PostgreSQL draft/batch groups, including source/copy
tampering, explicit legacy preservation, durable skips/resume, cross-campaign
identity deduplication, cancellation, lease waits and concurrent shared-budget
exhaustion. The full verifier then completed successfully, including native,
workflow, scheduler, research, all creator/career PostgreSQL groups, both UIs,
planner, delivery and recovery. `doctor.ps1 -Agent` and `agent-smoke.ps1` also
passed, with a real `free/default` Mistral route response. That route canary is
separate from the local creator-generation proof below.

Five governed real-model preparations were subsequently issued within the
remaining allowance: one regression draft and two two-creator batches, one
English and one Polish. Both batch parents reserved two medium-risk items;
issuance created no outgoing email action. All thirty rolling-day preparation
slots were then reserved; no further preparations were issued at that cap.
All five v2 draft tasks subsequently succeeded through local Ollama `qwen3:8b`,
with no errors. Both parents succeeded, each issuing two children with no
remaining reservations or skipped items. The selected angles included a short
clip, building goal, walkthrough and first-session proposals. Complete emails
were 190–227 words. Complete-copy and independent source/terms review judged
all five usable unchanged, including the earlier rejected Polish security-claim
case without that unsupported
capability assumption. This is an unmatched five-case sample, not a representative
holdout, model retraining or a measured general accuracy/reply-rate improvement.
No outgoing action was created by either parent; separate exact-message approval
and paced delivery remain distinct results.

The final November 2 checkpoint retained two SMTP acceptances and twenty-two
queued packets from the already approved twenty-four-message launch. Two new
grounded emails, one English and one Polish, were individually prepared,
compared with the exact reviewed bodies and approved through the normal API.
Both are queued for November 2 at 18:03:40 and 18:36:21 UTC, before their
18:58:53 UTC packet expiry. Total current-scope invitations are twenty-six:
two accepted, twenty-four queued and zero failed. The other three canary drafts
remain ready/unprepared, including the regression-only case. Batch issuance
did not approve its own messages. Shared twenty-four/day, three/hour, gaps and
jitter remain unchanged. The earlier twelve acceptances are separate; pending
reply reviews, confirmed interest and owner handoffs remain zero. Acceptance is
not inbox-placement proof, and queued packets still depend on execution, expiry
and final guards. No reply-rate or revenue improvement was measured.

## 2026-11-02 — Synthetic fit-age separation

Executed the prior `career.py` from commit `297ae97` and current version 2 in
the same container against an identical synthetic Software Engineer role with
five literal saved-skill matches, India location, no required-term/remote bonus
and a 72-hour window. No model or provider request was made.

| Age | Previous score | Version 2 score | Previous passes 75 | Version 2 passes 75 |
|---|---|---|---|---|
| 1 hour | 80 | 100 | Yes | Yes |
| 25 hours | 72 | 100 | No | Yes |
| 49 hours | 64 | 100 | No | Yes |
| 71 hours | 64 | 100 | No | Yes |
| 73 hours | Excluded | Excluded | No | No |

This confirms the scoring/freshness defect and its bounded correction for the
fixture. It does not calibrate fit, validate qualifications, measure semantic
accuracy or demonstrate better applications, interviews or offers. Separate
browser fixtures verify a real synthetic PDF upload, explicit opt-out/radio
selection and refusal before receipt for unknown documents/default controls.

## 2026-11-02 — Local career schema compatibility

Pinned Ollama 0.32.5 rejected the initial grounded draft schema with HTTP 400
before generation: its llama.cpp b10091 grammar parser cannot compile the
2,000/6,000 character repetitions produced by the strict string bounds.
`uniqueItems` is also unsupported by its schema converter. A synthetic request
reproduced the failure without using a résumé or external provider.

After separating the local transport grammar from the strict prompt/server
contract, the normal Qwen3 8B generator returned a valid grounded structure in
15.1 seconds: 146 words, three of three exact evidence selections, four supported
keywords and 1,473 recorded tokens. A synthetic corrective request took 8.1
seconds and 1,423 tokens. Both remained review-required for placeholder output;
neither is an application-quality pass or an eligibility benchmark. No real
application was submitted. Full parser length, duplicate and provenance checks
were retained. Exact upstream references are in the
[career operations guide](../docs/operations/dashboard-and-career.md).

## Experiment 41 — Explicit business context and reviewed continuation (2026-11-02)

Method: remove every email span from the text used to establish positive
commercial context before any bounded excerpt is selected. Keep original
evidence, negative-context refusal, source review and authorization separate.
The creator-intelligence suite passed seventy-five tests, including thirty-two
new regressions for address-only labels and bounded neighboring/preceding-line
cases. These cases establish the tested candidate-filter behavior, not address
ownership, consent, deliverability or response rate.

The initial combined image passed lint and 1,210 tests. A real compact snapshot
probe exposed typed-date and nested action-array projection defects; corrected
native regressions use actual parsed JSON and bounded creation-window cases.
Bulk discovery was held until active reviewed evidence was protected under the
existing campaign/prospect locks. The guard records aggregate protected counts,
adds no task/action row locks and leaves explicit refresh invalidation intact.
Twelve disposable creator-research PostgreSQL groups verified active AI/manual
packets, terminal/expiry release, new insertion, protection after row waits and
explicit refresh still refusing a final side-effect receipt. Before the actual
recovery-pacing audit, this image passed lint/all 1,216 tests and the complete
native, career/creator PostgreSQL,
workflow/scheduler, UI, planner, delivery and recovery verifier.

The two previously reviewed ready messages were individually prepared unchanged
and approved. Their reserved November 2 releases are 19:07:12 and 19:37:35 UTC,
before the 20:02:16 UTC packet expiry. The out-of-window regression remains held.
The continuation retains six new introductions per rolling day combined, existing
shared pacing/preparation/refresh allowances and individual exact review.

Both campaigns' native daily discovery was enabled without changing other
copy/compensation/targeting fields. Actual scheduled scans completed around
November 2 at 05:21 UTC:

| Campaign | Researched records | New | Updated | Protected | Business-contact candidate observations | Automatic authorizations |
|---|---:|---:|---:|---:|---:|---:|
| English | 134 | 22 | 105 | 7 | 31 | 0 |
| Polish | 44 | 7 | 34 | 3 | 10 | 0 |
| Total | 178 | 29 | 139 | 10 | 41 | 0 |

These are record/candidate observations across campaigns, not unique creators,
qualified leads or consent. The next native scans were scheduled for November 3
around 05:21 UTC. Before/after reads preserved all four queued v2
bodies, digests and research snapshots. A six-GET live compact snapshot verified
fresh mailbox monitoring in both campaigns, twenty-eight scoped initial actions,
a complete current creation window and zero pending reply reviews.

The hourly heartbeat was created active and its saved current-chat/hourly
configuration verified. At that initial checkpoint no scheduled Codex wake had
been observed; the manual snapshot and native scans were separate evidence.
At November 2, 05:45:50 UTC, the twenty-eight-invitation scope had twenty-three
SMTP acceptances, four runnable queued v2 packets and one blocked action with a
dead-lettered task; the action-only projection labeled five queued. Twelve
earlier acceptances are separate. Both monitors were fresh, the creation window
complete and pending replies zero. Confirmed interest and handoffs remained
zero. No queued message, candidate or schedule is counted as inbox arrival, an
interested lead, model learning or a response-rate improvement.

### Actual-send recovery audit and correction

Seventeen actual SMTP acceptances occurred between November 2, 05:18:23 and
05:19:39 UTC after recovery. They were not reservation timestamps. Spaced
approval reservations plus a final not-in-the-future check did not enforce the
configured 900/1,800-second gaps or three-per-hour policy when many old slots
were overdue. The prior local gate therefore does not establish this behavior.

The earlier API checkpoint of five queued actions also included one whose
linked task was dead-lettered after lease exhaustion. The refined state was
twenty-three accepted, four runnable queued v2 packets and one blocked action;
the blocked action/task had zero receipts and no established SMTP acceptance.
It was held without replacement.

ADR-0034's correction was rebuilt and deployed. Approval and actual receipt
acquisition share an advisory database gate; conservative receipt completion
history and unresolved sending enforce the stricter frozen/current policy.
Durable pre-receipt deferral retains the original packet, refunds its claim
attempt and requeues through the outbox without extending expiry. Insufficient
time refuses, and post-wait lease/approval checks use wall-clock time.

The first new suite had 1,225 passes and one obsolete source-string assertion
failure, corrected to the new boundary/deferral contract. The final image passed
lint/all 1,226 tests and the complete verifier. Its disposable PostgreSQL proof
established:

- Two concurrent overdue attempts create exactly one receipt and one deferral.
- Old unresolved sending blocks further egress; actual acceptance/ambiguous
  completion overrides old reservations, and a new approval honors actual history.
- A looser current policy cannot relax a saved stricter gap; jitter remains
  anchored to the actual constraint.
- Deferral preserves the complete packet/hash/expiry, clears the lease, leaves
  no error or receipt, refunds the attempt and matches schedule/outbox release.
- No slot before expiry refuses; lease and approval expiry while waiting on the
  global advisory gate both refuse before creating a receipt.

The full verifier also passed native helper, creator/career PostgreSQL, both
UIs, workflow/scheduler, planner and recovery paths. This is local synthetic
proof of the deployed gate, not a new external SMTP pacing canary or evidence
of inbox placement, interest or improved response rates.

### Combined-main integration verification

The independently merged career milestone and creator changes passed a fresh
combined rebuild: Ruff/all 1,321 tests, `test.ps1` and the complete verifier.
Seventeen added guard regressions distinguish default locking from post-lock
plain reads. Existing Apply, career-contact and creator-run guards still acquire
their initial locks; only the recheck after the global pacing wait uses the
internal nonlocking path against already-held scope.

Twenty creator-automation PostgreSQL groups included four actual global-wait
cases for run expiry, Gmail freshness, publication age and the AI draft's seven-
day lifetime. Six career-contact groups included expiry across that wait and
opt-out serialization. The other PostgreSQL, native helper, both UIs, planner,
delivery and queue-recovery proofs passed. Agent doctor passed, and a real
free/default gateway request returned exact `ROUTE_OK` through Mistral Small
3.2. No new local Qwen response or external SMTP pacing canary is inferred.
At that integration checkpoint the delivery/reply projection was twenty-three
accepted, four queued, one zero-receipt blocked action and zero pending replies;
the old regression draft was held. These checks establish integration behavior,
not creator interest.

### Later live pacing and reviewer checkpoint

At November 2, 19:57 UTC (November 3, 01:27 IST), matching the exact original
twenty-eight invitation IDs to a complete API action page established twenty-
seven SMTP acceptances, zero runnable queued and one unchanged blocked task;
the result was confirmed again at 20:02 UTC. All four previously approved v2
invitations were accepted with unchanged reviewed context. Their consecutive
acceptance gaps were 1,959.888540, 1,850.969555 and 1,821.906906 seconds, each above
the configured 1,800-second same-domain gap. This small actual-send canary is
separate from the earlier synthetic proof and the recorded recovery burst.

Scheduled reviewer cycles were observed since 06:20 UTC, with fresh label
monitoring and zero pending replies. One new draft requested at 19:06 UTC failed
at 19:09 UTC with `CREATOR_DRAFT_MODEL_UNAVAILABLE` and local inference unavailable;
no replacement packet or manual fallback was created. New AI introductions are
held; monitoring continues. No interest/handoff, inbox-placement or general
pacing guarantee is inferred. This checkpoint adds no runtime behavior.

## Experiment 42 — Creator local recovery baseline and bounded strategy change

Date: 2026-11-03.

The recorded local Creator invocation ran from November 2, 19:06:52 through
19:09:53 UTC and failed as unavailable without token usage. Its generic error
cannot retrospectively establish whether loading, device execution, transport or
another phase caused the timeout. At the November 3 maintenance inspection,
Qwen3 8B was cached at 5.2 GB, no model was loaded, the RTX 4070 Laptop exposed
8,188 MiB and Docker retained an NVIDIA device assignment. An internal worker TCP
connection to Ollama succeeded in 0.009 seconds; no HTTP proxy was configured.
These observations establish prerequisites, not successful inference.

Targeted synthetic regressions exercised terminal response-read failures, fixed
safe diagnostics, explicit local-only hosted non-use, immutable rendering and
EN/PL terms. Synthetic small-creator copy with the same brief/terms/footer changed
from 162 to 142 words in English and 141 to 128 in Polish. These are artificial
length measurements, not creator feedback or evidence of improved replies. Old
unmarked v2 EN/PL digest goldens remain unchanged. Complete integration tests and
an audited real local-only draft remain separate gates before operational recovery
can be claimed. No new live model call or outreach is inferred from these tests.

The final isolated source run passed Ruff/all 1,641 tests and the complete native,
PostgreSQL, browser, planner, delivery and recovery verifier. Its root/source
comparison found all fourteen changed non-documentation files identical. All
live container ID/image/start/restart fingerprints were preserved, with synthetic
validation credentials and external model/mail/discovery providers disabled.
The preceding failed runs are not successful integration evidence: one exposed
socket-only PostgreSQL initialization readiness before TCP migration access; the
second exposed a private Docker Desktop host-port publication issue under an
extra internal-network override. TCP readiness and a separate ordinary test
bridge resolved those respective cases. New quotation regressions also preserve
the public title as escaped data or refuse overlong expansion. No actual local
generation or creator response is claimed by the isolated verifier.

### Real cold/warm generation and reviewed restart

After PR #92 deployment, two normal audited local-only preparation tasks used
cached Qwen3 8B. The first began unloaded and completed in 170,384 ms with
700 prompt/15 completion tokens; the second began while resident and completed
in 2,642 ms with 601/15 tokens. Each succeeded on its first local invocation,
with zero recorded credits and no corrective generation or manual replacement.
Runtime inspection reported 100% GPU placement, 6.2 GB resident size and an
8,192-token context. These establish current generation; they do not establish
the exact cause of the earlier generic unavailable failure.

The cold timing leaves less than ten seconds of margin under 180 seconds.
The follow-up keeps a fixed bound but gives grounded requests a 300-second
socket response window; legacy remains 180. Targeted regressions exercise both
routes and retain fixed error, size and single-transport-attempt assertions.
Leases renew independently; cancellation/context/expiry are rechecked on return.
This is not an end-to-end task wall-clock bound or a second transport attempt.

Complete-copy review retained two new English messages unchanged at 212 and
204 words including terms/footer. At November 3, 09:10 UTC (14:40 IST), one new
exact-approved invitation was SMTP-accepted and one was queued for its paced
09:39:47 UTC slot within its real expiry. The original twenty-eight-invitation
batch remained twenty-seven accepted plus one unchanged blocked task; twelve
earlier acceptances are separate. Both reply monitors were fresh with zero
pending replies. No creator-interest, handoff, inbox-placement or causal
reply-improvement claim follows from these observations.

The headroom follow-up separately passed all 1,641 tests and the full isolated
verifier. The three changed source/test files matched the frozen checkout;
live container fingerprints remained unchanged. The earlier real canaries used
the previous 180-second window; the subsequent change supplies additional
response margin with otherwise unchanged transport/selection/approval behavior.

### Live inbound metadata observation

At November 3, 12:43 UTC (18:13 IST), two incoming English-campaign metadata
records matched the exact sender addresses and normalized outreach subjects of
the two earlier SMTP-accepted invitations. Both received timestamps followed
their corresponding acceptances. The earlier record retained its stored
identity and creation time across three complete same-mailbox label syncs;
the later record first appeared in the latest snapshot. Both monitors were fresh.

Both records remain unreviewed. The adapter exposes metadata and bounded
provider snippets, not complete authored messages. Full text was requested from
the owner; no review mutation, new approval or handoff was made at this checkpoint.
These observations establish the sampled intake/matching and one stable-record
case. They do not establish sender authenticity, full-message intent, general
replay reliability, collaboration or a causal response-rate improvement.

## Experiment 43 — Bounded automatic creator-reply evidence

Date: 2026-11-03.

The pure MIME parser passed 49 synthetic cases and Ruff. Focused Creator
transport/lifecycle checks passed 146 tests; the shared Gmail adapter suite
passed 107. These are overlapping suite scopes, not a combined test total.
The latter verifies fixed, bounded refresh-grant diagnosis without retaining
provider descriptions or mistaking unrelated HTTP 400 responses for expiry.

An exact-source PostgreSQL proof used a new internal network, pinned cached
image, synthetic credentials and no host ports or providers. All 25 Creator
scenario groups passed, including four new capture/retry/crash/cancellation
groups and a freshness-failure group. Two existing metadata-only records gained
complete private evidence without changing their original identities, previews
or review state. Complete snapshots refused recapture; missing/stale digests
refused semantic review; stale owners could not overwrite reclaimed evidence.
A newer failed sync blocked a still-recent complete read despite newer queued
work; a later owned completion restored freshness while retaining failure history.

The first narrow run reached the correct stale-owner rejection but expected the
wrong exception type. Its assertion was corrected; the full repeated proof
passed. Docker's default network pools were exhausted, so the isolated proof used
an explicitly checked unused subnet. No existing network or volume was deleted;
the created test instance was stopped and its evidence/volume retained.

Network-disabled browser proofs exercised the actual dashboard sources: inert
complete text beyond previews, incomplete-review refusal, exact digest payloads,
inline conflicts, preserved notes, late-response isolation, canceled polling,
mobile wrapping and failed-sync hold/recovery. Screenshots were inspected.

A separate read-only check using the existing OAuth helper confirmed an invalid
old refresh grant without changing settings or printing credentials. Renewal
was opened for the recorded account/client/scope. Full source gates, live
connection recovery, real body retrieval and any handoff are separate evidence;
none is inferred from the synthetic results above.

The first frozen-source run passed all 1,734 tests and the complete isolated
verifier, preserving live container fingerprints. Final rollout review added
default-empty explicit campaign UUID selection because the installed campaign
set is larger than the authorized job. Focused Creator coverage then passed
152 tests and settings coverage passed 34, including refusal of malformed,
unbounded or duplicate campaign scope. The final frozen-source run subsequently
passed Ruff/all 1,750 tests, Compose configuration, `test.ps1` and the complete
isolated `verify.ps1`, including all 25 Creator database groups and the browser
proofs. Live fingerprints remained unchanged and no live credentials were copied.
CI and merged-source deployment remain publication gates; neither run establishes
live Gmail access, actual reply interpretation or a sent handoff.

## Planned experiments

- Compare `qwen3:8b` local latency and tool-call reliability against one remote
  free route using the same harmless task set.
- Record route availability, throttling, latency, and human-intervention rate.
- Evaluate Prime Agent only inside a disposable worktree/container with a fixed
  token/time/tool budget.

## Experiment 44 — Live complete replies and draft-only response preparation

On November 4, owner same-account consent completed through the existing helper.
The saved grant retained the recorded Desktop client, exact read-only scope,
mailbox and Creator label checks. The previously merged source was reloaded only
for API/job-worker; eighty tracked app/static files matched across five roles.
Visible Career configuration/run-core, environment across reload and durable
volume mappings were preserved; hidden grant bindings are not exposed by the API.

Two complete governed syncs succeeded at 05:48:25 and 05:48:31 UTC. The second
captured two existing matched bodies in two full-message reads, with zero
unavailable bodies and no mailbox writes. Complete authored review confirmed one
willingness to talk on Discord, not commercial acceptance. A second commercial
policy reply remains pending rather than being forced into an inaccurate
category. After the owner's no-reply instruction, the prepared handoff and task
were confirmed cancelled; both contacts retained their evidence but had null
sending authorization and no opt-out suppression. No reply email was approved.

These observations prove the sampled recovery and reading/review path. They do
not establish general incoming replay, external handoff, collaboration, token
longevity or a response-rate improvement. New response-curation source tests and
real local generation remain separate checks until recorded below.

The initial full frozen-source run passed all 1,797 tests and the complete
isolated verifier. A final pagination correction added two regressions: unfinished
message IDs or a next-page cursor cannot queue drafts; the store also requires
current-task durable completion. The final frozen-source run passed all 1,799
tests, Ruff, Compose, `test.ps1`, the complete isolated `verify.ps1`, 27 Creator
PostgreSQL groups and actual-source network-disabled browser proofs. Both live
container fingerprint comparisons passed, with synthetic provider configuration.
The optional agent doctor and harmless configured gateway-route smoke passed;
that hosted route check does not prove local response generation. Live curation
and merged-source deployment remain separate checks.

## 2026-11-02 — Career platform and eligibility verification

The final isolated platform build passed Compose configuration, Ruff/all 1,552
unit/contract tests, test.ps1, the complete verify.ps1 and git diff --check.
Seven new disposable PostgreSQL groups verified source/fact persistence, omitted
field preservation, private evidence stripping, YC upsert and migration replay,
mandatory selection/approval/receipt gates, and policy/fact grant invalidation.
No HTTP/SMTP requests or side-effect receipts were allowed in that database proof.

Network-disabled desktop/mobile dashboard checks exercised actual edit/save HTTP
payloads, paired reference import, YC manual-only status, escaped public evidence,
reference preservation/removal and tri-state India facts. Screenshots were inspected.
The single Impeccable detector returned [] only in degraded regex mode because
optional parser modules were unavailable; computed contrast was not evaluated.
These checks establish local behavior, not external ATS compatibility, job authenticity,
eligibility accuracy, Gmail tracking or improved hiring outcomes. No inference route
was changed or local-model canary claimed for this milestone.

## 2026-11-02 — YC public schema correction measurements

The initial expanded governed scan returned 1,444 normalized records, zero matches
and twenty YC list failures. It exposed an inaccurate fixture assumption: generic
jobs navigation had been used as company identity. The correction requires the
actual canonical public companyUrl plus matching company.slug and retains all
other origin, posting, date and account restrictions. Nine additional regressions
bring the passing unit/contract suite to 1,561 tests with Ruff clean.

Bounded real public parser canaries observed ClickPe 2, SuperKalam 10 and Aviator
5 listing records. Two details each produced six stale exclusions, zero invalid
records and zero list/detail failures. No inference, account or application was
used. This proves those sampled public reads, not current vacancies or general
provider compatibility; governed runtime verification is recorded separately.
The final isolated fix build also passed Compose configuration, test.ps1,
the complete verify.ps1 and git diff --check. Independent source review confirmed
the existing origin/account/identity/date/request boundaries remain intact.

## 2026-11-04 — Greenhouse publication evidence and resumed application audit

The renewed native search returned 1,546 normalized listings, zero matches and
zero model calls; 70/71 sources succeeded. Independent read-only audits found
zero recorded applications, successful application receipts, linked Career email
receipts or executing/ambiguous Career actions. These counts are separate from
Creator outreach and do not imply a job application was submitted.

The fresh Karya lead had explicit publication evidence but scored 47 against the
saved minimum 75 and had unverified enrollment; it remained ineligible. Primary
provider documentation and real API responses distinguish first_published from
updated_at. New regression cases cover strict timestamp types, offset normalization,
missing updates, old publication versus recent update, future dates, narrower run
windows, the exact 72-hour boundary, and unchanged fit/enrollment blockers.
A pre-freeze image failed two lint checks; the current frozen source passed all
1,781 tests and the combined Creator/Career source passed all 1,830 with Ruff clean.
The isolated full verifier and governed provider canary are separate final gates.
The final combined build passed those gates: Compose configuration, `test.ps1`,
the complete `verify.ps1` and diff checks, including 27 Creator database groups
and actual-source browser proofs. The isolated governed Greenhouse search read
twenty public Karya records and retained the exact `2026-11-02T11:50:48Z`
publication with `published` provenance. The empty synthetic discovery profile
had preparation disabled and no Apply grant; the task made zero model calls and
created zero actions. This is source-contract proof, not a real-candidate fit or
submission result. Isolated services were then stopped, retaining their volumes.
