BEGIN;

CREATE TABLE IF NOT EXISTS creator_reply_drafts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id uuid NOT NULL REFERENCES marketing_campaigns(id),
    reply_id uuid NOT NULL REFERENCES creator_reply_messages(id),
    prospect_id uuid NOT NULL REFERENCES marketing_prospects(id),
    task_id uuid UNIQUE REFERENCES agent_tasks(id),
    requested_by varchar(120) NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','ready','failed')),
    reply_body_digest varchar(64) NOT NULL,
    input_snapshot jsonb NOT NULL,
    input_hash varchar(64) NOT NULL UNIQUE,
    model_context jsonb NOT NULL,
    source varchar(20) CHECK (source IS NULL OR source = 'ollama'),
    selected_model text,
    model_copy jsonb,
    subject varchar(600),
    body text,
    draft_digest varchar(64),
    error_code varchar(80),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT now() + interval '24 hours',
    CHECK (status <> 'ready' OR (source = 'ollama' AND selected_model IS NOT NULL
        AND model_copy IS NOT NULL AND subject IS NOT NULL AND body IS NOT NULL
        AND draft_digest IS NOT NULL)),
    CHECK (body IS NULL OR char_length(body) <= 20000)
);
CREATE INDEX IF NOT EXISTS creator_reply_drafts_reply_created
    ON creator_reply_drafts(reply_id,created_at DESC);
CREATE INDEX IF NOT EXISTS creator_reply_drafts_budget
    ON creator_reply_drafts(created_at,prospect_id);

CREATE UNIQUE INDEX IF NOT EXISTS creator_reply_draft_one_inference
    ON inference_invocations(task_id) WHERE purpose = 'marketing.creator_reply_draft';

INSERT INTO schema_migrations(version) VALUES ('029_creator_reply_drafts')
ON CONFLICT(version) DO NOTHING;
COMMIT;
