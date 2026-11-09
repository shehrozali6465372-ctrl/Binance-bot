-- Apply once with a dedicated database migration/admin role.
-- Runtime worker and importer roles must not own these objects.

CREATE TABLE IF NOT EXISTS public.binance_announcement_events (
  id BIGSERIAL PRIMARY KEY,
  source_id CHAR(64) NOT NULL,
  content_hash CHAR(64) NOT NULL UNIQUE,
  topic TEXT NOT NULL CHECK (topic = 'com_announcement_en'),
  catalog_id TEXT NOT NULL,
  catalog_name TEXT NOT NULL,
  event_type TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  disclaimer TEXT NOT NULL DEFAULT '',
  publisher TEXT NOT NULL CHECK (publisher = 'Binance'),
  source_url TEXT NOT NULL,
  published_at TIMESTAMPTZ NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  raw_payload JSONB NOT NULL,
  inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_binance_announcement_published_at
  ON public.binance_announcement_events (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_binance_announcement_source_id
  ON public.binance_announcement_events (source_id);

CREATE TABLE IF NOT EXISTS public.binance_announcement_worker_state (
  worker_name TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ,
  last_message_at TIMESTAMPTZ,
  last_persisted_at TIMESTAMPTZ,
  last_error TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
