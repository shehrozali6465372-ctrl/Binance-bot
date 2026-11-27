-- Durable Solana transactions whose finalized slot time is temporarily unknown.
-- Slot identity/hash remains canonical; events are replayed only after time is resolved.
ALTER TABLE layer1_onchain_solana_slot_journal
    DROP CONSTRAINT IF EXISTS layer1_onchain_solana_slot_journal_check2;
ALTER TABLE layer1_onchain_solana_slot_journal
    ADD CONSTRAINT solana_slot_journal_time_quarantine_check CHECK (
        (produced = TRUE AND block_hash IS NOT NULL)
        OR (produced = FALSE AND block_hash IS NULL AND block_time IS NULL)
    );

CREATE TABLE layer1_onchain_solana_quarantine (
    network_id TEXT NOT NULL CHECK (network_id = 'solana-mainnet'),
    provider TEXT NOT NULL,
    scope TEXT NOT NULL,
    signature TEXT NOT NULL,
    slot BIGINT NOT NULL CHECK (slot >= 0),
    transaction_index INTEGER NOT NULL CHECK (transaction_index >= 0),
    block_hash TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    source_page_id TEXT NOT NULL REFERENCES layer1_onchain_ingestion_pages(page_id),
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'REPLAYED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (network_id, provider, scope, signature),
    CHECK (length(btrim(provider)) > 0),
    CHECK (length(btrim(scope)) > 0),
    CHECK (length(btrim(signature)) > 0),
    CHECK (length(btrim(block_hash)) > 0)
);
CREATE INDEX idx_solana_quarantine_pending
    ON layer1_onchain_solana_quarantine(network_id, provider, scope, status, slot, signature);
