# Autonomous side-effect security review

Review date: 2026-08-25

Scope: exact-action persistence and approval, Playwright application adapter,
SMTP sender, dashboard review UI, Compose isolation, and CI coverage. This is an
implementation review, not a penetration test of third-party ATS sites.

## Findings

### SE-001 — Broad automatic approval would authorize unknown external actions

- Severity: Critical
- Status: Prevented by design
- Location: `services/control-api/app/policy.py`,
  `services/control-api/app/action_store.py`
- Evidence: application submission and email send derive `high` risk from the
  capability allowlist. The durable approval stores the exact action-context
  digest, and execution rejects a missing or mismatched digest.
- Impact: a global automatic switch could submit altered résumés/answers or send
  arbitrary messages under the user's identity.
- Resolution: preserve per-action approval. Automate discovery, drafting,
  preflight, field resolution, and plan creation around that boundary.

### SE-002 — At-least-once delivery could duplicate a real application

- Severity: High
- Status: Fixed
- Location: `services/control-api/app/action_store.py::begin_side_effect`,
  `services/control-api/app/policy.py`
- Evidence: a unique receipt is committed immediately before the final click or
  SMTP send. Side-effect tasks have one execution attempt. An existing receipt
  rejects a second application even when a distinct exact plan is approved.
- Impact: a crash or manual replan could otherwise apply twice or send duplicate
  mail.
- Resolution: durable fingerprint ledger and explicit `ambiguous` state after
  the irreversible boundary; no automatic retry.

### SE-003 — Browser automation could become an SSRF or credential-exfiltration tool

- Severity: High
- Status: Mitigated for implemented adapters
- Location: `services/control-api/app/application_browser.py`
- Evidence: external URLs require HTTPS/443 and an exact reviewed ATS hostname.
  Every browser request is aborted unless it remains on the initial hostname.
  No browser profile, cookies, downloads, host path, Docker socket, or arbitrary
  credentials are mounted.
- Impact: a caller-controlled URL or cross-origin subresource could probe the
  data network or transmit résumé contents.
- Resolution: exact hostname policy, same-host request routing, disposable
  context, and isolated container. Residual: browser engine vulnerabilities and
  same-host compromised ATS content still require image patching and monitoring.

### SE-004 — Agent could fabricate legal, consent, or employer-specific answers

- Severity: High
- Status: Prevented for implemented adapters
- Location: `services/control-api/app/application_browser.py::resolve_application_fields`
- Evidence: automatic resolution is limited to stored identity, résumé PDF, and
  approved draft material. Unknown required fields are returned to the dashboard
  for explicit answers. CAPTCHA, login, changed forms, and multi-step flows block.
- Impact: invented work authorization, demographic, certification, salary, or
  consent answers can create legal and reputational harm.
- Resolution: no answer inference and no CAPTCHA/login bypass.

### SE-005 — Dashboard credential persisted in browser session storage

- Severity: Medium
- Status: Fixed
- Location: `services/control-api/app/web/app.js`
- Evidence: the bearer token now exists only in JavaScript page memory and is
  cleared on disconnect/reload; `sessionStorage` is absent from shipped assets.
- Impact: a token persisted for the tab session has a longer theft window on a
  shared or compromised browser.
- Resolution: memory-only token plus existing same-origin CSP. Residual: any
  same-origin script compromise can still read it, so public deployment needs
  OIDC/RBAC and secure cookie-based sessions.

### SE-006 — Task input could redirect outbound SMTP

- Severity: High
- Status: Fixed
- Location: `services/control-api/app/settings.py`,
  `services/control-api/app/action_worker.py::_send_email`
- Evidence: host, port, TLS mode, credentials, and sender are fixed deployment
  settings. Task input contains only one validated recipient, subject, and body.
  External SMTP requires TLS; the no-TLS mode is accepted only for the fixed
  internal Mailpit test service.
- Impact: arbitrary SMTP endpoints could exfiltrate mail content or credentials.
- Resolution: configuration-only transport, exact sender binding, TLS validation,
  header-injection validation, and one-recipient messages.

### SE-007 — New browser runtime initially lacked image scan/SBOM coverage

- Severity: Medium
- Status: Fixed in CI configuration; clean-run result pending branch CI
- Location: `.github/workflows/ci.yml`, `.github/dependabot.yml`
- Evidence: CI now builds and separately scans the action-worker image and
  uploads an SPDX JSON SBOM; Dependabot covers its Python lock and Dockerfile.
  A local Trivy 0.74.0 scan found no unsuppressed high/critical issue. Two stale
  PURLs from the base image's third-party SBOM are narrowly suppressed until
  2026-09-25 after merged-filesystem/import checks proved those distributions
  absent; the dependency risk register contains the exact evidence.
- Impact: a vulnerable browser/runtime dependency could enter while only the
  control image was gated.
- Resolution: identical high/critical fixed-vulnerability policy for both
  runtime images. The remote clean-checkout CI result remains the authoritative
  merge evidence.

## Residual production blockers

- The dashboard still uses one bootstrap bearer token and must stay loopback or
  behind an SSH/VPN tunnel until OIDC/RBAC, rate limiting, and step-up approval
  are implemented.
- Real ATS behavior is prepared but not universally verified. Unsupported,
  login-gated, multi-page, CAPTCHA, or changed forms stop for manual handling.
- Real email requires user-owned SMTP/OAuth credentials and provider terms.
- The action container has normal outbound network access. The in-process URL
  policy is strong for current fixed adapters, but a VPS egress proxy/firewall
  would add defense in depth.
- A crash after an external service accepts data can only be classified
  `ambiguous`; the operator must reconcile it before any new action.
