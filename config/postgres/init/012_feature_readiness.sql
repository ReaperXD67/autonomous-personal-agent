-- Operator-attested local test metadata only; no logs, credentials or user content.
BEGIN;

CREATE TABLE IF NOT EXISTS feature_test_runs (
    id uuid PRIMARY KEY,
    git_commit varchar(40) NOT NULL CHECK (git_commit ~ '^[0-9a-f]{40}$'),
    working_tree_dirty boolean NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL CHECK (completed_at >= started_at),
    report jsonb NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS feature_test_runs_completed_idx
    ON feature_test_runs (completed_at DESC);

INSERT INTO schema_migrations (version) VALUES ('012_feature_readiness')
ON CONFLICT (version) DO NOTHING;

COMMIT;
