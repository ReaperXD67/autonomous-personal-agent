# Creator outreach intelligence choices

Reviewed: 2026-10-27. Scope: useful evaluation and feedback patterns for the
existing creator worker. This was a focused primary-source comparison, not an
exhaustive internet survey or an installation of third-party agent skills.

| Project | Verified provenance | Decision |
|---|---|---|
| [Promptfoo](https://github.com/promptfoo/promptfoo/tree/e48ed85e08ff8a1ca74fa7d0e41daf47cf155efb) | MIT; unarchived; inspected main commit `e48ed85e08ff8a1ca74fa7d0e41daf47cf155efb`; repository activity observed October 26 | Adopt explainable offline evaluation patterns in Hermes's existing trusted test container. No Promptfoo runtime dependency or downloaded prompt pack |
| [DSPy](https://github.com/stanfordnlp/dspy/tree/b8588f10fd7c2af03cba9f45f002b8442bfcbde4) | MIT; unarchived; inspected main commit `b8588f10fd7c2af03cba9f45f002b8442bfcbde4`; repository activity observed October 27 | Keep reviewed explanatory feedback as a future evaluation input. Do not add automatic prompt/code optimization without a reviewed dataset and bounded experiment |
| [Instructor](https://github.com/567-labs/instructor) | Canonical repository resolved from instructor-ai/instructor; MIT; unarchived; activity observed October 26 | Not added: schema validation and separately accounted bounded correction retries already exist in Hermes |

Licenses, repository state and commit references above were read from public
GitHub metadata. These are observation pins, not installed package versions.
No upstream code was copied or executed, and no provider or sending authority
was added.

## What shipped

[Promptfoo's Python assertions](https://www.promptfoo.dev/docs/configuration/expected-outputs/python/)
demonstrate boolean or numeric evaluations with explanatory results. Hermes
uses a small pure component to report observable editorial markers instead of
inventing an overall quality score. Existing draft reads expose it, and the
review UI shows plain escaped findings with the complete-email word count.
There is no new database record, model request, dependency or approval decision.

Synthetic cases cover title numbers, unsupported viewing/video-content claims,
generic openings, requested-language mismatch, feedback claims with zero
reviewed samples, missing source/next-step markers, rendered length, safe missing
data and unchanged private state/digests. Checks describe what they observed;
they cannot certify relevance, fluent translation or willingness to collaborate.

English/Polish reply and objection hints also fit the existing deterministic
path. They normalize bounded excerpts, remove recognizable quoted history and
guard conditional/negated interest. Raw evidence is unchanged, positive interest
requires original-message review, and feedback tags remain reviewed inputs.

## What remains deferred

[DSPy's GEPA](https://dspy.ai/3.4.1/api/optimizers/GEPA/overview/) uses evaluation
scores with explanatory feedback to propose improvements. Hermes currently has
no measured creator-response dataset establishing such an optimizer's benefit.
Its existing reviewed-outcome learner stays bounded; neither prompts nor code
are autonomously rewritten by this milestone.

[Instructor's validation retries](https://python.useinstructor.com/learning/validation/retry_mechanisms/)
would overlap existing Pydantic parsing and bounded retry accounting. Additional
dependencies are not evidence of better copy.

[Promptfoo's security model](https://github.com/promptfoo/promptfoo/blob/e48ed85e08ff8a1ca74fa7d0e41daf47cf155efb/SECURITY.md)
also treats configured extensions as executable trusted code. Arbitrary remote
skills, assertions or prompt packs are not loaded into the running agent. Any
future integration needs isolation and scoped credentials; it cannot bypass
Hermes's control-plane policy, exact approval or PostgreSQL audit path.
