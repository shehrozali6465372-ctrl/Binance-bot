-- Module 11 claim-verification snapshots. Keep migration 0001 immutable.
CREATE TABLE IF NOT EXISTS layer1_claim_verification_runs (
 verification_id TEXT PRIMARY KEY CHECK(length(verification_id)=64),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 claim_count INTEGER NOT NULL CHECK(claim_count >= 0),
 verified_count INTEGER NOT NULL CHECK(verified_count >= 0),
 corroborated_count INTEGER NOT NULL CHECK(corroborated_count >= 0),
 unresolved_count INTEGER NOT NULL CHECK(unresolved_count >= 0),
 payload_json JSONB NOT NULL CHECK(jsonb_typeof(payload_json)='object')
);
CREATE INDEX IF NOT EXISTS idx_layer1_claim_verification_latest
 ON layer1_claim_verification_runs(created_at DESC, verification_id DESC);
