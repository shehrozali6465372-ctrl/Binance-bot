# Module 14 Factor Provenance — Code-Level Implementation Review

Date: 2026-11-22  
Review basis: read-only inspection of the continuation worktree at `9899b9d5a01be342f8f64414b1a740257830935c`.

## Scope and safety
Reviewed `layer1/opportunity.py`, `layer1/publication_postgres.py`, `layer1/publication_runtime.py`, `layer1/migrations/publication_postgresql/0001_publication_storage.sql`, scheduled Module 14 call in `main.py`, and relevant tests. Read-only review only: no application code, tests, schema, DB rows, credentials, providers, runtime, publisher, gateway, CI, or publishing behavior changed.

## Current implementation facts
- Engine accepts six numeric factor values (0–100) and optional policy.
- Immutable snapshot has exactly two top-level keys: `policy` and `inputs`; it stores factor numbers/invalid markers, factor keys, gate inputs, asset ID, and policy weights/thresholds/version.
- `_decision_digest()` hashes the outcome plus decoded policy/input snapshot but does not validate a factor-provenance schema.
- SQLite stores JSON as TEXT and compares the stored string on idempotent replay.
- PostgreSQL stores JSONB; save compares decoded JSON values for an existing ID.
- PostgreSQL load returns the stored decision/snapshot but does not independently recompute and verify the decision digest.
- PostgreSQL validator checks basic fields, top-level keys, and JSON serializability; no factor-level provenance, status/value invariant, or schema-version validation.
- PostgreSQL migration runner verifies applied migration SHA-256 checksums. Never edit applied migration 0001; future DDL must be additive in a new numbered migration.
- Existing tests include generic legacy snapshots such as `{"policy":{"version":"..."}, "inputs":{"factor":0.9}}`; preserve compatibility and digest replay.
- Scheduled runtime still passes `factors=None`, `policy=None`; fail-closed DEFER must remain.

## Confirmed gaps
1. No versioned snapshot schema distinguishing legacy records from strict provenance-complete decisions.
2. A numeric factor can be accepted without evidence references, source timestamps, measurement windows, transformations/baseline versions, dependency groups, or quality flags.
3. No READY/MISSING/STALE/CONFLICTED/UNVERIFIED/NOT_APPLICABLE assessment status or enforced status/value invariant.
4. SQLite/PostgreSQL have different persistence comparison paths and need shared validation/canonicalization.
5. PostgreSQL read path does not independently verify the stored decision digest.
6. Legacy rows and test fixtures require explicit backward compatibility; do not rewrite or rehash them.
7. Existing migration checksum rules require future schema changes in a new additive migration, never by editing migration 0001.

## Recommended implementation design (not implemented)
1. Define a pure shared validator with explicit legacy/new schema versions.
2. Preserve deterministic legacy digest reproduction; never rewrite historical rows.
3. Add a new snapshot version containing all six factor assessments, rubric/implementation versions, statuses, and full subfeature provenance.
4. Enforce: only READY carries a numeric value; all other statuses carry null and a machine-readable reason; READY requires factor-specific evidence/freshness checks.
5. Validate exact asset identity, evidence/payload refs, provider IDs, publication/observation timestamps, measurement windows, units, transformations, baseline, dependency group, quality flags, and point-in-time cutoff.
6. Make SQLite save, PostgreSQL save/load, and digest use shared validators/canonicalization.
7. Add PostgreSQL read-time digest verification and deterministic replay checks.
8. Add a new numbered migration only if a demonstrated DB invariant requires DDL.
9. TDD cases: malformed schema, missing refs, READY without provenance, numeric value on non-READY, stale/future timestamps, wrong asset, source lineage duplication, invalid hashes, non-finite values, digest tampering, legacy replay, adapter parity, fresh-process replay, hard-gate dominance.
10. Keep factor derivation, scoring policy, and runtime activation separate. Provenance alone must never make a factor READY or permit PROCEED.

## Approval boundary
This is design only. It does not authorize runtime/application code, schema/migrations, production/Neon DB access, factor provider activation, weights/thresholds, or publisher/gateway/content-generation changes. Implementation requires explicit approval of scoped code changes; DB migration separately requires isolated test target and scope.

## Status
Code review complete for listed paths. Provenance implementation NOT STARTED. Runtime unchanged, `factors=None`, `policy=None`, fail-closed DEFER. B-SCORE-01 OPEN. Project PARTIAL — NOT PRODUCTION-READY.
