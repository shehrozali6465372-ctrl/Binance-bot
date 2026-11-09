import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { AnnouncementStore, SCHEMA_CHECK_SQL } from "../src/store.js";

test("runtime schema check is read-only and requires pre-applied tables", async () => {
  let captured;
  const pool = {
    async query(sql) {
      captured = sql;
      return { rows: [{ events_table: "binance_announcement_events", state_table: "binance_announcement_worker_state" }] };
    },
  };
  await new AnnouncementStore(pool).initialize();
  assert.match(captured, /to_regclass/);
  assert.doesNotMatch(captured, /CREATE|ALTER|DROP/i);
  assert.match(SCHEMA_CHECK_SQL, /^\s*SELECT/i);
});

test("runtime initialization fails clearly when migrations have not been applied", async () => {
  const pool = { async query() { return { rows: [{ events_table: null, state_table: null }] }; } };
  await assert.rejects(
    new AnnouncementStore(pool).initialize(),
    /apply migrations\/001_create_announcement_tables\.sql/,
  );
});

test("versioned migration defines constrained event and worker-state tables", async () => {
  const sql = await readFile(new URL("../migrations/001_create_announcement_tables.sql", import.meta.url), "utf8");
  assert.match(sql, /CREATE TABLE IF NOT EXISTS public\.binance_announcement_events/);
  assert.match(sql, /content_hash CHAR\(64\) NOT NULL UNIQUE/);
  assert.match(sql, /CHECK \(topic = 'com_announcement_en'\)/);
  assert.match(sql, /CREATE TABLE IF NOT EXISTS public\.binance_announcement_worker_state/);
  assert.match(sql, /idx_binance_announcement_published_at/);
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
