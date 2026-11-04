BEGIN;

ALTER TABLE creator_reply_drafts
    ADD COLUMN IF NOT EXISTS attempt_number integer NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS retry_of_id uuid REFERENCES creator_reply_drafts(id);
ALTER TABLE creator_reply_drafts DROP CONSTRAINT IF EXISTS creator_reply_drafts_input_hash_key;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='creator_reply_draft_attempt_shape') THEN
        ALTER TABLE creator_reply_drafts ADD CONSTRAINT creator_reply_draft_attempt_shape CHECK (
            (attempt_number=1 AND retry_of_id IS NULL)
            OR (attempt_number=2 AND retry_of_id IS NOT NULL AND retry_of_id<>id)
        );
    END IF;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS creator_reply_draft_context_attempt
    ON creator_reply_drafts(input_hash,attempt_number);
CREATE UNIQUE INDEX IF NOT EXISTS creator_reply_draft_one_recovery
    ON creator_reply_drafts(retry_of_id) WHERE retry_of_id IS NOT NULL;

INSERT INTO schema_migrations(version) VALUES ('030_creator_reply_draft_recovery')
ON CONFLICT(version) DO NOTHING;
COMMIT;
