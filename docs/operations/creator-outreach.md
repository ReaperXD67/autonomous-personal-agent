# Creator outreach operations

The **Creator campaigns** workspace turns a KarixMC promotion strategy into a
low-volume, reviewable funnel. It discovers relevant public YouTube channels,
helps an operator qualify a public business contact, prepares exact email
actions, records replies/results, and suggests evidence-based changes.

It does not scrape emails, read a mailbox, send in bulk, post publicly, negotiate
or pay creators, issue KarixMC points, or approve its own messages.

## 1. Configure official YouTube discovery

Create a user-owned Google Cloud project, enable YouTube Data API v3, and create
an API key following the [official YouTube Data API setup](https://developers.google.com/youtube/v3/getting-started).
Restrict the key to YouTube Data API v3 and, when the deployment has a stable
egress address, restrict the source IP. Put only this value in ignored `.env`:

```dotenv
YOUTUBE_API_KEY=your-restricted-key
```

The key is passed only to `job-worker`, the existing research runtime with edge
access. It is absent from the control API, normal worker, dispatcher, browser/
SMTP worker, task payloads, audit metadata, and dashboard.

YouTube currently documents a dedicated `search.list` bucket of 100 calls per
day, with each search costing one unit in that bucket, and a maximum of 50
results per request. Hermes uses no more than three queries and 25 results per
query, schedules no faster than daily, and caps discovery at 30 tasks per 24
hours (at most 90 search calls). `channels.list` supplies public channel
statistics; it does not supply a business email.

The guided command validates the key against one harmless official channel
lookup, then writes it only to ignored `.env` without echoing it:

```powershell
./scripts/promotion.ps1 -ConfigureYouTube
```

## 2. Create the KarixMC campaign

Open the loopback dashboard, connect, then select **Creator campaigns → Create
campaign**. The defaults describe the current product as a verified Minecraft
reward network where active play earns portable points across funded servers.

Before saving, verify:

- sender name and `https://karixmc.pl/` product/privacy links;
- a truthful product summary that does not claim exclusivity or guaranteed
  earnings;
- the exact free viewer-points offer KarixMC can fulfill;
- the exact server/community offer KarixMC can fulfill;
- the paid-collaboration description, if enabled;
- up to three narrow Minecraft queries, language/region, creator-size range,
  and recent-video window.

Activating the campaign schedules daily or weekly discovery. **Find creators**
queues one immediate low-risk task. Results show channel name, profile, public
subscriber count when visible, one matching recent video, query evidence, and a
deterministic relevance score.

## 3. Qualify a contact

YouTube discovery intentionally leaves the email blank. Use **Review contact**
only after a human finds an address explicitly published for business or
collaboration inquiries. Record:

1. the exact email;
2. the public HTTPS page where it was published;
3. a short note explaining why this one-to-one proposal is permitted and
   relevant; and
4. the operator authorization checkbox.

Do not add guessed addresses, personal addresses, hidden About-page data,
purchased/enriched lists, or contacts collected for another incompatible
purpose. The European Commission explains that direct-marketing data needs a
lawful ground, first-contact transparency, compliance with ePrivacy rules, and
immediate respect for objections. See its [business guidance on marketing data](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/legal-grounds-processing-data_en).
Obtain local legal advice for the countries and contact types actually used.

## 4. Use the free promotion kit

Select **Promotion kit** on any campaign. The control API deterministically
builds five copy-and-paste assets from the exact reviewed product, audience, and
offer fields:

- YouTube video description and community post;
- Discord community post;
- Reddit or similar community post; and
- partner newsletter/blog paragraph.

Every asset receives its own `utm_id`, source, medium, campaign, platform, and
content parameters. This follows [Google Analytics' campaign URL guidance](https://support.google.com/analytics/answer/10917952?hl=en)
and lets KarixMC distinguish channels after first-party attribution is wired.
The kit does not call an LLM, use a quota, create an account, or post anywhere.
Read each destination's self-promotion rules, edit for context, and disclose any
payment, free benefit, or other material relationship.

## 5. Run the email sequence

Every step creates one frozen sender/recipient/subject/body action in
**Approvals**. Nothing is sent until that exact action is approved. Open the full
packet to review sender, recipient, subject, body, expiry, and context digest;
approve from that review. A prospect's latest-message links open its exact packet
and task audit, including messages outside the most recent list page.

1. **Prepare introduction** explains the reward-network model, offers the
   configured viewer and creator/server pilot, asks for an honest collaboration,
   includes a per-prospect UTM link, identifies the contact source, and provides
   a direct opt-out.
   Optionally supply both a personalized subject and body. The server retains
   the contact/privacy/opt-out footer, marks the message `manual_initial`, and
   excludes it from template A/B learning. It retains the same sequence,
   suppression, digest, expiry, and approval requirements. Paid-offer terms
   remain generated from the reviewed campaign packet.
2. Record the reply manually. If it is a question, select **Asked a question**,
   then **Write manual answer**. Write only verified facts; the system adds the
   provenance/opt-out footer and creates another exact approval.
3. Record an ordinary or ambiguous “no” as **No / do not contact**. That address
   is durably suppressed and any pending approval becomes non-executable.
4. Choose **Declined only because it was unpaid** only when the creator actually
   communicated that specific condition. It unlocks one final paid-option
   draft. The message says it is final and does not imply an agreed fee or scope.

The action worker rechecks the owned unexpired lease, cancellation, exact frozen
context, contact authorization, suppression, and reply state immediately before
SMTP submission. A bounce or opt-out clears contact authorization and cannot be
reversed through the dashboard. Connection/TLS/login failures occur before a
receipt is created. After submission begins, uncertain acceptance remains
`ambiguous`: inspect the provider's records before preparing another message.
Known SMTP acceptance is saved before connection cleanup and survives a later
task-completion failure. **Sent to mail server** does not prove inbox delivery.

For external SMTP, approval also reserves a durable send time. Defaults allow no
more than one message every 15 minutes, one message to the same recipient domain
every 30 minutes, three in any rolling hour, or twelve in any rolling 24 hours;
up to three minutes of deterministic jitter avoids a mechanical cadence. The
dashboard shows the reserved time. PostgreSQL and the delayed outbox preserve it
across a process or VPS restart. If the safe time is later than the packet's
expiry, approval stops and asks you to prepare the message later. Mailpit remains
immediate because it is a local test sink.

## 6. Record results and adapt

Use **Record reply or result** to capture question/interest/decline state,
published placement URL, attributed views/clicks/signups/server owners, and
viewer points actually issued. Do not enter projections as results.

The dashboard shows the linear funnel and two introduction variants. For fewer
than ten SMTP-accepted introductions, the agent recommends collecting evidence.
Only after both variants have ten SMTP-accepted emails can a variant win. It must
lead positive-reply rate by at least five percentage points and 1.5×; then 80%
of future drafts use it while 20% continues exploration. High suppression,
question, or unpaid-decline rates produce stop/review suggestions.

These are associations, not proof of causation. The agent never changes an
offer, budget, contact, policy, code, or approval. An operator decides whether a
suggestion justifies editing the campaign.

## 7. Enable real delivery

First prove the complete creator path with synthetic data and Mailpit:

```powershell
./scripts/promotion.ps1 -LocalTest
```

This test creates an inactive synthetic campaign and reviewed synthetic contact,
builds five attributed promotion assets, prepares and approves one introduction,
verifies it in Mailpit, records an opt-out, proves further outreach is refused,
and removes its durable records. It does not call YouTube or external SMTP. Any
saved SMTP username/password is explicitly omitted from the test containers.

Run `./scripts/side-effect-smoke.ps1` as the broader application-and-email proof
when you also want to test the isolated ATS adapter and duplicate-submit guard.

Pacing prevents bursts; it cannot force a mailbox provider to place a message
in the inbox. Before contacting any creator, configure the sending domain with
your provider and DNS host:

1. publish exactly the SPF record your provider documents;
2. enable DKIM signing and publish the provider-issued DKIM record;
3. publish DMARC, begin with monitoring, inspect reports, and tighten the policy
   only after SPF/DKIM alignment is correct;
4. make `SMTP_FROM` a real monitored address on that authenticated domain and
   keep the visible From domain aligned with SPF or DKIM;
5. send one canary to an inbox you own, inspect the received authentication
   results, and reply to it before any creator send;
6. keep the default low volume, contact only relevant public business addresses,
   monitor bounces/complaints, and record every objection immediately.

Google requires authentication for all senders, recommends consistent gradual
volume instead of bursts, and says spam reports should remain below 0.1% and
never reach 0.3%; see its current
[email sender guidelines](https://support.google.com/mail/answer/81126?hl=en).
Yahoo likewise requires authentication and low complaints and documents easy
unsubscribe requirements for marketing/bulk mail in its
[sender best practices](https://senders.yahooinc.com/best-practices/).

Hermes' one-to-one creator messages already include a direct opt-out and durable
suppression. Do not scale this into subscription or bulk marketing. That would
require a real public RFC 8058 one-click unsubscribe endpoint, automated
complaint/bounce ingestion, and a separate legal/provider review; Hermes does
not invent a non-functional unsubscribe header.

For Gmail or Google Workspace, first enable two-step verification and create a
user-owned [app password](https://support.google.com/accounts/answer/185833?hl=en).
Google states that app passwords require two-step
verification, may be unavailable for organization-managed or Advanced
Protection accounts, and recommends OAuth when available; this deployment does
not yet hold mail OAuth tokens. The guided hidden prompt writes the fixed
`smtp.gmail.com:587` STARTTLS settings only to ignored `.env`:

```powershell
./scripts/promotion.ps1 -ConfigureGmail
./scripts/promotion.ps1 -OpenDashboard
```

For an existing provider, use the generic local prompt. Enter credentials only
at its hidden password prompt, never in dashboard fields or chat:

```powershell
./scripts/promotion.ps1 -ConfigureSMTP
./scripts/up.ps1 -SideEffects
./scripts/promotion.ps1 -CheckSMTP
```

Setup writes the SMTP fields together to ignored `.env`, preserving unrelated
settings and literal credential characters. **Settings → Email setup** shows
configured transport and the latest timestamped worker check. The medium-risk,
single-attempt `communications.smtp_check` task uses the usual policy/audit/outbox
path and fixed deployment settings. It checks connection, TLS, authentication
when configured, and SMTP NOOP; it sends no MAIL, RCPT, or DATA commands.

Saved settings and a previous check do not establish current delivery. Verify
one approved, authorized message and its receipt; an owned test inbox can also
confirm inbox arrival. Mailpit acceptance is local test evidence. External SMTP
acceptance means the provider accepted responsibility for the message, and
does not establish inbox placement, reading, or a reply.

## Known gaps

- inbound email reading/classification is manual;
- UTM performance is entered manually until KarixMC exposes a scoped analytics
  import/webhook;
- discovery covers official YouTube metadata; Twitch, TikTok, Discord,
  Minecraft servers, and blogs can be added manually but are not auto-searched;
- creator contracts, sponsorship disclosures, payments, point grants, content
  review, and publication remain human workflows.
