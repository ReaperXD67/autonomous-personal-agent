# Dependency risk register

Last reviewed: 2026-08-11

No dependency risk exception is active.

## Current package state

Direct and transitive Python dependencies are pinned in
`services/control-api/uv.lock`. The August 2026 update moves FastAPI to `0.141.1`,
Starlette to `1.3.1`, pytest to `9.1.1`, and the remaining direct runtime/dev
packages to their tested current versions.

GitHub initially reported seven advisories: one pytest temporary-directory issue
and six Starlette issues. Current pins resolve all seven:

| Package | Resolution | Verification |
|---|---|---|
| pytest `9.1.1` | Above patched `9.0.3` | Ruff + 12-test container suite |
| Starlette `1.3.1` | At latest required patched line | Image build, API health, safe and approval-gated live smoke paths |

The Starlette security update crossed a major version. It was merged only after
local runtime testing and GitHub Actions passed. Repository contract tests also
continue to forbid the unused high-risk surfaces (`StaticFiles`, `FileResponse`,
`HTTPEndpoint`, form parsing, and hostname-derived policy) as defense in depth.

## Review rule

Do not dismiss a future alert without either:

1. upgrading to a patched version and running unit, container, and relevant live
   failure-path tests; or
2. recording the exact affected interface, exposure analysis, compensating
   control, owner, and removal condition here.

Dependabot checks weekly with production and development dependencies grouped
separately; its Docker ecosystem entry tracks the control-service Dockerfile.
Release-pinned Compose service digests remain an explicit manual review. Reopen
review immediately when a new network-facing advisory appears.
