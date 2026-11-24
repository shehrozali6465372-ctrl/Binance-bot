-- Additive migration: legacy rows intentionally remain NULL/unreceipted.
-- Receipt JSON is created by the trusted worker and persisted in the same INSERT
-- as its normalized event; the downstream importer must verify the HMAC.
ALTER TABLE binance_announcement_events
  ADD COLUMN IF NOT EXISTS ingestion_receipt JSONB;
