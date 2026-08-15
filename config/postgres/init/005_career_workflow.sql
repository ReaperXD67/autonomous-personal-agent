BEGIN;

CREATE TABLE IF NOT EXISTS career_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name varchar(120) NOT NULL,
    candidate_name varchar(160) NOT NULL,
    desired_titles text[] NOT NULL DEFAULT ARRAY[]::text[],
    skills text[] NOT NULL DEFAULT ARRAY[]::text[],
    required_keywords text[] NOT NULL DEFAULT ARRAY[]::text[],
    excluded_keywords text[] NOT NULL DEFAULT ARRAY[]::text[],
    locations text[] NOT NULL DEFAULT ARRAY[]::text[],
    remote_only boolean NOT NULL DEFAULT false,
    employment_types text[] NOT NULL DEFAULT ARRAY[]::text[],
    max_age_hours integer NOT NULL DEFAULT 72 CHECK (max_age_hours BETWEEN 1 AND 168),
    min_score integer NOT NULL DEFAULT 45 CHECK (min_score BETWEEN 0 AND 100),
    schedule_minutes integer NOT NULL DEFAULT 360 CHECK (schedule_minutes BETWEEN 360 AND 10080),
    source_config jsonb NOT NULL DEFAULT '{"arbeitnow": true, "ashby_boards": [], "greenhouse_boards": []}'::jsonb,
    resume_text text NOT NULL DEFAULT '' CHECK (char_length(resume_text) <= 100000),
    active boolean NOT NULL DEFAULT false,
    requested_by varchar(120) NOT NULL,
    next_scan_at timestamptz NOT NULL DEFAULT now(),
    last_scan_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_career_profiles_due
    ON career_profiles (next_scan_at)
    WHERE active = true;

CREATE TABLE IF NOT EXISTS job_opportunities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id uuid NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    source varchar(40) NOT NULL CHECK (source IN ('arbeitnow', 'ashby', 'greenhouse')),
    source_key varchar(240) NOT NULL,
    company varchar(240) NOT NULL,
    title varchar(300) NOT NULL,
    location varchar(300) NOT NULL DEFAULT '',
    description text NOT NULL DEFAULT '' CHECK (char_length(description) <= 100000),
    remote boolean NOT NULL DEFAULT false,
    employment_type varchar(80),
    source_url varchar(2048) NOT NULL,
    apply_url varchar(2048) NOT NULL,
    published_at timestamptz NOT NULL,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    score integer NOT NULL CHECK (score BETWEEN 0 AND 100),
    score_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
    status varchar(30) NOT NULL DEFAULT 'new' CHECK (
        status IN ('new', 'shortlisted', 'dismissed', 'applied')
    ),
    applied_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (profile_id, source, source_key)
);

CREATE INDEX IF NOT EXISTS idx_job_opportunities_profile_rank
    ON job_opportunities (profile_id, status, score DESC, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_opportunities_fresh
    ON job_opportunities (published_at DESC);

CREATE TABLE IF NOT EXISTS job_application_drafts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id uuid NOT NULL REFERENCES job_opportunities(id) ON DELETE CASCADE,
    profile_id uuid NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    task_id uuid NOT NULL UNIQUE REFERENCES agent_tasks(id) ON DELETE RESTRICT,
    model varchar(120) NOT NULL,
    content jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_job_application_drafts_opportunity
    ON job_application_drafts (opportunity_id, created_at DESC);

DROP TRIGGER IF EXISTS set_career_profiles_updated_at ON career_profiles;
CREATE TRIGGER set_career_profiles_updated_at
BEFORE UPDATE ON career_profiles
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS set_job_opportunities_updated_at ON job_opportunities;
CREATE TRIGGER set_job_opportunities_updated_at
BEFORE UPDATE ON job_opportunities
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

INSERT INTO schema_migrations (version)
VALUES ('005_career_workflow')
ON CONFLICT (version) DO NOTHING;

COMMIT;
