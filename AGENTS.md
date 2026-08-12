# Repository agent instructions

These rules apply to every coding agent working in this repository.

## Before changing code

1. Inspect `git status`, the current branch, and recent history.
2. Read `README.md`, `docs/roadmap.md`, the relevant architecture/security docs,
   and the latest entry in `engineering/ENGINEERING_JOURNAL.md`.
3. Preserve user changes and never expose `.env`, provider keys, database data,
   browser profiles, backups, or agent memory.

## Engineering boundaries

- Keep PostgreSQL authoritative for durable task, approval, audit, and memory
  state. Redis is reconstructible transport/cache.
- All executable capabilities must enter through the control-plane policy and
  audit path. Hermes, MCP, schedulers, and coding workers may not bypass it.
- Derive risk from an allowlisted capability policy before enabling any real
  tool. Never trust a caller-supplied risk label for authorization.
- Do not mount the Docker socket or unrestricted host paths into agent services.
- Keep new runtimes containerized. Do not install project dependencies directly
  on Windows.
- Pin production images by release and digest after verifying upstream sources.
- Prefer a small explicit component over a new service unless lifecycle,
  security, scaling, or ownership justifies separation.

## Required documentation discipline

For every meaningful implementation:

- append a factual entry to `engineering/ENGINEERING_JOURNAL.md`;
- update `engineering/SYSTEM_EVOLUTION.md` when a boundary changes;
- update `engineering/EXPERIMENT_LOG.md` only with measurements actually run;
- add or supersede an ADR for a significant decision;
- synchronize README, roadmap, operations, architecture, and security claims.

Never mark a profile or integration operational because its container is merely
healthy. Verify a harmless end-to-end request or label it prepared/unverified.

## Validation

Use the narrowest tests during development, then run before handoff:

```powershell
docker compose config --quiet
./scripts/test.ps1
./scripts/verify.ps1
git diff --check
```

If optional inference changed, also run `./scripts/doctor.ps1 -Agent` and
`./scripts/agent-smoke.ps1`. Do not claim local-model validation unless the model
download and a real response both completed.

Record failures and limitations honestly. Do not commit, push, create a pull
request, rotate credentials, delete volumes, or change external accounts unless
the user explicitly requests that action.

The user's standing repository preference is to publish each validated major
milestone all the way to `main`: create or update a `codex/` branch, commit and
push the scoped work, create or update its pull request, and merge it into
`main`. Never publish secrets or work that has not passed the relevant
validation, and honor an explicit request to keep a milestone local.
