# Creator response curation: constrained plans and a durable review stop

Observed November 4, 2026. The requested improvement is automatic preparation of
a context-aware response for private inspection while the owner holds outgoing
replies. Preparing a draft must neither classify a creator as interested nor
create an email action. No upstream code, package or service was installed or
copied for this comparison.

## Inspected primary sources

| Source and pinned provenance | Relevant facts and cost | Decision |
|---|---|---|
| [Ollama v0.40.14](https://github.com/ollama/ollama/releases/tag/v0.40.14), released November 3, 2026; commit [`9a3e8177767245acc62b735eba7d5d8a553606d0`](https://github.com/ollama/ollama/commit/9a3e8177767245acc62b735eba7d5d8a553606d0); [MIT](https://github.com/ollama/ollama/blob/v0.40.14/LICENSE). The release page shows continued maintenance. | The official [structured-output guide](https://docs.ollama.com/capabilities/structured-outputs) documents JSON Schema in `format`, application validation and low-temperature generation. Hermes already has a pinned Ollama runtime and bounded HTTP client. | **Adopt** the schema-constrained selection pattern through the existing local endpoint. This research does not upgrade the repository's pinned 0.32.5 image or add an SDK. |
| [LangGraph 1.2.19](https://github.com/langchain-ai/langgraph/releases/tag/1.2.19), released October 30, 2026; commit [`5bd231cbfd913e05ebc662f519eb9a655bc766df`](https://github.com/langchain-ai/langgraph/commit/5bd231cbfd913e05ebc662f519eb9a655bc766df); [MIT](https://github.com/langchain-ai/langgraph/blob/1.2.19/LICENSE). Recent release activity supports maintenance. | Its [interrupt documentation](https://docs.langchain.com/oss/python/langgraph/interrupts) describes persisted external-review stops and warns that resumed nodes can repeat earlier side effects. The [package manifest](https://github.com/langchain-ai/langgraph/blob/1.2.19/libs/langgraph/pyproject.toml) adds langchain-core, checkpoint, SDK, prebuilt and xxhash packages alongside Pydantic. | **Adapt** durable state, explicit stops and idempotent writes using Hermes tasks/PostgreSQL. **Defer** a second orchestration/checkpoint framework: it duplicates existing ownership and audit paths. |

LangGraph's official [email-agent walkthrough](https://docs.langchain.com/oss/python/langgraph/thinking-in-graph-api)
separates reading, drafting and human review, but also demonstrates routing some
cases directly to sending. **Defer** that automatic-send branch for this job:
the user's hold applies to both conversations. A draft-only terminal state is
the appropriate adaptation. Neither upstream documentation nor a valid schema
establishes that a reply's meaning or proposed commercial terms are correct.

## Selected small component

Use the existing governed worker and local-only inference. The selected
`creator-reply-plan-v1` contract returns only one issued `response_mode`; the
server renders the English/Polish subject, body and provenance. Fixed commercial
wording keeps payment and scope unagreed. A shared handle or invitation can be
acknowledged without claiming friend acceptance, current collaboration or an
agreed fee. A missing route can prompt a business Discord/server-invite question.
Mail text and quoted history remain untrusted evidence, never tool instructions.

Freeze the full private reply body, its digest and campaign context; give the
model only the bounded authored-text view. Refuse overlong input rather than
silently truncate it. Bind the saved response to that context and digest, and
deduplicate repeated sync/manual requests. Automatic curation uses a separate,
default-empty campaign allowlist. Contact authorization may remain withdrawn:
preparing private wording does not restore it.

Expose ready/queued/failed history privately, including already-reviewed replies.
Show the complete response, local source, source-body digest and sending hold.
The UI offers inspection and curation, with no send or approval action. Drafting
does not clear pending review, alter classification or negotiate commercial terms.

## Observable acceptance criteria

Prove identical-context request deduplication, source-digest drift refusal,
default-off campaign isolation, local-only routing, bounded invocation failure,
and no outbound action/approval creation. Browser proof must cover escaped copy,
loading/recovery, stale-modal isolation, reviewed-history discoverability and
mobile wrapping. Keep task/model results separate from live delivery evidence.
This note establishes provenance and design intent; it claims no successful live
curation, creator-interest guarantee or measured reply-rate improvement.

## Explicit recovery after a real startup failure

The first native local attempts failed during model loading with substantial
observed host paging and CPU/disk pressure. GPU fit and container health did not
establish a usable response. [Ollama troubleshooting](https://docs.ollama.com/troubleshooting)
supports inspecting runtime/load diagnostics before changing providers or drivers.
[Microsoft's WSL configuration guide](https://learn.microsoft.com/windows/wsl/wsl-config)
describes shared resource and cache-reclaim behavior; a guest cache count must not
be mistaken for resident host RAM or proof of the sole cause.

Adapt the already-reviewed idempotent-resume pattern as one explicit linked
recovery, preserving the failure, budget cost and original deadline. Ordinary
sync does not repeat it. No orchestration dependency, model upgrade or automatic
global resource setting is added. See [ADR-0040](../decisions/ADR-0040-explicit-creator-draft-recovery.md).
