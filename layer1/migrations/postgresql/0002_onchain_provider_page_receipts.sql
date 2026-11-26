CREATE TABLE layer1_onchain_ingestion_pages (
    page_id TEXT PRIMARY KEY,
    cursor_key TEXT NOT NULL REFERENCES layer1_onchain_ingestion_checkpoints(cursor_key),
    scope_identity JSONB,
    page_material_json JSONB NOT NULL,
    receipt_sha256 TEXT NOT NULL CHECK (receipt_sha256 ~ '^[a-f0-9]{64}$'),
    receipts_json JSONB NOT NULL CHECK (jsonb_typeof(receipts_json) = 'array'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(btrim(cursor_key)) > 0)
);
CREATE INDEX idx_onchain_ingestion_pages_cursor
    ON layer1_onchain_ingestion_pages(cursor_key, created_at, page_id);
