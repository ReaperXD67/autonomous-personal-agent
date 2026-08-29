BEGIN;

CREATE TABLE IF NOT EXISTS inference_invocations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id uuid NOT NULL REFERENCES agent_tasks(id) ON DELETE RESTRICT,
    purpose varchar(80) NOT NULL,
    provider varchar(40) NOT NULL CHECK (provider IN ('openrouter', 'ollama')),
    requested_models jsonb NOT NULL DEFAULT '[]'::jsonb,
    selected_model varchar(240),
    selected_provider varchar(120),
    status varchar(20) NOT NULL DEFAULT 'started' CHECK (
        status IN ('started', 'succeeded', 'failed')
    ),
    privacy_mode varchar(80) NOT NULL,
    prompt_tokens integer NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0),
    completion_tokens integer NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0),
    total_tokens integer NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    cost_credits numeric(20, 12) NOT NULL DEFAULT 0 CHECK (cost_credits >= 0),
    latency_ms integer CHECK (latency_ms IS NULL OR latency_ms >= 0),
    fallback_attempt integer CHECK (fallback_attempt IS NULL OR fallback_attempt >= 1),
    error_code varchar(120),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_inference_invocations_task
    ON inference_invocations (task_id, created_at);
CREATE INDEX IF NOT EXISTS idx_inference_invocations_provider_day
    ON inference_invocations (provider, created_at DESC);

INSERT INTO schema_migrations (version)
VALUES ('008_free_model_routing')
ON CONFLICT (version) DO NOTHING;

COMMIT;
