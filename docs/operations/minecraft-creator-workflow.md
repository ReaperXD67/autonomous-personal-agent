# Minecraft creator partnerships

Hermes researches Minecraft YouTubers, prepares a relevant compensation proposal,
tracks responses, and sends interested creators your email or Discord so you can
continue personally. The campaign workspace shows research evidence, pending
decisions, reply excerpts, exact outgoing messages, and delivery history together.

## The revenue-share offer

Choose **Paid promotion first** and **Share of attributable earnings**. Write a
truthful product summary and a collaboration idea, such as exploring different
Minecraft servers listed on the website and making original content about them.
Confirm the website's current features before sending any claim.

Percentage and duration are optional proposals. Leave them blank to ask each
creator which percentage and earning window in weeks they would like to discuss.
Channel size, fit, and content are evidence for the conversation; Hermes does not
invent a rate or decide compensation from subscriber count.

For illustration, **30% × €1,000 over two weeks = €300**. This is arithmetic,
not a forecast or an agreed offer. Those example numbers are not inserted into
emails unless the operator explicitly enters them in the campaign. The sender
explains that compensation depends on attributable earnings, with no guaranteed
upfront fee or income. Before any agreement, the owner and creator must define
whether earnings means revenue or profit, which costs count, attribution, the
start date, the earning window, reporting, and the payment schedule.

The KarixMC starter contact is **Discord: karixai**. Replace it for another owner.
An email address, Discord username, or both can be used. Discord is text in the
handoff email; Hermes does not log into Discord or send Discord DMs.

## What runs automatically

| Step | Behavior |
|---|---|
| Discover | Official YouTube searches find a bounded sample of channels and videos. Scheduled discovery is optional. Country and language can remain unrestricted. |
| Research | Source excerpts, activity, subscriber evidence, fit, content ideas, and public business-contact candidates are retained. Missing evidence stays visible. |
| Qualify | The operator checks the source and authorizes the exact business contact. Discovery cannot authorize recipients. |
| Introduce | Choose a campaign template, a source-grounded personalized draft, or your own copy for exact approval. A preparation batch can queue up to five eligible drafts; it grants no sending authority. Finite sending runs use templates for already-reviewed contacts. |
| Read replies | Optional Gmail adapter reads metadata/excerpts from one custom label. Sender and subject matching suggest the creator; classification is conservative evidence. |
| Review | Positive interest and uncertain replies require confirmation against the original message. Explicit opt-outs suppress further contact. Questions need a reviewed answer. |
| Handoff | After confirmed interest, prepare one owner-contact email. A run can separately authorize this handoff automatically. SMTP acceptance marks the conversation handed off. |
| Stop | Hermes sends no further sequence messages after handoff. You negotiate and continue. No automatic reminders, contracts, payments, or revenue collection are implemented. |

For ongoing operation, follow the [creator continuation runbook](creator-outreach-continuation.md).
It separates an hourly Codex reviewer loop from Hermes's daily official YouTube
discovery, five-minute eligible Gmail reads and existing paced action worker.
The selected operating scope is six new introductions per rolling day across
the two reviewed English/Polish campaigns, with a soft three/three split. This
does not enable a generic template-sending run or remove individual contact,
complete-copy, positive-reply and handoff review. Installation and actual run
results are recorded in the journal; a schedule alone is not operational proof.
The hourly heartbeat is active, with scheduled reviews observed since November
2, 2026, 06:20 UTC. Both native daily scans and compact review reads were
verified. Genuine local generation released the model hold and reviewed outreach
resumed; see the [dated checkpoint](#verified-reviewed-launch).

## Set up the campaign

1. Run `./scripts/promotion.ps1` for a secret-safe readiness report.
2. Open **Creator campaigns → Create paid campaign**. Review the product URLs,
   sender, collaboration brief, compensation model, and handoff contact.
3. Keep country/language unrestricted for broad discovery, or choose explicit
   limits. New dashboard campaigns accept the full subscriber range; hidden
   subscriber counts still cannot satisfy automatic-send eligibility.
4. Choose **Find Minecraft creators**. Inspect the research dossier and published
   contact source before using **Review contact**.
5. Choose **Prepare introduction** and inspect a campaign template, request an
   **AI personalized draft**, or write your own copy. Alternatively choose
   **Authorize outreach run** for bounded template introductions.
   The run requires explicit confirmation of its campaign, cap, expiry, and
   optional handoff authority. Saving a campaign never starts a send run.
6. Review replies in **Your next decisions**. Confirm interest with evidence,
   then prepare the handoff or let the explicitly authorized run prepare it.

Automatic introductions require observed Minecraft topic evidence, known audience
within the selected range, recent published content, current geography eligibility,
and an authorized unsuppressed email. Missing or stale evidence blocks the send.
Research is deterministic and spends no model tokens; it is not an assertion
that every relevant creator has been found or that a partnership will succeed.

## Refresh a shortlist without model calls

Discovery already uses the official YouTube Data API; it does not require
opening channels one by one in a browser. After discovery, expand a campaign's
**Research a creator shortlist**, choose a batch size of one to ten, and select
**Research shortlist**. The default is five. The worker refreshes a bounded
selection from the campaign's saved pool and checks up to three recent uploads
per creator, then ranks fit and shows source evidence, publication dates,
contact-review needs and gaps.

This step uses no model tokens, authorizes no contact and sends no email. The
global refresh allowance is thirty creators per rolling day. An upload's
publication date remains separate from the time research ran; declared country
does not establish content language or viewer location. A partial/provider
failure remains visible instead of looking like complete coverage.

The server selects uncontacted Minecraft candidates from the saved campaign.
Within the preceding 24 hours, it prefers creators without a genuine issued
research reservation, then those attempted least recently; public-contact
evidence and relevance break ties. This ordering and eligibility filtering
apply before the 500-candidate cap, so successive batches within that window
advance beyond the same high-relevance prefix. History must match its canonical
task-payload audit, current targeting snapshot and exact profile URL. Changed,
unissued or expired history cannot change current priority. Cancelled or failed
reservations still count as attempts and consume the existing budget.

The shortlist
requires a dated Minecraft publication within the campaign's age limit, capped
at ninety days, an observed subscriber count inside its range, current explicit
business-contact evidence and eligible declared targeting. **Selected** also
requires the exact current contact to have been authorized; **Needs review**
keeps that decision with the operator. These labels are research priorities,
not permission to send. One active batch per campaign and the global rolling
reservation limit also apply to failed or cancelled work.

The result persists as a normal audited task. Use **Refresh research status** or
return later. **Review creator evidence** opens the current contact dossier,
including for a creator outside the loaded shortlist page. **Draft introduction**
opens the separate AI review workflow for a selected, already-authorized contact;
it does not generate or send automatically. Browser spot checks remain useful
when source ownership or product claims are unclear, but they are not the
normal discovery or batch-research mechanism.

Routine bulk discovery now preserves existing research when an unexpired active
draft or exact outreach action protects it, including manual packets. The saved
campaign discovery summary exposes `protected_count`; protected rows are not
silently assigned fresh observation times. New creators and unprotected rows
continue normally. Explicit single-creator refresh remains intentional and can
invalidate the frozen copy. Neither this preservation nor the recurring reviewer
extends a draft/approval deadline or overrides withdrawal and final send guards.
See [ADR-0033](../decisions/ADR-0033-preserve-active-creator-evidence-during-discovery.md).

API clients can queue the same bounded job with
`POST /v1/marketing/campaigns/{id}/pilot-research`, an actor, UUID idempotency key
and `limit` of one to ten. `GET` on that route returns the latest task; normal
task endpoints provide durable status and audit history. This is a research
capability, not an unrestricted Hermes tool connection.

## Source-grounded introductions

New personalized drafts use a bounded planning contract: the model chooses an
issued video-evidence ID and one offered content-angle ID. Hermes writes the
English/Polish opening, optional proposal, operator explanation and complete
email from authored wording, the recorded title and your reviewed brief. It
does not accept model-written factual prose on this path. The exact title is
quoted with its public link; the proposed episode is separate from the unseen
video. Title keywords offer possible angles, not proof of a video's contents,
server support, audience preferences or likely interest.

This replaces the free-copy contract for new drafts after review of the November
1 launch retained one AI email and required twenty-three manual replacements.
Historical drafts keep their original context, parser, complete copy and digest.
The new contract narrows the factual surface; its presence is not certification
of a truthful brief or a useful proposal. Inspect the complete email.

The November 2 real canary completed five v2 drafts through local `qwen3:8b`,
including English and Polish and the earlier rejected Polish security-claim
case. Complete-copy review found all five usable without manual rewriting.
The two preparation parents each issued two children and completed with no
skips. These five cases are a small sample, not a matched comparison with the
previous launch or proof of general accuracy, inbox placement or replies.

Within **Prepare introduction**, select **AI personalized draft · review required**
and choose **Generate personalized draft**. Drafting runs asynchronously through
the existing task and research-worker path. You can close the dialog and return;
the latest saved draft and its status are loaded when you select AI again.
Drafting requires a reviewed authorized contact, observed Minecraft topic
evidence, a valid sampled video, and research no older than seven days. The
drafting budget is at most three requests per creator and thirty globally per
rolling day; these are separate from send limits.

The model receives sanitized product metadata, the sampled video title and URL,
observed topics and subscriber count, offered angle IDs, and campaign-scoped
reviewed aggregate feedback. Recipient addresses, raw descriptions and raw inbox
text are excluded. The server derives the explanation from the selected plan;
observed reach can affect optional scope, never pay or a promise of views.
English and Polish are supported output contracts. Preferred
or strict targeting selects the base of the campaign's `target_language`, such
as `pl` or `pl-pl`; unrestricted language selection defaults to English.
Unsupported explicit languages stop before inference. The selected
`output_language` is frozen in the stored model context, and legacy drafts
without that field remain English. New server-authored openings and ideas use
the selected language; the operator explanation and wire keys remain English.

For a Polish email, first supply an operator-reviewed Polish product summary,
paid-offer description and optional revenue basis. The server inserts those
fields verbatim and does not translate commercial claims or terms. It supplies
Polish framing and next steps, while deliberately retaining the existing
English contact-source, privacy and opt-out footer. Inspect the complete
mixed-language envelope before individual exact-message approval.

The review identifies the angle-selection model separately from server-authored
wording and shows the selected plan, source, complete copy and quality notes.
Provenance binds the source title/URL, generation language, context and campaign.
Before saving or preparing v2 copy, Hermes rederives it and rejects changed
wording or provenance. A named SMP, mod, edition or feature in a title never
establishes that the website supplies it. Prerequisites and the creator's own
verdict remain part of reviewing a proposed independent test.

The existing free-only hosted route and local fallback remain bounded by the
inference ledger. Local v2 selection disables reasoning output and uses a
512-token generation cap. One invalid-output correction is allowed, with a
separate inference reservation and lease/cancellation/context checks; rejected
text is neither retained nor echoed into the prompt. Transport failures do not
receive this repair. `CREATOR_DRAFT_OUTPUT_INVALID` means responses failed the
selection contract; `CREATOR_DRAFT_MODEL_UNAVAILABLE` means no usable model
response was available. Neither silently creates fallback copy or an email.
Templates and manual writing remain explicit alternatives.

New drafts freeze the concise permission-first render version. It quotes the
selected public title once, offers one optional creator-controlled idea and asks
whether an independent test is worth discussing. The product summary, paid-offer
description and revenue basis remain verbatim; commercial terms and the standard
footer remain deterministic. Long briefs can still make long emails. Earlier v2
and legacy contexts retain their original rendering and digest. Silence is not
reviewed feedback, and this strategy is an experiment rather than a proven reply
improvement.

The individual draft API accepts `inference_mode: "local_only"` alongside the
ordinary actor and UUID idempotency key. This explicitly selects the configured
local model, skipping all hosted inference, while retaining the same medium-risk
task, lease checks, thirty/day and three/creator preparation limits and inference
ledger. Omit it for existing automatic routing. Reusing a key with a different
mode is refused; batch children retain automatic routing. Draft reads expose the
mode for review. This is useful for a genuine local recovery canary without
changing shared provider configuration. A ready draft still cannot send itself.

Grounded local inference has a fixed 300-second socket response timeout; legacy
copy retains 180 seconds. A real cold request took 170.384 seconds versus 2.642
seconds warm, motivating extra cold-start headroom. This is not a strict task
wall-clock deadline; independent heartbeat renewal and post-inference expiry,
context and cancellation checks remain. Response size, v2 tokens and invocation
counts are unchanged. It requires a complete stopped response and records separate fixed timeout,
connection, missing-model, busy, HTTP, malformed, oversized and incomplete-response
codes in the inference ledger. A broken response read terminates the draft
rather than leaving it apparently queued. There is no automatic transport retry
or replacement prose. The public draft error remains model-unavailable; inspect
the linked inference diagnostic for the narrower failure. A completed local-only
task and its valid saved copy establish generation; container health does not.
See [the recovery decision](../decisions/ADR-0036-creator-local-recovery-and-permission-strategy.md)
and [upstream comparison](../research/creator-model-recovery-and-permission-outreach-2026-11.md).

The draft review shows computed editorial findings and the complete-email word
count before preparation. Older responses without a report display an explicit
unavailable fallback. The authenticated draft API returns the full `quality_report`
on existing draft reads. It flags observable English/Polish wording markers, a
stored output-language contract that differs from the campaign request,
platform security-verification claims, feedback claims with zero reviewed creators,
missing source/next-step markers, and rendered emails over 250 words. The rendered
count includes terms/footer; the compatible hook/idea count covers server-authored
fields on v2 and model suggestions on legacy drafts.
Quoted title numbers are evidence, not invented commercial terms. Findings are
displayed as plain escaped text, alongside the existing quality notes.
There is no overall score or confidence estimate. The report does not rewrite
copy, change its digest, persist a review, block preparation or grant authority.
The language marker records the generation contract rather than detecting or
certifying the text's actual language. Naturalness, translation, truthful
relevance and semantic accuracy still require review. A directory listing alone
does not establish a capability to verify server safety; narrow wording guards
cannot catch every unsupported claim. Inspect the original copy even when its
editorial report has no findings. See the
[editorial evaluation decision](../research/creator-outreach-intelligence-2026-10.md)
and [grounded-generation comparison](../research/creator-grounded-generation-2026-11.md).

**Prepare exact AI email** binds the saved draft digest to the ordinary email
approval packet. It does not send the email or approve its own output. Changed
campaign/contact/research context or a draft older than 24 hours requires a fresh
draft. The final
packet retains required commercial wording and the contact-source, privacy and
opt-out footer. Sending follows the same exact approval, pacing, duplicate and
suppression checks as other creator emails.

AI copy is an individually reviewed workflow. Authorizing a creator run does not
authorize arbitrary model-generated messages; those runs keep the bounded
template path. Better relevance can reduce avoidable objections, but acceptance
depends on the creator, offer and timing. No response or collaboration rate is
guaranteed.

## Prepare several drafts together

Expand **Prepare personalized drafts in a batch**, choose one to five drafts
(default three), then select **Prepare draft batch**. This queues a normal
medium-risk preparation task, not an outreach run. Hermes selects eligible
creators with reviewed unsuppressed business contacts and fresh evidence, then
issues separate drafting tasks. **Refresh draft queue** shows each reserved,
queued, ready, failed, stale or skipped item and links to its individual review.

The batch shares the existing thirty-preparations-per-rolling-day and
three-per-prospect limits with individual requests. Genuine unmaterialized
reservations remain counted after cancellation or failure; materializing their
own matching children does not count twice. Stable membership and UUID child
keys make resume safe. Batch selection deduplicates canonical channel/profile
identity and exact normalized business email across active drafts, issued
reservations and its own selected items, including other campaigns.

Changed campaign/research/contact context, withdrawn eligibility, suppression or
an existing current draft can produce a durable per-item skip. Resuming does
not reopen that skip. Cancellation stops remaining issuance; already queued
drafts have their own task and require separate cancellation. Expired leases,
unissued caller tasks and modified parent payloads cannot issue children.
Neither the parent nor its children authorize a contact, create an outgoing
packet or approve a message. Review each complete result and use the normal
exact-message preparation and approval steps before any send.

API clients use `POST /v1/marketing/campaigns/{id}/draft-batches` with `actor`,
a UUID `idempotency_key` and `limit` from one to five. `GET` on that route returns
the latest issued overview; `GET /v1/marketing/draft-batches/{task_id}` returns
one batch. Ordinary task cancellation applies to the parent. These authenticated
routes preserve the same policy, outbox and PostgreSQL audit boundary.

## Automatic-run boundaries

- Default: three introductions per rolling 24 hours, valid for 24 hours.
  Maximum: ten introductions per rolling day and seven days of authority.
- Only template first approaches and explicitly enabled owner handoffs qualify.
  AI introductions, questions and custom messages retain individual exact-action
  approval.
- PostgreSQL records the run, exact action reservation, digest, recipient,
  approval, and outcome. Duplicate recipient/creator stages cannot be scheduled
  again across campaigns. Failed or uncertain automated reservations remain counted.
- SMTP pacing is shared with every outgoing email: default 15-minute global and
  30-minute same-domain spacing, three/hour and twelve/day, plus jitter. Handoffs
  also use this pacing. Mailpit is an immediate local sink.
- Pause, expiry, campaign changes, changed contact evidence, suppression, pending
  reply review, and stale required mailbox sync prevent new execution. A message
  already past the final send boundary can complete; Pause cannot recall it.
- A changed brief or owner contact requires a new run and newly prepared exact
  packets. Legacy pending creator packets must be prepared again to acquire the
  new campaign/contact snapshot checks.

The shared SMTP daily capacity is configured by
`OUTBOUND_EMAIL_DAILY_LIMIT` in ignored local configuration; its repository
default is twelve. The supported value must be at least the configured hourly
limit and at most fifty. This is a shared capacity bound for all SMTP messages,
including handoffs and career mail; it does not qualify contacts, approve copy
or raise a creator run's separate ten-initials-per-day maximum. After an
authorized configuration change, reload the affected services and inspect
`GET /v1/communications/status` plus the exact packets' reserved release times.
Approved work still has to fit within its expiry and pass the final send guards.

## Learning from real replies

In **Record reply or result** or **Review a creator reply**, select only objections
supported by the message. Eight tags cover generic pitches, unclear offers,
revenue-share confusion, fixed-fee preferences, content mismatch, attribution,
length and next steps. Gmail can suggest tags; none is selected or learned
automatically. Silence is not an explanation for rejection.

English and Polish hints recognize common objections, including revenue-share
percentage/window questions and fixed-fee preferences. A bounded normalized
view strips recognizable quoted/forwarded history and our opt-out instructions;
the stored original excerpt is unchanged. Negated or conditional interest and
quoted phrases remain review cases. Normalization is a heuristic, not a full
translation or proof of intent. Always review the original reply before
confirming interest or applying feedback tags.

The campaign's **What creators are teaching us** report counts distinct creators,
shows each objection and its recommended change, and explains future draft
selection. Repeated outcomes from one creator do not inflate the evidence.
Three distinct reviewed creators supporting one direction can establish a copy
hypothesis. All three strategies need at least ten accepted introductions each,
with a five-percentage-point and 1.5× lead over the runner-up, before Hermes
prefers an observed performer. These are operational heuristics, not statistical
proof: creator mix and timing can affect outcomes.

With adaptive copy enabled, 80% of future assignments favor the recommended
strategy and 20% explore alternatives. These are deterministic assignment
buckets, not exact quotas for small batches. Content-first leads with observed
video evidence, terms-first moves the proposal forward, and concise removes
repetition. Contact-source, privacy, opt-out and commercial caveats remain.
Turn off adaptive copy to keep balanced assignment while retaining the report.

Learning is campaign-scoped and uses durable reviewed outcomes and accepted
messages. It does not retrain model weights, rewrite its code, modify existing
approved packets, invent creator facts, increase send caps, change compensation,
or guarantee collaborators. A fixed-fee preference is an owner decision.
Historical campaign results are observational and can include earlier briefs;
review that context before interpreting a preference. Revenue attribution and
payout accounting are not implemented.

## Optional Gmail reply monitoring

SMTP sending and Gmail reading are separate integrations. Follow the
[Gmail setup guide](gmail-setup.md) to connect the owner's Desktop OAuth client
using `./scripts/gmail-oauth.ps1`. It requests exactly
`https://www.googleapis.com/auth/gmail.readonly`, verifies the mailbox and
label, then atomically saves the credentials in ignored local configuration.
The resulting reader configuration includes:

```dotenv
CREATOR_GMAIL_ENABLED=true
GMAIL_CREATOR_LABEL=Hermes/Creators
CREATOR_GMAIL_MAILBOX=your-monitored-sender@example.com
```

Create that custom label in your own mailbox and arrange for creator replies to
receive it. The adapter does not create filters or labels. Restart the control
API and research worker to load configuration. Credentials belong only in ignored
local configuration and are passed only to the research worker.

With creator Gmail enabled, the scheduler can queue read-only syncs for campaigns
with successfully sent marketing outreach in the previous 180 days, no more often
than once every five minutes. A sending grant is not required for that monitoring;
expired grants are not renewed. A generic SMTP self-test is not a marketing
outreach record and does not activate this rule. This is implemented scheduling
behavior; actual reply ingestion still needs its own live proof.

Choose **Check creator replies** and inspect the result. A configured flag is
not operational proof. Complete a real labeled-reply canary with an inbox you own
before relying on monitoring. The adapter validates mailbox identity, uses bounded
pages and durable cursors, and does not fetch attachments or follow message links.
OAuth grants mailbox-wide read access; the custom-label restriction is enforced
by the application, not by Google OAuth. See Google's
[message-list guide](https://developers.google.com/workspace/gmail/api/guides/list-messages)
and [message metadata reference](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get).

A run started with Gmail monitoring requires a completed sync within 30 minutes.
New unreviewed replies stop further campaign sending. Positive snippet matches
never authorize a handoff on their own: quoted text, ambiguous intent, and partial
excerpts need the operator's review. Without Gmail, record responses manually;
Hermes does not claim to watch an unconnected inbox.
Recognizable quoted/forwarded history and the outgoing opt-out instruction are
excluded from direct opt-out detection. This remains conservative excerpt parsing;
inspect the full message when context is incomplete.

An invalid or expired OAuth refresh grant means reading is unavailable even when
settings are present. Complete the [explicit renewal flow](gmail-setup.md#expiry-and-recovery),
reload the reader and pass a new governed sync. SMTP can remain authenticated
independently; a successful send does not prove reply monitoring.

## Verified reviewed launch

At the November 1, 2026 launch checkpoint, twenty-four distinct invitations had
individual contact authorization and exact-message approval: sixteen English and
eight Polish. Of twenty-four model tasks, nineteen returned copy and five failed
with `CREATOR_DRAFT_MODEL_UNAVAILABLE`; all nineteen successful results reported
local Ollama `qwen3:8b`. Source and product review retained one
exact AI draft and used twenty-three explicitly reviewed manual replacements.
Those replacements are operator decisions, not creator feedback or evidence that
the model learned from replies.

At November 3, 2026, 09:10 UTC (14:40 IST), the reviewed scope comprised the
original twenty-eight invitations plus two new ones: twenty-eight SMTP-accepted,
one paced queued task and one unchanged dead-lettered blocked item. The latter
had no established acceptance and was not replayed or replaced. The out-of-window
regression draft remains held. Twelve earlier acceptances are separate.

All four subsequent grounded v2 invitations, two English and two Polish, were
SMTP-accepted with their individually reviewed copy unchanged. Each successive
acceptance was more than 1,800 seconds apart in this small actual-send pacing
canary. This does not establish
general cadence, inbox placement or a response-rate guarantee.

Native scheduled discovery completed both campaign scans at approximately
05:21 UTC: 178 researched records, twenty-nine new, 139 updated and ten protected,
with forty-one business-contact candidate observations and zero automatic
authorizations. These are record observations across campaigns, not unique
people or qualified leads. Before/after reads confirmed that all four queued
v2 bodies, digests and research snapshots remained unchanged. A six-GET manual
review snapshot confirmed fresh monitoring for both campaigns and a complete
current creation window. Scheduled hourly reviews have been observed since
06:20 UTC. At the 19:57 UTC checkpoint both label monitors were fresh, with zero
pending replies, confirmed creator interest or owner handoffs.

The November 2 unavailable-model failure was preserved, without a replacement
packet or manual fallback. Following explicit maintenance, two separately
budgeted local-only Qwen drafts completed cold/warm in 170.384/2.642 seconds,
each on its first invocation. GPU inspection showed all layers offloaded and
100% GPU placement with an 8,192-token context. Complete-copy review retained
both new English introductions unchanged at 212 and 204 words, including terms
and footer. The availability hold was released. The first was SMTP-accepted;
the second was reserved for 09:39:47 UTC (15:09:47 IST), within its existing
approval expiry. That reservation is scheduled work, not delivery evidence.
Both label monitors were fresh with no pending replies; no actual creator
interest or handoff was established. The new strategy has no measured reply-rate
advantage. One Polish candidate was excluded because fresh activity research
failed; old metadata was not promoted to a lead or padded into the batch.

The local shared bound remains twenty-four/day, three/hour, 900-second global
and 1,800-second same-domain gaps plus up to 180 seconds of jitter. The repository
default remains twelve/day. Keep the computer, Docker and the desktop app
running; queued releases still depend on their expiry and final guards.
Individual approval and SMTP acceptance are not inbox-placement or reply proof.
Actual creator-reply matching/replay, owner handoff and Google's Testing-mode
refresh-token longevity remain operating limits.

The final recovery audit found seventeen actual SMTP acceptances between
05:18:23 and 05:19:39 UTC on November 2. Those were real acceptance times, not
reserved-slot timestamps. The reserved schedule had been spaced, but the send
boundary only rejected future slots, allowing multiple overdue slots to execute
together after recovery. The intended spacing/hourly policy was therefore not
enforced in that event. The deployed correction shares a database gate between
approval and actual receipt acquisition, applies the stricter frozen/current
policy to actual sending/accepted/ambiguous history, and durably defers unstarted
work without consuming its attempt, changing approved copy or extending expiry.
The earlier combined career/creator stack passed lint/all 1,321 tests and the complete
verifier, with concurrent/expiry/lock-wait PostgreSQL pacing proofs and time-
dependent scope rechecks after the pacing gate. The preceding 1,216-test
checkpoint missed this case. The four later spaced acceptances are the limited
live canary described above; this checkpoint adds no runtime behavior.
An overdue slot or queued action label alone does not prove safe, runnable work.

## Test before real outreach

Complete the [owned-inbox launch proof](creator-outreach.md#prove-an-owned-inbox-launch)
after configuring real SMTP. Saved settings, authenticated NOOP, durable message
acceptance, actual inbox receipt and labeled-reply replay are separate results.
The owned test shares the normal external-send pacing and never counts as a
creator lead or feedback sample.

```powershell
docker compose config --quiet
./scripts/test.ps1
./scripts/verify.ps1
./scripts/creator-outreach-smoke.ps1 -PaidHandoff
git diff --check
```

The complete verifier includes disposable PostgreSQL creator-automation,
grounded/legacy-draft and preparation-batch proofs, API-shortlist proofs, and
network-free native OAuth and SMTP-setup
regression checks. Its networkless creator-review browser proof checks the actual
desktop/mobile UI, escaping, missing-report fallback, draft queue and provenance,
and unchanged exact-action preparation behavior.
The draft proof uses synthetic model output, so it does not establish that a
configured external or local model is responding.
The paid-handoff smoke uses synthetic contacts and Mailpit: introduction,
confirmed interest, owner email/Discord handoff, terminal duplicate refusal,
and opt-out suppression. Test containers receive no saved SMTP credentials.
These tests do not establish external SMTP inbox placement, Gmail OAuth readiness,
YouTube coverage, attribution accuracy, revenue, or commercial agreement.

For provider setup and delivery limits, see [creator outreach operations](creator-outreach.md).
For the authority boundaries, see [ADR-0025](../decisions/ADR-0025-creator-partnership-handoff.md)
and [ADR-0030](../decisions/ADR-0030-grounded-creator-plans-and-draft-batches.md).
