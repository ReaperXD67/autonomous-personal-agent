# Audit event contract

Implemented `audit_events` captures:

- event timestamp and UUID;
- task ID and correlation ID;
- actor type/identity;
- tool/capability and action;
- risk level and approval status;
- execution status;
- bounded input/result metadata;
- error code/message;
- explicit `redacted` marker.

Raw bearer tokens, provider credentials, prompts, email bodies, browser cookies,
and arbitrary tool payloads must not enter audit rows. Current API records
payload keys, not values. Future tool adapters must define allowlisted metadata
schemas and retention periods before activation.

`inference_invocations` is a separate operational ledger rather than prompt
telemetry. It contains task/purpose, requested and selected model/provider,
status, privacy mode, token counts, latency, fallback attempt, error code, and
provider-reported cost. It explicitly omits prompt/completion text and secrets.

Audit events are append-oriented. Product tables may project current status,
but forensic timelines use event rows ordered by `occurred_at`. Deletion and
export policies remain planned because personal data retention requirements
depend on final deployment jurisdiction and use.

Execution-lifecycle actions include `task.started`, `task.recovered`,
`task.cancellation_requested`, `task.cancelled`, `task.succeeded`,
`task.failed`, and `task.dead_lettered`. Retry audit metadata contains only the
attempt number and delay, never payload contents. Heartbeats update lease state
without producing one audit row per interval to avoid unbounded audit volume.
