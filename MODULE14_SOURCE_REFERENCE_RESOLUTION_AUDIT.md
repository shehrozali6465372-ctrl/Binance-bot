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
