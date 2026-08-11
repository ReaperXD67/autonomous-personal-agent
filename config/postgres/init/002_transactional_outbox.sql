BEGIN;

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

INSERT INTO schema_migrations (version)
VALUES ('002_transactional_outbox')
ON CONFLICT (version) DO NOTHING;

COMMIT;
