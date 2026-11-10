# Binance CMS Announcement Worker

This is an isolated, read-only consumer of Binance's official English CMS announcement stream. It does not import the Square publisher, does not contain a Square publishing endpoint, and has no capability to create a Binance Square post.

## Runtime

- Node.js 22.12.0 or newer
- Official Binance SDK: `@binance/cms@1.0.3`
- PostgreSQL reachable through `DATABASE_URL`

## Required environment

- `BINANCE_API_KEY`: read-only Binance API key used for CMS stream authentication
- `BINANCE_API_SECRET`: matching secret used by the official SDK to sign the connection
- `DATABASE_URL`: PostgreSQL connection string for the shared announcement event store
- Optional `BINANCE_CMS_WS_URL`: defaults to the SDK's production CMS WebSocket URL

Never put credentials in source control or chat. Do not enable trading or withdrawal permissions for this key. Confirm the minimum required permission in Binance's current API-key UI/documentation before enabling the stream.

## Local verification

The test suite covers payload validation, deterministic deduplication, SQL parameterization and worker-state persistence using mocks. It does not open a live Binance connection.

```sh
npm test
```

The tests are fully mocked and do not connect to Binance, PostgreSQL, or Binance Square.

## Render Background Worker

- Root directory: `announcement-worker`
- Build command: `npm install --omit=dev`
- Start command: `npm start`
- Runtime: Node 22.12.0+
- Set the three required environment variables in Render's secret environment configuration.

The worker creates its two PostgreSQL tables idempotently at startup. The database must be durable and shared with the agent's ingestion adapter; a worker-local SQLite file or Render filesystem is not a valid substitute.

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

The worker currently runs idempotent DDL at startup, so its database role is not yet least-privilege. Before production, move schema creation into a separately credentialed migration step and grant the worker only the required event-table INSERT and worker-state SELECT/INSERT/UPDATE privileges; grant the Layer 1 importer only SELECT on the event ledger. Do not reuse a database owner credential for either runtime.
