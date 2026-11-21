# Module 14 — Feature and Historical Data Availability Audit

**Audit date:** 2026-11-22
**Repository checkpoint:** `173f5e98329ed27e558fe448f55891e88ef1012e`
**Branch:** `layer-1/module9-onchain-continuation`
**Scope:** Read-only source-code and schema audit for the six Module 14 factors
**Result:** PARTIAL FEATURE READINESS — HISTORICAL CALIBRATION DATASET NOT YET VERIFIED
**Runtime:** unchanged; `factors=None`, `policy=None`; DEFER remains mandatory.

## 1. Audit boundary and evidence standard

This audit inspected the continuation worktree's typed models, providers, persistence adapters, lifecycle logic, scheduled Module 14 call site, and relevant tests. It did not read production database rows, resume Neon, call live market-data providers, change credentials, or modify publisher/gateway code.

No local SQLite database files were present inside the repository worktree. Neon is suspended by the previously approved test-window boundary. The PostgreSQL CI run uses a disposable service container and synthetic acceptance fixtures; it is not a representative historical production dataset.

Consequently:
- **Code-level availability** below means the repository defines and persists the relevant structure.
- **Historical coverage** means the number, duration, completeness, and representativeness of real records. It cannot be asserted without a separately authorized read-only inventory of the correct production/staging data store.
- No row counts, time coverage, sample sizes, or calibration sufficiency are claimed.

## 2. Executive findings

| Factor | Code-level inputs | Readiness | Main limitation |
|---|---|---|---|
| Evidence strength | EvidenceRecord, Claim, ClaimVerificationResult, ClaimRegistry, source lineage, independent-source count, ResearchPackage | PARTIAL / strongest foundation | Source lineage metadata exists, but source-family assignment and claim-level support need historical quality audit; no adjudicated opportunity labels |
| Timeliness | published/updated/event/observed/source timestamps, per-field freshness, event lifecycle, timestamped market snapshots | PARTIAL | CoinGecko sparkline has no per-point timestamp; snapshot density and historical coverage are unverified; freshness defaults are not empirically calibrated for Module 14 |
| Materiality | AnnouncementEvidence, event lifecycle, MarketAnalysisResult, on-chain transfer rollups | PARTIAL | No persisted historical order-book spread/depth; market metrics are not causal evidence; event-category impact labels absent |
| Audience usefulness | research_question, verified facts, unknowns, editorial strategy/brief | WEAK / not empirically measurable yet | No structured reader-question rubric, human editorial-worthiness labels, or outcome dataset |
| Novelty | announcement revisions, event lifecycle material-change comparator, editorial brief angle/version history, publication ledger | PARTIAL | Existing comparator is deterministic lexical normalization, not general semantic equivalence; scheduled Module 14 call does not receive its result |
| Risk control | hard gates, evidence contradictions/unknowns, event states, on-chain mapping/finality/reorg and rejection records, later content safety | PARTIAL | No complete structured market-integrity / liquidity / concentration risk feature set or factor provenance; some checks occur downstream of Module 14 |

**No factor is ready to generate production numeric values today.** The repository has meaningful typed inputs for several factors, but it does not yet have the complete point-in-time feature and label dataset required to fit defensible weights or thresholds.

## 3. Factor-by-factor source audit

### 3.1 Evidence strength — PARTIAL

**Already implemented**
- `EvidenceRecord` captures source ID, source family/kind, publisher, subject, claim key/value, publication and observation timestamps, asset/mapping identity, content hash, lineage ID, primary-source flag, and source status.
- `Claim` links exact evidence IDs to a claim and retains subject, asset/mapping, unit, timeframe, event time, impact and optional max age.
- `ClaimVerificationResult` retains VERIFIED/CORROBORATED/etc. state, supporting and contradicting evidence IDs, independent source count, source-lineage mapping, and issues.
- The verifier has source-independence logic; tests cover syndicated copies not counting as independent corroboration and independent sources corroborating a matching claim.
- `ClaimRegistryStore` and the PostgreSQL publication store persist append-only verification snapshots.
- `ResearchPackage` preserves verified facts, qualified inferences, disputed claims, unknown claims and evidence IDs.

**Not yet sufficient**
- A source-family or lineage label is only as reliable as its provider-specific assignment. Historical misclassification and shared-origin syndication must be audited.
- Source authority is not a universal scalar: authority must be claim-specific (e.g. exchange status versus protocol security).
- The Module 14 decision snapshot currently stores only six factor numbers/invalid markers and gate inputs. It does not bind factor subfeatures, evidence IDs, source-dependency groups, rule versions, or reviewer overrides.
- No independent human labels currently establish whether a research package was editorial-worthy at its original cutoff.

**Next required work**
1. Build a source-family/lineage quality report from an authorized historical snapshot.
2. Measure missing claim-to-evidence links, stale/contradicted evidence rates, and independence-group collisions.
3. Define claim-specific authority rules with source documentation; do not turn source-kind counts into a truth score.
4. Add factor provenance to the immutable decision record before any production factor provider is enabled.

### 3.2 Timeliness — PARTIAL

**Already implemented**
- Evidence and claims preserve published/observed/updated/event timestamps.
- Market observations preserve provider source timestamp, local observation time, field availability, field provenance, per-field freshness, and provider metadata.
- Binance 24-hour ticker normalization derives source time from provider `closeTime`.
- CoinGecko market normalization requires `last_updated`; the code explicitly marks sparkline history freshness UNKNOWN because the sparkline has no per-point source timestamp.
- Market observations are persisted as timestamped snapshots. Market analysis can calculate comparable 1-hour and 24-hour returns from earlier snapshots, and marks history gaps / unavailable baselines.
- Event lifecycle distinguishes confirmed/developing/stale/resolved/disputed/withdrawn states.

**Not yet sufficient**
- The CoinGecko seven-day sparkline is an untimestamped array in this model. It cannot safely support exact point-in-time event windows or per-point freshness.
- Existing provider freshness defaults (e.g. 300/900 seconds) are operational freshness rules, not Module 14 empirically calibrated freshness distributions.
- Market snapshot cadence, retention, missing intervals, and per-asset coverage have not been measured against real persisted rows.
- A newly ingested announcement is not necessarily newly public; market movement may precede the observed publication timestamp.

**Next required work**
1. Inventory historical snapshot cadence, gaps, provider timestamp quality and retention by asset/provider.
2. For event studies, use timestamped OHLCV/trades with explicit event cutoffs; never infer exact timestamps from sparkline index positions.
3. Derive field-specific freshness distributions from provider cadence and failure behaviour, then review by event/use case.
4. Preserve decision-time snapshots so later source edits cannot leak into earlier decisions.

### 3.3 Materiality — PARTIAL

**Already implemented**
- Official Binance `AnnouncementEvidence` contains event type, title/body, publication/update/event timestamps, asset IDs, content hash and revision metadata.
- Event lifecycle has a bounded material-change comparator. It normalizes selected function words and grammatical aliases while retaining entities, numbers, negation, action/status and event time.
- `MarketAnalysisResult` can persist 1-hour/24-hour returns, provider-reported 24-hour change, volume-to-market-cap turnover proxy, benchmark return and relative return, facts, unknowns and quality flags.
- On-chain observations and transfer rollups preserve mapping/network/transaction/block identity, block time, finality, per-network counts and rejected-event summaries.

**Not yet sufficient**
- The market analysis has no persisted historical order-book spread/depth feature. Binance `GET /api/v3/depth` returns a current order-book snapshot; it is not a historical depth archive.
- The current market model uses a volume-to-market-cap ratio as a turnover proxy. That is not relative volume, order-book liquidity, or proof of a catalyst's impact.
- The event comparator detects substantive token/date/action differences; it explicitly does not claim general natural-language semantic equivalence.
- No adjudicated event-category materiality labels or affected-scope measurements are stored as Module 14 training labels.
- On-chain transfer volume/count does not establish buy/sell intent, named-entity attribution, or a causal market impact.

**Next required work**
1. Decide which event categories can be assessed from official source claims alone and which require market impact evidence.
2. For liquidity-sensitive assessments, separately capture timestamped depth/spread snapshots with pair, depth level, quote currency and observation time.
3. Use benchmark-relative event windows only when the underlying timestamped data and baseline coverage pass quality checks.
4. Keep causal attribution out of materiality unless a separate causal evidence design supports it.

### 3.4 Audience usefulness — WEAK / not empirically measurable

**Already implemented**
- Research packages carry an explicit asset-specific research question, verified facts, qualified inferences, disputed/unknown claims and gaps.
- Editorial strategy can build an editorial brief from a research package and preserve event/angle/version identity.
- Trend signals/clusters can provide attention/discovery context, but their contract explicitly limits confidence to `ATTENTION_ONLY_NOT_EVENT_PROOF`.

**Not implemented as a validated factor**
- There is no structured rubric that measures whether a reader's actual question is answered, what reader segment is served, or whether the package adds practical explanatory context.
- There is no independent reviewer label for editorial usefulness at the original decision cutoff.
- Engagement, views, likes or post reach are not a valid substitute for factual quality or reader utility. They are also affected by distribution and timing.

**Next required work**
1. Create reviewer anchor examples and a consistent editorial-worthiness rubric.
2. Collect independent human labels before looking at subsequent market outcomes or engagement.
3. Record reader question, intended audience, affected group, explanation delta, limitations and unresolved questions as structured fields.
4. Keep engagement metrics as secondary outcomes only, never as truth labels.

### 3.5 Novelty — PARTIAL; existing capability needs integration

**Already implemented**
- Announcement revision history is persisted.
- Event lifecycle compares previous and current event title/type/body/event time using deterministic token normalization. This is a bounded material-change detector, not a general semantic model.
- Editorial briefs are versioned by event and angle; publication history is available through the durable publication ledger and legacy cooldown history.

**Important correction to the initial proposal**
- It would be inaccurate to say that no material-delta comparator exists. A deterministic comparator already exists in `EventLifecycleStore._has_material_event_change()` and is used during announcement lifecycle synchronization.
- The actual Module 14 gap is that `main.py` currently passes `materially_new=False` to `OpportunityEvaluationEngine.evaluate()`; the event-lifecycle result is not wired into this parameter.
- The current `duplicate_angle` input is derived from a publication cooldown. A cooldown is not a semantic duplicate detector.
- Critical identity interaction: for Binance CMS records, `source_id` is a payload fingerprint containing catalog ID + publish date + title. `EventLifecycleStore.event_identity()` includes `source_id`; therefore a title or publish-date edit can produce a different event ID, preventing the existing comparator from seeing the previous revision. The code correctly marks these records `UNRESOLVED_NO_STABLE_PROVIDER_ID`; do not wire `materially_new` from this comparator for those cases as if continuity were proven. Body-only changes may remain comparable when the fingerprint identity remains stable, but that is not a general revision guarantee.
- Binance CMS announcement records can use a payload fingerprint rather than a stable provider article ID; those records explicitly carry `UNRESOLVED_NO_STABLE_PROVIDER_ID` revision correlation status.

**Next required work**
1. Define a stable event/revision/angle linkage using source evidence and event lifecycle IDs. For Binance CMS fingerprint records, require a provider-stable ID or a separately validated conservative correlation key; do not guess continuity from title similarity alone.
2. Wire the existing material-change result only after tests prove correct event/asset scope, stable revision identity, and no false update on timestamp-only or wording-only changes.
3. Build a semantic coverage comparison for editorial angles using prior briefs/drafts/posts, with human-reviewed false-positive/false-negative samples.
4. Treat unresolved source revision identity as missing evidence, not as proof of novelty.

### 3.6 Risk control — PARTIAL

**Already implemented**
- Module 14 hard gates can reject/defer ineligible assets, stale/incomplete research, withdrawn/disputed events, contradicted claims, unresolved critical claims, unsupported causal framing, and duplicate angles without material updates.
- Evidence verifier preserves contradiction, unresolved and source-lineage details.
- On-chain pipeline validates canonical mapping, network/chain metadata, transaction/block identity and finality; ingestion journal retains canonical/reorged/unverified states and rejection counts.
- Content verification and publication authorization add downstream safety checks.

**Not yet sufficient**
- `unsupported_causal_framing` is currently passed as `False` by the scheduled Module 14 call. The hard-gate parameter therefore does not currently receive a computed assessment at this boundary.
- There is no complete typed market-integrity feature set for spread, depth, liquidity concentration, abnormal volume relative to asset-specific baselines, or coordinated promotion signals.
- No complete risk register links security incidents, source uncertainty, market manipulation indicators, promotion disclosures/conflicts and communication constraints to each candidate's point-in-time package.
- Some platform/content checks happen after Module 14; their existence does not prove Module 14 itself has all required risk inputs.

**Next required work**
1. Wire evidence-backed causal-framing assessment; keep missing/unknown fail-closed.
2. Add only sourceable risk features with exact time windows and mapping provenance.
3. Separate hard prohibited conditions from residual disclosable risk; never average a platform prohibition into a soft score.
4. Validate risk-control direction: a high value must mean risks are identified and responsibly bounded, not that an asset is safe or likely to appreciate.

## 4. Cross-cutting implementation finding: factor provenance is missing

The current `OpportunityEvaluationEngine` accepts a mapping of six floats in [0,100] and a policy. Its immutable snapshot records the factor numbers, gate values, policy weights and thresholds. It does not record:
- source/evidence IDs per factor;
- subfeature values and their transformations;
- exact observation windows and baseline versions;
- source timestamp versus local observation timestamp;
- missing/stale/conflict flags per subfeature;
- source dependency group / independence rationale;
- factor-rubric and feature-code version;
- reviewer adjudication / override history.

This is a blocking auditability gap. Before fitting parameters, a decision must be reproducible from its point-in-time feature evidence—not merely from six final numbers.

## 5. Historical dataset status — NOT VERIFIED

Repository persistence supports durable histories for:
- market observations and market analyses;
- announcement revisions;
- trend signals/clusters;
- claim-verification snapshots;
- research-package versions;
- event lifecycle/revisions;
- editorial brief versions;
- publication ledger and opportunity decisions;
- on-chain canonical transfer events and block journals.

That proves storage capability, **not** historical dataset sufficiency. This audit did not inspect production database rows or wake the suspended Neon endpoint. CI integration uses disposable synthetic test data. There is currently no verified count of unique assets/events, event categories, source families, decision cutoffs, labelled cases, or usable out-of-time history.

A separately authorized read-only inventory must report, without exposing credentials or content secrets:
- counts and min/max timestamps by table/provider/source family;
- unique asset/event/package/decision counts;
- completeness and missingness by factor input;
- source lineage collisions and revision-correlation unresolved rates;
- time gaps and market snapshot cadence;
- duplicate event/asset leakage across candidate train/test splits;
- independently reviewed labels and adjudication coverage.

No historical data should be copied to an unapproved external service. Sampling and feature extraction should occur in the authorized data boundary, with a documented anonymization/export policy if any data leave it.

## 6. Research-backed validation design

- Binance public market-data documentation separates current order-book depth, klines, recent trades, ticker and exchange information. Current `/api/v3/depth` output is a snapshot; historical depth must be collected and persisted prospectively if the feature is required. Klines are timestamped bars and are the more appropriate source for declared historical return windows.
  https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md
- Binance documents public market-data-only endpoints, including `depth`, `klines`, `aggTrades`, `exchangeInfo`, ticker and book ticker; this supports read-only acquisition without private account endpoints.
  https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md
- Scikit-learn's `TimeSeriesSplit` documentation explains why ordinary random cross-validation can train on future observations and evaluate on the past. It also notes equal spacing assumptions for comparable fold durations. The project should use chronological walk-forward folds and group event/asset leakage controls; irregularly sampled observations need time-based folds rather than blindly applying row-count splits.
  https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html

These sources justify the data and validation method only. They do not provide Module 14 factor weights, thresholds, labels or floors.

## 7. Recommended next implementation sequence

1. **Read-only historical inventory** — after explicit authorization for the exact data store and scope. No Neon wake or production DB access is implied by this audit.
2. **Factor provenance contract** — design a versioned typed structure for each factor's subfeatures, source refs, windows, quality/missingness and code/rubric version. Do not wire it into the live decision path yet.
3. **Fix existing wiring gaps in an isolated branch** — connect verified event material-change results and causal-framing evidence to Module 14 inputs only after targeted tests; keep scoring policy unset.
4. **Acquire missing prospective data** — historical depth/spread and any other fields not retained today, using public read-only sources and bounded cadence after cost/rate-limit design.
5. **Human adjudication corpus** — build independent editorial-worthiness labels at historical cutoffs, including negative, corrected, withdrawn, disputed and manipulation-risk cases.
6. **Walk-forward validation and shadow evaluation** — measure false-PROCEED, subgroup failures, sensitivity, missingness, reviewer agreement and drift.
7. **Separate owner approval** — present empirical parameters and uncertainty; only then consider runtime activation.

## 8. Safety and change record

- No application code, database schema/data, provider credentials, CI workflow, publisher, gateway, schedules, Neon endpoint, or publication behaviour changed.
- No real provider API calls or market-data collection were executed in this audit.
- No Binance Square post or media upload was made.
- Module 14 remains fail-closed: `factors=None`, `policy=None`; `DEFER` remains expected.
- B-SCORE-01 remains OPEN. Project remains **PARTIAL — NOT PRODUCTION-READY**.
