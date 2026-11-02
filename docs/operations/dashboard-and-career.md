# Dashboard and career-mission operations

The command center is a website served by the control API. It works on the
current Windows machine now and can use the same UI on a VPS later. It is not a
desktop-only executable and does not depend on a hosted SaaS frontend.

Career missions now accept supported employer-board/job URLs, including Lever
EU, and explain job-risk signals before automatic preparation. The opportunity
inbox prioritizes recorded shortlists, interviews, offers and uncertain replies
in **Your next decisions**. These stages make no model calls; application writing
still uses configured inference. See [Career Play and Gmail](career-autopilot.md)
for source import, readiness, scope and verification limits.

Current fit evidence separates title/skill matches from freshness. Mission scan
details explain exclusions and partial source coverage. Draft review displays
generation-time résumé-grounding findings; automatic authorization recomputes
them. Unknown documents and consent/default choices require explicit handling.
SmartRecruiters extends read-only discovery and drafting, with manual submission.

The **Workflows** view coordinates dependent tasks with explicit result checks,
parallel limits, deadlines, and cancellation. Use its safe demo or the
application draft → form inspection recipe; see the
[workflow guide](workflows.md). Workflow-managed preparation creates only its
listed steps; preparing an exact submission remains a separate reviewed action.

## Start the complete local test

From PowerShell in the repository:

```powershell
./scripts/open-dashboard.ps1 -SideEffectsTest
```

This builds and starts the core stack plus the managed model hierarchy, runs
health checks, and opens <http://127.0.0.1:8080/> already authenticated through
a 90-second one-use fragment. The page removes the fragment immediately and
uses an HttpOnly session; it does not receive the long-lived control token. The
test profile independently starts a fake ATS and Mailpit at
<http://127.0.0.1:8025>; messages are captured inside Docker and never sent.
The Ollama daemon is ready, but Qwen weights remain unloaded unless both hosted
routes fail.

Use `-LocalModel` only to exercise the final Qwen fallback explicitly; the
script unloads it after the canary. `-CopyToken` is a recovery option only.
`./scripts/down.ps1` stops compute while
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
   local Qwen unless you explicitly enable OpenRouter; hosted drafting sends bounded
   résumé excerpts, supported keyword choices and the selected job to the verified
   free model/provider under the configured privacy policy.
8. Complete the application identity. This supplies routine name/contact fields
   but never invents screening, legal, demographic, or consent answers.
9. Save the mission and open **Play**. Choose preparation or a scoped automatic
   application run, review sites, cap, expiry, freshness and screening answers.
10. Follow the run and application tracker. See the [career Play and Gmail guide](career-autopilot.md)
    for scope, private account setup and honest source limitations.

Fresh matches appear under **Opportunities** with posting time, source link,
score, and matching reasons. Shortlist or dismiss them. **Generate private
draft** creates a fit summary, résumé evidence, honest gaps, keywords, and cover
letter through the policy-compatible ranked free route with local Qwen continuity.
The server issues content-bound IDs for exact résumé excerpts and supported literal
keywords. The model chooses IDs; the server resolves their original text, so the
model cannot rewrite a quotation or add an unsupported résumé keyword. Recognized
email/phone/URL spans, candidate-name lines and common headings are excluded from
evidence choices. Older saved drafts remain unchanged.

Provider errors, empty output, and structurally invalid output move to the next
ranked candidate under a separately counted reservation; exhausted hosted candidates
move to Qwen when local fallback is enabled. A deterministic review checks grounding,
cover-letter length, placeholders, unsupported metrics and tenure, and posting
integrity. Correctable findings allow **one** additional model call with its own
inference-ledger reservation. Hosted repair reuses the selected free route; it never
fans out to paid models. Failed or quota-blocked repair preserves the original draft
for review, without a substitute template. Source-integrity warnings alone do not
spend a repair call. Grounding is checked again against the current résumé before
automatic submission; these mechanical checks do not prove semantic truth or eligibility.
Task output records `quality_repair_model_calls` and `quality_repair_status`; the
deterministic review's `quality_model_calls` stays zero.

Local generation uses a separate transport schema: finite ID enums, required fields
and small array caps stay in Ollama's `format`, while string-length limits and
uniqueness remain in the full prompt and server validation. Ollama 0.32.5
[pins llama.cpp b10091](https://github.com/ollama/ollama/blob/v0.32.5/LLAMA_CPP_VERSION),
whose [grammar parser](https://github.com/ggml-org/llama.cpp/blob/b10091/src/llama-grammar.cpp)
rejects the repetitions produced by the 2,000/6,000-character string bounds.
The [schema converter documentation](https://github.com/ggml-org/llama.cpp/blob/b10091/grammars/README.md)
also lists `uniqueItems` as unsupported. This transport accommodation does not relax
the parser's length/type checks, duplicate-ID rejection or source-provenance guard.

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

The ongoing instruction lives under **Missions**, not in source code. Use **Pause** to stop new autonomous submissions. Use **Edit mission** to change titles, filters, sources,
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
./scripts/open-dashboard.ps1 -SideEffects
```

Application preflight/submission needs no credential when the supported hosted
form itself is public. Real email remains disabled until `MAIL_TRANSPORT=smtp`
and user-owned `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, TLS mode, username, and
password are configured in ignored deployment secrets. External SMTP requires
`starttls` or `ssl`. Recreate the control API and action worker after a setting
change. Never copy these credentials into a mission or chat.

## VPS access model

Do not publish port 8080 to the public internet. The signed browser session is a
single-operator convenience, not multi-user identity. For a first
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
  The system validates current price, active ZDR compatibility, returned model,
  and returned cost; it cannot promise third-party free capacity or output
  quality. Structurally invalid hosted output is rejected. Invalid grounding can be
  retained as a blocked, inspectable draft and gets at most one corrective call.
- Arbeitnow and public Ashby, Greenhouse, and Lever boards need no API key for
  discovery. Public hosted application forms do not guarantee automation
  compatibility or permission under every employer/site's terms.
- Electricity, internet, domain names, and VPS compute are infrastructure costs;
  “free software” does not make a continuously running VPS free.
- Public job-source terms and rate/availability can change. The project uses a
  conservative minimum six-hour schedule, retains original attribution links,
  and isolates source failures.
