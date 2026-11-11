# Binance Announcement Intelligence Pipeline

## Data path

1. The separate Binance CMS worker consumes the official CMS WebSocket and persists normalized observations in PostgreSQL (`binance_announcement_events`). This repository does not reimplement that WebSocket worker.
2. The Python agent reads the event ledger through `ANNOUNCEMENT_DATABASE_URL`, a read-only PostgreSQL role. The importer requires TLS `sslmode=verify-full` and a bounded recent lookback.
3. The importer associates only explicit parenthesized tickers with a unique CoinGecko candidate. Ambiguous or unmatched symbols are not attached to an asset.
4. `AnnouncementIntelligenceEngine` validates the official Binance HTTPS source, publisher, event taxonomy, timestamps, canonical asset IDs and content hash. Evidence and revision payloads are persisted in the Layer 1 SQLite store.
5. Module 3 independently verifies the CoinGecko asset ID against a fresh, exact Binance Spot ticker and `exchangeInfo` pair. An announcement alone never bypasses the listing/identity gate.
6. The existing publication path performs its own fresh Binance listing and identity revalidation. This module does not add or call a publication endpoint.

## Evidence identity and known source limits

The current CMS worker does **not** receive a documented stable Binance article ID or per-article permalink from the CMS payload. Its `source_id` is a deterministic local fingerprint derived from `catalogId + publishDate + title`; it is not a Binance-issued ID. Its `source_url` is the official announcements landing page, not an article permalink. The importer therefore records:

- `source_id_kind=payload_fingerprint`
- `source_url_kind=official_landing_page`
- `raw_evidence_ref=postgres:binance_announcement_events:content_hash:<sha256>`
- `revision_correlation_status=UNRESOLVED_NO_STABLE_PROVIDER_ID`

Title edits can produce a new fingerprint and cannot be confidently linked to the prior observation. They are retained as separate evidence rather than automatically merged. Same-fingerprint observations are ordered by observation time. `updated_at` and `event_at` are not fabricated when the source does not supply them.

The worker's scheduled WebSocket windows have no historical replay guarantee. A successful database read only proves that observations were stored; it does not prove complete Binance announcement-feed coverage. Runtime health therefore reports `PARTIAL_COVERAGE_NO_REPLAY`, not complete feed availability. A missed worker window may mean a missed announcement.

## Runtime configuration

- Install the optional importer driver with `pip install -r requirements-announcement-importer.txt`.
- Configure GitHub secret `ANNOUNCEMENT_DATABASE_URL` for the read-only importer role, with TLS verification (`sslmode=verify-full`). Do not use the worker or migrator role for the agent importer. The repository's existing `BINANCE_ANNOUNCEMENT_DATABASE_URL` is wired to the CMS worker's `DATABASE_URL` and is intentionally **not** reused by the importer; the separate read-only `ANNOUNCEMENT_DATABASE_URL` secret is currently absent.
- The CMS worker must be separately deployed/configured and writing to the expected PostgreSQL ledger. The agent importer does not start or dispatch the worker.
- If the secret is absent or the database is unavailable, announcement ingestion is marked unavailable/degraded; the market pipeline continues without synthetic announcement data.
- The scheduled publisher workflow remains `DRY_RUN=1` in this branch. No workflow was dispatched and no real Binance Square post was published during implementation or tests.

## Release blockers

A production announcement-feed sign-off still requires live, read-only verification against the configured worker database, confirmation that the worker is deployed and healthy, and an explicit coverage/replay strategy. The current implementation does not claim those external conditions are satisfied.
