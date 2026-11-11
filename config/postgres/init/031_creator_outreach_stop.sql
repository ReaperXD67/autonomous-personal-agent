BEGIN;

ALTER TABLE marketing_campaigns
    ADD COLUMN IF NOT EXISTS outreach_paused boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS outreach_epoch bigint NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS outreach_stopped_at timestamptz,
    ADD COLUMN IF NOT EXISTS outreach_stopped_by text,
    ADD COLUMN IF NOT EXISTS outreach_stop_reason text;

INSERT INTO schema_migrations(version) VALUES ('031_creator_outreach_stop')
ON CONFLICT(version) DO NOTHING;
COMMIT;
