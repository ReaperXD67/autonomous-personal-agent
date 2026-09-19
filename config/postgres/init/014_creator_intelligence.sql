BEGIN;

ALTER TABLE marketing_prospects
    ADD COLUMN IF NOT EXISTS intelligence jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(intelligence) = 'object');

INSERT INTO schema_migrations (version)
VALUES ('014_creator_intelligence')
ON CONFLICT (version) DO NOTHING;

COMMIT;
