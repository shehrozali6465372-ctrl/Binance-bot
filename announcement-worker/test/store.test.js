import test from "node:test";
import assert from "node:assert/strict";
import { AnnouncementStore, SCHEMA_SQL } from "../src/store.js";

test("schema is idempotent and enforces exact topic and content uniqueness", () => {
  assert.match(SCHEMA_SQL, /CREATE TABLE IF NOT EXISTS binance_announcement_events/);
  assert.match(SCHEMA_SQL, /content_hash CHAR\(64\) NOT NULL UNIQUE/);
  assert.match(SCHEMA_SQL, /CHECK \(topic = 'com_announcement_en'\)/);
  assert.match(SCHEMA_SQL, /CREATE TABLE IF NOT EXISTS binance_announcement_worker_state/);
});

test("save uses parameterized SQL and reports inserted versus duplicate", async () => {
  const calls = [];
  const pool = {
    async query(sql, params) {
      calls.push({ sql, params });
      return { rowCount: calls.length === 1 ? 1 : 0 };
    },
  };
  const store = new AnnouncementStore(pool);
  const event = {
    sourceId: "a".repeat(64),
    contentHash: "b".repeat(64),
    topic: "com_announcement_en",
    catalogId: "48",
    catalogName: "Listing",
    eventType: "listing",
    title: "A listing",
    body: "body",
    disclaimer: "",
    publisher: "Binance",
    sourceUrl: "https://www.binance.com/en/support/announcement",
    publishedAt: "2026-11-09T23:00:00.000Z",
    observedAt: "2026-11-10T00:00:00.000Z",
    rawPayload: { title: "A listing" },
  };

  assert.equal(await store.save(event), true);
  assert.equal(await store.save(event), false);
  assert.match(calls[0].sql, /ON CONFLICT \(content_hash\) DO NOTHING/);
  assert.equal(calls[0].params[0], event.sourceId);
  assert.equal(calls[0].params[13], JSON.stringify(event.rawPayload));
  assert.equal(calls.length, 2);
});

test("worker state updates use a fixed worker identity and bound values", async () => {
  let captured;
  const pool = { async query(sql, params) { captured = { sql, params }; return { rowCount: 1 }; } };
  const store = new AnnouncementStore(pool);
  await store.setState("DEGRADED", { lastError: "test error" });
  assert.match(captured.sql, /'binance-cms-announcements'/);
  assert.equal(captured.params[0], "DEGRADED");
  assert.equal(captured.params[4], "test error");
});


test("runtime initialization checks required table access without executing DDL", async () => {
  const calls = [];
  const pool = { async query(sql) { calls.push(sql); return { rowCount: 0, rows: [] }; } };
  const store = new AnnouncementStore(pool);

  await store.initialize();

  assert.equal(calls.length, 2);
  assert.match(calls[0], /^SELECT id FROM binance_announcement_events LIMIT 0$/);
  assert.match(calls[1], /^SELECT worker_name FROM binance_announcement_worker_state LIMIT 0$/);
  assert.ok(calls.every((sql) => !/\b(CREATE|ALTER|DROP)\b/i.test(sql)));
});


test("runtime grants are least privilege and importer cannot mutate the event ledger", async () => {
  const fs = await import("node:fs/promises");
  const grants = await fs.readFile(new URL("../migrations/001_runtime_role_grants.sql", import.meta.url), "utf8");
  assert.match(grants, /GRANT INSERT, SELECT \(id, content_hash\).*binance_announcement_worker/s);
  assert.match(grants, /GRANT SELECT, INSERT, UPDATE ON TABLE binance_announcement_worker_state/s);
  assert.match(grants, /GRANT SELECT ON TABLE binance_announcement_events\s+TO binance_announcement_importer/);
  assert.doesNotMatch(grants, /GRANT (ALL|INSERT|UPDATE|DELETE).*binance_announcement_importer/i);
  assert.doesNotMatch(grants, /GRANT ALL/i);
});
