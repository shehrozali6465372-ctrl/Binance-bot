import assert from "node:assert/strict";
import test from "node:test";
import { runAnnouncementMigrations } from "../src/migrate.js";

test("migration requires a dedicated migration URL and closes its pool", async () => {
  const calls = [];
  let ended = false;
  await assert.rejects(runAnnouncementMigrations({
    databaseUrl: "",
    poolFactory: () => { throw new Error("pool must not be created without migration credentials"); },
  }), /MIGRATION_DATABASE_URL/);

  await runAnnouncementMigrations({
    databaseUrl: "postgresql://migration.invalid/db?sslmode=verify-full",
    poolFactory: (options) => ({
      async query(sql) { calls.push({ options, sql }); },
      async end() { ended = true; },
    }),
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.application_name, "binance-cms-announcement-migrator");
  assert.match(calls[0].sql, /CREATE TABLE IF NOT EXISTS binance_announcement_events/);
  assert.equal(ended, true);
});

test("migration closes its pool when schema execution fails", async () => {
  let ended = false;
  await assert.rejects(runAnnouncementMigrations({
    databaseUrl: "postgresql://migration.invalid/db?sslmode=verify-full",
    poolFactory: () => ({
      async query() { throw new Error("migration failure"); },
      async end() { ended = true; },
    }),
  }), /migration failure/);
  assert.equal(ended, true);
});


test("migration rejects a URL without verified TLS before creating a pool", async () => {
  let poolFactoryCalled = false;
  await assert.rejects(runAnnouncementMigrations({
    databaseUrl: "postgresql://migration.invalid/db",
    poolFactory: () => { poolFactoryCalled = true; throw new Error("pool must not be created"); },
  }), /sslmode=verify-full/);
  assert.equal(poolFactoryCalled, false);
});
