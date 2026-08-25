# MCP catalog evaluation

Snapshot date: **2026-08-11**. Docker MCP Toolkit `v0.42.2`; catalog
`mcp/docker-mcp-catalog:latest` digest
`b388805a250eaff0d5db680c001bf2bb780d7578cb685729c651117ce702cdd9`.
Re-verify because catalog `latest` is mutable even though each selected image is
captured by digest.

Sources: [Docker MCP Catalog](https://docs.docker.com/ai/mcp-catalog-and-toolkit/catalog/),
[Docker MCP Toolkit](https://docs.docker.com/ai/mcp-catalog-and-toolkit/toolkit/),
and linked upstream repositories.

## Evaluated

| Candidate | Decision | Distribution | Auth/cost | Security/maintenance reason |
|---|---|---|---|---|
| Playwright (`playwright`) | Selected, disabled | `mcp/playwright@sha256:097d…` | Site credentials only when needed; no MCP fee | Official Microsoft server, Docker-built catalog image; powerful form/session actions require per-action risk |
| Fetch (`fetch`) | Selected, disabled | `mcp/fetch@sha256:d990…` | None | Reference server, one read tool; SSRF/private-network controls still required |
| Filesystem (`filesystem`) | Selected, disabled | `mcp/filesystem@sha256:35fc…` | Explicit mount | Reference server with configurable paths; never mount host home or project secrets |
| GitHub Official (`github-official`) | Selected, disabled | `ghcr.io/github/github-mcp-server@sha256:2afb…` | Fine-grained token/OAuth; GitHub plan limits apply | Official maintained GitHub server; archived `github` catalog entry rejected |
| Brave Search (`brave`) | Selected, disabled | `mcp/brave-search@sha256:b893…` | API key; provider rate/cost terms apply | More attributable/maintained than community DuckDuckGo connector; queries leave host |
| ast-grep (`ast-grep`) | Selected, disabled | `mcp/ast-grep@sha256:5fc3…` | None | Structural code inspection useful in sandbox; write/rewrite tools must remain policy-gated if exposed |
| PostgreSQL | Rejected for now | Catalog search exposed Prisma remote, not a reviewed local read-only server | Varies | General agent must not receive application DB credentials; design dedicated read-only role/view first |
| Sequential Thinking | Rejected | `mcp/sequentialthinking@sha256:cd31…` | None | Adds no external capability and may expose reasoning traces; native planning is sufficient |
| DuckDuckGo community | Rejected | `mcp/duckduckgo@sha256:d714…` | None | Catalog explicitly says community-maintained and unaffiliated; reliability/support unclear |
| Generic shell MCP | Rejected | none | N/A | Unrestricted command execution conflicts with least privilege; coding uses isolated worker later |

## Why nothing is enabled

Hermes can launch stdio MCP servers or connect over HTTP, while Docker MCP
Toolkit is a host-managed beta gateway. Bridging them from Compose either
requires host-specific state or Docker socket access. Foundation refuses that
privilege expansion. Next implementation should render a curated Docker MCP
profile, start gateway outside Hermes, expose only reviewed transport, and
validate one safe read per server.

The application adapter added in August 2026 uses Playwright as a dedicated,
fixed-purpose worker, not the generic Playwright MCP server. That lets the
control plane enforce exact ATS hosts, fields, form signature, approval digest,
and durable side-effect receipt in application code. The broader MCP candidate
remains disabled because it would expose unrelated navigation and form powers.

## Validation commands used

```text
docker mcp version
docker mcp catalog ls
docker mcp catalog server ls mcp/docker-mcp-catalog:latest --filter name=<candidate>
```

No server was started and no destructive operation was tested.
