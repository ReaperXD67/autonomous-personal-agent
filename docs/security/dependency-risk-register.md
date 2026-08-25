# Dependency risk register

Last reviewed: 2026-08-25

## Time-bounded Playwright base-attestation exception

Two exact PURLs in the pinned Microsoft Playwright base image's third-party SBOM
are suppressed until 2026-09-25:

| Advisory | Attested package | Runtime evidence | Removal condition |
|---|---|---|---|
| `GHSA-6v7p-g79w-8964` | `pkg:pypi/msgpack@1.1.2` | no importable distribution or matching metadata in the final image | upstream base SBOM/digest no longer reports it, or Trivy inventory confirms a real package and it is upgraded |
| `CVE-2025-47273` | `pkg:pypi/setuptools@70.3.0` | no importable distribution or matching metadata; embedded virtualenv wheels are fixed 82/83 | same |

Trivy itself warns that third-party SBOM input can be inaccurate. A merged-
filesystem inspection found neither distribution, and `importlib.util.find_spec`
returned `None` for both. The separately vendored msgpack under current pip and
fixed setuptools wheels under virtualenv are not the suppressed PURLs. The
exception is constrained by PURL, records a statement in `.trivyignore.yaml`,
and expires in 31 days. It does not ignore any other finding. The action image's
Ubuntu packages, application Python packages, and Playwright Node driver had zero
unsuppressed high/critical findings in the 2026-08-25 Trivy `0.74.0` scan.

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

## Enforced evidence

The branch-required `validate` job now runs GitHub Dependency Review for pull
request changes, Trivy `v0.74.0` over the repository and built runtime image,
and Anchore Syft through the pinned SBOM action. Fixed high/critical findings
fail the job; repository scanning also covers secrets and Dockerfile
misconfiguration. The runtime SPDX JSON SBOM is retained as a workflow artifact
for 14 days.

Local pre-merge evidence on 2026-08-15 found zero high/critical findings in the
locked runtime dependencies, Debian runtime image, or installed Python packages;
zero Dockerfile misconfigurations were reported, and SPDX JSON generation passed.
GitHub CI remains authoritative because it scans a clean checkout without local
ignored files.

Dependabot checks weekly with production and development dependencies grouped
separately; Docker and uv entries track both the control and action workers.
Release-pinned Compose service digests remain an explicit manual review. Reopen
review immediately when a new network-facing advisory appears.

Python base-image updates remain on the declared `>=3.13,<3.14` runtime line.
Dependabot ignores `>=3.14` until a coordinated compatibility change updates the
project constraint, uv source runtime, tests, and deployment evidence together.
