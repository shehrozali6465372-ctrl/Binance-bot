# Module 9 — Blockchain & On-chain Intelligence

## Provider decision

Status: **User-selected for initial implementation; live integration and production approval pending.**

| Network | Provider | Access plan | Verified scope | Current limitation |
|---|---|---|---|---|
| Bitcoin mainnet | Alchemy | Free | Bitcoin JSON-RPC and indexed UTXO REST APIs | Account/API-key access and workload-specific quotas not live-verified |
| Ethereum mainnet | Alchemy | Free | Ethereum JSON-RPC | Address/token history coverage must be mapped to supported methods and quota |
| Solana mainnet | Alchemy | Free | Solana JSON-RPC | Confirmed/finalized commitment and token-account data need method-level verification |
| BNB Smart Chain mainnet | Alchemy | Free | BSC JSON-RPC; chain ID 56 | Historical log ranges and free-tier limits must be tested |
| XRP Ledger mainnet | Chainstack | Developer Free | XRPL JSON-RPC and WebSocket via Global Node | Shared Global Nodes retain recent ledgers, not full history; no full-history guarantee |

Official provider facts checked on 2026-11-11:

- Alchemy Free plan publishes 30M compute units/month and 25 requests/second. Its plan page says all mainnets and testnets are included, but exact method-level support still varies by chain and product.
- Alchemy documents Bitcoin JSON-RPC plus indexed UTXO REST methods; Ethereum, Solana and BNB Smart Chain endpoints are documented. BNB Smart Chain mainnet is chain ID 56.
- Chainstack's XRP Ledger Developer plan is listed at $0/month, 3M request units/month and 25 requests/second, with one node and WebSockets; a free account is offered without a credit card.
- Chainstack's Oct 1, 2026 Extended Nodes article labels XRPL Global Nodes as Extended: provider-reported retention is roughly 750,000–1,500,000 ledgers (about 33–66 days), not a complete archive. An earlier Sep 16, 2026 Chainstack setup guide still says under six days; these provider pages conflict. The adapter therefore records `complete_ledgers` from `server_info` at runtime instead of hard-coding either duration. Full-history retention requires separately configured infrastructure.

Sources:

- https://www.alchemy.com/pricing
- https://www.alchemy.com/docs/reference/bitcoin-api-quickstart
- https://www.alchemy.com/docs/reference/node-supported-chains
- https://www.alchemy.com/docs/reference/bnb-smart-chain-api-quickstart
- https://www.alchemy.com/docs/chains/bitcoin/bitcoin-api-endpoints/getblockcount
- https://www.alchemy.com/docs/chains/bitcoin/bitcoin-api-endpoints/getblockheader
- https://www.alchemy.com/docs/chains/solana/solana-api-endpoints/get-slot
- https://www.alchemy.com/docs/bnb-smart-chain/bnb-smart-chain-api-overview
- https://chainstack.com/learn/how-to/how-to-get-xrp-ledger-rpc-endpoint-2026-guide/
- https://chainstack.com/build-better-with-xrp-ledger/
- https://chainstack.com/chainstack-extended-nodes-explained/
- https://chainstack.com/learn/how-to/how-to-get-xrp-ledger-rpc-endpoint-2026-guide/
- https://xrpl.org/docs/tutorials/public-servers
- https://xrpl.org/docs/references/http-websocket-apis/public-api-methods/server-info-methods/server_info

## Initial implementation in this branch

`layer1/onchain.py` currently provides:

- A strict five-network allowlist and provider-to-network allowlist.
- Canonical network family and chain-ID checks (Bitcoin/UTXO, Ethereum/EVM, Solana, BNB/EVM, XRPL).
- A mapping model that requires canonical CoinGecko asset ID, exact Binance symbol, native/token representation, decimals and HTTPS mapping provenance.
- The eligibility gate also requires the upstream Binance Spot source, verified CoinGecko ticker proof, proof timestamps/hash and a non-empty exact eligible-pair set; a manually forged `ELIGIBLE` status alone is insufficient.
- Network-specific block/transaction hash formats are checked before accepting observations.
- Native assets cannot declare a token contract or issuer. Non-native EVM/Solana assets require an explicit contract/mint and token standard; non-native XRPL assets require the exact issuer address and issued-currency code (XRPL is not an EVM contract network).
- An `ELIGIBLE` Binance Spot decision is mandatory before evidence can be accepted.
- Read-only provider probes in `layer1/onchain_providers.py`: Alchemy probes BTC block tip, ETH finalized block, Solana finalized slot and BNB finalized header using `verifiedValidatorNum=-3` (all validators); Chainstack probes XRPL validated-ledger metadata and captures the actual `complete_ledgers` retention range.
- Provider transport validates JSON-RPC envelopes, normalizes HTTP 429/network errors without exposing endpoint credentials, and rejects unsupported write methods.
- Bitcoin is modeled as probabilistic confirmations, not deterministic finality; a minimum confirmation threshold must be explicitly configured. Ethereum/BNB finalized block references, Solana `commitment=finalized`, and XRPL validated-ledger evidence are kept distinct.
- Exact asset, mapping, network, chain ID and provider matching; ticker-only and wrong-chain matches are rejected.
- Explicit finality states. Pending or unverified evidence is not accepted.
- Freshness thresholds are mandatory configuration. No uncalibrated default is silently assumed; a missing policy returns `FRESHNESS_POLICY_NOT_CONFIGURED`.
- Additive SQLite persistence. Only evidence revalidated as accepted can be stored; identical observation IDs are idempotent and conflicting content is rejected.

## Not yet implemented / not yet verified

- No live Alchemy or Chainstack request has been made. The current local process has no `ALCHEMY_API_KEY` or `CHAINSTACK_XRPL_ENDPOINT` environment variable. No provider API key or endpoint has been configured in the repository or deployment.
- Current focused tests: 25 domain tests and 10 provider-adapter tests. Full repository suite: 168 passed, 0 failed.
- Alchemy connector authentication is currently invalid/expired (app listing returned HTTP 401); no app ID or API key could be retrieved through the connector.
- No production API account, paid plan, secret, or infrastructure has been created or modified.
- Network-specific transaction/event acquisition, pagination, reorg reconciliation, token migration registries, and whale-transfer aggregation are still pending.
- No token contract mappings have been populated. Native asset support in the model is not proof that any Binance Spot asset mapping is verified.
- Freshness thresholds and finality policy must be calibrated per network and provider. Bitcoin probabilistic confirmations must not be mislabeled deterministic finality; Solana commitment and XRPL validated-ledger semantics must remain distinct.
- Provider integration tests must call documented read-only endpoints using configured credentials. Unit fixtures are not proof of live connectivity.

## Safety boundaries

- Only Binance Spot-eligible assets can enter on-chain candidate analysis.
- No ticker-only mapping, guessed contract, fake provider response, or fabricated metric.
- Unmapped, stale, unsupported or non-final data remains unavailable/unverified.
- Whale thresholds must be explicit system thresholds and do not prove buy/sell intent.
- No exchange inflow/outflow attribution without verified wallet labels.
- On-chain evidence is corroborative only and cannot authorize publication.
- Never publish a real Binance Square post during tests or diagnostics.
