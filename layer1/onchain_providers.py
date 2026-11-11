"""Read-only, bounded provider probes for the five Module 9 mainnets.

These adapters deliberately expose chain heads/health only. They do not submit
transactions, infer whale intent, or fabricate transaction-level observations.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen
from typing import Any, Callable, Optional


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
        if request_style not in {"jsonrpc2", "xrpl"}:
            raise ValueError("unsupported JSON-RPC request style")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive integer")
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._request_style = request_style
        self._opener = opener
        self._request_id = 0

    def get_json(self, path: str, query: Optional[dict] = None) -> dict:
        if (not isinstance(path, str) or not path or path.startswith("/")
                or any(part in {".", ".."} for part in path.split("/"))):
            raise ValueError("REST path must be a safe relative path")
        query = query or {}
        if not isinstance(query, dict) or any(
            not isinstance(key, str) or not isinstance(value, (str, int)) or isinstance(value, bool)
            for key, value in query.items()
        ):
            raise ValueError("REST query parameters must be string/integer values")
        url = self._endpoint.rstrip("/") + "/" + path
        if query:
            url += "?" + urlencode(query)
        request = Request(url, headers={"Accept": "application/json"}, method="GET")
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
        if not isinstance(decoded, dict):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "provider REST response must be a JSON object")
        return decoded

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


@dataclass(frozen=True)
class ProviderDataPage:
    provider: str
    network_id: str
    scope: str
    records: tuple
    next_cursor: Any = None
    page_number: Optional[int] = None
    total_pages: Optional[int] = None
    from_block: Optional[int] = None
    to_block: Optional[int] = None
    finalized_height: Optional[int] = None
    finality_reference: str = ""

    @property
    def complete(self) -> bool:
        return self.next_cursor is None


@dataclass(frozen=True)
class BitcoinAddressTransaction:
    txid: str
    confirmations: int
    block_height: Optional[int]
    block_hash: Optional[str]
    block_time: Optional[int]
    finality: str
    raw: dict


@dataclass(frozen=True)
class SolanaAddressTransaction:
    signature: str
    slot: int
    block_time: Optional[int]
    raw: dict


@dataclass(frozen=True)
class XrplAccountTransaction:
    transaction_hash: str
    ledger_index: int
    close_time_iso: Optional[str]
    transaction: dict
    metadata: dict
    raw: dict


@dataclass(frozen=True)
class EthereumAssetTransfer:
    block_number: int
    transaction_hash: str
    from_address: str
    to_address: str
    category: str
    amount_raw: str
    decimals: int
    contract_address: Optional[str]
    asset_label: Optional[str]
    block_timestamp: Optional[str]
    raw: dict


@dataclass(frozen=True)
class EvmTokenTransferLog:
    network_id: str
    contract_address: str
    from_address: str
    to_address: str
    amount_raw: str
    block_number: int
    block_hash: str
    transaction_hash: str
    log_index: int
    removed: bool


TRANSFER_EVENT_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def _is_evm_address(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]{40}", value) is not None


def _is_base58_pubkey(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", value) is not None


def _is_base58_signature(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{64,90}", value) is not None


def _parse_hex_quantity(value: Any, field: str) -> int:
    if not isinstance(value, str) or re.fullmatch(r"0x[0-9a-fA-F]+", value) is None:
        raise ProviderTransportError("INVALID_PROVIDER_DATA", f"provider {field} is not a valid hex quantity")
    return int(value, 16)


class AlchemyReadOnlyAdapter:
    """Read-only chain-head probes for BTC, ETH, SOL and BNB Smart Chain."""

    _READ_METHODS = {
        "bitcoin-mainnet": frozenset({"getblockcount", "getblockhash", "getblockheader"}),
        "ethereum-mainnet": frozenset({"eth_chainId", "eth_getBlockByNumber", "alchemy_getAssetTransfers", "eth_getLogs"}),
        "solana-mainnet": frozenset({"getGenesisHash", "getSlot", "getTransactionsForAddress"}),
        "bnb-smart-chain-mainnet": frozenset({"eth_chainId", "eth_getFinalizedHeader", "eth_getLogs", "eth_getBlockByNumber"}),
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

    def fetch_bitcoin_transaction(self, txid: str) -> dict:
        """Fetch full UTXO input/output details for one exact transaction ID."""
        if not isinstance(txid, str) or re.fullmatch(r"[0-9a-fA-F]{64}", txid) is None:
            raise ValueError("Bitcoin transaction ID must be exactly 32-byte hex")
        endpoint = ALCHEMY_ENDPOINTS["bitcoin-mainnet"].format(api_key=self._api_key)
        transport = self._transport_factory(endpoint, self._timeout_seconds)
        result = transport.get_json(
            f"api/v2/tx/{quote(txid, safe='')}", {"spending": "false"},
        )
        returned_txid = result.get("txid") if isinstance(result, dict) else None
        if (not isinstance(returned_txid, str)
                or re.fullmatch(r"[0-9a-fA-F]{64}", returned_txid) is None
                or returned_txid.lower() != txid.lower()):
            raise ProviderTransportError("TRANSACTION_ID_MISMATCH", "Bitcoin transaction details do not match the requested txid")
        if (not isinstance(result.get("vin"), list)
                or any(not isinstance(item, dict) for item in result["vin"])
                or not isinstance(result.get("vout"), list)
                or any(not isinstance(item, dict) for item in result["vout"])):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Bitcoin transaction details require vin and vout arrays")
        return result

    def fetch_bitcoin_address_transactions(self, address: str, page: int = 1,
                                           page_size: int = 1000,
                                           from_height: Optional[int] = None,
                                           to_height: Optional[int] = None) -> ProviderDataPage:
        if not isinstance(address, str) or not address.strip() or any(ch.isspace() for ch in address):
            raise ValueError("Bitcoin address must be a non-empty address string")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("Bitcoin page must be a positive integer")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 1000:
            raise ValueError("Bitcoin page_size must be between 1 and 1000")
        if from_height is not None and (isinstance(from_height, bool) or not isinstance(from_height, int) or from_height < 0):
            raise ValueError("from_height must be a non-negative integer")
        if to_height is not None and (isinstance(to_height, bool) or not isinstance(to_height, int) or to_height < 0):
            raise ValueError("to_height must be a non-negative integer")
        if from_height is not None and to_height is not None and from_height > to_height:
            raise ValueError("from_height must not exceed to_height")
        endpoint = ALCHEMY_ENDPOINTS["bitcoin-mainnet"].format(api_key=self._api_key)
        transport = self._transport_factory(endpoint, self._timeout_seconds)
        query = {"page": page, "pageSize": page_size, "details": "txs"}
        if from_height is not None:
            query["from"] = from_height
        if to_height is not None:
            query["to"] = to_height
        response = transport.get_json(
            f"api/v2/address/{quote(address, safe='')}", query,
        )
        if response.get("address") != address:
            raise ProviderTransportError("ADDRESS_SCOPE_MISMATCH", "Bitcoin provider returned a different address scope")
        returned_page, total_pages = response.get("page"), response.get("totalPages")
        raw_records = response.get("txs")
        if (isinstance(returned_page, bool) or not isinstance(returned_page, int) or returned_page != page
                or isinstance(total_pages, bool) or not isinstance(total_pages, int) or total_pages < 0
                or not isinstance(raw_records, list) or any(not isinstance(item, dict) for item in raw_records)):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Bitcoin address transaction page has an invalid shape")
        if returned_page > max(total_pages, 1):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Bitcoin provider page exceeds its reported page count")
        records = []
        for item in raw_records:
            txid = item.get("txid")
            confirmations = item.get("confirmations")
            if (not isinstance(txid, str) or re.fullmatch(r"[0-9a-fA-F]{64}", txid) is None
                    or isinstance(confirmations, bool) or not isinstance(confirmations, int)):
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Bitcoin address transaction identity/confirmation data is invalid")
            height, block_hash, block_time = item.get("blockHeight"), item.get("blockHash"), item.get("blockTime")
            if confirmations > 0:
                if (isinstance(height, bool) or not isinstance(height, int) or height <= 0
                        or not isinstance(block_hash, str) or re.fullmatch(r"[0-9a-fA-F]{64}", block_hash) is None
                        or isinstance(block_time, bool) or not isinstance(block_time, int) or block_time <= 0):
                    raise ProviderTransportError("INVALID_PROVIDER_DATA", "confirmed Bitcoin transaction lacks a valid block reference")
                finality = "CONFIRMED"
            elif confirmations == 0:
                height, block_hash, block_time, finality = None, None, None, "PENDING"
            else:
                finality = "ORPHANED"
            records.append(BitcoinAddressTransaction(txid, confirmations, height, block_hash, block_time, finality, item))
        cursor = page + 1 if page < total_pages else None
        return ProviderDataPage("alchemy", "bitcoin-mainnet", address, tuple(records),
                                cursor, returned_page, total_pages)

    def fetch_ethereum_asset_transfers(self, contract_addresses=None,
                                       from_block: Optional[int] = None,
                                       to_block: Optional[int] = None,
                                       from_address: Optional[str] = None,
                                       to_address: Optional[str] = None,
                                       categories=("erc20",), page_key: Optional[str] = None,
                                       max_count: int = 1000) -> ProviderDataPage:
        if (isinstance(from_block, bool) or not isinstance(from_block, int) or from_block < 0
                or isinstance(to_block, bool) or not isinstance(to_block, int) or to_block < from_block):
            raise ValueError("Ethereum transfer query requires a fixed non-negative block range")
        allowed_categories = {"external", "internal", "erc20"}
        categories = tuple(categories)
        if not categories or any(category not in allowed_categories for category in categories):
            raise ValueError("Ethereum transfer categories are invalid")
        contracts = tuple(contract_addresses or ())
        if any(not _is_evm_address(address) for address in contracts):
            raise ValueError("Ethereum contract addresses must be exact EVM addresses")
        if from_address is not None and not _is_evm_address(from_address):
            raise ValueError("from_address must be an exact EVM address")
        if to_address is not None and not _is_evm_address(to_address):
            raise ValueError("to_address must be an exact EVM address")
        if not contracts and from_address is None and to_address is None:
            raise ValueError("Ethereum transfer query must be scoped by a contract or monitored address")
        if any(category in {"external", "internal"} for category in categories) and from_address is None and to_address is None:
            raise ValueError("native/internal Ethereum transfer categories require a monitored from/to address")
        if any(category in {"erc20", "erc721", "erc1155"} for category in categories) and not contracts:
            raise ValueError("token transfer query requires exact contract_addresses")
        if isinstance(max_count, bool) or not isinstance(max_count, int) or not 1 <= max_count <= 1000:
            raise ValueError("max_count must be between 1 and 1000")
        if page_key is not None and (not isinstance(page_key, str) or not page_key.strip()):
            raise ValueError("page_key must be a non-empty opaque string")
        chain_id = self._call("ethereum-mainnet", "eth_chainId")
        if not isinstance(chain_id, str) or chain_id.lower() != "0x1":
            raise ProviderTransportError("NETWORK_ID_MISMATCH", "Alchemy endpoint returned the wrong Ethereum mainnet chain ID")
        finalized_block = self._call("ethereum-mainnet", "eth_getBlockByNumber", ["finalized", False])
        if not isinstance(finalized_block, dict) or not isinstance(finalized_block.get("hash"), str):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Ethereum finalized block response is invalid")
        finalized_height = self._hex_int(finalized_block.get("number"), "finalized block number")
        if to_block > finalized_height:
            raise ProviderTransportError("BLOCK_RANGE_NOT_FINALIZED", "Ethereum transfer query extends beyond the finalized block")
        params = {
            "fromBlock": hex(from_block), "toBlock": hex(to_block),
            "category": list(categories), "excludeZeroValue": True,
            "withMetadata": True, "maxCount": hex(max_count),
        }
        if contracts:
            params["contractAddresses"] = list(contracts)
        if from_address is not None:
            params["fromAddress"] = from_address
        if to_address is not None:
            params["toAddress"] = to_address
        if page_key is not None:
            params["pageKey"] = page_key
        result = self._call("ethereum-mainnet", "alchemy_getAssetTransfers", [params])
        if not isinstance(result, dict) or not isinstance(result.get("transfers"), list):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Alchemy Ethereum transfer page has an invalid shape")
        records = []
        for transfer in result["transfers"]:
            if (not isinstance(transfer, dict)
                    or not isinstance(transfer.get("hash"), str)
                    or re.fullmatch(r"0x[0-9a-fA-F]{64}", transfer["hash"]) is None
                    or not isinstance(transfer.get("category"), str)
                    or transfer["category"] not in categories
                    or not _is_evm_address(transfer.get("from"))
                    or not _is_evm_address(transfer.get("to"))):
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Alchemy returned a malformed Ethereum transfer record")
            block_number = _parse_hex_quantity(transfer.get("blockNum"), "transfer block number")
            if not from_block <= block_number <= to_block:
                raise ProviderTransportError("TRANSFER_BLOCK_OUT_OF_RANGE", "Alchemy returned a transfer outside the requested block range")
            raw_contract = transfer.get("rawContract")
            if not isinstance(raw_contract, dict):
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Alchemy transfer is missing raw-contract amount metadata")
            raw_value = raw_contract.get("value")
            if not isinstance(raw_value, str) or re.fullmatch(r"0x[0-9a-fA-F]+", raw_value) is None:
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Alchemy transfer raw amount is invalid")
            raw_decimals = raw_contract.get("decimal")
            decimals = _parse_hex_quantity(raw_decimals, "transfer decimals")
            if decimals > 36:
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Alchemy transfer decimals exceed the supported range")
            contract = raw_contract.get("address")
            if transfer["category"] == "erc20":
                if not _is_evm_address(contract) or contract.lower() not in {item.lower() for item in contracts}:
                    raise ProviderTransportError("TRANSFER_CONTRACT_MISMATCH", "Alchemy returned a token transfer outside the requested contract mapping")
            elif contract is not None and not _is_evm_address(contract):
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Alchemy native transfer contract reference is malformed")
            metadata = transfer.get("metadata")
            block_timestamp = metadata.get("blockTimestamp") if isinstance(metadata, dict) else None
            if block_timestamp is not None and not isinstance(block_timestamp, str):
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Alchemy transfer block timestamp is invalid")
            asset_label = transfer.get("asset")
            if asset_label is not None and not isinstance(asset_label, str):
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Alchemy transfer asset label is invalid")
            records.append(EthereumAssetTransfer(
                block_number, transfer["hash"], transfer["from"], transfer["to"],
                transfer["category"], str(int(raw_value, 16)), decimals,
                contract, asset_label, block_timestamp, transfer,
            ))
        cursor = result.get("pageKey")
        if cursor == "":
            cursor = None
        if cursor is not None and not isinstance(cursor, str):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Alchemy transfer page cursor is invalid")
        return ProviderDataPage("alchemy", "ethereum-mainnet", ",".join(contracts) or from_address or to_address,
                                tuple(records), cursor, from_block=from_block, to_block=to_block,
                                finalized_height=finalized_height,
                                finality_reference="eth_getBlockByNumber:finalized")

    def fetch_ethereum_finalized_height(self) -> int:
        """Return Ethereum mainnet's execution-layer finalized block height."""
        chain_id = self._call("ethereum-mainnet", "eth_chainId")
        if not isinstance(chain_id, str) or chain_id.lower() != "0x1":
            raise ProviderTransportError("NETWORK_ID_MISMATCH", "Alchemy endpoint returned the wrong Ethereum mainnet chain ID")
        header = self._call("ethereum-mainnet", "eth_getBlockByNumber", ["finalized", False])
        if not isinstance(header, dict):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Ethereum finalized block response is invalid")
        height = self._hex_int(header.get("number"), "Ethereum finalized block number")
        if not isinstance(header.get("hash"), str) or re.fullmatch(r"0x[0-9a-fA-F]{64}", header["hash"]) is None:
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Ethereum finalized block hash is invalid")
        return height

    def fetch_ethereum_block_header(self, block_number: int) -> dict:
        """Fetch one exact Ethereum execution-layer block header by height."""
        if isinstance(block_number, bool) or not isinstance(block_number, int) or block_number < 0:
            raise ValueError("block_number must be a non-negative integer")
        header = self._call("ethereum-mainnet", "eth_getBlockByNumber", [hex(block_number), False])
        if not isinstance(header, dict):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Ethereum block header response is invalid")
        returned_number = self._hex_int(header.get("number"), "Ethereum block number")
        timestamp = self._hex_int(header.get("timestamp"), "Ethereum block timestamp")
        block_hash = header.get("hash")
        if (returned_number != block_number or not isinstance(block_hash, str)
                or re.fullmatch(r"0x[0-9a-fA-F]{64}", block_hash) is None):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Ethereum canonical block header identity is invalid")
        return {"number": returned_number, "hash": block_hash.lower(), "timestamp": timestamp}

    def fetch_ethereum_erc20_transfer_logs(self, contract_address: str,
                                           from_block: int, to_block: int) -> ProviderDataPage:
        """Fetch a bounded mapped-contract ERC-20 Transfer log range on Ethereum."""
        if not _is_evm_address(contract_address):
            raise ValueError("Ethereum token contract must be an exact EVM address")
        if (isinstance(from_block, bool) or not isinstance(from_block, int) or from_block < 0
                or isinstance(to_block, bool) or not isinstance(to_block, int) or to_block < from_block):
            raise ValueError("Ethereum log query requires a fixed non-negative block range")
        # Keep requests conservatively bounded to ten blocks, matching the
        # existing free-tier BNB path; do not infer a larger plan entitlement.
        if to_block - from_block + 1 > 10:
            raise ValueError("Ethereum eth_getLogs request is limited to at most 10 blocks")
        chain_id = self._call("ethereum-mainnet", "eth_chainId")
        if not isinstance(chain_id, str) or chain_id.lower() != "0x1":
            raise ProviderTransportError("NETWORK_ID_MISMATCH", "Alchemy endpoint returned the wrong Ethereum mainnet chain ID")
        finalized_header = self._call("ethereum-mainnet", "eth_getBlockByNumber", ["finalized", False])
        if not isinstance(finalized_header, dict) or not isinstance(finalized_header.get("hash"), str):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Ethereum finalized header response is invalid")
        finalized_height = self._hex_int(finalized_header.get("number"), "Ethereum finalized block number")
        if re.fullmatch(r"0x[0-9a-fA-F]{64}", finalized_header["hash"]) is None:
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Ethereum finalized header hash is invalid")
        if to_block > finalized_height:
            raise ProviderTransportError("BLOCK_RANGE_NOT_FINALIZED", "Ethereum log query extends beyond the finalized block")
        logs = self._call("ethereum-mainnet", "eth_getLogs", [{
            "fromBlock": hex(from_block), "toBlock": hex(to_block),
            "address": contract_address, "topics": [TRANSFER_EVENT_TOPIC],
        }])
        if not isinstance(logs, list):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Alchemy Ethereum eth_getLogs response must be an array")
        records = tuple(self._decode_evm_transfer_log(
            "ethereum-mainnet", contract_address, item, from_block, to_block
        ) for item in logs)
        return ProviderDataPage(
            "alchemy", "ethereum-mainnet", contract_address, records,
            from_block=from_block, to_block=to_block,
            finalized_height=finalized_height,
            finality_reference="eth_getBlockByNumber:finalized",
        )

    def fetch_bnb_finalized_height(self) -> int:
        """Return the BNB finalized height after checking the endpoint chain ID."""
        chain_id = self._call("bnb-smart-chain-mainnet", "eth_chainId")
        if not isinstance(chain_id, str) or chain_id.lower() != "0x38":
            raise ProviderTransportError("NETWORK_ID_MISMATCH", "Alchemy endpoint returned the wrong BNB Smart Chain ID")
        header = self._call("bnb-smart-chain-mainnet", "eth_getFinalizedHeader", [-3])
        if not isinstance(header, dict):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "BNB finalized header response is invalid")
        height = self._hex_int(header.get("number"), "BNB finalized block number")
        if not isinstance(header.get("hash"), str) or re.fullmatch(r"0x[0-9a-fA-F]{64}", header["hash"]) is None:
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "BNB finalized header hash is invalid")
        return height

    def fetch_bnb_block_header(self, block_number: int) -> dict:
        """Fetch one independently addressable canonical BNB block header."""
        if isinstance(block_number, bool) or not isinstance(block_number, int) or block_number < 0:
            raise ValueError("block_number must be a non-negative integer")
        header = self._call("bnb-smart-chain-mainnet", "eth_getBlockByNumber", [hex(block_number), False])
        if not isinstance(header, dict):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "BNB block header response is invalid")
        returned_number = self._hex_int(header.get("number"), "BNB block number")
        timestamp = self._hex_int(header.get("timestamp"), "BNB block timestamp")
        block_hash = header.get("hash")
        if (returned_number != block_number or not isinstance(block_hash, str)
                or re.fullmatch(r"0x[0-9a-fA-F]{64}", block_hash) is None):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "BNB canonical block header identity is invalid")
        return {"number": returned_number, "hash": block_hash.lower(), "timestamp": timestamp}

    def fetch_bnb_erc20_transfer_logs(self, contract_address: str, from_block: int,
                                     to_block: int) -> ProviderDataPage:
        if not _is_evm_address(contract_address):
            raise ValueError("BNB token contract must be an exact EVM address")
        if (isinstance(from_block, bool) or not isinstance(from_block, int) or from_block < 0
                or isinstance(to_block, bool) or not isinstance(to_block, int) or to_block < from_block):
            raise ValueError("BNB log query requires a fixed non-negative block range")
        if to_block - from_block + 1 > 10:
            raise ValueError("Alchemy Free BNB eth_getLogs supports at most 10 blocks per query")
        chain_id = self._call("bnb-smart-chain-mainnet", "eth_chainId")
        if not isinstance(chain_id, str) or chain_id.lower() != "0x38":
            raise ProviderTransportError("NETWORK_ID_MISMATCH", "Alchemy endpoint returned the wrong BNB Smart Chain ID")
        finalized_header = self._call("bnb-smart-chain-mainnet", "eth_getFinalizedHeader", [-3])
        if not isinstance(finalized_header, dict) or not isinstance(finalized_header.get("hash"), str):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "BNB finalized header response is invalid")
        finalized_height = self._hex_int(finalized_header.get("number"), "BNB finalized block number")
        if to_block > finalized_height:
            raise ProviderTransportError("BLOCK_RANGE_NOT_FINALIZED", "BNB transfer query extends beyond the finalized block")
        logs = self._call("bnb-smart-chain-mainnet", "eth_getLogs", [{
            "fromBlock": hex(from_block), "toBlock": hex(to_block),
            "address": contract_address, "topics": [TRANSFER_EVENT_TOPIC],
        }])
        if not isinstance(logs, list):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Alchemy BNB eth_getLogs response must be an array")
        events = tuple(self._decode_bnb_transfer_log(contract_address, item, from_block, to_block) for item in logs)
        return ProviderDataPage("alchemy", "bnb-smart-chain-mainnet", contract_address,
                                events, from_block=from_block, to_block=to_block,
                                finalized_height=finalized_height,
                                finality_reference="eth_getFinalizedHeader:verifiedValidatorNum=-3")

    @staticmethod
    def _decode_bnb_transfer_log(contract_address: str, log: dict,
                                 from_block: int, to_block: int) -> EvmTokenTransferLog:
        return AlchemyReadOnlyAdapter._decode_evm_transfer_log(
            "bnb-smart-chain-mainnet", contract_address, log, from_block, to_block
        )

    @staticmethod
    def _decode_evm_transfer_log(network_id: str, contract_address: str, log: dict,
                                 from_block: int, to_block: int) -> EvmTokenTransferLog:
        label = "Ethereum" if network_id == "ethereum-mainnet" else "BNB"
        log_address = log.get("address") if isinstance(log, dict) else None
        if not isinstance(log_address, str) or log_address.lower() != contract_address.lower():
            raise ProviderTransportError("CONTRACT_SCOPE_MISMATCH", f"{label} log does not belong to the requested token contract")
        topics = log.get("topics")
        if (not isinstance(topics, list) or len(topics) != 3
                or any(not isinstance(topic, str) or re.fullmatch(r"0x[0-9a-fA-F]{64}", topic) is None for topic in topics)
                or topics[0].lower() != TRANSFER_EVENT_TOPIC
                or topics[1][2:26] != "0" * 24 or topics[2][2:26] != "0" * 24):
            raise ProviderTransportError("INVALID_TRANSFER_LOG", f"{label} log is not a standard ERC-20 Transfer event")
        data = log.get("data")
        if not isinstance(data, str) or re.fullmatch(r"0x[0-9a-fA-F]{64}", data) is None:
            raise ProviderTransportError("INVALID_TRANSFER_LOG", f"{label} Transfer event amount must be one uint256 word")
        block_number = _parse_hex_quantity(log.get("blockNumber"), "log block number")
        log_index = _parse_hex_quantity(log.get("logIndex"), "log index")
        block_hash, tx_hash = log.get("blockHash"), log.get("transactionHash")
        if (not isinstance(block_hash, str) or re.fullmatch(r"0x[0-9a-fA-F]{64}", block_hash) is None
                or not isinstance(tx_hash, str) or re.fullmatch(r"0x[0-9a-fA-F]{64}", tx_hash) is None
                or not from_block <= block_number <= to_block):
            raise ProviderTransportError("INVALID_TRANSFER_LOG", f"{label} Transfer event block/transaction references are invalid")
        removed = log.get("removed", False)
        if not isinstance(removed, bool):
            raise ProviderTransportError("INVALID_TRANSFER_LOG", f"{label} log removed flag must be boolean")
        return EvmTokenTransferLog(
            network_id, contract_address,
            "0x" + topics[1][-40:], "0x" + topics[2][-40:],
            str(int(data, 16)), block_number, block_hash, tx_hash, log_index, removed,
        )

    def fetch_solana_address_transactions(self, address: str,
                                          pagination_token: Optional[str] = None,
                                          limit: int = 100) -> ProviderDataPage:
        if not _is_base58_pubkey(address):
            raise ValueError("Solana account must be a valid base58 public key")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("Solana full transaction page limit must be between 1 and 100")
        if pagination_token is not None and (not isinstance(pagination_token, str) or not pagination_token.strip()):
            raise ValueError("Solana pagination_token must be a non-empty opaque string")
        genesis = self._call("solana-mainnet", "getGenesisHash")
        if genesis != SOLANA_MAINNET_GENESIS_HASH:
            raise ProviderTransportError("NETWORK_ID_MISMATCH", "Alchemy endpoint returned the wrong Solana genesis hash")
        config = {
            "transactionDetails": "full", "sortOrder": "desc", "limit": limit,
            "commitment": "finalized",
            "filters": {"status": "succeeded", "tokenAccounts": "balanceChanged"},
        }
        if pagination_token is not None:
            config["paginationToken"] = pagination_token
        result = self._call("solana-mainnet", "getTransactionsForAddress", [address, config])
        if not isinstance(result, dict):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Alchemy Solana transaction page has an invalid shape")
        raw_records = result.get("transactions", result.get("data"))
        if not isinstance(raw_records, list) or any(not isinstance(item, dict) for item in raw_records):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Alchemy Solana transaction records are invalid")
        records = []
        for item in raw_records:
            signature = item.get("signature")
            if signature is None and isinstance(item.get("transaction"), dict):
                signatures = item["transaction"].get("signatures")
                signature = signatures[0] if isinstance(signatures, list) and signatures else None
            slot, block_time = item.get("slot"), item.get("blockTime")
            if (not _is_base58_signature(signature)
                    or isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0
                    or not isinstance(item.get("transaction"), dict)
                    or not isinstance(item.get("meta"), dict)
                    or (block_time is not None and (isinstance(block_time, bool) or not isinstance(block_time, int) or block_time <= 0))):
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Alchemy Solana transaction lacks a valid signature, slot, transaction metadata or block time")
            records.append(SolanaAddressTransaction(signature, slot, block_time, item))
        cursor = result.get("paginationToken")
        if cursor == "":
            cursor = None
        if cursor is not None and not isinstance(cursor, str):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Alchemy Solana pagination token is invalid")
        return ProviderDataPage("alchemy", "solana-mainnet", address, tuple(records), cursor,
                                finality_reference="commitment=finalized")

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

    def fetch_account_transactions(self, account: str,
                                   ledger_index_min: int, ledger_index_max: int,
                                   marker=None, limit: int = 200) -> ProviderDataPage:
        if not isinstance(account, str) or not account.startswith("r") or not 25 <= len(account) <= 35:
            raise ValueError("XRPL account must be a valid-looking mainnet address")
        if (isinstance(ledger_index_min, bool) or not isinstance(ledger_index_min, int) or ledger_index_min < 0
                or isinstance(ledger_index_max, bool) or not isinstance(ledger_index_max, int)
                or ledger_index_max < ledger_index_min):
            raise ValueError("XRPL account_tx requires a fixed non-negative ledger range")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("XRPL account_tx limit must be between 1 and 1000")
        if marker is not None:
            try:
                json.dumps(marker, allow_nan=False)
            except (TypeError, ValueError):
                raise ValueError("XRPL marker must be a JSON-compatible opaque cursor") from None
        transport = self._transport_factory(self._endpoint, self._timeout_seconds)
        params = {
            "account": account, "ledger_index_min": ledger_index_min,
            "ledger_index_max": ledger_index_max, "limit": limit,
            "forward": False, "binary": False, "api_version": 2,
        }
        if marker is not None:
            params["marker"] = marker
        result = transport.call("account_tx", [params])
        if not isinstance(result, dict) or result.get("validated") is not True:
            raise ProviderTransportError("UNVALIDATED_XRPL_PAGE", "XRPL account_tx page is not marked validated")
        if result.get("account") != account:
            raise ProviderTransportError("ADDRESS_SCOPE_MISMATCH", "XRPL provider returned a different account scope")
        raw_records = result.get("transactions")
        if not isinstance(raw_records, list):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "XRPL account_tx transaction list is invalid")
        records = []
        for item in raw_records:
            if not isinstance(item, dict) or item.get("validated") is not True:
                raise ProviderTransportError("UNVALIDATED_XRPL_TRANSACTION", "XRPL account_tx contains a transaction without validated-ledger proof")
            tx_hash, ledger_index = item.get("hash"), item.get("ledger_index")
            transaction, metadata = item.get("tx_json"), item.get("meta")
            if (not isinstance(tx_hash, str) or re.fullmatch(r"[0-9a-fA-F]{64}", tx_hash) is None
                    or isinstance(ledger_index, bool) or not isinstance(ledger_index, int)
                    or not ledger_index_min <= ledger_index <= ledger_index_max
                    or not isinstance(transaction, dict) or not isinstance(metadata, dict)):
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "XRPL transaction identity, ledger or metadata is malformed")
            close_time = item.get("close_time_iso")
            if close_time is not None and not isinstance(close_time, str):
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "XRPL close_time_iso must be a string")
            records.append(XrplAccountTransaction(tx_hash, ledger_index, close_time, transaction, metadata, item))
        returned_min, returned_max = result.get("ledger_index_min"), result.get("ledger_index_max")
        if (isinstance(returned_min, bool) or not isinstance(returned_min, int)
                or isinstance(returned_max, bool) or not isinstance(returned_max, int)
                or returned_min > ledger_index_min or returned_max < ledger_index_max):
            raise ProviderTransportError("XRPL_LEDGER_RANGE_INCOMPLETE", "XRPL provider did not cover the requested fixed ledger range")
        cursor = result.get("marker")
        if cursor is not None:
            try:
                json.dumps(cursor, allow_nan=False)
            except (TypeError, ValueError):
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "XRPL pagination marker is not JSON-compatible") from None
        return ProviderDataPage("chainstack", "xrpl-mainnet", account, tuple(records), cursor,
                                from_block=ledger_index_min, to_block=ledger_index_max,
                                finality_reference="validated=true")

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
