# ADR-0014 — Private VPS before public production

Status: Accepted

## Context

The local alpha uses one service-wide bearer token held in browser memory. Its
containers and networks are narrow, but it does not yet have per-user OIDC,
RBAC, rate limits, step-up approval identity, or centralized secret management.
Putting a reverse proxy in front of that interface would provide TLS without
solving its authorization and abuse-control gaps.

The project nevertheless needs a reproducible single-host deployment path for
one trusted operator. Existing Compose ports already bind to loopback, and the
core lifecycle, approval, backup, and restore mechanisms can be reused on Linux.

## Decision

- Support a private single-operator VPS profile first. Keep all dashboard/admin
  ports on `127.0.0.1` and access them only through SSH, WireGuard, or Tailscale.
- Generate a production-mode owner-only `.env` on the VPS without provider
  credentials and refuse to overwrite an existing secret file.
- Fail preflight for dirty checkouts, placeholders, broad `.env` permissions,
  Mailpit, non-loopback published ports, host networking, privileged mode, or
  Docker-socket mounts.
- Disable OpenAPI discovery and validate Host headers in the application. The
  private VPS bootstrap allows only `localhost` and `127.0.0.1`.
- Make deployment prove a harmless queued task and a separate approval-gated
  task. Provide owner-only checksummed PostgreSQL backup and disposable restore
  commands, while leaving encryption/off-host transfer to deployment tooling.
- Do not treat these controls as authorization to expose the dashboard publicly.
  Public ingress remains blocked until OIDC/RBAC, rate/body limits, TLS, step-up
  identity, centralized secrets, monitoring/incident response, and signed
  release promotion are implemented and verified.

## Alternatives

- Public HTTPS with the bootstrap bearer token: rejected because TLS does not
  add per-user identity, brute-force throttling, revocation, or step-up approval.
- Kubernetes: rejected because a single host does not justify a larger control
  plane or improve the missing identity boundary.
- Manual VPS commands only: rejected because configuration drift could silently
  publish a port, preserve test SMTP, or deploy an unreviewed checkout.
- Wait for the complete public-production platform: rejected because a private
  tunnel provides a smaller useful boundary without weakening authorization.

## Consequences

One trusted operator can deploy and test an exact commit on a VPS without making
the admin surface internet-facing. Host hardening, provider accounts, encrypted
off-host retention, alert delivery, and real external-provider proofs remain
manual because they depend on the chosen host and accounts. The system remains
a private alpha, not a public or multi-user product.
