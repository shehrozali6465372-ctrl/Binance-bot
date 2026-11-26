# Module 14 Factor Provenance — Implementation Status

Date: 2026-11-22
Status: PARTIAL — structural snapshot validation and persistence digest verification implemented; factor scoring remains inactive.

## Implemented

- Strict, versioned v2 snapshot validation with legacy v1 compatibility.
- Six-factor completeness, explicit READY/MISSING/STALE/CONFLICTED/UNVERIFIED status handling; NOT_APPLICABLE rejected until an approved rubric permits it.
- READY-only numeric values (finite 0–100); non-READY values must be null and carry reason codes.
- Subfeature asset binding, source reference shape, SHA-256 payload-hash shape, explicit unit, unique feature keys, UTC timestamps, cutoff enforcement, measurement-window validation, transformation/baseline version pairs, and missingness rules.
- Future event timestamps require explicit SCHEDULED_FUTURE_EVENT semantics.
- Decision digest now validates and binds the complete v2 snapshot; legacy v1 digest semantics remain readable.
- Shared validation in PostgreSQL decision input validation; PostgreSQL read path recomputes digest and rejects tampered stored payloads.
- SQLite save path inherits shared digest validation. No database migration was needed.

## Tests added

- Unit coverage for valid/invalid v2 envelopes, legacy compatibility, missing/duplicate factors, status/value invariants, missing source refs, wrong asset, malformed hashes, cutoff violations, scheduled future event semantics, baseline provenance, duplicate subfeature keys, UTC timestamps, digest binding, SQLite v2 replay, PostgreSQL validator parity, and stored digest mismatch.
- Isolated PostgreSQL CI tests added for v2 persistence round-trip and tampered-row read rejection.
- Latest focused local run: **40 tests passed, 0 failures**. Local full discovery was environment-blocked (574 tests, 59 skipped, 34 errors; missing Pillow and psycopg imports were observed). Hosted CI on final code head 756fc9100b848ba21a99c8f84374636b91a2d200 passed: mocked safety suite **813 tests, 0 failures, 61 skipped**; isolated PostgreSQL integration **92 tests, successful**; isolated database target guard PASS.

## Explicit limitations

The validator does not establish that source IDs exist, payload hashes match actual payload bytes, sources are authentic/independent/authoritative, claims are supported, or numeric values are correctly derived. It does not validate approved rubric allowlists, source-specific freshness rules, human editorial labels, semantic novelty, or risk scoring. These require factor-specific logic and real historical evidence.

## Unchanged / not authorized by this implementation

- No changes to `OpportunityEvaluationEngine`, its six-factor interface, `main.py`, scheduled runtime or factor provider integrations.
- No policy weights, thresholds, floors, or factor values selected or activated.
- Runtime remains `factors=None`, `policy=None`; fail-closed DEFER.
- No database schema changes or migrations, production DB reads, Neon wake, live provider requests, publisher/gateway changes, or real posts.
- B-SCORE-01 remains OPEN. Project remains PARTIAL — NOT PRODUCTION-READY.

## Next

1. Review factor-specific semantic validation and source-reference resolution requirements.
2. Obtain a separately authorized, read-only historical-data inventory target; do not resume Neon or access production without new scope.
3. Design factor derivation only after evidence availability, source lineage, timestamp coverage and human labels are empirically established.
4. Keep shadow evaluation and any runtime activation behind separate explicit approval. Do not activate scoring from schema tests alone.


## Source-reference resolution next phase — 2026-11-22
- Read-only audit completed; see MODULE14_SOURCE_REFERENCE_RESOLUTION_AUDIT.md.
- V2 currently validates source_refs and source_payload_hashes structurally only. It does not resolve IDs against a persisted ClaimRegistry or verify hashes against payload bytes.
- Proposed next format is registry-bound v3 with exact registry_verification_id, per-source provenance, digest-verified ClaimRegistry resolution, exact asset/cutoff checks, and factor-specific independence/claim support rules. Not implemented or activated.


## ClaimRegistry snapshot integrity — 2026-11-22
- Added verify_claim_registry_payload() to SQLite and PostgreSQL ClaimRegistry load paths. Both recompute verification_id and reject stored payload tampering while preserving historical serializer modes (SQLite ensure_ascii=True; PostgreSQL ensure_ascii=False).
- Focused local run across evidence verification, opportunity and PostgreSQL decision validation: **112 tests, 0 failures, 2 DSN-gated skips**; compileall and diff-check passed.
- Actual PostgreSQL JSONB tamper rejection test added to the isolated CI job. Registry-bound v3 source resolution remains unimplemented.


## Hosted verification — ClaimRegistry integrity follow-up
- Code head cfca027d5d2cf2831948eff0b620c4fddb4fa600 passed hosted CI: mocked safety suite **815 tests, 0 failures, 61 skipped**; isolated PostgreSQL integration **92 tests, successful**; isolated database target guard PASS.
- The PostgreSQL integration run included ClaimRegistry JSONB payload tamper rejection, fresh-process registry load, v2 opportunity snapshot round-trip, research-package asset binding and decision digest tamper rejection.
- Local focused run: **112 tests, 0 failures, 2 DSN-gated skips**. No production DB or Neon data accessed.


## Registry-bound source resolver implementation — 2026-11-22
- Added `resolve_factor_source_provenance()` as an additive resolver primitive. It requires the exact expected ClaimRegistry verification ID, verifies the stored registry payload digest using the historical SQLite/PostgreSQL serializer modes, reconstructs and validates every EvidenceRecord, recomputes evidence IDs, and rejects ambiguous/missing references.
- Requires per-source provenance copies to match the complete EvidenceRecord serialization, including trust fields omitted from `evidence_id` (publisher, source kind, source URL, primary flag and source status).
- Enforces exact canonical asset identity and published/updated/observed/event timestamps at or before the decision cutoff.
- Compares `source_payload_hashes` to non-empty registry `content_hash` values only. Records from adapters without a content hash (including current on-chain observation/summary adapters) require an empty hash list; no synthetic payload hash is created.
- Added 9 synthetic unit tests covering successful resolution, unknown IDs, publisher tampering, registry digest mismatch, wrong registry ID, cross-asset evidence, cutoff violations, mismatched payload hashes, and adapters without original payload hashes.
- Focused run: `tests.test_opportunity_registry_resolution`, `tests.test_opportunity`, and `tests.test_evidence_verification`: **116 tests passed, 0 failures**.
- Important boundary: this is a resolver primitive only. It is NOT yet wired into a schema-version-3 decision snapshot validator, SQLite/PostgreSQL decision persistence, or factor-specific claim/independence rules. Do not describe v3 as fully implemented or accept a READY factor based on this function alone. Runtime remains disabled (`factors=None`, `policy=None`); no provider, DB, publisher or gateway activation.


## V3 preflight extension — 2026-11-22
- Added structural schema-version-3 validation: requires a lowercase SHA-256 `registry_verification_id` and per-subfeature `source_provenance` entries whose evidence IDs exactly match `source_refs`. V1/v2 semantics remain unchanged.
- Added `validate_registry_bound_opportunity_input_snapshot()`, which resolves every v3 subfeature against the exact digest-verified ClaimRegistry snapshot and checks the canonical asset and decision cutoff.
- SQLite decision persistence and PostgreSQL decision-input validation explicitly reject v3 until exact registry resolution is integrated into both persistence/load paths. This prevents the new structural format from being mistaken for a fully registry-verified durable decision.
- Focused verification after v3 preflight and persistence guards: **120 tests passed, 0 failures** across resolver, opportunity and evidence-verification suites.
- `compileall` and `git diff --check` passed before the latest v3 edits; rerun required after final edits.
- Full local discovery on this worktree: **586 tests discovered, 59 skipped, 34 errors**. Observed errors are environment/dependency blockers, notably missing `Pillow (PIL)` and `psycopg`, plus tests importing `main.py` that transitively require Pillow. This is not a full-suite pass. PostgreSQL integration remains skipped because `TEST_POSTGRES_DSN` is absent; no DB was opened.
- V3 is therefore **preflight-only, not production-ready or persisted**. Next work: exact-ID ClaimRegistry loaders for SQLite/PostgreSQL, transactionally bind/resolve v3 on save and re-verify on load, add isolated PostgreSQL integration/fresh-process tests, then implement factor-specific claim support and source independence. Runtime remains disabled.


## V3 exact-registry persistence integration — 2026-11-22
- Added exact-ID ClaimRegistry loaders: SQLite `ClaimRegistryStore.load_by_verification_id()` and PostgreSQL `PostgresPublicationStore.load_claim_registry_by_verification_id()`. Both validate the requested lowercase SHA-256 ID and recompute the stored payload digest using the store's historical serializer mode. PostgreSQL exact lookup uses `FOR SHARE` so a registry row cannot be concurrently modified while a decision is being bound inside the transaction.
- SQLite `OpportunityDecisionStore.save()` now resolves the exact registry within its existing decision transaction and refuses missing/tampered snapshots. SQLite `load()` verifies the decision digest, reloads the exact registry and repeats v3 source resolution. Registry store schema initialization occurs in the decision-store constructor, not inside save(), avoiding an accidental commit of the outer decision transaction.
- PostgreSQL `save_opportunity_decision()` resolves the exact registry within its existing transaction, verifies decision/package asset identity, and validates every v3 source reference before insert. `load_opportunity_decision()` re-verifies the decision digest and exact registry source references before returning v3 records.
- Added SQLite positive save/load plus tampered-registry rejection and missing-registry rejection; added exact-ID PostgreSQL loader unit test and a DSN-gated PostgreSQL end-to-end v3 save/load/tamper-rejection test.
- Focused verification: **123 tests passed, 1 skipped** across registry resolver/opportunity/evidence suites; PostgreSQL opportunity unit group **5 tests passed, 2 DSN-gated skipped**. `compileall` and `git diff --check` passed.
- The real PostgreSQL end-to-end test was not run because `TEST_POSTGRES_DSN` is not configured. Do not claim PostgreSQL runtime acceptance. No Neon/production DB was accessed.
- Remaining v3 work: factor-specific claim support and independence semantics, source adapter contract review, full isolated PostgreSQL acceptance with DSN, crash/fresh-process replay acceptance. Runtime stays disabled pending policy/provider approval.


## Factor claim support and source-independence — 2026-11-22
- Added optional v3 `claim_refs` to subfeature provenance; malformed/duplicate IDs are rejected. V1/v2 schema semantics are unchanged.
- Registry-bound v3 validation now requires explicit verified claim support for READY `evidence_strength` and `materiality` subfeatures. Claims are reconstructed and their IDs recomputed; claim asset/subject, claim type, verification state, contradiction state, unresolved issues, and exact supporting-evidence linkage are checked against the selected digest-verified registry.
- Every source record used by these two factors must be covered by a referenced claim's supporting IDs and linked from the claim's own `evidence_ids`. Evidence references alone are not accepted as claim support.
- Added conservative dependency grouping across shared `source_family`, `lineage_id`, or `content_hash`. Claim independent-source counts are recomputed from exact supporting EvidenceRecords and compared with the stored verification result; inflated/mismatched counts fail closed.
- No global independence minimum, factor score, weight, threshold, freshness window, provider ranking or rubric was selected. Source grouping is a provenance deduplication primitive, not a claim of real-world independence/authenticity.
- Focused tests: **137 passed, 0 failed, 3 skipped** across claim support, registry resolution, opportunity, evidence verification and PostgreSQL opportunity tests. PostgreSQL DSN-gated acceptance remains unrun.
- Full local discovery after this change: **602 tests run, 60 skipped, 34 errors**. The errors are environment/dependency import failures caused by missing Pillow/PIL and psycopg; this is not a full-suite pass.
- Remaining: source adapter contract review, PostgreSQL v3 E2E under isolated TEST_POSTGRES_DSN, fresh-process replay/crash acceptance, empirical source-quality and historical-data validation, and separately approved factor rubrics/providers. Runtime remains `factors=None`, `policy=None`; B-SCORE-01 OPEN; project PARTIAL — NOT PRODUCTION-READY.


## Source adapter hash-contract hardening — 2026-11-22
- Directly reviewed announcement, Binance Spot exchangeInfo, Binance/CoinGecko market, trend, local publication-history, Module 9 on-chain observation and Module 9 transfer-summary evidence adapters.
- Confirmed hash kinds are not interchangeable: market adapters hash canonicalized parsed provider JSON; exchangeInfo hashes a selected canonical pair projection; publication history hashes a synthesized local assertion; CoinGecko trending hashes its parsed item in `main.py`, while market-derived trend topics inherit the MarketScanner market-item hash; the generic adapter itself does not recompute the preimage; announcement digest is upstream CMS supplied and not recomputed in this repository; on-chain observation and summary adapters provide no `content_hash` (summary ID is a derived aggregate fingerprint, not a raw provider payload digest).
- Added strict lowercase SHA-256 format validation for non-empty `MarketObservation.data_hash` and `EvidenceRecord.content_hash`; empty remains allowed where a source has no payload digest. This is format validation, not preimage verification.
- TDD: malformed-hash tests failed before implementation; all focused adapter/evidence/importer/event-graph tests now pass: **98 passed, 0 failed**. `compileall` and `git diff --check` pass.
- Remaining: verify upstream CMS hash preimage/retention and formalize the existing CoinGecko/trend producer contracts; introduce explicit hash-kind semantics before calling any canonical projection/local/aggregate fingerprint an original source-payload hash; add provider raw-response hash only where exact bytes/object are retained. No provider requests, DB access, migrations, runtime scoring or publisher changes.


## Market-derived trend provenance correction — 2026-11-22
- TDD identified `market_gainer` and `market_volume` as two views over one MarketScanner universe. Without an underlying content hash, their separate source labels had incorrectly produced two independence groups.
- Both now use `source_family=market_scanner_derived` and `source_kind=MARKET`. Trend context rendering and package claim extraction now accept both MARKET and SOCIAL trend evidence.
- Regression failed before the fix (count 2), then passed with count 1 plus context/claim linkage. Latest adapter/evidence/importer/event-graph batch: **99 passed**; 14 research-package tests passed excluding one PIL-blocked main-import test.
- No provider or DB access; no score activation.


## 2026-11-22 — Registry hash-kind contract and opportunity schema v4

- Added `EvidenceRecord.content_hash_kind` with an allowlist of explicit semantics. This field is included in new ClaimRegistry schema-v2 serialization and per-source provenance, but excluded from `EvidenceRecord.evidence_id` so historical evidence identity remains stable. The immutable ClaimRegistry payload digest binds the added metadata.
- Legacy ClaimRegistry schema-v1 snapshots without this field remain readable as `UNSPECIFIED`; legacy copied provenance remains compatible. New registry payloads declare schema v2.
- Annotated only audited producer semantics: normalized Binance CMS payload, Binance exchangeInfo selected projection, local publication assertion fingerprint, and canonical parsed provider JSON for supported market/trend adapters. Unknown trend hashes stay unclassified. Module 9 observation/summary records remain without content hashes.
- Added registry-bound opportunity schema v4. Its `source_hashes` list carries exact `evidence_id`, `sha256`, and `kind`; v4 resolution compares it against the immutable selected registry and rejects unknown/unclassified non-empty hashes. V1/v2/v3 paths remain supported.
- SQLite decision save/load and PostgreSQL save/load validation paths now accept and revalidate schema v4 against the exact registry. No migration or live database access was performed.
- TDD RED confirmed the new tests failed before `content_hash_kind` existed. Focused verification: **105 tests passed, 0 failures, 8 skipped**; compileall and diff-check passed.
- Full local discovery: **620 tests, 526 passed, 60 skipped, 34 errors**. The 34 errors are environment/dependency import failures due to missing Pillow/PIL and psycopg; this is not a full-suite pass. `TEST_POSTGRES_DSN` is absent, so PostgreSQL integration remains unverified.
- No scoring weights, thresholds, provider activation, runtime enablement, database migration, production/Neon access, publisher/gateway changes or live publication. B-SCORE-01 remains OPEN; project remains PARTIAL — NOT PRODUCTION-READY.


## PostgreSQL v4 integration coverage — 2026-11-22
- Added a DSN-gated PostgreSQL v4 save/load integration test that persists a schema-v2 ClaimRegistry, binds a schema-v4 opportunity decision, reloads and verifies the typed hash metadata, then mutates the stored JSONB hash-kind and requires registry digest rejection.
- Local focused run including this new test: **105 passed, 0 failed, 8 skipped**. The new PostgreSQL integration test is skipped because `TEST_POSTGRES_DSN` is not configured; no database was accessed. `compileall` and `git diff --check` passed.


## 2026-11-22 — Evidence hash-kind consistency edge case
- TDD identified a provenance inconsistency: `EvidenceRecord` accepted a non-`UNSPECIFIED` `content_hash_kind` while `content_hash` was empty. Such a record asserted a digest semantic without carrying any digest.
- RED: `test_evidence_record_rejects_hash_semantics_without_a_content_hash` failed because validation accepted the invalid record.
- GREEN: `EvidenceRecord.validate()` now rejects an empty content hash paired with any classified hash kind. Empty hashes remain valid when kind is `UNSPECIFIED`; non-empty hashes with legacy `UNSPECIFIED` remain readable for backward compatibility, while registry-bound v4 continues to reject unclassified non-empty hashes.
- Focused verification: `python -m unittest tests.test_evidence_verification tests.test_opportunity tests.test_opportunity_registry_resolution -v` — **137 passed, 0 failed, 2 skipped**. The two PostgreSQL end-to-end tests were skipped because `TEST_POSTGRES_DSN` is not configured.
- `python -m compileall -q layer1 tests` and `git diff --check` passed. No DB/Neon access, migration, publisher/gateway change, scoring activation, live post, commit, push or merge.
- Runtime remains `factors=None`, `policy=None`, fail-closed DEFER; B-SCORE-01 OPEN; project PARTIAL — NOT PRODUCTION-READY.

## 2026-11-22 — Claim-result evidence uniqueness guard
- TDD found that a digest-valid ClaimRegistry result could repeat the same evidence ID in `supporting_evidence_ids` (and related evidence-ID lists). The validator converted these lists to sets for linkage checks and therefore accepted duplicate entries even though the canonical verifier emits unique evidence IDs.
- RED: `test_registry_bound_v3_rejects_duplicate_claim_result_evidence_ids` failed because a duplicated supporting ID was accepted.
- GREEN: claim-result evidence ID validation now rejects duplicates in supporting, contradicting and complete evidence ID lists, with explicit invalid/duplicate diagnostics. Independent-source counts continue to be recomputed from exact records.
- Focused verification: `python -m unittest tests.test_opportunity_registry_resolution tests.test_evidence_verification tests.test_opportunity -q` — **138 tests passed, 0 failed, 2 skipped**. The two skips are PostgreSQL DSN-gated tests because `TEST_POSTGRES_DSN` is absent. `compileall` and `git diff --check` passed.
- No database/Neon access, migration, scoring activation, publisher/gateway change, live post, commit, push or merge. Runtime remains `factors=None`, `policy=None`, fail-closed; B-SCORE-01 OPEN; project PARTIAL — NOT PRODUCTION-READY.

## 2026-11-22 — Claim/result registry cardinality guard
- TDD found that a digest-valid ClaimRegistry could carry an orphan verification result whose `claim_id` did not identify any claim; the factor support path ignored that extra result. Result IDs are now required to be lowercase SHA-256 and the result-ID set must exactly equal the claim-ID set.
- RED: `test_registry_bound_v3_rejects_orphan_claim_verification_result` failed because the orphan result was accepted. GREEN: validator rejects orphan/missing result references before factor-level claim resolution.
- Latest focused verification: **139 passed, 0 failed, 2 skipped** across registry resolution, evidence verification and opportunity tests. Two PostgreSQL DSN-gated tests skipped because `TEST_POSTGRES_DSN` is absent. `compileall` and `git diff --check` passed.
- No DB/Neon access, migration, scoring activation, publisher/gateway change, live post, commit, push or merge. Runtime remains fail-closed; B-SCORE-01 OPEN; project PARTIAL — NOT PRODUCTION-READY.

## 2026-11-22 — ClaimVerificationResult schema and lineage consistency
- Continued the Module 14 registry-bound claim audit. Previously, the factor support path validated selected result fields but did not bind `source_lineage` to the exact supporting/contradicting EvidenceRecords, nor require the complete `evidence_ids` set to equal the verifier's canonical union of claim-linked, supporting and contradicting IDs.
- TDD RED reproduced acceptance of a digest-valid result whose `source_lineage` values were forged. GREEN: registry validation now requires the exact canonical result field set, an allowed state, unique lowercase SHA-256 evidence-ID lists, non-negative integer independent-source count, unique string issues, exact evidence-ID union, resolved supporting/contradicting records, recomputed lineage keys, and recomputed independent-source count for every result in the registry.
- Focused verification: **141 tests passed, 0 failed, 2 skipped** across registry resolution, evidence verification and opportunity tests. The two PostgreSQL integration tests remain skipped because `TEST_POSTGRES_DSN` is absent. `compileall` and `git diff --check` passed.
- This verifies internal registry consistency, not semantic truth, source authenticity, authority, or actual independence. No DB/Neon access, migrations, scoring activation, publisher/gateway change, live post, commit, push, merge or deployment. Runtime remains fail-closed; B-SCORE-01 OPEN; project PARTIAL — NOT PRODUCTION-READY.

## 2026-11-22 — Deterministic claim-result replay and cross-asset support guard
- Deeper semantic audit found that individually consistent result fields could still be forged together: a digest-valid registry could claim an unrelated-asset record as supporting evidence, update the lineage/count/evidence lists, and appear internally consistent without the canonical verifier ever producing that result.
- Added a TDD regression that constructs a self-consistent forged claim/result referencing an Ethereum evidence record for a different asset. The registry-bound validator now re-runs `EvidenceVerificationEngine` over the exact reconstructed claims and evidence records and compares each complete canonical result, including state, issues, support/contradiction IDs, lineage and independent count.
- RED: the forged cross-asset result was rejected by deterministic replay (test asserts that specific rejection). GREEN: focused suite **142 passed, 0 failed, 2 skipped**; `compileall` and `git diff --check` passed.
- This is deterministic consistency with the current verifier, not proof that the verifier's semantic rules are complete or that provider evidence is authentic. No DB/Neon access, migrations, scoring activation, publisher/gateway changes, live posts, commit, push, merge or deployment. B-SCORE-01 remains OPEN; runtime remains fail-closed; project PARTIAL — NOT PRODUCTION-READY.

## 2026-11-22 — Source-assertion prompt attribution gap
- Semantic/prompt audit found that `render_claim_registry()` instructed the downstream model to attribute `SOURCE_ASSERTION` claims to the named source, but the rendered claim only included evidence IDs; it did not include the supporting records' publisher names. The instruction therefore lacked the source identity it required.
- TDD RED reproduced the missing publisher attribution. GREEN: renderer now resolves supporting evidence IDs against the registry and includes the exact supporting publisher names for each verified source assertion. Publisher text is newline-normalized before rendering. If no supporting publisher resolves, the output explicitly says `UNAVAILABLE` rather than inventing one.
- Focused verification: **143 passed, 0 failed, 2 skipped** across evidence verification, opportunity registry resolution and opportunity tests. The two skips remain PostgreSQL DSN-gated. `compileall` and `git diff --check` passed.
- This closes a prompt-context attribution omission only; it does not prove that a publisher is authoritative or that its assertion is true. No DB/Neon access, migrations, scoring activation, publisher/gateway changes, live posts, commit, push, merge or deployment.


## 2026-11-22 — Market provider labels no longer imply primary authority
- TDD found a trust-boundary defect: the market evidence adapter marked any provider whose label started with `binance_` as primary. Provider labels are data, not a reviewed authority registry; even `binance_untrusted` passed the old heuristic.
- Removed this prefix heuristic. All `MarketObservation`-derived EvidenceRecords now remain `is_primary=False` until a separately reviewed, claim-scoped source-authority contract exists. Binance Spot market observations remain preserved as MARKET evidence and attributed to their provider, but they no longer satisfy the primary-evidence predicate solely by provider name.
- Clarified downstream prompt semantics: `VERIFIED/SOURCE_ASSERTION` records that a named publisher made a statement; it does not independently verify the truth of the statement. Source attribution is not source authority.
- Regression tests reproduced both issues before the fix. Focused current Module 14 batch: **151 passed, 0 failed, 2 skipped** across source-adapter contracts, evidence verification, opportunity registry resolution and opportunity tests. The two skips are PostgreSQL DSN-gated tests because `TEST_POSTGRES_DSN` is absent. `compileall` and `git diff --check` passed.
- This conservative guard does not establish source rankings or authorize scoring weights/thresholds. Runtime remains `factors=None`, `policy=None`, fail-closed DEFER; B-SCORE-01 OPEN; project PARTIAL — NOT PRODUCTION-READY.


## 2026-11-22 — Module 9 aggregate summary primary-source classification
- Continued auditing every remaining primary-evidence producer. A validated individual Module 9 observation can be primary for the exact chain transaction observation after acceptance identity matching; a Module 9 transfer summary is a derived aggregate, not an originating chain record.
- Changed `evidence_from_onchain_summary()` to preserve its accepted/threshold-qualified ONCHAIN evidence but mark it `is_primary=False`. The underlying accepted observations remain individually represented and may retain primary status. This prevents an aggregate summary from satisfying a generic primary-source requirement for an underlying chain fact.
- TDD RED showed the aggregate summary was incorrectly primary; GREEN verifies non-primary classification and preserved research-package linkage. Full focused test results are recorded in the latest checkpoint.
- No change to Module 9 validation, finality, transfer thresholds, scoring, or runtime activation. B-SCORE-01 remains OPEN; runtime fail-closed; project PARTIAL — NOT PRODUCTION-READY.


## 2026-11-22 — Deterministic replay preserves factor-level diagnostics
- Full test discovery after adding deterministic ClaimRegistry replay surfaced four compatibility failures in the older `test_opportunity_claim_support` suite. The underlying forged payloads were rejected, but replay/general consistency checks ran before the factor-specific checks and replaced established actionable diagnostics for wrong-asset, non-verified, contradicted and inflated-count cases.
- Added an early preflight for requested claim asset identity and VERIFIED/CORROBORATED state before global registry consistency/replay. The complete deterministic replay remains mandatory for every result. Refined the independent-source mismatch error to state that the count does not match recomputed evidence grouping.
- TDD regression/compatibility verification: `tests.test_opportunity_claim_support` **9 passed**; focused Module 14 batch **151 passed, 0 failed, 2 skipped**. Compile and diff checks run again after the complete batch.
- This is diagnostic ordering only; no validation gate was removed or weakened. PostgreSQL integration remains skipped without `TEST_POSTGRES_DSN`.


## 2026-11-22 — Full local discovery after diagnostic-order compatibility fix
- Re-ran `python -m unittest discover -s tests -q` after the factor-level preflight change: **630 tests discovered, 61 skipped, 34 import/runtime errors, 0 assertion failures**. The 34 errors are environment dependency failures, principally missing `PIL` (Pillow) and `psycopg`, which prevent importing image/publisher/PostgreSQL-dependent modules. This is not a full-suite pass.
- The four assertion failures from the prior discovery run are resolved. The relevant Module 14 focused suite remains **151 passed, 0 failed, 2 skipped**; both skips are PostgreSQL DSN-gated.
- No dependencies were installed because environment changes require approval and the task can proceed with the isolated suites. `compileall` and `git diff --check` passed.

## 2026-11-23 — Explicit source hash semantics and schema-version type hardening
- Added producer-declared hash semantics to `MarketObservation` and `TrendSignal`. Generic caller-created records with a digest now default to `UNSPECIFIED`; provider/source strings no longer imply canonical parsed JSON semantics.
- Binance Spot and CoinGecko market normalizers explicitly label hashes computed over their parsed response objects. HotSearch CoinGecko Trending and market-derived producers explicitly carry the same kind; the trend persistence bridge preserves it.
- Evidence adapters now pass through the declared kind. Legacy persisted payloads missing the new field load as `UNSPECIFIED`; SQLite and PostgreSQL record decoders preserve explicit typed kinds.
- Registry schema version validation now rejects bool/float values; source resolver also restricts hash contract versions to exact integer 3 or 4.
- TDD RED reproduced both inferred-kind defects and the bool/float schema-version acceptance; GREEN focused tests pass. Added regression coverage for producer declarations, unknown/legacy hashes, SQLite/PostgreSQL JSON round-trip, Layer 1 trend persistence and schema/hash-contract type validation.
- Latest combined local verification: **293 passed, 0 failed, 2 skipped**. Two PostgreSQL acceptance tests remain skipped because `TEST_POSTGRES_DSN` is not configured. No database or Neon access.
- This closes the local producer hash-kind inference/type-validation edge cases only. It does not establish provider authenticity, source authority, semantic truth or actual source independence. Opportunity scoring remains disabled (`factors=None`, `policy=None`); B-SCORE-01 and the separate M14 calibration/evaluator blockers remain OPEN.
- Changes remain local and uncommitted in the original dirty worktree. No PR update, push, merge, migration, deployment or live publication.


## 2026-11-24 — Raw numeric evaluator activation blocked (AUD-M14-002)
- TDD reproduced that `OpportunityEvaluationEngine.evaluate()` could return PROCEED from six caller-supplied numeric factors with a test-only policy and otherwise satisfied hard gates.
- The raw `Mapping[str, float]` branch no longer calculates a weighted score. A complete/in-range raw mapping is recorded only as `UNVERIFIED_RAW_MAPPING` and returns `DEFER` with `REGISTRY_BOUND_FACTOR_PROVENANCE_REQUIRED`. Missing/incomplete/invalid mappings continue to defer with their validation reasons.
- Updated tests to assert raw values cannot produce PROCEED. Focused opportunity suite: **38 passed**. Full isolated suite: **1026 tests, 0 failures/errors, 63 skipped**. Compileall and diff-check passed.
- This closes the raw-mapping bypass only. No registry-bound production scoring engine, weights, thresholds, floors or factor values were invented. `AUD-M14-001` remains OPEN; active runtime remains `factors=None`, `policy=None`, fail-closed DEFER. Module 14 remains FAIL / DEFER; project remains PARTIAL / NOT PRODUCTION-READY. No DB/provider/publisher/runtime activation.
