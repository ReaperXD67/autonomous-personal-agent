# Creator outreach security review

Review date: 2026-08-28

Scope: YouTube creator discovery, public-contact qualification, outreach
sequencing, exact SMTP action planning, reply/result recording, suppression, and
bounded draft adaptation. This is an implementation review, not legal advice or
a review of a configured mail provider's terms.

## Findings

### CO-001 — “Promote everywhere” could become unsolicited mass communication

- Severity: Critical
- Status: Prevented by design
- Evidence: discovery creates prospects without contacts. Each contact requires
  an operator attestation and provenance. Each individual email remains a high-
  risk exact action requiring its own approval.
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
- Status: Prevented for implemented discovery
- Evidence: YouTube normalization stores channel identity, profile URL,
  subscriber count, one matching video, query, and score evidence. It never
  returns or infers email. Contact entry requires a separate public HTTPS source
  and written basis note.

### CO-006 — “Self-improvement” could change authorization or manipulate results

- Severity: Critical
- Status: Prevented by bounded adaptation
- Evidence: learning reads delivered-message and operator-recorded outcome
  counts. It can choose between two fixed truthful introduction templates only
  after minimum samples and a material lead. It preserves exploration and does
  not mutate code, offers, contacts, policy, budgets, SMTP, or approvals.
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

## Production blockers and operating limits

- No inbound OAuth email reader or automatic reply classification is present.
- No business-contact discovery or enrichment is present.
- No real YouTube API key or external SMTP compatibility is claimed by the
  implementation alone.
- No public posting, creator-account login, direct message, payment, contract,
  or campaign-credit issuance is automated.
- EU/EEA direct marketing requires a documented lawful approach, transparency,
  and immediate handling of objections; national ePrivacy rules also apply.
- The shared bearer-token dashboard must remain private until OIDC/RBAC,
  step-up approval, rate limits, and hardened ingress exist.
