import test from "node:test";
import assert from "node:assert/strict";
import { normalizeNeonWorkerDatabaseUrl } from "../prepare-neon-database-url.mjs";

const base = "postgresql://binance_announcement_worker:example-password@ep-example-pooler.ap-southeast-1.aws.neon.tech/binance_bot_staging";

test("upgrades Neon sslmode=require to verify-full and preserves other query options", () => {
  const result = new URL(normalizeNeonWorkerDatabaseUrl(`${base}?sslmode=require&channel_binding=require`));
  assert.equal(result.searchParams.get("sslmode"), "verify-full");
  assert.equal(result.searchParams.get("channel_binding"), "require");
  assert.equal(result.username, "binance_announcement_worker");
});

test("preserves an already strict verify-full Neon URL", () => {
  const result = new URL(normalizeNeonWorkerDatabaseUrl(`${base}?sslmode=verify-full`));
  assert.equal(result.searchParams.get("sslmode"), "verify-full");
});

test("rejects non-Neon database hosts", () => {
  assert.throws(
    () => normalizeNeonWorkerDatabaseUrl("postgresql://binance_announcement_worker:p@example.com/db?sslmode=require"),
    /Neon hostname/,
  );
});

test("rejects an owner or other database role", () => {
  assert.throws(
    () => normalizeNeonWorkerDatabaseUrl("postgresql://binance_bot_staging_owner:p@ep-example.ap-southeast-1.aws.neon.tech/db?sslmode=require"),
    /binance_announcement_worker/,
  );
});

test("rejects URLs without an explicit TLS mode", () => {
  assert.throws(
    () => normalizeNeonWorkerDatabaseUrl(`${base}`),
    /sslmode=require or sslmode=verify-full/,
  );
});
