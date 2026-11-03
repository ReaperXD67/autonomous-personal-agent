# Connect a Gmail reply inbox

This connects owner-controlled Gmail mailboxes to Creator or Career reply
monitoring. The two readers can use separate OAuth grants and custom labels.
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
2. For an external app in Testing, add each monitored mailbox as a test user.
   Create an OAuth client of type **Desktop app**, then download its JSON
   privately. A YouTube API key is not an OAuth client.
3. In the monitored Gmail, create **Hermes/Creators** for Creator replies or
   **Hermes/Careers** for Career replies (or the exact configured
   `GMAIL_CREATOR_LABEL` / `GMAIL_CAREER_LABEL`). Arrange a Gmail filter or manually
   apply the custom label to relevant replies. The reader cannot create labels
   or filters; Google system labels do not satisfy setup.
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

This defaults to `-Purpose Creator`. To connect the Career application mailbox
separately, first save that same email in the career profile, then run:

```powershell
./scripts/gmail-oauth.ps1 -Purpose Career `
  -ClientJsonPath 'C:\Users\YourName\Downloads\client_secret_your_client.json' `
  -Mailbox 'your-application@gmail.com'
```

The default browser opens Google's consent screen. Select the expected account
and review the permission. The helper requests only
`https://www.googleapis.com/auth/gmail.readonly`. This scope permits reading the
mailbox; limiting runtime reads to the selected custom label is Hermes application
behavior, not a Google label-specific permission. It grants no sending, deletion,
label creation, or filter-editing authority. See Google's
[scope definitions](https://developers.google.com/workspace/gmail/api/auth/scopes).

The temporary callback listens only on `127.0.0.1` on a random port. It validates
random state, uses S256 PKCE, rejects an unexpected scope or mailbox, and checks
that the expected custom user label exists. The callback closes after success/failure or a
bounded wait (default ten minutes; `-TimeoutSeconds` accepts 60–900).
No authorization URL, callback code, provider response, or token is printed.

Only after all checks pass does it atomically merge purpose-specific values into
ignored `.env`:

| Purpose | Saved settings |
| --- | --- |
| Creator (default) | `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `CREATOR_GMAIL_ENABLED`, `CREATOR_GMAIL_MAILBOX`, `GMAIL_CREATOR_LABEL` |
| Career | `GMAIL_CAREER_CLIENT_ID`, `GMAIL_CAREER_CLIENT_SECRET`, `GMAIL_CAREER_REFRESH_TOKEN`, `GMAIL_ENABLED`, `GMAIL_CAREER_MAILBOX`, `GMAIL_CAREER_LABEL` |

The input JSON is read in place; it is not copied into the repository.
SMTP and Gmail setup use a shared process lock for configuration writes.
Unrelated edits completed during browser consent are preserved; changed Gmail
settings stop the save. Avoid editing `.env` manually while a save is in progress.

Career setup never refreshes or replaces the Creator grant. The complete
dedicated Career tuple requires its recorded mailbox; the worker rejects partial
tuples and any difference from the profile's application email before requesting
OAuth. It checks Google's returned identity again before reading messages.
Legacy Career installations fall back to the common `GMAIL_*` grant only when all
three dedicated credentials are empty. These OAuth secrets are passed only to
the research worker.

If the selected purpose's existing credentials belong to another mailbox, are
incomplete, or cannot be verified, setup stops and preserves them. Creator setup
does not enable Career monitoring. Changing the application identity merely to
reuse a different connected mailbox is not a connection fix.

The only renewal exception is the explicit same-mailbox flow below, after Google
has identified the old refresh grant as invalid. Other verification failures
still stop setup.

## Verify before relying on monitoring

Creator full-text capture is a separate, explicit campaign opt-in. Keep
`CREATOR_GMAIL_FULL_REPLY_CAMPAIGN_IDS=[]` for metadata-only reading, or set a JSON
array of up to ten distinct saved campaign UUIDs in ignored configuration after
reviewing that scope. Connecting Gmail does not enable all campaigns' full bodies.
The ordinary sync backfills matched pending replies only for selected IDs; this
setting grants no sending authority. See the [complete-reply workflow](creator-outreach-continuation.md#complete-reply-evidence).

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

For Career, choose **Sync Gmail** and inspect the governed task result; a harmless
labeled sync is required before marking the connection verified. Check an owned
test reply against a known test application before relying on shortlist or
interview classification. Uncertain matches/times remain for review. See the
[Career tracking guide](career-autopilot.md#gmail-read-only-connection). Enabling
the flag or passing OAuth alone does not prove Career reply ingestion.

## Expiry and recovery

External apps left in Google's Testing publishing status receive refresh tokens
that expire after seven days when Gmail scope is requested. Password changes,
revocation and other account policies can also invalidate tokens. Plan the
appropriate Google publishing/verification setup for continued use, and rerun
local consent when reauthorization is needed. The helper does not change Cloud
publishing status or bypass Google verification. See
[Google's refresh-token rules](https://developers.google.com/identity/protocols/oauth2#expiration).

For a previously configured creator mailbox whose refresh request returns
Google's exact HTTP 400 `invalid_grant`, rerun the same Desktop client and
recorded mailbox explicitly:

```powershell
./scripts/gmail-oauth.ps1 `
  -ClientJsonPath 'C:\Users\YourName\Downloads\client_secret_your_client.json' `
  -Mailbox 'your-sender@gmail.com' `
  -ReauthorizeExistingMailbox
```

This option requires all three existing OAuth fields, enabled creator monitoring,
the recorded creator mailbox and label, the same client ID/secret, and disabled
career monitoring. It does not authorize changing accounts or clients. An outage,
wrong client, malformed response or authorization-code failure is not an expiry
exception. New consent still passes PKCE/state, exact read-only scope, mailbox,
label and atomic-save checks. Until consent finishes, the old settings remain
unchanged. Reload the reader services and run a governed reply sync before
claiming recovery. See [ADR-0028](../decisions/ADR-0028-explicit-creator-oauth-renewal.md).

For a dedicated Career grant, use the same command with `-Purpose Career` and the
recorded Career mailbox. Its renewal requires the complete existing
`GMAIL_CAREER_*` tuple, `GMAIL_ENABLED=true`, the recorded mailbox/custom label,
and the same Desktop client. Creator monitoring can remain enabled: its grant is
not used or changed. Only Google's exact invalid refresh-grant response allows
the old online identity check to be replaced by this recorded provenance; the
new consent still passes every account/scope/label/save check.

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
guarded invalid-grant renewal for both purposes, custom-label checks, credential
isolation, sanitized errors, atomic configuration merging, concurrent writers,
and a real synthetic loopback callback. Live-provider verification is a separate
milestone.
