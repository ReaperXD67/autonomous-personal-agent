# Integration roadmap

| Domain | Order | Boundary | Approval |
|---|---|---|---|
| Communication | Telegram control → email read → draft → send | Separate credentials/tools for read, draft, send | Send always high-risk |
| Development | GitHub read → branch/PR draft → CI → merge | Repository allowlist and protected branches | Merge/destructive high-risk |
| Research | Fetch/search → disposable browser → extraction | SSRF controls, domain policy, no personal browser profile | Form submit/download action-dependent |
| Productivity | Calendar/Drive/Notion/task manager | Per-provider OAuth scope and agent profile | External writes medium/high |
| Automation | Scheduler → durable jobs → webhooks | Persist before enqueue, signed inbound webhooks | Side-effect risk derived from target |
| Finance | Read-only summaries only | Separate account, no transaction permission | Transactions disabled |
| Jobs | Discovery → tracking → draft → submit | Site-specific adapters and evidence bundle | Exact approval or expiring scoped career grant |

Integration is added only when its threat model, credential scope, audit schema,
failure behavior, disable path, and safe test are documented.

Current jobs milestone: public Arbeitnow/Ashby/Greenhouse/Lever discovery,
opt-in attested-free OpenRouter drafting with local Qwen continuity, and the
first reviewed single-page hosted-form adapter are implemented. The hosted
route passed a user-key, strict-ZDR, reported-zero-cost canary on 2026-09-10;
free inventory and real résumé-draft quality still require ongoing observation.
SMTP send is implemented with the same exact-action envelope. The generic
browser MCP and unsupported site logins remain disabled. Gmail read-only label
tracking is implemented behind explicit OAuth configuration and an integration
off switch; no live mailbox verification is implied. Career Play can authorize
exact actions within the frozen scope described in ADR-0022.
