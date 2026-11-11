import json
import unittest
from urllib.error import HTTPError

from layer1.onchain_providers import (
    AlchemyReadOnlyAdapter,
    ChainstackXrplReadOnlyAdapter,
    ProviderTransportError,
    ReadOnlyJsonRpcTransport,
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

    def test_transport_rejects_mismatched_json_rpc_response_id(self):
        def opener(request, timeout):
            return FakeHttpResponse(b'{"jsonrpc":"2.0","id":99,"result":"0x1"}')
        transport = ReadOnlyJsonRpcTransport("https://example.invalid/key", opener=opener)
        with self.assertRaises(ProviderTransportError) as error:
            transport.call("eth_chainId")
        self.assertEqual(error.exception.reason_code, "INVALID_RPC_ENVELOPE")

    def test_chainstack_rejects_non_mainnet_or_non_https_endpoint(self):
        with self.assertRaisesRegex(ValueError, "mainnet endpoint"):
            ChainstackXrplReadOnlyAdapter("https://xrpl-testnet.core.chainstack.com/key")
        with self.assertRaisesRegex(ValueError, "mainnet endpoint"):
            ChainstackXrplReadOnlyAdapter("http://xrpl-mainnet.core.chainstack.com/key")


if __name__ == "__main__":
    unittest.main()
