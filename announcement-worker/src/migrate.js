import { createHash } from "node:crypto";
import pg from "pg";
import { SCHEMA_SQL } from "./store.js";

const { Pool } = pg;
const MIGRATION_VERSION = "001_initial_schema";
const MIGRATION_LOCK_KEY = "binance-cms-announcement-schema";
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

  const checksum = createHash("sha256").update(SCHEMA_SQL).digest("hex");
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

    const applied = await client.query(
      "SELECT checksum FROM binance_announcement_schema_migrations WHERE version = $1",
      [MIGRATION_VERSION],
    );
    if (applied.rowCount > 0) {
      const existingChecksum = String(applied.rows[0].checksum).trim();
      if (existingChecksum !== checksum) {
        throw new Error(`Migration checksum mismatch for ${MIGRATION_VERSION}; refusing to continue`);
      }
      await client.query("COMMIT");
      return;
    }

    await client.query(SCHEMA_SQL);
    await client.query(
      "INSERT INTO binance_announcement_schema_migrations (version, checksum) VALUES ($1, $2)",
      [MIGRATION_VERSION, checksum],
    );
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
