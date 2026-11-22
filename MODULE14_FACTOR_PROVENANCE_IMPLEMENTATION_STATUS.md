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
- Local focused run: 36 tests passed, 1 PostgreSQL DSN-gated test skipped before the final additional cases were added. A final full suite and CI run are still required.

## Explicit limitations

The validator does not establish that source IDs exist, payload hashes match actual payload bytes, sources are authentic/independent/authoritative, claims are supported, or numeric values are correctly derived. It does not validate approved rubric allowlists, source-specific freshness rules, human editorial labels, semantic novelty, or risk scoring. These require factor-specific logic and real historical evidence.

## Unchanged / not authorized by this implementation

- No changes to `OpportunityEvaluationEngine`, its six-factor interface, `main.py`, scheduled runtime or factor provider integrations.
- No policy weights, thresholds, floors, or factor values selected or activated.
- Runtime remains `factors=None`, `policy=None`; fail-closed DEFER.
- No database schema changes or migrations, production DB reads, Neon wake, live provider requests, publisher/gateway changes, or real posts.
- B-SCORE-01 remains OPEN. Project remains PARTIAL — NOT PRODUCTION-READY.

## Next

1. Run the full local unittest suite.
2. Verify both isolated PostgreSQL CI jobs on the new commit.
3. Review factor-specific semantic validation and source-reference resolution requirements.
4. Only after empirical historical-data inventory and separate approval, design factor derivation and shadow evaluation. Do not activate scoring from schema tests alone.

[executed on device: localhost (bd830869-fbae-4825-ae7b-5044d6161090)]
