# Binance Announcement Intelligence Pipeline

## Data path

1. The separate Binance CMS worker consumes the official CMS WebSocket and persists normalized observations in PostgreSQL (`binance_announcement_events`). This repository does not reimplement that WebSocket worker.
2. The Python agent reads the event ledger through `ANNOUNCEMENT_DATABASE_URL`, a read-only PostgreSQL role. The importer requires TLS `sslmode=verify-full` and a bounded recent lookback.
3. The importer associates only explicit parenthesized tickers with a unique CoinGecko candidate. Ambiguous or unmatched symbols are not attached to an asset.
4. `AnnouncementIntelligenceEngine` validates the official Binance HTTPS source, publisher, event taxonomy, timestamps, canonical asset IDs and content hash. Evidence and revision payloads are persisted in the Layer 1 SQLite store.
5. Module 3 independently verifies the CoinGecko asset ID against a fresh, exact Binance Spot ticker and `exchangeInfo` pair. An announcement alone never bypasses the listing/identity gate.
6. The existing publication path performs its own fresh Binance listing and identity revalidation. This module does not add or call a publication endpoint.

## Durable CMS ingestion receipt contract

The CMS worker now has a producer-side HMAC receipt path. After normalizing a message received through the authenticated official SDK stream, the worker signs a versioned canonical payload that binds the authority, schema version, topic, catalog ID, local source fingerprint, normalized content hash, catalog name, event type, title, body, disclaimer, publisher, source URL, publication timestamp and observation timestamp. The receipt is written into `binance_announcement_events.ingestion_receipt` in the same SQL INSERT as the normalized event.

- Additive worker migration: `announcement-worker/migrations/002_ingestion_receipts.sql`. Legacy rows remain NULL/unreceipted; migration 001 checksum is unchanged.
- Worker signing configuration is separate from Binance Spot: `BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON`, `BINANCE_CMS_RECEIPT_ACTIVE_KEY_ID`, `BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS`.
- Python importer verification uses `BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON` and `BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS`. It never creates CMS receipts.
- The importer reconstructs the exact receipt payload from the PostgreSQL row and verifies authority, HMAC, key ID allowlist and payload binding before writing any `AnnouncementEvidence`. Missing, malformed, tampered or untrusted receipts increment `untrusted_rows` and are not persisted as evidence.
- Missing CMS verifier configuration means zero trusted CMS evidence, not a fallback to caller-asserted provenance. Partial or inconsistent configuration fails closed.
- HMAC proves attestation by the configured worker key holder over the normalized message received through the authenticated SDK stream. It is not a Binance-origin digital signature and does not independently prove provider authorship.
- The scheduled CMS worker workflow requires signing keyring and active/trusted key configuration before starting. The Square agent workflow receives only the CMS verification keyring and trusted IDs; it does not receive the worker's active signing ID.

Receipt unit tests include a fixed Node.js-to-Python compatibility vector. PostgreSQL role integration tests verify the importer can read the receipt while the worker cannot SELECT it back. The Python test suite includes a fail-closed disposable PostgreSQL integration test for JSONB receipt round-trip, legacy NULL rejection and row-tamper rejection; it is wired into the isolated PostgreSQL CI job and runs only after the `binance_onchain_test` target guard. The worker-side PostgreSQL integration test separately checks atomic receipt persistence and role read/write boundaries. No production key has been provisioned and no live CMS/DB acceptance is claimed.

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
