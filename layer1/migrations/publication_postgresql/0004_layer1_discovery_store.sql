-- Additive PostgreSQL persistence for Layer1 market discovery and evidence.
-- JSONB payloads preserve the existing domain records without lossy column projection.
CREATE TABLE IF NOT EXISTS layer1_market_observations (
    observation_key TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    payload_json JSONB NOT NULL CHECK (jsonb_typeof(payload_json)='object')
);
CREATE INDEX IF NOT EXISTS idx_layer1_market_observations_history
    ON layer1_market_observations(asset_id, observed_at, provider);
CREATE TABLE IF NOT EXISTS layer1_market_analyses (
    analysis_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    currency TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ANALYZED','PARTIAL','UNAVAILABLE')),
    payload_json JSONB NOT NULL CHECK (jsonb_typeof(payload_json)='object')
);
CREATE TABLE IF NOT EXISTS layer1_identity_proofs (
    asset_id TEXT NOT NULL,
    base_asset TEXT NOT NULL,
    quote_asset TEXT NOT NULL,
    exchange_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('VERIFIED','UNVERIFIED')),
    expires_at TIMESTAMPTZ NOT NULL,
    payload_json JSONB NOT NULL CHECK (jsonb_typeof(payload_json)='object'),
    PRIMARY KEY(asset_id,base_asset,quote_asset,exchange_id)
);
CREATE TABLE IF NOT EXISTS layer1_announcement_evidence (
    source_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    publisher TEXT NOT NULL,
    event_type TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    payload_json JSONB NOT NULL CHECK (jsonb_typeof(payload_json)='object')
);
CREATE TABLE IF NOT EXISTS layer1_announcement_revisions (
    source_id TEXT NOT NULL,
    revision_key TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL,
    payload_json JSONB NOT NULL CHECK (jsonb_typeof(payload_json)='object'),
    PRIMARY KEY(source_id,revision_key)
);
CREATE INDEX IF NOT EXISTS idx_layer1_announcement_revision_order
    ON layer1_announcement_revisions(source_id,first_seen_at,revision_key);
CREATE TABLE IF NOT EXISTS layer1_trend_signals (
    signal_key TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    source TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    payload_json JSONB NOT NULL CHECK (jsonb_typeof(payload_json)='object')
);
CREATE INDEX IF NOT EXISTS idx_layer1_trend_signal_order
    ON layer1_trend_signals(observed_at,signal_key);
CREATE TABLE IF NOT EXISTS layer1_trend_clusters (
    cluster_id TEXT PRIMARY KEY,
    topic_key TEXT NOT NULL,
    asset_ids_json JSONB NOT NULL,
    source_count INTEGER NOT NULL CHECK(source_count>0),
    independent_source_count INTEGER NOT NULL CHECK(independent_source_count>0),
    signal_count INTEGER NOT NULL CHECK(signal_count>0),
    observed_at TIMESTAMPTZ NOT NULL,
    source_refs_json JSONB NOT NULL,
    confidence_limit TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS layer1_candidates (
    candidate_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    state TEXT NOT NULL,
    rejection_reasons_json JSONB NOT NULL,
    evidence_refs_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS layer1_candidate_rejections (
    rejection_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    source TEXT NOT NULL,
    source_observed_at TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL,
    details_json JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS layer1_candidate_scores (
    candidate_id TEXT NOT NULL,
    score_version TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL CHECK(score>=0 AND score<=100),
    components_json JSONB NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(candidate_id,score_version)
);
