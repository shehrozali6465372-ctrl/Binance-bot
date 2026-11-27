"""Bounded finalized Solana address-history ingestion for verified SPL token mappings."""
from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from .onchain import OnChainAssetMapping
from .onchain_ingestion import (
    OnChainFinalitySnapshot, normalize_solana_token_transfer_instructions,
)
from .onchain_providers import (
    MAX_DATETIME_UNIX_TIMESTAMP,
    ProviderTransportError, SolanaAddressTransaction, retry_provider_operation,
    _capture_provider_run_receipts, drain_provider_run_receipts,
    _solana_base58_decode, _is_base58_signature, SOLANA_MAX_PERSISTABLE_SLOT,
    include_provider_receipts_in_current_scope,
)
from .onchain_protocols import (
    OnChainIngestionStoreProtocol, OnChainMappingStoreProtocol,
    require_ingestion_store, require_mapping_store,
)

_RETRYABLE = {"TIMEOUT", "NETWORK_ERROR", "RATE_LIMITED"}


class SolanaAddressIngestionWorker:
    def __init__(
        self, provider, mapping_store: OnChainMappingStoreProtocol,
        ingestion_store: OnChainIngestionStoreProtocol, *,
        monitored_addresses: dict[str, tuple[str, ...]],
        start_slots: dict[str, int],
        max_slots_per_run: int,
        page_size: int,
        reorg_lookback_slots: int,
        retry_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        require_mapping_store(mapping_store)
        require_ingestion_store(ingestion_store)
        if not callable(getattr(ingestion_store, "list_pending_solana_quarantine", None)):
            raise ValueError("Solana ingestion store must support durable quarantine recovery")
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
            if not isinstance(mapping_id, str) or not mapping_id.strip() or isinstance(slot, bool) or not isinstance(slot, int) or not 0 <= slot <= SOLANA_MAX_PERSISTABLE_SLOT:
                raise ValueError("Solana mapping start slots are invalid")
        self.provider, self.mapping_store, self.ingestion_store = provider, mapping_store, ingestion_store
        self.monitored_addresses = {key: tuple(value) for key, value in monitored_addresses.items()}
        self.start_slots = dict(start_slots)
        self.max_slots_per_run, self.page_size = max_slots_per_run, page_size
        self.reorg_lookback_slots, self.retry_attempts = reorg_lookback_slots, retry_attempts
        self.sleep, self.clock = sleep, clock

    def _retry(self, operation):
        return retry_provider_operation(
            operation, attempts=self.retry_attempts, sleep=self.sleep,
        )

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
        if (isinstance(start_slot, bool) or not isinstance(start_slot, int)
                or isinstance(end_slot, bool) or not isinstance(end_slot, int)
                or not 0 <= start_slot <= end_slot <= SOLANA_MAX_PERSISTABLE_SLOT):
            raise ValueError("Solana slot-state range must be a fixed UInt64 range")
        produced = self._retry(lambda: self.provider.fetch_solana_produced_slots(start_slot, end_slot))
        if (not isinstance(produced, tuple) or tuple(sorted(set(produced))) != produced
                or any(isinstance(slot, bool) or not isinstance(slot, int)
                       or not 0 <= slot <= SOLANA_MAX_PERSISTABLE_SLOT
                       or not start_slot <= slot <= end_slot for slot in produced)):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Solana produced-slot range is malformed")
        states = {
            slot: {"produced": False, "block_hash": None, "block_time": None,
                   "transaction_signatures": ()}
            for slot in range(start_slot, end_slot + 1)
        }
        external_parent_hashes = {}
        previous_produced_slot = None
        for slot in produced:
            header = self._retry(lambda slot=slot: self.provider.fetch_solana_block_header(slot))
            parent_slot = header.get("parent_slot") if isinstance(header, dict) else None
            previous_block_hash = header.get("previous_block_hash") if isinstance(header, dict) else None
            transaction_signatures = header.get("transaction_signatures") if isinstance(header, dict) else None
            if (not isinstance(header, dict)
                    or not isinstance(transaction_signatures, tuple)
                    or any(not _is_base58_signature(signature) for signature in transaction_signatures)
                    or len(set(transaction_signatures)) != len(transaction_signatures)
                    or isinstance(header.get("number"), bool)
                    or header.get("number") != slot
                    or not isinstance(header.get("hash"), str) or len(_solana_base58_decode(header["hash"])) != 32
                    or not isinstance(previous_block_hash, str)
                    or len(_solana_base58_decode(previous_block_hash)) != 32
                    or isinstance(parent_slot, bool) or not isinstance(parent_slot, int)
                    or not 0 <= parent_slot <= SOLANA_MAX_PERSISTABLE_SLOT or parent_slot >= slot
                    or (header.get("timestamp") is not None and (
                        isinstance(header.get("timestamp"), bool)
                        or not isinstance(header.get("timestamp"), int)
                        or not 0 < header["timestamp"] <= MAX_DATETIME_UNIX_TIMESTAMP
                    ))
                    or header.get("finality_reference") != "commitment=finalized"):
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Solana finalized block header or parent linkage is malformed/not finalized")
            parent_state = states.get(parent_slot)
            if parent_slot >= start_slot and (
                    parent_state is None or not parent_state["produced"]):
                raise ProviderTransportError("SOLANA_PARENT_SLOT_MISSING", "Solana finalized block parent slot is missing from the produced-slot range")
            if (previous_produced_slot is not None
                    and parent_slot != previous_produced_slot):
                raise ProviderTransportError(
                    "SOLANA_PARENT_SLOT_MISMATCH",
                    "Solana finalized block parentSlot does not identify the immediately preceding produced block",
                )
            if parent_state is not None and parent_state["block_hash"] != previous_block_hash:
                raise ProviderTransportError("SOLANA_PARENT_HASH_MISMATCH", "Solana finalized block previousBlockhash does not match its produced parent slot")
            if parent_state is None and parent_slot < start_slot:
                if parent_slot not in external_parent_hashes:
                    parent_header = self._retry(
                        lambda parent_slot=parent_slot: self.provider.fetch_solana_block_header(parent_slot))
                    if (not isinstance(parent_header, dict)
                            or isinstance(parent_header.get("number"), bool)
                            or parent_header.get("number") != parent_slot
                            or not isinstance(parent_header.get("hash"), str)
                            or len(_solana_base58_decode(parent_header["hash"])) != 32):
                        raise ProviderTransportError(
                            "SOLANA_PARENT_SLOT_MISSING",
                            "Solana finalized block's parent slot has no valid independently fetched block header",
                        )
                    external_parent_hashes[parent_slot] = parent_header["hash"]
                if external_parent_hashes[parent_slot] != previous_block_hash:
                    raise ProviderTransportError(
                        "SOLANA_PARENT_HASH_MISMATCH",
                        "Solana finalized block previousBlockhash does not match its external parent slot hash",
                    )
            previous_produced_slot = slot
            block_time = (
                datetime.fromtimestamp(header["timestamp"], timezone.utc).isoformat()
                if header["timestamp"] is not None else None
            )
            states[slot] = {
                "produced": True, "block_hash": header["hash"], "block_time": block_time,
                "transaction_signatures": transaction_signatures,
            }
        return states

    @staticmethod
    def _journal_state(state: dict) -> dict:
        return {key: state[key] for key in ("produced", "block_hash", "block_time")}

    def _journal_payload(self, scope: str, states: dict[int, dict]) -> tuple[dict, ...]:
        return tuple({
            "network_id": "solana-mainnet", "provider": "alchemy", "scope": scope,
            "slot": slot, **self._journal_state(state),
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
            fresh_state = self._journal_state(fresh)
            if prior == fresh_state:
                continue
            if (prior.get("produced") and fresh_state.get("produced")
                    and prior.get("block_hash") == fresh_state.get("block_hash")
                    and prior.get("block_time") is None and fresh_state.get("block_time") is not None):
                continue
            if (prior.get("produced") and fresh_state.get("produced")
                    and prior.get("block_hash") == fresh_state.get("block_hash")
                    and prior.get("block_time") is not None and fresh_state.get("block_time") is None):
                raise ProviderTransportError(
                    "SOLANA_BLOCK_TIME_REGRESSION",
                    "Solana provider regressed a previously known canonical slot time to unknown",
                )
            changed += 1
            canonical_hash = fresh["block_hash"] if fresh["produced"] else "SKIPPED"
            tombstoned += self.ingestion_store.reconcile_block(
                "solana-mainnet", slot, canonical_hash, provider="alchemy", scope=scope)
            earliest = slot if earliest is None else min(earliest, slot)
        return tombstoned, earliest, changed, current

    def _replay_pending_quarantine(self, mapping, address: str, scope: str,
                                   cursor_key: str, cursor, summary: dict) -> None:
        pending = self.ingestion_store.list_pending_solana_quarantine(
            "solana-mainnet", "alchemy", scope, limit=self.page_size)
        for item in pending:
            states = self._slot_state(item["slot"], item["slot"])
            state = states[item["slot"]]
            # Block identity is authoritative even while timestamp enrichment is
            # pending. Check it first so a reorg cannot turn an old quarantine
            # record into a later identity-collision deadlock.
            if state["block_hash"] != item["block_hash"]:
                drain_provider_run_receipts()
                raise ProviderTransportError(
                    "SOLANA_QUARANTINE_BLOCK_HASH_MISMATCH",
                    "quarantined transaction no longer matches the finalized slot hash",
                )
            if state["block_time"] is None:
                drain_provider_run_receipts()
                continue
            signatures = state["transaction_signatures"]
            index = item["transaction_index"]
            if index >= len(signatures) or signatures[index] != item["signature"]:
                drain_provider_run_receipts()
                raise ProviderTransportError(
                    "SOLANA_QUARANTINE_TRANSACTION_MISMATCH",
                    "quarantined transaction signature no longer matches its finalized slot position",
                )
            payload = item["payload"]
            record = SolanaAddressTransaction(
                item["signature"], item["slot"], payload.get("block_time"),
                payload["raw"], item["transaction_index"],
            )
            observed_at = payload.get("observed_at")
            if not isinstance(observed_at, str):
                raise ValueError("quarantined Solana transaction is missing its original observation timestamp")
            events = normalize_solana_token_transfer_instructions(
                record, asset_id=mapping.asset_id, mapping_id=mapping.mapping_id,
                mint=mapping.contract_address, token_standard=mapping.token_standard,
                decimals=mapping.decimals, monitored_address=address,
                canonical_block_hash=state["block_hash"],
                canonical_block_time=state["block_time"], observed_at=observed_at,
            )
            events = tuple(replace(event, finality_snapshot=OnChainFinalitySnapshot(
                version=1, network_id="solana-mainnet", status="FINALIZED",
                reference="commitment=finalized",
            )) for event in events)
            canonical_block = ({
                "network_id": "solana-mainnet", "provider": "alchemy", "scope": scope,
                "block_number": item["slot"], "block_hash": state["block_hash"],
                "block_time": state["block_time"],
            },)
            committed = self.ingestion_store.commit_page(
                cursor_key, cursor, events, allow_recanonicalized=True,
                canonical_blocks=canonical_block,
                canonical_slots=self._journal_payload(scope, states),
                expected_cursor=cursor,
                scope_identity=("solana-mainnet", "alchemy", scope),
                provider_receipts=drain_provider_run_receipts(),
                solana_quarantine_replayed=(item["signature"],),
            )
            summary["events_inserted"] += committed["inserted"]
            summary["duplicates"] += committed["duplicates"]
            summary["tombstoned"] += committed["tombstoned"]
            summary["quarantine_replayed"] += 1
            summary["pages_committed"] += 1

    def _finalize_page_acceptances(self, summary: dict) -> None:
        result = self.mapping_store.engine.sign_pending_ingestion_pages(self.ingestion_store)
        summary["page_acceptances_signed"] = result["signed"]
        summary["page_acceptances_pending"] = result["pending"]
        summary["page_acceptances_rejected"] = result["rejected"]

    @_capture_provider_run_receipts
    def run_once(self) -> dict:
        mappings = self.mapping_store.list_verified_mappings("solana-mainnet")
        summary = {"mappings": 0, "mappings_skipped": 0, "addresses": 0, "slots_scanned": 0,
                   "events_inserted": 0, "duplicates": 0, "tombstoned": 0,
                   "reorg_slots_detected": 0, "reorg_events_tombstoned": 0,
                   "quarantined_transactions": 0, "quarantine_replayed": 0,
                   "pages_committed": 0, "checkpoints_advanced": 0}
        summary.update({"page_acceptances_signed": 0, "page_acceptances_pending": 0,
                        "page_acceptances_rejected": 0})
        for mapping in mappings:
            drain_provider_run_receipts()  # discard uncommitted evidence from prior mapping
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
            finalized_slot_receipts = drain_provider_run_receipts()
            if (isinstance(finalized_slot, bool) or not isinstance(finalized_slot, int)
                    or not 1 <= finalized_slot <= SOLANA_MAX_PERSISTABLE_SLOT):
                raise ProviderTransportError("INVALID_PROVIDER_DATA", "Solana finalized slot is invalid")
            initial_slot = self.start_slots[mapping.mapping_id]
            for address in self.monitored_addresses[mapping.mapping_id]:
                drain_provider_run_receipts()  # isolate the next address scope
                include_provider_receipts_in_current_scope(finalized_slot_receipts)
                summary["addresses"] += 1
                cursor_key, scope = self._cursor_key(address, mapping.mapping_id), self._scope(address, mapping.mapping_id)
                cursor = self.ingestion_store.get_checkpoint(cursor_key)
                if cursor is None:
                    next_slot, range_start, range_end, pagination_token = initial_slot, None, None, None
                    seen_tokens, last_position, exhausted = [], None, False
                else:
                    if (not isinstance(cursor, dict) or isinstance(cursor.get("next_slot"), bool)
                            or not isinstance(cursor.get("next_slot"), int)
                            or not 0 <= cursor["next_slot"] <= SOLANA_MAX_PERSISTABLE_SLOT):
                        raise ValueError("stored Solana checkpoint is malformed")
                    next_slot = cursor["next_slot"]
                    exhausted = cursor.get("exhausted", False)
                    if not isinstance(exhausted, bool):
                        raise ValueError("stored Solana exhaustion marker is malformed")
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
                        or not 0 <= range_start <= range_end <= SOLANA_MAX_PERSISTABLE_SLOT
                        or (pagination_token is not None and not isinstance(pagination_token, str))
                    ):
                        raise ValueError("stored Solana active range checkpoint is malformed")

                self._replay_pending_quarantine(
                    mapping, address, scope, cursor_key, cursor, summary,
                )
                # A pending-slot retry may have drained the current run's provider
                # receipts; retain the finalized-slot receipt for the next new page.
                include_provider_receipts_in_current_scope(finalized_slot_receipts)
                if exhausted:
                    if (next_slot != SOLANA_MAX_PERSISTABLE_SLOT or range_start is not None
                            or range_end is not None or pagination_token is not None):
                        raise ValueError("stored Solana terminal checkpoint is inconsistent")
                    continue
                if self.reorg_lookback_slots and next_slot > initial_slot:
                    lookback_start = max(initial_slot, next_slot - self.reorg_lookback_slots)
                    tombstones, rewind, changed, fresh = self._reconcile(scope, lookback_start, next_slot - 1)
                    summary["reorg_events_tombstoned"] += tombstones
                    summary["reorg_slots_detected"] += changed
                    if rewind is not None:
                        rewind_cursor = {"next_slot": rewind, "from_slot": None,
                                         "to_slot": None, "pagination_token": None}
                        self.ingestion_store.commit_page(
                            cursor_key, rewind_cursor, (), expected_cursor=cursor,
                            scope_identity=("solana-mainnet", "alchemy", scope),
                            allow_recanonicalized=True,
                            canonical_slots=self._journal_payload(scope, fresh))
                        cursor = rewind_cursor
                        next_slot, range_start, range_end, pagination_token = rewind, None, None, None
                        seen_tokens, last_position = [], None

                if range_start is not None:
                    active = self._slot_state(range_start, range_end)
                    journal = self.ingestion_store.get_solana_slot_journal(
                        "solana-mainnet", "alchemy", scope, range_start, range_end)
                    changed_slots = []
                    for slot, prior in journal.items():
                        fresh = self._journal_state(active[slot])
                        if prior == fresh:
                            continue
                        if (prior.get("produced") and fresh.get("produced")
                                and prior.get("block_hash") == fresh.get("block_hash")
                                and prior.get("block_time") is None and fresh.get("block_time") is not None):
                            continue
                        if (prior.get("produced") and fresh.get("produced")
                                and prior.get("block_hash") == fresh.get("block_hash")
                                and prior.get("block_time") is not None and fresh.get("block_time") is None):
                            raise ProviderTransportError(
                                "SOLANA_BLOCK_TIME_REGRESSION",
                                "Solana provider regressed a previously known canonical slot time to unknown",
                            )
                        changed_slots.append(slot)
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
                if len(page.records) > self.page_size:
                    raise ProviderTransportError(
                        "PAGE_LIMIT_EXCEEDED",
                        "Solana provider returned more transactions than the configured page size",
                    )
                observed = self.clock()
                if observed.tzinfo is None or observed.utcoffset() is None:
                    raise ValueError("worker clock must return timezone-aware datetime")
                observed_at = observed.astimezone(timezone.utc).isoformat()
                events = []
                positions = []
                quarantine_records = []
                for record in page.records:
                    raw_slot = record.raw.get("slot") if isinstance(record, SolanaAddressTransaction) and isinstance(record.raw, dict) else None
                    raw_block_time = record.raw.get("blockTime") if isinstance(record, SolanaAddressTransaction) and isinstance(record.raw, dict) else None
                    if (not isinstance(record, SolanaAddressTransaction)
                            or isinstance(record.slot, bool) or not isinstance(record.slot, int)
                            or isinstance(raw_slot, bool) or not isinstance(raw_slot, int)
                            or raw_slot != record.slot
                            or not 0 <= record.slot <= SOLANA_MAX_PERSISTABLE_SLOT
                            or not range_start <= record.slot <= range_end
                            or isinstance(record.transaction_index, bool)
                            or not isinstance(record.transaction_index, int)
                            or record.transaction_index < 0):
                        raise ProviderTransportError("SOLANA_SLOT_MISMATCH", "Solana raw transaction slot must be a non-boolean integer matching address-history slot")
                    if (record.block_time is not None
                            and (isinstance(record.block_time, bool)
                                 or not isinstance(record.block_time, int)
                                 or not 0 < record.block_time <= MAX_DATETIME_UNIX_TIMESTAMP)):
                        raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana address-history block time is invalid")
                    if "blockTime" in record.raw and (
                            (raw_block_time is not None and (
                                isinstance(raw_block_time, bool)
                                or not isinstance(raw_block_time, int)
                                or not 0 < raw_block_time <= MAX_DATETIME_UNIX_TIMESTAMP))
                            or raw_block_time != record.block_time):
                        raise ProviderTransportError(
                            "SOLANA_BLOCK_TIME_MISMATCH",
                            "Solana raw transaction blockTime does not match typed address-history block time",
                        )
                    positions.append((record.slot, record.transaction_index))
                    header = active.get(record.slot)
                    if header is None or not header["produced"]:
                        raise ProviderTransportError("SOLANA_BLOCK_EVIDENCE_MISSING", "Solana transaction slot has no independently verified finalized block")
                    if (record.transaction_index >= len(header["transaction_signatures"])
                            or header["transaction_signatures"][record.transaction_index] != record.signature):
                        raise ProviderTransportError(
                            "SOLANA_TRANSACTION_INDEX_MISMATCH",
                            "Solana address-history signature does not match the canonical block transaction at transactionIndex",
                        )
                    if header["block_time"] is None:
                        # Run the full normalizer as a validation-only preflight.
                        # The temporary time anchor is never persisted or emitted;
                        # canonical slot time remains unknown until replay.
                        validation_timestamp = (
                            record.block_time if record.block_time is not None
                            else int(observed.timestamp())
                        )
                        validation_block_time = datetime.fromtimestamp(
                            validation_timestamp, timezone.utc,
                        ).isoformat()
                        normalize_solana_token_transfer_instructions(
                            record, asset_id=mapping.asset_id, mapping_id=mapping.mapping_id,
                            mint=mapping.contract_address, token_standard=mapping.token_standard,
                            decimals=mapping.decimals, monitored_address=address,
                            canonical_block_hash=header["block_hash"],
                            canonical_block_time=validation_block_time, observed_at=observed_at,
                        )
                        quarantine_records.append({
                            "signature": record.signature, "slot": record.slot,
                            "transaction_index": record.transaction_index,
                            "block_hash": header["block_hash"],
                            "payload": {
                                "block_time": record.block_time, "raw": record.raw,
                                "observed_at": observed_at,
                            },
                        })
                        continue
                    events.extend(
                        replace(event, finality_snapshot=OnChainFinalitySnapshot(
                            version=1, network_id="solana-mainnet", status="FINALIZED",
                            reference=page.finality_reference,
                        ))
                        for event in normalize_solana_token_transfer_instructions(
                            record, asset_id=mapping.asset_id, mapping_id=mapping.mapping_id,
                            mint=mapping.contract_address, token_standard=mapping.token_standard,
                            decimals=mapping.decimals, monitored_address=address,
                            canonical_block_hash=header["block_hash"],
                            canonical_block_time=header["block_time"], observed_at=observed_at,
                        )
                    )
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
                exhausted = not has_more and range_end == SOLANA_MAX_PERSISTABLE_SLOT
                next_cursor = {
                    "mapping_id": mapping.mapping_id, "network_id": "solana-mainnet",
                    "address": address, "from_slot": range_start if has_more else None,
                    "to_slot": range_end if has_more else None,
                    "pagination_token": page.next_cursor if has_more else None,
                    "seen_tokens": next_seen_tokens,
                    "last_position": next_last_position if has_more else None,
                    "next_slot": (range_start if has_more else
                                  range_end if exhausted else range_end + 1),
                    "exhausted": exhausted,
                    "finality_reference": "commitment=finalized",
                    "finalized_slot": finalized_slot,
                }
                canonical_slots = self._journal_payload(scope, active)
                canonical_blocks = tuple({
                    "network_id": "solana-mainnet", "provider": "alchemy", "scope": scope,
                    "block_number": slot, "block_hash": state["block_hash"],
                    "block_time": state["block_time"],
                } for slot, state in active.items()
                    if state["produced"] and state["block_time"] is not None)
                committed = self.ingestion_store.commit_page(
                    cursor_key, next_cursor, events, allow_recanonicalized=True,
                    canonical_blocks=canonical_blocks, canonical_slots=canonical_slots,
                    expected_cursor=cursor,
                    scope_identity=("solana-mainnet", "alchemy", scope),
                    provider_receipts=drain_provider_run_receipts(),
                    solana_quarantine_records=quarantine_records)
                cursor = next_cursor
                summary["events_inserted"] += committed["inserted"]
                summary["duplicates"] += committed["duplicates"]
                summary["tombstoned"] += committed["tombstoned"]
                summary["quarantined_transactions"] += len(quarantine_records)
                summary["slots_scanned"] += len(active)
                summary["pages_committed"] += 1
                summary["checkpoints_advanced"] += 1
        self._finalize_page_acceptances(summary)
        return summary
