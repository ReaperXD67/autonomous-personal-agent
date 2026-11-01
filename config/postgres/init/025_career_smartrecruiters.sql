BEGIN;

ALTER TABLE job_opportunities DROP CONSTRAINT IF EXISTS job_opportunities_source_check;
ALTER TABLE job_opportunities ADD CONSTRAINT job_opportunities_source_check
    CHECK (source IN ('arbeitnow', 'ashby', 'greenhouse', 'lever', 'remotive', 'smartrecruiters'));

INSERT INTO schema_migrations (version) VALUES ('025_career_smartrecruiters')
ON CONFLICT (version) DO NOTHING;
COMMIT;
