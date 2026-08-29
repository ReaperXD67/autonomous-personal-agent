BEGIN;

CREATE TABLE IF NOT EXISTS marketing_campaigns (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name varchar(160) NOT NULL,
    product_name varchar(160) NOT NULL,
    product_url varchar(2048) NOT NULL CHECK (product_url ~ '^https://'),
    privacy_url varchar(2048) NOT NULL CHECK (privacy_url ~ '^https://'),
    product_summary varchar(1200) NOT NULL,
    target_audience varchar(500) NOT NULL,
    viewer_offer varchar(1000) NOT NULL,
    creator_offer varchar(1000) NOT NULL,
    paid_offer_enabled boolean NOT NULL DEFAULT true,
    paid_offer_details varchar(1200),
    sender_name varchar(160) NOT NULL,
    discovery_queries text[] NOT NULL,
    relevance_language varchar(16) NOT NULL DEFAULT 'en',
    region_code varchar(2),
    min_subscribers bigint NOT NULL DEFAULT 1000,
    max_subscribers bigint NOT NULL DEFAULT 250000,
    max_video_age_days integer NOT NULL DEFAULT 120,
    results_per_query integer NOT NULL DEFAULT 10,
    schedule_hours integer NOT NULL DEFAULT 24,
    adaptive_mode boolean NOT NULL DEFAULT true,
    active boolean NOT NULL DEFAULT false,
    next_scan_at timestamptz NOT NULL DEFAULT now(),
    last_scan_at timestamptz,
    created_by varchar(120) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (cardinality(discovery_queries) BETWEEN 1 AND 3),
    CHECK (
        relevance_language ~ '^[A-Za-z]{2}$'
        OR relevance_language IN ('zh-Hans', 'zh-Hant')
    ),
    CHECK (region_code IS NULL OR region_code ~ '^[A-Z]{2}$'),
    CHECK (min_subscribers >= 0),
    CHECK (max_subscribers >= min_subscribers),
    CHECK (max_video_age_days BETWEEN 7 AND 365),
    CHECK (results_per_query BETWEEN 1 AND 25),
    CHECK (schedule_hours BETWEEN 24 AND 168),
    CHECK (paid_offer_enabled = false OR paid_offer_details IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_marketing_campaigns_due
    ON marketing_campaigns (next_scan_at)
    WHERE active = true;

CREATE TABLE IF NOT EXISTS marketing_prospects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id uuid NOT NULL REFERENCES marketing_campaigns(id) ON DELETE CASCADE,
    platform varchar(40) NOT NULL CHECK (
        platform IN ('youtube', 'twitch', 'tiktok', 'discord', 'minecraft_server', 'blog', 'other')
    ),
    external_id varchar(500) NOT NULL,
    display_name varchar(300) NOT NULL,
    profile_url varchar(2048) NOT NULL CHECK (profile_url ~ '^https://'),
    audience_size bigint CHECK (audience_size IS NULL OR audience_size >= 0),
    latest_content_title varchar(500),
    latest_content_url varchar(2048) CHECK (
        latest_content_url IS NULL OR latest_content_url ~ '^https://'
    ),
    latest_content_published_at timestamptz,
    discovery_query varchar(160),
    relevance_score integer NOT NULL DEFAULT 0 CHECK (relevance_score BETWEEN 0 AND 100),
    relevance_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
    contact_email varchar(320),
    contact_source_url varchar(2048) CHECK (
        contact_source_url IS NULL OR contact_source_url ~ '^https://'
    ),
    contact_basis_note varchar(1000),
    contact_authorized_at timestamptz,
    contact_authorized_by varchar(120),
    status varchar(40) NOT NULL DEFAULT 'discovered' CHECK (
        status IN (
            'discovered', 'qualified', 'question', 'declined_unpaid',
            'interested', 'converted', 'suppressed', 'bounced'
        )
    ),
    tracking_code varchar(32) NOT NULL UNIQUE
        DEFAULT substring(replace(gen_random_uuid()::text, '-', '') from 1 for 16),
    suppressed_at timestamptz,
    suppression_reason varchar(500),
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (campaign_id, platform, external_id),
    CHECK (
        (contact_authorized_at IS NULL AND contact_authorized_by IS NULL)
        OR (
            contact_email IS NOT NULL
            AND contact_source_url IS NOT NULL
            AND contact_basis_note IS NOT NULL
            AND contact_authorized_by IS NOT NULL
        )
    ),
    CHECK (
        status NOT IN ('suppressed', 'bounced')
        OR suppressed_at IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_marketing_prospects_campaign_status
    ON marketing_prospects (campaign_id, status, relevance_score DESC);
CREATE INDEX IF NOT EXISTS idx_marketing_prospects_contactable
    ON marketing_prospects (campaign_id, relevance_score DESC)
    WHERE contact_authorized_at IS NOT NULL AND suppressed_at IS NULL;

CREATE TABLE IF NOT EXISTS marketing_outreach_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    prospect_id uuid NOT NULL REFERENCES marketing_prospects(id) ON DELETE RESTRICT,
    action_id uuid NOT NULL UNIQUE REFERENCES external_actions(id) ON DELETE RESTRICT,
    stage varchar(40) NOT NULL CHECK (
        stage IN ('initial', 'question_reply', 'paid_offer')
    ),
    variant varchar(80) NOT NULL,
    selection_reason varchar(500) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (prospect_id, action_id)
);

CREATE INDEX IF NOT EXISTS idx_marketing_messages_prospect_stage
    ON marketing_outreach_messages (prospect_id, stage, created_at DESC);

CREATE TABLE IF NOT EXISTS marketing_outcomes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    prospect_id uuid NOT NULL REFERENCES marketing_prospects(id) ON DELETE RESTRICT,
    classification varchar(40) NOT NULL CHECK (
        classification IN (
            'question', 'declined_unpaid', 'interested', 'converted',
            'do_not_contact', 'bounced', 'promotion_published'
        )
    ),
    note varchar(4000),
    promotion_url varchar(2048) CHECK (
        promotion_url IS NULL OR promotion_url ~ '^https://'
    ),
    attributed_views integer NOT NULL DEFAULT 0 CHECK (attributed_views >= 0),
    attributed_clicks integer NOT NULL DEFAULT 0 CHECK (attributed_clicks >= 0),
    attributed_signups integer NOT NULL DEFAULT 0 CHECK (attributed_signups >= 0),
    attributed_server_owners integer NOT NULL DEFAULT 0 CHECK (attributed_server_owners >= 0),
    viewer_points_issued bigint NOT NULL DEFAULT 0 CHECK (viewer_points_issued >= 0),
    recorded_by varchar(120) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_marketing_outcomes_prospect_created
    ON marketing_outcomes (prospect_id, created_at DESC);

DROP TRIGGER IF EXISTS set_marketing_campaigns_updated_at ON marketing_campaigns;
CREATE TRIGGER set_marketing_campaigns_updated_at
BEFORE UPDATE ON marketing_campaigns
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS set_marketing_prospects_updated_at ON marketing_prospects;
CREATE TRIGGER set_marketing_prospects_updated_at
BEFORE UPDATE ON marketing_prospects
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

INSERT INTO schema_migrations (version)
VALUES ('007_creator_outreach')
ON CONFLICT (version) DO NOTHING;

COMMIT;
