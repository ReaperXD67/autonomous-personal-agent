BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS job_opportunities_identity_profile
    ON job_opportunities(id, profile_id);

CREATE TABLE IF NOT EXISTS career_contacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id uuid NOT NULL REFERENCES career_profiles(id),
    opportunity_id uuid NOT NULL REFERENCES job_opportunities(id),
    email text NOT NULL CHECK (email = lower(email)),
    kind text NOT NULL CHECK (kind IN ('hiring', 'hr', 'founder')),
    source_url text NOT NULL,
    evidence_quote text NOT NULL,
    basis_note text NOT NULL,
    reviewed_by varchar(120) NOT NULL,
    profile_hash text NOT NULL,
    opportunity_hash text NOT NULL,
    reviewed_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    revoked_by varchar(120),
    FOREIGN KEY (opportunity_id, profile_id) REFERENCES job_opportunities(id, profile_id),
    CHECK (expires_at > reviewed_at AND expires_at <= reviewed_at + interval '72 hours')
);
CREATE INDEX IF NOT EXISTS career_contacts_opportunity ON career_contacts(opportunity_id);

CREATE TABLE IF NOT EXISTS career_contact_actions (
    action_id uuid PRIMARY KEY REFERENCES external_actions(id),
    contact_id uuid NOT NULL UNIQUE REFERENCES career_contacts(id),
    profile_id uuid NOT NULL REFERENCES career_profiles(id),
    opportunity_id uuid NOT NULL REFERENCES job_opportunities(id),
    recipient text NOT NULL CHECK (recipient = lower(recipient)),
    target_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (profile_id, target_key, recipient)
);
CREATE INDEX IF NOT EXISTS external_actions_career_recipient
    ON external_actions((lower(private_context->>'recipient')), opportunity_id)
    WHERE action_type = 'communications.email_send';

INSERT INTO schema_migrations(version) VALUES ('026_career_contacts')
ON CONFLICT(version) DO NOTHING;
COMMIT;
