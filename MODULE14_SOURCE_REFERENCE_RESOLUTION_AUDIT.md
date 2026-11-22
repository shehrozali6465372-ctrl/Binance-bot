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
