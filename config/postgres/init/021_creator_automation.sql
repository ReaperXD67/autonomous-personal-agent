BEGIN;

CREATE TABLE IF NOT EXISTS creator_contact_suppressions (
    email varchar(320) PRIMARY KEY CHECK (email = lower(email)),
    reason varchar(500) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
-- Upgrading must retain opt-outs recorded before the global address ledger existed.
INSERT INTO creator_contact_suppressions(email,reason)
SELECT lower(contact_email), COALESCE(suppression_reason,'Previously suppressed creator contact')
FROM marketing_prospects
WHERE suppressed_at IS NOT NULL AND contact_email IS NOT NULL AND length(trim(contact_email)) > 0
ON CONFLICT(email) DO NOTHING;

CREATE TABLE IF NOT EXISTS creator_automation_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id uuid NOT NULL REFERENCES marketing_campaigns(id) ON DELETE CASCADE,
    state varchar(20) NOT NULL CHECK (state IN ('running','paused','expired','blocked')),
    campaign_hash varchar(64) NOT NULL,
    max_initials_per_day integer NOT NULL CHECK (max_initials_per_day BETWEEN 1 AND 10),
    auto_handoff boolean NOT NULL DEFAULT false,
    monitor_gmail boolean NOT NULL DEFAULT false,
    authorized_by varchar(120) NOT NULL,
    reason varchar(500),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    paused_at timestamptz,
    next_tick_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS creator_automation_one_running
    ON creator_automation_runs(campaign_id) WHERE state = 'running';

CREATE TABLE IF NOT EXISTS creator_automation_actions (
    action_id uuid PRIMARY KEY REFERENCES external_actions(id) ON DELETE CASCADE,
    run_id uuid NOT NULL REFERENCES creator_automation_runs(id) ON DELETE CASCADE,
    campaign_id uuid NOT NULL REFERENCES marketing_campaigns(id) ON DELETE CASCADE,
    prospect_id uuid NOT NULL REFERENCES marketing_prospects(id) ON DELETE CASCADE,
    stage varchar(20) NOT NULL CHECK (stage IN ('initial','handoff')),
    recipient varchar(320) NOT NULL,
    creator_key varchar(2048) NOT NULL,
    context_hash varchar(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS creator_automation_daily
    ON creator_automation_actions(campaign_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS creator_automation_recipient_stage
    ON creator_automation_actions(lower(recipient), stage);
CREATE UNIQUE INDEX IF NOT EXISTS creator_automation_creator_stage
    ON creator_automation_actions(creator_key, stage);

CREATE TABLE IF NOT EXISTS creator_reply_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id uuid NOT NULL REFERENCES marketing_campaigns(id) ON DELETE CASCADE,
    gmail_message_id varchar(128) NOT NULL,
    gmail_thread_id varchar(128) NOT NULL,
    sender varchar(320) NOT NULL,
    subject varchar(500) NOT NULL,
    snippet varchar(600) NOT NULL,
    received_at timestamptz NOT NULL,
    prospect_id uuid REFERENCES marketing_prospects(id) ON DELETE SET NULL,
    suggested_classification varchar(40) NOT NULL,
    match_reason varchar(500) NOT NULL,
    needs_review boolean NOT NULL DEFAULT true,
    reviewed_by varchar(120),
    reviewed_at timestamptz,
    reviewed_classification varchar(40),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(campaign_id, gmail_message_id)
);
CREATE INDEX IF NOT EXISTS creator_replies_pending
    ON creator_reply_messages(campaign_id) WHERE needs_review;

CREATE TABLE IF NOT EXISTS creator_gmail_sync_state (
    campaign_id uuid PRIMARY KEY REFERENCES marketing_campaigns(id) ON DELETE CASCADE,
    mailbox_key varchar(64) NOT NULL,
    label_name varchar(225) NOT NULL,
    page_token varchar(2048),
    pending_message_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    revision integer NOT NULL DEFAULT 0,
    last_sync_at timestamptz,
    last_complete_at timestamptz
);

INSERT INTO schema_migrations(version) VALUES ('021_creator_automation')
ON CONFLICT(version) DO NOTHING;
COMMIT;
