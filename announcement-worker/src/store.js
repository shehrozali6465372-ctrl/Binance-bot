export const SCHEMA_SQL = `
CREATE TABLE IF NOT EXISTS binance_announcement_events (
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
  ON binance_announcement_events (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_binance_announcement_source_id
  ON binance_announcement_events (source_id);

CREATE TABLE IF NOT EXISTS binance_announcement_worker_state (
  worker_name TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ,
  last_message_at TIMESTAMPTZ,
  last_persisted_at TIMESTAMPTZ,
  last_error TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
`;

export class AnnouncementStore {
  constructor(pool) {
    this.pool = pool;
  }

  async initialize() {
    await this.pool.query(SCHEMA_SQL);
  }

  async save(event) {
    const result = await this.pool.query(
      `INSERT INTO binance_announcement_events
       (source_id, content_hash, topic, catalog_id, catalog_name, event_type,
        title, body, disclaimer, publisher, source_url, published_at, observed_at, raw_payload)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb)
       ON CONFLICT (content_hash) DO NOTHING
       RETURNING id`,
      [
        event.sourceId, event.contentHash, event.topic, event.catalogId,
        event.catalogName, event.eventType, event.title, event.body,
        event.disclaimer, event.publisher, event.sourceUrl, event.publishedAt,
        event.observedAt, JSON.stringify(event.rawPayload),
      ],
    );
    return result.rowCount === 1;
  }

  async setState(status, fields = {}) {
    await this.pool.query(
      `INSERT INTO binance_announcement_worker_state
       (worker_name, status, started_at, last_message_at, last_persisted_at, last_error)
       VALUES ('binance-cms-announcements', $1, $2, $3, $4, $5)
       ON CONFLICT (worker_name) DO UPDATE SET
         status = EXCLUDED.status,
         started_at = COALESCE(EXCLUDED.started_at, binance_announcement_worker_state.started_at),
         last_message_at = COALESCE(EXCLUDED.last_message_at, binance_announcement_worker_state.last_message_at),
         last_persisted_at = COALESCE(EXCLUDED.last_persisted_at, binance_announcement_worker_state.last_persisted_at),
         last_error = EXCLUDED.last_error,
         updated_at = NOW()`,
      [
        status,
        fields.startedAt ?? null,
        fields.lastMessageAt ?? null,
        fields.lastPersistedAt ?? null,
        fields.lastError ?? null,
      ],
    );
  }
}
