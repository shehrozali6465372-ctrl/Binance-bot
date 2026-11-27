# Module 9 — Blockchain & On-chain Intelligence

## Provider decision

Status: **User-selected providers; implementation remains draft. Live connectivity and production approval are pending.**

| Network | Provider | Selected plan | Main documented interface | Important limit |
|---|---|---|---|---|
| Bitcoin mainnet | Alchemy | Free | UTXO REST address history + Bitcoin JSON-RPC | Address-scoped; not a global wallet-discovery feed |
| Ethereum mainnet | Alchemy | Free | eth_getLogs for mapped ERC-20 Transfer events; alchemy_getAssetTransfers remains a scoped summary API | Free-tier eth_getLogs range is at most 10 blocks per request; worker verifies finalized head and canonical headers |
| Solana mainnet | Alchemy | Free | `getTransactionsForAddress` | Address/token-account scoped; full transaction pages up to 100 |
| BNB Smart Chain mainnet | Alchemy | Free | `eth_getLogs` + BNB JSON-RPC | Free-tier `eth_getLogs` range is at most 10 blocks per request |
| XRP Ledger mainnet | Chainstack | Developer Free | XRPL JSON-RPC `account_tx` + exact `ledger` header reads | Account-scoped; fixed validated-ledger ranges; history limited by provider's currently available ledger range |

Official provider facts checked on 2026-11-11:

- Alchemy Free plan publishes 30M compute units/month and 25 requests/second. Exact per-method availability and quota must still be verified with a working project API key.
- Documented Alchemy request costs: eth_getLogs 60 CUs; Ethereum alchemy_getAssetTransfers 120 CUs; Solana getTransactionsForAddress 100 CUs.
- Alchemy's current Ethereum eth_getLogs documentation lists a 10-block maximum per request on the Free tier. The implementation uses the same conservative 10-block bound on Ethereum and BNB; it does not infer paid-plan entitlements.
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
| Bitcoin | Alchemy UTXO GET /api/v2/address/{address} plus GET /api/v2/tx/{txid} | Address-scoped history with fixed block filters and pages <= 1,000; full transaction details expose vin/vout, txid, output index, decoded addresses and integer satoshi values. The output normalizer uses txid:vout identity; bounded worker and confirmation/reorg checkpointing remain pending. |
| Ethereum | Alchemy eth_getLogs for durable ingestion; alchemy_getAssetTransfers for scoped summaries | Exact mapped contract and ERC-20 Transfer topic; chain ID 1 checked; inclusive block range <= 10; range must not exceed the Ethereum finalized tag. Decodes provider-supplied transaction hash/log index, from/to and raw uint256. Canonical block headers are fetched independently by the worker. The summary API is not used to invent log indices. |
| BNB Smart Chain | Alchemy eth_getLogs | Exact token contract and ERC-20 Transfer topic; chain ID 56 checked; inclusive block range <= 10; range must not exceed eth_getFinalizedHeader with all validators (verifiedValidatorNum=-3). Decodes provider-supplied transaction hash/log index, from/to and raw uint256; preserves removed reorg flag. |
| Solana | Alchemy `getTransactionsForAddress` | Address/token-account scope; full transaction page <= 100; finalized commitment; requests successful transactions and balance-changing token-account activity; validates signature, slot and full transaction metadata; preserves `paginationToken`. |
| XRP Ledger | Chainstack `account_tx` + `ledger` | Account scope; explicit fixed ledger range (no moving `-1` bounds); opaque marker pagination; response and each transaction must be validated; exact validated ledger headers supply canonical hash and close time. |

Transport validates JSON-RPC envelopes, normalizes HTTP 429/network errors without exposing endpoint credentials, and exposes no transaction-submission method. REST and JSON-RPC calls are read-only in these adapters.

## Important coverage limits

- Alchemy `alchemy_getAssetTransfers` is documented for Ethereum and supported L2s; BNB is intentionally queried with `eth_getLogs`, not the Ethereum Transfers API.
- Ethereum and BNB methods can scan a mapped token contract's transfers. Native ETH queries require a monitored address; native/internal categories cannot silently become global scans.
- Bitcoin address history and Solana `getTransactionsForAddress` are address-scoped. XRPL `account_tx` is also account-scoped. These methods do not discover every whale wallet across their networks.
- Complete network-wide whale discovery is therefore **not available** from the selected five methods alone. BTC/SOL/XRPL need an explicit monitored-wallet source or a separately evaluated indexing/discovery product before broad whale coverage can be claimed.
- XRPL markers are opaque and may expire after 10 minutes. A worker must consume a page sequence promptly and checkpoint stable ledger bounds; the marker is not a durable cursor.
- Ethereum/BNB ERC-20 logs, address-seeded Bitcoin UTXO outputs, address-seeded Solana base SPL Token transfers and address-seeded XRPL issued-currency Payments now have callable bounded workers and durable page checkpoints. None of these events is wired into candidate analysis yet.
- Ethereum/BNB canonical block hashes, Bitcoin block hashes, Solana produced/skipped slots and XRPL ledger hashes are journaled and reconciled within configured lookback windows. Reorg recovery is bounded; no arbitrary-depth recovery is claimed.
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

## Bounded EVM ingestion worker implemented — 2026-11-11

layer1/onchain_evm_worker.py now orchestrates the existing mapping store, Alchemy read-only adapter, EVM Transfer normalizer and atomic ingestion store for **Ethereum mainnet and BNB Smart Chain ERC-20 contracts**.

Verified implementation behavior:
- Reads only mappings already persisted by OnChainStore.save_verified() and returned by list_verified_mappings() for the supported EVM network; mappings are revalidated against the configured chain ID and exact contract identity.
- Requires an explicit initial block for every mapping. No guessed genesis/start height is introduced.
- Reads the network-specific finalized height: Ethereum eth_getBlockByNumber("finalized"); BNB eth_getFinalizedHeader with all validators. Provider adapters check chain IDs 1 and 56 respectively.
- Scans no more than configured max_blocks_per_run; every eth_getLogs request is capped at 10 blocks, matching the current Alchemy Free-tier documented limit for Ethereum and BNB.
- Filters logs to the exact mapped contract and ERC-20 Transfer topic. The Ethereum transfer-summary API is not used for event persistence because it omits log index.
- Fetches and validates every block header in each bounded scan range with eth_getBlockByNumber, derives timestamps from those headers, and commits the scoped canonical block-hash journal atomically with events and the range checkpoint.
- Normalizes only logs carrying provider-supplied transaction hash and log index. Event identity remains transaction_hash:log_index.
- Commits each bounded log range and its next-block checkpoint through the existing atomic commit_page() transaction. Empty ranges also advance only after a successful provider response.
- Resumes from durable next_block after restart; provider timeout/network/rate-limit/5xx errors receive bounded retries. Malformed data, wrong finality semantics and scope mismatches fail closed.
- Re-fetches a caller-configured bounded recent block lookback, including blocks that previously had no transfers. If canonical hashes differ, affected events are tombstoned, the checkpoint rewinds to the earliest changed height, and the finalized range is replayed.
- A fresh worker page may re-canonicalize a previously tombstoned event identity only after its log is rechecked against the new canonical block header and its immutable transfer fields match. Ordinary store replays cannot resurrect tombstones.

Scope and operational limits:
- This is a callable orchestration component and test-verified Ethereum/BNB ingestion path, not a continuously scheduled production worker. A caller must provide mapping and ingestion stores, explicit start-block map, bounded run size and reorg lookback.
- No live Alchemy request or credential was used. Tests use deterministic local fixtures and do not prove live endpoint compatibility, actual account quota, provider uptime or plan-specific throttling behavior.
- SQLite remains the local/test persistence backend. PostgreSQL migration, real concurrency/failure tests, provider credentials, scheduler/worker lifecycle, metrics/alerts and operational runbook remain pending.
- Reorg detection is limited to the configured lookback window. A deeper reorg requires an operator-approved wider rescan/recovery procedure; do not claim arbitrary-depth automatic recovery.


## Ethereum provider documentation checked — 2026-11-11

- Alchemy Ethereum eth_getLogs reference documents the JSON-RPC log filter/response and a 10-block Free-tier range limit: https://www.alchemy.com/docs/chains/ethereum/ethereum-api-endpoints/eth-get-logs
- Alchemy support article updated 2026-08-25 describes Free-tier range restrictions: https://support.alchemy.com/articles/1883074130-why-do-i-see-a-free-tier-error-when-calling-eth-getlogs-with-a-large-block-range
- Alchemy explains removed logs and canonical reorg behavior: https://www.alchemy.com/docs/reference/logs

The worker uses fixed numeric block bounds and the provider's finalized tag, not latest. It does not rely on WebSocket subscriptions or the removed flag alone for reorg recovery. Local verification on 2026-11-11: 41 focused EVM worker/provider tests passed; full repository suite: 208 passed, 0 failed; compileall and git diff --check passed. No live provider request was made.


## Bitcoin UTXO output normalization implemented — 2026-11-11

The Alchemy read-only adapter now exposes fetch_bitcoin_transaction(txid), using the documented GET /api/v2/tx/{txid} endpoint to retrieve full vin/vout data and verify that the response matches the requested txid.

normalize_bitcoin_transaction_outputs() now:
- Requires an address-history record classified CONFIRMED and an explicit positive minimum-confirmation threshold supplied by the caller. No confirmation threshold is hardcoded or inferred as approved policy.
- Requires the full transaction's txid, block height, block hash and block time to match the address-history record.
- Requires the caller to provide an independently fetched canonical block hash and timezone-aware canonical block timestamp.
- Emits one event for each output with exactly one decoded address; event identity is txid:vout index.
- Preserves raw satoshi integer strings and uses 8 decimals; no floating-point BTC conversion is used.
- Represents the input side as a set of source addresses. A single source address is populated only when the input-address set is complete and contains exactly one address. Multiple input addresses are retained in from_addresses; no arbitrary sender is selected.
- Marks source-address completeness explicitly. Coinbase outputs have no fabricated sender; inputs without decoded address evidence make the source set incomplete.
- Skips outputs without one unambiguous decoded destination address (for example, OP_RETURN or multi-address scripts); it does not invent an output destination.
- Marks an event REORGED when the independently fetched canonical block hash differs from the transaction's referenced block hash.
- Requires the monitored address to appear in the transaction's decoded inputs or outputs and namespaces events under that address scope.

Important remaining limits:
- This is a provider detail fetch and pure output normalizer, not yet a Bitcoin ingestion worker. No Bitcoin event/checkpoint pages are being committed by a bounded Bitcoin worker yet.
- The next worker must use explicit monitored-address seeds, fixed block-height windows, independently fetched canonical block hashes, an explicitly configured confirmation threshold and durable restart semantics. Do not advance a window until every page and transaction detail has been safely normalized and committed.
- The normalizer relies on the provider's decoded address metadata (including isAddress); it does not implement independent Base58Check/Bech32 checksum verification.
- Multi-address output scripts are skipped because the current generic event model requires one destination address. Input addresses are represented as a set because Bitcoin transactions do not define a one-to-one sender/recipient mapping.
- Focused ingestion/provider tests: 50 passed, 0 failed. Full repository suite: 219 passed, 0 failed. compileall and git diff --check passed.
- No live Alchemy request or credential was used.

Official Alchemy references:
- Address history and fixed from/to block filters: https://www.alchemy.com/docs/chains/bitcoin/utxo-api-endpoints/utxo-api-endpoints/get-address
- Full transaction details and vin/vout schema: https://www.alchemy.com/docs/chains/bitcoin/utxo-api-endpoints/utxo-api-endpoints/get-transaction

## Bounded Bitcoin address-history ingestion worker implemented — 2026-11-11

`layer1/onchain_bitcoin_worker.py` now wires the Alchemy Bitcoin address-history and full-transaction detail methods to the existing Bitcoin output normalizer and atomic ingestion store.

- Reads only mappings returned by `OnChainStore.list_verified_mappings("bitcoin-mainnet")` that pass the worker's native BTC / UTXO / 8-decimal mapping checks.
- Requires explicit monitored-address seeds and an explicit start block for every mapping. Each address has an independent cursor and event scope; this is not a network-wide scan or global whale feed.
- Requires a caller-supplied positive `minimum_confirmations`; there is no implicit production confirmation policy. The worker calculates the safe scan ceiling as `tip_height - minimum_confirmations + 1`.
- Scans a bounded fixed block-height range per address and uses the provider's page number/page count with the same fixed from/to heights on every page. Each successful page commits its normalized outputs, canonical block journal and next-page/next-range checkpoint atomically.
- Fetches full transaction details by the exact txid for every address-history record. It never treats address-history summaries as transfer events and never fabricates output indexes.
- Independently resolves canonical block hashes and timestamps for every height in the range (including blocks with no address activity) using `getblockcount`, `getblockhash` and `getblockheader`.
- On restart, resumes the saved page for the same fixed range. If provider pagination metadata changes, it restarts the range at page 1 rather than continuing from a potentially stale offset.
- Reconciles a bounded caller-configured lookback against independently fetched canonical headers. It also checks already-journaled headers inside a partially paginated active range; a changed hash tombstones affected events and restarts that range at page 1.
- Retries provider timeouts, network errors, rate limits and HTTP 5xx responses a bounded number of times. Malformed pages, scope mismatch, transaction/block identity mismatch, insufficient confirmations and other non-retryable provider errors fail closed without advancing the affected page checkpoint.
- Uses `txid:vout` identity and integer satoshis through the existing normalizer. Multi-input source addresses remain a set; no single sender is invented.

Verification:
- Seven dedicated worker tests cover explicit address scope, page-level restart after a transaction-detail failure, empty pages, empty-block reorg recovery, reorg within a partially paginated range, confirmation gating and provider scope mismatch.
- Two provider tests cover independent Bitcoin tip/header retrieval and canonical header hash mismatch rejection.
- Focused Bitcoin worker/provider/normalizer suite: 58 passed, 0 failed. Full repository suite: 228 passed, 0 failed. `compileall` and `git diff --check` passed.
- All tests use deterministic local fixtures. No live Alchemy request or credential was used; no live provider compatibility, throughput, or billing behavior is claimed.

Remaining operational limits:
- Bitcoin address discovery is intentionally out of scope; an operator must provide monitored address seeds.
- Confirmation threshold, initial scan height, per-run range size and reorg lookback remain explicit caller policy.
- Reorg recovery is limited to the configured lookback and the active persisted range; deeper reorganizations require an operator-approved wider rescan.
- SQLite remains the local/test store. PostgreSQL migration, real concurrency/load testing, live provider verification, scheduler/worker lifecycle, metrics/alerts and runbook are still pending.
- Address checksum verification remains outside the normalizer; address decoding currently relies on provider-supplied address metadata.

## Solana transfer extraction assessment — 2026-11-11

Assessment only; no Solana transfer normalizer or worker was added in this step.

Verified from current official references:
- Alchemy `getTransactionsForAddress` returns address-scoped transaction history with full transaction and metadata when `transactionDetails: "full"`, including slot, transaction index, signature/transaction data and an opaque pagination token. The documented request limit is up to 100 full transactions per request; the endpoint is documented at 100 CUs per request.
- Solana transaction metadata can include `innerInstructions`, `preTokenBalances`, `postTokenBalances` and `loadedAddresses`. Versioned transactions require address lookup-table resolution before compiled instruction account indexes can be interpreted.
- Solana's official `@solana/transaction-introspection` package resolves static and lookup-table account indexes, walks outer and inner CPI instructions in execution order, and provides stable trace coordinates (`outerIndex` / `innerIndex`). Its companion generated token clients can identify and parse Token Program instructions.
- Alchemy `getBlock` can independently return a finalized slot's block identity with `transactionDetails: "none"`; its documented cost is 40 CUs. This can supply the blockhash/time journal needed for canonical slot checks.

Engineering decision:
- Do not treat token balance deltas as individual transfer events. A delta may aggregate multiple instruction effects and cannot by itself prove one source/destination transfer.
- Do not use the transaction signature alone as an event identity: a transaction can contain multiple outer and inner token transfers. Candidate identity must include the signature and the exact outer/inner instruction trace coordinate; do not fabricate either index.
- Correct extraction must resolve account indexes across static keys and loaded writable/readonly addresses, decode both outer and CPI instructions, validate exact Token / Token-2022 program IDs and verified mint mapping, and preserve integer base-unit amounts plus mint decimals.
- SOL native transfers require separate System Program instruction decoding and must not be inferred from net lamport balance changes alone (fees, rent, account creation/closure and other instructions can affect balances).
- The existing Python service has no drop-in Python equivalent of the official TypeScript transaction-introspection + generated token-program clients. Introducing a separate Node runtime solely for decoding would add operational complexity; no package has been added without a verified integration decision.
- The currently documented Alchemy endpoint describes slot filters but the exact fixed-range filter shape and its pagination stability were not established in this review. Do not build a resumable worker on assumed slot filter semantics.

Next Solana task:
1. Verify the exact slot-filter schema and pagination behavior from provider examples/schema or a controlled read-only test.
2. Decide whether to use a narrow Python decoder or a bounded Node interoperability boundary; compare maintained open-source options and license/runtime costs.
3. Build tests first for legacy + v0 lookup-table account resolution, outer + inner Transfer/TransferChecked, Token-2022, duplicate same-transaction transfers, failed transactions, unsupported extensions and missing metadata.
4. Only then add a normalizer whose event identity is signature + exact instruction trace coordinate and whose blockhash is independently verified at finalized commitment.
5. Keep the extractor address-scoped; no network-wide Solana whale coverage is implied.

Official references:
- Alchemy getTransactionsForAddress: https://www.alchemy.com/docs/chains/solana/solana-api-endpoints/get-transactions-for-address
- Alchemy getBlock: https://www.alchemy.com/docs/chains/solana/solana-api-endpoints/get-block
- Solana transaction introspection and account lookup resolution: https://solana.com/docs/core/transactions/transaction-introspection
- Solana RPC JSON structures (inner instructions, token balances, loaded addresses): https://solana.com/docs/rpc/json-structures
- SPL token transfer instructions: https://solana.com/docs/tokens/basics/transfer-tokens

## Solana SPL token address-history ingestion implemented — 2026-11-11

### Provider contract and pagination
- Alchemy `getTransactionsForAddress` now accepts paired inclusive fixed slot bounds and passes `filters.slot = {gte, lte}`, with `commitment=finalized`, `transactionDetails=full`, `sortOrder=desc`, `encoding=json`, `maxSupportedTransactionVersion=1`, and `tokenAccounts=balanceChanged`. Explicit JSON encoding retains compiled instruction bytes and resolved loaded-address metadata; version 1 opt-in is required to avoid rejecting v1 transactions.
- The adapter requires returned transaction slots to remain inside the requested range and requires the provider's transactionIndex for bounded slot queries. The returned opaque paginationToken is persisted with the exact address/mapping/range query.
- The official Alchemy endpoint page documents slot filters, transactionIndex, full transaction pages and pagination. QuickNode's current method reference documents inclusive slot gte/lte semantics and cursor positioning; the worker does not parse or synthesize the opaque cursor.
- Finalized slot is independently obtained through genesis-checked `getSlot(commitment=finalized)`. `getBlocks` identifies produced slots; `getBlock(commitment=finalized, transactionDetails=none)` verifies blockhash and blockTime for each produced slot.

### Instruction-level normalizer
- Added `normalize_solana_token_transfer_instructions()` for the base SPL Token Program only: standard `Transfer` (opcode 3) and `TransferChecked` (opcode 12).
- Resolves instruction program/account indexes using static message keys followed by metadata loaded writable and readonly addresses. Versioned transactions with missing/incomplete lookup-table address resolution fail closed.
- Walks each outer instruction followed by the corresponding inner CPI instructions. Stable event identity is `signature:outer:<index>` or `signature:inner:<outerIndex>:<innerIndex>`; no synthetic instruction indexes are generated.
- `TransferChecked` mint and decimals are checked against the verified mapping. Unchecked `Transfer` requires source and destination pre/post token-balance metadata to prove the same mapped mint and decimals.
- Monitored wallet ownership is proven using token-balance owner metadata. Event `from_address` and `to_address` are the actual source/destination token-account addresses; owner addresses are preserved in provenance. Aggregate balance deltas are never converted into individual transfer amounts.
- Amounts remain exact raw u64 base units. Failed transactions, missing metadata, inconsistent mint/owner/decimal evidence, invalid account indexes and mismatched signatures/slots fail closed.
- A single transaction with multiple token transfers produces separate instruction-trace event identities.

### Bounded worker and durability
- Added `layer1/onchain_solana_worker.py`. It requires explicit monitored address seeds and explicit starting slot per verified token mapping; it is not a network-wide Solana scan.
- Scans caller-bounded fixed slot windows and follows the opaque page cursor. It verifies descending (slot, transactionIndex) order, rejects repeated/looping cursors, and only advances after the event page, full per-slot canonical journal and checkpoint commit atomically.
- New SQLite `layer1_onchain_solana_slot_journal` records every slot in the scanned range. Produced slots store canonical blockhash/time; skipped slots store `produced=false` with null hash/time—no fabricated block is created.
- Bounded reorg reconciliation compares produced-slot membership and blockhashes, including empty/skipped slots. It tombstones events on removed/changed blocks, rewinds to the earliest changed slot, and replays the fixed range. Active partially paginated ranges are rechecked before resuming.
- Provider timeout/network/rate-limit/5xx failures use bounded retries. Non-finalized pages, wrong address scope, out-of-range records, malformed headers and invalid cursor progression do not advance the page checkpoint.

### Deliberate exclusions / production limits
- Native SOL System Program transfer extraction is not implemented; lamport balance deltas are not used as a substitute.
- Token-2022 is deliberately excluded from this first normalizer/worker. Token-2022 has extension-specific instructions including transfer-fee variants and transfer hooks; the worker skips Token-2022 mappings rather than silently missing or misreporting those events. Add extension-aware parsing before enabling those mappings.
- The official MIT `@solana/transaction-introspection` package v8.6.0 was reviewed; it supports legacy/v0/v1, lookup tables and inner CPI. No Node runtime or package was added to this Python-only service. The current Python parser is intentionally narrow and fixture-tested for the exact SPL instruction layouts it accepts. It does not claim to be a general Solana transaction decoder.
- Alchemy documents `getTransactionsForAddress` at 100 CUs/full page, `getBlock` at 40 CUs per produced slot and `getBlocks` at 10 CUs per range call. A worst-case 100-slot range with 100 produced blocks is approximately 4,010 CUs per address before full transaction pages; the bounded reorg lookback adds further header reads. Keep ranges and seed count conservative. This is not a low-cost global whale-indexing strategy.
- A produced slot with unavailable/null blockTime currently fails closed. Wallet-owner matching also requires provider token-balance owner metadata; missing owner evidence can mean the event is omitted for owner-address scope.
- Reorg recovery is limited to the configured lookback and active range. Deep finalized-chain reorganization requires operator-approved wider rescan.
- No live Alchemy request, API key, paid quota or production deployment was used. Local deterministic tests do not establish live endpoint behavior, provider billing or archival retention.

Verification for this implementation:
- New Solana normalizer, worker and provider tests are included in the repository suite. Full-suite result is recorded in the final progress entry below.
- No real Binance Square post or earning workflow was executed.

Official references:
- Alchemy `getTransactionsForAddress`: https://www.alchemy.com/docs/chains/solana/solana-api-endpoints/get-transactions-for-address
- Alchemy `getTransaction` v1 support and encoding options: https://www.alchemy.com/docs/chains/solana/solana-api-endpoints/get-transaction
- Solana maxSupportedTransactionVersion rules: https://solana.com/docs/rpc/http/gettransaction
- Alchemy `getBlocks`: https://www.alchemy.com/docs/chains/solana/solana-api-endpoints/get-blocks
- Alchemy `getBlock`: https://www.alchemy.com/docs/chains/solana/solana-api-endpoints/get-block
- Solana transaction introspection and account lookup resolution: https://solana.com/docs/core/transactions/transaction-introspection
- Solana RPC JSON structures: https://solana.com/docs/rpc/json-structures
- SPL token transfers: https://solana.com/docs/tokens/basics/transfer-tokens
- Token-2022 transfer fee extension: https://solana.com/docs/tokens/extensions/transfer-fees

## Solana worker final verification — 2026-11-11

- Full repository suite: **260 passed, 0 failed**.
- Focused Solana normalizer + worker + provider suite: **65 passed, 0 failed**.
- `compileall`: passed.
- `git diff --check`: passed.
- Tests use deterministic local fixtures only; no live Alchemy request or credentials used.
- New code includes no Node package or runtime dependency. The decoder is Python and intentionally accepts only the exact base SPL Token transfer layouts covered by tests.
- The implementation is not production-approved: PostgreSQL migration/concurrency tests, live provider/plan verification, scheduler lifecycle, operational monitoring, and a wider reorg recovery/runbook remain pending.

## Solana implementation commit and remote push — 2026-11-11
- Implementation commit: `ca567bc7ea64f278bf2564191333a3f460918cd1` — `feat(layer1): add bounded Solana SPL token ingestion`.
- Commit was pushed to `origin/layer-1/module9-onchain-intelligence` after confirming the remote head was the expected prior commit `f1198983757f1c5cc1fa4125afedaec9ae07c84b`.
- Local tracked tree is clean; only the pre-existing untracked `.venv/` remains.


## XRPL issued-currency Payment ingestion implemented — 2026-11-11

### Provider and canonical ledger evidence
- Existing `ChainstackXrplReadOnlyAdapter.fetch_account_transactions()` remains account-scoped and requires an explicit fixed inclusive ledger range. It rejects unvalidated pages/transactions, mismatched account scope, malformed transaction hashes/ledger indexes/metadata and provider responses that do not cover the requested range.
- Added `fetch_ledger_header(ledger_index)`: requests that exact ledger with `transactions=false`, requires `validated=true`, exact returned ledger index, a 32-byte ledger hash and integer close time. XRPL close time is converted from the Ripple epoch (2000-01-01 UTC) to Unix time.
- The worker obtains the current validated head via the existing `server_info` probe and never queries moving `-1` ledger bounds for page pagination.

### Payment normalizer
- Added `normalize_xrpl_payment()` for `TransactionType=Payment` and `TransactionResult=tesSUCCESS` only.
- Requires provider record `validated=true`, exact raw transaction hash and ledger index matching the typed record, transaction Account and Destination, and monitored account matching one of those two sides.
- Requires metadata `delivered_amount` to be a positive finite issued-currency object whose exact currency and issuer match the verified mapping. Missing, `unavailable`, malformed, zero, negative or non-finite delivered amounts fail closed. It never substitutes transaction `Amount` or infers a transfer from RippleState balance changes.
- Uses the transaction hash as the stable one-payment event identity; ledger index/hash and TransactionIndex are retained. The ledger hash is independently fetched from the exact validated ledger header before normalization.
- XRPL IOU amounts are decimal strings, not integer base units. The worker scales them using the mapping's explicitly configured `decimals` and accepts only an exact integer representation. Decimal arithmetic uses sufficient precision; XRPL normalized 16-digit mantissa and exponent range (-96..80; decimal adjusted exponent -81..95) are checked. Values not exactly representable at the configured scale are rejected rather than rounded.
- Non-Payment transactions, failed Payments and Payments of other issuer/currency mappings do not create events. Native XRP, CheckCash, AccountDelete, AMM-specific balance effects and trustline balance-delta inference are not implemented. XRPL classic-address checksum validation is not yet implemented; account seeds are shape-checked only, so production configuration must be validated with `xrpl-py` addresscodec or an equivalent checksum verifier before use.

### Bounded worker and recovery
- Added `layer1/onchain_xrpl_worker.py`, requiring verified XRPL issued-currency mappings, explicit monitored account seeds, explicit initial ledger per mapping, bounded ledger windows, page size/page count and reorg lookback.
- Each account query persists a fixed ledger range plus the provider's opaque marker. Event page, canonical ledger hashes and checkpoint are committed through the existing atomic `commit_page()` transaction.
- Marker contents are treated as opaque. Repeated/looping markers are rejected. If a persisted marker produces an RPC error, the worker resets the marker and replays the same fixed range from page one; replay is idempotent.
- The worker fetches exact validated headers for every ledger in the bounded range, including ledgers with no account transactions, so a changed ledger hash can be detected even when the old ledger had no transfer event.
- Completed-range lookback and active partial ranges are rechecked. Changed ledger hashes tombstone affected events and rewind/restart the relevant range before replay. Recovery is limited to the configured lookback plus the active range.
- Events are scoped per monitored account and mapping. The same Payment can therefore appear in multiple account scopes if both sender and recipient are monitored; downstream aggregation MUST deduplicate by `(mapping_id, transaction_hash)` before counting transfer volume.

### Open-source review
- Reviewed [`xrpl-py`](https://github.com/XRPLF/xrpl-py): maintained Python XRPL SDK, Python 3.10+ support, ISC license, native RPC models/client and address codecs. It is suitable if future address checksum validation, model-based RPC or XRPL serialization/signing is required.
- It was not added as a runtime dependency for this read-only extraction slice: the existing transport already handles the bounded JSON-RPC calls, and the normalizer consumes the validated JSON metadata directly. No SDK source was copied or vendored. Transaction signing is outside this project's read-only scope.

### Verification and limits
- New XRPL normalizer, worker and provider tests cover delivered-vs-requested partial payment amounts, missing/unavailable/malformed delivered amounts, exact issuer/currency, account-side proof, validated status, transaction hash/ledger identity, decimal exactness/precision, fixed-range marker resume, timeout recovery, expired-marker replay, marker loops, active-range reorg and completed-range ledger rewind.
- No live Chainstack request or credential was used. Provider JSON-RPC compatibility, actual history coverage/retention and real endpoint pagination remain unverified.
- Worker fetches each ledger header in its bounded range; this is intentionally conservative but can be RPC-intensive per monitored account. Keep windows and account seeds conservative until live quota/cost measurements are available.
- Account-scoped history is not network-wide whale discovery. Native XRP is not yet extracted. SQLite remains local/test storage; Postgres migration/concurrency, scheduler lifecycle, metrics/alerts, runbook, live provider verification, aggregation and candidate-analysis wiring remain pending.

Verification: focused XRPL normalizer/worker/provider/mapping suite: 89 passed, 0 failed; full repository suite: 286 passed, 0 failed; compileall and git diff --check passed. All tests use deterministic local fixtures.

Official XRPL references: [currency formats](https://xrpl.org/docs/references/protocol/data-types/currency-formats), [transaction metadata](https://xrpl.org/docs/references/protocol/transactions/metadata), [`account_tx`](https://xrpl.org/docs/references/http-websocket-apis/public-api-methods/account-methods/account_tx), and [markers and pagination](https://xrpl.org/docs/references/http-websocket-apis/api-conventions/markers-and-pagination).

## Cross-network transfer aggregation and deduplication — 2026-11-11

### Implemented API
- Added `layer1/onchain_aggregation.py` with `OnChainTransferAggregator`, `TransferAggregationResult`, `AssetTransferRollup` and `NetworkTransferSummary`.
- `OnChainTransferAggregator` requires the existing verified `OnChainStore`, an explicit positive decimal `minimum_amount_by_mapping` entry for **every** verified mapping, and explicit freshness limits. It rejects missing/unknown threshold IDs; there is no default whale threshold.
- Call `aggregate_store(ingestion_store, eligibility_by_asset, now=...)` to read canonical events from all supported networks. In-memory aggregation is also possible only after binding the canonical ingestion store; each event must already exist as the exact persisted canonical record and match the persisted `(network, provider, scope, block_number) -> block_hash` journal.
- The current `EligibilityDecision` must be supplied by canonical asset ID. The aggregator checks the exact Binance `exchangeInfo?permissions=SPOT` source, canonical CoinGecko identity proof, exact symbol/pair evidence, decision/proof freshness, and re-validates the mapping against the latest persisted ACCEPTED on-chain observation. Missing, stale, forged-shape, ineligible or unproven decisions produce no qualifying summary.

### Identity and amount rules
- Deduplication key is `(network_id, mapping_id, event_id)`. This collapses XRPL's same issued-currency Payment found from multiple monitored accounts (its event ID is the transaction hash) and collapses repeated discoveries of the same Bitcoin output, EVM log or Solana instruction. It does **not** collapse two different EVM logs or Solana instructions from one transaction.
- Duplicate rows across account scopes are accepted only when all economic and canonical fields agree. A conflict fails closed. `scope` and `observed_at` may differ between observations; amount, sender/destination evidence, transaction, block, event index and block time may not.
- The event's transaction hash, block hash and stable event ID are checked against network-specific formats. EVM/Bitcoin event-index suffixes must match `event_index`; Solana signature + outer/inner trace coordinates are retained in `event_id`; XRPL Payment event ID must equal its transaction hash.
- The event must match a verified mapping's exact asset ID, network and decimals; its provider must be approved for that network; its block must be recent under the configured network freshness policy; and its block hash must equal the canonical block journal for the exact account/contract scope. Missing or mismatched journal evidence is rejected.
- Amounts are integer base-unit strings converted with exact Decimal scaling using the mapping's decimals. No floating-point arithmetic, rounding, price conversion or cross-network quantity summation occurs.
- Output is segmented by `(asset_id, network_id, mapping_id)`, with a per-mapping explicit minimum amount and `threshold_met` flag. `qualifying_network_summaries`/`qualifying_assets` expose only summaries that meet the configured threshold. Asset rollups count observations and networks but intentionally expose no combined cross-network token amount or USD amount: wrapped/bridged supply and bridge legs can double-count economic movements.
- Source/destination counts are generic address counts, not inferred whale wallet counts. Incomplete Bitcoin input attribution contributes no source-address count. The layer does not infer buy/sell direction, trader intent, exchange deposits, net accumulation or whale status.

### Deterministic verification
- Focused aggregation suite: 17 passed, 0 failed. Full repository suite after candidate integration: 313 passed, 0 failed. `compileall` and `git diff --check` passed.
- Added `tests/test_onchain_aggregation.py`: cross-network asset rollup with differing decimals (BTC 8 vs ERC-20 wrapped BTC 18), per-mapping thresholds, XRPL account-scope dedupe, preservation of distinct EVM logs and Solana instructions in the same transaction, exact network event identity/index, canonical block-journal matching, Binance Spot eligibility/freshness gate, stale/future/noncanonical rejection, incomplete Bitcoin source attribution, conflicting duplicates and missing/invalid threshold configuration.
- Focused aggregation suite: 16 passed, 0 failed. Full repository suite: 302 passed, 0 failed. `compileall` and `git diff --check` passed.
- Each event supplied to in-memory aggregation must exactly match its persisted event row and canonical block journal entry. `aggregate_store()` reads only persisted canonical rows. This module is a deterministic aggregation API, not yet wired into Layer 1 candidate scoring or publication. No real Binance Square post is triggered by this module.
- The module does not apply Binance order filters (PRICE_FILTER, LOT_SIZE, MIN_NOTIONAL/NOTIONAL); those are execution constraints, not on-chain event thresholds. See [official Binance Spot filters](https://github.com/binance/binance-spot-api-docs/blob/master/filters.md).

### Remaining work
- Candidate-analysis integration with an explicit no-buy/sell/no-publication boundary and feature provenance.
- PostgreSQL schema/migration and real PostgreSQL transaction/concurrency tests; SQLite remains local/test storage.
- Scheduler/worker lifecycle, leases, metrics, alerting, retention and operational runbook.
- Live provider verification, RPC cost/latency measurements, address checksum validation for XRPL and independent chain-specific coverage review.

### Candidate-analysis corroboration integration
- `NetworkTransferSummary.summary_id` is a deterministic SHA-256 fingerprint of the exact mapping/network/event IDs, canonical block hashes, amount, threshold and time bounds. `TransferAggregationResult.generated_at` records when current Binance Spot/mapping validation was performed.
- `CandidateDiscoveryFilteringEngine.build(..., onchain_aggregation=result)` accepts an optional `TransferAggregationResult`. It rechecks result age, current Binance Spot eligibility source, canonical CoinGecko identity proof and proof freshness, summary asset/symbol, threshold arithmetic, and summary event freshness before attaching summary IDs.
- Qualified on-chain summary IDs are persisted by `Layer1Store.save_candidate()` under `evidence_refs_json.onchain_transfer_summaries`.
- On-chain evidence is corroborative only: it does not change candidate identity, discovery state, relevance score weights or publication authority. On-chain-only evidence cannot create a discovery candidate. Ineligible/stale/unverified candidates receive no on-chain refs.
- `main.run_once(..., onchain_aggregation_by_asset=...)` and `_persist_layer1_market_intelligence(..., onchain_aggregation_by_asset=...)` expose an explicit optional injection boundary keyed by canonical asset ID. Default is `None`/`NOT_PROVIDED`; the main cycle does not start on-chain workers or fetch providers automatically. An external, separately supervised worker/orchestrator must supply already validated `TransferAggregationResult` objects. The main pipeline persists only corroboration summary IDs and counts; it does not publish based on them.
- Candidate integration tests cover real aggregator-to-candidate flow, candidate identity stability, no on-chain-only discovery, Spot/proof/freshness hard gates, summary persistence and unchanged relevance scores.

## PostgreSQL persistence and transactional concurrency — implementation checkpoint, 2026-11-11

### Repository state before this work
- Verified local branch and remote branch were both layer-1/module9-onchain-intelligence at 9b2f1e636ea6298901de05aaee63415e72856e19.
- Tracked tree was clean; pre-existing untracked .venv/ was preserved and not staged, deleted or modified.
- PR #13 remained OPEN/Draft/unmerged; PR #12 remained OPEN/non-draft/unmerged and unchanged. Latest PR #13 check was 43070470073 SUCCESS.

### New PostgreSQL implementation
- Added layer1/onchain_postgres.py:
  - apply_postgres_migrations(dsn) applies numbered SQL migrations under a PostgreSQL transaction-level advisory lock and verifies SHA-256 checksums of previously applied migrations. It does not read environment variables or auto-migrate at store construction.
  - PostgresOnChainStore persists verified mappings and accepted observations, retaining the existing OnChainIntelligenceEngine validation gate and rejecting conflicting mapping/observation IDs.
  - PostgresOnChainIngestionStore implements the ingestion-store read/write contract using Psycopg 3 and PostgreSQL JSONB/timestamptz.
  - StaleCheckpointError, CheckpointIdentityConflict and CanonicalBlockConflict make concurrency/identity conflicts explicit.
- Added migration layer1/migrations/postgresql/0001_onchain_storage.sql for verified mappings, observations, transfer events, ingestion checkpoints, canonical block journal and Solana slot journal. It includes provider/network/scope composite uniqueness, event idempotency, foreign keys, check constraints and read-path indexes.
- Ingestion commits require the caller's expected checkpoint snapshot and explicit (network_id, provider, scope) identity. A transaction-scoped PostgreSQL advisory lock serializes the scope; a locked checkpoint row and compare-and-swap reject a stale worker. The checkpoint is unique per network/provider/scope.
- Event rows, canonical block/slot journal rows and checkpoint revision advance in one transaction. Event IDs are unique within network/provider/scope. Conflicting canonical block hashes and inconsistent slot journal changes fail closed unless the worker explicitly requests a reconciled reorg replay and no still-canonical event remains attached to the old hash.
- reconcile_block() uses the same transaction-level scope lock before tombstoning canonical events.
- SQLite remains supported. Its commit_page() now accepts optional expected-cursor/scope guards, rejects stale expected cursors and refuses silent canonical block/slot hash overwrites. All four existing workers (EVM, Bitcoin, Solana and XRPL) now pass the checkpoint snapshot and scope identity at each commit, updating their expected snapshot after successful commits.
- The existing optional Psycopg dependency is shared through requirements-announcement-importer.txt; requirements-onchain-postgres.txt includes that optional dependency. No SQLAlchemy/Alembic dependency was introduced.

### Tests and verification actually performed
- Added tests/test_onchain_postgres.py with a guarded integration suite requiring TEST_POSTGRES_DSN to point to a local database named binance_onchain_test. It covers migration repeatability/schema, mapping+observation round-trip/idempotency, atomic event+journal+checkpoint commits, transaction rollback after a mid-transaction database error, same-checkpoint concurrent workers, duplicate-event retry after a checkpoint conflict, overlapping-range protection, canonical block hash conflicts, reorg replay and Solana slot consistency.
- Added SQLite tests for stale checkpoint rejection and canonical block hash conflict. Existing worker reorg tests exposed and helped correct the Solana slot-journal reorg predicate; the focused ingestion + four worker suites now pass.
- Full repository suite: 326 passed, 0 failed, 10 skipped. The 10 skips include the PostgreSQL integration tests because TEST_POSTGRES_DSN is not configured.
- compileall: passed. git diff --check: passed.
- PostgreSQL migration SQL parsed successfully with PostgreSQL grammar tooling: 11 statements parsed. Psycopg 3.3.8 import was verified using a temporary dependency target under /tmp; the repository .venv/ was untouched.

### Explicit PostgreSQL verification blocker
- PostgreSQL 16 server/client binaries exist locally, but no server was running and no TEST_POSTGRES_DSN was configured.
- An isolated local PostgreSQL 16 test cluster was attempted under /tmp (database target binance_onchain_test); initialization failed because the environment's shared-memory syscall returned shmget: Function not implemented. The attempt did not reach a running database.
- Therefore the migration was not applied to a live server, and none of the multi-connection PostgreSQL tests ran. SQL grammar parsing and adapter import are not substitutes for PostgreSQL runtime/concurrency verification.
- No production Neon/other database was accessed, no database credentials were changed, no live RPC was called, and no publishing workflow was activated.

### Current status and next action
- PostgreSQL schema, migration runner and adapter are implemented locally but not yet runtime-verified or approved for production.
- Next: run the guarded integration suite against an accessible dedicated local/test PostgreSQL 16+ server using TEST_POSTGRES_DSN only; validate migrations, transaction rollback, concurrent inserts/checkpoints, canonical reorg replay, and mapping/observation persistence. Do not point tests at production or a shared database.
- Review any real-server failures before committing. Then run the full suite again, update this document, and only then consider a guarded commit/push to the existing feature branch. Keep PR #13 Draft and PR #12 unchanged.
- Remaining Module 9 tasks after real PostgreSQL verification: supervised worker lifecycle, durable distributed leases/ownership, retry/backoff classification, metrics/alerts, retention/runbook, live provider verification only after approval, and chain-specific review (including XRPL classic-address checksum and native SOL decision).



### Final verification addendum — 2026-11-11
- Final full repository suite after the last storage/test changes: **327 passed, 0 failed, 10 skipped**. The skipped tests are the guarded PostgreSQL integration cases; TEST_POSTGRES_DSN is not configured.
- Final compileall and git diff --check both passed.
- PostgreSQL SQL grammar parser accepted all 11 migration statements.
- Canonical block and Solana slot journal timestamps are now immutable when the canonical hash/produced identity is unchanged; a timestamp-only mutation fails closed. A focused SQLite regression test covers the block timestamp invariant.
- The PostgreSQL integration DSN guard was tightened: it requires the dedicated binance_onchain_test database, an explicit local hostname or Unix socket, no remote hostaddr and no PostgreSQL service alias.

### Neon staging-branch validation — 2026-11-12
- Located the existing Binance bot Neon account and project `Binance-bot-staging` (`orange-glade-36037611`), PostgreSQL 16, branch `staging` (`br-rough-mud-az28jpxs`), database `binance_bot_staging`. Existing announcement tables were inspected read-only and left unchanged.
- Created isolated copy-on-write branch `module9-pg-integration-test` (`br-falling-bread-azl8rggt`) from the staging branch. A 0.25 CU read-write compute was provisioned for the test branch; the account rejected changing the suspend interval, so the project default remains in effect.
- Applied the 11 statements from `0001_onchain_storage.sql` only to the isolated test branch, in a transaction. PostgreSQL 16.15 accepted the DDL. Verified all six Module 9 tables, their primary/unique/foreign/check constraints and indexes through PostgreSQL catalogs. The parent `staging` branch was not modified.
- Re-ran the full local unittest suite: **327 passed, 0 failed, 10 skipped**; the 10 PostgreSQL adapter integration tests remain skipped because their safety guard only permits a dedicated local `binance_onchain_test` DSN. `compileall` and `git diff --check` passed.
- This verifies the migration DDL against a real Neon PostgreSQL 16 server, but does **not** verify the Python Psycopg adapter, multi-connection concurrency or rollback against Neon. Do not claim full PostgreSQL integration readiness yet.
- No existing announcement rows/tables were changed, no on-chain fixture rows were inserted, no provider RPC or Binance publishing was invoked, and no schema was applied to the parent staging branch.
- Next: review/fix the adapter and test harness, then run the integration suite against this dedicated Neon test branch using an explicit, narrowly scoped test-only DSN path. Preserve the local-only guard by default; do not point tests at the parent staging branch or production.

### Final Neon PostgreSQL integration update — 2026-11-12
- Created database `binance_onchain_test` on the isolated `module9-pg-integration-test` branch; it is separate from the inherited `binance_bot_staging` database and from the parent `staging` branch.
- Ran the guarded Psycopg integration suite against that exact Neon branch endpoint and dedicated test database. The first 11-test run reported 10 passing and one failure because the canonical-block conflict test expected `ValueError` while the adapter intentionally raises the more specific `CanonicalBlockConflict`. The assertion was corrected. The corrected canonical-conflict, explicit-reorg-scope guard, and reorg replay tests then passed **3/3** against Neon. The other eight tests had passed in the first run. The entire Neon integration suite has not yet been rerun as one batch after the assertion correction; treat the combined result as strong but not final batch verification.
- The Neon run verified the real migration runner, mapping/observation round-trip and idempotency, atomic event+journal+checkpoint writes, rollback on a mid-transaction timestamp error, competing checkpoint writers, duplicate-event retry, canonical block conflict, reorg replay and Solana slot journal behavior.
- Added a fail-closed requirement that PostgreSQL `reconcile_block()` must receive explicit provider and scope so it always takes the same transaction advisory lock as page commits. All four workers already pass those identities.
- Final local full suite after this change: **328 passed, 0 failed, 11 skipped**. The 11 skipped are the PostgreSQL integration tests when no `TEST_POSTGRES_DSN` is set; the dedicated Neon run above executed them separately. `compileall` and `git diff --check` passed.
- The dedicated Neon test database contains only isolated synthetic test fixtures. The inherited announcement database/tables and the parent staging branch were not modified. The test branch has a 0.25 CU compute; the account rejected changing its suspend interval, so its default behavior remains.
- No commit, push, PR update, merge, deployment, production database mutation, provider RPC or real Binance Square publication occurred.
- Next: rerun the complete Neon integration suite once as a single clean batch, inspect/fix any issues, then perform final code/diff review. Do not promote the migration to the parent staging branch without explicit approval.

### Complete Neon PostgreSQL integration batch — 2026-11-12
- Re-ran the entire PostgreSQL integration module against the isolated Neon PostgreSQL 16.15 branch and dedicated `binance_onchain_test` database using an explicit exact-host allowlist plus TLS. Result: **13 tests passed, 0 failed** in 122.899 seconds. This includes the adapter contract test and all 12 live PostgreSQL integration tests.
- The earlier canonical-block test assertion mismatch is corrected to expect `CanonicalBlockConflict`; the dedicated reorg reconciliation API now requires explicit provider and scope.
- Tightened PostgreSQL Solana journal validation: a Solana slot journal record is accepted only when the checkpoint identity itself is `solana-mainnet`, and the slot network must equal that identity. Added a regression test for cross-network slot injection. The transaction rollback test now injects a bad canonical block timestamp after event insertion, proving rollback without using an invalid cross-network slot.
- The PostgreSQL test harness remains local-only by default. A remote endpoint is accepted only when `TEST_POSTGRES_ALLOWED_HOST` exactly matches the DSN hostname, database is exactly `binance_onchain_test`, TLS mode is required/verified, and no hostaddr or service alias is present.
- Final local repository suite: **329 passed, 0 failed, 12 skipped**. The 12 skips are the live PostgreSQL integration cases when `TEST_POSTGRES_DSN` is absent; the same 12 were executed in the dedicated Neon run above. `compileall` and `git diff --check` passed.
- No source was committed or pushed. `.venv/` remains pre-existing and untracked; it was not modified or staged. PR #13 remains Draft and PR #12 remains unchanged. No parent staging schema changes, production DB writes, live chain RPC, deployment, or Binance Square publishing occurred.
- PostgreSQL persistence/transaction adapter now has live integration evidence, but this does not by itself make the whole Module 9 service production-ready. Remaining work includes worker lifecycle/supervision, distributed ownership/leases, retry classification and backoff, observability, retention/runbook, and chain-specific validation decisions.


### Final local recovery and verification — 2026-11-12
- Recovered the existing uncommitted Module 9 PostgreSQL persistence work from the original development working tree; no reimplementation of completed modules was performed.
- Completed provider retry integration across EVM, Bitcoin, Solana and XRPL workers. Retry classification is limited to timeout, network errors, HTTP 429 and HTTP 5xx; bounded exponential backoff honors a capped Retry-After value. Retry delay configuration rejects non-finite values.
- XRPL normalization and aggregation fixtures now use checksum-valid classic addresses, matching the production validation boundary.
- Full repository unittest suite: **336 passed, 0 failed, 12 skipped**. The skips are the guarded PostgreSQL live integration cases when TEST_POSTGRES_DSN is absent from the ordinary suite.
- Dedicated isolated Neon PostgreSQL 16 integration batch: **13 passed, 0 failed** in 203.386 seconds, using the dedicated binance_onchain_test database, exact-host allowlist and TLS. No parent staging database was targeted.
- Focused provider/ingestion/XRPL/aggregation regression batch: **86 passed, 0 failed**. compileall and git diff --check passed.
- The pre-existing .venv/ directory was not staged. The temporary test DSN file is test-only and will be removed after the integration run.
- No real Binance Square post, provider RPC, production database mutation, deployment, PR merge or publishing workflow activation occurred.
- Module 9 remains not production-ready: worker supervision/lifecycle, distributed ownership/leases, observability/alerts, retention/runbook, and live provider verification still require separate work and approval.

## Acceptance receipt signing and durable key rotation (v1; local implementation, not production activation)

Module 9 emits an ACCEPTED validation result only when an explicit HMAC signing key is injected into OnChainIntelligenceEngine. The key must contain at least 32 bytes; receipt_key_id must be a stable 1–128 character identifier using letters, digits, dot, underscore or hyphen. Without an active signing key, a structurally valid observation returns UNAVAILABLE / ONCHAIN_RECEIPT_SIGNING_NOT_CONFIGURED.

`OnChainIntelligenceEngine.from_env()` now loads the operator-provisioned keyring through `layer1/onchain_receipt_config.py`:

- `ONCHAIN_RECEIPT_HMAC_KEYRING_JSON`: JSON object mapping key IDs to hex-encoded HMAC keys (minimum 32 bytes each).
- `ONCHAIN_RECEIPT_ACTIVE_KEY_ID`: key ID used to sign new receipts. It must exist in the keyring and in the trusted allowlist.
- `ONCHAIN_RECEIPT_TRUSTED_KEY_IDS`: comma-separated explicit allowlist for receipt verification. Retained historical key IDs must remain in this allowlist and keyring while receipts signed by those keys are still expected to be read.

A verification-only keyring may omit the active signer; in that mode no new ACCEPTED result is signed. Empty environment configuration disables receipt signing and trust. Malformed or inconsistent configuration fails closed. The repository/environment used for this local continuation has no Module 9 keyring, active key ID or trusted key IDs configured; no key was generated, read, stored or committed.

`EvidenceVerificationEngine.evidence_from_onchain_observation()` requires an explicit expected receipt key ID and a trusted key; the verification key can be supplied directly or resolved from the configured keyring. It now carries the signed validation envelope and the exact serialized observation/validation payload into `EvidenceRecord`. ClaimRegistry replay re-parses those fields and re-verifies the HMAC, key ID, observation identity and corresponding evidence fields before restoring primary provenance. A persisted key ID alone is no longer sufficient. SQLite and PostgreSQL on-chain stores verify persisted ACCEPTED rows by the receipt's own key ID, so trusted historical receipts remain readable after the active signing key rotates.

Operational requirements: provision keys only through an approved secret manager; never commit them, log them, expose them to untrusted callers/plugins, or place them in ordinary project configuration. Keep old verification keys only as long as required by the receipt retention policy, then retire their IDs from the allowlist deliberately. No production key IDs or secrets are supplied by this code.

Security boundary: receipt v1 authenticates that a holder of the configured shared key signed the supplied eligibility/mapping/observation snapshot and detects observation/receipt tampering. It does not authenticate the upstream provider response itself or prove that the observation was derived from that response. The individual observation path is not currently activated by main.py. Keep AUD-ONCHAIN-001 OPEN until provider-response binding, worker wiring, approved key provisioning, and disposable PostgreSQL worker/store acceptance are complete. This remains a local hardening slice, not production certification.

## Storage adapter contracts — structural, not runtime activation
- Module 9 workers and `OnChainTransferAggregator` now depend on structural protocols in `layer1/onchain_protocols.py`, rather than concrete SQLite store classes. SQLite and PostgreSQL adapters remain separate implementations.
- The ingestion contract requires `commit_page` calls to supply `expected_cursor` and `(network_id, provider, scope)` identity, and requires explicit provider/scope on reorg reconciliation. Constructor validation checks the relevant callable methods and keyword-capable signatures.
- This resolves the constructor-level nominal type incompatibility only. It does not wire workers into `main.py`, run provider ingestion, or establish PostgreSQL transaction/concurrency acceptance. A disposable PostgreSQL worker+aggregator integration suite remains required before Module 9 can be marked complete.


## Provider response body limits (AUD-ONCHAIN-004 — local remediation, not activated)

The shared `ReadOnlyJsonRpcTransport` now rejects unbounded reads. Construction requires an explicit positive `max_response_bytes`; both REST JSON and JSON-RPC responses use the same bounded incremental reader. The reader rejects a declared `Content-Length` above the configured ceiling before reading, rejects malformed content lengths, and reads at most one byte beyond the remaining budget to detect chunked/incorrectly declared oversized bodies. Redirect behavior remains disabled.

Default Alchemy and Chainstack XRPL adapters require the same explicit limit. Their `from_env()` constructors require `ONCHAIN_MAX_PROVIDER_RESPONSE_BYTES` as a positive base-10 integer; missing, zero, negative, fractional, scientific-notation or otherwise malformed values fail closed. There is deliberately no guessed default. A custom injected transport factory is a trusted test/integration seam and must independently enforce an equivalent response bound if used outside tests.

No provider response-size telemetry or representative production payload corpus has been collected in this task. Operators must choose and document a ceiling using actual maximum legitimate response sizes for the configured page/range limits plus a justified safety margin. The environment variable is not provisioned in this worktree. No live RPC/provider request was made. Therefore AUD-ONCHAIN-004 is **PARTIALLY REMEDIATED / OPEN**, not closed; deployment activation and provider acceptance remain pending.


### Mandatory signed-page authorization gate — owner-approved 26 November 2026
- Policy: **a valid trusted page HMAC is mandatory before a persisted event can be used in downstream business aggregation**. Unsigned, tampered, unverifiable, revoked-key or stale page evidence does not authorize the event.
- `aggregate_store()` enumerates durable page identities, verifies each page acceptance against store-reconstructed provider receipts and current canonical evidence, then requires every canonical event to be present in a currently valid signed page. An event without valid signed-page lineage causes aggregation to fail closed.
- The SQLite and PostgreSQL stores expose the same `list_ingestion_pages()` protocol. PostgreSQL runtime acceptance is still outstanding; the test module was skipped when no disposable PostgreSQL backend was available.
- The lower-level iterable `aggregate()` is not the production business-consumption boundary. Production integration must use `aggregate_store()`; future call sites must not bypass the HMAC gate.
- Current verification: 1,118 repository tests passed, 72 skipped; compileall and diff check passed (26 November 2026). The page scan is O(total durable pages) per aggregation and needs performance/retention acceptance before high-volume activation. Module 9 remains not production-ready.

### Owner-approved provider trust boundary — 26 November 2026
- Only these exact HTTPS origins are approved: bitcoin-mainnet.g.alchemy.com, eth-mainnet.g.alchemy.com, solana-mainnet.g.alchemy.com, bnb-mainnet.g.alchemy.com, and xrpl-mainnet.core.chainstack.com.
- Alchemy path profile: /v2/{single URL-safe API key}; Chainstack XRPL path profile: /{single URL-safe endpoint token}. Port 443 only; no userinfo, query, fragment, extra path, traversal, wildcard subdomain or custom host.
- Direct-only application transport: explicit ProxyHandler({}) disables environment/system proxy discovery; redirects remain blocked.
- This is not cryptographic provider attestation or infrastructure egress proof. Provider-signed proof/peer identity decisions and deployment egress verification remain open. No live endpoint call was made.


### Owner-approved TLS and provider-response integrity baseline — 26 November 2026
- HTTPS certificate-chain validation and hostname verification are mandatory. The exact five provider origin profiles approved in the previous checkpoint remain the only allowed origins.
- Persist provider response receipts and SHA-256 hashes as evidence for the exact captured response bytes and their request/page lineage.
- A SHA-256 hash is an integrity digest, not a provider signature or provider-identity proof.
- Do not require signed provider responses unless the provider officially documents a supported cryptographic response-signature format and verification procedure. Do not invent a custom signature scheme.
- The policy is approved, but transport negative tests, persisted receipt-lineage acceptance and deployment egress evidence remain required. Application-level direct-only proxy configuration does not prove infrastructure-level egress isolation.
- AUD-ONCHAIN-001 remains PARTIALLY REMEDIATED / OPEN. Module 9 remains not production-ready.


### Explicit HTTPS certificate and hostname verification — 26 November 2026
- The provider HTTP opener now passes an explicit ssl.create_default_context() to HTTPSHandler. The context requires certificate-chain validation (CERT_REQUIRED) and hostname checking; the platform CA trust store is used.
- TDD regression failed before the implementation because no explicit HTTPSHandler was supplied; after implementation the provider test module passed 71 tests.
- Full repository suite: 1,123 tests passed, 0 failures/errors, 72 skipped; compileall and diff check passed.
- Limitation: this is configuration-level verification, not an end-to-end TLS handshake test using an untrusted certificate and hostname mismatch. Those tests and deployment trust-store/egress evidence remain required. No live provider request was made.


### TLS negative-handshake and receipt persistence verification — 26 November 2026
- Local HTTPS integration fixtures verify a trusted chain/matching IP SAN succeeds, an untrusted chain fails, and a trusted chain with mismatched IP SAN fails. RED control with an unverified SSL context caused both negative tests to fail, confirming regression sensitivity.
- Provider tests: 74 passed. Ingestion tests: 38 passed.
- Raw JSON-RPC response byte hashes were checked against captured receipts, persisted with the page, and verified after SQLite store reopen and page-acceptance material reload.
- Full repository suite: 1,127 tests passed, 0 failures/errors, 72 skipped.
- Remaining lineage gap: request_sha256 excludes destination endpoint origin; persisted ProviderResponseReceipt contains provider/network/method labels but no endpoint-profile fingerprint. Carried forward under AUD-EVID-003. A non-secret endpoint fingerprint in attestation and persisted receipt is recommended, subject to compatibility/migration tests.
- Deployment egress, deployed trust-store assurance, endpoint-to-receipt binding and source authenticity remain unverified. No live provider or production operation occurred.


### Approved endpoint-profile fingerprint — 26 November 2026
- New successful transport response attestations include endpoint_profile_sha256, computed from canonical HTTPS scheme, IDNA-normalized hostname and effective port only. Credentials, provider API-key/token paths, query strings and fragments are excluded.
- Built-in Alchemy and Chainstack adapters compare this digest to the exact configured approved endpoint profile before receipt capture. SQLite and PostgreSQL page commits require the fingerprint for new receipts and validate it against the approved provider/network mapping. Page-acceptance material readers repeat the validation.
- Historical receipt JSON without this optional field remains readable as legacy evidence with endpoint_profile_sha256=None; it is not upgraded. Existing JSON/JSONB persistence needs no SQL migration.
- TDD covered missing and unapproved fingerprint rejection, adapter mismatch, persisted tampering with recomputed receipt digest, origin normalization/secrecy, and legacy deserialization. Full suite: 1,135 run, 0 failures/errors, 72 skipped; compileall and diff-check passed.
- This origin hash is not a TLS peer/certificate fingerprint, provider signature, or proof of upstream response authorship. Custom transport injection remains a trusted seam; deployment egress and peer-identity verification remain open.
- AUD-ONCHAIN-001 remains PARTIALLY REMEDIATED / OPEN. Module 9 is not production-ready. No live provider, database, migration, or publication operation occurred.


### XRPL canonical-ledger response receipt lineage — 26 November 2026
- XRPL worker canonical-ledger checks call Chainstack fetch_ledger_header() inside the worker-level receipt scope. This response was previously omitted from the captured batch even though it supports canonical block hash/time evidence.
- The method now requires a transport attestation in worker scope, validates endpoint_profile_sha256 against the configured approved Chainstack origin, and appends a Chainstack/xrpl-mainnet/ledger receipt. Missing attestation fails closed with MISSING_RESPONSE_ATTESTATION. Standalone reads without an active worker receipt scope retain existing behavior.
- TDD RED reproduced zero receipts; GREEN and negative missing-attestation test passed. Focused provider, ingestion and XRPL worker suites: 132 passed.
- Factory audit: no non-test adapter construction callsite found in this Python source tree; runtime activation remains disabled. Future production composition must not expose transport_factory injection to untrusted callers.


### Latest full-suite verification — 26 November 2026
- Following XRPL canonical-ledger header receipt capture, full suite: **1,137 tests run, 0 failures/errors, 72 skipped**. compileall and git diff --check passed.
- No live provider call, DB connection, migration, or publication occurred.


### XRPL pagination shared-evidence receipt fix — 26 November 2026
- Each XRPL page reuses the validated head and fixed-range canonical ledger headers. Previously, their response receipts were drained into page one only; later pages persisted only their account_tx response receipt.
- The worker now drains head/reorg/header receipts into an opaque collector-issued batch after header acquisition and reattaches the immutable batch before each pagination request. Each page therefore persists the shared supporting responses plus its own account_tx receipt.
- TDD RED reproduced missing `server_info` and header receipts on page two. GREEN verifies both page receipt sets and verifies both page HMAC acceptances.
- Focused worker suite: 14 passed. Full repository suite: 1,138 tests run, 0 failures/errors, 72 skipped. compileall and git diff --check passed.
- This is local test evidence only; it does not certify provider identity, production runtime wiring, or deployment egress.


### Chainstack validated-head receipt capture — 26 November 2026
- The real XRPL adapter's `probe()` previously called `server_info` without capturing its response attestation. This meant worker `head_receipts` were empty for the real adapter even though a test fake modeled the receipt.
- Probe now requires attestation inside a worker receipt scope, validates the approved Chainstack endpoint-profile fingerprint, and appends a `server_info` receipt. Missing attestation fails closed. Standalone probe behavior is unchanged.
- Combined with the Section 159 shared-batch fix, every XRPL pagination page receives the server_info receipt, fixed-range ledger-header receipts and its own account_tx receipt.
- Positive/negative provider probe tests + XRPL worker tests: 15 passed. Full suite: **1,140 tests, 0 failures/errors, 72 skipped**. compileall and diff-check PASS.


### Worker-scope response-attestation enforcement — 26 November 2026
- XRPL account_tx, Alchemy JSON-RPC and Alchemy Bitcoin address REST previously skipped receipt creation if an injected transport returned no attestation, even during worker runs.
- `_ACTIVE_PROVIDER_RUN` now marks worker capture scope. These methods fail closed with `MISSING_RESPONSE_ATTESTATION` in that scope and validate the endpoint-profile fingerprint before appending provider receipts. Standalone lightweight fake transports remain compatible outside worker scope.
- TDD RED reproduced missing XRPL and Alchemy receipts. Focused provider + XRPL worker suites: 96 passed. Full suite: **1,142 tests run, 0 failures/errors, 72 skipped**. compileall and diff-check PASS.


### Solana and EVM worker receipt-lineage audit — 26 November 2026
- Audited worker/provider call paths. Solana re-fetches finalized slot and active-range produced-slot/header evidence on each resumed pagination run, then commits those fresh supporting receipts with the page's `getGenesisHash` and `getTransactionsForAddress` responses. The suspected later-page receipt omission was not confirmed.
- EVM captures finalized-height evidence, each range's chain ID/finalized-header/`eth_getLogs` responses and canonical block-header responses. Each range commits its own receipt batch; subsequent ranges repeat their own finality checks.
- Added exact ordered receipt tests for Solana, Ethereum and BNB, including endpoint-profile fingerprints. Focused provider + Solana + EVM suites: 24 passed. Full suite: **1,145 tests run, 0 failures/errors, 72 skipped**. compileall and diff-check PASS.
- No product-code change was required for these audited paths. This does not certify production wiring, provider identity/authorship or live egress.


### Bitcoin transaction-detail response receipt fix — 26 November 2026
- Bitcoin worker derives UTXO events from `vin`/`vout` returned by `fetch_bitcoin_transaction(txid)`. That REST call previously had no response-attestation capture, so the detail payload used to normalize events was absent from the durable page receipt lineage.
- The adapter now requires attestation in worker scope, validates the approved Alchemy Bitcoin endpoint profile, and appends a `GET api/v2/tx` receipt. Missing attestation fails closed. Standalone legacy fake transports remain compatible outside worker scope.
- Added tests for missing attestation, valid receipt capture, and worker page persistence with both address-page and detail receipts plus verifiable HMAC acceptance.
- Focused provider + Bitcoin + Solana + EVM + XRPL suites: 131 passed. Full suite: **1,148 tests, 0 failures/errors, 72 skipped**. compileall and diff-check PASS.


### Runtime activation audit — 26 November 2026
- Confirmed no production composition root currently constructs the provider adapters, network workers, mapping store, or ingestion store. The scheduled main loop and one-shot entrypoint pass no `onchain_aggregation_by_asset`; the Layer 1 summary therefore reports `NOT_PROVIDED`.
- Current RDC process has provider and receipt configuration variables unset (presence-only check; no values read). Tracked GitHub workflow files contain no Module 9 provider/key configuration references. This does not prove external deployment secrets are absent.
- Worker constructors require explicit address/account seeds, start positions, bounded ranges/pages, reorg lookbacks and Bitcoin confirmations; mapping-store validation requires explicit per-network freshness limits. These operational policies are not safely inferable.
- Master Audit Section 164 records this as a HIGH active production capability gap. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY pending reviewed composition, durable store wiring, scheduling, offline fail-closed integration tests, and separately authorized deployment acceptance.
- No code behavior or runtime environment was changed; no live provider, DB, migration, publication, or Git write operation occurred.


### Accepted-observation lifecycle and aggregation ordering — 26 November 2026
- Aggregator requires a latest accepted OnChainObservation per verified mapping, in addition to signed ingestion-page evidence. Production-only source/AST audit found no `save_verified()` caller or production `OnChainObservation` construction; worker tests seed observations manually. The worker ingestion store and mapping/observation store are separate.
- Aggregator also requires fresh Binance EligibilityDecision objects. Main currently generates those inside its candidate loop, while the optional `onchain_aggregation_by_asset` parameter expects already-computed aggregation results before candidate construction. This is not yet a complete orchestration interface.
- Master Audit Section 165 records these as additional activation blockers. A production path must define anchor-observation provenance/refresh/reorg lifecycle and integrate aggregation after current eligibility decisions are available. Do not fabricate anchor observations or equate a transfer event with one.
- No runtime/code behavior change or production operation was performed.


### Anchor-observation receipt binding audit — 26 November 2026
- Reproduced that `OnChainIntelligenceEngine.validate()` accepts a directly constructed observation and signs it without any durable provider page/receipt reference. The current observation HMAC binds only the supplied eligibility, mapping and observation snapshot.
- Transfer aggregation separately verifies signed ingestion-page acceptances, but `save_verified()` does not consult that verifier and no page/event identity is bound to the anchor observation. Therefore signed transfer pages do not currently establish the provenance of the separate accepted-observation gate.
- A safe fix needs a first-party verifier that re-reads accepted durable page material, verifies exact provider/network/mapping/transaction/block/finality binding and current canonical state, then fails closed on unbound observations. Do not merely add a caller-controlled page ID or equate transfer events with anchor observations.
- Master Audit Section 166 records the confirmed local reproduction. AUD-ONCHAIN-001 remains HIGH / OPEN; AUD-ONCHAIN-002 mapping authority/freshness remains owner-policy blocked. No code change or production operation was performed.

### Per-network finality persistence gap — 26 November 2026
- SQLite/PostgreSQL page acceptance revalidates persisted events and canonical block/slot journals, but parsed chain-specific finality facts are not all preserved in page material.
- Bitcoin event payload omits observed confirmations and cursor omits actual tip height; EVM cursor omits finality reference; Solana cursor omits exact finalized slot; XRPL cursor omits validated head and page finality reference.
- Provider response receipt hashes do not expose parsed provider response values. They cannot replace a typed, worker-derived finality snapshot.
- Master Audit Section 167 specifies the exact per-network fields and safe implementation sequence. Next implementation should add versioned finality snapshots and provenance binding before changing observation acceptance. No code behavior or production operation changed.

### Typed chain-finality snapshot v1 — local implementation, 26 November 2026
- NormalizedTransferEvent now carries an optional immutable OnChainFinalitySnapshot. Legacy events without it remain explicitly unknown.
- Bitcoin events carry CONFIRMED plus the configured minimum-confirmation policy; signed page cursor carries observed tip height and minimum. EVM events carry FINALIZED and exact finality reference; cursor carries finalized height/reference. Solana events carry FINALIZED/commitment=finalized; cursor carries finalized slot. XRPL events carry FINALIZED/validated=true; cursor carries validated head/reference.
- Event snapshots and page cursors are included in page material and its HMAC acceptance. Moving head values remain page-scoped to preserve stable event identity across replay/reorg.
- Focused ingestion and four worker suites: 85 passed. Full suite: 1,149 tests, 0 failures/errors, 72 skipped; compileall and diff-check PASS.
- Anchor observation-to-page/event binding is still not implemented. Do not call AUD-ONCHAIN-001 closed or activate Module 9.

### Finality snapshot validation hardening — 26 November 2026
- TDD caught and fixed Python bool-as-int acceptance for snapshot version. Constructor now rejects boolean/non-integer versions and malformed network/status/reference shapes, and enforces Bitcoin CONFIRMED/minimum-policy versus deterministic FINALIZED semantics.
- Full suite after this behavior change: 1,150 tests, 0 failures/errors, 72 skipped. compileall and diff-check PASS.

### Observation provenance fail-closed boundary — partial local implementation, 26 November 2026
- Added immutable cursor/page/event provenance reference and a first-party verifier that re-reads the durable page, verifies page HMAC, checks exact observation/event identity, current canonical state and per-network finality cursor facts.
- \`validate()\` and SQLite/PostgreSQL \`save_verified()\` now reject missing or invalid page provenance. Signed observation acceptance payload carries the provenance fingerprint and exact pointer.
- TDD reproduced the former fabricated-observation acceptance and verified rejection after the change. Focused intelligence + ingestion suites: 71 passed; compileall/diff-check PASS.
- Full suite currently RED: 1,150 tests, 3 failures, 64 errors, 72 skipped. Existing fixtures have not yet been updated to create signed page material; positive acceptance tests are still required.
- Read-time canonical revalidation after reopen, endpoint_id-to-receipt binding and migration of all worker/aggregation fixtures remain open. This is not production-ready and does not close AUD-ONCHAIN-001.

### Separate provider-observation page provenance — local implementation, 26 November 2026
- Anchor OnChainObservation records are now stored in a distinct immutable provider_observations page-material collection. They are not normalized transfer events and are not included in transfer-flow aggregation.
- OnChainObservationProvenance binds (cursor_key, page_id, observation_id). SQLite/PostgreSQL page commit validates scope, collector-issued provider receipts, unique observation identity and matching canonical block/slot evidence. Observation payload is covered by page ID and page HMAC.
- The first-party verifier compares the complete observation payload and mapping/asset/network/chain/provider/scope, then validates Bitcoin confirmations, EVM/BNB finalized height/reference, Solana finalized slot/commitment and XRPL validated head.
- Accepted-observation reads re-open the page and canonical journal on every read. Missing/tampered/reorged pages fail closed. Aggregation uses the stored provenance receipt and does not count anchor observations as transfer events.
- SQLite tests cover positive pages for all four supported network families through aggregation fixtures, reopen, reorg and tamper rejection. All on-chain tests: 283 passed, 21 skipped; full suite: 1,153 passed, 72 skipped. compileall/diff-check PASS.
- Still open: endpoint_id-to-endpoint-instance binding; provider authenticity (application HMAC is not a provider signature); PostgreSQL live/disposable test; production anchor-observation producer/composition; mapping source authority approval. Module 9 remains NO-GO.

### Approved endpoint identity binding — 26 November 2026
- Added stable approved endpoint IDs for configured Alchemy network endpoints and Chainstack XRPL.
- Page commit, persisted provider-observation page verification and first-party observation provenance validation now require exact endpoint_id match with provider/network. An unapproved alias is rejected before page acceptance.
- RED/GREEN regression completed. All on-chain tests: 284 passed, 21 skipped; full repository: 1,154 passed, 72 skipped; compileall/diff-check PASS.
- Endpoint identity is configuration-bound, not provider-authenticated. Provider-origin signatures/authorship, PostgreSQL server-level acceptance tests and production anchor-observation composition remain open. Module 9 remains NO-GO.

### PostgreSQL endpoint contract test — 26 November 2026
- Added an adapter-level regression that rejects an unapproved provider-observation endpoint_id before any PostgreSQL database operation.
- Full repository suite: 1,155 passed, 72 skipped. No PostgreSQL server or migration was run; PostgreSQL reopen/durability integration remains unverified.

### Production producer/composition status — 26 November 2026
- Re-scanned production source-tree callsites: no OnChainObservation producer, no runtime provider_observations page writer, and no production construction of on-chain mapping/ingestion stores. The only OnChainObservation reconstruction callsite is evidence deserialization.
- Thus page-level provenance is locally implemented/tested but not connected to scheduled/one-shot production execution. A dedicated approved observation producer and runtime composition remain required. Module 9 stays inactive and NO-GO.

### Recovery hardening addendum — 26 November 2026
- SQLite page commits now require an explicit `expected_cursor` snapshot, matching PostgreSQL. Stale replay with an old snapshot is rejected before it can update the checkpoint.
- Pending page acceptance recovery now isolates malformed persisted page material per page and continues to later pages. SQLite invalid JSON and malformed JSON shapes are enumerated for rejection; PostgreSQL malformed JSONB shapes are likewise surfaced to page-level validation. Rejected pages remain unsigned and pending.
- Verification: focused on-chain/store adapter suites 105 passed, 21 skipped; full repository 1,161 passed, 72 skipped; compileall and diff-check passed. No live PostgreSQL/provider/production DB operations were performed.
- These fixes do not activate Module 9 or close provider-authenticity, mapping-authority, response-memory-budget, runtime-composition, or operational readiness blockers.


## Pending page-acceptance recovery visibility — 27 November 2026

- Evidence-bearing pages (events, canonical block/slot evidence, or provider observations) must be visible to page-acceptance recovery even if their receipt batch is missing/empty. Such pages cannot be signed and are reported as rejected while remaining unsigned/pending for operator review.
- SQLite and PostgreSQL `list_pending_page_acceptances()` now share the page-material classifier. Receipt-bearing empty-result provider pages remain signable; pure checkpoint-only cursor-control pages are excluded.
- This is a local code/test correction. Focused suites: 159 passed, 21 skipped. Full repository suite: 1,164 passed, 72 skipped. Compileall and diff-check passed.
- PostgreSQL server-backed acceptance remains pending. No live Chainstack/Alchemy request or production runtime activation occurred. Module 9 remains NO-GO.

### Reorg-invalidated signed page lifecycle — 27 November 2026
- Owner-approved policy: retain the original HMAC envelope as immutable historical evidence; record a separate `INVALIDATED` lifecycle state, reason, timestamp and affected canonical evidence; expose it in an operator-review queue.
- SQLite and PostgreSQL reorg reconciliation now persist lifecycle invalidation in the same transaction as canonical event reconciliation. Matching page material is checked across canonical blocks, Solana slots, events and provider observations for the exact network/provider/scope/height.
- The invalidated queue returns the original key ID, payload digest and signature alongside old/new canonical evidence. The normal HMAC verifier still fails closed after canonical evidence changes.
- Invalidated pages are not part of unsigned-page recovery. No automatic delete, re-sign, reactivation, or remediation is allowed or implemented. Operator review alone grants no approval authority.
- PostgreSQL schema change is migration `0004_onchain_page_acceptance_lifecycle.sql`; server-backed migration/transaction/reopen acceptance has not been performed. Module 9 remains NO-GO.

### Reorg lifecycle parity addendum — 27 November 2026
- Invalidation now covers both explicit `reconcile_block()` and `commit_page(..., allow_recanonicalized=True)` when an existing canonical block or Solana slot journal entry is replaced. The invalidation write occurs in the same SQLite/PostgreSQL transaction as journal replacement and checkpoint advancement.
- SQLite broad reconciliation now queues all signed pages matching the network and any supplied provider/scope filters, not just one exact scope. A guarded JSON-expression index supports scope selection.
- The operator queue now returns the original signed payload and acceptance timestamp in addition to signature/key/digest and reorg evidence.
- Regressions cover block-only and slot-only pages, unscoped multi-scope reconciliation, SQLite rollback on lifecycle write failure, and PostgreSQL helper evidence serialization. PostgreSQL server-level commit/reorg concurrency and migration application remain unverified.

### Legacy provider receipt endpoint-profile enforcement — 27 November 2026
- Historical `ProviderResponseReceipt` objects without `endpoint_profile_sha256` remain deserializable for diagnostics, but SQLite/PostgreSQL page-material verification now rejects any receipt missing the approved provider/network endpoint-profile fingerprint. This prevents pending-page recovery from newly HMAC-signing pre-fingerprint receipt rows.
- No fingerprint is synthesized and no historical signature is rewritten or deleted. Legacy pages without the field fail closed at current page acceptance verification.
- This is configuration-bound endpoint identity only; it does not prove upstream provider authorship or TLS peer identity. Module 9 remains NO-GO.

### Receipt-key configuration parser hardening — 27 November 2026
- Module 9 HMAC keyring JSON now rejects duplicate JSON key IDs rather than silently applying last-value-wins semantics. Hex key values must be contiguous even-length hexadecimal strings; whitespace and noncanonical encodings fail closed.
- Existing minimum 32-byte key requirement, explicit trusted-key allowlist, active-key trust check and verification-only keyring mode are unchanged. Tests use synthetic keys only. Production key custody, KMS/HSM, rotation and revocation operations remain unapproved/unverified.


### Accepted-observation store dependency fallback — 27 November 2026
- `OnChainStore` and `PostgresOnChainStore` now use the constructor-bound ingestion store when `save_verified()` is called without a per-call `ingestion_store` argument. An explicit per-call store still takes precedence.
- Before the fix, the constructor-bound store was retained for read-time provenance checks but ignored by the writer's default argument, causing otherwise valid signed-page observation writes/idempotent retries to fail closed.
- TDD: SQLite RED/GREEN regression plus PostgreSQL no-database adapter contract pass. Full repository suite: **1,179 tests, 0 failures/errors, 72 skipped**. No PostgreSQL server or live provider was contacted.
- This is not a producer/runtime integration. No production `OnChainObservation` producer or on-chain composition root was found; Module 9 remains NO-GO.


### Open provenance-linkage finding — AUD-ONCHAIN-012 (27 November 2026)
- A signed provider-observation page currently binds the observation payload and a set of provider response receipt digests under the application HMAC, but it does not prove that a particular response digest actually contains/derives the parsed observation record.
- SQLite synthetic reproduction: a page with an approved endpoint identity, canonical block evidence and a collector-issued synthetic receipt was signed; page HMAC verification returned true and the observation was persisted as `ACCEPTED`, although no response bytes/parser binding was supplied.
- This is an application-provenance gap, not a cryptographic HMAC break or proof of live provider compromise. Endpoint-profile fingerprinting alone does not solve it.
- Required design: versioned deterministic parser over the exact captured response bytes, explicit receipt-to-record locator/digest linkage, verification before commit and on read, bounded response memory, and adversarial substitution/replay tests. No unsafe acceptance shortcut was introduced. See Master Audit Section 185, AUD-ONCHAIN-012. Module 9 remains NO-GO.


### Production producer/runtime composition audit — 27 November 2026
- Four chain workers exist but require explicit provider/store dependencies, mapping-specific monitored address/account seeds, start positions and bounded run/reorg controls. No production composition root or non-test worker invocation was found.
- `main.py` only accepts optional precomputed `onchain_aggregation_by_asset`; scheduled and one-shot paths do not build Module 9 dependencies. The aggregator requires per-mapping thresholds and current eligibility decisions, but no production threshold config exists and eligibility is generated later inside the candidate loop.
- No production anchor-observation producer/writer exists. Tests seed observations directly. AUD-ONCHAIN-012 separately blocks treating those records as provider-derived evidence.
- Missing owner-controlled inputs include mapping source authority/freshness, monitored addresses/accounts, start positions, per-mapping thresholds, provider authenticity, signer custody, approved backend and operational controls. No defaults or runtime wiring added. See Master Audit Section 186. Module 9 remains NO-GO.

### EVM token-standard/decoder compatibility gap — AUD-ONCHAIN-013 (27 November 2026)
- The shared mapping validator and EVM worker accept any non-empty EVM `token_standard`, while the worker always fetches ERC-20 Transfer logs and the normalizer labels them `eth_getLogs:ERC20.Transfer`.
- A mapping declaring a different/unsupported interface can therefore be ingested with ERC-20 semantics, risking incomplete or misleading transfer evidence. Solana and XRPL paths apply stricter standard gates; EVM does not.
- Initial supported EVM standard scope still needs explicit owner approval. The source-matrix proposal recommends ERC-20/BEP-20, but does not authorize implementation. See Master Audit Section 187. No code change made; Module 9 remains NO-GO.

### Aggregation threshold output-bound hardening — AUD-ONCHAIN-014 (27 November 2026)
- Aggregator thresholds previously accepted arbitrary positive finite Decimal exponents and long integer strings, while summary serialization uses fixed-point formatting. Extreme values could expand to unbounded output and exhaust resources.
- TDD RED/GREEN: regression rejects `1e256`, `1e-37`, and 257-character integer threshold inputs. Implementation bounds input text to 256 characters, effective scale to 36 fractional places and magnitude to 256 integer digits, without changing valid thresholds or choosing business values.
- Focused aggregation suite: 20 passed. Master Audit Section 188. Fix is local and pending review; Module 9 remains NO-GO.

### Bitcoin orphaned history-row handling — AUD-ONCHAIN-015 (27 November 2026)
- Alchemy address-history parsing deliberately returns negative-confirmation transactions as `ORPHANED`, but the worker previously raised on any row below its confirmation threshold, aborting the whole page and blocking valid confirmed rows/checkpoint progress.
- TDD RED/GREEN: mixed orphaned + confirmed page now skips only the orphaned row, records `transactions_skipped_orphaned`, and ingests the confirmed transaction. Pending/malformed rows still fail closed; no silent pending checkpoint advancement was introduced.
- Bitcoin worker suite: 10 passed. Master Audit Section 189. Fix local, pending review; Module 9 remains NO-GO.

### Bitcoin mainnet address checksum/network validation — AUD-ONCHAIN-016 (27 November 2026)
- Bitcoin worker monitored-address seeds, Alchemy address-history request addresses, and normalized input/output/monitored address metadata now share strict mainnet address validation.
- Supports mainnet P2PKH/P2SH Base58Check and SegWit Bech32/Bech32m (`bc` HRP), including checksum, version, witness-program length and strict padding checks. Testnet/regtest encodings and malformed checksums fail closed.
- TDD RED/GREEN covered invalid Base58Check, invalid Bech32 checksum, wrong-network `tb1`, and malformed input/output address metadata. Focused Bitcoin worker/provider/normalizer suites: 114 passed.
- This validates encoding/network only; it does not prove address ownership, source authority, provider authenticity or seed authorization. No live provider calls or production seed configuration. Master Audit Section 190; local fix pending review. Module 9 remains NO-GO.
- Verification update: full repository suite **1,188 tests, 0 failures/errors, 72 skipped**; compileall and `git diff --check` PASS (27 November 2026). Master Audit Section 190 verification addendum.

### XRPL issued-currency code validation — AUD-ONCHAIN-017 (27 November 2026)
- Shared currency-code validation now follows XRPL's documented standard-code character set and 160-bit hex rules. Uppercase `XRP`, all-zero code, XRP encoded as hex, standard codes encoded as hex, `0x00`-prefixed nonstandard hex, and invalid standard-code punctuation are rejected.
- Shared mapping validation, XRPL worker mapping validation and `normalize_xrpl_payment()` use the same validator. Documented nonstandard hex currency example remains accepted.
- TDD RED/GREEN: mapping, normalizer and worker-boundary regressions; focused suites: 66 passed. Primary specs: https://xrpl.org/docs/references/protocol/data-types/currency-formats and https://xrpl.org/docs/references/protocol/binary-format. Master Audit Section 191. Fix local/pending review; Module 9 remains NO-GO.
- Verification update: full repository suite **1,194 tests, 0 failures/errors, 72 skipped**; compileall and `git diff --check` PASS (27 November 2026). Master Audit Section 191 verification addendum.

- Latest consolidated verification after adding official BIP350 Bech32m regression vectors: Bitcoin worker suite 16 passed; full repository suite **1,196 tests, 0 failures/errors, 72 skipped** (27 November 2026; 75.894 seconds). BIP350 reference: https://bips.dev/350/.

### Solana Base58 key/signature byte-length validation — AUD-ONCHAIN-018 (27 November 2026)
- Solana provider public-key validation now requires exactly 32 decoded Base58 bytes; transaction signature validation requires exactly 64 decoded bytes. Character-length regex checks alone were insufficient (`z` repeated 44 decoded to 33 bytes; `z` repeated 90 decoded to 66 bytes).
- Base58 decoder is centralized in `onchain_providers.py` and shared by provider, ingestion and worker. Blockhash and account-key paths retain exact decoded-length checks.
- TDD RED/GREEN tests cover invalid 33-byte public-key encoding and invalid 66-byte signature, plus valid existing key fixtures. Focused provider/Solana worker/ingestion suites: 162 passed. Master Audit Section 192; local fix pending review; Module 9 remains NO-GO.
- Latest consolidated verification after AUD-ONCHAIN-018: full repository suite **1,199 tests, 0 failures/errors, 72 skipped**; compileall and `git diff --check` PASS (27 November 2026).

### EVM JSON-RPC canonical QUANTITY parsing — AUD-ONCHAIN-019 (27 November 2026)
- EVM adapter had two quantity parsers with permissive/non-identical rules. `_hex_int()` accepted leading zeroes and Python-tolerated signed/whitespace values; `_parse_hex_quantity()` also accepted noncanonical leading-zero and uppercase encodings.
- Added shared EIP-1474 canonical QUANTITY predicate (`0x0` or lowercase `0x` followed by nonzero first hex digit and remaining lowercase hex digits); applied to both parsers. Fixed-width hex DATA parsing remains separate.
- TDD tests cover malformed, leading-zero, uppercase, signed and whitespace encodings plus canonical valid values. Focused provider/EVM worker/ingestion suites: 166 passed. Master Audit Section 193; local fix pending review; Module 9 remains NO-GO.
- Latest verification after AUD-ONCHAIN-019: full repository suite **1,202 tests, 0 failures/errors, 72 skipped**; compileall and `git diff --check` PASS (27 November 2026).

### BNB finalized-header hash validation — AUD-ONCHAIN-020 (27 November 2026)
- `fetch_bnb_erc20_transfer_logs()` previously accepted any string as the finalized-header hash, unlike the BNB finalized-height/header methods and Ethereum log path. It could therefore proceed to retrieve logs after receiving a malformed finality anchor.
- TDD RED/GREEN: malformed `not-a-block-hash` was accepted and the adapter advanced to `eth_getLogs`; the adapter now requires an exact `0x`-prefixed 32-byte hexadecimal hash before continuing.
- Focused BNB provider tests: 3 passed. No live RPC call. Master Audit Section 194. Fix local/pending review; Module 9 remains NO-GO.
- Verification update for AUD-ONCHAIN-020: full repository suite **1,203 tests, 0 failures/errors, 72 skipped** (27 November 2026; 73.472 seconds); `compileall` and `git diff --check` PASS. No live RPC/provider or production DB access. Branch/HEAD unchanged, no staging or Git write.

### EVM canonical block-hash cross-check audit — 27 November 2026
- Reviewed the proposed per-log canonical-header hypothesis. The EVM worker independently fetches and validates every header in each requested range, then passes the corresponding header hash into the transfer normalizer.
- The normalizer compares the provider log's block hash to that canonical header hash; mismatches and provider-marked removed logs are stored as `REORGED`, not canonical. Provider decoding separately validates exact block-hash/transaction-hash shapes and range membership.
- Synthetic Ethereum and BNB worker checks injected a nonmatching log hash: both persisted `REORGED`; canonical-only reads returned zero events. No live provider calls.
- No defect or code change identified; see Master Audit Section 195. This does not resolve AUD-ONCHAIN-012 or production activation blockers. Module 9 remains NO-GO.

### Bitcoin transaction/block association audit — 27 November 2026
- Reviewed the history/detail/canonical-header chain. Transaction details must match the address-history txid, block height, block hash and block time; the worker independently fetches canonical block headers and the normalizer marks any history-vs-canonical hash mismatch `REORGED`, not canonical.
- Synthetic mismatch check yielded a REORGED event and zero canonical-only rows. No new defect or code change. This is not a cryptographic Merkle-inclusion proof and does not establish provider authorship. Master Audit Section 196.

### Solana finalized block parent-link verification — AUD-ONCHAIN-021 (27 November 2026)
- Solana `getBlock` exposes `previousBlockhash` and `parentSlot`; the adapter previously discarded the parent hash and did not require parent linkage. A synthetic wrong-parent-hash response passed the prior worker checks.
- Adapter validates and returns both parent fields. Worker verifies in-range parent slots and hashes; Section 216 additionally fetches external parent-slot headers, caches them, and checks their block hashes against `previousBlockhash`, closing the bounded-range boundary gap.
- TDD RED/GREEN regressions cover missing linkage, wrong parent hash and parent slot omitted from the produced-slot set. See Master Audit Section 197. Local fix pending review; Module 9 remains NO-GO.
- Verification addendum: focused provider + Solana worker suites **109 passed**; full repository suite **1,206 tests, 0 failures/errors, 72 skipped** (27 November 2026; 71.843 seconds); compileall and `git diff --check` PASS. No live provider/production DB access. Local fix pending review.

### XRPL parent-ledger continuity — AUD-ONCHAIN-022 (27 November 2026)
- The Chainstack adapter now validates and preserves XRPL `ledger.parent_hash`; the worker verifies every ledger after the first in its fixed contiguous range points to the immediately preceding ledger hash. A mismatch aborts before account transaction retrieval.
- The parent of the first ledger in the fixed range is not fetched/compared. TDD reproduced a wrong parent hash before the fix; the worker now fails with `XRPL_PARENT_HASH_MISMATCH`. Master Audit Section 198.

### XRPL outer/nested ledger identity consistency — AUD-ONCHAIN-023 (27 November 2026)
- Adapter now requires the response-level and nested ledger indexes to both equal the requested index and their 32-byte hashes to agree case-insensitively. Previously conflicting outer/nested identities were accepted. TDD mismatch fixtures now fail closed with `INVALID_PROVIDER_DATA`. Master Audit Section 199.
- Both changes are local and pending review; no live provider/production DB access. Module 9 remains NO-GO.
- AUD-ONCHAIN-022/023 verification: focused provider + XRPL worker suites **115 passed**; full repository suite **1,210 tests, 0 failures/errors, 72 skipped** (27 November 2026; 88.505 seconds); compileall and diff-check PASS. No live Chainstack or production DB access. Both fixes remain local/pending review.

### XRPL transaction-to-ledger hash binding — AUD-ONCHAIN-024 (27 November 2026)
- XRPL account_tx rows include a ledger_hash identifying the validated ledger that contains each transaction. The adapter previously did not require this field, and the normalizer checked the row's transaction hash/index but not its ledger hash against the independently fetched canonical header.
- Adapter now requires a valid 32-byte transaction-row ledger hash; normalizer requires exact case-insensitive equality with the independently verified canonical ledger hash. Mismatches fail before event creation.
- TDD RED reproduced acceptance of a mismatched row hash. GREEN tests cover provider rejection of missing/malformed row hashes, normalizer mismatch rejection, and worker no-event/no-checkpoint-advance behavior. Master Audit Section 200.
- Focused provider + XRPL worker + normalization suites: **134 passed**, 0 failures/errors. Full repository verification pending. No live provider/production DB/migration access. AUD-ONCHAIN-024 fixed locally pending review; Module 9 remains NO-GO.

- Verification addendum: focused suites **134 passed**; full repository suite **1,213 tests, 0 failures/errors, 72 skipped** (27 November 2026; 77.800 seconds). compileall and diff-check PASS. PostgreSQL DSN unset; no PostgreSQL server/live provider used. Local uncommitted fix only; Module 9 remains NO-GO.

### Solana failed-transaction page isolation — AUD-ONCHAIN-025 (27 November 2026)
- Solana RPC transaction metadata defines `meta.err` as null on success and string/object on failure. The normalizer previously raised for a failed transaction, aborting the entire address-history page and preventing unrelated successful transactions and checkpoint progress.
- Normalizer now returns no events for non-null `meta.err`; worker continues with the remaining page records. Mixed-page regression proves successful transfer persists and checkpoint advances while failed transaction produces no event. Master Audit Section 201.
- Focused Solana worker + normalization suites: **30 passed**. Full repository verification pending. No live provider/production DB access; local uncommitted fix only; Module 9 remains NO-GO.

### Solana explicit execution-status requirement — AUD-ONCHAIN-026 (27 November 2026)
- Solana RPC metadata defines `meta.err` as string/object/null; null means success. Normalizer previously used `meta.get("err")`, so an absent field was indistinguishable from explicit null and could be accepted as a successful transfer.
- Normalizer now requires the explicit `err` field. Missing status fails closed; non-null status is skipped under AUD-ONCHAIN-025. RED/GREEN regression proves missing status is rejected. Master Audit Section 202.
- Focused Solana worker + normalization suites: **31 passed**. Full repository verification pending. No live provider/production DB access; local uncommitted fix; Module 9 remains NO-GO.

- Verification addendum for AUD-ONCHAIN-025/026: focused Solana worker + normalization suites **31 passed**; full repository suite **1,215 tests, 0 failures/errors, 72 skipped** (27 November 2026; 85.067 seconds); compileall and diff-check PASS. Combined worktree includes prior local XRPL AUD-ONCHAIN-024 changes. PostgreSQL DSN unset; no live provider/DB/migration. Local uncommitted only; Module 9 remains NO-GO.

### Solana canonical transaction-index binding — AUD-ONCHAIN-027 (27 November 2026)
- Found that the worker ordered/paginated address-history records using `transactionIndex`, while the independently fetched finalized block used `getBlock(transactionDetails="none")`; that mode omits the canonical block transaction/signature list. The supplied signature therefore was not proven to occupy the reported index.
- TDD RED: a record with index 18 was accepted when the canonical block signature list contained only indexes 0–17; the checkpoint advanced.
- Fixed locally: block-header adapter requests `transactionDetails="signatures"`, validates unique 64-byte Base58 signatures and returns the ordered immutable list. Worker requires exact `block_signatures[transactionIndex] == address_history.signature` before normalization or checkpoint commit. Invalid index/signature fails with `SOLANA_TRANSACTION_INDEX_MISMATCH`.
- Signature lists are transient and excluded from durable slot journals. This is a same-provider RPC cross-check, not a cryptographic inclusion proof or provider-authenticity guarantee.
- Focused Solana worker + provider + normalization suites: **134 passed**, 0 failures/errors. Full repository suite: **1,217 tests, 0 failures, 0 errors, 72 skipped** (27 November 2026; 82.168 seconds). `compileall` and `git diff --check` PASS. Master Audit Section 203. Local/uncommitted; Module 9 remains NO-GO.

### EVM block-global log-index uniqueness — AUD-ONCHAIN-028 (27 November 2026)
- Found that the EVM worker normalized each `eth_getLogs` record independently without enforcing uniqueness of `(block_number, log_index)` across a bounded page. Two different transaction hashes could claim the same block-global log position and both be committed.
- TDD RED: duplicate `logIndex=4` in the same block, attached to different transaction hashes, was accepted and advanced the checkpoint.
- Fixed locally: worker tracks every `(block_number, log_index)` in the page and fails with `DUPLICATE_EVM_LOG_INDEX` before `commit_page`. The same numeric index in different blocks remains valid.
- Focused EVM worker + provider suites: **114 passed**, 0 failures/errors. Full repository suite: **1,218 tests, 0 failures, 0 errors, 72 skipped** (27 November 2026; 80.604 seconds). `compileall` and `git diff --check` PASS. Master Audit Section 204. Local/uncommitted; Module 9 remains NO-GO.

### TLS peer leaf-certificate evidence — AUD-ONCHAIN-001 (27 November 2026)
- Standard direct-only HTTPS transport already enforced default CA-chain and hostname verification and rejected redirects. It did not persist the actual leaf certificate observed by the TLS socket; configured endpoint-profile hashes are not peer-certificate identity.
- Fixed locally: default HTTPS handler uses an `HTTPSConnection`/`HTTPResponse` subclass to capture `getpeercert(binary_form=True)` only after the unchanged verified TLS handshake. SHA-256 of the DER leaf certificate is added to transport attestation and `ProviderResponseReceipt.tls_peer_certificate_sha256`. Default verified transport fails closed if the peer fingerprint is absent or malformed.
- Alchemy RPC/Bitcoin REST and Chainstack XRPL receipt paths propagate the field. Existing JSON/JSONB receipt storage persists it without schema migration; legacy receipts default to null. SQLite reopen/page-acceptance tests verify persistence. PostgreSQL integration test definitions were updated but no PostgreSQL server was contacted.
- Local TLS TDD verifies exact certificate fingerprint and preserves existing rejection of untrusted chain/hostname mismatch. Focused provider + ingestion suites: **164 passed**; combined provider + ingestion + PostgreSQL tests: **195 run, 21 skipped** (PostgreSQL DSN unset). Full repository suite: **1,220 tests, 0 failures/errors, 72 skipped**; `compileall` and `git diff --check` PASS.
- Residual: leaf fingerprint is observational evidence, not pinning, provider signature, or proof of application response truth. Alchemy's documented `X-Alchemy-Signature` HMAC applies to webhook requests, not standard JSON-RPC responses; do not treat it as RPC response authentication (https://support.alchemy.com/articles/1337366997-what-is-alchemy-signature-and-where-to-find-the-auth-token). Injected opener/transport factory remains a trusted seam; production composition, deployed trust store/egress and real provider peer capture remain unverified. AUD-ONCHAIN-001 remains PARTIALLY REMEDIATED / OPEN; Module 9 remains NO-GO. Master Audit Section 205.

### EVM transaction-index to canonical block binding — AUD-ONCHAIN-029 (27 November 2026)
- Found that `eth_getLogs` decoder ignored `transactionIndex`, and the worker discarded the ordered transaction hashes returned by its independently fetched `eth_getBlockByNumber(..., false)` block header. A log's `transactionHash` was therefore not checked against the canonical block transaction at its claimed index.
- TDD RED: valid-looking log with missing `transactionIndex` was accepted by the decoder.
- Fixed locally: decoder requires canonical `transactionIndex`; Ethereum and BNB block-header adapters validate unique ordered 32-byte transaction hashes and return them as a tuple; worker requires exact `transaction_hashes[transaction_index] == transaction_hash` before normalization. Mismatch/out-of-range raises `EVM_TRANSACTION_INDEX_MISMATCH` before page commit/checkpoint advancement.
- Hash list remains transient; raw block/log response digests remain in page receipt lineage. This is a same-provider RPC cross-check, not a cryptographic transaction-inclusion proof.
- Focused EVM worker + provider suites: **120 passed**, 0 failures/errors. Full repository suite: **1,224 tests, 0 failures/errors, 72 skipped** (27 November 2026; 74.380 seconds); `compileall` and `git diff --check` PASS. Official refs: https://ethereum.org/developers/docs/apis/json-rpc/ and https://ethereum.github.io/execution-apis/api/methods/eth_getLogs/ . Master Audit Section 206. Local/uncommitted; Module 9 remains NO-GO.

### XRPL cumulative opaque-marker checkpoint bound — AUD-ONCHAIN-030 (27 November 2026)
- The worker caps pages per invocation at 1–20 but persists every unique XRPL marker in `seen_markers` across restarts. The checkpoint validator checks only list type; the adapter checks only JSON serializability. There is no cumulative marker-count or encoded-byte budget.
- Synthetic local SQLite reproduction committed 100 successive unique cursors across 100 separate runs with `max_pages_per_run=1`; the checkpoint retained 100 markers and serialized to 2,340 bytes. This proves the per-run cap does not bound lifetime checkpoint growth.
- Each subsequent page serializes all prior markers for loop detection and rewrites the full history, causing checkpoint growth and repeated serialization/write amplification.
- No behavior change applied: define an approved finite count/byte budget and safe recovery contract before imposing arbitrary limits. Consider storing canonical marker digests for history while retaining the current opaque marker for resume, with backward-compatible checkpoint parsing.
- Master Audit Section 207. AUD-ONCHAIN-030 MEDIUM / CONFIRMED / OPEN. No live Chainstack, PostgreSQL, migration, secrets, publication or Git write operations. Module 9 remains NO-GO.


### EVM removed-log lifecycle gap — AUD-ONCHAIN-031 (27 November 2026)
- The decoder accepts `removed=true`, and the normalizer is intended to persist removed logs as `REORGED` tombstones. The EVM worker currently performs canonical block `transactionIndex` binding first and does so unconditionally. A removed-fork transaction absent from the replacement canonical block therefore fails with `EVM_TRANSACTION_INDEX_MISMATCH` before reaching the tombstone normalizer.
- Synthetic local SQLite reproduction: removed log at transaction index 0, replacement canonical block with a different hash and no transactions; worker rejected the page and stored no event. No live provider/network used.
- Do not bypass the check without defining how removed records are matched, how unknown removed identities are handled, and how old-fork timestamps/finality metadata are represented. The replacement canonical header must not be presented as evidence about the removed fork.
- Alchemy references: https://www.alchemy.com/docs/how-to-get-on-chain-events and https://www.alchemy.com/docs/reference/logs . Master Audit Section 208. AUD-ONCHAIN-031 MEDIUM / CONFIRMED / OPEN; no behavior change. Module 9 remains NO-GO.


### Solana cumulative opaque-token/checkpoint bound — AUD-ONCHAIN-032 (27 November 2026)
- The Solana worker limits seen-token count to 10,000 but does not limit individual token length or total checkpoint JSON size. The Alchemy adapter accepts any non-empty string cursor; SQLite checkpoint persistence canonicalizes and commits the entire cursor payload without a byte budget.
- Synthetic local SQLite reproduction committed a 250,000-character pagination token in a single-entry seen-token history; serialized checkpoint size was 500,287 bytes, with zero events. This proves the count cap is not a byte cap; it does not claim Alchemy emits such a token.
- The shared HTTP response reader has a configurable limit, but `ONCHAIN_MAX_PROVIDER_RESPONSE_BYTES` is not provisioned in the inspected runtime and no operational ceiling is approved. Injected worker providers are not inherently constrained by that HTTP reader. An explicit token/checkpoint budget remains necessary.
- No behavior change: define operator-approved token, aggregate checkpoint and history budgets; reject over-budget cursors atomically; define recovery. Consider bounded digest history while preserving the current opaque resume token and backward-compatible checkpoints.
- Master Audit Section 209. AUD-ONCHAIN-032 MEDIUM / CONFIRMED / OPEN. No live RPC, PostgreSQL server, migration, secrets or Git write operations. Module 9 remains NO-GO.


### Solana worker page-cardinality enforcement — AUD-ONCHAIN-033 (27 November 2026)
- Alchemy adapter already rejected raw responses with more records than requested `limit`, but the worker itself trusted any tuple length from its injected provider and did not enforce configured `page_size`.
- TDD RED: worker configured for one record accepted a synthetic two-record page from the injected provider and advanced the checkpoint to slot 305. Both records were explicit failed transactions to isolate cardinality/checkpoint behavior.
- Local fix: worker now rejects `len(page.records) > self.page_size` with `PAGE_LIMIT_EXCEEDED` before normalization/commit. Regression asserts no checkpoint or event rows are written. Existing adapter-level guard remains.
- Focused worker suite: **15 passed**. Full suite/compile/diff verification pending. Master Audit Section 210. AUD-ONCHAIN-033 LOW / CONFIRMED / REMEDIATED LOCALLY pending full verification; Module 9 remains NO-GO.


### Bitcoin/XRPL worker page-cardinality enforcement — AUD-ONCHAIN-034 (27 November 2026)
- Alchemy Bitcoin and Chainstack XRPL adapters already reject raw pages larger than requested limits, but worker provider boundaries did not enforce `self.page_size` for injected providers.
- TDD RED: Bitcoin `page_size=1` accepted two records; XRPL `page_size=10` accepted eleven records. Both workers advanced/accepted the oversized page without `PAGE_LIMIT_EXCEEDED`.
- Local fix: Bitcoin and XRPL workers reject oversized record tuples before transaction detail fetch/normalization and durable page commit. Tests prove no event rows; XRPL retains its initial fixed-range checkpoint without advancing its marker/ledger cursor.
- Focused Bitcoin + XRPL + Solana worker suites: **49 passed**. Full suite pending. Master Audit Section 211. AUD-ONCHAIN-034 LOW / CONFIRMED / REMEDIATED LOCALLY pending full verification; Module 9 remains NO-GO.


### Solana null block-time recovery contract — AUD-ONCHAIN-035 (27 November 2026)
- Official Solana `getBlock` defines `blockTime` as `i64 | null`; null means no estimated time is available. `getBlockTime` also returns null when no block time was recorded: https://solana.com/developers/docs/rpc/http/getblock and https://solana.com/developers/docs/rpc/http/getblocktime .
- Alchemy adapter now preserves protocol-valid null as `timestamp=None`; the Solana worker still requires a positive integer timestamp for every produced slot being journaled/ingested. An external parent with null time can be used for hash-only anchoring, while an in-range null-time slot raises `INVALID_PROVIDER_DATA` before address-history ingestion/checkpoint progress.
- This avoids fabricated timestamps but one null-time block stalls the entire bounded slot window; no fallback, quarantine, partial progress or replay contract exists. No behavior fix applied pending an owner-approved timestamp provenance and partial-progress policy. Do not infer time from slot or wall clock.
- Master Audit Section 212. AUD-ONCHAIN-035 MEDIUM / CONFIRMED / OPEN. No live RPC/DB/migration. Module 9 remains NO-GO.

### EVM finalized block parent-hash continuity — AUD-ONCHAIN-036 (27 November 2026)
- Ethereum and BNB block-header adapters previously discarded the protocol `parentHash`, and the worker did not prove adjacent fetched headers formed a continuous chain. A synthetic two-block range with a deliberately wrong second-block parent hash was accepted and checkpointed before the fix.
- TDD RED/GREEN: adapters now require and return a valid 32-byte `parent_hash`; the EVM worker independently validates it and checks each fetched header points to the preceding fetched block hash. Resumed ranges fetch the immediately preceding header as an anchor; the check spans the worker's consecutive 10-block provider subranges in one run.
- Discontinuity fails with `EVM_PARENT_HASH_MISMATCH` before event or checkpoint commit. Provider tests cover missing/malformed parent hashes for Ethereum and BNB. Parent hashes are transient and not added to the durable journal.
- This is same-provider chain-continuity evidence, not consensus verification, block-header hash recomputation, or provider-authenticity proof. The configured seed block has no prior trusted anchor. Official references: https://ethereum.github.io/execution-apis/api/methods/eth_getBlockByNumber/ and https://eips.ethereum.org/EIPS/eip-1474 .
- Focused EVM worker + provider suites: **123 passed**, 0 failures/errors. Full repository verification pending. Master Audit Section 213. Local/uncommitted; Module 9 remains NO-GO.

### Bitcoin block-header parent-hash continuity — AUD-ONCHAIN-037 (27 November 2026)
- Bitcoin `getblockheader` exposes `previousblockhash` when a parent exists. The adapter previously discarded it; the worker did not validate adjacent headers in its fixed range. RED reproduction: a second block claimed a parent hash different from the first block's hash, but the worker accepted and advanced its checkpoint.
- TDD RED/GREEN: adapter now validates and returns `previous_block_hash`; worker validates the injected-provider field and checks each range's parent hash against the preceding header. Resumed ranges fetch the immediately preceding header as a continuity anchor. Genesis height 0 legitimately omits `previousblockhash`; the adapter permits absence only there.
- Mismatch fails with `BITCOIN_PARENT_HASH_MISMATCH` before event/checkpoint commit. Tests cover fixed-range discontinuity, resumed-range anchor mismatch, malformed/missing non-genesis parent hash and genesis omission. Parent hashes remain transient; no journal schema change.
- This is same-provider continuity validation, not proof-of-work/consensus verification, Merkle inclusion, header-hash recomputation or provider-authenticity proof. Official references: https://developer.bitcoin.org/reference/rpc/getblockheader.html and https://github.com/bitcoin/bitcoin/blob/master/src/rpc/blockchain.cpp .
- Focused Bitcoin worker + provider suites: **129 passed**, 0 failures/errors; compileall and diff-check PASS. Full repository verification pending. Master Audit Section 214. Local/uncommitted; Module 9 remains NO-GO.

- **AUD-ONCHAIN-022 boundary addendum (27 November 2026):** The original in-range XRPL parent check did not validate the first ledger against its predecessor. TDD reproduced acceptance of a first-ledger parent mismatch. Worker now fetches `range_start - 1` for every fixed range starting above ledger 1 and checks the first ledger's `parent_hash` against that header hash before `account_tx`; the existing in-range loop remains. Focused XRPL worker + provider suites: **128 passed**. Master Audit Section 215. Local/uncommitted; Module 9 remains NO-GO.

### Solana external parent-slot anchor — AUD-ONCHAIN-021 boundary addendum (27 November 2026)
- The initial parent-link fix checked parents only when they were inside the bounded slot range. RED reproduced acceptance of a wrong `previousBlockhash` for the first produced slot whose `parentSlot` was outside the range.
- Worker now fetches external parent-slot headers, validates exact slot/hash identity, caches parent hashes and compares them with child `previousBlockhash`. Missing parent fails with `SOLANA_PARENT_SLOT_MISSING`; mismatch fails with `SOLANA_PARENT_HASH_MISMATCH` before address history/checkpoint commit.
- Provider adapter preserves protocol-valid null `blockTime` as `timestamp=None` for identity-only external-parent checks. In-range produced slots still require positive time and fail closed on null; AUD-ONCHAIN-035 remains open. No time is fabricated and no schema migration is required.
- Focused Solana worker + provider suites: **129 passed**, 0 failures/errors. Tests prove an external parent with null time still anchors by hash, while an in-range null-time slot remains fail-closed. Full repository suite: **1,239 tests, 0 failures/errors, 72 skipped**; compileall and diff-check PASS. `TEST_POSTGRES_DSN` unset; no PostgreSQL server contacted. Master Audit Section 216. Local/uncommitted; Module 9 remains NO-GO.


### PostgreSQL canonical timestamp parity — AUD-ONCHAIN-038 (27 November 2026)
- Found a SQLite/PostgreSQL validation asymmetry: SQLite parsed canonical block and produced Solana slot timestamps and required timezone awareness; PostgreSQL checked only for non-empty strings.
- TDD RED: timezone-naive EVM block time and Solana produced-slot time both passed PostgreSQL validation and reached the fake connection's transaction boundary. No real database was contacted.
- Fixed locally: PostgreSQL now parses both timestamp fields as ISO-8601 and requires a timezone offset, matching SQLite. Invalid/naive timestamps fail before transaction; skipped Solana slots retain null hash/time semantics. No schema migration.
- Focused RED/GREEN regressions: **2 passed**; PostgreSQL contract + SQLite ingestion suites: **69 passed**. Full repository suite: **1,241 tests, 0 failures/errors, 72 skipped** (27 November 2026; 75.371 seconds). TEST_POSTGRES_DSN unset; no PostgreSQL server contacted. compileall and git diff --check PASS. Master Audit Section 217. Module 9 remains NO-GO.


### Solana null blockTime quarantine and replay — AUD-ONCHAIN-035 (27 November 2026)
- Owner-approved policy implemented locally: preserve the raw address-history transaction in durable quarantine with signature, slot, transaction index, block hash, provider transaction time (if any), and original observed_at. Do not fabricate canonical time.
- Unknown-time transactions are excluded from canonical events. Other known-time slots can proceed only after quarantine/page/checkpoint commit is atomic.
- Recovery re-fetches finalized slot header; requires same block hash and exact signature/index binding; uses the subsequently available canonical block time; commits canonical event + REPLAYED state atomically. Replay batch is bounded by existing configured page_size (max 100).
- Slot journal supports only same-hash null-to-known time enrichment; known-to-null regression and conflicting known times fail closed. Page acceptance material retains source-quarantine linkage and supports historical snapshot validation through this monotonic enrichment.
- SQLite implementation and worker path covered by tests. PostgreSQL migration 0005_solana_timestamp_quarantine.sql added and parser-validated (4 statements), but NOT APPLIED; no PostgreSQL server contacted.
- End-to-end quarantine/replay test PASS; Module 9 on-chain suite **369 tests, 0 failures/errors, 21 skipped**; full repository suite **1,243 tests, 0 failures/errors, 72 skipped** (78.274 seconds). An injected SQLite trigger failure proves replay transaction rollback leaves the quarantine row pending and the checkpoint/slot journal unchanged; retry succeeds after removing the trigger. compileall and diff-check PASS. TEST_POSTGRES_DSN unset.
- Remaining: PostgreSQL runtime/migration acceptance, quarantine retention/backlog/alert budget, and explicit operator/reorg resolution when slot hash or signature position changes. AUD-ONCHAIN-035 behavior locally remediated; operational/DB acceptance remains open. Module 9 NO-GO.


### Duplicate JSON member rejection — AUD-ONCHAIN-039 (27 November 2026)
- Both provider REST and JSON-RPC transports previously used Python's default JSON object parsing, which silently applies last-key-wins semantics when an object repeats a member name. Synthetic responses proved duplicate `status` and duplicate RPC `result` fields were accepted.
- TDD RED/GREEN: added a shared `object_pairs_hook` that rejects duplicate member names at every object depth; both transport paths convert the parse failure to `INVALID_JSON`. Unique-member responses retain existing parsing behavior.
- RED/GREEN duplicate-member regression: 1 passed after fix; focused provider suite: **112 passed**; full repository suite: **1,244 tests, 0 failures/errors, 72 skipped** (76.923 seconds). No live provider/network. Master Audit Section 219.
- This removes parser ambiguity; it does not prove provider authorship or close response-to-record provenance. Module 9 remains NO-GO.


### Strict JSON numeric token parsing — AUD-ONCHAIN-040 (27 November 2026)
- Python's default JSON parser accepted `NaN` and `Infinity` tokens as non-finite floats. Synthetic REST and JSON-RPC responses proved those non-standard numeric tokens crossed the provider parser boundary.
- TDD RED/GREEN: `_reject_nonstandard_json_constant()` is now passed as `parse_constant` to both response decoders; non-finite tokens fail as `INVALID_JSON`. This is strict syntax validation, not a new business numeric range.
- Regression covers REST NaN and RPC Infinity; focused provider suite **113 passed**, 0 failures/errors; full repository suite **1,245 tests, 0 failures/errors, 72 skipped** (76.362 seconds). Master Audit Section 220. No live provider/network. Module 9 remains NO-GO.


### Deeply nested provider JSON handling — AUD-ONCHAIN-041 (27 November 2026)
- Bounded provider responses with 1,100 nested arrays caused Python JSON decoding to raise `RecursionError`, which escaped the transport's stable provider error contract. The payload was below the configured byte limit.
- TDD RED/GREEN: REST and JSON-RPC regression fixture now verifies deeply nested content is normalized to `ProviderTransportError(INVALID_JSON)`. Both decode handlers catch `RecursionError`; the process-wide recursion limit is unchanged.
- Focused provider suite: **114 passed**; full repository suite: **1,246 tests, 0 failures/errors, 72 skipped** (78.870 seconds). Master Audit Section 221. No live provider/network. Module 9 remains NO-GO.

### REST query argument validation — AUD-ONCHAIN-042 (27 November 2026)
- `ReadOnlyJsonRpcTransport.get_json()` used `query = query or {}`, which silently converted falsey non-dictionary arguments (empty list/tuple/string, zero and false) into an empty query before the type validator.
- TDD RED reproduced all five invalid-input cases being accepted by an in-memory transport fixture. The fix defaults only `None` to `{}`; every other non-dictionary value reaches and fails the existing query contract validator. Explicit `{}` remains valid.
- Focused provider suite: **115 passed**. Full repository suite: **1,247 tests, 0 failures/errors, 72 skipped** (27 November 2026; 72.014 seconds). No live provider/network. Master Audit Section 222. Module 9 remains NO-GO.

### Provider receipt timestamp integrity — AUD-ONCHAIN-043 (27 November 2026)
- `ProviderResponseReceipt` previously accepted any non-empty `received_at` string, including malformed text and timezone-naive ISO-8601. That left provider evidence without a reliably interpretable instant.
- TDD RED reproduced acceptance of `not-a-timestamp` and `2026-11-27T12:00:00`. The model now parses ISO-8601 and requires a timezone offset; UTC `Z` remains valid and the original string is preserved. Legacy rows without endpoint fingerprints remain compatible when timestamps are valid.
- Focused provider suite: **116 passed**. Full repository suite: **1,248 tests, 0 failures/errors, 72 skipped** (27 November 2026; 73.667 seconds). Master Audit Section 223. No live provider/database. Module 9 remains NO-GO.

### Persisted receipt sequence validation — AUD-ONCHAIN-044 (27 November 2026)
- SQLite and PostgreSQL `list_page_receipts()` checked page and receipt digests but did not independently require per-page receipt sequence numbers to be contiguous and ordered. A modified receipt payload with a recomputed digest could be returned with a sequence gap.
- SQLite TDD RED changed sequence 1 to 2 and recomputed the receipt digest; the reader accepted it. Both adapters now validate list shape and exact 1-based sequence continuity independently for each page. Empty receipt lists remain valid. A synthetic PostgreSQL contract regression exercises the parity path without connecting to a server.
- Focused ingestion/PostgreSQL adapter suites: **97 tests, 0 failures/errors, 21 skipped**. Full repository suite: **1,250 tests, 0 failures/errors, 72 skipped** (27 November 2026; 76.778 seconds). Master Audit Section 224. Module 9 remains NO-GO.

### Persistence acceptance and recovery boundary review — Section 225 (27 November 2026)
- Reviewed pending-page recovery, trusted-key gating, HMAC page acceptance, SQLite immediate-transaction validation, PostgreSQL evidence lock order and locked page revalidation, malformed/unreceipted page visibility, and checkpoint-only page exclusion.
- No additional independently reproducible defect confirmed in this bounded review; finding register contained **49 unique IDs at that checkpoint**. Focused ingestion + PostgreSQL adapter + store protocol suites: **111 tests, 0 failures/errors, 21 skipped**.
- PostgreSQL remains synthetic adapter-contract coverage only; no server or production database contacted and no migration applied. This review is not production certification; Module 9 remains NO-GO.

### Canonical reorg invalidation lifecycle — Section 226 (27 November 2026)
- Reviewed SQLite/PostgreSQL signed-page invalidation, immutable historical signatures, affected old/current canonical hashes, scoped/unscoped reconciliation, reorg idempotency, block-only and Solana-slot-only pages, and transaction rollback on lifecycle-write failure.
- Existing focused ingestion + PostgreSQL adapter + store protocol suites: **111 tests, 0 failures/errors, 21 skipped**. No additional independently reproducible defect confirmed; finding register contained 49 unique IDs at that checkpoint.
- PostgreSQL coverage remains synthetic adapter-contract only; no server/database/migration application. Module 9 remains NO-GO.

### PostgreSQL latest-observation ordering integrity — AUD-ONCHAIN-045 (27 November 2026)
- PostgreSQL `get_latest_accepted_observation()` ordered by the denormalized `observed_at` column, which is not covered by the signed observation payload. A synthetic fixture proved that independently drifting this column could cause an older signed observation to be selected ahead of a newer signed observation.
- TDD RED/GREEN: lookup now parses each candidate timestamp from the signed payload, skips malformed timestamps, and selects the maximum `(observed_at, observation_id)` tuple. This avoids trusting the mutable projection column and prevents one malformed timestamp from aborting all candidate selection. SQLite already selects by the signed payload timestamp.
- Synthetic adapter regression passed. Combined PostgreSQL adapter + on-chain intelligence + ingestion + store protocol suites: **148 tests, 0 failures/errors, 21 skipped**. Full repository suite: **1,251 tests, 0 failures/errors, 72 skipped** (27 November 2026; 76.520 seconds). `compileall` and `git diff --check` PASS after documentation updates. No PostgreSQL server contacted; Module 9 remains NO-GO.

### Accepted observation read-back and reorg revocation — Section 228 (27 November 2026)
- Reviewed SQLite/PostgreSQL latest-observation and individual-observation reads: signed receipt verification, trusted-key checks, exact page observation matching, mapping binding, canonical block/slot revalidation, restart recovery and reorg revocation.
- SQLite observation-intelligence suite: **36 tests, 0 failures/errors**. Existing SQLite restart/reorg tests verify a reorg removes the observation from latest-accepted reads and changes individual read-back to `UNVERIFIED`.
- No additional defect confirmed. PostgreSQL restart/reorg integration remains DSN-gated and was not run; no server contacted. Module 9 remains NO-GO.

### Verified observation insert/idempotency — Section 229 (27 November 2026)
- Reviewed SQLite/PostgreSQL verified-write gates, mapping and observation duplicate handling, ID collision protection, constructor-bound ingestion store, and transactional insert/rollback boundaries.
- `tests.test_onchain_intelligence` + PostgreSQL adapter contract tests: **48 tests, 0 failures/errors**. No new independently reproducible defect confirmed.
- PostgreSQL runtime concurrency/crash acceptance remains unverified without a dedicated isolated server; no PostgreSQL/production database contacted. Module 9 remains NO-GO.

### Verified mapping projection consistency — AUD-ONCHAIN-046 (27 November 2026)
- SQLite and PostgreSQL `list_verified_mappings()` filtered on denormalized `network_id` but did not compare stored `mapping_id`, `asset_id`, and `network_id` columns with the mapping payload. A Bitcoin payload paired with an Ethereum scalar network column could be returned by an Ethereum-filtered list.
- TDD RED/GREEN: both adapters now select the three scalar identity fields and omit any row whose payload identity differs. Mapping status and `_validate_mapping()` checks remain. No schema change.
- SQLite + synthetic PostgreSQL regressions: **2 passed**. Focused on-chain intelligence + PostgreSQL adapter + protocol suites: **89 tests, 0 failures/errors, 21 skipped**. Full repository suite: **1,253 tests, 0 failures/errors, 72 skipped** (27 November 2026; 79.626 seconds); compileall and git diff-check PASS. Module 9 remains NO-GO.


### EVM token contract address syntax — AUD-ONCHAIN-047 (27 November 2026)
- Mapping validation previously accepted any non-empty EVM token contract string. A TDD RED test proved `not-an-evm-address` passed `_validate_mapping()`.
- Ethereum and BNB Smart Chain non-native mappings now require a `0x` prefix plus exactly 40 hexadecimal characters; malformed prefix/length/characters fail with `EVM_TOKEN_CONTRACT_ADDRESS_INVALID`. Native and non-EVM mapping branches are unchanged.
- This validates only address syntax, not deployment, ownership, token standard or official source provenance. AUD-ONCHAIN-002 remains open pending approved source authority and freshness policy.
- Focused on-chain intelligence tests: **38 passed**. Full repository suite: **1,254 tests, 0 failures/errors, 72 skipped** (27 November 2026; 82.804 seconds). Module 9 remains NO-GO.


### Solana mint address syntax — AUD-ONCHAIN-048 (27 November 2026)
- Central mapping validation previously accepted any non-empty Solana mint string; RED proved `not-a-solana-mint` passed `_validate_mapping()`.
- It now uses the existing base58 public-key predicate and requires a value decoding to exactly 32 bytes, returning `SOLANA_TOKEN_MINT_INVALID` otherwise. The check applies centrally at the mapping/store boundary.
- This is only public-key syntax/length validation, not proof that the account exists, is a mint account, uses an approved token program, or is the official asset. AUD-ONCHAIN-002 remains open.
- Focused on-chain intelligence tests: **39 passed**. Full repository suite: **1,255 tests, 0 failures/errors, 72 skipped** (27 November 2026; 75.405 seconds). Module 9 remains NO-GO.


### Solana token-standard alignment — AUD-ONCHAIN-049 (27 November 2026)
- Central mapping validation previously accepted any non-empty Solana token-standard label, while the active Solana worker and normalizer support `SPL_TOKEN` only. RED reproduced acceptance of a valid 32-byte mint paired with `ERC20`.
- Central validation now requires `token_standard == SPL_TOKEN` and rejects unsupported labels with `SOLANA_TOKEN_STANDARD_UNSUPPORTED`, aligning storage/acceptance with the implemented worker path. Additional Solana token standards require their own supported decoders and tests.
- Focused on-chain intelligence: **40 passed**; Solana worker + normalization: **36 passed**. Full repository suite: **1,256 tests, 0 failures/errors, 72 skipped** (27 November 2026; 78.627 seconds). Module 9 remains NO-GO.


### EVM token-standard alignment — AUD-ONCHAIN-050 (27 November 2026)
- The active EVM worker ingests ERC-20 Transfer logs only, but central mapping validation and worker validation accepted arbitrary non-empty token-standard labels. RED reproduced acceptance of `ERC721` at both boundaries.
- Both boundaries now accept only the existing ERC-20 labels `ERC20` and `ERC-20`; central validation returns `EVM_TOKEN_STANDARD_UNSUPPORTED` for other standards. This does not claim ERC-721/ERC-1155 ingestion.
- Focused on-chain intelligence + EVM worker + aggregation suites: **77 tests, 0 failures/errors**. Full repository suite: **1,258 tests, 0 failures/errors, 72 skipped** (27 November 2026; 78.874 seconds). Module 9 remains NO-GO.


### EVM token-standard type validation — AUD-ONCHAIN-051 (27 November 2026)
- The strict ERC-20 allowlist initially used set membership before checking type. TDD RED reproduced `TypeError` for list/dict values in untrusted mapping data.
- Central mapping validation and EVM worker now type-check the token-standard value before allowlist membership; malformed types are rejected cleanly. Supported labels remain `ERC20` and `ERC-20` only.
- Focused on-chain intelligence + EVM worker: **58 tests, 0 failures/errors**. Full repository suite: **1,259 tests, 0 failures/errors, 72 skipped** (27 November 2026; 76.372 seconds). Module 9 remains NO-GO.


### EVM and XRPL worker decimals boundary validation — AUD-ONCHAIN-052 (27 November 2026)
- EVM and XRPL worker `_validate_mapping()` guards did not independently enforce the already-existing central/normalizer invariant that decimals must be a non-boolean integer in the range `0..36`. A malformed mapping from a substituted/faulty mapping-store boundary passed worker validation and failed later in normalization.
- TDD RED reproduced eight invalid cases across both workers (`True`, `-1`, `37`, and string values). Both worker guards now enforce the existing integer/range contract before worker processing. Bitcoin's fixed 8-decimal check and Solana's existing range check were already present and remain unchanged.
- Focused EVM + XRPL worker suites: **36 tests, 0 failures/errors**. Full repository suite: **1,261 tests, 0 failures, 0 errors, 72 skipped** (27 November 2026; 76.536 seconds). `python -m compileall -q layer1 tests` and `git diff --check` PASS. This does not prove decimals match authoritative on-chain metadata. Module 9 remains NO-GO.

### EVM, Bitcoin and XRPL provider-scope review — Section 237 (27 November 2026)
- Bounded review of EVM provider-page/record network-contract-range binding, canonical transaction-index checks and duplicate log positions; Bitcoin address-history page binding, pagination, confirmation, canonical-header and transaction-detail checks; and XRPL account-page/fixed-ledger binding, validated headers, parent linkage and delivered-amount issuer/currency matching.
- No additional independently reproducible defect confirmed in these reviewed paths. This does not prove provider authenticity, official asset mapping, complete address indexing, chain-wide coverage or live-provider correctness. AUD-ONCHAIN-002 and existing operational-policy blockers remain unresolved; Module 9 remains NO-GO.

### Solana finalized address-page and transaction-position review — Section 238 (27 November 2026)
- Reviewed finalized provider/network/address binding, bounded page size, fixed slot/header evidence, transaction-index/signature matching, duplicate and descending-position checks, cursor replay protection, and null-block-time quarantine with atomic slot journal/events/receipts/checkpoint persistence.
- Existing tests cover quarantine replay and transaction rollback on quarantine persistence failure. No additional independently reproducible defect confirmed in this bounded review. The hard-coded 10,000 pagination-token cap and quarantine operational limits remain policy blockers AUD-ONCHAIN-032/AUD-ONCHAIN-035; no policy was invented. Module 9 remains NO-GO.


### XRPL opaque pagination marker validation — AUD-ONCHAIN-053 (27 November 2026)
- Worker cursor fingerprinting previously called `json.dumps(..., allow_nan=False)` directly. A provider `next_cursor` containing NaN raised raw `ValueError`; a corrupted persisted marker was forwarded to the provider before it was rejected.
- TDD RED reproduced both cases. The worker now uses a guarded canonical marker serializer that raises controlled `ProviderTransportError` (`INVALID_PROVIDER_DATA` for provider output; `INVALID_CHECKPOINT` for persisted state). Persisted current/history markers are validated before provider page requests. Valid opaque JSON marker structures remain unparsed.
- XRPL worker suite: **23 tests, 0 failures/errors**. No marker-size/depth/count budget was invented; AUD-ONCHAIN-030 remains an owner-policy blocker. Module 9 remains NO-GO.


### Bitcoin transaction-detail block metadata type validation — AUD-ONCHAIN-054 (27 November 2026)
- Bitcoin normalization compared transaction-detail `blockHeight`/`blockTime` to integer history metadata without checking the detail field types. Python equality allowed `True == 1` and `1.0 == 1`, so malformed booleans/floats could pass in edge cases.
- TDD RED reproduced bool/float aliases for both fields. Normalization now requires each detail field to be a non-boolean positive integer before exact history comparison.
- Focused Bitcoin normalization + worker suites: **32 tests, 0 failures/errors**. Full repository suite: **1,265 tests, 0 failures, 0 errors, 72 skipped** (27 November 2026; 75.452 seconds). `python -m compileall -q layer1 tests` and `git diff --check` PASS. Provider authenticity and authoritative chain evidence remain separate requirements; Module 9 remains NO-GO.


### EVM logIndex provider-boundary validation — AUD-ONCHAIN-055 (27 November 2026)
- EVM worker record validation checked `transaction_index` strictly but did not independently check `log_index`. A malformed/substituted provider record with `log_index=True` passed normalization and leaked a raw ingestion-store `ValueError` during commit (nothing persisted).
- TDD RED reproduced the exception-boundary leak. The worker now requires `log_index` to be a non-boolean, non-negative integer before duplicate-position tracking and normalization, returning controlled `INVALID_PROVIDER_DATA` for malformed records.
- Focused EVM worker suite: **18 tests, 0 failures/errors**. This does not establish provider authenticity or change the unresolved removed-log/tombstone policy (AUD-ONCHAIN-031). Module 9 remains NO-GO.


### EVM transfer-log record shape validation — AUD-ONCHAIN-056 (27 November 2026)
- EVM worker did not validate all provider record fields before normalization. TDD RED injected `from_address=None`; `.lower()` leaked an `AttributeError` from the normalizer.
- Worker now validates network-id type, EVM contract/from/to address syntax, amount string, non-boolean non-negative block/log/transaction indices, block/transaction hash syntax, and boolean removed flag before dereferencing record fields. Invalid records fail closed with `INVALID_PROVIDER_DATA`; canonical block transaction binding and duplicate log-position checks remain.
- Focused EVM worker + provider suites: **135 tests, 0 failures/errors**. This does not prove provider authenticity or settle removed-log/tombstone policy (AUD-ONCHAIN-031). Module 9 remains NO-GO.


### Bitcoin history identity validation before detail lookup — AUD-ONCHAIN-057 (27 November 2026)
- Worker used confirmed address-history `txid` to fetch transaction details before validating its exact identity. TDD RED injected `txid=None`; worker called the detail provider and surfaced its lookup failure as `TIMEOUT` instead of rejecting malformed provider data.
- Worker now validates confirmed record txid, block height/hash/time, confirmations and finality before detail lookup. Invalid identity/shape returns `INVALID_PROVIDER_DATA`; fixed-range/minimum-confirmation and independent detail-to-history checks remain. ORPHANED records remain skipped.
- Focused Bitcoin worker + provider suites: **136 tests, 0 failures/errors**. This does not prove provider authenticity or complete address indexing. Module 9 remains NO-GO.


### Bitcoin maximum-money validation — AUD-ONCHAIN-058 (27 November 2026)
- Bitcoin output normalization accepted any non-negative decimal satoshi string without enforcing the 21,000,000 BTC maximum-money ceiling. TDD RED proved acceptance of both an individual output above `2,100,000,000,000,000` satoshis and an aggregate output sum above that limit.
- Normalization now enforces the protocol maximum on each output and the cumulative transaction output sum. Oversized decimal strings are compared canonically before integer conversion; zero outputs remain allowed. No dust threshold or other monetary policy was added.
- Bitcoin output normalization: **15 tests, 0 failures/errors**; Bitcoin worker + provider: **136 tests, 0 failures/errors**. This is a monetary-range invariant check, not full transaction consensus validation. Module 9 remains NO-GO.


### EVM ERC-20 uint256 amount bound — AUD-ONCHAIN-059 (27 November 2026)
- EVM worker and normalizer required decimal digits but did not enforce the ERC-20 Transfer event's 32-byte uint256 amount range. TDD RED injected `2^256`; worker accepted and persisted the impossible amount.
- Shared `_is_uint256_decimal()` now checks canonical decimal text against `2^256-1` without parsing unbounded untrusted integers. EVM worker and normalizer both enforce `0..2^256-1`. No token supply or asset-specific cap was inferred.
- Focused EVM worker + ingestion suites: **85 tests, 0 failures/errors**. This validates ABI width only, not token supply or mapping authority. Module 9 remains NO-GO.


### EVM canonical quantity and Solana SPL amount encoding review — Section 246 (27 November 2026)
- Re-reviewed EVM JSON-RPC quantity grammar and Solana SPL Transfer/TransferChecked amount decoding. EVM parser enforces canonical EIP-1474 quantity syntax; SPL amount extraction reads exactly eight little-endian bytes (u64) after exact instruction-layout checks, with TransferChecked decimals bound to the verified mapping.
- Focused provider + Solana normalization + Solana worker + ingestion suites: **217 tests, 0 failures/errors**. No additional independently reproducible defect confirmed. Token-2022, provider authenticity, complete chain coverage and source authority remain outside this bounded review. Module 9 remains NO-GO.


### Solana raw full-transaction slot type validation — AUD-ONCHAIN-060 (27 November 2026)
- Normalizer compared `raw["slot"]` directly with `history.slot`; Python `True == 1` allowed a boolean raw slot to match integer slot 1. TDD RED reproduced acceptance and event emission.
- Normalizer now requires raw slot to be a non-boolean integer exactly matching the validated history slot, otherwise `SOLANA_SLOT_MISMATCH`.
- Focused Solana normalization + worker + provider suites: **153 tests, 0 failures/errors**. Provider authenticity remains a separate requirement. Module 9 remains NO-GO.


### Solana address-table lookup u8 index bound — AUD-ONCHAIN-061 (27 November 2026)
- Solana lookup metadata previously accepted any non-negative integer index; TDD RED showed `writableIndexes=[256]` passed and a transfer was emitted despite lookup indexes being u8 protocol values.
- `_solana_account_keys()` now restricts lookup indexes to non-boolean integers `0..255`, retaining existing loaded-address count/order checks.
- Focused Solana normalization + worker + provider suites: **154 tests, 0 failures/errors**. This does not verify lookup-table account state or authority. Module 9 remains NO-GO.


### Solana address-table lookup account-key validation — AUD-ONCHAIN-062 (27 November 2026)
- Solana normalizer checked lookup index arrays and resolved-address counts but did not validate `addressTableLookups[].accountKey`. TDD RED injected `not-a-solana-pubkey`; a transfer was still emitted.
- `_solana_account_keys()` now requires each lookup account key to be a 32-byte base58 public key using the existing predicate. Existing u8 index and loaded-address ordering/count checks remain.
- Focused Solana normalization + worker + provider suites: **155 tests, 0 failures/errors**. This is syntax validation only; lookup-table state/authority remains unverified. Module 9 remains NO-GO.


### Bitcoin transaction output index uint32 bound — AUD-ONCHAIN-063 (27 November 2026)
- Bitcoin output normalization accepted any non-negative integer output `n`; TDD RED proved `4294967296` was accepted even though the serialized outpoint vout index is uint32.
- Normalization now restricts output indexes to non-boolean integers `0..0xFFFFFFFF`; duplicate-index protection remains.
- Focused Bitcoin output normalization + worker + provider suites: **152 tests, 0 failures/errors**. This validates field width only, not full transaction consensus. Module 9 remains NO-GO.


### Bitcoin zero-page/non-empty-record consistency — AUD-ONCHAIN-064 (27 November 2026)
- Bitcoin adapter and worker accepted a page with `totalPages=0` and non-empty records. Worker then calculated no next page and advanced its fixed-range checkpoint. TDD RED reproduced both adapter and substituted-worker paths.
- Adapter and worker now reject non-empty records when total page count is zero with `INVALID_PROVIDER_DATA`; empty zero-page results remain valid. Existing pagination and page-count-change restart behavior remains.
- Focused Bitcoin worker + provider suites: **140 tests, 0 failures/errors**. This does not establish provider address-index completeness. Module 9 remains NO-GO.


### SQLite/PostgreSQL verified mapping read-parity review — Section 252 (27 November 2026)
- Both adapters read stored identity projections and payloads, compare mapping_id/asset_id/network_id, require VERIFIED status and call the same central mapping validator. Recent EVM/Solana contract/address/token-standard/decimals rules therefore remain shared rather than diverging by adapter.
- Focused on-chain intelligence + synthetic PostgreSQL adapter + provider suites: **197 tests, 0 failures/errors, 21 skipped**. No additional independently reproducible defect confirmed. No PostgreSQL server was contacted; runtime/cross-connection behavior remains unverified. Module 9 remains NO-GO.


### XRPL raw ledger-index type validation — AUD-ONCHAIN-065 (27 November 2026)
- XRPL payment normalization compared `raw["ledger_index"]` with the typed record index without checking the raw field's type; Python `True == 1` let a boolean raw index match ledger 1. TDD RED reproduced acceptance and event emission.
- Normalization now requires the raw ledger index to be a non-boolean integer before exact equality comparison with the typed record index. Malformed raw identity fails closed.
- Focused XRPL normalization: **18 tests, 0 failures/errors**; XRPL worker + provider: **138 tests, 0 failures/errors**. This does not establish provider authenticity or settle XRPL marker-budget policy (AUD-ONCHAIN-030). Module 9 remains NO-GO.


### XRPL raw/typed transaction binding — AUD-ONCHAIN-066 (27 November 2026)
- The XRPL normalizer validated raw hash/ledger identity but did not verify that raw `tx_json`/`meta` matched the typed transaction/metadata dictionaries used for normalization. TDD RED showed divergent raw destination and transaction result could still produce an event.
- Normalization now requires both raw objects to be dictionaries exactly equal to their typed counterparts; mismatch fails closed. Test fixtures now mirror the real adapter's raw response shape.
- Focused XRPL normalization: **19 tests, 0 failures/errors**; XRPL worker + provider: **138 tests, 0 failures/errors**. This binds local representations, not provider authenticity. Module 9 remains NO-GO.


### EVM `eth_getLogs` removed-flag presence — AUD-ONCHAIN-067 (27 November 2026)
- Shared Ethereum/BNB log decoder previously used `log.get("removed", False)`, accepting an incomplete provider log as explicitly non-removed. TDD RED reproduced acceptance with an otherwise valid Transfer log missing `removed`.
- Decoder now requires `removed` to be present and boolean; missing/null/non-boolean values fail with `INVALID_TRANSFER_LOG`. Explicit `False` and `True` retain their semantics.
- Focused provider suite: **118 tests, 0 failures/errors**; EVM worker + ingestion: **86 tests, 0 failures/errors**. This does not close owner-defined tombstone lifecycle policy AUD-ONCHAIN-031. Module 9 remains NO-GO.


### Solana raw/typed block-time binding — AUD-ONCHAIN-068 (27 November 2026)
- Solana normalization checked typed `block_time` against canonical block time but did not bind a present raw full-transaction `blockTime` member to that typed value. TDD RED reproduced acceptance after mutating only raw `blockTime`.
- Normalization now validates a present raw value as a positive non-boolean integer and requires exact equality with typed `history.block_time`; absent raw field remains compatible, and explicit null must match typed null. Canonical timestamp validation remains separate.
- Focused Solana normalization + worker + provider suites: **158 tests, 0 failures/errors**. Timestamp accuracy/provider authenticity and quarantine policy AUD-ONCHAIN-035 remain unresolved. Module 9 remains NO-GO.


### Bitcoin raw/typed address-history identity binding — AUD-ONCHAIN-069 (27 November 2026)
- The normalizer validated typed `BitcoinAddressTransaction` fields against fetched detail data but did not bind retained raw address-history data to the typed projection. TDD RED reproduced raw txid divergence and a Python `True == 1` alias in raw block height.
- Normalizer now requires raw txid to be valid 32-byte hex and equal typed txid; present raw confirmations/height/time must be non-boolean integers exactly equal to typed values, and present raw block hash must match typed hash case-insensitively. Optional block fields remain optional for compatibility.
- Focused Bitcoin normalization + worker + provider suites: **157 tests, 0 failures/errors**. Provider authenticity and mapping authority/freshness AUD-ONCHAIN-002 remain unresolved. Module 9 remains NO-GO.


### XRPL ledger-header close-time UInt32 bound — AUD-ONCHAIN-070 (27 November 2026)
- `fetch_ledger_header()` rejected negative/boolean/non-integer close times but accepted values above the XRPL header field's UInt32 maximum. TDD RED reproduced acceptance at `2**32`.
- Adapter now enforces `0 <= close_time <= 0xFFFFFFFF` before converting Ripple Epoch seconds into a Unix timestamp. Existing valid header conversion remains unchanged.
- Focused valid-header + out-of-range regression tests: **2 tests, 0 failures/errors**. This checks protocol width, not timestamp truth/provider authenticity or cross-ledger monotonicity. Module 9 remains NO-GO.
- Protocol reference: https://xrpl.org/docs/references/protocol/ledger-data/ledger-header

- Section 258 full verification: **1,284 repository tests, 0 failures, 0 errors, 72 skipped**; compileall and `git diff --check` PASS. Synthetic PostgreSQL tests only; no PostgreSQL server was contacted. Module 9 remains NO-GO.


### XRPL validated-ledger close-time monotonicity — AUD-ONCHAIN-071 (27 November 2026)
- Worker verified parent-hash linkage but did not require each validated ledger's canonical timestamp to be later than its preceding ledger. TDD RED reproduced acceptance of equal timestamps for linked ledgers.
- Worker now rejects equal/decreasing timestamps with `XRPL_LEDGER_TIME_NOT_MONOTONIC`, checking both the preceding anchor and every adjacent header in the fixed range before account-page requests. XRPL worker fixtures now use strictly increasing timestamps.
- Focused XRPL worker suite: **22 tests, 0 failures/errors**. This enforces ordering for the fetched range only; wall-clock accuracy, provider authenticity and cross-run anchor continuity remain separate. Module 9 remains NO-GO.
- Protocol reference: https://xrpl.org/docs/concepts/ledgers/ledger-close-times


### XRPL ledger-index UInt32 bounds — AUD-ONCHAIN-072 (27 November 2026)
- Chainstack adapter accepted out-of-range ledger indexes for exact header requests and fixed account-history ranges; validated-head and returned range metadata also lacked explicit UInt32 bounds. TDD RED showed oversized requests reached transport.
- Adapter now enforces positive UInt32 header/head indexes, non-negative UInt32 account-history bounds, and UInt32 returned range metadata before accepting it.
- Focused new regressions + existing valid header/account-range tests: **4 tests, 0 failures/errors**. This is protocol-width validation only; provider authenticity and history completeness remain unresolved. Module 9 remains NO-GO.
- Protocol reference: https://xrpl.org/docs/references/protocol/ledger-data/ledger-header

- Section 260 verification: **1,287 repository tests, 0 failures, 0 errors, 72 skipped**; compileall and `git diff --check` PASS. Focused XRPL provider + worker + normalization suites: 162 passed. `TEST_POSTGRES_DSN` unset; no PostgreSQL server contacted. Module 9 remains NO-GO.


### Bitcoin resumed-range confirmation-safe tip revalidation — AUD-ONCHAIN-073 (27 November 2026)
- Worker bounded newly created ranges by `safe_height`, but resumed a persisted fixed range without checking whether its old `range_end` still fit the current tip's confirmation-safe height. TDD RED reproduced a page-2 transaction above the current safe height being ingested after the tip regressed.
- Worker now defers the saved range without fetching headers or another history page whenever `range_end > safe_height`; the original page/range checkpoint remains intact for safe retry after the tip catches up.
- Focused Bitcoin worker suite: **22 tests, 0 failures/errors**. This does not prove provider confirmation claims or provider authenticity. Module 9 remains NO-GO.

- Section 261 full verification: **1,288 repository tests, 0 failures, 0 errors, 72 skipped**; compileall and `git diff --check` PASS. Focused Bitcoin worker + provider + ingestion suites: 211 passed. No PostgreSQL server contacted; Module 9 remains NO-GO.


### Bitcoin block-header timestamp UInt32 bounds — AUD-ONCHAIN-074 (27 November 2026)
- Both Alchemy provider adapter and Bitcoin worker accepted positive header timestamps above the serialized `nTime` UInt32 maximum. TDD RED reproduced acceptance of `2**32` at both boundaries.
- Both boundaries now enforce `1 <= timestamp <= 0xFFFFFFFF`, rejecting booleans, non-integers and out-of-width values. Valid header and genesis compatibility remain covered.
- Focused regression + valid-header tests: **4 tests, 0 failures/errors**. Width validation does not implement Bitcoin PoW, MTP, future-time or difficulty consensus validation; Module 9 remains NO-GO.
- Protocol references: https://github.com/bitcoin/bitcoin/blob/master/src/chain.h and https://github.com/bitcoin/bitcoin/blob/master/src/validation.cpp

- Section 262 full verification: **1,290 repository tests, 0 failures, 0 errors, 72 skipped**; compileall and `git diff --check` PASS. Focused Bitcoin provider + worker + ingestion suites: 213 passed. No PostgreSQL server contacted; Module 9 remains NO-GO.


### Bitcoin history/detail timestamp binding to canonical header — AUD-ONCHAIN-075 (27 November 2026)
- History and full transaction detail timestamps were bound to each other, but neither was compared with the independently fetched canonical header timestamp. TDD RED reproduced acceptance when history/detail agreed with each other but differed by one second from the header.
- Worker now rejects `record.block_time != header["timestamp"]` with `BITCOIN_BLOCK_TIME_MISMATCH` before transaction-detail fetch, event persistence or checkpoint advancement. Reorg fixtures now use matching timestamps.
- Focused Bitcoin worker suite: **24 tests, 0 failures/errors**. This is cross-source consistency validation, not Bitcoin consensus validation/provider authenticity. Module 9 remains NO-GO.
- Alchemy references: https://www.alchemy.com/docs/chains/bitcoin/utxo-api-endpoints/utxo-api-endpoints/get-transaction and https://www.alchemy.com/docs/chains/bitcoin/bitcoin-api-endpoints/getblock

- Section 263 full verification: **1,291 repository tests, 0 failures, 0 errors, 72 skipped**; compileall and `git diff --check` PASS. Focused Bitcoin provider + worker + ingestion suites: 214 passed. No PostgreSQL server contacted; Module 9 remains NO-GO.


### Bitcoin provider header height bool/int alias — AUD-ONCHAIN-076 (27 November 2026)
- Provider adapter compared returned `height` directly with requested integer height; Python `True == 1` allowed JSON boolean `true` to pass as height 1. TDD RED reproduced acceptance.
- Adapter now requires returned height to be a non-boolean integer before exact equality comparison. Focused alias + valid header/genesis tests: **3 tests, 0 failures/errors**. Module 9 remains NO-GO.

- Section 264 full verification: **1,292 repository tests, 0 failures, 0 errors, 72 skipped**; compileall and `git diff --check` PASS. Focused Bitcoin provider + worker + ingestion suites: 215 passed. No PostgreSQL server contacted; Module 9 remains NO-GO.


### Solana signed-int64 persistence bounds for u64 slots — AUD-ONCHAIN-077 (27 November 2026)
- Provider adapter and worker accepted slot identifiers/ranges above the Solana RPC `u64` maximum despite rejecting booleans and negatives. TDD RED reproduced oversized finalized/head, transaction, produced-slot, block-slot, fixed-range and worker configuration values.
- Added `SOLANA_MAX_PERSISTABLE_SLOT = 0x7FFFFFFFFFFFFFFF` and enforce it independently across adapter requests/responses and worker configuration, finalized slot, slot-state, checkpoint, parent and transaction boundaries. This is the signed-int64 storage ceiling for SQLite `INTEGER`/PostgreSQL `BIGINT`, a deliberately narrower subset than protocol `u64`.
- New boundary regressions: **7 tests, 0 failures/errors**. This is representation/storage validation, not validator consensus/provider authenticity. Module 9 remains NO-GO.
- Protocol references: https://solana.com/docs/rpc/http/getslot and https://solana.com/docs/rpc/json-structures

- Section 265 full verification: **1,299 repository tests, 0 failures, 0 errors, 72 skipped**; compileall and `git diff --check` PASS. Focused Solana provider + worker + normalization + ingestion suites: 238 passed. No PostgreSQL server contacted; Module 9 remains NO-GO.


### Solana terminal signed-int64 slot checkpoint — AUD-ONCHAIN-078 (27 November 2026)
- A completed Solana range ending at the signed-int64 persistence maximum computed `next_slot=max+1`; SQLite rejected the checkpoint with `OverflowError`. TDD RED reproduced the failed commit.
- Worker now persists `next_slot=max` plus a validated `exhausted=true` marker at the terminal slot. Future runs continue pending quarantine recovery but do not restart address-history pagination for the exhausted scope. Ordinary ranges still increment normally.
- Focused Solana worker suite: **22 tests, 0 failures/errors**. Module 9 remains NO-GO.

- Section 266 full verification: **1,300 repository tests, 0 failures, 0 errors, 72 skipped**; compileall and `git diff --check` PASS. Focused Solana provider + worker + normalization + ingestion suites: 239 passed. Focused Solana worker suite: 22 passed. No PostgreSQL server contacted; Module 9 remains NO-GO.


### Solana quarantine replay checks canonical hash before timestamp deferral — AUD-ONCHAIN-079 (27 November 2026)
- TDD reproduced a reorged quarantined slot whose replacement block still had null `block_time`: the worker skipped hash comparison, reorg reconciliation rewound the cursor, and the same signature later caused a quarantine identity-collision `ValueError`.
- Replay now compares canonical block hash before deferring for unknown time. Changed hash fails closed with `SOLANA_QUARANTINE_BLOCK_HASH_MISMATCH`; unchanged hash/null time remains pending. No automatic deletion or retention-policy choice was introduced.
- Focused regression + replay + reorg tests: 3 passed. Solana worker + normalization + ingestion + PostgreSQL contract suites: 150 tests, 0 failures/errors, 21 skipped. Full repository suite: **1,301 tests, 0 failures, 0 errors, 72 skipped**; compileall and `git diff --check` PASS. Module 9 remains NO-GO.


### Solana quarantine rejects raw boolean slot aliases — AUD-ONCHAIN-080 (27 November 2026)
- Null-timestamp quarantine bypassed the ordinary normalizer's strict raw-slot check. Worker/store equality accepted raw `slot: true` for typed slot `1` because Python `True == 1`; later replay would fail the normalizer and leave the quarantine item pending.
- Worker now validates raw slot as a non-boolean integer matching typed slot before quarantine. SQLite and PostgreSQL commit validators independently reject boolean/non-integer raw slot aliases.
- Focused worker + SQLite store + synthetic PostgreSQL store regressions: 3 passed. Full repository verification pending. Module 9 remains NO-GO.

- Section 268 verification: focused worker + SQLite store + synthetic PostgreSQL store regressions **3 passed**; full repository suite **1,304 passed, 0 failures/errors, 72 skipped** (80.180 seconds); compileall and `git diff --check` PASS. No PostgreSQL runtime was available; Module 9 remains NO-GO.


### Solana quarantine binds raw blockTime to typed history — AUD-ONCHAIN-081 (27 November 2026)
- Null-canonical-time quarantine bypassed normalizer validation. TDD RED reproduced a raw `blockTime` one second different from typed address-history time being persisted, although later replay would reject it.
- Worker now validates present raw blockTime as a positive non-boolean integer exactly matching typed history before quarantine; SQLite and PostgreSQL stores independently enforce the same binding. Missing raw field remains compatible; explicit null must match typed null.
- Focused worker + SQLite store + synthetic PostgreSQL store regressions: 3 passed. Full repository verification pending. Module 9 remains NO-GO.

- Section 269 verification: focused worker + SQLite store + synthetic PostgreSQL store regressions **3 passed**; full repository suite **1,307 passed, 0 failures/errors, 72 skipped** (86.088 seconds); compileall and `git diff --check` PASS. No PostgreSQL runtime was available; Module 9 remains NO-GO.


### Solana quarantine runs full transaction preflight — AUD-ONCHAIN-082 (27 November 2026)
- Null-timestamp quarantine bypassed the normalizer's mandatory `meta.err` validation. TDD RED reproduced a record with missing execution status being persisted and later rejected on every replay.
- Worker now runs the full normalizer as validation-only preflight with a temporary timestamp anchor; temporary events/time are discarded. SQLite and PostgreSQL stores independently require transaction/meta dictionaries, explicit `err`, matching first signature, and message dictionary.
- Focused worker + SQLite store + synthetic PostgreSQL store tests: 5 passed. Full repository verification pending. Module 9 remains NO-GO.

- Section 270 verification: focused worker + SQLite store + synthetic PostgreSQL store tests **5 passed**; full repository suite **1,310 passed, 0 failures/errors, 72 skipped** (79.136 seconds); compileall and `git diff --check` PASS. No PostgreSQL runtime was available; Module 9 remains NO-GO.


### Solana transaction execution-error shape validation — AUD-ONCHAIN-083 (27 November 2026)
- Normalizer treated every non-null `meta.err` JSON value as a valid failed transaction. TDD RED reproduced boolean, integer, array, empty-string and empty-object values being silently skipped.
- It now accepts only a non-empty string enum variant or a single-key structured enum object; malformed shapes fail with `INVALID_SOLANA_TRANSACTION`. Valid string and structured error variants remain skippable.
- Focused malformed-shape + valid failed transaction + missing-status tests: 3 passed. Full repository verification pending. Module 9 remains NO-GO.

- Section 271 verification: focused malformed-error-shape + valid failed-transaction + missing-status tests **3 passed**; full repository suite **1,311 passed, 0 failures/errors, 72 skipped** (82.832 seconds); compileall and `git diff --check` PASS. No PostgreSQL runtime was available; Module 9 remains NO-GO.

- Section 271 verification: focused malformed-error-shape + valid failed-transaction + missing-status tests **3 passed**; full repository suite **1,311 passed, 0 failures/errors, 72 skipped** (82.832 seconds); compileall and `git diff --check` PASS. No PostgreSQL runtime was available; Module 9 remains NO-GO.


### Continuation checkpoint — 27 November 2026 (after Master Audit Section 272)
- Section 272 fixed AUD-ONCHAIN-084. Ethereum and BNB provider header adapters accepted timestamps above the application's UTC `datetime`/ISO-8601 representable range. TDD RED reproduced both adapters accepting `253402300800` and the EVM worker raising `ValueError: year 10000 is out of range` during conversion. GREEN defines `MAX_DATETIME_UNIX_TIMESTAMP = 253402300799` and independently rejects out-of-range timestamps in both adapters and the worker before conversion/persistence.
- Focused EVM worker + provider suites: **151 tests, 0 failures/errors**. Full repository suite: **1,314 tests, 0 failures, 0 errors, 72 skipped** (82.021 seconds); compileall and `git diff --check` PASS.
- Preserve `/tmp/binance-w2e-continuation`, branch `work/module9-continuation-local`, HEAD `34bbe5b959ea6196b750529e67129af8c68b7590`, all existing modifications and untracked `layer1/migrations/postgresql/0005_solana_timestamp_quarantine.sql`; do not touch `/root/Binance-bot`. `TEST_POSTGRES_DSN` remains unset. No PostgreSQL runtime, production DB, live provider, migration application, Binance publication, staging, commit, push, merge or deployment. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.


### Continuation checkpoint — 27 November 2026 (after Master Audit Section 273)
- Section 273 fixed AUD-ONCHAIN-085. EVM worker checked parent-hash linkage but not timestamp order. TDD RED reproduced a parent-linked BNB header sequence with decreasing seconds being committed and an Ethereum sequence with equal timestamps being accepted. GREEN now requires strictly increasing Ethereum timestamps and non-decreasing BNB second-resolution timestamps; equal BNB seconds remain allowed because the adapter does not expose BNB's millisecond remainder. Violations fail with `EVM_BLOCK_TIMESTAMP_NOT_MONOTONIC` before page commit/checkpoint advancement.
- Focused EVM worker + provider suites: **154 tests, 0 failures/errors**. Full repository suite: **1,317 tests, 0 failures, 0 errors, 72 skipped** (83.582 seconds); compileall and `git diff --check` PASS. Official protocol references: Ethereum Yellow Paper header validation and BNB BEP-706 millisecond timestamp design.
- Preserve `/tmp/binance-w2e-continuation`, branch `work/module9-continuation-local`, HEAD `34bbe5b959ea6196b750529e67129af8c68b7590`, all existing modifications and untracked `layer1/migrations/postgresql/0005_solana_timestamp_quarantine.sql`; do not touch `/root/Binance-bot`. `TEST_POSTGRES_DSN` remains unset. No PostgreSQL runtime, production DB, live provider, migration application, Binance publication, staging, commit, push, merge or deployment. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.


### Continuation checkpoint — 27 November 2026 (after Master Audit Section 274)
- Section 274 fixed AUD-ONCHAIN-086. Solana provider accepted positive blockTime values above the application's UTC datetime/ISO-8601 representable range; worker could raise `ValueError: year 10000 is out of range` converting a canonical slot timestamp or a transaction time used as a null-time quarantine validation anchor. TDD RED reproduced both worker paths and both adapter acceptance paths. GREEN enforces `MAX_DATETIME_UNIX_TIMESTAMP = 253402300799` in Solana header/address-history adapters and independently in worker header, typed blockTime and raw blockTime validation. Protocol-valid null canonical block time remains supported.
- Focused Solana worker + provider suites: **159 tests, 0 failures/errors**. Full repository suite: **1,321 tests, 0 failures, 0 errors, 72 skipped** (84.206 seconds); compileall and `git diff --check` PASS.
- Preserve `/tmp/binance-w2e-continuation`, branch `work/module9-continuation-local`, HEAD `34bbe5b959ea6196b750529e67129af8c68b7590`, all existing modifications and untracked `layer1/migrations/postgresql/0005_solana_timestamp_quarantine.sql`; do not touch `/root/Binance-bot`. `TEST_POSTGRES_DSN` remains unset. No PostgreSQL runtime, production DB, live provider, migration application, Binance publication, staging, commit, push, merge or deployment. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.


### Continuation checkpoint — 27 November 2026 (after Master Audit Section 275)
- Section 275 fixed AUD-ONCHAIN-087. The Alchemy provider's `probe()` method duplicated canonical header parsing and bypassed existing timestamp bounds: Bitcoin accepted `time=2**32`; Ethereum/BNB probes raised `ValueError` on `253402300800`. GREEN defines/reuses the Bitcoin UInt32 maximum and enforces the shared UTC datetime upper bound in EVM probes before conversion. All three fail with `INVALID_PROVIDER_DATA`.
- Focused provider suite: **134 tests, 0 failures/errors**. Full repository suite: **1,323 tests, 0 failures, 0 errors, 72 skipped** (89.275 seconds); compileall and `git diff --check` PASS.
- Preserve `/tmp/binance-w2e-continuation`, branch `work/module9-continuation-local`, HEAD `34bbe5b959ea6196b750529e67129af8c68b7590`, all existing modifications and untracked `layer1/migrations/postgresql/0005_solana_timestamp_quarantine.sql`; do not touch `/root/Binance-bot`. `TEST_POSTGRES_DSN` remains unset. No PostgreSQL runtime, production DB, live provider, migration application, Binance publication, staging, commit, push, merge or deployment. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.


### Continuation checkpoint — 27 November 2026 (after Master Audit Section 276)
- Section 276 fixed AUD-ONCHAIN-088. Solana worker previously verified that a reported parent slot existed and its hash matched, but did not require it to be the immediately preceding produced slot in the ordered `getBlocks` range. TDD RED reproduced acceptance of slot 302 claiming parent 300 while slot 301 was also produced. GREEN now tracks the prior produced slot and rejects older-parent references with `SOLANA_PARENT_SLOT_MISMATCH`; missing parents retain `SOLANA_PARENT_SLOT_MISSING`. Reorg fixture updated to model changed produced-slot parent linkage coherently.
- Regression group: **3 tests, 0 failures/errors**. Full repository suite: **1,324 tests, 0 failures, 0 errors, 72 skipped** (84.021 seconds); compileall and `git diff --check` PASS. Protocol references: Solana RPC JSON Structures (`parentSlot`) and `getBlocks` confirmed-slot range.
- Preserve `/tmp/binance-w2e-continuation`, branch `work/module9-continuation-local`, HEAD `34bbe5b959ea6196b750529e67129af8c68b7590`, all existing modifications and untracked `layer1/migrations/postgresql/0005_solana_timestamp_quarantine.sql`; do not touch `/root/Binance-bot`. `TEST_POSTGRES_DSN` remains unset. No PostgreSQL runtime, production DB, live provider, migration application, Binance publication, staging, commit, push, merge or deployment. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.


### Continuation checkpoint — 27 November 2026 (after Master Audit Section 277)
- Section 277 fixed AUD-ONCHAIN-089. Bitcoin worker compared address-history `blockHash` with transaction-detail `blockHash` through normalization but did not compare either with the independently fetched canonical block header. TDD RED reproduced acceptance of mutually agreeing but wrong transaction hashes against a different canonical header hash. GREEN compares the typed history block hash to the canonical header hash before transaction-detail fetch/normalization and rejects divergence with `BITCOIN_BLOCK_HASH_MISMATCH`.
- Focused Bitcoin worker regressions: **4 tests, 0 failures/errors**. Full repository suite: **1,325 tests, 0 failures, 0 errors, 72 skipped** (82.909 seconds); compileall and `git diff --check` PASS.
- Preserve `/tmp/binance-w2e-continuation`, branch `work/module9-continuation-local`, HEAD `34bbe5b959ea6196b750529e67129af8c68b7590`, all existing modifications and untracked `layer1/migrations/postgresql/0005_solana_timestamp_quarantine.sql`; do not touch `/root/Binance-bot`. `TEST_POSTGRES_DSN` remains unset. No PostgreSQL runtime, production DB, live provider, migration application, Binance publication, staging, commit, push, merge or deployment. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.


### Continuation checkpoint — 27 November 2026 (after Master Audit Section 278)
- Section 278 fixed AUD-ONCHAIN-090. Bitcoin worker anchored resumed ranges to `range_start - 1` but skipped that parent-header check on the first configured scan range. TDD RED reproduced acceptance/commit of an initial range whose first header's `previous_block_hash` differed from the independently fetched preceding header hash. GREEN now fetches and validates the preceding header for every range with `range_start > 0`; genesis remains the only unanchored first range.
- Focused Bitcoin worker tests: **4 tests, 0 failures/errors**. Full repository suite: **1,326 tests, 0 failures, 0 errors, 72 skipped** (82.849 seconds); compileall and `git diff --check` PASS.
- Preserve `/tmp/binance-w2e-continuation`, branch `work/module9-continuation-local`, HEAD `34bbe5b959ea6196b750529e67129af8c68b7590`, all existing modifications and untracked `layer1/migrations/postgresql/0005_solana_timestamp_quarantine.sql`; do not touch `/root/Binance-bot`. `TEST_POSTGRES_DSN` remains unset. No PostgreSQL runtime, production DB, live provider, migration application, Binance publication, staging, commit, push, merge or deployment. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.


## 279. AUD-ONCHAIN-091 — XRPL account_tx close time is not bound to canonical ledger header (27 November 2026)

**Finding: AUD-ONCHAIN-091 — MEDIUM / CONFIRMED / REMEDIATED LOCALLY / TDD REGRESSION.** The Chainstack `account_tx` adapter retained each transaction's `close_time_iso`, but the XRPL worker ignored it and unconditionally substituted the timestamp from a separately fetched canonical ledger header. A response could therefore contain a matching validated ledger index/hash but a contradictory transaction-wrapper close time, and the worker would still ingest the event. XRPL documents `close_time_iso` as the close time of the ledger containing the transaction; the `ledger` response independently exposes the ledger header's `close_time` and `close_time_iso`. This is an evidence-consistency defect, not a request to trust the transaction-wrapper timestamp over the canonical header.

### TDD reproduction and remediation
- Added `test_transaction_close_time_must_match_independently_verified_ledger_header`. The account transaction claims the same validated ledger index/hash but its `close_time_iso` is one second different from the independently fetched canonical header. RED: the worker ignored the disagreement, ingested the event and advanced the checkpoint instead of rejecting the provider evidence.
- GREEN: before normalization/persistence, the worker now requires a non-empty timezone-aware ISO-8601 `record.close_time_iso`, requires the typed value to match the raw provider evidence, and compares its UTC instant exactly with the independently fetched canonical ledger-header timestamp. Malformed/missing/naive or raw/typed-conflicting evidence fails with `INVALID_PROVIDER_DATA`; a valid but different instant fails with `XRPL_LEDGER_TIME_MISMATCH`. The event timestamp continues to come from the canonical ledger header.
- Updated the XRPL worker test fixture so its account_tx close time matches the fake canonical ledger header. Preserved the existing unvalidated-record test's raw evidence shape.
- RED reproduced the defect: the new regression failed because `ProviderTransportError` was not raised. GREEN focused XRPL worker + provider suites: **157 tests, 0 failures/errors**. Full repository suite: **1,327 tests, 0 failures, 0 errors, 72 skipped** (27 November 2026; 86.045 seconds). `python -m compileall -q layer1 tests` and `git diff --check` PASS.

### Scope and limitations
- This binds the redundant account_tx transaction-wrapper close-time evidence to the independently fetched validated ledger header. It does not authenticate Chainstack, establish independent multi-provider corroboration, prove transaction inclusion with a Merkle proof, or constitute live-provider acceptance. The XRPL close-time protocol specifies strictly increasing validated-ledger close times; the worker's existing parent timestamp monotonicity check remains in place. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.
- Protocol references: XRPL `account_tx` response defines transaction `close_time_iso` as the time the containing ledger closed: https://xrpl.org/docs/references/http-websocket-apis/public-api-methods/account-methods/account_tx. XRPL `ledger` response defines header `close_time` / `close_time_iso`: https://xrpl.org/docs/references/http-websocket-apis/public-api-methods/ledger-methods/ledger. XRPL Ledger Close Times states validated-ledger close times are strictly increasing: https://xrpl.org/docs/concepts/ledgers/ledger-close-times.

### Section 279 verification checkpoint
- Focused XRPL worker + provider suites: **157 tests, 0 failures/errors**. Full repository suite: **1,327 tests, 0 failures, 0 errors, 72 skipped**. Compileall and `git diff --check` PASS.
- `TEST_POSTGRES_DSN` remains unset; no PostgreSQL runtime/server, production database, live provider, migration application, Binance publication, staging, commit, push, merge or deployment occurred. Existing uncommitted changes and untracked `layer1/migrations/postgresql/0005_solana_timestamp_quarantine.sql` remain preserved. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.


## 280. AUD-ONCHAIN-092 — XRPL worker accepts timestamps beyond UInt32 close_time range (27 November 2026)

**Finding: AUD-ONCHAIN-092 — LOW / CONFIRMED / REMEDIATED LOCALLY / TDD REGRESSION.** The Chainstack XRPL adapter correctly restricts the ledger header's Ripple-epoch `close_time` to UInt32 and converts it to Unix time by adding the Ripple epoch offset (946684800). The worker's independent provider boundary only required a non-negative integer timestamp, however. A different provider implementation or malformed adapter response could therefore pass a timestamp outside the protocol's representable close-time range; the worker would later fail during datetime conversion rather than rejecting provider data at the header boundary.

### TDD reproduction and remediation
- Added `test_rejects_xrpl_header_timestamp_outside_protocol_uint32_close_time_range` with a header timestamp of `253402300800`. RED: the worker accepted the malformed header through canonical-header preflight and reached later processing instead of failing closed.
- GREEN: worker header validation now independently requires `0 <= timestamp <= 946684800 + 0xFFFFFFFF`, matching the XRPL UInt32 Ripple-epoch close_time domain before parent-time comparisons, account_tx pagination, datetime conversion or persistence.
- Focused XRPL worker + provider suites: **158 tests, 0 failures/errors**. Full repository suite: **1,328 tests, 0 failures, 0 errors, 72 skipped**. `python -m compileall -q layer1 tests` and `git diff --check` PASS.

### Scope and limitations
- The bound reflects the protocol field's UInt32 range plus the Ripple epoch offset, not an estimate of current ledger time. The adapter's own UInt32 validation remains in place; this adds an independent worker-boundary guard. It does not establish provider authenticity or live-provider acceptance. Protocol reference: XRPL Ledger Header documents `close_time` as UInt32 seconds since the Ripple epoch: https://xrpl.org/docs/references/protocol/ledger-data/ledger-header. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.

### Section 280 verification checkpoint
- Focused XRPL worker + provider suites: **158 tests, 0 failures/errors**. Full repository suite: **1,328 tests, 0 failures, 0 errors, 72 skipped**. Compileall and `git diff --check` PASS.
- `TEST_POSTGRES_DSN` remains unset; no PostgreSQL runtime/server, production database, live provider, migration application, Binance publication, staging, commit, push, merge or deployment occurred. Existing uncommitted changes and untracked `layer1/migrations/postgresql/0005_solana_timestamp_quarantine.sql` remain preserved. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.


## 281. AUD-ONCHAIN-093 — XRPL configured start ledger exceeds protocol UInt32 range (27 November 2026)

**Finding: AUD-ONCHAIN-093 — LOW / CONFIRMED / REMEDIATED LOCALLY / TDD REGRESSION.** The XRPL worker constructor validated configured start-ledger values as positive integers but did not enforce the protocol's UInt32 ledger-index domain. A configuration value above `0xFFFFFFFF` was therefore accepted even though no valid XRPL ledger can have that index. During execution, the worker could treat the configured start as beyond the validated head and skip scanning without a configuration error, leaving an impossible cursor seed silently accepted.

### TDD reproduction and remediation
- Added `test_rejects_start_ledger_above_protocol_uint32_range`. RED: constructing the worker with `start_ledgers={mapping_id: 0x100000000}` did not raise the expected `ValueError`.
- GREEN: constructor validation now requires each configured start ledger to satisfy `1 <= ledger <= 0xFFFFFFFF`, rejecting booleans, non-integers and out-of-range values with the existing explicit start-ledger validation error.
- Focused XRPL worker + provider suites: **159 tests, 0 failures/errors**. Full repository suite: **1,329 tests, 0 failures, 0 errors, 72 skipped** (84.516 seconds). `python -m compileall -q layer1 tests` and `git diff --check` PASS.

### Scope and limitations
- This validates the configured seed at worker construction. It does not define a source-history start policy, prove mapping authority or provider authenticity, or close the separate cumulative marker-budget policy (AUD-ONCHAIN-030). Protocol reference: XRPL Ledger Header defines ledger index as UInt32: https://xrpl.org/docs/references/protocol/ledger-data/ledger-header. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.

### Section 281 verification checkpoint
- Focused XRPL worker + provider suites: **159 tests, 0 failures/errors**. Full repository suite: **1,329 tests, 0 failures, 0 errors, 72 skipped**. Compileall and `git diff --check` PASS.
- `TEST_POSTGRES_DSN` remains unset; no PostgreSQL runtime/server, production database, live provider, migration application, Binance publication, staging, commit, push, merge or deployment occurred. Existing uncommitted changes and untracked `layer1/migrations/postgresql/0005_solana_timestamp_quarantine.sql` remain preserved. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.


## 282. AUD-ONCHAIN-094 — XRPL worker does not independently bound validated head height (27 November 2026)

**Finding: AUD-ONCHAIN-094 — LOW / CONFIRMED / REMEDIATED LOCALLY / TDD REGRESSION.** The Chainstack adapter validates `server_info.validated_ledger.seq` as UInt32, but the worker's provider trust boundary only checked that `head_height` was an integer and not a boolean. A custom provider implementation or malformed adapter result could therefore advertise an impossible validated-ledger head above `0xFFFFFFFF`. The worker would accept the impossible head and continue scanning a lower configured range rather than rejecting malformed provider metadata.

### TDD reproduction and remediation
- Added `test_rejects_validated_head_above_uint32_before_scanning`. The fake provider advertises head `0x100000000` while returning otherwise valid canonical headers/timestamps for the configured scan range. RED: the worker did not raise, accepted the impossible head and proceeded to account scanning.
- GREEN: after validating provider/network/status/finality/type, the worker now independently requires `1 <= head.head_height <= 0xFFFFFFFF`; out-of-range values fail with `INVALID_PROVIDER_DATA` before mapping/account scanning or ledger-header requests.
- Focused XRPL worker + provider suites: **160 tests, 0 failures/errors**. Full repository suite: **1,330 tests, 0 failures, 0 errors, 72 skipped** (87.563 seconds). `python -m compileall -q layer1 tests` and `git diff --check` PASS.

### Scope and limitations
- This duplicates the adapter's protocol bound at the worker trust boundary. It does not establish provider authenticity, independent corroboration, history completeness or live-provider acceptance. Protocol reference: XRPL Ledger Header defines ledger index as UInt32: https://xrpl.org/docs/references/protocol/ledger-data/ledger-header. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.

### Section 282 verification checkpoint
- Focused XRPL worker + provider suites: **160 tests, 0 failures/errors**. Full repository suite: **1,330 tests, 0 failures, 0 errors, 72 skipped**. Compileall and `git diff --check` PASS.
- `TEST_POSTGRES_DSN` remains unset; no PostgreSQL runtime/server, production database, live provider, migration application, Binance publication, staging, commit, push, merge or deployment occurred. Existing uncommitted changes and untracked `layer1/migrations/postgresql/0005_solana_timestamp_quarantine.sql` remain preserved. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.


## 283. AUD-ONCHAIN-095 — XRPL persisted next-ledger cursor exceeds protocol exhaustion sentinel (27 November 2026)

**Finding: AUD-ONCHAIN-095 — LOW / CONFIRMED / REMEDIATED LOCALLY / TDD REGRESSION.** XRPL checkpoint validation required `next_ledger` to be an integer no smaller than the configured start ledger, but did not constrain its upper bound. The legitimate exhausted-history sentinel after the final UInt32 ledger is exactly `0x100000000`; a corrupted or tampered checkpoint larger than that could be accepted, cause reorg-lookback work against impossible ledger indexes, and then silently skip scanning because the cursor lies beyond the validated head.

### TDD reproduction and remediation
- Added `test_rejects_persisted_next_ledger_above_uint32_exhaustion_sentinel`. The test seeds a checkpoint with `next_ledger=0x100000001` in the isolated SQLite fixture. RED: the worker accepted the malformed checkpoint instead of raising the stored-checkpoint validation error.
- GREEN: checkpoint validation now requires `initial <= next_ledger <= 0x100000000`. The upper bound intentionally permits `0x100000000` as the one-past-maximum exhaustion sentinel produced after scanning the final valid UInt32 ledger, while rejecting any larger cursor before reorg reconciliation or provider ledger requests.
- Focused XRPL worker + provider suites: **161 tests, 0 failures/errors**. Full repository suite: **1,331 tests, 0 failures, 0 errors, 72 skipped** (80.463 seconds). `python -m compileall -q layer1 tests` and `git diff --check` PASS.

### Scope and limitations
- This protects the persisted next-ledger cursor, not all marker/checkpoint resource budgets. AUD-ONCHAIN-030 remains open pending owner-approved marker count/byte limits and recovery policy. The one-past-max sentinel is a cursor position, not a valid ledger index. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.

### Section 283 verification checkpoint
- Focused XRPL worker + provider suites: **161 tests, 0 failures/errors**. Full repository suite: **1,331 tests, 0 failures, 0 errors, 72 skipped**. Compileall and `git diff --check` PASS.
- `TEST_POSTGRES_DSN` remains unset; no PostgreSQL runtime/server, production database, live provider, migration application, Binance publication, staging, commit, push, merge or deployment occurred. Existing uncommitted changes and untracked `layer1/migrations/postgresql/0005_solana_timestamp_quarantine.sql` remain preserved. Module 9 remains NOT ACTIVATED / NOT PRODUCTION-READY / NO-GO.
