BEGIN;

ALTER TABLE career_profiles ADD COLUMN IF NOT EXISTS
    eligibility_facts jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE job_opportunities DROP CONSTRAINT IF EXISTS job_opportunities_source_check;
ALTER TABLE job_opportunities ADD CONSTRAINT job_opportunities_source_check
    CHECK (source IN ('arbeitnow', 'ashby', 'greenhouse', 'lever', 'remotive',
                     'smartrecruiters', 'yc'));

INSERT INTO schema_migrations(version) VALUES ('027_career_platform_discovery')
ON CONFLICT(version) DO NOTHING;
COMMIT;
