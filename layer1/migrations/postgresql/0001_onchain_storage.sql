-- Module 9 PostgreSQL persistence schema, migration 0001.
CREATE TABLE layer1_onchain_asset_mappings (
    mapping_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL CHECK (length(btrim(asset_id)) > 0),
    network_id TEXT NOT NULL CHECK (length(btrim(network_id)) > 0),
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (network_id, asset_id, mapping_id)
);

CREATE TABLE layer1_onchain_observations (
    observation_id TEXT PRIMARY KEY,
    mapping_id TEXT NOT NULL REFERENCES layer1_onchain_asset_mappings(mapping_id),
    asset_id TEXT NOT NULL,
    network_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    payload_json JSONB NOT NULL,
    validation_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(btrim(provider)) > 0),
    CHECK (length(btrim(asset_id)) > 0),
    CHECK (length(btrim(network_id)) > 0)
);
CREATE INDEX idx_layer1_onchain_asset_time
    ON layer1_onchain_observations(asset_id, observed_at DESC);
CREATE INDEX idx_layer1_onchain_mapping_time
    ON layer1_onchain_observations(mapping_id, observed_at DESC);

CREATE TABLE layer1_onchain_ingestion_checkpoints (
    cursor_key TEXT PRIMARY KEY,
    network_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    scope TEXT NOT NULL,
    cursor_json JSONB,
    revision BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (network_id, provider, scope),
    CHECK (length(btrim(network_id)) > 0),
    CHECK (length(btrim(provider)) > 0),
    CHECK (length(btrim(scope)) > 0)
);

CREATE TABLE layer1_onchain_transfer_events (
    network_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    scope TEXT NOT NULL,
    event_id TEXT NOT NULL,
    transaction_hash TEXT NOT NULL,
    block_number BIGINT NOT NULL CHECK (block_number >= 0),
    block_hash TEXT NOT NULL,
    canonical_status TEXT NOT NULL CHECK (canonical_status IN ('CANONICAL', 'REORGED', 'UNVERIFIED')),
    payload_json JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (network_id, provider, scope, event_id),
    CHECK (length(btrim(network_id)) > 0),
    CHECK (length(btrim(provider)) > 0),
    CHECK (length(btrim(scope)) > 0),
    CHECK (length(btrim(event_id)) > 0)
);
CREATE INDEX idx_onchain_transfer_block
    ON layer1_onchain_transfer_events(network_id, provider, scope, block_number, block_hash);
CREATE INDEX idx_onchain_transfer_tx
    ON layer1_onchain_transfer_events(network_id, transaction_hash);
CREATE INDEX idx_onchain_transfer_canonical
    ON layer1_onchain_transfer_events(network_id, block_number)
    WHERE canonical_status = 'CANONICAL';

CREATE TABLE layer1_onchain_ingestion_blocks (
    network_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    scope TEXT NOT NULL,
    block_number BIGINT NOT NULL CHECK (block_number >= 0),
    block_hash TEXT NOT NULL,
    block_time TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (network_id, provider, scope, block_number),
    CHECK (length(btrim(network_id)) > 0),
    CHECK (length(btrim(provider)) > 0),
    CHECK (length(btrim(scope)) > 0),
    CHECK (length(btrim(block_hash)) > 0)
);

CREATE TABLE layer1_onchain_solana_slot_journal (
    network_id TEXT NOT NULL CHECK (network_id = 'solana-mainnet'),
    provider TEXT NOT NULL,
    scope TEXT NOT NULL,
    slot BIGINT NOT NULL CHECK (slot >= 0),
    produced BOOLEAN NOT NULL,
    block_hash TEXT,
    block_time TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (network_id, provider, scope, slot),
    CHECK (length(btrim(provider)) > 0),
    CHECK (length(btrim(scope)) > 0),
    CHECK (
        (produced = TRUE AND block_hash IS NOT NULL AND block_time IS NOT NULL)
        OR
        (produced = FALSE AND block_hash IS NULL AND block_time IS NULL)
    )
);
