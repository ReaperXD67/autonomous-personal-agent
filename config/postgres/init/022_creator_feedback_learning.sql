ALTER TABLE marketing_outcomes
    ADD COLUMN IF NOT EXISTS feedback_tags jsonb NOT NULL DEFAULT '[]'::jsonb;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'marketing_feedback_tags_check') THEN
        ALTER TABLE marketing_outcomes ADD CONSTRAINT marketing_feedback_tags_check CHECK (
            jsonb_typeof(feedback_tags) = 'array' AND jsonb_array_length(feedback_tags) <= 8
            AND feedback_tags <@ '["too_generic","unclear_offer","unclear_revenue_share","prefers_fixed_fee","weak_content_fit","unclear_attribution","too_long","unclear_next_step"]'::jsonb
        );
    END IF;
END $$;

INSERT INTO schema_migrations (version) VALUES ('022_creator_feedback_learning')
ON CONFLICT DO NOTHING;
