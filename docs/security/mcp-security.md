# MCP security

MCP is a capability boundary, not a plugin shopping list. Foundation keeps all
servers disabled while preserving reviewed metadata and profiles.

## Risk classes

- `READ_ONLY`: retrieval that cannot mutate external/local state.
- `LOW_RISK_WRITE`: writes only inside an approved sandbox or draft namespace.
- `HIGH_RISK_WRITE`: external or production-visible mutation; approval required.
- `DESTRUCTIVE`: deletion, irreversible mutation, unrestricted shell; disabled.

## Curated candidates

| MCP | Purpose | Trust | Credentials | Read/write | Risk |
|---|---|---|---|---|---|
| Docker Catalog Fetch | Retrieve/extract page | Docker-built reference | none | read | `READ_ONLY` with SSRF risk |
| Microsoft Playwright | Browser automation | official + Docker-built | optional site sessions | read/write web | action-dependent, up to `HIGH_RISK_WRITE` |
| Reference Filesystem | Approved workspace | Docker-built reference | mount only | local read/write | `LOW_RISK_WRITE`; path escape is critical |
| GitHub Official | Repository workflows | official GitHub | fine-grained/OAuth | read/write | action-dependent; merge/delete high/destructive |
| Brave Search | Web research | Docker-built connector | API key | read | `READ_ONLY`, privacy/cost risk |
| Sequential Thinking | Planning | reference | none | no external state | not selected; redundant with model reasoning |
| PostgreSQL MCP | Database inspection | no suitable local reviewed candidate selected | scoped DB role | read preferred | disabled pending read-only design |

## Mandatory runtime controls

Every tool call must eventually carry agent identity, task ID, tool/action,
derived risk, approval requirement/result, execution result, and correlation
ID. Credentials are injected per server and never inherited wholesale.

Filesystem mounts must name exact approved directories, default read-only, and
exclude `.git`, `.env`, browser profiles, SSH, and home directories. Browser
sessions must be disposable. Database MCP must use a read-only role and network
path that cannot reach production administration. GitHub tokens must be
fine-grained, repository-scoped, and unable to bypass branch protection.

## Sampling

Hermes supports MCP server-initiated sampling. Disable sampling for every
untrusted server because it can spend model budget and create recursive tool
loops. If enabled later, set model allowlist, token cap, RPM limit, timeout,
tool-round cap, and audit verbosity.

## Enablement gate

Before enabling a server: verify official source and current catalog digest;
review tool list; assign risk per action; scope mounts/credentials/network;
test readiness and one safe read; verify disable path; document result in
engineering journal. Never test destructive tools automatically.

