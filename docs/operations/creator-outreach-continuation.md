# Continue reviewed creator outreach

This runbook defines the ongoing operator/reviewer loop for the two explicitly
selected English and Polish KarixMC campaigns. It reuses Hermes's existing
policy, PostgreSQL audit, draft and exact-action APIs. It does not enable a
generic template-sending run or grant a model authority to approve its own copy.
The [creator workflow](minecraft-creator-workflow.md) describes setup, commercial
terms and the individual review screens.

## Scope and cadence

| Work | Scope |
|---|---|
| Reviewer heartbeat | Hourly in the Codex desktop app, continuing until the user pauses it; use the two campaign IDs saved privately during setup, never guessed IDs or name-only matching |
| Official YouTube discovery | Hermes's native daily schedule for those campaigns; reuse existing fresh dossiers before asking for another discovery or refresh |
| Reply reading | Hermes's existing read-only labeled Gmail scheduler, no more often than every five minutes for campaigns with qualifying recent outreach |
| New introductions | At most six per rolling 24 hours across both campaigns combined; aim for three English and three Polish, without filling weak or ambiguous slots |
| Shared limits | Existing SMTP 24/day, three/hour, global/domain gaps and jitter; creator preparation and shortlist refresh each retain their thirty-per-rolling-day allowance |
| Message review | Source/contact review, complete exact-copy review and an individual API approval for every personalized email |
| Interest and handoff | Confirm the original reply, then one reviewed owner-contact email using the saved campaign contact, including Discord `karixai`; the owner continues |

The six-introduction ceiling is the reviewer's operating scope, not a new
Hermes server limit. Count initial packets whose `created_at` is within the
preceding 24 hours in the combined two-campaign scope, including queued or
uncertain work, before adding any. A recent `executed_at` alone does not make an
older packet a new creation. Shared SMTP capacity includes handoffs and other
email. Never
raise the limits to clear a backlog or turn unused allowance into a later burst.
Existing approved work is not recalled by this smaller operating ceiling; when
the current creation window already contains six or more introductions, add no
new ones until allowance returns.
The percentage and earning window in weeks remain individually negotiated;
do not change the saved product, compensation or campaign-copy settings.
Run only one reviewer cycle at a time, and recheck allowance before each new
approval. If another cycle is active or its state is uncertain, wait rather
than starting a parallel reviewer. Code, credentials and provider configuration
are maintenance work outside this recurring outreach scope.

Keep the computer, Docker and the desktop app running for this local workflow.
Local scheduled tasks require the computer and app to remain available;
scheduling alone does not establish a successful run. Manage the recurring
task through the app's Scheduled controls. See the
[official OpenAI scheduled-task documentation](https://learn.chatgpt.com/docs/automations?surface=app).

## Each hourly cycle

1. **Read before doing more work.** Inspect communications readiness/pacing,
   mailbox freshness, pending replies, existing task/batch status, current draft
   status/expiry and recent initial-message actions in both selected campaigns.
   An incomplete current creation window cannot establish remaining allowance.
   Resume existing work rather than issuing another task for the same creator.
   Inspect each queued action's linked task: a dead-lettered or otherwise
   terminal task is blocked even when its action still says queued. Check
   receipts/acceptance evidence before any recovery decision; never assume a
   queue label proves delivery or permits replay.
2. **Review replies first.** Check the original authored message, not a quoted
   pitch or a positive-looking snippet alone. Apply explicit opt-outs through
   the existing suppression path. Confirm actual interest before preparing one
   owner handoff; leave uncertain messages or negotiations for review. Do not
   invent an answer, a rate, a response or a creator-feedback outcome.
3. **Qualify new candidates from official metadata.** Use the gates below.
   Research precedes drafting: refreshing a creator after a draft or approval
   can invalidate its frozen context. Skip creators with active drafts, issued
   reservations or prior/pending outreach under the same canonical channel or
   exact normalized business address, including the other campaign. Do not run
   duplicate discovery/refresh tasks or repeatedly spend allowance on one lead.
   Routine bulk discovery preserves rows protected by active drafts/packets and
   records `protected_count` in the campaign discovery summary; it does not
   refresh their timestamps. Explicit
   single-creator refresh still invalidates a changed frozen context. Protection
   ends with the relevant expiry/terminal state and does not delay opt-outs or
   other final send guards. See [ADR-0033](../decisions/ADR-0033-preserve-active-creator-evidence-during-discovery.md).
4. **Prepare within remaining allowance.** Request individual drafts for the
   exact prequalified creator IDs when the campaign's broader server-selected
   batch could include sources outside this runbook's additional ninety-day
   gate. Use existing draft-only batches of at most five, three by default,
   only when their selection scope is suitable; do not assume a requested count
   freezes an operator-selected list. Stop at the combined six-new-introduction
   ceiling, any shared budget, unavailable model/provider or unresolved evidence.
   Failed and cancelled preparation reservations remain counted. Do not generate
   a replacement solely to hide failure or refresh a deadline.
5. **Review and approve exact copy.** Verify the cited source, selected angle,
   reviewed brief, individually negotiated revenue-share wording, sender,
   owner contact and mandatory footer. Use the stored digest; compare the
   complete prepared subject/body before the ordinary individual approval.
   The next reserved send slot must fit its actual approval expiry. Do not
   edit an already approved packet, bypass pacing or report queued mail as sent.
   Reservation time is a lower bound: actual sending/accepted/ambiguous history
   can durably defer the same unstarted task. An unresolved sending receipt
   blocks further egress; insufficient time before expiry refuses rather than
   extending or replacing the packet.
6. **Record and stop.** Preserve task/action IDs, source dates, decisions and
   outcomes privately through the existing APIs. Keep secrets and recipient
   details out of tracked files and notifications. Stay quiet when nothing
   actionable changes; notify on an actual reply/handoff, completed meaningful
   work, failure or required user action. A waiting queue is not a new lead.

## Gates for new recurring leads

- Use the canonical channel identity and a matching public, non-upcoming video
  owned by that channel. Preserve its actual publication date and source URL;
  observation time is a separate fact. Require fresh research within seven days
  and Minecraft publication evidence within ninety days for new automatic
  selections. Description boilerplate and an old sampled title are insufficient
  proof of current Minecraft activity. Ambiguous topic evidence stays reviewed.
- Require observed subscriber evidence inside the saved campaign range. Counts
  do not establish views, sales or audience demographics. Preserve explicit
  country/language declarations and existing prefer/strict semantics. Rank
  matching language first; a known mismatch or unknown language is a review
  case, not proof that the creator understands the proposed language.
- The exact business address must be published in the inspected channel/video
  description with explicit business, collaboration, sponsorship, `Biznes` or
  `Współpraca` wording outside every email address. A bare `business@…` address
  is not its own business invitation. Hold support, fan, personal, closed,
  negated or ambiguous third-party contacts. Never guess an address, scrape
  gated contact controls or infer ownership from the address's spelling.
- Review and record the exact source/basis before authorizing the contact.
  A candidate or fit score does not authorize a recipient. Preserve global
  suppression, prior conversation state and cross-campaign duplicate guards.
- Apply the ninety-day rule as an additional recurring-selection gate. Do not
  silently tighten existing campaigns or rewrite their already approved packets.
  The two previously reviewed ready drafts remain under the existing 365-day
  campaign scope; do not relabel them as newly qualified ninety-day leads or
  rewrite their prior review basis. The out-of-window regression sample remains
  a test case until
  fresh evidence qualifies it and a fresh draft can be prepared within budget.

Official metadata can support these dated identity and declaration checks; it
does not prove unseen video contents, a genuine business owner, willingness to
collaborate, server safety or product availability. The reviewed brief and
creator's independent verdict remain necessary.

## Compact local inspection

From the repository root, the helper defines functions without sending a
request on import:

```powershell
. ./scripts/creator-review-api.ps1
Get-CreatorReviewSnapshot -CampaignId @(
    [Guid]'FIRST-REVIEWED-CAMPAIGN-ID',
    [Guid]'SECOND-REVIEWED-CAMPAIGN-ID'
)
```

Replace the placeholders with the two IDs already reviewed during setup; keep
them in private operator configuration rather than publishing them here. The
snapshot reads compact readiness, pacing, latest SMTP diagnostic status, mailbox
freshness, pending-reply IDs, latest batch items and recent initial actions. It
omits addresses, bodies, credentials and approval requests. Require
`initial_creation_window_complete` before concluding there is room for new
introductions. A 200-item response can still cover the whole current creation
window when its verified creation-date boundary is older than 24 hours.
`action_history_may_be_truncated` then describes older lifetime history rather
than blocking that complete window. Do not infer cumulative delivery totals
from a bounded page; shared SMTP capacity remains server-enforced.

`Invoke-CreatorControlApi` supports explicit allowlisted loopback control-API
paths. Additional reads and authorized mutations still use the ordinary audited
APIs; the helper is not an alternate SMTP client or an approval bypass. Never
print its credentials or save private responses into tracked documentation.
`CREATOR_CONTROL_HTTP_409` is a conflict/pacing deferral to inspect or wait on,
not a reason to force a retry with another identity or idempotency key. Errors
remain fixed diagnostics rather than raw provider responses.

Run `./scripts/creator-review-api-smoke.ps1` for the helper's synthetic native
regressions. They use temporary fixture configuration and mocked HTTP, not
Google, SMTP delivery or a real campaign. A successful compact live read and
an actual reviewed cycle remain separate operating evidence.

## Pausing and evidence

Pause the recurring task when the user requests it. If the user asks to stop
outreach, stop new discovery/preparation/approvals and cancel pending actions
through the existing control plane as appropriate; pausing a reviewer alone
does not recall queued email. SMTP-accepted messages cannot be recalled. Keep
the durable audit and suppression history.

The engineering journal and Experiment 41 record the actual schedule
installation, manual-cycle result, tests and delivery checkpoint. A configured
schedule, healthy service, ready draft, exact approval, SMTP acceptance, inbox
arrival and interested creator are distinct results. This workflow guarantees
none of the latter outcomes and does not retrain its model from silence.

At November 2, 2026, 05:45:50 UTC (11:15:50 IST), the twenty-eight-invitation
scope contained twenty-three SMTP acceptances, four runnable queued v2 packets
and one blocked action whose linked task was dead-lettered after lease
exhaustion. The blocked action/task had zero receipts and no established SMTP
acceptance; it was held without replay or replacement. Both mailbox monitors
were fresh, the current creation window was complete and pending replies were
zero. No actual creator interest or owner handoff was established.

The hourly heartbeat is active and its saved state was checked; its first
scheduled Codex wake remains unobserved. A manual six-GET snapshot and both
native daily scans succeeded. Discovery preserved ten active records, with all
four queued v2 bodies, digests and research snapshots unchanged in before/after
reads. These are separate proofs of manual inspection and native scheduling.

The recovery audit found seventeen actual SMTP acceptances from 05:18:23 through
05:19:39 UTC despite spaced reserved slots. The old due-time check did not
enforce actual cadence; the preceding 1,216-test/full-verifier checkpoint missed
that case. The deployed correction shares a database gate between approval and
the actual receipt boundary, applies the stricter frozen/current policy to
actual history and durably defers unstarted work without a receipt, spent
attempt, changed copy or extended expiry. An unresolved sending receipt blocks
further egress. See [ADR-0034](../decisions/ADR-0034-actual-smtp-pacing-and-durable-deferral.md).

The combined career/creator stack passed lint/all 1,321 tests and the complete verifier,
including concurrent overdue deferral, accepted/ambiguous/unresolved history,
frozen-policy limits, unchanged packet/attempt state, no-slot refusal and lease
or approval expiry after advisory-lock waits. Actual wait cases also checked
creator-run expiry, Gmail freshness, publication age, AI draft lifetime and
career-contact expiry without taking new locks under the global gate.
This is local PostgreSQL/native
proof, not a new external SMTP pacing canary. CI remains the publication gate.
