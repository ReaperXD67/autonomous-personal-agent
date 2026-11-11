# Creator outreach security review

Review date: 2026-11-06

Scope: YouTube creator discovery, public-contact qualification, outreach
sequencing, exact SMTP action planning, reply/result recording, suppression, and
bounded draft adaptation, grounded selection/rendering, draft preparation
batches, local Gmail onboarding, complete-reply evidence and local draft-only
response curation with owner conversation holds.
This is an implementation review, not legal advice or
a review of a configured mail provider's terms.

## Findings

### CO-001 — “Promote everywhere” could become unsolicited mass communication

- Severity: Critical
- Status: Prevented by design
- Evidence: discovery creates unreviewed business-contact candidates. Each authorized contact requires
  an operator attestation and provenance. Each email remains a high-risk exact
  action. A finite campaign grant can authorize eligible template introductions
  and reviewed-interest handoffs; model-written copy requires individual review.
- Residual risk: an operator can still approve unsuitable outreach. Campaign
  owners must verify applicable direct-marketing and platform rules.

### CO-002 — A rejection could be misread as permission for another pitch

- Severity: High
- Status: Prevented by explicit reply states
- Evidence: only `declined_unpaid` unlocks one paid option. `do_not_contact` and
  `bounced` clear authorization and set durable suppression. An unspecified “no”
  must be recorded as do-not-contact, not unpaid-only decline.

### CO-003 — A pending approved email could outlive a later opt-out

- Severity: High
- Status: Fixed
- Evidence: `begin_side_effect` locks and revalidates the marketing prospect
  immediately before creating the SMTP receipt. Changed address, withdrawn
  authorization, suppression, or reply-state drift refuses execution.

### CO-004 — API discovery could leak its key or become a generic fetcher

- Severity: High
- Status: Mitigated
- Evidence: the key is present only in the egress-enabled research worker. The
  client fixes scheme, host, API prefix, redirects, timeout, response size,
  safe-search setting, query count, and result count. Errors do not include the
  key-bearing request URL. Task/audit payloads contain only campaign IDs.
- Residual risk: a Google API key should also be restricted in Google Cloud to
  YouTube Data API v3 and the deployment source IP.

### CO-005 — Public channel data could be treated as a contact database

- Severity: High
- Status: Bounded candidate research; address-only business-word false positives fixed (2026-11-02)
- Evidence: official public channel/video descriptions may yield business-email
  candidates only with nearby business/collaboration wording outside email
  addresses. All address spans are masked before bounded context slicing, so
  the candidate's local part, domain or a truncated neighboring address cannot
  supply the business label. The immediately preceding label line remains
  bounded and cannot contain another address; existing negative-context checks
  remain. A bare `business@…` is not an invitation. Sources, bounded
  excerpts, and timestamps are retained separately from authorized recipients.
  Contact authorization still requires source review, written basis, and an
  explicit operator decision. Refresh cannot authorize contact or undo suppression.
- Residual risk: descriptions may contain agency/sponsor contacts, stale addresses,
  hostile text, or unclear ownership. Heuristics are not ownership verification.

### CO-006 — “Self-improvement” could change authorization or manipulate results

- Severity: Critical
- Status: Prevented by bounded adaptation
- Evidence: learning reads SMTP-accepted-message and operator-reviewed outcomes
  with distinct-creator deduplication. It can choose among three fixed paid-copy
  strategies under sample/effect thresholds and inform later constrained AI
  prompts using reviewed aggregates. It preserves exploration and does
  not mutate code, offers, contacts, policy, budgets, SMTP, or approvals.
  Operator-personalized introductions retain exact approval and contact guards,
  but manual and AI variants are excluded from template performance comparison.
- Residual risk: manually entered attribution can be inaccurate. Suggestions
  show their sample evidence and should not be treated as causal proof.

### CO-007 — Promotional claims could exceed product readiness

- Severity: Medium
- Status: Operator control required
- Evidence: campaign copy is based on explicit product/offer fields and avoids
  “no one has done this” or guaranteed-result claims. Exact approval exposes the
  full message before send.
- Residual risk: the operator must keep live adoption, reward availability,
  point issuance, compensation, and sponsorship disclosures truthful.

### CO-008 — Cross-channel promotion could become automated spam

- Severity: High
- Status: Prevented by copy-only design
- Evidence: the promotion-kit endpoint is deterministic and read-only. It
  creates separate UTM links and browser-copyable text but has no platform
  credential, posting client, scheduler, or public-write capability.
- Residual risk: the operator must check each community's rules, contextualize
  the copy, avoid repetitive posting, and disclose material relationships.

### CO-009 — Model personalization could fabricate claims or change the offer

- Severity: High
- Status: Bounded plan selection and server rendering; individual review retained
- Evidence: `marketing.creator_draft` follows policy, durable task, audit and
  inference-accounting paths. Models see sanitized public metadata and reviewed
  aggregates, excluding recipient addresses and raw descriptions/inbox text.
  New `creator-grounded-plan-v2` contexts accept only an issued `evidence_id`
  and offered `angle_id`, without extra fields or duplicate keys. The server
  derives English/Polish copy and its explanation from authored wording,
  observed title metadata and the reviewed campaign. Source/title/URL,
  language, context and campaign digests bind the stored provenance; save and
  preparation rederive and compare the complete stored copy. Rendering also
  rejects changed source or campaign bindings. A title keyword offers an
  independent proposal, not a product capability, supported mode or proof of
  video contents. Commercial terms and the standard English footer remain
  deterministic. Unsupported explicit languages fail before inference.
  Markerless legacy contexts retain the existing free-copy validation path;
  old records and reviewed digests are not rewritten into the new contract.
  Immutable context, expiry, owned leases and cancellation fence both paths.
  Neither can use delegated template-send authority.
  Local v2 selection disables reasoning output and has a 512-token generation
  cap; at most one invalid-output correction has its own inference accounting
  and execution checks. Invalid selection and unavailable model response have
  separate fixed errors. No failed request silently acquires fallback prose,
  approval or sending authority.
  New contexts freeze a separate concise permission-first rendering marker;
  earlier unmarked v2 copy remains byte-for-byte compatible. Per-draft
  `local_only` is a fixed model-route selection, not an endpoint or prompt
  override. It skips hosted calls, binds idempotency/context/audit, and shares
  existing preparation and inference accounting. The fixed internal Ollama
  transport bypasses environment proxies. Failed local response reads,
  timeouts, HTTP errors and incomplete envelopes terminate with fixed safe
  codes; provider bodies and reasoning are not retained. Neither a local-only
  canary nor the new style gains approval, contact or sending authority.
  Measured cold generation motivates a fixed 300-second grounded local response
  timeout, with legacy remaining 180 seconds. It is not a hard task-duration
  guarantee. Independent lease renewal and post-inference cancellation/context/
  expiry checks remain; the longer response window adds no invocation, retry,
  approval extension or email authority.
  The November 1 launch retained one AI message and twenty-three reviewed
  manual replacements. Those operator decisions motivated the smaller factual
  surface; they are not creator feedback, training or proof of improved replies.
- Residual risk: source membership and deterministic rendering cannot establish
  that an operator's product brief is true, a sampled title is representative,
  a proposed test is suitable or a creator is interested. Authored angle wording
  needs review when product scope changes. The operator must inspect the sources
  and complete copy. The model sees sampled metadata, not the actual video.
  The computed editorial report adds observable wording/count warnings, not a
  semantic confidence score or approval. It cannot modify stored copy/digests.
  An empty finding list did not establish semantic accuracy in the earlier
  free-copy canary; legacy lexical checks remain bounded observations.

### CO-010 — Gmail setup could connect the wrong account or disclose credentials

- Severity: High
- Status: Explicit local account and scope checks
- Evidence: the native helper uses PKCE, random state, a bounded loopback
  callback, fixed Google endpoints and exact `gmail.readonly` scope. It verifies
  the expected mailbox and creator label before an atomic ignored-config write.
  A shared lock coordinates SMTP/OAuth writers; conflicting existing career
  credentials stop setup. Tokens and provider responses are not printed.
  Explicit renewal can proceed after an exact HTTP 400 `invalid_grant` refresh
  response only for the recorded enabled creator mailbox, same Desktop client,
  complete existing settings and disabled career monitoring. New consent must
  still pass all scope/identity/label/save checks; outages and wrong clients do
  not qualify. See [ADR-0028](../decisions/ADR-0028-explicit-creator-oauth-renewal.md).
- Residual risk: Google grants mailbox-wide read access even though runtime
  reads use one label. Local configuration still contains secrets, Google may
  revoke grants, and Testing-mode token expiry requires reauthorization.

### CO-011 — A batch shortlist could become an implicit sending decision

- Severity: High
- Status: Research-only capability
- Evidence: `marketing.creator_pilot` uses the existing policy/task/audit path,
  official YouTube metadata, a maximum of ten creators and three uploads each,
  and a shared rolling refresh allowance. Ranking is deterministic; output
  separates reasons, missing evidence, contact-review needs and publication
  dates. It makes no model call and creates no contact authorization or email.
  The dashboard loads the current dossier before a review or draft.
  Selection rotates through unattempted then oldest-attempted creators using
  24-hour issued reservation history bound to the canonical task-payload hash,
  current targeting snapshot and exact profile URL. Eligibility/fair ordering
  precede the 500-candidate cap. Generic tasks, stale context and modified audit
  hashes cannot supply priority history; failed/cancelled work remains budgeted.
- Residual risk: a small source sample can miss relevant activity, contacts or
  context. A score is a prioritization heuristic, not evidence of ownership,
  accurate audience demographics or willingness to collaborate.

### CO-012 — Repository research could import untrusted execution instructions

- Severity: High
- Status: Instruction-only reuse workflow; runtime authority unchanged
- Evidence: the reusable research skill requires primary-source provenance,
  license and fit review before adoption. It contains no executable helper,
  provider credentials or remote extension loader. Inspected repository content
  remains source material; the existing project policy governs installations,
  execution, publication and sending.
- Residual risk: an operator can still select unsuitable upstream code or a
  skill. Research and a successful installation do not prove a measured benefit
  or grant permission for external actions.

### CO-013 — Draft batching could amplify preparation or imply send permission

- Severity: High
- Status: Issued preparation-only capability
- Evidence: `marketing.creator_draft_batch` is medium risk and enters the
  existing policy/task/outbox/audit path. A creation audit binds the canonical
  payload hash, frozen membership and child keys; generic caller tasks and
  changed payloads cannot issue children. Each bounded batch contains at most
  five reviewed contacts. A shared PostgreSQL lock accounts for actual drafts
  plus genuine unmaterialized reservations, including stopped parents, under
  thirty per rolling day and three per prospect. Child materialization checks
  its key, actor, prospect and frozen input hash before consuming its reservation.
  Cross-campaign batch selection excludes matching canonical channels/profiles
  and exact normalized business addresses in current drafts, reservations and
  its own selected set. Current eligibility, context and lease checks follow
  row waits. Atomic child/outcome writes allow resume without duplicate work;
  terminal skips remain terminal. Preparation creates no external-action
  packet, approval decision, send grant or contact authorization.
- Residual risk: a completed parent means child drafting was queued, not that
  inference or complete-copy review succeeded. Cancelling a parent cannot recall
  independently queued children. Identity matching depends on the recorded
  channel/contact evidence and is not proof of ownership. The final sending
  boundary and exact individual review remain separate.

### CO-014 — A recurring reviewer could bypass review or duplicate ongoing work

- Severity: High
- Status: Defined operator continuation scope; existing API boundaries retained
- Evidence: the [continuation runbook](../operations/creator-outreach-continuation.md)
  fixes the reviewer to two privately selected campaigns and at most six new
  introductions per rolling 24 hours combined. This is an operating ceiling,
  not a new server authorization. The heartbeat inspects existing tasks,
  reservations, pending replies and the complete current action-creation window before
  adding work. Native discovery, labeled reply reads, draft generation and
  action execution retain their existing task/policy/audit paths. Personalized
  mail still requires recorded contact review, complete-copy review and an
  individual exact-action approval; positive interest is confirmed before one
  owner handoff. No generic template-send run is enabled by this continuation.
  The shared SMTP and preparation/refresh limits are unchanged. New automatic
  lead selection additionally requires recent dated Minecraft evidence and
  explicit business wording outside addresses; ambiguity is held for review.
- Residual risk: the reviewer can make an incorrect judgment, an app schedule
  can miss a run, or required local services/credentials can become unavailable.
  An incomplete current creation window cannot establish remaining allowance;
  a bounded page with a verified older boundary can still establish that window.
  Lifetime history truncation is not itself a reason to discard a complete
  current window or to infer cumulative delivery counts. Pausing the reviewer
  alone does not recall already queued email. Schedule installation, manual
  execution and actual SMTP/reply outcomes need separate evidence; no cadence
  establishes continued availability, ownership or creator interest.

### CO-015 — Routine discovery could invalidate active reviewed evidence

- Severity: High
- Status: Bulk-only preservation under existing row locks
- Evidence: bulk saves preserve an existing creator's research while an
  unexpired active draft or linked exact outreach action protects it. The check
  runs after existing campaign/prospect identity and suppression locks/checks;
  it adds no task/action row locks or recipient/body/digest writes. New records
  and unprotected rows retain normal discovery behavior. The saved campaign
  discovery summary exposes `protected_count` with an aggregate preservation
  audit. Terminal/expired work
  releases the pin; explicit single-creator refresh still invalidates changed
  snapshots. Contact withdrawal, suppression, campaign changes, expiry and the
  final SMTP fence remain effective.
- Residual risk: preserved research can become outdated while a packet waits.
  The pin extends no freshness window or approval deadline and does not certify
  the current source. Operators can intentionally refresh/withdraw work when new
  evidence requires it. See [ADR-0033](../decisions/ADR-0033-preserve-active-creator-evidence-during-discovery.md).

### CO-016 — Overdue reservations could burst after worker recovery

- Severity: High
- Status: Confirmed incident; deployed correction passed local PostgreSQL proofs
- Evidence: seventeen actual SMTP acceptances occurred between November 2,
  05:18:23 and 05:19:39 UTC despite the configured 900-second global gap,
  1,800-second domain gap and three-per-hour policy. Existing reservations were
  spaced, but the receipt boundary checked only that a slot was no longer in
  the future. Multiple overdue slots could therefore execute together. The
  prior local test/verifier checkpoint did not establish recovery pacing.
- Correction: approval and the actual receipt boundary share a database gate.
  Actual accepted/ambiguous history and unresolved sending enforce the stricter
  frozen/current policy. A later safe slot durably requeues the same unstarted
  task without a receipt, consumed claim attempt, changed copy or extended
  expiry; an insufficient window refuses. Concurrent overdue work, unresolved
  and completed receipts, policy changes, durable state and lease/approval
  expiry after advisory-lock waits passed disposable PostgreSQL proof. The
  combined career/creator integration also rechecks time-dependent scope after
  that wait using plain reads of already-locked rows; creator-run/AI lifetime,
  Gmail freshness, publication age and career-contact expiry wait cases passed.
  See
  [ADR-0034](../decisions/ADR-0034-actual-smtp-pacing-and-durable-deferral.md).
- Residual risk: a queued action can have a terminal linked task. Recovery must
  inspect task/receipt state rather than count every queued action as runnable;
  actual SMTP acceptance still does not establish inbox placement. The corrected
  gate has no new external SMTP pacing canary; the original burst remains a
  recorded incident rather than evidence of compliant delivery cadence.

### CO-017 — Body retrieval could broaden mailbox access or overstate reply evidence

- Severity: High
- Status: Implemented; isolated privacy/scope/retry proofs and two live complete reads passed
- Selected controls: existing `marketing.gmail_sync` metadata matching precedes
  at most three full-message reads inside its combined twenty-message budget.
  Only pending exact matches in the configured mailbox/custom label qualify,
  including existing metadata-only rows. Returned message/thread IDs, sender,
  subject and received time must match the saved record; task/campaign fences
  follow provider work. No OAuth expansion or mailbox write is introduced.
- Campaign scope: `CREATOR_GMAIL_FULL_REPLY_CAMPAIGN_IDS` is an explicit JSON
  allowlist of at most ten distinct campaign UUIDs, default `[]`. Automatic
  hydration and explicit read requests enforce it; other campaigns remain
  metadata-only. The readiness flag reports opt-in, not successful access.
  Existing authenticated captured-history reads remain available after opt-out.
- Content boundary: depth eight, sixty-four MIME nodes, 128 KiB decoded content,
  24,000 text characters and fixed charsets bound parsing. Attachments and
  embedded messages are excluded without attachment endpoint requests or
  external fetches. Full responses may include attachment metadata/encoding;
  attachment content is not decoded or stored. Malformed, missing, unsupported
  or over-limit required text remains incomplete/unavailable. A snippet or
  truncated body cannot be labeled complete.
- Review boundary: full selected plaintext/digest/status are separate private
  evidence. Overview and audit output omit bodies; authenticated detail is
  rendered as text, never active HTML or executable instructions. Complete rows
  remain stable; incomplete rows receive at most three attempts with a five-
  minute cooldown. Semantic review requires the exact complete-body digest;
  full text alone adds no positive decision, negotiation, handoff or send grant.
- Failure hold: a known completed read failure newer than the last complete
  sync blocks sending readiness and delegated authority. Only a later complete
  sync establishes recovery; configured credentials or queued/running work do
  not clear the hold. The dashboard displays a fixed warning without raw errors.
- Residual risk: exact sender/subject correlation is not sender authentication.
  A body can contain misleading statements, quoted history, signatures or hostile
  instructions. Completeness and digest integrity do not establish correct
  interpretation. Read-only OAuth remains mailbox-wide at Google, while the
  application enforces the narrower selection. Required regression and live
  evidence are listed in [ADR-0037](../decisions/ADR-0037-bounded-creator-full-reply-evidence.md).

### CO-018 — Response curation could leak inbox text or bypass an owner hold

- Severity: High
- Status: Implemented; complete isolated proof and two live local response drafts passed
- Scope: separate default-empty `CREATOR_REPLY_DRAFT_CAMPAIGN_IDS` selection
  gates both explicit requests and bounded automatic scheduling. Complete saved
  body evidence is required; the prior successful outreach, campaign/contact
  context, issued task/audit binding and owned lease are checked again after
  inference. Suppression refuses generation; withdrawing sending authorization
  does not erase evidence or prevent draft-only owner review.
- Data and output: private evidence goes only to the fixed configured local
  model, without a hosted fallback. The model selects issued response-mode IDs;
  server rendering cannot promise agreed rates, earnings or accepted friend
  requests. Full source and copy are private authenticated text. Routine overview,
  task and audit output omit the content. Unsupported or adversarial evidence can
  remain without a draft; no silent substituted copy is sent.
- Authority: one medium-risk preparation capability, no SMTP action or semantic
  review mutation. It cannot clear another reply, approve itself, renew an expired
  run, restore contact authorization or bypass final sending guards. An owner
  hold cancels pending work and withdraws authorization, distinct from recipient
  suppression. Repeated syncs reuse evidence-bound preparations; failed/cancelled
  drafts still consume the shared preparation allowance.
- Residual risk: authored-text separation and mode selection are bounded
  heuristics, not complete interpretation or sender authentication. Inspect the
  complete source and saved copy. The feature neither connects a Discord account
  nor sends a friend request. See [ADR-0038](../decisions/ADR-0038-local-creator-reply-curation.md).

### CO-019 — Recovery could erase failure or repeatedly spend preparation budget

- Severity: Medium
- Status: Implemented; full isolated validation and two real linked recoveries passed
- Controls: one explicit linked second preparation for an original terminal
  local model-unavailable failure, backed by a failed local invocation. Preserve
  original task, copy absence, audit and deadline; inherit that deadline and
  count both attempts in shared limits. Current source/contact/campaign binding,
  suppression, five-minute cooldown and database lineage uniqueness are checked.
  Ordinary/native preparation cannot initiate recovery. Cancelled, ready,
  invalid-output, changed or expired work and third attempts refuse.
- Authority: this remains private drafting, with one invocation per task and no
  email action, review mutation, hosted fallback or restored contact permission.
  The UI uses server eligibility and an explicit request, never status polling,
  to create recovery. A requested retry does not prove the provider is working.
- Residual risk: resource pressure or provider faults may recur. Actual model
  output and complete-copy review are needed before releasing an availability
  hold. See [ADR-0040](../decisions/ADR-0040-explicit-creator-draft-recovery.md).

### CO-020 — Search freshness could disagree with current drafting evidence

Discovery separates date and relevance pagination while retaining the same
durable search reservations and total request ceiling. Returned video metadata
must bind the exact channel, public/non-upcoming state and actual publication
window before treating a sample as current evidence. Explicit shortlist research
can promote a verified recent upload whose title identifies Minecraft before
language, contact and draft-evidence projection. The final reread supplies
contact candidates for the selected source, preventing an earlier removed
address from being merged back.
A contradictory reread fails that research. Recent unrelated uploads do not
renew an old matching sample. Approved-packet protection and explicit-refresh
invalidation remain separate. Search and the first three uploads are bounded
samples, and published metadata does not prove content suitability or interest.
See [ADR-0041](../decisions/ADR-0041-recent-creator-evidence.md).

### CO-021 — Targeted research must not refresh occupied identities

Optional explicit shortlist IDs stay inside the existing issued pilot task and
shared reservation accounting. Selection is all-or-nothing and idempotency binds
the requested ordered IDs. Cross-campaign canonical identity and known contact
matches refuse suppression, conversations, protected draft/packet evidence and
issued reservations. Eligibility is checked before research and again before
saving, including fresh contact observations. Omitted IDs retain automatic
selection. Neither path grants contact authorization or email approval.
See [ADR-0042](../decisions/ADR-0042-explicit-creator-research-selection.md).

## Production blockers and operating limits

### Owner stop and managed promotion instructions

A finite-run Pause is narrower than a campaign owner stop. The independent
PostgreSQL stop/epoch rejects exact and delegated creator authority at approval
and the final locked receipt boundary. Cleanup cancels scoped pending tasks;
its interruption cannot clear the stop. Explicit resumption does not revive
pre-stop approvals or restore grants/discovery. Already-entered SMTP and
ambiguous receipts remain separate outcomes. Old deployed images require a
controlled no-egress upgrade; offline local intent is not a committed live stop.
See [ADR-0043](../decisions/ADR-0043-durable-creator-outreach-stop.md).

The managed organic promotion pack contains reviewed instructions, not provider
clients or executable skills. Its networkless installer verifies bounded file
hashes and paths, rejects symlinks and collisions, owns only its namespace and
preserves private skills/memory. Installing or invoking a skill does not restore
sending, create an account, authorize posting or establish product/policy claims.
See [ADR-0044](../decisions/ADR-0044-reviewed-hermes-promotion-skills.md).

- A label-scoped read-only Gmail adapter and conservative reply suggestions are
  implemented. English/Polish hints exclude recognizable quote/forward history
  and distinguish direct objections from instructional mentions; negation,
  conditional interest and uncertain matches still require original-message
  review. Same-mailbox renewal and live metadata intake/matching passed; repeated
  sync stability was observed for one existing record, not a general replay
  canary. Complete-body hydration and digest-bound review passed isolated source,
  scope, PostgreSQL and browser proofs. Two complete real replies were retrieved
  after owner same-account renewal. Authored review confirmed one willingness to
  discuss; current owner holds prevent both replies. No externally delivered
  handoff or agreed collaboration is established.
- Business-contact discovery is limited to unreviewed candidates in official
  public descriptions; no gated About email extraction or general website crawl
  is present. Fit scores and research ideas are deterministic; optional AI
  introduction suggestions are separately labeled and individually reviewed.
- No real YouTube API key or external SMTP compatibility is claimed by the
  implementation alone.
- No public posting, creator-account login, direct message, payment, contract,
  or campaign-credit issuance is automated.
- EU/EEA direct marketing requires a documented lawful approach, transparency,
  and immediate handling of objections; national ePrivacy rules also apply.
- The shared bearer-token dashboard must remain private until OIDC/RBAC,
  step-up approval, rate limits, and hardened ingress exist.
