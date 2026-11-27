"""Bounded, restart-safe ingestion of mapped Ethereum and BNB ERC-20 logs.

Both networks use eth_getLogs and the stable transaction_hash:log_index
identity. Alchemy Ethereum transfer summaries are intentionally not used.
"""
from __future__ import annotations

import re
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from .onchain import OnChainAssetMapping
from .onchain_ingestion import (
    OnChainFinalitySnapshot, normalize_evm_transfer_log, _is_uint256_decimal,
)
from .onchain_providers import (
    MAX_DATETIME_UNIX_TIMESTAMP,
    EvmTokenTransferLog, ProviderTransportError, retry_provider_operation,
    _capture_provider_run_receipts, drain_provider_run_receipts,
    include_provider_receipts_in_current_scope,
)
from .onchain_protocols import (
    OnChainIngestionStoreProtocol, OnChainMappingStoreProtocol,
    require_ingestion_store, require_mapping_store,
)


EVM_NETWORKS = {
    "ethereum-mainnet": {"chain_id": "1", "provider_prefix": "ethereum"},
    "bnb-smart-chain-mainnet": {"chain_id": "56", "provider_prefix": "bnb"},
}
MAX_PROVIDER_BLOCK_SPAN = 10
_RETRYABLE = {"TIMEOUT", "NETWORK_ERROR", "RATE_LIMITED"}


class EvmTransferIngestionWorker:
    """Ingest bounded finalized Ethereum/BNB token ranges into the existing atomic store."""

    def __init__(
        self,
        provider,
        mapping_store: OnChainMappingStoreProtocol,
        ingestion_store: OnChainIngestionStoreProtocol,
        *,
        start_blocks: dict[str, int],
        max_blocks_per_run: int,
        reorg_lookback_blocks: int,
        retry_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        require_mapping_store(mapping_store)
        require_ingestion_store(ingestion_store)
        if not isinstance(start_blocks, dict) or not start_blocks:
            raise ValueError("explicit start_blocks are required for each verified mapping")
        for mapping_id, height in start_blocks.items():
            if not isinstance(mapping_id, str) or not mapping_id.strip():
                raise ValueError("start block mapping IDs must be non-empty strings")
            if isinstance(height, bool) or not isinstance(height, int) or height < 0:
                raise ValueError("start blocks must be non-negative integers")
        if isinstance(max_blocks_per_run, bool) or not isinstance(max_blocks_per_run, int) or not 1 <= max_blocks_per_run <= 1000:
            raise ValueError("max_blocks_per_run must be between 1 and 1000")
        if max_blocks_per_run < 1:
            raise ValueError("max_blocks_per_run must be positive")
        if isinstance(reorg_lookback_blocks, bool) or not isinstance(reorg_lookback_blocks, int) or reorg_lookback_blocks < 0:
            raise ValueError("reorg_lookback_blocks must be a non-negative integer")
        if isinstance(retry_attempts, bool) or not isinstance(retry_attempts, int) or not 1 <= retry_attempts <= 5:
            raise ValueError("retry_attempts must be between 1 and 5")
        self.provider = provider
        self.mapping_store = mapping_store
        self.ingestion_store = ingestion_store
        self.start_blocks = dict(start_blocks)
        self.max_blocks_per_run = max_blocks_per_run
        self.reorg_lookback_blocks = reorg_lookback_blocks
        self.retry_attempts = retry_attempts
        self.sleep = sleep
        self.clock = clock

    def _retry(self, operation):
        return retry_provider_operation(
            operation, attempts=self.retry_attempts, sleep=self.sleep,
        )

    @staticmethod
    def _cursor_key(mapping: OnChainAssetMapping) -> str:
        return f"alchemy:{mapping.network_id}:contract:{mapping.contract_address.lower()}"

    @staticmethod
    def _validate_mapping(mapping: OnChainAssetMapping) -> None:
        network = EVM_NETWORKS.get(mapping.network_id)
        if (network is None or mapping.network_family != "EVM"
                or mapping.chain_id != network["chain_id"] or mapping.mapping_status != "VERIFIED"
                or mapping.representation not in {"TOKEN", "WRAPPED", "BRIDGED", "DERIVATIVE"}
                or not isinstance(mapping.token_standard, str)
                or mapping.token_standard not in {"ERC20", "ERC-20"}
                or isinstance(mapping.decimals, bool) or not isinstance(mapping.decimals, int)
                or not 0 <= mapping.decimals <= 36
                or not isinstance(mapping.contract_address, str)
                or re.fullmatch(r"0x[0-9a-fA-F]{40}", mapping.contract_address) is None):
            raise ValueError("worker encountered a mapping outside the verified Ethereum/BNB token scope")

    def _header(self, mapping: OnChainAssetMapping, height: int) -> dict:
        prefix = EVM_NETWORKS[mapping.network_id]["provider_prefix"]
        method = getattr(self.provider, f"fetch_{prefix}_block_header")
        header = self._retry(lambda: method(height))
        if (not isinstance(header, dict)
                or isinstance(header.get("number"), bool)
                or not isinstance(header.get("number"), int)
                or header.get("number") != height
                or not isinstance(header.get("hash"), str)
                or re.fullmatch(r"0x[0-9a-fA-F]{64}", header["hash"]) is None
                or not isinstance(header.get("parent_hash"), str)
                or re.fullmatch(r"0x[0-9a-f]{64}", header["parent_hash"]) is None
                or not isinstance(header.get("transaction_hashes"), tuple)
                or any(not isinstance(item, str) or re.fullmatch(r"0x[0-9a-f]{64}", item) is None
                       for item in header["transaction_hashes"])
                or len(set(header["transaction_hashes"])) != len(header["transaction_hashes"])
                or isinstance(header.get("timestamp"), bool)
                or not isinstance(header.get("timestamp"), int) or not 0 <= header["timestamp"] <= MAX_DATETIME_UNIX_TIMESTAMP):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "provider returned a malformed canonical block header")
        return header

    def _reconcile_recent(self, mapping: OnChainAssetMapping, next_block: int, initial_block: int):
        if self.reorg_lookback_blocks == 0 or next_block <= initial_block:
            return 0, None, 0
        first = max(initial_block, next_block - self.reorg_lookback_blocks)
        changed = 0
        earliest_changed = None
        detected_blocks = 0
        scope = f"contract:{mapping.contract_address.lower()}"
        for height in range(first, next_block):
            stored_hash = self.ingestion_store.get_block_hash(
                mapping.network_id, "alchemy", scope, height
            )
            if stored_hash is None:
                continue
            header = self._header(mapping, height)
            if stored_hash.lower() != header["hash"].lower():
                detected_blocks += 1
                count = self.ingestion_store.reconcile_block(
                    mapping.network_id, height, header["hash"].lower(),
                    provider="alchemy", scope=scope,
                )
                changed += count
                if earliest_changed is None:
                    earliest_changed = height
        return changed, earliest_changed, detected_blocks

    def _finalize_page_acceptances(self, summary: dict) -> None:
        result = self.mapping_store.engine.sign_pending_ingestion_pages(self.ingestion_store)
        summary["page_acceptances_signed"] = result["signed"]
        summary["page_acceptances_pending"] = result["pending"]
        summary["page_acceptances_rejected"] = result["rejected"]

    @_capture_provider_run_receipts
    def run_once(self) -> dict:
        mappings = [
            mapping
            for network_id in EVM_NETWORKS
            for mapping in self.mapping_store.list_verified_mappings(network_id)
        ]
        summary = {
            "mappings": 0, "blocks_scanned": 0, "events_inserted": 0,
            "duplicates": 0, "tombstoned": 0, "reorg_blocks_detected": 0,
            "reorg_events_tombstoned": 0, "checkpoints_advanced": 0,
        }
        summary.update({"page_acceptances_signed": 0, "page_acceptances_pending": 0,
                        "page_acceptances_rejected": 0})
        for mapping in mappings:
            drain_provider_run_receipts()  # isolate this contract from prior mapping failures
            self._validate_mapping(mapping)
            if mapping.mapping_id not in self.start_blocks:
                raise ValueError(f"no explicit start block configured for mapping {mapping.mapping_id}")
            summary["mappings"] += 1
            cursor_key = self._cursor_key(mapping)
            scope = f"contract:{mapping.contract_address.lower()}"
            checkpoint = self.ingestion_store.get_checkpoint(cursor_key)
            initial_block = self.start_blocks[mapping.mapping_id]
            if checkpoint is None:
                next_block = initial_block
            else:
                if not isinstance(checkpoint, dict) or isinstance(checkpoint.get("next_block"), bool) or not isinstance(checkpoint.get("next_block"), int):
                    raise ValueError("stored EVM checkpoint is malformed")
                next_block = checkpoint["next_block"]
            reorg_count, rewind_to, reorg_blocks = self._reconcile_recent(mapping, next_block, initial_block)
            summary["reorg_events_tombstoned"] += reorg_count
            summary["reorg_blocks_detected"] += reorg_blocks
            if rewind_to is not None:
                # Rewind the durable cursor before replaying the changed finalized range.
                # A crash here is safe: the next run repeats this bounded reconciliation.
                next_block = rewind_to
                rewind_checkpoint = {
                    "mapping_id": mapping.mapping_id, "network_id": mapping.network_id,
                    "scope": scope, "next_block": rewind_to, "reorg_rewind": True,
                }
                self.ingestion_store.commit_page(
                    cursor_key, rewind_checkpoint, (), expected_cursor=checkpoint,
                    scope_identity=(mapping.network_id, "alchemy", scope))
                checkpoint = rewind_checkpoint
            prefix = EVM_NETWORKS[mapping.network_id]["provider_prefix"]
            finalized_method = getattr(self.provider, f"fetch_{prefix}_finalized_height")
            logs_method = getattr(self.provider, f"fetch_{prefix}_erc20_transfer_logs")
            finalized_height = self._retry(finalized_method)
            if isinstance(finalized_height, bool) or not isinstance(finalized_height, int) or finalized_height < 0:
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "provider finalized height is invalid")
            bounded_end = min(finalized_height, next_block + self.max_blocks_per_run - 1)
            if next_block > bounded_end:
                continue
            previous_header_hash = None
            previous_header_timestamp = None
            if next_block > initial_block:
                anchor_header = self._header(mapping, next_block - 1)
                previous_header_hash = anchor_header["hash"].lower()
                previous_header_timestamp = anchor_header["timestamp"]
            for range_start in range(next_block, bounded_end + 1, MAX_PROVIDER_BLOCK_SPAN):
                range_end = min(bounded_end, range_start + MAX_PROVIDER_BLOCK_SPAN - 1)
                page = self._retry(lambda: logs_method(
                    mapping.contract_address, range_start, range_end
                ))
                records = getattr(page, "records", None)
                expected_finality = (
                    "eth_getBlockByNumber:finalized"
                    if mapping.network_id == "ethereum-mainnet"
                    else "eth_getFinalizedHeader:verifiedValidatorNum=-3"
                )
                if (not isinstance(records, tuple)
                        or getattr(page, "provider", None) != "alchemy"
                        or getattr(page, "network_id", None) != mapping.network_id
                        or str(getattr(page, "scope", "")).lower() != mapping.contract_address.lower()
                        or getattr(page, "from_block", None) != range_start
                        or getattr(page, "to_block", None) != range_end
                        or isinstance(getattr(page, "finalized_height", None), bool)
                        or not isinstance(getattr(page, "finalized_height", None), int)
                        or page.finalized_height < range_end
                        or getattr(page, "finality_reference", None) != expected_finality):
                    raise ProviderTransportError("INVALID_PROVIDER_DATA", "provider log page is malformed or not finalized for the requested scope/range")
                headers = {
                    height: self._header(mapping, height)
                    for height in range(range_start, range_end + 1)
                }
                for height in range(range_start, range_end + 1):
                    header = headers[height]
                    if (previous_header_hash is not None
                            and header["parent_hash"].lower() != previous_header_hash):
                        raise ProviderTransportError(
                            "EVM_PARENT_HASH_MISMATCH",
                            "EVM finalized block parentHash does not match the preceding fetched block hash",
                        )
                    if previous_header_timestamp is not None:
                        invalid_time_order = (
                            header["timestamp"] <= previous_header_timestamp
                            if mapping.network_id == "ethereum-mainnet"
                            else header["timestamp"] < previous_header_timestamp
                        )
                        if invalid_time_order:
                            raise ProviderTransportError(
                                "EVM_BLOCK_TIMESTAMP_NOT_MONOTONIC",
                                "EVM finalized block timestamp is not monotonic relative to its parent",
                            )
                    previous_header_hash = header["hash"].lower()
                    previous_header_timestamp = header["timestamp"]
                normalized = []
                seen_log_positions = set()
                observed = self.clock()
                if observed.tzinfo is None or observed.utcoffset() is None:
                    raise ValueError("worker clock must return a timezone-aware datetime")
                observed_at = observed.astimezone(timezone.utc).isoformat()
                for record in records:
                    if not isinstance(record, EvmTokenTransferLog):
                        raise ProviderTransportError("INVALID_PROVIDER_DATA", "provider log page contains a malformed record")
                    if (
                        not isinstance(record.network_id, str)
                        or not isinstance(record.contract_address, str)
                        or re.fullmatch(r"0x[0-9a-fA-F]{40}", record.contract_address) is None
                        or not isinstance(record.from_address, str)
                        or re.fullmatch(r"0x[0-9a-fA-F]{40}", record.from_address) is None
                        or not isinstance(record.to_address, str)
                        or re.fullmatch(r"0x[0-9a-fA-F]{40}", record.to_address) is None
                        or not _is_uint256_decimal(record.amount_raw)
                        or isinstance(record.block_number, bool)
                        or not isinstance(record.block_number, int)
                        or record.block_number < 0
                        or not isinstance(record.block_hash, str)
                        or re.fullmatch(r"0x[0-9a-fA-F]{64}", record.block_hash) is None
                        or not isinstance(record.transaction_hash, str)
                        or re.fullmatch(r"0x[0-9a-fA-F]{64}", record.transaction_hash) is None
                        or isinstance(record.log_index, bool)
                        or not isinstance(record.log_index, int)
                        or record.log_index < 0
                        or not isinstance(record.removed, bool)
                        or isinstance(record.transaction_index, bool)
                        or not isinstance(record.transaction_index, int)
                        or record.transaction_index < 0
                    ):
                        raise ProviderTransportError(
                            "INVALID_PROVIDER_DATA",
                            "provider EVM transfer log contains malformed identity, address, amount, index or flag fields",
                        )
                    if (record.network_id != mapping.network_id
                            or record.contract_address.lower() != mapping.contract_address.lower()
                            or not range_start <= record.block_number <= range_end):
                        raise ProviderTransportError("PROVIDER_SCOPE_MISMATCH", "provider log is outside the requested mapping/range")
                    header = headers[record.block_number]
                    transaction_index = record.transaction_index
                    if (isinstance(transaction_index, bool) or not isinstance(transaction_index, int)
                            or transaction_index < 0
                            or transaction_index >= len(header["transaction_hashes"])
                            or header["transaction_hashes"][transaction_index] != record.transaction_hash.lower()):
                        raise ProviderTransportError(
                            "EVM_TRANSACTION_INDEX_MISMATCH",
                            "EVM log transactionHash does not match the canonical block transaction at transactionIndex",
                        )
                    log_position = (record.block_number, record.log_index)
                    if log_position in seen_log_positions:
                        raise ProviderTransportError(
                            "DUPLICATE_EVM_LOG_INDEX",
                            "provider returned more than one log for the same block-global logIndex",
                        )
                    seen_log_positions.add(log_position)
                    header = headers[record.block_number]
                    block_time = datetime.fromtimestamp(header["timestamp"], timezone.utc).isoformat()
                    normalized.append(replace(
                        normalize_evm_transfer_log(
                            record, asset_id=mapping.asset_id, mapping_id=mapping.mapping_id,
                            expected_contract_address=mapping.contract_address,
                            canonical_block_hash=header["hash"], decimals=mapping.decimals,
                            block_time=block_time, observed_at=observed_at, scope=scope,
                        ),
                        finality_snapshot=OnChainFinalitySnapshot(
                            version=1, network_id=mapping.network_id, status="FINALIZED",
                            reference=page.finality_reference,
                        ),
                    ))
                next_cursor = {
                    "mapping_id": mapping.mapping_id,
                    "network_id": mapping.network_id,
                    "scope": scope,
                    "from_block": range_start,
                    "to_block": range_end,
                    "next_block": range_end + 1,
                    "finalized_height": finalized_height,
                    "finality_reference": page.finality_reference,
                }
                committed = self.ingestion_store.commit_page(
                    cursor_key, next_cursor, normalized, allow_recanonicalized=True,
                    canonical_blocks=tuple({
                        "network_id": mapping.network_id, "provider": "alchemy", "scope": scope,
                        "block_number": height, "block_hash": header["hash"].lower(),
                        "block_time": datetime.fromtimestamp(header["timestamp"], timezone.utc).isoformat(),
                    } for height, header in headers.items()),
                    expected_cursor=checkpoint,
                    scope_identity=(mapping.network_id, "alchemy", scope),
                    provider_receipts=drain_provider_run_receipts(),
                )
                checkpoint = next_cursor
                summary["events_inserted"] += committed["inserted"]
                summary["duplicates"] += committed["duplicates"]
                summary["tombstoned"] += committed["tombstoned"]
                summary["blocks_scanned"] += range_end - range_start + 1
                summary["checkpoints_advanced"] += 1
        self._finalize_page_acceptances(summary)
        return summary
