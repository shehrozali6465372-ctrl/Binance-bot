# Module 9 — Asset Mapping Source Matrix Review

**Date:** 2026-11-26
**Finding:** AUD-ONCHAIN-002 (HIGH / OPEN)
**Status:** REVIEW REPORT FOR OWNER APPROVAL — NOT AN IMPLEMENTATION AUTHORIZATION
**Reviewed scope:** Bitcoin mainnet, Ethereum mainnet, BNB Smart Chain mainnet, Solana mainnet-beta, XRPL mainnet; source authority, exact identity evidence, source class, registries, project-domain association, and compatibility with the current data model.

## 1. Executive decision

The approved authority boundary is sound, but it is not yet a complete implementable source policy. Official network documentation can establish network identity and native-asset protocol facts. It cannot establish that an arbitrary token contract, mint, or issued asset belongs to a named project. Non-native asset identity therefore needs (a) project-controlled assertion, (b) independent on-chain state verification, and (c) a documented domain-to-project association decision.

**Recommended policy:**

1. Use network documentation/client consensus parameters only for network identity and native asset semantics.
2. Use the exact on-chain identifier as the canonical token key: EVM contract address + chain ID; Solana mint + cluster genesis hash + token program; XRPL trustline token issuer + currency; XRPL MPT issuance ID as a separate identity type.
3. Require a project-controlled source to assert that exact identifier belongs to the project. Independently verify the relevant on-chain state through a trusted read-only node/provider. These prove different things and must not substitute for each other.
4. Treat third-party registries as corroboration/discovery, not issuer authority, unless a separate registry-specific trust review explicitly grants stronger authority.
5. Keep asset eligibility on Binance, market identity (CoinGecko), and chain identity as separate evidence claims.
6. Do not support an asset family in production until its identity and precision model are representable and tested without lossy coercion.

## 2. Network/source matrix — recommended candidate sources

The domains below are candidate official documentation/code locations for owner review. This table does **not** create an allowlist. A host may only become trusted after exact path/API contract, retrieval behavior, ownership, and version-pinning are approved.

| Network / asset class | Network/native identity source candidate | Non-native asset identity | Independent chain-state evidence | Review outcome |
|---|---|---|---|---|
| Bitcoin mainnet / BTC | Bitcoin Core `src/kernel/chainparams.cpp` mainnet parameters, including chain type, default P2P port, and genesis hash; Bitcoin Developer Guide glossary for mainnet terminology. | Not applicable to BTC native. Do not treat BTC as an issued token. | Bitcoin Core-compatible chain query: `getblockchaininfo` (`chain=main`) plus genesis/block-header checks. Alchemy REST data is provider evidence for the current worker, not issuer authority. | Accept as candidate for network/native identity after pinning a reviewed Bitcoin Core release/commit and exact file path. |
| Ethereum mainnet / ETH | ethereum.org Networks page for conceptual network documentation; EIP-155 for chain-ID replay-protection semantics; independently verify chain ID 1 and genesis/checkpoint against a trusted node. | Project-controlled official-domain statement must identify exact ERC-20 contract on chain ID 1. | Read-only `eth_chainId`, `eth_getCode`, and `eth_call` for supported contract fields (including `decimals()` where implemented); compare exact address and chain ID. | Candidate. ERC-20 standard docs do not prove project ownership or require `decimals()` to exist. |
| BNB Smart Chain mainnet / BNB | Official BNB Chain wallet configuration and JSON-RPC endpoint docs specify Mainnet chain ID 56 and native BNB. | Project-controlled statement must identify exact BEP-20 contract on chain ID 56. | Read-only chain ID, contract bytecode, and supported contract state using a trusted BSC node/provider. | Candidate. Official BNB docs prove network config, not token issuer identity. |
| Solana mainnet-beta / SOL | Solana cluster docs; `getGenesisHash` to bind the RPC connection to the intended cluster. | Project-controlled statement must identify exact mint and token program (legacy SPL Token or Token-2022). | Read mint account at finalized commitment; verify account owner/program, initialized state, decimals, mint/freeze authorities and supported extensions as applicable. | Candidate. Public Solana RPC is rate-limited and explicitly not intended for production applications; use trusted/private provider for production verification. |
| XRPL mainnet / XRP | XRPL protocol docs for currency formats and XRP's native/no-issuer semantics; validate the network using trusted validated-ledger evidence. | Trust-line token: project-controlled assertion for exact issuer + currency. MPT: distinct issuance ID and issuer, not issuer+currency alias. | Read validated ledger objects and exact issued-asset/MPT issuance fields. Verify issuer account, currency or issuance ID and applicable flags/scale. | Candidate for XRP and trust-line tokens. MPT requires a model/worker change before support. |

### Primary source references reviewed

- Bitcoin Core mainnet chain parameters: https://github.com/bitcoin/bitcoin/blob/master/src/kernel/chainparams.cpp (mutable branch; production policy must pin a release/commit and file digest).
- Bitcoin Core `getblockchaininfo`: https://bitcoincore.org/en/doc/23.0.0/rpc/blockchain/getblockchaininfo/ .
- Bitcoin Developer Guide glossary: https://developer.bitcoin.org/glossary.html .
- Ethereum network documentation: https://ethereum.org/developers/docs/networks/ .
- EIP-155: https://eips.ethereum.org/EIPS/eip-155 .
- ERC-20: https://eips.ethereum.org/EIPS/eip-20 .
- BNB Chain wallet configuration: https://docs.bnbchain.org/bnb-smart-chain/developers/wallet-configuration/ .
- BNB Chain JSON-RPC endpoints: https://docs.bnbchain.org/bnb-smart-chain/developers/json_rpc/json-rpc-endpoint/ .
- Solana clusters: https://solana.com/docs/references/clusters .
- Solana `getGenesisHash`: https://solana.com/docs/rpc/http/getgenesishash .
- Solana mint account and decimals: https://solana.com/docs/tokens/basics/create-mint .
- XRPL currency formats: https://xrpl.org/docs/references/protocol/data-types/currency-formats .
- XRPL fungible tokens: https://xrpl.org/docs/concepts/tokens/fungible-tokens .
- XRPL MPT: https://xrpl.org/docs/concepts/tokens/fungible-tokens/multi-purpose-tokens .
- XRPL MPT issuance fields: https://xrpl.org/docs/references/protocol/transactions/types/mptokenissuancecreate .

## 3. Registry assessment

| Registry | What it can usefully attest | What it does not prove | Recommendation |
|---|---|---|---|
| Trust Wallet Assets | Curated token metadata and wallet display metadata; its repository has automated validation and maintainer review. | The repository explicitly says inclusion does not mean Trust Wallet is in direct partnership with every project. It is community-maintained and accepts submissions subject to review. | Optional independent corroborator only; never issuer proof. Sources: https://github.com/trustwallet/assets and https://developer.trustwallet.com/listing-new-assets/requirements . |
| ethereum-lists/chains / chainid.network | EVM chain metadata such as chain ID, native currency, RPC and explorer references. | It is a community-maintained chain metadata repository, not Ethereum Foundation-issued proof and not a token issuer registry. | Candidate secondary cross-check for EVM chain configuration only; do not use for token identity. Source: https://github.com/ethereum-lists/chains . |
| Legacy Solana Token List (`solana-labs/token-list`) | Historical token metadata format. | Repository is archived/read-only and explicitly EOL. | Reject as a current authoritative registry. Source: https://github.com/solana-labs/token-list . |
| Block explorers | Public visibility into chain state and contract/mint/issuer data. | Explorer labels, token logos, verified-source badges or project descriptions are not independently sufficient proof of issuer/domain control. | Use as an investigation interface only; production verifier should query chain state through a trusted provider and retain raw proof. |
| CoinGecko | Market asset identity, market data and external asset metadata. | CoinGecko asset ID/ticker is not proof of chain contract ownership or Binance listing eligibility. | Keep as a separate identity cross-reference, not an authoritative on-chain mapping source. |

## 4. Important technical incompatibilities found in the current implementation

These are not theoretical policy details; they affect whether the existing schema can faithfully represent all five networks.

### 4.1 XRPL MPT is not representable by the current mapping identity

Current `OnChainAssetMapping` stores XRPL issued assets as `issuer_address + issued_currency` and requires `token_standard == XRPL_ISSUED_CURRENCY`. XRPL MPTs have a distinct `MPTokenIssuanceID` (192-bit identifier) and are not identified by issuer+currency. XRPL documentation also defines `AssetScale` separately. The current model has no MPT issuance ID or asset-scale field, and the current XRPL worker/normalizer is for issued-currency Payments.

**Recommendation:** explicitly scope initial XRPL support to XRP native + trust-line issued currencies. Mark MPT as unsupported/unverified until a separate identity variant, amount precision, issuance-state reader and worker path are designed and tested. Do not squeeze MPT IDs into `issued_currency`.

### 4.2 XRPL trust-line token precision is not a conventional fixed decimals field

XRPL issued-currency values use a 15-significant-digit mantissa/exponent representation. MPTs use integer units and optional `AssetScale`. XRP itself is denominated in drops (1 XRP = 1,000,000 drops). One generic `decimals` integer is therefore not a faithful precision model for all XRPL asset classes.

**Recommendation:** use a typed precision model (for example `EVM_DECIMALS`, `SOLANA_MINT_DECIMALS`, `XRPL_SIGNIFICANT_DIGITS`, `XRPL_MPT_ASSET_SCALE`, `NATIVE_BASE_UNITS`) or keep unsupported classes excluded. Do not infer or copy decimals from project web pages.

### 4.3 ERC-20 `decimals()` is optional

EIP-20 explicitly marks `decimals()` optional. A verifier cannot assume every ERC-20 contract exposes it. If absent, the mapping must not invent decimals from a website, ticker, registry or explorer display.

**Recommendation:** distinguish on-chain raw-unit ingestion from display precision. For assets whose decimals cannot be independently verified, fail closed for human-unit aggregation or store raw units without converting them. A project claim may corroborate expected precision but cannot make a missing contract method exist.

### 4.4 Solana token-program scope must be explicit

The current Solana transfer normalizer is documented as supporting the base SPL Token Program only. Solana now has Token-2022 and token extensions. A mint address alone does not tell the verifier which supported parser/semantics apply.

**Recommendation:** initial policy should accept only the legacy SPL Token Program until Token-2022 support is separately audited. Verify the mint account's owning token program and reject unsupported program IDs/extensions rather than accepting any non-empty `token_standard` string.

### 4.5 Bitcoin scope should remain native BTC only for this worker set

The current Bitcoin path is UTXO/address-history and transaction-output based. It does not implement a general token protocol verifier for inscriptions, Runes, or other overlays.

**Recommendation:** explicitly limit the current Bitcoin mapping to native BTC. Do not represent protocol-layer assets as generic Bitcoin token contracts without a separate protocol-specific parser and provenance contract.

### 4.6 EVM project claims and on-chain state are separate facts

A project website can assert "our token is contract X"; chain RPC can prove that code exists at X and report contract state. Neither alone proves both facts. Also, EIP-20's `symbol`, `name`, and `decimals` are optional, so metadata fields cannot be treated as guaranteed standard outputs.

**Recommendation:** require both project-domain assertion and independent chain-state checks for contract existence, chain identity, decimals if available, and supported standard behavior. Compare exact values; do not accept symbol/ticker matching as identity.

## 5. Project-domain association: recommended approval process

A domain-control challenge proves control of a DNS zone or HTTPS origin; it does **not**, by itself, prove that the domain belongs to the claimed token issuer or project. Use two distinct approvals:

1. **Association evidence:** record why the domain is attributable to the project (for example, cross-link from a previously authenticated project channel, legal issuer documentation, or a cryptographically signed statement from a known project-controlled key). DNS TXT/HTTPS challenge can prove current domain control but is only one part of this evidence.
2. **Policy approval:** a named Mapping Policy Owner/reviewer accepts the association, exact network and exact asset identifier. The record includes reviewer identity, evidence references, approval time, policy version, expiry/revalidation and revocation status.

**Recommended authority:** the project owner (you) is the initial Mapping Policy Owner and approves the first domain association for each project. You may later delegate to named reviewers, but delegation must be explicit, scoped, revocable and audited. For high-risk assets or disputed ownership, require a second independent reviewer. No reviewer identity or key should be hard-coded before the owner confirms it.

Domain association must be scoped to `(project_id, normalized_domain, network_id, asset_identifier)` rather than granting a domain blanket authority over all tokens or all chains. Subdomains should not inherit trust automatically. Rebrands, domain transfers, compromised sites and issuer-key rotations require revocation/supersession records.

## 6. Recommended implementation policy after owner approval

1. **Versioned source policy:** source class + exact origin + exact path/API contract + supported network + asset class + parser/canonicalization version. Pin mutable GitHub sources to immutable commit SHA/release and digest.
2. **Typed asset identity:** separate native, EVM contract, Solana mint, XRPL trustline and XRPL MPT identities. No generic string field that allows cross-family confusion.
3. **Two independent attestations:** project/domain assertion and chain-state observation. Persist both evidence digests, retrieval time, finality/ledger reference, verifier and policy version.
4. **No URL-only verification:** source URL and a caller-provided `VERIFIED` label never establish authority. Retrieve the exact approved resource under SSRF-safe transport, disable redirects by default, and verify content/fields.
5. **Source-specific expiry:** network docs/configuration, project-domain association, project token assertion, and registry records need separate revalidation schedules. Do not assign a single TTL. Expiry must be checked on every store read/worker/aggregation/evidence boundary.
6. **Conflict handling:** if project sources disagree with chain state, a second project source, or a superseding contract, mark mapping `CONFLICTED`/`UNVERIFIED`; never choose by recency alone.
7. **Verifier trust:** use an application signing key held in an approved secret manager/KMS, with key ID, rotation, revocation and historical verification semantics. The signed receipt attests to the application's review; it is not a provider-origin signature.
8. **Database parity:** implement SQLite and PostgreSQL semantics identically and test close/reopen, expiry, revocation, concurrency and stale-reader behavior against disposable PostgreSQL before closing the finding.

## 7. Required owner decisions (approval checklist)

The following are proposed defaults for owner review, not decisions already made:

- [ ] Approve the candidate network documentation/code sources in Section 2, including pinning Bitcoin Core to a reviewed release/commit.
- [ ] Confirm the initial supported asset scope: BTC native only; ETH/BNB ERC-20/BEP-20 contracts; Solana legacy SPL Token only; XRPL XRP + trust-line issued currencies; XRPL MPT excluded until schema/worker support.
- [ ] Approve the typed precision handling recommendation, especially XRPL trustline significant-digit semantics and MPT AssetScale exclusion.
- [ ] Confirm you are the initial Mapping Policy Owner for project-domain associations, with delegation only by explicit recorded approval.
- [ ] Approve Trust Wallet Assets as optional corroboration only; ethereum-lists as EVM network metadata cross-check only; reject archived Solana token-list as a current registry.
- [ ] Set source-specific freshness/revalidation periods after reviewing source update cadence and asset risk; do not use arbitrary defaults.
- [ ] Decide whether project-controlled assertion plus independent chain-state verification is sufficient, or whether a second independent issuer/registry source is mandatory for selected asset classes.
- [ ] Approve verifier identity and signing-key custody/rotation/revocation design before implementation.

## 8. Current code facts and test implications

The current `layer1/onchain.py` `_validate_mapping()` checks allowed source labels and basic HTTPS URL syntax, but does not enforce exact source hosts/paths, fetch or parse the source, bind extracted fields to the mapping identity, verify project-domain association, or expire mappings. It rejects timestamps more than five minutes in the future but has no maximum age. SQLite `list_verified_mappings()` reuses this validator; this does not create source authenticity or freshness.

The test fixtures currently use generic URLs such as `https://bitcoin.org/`, `https://example.org/token`, `https://solana.com`, and `https://xrpl.org` with `OFFICIAL_PROJECT` or `OFFICIAL_NETWORK` labels. These must remain explicitly synthetic/test-only; their labels must not be mistaken for production source approvals.

No code behavior was changed during this review. No allowlist, TTL, verifier key, domain association or production source was added. No provider request, production database, migration, secret read, Binance Square publication, deployment, staging, commit, push or merge occurred.

## 9. Recommendation / requested owner disposition

**Recommendation:** approve the scoped source matrix and compatibility exclusions in Sections 2–7 as the implementation baseline, with the explicit limitations above. If any proposed asset family or trust source is not approved, keep it unsupported and fail closed. Do not mark AUD-ONCHAIN-002 closed until the source retrieval/verifier/read-path/expiry implementation and SQLite + disposable PostgreSQL acceptance pass.

**Finding status remains HIGH / OPEN. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.**
