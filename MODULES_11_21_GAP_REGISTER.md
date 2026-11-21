# LATEST AUTHORITATIVE CONTINUATION OVERRIDE — 2026-11-21 (Fail-closed Layer 1 PostgreSQL outages)

This entry records a second scheduled-runtime persistence correction. Earlier entries remain historical.

## Defect reproduced and corrected
- Repository/worktree: `shehrozali6465372-ctrl/Binance-bot`, `/tmp/binance-w2e-continuation`; local branch `work/module9-continuation-local`.
- Parent commit: `387e07053ac65b893d8af5cc5d07bb71540a0bcd`; existing PR #14 remains the only target. Do not create another PR, merge, deploy, or touch `main`.
- Audit found the Layer 1 persistence boundary in `_run_once_impl()` caught every exception, logged the failure, and returned `False`. A PostgreSQL `OperationalError` could therefore be finalized as an ordinary `NO_CANDIDATE_OR_BLOCKED` cycle rather than triggering the scheduler's supervised-stop/reconciliation policy.
- TDD RED: added `test_postgres_layer1_persistence_connection_loss_propagates_to_scheduler`; it failed because the synthetic psycopg `OperationalError` was swallowed.
- GREEN: when PostgreSQL is selected, psycopg transport/session failures (`OperationalError` / `InterfaceError`) now propagate from the Layer 1 persistence boundary. The scheduler's existing handler then stops the process for supervised restart and publication-state reconciliation. Non-connection Layer 1 failures retain the prior blocked-cycle behavior.
- Together with the preceding PostgreSQL 72-hour cooldown-history fix, the focused scheduled-persistence, end-to-end pipeline, publisher-safety and authorization suites now report **75 passed, 0 failed**.
- Full local suite after both changes, with PostgreSQL DSN/allowlist unset: **777 tests, 0 failures, 58 skipped**. The 58 are guarded PostgreSQL integration tests and are not counted as passes. The previously approved separate live disposable-Neon recovery batch remains **22 passed**; it was not repeated for these deterministic exception-propagation changes.
- `python -m compileall -q main.py layer1 tests` and `git diff --check`: PASS.

## Safety and scope
- Application change is limited to propagating PostgreSQL transport/session failures from the Layer 1 persistence catch boundary. The previous commit separately made the 72-hour cooldown-history read fail closed for PostgreSQL; SQLite best-effort behavior is unchanged.
- No production database, provider API, media upload, Binance Square publication, Pinterest Pin, scheduled workflow dispatch, merge or deployment was performed. No publisher configuration was changed.
- Disposable Neon remains suspended. No additional database-backed test was required for this isolated exception-policy regression.
- Project remains **PARTIAL — NOT PRODUCTION-READY**. Remaining release gaps include database failover/reconnect drills, full scheduled discovery-to-publication recovery acceptance, production DB architecture/cutover review, and production owner approval.

---

# LATEST AUTHORITATIVE CONTINUATION OVERRIDE — 2026-11-21 (Fail-closed PostgreSQL cooldown-history read)

This entry records a separate scheduled-runtime safety correction after the approved PostgreSQL recovery window. Earlier entries remain historical.

## Defect reproduced and corrected
- Repository/worktree: `shehrozali6465372-ctrl/Binance-bot`, `/tmp/binance-w2e-continuation`; local branch `work/module9-continuation-local`.
- Parent commit: `d39ec607aa778f4ccccf38bf39ffcecd5a909aad`; existing PR #14 is the only target. Do not create another PR, merge, deploy, or touch `main`.
- Audit found `_run_once_impl()` swallowed all exceptions from `publisher.db.get_posted_hours_dict(hours=72)`, including PostgreSQL connection/session failures, then continued with incomplete cooldown history.
- TDD RED: added `test_postgres_connection_loss_during_posted_hours_lookup_aborts_pipeline`; it failed because the synthetic psycopg `OperationalError` was swallowed and the cycle proceeded to candidate discovery.
- GREEN: PostgreSQL-selected runtime now re-raises the original history-read exception. The existing scheduler-level psycopg connection-failure handler can then stop the scheduler for supervised restart/reconciliation. Legacy SQLite retains its previous best-effort behavior.
- Focused regression: **1 passed** after the fix. Related scheduled-persistence, end-to-end pipeline, publisher-safety and authorization suites: **74 passed, 0 failed**.
- Full local suite after the code change, with PostgreSQL DSN/allowlist unset: **776 tests, 0 failures, 58 skipped**. These 58 are guarded PostgreSQL integration tests and are not counted as passes. This run does not replace the separately approved live PostgreSQL recovery acceptance of 22 passed.
- `python -m compileall -q main.py layer1 tests` and `git diff --check`: PASS.

## Safety and scope
- Runtime change is limited to propagating errors from the 72-hour history read when PostgreSQL is selected; SQLite behavior is unchanged.
- No production database, provider API, media upload, Binance Square publication, Pinterest Pin, scheduled workflow dispatch, merge or deployment was performed. No publisher configuration was changed.
- The disposable Neon endpoint remains suspended. No additional live PostgreSQL run was needed for this deterministic connection-failure regression.
- Project remains **PARTIAL — NOT PRODUCTION-READY**. Remaining release gaps include database failover/reconnect drills, full scheduled discovery-to-publication recovery acceptance, production DB architecture/cutover review, and production owner approval.

---

# LATEST AUTHORITATIVE CONTINUATION OVERRIDE — 2026-11-21 (Approved PostgreSQL recovery window)

This entry records the latest approved live disposable-PostgreSQL verification. Earlier entries remain historical.

## Exact repository and target
- Repository: `shehrozali6465372-ctrl/Binance-bot`; worktree: `/tmp/binance-w2e-continuation`; local branch: `work/module9-continuation-local`.
- HEAD before this documentation-only update: `a2338c600c06efd5520435328d163b452b6bfa96`; worktree was clean. Existing PR #14 remains OPEN / DRAFT / UNMERGED; continuation branch `layer-1/module9-onchain-continuation`, base `layer-1/module9-onchain-intelligence`. No duplicate PR, merge, deploy, or `main` changes.
- Approved disposable target only: Neon project `orange-glade-36037611`; branch `br-falling-butterfly-az03rryi` (`module9-pg-lease-fencing-disposable`); endpoint `ep-autumn-frost-azvk3fj4` (`module9-disposable-test`); database `binance_onchain_test`; role `binance_bot_staging_owner`.
- Endpoint was idle before the window, explicitly started after user approval, and explicitly suspended at the end. Final Neon API state: `idle`, suspended at `2026-11-21T15:06:52Z`. Do not resume without a separate approval.

## Live target guard and focused acceptance
- Direct endpoint hostname was matched to the exact endpoint ID and configured as the test allowlist. Neon connector initially returned its pooler host; only the exact `-pooler` hostname was replaced with the verified direct endpoint host. Database name remained `binance_onchain_test`.
- Shared preflight guard passed: dedicated database identity verified, `sslmode=require`, `channel_binding=require`, and psycopg client-side TLS `conn.pgconn.ssl_in_use=True`. Guard uses a read-only preflight connection before test migrations.
- Focused PostgreSQL recovery/atomicity batch across the seven guarded integration modules (`test_claim_registry_postgres.py`, `test_event_lifecycle_postgres.py`, `test_layer1_postgres.py`, `test_legacy_postgres.py`, `test_onchain_postgres.py`, `test_postgres_adapter_atomicity.py`, `test_publication_postgres.py`): **22 passed, 0 failed, 65 deselected**, 200.48 seconds; exit code 0.
- Selection covered fresh-process persistence/recovery, run-lease durability/fencing/crash recovery, open-transaction rollback after worker process kill, event/checkpoint atomicity, reorg rollback, adapter atomicity, and unknown publication-attempt/quota reconciliation.
- No full repository suite was rerun; the earlier full-suite result of 775 passed / 58 skipped remains a separate DSN-absent verification and is not upgraded by this focused run.

## Safety and remaining blockers
- Only the named disposable database was used. No production DB, runtime configuration, publisher, publishing gateway, scheduled earning workflow, provider API, media upload, Binance Square post, Pinterest Pin, deployment, or merge was touched.
- No application source code changed in this test window. The test run itself left the worktree clean.
- Project and Module 21 remain **PARTIAL — NOT PRODUCTION-READY**. Still outstanding: database failover/reconnect drills, full scheduled discovery-to-publication recovery acceptance, production DB architecture/cutover review, and explicit production owner approval. SQLite remains the runtime default.
- Endpoint is suspended again. Do not repeat this focused batch or wake the endpoint unless a new gap is identified and separately approved.

---

# CURRENT AUTHORITATIVE CONTINUATION OVERRIDE — 2026-11-21 (PostgreSQL adapter rollback acceptance)

This section supersedes the prior 2026-11-21 statement that the full suite and adapter rollback tests were still pending. Older entries remain historical.

## Exact repository state
- Repository: `shehrozali6465372-ctrl/Binance-bot`.
- Worktree: `/tmp/binance-w2e-continuation`; local branch: `work/module9-continuation-local`.
- Parent HEAD before this test-only addition: `1282a3f3ecf07f7c0c939ce706ef96fb26dc4e08`.
- Existing PR #14 remains OPEN / DRAFT / UNMERGED; target branch `layer-1/module9-onchain-continuation`, base `layer-1/module9-onchain-intelligence`. Do not create another PR, merge, deploy, or touch `main`.
- New local test file: `tests/test_postgres_adapter_atomicity.py`. No application runtime code changed.

## Disposable PostgreSQL adapter rollback acceptance — 2026-11-21
- User explicitly approved resuming the existing disposable Neon test endpoint for this test window.
- Target was verified before connecting: Neon project `orange-glade-36037611`, branch `br-falling-butterfly-az03rryi` (`module9-pg-lease-fencing-disposable`), endpoint `ep-autumn-frost-azvk3fj4` (`module9-disposable-test`), database `binance_onchain_test`, role `binance_bot_staging_owner`.
- Remote DB preflight passed: exact direct endpoint host allowlist, `sslmode=require`, `channel_binding=require`, database identity `binance_onchain_test`, and psycopg client-side TLS `ssl_in_use=True`. The credential file `/tmp/binance-postgres-test.env` remains mode `0600`; never display or commit its contents.
- Added four PostgreSQL failure-injection tests in `tests/test_postgres_adapter_atomicity.py`:
  1. `PostgresPublicationStore.save_claim_registry`: injected insert failure leaves no row for the exact immutable verification ID.
  2. `PostgresLayer1Store.save_announcement`: injected failure on the second evidence-table insert rolls back the preceding revision insert.
  3. `PostgresLegacyDatabase.save_post`: injected insert failure leaves no legacy post-history row.
  4. `PostgresOnChainStore.save_verified`: injected observation insert failure rolls back the earlier asset-mapping insert.
- Fifth adapter case reuses the existing `tests.test_onchain_postgres.PostgresOnChainIngestionTests.test_failure_after_event_insert_rolls_back_event_journal_and_checkpoint`: malformed canonical block timestamp fails after event insertion and verifies event, checkpoint and block journal all roll back.
- Focused five-case run: **5 passed, 0 failed**. The first attempt found a test assertion defect (it counted all historical claim snapshots rather than checking the exact verification ID); the assertion was corrected and the complete focused batch passed.
- These four new tests are PostgreSQL trigger-based transactional failure-injection/rollback tests, not four forced process-kill tests. The existing Module 21 test `test_postgres_open_transaction_is_rolled_back_after_worker_process_kill` separately provides true worker-process-kill evidence for an open transaction.
- Full repository suite with the guarded disposable PostgreSQL DSN enabled: **772 tests, 0 failures, 0 errors, 0 skipped**, 477.163 seconds. This includes all DB-gated integration tests and the new rollback tests. Exit code 0.
- `compileall` for `main.py`, `image_engine.py`, `layer1`, and `tests`: PASS. `git diff --check`: PASS.
- Neon endpoint was explicitly suspended after testing; API response state `idle`, `suspended_at=2026-11-21T09:16:16Z`. Do not resume again without a new approval.
- Safety: only the disposable `binance_onchain_test` database was used. No production DB, production credential, runtime/publisher configuration, scheduled workflow, real provider API, media upload, Binance Square post, Pinterest Pin, deployment or merge was touched.

## Updated Module 21 assessment
- Five adapter transaction rollback cases now have execution evidence (four newly added PostgreSQL failure-injection tests plus the existing on-chain ingestion rollback test).
- This does not close the separate fresh-process recovery, crash/restart, database failover/reconnect, full scheduled discovery-to-publication recovery, production DB architecture/cutover review, or operational owner-approval requirements.
- Module 21 and the overall project remain **PARTIAL — NOT PRODUCTION-READY**.

## Push verification and next action
- Commit `1447870363da66dbbd7775ccfbe4917d9a351306` (`Add PostgreSQL adapter rollback acceptance tests`) was pushed to the existing PR #14 head branch. Push exited 0; GitHub commit fetch returned the exact commit and matching test/document diff.
- The remote branch was confirmed at the new SHA after push. PR #14 remains OPEN / DRAFT / UNMERGED; no duplicate PR was created.
- GitHub workflow-runs query for this SHA returned zero PR-triggered runs. Hosted CI remains NOT VERIFIED; do not call local test success hosted CI success.
- Next: continue with the remaining Module 21 operational gaps, not duplicate the five rollback cases. Keep endpoint suspended and require separate approval for any new DB window.

---

# LATEST AUTHORITATIVE GAP REGISTER UPDATE — 2026-11-19 (Module 21 fresh-process recovery)

This update supersedes the previous Module 21 fresh-process test count and recovery coverage statement. Older entries are retained as historical checkpoints.

## New process-boundary recovery acceptance
- Worktree: `/tmp/binance-w2e-continuation`; branch `work/module9-continuation-local`; parent commit `77221377f71715f317f07f8750b2e6bf214eae42`, which matched the remote PR #14 continuation branch before these local test additions.
- `tests/test_publication_postgres.py` adds four guarded integration tests, all passing against the existing disposable `binance_onchain_test` database:
  - `test_postgres_run_lease_crash_recovery_survives_fresh_process`: a separate worker process acquires a durable lease and is force-killed (no graceful adapter close); a recovery process sees the orphaned lease, cannot overlap it, and performs only explicit operator recovery with exact run ID and termination evidence. Parent verifies `INTERRUPTED` and lease removal.
  - `test_unknown_publication_attempt_and_quota_reconcile_in_fresh_process`: persists a `PUBLICATION_UNKNOWN` attempt and linked quota reservation; a separate process verifies durable pending state and idempotent duplicate blocking, then atomically reconciles attempt/quota/audit to a synthetic confirmed remote identity. Parent reconnect verifies all final records.
  - `test_research_editorial_draft_validation_image_and_opportunity_survive_fresh_process`: verifies fresh-process retrieval of research package, editorial brief, draft, text and visual validation results, image artifact metadata and opportunity decision.
  - `test_postgres_open_transaction_is_rolled_back_after_worker_process_kill`: force-kills a worker while a transaction containing a synthetic run and lease is still open; a fresh process verifies rollback, committed control-row survival, backend disappearance and absence of orphaned leases.
- Focused process-boundary tests: **4 passed, 0 failed**. The existing mocked publisher authorization integration test was also extended to close its connection and verify authorization integrity and provenance bindings from a separate Python process; focused authorization test **1 passed**. Initial test-only fixture issues (numeric attempt ID type and image artifact metadata nesting) were corrected; no product code change was needed.
- Final full repository suite after the open-transaction crash test and subprocess-argument hardening, with `TEST_POSTGRES_DSN` and exact allowed-host/TLS guard loaded in-process: **750 tests, 0 failures, 0 errors, 0 skipped** (414.859 seconds). All PostgreSQL integration tests executed; this is not a skip-based estimate.
- `compileall -q .` and `git diff --check`: PASS.
- The only application test file changed is `tests/test_publication_postgres.py`; both canonical project context documents are updated. No production application logic, workflow, publisher configuration, credentials or schedules changed.

### Updated Module 21 assessment
- Fresh-process persistence/recovery evidence now exists for event lifecycle, run leases, unknown publication + quota reconciliation, research/editorial/draft/validation/image/opportunity records, and publication authorization.
- The open-transaction process-kill rollback requirement is now covered. Still outstanding: database failover/reconnect drills; full scheduled discovery-to-publication recovery acceptance; fresh-process recovery tests for other PostgreSQL adapters; production DB architecture/cutover review and owner approval.
- SQLite remains the runtime default. No production database was used, no real publisher was activated, no real Binance post or media upload occurred, and no production deployment/merge was performed.
- **Module 21 remains PARTIAL / NOT PRODUCTION-READY.** These tests are isolated durability evidence, not production certification.

---

# LATEST AUTHORITATIVE GAP REGISTER UPDATE — 2026-11-18 (PostgreSQL integration acceptance)

This entry supersedes earlier claims below that the isolated PostgreSQL integration tests are skipped or not yet executed. Historical counts are retained for traceability.

## PostgreSQL integration acceptance — PASS on disposable test database; production readiness still PARTIAL
- Correct code worktree: `/tmp/binance-w2e-continuation`; baseline commit `df7c4f245f1f93ff137ee0a416c10e1eb4f761b3`, exactly matching GitHub `layer-1/module9-onchain-continuation` before the current test-only fix. PR #14 remains OPEN / DRAFT / UNMERGED.
- Existing `/tmp/binance-deepseek-verify/.env` was found and read without displaying or copying secret values. It is mode `0600`, contains `TEST_POSTGRES_DSN` and `TEST_POSTGRES_ALLOWED_HOST`, and targets the dedicated `binance_onchain_test` database on the exact allowlisted host with `sslmode=require`. A read-only connection verified the database identity and client-side TLS.
- The first DB integration run exposed a test fixture defect in `tests/test_publication_postgres.py`: missing `timedelta`, `PUBLISHER_ENABLED` left false in the mocked publisher test, mock `read()` did not accept the bounded read argument, and mock share URL did not satisfy the production Binance Square URL/remote-ID contract.
- Test-only correction: imported `timedelta`; enabled the publisher only in that local test config; updated the mock response to implement `read(size)`; changed the fixture URL to `https://www.binance.com/square/post/pg-integration-post-1`; and attached `result.error` to the status assertion. The network transport remains patched and deterministic; no real Binance request/post was made.
- Focused PostgreSQL authorization test after correction: **1 passed, 0 failed**. Focused operator reconciliation regressions: **5 passed, 0 failed**.
- Added a fresh-process persistence test for Module 12/21 PostgreSQL event lifecycle: the original connection is closed, a child Python process reconnects and verifies the event plus transition history, and the parent reconnects for fixture cleanup. **1 passed**. This is process-boundary persistence evidence, not a crash-during-transaction test.
- Full repository suite with the isolated PostgreSQL DSN enabled: **746 tests, 0 failures, 0 errors, 0 skipped**. PostgreSQL-gated tests ran rather than being skipped. `compileall` and `git diff --check` passed.
- Tests are limited to the disposable `binance_onchain_test` database. Module 9 on-chain integration fixtures truncate their own test tables in this disposable database; never run these tests against production.
- No production DB was used, no production config/credentials/schedules were changed, no real provider inference or media upload was made, and no real Binance post was published.

### Remaining Module 21 acceptance
- The PostgreSQL persistence adapters and their current integration tests now have live disposable-DB execution evidence. This is not a complete production cutover or an end-to-end production recovery certification.
- Still required: complete crash/restart and operator-recovery drills across scheduled run leases, quota reservations, publication attempts, event lifecycle, research/editorial/draft/validation/image records; production DB architecture/cutover review; and explicit owner approval before any production change.
- Module 21 remains **PARTIAL / NOT PRODUCTION-READY**. The test DB must never be reused as `POSTGRES_DSN` in production.

---

# Module 11–21 Implementation Gap Register

## Cross-cutting blocker #1 — scheduled persistence and daily quota (2026-11-16)

- **Status: IMPLEMENTATION + ISOLATED POSTGRESQL ACCEPTANCE VERIFIED; LIVE OPERATIONAL CUTOVER STILL PENDING.** Existing PostgreSQL publication persistence, migrations, legacy history/analytics adapter, atomic quota reservations and PostgreSQL run leases were reused; no duplicate subsystem was introduced.
- `_get_today_post_count()` validates a non-negative integer and fails closed with a sanitized error on unavailable/malformed database results. It never resets the daily quota to zero after a database failure.
- `.github/workflows/run_bot.yml` passes repository variable `PERSISTENCE_BACKEND` (default `sqlite` while dry-run) and separate secret `POSTGRES_DSN`. Read-only `ANNOUNCEMENT_DATABASE_URL` is not used as the writable publication ledger. Live GHA publishing is rejected unless PostgreSQL is selected.
- Isolated PostgreSQL target preflight passed: `binance_onchain_test`, exact `TEST_POSTGRES_ALLOWED_HOST` match and TLS. The existing mode-0600 `/tmp/binance-deepseek-verify/.env` was parsed in-process; DSN/host values were not printed or copied.
- Acceptance: `tests.test_scheduled_persistence_safety` + `tests.test_legacy_postgres` + `tests.test_publication_postgres`: **44 passed, 0 failed, 0 skipped**. Covered concurrent daily quota reservations, durable/fenced run leases, PostgreSQL legacy post/metrics/run persistence and daily count, idempotency/reconciliation and fail-closed scheduled configuration.
- Actual runtime composition smoke: **PASS** with `PERSISTENCE_BACKEND=postgresql`, isolated test DSN and `DRY_RUN=1`; factory created the PostgreSQL store, publisher used `PostgresLegacyDatabase` on the shared connection, no SQLite fallback occurred, and daily quota count returned an integer from `binance_onchain_test`.
- GitHub Actions mocked safety CI for code head `9091e036d55085ffb6525f1405dc0e5739053883`: run `43891086561`, SUCCESS. It does not prove live provider/publishing acceptance.
- Safety: workflow `DRY_RUN: "1"` remains unchanged. No production DSN, production DB operation, secret/variable mutation, publisher activation, real Binance post, workflow dispatch, merge or deployment occurred.
- Remaining operational acceptance: owner-controlled GitHub secret `POSTGRES_DSN` must point to an authorized writable application database and repository variable `PERSISTENCE_BACKEND=postgresql` must be set before any separately approved live scheduled publishing. Do not reuse `TEST_POSTGRES_DSN` in production. Secret values are not inspectable or documented here.
## 5.11 Module 11 — Evidence Verification Engine

### Latest checkpoint — 2026-11-15 (PARTIAL; supersedes older verification counts below)

- Added generated-post claim attribution: the trusted rendered register now exposes stable claim IDs; the writer is instructed to copy claim text exactly with an inline internal reference; the deterministic gate rejects unmarked sentences, unknown/foreign/unverified claim IDs, and any sentence that differs from its referenced claim text. Internal markers are removed before persistence/publication, and only actually referenced verified IDs are bound to the draft.
- TDD regressions were observed failing before the implementation for missing attribution, rewritten text with a real claim ID, and unknown claim IDs. Latest targeted evidence-verification, content-verification and DeepSeek-generator batch: **75 passed, 0 failed**. `compileall` and `git diff --check` pass.
- Full repository suite in an isolated temporary test venv (`/tmp/binance-module11-test-venv`; Pillow installed there only): **522 tests ran: 510 passed, 0 failed, 12 skipped**. The 12 skips require `TEST_POSTGRES_DSN`. The run included DeepSeek-generator, end-to-end and publisher-safety tests. `compileall` and `git diff --check` passed. No project dependency manifest or production environment was modified.
- The deterministic conjunction splitter handles clear independent-subject clauses and explicit shared-subject predicates only when a recognized finite verb makes the next proposition clear. Coordinated object lists and ambiguous elliptical patterns are preserved instead of guessed apart; package-level tests show split factual assertions remain `UNCLASSIFIED` without matching evidence.
- Explicit sentence-to-claim attribution is fail-closed and exact-match, not semantic entailment: paraphrases and ordinary unattributed prose are rejected. Internal claim markers are removed before draft hashing/storage, and only actually referenced claim IDs are attached to the saved draft.
- Module 11 remains **PARTIAL**: full semantic fact/causal inference and all natural-language variants of ambiguous shared-subject/elliptical compound claims are not implemented. These ambiguous forms remain unresolved/fail-closed rather than being guessed. Module 11 persistence is verified against the existing append-only SQLite store; the separate Module 21 production-durability boundary is tracked under Module 21, not solved by introducing a second Module 11 database. The 12 PostgreSQL tests are unrelated configured integration skips because `TEST_POSTGRES_DSN` was not set; no test DB was provisioned.
- Existing local changes are preserved; this checkpoint is uncommitted/unpushed. No live provider call, production write, publication, merge or deployment.

Historical checkpoint details below are superseded where counts or implementation descriptions differ.

- Earlier focused verification: **47 passed, 0 failed**. Earlier full repository suite: **398 passed, 0 failed, 12 skipped**. The 12 skips required PostgreSQL because `TEST_POSTGRES_DSN` was not configured.
- Research-package claims now use deterministic atomic sentence/semicolon splitting, exact candidate `market_data_hash` linkage, exact rendered-number-to-source-value checks, currency-aware evidence matching, Binance Spot exchangeInfo evidence, announcement freshness evidence tied to title lineage, and local latest-200-publication-ledger evidence.
- DeepSeek Phase 2 now rejects numeric tokens not present in the trusted verified/corroborated claim lines. The guard ignores hashtags and is intentionally a numeric consistency check, not a semantic fact checker.
- Unknown content remains `UNCLASSIFIED` and blocks DeepSeek. Qualified analysis is kept separate from unresolved factual claims. Skills Hub metrics are excluded from LLM research packages until their source provenance is verified; their existing internal scoring path is not changed.
- Market evidence retains exact provider event timestamps. Distinct snapshots are not collapsed into a UTC-minute bucket. The registry's package view selects the latest claim per asset/mapping/key/timeframe scope while preserving historical snapshots in append-only storage.
- Module 9 freshness rules were not weakened. Only stale fixed timestamps in five Module 9 test fixtures were changed to current UTC-relative values; the affected batch passes 74/74.
- Module 11 remains **PARTIAL**: trend/on-chain evidence is adapted but not yet surfaced comprehensively in research packages; non-numeric factual claims in generated posts still lack complete semantic validation; production persistence integration remains unverified. Do not start Module 12 until those acceptance gaps are resolved.

Earlier checkpoint details below are historical and are superseded where counts or implementation descriptions differ.

**Purpose:** Validate every material factual claim against attributable evidence.

**Claim states:** `VERIFIED`, `CORROBORATED`, `UNVERIFIED`, `CONTRADICTED`, `STALE`.

**Required logic:**
1. Split research/content into atomic factual claims.
2. Link every material claim to one or more evidence IDs.
3. Prefer primary sources; independently corroborate material claims where reasonably available.
4. Verify exact subject, asset identity, number, unit, timeframe, date and status.
5. Determine whether sources are independent or syndicated copies.
6. Compare source publication/update time to observation time and event time.
7. Detect contradictions and preserve both sides; do not pick the more convenient one.
8. Distinguish confirmed fact, source assertion, estimate, analyst interpretation and hypothesis.
9. Require stronger evidence for high-impact/security/legal/listing claims.
10. Do not use LLM confidence as evidence.

**Outputs:** Claim registry, evidence links, verification state and unresolved issue list.

**Acceptance:** Unsupported claim cannot pass; number/date/entity mismatch caught; contradictions remain visible; stale claims fail; source lineage is retained.

### Implementation checkpoint — 2026-11-14 (PARTIAL; NOT COMPLETE)

- Added `layer1/evidence_verification.py` with typed `EvidenceRecord`, `Claim`, `ClaimVerificationResult` and `ClaimRegistry` models, stable SHA-256 IDs, deterministic verification, source adapters and an append-only `ClaimRegistryStore`.
- The engine supports the five required states: `VERIFIED`, `CORROBORATED`, `UNVERIFIED`, `CONTRADICTED`, and `STALE`.
- Evidence adapters reuse persisted announcement revisions, market observations and trend signals, plus matching Module 9 accepted observations / threshold-qualified aggregation summaries. Mapping IDs and original source lineage are retained.
- Exact subject, asset/mapping identity, value, unit, timeframe, event time and status are compared. Publication, update and observation timestamps are retained separately; future/stale evidence does not pass.
- Independent-source grouping unions shared source-family, content-hash and lineage identifiers, so syndicated copies do not count as independent. Contradictory accepted evidence is retained on both sides.
- High-impact claims require an explicit freshness policy, a primary source and at least two independent source groups. Estimates, interpretations, hypotheses and unclassified drafts cannot be verified as facts.
- `_persist_layer1_market_intelligence()` now rebuilds and persists source-record claim assertions. Package assembly creates unclassified sentence drafts, persists the package registry and appends a bounded verification register.
- DeepSeek Phase 1 and Phase 2 now fail closed unless the final trusted register reports at least one verified/corroborated claim and zero unresolved claims. A marker-spoofing test ensures earlier untrusted text cannot override the appended register. Unsupported smart-money/trending/Alpha heuristic instructions and fabricated trade-level requirements were removed from the writing prompt.
- Market snapshots retain exact provider event timestamps; publication/update/observation timestamps are not truncated for comparison or freshness checks.

**Focused verification:** 30 tests passed, 0 failed (21 evidence-verification tests, 8 DeepSeek-generator tests and 1 Layer 1 runtime persistence integration test). Python compile check and `git diff --check` passed.

The package-facing register selects the latest claim per asset/mapping/key/timeframe scope so historical stale market snapshots do not block current research. Announcement and individual on-chain transaction claims retain event-specific scope; the latest stale observation remains unresolved and blocks generation. Historical records remain in the append-only registry.

**Full repository verification:** 381 tests ran: 320 passed, 48 errored, 1 failed, 12 skipped. All 49 non-passing tests are in existing Module 9 on-chain test files: 48 fixtures fail with `ONCHAIN_OBSERVATION_STALE`; one expects `ACCEPTED` but receives `UNAVAILABLE`. The 12 PostgreSQL integration tests were skipped because `TEST_POSTGRES_DSN` is not configured. No Module 11 test failed. The Module 9 failures were not changed or bypassed.

**Remaining gaps — Module 11 is not complete:**
- `split_atomic_claims()` currently segments sentences/semicolon clauses; it does not semantically split compound sentences or classify each factual statement.
- Research-package sentence drafts are deliberately `UNCLASSIFIED`, carry no evidence IDs, and therefore keep the DeepSeek gate blocked. Structured mapping of every material sentence to evidence IDs and an explicit claim type is still required before the gate can be relaxed.
- Current persistence uses the existing Layer 1 SQLite store. Integration with the final Module 21 / production persistence boundary has not been validated.
- No live DeepSeek request, live RPC, production database write, publisher activation, Binance Square post, workflow change, merge or deployment was performed.

## 5.12 Module 12 — Event Lifecycle Intelligence

**Purpose:** Maintain the state and history of each canonical event and detect materially new information.

**Lifecycle states:** `DISCOVERED → UNDER_VERIFICATION → CONFIRMED → DEVELOPING → RESOLVED`; `STALE`/`WITHDRAWN` are possible terminal/side states as defined by event type.

**Required logic:**
1. Assign stable event identity and canonical source/evidence references.
2. Store first publication, first observation, last update and effective event time separately.
3. Transition states only under explicit rules and evidence.
4. Distinguish a correction/update to an event from a new event.
5. Reopen/reclassify only when meaningful new evidence arrives.
6. Expire/mark stale when source/event freshness policy requires it.
7. Use event lifecycle to prevent repeat posts without material development.

**Outputs:** Event current state plus append-only transition history.

**Acceptance:** Legal transitions enforced; duplicate source update does not create new event; materially new evidence is captured; restart preserves state; stale event cannot masquerade as breaking news.

## 5.13 Module 13 — Deep Research Engine

**Purpose:** Build an evidence-backed research package for an eligible candidate/event.

**Inputs:** Candidate, market analysis, on-chain observations where available, event graph/lifecycle, evidence registry and source constraints.

**Required logic:**
1. Define the research question from the event, not from a generic coin template.
2. Gather primary and corroborating evidence within a bounded request/time budget.
3. Compare claims and timelines across sources.
4. Include market and on-chain context only when available and identity-verified.
5. Separate what happened, what is known, what is inferred, what is disputed and what remains unknown.
6. Identify reader value, key risks and alternative explanations.
7. Record source coverage gaps and research cutoff time.
8. Build a reproducible research package whose claims reference evidence IDs.

**Outputs:** Versioned research package and explicit completeness status.

**Failure rules:** Insufficient or contradictory evidence leads to `RESEARCH_MORE`, `DEFER` or `REJECT`; do not fill gaps with model imagination.

**Acceptance:** Every material factual sentence has evidence link; data cutoff is explicit; missing source class is visible; package reproducible from stored inputs.

## 5.14 Module 14 — Opportunity Evaluation Engine

**Purpose:** Make the pre-editorial decision on whether the verified research is useful and timely enough to draft.

**Decision states:** `PROCEED`, `RESEARCH_MORE`, `DEFER`, `REJECT`.

**Required logic:**
1. Verify Binance eligibility snapshot and freshness.
2. Verify event and research state.
3. Evaluate evidence strength, timeliness, materiality, audience usefulness, novelty and risk.
4. Evaluate whether the event has already been covered and whether any new development is material.
5. Check for contradictions, unsupported causal framing and incomplete critical fields.
6. Explain each decision with rule/score/reason IDs.
7. `PROCEED` authorizes editorial drafting only, not publication.

**Acceptance:** A high score cannot pass contradicted/unlisted/stale hard gate; same research inputs yield same deterministic gate decision for the same policy version; defer/reject reasons are traceable.

---

## 5.15 Module 15 — AI Decision Engine (Direct DeepSeek API)

**Selected provider constraint:** Connect directly to the official DeepSeek API. No OpenRouter, Together, third-party aggregator, proxy, or external LLM gateway. The exact currently supported Flash model identifier, endpoint semantics, limits and structured-output features must be verified from current official DeepSeek documentation/official model response before implementation; do not hardcode an unverified model ID from this document.

**Purpose:** Use an LLM to synthesize verified research and support editorial decisions, not to act as the system of record or safety authority.

**Inputs:** Versioned research package, evidence IDs/claim states, editorial policy, structured output schema and model configuration.

**Required logic:**
1. Call DeepSeek directly using securely configured credentials and documented official API interface.
2. Send only necessary information; redact secrets and unrelated sensitive data.
3. Prompt with explicit fact/interpretation/unknown separation and prohibition on inventing data.
4. Require structured output where supported; validate response against a strict schema regardless.
5. Retain model ID, request version, response ID/metadata, token usage and latency where available—never secret values.
6. Validate referenced evidence IDs against actual package IDs.
7. Reject malformed, truncated, unsupported or contradictory output.
8. Retry only transient errors with bounded backoff; do not retry invalid content indefinitely.
9. Treat model output as untrusted input and pass it through deterministic checks.

**Failure rules:** API unavailable, model ID unsupported, schema invalid or response not grounded means AI capability unavailable; no cached/fabricated answer presented as current.

**Acceptance:** Actual direct API read/generation test using safe non-publishing request; exact model confirmed; malformed response rejection; timeout/rate limit handled; credentials never logged; third-party route absent.

## 5.16 Module 16 — Editorial Strategy Engine

**Purpose:** Select a reader-focused article angle and format based on evidence and the research question.

**Formats may include:** Event update, market movement explanation, project development analysis, educational explainer, risk/context analysis, or substantive follow-up.

**Required logic:**
1. Identify the central reader question and why the information matters now.
2. Select a format that matches the evidence; do not force breaking-news style for routine market noise.
3. Select an angle not already used for the same event unless materially updated.
4. Build an outline that preserves evidence hierarchy and uncertainty.
5. Define exactly what must not be claimed.
6. Set editorial constraints: audience, length, tone, content format and risk language.

**Outputs:** Versioned editorial brief with structure and prohibited/uncertain claims.

**Acceptance:** Angle is traceable to evidence; duplicate angle detected; no unsupported certainty or direct trade instruction in brief.

## 5.17 Module 17 — Content Generation Engine

**Purpose:** Produce original, useful Binance Square text from an approved editorial brief using direct DeepSeek.

**Required logic:**
1. Generate from the research package and editorial brief only.
2. Preserve verified figures, dates, units, names and source meaning.
3. Clearly word uncertainty and alternative explanations.
4. Structure content around event/evidence/reason/implications/risks rather than generic price commentary.
5. Avoid buy/sell/entry/exit commands, personalized financial advice, guarantees and fabricated targets.
6. Check length, formatting, repeated phrases/angles and source attribution conventions.
7. Save draft and exact source/version references before validation.
8. Revisions must retain provenance and version history.

**Outputs:** Unpublished draft with a claim-to-evidence reference map.

**Failure rules:** Draft without research references, materially altered figures, or unsupported claims is not eligible for validation/publishing.

**Acceptance:** Draft facts match research; no fabricated values; no prohibited trade instructions; repeated-content cases flagged; draft version stored before later processing.

## 5.18 Module 18 — Content Verification & Safety Engine

**Purpose:** Independently validate text before media creation/publishing package assembly.

**Required checks:**
- Asset/ticker identity matches canonical Binance asset.
- Every material factual claim is supported by allowed claim states.
- Values, units, dates, percentages, timeframes and event status match evidence.
- Causal language does not exceed evidence.
- Contradictions and uncertainty are represented accurately.
- No fabricated catalyst, citation, source or quote.
- No direct personalized financial advice, guaranteed result or manipulative claim.
- Originality/repetition policy passes.
- Platform formatting/content constraints are met using current documented rules.

**Decision states:** `PASS`, `NEEDS_REVISION`, `REJECT`.

**Required logic:** deterministic checks first; LLM-assisted semantic review may supplement but cannot override failed deterministic rules. A revision creates a new version and must be rechecked in full.

**Acceptance:** Wrong ticker/date/number fails; unknown source fails; repeated revision cannot inherit old PASS; only current draft hash with PASS can proceed.

## 5.19 Module 19 — Image Generation Engine (Cloudflare Workers AI)

**Selected provider constraint:** Use Cloudflare Workers AI directly for actual image-generation inference. Do not route through a third-party image-generation aggregator. The exact model must be selected only after verifying current official Cloudflare model catalog, image-generation/editing support, account access, limits, pricing, output format, quality and latency. No model ID is locked by this document.

**Keep separate:** image generation inference, Python/Pillow composition, image validation, media storage, and Binance media upload are distinct operations.

**Required logic:**
1. Receive the approved editorial brief, exact canonical asset identity and visual requirements.
2. Build a prompt from validated facts only; avoid generating unverified logo, ticker, chart data, price or dates.
3. Call the official Workers AI inference interface directly.
4. Validate that actual image bytes were returned and decode successfully; an HTTP 200 without valid image bytes is not success.
5. Record exact model, generation parameters, request ID, time, bytes, dimensions and content hash where available.
6. Use existing Pillow composition where it is suitable; verify installed libraries before adding replacements.
7. Separate generated illustrative background from factual text/labels/charts. Prefer deterministic rendering for exact labels and numbers rather than asking a generative model to spell critical figures.
8. No chart unless genuine data series, units, timestamps and provenance are present.
9. A non-data illustration must not be presented as a photograph or verified event evidence.
10. Store final artifact locally/in approved storage according to existing workflow; do not add Cloudflare Images or another host by default.
11. Pass the final asset to Module 20; do not upload/publish directly.

**Failure rules:** Model unavailable, content rejected, empty/invalid bytes, decode failure, missing required image or incorrect format means generation failure. No blank/stock/mock image and no fake success. A safe skip/reject policy applies if image is required.

**Acceptance:** Real Workers AI inference; exact model verified; actual decodable image; correct hash/metadata; prompt facts traceable; image generation distinct from Binance upload; no unapproved image-hosting dependency.

## 5.20 Module 20 — Visual Quality & Consistency Engine

**Purpose:** Validate that the visual is usable, truthful, and consistent with the exact approved text/asset.

**Required logic:**
1. Validate image file type, dimensions, size, decodeability and visual boundaries.
2. Match exact asset/ticker/project identity against the approved draft.
3. Compare all rendered numbers, dates, percentages and chart labels with evidence. Use deterministic rendering/known text layer metadata where possible; OCR/vision can flag issues but is not sole proof for exact figures.
4. Ensure any chart points to real data IDs and time range; synthetic or missing points reject the chart.
5. Validate text visibility, contrast, clipping, overlap, readability and platform aspect-ratio requirements based on current documented constraints.
6. Detect obvious duplicate asset/hash and mismatched subject.
7. Record each check and validation version.
8. Bind the exact validated image hash to the exact validated text draft hash.
9. Revalidate if either asset changes.
10. Media upload is not part of this validation pass; upload state is tracked separately in Module 21.

**Outputs:** `PASS`, `NEEDS_REVISION`, `REJECT`, with visual/draft hash association.

**Acceptance:** Wrong ticker/figure mismatch fails; chart without source data fails; corrupt image fails; changed text/image invalidates prior approval; correct draft-image pair remains traceable.

---

## 5.21 Module 21 — Publishing, Persistence & Autonomous Operations Engine

**Purpose:** Provide the single controlled boundary between approved content and live Binance Square publication, while preserving durable state, safe recovery, and operational observability.

### 21A. Publication authorization

Before authorization, verify all mandatory predicates:

1. Canonical asset still `ELIGIBLE` for Binance Spot and verification is within configured freshness window.
2. Event/candidate remains current and not materially superseded/stale.
3. Current text draft hash has Module 18 `PASS`.
4. Current image hash paired with that draft has Module 20 `PASS`.
5. All required sources/evidence are present and no blocking contradiction exists.
6. Daily quota reservation is available and concurrency-safe.
7. Duplicate/repetition policy passes.
8. Credentials/configuration and provider capability are available.
9. Content/media satisfy documented Binance Square publishing API requirements.
10. Publication intent/idempotency key is unique and durably recorded before external side effect.

No LLM or scheduler can create its own authorization. Authorization is deterministic and records each pass/fail reason.

### 21B. Single controlled publishing gateway

- One internal API/function boundary is the only code allowed to call the real Binance Square publish endpoint.
- Search every direct publish call during audit; remove/route bypasses only through approved scoped changes.
- The gateway accepts an already-authorized immutable package, not an arbitrary AI-generated body.
- It validates intent ID, payload hash, idempotency key, authorization expiry, quota reservation and current status.
- It records submission state before sending the request.
- It records provider response and external post ID/URL only when supported by actual response evidence.
- It never assumes success from a local function return or HTTP status without validating response schema and external ID.
- It cannot be called by unit tests in a way that reaches production; tests must use a non-publishing seam or safe test facility.

### 21C. Idempotency and uncertain-outcome reconciliation

**Critical scenario:** Binance may accept a post while the network response is lost. A timeout is not proof of failure.

States include at minimum:
`CREATED → AUTHORIZED → SUBMITTING → CONFIRMED`
with alternative terminal/recovery states `REJECTED`, `FAILED_CONFIRMED`, and `UNKNOWN_NEEDS_RECONCILIATION`.

Required logic:
1. Persist publication intent and unique idempotency identity before the network call.
2. On a definitive provider rejection, record failure and reason.
3. On confirmed success with valid external content ID, record `CONFIRMED` and immutable linkage.
4. On timeout, connection reset, malformed/ambiguous response or process crash after submission, set `UNKNOWN_NEEDS_RECONCILIATION`.
5. Do not blindly retry an unknown publication.
6. Reconcile only through an authorized, documented read capability or reliable response/ledger evidence. Do not invent private endpoints or use browser automation.
7. If no supported way exists to prove outcome, remain safely unknown and require policy-controlled/manual resolution; never claim no post exists.
8. A repeat submission is allowed only when non-publication is proven or provider documentation guarantees idempotent request behavior with the same key.

### 21D. Persistent records, quotas and data integrity

- Use the existing persistence/database after audit; do not introduce a second database for the same state.
- Make state changes transactional where supported; define uniqueness constraints for run, candidate/event, intent and confirmed external post identifiers.
- Persist daily quota reservation/consumption with timezone, date boundary, concurrency and crash recovery semantics.
- Uncertain submissions must conservatively consume or reserve quota until resolved so retries cannot exceed policy.
- Append state transition history; do not overwrite evidence of prior transitions.
- Store exact Binance content/post ID and URL when returned; never update metrics by symbol alone.
- Separate per-post analytics from account-period analytics; keep performance-learning loop frozen until authorized official data access exists.
- Keep rewards, tips, views, likes, click-rate, reading-time and other measurements separate by scope/source/time.

### 21E. Monitoring, recovery and evaluation

Monitor real signals:
- run starts/completions;
- provider availability, errors, latency and rate limits;
- data freshness and schema failure;
- Binance listing gate outcomes;
- evidence coverage/contradictions;
- event/candidate duplicate and rejection reasons;
- image generation/validation/upload stages separately;
- publication intent state, unknown outcomes and reconciliation;
- quota and database integrity;
- exception rates and recovery result.

Recovery rules:
1. Retry only idempotent/read operations or provider operations whose semantics are documented.
2. Use bounded retries, backoff/jitter and circuit-breaking/disablement where repeated errors would cause harm.
3. Never retry a non-idempotent publication on an unknown result.
4. Resume from durable state; do not rerun already-completed side effects.
5. Alert/report unresolved unknowns and blocking service failures.
6. Do not treat internal telemetry as audience engagement or W2E performance metrics.

**Acceptance:** One gateway only; concurrency-safe quota; duplicate publication regression blocked; timeout-after-accept scenario remains unknown until reconciled; restart recovery does not repeat side effects; publication ID is linked to exact intent; database failure blocks unsafe publishing; no real post emitted by tests.

---

# 6. Global decision gates and state flow

The major pipeline is:

`Run Context → Real Source Acquisition → Binance Spot Eligibility → Candidate Discovery → Relevance Ranking → Market/On-chain Analysis → Event/Evidence Graph → Deep Research → Opportunity Evaluation → DeepSeek Editorial Decision → Editorial Brief → Draft → Text Validation → Cloudflare Image Generation → Visual Validation → Publication Authorization → Single Gateway → Reconciliation → Persistent Record → Monitoring/Evaluation`.

The flow is not a rigid requirement that every data source must be available for every asset. It is a set of gates. A missing optional on-chain provider may be reported as unavailable while market-only research continues if the editorial rule allows it; a missing mandatory asset-identity or core evidence check must block the candidate.

## 6.1 Mandatory hard gates

1. Binance Spot listing/asset identity verified.
2. Data freshness and source provenance acceptable for the particular claim.
3. No unresolved critical contradiction.
4. Research package complete enough for the selected content claims.
5. Text passes current claim/safety validation.
6. Image is present if required and passes visual consistency.
7. Publication authorization and quota reservation succeed.
8. Unique durable intent exists.

No soft score can override a failed hard gate.

## 6.2 No-publish outcomes

The system must be able to make and record a valid `NO_PUBLISH` decision when:
- no eligible Binance Spot asset/catalyst exists;
- data is stale or insufficient;
- source is unverifiable or materially contradictory;
- an event is duplicate or has no material update;
- research/editorial value is weak;
- text/image validation fails;
- quota is exhausted;
- publishing state is uncertain;
- critical provider/database/safety control is unavailable.

Not publishing is a successful safe decision, not an execution failure.

---

# 7. Technology decisions and selection gates

This section records approved direction only. A technology is not production-approved until current official documentation, compatibility, licensing, actual access, behavior and cost are verified.

| Area | Direction | Status / constraint |
|---|---|---|
| Core language | Preserve existing Python codebase | Existing stack observed previously; verify exact runtime/dependencies during audit |
| Architecture style | Modular monolith first | Locked preference; no microservices merely for component count |
| LLM | Direct official DeepSeek API | User-confirmed; no third-party LLM aggregator/proxy; exact current Flash model ID and API features must be verified |
| Image-generation inference | Cloudflare Workers AI direct | User-confirmed; exact image model/capabilities/account access/pricing must be verified |
| Image composition | Existing Python/Pillow capability where fit | Audit and reuse before replacing/adding library |
| Market data | Existing Binance official endpoints + CoinGecko integration | Audit endpoint support, limits, terms, correctness and actual usage |
| Binance listing eligibility | Official Spot exchange metadata | Mandatory authoritative gate; verify schema/semantics from current official docs |
| On-chain provider | Not selected | Evaluate verified direct RPC/open-source/indexed providers; do not add until need and asset mappings proven |
| Database | Preserve existing database | Inspect schema/transactions/migrations; no replacement chosen without evidence |
| Cache/queue | No new product selected | Reuse existing cache/state first; add Redis/queue only if measured need proves it |
| Scheduling | Existing GitHub Actions initially | Inspect quotas and run behavior; no workflow change without approval |
| Monitoring | Structured logs and existing CI/runtime diagnostics first | Add hosted monitoring only for demonstrated gap and cost case |
| Testing | Existing test suite plus appropriate static/unit/integration/failure tests | Verify tools and reuse current project conventions; production integration uses real documented interfaces |
| Open-source dependencies | Reuse only after verification | License, maintenance, vulnerabilities, docs, compatibility and logical tests required |
| Analytics read source | None approved | Performance learning frozen until official authorized machine-readable source verified |

## 7.1 DeepSeek requirements

- Direct HTTPS connection to official DeepSeek API only.
- Credentials stored outside source code in approved secrets/config.
- Exact model identifier verified from official documentation/API before use.
- Explicit timeout, bounded retry, rate-limit handling and usage/cost recording where available.
- Response schema validation and prompt/version tracking.
- No fallback to a different LLM provider without explicit approval.

## 7.2 Cloudflare Workers AI requirements

- Direct official Workers AI inference; no third-party generation proxy.
- Select model after real account-access and output test.
- Verify that selected model truly supports required image generation/editing operation.
- Track inference separately from Pillow composition and Binance media upload.
- Cloudflare Images is a separate storage/delivery product and is **not selected by default**.

## 7.3 Open-source adoption decision protocol

For every required capability:
1. Search existing repository/dependencies first.
2. Search suitable maintained open-source implementations.
3. Review license, security, support and docs.
4. Validate fit with a real isolated run.
5. Run logical tests against the project's edge cases.
6. Record adopt/reject decision and reason.
7. Integrate behind one owned interface.
8. Implement only residual logic not provided by the verified tool.

This avoids unnecessary code and duplicate libraries. If no suitable tool exists, implement the smallest clear module and cover it with tests.

---

# 8. Persistence and state-machine invariants

Exact table names/schema are decided after database audit; the semantic guarantees below are mandatory.

- Stable internal IDs for run, asset, evidence, event, candidate, draft, visual asset and publication intent.
- Unique constraints/indexes where they protect idempotency and identity.
- Explicit state transitions with prior/current state, actor/module, timestamp and reason.
- Atomic update for state + quota reservation where the database supports transactions.
- No side effect may be repeated merely because the process restarted.
- Store immutable content/image hashes so a validation approval applies only to the exact validated artifact.
- Do not use coin symbol as a unique key for post records or analytics.
- Account-period and post-level metrics are different scopes and cannot be mixed.
- Unknown publication outcome is a first-class persistent state.
- Timezones and daily quota boundaries must be explicit and tested.
- Retention and personal-data minimization must be defined for any wallet/source data.

---

# 9. Security, reliability and operational rules

1. Least-privilege API credentials; no secrets in repository, prompt, output, image metadata or logs.
2. Validate all provider responses as untrusted input.
3. Pin/lock dependencies appropriately and scan advisories before production release.
4. Protect against overlapping scheduled runs and race conditions.
5. Bound timeouts, request sizes, pagination, retries and token/image payload sizes.
6. Treat provider content and model output as data, never as executable instructions.
7. Keep external calls observable without leaking credentials.
8. Use explicit circuit-breaker/degraded state only where it prevents repeated unsafe attempts; do not silently substitute fake data.
9. Fail closed for identity, listing, evidence, quota, authorization and publication ambiguity.
10. Fail visibly and safely for optional intelligence providers; do not invent missing optional signals.
11. Maintain rollback path and migration reversibility where feasible.
12. Preserve current operational behavior until a tested migration is approved.

---

# 10. Verification strategy and acceptance standard

A feature may be labelled `COMPLETE` only when the following relevant evidence exists:

## 10.1 Static/source verification

- Code path exists and is reachable from orchestration.
- No duplicate or bypass implementation exists.
- Inputs/outputs and state effects match the contract.
- Error paths and security boundaries are inspected.
- Dependencies and licenses are verified.

## 10.2 Deterministic logic tests

- Input validation and boundary conditions.
- Same input/version yields deterministic rules-based result.
- State transition legality.
- Identity collisions, duplicates, stale data and missing evidence.
- Quota/concurrency and idempotency invariants.

Test fixtures may validate pure deterministic logic but are not real-provider evidence.

## 10.3 Real provider integration tests

- Use actual documented official APIs with read-only/safe operations or provider-supported test facilities.
- Record timestamp, endpoint/model, response schema, relevant status and redacted evidence.
- Never use unapproved private endpoints.
- Never generate fake provider success.
- Do not publish a real Binance Square post.

## 10.4 Database and recovery tests

- Actual schema/migration applied in isolated test database/environment.
- Unique constraints and transactions tested.
- Crash/restart recovery tested.
- Unknown publication state is not blindly retried.
- State and quota consistency tested under concurrency.

## 10.5 End-to-end safe test

Run a full pipeline in a non-publishing mode where all actual read providers and real AI/image generation can be exercised, but the final gateway is guarded so no production publication request can be made. The test must prove every stage's actual output and status. A dry run that substitutes fake market/provider/model outputs does not count as end-to-end evidence.

## 10.6 Production verification

- Read-only health/diagnostic verification after approved deployment.
- Confirm expected version/commit.
- Confirm provider access and database integrity safely.
- No real post is used as a test unless the user explicitly changes that constraint and separately approves it; current rule is no real post testing.
## 10.7 Completion report format

For every module report:
- Status: `EXISTS_AND_VERIFIED | EXISTS_BUT_DEFECTIVE | PARTIAL | MISSING | NOT_VERIFIABLE`.
- Code locations and current commit SHA.
- What was reused from open source/existing code.
- What minimal gap was implemented (if authorized).
- Tests run and actual result identifiers.
- Real provider evidence and timestamp where applicable.
- Known limitations and unresolved risks.
- Whether deployment is required and whether separately approved.

Never report an unrun test as passed or a source inspection as runtime verification.

---

# 11. Required architecture-to-code audit before implementation

The first execution phase is read-only. It must inspect, at minimum:

- `main.py` and all imported/local modules.
- `image_engine.py` generation, composition, asset persistence and upload paths.
- `.github/workflows/run_bot.yml` and all workflow triggers/permissions/secrets references.
- All dependency files, lock files and package versions.
- Database schema, migrations, persistence methods and publication history formats.
- Every market/news/trending/announcement provider endpoint and its official support status.
- All Binance listing filters and every direct publish call path.
- Daily quota, cooldown, duplicate/repetition logic and concurrency behavior.
- Tests, fixtures, test commands, CI results and coverage gaps.
- Runtime/deployment configuration and actual non-secret provider/service usage evidence.
- Current Git commit, uncommitted state where accessible, and rollback baseline.

For each of the 21 modules, create a mapping:
`architecture requirement → existing code location → evidence → status → exact gap → reuse candidate → minimal proposed fix → acceptance test`.

No implementation begins merely because a module is listed in this architecture. First prove what already works and what is missing.

---

# 12. Explicit unresolved decisions (must not be guessed)

The following remain open until verified:

1. Exact current DeepSeek Flash model ID, API capabilities, limits and price.
2. Exact Cloudflare Workers AI image model, image-generation/editing capabilities, account availability, limits and price.
3. Suitable on-chain provider/network coverage and exact listed-asset mapping process.
4. Current database schema's ability to support the required state/ledger contracts without migration.
5. Exact provider-specific freshness thresholds based on endpoint semantics and observed update cadence.
6. Exact event/claim scoring weights and thresholds, to be calibrated using traceable evidence—not guessed constants.
7. Exact image dimensions/format limits from current Binance Square publishing documentation.
8. Official analytics read/export capability; until then performance learning remains frozen.
9. Whether any existing open-source library fully covers a proposed function; this requires repository/dependency and upstream verification.

No exact cost estimate should be presented until actual usage, quotas, model pricing and deployment plans are verified.

---

# 13. Out-of-scope and prohibitions

- Trading/exchange order execution.
- Unlisted-asset discovery or publication candidacy.
- Personalized buy/sell/entry/exit advice.
- Engagement manipulation or reward gaming.
- Unofficial/private Binance endpoints in production without explicit authorization and support review.
- Personal browser automation.
- Real Binance Square post as a test.
- Arbitrary microservices, graph databases, Redis, vector databases or agent frameworks without measured need.
- Duplicate implementation of an existing suitable open-source capability.
- New paid subscription/provider without a cost-benefit decision and user approval.
- Performance-learning changes based on inferred/guessed/scraped unsupported metrics.

---

# 14. Frozen architecture approval checklist

This specification is the frozen target baseline. Before implementation, the audit must establish evidence for each item:

- [ ] All 21 logical modules mapped to existing code.
- [ ] Existing open-source capabilities inventoried, license-reviewed and logically tested.
- [ ] Duplicate capabilities and direct publisher bypasses identified.
- [ ] All actual provider endpoints classified as official/documented, third-party, unofficial, or unknown.
- [ ] Binance Spot eligibility proven as an unbypassable hard gate.
- [ ] Exact asset and on-chain identity mapping designed without ticker-only inference.
- [ ] DeepSeek direct API/model verified.
- [ ] Cloudflare Workers AI image model verified.
- [ ] Existing image engine/media upload behavior mapped.
- [ ] Persistence and publication ledger gaps measured.
- [ ] Timeout/uncertain publication reconciliation behavior tested safely.
- [ ] Daily quota/concurrency semantics verified.
- [ ] Cost/access inventory supported by actual usage evidence.
- [ ] Regression and safe end-to-end test plan prepared.
- [ ] Implementation scope, rollback and acceptance criteria approved.

This checklist does not authorize the work to be marked done merely by checking boxes in the document. Each check requires attached evidence in the Master Context/audit record.

---

# 15. Change history

| Version | Date | Change | Status |
|---|---|---|---|
| 1.0 | 2026-11-09 | Initial locked 21-module architecture; recorded permanent open-source reuse, no-duplicate/no-useless-logic, no-fake production, Binance Spot-only eligibility, listed-asset-only on-chain analysis, direct DeepSeek API, Cloudflare Workers AI image generation, single publishing gateway and safe verification requirements. | 🔒 Locked baseline |

**No repository code, runtime configuration, credentials, workflow, deployment, paid plan, or Binance Square publication was changed while authoring this architecture document.**


## Latest continuation checkpoint — 2026-11-14 (supersedes previous test counts)

### Module 11 incremental work
- Added `EvidenceVerificationEngine.append_asset_evidence_context()` and wired it into `main._attach_claim_register()`. It surfaces accepted trend topics and threshold-qualified Module 9 summary IDs only for the exact canonical subject/asset. No cross-asset evidence is attached.
- `claims_from_research_package()` now recognizes exact `Trend topic:` and `On-chain transfer summary ID:` lines. Trend claims link only matching topic-digest/subject/asset SOCIAL evidence. On-chain claims link only exact summary ID + subject/asset + accepted THRESHOLD_MET evidence, retaining mapping/network/event scope. Unknown trend topics remain unverified.
- Added regression tests for exact linkage, unknown trend topic blocking and cross-asset isolation.
- Evidence-verification focused tests: **36 passed**.
- Cross-layer focused batch (evidence, event graph, DeepSeek client, on-chain aggregation/providers/workers/normalizers): **245 passed, 0 failed, 12 skipped**.
- Full repository suite, after installing Pillow 13.0.0 into temporary `/tmp/binance-test-deps` only: **402 passed, 0 failed, 12 skipped**. The 12 skips are PostgreSQL integration tests without `TEST_POSTGRES_DSN`. The first run without Pillow had five import errors because the repository workflow installs Pillow but the remote test environment did not. No repository dependency or workflow file was changed to hide this.
- `python -m compileall -q layer1 main.py image_engine.py tests` and `git diff --check` passed.

### Module 15 direct DeepSeek update
- Official current API documentation lists `deepseek-flash` and `deepseek-v4-pro`; the legacy `deepseek-chat` / `deepseek-reasoner` aliases were scheduled for discontinuation on 2026-07-24. The project default is now `deepseek-flash`, with explicit `DEEPSEEK_MODEL` override retained.
- Requests explicitly set `thinking: {type: disabled}` for the current deterministic text-generation path and bounded token use.
- Mocked direct API and configuration tests pass. No real API call was made; the runtime secret/workflow mismatch remains unchanged.

### Remaining status — do not overstate completion
- Module 11 remains **PARTIAL** because non-numeric semantic hallucination detection and the final production persistence boundary are not fully proven. The numeric guard is not a semantic fact checker.
- Modules 12–21 remain unaudited/not verified against all acceptance criteria. In particular, Module 12 has an event graph but no demonstrated durable event lifecycle state machine; Module 14 currently defers scoring when its five required inputs are absent; Modules 19–20 do not yet have proven Cloudflare image inference plus final image/draft consistency validation; Module 21 requires deeper authorization, quota, idempotency, reconciliation and recovery audit.
- Current workflow remains unchanged and still supplies Gemini variable names while runtime expects DeepSeek variables. No secret or workflow changes without explicit approval.
- Cloudflare current model candidate: `@cf/black-forest-labs/flux-2-klein-4b`. Official docs list 10,000 free Neurons/day for Workers AI overall; free-plan model access and actual inference must be confirmed in the user's account before activation. No inference was run.
- No commit, push, merge, deployment, real post, live RPC, production DB write, publisher activation or paid infrastructure provisioning occurred.


## Module 12 implementation checkpoint — 2026-11-14

### Implemented
- Added `layer1/event_lifecycle.py` backed by the existing `Layer1Store` SQLite connection; no new database/service.
- Stable event identity uses canonical asset + event type + stable provider source ID. Fingerprint-only CMS IDs are intentionally not merged across revisions because title edits cannot be reliably correlated.
- Separate first-published, first-observed, last-source-update and effective-event timestamps.
- Explicit legal transition map and append-only transition history, with source revision history and transactional current-state updates.
- First observation enters `DISCOVERED → UNDER_VERIFICATION`; only Module 11 VERIFIED/CORROBORATED source claim evidence can confirm.
- Stale source evidence transitions to `STALE`; duplicate old source observations cannot reopen it. Reopening stale/resolved state requires a new revision explicitly marked materially new and verified.
- Resolution/withdrawal requires explicit verified resolution evidence; withdrawal is terminal.
- Multi-asset announcements split into one event per canonical asset.
- Wired announcement lifecycle synchronization into `_persist_layer1_market_intelligence` after the Module 11 claim registry is rebuilt.
- Regression coverage includes legal transitions, exact verified source linkage, stale and unknown handling, multi-asset splitting, duplicate updates, fingerprint non-correlation, append-only history and restart recovery.
- Module 12 focused tests: **12 passed**; event graph + lifecycle tests: **22 passed**.

### Explicit remaining limitation
- Runtime currently passes `materially_new=False` because the imported announcement evidence contains title/hash/timestamps but not enough normalized change semantics to prove materiality. The lifecycle API supports an explicit material-new flag, but automated classification of material changes is not yet proven. Module 12 is therefore **PARTIAL**, not complete.
- Per-event-type stale TTL configuration and operator/reconciliation policy remain to be wired; do not apply a guessed global TTL.

## 2026-11-14 — Modules 12–21 continuation status (local implementation; acceptance incomplete)

### Implemented code and current status
| Module | Current status | Evidence / code | Remaining acceptance gap |
|---|---|---|---|
| 11 Evidence verification | PARTIAL | layer1/evidence_verification.py; source adapters, exact trend/on-chain links, registry and numeric gate | Complete semantic sentence-to-evidence validation; semantic hallucination/causal coverage; production persistence boundary |
| 12 Event lifecycle | PARTIAL | layer1/event_lifecycle.py; explicit state machine, disputed state, append-only transitions, multi-asset/restart tests, normalized title/event-type/effective-time/full-body material-change detection | Semantic materiality classification, stable provider revision IDs where unavailable, and source-specific freshness policy |
| 13 Deep research | PARTIAL | layer1/research_package.py; versioned package, cutoff, evidence/source coverage, facts/inferences/disputed/unknown, idempotent persistence | Full bounded source acquisition/corroboration and complete sentence-level claim mapping |
| 14 Opportunity evaluation | PARTIAL / FAIL-CLOSED | layer1/opportunity.py; hard gates, deterministic optional weighted scoring, persisted decisions | Approved weights and evidence-derived factor providers absent; runtime currently supplies no policy/factors and correctly returns DEFER |
| 15 AI decision / DeepSeek | PARTIAL | layer1/deepseek_client.py; direct API client; official deepseek-flash model contract verified; mocked client tests | No authenticated live API test; GitHub Actions still maps Gemini secrets while runtime reads DeepSeek variables |
| 16 Editorial strategy | PARTIAL | layer1/editorial_strategy.py; event/on-chain/market angle, prohibited claims, uncertainty and duplicate angle versioning | No live AI/editorial quality evaluation; no complete semantic duplicate-angle detection |
| 17 Content generation | PARTIAL | layer1/content_generation.py; append-only draft versions, research/brief/claim provenance and validation ledgers | No live DeepSeek generation; exact generated content still needs stronger semantic verification |
| 18 Content verification | PARTIAL | layer1/content_verification.py; canonical asset/ticker, claim states, numeric guard, prohibited trade/guarantee phrases | No full semantic factual/causal/repetition validator; numeric allowlist is not semantic proof |
| 19 Image generation | PARTIAL | image_engine.py; direct Cloudflare FLUX.2 Klein 4B client, multipart and image-byte checks, deterministic composition and provenance sidecar | No real authenticated Workers AI inference, account access/cost validation or provider output evidence |
| 20 Visual quality | PARTIAL | layer1/visual_quality.py; exact draft/image hash pair, PNG/dimensions/size/identity/metadata, deterministic overlay geometry, clipping/bounds, font-size, non-overlap and conservative WCAG contrast checks | No independent OCR/vision audit of AI background semantic mismatch or arbitrary generated text |
| 21 Publishing/persistence | PARTIAL | layer1/publication_authorization.py, main.py, scripts/reconcile_publications.py, layer1/publication_postgres.py and layer1/migrations/publication_postgresql/; immutable auth, exact event binding, daily quota, attempt binding, visual-validation-version gate, persisted validation, manual unknown-outcome reconciliation, explicit opt-in PostgreSQL adapter and 29 mocked-transport integration tests on disposable Neon | SQLite remains default; no production cutover, isolated PostgreSQL recovery/concurrency drill, live Binance provider verification or real post (never performed) |

### Verification (latest available — 2026-11-15)
- Full local repository suite: **585 tests ran, 0 failed, 27 skipped** with `TEST_POSTGRES_DSN` and `TEST_POSTGRES_ALLOWED_HOST` unset. The skips are environment-guarded integration tests; this run did not connect to PostgreSQL.
- Module 13 research-package focused suite: **13 passed, 0 failed**, including a TDD regression for retaining cutoff-eligible contradictory evidence IDs.
- Module 12 announcement-importer/event-lifecycle/event-graph focused suite from the immediately preceding checkpoint: **39 passed, 0 failed**.
- `python -m compileall -q layer1 tests main.py image_engine.py` and `git diff --check` passed after the latest code and documentation edits.
- The separate Module 21 disposable-Neon integration run remains **29/29 passed** from its own earlier checkpoint; it is not included in the 585-test local count.
- No live DeepSeek API, Cloudflare inference, RPC, production DB write, Binance media upload or real Binance Square publication.

### Official provider contract checks
- DeepSeek official API docs: deepseek-flash and deepseek-v4-pro are listed model IDs; use current API contract, not retired aliases. https://api-docs.deepseek.com/api/create-chat-completion/ and https://api-docs.deepseek.com/api/list-models/.
- Cloudflare official model page lists @cf/black-forest-labs/flux-2-klein-4b; model requires multipart form data and supports prompt, width and height. https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/.
- Official documentation verification is not the same as authenticated account entitlement or a real inference test.

### Explicit release blockers
- Do not mark Modules 11–21 complete: each has a documented remaining acceptance gap above.
- Module 14 is deliberately fail-closed until the owner approves/calibrates a scoring policy and source-backed factor values; no fabricated weights.
- Do not activate live publishing until the media-upload/authorization ordering, PostgreSQL persistence, workflow DeepSeek-secret mapping, and provider-safe recovery have been separately resolved and approved.
- Do not commit, push, merge, deploy, change workflow/secrets/schedule, activate publisher or publish a real post without explicit approval.
- Preserve current branch/worktree and continue the module-by-module audit; no duplicate implementations.

## Final verification supersession — 2026-11-14 22:22 UTC
- Final full suite: **478 passed, 0 failed, 12 skipped**. Skips are PostgreSQL integration tests without TEST_POSTGRES_DSN.
- compileall and git diff --check passed; final log /tmp/full-suite-2026-11-14-final-final.log.
- Cloudflare FLUX.2 Klein 4B request bounds now enforce the official 256–1920 width/height range; the upper-bound regression is included.
- This is test evidence only; Modules 11–21 remain PARTIAL for the explicit acceptance gaps in the table above. No live provider inference or publishing was performed.

## Latest Module 19–21 hardening — 2026-11-14
- Module 19 image provenance is now persisted in image_generation_artifacts, including prompt hash, inference parameters, provider/model/request ID, timestamps, source and final image hashes, draft hash and canonical asset. Immutable exact-pair replay is idempotent; conflicting metadata for an existing pair is rejected.
- Module 20 validates prompt hash and the official Cloudflare FLUX.2 Klein 4B generation bounds (256–1920) in addition to final image/draft hashes, format, dimensions and allowed overlays.
- Module 21 authorization rejects noncanonical asset IDs, invalid ticker strings, duplicate image hashes and non-hex image digests.
- Added IMAGE_REQUIRED (default true). Generation/visual QA failure, required media-upload failure or image-pipeline exception blocks publication. Text-only operation requires explicit IMAGE_REQUIRED=false; dry-run does not call Binance media upload.
- Repository search confirms one live publisher.publish() call site in main.py. ImageUploader's media endpoints are separate and are not a second publication gateway.
- Focused regression batch: 28 passed, 0 failed. Latest full suite: **483 passed, 0 failed, 12 skipped**; skips require TEST_POSTGRES_DSN. compileall and git diff --check passed.
- This is deterministic test evidence, not proof of real Cloudflare inference, Binance media upload, PostgreSQL persistence or live publication. Modules 11–21 remain PARTIAL as listed above.

## Module 19–20 provenance persistence update — 2026-11-14
- Added durable local SQLite image-generation artifact records to DraftStore with canonical artifact ID, exact hashes, provider/model/request metadata, prompt hash, generation parameters, asset identity and image path. The pipeline writes this before visual validation.
- Visual QA enforces prompt provenance and official Cloudflare model request bounds (256–1920), plus supported output format. Added regression coverage.
- Verification: full suite **483 passed, 0 failed, 12 skipped**; compileall and git diff --check passed. PostgreSQL tests remain skipped; no real provider call/upload/publication occurred.
- Module 19/20 remain PARTIAL: persistence is currently SQLite-only, no authenticated Cloudflare inference, and no independent OCR/visual semantic QA.

## Module 21 safety refinement — 2026-11-14
- Fixed a real dry-run side-effect gap: generated images were being uploaded to Binance media endpoint even with DRY_RUN=1. Upload now requires explicit non-dry-run and an existing image path; regression test covers dry-run/no-image/live-eligible predicate.
- Verification: full suite **484 passed, 0 failed, 12 skipped**; compileall and git diff --check passed.
- Live-mode media upload still precedes final publication authorization; this is not considered resolved and remains a production release blocker.

## Module 21 publication-order fix — 2026-11-14
- **Resolved:** media upload previously happened before final publication authorization. Pipeline now persists exact image artifact, passes visual QA, revalidates Spot, reserves quota and persists immutable authorization before media upload. The upload helper verifies authorization integrity and exact draft/image binding before invoking the external upload callback. Upload failure releases reservation and aborts; dry-run never uploads.
- Regression tests cover missing/tampered authorization and exact image/draft hash binding. Static call order: authorize → upload_authorized_image → publisher.publish.
- Verification: **486 passed, 0 failed, 12 skipped**; compileall and git diff --check passed. No real media upload or post performed.
- Remaining Module 21 gaps: PostgreSQL integration suite unavailable without TEST_POSTGRES_DSN; no production DB/recovery drill; no live API side-effect test. Treat this particular ordering defect as fixed, not all of Module 21.

## Module 15 strict response and bounded retry update — 2026-11-14
- Direct client now rejects any response that is not the expected chat.completion object, exact configured model, non-empty response ID, finish_reason=stop, non-empty text and text-only (no refusal/tool_calls). In particular, length/content_filter/aborted/tool_calls/unknown finish reasons fail closed because official DeepSeek docs state length may be truncated.
- Added bounded exponential retry for transient HTTP 408/429/500/502/503/504 and transport failures only; auth errors do not retry. Response ID, model, token counts and measured latency are retained/logged safely.
- Official contract: https://api-docs.deepseek.com/api/create-chat-completion/.
- Focused DeepSeek tests: 27 passed, 0 failed; full-suite verification pending. No authenticated live API request.

## Module 19/21 media transport security update — 2026-11-14
- Presigned upload URL allowlist and HTTPS/port/userinfo/query/fragment checks are enforced before PUT and again inside the low-level upload method. Final processed media URL must be the Binance CDN host bin.bnbstatic.com or subdomain.
- Sensitive presigned URLs, file tickets and response bodies were removed from logs.
- Regression tests cover SSRF-style destinations and invalid final media hosts. Focused batch: 32 passed, 0 failed; static checks passed.
- Still requires a safe authenticated provider validation to confirm the current real storage/CDN hostnames; no external upload performed.

## Final current verification — 2026-11-14 22:58 UTC
- Latest full suite after all changes in this checkpoint: **495 passed, 0 failed, 12 skipped**. 12 skipped require TEST_POSTGRES_DSN.
- compileall and git diff --check passed. Log: /tmp/full-suite-2026-11-14-no-redirect.log.
- Binance media upload presigned URL, image-status and PUT calls now reject redirects; they use an HTTP opener with redirect handling disabled. This prevents silent destination changes.
- Module 19/21 still need real authenticated provider/media validation; no live upload, DeepSeek request or Square post has been made.

## Module 19/21 no-redirect transport hardening — 2026-11-14
- Binance media API and presigned PUT operations now disable HTTP redirects to prevent destination changes after URL/key validation.
- Regression coverage added. Latest full suite: **495 passed, 0 failed, 12 skipped**; compileall and git diff --check passed.
- No live media upload performed; provider's current returned hostnames remain to be validated through an approved safe authenticated test.

## Module 17 draft provenance integrity update — 2026-11-14
- Fixed immutable provenance idempotency: an identical draft hash cannot silently be rebound to a different research package or approved claim set. Conflicting provenance now raises and requires a new editorial brief/version.
- Input validation strengthened for claim-ID sequences and text/visual validation hash/status/version/reason schemas.
- Focused regression batch: 24 passed, 0 failed; full-suite rerun pending.

## Module 21 exact draft provenance binding — 2026-11-14
- Authorization payload now binds draft_id, research_package_id, editorial_brief_id, approved_claim_ids and a provenance digest, not only text/image hashes.
- Authorization requires persisted exact draft and source/brief/claim references plus persisted PASS validation. Publisher rechecks the exact draft/provenance immediately before network POST and releases quota on mismatch/missing row.
- Added regression for no persisted draft and DB tampering of approved claim IDs; focused batch 44 passed, 0 failed. Full suite pending.

## Latest verification and provider readiness — 2026-11-14 23:05 UTC
- Full suite after Module 21 exact draft provenance binding: **499 passed, 0 failed, 12 skipped**; compileall and git diff --check passed. PostgreSQL tests skipped due missing TEST_POSTGRES_DSN.
- Local execution environment has no DEEPSEEK_API_KEY, SQUARE_API_KEY, CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, DATABASE_URL or TEST_POSTGRES_DSN configured; no .env files present.
- Workflow currently maps Gemini secret/model but runtime expects DeepSeek secret/model; Cloudflare credentials are not mapped; DRY_RUN remains "1". No workflow/secret changes made.
- Live provider integration is blocked until correct credentials/config are provisioned and an explicit safe non-publishing provider test is approved. No actual external request/upload/post has been made.

## Module 21 publish/reconciliation URL hardening — 2026-11-14
- Square publication POST redirects are disabled to prevent API-key/body forwarding to a new host.
- Manual reconciliation validates remote IDs and supplied Binance Square links against official HTTPS host and exact post ID/path; a failure decision cannot include a share link.
- Focused publisher/reconciliation tests: 31 passed, 0 failed; full suite pending.

## Module 21 latest gateway verification — 2026-11-14
- Square publish POST no longer follows redirects; operator reconciliation validates official HTTPS Binance post links and exact remote post IDs.
- Production code search found exactly one content/add endpoint reference (PostPublisher.API_URL in main.py).
- Full suite: **501 passed, 0 failed, 12 skipped**; compileall and git diff --check passed. No real post.

## Module 11 asset isolation update — 2026-11-14
- Base registry was global across candidate assets; candidate-specific drafting now scopes the registry to exact canonical asset ID before rendering/number allowlisting. Other-asset evidence cannot leak into a draft's context. Cross-asset evidence references become unresolved.
- Focused tests: 153 passed, 0 failed; full suite pending.

## Module 11 current verification — 2026-11-14 23:12 UTC
- Asset-scoped claim registry implementation passed full suite: **503 passed, 0 failed, 12 skipped**. compileall and git diff --check passed.
- 12 skipped require TEST_POSTGRES_DSN. Semantic sentence-level attribution remains an explicit acceptance gap.

## CI fixture failure diagnosis — 2026-11-15
- GitHub Actions run `43602790623` was inspected. Its 49 non-passing tests (48 errors, 1 failure) were caused by hard-coded 2026-11-11 on-chain test fixture timestamps running on 2026-11-14; the production freshness validator correctly returned `ONCHAIN_OBSERVATION_STALE`.
- The preserved local continuation worktree replaces those fixed fixture timestamps with current UTC-relative fixture data. No freshness policy or production validation was relaxed.
- Corrected focused Module 9 test batch: **74 passed, 0 failed**. Full local suite: **503 passed, 0 failed, 12 skipped**; the skips are PostgreSQL integration tests requiring `TEST_POSTGRES_DSN`.
- Static checks (`compileall`, `git diff --check`) pass. The corrected worktree remains uncommitted/unpushed, so the remote CI result is still the failure on the old committed files until a reviewed checkpoint is pushed and CI rerun.


## Module 11 continuation — unmatched announcement-detail laundering fix — 2026-11-15
- Found and fixed a classification gap: an unmatched `Detail:` headline with no exact accepted announcement-title evidence was labeled `ANALYST_INTERPRETATION`. This was unsafe because unverified non-factual claims are listed as qualified analysis rather than unresolved facts in the research package.
- Unmatched `Detail:` lines now remain `UNCLASSIFIED` under `announcement.title`, with no evidence IDs; exact accepted source-title matches still retain their source assertion and lineage. The unmatched claim is UNVERIFIED and forces `RESEARCH_MORE`.
- TDD regression was observed failing before the code change and passing afterward. Focused evidence/research/content-verification/end-to-end batch: **54 passed, 0 failed**.
- GitHub Actions for commit `ea753d2cdbfea37f714de1c8daa2b9309bd2faf3` succeeded: run `43636409987`, job `mocked-safety-tests`.
- Remaining Module 11 blockers are unchanged: complete semantic non-numeric/causal verification, reliable compound-clause splitting, complete sentence-to-evidence attribution for generated posts, and production persistence validation. This is a narrow defect fix, not Module 11 completion.


## Module 11 follow-up verification supersession — 2026-11-15
- The initial `Detail:` correction was narrowed after full-suite regression caught generated `Type: MARKET MOVEMENT` details being over-classified as unresolved factual claims.
- Final rule: `Detail:` under an explicit `Type: MARKET MOVEMENT` remains qualified `ANALYST_INTERPRETATION`; unmatched details under announcement types or without that explicit context remain `UNCLASSIFIED` unless exact accepted title evidence is linked.
- Added a regression for this explicit market-movement exception. Focused evidence/research/content/end-to-end/DeepSeek suite: **71 passed**. Full suite: **507 passed, 0 failed, 12 skipped**. `compileall` and `git diff --check` pass.
- This fixes the headline-classification laundering path without misclassifying the agent's own clearly labeled market-movement heuristic. General semantic fact/causal verification remains open; Module 11 is still PARTIAL.

## GitHub follow-up confirmation — 2026-11-15
- Follow-up implementation commit `43f5329103fc48772ce10503d55cac9349a9843e` is pushed to `layer-1/module9-onchain-continuation`.
- GitHub Actions run `43640134763` for that exact commit completed **SUCCESS**. PR #14 remains Draft/open/unmerged; its description now carries the latest 507/0/12 local test count and the remaining release blockers.


## Module 12 narrow material-change fix — 2026-11-15
- `sync_announcements()` now compares the previous persisted revision's explicit `event_at` with the incoming revision. A verified change to that event time is marked material and can move a CONFIRMED event to DEVELOPING.
- A changed content hash, source `updated_at`, or observation timestamp alone is not material. Two regression tests cover both positive and negative cases.
- Full suite: **509 passed, 0 failed, 12 skipped** (PostgreSQL integration requires `TEST_POSTGRES_DSN`); compileall and diff checks pass.
- Remaining Module 12 acceptance gap: semantic materiality for announcement body/title/status changes cannot be safely inferred from the currently persisted schema. Need structured source fields or a validated diff policy; no hash/title heuristics have been invented.

## Module 11 sentence splitter hardening — 2026-11-15
- Improved the existing deterministic atomic-claim splitter so common abbreviations (`U.S.`, `e.g.`, `i.e.`, `Dr.`, `etc.` and related forms) are not incorrectly split into separate claims at their internal periods.
- Added a regression that failed before the fix (`U.S.` and `e.g.` were split into fragments); after the fix the focused evidence-verification suite passes **41 tests, 0 failures**.
- This is a narrow segmentation correctness improvement only. It does not provide semantic compound-clause decomposition or generated-post sentence-to-evidence entailment; Module 11 remains PARTIAL.

## GitHub Actions provider wiring — 2026-11-15
- With explicit user approval, updated the scheduled workflow environment mapping from unused Gemini variables to the configured DeepSeek API key/model, and added the Cloudflare Workers AI token/account ID mapping. Kept the code-expected `ANNOUNCEMENT_DATABASE_URL` binding.
- The workflow remains `DRY_RUN: "1"`; schedule, Square key mapping, permissions, and publisher safety controls were not changed. No real post or live media upload was performed.
- Added regression assertions; focused workflow/importer and DeepSeek client tests: **19 passed**. YAML parse/binding assertions, compileall and `git diff --check` passed. Full suite / remote CI confirmation pending because Pillow is missing in the available local Python runtime.
- Workflow change is local only until pushed; actual scheduled GitHub Actions execution against DeepSeek has not yet been verified.

## Workflow integration CI confirmation — 2026-11-15
- GitHub Actions run `43644649579` for commit `2b8a3ec959d465a747fa54a51736e63fa459e475` completed **SUCCESS**. The mocked safety job compiled the project and ran the full unittest discovery: **510 passed, 0 failed, 12 skipped**. The 12 skips require `TEST_POSTGRES_DSN`.
- This verifies mocked safety and test suite compatibility with the workflow change. It is not a live DeepSeek/Cloudflare provider check and does not establish that the scheduled `run_bot.yml` workflow has successfully completed a provider-backed run.
- PR #14 remains Draft/open/unmerged. `DRY_RUN=1` remains set; no live inference, media upload or real Square post was triggered.

## Module 11 abbreviation-safe organization-name segmentation — 2026-11-15
- Added regression coverage for corporate suffixes (`Inc.`, `Corp.`, `Ltd.`, `PLC`, `LLC`, `Co.`) and clock-time abbreviations (`a.m.`, `p.m.`), which were previously split as sentence boundaries by `split_atomic_claims()`.
- TDD RED reproduced malformed fragments; GREEN extends deterministic protection for corporate suffixes and preserves sentence boundaries after `a.m.`/`p.m.`. Focused evidence-verification suite: **43 passed, 0 failed**.
- No NLP dependency or semantic inference added. This does not close semantic compound-clause decomposition or sentence-to-evidence entailment; Module 11 remains PARTIAL.
- Full repository verification pending; no provider calls or publishing actions.


## Module 11 verification clarification — 2026-11-15
- Rechecked the existing runtime path: `_persist_layer1_market_intelligence()` rebuilds and saves source-record claim registries; `_attach_claim_register()` scopes evidence to the asset, extracts package claims, verifies and saves the package registry, and builds a `ResearchPackageStore` record. Existing `tests/test_layer1_foundation.py` asserts SQLite claim-run persistence and cache idempotency. This confirms local SQLite integration coverage; it does not prove a separate production/PostgreSQL persistence boundary.
- Re-ran `tests.test_evidence_verification`: **43 passed**. A combined invocation including `tests.test_deepseek_generator` could not import `main` because this remote Python lacks Pillow (`ModuleNotFoundError: PIL`). No dependency was installed; this is an environment/import blocker, not a passing DeepSeek-generator result.
- `git diff --check` passed. Module 11 remains PARTIAL: semantic compound-clause extraction and sentence-level semantic entailment are not implemented; lexical similarity is not accepted as proof.


## Module 12 lifecycle revision checkpoint — 2026-11-15
- Re-audited the existing `layer1/event_lifecycle.py` state machine and its `main.py` ingestion/publishing call sites; retained the existing SQLite store, transition history, legal-transition table and fail-closed behavior.
- Added deterministic material revision detection for normalized announcement title and event type, alongside the existing effective event-time comparison. Cosmetic capitalization/spacing/punctuation differences do not create a material update; title changes such as a listing being postponed now transition a verified event from `CONFIRMED` to `DEVELOPING`. Content hash and source-update timestamp alone remain insufficient.
- TDD: new regression first failed because the event stayed `CONFIRMED`; after the fix, the complete lifecycle suite passed **17/17**. `git diff --check` passed.
- Module 12 remains **PARTIAL**: source model does not currently retain full announcement body/status/revision diff, and CMS fingerprint IDs still cannot safely correlate title revisions without a stable provider ID. Full semantic materiality and live source/restart integration remain open. No provider call, database provisioning, production write, publish, commit or push.


## Module 13 research-cutoff integrity checkpoint — 2026-11-15
- Re-audited `DeepResearchEngine.build()` and found a cutoff inconsistency: source coverage excluded post-cutoff evidence, but verified claims could still enter the package even when the claim or its only supporting evidence was observed/published after the cutoff.
- Applied one eligible-evidence set to both source coverage and claim attribution. Claims observed after cutoff are excluded from latest-claim selection. A claim can appear as a verified fact or contradiction only when at least one of its actual supporting evidence IDs resolves to accepted, exact-asset evidence published and observed by cutoff; otherwise it is downgraded to `UNVERIFIED`/unknown with no future evidence IDs.
- TDD: the new future-claim regression failed before the fix; both future-claim and future-only-support regressions pass after the fix. Full Module 13 test file: **10/10 passed**.
- Module 13 remains **PARTIAL**: broad acquisition/source-class coverage and live provider-backed reproducibility remain constrained by configured providers and the upstream unresolved-claim gate. No live API, production DB, publish, commit or push.


## Module 13 cutoff and contract validation checkpoint — 2026-11-15
- Extended the Module 13 research cutoff from coverage-only to claim-level enforcement. Claims observed after cutoff are excluded before latest-claim selection. Verified/corroborated facts and contradictions require at least one actual supporting evidence ID that resolves to accepted, exact-asset evidence published and observed by cutoff; future-only evidence is stripped and the claim becomes `UNVERIFIED`/unknown. Evidence updated after cutoff is also excluded.
- Added explicit validation for lifecycle-state values and source-kind values. Unknown states/classes can no longer silently pass through to a `READY` package.
- TDD regressions reproduced future-dated verified claims and unknown event states passing before the fix. Research package suite: **12/12 passed**.
- Module 13 remains **PARTIAL** pending broader source acquisition and real-provider reproducibility.


## Module 15 direct DeepSeek contract checkpoint — 2026-11-15
- Verified current official DeepSeek API docs: the official model-list endpoint is `GET https://api.deepseek.com/models`; current Chat Completions accepts `deepseek-flash` and `deepseek-v4-pro`, and the documented model ID for V4.1 Flash is `deepseek-flash`. The existing direct `https://api.deepseek.com/chat/completions` endpoint and model IDs remain valid.
- Added the official request option `safety_check: {level: high}` to the direct client. This uses DeepSeek's documented basic risk-control review; it does not replace local evidence or content gates. Added a request-contract assertion.
- Direct client suite: **11/11 passed** (mocked transport only). No live API call or paid inference was performed; provider credentials/access and actual response behavior remain unverified.
- Official references: DeepSeek model list, Chat Completions API and API change log (2026-11-13).
- Module 15 remains **PARTIAL** until a safe, explicitly approved real API request verifies the configured model/account.


## Module 17 draft provenance hardening checkpoint — 2026-11-15
- The draft persistence boundary previously accepted arbitrary non-empty strings as approved claim IDs. The evidence registry's claim IDs are lowercase SHA-256 digests, so this allowed malformed provenance to be stored even though later layers expected stable registry identifiers.
- `DraftStore.save_draft()` now requires every approved claim ID to match lowercase `[0-9a-f]{64}` before any insert. Updated unit fixtures to use digest-shaped identifiers and added malformed/uppercase/short/long rejection coverage.
- TDD regression failed against the previous implementation; after the change, Module 17 draft persistence plus Module 21 authorization tests passed **20/20**.
- Module 17 remains **PARTIAL** pending end-to-end live-provider output and independent semantic quality checks; no live generation, upload or publication was performed.


## Module 21 exact event-to-publication correlation audit — 2026-11-15
- Reverified `/tmp/binance-deepseek-verify`: branch `layer-1/module9-onchain-continuation`, HEAD `3fe895493ef35b8177b037eef382384c8392abb6`, 19 pre-existing modified tracked files at audit start, and `git diff --check` clean. No reset/checkout/clean, commit, push, merge or deployment.
- Confirmed the integrity defect by tracing announcement ingestion, candidate enrichment, research-package creation, editorial-brief persistence, draft provenance and publication authorization. The old per-asset dictionary collapsed distinct announcement events, while publication selected `latest_for_asset()` even though the selected editorial brief already carried an event identity. With two events for one asset, the latest record could be unrelated to the announcement used for the draft.
- Added exact source lookup (`get_for_source`) and a lossless `index_by_asset_source()` keyed by canonical asset, source ID and event type. Announcement hints now retain the source event type; candidate enrichment carries the selected announcement source identity; research/editorial creation uses that exact event. Publication authorization now resolves the lifecycle record by the selected editorial brief's event ID and rejects an asset mismatch; it no longer chooses the latest event for the asset.
- Deterministic two-events/one-asset regression confirms the old `latest_for_asset()` points to the second event while exact source resolution and the new index retain both event IDs. TDD RED initially failed because exact source resolution did not exist; GREEN passes after the minimal lifecycle-store addition.
- Verification: focused regression **1/1 passed**; lifecycle suite **18/18 passed**; publication authorization suite **10/10 passed**; full suite **533 tests, 0 failures, 12 skipped**; `compileall` and `git diff --check` passed. The 12 skips require `TEST_POSTGRES_DSN`; this is local SQLite/mock verification, not PostgreSQL durability or live provider verification.
- Module 21 remains **PARTIAL**. The exact event identity now flows through local announcement selection, research/editorial brief and the publication-time lifecycle lookup, but durable PostgreSQL event/draft correlation, recovery drills and safe provider submission/reconciliation remain unverified. No real Binance Square post, live DeepSeek/Cloudflare call, production DB operation or paid request occurred.
- Existing legacy `event_lifecycle_by_asset` / `event_lifecycle_id_by_asset` summary projections remain for compatibility and are lossy; event-specific decisions must use `event_lifecycle_by_asset_source` instead. No commit or push was made.


## Module 21 persistence backend audit — 2026-11-15
- Read-only follow-up inspection found that the current publication-critical persistence path is SQLite-only: `main.Database` opens `sqlite3.connect()`, `PostPublisher` uses that database, `DraftStore` and `PublicationAuthorizationEngine` explicitly require `sqlite3.Connection`, and `EventLifecycleStore` also requires the existing SQLite-backed `Layer1Store` connection.
- The only repository test module gated by `TEST_POSTGRES_DSN` is `tests/test_onchain_postgres.py`; the 12 skipped tests exercise Module 9 on-chain persistence, not Module 21 publication authorization/draft/event durability. The only PostgreSQL adapter/migration currently found is `layer1/onchain_postgres.py` and `layer1/migrations/postgresql/0001_onchain_storage.sql`, scoped to on-chain storage.
- Therefore, the 12 skips must not be described as skipped Module 21 PostgreSQL integration tests. Module 21 does not currently have a PostgreSQL persistence adapter or PostgreSQL authorization/draft/event integration suite. This is an architecture/implementation gap, not merely a missing DSN.
- No PostgreSQL resources were provisioned and no DB was modified. Implementing publication-critical PostgreSQL storage requires an explicit storage architecture and migration/transaction design across publisher attempts, quota reservations, drafts, validation results, event lifecycle and reconciliation; this audit did not attempt a broad storage rewrite.
- Module 21 remains **PARTIAL / BLOCKED for PostgreSQL production durability** until that backend exists and is tested against a dedicated isolated PostgreSQL database. SQLite tests remain local deterministic coverage only.


## Module 21 immutable event authorization and final pre-submit revalidation — 2026-11-15
- Continued from the exact existing worktree after re-verifying branch `layer-1/module9-onchain-continuation`, HEAD `3fe895493ef35b8177b037eef382384c8392abb6`, 19 pre-existing modified tracked files, and clean `git diff --check`. Preserved all pre-existing changes.
- Found a second event-provenance weakness: the immutable `PublicationAuthorization` included `editorial_brief_id` but did not include the exact `event_id`; `authorize()` also did not verify that the persisted editorial brief belonged to the persisted research package or that its event still matched the selected asset/lifecycle state.
- Added `event_id` to the immutable authorization payload (therefore included in its authorization digest). Authorization now resolves the persisted editorial brief by exact `brief_id`, requires its `research_package_id` to match the draft, and verifies the exact event record has the same canonical asset and a publishable lifecycle state matching the authorization snapshot.
- Added `validate_persisted_event_binding()` and invoked it again in `PostPublisher.publish()` immediately before the external HTTP POST, after the durable publication attempt reservation. If the event is withdrawn, its state changes, its asset changes, or the editorial-event link is altered/missing, the attempt is marked `FAILED_CONFIRMED`, quota is closed consistently, and the network POST is not made.
- TDD: test first failed because `PublicationAuthorization` had no `event_id`; after implementation, authorization tests cover exact event binding and state/asset mutation. Publisher safety regression mutates the event to WITHDRAWN after the durable attempt reservation and proves the external transport is never called.
- Verification after the final code change: focused Module 21 batch (`tests.test_publication_authorization`, `tests.test_publisher_safety`, `tests.test_event_lifecycle`) **52 passed, 0 failed**. Full suite: **536 tests, 0 failed, 12 skipped** (12 skips are the existing Module 9 on-chain PostgreSQL integration tests; no Module 21 PostgreSQL adapter/tests exist). `compileall` and `git diff --check` pass.
- Updated working tree now has **20 modified tracked files**, zero untracked files; branch and HEAD unchanged. No reset, commit, push, merge, deploy, live provider request, paid API call, production DB write, image upload or real Binance Square post.
- Module 21 remains **PARTIAL / BLOCKED for production durability**: publisher, drafts, authorization, quota and event lifecycle are still SQLite-backed. The existing PostgreSQL adapter/migration is Module 9 on-chain-only. A real Module 21 PostgreSQL backend, migration/transaction semantics, isolated PostgreSQL concurrency/rollback tests and recovery/reconciliation drill are still required; the 12 PostgreSQL skips do not test Module 21.


## Module 20 deterministic overlay verification hardening — 2026-11-15
- Re-audited the final image composition and found that Module 20 recorded the two deterministic text labels but did not persist their pixel bounds, font sizes, or text/background colors. The validator therefore could not prove that its own text layer was in bounds, readable, or non-overlapping.
- `ImageComposer` now records each rendered label's actual Pillow text bounding box, font size, RGB fill, and the exact lower-panel rectangle/RGBA fill in the immutable image sidecar.
- `VisualQualityEngine` now requires this geometry metadata and fails closed when it is missing or malformed. It checks canvas/panel bounds, text-box containment, minimum 28px font size, overlap, and conservative WCAG AA contrast (4.5:1) against the brightest possible panel background. Validation version is now `visual-quality-v2`.
- Publication authorization and the publisher's persisted pre-submit recheck now require `visual-quality-v2` PASS for the exact draft/image pair. An older `visual-quality-v1` PASS can no longer authorize or submit an image after the validator contract changed.
- Re-audited the legacy `ImageIntelligenceEngine` and found it generated a synthetic candlestick series from current price/change when no price history was supplied. Removed that fabricated chart path; without at least five supplied history points the renderer now shows `VERIFIED PRICE HISTORY REQUIRED` and draws no chart.
- TDD: new tests first failed against the prior implementation for missing overlay geometry, clipped/overlapping boxes, insufficient contrast/small text, obsolete visual validation versions, and fabricated chart history. After implementation, focused visual/image/publisher/auth/end-to-end batch passed **37 tests**, and visual/image batch passed **25 tests**.
- Full repository suite: **542 tests, 0 failures, 12 skipped**. The 12 skips are Module 9 on-chain PostgreSQL tests, not Module 21. `compileall` and `git diff --check` passed.
- Module 20 remains PARTIAL: deterministic checks cover only the renderer-owned two-label overlay; no independent OCR/vision audit verifies the generated AI background's semantic match or arbitrary text embedded by a provider. No image-generation provider call or media upload was made.
- Module 21 remains PARTIAL/BLOCKED for PostgreSQL durability. Installed `psycopg 3.3.9` only in the isolated temporary test venv, but a temporary local PostgreSQL 16 cluster could not initialize because this remote kernel returns `Function not implemented` for `shmget`. No PostgreSQL server/database was created, no production/Neon database was touched, and no paid infrastructure was provisioned. The publication-critical runtime remains SQLite-backed; a Module 21 PostgreSQL adapter and real integration/concurrency/recovery tests are still absent.
- Latest working tree: 24 modified tracked files, zero untracked files; branch `layer-1/module9-onchain-continuation`, HEAD `3fe895493ef35b8177b037eef382384c8392abb6`. All prior uncommitted work preserved. No commit, push, merge, deployment, live provider call, upload, or real Binance Square post.


## Neon persistence discovery — read-only audit, 2026-11-15
- Read-only Neon account inspection found the existing free-plan project `Binance-bot-staging` (`orange-glade-36037611`) under the `Binance bot` connection. Its default `staging` branch (`br-rough-mud-az28jpxs`) contains database `binance_bot_staging` with only `binance_announcement_events`, `binance_announcement_schema_migrations`, and `binance_announcement_worker_state`.
- Existing branches `module9-pg-integration-test` and `module9-pg-lease-fencing-disposable` contain those announcement tables plus the six Module 9 on-chain persistence tables. Read-only table listing found no Module 21 publication, quota, draft, authorization, event-lifecycle or reconciliation tables on these branches.
- No Neon SQL writes, schema changes, branch creation/deletion, endpoint provisioning or credential retrieval were performed. Remote shell has `DATABASE_URL`, `POSTGRES_DSN`, `PUBLICATION_DATABASE_URL`, `TEST_POSTGRES_DSN` and `ANNOUNCEMENT_DATABASE_URL` all unset.
- This corrects the earlier assumption that no PostgreSQL test route exists: an existing free Neon staging project is available for a disposable-branch integration path. The local PostgreSQL cluster still cannot bootstrap on this remote kernel (`shmget` unsupported). The Neon schema itself is not yet a Module 21 backend.
- Next safe step requires approval to create a temporary test branch from `staging`, validate the Module 21 schema/adapter there, and later explicitly approve discarding the temporary branch or applying a migration to the staging parent. The default staging branch must remain untouched until explicit approval.


## Module 14 deterministic decision identity and persistence hardening — 2026-11-15
- Re-audited `layer1/opportunity.py` and found that `decision_id` previously hashed only the outcome state, weighted score, reasons, policy version and a few coarse gate states. Distinct factor vectors or changed policy weights/thresholds could therefore collapse to the same ID when their displayed score/outcome matched. The append-only decision store also used `INSERT OR IGNORE` and silently accepted a conflicting payload/package for an existing ID.
- Decision identity now binds the exact normalized factor vector and factor-key set, full scoring policy snapshot (version, weights, thresholds and eligibility freshness bound), eligibility snapshot timestamp, effective freshness bound, research/event states, contradiction and unresolved counts, causal/duplicate/material-update flags, plus the resulting decision/reasons. JSON hashing rejects non-finite values.
- Policy validation now rejects non-string/empty versions and boolean, nonnumeric or non-finite thresholds. Eligibility max-age validation runs even when policy is unconfigured. Persisted decisions validate state, finite bounded score, policy version, reason tuple and SHA-256-shaped decision ID.
- `OpportunityDecisionStore.save()` now checks an existing ID's immutable stored package/outcome/score/reasons/policy payload and raises on conflicting reuse instead of silently ignoring it.
- TDD: regressions first failed on the old code for score-collision factor vectors, policy changes reusing an ID, invalid max-age acceptance, malformed thresholds, and silent decision-store conflicts. After implementation, Opportunity/Research/Editorial/End-to-end focused batch passed **31 tests**.
- Full repository suite: **548 tests, 0 failures, 12 skipped**. The 12 skips remain the Module 9 on-chain PostgreSQL integration tests; no Module 21 PostgreSQL integration is present. No real DeepSeek/Cloudflare request or Binance Square post occurred; provider transports in tests are mocked.
- Module 14 remains PARTIAL: the scoring policy still requires external human approval and evidence-backed factor values; this hardening makes decision identity auditable but does not approve or invent policy weights. No commit, push, merge or deployment.


## Module 14 persisted audit-input snapshot — 2026-11-15
- Extended `OpportunityDecision` with a canonical `input_snapshot_json` containing the exact factor vector/key set, policy weights/thresholds/version/freshness bound and gate inputs. The decision ID is now reproducible from outcome plus this snapshot.
- `OpportunityDecisionStore` adds the column additively for existing SQLite files, persists the full snapshot, verifies the decision digest before insert, and compares the snapshot on idempotent reuse. Existing decision rows are not dropped or rewritten.
- Added a persistence assertion proving the stored record retains factor values and policy version. Opportunity tests: **14/14 passed**. Full repository suite after this final change: **548 tests, 0 failures, 12 skipped**.
- This is local SQLite persistence coverage; PostgreSQL remains an open Module 21 integration gap.


## Module 21 PostgreSQL persistence foundation — 2026-11-15
- Added additive migration `layer1/migrations/publication_postgresql/0001_publication_storage.sql` and applied it to the existing disposable Neon branch `module9-pg-lease-fencing-disposable` (`br-falling-butterfly-az03rryi`) in both `binance_bot_staging` and `binance_onchain_test`. No new Neon branch/project/compute was created. The migration checksum is recorded and verified in both DBs; all newly added publication-critical tables are empty.
- Added explicit-DSN-only `PostgresPublicationStore` primitives for atomic daily quota reservation, same-symbol pending attempt exclusion, idempotency identity checks, forward-only state transitions, pending attempt listing and operator-evidenced reconciliation. Reconciliation updates attempt status, quota status and append-only audit record in one transaction.
- TDD evidence: state-machine/migration/identity contract tests pass. Four PostgreSQL integration tests are present and host/database/TLS guarded, but currently skip because `TEST_POSTGRES_DSN` is unset in the active worktree shell.
- Full suite: **559 tests, 0 failures, 16 skipped** (12 existing Module 9 PG skips + 4 new Module 21 PG integration skips); `compileall` and `git diff --check` pass.
- DSN was previously supplied only to an interactive shell in the separate `/tmp/binance-layer1-audit` worktree and explicitly unset after tests; the active `/tmp/binance-deepseek-verify` shell has no DSN and no repo `.env` file. Do not copy credentials from another worktree or retrieve/print secrets.
- **Still PARTIAL:** runtime is still SQLite-backed; draft/research/editorial/event/authorization PostgreSQL store methods, PostPublisher backend integration, real Python adapter integration/concurrency/rollback tests and crash/restart recovery drills remain outstanding. No real post, provider call, production DB write, credential/schedule change, commit, push, merge or deploy.


## Module 21 PostgreSQL DSN verification and live integration tests — 2026-11-15
- User created `/tmp/binance-deepseek-verify/.env`. Verified file exists, is a regular file, mode `0600`, and contains non-empty `TEST_POSTGRES_DSN` and `TEST_POSTGRES_ALLOWED_HOST`. The secret DSN/password was never printed or copied into project documentation.
- Sanitized DSN checks: scheme `postgresql`, expected Neon host `ep-autumn-frost-azvk3fj4.c-3.ap-southeast-1.aws.neon.tech`, database `binance_onchain_test`, TLS `sslmode=require`; expected-host allowlist matches. File size 278 bytes. The `.env` was loaded programmatically into Python rather than sourced by `/bin/sh`; do not rely on shell `.` for future validation.
- Verified live connection successfully: database `binance_onchain_test`, role `binance_bot_staging_owner`, schema `public`. Confirmed `publication_attempts`, `publication_quota_reservations`, and `publication_reconciliation_events` exist. A preliminary lookup used a guessed table name `publication_daily_quota` which is not the schema's actual table name; no schema change was made.
- Executed `tests.test_publication_postgres` with environment loaded directly from `.env`: **11 tests passed, 0 failures, 0 skipped**, including all four real Neon integration tests for concurrent quota reservations, idempotency/content binding, same-symbol attempt exclusion, and atomic unknown-outcome reconciliation. Tests completed against the disposable `binance_onchain_test` database.
- Test effects were confined to test fixtures/database rows used by the integration tests; no real Binance Square post or production publisher action occurred. No production/default branch writes, credential changes, schedule/workflow changes, commit, push, merge or deployment.
- Current branch/HEAD remain `layer-1/module9-onchain-continuation` / `3fe895493ef35b8177b037eef382384c8392abb6`. Existing modified/untracked project files preserved.
- Module 21 remains PARTIAL: this verifies the quota/attempt/reconciliation adapter and actual Neon integration tests only. PostgreSQL persistence for event lifecycle, research packages, editorial briefs, drafts, text/visual validation, image artifacts and opportunity decisions, plus authorization persistence and `PostPublisher` backend integration, are still required.


## Module 21 research-package and editorial-brief PostgreSQL persistence — 2026-11-15
- Added opt-in `PostgresPublicationStore.save_research_package()` / `load_latest_research_package()`. Writes canonical JSONB payloads as append-only versions under a per-research-key transaction advisory lock; exact hash/payload/cutoff replays return the original immutable row, conflicting reuse is rejected, and latest-version reads return the stored payload.
- Added opt-in `save_editorial_brief()` / `load_latest_editorial_brief()`. Editorial briefs are versioned under an event+angle advisory lock, FK-bound to an existing research package, idempotent for exact replays, and reject conflicting payload/research binding reuse.
- Added validation for non-empty identities, lowercase SHA-256 hashes, timezone-aware cutoffs, JSON-object payloads and finite JSON values. No change to SQLite defaults or automatic backend selection.
- TDD evidence: new validation test was observed RED before helper implementation; editorial integration test was observed RED before adapter implementation. Both research package and editorial brief live tests passed on the existing disposable Neon `binance_onchain_test` database. Final focused Module 21 test module: **14 tests passed, 0 failures, 0 skipped** (includes four publication-ledger integration tests plus research and editorial persistence integrations). `compileall` and `git diff --check` passed.
- Tests use uniquely namespaced fixtures and delete only those fixture rows. No production/default branch changes, real publisher activation, external provider calls or real Binance Square posts. No commit, push, merge or deployment.
- Still PARTIAL: PostgreSQL event lifecycle, drafts, text/visual validation, image artifacts, opportunity decisions, authorization, and publisher/backend integration remain unimplemented; crash/restart and full end-to-end durability validation remain open.


## Module 21 PostgreSQL event-lifecycle persistence — 2026-11-15
- Added opt-in event lifecycle persistence to `PostgresPublicationStore`: transaction/advisory-lock protected event creation and state transitions, append-only revision payloads, append-only transition history, exact latest-revision idempotency, immutable event/revision identity checks, and ordered load API.
- Validation mirrors the existing SQLite lifecycle transition graph and requires timezone-aware timestamps, lowercase SHA-256 revision IDs, finite JSON payloads, and non-empty evidence references. SQLite `EventLifecycleStore` behavior/default remains unchanged.
- TDD/live Neon evidence: initial live test caught duplicate replay handling; corrected and reran the Module 21 PostgreSQL suite **17/17 passed** on guarded disposable `binance_onchain_test`, including a two-worker same-event transition race (exactly one transition commits; the competing stale transition is rejected). Existing SQLite lifecycle suite **18/18 passed**; full repository suite **565 tests, 0 failures, 20 skipped** (run without PostgreSQL DSN; PG integration is separately run with guarded DSN). No production DB, real publisher, provider call or Binance Square post.
- Remaining Module 21 gaps: connect the existing research/editorial/draft/validation/image/opportunity/authorization models to the PostgreSQL backend; integrate `PostPublisher` with one durable transaction/attempt contract; extend concurrency coverage across cross-record workflows, test transaction rollback, crash/restart and end-to-end recovery; preserve SQLite as explicit legacy/default until a reviewed cutover exists. Module 21 remains PARTIAL.

## Module 21 PostgreSQL draft and validation persistence — 2026-11-15
- Confirmed the existing draft append-only API and added a two-worker live concurrency test. Per-draft advisory locking correctly serialized writes into versions 1 and 2; replay/idempotency, immutable provenance and FK binding tests pass.
- Added opt-in PostgreSQL save/load APIs for text and visual validation records. Both are append-only, hash-identified, JSONB-backed, exact-replay idempotent, and queryable by draft hash or exact draft/image pair. New validation versions preserve changed outcomes as new records.
- Added deterministic input normalization tests and live Neon integration tests for persistence, replay and latest-record reads.
- Guarded disposable database verification: `binance_onchain_test`, expected Neon host allowlist and TLS required; DSN loaded from local mode-0600 `.env` without printing secrets. Full `tests.test_publication_postgres`: **22 passed, 0 failed, 0 skipped**; draft/validation focused tests: **5 passed**.
- Remaining gaps: image artifact persistence, opportunity decision persistence, authorization persistence, PostPublisher durable-backend integration, transaction rollback and cross-record concurrency, crash/restart recovery and end-to-end durability. SQLite remains runtime default; Module 21 remains PARTIAL. No production publisher, credentials, schedules, live Binance post, commit, push, merge or deployment.


## Module 21 PostgreSQL image-artifact persistence — 2026-11-15
- Added opt-in `save_image_artifact()` / `load_image_artifact()` on `PostgresPublicationStore`, reusing the existing migration table without schema changes.
- Validation enforces the approved Cloudflare Workers AI provider/model, canonical asset ID, SHA-256 hashes, timezone-aware generation timestamp, bounded generation parameters, dimensions, image path and finite JSON metadata.
- Writes are serialized by a transaction-scoped advisory lock for the exact draft/image pair. Exact metadata/path replay returns the immutable artifact ID; conflicting provenance for the same pair is rejected.
- Deterministic validation and live disposable Neon persistence/replay/conflict tests pass **2/2**. Final complete `tests.test_publication_postgres`: **24 passed, 0 failed, 0 skipped** against guarded disposable `binance_onchain_test`; `compileall -q layer1 tests` and `git diff --check` pass.
- Remaining gaps: opportunity-decision persistence, authorization persistence, `PostPublisher` durable backend integration, rollback/cross-record concurrency, crash/restart and end-to-end durability. SQLite remains runtime default; Module 21 is PARTIAL. No production publisher, provider inference, real post, commit, push, merge or deployment.


## Module 21 PostgreSQL opportunity, authorization and atomic attempt ledger — 2026-11-15
- Added immutable research-bound opportunity decision save/load with digest verification, JSONB input snapshots, exact replay idempotency and conflicting-payload rejection.
- Added authorization save/load with integrity/expiry checks, exact editorial-event/research/draft/claim binding, text PASS and image artifact/current visual PASS checks, and exclusive quota binding in the same transaction.
- Added atomic authorized-attempt begin/finish operations: a persisted unexpired authorization is checked against exact symbol/content hash, a single pending attempt per symbol is enforced, and attempt/quota states advance together transactionally.
- Full PostgreSQL integration module: **27 passed, 0 failed, 0 skipped** against guarded disposable `binance_onchain_test`; focused opportunity **2/2**, authorization and no-network attempt/quota lifecycle **1/1**. `compileall` and `git diff --check` pass.
- Still open: wire `PostPublisher` to this backend under explicit opt-in and prove all publisher gates/final pre-submit checks/recovery paths; transaction rollback, cross-record races, process crash/restart and full end-to-end recovery. SQLite remains runtime default; Module 21 remains PARTIAL. No real Binance Square post, commit, push, merge or deployment.


## Module 21 full-suite verification — 2026-11-15
- Full repository suite with `TEST_POSTGRES_DSN` intentionally unset: **575 tests, 0 failures, 26 skipped**.
- Separate guarded disposable Neon integration run for `tests.test_publication_postgres`: **27 passed, 0 failed, 0 skipped**. These are separate test scopes; do not conflate full-suite skips with the live PostgreSQL result.
- `compileall -q layer1 tests` and `git diff --check` pass. `PostPublisher` remains on SQLite and the durable PostgreSQL store is opt-in only. Module 21 remains PARTIAL pending publisher wiring and crash/restart/end-to-end recovery.


## Module 21 PostgreSQL-backed publisher integration — 2026-11-15

- `PostPublisher` now accepts an optional explicit `postgres_store`; the normal constructor path remains SQLite-backed and unchanged. No environment-based DSN discovery or backend cutover was introduced.
- PostgreSQL opt-in publication uses `begin_authorized_attempt` and `finish_authorized_attempt`, keeping attempt and quota transitions atomic in PostgreSQL. It does not write publication attempts to the SQLite ledger.
- Added a PostgreSQL pre-submit revalidation transaction: persisted authorization expiry and identity, draft/brief/claim provenance, current event lifecycle, latest text validation, image artifact/current visual validation, and exact quota-to-attempt binding are checked immediately before the external request.
- Successful remote acceptance is first persisted as `PUBLICATION_UNKNOWN` with remote ID, then advanced to `PUBLISHED_CONFIRMED`; ambiguous HTTP/transport outcomes remain non-retryable. Existing pending attempts block submission.
- Unit verification: publisher-safety suite **25 passed**; full repository suite **577 passed, 0 failed, 26 skipped** with PostgreSQL test DSN unset; `compileall` and `git diff --check` passed.
- Two focused opt-in publisher tests use a mocked transport only. No real Binance Square post was made.
- Live PostgreSQL integration could not be run in this continuation because `TEST_POSTGRES_DSN` and `TEST_POSTGRES_ALLOWED_HOST` were not available in the remote shell. The PostgreSQL authorization-to-publisher integration test is present but remains unexecuted here.
- Module 21 remains **PARTIAL**: crash/restart recovery and full live PostgreSQL end-to-end verification remain open. SQLite remains the default runtime backend. No production credentials, schedules, publisher activation, commit, push, merge, or deployment were changed.


## Module 21 crash/restart recovery hardening — 2026-11-15 continuation

- Extended the disposable PostgreSQL unknown-outcome integration test to close the original DB connection and reopen a fresh `PostgresPublicationStore`, simulating process termination/restart. The test then verifies `list_pending_attempts()` still returns the durable `PUBLICATION_UNKNOWN` record and a repeated idempotency key resolves to the same existing attempt rather than creating a new submission.
- The same test proceeds through operator reconciliation and checks the terminal attempt, quota state, and audit event together. This is a live PostgreSQL test when the guarded `TEST_POSTGRES_DSN` is supplied; it was not executed in this continuation because the required DSN/host allowlist variables are absent.
- Static state-machine, migration-safety, identity tests: **7 passed**. Publisher safety tests: **25 passed**.
- Full suite was not rerun after this test-only recovery extension; prior verified full-suite result remains **577 passed, 0 failed, 26 skipped**. Syntax compilation and `git diff --check` passed after the extension.
- No automatic reconciliation or blind retry is introduced. `PUBLICATION_UNKNOWN` remains blocked until an operator supplies evidence and resolves it to a confirmed terminal state.
- Module 21 remains **PARTIAL** pending live guarded PostgreSQL restart/reconciliation execution and complete live publisher end-to-end verification.

### Module 21 — interrupted SUBMITTING recovery (2026-11-15)
- Closed a recovery-policy gap: operator reconciliation may now resolve either `SUBMITTING` (process died after reservation; remote outcome must be independently checked) or `PUBLICATION_UNKNOWN` attempts. This does not authorize automatic retry.
- Reconciliation retains the required operator/evidence/note fields and atomic attempt + quota + audit update. Terminal states remain immutable.
- Tests: publisher safety 25 passed; full suite 579 ran, 0 failed, 27 skipped. New guarded live PostgreSQL restart/reconciliation test was skipped because the test DSN/allowed-host environment variables were unavailable. Do not count it as verified.
- Status remains PARTIAL; live disposable PostgreSQL integration and publisher E2E are still outstanding.

### Module 21 — guarded live PostgreSQL end-to-end verification (2026-11-15)
- Ran `tests.test_publication_postgres` against the existing disposable Neon branch `module9-pg-lease-fencing-disposable` / database `binance_onchain_test`, with the exact host/TLS guard satisfied: **29 passed, 0 failed, 0 skipped**.
- The suite covers all publication PostgreSQL persistence adapters, append-only versioning, event lifecycle replay/transition concurrency, quota concurrency, same-symbol pending attempt fencing, authorization persistence, and both `PUBLICATION_UNKNOWN` and interrupted `SUBMITTING` process-restart/reconciliation paths.
- The actual `PostPublisher(postgres_store=...)` integration test ran against the disposable PostgreSQL ledger with a deterministic mocked Binance transport. It confirmed successful durable attempt/quota finalization and that a second invocation is blocked without a second transport call. This is not a live Binance publication test.
- Separate local full-suite result remains **579 tests, 0 failures, 27 skipped** with the PG DSN unset; separate live PG suite is **29/29 passed**. Do not merge these counts. `compileall` and `git diff --check` pass.
- Safety: the connection string was passed only to the remote test process and not printed or stored in repository files. No production/default DB, credentials, schedules, publisher activation, real Binance POST, commit, push, merge, or deploy.
- Do not run `tests.test_onchain_postgres` against this shared disposable branch in this continuation: its setup truncates Module 9 on-chain tables. That suite was intentionally excluded to preserve the branch's existing Module 9 test data.
- Status: Module 21's opt-in PostgreSQL adapter and mocked publisher integration are verified against the disposable test database. SQLite remains the runtime default; production cutover/activation is not performed or authorized. Overall project/module completion is not claimed from this isolated Module 21 test result.


## Module 11 explicit comma-adverb shared-subject segmentation — 2026-11-15
- TDD RED reproduced a concrete gap: `BTC rose 8%, then fell 4%.` and `ETH gained 3%, later dropped 2%.` remained single compound claims because the deterministic shared-subject splitter only recognized `and`/`but` conjunctions.
- Extended the narrow grammar to split only explicit comma + `then`/`later`/`subsequently` + recognized finite predicate, reusing the original explicit subject for the second predicate. Coordinated object lists and ambiguous elliptical constructions remain preserved; no NLP dependency or semantic inference was added.
- Regression test was observed failing before the change and passes after. Evidence-verification suite: **49 passed, 0 failed**.
- Full repository suite with PostgreSQL DSN intentionally unset: **580 tests ran, 0 failed, 27 skipped**. `compileall -q layer1 tests main.py` and `git diff --check` passed. The 27 PostgreSQL skips are not counted as live integration tests.
- This is a bounded segmentation improvement only. It does not establish sentence-level semantic entailment, resolve arbitrary compound/elliptical forms, or close Module 11. Unknown/ambiguous forms continue to fail closed. No live provider inference, production database write, publisher activation, real Binance Square post, commit, push, merge or deployment.


## 2026-11-15 — Announcement body provenance preservation (Modules 4, 11, 12)
- Audit found the read-only announcement importer selected the full CMS `body` column but discarded it when constructing `AnnouncementEvidence`; Module 12 therefore could not retain full source revision content even though the upstream ledger provided it.
- Added an optional backward-compatible `AnnouncementEvidence.body` field (default empty string), strict text-type validation, and passed the exact imported body into the evidence object. Existing SQLite `save_announcement()` and Module 12 revision payload serialization already persist the dataclass payload, so no new table or duplicate persistence layer was introduced.
- TDD regression was observed RED before the change (`AnnouncementEvidence` had no `body` attribute). After implementation, importer + event lifecycle + event graph focused suites: **38 passed, 0 failed**. This includes a new check that the exact body is present in the append-only event revision payload. `compileall` and `git diff --check` passed.
- This preserves the source body for downstream claim extraction and revision review; it does **not** prove semantic materiality of arbitrary body edits, complete claim-to-evidence entailment, or source-specific freshness policy. Module 12 and Module 11 remain PARTIAL. No live CMS connection, production DB write, publisher activation, real Binance Square post, commit, push, merge or deployment.


## Full-suite verification after announcement-body provenance change — 2026-11-15
- Full local unittest suite with `TEST_POSTGRES_DSN` and `TEST_POSTGRES_ALLOWED_HOST` unset: **581 tests ran, 0 failed, 27 skipped**. The skipped tests are guarded PostgreSQL integration tests; the separate Module 21 live Neon run remains **29/29 passed** and is not combined with this local count.
- Latest focused announcement-importer + event-lifecycle + event-graph batch: **38 passed, 0 failed**. `compileall -q layer1 tests main.py image_engine.py` and `git diff --check` passed after the code change.
- This confirms local regression coverage only. It does not close the documented semantic/source-provider/production acceptance gaps across Modules 1–21. No production DB, live CMS, live DeepSeek/Cloudflare inference, real Binance POST, publisher activation, commit, push, merge or deployment.


## Exact duplicate artifact cleanup — 2026-11-15
- SHA-256 audit of tracked files found two exact duplicate legacy Python entrypoint copies (`Main.pay` and `python agent_bot.py`) and two exact duplicate 1080x1080 PNG assets (`NEAR_20260626_000440_9cdf83a40992d848.png` and `NEAR_20260626_002414_65c7c25e71a0e4ae.png`).
- Confirmed the scheduled workflow invokes only `python main.py`; neither legacy duplicate entrypoint was referenced by `.github/workflows` or `scripts`. Removed only `python agent_bot.py`, retaining `Main.pay` as the one legacy copy. Removed only the later-named duplicate PNG, retaining the earlier `000440` copy; both had identical SHA-256 `bb080aabd15ed0b1767a8f21670b31ea23d2ea2c9ab721153090bbbb95e6cb22` and neither filename was referenced by source/docs.
- No `.env*` swap/backup files, posted-symbol records, publication logs, workflow entrypoint, `main.py`, or production data files were modified. Deletions remain local/uncommitted; no deployment occurred.


## Module 12 full-body revision materiality checkpoint — 2026-11-15
- TDD RED reproduced a lifecycle gap: with a stable provider article ID, a verified announcement could change its full body (including a scheduled listing date) while keeping the same title, event type and effective event timestamp; the event remained `CONFIRMED` instead of moving to `DEVELOPING`.
- Extended `_has_material_event_change()` to compare normalized full-body text in addition to title, event type and effective event time. Normalization is case/whitespace/punctuation insensitive. Any remaining normalized body difference is conservatively material; this is text-difference detection, not semantic interpretation. Empty legacy body vs empty body remains non-material; newly populated body vs absent body is material.
- Added regression covering a date change in body => `DEVELOPING`, and cosmetic case/spacing/punctuation changes => remains `CONFIRMED`. Regression failed before implementation and passed after. Lifecycle + event graph + announcement importer suites: **39 passed, 0 failed**.
- Full local suite with PostgreSQL DSN unset: **582 tests ran, 0 failed, 27 skipped**. `compileall` and `git diff --check` passed. The skipped PostgreSQL tests remain separately gated; no new live PostgreSQL run in this continuation.
- Module 12 remains PARTIAL: no semantic diff classifier, stable CMS revision ID unavailable for fingerprint-based records, and live provider/restart integration remains unverified. No live CMS, production DB, real Binance POST, publisher activation, commit, push, merge or deployment.


## Module 11 exact announcement-body attribution checkpoint — 2026-11-15
- TDD RED reproduced a provenance gap: `AnnouncementEvidence.body` was retained in source revisions, but the Module 11 evidence adapter emitted only title/event-type/freshness/asset records. A research-package `Detail:` containing an exact source-body passage therefore could not link to the source body.
- Added a typed `announcement.body` evidence record when a non-empty source body exists. `Detail:` lines now link to that record only when the complete text matches the source body (case-insensitive, surrounding whitespace ignored); title matching remains the existing exact title path. Paraphrases or partially overlapping statements remain UNCLASSIFIED with no evidence IDs and verify UNVERIFIED. This is exact-string provenance matching, not semantic entailment or proof that arbitrary claims follow from a passage.
- Added regression for exact source-body matching and paraphrase rejection. The regression failed before implementation and passed after. Evidence-verification suite: **50 passed, 0 failed**.
- Full local suite with PostgreSQL DSN unset: **583 tests ran, 0 failed, 27 skipped**. No PostgreSQL integration rerun in this continuation. Module 11 remains PARTIAL: sentence-level semantic entailment, compound/elliptical parsing beyond the bounded grammar, and complete claim attribution are still unresolved.
- No live provider call, production DB write, real Binance POST, publisher activation, commit, push, merge or deployment.


## Module 13 contradiction-evidence retention checkpoint — 2026-11-15
- TDD RED reproduced a research-package audit defect: `DeepResearchEngine.build()` selected only `supporting_evidence_ids` when filtering evidence by cutoff. For a `CONTRADICTED` result, the relevant IDs are in `contradicting_evidence_ids`, so the package retained the disputed claim but omitted the very evidence that contradicted it.
- Updated cutoff filtering to independently filter supporting and contradicting evidence IDs against the package's eligible evidence set. Contradicted claims now retain only cutoff-eligible conflicting evidence IDs; verified/corroborated facts continue to use supporting IDs. A contradiction with eligible conflicting evidence still forces `REJECT`.
- Added regression proving conflict ID retention and rejection. It failed before the fix and passes afterward. Module 13 focused suite: **13 passed, 0 failed**.
- Full local suite with PostgreSQL DSN unset: **585 tests ran, 0 failed, 27 skipped**. No new PostgreSQL integration run. `compileall` and `git diff --check` checked separately after edits.
- Module 13 remains PARTIAL pending broader source acquisition, multi-provider reproducibility, and full coverage of provider outage/independence scenarios. No live API, production DB, real Binance POST, publisher activation, commit, push, merge or deployment.

## Module 17 latest-validation ordering fix — 2026-11-15
- TDD RED reproduced a safety defect in `DraftStore`: when two text or visual validation records shared the same `created_at` timestamp, `latest_text_validation()` / `visual_validation()` broke the tie using lexical `validation_id`. A lexically larger older `PASS` could therefore outrank a later inserted `REJECT`, potentially exposing a stale approval.
- Changed both latest-record queries to use SQLite `rowid DESC` after `created_at DESC`, preserving append/insertion order for timestamp ties. No schema migration or production database operation was needed.
- Added a deterministic regression that inserts older `PASS` then newer `REJECT` with an identical timestamp and deliberately reverse-ordered IDs; the test failed before the fix and passes after for both text and visual validation.
- Modules 16–18 focused tests: **38 passed, 0 failed**. Full local suite using `/tmp/binance-module11-test-venv/bin/python`: **586 tests ran, 0 failed, 27 skipped**. The 27 guarded PostgreSQL tests are skips, not live DB verification. `compileall` and `git diff --check` passed.
- Module 17 remains PARTIAL pending direct DeepSeek generation/provider acceptance and independent semantic quality checks. Modules 16 and 18 remain PARTIAL for the documented angle/semantic-entailment, numeric/source/causal, originality and current platform-policy gaps. No live provider calls, real Binance POST, production DB/credential/schedule changes, publisher activation, commit, push, merge or deployment.


## Module 21 PostgreSQL run-lease persistence — 2026-11-15 continuation
- TDD RED reproduced a backend-boundary defect: `run_once()` always used the SQLite `RunLease`, even when the application selected the PostgreSQL publication backend. The regression failed before the backend-routing/fail-closed implementation.
- Added additive PostgreSQL migration `0003_layer1_run_lease.sql`; migrations 0001/0002 remain immutable. `PostgresPublicationStore` now performs atomic run+lease acquisition under a transaction-scoped advisory lock, active-lease inspection, and atomic run-finalization + lease deletion. The adapter shares the application-owned PostgreSQL connection.
- `main.run_once()` now uses PostgreSQL run leases only for explicit `PERSISTENCE_BACKEND=postgresql`; a missing PostgreSQL runtime store raises instead of silently creating/using SQLite. SQLite remains unchanged when explicitly selected/defaulted. Backend selection is included in the secret-free config fingerprint.
- Guarded disposable Neon integration: **2 passed, 0 failed**. Verified active lease visibility, competing-run rejection, finish/release and a two-connection race with exactly one winner. Cleanup is scoped to exact generated run IDs. No Module 9 on-chain tables were modified.
- Full local suite after final fail-closed refinement: **613 tests ran, 0 failures, 32 skipped** with PostgreSQL environment variables unset. The 32 skips are guarded PostgreSQL integration tests, not passes. `compileall -q main.py layer1 scripts tests` and `git diff --check` passed. Module 21 remains **PARTIAL**: Layer1 market/discovery/evidence/cache persistence and legacy posts/analytics still use SQLite; event lifecycle remains SQLite-origin with a PostgreSQL snapshot mirror. Provider, media-upload, scheduled-workflow and production acceptance gaps remain open. No production cutover, real Binance post, merge, deployment, commit or push.


## Module 21 remaining persistence-boundary audit — 2026-11-15 continuation
- `Layer1Store` remains a 13-method SQLite store for market observations/history, analyses, identity-proof cache, announcement evidence/revisions, trends/clusters, candidates, rejections and scores. `_persist_layer1_market_intelligence()` always instantiates it from `DATABASE_PATH`, even with PostgreSQL selected.
- Graph rebuild, evidence-registry rebuild, `ClaimRegistryStore` and `EventLifecycleStore` still depend on the SQLite connection or SQLite-specific query behavior. The claim registry is additionally snapshotted into PostgreSQL and event lifecycle is mirrored, but this does not make the discovery/evidence/graph tables PostgreSQL-authoritative.
- Legacy `Database` is also a 13-method SQLite contract. `PostPublisher` constructs it unconditionally; `main()`/`main_loop()` still use it for history, and `PerformanceAnalyzer` relies on SQLite SQL including `strftime` and `?` placeholders. Migration tables for `posts`, `post_analytics`, `metrics` and `runs` are not yet a complete runtime adapter.
- Next: introduce a store-neutral Layer1 persistence contract and a PostgreSQL implementation, then migrate graph/evidence/lifecycle consumers and test them against isolated PostgreSQL. Port legacy post/analytics storage afterward. Do not treat the current PostgreSQL option as a full discovery-to-publication backend, and do not cut over production.

## Module 21 store-neutral source-read contract — 2026-11-15 continuation
- Added `Layer1Store.iter_announcement_revisions()`, `iter_market_observations()`, and `iter_trend_signals()` as validated, deterministically ordered domain-record reads.
- `EventIntelligenceGraphEngine.rebuild_from_store()` and `EvidenceVerificationEngine.rebuild_from_store()` now use this store API rather than SQLite `.conn.execute(...)`. Missing contract methods fail closed with `TypeError`.
- TDD RED confirmed the new contract test failed before these methods existed. Focused foundation + graph + evidence + lifecycle regression suites: **182 passed, 0 failed**. Full local unittest discovery: **614 tests, 0 failures, 32 skipped** (guarded PostgreSQL skips, not passes). `compileall` and `git diff --check` passed.
- This is only the read-boundary extraction, not PostgreSQL support. No Layer1 PostgreSQL schema/adapter, PostgreSQL integration verification, claim-registry PostgreSQL runtime integration, event-lifecycle backend abstraction, or runtime backend wiring has been completed in this step. SQLite remains authoritative for these records.
- Current runtime fix worktree: detached `8b609ce29597cc36d4c1839f3c302f8d607e1fd6`, initially clean before this step; live remote branch resolves to the same SHA. Local `origin/...` tracking ref is stale at `8b1783dda9a21d23257843f37e21b0b5423333f3`. PR #14 is open and draft/unmerged; no Actions runs returned for commit `8b609ce`. Other worktrees were preserved; `/tmp/binance-layer1-audit` contains user changes and must not be modified.
- No commit, push, merge, deployment, production DB write, provider request, Binance POST, publisher activation, workflow/schedule change, or credential change.

## Module 21 PostgreSQL Layer1 discovery store — 2026-11-15 continuation
- Added additive migration `0004_layer1_discovery_store.sql` for the 10 Layer1 discovery/evidence persistence tables and history indexes; migrations 0001–0003 remain unchanged. No DROP, TRUNCATE, or DELETE DDL is included.
- Added `PostgresLayer1Store` in `layer1/layer1_postgres.py` implementing identity-proof cache, market observations/history, market analyses, announcement current state + append-only revisions, trend signals/clusters, candidates, rejection records and candidate scores. Writes are transaction-scoped; JSON payloads are JSONB; reads preserve deterministic order and domain validation. It shares the publication store's psycopg connection and does not own/close it.
- Guarded disposable Neon integration (`binance_onchain_test`, exact allowed host, TLS): **1 passed, 0 failed**. It round-tripped the source records and exercised all current Layer1 store write families. Cleanup used unique test identifiers. No Module 9 on-chain tables were accessed or modified.
- Local contract/migration tests: **3 passed**. Full local unittest discovery with PostgreSQL env unset: **618 tests, 0 failures, 33 skipped**; guarded skips are not passes. `compileall` and `git diff --check` passed.
- Remaining runtime wiring is explicitly open: `_persist_layer1_market_intelligence()` still constructs SQLite `Layer1Store`; `ClaimRegistryStore` and `EventLifecycleStore` need backend-neutral adapters; legacy `Database` and `PerformanceAnalyzer` remain SQLite-specific. No full discovery-to-publication PostgreSQL runtime claim is justified. Module 21 remains PARTIAL.
- No production DB, provider, real Binance POST, publisher activation, credential/schedule/workflow change, merge or deployment.

## Module 21 PostgreSQL Layer1 runtime routing — 2026-11-15 continuation
- `_persist_layer1_market_intelligence()` now routes Layer1 discovery/evidence/cache/analysis/candidate/score persistence and graph/evidence source reads through `PostgresLayer1Store` whenever the explicit PostgreSQL publication store is supplied. SQLite remains the default path.
- PostgreSQL mode now persists the base claim-verification snapshot only through `PostgresClaimRegistryStore`; duplicate SQLite claim-registry persistence is removed. Per-asset claim snapshot handling no longer opens an unused SQLite connection in PostgreSQL mode.
- Event lifecycle remains a transitional SQLite state machine with a dedicated SQLite connection and exact PostgreSQL history mirror. The direct-connection constructor support removes its dependency on a full SQLite `Layer1Store`, but this is not native PostgreSQL event-lifecycle ownership. That is the next persistence boundary to migrate.
- TDD + focused regression: **187 passed, 0 failed**. Full local suite: **620 tests, 0 failures, 33 skipped** (guarded PG skips, not passes). Compileall and diff-check passed. The separate real Neon `PostgresLayer1Store` integration was **1 passed** in the previous slice; no real provider/publisher run was performed for this routing change.
- No production DB, live provider, real Binance POST, publisher activation, credentials/schedules/workflows, merge or deployment.

## Module 21 PostgreSQL legacy post-history and analytics — 2026-11-15 continuation
- Added `PostgresLegacyDatabase` for the complete legacy `Database` read/write method surface, using existing PostgreSQL `posts`, `metrics`, `runs`, and `post_analytics` schema. `PostPublisher` selects this adapter when PostgreSQL is selected; PostgreSQL mode no longer creates a local SQLite Database. Existing SQLite-only raw connection paths remain backend-conditional.
- Added `PostgresPerformanceAnalyzer` for publication metadata, metrics updates keyed by exact remote post ID, and insight summaries. PostgreSQL posting-hour aggregation uses `EXTRACT` rather than SQLite `strftime`. SQLite analyzer remains for SQLite mode.
- PostgreSQL publisher now durably inserts the local post-history row after persisting remote identity as `PUBLICATION_UNKNOWN` and before terminal `PUBLISHED_CONFIRMED`. A failure in the local history insert leaves the attempt recoverable as unknown with remote identity retained. Analytics references the exact local post ID.
- Guarded Neon integration: **1 passed** for all legacy DB methods and analytics; **1 passed** for mocked-transport PostgreSQL publisher E2E, including post-history row, attempt/quota finalization, duplicate blocking, and no SQLite DB file. No real Binance POST.
- Focused local regression: **28 passed**. Full local suite: **628 tests, 0 failures, 37 skipped** (guarded PostgreSQL skips, not passes). Compileall and diff-check passed.
- Additional guarded Neon runtime integration: **2 passed**. It exercised the actual Layer1 runtime persistence function with the real PostgreSQL store/adapters and proved claim-registry persistence plus no SQLite file creation; the second test round-tripped all Layer1 store families. External announcement DB was disabled and candidate input was empty, so this was persistence routing verification, not provider or publishing E2E.
- Persistence boundary audit: all known runtime discovery/evidence/graph/claim/event lifecycle/run lease/post-history/analytics persistence now has a PostgreSQL implementation when explicitly selected. Remaining gaps are full end-to-end provider/media/scheduled acceptance and production approval. Module 21 remains PARTIAL until those acceptance gates pass.

## Module 21 PostgreSQL-native event lifecycle — 2026-11-15 continuation
- Added `PostgresEventLifecycleStore` using existing PostgreSQL lifecycle tables and the publication store's shared connection. It preserves the existing state machine, append-only revisions/transitions, exact source identity, material-change rules, verification-gated resolution/withdrawal, stale handling and deterministic reads. Advisory locks + row locks protect concurrent observations; current state and history writes are transactional.
- PostgreSQL runtime now selects this native adapter. It performs a guarded compatibility bootstrap from legacy SQLite only for event IDs absent from PostgreSQL, using the existing snapshot importer and its exact-prefix divergence checks. After import, PostgreSQL owns lifecycle updates; no SQLite lifecycle mirror writes are performed in PostgreSQL mode. SQLite mode is unchanged.
- Guarded disposable Neon lifecycle integration: **2 passed, 0 failed**, covering first observation, verification, confirmation, material revision, duplicate replay, legacy snapshot bootstrap and idempotent re-bootstrap. Exact generated IDs were used for cleanup.
- Focused local runtime/lifecycle tests: **24 passed**. Full local suite: **624 tests, 0 failures, 35 skipped** (guarded PostgreSQL skips, not passes). `compileall` and `git diff --check` passed.
- Legacy post-history and analytics are now covered by the following PostgreSQL implementation checkpoint. The remaining gap is full runtime/provider/media/scheduled acceptance; no production cutover, provider run, or Binance publication.

## Module 12 semantic event revision classifier — 2026-11-16
- Added deterministic token-level normalization for title/body revisions. It canonicalizes a bounded set of grammatical variants and function words but preserves token order, negation, entities, numbers, dates/times and status/action tokens. A substantive ordered-token difference remains conservatively material; this is not a general NLP semantic classifier.
- The prior comparator falsely moved a confirmed event to DEVELOPING for an active-voice grammar paraphrase that preserved the same listing facts. A regression test reproduced the failure before the fix.
- SQLite lifecycle tests: **23 passed**; local lifecycle + PostgreSQL adapter contract tests: **25 passed**. Guarded disposable Neon lifecycle integration: **3 passed**, proving paraphrase remains CONFIRMED while a trading-suspension status change moves the event to DEVELOPING.
- Full local suite: **631 tests, 0 failures, 38 skipped** (guarded PostgreSQL skips, not passes). Compileall and diff-check passed.
- Remaining semantic evidence gaps: causal/compound claim coverage and full generated-post sentence-to-evidence attribution acceptance. Module 12 remains an acceptance gap until a broader owner-reviewed semantic policy is specified and tested. No live Binance POST or production changes.

## Module 11 causal/compound claim evidence guard — 2026-11-16
- Hardened `EvidenceVerificationEngine._verify_one`: one structured field/value evidence link can no longer verify a claim whose text adds a recognized causal relation or contains multiple independent atomic propositions. Such claims stay `UNVERIFIED` with explicit causal/compound issue codes.
- Exact attributed source assertion exception is limited to accepted, exact announcement title/body evidence and canonical source-assertion text. This closes the prior route where arbitrary causal prose could inherit a price or announcement-body evidence link.
- TDD reproduced the prior false `VERIFIED` outcomes for causal, compound and laundering cases. Evidence module: **55 passed**. Full suite: **636 tests, 0 failures, 38 skipped** (guarded PostgreSQL skips, not passes); compileall and diff-check passed.
- Scope limitation: deterministic bounded phrase detection and atomic splitter, not general NLP causal reasoning. Broader semantic coverage and full generated-post attribution acceptance remain open.

## Module 11 generated-post causal attribution integration — 2026-11-16
- Added a deterministic end-to-end test across claim verification and generated-post content validation. A claim marker cannot publish an unsupported causal sentence when its linked source only verifies the market field; the content gate rejects the unverified reference and unresolved asset claim.
- No live model call, Binance transport, or publication is performed by this test.
- Full suite: **637 tests, 0 failures, 38 skipped** (guarded PostgreSQL skips, not passes); compileall and diff-check passed.

## Module 11 one-to-one generated sentence attribution — 2026-11-16
- Added a positive-path test proving two separate factual sentences map to two distinct verified claim IDs and both are the only approved IDs. Negative-path causal attribution remains rejected when only market-field evidence is linked.
- Full suite: **638 tests, 0 failures, 38 skipped** (guarded PostgreSQL skips, not passes); compileall and diff-check passed.

## Module 19/21 Binance media-upload acknowledgement hardening — 2026-11-16
- Audit found `_upload_to_presigned_url()` accepted any returned HTTP status as success, despite the documented successful PUT statuses being HTTP 200/201. This could advance to image-status polling after a storage upload was not acknowledged as complete.
- TDD: added a status-matrix regression test; before the fix, 202/204/302/400/500 all incorrectly returned success. The uploader now accepts only 200/201 and rejects all other response statuses. Existing HTTPS presigned-host allowlist and redirect refusal are unchanged.
- Focused Cloudflare image-generation + deterministic pipeline tests: **17 passed, 0 failed**. Full repository unittest discovery: **639 tests, 0 failures, 38 skipped** (guarded PostgreSQL integration skips, not passes). `compileall` and `git diff --check` passed. No real Cloudflare request, Binance media upload, real Square post, production DB, credential/workflow/schedule modification, merge or deployment.
- This closes only the HTTP acknowledgement handling defect. Authenticated Cloudflare inference, actual Binance media upload and full scheduled provider-backed execution remain unverified; Modules 19–21 remain **PARTIAL**.

## Module 19 Binance media-upload sequence regression — 2026-11-16
- Added deterministic integration tests for the Binance media flow. Success path must call presigned URL → storage PUT → image status in that order and return the processed CDN URL. If storage PUT is not confirmed, image-status polling must not run.
- All network-facing steps are stubbed. Focused image-generation suite: **18 passed**. Full local suite: **641 tests, 0 failures, 38 skipped** (guarded PostgreSQL integration skips, not passes). Compileall and diff-check passed.
- This is mock-based orchestration evidence only; no authenticated media upload, live provider request, real Square post, production DB, workflow/schedule modification, merge or deployment. Module 19/21 remain PARTIAL.

## 2026-11-16 PostgreSQL acceptance continuation
- Located the existing guarded test environment at `/tmp/binance-deepseek-verify/.env` (mode `0600`). It contains only `TEST_POSTGRES_DSN` and `TEST_POSTGRES_ALLOWED_HOST`; secret values were not printed, copied into docs, or moved. The active working repository remains `/tmp/binance-runtime-fix`; the env file is in a separate worktree and was read programmatically for the test process only.
- Verified the DSN scheme, exact allowlisted Neon hostname, database name `binance_onchain_test`, and `sslmode=require`; an actual psycopg connection confirmed `binance_onchain_test` / `public`.
- Ran `tests.test_publication_postgres` against the disposable Neon database: **34 tests passed, 0 failures, 0 skips** (127.19 seconds). This includes the guarded PostgreSQL publication adapter/reconciliation/publisher tests with deterministic mocked Binance transport; it is not a real Binance publication.
- A broader batch covering Layer1, claim-registry, event-lifecycle and legacy PostgreSQL modules was interrupted while waiting inside the semantic event-lifecycle integration test. It is not counted as a pass. The interrupted test was then rerun individually with bounded PostgreSQL statement/lock timeouts and passed: **1/1**. No destructive `tests.test_onchain_postgres` suite was run because it truncates Module 9 on-chain tables.
- Verified GitHub branch `layer-1/module9-onchain-continuation` still resolves to `0c0b530c6dd8f7353dc0c7ecd6d4b78ae667d7a7`; active working tree was clean and no application code changed during this continuation.
- Remaining acceptance blocker: the located `.env` contains no DeepSeek, Cloudflare or announcement-database credentials. Earlier remote environment inspection also found those provider variables unset. Therefore authenticated DeepSeek generation, Cloudflare inference, external announcement ingestion and actual Binance media upload remain unverified. Do not trigger the scheduled GitHub workflow or any live provider/publisher path without explicit authorization.
- Production publisher remains inactive; no real Binance Square post, production DB operation, credential/schedule/workflow modification, merge or deployment occurred.

## 2026-11-16 acceptance checkpoint
- Branch/PR #14 head verified before documentation update: `4dd006834e0d265411119fa276ff2808d0ab701f`; PR remains open, draft, and unmerged.
- CI run `43770662317`: completed/success for the `mocked-safety-tests` job on the preceding code commit. It is mocked safety CI, not provider-backed or production acceptance.
- Local full suite: **641 passed, 38 skipped, 0 failures**; skips are guarded PostgreSQL integration tests, not passes.
- Disposable Neon PostgreSQL: publication integration **34/34 passed**; one semantic event-lifecycle integration **1/1 passed**. Broader PG batch was interrupted; Layer1/claim-registry/legacy batch is not accepted as passing.
- DeepSeek and Cloudflare authenticated API checks remain NOT RUN / unverified because no corresponding credentials were found in the inspected test environment. No real Cloudflare inference, Binance media upload, external announcement ingestion, or Square publication.
- Existing deterministic media tests verify HTTP acknowledgement and upload sequencing only with mocked network calls.
- No production DB, publisher activation, real post, credentials/schedules/workflow changes, merge, deployment, or paid resources.
- Outstanding next gate: safely validate provider credentials through the existing secure environment and obtain explicit authorization before any potentially billable live provider request. Then test DeepSeek and Cloudflare separately, without invoking the scheduled workflow or production publishing path.


## 2026-11-16 manual provider-verification workflow checkpoint
- User explicitly approved creating a separate manual-only provider verification workflow on the condition that API keys must never be exposed.
- Added `.github/workflows/provider-verification.yml` (workflow_dispatch only) and `tests/test_provider_verification_workflow.py` on `layer-1/module9-onchain-continuation`.
- Workflow uses only existing GitHub Secrets/Variables: `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `CLOUDFLARE_API_TOKEN`, and `CLOUDFLARE_ACCOUNT_ID`. Secret values are passed only as process environment variables; the script does not print, serialize, echo, or upload them. Shell tracing is disabled.
- The job has read-only contents permission, a five-minute job timeout, one bounded DeepSeek completion (20-second timeout, zero retries, 32-token cap), and one 256x256 Cloudflare Workers AI image generation (60-second timeout). It logs only pass/fail, model, latency, token count, image metadata, and exception class; it does not log generated text, auth headers, response bodies, or secret values. Temporary image output is deleted and is not uploaded.
- Both provider checks run independently. The workflow does not invoke `main.py`, `run_bot.yml`, the publisher, Binance APIs, Square credentials, announcement DB, production DB, caches, or artifact uploads. Existing scheduled `run_bot.yml` was inspected and left unchanged.
- Static safety tests were added, but have not yet been executed in this environment. GitHub Actions may run the repository's existing mocked push CI due to commits on the layer-1 branch; that is separate from live provider verification.
- **Live verification has NOT been run.** The workflow has not been manually dispatched; no provider API request has been made by this workflow. DeepSeek/Cloudflare calls may incur provider usage charges. Obtain explicit confirmation before manually running it.
- PR #14 remains open, draft, and unmerged. No real Binance Square post, publisher activation, production DB operation, credential/schedule modification, merge, or deployment.


## Provider verification follow-up — 2026-11-16

- Latest manual provider run `43781609081` checked out the dedicated implementation branch successfully and completed the Cloudflare Workers AI 256x256 image-generation check successfully.
- The DeepSeek step returned a failure because the workflow required the generated assistant text to equal one exact sentinel string. That is an unnecessarily strict assertion for an authenticated generation smoke test; wording can vary even when a valid completion is returned.
- The manual workflow was changed to accept any non-null `DeepSeekClient.chat()` result. The client itself only returns a result after validating a non-empty assistant message, model identity, response object, and normal completion. A `None` result still fails the check.
- A regression test now guards against reintroducing the exact-string comparison.
- Commits: workflow fix `e149e0a6fa2a44827fb8095f01545d2523fa3f1d`; regression test `ce1637e972921c6085a566155b60414341e31292`.
- Manual provider run `43782717263` on `main` completed successfully with both real authenticated checks passing: DeepSeek `deepseek-flash` (997 ms, 30 total tokens) and Cloudflare Workers AI `@cf/black-forest-labs/flux-2-klein-4b` (JPEG 256x256, 6132 ms). This is live provider evidence, not a mocked test.
- Credentials are not printed. Production publisher, scheduled workflow, production database, and publishing credentials remain untouched.


## 2026-11-16 scheduled-workflow restoration and CI compatibility audit

- User-approved restoration commit: `3da5c20f9d7af32e6d914bbada07d210bf6aeff4`. Only `.github/workflows/run_bot.yml` was restored to the exact base-branch blob; verification confirmed byte-for-byte content equality with `layer-1/module9-onchain-intelligence`. The workflow schedule and `DRY_RUN: "1"` were preserved.
- The first post-restoration Phase 1 Safety Tests run `43785915439` failed after **649 tests: 610 passed, 1 failed, 38 skipped**. The sole failure was a stale assertion in `tests/test_module4_announcement_importer.py` that incorrectly coupled an importer-dependency test to DeepSeek/Cloudflare workflow variables and prohibited Gemini variables. No application behavior failed in that run.
- Removed only those unrelated provider-variable assertions in commit `6c04de2e021dd64618df521921720cfef5b3118b`; importer dependency, dry-run and read-only announcement DB assertions remain. The resulting Phase 1 run `43786286550` was in progress when this checkpoint was written; do not count it as passing until its completed conclusion is checked.
- **Release blocker retained:** PR branch `main.py` configures and invokes `DeepSeekGenerator` using `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL`, but the restored `run_bot.yml` injects `GEMINI_API_KEY` / `GEMINI_MODEL`. The base branch `main.py` is Gemini-based, while the PR implementation is DeepSeek-based. This is a genuine runtime configuration incompatibility for the merged scheduled workflow. It was deliberately not changed because the user's approval covered restoring this workflow file only. Do not merge or deploy until the user explicitly approves a compatible production workflow configuration and it is independently safety-reviewed.
- No scheduled workflow was dispatched; no Binance POST, production DB write, credential/schedule change, merge, or deployment occurred. The PR remains open/draft/unmerged.


## 2026-11-16 latest-branch PostgreSQL acceptance verification

- Acceptance worktree was created separately at current PR head `a4677d705b313e04b54e479cd2871ce1609d717f`; the pre-existing `/tmp/binance-runtime-fix`, `/tmp/binance-deepseek-verify`, and `/tmp/binance-layer1-audit` worktrees were not checked out, reset, or overwritten.
- Used only the existing guarded test environment `/tmp/binance-deepseek-verify/.env`. It contains the disposable `binance_onchain_test` PostgreSQL DSN and exact host allowlist; no provider credentials or announcement DB credential were loaded or exposed. Tests verified database name, exact allowlisted host and TLS before running.
- Current PR-head integration results on that disposable DB: `tests.test_claim_registry_postgres` **1/1 passed**; `tests.test_layer1_postgres` **2/2 passed**; `tests.test_event_lifecycle_postgres` **5/5 passed**; `tests.test_legacy_postgres` **3/3 passed**. Tests use generated identifiers and exact-row cleanup. No `tests.test_onchain_postgres` run was made because that suite truncates Module 9 tables.
- Existing earlier acceptance evidence remains: `tests.test_publication_postgres` **34/34 passed** with mocked Binance transport; it is not a real publication. The four current-branch suites above add 11 fresh PostgreSQL integration passes.
- GitHub Actions run `43786286550` on code commit `6c04de2e021dd64618df521921720cfef5b3118b` completed SUCCESS: `compileall` passed and **649 tests ran, 0 failures, 38 skipped**. The 38 skips are guarded DB tests in CI; the selected PostgreSQL suites were run separately as recorded above. Subsequent commits `a9a5dca2012910358c35534b217a28aedfbe5b17` and `a4677d705b313e04b54e479cd2871ce1609d717f` update documentation only.
- No real Binance POST, publisher activation, production DB operation, scheduled workflow dispatch, credentials/schedule change, merge or deployment occurred.
- Remaining blockers are unchanged: Module 11/12 bounded semantic limitations; Module 13 source-acquisition and outage/independence coverage; Modules 16–18 full semantic/originality/policy acceptance; Module 19 authenticated Binance media upload; Module 20 independent OCR/vision validation; Module 21 complete end-to-end runtime acceptance and production persistence cutover. The PR scheduled workflow provider mismatch recorded above remains a hard release blocker.


## 2026-11-16 — DeepSeek/Cloudflare scheduled-workflow alignment
- User explicitly approved aligning only the provider environment mappings in `.github/workflows/run_bot.yml`.
- Commit: `0a97bfa848c3700400120b32eb4cfb04f437ebe8`.
- Replaced `GEMINI_API_KEY` / `GEMINI_MODEL` with `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL=deepseek-flash`; added `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`. Existing `SQUARE_API_KEY`, `GH_TOKEN`, and `ANNOUNCEMENT_DATABASE_URL` mappings were preserved.
- Verified the workflow diff contains only these provider mapping changes. Five-minute cron (`*/5 * * * *`) and `DRY_RUN: "1"` are unchanged. No dispatch or scheduled run was triggered.
- GitHub Actions run `43786947834` on the exact workflow-change commit completed SUCCESS: Python compile step passed and the full mocked publication safety test job passed. This is CI evidence, not a scheduled workflow runtime test.
- PR #14 remains OPEN / DRAFT / UNMERGED. No production publisher activation, Binance POST, production DB operation, merge or deployment occurred.
- Prior authenticated provider smoke evidence remains separately valid: run `43782717263` verified one DeepSeek `deepseek-flash` completion and one Cloudflare Workers AI image generation. It did not invoke the scheduled bot workflow or Binance publisher.
- The former Gemini/DeepSeek environment mismatch is closed in the PR branch configuration. Remaining release blockers are unchanged: scheduled runtime is intentionally not dispatched; Modules 11–18 have semantic/source/policy acceptance gaps; Module 19 real Binance media upload is unverified; Module 20 independent OCR/vision acceptance is incomplete; Module 21 end-to-end runtime and production persistence cutover are incomplete. Do not mark the project production-ready.

## Module 11 temporal compound-claim guard — 2026-11-16
- On the latest fetched continuation head `85351ba9c1af429bcdd5bb807d66d342794a03dd`, source audit found a concrete evidence-laundering gap: `split_atomic_claims()` did not split a shared-subject temporal construction such as “ABC price rose 8% before falling 4%”. `_verify_one()` therefore treated it as one proposition and allowed a single `market.price_change` evidence record to return `VERIFIED`.
- TDD RED: added a regression for both “before falling” and “after rising”; both cases returned `VERIFIED` before the fix. GREEN: added a bounded temporal-action pattern (`before|after` followed by a gerund) to the existing compound-claim gate. Such claims now remain `UNVERIFIED` with `COMPOUND_CLAIM_REQUIRES_ATOMIC_EVIDENCE` unless they are an exact canonical primary announcement source assertion.
- Added a negative control: a single fact with a date modifier (“before 2026-11-20”) remains `VERIFIED`; the guard does not flag a date-only temporal modifier.
- Focused evidence-verification suite: **56 passed, 0 failed**. Full local unittest discovery on `/tmp/binance-continue-85351`: **650 tests, 0 failures, 38 skipped**. The 38 are environment-guarded PostgreSQL tests and are not counted as passes. `compileall` and `git diff --check` passed.
- Scope is deliberately bounded lexical protection, not general NLP or semantic entailment. Other temporal/elliptical constructions may still need policy-backed coverage. No provider calls, Binance media upload, real Square post, production database operation, workflow/schedule change, merge or deployment occurred.
- Work was performed in a new detached worktree `/tmp/binance-continue-85351` at the fetched remote head. Existing worktrees were not checked out, reset, cleaned or overwritten. With explicit user approval, the four-file change was committed as `d3ae64fd29bd60616cc5d18d5f7859cc9c814b95` and pushed fast-forward to `layer-1/module9-onchain-continuation` (PR #14 head branch). GitHub commit retrieval confirmed the commit and exact diff. No merge, deployment, workflow dispatch, provider call, media upload, production DB operation or Binance post occurred.

## Module 11 shared-subject sequential-action guard — 2026-11-16 (local verification checkpoint)
- Re-audit found that shared-subject sequences without an explicit conjunction, e.g. “ABC price rose 8% then fell 4%” and “ABC price rose 8% later fell 4%”, escaped the existing splitter and could be marked `VERIFIED` from one market-field evidence record.
- TDD RED reproduced the false `VERIFIED` result for the bare `then` and `later` cases. A comma + `subsequently` control was already rejected by the earlier grammar.
- Extended `_SHARED_SUBJECT_CONJUNCTION` to recognize standalone `then`, `later`, and `subsequently` before a known finite predicate and reconstruct the shared subject. Focused evidence-verification suite: **57 passed**. Full suite in the existing Pillow-enabled isolated venv: **651 tests, 0 failures, 38 guarded PostgreSQL skips**. `compileall` and `git diff --check` passed.
- The system interpreter lacks Pillow, so its attempted full discovery produced 19 import errors; those are environment/import failures, not application test failures. The isolated venv run is the valid full-suite result. No packages were installed.
- Local detached worktree `/tmp/binance-continue-85351` remains at base `502ff79d6ba10205ebf80a525c46184c9aa36695`; source/test changes and this documentation checkpoint are local only. No commit or push has been made for this follow-up.
- Module 11 remains **PARTIAL**: this closes only the specific bounded sequential-action grammar gap, not general semantic entailment, arbitrary ellipsis, or full generated-post sentence-to-evidence verification. No provider call, media upload, real Square post, production DB write, workflow dispatch, credential/schedule change, merge or deployment occurred.

### Continuation checkpoint — 2026-11-16 (bounded compound-claim hardening; PARTIAL)

- Audited the latest Module 11 splitter/verification path and reproduced three additional single-field evidence bypasses: comma participial action (`ABC price rose 8%, falling 4%`), subordinate independent clause (`ABC price rose 8% as trading volume increased 2%`), and finite relative clause (`ABC price rose 8%, which was 4% higher than yesterday`). Before the fix, each was incorrectly `VERIFIED` by one `market.price` evidence record.
- Added TDD regressions; all three variants were observed failing before the fix. The bounded deterministic guard now rejects comma-led second-action participles from an explicit predicate allowlist, splits `as` only when the right side is a recognized independent subject/finite-verb clause, and detects comma-led `which + recognized finite predicate` relative clauses. Rejected claims remain `UNVERIFIED` with `COMPOUND_CLAIM_REQUIRES_ATOMIC_EVIDENCE`; no evidence is inferred or fabricated.
- Latest evidence-verification suite: **58 passed, 0 failed**. Combined evidence-verification, content-verification and DeepSeek-generator suite: **87 passed, 0 failed**. Full repository suite: **652 tests ran, 0 failed, 38 skipped**. The 38 skips are environment-guarded PostgreSQL tests requiring `TEST_POSTGRES_DSN`; they are not passes. `compileall` and `git diff --check` passed.
- Scope remains deliberately bounded and fail-closed. This does not provide general natural-language semantic entailment, causal inference, or coverage of every ambiguous/elliptical grammar form. Exact generated-post claim attribution remains an exact-match control, not semantic proof. Such unrecognized statements must remain unresolved; no unsupported claim may be upgraded based on model confidence.
- Module 11 therefore remains **PARTIAL / NOT COMPLETE** against the full semantic acceptance criterion. Do not represent this grammar hardening as a complete semantic verifier. No live provider request, production write, real Binance publication, workflow dispatch, merge or deployment occurred.

## Module 11 market-claim display binding guard — 2026-11-16 (local verification; PARTIAL)

- On clean detached worktree /tmp/binance-continue-85351 at exact PR #14 head 22391cbed66f6458bf33f8accd68837cdbee6b07, reproduced false verification when claim text contradicted the structured market claim: structured/evidenced market.price = 100 USD still verified prose “ABC price is 999 USD” and “ABC volume is 100 USD”. Added a wrong-currency case (“ABC price is 100 EUR”).
- TDD confirmed the first two regressions failed before implementation. Added bounded _claim_text_mismatch() validation for supported market keys. It checks metric identity, displayed numeric literals at the field's rendering precision, explicit uppercase unit/currency suffixes and currency symbols; ISO dates are excluded. A mismatch is recorded as CLAIM_TEXT_STRUCTURED_VALUE_MISMATCH:* and the claim remains UNVERIFIED.
- Focused evidence-verification: 59 passed. Combined evidence/content/research-package/DeepSeek-generator: 101 passed. Full repository: 653 tests, 0 failures, 38 skipped. All 38 skips are guarded PostgreSQL tests requiring TEST_POSTGRES_DSN, not passes. compileall and git diff --check passed.
- This closes only the bounded displayed market metric/value/unit binding gap. It is not general semantic entailment; negation, modal language, directional predicates, non-market prose/value alignment, and arbitrary paraphrase remain open. Module 11 remains PARTIAL / NOT COMPLETE.
- No live provider calls, media upload, real Binance Square post, production DB operation, workflow dispatch, credential/schedule/workflow change, merge or deployment occurred. Changes and docs are local only; no commit or push has been made.
## Module 11 announcement-text binding addendum — 2026-11-16 (supersedes previous local verification counts; PARTIAL)

- Reproduced a second text/evidence mismatch: arbitrary prose (“ABC listing confirmed for December 1”) was marked VERIFIED as SOURCE_ASSERTION when linked to an accepted announcement.body whose exact source text was different. The new regression failed before the fix.
- Announcement title/body claims now require SOURCE_ASSERTION type, exact linked source identity/value and either the canonical internal Source assertion text or exact Detail: <source value> text emitted by the package parser. Other text/paraphrases receive ANNOUNCEMENT_TEXT_EVIDENCE_MISMATCH and remain UNVERIFIED. Existing exact Detail and direct primary source assertion tests still pass.
- Final local test counts after both market and announcement binding guards: evidence-verification **60 passed**; combined evidence/content/research-package/DeepSeek-generator **102 passed**; full repository **654 tests, 0 failures, 38 skipped**. All 38 skips require TEST_POSTGRES_DSN and are not passes. compileall and git diff --check passed.
- Scope remains bounded deterministic binding, not general semantic entailment. Arbitrary non-market prose, negation, modality, directional claims and unrecognized paraphrases remain open; Module 11 stays PARTIAL / NOT COMPLETE. No live provider call, Binance media upload/post, production DB operation, workflow dispatch, credential/schedule change, merge or deployment occurred. No commit/push has been made.
## Module 11 structured source-assertion text binding — 2026-11-16 (latest local checkpoint; PARTIAL)

- TDD reproduced four false VERIFIED cases where linked evidence supported the structured value but not the displayed text: Binance Spot YES vs “Binance Spot: NO”; 2-hour publication history vs “Last posted: 12 hours ago”; event_type listing vs “Type: delisting”; freshness FRESH vs “Age: stale”.
- Extended the fail-closed text binder to accept canonical internal Source assertion text and exact known package templates for announcement event type/freshness, Binance Spot eligibility, publication last-posted status, trend topic digest/value and on-chain transfer-summary ID. Unknown source-assertion formats fail closed. Announcement title/body remain exact source-payload-only: canonical internal assertion or exact Detail: source value with matching linked evidence.
- Kept the existing exact “Binance announced a listing” event-type template because a package test relies on that explicit mapping. Evidence-verification: **61 passed**; combined evidence/content/research-package/DeepSeek-generator: **103 passed**; full repository: **655 tests, 0 failures, 38 skipped**. The 38 are TEST_POSTGRES_DSN-guarded PostgreSQL tests, not passes. compileall and git diff --check passed.
- This is structured text/value binding, not general semantic entailment. Arbitrary prose, negation, modality, directional predicates, free-prose asset-symbol mismatch and unrecognized paraphrases remain unresolved. Module 11 remains **PARTIAL / NOT COMPLETE**.
- Local-only change in /tmp/binance-continue-85351 at PR #14 base HEAD 22391cbed66f6458bf33f8accd68837cdbee6b07. Four files modified; no commit/push, merge, deployment, workflow dispatch, production write, live provider call, media upload or Binance post. Other worktrees preserved.

## Neon persistence branch audit — 2026-11-17 (read-only)

- Compared both databases (`binance_bot_staging`, `binance_onchain_test`) on the integration and disposable Neon branches. The integration branch lacks publication ledger tables in both databases; its `binance_onchain_test` has only Layer-1 ingestion tables and `layer1_schema_migrations`.
- The disposable branch contains publication attempts, authorizations, quota reservations, reconciliation events, and run persistence tables. Its `binance_onchain_test` additionally contains `layer1_run_lease`, `layer1_runs`, and schema migration ledger. Inspected key table columns, indexes, foreign keys and status checks read-only.
- This is test-schema evidence only, not production readiness. Do not point scheduled publishing at either disposable branch. Staging branch does not yet prove full publication-ledger schema coverage.
- GitHub Actions documentation-push runs 43907241840 and 43907254115 both completed SUCCESS.
- No Neon writes/config changes, secret changes, workflow dispatch, merge/deploy, publisher activation, or real post occurred. Keep DRY_RUN=1 and publisher disabled. Production requires a separately identified/provisioned database and explicit cutover approval.

## 2026-11-18 — Module 12 and Module 18/21 contract regressions fixed

- TDD RED on commit `49d4aaec913d49af01a4e5325eba995c2c161a5a`: GitHub Actions run `44217708860` ran 674 tests, 4 expected errors, 40 skipped. Failures reproduced the absent `ContentVerificationResult.evidence_status` contract and illegal non-material STALE/RESOLVED lifecycle transitions.
- GREEN on commit `2c45e6611779316b62be1721bfa83daf71ef4dd9`: GitHub Actions run `44217840412` SUCCESS; compileall passed; 674 tests, 0 failures, 40 skipped.
- Module 18/21: `ContentVerificationResult.evidence_status` is VERIFIED only for PASS with approved claim IDs; otherwise UNVERIFIED. `main.py` now sends this evidence status separately from text-validation PASS/REJECT.
- Module 12: SQLite and PostgreSQL adapters no longer try to transition a non-material verified revision directly from STALE or RESOLVED to CONFIRMED. Reopening remains restricted to materially new verified evidence through UNDER_VERIFICATION.
- PostgreSQL parity test cases are present but skipped in the hosted CI run because TEST_POSTGRES_DSN was not configured. Live PostgreSQL parity remains NOT VERIFIED.
- No production side effects or publisher activation.

## 2026-11-18 — Independent default-off publication kill switch

- Added `PUBLISHER_ENABLED` as a strict boolean environment setting, default false.
- Live mode requires both `DRY_RUN=false` and explicit `PUBLISHER_ENABLED=true`, while retaining provider-credential and PostgreSQL durability checks.
- Publisher network submission and Binance media upload each enforce the switch independently; the main runtime fingerprints the setting.
- TDD coverage added for default-off, config validation, publisher refusal and media-upload refusal. The final CI run `44218585027` passed: compileall + 678 tests, 0 failures, 40 skipped.
- The 40 skips include PostgreSQL integration tests without TEST_POSTGRES_DSN. No live provider/media/publishing test was run.
- Scheduled workflow remains DRY_RUN=1 and publisher disabled. No production side effects.

## 2026-11-18 — Persisted publication duplicate policy enforced

- Removed the caller-supplied duplicate-policy boolean from both SQLite and PostgreSQL authorization interfaces. The authorization engines now derive the pass result from persisted records.
- Checks recent same-symbol posts (configured hard cooldown), exact duplicate content, unresolved SUBMITTING/PUBLICATION_UNKNOWN attempts, and competing active same-symbol quota reservations.
- Exceptional cooldown bypass is based on persisted event type and persisted CONFIRMED/DEVELOPING lifecycle only. It does not bypass unresolved attempts, exact duplicates or competing reservations.
- SQLite checks are re-run before attempt reservation and immediately before HTTP POST. PostgreSQL uses symbol-scoped advisory transaction locks and repeats the check inside the durable pre-submit transaction.
- Test-first red run reproduced missing caller-independent policy; follow-up CI run `44219811233` passed: compileall + 683 tests, 0 failures, 40 skipped.
- The 40 skips include live PostgreSQL tests requiring TEST_POSTGRES_DSN. PostgreSQL duplicate-policy integration test exists but remains unexecuted in this CI run.
- No production publication or other external side effects.



## 2026-11-18 — Module 21 PostgreSQL pre-submit failure-state correction

- TDD reproduced that a PostgreSQL pre-submit validation/duplicate-ledger exception was incorrectly classified as `PUBLICATION_UNKNOWN` even though the HTTP request had not been sent.
- The publisher now isolates the preflight from the network call. A preflight exception records `FAILED_CONFIRMED` and returns without invoking the Binance transport. Only exceptions after entering the network submission path retain `PUBLICATION_UNKNOWN` semantics.
- RED run: GitHub Actions `44220146035`, 684 tests, 1 failure, 40 PostgreSQL tests skipped. GREEN run: `44220220216`, **684 tests, 0 failures, 40 skipped**; compileall passed.
- The PostgreSQL query failure remains fail-closed (exception prevents POST). The new regression uses a deterministic mocked store; it is not a substitute for live PostgreSQL integration.
- Module 21 remains **PARTIAL / NOT COMPLETE** until the guarded PostgreSQL authorization/duplicate/recovery tests execute against the approved disposable test database and crash/restart/unknown-outcome recovery is accepted. No production DB or real publisher activity was used.



## 2026-11-18 — Module 21 explicit interrupted-run recovery

- Added explicit operator-only recovery to SQLite and PostgreSQL run-lease stores. No age-based lease stealing or automatic replay is introduced.
- Recovery requires the exact active run ID, affirmative process-termination confirmation, operator evidence and operator identity. It atomically marks the prior run `INTERRUPTED`, stores the recovery evidence in the run summary and deletes only the matching lease. A mismatched ID or inconsistent run state fails closed.
- PostgreSQL lease acquire, finish and recovery share the same advisory transaction lock/lock order to avoid racing normal completion against operator recovery.
- SQLite/adapter regression tests pass. A PostgreSQL integration regression was added but remains guarded by `TEST_POSTGRES_DSN`.
- CI run `44220831869`: **687 tests, 0 failures, 41 skipped**; compile passed. The 41 skips include the PostgreSQL integration suite and are not accepted as PostgreSQL passes.
- This closes the code-level manual run-lease recovery gap only. Module 21 remains **PARTIAL / NOT COMPLETE** pending disposable-branch PostgreSQL acceptance, unknown publication reconciliation, quota/crash recovery end-to-end and operational verification.



## 2026-11-18 — Module 21 confirmed-post persistence and run-lease owner guards

- Fixed a post-acceptance state bug: after PostgreSQL durably records `PUBLISHED_CONFIRMED`, a failure writing the secondary local JSONL/history file no longer downgrades the returned result to `PUBLICATION_UNKNOWN`. PostgreSQL remains authoritative; the local history failure is logged without exception text.
- TDD regression failed RED on `4b2e61a97fcfa53ba717b4edc56c7be51b7125e3`; fix passed in the latest suite.
- PostgreSQL run-lease adapter now refuses recovery when the current adapter instance owns that same run ID. This complements the SQLite owner guard and exact-ID/operator-confirmation checks.
- GitHub Actions run `44221215550`: **688 tests, 0 failures, 41 skipped**; compile passed. The PostgreSQL integration cases, including the new recovery regression, remain skipped without `TEST_POSTGRES_DSN`.
- Module 21 remains **PARTIAL / NOT COMPLETE** pending real disposable-branch PostgreSQL acceptance, unknown-publication reconciliation and full crash/restart recovery validation. No real Square post, production DB write or publisher activation.



## 2026-11-18 — Module 21 post-confirmation state consistency

- Both SQLite and PostgreSQL publisher paths now treat local Markdown/JSONL history as secondary after the authoritative ledger records `PUBLISHED_CONFIRMED`. A local file failure no longer changes the confirmed result to `PUBLICATION_UNKNOWN`.
- SQLite quota finalization failure after confirmed publication no longer downgrades the attempt/result. The reservation remains `PUBLICATION_UNKNOWN` (active, conservative) and emits an operator-review critical log; it is not released. This inconsistency requires operator reconciliation and is not claimed as fully automated.
- TDD regression for SQLite local history and quota finalization is green. Latest CI `44221784199`: **690 tests, 0 failures, 41 skipped**, compile passed.
- PostgreSQL integration tests remain skipped without the approved test DSN. Module 21 remains **PARTIAL / NOT COMPLETE** pending direct disposable PostgreSQL acceptance, quota-state reconciliation, unknown-publication recovery and end-to-end crash/restart verification.



## 2026-11-18 — SQLite quota finalization fail-safe

- SQLite publisher now preserves `PUBLISHED_CONFIRMED` after remote acceptance even if the separate quota finalization update fails. The reservation remains `PUBLICATION_UNKNOWN` and active for operator review; it is never released automatically. The confirmed attempt and return status are not downgraded.
- Regression CI `44221784199`: **690 tests, 0 failures, 41 skipped**; compile passed. A first test expectation was corrected to the actual conservative state: the reservation had already been marked `PUBLICATION_UNKNOWN` immediately after the remote acceptance response.
- PostgreSQL integration acceptance remains skipped without the approved disposable DSN. Module 21 remains **PARTIAL / NOT COMPLETE**.



## 2026-11-18 — DeepSeek and Cloudflare model ID documentation verification

- Official DeepSeek model-list docs currently list `deepseek-flash` and `deepseek-v4-pro`; the configured `deepseek-flash` identifier is valid. Source: https://api-docs.deepseek.com/api/list-models/
- Official Cloudflare Workers AI docs confirm `@cf/black-forest-labs/flux-2-klein-4b`, multipart form-data input, and fixed four-step inference. The current image client uses the documented multipart path and does not send a configurable step count. Source: https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/
- No live authenticated DeepSeek/Cloudflare request was run. Provider runtime acceptance remains pending; image inference has published usage pricing, so do not assume it is free or run it without explicit cost approval.



## 2026-11-18 — SQLite final pre-submit ledger failure correction

- The final SQLite event/provenance and persisted duplicate-policy checks now execute inside a dedicated pre-submit exception boundary. A database/ledger exception before transport is a known `FAILED_CONFIRMED` no-submit result, not `PUBLICATION_UNKNOWN`; no Binance HTTP call is made.
- The attempt and quota are finalized as `FAILED_CONFIRMED` when possible. If ledger finalization itself fails, remaining `SUBMITTING`/`PUBLICATION_UNKNOWN` fences are retained and critical sanitized logs are emitted; reservations are never released in an uncertain state.
- TDD/CI run `44222425776`: **691 tests, 0 failures, 41 skipped**, compile passed. The 41 PostgreSQL integration skips remain unverified.



## 2026-11-18 — Atomic SQLite publication/quota state transition

- SQLite `PostPublisher._finish_attempt` now updates the publication attempt and its linked quota reservation in a single transaction. Attempt transitions are constrained; terminal states cannot be downgraded.
- Removed separate final quota writes that could fail after the attempt had already been confirmed. The linked reservation is now updated to the same terminal/unknown state atomically. Pre-submit reservation transitions remain separate.
- This supersedes the earlier temporary fail-safe that left a quota reservation `PUBLICATION_UNKNOWN` after the attempt became `PUBLISHED_CONFIRMED`.
- CI run `44223021885`: **691 tests, 0 failures, 41 skipped**; compile passed. PostgreSQL integration acceptance remains skipped pending approved disposable DSN.



## 2026-11-18 — PostgreSQL duplicate-ledger query failure regression

- Added a non-DSN unit test that injects a query failure inside the PostgreSQL duplicate-policy transaction and verifies the exception propagates. This proves the store does not fail open when the duplicate ledger is unavailable.
- The pre-submit publisher catches the propagated error before transport and records a known no-submit failure; no Binance request is sent.
- CI run `44223361236`: **692 tests, 0 failures, 41 skipped**; compile passed. The 41 guarded PostgreSQL integration tests remain unverified.



## 2026-11-18 — Module 19 image artifact format consistency

- Workers AI image generation now requires decoded bytes to match the requested file extension (PNG/JPEG/WEBP). Previously valid image bytes could be written under a different extension, creating a misleading artifact.
- Added a regression; RED run `44223544726`, GREEN run `44223645854`: **693 tests, 0 failures, 41 skipped**, compile passed.
- This is mocked response/decoder verification only; authenticated Cloudflare generation and Binance media upload remain unverified.



## 2026-11-18 — Module 20 final image extension validation

- Final visual QA now requires both PNG-decoded image content and a `.png` filename. This prevents a PNG payload stored as `.jpg` from passing the final artifact gate.
- TDD regression RED `44223868599`; GREEN `44223962776`: **694 tests, 0 failures, 41 skipped**, compile passed.
- Live Cloudflare generation and Binance media upload remain unverified; PostgreSQL integration tests remain skipped pending approved test DSN.



## 2026-11-18 — Module 13 foreign-asset research isolation

- Fixed a cross-asset contamination defect in `DeepResearchEngine`: claims without an explicit `asset_id` must now have `subject == selected asset_id`; explicitly bound claims must match the selected asset.
- Unbound evidence explicitly naming a different canonical CoinGecko asset is excluded. Source coverage counts only cutoff-eligible evidence linked to selected-asset claims.
- TDD RED `44224206173`; GREEN `44224293433`: **696 tests, 0 failures, 41 skipped**, compile passed. PostgreSQL integration acceptance remains pending.



## 2026-11-18 — Module 13 canonical subject and asset-ID cross-check

- Hardened research package isolation beyond optional asset IDs: if a claim/evidence subject explicitly names a canonical CoinGecko asset different from the selected package asset, it is rejected even when its `asset_id` field is incorrectly set to the selected asset.
- This closes a malformed claim/evidence pair that could pass the lower-level verifier's exact subject/asset field equality while semantically naming another canonical asset.
- TDD RED `44224711294`; GREEN `44224786514`: **696 tests, 0 failures, 41 skipped**, compile passed. PostgreSQL integration acceptance remains pending.


## 2026-11-18 — Module 11 market-claim polarity and uncertainty guard

- TDD reproduced false-positive verification cases in which structured market evidence for a positive change could be paired with text saying “down”, and market assertions containing negation or modal/uncertain language could still become `VERIFIED`. The new regressions failed before the implementation.
- `EvidenceVerificationEngine._claim_text_mismatch()` now checks directional language against the signed value for `market.price_change` and `market.change_24h`. Unsigned magnitudes inherit a clear direction word; explicit signs that contradict the word fail closed. Conflicting positive/negative language is rejected. Neutral language such as “flat” or “unchanged” is accepted only for a zero value.
- Market claim text containing negation (for example, “not 100 USD”) or modal/uncertain language (for example, “may be 100 USD”, “could rise”) is no longer accepted as a confirmed market fact. It returns a structured text mismatch and remains unverified.
- RED was observed for both regression groups; GREEN focused verification passed. Final local validation on the isolated worktree: `compileall` passed; full suite **698 tests, 0 failures, 41 skipped**; `git diff --check` passed. The 41 skips are PostgreSQL integration tests guarded by missing `TEST_POSTGRES_DSN`; they are not accepted as passes.
- Scope is deliberately bounded deterministic text/value consistency. It does not implement general semantic entailment, all natural-language paraphrases, ambiguous elliptical claim splitting or full semantic attribution. Module 11 remains **PARTIAL**; no LLM confidence is treated as evidence.
- Module 14 remains fail-closed pending an owner-approved, evidence-backed opportunity scoring policy and calibrated factor definitions. No policy weights or thresholds were invented.
- Work was performed in a new isolated worktree from PR #14 head `b399a6feaa03bceb6ce5dda48e84d4b35889e25f`; existing `/root/Binance-bot` checkout and its three pre-existing announcement-worker modifications were left untouched. Changes are local and uncommitted/unpushed.
- No PostgreSQL test DSN was loaded, no database was written, no live DeepSeek/Cloudflare request was made, no Binance media upload/post occurred, and no publisher, production workflow, credential, deployment, merge or schedule was changed.

## 2026-11-18 — Module 11 semicolon boundary hardening

- Found a deterministic segmentation gap: `split_atomic_claims()` split semicolon-delimited claims only when whitespace followed the semicolon. A compact but valid input such as `BTC price is $100;ETH volume is $5m` remained one compound claim.
- Added a regression test first; it failed RED with the two clauses incorrectly returned as one. Updated the splitter to treat a semicolon as a clause boundary whether or not whitespace follows it. Existing semicolon/sentence regression and the new no-whitespace case pass.
- Focused Module 11 suite: **64 tests, 0 failures**. Full isolated repository suite: **699 tests, 0 failures, 41 skipped**. `compileall` and `git diff --check` passed before documentation update; PostgreSQL tests remain skipped because `TEST_POSTGRES_DSN` is not configured.
- This is a narrow punctuation-boundary fix, not general semantic entailment. Ambiguous elliptical claims, paraphrase entailment and full natural-language semantic attribution remain unsupported; Module 11 remains **PARTIAL**.
- Changes were pushed from the isolated worktree `/tmp/binance-w2e-continuation` to the existing PR #14 continuation branch in commit `7e8cc99`; remote file content was verified. No production database, live provider, Cloudflare inference, publisher, Binance post, deployment, merge or original `/root/Binance-bot` checkout was touched.

## 2026-11-18 — Module 11 possessive-asset clause segmentation

- Added a TDD regression for compound market prose using possessive asset subjects, e.g. `Bitcoin's price rose 8% and Ethereum's price fell 4%`. The pre-fix splitter returned the entire sentence as one claim, allowing one structured market-field link to appear to cover two assets/propositions.
- Extended the bounded independent-clause subject grammar to recognize possessive asset names and lowercase descriptor words after an explicitly capitalized entity token. Kept the entity-leading token case-sensitive to avoid treating ordinary lowercase adverbs such as `later` as asset names.
- Added a verifier-level regression proving a possessive multi-asset sentence remains `UNVERIFIED` with `COMPOUND_CLAIM_REQUIRES_ATOMIC_EVIDENCE` when only one market evidence link is supplied.
- Module 11 focused suite: **65 tests, 0 failures**. Full local suite: **701 tests, 0 failures, 41 skipped**. The 41 skips are PostgreSQL integration tests guarded by absent `TEST_POSTGRES_DSN`; they are not accepted as passes. No production or external provider actions were used.
- Scope remains deterministic clause segmentation and evidence-link protection, not general semantic entailment, broad paraphrase understanding, or full natural-language attribution. Module 11 remains **PARTIAL / NOT COMPLETE**.
- Current edits are local and uncommitted in `/tmp/binance-w2e-continuation`; no push was made in this continuation. Existing PR #14 and the remote branch remain unchanged by this local edit. Original `/root/Binance-bot` checkout remains untouched.

## 2026-11-18 — Module 14 policy source check and PostgreSQL test gate

- Read `SCORING_POLICY.md`: it documents **Module 7 Relevance Scoring Policy**, not the Module 14 opportunity scoring policy. It explicitly says its audience-relevance/novelty definitions and materiality/credibility baselines need approval/calibration. It does not supply an owner-approved Module 14 policy or validated Module 14 factor inputs. Module 14 must remain fail-closed; do not repurpose Module 7 weights as Module 14 weights.
- Active continuation worktree check confirms `TEST_POSTGRES_DSN` is absent. Existing project notes identify a disposable Neon test branch and a prior DSN file in a different worktree, but credentials must not be copied or retrieved from that location. No database test was attempted with a guessed or production DSN. Module 21 PostgreSQL integration remains unverified until an approved disposable DSN/host allowlist is supplied through the active test environment.


## 2026-11-18 — Module 11 negated auxiliary clause segmentation

- TDD found a deterministic split gap: `Bitcoin's price rose 8% and Ethereum's price did not change.` was retained as one claim because the finite-verb grammar did not recognize the auxiliary `did`.
- Added a regression first and observed RED. Extended the bounded finite-verb vocabulary to recognize `do` / `does` / `did` and `change` / `changes` / `changed`; the independent second clause is now separated while its negation remains intact.
- Focused evidence-verification suite: **67 tests, 0 failures**. `compileall` and `git diff --check` passed. Full repository suite: **702 tests, 0 failures, 41 skipped**. The 41 skips are PostgreSQL integration tests gated by absent `TEST_POSTGRES_DSN`; they are not passes.
- This is deterministic segmentation only. It does not infer semantic truth or implement general semantic entailment; Module 11 remains **PARTIAL / NOT COMPLETE**.
- Work remains local and unpushed in `/tmp/binance-w2e-continuation`; the original checkout is untouched. No DB/provider/Cloudflare/media-upload/publishing/deployment/merge actions occurred.


## 2026-11-18 — Authoritative continuation state after Module 11 negated auxiliary fix

- Current PR #14 remains OPEN / DRAFT / UNMERGED. Head branch: `layer-1/module9-onchain-continuation`; base: `layer-1/module9-onchain-intelligence`.
- Latest pushed head: `978f04d9cd236091b5e35b9e18367f1c6035a228`; exact remote branch SHA verified with `git ls-remote`. The isolated worktree `/tmp/binance-w2e-continuation` was clean immediately after push.
- Local verification on that exact commit: full suite **702 tests, 0 failures, 41 skipped**; focused Module 11 evidence-verification suite **67 tests, 0 failures**; `compileall` and `git diff --check` passed.
- The 41 skipped tests are guarded PostgreSQL integration tests requiring `TEST_POSTGRES_DSN`; they are not passes. GitHub workflow-runs and combined-status queries for this exact head returned no entries, so latest-head hosted CI is **NOT VERIFIED**.
- Module 11 latest fix adds `do` / `does` / `did` and `change` / `changes` / `changed` to the bounded independent-clause grammar. Negation in `Bitcoin's price rose 8% and Ethereum's price did not change.` is preserved. Module 11 remains PARTIAL; no general semantic entailment claim is made.
- Module 14 remains fail-closed pending owner-approved evidence-backed scoring policy and calibrated factors. Module 21 remains PARTIAL pending approved disposable PostgreSQL acceptance and crash/restart, quota, and unknown-publication reconciliation evidence. Live DeepSeek/Cloudflare and Binance authenticated media-upload acceptance remain unverified.
- No real Binance post, media upload, publisher activation, production DB write, credential/schedule change, workflow dispatch, merge, or deployment occurred. `DRY_RUN=1`; `PUBLISHER_ENABLED` remains default-off.
- This entry supersedes older status notes that described commit `978f04d` as local/unpushed or said its push was not authorized. Those statements are historical and no longer current.


## 2026-11-18 — GitHub push credential persistence defect fixed

- Source audit found `_try_git_push()` was rewriting the `origin` remote to `https://x-access-token:<token>@github.com/...`. On a persistent checkout this could leave the GitHub token stored in `.git/config`.
- Removed the token-bearing remote URL mutation. Authentication is now passed to the `git push` subprocess using process-scoped Git HTTP extra-header configuration (`GIT_CONFIG_COUNT` and indexed key/value environment variables). Existing transient Git config entries are preserved; the token is not placed in command arguments or the remote URL. Existing branch-target selection and scheduled workflow were not changed.
- TDD regression failed against the old implementation because it called `git remote set-url`; after the fix, both focused security tests pass, including missing-token no-op behavior.
- Full local repository suite after the fix: **704 tests, 0 failures, 41 skipped**. `compileall` and `git diff --check` passed. The 41 skips remain PostgreSQL integration tests gated by missing `TEST_POSTGRES_DSN`, not passes.
- Code commit `626ec8fe69cbc824dc12271d0bb1fa4b210219d2` was pushed to the existing PR #14 branch and its exact remote SHA was verified. No deployment, merge, production DB operation, publisher activation or live Binance post occurred.


## 2026-11-18 — Lowercase possessive asset clause segmentation

- TDD reproduced that `bitcoin's price rose 8% and ethereum's price fell 4%.` remained a single compound claim. The bounded subject grammar had required uppercase initial characters for possessive asset names.
- Added a constrained lowercase possessive subject alternative only when followed by explicit market descriptors (`price`, `volume`, `market cap`). Added coverage for two distinct lowercase asset subjects and a lowercase shared-subject continuation.
- Focused Module 11 evidence-verification suite: **68 tests, 0 failures**. Full repository suite: **705 tests, 0 failures, 41 skipped**; `compileall` and `git diff --check` passed. The 41 PostgreSQL integration skips remain unexecuted without `TEST_POSTGRES_DSN`.
- Code commit `08ecde578f58abcabdaae676838410e5d46ce4ad` was pushed to the existing PR #14 branch and the exact remote SHA was verified. Module 11 remains PARTIAL; no semantic-entailment claim is made.


## 2026-11-18 — Module 15 invalid DeepSeek candidate selection correction

- Code audit found the review path silently selected `research_packages[0]` when DeepSeek's top-ranked symbol did not match any supplied candidate. This could publish a different asset than the model selected.
- Added exact candidate-set resolution. Unknown/malformed top-ranked symbols and duplicate/ambiguous candidate symbols now fail closed; the runtime stops the cycle instead of substituting the first package. Case-insensitive exact symbol matching is retained.
- TDD focused suite: initial run failed because the resolver was absent; after implementation `tests.test_deepseek_generator` passed **20/20**. Full repository suite: **708 tests, 0 failures, 41 skipped**. PostgreSQL integration tests remain skipped without `TEST_POSTGRES_DSN`.
- Module 15 remains PARTIAL: structured ranking completeness/uniqueness/candidate membership validation beyond the selected top symbol, live current-head DeepSeek acceptance, and durable model request/usage/latency audit are still not fully accepted. No live provider request or publisher action occurred.


## 2026-11-18 — Module 15 strict Phase 1 ranking parser

- Replaced permissive parsing with a bounded fail-closed contract: 1–3 records; contiguous ranks starting at 1; unique alphanumeric tickers; required non-empty reasons; no extra prose or malformed fields. Duplicate ranks/symbols, rank gaps/zero, malformed tickers and empty reasons now reject the entire model response.
- The separate runtime candidate resolver also rejects unknown and ambiguous top-ranked symbols rather than substituting the first research package.
- TDD: 7 malformed-response subcases failed against the old parser. Focused Module 15 suite after fixes: **24 passed**. Full suite: **712 tests, 0 failures, 41 skipped**. PostgreSQL integration tests remain unexecuted without `TEST_POSTGRES_DSN`.
- Module 15 remains PARTIAL pending candidate-set validation for every returned rank, current-head live DeepSeek acceptance, and complete durable provider request/usage/latency audit.


## 2026-11-18 — Module 15 all-ranked-candidate membership check

- Candidate resolution now validates every rank against the supplied research packages, not only the top rank. Each symbol must resolve exactly once; duplicate/ambiguous candidate symbols, unknown secondary ranks, malformed ranking fields, and invalid rank sequences fail closed.
- TDD regression: valid top-ranked symbol plus unknown secondary symbol failed before the fix and passes after. Focused Module 15 suite: **25 passed**. Full repository suite: **713 tests, 0 failures, 41 skipped**. `compileall` and `git diff --check` passed.
- Module 15 remains PARTIAL pending live DeepSeek acceptance and durable provider audit; no inference request was made.


## 2026-11-18 — Module 16 editorial brief delimiter-injection defect

- TDD reproduced a control-record injection in `EditorialBrief.render()`: untrusted prohibited-claim text could inject nested editorial delimiters and forged `READY`/brief-ID/claim-ID fields. The actual brief was `REJECT`, but `DeepSeekGenerator._editorial_brief_allows()` selected the forged nested block and returned true.
- Renderer now sanitizes every free-text brief field to one line and neutralizes `<<<` / `>>>` structural markers. The regression proves the same rejected brief no longer passes the gate.
- RED observed before fix; focused Editorial Strategy + DeepSeek tests **44/44 passed** after fix; full suite **714 passed, 0 failed, 41 skipped**. PostgreSQL integration remains unexecuted without `TEST_POSTGRES_DSN`.
- Module 16 remains PARTIAL: this closes one serialization/gate-injection defect, not general LLM prompt-injection risk or live DeepSeek acceptance.


## 2026-11-18 — Module 13 research package delimiter-injection defect

- TDD reproduced a fail-open research gate: an unresolved claim containing newlines, nested research-package delimiters and forged `READY`/package-ID fields caused `_research_package_allows()` to accept a real `RESEARCH_MORE` package because the parser selected the last matching block.
- `ResearchPackage.render()` now sanitizes free-text research question, claim text and gap fields to one line and neutralizes structural `<<<` / `>>>` delimiters. The same incomplete package is now rejected by the gate.
- RED reproduced before fix. Focused Module 13 + 16 + DeepSeek tests: **60 passed**. Full suite: **716 passed, 0 failed, 41 skipped**. PostgreSQL integration remains unexecuted without `TEST_POSTGRES_DSN`.
- Module 13 and 16 remain PARTIAL. These fixes close two deterministic delimiter-injection paths only; general prompt-injection resistance and live provider acceptance remain unverified.

## 2026-11-18 — Module 20 visual validator decompression-bomb handling
- **Finding:** `VisualQualityEngine.validate()` caught only `OSError` and `ValueError` around Pillow decoding. Pillow's `Image.DecompressionBombError` and `Image.DecompressionBombWarning` (when warnings are configured as errors) escaped and could crash the validation path rather than fail closed.
- **Evidence:** Added two TDD regressions. Both reproduced RED before implementation: one forced `DecompressionBombError` with a tiny image and low `Image.MAX_IMAGE_PIXELS`; the other promoted `DecompressionBombWarning` to an exception and reproduced an uncaught exception.
- **Fix:** Catch the two explicit Pillow decompression-bomb classes and return the existing `IMAGE_MISSING_OR_UNDECODABLE` rejection reason. No broad exception suppression.
- **Verification:** `tests.test_visual_quality` — 13 passed, 0 failed. Full repository `unittest discover -s tests -v` exited 0; aggregate count not recorded from the truncated tool output. PostgreSQL integration tests remain skipped without `TEST_POSTGRES_DSN`.
- **Status:** Defect fixed locally; not committed or pushed. Module 20 remains PARTIAL for independent semantic/OCR verification of generated image backgrounds.

## 2026-11-18 — Publication authorization NO_EVENT downgrade bypass
- **Finding:** SQLite and PostgreSQL authorization paths skipped lifecycle lookup whenever the caller supplied `event_state="NO_EVENT"`, even though the immutable editorial brief still referenced a concrete `event_id`. A caller could downgrade an existing WITHDRAWN/STALE event to NO_EVENT and bypass event-state gating.
- **RED evidence:** Added a regression that seeded a WITHDRAWN lifecycle record and requested authorization with NO_EVENT. Before the fix, authorization succeeded.
- **Fix:** SQLite duplicate-policy and persisted-event revalidation now always query the exact event ID; NO_EVENT is valid only when that event has no lifecycle row. Applied the same invariant to PostgreSQL duplicate-policy checks, authorization persistence, immediate pre-submit revalidation, and the PostgreSQL runtime adapter. Missing lifecycle schema remains fail-closed.
- **Verification:** `tests.test_publication_authorization`, `tests.test_publication_runtime`, and `tests.test_publication_postgres`: 69 tests, 0 failures, 20 skipped. PostgreSQL integration skips remain unverified without the approved disposable DSN.
- **Status:** Local fix and unit/contract coverage complete; not committed or pushed. Module 21 remains PARTIAL pending approved live PostgreSQL integration and crash/restart/reconciliation acceptance.

## 2026-11-18 — Final regression verification checkpoint
- The test fixtures in `tests/test_publisher_safety.py` were updated to model the existing `layer1_event_lifecycle` table even for the NO_EVENT case. This preserves the runtime fail-closed contract while representing an empty lifecycle ledger accurately.
- Focused publisher-safety suite: 35 passed, 0 failed. Focused publication authorization/runtime/PostgreSQL contract suite: 69 run, 0 failed, 20 skipped. Visual-quality suite: 13 passed, 0 failed.
- Full repository suite: **721 run, 0 failed, 41 skipped**. All 41 skips are PostgreSQL integration tests requiring the absent `TEST_POSTGRES_DSN`.


## 2026-11-18 — Module 19/21 authorized media byte-identity TOCTOU fix (local, uncommitted)

- Audit finding: `upload_authorized_image()` validated the immutable authorization against the caller-provided image hash list, but did not hash the actual bytes at `image_path`. A replaced image file could be uploaded under authorization for a different image.
- TDD RED reproduced the bypass: `test_media_upload_rejects_file_replaced_after_authorization_hashing` failed because the old implementation called the uploader without reading or hashing the file.
- Fix: the upload boundary now requires exactly one digest for its single-image operation, hashes the file bytes and rejects missing/mismatched files before any upload callback. It writes the verified bytes to a private temporary snapshot and uploads that snapshot, closing the path-replacement race between verification and the uploader's file read.
- Regression coverage proves pre-upload mismatch rejection, snapshot byte stability if the original source path changes during upload, and continued Binance CDN URL allowlisting.
- Focused result: `tests.test_cloudflare_image_generation` — 22 passed, 0 failed. `git diff --check` passed.
- Local-only and uncommitted. No provider call or media upload occurred. Module 19/20/21 remain PARTIAL; live media acceptance, PostgreSQL integration, crash/restart, quota recovery and unknown-publication reconciliation remain outstanding.


## 2026-11-18 — Module 20 bounded image read and validation snapshot (local, uncommitted)

- Audit finding: `VisualQualityEngine.validate()` read the entire image into memory before checking the 10 MiB limit.
- TDD RED reproduced the unbounded read on a sparse file larger than 10 MiB.
- Fix: bounded read of at most 10 MiB + 1 byte; reject out-of-bounds input before decoding; hash and decode the same in-memory snapshot to avoid path replacement between digest and image inspection.
- Focused result: `tests.test_visual_quality` — 14 passed, 0 failed. Media-upload snapshot regression suite: 22 passed, 0 failed.
- Local-only/uncommitted. No provider call or upload. Module 20 remains PARTIAL pending independent semantic/OCR verification and broader generated-media acceptance.


## 2026-11-18 — Module 21 PostgreSQL daily-quota union accounting (local, uncommitted)

- Defect: `max(reservation_count, analytics_count)` could undercount disjoint legacy analytics and active reservations, allowing the daily limit to be exceeded.
- Fix: count active durable reservations plus analytics rows that are not linked by `remote_post_id` to a durable publication attempt. Added strict non-negative integer count validation.
- TDD unit contract passes. Added a PostgreSQL integration regression for 7 legacy analytics + 1 active reservation against a limit of 8; it is skipped without the approved `TEST_POSTGRES_DSN` and remains unverified against a real database.
- No production database access. Module 21 remains PARTIAL pending live disposable-PostgreSQL acceptance, transaction/concurrency testing and crash/restart recovery.


## 2026-11-18 — Module 19 upload-boundary bounded read (local, uncommitted)

- Follow-up audit bounded the media upload digest read to 10 MiB + 1 byte. Oversized replacement files are rejected before hashing or upload, preventing an unbounded allocation at the second (upload) boundary.
- TDD RED reproduced the old behavior; focused image + visual suites: 37 passed, 0 failed. Local-only; no upload occurred.


## 2026-11-18 — Combined regression checkpoint after Modules 19–21 audit fixes

- Full suite: **727 passed, 0 failed, 42 skipped**. The new PostgreSQL quota integration regression is skipped without `TEST_POSTGRES_DSN`; live DB behavior remains unverified.
- `compileall` and `git diff --check`: PASS.
- Branch/HEAD/remote SHA unchanged: `work/module9-continuation-local` / `78631ecc72470d445507b4110891aa8110738256`; PR #14 head ref still matches.
- 19 modified tracked files, 869 insertions / 152 deletions. No commit or push. Continue remaining audit; do not mark Modules 17–21 or project complete.


## 2026-11-18 — Module 21 publication identity finalization hardening (local, uncommitted)

- PostgreSQL finalization previously permitted `PUBLISHED_CONFIRMED` without a remote ID and same-state updates could replace a recorded remote ID/share link. `PUBLICATION_UNKNOWN` identity was also mutable. Operator reconciliation store calls lacked the CLI's URL/ID format validation.
- Added shared `validate_attempt_completion()` and applied it to both finalization methods and reconciliation. Published requires a valid ID; failed cannot carry an ID/link; unknown can carry a validated ID and matching Binance Square link; IDs/links are immutable once recorded.
- TDD unit contract: 2 passed. PostgreSQL integration regression added but skipped without approved `TEST_POSTGRES_DSN`.

## 2026-11-18 — Module 19 Cloudflare response bounded read (local, uncommitted)

- Provider inference response was read without a size bound before its 20 MiB validation. TDD regression observed unbounded `read(-1)`.
- Changed to read at most 20 MiB + 1 byte and reject oversized response before decoding/writing.
- Focused Cloudflare + publication identity tests: 26 passed, 0 failed. No live provider call. Module 19 remains PARTIAL.


## 2026-11-18 — Module 19/21 transport response and upload bounds (local, uncommitted)

- Bounded Cloudflare inference response reads to 20 MiB + 1 byte; Binance media presigned/status JSON responses to 1 MiB + 1 byte; presigned image file reads to 10 MiB + 1 byte. Oversize is rejected before decode/upload.
- Bounded Binance publication API response reads to 1 MiB + 1 byte. Overflow after submission is classified `PUBLICATION_UNKNOWN` and remains non-retryable.
- Regression coverage includes oversize provider response read size, oversize presigned upload rejected before network, and oversized publication response leaving a durable unresolved attempt without a second POST.
- Full suite: **734 passed, 0 failed, 43 skipped**. Compileall and diff check passed. PostgreSQL integration remains skipped without approved disposable DSN.


## 2026-11-18 — Module 21 authorization-to-submit TOCTOU fence (local, uncommitted)

- Fixed the gap where pre-submit authorization locks were released before the HTTP POST. `authorized_submission_guard()` now retains the outer transaction, symbol + event advisory locks, provenance row locks, validation advisory locks, attempt and quota locks through the bounded request. This also prevents a `NO_EVENT` lifecycle row from being inserted between validation and submission.
- Added shared per-draft text and per-draft/image validation advisory locks. Validation writers acquire them before appending; authorization and pre-submit readers acquire them before reading latest validation rows, preventing a new REJECT/NEEDS_REVISION record racing past authorization.
- PostgreSQL publisher now sends the request only inside the guard. Preflight failure is known not-submitted; errors after request start remain UNKNOWN and fenced.
- Lock order is consistent: symbol -> event -> sorted validation scopes -> dependent row/quota locks.
- Focused guard/publisher/identity tests: 7 passed. Live PostgreSQL concurrency acceptance remains unverified without the approved disposable test DSN. Module 21 remains PARTIAL.


## 2026-11-18 — Latest continuation verification checkpoint

- Full local suite: **736 passed, 0 failed, 43 skipped**. PostgreSQL integration skips remain unverified due missing approved `TEST_POSTGRES_DSN`.
- `compileall` and `git diff --check`: PASS.
- 19 modified tracked files; diff **+1,390 / -191**. No commit/push. Local branch/HEAD and PR #14 remote head remain aligned at `78631ecc72470d445507b4110891aa8110738256`.
- PR #14 still OPEN / DRAFT / UNMERGED. No hosted workflow runs or combined statuses found; hosted CI not verified.
- Modules 17–21 and overall project remain PARTIAL. No production action performed.


## 2026-11-18 — Module 20 visual provenance sidecar size bound (local, uncommitted)

- Gap found: visual QA parsed provenance JSON via an unbounded `read_text()` call. A malformed or tampered sidecar could consume unbounded memory before its content was checked.
- RED test proved the issue: a valid sidecar carrying a metadata field larger than 1 MiB was accepted as PASS.
- Fix: cap sidecar read to 1 MiB + 1 byte; reject empty/oversized content before decode/parse; fail closed for invalid UTF-8/JSON and excessive JSON nesting.
- Focused regression set: 3 passed. Latest full suite: **737 passed, 0 failed, 43 skipped**. Compileall and diff check passed.
- PostgreSQL integration tests remain unverified (no `TEST_POSTGRES_DSN`). Module 20 and overall project remain PARTIAL; no production actions or Git push/commit.


## 2026-11-18 — Module 21 event revision payload resource bounds (local, uncommitted)

- Gap: event revision JSON and evidence-reference arrays had no explicit resource bounds before PostgreSQL persistence.
- Added fail-closed limits: 256 KiB estimated JSON payload, nesting depth 64, 10,000 nodes, JSON-compatible values/string keys, 100 evidence refs maximum, 2,048 characters per ref. Structural checks run before JSON serialization and before acquiring lifecycle DB locks; JSON serialization disallows NaN/Infinity.
- Event lifecycle writer now routes through this shared validator. Added regression cases for oversized payloads, excessive evidence references, oversized individual references and deeply nested JSON.
- Focused state-machine suite: 6 passed. Full suite checkpoint: 738 passed, 0 failed, 43 skipped; rerun after final defensive refinements remains pending. PostgreSQL integration remains unverified without approved test DSN. Module 21 remains PARTIAL.


## 2026-11-18 — Final verification after Module 21 event-payload hardening

- Full local suite: **738 passed, 0 failed, 43 skipped**. PostgreSQL integration tests remain skipped because `TEST_POSTGRES_DSN` is absent; no live database acceptance is claimed.
- `compileall` and `git diff --check`: PASS.
- 19 modified tracked files; final code/doc diff at checkpoint **+1,554 / -200**. Branch `work/module9-continuation-local`; local HEAD and remote continuation branch SHA both `78631ecc72470d445507b4110891aa8110738256`.
- No commit/push/merge/deployment or production actions. Modules 17–21 and overall project remain PARTIAL / NOT PRODUCTION READY.


## 2026-11-18 — Module 19 Cloudflare bearer-token redirect hardening (local, uncommitted)

- Gap: Workers AI requests carried a Cloudflare bearer `Authorization` header through the default `urllib.request.urlopen` transport, which follows redirects. A 3xx response could redirect the credential-bearing request to a different origin.
- Fix: the generator's production default now uses `_open_without_redirect`; injected openers remain supported for tests. A redirect is rejected instead of followed.
- TDD regression: default transport test added first; focused Cloudflare suite **27 passed, 0 failed**. Full suite **739 passed, 0 failed, 43 skipped**. PostgreSQL integration tests remain skipped because no approved `TEST_POSTGRES_DSN` is configured.
- `compileall` and `git diff --check`: PASS. No live provider call or other external side effect. Module 19 remains PARTIAL pending provider acceptance and broader integration checks.


## 2026-11-18 — Secret-bearing provider transport redirect hardening (local, uncommitted)

- DeepSeek client finding: default `urlopen` followed redirects for a request carrying a bearer API key. Replaced the default with a no-redirect transport; custom injected openers remain supported.
- Module 9 on-chain finding: Alchemy/provider credentials can be embedded in endpoint paths; default `urlopen` followed redirects. `ReadOnlyJsonRpcTransport` now rejects redirects by default.
- TDD RED regressions confirmed both clients previously selected redirect-following transports. Focused results: DeepSeek **12 passed**; on-chain provider **44 passed**. Full suite **741 passed, 0 failed, 43 skipped**. `compileall` and `git diff --check` passed.
- No live provider calls. PostgreSQL integration remains unverified without an approved disposable `TEST_POSTGRES_DSN`. Modules 9/19 remain PARTIAL.


## 2026-11-18 — Legacy GitHub image-upload credential redirect gap

- Audit found legacy `ImageUploader._github_api_upload()` GET/PUT requests carrying GitHub bearer credentials while using redirect-following `urlopen`.
- Added RED regression first; it failed against the previous transport. Both requests now use `_open_without_redirect`.
- The active orchestrator uses the Binance presigned-media method; the GitHub REST path has no production call-site in the repository search, but remains a callable legacy method and is now hardened.
- Focused media/image suite: **28 passed, 0 failed**. Full suite and static checks pending.
- Other remaining `urlopen` calls in current call paths are public unauthenticated market/trending/Skills Hub requests or public image HEAD checks. No credentials were found attached to those call sites.
- No live requests, production side effects, commit, push, merge or deployment. PostgreSQL integration remains skipped pending an approved disposable DSN. Overall status remains PARTIAL / NOT PRODUCTION READY.


## 2026-11-18 — Full-suite verification after legacy GitHub transport fix

- Full suite: **742 passed, 0 failed, 43 skipped**. PostgreSQL integration tests remain skipped because `TEST_POSTGRES_DSN` is absent.
- `compileall -q .` and `git diff --check`: PASS.
- Working tree: 23 modified tracked files, no untracked files; diff **+1,716 / -208**. No commit or push. All live provider and production side effects remain unperformed.


## 2026-11-18 — Narrow AWS presigned upload allowlist to S3 service endpoints

- RED regression demonstrated that `attacker.amazonaws.com` passed the previous broad `*.amazonaws.com` suffix check.
- Updated the allowlist to require an explicit `s3` or `s3-*` hostname service label under `amazonaws.com`, while retaining existing HTTPS/port/userinfo/fragment/query checks and Binance domains.
- Focused image/media suite: **29 passed, 0 failed**.
- Cryptographic signature validation and local expiry parsing are not claimed. Binance's real presigned URL query contract was not fetched; verify it in a separately authorized integration acceptance before enforcing provider-specific signature/expiry field assumptions.
- Full suite/static checks pending. No live upload, production write, commit or push.


## 2026-11-18 — Full verification after presigned AWS hostname allowlist tightening

- Full suite: **742 passed, 0 failed, 43 skipped**; the 43 PostgreSQL integration tests remain skipped because `TEST_POSTGRES_DSN` is absent.
- `compileall -q .` and `git diff --check`: PASS.
- Working tree remains 23 modified tracked files, no untracked files; diff **+1,762 / -209**. Local HEAD and remote PR #14 branch SHA both `78631ecc72470d445507b4110891aa8110738256`. No commit/push.
- No production DB, provider, media-upload or publication side effects. Production readiness remains PARTIAL / NOT READY.

## 2026-11-18 — Final diff count correction

- Supersedes earlier interim diff counts: current measured worktree diff after all audit documentation appends is **23 modified tracked files, +1,791 / -209**.
- Full suite remains **742 passed, 0 failed, 43 skipped**; compileall passed after code changes and `git diff --check` was rechecked after the final documentation append.
- PR #14 remote continuation SHA remains equal to local HEAD `78631ecc72470d445507b4110891aa8110738256`. No commit or push.
## 2026-11-18 — Module 19/20 decoded-image pixel-count bounds (TDD, local pending push)

- Audit finding: the Cloudflare Workers AI generator and Module 20 visual validator enforced compressed response/file byte limits but decoded image pixels only after Pillow verification/loading. A highly compressed image could therefore cause excessive decoded-memory allocation before the existing dimension checks.
- RED evidence: added one regression to each relevant suite. Both failed against the prior implementation because `Image.Image.load()` was reached before a decoded-pixel bound was enforced.
- Fix: the Workers AI generator now rejects decoded images above 16,777,216 pixels and dimensions outside 256–4096 before verification/loading; Pillow decompression-bomb exceptions/warnings are normalized to safe image rejection. Module 20 rejects images above 2,000,000 pixels and wrong required dimensions (1080×1350) before verification/loading. Existing byte limits, exact image/draft hashes and provenance checks remain in place.
- Focused image + visual QA suites: **45 tests, 0 failures**. Full repository suite: **744 tests, 0 failures, 43 skipped**. `compileall -q .` and `git diff --check` passed.
- The 43 skipped tests are PostgreSQL integration tests gated by absent `TEST_POSTGRES_DSN`; no live PostgreSQL acceptance is implied. No Cloudflare inference, authenticated Binance media upload, real post, production DB operation, publisher activation, workflow dispatch, merge or deployment occurred.
- Changes are local and not yet committed/pushed at this checkpoint. Modules 19/20 remain PARTIAL pending real provider/media acceptance and independent OCR/vision semantic validation.


## 2026-11-18 — Pixel-bound fix pushed and hosted CI verified

- The decoded-image pixel-count hardening described above was committed as `f59a4f1d160c9e8bde830559dba95174148ec10c` (`fix: bound decoded image pixel allocations`) and pushed non-forcefully to the existing PR #14 head branch.
- Post-push verification confirmed local HEAD and remote `layer-1/module9-onchain-continuation` both equal `f59a4f1d160c9e8bde830559dba95174148ec10c`; working tree was clean.
- PR #14 remained OPEN / DRAFT / UNMERGED, with the expected head and base branches. GitHub Actions run `44340291099` for this exact SHA completed SUCCESS.
- This hosted mocked-safety workflow success does not substitute for the 43 skipped PostgreSQL integrations or real Cloudflare/Binance provider acceptance.


## 2026-11-18 — Cloudflare Workers AI model contract rechecked against official docs

- Official Cloudflare model documentation confirms the configured model ID `@cf/black-forest-labs/flux-2-klein-4b`, multipart REST input, and Base64 image output. The official launch documentation confirms `prompt`, `width`, and `height` multipart fields and a 256–1920 range; the implementation's 1024×1024 request is within that range.
- Official listed output price is $0.000287 per 512×512 tile. A 1024×1024 output is approximately four tiles, giving an estimated $0.001148 per output image before any account-specific billing effects. No live inference was called and no charge was incurred by this documentation check.
- Sources: https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/ ; https://developers.cloudflare.com/changelog/post/2026-01-15-flux-2-klein-4b-workers-ai/ ; https://developers.cloudflare.com/workers-ai/platform/pricing/ .
- This closes only the public model-ID/request-shape/pricing-documentation check. Account entitlement, real provider response, latency/quality and actual billing remain unverified. Module 19 remains PARTIAL.


## 2026-11-18 — Module 18 digit-leading Binance ticker cashtag fix (TDD, local pending push)

- Finding: `ContentVerificationEngine` accepted alphanumeric symbols beginning with digits in its canonical symbol input validation, but the cashtag extractor required the first cashtag character to be a letter. Valid Binance symbols such as `1INCH` were therefore rejected at the Module 18 identity gate.
- RED: added an end-to-end content-verification regression using a verified `1INCH` claim and `$1INCH`; it failed before the fix with `CASHTAG_ASSET_IDENTITY_MISMATCH`.
- Fix: cashtag extraction now accepts 2–20 alphanumeric characters, matching the engine's existing symbol validation contract. Exact equality with the selected canonical symbol remains mandatory; multiple or wrong cashtags still fail.
- Focused content-verification + DeepSeek suites: **40 tests, 0 failures**. Full suite: **745 tests, 0 failures, 43 skipped**. `compileall -q .` and `git diff --check` passed.
- The 43 skipped tests remain PostgreSQL integration tests gated by absent `TEST_POSTGRES_DSN`. No live provider request, database write, media upload, real Binance post, merge or deployment occurred. Change is local and not yet committed/pushed. Module 18 remains PARTIAL for broader semantic/originality/current-platform-policy acceptance.


## 2026-11-18 — Module 18 digit-leading cashtag fix pushed and CI verified

- The Module 18 fix was committed as `32497adc840a04c50d56b4efb5c1395a83593309` (`fix: accept digit-leading asset cashtags`) and pushed to the existing PR #14 branch.
- Local and remote branch SHA matched at `32497adc840a04c50d56b4efb5c1395a83593309`; PR #14 remained OPEN / DRAFT / UNMERGED with the expected base/head branches.
- GitHub Actions mocked-safety workflow for the exact commit completed SUCCESS: run `44341243997`.
- This CI result does not execute the 43 skipped PostgreSQL integration tests or establish live provider/media/publishing acceptance.

## 2026-11-19 — Module 21 open-transaction crash recovery and adapter coverage audit

- Added test_postgres_open_transaction_is_rolled_back_after_worker_process_kill. A separate worker inserts a unique run row and lease inside an open PostgreSQL transaction, signals the parent, and is force-killed. A fresh process waits for the backend to disappear and verifies the uncommitted run/lease are absent, a previously committed control row remains intact, and no orphan lease remains.
- Focused result after DSN handling hardening: 1 passed in 16.314 seconds against the guarded disposable binance_onchain_test database.
- Final full suite after subprocess-argument hardening: 750 tests, 0 failures, 0 errors, 0 skipped in 414.859 seconds with the isolated PostgreSQL DSN loaded in-process and exact allowed-host/TLS guard active. PostgreSQL integration tests executed rather than being skipped.
- Fresh-process persistence coverage inventory: PostgreSQL event lifecycle has a fresh-process reopen test; Module 21 publication/run lease, unknown attempt/quota, and research/editorial/draft/validation/image/opportunity/authorization paths have fresh-process coverage. The inspected tests do not show explicit fresh-process recovery tests for PostgresClaimRegistryStore, PostgresLayer1Store, PostgresLegacyDatabase, or Module 9 PostgresOnChainIngestionStore / PostgresOnChainStore. These are next coverage gaps to assess; same-process round trips and transaction rollback tests are not equivalent to restart recovery.
- No production database, runtime cutover, provider inference, authenticated upload, real Binance publication, merge or deployment. SQLite remains the runtime default. Module 21 and the overall project remain PARTIAL / NOT PRODUCTION-READY.
- Final verification: compileall -q . PASS; git diff --check PASS; credential-pattern scan of the complete diff PASS. Test/code commit 4a32320c9d697ece7be5e9c553f81baaa7128de1 and documentation follow-up commit 06bd27ba5d99efba1adbbb030092e444ce61c894 were non-force pushed to the existing PR #14 branch. Latest local and remote SHA match 06bd27ba5d99efba1adbbb030092e444ce61c894; PR #14 remains OPEN / DRAFT / UNMERGED. Hosted CI run 44448416055 for the latest exact SHA completed SUCCESS. Next: design isolated fresh-process adapter tests from actual contracts; do not merge or deploy.
# LATEST AUTHORITATIVE GAP REGISTER UPDATE — 2026-11-20 (PostgreSQL adapter fresh-process coverage)

This update supersedes the 2026-11-19 next-step statement about adding fresh-process coverage to the four adapters below. Historical entries remain for traceability.

## Newly verified adapter persistence coverage
- Correct worktree: `/tmp/binance-w2e-continuation`; local branch `work/module9-continuation-local`; parent HEAD `3b3cc2d92c059f4e6f4ad110a5ff6a8fd69117e8`, matching the remote PR #14 branch before these local changes.
- Added five test-only fresh-process reopen checks:
  - Claim registry snapshot persistence (`PostgresClaimRegistryStore`).
  - Layer 1 market observation persistence (`PostgresLayer1Store`).
  - Legacy post-history persistence (`PostgresLegacyDatabase`).
  - Module 9 ingestion checkpoint + event persistence (`PostgresOnChainIngestionStore`).
  - Module 9 verified on-chain observation persistence (`PostgresOnChainStore`).
- Each test creates synthetic data in the dedicated disposable `binance_onchain_test` database, closes the originating connection, and reads the data from a new process. This establishes process-boundary persistence for the tested records; it is not a crash/failover drill or production cutover.
- Combined adapter batch: **24 passed, 0 failed, 0 skipped**. New tests individually passed.
- Initial full-suite execution on 2026-11-20: 755 tests, 53 skipped; superseded by the later final run recorded below (**755 tests, 0 skipped**).
- `compileall`, `git diff --check`, and changed-diff secret-pattern scan all passed.
- Four test files modified only (229 insertions); no application runtime or production components changed. Work is not yet committed/pushed; remote branch remains at parent SHA.
- No real publish/network POST occurred; publisher output explicitly showed dry-run with no network POST attempted.

## Remaining production/operational gaps
- PostgreSQL database failover/reconnect drills remain outstanding.
- Full scheduled discovery-to-publication recovery and operator acceptance across all 21 modules remain outstanding.
- SQLite remains runtime default; no PostgreSQL production cutover has been approved or demonstrated.
- Production DB architecture/cutover review and explicit owner approval remain mandatory.
- Real provider inference, OCR/vision acceptance, authenticated Binance media upload and real publishing are not covered by these tests.
- Project status remains **PARTIAL / NOT PRODUCTION-READY**.

---
# LATEST AUTHORITATIVE GAP REGISTER UPDATE — 2026-11-20 (PostgreSQL adapter fresh-process coverage)

This update supersedes the 2026-11-19 next-step statement about adding fresh-process coverage to the adapters below. Historical entries remain for traceability.

## Newly verified adapter persistence coverage
- Correct worktree: `/tmp/binance-w2e-continuation`; local branch `work/module9-continuation-local`; parent HEAD `3b3cc2d92c059f4e6f4ad110a5ff6a8fd69117e8`, matching the remote PR #14 branch before these changes.
- Added five test-only fresh-process reopen checks:
  - Claim registry snapshot persistence (`PostgresClaimRegistryStore`).
  - Layer 1 market observation persistence (`PostgresLayer1Store`).
  - Legacy post-history persistence (`PostgresLegacyDatabase`).
  - Module 9 ingestion checkpoint + event persistence (`PostgresOnChainIngestionStore`).
  - Module 9 verified on-chain observation persistence (`PostgresOnChainStore`).
- Each test stores synthetic data in the dedicated disposable `binance_onchain_test` database, closes the originating connection, and verifies recovery from a new process. The verified observation test uses unique mapping and observation identifiers and key-scoped cleanup. This is process-boundary persistence evidence, not a database crash/failover drill or production cutover.
- Combined adapter batch before final cleanup refinement: **24 passed, 0 failed, 0 skipped**. All five new tests passed individually during development; final cleanup-refined verified-observation test rerun: **1 passed**.
- Final full suite after final code/test change on 2026-11-20: **755 tests, 0 failures, 0 errors, 0 skipped**, 425.521 seconds; process exit code 0. PostgreSQL-gated tests ran with the isolated disposable test DSN.
- `compileall`, `git diff --check`, and changed-diff secret-pattern scan passed.
- Changed scope: four test files (229 insertions) and these two project documentation files. No application runtime or production components changed. Changes await commit/push; remote PR branch was still at parent SHA on last verification.
- No real publication occurred; the suite explicitly logged publisher dry-run with no network POST attempted.

## Remaining production/operational gaps
- PostgreSQL database failover/reconnect drills remain outstanding.
- Full scheduled discovery-to-publication recovery and operator acceptance across all 21 modules remain outstanding.
- SQLite remains runtime default; no PostgreSQL production cutover has been approved or demonstrated.
- Production DB architecture/cutover review and explicit owner approval remain mandatory.
- Real provider inference, OCR/vision acceptance, authenticated Binance media upload and real publishing are not covered by these tests.
- Project status remains **PARTIAL / NOT PRODUCTION-READY**.

---

# LATEST AUTHORITATIVE GAP REGISTER UPDATE — 2026-11-20 (PostgreSQL client-connection recovery)

This update supersedes the previous 2026-11-20 test count and next-step statement. Earlier records remain historical.

## Client connection loss / recovery evidence
- Added `test_closed_connection_fails_closed_and_new_store_recovers_durable_quota` in `tests/test_publication_postgres.py`.
- Against the disposable `binance_onchain_test` database, the test commits a synthetic quota reservation, closes the original psycopg connection, verifies that the closed connection raises `psycopg.OperationalError`, creates a new `PostgresPublicationStore`, and verifies the committed reservation is still present and `RESERVED`.
- Focused test: **1 passed**. Full repository suite after the change: **756 tests, 0 failures, 0 errors, 0 skipped**, 425.211 seconds; exit code 0.
- The managed test DB rejected `pg_terminate_backend` for the test session (returned false). Therefore this is client-connection closure plus explicit store reconstruction—not a PostgreSQL backend-kill, TCP partition, cluster failover or transparent reconnect drill.
- No application runtime code changed. The existing store's closed connection fails rather than silently falling back; recovery here requires creating a new store object. Production runtime restart/reconstruction behavior still needs end-to-end acceptance.
- Previous initial 755-test run with 53 skips is superseded by the final 755-test zero-skip run recorded in the prior checkpoint, and now by this latest 756-test zero-skip run.

## Remaining Module 21 / production gaps
- Real PostgreSQL backend termination, server restart, HA failover, DNS/endpoint failover and reconnect acceptance remain open; they require a controlled authorized PostgreSQL environment with the necessary privileges/topology.
- Scheduled discovery-to-publication recovery and full operator acceptance across all 21 modules remain outstanding.
- SQLite remains runtime default; no PostgreSQL production cutover is approved or demonstrated.
- Production DB architecture/cutover review and explicit owner approval remain mandatory.
- Real provider inference, independent OCR/vision acceptance, authenticated Binance media upload and real publishing remain outside this test evidence.
- Project remains **PARTIAL / NOT PRODUCTION-READY**. No production DB writes, publisher activation, real post, merge or deployment.

---


# LATEST AUTHORITATIVE GAP REGISTER UPDATE — 2026-11-20 (scheduled entrypoint cleanup)

## Newly closed code-level lifecycle gap
- In the one-shot scheduled entrypoint, `main.main()` previously read posted-symbol history before entering `try/finally`. A history DB exception therefore skipped explicit close of the publisher DB and shared PostgreSQL store.
- Moved the history read into the protected lifecycle and added `test_one_shot_bootstrap_closes_postgres_resources_when_history_read_fails`, proving both resources close and the cycle does not enter `run_once`.
- Focused regression: **1 passed**; scheduled persistence safety suite: **10 passed**; existing `run_once` lease/failure suite: **11 passed**.
- Full repository suite: **757 tests, 0 failures, 0 errors, 54 skipped**, exit code 0. The current runtime had no `TEST_POSTGRES_DSN` and no `psycopg`; PostgreSQL-gated tests were skipped. This does not prove PostgreSQL runtime acceptance.
- A separate read-only check of the older mode-0600 test `.env` found the expected disposable DB name, host allowlist match and `sslmode=require`, but the live session reported `pg_stat_ssl.ssl=false`. The DSN was not supplied to tests and no DB writes were attempted; PostgreSQL integration remains unverified here.
- Application/test commit `87e43863016dca951c7b747c70f6ebd783e7c7fe` was pushed to PR #14. Hosted CI run `44624351552` for combined SHA `aa413a483e8643eb420717232251ceb993f889e3` passed; this run predates the latest documentation-only correction, so the final docs SHA still needs hosted CI verification. Compileall, diff check and changed-diff credential-pattern scan passed.

## Remaining Module 21 / production gaps
- Actual PostgreSQL backend kill, server restart, HA failover, DNS/endpoint failover and transparent reconnect remain unverified.
- Full scheduled discovery-to-publication recovery across discovery, authorization, quota, publisher and reconciliation remains outstanding; this change covers bootstrap resource cleanup only.
- SQLite remains runtime default; no production PostgreSQL cutover is approved or demonstrated.
- Production DB architecture review and explicit owner approval remain mandatory.
- Live provider inference, independent OCR/vision acceptance, authenticated Binance media upload and real publishing acceptance remain outstanding.
- Project remains **PARTIAL / NOT PRODUCTION-READY**. No production writes, publisher activation, real post, merge or deployment.


# LATEST AUTHORITATIVE GAP REGISTER UPDATE — 2026-11-20 (one-shot scheduler lease integration)

## Closed scheduled-entrypoint resource leak
- PostgreSQL store creation followed by a failing `PostPublisher` constructor previously bypassed the one-shot entrypoint's cleanup block. A test was written first and reproduced the uncaught constructor exception.
- Moved publisher construction into the protected lifecycle; close the publisher DB only if constructed, and always close the PostgreSQL store when present.
- Regression `test_one_shot_bootstrap_closes_postgres_store_when_publisher_initialization_fails`: PASS.

## One-shot scheduler → run lease integration
- Added real `main.main()` → `run_once()` orchestration tests with downstream pipeline mocked.
- Success path: durable lease adapter receives acquire and matching `SUCCEEDED` finish; publisher DB and shared store close.
- Failure path: synthetic pipeline exception results in matching `FAILED` lease finalization before nonzero scheduler exit; both DB resources close.
- Scheduled safety suite: **13 passed**; combined runtime-adapter + scheduled safety batch: **24 passed**.
- Full suite: **760 passed, 0 failed, 0 errors, 54 skipped**, 50.284 seconds. `TEST_POSTGRES_DSN` absent; PostgreSQL DB integration tests were skipped. No live PostgreSQL end-to-end acceptance established.
- Actual discovery → PostgreSQL evidence persistence → quota → authorization → publication → reconciliation workflow remains unverified as a single controlled run. The new tests cover orchestration and lease lifecycle only; they deliberately mock discovery/publication and cannot submit a post.

## Production blockers remain
- Real PostgreSQL HA/backend-kill/restart/DNS/reconnect drill and an authorized controlled TLS test endpoint.
- Scheduled full-path acceptance with real disposable PostgreSQL, mocked external providers and no publication side effects.
- Production database architecture/cutover review and explicit owner approval; SQLite remains runtime default.
- Real provider, OCR/vision, authenticated media upload and Binance publishing acceptance.
- Project remains **PARTIAL / NOT PRODUCTION-READY**. No production DB writes, real post, merge or deployment.


# LATEST AUTHORITATIVE GAP REGISTER UPDATE — 2026-11-20 (TLS test prerequisite re-verification)

## B-PG-01 — BLOCKED
- Read-only active environment check: `TEST_POSTGRES_DSN` absent; neither `psycopg` nor `psycopg2` is available.
- The previously inspected DSN is not eligible for reuse because its live PostgreSQL session reported `pg_stat_ssl.ssl = false`.
- No database connection or write was attempted; no package or database server was installed/launched.
- Existing fixture checks the disposable database name, exact allowlisted host and requested TLS mode before migrations. Add/perform a live preflight that verifies `pg_stat_ssl.ssl = true`, `pg_backend_pid()`, and the actual connected database before allowing migrations or test writes.
- Required prerequisite: owner-authorized disposable PostgreSQL endpoint, exact host allowlist, TLS certificate/hostname validation, dedicated test credentials and sufficient test-schema permissions.

## B-PG-02 — NOT VERIFIED: full scheduled workflow acceptance
- Required harness: real PostgreSQL adapters and transaction boundaries; deterministic mocked discovery/research/content/image providers; local in-process publisher transport fake with network disabled.
- Cover run lease, discovery, evidence persistence, quota reservation, authorization, mocked publication-attempt ledger, reconciliation, final state, failure cleanup, duplicate-run protection and concurrent quota/lease contention.
- Verify durable records from a fresh connection/process and prove zero external provider/Binance network calls. No real media upload or post.
- Current one-shot scheduler tests cover orchestration/lease lifecycle with fake downstream pipeline dependencies; they do not satisfy this full-path gate.

## main_loop() investigation — no defect established
- The caught posted-symbol history value is passed to `_run_once_impl()`, whose current body does not consume that argument. No change is justified by this path alone.
- Separate post-history and DB cooldown reads inside `_run_once_impl()` retain their own exception handling and may merit a separate targeted audit. Do not treat that as a confirmed defect without tracing enforcement and writing a failing test first.

## Remaining operational acceptance
- B-PG-03/B-PG-04: backend kill, server restart, HA/DNS failover and reconnect remain NOT VERIFIED; require an authorized controllable database topology and suitable privileges.
- B-PG-05: production DB architecture review and owner approval remain PENDING.
- B-CF-01, B-VIS-01, B-SCORE-01, B-CONTENT-01, B-POLICY-01 and B-PUBLISH-01 remain open.
- SQLite remains runtime default. Project remains **PARTIAL — NOT PRODUCTION-READY**.
- No production resources, publisher/gateway, external providers, real Binance publication, merge or deployment were touched.



# CONTINUATION CORRECTION — 2026-11-20 (adapter test inventory)

- Read-only source inspection at local/remote PR #14 SHA `c165be0fc60606abe262ad9b91fb9f2553f5e2ee` found existing clean-reopen subprocess tests for `PostgresClaimRegistryStore`, `PostgresLayer1Store`, `PostgresLegacyDatabase`, `PostgresOnChainIngestionStore`, and `PostgresOnChainStore` (exact test names and paths are recorded in `PROJECT_CONTEXT.md`).
- These tests close the original connection and read committed synthetic records from a separate Python process. They are NOT writer-process crash tests and do not prove rollback of an uncommitted transaction after abrupt termination. The prior gap wording that said no fresh-process tests existed was too broad; the remaining gap is crash-during-open-transaction and operational recovery semantics.
- The disposable `binance_onchain_test` acceptance was previously completed (750 passed, 0 failed, 0 skipped on 19 November); do not repeat it without a new, narrowly scoped test requirement.
- B-PG-01 remains BLOCKED for new DB-backed work because the older DSN's live session reported `pg_stat_ssl.ssl = false`. No DB connection, migration or write was attempted in this audit. The 20 November 760-test suite had 54 skips because the DSN was absent and must not be represented as PostgreSQL acceptance.
- Next: inspect adapter transaction boundaries and design isolated process-kill/rollback tests. Run them only after owner authorization and live read-only verification of the disposable database identity, exact allowed host and `pg_stat_ssl.ssl = true`. Backend termination, server restart and HA/DNS failover remain separate NOT VERIFIED gates.


# LATEST GAP REGISTER UPDATE — 2026-11-20 (adapter crash rollback + disposable endpoint)

## B-PG-01 — BLOCKED for new DB-backed tests
- The existing dedicated Neon branch `module9-pg-lease-fencing-disposable` (`br-falling-butterfly-az03rryi`) is still `ready`; its endpoint `module9-disposable-test` (`ep-autumn-frost-azvk3fj4`) is currently `idle`/suspended (suspended at `2026-11-19T22:06:46Z`). It was not woken.
- Active RDC shell lacks `TEST_POSTGRES_DSN` and `TEST_POSTGRES_ALLOWED_HOST`. The historical `.env` file exists but was not read; its previously recorded connection was rejected after live `pg_stat_ssl.ssl=false` evidence.
- No DB connection, SQL, migration, write, endpoint start, restart, credential retrieval or dependency installation occurred. Do not repeat the prior 750-test disposable acceptance.

## Adapter crash-during-transaction gap — design only
- Claim registry: kill after `layer1_claim_verification_runs` INSERT; assert snapshot absent.
- Layer1: exercise `save_announcement()` and kill after the revision INSERT but before the evidence INSERT completes; assert both rows absent.
- Legacy: kill after synthetic `posts` INSERT; assert post absent.
- On-chain ingestion: kill after transfer-event INSERT and before checkpoint update; assert event absent and checkpoint unchanged.
- Verified on-chain store: kill after mapping INSERT and before observation INSERT; assert mapping and observation absent.
- Each worker must invoke the real adapter method and real psycopg transaction. A delegating connection proxy may signal readiness after the target INSERT while the transaction remains open. Parent kills the worker; a separate verifier waits for backend exit and checks rollback plus a committed control record.
- Unique synthetic keys and exact-key cleanup only. Do not use broad table truncation for these cases. No transaction defect is established by static inspection; no runtime crash rollback is yet verified.
- Run only after owner authorization and a disposable TLS-enabled endpoint passes live read-only database identity, exact-host and `pg_stat_ssl.ssl=true` checks. Keep the current idle endpoint idle unless explicitly authorized to start it.

## CI and PR
- Latest local docs checkpoint SHA before this update: `587e9337ad1a9e1438fcceab383869f618eb0dd7`.
- GitHub status and PR-workflow lookup for that SHA returned no status checks/runs. Hosted CI is NOT VERIFIED, not passed.
- Continue on existing PR #14 only; no duplicate PR, merge or deployment.

## Status
- B-PG-01 remains BLOCKED; adapter crash rollback and operational failover remain NOT VERIFIED. The previous 19 November disposable PostgreSQL suite acceptance remains valid historical evidence and will not be repeated unnecessarily.
- SQLite remains runtime default. Project remains **PARTIAL — NOT PRODUCTION-READY**.


# LATEST GAP REGISTER UPDATE — 2026-11-20 (authorized endpoint TLS preflight)

## B-PG-01 — STILL BLOCKED
- User authorized starting only the disposable Neon endpoint `module9-disposable-test` (`ep-autumn-frost-azvk3fj4`) on branch `module9-pg-lease-fencing-disposable` (`br-falling-butterfly-az03rryi`). It was started, then suspended after preflight; final read-only state is `idle` (`2026-11-20T07:57:38Z`).
- A single read-only Neon management SQL query against `binance_onchain_test` returned database `binance_onchain_test`, role `binance_bot_staging_owner`, server address `127.0.0.1/32`, and `pg_stat_ssl.ssl=false`.
- This query used the Neon management SQL connector, not the application's direct psycopg DSN; therefore it is not proof of the direct application's TLS handshake. Treat it as a failed/insufficient TLS signal and fail closed. No DB migrations or writes were run.
- Active RDC environment still lacks `TEST_POSTGRES_DSN` and `TEST_POSTGRES_ALLOWED_HOST`; no password/connection string was retrieved and no env file was read.
- Required next: dedicated test credentials + exact host allowlist provisioned securely to active test process; direct psycopg read-only preflight must confirm database identity, exact host and `pg_stat_ssl.ssl=true` on that same connection before any DB-backed tests.

## Adapter crash rollback — NOT IMPLEMENTED / NOT EXECUTED
- The five narrow process-kill tests remain design-only. Do not repeat historical 750/750 PostgreSQL suite. Run only after B-PG-01 direct TLS preflight succeeds.
- No production DB/config, publisher, workflow, Binance account, merge or deployment was touched. Project remains PARTIAL — NOT PRODUCTION-READY.


# LATEST GAP REGISTER UPDATE — 2026-11-21 (continuous scheduler PostgreSQL failure boundary)

## Code-level gap closed locally
- `main_loop()` previously swallowed a PostgreSQL connection/session failure from `get_posted_symbols()` and substituted an empty set. In PostgreSQL mode this could allow the scheduler to continue without trustworthy duplicate history.
- Added fail-closed classification for psycopg `OperationalError` and `InterfaceError`. History-read connection loss now stops before pipeline execution; connection loss during `run_once()` stops with a non-zero exit and explicit reconciliation-before-retry log. No automatic retry or uncertain-publication replay is performed.
- Added `try/finally` ownership cleanup around continuous scheduler initialization and execution. Publisher DB closes if constructed; shared PostgreSQL store closes even when `PostPublisher` initialization fails.
- Regression tests cover history lookup loss, mid-iteration loss, both resource closures, and publisher-constructor failure. The constructor cleanup test failed before the fix and passed after it.

## Verification
- Scheduled persistence suite: **16 passed, 0 failed**.
- Full repository suite: **775 passed, 0 failed, 58 skipped**, 38.836 seconds, exit code 0.
- Skips include PostgreSQL integration tests because `TEST_POSTGRES_DSN` was absent. This run is NOT PostgreSQL backend/restart/failover acceptance.
- Compileall and `git diff --check` passed. A separate synthetic mid-iteration psycopg connection-loss test verified non-zero exit and closure of both resources.
- Local-only, uncommitted changes at HEAD `a7c7e809d2a576d6062772cb7f086f03fccac776`, branch `work/module9-continuation-local`: `main.py`, `tests/test_scheduled_persistence_safety.py`, and documentation. Existing PR #14 remote branch still matched the pre-change HEAD at the final remote check; no commit/push/PR/merge/deployment occurred.

## Remaining operational acceptance — NOT VERIFIED
- Actual PostgreSQL backend termination, server restart, HA failover, DNS/endpoint failover and transparent reconnect.
- Controlled disposable PostgreSQL crash/rollback tests and full scheduled 21-module recovery acceptance; requires separately authorized active DB endpoint and test DSN.
- Full path must still prove durable run lease, discovery/evidence persistence, quota, authorization, publisher attempt ledger, reconciliation, fresh-process recovery and zero real Binance publication side effects.
- SQLite remains runtime default; production database cutover and architecture approval remain pending.
- Project remains **PARTIAL — NOT PRODUCTION-READY**. No production DB writes, real Binance post, publisher activation, merge or deployment.


# LATEST GAP REGISTER UPDATE — 2026-11-21 (CI dependency failure)

- Existing PR #14 CI run `44913324014` failed because `.github/workflows/phase1-safety-tests.yml` installed Pillow but omitted the optional PostgreSQL driver required by mocked tests. The job log shows 10 errors, each `ModuleNotFoundError: No module named 'psycopg'`; this was a CI dependency setup defect, not a test assertion or application compile failure.
- Workflow now installs `requirements-onchain-postgres.txt` in the mocked test job. That file includes the existing `psycopg[binary]>=3.2,<4` requirement. No live DB connection is enabled by installing the driver.
- Verification: PostgreSQL target guard + scheduled persistence suites **24 passed**; full suite **775 tests, exit code 0**; compileall and diff check passed. `TEST_POSTGRES_DSN` remains absent, so DB integration/restart/failover acceptance is still unverified.
- The workflow fix and documentation are local only until the next verified push to the existing PR #14 branch. Project remains **PARTIAL — NOT PRODUCTION-READY**.


# LATEST GAP REGISTER UPDATE — 2026-11-21 (publication authorization DB failure boundary)

## Additional code-level gap closed locally
- In `main.py`, publication-authorization exceptions were all treated as normal policy denials. A PostgreSQL `OperationalError`/`InterfaceError` could be caught, quota release attempted, and the cycle returned as a normal blocked result.
- Added a PostgreSQL-only connection-failure propagation guard before quota release. Transport/session failures now reach the existing supervised-restart path and preserve the reservation fence. Ordinary policy/validation errors still release quota; SQLite behavior is unchanged.
- Added two regression tests. RED was observed before implementation; both passed after the fix.
- Focused suites: **77 passed, 0 failed**. Full local suite: **779 passed, 0 failed, 58 skipped**. Compileall and diff check passed. The 58 skips include PostgreSQL DB integration tests; no DSN was supplied and no new database acceptance occurred.
- Current change is local/uncommitted on `work/module9-continuation-local` at base SHA `f42d0f24c81d90227098a20ab72ea0581adbd312`. Live GitHub branch lookup returned the same SHA; cached `origin` tracking ref was stale. PR #14 has not yet received this change, and hosted CI has not tested it.

## B-PG-02 — STILL OPEN: complete scheduled PostgreSQL pipeline acceptance
- Existing SQLite end-to-end test covers evidence/lifecycle/research/opportunity/editorial/draft/text QA/image/visual QA/authorization, but not the complete scheduled `run_once()` orchestration on PostgreSQL.
- Separate PostgreSQL tests already cover run-lease worker termination and recovery, durable publication attempts, fresh-process unknown-outcome reconciliation, quota fencing, and mocked publisher transport. Do not misstate these as one complete scheduled-flow acceptance.
- Still required: one isolated end-to-end scheduled harness using real PostgreSQL adapters, deterministic discovery/research/content/image fakes, network-disabled publisher transport, failure injection at stage boundaries, fresh-process verification of durable records, unknown outcome reconciliation, duplicate prevention, and proof of zero real Binance/provider side effects.
- Neon endpoint remains suspended. No migrations, DB writes, endpoint wake, provider API call, real media upload, Binance post, merge or deployment occurred in this step.

## Status
- Project remains **PARTIAL — NOT PRODUCTION-READY**. SQLite remains runtime default. Production DB cutover, full scheduled PostgreSQL acceptance, backend termination/restart/HA/DNS failover and owner architecture approval remain open.


# POST-PUSH STATUS — 2026-11-21 (commit 935c264)

- Latest source/test hardening commit `935c2647771c2777fd5a841a71fed4c288a5749f` is verified on the existing PR #14 head branch. PR #14 remains OPEN / DRAFT / UNMERGED and targets `layer-1/module9-onchain-intelligence`.
- Hosted GitHub Actions run `44919716032` completed **success** for commit `935c264`. It validates the mocked safety workflow only; it does not close B-PG-02 or prove live PostgreSQL acceptance.
- Local full suite: **779 passed, 0 failed, 58 skipped**; all 58 skipped tests remain excluded from PostgreSQL acceptance claims.
- Continue with the design/implementation of the full scheduled PostgreSQL acceptance harness. Neon remains suspended and needs a separately approved test window before any new DB-backed run.


# B-PG-02 DEPENDENCY AUDIT — 2026-11-21

## Newly verified blocker: B-SCORE-01 prevents the positive scheduled path
- `main.py::_run_once_impl()` currently calls `OpportunityEvaluationEngine.evaluate(..., factors=None, policy=None)` when it persists each research package.
- `OpportunityEvaluationEngine` explicitly returns `DEFER` with `APPROVED_OPPORTUNITY_SCORING_POLICY_NOT_CONFIGURED` when other prerequisites pass but policy is absent. Runtime persists the decision and creates an editorial brief only inside `if opportunity_decision.state == "PROCEED"`.
- Therefore the current scheduled runtime cannot reach editorial brief, draft, authorization, quota reservation or publisher submission on the positive path. This is intentional fail-closed behavior while B-SCORE-01 awaits an owner-approved scoring policy and evidence-backed factors.
- Do not invent weights/factors, monkeypatch the production engine to force `PROCEED`, or claim a test-only policy proves production acceptance.
- Existing `tests/test_opportunity.py::test_unconfigured_policy_defers_instead_of_guessing_weights` covers the engine contract; the SQLite end-to-end test passes an explicit test policy directly and does not validate scheduled runtime configuration.

## B-PG-02 test strategy update
- Keep B-PG-02 OPEN. Split acceptance into (a) current scheduled fail-closed path, which should persist a DEFER decision and prove no editorial/draft/authorization/quota/publisher side effects, and (b) positive scheduled path, which is blocked until B-SCORE-01 is resolved by the owner.
- Prepare a deterministic harness using actual PostgreSQL adapters and an ephemeral isolated PostgreSQL service, with fake discovery/announcement/research/content/image providers and a publisher transport that is technically unable to reach the network. Include failure injection, fresh-process reads, unknown-outcome reconciliation and duplicate prevention once the positive path is legitimately available.
- Active RDC shell has no `TEST_POSTGRES_DSN` or `TEST_POSTGRES_ALLOWED_HOST`; `pg_isready` reports no local server. The Neon disposable endpoint remains suspended. No DB connection or write was attempted.
- Remote branch SHA and PR #14 head both verify `c19e8f2c5b109e641b6736fb731a3a391ced6d4b`; cached local origin tracking ref is stale. Worktree was clean before this documentation-only audit.

## Status
- B-PG-02 remains OPEN; B-SCORE-01 remains OPEN. No DB-backed acceptance, live provider call, media upload, real Binance post, merge or deployment occurred.
- Project remains **PARTIAL — NOT PRODUCTION-READY**; SQLite remains runtime default.


# POSTGRESQL CI ACCEPTANCE HARNESS — 2026-11-22

## CI integration job added locally
- Added a separate GitHub Actions job with an ephemeral `postgres:16` service and dedicated `binance_onchain_test` database. It sets only CI-local DB credentials, `TEST_POSTGRES_ALLOWED_HOST=localhost`, and runs the existing database identity/target guard before migrations/tests.
- It runs the actual DB-backed integration modules: on-chain, Layer 1, claim registry, event lifecycle, legacy compatibility, adapter atomicity, publication/recovery, and scheduled entrypoint acceptance.
- Fresh-process test assertions now distinguish loopback CI PostgreSQL (TLS not required by the local target guard) from remote database targets (the existing guard still enforces allowlisted host, TLS, and channel binding).

## Scheduled entrypoint acceptance added
- New `tests/test_scheduled_postgres_acceptance.py` calls the real `main.run_once()` with the actual PostgreSQL publication store and run-lease adapter. A deterministic empty scanner drives the safe no-candidate branch. It asserts durable `NO_CANDIDATE_OR_BLOCKED` finalization, lease release, no SQLite fallback file, no network/provider HTTP, no publisher call, and no new publication attempt/quota reservation.
- This is acceptance of the scheduled no-candidate fail-closed path only. It does not prove a complete positive discovery-to-publication run.

## Verification
- Compileall passed.
- Targeted local tests: 23 run, 0 failed, 1 DB-backed acceptance test skipped because no local DSN was supplied.
- Full local suite: **780 passed, 0 failed, 59 skipped** (41.680 sec); skipped DB tests are not counted as acceptance.
- Workflow YAML parse and `git diff --check` passed.
- Hosted PostgreSQL service job is not yet verified; wait for the GitHub Actions check before marking DB-backed acceptance green.

## Still open
- B-PG-02 remains OPEN pending hosted PostgreSQL service job success and positive-path scheduled acceptance.
- B-SCORE-01 remains OPEN: scheduled runtime supplies no approved opportunity policy/factors and correctly persists DEFER. Positive editorial/content/publication acceptance requires owner-approved weights/thresholds and evidence-backed factor derivation. Do not fabricate a policy or force PROCEED.
- Neon remains suspended. No production DB, live provider, real media upload, Binance post, merge or deployment occurred. Project remains **PARTIAL — NOT PRODUCTION-READY**.


# POSTGRESQL MIGRATION RUNNER REGRESSION — 2026-11-22

## Hosted CI diagnosis
- Run `44960145503`: mocked safety job **success**; isolated PostgreSQL integration job **failure**.
- PostgreSQL 16 service startup and the read-only target guard both succeeded. Migration application then failed with `psycopg.errors.SyntaxError` at the prose fragment `apply only on an isolated disposable test branch.`
- Root cause: `apply_postgres_migrations()` used naive `source.split(";")`; migration `0001_publication_storage.sql` has a semicolon in a `--` comment, so a fragment of that comment was executed as SQL. Subsequent missing-table errors were downstream effects.

## Fix and regression tests
- Added a SQL-aware `_split_sql_statements()` handling line comments, nested block comments, single-quoted values, double-quoted identifiers, and doubled quote escapes. Unterminated comments/quotes and dollar-quoted procedural blocks fail closed. The checked-in migration files and checksums were not modified.
- Migration runner now executes statements from the splitter.
- New parser tests: **5 passed, 0 failed**. All five checked-in migration files were parsed: statement counts 11, 37, 2, 2, 13 respectively.
- Full local suite after fix: **785 passed, 0 failed, 59 skipped**; PostgreSQL integration cases remain skipped locally because no DSN was configured.

## Status
- The failed hosted PostgreSQL run must not be counted as DB acceptance. Push the splitter fix to the existing PR #14 branch and require a new hosted run.
- B-PG-02 remains OPEN until corrected CI passes and the positive scheduled path is accepted. B-SCORE-01 remains OPEN pending owner-approved scoring policy/factors.
- No Neon wake, production DB operation, live provider call, real media upload, Binance post, merge or deployment occurred. Project remains **PARTIAL — NOT PRODUCTION-READY**.
