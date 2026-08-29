# Dashboard and career-mission operations

The command center is a website served by the control API. It works on the
current Windows machine now and can use the same UI on a VPS later. It is not a
desktop-only executable and does not depend on a hosted SaaS frontend.

## Start the complete local test

From PowerShell in the repository:

```powershell
./scripts/open-dashboard.ps1 -LocalModel -SideEffectsTest -CopyToken
```

This builds and starts the core stack, starts or reuses Qwen3 8B through Ollama,
runs health checks, copies `CONTROL_API_TOKEN` without printing it, and opens
<http://127.0.0.1:8080/>. Paste the clipboard value into **Connect workspace**,
then overwrite the clipboard with ordinary text. The test profile also starts a
fake ATS and Mailpit at <http://127.0.0.1:8025>; messages are captured inside
Docker and never sent.

Use `./scripts/open-dashboard.ps1 -CopyToken` when discovery/tracking is enough
and local drafting is not needed. `./scripts/down.ps1` stops compute while
preserving PostgreSQL data. The scheduler runs only while Docker and the stack
are running. Laptop sleep, shutdown, or Docker Desktop shutdown pauses scans;
overdue active missions are picked up after restart.

## Create the first real job hunt

1. Open **Missions → Create mission**.
2. Give it a name and the candidate name used in drafts.
3. Add several precise titles, for example `Software Engineer`, `Backend
   Intern`, and `AI Engineer`.
4. Add only skills actually supported by the résumé. Optional required and
   excluded keywords reduce noise.
5. Select locations, remote preference, employment types, freshness (24–168
   hours), and minimum score.
6. Keep the no-key Arbeitnow source enabled. Optionally add exact public Ashby,
   Greenhouse, or Lever employer board slugs.
7. Paste plain résumé text. It is stored in PostgreSQL, hidden from profile API
   responses, and omitted from task payloads/audit metadata. Drafting stays on
   local Qwen unless you explicitly enable OpenRouter; hosted drafting sends the
   résumé and selected job to the verified free model/provider under the
   configured privacy policy.
8. Complete the application identity. This supplies routine name/contact fields
   but never invents screening, legal, demographic, or consent answers.
9. Enable **Automatically prepare strong fresh matches** if desired. Set its
   score threshold and per-scan cap. This drafts and inspects supported forms
   automatically; it does not approve the final click.
10. Check **Keep this mission running automatically**, save, and use **Scan
    now** for the first result.

Fresh matches appear under **Opportunities** with posting time, source link,
score, and matching reasons. Shortlist or dismiss them. **Generate private
draft** creates a truthful fit summary, résumé evidence, honest gaps, keywords,
and cover-letter draft through the ranked free route with local Qwen continuity.
The **Settings** page shows which route actually ran. **Inspect form** opens only a reviewed
Greenhouse, Ashby, or Lever hosted form in the isolated worker. **Prepare exact
submission** resolves routine fields and asks for every unknown required answer.
It freezes the final host, form signature, values, résumé/draft hashes, and
submit label into the **Approvals** inbox.

Review that exact envelope and approve it once. The worker reloads and rechecks
the form, commits a durable receipt, and performs one final click. It will not
retry automatically. CAPTCHA, account login, multi-page flows, changed forms,
or unknown required answers stop for user handling; the adapter never bypasses
them or guesses consent.

## Switch or pause the task

The ongoing instruction lives under **Missions**, not in source code. Toggle a
mission off to pause it. Use **Edit mission** to change titles, filters, sources,
schedule, or résumé. Create a second mission for a materially different search,
such as internships versus full-time roles; each schedule and result set stays
separate.

The **Tasks & audit** view can also assign harmless one-off `foundation.echo`
or bounded wait tasks and shows execution history. The **Approvals** inbox is
where future high-impact operations stop for a decision.

## Creator campaigns

The same command center now includes a separate **Creator campaigns** workspace
for KarixMC promotion. It uses official YouTube metadata, manual public-contact
qualification, exact approval per email, durable suppression, reply/result
entry, and bounded draft-variant learning. It is intentionally separate from
career profiles and never reuses résumé or opportunity data. See
[creator outreach operations](creator-outreach.md) before configuring a real API
key or SMTP destination.

## Repeatable engineering proof

With the core and local model running:

```powershell
./scripts/career-smoke.ps1 -Draft
./scripts/side-effect-smoke.ps1
```

The script retrieves a current listing from the reviewed public API, creates a
synthetic inactive profile, queues a real policy-bound scan, requires at least
one persisted attributable match, queues a structured draft through the
configured route, then deletes
only its exact synthetic profile. It never uses a real résumé.
The second command uses a fake candidate, fake ATS, and local Mailpit inbox. It
proves the exact digest, application click, email send, and duplicate receipt
guard, then deletes only its own PostgreSQL records.

## Enable real external actions

Start the isolated executor without test fixtures:

```powershell
./scripts/open-dashboard.ps1 -LocalModel -SideEffects -CopyToken
```

Application preflight/submission needs no credential when the supported hosted
form itself is public. Real email remains disabled until `MAIL_TRANSPORT=smtp`
and user-owned `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, TLS mode, username, and
password are configured in ignored deployment secrets. External SMTP requires
`starttls` or `ssl`. Recreate the control API and action worker after a setting
change. Never copy these credentials into a mission or chat.

## VPS access model

Do not publish port 8080 to the public internet. The current bearer token is a
single administrator bootstrap credential, not multi-user login. For a first
VPS test, bind the Compose port to loopback and use either:

- an SSH tunnel: `ssh -L 8080:127.0.0.1:8080 deploy@your-vps`, then open the
  local URL; or
- WireGuard/Tailscale plus a firewall rule that permits only the private VPN;
  or
- an authenticated HTTPS reverse proxy after OIDC, rate limits, and TLS are
  implemented.

The UI, API, career/action workers, PostgreSQL, Redis, and optional Ollama can run
on a single Linux VPS. Local Qwen requires sufficient RAM/GPU; a CPU-only low-cost
VPS may discover and rank jobs but generate drafts slowly or not at all. Keep
drafting on a private GPU machine or select a provider only after reviewing its
privacy and free-tier terms.

## What is free and what is not

- The code, Docker stack, PostgreSQL, Redis, dashboard, scheduler, scoring, and
  local Ollama/Qwen inference have no per-token software charge.
- Eligible OpenRouter `:free` variants report zero inference cost, but their
  shared request quotas, availability, privacy endpoints, and terms can change.
  The system validates current price and returned cost; it cannot promise
  third-party free capacity.
- Arbeitnow and public Ashby, Greenhouse, and Lever boards need no API key for
  discovery. Public hosted application forms do not guarantee automation
  compatibility or permission under every employer/site's terms.
- Electricity, internet, domain names, and VPS compute are infrastructure costs;
  “free software” does not make a continuously running VPS free.
- Public job-source terms and rate/availability can change. The project uses a
  conservative minimum six-hour schedule, retains original attribution links,
  and isolates source failures.
