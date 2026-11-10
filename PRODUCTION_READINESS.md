# Production Readiness Report — Binance-bot

**Assessment date:** 2026-11-10 UTC  
**Repository:** `shehrozali6465372-ctrl/Binance-bot`  
**Branch:** `feature/binance-cms-announcement-worker`  
**Current code commit:** `8c864932f250233434d3e100b4dfd0f933eced5b`

**PR:** [#2 — Draft, open, unmerged](https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/2)

## Current verdict

**NOT PRODUCTION READY.** The isolated PostgreSQL migration, least-privilege role behavior, and TLS hostname verification now pass in CI. Production provider credentials, live CMS connectivity, deployment health, and operational recovery have not been verified.

## Verification status

| Area | Status | Evidence / limitation |
|---|---|---|
| Worker unit and lifecycle tests | PASS | GitHub Actions run `42797656785`; 38/38 tests passed in PostgreSQL integration job; offline Node job had 37 passed and 1 expected integration skip |
| WebSocket heartbeat monitoring | PASS (unit + SDK contract) | Active ping/pong, timeout degradation, recovery isolation, and shutdown cleanup tested; live Binance heartbeat not exercised |
| Worker PostgreSQL connection timeout | PASS (configuration) | `connectionTimeoutMillis: 10000` is set and regression-tested; actual blackhole/network timeout behavior not separately exercised |
| Python Layer 1 tests and compilation | PASS | GitHub Actions run `42797656785`; 65 tests passed and Python compilation passed |
| Offline worker SDK contract tests | PASS | Same run; `mocked-announcement-tests` passed |
| Disposable PostgreSQL migration | PASS | PostgreSQL 16 CI container; dedicated migration role executed schema migration and migration ledger assertion passed on run `42797656785` |
| Runtime role separation | PASS | Worker insert/RETURNING, duplicate suppression, worker-state upsert; importer read-only; unauthorized payload reads, DDL and importer writes rejected in CI and Neon staging |
| TLS chain and hostname verification | PASS | Disposable test CA trusted; wrong hostname rejected in CI; actual Neon staging endpoint also accepted `sslmode=verify-full` |
| Production database/provider TLS compatibility | NOT TESTED | CI used a generated test CA, not the selected production provider's certificate chain |
| Live Binance CMS connectivity | NOT TESTED | No live CMS credentials/socket used; heartbeat is verified only with deterministic fakes and the pinned SDK contract |
| Worker liveness state signal | PASS (implementation/tests) | `updated_at` refreshed on pong; missed pong marks `DEGRADED`; no external alert route is configured |
| Production deployment and runtime health | BLOCKED | No deployment or production environment changes authorized/performed |
| External monitoring/alert delivery, rollback and recovery under provider outage | NOT TESTED | Requires approved staging deployment and operational configuration review |
| Real Binance Square publishing | NOT TESTED / PROHIBITED IN TESTS | No real post published; publishing requires separate explicit approval |

## Corrected integration finding

The first real PostgreSQL CI run exposed a missing worker `SELECT(content_hash)` grant: PostgreSQL requires SELECT on the `ON CONFLICT (content_hash)` arbiter column. The grant was narrowed to `SELECT(id, content_hash)`; payload columns remain inaccessible to the worker. The corrected commit passed the full PostgreSQL integration job on run `42735817233`.

## Remaining blockers

1. **Production database role and migration rollout — BLOCKED.** Cause: no production database credentials or migration authorization used. Impact: production schema and role configuration remain unverified. Fix: provision separate migration, worker and importer roles through the database provider's secure secret UI; verify membership and grants; apply migration only after explicit approval. Verification: read-only diagnostics, migration ledger, role privilege tests and provider TLS handshake.
2. **Production provider TLS — NOT TESTED.** Cause: CI used a disposable CA and local hostname. Impact: actual provider CA/hostname compatibility is unknown. Fix: obtain provider's documented CA configuration and test against an isolated staging branch/database. Verification: successful `verify-full` handshake plus negative hostname-mismatch test.
3. **Live CMS read path — NOT TESTED.** Cause: no live credentials or connection used. Impact: authentication, reconnect behavior and actual feed payload compatibility are not confirmed against Binance. Fix: configure a least-privilege read-only key in the approved secret store and run a controlled read-only smoke test. No publishing action is involved.
4. **Deployment and operations — BLOCKED / NOT TESTED.** Cause: production deployment, monitoring and rollback have not been authorized or executed. Impact: runtime health and recovery cannot be certified. Fix: approve a staging deployment, add health/alerting and validate rollback before production approval.

## Safety boundaries preserved

- PR #2 remains Draft, open and unmerged.
- No production database, credentials, live CMS connection, deployment, paid infrastructure, or real Binance Square post was used.
- Existing publisher workflow and schedule were not changed as part of this database integration work.


## Isolated Neon staging verification (2026-11-10 UTC)

- **Staging database:** Neon account `Binance bot`; project `Binance-bot-staging` (`orange-glade-36037611`); PostgreSQL 16; AWS Singapore; branch `staging`; database `binance_bot_staging`.
- **Migration/TLS:** the initial schema migration was executed against the actual Neon staging endpoint using the dedicated migrator role and `sslmode=verify-full`; the provider certificate chain and hostname validated successfully. After migration-ledger hardening, the `001_initial_schema` ledger row was added through the Neon migrator connection with SHA-256 checksum `ec11200ac7003be7f289b4d9f7724b9d5230570bc050de6bf5fb9876f3cb4377`. The new transactional migration runner itself was then exercised against disposable PostgreSQL 16 in GitHub CI. Migration unit tests cover advisory locking, first application, idempotent skip, checksum drift rollback, and failure cleanup.
- **Roles:** three distinct non-superuser logins exist. The migrator owns the announcement tables and can create schema objects. Worker can INSERT events, read only `id` and `content_hash`, use the event sequence, and SELECT/INSERT/UPDATE worker state. Importer can SELECT the event ledger only. Both runtime roles lack schema CREATE; worker payload SELECT/DDL and importer INSERT were rejected in actual staging checks.
- **Staging integration:** worker insert/RETURNING, duplicate suppression, state upsert, importer read, and forbidden-operation checks passed through the Neon database connector. The disposable verification event and worker-state row were deleted. No real announcement or publishing action was generated.
- **Scope:** staging DB and roles are verified; this is not production DB certification. The CI-generated CA test remains useful for negative hostname testing. The selected provider's staging TLS path is now additionally verified.
- **Still blocked:** live Binance CMS authentication/connection and real ping/pong require a read-only Binance API key/secret; no such credential has been supplied. No Render service has been created. Render Free Web Service sleeps when idle and is unsuitable for a reliable always-on WebSocket worker; a continuously running Background Worker plan or another always-on runtime is needed. External alert delivery, rollback and outage recovery remain untested.
- **Safety:** PR #2 remains Draft/open/unmerged. Existing scheduled Square publisher workflow and schedule remain unchanged. No real Binance Square post was published.


## Verification after migration-ledger hardening (2026-11-10 UTC)

- Worker Node suite: 37 passed, 0 failed, 1 skipped locally. The skipped test is the real PostgreSQL integration test because the local runner was not supplied direct database URLs; actual Neon role behavior was separately verified through the connected Neon database tools. The GitHub PostgreSQL CI job is configured to run all tests, including the migration-ledger assertion, with the migration URL and cleanup credentials.
- Python Layer 1 suite: 65 passed, 0 failed. Python compileall passed using the isolated verification venv with Pillow installed.
- Migration runner now uses a transaction-scoped advisory lock, a version/checksum ledger, same-checksum skip, and checksum-drift rollback. Focused migration tests passed 6/6; the runner was exercised against disposable PostgreSQL 16 in GitHub CI. The Neon staging ledger row was separately verified against the current schema checksum. Workflow YAML parsing and `git diff --check` passed.
- Neon staging migration ledger currently contains one `001_initial_schema` row with the expected SHA-256 checksum. Runtime role grants and schema ownership were independently inspected on the live staging database.
- The selected Render Free plan is explicitly unsuitable for production background processing: Render says Free instances are not for production, and Free web services can spin down after 15 minutes without inbound HTTP or WebSocket messages; Render can also restart them. Official docs: https://render.com/docs/free. No Render service has been created.


## Migration-ledger release verification (2026-11-10 UTC)

- Commit 8c864932f250233434d3e100b4dfd0f933eced5b pushed to the existing feature branch. No merge or deployment performed.
- GitHub push workflow run 42797656785 and PR workflow run 42797667878 both completed SUCCESS; all three jobs passed in both runs.
- PostgreSQL security integration job: 38/38 passed, 0 failed, 0 skipped. This includes migration-ledger existence/checksum, migrator execution, worker insert/RETURNING, duplicate suppression, worker-state upsert, importer read-only enforcement, worker payload-column/DDL denial, importer write denial, and TLS hostname mismatch rejection.
- Python Layer 1 job: 65 tests passed, compilation passed. Offline Node job: 37 passed, 1 expected PostgreSQL integration skip. npm ci completed and reported 0 dependency vulnerabilities.
- PR #2 remains OPEN, Draft, unmerged, and mergeable. Existing publishing workflow/schedule untouched; no live CMS connection or real Binance Square post.


## GitHub Actions bounded ingestion design — 2026-11-10 UTC

- User accepted the five-minute cadence and selected GitHub Actions to avoid paid hosting. Added a separate feature-branch workflow at `.github/workflows/binance-cms-announcement-ingestion.yml`; the existing Square publishing workflow was not changed.
- Each run starts the existing official Binance CMS WebSocket worker for a maximum of four minutes, then sends SIGTERM for graceful write-queue drain and resource cleanup. Runs are serialized. The workflow uses `npm ci --omit=dev`, Node 22.12.0, a job timeout of eight minutes, and only the worker entry point.
- Required Actions secrets are `BINANCE_API_KEY`, `BINANCE_API_SECRET`, and `BINANCE_ANNOUNCEMENT_DATABASE_URL` (dedicated worker role, `sslmode=verify-full`). They are not yet configured or verified.
- Verification after adding the workflow: YAML parse passed; full Node suite passed 42 tests with 1 expected PostgreSQL integration skip locally; Python Layer 1 suite passed 65/65 and compileall passed; `git diff --check` passed. The actual PostgreSQL role/TLS integration remains covered by the previous successful GitHub CI run, not rerun locally in this change. New GitHub CI and an actual manual CMS run remain pending.
- **Operational limitation:** this is a bounded WebSocket push-stream window, not REST polling. A one-minute target gap remains between four-minute sessions, in addition to GitHub schedule delay/drop risk. The CMS stream has no verified historical replay guarantee, so announcements can be missed during gaps or missed runs. This is not certified continuous production ingestion.
- **Activation blocker:** repository default branch is `main`; GitHub scheduled workflows run only from the default branch. The new workflow is on the feature branch and will not schedule automatically until PR #2 is approved and merged. PR #2 remains Draft/open/unmerged. No merge, deployment, manual dispatch, secret configuration, live CMS connection, or Square post occurred.
