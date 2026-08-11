# Integration roadmap

| Domain | Order | Boundary | Approval |
|---|---|---|---|
| Communication | Telegram control → email read → draft → send | Separate credentials/tools for read, draft, send | Send always high-risk |
| Development | GitHub read → branch/PR draft → CI → merge | Repository allowlist and protected branches | Merge/destructive high-risk |
| Research | Fetch/search → disposable browser → extraction | SSRF controls, domain policy, no personal browser profile | Form submit/download action-dependent |
| Productivity | Calendar/Drive/Notion/task manager | Per-provider OAuth scope and agent profile | External writes medium/high |
| Automation | Scheduler → durable jobs → webhooks | Persist before enqueue, signed inbound webhooks | Side-effect risk derived from target |
| Finance | Read-only summaries only | Separate account, no transaction permission | Transactions disabled |
| Jobs | Discovery → tracking → draft → submit | Site-specific adapters and evidence bundle | Every submit requires approval |

Integration is added only when its threat model, credential scope, audit schema,
failure behavior, disable path, and safe test are documented.

