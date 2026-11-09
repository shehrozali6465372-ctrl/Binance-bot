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

The worker does not create or alter database objects at runtime. Apply the versioned SQL migration in migrations/001_create_announcement_tables.sql once using a database administrator/migration credential. Then configure DATABASE_URL with a restricted runtime role.

Minimum grants for the worker role (replace role names as appropriate):

```sql
GRANT CONNECT ON DATABASE your_database TO binance_cms_worker;
GRANT USAGE ON SCHEMA public TO binance_cms_worker;
GRANT SELECT, INSERT ON TABLE public.binance_announcement_events TO binance_cms_worker;
GRANT USAGE, SELECT ON SEQUENCE public.binance_announcement_events_id_seq TO binance_cms_worker;
GRANT SELECT, INSERT, UPDATE ON TABLE public.binance_announcement_worker_state TO binance_cms_worker;
```

Use a separate read-only role for the Python importer:

```sql
GRANT CONNECT ON DATABASE your_database TO binance_cms_importer;
GRANT USAGE ON SCHEMA public TO binance_cms_importer;
GRANT SELECT ON TABLE public.binance_announcement_events TO binance_cms_importer;
```

The worker role must not own the schema/tables and must not receive CREATE, ALTER, DROP, or role-management privileges. The importer role should have no write privileges. The database must be durable and shared with the agent's ingestion adapter; a worker-local SQLite file or Render filesystem is not a valid substitute.

## Event identity and replay limitations

The documented CMS push payload contains catalog metadata, publish timestamp, title, body and disclaimer. It does not document a stable article ID or article permalink. Therefore:

- `source_id` and `content_hash` are deterministic fingerprints, not Binance-issued IDs.
- `source_url` is the official announcements landing page, not a fabricated article permalink.
- Exact payload duplicates are ignored by a unique content hash.
- Edited payloads are retained as distinct observations; the worker does not claim it can correlate revisions to one article.
- The documented stream has no historical replay guarantee. Reconnection can resume future events but cannot prove that events missed during an outage were recovered.

Worker state is stored in `binance_announcement_worker_state`. A `LISTENING` status proves connection initialization, not complete feed coverage. Do not mark the announcement provider fully healthy without monitoring disconnects and coverage gaps.
