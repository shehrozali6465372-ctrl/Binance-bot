# Module 11–21 Implementation Gap Register

This register tracks whether the locked architecture contracts are reachable and implemented in the repository at the continuation branch baseline. It is not a replacement architecture and does not declare modules complete.

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
