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
## Progress update — Layer 1 CMS importer and reproducible CI

### Implemented on the feature branch
- Added layer1/announcement_importer.py. It reads only recent documented CMS rows from binance_announcement_events using parameterized SELECT SQL; it sets PostgreSQL sslmode=require and default_transaction_read_only=on, uses a 5-second connect timeout, and closes cursor/connection.
- Importer uses a 7-day lookback by default and caps reads at 250 rows (hard cap 1,000). It selects the latest stored revision per source_id.
- Asset attribution is deliberately conservative: it accepts only uppercase ticker symbols in parentheses and only when the symbol maps to exactly one current candidate with a canonical coingecko asset ID. Ambiguous or free-standing symbol matches are rejected.
- Validated AnnouncementEvidence is persisted into Layer1Store and passed into CandidateDiscoveryFilteringEngine.build() for the matching asset. The candidate evidence ledger now records announcement source IDs.
- The importer is optional until ANNOUNCEMENT_DATABASE_URL is configured. Without that environment variable provider health is UNAVAILABLE_NO_DATABASE_URL and existing Layer 1 market flow remains unchanged. If configured but the read/import fails, the Layer 1 cycle fails closed.
- No Square publisher code, publisher credentials, direct publishing routes, or publishing logic were changed. A dedicated integration test patches the publisher to raise if called and verifies announcement evidence reaches the Layer 1 candidate ledger.
- Added tests for exact ticker matching, ambiguous symbol rejection, free-standing ticker rejection, invalid event rejection, read-only SQL, TLS/read-only connection options, query time window, and Layer 1 evidence integration.

### Worker SDK and dependency verification
- Added announcement-worker/package-lock.json (lockfile v3, 48 installed packages) using Node v22.23.1 / npm 10.9.8.
- announcement-worker/package.json now declares type=module.
- CI now runs npm ci and an offline official @binance/cms SDK export/constructor contract test; it does not open a live Binance connection.
- Verified locally on the authorized device in /tmp/binance-bot-check: npm ci completed and Node tests passed 13/13.

### Verified CI result
- Latest verified feature commit: d47466f3aa10c7695929a4be18b3dad3367ef900.
- GitHub Actions run 42719504744 completed SUCCESS for that exact commit.
- Node job: 13 passed, 0 failed; npm ci completed.
- Python Layer 1 job: 62 tests passed; Python compileall passed.
- The Python importer tests use an injected fake connector. No real PostgreSQL server, Binance WebSocket, or Square publishing endpoint was contacted.
- The earlier failing CI runs were corrected; the latest run is green. Do not treat earlier failed runs as the final state.

### Activation blockers / boundaries
- The current scheduled run_bot.yml workflow still installs Pillow only and does not provide ANNOUNCEMENT_DATABASE_URL or psycopg. The importer is therefore implemented and tested but not active in the scheduled production workflow.
- Wiring the new database secret and psycopg dependency into the existing scheduled publisher workflow requires a separate explicit approval because it changes that workflow's environment. No credentials or secrets were added or read.
- No live worker service, PostgreSQL database, Render service, Cloudflare resource, or paid resource has been created. No live Binance CMS connection was opened and no real Square post was published.
- PR #2 remains open, draft, and unmerged.

### Next steps
1. Add mocked worker lifecycle tests for transport error/close events, queued message handling, shutdown and pool cleanup; no network access.
2. Review importer SQL against a disposable PostgreSQL test instance or equivalent controlled fixture before production activation.
3. Obtain explicit approval before modifying run_bot.yml to install psycopg and pass ANNOUNCEMENT_DATABASE_URL from a GitHub secret. The secret itself must be created by the repository owner; never place its value in code or context.
4. Confirm worker runtime/database hosting and exact costs before provisioning; no paid resources without approval.
5. Keep PR #2 unmerged and deployment disabled until integration, security review, and explicit approval are complete.

## Continuation update — current branch verification (2026-11-10 UTC)

This section supersedes earlier status/gap statements above where they conflict.

- Current feature branch HEAD before the optional-import failure fix: 8f43849d3464e6ce5432b3f9ccc3b50456640d67 (branch: feature/binance-cms-announcement-worker).
- PR #2 remains open, draft, and unmerged: https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/2.
- Latest verified GitHub Actions run before this fix: run 42719943415, head 8f43849d3464e6ce5432b3f9ccc3b50456640d67, conclusion SUCCESS. Both mocked-announcement-tests and python-layer1-tests passed.
- The worker now has a committed npm lockfile, npm ci in CI, an offline official SDK export/constructor contract test, and mocked lifecycle tests for message persistence, transport error/reconnect state, failed connection cleanup, database initialization failure cleanup, and graceful shutdown.
- The Python importer and Layer 1 integration are implemented on this feature branch. Tests verify that imported announcement evidence reaches candidate evaluation and that the Square publisher is not instantiated.
- Worker CI does not perform a live Binance connection or real PostgreSQL integration. Python importer tests inject a fake connector; they do not prove real PostgreSQL compatibility.
- Root scheduled .github/workflows/run_bot.yml currently installs Pillow only and does not configure ANNOUNCEMENT_DATABASE_URL or install psycopg. Therefore the importer is not activated by the existing scheduled workflow. Do not modify that workflow or add its secret/dependency without separate explicit approval.
- A configured importer failure previously propagated before the Layer1Store cleanup block, potentially interrupting the established cycle and leaking the SQLite connection. The current continuation fix wraps this optional enrichment read, records DEGRADED_IMPORT_FAILED without logging exception text/DSNs, and allows the established market-data path to continue. A regression test covers that behavior.
- announcement-worker currently creates its PostgreSQL tables at startup. Before production, split schema migration privileges from the runtime worker role; do not give the listener a broad owner/admin credential.
- sslmode=require encrypts the importer connection but does not provide the strongest hostname verification. Before production, decide and test a certificate-verifying TLS mode supported by the selected database provider.
- No Binance API key, database secret, production connection, paid resource, Render service, Cloudflare resource, or live Square post was created or used in this continuation.
- No production deployment, PR merge, or publisher workflow change was performed.

### Remaining production gates
1. Confirm a dedicated durable PostgreSQL instance and exact monthly cost; obtain explicit approval before provisioning.
2. Create separate migration and least-privilege worker/importer database roles.
3. Confirm the Python runtime dependency installation strategy for psycopg; this requires approval before changing the scheduled workflow.
4. Test worker persistence and importer query against a disposable real PostgreSQL instance with no production credentials.
5. Validate TLS certificate/hostname verification, secret rotation, and Render environment configuration.
6. Run a controlled live Binance CMS connectivity test only after credentials and infrastructure are explicitly approved; keep Square publishing disabled throughout.
7. Review PR merge conflicts/base branch and obtain explicit merge/deployment approval.


## Latest post-fix verification (2026-11-10 UTC)

- Optional announcement importer failure handling and its regression test were committed in code commit 05d6bcd793400a936ea73da20804dcd3a16db393.
- GitHub Actions run 42720344133 tested that exact code commit and completed SUCCESS. Both Node worker tests and Python Layer 1 tests passed.
- The regression confirms a failed optional CMS database import is reported as DEGRADED_IMPORT_FAILED while market observations/candidate evaluation continue. Exception text is not logged.
- The branch head after the context-only update will be recorded by GitHub; the verified code commit remains 05d6bcd793400a936ea73da20804dcd3a16db393.
- GitHub reports PR #2 as open, draft, unmerged, and mergeable=false (mergeable_state=dirty). The base branch has advanced one commit beyond the PR's recorded base; that base commit adds .github/workflows/announcement-worker-tests.yml, a path also independently added/extended on this feature branch. The feature branch therefore needs an explicit base-sync/conflict-resolution decision. No merge, rebase, PR retarget, or deployment was performed because merge approval has not been granted.
- Latest compare at this check: feature branch 36 commits ahead and 1 commit behind layer-1/completion-hardening.
- This branch's workflow changes, worker, importer, and tests remain unmerged. The production scheduled workflow .github/workflows/run_bot.yml remains untouched.


## Approved branch synchronization completed (2026-11-10 UTC)

- User explicitly approved syncing the feature branch with the base and resolving the workflow conflict.
- Created a non-rewrite two-parent merge commit: 0aa7aed7cf2e47c64fbdb6d6c65a0cc3d1e9dc19.
  - First parent (feature history): 346085c95d847bc69b1f8ed7c0496346d8bbfd44.
  - Second parent (base branch): ec1ee7b6902e5f24d37c54e8e5fd2c71334d1b42.
- Conflict was limited to .github/workflows/announcement-worker-tests.yml. Preserved the feature branch's expanded workflow because it retains the base workflow while also performing locked npm ci, the offline SDK contract tests, and the Python Layer 1 test job.
- The feature branch is now 40 commits ahead and 0 behind layer-1/completion-hardening. No force push or history rewrite was used.
- GitHub PR #2 is now open, draft, unmerged, and mergeable=true. It has NOT been merged.
- GitHub Actions push run 42722549557 and PR run 42722558943 both completed SUCCESS on merge commit 0aa7aed7cf2e47c64fbdb6d6c65a0cc3d1e9dc19. In each run, both mocked-announcement-tests and python-layer1-tests passed.
- The publisher workflow .github/workflows/run_bot.yml was not changed. No deployment, live Binance stream connection, Square post, secrets change, database creation, or paid infrastructure provisioning occurred.

## Codex review loop update — 2026-11-10 UTC

### Reviewer selection and review result
- User explicitly selected Codex as the AI reviewer for PR #2.
- Reviewer selection was persisted by the gh-review-loop plugin for `chatgpt-codex-connector`, with trigger phrase `@codex review`. Automatic reviews remain disabled; only explicit review requests should trigger a cycle.
- Posted the first review request on PR #2 at `2026-11-10T00:10:11Z`: https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/2#issuecomment-6754990725.
- Codex completed its code review against commit `11bd1567e2ca69cfe4099ebba2396755a9864184` at `2026-11-10T00:13:33Z` and reported one unresolved P2 (medium) finding.
- Finding: `announcement-worker/src/worker.js`, line 47 — **Drain queued messages before honoring shutdown**. If SIGTERM/SIGINT arrives while callbacks are queued behind a slow database write, shutdown sets `closed` before awaiting `writeQueue`; queued callbacks then return without persisting already-received announcements. Because Binance CMS historical replay is not documented/guaranteed, this can cause permanent event loss.
- Required behavior: stop accepting new stream messages first, allow already accepted/queued writes to drain, then close the database pool and finish shutdown. Preserve error handling and bounded shutdown behavior; do not silently discard accepted messages.
- Review thread: https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/2#discussion_r4519545553.
- Review thread remains unresolved. No reviewer finding has been marked resolved or replied to.

### Verification profile gate and current work state
- gh-review-loop first-run detection identified a monorepo and one candidate check: `npm test` in `announcement-worker/`.
- The full GitHub CI workflow also includes Python compile and Layer 1 unit tests. A proposed customized verification profile was presented with these checks:
  1. `npm test` (working directory `announcement-worker/`)
  2. `python -m compileall -q .`
  3. `python -m unittest discover -s tests -v`
- The verification profile has NOT yet been saved; user has not confirmed the proposed profile. Do not edit code until the profile decision is saved (confirmed or explicit skip) under the gh-review-loop first-run gate.
- No code fix has been made for the P2 finding yet. No code files have changed as part of this review cycle.
- The review-loop cycle receipt recorded 0 fixes, 0 repeat-review requests, and verification skipped because the review finding had not yet been addressed.
- Codex review is complete for commit `11bd1567e2ca69cfe4099ebba2396755a9864184`; the loop has not yet completed the fix/re-review/verification phase.

### Current repository / PR state at this handoff
- Repository: https://github.com/shehrozali6465372-ctrl/Binance-bot
- Branch: `feature/binance-cms-announcement-worker`
- Working clone used for review: `/tmp/Binance-bot-gh-review-loop` on the authorized Remote Desktop Commander device; no personal browser used.
- Feature branch HEAD at review time: `11bd1567e2ca69cfe4099ebba2396755a9864184`.
- PR #2 remains open, Draft, unmerged. Do not mark ready, merge, or deploy without separate explicit approval.
- Existing Binance Square publisher, its schedule, credentials, and production workflow remain untouched.
- No real Binance Square post was published. No live Binance WebSocket or production database was contacted during this review.
- No infrastructure, secrets, database resources, or paid services were created or changed.

### Next steps
1. Obtain user's decision on the proposed verification profile; save it before any code edit.
2. Write a failing regression test that simulates SIGTERM/SIGINT while at least one accepted announcement write is queued behind a delayed database write. Confirm it fails on the current shutdown behavior.
3. Implement the minimal intake-stop / queue-drain / pool-close ordering fix without changing the existing publisher.
4. Run the focused worker test, full worker tests, Python compile, and complete Python Layer 1 suite using the saved profile.
5. Inspect the diff and run the gh-review-loop cycle summary before pushing any code change.
6. Push the fix to the same feature branch, request Codex re-review using the plugin script, and wait for a response against the new commit. Keep the review request cap at 3.
7. Keep PR #2 Draft and unmerged; do not deploy or publish a real Square post.

## Codex shutdown finding — implementation and local verification (2026-11-10 UTC)

- User approved adjusting the local gh-review-loop verification profile to match the repository's actual GitHub Actions scope rather than compiling every unrelated legacy Python file.
- Saved customized verification profile for `shehrozali6465372-ctrl/Binance-bot`:
  1. `npm test` in `announcement-worker/`.
  2. Create an isolated Python virtual environment at `/tmp/binance-bot-verify-venv`.
  3. Install Pillow in that environment, matching the CI dependency.
  4. `python -m compileall -q main.py image_engine.py layer1`.
  5. `python -m unittest discover -s tests -v`.
- The previous broad `python -m compileall -q .` was not aligned with CI and included the unrelated legacy tracked file `python agent_bot.py`, which currently has an existing syntax error. It was narrowed to the exact Python sources compiled by CI; no legacy Python source was edited.
- The host Python installation is PEP 668 externally managed, so Pillow was installed in an isolated `/tmp` virtual environment instead of modifying system Python.
- The saved profile runner completed successfully: all five required checks passed (Node worker tests, venv setup, Pillow install, Python compile, Python unit tests).
- Implemented the Codex P2 shutdown fix in `announcement-worker/src/worker.js`: stop message intake synchronously, unsubscribe, preserve already accepted callbacks in the write queue, await those writes before normal resource closure, make shutdown idempotent, and bound waiting with an injectable 30-second default timeout. If the timeout expires, the pool is deliberately kept open until accepted writes settle, then cleanup runs asynchronously.
- Added two lifecycle regressions in `announcement-worker/test/worker-lifecycle.test.js`: queued accepted messages are drained and post-shutdown messages are rejected; timeout does not close the pool underneath an in-flight write and cleanup happens after it settles.
- Focused worker lifecycle suite passed 6/6 tests before the full profile run. The complete saved verification profile also passed.
- Added `announcement-worker/node_modules/` to `.gitignore`; dependencies are local only and must not be committed.
- At this handoff, these changes are local and uncommitted. The PR review thread remains unresolved pending Codex re-review. No push or re-review request has yet been made in this cycle.
- PR #2 remains Draft, open, and unmerged. No production publisher workflow, deployment, live Binance CMS connection, production database, secrets, paid resources, or real Square post were touched.

### Next actions
1. Inspect final diff and run `git diff --check` plus the saved profile once more after context/ignore updates.
2. Obtain the gh-review-loop cycle summary before commit/push, then commit and push only the scoped fix, tests, `.gitignore`, and this context update.
3. Request Codex re-review with the official gh-review-loop request script and wait for the review result; do not resolve the thread manually.
4. Keep PR #2 Draft/unmerged and retain all production gates listed above.


## Codex follow-up review — recovery and startup cleanup (2026-11-10 UTC)

- Codex re-reviewed commit `84b74912cc1d018760933b6256813fd7df172efc` after one re-review request (cap usage: 1/3).
- The prior P2 shutdown-drain finding is now outdated and was automatically cleared by the review-loop fetch.
- Codex reported two new P2 findings:
  1. `announcement-worker/src/worker.js` — if both the `RECEIVING` state write and subsequent `DEGRADED` state write fail, the chained `writeQueue` remains rejected; later accepted messages are skipped even after the database recovers.
  2. Startup cleanup — if `connect()` succeeds but a later startup step (for example, writing `LISTENING`) fails, the opened WebSocket connection is not disconnected and may keep the process alive.
- A changed-files-only pattern sweep was attempted for the queue recovery cluster. It returned `pattern_too_thin` (0 significant shared tokens; no safe sibling candidates), so no additional files were swept or edited.
- Added two regression tests first and confirmed both failed against the reviewed implementation:
  - `write queue recovers after RECEIVING and DEGRADED state updates both fail` (the queue rejected and caused an unhandled rejection).
  - `startup failure after websocket connect disconnects the opened connection` (connection remained open).
- Implemented scoped fixes in `announcement-worker/src/worker.js`:
  - Queue failure reporting now catches and logs a secondary `DEGRADED` state-write failure without allowing the queue chain to remain rejected. Subsequent message callbacks can execute after transient database recovery.
  - The opened connection and stream are tracked during startup. Startup failure unsubscribes the stream when created, disconnects an already-open connection, and closes the pool.
- Focused worker lifecycle tests now pass 8/8, including both new regressions. These follow-up changes are currently local and uncommitted; full saved-profile verification, review receipt, push, and Codex re-review remain pending.
- PR #2 remains Draft, open, and unmerged. Existing production publisher workflow and schedule remain unchanged. No live Binance CMS connection, real Square post, production database, secret, paid resource, or deployment was used.

### Follow-up fixes verified and pushed to be recorded

- Both new Codex P2 findings were reproduced with failing tests before implementation; the focused lifecycle suite then passed 8/8.
- The saved repo-aware verification profile passed all 5 required checks after the fixes: npm worker tests, isolated venv setup, Pillow dependency install, Python compileall over CI-scoped sources, and the complete Python unittest suite.
- `git diff --check` passed. The gh-review-loop cycle 3 receipt recorded 2 findings fixed locally, 2 still open pending reviewer confirmation, verification passed, and no re-review request yet for this follow-up cycle.
- Queue recovery change suppresses secondary status-write failure after logging it, preventing a rejected promise from poisoning subsequent accepted queue callbacks. Startup cleanup now unsubscribes the stream when available and disconnects the opened connection before closing the pool.

## Codex review cycle 4 — optional importer dependency (2026-11-10 UTC)

- Codex completed another explicit review of PR #2 after the second re-review request. It reported one new P2 finding in `layer1/announcement_importer.py`: the optional runtime path imports `psycopg`, but the repository had no Python dependency manifest and the existing scheduled agent workflow installs only Pillow.
- The two previously reported worker findings were repeated in the review output. Current HEAD `7cc3eef` contains the queue recovery and startup socket cleanup fixes; they must be rechecked against current source and the reviewer must confirm them rather than treating repeated stale threads as proof of a regression.
- Added a test-first regression for the dependency declaration. It failed before implementation because `requirements-announcement-importer.txt` did not exist.
- Added `requirements-announcement-importer.txt` declaring `psycopg[binary]>=3.2,<4` for the optional importer runtime. The manifest is intentionally separate from the publisher's existing dependency installation.
- IMPORTANT remaining deployment gate: the existing scheduled publisher workflow `.github/workflows/run_bot.yml` was not modified, per the standing instruction not to change the publisher workflow/schedule without separate approval. Therefore the new manifest declares the dependency but does not yet cause the scheduled GitHub Actions runtime to install it. To fully close the P2 finding for that runtime, explicit approval is required to add a dependency-install step to that workflow (or to select another approved agent runtime that installs this manifest).
- No real CMS connection, production database, real Square post, deployment, secrets change, paid resource, or publisher schedule change occurred.
- The new dependency-manifest regression passed after adding the manifest. The saved five-check repo-aware verification profile also passed in full on this working tree: worker npm tests, isolated Python venv setup, Pillow install, CI-scoped compileall, and all Python unit tests. `git diff --check` passed.
- Scope limitation: the saved profile does not install `requirements-announcement-importer.txt`; no real PostgreSQL driver connection was attempted. The manifest declaration is verified, but scheduled-runtime installation remains unverified and intentionally awaits separate approval to touch `run_bot.yml`.

## Approved scheduled-runtime dependency installation (2026-11-10 UTC)

- User explicitly approved the narrow `run_bot.yml` dependency-installation change.
- Added only `pip install -r requirements-announcement-importer.txt` to the existing Install dependencies step, after Pillow. No schedule, trigger, publisher code, environment variables, `DRY_RUN`, post limits, cache, or artifact behavior was changed.
- Added a regression assertion that the scheduled agent workflow installs the optional importer dependency. It failed before the workflow edit and passed afterward.
- Both importer dependency tests passed. The full saved verification profile passed all 5 required checks. Installed the manifest into the isolated verification venv and confirmed `import psycopg` succeeds with psycopg 3.3.8. This is a local dependency/import check only; no PostgreSQL connection was made.
- `git diff --check` passed. GitHub Actions will provide the final workflow-level verification after push.
- The gh-review-loop re-review cap is currently exhausted (3/3 requests); no further Codex re-review request was sent. PR remains Draft/open/unmerged; no deployment or live post publishing occurred.


## TLS hostname verification hardening (2026-11-10 UTC)

- Reproduced the existing importer TLS weakness test-first: changed the test expectation to `sslmode=verify-full`; it failed because the importer still passed `require`.
- Updated the read-only Python importer to request `sslmode=verify-full`. This verifies the certificate chain and server hostname using the driver's trusted CA configuration, rather than merely requiring encrypted transport. `default_transaction_read_only=on` and the 5-second connection timeout remain unchanged.
- This is code-level configuration verification only. No actual PostgreSQL connection or certificate handshake was attempted; compatibility with the eventual selected database provider and its CA chain remains a deployment integration gate.


## Database role separation implementation (2026-11-10 UTC)

- Refactored worker startup schema initialization: `AnnouncementStore.initialize()` now performs only zero-row SELECT permission checks against the event and worker-state tables. It no longer executes CREATE TABLE or other DDL using runtime credentials. The worker fails startup before opening the CMS socket if these checks fail.
- Added an explicit `npm run migrate` command backed by `src/migrate.js`. It requires the separate `MIGRATION_DATABASE_URL`, validates PostgreSQL URL plus `sslmode=verify-full`, applies the idempotent schema SQL, and always closes its pool. The migration URL is not read by worker startup.
- Added `migrations/001_runtime_role_grants.sql`: worker receives event INSERT plus SELECT(id), sequence USAGE, and worker-state SELECT/INSERT/UPDATE; importer receives only SELECT on the event ledger. PUBLIC table/sequence grants are revoked. The SQL expects the two login roles to be created securely by the database owner first; no passwords are stored in the repo.
- Enforced `sslmode=verify-full` in the Node worker and migration connection URLs, matching the Python importer. Missing/unverified TLS URLs fail before a database pool is created.
- Added mocked tests for runtime no-DDL privilege checks, migration URL isolation/cleanup, least-privilege grant declarations, and rejection of database URLs without verified TLS. No live database, credentials, role creation, or migration execution was performed.
- This implementation still requires disposable PostgreSQL integration to prove exact role grants, sequence behavior, schema ownership, and TLS certificate hostname validation with the selected provider.
- Database-role separation implementation commit: `2eaf4da27336daf304778300be486956ce975ed9`. The saved local verification profile passed all five checks; the worker suite passed 27/27 tests. GitHub Actions push run `42734335239` and PR run `42734343713` both completed SUCCESS for that exact commit.
- PR #2 remains OPEN, Draft, and mergeable; no merge or deployment was performed. The branch working tree was clean after push.
- Local environment has the PostgreSQL client (`psql`) but no running PostgreSQL server (`pg_isready` reports no response); therefore the grant SQL and migration were not executed against a database. Disposable real-PostgreSQL role/TLS integration remains a hard gate before production.

## Disposable PostgreSQL security integration CI (2026-11-10 UTC)

- Added `announcement-worker/test/postgres-integration.test.js` to exercise the real PostgreSQL role boundary when three disposable test connection URLs are supplied. It verifies worker schema access, event insert plus `RETURNING id`, content-hash duplicate suppression, worker-state upsert, importer ledger read, worker payload-column/DDL denial, importer write denial, and TLS hostname mismatch rejection.
- Added a dedicated `postgres-security-integration` job to `.github/workflows/announcement-worker-tests.yml`. The job creates a short-lived test CA/server certificate, starts an isolated PostgreSQL 16 Docker container, creates separate migration/worker/importer login roles with CI-only passwords, runs the migration as the migration role, applies the grants as database owner, and runs the integration suite. A cleanup step removes the container even after failure.
- Documented the disposable integration test in `announcement-worker/README.md`.
- Local verification: YAML parsed successfully and `git diff --check` passed. `npm test` passed 27 tests with 1 PostgreSQL integration test skipped because this device has no local PostgreSQL server or Docker daemon. This is not evidence that the real database assertions pass.
- The integration job has not yet run on GitHub Actions. Actual SQL grant execution, runtime-role behavior, and TLS chain/hostname verification remain NOT TESTED until the CI job succeeds.
- No production DB credentials, live CMS socket, production publisher workflow/schedule changes, deployment, or real Binance Square post were used. PR #2 must remain Draft/open/unmerged.

## PostgreSQL integration finding and least-privilege correction (2026-11-10 UTC)

- First real GitHub Actions PostgreSQL run successfully started TLS-enabled PostgreSQL 16, created the three distinct roles, executed the schema migration with the migration role, and applied the role grants. It then failed at `AnnouncementStore.save()` with `permission denied for table binance_announcement_events`; the failure is real and not a mocked-test issue.
- Root cause: the worker INSERT uses `ON CONFLICT (content_hash) DO NOTHING`. PostgreSQL requires SELECT privilege on columns used in the conflict target, in addition to SELECT on `id` for `RETURNING`. Official PostgreSQL INSERT documentation explicitly states SELECT privilege is required on `index_column_name` used for conflict-target inference: https://www.postgresql.org/docs/18/sql-insert.html
- TDD correction: tightened the static grant regression to require `SELECT (id, content_hash)` and confirmed it failed before changing the SQL. Updated `001_runtime_role_grants.sql` to grant only those two columns; worker payload fields remain unreadable. README updated to document the precise privilege requirement.
- The integration job exposed the missing grant, but the corrected SQL has not yet been re-run against PostgreSQL. The next required step is push the correction and require the same integration job to pass. Until then, database integration status remains BLOCKED/NOT VERIFIED; do not claim role separation is production-verified.

## Corrected PostgreSQL integration — verified (2026-11-10 UTC)

- The least-privilege fix was committed as `656da6d7f1942492f058ebbf8cb944e8346deceb` (`fix(db): grant conflict-key read to worker`) and pushed to the existing feature branch.
- The real PostgreSQL integration job then passed against disposable PostgreSQL 16: migration role successfully created schema; grants applied; worker `initialize`, event INSERT with `RETURNING id`, duplicate `ON CONFLICT` suppression, and state upsert succeeded; importer could read the ledger but could not write; worker could not read payload columns or create schema objects; `sslmode=verify-full` accepted the trusted localhost certificate and rejected a trusted certificate presented under `wrong.localhost`.
- Exact GitHub Actions evidence: push run `42735817233` completed SUCCESS with all 3 jobs; its PostgreSQL job `129564663457` passed all 28/28 tests, 0 failures, 0 skips. PR run `42735828025` also passed all 3 jobs. The first integration attempt (`42735579908`) failed on the missing `content_hash` read grant; the fix was evidence-driven and verified by the subsequent successful real database run.
- PR #2 remains OPEN, Draft, and mergeable at commit `656da6d`; branch working tree was clean after push.
- Added `PRODUCTION_READINESS.md` with PASS/FAIL/BLOCKED/NOT TESTED evidence, remaining blockers, causes, impacts, fixes and verification methods. Overall verdict remains NOT PRODUCTION READY because the selected production provider's CA/hostname compatibility, live Binance CMS connection, deployment health, monitoring and rollback are not yet verified.
- No production database/credentials, live CMS connection, deployment, paid resource, publisher workflow/schedule change, or real Binance Square post was used.

- Follow-up verification after the `content_hash` grant correction: the saved repo-aware profile passed all 5 required checks again (worker npm tests, venv setup, Pillow install, scoped Python compileall, full Python unittest suite). `git diff --check` and workflow YAML parsing also passed. The real PostgreSQL proof remains the GitHub CI run `42735817233` and PR run `42735828025`.

## PostgreSQL startup timeout hardening (2026-11-10 UTC)

- Added a test-first regression requiring the worker PostgreSQL pool to set a bounded connection establishment timeout. The test failed before implementation because `connectionTimeoutMillis` was unset (node-postgres default is 0/no timeout per its official Pool docs: https://node-postgres.com/apis/pool).
- Worker pool now sets `connectionTimeoutMillis: 10_000` while retaining `max: 3` and the existing application name. Ten seconds allows more tolerance for a cold-starting managed database than a five-second limit; this is a configuration bound, not proof that every network failure mode times out at exactly ten seconds.
- Focused lifecycle tests passed 10/10; full worker suite passed 28/29 with only the PostgreSQL integration test skipped locally (no local server). Saved five-check repo-aware profile had passed before this small addition; GitHub CI is the definitive integration proof.
- Commit `e7436f899290f83dda9dbe053e9d0bbb0de1b16a` pushed. GitHub Actions push run `42736426249` and PR run `42736434207` both passed all three jobs. PostgreSQL integration job ran 29/29 tests, 0 failures, 0 skips, including the real TLS/role integration and connection-timeout configuration regression.
- PR #2 remains OPEN, Draft, mergeable. No production DB credentials, CMS live connection, deployment, or publishing side effect occurred.

- After the 10-second connection-timeout change, the saved five-check repo-aware verification profile was rerun and passed all 5 checks. `git diff --check` also passes. The code commit remains `e7436f8`; the production-readiness report now includes the bounded-connection configuration and its test evidence.

## WebSocket heartbeat and liveness hardening (2026-11-10 UTC)

- The pinned `@binance/cms@1.0.3` SDK contract was inspected in the installed package and locked by a regression test: its `WebsocketStreamsConnection` exposes `isConnected()`, `pingServer()`, and `pong` event listeners. Its package README documents automatic connection renewal before the 24-hour API key expiration and automatic stream resubscription after reconnect/renewal. This verifies the SDK capability, not a live Binance session.
- Worker now sends an active ping every 30 seconds and requires a pong within 10 seconds. A missing pong records a heartbeat-specific `DEGRADED` reason; a later pong clears only that reason. Transport, heartbeat, message-processing and queue failures are tracked independently, preventing a successful pong from erasing an unrelated database failure. The worker refreshes state-row `updated_at` on pong/state transitions for external freshness monitoring.
- Heartbeat interval/timeout values are validated as positive Node timer-safe integers before pool creation. Timer handles are unreferenced and both the recurring interval and pending pong timeout are cancelled during graceful shutdown.
- Added regression coverage for successful ping/pong, pong timeout, independent database degradation preservation, shutdown timer cleanup, invalid timer configuration, and the pinned SDK heartbeat API contract. README documents the 30s/10s policy and suggested external alert thresholds; those thresholds are operational suggestions, not Binance feed SLAs.
- Local worker suite: 34 passed, 0 failed, 1 PostgreSQL integration test skipped (no local server). Saved five-check repo-aware verification profile: 5/5 passed. `git diff --check` passed.
- Code commit `a4fc2f9780238e5f87b90b93e850e7f01eb05fc8` pushed. GitHub Actions push run `42780876489` and PR run `42780883836` passed all 3 jobs. PostgreSQL security integration job ran the complete suite with 35/35 passed, 0 failed, 0 skipped; the isolated migration/role/TLS integration also passed.
- PR #2 remains OPEN, Draft, mergeable. Live Binance ping/pong, provider TLS, production DB, deployment, and external alert delivery remain NOT TESTED. No live CMS credentials, production DB, deployment, publisher workflow changes, or real Square post were used.
