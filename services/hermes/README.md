# Hermes integration boundary

Compose profile `agent` runs official Nous Research image
`nousresearch/hermes-agent:v2026.8.3`, pinned by multi-platform digest. Hermes
state lives in named volume `hermes_data`; no host filesystem or Docker socket
is mounted.

The container receives OmniRoute's internal URL and scoped provider keys from
ignored environment configuration. A networkless one-shot service copies the
reviewed template into the private Hermes volume before every agent start.
After OmniRoute onboarding:

1. Create a scoped OmniRoute inference key from its loopback-only dashboard.
2. Put that key in ignored `.env` as `OMNIROUTE_API_KEY`.
3. Create a dedicated OpenRouter inference key and put it in ignored `.env` as
   `OPENROUTER_API_KEY`.
4. Start the agent profile; it renders `config.example.yaml` automatically.
5. Keep the primary at `free/default`, followed by `openrouter/free`, then the
   internal Ollama fallback. A generic `auto` route is not the primary policy.
6. Verify the primary and provider-health checks with harmless requests.

The intended chain is OmniRoute `free/default`, OpenRouter `openrouter/free`,
then internal `http://ollama:11434/v1` model `qwen3:8b`. The agent profile
supervises the small Ollama daemon but does not load Qwen during startup; the
first final-fallback request loads weights and the idle timeout unloads them.
`-LocalModel` performs an explicit canary only. The non-secret
`HERMES_LOCAL_FALLBACK_KEY` value only satisfies OpenAI-client compatibility;
Ollama does not authenticate it.

`openrouter/free` filters for request capabilities but OpenRouter documents its
final compatible-model choice as random. The career worker therefore keeps a
separate stricter adapter that ranks current free models by benchmark/capability,
checks active ZDR endpoints, and sends no more than one primary plus three
fallbacks. Do not describe the interactive free router itself as benchmark-best.

Approval mode stays manual. MCP stays empty. Terminal, host filesystem, and
external messaging credentials are intentionally not provisioned here.

## Reviewed organic promotion skills

The existing networkless `hermes-config` initializer verifies and seeds eight
small native skills into `/opt/data/skills/hermes-promotion`. They are available
through Hermes's normal skill discovery; no external registry installer, global
Windows package or additional service is needed.

| Skill | Useful output |
|---|---|
| `promotion-brief` | Product claim ledger, audience evidence, constraints and priorities |
| `organic-campaigns` | Distinct campaign concepts, short storyboards and capture lists |
| `community-fit` | Dated community-rule assessment and useful unsent contribution drafts |
| `creator-fit` | Source-grounded creator shortlist and independent-content briefing |
| `content-repurpose` | Rights-aware, channel-specific versions of an original story |
| `landing-review` | Evidence of activation friction and grounded proposed page copy |
| `experiment-design` | One-variable organic pilots, event definitions and matched-window results |
| `promotion-release-review` | Exact-artifact readiness review with unresolved holds and permissions |

These are planning instructions, not messaging or publishing tools. They do not
connect accounts, provision credentials, purchase ads, change commercial offers,
create schedules or authorize a send. An owner mailing pause survives a creative
request or service restart; the trusted control plane still governs execution.
The pack is intended for zero-cash organic work. Virality and conversion gains
remain hypotheses until measured.

The [selection and provenance record](skills/PROVENANCE.md) pins the inspected
upstream sources and license decisions. Selected MIT planning patterns were
adapted into concise original procedures, retaining the notice. The full
marketing collection, paid-tool integrations and broad agent-persona packs were
not installed. The pinned Hermes image stays unchanged.

The standard-library [installer](install-managed-skills.py) checks every file
against [the package manifest](skills/promotion-manifest.json), rejects extra
files, traversal and symlinks, and stages the verified replacement before it
renames the owned category. It preserves all other profile skills and state. If
an owned skill was changed locally, installation refuses rather than overwriting
it; inspect and preserve that work before resolving the difference. A stale
install lock also requires review rather than automatic deletion.

Check package bytes without starting an agent or making a model request in an
already built, isolated test image:

```powershell
docker compose --profile tools run --rm --no-deps test python services/hermes/install-managed-skills.py --source services/hermes/skills/promotion --manifest services/hermes/skills/promotion-manifest.json --check
```

The normal agent-profile initialization seeds the package before a newly started
Hermes service. It is not a live profile installation or model canary merely
because these files exist. After a safe initialization, `hermes skills list`
inside the container can verify discovery, and a separately authorized planning
request can verify useful output. Do not start the sending worker to install or
test skills. A raw restart of an existing container does not rerun Compose's
one-shot initializer.

The Minecraft creator partnership workflow is implemented in the trusted control
plane and existing research/action workers. It supports paid-first or revenue-share
proposals, bounded run grants, reviewed replies, and a single owner email/Discord
handoff. This interactive Hermes runtime does not bypass that path or receive
SMTP/Gmail credentials. See the
[creator workflow guide](../../docs/operations/minecraft-creator-workflow.md).

Dashboard is not published by Compose. Release `v2026.8.3` correctly refuses
non-loopback binding without a registered authentication provider; add a
reviewed override only after configuring password or OAuth authentication.

Upstream source: <https://github.com/NousResearch/hermes-agent/releases/tag/v2026.8.3>
