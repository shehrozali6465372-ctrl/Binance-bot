import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import pg from "pg";
import { AnnouncementStore } from "../src/store.js";

const { Pool, Client } = pg;
const workerUrl = process.env.POSTGRES_WORKER_URL;
const importerUrl = process.env.POSTGRES_IMPORTER_URL;
const tlsMismatchUrl = process.env.POSTGRES_TLS_MISMATCH_URL;
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
  const worker = new Pool({ connectionString: workerUrl, max: 1 });
  const importer = new Pool({ connectionString: importerUrl, max: 1 });
  try {
    const store = new AnnouncementStore(worker);
    await store.initialize();

    const event = makeEvent();
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
  }

  const wrongHost = new Client({ connectionString: tlsMismatchUrl, connectionTimeoutMillis: 5000 });
  try {
    await assert.rejects(wrongHost.connect(), /certificate|hostname|does not match|altname/i,
      "verify-full rejects a trusted certificate issued for a different hostname");
  } finally {
    await wrongHost.end().catch(() => {});
  }
});
