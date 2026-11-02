BEGIN;

DO $migration$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM schema_migrations
                   WHERE version = '027_career_platform_discovery') THEN
        ALTER TABLE job_opportunities DROP CONSTRAINT IF EXISTS job_opportunities_source_check;
        ALTER TABLE job_opportunities ADD CONSTRAINT job_opportunities_source_check
            CHECK (source IN ('arbeitnow', 'ashby', 'greenhouse', 'lever',
                             'remotive', 'smartrecruiters'));
    END IF;
END
$migration$;

INSERT INTO schema_migrations (version) VALUES ('025_career_smartrecruiters')
ON CONFLICT (version) DO NOTHING;
COMMIT;
