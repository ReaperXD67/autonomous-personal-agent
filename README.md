<div align="center">

![Autonomous Personal Agent — animated project overview](./docs/assets/readme/autonomous-personal-agent-hero.svg)

</div>

[![CI](https://github.com/ReaperXD67/autonomous-personal-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/ReaperXD67/autonomous-personal-agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Status: foundation](https://img.shields.io/badge/status-foundation-16a085.svg)](#implemented-now)

**A control plane for useful autonomy: durable work, explicit approvals, and an audit trail by default.**

This is a security-first, self-hosted foundation for an autonomous personal agent. This
repository establishes durable task state, approval gates, audit events,
containerized workers, persistent memory storage, model-routing boundaries,
and a curated MCP policy layer before broad autonomy is enabled.

> [!IMPORTANT]
> **Foundation status:** core infrastructure works locally. Email, job
> applications, Telegram, browser automation, coding agents, and unrestricted
> MCP access are planned—not implemented.

## Why this exists

Personal agents can read hostile content and invoke powerful tools. Building
features first and controls later creates an unsafe system. This project starts
with explicit trust boundaries, least privilege, durable state, observability,
and human approval for high-impact actions.

## Implemented now

| Capability | Status | Notes |
|---|---|---|
| Container-first local stack | Implemented | Docker Compose; no project Python, Node, Redis, or PostgreSQL install on Windows |
| Control API | Implemented | Bearer-authenticated task submission, status, metrics, approval decisions |
| Dispatcher + worker | Implemented | Transactional outbox, owned leases, heartbeats, cancellation, delayed retries, dead letters, deterministic foundation handlers |
| Approval policy | Implemented | High-risk and destructive tasks enter `pending_approval` |
| Durable task/audit state | Implemented | PostgreSQL 17 + pgvector; state, audit, and outbox writes share transactions |
| Queue/cache | Implemented | Password-protected Redis 8 with AOF persistence |
| Hermes + OmniRoute | Verified locally | Optional pinned profile; 79 routes, `free/default`, and Hermes one-shot inference passed |
| Local inference | Verified | Pinned Ollama + Qwen3 8B returned `LOCAL_MODEL_OK` on the observed 8 GB NVIDIA GPU |
| MCP policy architecture | Implemented | Curated registry, agent profiles, risk classes; no MCP server enabled by default |
| Supply-chain CI | Implemented | Required dependency review, Trivy repository/image gates, immutable actions, SPDX runtime SBOM |
| Full autonomous features | Planned | See [roadmap](docs/roadmap.md) |

## Architecture

```mermaid
flowchart LR
    U["User / future Telegram / web UI"] --> API["Control API"]
    API --> POLICY["Risk policy + approval gate"]
    POLICY -->|"approved / low risk"| OB["Transactional outbox"]
    POLICY -->|"high impact"| A["Pending human approval"]
    OB --> D["Outbox dispatcher"]
    D --> Q["Redis ready queue"]
    Q --> W["Worker"]
    API --> PG[("PostgreSQL + pgvector")]
    W --> PG
    W --> AUDIT["Audit events"]
    AUDIT --> PG

    H["Hermes (optional)"] --> O["OmniRoute (optional)"]
    O --> LLM["Configured LLM providers"]
    H -. "future policy adapter" .-> POLICY
    H -. "reviewed profiles only" .-> MCP["MCP gateway / tools"]
```

Core stack runs without an LLM key. Optional `agent` profile is isolated from
PostgreSQL and receives only model-network access plus normal outbound access.

## Quick start: Windows + Docker Desktop

Prerequisites: Docker Desktop with Linux containers and Compose v2. PowerShell
is already part of Windows.

```powershell
git clone https://github.com/ReaperXD67/autonomous-personal-agent.git
cd autonomous-personal-agent
./scripts/init-env.ps1
./scripts/up.ps1
./scripts/health.ps1
./scripts/smoke.ps1
./scripts/doctor.ps1 -Agent
```

Open health endpoint at `http://127.0.0.1:8080/health/ready`. PostgreSQL and
Redis have no published host ports.

Stop cleanly:

```powershell
./scripts/down.ps1
```

## Useful commands

| PowerShell | Make | Purpose |
|---|---|---|
| `./scripts/init-env.ps1` | `make init` | Create ignored `.env` with random local secrets |
| `./scripts/up.ps1` | `make up` | Build and start core stack |
| `./scripts/health.ps1` | `make health` | Check container and dependency readiness |
| `./scripts/smoke.ps1` | `make smoke` | Verify safe path and approval-gated path |
| `./scripts/recovery-smoke.ps1` | `make recovery-smoke` | Verify expired leases retry and exhaust safely |
| `./scripts/lifecycle-smoke.ps1` | `make lifecycle-smoke` | Verify queued/running cancellation and dead-letter inspection |
| `./scripts/agent-smoke.ps1` | `make agent-smoke` | Verify configured OmniRoute model inference |
| `./scripts/test.ps1` | `make test` | Run lint and tests in isolated container |
| `./scripts/logs.ps1` | `make logs` | Follow bounded Docker logs |
| `./scripts/backup.ps1` | `make backup` | Create ignored PostgreSQL custom dump + SHA-256 |
| `./scripts/restore-drill.ps1` | `make restore-drill` | Restore into a random disposable database and validate it |
| `./scripts/down.ps1` | `make down` | Stop stack without deleting volumes |
| `./scripts/doctor.ps1` | `make doctor` | Diagnose Docker, WSL, configuration, services, GPU, and agent readiness |
| `./scripts/readiness.ps1` | `make readiness` | Run the complete core, restore, local/routed-model, and Hermes readiness gate |

## Optional Hermes + OmniRoute profile

```powershell
./scripts/up.ps1 -Agent
```

This starts release-pinned upstream images and binds dashboards to loopback:

- OmniRoute: `http://127.0.0.1:20128`

Hermes dashboard is intentionally not published. Current upstream requires an
auth provider for any non-loopback container bind; configure that first, then
add a reviewed authenticated dashboard override. Do not weaken this guard.

This workstation is onboarded with a scoped inference-only key in ignored
`.env`; `free/default` and Hermes one-shot inference pass. A fresh clone still
requires local administrator onboarding and a new scoped key. Use
[services/hermes/config.example.yaml](services/hermes/config.example.yaml) as the
reviewed boundary and never treat image health alone as inference readiness.

## Complete test-readiness gate

After first boot, verify the complete configured workstation with one command:

```powershell
./scripts/readiness.ps1
```

It runs the full lifecycle suite, disposable database restore, environment
doctor, OmniRoute route, local GPU model, and Hermes one-shot request. A
secret-free machine-readable result is written to ignored
`runtime/readiness/latest.json`. See the [test-readiness guide](docs/operations/test-readiness.md).

## Completely local, no-token-cost inference

The observed RTX 4070 Laptop GPU has 8 GB VRAM. Current Nemotron 3 agentic
checkpoints are too large for it, so the local fallback is Qwen3 8B Q4:

```powershell
./scripts/local-model.ps1
```

This starts a digest-pinned Ollama container, downloads the approximately 5.2 GB
model, requires the exact harmless response `LOCAL_MODEL_OK`, and verifies GPU
placement. This workstation passed that check on 2026-08-15. It is private and
has no token bill, but its 8K configured context and model quality are below
strong hosted models.
Use OmniRoute free providers for Nemotron or larger coding models when available.
See the [free-stack assessment](docs/research/free-agent-stack-2026-08.md) and
[remaining manual setup](docs/operations/manual-setup.md).

## Security defaults

- Secrets are generated locally and ignored by Git.
- Published ports bind to `127.0.0.1` only.
- PostgreSQL and Redis live on an internal Docker network.
- Application containers run as non-root, read-only, without Linux capabilities.
- High-risk and destructive tasks require an explicit approval record.
- Audit metadata stores keys and outcomes, not raw secrets or request bodies.
- Hermes receives no Docker socket or host filesystem mount.
- MCP registry starts disabled; each server needs review and scoped credentials.
- Required CI rejects new fixed high/critical dependency or runtime-image
  vulnerabilities and repository secret/misconfiguration findings.

This is not safe for public internet exposure without TLS, authenticated reverse
proxy, rate limiting, secret management, and VPS hardening described in the
[deployment guide](docs/operations/deployment.md).

## Data and persistence

| Data | Store | Durability |
|---|---|---|
| Tasks, approvals, audits | PostgreSQL | Authoritative, backed up |
| Long-term memory and embeddings | PostgreSQL + pgvector | Authoritative, backed up |
| Ready queue, cache, transient state | Redis | Recoverable; AOF enabled, not authoritative |
| Hermes state | `hermes_data` volume | Optional; back up after onboarding |
| OmniRoute configuration | `omniroute_data` volume | Optional; contains credentials, encrypt backups |
| Local Ollama models | `ollama_data` volume | Optional; reproducible downloads, potentially large |

Named volumes survive `docker compose down`. Never run `down --volumes` unless
intentional data deletion is acceptable and backups were verified.

## Repository map

```text
config/postgres/init/     versioned database bootstrap schema
docs/                     architecture, ADRs, operations, security, roadmap
engineering/              factual build and validation journal
AGENTS.md                  durable rules for future coding agents
mcp/                      curated tool registry, profiles, permission policy
scripts/                  Windows-first lifecycle and verification commands
services/control-api/     control API, outbox dispatcher, and worker image
services/hermes/          verified upstream integration boundary
services/omniroute/       verified upstream integration boundary
tests/                    repository security/Compose contracts
```

## Documentation

- [Architecture overview](docs/architecture/overview.md)
- [Component boundaries](docs/architecture/components.md)
- [Networking](docs/architecture/networking.md)
- [Task and data flows](docs/architecture/data-flow.md)
- [Security baseline](docs/security/security-baseline.md)
- [Threat model](docs/security/threat-model.md)
- [Dependency risk register](docs/security/dependency-risk-register.md)
- [MCP security](docs/security/mcp-security.md)
- [Local operations](docs/operations/local-development.md)
- [Manual setup remaining](docs/operations/manual-setup.md)
- [Free agent/model research](docs/research/free-agent-stack-2026-08.md)
- [Engineering journal](engineering/ENGINEERING_JOURNAL.md)
- [System evolution](engineering/SYSTEM_EVOLUTION.md)
- [Experiment log](engineering/EXPERIMENT_LOG.md)

## License

[MIT](LICENSE)
