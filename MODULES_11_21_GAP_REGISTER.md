# Module 11–21 Implementation Gap Register

This register tracks whether the locked architecture contracts are reachable and implemented in the repository at the continuation branch baseline. It is not a replacement architecture and does not declare modules complete.

## 5.11 Module 11 — Evidence Verification Engine

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
