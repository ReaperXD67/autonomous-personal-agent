BEGIN;

CREATE TABLE IF NOT EXISTS agent_workflows (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    correlation_id uuid NOT NULL DEFAULT gen_random_uuid(),
    title varchar(200) NOT NULL,
    objective varchar(2000) NOT NULL DEFAULT '',
    requested_by varchar(120) NOT NULL,
    idempotency_key varchar(200) UNIQUE,
    specification_hash varchar(64) NOT NULL,
    status varchar(30) NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'cancelling', 'succeeded', 'failed', 'cancelled', 'timed_out')),
    max_parallel integer NOT NULL CHECK (max_parallel BETWEEN 1 AND 4),
    timeout_seconds integer NOT NULL CHECK (timeout_seconds BETWEEN 60 AND 86400),
    deadline_at timestamptz NOT NULL,
    stop_reason varchar(30) CHECK (stop_reason IN ('cancelled', 'timed_out')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    reconciled_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS workflow_steps (
    workflow_id uuid NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    key varchar(40) NOT NULL,
    position integer NOT NULL CHECK (position BETWEEN 0 AND 31),
    title varchar(200) NOT NULL,
    kind varchar(100) NOT NULL,
    payload jsonb NOT NULL,
    depends_on jsonb NOT NULL DEFAULT '[]'::jsonb,
    risk_level varchar(20) NOT NULL,
    expect_output jsonb NOT NULL DEFAULT '{}'::jsonb,
    status varchar(30) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'dispatched', 'succeeded', 'failed', 'skipped', 'cancelled')),
    task_id uuid UNIQUE REFERENCES agent_tasks(id) ON DELETE RESTRICT,
    error_code varchar(100),
    PRIMARY KEY (workflow_id, key),
    UNIQUE (workflow_id, position)
);

CREATE INDEX IF NOT EXISTS idx_workflow_reconcile
    ON agent_workflows (reconciled_at) WHERE status IN ('running', 'cancelling');

DROP TRIGGER IF EXISTS set_agent_workflows_updated_at ON agent_workflows;
CREATE TRIGGER set_agent_workflows_updated_at BEFORE UPDATE ON agent_workflows
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

INSERT INTO schema_migrations (version) VALUES ('009_durable_workflows')
ON CONFLICT (version) DO NOTHING;

COMMIT;
