BEGIN;

ALTER TABLE task_approvals
    ADD COLUMN IF NOT EXISTS action_context_hash varchar(64);

ALTER TABLE career_profiles
    ADD COLUMN IF NOT EXISTS application_identity jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS auto_prepare boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS auto_prepare_min_score integer NOT NULL DEFAULT 75,
    ADD COLUMN IF NOT EXISTS max_auto_prepare_per_scan integer NOT NULL DEFAULT 3;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'career_profiles_auto_prepare_min_score_check'
    ) THEN
        ALTER TABLE career_profiles
            ADD CONSTRAINT career_profiles_auto_prepare_min_score_check
            CHECK (auto_prepare_min_score BETWEEN 0 AND 100);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'career_profiles_max_auto_prepare_per_scan_check'
    ) THEN
        ALTER TABLE career_profiles
            ADD CONSTRAINT career_profiles_max_auto_prepare_per_scan_check
            CHECK (max_auto_prepare_per_scan BETWEEN 1 AND 10);
    END IF;
END;
$$;

ALTER TABLE job_opportunities DROP CONSTRAINT IF EXISTS job_opportunities_source_check;
ALTER TABLE job_opportunities ADD CONSTRAINT job_opportunities_source_check
    CHECK (source IN ('arbeitnow', 'ashby', 'greenhouse', 'lever'));

CREATE TABLE IF NOT EXISTS job_application_preflights (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id uuid NOT NULL REFERENCES job_opportunities(id) ON DELETE CASCADE,
    task_id uuid NOT NULL UNIQUE REFERENCES agent_tasks(id) ON DELETE RESTRICT,
    apply_url varchar(2048) NOT NULL,
    final_url varchar(2048) NOT NULL,
    form_signature varchar(64),
    fields jsonb NOT NULL DEFAULT '[]'::jsonb,
    submit_label varchar(160),
    blocked_reason varchar(160),
    has_captcha boolean NOT NULL DEFAULT false,
    has_login boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_job_application_preflights_opportunity
    ON job_application_preflights (opportunity_id, created_at DESC);

CREATE TABLE IF NOT EXISTS external_actions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id uuid UNIQUE REFERENCES agent_tasks(id) ON DELETE RESTRICT,
    opportunity_id uuid REFERENCES job_opportunities(id) ON DELETE SET NULL,
    action_type varchar(80) NOT NULL CHECK (
        action_type IN ('career.application_submit', 'communications.email_send')
    ),
    status varchar(40) NOT NULL CHECK (
        status IN (
            'pending_approval', 'queued', 'executing', 'succeeded', 'failed',
            'rejected', 'cancelled', 'ambiguous'
        )
    ),
    target_display varchar(500) NOT NULL,
    public_context jsonb NOT NULL,
    private_context jsonb NOT NULL,
    context_hash varchar(64) NOT NULL CHECK (context_hash ~ '^[0-9a-f]{64}$'),
    idempotency_key varchar(200) NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    external_reference varchar(500),
    last_error varchar(1000),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    executed_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_external_actions_status_created
    ON external_actions (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_external_actions_opportunity
    ON external_actions (opportunity_id, created_at DESC)
    WHERE opportunity_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS side_effect_receipts (
    fingerprint varchar(64) PRIMARY KEY CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    action_id uuid NOT NULL UNIQUE REFERENCES external_actions(id) ON DELETE RESTRICT,
    task_id uuid NOT NULL UNIQUE REFERENCES agent_tasks(id) ON DELETE RESTRICT,
    status varchar(20) NOT NULL CHECK (status IN ('executing', 'succeeded', 'ambiguous')),
    external_reference varchar(500),
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

DROP TRIGGER IF EXISTS set_external_actions_updated_at ON external_actions;
CREATE TRIGGER set_external_actions_updated_at
BEFORE UPDATE ON external_actions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

INSERT INTO schema_migrations (version)
VALUES ('006_exact_external_actions')
ON CONFLICT (version) DO NOTHING;

COMMIT;
