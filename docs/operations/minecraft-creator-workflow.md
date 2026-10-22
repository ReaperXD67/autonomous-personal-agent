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
| Introduce | Choose a campaign template, an AI personalized draft, or your own copy for exact approval. Finite runs use generated template introductions for already-reviewed contacts; AI drafts retain individual review. Revenue-share wording uses the campaign's explicit terms. |
| Read replies | Optional Gmail adapter reads metadata/excerpts from one custom label. Sender and subject matching suggest the creator; classification is conservative evidence. |
| Review | Positive interest and uncertain replies require confirmation against the original message. Explicit opt-outs suppress further contact. Questions need a reviewed answer. |
| Handoff | After confirmed interest, prepare one owner-contact email. A run can separately authorize this handoff automatically. SMTP acceptance marks the conversation handed off. |
| Stop | Hermes sends no further sequence messages after handoff. You negotiate and continue. No automatic reminders, contracts, payments, or revenue collection are implemented. |

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

The server selects uncontacted Minecraft candidates from the saved campaign,
preferring existing public-contact evidence before relevance. The shortlist
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

API clients can queue the same bounded job with
`POST /v1/marketing/campaigns/{id}/pilot-research`, an actor, UUID idempotency key
and `limit` of one to ten. `GET` on that route returns the latest task; normal
task endpoints provide durable status and audit history. This is a research
capability, not an unrestricted Hermes tool connection.

## A model-written introduction for each creator

This drafting mode is experimental. Local lifecycle and interface tests pass,
and the configured local model has returned real responses, but live review has
not established usable creator-specific copy. Failed validation stops the draft;
use the separately reviewed manual or template path when appropriate.

Within **Prepare introduction**, select **AI personalized draft · review required**
and choose **Generate personalized draft**. Drafting runs asynchronously through
the existing task and research-worker path. You can close the dialog and return;
the latest saved draft and its status are loaded when you select AI again.
Drafting requires a reviewed authorized contact, observed Minecraft topic
evidence, a valid sampled video, and research no older than seven days. The
drafting budget is at most three requests per creator and thirty globally per
rolling day; these are separate from send limits.

The model receives the campaign's product summary, the creator's sampled video
title, public video URL, observed topics and subscriber count, and campaign-scoped
reviewed aggregate feedback. Recipient addresses, raw descriptions and raw
inbox text are excluded. It proposes an opening
and a content idea, explains the approach and how the observed reach influenced
the format, and cites recorded evidence. Reach is not a payment formula or a
promise of views. The first version writes English copy; translated pitches are
not implemented.

The review shows the actual model and source, complete message, evidence links,
quality notes, and feedback context. Inspect those sources and confirm that the
idea matches what the website can actually offer. The existing free-only hosted
model route and local fallback are used; neither route has authority to contact
the creator. The local creator model can reason internally within a bounded
request; only its final copy and explicit operator rationale are saved. Internal
reasoning traces are discarded. Invalid local output can trigger one bounded
regeneration from the
same evidence and a fixed validation hint; rejected text is neither retained nor
fed back into the prompt. Each attempt reserves inference separately and rechecks
the task's lease, cancellation and context. Transport failures are not retried
by this repair step. If no attempt passes, the draft stays visibly failed.
Choosing a template is a separate, explicitly labeled option.

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

## Learning from real replies

In **Record reply or result** or **Review a creator reply**, select only objections
supported by the message. Eight tags cover generic pitches, unclear offers,
revenue-share confusion, fixed-fee preferences, content mismatch, attribution,
length and next steps. Gmail can suggest tags; none is selected or learned
automatically. Silence is not an explanation for rejection.

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

## Test before real outreach

```powershell
docker compose config --quiet
./scripts/test.ps1
./scripts/verify.ps1
./scripts/creator-outreach-smoke.ps1 -PaidHandoff
git diff --check
```

The complete verifier includes disposable PostgreSQL creator-automation,
AI-draft and API-shortlist proofs, plus network-free native OAuth and SMTP-setup
regression checks.
The draft proof uses synthetic model output, so it does not establish that a
configured external or local model is responding.
The paid-handoff smoke uses synthetic contacts and Mailpit: introduction,
confirmed interest, owner email/Discord handoff, terminal duplicate refusal,
and opt-out suppression. Test containers receive no saved SMTP credentials.
These tests do not establish external SMTP inbox placement, Gmail OAuth readiness,
YouTube coverage, attribution accuracy, revenue, or commercial agreement.

For provider setup and delivery limits, see [creator outreach operations](creator-outreach.md).
For the authority boundaries, see [ADR-0025](../decisions/ADR-0025-creator-partnership-handoff.md)
and [ADR-0026](../decisions/ADR-0026-reviewed-creator-ai-drafts.md).
