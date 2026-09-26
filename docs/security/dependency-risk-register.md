# Dependency risk register

Last reviewed: 2026-09-26

## Retired Playwright bundled-tool exceptions

The two exceptions that expired on 2026-09-25 are removed. The action image now
uses matching Playwright Python/package `1.63.0`, with Microsoft's Noble image
pinned to `sha256:72bd171a9ffc2b4b59532aaa6210e21014d07093120dc25528870c0b840da1f0`.
The official [release](https://github.com/microsoft/playwright-python/releases/tag/v1.63.0)
and registry manifest were checked on 2026-09-26. No unrelated application
dependency changed in the regenerated containerized uv lock.

Upgrading the base alone did not remove the old package records: global pip
`26.2.1` still included `pip/_vendor/bom.cdx.json` entries for
`pkg:pypi/msgpack@1.1.2` and `pkg:pypi/setuptools@70.3.0`. Its vendored msgpack
`1.1.2` Python code was present even though no standalone distribution was
importable. The native `_cmsgpack` extension was absent and `Unpacker` used the
Python fallback; the [upstream fix](https://github.com/msgpack/msgpack-python/commit/2c56ddb5d0025ed481d962c0f5d62d19dec7476d)
changes the native unpacker. Virtualenv `21.7.8` contained setuptools wheels
`82.0.1` and `84.0.0`, not the old attested version. Package absence alone was
therefore insufficient evidence for the former msgpack explanation.

The final Docker stage now uninstalls unused global pip and virtualenv after
`uv sync --frozen`, and removes the build caches. The application's locked
virtual environment is retained. A merged-filesystem inspection of the rebuilt
image found no msgpack/setuptools paths or pip vendor SBOM. Both the global
Python interpreter and application interpreter reported no importable
msgpack/setuptools distribution, and global pip/virtualenv were absent.

Playwright `1.63.0` launched Chromium `153.0.8010.12` and passed text entry,
checkbox and local button interaction in a container with no network, a
read-only filesystem, a temporary `/tmp`, dropped capabilities and the existing
non-root runtime user. `.trivyignore.yaml` now has an empty vulnerability list;
fixed high/critical findings remain blocking in the unfiltered image scan.

Trivy `0.74.0`, with its vulnerability database refreshed on 2026-09-26, scanned
the cleaned image at 08:45 UTC with no exceptions and reported **zero fixable
high/critical findings** across Ubuntu packages, the Playwright Node driver,
Python packages and the uv binary (`--severity HIGH,CRITICAL --ignore-unfixed`,
exit code 0). The archive was staged inside the scanner's Linux filesystem;
the scanner had no Docker socket. This does not claim that unfixed or lower-
severity advisories are absent.

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

## September 2026 Debian PCRE2 security update

The 2026-09-13 clean-checkout scan newly flagged `libpcre2-8-0=10.42-1` in
the pinned Python Bookworm image. Debian identifies `10.42-1+deb12u1` as fixed
for [CVE-2026-86145](https://security-tracker.debian.org/tracker/CVE-2026-86145)
and [CVE-2026-89161](https://security-tracker.debian.org/tracker/CVE-2026-89161).

The control Dockerfile retains the verified Python release/digest and adds a
shared base stage with an exact-version upgrade of that existing package.
Dependency, test, and runtime stages inherit the patch. APT verifies signed
Debian repository metadata; package lists are removed from the final layer.
No broad distribution upgrade or vulnerability suppression was introduced.
Future removal depends on verifying that a replacement pinned Python base
already contains the patched version. Ubuntu Noble's status must be evaluated
separately; the Debian patch does not establish that the Playwright base is fixed.

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
