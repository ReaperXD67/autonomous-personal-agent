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
| Prompt injection in job/webpage/email content | Tool misuse, exfiltration | Job text is treated as untrusted data; career worker has fixed handlers/hosts; local draft prompt says ignore embedded instructions; no submit tool |
| Malicious webpage | Browser exploit/session theft | Disposable non-root browser container, no personal profile/download/host mount, exact ATS and same-host request policy, patched image |
| Credential leakage | Account takeover | Scoped secrets, no body/header logs, filtered MCP env, secret scanning, rotation runbook |
| Tool abuse/confused deputy | Unauthorized action | Agent-specific allowlists, derived risk, approval gate, audit/correlation IDs |
| Arbitrary code execution | Host/data compromise | No shell MCP by default, non-root read-only workers, no Docker socket, future sandbox per coding task |
| Malicious MCP server | Exfiltration/tool spoofing | Curated signed catalog, digest pin, disabled default, per-server secrets, sampling disabled for untrusted tools |
| SSRF | Internal service/metadata access | Career fetches use fixed HTTPS hosts, validated redirects/slugs, size/time bounds; future generic browser still requires DNS/IP policy and egress proxy |
| Unauthorized job application | Legal/reputation damage | Exact expiring approval digest, explicit unknown answers, form/resume/draft revalidation, one final click, durable receipt; unsupported forms stop |
| Résumé disclosure | Identity/privacy loss | Raw résumé stays in PostgreSQL and internal local-model context; API exposes only presence/length; public sources/tasks/audits do not receive it |
| Accidental email send | Privacy/reputation damage | Exact sender/recipient/subject/body approval, fixed TLS SMTP configuration, one recipient, durable receipt |
| GitHub destructive operation | Code/repo loss | Fine-grained token, repo allowlist, destructive tools disabled, protected branches |
| Secret enters logs/audit | Persistent exposure | Structured allowlisted metadata, no payload/body logging, redaction tests |
| Queue replay/duplication | Repeated side effect | DB state rejects stale entries; unique pre-click/pre-send receipt blocks retry and duplicate application |
| Approval forgery | High-impact execution | Authenticated durable decision bound to exact context hash; future per-user identity, MFA, and signed approvals |
| Supply-chain compromise | Malicious image/dependency | Release+digest pins, lockfile; future SBOM/signature verification and scanning |
| Unsafe autonomous self-improvement | Policy bypass | Skills/config writes require approval, immutable policy ownership; not enabled |

## Abuse cases requiring explicit denial

Autonomous purchases/transfers, mass outreach, credential harvesting, public
publishing, repository deletion, data deletion, arbitrary production shell, and
approval-policy modification by the same agent executing a task.

## Residual risk

Bootstrap bearer token is service-wide; image digests ensure immutability but
not upstream trust; audit storage shares database role with application; public
job data may be incomplete or malicious; real ATS compatibility is partial; and
post-handoff ambiguity cannot be eliminated. These prevent public-production
classification.
