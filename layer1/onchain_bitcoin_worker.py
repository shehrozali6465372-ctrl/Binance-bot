"""Bounded, restart-safe Bitcoin address-history ingestion.

This worker is deliberately address-seeded: it is not a network-wide whale
feed. Bitcoin confirmation policy is supplied explicitly by the caller.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Callable

from .onchain import OnChainAssetMapping, OnChainStore
from .onchain_ingestion import OnChainIngestionStore, normalize_bitcoin_transaction_outputs
from .onchain_providers import BitcoinAddressTransaction, ProviderTransportError


_RETRYABLE = {"TIMEOUT", "NETWORK_ERROR", "RATE_LIMITED"}


class BitcoinAddressIngestionWorker:
    def __init__(
        self, provider, mapping_store: OnChainStore,
        ingestion_store: OnChainIngestionStore, *,
        monitored_addresses: dict[str, tuple[str, ...]],
        start_blocks: dict[str, int],
        minimum_confirmations: int,
        max_blocks_per_run: int,
        page_size: int,
        reorg_lookback_blocks: int,
        retry_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        if not isinstance(mapping_store, OnChainStore) or not isinstance(ingestion_store, OnChainIngestionStore):
            raise ValueError("worker requires the existing mapping and ingestion stores")
        if not isinstance(monitored_addresses, dict) or not monitored_addresses:
            raise ValueError("explicit monitored address seeds are required")
        if not isinstance(start_blocks, dict) or not start_blocks:
            raise ValueError("explicit start block per verified mapping is required")
        if isinstance(minimum_confirmations, bool) or not isinstance(minimum_confirmations, int) or minimum_confirmations < 1:
            raise ValueError("minimum_confirmations must be explicitly configured as a positive integer")
        if isinstance(max_blocks_per_run, bool) or not isinstance(max_blocks_per_run, int) or not 1 <= max_blocks_per_run <= 1000:
            raise ValueError("max_blocks_per_run must be between 1 and 1000")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        if isinstance(reorg_lookback_blocks, bool) or not isinstance(reorg_lookback_blocks, int) or reorg_lookback_blocks < 0:
            raise ValueError("reorg_lookback_blocks must be a non-negative integer")
        if isinstance(retry_attempts, bool) or not isinstance(retry_attempts, int) or not 1 <= retry_attempts <= 5:
            raise ValueError("retry_attempts must be between 1 and 5")
        for mapping_id, addresses in monitored_addresses.items():
            if (not isinstance(mapping_id, str) or not mapping_id.strip()
                    or not isinstance(addresses, (tuple, list)) or not addresses
                    or any(not isinstance(a, str) or not a.strip() or any(c.isspace() for c in a) for a in addresses)
                    or len(set(addresses)) != len(addresses)):
                raise ValueError("each mapping requires unique, explicit non-empty monitored address seeds")
        for mapping_id, height in start_blocks.items():
            if not isinstance(mapping_id, str) or not mapping_id.strip() or isinstance(height, bool) or not isinstance(height, int) or height < 0:
                raise ValueError("start block mapping IDs and heights are invalid")
        if set(monitored_addresses) != set(start_blocks):
            raise ValueError("monitored address seeds and explicit start blocks must cover the same mapping IDs")
        self.provider, self.mapping_store, self.ingestion_store = provider, mapping_store, ingestion_store
        self.monitored_addresses = {key: tuple(value) for key, value in monitored_addresses.items()}
        self.start_blocks = dict(start_blocks)
        self.minimum_confirmations = minimum_confirmations
        self.max_blocks_per_run, self.page_size = max_blocks_per_run, page_size
        self.reorg_lookback_blocks, self.retry_attempts = reorg_lookback_blocks, retry_attempts
        self.sleep, self.clock = sleep, clock

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
    def _validate_mapping(mapping: OnChainAssetMapping):
        if (mapping.network_id != "bitcoin-mainnet" or mapping.network_family != "UTXO"
                or mapping.chain_id != "bitcoin-mainnet" or mapping.mapping_status != "VERIFIED"
                or mapping.representation != "NATIVE" or mapping.contract_address is not None
                or mapping.token_standard is not None or mapping.decimals != 8):
            raise ValueError("Bitcoin worker requires a verified native BTC asset mapping")

    @staticmethod
    def _cursor_key(address: str) -> str:
        return f"alchemy:bitcoin-mainnet:address:{address}"

    def _header(self, height: int) -> dict:
        header = self._retry(lambda: self.provider.fetch_bitcoin_block_header(height))
        if (not isinstance(header, dict) or isinstance(header.get("number"), bool)
                or header.get("number") != height
                or not isinstance(header.get("hash"), str)
                or re.fullmatch(r"[0-9a-fA-F]{64}", header["hash"]) is None
                or isinstance(header.get("timestamp"), bool)
                or not isinstance(header.get("timestamp"), int) or header["timestamp"] <= 0):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Bitcoin provider returned a malformed canonical block header")
        return header

    def _reconcile(self, address: str, next_block: int, initial_block: int):
        if self.reorg_lookback_blocks == 0 or next_block <= initial_block:
            return 0, None, 0
        scope = f"address:{address}"
        first = max(initial_block, next_block - self.reorg_lookback_blocks)
        tombstoned = detected = 0
        earliest = None
        for height in range(first, next_block):
            stored = self.ingestion_store.get_block_hash("bitcoin-mainnet", "alchemy", scope, height)
            if stored is None:
                continue
            header = self._header(height)
            if stored.lower() != header["hash"].lower():
                detected += 1
                tombstoned += self.ingestion_store.reconcile_block(
                    "bitcoin-mainnet", height, header["hash"].lower(), provider="alchemy", scope=scope)
                if earliest is None:
                    earliest = height
        return tombstoned, earliest, detected

    def run_once(self) -> dict:
        mappings = self.mapping_store.list_verified_mappings("bitcoin-mainnet")
        summary = {"mappings": 0, "addresses": 0, "blocks_scanned": 0,
                   "events_inserted": 0, "duplicates": 0, "tombstoned": 0,
                   "reorg_blocks_detected": 0, "reorg_events_tombstoned": 0,
                   "pages_committed": 0, "checkpoints_advanced": 0}
        for mapping in mappings:
            self._validate_mapping(mapping)
            if mapping.mapping_id not in self.start_blocks or mapping.mapping_id not in self.monitored_addresses:
                raise ValueError(f"verified Bitcoin mapping {mapping.mapping_id} has no explicit seed/start block")
            summary["mappings"] += 1
            tip = self._retry(self.provider.fetch_bitcoin_tip_height)
            if isinstance(tip, bool) or not isinstance(tip, int) or tip <= 0:
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Bitcoin tip height is invalid")
            # A transaction at height H has tip-H+1 confirmations.
            safe_height = tip - self.minimum_confirmations + 1
            for address in self.monitored_addresses[mapping.mapping_id]:
                summary["addresses"] += 1
                cursor_key, scope = self._cursor_key(address), f"address:{address}"
                initial = self.start_blocks[mapping.mapping_id]
                cursor = self.ingestion_store.get_checkpoint(cursor_key)
                if cursor is None:
                    next_block = initial
                    page_number = 1
                    range_start = range_end = None
                else:
                    if not isinstance(cursor, dict) or isinstance(cursor.get("next_block"), bool) or not isinstance(cursor.get("next_block"), int):
                        raise ValueError("stored Bitcoin checkpoint is malformed")
                    next_block = cursor["next_block"]
                    range_start, range_end = cursor.get("from_block"), cursor.get("to_block")
                    page_number = cursor.get("page", 1)
                    if range_start is not None and (
                        isinstance(range_start, bool) or not isinstance(range_start, int)
                        or isinstance(range_end, bool) or not isinstance(range_end, int)
                        or not range_start <= range_end or isinstance(page_number, bool)
                        or not isinstance(page_number, int) or page_number < 1
                    ):
                        raise ValueError("stored Bitcoin page checkpoint is malformed")
                reorg_tombstones, rewind, reorg_blocks = self._reconcile(address, next_block, initial)
                summary["reorg_events_tombstoned"] += reorg_tombstones
                summary["reorg_blocks_detected"] += reorg_blocks
                if rewind is not None:
                    next_block, range_start, range_end, page_number = rewind, None, None, 1
                    self.ingestion_store.commit_page(cursor_key, {
                        "next_block": rewind, "reorg_rewind": True,
                    }, ())
                if range_start is None:
                    if next_block > safe_height:
                        continue
                    range_start = next_block
                    range_end = min(safe_height, range_start + self.max_blocks_per_run - 1)
                    page_number = 1
                headers = {height: self._header(height) for height in range(range_start, range_end + 1)}
                # A page-level restart may resume inside a range that itself was
                # reorganized. Reconcile its already-journaled headers before
                # trusting the saved page number; if any changed, replay page 1.
                active_range_changed = False
                for height, header in headers.items():
                    prior_hash = self.ingestion_store.get_block_hash(
                        "bitcoin-mainnet", "alchemy", scope, height)
                    if prior_hash is not None and prior_hash.lower() != header["hash"].lower():
                        summary["reorg_blocks_detected"] += 1
                        summary["reorg_events_tombstoned"] += self.ingestion_store.reconcile_block(
                            "bitcoin-mainnet", height, header["hash"].lower(),
                            provider="alchemy", scope=scope)
                        active_range_changed = True
                if active_range_changed:
                    page_number = 1
                expected_total_pages = cursor.get("total_pages") if (
                    cursor is not None and range_start is not None and page_number > 1
                    and not active_range_changed
                ) else None
                page = self._retry(lambda: self.provider.fetch_bitcoin_address_transactions(
                    address, page_number, self.page_size, range_start, range_end))
                # Fixed block bounds prevent new-tip pagination drift. If the
                # provider's page count nevertheless changes (reindexing), do
                # not continue from a stale offset: restart this fixed range.
                if (expected_total_pages is not None
                        and getattr(page, "total_pages", None) != expected_total_pages):
                    page_number = 1
                    page = self._retry(lambda: self.provider.fetch_bitcoin_address_transactions(
                        address, page_number, self.page_size, range_start, range_end))
                records = getattr(page, "records", None)
                total_pages = getattr(page, "total_pages", None)
                if (not isinstance(records, tuple) or getattr(page, "provider", None) != "alchemy"
                        or getattr(page, "network_id", None) != "bitcoin-mainnet"
                        or getattr(page, "scope", None) != address
                        or getattr(page, "page_number", None) != page_number
                        or isinstance(total_pages, bool) or not isinstance(total_pages, int)
                        or total_pages < 0 or page_number > max(total_pages, 1)
                        or (getattr(page, "next_cursor", None) is not None) != (page_number < total_pages)
                        or (page_number < total_pages and getattr(page, "next_cursor", None) != page_number + 1)):
                    raise ProviderTransportError("INVALID_PROVIDER_DATA", "Bitcoin address-history page is malformed or outside the requested address/page scope")
                normalized = []
                observed = self.clock()
                if observed.tzinfo is None or observed.utcoffset() is None:
                    raise ValueError("worker clock must return a timezone-aware datetime")
                observed_at = observed.astimezone(timezone.utc).isoformat()
                for record in records:
                    if not isinstance(record, BitcoinAddressTransaction):
                        raise ProviderTransportError("INVALID_PROVIDER_DATA", "Bitcoin address-history page contains a malformed transaction")
                    if (record.block_height is None or not range_start <= record.block_height <= range_end
                            or record.confirmations < self.minimum_confirmations):
                        raise ProviderTransportError("BITCOIN_CONFIRMATIONS_INSUFFICIENT", "Bitcoin page contains a transaction outside the fixed range or below the configured confirmation threshold")
                    header = headers[record.block_height]
                    detail = self._retry(lambda txid=record.txid: self.provider.fetch_bitcoin_transaction(txid))
                    block_time = datetime.fromtimestamp(header["timestamp"], timezone.utc).isoformat()
                    normalized.extend(normalize_bitcoin_transaction_outputs(
                        record, detail, asset_id=mapping.asset_id, mapping_id=mapping.mapping_id,
                        monitored_address=address, canonical_block_hash=header["hash"],
                        block_time=block_time, observed_at=observed_at,
                        minimum_confirmations=self.minimum_confirmations))
                has_more = page_number < total_pages
                next_cursor = {
                    "mapping_id": mapping.mapping_id, "network_id": "bitcoin-mainnet",
                    "address": address,
                    "from_block": range_start if has_more else None,
                    "to_block": range_end if has_more else None,
                    "page": page_number + 1 if has_more else 1,
                    "total_pages": total_pages, "next_block": range_start if has_more else range_end + 1,
                    "minimum_confirmations": self.minimum_confirmations,
                }
                blocks = tuple({
                    "network_id": "bitcoin-mainnet", "provider": "alchemy", "scope": scope,
                    "block_number": height, "block_hash": header["hash"].lower(),
                    "block_time": datetime.fromtimestamp(header["timestamp"], timezone.utc).isoformat(),
                } for height, header in headers.items())
                committed = self.ingestion_store.commit_page(
                    cursor_key, next_cursor, normalized, allow_recanonicalized=True,
                    canonical_blocks=blocks)
                summary["events_inserted"] += committed["inserted"]
                summary["duplicates"] += committed["duplicates"]
                summary["tombstoned"] += committed["tombstoned"]
                summary["blocks_scanned"] += len(headers)
                summary["pages_committed"] += 1
                summary["checkpoints_advanced"] += 1
        return summary
