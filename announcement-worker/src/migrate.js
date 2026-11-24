import { createHash } from "node:crypto";
import pg from "pg";
import { SCHEMA_SQL } from "./store.js";

const { Pool } = pg;
const MIGRATION_LOCK_KEY = "binance-cms-announcement-schema";
export const RECEIPT_MIGRATION_VERSION = "002_ingestion_receipts";
export const RECEIPT_MIGRATION_SQL = `
-- Additive migration: legacy rows intentionally remain NULL/unreceipted.
-- Receipt JSON is created by the trusted worker and persisted in the same INSERT
-- as its normalized event; the downstream importer must verify the HMAC.
ALTER TABLE binance_announcement_events
  ADD COLUMN IF NOT EXISTS ingestion_receipt JSONB;
`;
export const MIGRATIONS = Object.freeze([
  Object.freeze({ version: "001_initial_schema", sql: SCHEMA_SQL }),
  Object.freeze({ version: RECEIPT_MIGRATION_VERSION, sql: RECEIPT_MIGRATION_SQL }),
]);

const MIGRATION_LEDGER_SQL = `
CREATE TABLE IF NOT EXISTS binance_announcement_schema_migrations (
  version TEXT PRIMARY KEY,
  checksum CHAR(64) NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
`;

export async function runAnnouncementMigrations({
  databaseUrl = process.env.MIGRATION_DATABASE_URL,
  poolFactory = (options) => new Pool(options),
} = {}) {
  if (typeof databaseUrl !== "string" || !databaseUrl.trim()) {
    throw new Error("MIGRATION_DATABASE_URL environment variable is required");
  }
  let parsed;
  try { parsed = new URL(databaseUrl.trim()); }
  catch { throw new Error("MIGRATION_DATABASE_URL must be a valid PostgreSQL connection URL"); }
  if (!["postgres:", "postgresql:"].includes(parsed.protocol)
      || parsed.searchParams.get("sslmode") !== "verify-full") {
    throw new Error("MIGRATION_DATABASE_URL must use PostgreSQL with sslmode=verify-full");
  }

  const pool = poolFactory({
    connectionString: databaseUrl.trim(),
    max: 1,
    application_name: "binance-cms-announcement-migrator",
  });
  let client;
  try {
    client = await pool.connect();
    await client.query("BEGIN");
    await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [MIGRATION_LOCK_KEY]);
    await client.query(MIGRATION_LEDGER_SQL);

    for (const migration of MIGRATIONS) {
      const checksum = createHash("sha256").update(migration.sql).digest("hex");
      const applied = await client.query(
        "SELECT checksum FROM binance_announcement_schema_migrations WHERE version = $1",
        [migration.version],
      );
      if (applied.rowCount > 0) {
        const existingChecksum = String(applied.rows[0].checksum).trim();
        if (existingChecksum !== checksum) {
          throw new Error(`Migration checksum mismatch for ${migration.version}; refusing to continue`);
        }
        continue;
      }

      await client.query(migration.sql);
      await client.query(
        "INSERT INTO binance_announcement_schema_migrations (version, checksum) VALUES ($1, $2)",
        [migration.version, checksum],
      );
    }
    await client.query("COMMIT");
  } catch (error) {
    if (client) await client.query("ROLLBACK").catch(() => {});
    throw error;
  } finally {
    client?.release();
    await pool.end();
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  runAnnouncementMigrations().then(
    () => console.info("Binance CMS announcement schema migration completed"),
    (error) => {
      console.error("Binance CMS announcement schema migration failed", String(error?.message || error));
      process.exitCode = 1;
    },
  );
}
