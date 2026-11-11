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
