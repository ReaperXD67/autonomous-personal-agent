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

Recreate the research worker after changing the secret:

```powershell
./scripts/up.ps1
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

## 4. Run the sequence

Every step creates one frozen sender/recipient/subject/body action in
**Approvals**. Nothing is delivered until that exact action is approved.

1. **Prepare introduction** explains the reward-network model, offers the
   configured viewer and creator/server pilot, asks for an honest collaboration,
   includes a per-prospect UTM link, identifies the contact source, and provides
   a direct opt-out.
2. Record the reply manually. If it is a question, select **Asked a question**,
   then **Write manual answer**. Write only verified facts; the system adds the
   provenance/opt-out footer and creates another exact approval.
3. Record an ordinary or ambiguous “no” as **No / do not contact**. That address
   is durably suppressed and any pending approval becomes non-executable.
4. Choose **Declined only because it was unpaid** only when the creator actually
   communicated that specific condition. It unlocks one final paid-option
   draft. The message says it is final and does not imply an agreed fee or scope.

The action worker rechecks address, authorization, suppression, and reply state
immediately before SMTP. A bounce or opt-out clears contact authorization and
cannot be reversed through the dashboard.

## 5. Record results and adapt

Use **Record reply or result** to capture question/interest/decline state,
published placement URL, attributed views/clicks/signups/server owners, and
viewer points actually issued. Do not enter projections as results.

The dashboard shows the linear funnel and two introduction variants. For fewer
than ten delivered introductions, the agent recommends collecting evidence.
Only after both variants have ten delivered emails can a variant win. It must
lead positive-reply rate by at least five percentage points and 1.5×; then 80%
of future drafts use it while 20% continues exploration. High suppression,
question, or unpaid-decline rates produce stop/review suggestions.

These are associations, not proof of causation. The agent never changes an
offer, budget, contact, policy, code, or approval. An operator decides whether a
suggestion justifies editing the campaign.

## 6. Enable real delivery

First prove the mail path with Mailpit:

```powershell
./scripts/side-effect-smoke.ps1
```

Then configure user-owned TLS SMTP as described in
[manual setup](manual-setup.md#real-email-transport) and start the side-effect
profile:

```powershell
./scripts/up.ps1 -SideEffects
```

Send a harmless message to an address you own before contacting a creator. A
healthy container is not delivery proof; verify the provider inbox and receipt.

## Known gaps

- inbound email reading/classification is manual;
- UTM performance is entered manually until KarixMC exposes a scoped analytics
  import/webhook;
- discovery covers official YouTube metadata; Twitch, TikTok, Discord,
  Minecraft servers, and blogs can be added manually but are not auto-searched;
- creator contracts, sponsorship disclosures, payments, point grants, content
  review, and publication remain human workflows.
