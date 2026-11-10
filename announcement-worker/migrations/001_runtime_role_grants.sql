-- Run as the database/schema owner after creating these two fresh LOGIN roles securely.
-- Do not store role passwords in this file or in source control.
REVOKE ALL PRIVILEGES ON TABLE binance_announcement_events
  FROM PUBLIC, binance_announcement_worker, binance_announcement_importer;
REVOKE ALL PRIVILEGES ON TABLE binance_announcement_worker_state
  FROM PUBLIC, binance_announcement_worker, binance_announcement_importer;
REVOKE ALL PRIVILEGES ON SEQUENCE binance_announcement_events_id_seq
  FROM PUBLIC, binance_announcement_worker, binance_announcement_importer;
REVOKE CREATE ON SCHEMA public
  FROM binance_announcement_worker, binance_announcement_importer;

GRANT USAGE ON SCHEMA public TO binance_announcement_worker;
GRANT USAGE ON SCHEMA public TO binance_announcement_importer;

-- Worker needs content_hash for ON CONFLICT index inference and id for RETURNING.
-- No event payload columns are readable by the worker.
GRANT INSERT, SELECT (id, content_hash) ON TABLE binance_announcement_events
  TO binance_announcement_worker;
GRANT USAGE ON SEQUENCE binance_announcement_events_id_seq
  TO binance_announcement_worker;

-- Worker state upsert reads existing state fields and inserts/updates one row.
GRANT SELECT, INSERT, UPDATE ON TABLE binance_announcement_worker_state
  TO binance_announcement_worker;

-- Layer 1 importer has no write privilege on the event ledger.
GRANT SELECT ON TABLE binance_announcement_events
  TO binance_announcement_importer;
