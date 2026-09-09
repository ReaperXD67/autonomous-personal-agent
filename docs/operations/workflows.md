# Durable workflows

Workflows coordinate the existing capabilities into bounded plans. They provide
durable execution and explicit result checks, not general intelligence or an
autonomous model planner. Inputs are fixed at creation; every capability still
enters the control-plane policy, task, audit, and outbox path.

## Use the dashboard

Start the normal private dashboard and open **Workflows**. Choose:

- **Safe parallel demo:** four harmless foundation steps demonstrate a fork,
  join, and verified completion without inference or external requests.
- **Application preparation:** select an existing opportunity. Generate a
  draft, require `draft_created: true`, then inspect its form and require
  `blocked_reason: null`. This needs the configured drafting route and action
  worker; it does not submit the application.
- **Custom plan:** edit a JSON step list using the enabled capabilities.

Set a title, objective, parallel task limit, and deadline. Inspect the run to see
dependencies, expected results, task state, failure reasons, and task audit
links. The page refreshes progress without discarding the form. **Stop workflow**
prevents new steps and cancels or interrupts existing ones cooperatively.

## API example

Authenticated scripts can submit the same plan using `POST /v1/workflows`:

```json
{
  "title": "Verify a dependent plan",
  "objective": "Complete only after the expected evidence is present",
  "requested_by": "operator",
  "idempotency_key": "example-workflow-001",
  "max_parallel": 2,
  "timeout_seconds": 300,
  "steps": [
    {
      "key": "signal",
      "title": "Verify the starting signal",
      "kind": "foundation.echo",
      "payload": {"message": "ready"},
      "expect_output": {"echo": "ready"}
    },
    {
      "key": "finish",
      "title": "Verify completion",
      "kind": "foundation.echo",
      "payload": {"message": "done"},
      "depends_on": ["signal"],
      "expect_output": {"echo": "done"}
    }
  ]
}
```

Use `GET /v1/workflows` or `GET /v1/workflows/{id}` for state.
`POST /v1/workflows/{id}/cancel` accepts `{"actor":"operator"}` plus an optional
reason. Reusing an idempotency key with the same normalized plan returns the
original workflow; a different plan returns HTTP 409. No update endpoint exists.

| Capability | Payload |
|---|---|
| `foundation.echo` | `message` string, up to 2,000 characters |
| `foundation.wait` | `seconds`, finite number from 0 through 60 |
| `career.search` | `profile_id` UUID |
| `career.application_draft` | `profile_id` and `opportunity_id` UUIDs |
| `career.application_preflight` | `opportunity_id` UUID; optional `profile_id` |
| `marketing.creator_discovery` | `campaign_id` UUID |

Step keys are unique, start with a letter, and use up to 40 letters, numbers,
underscores, or hyphens. A plan permits 1–32 steps, 1–4 concurrent task slots, a
60–86,400 second timeout, and up to 64 KiB of normalized specification. A step
can check at most eight exact top-level scalar output fields. `null` means the
field must exist and be null; a missing field fails. Numbers compare by numeric
value; strings and booleans are never coerced. No expressions, nested paths,
output substitution, or generated tool names are evaluated.

## Outcome and recovery semantics

All dependencies must succeed before a step starts. A worker success without
the expected evidence becomes `OUTPUT_CHECK_FAILED` at the workflow step while
the underlying task retains its actual execution result. Failed, rejected,
cancelled, or dead-lettered steps skip their descendants. Independent branches
continue. A workflow succeeds only when every step passes.

An elevated-risk step waits in the ordinary approval inbox and occupies a
concurrency slot. The coordinator never approves it. Workflow-managed search,
draft, and preflight suppress automatic child tasks so the submitted step limit
cannot expand through normal career automation. You may separately prepare an
exact application action from the opportunity after reviewing the completed
workflow. External email/send capabilities cannot be put in a workflow.

Each step uses the existing task retry budget, at most three attempts. The
workflow deadline includes queue time, approvals, and retry delay. Expiry stops
new dispatch and requests cancellation; an already-running call may finish
before it observes cancellation. `cancelling` remains visible until workers or
lease recovery resolve all children. Completion after the deadline is timed out.
Stopping the stack delays work; it does not pause the stored deadline.

The dispatcher reconstructs due queued signals that have been published for at
least 60 seconds without being claimed. This covers Redis loss and a worker
crashing between queue removal and PostgreSQL claim. Duplicate signals are
discarded by durable task state. Outbox delivery generations protect newer
signals from stale acknowledgments. This does not retry an already-completed
external action or extend its one-attempt policy.

## Validation and diagnosis

Upgrade by rebuilding the core and running the normal Compose startup. Migrations
009 and 010 add workflow tables and outbox generation state without removing
existing task data. Before rolling application code back, stop active workflows
and wait for their children to settle; older dispatchers do not coordinate them.
Keep the additive schema in place. Data rollback uses the existing verified
backup/restore procedure, not ad-hoc table or volume deletion.

```powershell
./scripts/test.ps1
./scripts/verify.ps1
# Re-run only the isolated workflow proof against a running core:
./scripts/workflow-smoke.ps1
```

The test command rebuilds its image to avoid testing stale source. Full
verification includes workflow and queue-recovery probes. The workflow probe
creates a randomly named disposable PostgreSQL database and applies the
committed migrations; the queue probe uses an isolated synthetic schema. Both
clean up their own fixtures and make no model or external-network requests.

For a stalled run inspect its child task and audit first. `pending_approval`
requires a decision; `queued` may mean the corresponding worker is not running;
`running` retains owned lease/heartbeat state. A failed result check means
execution finished but the requested evidence was not present. No reset,
automatic replan, or hidden retry of a completed plan occurs.

If a future deployment's capability policy invalidates an older saved step, the
coordinator fails that step with `STEP_POLICY_REJECTED` and blocks its dependents.
Other workflows continue; the invalid step is never dispatched.
