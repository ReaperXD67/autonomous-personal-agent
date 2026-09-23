# Career Play and Gmail setup

Create a private career mission with your actual resume text, identity, portfolio,
role titles, skills and allowed locations. All required keywords must match;
remote jobs restricted to another country are not treated as worldwide jobs.
Choose public employer boards under Sources. Remotive is optional, delayed by
24 hours, and retains its original listing links. Greenhouse update timestamps
do not establish when a job was posted.

Open **Play** on the mission. **Prepare** generates drafts and form inspections
for review. **Apply** additionally authorizes submissions within the displayed
scope. Defaults are 72 hours, score 75, three applications per rolling 24 hours,
and a 24-hour run. Choose the actual ATS hosts and provide known screening
answers. Required unknown answers stop the item for review. Editing profile
preferences, identity or resume invalidates the existing grant. Press Play again
after reviewing the changed scope. Pause stops new submissions at the durable
receipt boundary; already submitted requests cannot be undone.

Optional hiring email applies only to a fresh matching job that explicitly
publishes one unambiguous hiring address. It uses a run-bound resume-derived
cover letter and saved portfolio, never guessed addresses. Email and ATS
submissions share the same target deduplication and daily allowance. SMTP must
be configured; Mailpit is a local test sink. SMTP acceptance records a submitted
application but does not prove inbox delivery. Existing sender pacing still applies.

The run shows preparation failures and missing answers. The application tracker
records submission, acknowledgement, recruiter reply, interview, rejection,
offer, withdrawal and review-needed history. Manual outcomes and Gmail signals
retain their source and confidence. Outcome suggestions are descriptive; they
do not claim why a rejection happened or silently widen the authorized scope.

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

Official references: [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes),
[offline OAuth](https://developers.google.com/identity/protocols/oauth2/web-server#offline),
[message metadata](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get),
[Remotive API](https://github.com/remotive-com/remote-jobs-api).
