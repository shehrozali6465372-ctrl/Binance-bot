# Module 11–21 Implementation Gap Register

This register tracks whether the locked architecture contracts are reachable and implemented in the repository at the continuation branch baseline. It is not a replacement architecture and does not declare modules complete.

## 5.11 Module 11 — Evidence Verification Engine

### Latest checkpoint — 2026-11-14 (PARTIAL; supersedes older verification counts below)

- Focused verification: **47 passed, 0 failed**. Full repository suite: **398 passed, 0 failed, 12 skipped**. The 12 skips are PostgreSQL integration tests because `TEST_POSTGRES_DSN` is not configured.
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
| 12 Event lifecycle | PARTIAL | layer1/event_lifecycle.py; explicit state machine, disputed state, append-only transitions, multi-asset and restart tests | Automated material-change classification and source-specific freshness policy |
| 13 Deep research | PARTIAL | layer1/research_package.py; versioned package, cutoff, evidence/source coverage, facts/inferences/disputed/unknown, idempotent persistence | Full bounded source acquisition/corroboration and complete sentence-level claim mapping |
| 14 Opportunity evaluation | PARTIAL / FAIL-CLOSED | layer1/opportunity.py; hard gates, deterministic optional weighted scoring, persisted decisions | Approved weights and evidence-derived factor providers absent; runtime currently supplies no policy/factors and correctly returns DEFER |
| 15 AI decision / DeepSeek | PARTIAL | layer1/deepseek_client.py; direct API client; official deepseek-flash model contract verified; mocked client tests | No authenticated live API test; GitHub Actions still maps Gemini secrets while runtime reads DeepSeek variables |
| 16 Editorial strategy | PARTIAL | layer1/editorial_strategy.py; event/on-chain/market angle, prohibited claims, uncertainty and duplicate angle versioning | No live AI/editorial quality evaluation; no complete semantic duplicate-angle detection |
| 17 Content generation | PARTIAL | layer1/content_generation.py; append-only draft versions, research/brief/claim provenance and validation ledgers | No live DeepSeek generation; exact generated content still needs stronger semantic verification |
| 18 Content verification | PARTIAL | layer1/content_verification.py; canonical asset/ticker, claim states, numeric guard, prohibited trade/guarantee phrases | No full semantic factual/causal/repetition validator; numeric allowlist is not semantic proof |
| 19 Image generation | PARTIAL | image_engine.py; direct Cloudflare FLUX.2 Klein 4B client, multipart and image-byte checks, deterministic composition and provenance sidecar | No real authenticated Workers AI inference, account access/cost validation or provider output evidence |
| 20 Visual quality | PARTIAL | layer1/visual_quality.py; exact draft/image hash pair, PNG/dimensions/size/identity/metadata/overlay checks | No independent OCR/visual audit for contrast, clipping, readability or semantic mismatch |
| 21 Publishing/persistence | PARTIAL | layer1/publication_authorization.py, main.py, scripts/reconcile_publications.py; immutable auth, daily quota, attempt binding, persisted validation and manual unknown-outcome reconciliation | PostgreSQL integration skipped; no production recovery drill/provider request; media upload currently precedes final publication authorization |

### Verification (latest available)
- Full suite completed before the final lifecycle edge-case test: 474 passed, 0 failed, 12 skipped.
- New lifecycle/disputed-resolution regression plus the other focused integration gates: 56 passed, 0 failed.
- The full suite was rerun after the latest changes; its result is being collected from /tmp/full-suite-2026-11-14-latest.log and must supersede earlier counts only after confirmed.
- Twelve skipped tests are PostgreSQL integration tests requiring TEST_POSTGRES_DSN.
- Python compileall and git diff --check passed in the latest focused batch.
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
