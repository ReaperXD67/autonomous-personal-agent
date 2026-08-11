# ADR-0003: Generated local secrets and explicit configuration

- Status: Accepted
- Date: 2026-08-11

## Context

Repository will eventually hold many high-impact credentials. Example keys often
become real secrets accidentally, and permissive environment inheritance leaks
unrelated credentials to tools.

## Decision

Commit placeholders only. Generate cryptographically random local bootstrap
values into ignored `.env`. Pass each container an explicit environment subset.
Reject placeholder/short control tokens at startup. Plan Docker secrets or an
external manager for VPS.

## Alternatives

- Fixed development passwords: convenient, unsafe and commonly deployed.
- Commit encrypted secrets: requires key-distribution lifecycle too early.
- Docker secrets locally: secure, but uneven Compose/upstream image support.

## Consequences

First boot needs one initialization command. Secret rotation must account for
existing volumes. Optional upstream onboarding stays deliberate rather than
magically fabricating credentials.

