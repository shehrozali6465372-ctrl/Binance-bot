# Binance Square Write-to-Earn Agent — Canonical Project Context

Last updated: 2026-11-10 (UTC)

This is the canonical working context for continuing the Binance Square Write-to-Earn Agent project. Keep this file in this GitHub repository and update it as work progresses. Do not use ChatGPT Library or create a parallel Library copy.

## Repository and working branch

- Repository: https://github.com/shehrozali6465372-ctrl/Binance-bot
- Current feature branch: `feature/binance-cms-announcement-worker`
- Feature branch HEAD before this verification-context update: `748505bb5462d0a351685f9f922b5056049aebf3`
- Draft PR #2: https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/2
- PR title: Add isolated Binance CMS announcement listener
- PR base: `layer-1/completion-hardening`
- PR #2 is open and draft; it has NOT been merged.
- Do not merge, deploy, or alter the production publisher without separate explicit approval.

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

## Current verified status at last handoff

| Area | Status |
|---|---|
| Existing publisher | Existing workflow must remain untouched |
| Worker feature code | Draft implementation exists on feature branch |
| Feature PR | PR #2 open, draft, not merged |
| Main branch | Not changed by this worker PR |
| Dedicated Binance database | Not created |
| Render Binance worker | Not created |
| Paid resource approval | Not granted |
| Package lockfile | Missing |
| Actual SDK runtime smoke test | Not verified |
| GitHub Actions latest run | PASS: run `42715929886`, head SHA `748505bb5462d0a351685f9f922b5056049aebf3`, PR event, mocked test job success |
| Local mirrored unit tests | 12 passed, 0 failed |
| Live Binance stream test | Not performed |
| Python agent importer | Not implemented |
| Real Binance Square post during tests | None; must remain none |

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

1. Re-fetch the current feature branch and this context file before continuing; do not assume the SHAs above remain current.
2. Generate and commit `announcement-worker/package-lock.json` using Node >=22.12 and verify `npm ci`.
3. Strengthen tests to cover SDK import/export contract and worker lifecycle with injected mocks; no real network or publishing.
4. Verify GitHub Actions run status for the exact latest feature commit; fix failures and rerun.
5. Design and implement the Python PostgreSQL importer in a separate, reviewable change. Keep it read-only with respect to the announcement ledger and preserve existing publisher behavior.
6. Add safe integration tests proving imported announcement events reach Layer 1 candidate evaluation without publishing a Square post.
7. Reassess hosting architecture and current Render pricing. Do not provision paid resources without explicit cost approval.
8. Only after tests and security review, request approval for any merge or deployment. PR #2 must remain unmerged until approved.

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