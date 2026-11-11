"""Bounded finalized Solana address-history ingestion for verified SPL token mappings."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable

from .onchain import OnChainAssetMapping, OnChainStore
from .onchain_ingestion import (
    OnChainIngestionStore, normalize_solana_token_transfer_instructions,
    _solana_base58_decode,
)
from .onchain_providers import ProviderTransportError, SolanaAddressTransaction

_RETRYABLE = {"TIMEOUT", "NETWORK_ERROR", "RATE_LIMITED"}


class SolanaAddressIngestionWorker:
    def __init__(
        self, provider, mapping_store: OnChainStore,
        ingestion_store: OnChainIngestionStore, *,
        monitored_addresses: dict[str, tuple[str, ...]],
        start_slots: dict[str, int],
        max_slots_per_run: int,
        page_size: int,
        reorg_lookback_slots: int,
        retry_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        if not isinstance(mapping_store, OnChainStore) or not isinstance(ingestion_store, OnChainIngestionStore):
            raise ValueError("worker requires existing mapping and ingestion stores")
        if not isinstance(monitored_addresses, dict) or not monitored_addresses:
            raise ValueError("explicit monitored Solana address seeds are required")
        if not isinstance(start_slots, dict) or set(start_slots) != set(monitored_addresses):
            raise ValueError("every monitored Solana mapping requires one explicit start slot")
        if isinstance(max_slots_per_run, bool) or not isinstance(max_slots_per_run, int) or not 1 <= max_slots_per_run <= 1000:
            raise ValueError("max_slots_per_run must be between 1 and 1000")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
            raise ValueError("full Solana transaction page_size must be between 1 and 100")
        if isinstance(reorg_lookback_slots, bool) or not isinstance(reorg_lookback_slots, int) or not 0 <= reorg_lookback_slots <= 10000:
            raise ValueError("reorg_lookback_slots must be between 0 and 10000")
        if isinstance(retry_attempts, bool) or not isinstance(retry_attempts, int) or not 1 <= retry_attempts <= 5:
            raise ValueError("retry_attempts must be between 1 and 5")
        for mapping_id, addresses in monitored_addresses.items():
            if (not isinstance(mapping_id, str) or not mapping_id.strip()
                    or not isinstance(addresses, (tuple, list)) or not addresses
                    or any(not isinstance(address, str) or not address.strip()
                           or len(_solana_base58_decode(address)) != 32 for address in addresses)
                    or len(set(addresses)) != len(addresses)):
                raise ValueError("each mapping requires unique explicit non-empty monitored address seeds")
        for mapping_id, slot in start_slots.items():
            if not isinstance(mapping_id, str) or not mapping_id.strip() or isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
                raise ValueError("Solana mapping start slots are invalid")
        self.provider, self.mapping_store, self.ingestion_store = provider, mapping_store, ingestion_store
        self.monitored_addresses = {key: tuple(value) for key, value in monitored_addresses.items()}
        self.start_slots = dict(start_slots)
        self.max_slots_per_run, self.page_size = max_slots_per_run, page_size
        self.reorg_lookback_slots, self.retry_attempts = reorg_lookback_slots, retry_attempts
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
        if (mapping.network_id != "solana-mainnet" or mapping.network_family != "SOLANA"
                or mapping.chain_id != "mainnet-beta" or mapping.mapping_status != "VERIFIED"
                or mapping.representation not in {"TOKEN", "WRAPPED", "BRIDGED"}
                or not isinstance(mapping.contract_address, str) or not mapping.contract_address
                or mapping.token_standard != "SPL_TOKEN"
                or isinstance(mapping.decimals, bool) or not isinstance(mapping.decimals, int)
                or not 0 <= mapping.decimals <= 36):
            raise ValueError("Solana worker requires a verified SPL token mint mapping")

    @staticmethod
    def _cursor_key(address: str, mapping_id: str) -> str:
        return f"alchemy:solana-mainnet:address:{address}:mapping:{mapping_id}"

    @staticmethod
    def _scope(address: str, mapping_id: str) -> str:
        return f"address:{address}:mapping:{mapping_id}"

    def _slot_state(self, start_slot: int, end_slot: int) -> dict[int, dict]:
        produced = self._retry(lambda: self.provider.fetch_solana_produced_slots(start_slot, end_slot))
        if (not isinstance(produced, tuple) or tuple(sorted(set(produced))) != produced
                or any(isinstance(slot, bool) or not isinstance(slot, int)
                       or not start_slot <= slot <= end_slot for slot in produced)):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Solana produced-slot range is malformed")
        states = {
            slot: {"produced": False, "block_hash": None, "block_time": None}
            for slot in range(start_slot, end_slot + 1)
        }
        for slot in produced:
            header = self._retry(lambda slot=slot: self.provider.fetch_solana_block_header(slot))
            if (not isinstance(header, dict) or header.get("number") != slot
                    or not isinstance(header.get("hash"), str) or len(_solana_base58_decode(header["hash"])) != 32
                    or isinstance(header.get("timestamp"), bool)
                    or not isinstance(header.get("timestamp"), int) or header["timestamp"] <= 0
                    or (header.get("parent_slot") is not None and (
                        isinstance(header.get("parent_slot"), bool)
                        or not isinstance(header.get("parent_slot"), int)
                        or header["parent_slot"] >= slot))
                    or header.get("finality_reference") != "commitment=finalized"):
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Solana finalized block header is malformed or not finalized")
            block_time = datetime.fromtimestamp(header["timestamp"], timezone.utc).isoformat()
            states[slot] = {
                "produced": True, "block_hash": header["hash"], "block_time": block_time,
            }
        return states

    def _journal_payload(self, scope: str, states: dict[int, dict]) -> tuple[dict, ...]:
        return tuple({
            "network_id": "solana-mainnet", "provider": "alchemy", "scope": scope,
            "slot": slot, **state,
        } for slot, state in states.items())

    def _reconcile(self, scope: str, start_slot: int, end_slot: int):
        stored = self.ingestion_store.get_solana_slot_journal(
            "solana-mainnet", "alchemy", scope, start_slot, end_slot)
        if not stored:
            return 0, None, 0, None
        current = self._slot_state(start_slot, end_slot)
        tombstoned = changed = 0
        earliest = None
        for slot, prior in stored.items():
            fresh = current[slot]
            if prior == fresh:
                continue
            changed += 1
            canonical_hash = fresh["block_hash"] if fresh["produced"] else "SKIPPED"
            tombstoned += self.ingestion_store.reconcile_block(
                "solana-mainnet", slot, canonical_hash, provider="alchemy", scope=scope)
            earliest = slot if earliest is None else min(earliest, slot)
        return tombstoned, earliest, changed, current

    def run_once(self) -> dict:
        mappings = self.mapping_store.list_verified_mappings("solana-mainnet")
        summary = {"mappings": 0, "mappings_skipped": 0, "addresses": 0, "slots_scanned": 0,
                   "events_inserted": 0, "duplicates": 0, "tombstoned": 0,
                   "reorg_slots_detected": 0, "reorg_events_tombstoned": 0,
                   "pages_committed": 0, "checkpoints_advanced": 0}
        for mapping in mappings:
            # Native SOL and Token-2022 extension mints are deliberately outside
            # this first token-only decoder; never silently mislabel them.
            if mapping.representation == "NATIVE" or mapping.token_standard == "TOKEN_2022":
                summary["mappings_skipped"] += 1
                continue
            self._validate_mapping(mapping)
            if mapping.mapping_id not in self.start_slots or mapping.mapping_id not in self.monitored_addresses:
                raise ValueError(f"verified Solana mapping {mapping.mapping_id} has no explicit seed/start slot")
            summary["mappings"] += 1
            finalized_slot = self._retry(self.provider.fetch_solana_finalized_slot)
            if isinstance(finalized_slot, bool) or not isinstance(finalized_slot, int) or finalized_slot <= 0:
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Solana finalized slot is invalid")
            initial_slot = self.start_slots[mapping.mapping_id]
            for address in self.monitored_addresses[mapping.mapping_id]:
                summary["addresses"] += 1
                cursor_key, scope = self._cursor_key(address, mapping.mapping_id), self._scope(address, mapping.mapping_id)
                cursor = self.ingestion_store.get_checkpoint(cursor_key)
                if cursor is None:
                    next_slot, range_start, range_end, pagination_token = initial_slot, None, None, None
                    seen_tokens, last_position = [], None
                else:
                    if (not isinstance(cursor, dict) or isinstance(cursor.get("next_slot"), bool)
                            or not isinstance(cursor.get("next_slot"), int)):
                        raise ValueError("stored Solana checkpoint is malformed")
                    next_slot = cursor["next_slot"]
                    range_start, range_end = cursor.get("from_slot"), cursor.get("to_slot")
                    pagination_token = cursor.get("pagination_token")
                    seen_tokens = cursor.get("seen_tokens", [])
                    last_position = cursor.get("last_position")
                    if (not isinstance(seen_tokens, list)
                            or any(not isinstance(token, str) or not token for token in seen_tokens)
                            or len(set(seen_tokens)) != len(seen_tokens)):
                        raise ValueError("stored Solana pagination-token history is malformed")
                    if last_position is not None and (
                        not isinstance(last_position, list) or len(last_position) != 2
                        or any(isinstance(value, bool) or not isinstance(value, int) or value < 0
                               for value in last_position)
                    ):
                        raise ValueError("stored Solana transaction-position checkpoint is malformed")
                    if range_start is not None and (
                        isinstance(range_start, bool) or not isinstance(range_start, int)
                        or isinstance(range_end, bool) or not isinstance(range_end, int)
                        or range_start > range_end
                        or (pagination_token is not None and not isinstance(pagination_token, str))
                    ):
                        raise ValueError("stored Solana active range checkpoint is malformed")

                if self.reorg_lookback_slots and next_slot > initial_slot:
                    lookback_start = max(initial_slot, next_slot - self.reorg_lookback_slots)
                    tombstones, rewind, changed, fresh = self._reconcile(scope, lookback_start, next_slot - 1)
                    summary["reorg_events_tombstoned"] += tombstones
                    summary["reorg_slots_detected"] += changed
                    if rewind is not None:
                        self.ingestion_store.commit_page(
                            cursor_key, {"next_slot": rewind, "from_slot": None,
                                         "to_slot": None, "pagination_token": None},
                            (), canonical_slots=self._journal_payload(scope, fresh))
                        next_slot, range_start, range_end, pagination_token = rewind, None, None, None
                        seen_tokens, last_position = [], None

                if range_start is not None:
                    active = self._slot_state(range_start, range_end)
                    journal = self.ingestion_store.get_solana_slot_journal(
                        "solana-mainnet", "alchemy", scope, range_start, range_end)
                    changed_slots = [
                        slot for slot, prior in journal.items()
                        if prior != active[slot]
                    ]
                    if changed_slots:
                        for slot in changed_slots:
                            state = active[slot]
                            canonical_hash = state["block_hash"] if state["produced"] else "SKIPPED"
                            summary["reorg_events_tombstoned"] += self.ingestion_store.reconcile_block(
                                "solana-mainnet", slot, canonical_hash,
                                provider="alchemy", scope=scope)
                        summary["reorg_slots_detected"] += len(changed_slots)
                        next_slot = min(changed_slots)
                        range_start, range_end, pagination_token = None, None, None
                        seen_tokens, last_position = [], None
                else:
                    active = None

                if range_start is None:
                    if next_slot > finalized_slot:
                        continue
                    range_start = next_slot
                    range_end = min(finalized_slot, range_start + self.max_slots_per_run - 1)
                    pagination_token = None
                    seen_tokens, last_position = [], None
                    active = self._slot_state(range_start, range_end)
                elif active is None:
                    active = self._slot_state(range_start, range_end)

                page = self._retry(lambda: self.provider.fetch_solana_address_transactions(
                    address, pagination_token, self.page_size, range_start, range_end))
                if (getattr(page, "provider", None) != "alchemy"
                        or getattr(page, "network_id", None) != "solana-mainnet"
                        or getattr(page, "scope", None) != address
                        or getattr(page, "finality_reference", None) != "commitment=finalized"
                        or not isinstance(getattr(page, "records", None), tuple)
                        or (getattr(page, "next_cursor", None) is not None
                            and (not isinstance(page.next_cursor, str) or not page.next_cursor.strip()))):
                    raise ProviderTransportError("INVALID_PROVIDER_DATA", "Solana address-history page is malformed, unscoped or not finalized")
                observed = self.clock()
                if observed.tzinfo is None or observed.utcoffset() is None:
                    raise ValueError("worker clock must return timezone-aware datetime")
                observed_at = observed.astimezone(timezone.utc).isoformat()
                events = []
                positions = []
                for record in page.records:
                    if (not isinstance(record, SolanaAddressTransaction)
                            or isinstance(record.slot, bool) or not isinstance(record.slot, int)
                            or not range_start <= record.slot <= range_end
                            or isinstance(record.transaction_index, bool)
                            or not isinstance(record.transaction_index, int)
                            or record.transaction_index < 0):
                        raise ProviderTransportError("INVALID_PROVIDER_DATA", "Solana page record is outside the fixed slot range or lacks transaction position")
                    positions.append((record.slot, record.transaction_index))
                    header = active.get(record.slot)
                    if header is None or not header["produced"]:
                        raise ProviderTransportError("SOLANA_BLOCK_EVIDENCE_MISSING", "Solana transaction slot has no independently verified finalized block")
                    events.extend(normalize_solana_token_transfer_instructions(
                        record, asset_id=mapping.asset_id, mapping_id=mapping.mapping_id,
                        mint=mapping.contract_address, token_standard=mapping.token_standard,
                        decimals=mapping.decimals, monitored_address=address,
                        canonical_block_hash=header["block_hash"],
                        canonical_block_time=header["block_time"], observed_at=observed_at,
                    ))
                if len(set(positions)) != len(positions):
                    raise ProviderTransportError("INVALID_PROVIDER_DATA", "Solana page contains duplicate slot/transaction-index positions")
                if positions != sorted(positions, reverse=True):
                    raise ProviderTransportError("INVALID_PROVIDER_DATA", "Solana page transactions are not in descending slot/transaction-index order")
                if last_position is not None and positions and positions[0] >= tuple(last_position):
                    raise ProviderTransportError("INVALID_PROVIDER_DATA", "Solana page cursor repeated or moved backward in transaction history")
                has_more = page.next_cursor is not None
                next_seen_tokens = list(seen_tokens)
                if has_more:
                    if (page.next_cursor == pagination_token or page.next_cursor in next_seen_tokens
                            or len(next_seen_tokens) >= 10000):
                        raise ProviderTransportError("INVALID_PROVIDER_DATA", "Solana provider repeated or exceeded the bounded opaque pagination cursor history")
                    next_seen_tokens.append(page.next_cursor)
                else:
                    next_seen_tokens = []
                next_last_position = list(positions[-1]) if positions else last_position
                next_cursor = {
                    "mapping_id": mapping.mapping_id, "network_id": "solana-mainnet",
                    "address": address, "from_slot": range_start if has_more else None,
                    "to_slot": range_end if has_more else None,
                    "pagination_token": page.next_cursor if has_more else None,
                    "seen_tokens": next_seen_tokens,
                    "last_position": next_last_position if has_more else None,
                    "next_slot": range_start if has_more else range_end + 1,
                    "finality_reference": "commitment=finalized",
                }
                canonical_slots = self._journal_payload(scope, active)
                canonical_blocks = tuple({
                    "network_id": "solana-mainnet", "provider": "alchemy", "scope": scope,
                    "block_number": slot, "block_hash": state["block_hash"],
                    "block_time": state["block_time"],
                } for slot, state in active.items() if state["produced"])
                committed = self.ingestion_store.commit_page(
                    cursor_key, next_cursor, events, allow_recanonicalized=True,
                    canonical_blocks=canonical_blocks, canonical_slots=canonical_slots)
                summary["events_inserted"] += committed["inserted"]
                summary["duplicates"] += committed["duplicates"]
                summary["tombstoned"] += committed["tombstoned"]
                summary["slots_scanned"] += len(active)
                summary["pages_committed"] += 1
                summary["checkpoints_advanced"] += 1
        return summary
