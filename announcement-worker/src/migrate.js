import pg from "pg";
import { SCHEMA_SQL } from "./store.js";

const { Pool } = pg;

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
  try {
    await pool.query(SCHEMA_SQL);
  } finally {
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
