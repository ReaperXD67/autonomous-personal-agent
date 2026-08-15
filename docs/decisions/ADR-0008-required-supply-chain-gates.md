# ADR-0008 — Required supply-chain gates and SBOM

Status: Accepted

## Context

Dependency updates were pinned and tested, but the required branch check did not
scan pull-request dependency changes, repository secrets/misconfiguration,
locked dependencies, or the built runtime image. Releases also lacked a machine-
readable bill of materials.

## Decision

- Extend the existing branch-required `validate` job instead of creating a
  non-required security workflow.
- Run GitHub Dependency Review on pull requests and reject high-or-critical new
  advisories.
- Run Trivy `v0.74.0` against the repository and runtime image, failing on fixed
  high-or-critical vulnerabilities while scanning repository secrets and
  configuration as well.
- Generate an SPDX JSON runtime-image SBOM and retain it as a 14-day workflow
  artifact.
- Pin every third-party action to its full commit SHA and leave version comments
  for automated update tooling.

## Alternatives

- Depend only on GitHub's asynchronous advisory UI.
- Run scans in an optional scheduled workflow.
- Upload SARIF with broader token permissions.
- Sign local-only development images without a trusted registry identity.

## Reasoning

Keeping checks in `validate` makes existing branch protection enforce them.
Table output requires only `contents: read`, so forked pull requests do not gain
security-event write permission. An SBOM provides concrete release evidence.
Image signing is deferred until a registry and keyless OIDC identity exist;
pretending an unsigned local tag is a verified release would add no trust.

## Consequences

Pull requests take longer and depend on current vulnerability databases. A new
fixed high-or-critical advisory blocks merge until upgraded or explicitly
documented. SBOM artifacts expire after 14 days and are evidence, not a long-term
archive. Signature verification remains a separate production gate.
