BEGIN;

CREATE TABLE IF NOT EXISTS career_gmail_sync_state (
    profile_id uuid PRIMARY KEY REFERENCES career_profiles(id) ON DELETE CASCADE,
    mailbox_key varchar(64) NOT NULL,
    label_name varchar(225) NOT NULL,
    page_token varchar(2048),
    pending_message_ids jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(pending_message_ids) = 'array'),
    revision bigint NOT NULL DEFAULT 0,
    last_sync_at timestamptz
);

CREATE TABLE IF NOT EXISTS career_gmail_messages (
    profile_id uuid NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    gmail_message_id varchar(128) NOT NULL,
    gmail_thread_id varchar(128) NOT NULL,
    sender varchar(320) NOT NULL,
    subject varchar(500) NOT NULL,
    snippet varchar(600) NOT NULL,
    received_at timestamptz NOT NULL,
    opportunity_id uuid REFERENCES job_opportunities(id) ON DELETE SET NULL,
    suggested_status varchar(30) NOT NULL CHECK (suggested_status IN (
        'submitted', 'acknowledgement', 'recruiter_reply', 'interview', 'rejected',
        'offer', 'withdrawn', 'needs_review'
    )),
    confidence varchar(20) NOT NULL CHECK (confidence IN ('high', 'medium', 'low', 'manual')),
    evidence varchar(1000) NOT NULL,
    match_reason varchar(300) NOT NULL,
    meeting_at timestamptz,
    needs_review boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, gmail_message_id)
);

CREATE TABLE IF NOT EXISTS career_gmail_threads (
    profile_id uuid NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    gmail_thread_id varchar(128) NOT NULL,
    opportunity_id uuid NOT NULL REFERENCES job_opportunities(id) ON DELETE CASCADE,
    sender_domain varchar(253) NOT NULL,
    source varchar(20) NOT NULL CHECK (source IN ('manual', 'gmail')),
    PRIMARY KEY (profile_id, gmail_thread_id)
);

CREATE TABLE IF NOT EXISTS career_application_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id uuid NOT NULL REFERENCES job_opportunities(id) ON DELETE CASCADE,
    profile_id uuid NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    status varchar(30) NOT NULL CHECK (status IN (
        'submitted', 'acknowledgement', 'recruiter_reply', 'interview', 'rejected',
        'offer', 'withdrawn', 'needs_review'
    )),
    source varchar(20) NOT NULL CHECK (source IN ('manual', 'gmail')),
    confidence varchar(20) NOT NULL CHECK (confidence IN ('high', 'medium', 'low', 'manual')),
    evidence varchar(1000) NOT NULL,
    occurred_at timestamptz NOT NULL,
    meeting_at timestamptz,
    needs_review boolean NOT NULL DEFAULT false,
    gmail_message_id varchar(128),
    actor varchar(120) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_career_gmail_event_once
    ON career_application_events (profile_id, gmail_message_id) WHERE source = 'gmail';
CREATE INDEX IF NOT EXISTS idx_career_events_opportunity
    ON career_application_events (opportunity_id, occurred_at DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_career_gmail_review
    ON career_gmail_messages (profile_id, received_at DESC) WHERE opportunity_id IS NULL;

INSERT INTO schema_migrations (version) VALUES ('017_career_tracking')
ON CONFLICT (version) DO NOTHING;
COMMIT;
