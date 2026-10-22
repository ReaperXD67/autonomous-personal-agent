CREATE TABLE IF NOT EXISTS creator_email_drafts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id uuid NOT NULL REFERENCES marketing_campaigns(id),
    prospect_id uuid NOT NULL REFERENCES marketing_prospects(id),
    task_id uuid UNIQUE REFERENCES agent_tasks(id),
    requested_by text NOT NULL,
    idempotency_key uuid NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'ready', 'prepared', 'failed')),
    input_snapshot jsonb NOT NULL,
    input_hash text NOT NULL,
    model_context jsonb NOT NULL,
    source text CHECK (source IN ('openrouter', 'ollama')),
    selected_model text,
    model_copy jsonb,
    subject text,
    body text,
    draft_digest text,
    error_code text,
    quality_notes jsonb NOT NULL DEFAULT '[]',
    action_id uuid UNIQUE REFERENCES external_actions(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT now() + interval '24 hours',
    CHECK (status NOT IN ('ready', 'prepared') OR
        (source IS NOT NULL AND selected_model IS NOT NULL AND model_copy IS NOT NULL
         AND subject IS NOT NULL AND body IS NOT NULL AND draft_digest IS NOT NULL)),
    CHECK (status <> 'prepared' OR action_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS creator_email_drafts_prospect_created
    ON creator_email_drafts (prospect_id, created_at DESC);

INSERT INTO schema_migrations (version) VALUES ('023_creator_ai_drafts')
ON CONFLICT DO NOTHING;
