BEGIN;

ALTER TABLE marketing_campaigns
    ADD COLUMN IF NOT EXISTS country_mode varchar(8) NOT NULL DEFAULT 'any'
        CHECK (country_mode IN ('any', 'prefer', 'strict')),
    ADD COLUMN IF NOT EXISTS target_country varchar(2)
        CHECK (target_country IS NULL OR target_country ~ '^[A-Z]{2}$'),
    ADD COLUMN IF NOT EXISTS language_mode varchar(8) NOT NULL DEFAULT 'any'
        CHECK (language_mode IN ('any', 'prefer', 'strict')),
    ADD COLUMN IF NOT EXISTS target_language varchar(30)
        CHECK (target_language IS NULL OR target_language ~ '^[a-z]{2,3}(-[a-z0-9]{2,8}){0,3}$'),
    ADD COLUMN IF NOT EXISTS last_discovery_summary jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(last_discovery_summary) = 'object');

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'marketing_country_target_required') THEN
        ALTER TABLE marketing_campaigns ADD CONSTRAINT marketing_country_target_required
            CHECK (country_mode = 'any' OR target_country IS NOT NULL);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'marketing_language_target_required') THEN
        ALTER TABLE marketing_campaigns ADD CONSTRAINT marketing_language_target_required
            CHECK (language_mode = 'any' OR target_language IS NOT NULL);
    END IF;
END $$;

INSERT INTO schema_migrations (version)
VALUES ('015_creator_targeting')
ON CONFLICT (version) DO NOTHING;

COMMIT;
