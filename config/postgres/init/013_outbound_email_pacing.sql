BEGIN;

CREATE TABLE IF NOT EXISTS outbound_email_schedule (
    action_id uuid PRIMARY KEY REFERENCES external_actions(id) ON DELETE RESTRICT,
    task_id uuid NOT NULL UNIQUE REFERENCES agent_tasks(id) ON DELETE RESTRICT,
    recipient_domain varchar(253) NOT NULL,
    scheduled_for timestamptz NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'scheduled' CHECK (
        status IN ('scheduled', 'sending', 'accepted', 'skipped', 'ambiguous')
    ),
    min_interval_seconds integer NOT NULL CHECK (min_interval_seconds >= 60),
    domain_min_interval_seconds integer NOT NULL CHECK (
        domain_min_interval_seconds >= min_interval_seconds
    ),
    hourly_limit integer NOT NULL CHECK (hourly_limit BETWEEN 1 AND 10),
    daily_limit integer NOT NULL CHECK (daily_limit BETWEEN hourly_limit AND 50),
    jitter_seconds integer NOT NULL CHECK (jitter_seconds BETWEEN 0 AND 900),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_outbound_email_schedule_active_time
    ON outbound_email_schedule (scheduled_for)
    WHERE status IN ('scheduled', 'sending', 'accepted', 'ambiguous');
CREATE INDEX IF NOT EXISTS idx_outbound_email_schedule_active_domain_time
    ON outbound_email_schedule (recipient_domain, scheduled_for)
    WHERE status IN ('scheduled', 'sending', 'accepted', 'ambiguous');

INSERT INTO schema_migrations (version)
VALUES ('013_outbound_email_pacing')
ON CONFLICT (version) DO NOTHING;

COMMIT;
