-- Durable single-run coordination for the explicitly selected PostgreSQL runtime.
-- Existing SQLite run records remain untouched for legacy/default deployments.
CREATE TABLE IF NOT EXISTS layer1_runs (
    run_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('RUNNING','SUCCEEDED','NO_CANDIDATE_OR_BLOCKED','FAILED','INTERRUPTED')),
    config_hash TEXT NOT NULL CHECK (length(config_hash)=64),
    summary_json JSONB CHECK (summary_json IS NULL OR jsonb_typeof(summary_json)='object'),
    CHECK ((status='RUNNING' AND finished_at IS NULL) OR (status<>'RUNNING' AND finished_at IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS layer1_run_lease (
    lease_name TEXT PRIMARY KEY CHECK (lease_name='agent'),
    run_id TEXT NOT NULL UNIQUE REFERENCES layer1_runs(run_id),
    acquired_at TIMESTAMPTZ NOT NULL
);
