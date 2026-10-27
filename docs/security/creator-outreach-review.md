# Creator outreach security review

Review date: 2026-10-27

Scope: YouTube creator discovery, public-contact qualification, outreach
sequencing, exact SMTP action planning, reply/result recording, suppression, and
bounded draft adaptation, constrained AI copy, and local Gmail onboarding.
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
- Status: Updated with bounded candidate research (2026-09-19; ADR-0021)
- Evidence: official public channel/video descriptions may yield business-email
  candidates only with nearby business/collaboration wording. Sources, bounded
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
- Status: Constrained suggestions with individual review
- Evidence: `marketing.creator_draft` follows policy, durable task, audit and
  inference-accounting paths. Models see sanitized public metadata and reviewed
  aggregates, excluding recipient addresses and raw descriptions/inbox text.
  Only a hook, optional idea, rationale, fixed evidence reference and assigned
  reach strategy are accepted. Server code composes commercial terms and footer.
  Immutable digest/context and lease checks fence stale drafts; AI messages
  cannot use delegated template authority.
- Residual risk: lexical/schema validation cannot prove truth, contextual
  relevance or product availability. The operator must inspect the sources and
  complete copy. The model sees only sampled metadata, not the actual video.
  The computed editorial report adds observable wording/count warnings, not a
  semantic confidence score or approval. It cannot modify stored copy/digests.

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
- Residual risk: a small source sample can miss relevant activity, contacts or
  context. A score is a prioritization heuristic, not evidence of ownership,
  accurate audience demographics or willingness to collaborate.

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
