# Threat model

## Assets

Credentials, personal memory, email/job data, browser sessions, source code,
task/audit integrity, provider budget, VPS availability, and external reputation.

## Trust boundaries

User interface → control API; control API → data stores; queue → worker;
Hermes → model router; model output → tool policy; browser/email/web content →
agent; MCP gateway → external server; VPS → internet.

## Threats and mitigations

| Threat | Impact | Current/future mitigation |
|---|---|---|
| Prompt injection in webpage/email | Tool misuse, exfiltration | Treat content as untrusted data; no direct tool grants; approval for side effects; future content labels and egress policy |
| Malicious webpage | Browser exploit/session theft | Future disposable browser container, no personal profile mount, domain/download policy, patched image |
| Credential leakage | Account takeover | Scoped secrets, no body/header logs, filtered MCP env, secret scanning, rotation runbook |
| Tool abuse/confused deputy | Unauthorized action | Agent-specific allowlists, derived risk, approval gate, audit/correlation IDs |
| Arbitrary code execution | Host/data compromise | No shell MCP by default, non-root read-only workers, no Docker socket, future sandbox per coding task |
| Malicious MCP server | Exfiltration/tool spoofing | Curated signed catalog, digest pin, disabled default, per-server secrets, sampling disabled for untrusted tools |
| SSRF | Internal service/metadata access | Future URL policy, DNS/IP validation, egress proxy; fetch/browser not enabled now |
| Unauthorized job application | Legal/reputation damage | Submission capability high-risk and approval-gated; not implemented |
| Accidental email send | Privacy/reputation damage | Separate draft/send permissions; send high-risk; not implemented |
| GitHub destructive operation | Code/repo loss | Fine-grained token, repo allowlist, destructive tools disabled, protected branches |
| Secret enters logs/audit | Persistent exposure | Structured allowlisted metadata, no payload/body logging, redaction tests |
| Queue replay/duplication | Repeated side effect | DB state transition rejects stale entries; future side-effect idempotency ledger |
| Approval forgery | High-impact execution | Authenticated durable decision now; future approver identity, MFA, signed decision/context hash |
| Supply-chain compromise | Malicious image/dependency | Release+digest pins, lockfile; future SBOM/signature verification and scanning |
| Unsafe autonomous self-improvement | Policy bypass | Skills/config writes require approval, immutable policy ownership; not enabled |

## Abuse cases requiring explicit denial

Autonomous purchases/transfers, mass outreach, credential harvesting, public
publishing, repository deletion, data deletion, arbitrary production shell, and
approval-policy modification by the same agent executing a task.

## Residual risk

Bootstrap bearer token is service-wide; image digests ensure immutability but
not upstream trust; audit storage shares database role with application;
worker crash recovery is incomplete. These prevent production classification.

