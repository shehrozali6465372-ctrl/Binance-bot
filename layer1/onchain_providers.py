"""Read-only, bounded provider probes for the five Module 9 mainnets.

These adapters deliberately expose chain heads/health only. They do not submit
transactions, infer whale intent, or fabricate transaction-level observations.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from typing import Callable, Optional


ALCHEMY_ENDPOINTS = {
    "bitcoin-mainnet": "https://bitcoin-mainnet.g.alchemy.com/v2/{api_key}",
    "ethereum-mainnet": "https://eth-mainnet.g.alchemy.com/v2/{api_key}",
    "solana-mainnet": "https://solana-mainnet.g.alchemy.com/v2/{api_key}",
    "bnb-smart-chain-mainnet": "https://bnb-mainnet.g.alchemy.com/v2/{api_key}",
}
SOLANA_MAINNET_GENESIS_HASH = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"


class ProviderTransportError(RuntimeError):
    def __init__(self, reason_code: str, message: str, http_status: Optional[int] = None):
        super().__init__(message)
        self.reason_code = reason_code
        self.http_status = http_status


class ReadOnlyJsonRpcTransport:
    """Small JSON-RPC HTTP transport that never logs endpoint URLs or bodies."""

    def __init__(self, endpoint: str, timeout_seconds: int = 10,
                 request_style: str = "jsonrpc2", opener: Callable = urlopen):
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("provider endpoint must be an HTTPS URL")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive integer")
        if request_style not in {"jsonrpc2", "xrpl"}:
            raise ValueError("unsupported JSON-RPC request style")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive integer")
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._request_style = request_style
        self._opener = opener
        self._request_id = 0

    def call(self, method: str, params: Optional[list] = None) -> Any:
        if not isinstance(method, str) or not method or not method.replace("_", "").isalnum():
            raise ValueError("RPC method name is invalid")
        self._request_id += 1
        request_id = self._request_id
        if self._request_style == "xrpl":
            payload = {"method": method, "params": params if params is not None else [{}], "id": request_id}
        else:
            payload = {"jsonrpc": "2.0", "id": request_id, "method": method,
                       "params": params if params is not None else []}
        request = Request(
            self._endpoint,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            status = int(exc.code)
            reason = "RATE_LIMITED" if status == 429 else "HTTP_ERROR"
            raise ProviderTransportError(reason, f"provider returned HTTP {status}", status) from None
        except URLError:
            raise ProviderTransportError("NETWORK_ERROR", "provider network request failed") from None
        except TimeoutError:
            raise ProviderTransportError("TIMEOUT", "provider request timed out") from None
        except OSError:
            raise ProviderTransportError("NETWORK_ERROR", "provider network request failed") from None
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProviderTransportError("INVALID_JSON", "provider returned invalid JSON") from None
        if (not isinstance(decoded, dict) or type(decoded.get("id")) is not int
                or decoded.get("id") != request_id
                or (self._request_style == "jsonrpc2" and decoded.get("jsonrpc") != "2.0")):
            raise ProviderTransportError("INVALID_RPC_ENVELOPE", "provider response ID/envelope is invalid")
        if decoded.get("error") is not None:
            error = decoded.get("error")
            code = error.get("code") if isinstance(error, dict) else None
            raise ProviderTransportError("RPC_ERROR", f"provider RPC method failed (code={code})")
        if self._request_style == "xrpl" and decoded.get("status") not in {None, "success"}:
            raise ProviderTransportError("RPC_ERROR", "XRPL provider reported an unsuccessful response")
        if "result" not in decoded:
            raise ProviderTransportError("INVALID_RPC_ENVELOPE", "provider response has no result")
        return decoded["result"]


@dataclass(frozen=True)
class ProviderHealthResult:
    provider: str
    network_id: str
    status: str
    observed_at: str
    head_height: Optional[int] = None
    block_hash: Optional[str] = None
    block_time: Optional[str] = None
    head_age_seconds: Optional[int] = None
    history_range: Optional[str] = None
    finality: str = "UNVERIFIED"
    finality_reference: str = ""
    reason_code: str = ""


class AlchemyReadOnlyAdapter:
    """Read-only chain-head probes for BTC, ETH, SOL and BNB Smart Chain."""

    _READ_METHODS = {
        "bitcoin-mainnet": frozenset({"getblockcount", "getblockhash", "getblockheader"}),
        "ethereum-mainnet": frozenset({"eth_chainId", "eth_getBlockByNumber"}),
        "solana-mainnet": frozenset({"getGenesisHash", "getSlot"}),
        "bnb-smart-chain-mainnet": frozenset({"eth_chainId", "eth_getFinalizedHeader"}),
    }

    def __init__(self, api_key: str, timeout_seconds: int = 10,
                 transport_factory: Optional[Callable[[str, int], ReadOnlyJsonRpcTransport]] = None):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("Alchemy API key is required")
        if any(char in api_key for char in "/?#"):
            raise ValueError("Alchemy API key contains invalid URL characters")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive integer")
        self._api_key = api_key.strip()
        self._timeout_seconds = timeout_seconds
        self._transport_factory = transport_factory or (
            lambda endpoint, timeout: ReadOnlyJsonRpcTransport(endpoint, timeout)
        )

    @classmethod
    def from_env(cls, environ=os.environ):
        api_key = environ.get("ALCHEMY_API_KEY", "")
        if not api_key:
            raise ValueError("ALCHEMY_API_KEY is not configured")
        return cls(api_key)

    def _call(self, network_id: str, method: str, params: Optional[list] = None):
        allowed = self._READ_METHODS.get(network_id)
        if allowed is None:
            raise ValueError("network is not supported by the Alchemy adapter")
        if method not in allowed:
            raise ValueError("RPC method is not allowed by the read-only Alchemy adapter")
        endpoint = ALCHEMY_ENDPOINTS[network_id].format(api_key=self._api_key)
        return self._transport_factory(endpoint, self._timeout_seconds).call(method, params)

    @staticmethod
    def _hex_int(value: Any, field: str) -> int:
        if not isinstance(value, str) or not value.startswith("0x"):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", f"provider {field} is not a hex quantity")
        try:
            number = int(value, 16)
        except ValueError:
            raise ProviderTransportError("INVALID_PROVIDER_DATA", f"provider {field} is invalid") from None
        if number < 0:
            raise ProviderTransportError("INVALID_PROVIDER_DATA", f"provider {field} is negative")
        return number

    def probe(self, network_id: str) -> ProviderHealthResult:
        observed_at = datetime.now(timezone.utc).isoformat()
        if network_id == "bitcoin-mainnet":
            height = self._call(network_id, "getblockcount")
            if isinstance(height, bool) or not isinstance(height, int) or height <= 0:
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Bitcoin block height is invalid")
            block_hash = self._call(network_id, "getblockhash", [height])
            header = self._call(network_id, "getblockheader", [block_hash, True])
            if not isinstance(header, dict) or header.get("height") != height or header.get("hash") != block_hash:
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Bitcoin block header does not match requested tip")
            confirmations = header.get("confirmations")
            if isinstance(confirmations, bool) or not isinstance(confirmations, int) or confirmations < 0:
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Bitcoin confirmation count is invalid")
            block_time = header.get("time")
            if isinstance(block_time, bool) or not isinstance(block_time, int) or block_time <= 0:
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Bitcoin block time is invalid")
            return ProviderHealthResult(
                "alchemy", network_id, "AVAILABLE", observed_at, height, block_hash,
                datetime.fromtimestamp(block_time, timezone.utc).isoformat(),
                finality="CONFIRMED" if confirmations > 0 else "UNVERIFIED",
                finality_reference=f"confirmations={confirmations}",
                reason_code="BITCOIN_CHAIN_TIP_READ_ONLY",
            )
        if network_id in {"ethereum-mainnet", "bnb-smart-chain-mainnet"}:
            expected_chain_id = "0x1" if network_id == "ethereum-mainnet" else "0x38"
            actual_chain_id = self._call(network_id, "eth_chainId")
            if not isinstance(actual_chain_id, str) or actual_chain_id.lower() != expected_chain_id:
                raise ProviderTransportError("NETWORK_ID_MISMATCH", "Alchemy endpoint returned the wrong EVM chain ID")
            if network_id == "ethereum-mainnet":
                block = self._call(network_id, "eth_getBlockByNumber", ["finalized", False])
                finality_reference = "eth_getBlockByNumber:finalized"
            else:
                block = self._call(network_id, "eth_getFinalizedHeader", [-3])
                finality_reference = "eth_getFinalizedHeader:verifiedValidatorNum=-3"
            if not isinstance(block, dict) or not isinstance(block.get("hash"), str):
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "finalized EVM block response is invalid")
            height = self._hex_int(block.get("number"), "block number")
            block_timestamp = self._hex_int(block.get("timestamp"), "block timestamp")
            return ProviderHealthResult(
                "alchemy", network_id, "AVAILABLE", observed_at, height, block["hash"],
                datetime.fromtimestamp(block_timestamp, timezone.utc).isoformat(),
                finality="FINALIZED", finality_reference=finality_reference,
                reason_code="EVM_FINALIZED_HEAD_READ_ONLY",
            )
        if network_id == "solana-mainnet":
            genesis_hash = self._call(network_id, "getGenesisHash")
            if genesis_hash != SOLANA_MAINNET_GENESIS_HASH:
                raise ProviderTransportError("NETWORK_ID_MISMATCH", "Alchemy endpoint returned the wrong Solana genesis hash")
            slot = self._call(network_id, "getSlot", [{"commitment": "finalized"}])
            if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Solana finalized slot is invalid")
            return ProviderHealthResult(
                "alchemy", network_id, "AVAILABLE", observed_at, slot,
                finality="FINALIZED", finality_reference="commitment=finalized",
                reason_code="SOLANA_FINALIZED_SLOT_READ_ONLY",
            )
        raise ValueError("network is not supported by the Alchemy adapter")


class ChainstackXrplReadOnlyAdapter:
    """Read-only XRPL mainnet health probe through a Chainstack Global Node."""

    def __init__(self, endpoint: str, timeout_seconds: int = 10,
                 transport_factory: Optional[Callable[[str, int], ReadOnlyJsonRpcTransport]] = None):
        parsed = urlparse(endpoint)
        if (parsed.scheme != "https" or parsed.hostname != "xrpl-mainnet.core.chainstack.com"
                or not parsed.path.strip("/")):
            raise ValueError("Chainstack XRPL endpoint must be the configured HTTPS mainnet endpoint")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive integer")
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._transport_factory = transport_factory or (
            lambda url, timeout: ReadOnlyJsonRpcTransport(url, timeout, request_style="xrpl")
        )

    @classmethod
    def from_env(cls, environ=os.environ):
        endpoint = environ.get("CHAINSTACK_XRPL_ENDPOINT", "")
        if not endpoint:
            raise ValueError("CHAINSTACK_XRPL_ENDPOINT is not configured")
        return cls(endpoint)

    def probe(self) -> ProviderHealthResult:
        transport = self._transport_factory(self._endpoint, self._timeout_seconds)
        response = transport.call("server_info", [{}])
        info = response.get("info") if isinstance(response, dict) else None
        ledger = info.get("validated_ledger") if isinstance(info, dict) else None
        if not isinstance(ledger, dict):
            raise ProviderTransportError("XRPL_VALIDATED_LEDGER_UNAVAILABLE", "Chainstack did not return a validated XRPL ledger")
        height, block_hash, age = ledger.get("seq"), ledger.get("hash"), ledger.get("age")
        history_range = info.get("complete_ledgers")
        if not isinstance(history_range, str) or not history_range.strip() or history_range == "empty":
            raise ProviderTransportError("XRPL_HISTORY_WINDOW_UNAVAILABLE", "Chainstack did not report an available XRPL ledger-history window")
        if (isinstance(height, bool) or not isinstance(height, int) or height <= 0
                or not isinstance(block_hash, str) or not block_hash
                or isinstance(age, bool) or not isinstance(age, (int, float)) or age < 0):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Chainstack validated-ledger metadata is invalid")
        return ProviderHealthResult(
            "chainstack", "xrpl-mainnet", "AVAILABLE", datetime.now(timezone.utc).isoformat(),
            height, block_hash, head_age_seconds=int(age), history_range=history_range,
            finality="FINALIZED", finality_reference="validated_ledger=true",
            reason_code="XRPL_VALIDATED_LEDGER_READ_ONLY",
        )
