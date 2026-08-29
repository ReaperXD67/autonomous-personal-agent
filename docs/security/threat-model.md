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
| Résumé disclosure | Identity/privacy loss | Raw résumé stays in PostgreSQL; API exposes only presence/length; public sources/tasks/audits do not receive it. Hosted drafting is off by default, uses no-training/ZDR filters, and falls back locally rather than weakening privacy |
| Paid-model route drift | Unexpected credit spend | Runtime accepts only exact `:free` live-catalog IDs with zero prompt/completion/request prices, checks the actual selected model and zero returned cost, and keeps an atomic PostgreSQL daily cap |
| Shared free-pool double consumption | Premature quota exhaustion and misleading local usage | OpenRouter is assigned only to the direct career adapter; Hermes uses a separate OmniRoute pool; agent doctor warns if OpenRouter appears in both paths |
| OpenRouter key theft | Provider-account abuse | Dedicated inference key only in ignored `.env` and the career worker; never accept a management key; no key/header/body logging; use a user-configured key limit and rotate after exposure |
| Accidental email send | Privacy/reputation damage | Exact sender/recipient/subject/body approval, fixed TLS SMTP configuration, one recipient, durable receipt |
| Unsolicited creator outreach | Privacy/legal/reputation damage | Official metadata discovery has no email; operator records public contact provenance/basis; each send exact-approved; opt-out/bounce suppresses durably |
| Stale creator approval after opt-out | Unwanted follow-up | Action worker locks and revalidates address, authorization, suppression, and reply state immediately before SMTP receipt |
| Unsafe adaptive outreach | Manipulative spam or policy bypass | Minimum samples/effect threshold; choice limited to two fixed draft variants; 20% exploration; no autonomous send, spend, policy, code, or contact mutation |
| GitHub destructive operation | Code/repo loss | Fine-grained token, repo allowlist, destructive tools disabled, protected branches |
| Secret enters logs/audit | Persistent exposure | Structured allowlisted metadata, no payload/body logging, redaction tests; inference audit omits prompts/completions and records route metrics only |
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
