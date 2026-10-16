BEGIN;

ALTER TABLE marketing_campaigns
    ADD COLUMN IF NOT EXISTS outreach_mode varchar(16) NOT NULL DEFAULT 'community',
    ADD COLUMN IF NOT EXISTS compensation_model varchar(20) NOT NULL DEFAULT 'fixed_fee',
    ADD COLUMN IF NOT EXISTS revenue_share_percent double precision,
    ADD COLUMN IF NOT EXISTS revenue_share_weeks integer,
    ADD COLUMN IF NOT EXISTS revenue_share_basis varchar(500),
    ADD COLUMN IF NOT EXISTS handoff_name varchar(160),
    ADD COLUMN IF NOT EXISTS handoff_email varchar(320),
    ADD COLUMN IF NOT EXISTS handoff_discord varchar(40);

ALTER TABLE marketing_campaigns
    DROP CONSTRAINT IF EXISTS marketing_campaigns_compensation_check,
    ADD CONSTRAINT marketing_campaigns_compensation_check CHECK (
        compensation_model IN ('fixed_fee', 'revenue_share')
        AND (revenue_share_percent IS NULL OR revenue_share_percent > 0 AND revenue_share_percent <= 100)
        AND (revenue_share_weeks IS NULL OR revenue_share_weeks BETWEEN 1 AND 52)
    ),
    DROP CONSTRAINT IF EXISTS marketing_campaigns_outreach_mode_check,
    ADD CONSTRAINT marketing_campaigns_outreach_mode_check
        CHECK (outreach_mode IN ('community', 'paid')),
    DROP CONSTRAINT IF EXISTS marketing_campaigns_paid_handoff_check,
    ADD CONSTRAINT marketing_campaigns_paid_handoff_check CHECK (
        outreach_mode <> 'paid' OR (
            paid_offer_enabled AND nullif(btrim(paid_offer_details), '') IS NOT NULL
            AND (nullif(btrim(handoff_email), '') IS NOT NULL
                 OR nullif(btrim(handoff_discord), '') IS NOT NULL)
        )
    );

ALTER TABLE marketing_prospects
    DROP CONSTRAINT IF EXISTS marketing_prospects_status_check,
    ADD CONSTRAINT marketing_prospects_status_check CHECK (
        status IN (
            'discovered', 'qualified', 'question', 'declined_unpaid',
            'interested', 'handed_off', 'converted', 'suppressed', 'bounced'
        )
    );

ALTER TABLE marketing_outreach_messages
    DROP CONSTRAINT IF EXISTS marketing_outreach_messages_stage_check,
    ADD CONSTRAINT marketing_outreach_messages_stage_check CHECK (
        stage IN ('initial', 'question_reply', 'paid_offer', 'handoff')
    );

INSERT INTO schema_migrations (version)
VALUES ('020_creator_paid_handoff')
ON CONFLICT (version) DO NOTHING;

COMMIT;
