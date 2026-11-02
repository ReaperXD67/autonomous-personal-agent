# Creator outreach security review

Review date: 2026-11-02

Scope: YouTube creator discovery, public-contact qualification, outreach
sequencing, exact SMTP action planning, reply/result recording, suppression, and
bounded draft adaptation, grounded selection/rendering, draft preparation
batches, and local Gmail onboarding.
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
  evidence requires it. See [ADR-0032](../decisions/ADR-0032-preserve-active-creator-evidence-during-discovery.md).

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
  expiry after advisory-lock waits passed disposable PostgreSQL proof. See
  [ADR-0033](../decisions/ADR-0033-actual-smtp-pacing-and-durable-deferral.md).
- Residual risk: a queued action can have a terminal linked task. Recovery must
  inspect task/receipt state rather than count every queued action as runnable;
  actual SMTP acceptance still does not establish inbox placement. The corrected
  gate has no new external SMTP pacing canary; the original burst remains a
  recorded incident rather than evidence of compliant delivery cadence.

## Production blockers and operating limits

- A label-scoped read-only Gmail adapter and conservative reply suggestions are
  implemented. English/Polish hints exclude recognizable quote/forward history
  and distinguish direct objections from instructional mentions; negation,
  conditional interest and uncertain matches still require original-message
  review. Same-mailbox renewal and a fresh governed runtime read passed; a real
  incoming-reply matching/replay canary remains separate live proof.
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
