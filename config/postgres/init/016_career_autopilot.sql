BEGIN;

ALTER TABLE job_opportunities ADD COLUMN IF NOT EXISTS published_at_basis varchar(10)
    NOT NULL DEFAULT 'unknown' CHECK (published_at_basis IN ('published', 'updated', 'unknown'));
ALTER TABLE job_opportunities DROP CONSTRAINT IF EXISTS job_opportunities_source_check;
ALTER TABLE job_opportunities ADD CONSTRAINT job_opportunities_source_check
    CHECK (source IN ('arbeitnow', 'ashby', 'greenhouse', 'lever', 'remotive'));

CREATE TABLE IF NOT EXISTS career_autopilot_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id uuid NOT NULL REFERENCES career_profiles(id),
    state text NOT NULL CHECK (state IN ('running', 'paused', 'expired')),
    mode text NOT NULL CHECK (mode IN ('prepare', 'apply')),
    profile_hash text NOT NULL,
    min_score integer NOT NULL CHECK (min_score BETWEEN 0 AND 100),
    max_age_hours integer NOT NULL CHECK (max_age_hours BETWEEN 1 AND 168),
    max_applications_per_day integer NOT NULL CHECK (max_applications_per_day BETWEEN 1 AND 10),
    allowed_hosts jsonb NOT NULL,
    answers jsonb NOT NULL DEFAULT '{}',
    include_cold_email boolean NOT NULL DEFAULT false,
    authorized_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    paused_at timestamptz,
    last_error text,
    last_mail_sync_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS career_autopilot_one_active
    ON career_autopilot_runs(profile_id) WHERE state = 'running';
CREATE TABLE IF NOT EXISTS career_autopilot_items (
    run_id uuid NOT NULL REFERENCES career_autopilot_runs(id),
    opportunity_id uuid NOT NULL REFERENCES job_opportunities(id),
    opportunity_hash text NOT NULL,
    state text NOT NULL DEFAULT 'preparing',
    reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, opportunity_id)
);
CREATE TABLE IF NOT EXISTS career_autopilot_actions (
    action_id uuid PRIMARY KEY REFERENCES external_actions(id),
    run_id uuid NOT NULL REFERENCES career_autopilot_runs(id),
    profile_id uuid NOT NULL REFERENCES career_profiles(id),
    opportunity_id uuid NOT NULL REFERENCES job_opportunities(id),
    target_key text NOT NULL,
    opportunity_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (profile_id, target_key)
);
CREATE INDEX IF NOT EXISTS career_autopilot_daily_budget
    ON career_autopilot_actions(profile_id, created_at);

CREATE TABLE IF NOT EXISTS career_source_requests (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source text NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS career_source_request_window
    ON career_source_requests(source, requested_at);
INSERT INTO schema_migrations (version) VALUES ('016_career_autopilot')
ON CONFLICT (version) DO NOTHING;
COMMIT;
