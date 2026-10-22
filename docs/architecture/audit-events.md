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

Creator drafting emits `creator_draft.created`, `creator_draft.ready` and
`creator_draft.failed` with draft identity, route source and a bounded error code.
These events and the inference ledger do not include copy or contact data.
The separate `creator_email_drafts` product table intentionally stores the
reviewable message, sanitized prompt context and private input snapshot so
preparation can verify exact provenance; it is not general model telemetry.

Creator shortlist research emits `creator.pilot.created` with its campaign,
reserved batch size and canonical payload hash, then `creator.pilot.researched`
for completed creator refreshes. The creation audit binds the exact task to its
server-issued reservation; generic task submissions cannot reuse that authority.
The shared rolling allowance counts issued reservations even if a task fails or
is cancelled. Research audit records include no addresses, raw descriptions,
message copy or authorization grants.

Audit events are append-oriented. Product tables may project current status,
but forensic timelines use event rows ordered by `occurred_at`. Deletion and
export policies remain planned because personal data retention requirements
depend on final deployment jurisdiction and use.

Execution-lifecycle actions include `task.started`, `task.recovered`,
`task.cancellation_requested`, `task.cancelled`, `task.succeeded`,
`task.failed`, and `task.dead_lettered`. Retry audit metadata contains only the
attempt number and delay, never payload contents. Heartbeats update lease state
without producing one audit row per interval to avoid unbounded audit volume.
