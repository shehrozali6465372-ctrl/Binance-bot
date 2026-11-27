"""Bounded, restart-safe ingestion of validated XRPL issued-currency Payments.

History is address-seeded and queried over fixed validated-ledger bounds. The
provider's marker is opaque and ephemeral; durable recovery is anchored to the
fixed ledger range and safe replay, never to parsing the marker.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from .onchain import OnChainAssetMapping
from .onchain_ingestion import OnChainFinalitySnapshot, normalize_xrpl_payment
from .onchain_providers import (
    ProviderTransportError, XrplAccountTransaction, is_valid_xrpl_classic_address,
    is_valid_xrpl_issued_currency_code,
    retry_provider_operation, _capture_provider_run_receipts,
    drain_provider_run_receipts, include_provider_receipts_in_current_scope,
)
from .onchain_protocols import (
    OnChainIngestionStoreProtocol, OnChainMappingStoreProtocol,
    require_ingestion_store, require_mapping_store,
)


_RETRYABLE = {"TIMEOUT", "NETWORK_ERROR", "RATE_LIMITED"}


class XrplIssuedCurrencyIngestionWorker:
    def __init__(
        self, provider, mapping_store: OnChainMappingStoreProtocol, ingestion_store: OnChainIngestionStoreProtocol, *,
        monitored_accounts: dict[str, tuple[str, ...]], start_ledgers: dict[str, int],
        max_ledgers_per_run: int, page_size: int = 200, max_pages_per_run: int = 10,
        reorg_lookback_ledgers: int = 20, retry_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        require_mapping_store(mapping_store)
        require_ingestion_store(ingestion_store)
        if not isinstance(monitored_accounts, dict) or not monitored_accounts:
            raise ValueError("explicit monitored XRPL account seeds are required")
        if not isinstance(start_ledgers, dict) or set(monitored_accounts) != set(start_ledgers):
            raise ValueError("explicit start ledger must cover every monitored mapping")
        for mapping_id, accounts in monitored_accounts.items():
            if (not isinstance(mapping_id, str) or not mapping_id.strip()
                    or not isinstance(accounts, (tuple, list)) or not accounts
                    or any(not is_valid_xrpl_classic_address(a) for a in accounts)
                    or len(set(accounts)) != len(accounts)):
                raise ValueError("each mapping requires unique checksum-valid classic XRPL account seeds")
        for mapping_id, ledger in start_ledgers.items():
            if (not isinstance(mapping_id, str) or isinstance(ledger, bool)
                    or not isinstance(ledger, int) or not 1 <= ledger <= 0xFFFFFFFF):
                raise ValueError("start ledger mapping IDs and indexes are invalid")
        if isinstance(max_ledgers_per_run, bool) or not isinstance(max_ledgers_per_run, int) or not 1 <= max_ledgers_per_run <= 100:
            raise ValueError("max_ledgers_per_run must be between 1 and 100")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        if isinstance(max_pages_per_run, bool) or not isinstance(max_pages_per_run, int) or not 1 <= max_pages_per_run <= 20:
            raise ValueError("max_pages_per_run must be between 1 and 20")
        if isinstance(reorg_lookback_ledgers, bool) or not isinstance(reorg_lookback_ledgers, int) or not 0 <= reorg_lookback_ledgers <= 1000:
            raise ValueError("reorg_lookback_ledgers must be between 0 and 1000")
        if isinstance(retry_attempts, bool) or not isinstance(retry_attempts, int) or not 1 <= retry_attempts <= 5:
            raise ValueError("retry_attempts must be between 1 and 5")
        self.provider, self.mapping_store, self.ingestion_store = provider, mapping_store, ingestion_store
        self.monitored_accounts = {key: tuple(value) for key, value in monitored_accounts.items()}
        self.start_ledgers = dict(start_ledgers)
        self.max_ledgers_per_run, self.page_size = max_ledgers_per_run, page_size
        self.max_pages_per_run, self.reorg_lookback_ledgers = max_pages_per_run, reorg_lookback_ledgers
        self.retry_attempts, self.sleep, self.clock = retry_attempts, sleep, clock

    def _retry(self, operation):
        return retry_provider_operation(
            operation, attempts=self.retry_attempts, sleep=self.sleep,
        )

    @staticmethod
    def _marker_key(marker, *, reason_code="INVALID_CHECKPOINT") -> str:
        try:
            return json.dumps(marker, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            raise ProviderTransportError(
                reason_code, "XRPL pagination marker is not finite JSON-compatible data",
            ) from None

    @staticmethod
    def _scope(mapping: OnChainAssetMapping, account: str) -> str:
        return f"account:{account}:mapping:{mapping.mapping_id}"

    @staticmethod
    def _cursor_key(account: str, mapping: OnChainAssetMapping) -> str:
        return f"chainstack:xrpl-mainnet:{account}:mapping:{mapping.mapping_id}"

    @staticmethod
    def _validate_mapping(mapping: OnChainAssetMapping):
        if (mapping.network_id != "xrpl-mainnet" or mapping.network_family != "XRPL"
                or mapping.chain_id != "xrpl-mainnet" or mapping.mapping_status != "VERIFIED"
                or mapping.representation != "TOKEN" or mapping.contract_address is not None
                or mapping.token_standard != "XRPL_ISSUED_CURRENCY"
                or isinstance(mapping.decimals, bool) or not isinstance(mapping.decimals, int)
                or not 0 <= mapping.decimals <= 36
                or not is_valid_xrpl_classic_address(mapping.issuer_address)
                or not is_valid_xrpl_issued_currency_code(mapping.issued_currency)):
            raise ValueError("worker requires a checksum-valid classic XRPL issuer address and verified issued-currency mapping")

    def _header(self, ledger_index: int) -> dict:
        header = self._retry(lambda: self.provider.fetch_ledger_header(ledger_index))
        if (not isinstance(header, dict) or header.get("number") != ledger_index
                or isinstance(header.get("number"), bool)
                or not isinstance(header.get("hash"), str)
                or re.fullmatch(r"[0-9a-fA-F]{64}", header["hash"]) is None
                or not isinstance(header.get("parent_hash"), str)
                or re.fullmatch(r"[0-9a-fA-F]{64}", header["parent_hash"]) is None
                or isinstance(header.get("timestamp"), bool)
                or not isinstance(header.get("timestamp"), int)
                or not 0 <= header["timestamp"] <= 946684800 + 0xFFFFFFFF
                or header.get("finality_reference") != "validated=true"):
            raise ProviderTransportError("INVALID_PROVIDER_DATA", "Chainstack returned a malformed or unvalidated XRPL ledger header")
        return header

    def _reconcile_recent(self, mapping, account, next_ledger, initial_ledger):
        if self.reorg_lookback_ledgers == 0 or next_ledger <= initial_ledger:
            return 0, None, 0
        scope = self._scope(mapping, account)
        first = max(initial_ledger, next_ledger - self.reorg_lookback_ledgers)
        changed_events = changed_ledgers = 0
        earliest = None
        for ledger_index in range(first, next_ledger):
            stored_hash = self.ingestion_store.get_block_hash("xrpl-mainnet", "chainstack", scope, ledger_index)
            if stored_hash is None:
                continue
            header = self._header(ledger_index)
            if stored_hash.lower() != header["hash"].lower():
                changed_ledgers += 1
                changed_events += self.ingestion_store.reconcile_block(
                    "xrpl-mainnet", ledger_index, header["hash"].lower(),
                    provider="chainstack", scope=scope,
                )
                if earliest is None:
                    earliest = ledger_index
        return changed_events, earliest, changed_ledgers

    def _finalize_page_acceptances(self, summary: dict) -> None:
        result = self.mapping_store.engine.sign_pending_ingestion_pages(self.ingestion_store)
        summary["page_acceptances_signed"] = result["signed"]
        summary["page_acceptances_pending"] = result["pending"]
        summary["page_acceptances_rejected"] = result["rejected"]

    @_capture_provider_run_receipts
    def run_once(self) -> dict:
        mappings = self.mapping_store.list_verified_mappings("xrpl-mainnet")
        summary = {"mappings": 0, "accounts": 0, "ledgers_scanned": 0,
                   "pages_committed": 0, "events_inserted": 0, "duplicates": 0,
                   "reorg_ledgers_detected": 0, "reorg_events_tombstoned": 0,
                   "checkpoints_advanced": 0, "markers_reset": 0}
        if not mappings:
            self._finalize_page_acceptances(summary)
            return summary
        head = self._retry(self.provider.probe)
        head_receipts = drain_provider_run_receipts()
        if (getattr(head, "provider", None) != "chainstack"
                or getattr(head, "network_id", None) != "xrpl-mainnet"
                or getattr(head, "status", None) != "AVAILABLE"
                or getattr(head, "finality", None) != "FINALIZED"
                or isinstance(getattr(head, "head_height", None), bool)
                or not isinstance(getattr(head, "head_height", None), int)):
            raise ProviderTransportError("XRPL_VALIDATED_HEAD_UNAVAILABLE", "Chainstack did not return a validated XRPL mainnet head")
        if not 1 <= head.head_height <= 0xFFFFFFFF:
            raise ProviderTransportError(
                "INVALID_PROVIDER_DATA", "Chainstack XRPL validated head height is outside the UInt32 ledger-index range",
            )
        summary.update({"page_acceptances_signed": 0, "page_acceptances_pending": 0,
                        "page_acceptances_rejected": 0})
        for mapping in mappings:
            drain_provider_run_receipts()  # isolate each mapping's account set
            self._validate_mapping(mapping)
            accounts = self.monitored_accounts.get(mapping.mapping_id)
            if not accounts or mapping.mapping_id not in self.start_ledgers:
                raise ValueError(f"no explicit monitored accounts/start ledger configured for {mapping.mapping_id}")
            summary["mappings"] += 1
            for account in accounts:
                drain_provider_run_receipts()  # isolate the next account scope
                include_provider_receipts_in_current_scope(head_receipts)
                summary["accounts"] += 1
                scope = self._scope(mapping, account)
                cursor_key = self._cursor_key(account, mapping)
                initial = self.start_ledgers[mapping.mapping_id]
                checkpoint = self.ingestion_store.get_checkpoint(cursor_key)
                expected_checkpoint = checkpoint
                if checkpoint is None:
                    checkpoint = {"mapping_id": mapping.mapping_id, "account": account,
                                  "next_ledger": initial, "range_start": None,
                                  "range_end": None, "marker": None, "seen_markers": []}
                if (not isinstance(checkpoint, dict) or checkpoint.get("mapping_id") != mapping.mapping_id
                        or checkpoint.get("account") != account
                        or isinstance(checkpoint.get("next_ledger"), bool)
                        or not isinstance(checkpoint.get("next_ledger"), int)
                        or not initial <= checkpoint["next_ledger"] <= 0x100000000
                        or not isinstance(checkpoint.get("seen_markers", []), list)):
                    raise ValueError("stored XRPL account checkpoint is malformed")
                self._marker_key(checkpoint.get("marker"))
                for saved_marker in checkpoint.get("seen_markers", []):
                    self._marker_key(saved_marker)
                reorg_count, rewind, reorg_ledgers = self._reconcile_recent(
                    mapping, account, checkpoint["next_ledger"], initial)
                summary["reorg_events_tombstoned"] += reorg_count
                summary["reorg_ledgers_detected"] += reorg_ledgers
                if rewind is not None:
                    checkpoint = {"mapping_id": mapping.mapping_id, "account": account,
                                  "next_ledger": rewind, "range_start": None,
                                  "range_end": None, "marker": None, "seen_markers": []}
                    self.ingestion_store.commit_page(
                        cursor_key, checkpoint, (), expected_cursor=expected_checkpoint,
                        scope_identity=("xrpl-mainnet", "chainstack", scope))
                    expected_checkpoint = checkpoint
                range_start = checkpoint.get("range_start")
                range_end = checkpoint.get("range_end")
                if range_start is None:
                    range_start = checkpoint["next_ledger"]
                    range_end = min(head.head_height, range_start + self.max_ledgers_per_run - 1)
                    if range_start > range_end:
                        continue
                    checkpoint = {**checkpoint, "range_start": range_start,
                                  "range_end": range_end, "marker": None, "seen_markers": []}
                    self.ingestion_store.commit_page(
                        cursor_key, checkpoint, (), expected_cursor=expected_checkpoint,
                        scope_identity=("xrpl-mainnet", "chainstack", scope))
                    expected_checkpoint = checkpoint
                if (isinstance(range_start, bool) or not isinstance(range_start, int)
                        or isinstance(range_end, bool) or not isinstance(range_end, int)
                        or range_start < initial or range_end < range_start
                        or range_end > head.head_height):
                    raise ValueError("stored XRPL fixed ledger range is malformed or beyond validated head")
                headers = {index: self._header(index) for index in range(range_start, range_end + 1)}
                if range_start > 1:
                    preceding_header = self._header(range_start - 1)
                    if headers[range_start]["parent_hash"].lower() != preceding_header["hash"].lower():
                        raise ProviderTransportError(
                            "XRPL_PARENT_HASH_MISMATCH",
                            "XRPL first validated ledger parent_hash does not match the preceding ledger hash",
                        )
                    if headers[range_start]["timestamp"] <= preceding_header["timestamp"]:
                        raise ProviderTransportError(
                            "XRPL_LEDGER_TIME_NOT_MONOTONIC",
                            "XRPL validated ledger close time must be strictly later than its parent ledger",
                        )
                for index in range(range_start + 1, range_end + 1):
                    if headers[index]["parent_hash"].lower() != headers[index - 1]["hash"].lower():
                        raise ProviderTransportError(
                            "XRPL_PARENT_HASH_MISMATCH",
                            "XRPL validated ledger parent_hash does not match the preceding ledger hash",
                        )
                    if headers[index]["timestamp"] <= headers[index - 1]["timestamp"]:
                        raise ProviderTransportError(
                            "XRPL_LEDGER_TIME_NOT_MONOTONIC",
                            "XRPL validated ledger close time must be strictly later than its parent ledger",
                        )
                # These provider responses are shared evidence for every page in this
                # fixed range. Preserve an opaque collector-issued batch and attach
                # it to each page commit, not only the first pagination page.
                supporting_receipts = drain_provider_run_receipts()
                # Revalidate an in-progress fixed range before trusting its opaque marker.
                # This catches a ledger-hash change between page commits and forces a full replay.
                active_rewind = None
                for index, header in headers.items():
                    stored_hash = self.ingestion_store.get_block_hash("xrpl-mainnet", "chainstack", scope, index)
                    if stored_hash is not None and stored_hash.lower() != header["hash"].lower():
                        summary["reorg_ledgers_detected"] += 1
                        summary["reorg_events_tombstoned"] += self.ingestion_store.reconcile_block(
                            "xrpl-mainnet", index, header["hash"].lower(), provider="chainstack", scope=scope)
                        if active_rewind is None:
                            active_rewind = index
                marker = checkpoint.get("marker")
                seen_markers = list(checkpoint.get("seen_markers", []))
                if active_rewind is not None:
                    marker = None
                    seen_markers = []
                    checkpoint = {"mapping_id": mapping.mapping_id, "account": account,
                                  "next_ledger": active_rewind, "range_start": range_start,
                                  "range_end": range_end, "marker": None, "seen_markers": []}
                    self.ingestion_store.commit_page(
                        cursor_key, checkpoint, (), expected_cursor=expected_checkpoint,
                        scope_identity=("xrpl-mainnet", "chainstack", scope))
                    expected_checkpoint = checkpoint
                pages = 0
                while pages < self.max_pages_per_run:
                    include_provider_receipts_in_current_scope(supporting_receipts)
                    try:
                        page = self._retry(lambda: self.provider.fetch_account_transactions(
                            account, range_start, range_end, marker=marker, limit=self.page_size))
                    except ProviderTransportError as exc:
                        # XRPL markers are ephemeral. If a persisted marker has expired,
                        # safely restart this same fixed range from its first page.
                        if marker is not None and exc.reason_code == "RPC_ERROR":
                            reset = {"mapping_id": mapping.mapping_id, "account": account,
                                     "next_ledger": range_start, "range_start": range_start,
                                     "range_end": range_end, "marker": None, "seen_markers": []}
                            self.ingestion_store.commit_page(
                                cursor_key, reset, (), expected_cursor=expected_checkpoint,
                                scope_identity=("xrpl-mainnet", "chainstack", scope))
                            expected_checkpoint = reset
                            summary["markers_reset"] += 1
                            break
                        raise
                    records = getattr(page, "records", None)
                    if (not isinstance(records, tuple) or page.provider != "chainstack"
                            or page.network_id != "xrpl-mainnet" or page.scope != account
                            or page.from_block != range_start or page.to_block != range_end
                            or page.finality_reference != "validated=true"):
                        raise ProviderTransportError("INVALID_PROVIDER_DATA", "Chainstack XRPL page does not match the fixed validated account/range")
                    if len(records) > self.page_size:
                        raise ProviderTransportError(
                            "PAGE_LIMIT_EXCEEDED",
                            "XRPL provider returned more transactions than the configured page size",
                        )
                    observed = self.clock()
                    if observed.tzinfo is None or observed.utcoffset() is None:
                        raise ValueError("worker clock must return a timezone-aware datetime")
                    observed_at = observed.astimezone(timezone.utc).isoformat()
                    events = []
                    for record in records:
                        if not isinstance(record, XrplAccountTransaction) or not range_start <= record.ledger_index <= range_end:
                            raise ProviderTransportError("INVALID_PROVIDER_DATA", "XRPL account page contains a record outside its validated range")
                        header = headers.get(record.ledger_index)
                        if header is None:
                            raise ProviderTransportError("INVALID_PROVIDER_DATA", "XRPL transaction ledger header was not independently verified")
                        if (not isinstance(record.close_time_iso, str)
                                or not record.close_time_iso
                                or not isinstance(record.raw, dict)
                                or record.raw.get("close_time_iso") != record.close_time_iso):
                            raise ProviderTransportError(
                                "INVALID_PROVIDER_DATA",
                                "XRPL transaction close_time_iso is missing or differs from its raw provider evidence",
                            )
                        try:
                            transaction_close_time = datetime.fromisoformat(
                                record.close_time_iso.replace("Z", "+00:00"))
                        except ValueError:
                            raise ProviderTransportError(
                                "INVALID_PROVIDER_DATA", "XRPL transaction close_time_iso is malformed",
                            ) from None
                        if (transaction_close_time.tzinfo is None
                                or transaction_close_time.utcoffset() is None):
                            raise ProviderTransportError(
                                "INVALID_PROVIDER_DATA", "XRPL transaction close_time_iso must be timezone-aware",
                            )
                        canonical_close_time = datetime.fromtimestamp(header["timestamp"], timezone.utc)
                        if transaction_close_time.astimezone(timezone.utc) != canonical_close_time:
                            raise ProviderTransportError(
                                "XRPL_LEDGER_TIME_MISMATCH",
                                "XRPL account_tx close_time_iso does not match the independently verified ledger header",
                            )
                        block_time = canonical_close_time.isoformat()
                        event = normalize_xrpl_payment(
                            record, monitored_account=account, asset_id=mapping.asset_id,
                            mapping_id=mapping.mapping_id, issuer_address=mapping.issuer_address,
                            issued_currency=mapping.issued_currency, decimals=mapping.decimals,
                            canonical_ledger_hash=header["hash"], block_time=block_time,
                            observed_at=observed_at, scope=scope,
                        )
                        if event is not None:
                            events.append(replace(
                                event, finality_snapshot=OnChainFinalitySnapshot(
                                    version=1, network_id="xrpl-mainnet", status="FINALIZED",
                                    reference=page.finality_reference,
                                ),
                            ))
                    next_marker = page.next_cursor
                    if next_marker is not None:
                        marker_key = self._marker_key(
                            next_marker, reason_code="INVALID_PROVIDER_DATA")
                        prior_keys = {self._marker_key(item) for item in seen_markers}
                        current_key = self._marker_key(marker) if marker is not None else None
                        if marker_key in prior_keys or marker_key == current_key:
                            raise ProviderTransportError("XRPL_MARKER_LOOP", "XRPL account_tx pagination marker repeated")
                        seen_markers.append(next_marker)
                    if next_marker is None:
                        next_checkpoint = {"mapping_id": mapping.mapping_id, "account": account,
                                           "next_ledger": range_end + 1, "range_start": None,
                                           "range_end": None, "marker": None, "seen_markers": []}
                    else:
                        next_checkpoint = {"mapping_id": mapping.mapping_id, "account": account,
                                           "next_ledger": range_start, "range_start": range_start,
                                           "range_end": range_end, "marker": next_marker,
                                           "seen_markers": seen_markers}
                    next_checkpoint.update({
                        "validated_head_height": head.head_height,
                        "finality_reference": page.finality_reference,
                    })
                    canonical_blocks = tuple({
                        "network_id": "xrpl-mainnet", "provider": "chainstack", "scope": scope,
                        "block_number": index, "block_hash": header["hash"].lower(),
                        "block_time": datetime.fromtimestamp(header["timestamp"], timezone.utc).isoformat(),
                    } for index, header in headers.items())
                    committed = self.ingestion_store.commit_page(
                        cursor_key, next_checkpoint, events, allow_recanonicalized=True,
                        canonical_blocks=canonical_blocks,
                        expected_cursor=expected_checkpoint,
                        scope_identity=("xrpl-mainnet", "chainstack", scope),
                        provider_receipts=drain_provider_run_receipts(),
                    )
                    expected_checkpoint = next_checkpoint
                    summary["events_inserted"] += committed["inserted"]
                    summary["duplicates"] += committed["duplicates"]
                    summary["pages_committed"] += 1
                    summary["checkpoints_advanced"] += 1
                    pages += 1
                    summary["ledgers_scanned"] += len(headers) if pages == 1 else 0
                    marker = next_marker
                    if marker is None:
                        break
        self._finalize_page_acceptances(summary)
        return summary
