# Grounded creator drafting: constrain the decision, render the facts

Reviewed November 2, 2026 against Hermes `297ae97`. This focused primary-source
comparison addresses the November 1 launch's copy failures. It informs the
original implementation below, not an installed framework or a measured
improvement in creator response. Earlier campaign/orchestration comparisons
remain in [the systems note](creator-outreach-systems-2026-11.md).

## The demonstrated gap

The private launch evidence records twenty-four drafting tasks: nineteen
returned local Qwen copy and five failed without a usable draft. Final review
retained one exact AI draft and used twenty-three reviewed manual replacements.
Some intermediate review files were captured while generation was queued;
their rejection reasons are not a clean semantic-failure rate. Recipient
identities, addresses and exact messages remain private and are not reproduced.

Review found unsupported verification/curation claims, assumed server modes or
features, descriptions of unseen video contents, poor Polish/English phrasing,
and inferred audience preferences. Several empty editorial finding lists
accompanied unsuitable copy. These are product-accuracy and relevance failures,
not merely malformed JSON. `creator_drafting.py` already supplies a Pydantic
JSON schema to local Ollama, validates returned copy and allows one separately
accounted local correction. Installing a validation wrapper alone would largely
repeat existing machinery.

## Upstream comparison and provenance

All links were inspected as public source material. Release commits below are
observation pins, not adopted package versions; their dates do not assert that
they are each repository's latest default-branch commit. Release pages supply
additional maintenance evidence. No upstream code, models, skills or packages
were downloaded for execution, installed or copied into Hermes.

| Project and inspected provenance | Relevant pattern and dependency cost | Decision |
|---|---|---|
| [Outlines 1.3.3](https://github.com/dottxt-ai/outlines/releases/tag/1.3.3), commit [`3d251f8d758a01cfee4ddc99646886845dbd8c6d`](https://github.com/dottxt-ai/outlines/commit/3d251f8d758a01cfee4ddc99646886845dbd8c6d), authored August 2, 2026; release August 6. [Apache-2.0](https://github.com/dottxt-ai/outlines/blob/3d251f8d758a01cfee4ddc99646886845dbd8c6d/LICENSE). | Its pinned [README](https://github.com/dottxt-ai/outlines/blob/3d251f8d758a01cfee4ddc99646886845dbd8c6d/README.md) demonstrates classification with finite `Literal` choices. The [manifest](https://github.com/dottxt-ai/outlines/blob/3d251f8d758a01cfee4ddc99646886845dbd8c6d/pyproject.toml) adds `outlines_core`, JSON-schema/template/cache packages and optional backend integrations. | **Adapt the finite-choice pattern**, using existing Pydantic/Ollama. Defer the runtime: a grammar constraining arbitrary prose still cannot establish product truth. |
| [Instructor 1.17.0](https://github.com/567-labs/instructor/releases/tag/v1.17.0), commit [`f539bf2bf43ef4d1cb4e2a405751d6a8815ce05f`](https://github.com/567-labs/instructor/commit/f539bf2bf43ef4d1cb4e2a405751d6a8815ce05f), committed September 9, 2026 UTC. [MIT](https://github.com/567-labs/instructor/blob/f539bf2bf43ef4d1cb4e2a405751d6a8815ce05f/LICENSE). | Pydantic validation/retries overlap Hermes. Its [manifest](https://github.com/567-labs/instructor/blob/f539bf2bf43ef4d1cb4e2a405751d6a8815ce05f/pyproject.toml) adds provider, retry, CLI, HTTP and template dependencies. [Citation documentation](https://python.useinstructor.com/concepts/citation/) explicitly distinguishes checking source quotes from validating the extracted factual assertions. | **Adapt source membership validation**, without fuzzy replacement of the authoritative title. Defer the runtime and model-based validators; they add calls without proving the rejected capabilities exist. |
| [Guidance 0.3.2](https://github.com/guidance-ai/guidance/releases/tag/0.3.2), commit [`172f1d4bf541ff5b5722d76ecb31cbc9eb075ab3`](https://github.com/guidance-ai/guidance/commit/172f1d4bf541ff5b5722d76ecb31cbc9eb075ab3), committed March 18, 2026. [MIT](https://github.com/guidance-ai/guidance/blob/172f1d4bf541ff5b5722d76ecb31cbc9eb075ab3/LICENSE.md). | Its pinned [README](https://github.com/guidance-ai/guidance/blob/172f1d4bf541ff5b5722d76ecb31cbc9eb075ab3/README.md) interleaves authored text with constrained selection/generation. Its [manifest](https://github.com/guidance-ai/guidance/blob/172f1d4bf541ff5b5722d76ecb31cbc9eb075ab3/pyproject.toml) includes NumPy, `guidance-stitch`, `llguidance` and optional model backends. This release is older than the others; no recent-release claim is made. | **Adapt the division between authored wording and model choice.** Defer a second inference integration: Hermes already has the necessary structured endpoint. |
| [Pydantic AI 2.64.0](https://github.com/pydantic/pydantic-ai/releases/tag/v2.64.0), commit [`cde1d10f88ce6d0ab4743e226d51a9ac65810f50`](https://github.com/pydantic/pydantic-ai/commit/cde1d10f88ce6d0ab4743e226d51a9ac65810f50), committed October 30, 2026 UTC. [MIT](https://github.com/pydantic/pydantic-ai/blob/cde1d10f88ce6d0ab4743e226d51a9ac65810f50/LICENSE). | Pinned [output documentation](https://github.com/pydantic/pydantic-ai/blob/cde1d10f88ce6d0ab4743e226d51a9ac65810f50/docs/output.md) separates prompted/native/tool output and application validators with bounded retries. Its [slim manifest](https://github.com/pydantic/pydantic-ai/blob/cde1d10f88ce6d0ab4743e226d51a9ac65810f50/pydantic_ai_slim/pyproject.toml) still adds a graph runtime, HTTP/async, telemetry and pricing packages. | **Adapt explicit validation against run context.** Defer the framework: PostgreSQL leases, inference accounting, policy and approval already belong to Hermes. |

[Ollama's structured-output documentation](https://docs.ollama.com/capabilities/structured-outputs)
supports the existing `format=model_json_schema()` and subsequent Pydantic
validation. The missing constraint is what the output may assert, rather than
whether its keys have the right shape. This is an inference from the local
failures and implementation, not an upstream benchmark of Hermes.

## Implemented small adaptation

1. **Freeze a versioned drafting contract with the evidence.** New v2 contexts
   contain server-authored candidate IDs and eligibility notes alongside the
   existing language, title/URL and observed reach strategy. Markerless legacy
   contexts must retain their present parser and rendering; never rewrite old
   model contexts, complete emails or reviewed digests.
2. **Ask the model to select, not invent facts.** Return only offered evidence
   and angle IDs, with strict types and no extra fields. Validate membership and
   the evidence/angle pairing against the frozen context on the server, even
   when native schema enforcement is available. A supplied ID is not evidence
   unless the server offered it. A rationale needed for the UI can be derived
   from the selected candidate's authored reason instead of generated prose.
3. **Render the selected proposal in authored English/Polish.** Quote the exact
   recorded title once with its source link, then propose a separate optional
   creator-led episode. Use wording such as “Your public title … gave me an idea
   for a separate episode” rather than asserting what an unseen video shows.
   The title establishes only its own wording, not a review, audience preference,
   channel-wide format or a recent upload. Preserve proper names and title text
   as evidence instead of inventing a translation.
4. **Make specificity conditional on real prerequisites.** A build-related
   title can suggest a creator-chosen starter-build challenge if the selected
   server's rules permit it; a comparison title can suggest an independent
   first-session verdict. A mod, named SMP, edition, reward, automation mechanic
   or security theme must not become an assertion that the product supplies it.
   Generic first-session exploration is preferable when metadata gives no safe
   narrower connection. Do not require a positive verdict or tell the creator
   to avoid assessing quality or safety.
5. **Keep the deterministic commercial envelope and authority.** The operator's
   product/offer text is still reviewed input. Percentage, weeks, earning basis,
   attribution and payout remain individually agreed before publication, with
   no guaranteed fixed payment. Keep the standard source/privacy/opt-out footer,
   context rechecks and exact individual approval. Selection cannot authorize
   contact, change recipients, negotiate, alter a budget or send a message.
6. **Expose failure honestly.** A selector outside the offered set fails with a
   fixed diagnostic rather than silently turning into approved prose. Invalid
   output and unavailable response have distinct errors; a template or manual
   alternative remains an explicit separate choice. Context changes, expired
   leases and cancellation still stop work.

The observed implementation uses `creator-grounded-plan-v2`, strict ID-only
plans, authored rendering and source/context/campaign provenance in the existing
draft table. Stored-copy validation rederives the entire copy before acceptance;
the old parser remains for legacy contexts. An audited preparation-only parent
can also queue up to five child drafts within the same shared rolling allowance.
It introduces no framework dependency, service, schema migration or sending
authority. [ADR-0030](../decisions/ADR-0030-grounded-creator-plans-and-draft-batches.md)
records that boundary. Test and live measurements belong in
[Experiment 39](../../engineering/EXPERIMENT_LOG.md#experiment-39--grounded-creator-plans-and-preparation-batches-2026-11-02)
and the engineering journal, rather than being inferred from source inspection.

This trades unconstrained prose variation for a smaller factual surface and
more dependable language. It is an original Hermes design informed by the
linked patterns, not copied upstream implementation. It can reduce repeated
manual correction of the observed classes by construction; whether operators
prefer the resulting proposals still needs measurement.

## Why a free-copy critic is deferred

[Self-Refine](https://arxiv.org/abs/2303.17651) describes iterative feedback and
revision by a model. Such a pass may help wording, but it supplies no new evidence
that a named server, supported mode or verification feature exists. Instructor's
[semantic-validation documentation](https://python.useinstructor.com/concepts/validation/)
also notes the extra model cost and latency. These sources do not establish a
creator-email acceptance rate. A critic can later be compared on a private,
reviewed holdout; it should remain an advisory bounded call rather than an
authority that certifies its own prose or approves sends.

## Evidence required before claiming improvement

Use synthetic regressions derived from the failure classes, without publishing
recipient data: unsupported feature/mode inference, unseen-video claims, quoted
titles containing instructions, EN/PL generation, unrelated/narrow titles,
wrong/forged IDs, changed snapshots, legacy behavior and unchanged approval
digests. Compare source fidelity, proposal relevance, naturalness and the need
for manual replacement on the same reviewed examples, with unavailable model
responses counted separately. Record any real inference route, latency and token
usage actually observed. Unit coverage proves the bounded contract; a human
copy review tests whether the resulting proposal is useful. Neither proves
inbox placement, interest, a reply or revenue. This note runs no live inference,
mailbox read or outreach action and reports no post-change model-quality or
response-rate measurements.
