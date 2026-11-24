import assert from "node:assert/strict";
import test from "node:test";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { MIGRATIONS, RECEIPT_MIGRATION_SQL, runAnnouncementMigrations } from "../src/migrate.js";
import { SCHEMA_SQL } from "../src/store.js";

const databaseUrl = "postgresql://migration.invalid/db?sslmode=verify-full";
const lockKey = "binance-cms-announcement-schema";
const checksum = (sql) => createHash("sha256").update(sql).digest("hex");

function createPoolHarness({ appliedRows = [], failAt = null } = {}) {
  const calls = [];
  let released = false;
  let ended = false;
  const client = {
    async query(sql, params = []) {
      calls.push({ sql, params });
      if (failAt && sql === failAt) throw new Error("database operation failed");
      if (sql.startsWith("SELECT checksum FROM binance_announcement_schema_migrations")) {
        const row = appliedRows.find((item) => item.version === params[0]);
        return { rows: row ? [{ checksum: row.checksum }] : [], rowCount: row ? 1 : 0 };
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

test("initial schema and additive receipt migration apply transactionally in order", async () => {
  const harness = createPoolHarness();
  await runAnnouncementMigrations({ databaseUrl, poolFactory: harness.poolFactory });

  const sql = harness.calls.map((call) => call.sql);
  assert.equal(sql[0], "BEGIN");
  assert.match(sql[1], /pg_advisory_xact_lock/);
  assert.deepEqual(harness.calls[1].params, [lockKey]);
  assert.match(sql[2], /CREATE TABLE IF NOT EXISTS binance_announcement_schema_migrations/);
  assert.ok(sql.includes(SCHEMA_SQL));
  assert.ok(sql.includes(RECEIPT_MIGRATION_SQL));
  assert.ok(sql.indexOf(SCHEMA_SQL) < sql.indexOf(RECEIPT_MIGRATION_SQL));
  const records = harness.calls.filter((call) => call.sql.startsWith("INSERT INTO binance_announcement_schema_migrations"));
  assert.deepEqual(records.map((record) => record.params), [
    ["001_initial_schema", checksum(SCHEMA_SQL)],
    ["002_ingestion_receipts", checksum(RECEIPT_MIGRATION_SQL)],
  ]);
  assert.equal(sql.at(-1), "COMMIT");
  assert.equal(harness.released, true);
  assert.equal(harness.ended, true);
});

test("receipt migration file exactly matches the checksum-pinned migration", async () => {
  const file = await readFile(new URL("../migrations/002_ingestion_receipts.sql", import.meta.url), "utf8");
  assert.equal(file.trim(), RECEIPT_MIGRATION_SQL.trim());
});

test("already-applied migrations with matching checksums are skipped", async () => {
  const harness = createPoolHarness({ appliedRows: MIGRATIONS.map((migration) => ({
    version: migration.version, checksum: checksum(migration.sql),
  })) });
  await runAnnouncementMigrations({ databaseUrl, poolFactory: harness.poolFactory });
  assert.equal(harness.calls.some((call) => call.sql === SCHEMA_SQL || call.sql === RECEIPT_MIGRATION_SQL), false);
  assert.equal(harness.calls.some((call) => call.sql.startsWith("INSERT INTO binance_announcement_schema_migrations")), false);
  assert.equal(harness.calls.at(-1).sql, "COMMIT");
  assert.equal(harness.released, true);
  assert.equal(harness.ended, true);
});

test("already-applied initial schema is not rewritten while new receipt migration is applied", async () => {
  const harness = createPoolHarness({ appliedRows: [{ version: "001_initial_schema", checksum: checksum(SCHEMA_SQL) }] });
  await runAnnouncementMigrations({ databaseUrl, poolFactory: harness.poolFactory });
  assert.equal(harness.calls.some((call) => call.sql === SCHEMA_SQL), false);
  assert.equal(harness.calls.some((call) => call.sql === RECEIPT_MIGRATION_SQL), true);
  const inserted = harness.calls.find((call) => call.sql.startsWith("INSERT INTO binance_announcement_schema_migrations"));
  assert.deepEqual(inserted.params, ["002_ingestion_receipts", checksum(RECEIPT_MIGRATION_SQL)]);
});

test("migration checksum drift aborts and rolls back", async () => {
  const harness = createPoolHarness({ appliedRows: [{ version: "001_initial_schema", checksum: "0".repeat(64) }] });
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
