# Binance CMS Announcement Worker

This is an isolated, read-only consumer of Binance's official English CMS announcement stream. It does not import the Square publisher, does not contain a Square publishing endpoint, and has no capability to create a Binance Square post.

## Runtime

- Node.js 22.12.0 or newer
- Official Binance SDK: `@binance/cms@1.0.3`
- PostgreSQL reachable through `DATABASE_URL`

## Required environment

- `BINANCE_API_KEY`: read-only Binance API key used for CMS stream authentication
- `BINANCE_API_SECRET`: matching secret used by the official SDK to sign the connection
- `DATABASE_URL`: PostgreSQL connection string for the worker runtime role; it must include `sslmode=verify-full`
- Optional `BINANCE_CMS_WS_URL`: defaults to the SDK's production CMS WebSocket URL

The Layer 1 importer uses a separate `ANNOUNCEMENT_DATABASE_URL` with a read-only importer role and `sslmode=verify-full`. Schema setup uses a separate, manually supplied `MIGRATION_DATABASE_URL`; never reuse the worker or importer runtime credentials for migrations.

Never put credentials in source control or chat. Do not enable trading or withdrawal permissions for this key. Confirm the minimum required permission in Binance's current API-key UI/documentation before enabling the stream.

## Local verification

The test suite covers payload validation, deterministic deduplication, SQL parameterization and worker-state persistence using mocks. It does not open a live Binance connection.

```sh
npm test
```

The tests are fully mocked and do not connect to Binance, PostgreSQL, or Binance Square.

## Database provisioning and migration

Use a durable PostgreSQL database that is already available to the project; this repository does not provision paid infrastructure. Create the worker and importer login roles securely without embedding passwords in SQL files, then run `npm run migrate` with a dedicated `MIGRATION_DATABASE_URL` and apply `migrations/001_runtime_role_grants.sql` as the schema owner. Set `DATABASE_URL` to the worker role and `ANNOUNCEMENT_DATABASE_URL` to the importer role. Ensure runtime roles have no membership in broader privileged roles. All PostgreSQL URLs must include `sslmode=verify-full`. Do not use a worker-local SQLite file or ephemeral filesystem as a substitute for durable shared storage.

## Event identity and replay limitations

The documented CMS push payload contains catalog metadata, publish timestamp, title, body and disclaimer. It does not document a stable article ID or article permalink. Therefore:

- `source_id` and `content_hash` are deterministic fingerprints, not Binance-issued IDs.
- `source_url` is the official announcements landing page, not a fabricated article permalink.
- Exact payload duplicates are ignored by a unique content hash.
- Edited payloads are retained as distinct observations; the worker does not claim it can correlate revisions to one article.
- The documented stream has no historical replay guarantee. Reconnection can resume future events but cannot prove that events missed during an outage were recovered.

Worker state is stored in `binance_announcement_worker_state`. A `LISTENING` status proves connection initialization, not complete feed coverage. Do not mark the announcement provider fully healthy without monitoring disconnects and coverage gaps.


## PostgreSQL TLS and privileges

The Python Layer 1 importer connects with `sslmode=verify-full`, which requires a trusted certificate chain and a certificate hostname matching the database host. Do not weaken this to `require` or disable certificate verification to work around a CA/hostname error. Verify the selected provider's CA configuration in a disposable database integration test before production activation.

Schema creation is separated from runtime startup. The worker verifies required table access using zero-row SELECTs and does not execute DDL. `MIGRATION_DATABASE_URL` is used only by the explicit `npm run migrate` command. The migrator uses a transaction-scoped advisory lock and records version `001_initial_schema` plus a SHA-256 checksum in `binance_announcement_schema_migrations`; an already-applied matching version is skipped, while checksum drift aborts and rolls back. Apply `migrations/001_runtime_role_grants.sql` after securely creating the `binance_announcement_worker` and `binance_announcement_importer` login roles. The worker gets event INSERT plus SELECT(id, content_hash) and sequence USAGE, plus worker-state SELECT/INSERT/UPDATE. The narrow `content_hash` read is required by PostgreSQL for `ON CONFLICT (content_hash)` index inference; event payload columns remain unreadable to the worker. The importer gets only SELECT on the event ledger. Create both runtime roles without schema CREATE privileges; the integration test verifies they cannot create schema objects. Do not reuse a database owner or migration credential for either runtime.


### Disposable PostgreSQL security integration test

The `postgres-security-integration` CI job starts an isolated PostgreSQL 16 container with a short-lived test CA and server certificate. It creates separate migration, worker, and importer roles, runs `npm run migrate` with the migration role, applies `migrations/001_runtime_role_grants.sql` as the database owner, and verifies runtime permissions plus TLS hostname rejection. It uses disposable CI credentials and data only; it does not connect to a production database or the Binance CMS.

To run the same integration test locally, provide `POSTGRES_WORKER_URL`, `POSTGRES_IMPORTER_URL`, and `POSTGRES_TLS_MISMATCH_URL` for an isolated PostgreSQL instance configured with verified TLS, after applying the migration and role grants. Without these three variables, the integration test is skipped; the ordinary mocked test suite remains runnable offline.


## WebSocket liveness monitoring

The worker sends an SDK-level WebSocket ping every 30 seconds and expects a `pong` within 10 seconds. A missing pong marks the worker `DEGRADED`; a later pong clears only the heartbeat degradation reason. Database/message and transport degradation reasons are tracked independently, so a healthy pong cannot incorrectly clear an unrelated persistence failure. The SDK also handles connection renewal and reconnect/resubscription; transport `open` clears transport/heartbeat degradation, while a message-processing or database error remains visible until a successful event is persisted. Heartbeat timers are unreferenced and are cancelled during graceful shutdown.

The `updated_at` field in `binance_announcement_worker_state` is refreshed by heartbeat/state updates and can be used by an external monitor. Suggested alert conditions: status `DEGRADED` for more than 2 minutes; no heartbeat/state update for more than 2 minutes while the process is expected to be running; or repeated worker restarts. These thresholds are operational starting points, not Binance feed delivery SLAs. The CMS stream does not document historical replay, so a healthy ping proves transport responsiveness only—not that no announcements were missed.


## Zero-cost GitHub Actions execution (bounded stream windows)

The separate workflow `.github/workflows/binance-cms-announcement-ingestion.yml` is designed for the accepted five-minute cadence. Each scheduled invocation opens the existing official CMS WebSocket worker for at most four minutes, then sends SIGTERM so the worker drains accepted database writes and closes the stream and pool. The remaining minute is a target gap for startup/scheduling variation, not a delivery guarantee. GitHub schedule events are best-effort and may start late or be dropped under platform load.

This is **not REST polling**: Binance's documented CMS interface used here is a WebSocket push stream. Each run gets a fresh connection; the SDK reconnects within that run, but the documented stream has no historical replay guarantee. Announcements arriving during gaps or missed runs may be permanently missed. Do not claim complete feed coverage or production-grade continuous ingestion from this design.

The workflow uses a dedicated worker-role PostgreSQL URL and a read-only Binance API key. Configure these repository Actions secrets without sharing their values in chat:

- `BINANCE_API_KEY`
- `BINANCE_API_SECRET`
- `BINANCE_ANNOUNCEMENT_DATABASE_URL` (worker role only; PostgreSQL URL must use `sslmode=verify-full`)

GitHub location: repository **Settings → Secrets and variables → Actions → New repository secret**. Do not use the migrator or importer URL for the worker secret. No credentials are stored in the workflow or repository. The scheduled workflow is intentionally separate from the existing Square publishing workflow and calls only `node src/worker.js`; it cannot publish a Square post.

GitHub limitation: `schedule` events run only from the repository's default branch (`main`). This workflow is maintained on an integration branch based on `main`; the schedule becomes active only after this isolated integration is reviewed and merged into `main`. `workflow_dispatch` can be used for a controlled manual run after secrets and database schema are configured. This workflow is isolated from the existing Square publisher and cannot publish a Square post.
