# Module 14 — Factor Provenance and Point-in-Time Evidence Contract

**Status:** PARTIALLY IMPLEMENTED — V2 STRUCTURAL VALIDATION AND DIGEST REPLAY ONLY; NOT ACTIVE FOR SCORING
**Date:** 2026-11-22
**Parent documents:** `MODULE14_OPPORTUNITY_SCORING_POLICY_PROPOSAL.md`, `MODULE14_FEATURE_DATA_AVAILABILITY_AUDIT.md`
**Runtime effect:** NONE. The scheduled path must continue to pass `factors=None` and `policy=None`.

## 1. Purpose

A Module 14 decision must be reproducible from the exact evidence available at its decision cutoff. Six final numbers are not sufficient audit evidence.

This contract defines the minimum provenance envelope required before any factor provider can be trusted. It does not define factor values, weights, thresholds, floors, freshness limits, or a scoring algorithm.

## 2. Required evaluation pipeline

The intended future sequence is:

1. Resolve canonical asset and event identity.
2. Freeze a point-in-time evidence snapshot at a declared UTC cutoff.
3. Resolve source lineage, dependency groups, revisions and claim-level support.
4. Evaluate non-compensatory eligibility, evidence, event and platform gates.
5. Derive deterministic, source-backed subfeatures for each factor.
6. Produce a factor assessment with explicit availability/quality state.
7. Score only if all decision-required factor assessments are complete and valid under a separately approved rubric/policy.
8. Persist immutable factor provenance, decision inputs, policy version and resulting decision.
9. Preserve fail-closed DEFER if any required evidence is missing, stale, conflicted, unverified or cannot be replayed.

LLM output may help draft a human-readable explanation, but must not supply or override source authority, claim verification, factor numbers, policy weights, thresholds, gate results or missing-data status.

## 3. Canonical factor assessment envelope

Each of the six existing factors must eventually produce a record with these fields:

| Field | Requirement |
|---|---|
| `factor_name` | One of the six locked names: evidence_strength, timeliness, materiality, audience_usefulness, novelty, risk_control |
| `assessment_status` | READY, MISSING, STALE, CONFLICTED, UNVERIFIED, or NOT_APPLICABLE (only if a separately approved rubric defines it) |
| `value` | Nullable until READY; if READY, finite and within the engine's approved range |
| `rubric_version` | Immutable identifier for factor definition and qualitative anchors |
| `feature_pipeline_version` | Immutable identifier for extraction/transformation code |
| `source_contract_version` | Provider/source field contract version |
| `subfeatures` | Non-empty, named, typed list of the evidence inputs used |
| `reason_codes` | Stable machine-readable reasons for missingness, conflict, stale data or exclusion |
| `evaluated_at` | UTC timestamp of factor evaluation |
| `decision_cutoff_at` | UTC evidence cutoff used for the assessment |

A non-READY assessment must not contain a numeric factor value. Missing or unknown must never be converted to zero, a midpoint, a neutral score, or a model-generated estimate.

## 4. Subfeature provenance envelope

Every subfeature must retain:

- `feature_key`: stable identifier, not a display label;
- `availability`: AVAILABLE, MISSING, STALE, CONFLICTED, UNVERIFIED, or NOT_APPLICABLE under an approved rule;
- `raw_value`: typed value or null; preserve original source units and precision;
- `normalized_value`: optional deterministic transformation output, with its own unit;
- `unit`: explicit unit/currency/network/measurement convention;
- `source_refs`: one or more exact evidence IDs, observation IDs, event/revision IDs or provider record IDs;
- `source_payload_hashes`: hashes of exact source payloads where the underlying record may be revised;
- `provider_timestamp`: timestamp asserted by provider/source, if supplied;
- `event_at` plus `event_time_semantics`: event time and whether it is an observed event time or an explicitly scheduled future event;
- `published_at` / `updated_at`: source publication and update timestamps where applicable;
- `observed_at`: when this system retrieved/observed the source;
- `window_start_at` / `window_end_at`: exact interval for any aggregate or time-series calculation;
- `transformation_id` and `transformation_version`: deterministic calculation provenance;
- `baseline_id` and `baseline_version`: required whenever relative, normalized or benchmark comparison is used;
- `source_dependency_group`: shared-origin/syndication group, if applicable;
- `quality_flags`: explicit flags for gaps, stale data, provider conflicts, incomplete pagination, reorg, mapping uncertainty or other relevant limitations;
- `missing_reason`: mandatory when the feature is not AVAILABLE.

Do not put API keys, access tokens, credentials, private user data or unnecessary full source text into this envelope. Prefer immutable IDs and hashes linked to the approved evidence store.

## 5. Factor-specific minimum provenance

### 5.1 Evidence strength

Subfeatures must link each material claim to the exact supporting/contradicting evidence IDs, source kind/family, publisher, primary-source status, lineage/dependency group, claim verification state and canonical asset/mapping identity.

Independent-source counts must be traceable to the source groups actually counted. Copies, syndication and shared-origin reporting cannot be counted as independent corroboration. Authority is claim-specific, not a universal provider ranking.

### 5.2 Timeliness

Each timestamp must retain its semantic type: event time, publication time, source update time, provider observation time, local retrieval time, or decision cutoff. A freshness assessment must reference the applicable field/provider/event-class rule version and the actual age calculation.

Untimestamped sparkline positions or ingestion time cannot be substituted for source event time. Future event time is not evidence that the event has already occurred.

### 5.3 Materiality

Each subfeature must retain event category, affected asset/user/network/venue scope, verified mechanism, magnitude/unit where supported, event window, market benchmark/baseline and data quality. Market reaction must be labeled as observed reaction, not causal attribution.

If liquidity is relevant, preserve the actual order-book snapshot timestamp, pair, quote asset, depth levels and spread calculation. A single current snapshot cannot be represented as historical liquidity.

### 5.4 Audience usefulness

Each assessment must record the target reader question, intended reader segment, verified answer, practical context, affected scope, uncertainty/caveats, and reviewer rubric version. Human adjudication must be traceable by pseudonymous reviewer ID/role, timestamp and adjudication outcome. Engagement is not a factual evidence label.

### 5.5 Novelty

Each assessment must link exact prior event/revision, prior editorial brief/angle, draft and publication IDs; identify the material delta; and retain the comparator version and result. Unresolved source revision identity must remain unresolved.

The existing event lifecycle lexical comparator may be used only when stable event identity is proven. Binance CMS payload fingerprints that change with title/publish date must not be treated as provider-stable revision lineage.

### 5.6 Risk control

Each risk subfeature must retain risk category, evidence IDs, severity rubric version, time window, asset/network/pair scope, mitigation/disclosure state and hard-gate status. Prohibited platform content is a hard gate, not a numeric deduction.

A high risk_control value must mean risks are identified and responsibly bounded. It must never mean that an asset is safe, low-risk as an investment, or expected to appreciate.

## 6. Point-in-time and replay invariants

1. Every evidence item used must have been published/observed by the decision cutoff, except a future `event_at` explicitly representing a scheduled future event.
2. Later source revisions, later prices, later chain attribution, later lifecycle outcomes and later engagement cannot leak into a past decision snapshot.
3. The exact source payload hash, feature code/rubric version, baseline version and cutoff must be retained.
4. All derived features must be reproducible from stored inputs. Non-deterministic LLM judgements cannot be the sole source of a numeric factor value.
5. Cross-asset evidence must be rejected or explicitly scoped; no implicit ticker-only identity joins.
6. Cross-network token amounts cannot be added unless a separately validated common unit/representation and bridge/duplicate treatment exists.
7. Reorged/orphaned on-chain events must be excluded from canonical evidence and remain visible as quality/rejection history.
8. Every factor value must be explainable as a deterministic mapping from its subfeatures and rubric version.
9. The immutable decision digest must bind the complete factor provenance envelope, not just the six final values.
10. If a source cannot be replayed or provenance is incomplete, the factor assessment is not READY and scoring must not proceed.

## 7. Immutable decision snapshot compatibility

The current decision snapshot outer shape remains `{"policy": ..., "inputs": ...}`. Version 2 is now supported by a strict structural validator through `inputs.schema_version = 2` and a `factor_assessments` collection, while snapshots without a schema version retain legacy v1 replay semantics. Both versions remain bound by deterministic canonical JSON and SHA-256 digest binding.

Before implementation, review all consumers and validators:
- `OpportunityEvaluationEngine.evaluate()` snapshot construction and `_decision_digest()`;
- SQLite `OpportunityDecisionStore`;
- PostgreSQL `validate_opportunity_decision_input()` and `save_opportunity_decision()`;
- decision migrations and read/load paths;
- fresh-process durability tests;
- existing idempotency/collision tests.

Do not silently change snapshot schema in place. Add an explicit schema version, migration/backward-compatibility strategy and replay tests. Existing historical decision snapshots must remain readable and immutable.

## 8. Required tests before any factor provider can be accepted

- Missing required subfeature => no numeric factor value and no PROCEED.
- Stale/conflicted/unverified subfeature => explicit status and fail-closed result.
- Wrong asset/mapping/evidence reference => reject.
- Evidence observed after cutoff => excluded or rejected; never silently included.
- Source copies with common lineage => no extra independent corroboration.
- Same input snapshot and versions => byte-identical canonical provenance and decision digest.
- Any source value, evidence ref, window, transformation, baseline, rubric or policy change => decision digest changes.
- Reorged on-chain evidence cannot enter a READY factor.
- Untimestamped CoinGecko sparkline points cannot be used for event-window features.
- Current order-book snapshot cannot be represented as historical depth.
- CMS title edit with unresolved provider revision identity cannot be asserted as a correlated material update.
- Hard-gate failure cannot be offset by high values in other factors.
- Risk-control polarity is tested so "high" never means "asset is safe".
- LLM output cannot set factor values, weights, thresholds or gate state.
- Fresh-process database replay reproduces the same factor assessments and decision digest.

## 9. Approval boundary

This is a design contract only. It does not authorize:
- reading production database rows or resuming Neon;
- collecting live provider data or adding recurring API calls;
- changing database schemas/migrations;
- changing `OpportunityEvaluationEngine`, scheduled `main.py` behavior or the six-factor interface;
- selecting factor values, weights, thresholds, floors or source trust rankings;
- activating PROCEED or publishing content.

Those steps require separate scoped review and approval. Until then, keep `factors=None`, `policy=None`, and DEFER.


## 10. Implementation status — 2026-11-22

Implemented in the continuation branch (structural/persistence layer only):

- `validate_opportunity_input_snapshot()` accepts legacy v1 snapshots without rewriting them and validates strict v2 snapshots.
- V2 requires all six locked factor names exactly once, explicit assessment state, finite 0–100 values only for READY, and reason codes with null values for non-READY states.
- V2 subfeatures require exact asset identity, unique feature keys, explicit units, source references for AVAILABLE features, correctly shaped SHA-256 payload hashes, observed-at UTC timestamp, and paired measurement-window boundaries.
- Provider/published/updated/observed timestamps and measurement-window end cannot be after the decision cutoff. Future `event_at` is accepted only with `SCHEDULED_FUTURE_EVENT` semantics.
- Normalized values require transformation and baseline ID/version provenance. NOT_APPLICABLE is rejected until an approved rubric explicitly supports it.
- `_decision_digest()` validates the snapshot before hashing, so all factor provenance fields are included in the immutable digest.
- PostgreSQL input validation uses the same validator. PostgreSQL decision reads recompute and verify the digest; the helper handles PostgreSQL NUMERIC/Decimal scores.
- SQLite decision saves use the same digest path and therefore validate v2 snapshots while preserving legacy v1 records.
- No database migration was needed. No applied migration file was changed.

Verified locally so far:
- Focused local run: **40 tests passed, 0 failures** across opportunity and PostgreSQL decision validation/digest unit tests.
- Full local discovery: **574 tests, 59 skipped, 34 errors**. Import failures observed include missing `PIL` (Pillow) and `psycopg`; the workflow installs both via its explicit dependency steps. This is not a clean full-suite pass. DSN-gated PostgreSQL tests were not run locally.
- PostgreSQL live integration test cases were added to the isolated CI suite, including v2 persistence round-trip, research-package asset binding, and tampered-row read rejection. Hosted verification for this code commit remains pending.

Important limits — this is NOT factor approval or provider acceptance:
- The validator checks structure and timestamp relationships only. It does not resolve source_refs against the evidence store, prove that payload hashes match fetched payload bytes, establish source authenticity/authority, prove independence of source families, or verify claim-level support.
- It does not verify that a rubric/pipeline/source-contract version is approved, nor reproduce a numeric factor value from its subfeatures.
- It cannot infer from generic schema fields whether a measurement window or payload hash is semantically mandatory for a particular feature; factor-specific semantic validators remain required.
- It does not verify human audience-usefulness adjudication, semantic novelty, risk severity, prohibited-content classification, or source-specific freshness policy.
- `OpportunityEvaluationEngine`, its six-factor interface, `main.py` scheduled call, and provider integrations remain unchanged. No factor provider is wired. Runtime remains `factors=None`, `policy=None`, fail-closed DEFER.
- No scoring weights, thresholds, floors, source trust rankings, or factor values were selected or activated. No production DB or Neon data was accessed; no live provider requests were made; no publisher/gateway changes or real posts occurred.

The next required phase is factor-specific semantic/provenance resolution and empirical dataset validation. This requires separate review before connecting any factor provider or changing runtime behavior.


## 2026-11-22 — Module 14 v2 provenance verification update
- Focused local opportunity/PostgreSQL decision tests: **39 passed, 0 failed**. `compileall` and `git diff --check` passed.
- Full local discovery did NOT pass: 574 tests, 59 skipped, 34 errors. Observed import errors include missing `PIL` (Pillow) and `psycopg` in this remote worktree; workflow installs these dependencies. No local PostgreSQL DSN was configured, so DSN-gated integration tests were skipped.
- Added isolated PostgreSQL integration coverage for v2 snapshot round-trip, package asset identity mismatch rejection, and stored-row digest tamper detection. Awaiting hosted CI on the code commit.
