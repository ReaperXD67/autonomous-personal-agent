# Career Play and Gmail setup

Create a private career mission with your actual resume text, identity, portfolio,
role titles, skills and allowed locations. All required keywords must match;
remote jobs restricted to another country are not treated as worldwide jobs.
Choose public employer boards under Sources. Remotive is optional, delayed by
24 hours, and retains its original listing links. Greenhouse update timestamps
do not establish when a job was posted.

### Import an employer board from a job link

In **Edit mission → Search sources**, paste an Ashby, Greenhouse, Lever US or
Lever EU board/job URL into **Employer board or job URL**, then choose **Add
board from URL**. Review the resulting source field and save the mission. The
resolver recognizes the URL locally, discards tracking parameters and performs
no network request or inference. A later scan reads the entire configured
employer board through its public API; importing a job link does not select,
verify or apply to that particular vacancy. The provider-specific fields also
accept matching URLs directly. US and EU Lever boards are separate sources.

For LinkedIn, YC or a company careers page, follow the employer's application
link and copy its supported ATS URL. Direct platform/account automation and
arbitrary website scraping remain unavailable. Unsupported links produce setup
guidance rather than silently connecting an account.

### Job-risk and freshness checks

Each opportunity displays current, explainable checks for applicant payments,
credential or sensitive-data requests, unsafe destinations and mismatched ATS
board identities. Strong signals stop automatic preparation before inference;
the same checks run again at final automatic submission. Inspect flagged jobs
and independently verify the original employer. A **No strong flags** result
leaves authenticity unverified and cannot prove that a vacancy is open. Consumer
email contacts, sparse descriptions and unconfirmed publication dates remain
visible evidence. Updated, observed and future dates never establish freshness.

These are deterministic heuristics, not a fraud detector with measured accuracy.
Discovery, ranking, source import, checks and reply classification make no model
calls. Application drafting uses the configured model and still consumes model
tokens and compute, even on free routes or local hardware.

Open **Play** on the mission. **Prepare** generates drafts and form inspections
for review. **Apply** additionally authorizes submissions within the displayed
scope. Defaults are 72 hours, score 75, three applications per rolling 24 hours,
and a 24-hour run. Choose the actual ATS hosts and provide known screening
answers. Required unknown answers stop the item for review. Editing profile
preferences, identity or resume invalidates the existing grant. Press Play again
after reviewing the changed scope. Pause stops new submissions at the durable
receipt boundary; already submitted requests cannot be undone.

Preparation uses a separate rolling allowance: at most 20 opportunities per
profile in 24 hours, across all runs and including failed preparation, and at
most twice the selected daily application limit per run (maximum 20). Starting
another Play run cannot reset the profile preparation allowance. A default
Prepare run can therefore be followed by Apply without treating its drafts as
submitted applications. Exact submission reservations retain the selected daily
cap, destination deduplication and final execution checks. The mission shows
both counters and explains when preparation has reached its limit.

Each newly prepared packet retains a direct link to its exact action. Follow
**View exact action** to review it; progress reflects its queued or terminal
result, including a later manual submission. The link itself grants no authority.
Migration 019 backfills links only from known authorization reservations; older
preparation-only history is not matched by guesswork.

Optional hiring email applies only to a fresh matching job that explicitly
publishes one unambiguous hiring address. It uses a run-bound resume-derived
cover letter and saved portfolio, never guessed addresses. Email and ATS
submissions share the same target deduplication and daily allowance. SMTP must
be configured; Mailpit is a local test sink. SMTP acceptance records a submitted
application but does not prove inbox delivery. Existing sender pacing still applies.

The run shows preparation failures and missing answers. The application tracker
records submission, acknowledgement, recruiter reply, shortlist, interview, rejection,
offer, withdrawal and review-needed history. Manual outcomes and Gmail signals
retain their source and confidence. Outcome suggestions are descriptive; they
do not claim why a rejection happened or silently widen the authorized scope.

**Your next decisions** in the opportunity inbox prioritizes offers, interviews,
shortlists and uncertain mailbox matches as the dashboard refreshes. Counts
cover the loaded history and selected mission, not an unbounded mailbox. A
shortlist is an employer-reply outcome, separate from manually shortlisting a
job you want to apply to. Conditional, negated and contradictory messages remain
conservative evidence; a subject alone cannot confirm a contradicted outcome.
Review the original reply before relying on a signal. The agent neither accepts
interviews nor sends replies from inbox content, and does not invent times.

## Fit, scan coverage and application evidence

Fit policy version 2 gives title evidence up to 45 points and up to five distinct
saved-skill matches 11 points each. Explicit spelling aliases are deduplicated;
Java does not match JavaScript, SQL does not match NoSQL, and React does not
match “reactive”. A strong job retains the same fit at one or 71 hours. Freshness
remains a separate hard window, and automatic applications still require a
proven publication date. The score is an inspectable heuristic, not a probability
of hiring or an assertion about experience, education or work authorization.
Old scoring grants stop rather than inheriting changed semantics; review Play
again after upgrading.

Open a mission's **Latest search coverage and exclusions** for normalized listing
counts, first exclusion reasons, source warnings and bounded provider coverage.
An unavailable source is not evidence that its jobs closed. The worker cannot
call a partial page a search of the entire web. Current fit details are recomputed
from saved preferences; historical stored scores change on the next rescan.

Draft review exposes exact saved-résumé evidence quotations, observed keywords,
honest gaps and a generation-time quality report. Delegated submission requires
current evidence checks, including narrow unsupported metric/tenure and
placeholder findings. The useful-copy length rule is a heuristic, not a writing
quality guarantee. Authorization and final submission recheck current inputs and
grant expiry after database waits. Models cannot supply or approve their own
quality verdict. Inspect complete copy before manually approving an exception.

Form autofill uses stored identity only for supported, clearly identified text
fields. A résumé is attached only to an explicit compatible résumé upload.
Consent, radio choices, employer-specific questions and default-checked optional
controls require explicit answers; unknown documents need manual handling on the
employer page. A changed default invalidates the approved form signature.

### SmartRecruiters and multi-location discovery

Add SmartRecruiters company slugs or supported public board URLs under Search
sources. The official adapter reads one page of at most 50 listings and at most
ten fresh details per board, prioritizes matching title metadata and reports
truncation/failures. Explicit India-only preferences can narrow the provider
query; this does not establish work eligibility. `releasedDate` is an employer
publication/re-publication date, not proof of first creation or authenticity.
These jobs support discovery and drafting; submit on the original employer page.
SmartRecruiters does not join the automatic browser destination allowlist.

Ashby discovery now retains explicitly listed secondary locations and country
metadata. A hybrid workplace is not classified as fully remote merely because
the source's broad `isRemote` flag is true.

## Gmail read-only connection

1. Enable the Gmail API in a Google Cloud project you control. Configure an OAuth
   consent screen and **Desktop app** client for your account. Add the career
   mailbox as a test user if the app is in Testing; keep its downloaded JSON
   private. Request offline access with only
   `https://www.googleapis.com/auth/gmail.readonly`; the worker rejects broader
   scopes and refresh responses without scope attestation.
2. Create a Gmail label named `Hermes/Careers` (or your chosen label). Add only
   application replies to it, manually or using your own Gmail filters. The
   adapter cannot create labels or modify mail.
3. Use the exact Gmail account email in the mission's application identity. From
   the repository root, run the local helper with that address:

   ```powershell
   ./scripts/gmail-oauth.ps1 -Purpose Career `
     -ClientJsonPath 'C:\Users\YourName\Downloads\client_secret_your_client.json' `
     -Mailbox 'your-application@gmail.com'
   ```

   Select that account in Google's consent screen. The helper checks PKCE/state,
   exact read-only scope, mailbox identity and the existing custom label before
   saving anything. It does not create a label/filter or send mail.
4. Successful setup atomically saves `GMAIL_CAREER_CLIENT_ID`,
   `GMAIL_CAREER_CLIENT_SECRET`, `GMAIL_CAREER_REFRESH_TOKEN`,
   `GMAIL_CAREER_MAILBOX`, `GMAIL_CAREER_LABEL` and `GMAIL_ENABLED=true` in ignored
   `.env`. Only the research worker receives OAuth secrets. Recreate the readers
   with `docker compose up -d control-api job-worker`. Never paste credentials
   into a task, commit, browser URL or screenshot.
5. Use **Sync Gmail** and verify the task result. A healthy container or enabled
   setting is only configuration evidence. A successful, harmless label sync is
   required before calling the connection verified.

The OAuth scope technically grants mailbox-wide read access. The implementation
enforces the selected label on both listing and individual message reads, retains
only bounded headers/snippets, and never downloads bodies or attachments. Each
pass lists at most 50 IDs and retrieves at most 20 metadata records. Durable
cursors allow later passes to continue. Matching requires a known application
thread/reference or strong company/title evidence; unmatched mail appears in
the review list. A suggested meeting time is not a calendar invitation or booking.

While enabled, the scheduler checks replies every 15 minutes for active runs
and applications submitted in the past 180 days, even when applying is paused.
Set `GMAIL_ENABLED=false` and recreate the services to stop scheduled and manual reads.
The local stack must remain running; laptop sleep pauses work.

An OAuth connection for creator outreach does not automatically enable careers.
`-Purpose Career` preserves the shared `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`
and `GMAIL_REFRESH_TOKEN` used by Creator monitoring. All three dedicated Career
credentials must be present together with `GMAIL_CAREER_MAILBOX`; partial tuples
stop rather than borrowing individual Creator secrets. When all dedicated
credentials are empty, older same-mailbox installations retain shared-grant
fallback. The configured Career mailbox must match the selected profile before
OAuth runs, and the authenticated mailbox is checked again before labeled reads.
Do not change the candidate identity merely to make an existing connection pass.
See the [OAuth runbook](gmail-setup.md) for recovery and token-expiry limits.

Official references: [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes),
[offline OAuth](https://developers.google.com/identity/protocols/oauth2/web-server#offline),
[message metadata](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get),
[Remotive API](https://github.com/remotive-com/remote-jobs-api).

## Local validation

`./scripts/test.ps1` runs containerized lint and unit/contract tests.
`./scripts/career-autopilot-smoke.ps1` exercises durable run, risk, receipt,
shortlist and reply-monitoring guards in a disposable PostgreSQL database.
`./scripts/career-ui-smoke.ps1` runs the actual dashboard assets with synthetic
data and no browser network access, checking outcome priority, escaped text,
risk filters, source-import errors and mobile overflow. Screenshots stay under
ignored `output/playwright/career/`. The full `./scripts/verify.ps1` includes both
career checks. These fixtures do not prove real external ATS compatibility or
incoming Gmail reply accuracy.
