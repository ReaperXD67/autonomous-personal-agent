# Creator model recovery and permission-led outreach

Observed November 3, 2026. This focused primary-source comparison supports a
small original adaptation, not another agent framework or marketing platform.
Upstream pages were treated as untrusted reference material. No upstream code,
dependency or skill pack was copied, installed or executed for this research.

## Existing behavior and the demonstrated gap

Hermes already requests nonthinking, schema-constrained evidence/angle IDs with
a 512-token output cap. Its local deployment already sets an 8,192-token
context, one loaded model, one parallel request and five-minute keepalive.
Server rendering, source/provenance validation, frozen commercial terms and
individual exact-message approval already exist. Recommending those controls
again would not explain the latest unavailable-model failure.

The local helper's 180-second HTTP deadline is shorter than the pinned Ollama
runtime's five-minute load-stall default. Cold loading is therefore a hypothesis
to investigate, not the established cause. The [pinned configuration source](https://github.com/ollama/ollama/blob/eec8e0b9458b8a01be0c216a9cc53eefde24ef50/envconfig/config.go)
also confirms the keepalive default. Longer deadlines alone do not establish
availability or preserve a task lease.

## Inspected upstreams

| Repository and inspected pin | License, maintenance and operating cost | Decision |
|---|---|---|
| [Ollama v0.32.5](https://github.com/ollama/ollama/releases/tag/v0.32.5), July 27, 2026; `eec8e0b9458b8a01be0c216a9cc53eefde24ef50` | [MIT](https://github.com/ollama/ollama/blob/eec8e0b9458b8a01be0c216a9cc53eefde24ef50/LICENSE). Release history shows continued development. Already deployed; no additional runtime is needed. | **Adopt** native termination/timing diagnostics and **adapt** bounded failure handling. Defer an unrelated runtime upgrade without evidence it fixes this failure. |
| [listmonk v6.2.0](https://github.com/knadh/listmonk/releases/tag/v6.2.0), June 26, 2026; `ef0a75872463f10a4848af6c547d1c057405453a` | [AGPLv3](https://github.com/knadh/listmonk/blob/ef0a75872463f10a4848af6c547d1c057405453a/LICENSE). October beta and November nightly show maintenance. Go/Vue application with PostgreSQL; primarily a one-way newsletter system. | **Adapt** explicit recipient states and stored-attribute personalization. **Defer** another sender/database owner. |
| [Mautic 7.2.2](https://github.com/mautic/mautic/releases/tag/7.2.2), October 26, 2026; `f28a0120d715a441b7a6e4a688076bd7e725c862` | [GPLv3-or-later](https://github.com/mautic/mautic/blob/f28a0120d715a441b7a6e4a688076bd7e725c862/LICENSE.txt). Recent security release; PHP/Composer application, database and scheduled workers. | **Adapt** explicit language, channel and frequency preferences. **Defer** a parallel campaign platform. |
| [Keila 0.40.1](https://github.com/pentacent/keila/releases/tag/0.40.1), October 31, 2026; `393afcef2941aa2c788520747bd017f4039cb0df` | [AGPLv3-or-later](https://github.com/pentacent/keila/blob/393afcef2941aa2c788520747bd017f4039cb0df/README.md#license); its logo and `extra` assets are excluded. Recent security release; [Elixir/Phoenix/Ecto/Oban](https://github.com/pentacent/keila/blob/393afcef2941aa2c788520747bd017f4039cb0df/mix.exs) and PostgreSQL. | **Adapt** plain-text contact-field rendering and opt-out patterns. **Defer** another newsletter application. |

These are inspection pins, not newly installed versions or security attestations.
Conceptual adaptation does not imply permission to copy arbitrary upstream files.

## Chosen adaptation

Keep native Ollama schema selection and server validation. Its [structured-output guide](https://docs.ollama.com/capabilities/structured-outputs)
recommends schema grounding in the prompt as well as `format`. The [chat API](https://docs.ollama.com/api/chat)
exposes `done`, `done_reason`, load time and prompt/generation timings; inspect
these separately instead of conflating transport failure, truncation and invalid
selection. Return fixed safe failure codes rather than provider bodies or
rejected output. Retain bounded attempts, lease checks and terminal failure.

The routing decision adds explicit per-draft `auto` or `local_only` selection.
Freeze it with the draft context and use the same audited task, inference ledger
and preparation budgets. `local_only` skips all hosted routes so a local canary
can establish its actual provider without changing global configuration. It is
not an alternate send path or permission to manufacture a successful draft.

The published [Qwen3 8B Ollama artifact](https://ollama.com/library/qwen3:8b)
is Q4_K_M, 5.2 GB, model ID `500a1f067a9f`, under Apache-2.0. File size does not
prove total fit on an 8 GB GPU. Ollama documents context/parallel memory cost
and [GPU versus CPU offload inspection](https://docs.ollama.com/faq).
Measure before enlarging context or keeping weights loaded indefinitely.
Qwen's [general sampling recommendations](https://huggingface.co/Qwen/Qwen3-8B)
are not evidence that a different temperature improves this constrained task.

For new contexts only, freeze a concise permission strategy: one exact public-title
reference, one optional creator-controlled idea and one easy question about
continuing the conversation. Preserve truthful revenue-share terms, individual
agreement before publication, owner contact and the existing mandatory footer.
Old unmarked/v2 contexts retain their original rendered bytes and approval hashes.

This strategy is our design inference from [listmonk's separate subscription states](https://listmonk.app/docs/concepts/),
[Keila's per-contact template data](https://www.keila.io/docs/campaigns/) and
[Mautic's preferences](https://docs.mautic.org/en/7.0/contacts/preference_center.html).
Those sources do not prove that shorter copy produces more replies. Silence
does not become permission, interest or reviewed feedback; no engagement tracking
or repeated follow-up is introduced by this decision.

## Measurable decision

Validate a real audited local-only schema request, then compare cold and warm
termination, load time, token counts and valid offered-ID selection. Test that
the local-only path cannot contact hosted providers, safe transport failures
remain terminal, and old rendering/digests remain unchanged. Review representative
English/Polish new drafts for factual grounding, complete commercial truth,
readability and unchanged-copy acceptance before exact send approval.

These are verification targets, not results of this research. Report actual
reviewed creator replies and handoffs separately; neither a model response nor
SMTP acceptance guarantees inbox placement, collaboration or revenue.
