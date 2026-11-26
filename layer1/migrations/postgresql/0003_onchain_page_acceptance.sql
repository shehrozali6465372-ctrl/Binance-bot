CREATE TABLE layer1_onchain_ingestion_page_acceptances (
    page_id TEXT PRIMARY KEY REFERENCES layer1_onchain_ingestion_pages(page_id),
    cursor_key TEXT NOT NULL,
    key_id TEXT NOT NULL CHECK (key_id ~ '^[A-Za-z0-9._-]{1,128}$'),
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[a-f0-9]{64}$'),
    payload_json JSONB NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    signature TEXT NOT NULL CHECK (signature ~ '^[a-f0-9]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(btrim(cursor_key)) > 0)
);
