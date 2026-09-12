BEGIN;

CREATE TABLE IF NOT EXISTS goal_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    correlation_id uuid NOT NULL DEFAULT gen_random_uuid(),
    goal varchar(2000) NOT NULL,
    requested_by varchar(120) NOT NULL,
    mode varchar(10) NOT NULL CHECK (mode IN ('model', 'demo')),
    request_context jsonb NOT NULL,
    action_inventory jsonb NOT NULL,
    request_hash varchar(64) NOT NULL,
    idempotency_key varchar(200) UNIQUE,
    task_id uuid UNIQUE REFERENCES agent_tasks(id) ON DELETE RESTRICT,
    status varchar(20) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'ready', 'unsupported', 'failed', 'adopted')),
    source varchar(20) CHECK (source IN ('openrouter', 'ollama', 'template')),
    selected_model varchar(240),
    summary varchar(800),
    limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
    workflow_spec jsonb,
    plan_digest varchar(64),
    workflow_id uuid UNIQUE REFERENCES agent_workflows(id) ON DELETE RESTRICT,
    error_code varchar(100),
    adopted_by varchar(120),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT now() + interval '24 hours',
    CHECK ((workflow_spec IS NULL) = (plan_digest IS NULL)),
    CHECK (status <> 'adopted' OR workflow_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_goal_plans_created ON goal_plans (created_at DESC);

INSERT INTO schema_migrations (version) VALUES ('011_goal_plans')
ON CONFLICT (version) DO NOTHING;

COMMIT;
