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
