import json
import unittest
from urllib.error import HTTPError

from layer1.onchain_providers import (
    AlchemyReadOnlyAdapter,
    BitcoinAddressTransaction,
    EthereumAssetTransfer,
    ChainstackXrplReadOnlyAdapter,
    ProviderDataPage,
    SolanaAddressTransaction,
    XrplAccountTransaction,
    ProviderTransportError,
    ReadOnlyJsonRpcTransport,
    SOLANA_MAINNET_GENESIS_HASH,
    is_valid_xrpl_classic_address,
    retry_provider_operation,
)


class FakeTransport:
    def __init__(self, responses, calls):
        self.responses = responses
        self.calls = calls

    def call(self, method, params=None):
        self.calls.append((method, params))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeHttpResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class OnChainProviderTests(unittest.TestCase):
    def adapter(self, responses):
        calls = []
        def factory(endpoint, timeout):
            self.assertTrue(endpoint.startswith("https://"))
            self.assertEqual(timeout, 10)
            return FakeTransport(responses, calls)
        return AlchemyReadOnlyAdapter("test-key", transport_factory=factory), calls

    def test_provider_retry_policy_honors_retry_after_and_caps_exponential_backoff(self):
        delays = []
        attempts = []
        def operation():
            attempts.append(len(attempts) + 1)
            if len(attempts) == 1:
                raise ProviderTransportError("RATE_LIMITED", "slow down", 429, retry_after_seconds=7)
            return "ok"
        result = retry_provider_operation(
            operation, attempts=3, sleep=delays.append,
            base_delay_seconds=0.25, max_delay_seconds=2.0,
        )
        self.assertEqual(result, "ok")
        self.assertEqual(len(attempts), 2)
        self.assertEqual(delays, [7.0])

    def test_provider_retry_policy_does_not_retry_permanent_errors(self):
        delays = []
        def operation():
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "bad payload")
        with self.assertRaises(ProviderTransportError):
            retry_provider_operation(operation, attempts=4, sleep=delays.append)
        self.assertEqual(delays, [])

    def test_xrpl_classic_address_validation_checks_version_and_checksum(self):
        self.assertTrue(is_valid_xrpl_classic_address("rLNaPoKeeBjZe2qs6x52yVPZpZ8td4dc6w"))
        self.assertTrue(is_valid_xrpl_classic_address("rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"))
        self.assertTrue(is_valid_xrpl_classic_address("rf1BiGeXwwQoi8Z2ueFYTEXSwuJYfV2Jpn"))
        self.assertFalse(is_valid_xrpl_classic_address("rBqiK7z9a7M8w2F7yQzvVJ5QJ8qQh2vKQ"))
        self.assertFalse(is_valid_xrpl_classic_address("X7F9A2D3E4B5C6D7E8F9A2D3E4B5C6D7E8F9A2D3"))
        self.assertFalse(is_valid_xrpl_classic_address("r" + "1" * 24))

    def test_alchemy_bitcoin_probe_uses_read_only_header_and_preserves_confirmation_count(self):
        adapter, calls = self.adapter([
            900000,
            "a" * 64,
            {"height": 900000, "hash": "a" * 64, "time": 1794398340, "confirmations": 1},
        ])
        result = adapter.probe("bitcoin-mainnet")
        self.assertEqual(result.status, "AVAILABLE")
        self.assertEqual(result.head_height, 900000)
        self.assertEqual(result.finality, "CONFIRMED")
        self.assertEqual(result.finality_reference, "confirmations=1")
        self.assertEqual([call[0] for call in calls], ["getblockcount", "getblockhash", "getblockheader"])

    def test_bitcoin_worker_tip_and_canonical_header_are_independently_resolved(self):
        block_hash = "a" * 64
        adapter, calls = self.adapter([900000, block_hash, {
            "height": 900000, "hash": block_hash, "time": 1794398340,
        }])
        self.assertEqual(adapter.fetch_bitcoin_tip_height(), 900000)
        header = adapter.fetch_bitcoin_block_header(900000)
        self.assertEqual(header, {
            "number": 900000, "hash": block_hash, "timestamp": 1794398340,
        })
        self.assertEqual([call[0] for call in calls], [
            "getblockcount", "getblockhash", "getblockheader",
        ])

    def test_bitcoin_worker_rejects_canonical_header_hash_mismatch(self):
        adapter, _ = self.adapter([
            "a" * 64, {"height": 900000, "hash": "b" * 64, "time": 1794398340},
        ])
        with self.assertRaises(ProviderTransportError):
            adapter.fetch_bitcoin_block_header(900000)

    def test_alchemy_ethereum_probe_verifies_chain_id_and_finalized_block(self):
        adapter, calls = self.adapter([
            "0x1",
            {"number": "0x100", "hash": "0x" + "a" * 64, "timestamp": "0x6553f100"},
        ])
        result = adapter.probe("ethereum-mainnet")
        self.assertEqual(result.finality, "FINALIZED")
        self.assertEqual(result.finality_reference, "eth_getBlockByNumber:finalized")
        self.assertEqual([call[0] for call in calls], ["eth_chainId", "eth_getBlockByNumber"])
        self.assertEqual(calls[1][1], ["finalized", False])

    def test_ethereum_eth_getlogs_decodes_exact_transfer_log_and_checks_finality(self):
        contract = "0x" + "3" * 40
        sender = "0x" + "1" * 40
        recipient = "0x" + "2" * 40
        transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        log = {
            "address": contract, "blockNumber": "0x100", "blockHash": "0x" + "a" * 64,
            "transactionHash": "0x" + "b" * 64, "logIndex": "0x7", "removed": False,
            "topics": [transfer_topic, "0x" + "0" * 24 + sender[2:], "0x" + "0" * 24 + recipient[2:]],
            "data": "0x" + format(123456, "064x"),
        }
        adapter, calls = self.adapter([
            "0x1", {"number": "0x200", "hash": "0x" + "c" * 64},
            {"number": "0x100", "hash": "0x" + "c" * 64, "timestamp": "0x6553f100"},
            "0x1", {"number": "0x200", "hash": "0x" + "c" * 64},
            [log],
        ])
        self.assertEqual(adapter.fetch_ethereum_finalized_height(), 512)
        header = adapter.fetch_ethereum_block_header(256)
        self.assertEqual(header["hash"], "0x" + "c" * 64)
        page = adapter.fetch_ethereum_erc20_transfer_logs(contract, 256, 265)
        self.assertEqual(page.network_id, "ethereum-mainnet")
        self.assertEqual(page.finalized_height, 512)
        self.assertEqual(page.records[0].log_index, 7)
        self.assertEqual(page.records[0].amount_raw, "123456")
        self.assertEqual(page.records[0].from_address, sender)
        self.assertEqual(calls[-1][0], "eth_getLogs")
        self.assertEqual(calls[-1][1][0]["fromBlock"], "0x100")
        self.assertEqual(calls[-1][1][0]["toBlock"], "0x109")
        with self.assertRaisesRegex(ValueError, "10 blocks"):
            adapter.fetch_ethereum_erc20_transfer_logs(contract, 256, 266)

    def test_ethereum_eth_getlogs_rejects_range_beyond_finalized_head(self):
        adapter, _ = self.adapter([
            "0x1", {"number": "0x100", "hash": "0x" + "c" * 64},
        ])
        with self.assertRaises(ProviderTransportError) as error:
            adapter.fetch_ethereum_erc20_transfer_logs("0x" + "3" * 40, 257, 257)
        self.assertEqual(error.exception.reason_code, "BLOCK_RANGE_NOT_FINALIZED")

    def test_ethereum_block_header_rejects_wrong_height(self):
        adapter, _ = self.adapter([
            {"number": "0x101", "hash": "0x" + "c" * 64, "timestamp": "0x6553f100"},
        ])
        with self.assertRaises(ProviderTransportError) as error:
            adapter.fetch_ethereum_block_header(256)
        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")

    def test_bnb_worker_header_methods_validate_finalized_height_and_exact_block_identity(self):
        adapter, calls = self.adapter([
            "0x38",
            {"number": "0x200", "hash": "0x" + "b" * 64},
            {"number": "0x201", "hash": "0x" + "c" * 64, "timestamp": "0x6553f100"},
        ])
        self.assertEqual(adapter.fetch_bnb_finalized_height(), 512)
        header = adapter.fetch_bnb_block_header(513)
        self.assertEqual(header["number"], 513)
        self.assertEqual(header["hash"], "0x" + "c" * 64)
        self.assertEqual(header["timestamp"], int("6553f100", 16))
        self.assertEqual([call[0] for call in calls], [
            "eth_chainId", "eth_getFinalizedHeader", "eth_getBlockByNumber",
        ])
        self.assertEqual(calls[-1][1], ["0x201", False])

    def test_bnb_block_header_rejects_wrong_returned_height(self):
        adapter, _ = self.adapter([
            {"number": "0x202", "hash": "0x" + "c" * 64, "timestamp": "0x6553f100"},
        ])
        with self.assertRaises(ProviderTransportError) as error:
            adapter.fetch_bnb_block_header(513)
        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")

    def test_alchemy_bnb_probe_checks_chain_id_56_and_finalized_header(self):
        adapter, calls = self.adapter([
            "0x38",
            {"number": "0x200", "hash": "0x" + "b" * 64, "timestamp": "0x6553f100"},
        ])
        result = adapter.probe("bnb-smart-chain-mainnet")
        self.assertEqual(result.network_id, "bnb-smart-chain-mainnet")
        self.assertEqual(result.finality_reference, "eth_getFinalizedHeader:verifiedValidatorNum=-3")
        self.assertEqual([call[0] for call in calls], ["eth_chainId", "eth_getFinalizedHeader"])
        self.assertEqual(calls[1][1], [-3])

    def test_alchemy_solana_probe_checks_mainnet_genesis_and_finalized_slot(self):
        adapter, calls = self.adapter([
            "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
            300000000,
        ])
        result = adapter.probe("solana-mainnet")
        self.assertEqual(result.head_height, 300000000)
        self.assertEqual(result.finality_reference, "commitment=finalized")
        self.assertEqual(calls[1], ("getSlot", [{"commitment": "finalized"}]))

    def test_chainstack_xrpl_probe_uses_only_validated_ledger(self):
        calls = []
        def factory(endpoint, timeout):
            self.assertEqual(timeout, 10)
            return FakeTransport([{
                "info": {
                    "validated_ledger": {"seq": 85000000, "hash": "c" * 64, "age": 4},
                    "complete_ledgers": "84250000-85000000",
                }
            }], calls)
        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/redacted-key",
            transport_factory=factory,
        )
        result = adapter.probe()
        self.assertEqual(result.provider, "chainstack")
        self.assertEqual(result.finality, "FINALIZED")
        self.assertEqual(result.finality_reference, "validated_ledger=true")
        self.assertEqual(result.history_range, "84250000-85000000")
        self.assertEqual(calls, [("server_info", [{}])])

    def test_rejects_wrong_network_id_and_unsupported_write_method(self):
        adapter, _ = self.adapter(["0x38"])
        with self.assertRaises(ProviderTransportError) as mismatch:
            adapter.probe("ethereum-mainnet")
        self.assertEqual(mismatch.exception.reason_code, "NETWORK_ID_MISMATCH")
        with self.assertRaisesRegex(ValueError, "not allowed"):
            adapter._call("ethereum-mainnet", "eth_sendRawTransaction", ["0xdead"])

    def test_json_rpc_transport_validates_envelope_and_redacts_endpoint_on_http_error(self):
        captured = {}
        def opener(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeHttpResponse(b'{"jsonrpc":"2.0","id":1,"result":"0x1"}')
        transport = ReadOnlyJsonRpcTransport(
            "https://example.invalid/v2/secret", opener=opener,
        )
        self.assertEqual(transport.call("eth_chainId"), "0x1")
        self.assertEqual(captured["body"]["method"], "eth_chainId")
        self.assertEqual(captured["timeout"], 10)

        def http_error_opener(request, timeout):
            raise HTTPError(request.full_url, 429, "rate limited", None, None)
        limited = ReadOnlyJsonRpcTransport(
            "https://example.invalid/v2/secret", opener=http_error_opener,
        )
        with self.assertRaises(ProviderTransportError) as error:
            limited.call("eth_blockNumber")
        self.assertEqual(error.exception.reason_code, "RATE_LIMITED")
        self.assertNotIn("secret", str(error.exception))

    def test_chainstack_xrpl_probe_rejects_empty_history_window(self):
        def factory(endpoint, timeout):
            return FakeTransport([{
                "info": {
                    "validated_ledger": {"seq": 85000000, "hash": "c" * 64, "age": 4},
                    "complete_ledgers": "empty",
                }
            }], [])
        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/redacted-key",
            transport_factory=factory,
        )
        with self.assertRaises(ProviderTransportError) as error:
            adapter.probe()
        self.assertEqual(error.exception.reason_code, "XRPL_HISTORY_WINDOW_UNAVAILABLE")

    def test_rest_transport_uses_get_and_never_exposes_api_key_in_errors(self):
        captured = {}
        def opener(request, timeout):
            captured["method"] = request.get_method()
            captured["url"] = request.full_url
            return FakeHttpResponse(b'{"ok":true}')
        transport = ReadOnlyJsonRpcTransport("https://example.invalid/v2/secret", opener=opener)
        self.assertEqual(transport.get_json("api/v2/address/test", {"page": 2}), {"ok": True})
        self.assertEqual(captured["method"], "GET")
        self.assertIn("page=2", captured["url"])
        with self.assertRaisesRegex(ValueError, "relative path"):
            transport.get_json("../escape")

    def test_transport_rejects_mismatched_json_rpc_response_id(self):
        def opener(request, timeout):
            return FakeHttpResponse(b'{"jsonrpc":"2.0","id":99,"result":"0x1"}')
        transport = ReadOnlyJsonRpcTransport("https://example.invalid/key", opener=opener)
        with self.assertRaises(ProviderTransportError) as error:
            transport.call("eth_chainId")
        self.assertEqual(error.exception.reason_code, "INVALID_RPC_ENVELOPE")

    def test_bitcoin_address_history_keeps_unconfirmed_transactions_pending(self):
        calls = []
        class FakeRestTransport(FakeTransport):
            def get_json(self, path, query=None):
                return {"address": "bc1qexample", "page": 1, "totalPages": 1,
                        "txs": [{"txid": "a" * 64, "confirmations": 0}]}
        adapter = AlchemyReadOnlyAdapter(
            "test-key", transport_factory=lambda endpoint, timeout: FakeRestTransport([], calls),
        )
        page = adapter.fetch_bitcoin_address_transactions("bc1qexample")
        self.assertEqual(page.records[0].finality, "PENDING")
        self.assertIsNone(page.records[0].block_height)

    def test_bitcoin_address_history_marks_negative_confirmation_transaction_orphaned(self):
        class FakeRestTransport(FakeTransport):
            def get_json(self, path, query=None):
                return {"address": "bc1qexample", "page": 1, "totalPages": 1,
                        "txs": [{"txid": "a" * 64, "confirmations": -1}]}
        adapter = AlchemyReadOnlyAdapter(
            "test-key", transport_factory=lambda endpoint, timeout: FakeRestTransport([], []),
        )
        page = adapter.fetch_bitcoin_address_transactions("bc1qexample")
        self.assertEqual(page.records[0].finality, "ORPHANED")

    def test_ethereum_asset_transfers_are_contract_scoped_and_paginated(self):
        adapter, calls = self.adapter([
            "0x1",
            {"number": "0xc8", "hash": "0x" + "c" * 64},
            {
            "transfers": [{
                "blockNum": "0x64", "hash": "0x" + "a" * 64,
                "from": "0x" + "1" * 40, "to": "0x" + "2" * 40,
                "category": "erc20", "asset": "TOK",
                "rawContract": {"value": "0x64", "address": "0x" + "3" * 40, "decimal": "0x12"},
                "metadata": {"blockTimestamp": "2026-11-11T00:00:00Z"},
            }],
            "pageKey": "next-page",
        }])
        page = adapter.fetch_ethereum_asset_transfers(
            contract_addresses=["0x" + "3" * 40], from_block=100, to_block=200,
            page_key="previous-page", max_count=250,
        )
        self.assertIsInstance(page, ProviderDataPage)
        self.assertEqual(page.network_id, "ethereum-mainnet")
        self.assertEqual(page.next_cursor, "next-page")
        self.assertEqual(page.finalized_height, 200)
        self.assertEqual(page.finality_reference, "eth_getBlockByNumber:finalized")
        self.assertEqual(len(page.records), 1)
        self.assertIsInstance(page.records[0], EthereumAssetTransfer)
        self.assertEqual(page.records[0].amount_raw, "100")
        self.assertEqual(page.records[0].decimals, 18)
        self.assertEqual(page.records[0].contract_address, "0x" + "3" * 40)
        params = calls[2][1][0]
        self.assertEqual(calls[2][0], "alchemy_getAssetTransfers")
        self.assertEqual(params["fromBlock"], "0x64")
        self.assertEqual(params["toBlock"], "0xc8")
        self.assertEqual(params["contractAddresses"], ["0x" + "3" * 40])
        self.assertEqual(params["maxCount"], "0xfa")
        self.assertEqual(params["pageKey"], "previous-page")

    def test_ethereum_transfer_page_rejects_unmapped_token_contract(self):
        adapter, _ = self.adapter([
            "0x1", {"number": "0xc8", "hash": "0x" + "c" * 64},
            {"transfers": [{
                "blockNum": "0x64", "hash": "0x" + "a" * 64,
                "from": "0x" + "1" * 40, "to": "0x" + "2" * 40,
                "category": "erc20", "rawContract": {"value": "0x64", "address": "0x" + "4" * 40, "decimal": "0x12"},
            }]},
        ])
        with self.assertRaises(ProviderTransportError) as error:
            adapter.fetch_ethereum_asset_transfers(
                contract_addresses=["0x" + "3" * 40], from_block=100, to_block=200,
            )
        self.assertEqual(error.exception.reason_code, "TRANSFER_CONTRACT_MISMATCH")

    def test_ethereum_transfer_query_rejects_unfinalized_block_range(self):
        adapter, _ = self.adapter([
            "0x1", {"number": "0x64", "hash": "0x" + "c" * 64},
        ])
        with self.assertRaises(ProviderTransportError) as error:
            adapter.fetch_ethereum_asset_transfers(
                contract_addresses=["0x" + "3" * 40], from_block=100, to_block=101,
            )
        self.assertEqual(error.exception.reason_code, "BLOCK_RANGE_NOT_FINALIZED")

    def test_bnb_transfer_query_rejects_unfinalized_block_range(self):
        adapter, _ = self.adapter([
            "0x38", {"number": "0x64", "hash": "0x" + "c" * 64},
        ])
        with self.assertRaises(ProviderTransportError) as error:
            adapter.fetch_bnb_erc20_transfer_logs("0x" + "3" * 40, 100, 101)
        self.assertEqual(error.exception.reason_code, "BLOCK_RANGE_NOT_FINALIZED")

    def test_ethereum_native_transfer_query_requires_a_monitored_address_even_with_contract_filter(self):
        adapter, _ = self.adapter([])
        with self.assertRaisesRegex(ValueError, "require a monitored"):
            adapter.fetch_ethereum_asset_transfers(
                contract_addresses=["0x" + "3" * 40], categories=["external"],
                from_block=100, to_block=200,
            )

    def test_ethereum_transfer_query_rejects_unscoped_global_scan(self):
        adapter, _ = self.adapter([])
        with self.assertRaisesRegex(ValueError, "must be scoped"):
            adapter.fetch_ethereum_asset_transfers(
                categories=["erc20"], from_block=1, to_block=2,
            )

    def test_bnb_erc20_logs_are_contract_scoped_decoded_and_free_tier_range_bounded(self):
        contract = "0x" + "3" * 40
        sender = "0x" + "1" * 40
        recipient = "0x" + "2" * 40
        transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        log = {
            "address": contract, "blockNumber": "0x64", "blockHash": "0x" + "a" * 64,
            "transactionHash": "0x" + "b" * 64, "logIndex": "0x2", "removed": False,
            "topics": [transfer_topic, "0x" + "0" * 24 + sender[2:], "0x" + "0" * 24 + recipient[2:]],
            "data": "0x" + format(123456, "064x"),
        }
        adapter, calls = self.adapter([
            "0x38", {"number": "0x200", "hash": "0x" + "c" * 64}, [log],
        ])
        page = adapter.fetch_bnb_erc20_transfer_logs(contract, 100, 109)
        event = page.records[0]
        self.assertEqual(event.from_address, sender)
        self.assertEqual(event.to_address, recipient)
        self.assertEqual(event.amount_raw, "123456")
        self.assertEqual(event.log_index, 2)
        self.assertFalse(event.removed)
        self.assertEqual(page.finalized_height, 512)
        self.assertEqual(page.finality_reference, "eth_getFinalizedHeader:verifiedValidatorNum=-3")
        self.assertEqual(calls[2][0], "eth_getLogs")
        self.assertEqual(calls[2][1][0]["fromBlock"], "0x64")
        self.assertEqual(calls[2][1][0]["toBlock"], "0x6d")
        with self.assertRaisesRegex(ValueError, "10 blocks"):
            adapter.fetch_bnb_erc20_transfer_logs(contract, 100, 110)

    def test_bnb_reorg_removed_log_is_preserved_as_removed_not_counted_as_live(self):
        contract = "0x" + "3" * 40
        topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        log = {
            "address": contract, "blockNumber": "0x64", "blockHash": "0x" + "a" * 64,
            "transactionHash": "0x" + "b" * 64, "logIndex": "0x2", "removed": True,
            "topics": [topic, "0x" + "0" * 64, "0x" + "0" * 64],
            "data": "0x" + "0" * 64,
        }
        adapter, _ = self.adapter([
            "0x38", {"number": "0x200", "hash": "0x" + "c" * 64}, [log],
        ])
        event = adapter.fetch_bnb_erc20_transfer_logs(contract, 100, 100).records[0]
        self.assertTrue(event.removed)

    def test_solana_address_transaction_pages_require_finalized_commitment(self):
        address = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
        adapter, calls = self.adapter([
            SOLANA_MAINNET_GENESIS_HASH,
            {"transactions": [{"signature": "3jUKrQp1UGq5ih6FTDUUt2kkqUfoG2o4kY5T1DoVHK2tXXDLdxJSXzuJGY4JPoRivgbi45U2bc7LZfMa6C4R3szX",
                                "slot": 300, "transactionIndex": 17,
                                "transaction": {"signatures": ["3jUKrQp1UGq5ih6FTDUUt2kkqUfoG2o4kY5T1DoVHK2tXXDLdxJSXzuJGY4JPoRivgbi45U2bc7LZfMa6C4R3szX"]},
                                "meta": {"err": None}}],
             "paginationToken": "next"},
        ])
        page = adapter.fetch_solana_address_transactions(
            address, pagination_token="prev", limit=50, slot_start=200, slot_end=300)
        self.assertEqual(page.next_cursor, "next")
        self.assertEqual(page.finality_reference, "commitment=finalized")
        self.assertIsInstance(page.records[0], SolanaAddressTransaction)
        self.assertEqual(page.records[0].transaction_index, 17)
        self.assertEqual(calls[1][0], "getTransactionsForAddress")
        self.assertEqual(calls[1][1][1]["transactionDetails"], "full")
        self.assertEqual(calls[1][1][1]["commitment"], "finalized")
        self.assertEqual(calls[1][1][1]["encoding"], "json")
        self.assertEqual(calls[1][1][1]["maxSupportedTransactionVersion"], 1)
        self.assertEqual(calls[1][1][1]["filters"], {
            "status": "succeeded", "tokenAccounts": "balanceChanged",
            "slot": {"gte": 200, "lte": 300},
        })
        self.assertEqual(calls[1][1][1]["paginationToken"], "prev")
        self.assertEqual(calls[1][1][1]["filters"]["slot"], {"gte": 200, "lte": 300})

    def test_solana_address_history_rejects_records_outside_fixed_slot_range(self):
        address = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
        signature = "3jUKrQp1UGq5ih6FTDUUt2kkqUfoG2o4kY5T1DoVHK2tXXDLdxJSXzuJGY4JPoRivgbi45U2bc7LZfMa6C4R3szX"
        adapter, _ = self.adapter([
            SOLANA_MAINNET_GENESIS_HASH,
            {"transactions": [{
                "signature": signature, "slot": 301, "transactionIndex": 3,
                "transaction": {"signatures": [signature]}, "meta": {"err": None},
            }], "paginationToken": None},
        ])
        with self.assertRaises(ProviderTransportError):
            adapter.fetch_solana_address_transactions(address, slot_start=200, slot_end=300)

    def test_solana_slot_range_requires_both_fixed_bounds(self):
        address = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
        adapter, _ = self.adapter([SOLANA_MAINNET_GENESIS_HASH])
        with self.assertRaises(ValueError):
            adapter.fetch_solana_address_transactions(address, slot_start=100)

    def test_solana_finalized_slot_and_canonical_block_header(self):
        blockhash = "11111111111111111111111111111111"
        adapter, calls = self.adapter([
            SOLANA_MAINNET_GENESIS_HASH, 300,
            {"blockhash": blockhash, "blockTime": 1794398400, "parentSlot": 299},
        ])
        self.assertEqual(adapter.fetch_solana_finalized_slot(), 300)
        header = adapter.fetch_solana_block_header(300)
        self.assertEqual(header["number"], 300)
        self.assertEqual(header["hash"], blockhash)
        self.assertEqual(header["timestamp"], 1794398400)
        self.assertEqual(header["finality_reference"], "commitment=finalized")
        self.assertEqual(calls[2][1][1]["maxSupportedTransactionVersion"], 1)
        self.assertEqual([call[0] for call in calls], ["getGenesisHash", "getSlot", "getBlock"])

    def test_solana_produced_slots_and_skipped_slot_are_explicit(self):
        adapter, calls = self.adapter([[100, 102, 105], None])
        self.assertEqual(adapter.fetch_solana_produced_slots(100, 105), (100, 102, 105))
        self.assertIsNone(adapter.fetch_solana_block_header(101))
        self.assertEqual(calls[0][1], [100, 105, {"commitment": "finalized"}])

    def test_bitcoin_transaction_details_fetches_vin_vout_by_exact_txid(self):
        txid = "a" * 64
        calls = []
        class FakeRestTransport(FakeTransport):
            def get_json(self, path, query=None):
                calls.append((path, query))
                return {
                    "txid": txid, "vin": [{"addresses": ["1BoatSLRHtKNngkdXEeobR76b53LETtpyT"]}],
                    "vout": [{"n": 0, "value": "1000", "addresses": ["bc1qexample"]}],
                }
        def factory(endpoint, timeout):
            return FakeRestTransport([], [])
        adapter = AlchemyReadOnlyAdapter("test-key", transport_factory=factory)
        result = adapter.fetch_bitcoin_transaction(txid)
        self.assertEqual(result["txid"], txid)
        self.assertEqual(len(result["vout"]), 1)
        self.assertEqual(calls[0][0], "api/v2/tx/" + txid)
        self.assertEqual(calls[0][1], {"spending": "false"})

    def test_bitcoin_transaction_details_rejects_mismatched_txid(self):
        def factory(endpoint, timeout):
            class Transport:
                def get_json(self, path, query=None):
                    return {"txid": "b" * 64, "vin": [], "vout": []}
            return Transport()
        adapter = AlchemyReadOnlyAdapter("test-key", transport_factory=factory)
        with self.assertRaises(ProviderTransportError) as error:
            adapter.fetch_bitcoin_transaction("a" * 64)
        self.assertEqual(error.exception.reason_code, "TRANSACTION_ID_MISMATCH")

    def test_bitcoin_address_history_uses_bounded_rest_pagination(self):
        calls = []
        class FakeRestTransport(FakeTransport):
            def get_json(self, path, query=None):
                calls.append((path, query))
                return {"address": "bc1qexample", "page": 2, "totalPages": 3,
                        "txs": [{"txid": "a" * 64, "blockHeight": 900000,
                                 "blockHash": "b" * 64, "blockTime": 1794398340,
                                 "confirmations": 3}]}
        def factory(endpoint, timeout):
            return FakeRestTransport([], [])
        adapter = AlchemyReadOnlyAdapter("test-key", transport_factory=factory)
        page = adapter.fetch_bitcoin_address_transactions("bc1qexample", page=2, page_size=25)
        self.assertEqual(page.next_cursor, 3)
        self.assertIsInstance(page.records[0], BitcoinAddressTransaction)
        self.assertEqual(page.records[0].txid, "a" * 64)
        self.assertEqual(page.records[0].finality, "CONFIRMED")
        self.assertEqual(calls[0][0], "api/v2/address/bc1qexample")
        self.assertEqual(calls[0][1]["details"], "txs")
        self.assertEqual(calls[0][1]["pageSize"], 25)

    def test_xrpl_account_tx_uses_fixed_validated_ledger_range_and_opaque_marker(self):
        calls = []
        def factory(endpoint, timeout):
            return FakeTransport([{
                "account": "rLNaPoKeeBjZe2qs6x52yVPZpZ8td4dc6w", "validated": True,
                "ledger_index_min": 100, "ledger_index_max": 200,
                "transactions": [{"hash": "A" * 64, "validated": True, "ledger_index": 150,
                                  "tx_json": {"TransactionType": "Payment"}, "meta": {"TransactionResult": "tesSUCCESS"}}],
                "marker": {"ledger": 150, "seq": 5},
            }], calls)
        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/redacted-key", transport_factory=factory,
        )
        page = adapter.fetch_account_transactions(
            "rLNaPoKeeBjZe2qs6x52yVPZpZ8td4dc6w", ledger_index_min=100, ledger_index_max=200,
            marker={"ledger": 149, "seq": 4}, limit=50,
        )
        self.assertEqual(page.next_cursor, {"ledger": 150, "seq": 5})
        self.assertEqual(page.finality_reference, "validated=true")
        self.assertIsInstance(page.records[0], XrplAccountTransaction)
        self.assertEqual(page.records[0].transaction_hash, "A" * 64)
        params = calls[0][1][0]
        self.assertEqual(params["ledger_index_min"], 100)
        self.assertEqual(params["ledger_index_max"], 200)
        self.assertEqual(params["marker"], {"ledger": 149, "seq": 4})
        self.assertTrue(page.complete is False)

    def test_xrpl_fetches_exact_validated_ledger_header_and_converts_ripple_close_time(self):
        calls = []
        def factory(endpoint, timeout):
            return FakeTransport([{
                "validated": True, "ledger_index": 500, "ledger_hash": "B" * 64,
                "ledger": {"ledger_index": 500, "ledger_hash": "B" * 64, "close_time": 800000000},
            }], calls)
        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/redacted-key", transport_factory=factory,
        )
        header = adapter.fetch_ledger_header(500)
        self.assertEqual(header["number"], 500)
        self.assertEqual(header["hash"], "b" * 64)
        self.assertEqual(header["timestamp"], 1746684800)
        self.assertEqual(header["finality_reference"], "validated=true")
        self.assertEqual(calls[0][0], "ledger")
        self.assertEqual(calls[0][1][0], {"ledger_index": 500, "transactions": False, "expand": False})

    def test_xrpl_ledger_header_rejects_unvalidated_or_wrong_ledger(self):
        for result in (
            {"validated": False, "ledger_index": 500, "ledger_hash": "B" * 64,
             "ledger": {"close_time": 800000000}},
            {"validated": True, "ledger_index": 501, "ledger_hash": "B" * 64,
             "ledger": {"close_time": 800000000}},
        ):
            adapter = ChainstackXrplReadOnlyAdapter(
                "https://xrpl-mainnet.core.chainstack.com/redacted-key",
                transport_factory=lambda endpoint, timeout, value=result: FakeTransport([value], []),
            )
            with self.assertRaises(ProviderTransportError):
                adapter.fetch_ledger_header(500)

    def test_xrpl_rejects_unvalidated_transaction_pages(self):
        def factory(endpoint, timeout):
            return FakeTransport([{
                "account": "rLNaPoKeeBjZe2qs6x52yVPZpZ8td4dc6w", "validated": True,
                "transactions": [{"hash": "A" * 64, "validated": False,
                                  "ledger_index": 150, "tx_json": {}, "meta": {}}],
            }], [])
        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/redacted-key", transport_factory=factory,
        )
        with self.assertRaises(ProviderTransportError) as error:
            adapter.fetch_account_transactions("rLNaPoKeeBjZe2qs6x52yVPZpZ8td4dc6w", ledger_index_min=100, ledger_index_max=200)
        self.assertEqual(error.exception.reason_code, "UNVALIDATED_XRPL_TRANSACTION")

    def test_chainstack_rejects_non_mainnet_or_non_https_endpoint(self):
        with self.assertRaisesRegex(ValueError, "mainnet endpoint"):
            ChainstackXrplReadOnlyAdapter("https://xrpl-testnet.core.chainstack.com/key")
        with self.assertRaisesRegex(ValueError, "mainnet endpoint"):
            ChainstackXrplReadOnlyAdapter("http://xrpl-mainnet.core.chainstack.com/key")


if __name__ == "__main__":
    unittest.main()
