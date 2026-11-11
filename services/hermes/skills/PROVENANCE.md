# Promotion skill selection — November 11, 2026

The decision is a small organic research/creative/measurement pack inside the
existing Hermes runtime. No Windows package installation, new service, paid
subscription, account integration or bulk-email authority is required.

| Source | Inspected reference and maintenance evidence | License | Decision |
|---|---|---|---|
| [Corey Haines Marketing Skills](https://github.com/coreyhaines31/marketingskills) | `3e729622e3de0c82abdb906190d91f9018045872`; repository non-archived, commit November 11, 2026 02:25:46 UTC | Root `LICENSE`: MIT, copyright 2025 Corey Haines | **Adapt** six planning/analysis procedures into eight small Hermes-native skills. Preserve notice. No entire collection, installer scripts or paid-provider integrations. |
| [Nous Research Hermes Agent](https://github.com/NousResearch/hermes-agent) | Deployed release `v2026.8.3`, tag object `7de39e700d2c329e15d32eb0b96e2f7cdd9fbdb2`, commit `3c27eb6234bf91b8ceee9e9071591b31e9b148cb`; release tagged August 3, 2026. Upstream non-archived with November 11 maintenance; current-main observation `78abaafcccec20a546c94e8734a70e38c08a6a69` | MIT | **Reuse existing runtime** and categorized SKILL.md format. Do not upgrade or infer that current-main features exist in the pinned image. |
| [Agency Agents](https://github.com/msitarzewski/agency-agents) | `8ae6164602c95ca78828b148b9052460ee426885`; non-archived, commit November 9, 2026 00:27:04 UTC | Root `LICENSE`: MIT, copyright 2025 AgentLand Contributors | **Defer** role/persona collection. The existing agent can already plan and delegate; broad role imports add instructions without a demonstrated gap or a bounded native integration. No files copied. |
| [Anthropic Skills](https://github.com/anthropics/skills) | `2c5958ecac7cee2b583967a2c4981d0f4a75c579`; non-archived, commit November 6, 2026 22:32:28 UTC | GitHub repository-level SPDX is absent; no root `LICENSE` file was returned. Individual skills/notices require separate review. | **Defer copying**; no relevant executable addition is needed and package-specific license review was not completed. No files copied. |

## Exact primary sources inspected

- [Hermes pinned skills loader](https://github.com/NousResearch/hermes-agent/blob/3c27eb6234bf91b8ceee9e9071591b31e9b148cb/tools/skills_tool.py)
- [Hermes pinned Dockerfile](https://github.com/NousResearch/hermes-agent/blob/3c27eb6234bf91b8ceee9e9071591b31e9b148cb/Dockerfile)
- [Marketing Skills license](https://github.com/coreyhaines31/marketingskills/blob/3e729622e3de0c82abdb906190d91f9018045872/LICENSE)
- [Marketing plan](https://github.com/coreyhaines31/marketingskills/blob/3e729622e3de0c82abdb906190d91f9018045872/skills/marketing-plan/SKILL.md)
- [Community marketing](https://github.com/coreyhaines31/marketingskills/blob/3e729622e3de0c82abdb906190d91f9018045872/skills/community-marketing/SKILL.md)
- [Creator partnerships](https://github.com/coreyhaines31/marketingskills/blob/3e729622e3de0c82abdb906190d91f9018045872/skills/influencer-marketing/SKILL.md)
- [Experiment design](https://github.com/coreyhaines31/marketingskills/blob/3e729622e3de0c82abdb906190d91f9018045872/skills/ab-testing/SKILL.md)
- [Analytics](https://github.com/coreyhaines31/marketingskills/blob/3e729622e3de0c82abdb906190d91f9018045872/skills/analytics/SKILL.md)
- [Useful free tools](https://github.com/coreyhaines31/marketingskills/blob/3e729622e3de0c82abdb906190d91f9018045872/skills/free-tools/SKILL.md)
- [Agency Agents license](https://github.com/msitarzewski/agency-agents/blob/8ae6164602c95ca78828b148b9052460ee426885/LICENSE)

The implementation uses original concise instructions rather than importing
cross-skill references, schedulers, provider clients or release tooling. Its only
executable addition is a standard-library packaging installer, run without a
network by the existing config initializer. Skill use consumes normal model
tokens; no observed growth, accuracy improvement or completed live installation
is inferred merely from shipping files. Runtime enumeration and a real planning
response are separate verification steps.
