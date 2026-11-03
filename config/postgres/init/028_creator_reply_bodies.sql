BEGIN;

ALTER TABLE creator_reply_messages
    ADD COLUMN IF NOT EXISTS body_status varchar(20) NOT NULL DEFAULT 'missing',
    ADD COLUMN IF NOT EXISTS body_text text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS body_format varchar(8),
    ADD COLUMN IF NOT EXISTS body_digest varchar(64),
    ADD COLUMN IF NOT EXISTS body_version varchar(40),
    ADD COLUMN IF NOT EXISTS body_attempt_count integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS body_attempted_at timestamptz,
    ADD COLUMN IF NOT EXISTS body_fetched_at timestamptz,
    ADD COLUMN IF NOT EXISTS body_error_code varchar(64),
    ADD COLUMN IF NOT EXISTS body_mailbox_key varchar(64),
    ADD COLUMN IF NOT EXISTS body_label_name varchar(225),
    ADD COLUMN IF NOT EXISTS body_capture_task_id uuid REFERENCES agent_tasks(id),
    ADD COLUMN IF NOT EXISTS body_capture_lease_id uuid,
    ADD COLUMN IF NOT EXISTS reviewed_body_digest varchar(64);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'creator_reply_body_shape') THEN
        ALTER TABLE creator_reply_messages ADD CONSTRAINT creator_reply_body_shape CHECK (
            body_status IN ('missing','reading','complete','unavailable','oversize','unsupported')
            AND body_attempt_count BETWEEN 0 AND 3
            AND char_length(body_text) <= 24000
            AND (body_format IS NULL OR body_format IN ('plain','html'))
            AND ((body_status = 'complete' AND length(body_text) > 0
                  AND body_format IS NOT NULL AND body_digest IS NOT NULL
                  AND body_digest ~ '^[0-9a-f]{64}$'
                  AND body_version IS NOT NULL AND body_fetched_at IS NOT NULL
                  AND body_mailbox_key IS NOT NULL AND body_label_name IS NOT NULL
                  AND body_error_code IS NULL)
                 OR (body_status <> 'complete' AND body_text = '' AND body_digest IS NULL))
        );
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS creator_replies_capture_pending
    ON creator_reply_messages(campaign_id,received_at)
    WHERE needs_review AND body_status IN ('missing','reading');

CREATE INDEX IF NOT EXISTS creator_reply_sync_failures
    ON agent_tasks ((payload->>'campaign_id'), (COALESCE(completed_at,dead_lettered_at)) DESC)
    WHERE kind = 'marketing.gmail_sync' AND status IN ('failed','dead_lettered');

INSERT INTO schema_migrations(version) VALUES ('028_creator_reply_bodies')
ON CONFLICT(version) DO NOTHING;
COMMIT;
