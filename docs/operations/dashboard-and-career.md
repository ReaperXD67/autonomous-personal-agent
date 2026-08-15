# Dashboard and career-mission operations

The command center is a website served by the control API. It works on the
current Windows machine now and can use the same UI on a VPS later. It is not a
desktop-only executable and does not depend on a hosted SaaS frontend.

## Start the complete local test

From PowerShell in the repository:

```powershell
./scripts/open-dashboard.ps1 -LocalModel -CopyToken
```

This builds and starts the core stack, starts or reuses Qwen3 8B through Ollama,
runs health checks, copies `CONTROL_API_TOKEN` without printing it, and opens
<http://127.0.0.1:8080/>. Paste the clipboard value into **Connect workspace**,
then overwrite the clipboard with ordinary text.

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
6. Keep the no-key Arbeitnow source enabled. Optionally add exact public Ashby
   or Greenhouse employer board slugs.
7. Paste plain résumé text. It is stored in PostgreSQL, hidden from profile API
   responses, omitted from task payloads/audit metadata, and used only by local
   Qwen for drafts.
8. Check **Keep this mission running automatically**, save, and use **Scan now**
   for the first result.

Fresh matches appear under **Opportunities** with posting time, source link,
score, and matching reasons. Shortlist or dismiss them. **Generate private
draft** creates a truthful fit summary, résumé evidence, honest gaps, keywords,
and cover-letter draft using local Qwen. Inspect the pack and open the official
application link in a separate tab.

Marking a listing `applied` records what the user already submitted. It does not
submit a form. CAPTCHAs, account logins, screening questions, consent, and the
reputational/legal effect of an application make blind submission unsafe. A
future site-specific submit adapter must create an exact high-risk approval
before each application.

## Switch or pause the task

The ongoing instruction lives under **Missions**, not in source code. Toggle a
mission off to pause it. Use **Edit mission** to change titles, filters, sources,
schedule, or résumé. Create a second mission for a materially different search,
such as internships versus full-time roles; each schedule and result set stays
separate.

The **Tasks & audit** view can also assign harmless one-off `foundation.echo`
or bounded wait tasks and shows execution history. The **Approvals** inbox is
where future high-impact operations stop for a decision.

## Repeatable engineering proof

With the core and local model running:

```powershell
./scripts/career-smoke.ps1 -Draft
```

The script retrieves a current listing from the reviewed public API, creates a
synthetic inactive profile, queues a real policy-bound scan, requires at least
one persisted attributable match, queues a local structured draft, then deletes
only its exact synthetic profile. It never uses a real résumé.

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

The UI, API, career worker, PostgreSQL, Redis, and optional Ollama can run on a
single Linux VPS. Local Qwen requires sufficient RAM/GPU; a CPU-only low-cost
VPS may discover and rank jobs but generate drafts slowly or not at all. Keep
drafting on a private GPU machine or select a provider only after reviewing its
privacy and free-tier terms.

## What is free and what is not

- The code, Docker stack, PostgreSQL, Redis, dashboard, scheduler, scoring, and
  local Ollama/Qwen inference have no per-token software charge.
- Arbeitnow, public Ashby boards, and public Greenhouse boards need no API key.
- Electricity, internet, domain names, and VPS compute are infrastructure costs;
  “free software” does not make a continuously running VPS free.
- Public job-source terms and rate/availability can change. The project uses a
  conservative minimum six-hour schedule, retains original attribution links,
  and isolates source failures.
