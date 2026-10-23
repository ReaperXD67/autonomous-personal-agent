# Connect a Gmail reply inbox

This connects an owner-controlled Gmail mailbox to creator reply monitoring.
Sending mail still uses the separate
[SMTP setup](creator-outreach.md#7-enable-real-delivery), including the hidden
credential prompt in `./scripts/promotion.ps1 -ConfigureGmail`.
Creating a Google account does not connect either integration.

For Gmail SMTP, the local helper asks for Google's generated **16-character app
password** after the sender address. That hidden prompt displays no typed or
pasted characters; press Enter to submit or Ctrl+C to cancel. Grouping spaces
are removed and invalid lengths prompt again without saving. Read-only OAuth
completion does not provide this sending credential.

## Prepare Google and the mailbox

1. In your own Google Cloud project, enable **Gmail API**. Configure the OAuth
   consent screen with the project owner's real contact details.
2. For an external app in Testing, add the sender mailbox as a test user.
   Create an OAuth client of type **Desktop app**, then download its JSON
   privately. A YouTube API key is not an OAuth client.
3. In that sender's Gmail, create the label **Hermes/Creators** (or the exact
   custom `GMAIL_CREATOR_LABEL` already configured). Arrange a Gmail filter or
   manually apply the label to creator replies. The reader cannot create
   labels or filters.
4. Keep the downloaded client JSON outside version control. Pass its absolute
   local path to the command below; do not paste its contents, tokens, or
   authorization codes into chat.

Google documents the [Desktop app flow](https://developers.google.com/identity/protocols/oauth2/native-app)
and the [Gmail API setup](https://developers.google.com/workspace/gmail/api/quickstart/python).
The helper uses built-in PowerShell/.NET; no host Python or Node installation is
needed.

## Connect locally

From the repository root, substitute your exact mailbox and client-file path:

```powershell
./scripts/gmail-oauth.ps1 `
  -ClientJsonPath 'C:\Users\YourName\Downloads\client_secret_your_client.json' `
  -Mailbox 'your-sender@gmail.com'
```

The default browser opens Google's consent screen. Select the expected account
and review the permission. The helper requests only
`https://www.googleapis.com/auth/gmail.readonly`. This scope permits reading the
mailbox; limiting runtime reads to **Hermes/Creators** is Hermes application
behavior, not a Google label-specific permission. It grants no sending, deletion,
label creation, or filter-editing authority. See Google's
[scope definitions](https://developers.google.com/workspace/gmail/api/auth/scopes).

The temporary callback listens only on `127.0.0.1` on a random port. It validates
random state, uses S256 PKCE, rejects an unexpected scope or mailbox, and checks
that the creator label exists. The callback closes after success/failure or a
bounded wait (default ten minutes; `-TimeoutSeconds` accepts 60–900).
No authorization URL, callback code, provider response, or token is printed.

Only after all checks pass does it atomically merge these values into ignored
`.env`: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`,
`CREATOR_GMAIL_ENABLED`, `CREATOR_GMAIL_MAILBOX`, and `GMAIL_CREATOR_LABEL`.
The input JSON is read in place; it is not copied into the repository.
SMTP and Gmail setup use a shared process lock for configuration writes.
Unrelated edits completed during browser consent are preserved; changed Gmail
settings stop the save. Avoid editing `.env` manually while a save is in progress.

The OAuth credentials are currently shared with the career reader. If existing
credentials belong to another mailbox, are incomplete, or cannot be verified,
setup stops and preserves them. It never silently switches a career inbox or
enables career monitoring. A separate second Gmail credential set is not
implemented.

## Verify before relying on monitoring

After a successful setup, reload the services that use the settings:

```powershell
docker compose up -d control-api job-worker
```

Use an inbox you control to reply to a reviewed test introduction, apply the
creator label in the sender mailbox, and choose **Check creator replies** in the
campaign dashboard. Verify the recorded sender, conversation match, excerpt and
review decision. Positive interest still requires confirmation against the
original reply. Repeat the sync to confirm the same message is not imported
twice.

Use a separate, clearly named test campaign and owned test conversation for this
proof, rather than counting a test reply as creator interest or learning
feedback. Retain the subject and verify the campaign/conversation match. The separate
[SMTP launch checks](creator-outreach.md#prove-an-owned-inbox-launch) distinguish
provider acceptance from actual inbox receipt; a Sent-folder copy is not inbox
delivery evidence.

Send the test reply from a different owned mailbox than the monitored sender.
The adapter ignores the monitored mailbox's own sender address and messages
marked Sent, Draft, Spam or Trash. Keep that filter intact; same-account
self-mail does not prove incoming creator-reply ingestion.

A successful helper run proves account identity and label access. It does not
prove reply ingestion, successful SMTP delivery, inbox placement, or permission
to begin a creator run. Complete those separate checks in the
[creator workflow](minecraft-creator-workflow.md).

## Expiry and recovery

External apps left in Google's Testing publishing status receive refresh tokens
that expire after seven days when Gmail scope is requested. Password changes,
revocation and other account policies can also invalidate tokens. Plan the
appropriate Google publishing/verification setup for continued use, and rerun
local consent when reauthorization is needed. The helper does not change Cloud
publishing status or bypass Google verification. See
[Google's refresh-token rules](https://developers.google.com/identity/protocols/oauth2#expiration).

If consent is declined, times out, selects another account, grants extra scope,
or the label is missing, existing configuration stays intact. Google may already
have recorded a consent grant before a later local check fails; inspect or revoke
that grant in the Google account when abandoning setup. Do not repeatedly
authorize a new client to work around an account conflict.

For local regression checks without accessing Gmail or the real environment:

```powershell
./scripts/gmail-oauth-smoke.ps1
```

This exercises PKCE, callback state/host limits, exact scope, account conflicts,
label checks, sanitized errors, atomic configuration merging, concurrent writers,
and a real synthetic loopback callback. Live-provider verification is a separate
milestone.
