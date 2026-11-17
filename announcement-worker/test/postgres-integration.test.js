import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import pg from "pg";
import { AnnouncementStore } from "../src/store.js";

const { Pool, Client } = pg;
const workerUrl = process.env.POSTGRES_WORKER_URL;
const importerUrl = process.env.POSTGRES_IMPORTER_URL;
const tlsMismatchUrl = process.env.POSTGRES_TLS_MISMATCH_URL;
const migrationUrl = process.env.POSTGRES_MIGRATION_URL;
const enabled = Boolean(workerUrl && importerUrl && tlsMismatchUrl);

function makeEvent() {
  const contentHash = createHash("sha256").update(`integration-${Date.now()}-${Math.random()}`).digest("hex");
  return {
    sourceId: createHash("sha256").update(`source-${contentHash}`).digest("hex"),
    contentHash,
    topic: "com_announcement_en",
    catalogId: "integration-test",
    catalogName: "Integration Test",
    eventType: "test",
    title: "Disposable PostgreSQL integration test",
    body: "Test-only content",
    disclaimer: "",
    publisher: "Binance",
    sourceUrl: "https://www.binance.com/en/support/announcement",
    publishedAt: new Date().toISOString(),
    observedAt: new Date().toISOString(),
    rawPayload: { test: true },
  };
}

test("PostgreSQL roles enforce runtime least privilege over verified TLS", { skip: !enabled }, async () => {
  if (migrationUrl) {
    const migrator = new Pool({ connectionString: migrationUrl, max: 1 });
    try {
      const ledger = await migrator.query(
        "SELECT version, checksum FROM binance_announcement_schema_migrations WHERE version = $1",
        ["001_initial_schema"],
      );
      assert.equal(ledger.rowCount, 1, "the applied schema migration is recorded exactly once");
      assert.match(ledger.rows[0].checksum.trim(), /^[a-f0-9]{64}$/);
    } finally {
      await migrator.end();
    }
  }

  let previousWorkerState = null;
  if (migrationUrl) {
    const migrator = new Pool({ connectionString: migrationUrl, max: 1 });
    try {
      const previous = await migrator.query(
        "SELECT worker_name, status, started_at, last_message_at, last_persisted_at, last_error, updated_at FROM binance_announcement_worker_state WHERE worker_name = $1",
        ["binance-cms-announcements"],
      );
      previousWorkerState = previous.rows[0] ?? null;
    } finally {
      await migrator.end();
    }
  }

  const worker = new Pool({ connectionString: workerUrl, max: 1 });
  const importer = new Pool({ connectionString: importerUrl, max: 1 });
  let testEvent;
  try {
    const store = new AnnouncementStore(worker);
    await store.initialize();

    const event = makeEvent();
    testEvent = event;
    assert.equal(await store.save(event), true, "worker can insert an event and RETURNING id");
    assert.equal(await store.save(event), false, "content hash uniqueness prevents duplicate persistence");
    await store.setState("LISTENING", { startedAt: new Date().toISOString() });

    const imported = await importer.query(
      "SELECT content_hash, title FROM binance_announcement_events WHERE content_hash = $1",
      [event.contentHash],
    );
    assert.equal(imported.rowCount, 1, "importer can read the event ledger");
    assert.equal(imported.rows[0].title, event.title);

    await assert.rejects(
      worker.query("SELECT title FROM binance_announcement_events LIMIT 1"),
      /permission denied/i,
      "worker cannot read event payload columns",
    );
    await assert.rejects(
      worker.query("CREATE TABLE public.worker_must_not_ddl(id integer)"),
      /permission denied/i,
      "worker cannot create schema objects",
    );
    await assert.rejects(
      importer.query("INSERT INTO binance_announcement_events (source_id, content_hash, topic, catalog_id, catalog_name, event_type, title, body, disclaimer, publisher, source_url, published_at, observed_at, raw_payload) VALUES ('x', 'y', 'com_announcement_en', 'x', 'x', 'x', 'x', '', '', 'Binance', 'https://example.com', NOW(), NOW(), '{}'::jsonb)"),
      /permission denied/i,
      "importer cannot write to the ledger",
    );
  } finally {
    await Promise.all([worker.end(), importer.end()]);
    if (migrationUrl && testEvent) {
      const cleanup = new Pool({ connectionString: migrationUrl, max: 1 });
      try {
        const deleted = await cleanup.query(
          "DELETE FROM binance_announcement_events WHERE content_hash = $1 RETURNING id",
          [testEvent.contentHash],
        );
        assert.equal(deleted.rowCount, 1, "staging integration fixture is removed");
        if (previousWorkerState) {
          await cleanup.query(
            `INSERT INTO binance_announcement_worker_state
             (worker_name, status, started_at, last_message_at, last_persisted_at, last_error, updated_at)
             VALUES ($1, $2, $3, $4, $5, $6, $7)
             ON CONFLICT (worker_name) DO UPDATE SET
               status = EXCLUDED.status,
               started_at = EXCLUDED.started_at,
               last_message_at = EXCLUDED.last_message_at,
               last_persisted_at = EXCLUDED.last_persisted_at,
               last_error = EXCLUDED.last_error,
               updated_at = EXCLUDED.updated_at`,
            [
              previousWorkerState.worker_name,
              previousWorkerState.status,
              previousWorkerState.started_at,
              previousWorkerState.last_message_at,
              previousWorkerState.last_persisted_at,
              previousWorkerState.last_error,
              previousWorkerState.updated_at,
            ],
          );
        } else {
          await cleanup.query(
            "DELETE FROM binance_announcement_worker_state WHERE worker_name = $1",
            ["binance-cms-announcements"],
          );
        }
      } finally {
        await cleanup.end();
      }
    }
  }

  const wrongHost = new Client({ connectionString: tlsMismatchUrl, connectionTimeoutMillis: 5000 });
  try {
    await assert.rejects(wrongHost.connect(), /certificate|hostname|does not match|altname/i,
      "verify-full rejects a trusted certificate issued for a different hostname");
  } finally {
    await wrongHost.end().catch(() => {});
  }
});
