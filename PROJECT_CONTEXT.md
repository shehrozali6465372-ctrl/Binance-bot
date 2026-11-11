# Binance Square Write-to-Earn Agent — Canonical Project Context

Last updated: 2026-11-11 (UTC)

This is the canonical working context for continuing the Binance Square Write-to-Earn Agent project. Keep this file in this GitHub repository and update it as work progresses. Do not use ChatGPT Library or create a parallel Library copy.

## Repository and working branch

- Repository: https://github.com/shehrozali6465372-ctrl/Binance-bot
- Repository: `https://github.com/shehrozali6465372-ctrl/Binance-bot`
- Current implementation branch: `layer-1/module8-market-analysis`
- Module 8 implementation commit: `820a755e4a233b3fe7c812f795a9d6aba6e0a29b`
- Context update commit that introduced this file to the Layer 1 stack: `eb1919f5655d888cce28a61683846107d67bb40c` (the current context follow-up is a separate commit).
- Stacked Layer 1 PR chain: #7 → #8 → #9 → #10 → #11 → #12 (PR #12 will be created from the current branch after context update).
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
| Module 8 — Market Analysis | Implemented on commit `820a755e4a233b3fe7c812f795a9d6aba6e0a29b`; 133-test full local suite passed, including eight market-analysis tests plus runtime persistence checks. PR #12 CI runs `43020470472` and `43020622048` passed for heads `eb1919f5655d888cce28a61683846107d67bb40c` and `7ce44bdac0cf75f2525faacd07a33755df9f72bf`, respectively. |
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
| #12 | `layer-1/module8-market-analysis` | `eb1919f5655d888cce28a61683846107d67bb40c` (contains implementation commit `820a755`) | `43020470472`, `43020622048` — success | Open, non-draft, unmerged; https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/12 |

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

1. Push `layer-1/module8-market-analysis`, create stacked PR #12 targeting `layer-1/module5-6-candidate-intelligence`, then verify the exact head SHA's CI. Keep all PRs unmerged until explicitly approved.
2. Continue Module 9 only after an evidence-based provider evaluation: exact network/token coverage, official docs, open-source license/maintenance, security, rate limits, data freshness/finality, cost, and operational burden. Do not add a paid provider or infrastructure without approval.
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
