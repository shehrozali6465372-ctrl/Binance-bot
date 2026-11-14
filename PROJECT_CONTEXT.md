# Binance Square Write-to-Earn Agent — Canonical Project Context

Last updated: 2026-11-12 (UTC) — corrected continuation rules and Module 9 lease handoff

This is the canonical working context for continuing the Binance Square Write-to-Earn Agent project. Keep this file in this GitHub repository and update it as work progresses. Do not use ChatGPT Library or create a parallel Library copy.

## CURRENT CONTINUATION OVERRIDE — 2026-11-12

This section is the authoritative instruction for the next continuation. If older notes elsewhere in this file conflict with it, follow this section.

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
