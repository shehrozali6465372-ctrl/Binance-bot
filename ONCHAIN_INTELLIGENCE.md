# Module 9 — Blockchain & On-chain Intelligence

## Provider decision

Status: **User-selected providers; implementation remains draft. Live connectivity and production approval are pending.**

| Network | Provider | Selected plan | Main documented interface | Important limit |
|---|---|---|---|---|
| Bitcoin mainnet | Alchemy | Free | UTXO REST address history + Bitcoin JSON-RPC | Address-scoped; not a global wallet-discovery feed |
| Ethereum mainnet | Alchemy | Free | `alchemy_getAssetTransfers` + Ethereum JSON-RPC | Transfer API requires an exact contract or monitored address scope |
| Solana mainnet | Alchemy | Free | `getTransactionsForAddress` | Address/token-account scoped; full transaction pages up to 100 |
| BNB Smart Chain mainnet | Alchemy | Free | `eth_getLogs` + BNB JSON-RPC | Free-tier `eth_getLogs` range is at most 10 blocks per request |
| XRP Ledger mainnet | Chainstack | Developer Free | XRPL JSON-RPC `account_tx` | Account-scoped; history limited by provider's currently available ledger range |

Official provider facts checked on 2026-11-11:

- Alchemy Free plan publishes 30M compute units/month and 25 requests/second. Exact per-method availability and quota must still be verified with a working project API key.
- Documented Alchemy request costs: Ethereum `alchemy_getAssetTransfers` 120 CUs; BNB `eth_getLogs` 60 CUs; Solana `getTransactionsForAddress` 100 CUs.
- Alchemy's `eth_getLogs` documentation lists a 10-block maximum per request on the Free tier for BNB and several other chains.
- Chainstack XRPL Developer Free is listed at $0/month, 3M request units/month, 25 requests/second, one node and WebSockets.
- Chainstack's Oct 1, 2026 Extended Nodes article reports roughly 750,000–1,500,000 XRPL ledgers (about 33–66 days) for Global Nodes. An earlier Sep 16, 2026 setup guide says under six days. Those provider pages conflict; the adapter reads `complete_ledgers` at runtime and does not assume either duration. Full-history retention requires separately configured infrastructure.

## Implemented domain validation

`layer1/onchain.py` provides:

- Five-network allowlist and provider-to-network allowlist.
- Exact network family and chain-ID validation.
- Canonical CoinGecko asset ID, exact Binance symbol, native/token representation, decimals and HTTPS provenance requirements.
- Verified Binance Spot eligibility gate requiring upstream source, identity proof, proof timestamps/hash and exact eligible trading pairs. A manually supplied `ELIGIBLE` status is insufficient.
- Exact asset/mapping/network/provider matching; ticker-only and wrong-chain matches are rejected.
- Native assets cannot declare contracts or issuers. EVM/Solana token mappings require exact contract/mint and standard. XRPL issued assets require issuer plus issued-currency identity.
- Chain-specific finality: Bitcoin probabilistic confirmation threshold; Ethereum/BNB finalized headers; Solana finalized commitment; XRPL validated ledger.
- Mandatory, explicitly configured freshness thresholds. Missing policy returns `FRESHNESS_POLICY_NOT_CONFIGURED`; no guessed production threshold is applied.
- Additive SQLite persistence for accepted observations, with idempotent duplicate handling and conflicting-ID rejection.

## Implemented read-only data acquisition

`layer1/onchain_providers.py` includes the following methods:

| Network | Method | Returned data and safeguards |
|---|---|---|
| Bitcoin | Alchemy UTXO `GET /api/v2/address/{address}` | Address history, `details=txs`, page size <= 1,000. Confirmations are classified as `CONFIRMED`, `PENDING` or `ORPHANED`; confirmed records require block height/hash/time. Raw satoshi values are not converted to floats. |
| Ethereum | Alchemy `alchemy_getAssetTransfers` | Exact contract or monitored-address scope; fixed block range checked against finalized head; `pageKey` pagination; `maxCount` <= 1,000. Raw amount and decimals are normalized to integer base units; no floating-point value is used for amount. |
| BNB Smart Chain | Alchemy `eth_getLogs` | Exact token contract and ERC-20 Transfer topic; chain ID 56 checked; inclusive block range <= 10 on Free tier; range must not exceed `eth_getFinalizedHeader` with all validators (`verifiedValidatorNum=-3`). Decodes from/to and raw uint256; preserves `removed` reorg flag. |
| Solana | Alchemy `getTransactionsForAddress` | Address/token-account scope; full transaction page <= 100; finalized commitment; requests successful transactions and balance-changing token-account activity; validates signature, slot and full transaction metadata; preserves `paginationToken`. |
| XRP Ledger | Chainstack `account_tx` | Account scope; explicit fixed ledger range (no moving `-1` bounds); opaque marker pagination; response and each transaction must be validated; returned ledger bounds are checked. |

Transport validates JSON-RPC envelopes, normalizes HTTP 429/network errors without exposing endpoint credentials, and exposes no transaction-submission method. REST and JSON-RPC calls are read-only in these adapters.

## Important coverage limits

- Alchemy `alchemy_getAssetTransfers` is documented for Ethereum and supported L2s; BNB is intentionally queried with `eth_getLogs`, not the Ethereum Transfers API.
- Ethereum and BNB methods can scan a mapped token contract's transfers. Native ETH queries require a monitored address; native/internal categories cannot silently become global scans.
- Bitcoin address history and Solana `getTransactionsForAddress` are address-scoped. XRPL `account_tx` is also account-scoped. These methods do not discover every whale wallet across their networks.
- Complete network-wide whale discovery is therefore **not available** from the selected five methods alone. BTC/SOL/XRPL need an explicit monitored-wallet source or a separately evaluated indexing/discovery product before broad whale coverage can be claimed.
- XRPL markers are opaque and may expire after 10 minutes. A worker must consume a page sequence promptly and checkpoint stable ledger bounds; the marker is not a durable cursor.
- Provider pages are returned as typed/raw records. They are not yet durably checkpointed, persisted as normalized transfer events, or wired into candidate analysis.
- BNB removed logs and Bitcoin orphaned transactions are surfaced, but persistent reorg tombstones, canonical re-fetch/reconciliation and transaction/log uniqueness storage remain pending.
- No transfer value threshold, whale classification, exchange attribution, bridge deduplication or buy/sell intent inference is enabled.

## Open-source reuse review — 2026-11-11

The following public projects were inspected before extending the ingestion layer:

| Project | Verified repository facts | Reuse decision |
|---|---|---|
| [Fystack Multi-Chain Indexer](https://github.com/fystack/multichain-indexer) | Go; MIT; public and not archived; latest main commit observed as `9c0db2c17e4ef260917b3f1038304fa3014ebca2` (2026-11-09). README lists Ethereum, BNB, Bitcoin, Solana and XRP; Solana and XRP are marked Beta. Uses restart-safe KV progress, catch-up/manual/rescan workers, retries and reorg rollback. | Best multi-chain architecture reference, but not a drop-in dependency: Go plus its worker/KV/Redis/NATS/Postgres stack would duplicate this Python service. Its core use case is matching transactions to known deposit addresses. |
| [Chaindexing](https://github.com/chaindexing/chaindexing-rs) | Rust; Apache-2.0; public and not archived; EVM-focused. README documents canonical event identity, block-hash/parent-hash tracking, durable Postgres checkpoints, transactional cursor writes, reorg repair and outbox. | Strong EVM correctness reference, but not a drop-in dependency: Rust 1.91+ and EVM-only scope do not replace BTC/SOL/XRPL adapters. Adopt event identity, atomic checkpoint and tombstone concepts in the existing Python layer. |
| [thirdweb Insight](https://github.com/thirdweb-dev/insight) | Go; Apache-2.0; GitHub repository metadata marks it archived. | Rejected as a runtime dependency because it is archived. |

No third-party source code was copied or vendored in this change. The implementation below is an in-repository Python/SQLite adaptation of general persistence and recovery patterns; upstream licenses are recorded for traceability, not as a claim that upstream code is embedded.

## Durable ingestion persistence implemented

`layer1/onchain_ingestion.py` now provides:

- A normalized transfer-event record with exact raw integer amount strings, decimals, block and transaction identity, source scope, mapping identity, timestamps, provenance and canonical status.
- Durable per-scope checkpoints stored in SQLite.
- Atomic page commit: event inserts and checkpoint advancement happen in one `BEGIN IMMEDIATE` transaction. A crash or conflicting event payload rolls back both.
- Idempotent page replay for identical event identities and payloads; conflicting reuse of an identity is rejected.
- Composite event uniqueness across network, provider, scope and event ID.
- Reorg tombstones (`REORGED`) retained for audit and excluded from canonical-only reads.
- Canonical block reconciliation that marks stored events at a height as reorged when their block hash differs from a separately verified canonical block hash.
- An EVM `Transfer` log normalizer keyed by `transaction_hash:log_index`; provider `removed=true` is persisted as a reorg tombstone, never as an active transfer.

Important integration limits:
- This is a storage primitive, not yet a continuously running worker. Provider page fetch, normalization, commit and restart orchestration are not yet wired together.
- The EVM normalizer currently targets validated `eth_getLogs` Transfer logs (the existing BNB adapter path). The Ethereum Transfers API returns transfer summaries without a log index; it must not be assigned a fabricated log identity. Other network adapters still need chain-correct transfer extractors before their records can be persisted as transfer events.
- A stable checkpoint must include the fixed block/ledger range and provider scope. XRPL markers can expire; persist the fixed ledger window as the durable restart boundary and treat an expired marker as a reason to replay that bounded window.
- `reconcile_block` requires a verified canonical block hash supplied by the caller. It does not independently query a provider, choose a reorg depth, or prove finality.
- SQLite is appropriate for the current local/test foundation. Before concurrent production workers or deployment to managed Postgres, the schema and transaction semantics must be migrated and load-tested against the chosen production database.

## Not yet implemented / not yet verified

- No live Alchemy or Chainstack request has been made. The local process has no `ALCHEMY_API_KEY` or `CHAINSTACK_XRPL_ENDPOINT`; no provider endpoint/key has been configured in the repository or deployment.
- Alchemy connector authentication was invalid/expired (app listing returned HTTP 401); no app ID or API key could be retrieved through the connector.
- No production API account, paid plan, secret, or infrastructure has been created or modified.
- No token contract mappings have been populated. Native asset support in the model is not proof that any Binance Spot asset mapping is verified.
- Provider-specific freshness thresholds, finality policy and historical coverage must be calibrated using live read-only observations before candidate evidence is enabled.
- Module 7 scoring remains deferred. On-chain evidence is corroborative only and cannot authorize publication.

## Official method documentation

- Alchemy pricing: https://www.alchemy.com/pricing
- Bitcoin address history: https://www.alchemy.com/docs/chains/bitcoin/utxo-api-endpoints/utxo-api-endpoints/get-address
- Ethereum Transfers API: https://www.alchemy.com/docs/data/transfers-api/transfers-endpoints/alchemy-get-asset-transfers
- BNB `eth_getLogs` and free-tier block ranges: https://www.alchemy.com/docs/chains/bnb-smart-chain/bnb-smart-chain-api-endpoints/eth-get-logs
- Solana `getTransactionsForAddress`: https://www.alchemy.com/docs/chains/solana/solana-api-endpoints/get-transactions-for-address
- XRPL `account_tx`: https://xrpl.org/docs/references/http-websocket-apis/public-api-methods/account-methods/account_tx
- XRPL markers and pagination: https://xrpl.org/docs/references/http-websocket-apis/api-conventions/markers-and-pagination
- Chainstack XRPL Global Node history: https://chainstack.com/chainstack-extended-nodes-explained/

## Safety boundaries

- Only Binance Spot-eligible assets can enter on-chain candidate analysis.
- No ticker-only mapping, guessed contract, fake provider response, or fabricated metric.
- Unmapped, stale, unsupported or non-final data remains unavailable/unverified.
- Whale thresholds must be explicit system thresholds and do not prove buy/sell intent.
- No exchange inflow/outflow attribution without verified wallet labels and provenance.
- Addresses are pseudonymous; no real-world identity claims without reliable evidence.
- On-chain evidence is corroborative and cannot authorize publication.
- Never publish a real Binance Square post during tests or diagnostics.
