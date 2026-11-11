BEGIN;

CREATE TABLE IF NOT EXISTS creator_reply_deferrals (
    id uuid PRIMARY KEY,
    campaign_id uuid NOT NULL REFERENCES marketing_campaigns(id),
    reply_id uuid NOT NULL REFERENCES creator_reply_messages(id),
    body_digest varchar(64) NOT NULL CHECK (body_digest ~ '^[0-9a-f]{64}$'),
    prospect_ids uuid[] NOT NULL CHECK (cardinality(prospect_ids) BETWEEN 1 AND 3),
    authorized_by varchar(120) NOT NULL CHECK (length(authorized_by)>0),
    reason text NOT NULL CHECK (length(reason) BETWEEN 10 AND 1000),
    idempotency_key uuid NOT NULL UNIQUE,
    duration_hours integer NOT NULL CHECK (duration_hours BETWEEN 1 AND 24),
    campaign_hash varchar(64) NOT NULL CHECK (campaign_hash ~ '^[0-9a-f]{64}$'),
    outreach_epoch bigint NOT NULL CHECK (outreach_epoch>=0),
    source_identity jsonb NOT NULL CHECK (jsonb_typeof(source_identity)='array'),
    prospect_identity_hashes jsonb NOT NULL CHECK (jsonb_typeof(prospect_identity_hashes)='object'),
    source_mailbox_key varchar(64) NOT NULL CHECK (source_mailbox_key ~ '^[0-9a-f]{64}$'),
    source_label_name varchar(225) NOT NULL CHECK (length(source_label_name)>0),
    scope_hash varchar(64) NOT NULL CHECK (scope_hash ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    revoked_by varchar(120),
    CHECK (expires_at>created_at AND expires_at<=created_at+interval '24 hours'),
    CHECK ((revoked_at IS NULL)=(revoked_by IS NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS creator_reply_deferral_one_unrevoked
    ON creator_reply_deferrals(campaign_id,reply_id) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS creator_reply_deferral_campaign
    ON creator_reply_deferrals(campaign_id,created_at DESC);

INSERT INTO schema_migrations(version) VALUES ('032_creator_reply_deferrals')
ON CONFLICT(version) DO NOTHING;
COMMIT;
