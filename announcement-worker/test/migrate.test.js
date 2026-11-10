import assert from "node:assert/strict";
import test from "node:test";
import { createHash } from "node:crypto";
import { runAnnouncementMigrations } from "../src/migrate.js";

const databaseUrl = "postgresql://migration.invalid/db?sslmode=verify-full";
const version = "001_initial_schema";
const lockKey = "binance-cms-announcement-schema";

function createPoolHarness({ appliedRows = [], failAt = null } = {}) {
  const calls = [];
  let released = false;
  let ended = false;
  const client = {
    async query(sql, params = []) {
      calls.push({ sql, params });
      if (failAt && sql === failAt) throw new Error("database operation failed");
      if (sql.startsWith("SELECT checksum FROM binance_announcement_schema_migrations")) {
        return { rows: appliedRows, rowCount: appliedRows.length };
      }
      return { rows: [], rowCount: 0 };
    },
    release() { released = true; },
  };
  const pool = {
    async connect() { return client; },
    async end() { ended = true; },
  };
  return { poolFactory: () => pool, calls, get released() { return released; }, get ended() { return ended; } };
}

test("migration requires a dedicated migration URL before opening a pool", async () => {
  let poolFactoryCalled = false;
  await assert.rejects(runAnnouncementMigrations({
    databaseUrl: "",
    poolFactory: () => { poolFactoryCalled = true; throw new Error("pool must not be created"); },
  }), /MIGRATION_DATABASE_URL/);
  assert.equal(poolFactoryCalled, false);
});

test("first migration is locked, applied transactionally, and recorded in the ledger", async () => {
  const harness = createPoolHarness();
  await runAnnouncementMigrations({ databaseUrl, poolFactory: harness.poolFactory });

  const sql = harness.calls.map((call) => call.sql);
  assert.equal(sql[0], "BEGIN");
  assert.match(sql[1], /pg_advisory_xact_lock/);
  assert.deepEqual(harness.calls[1].params, [lockKey]);
  assert.match(sql[2], /CREATE TABLE IF NOT EXISTS binance_announcement_schema_migrations/);
  assert.match(sql[3], /SELECT checksum FROM binance_announcement_schema_migrations/);
  assert.ok(sql.some((statement) => /CREATE TABLE IF NOT EXISTS binance_announcement_events/.test(statement)));
  const record = harness.calls.find((call) => call.sql.startsWith("INSERT INTO binance_announcement_schema_migrations"));
  assert.ok(record, "applied migration is recorded");
  assert.equal(record.params[0], version);
  assert.match(record.params[1], /^[a-f0-9]{64}$/);
  assert.equal(record.params[1], createHash("sha256").update(sql.find((statement) => /CREATE TABLE IF NOT EXISTS binance_announcement_events/.test(statement))).digest("hex"));
  assert.equal(sql.at(-1), "COMMIT");
  assert.equal(harness.released, true);
  assert.equal(harness.ended, true);
});

test("an already-applied migration with the same checksum is skipped", async () => {
  const source = await import("../src/store.js");
  const checksum = createHash("sha256").update(source.SCHEMA_SQL).digest("hex");
  const same = createPoolHarness({ appliedRows: [{ checksum }] });
  await runAnnouncementMigrations({ databaseUrl, poolFactory: same.poolFactory });
  assert.equal(same.calls.some((call) => /CREATE TABLE IF NOT EXISTS binance_announcement_events/.test(call.sql)), false);
  assert.equal(same.calls.some((call) => call.sql.startsWith("INSERT INTO binance_announcement_schema_migrations")), false);
  assert.equal(same.calls.at(-1).sql, "COMMIT");
  assert.equal(same.released, true);
  assert.equal(same.ended, true);
});

test("migration checksum drift aborts and rolls back", async () => {
  const harness = createPoolHarness({ appliedRows: [{ checksum: "0".repeat(64) }] });
  await assert.rejects(
    runAnnouncementMigrations({ databaseUrl, poolFactory: harness.poolFactory }),
    /checksum mismatch/i,
  );
  assert.equal(harness.calls.at(-1).sql, "ROLLBACK");
  assert.equal(harness.released, true);
  assert.equal(harness.ended, true);
});

test("migration query failure rolls back and closes the pool", async () => {
  const harness = createPoolHarness({ failAt: "BEGIN" });
  await assert.rejects(runAnnouncementMigrations({ databaseUrl, poolFactory: harness.poolFactory }), /database operation failed/);
  assert.equal(harness.calls.at(-1).sql, "ROLLBACK");
  assert.equal(harness.released, true);
  assert.equal(harness.ended, true);
});

test("migration rejects a URL without verified TLS before creating a pool", async () => {
  let poolFactoryCalled = false;
  await assert.rejects(runAnnouncementMigrations({
    databaseUrl: "postgresql://migration.invalid/db",
    poolFactory: () => { poolFactoryCalled = true; throw new Error("pool must not be created"); },
  }), /sslmode=verify-full/);
  assert.equal(poolFactoryCalled, false);
});
