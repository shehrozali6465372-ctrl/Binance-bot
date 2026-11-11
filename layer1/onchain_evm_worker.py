"""Bounded, restart-safe ingestion of mapped BNB ERC-20 Transfer logs.

The worker intentionally handles the one EVM provider path that exposes a
stable transaction/log index today. Ethereum's Alchemy transfer summaries are
not accepted because they do not expose a log index.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Callable

from .onchain import OnChainAssetMapping, OnChainStore
from .onchain_ingestion import OnChainIngestionStore, normalize_evm_transfer_log
from .onchain_providers import EvmTokenTransferLog, ProviderTransportError


NETWORK_ID = "bnb-smart-chain-mainnet"
MAX_PROVIDER_BLOCK_SPAN = 10
_RETRYABLE = {"TIMEOUT", "NETWORK_ERROR", "RATE_LIMITED"}


class EvmTransferIngestionWorker:
    """Ingest bounded finalized BNB token ranges into the existing atomic store."""

    def __init__(
        self,
        provider,
        mapping_store: OnChainStore,
        ingestion_store: OnChainIngestionStore,
        *,
        start_blocks: dict[str, int],
        max_blocks_per_run: int,
        reorg_lookback_blocks: int,
        retry_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        if not isinstance(mapping_store, OnChainStore) or not isinstance(ingestion_store, OnChainIngestionStore):
            raise ValueError("worker requires the existing on-chain mapping and ingestion stores")
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
        for attempt in range(self.retry_attempts):
            try:
                return operation()
            except ProviderTransportError as exc:
                retryable = exc.reason_code in _RETRYABLE or (
                    exc.reason_code == "HTTP_ERROR" and exc.http_status is not None and exc.http_status >= 500
                )
                if not retryable or attempt + 1 >= self.retry_attempts:
                    raise
                self.sleep(min(0.25 * (2 ** attempt), 2.0))

    @staticmethod
    def _cursor_key(mapping: OnChainAssetMapping) -> str:
        return f"alchemy:{mapping.network_id}:contract:{mapping.contract_address.lower()}"

    @staticmethod
    def _validate_mapping(mapping: OnChainAssetMapping) -> None:
        if (mapping.network_id != NETWORK_ID or mapping.network_family != "EVM"
                or mapping.chain_id != "56" or mapping.mapping_status != "VERIFIED"
                or mapping.representation not in {"TOKEN", "WRAPPED", "BRIDGED", "DERIVATIVE"}
                or not isinstance(mapping.contract_address, str)
                or re.fullmatch(r"0x[0-9a-fA-F]{40}", mapping.contract_address) is None):
            raise ValueError("worker encountered a mapping outside the verified BNB token scope")

    def _header(self, height: int) -> dict:
        header = self._retry(lambda: self.provider.fetch_bnb_block_header(height))
        if (not isinstance(header, dict) or header.get("number") != height
                or not isinstance(header.get("hash"), str)
                or re.fullmatch(r"0x[0-9a-fA-F]{64}", header["hash"]) is None
                or isinstance(header.get("timestamp"), bool)
                or not isinstance(header.get("timestamp"), int) or header["timestamp"] < 0):
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
            header = self._header(height)
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

    def run_once(self) -> dict:
        mappings = self.mapping_store.list_verified_mappings(NETWORK_ID)
        summary = {
            "mappings": 0, "blocks_scanned": 0, "events_inserted": 0,
            "duplicates": 0, "tombstoned": 0, "reorg_blocks_detected": 0,
            "reorg_events_tombstoned": 0, "checkpoints_advanced": 0,
        }
        for mapping in mappings:
            self._validate_mapping(mapping)
            if mapping.mapping_id not in self.start_blocks:
                raise ValueError(f"no explicit start block configured for mapping {mapping.mapping_id}")
            summary["mappings"] += 1
            cursor_key = self._cursor_key(mapping)
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
                self.ingestion_store.commit_page(cursor_key, {
                    "mapping_id": mapping.mapping_id, "network_id": NETWORK_ID,
                    "scope": f"contract:{mapping.contract_address.lower()}",
                    "next_block": rewind_to, "reorg_rewind": True,
                }, ())
            finalized_height = self._retry(self.provider.fetch_bnb_finalized_height)
            if isinstance(finalized_height, bool) or not isinstance(finalized_height, int) or finalized_height < 0:
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "provider finalized height is invalid")
            bounded_end = min(finalized_height, next_block + self.max_blocks_per_run - 1)
            if next_block > bounded_end:
                continue
            scope = f"contract:{mapping.contract_address.lower()}"
            for range_start in range(next_block, bounded_end + 1, MAX_PROVIDER_BLOCK_SPAN):
                range_end = min(bounded_end, range_start + MAX_PROVIDER_BLOCK_SPAN - 1)
                page = self._retry(lambda: self.provider.fetch_bnb_erc20_transfer_logs(
                    mapping.contract_address, range_start, range_end
                ))
                records = getattr(page, "records", None)
                if (not isinstance(records, tuple)
                        or getattr(page, "provider", None) != "alchemy"
                        or getattr(page, "network_id", None) != NETWORK_ID
                        or str(getattr(page, "scope", "")).lower() != mapping.contract_address.lower()
                        or getattr(page, "from_block", None) != range_start
                        or getattr(page, "to_block", None) != range_end
                        or isinstance(getattr(page, "finalized_height", None), bool)
                        or not isinstance(getattr(page, "finalized_height", None), int)
                        or page.finalized_height < range_end):
                    raise ProviderTransportError("INVALID_PROVIDER_DATA", "provider log page is malformed or not finalized for the requested scope/range")
                headers = {
                    height: self._header(height)
                    for height in range(range_start, range_end + 1)
                }
                normalized = []
                observed = self.clock()
                if observed.tzinfo is None or observed.utcoffset() is None:
                    raise ValueError("worker clock must return a timezone-aware datetime")
                observed_at = observed.astimezone(timezone.utc).isoformat()
                for record in records:
                    if not isinstance(record, EvmTokenTransferLog):
                        raise ProviderTransportError("INVALID_PROVIDER_DATA", "provider log page contains a malformed record")
                    if (record.network_id != NETWORK_ID
                            or record.contract_address.lower() != mapping.contract_address.lower()
                            or not range_start <= record.block_number <= range_end):
                        raise ProviderTransportError("PROVIDER_SCOPE_MISMATCH", "provider log is outside the requested mapping/range")
                    header = headers[record.block_number]
                    block_time = datetime.fromtimestamp(header["timestamp"], timezone.utc).isoformat()
                    normalized.append(normalize_evm_transfer_log(
                        record, asset_id=mapping.asset_id, mapping_id=mapping.mapping_id,
                        expected_contract_address=mapping.contract_address,
                        canonical_block_hash=header["hash"], decimals=mapping.decimals,
                        block_time=block_time, observed_at=observed_at, scope=scope,
                    ))
                next_cursor = {
                    "mapping_id": mapping.mapping_id,
                    "network_id": NETWORK_ID,
                    "scope": scope,
                    "from_block": range_start,
                    "to_block": range_end,
                    "next_block": range_end + 1,
                    "finalized_height": finalized_height,
                }
                committed = self.ingestion_store.commit_page(
                    cursor_key, next_cursor, normalized, allow_recanonicalized=True,
                    canonical_blocks=tuple({
                        "network_id": NETWORK_ID, "provider": "alchemy", "scope": scope,
                        "block_number": height, "block_hash": header["hash"].lower(),
                        "block_time": datetime.fromtimestamp(header["timestamp"], timezone.utc).isoformat(),
                    } for height, header in headers.items()),
                )
                summary["events_inserted"] += committed["inserted"]
                summary["duplicates"] += committed["duplicates"]
                summary["tombstoned"] += committed["tombstoned"]
                summary["blocks_scanned"] += range_end - range_start + 1
                summary["checkpoints_advanced"] += 1
        return summary
