BEGIN;

ALTER TABLE agent_tasks
    ADD COLUMN IF NOT EXISTS lease_id uuid,
    ADD COLUMN IF NOT EXISTS claimed_by varchar(120),
    ADD COLUMN IF NOT EXISTS next_attempt_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS cancellation_requested_at timestamptz,
    ADD COLUMN IF NOT EXISTS cancellation_requested_by varchar(120),
    ADD COLUMN IF NOT EXISTS cancellation_reason varchar(500),
    ADD COLUMN IF NOT EXISTS dead_lettered_at timestamptz;

ALTER TABLE agent_tasks DROP CONSTRAINT IF EXISTS agent_tasks_status_check;
ALTER TABLE agent_tasks ADD CONSTRAINT agent_tasks_status_check CHECK (
    status IN (
        'pending_approval', 'queued', 'running', 'succeeded', 'failed',
        'rejected', 'cancelled', 'dead_lettered'
    )
);

ALTER TABLE task_outbox
    ADD COLUMN IF NOT EXISTS available_at timestamptz NOT NULL DEFAULT now();

DROP INDEX IF EXISTS idx_task_outbox_unpublished;
CREATE INDEX idx_task_outbox_unpublished
    ON task_outbox (available_at, created_at)
    WHERE published_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_agent_tasks_retry_ready
    ON agent_tasks (next_attempt_at, created_at)
    WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS idx_agent_tasks_dead_lettered
    ON agent_tasks (dead_lettered_at DESC)
    WHERE status = 'dead_lettered';

INSERT INTO schema_migrations (version)
VALUES ('004_execution_lifecycle')
ON CONFLICT (version) DO NOTHING;

COMMIT;
