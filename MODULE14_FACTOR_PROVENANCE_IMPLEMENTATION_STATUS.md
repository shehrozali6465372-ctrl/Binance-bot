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
