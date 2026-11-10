export function normalizeNeonWorkerDatabaseUrl(value) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error("Database URL must be a valid PostgreSQL connection URL");
  }

  if (!["postgres:", "postgresql:"].includes(url.protocol)) {
    throw new Error("Database URL must use the PostgreSQL protocol");
  }
  if (!url.hostname.endsWith(".neon.tech")) {
    throw new Error("Database URL must point to a Neon hostname");
  }
  if (decodeURIComponent(url.username) !== "binance_announcement_worker") {
    throw new Error("Database URL must authenticate as binance_announcement_worker");
  }

  const sslmode = url.searchParams.get("sslmode");
  if (!["require", "verify-full"].includes(sslmode)) {
    throw new Error("Neon database URL must set sslmode=require or sslmode=verify-full");
  }

  url.searchParams.set("sslmode", "verify-full");
  return url.toString();
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const value = process.env.BINANCE_ANNOUNCEMENT_DATABASE_URL;
  const target = process.env.GITHUB_ENV;
  if (!value || !target) {
    throw new Error("BINANCE_ANNOUNCEMENT_DATABASE_URL and GITHUB_ENV are required");
  }
  const normalized = normalizeNeonWorkerDatabaseUrl(value);
  const { appendFileSync } = await import("node:fs");
  appendFileSync(target, `DATABASE_URL=${normalized}\n`, { mode: 0o600 });
  console.log("Neon worker database URL validated and strict TLS mode enabled.");
}
