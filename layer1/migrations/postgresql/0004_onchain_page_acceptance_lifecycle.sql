CREATE TABLE layer1_onchain_ingestion_page_acceptance_lifecycle (
    page_id TEXT PRIMARY KEY
        REFERENCES layer1_onchain_ingestion_page_acceptances(page_id),
    status TEXT NOT NULL CHECK (status = 'INVALIDATED'),
    reason_code TEXT NOT NULL CHECK (reason_code = 'CANONICAL_EVIDENCE_REORGED'),
    affected_evidence_json JSONB NOT NULL
        CHECK (jsonb_typeof(affected_evidence_json) = 'array'
               AND jsonb_array_length(affected_evidence_json) > 0),
    invalidated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_onchain_page_acceptance_lifecycle_status
    ON layer1_onchain_ingestion_page_acceptance_lifecycle(status, invalidated_at, page_id);

CREATE INDEX idx_onchain_ingestion_pages_scope_identity
    ON layer1_onchain_ingestion_pages(scope_identity);
