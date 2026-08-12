BEGIN;

ALTER TABLE agent_tasks
    ADD COLUMN IF NOT EXISTS max_attempts integer NOT NULL DEFAULT 3,
    ADD COLUMN IF NOT EXISTS last_heartbeat_at timestamptz,
    ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'agent_tasks_max_attempts_check'
    ) THEN
        ALTER TABLE agent_tasks
            ADD CONSTRAINT agent_tasks_max_attempts_check
            CHECK (max_attempts BETWEEN 1 AND 10);
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_agent_tasks_expired_lease
    ON agent_tasks (lease_expires_at)
    WHERE status = 'running';

INSERT INTO schema_migrations (version)
VALUES ('003_worker_leases')
ON CONFLICT (version) DO NOTHING;

COMMIT;
