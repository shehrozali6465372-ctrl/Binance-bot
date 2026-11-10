# Binance Square Write-to-Earn Agent — Project Context

Last updated: 2026-11-11 (UTC)
Repository: https://github.com/shehrozali6465372-ctrl/Binance-bot
Current working branch: `fix/cms-websocket-startup-error-race`
Current PR: https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/6
PR base: `integration/binance-cms-worker-main`
PR head at context capture: `4e8f4de76d5d6586588e605f858648466a25c88d`
PR state: OPEN, DRAFT, NOT MERGED.

> This file records the project vision, verified state, operational decisions, known blockers, and handoff rules. Update it when project state changes. Do not treat a planned action as completed until its result is verified.

## 1. Project vision and scope

Build and productionize the existing Binance Square Write-to-Earn Agent without restarting or replacing its established workflow.

The project has two distinct responsibilities:

1. **Binance Square content/publishing workflow** — preserve the existing agent and publisher that create and publish content to Binance Square using the supported, configured integration.
2. **Binance CMS announcement ingestion worker** — a separate read-only service that connects to Binance's CMS Announcement WebSocket, receives official announcement events, normalizes them, and persists them to PostgreSQL/Neon for downstream processing.

The CMS worker is not a trading bot. It must not place trades, withdraw funds, or publish Binance Square posts. Do not conflate the CMS worker's credentials or permissions with Square publishing credentials.

The broader intended flow is:
- Receive official Binance announcements through CMS WebSocket.
- Normalize and persist announcement data in PostgreSQL.
- Let the existing agent process/analyze relevant announcements and generate content.
- Use the existing supported Binance Square publishing workflow where appropriate.

Do not invent or assume that every stage is already fully integrated or production-ready. Verify each boundary independently.

## 2. Non-negotiable project rules

- Preserve existing working Binance Square publisher and earning workflow.
- Do not restart the project or repeat already completed work.
- Verify repository, branch, commit, CI, and deployed/live state before continuing.
- Do not merge PRs blindly. Review official Binance documentation and actual code contracts first.
- **Never publish a real Binance Square post during tests, diagnostics, CI, or smoke tests.**
- Automated tests must not invoke a real publishing endpoint or create a real post.
- Use real services and evidence for integration verification; do not present mocks as live verification.
- Mocks are acceptable for isolated unit/regression tests, but clearly label them.
- Do not expose API keys, secrets, signed URLs, signatures, database credentials, or tokens in logs, context files, PRs, or support messages.
- Do not bypass Binance regional/legal restrictions using VPNs, proxies, or misleading IP geolocation.
- Keep CMS ingestion read-only and isolated from the Square publisher.
- Keep architecture decisions and project context documented and updated.
- No production approval until all applicable acceptance gates pass.

## 3. Repository and current GitHub state

- Repository: https://github.com/shehrozali6465372-ctrl/Binance-bot
- Current branch: `fix/cms-websocket-startup-error-race`
- PR #6: https://github.com/shehrozali6465372-ctrl/Binance-bot/pull/6
- PR title: Fix early Binance CMS WebSocket error handling race
- PR base branch: `integration/binance-cms-worker-main`
- PR status at last verification: open, draft, not merged.
- Branch HEAD at last verification: `4e8f4de76d5d6586588e605f858648466a25c88d`
- Latest known commit message: Add read-only runner egress IP diagnostic.
- Do not merge or deploy this draft PR without explicit review and passing acceptance gates.

The canonical `PROJECT_CONTEXT.md` was not present at the inspected PR branch root when this context was created. This file is being added as the project handoff record. Verify its location and branch after commit.

## 4. CMS announcement worker — architecture and verified implementation

Worker directory: `announcement-worker/`

Technology and dependencies:
- Node.js 22.12.0 (workflow pins this version).
- Official Binance CMS SDK: `@binance/cms@1.0.3`.
- Pinned transitive/common SDK used by the implementation: `@binance/common@2.5.3`.
- PostgreSQL client: `pg@8.16.3`.
- PostgreSQL/Neon is used for durable announcement and worker-state persistence.

CMS connection:
- Production endpoint observed in code/PR documentation: `wss://api.binance.com/sapi/wss`.
- Signed CMS WebSocket connection uses the configured Binance API key/secret through the official SDK.
- The current implementation uses `CmsWebsocketStreams` and the signed `WebsocketStreamsBase` transport.
- The worker attaches transport `open`, `error`, and `close` handlers before starting the handshake. This addresses the early unhandled EventEmitter error race.
- The CMS message stream listener is registered before the first awaited post-connect state write.
- The pinned SDK owns its WebSocket keepalive: it sends an empty PING every 30 seconds, handles server PING/PONG, reconnects after close, and refreshes signed stream URLs. The worker does not implement a competing custom heartbeat.
- Transport, message-processing, and database degradation states are tracked separately.
- Error diagnostics redact WebSocket URLs to avoid leaking signed URLs/signatures.
- The CMS stream does not document historical replay. A successful reconnect does not prove missed announcements were recovered.

Persistence:
- Worker uses a PostgreSQL pool and a least-privilege worker database role.
- The Neon connection helper enforces a Neon hostname, the `binance_announcement_worker` role, and strict TLS (`sslmode=verify-full`).
- A helper in `.github/scripts/prepare-neon-database-url.mjs` upgrades an accepted Neon URL to strict TLS after validation.
- Database migrations/schema and operational state should be checked against the actual repository before making further schema assumptions.

## 5. GitHub Actions diagnostic and latest observed failure

Workflow:
- `.github/workflows/binance-cms-manual-smoke.yml`
- URL: https://github.com/shehrozali6465372-ctrl/Binance-bot/actions/workflows/binance-cms-manual-smoke.yml
- Trigger: manual `workflow_dispatch`.
- Runner: GitHub-hosted `ubuntu-latest`.
- The workflow is bounded and read-only; it does not contain or invoke the Square publishing workflow.

Latest verified diagnostic run:
- Run ID: `42917788661`
- URL: https://github.com/shehrozali6465372-ctrl/Binance-bot/actions/runs/42917788661
- Commit: `4e8f4de76d5d6586588e605f858648466a25c88d`
- Result: completed with failure.
- The outbound-IP diagnostic, Node setup, dependency installation, Neon TLS URL validation, secret-presence validation, and strict Neon TLS setup completed.
- The read-only CMS diagnostic failed at WebSocket handshake.
- The workflow's four-minute bounded listener did not publish a Square post.

Actual egress IP observed in that specific run:
- IPv4: `13.89.127.3`
- IP geolocation response: Des Moines, Iowa, United States (US).
- Runner context: GitHub-hosted Actions runner (central US region).
- This is the observed IP for that run only. GitHub-hosted runner egress IPs can change; do not document it as a permanent runner IP.

Observed Binance connection result:
- WebSocket upgrade returned HTTP `451`.
- Connection closed with code `1006`.
- This is consistent with the regional restriction explanation provided by Binance support for US-based IPs.
- Do not claim that credentials are invalid or that Binance has an outage based on this result.

A separate cleanup/lifecycle error was also observed after startup failure:
- `Cannot use a pool after calling end on the pool`.
- This appears to be a shutdown/database-pool lifecycle race following connection startup failure.
- Root cause has not yet been established and it has not been verified fixed. Investigate independently with regression tests before changing code.

## 6. Binance support case — regional restriction findings (2026-11-11)

Support case shown in screenshots:
- Case ID: `#173902977`
- Support representative: CS Ozan D.

Support statements captured by the user:
1. Binance compliance controls restrict API access based on source IP when the connection originates from a restricted location.
2. The representative listed restricted locations including Canada, Netherlands, United States, Cuba, Democratic People's Republic of Korea (DPRK), Iran, Syria, Crimea, non-government-controlled areas of Ukraine, and other locations Binance Operators may designate.
3. The representative stated: **“Outside of this list is ok.”**
4. The representative also stated: **“Outside of the restricted location is good for server.”**
5. In response to repeated clarification about Pakistan, the representative repeated that locations outside the restriction list are acceptable.

Interpretation and limits:
- The US-based GitHub Actions IP used in the observed test is in a restricted location according to the support response. HTTP 451 is therefore expected for that runner IP.
- Pakistan was not included in the restricted locations listed in the support chat. The representative's general statement indicates that a server outside restricted locations is acceptable under the stated IP-location policy.
- This is a support-chat policy clarification, not a successful connection test and not a formal guarantee that every Pakistan-hosted/cloud IP will be accepted.
- Actual IP geolocation, provider/ASN classification, account/product eligibility, and the CMS handshake must still be verified.
- Support did not provide a separate detailed written confirmation of all Binance Square publishing API requirements. Do not infer those requirements from the CMS/IP discussion.
- The support conversation was closed after the user thanked the representative. Do not reopen or repeat questions already answered unless new evidence creates a genuinely new issue.

## 7. Hosting decision

Decision:
- Keep GitHub as the source-control and CI/CD system.
- Do not rely on standard GitHub-hosted `ubuntu-latest` for the production CMS WebSocket connection while its egress is US-based/restricted.
- Run the long-lived CMS worker on a server whose actual outbound public IP is outside Binance's restricted locations, after verifying the IP and provider region.
- A Pakistan-based server is a candidate because Pakistan was not named in the support-provided restricted list, but the actual egress IP must be checked.
- Another non-restricted region may be used if its IP is verifiably outside the restricted list and otherwise compliant.
- Do not select a provider based only on its advertised data-center country. Verify the server's actual outbound IP from the deployed runtime.
- Do not use VPN/proxy routing to evade regional restrictions.

Possible deployment patterns to evaluate:
- A compliant-region VM with a GitHub self-hosted runner, if appropriate for CI tasks; or
- GitHub Actions for CI/CD plus a separate long-running worker service in a compliant region.
Choose the least complex production architecture that supports stable outbound IP, process supervision, logs, restart policy, secrets management, monitoring, and secure Neon connectivity.
Do not move the existing Square publisher unless the architecture and deployment plan require it and the change is explicitly reviewed.

## 8. Secrets and configuration — names only, never values

Known CMS worker / workflow secret names:
- `BINANCE_API_KEY`
- `BINANCE_API_SECRET`
- `BINANCE_ANNOUNCEMENT_DATABASE_URL` (GitHub Actions secret used to prepare the worker DB URL)
- `DATABASE_URL` (runtime variable populated from the validated URL)
- Optional `BINANCE_CMS_WS_URL` override (default should remain the official production URL unless an approved reason requires override)
- `BINANCE_CMS_DIAGNOSTIC_MODE` (diagnostic mode used in the bounded workflow)

Rules:
- Never copy secret values into this file.
- Never print secret values in logs.
- CMS worker credentials must not be assumed to be the same as the Square publisher credentials without checking the actual environment/configuration.
- Confirm least-privilege API permissions against official Binance documentation and account settings before production.
- Do not expose GitHub secret values; verify only presence/configuration through safe checks.

## 9. Validation history and current evidence

PR #6 description records:
- Run `42889710401` at commit `a61fac1`: mocked tests and PostgreSQL TLS/least-privilege integration passed.
- Run `42889534879` exposed a signed-URL error-log redaction test failure; redaction was added and the later run passed.
- The PR includes regression tests for startup error-listener ordering and sanitized diagnostics.
- The PR also includes Neon TLS URL helper tests.
- The later manual smoke run `42917788661` failed on the restricted US egress IP with HTTP 451, despite the preflight checks passing.

Do not treat prior unit/integration CI success as proof of live Binance CMS connectivity. Do not treat the failed US-region smoke test as a code regression until retested from a compliant region.

## 10. Remaining work — ordered acceptance gates

### Gate A — hosting and source IP
1. Evaluate hosting providers/regions and select a compliant region.
2. Provision a server/worker runtime with stable outbound IP and required process supervision.
3. From the actual runtime, record the outbound public IP and verify its geolocation. Keep the result and timestamp in deployment notes.
4. Confirm the IP is outside Binance's current restricted locations. Do not assume a provider's advertised region is sufficient.

### Gate B — live CMS read-only integration
5. Deploy/configure the CMS worker with secrets from the secure environment only.
6. Run a bounded read-only CMS WebSocket connection test from the selected server.
7. Capture sanitized status, connection lifecycle, and safe response diagnostics. Never log signed URLs, signatures, API keys, or secrets.
8. Verify that an actual announcement event is received and persisted in PostgreSQL/Neon. A successful socket open alone is not proof of ingestion.
9. Verify reconnect behavior and explicitly document that historical replay is not guaranteed by the CMS stream contract.
10. Verify worker-state monitoring and alert behavior.

### Gate C — cleanup and resilience
11. Reproduce and fix the `Cannot use a pool after calling end on the pool` shutdown race, if still present.
12. Add regression tests for failure during handshake, queued database writes, graceful shutdown, pool close ordering, and repeated shutdown calls.
13. Verify no unhandled EventEmitter errors, unhandled promise rejections, duplicate writes, or leaked timers/sockets.

### Gate D — Square publishing and full agent
14. Review the existing Binance Square publisher independently against current official Binance Square/API documentation.
15. Verify account eligibility, API access, permissions, content rules, quotas/rate limits, and any required IP restrictions from authoritative documentation/account configuration.
16. Keep publishing tests dry-run/sandbox/mock only where supported. Never create a real Square post during tests.
17. Verify the full handoff from announcement processing to content generation to the existing publishing gateway without bypassing that gateway.
18. Verify idempotency, duplicate prevention, retry behavior, uncertain-publication reconciliation, quota accounting, concurrency control, and audit logs.
19. Complete security review, dependency audit, operational monitoring, rollback plan, and production runbook.
20. Only then request explicit production-release approval.

## 11. Related project history and constraints

- The project has an established Binance Square publisher and write-to-earn workflow. Preserve it.
- The user has emphasized layered implementation and completing Layer 1 before moving ahead.
- The user previously referenced branch `feature/binance-cms-announcement-worker`, PR #2, base `layer-1/completion-hardening`, and commit `1cbf4a4065a253cadb0acab08b835829fc3e47b4` as earlier project history. Treat these as historical references only; current active PR/branch is listed in Section 3.
- Current active CMS implementation work is PR #6. Do not assume historical branches are still current.
- Existing publishing safety hardening includes a Single Publishing Gateway, quota/concurrency protections, uncertain-publication handling, and account-aware scheduling from prior project phases. Verify the actual current code and tests before modifying or declaring these complete.
- Earlier user-reported phase notes: Phase 9 account-aware scheduling was closed; Phase 10 release readiness was blocked pending security review. These are historical project notes and must be revalidated against current repository/CI before claiming current release status.

## 12. Operating protocol for future work

At the start of each continuation:
1. Read this file.
2. Verify current branch, HEAD, PR state, latest CI/workflow run, and working tree/repo state.
3. Identify what is already complete and what is still blocked.
4. Do not repeat completed checks unless new code/state invalidates their evidence.
5. Make one bounded change at a time; add/update tests for behavior changes.
6. Run targeted tests, then relevant full tests/CI.
7. Inspect diffs and logs for secret leakage and unintended publisher invocation.
8. Update this context file with commit/run IDs and verified outcomes.
9. Report clearly what was implemented, what passed, what failed, and what remains.
10. Never claim production-ready until all applicable acceptance gates are verified.

## 13. Current status summary

- Existing Binance Square publisher: preserve; do not alter without a scoped reason.
- CMS worker code: implemented in current draft PR; unit/regression and prior database/TLS checks have passed as recorded in PR history.
- GitHub-hosted runner live CMS test: blocked by US-based runner egress IP; HTTP 451 observed.
- Binance support regional guidance: outside restricted locations is acceptable; US is restricted; Pakistan was not on the list supplied in the support chat.
- Pakistan/non-restricted-region actual server: not provisioned or verified in this record.
- Live CMS ingestion + PostgreSQL persistence from compliant-region host: pending.
- Pool shutdown-after-failure race: observed, root cause/fix pending.
- Full Binance Square API eligibility review: pending independent verification.
- PR #6: open draft, not merged.
- Real Binance Square publishing in tests: prohibited.
