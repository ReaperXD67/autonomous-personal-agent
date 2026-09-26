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
- constant-time bearer/session/CSRF comparisons;
- 90-second one-use browser bootstraps, immediate URL-fragment scrubbing,
  signed HttpOnly SameSite=Strict sessions, exact same-origin checks, and CSRF
  headers on cookie-authenticated writes; bearer auth remains for scripts;
- disabled OpenAPI/docs routes and explicit Host-header allowlisting;
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
- isolated Playwright runtime with exact ATS host/same-host request policy,
  disposable browser context, no login/CAPTCHA bypass, and no host profile;
- exact external-action SHA-256 approval binding, expiry, résumé/draft/form
  revalidation, one-attempt policy, and durable pre-side-effect receipts;
- deployment-fixed SMTP endpoint/sender, external TLS enforcement, single
  validated recipient, and local-only no-TLS Mailpit test mode;
- atomic external-SMTP schedule reservation with bounded 15-minute global and
  30-minute same-domain gaps, rolling 3/hour and 12/day caps, deterministic
  jitter, restart-safe outbox release, and a final due-time check;
- test-profile startup explicitly blanks deployment SMTP username/password
  before creating Mailpit-mode containers;
- official-host-only YouTube research with a worker-scoped API key, bounded
  queries/results, and unreviewed public business-contact candidates with source
  excerpts; discovery never grants contact authorization;
- transactionally reserved YouTube search calls across campaigns, bounded pages,
  cooperative cancellation, quota/rate stops, and complete authenticated creator
  exports with formula escaping and explicit eligibility/suppression evidence;
- operator-recorded public-contact source/basis/authorization, durable opt-out
  and bounce suppression, and pre-SMTP reply-state revalidation;
- evidence-thresholded creator-copy adaptation limited to fixed draft variants;
  it cannot alter contacts, offers, budgets, capability risk, code, approvals,
  or sending authority;
- résumé text excluded from queue/task/audit/public-source payloads and local
  draft output constrained to a structured schema;
- hosted résumé drafting disabled by default; its only eligible model IDs end in
  `:free`, carry zero catalog price, appear in the active ZDR endpoint inventory,
  and return zero usage cost; no-training/ZDR provider filters, an atomic daily
  cap, separately reserved semantic retries, and local fallback fail closed on
  cost, invalid output, or privacy availability;
- OpenRouter inference key scoped to the career worker and Hermes only;
  model/prompt/response content is excluded from the career inference ledger;
- explicit Hermes routing order: OmniRoute `free/default`, OpenRouter
  `openrouter/free`, then local Qwen; diagnostics report route composition and
  production startup refuses a missing secondary key;
- local Qwen weights load on the first final-fallback request and expire after
  idle time; no Docker socket or host controller is exposed to the agent;
- required immutable-action CI gates for dependency review, repository
  vulnerability/secret/misconfiguration scanning, runtime-image vulnerability
  scanning, and an SPDX JSON SBOM artifact;
- private-VPS scripts that generate owner-only secrets, reject dirty checkouts,
  placeholders, Mailpit, non-loopback ports, host networking, privileged mode,
  and Docker-socket mounts before deployment;
- boot-managed systemd startup plus a persistent non-generating provider-health
  timer; Compose retains per-container restart policies;

## Secrets

Never commit `.env`, private keys, OAuth tokens, browser profiles, database
files, rendered Hermes config, session cookies, or one-use login URLs. Use
scoped credentials per integration.
Provider keys must not share privileges with GitHub/email/admin tokens. Rotate
after exposure, remove from history using approved incident procedure, and
assume logs/artifacts containing a leaked value are compromised.

## Actions still required before public production

- HTTPS reverse proxy, authenticated admin access, and API rate limiting;
- secrets manager/Docker secrets support;
- short-lived identity and per-user authorization, replacing one bootstrap token;
- signed release images and upstream image-signature verification;
- egress allowlists for browser/email/tool workers;
- OIDC/RBAC and rate limits before any non-private dashboard exposure;
- provider reconciliation/runbook for side effects left `ambiguous` after a
  crash at the external boundary;
- backup encryption, off-host retention/scheduling, and incident response;

## Workflow authority

Workflow plans can invoke only foundation echo/wait, allowlisted career search,
draft/preflight, and creator discovery. Each step derives risk from capability
policy; caller risk can only increase it. Raw email send and application submit
are excluded. Exact external actions must still be prepared and individually
approved through the existing action path. A workflow does not authorize an
external action or allow an LLM to change its own policy.

Plans reject cycles, unknown references, oversized inputs, and arbitrary result
expressions. Result checks compare explicit top-level scalar values without
string/boolean coercion. Workflow audit stores IDs/statuses, not objectives,
payload values, or expected evidence. Workflow creation/read/cancel uses the
existing bearer or same-origin session/CSRF controls. No new credentials,
networks, mounts, model providers, or executor capabilities are granted.

## Goal proposal and evidence authority

`planning.propose` derives medium risk from the capability allowlist. Models see
only the user-supplied goal and opaque action descriptions; stored résumés,
contacts, job text, context IDs, and executable payloads are not included.
Strict output validation compiles only the selected inventory, with no raw send,
submit, coding, recursive planner, or arbitrary URL action. Lease and task-to-plan
checks fence stale or forged worker writes. Adoption checks the exact digest,
expiry, completed task, and current selected context before atomic workflow
creation. Models do not approve their proposals.

Readiness reports accept only fixed fields/check IDs/reason codes, timestamps,
durations, revision/dirty state, and allowlisted configuration booleans. Browser
session authentication cannot publish evidence. The service-wide operator token
can attest a report; evidence is not cryptographically trusted or a promise of
future liveness. Fixture results never imply real SMTP or universal ATS success.

## Unsafe configurations

SMTP connection diagnostics accept an empty execution payload and cannot choose
another host, sender, TLS mode, or credential. They derive medium risk and one
attempt from server policy. The private status API projects only allowlisted
scalar evidence. Browser submissions require the existing same-origin session
and CSRF checks. Generic setup keeps credentials in ignored local configuration.

The side-effect boundary rechecks the current lease, cancellation, expiry after
row-lock waits, and both frozen contexts before creating a receipt. Stale workers
cannot record action failures. Once SMTP acceptance is durably known, cleanup or
task failure cannot erase it. A crash between external acceptance and its durable
commit remains uncertain; this does not provide exactly-once external delivery.

Pacing is abuse/reputation defense, not a spam-filter bypass. Inbox placement
still depends on recipient relevance and consent, SPF/DKIM/DMARC alignment,
provider/IP reputation, complaint and bounce handling, message content, and
working unsubscribe handling where required. Hermes does not fabricate an RFC
8058 one-click URL without a real public suppression endpoint.

Never mount `/var/run/docker.sock` into Hermes or general workers; never mount
host home/root; never use privileged mode/host networking; never expose admin
dashboards without authentication; never disable approval to fix workflow
friction; never log request bodies by default.

The current application/email adapter deliberately optimizes the work around
approval rather than replacing authorization with an “intelligent” model. An
LLM cannot approve its own external action, infer legal consent, or change the
capability policy that authorizes its executor.


### Scoped career authorization and Gmail (2026-09-23)

An explicit Apply-mode Play grant may authorize exact career actions while
retaining high risk, digest-bound approvals, audit and receipts. It is scoped to
a frozen profile, known posting dates, selected destinations, explicit answers,
rolling cap and expiry. The action boundary checks pause and content changes;
no agent may broaden the grant. Gmail is read-only, matched to the profile
mailbox, label-restricted in the adapter, bounded and disabled by configuration.
Message content is untrusted data and cannot trigger tools. See ADR-0022 for the
full boundary and residual mailbox-wide OAuth scope.
