# Module 14 — Source Reference Resolution Audit

Date: 2026-11-22  
Review basis: read-only inspection of the existing EvidenceRecord, ClaimRegistry, evidence adapters, SQLite registry store and PostgreSQL registry persistence paths.

## Scope and safety

This is a code-level audit only. No database was opened, no production or Neon rows were queried, no provider was called, and no application/runtime/publisher behavior was changed.

## Verified current architecture

### Evidence identity

- EvidenceRecord.evidence_id is a deterministic SHA-256 over source_id, source_family, claim_key, subject, asset_id, mapping_id, value, unit, timeframe, event_at, status_value, published_at, updated_at, observed_at, content_hash and lineage_id.
- The evidence_id payload does not include source_kind, publisher, source_url, is_primary or source_status. Therefore evidence_id alone is not a complete integrity commitment to all trust/provenance attributes.
- ClaimRegistry.to_dict() includes claims, evidence_records, verification results and unresolved issues. Its verification_id is a SHA-256 of the canonical serialized registry payload. The registry snapshot hash therefore binds more fields than the individual evidence_id.
- SQLite ClaimRegistryStore.load_latest() and PostgreSQL load_latest_claim_registry() return the stored payload without recomputing verification_id from the payload. A future resolver must verify the registry snapshot digest before trusting it.

### Source lineage and independence

- EvidenceVerificationEngine._lineage_key() prefers lineage_id, then content_hash, then source_family.
- _independent_source_count() unions evidence records that share lineage_id, content_hash OR source_family. Multiple records from the same source family are not counted as independent merely because they have different evidence IDs.
- ClaimVerificationResult retains supporting_evidence_ids, contradicting_evidence_ids, independent_source_count, source_lineage and issues. Those are useful audit signals, but a factor assessment currently has no binding to a particular ClaimVerificationResult.

### Source payload hash coverage

- Announcement adapters propagate AnnouncementEvidence.content_hash.
- Market adapters propagate MarketObservation.data_hash.
- Trend adapters propagate TrendSignal.content_hash.
- Binance exchangeInfo and local publication-ledger adapters compute a canonical content hash.
- The current on-chain observation and on-chain summary adapters do not populate EvidenceRecord.content_hash. Their evidence_id still binds the normalized EvidenceRecord fields, but it is not a hash of the original provider payload bytes.
- Consequently a generic rule that every source reference must have a source_payload_hash is not supported by all existing adapters. Hash requirements must be source-contract-specific; do not invent a payload hash from incomplete source fields and label it an original-payload hash.

### Current v2 gap

- V2 source_refs are strings and are only structurally checked. They are not resolved against a persisted ClaimRegistry.
- source_payload_hashes are checked for SHA-256 syntax, not compared with source records or original payload bytes.
- A subfeature has one aggregate set of timestamps. If it references multiple evidence records, it cannot retain each record's separate provider/published/updated/observed timestamps, source family, lineage and trust status.
- A source_id can produce multiple EvidenceRecords for different claim_key/subject fields. source_id alone can therefore be ambiguous; exact evidence_id is the safer registry reference.
- A v2 READY status is structural only. It does not prove that the referenced evidence exists, is accepted, is independent, supports the claim, or was derived correctly.

## Recommended next schema and resolver design

Do not silently upgrade v2. Keep v2 as a structural snapshot format and introduce a separately versioned registry-bound format (proposed v3) only after review.

1. Add inputs.registry_verification_id. It must identify the exact immutable ClaimRegistry snapshot used when the factor assessment was prepared; do not resolve against whichever registry happens to be latest later.
2. Add a per-subfeature source_provenance array with one record per source reference. Each item should carry evidence_id, source_id, source_family, source_kind, publisher, asset_id, source_status, is_primary, published_at, updated_at, observed_at, content_hash and lineage_id.
3. Require source_refs to equal the unique evidence_id set in source_provenance. Resolve every evidence_id against the exact registry snapshot; reject missing or ambiguous references.
4. Recompute the ClaimRegistry verification_id from its canonical payload before resolution. Reconstruct each EvidenceRecord and recompute its evidence_id. Compare every copied source_provenance field to the stored record, not just its evidence_id.
5. Enforce exact asset identity and source timestamps <= the decision cutoff for every referenced record. Do not collapse multi-source timestamps into one timestamp and pretend each source was independently checked.
6. Compare source_payload_hashes with the source records' content_hash only where the adapter/source contract actually supplies a valid original-payload hash. For adapters without one, require an explicit non-payload-hash identity and keep the limitation visible.
7. Use source_family, lineage_id and content_hash dependency groups for factor-specific independence checks. Do not count multiple fields from the same provider/source family as independent corroboration.
8. Where a factor depends on verified claims, require explicit claim_id / verification result references and require the appropriate VERIFIED or CORROBORATED state with no relevant contradiction or unresolved issue. A raw evidence record is not automatically a verified claim.
9. Keep factor-specific rules separate: evidence strength needs source/claim quality and independence; timeliness needs per-source timestamps and calibrated freshness; materiality needs event/revision linkage and point-in-time market context; audience usefulness needs human editorial labels; novelty needs angle/revision correlation; risk control needs typed risk features and contradiction handling.
10. Preserve legacy v1 replay and v2 structural validation. New registry-bound validation must be additive and must fail closed when the exact registry snapshot is unavailable.

## Approval and activation boundary

This audit does not authorize:
- schema v3 implementation or changes to the six-factor OpportunityEvaluationEngine interface;
- production/Neon database access or waking the suspended Neon endpoint;
- any factor provider, scoring policy, weights, thresholds or runtime activation;
- publisher, gateway, content-generation or live publishing changes.

Implementation should begin with TDD against synthetic ClaimRegistry fixtures. PostgreSQL integration must use only the existing disposable CI PostgreSQL service unless a separate, explicit read-only/isolated target is authorized.

## Current status

- V2 structural validation and decision-digest verification: implemented and hosted CI accepted.
- Registry-bound source resolution: NOT IMPLEMENTED.
- Original payload-byte verification for all adapter families: NOT VERIFIED / not uniformly available.
- Factor-specific semantic readiness: NOT IMPLEMENTED.
- Runtime remains factors=None, policy=None; fail-closed DEFER.
- B-SCORE-01 remains OPEN. Project remains PARTIAL — NOT PRODUCTION-READY.


## 2026-11-22 — ClaimRegistry digest gap closed
- Current SQLite ClaimRegistryStore.load_latest() and PostgreSQL load_latest_claim_registry() now call verify_claim_registry_payload() and reject a payload whose verification_id does not match its canonical serialization.
- Serializer compatibility is explicit: SQLite uses ensure_ascii=True (historical default); PostgreSQL uses ensure_ascii=False (historical explicit setting). This avoids changing existing verification IDs.
- Added SQLite and PostgreSQL-loader tamper unit tests, including a non-ASCII payload test; added an actual PostgreSQL JSONB row-tamper integration test for CI.
- Exact source_refs resolution against a selected ClaimRegistry, per-source metadata binding and original payload-byte verification remain open; do not treat v2 structural refs as verified.


## Hosted confirmation — 2026-11-22
- ClaimRegistry SQLite/PostgreSQL read-time digest checks and the actual PostgreSQL JSONB tamper test passed hosted CI. The mocked safety suite passed 815 tests (0 failures, 61 skipped); isolated PostgreSQL integration passed 92 tests.
- This closes only persisted registry-snapshot digest integrity. Exact factor source_refs resolution and per-source provenance binding remain open.


## Resolver implementation progress — 2026-11-22
A first additive resolver primitive, `resolve_factor_source_provenance()`, is implemented and locally tested. It validates the exact registry snapshot digest, reconstructs EvidenceRecords and recomputes evidence IDs, compares complete per-source provenance copies, checks asset/cutoff boundaries, and matches source payload hashes only to non-empty registry content hashes. Synthetic adapters without content hashes are accepted only with no payload hash supplied. Focused verification passed 116 tests across resolver, opportunity and evidence-verification suites.

This does not yet complete the proposed v3 schema: the resolver is not wired into decision snapshot validation or SQLite/PostgreSQL persistence; factor-specific claim support and independence checks are not implemented. It must remain a precondition primitive, not a factor approval signal. Runtime remains fail-closed.


## V3 preflight boundary — 2026-11-22
The resolver is now exposed through a schema-version-3 preflight validator. V3 requires the exact registry verification ID and per-subfeature source_provenance matching source_refs. The validator resolves each source against the selected digest-verified registry. Decision persistence is deliberately blocked for v3 in both SQLite and PostgreSQL validation until those stores can load the exact registry by ID and repeat resolution transactionally/on read. Focused tests: 120 passed. Full local discovery: 586 discovered, 59 skipped, 34 environment/dependency errors (Pillow and psycopg absent); PostgreSQL DSN not configured. No production DB, Neon, provider, publisher or gateway was touched.


## Exact-ID persistence integration — 2026-11-22
Exact registry lookup and decision persistence are now wired for v3. SQLite and PostgreSQL can load a registry by its exact verification ID and verify its stored digest. SQLite decision save validates the referenced registry within its transaction; SQLite load revalidates it. PostgreSQL decision save validates the exact registry and package asset within its transaction; PostgreSQL load revalidates it. PostgreSQL exact registry lookup uses a row share lock during transactional binding. Tests include SQLite positive round-trip and registry tamper rejection, missing-registry rejection, PostgreSQL exact-ID loader unit coverage, and a DSN-gated PostgreSQL end-to-end round-trip/tamper test. Local focused run: 123 passed, 1 skipped; PostgreSQL opportunity group: 5 passed, 2 skipped because DSN is unavailable. PostgreSQL E2E is not yet accepted.

## Factor claim support and independence implementation — 2026-11-22

The following supersedes the earlier historical statements above that factor-specific claim/independence checks were still unimplemented:

- V3 subfeatures may carry `claim_refs`, exact Claim IDs from the same digest-verified registry. The v3 structural validator rejects malformed/duplicate claim references; v1/v2 envelopes remain unchanged.
- Registry-bound validation now requires claim references for READY `evidence_strength` and `materiality` subfeatures. Each referenced Claim is reconstructed and its claim ID recomputed; its asset/subject must match the decision asset; claim type must be `CONFIRMED_FACT` or `SOURCE_ASSERTION`; and the paired result must be `VERIFIED` or `CORROBORATED` with no contradiction or unresolved issues.
- Every source record used by those factors must be covered by the referenced claim results' `supporting_evidence_ids`, and the supporting IDs must also be linked from the Claim itself. Merely listing an evidence ID is not claim support.
- Claim result `independent_source_count` is recomputed from the exact supporting EvidenceRecords. A stored count that does not match the actual provenance groups is rejected.
- `group_independent_evidence_records()` conservatively joins records sharing any non-empty `source_family`, `lineage_id`, or `content_hash`. A shared token joins the records transitively; multiple evidence IDs or different publisher labels do not make copies independent. Missing content hashes are not invented; the source-family fallback still prevents same-family records from inflating independence.
- These checks validate linkage and consistency with the deterministic claim-verification registry. They do not establish real-world source authenticity, editorial authority, semantic entailment beyond the existing claim verifier, or a policy-required minimum number of independent sources. No universal independence threshold was added.
- Focused tests cover positive claim binding, missing claim refs, unverified/contradicted claims, cross-asset claims, evidence-reference mismatch, inflated independence counts, shared family/lineage grouping and shared payload hashes across different families.
- Focused verification after this change: **139 tests passed, 0 failures, 3 skipped** across claim support, registry resolution, opportunity, evidence verification and PostgreSQL opportunity tests. Skips include DSN-gated PostgreSQL acceptance; no PostgreSQL DB was accessed.
- Runtime scoring remains disabled. The implementation does not select weights, thresholds, factor values, source rankings or independent-source minimums.


## Source adapter contract audit — 2026-11-22

This section records a direct code-path review of the adapters and upstream model validators. It supersedes the earlier broad statement that the adapters uniformly supply original-payload hashes: they do not.

### Per-adapter findings

| Adapter | Identity / family / lineage behavior | Hash meaning and limitation |
|---|---|---|
| Binance announcement importer → `evidence_from_announcement` | `source_id` is passed through from the CMS ledger; `source_family` is `publisher.casefold()` (currently one Binance family); `lineage_id` is `content_hash` when present, otherwise `source_id`. CMS rows may explicitly mark `source_id_kind=payload_fingerprint` and unresolved revision correlation when the source ID is a local catalog/date/title fingerprint rather than a provider article ID. | `content_hash` is supplied by the upstream CMS database and format-validated, but this repository does not recompute it from title/body or prove the upstream hash preimage. `raw_evidence_ref` is a locator, not byte verification. Treat as upstream-attested digest until the worker's hash algorithm and retained bytes are independently verified. |
| Binance Spot `exchangeInfo` eligibility | Fixed family `binance_spot_exchange_info`; source ID includes symbol and observed-time digest; lineage equals the digest of the canonical pair projection. | Hash is computed from selected canonical fields (`symbol`, base/quote, trading status, spot permission, permission sets), not the full raw HTTP response. It is a normalized projection fingerprint, not a raw-response payload hash. |
| Local publication history | Fixed family `local_publication_ledger`; source and lineage IDs are derived from the local symbol/value/observed-time assertion. | Hash is over a synthesized local ledger assertion (`symbol|value|observed_at`), not an external provider payload. It is useful for idempotent identity, not independent market evidence. |
| Binance market ticker | Family is provider name; source ID/content hash are derived from canonical JSON serialization of the raw response payload; lineage uses that hash. | Raw response object is hashed after JSON canonicalization. This is a digest of the parsed JSON object, not transport bytes/headers. |
| CoinGecko market item | Family is provider name; source ID/content hash are derived from canonical JSON serialization of the individual raw item; lineage uses that hash. | Digest covers the parsed item object; not original wire bytes. `last_updated` is required and used as source timestamp. |
| Trend signal | CoinGecko trending retains `coingecko_trending`; its production caller sets `source_item_id` to the CoinGecko coin ID. Market gainer/volume topics share `market_scanner_derived` and use the canonical asset ID as `source_item_id`; their underlying market digest is inherited from the MarketScanner observation. | The CoinGecko trending caller computes SHA-256 over the canonicalized parsed `item` object. Market gainer/volume carry the `market_data_hash` generated by MarketScanner from the parsed CoinGecko market item. The generic `TrendSignal` adapter itself consumes the supplied digest and validates its format but does not recompute the preimage. Market-derived gainer/volume topics are typed `MARKET`; CoinGecko trending remains `SOCIAL` only as a legacy attention-signal category, not as proof that the underlying source is a social network. |
| Module 9 on-chain observation | Family is `observation.provider`; source ID is Module 9 `observation_id`; current adapter supplies no `content_hash` and no `lineage_id`. | `observation_id` is an internal normalized observation identity, not evidence that the original RPC response bytes were retained or hashed. Independence grouping therefore conservatively falls back to provider family. |
| Module 9 transfer summary | Fixed family `module9_canonical_store`; source ID is `summary_id`; no `content_hash` or `lineage_id` is supplied. | `summary_id` is a SHA-256 of a canonical aggregation fingerprint over normalized transfer/event fields, block hashes, totals, thresholds and time range. It is a derived aggregate fingerprint, not a raw provider payload hash. |

### Contract hardening implemented

- `MarketObservation.validate()` now rejects any non-empty `data_hash` that is not exactly 64 lowercase hexadecimal characters. Empty remains allowed for sources that do not provide a digest.
- `EvidenceRecord.validate()` now applies the same rule to non-empty `content_hash`. Empty remains allowed; no synthetic raw-payload hash is fabricated for Module 9 observations/summaries.
- This is format validation only. It does not prove the digest's preimage, origin, source authenticity, or transport-level integrity.
- Added test-first regressions for malformed digest rejection, absent-hash compatibility, on-chain no-raw-hash behavior, and the Binance exchangeInfo canonical-projection hash distinction.
- Focused run after these changes: **98 tests passed, 0 failures** across source adapter contracts, evidence verification, announcement importer and event graph. `compileall` and `git diff --check` passed.

### Remaining adapter gaps / next decisions

1. Verify the upstream CMS worker's exact content-hash preimage and retention path before treating announcement hashes as independently verifiable raw-content digests. Do not recompute from body alone until the worker contract is known.
2. Preserve hash-kind distinctions (raw parsed response, canonical projection, upstream-supplied digest, local assertion fingerprint, aggregate fingerprint, absent) in a future additive provenance contract. Do not overload `source_payload_hashes` with non-raw fingerprints.
3. Production CoinGecko trend producers currently compute hashes from parsed item objects, and market-derived trend producers inherit the market-item hash. Generic TrendSignal callers still need an explicit producer contract tying `content_hash` to retained source content; otherwise use source-item identity plus source-family fallback and do not assert payload integrity.
4. On-chain evidence needs an optional provider response digest only if the actual adapter retains the complete canonical provider response or an independently verifiable canonical event payload. Normalized observation IDs and summary IDs must not be relabeled as raw-payload hashes.
5. No adapter was invoked, no provider request was made, no database was accessed, and no Module 9 provider/runtime code was changed during this audit.


## Market-derived trend independence correction — 2026-11-22

- TDD exposed a false independence case: `HotSearchEngine._from_market_data()` emits `market_gainer` and `market_volume` as two labels over the same MarketScanner universe. When the underlying `market_data_hash` was absent, the evidence adapter used the two labels as separate `source_family` values, so the deterministic independence counter reported two sources from one underlying market scanner.
- Both labels now map to one `source_family=market_scanner_derived`, even when no hash is available. Their `source_kind` is `MARKET`, not `SOCIAL`; the existing trend context renderer and research-package claim parser accept both MARKET and SOCIAL trend records so the evidence remains usable without misclassifying market-derived topics as social data.
- Test-first regression failed before the fix (independent count 2, expected 1). After the fix, the adapter test verifies one dependency group, MARKET typing, context rendering and exact claim linkage.
- Updated focused verification: **99 passed, 0 failed** across source adapter contracts, evidence verification, announcement importer and event graph; **14 additional research-package tests passed** excluding one test that imports `main.py` and is blocked by missing Pillow/PIL in this environment. Compileall and diff-check passed.
- This corrects only the derived market-trend provenance classification/grouping. It does not establish independent providers or activate scoring.


## 2026-11-22 — Versioned hash-semantics binding and opportunity schema v4

The earlier v3 source-hash contract treated every non-empty `EvidenceRecord.content_hash` as a payload hash. Direct adapter/producer inspection established that this is not a safe generalization. Hash meaning is now explicit and bound by the immutable registry:

- `EvidenceRecord.content_hash_kind` is serialized in ClaimRegistry schema v2 and in copied per-source provenance. It is deliberately excluded from the historical `EvidenceRecord.evidence_id` formula; the enclosing registry digest binds the kind and all other serialized record fields.
- Legacy ClaimRegistry payloads without a schema marker remain schema v1. The resolver reconstructs their records with `content_hash_kind=UNSPECIFIED` and preserves their old evidence IDs and copied-provenance shape. New `ClaimRegistry.to_dict()` payloads declare schema v2.
- Producer assignments are evidence-specific: Binance CMS announcement import uses `CANONICAL_NORMALIZED_PAYLOAD_SHA256` (normalized CMS payload, not transport bytes); Binance Spot exchangeInfo uses `CANONICAL_SELECTED_PROJECTION_SHA256`; local publication history uses `LOCAL_ASSERTION_FINGERPRINT_SHA256`; parsed provider market data uses `CANONICAL_PARSED_PROVIDER_JSON_SHA256`. CoinGecko trending and market-scanner-derived trend records inherit the parsed-provider JSON classification. Unknown trend-source hash semantics remain `UNSPECIFIED`.
- Module 9 observation and transfer-summary adapters continue to provide no `content_hash`; no synthetic payload hash is fabricated.
- Opportunity schema v4 replaces ambiguous `source_payload_hashes` with `source_hashes`, an exact per-evidence list of `{evidence_id, sha256, kind}`. The resolver compares this list to the digest-verified registry record, rejects `UNSPECIFIED` non-empty hashes, and rejects copied or factor-level kind tampering.
- V1/v2/v3 opportunity validation remains available. SQLite decision save/load and PostgreSQL decision save/load validation paths now also bind and re-resolve v4 snapshots against the exact registry ID.

TDD evidence: the new registry/hash-kind tests failed before implementation because `EvidenceRecord` had no `content_hash_kind`. After implementation, focused evidence/opportunity/registry/PostgreSQL-adapter tests passed **103 tests, 0 failures, 7 skipped**; `compileall` and `git diff --check` passed. Full local discovery ran **620 tests: 526 passed, 60 skipped, 34 errors**. The errors are environment dependency import failures (`Pillow/PIL` and `psycopg` absent); this is not a full-suite pass. `TEST_POSTGRES_DSN` is not configured, so no PostgreSQL integration was run.

This implementation only improves provenance representation and immutable binding. It does not prove source authenticity, original transport-byte integrity, real-world source independence, correct hash preimages beyond the audited producer paths, or factor score validity. Runtime remains disabled; no weights/providers/thresholds were activated. B-SCORE-01 remains OPEN and the project remains PARTIAL — NOT PRODUCTION-READY.


## PostgreSQL v4 integration test added — 2026-11-22
A DSN-gated PostgreSQL integration test now covers v4 registry persistence, decision save/load and JSONB hash-kind tamper rejection. It is not executed locally because `TEST_POSTGRES_DSN` is absent. No database was accessed. Latest focused local run: **105 passed, 0 failed, 8 skipped**; compileall and diff-check passed.


## 2026-11-22 — Hash-kind consistency regression
- `EvidenceRecord.validate()` previously allowed a concrete hash-kind classification with an empty `content_hash`. This could encode provenance semantics without a digest value.
- Added a TDD regression (RED observed) and now reject that combination. Hashless evidence remains supported only with `content_hash_kind=UNSPECIFIED`; this preserves Module 9 observation/summary semantics. Existing non-empty legacy hashes with UNSPECIFIED remain loadable for v1/v2 compatibility; schema v4 still rejects them.
- Verification: 137 focused tests passed, 0 failed, 2 DSN-gated PostgreSQL tests skipped; compileall and diff-check passed.


## 2026-11-22 — Claim-result duplicate evidence reference edge case
- A digest-valid registry payload could contain duplicate IDs in a verification result's `supporting_evidence_ids`; the factor support validator used set-based subset checks and did not reject duplicates. This is malformed provenance even though repeated references did not increase the recomputed independent-source group count.
- Added a TDD regression (RED reproduced acceptance) and now require uniqueness in `supporting_evidence_ids`, `contradicting_evidence_ids`, and `evidence_ids` before linkage/count validation.
- Focused verification: **138 passed, 0 failed, 2 skipped**; PostgreSQL skips are due to absent `TEST_POSTGRES_DSN`. Compileall and diff-check pass.
- This is a structural provenance-integrity guard, not a scoring policy change or source-independence proof.


## 2026-11-22 — ClaimRegistry claim/result cardinality validation
- A digest-valid registry with an extra verification result for a nonexistent claim was silently accepted because the factor path only looked up explicitly referenced claims. That permits internally inconsistent registry snapshots.
- Added a TDD regression (RED reproduced acceptance). Result claim IDs must now be lowercase SHA-256 and the complete result-ID set must exactly equal the claim-ID set, rejecting both orphan and missing result rows.
- Latest focused verification: **139 passed, 0 failed, 2 skipped**; PostgreSQL integration skips remain due to absent `TEST_POSTGRES_DSN`. Compileall and diff-check pass.


## 2026-11-22 — ClaimVerificationResult internal consistency audit
- Found that digest verification alone only proves a stored payload matches its digest; it does not prove its nested verification-result fields are mutually consistent. The factor validator had not recomputed `source_lineage` or required `evidence_ids` to equal the canonical union emitted by `EvidenceVerificationEngine`.
- Added TDD coverage for forged lineage and mismatched result evidence linkage. Validation now checks the complete result schema, state enum, unique SHA-256 references, issue shape, exact result evidence-ID union, exact lineage mapping from registry EvidenceRecords, and recomputed independent-source count for every claim result (not only factor-referenced claims).
- RED reproduced forged-lineage acceptance. Focused suite: **141 passed, 0 failed, 2 skipped**; skips are PostgreSQL DSN-gated (`TEST_POSTGRES_DSN` absent). Compileall and diff-check pass.
- Scope limitation: internal structural consistency only; this does not establish source authenticity, semantic entailment, authority, or real-world independence. No DB/Neon access or publishing/runtime activation.


## 2026-11-22 — Deterministic replay of claim verification results
- A coordinated forged registry could previously add a cross-asset evidence record to `supporting_evidence_ids` and also rewrite the result's evidence set, lineage and independent count. Local field checks alone cannot prove that the canonical verifier would produce that result.
- Added a regression that updates the claim identity and registry digest consistently while inserting a different-asset record as purported corroboration. The registry-bound path now replays `EvidenceVerificationEngine` using the exact reconstructed registry claims/evidence and compares the full canonical result for every claim. The regression confirms the forged result is rejected specifically by replay comparison.
- Focused tests: **142 passed, 0 failed, 2 skipped**; skips remain PostgreSQL DSN-gated. `compileall` and diff-check pass.
- The replay proves deterministic derivation under the current verifier implementation; it does not prove the verifier captures every semantic edge case or establishes external source authenticity.


## 2026-11-22 — SOURCE_ASSERTION publisher attribution in rendered prompt
- Found a mismatch between the register's instruction (“Attribute SOURCE_ASSERTION claims to the named source”) and its actual rendered content: it exposed evidence IDs but omitted the corresponding publisher identity. A downstream model could not reliably follow the attribution instruction from the rendered register alone.
- Added a regression that expects the actual supporting publisher to appear. The renderer now resolves supporting evidence IDs to exact registry records and emits their publisher names; missing resolution is labelled `UNAVAILABLE`, never guessed.
- TDD RED reproduced the omission. Focused suite: **143 passed, 0 failed, 2 skipped**; compileall and diff-check passed. This improves attribution context, not source authority/authenticity.

## 2026-11-22 — Source authority is not inferred from provider labels

- TDD found `evidence_from_market_observation()` assigned `is_primary=True` whenever the caller-controlled `MarketObservation.provider` string began with `binance_`. This treated arbitrary labels such as `binance_untrusted` as primary authority and silently elevated Binance market observations without a claim-scoped authority contract.
- Removed the provider-name prefix heuristic. Market-observation evidence is now always non-primary (`is_primary=False`) until a separately reviewed, claim-scoped authority policy and provenance contract exist. `source_kind=MARKET` and publisher identity remain available for attribution and lineage; this change does not discard the observation.
- This is deliberately conservative. It does not assert that Binance market data is never authoritative; it says this adapter currently lacks enough verified metadata to encode authority safely. High-impact claims that need primary evidence remain UNVERIFIED unless supported through another explicit primary-evidence adapter plus independent corroboration.
- Also clarified the rendered model instructions: a `SOURCE_ASSERTION` marked `VERIFIED` means only that the named publisher made that assertion, not that its content is independently confirmed truth. Publisher attribution and source authority are distinct.
- TDD RED reproduced both issues: `binance_spot` and arbitrary `binance_untrusted` labels were both treated as primary, and the rendered prompt lacked the explicit definition. GREEN changes are covered by `test_market_provider_name_does_not_grant_primary_source_authority` and the source-assertion rendering regression.
- No live provider research, provider calls, DB/Neon access, migration, scoring policy/weight/threshold change, runtime activation, publisher/gateway change, live post, commit, push or merge. This does not establish any new source-authority ranking. B-SCORE-01 remains OPEN; runtime remains fail-closed.

## 2026-11-22 — Derived Module 9 summaries are not primary chain evidence

- Extended the primary-authority audit to all remaining `is_primary=True` evidence producers. Binance Spot `exchangeInfo` eligibility remains primary for the narrow claim it directly establishes (active Spot pair/permissions); the local publication ledger remains primary only for the project's own recorded publication history; an individually accepted Module 9 on-chain observation remains primary only after its exact asset, mapping, network, provider and observation IDs match the Module 9 acceptance record.
- Found that `evidence_from_onchain_summary()` also marked a Module 9 aggregate transfer summary as primary. That record is a derived threshold-qualified aggregate produced by the canonical store, not an individual source-chain observation. Its old flag could incorrectly satisfy a generic primary-source predicate for claims about on-chain activity.
- Changed aggregate summary evidence to `is_primary=False` while preserving `source_status=ACCEPTED`, `source_kind=ONCHAIN`, exact asset/mapping/network identity, summary ID and threshold qualification. This means the system can accurately cite the Module 9 aggregate without misrepresenting it as an originating primary chain source. The accepted underlying observations remain separately represented.
- TDD RED reproduced the old primary flag on a threshold-qualified summary; GREEN test asserts the summary is non-primary and the exact research-package linkage still works.
- This is a source-role classification correction, not a change to Module 9 acceptance/finality, thresholds, aggregation or opportunity scoring. No DB/Neon access, provider calls, migrations, scoring activation, publisher/gateway change, live posts, commit, push or merge.

## 2026-11-22 — External source-contract checks (official documentation)

This section records narrow claims supported by current official documentation; it does not assign a universal provider ranking or a numeric credibility score.

- Binance's official Spot API reference defines `GET /api/v3/exchangeInfo` as current exchange trading rules and symbol information, and exposes `status`, `baseAsset`, `quoteAsset`, `isSpotTradingAllowed`, `permissionSets` and related symbol metadata. This supports treating the official exchangeInfo response as primary evidence for the narrow claim that Binance currently reports a particular pair/status/permission. It does **not** make Binance authoritative for asset identity outside the verified mapping, market manipulation, security, token legitimacy, or independent investment merit. Sources: https://developers.binance.com/en/docs/products/spot/rest-api and https://developers.binance.info/en/docs/catalog/core-trading-spot-trading/api/rest-api/general
- Binance's official market-data-only documentation identifies public market endpoints including `/api/v3/ticker/24hr` and `/api/v3/exchangeInfo`; these are public observations. The endpoint's first-party origin proves who served the observation, not that one exchange's quote is a complete or manipulation-resistant representation of the global market. Source: https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md
- CoinGecko describes its market data as aggregated across centralized and decentralized exchanges and offers market/history endpoints. This is a provider description of its aggregation product, not independent validation of the provider's methodology or a guarantee that a value is authoritative for every asset/time window. Source: https://www.coingecko.com/en/api
- Ethereum's official JSON-RPC documentation distinguishes `latest`, `safe` and `finalized` block tags; `finalized` denotes the latest finalized block. A provider's claim of finality still needs exact network, block/transaction, mapping and provider-validation linkage in Module 9; a summary label alone is not proof. Source: https://ethereum.org/developers/docs/apis/json-rpc/

### Consequences for the code and scoring design

1. Keep exchangeInfo primary only for Binance's own current pair/permission assertions and only after canonical asset mapping proof.
2. Keep exchange ticker observations non-primary in generic evidence verification; use them as attributed market observations and reconcile provider discrepancies/market coverage separately.
3. Treat CoinGecko as an aggregated market-data provider observation, not a primary issuer/exchange assertion. Its provider documentation alone cannot justify a universal credibility score.
4. Treat Module 9 accepted individual chain observations as primary only for the exact validated observation/network/mapping; keep Module 9 transfer summaries as accepted derived evidence, not primary chain records.
5. Do not convert these source roles into Module 14 weights, minimum source counts, thresholds or a source leaderboard. Those require factor-specific labels, data and separately approved policy validation.


## 2026-11-22 continuation — exact Binance Spot base-asset binding
- Review found the evidence adapter accepted an arbitrary canonical CoinGecko asset ID alongside any syntactically valid active Binance pair. The runtime caller already selected pairs by ticker, but the adapter contract itself did not bind the pair's `baseAsset` to that caller-proven ticker.
- Added required `expected_base_asset` input; the adapter now accepts only pairs whose exact `baseAsset` matches it. The runtime passes the candidate ticker used by the upstream identity-proof path.
- Added a regression test proving a live-looking `DEFUSDT` pair cannot be attached to `coingecko:abc` when the expected base is `ABC`. Existing positive/negative pair fixtures now declare their expected base explicitly.
- This is a local adapter-boundary hardening change; it does not independently prove the upstream CoinGecko-to-Binance identity mapping. That proof remains the responsibility of the existing listing-eligibility path.


## 2026-11-22 continuation — announcement hash semantics
- Traced the in-repository announcement path: `announcement_importer` reads `content_hash` from the worker-owned `binance_announcement_events` table and passes it through; this repository does not contain the producer implementation or a canonical serialization contract for that field.
- The evidence adapter previously labelled every non-empty announcement hash `CANONICAL_NORMALIZED_PAYLOAD_SHA256`, which was stronger than the available evidence. Changed it to `UNSPECIFIED` while retaining the digest for source/revision correlation.
- Regression test first failed against the old label and now requires `UNSPECIFIED`. This does not prove the upstream digest is invalid; it records that its semantics are not independently established in this codebase. Do not promote it to a typed canonical hash until the worker producer and exact payload serialization are inspected and verified.

## 2026-11-22 continuation — ClaimRegistry producer authenticity and storage authorization boundary

- Traced the complete in-repository ClaimRegistry write/read paths. `EvidenceRecord.is_primary` is serialized by `ClaimRegistry.to_dict()` and therefore included in the registry snapshot SHA-256. The historical `EvidenceRecord.evidence_id` formula deliberately does not include `source_kind`, `publisher`, `source_url`, `is_primary` or `source_status`; factor resolution reconstructs and compares the complete serialized record, but that comparison is still against the registry payload supplied by the store.
- SQLite `ClaimRegistryStore.save()` computes the digest from the payload and inserts it; the loader recomputes the digest. PostgreSQL `save_claim_registry()` similarly computes the digest and inserts the JSONB snapshot; exact-ID and latest loaders recompute it. These checks detect payload changes when the expected digest is held fixed.
- They do **not** authenticate the original producer or protect the digest from an actor who can rewrite both `payload_json` and `verification_id`. Such an actor can change `is_primary`, recompute the public SHA-256, and create a self-consistent forged snapshot. Deterministic verifier replay does not close this gap because the replay consumes the same supplied evidence records and their asserted provenance fields.
- The PostgreSQL migration defines the snapshot table, primary key and read index, but contains no role creation, `GRANT`/`REVOKE`, row-level security policy, or mutation-prevention trigger. The SQLite store likewise has no database-enforced append-only trigger. Application methods use insert-only/idempotent behavior, but the checked-in schema does not establish that the deployed database role is unable to UPDATE/DELETE. Actual deployed grants were not inspected; no DB/Neon access was performed.
- No producer signature, signed source attestation, trusted ingestion identity, or externally protected digest/key is present in the inspected ClaimRegistry contract. Primary flags are assigned by in-repository adapter code: Binance CMS announcement assertions, Binance Spot exchangeInfo eligibility, local publication history, and accepted individual Module 9 observations. Their narrow claim scope was reviewed separately, but the persisted flag alone is not a cryptographic proof that the expected adapter produced the record.
- **Disposition:** do not add a fake signature, hard-coded key, or claim that SHA-256 is authentication. Keep the existing integrity/replay checks and treat `is_primary` as an application-level source-role assertion under the current process/storage trust boundary, not an authenticated attestation. Before production trust is elevated, define and approve: (1) least-privilege writer/reader DB roles with UPDATE/DELETE denied to runtime roles and separately controlled migration/admin access; (2) protected append-only audit/backup controls; and, if snapshots cross a process or organizational trust boundary, (3) a signed ingestion envelope or HMAC/signature key held outside the writable database, binding producer identity, adapter/version, source identity, exact evidence payload and timestamp. Verify key rotation, revocation, replay protection and recovery procedures before activation.
- This is a documented security limitation, not a code-level fix. No schema/migration, database/Neon access, role change, key generation, signature implementation, scoring activation, publisher/gateway change, live post, commit, push, merge or deployment. Module 14 remains fail-closed; B-SCORE-01 remains OPEN; project PARTIAL — NOT PRODUCTION-READY.

## 2026-11-22 continuation — derived announcement metadata cannot inherit primary status

- Audited each remaining `is_primary=True` producer at claim granularity. The announcement adapter correctly preserves Binance publisher assertions for the original `announcement.title`, `announcement.body` and `announcement.event_type` fields. However, it copied the same primary flag into two locally derived records: `announcement.freshness` (computed from published/updated/observed timestamps) and `announcement.asset_id` (resolved by the importer's local parenthesized-ticker-to-CoinGecko candidate map).
- This incorrectly represented local calculations/identity resolution as if Binance itself had asserted those derived values. Changed only those two records to `is_primary=False`; original announcement content assertions remain primary and attributed to Binance. This does not change their accepted/unverified/stale status, asset matching, freshness calculation, source lineage or source hash semantics.
- TDD RED added assertions to the existing adapter contract test and reproduced the inherited `is_primary=True` on the derived freshness record. GREEN changed the adapter to explicitly clear primary status for both derived record types. Focused verification including announcement importer tests: **10 passed, 0 failed**; `compileall -q layer1 tests main.py` and `git diff --check` passed.
- Remaining primary producers were reviewed by scope: Binance Spot exchangeInfo is primary only for Binance's own active pair/Spot permission assertion, with the expected base ticker bound at the adapter and the upstream canonical asset mapping still a separate prerequisite; local publication history is primary only for the local ledger's own bounded latest-200-post assertion, not for Binance platform-wide history; an individual Module 9 observation is primary only when the Module 9 validation record is ACCEPTED and matches exact observation, asset, mapping, network and provider IDs. Derived Module 9 transfer summaries and market observations remain non-primary.
- This is a narrow source-role correction, not cryptographic producer authentication. The worker CMS source trust boundary, actual deployed database grants and external source authenticity remain unverified. No database/Neon access, provider calls, migrations, scoring activation, publisher/gateway change, live post, commit, push, merge or deployment. B-SCORE-01 remains OPEN; runtime remains fail-closed; project PARTIAL — NOT PRODUCTION-READY.

## 2026-11-22 continuation — Module 9 observation acceptance and mapping provenance boundary

### Confirmed code findings

- `OnChainIntelligenceEngine.validate()` performs substantial deterministic checks: current Binance eligibility metadata, canonical asset/symbol equality, configured network/chain identity, mapping shape, approved provider label, block/transaction identifier format, chain-specific finality marker, timezone-aware timestamps and configured freshness. Worker paths add provider-page scope/range checks, finalized-height/header checks, transaction-position checks, and atomic page/checkpoint persistence.
- Those checks establish consistency of the objects supplied to the validator. The `OnChainObservation` contract does not carry the original provider response, a canonical raw-response hash, provider request/response ID, or a signed provider attestation. `endpoint_id`, `provider`, `finality_reference`, block hash and transaction hash are ordinary caller-supplied fields. The workers do parse provider responses and perform chain-specific checks, but the acceptance record itself does not retain a verifiable link back to those exact response bytes.
- `OnChainValidationResult` is a public frozen dataclass with no unforgeable validation receipt. `EvidenceVerificationEngine.evidence_from_onchain_observation()` marks evidence `ACCEPTED`/primary when the supplied result says `ACCEPTED` and five identity fields match. It does not rerun validation or prove the result was emitted by `OnChainIntelligenceEngine`. Existing tests construct an `ACCEPTED` result directly and pass it to this adapter; therefore a caller able to invoke the adapter can manufacture a matching result without executing the validator. This is an acceptance-authenticity gap, not merely a missing comparison field.
- `OnChainStore.save_verified()` and `PostgresOnChainStore.save_verified()` are safer persistence boundaries because they rerun `self.engine.validate(eligibility, mapping, observation)` before writing. However, the SQLite/PostgreSQL read paths return stored `validation_json` based on its status and do not cryptographically authenticate the original provider response or stored validation. Database write authorization and tamper protection remain separate trust prerequisites.
- Mapping validation is also structurally weaker than its name implies. `_validate_mapping()` checks `mapping_status == VERIFIED`, an allowlisted `source_type`, an HTTPS `source_url`, field shape, network/chain consistency, representation and timestamp syntax. It does not fetch or inspect the cited official source, retain a source-document excerpt/hash, prove the exact contract/mint/issuer/decimals against that source, bind a reviewer/verification actor, or impose a mapping-age policy. Consequently, `VERIFIED` plus `OFFICIAL_PROJECT`/`OFFICIAL_NETWORK` is an application assertion, not a reproducible source-backed mapping proof. Test fixtures use generic URLs such as `https://bitcoin.org/` and `https://example.org/token`, which demonstrates that the current validator does not establish page-level evidence.
- `main.py`'s current `EvidenceVerificationEngine.rebuild_from_store()` call passes `onchain_summary_refs` but does not pass `onchain_records`. Thus the main runtime ClaimRegistry path shown here does not currently feed individual Module 9 observations through this adapter; it attaches derived network summaries instead. Do not infer individual observation primary evidence is live in this runtime path from the adapter's existence.

### External contract cross-check

- Binance documents `/api/v3/exchangeInfo` as current exchange trading rules and symbol information, including `baseAsset`, `quoteAsset`, `status`, `isSpotTradingAllowed` and `permissionSets`. The implementation's active-pair/permission checks are aligned with this narrow purpose. Binance's endpoint does not prove that an arbitrary CoinGecko ID or on-chain contract is the same asset; the separate CoinGecko-to-Binance identity proof is still needed. Official reference: https://developers.binance.info/en/docs/catalog/core-trading-spot-trading/api/rest-api/general
- CoinGecko's official client schema exposes ticker fields including `coin_id`, `is_stale`, `is_anomaly`, `last_fetch_at`, `market.identifier`, `base`, `target` and `timestamp`. The resolver checks exact CoinGecko coin ID, Binance exchange identifier, base/quote, unique exact row, stale/anomaly flags and freshness. This is a useful cross-provider identity signal, but it is still CoinGecko-served ticker metadata, not an issuer-signed token contract registry or proof of a chain deployment. Reference: https://github.com/coingecko/coingecko-typescript/blob/main/src/resources/coins/tickers.ts
- Binance's official docs explain `permissionSets` as grouped permissions with AND/OR semantics; the code correctly checks that at least one group contains `SPOT`, in addition to `TRADING` and `isSpotTradingAllowed`. Reference: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md

### Disposition / required production controls

1. Do not treat a caller-constructed `OnChainValidationResult(status="ACCEPTED", ...)` as an authenticated receipt. Before primary evidence use, redesign the boundary so evidence conversion consumes a trusted validation service/receipt that is bound to a canonical observation fingerprint and the exact mapping/eligibility snapshot, with an explicit trust boundary. A Python-only private marker is not cryptographic authentication; if records cross process/storage boundaries, use a signed/HMAC envelope with a protected key and replay/rotation/revocation controls.
2. Extend the on-chain observation provenance contract to bind provider identity, network, method/endpoint, request scope/range, response identity, exact raw or canonical response hash, parser/adapter version, retrieval timestamp, and the exact transaction/block/header/finality facts used. Preserve privacy and avoid storing API credentials/headers. Verify the hash from retained immutable material or a signed provider envelope; a hash with no retained source bytes is only a correlation value.
3. Replace caller-supplied mapping `VERIFIED` labels with an auditable mapping-verification record: exact official source URL/document or registry entry, retrieval/verification timestamp, source payload/projection hash and hash semantics, exact contract/mint or issuer/currency, network/chain, decimals/token standard, representation, verifier identity/review, and expiry/revalidation policy. Unknown, stale, conflicting or unsupported mapping proof must fail closed.
4. Add adversarial tests: fabricated accepted result; mismatched validation payload; altered provider response with same asserted IDs; forged mapping status/source URL; contract/decimals mismatch; stale mapping; tampered persisted validation. Test SQLite and PostgreSQL paths separately; PostgreSQL tests remain DSN-gated.
5. Decide explicitly whether Module 9 individual observations should be included in the main ClaimRegistry runtime path. Current inspected `main.py` call only passes derived summaries; do not silently treat the standalone adapter as wired into production.

No code, migration, DB/Neon, key, publisher, gateway, scoring-policy, runtime-activation, commit, push, merge or deployment change was made in this audit. This section records verified limitations and prerequisites only. B-SCORE-01 remains OPEN; Module 14 remains fail-closed; project remains PARTIAL — NOT PRODUCTION-READY.

## 2026-11-23 continuation — explicit market/trend hash-kind provenance

### Finding and correction
- The prior adapter assigned `CANONICAL_PARSED_PROVIDER_JSON_SHA256` whenever a `MarketObservation` carried any valid-looking digest, regardless of how the caller obtained it. The trend adapter inferred the same kind from source-name strings. Both were overclaims: provider labels are caller-controlled and a 64-hex digest establishes format, not what bytes/object were hashed.
- `MarketObservation` now carries `data_hash_kind`; `TrendSignal` carries `content_hash_kind`. Both default to `UNSPECIFIED`, enforce the shared hash-kind allowlist, and reject a non-UNSPECIFIED kind when the corresponding digest is absent. Legacy JSON records without the fields remain readable as `UNSPECIFIED`.
- `MarketDataIntelligenceEngine.fetch_binance_24h()` and `.normalize_coingecko_market()` explicitly declare `CANONICAL_PARSED_PROVIDER_JSON_SHA256` because each computes SHA-256 over the canonical JSON serialization of the parsed provider payload. HotSearch's CoinGecko Trending producer declares the same kind for its parsed `item`; market-gainer/volume signals inherit it only when the originating market item hash is present. The CoinGecko Trending serialization rejects non-finite JSON values (`allow_nan=False`).
- `EvidenceVerificationEngine` now preserves the explicit kind supplied by the source record. It does not infer semantics from `provider`, `source`, or the presence of a digest. Legacy/unclassified non-empty hashes remain available for correlation but cannot satisfy the v4 typed-hash contract.
- SQLite serialization and the PostgreSQL `_market`/`_trend` JSON decoders were exercised locally. Legacy payloads missing the new fields default to `UNSPECIFIED`; typed records retain their kind. No database connection was opened.

### Schema/version edge cases
- Both `validate_factor_claim_support()` and `resolve_factor_source_provenance()` now require registry `schema_version` to be an exact integer 1 or 2; Python booleans and floats are rejected even where equality would otherwise match an integer.
- `resolve_factor_source_provenance()` now requires `hash_contract_version` to be an exact integer 3 or 4. Boolean, float and unsupported versions fail closed.

### Verification and limits
- TDD RED reproduced incorrect canonical-kind inference for arbitrary market/trend hashes and acceptance of bool/float registry schema versions; the new regression cases pass after correction.
- Combined local batch: **293 passed, 0 failed, 2 skipped**; compileall and `git diff --check` passed. A temporary import-only Pillow shim was used only because the RDC environment lacks Pillow; no image generation or image processing was exercised.
- `TEST_POSTGRES_DSN` is not configured; PostgreSQL end-to-end save/load/tamper/fresh-process tests remain skipped. No Neon/production database access, migration, provider call, score activation or publication occurred.
- This corrects hash-semantics attribution and structural type validation; it does not authenticate the producer, verify retained preimage bytes, establish source authority, or prove truth/independence. Module 14 remains fail-closed and production acceptance remains OPEN.
