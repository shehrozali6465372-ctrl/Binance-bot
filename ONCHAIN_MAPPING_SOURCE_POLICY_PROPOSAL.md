# Module 9 Asset Mapping Source Policy — Approval Proposal

**Status:** PROPOSAL ONLY — NOT APPROVED, NOT IMPLEMENTED\
**Finding:** AUD-ONCHAIN-002 (HIGH / OPEN)\
**Prepared:** 2026-11-24\
**Scope:** Source authenticity, exact mapping identity, freshness/expiry, and persistence read enforcement for Module 9 asset mappings.

## 1. Verified current behavior

The current `OnChainIntelligenceEngine._validate_mapping()` in `layer1/onchain.py`:
- Accepts only the labels `OFFICIAL_PROJECT`, `OFFICIAL_NETWORK`, and `OFFICIAL_REGISTRY`, but does not bind any label to an approved host, path, network, or asset.
- Accepts any URL with `https` scheme and a non-empty network location. It does not verify the cited page or the exact contract/mint/issuer/currency/decimals.
- Parses `verified_at` and rejects timestamps more than five minutes in the future, but has no maximum age or expiry rule.
- Is reused by SQLite and PostgreSQL `list_verified_mappings()`; aggregation checks observation freshness separately and does not expire mapping attestations.

The test corpus demonstrates that these labels are not presently source-backed: BTC fixtures use `https://bitcoin.org/`; generic EVM fixtures use `https://example.org/token`; Solana/XRPL fixtures use generic project URLs. These are test fixtures, not approved production source policy.

The repository contains mapping-consuming workers and persistence interfaces, but no authoritative mapping-source ingestion/review service that retrieves a source document, proves its ownership, captures a content hash, and issues a verifier-bound mapping record.

## 2. Security objective

A mapping may be treated as VERIFIED only when a trusted verifier can reproduce the exact assertion:

`(asset_id, binance_symbol, network_id, chain_id, representation, contract/mint or issuer+currency, token_standard, decimals)`

from an approved source appropriate to that network and asset class, and can prove which source version was reviewed, by whom/which verifier, when, and under which policy version.

A source URL string or caller-supplied `VERIFIED` label is not proof. A valid HMAC over caller-supplied fields alone does not establish that the upstream page actually contained those fields.

## 3. Proposed source classes (semantics only; no host allowlist approved)

| Source class | Intended use | Required evidence |
|---|---|---|
| `OFFICIAL_PROJECT` | Issuer/project-controlled assertion for a token or issued asset | Explicitly verified project-domain ownership/association; exact network and contract/mint or XRPL issuer+currency; captured source content/projection hash; verifier record |
| `OFFICIAL_NETWORK` | Network-maintained canonical information, primarily native-asset/network identity | Exact network identity and native-asset semantics; source page/API contract tied to the network; captured source content/projection hash |
| `OFFICIAL_REGISTRY` | A registry with a documented maintainer, update process, and stable asset identity fields | Registry-specific schema/version/signature or retrieval evidence; exact asset/network/contract fields; captured source content/projection hash |

These classes must not be treated as interchangeable. A network documentation page that merely describes a standard does not prove that a particular token contract is the official contract. A block explorer can show on-chain state but is not, by itself, proof of issuer/project ownership. CoinGecko identity and Binance Spot eligibility are separate cross-provider assertions; neither alone proves the on-chain mapping.

## 4. Required mapping verification record

Before implementation, approve a versioned record containing at least:
- Stable mapping ID and exact identity tuple listed in Section 2.
- Source class, canonical HTTPS URL, normalized exact hostname, path rule, and source document/registry identifier.
- Source retrieval timestamp, source publication/version timestamp where available, verifier timestamp, and next revalidation/expiry timestamp.
- Canonicalized source projection (or immutable content-addressed evidence reference), SHA-256 digest, canonicalization version, and hash semantics.
- Exact extracted fields and field-to-source locations sufficient for independent reproduction.
- Verification actor/service identity, review outcome, policy version, and signed verifier receipt.
- Conflict state and supersession link when multiple sources disagree or a mapping changes.

Do not persist full secrets, authenticated URLs, or unnecessary personal data in the source evidence.

## 5. Host, URL, and retrieval controls proposed

- Exact normalized hostname allowlists; no wildcard or substring/suffix matching.
- Rules scoped by source class, network, and where necessary asset/issuer. Dynamic project domains require a separately reviewed project-domain association record; they must not be admitted merely because a mapping labels itself `OFFICIAL_PROJECT`.
- HTTPS only; reject URL user-info, unexpected ports, fragments, ambiguous host encodings, IP-literal hosts, and non-canonical paths unless a reviewed source contract explicitly requires an exception.
- No redirects for authenticated or trust-bearing retrieval. If public-source redirects are ever allowed, validate every hop against the same exact-origin policy and strip credentials.
- Apply SSRF controls at retrieval: resolve and reject loopback, private, link-local, multicast, reserved and metadata-service destinations; re-check DNS at connection time to reduce rebinding risk.
- Parse only documented source contracts. Validate the exact asset/network/contract/issuer/currency/decimals fields rather than trusting page titles or search snippets.

These are proposed controls. They are not yet implemented or tested.

## 6. Freshness and expiry policy — approval required

Do not introduce one universal TTL. The acceptable age depends on source class, network, token/issuer risk, source update cadence, and the operational cost of stale mappings. The policy owner must approve a maximum age/revalidation interval for each supported source-class/network combination, including:
- Native assets per network.
- EVM token contracts per supported EVM network.
- Solana mint addresses and token standards.
- XRPL issuer/currency pairs.
- Project-domain association records and registry versions.

At every trust boundary (initial verification, SQLite/PostgreSQL list/read, worker selection, aggregation, and final evidence issuance), expired or policy-version-obsolete mappings must become non-VERIFIED and must not be silently reused. A source outage must not extend an expiry window. Revalidation should be explicit and produce a new immutable verification record rather than rewriting history.

## 7. Required tests before closure

- Reject unrelated HTTPS hosts, deceptive suffix hosts, user-info URLs, unexpected ports, fragments, IP literals, malformed/encoded hosts, and disallowed paths.
- Accept only explicitly approved exact host/path/network/source-class combinations.
- Prove source payload hash and extracted fields bind to the exact mapping tuple.
- Reject mismatched contract, mint, issuer, currency, decimals, token standard, network, chain ID, and asset ID.
- Reject expired, future-dated, missing, malformed, and policy-version-obsolete records.
- Verify stale mappings are filtered consistently by SQLite and PostgreSQL read paths, all four workers, and aggregation.
- Verify source changes, revoked project-domain association, registry-version rollback, conflicting sources, and superseded mappings fail closed.
- Verify signed verifier receipts survive restart/key rotation but cannot be rebound to a different mapping tuple or source payload.
- Include dedicated disposable PostgreSQL acceptance for read-path expiry and concurrent mapping replacement; do not use production databases.

## 8. Owner decisions required before code changes

1. Approve the semantics of the three source classes, or provide corrected definitions.
2. Approve the authoritative source/host/path/contract evidence matrix for each supported network and asset class. Supply named owners/reviewers for project-domain association.
3. Approve source-specific maximum ages and revalidation cadence; do not choose arbitrary TTLs in code.
4. Decide whether each mapping requires one primary source plus independent corroboration, and define acceptable corroborators by asset class.
5. Approve the verifier identity/key custody and revocation/rotation model.
6. Confirm whether existing generic fixtures should remain test-only and be migrated to explicitly marked synthetic policy fixtures.

## 9. Current disposition

No host allowlist, source contract, mapping TTL, or verifier key was invented. No code, schema, database, provider, deployment, or publication behavior was changed by this proposal. Until the owner decisions above are approved and the verifier/read-path tests pass, keep **AUD-ONCHAIN-002 HIGH / OPEN** and do not treat `mapping_status=VERIFIED` as reproducible source-backed proof.

## 10. Owner approval record — source-class semantics only (26 November 2026)

**Approved:** The owner approved the three source-class definitions in Section 3:

- `OFFICIAL_PROJECT`: issuer/project-controlled assertion, with independently verified project-domain association and exact asset identity evidence.
- `OFFICIAL_NETWORK`: network-maintained canonical information, primarily for network/native-asset identity; not a substitute for issuer proof for arbitrary tokens.
- `OFFICIAL_REGISTRY`: a registry with a documented maintainer/update process and stable asset identity fields.

**Approval boundary:** This approval covers definitions/semantics only. It does **not** approve any hostname, URL path, source contract, network/asset matrix, project-domain association, TTL/revalidation interval, corroboration rule, verifier identity, signing key/custody model, or implementation. Those remain explicit owner decisions. No code or runtime trust behavior is authorized by this approval alone.

## 11. Owner approval record — five-network source-authority boundary (26 November 2026)

**Approved:** The owner approved the proposed source-authority boundary for the five currently supported networks: Bitcoin, Ethereum, BNB Smart Chain, Solana, and XRPL. Network-maintained documentation may establish network identity and native-asset facts. Non-native token identity requires project-controlled evidence for the exact token identity (including the applicable contract, mint, or issuer/currency tuple).

**Approval boundary:** This approves the authority distinction and evidence boundary only. It does not approve exact URLs, hostnames, paths, API/document contracts, registry entries, project-domain association records or approvers, source freshness/TTL, independent corroboration rules, verifier identity, key custody/rotation/revocation, or implementation. The Bitcoin documentation path and named project-domain association approvers remain unresolved. Do not admit any source host based only on this approval.
