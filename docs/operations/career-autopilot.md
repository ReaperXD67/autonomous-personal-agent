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

## Gmail read-only connection

1. Enable the Gmail API in a Google Cloud project you control. Configure an OAuth
   consent screen and client for your account. Request offline access with only
   `https://www.googleapis.com/auth/gmail.readonly`; the worker rejects broader
   scopes and refresh responses without scope attestation.
2. Create a Gmail label named `Hermes/Careers` (or your chosen label). Add only
   application replies to it, manually or using your own Gmail filters. The
   adapter cannot create labels or modify mail.
3. Put `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, and
   `GMAIL_CAREER_LABEL` in the ignored local `.env` or the deployment secret
   manager. Never paste them into a task, commit, browser URL or screenshot.
   Set `GMAIL_ENABLED=true` only after supplying these values. Recreate the
   control API and research worker with `docker compose up -d control-api job-worker`.
4. Use the exact Gmail account email in the mission's application identity.
   The adapter checks the authenticated mailbox before reading labelled messages.
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
The career label must exist and the authenticated mailbox must match the saved
application identity. Configure that mailbox deliberately; do not change the
candidate identity merely to make an existing connection pass. Shared credential
changes also need to preserve any enabled creator mailbox's identity.

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
