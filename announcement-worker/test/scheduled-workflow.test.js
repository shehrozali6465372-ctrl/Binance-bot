import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const workflow = await readFile(
  new URL("../../.github/workflows/binance-cms-announcement-ingestion.yml", import.meta.url),
  "utf8",
);

test("scheduled CMS ingestion runs on the accepted five-minute cadence", () => {
  assert.match(workflow, /cron:\s*["']\*\/5 \* \* \* \*["']/);
  assert.match(workflow, /^\s*workflow_dispatch:\s*$/m);
});

test("scheduled ingestion is serialized and cannot cancel an active run", () => {
  assert.match(workflow, /group:\s*binance-cms-announcement-ingestion/);
  assert.match(workflow, /cancel-in-progress:\s*false/);
});

test("worker receives only dedicated secrets and validates verified PostgreSQL TLS", () => {
  assert.match(workflow, /BINANCE_API_KEY:\s*\$\{\{\s*secrets\.BINANCE_API_KEY\s*\}\}/);
  assert.match(workflow, /BINANCE_API_SECRET:\s*\$\{\{\s*secrets\.BINANCE_API_SECRET\s*\}\}/);
  assert.match(workflow, /DATABASE_URL:\s*\$\{\{\s*secrets\.BINANCE_ANNOUNCEMENT_DATABASE_URL\s*\}\}/);
  assert.match(workflow, /sslmode=verify-full/);
  assert.match(workflow, /npm ci --omit=dev/);
});

test("each run uses a bounded four-minute CMS stream and graceful SIGTERM", () => {
  assert.match(workflow, /timeout --preserve-status --signal=TERM --kill-after=20s 240s node src\/worker\.js/);
  assert.match(workflow, /timeout-minutes:\s*8/);
});

test("scheduled ingestion invokes only the isolated read-only worker", () => {
  assert.match(workflow, /working-directory:\s*announcement-worker/);
  assert.doesNotMatch(workflow, /python main\.py|PostPublisher|publish\(/);
});
