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
| Introduce | Prepare one exact email for individual approval, or authorize a finite run for already-reviewed contacts. Revenue-share wording uses the campaign's explicit terms. |
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
5. Prepare and inspect an introduction, or choose **Authorize outreach run**.
   The run requires explicit confirmation of its campaign, cap, expiry, and
   optional handoff authority. Saving a campaign never starts a send run.
6. Review replies in **Your next decisions**. Confirm interest with evidence,
   then prepare the handoff or let the explicitly authorized run prepare it.

Automatic introductions require observed Minecraft topic evidence, known audience
within the selected range, recent published content, current geography eligibility,
and an authorized unsuppressed email. Missing or stale evidence blocks the send.
Research is deterministic and spends no model tokens; it is not an assertion
that every relevant creator has been found or that a partnership will succeed.

## Automatic-run boundaries

- Default: three introductions per rolling 24 hours, valid for 24 hours.
  Maximum: ten introductions per rolling day and seven days of authority.
- Only generated first approaches and explicitly enabled owner handoffs qualify.
  Questions and custom messages retain individual exact-action approval.
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

SMTP sending and Gmail reading are separate integrations. Configure existing
`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, and `GMAIL_REFRESH_TOKEN` locally with
exactly `https://www.googleapis.com/auth/gmail.readonly`, then set:

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

The complete verifier includes a disposable PostgreSQL creator-automation proof.
The paid-handoff smoke uses synthetic contacts and Mailpit: introduction,
confirmed interest, owner email/Discord handoff, terminal duplicate refusal,
and opt-out suppression. Test containers receive no saved SMTP credentials.
These tests do not establish external SMTP inbox placement, Gmail OAuth readiness,
YouTube coverage, attribution accuracy, revenue, or commercial agreement.

For provider setup and delivery limits, see [creator outreach operations](creator-outreach.md).
For the authority boundary, see [ADR-0025](../decisions/ADR-0025-creator-partnership-handoff.md).
