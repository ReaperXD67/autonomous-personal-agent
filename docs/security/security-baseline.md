# Security baseline

## Default autonomy policy

| Risk | Examples | Default |
|---|---|---|
| Low | read, classify, summarize, research | May queue automatically after validation |
| Medium | create draft, modify sandbox file, open draft PR | Allowed only to capability-specific sandbox; fully audited |
| High | send email, submit application, merge/publish, change infrastructure | Human approval required |
| Destructive | delete data/repository, destructive shell, purchases/transfers | Human approval required plus future step-up authentication; disabled today |

The implemented capability allowlist derives a minimum risk from the task kind.
A caller-provided risk may escalate that result but cannot lower it. Every new
capability must enter this registry before its handler is reachable.

## Implemented controls

- generated local secrets; placeholder rejection in control API;
- constant-time bearer token comparison;
- loopback-only published interfaces;
- no PostgreSQL/Redis host ports;
- password-protected Redis and PostgreSQL;
- internal data/model networks;
- non-root, read-only application containers with all capabilities dropped;
- health checks and dependency-gated startup;
- approval state persisted before queue publication;
- structured logs without headers/bodies;
- redacted audit metadata with correlation IDs;
- uniquely owned worker leases, heartbeats, cooperative cancellation, bounded
  retry delays, and authenticated dead-letter inspection;
- upstream images pinned by release and manifest digest;
- MCP servers disabled by default;
- career-source HTTPS hosts, redirects, response sizes, timeouts, and board
  slugs allowlisted; arbitrary URLs rejected;
- résumé text excluded from queue/task/audit/public-source payloads and local
  draft output constrained to a structured schema;
- required immutable-action CI gates for dependency review, repository
  vulnerability/secret/misconfiguration scanning, runtime-image vulnerability
  scanning, and an SPDX JSON SBOM artifact;

## Secrets

Never commit `.env`, private keys, OAuth tokens, browser profiles, database
files, or rendered Hermes config. Use scoped credentials per integration.
Provider keys must not share privileges with GitHub/email/admin tokens. Rotate
after exposure, remove from history using approved incident procedure, and
assume logs/artifacts containing a leaked value are compromised.

## Actions still required before production

- HTTPS reverse proxy, authenticated admin access, and API rate limiting;
- secrets manager/Docker secrets support;
- short-lived identity and per-user authorization, replacing one bootstrap token;
- signed release images and upstream image-signature verification;
- egress allowlists for browser/email/tool workers;
- OIDC/RBAC and rate limits before any non-private dashboard exposure;
- idempotent side-effect keys for future external write tools;
- backup encryption, off-host retention/scheduling, and incident response;

## Unsafe configurations

Never mount `/var/run/docker.sock` into Hermes or general workers; never mount
host home/root; never use privileged mode/host networking; never expose admin
dashboards without authentication; never disable approval to fix workflow
friction; never log request bodies by default.
