BEGIN;

ALTER TABLE career_autopilot_items
    ADD COLUMN IF NOT EXISTS action_id uuid REFERENCES external_actions(id);

-- Existing authorization reservations establish an exact, unambiguous link.
-- Preparation-only history has no durable link and is not guessed from recency.
UPDATE career_autopilot_items i SET action_id = a.action_id
FROM career_autopilot_actions a
WHERE a.run_id = i.run_id AND a.opportunity_id = i.opportunity_id
  AND i.action_id IS NULL;

CREATE INDEX IF NOT EXISTS career_autopilot_items_run_created
    ON career_autopilot_items(run_id, created_at);

INSERT INTO schema_migrations (version) VALUES ('019_career_preparation_progress')
ON CONFLICT (version) DO NOTHING;
COMMIT;
