## Latest verified coding continuation — 2026-11-18 (persisted publication duplicate policy)

- Active implementation remains PR #14 on `layer-1/module9-onchain-continuation`; draft/open/unmerged. User approved application-code commits on this existing branch. RDC remains prohibited.
- Removed caller-supplied `duplicate_policy_passed=True` from application authorization flow. The authorization engine now computes the duplicate-policy result from persisted ledgers; the caller cannot declare the policy passed.
- The persisted policy checks:
  - Recent same-symbol posts within configured `repetition_hard_hours` (1–168 hours).
  - Exact duplicate content hashes in prior posts/confirmed attempts.
  - Unresolved `SUBMITTING` / `PUBLICATION_UNKNOWN` attempts, which block even exceptional catalyst events.
  - Competing active quota reservations for the same symbol.
  - Exceptional cooldown bypass only when the persisted event lifecycle is CONFIRMED/DEVELOPING and its persisted event type is explicitly allowlisted (`new_listing`, `launchpool`, `megadrop`, `airdrop`, `delisting`). It never bypasses unresolved attempts, exact content duplicates or competing reservations.
- SQLite authorization and pre-submit revalidation use the existing posts/attempts/quota tables and acquire an immediate write transaction. The publisher rechecks again immediately before the HTTP POST, excluding only its own idempotency key and quota reservation.
- PostgreSQL authorization and pre-submit revalidation use the existing publication tables and symbol-scoped transaction advisory lock; the pre-submit lock is acquired before row locks to preserve lock order. The PostgreSQL store rechecks the same duplicate policy immediately before the external POST.
- Regression coverage added for recent posts, unresolved attempts, exceptional-event non-bypass, competing reservations, revalidation after authorization, and PostgreSQL parity. Hosted CI run `44219811233` for commit `bde27012230a8c8ec695643d41e9023efcb4c792`: SUCCESS; compileall passed; **683 tests, 0 failures, 40 skipped**.
- The 40 skipped tests include PostgreSQL integration tests because `TEST_POSTGRES_DSN` was not configured in this hosted run. The PostgreSQL duplicate-policy integration case is present but not live-verified here.
- No real Binance post, authenticated media upload, production DB write, production credential/schedule change, workflow dispatch, publisher activation, merge or deployment.
- Do not repeat these fixes. Next priority is to continue remaining Layer 1–21 integration gaps, especially operational Module 9 worker/runtime integration and remaining Module 11 semantic verification gaps. Do not invent monitored addresses or source configuration; require explicit configuration and fail closed when absent.

## Latest verified coding continuation — 2026-11-18 (independent publication kill switch)

- Active target remains PR #14 on `layer-1/module9-onchain-continuation`; base branch remains `layer-1/module9-onchain-intelligence`. PR remains draft/open/unmerged.
- User approved application-code commits on this existing PR branch. RDC remains prohibited. No workflow dispatch, deployment, merge, production DB write or real Binance post.
- Added an independent, default-off `PUBLISHER_ENABLED` configuration flag:
  - `Config.from_env()` reads strict boolean `PUBLISHER_ENABLED`, default `false`.
  - Live configuration validation rejects `DRY_RUN=false` unless `PUBLISHER_ENABLED=true`, in addition to existing provider-credential and durable PostgreSQL requirements.
  - `PostPublisher.publish()` returns `PUBLISHER_DISABLED` before authorization/network when the switch is off.
  - `upload_authorized_image()` independently refuses real media upload unless the switch is explicitly true; the application passes the config flag into the upload boundary.
  - The main runtime fingerprint includes the switch. Existing scheduled workflow remains unchanged with `DRY_RUN=1`; no `PUBLISHER_ENABLED=true` value was added. Publisher remains disabled.
- TDD test-only commit `9a45119df7ba5410c6b44c01046b94d739809dc5` added coverage for default-off behavior, config validation, direct publisher blocking, and media-upload blocking. CI initially reproduced the missing config field and expected failures.
- Implementation commits: `897f47e92727b0a5edba66f68ee9df0f460b6c29`, `aad1d5cdac87e6659247630e1e219f130e727810`, `e0e5f6acb6c3a3c90c40f791873173ce34310055`. Follow-up test fixture commits: `1b293a93ffbe5d5b4a1c2cffc71f71e489ba62f2`, `698860680573da989a577f76587e5f9cb6e1c23b`.
- Final GitHub Actions run `44218585027` for exact commit `698860680573da989a577f76587e5f9cb6e1c23b`: SUCCESS; compileall passed; **678 tests, 0 failures, 40 skipped**.
- The 40 skips still include live PostgreSQL integration tests without `TEST_POSTGRES_DSN`. No PostgreSQL parity acceptance is implied.
- No publisher activation, real media upload, real Binance post, production database/credential/schedule changes, workflow dispatch, merge or deployment.
- Continue the remaining Layer 1–21 gap register; the independent publisher kill switch is now implemented and must not be re-created.

## Latest verified coding continuation — 2026-11-18 (Module 12 lifecycle + Module 18/21 publication evidence contract)

- Active target remains PR #14 on `layer-1/module9-onchain-continuation`; base branch remains `layer-1/module9-onchain-intelligence`. No merge or deployment.
- User explicitly approved application-code commits to the existing PR branch. RDC remains prohibited; implementation and verification are performed through GitHub source commits and the repository's existing GitHub Actions CI.
- Test-first commit: `49d4aaec913d49af01a4e5325eba995c2c161a5a`. It added regression tests for the content-evidence status contract and non-material revisions of STALE/RESOLVED events. CI run `44217708860` reproduced 4 errors across 674 tests (40 skipped): two missing evidence-status contract errors and two illegal lifecycle transition errors. This is the expected RED result.
- Implementation commit: `2c45e6611779316b62be1721bfa83daf71ef4dd9`.
  - `ContentVerificationResult.evidence_status` now maps only PASS with non-empty approved claim IDs to VERIFIED; all other outcomes map to UNVERIFIED.
  - Main publication authorization now passes the evidence status separately from text-validation status. This fixes the PASS-versus-VERIFIED contract mismatch that blocked valid publication authorization.
  - SQLite and PostgreSQL event lifecycle state machines now confirm a verified event only from UNDER_VERIFICATION. A cosmetic/non-material new revision no longer attempts the illegal STALE/RESOLVED → CONFIRMED transition. A materially new, verified revision still reopens through UNDER_VERIFICATION according to the existing transition graph.
- GitHub Actions run `44217840412` for the exact implementation commit completed SUCCESS: `python -m compileall` passed and unittest discovery ran **674 tests, 0 failures, 40 skipped**.
- The 40 skipped tests include PostgreSQL integration tests because `TEST_POSTGRES_DSN` was not configured in this GitHub Actions run. The SQLite regressions passed; PostgreSQL parity test cases were added but their live database execution is still pending. Do not report PostgreSQL parity as verified from this CI run.
- No real Binance Square post, authenticated media upload, production DB write, credential/schedule change, workflow dispatch, publisher activation, merge, deployment or paid infrastructure action occurred.
- Next: continue the remaining Layer 1–21 integration and safety gap register in priority order; do not repeat these fixes. Re-run PostgreSQL parity tests only against the exact isolated allowlisted test database, never production.

# Binance Square Write-to-Earn Agent — Canonical Project Context

Last updated: 2026-11-16 (Pakistan local date, UTC+05:00) — Blocker #1 isolated PostgreSQL acceptance verified

## LATEST IMPLEMENTATION CHECKPOINT — BLOCKER #1 (2026-11-16)

- Repository: `shehrozali6465372-ctrl/Binance-bot`; target branch: `layer-1/module9-onchain-continuation`; PR #14 remains OPEN, DRAFT and UNMERGED. Code head before this documentation update: `9091e036d55085ffb6525f1405dc0e5739053883`.
- The implementation reuses the existing PostgreSQL publication runtime, migrations, `PostgresLegacyDatabase`, atomic quota reservations and PostgreSQL run lease; no duplicate persistence subsystem was created.
- Fix on this branch: `_get_today_post_count()` validates a non-negative integer and raises a sanitized `RuntimeError` on unavailable/malformed database results. It never resets quota to zero on a database failure. GitHub Actions passes repository variable `PERSISTENCE_BACKEND` (default `sqlite` while dry-run) and secret `POSTGRES_DSN`; the read-only `ANNOUNCEMENT_DATABASE_URL` is not reused as the writable publication ledger. Live GHA publishing is rejected unless PostgreSQL is selected.
- **Isolated PostgreSQL acceptance — PASS:** loaded only `TEST_POSTGRES_DSN` and `TEST_POSTGRES_ALLOWED_HOST` from the pre-existing mode-0600 file `/tmp/binance-deepseek-verify/.env`. A preflight verified database `binance_onchain_test`, exact allowlisted host and TLS. Values were parsed in-process and never printed, copied into docs, or sent to GitHub.
- Targeted acceptance command ran `tests.test_scheduled_persistence_safety`, `tests.test_legacy_postgres`, and `tests.test_publication_postgres`: **44 tests passed, 0 failed, 0 skipped**. This includes concurrent quota reservation, durable run-lease fencing, PostgreSQL legacy history/analytics and quota count, publication attempt idempotency/reconciliation, and fail-closed scheduled persistence behavior.
- Additional actual application-wiring smoke test — **PASS** with `PERSISTENCE_BACKEND=postgresql`, `POSTGRES_DSN` temporarily set to the isolated test DSN and `DRY_RUN=1`: `_create_runtime_postgres_store()` applied/checked migrations, `PostPublisher` used `PostgresLegacyDatabase` on the shared PostgreSQL connection, SQLite fallback was absent, and the quota count returned an integer. The connected database identity was verified as `binance_onchain_test`.
- Existing GitHub Actions CI for code head `9091e036d55085ffb6525f1405dc0e5739053883`: run `43891086561`, completed SUCCESS. This is mocked safety CI, not live publishing acceptance.
- Safety preserved: workflow `DRY_RUN: "1"` remains unchanged. No production DSN was used; no production DB operation, GitHub secret/variable mutation, publisher activation, real Binance Square post, workflow dispatch, merge or deployment occurred. No paid infrastructure was provisioned.
- **Status: IMPLEMENTATION AND ISOLATED POSTGRESQL ACCEPTANCE VERIFIED; LIVE OPERATIONAL CUTOVER STILL NOT APPROVED/VERIFIED.** The workflow defaults to SQLite unless the repository variable is explicitly set. Before any live scheduled publishing, the owner must configure a writable production `POSTGRES_DSN` GitHub secret and repository variable `PERSISTENCE_BACKEND=postgresql`, then separately authorize live publishing. Never use `TEST_POSTGRES_DSN` as the production DSN. Secret values cannot be inspected from GitHub and must not be recorded here.

Last updated: 2026-11-16 (Pakistan local date, UTC+05:00) — complete Layer 1–21 deep code review and continuation-state reconciliation

This is the canonical working context for continuing the Binance Square Write-to-Earn Agent project. Keep this file in this GitHub repository and update it as work progresses. Do not use ChatGPT Library or create a parallel Library copy.

## CURRENT CONTINUATION OVERRIDE — 2026-11-16 (COMPLETE LAYER 1–21 CODE REVIEW)

This is the latest authoritative continuation state. It supersedes older "current" instructions and checkpoints below. Historical notes are retained for traceability; do not treat their branch, worktree, file-presence, test-count or next-task statements as current unless reverified.

### Current GitHub target and exact baseline
- Repository: https://github.com/shehrozali6465372-ctrl/Binance-bot
- Active review target: PR #14 — https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/14
- PR state at review: OPEN, DRAFT, UNMERGED.
- Head branch: layer-1/module9-onchain-continuation
- Base branch: layer-1/module9-onchain-intelligence
- GitHub head SHA at review: 9c02c85124a32e81dbdbf4d96aa76d37c20b0bc9
- The review findings were written to PROJECT_CONTEXT.md through documentation-only GitHub commits. No application source, test, workflow or production files were changed by this context update. The reviewed application-code snapshot remains 9c02c85124a32e81dbdbf4d96aa76d37c20b0bc9.
- Base SHA recorded by PR metadata: 3afed37192b66c57aba2f17ba841a84a60227cda
- Review date: 2026-11-16 (Pakistan local date, UTC+05:00).
- Read-only review worktree: /tmp/binance-deepseek-verify on the Remote Desktop Commander host.
- Local worktree HEAD at review: 9c02c85124a32e81dbdbf4d96aa76d37c20b0bc9, branch layer-1/module9-onchain-continuation.
- Five local modified files were present and must be preserved: layer1/evidence_verification.py, tests/test_evidence_verification.py, tests/test_content_verification.py, PROJECT_CONTEXT.md and MODULES_11_21_GAP_REGISTER.md. They contain the additional bounded Module 11 negation/direction/unit follow-up and test/documentation updates. They are not included in the GitHub head above and must not be discarded, overwritten, or mistaken for GitHub code.
- Other existing worktrees, including /tmp/binance-continue-85351, were not modified or deleted by this review.

### Verified CI and test evidence
- Latest GitHub Actions run for the exact PR head: run 43854798245, commit 9c02c85124a32e81dbdbf4d96aa76d37c20b0bc9, SUCCESS: https://github.com/shehrozali6465372-ctrl/Binance-bot/actions/runs/43854798245
- Its actual job ran compileall and unittest discovery: 655 tests, 0 failures, 38 skipped. The 38 skips are guarded PostgreSQL integration tests requiring TEST_POSTGRES_DSN; they are not passes and do not prove PostgreSQL behavior.
- The local follow-up worktree separately recorded 660 tests, 0 failures, 38 skipped, with 65 focused evidence-verification tests passing. These counts apply to the five-file local follow-up, not the GitHub head.
- GitHub CI is a mocked/offline test run. It does not establish live Binance market ingestion, live announcement import, live DeepSeek inference on the scheduled workflow, current-head Cloudflare image generation, authenticated Binance media upload, real Square publishing, or production database persistence.
- An earlier authenticated DeepSeek/Cloudflare provider smoke run (43782717263) was on main at commit d8628e109496b2d4d937ff417edd9361baa62b80, not the current PR head. Do not use it as current-head provider acceptance evidence.
- The current PR-head image request unit tests do assert multipart/form-data, but they are mocked tests, not a live Cloudflare request.

### Review safety and scope
- The review was read-only with respect to application code. No source implementation was changed, deleted, committed, pushed, merged or deployed by the review.
- No real Binance Square post, Binance media upload, scheduled workflow dispatch, production DB write, credential/schedule change or paid resource provisioning occurred.
- DRY_RUN remains 1 in the scheduled workflow. Do not change it or enable the publisher during fixes or verification.
- There is no independently enforced PUBLISHER_ENABLED kill switch in the current code. Do not treat DRY_RUN alone as an adequate production safety architecture.
- Do not use Codex. Preserve existing local changes/worktrees. Do not use the personal browser for this project.
- The review findings below are audit findings and fix requirements, not permission to alter production behavior. Implement in isolated, reviewed changes with TDD and explicit user approval before any code commit/push beyond the explicitly authorized documentation update, merge, deploy, publisher activation or production write.

### Immediate continuation priorities
1. Fix the confirmed Module 21 PASS-versus-VERIFIED authorization contract mismatch.
2. Fix the confirmed Module 12 illegal event-lifecycle transition for non-material revisions of STALE/RESOLVED events; add SQLite and PostgreSQL parity tests.
3. Fix the Git history push/retry logic and stop persisting token-bearing remote URLs in .git/config.
4. Make scheduled-run persistence and daily quota durable before any live-publishing enablement; the current workflow only restores published_posts.jsonl and never restores agent.db.
5. Integrate Module 9 workers with the actual runtime and PostgreSQL-compatible store interfaces; do not claim Module 9 is operational merely because provider worker classes and PostgreSQL stores exist.
6. Correct Modules 2, 5, 6, 7 and 14–18 integration gaps documented in the 2026-11-16 review below.
7. Obtain a current-PR-head authenticated Cloudflare and DeepSeek provider smoke test, then separately verify Binance media upload in a safe non-publishing test path. Never publish a real Square post.
8. Reconcile this file with MODULES_11_21_GAP_REGISTER.md after the code findings are accepted; the gap register still contains older status/test checkpoints and should not override this current review.

## HISTORICAL CONTINUATION OVERRIDE — 2026-11-12 (SUPERSEDED BY 2026-11-16)

This section is retained as historical context only. Its old branch, worktree, HEAD, device, Module 9 distributed-lease next-task and file-presence details do not describe the current PR #14 review baseline. Follow the 2026-11-16 override above.

## HISTORICAL CONTINUATION OVERRIDE — 2026-11-12 (ARCHIVED CHECKPOINT)

This is an archived 2026-11-12 checkpoint only. It is superseded by the 2026-11-16 CURRENT CONTINUATION OVERRIDE at the top of this file.

### Development method
- **Do not use Codex.** The user has explicitly confirmed that the Codex usage limit is exhausted and Codex must no longer be used for this project. Do not check its quota, wait for a reset, invoke Codex, or make Codex availability a dependency.
- Continue through the authorized Remote Desktop Commander connection. GPT performs repository inspection, implementation and tests directly.
- Before editing, inspect the real repository, branch, HEAD, remotes, working tree and relevant code. Preserve every existing modification and untracked file.
- Do not run destructive Git commands (reset, clean, forced checkout, destructive stash/pop) or overwrite existing work.
- No paid infrastructure or service usage without explicit approval.

### Latest actual local repository verification
Verified on 2026-11-12 through Remote Desktop Commander:
- Device: `localhost` (ID `e87fd591-3c93-40d6-8543-95eabff1ca2f`), online at verification time.
- Working directory: `/tmp/binance-layer1-audit`.
- Actual origin remote: `https://github.com/shehrozali6465372-ctrl/Binance-bot.git`.
- Actual branch: `layer-1/module9-onchain-intelligence`.
- Actual HEAD: `113be7d1f71a719329d4d1e6b4ca3c0c37206a9b`.
- Actual Git status:
  ```text
  ## layer-1/module9-onchain-intelligence
   M PROJECT_CONTEXT.md
   M layer1/onchain_evm_worker.py
   M tests/test_onchain_evm_worker.py
  ?? .venv/
  ?? layer1/onchain_evm_store.py
  ?? layer1/onchain_worker_lifecycle.py
  ?? tests/test_onchain_worker_lifecycle.py
  ```
- These are existing working-tree changes and must be preserved. In particular, do not stage or delete `.venv/`.
- The historical handoff also mentioned `Binance-bot-staging`, but the actual local origin verified in this session is `Binance-bot`. Do not silently switch repositories; if the user later identifies staging as the intended target, clarify before changing remotes or working directories.
- The current context file itself is modified and uncommitted. Do not assume this update has been committed or pushed.

### Completed Module 9 work — do not duplicate
- Multi-network ingestion for Bitcoin, Ethereum, BNB Smart Chain, Solana and XRPL.
- Provider retry classification/backoff across EVM, Bitcoin, Solana and XRPL workers.
- Reorg handling, canonical block/slot journals, durable checkpoints and checkpoint CAS.
- PostgreSQL persistence adapters and migration runner.
- Real isolated Neon PostgreSQL 16 integration batch: 13 passed, 0 failed. This was run against the dedicated `binance_onchain_test` database on the isolated `module9-pg-integration-test` branch, not the parent staging branch.
- Latest recorded local full suite: 329 passed, 0 failed, 12 skipped. The 12 live PostgreSQL tests were separately executed in the Neon batch above. This is historical verification; rerun relevant tests after further changes.
- EVM worker store-boundary adapters in `layer1/onchain_evm_store.py` were added in the current working tree. They explicitly support the existing SQLite and PostgreSQL store classes and reject arbitrary duck-typed stores.
- Process-local lifecycle runner in `layer1/onchain_worker_lifecycle.py` was added in the current working tree. It supports explicit start/stop, periodic bounded `run_once()`, status/error reporting and exception isolation. Its focused test suite previously passed 5 tests; re-run before relying on that result.
- The lifecycle runner is **not** distributed ownership, a persistent heartbeat, a PostgreSQL lease, or multi-instance duplicate-worker protection.

### Exact next task — Module 9 distributed worker ownership
Do not redo the lifecycle runner, EVM adapter, PostgreSQL persistence layer or provider ingestion.

First inspect the existing PostgreSQL migrations, `PostgresOnChainIngestionStore`, `PostgresOnChainStore`, transaction/locking patterns, checkpoint CAS, existing agent-wide `RunLease`, any SQLite lease implementation, and related tests. Reuse an existing lease abstraction only if its scope and lifecycle semantics demonstrably fit.

Implement PostgreSQL-backed, scoped worker leases with:
1. Atomic acquisition and explicit worker identity/scope.
2. Database-time expiry where appropriate.
3. Heartbeat/renewal and safe release.
4. Owner verification and stale-owner rejection.
5. Safe takeover after expiry.
6. Monotonically increasing fencing token/generation.
7. Concurrent acquisition safety.
8. Ownership/fencing validation in the same transaction as event, journal and checkpoint commit, so a stale worker cannot commit after lease expiry or takeover.
9. Independent scopes for network/provider/monitored ingestion as appropriate; do not use one global lease.
10. Preserve SQLite development/test support. No in-memory fallback for distributed ownership.

Lease ownership and checkpoint CAS are separate protections; retain both. Event/journal/checkpoint atomicity must remain intact.

### Required TDD coverage
Test successful and competing acquisition, renewal, wrong-owner renewal, release, wrong-owner release, expired takeover, stale owner rejection after takeover, monotonic fencing generation, concurrent workers, stale-owner commit rejection, rollback consistency, and scope isolation.

Run live PostgreSQL concurrency/rollback tests only against a dedicated isolated test database. SQLite or mocks alone do not establish PostgreSQL concurrency correctness. Report clearly which PostgreSQL tests actually ran.

### Safety and release boundaries
- Never publish a real Binance Square post or activate the publisher.
- No production database writes, production credential/schedule changes, deployment, PR merge, commit or push without explicit approval.
- Do not expose secret values in logs/output.
- No unrelated module changes.
- Preserve the existing publisher and earning workflow.
- Update this canonical context after each meaningful implementation and verification milestone.

### First actions in the next continuation
1. Re-list Remote Desktop Commander devices and verify the intended device is online.
2. Reconfirm working directory, origin, branch, HEAD and full Git status.
3. Read this context and inspect the lease/transaction code listed above.
4. Run focused lifecycle tests and `git diff --check` before making changes.
5. Present a concise verified state report, then implement only the distributed lease slice.

## Repository and working branch

- Repository: https://github.com/shehrozali6465372-ctrl/Binance-bot
- Repository: `https://github.com/shehrozali6465372-ctrl/Binance-bot`
- Current implementation branch: `layer-1/module9-onchain-intelligence` (Module 9 stacked Draft PR #13)
- Module 8 implementation commit: `820a755e4a233b3fe7c812f795a9d6aba6e0a29b`
- Context update commit that introduced this file to the Layer 1 stack: `eb1919f5655d888cce28a61683846107d67bb40c` (the current context follow-up is a separate commit).
- Stacked Layer 1 PR chain: #7 → #8 → #9 → #10 → #11 → #12 → #13. PR #12 is the Module 8 base for Module 9 PR #13.
- Current branch is based on `layer-1/module5-6-candidate-intelligence` (PR #11).
- PR #2 (CMS worker) remains open/draft and unmerged; PR #3 and #6 also remain open/draft.
- PRs #7–#11 are open, non-draft and unmerged; do not merge any PR or deploy without separate explicit approval.
- The production publisher and its live workflow must remain untouched.

## Non-negotiable project rules

1. Preserve the existing working Binance Square publisher and earning workflow.
2. Never publish a real Binance Square post during tests or diagnostics.
3. Do not use the user's personal browser for this project.
4. Do not change the existing live publishing workflow, its schedule, or its credentials as part of announcement-worker work.
5. Do not invent production data, Binance article IDs, article URLs, stream replay guarantees, or successful deployment/CI results.
6. Reuse official, documented APIs and maintained open-source SDKs where practical; do not hand-roll Binance CMS authentication/signing.
7. Do not create paid infrastructure or incur costs without explicit approval of the exact resources/cost.
8. Do not reuse another project's database or Render service without explicit approval.
9. Do not stop at inspection when implementation is requested; implement and test safely, and clearly distinguish verified tests from unverified runtime behavior.
10. Keep this as the single canonical project context file in the repository. Update it rather than creating duplicate context files.

## Product and architecture goal

The product is a Binance Square Write-to-Earn Agent. The long-term architecture target is 21 modules, with Layer 1 being completed first.

The existing publishing workflow must remain isolated and unchanged while announcement intelligence is developed. The announcement stream is intended to supply fresh, verified Binance announcement evidence to Layer 1 candidate selection and content generation. The stream listener alone does not complete this integration: the Python agent must later import and consume the stored events through a separately reviewed, tested integration.

## Existing publisher and safety baseline

- Existing publisher code and workflow are already present in the repository.
- Existing publisher uses a durable SQLite idempotency ledger and protects against unsafe automatic retries after unknown publication outcomes.
- `PostPublisher.publish()` honors `DRY_RUN` before making the external POST.
- Existing production workflow was previously observed with `DRY_RUN=0`, a five-minute cron schedule, and `python main.py`. Treat that as sensitive live behavior: do not modify it in this workstream.
- Feature-branch tests must use dry-run/mocks and must not send a real Square publication request.
- There is one controlled publisher call path in `main.py` from the prior audit. Re-audit before any future publisher changes.

## Binance official CMS announcement stream

Official documentation and SDK research completed previously:

- Announcement documentation: https://developers.binance.com/en/docs/products/announcements/announcement
- General information: https://developers.binance.com/en/docs/products/announcements/general-info
- Official SDK repository: https://github.com/binance/binance-connector-js
- SDK package: `@binance/cms`, pinned to version `1.0.3`
- Required Node runtime: `>=22.12.0`
- Production WebSocket endpoint: `wss://api.binance.com/sapi/wss`
- English announcements topic: `com_announcement_en`
- API key authentication is required; the official SDK handles signed connection/authentication, connection renewal, reconnect, and re-subscription.
- Do not implement a custom signing or reconnect protocol when the official SDK supports it.

The documented DATA envelope contains a JSON-string `data` field with announcement properties such as `catalogId`, `catalogName`, `publishDate` (milliseconds), `title`, `body`, and `disclaimer`.

Important limitations:
- The documented payload does not provide a stable Binance-issued article ID or a guaranteed article-specific permalink.
- A historical replay/backfill guarantee has not been documented/verified.
- Deterministic `sourceId` and `contentHash` values in this implementation are local fingerprints, not Binance-issued IDs.
- The stored source URL points to the official announcements landing page, not a unique article permalink.
- A live listener cannot guarantee recovery of announcements missed while disconnected unless a separately verified historical source/backfill is added.

## Announcement worker implementation status

New worker code is isolated under `announcement-worker/` on the feature branch.

Files currently added:
- `announcement-worker/package.json`
- `announcement-worker/src/normalize.js`
- `announcement-worker/src/store.js`
- `announcement-worker/src/worker.js`
- `announcement-worker/test/normalize.test.js`
- `announcement-worker/test/store.test.js`
- `announcement-worker/README.md`
- `.github/workflows/announcement-worker-tests.yml`

Implementation intent:
- Consume the official SDK's English announcement stream.
- Strictly validate and normalize the documented DATA envelope.
- Compute deterministic local fingerprints for deduplication.
- Persist events to dedicated PostgreSQL tables using parameterized SQL and a unique content hash.
- Track worker state and errors.
- Keep all Square publishing code out of the worker.
- Shut down gracefully.

Current known gaps — do not describe this as production-ready:
1. No `package-lock.json` has been committed yet. Generate and commit a reproducible lockfile before deployment.
2. Verify the installed official SDK's runtime exports, including `CMS_WS_STREAMS_PROD_URL`, and actual event/error behavior using a mocked SDK or CI runtime test.
3. Lifecycle tests for the worker are not yet comprehensive.
4. Database migration/permissions need hardening. Prefer a migration/admin role to create tables, then a restricted worker role with only the required INSERT/UPDATE/SELECT permissions.
5. Existing Python agent does not yet read these PostgreSQL announcement events. Prior code audit found `_persist_layer1_market_intelligence` passes announcements as an empty list (`[]`).
6. A separate Python importer/integration is required and must be separately tested and reviewed.
7. Reconnect coverage gaps and missed events need explicit observability; SDK reconnect support does not equal guaranteed no-loss delivery.
8. The live Binance WebSocket has not yet been tested in production.
9. GitHub Actions status for the latest feature branch has not been verified. Do not claim CI is green.
10. Previous local test execution ran 12 tests (9 normalizer + 3 store) against a mirrored local copy of the implementation. This is not equivalent to running tests from the GitHub checkout, installing the actual SDK, or verifying a live stream.

## Render and database decisions

- User explicitly approved using the 3rd Render account for a separate Binance worker, but has NOT approved paid infrastructure costs/resources.
- 3rd Render account/workspace previously selected:
  - Link: `link_6ae47df96bc881918da5794d3b3747b4`
  - Workspace: `My Workspace`
  - Workspace ID: `tea-db8u854s728c73b3pr60`
  - Region: Oregon
- Existing service in that workspace: `pinterest-affiliate-marketing-agent`. It belongs to another project and must not be modified.
- No Binance-specific Render Postgres instance or worker had been created at last verification.
- Existing Neon projects inspected belong to other projects; do not reuse them for Binance without explicit instruction:
  - Primary: `billowing-grass-66503241` (Pinterest affiliate marketing agent personal browser), `frosty-waterfall-15017556` (AtoZ Product Hub), `aged-base-29683584` (UCOS)
  - 2rd neon javed: `dry-firefly-39925447` (pinterest-affiliate-marketing-agent)
- No database credentials or API secrets have been supplied in this context file. Never put secret values in this file, Git history, chat, or source code.

### Render free-tier clarification

Do not oversimplify Render pricing:
- Render Free Web Services can be used for limited web-service deployments, but they sleep after inactivity and are not a reliable always-on runtime for a persistent WebSocket listener.
- Render Background Workers are not offered on the Free instance type in the pricing information checked during this work. A persistent Background Worker therefore requires a paid compute instance.
- Render Postgres Free is temporary (30-day expiry) and is not suitable as durable production storage.
- Previously researched baseline estimate was approximately $7/month for the smallest paid Background Worker plus $6/month for the smallest paid Postgres plan (about $13/month before storage/other usage). Recheck current official pricing before any provisioning; prices can change.
- User has not approved this cost. Do not provision either paid resource until the user explicitly approves the exact cost.
- A zero-cost alternative may be explored, but it must be technically honest: a sleeping Free Web Service is not equivalent to an always-on Background Worker and must not be represented as reliable continuous stream ingestion.

## Current verified status — 2026-11-11

| Area | Verified status |
|---|---|
| Module 1 — Configuration & Orchestration | Implemented on PR #7; CI run `43010555046` passed |
| Module 2 — Market Data Intelligence | Implemented/hardened on PR #8; CI run `43012341406` passed |
| Module 3 — Binance Spot Eligibility | Implemented on PR #9; CI run `43014523334` passed |
| Module 4 — Announcement Intelligence | Python importer integration on PR #10; CI run `43016772576` passed. Live CMS/DB import remains unverified. |
| Module 5 — Trending/Narrative Intelligence | Implemented on PR #11; CI run `43018392595` passed |
| Module 6 — Candidate Discovery & Filtering | Implemented with event/trend cluster deduplication on PR #11; CI run `43018392595` passed |
| Module 7 — Relevance & Scoring | Deterministic versioned scorer exists (`layer1-relevance-v1`), but runtime scoring is explicitly deferred because calibrated evidence inputs are not all available. Do not activate guessed weights/values. |
| Module 8 — Market Analysis | Implemented on the Module 8 branch; PR #12 remains open, non-draft and unmerged. The verified base SHA for Module 9 PR #13 is `f7e6fc511e146b6bfb6f25afb0009c369d8afd4a`. Earlier CI successes apply only to the exact older SHAs listed below; do not assume they validate later heads. |
| Module 9 — On-chain Intelligence | Domain validation, five read-only scoped provider adapters, durable SQLite event/checkpoint store, shared bounded Ethereum/BNB ERC-20 ingestion worker, and Bitcoin txid:vout output normalizer implemented on PR #13. Ethereum/BNB worker paths and Bitcoin output normalization are test-verified locally; no live provider calls have been made. Bitcoin worker, production persistence and candidate integration remain incomplete. Remote CI remains unverified. |
| CMS worker PR #2 | Open/draft/unmerged; CI and prior worker tests do not prove live stream operation |
| CMS integration PR #3 | Open/draft/unmerged; no live deployment verified |
| CMS startup-race PR #6 | Open/draft/unmerged |
| Repository secrets | Names visible: `BINANCE_ANNOUNCEMENT_DATABASE_URL`, `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `GEMINI_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `SQUARE_API_KEY`. `ANNOUNCEMENT_DATABASE_URL` is NOT present. No secret values are stored here. |
| Announcement importer runtime | Missing separate read-only `ANNOUNCEMENT_DATABASE_URL`; importer reports `UNAVAILABLE_MISSING_ANNOUNCEMENT_DATABASE_URL` until configured. Do not reuse worker DB credential/role. |
| Live Binance CMS stream | Not verified in this continuation; no live connection initiated |
| Live Module 8 market history | No external live request was made in this continuation. Runtime now persists analyses from stored timestamped observations; returns remain null until real history accumulates. |
| Deployment / merge | No deployment and no merge performed |
| Real Binance Square publication during tests | None; must remain none |

### Stacked Layer 1 PR and CI status

| PR | Branch | Head SHA | CI run | Current state |
|---|---|---|---|---|
| #7 | `layer-1/module1-orchestration-hardening` | `e8f219940a220ab77a31419cbda18d390223c5cb` | `43010555046` — success | Open, non-draft, unmerged |
| #8 | `layer-1/module2-market-data-intelligence` | `892d13cc6c90c6cbcd15cd11dcf7749c3ec48fa1` | `43012341406` — success | Open, non-draft, unmerged |
| #9 | `layer-1/module3-binance-eligibility-hardening` | `4c34aeadcfc5ec1716630c8209a72f1fd7765f60` | `43014523334` — success | Open, non-draft, unmerged |
| #10 | `layer-1/module4-announcement-intelligence` | `35a181f1f99058d276ad7e58606c2fd01f681ba9` | `43016772576` — success | Open, non-draft, unmerged |
| #11 | `layer-1/module5-6-candidate-intelligence` | `8b46af4bbe0afb73d5650a1bb64a761024e53dec` | `43018392595` — success | Open, non-draft, unmerged |
| #12 | `layer-1/module8-market-analysis` | Earlier verified heads: `eb1919f5655d888cce28a61683846107d67bb40c`, `7ce44bdac0cf75f2525faacd07a33755df9f72bf` | `43020470472`, `43020622048` — success for those exact heads | Open, non-draft, unmerged; https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/12 |
| #13 | `layer-1/module9-onchain-intelligence` | `93f868d8bf9624b96e3d30ab66f7bbab26b0d92d` | No workflow runs/statuses returned; unverified | Open, Draft, unmerged; base `layer-1/module8-market-analysis`; https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/13 |

Local full-suite command on the Module 8 branch: `./.venv/bin/python -m unittest discover -s tests -v` — **133 tests passed, 0 failed**. `compileall` and `git diff --check` passed. Unit/integration fixtures are not evidence of live provider connectivity.

## Cloudflare compatibility verification (2026-11-10)

The user asked whether Cloudflare Workers can replace the proposed Render Background Worker. A source-level compatibility review was performed against Cloudflare's current official docs and Binance's official SDK source.

Verified facts:
- Cloudflare Durable Objects support outbound WebSocket clients, but outbound WebSockets do not use the Durable Object WebSocket Hibernation API.
- Cloudflare's Durable Object lifecycle documentation says an open outbound connection prevents eviction for up to 15 minutes per operation; later I/O may extend in-memory lifetime, but this is not a contractual guarantee of uninterrupted, always-on 24/7 ingestion.
- Cloudflare Workers Free limits include 100,000 requests/day and 10 ms CPU per request. Durable Objects are available on Free with SQLite storage, subject to free account limits.
- Binance's official `@binance/cms@1.0.3` package declares Node-targeted dependencies and the official common WebSocket implementation imports runtime `events` and `ws`; it also imports `http` types. The runtime `ws` dependency is designed for Node's WebSocket stack, not Cloudflare's native Worker WebSocket API.
- Therefore the existing official Binance SDK has NOT been shown compatible with Cloudflare Workers/Durable Objects. Do not deploy the current `announcement-worker/src/worker.js` to Cloudflare as-is.
- The existing worker is also Node/PostgreSQL-specific: it imports `pg`, uses `process.env`, and registers Node process signal handlers. It is not a Cloudflare Worker implementation.
- Cloudflare Durable Object SQLite could potentially replace a dedicated Postgres store for a Cloudflare-native implementation, but this does not solve the SDK/runtime incompatibility or guarantee always-on outbound stream connectivity.
- Do not hand-roll Binance authentication/signing to bypass the official SDK limitation. Any alternative transport/auth design must be based on an officially documented Binance interface and reviewed before implementation.
- A Cloudflare Worker may still be useful as a read-only authenticated API/adapter or scheduled processing component, but that is a different role from maintaining the Binance CMS WebSocket connection.

Sources reviewed:
- Cloudflare Durable Object WebSocket guidance: https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- Cloudflare Durable Object lifecycle: https://developers.cloudflare.com/durable-objects/concepts/durable-object-lifecycle/
- Cloudflare Workers limits: https://developers.cloudflare.com/workers/platform/limits/
- Cloudflare Durable Object limits: https://developers.cloudflare.com/durable-objects/platform/limits/
- Binance CMS package manifest: https://github.com/binance/binance-connector-js/blob/master/clients/cms/package.json
- Binance CMS export entry point: https://github.com/binance/binance-connector-js/blob/master/clients/cms/src/index.ts
- Binance official WebSocket implementation: https://github.com/binance/binance-connector-js/blob/master/common/src/websocket.ts
- Binance CMS WebSocket stream class: https://github.com/binance/binance-connector-js/blob/master/clients/cms/src/websocket-streams/websocket-streams.ts

Current Cloudflare decision:
- Cloudflare Workers/Durable Objects is NOT approved as a drop-in replacement for the current listener.
- No Cloudflare Worker, Durable Object, D1 database, or Cloudflare deployment has been created.
- No existing Cloudflare resources, secrets, or zones have been modified.
- Next work should prototype compatibility in an isolated branch only if a supported official SDK/runtime path is established. Otherwise retain the official Node SDK and evaluate a persistent Node runtime, with no paid provisioning until explicit cost approval.

## Required next steps (in order)

1. Continue Module 9 on `layer-1/module9-onchain-intelligence` and PR #13. Do not recreate completed domain/provider adapters or the durable ingestion foundation.
2. Wire provider-specific transfer extraction into the durable store, starting with EVM canonical block-header verification and then implementing BTC/SOL/XRPL chain-correct event identities and restart boundaries. Do not fabricate event IDs or global whale coverage.
3. Keep the open-source evaluation evidence-based. Reuse maintained, license-compatible components only when they fit the existing Python architecture; do not introduce a parallel Go/Rust indexing stack without a demonstrated need.
4. Verify remote CI for the exact current head before treating it as passed. Current GitHub workflow/status lookup returned no runs/statuses.
3. Keep Module 7 runtime scoring deferred until all dimensions have documented definitions, calibrated evidence, representative historical backtesting, and reviewed thresholds. Module 8 outputs do not automatically authorize scoring or publication.
4. Resolve CMS ingestion separately: add the distinct least-privilege read-only `ANNOUNCEMENT_DATABASE_URL` secret, verify the worker's own DB role/connection, then perform a controlled read-only staging/live smoke only with explicit authorization. Do not reuse `BINANCE_ANNOUNCEMENT_DATABASE_URL` for the importer.
5. Preserve the existing publisher workflow and daily quota. Never dispatch a publishing workflow or publish a real Square post during tests/diagnostics.
6. Do not merge, deploy, create paid resources, or modify production secrets/configuration without explicit approval.

## Context maintenance

Whenever implementation, tests, CI, infrastructure, or architecture decisions change:
- Update this file in the same feature branch/PR.
- Record exact branch, commit SHA, PR state, test command and result, and any remaining blockers.
- Clearly label facts as verified, unverified, or planned.
- Never store API keys, secrets, database URLs, tokens, or other credentials here.
- Do not create duplicate context files or copy this file to ChatGPT Library.

## Progress update — 2026-11-10

### Verified SDK contract and worker correction
- Re-read the official Binance connector-js source for @binance/cms.
- Verified ConfigurationWebsocketStreams accepts apiKey, apiSecret, wsURL, and reconnectDelay; the worker's CMS constructor configuration uses the correct property names.
- Verified WebsocketStreams.connect() resolves to WebsocketStreamsConnection.
- Verified the connection exposes .on(error), .on(close), and .disconnect().
- Verified comAnnouncementEn() returns a stream handler whose supported event is only message and whose .unsubscribe() method is valid.
- Found and fixed a real defect: the worker previously registered error on the stream handler, which does not support that event. It now registers transport error and close listeners on the connection and marks the worker DEGRADED on unexpected transport failure/closure.
- No live Binance connection was opened during this source review or code change.

### Current branch / PR / CI
- Branch: feature/binance-cms-announcement-worker
- Latest verified feature commit before this context update: 54a39277c43177c6ef1400dc7cd548649c8bb180
- PR #2: open, draft, unmerged; base layer-1/completion-hardening.
- GitHub Actions run 42718605216 for commit 54a39277c43177c6ef1400dc7cd548649c8bb180: job mocked-announcement-tests completed SUCCESS.
- That workflow currently runs the offline Node test suite only; it does not install/import the production SDK or exercise a live WebSocket. Do not interpret this as runtime integration proof.
- announcement-worker/package-lock.json is still missing. Reproducible npm ci verification remains outstanding.
- The transport-event correction is committed, but dedicated worker lifecycle tests with mocked SDK/connection are still outstanding.

### Safety / deployment
- Existing Square publisher and live publishing workflow remain untouched.
- No real Square post was published.
- No Binance CMS production connection was initiated.
- No Render/Neon/Cloudflare resources were created or modified; no paid resources were provisioned.
- PR #2 remains unmerged and no deployment was performed.

### Next work
1. Add deterministic worker lifecycle tests using injected/mock CMS connection and database pool; tests must not open a network connection or publish a Square post.
2. Generate and commit the npm lockfile using Node >=22.12, then change CI to npm ci and run the complete test suite.
3. Implement the separate Python importer only after reviewing existing Layer 1 data contracts and tests; importer must be read-only against the announcement ledger and must not change publisher behavior.
4. Add integration tests proving announcement evidence reaches Layer 1 candidate evaluation without invoking the Square publisher.
5. Keep PR unmerged and request explicit approval before any merge, deployment, or paid infrastructure.

## Progress update — 2026-11-11 — Module 8 Market Analysis

### Implementation
- Added `MarketAnalysisResult` and `MarketAnalysisEngine` in `layer1/foundation.py`.
- Calculates 1h/24h returns only from comparable timestamped observations with same canonical asset, provider and currency; baseline tolerances are 15 minutes for 1h and 60 minutes for 24h.
- Keeps CoinGecko provider-reported 24h change separate from independently calculated returns.
- Computes volume-to-market-cap ratio as a turnover proxy; does not mislabel it as relative volume.
- Supports same-provider/same-currency benchmark comparison; relative return is the difference in percentage points.
- Detects stale/non-comparable peer quotes, same-asset/same-currency provider price conflicts, history gaps at/above two hours, and potential outliers (>20% from series median).
- Keeps missing baselines/benchmarks as null/unknown. The un-timestamped 7-day sparkline is not used as hourly/daily history. The engine emits no causal hypotheses.
- Added additive `layer1_market_analyses` persistence and timestamp-ordered `get_market_history` to `Layer1Store`.
- Wired runtime analysis after each successfully normalized market observation. It reuses persisted history and a recent stored BTC observation where available; it does not make extra provider requests.
- Added `MARKET_ANALYSIS.md` with calculation rules and current data limitations.

### Verification
- Test-first cycle: `tests/test_market_analysis.py` failed on import before the engine existed, then passed after implementation.
- Full suite: `./.venv/bin/python -m unittest discover -s tests -v` — 133 passed, 0 failed.
- `./.venv/bin/python -m compileall -q main.py image_engine.py layer1 tests` — passed.
- `git diff --check` — passed.
- Runtime integration test confirms analysis is persisted and explicitly `PARTIAL` when no timestamped 24h baseline exists.
- No live market-provider request was made during this continuation; local fixtures do not prove live data coverage.
- No live CMS connection, deployment, merge, or real Binance Square publication occurred.

### Branch / commit
- Branch: `layer-1/module8-market-analysis`
- Module 8 implementation commit: `820a755e4a233b3fe7c812f795a9d6aba6e0a29b`
- Context update commit that introduced this file to the Layer 1 stack: `eb1919f5655d888cce28a61683846107d67bb40c` (the current context follow-up is a separate commit).
- Parent branch: `layer-1/module5-6-candidate-intelligence` (PR #11)
- PR #12: https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/12 — open, non-draft, unmerged. CI run `43020470472` passed for head `eb1919f5655d888cce28a61683846107d67bb40c`.

### Module 8 limitations
- Current runtime usually receives only the current CoinGecko markets observation per asset per cycle. Real 1h/24h calculations become available only after timestamped observations accumulate across cycles.
- CoinGecko's `sparkline_in_7d.price` has no per-point timestamps in this data contract and is intentionally excluded from calculated returns.
- Benchmark comparison is opportunistic; it requires a sufficiently recent stored BTC observation from the same provider and currency.
- Outlier and history-gap flags require analyst review; they do not alter or delete raw observations.
- Module 8 analysis is research context only. It does not alter Binance Spot eligibility, candidate hard gates, Module 7 deferred scoring, or publication authorization.


## Progress update — PR #12 created

- PR #12: https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/12
- Base: `layer-1/module5-6-candidate-intelligence` (PR #11).
- Head branch: `layer-1/module8-market-analysis`.
- PR state at verification: OPEN, non-draft, unmerged.
- GitHub Actions run `43020470472` completed SUCCESS for head `eb1919f5655d888cce28a61683846107d67bb40c`.
- This context update was a documentation-only follow-up; CI run `43020622048` completed SUCCESS for resulting head `7ce44bdac0cf75f2525faacd07a33755df9f72bf`. It did not alter Module 8 code or its 133-test local result.

## Progress update — 2026-11-11 — Module 9 provider decision and validation foundation

### User-approved provider scope
- User selected **Alchemy Free as primary** for Bitcoin mainnet, Ethereum mainnet, Solana mainnet, and BNB Smart Chain mainnet.
- User requested a separate free XRP Ledger provider; **Chainstack Developer Free** is the selected initial XRP candidate.
- Official plan pages checked: Alchemy Free publishes 30M CU/month and 25 requests/second; Chainstack XRPL Developer Free is listed at 3M request units/month, 25 requests/second, one node and WebSockets, with no credit card required. These are published plan limits, not an uptime/SLA guarantee.
- Chainstack's Oct 1, 2026 Extended Nodes documentation says XRPL Global Nodes retain roughly 750,000–1,500,000 ledgers (about 33–66 days), not a complete archive. An earlier Sep 16, 2026 setup guide says under six days; provider pages conflict. Runtime `complete_ledgers` from `server_info` is authoritative; adapter records it rather than assuming a fixed duration. Full-history retention needs separately configured infrastructure.
- Alchemy official docs show Bitcoin RPC/indexed UTXO APIs, Ethereum, Solana and BNB Smart Chain endpoints. BNB Smart Chain chain ID is 56.
- No Alchemy/Chainstack API keys were configured, no live provider request was made, and no external account/paid plan/secret/deployment was changed. Alchemy connector team lookup returned no team membership; `list_apps` then returned HTTP 401 (invalid/expired auth token), so no app or API key could be read or selected.
- Detailed provider choice and limitations: `ONCHAIN_INTELLIGENCE.md`.

### Initial Module 9 code
- Added `layer1/onchain.py` with a five-network provider allowlist, exact network family/chain-ID checks, canonical asset mapping validation, Binance Spot eligibility gate that requires the verified upstream identity proof and exact eligible pairs, provider/provenance checks, network-specific hash validation, chain-specific finality handling, configurable freshness thresholds and additive SQLite persistence.
- Added `layer1/onchain_providers.py` with read-only Alchemy chain-head probes and scoped transaction/transfer pages: Bitcoin address UTXO transaction pages; Ethereum `alchemy_getAssetTransfers` pages; BNB contract-scoped ERC-20 `eth_getLogs` pages; Solana finalized `getTransactionsForAddress` pages; and Chainstack XRPL validated `account_tx` pages.
- Ethereum/BNB transfer ranges are checked against the chain's finalized head. BNB Free tier `eth_getLogs` range is enforced at 10 inclusive blocks. Solana queries require finalized commitment and successful transactions. XRPL queries require fixed ledger bounds and validated pages. Bitcoin transaction confirmations are separated into CONFIRMED/PENDING/ORPHANED.
- Transfer amounts remain raw base units with explicit decimals; ERC-20 logs decode `from`, `to`, raw uint256 and preserve the reorg `removed` flag. XRPL marker is kept opaque and returned ledger range is validated.
- Important: all current methods are scoped (contract/address/account), not a complete global chain-wide whale feed. Pages are not yet checkpointed or persisted as normalized transfer events and are not wired into candidate analysis.
- Bitcoin is deliberately not labeled as deterministic `FINALIZED`: the engine requires `CONFIRMED` plus an explicitly configured minimum confirmation count. Ethereum/BNB finalized headers, Solana finalized commitment, and XRPL validated-ledger semantics are checked separately.
- The engine fails closed when freshness policy is missing; no arbitrary production freshness values are assumed.
- Persistence revalidates eligibility and mapping before insert, deduplicates identical observation IDs and rejects conflicting payload reuse.
- Added `tests/test_onchain_intelligence.py` covering eligibility, same-ticker identity mismatch, wrong network/chain ID, unsupported networks, provider allowlist, native/token mapping constraints (including XRPL issuer/currency identity), Bitcoin confirmation policy, Solana commitment semantics, pending finality, stale data, missing freshness policy and persistence idempotency.
- Added `tests/test_onchain_providers.py` for all five provider probes and scoped transfer/page methods, including EVM finality windows, BNB 10-block free-tier limit, Transfer log decoding, raw amount/decimals preservation, Bitcoin pending/orphan states, Solana finalized commitment, XRPL validated marker pagination, read-only method restrictions, JSON-RPC/REST transport validation, rate-limit normalization and endpoint credential redaction. All provider tests use deterministic in-process transport doubles; they do not call the internet.

### Verification
- Test-first RED confirmed: focused test import failed because `layer1.onchain` did not yet exist.
- Focused Module 9 domain tests: **25 passed, 0 failed**.
- Focused Module 9 provider-adapter tests: **25 passed, 0 failed**.
- Focused Module 9 domain tests: **25 passed, 0 failed**.
- Final full suite: `./.venv/bin/python -m unittest discover -s tests -v` — **183 passed, 0 failed**.
- `./.venv/bin/python -m compileall -q main.py image_engine.py layer1 tests` — passed.
- `git diff --check` — passed.
- `./.venv/bin/python -m compileall -q main.py image_engine.py layer1 tests` — passed.
- `git diff --check` — passed.
- No real blockchain provider calls were made. Unit tests do not prove provider connectivity or live chain data correctness.

### Current branch / PR
- Working branch: `layer-1/module9-onchain-intelligence`, created from Module 8 head `f7e6fc511e146b6bfb6f25afb0009c369d8afd4a` to keep PR #12 unchanged.
- Module 9 implementation is committed and pushed to the new branch.
- Draft PR #13: https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/13
- PR #13 base: `layer-1/module8-market-analysis`; head: `layer-1/module9-onchain-intelligence`.
- PR #13 is OPEN, draft, unmerged; it is intentionally not production-ready.
- Existing untracked `.venv/` is preserved and must not be deleted or staged.
- PR #12 was not modified, merged, or deployed during this continuation.

### Remaining Module 9 work
1. Add durable per-provider cursor checkpoints and normalized transfer-event persistence with unique transaction/log keys; handle reorg tombstones and canonical re-fetch/reconciliation.
2. Add read-only provider integration checks only after API credentials/endpoints are deliberately configured; redact endpoint keys and never log credentials.
3. Populate and independently verify native/token mappings from official sources; do not infer contracts from tickers.
4. Calibrate network/provider freshness and finality policy using observed data before enabling candidate evidence.
5. Evaluate the missing wallet-discovery coverage for BTC/SOL/XRPL; current methods only query known addresses/accounts.
6. Add decimal-aware transfer aggregation and explicit system whale thresholds, with no buy/sell intent claims.
7. Integrate validated on-chain evidence into the existing candidate-analysis flow without bypassing Binance Spot eligibility.
8. Keep Module 7 scoring deferred and preserve all publication safety boundaries.


### Module 9 continuation — open-source review and durable ingestion foundation (2026-11-11)

- Re-verified current branch/HEAD before editing: `layer-1/module9-onchain-intelligence`, `ba93850668da6ad9c898549c8775dff8f5d4b90c`; working tree was clean except the existing untracked `.venv/`, which remains preserved.
- Reviewed Fystack Multi-Chain Indexer (MIT, Go, multi-chain; Solana/XRP listed Beta) and Chaindexing (Apache-2.0, Rust, EVM-only, Postgres atomic checkpoints/reorg handling). Their complete runtimes are not drop-in fits for this Python service. No third-party source was copied or vendored; architecture patterns were adapted. thirdweb Insight was rejected because GitHub marks it archived.
- Added `layer1/onchain_ingestion.py`: normalized transfer event persistence, unique scoped event identities, atomic event+cursor commit, idempotent replay, conflict rejection, reorg tombstones and canonical block-hash reconciliation.
- Added `normalize_evm_transfer_log`, using `transaction_hash:log_index` as the stable event key, requiring exact verified contract scope and a separately verified canonical block hash, and preserving provider `removed=true` or block-hash mismatch as `REORGED`.
- Added `tests/test_onchain_ingestion.py`; RED import failure was observed before implementation, then focused tests passed (7 tests before the latest full-suite run).
- Integration remains intentionally incomplete: the shared bounded worker now connects Ethereum and BNB ERC-20 log extraction to normalization and atomic checkpoint commit. BTC/SOL/XRPL transfer extractors remain pending. Ethereum transfer summaries lack log index; no synthetic event identity is invented.
- XRPL durable restart should use fixed ledger bounds; opaque markers can expire. Canonical block reconciliation only accepts a caller-supplied independently verified hash and does not choose reorg depth.
- No live provider calls, credential reads, production DB changes, real Binance Square posts, PR merges or deployments occurred.


## Progress update — 2026-11-11 — Module 9 durable ingestion and open-source review

### Verified working state
- Repository: https://github.com/shehrozali6465372-ctrl/Binance-bot.
- Working directory on authorized remote device: /tmp/binance-layer1-audit.
- Branch: layer-1/module9-onchain-intelligence.
- Latest implementation commit pushed to origin: 93f868d8bf9624b96e3d30ab66f7bbab26b0d92d (feat(layer1): persist on-chain transfer ingestion checkpoints).
- Worktree after push: clean for tracked files; pre-existing untracked .venv/ remains and must not be staged/deleted.
- PR #13: OPEN, Draft, unmerged, mergeable reported true; head SHA matches 93f868d8bf9624b96e3d30ab66f7bbab26b0d92d; base is layer-1/module8-market-analysis at f7e6fc511e146b6bfb6f25afb0009c369d8afd4a. PR body updated to describe current work and limits.
- PR #12: OPEN, non-draft, unmerged; head layer-1/module8-market-analysis, SHA f7e6fc511e146b6bfb6f25afb0009c369d8afd4a. It was not changed or merged in this continuation.
- GitHub workflow-run and combined-status queries for current Module 9 head returned empty arrays. Remote CI is UNVERIFIED, not passed.

### Open-source reuse review
- Fystack Multi-Chain Indexer: public Go project, MIT license, not archived at review time. Its README lists Ethereum, BNB, Bitcoin, Solana and XRP; Solana and XRP are marked Beta. Useful patterns include restart-safe progress, catch-up/rescan, retry and reorg rollback. Its separate Go/KV/Redis/NATS/Postgres stack and known-address monitoring use case make it unsuitable as a drop-in runtime for this Python agent.
- Chaindexing: public Rust project, Apache-2.0, not archived at review time, EVM-focused. Useful patterns include canonical event identity, block-hash tracking, durable Postgres checkpoints, atomic cursor writes and reorg repair. It does not replace BTC/SOL/XRPL adapters and would add a separate Rust runtime.
- thirdweb Insight: GitHub metadata marks the repository archived; rejected as a production runtime dependency.
- No upstream code was copied or vendored. The new implementation adapts general persistence/recovery patterns inside the existing Python project. Upstream license references do not imply copied code.

### New implementation
- Added layer1/onchain_ingestion.py.
- Added tests/test_onchain_ingestion.py.
- Added NormalizedTransferEvent with network/provider/scope identity, transaction/block references, event index, sender/recipient, raw integer base-unit amount, decimals, timestamps, mapping identity, provenance and canonical status.
- Added durable SQLite per-scope cursor checkpoints.
- commit_page() inserts a complete normalized page and advances its cursor in one BEGIN IMMEDIATE transaction. A conflict/error rolls back event writes and checkpoint advancement together.
- Identical replay is idempotent. Conflicting payload reuse of the same scoped event identity is rejected. Identity uniqueness is composite across network, provider, scope and event ID.
- Reorg tombstones are retained as REORGED, excluded from canonical-only reads, and a stale canonical replay cannot resurrect a tombstoned event.
- reconcile_block() tombstones stored events at a block height when their block hash differs from a separately provider-verified canonical hash. It does not itself query providers, determine reorg depth or prove finality.
- normalize_evm_transfer_log() uses transaction_hash:log_index, requires exact mapped contract/scope and a separately verified canonical block hash. Provider removed=true or a block-hash mismatch is normalized as REORGED.
- The EVM persistence primitive is now connected end-to-end for Ethereum and BNB by the bounded worker recorded below. Bitcoin has a provider detail fetch and pure output normalizer, but no Bitcoin page/checkpoint worker yet; Solana and XRPL transfer extraction remain pending.
- Concrete transfer normalization covers EVM ERC-20 Transfer logs and Bitcoin UTXO outputs. Ethereum alchemy_getAssetTransfers summaries do not supply a log index; do not invent one. Bitcoin uses txid:vout identity and a source-address set; its bounded worker is pending. Solana/XRPL chain-specific transfer extractors remain pending.
- XRPL markers may expire; fixed ledger bounds, not opaque markers, must be the durable restart boundary.
- SQLite is a development/test foundation. A production Postgres migration and concurrency/load validation remain required before production workers.

### Verification for commit 93f868d
- ./.venv/bin/python -m unittest tests.test_onchain_ingestion -v — 9 passed, 0 failed.
- ./.venv/bin/python -m unittest discover -s tests -v — 192 passed, 0 failed.
- ./.venv/bin/python -m compileall -q main.py image_engine.py layer1 tests — passed.
- git diff --check — passed.
- Tests use deterministic local SQLite and fake provider records. No live Alchemy/Chainstack request was made; provider credentials/endpoints remain unconfigured.
- No production database, API credentials, infrastructure, publishing workflow, PR merge or deployment was modified. No real Binance Square post was published.

### Next work — continue from this exact state
1. Re-read current code/docs and inspect current Git state before editing; preserve .venv/ and do not repeat completed work.
2. Build an end-to-end bounded EVM ingestion worker: fetch exact mapped contract logs in finalized block windows, fetch canonical block headers/timestamps, verify every log's block hash, normalize and atomically persist page plus checkpoint, then resume safely after restart.
3. Define a bounded reorg reconciliation policy (explicit depth/finality rules and canonical header re-fetch); do not rely solely on a provider's removed flag.
4. Add BTC, Solana and XRPL event normalizers only after proving chain-correct stable event identity and pagination/restart semantics. XRPL must use fixed ledger ranges and recover expired markers by replaying a bounded range.
5. Migrate storage to Postgres only after choosing the actual deployment DB and validating transactions/unique constraints under concurrency. Do not provision paid resources without explicit approval.
6. Connect validated, mapped events to candidate analysis only after decimal-aware aggregation, deduplication and explicit thresholds are implemented. Preserve Binance Spot eligibility as a hard gate; on-chain evidence is corroborative only.
7. Keep PR #13 Draft until live read-only provider verification, full ingestion integration, database migration and candidate integration are independently reviewed. Never merge/deploy or publish a real Binance Square post without explicit approval.

## Progress update — 2026-11-11 — Bounded BNB EVM ingestion worker

### Verified repository state before implementation
- Repository: https://github.com/shehrozali6465372-ctrl/Binance-bot.
- Working directory: /tmp/binance-layer1-audit.
- Branch: layer-1/module9-onchain-intelligence.
- HEAD at start: ee50839065cf92bdd536d37b8b7d30f562fff237; origin/layer-1/module9-onchain-intelligence matched this exact SHA.
- Tracked working tree was clean. Existing untracked .venv/ was present and preserved.
- PR #13 was verified OPEN, Draft, unmerged. PR #12 was verified OPEN, non-draft, unmerged. PR #12 was not modified.
- GitHub combined-status and workflow-run queries for ee50839 returned empty arrays; CI remains UNVERIFIED.

### Implementation added
- Added layer1/onchain_evm_worker.py, orchestrating existing verified mappings, Alchemy BNB eth_getLogs, canonical block headers, normalize_evm_transfer_log() and OnChainIngestionStore.commit_page().
- Added OnChainStore.list_verified_mappings() to read only previously accepted/verified mapping records and revalidate their mapping data.
- Added read-only provider methods for BNB finalized height and exact canonical block-header retrieval; the BNB allowlist now includes eth_getBlockByNumber.
- Worker requires explicit initial block heights per mapping, a bounded run size, and explicit reorg lookback. Alchemy BNB log requests remain capped at 10 blocks.
- Worker verifies page provider/network/scope/range/finality metadata, fetches canonical headers for every block in each scanned range, journals those hashes atomically, and derives block timestamps from those headers.
- Each complete fixed block range commits normalized events and the next-block cursor atomically. Empty ranges are checkpointed only after a successful, validated provider response.
- Bounded retries cover timeout, network, rate-limit and HTTP 5xx provider errors. Malformed provider data and scope mismatches fail closed.
- Reorg lookback re-fetches canonical headers including previously empty blocks, tombstones affected events, rewinds the durable cursor to the earliest changed block and replays that finalized range.
- commit_page() gained an opt-in allow_recanonicalized path used only by the worker after independent header verification. It permits a re-included transaction/log identity to become canonical again only when stable transfer fields match; default store replay behavior still prevents stale canonical pages from resurrecting tombstones.

### Scope limitations
- The complete EVM paths now cover **Ethereum and BNB Smart Chain ERC-20** through eth_getLogs. Ethereum alchemy_getAssetTransfers summaries still omit log index and are not used to create stable event identities. Bitcoin output normalization now uses txid:vout; the bounded Bitcoin worker is pending. Solana/XRPL transfer normalization remains pending.
- The worker is callable orchestration, not yet a scheduled/always-on worker process. No credentials, endpoints, live requests or production services were configured.
- Reorg repair is bounded by the explicitly configured lookback; deeper reorgs require a separately controlled wider rescan.
- SQLite remains a development/test backend. PostgreSQL migration and real concurrency tests remain pending.
- BTC, Solana and XRPL transfer normalizers remain pending. Candidate integration, aggregation and whale thresholds remain pending; no thresholds were guessed.

### Verification
- New worker tests cover mapped-contract scope, normalized transaction/log identity, bounded range checkpointing, restart resume, timeout retry, no checkpoint advancement on provider failure, bounded reorg detection/rewind/replay and rejection of invalid worker bounds.
- Focused Module 9 test group (worker, ingestion store, provider adapters, domain validation): **68 passed, 0 failed**.
- Full suite: ./.venv/bin/python -m unittest discover -s tests -v — **201 passed, 0 failed**.
- No real Binance Square publication or earning workflow was triggered. No live blockchain provider request was made.
- `./.venv/bin/python -m compileall -q main.py image_engine.py layer1 tests` — passed.
- `git diff --check` — passed.
- Implementation commit: `5afd3f7c864c8959290d00fb89efe657e15cab73` (`feat(layer1): add bounded BNB EVM transfer ingestion worker`).
- Only the eight intended project/source/test files were staged and committed. The existing untracked `.venv/` was not staged, modified or deleted.
- The branch was committed locally and then pushed to the existing Module 9 feature branch; final remote PR/CI verification is recorded in the session handoff.

### Exact next work
1. Finish static checks and inspect the complete diff; preserve .venv/.
2. Run a final full suite after any code correction.
3. Commit and push only to layer-1/module9-onchain-intelligence if the current remote/permissions remain valid.
4. Recheck PR #13 remains Draft and remote CI status; do not merge or deploy.
5. Next implementation after this worker: add Ethereum eth_getLogs Transfer extraction with the same stable log identity and finalized canonical-header checks, then build provider contract/live read-only verification once credentials are deliberately configured.

## Post-push verification — 2026-11-11

- Module 9 worker implementation commit: 5afd3f7c864c8959290d00fb89efe657e15cab73.
- Context/PR follow-up commit already pushed before this note: f19d03f50220273fa2febda57e6335a63be6bba1.
- Confirmed origin/layer-1/module9-onchain-intelligence points to f19d03f50220273fa2febda57e6335a63be6bba1 before this context-only follow-up.
- PR #13: OPEN, Draft, unmerged; head branch layer-1/module9-onchain-intelligence at f19d03f50220273fa2febda57e6335a63be6bba1; base layer-1/module8-market-analysis at f7e6fc511e146b6bfb6f25afb0009c369d8afd4a.
- PR #12: OPEN, non-draft, unmerged; head remains f7e6fc511e146b6bfb6f25afb0009c369d8afd4a; base remains layer-1/module5-6-candidate-intelligence at 8b46af4bbe0afb73d5650a1bb64a761024e53dec. No PR #12 changes were made.
- Latest Module 9 combined commit-status query returned an empty statuses array and the workflow-run query returned an empty workflow_runs array. Remote CI is still UNVERIFIED; do not report it as passed.
- Final local full test suite: 201 passed, 0 failed. compileall and git diff --check passed.
- The tracked worktree is clean. Existing untracked .venv/ remains present and was never staged or modified.
- No live blockchain provider calls, secrets, infrastructure, real Binance Square posts, merge or production deployment were used/performed.


## Progress update — 2026-11-11 — Ethereum EVM ingestion

### Verified starting point
- Repository: https://github.com/shehrozali6465372-ctrl/Binance-bot.
- Working directory: /tmp/binance-layer1-audit.
- Branch: layer-1/module9-onchain-intelligence.
- Starting HEAD: 8b1ccf6c871f1cfce53ad3c1fcba56032cd920d1; tracked working tree clean.
- Existing untracked .venv/ preserved.
- PR #13 remained OPEN, Draft and unmerged. PR #12 remained OPEN, non-draft and unmerged. Remote CI queries returned empty arrays; CI remains unverified.

### Implementation added
- Added Ethereum eth_getLogs to the Alchemy read-only method allowlist.
- Added fetch_ethereum_finalized_height() with chain ID 1 verification and the execution-layer finalized block tag.
- Added fetch_ethereum_block_header() with exact returned-height/hash and timestamp validation.
- Added fetch_ethereum_erc20_transfer_logs() scoped to one exact mapped contract and the canonical ERC-20 Transfer event topic. It verifies chain ID, finalized height, block range and every decoded log's block/transaction/log-index identity.
- Refactored EVM log decoding into a shared network-aware decoder; BNB behavior remains covered by its existing tests.
- Extended the existing EvmTransferIngestionWorker to discover verified mappings on Ethereum and BNB, dispatch to each network's existing provider methods, enforce network-specific finality references, and reuse the same atomic event/block-hash/checkpoint storage.
- Both networks use the same stable event identity: transaction_hash:log_index. Ethereum alchemy_getAssetTransfers summaries are not used to manufacture missing log indices.
- Ethereum request windows are capped at 10 blocks. This is confirmed by Alchemy's current official Ethereum eth_getLogs docs, which list 10 blocks for Free tier; no paid-plan capability is assumed.
- Canonical block hashes and timestamps are fetched independently and journaled atomically with events and the durable checkpoint. Bounded reorg detection, rewind and replay are shared across both EVM networks.

### Verification
- Provider adapter tests: 30 passed after Ethereum provider methods were added.
- Combined EVM worker/provider tests: 41 passed after the additional wrong-finality checkpoint-protection test.
- Full suite: 208 passed, 0 failed.
- compileall and git diff --check passed.
- Ethereum worker tests cover exact mapped contract, finalized-range log ingestion, stable event identity, restart resume, empty-block reorg detection/replay, and fail-closed rejection of a page carrying the wrong finality semantics.
- Full suite, compile checks and diff checks were rerun after code review: 208 tests passed, compileall passed and git diff --check passed.
- No live Alchemy requests or credentials were used. No real Binance Square post or earning workflow was triggered.

### Remaining limits
- Ethereum/BNB EVM worker is still callable orchestration, not a scheduled/always-on production service.
- Provider contract tests use deterministic fake JSON-RPC responses; live endpoint compatibility, quota behavior and operational reliability remain unverified.
- SQLite remains a development/test backend; PostgreSQL migration and real concurrency tests remain pending.
- Bitcoin, Solana and XRPL transfer normalizers remain pending.
- Candidate integration, decimal-aware cross-provider aggregation, deduplication and calibrated whale thresholds remain pending. No threshold was invented.

### Exact next task after this update
1. Complete final full-suite/static verification, inspect the full diff and preserve .venv/.
2. Commit and push only to layer-1/module9-onchain-intelligence if the remote head is unchanged and permissions permit.
3. Recheck PR #13 remains Draft and PR #12 remains unchanged; remote CI may remain unverified.
4. Next implementation after Ethereum: assess and implement Bitcoin address-history normalization only where stable txid/output identity, amount and address evidence are actually available. Do not invent output indexes or treat transaction summaries as individual transfers.

## Post-push verification — Ethereum EVM ingestion — 2026-11-11

- Implementation commit: efcb0e7252ea697f3192902be757c0bf2887e01c (feat(layer1): add Ethereum ERC20 log ingestion).
- The remote feature branch was checked before push and still pointed to 8b1ccf6c871f1cfce53ad3c1fcba56032cd920d1. A normal fast-forward push succeeded; the remote branch then matched efcb0e7252ea697f3192902be757c0bf2887e01c.
- PR #13 remains OPEN, Draft, unmerged; head efcb0e7252ea697f3192902be757c0bf2887e01c, base layer-1/module8-market-analysis at f7e6fc511e146b6bfb6f25afb0009c369d8afd4a.
- PR #12 remains OPEN, non-draft, unmerged; head f7e6fc511e146b6bfb6f25afb0009c369d8afd4a and base 8b46af4bbe0afb73d5650a1bb64a761024e53dec. No changes made to PR #12.
- GitHub combined status returned an empty statuses array and workflow-run query returned an empty workflow_runs array for efcb0e7. CI remains UNVERIFIED.
- Final full local suite: 208 passed, 0 failed. Focused EVM worker/provider tests: 41 passed, 0 failed. compileall and git diff --check passed.
- Tracked working tree clean after commit. Existing untracked .venv/ remains present, not staged, not modified and not deleted.
- No live Alchemy request, credentials, production database, paid resource, production deployment, PR merge, Binance Square publication or earning workflow was used/performed.
- The Bitcoin address-history/transaction-detail assessment is complete and a txid:vout output normalizer is implemented in the progress entry below. Next task is the bounded Bitcoin page/checkpoint worker; do not fabricate output indexes or sender attribution.


## Progress update — 2026-11-11 — Bitcoin UTXO output normalization

### Evidence and implementation boundary
- Alchemy's Bitcoin address-history endpoint supports fixed from/to block-height filters and page-based retrieval, with details=txs.
- The documented GET /api/v2/tx/{txid} response exposes vin and vout arrays. Output records include output index n, satoshi value strings and decoded addresses; inputs expose prior outpoint references and decoded source addresses.
- The address-history summary alone is not treated as a transfer event. The adapter now retrieves full transaction details by exact txid and rejects a mismatched returned txid.
- Added from_addresses and from_addresses_complete to the generic normalized event model while preserving backward-compatible defaults for existing EVM events and old JSON payloads.
- Added normalize_bitcoin_transaction_outputs(): one event per addressable vout, stable event ID txid:vout, raw satoshis, 8 decimals, exact block reference checks, explicit minimum-confirmation threshold, canonical block-hash comparison, and monitored-address scope validation.
- Multi-input transactions retain the full decoded input-address set. A single from_address is only populated when that set is complete and contains exactly one address. Coinbase events have no fabricated sender.
- Outputs with no address or multiple destination addresses are skipped instead of assigned a guessed destination.

### Verification
- Bitcoin normalizer tests cover txid:vout identity, satoshi amounts, multiple input addresses, source completeness, coinbase sender absence, duplicate output index rejection, monitored-address membership, block mismatch reorg tombstones, explicit confirmation threshold and storage round-trip.
- Provider tests cover full transaction detail retrieval and txid mismatch rejection.
- Focused ingestion/provider tests: 50 passed, 0 failed. Full suite: 219 passed, 0 failed. compileall and git diff --check passed.
- No live Alchemy request or credential was used.

### Remaining Bitcoin work
- No bounded Bitcoin ingestion worker has been implemented yet. The worker must be seeded with explicitly monitored addresses and verified Bitcoin asset mapping; this provider is not a global whale feed.
- Use fixed block-height windows, page checkpoints, explicit minimum confirmations, independently fetched canonical block headers and atomic event/block-hash/checkpoint commits.
- Reconcile reorgs by re-fetching canonical block hashes; a provider's orphaned flag alone is not enough.
- Do not guess the confirmation threshold. The worker constructor must require it explicitly.
- Independent Bitcoin address checksum validation is not yet implemented; normalized addresses are sourced from Alchemy's isAddress/address metadata.

### Exact next task
Build the bounded Bitcoin address-history ingestion worker on the existing ingestion store. It must process fixed block windows, resume page-by-page safely, fetch each tx detail by txid, normalize all addressable outputs, verify canonical headers and commit each page plus checkpoint atomically. Require explicit address seeds and a caller-supplied minimum-confirmation threshold. Do not claim network-wide discovery.

## Post-push verification — Bitcoin UTXO output normalizer — 2026-11-11

- Implementation commit: 7918fa3457d968342116c94c0ef6b495b93634b5 (feat(layer1): normalize Bitcoin UTXO transaction outputs).
- Remote feature branch was checked before push and still pointed to e491242845c0c5863cb7f67baa4a2c0795cbb782. Normal fast-forward push succeeded; remote branch then matched 7918fa3457d968342116c94c0ef6b495b93634b5.
- PR #13 remains OPEN, Draft and unmerged; head 7918fa3457d968342116c94c0ef6b495b93634b5, base layer-1/module8-market-analysis at f7e6fc511e146b6bfb6f25afb0009c369d8afd4a.
- PR #12 remains OPEN, non-draft and unmerged; head f7e6fc511e146b6bfb6f25afb0009c369d8afd4a and base 8b46af4bbe0afb73d5650a1bb64a761024e53dec. No changes were made to PR #12.
- GitHub combined status returned an empty statuses array and workflow-run query returned an empty workflow_runs array for 7918fa3. CI remains UNVERIFIED.
- Final local full suite: 219 passed, 0 failed. Focused ingestion/provider tests: 50 passed, 0 failed. compileall and git diff --check passed.
- Tracked working tree clean after commit. Existing untracked .venv/ remains present, not staged, not modified and not deleted.
- No live Alchemy request, credentials, production database, paid resource, deployment, PR merge, real Binance Square post or earning workflow was used/performed.
- Next exact task: implement the bounded Bitcoin address-history ingestion worker using explicit monitored address seeds, fixed block-height windows, caller-supplied minimum confirmations, independently fetched canonical headers, page-level atomic checkpointing and bounded reorg recovery. Do not guess a confirmation threshold or claim global whale coverage.

## Progress update — 2026-11-11 — Bounded Bitcoin address-history worker

### Implementation
- Added `layer1/onchain_bitcoin_worker.py` to orchestrate verified native BTC mapping lookup, explicit monitored address seeds, fixed block-height windows, page-based address history, exact txid detail fetch, Bitcoin output normalization and atomic SQLite page/checkpoint commits.
- Added read-only Alchemy provider helpers for Bitcoin tip height and independently resolved canonical block headers via getblockcount → getblockhash → getblockheader.
- Caller must provide `minimum_confirmations`, explicit per-mapping monitored addresses, explicit start blocks, bounded max blocks/page size and reorg lookback. The worker computes its safe scan ceiling from the configured confirmation threshold; no confirmation policy is guessed.
- Checkpoint cursor preserves fixed from/to range and next page; events, canonical block hashes (including empty blocks) and page cursor commit in one existing `commit_page` transaction. A completed page range clears active range fields and advances next_block.
- Re-fetches canonical headers in the bounded lookback and in any partially paginated active range. A changed header tombstones affected events and restarts the range from page 1. Changed provider totalPages metadata also forces a page-1 replay instead of continuing a stale page offset.
- Provider errors are retried only for bounded retryable categories (timeouts, network errors, rate limits and HTTP 5xx); invalid data/scope mismatches/insufficient confirmations fail closed.
- Address-history summaries are not transfer events. Full transaction details are fetched by exact txid and only output records with stable provider-supplied vout indexes and one decoded destination address become events. No arbitrary sender attribution is added.

### Verification
- New worker tests: 7 passed. Bitcoin worker/provider/normalizer focused suite: 58 passed, 0 failed.
- Full repository suite: 228 passed, 0 failed.
- `compileall`: passed. `git diff --check`: passed.
- Deterministic local fixtures only; no live Alchemy request/credential used.
- No real Binance Square post or earning workflow; no deployment, merge, paid infrastructure or production DB mutation.

### Limitations and next task
- Bitcoin worker is explicitly address-scoped, not network-wide discovery. Operator-supplied seeds are mandatory.
- Confirmation threshold, start height, block-window size and reorg lookback are caller policy. Reorg recovery is bounded by configured lookback plus active page range.
- SQLite remains local/test persistence; Postgres migration/concurrency validation, live provider verification, scheduling, metrics/alerts and operational runbook remain outstanding.
- Next continue with Solana transaction/event extraction assessment, only normalize records where stable transaction/signature and instruction identity, mint, raw amount, source/destination and canonical slot evidence are all present. Do not invent instruction indexes or use aggregate account history summaries as transfer events. Assess reusable open-source code before implementing; preserve current architecture and never publish a real Binance Square post.

## Solana extraction assessment — 2026-11-11 (research only; no implementation)
- Official Alchemy `getTransactionsForAddress` supports address-scoped full transaction + metadata pages, opaque pagination tokens and up to 100 full transactions per request (100 CUs documented). Response entries include slot and transaction index; transaction metadata may contain inner instructions, pre/post token balances and loaded lookup-table addresses.
- Solana official `@solana/transaction-introspection` resolves static + lookup-table account indexes and walks outer/inner CPI instructions with exact trace coordinates. Generated Token Program clients decode standard instructions. This is TypeScript tooling, not a direct drop-in for this Python service.
- Individual token transfer events cannot be reconstructed safely from aggregate token-balance deltas alone. A single transaction can contain multiple transfers; identity needs signature + exact outer/inner instruction coordinates.
- A correct parser must handle legacy/v0 transactions, loaded addresses, inner CPI, Token + Token-2022 program IDs, verified mint mapping, raw integer amount/decimals, failed transactions and missing metadata. Native SOL needs separate System Program instruction decoding; net lamport balance deltas are insufficient because fees/rent/account lifecycle also change balances.
- Alchemy `getBlock` can return finalized block identity for a slot with transactionDetails=none (documented 40 CUs), suitable for an independent blockhash journal.
- Exact fixed slot-filter schema and pagination stability for the current `getTransactionsForAddress` endpoint remain unverified. Do not implement a worker using assumed filter semantics.
- No Solana normalizer/worker or extra package was added. Next: verify slot filters/pagination; compare maintained Python parsing options against a minimal Node interop boundary; write tests for legacy/v0, lookup tables, outer/inner Transfer and TransferChecked, Token-2022 and stable instruction identity; then implement only if exact evidence is available.
- Official references: Alchemy getTransactionsForAddress and getBlock; Solana transaction introspection, RPC JSON structures and SPL token transfer instructions (URLs recorded in `ONCHAIN_INTELLIGENCE.md`).

## Solana SPL token worker progress — 2026-11-11

### Implemented
- Added fixed inclusive slot filters to Alchemy `getTransactionsForAddress`; query uses finalized full transactions, desc ordering, `encoding=json`, `maxSupportedTransactionVersion=1` and tokenAccounts=balanceChanged. Provider validates each record remains in requested slots and requires transactionIndex for fixed-slot queries.
- Added finalized slot/header/produced-slot provider helpers: genesis-checked getSlot(finalized), getBlocks(finalized) and getBlock(finalized, transactionDetails=none).
- Added narrow Python `normalize_solana_token_transfer_instructions` for SPL Token Program Transfer and TransferChecked. It resolves static + loaded lookup addresses, outer and inner CPI instructions, exact u64 base-unit amounts, mint/decimals, source/destination token accounts and wallet owner evidence. Stable identity includes signature + exact outer/inner trace index.
- Added `layer1/onchain_solana_worker.py`: explicit address seeds and start slots, bounded fixed slot windows, opaque cursor checkpointing, descending slot/transaction-index validation, cursor-loop rejection, finalized headers, exact transaction normalizer, and atomic page+checkpoint+slot-journal commits.
- Added dedicated slot journal table recording both produced and skipped slots without fabricating block hashes or timestamps. Reorg reconciliation detects changed hashes and produced/skipped transitions, tombstones affected events and replays from the earliest changed slot; active page ranges are checked before resuming.
- Unsupported native SOL and Token-2022 mappings are deliberately skipped. Token-2022 is not enabled until extension-aware transfer-fee/hook instruction handling is implemented. No transfer is inferred from aggregate balance deltas.
- Official MIT `@solana/transaction-introspection` v8.6.0 (legacy/v0/v1 + ALT + inner CPI support) was reviewed but not added because it requires a Node/Kit runtime boundary in this Python service; the in-repo decoder is deliberately limited to known SPL Token instruction layouts. No external source code was copied.

### Cost and coverage limits
- Alchemy docs list getTransactionsForAddress full page = 100 CUs, getBlock = 40 CUs, getBlocks = 10 CUs. Worst-case 100-slot range with 100 produced blocks costs about 4,010 CUs per address plus 100 CUs per full transaction page; reorg lookback incurs more header reads. Seed count and slot window must remain conservative.
- The worker is address-seeded, not network-wide. Native SOL and Token-2022 not supported. Produced slots with missing blockTime fail closed. Owner-address attribution requires token balance owner metadata.
- Reorg recovery is bounded by configured lookback plus active range. SQLite remains the local/test store; Postgres migration/concurrency, scheduler lifecycle, metrics/alerts, runbook and live provider verification remain outstanding.
- All tests are deterministic local fixtures; no live Alchemy call or credentials used.

### Exact next task
Assess XRPL payment/issued-currency extraction and transaction history pagination using Chainstack's validated ledger boundaries. Only normalize actual validated Payment/issued-currency transfer records with exact transaction hash, ledger index/hash, delivered amount, currency/issuer and account-side evidence. Do not treat balance changes as synthetic payments or infer missing delivered amounts. Reuse maintained open-source code only after checking license, support and Python integration. Preserve all non-negotiable rules and never publish a real Binance Square post.

## Solana worker verification — 2026-11-11
- Full repository suite: 260 passed, 0 failed.
- Focused Solana normalizer + worker + provider suite: 65 passed, 0 failed.
- compileall and git diff --check passed.
- No live Alchemy calls, credentials, deployment, production DB mutation, PR merge or real Binance Square post.
- Current exact implementation scope: base SPL Token Program Transfer/TransferChecked only; native SOL and Token-2022 skipped; address-seeded finalized slot windows with opaque page cursor, per-slot produced/skipped journal and bounded reorg recovery.
- Next exact task: XRPL validated ledger/account_tx extraction assessment and payment normalization. Only real Payment/issued-currency delivered transfers with exact validated ledger, tx hash, delivered amount/currency/issuer and account-side evidence; no balance-delta synthetic events.

## Latest Solana implementation commit — 2026-11-11
- Commit `ca567bc7ea64f278bf2564191333a3f460918cd1` adds the bounded Solana SPL token address-history worker and normalizer, fixed slot filtering, finalized header verification, produced/skipped slot journal and reorg-safe pagination.
- Successfully pushed to `origin/layer-1/module9-onchain-intelligence` after remote SHA guard. Branch local/remote head verified at this commit before this context-only update.
- Full suite 260 passed, focused Solana/provider suite 65 passed, compileall and git diff --check passed.
- Tracked tree clean; existing untracked `.venv/` preserved.


## Progress update — 2026-11-11 — XRPL issued-currency ingestion

### Verified starting point
- Repository: `shehrozali6465372-ctrl/Binance-bot`; workdir `/tmp/binance-layer1-audit`.
- Branch `layer-1/module9-onchain-intelligence`; local HEAD and fetched remote branch both matched `e72c594b6e6524ceb71997ac1f9b8a960bd54832` before edits.
- Tracked working tree was clean. Existing untracked `.venv/` was preserved and remains untracked.
- PR #13 was OPEN, Draft, unmerged, head `e72c594b6e6524ceb71997ac1f9b8a960bd54832`, base `layer-1/module8-market-analysis` at `f7e6fc511e146b6bfb6f25afb0009c369d8afd4a`.
- PR #12 was OPEN, non-draft, unmerged and unchanged, head `f7e6fc511e146b6bfb6f25afb0009c369d8afd4a`, base `layer-1/module5-6-candidate-intelligence` at `8b46af4bbe0afb73d5650a1bb64a761024e53dec`.
- GitHub head status initially had no commit statuses; workflow run query showed `Phase 1 Safety Tests` run `43053159016` completed successfully. This single workflow does not prove full release readiness.

### Reuse assessment
- Reviewed `xrpl-py` (`XRPLF/xrpl-py`): native Python XRPL SDK, Python >=3.10, ISC license, provides RPC clients/models and address codecs. Not added because this narrow read-only path uses the existing JSON-RPC transport and direct validated JSON metadata; signing/serialization APIs are unnecessary. No external source copied or vendored.
- Official XRPL docs confirm `delivered_amount` is the field to use for actual Payment delivery, including partial payments; metadata changes are final only in validated ledgers. `account_tx` is account-scoped and supports opaque marker pagination. General marker docs warn that markers are undefined and may expire after about 10 minutes; fixed ledger bounds are therefore the durable recovery boundary.

### Implementation
- Added `normalize_xrpl_payment()` in `layer1/onchain_ingestion.py`.
  - Accepts only validated successful `Payment` transactions.
  - Checks the provider record's exact transaction hash and ledger index against the raw record, requires transaction Account/Destination and monitored account side evidence.
  - Requires exact `delivered_amount` currency and issuer matching the verified mapping; missing, unavailable, malformed, zero, negative or non-finite values fail closed.
  - Never substitutes requested `Amount` and never converts RippleState/account balance changes into synthetic transfers.
  - Stable event ID is transaction hash; event includes validated ledger index/hash and TransactionIndex where supplied.
  - Converts issued IOU decimal strings to integer raw amount using the mapping's configured decimal scale only when exact. XRPL normalized mantissa/exponent protocol bounds are enforced; no rounding.
- Added `ChainstackXrplReadOnlyAdapter.fetch_ledger_header()` in `layer1/onchain_providers.py`. It requests one exact ledger, requires `validated=true`, matching ledger index, exact 32-byte ledger hash and integer close time, then converts Ripple-epoch close time to Unix time.
- Added `layer1/onchain_xrpl_worker.py`.
  - Requires verified issued-currency mappings, explicit monitored accounts, explicit start ledgers, bounded ledger range/page count/page size and bounded reorg lookback.
  - Reads the current validated head and uses fixed ledger bounds for all `account_tx` pages.
  - Stores opaque marker as checkpoint only; detects marker loops. On an RPC error with a persisted marker, resets and replays the same fixed range from page one.
  - Fetches validated ledger headers for every ledger in the bounded range (including empty ledgers), commits ledger-hash journal, normalized events and page checkpoint atomically.
  - Rechecks completed lookback and active partial range; changed ledger hash tombstones affected events and rewinds/restarts the range.
  - Events are account-scoped. If both sender and destination accounts are monitored, the same Payment can exist in both scopes; downstream aggregation must deduplicate by `(mapping_id, transaction_hash)`.
- Native XRP, CheckCash, AccountDelete, AMM/trustline balance-delta extraction and network-wide account discovery remain unsupported. XRPL classic-address checksum validation is not yet implemented; current seed checks validate Base58 shape/length only, not checksum. Only mapped issued-currency Payments are normalized.

### Tests added
- `tests/test_xrpl_normalization.py` — Payment/partial Payment, actual delivered amount, missing/unavailable/malformed amount, exact issuer/currency, account-side evidence, transaction/ledger identity, exact decimal scaling and precision/range.
- `tests/test_onchain_xrpl_worker.py` — fixed ledger range, page marker resume after timeout, expired marker replay, repeated marker rejection, validated-record requirement, active/completed range reorg rewind and no checkpoint advancement on malformed records.
- `tests/test_onchain_providers.py` — exact validated XRPL ledger header, Ripple close-time conversion, unvalidated/wrong-index rejection.

### Verification
- Focused XRPL normalizer/worker/provider/mapping suite: 89 passed, 0 failed.
- Full repository suite: 286 passed, 0 failed.
- `compileall` and `git diff --check` passed.
- Deterministic local fixtures only; no live Chainstack calls.

### Operational limitations
- No live Chainstack request or credential was used; provider JSON-RPC compatibility, actual history coverage/retention and real endpoint pagination remain unverified.
- Worker fetches each ledger header in its bounded range; this can be RPC-intensive per monitored account. Keep range sizes and seeds conservative pending measured live quotas/cost.
- Account history is not network-wide whale discovery. Multiple account scopes can surface the same transaction; aggregation dedupe is mandatory.
- SQLite remains local/test storage. Postgres migration/concurrency validation, scheduler lifecycle, metrics/alerts, runbook, live provider verification, decimal-aware aggregation and candidate-analysis wiring remain outstanding.
- No real Binance Square post/earning workflow, deployment, PR merge, production DB mutation, secret change or paid infrastructure action occurred.

### Exact next task
Implement PostgreSQL schema/migration and real PostgreSQL transaction/concurrency verification for the verified mapping store and ingestion/checkpoint/block journals. Preserve SQLite local/test support. Then implement supervised worker scheduling/leases, retries, metrics/alerts, retention and runbook. PR #13 remains Draft until live provider, PostgreSQL and operational readiness evidence is complete.


## Progress update — 2026-11-11 — cross-network transfer aggregation

### Starting state verified
- Repo `shehrozali6465372-ctrl/Binance-bot`, branch `layer-1/module9-onchain-intelligence`.
- Before implementation, local and remote HEAD both matched `386d54f3ff2e54414e2597e9dd6b252455aae228`; tracked tree clean. Existing untracked `.venv/` preserved.
- PR #13 remained open, Draft, unmerged; PR #12 remained open and unchanged.

### Implementation
- Added `layer1/onchain_aggregation.py`:
  - `OnChainTransferAggregator` requires verified `OnChainStore` mappings, exact threshold configuration for every verified mapping and a current `EligibilityDecision` per canonical asset ID.
  - Uses the mapping store's most recent persisted ACCEPTED observation and existing `OnChainIntelligenceEngine.validate()` to re-check mapping/Spot eligibility evidence. Binance `exchangeInfo?permissions=SPOT`, exact symbol, CoinGecko identity proof and freshness are mandatory.
  - Requires the canonical ingestion store's block journal and verifies each event's block hash against exact `(network, provider, scope, height)` evidence. Missing/mismatched journal entries are rejected.
  - Checks network-specific transaction hash, block hash and stable event ID formats; verifies EVM/Bitcoin event-index suffix equals event_index; Solana signature+outer/inner trace coordinate stays in event_id and event_index remains null; XRPL Payment event_id equals transaction hash.
  - Deduplication key `(network_id, mapping_id, event_id)` collapses XRPL same Payment across account scopes, Bitcoin same vout, EVM same log and Solana same instruction across scopes. Different EVM logs or Solana instructions in one tx remain distinct. Duplicate economic/canonical payload conflict raises rather than selecting one.
  - Converts raw integer amount strings with exact Decimal scaling by mapping decimals. No float arithmetic, rounding, USD conversion or cross-network quantity summation.
  - Groups output by `(asset_id, network_id, mapping_id)` and applies explicit positive threshold per mapping. `qualifying_network_summaries`/`qualifying_assets` surface only threshold-qualified summaries. Asset rollup counts observations/networks but does not add quantities across chains, because wrapped/bridged representations can double-count flows.
  - Source/destination metrics are generic address counts, not wallet/whale claims. Incomplete Bitcoin input attribution does not become a fabricated single sender. No buy/sell intent or publication action.
- Added `OnChainStore.get_latest_accepted_observation()` and `OnChainIngestionStore.list_all_events()`.
- No automatic arbitrary threshold, price oracle, buy/sell inference, or candidate scoring change was added. This remains a callable deterministic aggregation API until candidate integration is separately tested and reviewed.

### Tests
- Added `tests/test_onchain_aggregation.py` covering cross-network BTC (8 decimals) vs wrapped ERC-20 BTC (18 decimals), explicit per-mapping thresholds, XRPL account-scope dedupe, preservation of separate EVM logs and Solana instructions in one transaction, stable event/index validation, block journal enforcement, Binance Spot eligibility and freshness, stale/future/noncanonical events, Bitcoin incomplete input attribution, conflicting duplicates, and missing/invalid threshold config.
- Focused aggregation tests: 16 passed, 0 failed.
- Final full repository suite after all aggregation refinements: 302 passed, 0 failed.
- `compileall` and `git diff --check` passed after final edits.

### Remaining Module 9 work
1. Push this aggregation commit using a remote-SHA guard and update PR #13 body without changing Draft status.
2. PostgreSQL schema/migration and real PostgreSQL concurrency/atomicity tests. SQLite remains local/test storage.
3. Scheduler/worker lifecycle, leases, retry budgets, metrics/alerts, retention and runbook.
4. Live provider verification, quota/latency measurement, XRPL address checksum validation and chain-specific data coverage review.

### Non-negotiables
- Never publish real Binance Square posts or invoke earning workflow in tests.
- Do not deploy, merge PR #13/#12, change secrets, mutate production DB or provision paid infrastructure without explicit approval.
- Preserve `.venv/` untracked and all previous module work.


### Final aggregation verification addendum
- Focused aggregation suite: 16 passed, 0 failed.
- Full repository suite: 302 passed, 0 failed.
- `compileall` and `git diff --check` passed.
- Aggregator refuses arbitrary in-memory injection: each supplied event must exactly match the persisted event record and its canonical block journal entry. `aggregate_store()` reads only canonical persisted rows.
- The test suite emitted only its existing dry-run publisher log (`Would publish ... no network POST attempted`); no real Binance Square request was performed.


## Progress update — 2026-11-11 — candidate-analysis corroboration integration

### Implementation
- Added deterministic `NetworkTransferSummary.summary_id` SHA-256 based on mapping/network, exact event IDs, canonical block hashes, amount, threshold and time bounds. `TransferAggregationResult` now carries `generated_at`.
- Extended `Candidate` with `onchain_transfer_summary_ids`; `CandidateDiscoveryFilteringEngine.build()` accepts optional `onchain_aggregation=TransferAggregationResult`.
- Candidate builder rechecks result age, current Binance Spot eligibility source, canonical CoinGecko identity proof, proof freshness, summary asset/symbol, explicit threshold arithmetic and event time bounds before attaching summary IDs.
- On-chain evidence is corroborative only. It does not change candidate ID, candidate discovery state, relevance score weights or publication authority. On-chain-only data cannot create a candidate. Ineligible/stale/unverified candidate eligibility does not receive on-chain refs.
- `Layer1Store.save_candidate()` persists summary IDs under `evidence_refs_json.onchain_transfer_summaries`.
- Added optional `onchain_aggregation_by_asset` injection to `_run_once_impl`, `run_once` and `_persist_layer1_market_intelligence`. Default is `None` and summary status is `NOT_PROVIDED`; no on-chain provider worker is auto-started. An external orchestrator must supply already validated result objects. Main only attaches summary refs; it does not grant trading/publishing authority.

### Tests
- Added `tests/test_onchain_candidate_integration.py`: candidate identity stability, on-chain-only non-discovery, ineligible/stale proof rejection, nonmatching asset/threshold filtering, malformed aggregation result rejection, evidence persistence, unchanged relevance score and optional main-pipeline injection validation.
- Added real aggregator-to-candidate end-to-end test in `tests/test_onchain_aggregation.py`.
- Focused candidate integration: 10 tests passed. Focused aggregation: 17 tests passed. Combined focused: 27 passed.
- Final full repository suite after candidate integration: 313 passed, 0 failed. `compileall` and `git diff --check` passed.

### Remaining Module 9 work
1. Final full suite/static verification, then guarded commit/push and PR #13 body update while preserving Draft.
2. PostgreSQL schema/migration and real PostgreSQL transaction/concurrency/atomicity tests for mappings, events, block journals and checkpoints. SQLite remains local/test.
3. Supervised worker scheduling/lifecycle, leases, retry budgets, metrics/alerts, retention and runbook.
4. Live provider verification, quotas/latency measurements, XRPL classic-address checksum validation and independent chain-specific coverage review.

### Runtime boundary
- Normal `run_once()` continues with `onchain_aggregation_by_asset=None`; no automatic on-chain worker startup or live RPC occurs. On-chain candidate corroboration only activates when an external orchestrator passes current validated aggregation results keyed by canonical CoinGecko asset ID.
- No buy/sell inference, order placement, candidate-only discovery or Binance Square publishing authority was added.

### Final GitHub handoff — 2026-11-11
- Latest implementation commit: `cb1a118887da08efdfe9d436dd550ddd35b5c8e0` (`feat(layer1): attach on-chain corroboration to candidates`). Local and fetched remote branch matched after push.
- PR #13: OPEN, Draft, unmerged; head `cb1a118887da08efdfe9d436dd550ddd35b5c8e0`; base `layer-1/module8-market-analysis` at `f7e6fc511e146b6bfb6f25afb0009c369d8afd4a`.
- PR #13 GitHub Actions run `43070205665` (`Phase 1 Safety Tests`): completed SUCCESS; job `mocked-safety-tests` completed SUCCESS. Commit status endpoint has no separate status contexts; workflow run is the verified CI result.
- PR #12 remains OPEN, non-draft, unmerged and unchanged; head `f7e6fc511e146b6bfb6f25afb0009c369d8afd4a`, base `8b46af4bbe0afb73d5650a1bb64a761024e53dec`.
- Full repository suite: 313 passed, 0 failed. Focused aggregation + candidate integration: 27 passed. `compileall` and `git diff --check` passed.
- Tracked working tree clean after push; `.venv/` remains untracked and untouched.
- No production deployment, PR merge, live on-chain RPC, secrets change, production database mutation, paid infrastructure, or real Binance Square post was performed.

### Branch-head correction after documentation handoff
- Latest branch HEAD after the documentation-only handoff commit: `88ebe86394dfac109170515866ee50154cc81eb8`.
- PR #13 head is therefore `88ebe86394dfac109170515866ee50154cc81eb8` (not the immediately preceding implementation commit `cb1a118887da08efdfe9d436dd550ddd35b5c8e0`).
- The implementation commit's Phase 1 Safety Tests run `43070205665` passed; the documentation-only handoff commit's run `43070324062` also passed (`mocked-safety-tests`).
- PR #12 remains unchanged/open/unmerged.

## Module 9 PostgreSQL persistence progress — 2026-11-11

- Verified actual local/remote branch head 9b2f1e636ea6298901de05aaee63415e72856e19 on layer-1/module9-onchain-intelligence. PR #13 remains OPEN/Draft/unmerged; PR #12 remains OPEN/non-draft/unmerged and unchanged. Tracked tree was clean before edits; the existing untracked .venv/ remains untouched.
- Added layer1/onchain_postgres.py with explicit-DSN PostgreSQL implementations PostgresOnChainStore and PostgresOnChainIngestionStore plus a versioned migration runner with migration SHA-256 checksums and a transaction-level advisory lock. Store construction does not auto-run migrations or consult production environment variables.
- Added layer1/migrations/postgresql/0001_onchain_storage.sql for verified mappings, accepted observations, transfer events, checkpoints, canonical block journal and Solana slot journal. Database constraints enforce scoped uniqueness, event idempotency, mapping/observation foreign keys and slot consistency.
- PostgreSQL ingestion commit uses a transaction-scoped scope advisory lock, row-locked checkpoint and expected-cursor compare-and-swap. Events, canonical journal changes and checkpoint revision are atomic. Conflicting block hashes, stale checkpoint writes and conflicting identity reuse fail closed. Reorg reconciliation takes the same scope lock.
- SQLite remains supported. Its store gained optional expected-cursor/scope checks and fail-closed canonical block/slot conflict handling. EVM, Bitcoin, Solana and XRPL workers now pass their persisted checkpoint snapshot and (network, provider, scope) identity on each commit.
- Optional Psycopg 3 driver is documented in requirements-onchain-postgres.txt and shared with the existing importer requirements. No SQLAlchemy/Alembic dependency was added.
- Added tests/test_onchain_postgres.py guarded by TEST_POSTGRES_DSN. The integration suite refuses non-local hosts and any database name other than binance_onchain_test. SQLite regression tests cover stale checkpoint and canonical block conflict behavior.
- Verification: full suite 326 passed, 0 failed, 10 skipped; compileall passed; git diff --check passed; migration SQL parsed as 11 PostgreSQL statements; Psycopg 3.3.8 import verified in /tmp without modifying .venv/.
- PostgreSQL runtime/concurrency remains unverified: no TEST_POSTGRES_DSN was available. An isolated PostgreSQL 16 cluster could not initialize because the sandbox's shmget syscall returned Function not implemented. No real PostgreSQL migration or multi-connection integration test ran.
- Changes are local and uncommitted. No push, PR update, merge, deployment, production database mutation, secret change, live provider RPC or real Binance Square post occurred.
- Exact next task: execute the guarded integration suite against a dedicated local/test PostgreSQL 16+ database. Fix any real-server failures, rerun full tests and static checks, then perform a final diff review before a guarded commit/push. Keep PR #13 Draft and PR #12 unchanged. Continue afterward with worker lifecycle, leases, retries, observability, retention/runbook and chain-specific verification.



### Final verification addendum — 2026-11-11
- Final full repository suite after the last storage/test changes: **327 passed, 0 failed, 10 skipped**. The skipped tests are the guarded PostgreSQL integration cases; TEST_POSTGRES_DSN is not configured.
- Final compileall and git diff --check both passed.
- PostgreSQL SQL grammar parser accepted all 11 migration statements.
- Canonical block and Solana slot journal timestamps are now immutable when the canonical hash/produced identity is unchanged; a timestamp-only mutation fails closed. A focused SQLite regression test covers the block timestamp invariant.
- The PostgreSQL integration DSN guard was tightened: it requires the dedicated binance_onchain_test database, an explicit local hostname or Unix socket, no remote hostaddr and no PostgreSQL service alias.

### Neon staging-branch validation — 2026-11-12
- Located the existing Binance bot Neon account and project `Binance-bot-staging` (`orange-glade-36037611`), PostgreSQL 16, branch `staging` (`br-rough-mud-az28jpxs`), database `binance_bot_staging`. Existing announcement tables were inspected read-only and left unchanged.
- Created isolated copy-on-write branch `module9-pg-integration-test` (`br-falling-bread-azl8rggt`) from the staging branch. A 0.25 CU read-write compute was provisioned for the test branch; the account rejected changing the suspend interval, so the project default remains in effect.
- Applied the 11 statements from `0001_onchain_storage.sql` only to the isolated test branch, in a transaction. PostgreSQL 16.15 accepted the DDL. Verified all six Module 9 tables, their primary/unique/foreign/check constraints and indexes through PostgreSQL catalogs. The parent `staging` branch was not modified.
- Re-ran the full local unittest suite: **327 passed, 0 failed, 10 skipped**; the 10 PostgreSQL adapter integration tests remain skipped because their safety guard only permits a dedicated local `binance_onchain_test` DSN. `compileall` and `git diff --check` passed.
- This verifies the migration DDL against a real Neon PostgreSQL 16 server, but does **not** verify the Python Psycopg adapter, multi-connection concurrency or rollback against Neon. Do not claim full PostgreSQL integration readiness yet.
- No existing announcement rows/tables were changed, no on-chain fixture rows were inserted, no provider RPC or Binance publishing was invoked, and no schema was applied to the parent staging branch.
- Next: review/fix the adapter and test harness, then run the integration suite against this dedicated Neon test branch using an explicit, narrowly scoped test-only DSN path. Preserve the local-only guard by default; do not point tests at the parent staging branch or production.

### Final Neon PostgreSQL integration update — 2026-11-12
- Created database `binance_onchain_test` on the isolated `module9-pg-integration-test` branch; it is separate from the inherited `binance_bot_staging` database and from the parent `staging` branch.
- Ran the guarded Psycopg integration suite against that exact Neon branch endpoint and dedicated test database. The first 11-test run reported 10 passing and one failure because the canonical-block conflict test expected `ValueError` while the adapter intentionally raises the more specific `CanonicalBlockConflict`. The assertion was corrected. The corrected canonical-conflict, explicit-reorg-scope guard, and reorg replay tests then passed **3/3** against Neon. The other eight tests had passed in the first run. The entire Neon integration suite has not yet been rerun as one batch after the assertion correction; treat the combined result as strong but not final batch verification.
- The Neon run verified the real migration runner, mapping/observation round-trip and idempotency, atomic event+journal+checkpoint writes, rollback on a mid-transaction timestamp error, competing checkpoint writers, duplicate-event retry, canonical block conflict, reorg replay and Solana slot journal behavior.
- Added a fail-closed requirement that PostgreSQL `reconcile_block()` must receive explicit provider and scope so it always takes the same transaction advisory lock as page commits. All four workers already pass those identities.
- Final local full suite after this change: **328 passed, 0 failed, 11 skipped**. The 11 skipped are the PostgreSQL integration tests when no `TEST_POSTGRES_DSN` is set; the dedicated Neon run above executed them separately. `compileall` and `git diff --check` passed.
- The dedicated Neon test database contains only isolated synthetic test fixtures. The inherited announcement database/tables and the parent staging branch were not modified. The test branch has a 0.25 CU compute; the account rejected changing its suspend interval, so its default behavior remains.
- No commit, push, PR update, merge, deployment, production database mutation, provider RPC or real Binance Square publication occurred.
- Next: rerun the complete Neon integration suite once as a single clean batch, inspect/fix any issues, then perform final code/diff review. Do not promote the migration to the parent staging branch without explicit approval.

### Complete Neon PostgreSQL integration batch — 2026-11-12
- Re-ran the entire PostgreSQL integration module against the isolated Neon PostgreSQL 16.15 branch and dedicated `binance_onchain_test` database using an explicit exact-host allowlist plus TLS. Result: **13 tests passed, 0 failed** in 122.899 seconds. This includes the adapter contract test and all 12 live PostgreSQL integration tests.
- The earlier canonical-block test assertion mismatch is corrected to expect `CanonicalBlockConflict`; the dedicated reorg reconciliation API now requires explicit provider and scope.
- Tightened PostgreSQL Solana journal validation: a Solana slot journal record is accepted only when the checkpoint identity itself is `solana-mainnet`, and the slot network must equal that identity. Added a regression test for cross-network slot injection. The transaction rollback test now injects a bad canonical block timestamp after event insertion, proving rollback without using an invalid cross-network slot.
- The PostgreSQL test harness remains local-only by default. A remote endpoint is accepted only when `TEST_POSTGRES_ALLOWED_HOST` exactly matches the DSN hostname, database is exactly `binance_onchain_test`, TLS mode is required/verified, and no hostaddr or service alias is present.
- Final local repository suite: **329 passed, 0 failed, 12 skipped**. The 12 skips are the live PostgreSQL integration cases when `TEST_POSTGRES_DSN` is absent; the same 12 were executed in the dedicated Neon run above. `compileall` and `git diff --check` passed.
- No source was committed or pushed. `.venv/` remains pre-existing and untracked; it was not modified or staged. PR #13 remains Draft and PR #12 remains unchanged. No parent staging schema changes, production DB writes, live chain RPC, deployment, or Binance Square publishing occurred.
- PostgreSQL persistence/transaction adapter now has live integration evidence, but this does not by itself make the whole Module 9 service production-ready. Remaining work includes worker lifecycle/supervision, distributed ownership/leases, retry classification and backoff, observability, retention/runbook, and chain-specific validation decisions.


### Final local recovery and verification — 2026-11-12
- Recovered the existing uncommitted Module 9 PostgreSQL persistence work from the original development working tree; no reimplementation of completed modules was performed.
- Completed provider retry integration across EVM, Bitcoin, Solana and XRPL workers. Retry classification is limited to timeout, network errors, HTTP 429 and HTTP 5xx; bounded exponential backoff honors a capped Retry-After value. Retry delay configuration rejects non-finite values.
- XRPL normalization and aggregation fixtures now use checksum-valid classic addresses, matching the production validation boundary.
- Full repository unittest suite: **336 passed, 0 failed, 12 skipped**. The skips are the guarded PostgreSQL live integration cases when TEST_POSTGRES_DSN is absent from the ordinary suite.
- Dedicated isolated Neon PostgreSQL 16 integration batch: **13 passed, 0 failed** in 203.386 seconds, using the dedicated binance_onchain_test database, exact-host allowlist and TLS. No parent staging database was targeted.
- Focused provider/ingestion/XRPL/aggregation regression batch: **86 passed, 0 failed**. compileall and git diff --check passed.
- The pre-existing .venv/ directory was not staged. The temporary test DSN file is test-only and will be removed after the integration run.
- No real Binance Square post, provider RPC, production database mutation, deployment, PR merge or publishing workflow activation occurred.
- Module 9 remains not production-ready: distributed ownership/leases, observability/alerts, retention/runbook, and live provider verification still require separate work and approval. A process-local, explicit-start lifecycle runner was added in `layer1/onchain_worker_lifecycle.py`; it supervises bounded `run_once()` cycles, records run/error status and supports graceful stop, but does not provide distributed ownership or persistent heartbeat.

### Canonical EVM header verification checkpoint — 2026-11-12

- Reviewed the current Ethereum/BNB provider, ingestion worker and durable-store architecture against the requested bounded slice. The slice is already implemented in the checked-out branch; no duplicate adapter, event store or journal was added.
- Existing verified behavior: Ethereum and BNB use scoped `eth_getLogs` Transfer extraction; finalized-height and chain-ID checks are enforced; each scanned block gets an independently fetched canonical header with exact height, hash and timestamp validation; every log is compared with that header before normalization; canonical block hashes/timestamps, normalized events and the next cursor commit atomically; bounded lookback re-fetches headers and reconciles reorgs.
- TDD result: no new RED test was added because there was no safe unimplemented behavior in this slice to drive. Existing regression tests already cover the required failure modes and pass without code changes.
- Focused verification: `./.venv/bin/python -m unittest tests.test_onchain_providers tests.test_onchain_ingestion tests.test_onchain_evm_worker -v` — **75 passed, 0 failed**.
- Full repository verification: `./.venv/bin/python -m unittest discover -s tests -v` — **336 passed, 0 failed, 12 skipped**. The skips are guarded PostgreSQL live integration tests because `TEST_POSTGRES_DSN` is not configured. No live RPC or publishing was used.
- Precise blocker for further implementation in this slice: `EvmTransferIngestionWorker` currently requires the concrete SQLite `OnChainStore` and `OnChainIngestionStore`, while the branch also contains separate PostgreSQL store implementations. Making the EVM worker consume PostgreSQL stores would be a new store-interface/adapter and contract-test slice, not canonical-header verification; it is unsafe to guess that interface here.
- Existing untracked `.venv/` was preserved and untouched. No source/test changes, commit, push, PR update, deployment, production DB/secret change or Binance Square publication occurred in this continuation.

### EVM worker store boundary — 2026-11-12

- Added `layer1/onchain_evm_store.py` with explicit `EvmMappingStoreAdapter` and `EvmIngestionStoreAdapter` boundaries. The adapters accept only the existing SQLite or PostgreSQL store classes; arbitrary duck-typed objects are rejected.
- Verified the EVM worker-reachable contracts: `list_verified_mappings()` for the mapping store, and `get_checkpoint()`, atomic `commit_page()`, `get_block_hash()` and scoped `reconcile_block()` for the ingestion store. Both backends have matching call signatures and preserve their own transaction, expected-cursor CAS, canonical-header journal, and reorg semantics through delegation.
- Added boundary tests proving SQLite compatibility, PostgreSQL implementation compatibility without a live database, and rejection of undeclared duck types. Existing SQLite EVM ingestion/restart/reorg tests remain passing.
- No schema/API expansion was required. No live chain RPC, production database/secret access, commit, push, deployment, PR change or Binance Square publication occurred. `.venv/` was preserved.


## 2026-11-14 — Codex-free implementation continuation

### User directive
- User explicitly instructed: do not use Codex for this project. All further implementation is performed directly through ChatGPT's authorized GitHub tools and the authorized remote environment, never through Codex.

### Branch and preservation
- Created isolated continuation branch `layer-1/module9-onchain-continuation` from `layer-1/module9-onchain-intelligence` to avoid modifying PR #13 or the local working tree.
- PR #13 remains open, Draft and unmerged. Its head at branch creation was `3afed37192b66c57aba2f17ba841a84a60227cda`.
- No commit was made to `main`; no merge, deployment, production configuration, credential, schedule or publisher activation was performed.

### Implemented on the continuation branch
- Added `layer1/deepseek_client.py`: direct HTTPS client to the official DeepSeek Chat Completions API, using the standard library, schema validation, timeout, response-usage parsing, bounded error reporting, and no credential logging.
- Added `tests/test_deepseek_client.py`: deterministic fake-transport tests for endpoint/payload, response parsing, malformed response, empty content, HTTPS-only configuration and secret redaction.
- Added `MODULES_11_21_GAP_REGISTER.md`: copied the locked Module 11–21 contract text into a traceability register. This is documentation only; it does not assert those modules are implemented.
- GitHub creation commits: DeepSeek client `ff58c82b12534339c1cf2524a9a9f94998cedf0b`; tests `13b99be87f70208914d44adcae0db58d2a2c9a1d`; gap register `6ae7c3095f267061e48fe129952e8b42f501b162`.

### Verification status and limitations
- The GitHub connector was used to write the files. The new code has **not yet been executed**, because the local Codex-free test environment and GitHub Actions run are not verified.
- The existing application still instantiates the legacy `GeminiGenerator`; this new DeepSeek client is not yet wired into the runtime.
- Workflow file `.github/workflows/run_bot.yml` currently references Gemini credentials/model and has `DRY_RUN: "1"`. Do not modify workflow, secrets or activation without explicit approval.
- Cloudflare Workers AI image generation has not been implemented or runtime-verified.
- Modules 11–21 remain unverified/partial until each is mapped against code and tested. No real Binance Square post has been made.
- Do not report the added client as full completion of Module 15, and do not report all 21 modules complete.


## 2026-11-14 — DeepSeek runtime verification and workflow compatibility checkpoint

### Exact continuation state
- Continuation branch: `layer-1/module9-onchain-continuation`.
- Verified branch HEAD before this checkpoint's test/documentation changes: `bbb71fc6056afa5a998fddf602eb46a0c02ae779` (`feat(ai): wire Layer 1 content generation to DeepSeek`).
- This branch is separate from PR #13. PR #13 remains open, Draft and unmerged.
- Verification was performed in a new isolated worktree at `/tmp/binance-deepseek-verify`. The pre-existing `/tmp/binance-layer1-audit` worktree, including its modified and untracked Module 9 files, was preserved. The unrelated `/root/Binance-bot` CMS-worker worktree and its three modified files were also preserved.
- No worktree was switched, reset, cleaned, or overwritten to obtain this verification checkout.

### DeepSeek integration findings
- `main.py` defines `Config` with `deepseek_api_key`, `deepseek_model`, temperature/top-p/output-token settings, and reads `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL`.
- `DeepSeekGenerator` is wired into both existing runtime entrypoints (`main()` and `main_loop()`). Its `decide()` and `generate()` methods call the direct `layer1.deepseek_client.DeepSeekClient`.
- Missing `DEEPSEEK_API_KEY` fails closed: `decide()` returns an empty ranking and `generate()` returns empty content. A failed/empty Phase 2 generation reaches the existing early return before the publisher call. No alternate AI provider is invoked.
- Runtime comments, prompts, and log messages now identify DeepSeek. The legacy database field `gemini_decision` and output key `gemini_rank` remain unchanged for schema compatibility. `SCORE_DEEPSEEK_REVIEW` is the active threshold name; `SCORE_GEMINI_REVIEW` remains a compatibility alias.
- Updated the stale application Config test from Gemini to DeepSeek fields. Updated the malformed-client-response test to assert the actual client contract: invalid response structure returns `None` rather than propagating a `ValueError`.
- Added `tests/test_deepseek_generator.py` covering Config environment loading, mocked `decide()`, mocked `generate()`, missing-key fail-closed behavior, no legacy-provider fallback, and the empty-content-before-publisher guard.
- No live DeepSeek API request was made; all generator/client tests use deterministic mocks/fake transport.

### Fresh verification evidence
- Focused DeepSeek + foundation + market-analysis + announcement-importer/runtime + publisher-safety batch: **144 passed, 0 failed**.
- Python compile check for `main.py`, DeepSeek client, and touched tests: passed.
- `git diff --check`: passed.
- Full repository discovery was also attempted: **346 tests ran, 1 failed, 48 errored, 12 skipped**. The failures are outside the DeepSeek-focused batch and predominantly originate in Module 9 fixture/observation freshness (`ONCHAIN_OBSERVATION_STALE`); one on-chain intelligence fixture returned `UNAVAILABLE` where it expected `ACCEPTED`. The 12 PostgreSQL integration tests were skipped because `TEST_POSTGRES_DSN` was absent. These failures have not been changed as part of Task 1 and must not be represented as a green full suite.

### Workflow/configuration mismatch — documented, not changed
- `.github/workflows/run_bot.yml` still supplies `GEMINI_API_KEY` and `GEMINI_MODEL`; current application Config reads `DEEPSEEK_API_KEY` and `DEEPSEEK_MODEL`. Therefore the workflow does not currently supply the API key/model fields expected by the DeepSeek runtime.
- Workflow still explicitly sets `DRY_RUN: "1"`. This safety setting was not changed.
- Safe compatibility plan only: keep the workflow, secrets, schedule, permissions, and activation untouched until the owner approves a separate change. Before any approved workflow migration, verify the intended official DeepSeek model ID and secret availability, then propose replacing the workflow environment mapping with `DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}` and an explicit `DEEPSEEK_MODEL`; do not add Gemini fallback or expose/modify secret values. Keep `DRY_RUN: "1"` throughout test and staging validation. No workflow_dispatch or scheduled workflow was triggered during this checkpoint.

### Safety
- No Codex use.
- No live DeepSeek request, live RPC, production database write, production credential/secret/schedule change, publisher activation, Binance Square publication, commit to `main`, merge, or deployment.
- Task 1 verification changes were committed as `65a0aa2224883aeef2c02b5968dc91519fbbda6e` (`test(ai): verify DeepSeek runtime integration`) and the checkpoint was committed as `a7fe1368b7a8dd5a67abe4e2371efcd46f28cde` (`docs: record DeepSeek verification checkpoint`). Both commits were pushed to `layer-1/module9-onchain-continuation`; remote HEAD was verified at `a7fe1368b7a8dd5a67abe4e2371efcd46f28cde`. No other branch was modified.
- Module 15 is not declared complete, and Modules 10–21 are not declared complete. Proceed to Modules 10–14 only after the DeepSeek test changes are reviewed and recorded on the continuation branch; do not repeat completed Modules 1–9.


## 2026-11-14 — Module 10 Event Intelligence Graph implementation checkpoint

### Architecture contract inspected
- Read the exact locked contract at section 5.10, "Module 10 — Event Intelligence Graph".
- Existing Modules 4–6 already supplied announcement source/revision provenance, canonical event grouping, trend copy clustering, candidate event-cluster references and persisted source records. These were reused; no duplicate discovery or trend-clustering implementation was created.
- The verified gap was the absence of a unified typed graph/relationship view across the existing evidence records.

### Minimal implementation
- Added `layer1/event_graph.py` with deterministic `GraphEntity`, `GraphRelationship`, `EventGraph` and `EventIntelligenceGraphEngine`.
- Uses existing Layer1 SQLite persistence and standard-library data structures only. No graph database, third-party graph framework, microservice or paid infrastructure.
- Entity types include asset, project, announcement, event, source, market observation, on-chain observation, trend signal and duplicate cluster. Stable IDs are SHA-256 derived from typed canonical IDs.
- Every relationship requires typed endpoints, a timestamp, a bounded deterministic confidence weight, a state (`CONFIRMED`, `POSSIBLE`, `UNKNOWN`) and one or more evidence entity references. Graph validation rejects dangling endpoints/evidence and duplicate IDs.
- Confidence weights are deterministic evidence-strength weights, not calibrated probabilities or LLM confidence.
- Causal edge types are rejected; the graph does not infer that a market move was caused by an announcement or transfer.
- Copied reports are clustered only on exact content-hash equality. Their original announcement/trend nodes and publisher/provider ancestry remain in the graph; identical content is one content lineage, not independent corroboration.
- Announcement revisions are linked only when the source provides a stable provider ID. Fingerprint-only CMS records remain uncorrelated. Where a stable provider revision changes the canonical event, the old event is linked to the updated event; unrelated event fingerprints remain separate.
- `rebuild_from_store()` reconstructs announcements/revisions, market observations and trend signals from existing Layer1 persisted source tables. Module 9 data is a separate store: callers supply its persisted raw observations with matching accepted `OnChainValidationResult` records or candidate-accepted network aggregation summary references. Unvalidated raw on-chain observations remain `POSSIBLE`; unqualified aggregation summaries are rejected.
- Project nodes and evidence-backed additional relationships are supported, but no project entity is fabricated where the repository has no verified project source record.
- `EventGraph.to_dict()` exposes the relationship set and duplicate-cluster references as a JSON-safe graph view.
- Integrated graph construction into `_persist_layer1_market_intelligence()`. The Layer1 runtime summary now returns `event_graph` and a compact `event_graph_summary`; full graph payload is omitted from routine log lines. Empty source coverage is explicitly reported as `AVAILABLE_EMPTY`.

### Acceptance tests and verification
- Added 11 deterministic Module 10 tests in `tests/test_event_graph.py` covering stable IDs, entity types, project relationships, evidence traceability, confidence/timestamps, causal-edge rejection, exact copied-content clustering and source ancestry, stable-provider updates versus fingerprint-only records, distinct events, Module 9 accepted/unqualified summary handling, and deterministic reconstruction from persisted records.
- Extended the existing Layer1 runtime persistence test to assert that the graph is built and returned by the live application pipeline (using mocked market/provider inputs; no live RPC).
- Focused suite after Module 10 changes: **155 passed, 0 failed** across DeepSeek, event graph, Layer1 foundation, market analysis, announcement importer/runtime and publisher-safety tests.
- Python compile check: passed.
- `git diff --check`: passed.
- No live RPC, production database write, Binance Square publication, workflow trigger, credential change, deployment or merge was performed.

### Module 10 status
- Implementation and deterministic acceptance tests are verified in the isolated continuation worktree.
- The graph is a reproducible derived view of persisted source evidence, not a separately persisted graph database. Module 9 observations/aggregation summaries must be supplied from the existing Module 9 persistent source boundary as described above.
- No production-readiness claim is made. The previously observed full-suite Module 9 freshness/fixture failures remain outside this module change and have not been hidden or modified.
- Implementation commit `289f214b3992c21f7e0340b7847f9026f25d8a17` (`feat(layer1): add evidence-backed event intelligence graph`) and context checkpoint commit `048e14d130dd907a7139a3529113cc3bdd67534e` (`docs: record Module 10 graph verification`) were pushed to `layer-1/module9-onchain-continuation`. Remote HEAD was verified at `048e14d130dd907a7139a3529113cc3bdd67534e`; the isolated worktree is clean.

## 2026-11-14 — Module 11 Evidence Verification Engine checkpoint (PARTIAL)

### Exact continuation state
- Repository: `shehrozali6465372-ctrl/Binance-bot`.
- Active branch: `layer-1/module9-onchain-continuation`.
- HEAD before this Module 11 working-tree change: `cceebd5680c70d5e34d4bd0de4035008f7b45481` (`docs: confirm Module 10 checkpoint push`).
- Worktree: `/tmp/binance-deepseek-verify`. The earlier Module 9 audit worktree was not reset, cleaned or overwritten.
- Module 11 changes are local and uncommitted. No commit or push was made; no other branch was touched. PR #13 remains open, Draft and unmerged.
- The locked architecture file was read at section 5.11. Its contract was not modified.

### Implemented
- Added `layer1/evidence_verification.py` and `tests/test_evidence_verification.py`.
- Added typed `EvidenceRecord`, `Claim`, `ClaimVerificationResult` and `ClaimRegistry` models with deterministic SHA-256 IDs.
- Added deterministic verification states: `VERIFIED`, `CORROBORATED`, `UNVERIFIED`, `CONTRADICTED`, and `STALE`.
- Added source adapters for existing announcement revisions, market observations, trend signals, accepted Module 9 observations and threshold-qualified Module 9 aggregation summaries. Canonical asset and mapping identities, source family, publisher, content hash, lineage and separate publication/update/observation/event times are retained.
- Exact subject, asset ID, mapping ID, value, unit, timeframe, event time and expected status are checked. Source publication/update time after the claim observation cutoff is rejected; stale evidence does not pass.
- Independent-source grouping merges shared source-family, content-hash and lineage identifiers. Syndicated copies do not count as independent. Conflicting accepted evidence is retained on both sides.
- High-impact claims require an explicit freshness policy, a primary source and at least two independent source groups. Estimates, analyst interpretations, hypotheses and unclassified claims cannot pass as confirmed facts.
- Added append-only `ClaimRegistryStore` snapshots in the existing Layer 1 SQLite store.
- Integrated source-record claim registry construction and persistence into `_persist_layer1_market_intelligence()`.
- Research-package assembly creates sentence/semicolon claim drafts, marks them `UNCLASSIFIED` with no evidence IDs, persists the package registry and appends the bounded verification register.
- DeepSeek Phase 1 and Phase 2 now require a trusted final register with at least one verified/corroborated claim and zero unresolved claims. Missing, unresolved or spoofed earlier register markers fail closed.
- Removed unsupported writing-prompt directives that inferred smart-money accumulation, Binance trending or Alpha selection from heuristic scores; numeric trade levels must have verified evidence.
- Research snippets/headlines are explicitly treated as untrusted data, not instructions.

### Verification evidence
- Focused verification: **30 passed, 0 failed** — 21 evidence-verification tests, 8 DeepSeek-generator tests and 1 Layer 1 runtime persistence integration test.
- Python `compileall`: passed.
- `git diff --check`: passed; new files were also checked for trailing whitespace.
- Full repository suite: **381 tests — 320 passed, 48 errors, 1 failure, 12 skipped**.
- All 49 non-passing results are in existing Module 9 test files: 48 fixtures fail with `ONCHAIN_OBSERVATION_STALE`; one expects `ACCEPTED` but receives `UNAVAILABLE`. The 12 PostgreSQL integration tests were skipped because `TEST_POSTGRES_DSN` is not configured. No Module 11 test failed. These Module 9 failures were not changed, bypassed or hidden.
- Full-suite output is retained at `/tmp/module11-full-tests-final.log` in the remote environment.

### Remaining gaps — Module 11 is NOT complete
- `split_atomic_claims()` currently segments sentences and semicolon clauses; it does not semantically split compound sentences or classify every factual statement.
- Free-text research drafts remain `UNCLASSIFIED` and unlinked. This intentionally blocks DeepSeek decision and generation until every material claim is converted into a structured claim and linked to attributable evidence IDs.
- Source-record assertions are not proof that all research-package statements are true. Full sentence-to-evidence mapping and a semantic content-verification acceptance gate remain outstanding.
- Persistence currently uses the existing Layer 1 SQLite store. The final Module 21 / production persistence boundary has not been validated.
- Market snapshots retain exact provider event timestamps; distinct snapshots are not collapsed into a UTC-minute bucket. The package-facing register selects the latest claim per asset/mapping/key/timeframe scope; event-specific announcement and on-chain transaction claims retain their event identity. Historical snapshots remain in the append-only registry, and the latest stale observation still blocks generation.
- Do not relax the DeepSeek gate to make generation work. Complete structured claim mapping and deterministic acceptance tests first.

### Exact next task
Continue Module 11 only: implement structured atomic-claim extraction/classification and evidence-ID mapping for research-package content; verify every factual claim with the deterministic engine; preserve unresolved/contradictory/stale claims; test that unsupported content remains blocked. Do not start Module 12 until Module 11's complete acceptance criteria are met. Do not modify Module 9 merely to make the current full suite appear green.

### Safety
- No Codex use, live DeepSeek API request, live RPC, production database write, workflow/secret/schedule change, publisher activation, Binance Square post, merge or deployment.
- `.github/workflows/run_bot.yml` remains unchanged and `DRY_RUN: "1"` remains in place.
- No commit or push was made for this Module 11 checkpoint.

## 2026-11-14 — Module 11 evidence mapping continuation and full-suite repair

### Current repository state
- Repository: `shehrozali6465372-ctrl/Binance-bot`.
- Active branch: `layer-1/module9-onchain-continuation`.
- HEAD remains `cceebd5680c70d5e34d4bd0de4035008f7b45481`; all changes in this checkpoint are local and uncommitted.
- Worktree: `/tmp/binance-deepseek-verify`.
- PR #13 remains open, Draft and unmerged. Default branch `main` was not touched.
- `MODULES_11_21_GAP_REGISTER.md` and this context file are updated. Locked architecture file remains unchanged.

### Additional Module 11 implementation
- `claims_from_research_package()` now splits compound sentences/semicolon clauses and classifies each resulting atom. Exact source-title strings are preserved for title-to-announcement matching. Unknown claims remain `UNCLASSIFIED` and block generation.
- Added exact adapters for official Binance Spot exchangeInfo pairs and local latest-200-post publication history. Announcement freshness is derived from publication/update timestamps and tied to the exact announcement title/lineage.
- Market claims are linked to the candidate's exact `market_data_hash`; missing hash means no auto-link. Displayed rounding is accepted only when it exactly matches the source's formatted value, while the claim retains the original source value. Different quote currencies are kept separate.
- The registry distinguishes blocking unresolved factual claims from qualified non-factual analysis. The generator requires a verified claim, zero unresolved factual claims and a valid trusted register schema.
- DeepSeek Phase 2 rejects numeric tokens absent from verified/corroborated claim lines. Hashtags are excluded from this numeric scan. This is a deterministic numeric consistency guard, not a full semantic fact checker.
- Removed Skills Hub metrics from LLM research packages pending attributable provider provenance. Kept those internal scoring fields unchanged. Corrected misleading volume/smart-money and execution/liquidity language so heuristic values are not presented as measured market facts or executable trade levels.
- Added an end-to-end deterministic test that builds a research package and maps its market, Binance Spot and publication-history assertions to evidence without unresolved factual claims.

### Test-fixture freshness correction (Module 9 tests only)
- The earlier 49 full-suite failures were caused by static test timestamps from 2026-11-11. The existing freshness policy correctly rejected those observations on 2026-11-14.
- Updated only test fixtures in `tests/test_onchain_aggregation.py`, `tests/test_onchain_bitcoin_worker.py`, `tests/test_onchain_intelligence.py`, `tests/test_onchain_solana_worker.py`, and `tests/test_onchain_xrpl_worker.py` to use current UTC-relative times. Provider block/event timestamps were also made relative to the injected test clock.
- No Module 9 production code, freshness threshold, validation rule, RPC adapter or database behavior was modified or weakened.
- The five affected Module 9 test files now pass **74/74** tests.

### Fresh verification
- Focused suite: **47 passed, 0 failed** — evidence verification, DeepSeek generator, research-package evidence mapping and Layer 1 runtime persistence.
- Module 9 affected test batch: **74 passed, 0 failed**.
- Full repository suite: **398 passed, 0 failed, 12 skipped** (`unittest discover -s tests -q`).
- The 12 skips are PostgreSQL integration tests because `TEST_POSTGRES_DSN` is not configured.
- Python `compileall`: passed for all touched application/test files.
- `git diff --check`: passed.
- Full-suite log: `/tmp/full-suite-2026-11-14-final.log`.

### Current limitations — do not mark Module 11 complete
- Research-package mapping currently covers explicit market fields, official Binance Spot eligibility, local publication history, and announcement title/type/freshness. Future/other fields remain unclassified until a matching evidence adapter is added.
- Trend and Module 9 on-chain evidence adapters exist, but the current research-package builder does not yet expose every trend/on-chain assertion as a package claim.
- The generated final post still lacks a complete semantic claim-to-evidence validator. The numeric guard does not detect every non-numeric factual hallucination or guarantee semantic attribution. This must be implemented and tested before Module 11 is complete.
- Existing Layer 1 SQLite persistence has not been validated against the final Module 21 production persistence boundary.
- Module 12–21 implementation and acceptance remain outstanding; no 21-module completion claim is made.

### Safety / deployment state
- No Codex use, live DeepSeek API request, live RPC, production database write, real Binance Square publication, publisher activation, workflow/secret/schedule change, merge or deployment.
- `.github/workflows/run_bot.yml` remains unchanged and `DRY_RUN: "1"` remains in place.
- No commit or push was made. Do not commit, push, merge or deploy without explicit approval.

### GitHub Actions / DeepSeek configuration mismatch (verified; intentionally unchanged)
- `.github/workflows/run_bot.yml` still supplies `GEMINI_API_KEY` and `GEMINI_MODEL=gemini-2.5-flash`.
- `main.py` reads only `DEEPSEEK_API_KEY` and `DEEPSEEK_MODEL` (default `deepseek-chat`). Therefore the current GitHub Actions workflow does not provide the credentials/model settings required by the new DeepSeek runtime; Phase 1/2 fail closed there.
- The workflow schedule remains `*/5 * * * *`; `DRY_RUN: "1"` remains set. No workflow or secret was modified.
- Safe plan, only after explicit owner approval: add the `DEEPSEEK_API_KEY` repository secret, change the workflow environment mapping to `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL`, retain `DRY_RUN: "1"` and the existing schedule, then verify a mocked/dry-run Actions execution before any production-publishing change. Keep legacy Gemini secrets until the new path is verified.


## Continuation checkpoint — 2026-11-14 (verified after Module 11 and DeepSeek updates)

- Repository remains on `layer-1/module9-onchain-continuation`, HEAD `cceebd5680c70d5e34d4bd0de4035008f7b45481`. Existing uncommitted work is preserved; no commit, push, merge, deployment, workflow edit, credential change, schedule change, or live Binance post was performed.
- Module 11 research-package assembly now appends exact-asset trend topics and threshold-qualified Module 9 summary references from accepted evidence records. The parser links trend topics by canonical topic digest plus exact subject/asset and links on-chain summaries by exact 64-character summary ID, canonical subject/asset, accepted status and threshold status. Unknown/mismatched assertions remain unresolved. This is a narrow evidence-surfacing improvement, not a full semantic fact checker.
- New regression tests cover exact trend/on-chain evidence links, unknown trend assertions remaining unverified, and no cross-asset evidence leakage.
- Direct DeepSeek defaults changed from deprecated `deepseek-chat` to current official `deepseek-flash`; API requests explicitly disable thinking mode to keep the text-generation path and token use bounded. `DEEPSEEK_MODEL` still overrides the default. No live DeepSeek API request was made.
- Current official DeepSeek API docs list `deepseek-flash` and `deepseek-v4-pro`; the docs' update history says legacy `deepseek-chat` / `deepseek-reasoner` names were to be discontinued on 2026-07-24. See https://api-docs.deepseek.com/api/create-chat-completion/ and https://api-docs.deepseek.com/updates/.
- Verification: full `unittest` suite **402 passed, 0 failed, 12 skipped**. The 12 skipped tests require `TEST_POSTGRES_DSN`. The initial run without Pillow could not import five main-dependent test modules; Pillow 13.0.0 was installed only into temporary `/tmp/binance-test-deps` (not into the repo or system environment), then the complete suite passed with `PYTHONPATH=/tmp/binance-test-deps`. `compileall` and `git diff --check` passed.
- Module 11 remains **PARTIAL**: non-numeric semantic hallucination detection is not proven; no real DeepSeek request was made; production database boundary integration is not yet validated. The new trend/on-chain adapter coverage must not be represented as full Module 11 completion.
- Modules 12–21 have not been declared complete. Their architecture acceptance criteria still require module-by-module source audit, implementation where missing, deterministic tests, persistence/recovery tests and safe end-to-end evidence. No real Cloudflare Workers AI image inference or live publishing integration was performed.
- Runtime integration blocker remains: `.github/workflows/run_bot.yml` supplies Gemini environment names while `main.py` reads `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL`. Workflow and secrets were intentionally left unchanged pending explicit owner approval.
- Cloudflare's current Workers AI catalog lists `@cf/black-forest-labs/flux-2-klein-4b`; the current pricing docs describe 10,000 free Neurons/day, with paid usage beyond that on Workers Paid. This is a candidate for Module 19 only; account access, free-tier availability for this model, actual inference output and cost must be validated before activation. See https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/ and https://developers.cloudflare.com/workers-ai/platform/pricing/.


## Module 12 continuation — 2026-11-14
- Implemented durable event lifecycle state and append-only transition history in `layer1/event_lifecycle.py` using the existing Layer1Store SQLite connection.
- Pipeline synchronization is wired after Module 11 registry verification; only verified/corroborated announcement evidence can confirm. Stale and unverified evidence do not become confirmed events.
- Stable provider IDs correlate revisions; CMS payload fingerprints do not. Multi-asset announcements split by canonical asset. Resolution/withdrawal require explicit verified evidence. Restart recovery tested.
- Module 12 tests: 12 passed; combined event graph/lifecycle: 22 passed.
- Still partial: automatic material-change classification is intentionally not guessed because importer records do not contain enough normalized change semantics; stale TTL is not globally hard-coded.

## 2026-11-14 — Modules 12–21 implementation continuation (latest local checkpoint; NOT production complete)

### Exact Git/worktree checkpoint
- Repository: shehrozali6465372-ctrl/Binance-bot.
- Worktree: /tmp/binance-deepseek-verify.
- Branch: layer-1/module9-onchain-continuation.
- Base HEAD remains cceebd5680c70d5e34d4bd0de4035008f7b45481; all current work is local and uncommitted.
- PR #13 remains Draft/open/unmerged. No commit, push, merge, deploy or main-branch change.
- The earlier Module 9 fixture corrections and Module 11 changes remain in the same preserved worktree. No reset/clean was run.

### Modules 12–21 code added / integrated
- Module 12: layer1/event_lifecycle.py; append-only lifecycle transitions and revision records, exact canonical asset splitting, explicit disputed state, verified resolution/withdrawal evidence, stale handling and restart recovery. Pipeline syncs announcements using Module 11 claim registry.
- Module 13: layer1/research_package.py; reproducible, versioned research packages with explicit cutoff, source coverage, verified facts, qualified inferences, disputed/unknown claims and completeness states. Persisted through the existing Layer 1 SQLite connection and appended to each candidate's research context.
- Module 14: layer1/opportunity.py; deterministic hard gates and optional weighted factors with strict schema/threshold validation; decision persistence and DeepSeek gate binding.
- Module 16: layer1/editorial_strategy.py; deterministic event/on-chain/market angle selection, prohibited-claim and uncertainty lists, duplicate-angle detection and versioned briefs.
- Module 17: layer1/content_generation.py; append-only exact-draft versions, provenance to research package/editorial brief/approved claim IDs, and persisted text/visual validation ledgers.
- Module 18: layer1/content_verification.py; canonical ticker/asset, verified claim register, numeric guard, prohibited trade instruction/guarantee checks; persisted PASS is required for authorization.
- Module 19: image_engine.py; direct Cloudflare Workers AI FLUX.2 Klein 4B multipart client; strict provider response/image byte decoding; Pillow composition uses generic generated background and deterministic text overlay; writes a hash/provenance sidecar.
- Module 20: layer1/visual_quality.py; PNG decode, dimensions, size, exact draft/image hashes, canonical identity, model/overlay metadata and chart/numeric-overlay checks.
- Module 21: layer1/publication_authorization.py, main.py, scripts/reconcile_publications.py; immutable authorization hash, fresh eligibility and event/evidence/text/visual gates, daily quota reservation, unique attempt binding, exact persisted validation lookup, unknown-outcome reconciliation and quota-state synchronization.
- DeepSeek's current official documented model ID deepseek-flash is retained as default. Current official API docs list deepseek-flash and deepseek-v4-pro; the chat completion client remains direct, without a third-party aggregator.
- Current official Cloudflare model ID is @cf/black-forest-labs/flux-2-klein-4b; official model page specifies multipart inputs. Code uses 1024x1024 inference and then deterministic 1080x1350 final composition.
- No live DeepSeek request, Cloudflare inference, Binance publish or external media upload was performed. Image-generation end-to-end test uses a deterministic fake transport/locally created image bytes, so it is not real provider evidence.

### Latest verification evidence
- Full repository test run before the final lifecycle edge-case test: 474 passed, 0 failed, 12 skipped.
- After adding disputed-event explicit-resolution coverage, focused regression batch: 56 passed, 0 failed (includes event lifecycle, DeepSeek gate, publication authorization/safety and the complete research-to-authorization pipeline).
- A new complete full-suite run was started as PID 21012; result must be read from /tmp/full-suite-2026-11-14-latest.log before treating it as final.
- Static checks (compileall and git diff --check) passed on the 56-test regression batch. The final full-suite process also runs both static checks after tests.
- Twelve PostgreSQL integration tests remain skipped because TEST_POSTGRES_DSN is not configured.

### Critical current blockers — all modules 11–21 remain PARTIAL
1. Module 11 semantic completeness: non-numeric factual hallucinations/causal claims are not comprehensively detected; trend/on-chain adapters do not prove every natural-language statement. Numeric checks are not semantic fact checking.
2. Module 12 material updates: automated material-change classification is not available from current normalized announcement fields; caller currently passes materially_new=False. A generic TTL is not guessed.
3. Module 13 source breadth: packages use existing persisted sources and exact evidence IDs, but a complete bounded external research acquisition/corroboration workflow and complete sentence-to-evidence semantics are not proven.
4. Module 14 blocks by design until configured: no approved scoring weights/factor-calibration or evidence-backed factor provider exists. Runtime supplies no factors/policy, so decision is DEFER; do not invent scoring constants to force PROCEED.
5. Module 15 provider proof: current model/API contract is checked against official docs and mock-tested; no live API request was made because no credential/provider test was approved.
6. Modules 16–17: editorial brief and draft persistence are integrated, but generation quality/semantic correctness cannot be established without a live DeepSeek request plus independent validation.
7. Module 18: deterministic numeric and prohibited-language checks are not a complete semantic, causality, repetition or source-attribution validator.
8. Module 19: provider client is implemented and model/multipart contract checked against official docs, but no authenticated real inference or account entitlement/cost verification. Do not say image inference is production-proven.
9. Module 20: deterministic image metadata and hash checks are implemented; no independent OCR/visual model audit of text visibility/contrast/clipping/semantic imagery. No unsupported chart is created.
10. Module 21: authorization/quota/attempt binding and manual reconciliation tests are implemented, but no production persistence test (PostgreSQL tests skipped), no provider publication call and no production recovery drill. Media upload currently occurs before the final publication authorization and should be reviewed/reordered before live enablement.
11. All modules 1–10: they are existing implementation, but this continuation has not repeated a fresh requirement-by-requirement architecture audit of every acceptance item. Do not label all 21 modules complete based only on a green unit suite.

### Safety and untouched systems
- No Codex, no paid infrastructure provisioning, no real Binance Square post, no live RPC, no production database write, no workflow/secret/schedule changes, no publisher activation, no merge or deployment.
- .github/workflows/run_bot.yml remains unchanged, retains DRY_RUN: "1", and still has the documented Gemini/DeepSeek environment-variable mismatch. No workflow run was triggered.
- No commit or push. Preserve this uncommitted working tree and continue from the exact branch/HEAD above.

## Verification supersession — 2026-11-14 22:22 UTC
- The final full repository run after the disputed-event lifecycle test and Cloudflare official dimension-bound correction completed: **478 passed, 0 failed, 12 skipped**.
- The 12 skipped cases are PostgreSQL integration tests because TEST_POSTGRES_DSN is not configured.
- Python compileall and git diff --check both completed with exit code 0.
- Final log: /tmp/full-suite-2026-11-14-final-final.log.
- Official Cloudflare FLUX.2 Klein 4B docs specify width/height 256–1920; the request validator now enforces that exact range, with a regression test for 1921 rejection.
- This supersedes the 474/402/398 historical counts above. The worktree remains uncommitted on layer-1/module9-onchain-continuation at base HEAD cceebd5680c70d5e34d4bd0de4035008f7b45481.

## 2026-11-14 — Image provenance and strict publication-gate hardening
- Image generation sidecars now include prompt SHA-256 and exact inference width/height/output-format metadata. The exact final image hash and draft hash remain linked.
- Added append-only image_generation_artifacts persistence to the existing SQLite DraftStore. Records include provider/model/request ID/generated time/prompt hash/parameters/source-image hash/final-image hash/draft hash/canonical asset and local path. Exact draft/image pair replay is idempotent; conflicting provenance for the same pair is rejected.
- VisualQualityEngine now rejects missing prompt provenance and generation parameters outside Cloudflare's documented 256–1920 range.
- Publication authorization now rejects non-canonical CoinGecko IDs, invalid ticker format, duplicate image hashes and non-hex SHA-256 image hashes.
- IMAGE_REQUIRED is a validated config setting, defaults to true, and may be disabled only explicitly with IMAGE_REQUIRED=false. When required, missing generation, failed visual validation, image-upload failure or an image-pipeline exception blocks publication; no silent text-only fallback. Dry-run still avoids Binance media upload while requiring local image generation/QA.
- Verified only one production call site invokes publisher.publish() in main.py. Legacy python agent_bot.py has no separate publishing call path; image-upload requests are not publication calls.
- New focused image/provenance/publication regression batch: 28 passed, 0 failed. Full repository suite after all these changes: **483 passed, 0 failed, 12 skipped**. The 12 skips require TEST_POSTGRES_DSN.
- Final static checks: python -m compileall -q layer1 main.py image_engine.py scripts tests and git diff --check both passed. Final log: /tmp/full-suite-2026-11-14-image-required-final.log.
- All work remains uncommitted on layer-1/module9-onchain-continuation at base HEAD cceebd5680c70d5e34d4bd0de4035008f7b45481. No provider inference, media upload, real Binance post, production DB write, workflow/secret change, commit/push, merge or deployment.

## Verification supersession — 2026-11-14 (Module 19–20 provenance persistence)
- Latest full suite after adding persisted image-generation artifacts: **483 passed, 0 failed, 12 skipped** in 23.781s. Log: /tmp/full-suite-2026-11-14-image-artifact.log.
- compileall and git diff --check both passed.
- Added image_generation_artifacts to the existing SQLite DraftStore: deterministic artifact ID; exact draft/final-image/source-image/prompt hashes; canonical asset/symbol; provider/model/request ID; generation timestamp and parameters; image path; immutable JSON metadata. Pipeline persists this record before visual validation. Sidecar remains as the file-bound manifest.
- Visual QA now fails closed on missing/malformed prompt hash and invalid Cloudflare FLUX.2 Klein 4B generation dimensions/format; 256–1920 provider input bounds. Tests cover metadata round-trip, missing metadata rejection, invalid prompt hash and out-of-range dimensions.
- End-to-end test verifies image artifact persistence occurs before visual QA and publication authorization.
- PostgreSQL tests remain skipped (TEST_POSTGRES_DSN absent). DraftStore remains SQLite-only; this does not prove multi-process/production persistence.
- Exact Git state: branch layer-1/module9-onchain-continuation, HEAD cceebd5680c70d5e34d4bd0de4035008f7b45481; all changes remain uncommitted/unpushed. No real post, external media upload, live provider inference, merge or deployment.

## Verification supersession — 2026-11-14 (dry-run media side-effect guard)
- Added should_upload_image(dry_run, image_path) and wired main.py so Binance Square media upload is skipped whenever DRY_RUN is enabled, even if image generation succeeds. Dry-run no longer performs this external media side effect.
- Focused regression: 28 passed, 0 failed across Cloudflare image generation, end-to-end pipeline and publisher safety.
- Latest full suite: **484 passed, 0 failed, 12 skipped** in 25.355s. Log: /tmp/full-suite-2026-11-14-dryrun-guard.log. Python compileall and git diff --check passed.
- The existing media upload still occurs before final immutable publication authorization in live mode. This remains an explicit Module 21 release blocker; do not enable live publishing until ordering is redesigned/tested.
- No real media upload or Binance post was made; test media upload helper uses local deterministic assertions only.

## Latest publication-order hardening — 2026-11-14 22:44 UTC
- Fixed the critical Module 21 side-effect order in main.py. The flow is now: generate image locally → persist image artifact → visual QA PASS → fresh Binance Spot revalidation → reserve quota + persist immutable publication authorization bound to exact draft/image hash → upload media through upload_authorized_image() which rechecks authorization integrity and exact content/image hashes → publisher submission performs its own authorization/quota checks.
- Binance media upload is no longer performed before final publication authorization. Failed/missing upload releases the quota reservation and aborts; dry-run does not upload media. No actual upload was run.
- Added upload_authorized_image() helper with fail-closed checks for missing/tampered/expired/mismatched authorization, exact draft/image binding, missing API key, and non-HTTPS upload result. Added regression tests proving no upload callback is invoked when authorization is missing or hash validation fails.
- Verification after this change: full suite **486 passed, 0 failed, 12 skipped** in 23.699s. compileall and git diff --check passed. Log: /tmp/full-suite-2026-11-14-auth-before-upload.log.
- Static order inspection confirms authorize() at main.py:4662, upload_authorized_image() at :4690, publisher.publish() at :4721.
- This supersedes earlier notes that media upload preceded authorization; the order is now corrected and test-covered.
- Still not production complete: no TEST_POSTGRES_DSN; no real provider API/inference or Binance upload/post; workflow Gemini/DeepSeek secret mismatch; semantic factual validator and opportunity policy unresolved; no end-to-end production recovery drill. All changes remain local/uncommitted on branch layer-1/module9-onchain-continuation at base HEAD cceebd5680c70d5e34d4bd0de4035008f7b45481.

## Module 15 direct DeepSeek client hardening — 2026-11-14
- Current official Chat Completions schema verified: response requires chat.completion object, ID, model and choice finish_reason; finish_reason values include stop, length, content_filter, tool_calls, insufficient_system_resource and aborted. Official docs explicitly say length can truncate content. Source: https://api-docs.deepseek.com/api/create-chat-completion/.
- Client now requires exact expected model ID, response object type, non-empty response ID, exactly terminal finish_reason=stop, non-empty text and no refusal/tool calls. Truncated, filtered, aborted, tool-call, wrong-model and malformed identity responses fail closed.
- Added bounded retries (max 2 retries, exponential 0.25s base by default) only for HTTP 408/429/500/502/503/504 and transport errors. 401/auth/config errors are not retried. Retry bounds validated; no response body or secret is logged.
- DeepSeek response object now retains response ID, token usage and measured latency_ms; safe metadata is logged without credential values.
- Focused tests after changes: 27 passed, 0 failed; compileall and git diff --check passed. A full suite run is still required to establish new final count.
- No live DeepSeek request was made. This is contract/mock verification, not authenticated production provider proof.

## Module 19/21 media transport security hardening — 2026-11-14
- Presigned upload targets are now checked before any PUT: HTTPS only, port 443/default, no userinfo/fragment, signed query required, host must be under the allowlisted Binance/AWS storage suffixes. The low-level PUT method repeats this check so it cannot be bypassed by direct invocation.
- Returned public media URL is separately restricted to HTTPS Binance CDN host bin.bnbstatic.com / subdomains before it can enter imageList.
- Removed presigned URL, file-ticket, upload response body and raw exception details from logs. Only provider status/code, safe attempt counts and exception class remain.
- Added tests for malicious host, localhost/IP, HTTP, credentials, nonstandard port, missing signature query, and non-Binance CDN return URL. Focused Module 19/20/21 batch: 32 passed, 0 failed; compileall and git diff --check passed.
- Host allowlist has not been confirmed by a real authenticated Binance Square media upload; unknown future storage hosts intentionally fail closed until verified. No upload/post was made.

## Latest full verification — 2026-11-14 22:58 UTC
- After DeepSeek strict-response/retry hardening, publication-before-upload authorization, media host/SSRF validation, sensitive log redaction and no-redirect transport: **495 passed, 0 failed, 12 skipped** in 25.781s.
- 12 skipped are PostgreSQL integration tests because TEST_POSTGRES_DSN is absent.
- Python compileall and git diff --check passed.
- Binance media presigned API/status calls and binary PUT now use a no-redirect HTTP opener. Redirect responses fail instead of silently forwarding the request or credentials to a new destination.
- Full-suite log: /tmp/full-suite-2026-11-14-no-redirect.log.
- Exact Git state remains branch layer-1/module9-onchain-continuation, HEAD cceebd5680c70d5e34d4bd0de4035008f7b45481. All changes local/uncommitted; no push/merge/deploy.

## Final media transport redirect hardening — 2026-11-14 23:02 UTC
- Binance media presignedUrl, imageStatus and storage PUT requests now use an HTTP opener with redirects disabled. A redirect response is treated as failure; the client will not silently forward a signed upload URL or Square API key to a different host.
- Added a focused regression for the no-redirect handler. Latest full suite after this change: **495 passed, 0 failed, 12 skipped**; compileall and git diff --check passed. Log: /tmp/full-suite-2026-11-14-no-redirect.log.
- No live media request or upload was made; the current host allowlist still needs authenticated provider confirmation before production enablement.

## Module 17 draft provenance integrity hardening — 2026-11-14
- DraftStore now rejects reusing the same exact content hash/editorial brief key with different research-package IDs or approved claim IDs. It returns the existing record only when all immutable provenance matches.
- DraftStore validates approved_claim_ids as a sequence of non-empty strings (not a bare string/bytes or malformed items).
- Text/visual validation ledgers now validate lowercase SHA-256 hashes, status/version types and reason-list shape before persistence.
- Focused tests (content generation, end-to-end pipeline and image pipeline): **24 passed, 0 failed**; compileall and git diff --check passed. Full suite must be rerun for the final count.

## Module 21 persisted draft provenance binding — 2026-11-14
- PublicationAuthorization now binds the exact persisted draft ID, research package ID, editorial brief ID, approved claim IDs and a SHA-256 digest over those provenance fields, in addition to content/image hashes.
- Authorization creation fails unless the exact content is already present in content_draft_versions with non-empty research/editorial/approved-claim provenance and persisted text PASS / image PASS records.
- The single publisher re-reads the exact draft row immediately before publication and rejects/de-reserves quota if the draft is missing or its research/brief/claim provenance changed after authorization. This closes the path where a PASS validation row alone could authorize arbitrary text.
- Focused Module 17/21, publisher safety, end-to-end and media tests: **44 passed, 0 failed**; compileall and git diff --check passed. Full-suite verification pending.

## Module 21 persisted-provenance authorization verification — 2026-11-14 23:05 UTC
- Latest full repository suite after exact persisted-draft authorization and publisher recheck: **499 passed, 0 failed, 12 skipped** in 27.571s.
- 12 skipped tests are PostgreSQL integration cases; TEST_POSTGRES_DSN is absent.
- compileall and git diff --check passed. Log: /tmp/full-suite-2026-11-14-provenance-bound-auth.log.
- Local Remote Desktop execution environment was checked by presence only (no values read): DEEPSEEK_API_KEY, SQUARE_API_KEY, CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, DATABASE_URL and TEST_POSTGRES_DSN are all not configured; .env/.env.local/.env.production absent.
- GitHub Actions workflow maps GEMINI_API_KEY/GEMINI_MODEL rather than DEEPSEEK_API_KEY/DEEPSEEK_MODEL; it maps SQUARE_API_KEY and ANNOUNCEMENT_DATABASE_URL, has DRY_RUN=1, and does not map Cloudflare Workers AI credentials. This workflow was inspected but deliberately not modified due explicit no-workflow/secrets-change constraint.
- Consequently, live DeepSeek, Cloudflare inference, Binance media upload and publication tests cannot be executed from this local worker. No real provider request/upload/post was made.
- Branch/HEAD unchanged: layer-1/module9-onchain-continuation / cceebd5680c70d5e34d4bd0de4035008f7b45481; all changes uncommitted/unpushed.

## Module 21 publishing and reconciliation URL hardening — 2026-11-14
- Square content/add POST now uses a no-redirect HTTP opener. The Square API key and post body are not forwarded to a redirect target. A redirect is treated as a failure, never followed.
- Operator reconciliation validates remote post IDs and any supplied share URL: HTTPS only, official www.binance.com/binance.com host, exact /square/post/<remote_id> path, no userinfo/fragment, and URL ID must equal the remote ID. Confirm-failed cannot accept a share URL.
- Focused publisher/reconciliation/authorization tests: 31 passed, 0 failed; compileall and git diff --check passed. Full-suite rerun pending.

## Module 21 final gateway/reconciliation verification — 2026-11-14 23:09 UTC
- Full suite after no-redirect Square POST and strict manual reconciliation URL validation: **501 passed, 0 failed, 12 skipped** in 25.392s.
- compileall and git diff --check passed.
- Exactly one production code reference to Binance Square content/add exists: PostPublisher.API_URL in main.py. It uses a no-redirect opener and validates immutable draft/provenance, persisted PASS records, quota, idempotency attempt and authorization before the post request.
- Full log: /tmp/full-suite-2026-11-14-publish-reconcile-hardening.log.
- Git branch/HEAD unchanged; uncommitted worktree only. No actual post was published.

## Module 11 cross-asset isolation fix — 2026-11-14 23:11 UTC
- Found that the base claim registry is built across the entire candidate universe; attaching it wholesale to one candidate could expose other assets' verified numeric facts in that candidate's DeepSeek context/numeric allowlist.
- Added EvidenceVerificationEngine.scope_registry_to_asset() and wired _attach_claim_register() to use only exact canonical asset claims/evidence before appending market/Spot/publication records and rendering the claim register. Foreign-asset evidence is excluded even if incorrectly referenced; the affected claim remains unresolved due missing evidence rather than leaking the other asset's values.
- Added multi-asset isolation and cross-asset-reference regressions.
- Focused verification (evidence verification, DeepSeek generator, end-to-end pipeline and all Layer 1 foundation tests): **153 passed, 0 failed**; compileall and git diff --check passed. Full-suite rerun pending.

## Latest Module 11 asset-scoped registry verification — 2026-11-14 23:12 UTC
- Full suite after candidate-specific claim/evidence scoping: **503 passed, 0 failed, 12 skipped** in 25.534s.
- compileall and git diff --check passed.
- Full log: /tmp/full-suite-2026-11-14-asset-scoped-claims.log.
- This is the current superseding test count; 12 skipped still require TEST_POSTGRES_DSN.
- No external provider requests, uploads or posts; Git branch/HEAD unchanged and all changes remain local/uncommitted.

## Continuation checkpoint — 2026-11-15 (CI failure root cause verified)
- Correct working tree: `/tmp/binance-deepseek-verify`; repository `shehrozali6465372-ctrl/Binance-bot`; branch `layer-1/module9-onchain-continuation`; base HEAD `cceebd5680c70d5e34d4bd0de4035008f7b45481`.
- GitHub Actions run `43602790623` (`mocked-safety-tests`) was inspected from its job logs. It ran 358 tests and failed with 48 errors + 1 failure + 12 PostgreSQL skips. The failing Module 9 fixtures used hard-coded `2026-11-11` timestamps while the runner was executing on 2026-11-14, so the production freshness policy correctly rejected those observations as stale (`ONCHAIN_OBSERVATION_STALE`). This was a test-fixture defect, not justification to weaken freshness validation.
- The preserved local worktree already contains the correction: Module 9 test fixtures now use current UTC-relative timestamps for on-chain observations, provider headers and mapping/eligibility provenance. No production freshness threshold or validation logic was weakened.
- Focused Module 9 regression batch after the fixture correction: **74 passed, 0 failed** across on-chain intelligence, XRPL, Bitcoin, Solana and aggregation tests.
- Full local repository suite: **503 passed, 0 failed, 12 skipped** in 27.031s. The 12 skips require `TEST_POSTGRES_DSN`, which is not configured. This is a local worktree result, not yet a GitHub Actions result.
- `python -m compileall -q main.py image_engine.py layer1 scripts tests` and `git diff --check` both pass.
- Worktree contains 16 modified tracked files and 20 untracked files; all existing changes are preserved. No reset/clean, commit, push, merge, deployment, provider inference, media upload or real Binance Square post was performed. GitHub still points at the old committed fixture versions, so the CI run has not yet been re-triggered against the corrected working tree.
- Module 11 remains PARTIAL because semantic non-numeric factual/causal claim verification is not complete. Modules 12–21 have implementations but the documented acceptance gaps remain; PostgreSQL integration, live DeepSeek/Cloudflare proof, configured opportunity policy and production recovery drill are outstanding.
- PR #13 is an older Draft PR from `layer-1/module9-onchain-intelligence` into `layer-1/module8-market-analysis`; it is not the current continuation branch. PR #2 is the separate CMS announcement-worker PR. Neither PR was modified.


## Module 11 continuation — unmatched announcement-detail laundering fix — 2026-11-15
- Rechecked GitHub Actions for pushed commit `ea753d2cdbfea37f714de1c8daa2b9309bd2faf3`: `Phase 1 Safety Tests` run `43636409987`, job `mocked-safety-tests`, completed SUCCESS. This supersedes the earlier note that CI had not yet reported a run for that commit.
- Found a claim-classification defect in `EvidenceVerificationEngine.claims_from_research_package()`: when a `Detail:` announcement headline did not exactly match an accepted source record, it was incorrectly labeled `ANALYST_INTERPRETATION`. `DeepResearchEngine` treats non-factual types separately from unresolved factual claims, so this could allow an unsupported headline to be treated as qualified inference when other verified facts existed.
- Changed unmatched `Detail:` lines to `UNCLASSIFIED` with the announcement-title claim key and no evidence IDs. Exact title matches still bind to source lineage and remain source assertions; unmatched titles now produce `UNVERIFIED` and block research readiness.
- Added regression tests proving unmatched headlines appear in the unresolved register and force `RESEARCH_MORE`, never the qualified-inference section.
- TDD evidence: new regression initially failed (`ANALYST_INTERPRETATION` returned instead of `UNCLASSIFIED`); after the fix, it passed. Focused batch across evidence verification, research packages, content verification and end-to-end pipeline: **54 passed, 0 failed**.
- This closes one concrete Module 11 classification defect only. General semantic factual/causal validation, conservative compound-clause decomposition and complete generated-post sentence-to-evidence attribution remain open. Do not mark Module 11 complete.
- No external provider call, media upload, production DB write, publisher activation, real Binance Square post, workflow/secrets/schedule change, merge or deployment.
- Working branch before this follow-up: `layer-1/module9-onchain-continuation`, pushed base commit `ea753d2cdbfea37f714de1c8daa2b9309bd2faf3`; follow-up code/docs/tests are currently local pending verification and review.


## Module 11 follow-up verification supersession — 2026-11-15 01:56 PKT
- A first full-suite run after the initial unmatched-Detail fix exposed an over-broad classification change: generated `Type: MARKET MOVEMENT` heuristic details were also being marked unresolved. No code was pushed from that failing state.
- Narrowed the rule using explicit preceding `Type:` context: `Detail:` text under `MARKET MOVEMENT` remains labeled `ANALYST_INTERPRETATION`; an unmatched `Detail:` under announcement types or without explicit market-movement context remains `UNCLASSIFIED` unless an exact accepted announcement-title record matches.
- Added a regression for the explicit market-movement classification. The focused evidence/research/content/end-to-end/DeepSeek batch now passes **71 tests, 0 failures**.
- Full repository suite after the final narrowed fix: **507 passed, 0 failed, 12 skipped** in 32.048s. The 12 skipped require `TEST_POSTGRES_DSN`.
- `compileall` and `git diff --check` pass. No provider inference, upload, production DB write, or real Square publication.
- The code and documentation follow-up is local and uncommitted at this checkpoint; Module 11 remains PARTIAL due general semantic factual/causal verification and sentence-level generated-post attribution gaps.

## GitHub follow-up confirmation — 2026-11-15
- The Module 11 unmatched-announcement-detail fix and its tests were committed as `43f5329103fc48772ce10503d55cac9349a9843e` and pushed to `layer-1/module9-onchain-continuation`.
- GitHub Actions run `43640134763` for this exact commit completed **SUCCESS**. PR #14 was updated with the final local verification counts and current release blockers; it remains Draft, open, unmerged and mergeable.
- Local working tree was clean immediately after the push. No production integration or publishing actions were taken.


## Module 12 material event-time revision detection — 2026-11-15
- Closed one deterministic lifecycle gap: `sync_announcements()` previously passed `materially_new=False` unconditionally, so a verified source revision that explicitly changed the event's effective `event_at` could never move a CONFIRMED event to DEVELOPING.
- Added conservative comparison against the prior persisted revision payload. Only an explicit change to `event_at` is treated as material. Content-hash changes, `updated_at` changes, observation timestamps, and unchanged event times are not material by themselves.
- Added two TDD regressions: verified event-time change transitions to DEVELOPING; content-hash/source-update-only revision remains CONFIRMED. The first test failed before the implementation and both pass after.
- Full repository suite with the project virtualenv: **509 passed, 0 failed, 12 skipped** in 32.184s. The 12 skips require `TEST_POSTGRES_DSN`. `python -m compileall -q layer1 tests` and `git diff --check` pass.
- This is a narrow Module 12 fix, not full material-change classification. Meaningful body/title changes cannot be judged from the currently persisted announcement schema alone; do not infer materiality from a hash/title change. Full event semantic-diff remains open.
- No live provider call, DB production write, media upload, real Square post, credential/workflow/schedule change, merge or deployment. Local worktree contains this code/test/doc update pending push and CI confirmation.

## Module 11 continuation — abbreviation-safe claim segmentation — 2026-11-15
- Verified the active worktree and branch before editing: `/tmp/binance-deepseek-verify`, `layer-1/module9-onchain-continuation`, HEAD `ca3afbd7744c197875565d385daaf706cd213bc3`; worktree was clean at start.
- Existing `split_atomic_claims()` incorrectly split common abbreviations such as `U.S.` and `e.g.` into fragments, creating malformed atomic claim records and degrading later evidence attribution.
- Added a failing regression first, confirmed RED, then protected common abbreviations during deterministic sentence segmentation. Focused `tests.test_evidence_verification`: **41 passed, 0 failed**.
- This does not solve semantic clause decomposition or generated-post sentence-to-evidence entailment. Module 11 remains PARTIAL. Full suite and CI verification pending.

## GitHub DeepSeek credential setup and local secret-file protection — 2026-11-15
- User configured GitHub repository Actions secrets and variables. Screenshots confirmed the presence (names only; secret values are not visible) of `DEEPSEEK_API_KEY`, `CLOUDFLARE_API_TOKEN`, and the exact code-expected `ANNOUNCEMENT_DATABASE_URL`. The older `BINANCE_ANNOUNCEMENT_DATABASE_URL` remains present and was not removed. Repository variables `DEEPSEEK_MODEL=deepseek-flash` and `CLOUDFLARE_ACCOUNT_ID` are present.
- Read-only inspection of `.github/workflows/run_bot.yml` confirms the scheduled workflow still maps `GEMINI_API_KEY` and hard-codes `GEMINI_MODEL=gemini-2.5-flash`; it does not map `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `CLOUDFLARE_API_TOKEN`, or `CLOUDFLARE_ACCOUNT_ID`. It does map `ANNOUNCEMENT_DATABASE_URL` and keeps `DRY_RUN: "1"`.
- `main.py` uses the DeepSeek client directly; it does not contain an active Gemini generation path. The GitHub workflow therefore does not yet supply the configured DeepSeek key to the scheduled process. Repository source also explicitly treats workflow files as deployment configuration that the agent must not self-modify; no workflow change was made.
- Added `.env`, `.env.*`, and an `.env.example` exception to `.gitignore` to prevent accidental commits of local credentials. No `.env` file was created and no secrets were read or copied.
- Verification constraint: this RDC Python environment has no `pytest` or Pillow installed and no matching cached wheels. The stdlib DeepSeek client tests ran: **11 passed**. Importing `tests.test_deepseek_generator` was blocked by missing Pillow; no full-suite result is claimed for this environment. No packages were installed.
- Current branch at the start of this checkpoint: `layer-1/module9-onchain-continuation`, HEAD `cce51191aa81a8b6d7c731a91ff7d1179182b5f5`, clean worktree. Workflow/provider activation remains pending an explicitly approved, reviewed deployment-configuration change. No production publisher activation, live inference, upload, real Square post, merge, or deployment occurred.

## Approved GitHub Actions DeepSeek/Cloudflare workflow wiring — 2026-11-15
- User explicitly approved the previously proposed workflow integration. Before editing, reverified branch `layer-1/module9-onchain-continuation`, HEAD `cce51191aa81a8b6d7c731a91ff7d1179182b5f5`, and preserved the two pre-existing local changes to `.gitignore` and this context file.
- Updated `.github/workflows/run_bot.yml` to map `DEEPSEEK_API_KEY` from repository secrets and `DEEPSEEK_MODEL` from repository variables; mapped `CLOUDFLARE_API_TOKEN` from secrets and `CLOUDFLARE_ACCOUNT_ID` from variables. Kept the exact code-expected `ANNOUNCEMENT_DATABASE_URL` secret mapping.
- Removed the unused Gemini API key/model environment mappings from this workflow. Existing Gemini repository secret was not deleted or modified.
- Preserved `DRY_RUN: "1"`, `LIVE_MARKET_DATA: "1"`, one-iteration scheduled-run configuration, schedule, permissions, concurrency, Square key mapping, and all publisher safety controls. This change does not authorize or enable a real Binance Square post.
- Added a regression assertion to the existing scheduled-workflow configuration test. TDD RED confirmed the test failed because DeepSeek mappings were absent; GREEN passed after the workflow change.
- Verification: focused workflow/importer and DeepSeek client suite **19 passed**; workflow YAML parsed successfully and the expected DeepSeek, Cloudflare, database, and DRY_RUN bindings were asserted; `python -m compileall -q main.py image_engine.py layer1 scripts tests` and `git diff --check` passed.
- A broader test collection including runtime integration was blocked because Pillow (`PIL`) is absent in available remote Python environments. No package was installed. Full repository suite and GitHub Actions confirmation remain pending.
- No live DeepSeek request, Cloudflare inference/upload, production database write, publisher activation, real Square post, merge, or deployment was performed. Workflow edits are local only at this checkpoint; do not claim GitHub Actions is already using the new mapping until the change is pushed and a successful run is observed.

## Workflow integration CI confirmation — 2026-11-15
- GitHub Actions run `43644649579` for exact commit `2b8a3ec959d465a747fa54a51736e63fa459e475` completed **SUCCESS**. Job `mocked-safety-tests` completed all steps successfully.
- The GitHub-hosted CI environment installed Pillow, compiled the project, and ran `python -m unittest discover -s tests -v`: **510 tests ran, OK, 12 skipped**. The 12 skips are PostgreSQL integration tests requiring `TEST_POSTGRES_DSN`.
- This is mocked safety CI, not a live provider execution. It does not prove the DeepSeek API key works, Cloudflare inference works, or the scheduled `run_bot.yml` workflow has completed a provider-backed run.
- PR #14 remains Draft, open, unmerged, and mergeable. Its description was refreshed to show the workflow mapping and remaining release blockers.
- The workflow continues to preserve `DRY_RUN=1`; no workflow_dispatch, scheduled provider inference, media upload, production database write, or real Binance Square post was initiated by this work.

## Module 11 abbreviation segmentation follow-up — 2026-11-15
- Verified active branch `layer-1/module9-onchain-continuation`, HEAD `3fe895493ef35b8177b037eef382384c8392abb6`, and clean worktree before editing.
- Found that deterministic claim segmentation protected common abbreviations and initials but split organization suffixes such as `Inc.` and `Corp.` into malformed fragments.
- Added a regression first and confirmed RED; extended the existing abbreviation allowlist for `Inc.`, `Corp.`, `Ltd.`, `PLC`, `LLC`, and `Co.` without introducing an NLP dependency or semantic inference.
- Focused evidence-verification suite: **43 passed, 0 failed**. Full-suite verification pending.
- This is a narrow segmentation robustness fix only. It does not implement semantic compound-clause decomposition or generated-post sentence-to-evidence entailment; Module 11 remains PARTIAL.
- No external provider request, database write, media upload, publishing action, commit, push, merge or deployment has been performed.


## Module 11 runtime/persistence re-audit — 2026-11-15
- Confirmed the existing code path already persists source-record claim registries during `_persist_layer1_market_intelligence()` and persists asset-scoped research-package registries plus `ResearchPackageStore` records in `_attach_claim_register()`. Existing foundation integration tests assert SQLite claim-run persistence and cache idempotency. This is local SQLite integration coverage, not proof of the separate production/PostgreSQL persistence boundary.
- Re-ran `python -m unittest tests.test_evidence_verification tests.test_deepseek_generator -v`: all **43 evidence-verification tests passed**; DeepSeek-generator test module import was blocked because Pillow (`PIL`) is unavailable in this remote Python. No package installation attempted and no DeepSeek-generator test pass is claimed.
- `git diff --check` passed. Module 11 remains PARTIAL because semantic compound-clause decomposition and generated-post sentence-to-evidence entailment remain open.


## Module 11 generated-post attribution hardening — 2026-11-15
- Verified the exact continuation worktree before editing: `/tmp/binance-deepseek-verify`, branch `layer-1/module9-onchain-continuation`, HEAD `3fe895493ef35b8177b037eef382384c8392abb6`. Preserved the four pre-existing modified files; no reset, clean, checkout, commit or push.
- Added a strict claim-attribution protocol to the generated-post gate. The trusted claim register now includes each verified claim's stable claim ID. The DeepSeek writing prompt requires every factual sentence to start with `[[CLAIM:<64-hex-claim-id>]]` and to copy the exact verified claim text.
- `ContentVerificationEngine` now splits the draft into sentence/clause units, requires exactly one known verified/corroborated claim marker for each non-hashtag sentence, compares the sentence text exactly after conservative whitespace/case/punctuation normalization, rejects missing/unknown/unverified/mismatched references, and returns only claim IDs actually used by the draft. Verified claims from another canonical asset are excluded even when a foreign claim ID is supplied.
- Internal attribution markers are stripped before the content hash, draft persistence, publication authorization and post content. A draft with no successfully attributed claim is rejected before `DraftStore.save_draft()` to avoid violating its non-empty provenance contract.
- TDD evidence: regressions reproduced the old unsafe behavior for an unmarked factual sentence, a rewritten sentence carrying a legitimate claim ID, unknown claim IDs, and independent conjunction clauses. Tests now cover cross-asset reference rejection, claim-ID rendering, conjunction split/no-split cases and package-level preservation as `UNCLASSIFIED`.
- Added a conservative conjunctive splitter: it splits `and` / `but` / `while` / `whereas` when a separate subject–verb clause is visible, and splits shared-subject coordinated predicates only when a recognized second finite verb is explicit. Coordinated object lists and ambiguous elliptical structures are not guessed apart; explicit shared-subject predicates are split only when a recognized finite verb makes the second proposition clear. Unsupported facts remain unresolved. This is a bounded deterministic rule set, not a full natural-language parser.
- Verification in isolated temporary venv `/tmp/binance-module11-test-venv` (Pillow installed only there; no repo dependency file or production environment changed): full `python -m unittest discover -s tests -q` -> **522 tests ran: 510 passed, 0 failed, 12 skipped**. All 12 skips require `TEST_POSTGRES_DSN`. The full run included the DeepSeek-generator, end-to-end and publisher-safety tests. `compileall` and `git diff --check` pass.
- The content gate requires exact, verbatim claim text with internal `[[CLAIM:<id>]]` references; it rejects unmarked factual sentences, unknown/foreign/unverified IDs, and paraphrases. It strips internal markers before draft hashing/persistence and binds only the actually referenced claim IDs. This is deliberately fail-closed, but it can reject otherwise accurate paraphrased/editorial prose; no arbitrary semantic entailment is claimed.
- Module 11 remains **PARTIAL** because full semantic fact/causal inference and every natural-language form of ambiguous shared-subject/elliptical compounds are not supported; ambiguous cases are retained as unresolved rather than guessed. Existing Module 11 append-only SQLite registry persistence is covered by integration tests. Module 21 production durability is a separate cross-module boundary. Twelve unrelated PostgreSQL integration tests were skipped because `TEST_POSTGRES_DSN` was not configured; no test DB was added.
- No live DeepSeek/Cloudflare call, paid API use, production database write, real Binance Square post, publisher activation, workflow/secrets/schedule change, merge, deployment, commit or push.


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


## Module 20 visual verification and Module 21 continuation checkpoint — 2026-11-15
- Reverified exact working tree through Remote Desktop Commander before work: `/tmp/binance-deepseek-verify`, branch `layer-1/module9-onchain-continuation`, HEAD `3fe895493ef35b8177b037eef382384c8392abb6`; 20 modified tracked files at entry, zero untracked, clean `git diff --check`. Preserved all prior changes.
- Hardened Module 20 image sidecar: `ImageComposer` now stores actual Pillow text bounding boxes, font sizes, RGB text fills and lower-panel RGBA background geometry for both deterministic labels.
- `VisualQualityEngine` now validates overlay metadata, canvas/panel containment, clipping, non-overlap, minimum font size and conservative WCAG AA contrast (4.5:1). Missing geometry fails closed. Validation version advanced to `visual-quality-v2`.
- Updated publication authorization and publisher pre-submit validation to require `visual-quality-v2` PASS for the exact draft/image pair; a legacy `visual-quality-v1` PASS cannot be reused. Tests prove obsolete validation is rejected both at authorization and if downgraded after authorization before network submission.
- Removed legacy synthetic candlestick generation when no supplied price history exists. Renderer now displays `VERIFIED PRICE HISTORY REQUIRED` and does not draw a chart in that case.
- TDD regressions were observed RED before implementation. Focused visual/image/auth/publisher/end-to-end tests passed; final full repository suite: **542 tests, 0 failures, 12 skipped**. Skips are Module 9 on-chain PostgreSQL integration tests only. `compileall` and `git diff --check` pass.
- Module 20 remains PARTIAL because no independent OCR/vision review of the AI-generated background or arbitrary embedded provider text is implemented; deterministic checks only prove the renderer-owned labels and geometry.
- Module 21 PostgreSQL feasibility check: `psycopg 3.3.9` installed only in `/tmp/binance-module11-test-venv`. PostgreSQL 16 binaries exist, but a temporary cluster could not bootstrap because this remote kernel does not implement `shmget` (`Function not implemented`). No PostgreSQL service/database was created; no production/Neon DB or paid infrastructure was touched. Module 21 still lacks a PostgreSQL adapter and isolated integration/concurrency/recovery tests.
- Latest worktree: 24 modified tracked files, zero untracked; branch/HEAD unchanged. No commit, push, merge, deployment, live DeepSeek/Cloudflare call, image upload or real Binance Square post. Keep all changes uncommitted and continue from this exact worktree.


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
- Continued in the active worktree `/tmp/binance-deepseek-verify`, branch `layer-1/module9-onchain-continuation`, HEAD `3fe895493ef35b8177b037eef382384c8392abb6`. All pre-existing modified files were preserved; no checkout/reset/clean, commit, push, merge or deployment.
- Read the current project context and gap register before work. The existing Neon project is `Binance-bot-staging` (`orange-glade-36037611`); reused the existing non-default disposable branch `module9-pg-lease-fencing-disposable` (`br-falling-butterfly-az03rryi`). No new branch, project, endpoint or compute was provisioned.
- Added `layer1/migrations/publication_postgresql/0001_publication_storage.sql` (additive DDL only) covering event lifecycle/revisions/transitions, research packages, editorial briefs, drafts, text/visual validation, image artifacts, opportunity decisions, publication attempts, quota reservations, immutable authorizations, reconciliation audit, posts, analytics, metrics and runs.
- Applied the same migration/checksum to the disposable branch's `binance_bot_staging` and `binance_onchain_test` databases. Version `0001_publication_storage.sql`, checksum `2f6533009591add7c0f83b3eb013d986e7191216ec598f0408161ed793de1eb0`. Read-only verification confirmed the migration record in both databases and zero rows in all new publication-critical ledgers; no existing announcement or Module 9 data was modified.
- Added `layer1/publication_postgres.py` as explicit-DSN-only opt-in persistence primitives. Implemented daily quota reservation under a transaction advisory lock, atomic per-symbol pending-attempt exclusion, idempotency-key/content binding, forward-only attempt/quota state transitions, pending-attempt recovery listing, and operator-evidenced reconciliation that updates attempt, quota and append-only audit in one transaction. This module does not read environment variables or replace the SQLite default.
- Added `tests/test_publication_postgres.py`: state-machine and migration contract tests pass; guarded live PostgreSQL tests cover concurrent quota reservation, same-symbol attempt fencing, idempotency binding and atomic reconciliation. The four live tests are skipped until `TEST_POSTGRES_DSN` is present.
- Full local suite after this checkpoint: **559 tests, 0 failures, 16 skipped**. The 12 existing skips are Module 9 PostgreSQL integration tests; the 4 new skips are Module 21 PostgreSQL integration tests because the active shell has no `TEST_POSTGRES_DSN`. `compileall` and `git diff --check` pass.
- Important DSN clarification: the earlier Module 9 test DSN was entered interactively in a previous `/tmp/binance-layer1-audit` shell session and explicitly unset after testing. It is not in the active `/tmp/binance-deepseek-verify` environment or a repo `.env` file. No secret value was recovered or printed. Neon MCP read-only/SQL operations were used instead for schema verification.
- Module 21 remains **PARTIAL**: the new migration and quota/attempt/reconciliation primitives are not yet wired into `PostPublisher`; PostgreSQL persistence methods for research/editorial/draft/event/authorization records, crash/restart integration, rollback/concurrency tests via the Python adapter, and end-to-end publisher recovery remain open. Production publisher, credentials, schedules, default staging branch and live Binance submission remain untouched.


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
- Added explicit-DSN `PostgresPublicationStore.observe_event_lifecycle()` and `load_event_lifecycle()` using the existing Module 21 event, revision and transition tables. The adapter uses a transaction-scoped advisory lock per event plus a row lock, enforces immutable event identity and revision payloads, validates the same forward-only lifecycle transition graph as the SQLite implementation, stores revision payloads/evidence references as JSONB, and returns ordered revision/transition history.
- Exact latest-revision replay is idempotent and creates no duplicate transition. Reuse of an older revision as a new transition or reuse of a revision hash with a conflicting payload is rejected. Initial lifecycle state must be `DISCOVERED`; later transitions must match the currently persisted state.
- Added deterministic validation and live PostgreSQL integration coverage for initial event creation, duplicate replay, append-only revisions, ordered transition history, conflicting revision payload rejection and illegal transition rejection.
- TDD caught two issues during live Neon verification: duplicate replay handling and the transition test's initially incorrect expectation (`UNDER_VERIFICATION` to `CONFIRMED` is an allowed transition). The test now asserts an actually illegal `DISCOVERED` to `CONFIRMED` transition.
- Verification on the existing disposable `binance_onchain_test` DB (host/database/TLS guarded, DSN loaded from local `.env` without printing secrets): `tests.test_publication_postgres` **17 passed, 0 failed, 0 skipped** (including a two-worker same-event transition race); `tests.test_event_lifecycle` **18 passed, 0 failed**; full repository suite **565 tests, 0 failures, 20 skipped** (run without PostgreSQL DSN; Module 21 PG integration was separately run with guarded DSN). No production/default branch, publisher, credentials, schedules, external provider or real Binance Square post was touched.
- PostgreSQL event-lifecycle adapter remains an opt-in persistence API; SQLite remains the runtime default. `PostPublisher`/draft/validation/image/opportunity/authorization runtime integration and crash/restart recovery across the full publication pipeline are still outstanding. Module 21 remains PARTIAL.

## Module 21 PostgreSQL draft and validation persistence — 2026-11-15
- Verified exact worktree before changes: `/tmp/binance-deepseek-verify`, branch `layer-1/module9-onchain-continuation`, HEAD `3fe895493ef35b8177b037eef382384c8392abb6`. Preserved every pre-existing modified/untracked file; no reset/clean or branch switch.
- Confirmed the PostgreSQL draft append-only API already existed in this worktree. Added a real two-worker concurrent draft-version regression: transaction-scoped advisory locking serializes writes and yields versions 1 and 2 without lost updates. Exact replay remains idempotent; provenance conflicts and FK mismatches are rejected.
- Added explicit-DSN PostgreSQL APIs `save_text_validation`, `save_visual_validation`, `load_latest_text_validation`, and `load_latest_visual_validation`. Validation records are append-only, canonical-hash identified, idempotent on exact replay, JSONB-backed, and queryable by draft hash / exact draft-image pair. New validator versions can record changed outcomes without overwriting history.
- Added deterministic input normalization/validation tests and live Neon integration tests for text/visual persistence, replay, revised outcome history and latest-record retrieval.
- Verification used only the host/database/TLS-guarded disposable `binance_onchain_test` DB, with DSN loaded programmatically from local mode-0600 `.env`; secret values were not printed. Full `tests.test_publication_postgres`: **22 passed, 0 failed, 0 skipped**. Draft/validation focused batch: **5 passed**. No production/default branch writes, publisher activation, credentials/schedules/workflow changes, provider calls, or real Binance Square posts.
- `PostPublisher` remains unintegrated with the PostgreSQL store; image artifact, opportunity decision, authorization persistence and end-to-end crash/restart recovery remain open. SQLite remains the runtime default. Module 21 is still PARTIAL. No commit, push, merge or deployment.


## Module 21 PostgreSQL image-artifact persistence — 2026-11-15
- Added explicit-DSN `PostgresPublicationStore.save_image_artifact()` and `load_image_artifact()` using the existing `image_generation_artifacts` table; no migration/schema change was needed.
- Added deterministic input validation for required metadata, approved Cloudflare Workers AI provider/model, canonical asset identity, lowercase SHA-256 hashes, timezone-aware generation time, bounded generation dimensions/format, output dimensions, non-empty path and finite JSON metadata.
- Persistence uses a transaction-scoped advisory lock on the exact draft/image pair, append-only immutable provenance, canonical artifact identity, exact replay idempotency and conflict rejection. Load returns the stored metadata and image path.
- TDD evidence: deterministic provider/hash rejection test and live disposable-Neon persistence/replay/conflict test both passed (**2/2**). Final complete `tests.test_publication_postgres`: **24 passed, 0 failed, 0 skipped** against the host/database/TLS-guarded disposable `binance_onchain_test` DB. `compileall -q layer1 tests` and `git diff --check` passed.
- Scope remains opt-in only; SQLite stays runtime default. Opportunity decision persistence, publication authorization persistence, `PostPublisher` backend integration, transaction rollback/cross-record concurrency, crash/restart and end-to-end durability remain open. Module 21 remains PARTIAL. No production publisher, credentials, schedules, provider inference, real Binance Square post, commit, push, merge or deployment.


## Module 21 PostgreSQL opportunity, authorization and atomic attempt ledger — 2026-11-15
- Added `save_opportunity_decision()` / `load_opportunity_decision()` with immutable digest verification, exact research-package FK binding, JSONB input snapshot persistence, replay idempotency and collision rejection.
- Added `save_publication_authorization()` / `load_publication_authorization()`. Persistence verifies the immutable authorization digest and bounded expiry, exact editorial-event/research binding, exact draft/content/claim provenance, text PASS, image artifact/current visual PASS when applicable, and a matching RESERVED quota row. Authorization insert and exclusive quota binding occur in one transaction.
- Added `begin_authorized_attempt()` and `finish_authorized_attempt()`. The first validates the persisted unexpired authorization and exact symbol/content hash, enforces one pending attempt per symbol, and atomically creates the SUBMITTING attempt plus moves its quota reservation to SUBMITTING. The finish operation atomically advances both ledgers. These are explicit opt-in APIs; they do not activate or replace the SQLite `PostPublisher`.
- TDD/live Neon evidence: opportunity persistence test **2/2 passed**; authorization + no-network atomic attempt/quota lifecycle test **1/1 passed**; complete `tests.test_publication_postgres` **27 passed, 0 failed, 0 skipped** on guarded disposable `binance_onchain_test`. One initial replay test exposed tuple/list JSONB normalization and was corrected; one test cleanup FK ordering issue was corrected. No live Binance API request was made.
- `compileall -q layer1 tests` and `git diff --check` passed after the implementation. Existing worktree branch/HEAD unchanged. SQLite remains runtime default. Module 21 is still PARTIAL because `PostPublisher` is not yet wired to these PostgreSQL primitives, full crash/restart and cross-record recovery drills remain open, and a production backend cutover has not been approved or tested.


## Module 21 continuation verification checkpoint — 2026-11-15
- Full repository suite run with PostgreSQL DSN intentionally unset: **575 tests ran, 0 failures, 26 skipped**. The Module 21 PostgreSQL integration suite was separately executed with the guarded disposable DSN and passed **27/27**.
- `compileall -q layer1 tests` and `git diff --check` passed after the latest implementation. Branch remains `layer-1/module9-onchain-continuation`; HEAD remains `3fe895493ef35b8177b037eef382384c8392abb6`.
- The 26 skips in the full-suite run are not proof of PostgreSQL integration; the separate 27-test live disposable-DB run is the evidence for the Module 21 adapter.
- `PostPublisher` is still SQLite-backed and has not been routed through the PostgreSQL methods. Do not describe Module 21 as complete or production-ready. No live Binance post, commit, push, merge, deployment, production database or credentials change.


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

### Module 21 interrupted SUBMITTING reconciliation hardening — 2026-11-15
- Review identified a recovery gap: a process can terminate after the durable attempt/quota transaction commits in `SUBMITTING`, leaving no evidence whether the outbound request reached Binance. Such a record must remain non-retryable and require operator verification.
- Added `validate_reconciliation_source_status()` and allowed operator reconciliation from either `SUBMITTING` or `PUBLICATION_UNKNOWN` to a confirmed terminal state. Terminal attempts remain non-reopenable; reconciliation still requires operator identity, evidence, note, and a bound active quota reservation, and updates attempt, quota, and audit event in one transaction.
- Added a pure state-policy test and a guarded disposable-PostgreSQL integration test that simulates restart from `SUBMITTING`, confirms the attempt remains pending/idempotency-fenced, then reconciles only after operator evidence. The live integration test was skipped because `TEST_POSTGRES_DSN` and `TEST_POSTGRES_ALLOWED_HOST` were unset; it is not counted as passed.
- Verification: publisher safety suite 25 passed; full repository suite 579 ran, 0 failed, 27 skipped. Static policy tests passed. No real Binance POST was made. No production database, credentials, publisher schedule, or workflow was changed. No commit, push, merge, or deploy.
- Module 21 remains PARTIAL pending guarded live PostgreSQL integration, publisher end-to-end verification, and broader acceptance evidence.

### Module 21 guarded live PostgreSQL verification — 2026-11-15
- Reused the existing Neon staging project `Binance-bot-staging`, existing disposable branch `module9-pg-lease-fencing-disposable` (`br-falling-butterfly-az03rryi`), and database `binance_onchain_test`. Retrieved the branch-scoped connection string through the connected Neon integration and passed it only to the remote test process; the DSN/password was not printed, persisted, or added to repository files.
- Guarded integration suite `tests.test_publication_postgres`: **29 passed, 0 failed, 0 skipped** against the disposable Neon database. This includes publication authorization persistence and the actual `PostPublisher(postgres_store=...)` flow with deterministic mocked Binance transport, successful attempt/quota terminal state, and duplicate invocation blocked without a second transport call.
- Also verified live concurrent quota reservations, same-symbol pending-attempt exclusion, content/idempotency binding, append-only research/editorial/draft persistence, concurrent draft version allocation, event revision/transition persistence and same-state race serialization, validation/image/opportunity persistence, crash/restart from both `SUBMITTING` and `PUBLICATION_UNKNOWN`, and operator reconciliation/audit consistency.
- The crash/restart tests close the original PostgreSQL connection and instantiate a fresh store before verifying durable pending state and non-retry behavior. Operator reconciliation is now allowed from `SUBMITTING` or `PUBLICATION_UNKNOWN`, with required operator/evidence/note and atomic attempt/quota/audit update.
- The publisher E2E uses a mocked transport only. No real Binance Square POST, live provider request, production/default database operation, credential/schedule change, or production publisher activation occurred.
- Full local suite after recovery hardening: **579 tests, 0 failures, 27 skipped** with PostgreSQL DSN unset. Separate live PostgreSQL module: **29/29 passed**. These are separate scopes and must not be combined into one count. `compileall` and `git diff --check` pass.
- Important isolation note: do not run `tests.test_onchain_postgres` against this shared disposable branch in this continuation; that older Module 9 suite truncates its on-chain tables in `setUp`. It was deliberately excluded to preserve the existing disposable branch's Module 9 test data. The Module 21 publication integration suite ran independently and passed.
- Module 21 backend integration is verified on the disposable branch, but SQLite remains the runtime default and no production cutover/deployment has been approved. Treat the PostgreSQL backend as integration-complete for this isolated test scope, not as production-enabled. No commit, push, merge, or deploy.


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


## Module 11 PostgreSQL claim-registry persistence checkpoint — 2026-11-15
- Added additive migration `0002_claim_verification_runs.sql` for table `layer1_claim_verification_runs`; the previously applied `0001_publication_storage.sql` checksum is preserved. The table stores immutable verification snapshots, stable SHA-256 identity, aggregate counts, and JSONB payload; a latest-snapshot index supports deterministic retrieval.
- Added `PostgresPublicationStore.save_claim_registry()` and `load_latest_claim_registry()`. Writes accept only the typed `ClaimRegistry`, use canonical JSON serialization and digest identity, are idempotent for identical payloads, and reject conflicting payload reuse.
- Added guarded integration coverage in `tests/test_claim_registry_postgres.py`. The test requires the exact disposable `binance_onchain_test` database, explicit allowed host, and TLS; it only deletes its own test rows by exact digest IDs.
- Commit: `527bcbec97a88c4238a5092930591fb941dc1ec5`. GitHub Actions run `43725080804`: **587 tests ran, 0 failed, 28 skipped**; compile and mocked safety job succeeded. The additional PostgreSQL integration test was skipped because `TEST_POSTGRES_DSN` is not configured in hosted CI. Therefore this run does not prove the migration or SQL methods against a live PostgreSQL server.
- This closes only the PostgreSQL persistence primitive for claim-registry snapshots. The normal runtime still uses SQLite, and `ClaimRegistryStore`, `EventLifecycleStore`, `ResearchPackageStore`, `EditorialBriefStore`, `DraftStore`, `OpportunityDecisionStore`, and `Layer1Store` are not yet unified behind a selected PostgreSQL runtime backend. Module 21 remains PARTIAL; no production cutover or publishing activation.
- No production database, credentials, schedules, GitHub Actions dispatch, live provider request, media upload, real Binance Square post, merge, or deployment was performed.


## 2026-11-15 — Explicit PostgreSQL runtime persistence wiring checkpoint

- Added explicit `PERSISTENCE_BACKEND=sqlite|postgresql` and `POSTGRES_DSN` configuration to the main application. SQLite remains the default. Selecting PostgreSQL without a non-empty DSN fails validation before runtime work; an explicitly selected PostgreSQL backend applies only the additive publication migration and does not silently fall back to SQLite.
- Added `layer1/publication_runtime.py` adapters for claim-registry snapshots, research packages, opportunity decisions, editorial briefs, drafts, image artifacts, text/visual validation, and publication authorization. The normal main runtime now passes one `PostgresPublicationStore` instance through the selected publication-critical persistence path and into `PostPublisher`.
- Added a guarded event-lifecycle snapshot mirror from the existing SQLite Layer1 foundation ledger into PostgreSQL. It copies the exact event identity, revision payloads, and ordered transition history; existing PostgreSQL history must be an exact prefix of the SQLite history, otherwise the mirror fails closed rather than overwriting divergent history. The PostgreSQL publication authorization therefore checks the mirrored exact event state for announcement-driven posts.
- The base Layer1 market/foundation store, run lease, and legacy post/analytics records remain SQLite. This checkpoint does not claim that every subsystem has been migrated to PostgreSQL; it routes publication provenance, authorization, quota, and attempt records through the selected PostgreSQL backend while preserving the existing discovery foundation.
- Added unit coverage for backend selection and adapters, plus a guarded PostgreSQL event-snapshot mirror integration test. Local verification after the runtime wiring: **595 tests ran, 0 failed, 28 skipped**; focused follow-up after the last small adapter correction: **15 tests ran, 0 failed, 5 skipped**. `compileall` and `git diff --check` passed. The guarded PostgreSQL integration tests remain skipped in this environment because `TEST_POSTGRES_DSN` is unset; the new runtime adapters and event mirror have not yet been verified against a live PostgreSQL instance in this checkpoint.
- `scripts/reconcile_publications.py` remains SQLite-only and still needs a PostgreSQL mode before this runtime path is operationally complete. The opportunity engine still deliberately defers when the approved scoring policy is absent; no weights or thresholds were invented.
- No production credentials, schedules, workflows, publisher activation, live provider calls, real Binance Square POST, merge, or deployment were performed. No commit or push has been made in this checkpoint.

- Migration checksum correction: live disposable Neon verification showed that adding the claim-registry table to already-applied migration 0001 changed its checksum. Restored 0001 byte-for-byte from the pre-claim-registry commit and moved the table/index into new additive migration 0002. This preserves existing migration history and lets the shared disposable branch apply the new table without rewriting the old migration.

## Module 21 PostgreSQL operator reconciliation support — 2026-11-15
- Extended `scripts/reconcile_publications.py` with explicit `--backend sqlite|postgresql` selection and `--postgres-dsn` support, including `PERSISTENCE_BACKEND` / `POSTGRES_DSN` environment configuration. SQLite remains the default. Selecting PostgreSQL without a DSN fails closed; it never silently opens SQLite.
- PostgreSQL `list` and `show` now use the publication store's pending-attempt and exact-attempt lookup APIs. PostgreSQL `confirm-published` / `confirm-failed` use `PostgresPublicationStore.reconcile_attempt()`, preserving the existing single-transaction attempt + quota + audit update. This remains an operator-only path: it performs no HTTP request, publish, retry, or automatic reconciliation.
- Added `get_attempt()` and strengthened PostgreSQL reconciliation identity checks: conflicting known remote IDs are rejected; a known remote ID cannot be marked as a confirmed failure; an existing share link cannot be rebound; verified Binance Square share links are persisted with the confirmed remote ID. The existing SQLite reconciliation path remains intact.
- TDD coverage: new CLI/backend tests cover SQLite default, explicit PostgreSQL DSN requirement/no fallback, PostgreSQL list/show, both operator decisions, and remote-ID conflict rejection. Guarded Neon integration coverage verifies share-link persistence, atomic quota/audit updates, and conflict rejection without mutation.
- Verification: PostgreSQL CLI read-only `list` smoke test against the disposable `binance_onchain_test` branch returned `No unresolved publication attempts`. Focused regression batch: **74 passed, 0 failed** (includes guarded live Neon PostgreSQL tests, publisher safety, and runtime adapter tests). Full local suite with PostgreSQL environment variables unset: **606 tests ran, 0 failed, 30 skipped**; the guarded PostgreSQL skips are not counted as passes. `compileall` and `git diff --check` passed.
- No real Binance Square POST, provider request, production database write, credential/schedule/workflow change, publisher activation, merge, or deployment was performed. Changes are local and uncommitted; no GitHub commit or push was made.
- Module 21 remains **PARTIAL** pending the remaining end-to-end runtime acceptance and production-readiness review. PostgreSQL operator reconciliation support is implemented and verified only in the isolated staging/test scope; SQLite remains the runtime default and no production cutover is approved.


## Module 21 PostgreSQL runtime authorization-to-publisher E2E verification — 2026-11-15
- Strengthened the guarded Neon integration test to exercise the actual `PostgresPublicationAuthorizationEngine` rather than manually constructing a `PublicationAuthorization`. The test now persists research package, editorial brief, exact draft, and PASS text validation; reserves quota through the adapter; creates/persists authorization through the adapter; and passes that authorization to the real `PostPublisher(postgres_store=...)`.
- The Binance transport is replaced with a deterministic mocked response. The test verifies one transport call, PostgreSQL attempt and quota reaching `PUBLISHED_CONFIRMED`, a second identical invocation returning `DUPLICATE_BLOCKED` without another transport call, and zero rows in SQLite's publication-attempt ledger. The test disables local post-file output so the integration run leaves no local publication artifact.
- Updated guarded Neon test: **1 passed, 0 failed** after the change. Before strengthening this test, the complete guarded `tests.test_publication_postgres` suite passed **31/31**. Full local unittest suite with PostgreSQL variables unset: **606 tests, 0 failures, 30 skipped**; those 30 skips are guarded PostgreSQL tests, not passes. Runtime adapter + publisher safety batch: **33 passed, 0 failed**. `compileall` and `git diff --check` passed.
- Runtime source inspection confirmed the explicit PostgreSQL store is passed into the publication runtime adapters and `PostPublisher`; the base Layer1 foundation/run-lease and legacy post/analytics records remain SQLite. This is publication-critical-path E2E evidence, not a full end-to-end run of the market-discovery/provider/media pipeline.
- No real Binance Square POST, live provider request, production database write, production publisher activation, credential/schedule/workflow change, merge, or deployment occurred. SQLite remains the default backend; no production cutover is approved. Changes are local and uncommitted. Module 21 remains **PARTIAL** pending broader runtime and production-readiness acceptance.


## Module 21 PostgreSQL acceptance verification follow-up — 2026-11-15
- Re-verified repository state before testing: isolated `/tmp/binance-runtime-fix` is detached at `9ce1baa7d6455a4e1f701ff5532dea42faa67952`, clean; `origin/layer-1/module9-onchain-continuation` resolves to the same SHA. PR #14 is still open, draft, and unmerged. Other worktrees were left untouched.
- Connected only to the documented disposable Neon `binance_onchain_test` branch using the `Binance bot` Neon connection. The guarded command supplied the exact DSN host as `TEST_POSTGRES_ALLOWED_HOST`; no DSN/password was printed. Ran `tests.test_claim_registry_postgres` plus `tests.test_publication_postgres`: **32 tests passed, 0 failed**. This includes the full guarded publication integration suite, including authorization-to-publisher mocked-transport E2E, concurrency, and interrupted-attempt reconciliation. Test cleanup is scoped to each generated test identity; the Module 9 on-chain PostgreSQL suite was not run because it truncates shared on-chain tables.
- Focused local publication/runtime/publisher/reconciliation batch: **73 tests, 0 failures, 17 skipped** with PostgreSQL DSN unset. Full local unittest discovery with PostgreSQL variables unset: **606 tests, 0 failures, 30 skipped**. Skips are guarded PostgreSQL tests and are not counted as passes; the separate 32/32 Neon run is reported independently.
- `compileall -q main.py layer1 scripts tests` and `git diff --check` passed. No source-code changes were required in this acceptance pass; this section records the new verification evidence.
- Scope boundary confirmed by source inspection: PostgreSQL is explicit opt-in and only publication-critical persistence (claim registry, research package, editorial brief, opportunity decision, draft/validation/image artifacts, authorization, quota, attempt and reconciliation) uses the PostgreSQL store. Layer1 discovery/foundation data, run leases, and legacy post/analytics records remain SQLite. SQLite is still the default. The complete market-discovery/provider/media pipeline has not been run end-to-end with PostgreSQL selected.
- PR #14 metadata currently lists unresolved acceptance gaps: scheduled workflow has not been observed running against real DeepSeek/Cloudflare credentials; live DeepSeek inference and authenticated Cloudflare image generation are unverified; authenticated Binance media upload/publishing is unverified; no production cutover is authorized. Module 21 remains **PARTIAL**, not production-ready.
- No real Binance Square POST, live provider request, production DB write, publisher activation, credential/schedule/workflow change, merge, deployment, commit, or push occurred in this follow-up.

## Module 21 PostgreSQL run-lease persistence checkpoint — 2026-11-15
- Audit found that `run_once()` still constructed `layer1.foundation.RunLease` against `DATABASE_PATH` even when `PERSISTENCE_BACKEND=postgresql`. This left cross-instance run ownership in a local SQLite file while publication authorization/quota/attempt records used PostgreSQL.
- Added additive migration `0003_layer1_run_lease.sql` for PostgreSQL `layer1_runs` and the singleton `layer1_run_lease`. Existing migrations 0001/0002 were not edited. The PostgreSQL store now acquires the logical agent lease under a transaction-scoped advisory lock, inserts run + lease atomically, inspects the active run, and finalizes run status + lease deletion in one transaction. Finalization rejects lost ownership and invalid/non-finite summary payloads.
- Added `PostgresRunLease` adapter sharing the existing `PostgresPublicationStore` connection; adapter close does not close the application-owned shared connection. `main.run_once()` now selects it only for explicit PostgreSQL configuration. If PostgreSQL is selected but the runtime store is missing, it fails closed instead of falling back to SQLite. SQLite selection retains the existing `RunLease` path. The backend selection is included in the secret-free run configuration fingerprint.
- TDD: the new PostgreSQL-without-store regression was observed failing before the fail-closed check and passing after it. Adapter, migration, SQLite compatibility, backend selection and no-fallback focused tests passed.
- Guarded disposable Neon integration on the existing `binance_onchain_test` branch: **2 passed, 0 failed**. One test verified durable run creation, active-lease inspection, overlap rejection and atomic successful finish. A second used two independent PostgreSQL connections concurrently and verified exactly one `ACQUIRED` and one `BLOCKED` result. Test rows were removed by their exact generated run IDs. No shared Module 9 on-chain tables were touched.
- Full local suite after the final fail-closed refinement: **613 tests ran, 0 failures, 32 skipped** with PostgreSQL environment variables unset. The 32 skips are guarded PostgreSQL integration tests, not passes. `compileall -q main.py layer1 scripts tests` and `git diff --check` passed.
- Scope remains deliberately partial: `Layer1Store` market/discovery/evidence/cache records and legacy `Database` post/analytics history still use SQLite; event lifecycle is mirrored from SQLite into PostgreSQL for publication-time authorization. Live DeepSeek inference, authenticated Cloudflare image generation, Binance media upload, scheduled workflow execution and production publishing remain unverified. SQLite remains the default; no production cutover is authorized.
- No real Binance Square POST, live content-provider request, production database write, production credential/schedule/workflow change, publisher activation, merge, deployment, commit or push occurred. Changes remain local and uncommitted in the isolated worktree.

## Module 21 follow-on persistence boundary audit — 2026-11-15
- Post-run-lease audit mapped the remaining runtime persistence surface. `Layer1Store` in `layer1/foundation.py` has 13 SQLite-bound methods covering market observations/history, market analyses, identity-proof cache, announcement evidence/revisions, trend signals/clusters, candidates, rejections and scores. `_persist_layer1_market_intelligence()` still constructs it directly from `DATABASE_PATH` even when a PostgreSQL publication store is supplied.
- This is not an isolated constructor swap: the current `EventIntelligenceGraphEngine.rebuild_from_store()`, `EvidenceVerificationEngine.rebuild_from_store()`, `ClaimRegistryStore`, and `EventLifecycleStore` consume the SQLite connection or SQLite-specific query behavior. Claim-registry snapshots are additionally written to PostgreSQL and event lifecycle is mirrored, but the authoritative discovery/evidence tables and graph rebuild still originate from SQLite.
- The legacy `Database` surface in `main.py` has 13 SQLite methods. `PostPublisher` constructs `Database(config.database_path)` unconditionally, and the runtime still uses it for posted-symbol/history reads and legacy post/analytics paths. `PerformanceAnalyzer` executes SQLite-specific SQL (including `strftime` and `?` placeholders). The Module 21 migration includes legacy `posts`, `post_analytics`, `metrics` and `runs` tables, but these tables are not a complete runtime adapter for the legacy `Database` contract.
- Therefore, `PERSISTENCE_BACKEND=postgresql` currently means publication-critical provenance/authorization/quota/attempt/reconciliation plus the new run lease are PostgreSQL-backed; it does **not** mean the complete discovery, evidence, graph, post-history and analytics runtime is PostgreSQL-backed. Do not claim otherwise or perform a production cutover.
- Next bounded architecture task: define a store-neutral contract for the Layer1 discovery/evidence persistence API, then add a PostgreSQL implementation and migrate the graph/claim/event-lifecycle consumers with TDD and isolated PostgreSQL integration tests. Only after that should the legacy `Database`/analytics path be ported. Avoid a raw `sqlite3.Connection` substitution: current consumers depend on SQLite-specific SQL and connection semantics.
- Current isolated worktree `/tmp/binance-runtime-fix` remains detached at `637f8e6dbb4f6d9c712473d92fef18c590985f4c`; remote `origin/layer-1/module9-onchain-continuation` was rechecked at the same SHA. PR #14 remains open/draft/unmerged per the prior verified metadata. All current run-lease and documentation changes are local/uncommitted; no commit, push, merge or deployment was performed.

## Module 21 store-neutral source-read contract — 2026-11-15 continuation
- Reverified on Remote Desktop Commander device `e87fd591-3c93-40d6-8543-95eabff1ca2f`: `/tmp/binance-runtime-fix` is detached at `8b609ce29597cc36d4c1839f3c302f8d607e1fd6`, with no pre-existing working-tree changes. The live GitHub remote branch `layer-1/module9-onchain-continuation` resolves to this same SHA. The local remote-tracking ref is stale at `8b1783dda9a21d23257843f37e21b0b5423333f3`; do not use it as the current remote SHA. PR #14 was fetched from GitHub and is OPEN; its body identifies it as a Draft PR. It remains unmerged. No Actions workflow runs were returned for commit `8b609ce`.
- `/tmp/binance-layer1-audit` contains extensive pre-existing user changes (including Module 9 source, tests, workflow, and `.venv`); it was not modified. `/tmp/binance-deepseek-verify` is clean at `6b18621660996c25547593f7f52ae2ee6d94352f` and was not modified. The test venv `/tmp/binance-module11-test-venv/bin/python` exists.
- Added the first store-neutral source-read boundary to `Layer1Store`: `iter_announcement_revisions()`, `iter_market_observations()`, and `iter_trend_signals()`. Each returns validated domain records in the same deterministic SQL ordering previously embedded in graph/evidence consumers.
- Migrated `EventIntelligenceGraphEngine.rebuild_from_store()` and `EvidenceVerificationEngine.rebuild_from_store()` to consume these methods instead of reaching into `store.conn` and issuing SQLite-specific SQL. Both consumers fail closed with a clear `TypeError` if the required contract methods are absent. This is an additive API refactor; SQLite persistence behavior and source provenance remain unchanged.
- TDD: the new contract regression first failed because the methods did not exist; after implementation it passed. Focused Layer1 foundation, event graph, evidence verification and event lifecycle suites: **182 passed, 0 failed**. Full local unittest discovery: **614 tests ran, 0 failures, 32 skipped**; the 32 skips are guarded PostgreSQL integration tests and are not passes. `compileall -q main.py layer1 scripts tests` and `git diff --check` passed. No PostgreSQL integration test was run in this bounded step, and no PostgreSQL Layer1 adapter or migration has been implemented yet.
- Remaining store-neutral work: PostgreSQL implementations for these reads and all Layer1 writes/history/cache/analysis operations; `ClaimRegistryStore` and `EventLifecycleStore` still have SQLite connection assumptions; runtime construction still creates `Layer1Store` from `DATABASE_PATH`. Legacy `Database` and analytics remain SQLite. Module 21 is still **PARTIAL**.
- No credentials or DSNs were displayed. No production database, provider, Binance transport, publisher, workflow, schedule, or credentials were touched. No commit, push, merge, or deployment was performed.

## Module 21 PostgreSQL Layer1 discovery store — 2026-11-15 continuation
- Added additive migration `0004_layer1_discovery_store.sql` with PostgreSQL tables/indexes for market observations/history, market analyses, identity-proof cache, announcement current/revision records, trend signals/clusters, candidates, candidate rejections and candidate scores. Existing migrations 0001–0003 were not modified. No destructive DDL or data-clearing statement is present.
- Added `PostgresLayer1Store` in `layer1/layer1_postgres.py`. It implements the existing Layer1 persistence operations with PostgreSQL placeholders, JSONB payloads, deterministic read ordering and transaction-scoped writes. Domain records are validated before persistence and after deserialization. Identity-proof expiry and announcement revision append-only semantics are preserved. The adapter receives the application-owned psycopg connection; `close()` is a no-op and never closes that shared connection.
- Added guarded integration coverage in `tests/test_layer1_postgres.py` for round-tripping identity proof, market observation/history, announcement revisions, trend signals, market analysis, trend clusters, candidates, rejection records and relevance scores. Test guard requires exact database `binance_onchain_test`, exact `TEST_POSTGRES_ALLOWED_HOST`, and TLS. Cleanup is scoped to unique generated identifiers.
- Verified the migration and round-trip integration against the existing disposable Neon branch `br-falling-butterfly-az03rryi` / database `binance_onchain_test`: **1 passed, 0 failed**. The temporary DSN was kept out of output and removed from the remote temp filesystem after the run. The environment did not have persistent `TEST_POSTGRES_DSN` or `TEST_POSTGRES_ALLOWED_HOST` variables configured; the guarded one-off test supplied them only for that process.
- Added contract/migration tests for explicit connection ownership, shared-connection close behavior, and additive migration contents. Focused regression batch: **7 tests, 0 failures, 1 skipped** (the integration test skipped in the no-DSN process; it had already passed in the separately guarded Neon run). Full local suite with PostgreSQL environment variables unset: **618 tests ran, 0 failures, 33 skipped**; all 33 are guarded skips, not passes. `compileall -q main.py layer1 scripts tests` and `git diff --check` passed.
- This completes the PostgreSQL Layer1 store implementation slice, not full runtime cutover. `main._persist_layer1_market_intelligence()` still constructs SQLite `Layer1Store`; `ClaimRegistryStore` and `EventLifecycleStore` still need backend-neutral integration; graph/evidence reads are contract-based but no full PostgreSQL runtime path has been wired. Legacy `Database`/analytics remain SQLite. Module 21 remains **PARTIAL**.
- No production database, live provider, Binance POST, production publisher, credentials, schedules, workflow, merge or deployment were touched.

## Module 21 PostgreSQL Layer1 runtime routing — 2026-11-15 continuation
- `_persist_layer1_market_intelligence()` now selects `PostgresLayer1Store(postgres_store.conn)` when the application supplies its explicit PostgreSQL publication store; SQLite `Layer1Store` remains the default when no PostgreSQL store is supplied. All discovery/market/evidence/cache/candidate/score writes and graph/evidence source reads in that runtime function now use the selected store.
- In PostgreSQL mode, the base claim-verification snapshot is written through `PostgresClaimRegistryStore` only. The former duplicate SQLite claim-registry write is removed. Per-asset claim snapshots in `_attach_claim_register()` also avoid opening an unused SQLite claim connection when PostgreSQL is selected.
- Event lifecycle is an explicitly transitional exception: `EventLifecycleStore` still implements a SQLite state machine, so PostgreSQL mode gives it a dedicated SQLite connection and mirrors the exact append-only revision/transition snapshot to PostgreSQL using the existing divergence checks. It no longer shares or reaches into the PostgreSQL discovery-store connection. `EventLifecycleStore` now accepts a direct existing SQLite connection as well as a Layer1Store wrapper. Native PostgreSQL event-lifecycle ownership remains the next persistence task; this path is not described as a full single-store cutover.
- Added TDD regression: direct SQLite connection support failed before the constructor change and passed afterward. Added runtime routing regression with a fake publication store verifying `PostgresLayer1Store` receives the application's shared connection, claim registry is written through the PostgreSQL adapter, and the SQLite claim-verification table is not created. Focused foundation + graph + evidence + lifecycle + adapter contract suites: **187 passed, 0 failed**.
- Full local unittest discovery: **620 tests ran, 0 failures, 33 skipped**; 33 guarded PostgreSQL skips are not passes. `compileall -q main.py layer1 scripts tests` and `git diff --check` passed. The real Neon Layer1 adapter integration remains separately verified **1/1 passed** in the prior implementation slice; this runtime-routing slice was tested locally with deterministic adapters and did not execute a real provider or publication path.
- No production database, live provider, Binance POST, production publisher, credentials, schedules, workflow, merge or deployment were touched. Module 21 remains **PARTIAL**.

## Module 21 PostgreSQL legacy post-history and analytics — 2026-11-15 continuation
- Added `PostgresLegacyDatabase` in `layer1/legacy_postgres.py`, implementing the legacy `Database` public contract against existing PostgreSQL `posts`, `metrics`, `runs`, and `post_analytics` tables: save post/metrics/run, recent posts, posted-symbol history, per-symbol count, posted-hours map, UTC daily analytics count, and top performers. JSON metadata/summary use JSONB; timestamps use `TIMESTAMPTZ`; all writes are transaction-scoped. `close()` does not close the application-owned PostgreSQL connection.
- Added `PostgresPerformanceAnalyzer` in `main.py` for PostgreSQL `record_publish`, exact-remote-ID metrics updates, and insight summaries. SQLite `strftime` was replaced with PostgreSQL `EXTRACT(HOUR FROM created_at AT TIME ZONE 'UTC')`. The original `PerformanceAnalyzer` remains unchanged for SQLite mode except it now records the optional local post ID.
- `PostPublisher` now selects `PostgresLegacyDatabase` when given the real PostgreSQL publication store. PostgreSQL mode no longer opens a SQLite `Database` at all; the only remaining SQLite read is the read-only, mode=ro one-time event-lifecycle bootstrap when a legacy DB file already exists. SQLite-only raw connection call sites remain behind the explicit SQLite branch. `main()` and `main_loop()` now use `publisher.db` rather than constructing a second `Database`.
- The PostgreSQL publisher path now persists the confirmed remote post identity in `posts` after first recording the attempt as `PUBLICATION_UNKNOWN`, and before finalizing the attempt as `PUBLISHED_CONFIRMED`. If the post-history write fails, the attempt remains recoverable as unknown with the remote ID already durable. `PerformanceAnalyzer` records its analytics row with the exact local post ID.
- Guarded disposable Neon integration: **1 passed** for post/history/metrics/runs/analytics CRUD and analyzer insights; **1 passed** for the actual PostgreSQL-authorized publisher with a deterministic mocked Binance transport, including durable `posts` row, terminal attempt/quota state, duplicate-submit block, and confirmation that no SQLite database file was created. No real Binance HTTP POST occurred.
- Guarded disposable Neon runtime-routing integration added: the actual `_persist_layer1_market_intelligence()` was executed with a real `PostgresPublicationStore`, real `PostgresLayer1Store`, `PostgresClaimRegistryStore`, and `PostgresEventLifecycleStore`, with external announcement DB disabled and an empty candidate fixture. It persisted the claim snapshot in PostgreSQL and verified that no SQLite database file was created: **1 passed**. The Layer1 adapter round-trip Neon test also passed in the same run: **1 passed**.
- Full local unittest discovery after this runtime integration regression: **628 tests ran, 0 failures, 37 skipped**; the 37 are guarded PostgreSQL integration skips, not passes. Focused publisher safety + adapter/runtime batch: **28 passed, 0 failed**. `compileall -q main.py layer1 scripts tests` and `git diff --check` passed.
- Remaining work is acceptance, not an identified SQLite persistence gap: guarded full-runtime PostgreSQL execution with provider stubs/fixtures, direct live DeepSeek and authenticated Cloudflare acceptance, Binance media upload verification, scheduled workflow execution, and explicit owner-approved production cutover. No production DB, live provider, real Binance POST, production publisher, credentials, schedules, workflow, merge or deployment were touched. Module 21 remains **PARTIAL** until end-to-end acceptance is independently demonstrated.

## Module 12 semantic event revision classifier — 2026-11-16 continuation
- Reproduced a false-positive lifecycle transition: a paraphrase that preserved the same Binance listing date/time but changed grammar caused `CONFIRMED -> DEVELOPING` under the prior raw-normalized-text comparator.
- Added deterministic `_semantic_material_tokens()` in `layer1/event_lifecycle.py`. It removes a bounded set of grammatical stopwords and canonicalizes explicit inflection groups for announcement/listing/start/postpone/cancel/suspend/resume/delist/open/close/update. It preserves token order, negation, named entities, numbers, dates, times and status/action words. The comparator remains conservative: any substantive ordered-token difference is material; it does not claim general NLP semantic equivalence.
- Title and body revisions now use this comparator; `event_type` and effective `event_at` comparisons remain unchanged. Source content hashes and source update timestamps alone remain non-material. PostgreSQL inherits the exact same classifier through `PostgresEventLifecycleStore`.
- Regression evidence: new test first failed (`DEVELOPING` instead of expected `CONFIRMED`) before implementation. After implementation, SQLite lifecycle suite: **23 passed**; combined local event lifecycle + PostgreSQL adapter contract tests: **25 passed**. Guarded disposable Neon event lifecycle integration: **3 passed**, including semantic paraphrase no-op and trading-suspension material transition.
- Full local suite: **631 tests, 0 failures, 38 skipped** (guarded PostgreSQL skips, not passes). `compileall -q main.py layer1 scripts tests` and `git diff --check` passed.
- This closes the specific deterministic paraphrase/status revision gap, not the entire semantic evidence-verification acceptance gap. Causal/compound claim coverage, sentence-to-evidence attribution acceptance, live provider acceptance and complete end-to-end publication remain separate open gates. No live Binance POST, production database, credentials, schedules, workflow, merge or deployment was used.

## Module 21 PostgreSQL-native event lifecycle — 2026-11-15 continuation
- Added `PostgresEventLifecycleStore` in `layer1/event_lifecycle_postgres.py`, reusing the existing publication PostgreSQL connection and existing `layer1_event_lifecycle`, `layer1_event_revisions`, and `layer1_event_transitions` tables. No additional migration was needed because migration 0001 already defines these tables and their transition constraints.
- Ported the lifecycle state machine with transaction-scoped advisory locking, row locking, atomic current-state + append-only revision/transition writes, duplicate replay handling, verification-driven state changes, material-revision handling, stale transitions, exact source lookup, latest-by-asset lookup and history reads. `sync_announcements()` now consumes the same claim-registry attribution logic while reading/writing PostgreSQL directly.
- Added a guarded one-time compatibility bootstrap: on PostgreSQL runtime startup, legacy SQLite lifecycle event IDs are inspected; only IDs absent from PostgreSQL are imported through the existing exact-prefix/divergence-checking snapshot importer. Once present, PostgreSQL is authoritative and stale SQLite snapshots are not replayed over it. The SQLite connection is read-only for this bootstrap and is closed in the runtime `finally` block.
- `_persist_layer1_market_intelligence()` now uses `PostgresEventLifecycleStore` in PostgreSQL mode and no longer writes or mirrors event lifecycle transitions to SQLite. Publication authorization already reads the PostgreSQL lifecycle record, so its state check now sees the same authoritative store. SQLite mode continues using the original `EventLifecycleStore` unchanged.
- Guarded disposable Neon integration: **2 passed, 0 failed**. Verified native PostgreSQL first observation, verification transition, confirmation, material revision to DEVELOPING, duplicate replay idempotency, SQLite legacy snapshot import, exact record round-trip and second-bootstrap no-op. Cleanup was limited to exact generated event IDs.
- Focused local runtime/lifecycle tests: **24 passed, 0 failed**. Full local unittest discovery: **624 tests ran, 0 failures, 35 skipped**; the 35 are guarded PostgreSQL skips and are not passes. `compileall -q main.py layer1 scripts tests` and `git diff --check` passed.
- This closes the event-lifecycle SQLite dependency for explicit PostgreSQL runtime mode. The next legacy post-history/analytics slice is documented below; until that slice is verified, do not claim the complete runtime persistence contract is PostgreSQL-backed. No production cutover or live publication occurred.

## Module 11 causal/compound claim evidence guard — 2026-11-16 continuation
- Reproduced two evidence-laundering defects before implementation: a `market.price` claim whose text added an unsupported `because` clause, and a claim combining an exact price plus an independent volume movement, both reached `VERIFIED` using only the price evidence. A third test showed that arbitrary causal text could be typed as `announcement.body` and inherit a direct-source exception without matching the canonical source-assertion text.
- Added bounded causal-relation phrase detection in `layer1/evidence_verification.py` and reused `split_atomic_claims()` to identify multiple independent propositions. A single typed field/value cannot verify either a causal relation or multiple atomic propositions; the result is `UNVERIFIED` with explicit issue codes `CAUSAL_RELATION_REQUIRES_DIRECT_SOURCE_ASSERTION` and/or `COMPOUND_CLAIM_REQUIRES_ATOMIC_EVIDENCE`.
- Narrow exception: an explicitly typed `SOURCE_ASSERTION` under `announcement.title` or `announcement.body` may retain causal/compound source wording only when accepted linked evidence has the exact same source key, subject, asset and value, and the claim text exactly matches the canonical rendered source-assertion form. Arbitrary claim text cannot borrow that exception.
- Added tests for passive and active causal wording, compound propositions, exact attributed primary announcement body assertions, and attempted laundering under the announcement-body key. The first causal, compound and laundering tests failed before the fix (`VERIFIED` instead of `UNVERIFIED`) and passed after it. Evidence-verification module: **55 passed**.
- Full local unittest discovery: **636 tests, 0 failures, 38 skipped** (guarded PostgreSQL skips, not passes). `compileall -q main.py layer1 scripts tests` and `git diff --check` passed.
- This is a deterministic phrase/atomic-clause guard, not general natural-language causal reasoning. Unsupported causal paraphrases outside the bounded phrase list and clauses not recognized by the atomic splitter remain a limitation. Full generated-post attribution and end-to-end acceptance remain open. No live provider, Binance POST, production database, credentials, schedules, workflow, merge or deployment was used.

## Module 11 generated-post causal attribution integration — 2026-11-16
- Added an end-to-end deterministic regression from typed market evidence -> `EvidenceVerificationEngine.verify()` -> `ContentVerificationEngine.validate()`. A draft that carries the correct claim marker but appends an unsupported causal clause is rejected because the underlying claim is unresolved; the generated-post gate also reports the unresolved asset claim.
- This verifies the evidence-level causal/compound guard is enforced at the actual draft validation boundary, not only in an isolated unit test. No provider inference or publisher transport is called.
- Full local suite after this integration test: **637 tests, 0 failures, 38 skipped** (guarded PostgreSQL skips, not passes). Compileall and diff-check passed.

## Module 11 one-to-one generated sentence attribution — 2026-11-16
- Added a positive-path draft validation integration test with two distinct verified market claims. Each factual sentence carries its own claim ID, and the validator returns PASS with exactly those two approved claim IDs. The prior negative-path causal test remains and rejects unsupported causal text even when it carries a syntactically valid claim marker.
- Full local suite after both positive and negative attribution cases: **638 tests, 0 failures, 38 skipped** (guarded PostgreSQL skips, not passes). Compileall and diff-check passed.

## Module 19/21 Binance media-upload acknowledgement hardening — 2026-11-16
- Audited the existing Cloudflare image-generation → visual QA → publication authorization → Binance Square media-upload path and its regression tests. Found that `ImageUploader._upload_to_presigned_url()` returned success for every HTTP response status even though its own contract/comment specified HTTP 200 or 201. This could allow `/image/imageStatus` polling to proceed after a storage PUT that was not confirmed as complete.
- Added a regression test first; it reproduced false success for HTTP 202, 204, 302, 400 and 500. Updated the uploader to accept only HTTP 200/201 and fail closed for every other returned status. Existing no-redirect transport and presigned-host allowlist remain in force.
- Focused image-generation + deterministic end-to-end pipeline suite: **17 passed, 0 failed**. No real Cloudflare inference, Binance media upload, Binance POST, credentials, production DB, workflow/schedule change, merge or deployment occurred.
- Full repository unittest discovery completed: **639 tests, 0 failures, 38 skipped** (guarded PostgreSQL integration skips, not passes). `compileall -q main.py image_engine.py layer1 scripts tests` and `git diff --check` passed. Module 19/21 remain **PARTIAL** because authenticated provider/media acceptance and scheduled runtime evidence are still outstanding.

## Module 19 Binance media-upload sequence regression — 2026-11-16
- Added deterministic orchestration coverage for the existing Binance Square media flow. The success case asserts strict order: presigned URL request → binary storage PUT → image-status poll → Binance CDN URL return. The failure case asserts that an unconfirmed storage PUT stops the flow and image-status polling is never called.
- The tests stub all network-facing methods; they do not contact Binance or upload an image. Focused image-generation suite: **18 passed, 0 failed**. Full repository unittest discovery: **641 tests, 0 failures, 38 skipped** (guarded PostgreSQL integration skips, not passes). Compileall and diff-check passed.
- Combined with commit `d5e24751`, this proves deterministic status handling and media-flow sequencing locally only. Authenticated Binance media upload and provider-backed scheduled execution remain unverified; Modules 19–21 remain PARTIAL.

## 2026-11-16 PostgreSQL acceptance continuation
- Located the existing guarded test environment at `/tmp/binance-deepseek-verify/.env` (mode `0600`). It contains only `TEST_POSTGRES_DSN` and `TEST_POSTGRES_ALLOWED_HOST`; secret values were not printed, copied into docs, or moved. The active working repository remains `/tmp/binance-runtime-fix`; the env file is in a separate worktree and was read programmatically for the test process only.
- Verified the DSN scheme, exact allowlisted Neon hostname, database name `binance_onchain_test`, and `sslmode=require`; an actual psycopg connection confirmed `binance_onchain_test` / `public`.
- Ran `tests.test_publication_postgres` against the disposable Neon database: **34 tests passed, 0 failures, 0 skips** (127.19 seconds). This includes the guarded PostgreSQL publication adapter/reconciliation/publisher tests with deterministic mocked Binance transport; it is not a real Binance publication.
- A broader batch covering Layer1, claim-registry, event-lifecycle and legacy PostgreSQL modules was interrupted while waiting inside the semantic event-lifecycle integration test. It is not counted as a pass. The interrupted test was then rerun individually with bounded PostgreSQL statement/lock timeouts and passed: **1/1**. No destructive `tests.test_onchain_postgres` suite was run because it truncates Module 9 on-chain tables.
- Verified GitHub branch `layer-1/module9-onchain-continuation` still resolves to `0c0b530c6dd8f7353dc0c7ecd6d4b78ae667d7a7`; active working tree was clean and no application code changed during this continuation.
- Remaining acceptance blocker: the located `.env` contains no DeepSeek, Cloudflare or announcement-database credentials. Earlier remote environment inspection also found those provider variables unset. Therefore authenticated DeepSeek generation, Cloudflare inference, external announcement ingestion and actual Binance media upload remain unverified. Do not trigger the scheduled GitHub workflow or any live provider/publisher path without explicit authorization.
- Production publisher remains inactive; no real Binance Square post, production DB operation, credential/schedule/workflow modification, merge or deployment occurred.

## 2026-11-16 GitHub continuation checkpoint — context synchronization
- Canonical GitHub branch: `layer-1/module9-onchain-continuation`; verified branch HEAD and PR #14 head both equal `4dd006834e0d265411119fa276ff2808d0ab701f` before this documentation-only update. PR #14 remains open, draft, and unmerged.
- Latest verified GitHub Actions run: `43770662317`, workflow `Phase 1 Safety Tests`, push event, completed with conclusion `success`. Its `mocked-safety-tests` job passed. This verifies mocked safety CI on the exact preceding code commit; it does not establish live provider or production acceptance.
- Latest complete local unittest discovery recorded for this checkpoint: **641 tests, 0 failures, 38 skipped**. The 38 skips are guarded PostgreSQL integration tests and are not passes. The 34-test disposable Neon publication integration passed separately, and the semantic event-lifecycle PostgreSQL test passed separately (1/1). The wider Layer1/claim-registry/event-lifecycle/legacy PostgreSQL batch was interrupted and is not a pass.
- Provider acceptance remains blocked/unverified: the inspected test environment contained only the guarded disposable PostgreSQL DSN and allowlisted host; no DeepSeek or Cloudflare credentials were present there. Do not claim authenticated DeepSeek generation, Cloudflare inference, external announcement ingestion, or actual Binance media upload.
- Media-upload hardening and sequence tests are mock-based: storage PUT success is limited to HTTP 200/201; the tested sequence is presigned URL → storage PUT → image-status poll. No live media upload or Binance Square post occurred.
- No production publisher activation, real Binance Square publication, production database operation, credential/schedule/workflow change, PR merge, deployment, or paid infrastructure provisioning occurred.
- Next: continue only from this branch/PR head; validate provider credentials through the user's existing secure environment (never request secrets in chat), then perform explicitly authorized provider acceptance without triggering the scheduled workflow or production publisher. Keep Module 21 and Modules 19–21 marked PARTIAL until required end-to-end acceptance gates pass.


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


## Latest authoritative checkpoint — live provider verification passed — 2026-11-16

### Verified GitHub state
- Repository: `shehrozali6465372-ctrl/Binance-bot`.
- Continuation branch: `layer-1/module9-onchain-continuation`.
- PR #14: https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/14
- PR #14 is still **OPEN / DRAFT / UNMERGED**; base branch remains `layer-1/module9-onchain-intelligence`.
- Branch HEAD at this checkpoint: `dbe0d13cf5f3a5cfe17971f6179dd1157aa029e1`.
- The latest Phase 1 Safety Tests run for that exact HEAD is run `43782814185`, completed **SUCCESS**. The immediately preceding documentation commit also passed in run `43782807214`.

### Live DeepSeek + Cloudflare provider acceptance
- Manual-only workflow: `.github/workflows/provider-verification.yml`.
- Workflow is available on `main`; current workflow definition commit: `d8628e109496b2d4d937ff417edd9361baa62b80`.
- Workflow explicitly checks out `layer-1/module9-onchain-continuation` for provider implementation code. This fixes the earlier `ModuleNotFoundError: No module named 'layer1'` caused by checking out `main` for code that existed only on the continuation branch.
- Latest live run: `43782717263`, completed **SUCCESS** on `main`: https://github.com/shehrozali6465372-ctrl/Binance-bot/actions/runs/43782717263
- DeepSeek authenticated generation: **PASS** — model `deepseek-flash`, latency 997 ms, 30 total tokens.
- Cloudflare Workers AI image generation: **PASS** — model `@cf/black-forest-labs/flux-2-klein-4b`, JPEG, 256x256, 6,132 ms.
- This is real authenticated provider acceptance, not mocked CI. It verifies one bounded request to each provider only; it does not establish long-duration reliability, rate-limit behavior, production throughput, or complete end-to-end agent acceptance.
- DeepSeek smoke-test false negative was fixed: workflow previously required the generated response to equal one exact sentinel string. It now accepts a non-null result from `DeepSeekClient.chat()`; the client validates the response structure, non-empty assistant content, model identity, and normal completion. A `None` result still fails. Regression test added to prevent reintroducing exact-string matching.
- Relevant commits: workflow branch fix `e149e0a6fa2a44827fb8095f01545d2523fa3f1d`; regression test `ce1637e972921c6085a566155b60414341e31292`; later documentation/status commits are recorded in GitHub history.
- Secret-handling boundary remains unchanged: keys are read from GitHub Secrets/Variables as process environment variables; never print, echo, serialize, or upload secret values, response bodies, or generated text.

### Safety boundary and remaining work
- No real Binance Square post was made. Production publisher was not activated.
- Existing scheduled `run_bot.yml`, production database, credentials, and schedules were not changed or triggered by this verification.
- No PR merge, deployment, or paid infrastructure provisioning occurred.
- PR #14 remains open/draft/unmerged. Continue from its current branch and HEAD; do not recreate modules or restart the project.
- Provider connectivity is now verified. Modules 19–21 and overall production readiness must not be marked complete solely from this smoke test; remaining module-specific and end-to-end acceptance gates still need separate evidence.
- Before further code changes, inspect current GitHub PR/branch state and existing implementation. Preserve the user's constraints: no Codex, no personal browser for this project, no production publishing, no credential exposure, and no merge/deploy without explicit approval.


## 2026-11-16 — Scheduled workflow restoration and CI follow-up

- Restored `.github/workflows/run_bot.yml` to exact base-branch content in commit `3da5c20f9d7af32e6d914bbada07d210bf6aeff4`; only that file changed in the restoration commit. The five-minute schedule and `DRY_RUN: "1"` remain as before.
- Phase 1 run `43785915439` exposed one stale test assertion: the importer dependency test required DeepSeek/Cloudflare env entries and rejected Gemini entries. Removed those unrelated assertions in `6c04de2e021dd64618df521921720cfef5b3118b`; the importer, dry-run and announcement DB checks remain. Follow-up CI run `43786286550` must be checked for its final result.
- Important unresolved release blocker: PR `main.py` uses DeepSeek, but restored scheduled workflow provides Gemini variables. The workflow was not changed beyond the user's explicit approval. Do not merge/deploy until a separately approved production provider configuration is aligned and verified.
- No scheduled run, Binance post, production DB write, merge or deployment occurred.


## 2026-11-16 — Current PR-head PostgreSQL acceptance results

- Created a separate detached acceptance worktree at PR head `a4677d705b313e04b54e479cd2871ce1609d717f`; existing worktrees and their checked-out states were preserved.
- Against the guarded disposable `binance_onchain_test` database, with exact host/TLS checks: claim-registry PostgreSQL tests **1/1 passed**; Layer1 PostgreSQL tests **2/2 passed**; event-lifecycle PostgreSQL tests **5/5 passed**; legacy post-history/analytics PostgreSQL tests **3/3 passed**. The destructive Module 9 `test_onchain_postgres` suite was not run.
- GitHub Actions run `43786286550` passed on the current application/test code: `compileall` passed; **649 tests, 0 failures, 38 guarded PostgreSQL skips**. These skips are not passes; selected PG integrations were verified separately.
- Existing publication PostgreSQL integration evidence remains **34/34 passed** with mocked Binance transport only.
- The scheduled workflow compatibility blocker remains: PR `main.py` is DeepSeek-based, but the restored `run_bot.yml` still injects Gemini variables. No further workflow modification, dispatch, publishing, merge or deployment was performed.


## 2026-11-16 — Approved scheduled-workflow provider alignment
- User approved the limited provider mapping change in `.github/workflows/run_bot.yml`; commit `0a97bfa848c3700400120b32eb4cfb04f437ebe8`.
- Scheduled job now maps `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL=deepseek-flash`, `CLOUDFLARE_API_TOKEN`, and `CLOUDFLARE_ACCOUNT_ID`. Existing Square, GitHub token and announcement DB mappings remain.
- Verified five-minute cron and `DRY_RUN: "1"` unchanged; provider env diff was limited to Gemini-to-DeepSeek replacement plus Cloudflare mappings.
- GitHub Actions run `43786947834` for the exact workflow commit completed SUCCESS (compileall and mocked publication safety test job). This does not prove scheduled runtime.
- Existing live provider smoke run `43782717263` separately passed one authenticated DeepSeek completion and one Cloudflare image generation; no Binance media upload or Square publication was performed.
- PR #14 remains open/draft/unmerged. No workflow dispatch, Binance POST, production DB operation, publisher activation, merge or deployment occurred.
- Next: continue module acceptance from the current PR head without restarting or duplicating implementation. Keep dry-run and publishing controls intact. Do not claim end-to-end production readiness until Modules 11–21 remaining acceptance gates and safe runtime validation have evidence.

## Module 11 temporal compound-claim guard — 2026-11-16
- On the latest fetched continuation head `85351ba9c1af429bcdd5bb807d66d342794a03dd`, source audit found a concrete evidence-laundering gap: `split_atomic_claims()` did not split a shared-subject temporal construction such as “ABC price rose 8% before falling 4%”. `_verify_one()` therefore treated it as one proposition and allowed a single `market.price_change` evidence record to return `VERIFIED`.
- TDD RED: added a regression for both “before falling” and “after rising”; both cases returned `VERIFIED` before the fix. GREEN: added a bounded temporal-action pattern (`before|after` followed by a gerund) to the existing compound-claim gate. Such claims now remain `UNVERIFIED` with `COMPOUND_CLAIM_REQUIRES_ATOMIC_EVIDENCE` unless they are an exact canonical primary announcement source assertion.
- Added a negative control: a single fact with a date modifier (“before 2026-11-20”) remains `VERIFIED`; the guard does not flag a date-only temporal modifier.
- Focused evidence-verification suite: **56 passed, 0 failed**. Full local unittest discovery on `/tmp/binance-continue-85351`: **650 tests, 0 failures, 38 skipped**. The 38 are environment-guarded PostgreSQL tests and are not counted as passes. `compileall` and `git diff --check` passed.
- Scope is deliberately bounded lexical protection, not general NLP or semantic entailment. Other temporal/elliptical constructions may still need policy-backed coverage. No provider calls, Binance media upload, real Square post, production database operation, workflow/schedule change, merge or deployment occurred.
- Work was performed in a new detached worktree `/tmp/binance-continue-85351` at the fetched remote head. Existing worktrees were not checked out, reset, cleaned or overwritten. With explicit user approval, the four-file change was committed as `d3ae64fd29bd60616cc5d18d5f7859cc9c814b95` and pushed fast-forward to `layer-1/module9-onchain-continuation` (PR #14 head branch). GitHub commit retrieval confirmed the commit and exact diff. No merge, deployment, workflow dispatch, provider call, media upload, production DB operation or Binance post occurred.

## Module 11 shared-subject sequential-action guard — 2026-11-16 (local verification checkpoint)
- Re-audited the bounded compound-claim splitter after the prior temporal `before/after + gerund` fix. A new evidence-laundering gap remained: sentences such as “ABC price rose 8% then fell 4%” and “ABC price rose 8% later fell 4%” were not segmented by the shared-subject parser and could inherit one `market.price_change` evidence record as `VERIFIED`.
- TDD RED: added three regressions covering bare `then`, bare `later`, and comma + `subsequently`; the first two reproduced `VERIFIED` incorrectly, while the comma + `subsequently` case was already guarded.
- GREEN: extended `_SHARED_SUBJECT_CONJUNCTION` to recognize standalone `then`, `later`, and `subsequently` before a recognized finite predicate, reconstructing the explicit subject on the second clause. No NLP dependency or semantic inference was added.
- Focused `tests.test_evidence_verification`: **57 passed, 0 failed**. Full suite using the existing isolated `/tmp/binance-module11-test-venv` (Pillow available): **651 tests, 0 failures, 38 skipped**. The 38 are environment-guarded PostgreSQL tests and are not counted as passes. `compileall` and `git diff --check` passed.
- System Python full-suite attempt was not a valid full-suite result: 19 test-module/import errors were caused by missing Pillow (`PIL`) in that interpreter. No dependency was installed; the isolated existing test venv was used for the valid full-suite run.
- Current local worktree: `/tmp/binance-continue-85351`, detached at `502ff79d6ba10205ebf80a525c46184c9aa36695`; only `layer1/evidence_verification.py` and `tests/test_evidence_verification.py` are modified at this checkpoint. No other worktree was changed. Docs are being updated locally; no commit or push has been made for this follow-up.
- This is bounded deterministic grammar coverage only. General semantic causal inference, arbitrary ellipsis, and sentence-level semantic entailment remain unresolved; Module 11 remains PARTIAL. No live provider request, Binance media upload/POST, production DB write, workflow dispatch, schedule/credential change, merge or deployment occurred.

## Module 11 continuation — 2026-11-16 compound-claim hardening (PARTIAL)

- Starting baseline: branch `layer-1/module9-onchain-continuation`, HEAD `8e594dc9a4e56cb49531558fef600ddeb6f008a6` (PR #14). Existing changes were preserved; implementation was performed in the isolated `/tmp/binance-continue-85351` worktree.
- Reproduced three additional one-field evidence bypasses before the fix: comma participial action (`ABC price rose 8%, falling 4%`), subordinate independent clause (`ABC price rose 8% as trading volume increased 2%`), and comma-led relative clause (`ABC price rose 8%, which was 4% higher than yesterday`). Each incorrectly returned `VERIFIED` from one `market.price` evidence record.
- Added regression coverage and bounded deterministic guards. `as` is treated as a clause boundary only when the right side starts with a recognized independent subject/finite verb. Comma participial predicates use an explicit allowlist. Comma-led `which + recognized finite predicate` is treated as a second proposition. All require atomic evidence and remain `UNVERIFIED` when only one field is linked.
- TDD: regression failed before implementation and passed after. Evidence-verification suite **58/58**; combined evidence/content/DeepSeek-generator suite **87/87**; full repository suite **652 tests, 0 failures, 38 skipped** (PostgreSQL integration tests skipped because `TEST_POSTGRES_DSN` is not configured). `compileall` and `git diff --check` passed.
- This is not general NLP/semantic entailment. Causal inference and unrecognized/ambiguous elliptical constructions remain fail-closed rather than semantically resolved. Module 11 remains **PARTIAL**, not complete. Exact generated-post claim attribution is not semantic proof. No live provider request, production DB write, real Binance post, workflow dispatch, merge or deployment occurred.

## Module 11 market-claim display binding guard — 2026-11-16 (local verification; PARTIAL)

- Starting point: exact PR #14 head 22391cbed66f6458bf33f8accd68837cdbee6b07, inspected in clean detached worktree /tmp/binance-continue-85351. Other pre-existing worktrees, including the dirty Module 9 worktree, were not modified.
- Source audit reproduced a further verification bypass: a Claim whose structured fields and linked evidence asserted market.price = 100 USD could carry displayed text such as “ABC price is 999 USD” or “ABC volume is 100 USD” and still return VERIFIED. An explicit wrong-currency display (“ABC price is 100 EUR”) was also added as a regression.
- TDD RED: the first two mismatched text cases returned VERIFIED before the implementation. GREEN: _claim_text_mismatch() now applies a bounded deterministic binding check for supported market claim keys (market.price, market.price_change, market.change_24h, market.volume_24h, market.market_cap). It requires the rendered metric label, checks every displayed numeric literal against the structured value at the field's display precision, checks explicit unit/currency suffixes and symbols, and excludes ISO date literals. Mismatches add CLAIM_TEXT_STRUCTURED_VALUE_MISMATCH:* and force UNVERIFIED.
- Verification: focused evidence-verification suite 59 passed; combined evidence/content/research-package/DeepSeek-generator suite 101 passed; full repository discovery (unittest discover -s tests) 653 tests, 0 failures, 38 skipped. The 38 skips are PostgreSQL integration tests requiring TEST_POSTGRES_DSN; they are not passes. compileall and git diff --check passed.
- Scope is deliberately limited to displayed market metric/value/unit consistency. This is not general semantic entailment: negation, modal language, directional predicates, non-market prose/value alignment, and arbitrary paraphrase are still not comprehensively checked. Module 11 remains PARTIAL / NOT COMPLETE.
- The full test suite uses mocked provider/media transports and dry-run/publisher safety tests; it is not live Binance publishing or live media-upload acceptance. No live provider request, Binance media upload, real Square post, production DB write, credential/schedule/workflow change, workflow dispatch, merge, deployment or paid infrastructure provisioning occurred.
- Current worktree /tmp/binance-continue-85351 contains local modifications to layer1/evidence_verification.py, tests/test_evidence_verification.py, and these context/gap docs. No commit or push has been made for this checkpoint. Preserve this worktree and its changes; do not reset or clean it.
## Module 11 announcement-text binding addendum — 2026-11-16 (supersedes prior local verification counts; PARTIAL)

- A second text-to-evidence bypass was reproduced: an arbitrary sentence could be attached to an accepted announcement.body structured value and verified as SOURCE_ASSERTION, even though the sentence was not the source's actual title/body. TDD RED showed “ABC listing confirmed for December 1” returned VERIFIED when the linked source body was “Binance will list ABC on 2026-12-01 at 08:00 UTC.”
- GREEN: announcement.title/body claims now remain UNVERIFIED unless the claim is a SOURCE_ASSERTION with exact linked source identity/value and its text is either the canonical internal Source assertion representation or the exact Detail: <source value> representation used by the package parser. The existing exact-detail and direct-primary source tests remain passing. Non-exact paraphrases do not inherit announcement-body evidence.
- Updated verification after both text-binding guards: focused evidence-verification **60 passed**; combined evidence/content/research-package/DeepSeek-generator **102 passed**; full repository **654 tests, 0 failures, 38 skipped**. The 38 skips require TEST_POSTGRES_DSN and are not passes. compileall and git diff --check were run after code changes.
- Current local diff now includes bounded market display metric/value/unit binding plus exact announcement title/body source-text binding. This still does not implement general semantic entailment for arbitrary non-market prose, negation, modality, directional claims or all paraphrase forms. Module 11 remains PARTIAL / NOT COMPLETE.
- No live provider request, real Binance media upload or post, production DB operation, workflow dispatch, credential/schedule change, merge or deployment occurred. Changes remain local in /tmp/binance-continue-85351; no commit/push has been made. Existing worktrees remain untouched.
## Module 11 structured source-assertion text binding — 2026-11-16 (latest local checkpoint; PARTIAL)

- Continued source audit found four more false-verification cases where evidence fields matched but rendered SOURCE_ASSERTION text did not: Binance Spot YES evidence paired with “Binance Spot: NO”; a 2-hour publication ledger value paired with “Last posted: 12 hours ago”; event_type=listing paired with “Type: delisting”; and freshness=FRESH paired with “Age: stale”. All four regressions returned VERIFIED before the fix.
- Extended the deterministic text-binding guard. Canonical internal Source assertion strings remain supported. Package-facing templates are now checked against their structured values for announcement event type/freshness, Binance Spot eligibility, publication last-posted status, trend topic digest/value, and on-chain transfer-summary ID. Unknown source-assertion formats fail closed. Announcement title/body remain limited to canonical source assertion or exact Detail: source payload with exact linked evidence.
- Existing package test uses “Binance announced a listing” for event_type=listing; this exact supported template is retained alongside “Type: listing”. Unlinked CONFIRMED_FACT drafts remain unresolved without adding spurious text-binding errors.
- Latest verification: evidence-verification **61 passed**; combined evidence/content/research-package/DeepSeek-generator **103 passed**; full repository **655 tests, 0 failures, 38 skipped**. All 38 skips require TEST_POSTGRES_DSN and are not passes. compileall and git diff --check passed after the final source changes.
- Scope remains deterministic binding for supported claim formats, not general semantic entailment. Arbitrary prose, negation, modality, directional predicates, asset-symbol mismatch in free prose, and unrecognized paraphrases are not comprehensively resolved. Module 11 remains **PARTIAL / NOT COMPLETE**.
- Current changes remain local in detached worktree /tmp/binance-continue-85351 at base HEAD 22391cbed66f6458bf33f8accd68837cdbee6b07. Four files are modified: layer1/evidence_verification.py, tests/test_evidence_verification.py, PROJECT_CONTEXT.md, MODULES_11_21_GAP_REGISTER.md. No commit or push, merge, deployment, workflow dispatch, production DB write, live provider request, media upload or Binance Square post occurred. Other existing worktrees were left untouched.

## 2026-11-16 — Complete Layer 1–21 deep code review (PR #14)

### Review method and evidence boundary
- Reviewed the PR #14 branch code in the local worktree at the exact GitHub head 9c02c85124a32e81dbdbf4d96aa76d37c20b0bc9, including main.py, image_engine.py, layer1 modules, tests, migrations, scripts, active GitHub workflows and the 21-module locked architecture.
- Read the canonical project context and MODULES_11_21_GAP_REGISTER.md and compared their claims against the current branch, current file inventory, runtime call sites, current CI and local worktree state.
- Ran read-only AST/static duplicate scans, tracked-file SHA-256 comparison, call-site searches, test/reference inspection, git status and git diff --check. No exact byte-identical tracked files or duplicate top-level class/function definitions were found by those scans. This does not mean there is no duplicated business logic or obsolete path.
- Reproduced the Module 12 lifecycle failure with a local SQLite fixture. The Module 21 status mismatch is directly visible in the caller and authorization contract. Other integration findings were established by tracing runtime call sites and adapter type checks.
- No code was modified during this review. Findings below are classified as confirmed defects, integration gaps, design/acceptance gaps or cleanup candidates; do not treat every observation as a proven runtime crash.

### Executive assessment
The repository contains substantial implementation for all 21 module areas, but the current PR is not an accepted end-to-end production system. The most important blockers are: publication authorization status mismatch; illegal event lifecycle transition; non-durable scheduled-run state/daily quota; failed Git push recovery and credential-bearing remote URL; Module 9 workers not wired into the runtime and incompatible with the PostgreSQL store classes; and opportunity/editorial/content stages that are not currently connected as their intended policy flow. Keep DRY_RUN=1 and publishing disabled.

### Module-by-module findings

#### Module 1 — Foundation, configuration and orchestration
- Core configuration, persistence and orchestration code exists; no claim is made that the entire module is missing.
- Operational blocker: the active scheduled workflow runs on a fresh GitHub-hosted runner, restores only published_posts.jsonl, and uploads agent.db only as an artifact. It does not restore agent.db on the next run. See .github/workflows/run_bot.yml:38–42 and 70–89.
- The main runtime defaults to the local SQLite database unless a separate PostgreSQL publication backend is explicitly configured. The active workflow maps ANNOUNCEMENT_DATABASE_URL for the read-only announcement ledger, not a durable agent-state DATABASE_URL/PERSISTENCE_BACKEND. See workflow lines 44–68 and main.py database/configuration initialization.
- Consequence: event, market, candidate, lifecycle, draft, authorization/quota and other SQLite state can be lost between scheduled runs. The daily count helper reads post_analytics from the current DB (main.py:1115–1131); it does not count the JSONL history. If live publishing were enabled on this ephemeral workflow, MAX_DAILY_POSTS=6 could reset with a fresh DB on subsequent runs. This is a release blocker, currently contained by DRY_RUN=1.
- The workflow cache uses the same fixed key for restore and save (run_bot.yml:38–42, 70–75). GitHub Actions cache entries are immutable for an existing key; this is not a reliable rolling-state store.
- No destructive action was taken.

#### Module 2 — Market data intelligence
- MarketDataIntelligenceEngine is instantiated in main.py:5419–5422 with fetch_json=lambda *_: None.
- The runtime normalizes the existing CoinGecko payload at main.py:5470–5477. The engine's fetch_binance_24h method exists at layer1/foundation.py:1005 onward, but no runtime call site invokes it; the only matches outside the method definition are tests.
- Therefore the intended independent Binance 24-hour ticker observation/cross-provider comparison is not active in the normal pipeline. The Binance exchangeInfo eligibility snapshot is a separate product/status check and must not be misrepresented as Binance price/volume market data.
- Module 8 market analysis can operate on persisted observations, but those observations currently derive from the CoinGecko path. Cross-provider validation is not established.

#### Module 3 — Binance Spot eligibility
- This is one of the stronger integrated areas: current runtime fetches and validates official exchangeInfo/Spot eligibility and revalidates before media work and again after media work, before authorization (main.py:4971–4980 and 5036–5045).
- Preserve the fail-closed eligibility and canonical asset identity checks. Do not weaken them while fixing adjacent modules.
- Remaining live-provider reliability and current-head acceptance must be tested separately; mocked tests are not live exchangeInfo acceptance.

#### Module 4 — Announcement intelligence/import
- The Python importer is a read-only consumer of the official announcement ledger; main.py:5328–5338 conditionally invokes it only when ANNOUNCEMENT_DATABASE_URL is present.
- The active PR #14 branch does not contain the announcement-worker/ directory, while .github/workflows/announcement-worker-tests.yml:7–13 and 30–32 refer to that directory and run npm test from it. This workflow's manual dispatch/test job cannot work against this branch as checked because its working directory is absent.
- Older context sections describe the announcement-worker as present on a separate feature branch. Treat that as historical/separate workstream, not evidence that it exists in the current PR #14 tree.
- The importer and the source producer are separate components. A successful importer unit test does not prove that the upstream live CMS worker is running or that the database is being populated.

#### Module 5 — Trending/narrative intelligence
- layer1/foundation.py:1423–1433 defines independent_source_count by grouping distinct content_hash fingerprints (or a conservative unknown-topic fingerprint).
- This measures distinct content fingerprints, not independently verified publisher/provider identities. Different content from the same provider can be counted as multiple independent sources. Do not describe this metric as proof of independent-source corroboration.
- Source lineage/provider identity should be represented and validated explicitly before using this count for evidence strength.

#### Module 6 — Candidate discovery and filtering
- Candidate identity includes event cluster IDs, trend cluster IDs, or market_refs as the final fallback (layer1/foundation.py:1568–1580 and 1658–1677).
- For market-only candidates, market_refs derive from market data hashes/endpoints (line 1574) and are used as the identity basis (lines 1658–1671). A new market snapshot can therefore create a new candidate ID even if the underlying asset/opportunity has not materially changed. This can weaken deduplication and candidate continuity.
- Announcement/candidate identity and event-lifecycle identity use different derivation paths. The current runtime also performs source/event-type lookups when selecting lifecycle state. A single canonical event identity/correlation contract is needed across candidate, graph, research, editorial and lifecycle records.
- Keep asset identity and eligibility validation intact; do not fix candidate continuity by merging unrelated assets/events.

#### Module 7 — Relevance scoring
- The new RelevanceScoringEngine is invoked (main.py:5604–5613), but all five inputs — event_materiality, source_credibility, freshness, audience_relevance and novelty — are passed as None. The engine therefore persists an explicit deferred score rather than inventing evidence. This is correct fail-closed behavior.
- The actual legacy candidate-ranking path later assigns a heuristic score from absolute 24-hour price change and volume ratio when Skills Hub scoring is unavailable (main.py:4584–4598). That heuristic, not the new evidence-based relevance score, controls ranking.
- Result: Module 7's evidence-based scorer is not the operative ranking policy. Do not activate guessed weights; either provide owner-approved evidence-backed components or keep the system in review/defer mode and make the legacy heuristic's non-authoritative status explicit.

#### Module 8 — Market analysis
- Market analysis is built from stored CoinGecko observations and available historical/peer/benchmark data (main.py:5470–5477 and 5535–5557).
- Because Module 2 does not call the Binance ticker fetch method and scheduled SQLite history is not restored, independent-provider comparison and durable longitudinal analysis are not established in the current scheduled runtime.
- Keep unavailable history/benchmark fields explicitly unavailable; never synthesize market history or infer a return series from a single snapshot.

#### Module 9 — On-chain intelligence
- Runtime accepts onchain_aggregation_by_asset as an optional argument with a default of None, then converts None to an empty mapping (main.py:4226–4227, 5232–5247). The public run_once/main entrypoints do not instantiate or run the provider workers and do not supply this mapping. A repository search found no non-test worker constructor call sites.
- Consequently the normal scheduled pipeline reports onchain_aggregation_status=NOT_PROVIDED and cannot attach on-chain aggregation summaries to candidates/graph.
- All four provider worker constructors require isinstance(mapping_store, OnChainStore) and isinstance(ingestion_store, OnChainIngestionStore): layer1/onchain_evm_worker.py:42, onchain_bitcoin_worker.py:35, onchain_solana_worker.py:31, onchain_xrpl_worker.py:35.
- PostgresOnChainStore and PostgresOnChainIngestionStore are separate classes and are not subclasses of those SQLite classes. Verified with issubclass checks: both False. Thus the existing PostgreSQL stores cannot be passed directly to the current workers; constructors reject them.
- Worker/provider/store implementations and migrations are not equivalent to an operational ingestion service. A real runtime runner, store abstraction/adapter and safe ownership/scheduling/monitoring are still required. Earlier context mentions onchain_evm_store.py and onchain_worker_lifecycle.py in a separate worktree; those files are absent from the current PR #14 branch and must not be assumed present here.
- No live chain provider calls or production ingestion were made.

#### Module 10 — Event intelligence graph
- The graph is rebuilt from persisted records in main.py:5614–5629 and receives on-chain summary references from onchain_graph_refs.
- Since Module 9 is not wired and the runtime input defaults to an empty mapping, on-chain graph entities/relationships are not produced by the normal scheduled path. The graph can still represent other stored events/claims; do not call the entire graph module absent.
- Candidate IDs, event lifecycle IDs and graph entity IDs need an explicit shared correlation contract to prevent split or orphaned event records.

#### Module 11 — Evidence verification
- The PR head contains deterministic evidence registry, source provenance, structured metric/value/unit binding and bounded compound-claim controls. It is not general natural-language semantic entailment.
- GitHub-head evidence-verification focused suite recorded in the preceding history: 61 passing tests for the structured source-assertion checkpoint. The current local follow-up worktree adds negation/direction/unit cases and records 65 focused tests; those additional changes are local-only and not in GitHub HEAD.
- Remaining limitations: arbitrary paraphrases, free-prose asset-symbol mismatch, general negation/modal/conditional scope, unrecognized compound grammar, arbitrary non-market prose and complete sentence-to-evidence semantic entailment.
- Unknown or unsupported claims must remain UNVERIFIED/UNRESOLVED. Do not promote a regex/lexical guard into a claim of complete semantic verification.

#### Module 12 — Event lifecycle
- Confirmed reproducible defect in both SQLite and PostgreSQL transition implementations.
- Transition map: STALE and RESOLVED can reopen only through UNDER_VERIFICATION (layer1/event_lifecycle.py:20–29).
- In observe(), the non-material-revision branch can leave a STALE/RESOLVED event in its old state, but a later VERIFIED branch includes UNDER_VERIFICATION, STALE and RESOLVED and can select CONFIRMED directly (event_lifecycle.py:224–260). That transition is illegal under the declared transition graph and raises ValueError.
- The PostgreSQL implementation mirrors the same transition logic (layer1/event_lifecycle_postgres.py:130–167).
- A local SQLite fixture reproduced the failure for a stale event receiving a non-material revision. The same logic exists in PostgreSQL; live PostgreSQL reproduction remains unrun because TEST_POSTGRES_DSN was not configured in the current CI/local environment.
- Existing lifecycle tests cover material changes, old-source replay and stale handling, but do not cover the non-material revision after STALE/RESOLVED case (tests/test_event_lifecycle.py:110–128, 177–220, 392 onward).
- Fix the state decision so a non-material revision does not reopen a stale/resolved event; add exact SQLite and isolated PostgreSQL regression tests. Preserve material-revision reopening semantics.

#### Module 13 — Deep research package
- Research package assembly checks required source kinds, unresolved claims and lifecycle states (layer1/research_package.py:194–243).
- The source coverage report is source-kind coverage, not proof that each source independently supports each claim or that multiple source records are independent publishers. Preserve the distinction between evidence availability and evidence support.
- Module 13 is connected into the runtime before opportunity evaluation (main.py:4425–4442), but downstream policy inputs still defer the pipeline.

#### Module 14 — Opportunity evaluation
- The runtime hardcodes unsupported_causal_framing=False and materially_new=False, computes duplicate_angle from the cooldown, and passes factors=None and policy=None (main.py:4443–4458).
- This intentionally fails closed, but means the runtime has no calibrated evidence-backed opportunity policy and cannot legitimately produce PROCEED from this path.
- Editorial strategy is only invoked inside the PROCEED branch (main.py:4470–4485). Therefore the current configuration blocks the intended editorial/content path rather than completing it.
- Do not invent weights or enable PROCEED until an owner-approved policy and source-backed factor calculation are defined.

#### Module 15 — DeepSeek integration
- The dedicated client supports the configured model identifiers (layer1/deepseek_client.py:20–21), but the legacy DeepSeekGenerator in main.py remains responsible for decision and writing prompts (main.py:3326–3376).
- Phase 1 ranking uses a free-text prompt/parser rather than a constrained structured-output contract (main.py:3341–3374 and 3594–3609). Rank completeness, uniqueness, symbol membership and candidate membership need strict deterministic validation.
- If the model returns a symbol not found in the research packages, main.py logs the mismatch and falls back to research_packages[0] (main.py:4791–4809). This silently converts an invalid model decision into a different candidate selection. Reject the decision instead of substituting another asset.
- Provider smoke evidence from main at d8628e1 does not verify the current PR head's scheduled runtime.

#### Module 16 — Editorial strategy
- EditorialStrategyEngine is invoked only if OpportunityEvaluationEngine returns PROCEED (main.py:4470–4485).
- Because current runtime passes policy=None and factors=None, the normal path remains deferred and the editorial engine is not reached. Unit tests of the editorial engine do not establish runtime integration.
- The locked architecture's editorial requirements need an explicit accepted opportunity policy and end-to-end test fixture before this module is marked complete.

#### Module 17 — Content generation and draft persistence
- Actual DeepSeek content generation is still performed by DeepSeekGenerator.generate() in main.py:3376–3403 and its prompt builder at 3613 onward. The layer1 content-generation module primarily provides draft/validation persistence rather than owning the complete model-generation lifecycle.
- Model output metadata such as provider request ID, token usage and latency should be persisted as structured run metadata if required for reproducibility/cost monitoring; current review did not establish a complete durable audit for these fields.
- Keep exact draft hash, approved claim IDs, research package and editorial brief provenance bindings. Do not weaken them to improve generation yield.

#### Module 18 — Content verification
- The verifier requires exactly one claim marker per factual sentence and exact normalized sentence text equality with the referenced claim (layer1/content_verification.py:105–125).
- The writing prompt explicitly says every factual sentence must copy claim text verbatim, and says qualified non-factual analysis should be omitted unless a future explicit policy approves it (main.py:3645–3652).
- This is conservative but does not fulfil the architecture's intended labelled interpretation/implications/alternative-explanation content. A policy-backed non-factual analysis lane is needed; do not allow unlabelled analysis to masquerade as verified facts.
- The verifier correctly rejects unresolved claims, mismatched cashtags and trade-instruction patterns. Preserve those controls.

#### Module 19 — Cloudflare image generation (IMPORTANT REVIEW CORRECTION)
- The earlier preliminary review message incorrectly claimed that the active Cloudflare request used JSON. That claim was based on legacy JSON code elsewhere in image_engine.py and was wrong for the current Workers AI generator.
- The actual CloudflareWorkersAIImageGenerator.generate() builds multipart/form-data at image_engine.py:130–178; tests/test_cloudflare_image_generation.py:217–242 and 255 onward explicitly exercise multipart behavior.
- Do not record or act on the earlier JSON-versus-multipart allegation as a defect. Current request serialization is already multipart in the PR head.
- The remaining acceptance gap is provider verification on the exact current PR head. The earlier authenticated provider smoke run was on main commit d8628e1, not 9c02c85. Mocked request tests are not a live current-head provider test.
- Legacy GitHub image upload JSON code around image_engine.py:1076–1091 is a different path and must not be confused with the Cloudflare Workers AI request.

#### Module 20 — Visual quality
- Deterministic validation checks PNG decoding, dimensions, byte size, final-image hash against the sidecar, draft/image pairing, asset identity, approved model, prompt/generation metadata, overlay labels, geometry, contrast, overlap, chart references and numeric overlays (layer1/visual_quality.py:44–112 and 127–220).
- It does not run OCR or an independent vision classifier over the generated background to detect unrequested text, logos, watermarks or visual hallucinations. Metadata/overlay validation cannot prove the background is text/logo-free.
- Add an independent visual/OCR acceptance stage if the locked design requires that property. Do not claim current visual QA proves absence of background text or logos.

#### Module 21 — Publication authorization and publisher
- Confirmed contract mismatch: main.py:5098–5108 passes content_verification.status as evidence_status. ContentVerificationResult success is PASS (layer1/content_verification.py:146–151), but PublicationAuthorization.validate_for_submission requires evidence_status == VERIFIED (layer1/publication_authorization.py:107–115). The normal successful result therefore fails the evidence authorization gate if this path is reached. The PostgreSQL authorization adapter enforces the same contract.
- main.py passes duplicate_policy_passed=True at line 5110 rather than having the authorization boundary independently validate the duplicate/cooldown evidence. The pre-generation cooldown checks remain separate controls; do not treat this hardcoded boolean as a fresh authorization proof.
- upload_authorized_image verifies the persisted authorization and submitted image hash list (image_engine.py:1405–1438), but it does not reread the image file and recompute its SHA-256 immediately before upload. A file replacement between visual validation/authorization and upload is a time-of-check/time-of-use risk. Rehash the exact bytes immediately before network upload and bind those bytes to the authorization.
- No independent PUBLISHER_ENABLED kill switch was found. The workflow's DRY_RUN=1 currently blocks external publishing, but a single DRY_RUN configuration change can expose the live path once the other gates are corrected. Require an independent, default-off publisher enablement control plus explicit environment/credential policy before any activation.
- The runtime correctly revalidates exact Binance Spot eligibility before and after image work (main.py:4971–4980 and 5036–5045); preserve this.
- The current scheduled workflow is not production-safe for live publishing until durable DB state, quota, authorization and end-to-end acceptance are complete.

### Cross-cutting bugs and operational blockers

#### A. Git history push/retry can report success without a remote push
- main.py:678–695 commits the history file; if the first push fails, the retry loop tries another commit.
- If that second commit reports "nothing to commit", the code returns True immediately at main.py:683–689 without attempting git push.
- _retry_pending_push() checks only uncommitted files via git status at main.py:774–791. A committed-but-unpushed local HEAD is therefore not detected.
- The recovery mechanism can silently leave published_posts.jsonl history absent from GitHub.
- _try_git_push() sets origin to a token-bearing HTTPS URL at main.py:697–702 and does not restore the original remote URL. This leaves the token in the local .git/config for the remainder of the workspace lifetime. Use a temporary auth header/credential helper and never persist the token in remote config.
- Add tests for push failure after commit, retry with clean worktree but ahead-of-remote HEAD, token-safe auth and restoration/absence of credential material.

#### B. GitHub Actions state persistence and quota
- Active workflow .github/workflows/run_bot.yml:38–42 restores only published_posts.jsonl; lines 70–89 save the same fixed-key cache and upload agent.db as an artifact.
- agent.db is not restored on the next scheduled run. GitHub-hosted scheduled runners are fresh environments.
- main.py:1115–1131 counts today's posts from post_analytics in the DB and returns zero on DB errors. It does not derive the count from the restored JSONL file.
- Therefore SQLite state and daily quota can reset between runs if the live workflow is enabled. DRY_RUN=1 currently contains this risk; it is a hard release blocker.
- Do not use immutable GitHub Actions cache entries as a database. Use a deliberately approved durable persistence service or keep live publishing disabled.

#### C. Duplicate/obsolete implementation paths and cleanup candidates
- SHA-256 scan found no exact byte-identical tracked files. AST scan found no duplicate top-level class/function definitions. This does not rule out semantic duplication.
- The new evidence-based relevance scorer and the legacy heuristic ranking both exist; the latter remains the operative ranking path when Skills Hub scoring is unavailable.
- The active publisher has a single main runtime path, but legacy publisher/image fallback code and old helpers remain. Review each by call graph before deletion.
- github/workflows/run_bot.yml is outside GitHub's recognized .github/workflows directory. It is a stale/legacy workflow file, not an active GitHub Actions workflow. It also contains older configuration/duplicate YAML jobs keys and should be removed only after verifying no external tooling references it.
- .github/workflows/announcement-worker-tests.yml refers to announcement-worker/, which is absent from this PR branch. Either restore that feature on its intended branch or retire/retarget this stale workflow; do not pretend it tests this PR.
- Skills Hub BAPI is explicitly disabled in main.py:4302–4305; skills_used is hardcoded False and skills_candidates is empty. Do not report Skills Hub discovery as operational.
- TradeSetup/EmotionEngine and other legacy helpers should be classified by actual call-site reachability before deletion. No bulk deletion was performed.
- The review found no exact duplicate files and did not delete any code.

### Security, reliability and testing gaps still open
- Git push token is written into the local origin URL (main.py:697–702).
- Live publisher has no independent default-off kill switch.
- Scheduled SQLite state and quota are ephemeral.
- PostgreSQL integration tests are skipped in GitHub CI (38 skips); no claim of current-head PostgreSQL concurrency acceptance.
- No current-head live Binance media upload, no real Square post and no scheduled live workflow dispatch.
- Current-head authenticated DeepSeek/Cloudflare provider smoke tests remain unverified; the older main-branch provider smoke is historical only.
- OCR/vision background validation is missing.
- General semantic entailment and non-factual analysis policy are incomplete.
- No real provider response, production DB state, or production outcome may be inferred from mocked tests.

### Context and repository cross-check discrepancies
- Before this update, the file's top "CURRENT CONTINUATION OVERRIDE — 2026-11-12" still directed continuation to Module 9 distributed worker leases and a different branch/worktree. It is now relabelled historical; this 2026-11-16 override is authoritative.
- Older sections describe layer1/onchain_evm_store.py and layer1/onchain_worker_lifecycle.py as existing in a different worktree. They are absent from the current PR #14 branch.
- Older sections describe announcement-worker/ as present on a feature branch. It is absent from the current PR #14 branch; the workflow still points to it.
- Older test counts (329, 510, 522, 649, 650–655 and 38 skips) are historical snapshots. The exact current PR-head CI result is 655 run / 0 failures / 38 skipped in run 43854798245. The 660/38 result belongs to the local unpushed five-file follow-up.
- The latest gap register still has older module status/checkpoint/test-count statements. Reconcile it separately after this context update; do not use it to override the current PR #14 branch facts.
- Existing local worktree contains five uncommitted modifications, including a local PROJECT_CONTEXT.md change. This GitHub update is performed through the GitHub file API and must not be used to overwrite/reset/sync that local worktree. The local branch is behind the GitHub branch by documentation-only commits made after the reviewed application-code SHA. Inspect the exact remote commit count before reconciling; use a non-destructive fetch/rebase/merge only after checking all local diffs and preserving the five modified files.

### Required fix/acceptance sequence (do not mark complete prematurely)
1. Add TDD regression for Module 21 PASS-to-VERIFIED contract mapping; verify both SQLite and PostgreSQL authorization adapters.
2. Add TDD regression for Module 12 non-material revision after STALE and RESOLVED; verify SQLite and dedicated PostgreSQL integration.
3. Fix Git push recovery to detect ahead-of-remote commits and retry push without relying on uncommitted files; remove token-bearing remote URL persistence.
4. Design/approve durable state for scheduled runtime and enforce daily quota across independent runs; keep DRY_RUN=1.
5. Define store protocols/adapters for Module 9 workers and PostgreSQL, add a runner with safe worker ownership/monitoring, then test on an isolated PostgreSQL DB.
6. Integrate Binance market ticker fetch or explicitly revise the Module 2 acceptance contract; do not infer Binance market data from exchangeInfo.
7. Replace trend hash uniqueness with provider/source identity evidence; stabilize candidate/event identity across revisions and market snapshots.
8. Keep Module 7 deferred until all scoring factors have evidence; prevent legacy heuristic from being represented as the evidence-based score.
9. Define and approve opportunity factors/policy before PROCEED; only then test editorial strategy and content generation end-to-end.
10. Introduce a structured DeepSeek ranking schema and reject unknown/duplicate/out-of-set symbols instead of fallback selection.
11. Define a separate policy-backed labelled analysis lane for Module 18 while preserving exact factual claim attribution and trade-instruction rejection.
12. Verify current PR-head DeepSeek and Cloudflare providers with authenticated smoke tests; verify media upload in a safe isolated path without Square publication.
13. Add OCR/independent vision acceptance for Module 20 if required by the locked architecture.
14. Rehash the exact image bytes immediately before upload and independently validate duplicate policy at authorization.
15. Add tests for GitHub Actions persistence, workflow paths, stale workflow references, push failures, authorization boundaries and end-to-end failure recovery.
16. Update MODULES_11_21_GAP_REGISTER.md after each accepted fix and maintain a single current status table.
17. Keep all publishing disabled, no real Square posts, no production DB writes, no merge/deploy, and no paid resources unless separately approved.

### Final review conclusion
- Overall status: PARTIAL / NOT PRODUCTION-READY.
- Modules 1–21 have code artifacts, but several module contracts are deferred, disconnected or not accepted end-to-end.
- Confirmed defects: Module 12 illegal transition; Module 21 PASS/VERIFIED mismatch; Git push retry false-success; token-bearing origin URL persistence; scheduled workflow state/daily quota loss if publishing is enabled.
- Confirmed integration gaps: Module 2 Binance ticker not called; Module 9 workers not run and PostgreSQL store type incompatibility; Module 14 policy/factors missing and editorial path blocked; Module 15 invalid-symbol fallback; Module 16 unreachable under current deferred policy.
- Important limitations: Module 5 source independence is content-hash based; Module 6 market snapshot candidate identity is unstable; Module 18 exact-copy-only factual sentences do not fulfil the intended analysis lane; Module 20 lacks independent background OCR/vision.
- Review correction: Cloudflare Workers AI request is already multipart; the earlier preliminary JSON allegation was incorrect and must not be repeated.
- No application code was modified or cleaned up by this review.

## Neon branch/database audit — 2026-11-17 (read-only; no production cutover)

- Rechecked the linked Neon project `Binance-bot-staging` (`orange-glade-36037611`). No dedicated production Neon project/branch was identified in the linked account inventory.
- Branches inspected: `staging`, `module9-pg-integration-test` (`br-falling-bread-azl8rggt`), and `module9-pg-lease-fencing-disposable` (`br-falling-butterfly-az03rryi`). The latter two remain test/disposable branches; do not repurpose either as production.
- Important correction to the initial table inventory: each branch contains two databases, `binance_bot_staging` and `binance_onchain_test`. Table inventory is database-specific:
  - Integration branch / `binance_bot_staging`: announcement ingestion tables plus six Layer-1 on-chain ingestion tables; no publication ledger tables.
  - Integration branch / `binance_onchain_test`: six Layer-1 on-chain ingestion tables plus `layer1_schema_migrations`; no publication attempt, quota reservation, publication authorization, or durable run lease tables.
  - Disposable branch / `binance_bot_staging`: announcement ingestion, Layer-1 ingestion, content/research/analytics, and publication tables including `publication_attempts`, `publication_authorizations`, `publication_quota_reservations`, `publication_reconciliation_events`, and `runs`.
  - Disposable branch / `binance_onchain_test`: broad Layer-1/content/research schema plus publication tables and `layer1_run_lease`, `layer1_runs`, and `layer1_schema_migrations`.
- Read-only schema inspection confirmed quota reservation has a UTC day key, status check constraint, unique reservation id and unique attempt id; publication attempts enforce unique idempotency key and unique remote post id, plus constrained status/content hash; publication authorization references draft, editorial brief, research package and quota reservation; `layer1_run_lease` enforces one agent lease and references `layer1_runs`.
- This demonstrates the disposable branch contains the richer test schema, not that it is production-ready. The integration branch's two DBs do not carry the full publication persistence schema. The staging branch inventory also does not demonstrate a complete, validated production publication ledger.
- No row contents, credentials, DSNs, secrets, or user payloads were read. No Neon writes, branch promotions, compute setting changes, or resource provisioning occurred.
- GitHub Actions runs `43907241840` (commit `13d38c195ad6e837d6f5465beab6433cf56b54ce`) and `43907254115` (commit `f760cad9072359f06b873618b6de2fed7f0ac13f`) both completed with conclusion `success`.
- PR #14 remains open/draft/unmerged as of this audit; no merge, deployment, workflow dispatch, production write, credential change, schedule change, or real Binance Square publication occurred.
- Decision: keep the production publisher disabled and `DRY_RUN=1`. Before any approved live cutover, provision/identify a dedicated production database, apply and verify the exact migrations against it, verify role grants/least privilege, TLS/host allowlist, backup/restore and retention, quota/run-lease concurrency, and only then configure production GitHub secret/variable in a separately approved change. Never use the disposable test branch as production.

## 2026-11-17 — PostgreSQL runtime migration fix, CI dispatch and continuation handoff

### Authoritative GitHub state
- Repository: `shehrozali6465372-ctrl/Binance-bot`.
- PR #14: https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/14 — OPEN, Draft, not merged.
- Branch: `layer-1/module9-onchain-continuation`.
- Application fix commit: `0f2686421fdeb853fb83b2ea0254218a8c53f36f` (`Fix runtime PostgreSQL migration privilege handling`).
- The PR head was verified at this exact SHA after push. The working tree was clean before this documentation-only update.

### PostgreSQL startup blocker — fix pushed and exercised in GitHub Actions
- Previous failed run #1808 / ID `44122320123` on SHA `a73188a93e375aff7a5151657453c13f5a0a7b2d` failed during runtime startup with `psycopg.errors.InsufficientPrivilege: permission denied for schema public`.
- Root cause: application startup called publication migration DDL and attempted schema/table creation using the least-privilege application role.
- Fix in commit `0f2686421fdeb853fb83b2ea0254218a8c53f36f`:
  - `layer1/onchain_postgres.py`: added `verify_postgres_migrations()`; checks the migration ledger and SHA-256 checksums using SELECT-only access; missing migrations/checksum drift fail closed.
  - `layer1/publication_postgres.py`: added `verify_publication_postgres_migrations()` wrapper for the publication migration directory.
  - `main.py`: runtime PostgreSQL store creation now verifies migrations and does not execute DDL migrations.
  - `tests/test_publication_postgres.py`: regression coverage for SELECT-only verification, missing migration, checksum drift and runtime not invoking the migration applier.
- Explicit migration applier functions remain available for a separately authorized migrator/owner path. Do not grant broad schema CREATE to the application role as a workaround.
- Local verification before push: 45 focused test cases; 26 executed and passed, 19 skipped because `TEST_POSTGRES_DSN` was not configured. Python compilation and `git diff --check` passed.

### GitHub Actions run after the fix
- Manually dispatched `Binance Square Auto Poster` (`.github/workflows/run_bot.yml`) on the PR branch and exact commit `0f2686421fdeb853fb83b2ea0254218a8c53f36f`.
- Run #44141611015: https://github.com/shehrozali6465372-ctrl/Binance-bot/actions/runs/44141611015.
- Final run conclusion: `success`; job `run-agent` and all steps, including `Run Binance Square Agent` and artifact upload, succeeded.
- Sanitized log confirms `PERSISTENCE_BACKEND=postgresql`, `POSTGRES_DSN` was present (value masked), and `DRY_RUN=1`. The old schema `CREATE` privilege failure did not recur. This is runtime evidence that the SELECT-only migration verification path passed startup against the configured database; it is not a full PostgreSQL integration/concurrency test.
- Safety settings in the workflow were `DRY_RUN=1`, `POST_INTERVAL=0`, `MAX_ITERATIONS=1`. No real Binance Square post was submitted.
- The run reported `Binance Spot eligibility unavailable; failing closed: HTTPError`, then `Market scanner returned no candidates; no announcement-only synthetic candidates are created`. Therefore the workflow's green conclusion means the bounded dry-run process completed safely, not that a market candidate was successfully produced or that publishing works end-to-end.
- A separate read-only HTTP GET to `https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT` from the connected remote machine returned HTTP 200. This does not establish GitHub runner reachability or explain the runner's HTTPError; exact runner status is currently not logged. Do not bypass the eligibility gate or synthesize candidates.
- `CLOUDFLARE_ACCOUNT_ID` appeared empty in the workflow environment. Image generation was not reached in this run, so impact remains unverified. Do not expose or inspect secret values.
- Cache save emitted a non-blocking warning because another job may have reserved the same cache key. Artifact `agent-output-44141611015` uploaded successfully. Node.js 20 deprecation warnings were also emitted.

### Full safety CI evidence
- PR check `mocked-safety-tests` passed (workflow run `44141286899`, job `134244458768`).
- Job log reports `Ran 666 tests in 6.794s` and `OK (skipped=38)`: 628 tests executed successfully; 38 skipped, including PostgreSQL integration cases requiring `TEST_POSTGRES_DSN`.
- Do not describe this as 666 passed. No dedicated current-head live PostgreSQL integration/concurrency suite was run.
- PR #14 remained OPEN/Draft/unmerged at the last check. The PR check list showed `mocked-safety-tests` passing.

### Current blocker and next work — resume here, do not repeat completed work
1. Diagnose the Binance Spot `HTTPError` from the GitHub runner. Add safe status-code-only diagnostics (HTTP status, allowlisted retry/rate-limit metadata, exception class; never response body, URL credentials, API keys or DSNs). Reproduce on a non-publishing test path and add regression tests. Do not weaken the official `exchangeInfo` validation, bypass the fail-closed gate, or create synthetic candidates.
2. Verify why `CLOUDFLARE_ACCOUNT_ID` is empty by checking only whether the intended repository secret/variable name is configured; never print its value. Determine whether the current code expects a secret or variable and reconcile only with explicit user approval before changing GitHub settings.
3. Arrange a genuinely dedicated isolated PostgreSQL integration target named `binance_onchain_test` or other exact test DB name required by the relevant suite. Current tests in `tests/test_onchain_postgres.py` explicitly require `binance_onchain_test` on localhost or an exact `TEST_POSTGRES_ALLOWED_HOST` with TLS; other PostgreSQL integration suites also use `TEST_POSTGRES_DSN`. Never point destructive integration tests at production. Do not provision paid infrastructure or alter production DB without explicit approval.
4. Run the PostgreSQL integration suites against the isolated test DB, capture exact pass/skip/fail counts, and verify migrations, transaction behavior, concurrency and runtime SELECT-only role access. No live integration result exists yet.
5. Continue the older full-review blockers in the required sequence above; in particular Module 12 stale/resolved non-material transition, Module 21 `PASS` versus `VERIFIED` authorization contract, Git history push retry/token persistence, durable scheduled state/quota, Module 9 worker/PostgreSQL adapter integration, Module 14 opportunity policy and downstream Module 16 reachability. The deep review findings and required sequence immediately above this checkpoint remain open unless separately proven fixed.
6. Recheck PR #14 checks after any new push. Do not merge, deploy, activate publisher, change credentials/schedules, migrate production schema, modify production permissions, run live publication, or provision paid resources without separate explicit approval.

### Non-negotiable safety and worktree constraints
- Continue in `/tmp/binance-blocker1-fix` on `layer-1/module9-onchain-continuation`; verify branch, HEAD and `git status` before every change.
- Preserve every other existing worktree and all uncommitted changes elsewhere. Do not reset, clean, delete, overwrite or bulk-sync worktrees.
- No Codex. Do not use the Pinterest personal browser for this Binance project.
- Keep `DRY_RUN=1`; never publish a real Binance Square post during testing.
- Never print, copy into context, or expose secrets, DSNs, passwords, authorization headers or raw provider response bodies.
- No merge, deployment, production database writes/migrations/permission changes, credential/schedule/workflow configuration changes, or paid provisioning without separate explicit approval.
- The application fix is already pushed. This checkpoint is documentation; do not recreate or reapply the PostgreSQL verifier fix.


## 2026-11-17 — Binance Spot HTTP diagnostics and Cloudflare workflow configuration

### Approved continuation work

User explicitly approved:
1. Commit and push the safe Binance Spot HTTP diagnostic changes to PR #14.
2. Correct the Cloudflare account ID workflow mapping to use the existing repository variable.

### Binance Spot diagnostic implementation

Files changed:
- `main.py`
- `tests/test_layer1_foundation.py`

Changes:
- Added safe HTTP diagnostic extraction for the Binance Spot eligibility failure path.
- Log fields are restricted to exception class, HTTP status (or `unknown`) and explicitly allowlisted headers.
- Allowlisted headers: `Retry-After`, `X-MBX-USED-WEIGHT-1M`, `X-RateLimit-Limit-Minute`, `X-RateLimit-Remaining-Minute`, `X-RateLimit-Reset`.
- Header values are sanitized and length-limited.
- URL, query parameters, response body, reason phrase, credentials, authorization headers and non-allowlisted headers are not logged.
- The market HTTP adapter preserves only allowlisted rate-limit headers for handled 418/429/5xx responses.
- Official Binance Spot `exchangeInfo?permissions=SPOT` validation and fail-closed behavior remain unchanged. No synthetic candidates or eligibility bypass were introduced.

Regression coverage:
- HTTPError 403 exposes status and allowlisted headers without leaking URL credentials, reason text, authorization values or arbitrary headers.
- ProviderResponse 429 exposes status and allowlisted headers without leaking authorization data.
- HTTP adapter 429 preserves rate-limit headers and excludes Authorization.

Local test evidence:
- `python -m unittest tests.test_layer1_foundation`: 104 tests passed.
- Full `python -m unittest discover -s tests`: 668 tests run, 630 passed, 38 skipped, 0 failures.
- Python compileall: PASS.
- `git diff --check`: PASS.
- The 38 skipped tests remain skipped; do not describe all 668 as executed/passed.

### Cloudflare configuration finding and approved correction

Read-only GitHub Actions configuration inspection established:
- Repository variable `CLOUDFLARE_ACCOUNT_ID` exists and is non-empty (value intentionally not read or displayed).
- Repository secret `CLOUDFLARE_ACCOUNT_ID` is absent.
- Workflow previously referenced `secrets.CLOUDFLARE_ACCOUNT_ID`, resulting in an empty value.
- Approved workflow correction: `CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}`.

No secret or variable values were exposed or modified.

### Exact state at this checkpoint

- Worktree: `/tmp/binance-blocker1-fix`
- Branch: `layer-1/module9-onchain-continuation`
- Base HEAD before this approved diagnostic/config commit: `c63ae933ed087ca886f55ca7764af2f80c8258e9`
- PR #14 remains OPEN / DRAFT / UNMERGED.
- `DRY_RUN: "1"` remains unchanged.
- No live post, production database write, credential change, schedule change, merge or deployment performed.
- No other worktrees were modified.

### Required next verification

After pushing the approved changes:
1. Confirm remote branch SHA and PR #14 head SHA match the new commit.
2. Manually dispatch `Binance Square Auto Poster` on `layer-1/module9-onchain-continuation` (workflow has `workflow_dispatch`) and verify `DRY_RUN=1`.
3. Inspect the new run logs for the exact Binance Spot HTTP status and only the allowlisted headers. Never copy secrets or response bodies.
4. Confirm Spot eligibility still fails closed when provider access is denied/unavailable and no synthetic candidates are created.
5. Verify Cloudflare account ID reaches the workflow as a non-empty environment value without printing it; verify whether image generation is reached and whether it succeeds. Do not expose the account ID.
6. Update this context again with the exact run ID, status, diagnostics and any remaining blocker.
7. Continue isolated PostgreSQL integration acceptance only after identifying and validating the dedicated non-production test database.

Do not repeat the already-completed PostgreSQL runtime migration fix. Do not mark the Binance runner blocker closed until the new GitHub Actions run supplies reproducible evidence.


## 2026-11-17 — GitHub Actions verification after safe diagnostics commit

### Commit and PR verification

- Approved changes committed and pushed: `cac870c589ce326764d287ad678e02c500a54d3a`.
- Commit message: `Add safe Binance Spot HTTP diagnostics`.
- Files committed: `main.py`, `tests/test_layer1_foundation.py`, `.github/workflows/run_bot.yml`, `PROJECT_CONTEXT.md`.
- Remote branch SHA and local HEAD both equal `cac870c589ce326764d287ad678e02c500a54d3a`.
- PR #14 head SHA equals the same commit; PR remains OPEN / DRAFT / UNMERGED.
- Local working tree is clean.
- Focused suite rerun after workflow/context changes: 104 tests passed.
- Full suite result from this work session: 668 tests run, 630 passed, 38 skipped, 0 failures.
- Python compilation and `git diff --check` passed.

### Manual dry-run workflow execution

Workflow: `Binance Square Auto Poster`
Run ID: `44146147107`
Run URL: `https://github.com/shehrozali6465372-ctrl/Binance-bot/actions/runs/44146147107`
Commit tested: `cac870c589ce326764d287ad678e02c500a54d3a`
Trigger: `workflow_dispatch` on `layer-1/module9-onchain-continuation`
Final result: SUCCESS
Agent job: SUCCESS
Run Binance Square Agent step: SUCCESS
Artifact upload: SUCCESS
Cache save: warning/non-blocking (cache save failed); Node.js 20 deprecation and ubuntu-latest migration warnings are non-blocking.

### Actual Binance Spot response

The new log emitted:
- Exception: `HTTPError`
- HTTP status: `451`
- Allowlisted headers: empty
- Agent then logged: `Market scanner returned no candidates; no announcement-only synthetic candidates are created`.
- Workflow environment confirmed `DRY_RUN=1`.
- No Binance Square publication occurred.

Interpretation:
- The runner's exact response is now established as HTTP 451, not a generic or inferred HTTP error.
- IETF RFC 7725 defines 451 as `Unavailable For Legal Reasons`, meaning the responding server or an intermediary is denying access due to a legal demand. This does not by itself identify which entity applied the restriction or establish the precise jurisdiction/reason.
- No response body or non-allowlisted headers were read into logs. The exact blocking entity and policy reason therefore remain unknown.
- Do not call this a confirmed Binance geo-block until a permitted, safe source identifies the blocking entity or reason.
- Do not bypass the restriction with proxies/VPNs or weaken the eligibility check.

### Cloudflare variable correction verification

- Workflow now maps `CLOUDFLARE_ACCOUNT_ID` from `vars.CLOUDFLARE_ACCOUNT_ID`.
- The run environment confirmed the variable was non-empty. Its value must never be copied into chat, logs, or project context.
- The Binance scanner returned zero candidates before the image-generation path. Cloudflare image generation was therefore not reached; its operational success remains unverified.

### Next exact continuation

1. Preserve the verified HTTP 451 result and fail-closed behavior.
2. Investigate only supported/official Binance API routing options and determine whether an official alternate base endpoint changes the status from the same GitHub runner. If testing alternate official endpoints, make only bounded public GET requests and log status codes only; do not log bodies, URLs with query data, or headers beyond the approved allowlist. Do not use VPNs, proxies, or evasion.
3. Check whether RFC 7725's `Link; rel=blocked-by` signal is present only if it can be captured safely without expanding logs to arbitrary headers; otherwise keep the blocker entity unknown.
4. Keep `DRY_RUN=1`; no live publishing.
5. Cloudflare account ID is now mapped correctly but image generation remains untested because no candidates were produced.
6. Recheck PR #14 checks for commit `cac870c589ce326764d287ad678e02c500a54d3a`.
7. Continue isolated PostgreSQL integration acceptance only after verifying a dedicated non-production test DB. The latest workflow run does not prove PostgreSQL integration, concurrency or production publication readiness.
8. Do not merge, deploy, change credentials/schedules, alter production DB, or activate publisher without separate explicit approval.


### PR safety check after the documentation checkpoint

- Latest branch commit: `1362947d5a1cda645fb2f7b58936f22252369b6a`.
- PR #14 head SHA matches this commit.
- `mocked-safety-tests` completed successfully on this latest HEAD.
- PR remains OPEN / DRAFT / UNMERGED.
- The manual dry-run workflow run `44146147107` tested the preceding application/config commit `cac870c589ce326764d287ad678e02c500a54d3a`; the subsequent commit only appended this context verification record.


---

## 2026-11-18 — Single-project, multi-location inventory and reconciliation

### Scope and authority

- This remains **one Binance Square Write-to-Earn Agent project**, not separate projects. Development, testing and deployment have been distributed across stacked GitHub branches/PRs, several local worktrees, the ChatGPT Library, Neon test branches and a Render CMS worker.
- Canonical repository: \`shehrozali6465372-ctrl/Binance-bot\`.
- Default branch \`main\` was at \`5c94cca52d80a9786295772c905ae1f3cdc71159\` during this audit. \`PROJECT_CONTEXT.md\` is absent from \`main\` (GitHub contents API returned 404); the active project context is on the open PR #14 head branch, not the default branch.
- PR #14 was OPEN / DRAFT / UNMERGED at pre-audit head \`28353d311f44b448357a92aab976d7477445d536\` (93 commits, 65 changed files). This audit supersedes the older tail note below that still calls \`1362947d5a1cda645fb2f7b58936f22252369b6a\` the latest branch commit.
- The locked architecture is a design contract, version 1.0 dated 2026-11-09. It defines 21 logical modules in one modular system; it does not describe 21 microservices and does not claim that all modules are implemented or production-ready.
- Current PR #14 files include \`PROJECT_CONTEXT.md\`, \`Binance_Square_W2E_20x_LOCKED_Architecture.md\`, and \`MODULES_11_21_GAP_REGISTER.md\`. The current GitHub architecture blob SHA is \`8991f44b154dbb76bc86950d5a91b84541b54448\` (68,588 characters in the fetched file). The gap register's top status says cross-cutting blocker #1 has implementation and isolated PostgreSQL acceptance verified, while live operational cutover remains pending; its documented acceptance batch is 44 passed.

### GitHub pull-request and branch map

The repository had 14 PRs and 17 branches. PRs #4 and #5 are merged; the other 12 PRs are open. Current PR states and branch relationships:

- #1 — Phase 1 publishing safety foundation: OPEN / DRAFT.
- #2 — Isolated Binance CMS announcement listener: OPEN / DRAFT; base \`layer-1/completion-hardening\`, head \`feature/binance-cms-announcement-worker\`, SHA \`55ff3e6a409a6f2b7b944c43772140b788556223\`.
- #3 — Isolated Binance CMS worker and scheduled ingestion: OPEN / DRAFT; base \`main\`, head \`integration/binance-cms-worker-main\`, SHA \`47e85384f2eeba2ac5bb4f2fb2cfa26ec4dc6558\`.
- #4 — Manual CMS smoke dispatch: MERGED.
- #5 — Neon worker TLS mode: MERGED.
- #6 — CMS WebSocket startup error race: OPEN / DRAFT; base \`integration/binance-cms-worker-main\`, head \`fix/cms-websocket-startup-error-race\`, SHA \`1608f9f8130cc2aa7ec1142788e42c8df84e1c6c\`.
- #7 — Module 1 orchestration hardening: OPEN.
- #8 — Module 2 market-data hardening: OPEN.
- #9 — Module 3 Binance Spot eligibility: OPEN.
- #10 — Module 4 announcement intelligence: OPEN.
- #11 — Modules 5–6 candidate/trend intelligence: OPEN.
- #12 — Module 8 market analysis: OPEN; head SHA \`f7e6fc511e146b6bfb6f25afb0009c369d8afd4a\`.
- #13 — Module 9 on-chain foundation: OPEN / DRAFT; head SHA \`3afed37192b66c57aba2f17ba841a84a60227cda\`.
- #14 — Modules 11–21 continuation: OPEN / DRAFT; base is PR #13's branch.

PRs #7–#14 form a stacked Layer 1 development chain. Do not treat them as independent products or merge them out of order. PRs #2, #3 and #6 are the overlapping CMS worker workstream and must be reconciled separately.

### CMS worker duplication and deployed implementation

- PR #2 and PR #3 touch 17 identical paths. Of those, 11 files have identical Git blob SHAs; six have different content: the two workflow files, worker README, \`announcement-worker/src/worker.js\`, scheduled-workflow tests and worker-lifecycle tests. They are parallel versions of the same CMS worker capability, not two separate products.
- PR #6 is a follow-up to PR #3 and is 27 commits ahead of PR #3. Its startup-race fix attaches transport error/open/close listeners before awaiting the transport connection. It switches from the high-level \`Cms\` connection path to \`CmsWebsocketStreams\` / \`WebsocketStreamsBase\`, and removes the worker-managed ping/pong timers in favor of the SDK's signed-stream keepalive. This is a material transport/heartbeat change, not a trivial patch; do not merge PR #6 wholesale into PR #2 without reviewing the SDK contract and regression tests.
- PR #2 and PR #3 have diverged from a common base; PR #2 is the more integrated feature branch and includes the Python importer and scheduled-agent wiring. PR #2 is the CMS branch deployed to Render.
- Render service \`binance-cms-announcement-worker\` is a free-plan Node Web Service on \`feature/binance-cms-announcement-worker\`. Its latest successful deployment during this audit was commit \`55ff3e6a409a6f2b7b944c43772140b788556223\` (deployment \`dep-dbtp6nralhtc73fho520\`, 2026-11-16 23:36 UTC). This matches PR #2's current head. It is a CMS ingestion worker, not a Binance Square publisher.
- **Deployed-branch code risk:** PR #2's \`announcement-worker/src/worker.js\` awaits \`client.websocketStreams.connect()\` before registering \`connection.on("error")\` (connect at line 180; error listener at line 276 in the fetched PR #2 file). PR #6's tests and fix target the early WebSocket error-listener race. The deployed PR #2 code therefore still has the same vulnerable listener ordering. This is a code-level risk, not proof that the live service has crashed. Reconcile/port the narrow fix after review; preserve the existing service and do not change deployment without approval.

### Local worktree inventory — preserve all existing state

Eight local directories are checkouts of the canonical \`Binance-bot\` repository; one additional directory is a different repository whose relationship is unverified:

1. \`/tmp/binance-blocker1-fix\` — clean; branch \`layer-1/module9-onchain-continuation\`; HEAD \`28353d311f44b448357a92aab976d7477445d536\`. This was the clean pre-audit mirror of PR #14 at HEAD 28353d3; it has not been synchronized since the pre-audit checkout; treat it as a historical snapshot, not the current PR #14 mirror. Its worktree remains clean.
2. \`/tmp/binance-deepseek-verify\` — branch \`layer-1/module9-onchain-continuation\`; HEAD \`9c02c85124a32e81dbdbf4d96aa76d37c20b0bc9\`; 16 modified tracked files plus untracked \`tests/test_git_sync.py\`. Contains local, uncommitted follow-up changes for publication status mapping, publisher default-off gating, duplicate-policy recomputation, lifecycle transition validation, image-byte hash revalidation and token-safe Git push/retry. These changes are not in current PR #14 and must not be overwritten or assumed accepted.
3. \`/tmp/binance-continue-85351\` — detached HEAD \`22391cbed66f6458bf33f8accd68837cdbee6b07\`; four modified files. Its modified evidence-verification source/test files are byte-identical to current PR #14; its local context/gap-register changes remain divergent and must be preserved.
4. \`/tmp/binance-layer1-audit\` — branch \`layer-1/module9-onchain-intelligence\`; HEAD \`3afed37192b66c57aba2f17ba841a84a60227cda\`; 15 modified tracked files and 10 untracked paths, including a pre-existing \`.venv/\`. Local-only work adds worker lease/lifecycle/store-adapter code, a PostgreSQL migration, tests and a Module 9 integration workflow. These changes are not on GitHub PR #13.
5. \`/tmp/binance-pr14-acceptance\` — detached HEAD \`a4677d705b313e04b54e479cd2871ce1609d717f\`; clean historical snapshot, 27 commits behind current PR #14.
6. \`/tmp/binance-runtime-fix\` — detached HEAD \`4dd006834e0d265411119fa276ff2808d0ab701f\`; clean historical snapshot, 55 commits behind current PR #14.
7. \`/tmp/binance-bot-check\` — feature-branch checkout at \`d47466f3aa10c7695929a4be18b3dad3367ef900\`; it is 39 commits behind PR #2's current head \`55ff3e6a409a6f2b7b944c43772140b788556223\`. Its local remote-tracking ref is stale. It has untracked \`.venv/\` and \`announcement-worker/node_modules/\`; preserve both.
8. \`/tmp/Binance-bot-gh-review-loop\` — branch \`integration/binance-cms-worker-main\`; HEAD \`47e85384f2eeba2ac5bb4f2fb2cfa26ec4dc6558\`, matching PR #3; untracked \`announcement-worker/node_modules/\`; preserve.
9. \`/tmp/binance-square-agent\` — different origin, \`stephen20250410/binance-square-agent\`; local \`main\` is two commits ahead of its origin and has an untracked \`README.live-poster.md\`. Its relationship to canonical \`Binance-bot\` is not established. Do not import or merge it as canonical project code without provenance review.

The detached PR #14 snapshots are ancestors of the current PR #14 head, not independent project branches. The local dirty changes in \`binance-deepseek-verify\` and \`binance-layer1-audit\` are separate uncommitted work and must be preserved. No reset, clean, stash, checkout, force-push or worktree deletion was performed.

### Local verification performed during this audit

- In \`/tmp/binance-deepseek-verify\`, the focused regression batch completed **236 tests, 0 failures, 24 skipped**. The skipped cases require a PostgreSQL test DSN. \`compileall\` and \`git diff --check\` passed. The run explicitly unset PostgreSQL DSNs and provider/publisher credentials; it did not contact providers, databases or Binance publishing endpoints. This is local follow-up evidence only, not PR #14 acceptance.
- In \`/tmp/binance-layer1-audit\`, the focused Module 9 worker/lease/lifecycle batch completed **95 tests, 0 failures, 28 skipped** with PostgreSQL DSN and provider credentials unset. \`compileall\` and \`git diff --check\` passed. The skipped tests require PostgreSQL integration configuration. The local Module 9 document records an earlier 377-test PostgreSQL-enabled run on 2026-11-16; that historical run was not repeated in this audit.
- The Module 9 local changes include a process-local \`OnChainWorkerRunner\`, durable scoped lease/fencing code and shared storage adapters. The current runtime still accepts on-chain aggregation as injected input; it does not construct/start the worker fleet or runner. Provider credentials and approved monitored-account seeds remain absent. Do not describe Module 9 as production-ready or runtime-integrated.

### Documentation source reconciliation

- Before the 2026-11-18 inventory append, GitHub \`PROJECT_CONTEXT.md\` on PR #14 was 2,487 lines / 367,599 characters; the inventory, SDK addendum and subsequent corrections have since extended the file; do not use the pre-audit count as the current size. Its previous tail still named \`1362947d...\` as the latest commit; this 2026-11-18 inventory supersedes that statement.
- The Library \`Binance_Square_W2E_Agent_Master_Context.md\` version 28 is a historical 2026-11-09 snapshot, not the current continuation record.
- The Library contains eight byte-identical copies of the locked architecture document. They are identical to one another but **not equal to the current GitHub architecture file**: Library copies are 62,800 characters; the current GitHub version is 68,588 characters with blob SHA \`8991f44b154dbb76bc86950d5a91b84541b54448\`. Treat all eight Library copies as stale snapshots; do not use them to override the current GitHub architecture and do not delete them during this audit.
- The Library's 2026-11-16 production-blocker register is historical and is not the same file/scope as the current GitHub \`MODULES_11_21_GAP_REGISTER.md\`. The latter's current top entry records blocker #1 as isolated PostgreSQL acceptance verified, with live operational cutover still pending.
- GitHub \`ONCHAIN_INTELLIGENCE.md\` on PR #13 is the checked-in Module 9 document. The local Module 9 worktree's version is 558 lines and contains a further 87-line local-only addendum; that addendum is not on PR #13.

### Neon and production boundary

- The prior read-only Neon inventory found only the \`Binance-bot-staging\` project, with staging and disposable Module 9 test branches/databases. No dedicated production Neon project/branch was identified. Do not relabel or promote any staging/disposable branch as production.
- No Neon writes, promotions, credential reads, production schema changes, provider RPC calls, publisher activation or real Binance Square publication occurred during this audit.
- Keep \`DRY_RUN=1\`; keep the production publisher disabled. Do not merge, deploy, change schedules/credentials, provision paid infrastructure or modify production resources without separate explicit approval.

### Exact continuation order

1. Continue the single-project implementation registry from this inventory. Compare each source location against the current PR #14 / PR #13 code before deciding whether it is duplicate, superseded or unique.
2. Reconcile the PR #6 WebSocket startup-race fix with deployed PR #2. Review the SDK transport/keepalive contract and port only the necessary tested behavior; do not merge PR #6 wholesale.
3. Review the uncommitted \`binance-deepseek-verify\` follow-up patch against current PR #14, preserve all local changes, and only integrate after a complete diff/test review.
4. Review the uncommitted Module 9 worker lease/lifecycle implementation, complete its PostgreSQL acceptance, and design runtime wiring only after the storage/lease contracts are accepted. Do not duplicate the existing worker implementations.
5. Continue the known Layer 1 gaps from the 2026-11-16 review: Module 2 real Binance ticker acquisition; evidence-based Module 7 scoring; approved opportunity factors before Modules 14/16; structured DeepSeek ranking; policy-backed Module 18 analysis lane; independent OCR/vision checks for Module 20; and remaining Module 21 publication/recovery hardening.
6. Keep all tests dry-run/mocked unless a separately approved isolated test target is explicitly configured. Never publish a real Binance Square post as a test.


### CMS SDK keepalive implementation cross-check — 2026-11-18

- Inspected the installed, lockfile-pinned \`@binance/cms@1.0.3\` and \`@binance/common@2.5.3\` package source in the local PR #3 CMS checkout. This was package-source inspection only; no live Binance connection was made.
- The high-level \`Cms\` SDK path constructs a \`WebsocketStreamsBase\`, sets \`signedStreams = true\`, awaits \`websocketBase.connect()\`, and only then returns its \`WebsocketStreamsConnection\` wrapper. That confirms why an application cannot attach wrapper-level transport listeners before the handshake when it uses the high-level \`Cms.connect()\` call.
- The pinned SDK itself schedules an empty WebSocket PING every 30 seconds for signed streams in \`WebsocketStreamsBase.onOpen()\`; the timer is bound to the socket and cleared during cleanup, and the open handler schedules it again after reconnect.
- PR #2's worker also configures a 30-second application heartbeat and calls \`connection.pingServer()\` while waiting for PONG. Therefore the deployed PR #2 implementation runs a redundant application-level heartbeat alongside the SDK's own signed-stream keepalive. This is a code-level redundancy; no failure or provider-side rejection was observed in this audit.
- PR #6 removes the application-level ping/pong timer and relies on the SDK keepalive, while attaching transport listeners before the initial handshake. That design is consistent with the inspected pinned SDK source. Before porting it, add explicit SDK contract assertions for the low-level \`CmsWebsocketStreams.WebsocketStreamsConnection\` and \`WebsocketStreamsBase\` exports and keepalive/reconnect behavior; PR #6's current \`sdk-contract.test.js\` directly asserts the high-level \`Cms\` constructor and URL but does not explicitly assert those low-level exports.
- Recommended reconciliation: keep one keepalive owner (the pinned SDK), retain explicit transport health/degradation state, and register transport listeners before starting the handshake. Do not merge the PR #6 branch wholesale into deployed PR #2; port and test the minimal contract-compatible change on the deployed branch only after approval.


### Post-audit context verification

- The 2026-11-18 audit appended the cross-location inventory, CMS SDK keepalive/startup-race addendum and verification corrections to this \`PROJECT_CONTEXT.md\` on the PR #14 branch. The prior documentation-only commits for this audit were \`44d7cd96b0392daf582b82a390fb3259e92f6443\`, \`b8f76464d3fb97d799f8ab07d2087b5fb08c170a\`, and \`ce470b118d57288823e810bd21bf07695e36ff72\`.
- PR #14 remains OPEN / DRAFT / UNMERGED. Verify the live PR head through GitHub metadata before any future update.
- \`/tmp/binance-blocker1-fix\` remains clean at the pre-audit SHA \`28353d311f44b448357a92aab976d7477445d536\`; it was not pulled or modified and is a historical snapshot, not the current GitHub PR #14 head.
- These updates changed only \`PROJECT_CONTEXT.md\`. No application source, workflow, database, credential, schedule or deployment was changed.


## FOUR-PLATFORM CANONICAL MASTER MAP — 2026-11-18

**Superseding audit:** This entry records the 18 November 2026 read-only reconciliation across GitHub, Render, Neon and Remote Desktop Commander. The detailed operator map is stored in the user's Library as `/Binance_Bot_Canonical_Master_Map_2026-11-18.md` (51,441 bytes; SHA-256 `d2e9f1431eb670fabdcf2698e66d8a2257e7f979f60e676c7d63e6949897efc4`). Use that map as the current four-platform inventory and execution sequence. It does not replace the locked architecture or this context file's project history.

### GitHub — current state
- Repository: `shehrozali6465372-ctrl/Binance-bot`; default `main` HEAD observed `5c94cca52d80a9786295772c905ae1f3cdc71159`.
- PR #14 remains OPEN / DRAFT / UNMERGED; current branch `layer-1/module9-onchain-continuation`, HEAD `c88d4feb1a3d8b8c8d15a875557ce9cef2818976`; base PR #13 branch at `3afed37192b66c57aba2f17ba841a84a60227cda`.
- PR #14 code baseline immediately before the documentation-only audit commits is `28353d311f44b448357a92aab976d7477445d536`. The selected clean local worktree is at this code SHA; GitHub branch then advanced to `c88d4fe...` through docs-only commits.
- Latest PR #14 safety CI run `44195471227` for `c88d4fe...` completed SUCCESS. This is CI evidence, not production release acceptance.
- PR #7–#14 are stacked; no merge, retarget or rebase performed. PR #2/#3/#6 remain a separate CMS reconciliation track.
- PR #14 workflow declares `DRY_RUN: "1"`, `MAX_ITERATIONS: "1"`, and defaults persistence to SQLite unless `PERSISTENCE_BACKEND` is configured. Secret values were not read. Two 17 Nov `workflow_dispatch` runs on this branch (`44146147107`, `44141611015`) completed successfully with this workflow configuration; one earlier run (`44122320123`) failed in the agent step. No external Square publication confirmation was sought or claimed.

### Render — current state
- The only Binance Render service found is `binance-cms-announcement-worker`, service ID `srv-dbrr6ctg1s2s73dbi0cg`, in the third Render account/workspace.
- It is a free Singapore web service connected to `shehrozali6465372-ctrl/Binance-bot` branch `feature/binance-cms-announcement-worker` (PR #2), URL `https://binance-cms-announcement-worker.onrender.com`.
- Latest live deploy `dep-dbtp6nralhtc73fho520` uses commit `55ff3e6a409a6f2b7b944c43772140b788556223`, completed 16 Nov 2026 23:36:45 UTC. A prior attempt immediately before it failed; the subsequent build/deploy succeeded.
- 17 Nov app log samples contain recurring CMS heartbeat pong messages. The 17–18 Nov warn/error query returned no matching logs; the retrieved log page does not certify continuous health through the full 18 Nov day.
- No Binance publisher web service and no Render-managed PostgreSQL instance were found across the three inspected Render accounts. No Render deploy/restart/env change was made.

### Neon — production-project discovery supersedes older notes
- The current Binance Neon account exposes three Binance-named projects; therefore the prior statement “no production Neon project identified” is superseded:
  1. `Binance-bot-production`, project `orange-glade-36037611`. Its default `production` branch DB `binance_bot_production` contains only CMS event/worker tables and read-only counts show 16 announcement events, 1 worker-state row and 1 CMS migration. This is likely the read-only announcement ledger, but the actual `ANNOUNCEMENT_DATABASE_URL` secret binding is unverified.
  2. `Binance-bot-publisher-production`, project `withered-cherry-74978567`. Default `production` branch DB `binance_publisher_production` contains the Module 1–21/publisher schema; read-only counts show 5 Layer 1 migrations but zero posts, runs, metrics, publication attempts, authorizations, quota reservations, reconciliation events, candidates and on-chain transfer events. This is the likely publisher-ledger target, but the actual `POSTGRES_DSN` secret binding is unverified; do not claim production cutover.
  3. `Binance-bot-production-empty-archive`, project `misty-wildflower-60247190`. Its default `production` branch has zero user tables and an idle endpoint. It is only an empty/orphan/duplicate candidate; secret references cannot be checked, so do not delete, rename or repurpose it.
- The child branch `mcp-migration-2026-11-17T01-04-37` in the publisher project is missing `layer1_schema_migrations`, its primary key and grant relative to the current parent. Treat it as a stale schema snapshot; do not use as current migration baseline without controlled reconciliation.
- The existing Module 9 integration/disposable branches remain test-only. A disposable `binance_onchain_test` target had 1 attempt, 1 authorization and 1 quota reservation, while posts/runs/metrics/candidates/transfers were zero. These are test records, not real publication evidence.
- All Neon inspection was list/get/schema/SELECT only. No Neon write, migration, branch promotion, endpoint restart, credential access or deletion occurred.

### Remote Desktop Commander — one active worktree
- Device `bd830869-fbae-4825-ae7b-5044d6161090` was online. The only active worktree selected is `/tmp/binance-blocker1-fix`, branch `layer-1/module9-onchain-continuation`, clean HEAD `28353d311f44b448357a92aab976d7477445d536`; its matching origin tracking ref was observed at the same SHA.
- This worktree is the last verified PR #14 code baseline; the latest GitHub PR #14 head `c88d4fe...` adds documentation-only commits after that code checkpoint. Reconcile its context documentation without resetting/overwriting this local tree.
- All other known directories are frozen references, not active worktrees. In particular, `/tmp/binance-deepseek-verify` has 16 modified tracked files plus untracked `tests/test_git_sync.py`; `/tmp/binance-layer1-audit` has 15 modified tracked files plus unique untracked Module 9 lease/lifecycle code and tests; `/root/Binance-bot` has three modified CMS files. Preserve all changes and dependencies. Do not use `git clean`, hard reset, blind cherry-pick, mass sync or worktree deletion.
- Other historical snapshots and the different-origin `/tmp/binance-square-agent` remain frozen. Do not import code from the different-origin repository without provenance.

### Exact duplicate cleanup in Library
- Library contained one canonical `Binance_Square_W2E_20x_LOCKED_Architecture.md` and seven numbered copies `(1)` through `(7)`.
- All eight were byte-identical: 68,758 bytes each; SHA-256 `39d7474c48e92b0c476ab65290b9e0bd99369a41f6a52a8236485daf827b6d83`.
- The seven numbered copies were moved to Library trash successfully. The unnumbered canonical architecture was retained. Post-cleanup Library listing shows one architecture file and the new canonical Master Map.
- No GitHub source files, branches, local worktrees, Neon projects/branches/data, Render resources or deployments were deleted.
- PR #2/#3 CMS overlap, dirty worktrees and the empty Neon archive remain non-confirmed duplicates; preserve them pending dependency review.

### Current project position and continuation
- Project remains NOT COMPLETE / NOT PRODUCTION-ACCEPTED. The 21-module matrix, blockers and strict execution order are in the Library Master Map.
- Continue only in `/tmp/binance-blocker1-fix`. First review/compare the existing PR #14 follow-up patch donor and Module 9 worker/lifecycle donor; transfer only unique, tested improvements. Do not reimplement already completed work.
- Next correctness priorities remain Module 21 publication state/idempotency and durable scheduled persistence; Module 12 transition matrix; Git push recovery/token-safe auth; Module 9 worker lease/lifecycle/runtime integration; Module 2 Binance ticker acquisition; approved Module 7/14 factors; strict Module 15 ranking; Module 18 policy-backed content checks; Module 20 OCR/vision and exact-byte rehash.
- Preserve `DRY_RUN=1`; keep the publisher disabled. Never publish a real Binance Square post during tests. No production DSN binding, live publisher enablement, deployment, schedule/credential change or paid infrastructure is approved by this audit.
- This update records verified facts and explicitly identified unknowns. It does not authorize production resource changes or a live publishing cutover.

**Safety boundary:** no secrets or DSN values were read or written; no code or workflow changes were made in this audit; no local changes were cleaned; no production database was modified; no Render deploy/restart was triggered; no GitHub workflow was dispatched for this audit; no merge/deployment or real Binance Square post occurred.


## Module 12 stale/resolved non-material revision correction — 2026-11-18

**Status: IMPLEMENTED IN THE SINGLE ACTIVE LOCAL WORKTREE; SQLITE AND ISOLATED NEON POSTGRESQL REGRESSION ACCEPTANCE PASSED; CODE CHANGE NOT COMMITTED OR PUSHED.**

- Root cause reproduced: when a new but non-material revision with VERIFIED evidence arrived for an event already in STALE or RESOLVED, the implementation could select CONFIRMED directly. The allowed transition map requires reopening only through UNDER_VERIFICATION, so the transition raised `ValueError: illegal event lifecycle transition`.
- TDD evidence: two new SQLite regression tests were added first and both failed RED with that exact exception before the source change.
- Minimal correction: in both `layer1/event_lifecycle.py` and `layer1/event_lifecycle_postgres.py`, the VERIFIED-to-CONFIRMED branch now accepts only `current_state == "UNDER_VERIFICATION"`. The existing materially-new verified revision path remains unchanged and reopens STALE/RESOLVED via UNDER_VERIFICATION.
- Added two guarded Neon PostgreSQL regression tests to `tests/test_event_lifecycle_postgres.py` covering non-material revisions after STALE and RESOLVED.
- SQLite lifecycle suite: **25 passed, 0 failed**.
- PostgreSQL lifecycle module: **7 passed, 0 failed, 0 skipped**, run against isolated Neon project `Binance-bot-production`, endpoint `module9-disposable-test`, branch `br-falling-butterfly-az03rryi`, database `binance_onchain_test`. Preflight confirmed exact host against `TEST_POSTGRES_ALLOWED_HOST` and TLS; the DSN and credential values were not emitted. No production/default branch was used.
- Full local suite on the active worktree: **672 tests, 0 failed, 40 skipped** with PostgreSQL DSN unset. Skipped tests are guarded PostgreSQL integration cases; the 7-test Module 12 PostgreSQL suite was run separately and passed. The full suite used the previously installed isolated test venv `/tmp/binance-module11-test-venv`; no repo dependency file or install changed.
- `compileall` and `git diff --check`: PASS.
- Post-test read-only check of the disposable database: one lifecycle row, one revision row, one transition row and six schema migrations remained. No pre-test count snapshot exists, so the remaining row's ownership/age is unknown; it was preserved, not deleted.
- Active canonical worktree remains `/tmp/binance-blocker1-fix`, branch `layer-1/module9-onchain-continuation`, baseline HEAD and origin-tracking ref `28353d311f44b448357a92aab976d7477445d536`. Exactly four modified, uncommitted files: `layer1/event_lifecycle.py`, `layer1/event_lifecycle_postgres.py`, `tests/test_event_lifecycle.py`, `tests/test_event_lifecycle_postgres.py`.
- No code commit/push, merge, PR retarget, Render change, production database write, credential change, scheduled workflow change or real Square post was performed for this correction.
- The Library master map `/Binance_Bot_Canonical_Master_Map_2026-11-18.md` was updated with this checkpoint and the revised next step: inspect/fix the next Module 21 authorization/duplicate/final revalidation blocker, then durable scheduled recovery and safe Git push/auth integrity. Do not repeat Module 12 work.

Safety remains: keep `DRY_RUN=1`; publisher disabled; no real Square publication; no production DB changes; preserve all other worktrees and their uncommitted data.


## 17. Module 21 publication-safety continuation — 18 November 2026

**Status: LOCAL SQLITE / MOCKED ACCEPTANCE PASSED; DIRECT POSTGRESQL ACCEPTANCE BLOCKED BY MISSING TEST DSN; MODULE 21 IS NOT COMPLETE. Local code changes remain uncommitted.**

### Canonical state and branch reconciliation

- Active local worktree: `/tmp/binance-blocker1-fix`; branch `layer-1/module9-onchain-continuation`; HEAD `28353d311f44b448357a92aab976d7477445d536`. Local `origin/layer-1/module9-onchain-continuation` still resolves to that baseline.
- Live PR #14 is OPEN / DRAFT / UNMERGED. Before this documentation-only update its head was `9f4d8911e3e1bee21fb8b5d690a7810da06d58f2`; base is `layer-1/module9-onchain-intelligence`.
- GitHub compare from local HEAD to that PR head showed 6 commits ahead, 0 behind, merge base equal to local HEAD; all 6 commits touched only `PROJECT_CONTEXT.md`. No remote code-file delta exists relative to this local baseline. The live PR head differs from the older `c88d4feb...` checkpoint in prior notes. Do not use the stale local tracking ref as the live GitHub head.

### Preserved local worktree delta

- Exactly 16 tracked files modified, no untracked files; no reset, cleanup, code commit, code push, merge, or deployment.
- Files: `image_engine.py`; `layer1/content_verification.py`; `layer1/event_lifecycle.py`; `layer1/event_lifecycle_postgres.py`; `layer1/publication_authorization.py`; `layer1/publication_postgres.py`; `layer1/publication_runtime.py`; `main.py`; `tests/test_cloudflare_image_generation.py`; `tests/test_content_verification.py`; `tests/test_end_to_end_pipeline.py`; `tests/test_event_lifecycle.py`; `tests/test_event_lifecycle_postgres.py`; `tests/test_publication_authorization.py`; `tests/test_publication_postgres.py`; `tests/test_publisher_safety.py`.
- Diff summary: 769 insertions, 116 deletions. No untracked files. `git diff --check`: PASS. No active pytest/unittest process remained.
- Module 12's four-file lifecycle correction is preserved and was not reimplemented or rerun in this focused batch.

### Module 21 implementation present locally

- `ContentVerificationResult.evidence_status` maps successful PASS results with approved claim IDs to VERIFIED and rejected/unapproved results to UNVERIFIED; runtime authorization wiring uses this property.
- Removed caller-supplied `duplicate_policy_passed=True`. Authorization now carries catalyst/cooldown context and checks persisted recent posts, unresolved SUBMITTING/PUBLICATION_UNKNOWN attempts, competing active quota reservations, clock skew, and ledger availability. Exceptional catalyst cooldown exemptions do not bypass unresolved attempts.
- SQLite/PostgreSQL publication paths resolve an existing idempotency key before new-publication cooldown checks. New attempts are checked against persisted duplicate policy and rechecked immediately before POST, alongside provenance/lifecycle validation. PostgreSQL authorization/attempt creation uses a symbol-scoped advisory transaction lock.
- Added independent default-off `PUBLISHER_ENABLED`; omitted setting defaults false. Publisher/media side effects require DRY_RUN=false and explicit publisher enablement. Operational requirement remains `DRY_RUN=1`, publisher disabled.
- Image upload reads the exact bytes, verifies SHA-256 against supplied and authorized hashes, then passes immutable `AuthorizedImagePayload` bytes to the uploader; the uploader does not reopen the file.
- End-to-end test initially failed because `Layer1Store` intentionally has no posts/publication_attempts tables. Fail-closed application behavior was preserved; the disposable test fixture now creates those minimal ledger tables.

### Local verification

- Successful focused batch: `tests.test_content_verification`, `tests.test_publication_authorization`, `tests.test_publisher_safety`, `tests.test_publication_runtime`, `tests.test_end_to_end_pipeline`, `tests.test_cloudflare_image_generation`, `tests.test_publication_postgres`: **127 passed, 0 failed, 19 skipped**.
- The system Python lacked Pillow; no dependency was installed. The passing run used the pre-existing `/tmp/binance-layer1-audit/.venv/bin/python` only as interpreter while executing/importing code from the canonical worktree. No other worktree was checked out or modified.
- The 19 skips are environment-guarded PostgreSQL integration tests because `TEST_POSTGRES_DSN` is absent in the current shell. Mocked PostgreSQL publisher tests ran and passed.
- `compileall -q main.py image_engine.py layer1 tests`: PASS. `git diff --check`: PASS. Publisher transports were mocked; no real Square post or media upload occurred.

### Neon target and direct PostgreSQL blocker

- Read-only Neon metadata identifies project `Binance-bot-production` (`orange-glade-36037611`), branch `module9-pg-lease-fencing-disposable` (`br-falling-butterfly-az03rryi`), database `binance_onchain_test`. Branch state READY; parent `br-falling-bread-azl8rggt`.
- A read-only Neon MCP SELECT confirmed `current_database() = binance_onchain_test`. The connector session reported loopback `127.0.0.1/32` and `pg_stat_ssl.ssl=false`; this proxied connector session does not certify direct application-client TLS.
- Current canonical RDC shell and login shell have neither `TEST_POSTGRES_DSN` nor `TEST_POSTGRES_ALLOWED_HOST`; no test-env file was found in the canonical worktree. No DSN/password was printed or retrieved. The previously documented endpoint host is `ep-autumn-frost-azvk3fj4.c-3.ap-southeast-1.aws.neon.tech`, but direct host-allowlist and TLS preflight cannot be repeated without the approved local DSN.
- Therefore the PostgreSQL publication suite has **NOT** been verified green after the idempotency-ordering correction. Do not claim Module 21 complete. Do not retrieve a privileged Neon connection string as a workaround. No Neon data/schema writes or production/default-branch access occurred.

### Remaining acceptance and exact next action

1. Recover the approved direct test DSN and allowlist from the intended local test configuration without printing credentials; verify exact database, branch/host and TLS.
2. Run PostgreSQL publication authorization/integration acceptance: persisted duplicate post, pending/unknown attempt fence, same-key replay, competing reservations, final pre-submit revalidation, transaction rollback/error paths and advisory-lock concurrency.
3. Review/test PostgreSQL fail-closed behavior when a duplicate-ledger query fails inside the authorization transaction; verify deliberate rollback and RESERVED quota outcome.
4. Reconcile SQLite/PostgreSQL behavior after integration acceptance.
5. Durable scheduled workflow state, quota recovery, crash recovery and full dry-run end-to-end acceptance remain outstanding.

Safety: publisher disabled, `DRY_RUN=1`, no real Square post, no production DB writes, no credential/schedule change, no Render deployment, no paid provisioning, and all other worktrees preserved.



## 2026-11-18 — PostgreSQL pre-submit rejection classification hardening

- Continued from PR #14 on `layer-1/module9-onchain-continuation`; latest verified code head: `971a1a06876920408cac74c3e4d4366411459570`.
- Audited the PostgreSQL publication path after the persisted duplicate-policy implementation. The duplicate-policy query itself fails closed: database/query errors propagate from the transaction and prevent the HTTP POST.
- Found a state-classification defect: if the final PostgreSQL authorization/provenance/duplicate preflight failed before the network request, the publisher's broad exception handler recorded `PUBLICATION_UNKNOWN`. This was incorrect because no POST had been attempted; it also retained quota as an unresolved outcome.
- TDD evidence: new mocked publisher regression first failed RED on commit `011d9faaaa854a959caa6076bc6a5dd169a4355f` (684 tests, 1 failure, 40 PostgreSQL skips). It asserted no HTTP call and a known `FAILED_CONFIRMED` state for a pre-submit ledger failure.
- Minimal fix on commit `971a1a06876920408cac74c3e4d4366411459570`: pre-submit validation now has its own exception boundary. A preflight rejection records `FAILED_CONFIRMED`, returns a known no-submit result, and does not call the Binance transport. The existing post-request ambiguous network exception path still records `PUBLICATION_UNKNOWN`.
- GitHub Actions run `44220220216`: **SUCCESS**, compile step passed, **684 tests, 0 failures, 40 skipped**. The regression passed. The 40 skips remain PostgreSQL integration tests gated by missing `TEST_POSTGRES_DSN`; this CI run does not prove direct PostgreSQL integration acceptance.
- No live Binance request, media upload, real Square post, production DB write, workflow dispatch, deployment, credential/schedule change or publisher activation occurred. Keep `DRY_RUN=1` and `PUBLISHER_ENABLED=false`.
- Next: continue Module 21 transaction/error/recovery audit and arrange approved disposable-branch PostgreSQL acceptance without exposing a DSN or touching production. Module 11 semantic verification, live DeepSeek/Cloudflare provider acceptance, and full production cutover remain incomplete.



## 2026-11-18 — Explicit operator recovery for interrupted run leases

- Added manual recovery APIs for SQLite `RunLease` and PostgreSQL `PostgresRunLease` / `PostgresPublicationStore`.
- Recovery is never automatic and never replays the pipeline. It requires an exact expected run ID, explicit `process_termination_confirmed=True`, non-empty operator evidence and operator identity. A mismatched lease owner, non-RUNNING record or invalid prior summary fails closed.
- Recovery atomically marks the run `INTERRUPTED`, appends operator-recovery metadata to the run summary, and removes only the matching lease. If no lease exists it returns false.
- PostgreSQL acquire, normal finish and manual recovery now use the same transaction-scoped advisory lock and consistent lock ordering to serialize terminal completion against recovery.
- Added SQLite mocked/temporary-database coverage and a guarded PostgreSQL integration regression. GitHub Actions run `44220831869` on head `c1cd293046a2bf2ca15a25178ec77b97340ba7a1`: **SUCCESS**, compile passed, **687 tests, 0 failures, 41 skipped**.
- The new PostgreSQL recovery integration test is among the guarded skips because `TEST_POSTGRES_DSN` is not configured in hosted CI. Only SQLite and mocked adapter behavior are verified here.
- No run was force-released in any connected database; no DB writes, production changes, provider calls, publisher activation, real Square post, workflow dispatch, merge or deployment were performed.
- Remaining: run the guarded PostgreSQL recovery/authorization suite against the approved disposable test branch, validate crash/unknown-publication reconciliation end-to-end, and complete provider/semantic acceptance. Keep `DRY_RUN=1` and publisher default-off.



## 2026-11-18 — Preserve PostgreSQL-confirmed publication when local history fails

- Audited the post-acceptance persistence sequence in the PostgreSQL publisher. Once Binance returns a valid success response with an external post ID, the authoritative PostgreSQL attempt is first transitioned to `PUBLICATION_UNKNOWN` with the remote identity, then finalized to `PUBLISHED_CONFIRMED`.
- Found a defect: a later secondary `_save_locally()` / JSONL history write exception was caught by the broad submission handler and the method returned `PUBLICATION_UNKNOWN`, even though PostgreSQL already held `PUBLISHED_CONFIRMED`. The follow-up attempt transition was invalid and could misreport confirmed publication.
- TDD: regression failed RED on commit `4b2e61a97fcfa53ba717b4edc56c7be51b7125e3` (688 tests, 1 failure, 41 skipped).
- Fix on commit `aa059d6c128d25a9388ecf4eca882fa417a3fb14`: secondary local history persistence is now best-effort after durable PostgreSQL confirmation. Failure is logged by exception class only; result remains `PUBLISHED_CONFIRMED` with the actual remote post ID. The authoritative ledger is not downgraded.
- Additional run-lease guard: PostgreSQL adapter now refuses an active owner process attempting to recover its own lease. TDD regression was observed RED on `23b5f4e93981825bd204f00f71b28118143c0ea3`, then fixed.
- Final GitHub Actions run `44221215550` on `d963542d2f3de46ffd8a8c1387e41d0a1d30a9e9`: **SUCCESS**, compile passed, **688 tests, 0 failures, 41 skipped**.
- The 41 skips remain guarded PostgreSQL integration tests; no direct PostgreSQL acceptance is implied. No live Binance request or real post was made.



## 2026-11-18 — SQLite confirmed-publication finalization hardening

- Mirrored the PostgreSQL post-confirmation protection into the SQLite publisher: after a valid Binance response and durable `PUBLISHED_CONFIRMED` attempt state, a secondary local Markdown/history write failure is logged but cannot downgrade the publication result.
- Added a regression for quota finalization failure after remote confirmation. The attempt remains `PUBLISHED_CONFIRMED`; if the quota status update fails, the reservation remains `PUBLICATION_UNKNOWN` (an active conservative reservation) and a critical operator-review log is emitted. It is not released and cannot silently free daily quota.
- The test's initial expected reservation state was corrected: the publisher had already moved the reservation to `PUBLICATION_UNKNOWN` immediately after remote acceptance, before local post persistence. That is the safe state to retain if final quota confirmation fails.
- Final hosted GitHub Actions run `44221784199` on head `d98499b206d56493393e4e9a1923e663e40ef4b8`: **SUCCESS**, compile passed, **690 tests, 0 failures, 41 skipped**.
- The 41 skips remain guarded PostgreSQL integration tests requiring `TEST_POSTGRES_DSN`; they are not passed. No real Binance post or media upload was performed.
- SQLite and PostgreSQL publishers now preserve a confirmed external post when only secondary local history persistence fails. PostgreSQL stores attempt+quota state atomically; SQLite keeps an unresolved quota reservation if its separate final quota transition fails, pending operator review.



## 2026-11-18 — SQLite quota-finalization failure remains safely reserved

- Added a deterministic regression for a quota status write failing after the SQLite publisher has already persisted the attempt as `PUBLISHED_CONFIRMED`.
- The attempt/result must remain `PUBLISHED_CONFIRMED`; the quota reservation remains `PUBLICATION_UNKNOWN` (still counted as active) if the separate final quota transition fails. A critical log records the need for operator review. No reservation is released and no retry is enabled.
- Latest hosted GitHub Actions run `44221784199` on `d98499b206d56493393e4e9a1923e663e40ef4b8`: **SUCCESS**, compile passed, **690 tests, 0 failures, 41 skipped**.
- The 41 skips are PostgreSQL integration tests gated by missing `TEST_POSTGRES_DSN`; they are not passes. No live Binance request, upload or real post occurred.



## 2026-11-18 — Official provider model identifier audit

- Verified against current official DeepSeek API model-list documentation: `deepseek-flash` is a valid API model ID; `deepseek-v4-pro` is also listed. The configured `deepseek-flash` identifier is not a guessed model name. Official source: https://api-docs.deepseek.com/api/list-models/
- Verified against current official Cloudflare Workers AI model documentation: `@cf/black-forest-labs/flux-2-klein-4b` is a valid Workers AI text-to-image model ID. The docs specify multipart form-data requests and fixed four-step inference for this distilled model; the current implementation uses multipart and does not attempt to override steps. Official source: https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/
- This is documentation/model-ID verification only. No authenticated provider request or image generation was executed. Cloudflare model pricing is published per output tile; do not assume usage is free or trigger provider verification without explicit cost approval.



## 2026-11-18 — SQLite final pre-submit fail-closed classification

- TDD exposed that a SQLite persisted duplicate-policy query exception during the final pre-submit revalidation was falling into the broad post-request exception handler and being recorded as `PUBLICATION_UNKNOWN`, even though the HTTP POST had not begun.
- The final event/provenance and duplicate-policy checks plus local request construction now have a dedicated pre-submit exception boundary. Any exception before transport invocation returns known `FAILED_CONFIRMED`, attempts to finalize the attempt and quota as `FAILED_CONFIRMED`, and never invokes Binance transport. If either local ledger update also fails, the attempt/reservation remains fenced and a sanitized critical log is emitted.
- RED: run `44222317391` initially failed because the test injected the error at the earlier authorization check; the test was corrected to fail only the final revalidation. GREEN: run `44222425776` on `4303c466d7af51fd72f9e7b945144dda653038fe`: **SUCCESS**, compile passed, **691 tests, 0 failures, 41 skipped**.
- The 41 skips are PostgreSQL integration tests requiring `TEST_POSTGRES_DSN`; this does not prove PostgreSQL acceptance. No live Binance request/post occurred.



## 2026-11-18 — Atomic SQLite publication attempt/quota finalization

- Replaced separate SQLite publication-attempt and quota finalization writes with one transaction in `PostPublisher._finish_attempt`.
- The method now enforces allowed attempt transitions and updates the linked quota reservation by `attempt_id` in the same transaction. It prevents terminal-state downgrade and inconsistent attempt/quota finalization.
- Normal authorized publishing initializes the quota schema before attempt finalization. Legacy/private attempt-only callers without the quota table retain their existing behavior; the method detects that schema absence explicitly.
- Removed redundant post-finalization quota writes. The pre-submit `SUBMITTING` and pre-network `RELEASED` transitions remain separate and fail closed.
- This supersedes the prior temporary behavior where a confirmed SQLite attempt could retain a `PUBLICATION_UNKNOWN` quota reservation after a separate final quota write failed.
- GitHub Actions run `44223021885` on `acf9d8124cf69edfc98db606ab32080a71fdd234`: **SUCCESS**, compile passed, **691 tests, 0 failures, 41 skipped**. The 41 PostgreSQL integration tests remain skipped without `TEST_POSTGRES_DSN`.
- No live Binance request/post or production database write occurred.



## 2026-11-18 — PostgreSQL duplicate-ledger fail-closed unit coverage

- Added an executable unit test proving `PostgresPublicationStore.validate_persisted_duplicate_policy` propagates a duplicate-ledger query failure instead of converting it to an empty/no-block result.
- The publisher's PostgreSQL pre-submit boundary converts this propagated exception into a known no-submit `FAILED_CONFIRMED` outcome before transport invocation.
- GitHub Actions run `44223361236` on `81429026c96dc5a06f7ac646d35c224f19983710`: **SUCCESS**, compile passed, **692 tests, 0 failures, 41 skipped**.
- This is a mocked unit test; the 41 PostgreSQL integration skips still require the approved disposable test DSN/host allowlist.



## 2026-11-18 — Cloudflare generated-image format/extension consistency

- Added a regression showing the Workers AI image generator previously accepted valid PNG bytes for an output path ending in `.jpg`, writing a mislabeled artifact.
- The generator now checks the decoded image format against the requested artifact extension (`.png` → PNG, `.jpg/.jpeg` → JPEG, `.webp` → WEBP) before writing. A mismatch fails closed and no target file is created.
- TDD: RED run `44223544726`; GREEN run `44223645854` on head `50fde05c9c3576a5d16db36e39e0f7d15f249b93`: **SUCCESS**, compile passed, **693 tests, 0 failures, 41 skipped**.
- The 41 skipped tests remain PostgreSQL integration tests gated by `TEST_POSTGRES_DSN`. No live Cloudflare inference or Binance media upload was run.



## 2026-11-18 — Module 20 final image format/extension binding

- Added a regression showing PNG bytes under a `.jpg` filename passed visual QA because the validator checked decoded format but not the filename extension.
- `VisualQualityEngine` now requires both PNG-decoded content and a `.png` path for the final composite artifact. The sidecar/draft/hash checks remain unchanged.
- TDD: RED run `44223868599`; GREEN run `44223962776` on `f501336c07fa8c28405782ec38a23569d7d9b956`: **SUCCESS**, compile passed, **694 tests, 0 failures, 41 skipped**.
- The 41 PostgreSQL integration tests remain skipped without `TEST_POSTGRES_DSN`; no live Cloudflare inference or Binance media upload occurred.



## 2026-11-18 — Module 13 cross-asset research package isolation

- TDD found `DeepResearchEngine.build` accepted claims with `asset_id=None` even when their `subject` was another canonical CoinGecko asset, allowing a verified foreign-asset claim and evidence to enter the selected asset's research package.
- Fixed claim scoping: explicit claim asset IDs must match the selected asset; unbound claims are eligible only when their subject equals the selected canonical asset ID.
- Unbound evidence records whose subject explicitly names a different canonical asset are excluded. Source coverage is now calculated only from cutoff-eligible evidence actually linked to selected-asset claims, not every accepted unbound evidence record in the registry.
- Regression RED run `44224206173`; GREEN run `44224293433` on `6c34cc8b5ac258169bb790c4d2f4aa7fe90fb03b`: **SUCCESS**, compile passed, **696 tests, 0 failures, 41 skipped**.
- The 41 PostgreSQL integration skips remain unverified; no live provider or publisher calls were made.



## 2026-11-18 — Module 13 canonical subject/asset consistency hardening

- Extended the Module 13 cross-asset fix after a second regression showed a malformed claim could carry the selected `asset_id` while its canonical `subject` named a different CoinGecko asset. Evidence Verification matched the malformed claim/evidence pair, so filtering only on `asset_id` was insufficient.
- Research packages now reject any claim or evidence record whose subject explicitly uses a different canonical `coingecko:` identity, regardless of whether the optional `asset_id` field claims the selected asset. Unbound non-canonical event subjects remain eligible only through a selected-asset claim's evidence links.
- Regression RED run `44224711294`; GREEN run `44224786514` on `018eb43369bcb3b3c95560ce7f0935fee2c0a7de`: **SUCCESS**, compile passed, **696 tests, 0 failures, 41 skipped**.
- PostgreSQL integration tests remain skipped; no live provider or publishing calls.


## 2026-11-18 — Local Module 11 coding continuation (PR #14)

- Reconnected to the existing GitHub repository and fetched PR #14 head `b399a6feaa03bceb6ce5dda48e84d4b35889e25f` from `layer-1/module9-onchain-continuation`.
- The original `/root/Binance-bot` checkout was on `feature/binance-cms-announcement-worker` with three pre-existing modified announcement-worker files. Those changes were preserved. A separate worktree was created at `/tmp/binance-w2e-continuation` from the exact PR #14 head, with local branch `work/module9-continuation-local`.
- TDD found a Module 11 false-positive: a positive market-change value paired with “down 5%” could be marked VERIFIED. Additional false positives allowed negated and modal/uncertain market assertions to pass.
- Added fail-closed directional consistency for `market.price_change` / `market.change_24h`, plus negation and modal/uncertainty rejection. Explicit numeric signs must agree with directional wording; unsigned values can use an unambiguous direction word; neutral wording is valid only for zero movement.
- Regression tests first failed against the previous implementation, then passed after the fix. Final isolated-worktree validation: Python `compileall` passed; full `unittest discover` suite **698 tests, 0 failures, 41 skipped**; `git diff --check` passed. The 41 skips are PostgreSQL integration tests requiring `TEST_POSTGRES_DSN`, not successful database tests.
- Module 11 remains PARTIAL: broad semantic entailment, all natural-language paraphrases, and ambiguous shared-subject/elliptical claim forms are not solved by this bounded deterministic fix. Module 14 remains fail-closed until an owner-approved scoring policy and calibrated factor definitions are supplied.
- All changes remain local and uncommitted/unpushed. No changes were made to the original dirty checkout. No database/production write, provider inference, paid Cloudflare generation, Binance upload/post, publisher activation, workflow/credential/schedule change, merge or deployment occurred.

## 2026-11-18 continuation update — Module 11 semicolon segmentation

- Continued from the existing PR #14 continuation branch in the isolated worktree `/tmp/binance-w2e-continuation`; original `/root/Binance-bot` checkout remains untouched.
- Fixed `split_atomic_claims()` so semicolon-delimited clauses split even when the semicolon is not followed by whitespace. The new regression was observed failing before the one-line implementation change, then passed with the existing semicolon regression.
- Verification: focused Module 11 suite **64 passed, 0 failed**; full suite **699 tests, 0 failures, 41 skipped**. The 41 PostgreSQL integration skips are not passes and remain gated by missing `TEST_POSTGRES_DSN`.
- Module 11 remains PARTIAL: deterministic clause splitting and structured checks do not provide general semantic entailment or cover every ambiguous natural-language form.
- Pushed to the existing PR #14 continuation branch in commit `7e8cc99`; remote file content was verified. No DB writes, live DeepSeek/Cloudflare calls, Binance publishing, production changes, deployment or merge.
