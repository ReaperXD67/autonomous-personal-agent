# ADR-0002: Container-first Windows development

- Status: Accepted
- Date: 2026-08-11

## Context

Local host is Windows; target is Linux KVM VPS. Installing language runtimes,
databases, browser dependencies, and agents directly on Windows increases drift.

## Decision

Run application dependencies in Linux containers through Docker Desktop/WSL2.
Use same Compose model locally and on VPS, with environment-specific ingress and
secret handling. Keep PowerShell lifecycle wrappers for Windows ergonomics.

## Alternatives

- Native Windows installs: faster edit loop for some tools, high parity cost.
- Develop only inside WSL: viable but adds a manual environment contract.
- Devcontainer only: useful later, not required for operation.

## Consequences

Docker is required and initial pulls/builds cost time. In return, dependency
versions, runtime OS, and service topology are reproducible.

