BEGIN;

ALTER TABLE task_outbox
    ADD COLUMN IF NOT EXISTS generation bigint NOT NULL DEFAULT 1
        CHECK (generation > 0);

CREATE INDEX IF NOT EXISTS idx_task_outbox_published_recovery
    ON task_outbox (published_at, task_id)
    WHERE published_at IS NOT NULL;

INSERT INTO schema_migrations (version)
VALUES ('010_outbox_generation')
ON CONFLICT (version) DO NOTHING;

COMMIT;
