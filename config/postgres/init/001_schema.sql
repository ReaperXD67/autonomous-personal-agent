BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_tasks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    correlation_id uuid NOT NULL DEFAULT gen_random_uuid(),
    title varchar(200) NOT NULL,
    kind varchar(100) NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    output jsonb,
    risk_level varchar(20) NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'destructive')),
    status varchar(30) NOT NULL CHECK (status IN ('pending_approval', 'queued', 'running', 'succeeded', 'failed', 'rejected', 'cancelled')),
    requested_by varchar(120) NOT NULL,
    approved_by varchar(120),
    approved_at timestamptz,
    error_code varchar(100),
    error_message text,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 10),
    last_heartbeat_at timestamptz,
    lease_expires_at timestamptz,
    idempotency_key varchar(200) UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_agent_tasks_status_created
    ON agent_tasks (status, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_correlation
    ON agent_tasks (correlation_id);
CREATE TABLE IF NOT EXISTS task_approvals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id uuid NOT NULL REFERENCES agent_tasks(id) ON DELETE RESTRICT,
    decision varchar(20) NOT NULL CHECK (decision IN ('approved', 'rejected')),
    actor varchar(120) NOT NULL,
    reason varchar(500),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    correlation_id uuid NOT NULL,
    task_id uuid REFERENCES agent_tasks(id) ON DELETE SET NULL,
    actor_type varchar(40) NOT NULL,
    actor_id varchar(120) NOT NULL,
    tool_name varchar(160),
    action varchar(160) NOT NULL,
    risk_level varchar(20) NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'destructive')),
    approval_status varchar(30) NOT NULL,
    execution_status varchar(30) NOT NULL,
    input_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    result_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_code varchar(100),
    error_message text,
    redacted boolean NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_audit_events_task_time
    ON audit_events (task_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_correlation_time
    ON audit_events (correlation_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS task_outbox (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id uuid NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
    correlation_id uuid NOT NULL,
    topic varchar(120) NOT NULL,
    payload jsonb NOT NULL,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    UNIQUE (task_id, topic)
);

CREATE INDEX IF NOT EXISTS idx_task_outbox_unpublished
    ON task_outbox (created_at)
    WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS memory_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace varchar(120) NOT NULL,
    memory_type varchar(40) NOT NULL,
    content text NOT NULL,
    content_hash varchar(64) NOT NULL,
    embedding vector(1536),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_task_id uuid REFERENCES agent_tasks(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    UNIQUE (namespace, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_memory_records_namespace_type
    ON memory_records (namespace, memory_type);
CREATE INDEX IF NOT EXISTS idx_memory_records_embedding_hnsw
    ON memory_records USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_agent_tasks_updated_at ON agent_tasks;
CREATE TRIGGER set_agent_tasks_updated_at
BEFORE UPDATE ON agent_tasks
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS set_memory_records_updated_at ON memory_records;
CREATE TRIGGER set_memory_records_updated_at
BEFORE UPDATE ON memory_records
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

INSERT INTO schema_migrations (version)
VALUES ('001_foundation')
ON CONFLICT (version) DO NOTHING;

COMMIT;
