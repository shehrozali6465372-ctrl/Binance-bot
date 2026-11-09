export const SCHEMA_CHECK_SQL = `
SELECT
  to_regclass('public.binance_announcement_events') AS events_table,
  to_regclass('public.binance_announcement_worker_state') AS state_table
`;

export class AnnouncementStore {
  constructor(pool) {
    this.pool = pool;
  }

  async initialize() {
    // Runtime credentials must not need CREATE/ALTER privileges. Apply the
    // versioned migration with a separate administrative role before startup.
    const result = await this.pool.query(SCHEMA_CHECK_SQL);
    const tables = result.rows?.[0];
    if (!tables?.events_table || !tables?.state_table) {
      throw new Error("Announcement database schema is missing; apply migrations/001_create_announcement_tables.sql");
    }
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
