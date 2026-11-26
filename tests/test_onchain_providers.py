import hashlib
import http.server
import json
import os
import ssl
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from dataclasses import FrozenInstanceError
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, ProxyHandler, Request

from layer1.onchain_providers import (
    AlchemyReadOnlyAdapter,
    ALCHEMY_ENDPOINTS,
    _alchemy_endpoint,
    BitcoinAddressTransaction,
    EthereumAssetTransfer,
    ChainstackXrplReadOnlyAdapter,
    ProviderDataPage,
    SolanaAddressTransaction,
    XrplAccountTransaction,
    ProviderTransportError,
    _parse_hex_quantity,
    ReadOnlyJsonRpcTransport,
    SOLANA_MAINNET_GENESIS_HASH,
    is_valid_xrpl_classic_address,
    retry_provider_operation,
    _ACTIVE_PAGE_RECEIPTS,
    _capture_provider_page_receipts,
    _capture_provider_run_receipts,
    drain_provider_run_receipts,
    include_provider_receipts_in_current_scope,
    _open_without_redirect,
    _endpoint_profile_sha256, _approved_endpoint_profile_sha256,
)


_TLS_FIXTURES = Path(__file__).parent / "fixtures" / "onchain_tls"


@contextmanager
def _local_tls_server(cert_name):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            payload = b"tls-test-ok"
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(
        _TLS_FIXTURES / f"{cert_name}.pem",
        _TLS_FIXTURES / f"{cert_name}-key.pem",
    )
    server.socket = server_context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{server.server_port}/health"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class FakeTransport:
    def __init__(self, responses, calls, endpoint=None):
        self.responses = responses
        self.calls = calls
        self.endpoint_profile_sha256 = (
            _endpoint_profile_sha256(endpoint) if endpoint is not None else None
        )
        self.last_response_attestation = None

    def call(self, method, params=None):
        self.calls.append((method, params))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            self.last_response_attestation = None
            raise response
        ordinal = len(self.calls)
        self.last_response_attestation = {
            "request_sha256": hashlib.sha256(f"request-{ordinal}".encode()).hexdigest(),
            "response_sha256": hashlib.sha256(json.dumps(response, sort_keys=True).encode()).hexdigest(),
            **({"endpoint_profile_sha256": self.endpoint_profile_sha256}
               if self.endpoint_profile_sha256 is not None else {}),
            "response_bytes": len(json.dumps(response).encode()),
            "http_status": 200,
            "received_at": "2026-11-26T00:00:00+00:00",
        }
        return response


class FakeHttpResponse:
    def __init__(self, payload, headers=None):
        self.payload = payload
        self.headers = headers or {}
        self.read_calls = []
        self._offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        self.read_calls.append(size)
        if size is None or size < 0:
            size = len(self.payload) - self._offset
        chunk = self.payload[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk


class OnChainProviderTests(unittest.TestCase):
    def adapter(self, responses):
        calls = []
        def factory(endpoint, timeout):
            self.assertTrue(endpoint.startswith("https://"))
            self.assertEqual(timeout, 10)
            return FakeTransport(responses, calls, endpoint)
        return AlchemyReadOnlyAdapter("test-key", transport_factory=factory), calls

    def test_nested_page_capture_keeps_worker_supporting_calls_and_drains_ordered_receipts(self):
        from layer1.onchain_providers import ProviderResponseReceipt

        def receipt(method, sequence):
            return ProviderResponseReceipt(
                sequence=sequence, provider="alchemy", network_id="ethereum-mainnet",
                method=method, request_sha256=("a" if sequence == 1 else "c") * 64,
                response_sha256=("b" if sequence == 1 else "d") * 64,
                response_bytes=10, http_status=200,
                received_at="2026-11-26T00:00:00+00:00",
            endpoint_profile_sha256="e" * 64,
            )

        class Worker:
            @_capture_provider_run_receipts
            def run_once(self):
                collector = _ACTIVE_PAGE_RECEIPTS.get()
                collector.append(receipt("eth_getBlockByNumber", len(collector) + 1))
                page = self.fetch_page()
                self.assert_page_receipts = page.response_receipts
                drained = drain_provider_run_receipts()
                self.assert_drained = drained
                assert _ACTIVE_PAGE_RECEIPTS.get() == []
                return "ok"

            @_capture_provider_page_receipts
            def fetch_page(self):
                collector = _ACTIVE_PAGE_RECEIPTS.get()
                collector.append(receipt("eth_getLogs", len(collector) + 1))
                return ProviderDataPage("alchemy", "ethereum-mainnet", "contract:test", ())

        worker = Worker()
        self.assertEqual(worker.run_once(), "ok")
        self.assertEqual([r.method for r in worker.assert_page_receipts], ["eth_getLogs"])
        self.assertTrue(worker.assert_drained.is_collector_issued())
        self.assertEqual([r.method for r in worker.assert_drained.receipts], [
            "eth_getBlockByNumber", "eth_getLogs",
        ])
        self.assertEqual([r.sequence for r in worker.assert_drained.receipts], [1, 2])
        self.assertIsNone(_ACTIVE_PAGE_RECEIPTS.get())

    def test_concurrent_worker_receipt_scopes_do_not_cross_contaminate(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from layer1.onchain_providers import ProviderResponseReceipt

        barrier = Barrier(2)

        def run_worker(label):
            @_capture_provider_run_receipts
            def run():
                collector = _ACTIVE_PAGE_RECEIPTS.get()
                collector.append(ProviderResponseReceipt(
                    sequence=1, provider="alchemy", network_id="ethereum-mainnet",
                    method=label, request_sha256="a" * 64, response_sha256="b" * 64,
                    response_bytes=1, http_status=200,
                    received_at="2026-11-26T00:00:00+00:00",
            endpoint_profile_sha256="e" * 64,
                ))
                barrier.wait(timeout=2)
                return tuple(item.method for item in drain_provider_run_receipts().receipts)
            return run()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run_worker, ("worker-a", "worker-b")))
        self.assertEqual(results, [("worker-a",), ("worker-b",)])
        self.assertIsNone(_ACTIVE_PAGE_RECEIPTS.get())

    def test_captured_shared_provider_evidence_can_be_replayed_into_each_scope(self):
        from layer1.onchain_providers import ProviderResponseReceipt
        @_capture_provider_run_receipts
        def exercise():
            collector = _ACTIVE_PAGE_RECEIPTS.get()
            collector.append(ProviderResponseReceipt(
                sequence=1, provider="chainstack", network_id="xrpl-mainnet",
                method="server_info", request_sha256="a" * 64,
                response_sha256="b" * 64, response_bytes=64, http_status=200,
                received_at="2026-11-26T00:00:00+00:00",
            endpoint_profile_sha256="e" * 64,
            ))
            shared = drain_provider_run_receipts()
            include_provider_receipts_in_current_scope(shared)
            first_page = drain_provider_run_receipts()
            include_provider_receipts_in_current_scope(shared)
            second_page = drain_provider_run_receipts()
            return first_page, second_page
        first, second = exercise()
        self.assertTrue(first.is_collector_issued())
        self.assertTrue(second.is_collector_issued())
        self.assertEqual(first.receipts, second.receipts)
        self.assertEqual(first.receipts[0].sequence, 1)

    def test_replaying_raw_tuple_into_worker_receipt_scope_is_rejected(self):
        @_capture_provider_run_receipts
        def exercise():
            with self.assertRaisesRegex(ValueError, "collector-issued"):
                include_provider_receipts_in_current_scope(())
        exercise()

    def test_worker_receipt_scope_isolated_and_reset_after_exception(self):
        @_capture_provider_run_receipts
        def failing_worker():
            self.assertIsNotNone(_ACTIVE_PAGE_RECEIPTS.get())
            raise RuntimeError("expected test failure")
        with self.assertRaisesRegex(RuntimeError, "expected test failure"):
            failing_worker()
        self.assertIsNone(_ACTIVE_PAGE_RECEIPTS.get())
        with self.assertRaisesRegex(RuntimeError, "inside a worker capture scope"):
            drain_provider_run_receipts()

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
        self.assertEqual(len(page.response_receipts), 3)
        self.assertTrue(all(
            item.endpoint_profile_sha256 == _endpoint_profile_sha256(
                "https://eth-mainnet.g.alchemy.com/v2/test-key"
            ) for item in page.response_receipts
        ))
        self.assertEqual([item.method for item in page.response_receipts], [
            "eth_chainId", "eth_getBlockByNumber", "eth_getLogs",
        ])
        self.assertEqual([item.sequence for item in page.response_receipts], [1, 2, 3])
        self.assertTrue(all(item.network_id == "ethereum-mainnet" for item in page.response_receipts))
        self.assertEqual(page.records[0].log_index, 7)
        self.assertEqual(page.records[0].amount_raw, "123456")
        self.assertEqual(page.records[0].from_address, sender)
        self.assertEqual(calls[-1][0], "eth_getLogs")
        self.assertEqual(calls[-1][1][0]["fromBlock"], "0x100")
        self.assertEqual(calls[-1][1][0]["toBlock"], "0x109")
        with self.assertRaisesRegex(ValueError, "10 blocks"):
            adapter.fetch_ethereum_erc20_transfer_logs(contract, 256, 266)

    def test_ethereum_page_carries_exact_raw_response_receipts_for_each_rpc_call(self):
        contract = "0x" + "3" * 40
        raw_responses = [
            b'{"jsonrpc":"2.0","id":1,"result":"0x1"}',
            (b'{"jsonrpc":"2.0","id":1,"result":{"number":"0x200","hash":"0x'
             + b'c' * 64 + b'"}}'),
            b'{"jsonrpc":"2.0","id":1,"result":[]}',
        ]
        response_index = []
        def opener(request, timeout):
            self.assertEqual(timeout, 10)
            raw = raw_responses[len(response_index)]
            response_index.append(raw)
            return FakeHttpResponse(raw, headers={"Content-Length": str(len(raw))})
        adapter = AlchemyReadOnlyAdapter(
            "test-key",
            transport_factory=lambda endpoint, timeout: ReadOnlyJsonRpcTransport(
                endpoint, timeout, opener=opener, max_response_bytes=4096,
            ),
        )
        page = adapter.fetch_ethereum_erc20_transfer_logs(contract, 256, 265)
        self.assertEqual(len(page.response_receipts), 3)
        self.assertEqual(
            [receipt.response_sha256 for receipt in page.response_receipts],
            [hashlib.sha256(raw).hexdigest() for raw in raw_responses],
        )
        self.assertEqual([receipt.response_bytes for receipt in page.response_receipts],
                         [len(raw) for raw in raw_responses])
        self.assertEqual([receipt.sequence for receipt in page.response_receipts], [1, 2, 3])
        self.assertTrue(all(receipt.http_status == 200 for receipt in page.response_receipts))
        self.assertNotIn("test-key", repr(page.response_receipts))
        with self.assertRaises(FrozenInstanceError):
            page.response_receipts[0].method = "tampered"
        with self.assertRaises(AttributeError):
            page.response_receipts.append(page.response_receipts[0])

    def test_ethereum_worker_finality_log_and_canonical_header_calls_emit_ordered_receipts(self):
        contract = "0x" + "3" * 40
        adapter, _ = self.adapter([
            "0x1", {"number": "0x200", "hash": "0x" + "b" * 64},
            "0x1", {"number": "0x200", "hash": "0x" + "b" * 64}, [],
            {"number": "0x100", "hash": "0x" + "c" * 64, "timestamp": "0x6553f100"},
        ])

        @_capture_provider_run_receipts
        def worker_provider_sequence():
            self.assertEqual(adapter.fetch_ethereum_finalized_height(), 512)
            page = adapter.fetch_ethereum_erc20_transfer_logs(contract, 256, 265)
            self.assertEqual([item.method for item in page.response_receipts], [
                "eth_chainId", "eth_getBlockByNumber", "eth_getLogs",
            ])
            adapter.fetch_ethereum_block_header(256)
            return drain_provider_run_receipts()

        batch = worker_provider_sequence()
        self.assertEqual([item.method for item in batch.receipts], [
            "eth_chainId", "eth_getBlockByNumber", "eth_chainId",
            "eth_getBlockByNumber", "eth_getLogs", "eth_getBlockByNumber",
        ])
        self.assertEqual([item.sequence for item in batch.receipts], list(range(1, 7)))
        expected_profile = _approved_endpoint_profile_sha256("alchemy", "ethereum-mainnet")
        self.assertTrue(all(item.endpoint_profile_sha256 == expected_profile for item in batch.receipts))

    def test_evm_json_rpc_quantity_rejects_noncanonical_encodings(self):
        for value in ("0x", "0x00", "0x01", "0x000a", "0x+1", "0x 1", "0x-1", "0x1g", "0X1"):
            with self.subTest(value=value):
                with self.assertRaises(ProviderTransportError):
                    AlchemyReadOnlyAdapter._hex_int(value, "test quantity")

    def test_evm_json_rpc_quantity_accepts_canonical_zero_and_hex_values(self):
        self.assertEqual(AlchemyReadOnlyAdapter._hex_int("0x0", "test quantity"), 0)
        self.assertEqual(AlchemyReadOnlyAdapter._hex_int("0x1", "test quantity"), 1)
        self.assertEqual(AlchemyReadOnlyAdapter._hex_int("0xa0f", "test quantity"), 0xA0F)
        self.assertEqual(_parse_hex_quantity("0xa0f", "test quantity"), 0xA0F)

    def test_evm_log_quantity_parser_rejects_noncanonical_encodings(self):
        for value in ("0x", "0x00", "0x01", "0x000a", "0x+1", "0x 1", "0x-1", "0x1g", "0X1", "0xA0f"):
            with self.subTest(value=value):
                with self.assertRaises(ProviderTransportError):
                    _parse_hex_quantity(value, "test quantity")

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

    def test_bnb_worker_finality_log_and_canonical_header_calls_emit_ordered_receipts(self):
        contract = "0x" + "3" * 40
        adapter, _ = self.adapter([
            "0x38", {"number": "0x200", "hash": "0x" + "b" * 64},
            "0x38", {"number": "0x200", "hash": "0x" + "b" * 64}, [],
            {"number": "0x100", "hash": "0x" + "c" * 64, "timestamp": "0x6553f100"},
        ])

        @_capture_provider_run_receipts
        def worker_provider_sequence():
            self.assertEqual(adapter.fetch_bnb_finalized_height(), 512)
            page = adapter.fetch_bnb_erc20_transfer_logs(contract, 256, 265)
            self.assertEqual([item.method for item in page.response_receipts], [
                "eth_chainId", "eth_getFinalizedHeader", "eth_getLogs",
            ])
            adapter.fetch_bnb_block_header(256)
            return drain_provider_run_receipts()

        batch = worker_provider_sequence()
        self.assertEqual([item.method for item in batch.receipts], [
            "eth_chainId", "eth_getFinalizedHeader", "eth_chainId",
            "eth_getFinalizedHeader", "eth_getLogs", "eth_getBlockByNumber",
        ])
        self.assertEqual([item.sequence for item in batch.receipts], list(range(1, 7)))
        expected_profile = _approved_endpoint_profile_sha256("alchemy", "bnb-smart-chain-mainnet")
        self.assertTrue(all(item.endpoint_profile_sha256 == expected_profile for item in batch.receipts))

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
            }], calls, endpoint)
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

    def test_chainstack_xrpl_probe_captures_server_info_response_receipt_in_worker_scope(self):
        endpoint = "https://xrpl-mainnet.core.chainstack.com/redacted-key"
        adapter = ChainstackXrplReadOnlyAdapter(
            endpoint, transport_factory=lambda url, timeout: FakeTransport([{
                "info": {
                    "validated_ledger": {"seq": 85000000, "hash": "c" * 64, "age": 4},
                    "complete_ledgers": "84250000-85000000",
                }
            }], [], url),
        )

        @_capture_provider_run_receipts
        def run_probe():
            result = adapter.probe()
            return result, drain_provider_run_receipts()

        result, batch = run_probe()
        self.assertEqual(result.status, "AVAILABLE")
        self.assertEqual(len(batch.receipts), 1)
        receipt = batch.receipts[0]
        self.assertEqual(receipt.method, "server_info")
        self.assertEqual(receipt.provider, "chainstack")
        self.assertEqual(receipt.network_id, "xrpl-mainnet")
        self.assertEqual(receipt.endpoint_profile_sha256, _approved_endpoint_profile_sha256("chainstack", "xrpl-mainnet"))

    def test_chainstack_xrpl_probe_fails_closed_without_worker_response_attestation(self):
        class UnattestedTransport:
            last_response_attestation = None
            def call(self, method, params=None):
                return {"info": {
                    "validated_ledger": {"seq": 85000000, "hash": "c" * 64, "age": 4},
                    "complete_ledgers": "84250000-85000000",
                }}

        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/redacted-key",
            transport_factory=lambda url, timeout: UnattestedTransport(),
        )
        @_capture_provider_run_receipts
        def run_probe():
            with self.assertRaises(ProviderTransportError) as error:
                adapter.probe()
            self.assertEqual(error.exception.reason_code, "MISSING_RESPONSE_ATTESTATION")
        run_probe()

    def test_rejects_wrong_network_id_and_unsupported_write_method(self):
        adapter, _ = self.adapter(["0x38"])
        with self.assertRaises(ProviderTransportError) as mismatch:
            adapter.probe("ethereum-mainnet")
        self.assertEqual(mismatch.exception.reason_code, "NETWORK_ID_MISMATCH")
        with self.assertRaisesRegex(ValueError, "not allowed"):
            adapter._call("ethereum-mainnet", "eth_sendRawTransaction", ["0xdead"])

    def test_json_rpc_transport_rejects_endpoint_userinfo_credentials(self):
        for endpoint in (
            "https://provider.example@attacker.example/v2/key",
            "https://user:password@provider.example/v2/key",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaisesRegex(ValueError, "HTTPS URL"):
                    ReadOnlyJsonRpcTransport(endpoint, max_response_bytes=1024)

    def test_default_json_rpc_transport_rejects_redirects_for_keyed_endpoints(self):
        with patch("layer1.onchain_providers._open_without_redirect", create=True) as safe_open:
            transport = ReadOnlyJsonRpcTransport("https://provider.example/v2/secret-api-key", max_response_bytes=1024)
        self.assertIs(transport._opener, safe_open)

    def test_json_rpc_transport_validates_envelope_and_redacts_endpoint_on_http_error(self):
        captured = {}
        def opener(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeHttpResponse(b'{"jsonrpc":"2.0","id":1,"result":"0x1"}')
        transport = ReadOnlyJsonRpcTransport(
            "https://example.invalid/v2/secret", opener=opener, max_response_bytes=1024,
        )
        self.assertEqual(transport.call("eth_chainId"), "0x1")
        self.assertEqual(captured["body"]["method"], "eth_chainId")
        self.assertEqual(captured["timeout"], 10)

        def http_error_opener(request, timeout):
            raise HTTPError(request.full_url, 429, "rate limited", None, None)
        limited = ReadOnlyJsonRpcTransport(
            "https://example.invalid/v2/secret", opener=http_error_opener, max_response_bytes=1024,
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
            }], [], endpoint)
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
        transport = ReadOnlyJsonRpcTransport("https://example.invalid/v2/secret", opener=opener, max_response_bytes=1024)
        self.assertEqual(transport.get_json("api/v2/address/test", {"page": 2}), {"ok": True})
        self.assertEqual(captured["method"], "GET")
        self.assertIn("page=2", captured["url"])
        with self.assertRaisesRegex(ValueError, "relative path"):
            transport.get_json("../escape")

    def test_transport_rejects_mismatched_json_rpc_response_id(self):
        def opener(request, timeout):
            return FakeHttpResponse(b'{"jsonrpc":"2.0","id":99,"result":"0x1"}')
        transport = ReadOnlyJsonRpcTransport("https://example.invalid/key", opener=opener, max_response_bytes=1024)
        with self.assertRaises(ProviderTransportError) as error:
            transport.call("eth_chainId")
        self.assertEqual(error.exception.reason_code, "INVALID_RPC_ENVELOPE")

    def test_bitcoin_address_history_rejects_invalid_address_before_transport(self):
        calls = []
        adapter = AlchemyReadOnlyAdapter(
            "test-key", transport_factory=lambda endpoint, timeout: calls.append(endpoint))
        with self.assertRaisesRegex(ValueError, "valid Bitcoin mainnet address"):
            adapter.fetch_bitcoin_address_transactions("bc1qexample")
        self.assertEqual(calls, [])

    def test_bitcoin_address_history_keeps_unconfirmed_transactions_pending(self):
        calls = []
        class FakeRestTransport(FakeTransport):
            def get_json(self, path, query=None):
                return {"address": "1BoatSLRHtKNngkdXEeobR76b53LETtpyT", "page": 1, "totalPages": 1,
                        "txs": [{"txid": "a" * 64, "confirmations": 0}]}
        adapter = AlchemyReadOnlyAdapter(
            "test-key", transport_factory=lambda endpoint, timeout: FakeRestTransport([], calls),
        )
        page = adapter.fetch_bitcoin_address_transactions("1BoatSLRHtKNngkdXEeobR76b53LETtpyT")
        self.assertEqual(page.records[0].finality, "PENDING")
        self.assertIsNone(page.records[0].block_height)

    def test_bitcoin_address_history_marks_negative_confirmation_transaction_orphaned(self):
        class FakeRestTransport(FakeTransport):
            def get_json(self, path, query=None):
                return {"address": "1BoatSLRHtKNngkdXEeobR76b53LETtpyT", "page": 1, "totalPages": 1,
                        "txs": [{"txid": "a" * 64, "confirmations": -1}]}
        adapter = AlchemyReadOnlyAdapter(
            "test-key", transport_factory=lambda endpoint, timeout: FakeRestTransport([], []),
        )
        page = adapter.fetch_bitcoin_address_transactions("1BoatSLRHtKNngkdXEeobR76b53LETtpyT")
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

    def test_bnb_erc20_logs_reject_malformed_finalized_header_hash(self):
        adapter, calls = self.adapter([
            "0x38", {"number": "0x200", "hash": "not-a-block-hash"},
        ])
        with self.assertRaises(ProviderTransportError) as error:
            adapter.fetch_bnb_erc20_transfer_logs("0x" + "3" * 40, 100, 100)
        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")
        self.assertEqual([call[0] for call in calls], ["eth_chainId", "eth_getFinalizedHeader"])

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
        self.assertEqual([item.method for item in page.response_receipts], [
            "eth_chainId", "eth_getFinalizedHeader", "eth_getLogs",
        ])
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

    def test_solana_address_history_rejects_base58_string_that_decodes_to_33_bytes(self):
        adapter, calls = self.adapter([])
        with self.assertRaisesRegex(ValueError, "valid base58 public key"):
            adapter.fetch_solana_address_transactions("z" * 44)
        self.assertEqual(calls, [])

    def test_solana_address_history_rejects_signature_that_decodes_to_66_bytes(self):
        signature = "z" * 90
        adapter, _ = self.adapter([
            SOLANA_MAINNET_GENESIS_HASH,
            {"transactions": [{
                "signature": signature, "slot": 300, "transactionIndex": 1,
                "transaction": {"signatures": [signature]}, "meta": {"err": None},
            }], "paginationToken": None},
        ])
        with self.assertRaises(ProviderTransportError):
            adapter.fetch_solana_address_transactions(
                "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY", slot_start=300, slot_end=300)

    def test_solana_address_history_accepts_a_32_byte_base58_public_key(self):
        address = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
        adapter, calls = self.adapter([SOLANA_MAINNET_GENESIS_HASH,
                                       {"transactions": [], "paginationToken": None}])
        page = adapter.fetch_solana_address_transactions(address, slot_start=10, slot_end=20)
        self.assertEqual(page.records, ())
        self.assertEqual(calls[1][0], "getTransactionsForAddress")

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

    def test_solana_worker_supporting_calls_and_transaction_page_all_emit_ordered_receipts(self):
        address = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
        blockhash = "11111111111111111111111111111111"
        adapter, _ = self.adapter([
            SOLANA_MAINNET_GENESIS_HASH, 310, [300, 301],
            {"blockhash": blockhash, "previousBlockhash": blockhash,
             "blockTime": 1794398400, "parentSlot": 299},
            {"blockhash": blockhash, "previousBlockhash": blockhash,
             "blockTime": 1794398401, "parentSlot": 300},
            SOLANA_MAINNET_GENESIS_HASH, {"transactions": [], "paginationToken": None},
        ])

        @_capture_provider_run_receipts
        def worker_provider_sequence():
            self.assertEqual(adapter.fetch_solana_finalized_slot(), 310)
            self.assertEqual(adapter.fetch_solana_produced_slots(300, 301), (300, 301))
            adapter.fetch_solana_block_header(300)
            adapter.fetch_solana_block_header(301)
            page = adapter.fetch_solana_address_transactions(
                address, pagination_token="cursor", limit=10, slot_start=300, slot_end=301,
            )
            self.assertEqual([item.method for item in page.response_receipts], [
                "getGenesisHash", "getTransactionsForAddress",
            ])
            return drain_provider_run_receipts()

        batch = worker_provider_sequence()
        self.assertTrue(batch.is_collector_issued())
        self.assertEqual([item.method for item in batch.receipts], [
            "getGenesisHash", "getSlot", "getBlocks", "getBlock", "getBlock",
            "getGenesisHash", "getTransactionsForAddress",
        ])
        self.assertEqual([item.sequence for item in batch.receipts], list(range(1, 8)))
        expected_profile = _approved_endpoint_profile_sha256("alchemy", "solana-mainnet")
        self.assertTrue(all(item.endpoint_profile_sha256 == expected_profile for item in batch.receipts))

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
            {"blockhash": blockhash, "previousBlockhash": blockhash,
             "blockTime": 1794398400, "parentSlot": 299},
        ])
        self.assertEqual(adapter.fetch_solana_finalized_slot(), 300)
        header = adapter.fetch_solana_block_header(300)
        self.assertEqual(header["number"], 300)
        self.assertEqual(header["hash"], blockhash)
        self.assertEqual(header["timestamp"], 1794398400)
        self.assertEqual(header["parent_slot"], 299)
        self.assertEqual(header["previous_block_hash"], blockhash)
        self.assertEqual(header["finality_reference"], "commitment=finalized")
        self.assertEqual(calls[2][1][1]["maxSupportedTransactionVersion"], 1)
        self.assertEqual([call[0] for call in calls], ["getGenesisHash", "getSlot", "getBlock"])

    def test_solana_block_header_rejects_missing_parent_linkage(self):
        adapter, _ = self.adapter([{"blockhash": "11111111111111111111111111111111",
                                    "blockTime": 1794398400, "parentSlot": 299}])
        with self.assertRaises(ProviderTransportError):
            adapter.fetch_solana_block_header(300)

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
                    "vout": [{"n": 0, "value": "1000", "addresses": ["1BoatSLRHtKNngkdXEeobR76b53LETtpyT"]}],
                }
        def factory(endpoint, timeout):
            return FakeRestTransport([], [])
        adapter = AlchemyReadOnlyAdapter("test-key", transport_factory=factory)
        result = adapter.fetch_bitcoin_transaction(txid)
        self.assertEqual(result["txid"], txid)
        self.assertEqual(len(result["vout"]), 1)
        self.assertEqual(calls[0][0], "api/v2/tx/" + txid)
        self.assertEqual(calls[0][1], {"spending": "false"})

    def test_bitcoin_transaction_details_fails_closed_without_worker_response_attestation(self):
        txid = "a" * 64
        class UnattestedTransport:
            last_response_attestation = None
            def get_json(self, path, query=None):
                return {"txid": txid, "vin": [], "vout": []}
        adapter = AlchemyReadOnlyAdapter(
            "test-key", transport_factory=lambda endpoint, timeout: UnattestedTransport(),
        )

        @_capture_provider_run_receipts
        def worker_detail_call():
            with self.assertRaises(ProviderTransportError) as error:
                adapter.fetch_bitcoin_transaction(txid)
            self.assertEqual(error.exception.reason_code, "MISSING_RESPONSE_ATTESTATION")
        worker_detail_call()

    def test_bitcoin_transaction_details_captures_rest_receipt_in_worker_scope(self):
        txid = "a" * 64
        class AttestedTransport:
            def __init__(self, endpoint):
                self.last_response_attestation = {
                    "request_sha256": "a" * 64, "response_sha256": "b" * 64,
                    "endpoint_profile_sha256": _endpoint_profile_sha256(endpoint),
                    "response_bytes": 128, "http_status": 200,
                    "received_at": "2026-11-26T00:00:00+00:00",
                }
            def get_json(self, path, query=None):
                return {"txid": txid, "vin": [], "vout": []}
        adapter = AlchemyReadOnlyAdapter(
            "test-key", transport_factory=lambda endpoint, timeout: AttestedTransport(endpoint),
        )

        @_capture_provider_run_receipts
        def worker_detail_call():
            result = adapter.fetch_bitcoin_transaction(txid)
            self.assertEqual(result["txid"], txid)
            return drain_provider_run_receipts()

        batch = worker_detail_call()
        self.assertEqual(len(batch.receipts), 1)
        receipt = batch.receipts[0]
        self.assertEqual(receipt.method, "GET api/v2/tx")
        self.assertEqual(receipt.network_id, "bitcoin-mainnet")
        self.assertEqual(receipt.endpoint_profile_sha256, _approved_endpoint_profile_sha256("alchemy", "bitcoin-mainnet"))

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
                return {"address": "1BoatSLRHtKNngkdXEeobR76b53LETtpyT", "page": 2, "totalPages": 3,
                        "txs": [{"txid": "a" * 64, "blockHeight": 900000,
                                 "blockHash": "b" * 64, "blockTime": 1794398340,
                                 "confirmations": 3}]}
        def factory(endpoint, timeout):
            return FakeRestTransport([], [])
        adapter = AlchemyReadOnlyAdapter("test-key", transport_factory=factory)
        page = adapter.fetch_bitcoin_address_transactions("1BoatSLRHtKNngkdXEeobR76b53LETtpyT", page=2, page_size=25)
        self.assertEqual(page.next_cursor, 3)
        self.assertIsInstance(page.records[0], BitcoinAddressTransaction)
        self.assertEqual(page.records[0].txid, "a" * 64)
        self.assertEqual(page.records[0].finality, "CONFIRMED")
        self.assertEqual(calls[0][0], "api/v2/address/1BoatSLRHtKNngkdXEeobR76b53LETtpyT")
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
            }], calls, endpoint)
        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/redacted-key", transport_factory=factory,
        )
        page = adapter.fetch_account_transactions(
            "rLNaPoKeeBjZe2qs6x52yVPZpZ8td4dc6w", ledger_index_min=100, ledger_index_max=200,
            marker={"ledger": 149, "seq": 4}, limit=50,
        )
        self.assertEqual(page.next_cursor, {"ledger": 150, "seq": 5})
        self.assertEqual(page.finality_reference, "validated=true")
        self.assertEqual(len(page.response_receipts), 1)
        self.assertEqual(page.response_receipts[0].provider, "chainstack")
        self.assertEqual(page.response_receipts[0].network_id, "xrpl-mainnet")
        self.assertEqual(page.response_receipts[0].method, "account_tx")
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
                "ledger": {"ledger_index": 500, "ledger_hash": "B" * 64,
                           "parent_hash": "A" * 64, "close_time": 800000000},
            }], calls, endpoint)
        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/redacted-key", transport_factory=factory,
        )
        header = adapter.fetch_ledger_header(500)
        self.assertEqual(header["number"], 500)
        self.assertEqual(header["hash"], "b" * 64)
        self.assertEqual(header["parent_hash"], "a" * 64)
        self.assertEqual(header["timestamp"], 1746684800)
        self.assertEqual(header["finality_reference"], "validated=true")
        self.assertEqual(calls[0][0], "ledger")
        self.assertEqual(calls[0][1][0], {"ledger_index": 500, "transactions": False, "expand": False})

    def test_xrpl_ledger_header_rejects_conflicting_outer_and_nested_ledger_index(self):
        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/redacted-key",
            transport_factory=lambda url, timeout: FakeTransport([{
                "validated": True, "ledger_index": 500, "ledger_hash": "B" * 64,
                "ledger": {"ledger_index": 499, "ledger_hash": "B" * 64,
                            "parent_hash": "A" * 64, "close_time": 800000000},
            }], [], url),
        )
        with self.assertRaises(ProviderTransportError):
            adapter.fetch_ledger_header(500)

    def test_xrpl_ledger_header_rejects_conflicting_outer_and_nested_ledger_hash(self):
        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/redacted-key",
            transport_factory=lambda url, timeout: FakeTransport([{
                "validated": True, "ledger_index": 500, "ledger_hash": "B" * 64,
                "ledger": {"ledger_index": 500, "ledger_hash": "C" * 64,
                            "parent_hash": "A" * 64, "close_time": 800000000},
            }], [], url),
        )
        with self.assertRaises(ProviderTransportError):
            adapter.fetch_ledger_header(500)

    def test_xrpl_ledger_header_rejects_missing_parent_hash(self):
        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/redacted-key",
            transport_factory=lambda url, timeout: FakeTransport([{
                "validated": True, "ledger_index": 500, "ledger_hash": "B" * 64,
                "ledger": {"ledger_index": 500, "ledger_hash": "B" * 64,
                            "close_time": 800000000},
            }], [], url),
        )
        with self.assertRaises(ProviderTransportError):
            adapter.fetch_ledger_header(500)

    def test_xrpl_ledger_header_response_is_included_in_worker_receipt_lineage(self):
        endpoint = "https://xrpl-mainnet.core.chainstack.com/redacted-key"
        adapter = ChainstackXrplReadOnlyAdapter(
            endpoint,
            transport_factory=lambda url, timeout: FakeTransport([{
                "validated": True, "ledger_index": 500, "ledger_hash": "B" * 64,
                "ledger": {"ledger_index": 500, "ledger_hash": "B" * 64,
                           "parent_hash": "A" * 64, "close_time": 800000000},
            }], [], url),
        )

        @_capture_provider_run_receipts
        def worker_supporting_header_call():
            adapter.fetch_ledger_header(500)
            return drain_provider_run_receipts()

        batch = worker_supporting_header_call()
        self.assertEqual(len(batch.receipts), 1)
        receipt = batch.receipts[0]
        self.assertEqual(receipt.provider, "chainstack")
        self.assertEqual(receipt.network_id, "xrpl-mainnet")
        self.assertEqual(receipt.method, "ledger")
        self.assertEqual(receipt.endpoint_profile_sha256, _endpoint_profile_sha256(endpoint))

    def test_xrpl_ledger_header_rejects_missing_transport_attestation_in_worker_scope(self):
        class UnattestedTransport:
            last_response_attestation = None
            def call(self, method, params=None):
                return {
                    "validated": True, "ledger_index": 500, "ledger_hash": "B" * 64,
                    "ledger": {"ledger_index": 500, "ledger_hash": "B" * 64,
                           "parent_hash": "A" * 64, "close_time": 800000000},
                }

        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/redacted-key",
            transport_factory=lambda url, timeout: UnattestedTransport(),
        )
        @_capture_provider_run_receipts
        def worker_supporting_header_call():
            with self.assertRaises(ProviderTransportError) as error:
                adapter.fetch_ledger_header(500)
            self.assertEqual(error.exception.reason_code, "MISSING_RESPONSE_ATTESTATION")
        worker_supporting_header_call()

    def test_xrpl_account_tx_page_fails_closed_without_worker_response_attestation(self):
        class UnattestedTransport:
            last_response_attestation = None
            def call(self, method, params=None):
                return {
                    "validated": True, "account": "rLNaPoKeeBjZe2qs6x52yVPZpZ8td4dc6w",
                    "ledger_index_min": 100, "ledger_index_max": 200,
                    "transactions": [], "marker": None,
                }

        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/redacted-key",
            transport_factory=lambda url, timeout: UnattestedTransport(),
        )
        @_capture_provider_run_receipts
        def worker_page_call():
            with self.assertRaises(ProviderTransportError) as error:
                adapter.fetch_account_transactions(
                    "rLNaPoKeeBjZe2qs6x52yVPZpZ8td4dc6w", ledger_index_min=100, ledger_index_max=200,
                )
            self.assertEqual(error.exception.reason_code, "MISSING_RESPONSE_ATTESTATION")
        worker_page_call()

    def test_xrpl_ledger_header_rejects_unvalidated_or_wrong_ledger(self):
        for result in (
            {"validated": False, "ledger_index": 500, "ledger_hash": "B" * 64,
             "ledger": {"close_time": 800000000}},
            {"validated": True, "ledger_index": 501, "ledger_hash": "B" * 64,
             "ledger": {"close_time": 800000000}},
        ):
            adapter = ChainstackXrplReadOnlyAdapter(
                "https://xrpl-mainnet.core.chainstack.com/redacted-key",
                transport_factory=lambda endpoint, timeout, value=result: FakeTransport([value], [], endpoint),
            )
            with self.assertRaises(ProviderTransportError):
                adapter.fetch_ledger_header(500)

    def test_xrpl_rejects_unvalidated_transaction_pages(self):
        def factory(endpoint, timeout):
            return FakeTransport([{
                "account": "rLNaPoKeeBjZe2qs6x52yVPZpZ8td4dc6w", "validated": True,
                "transactions": [{"hash": "A" * 64, "validated": False,
                                  "ledger_index": 150, "tx_json": {}, "meta": {}}],
            }], [], endpoint)
        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/redacted-key", transport_factory=factory,
        )
        with self.assertRaises(ProviderTransportError) as error:
            adapter.fetch_account_transactions("rLNaPoKeeBjZe2qs6x52yVPZpZ8td4dc6w", ledger_index_min=100, ledger_index_max=200)
        self.assertEqual(error.exception.reason_code, "UNVALIDATED_XRPL_TRANSACTION")

    def test_alchemy_endpoint_profiles_are_exact_https_hosts_and_v2_paths(self):
        expected_hosts = {
            "bitcoin-mainnet": "bitcoin-mainnet.g.alchemy.com",
            "ethereum-mainnet": "eth-mainnet.g.alchemy.com",
            "solana-mainnet": "solana-mainnet.g.alchemy.com",
            "bnb-smart-chain-mainnet": "bnb-mainnet.g.alchemy.com",
        }
        self.assertEqual(set(ALCHEMY_ENDPOINTS), set(expected_hosts))
        for network_id, hostname in expected_hosts.items():
            with self.subTest(network_id=network_id):
                endpoint = _alchemy_endpoint(network_id, "test-key_123")
                self.assertEqual(endpoint, f"https://{hostname}/v2/test-key_123")
        for invalid_key in ("key/other", "key?query", "key#fragment", "key@host", "key with space"):
            with self.subTest(invalid_key=invalid_key):
                with self.assertRaises(ValueError):
                    _alchemy_endpoint("ethereum-mainnet", invalid_key)

    def test_endpoint_profile_fingerprint_uses_only_canonical_https_origin(self):
        first = _endpoint_profile_sha256("https://Provider.Example/v2/secret-one")
        second = _endpoint_profile_sha256("https://provider.example:443/v2/secret-two?query=private")
        self.assertEqual(first, second)
        self.assertNotEqual(first, _endpoint_profile_sha256("https://provider.example:8443/v2/secret-one"))
        with self.assertRaises(ValueError):
            _endpoint_profile_sha256("http://provider.example/path")

    def test_alchemy_adapter_rejects_attestation_for_a_different_endpoint_profile(self):
        class WrongProfileTransport(FakeTransport):
            def call(self, method, params=None):
                result = super().call(method, params)
                self.last_response_attestation["endpoint_profile_sha256"] = "f" * 64
                return result

        adapter = AlchemyReadOnlyAdapter(
            "test-key",
            transport_factory=lambda endpoint, timeout: WrongProfileTransport(["0x1"], [], endpoint),
        )
        @_capture_provider_run_receipts
        def call():
            with self.assertRaises(ProviderTransportError) as error:
                adapter._call("ethereum-mainnet", "eth_chainId")
            self.assertEqual(error.exception.reason_code, "ENDPOINT_PROFILE_MISMATCH")
        call()

    def test_alchemy_worker_rpc_fails_closed_without_response_attestation(self):
        class UnattestedTransport:
            last_response_attestation = None
            def call(self, method, params=None):
                return "0x1"

        adapter = AlchemyReadOnlyAdapter(
            "test-key", transport_factory=lambda endpoint, timeout: UnattestedTransport(),
        )
        @_capture_provider_run_receipts
        def worker_supporting_call():
            with self.assertRaises(ProviderTransportError) as error:
                adapter._call("ethereum-mainnet", "eth_chainId")
            self.assertEqual(error.exception.reason_code, "MISSING_RESPONSE_ATTESTATION")
        worker_supporting_call()

    def test_legacy_provider_receipt_without_endpoint_fingerprint_remains_readable(self):
        from layer1.onchain_providers import ProviderResponseReceipt
        legacy = ProviderResponseReceipt(**{
            "sequence": 1, "provider": "alchemy", "network_id": "ethereum-mainnet",
            "method": "eth_chainId", "request_sha256": "a" * 64,
            "response_sha256": "b" * 64, "response_bytes": 32, "http_status": 200,
            "received_at": "2026-11-26T00:00:00+00:00",
        })
        self.assertIsNone(legacy.endpoint_profile_sha256)

    def test_default_provider_opener_disables_all_environment_proxies(self):
        with patch("layer1.onchain_providers.build_opener") as build_opener:
            build_opener.return_value.open.return_value = object()
            _open_without_redirect(object(), timeout=3)
        handlers = build_opener.call_args.args
        proxy_handlers = [item for item in handlers if isinstance(item, ProxyHandler)]
        self.assertEqual(len(proxy_handlers), 1)
        self.assertEqual(proxy_handlers[0].proxies, {})

    def test_default_provider_opener_enforces_tls_certificate_and_hostname_verification(self):
        with patch("layer1.onchain_providers.build_opener") as build_opener:
            build_opener.return_value.open.return_value = object()
            _open_without_redirect(object(), timeout=3)
        handlers = build_opener.call_args.args
        https_handlers = [item for item in handlers if isinstance(item, HTTPSHandler)]
        self.assertEqual(len(https_handlers), 1)
        context = https_handlers[0]._context
        self.assertIsNotNone(context)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_provider_tls_accepts_trusted_chain_and_matching_ip_san(self):
        ca_file = str(_TLS_FIXTURES / "ca.pem")
        with patch.dict(os.environ, {"SSL_CERT_FILE": ca_file, "SSL_CERT_DIR": ""}):
            with _local_tls_server("trusted-ip") as url:
                with _open_without_redirect(Request(url), timeout=3) as response:
                    self.assertEqual(response.read(), b"tls-test-ok")

    def test_provider_tls_rejects_untrusted_certificate_chain(self):
        ca_file = str(_TLS_FIXTURES / "ca.pem")
        with patch.dict(os.environ, {"SSL_CERT_FILE": ca_file, "SSL_CERT_DIR": ""}):
            with _local_tls_server("untrusted-ip") as url:
                with self.assertRaises(URLError) as error:
                    _open_without_redirect(Request(url), timeout=3)
        self.assertIn("CERTIFICATE_VERIFY_FAILED", str(error.exception.reason))

    def test_provider_tls_rejects_hostname_mismatch_even_with_trusted_chain(self):
        ca_file = str(_TLS_FIXTURES / "ca.pem")
        with patch.dict(os.environ, {"SSL_CERT_FILE": ca_file, "SSL_CERT_DIR": ""}):
            with _local_tls_server("trusted-wrong-host") as url:
                with self.assertRaises(URLError) as error:
                    _open_without_redirect(Request(url), timeout=3)
        self.assertIn("IP address mismatch", str(error.exception.reason))

    def test_chainstack_rejects_unapproved_endpoint_authorities_and_paths(self):
        for endpoint in (
            "https://xrpl-mainnet.core.chainstack.com:444/key",
            "https://xrpl-mainnet.core.chainstack.com/key?redirect=https://attacker.example",
            "https://xrpl-mainnet.core.chainstack.com/key#fragment",
            "https://user@xrpl-mainnet.core.chainstack.com/key",
            "https://xrpl-mainnet.core.chainstack.com/key/extra",
            "https://xrpl-mainnet.core.chainstack.com/../key",
            "https://sub.xrpl-mainnet.core.chainstack.com/key",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    ChainstackXrplReadOnlyAdapter(endpoint)

    def test_chainstack_accepts_only_approved_https_origin_and_single_token_path(self):
        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/redacted-key",
            transport_factory=lambda endpoint, timeout: FakeTransport([], [], endpoint),
        )
        self.assertEqual(
            adapter._endpoint,
            "https://xrpl-mainnet.core.chainstack.com/redacted-key",
        )

    def test_chainstack_rejects_non_mainnet_or_non_https_endpoint(self):
        with self.assertRaisesRegex(ValueError, "mainnet endpoint"):
            ChainstackXrplReadOnlyAdapter("https://xrpl-testnet.core.chainstack.com/key")
        with self.assertRaisesRegex(ValueError, "mainnet endpoint"):
            ChainstackXrplReadOnlyAdapter("http://xrpl-mainnet.core.chainstack.com/key")


    def test_transport_requires_an_explicit_positive_response_byte_limit(self):
        with self.assertRaisesRegex(ValueError, "max_response_bytes"):
            ReadOnlyJsonRpcTransport("https://provider.example/v2/key")
        with self.assertRaisesRegex(ValueError, "max_response_bytes"):
            ReadOnlyJsonRpcTransport("https://provider.example/v2/key", max_response_bytes=0)
        with self.assertRaisesRegex(ValueError, "max_response_bytes"):
            ReadOnlyJsonRpcTransport("https://provider.example/v2/key", max_response_bytes=True)

    def test_transport_rejects_content_length_over_limit_before_reading(self):
        response = FakeHttpResponse(
            b'{"ok":true}', headers={"Content-Length": "11"},
        )
        transport = ReadOnlyJsonRpcTransport(
            "https://provider.example/v2/key", max_response_bytes=10,
            opener=lambda request, timeout: response,
        )
        with self.assertRaises(ProviderTransportError) as error:
            transport.get_json("api/v1/status")
        self.assertEqual(error.exception.reason_code, "RESPONSE_TOO_LARGE")
        self.assertEqual(response.read_calls, [])

    def test_transport_enforces_streamed_byte_limit_without_content_length(self):
        response = FakeHttpResponse(b'{"ok":true}')
        transport = ReadOnlyJsonRpcTransport(
            "https://provider.example/v2/key", max_response_bytes=8,
            opener=lambda request, timeout: response,
        )
        with self.assertRaises(ProviderTransportError) as error:
            transport.get_json("api/v1/status")
        self.assertEqual(error.exception.reason_code, "RESPONSE_TOO_LARGE")
        self.assertTrue(all(size > 0 for size in response.read_calls))
        self.assertLessEqual(sum(response.read_calls), 9)

    def test_transport_accepts_response_exactly_at_byte_limit(self):
        payload = b'{"ok":1}'
        response = FakeHttpResponse(payload, headers={"Content-Length": str(len(payload))})
        transport = ReadOnlyJsonRpcTransport(
            "https://provider.example/v2/key", max_response_bytes=len(payload),
            opener=lambda request, timeout: response,
        )
        self.assertEqual(transport.get_json("api/v1/status"), {"ok": 1})

    def test_provider_adapters_require_explicit_response_limit_for_default_transport(self):
        with self.assertRaisesRegex(ValueError, "max_response_bytes"):
            AlchemyReadOnlyAdapter("test-key")
        with self.assertRaisesRegex(ValueError, "max_response_bytes"):
            ChainstackXrplReadOnlyAdapter(
                "https://xrpl-mainnet.core.chainstack.com/key",
            )

    def test_provider_from_env_requires_explicit_response_limit(self):
        with self.assertRaisesRegex(ValueError, "ONCHAIN_MAX_PROVIDER_RESPONSE_BYTES"):
            AlchemyReadOnlyAdapter.from_env({"ALCHEMY_API_KEY": "test-key"})
        with self.assertRaisesRegex(ValueError, "ONCHAIN_MAX_PROVIDER_RESPONSE_BYTES"):
            ChainstackXrplReadOnlyAdapter.from_env({
                "CHAINSTACK_XRPL_ENDPOINT": "https://xrpl-mainnet.core.chainstack.com/key",
            })

    def test_provider_from_env_uses_explicit_response_limit_for_default_transport(self):
        alchemy = AlchemyReadOnlyAdapter.from_env({
            "ALCHEMY_API_KEY": "test-key",
            "ONCHAIN_MAX_PROVIDER_RESPONSE_BYTES": "8192",
        })
        alchemy_transport = alchemy._transport_factory("https://provider.example/key", 10)
        self.assertEqual(alchemy_transport._max_response_bytes, 8192)

        xrpl = ChainstackXrplReadOnlyAdapter.from_env({
            "CHAINSTACK_XRPL_ENDPOINT": "https://xrpl-mainnet.core.chainstack.com/key",
            "ONCHAIN_MAX_PROVIDER_RESPONSE_BYTES": "4096",
        })
        xrpl_transport = xrpl._transport_factory("https://xrpl-mainnet.core.chainstack.com/key", 10)
        self.assertEqual(xrpl_transport._max_response_bytes, 4096)

    def test_provider_from_env_rejects_non_positive_or_non_integer_response_limits(self):
        for value in ("0", "-1", "1.5", "1e6", ""):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "ONCHAIN_MAX_PROVIDER_RESPONSE_BYTES"):
                    AlchemyReadOnlyAdapter.from_env({
                        "ALCHEMY_API_KEY": "test-key",
                        "ONCHAIN_MAX_PROVIDER_RESPONSE_BYTES": value,
                    })

    def test_transport_bounds_json_rpc_response_and_rejects_malformed_content_length(self):
        oversized = FakeHttpResponse(b'{"jsonrpc":"2.0","id":1,"result":"0x1"}')
        transport = ReadOnlyJsonRpcTransport(
            "https://provider.example/key", max_response_bytes=8,
            opener=lambda request, timeout: oversized,
        )
        with self.assertRaises(ProviderTransportError) as error:
            transport.call("eth_chainId")
        self.assertEqual(error.exception.reason_code, "RESPONSE_TOO_LARGE")

        malformed = FakeHttpResponse(b'{"ok":true}', headers={"Content-Length": "unknown"})
        transport = ReadOnlyJsonRpcTransport(
            "https://provider.example/key", max_response_bytes=64,
            opener=lambda request, timeout: malformed,
        )
        with self.assertRaises(ProviderTransportError) as error:
            transport.get_json("api/v1/status")
        self.assertEqual(error.exception.reason_code, "INVALID_CONTENT_LENGTH")
        self.assertEqual(malformed.read_calls, [])

    def test_json_rpc_transport_exposes_non_secret_request_and_exact_response_digests(self):
        raw = b'{"jsonrpc":"2.0","id":1,"result":"0x1"}'
        response = FakeHttpResponse(raw, headers={"Content-Length": str(len(raw))})
        transport = ReadOnlyJsonRpcTransport(
            "https://provider.example/v2/credential-must-not-leak",
            opener=lambda request, timeout: response, max_response_bytes=1024,
        )
        self.assertEqual(transport.call("eth_chainId"), "0x1")
        attestation = transport.last_response_attestation
        self.assertEqual(attestation["response_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(attestation["response_bytes"], len(raw))
        self.assertEqual(attestation["http_status"], 200)
        self.assertRegex(attestation["request_sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(
            attestation["endpoint_profile_sha256"],
            hashlib.sha256(b"https://provider.example:443").hexdigest(),
        )
        self.assertNotIn("credential-must-not-leak", repr(attestation))
        self.assertNotIn("provider.example", repr(attestation))

    def test_failed_transport_call_clears_previous_response_metadata(self):
        responses = [
            FakeHttpResponse(b'{"jsonrpc":"2.0","id":1,"result":"0x1"}'),
            HTTPError("https://provider.example/key", 503, "unavailable", None, None),
        ]
        transport = ReadOnlyJsonRpcTransport(
            "https://provider.example/key", max_response_bytes=1024,
            opener=lambda request, timeout: responses.pop(0),
        )
        self.assertEqual(transport.call("eth_chainId"), "0x1")
        self.assertIsNotNone(transport.last_response_attestation)
        with self.assertRaises(ProviderTransportError):
            transport.call("eth_chainId")
        self.assertIsNone(transport.last_response_attestation)


    def test_bitcoin_address_page_rejects_more_records_than_requested_page_size(self):
        class FakeRestTransport(FakeTransport):
            def get_json(self, path, query=None):
                return {"address": "1BoatSLRHtKNngkdXEeobR76b53LETtpyT", "page": 1, "totalPages": 1,
                        "txs": [{"txid": "a" * 64, "confirmations": 0},
                                {"txid": "b" * 64, "confirmations": 0}]}
        adapter = AlchemyReadOnlyAdapter(
            "test-key", transport_factory=lambda endpoint, timeout: FakeRestTransport([], []),
        )
        with self.assertRaises(ProviderTransportError) as error:
            adapter.fetch_bitcoin_address_transactions("1BoatSLRHtKNngkdXEeobR76b53LETtpyT", page_size=1)
        self.assertEqual(error.exception.reason_code, "PAGE_LIMIT_EXCEEDED")

    def test_ethereum_transfer_page_rejects_more_records_than_requested_max_count(self):
        transfer = {
            "blockNum": "0x64", "hash": "0x" + "a" * 64,
            "from": "0x" + "1" * 40, "to": "0x" + "2" * 40,
            "category": "erc20",
            "rawContract": {"value": "0x1", "address": "0x" + "3" * 40, "decimal": "0x0"},
        }
        adapter, _ = self.adapter([
            "0x1", {"number": "0xc8", "hash": "0x" + "c" * 64},
            {"transfers": [transfer, dict(transfer, hash="0x" + "b" * 64)]},
        ])
        with self.assertRaises(ProviderTransportError) as error:
            adapter.fetch_ethereum_asset_transfers(
                contract_addresses=["0x" + "3" * 40], from_block=100, to_block=200,
                max_count=1,
            )
        self.assertEqual(error.exception.reason_code, "PAGE_LIMIT_EXCEEDED")

    def test_solana_transaction_page_rejects_more_records_than_requested_limit(self):
        address = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
        transaction = {
            "signature": "3jUKrQp1UGq5ih6FTDUUt2kkqUfoG2o4kY5T1DoVHK2tXXDLdxJSXzuJGY4JPoRivgbi45U2bc7LZfMa6C4R3szX",
            "slot": 300, "transactionIndex": 1,
            "transaction": {"signatures": ["3jUKrQp1UGq5ih6FTDUUt2kkqUfoG2o4kY5T1DoVHK2tXXDLdxJSXzuJGY4JPoRivgbi45U2bc7LZfMa6C4R3szX"]},
            "meta": {},
        }
        adapter, _ = self.adapter([
            SOLANA_MAINNET_GENESIS_HASH,
            {"transactions": [transaction, dict(transaction, transactionIndex=2)]},
        ])
        with self.assertRaises(ProviderTransportError) as error:
            adapter.fetch_solana_address_transactions(address, limit=1)
        self.assertEqual(error.exception.reason_code, "PAGE_LIMIT_EXCEEDED")

    def test_xrpl_transaction_page_rejects_more_records_than_requested_limit(self):
        account = "rLNaPoKeeBjZe2qs6x52yVPZpZ8td4dc6w"
        transaction = {
            "hash": "A" * 64, "validated": True, "ledger_index": 150,
            "tx_json": {}, "meta": {},
        }
        adapter = ChainstackXrplReadOnlyAdapter(
            "https://xrpl-mainnet.core.chainstack.com/test-key",
            transport_factory=lambda endpoint, timeout: FakeTransport([{
                "account": account, "validated": True,
                "transactions": [transaction, dict(transaction, hash="B" * 64)],
                "ledger_index_min": 100, "ledger_index_max": 200,
            }], []),
        )
        with self.assertRaises(ProviderTransportError) as error:
            adapter.fetch_account_transactions(account, 100, 200, limit=1)
        self.assertEqual(error.exception.reason_code, "PAGE_LIMIT_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
