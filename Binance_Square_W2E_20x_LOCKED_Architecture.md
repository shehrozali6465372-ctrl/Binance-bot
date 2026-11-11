# Binance Square W2E Agent — 20x Target Architecture

> **Document class:** Locked architecture specification (design baseline)  
> **Project:** Binance Square Write-to-Earn autonomous editorial agent  
> **Repository:** https://github.com/shehrozali6465372-ctrl/Binance-bot  
> **Architecture version:** 1.0  
> **Architecture date:** 2026-11-09  
> **Status:** 🔒 **LOCKED — design baseline; implementation not yet verified**  
> **Canonical project context:** `Binance_Square_W2E_Agent_Master_Context.md`  
> **Important:** This is a target design contract. It does not claim that all 21 modules already exist or work in the repository.

---

# 0. Lock declaration and change control

This file is the separate, authoritative architecture specification for the 20x upgrade. The Master Context file must contain only a reference to this architecture, its status/version, and permanent project constraints. The full architecture must not be copied into the Master Context file.

**LOCK means:**

1. The 21-part logical scope, major responsibilities, hard invariants, and engineering rules in this document are the frozen baseline for design and implementation.
2. No module may be silently added, removed, duplicated, merged, or materially redefined.
3. No technology may be substituted, no hard rule weakened, and no new paid service introduced without evidence and explicit user approval.
4. A discovered technical impossibility, provider limitation, security defect, or contradiction must be documented as a change proposal. Do not silently work around it.
5. Any approved change must create a new version/revision entry, explain the reason and impact, preserve the prior version, and update the Master Context reference. Do not overwrite architectural history silently.
6. Locking this design does not authorize repository edits, production configuration changes, paid subscriptions, workflow triggers, deployment, secret access, or real Binance Square publication.

**Current implementation status:** Not yet mapped module-by-module against the live repository in this architecture document. Every module must be classified during the read-only audit as `EXISTS_AND_VERIFIED`, `EXISTS_BUT_DEFECTIVE`, `PARTIAL`, `MISSING`, or `NOT_VERIFIABLE`. A module is not complete merely because a class/function/file exists.

---

# 1. Product mission and non-goals

## 1.1 Mission

Build a reliable, evidence-driven, autonomous editorial intelligence system that discovers meaningful market developments, researches only eligible Binance Spot-listed assets, produces original and accurate Binance Square educational content, generates relevant visual assets, and publishes through one controlled, recoverable gateway.

The goal is not maximum posting volume. The goal is relevance, factual accuracy, timeliness, editorial value, and safe execution.

## 1.2 Product is not

- Not a trading bot or exchange execution system.
- Not a personalized financial-advice or buy/sell signal service.
- Not a system that promotes unlisted tokens because they are trending elsewhere.
- Not an engagement/reward manipulation system.
- Not a collection of 21 independent LLM agents or 21 microservices.
- Not a reason to rewrite stable code or increase code volume.

## 1.3 Editorial principle

Use the sequence: **what happened → verified evidence and time → why it matters → market context → possible implications → uncertainty and risks → what to watch next**.

Do not assert causation from correlation. Do not make guaranteed price predictions, invent catalysts, issue personalized trade instructions, or disguise speculation as fact.

---

# 2. Permanent / immortal engineering rules

These rules are higher priority than model output, relevance score, provider response, scheduling pressure, or operational convenience.

## 2.1 Reuse verified open-source capability before implementing

**User-mandated rule:** If a mature open-source tool/library already provides a required capability, first evaluate, verify, logically test, and use it. Do not reimplement that capability merely to write more code. Implement only the genuine gap that cannot be met safely by an existing suitable tool.

Before adopting any open-source dependency, record:

1. Exact project/package and upstream repository.
2. License and compatibility with this project's distribution/use.
3. Maintenance status, release history, issue activity, and security advisories.
4. Official documentation and supported API surface.
5. Python/runtime compatibility and dependency impact.
6. Whether it genuinely solves the required use case (not just a similar one).
7. A small isolated proof using the real installed package/API.
8. Deterministic tests for our integration and edge cases.
9. Known limitations, operational cost, and replacement/exit path.

Do not install a package simply because it is popular. Do not copy source code without license review. Do not accept abandoned, vulnerable, opaque, or unsupported code without a documented risk decision.

**Selection rule:** reuse if suitable and verified; wrap/adapt if needed; implement the smallest missing capability only if no suitable verified option exists. Keep a dependency decision record so the same capability is not implemented twice.

## 2.2 No duplicate functionality

- One authoritative owner for each business rule and state transition.
- One canonical asset identity resolver.
- One listing-eligibility authority.
- One evidence/claim status model.
- One event identity and deduplication policy.
- One publication authorization path and one publishing gateway.
- One authoritative publication ledger.
- No parallel implementations of the same retry, freshness, scoring, upload, or validation rule.
- Existing working code is reused or refactored only when there is a proven defect or clear maintainability/safety gain.

## 2.3 No missing or useless logic

Every new function/module must have a defined responsibility, contract, owner, caller, state effect, failure behavior, and test. If it has no necessary role, it must not be added. Remove neither existing behavior nor safeguards without impact analysis and approval.

## 2.4 No fake production behavior

- No mock provider, fake API response, fabricated event, synthetic market metric, dummy success, placeholder implementation, or simulated provider result in the production path.
- Provider failures must be reported as failures/degraded/unavailable, not converted into invented data.
- Static fallback universes, synthetic histories, sample prices, fabricated trend strengths, or fake metrics must never qualify a real production candidate or be presented as live evidence.
- A successful HTTP status alone is not proof that returned data is semantically correct.
- No component may be called complete without code inspection plus appropriate verification evidence.

**Testing distinction:** deterministic fixtures/test doubles may be used only to test pure logic in isolated unit tests where real external calls would make the test nondeterministic. They must never be used as proof of provider integration, end-to-end production capability, or live data correctness. Real integration checks must call the actual documented provider interface using safe/read-only operations or an explicitly provided test facility. No fake provider is permitted in production.

## 2.5 Hard Binance Spot eligibility invariant

Only assets verified as officially listed and currently eligible for Binance Spot trading may enter the publish-candidate path. Binance Alpha, DEX availability, CoinGecko listing, another exchange listing, or a blockchain registry entry does not qualify.

The gate must validate exact asset identity, exact Binance trading symbol/pair, current symbol status, applicable Spot permission, and the relevant base/quote relationship. Ambiguous ticker matches, delisted/suspended/inactive/non-Spot assets, stale metadata, or inability to verify means **reject/defer; fail closed**. Recheck eligibility near publication authorization.

The requirement applies to all discovery sources and all AI decisions. No score, LLM, source, or downstream module can override it.

## 2.6 On-chain scope restriction

On-chain analysis is permitted only for assets that pass the Binance Spot eligibility invariant and whose exact asset-to-chain/contract identity can be proven. Native assets must not be incorrectly rejected merely because they do not have a contract address. Wrapped, bridged, staked, derivative, and same-ticker assets must be distinguished.

Unmapped/unsupported/stale on-chain data is `UNAVAILABLE` or `UNVERIFIED`; it is never inferred or fabricated. On-chain signals are supporting evidence, not standalone publish authorization.

## 2.7 AI authority boundary

Direct DeepSeek API supports language/research/editorial tasks. AI cannot:

- approve an unlisted asset;
- certify evidence without source verification;
- invent missing facts or numerical values;
- change daily limits or cooldown policy;
- bypass content validation;
- bypass publication authorization/idempotency;
- mark an unknown publication as failed or confirmed without evidence;
- change credentials, database state, or deployment policy.

Hard invariants are deterministic code and persistent-state responsibilities.

## 2.8 Image truth and consistency

Image generation is a first-class required capability, not decoration. Generation, composition, validation, media upload, and publication are separate operations with separate statuses. The image must match the approved post and exact eligible asset. Charts must use genuine timestamped data. Never present synthetic price history as real. If suitable data is missing, omit the chart or clearly label a non-data illustration. Generation success does not imply image correctness or upload success.

## 2.9 Safe publishing and user constraints

- Testing must never publish a real Binance Square post.
- No personal-browser automation is part of this architecture.
- Only one controlled publishing gateway may invoke the real publishing interface.
- No direct publisher bypass from schedulers, AI tools, tests, image code, or recovery jobs.
- Uncertain provider outcome must be reconciled before another publication attempt.
- Performance-metric learning remains frozen until an official, authorized, machine-readable Binance creator analytics source is verified. Internal engineering telemetry is allowed but is not audience-performance data.

## 2.10 Change discipline

Baseline commit, relevant files, dependencies, existing tests, deployment configuration, and rollback point must be recorded before implementation. Small changes, tests, review, and explicit production approval are required. No blind rewrite.

---

# 3. System architecture and module count

The architecture contains **21 logical functional modules** in four layers. They are responsibility boundaries, not a requirement for 21 separate files, processes, agents, containers, or microservices. The preferred starting shape is a modular monolith that fits the existing Python system, with clear interfaces and state ownership. A service split is allowed only when measured scaling, isolation, or reliability requirements justify it.

## Layer 1 — Foundation & Market Intelligence (Modules 1–7)

1. Configuration & Orchestration Engine
2. Market Data Intelligence Engine
3. Binance Listing Eligibility Engine
4. Announcement Intelligence Engine
5. Trending & Narrative Intelligence Engine
6. Candidate Discovery & Filtering Engine
7. Relevance & Scoring Engine

## Layer 2 — Research & Intelligence (Modules 8–14)

8. Market Analysis Engine
9. Blockchain & On-chain Intelligence Engine
10. Event Intelligence Graph
11. Evidence Verification Engine
12. Event Lifecycle Intelligence
13. Deep Research Engine
14. Opportunity Evaluation Engine

## Layer 3 — AI & Editorial Intelligence (Modules 15–20)

15. AI Decision Engine — direct official DeepSeek API
16. Editorial Strategy Engine
17. Content Generation Engine
18. Content Verification & Safety Engine
19. Image Generation Engine — Cloudflare Workers AI
20. Visual Quality & Consistency Engine

## Layer 4 — Publishing & Autonomous Operations (Module 21)

21. Publishing, Persistence & Autonomous Operations Engine, with distinct internal responsibilities for authorization, publishing, reconciliation, persistent records, monitoring, recovery, and evaluation. Those responsibilities must not become duplicate competing authorities.

---

# 4. Cross-module data contracts

The exact Python types/table layout are to be fitted to the current code and database during audit. These are mandatory semantic contracts, not a directive to introduce a particular framework or duplicate existing models.

## 4.1 Canonical Asset Identity

Minimum semantic fields:

- `asset_id`: internal immutable canonical identifier.
- `asset_name`.
- `base_asset` and verified Binance `symbol`/`trading_pair`.
- `quote_asset`.
- `binance_spot_status` and applicable Spot permissions.
- `eligibility_status`: `ELIGIBLE | INELIGIBLE | UNVERIFIED`.
- `verified_at`, source endpoint/reference, and source-data version/hash where feasible.
- Asset type: native, contract token, wrapped, bridged, staked/derivative, or unknown.
- For on-chain mapping: chain/network ID, contract address if applicable, decimals where needed, mapping provenance, and mapping status.

Ticker text is not a canonical identity. All modules must refer to the canonical asset identity rather than independently re-resolving tickers.

## 4.2 Source Evidence

Minimum fields:

- `evidence_id`, `source_name`, source category, source URL/reference.
- Original publisher/source identity where known.
- `published_at`, `updated_at` if provided, `observed_at`, and retrieval time.
- Raw-response/content hash or retained evidence reference under allowed data-retention rules.
- Asset/event associations and extraction method.
- Source trust class, freshness status, and verification status.
- Provider error/limitations, if any.

Do not rewrite source publication time as observation time. Preserve both.

## 4.3 Market Observation

Minimum fields:

- Canonical `asset_id`, provider, endpoint/product, observation timestamp.
- Price, currency, 24h change, 24h volume, market cap, liquidity if supplied, and historical points only when actually received.
- Field-level availability and provenance.
- Freshness/validation status.
- No synthetic historical points or fabricated metrics.

## 4.4 Event

Minimum fields:

- Stable internal `event_id` and event type.
- Canonical asset IDs (zero or more, but identity must be established).
- Primary source evidence and corroborating evidence IDs.
- First published time, first observed time, last materially updated time.
- Event lifecycle state and state history.
- Materiality, confidence and their reason breakdowns.
- Duplicate/canonical event relationship.

## 4.5 Candidate

Minimum fields:

- `candidate_id`, canonical asset ID, linked event IDs, signal/evidence IDs.
- Binance eligibility snapshot and timestamp.
- Discovery reasons, data completeness, freshness, duplicate status.
- Relevance score breakdown and rank.
- Candidate state and rejection/defer reasons.

## 4.6 Research Package

Minimum fields:

- Candidate/event/asset references.
- Facts, each linked to evidence IDs.
- Interpretations/hypotheses, explicitly labelled as such.
- Market context and on-chain observations where available.
- Contradictions, unknowns, limitations and stale/missing fields.
- Research creation time and input-data version/fingerprint.
- Editorial eligibility decision and reason.

## 4.7 Content Draft

Minimum fields:

- Draft ID, candidate/event/asset references, version.
- Editorial brief, text, language, creation time, model/provider/model ID.
- Research/evidence references.
- Claim-validation results and safety results.
- Duplicate/originality result.
- Draft status and revision/rejection reasons.

## 4.8 Visual Asset

Minimum fields:

- Asset ID, generation provider, exact model ID, generation request metadata (excluding secrets), actual file hash, format, dimensions, bytes/path/reference.
- Post/draft/canonical asset association.
- Real-data sources for each chart/number if any.
- Composition/validation results.
- Upload state and remote media reference, separate from generation state.

## 4.9 Publication Intent and Record

Minimum fields:

- Immutable internal publication intent ID and idempotency key.
- Draft and visual asset hashes/versions.
- Canonical asset ID and last Binance eligibility verification.
- Daily quota reservation and dedup/repetition decision.
- Intent state, timestamps and transition history.
- Provider request/response evidence, with secrets removed.
- Confirmed external Binance content/post ID and URL when known.
- If outcome cannot be established, explicit `UNKNOWN` state and reconciliation history.

A publication record must never be linked to a coin only by ticker name.

---

# 5. Detailed module specifications

Each module below defines purpose, inputs, required logic, outputs, fail-closed behavior and acceptance criteria. Reuse suitable existing repository code and verified open-source libraries first; these contracts do not require duplicate implementations.

## 5.1 Module 1 — Configuration & Orchestration Engine

**Purpose:** Start and coordinate one controlled agent execution with validated settings and unique run identity.

**Inputs:** Environment/configuration, secret references, schedule trigger, runtime metadata, feature flags, previous persisted run/lock state.

**Required logic:**
1. Load configuration once through one authoritative configuration path.
2. Validate required versus optional settings, types, ranges, URLs, timeouts, limits and provider/model identifiers.
3. Never log secret values. Confirm only presence/validity metadata.
4. Create a unique `run_id`; acquire a concurrency/lease guard so overlapping runs cannot race on quota or publication state.
5. Initialize only required providers and services; record capability health.
6. Build immutable run context including configuration version/hash and start time.
7. Pass execution through explicit layer boundaries; do not let schedulers call publisher internals.
8. Persist run outcome and release lease safely even on exceptions.

**Outputs:** Validated run context, provider capability states, run status and logs.

**Failure rules:** Missing mandatory configuration, invalid limits, failed database connection when persistence is mandatory, or inability to establish safe execution exclusivity blocks publishing. Optional provider failures degrade only their dependent capabilities.

**Acceptance:** Invalid config fails before candidate processing; secrets never appear in logs; overlapping runs do not double-reserve quota/publish; run state is traceable after process restart; cleanup works on exceptions.

## 5.2 Module 2 — Market Data Intelligence Engine

**Purpose:** Acquire genuine, timestamped market observations from approved providers.

**Approved initial sources:** Existing Binance official market-data interfaces and existing CoinGecko integration, subject to endpoint/schema/terms/quota audit. No new provider is automatically approved.

**Inputs:** Eligible Binance asset universe, provider config, request budgets, cache metadata.

**Required logic:**
1. Fetch only documented/approved endpoint data; record provider and endpoint identity.
2. Normalize symbols only through the canonical asset mapping; do not merge assets by ticker alone.
3. Validate schema, numeric values, currency, timestamp, price positivity where applicable, and impossible/inconsistent values.
4. Distinguish provider publication/update time from observation time.
5. Apply source-specific freshness thresholds based on field and use case; one global age limit is not appropriate for every data type.
6. Cache only with explicit TTL and provenance; cache must retain original data timestamp and never silently refresh its age.
7. Track rate limits, 429s, 5xx, timeouts and provider data gaps.
8. If multiple providers disagree, retain both observations and mark discrepancy; do not average conflicting prices blindly.
9. Historical series must contain actual provider observations. No synthetic history fallback in production.

**Outputs:** Market observations with per-field availability, provenance, freshness and validation status.

**Failure rules:** No valid current observation means dependent market analysis is `UNAVAILABLE`; stale data cannot be treated as current. One provider's outage must not cause a fabricated fallback.

**Acceptance:** Real read-only provider query passes; timestamps survive cache; malformed/stale data rejected; source discrepancy visible; no production path uses synthetic prices or history; rate-limit behavior is bounded.

## 5.3 Module 3 — Binance Listing Eligibility Engine

**Purpose:** Enforce the user's absolute Binance Spot listing rule.

**Authoritative input:** Binance's official documented Spot exchange metadata (e.g., `exchangeInfo`) and validated exact asset/pair identity.

**Required logic:**
1. Build current listing metadata snapshot from the official interface.
2. Validate response completeness, schema, time, status fields, permissions and trading-symbol semantics against current official documentation.
3. Resolve the exact `baseAsset`, `quoteAsset`, pair symbol and Spot permission; do not rely on a ticker substring.
4. Use the canonical asset resolver to handle same-ticker collisions, wrapped/bridged/staked representations and chain mapping.
5. Determine eligibility only from the exact supported rule set: active/trading symbol and applicable Spot permission, with quote/market requirements configured explicitly.
6. Mark all non-listed, delisted, suspended, inactive, non-Spot-only, ambiguous, stale or unverifiable assets `INELIGIBLE`/`UNVERIFIED`.
7. Keep a timestamped eligibility snapshot and reason code.
8. Revalidate near publication authorization; discovery-time verification is not enough.
9. Fail closed when official metadata is unavailable or parsing semantics are uncertain.

**Outputs:** `ELIGIBLE`, `INELIGIBLE`, or `UNVERIFIED` with exact pair, asset identity, source, time and reasons.

**Acceptance:** Official read-only metadata test; spot-only versus Alpha-only case; inactive/suspended pair rejection; same-ticker different-asset rejection; stale metadata fail-closed; recheck before publication. No AI or score can override this module.

## 5.4 Module 4 — Announcement Intelligence Engine

**Purpose:** Discover material events from authentic, attributable announcement sources.

**Inputs:** Official Binance announcement sources and verified official project sources for assets already eligible or awaiting exact identity resolution.

**Required logic:**
1. Use only documented/authorized feeds/interfaces whose use and terms are acceptable; distinguish official pages from unofficial BAPIs or scraped/internal endpoints.
2. Preserve original source URL/ID, author/publisher, published/updated time, observed time and raw evidence reference.
3. Parse event type using explicit taxonomy (listing/delisting, suspension, maintenance, upgrade, governance, integration, exploit/security incident, launch/release, etc.).
4. Extract asset references, then resolve exact identity through Module 3 before creating a publish candidate.
5. Treat ticker extraction as a hint, never final identity proof.
6. Detect updates to prior announcement versus genuinely new event.
7. Deduplicate by stable source article ID where available; otherwise use carefully defined normalized content/source/entity/time fingerprints and retain a reviewable match reason.
8. Distinguish announcement publication from effective/event time.

**Outputs:** Structured announcement event/evidence records.

**Failure rules:** Unofficial/unverifiable source cannot be represented as official; ambiguous symbol is not promoted; stale/withdrawn announcement must be marked accordingly.

**Acceptance:** Original and updated announcements handled correctly; same event across mirrors clustered; symbol collision rejected; source timestamps retained; unauthorized endpoint excluded from production.

## 5.5 Module 5 — Trending & Narrative Intelligence Engine

**Purpose:** Identify genuine demand/narrative signals without confusing popularity with material opportunity.

**Inputs:** Verified provider trending/search data, official announcement topics and validated market observations.

**Required logic:**
1. Record source and timestamp for each trend signal.
2. Normalize narrative/topic names without merging unrelated assets.
3. Cluster duplicate topic mentions, retaining source count and independence (multiple copies of one article are not independent corroboration).
4. Calculate trend freshness and persistence only from actual observations.
5. Separate attention signals from event evidence and market impact.
6. Identify hardcoded/synthetic/demo fallbacks and permanently exclude them from production opportunity evidence.
7. Apply Binance listing eligibility before allowing an asset-linked trend into candidate generation.
8. Avoid interpreting rank order as proof of a catalyst.

**Outputs:** Trend/narrative observations with source, freshness, asset match and confidence limits.

**Failure rules:** Provider unavailable means trend data unavailable; do not generate static narratives that appear live.

**Acceptance:** Live provider data provenance; duplicate syndication not counted as independent sources; stale trend expires; unlisted token excluded; no synthetic fallback becomes a candidate.

## 5.6 Module 6 — Candidate Discovery & Filtering Engine

**Purpose:** Combine validated signals into a canonical research candidate without duplicating the same asset/event opportunity.

**Inputs:** Modules 2–5 outputs and Binance eligibility decisions.

**Required logic:**
1. Create candidate only from actual source-backed signals.
2. Resolve canonical asset identity first.
3. Enforce Module 3 eligibility before a candidate may enter the research/publish-candidate path.
4. Combine market, event, trend and on-chain signals under one canonical candidate/event identity.
5. Deduplicate by asset + event + material update, not ticker alone.
6. Apply objective minimum data/freshness/risk constraints; missing data is not silently treated as a zero or a pass.
7. Preserve rejected candidates with reason codes for audit; never send them downstream as eligible.
8. Maintain cooldown/repetition state in persistent storage with concurrency safety.

**Outputs:** Candidate queue with linked evidence, eligibility snapshot, discovery reasons and explicit state.

**Acceptance:** Same asset/event from multiple providers produces one candidate; new material event may create a new candidate; unlisted asset is rejected; stale/incomplete candidate is deferred/rejected with reason; concurrent runs do not duplicate queue work.

## 5.7 Module 7 — Relevance & Scoring Engine

**Purpose:** Rank candidate research priority by usefulness and evidence quality—not simply price movement or trend rank.

**Potential dimensions:** Event materiality, source credibility, freshness, audience relevance, market context, novelty, evidence completeness, asset liquidity/market relevance and repetition risk.

**Required logic:**
1. Define each score component, scale, direction, weight and missing-value behavior.
2. Scores must be explainable: persist component values and evidence references.
3. Missing evidence must not receive a positive default score.
4. Separate hard rejection conditions from soft ranking; listing eligibility is a hard gate, never a weighted factor.
5. Avoid double-counting correlated data (e.g., multiple copied news articles or the same provider's rank repeated across features).
6. Version score rules/config and retain the version used for each decision.
7. Keep current score behavior until baseline/audit shows how to transition safely; no silent weight replacement.
8. A high score prioritizes research; it never authorizes publishing.

**Outputs:** Ranked candidate and explainable score breakdown.

**Acceptance:** Deterministic same-input/same-version result; no score override of hard gates; missing data behavior tested; score reason traceable; correlated signal double-counting addressed.

---

## 5.8 Module 8 — Market Analysis Engine

**Purpose:** Explain actual market behavior with context and explicitly separate observation from interpretation.

**Inputs:** Validated market observations, historical provider data, broad-market benchmarks and event timeline.

**Required logic:**
1. Confirm price/volume time windows and units.
2. Calculate percentage movement from actual comparable observations.
3. Compare asset movement against relevant benchmark/broader market where data exists.
4. Compute liquidity/turnover metrics with correct names; do not call volume/market-cap turnover “relative volume” without a historical baseline.
5. Use historical volatility or relative volume only when actual history and methodology support it.
6. Detect gaps, outliers and provider conflicts.
7. Distinguish facts (price changed) from hypotheses (possible catalyst).
8. Never claim a cause merely because an event and price movement happened at similar times.

**Outputs:** Market-analysis facts, calculations, context, hypotheses, unknowns and evidence.

**Acceptance:** Recalculations independently reproduce; units/timeframes correct; synthetic history impossible in production; correlation/causation language validated; provider gaps explicit.

## 5.9 Module 9 — Blockchain & On-chain Intelligence Engine

**Purpose:** Add verifiable blockchain observations for Binance Spot-eligible assets only.

**Provider selection:** No RPC/indexer/explorer provider is selected by this architecture. Candidate sources must pass the open-source/vendor evaluation rule, coverage check, official documentation, rate limits, licensing, cost and reliability review before approval.

**Required logic:**
1. Require an `ELIGIBLE` Binance asset decision before on-chain candidate analysis.
2. Resolve native asset or exact token contract/network mapping from a trustworthy registry/official project source and corroborate against asset identity. Ticker alone is invalid.
3. Support only explicitly configured networks and token standards.
4. Retrieve actual chain data using documented RPC/indexer APIs.
5. Record chain ID, block height/hash, transaction hash/address references where appropriate, block time, observation time, provider and finality/confirmation semantics.
6. Handle reorgs, pending transactions, duplicate transaction logs, pagination, decimals, token migrations and wrapped/bridged representations correctly.
7. Define “whale/large transfer” thresholds explicitly and label them as system thresholds—not proof of buy/sell intent.
8. Do not infer exchange inflow/outflow without verified wallet labels and provenance.
9. Treat addresses as pseudonymous; do not claim real-world identity without reliable evidence.
10. On-chain data is corroborative. It cannot independently establish price causation or authorize publication.

**Outputs:** Timestamped on-chain observations with exact asset/network mapping, methodology and limitations.

**Failure rules:** Unsupported network, uncertain contract mapping, stale block data, RPC failure or unverifiable wallet label becomes `UNAVAILABLE`/`UNVERIFIED`; no invented metrics.

**Acceptance:** Exact mapping test for contract and native assets; wrong-chain/same-ticker rejection; decimals and reorg handling; duplicate log prevention; provider failure; no unlisted asset enters on-chain candidate path.

## 5.10 Module 10 — Event Intelligence Graph

**Purpose:** Link events, assets, sources, market observations and on-chain evidence so the agent can understand relationships and avoid duplicate narratives.

**Implementation rule:** First evaluate whether current relational database and existing open-source graph/relationship libraries are sufficient. Do not introduce a graph database or graph framework solely because the design uses the word “graph.”

**Required logic:**
1. Represent entities (asset, project, announcement, event, source, market observation, on-chain observation) with stable IDs.
2. Represent relationships with type, evidence, timestamp and confidence.
3. Only create confirmed relationships when evidence supports them; otherwise mark as possible/unknown.
4. Cluster copied reports while retaining original source ancestry.
5. Detect event updates versus distinct new events.
6. Keep graph state reproducible from persisted source records.

**Outputs:** Event relationship set/graph view and duplicate cluster references.

**Acceptance:** Relationship always traceable to evidence; copied content not counted as independent corroboration; no unsupported causal edge; graph data can be reconstructed or audited.

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