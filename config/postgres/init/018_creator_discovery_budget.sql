BEGIN;

ALTER TABLE marketing_campaigns ADD COLUMN IF NOT EXISTS search_pages_per_query integer
    NOT NULL DEFAULT 1 CHECK (search_pages_per_query BETWEEN 1 AND 3);

CREATE TABLE IF NOT EXISTS marketing_youtube_search_requests (
    id bigserial PRIMARY KEY,
    task_id uuid REFERENCES agent_tasks(id) ON DELETE SET NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    basis varchar(30) NOT NULL DEFAULT 'request'
        CHECK (basis IN ('request', 'legacy_reservation'))
);
CREATE INDEX IF NOT EXISTS idx_marketing_search_budget_time
    ON marketing_youtube_search_requests(requested_at);
CREATE INDEX IF NOT EXISTS idx_marketing_search_budget_task
    ON marketing_youtube_search_requests(task_id);

-- Older discovery had no per-request ledger. Conservatively reserve its maximum
-- three first-page searches per attempt, once only, including delayed/queued work.
-- Retain a full day from migration because exact historical request times are unknown.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM schema_migrations
                   WHERE version = '018_creator_discovery_budget') THEN
        INSERT INTO marketing_youtube_search_requests(task_id, requested_at, basis)
        SELECT t.id, now(), 'legacy_reservation'
        FROM agent_tasks t CROSS JOIN LATERAL
            generate_series(1, LEAST(90, 3 * GREATEST(t.attempt_count, 1)))
        WHERE t.kind = 'marketing.creator_discovery'
          AND NOT (t.payload ? 'prospect_id')
          AND GREATEST(t.created_at, t.started_at, t.completed_at, t.updated_at)
              >= now() - interval '24 hours';
    END IF;
END $$;

INSERT INTO schema_migrations(version) VALUES ('018_creator_discovery_budget')
ON CONFLICT(version) DO NOTHING;
COMMIT;
