"""Fail-closed aggregation of canonical on-chain transfer events.

Amounts are normalized only within the exact verified asset mapping and remain
segmented by network/mapping. Cross-network USD or quantity totals are never
summed: wrapped/bridged representations can double-count the same economic
movement and no price/oracle proof is available in this layer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from typing import Iterable, Mapping, Optional

from .foundation import BinanceListingEligibilityEngine, EligibilityDecision
from .onchain import NETWORK_PROVIDERS, OnChainAssetMapping, OnChainStore, _parse_timestamp
from .onchain_ingestion import NormalizedTransferEvent, OnChainIngestionStore


@dataclass(frozen=True)
class NetworkTransferSummary:
    asset_id: str
    binance_symbol: str
    network_id: str
    mapping_id: str
    representation: str
    decimals: int
    transfer_count: int
    total_amount: str
    minimum_amount: str
    threshold_met: bool
    unique_source_address_count: int
    unique_destination_address_count: int
    first_block_time: str
    last_block_time: str


@dataclass(frozen=True)
class AssetTransferRollup:
    asset_id: str
    binance_symbol: str
    network_count: int
    observation_count: int
    network_summaries: tuple[NetworkTransferSummary, ...]


@dataclass(frozen=True)
class TransferAggregationResult:
    assets: tuple[AssetTransferRollup, ...]
    network_summaries: tuple[NetworkTransferSummary, ...]
    deduplicated_events: int
    rejected_events: int
    rejection_counts: tuple[tuple[str, int], ...]
    # Deliberately absent: summing token units or USD value across networks is unsafe.
    cross_network_total_amount: Optional[str] = None

    @property
    def qualifying_network_summaries(self) -> tuple[NetworkTransferSummary, ...]:
        return tuple(row for row in self.network_summaries if row.threshold_met)

    @property
    def qualifying_assets(self) -> tuple[AssetTransferRollup, ...]:
        qualified = {row.asset_id for row in self.qualifying_network_summaries}
        return tuple(row for row in self.assets if row.asset_id in qualified)


class OnChainTransferAggregator:
    """Aggregate canonical transfer evidence after current Binance Spot gating.

    A positive threshold is mandatory for every verified mapping. It is an
    explicit human-unit amount for that mapping, not an inferred whale cutoff.
    """

    def __init__(
        self,
        mapping_store: OnChainStore,
        *,
        minimum_amount_by_mapping: Mapping[str, str | int | Decimal],
        eligibility_max_age_seconds: int = 300,
        identity_proof_max_age_seconds: int = 900,
    ):
        if not isinstance(mapping_store, OnChainStore):
            raise ValueError("mapping_store must be the verified OnChainStore")
        if (isinstance(eligibility_max_age_seconds, bool)
                or not isinstance(eligibility_max_age_seconds, int)
                or eligibility_max_age_seconds <= 0
                or isinstance(identity_proof_max_age_seconds, bool)
                or not isinstance(identity_proof_max_age_seconds, int)
                or identity_proof_max_age_seconds <= 0):
            raise ValueError("eligibility freshness limits must be positive integer seconds")
        if not isinstance(minimum_amount_by_mapping, Mapping) or not minimum_amount_by_mapping:
            raise ValueError("explicit positive minimum amounts are required for every verified mapping")
        thresholds: dict[str, Decimal] = {}
        for mapping_id, value in minimum_amount_by_mapping.items():
            if not isinstance(mapping_id, str) or not mapping_id.strip():
                raise ValueError("threshold mapping IDs must be non-empty strings")
            try:
                amount = Decimal(str(value))
            except (InvalidOperation, ValueError):
                raise ValueError(f"threshold for {mapping_id} must be a decimal amount") from None
            if not amount.is_finite() or amount <= 0:
                raise ValueError(f"threshold for {mapping_id} must be a positive finite decimal")
            thresholds[mapping_id] = amount
        verified_ids = {mapping.mapping_id for mapping in mapping_store.list_verified_mappings()}
        if not verified_ids:
            raise ValueError("at least one verified asset mapping is required before aggregation")
        missing_thresholds = verified_ids - thresholds.keys()
        unknown_thresholds = thresholds.keys() - verified_ids
        if missing_thresholds or unknown_thresholds:
            details = []
            if missing_thresholds:
                details.append("missing=" + ",".join(sorted(missing_thresholds)))
            if unknown_thresholds:
                details.append("unknown=" + ",".join(sorted(unknown_thresholds)))
            raise ValueError("threshold configuration must exactly cover verified mappings: " + "; ".join(details))
        self.mapping_store = mapping_store
        self.minimum_amount_by_mapping = thresholds
        self._ingestion_store: Optional[OnChainIngestionStore] = None
        self.eligibility_max_age_seconds = eligibility_max_age_seconds
        self.identity_proof_max_age_seconds = identity_proof_max_age_seconds

    @staticmethod
    def _now(value: Optional[datetime]) -> datetime:
        current = value or datetime.now(timezone.utc)
        if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("aggregation clock must be timezone-aware")
        return current.astimezone(timezone.utc)

    def _mappings(self) -> dict[str, OnChainAssetMapping]:
        mappings = self.mapping_store.list_verified_mappings()
        mapping_ids = {mapping.mapping_id for mapping in mappings}
        missing = mapping_ids - self.minimum_amount_by_mapping.keys()
        unknown = self.minimum_amount_by_mapping.keys() - mapping_ids
        if missing or unknown:
            raise ValueError("verified mappings and explicit threshold configuration no longer match")
        return {mapping.mapping_id: mapping for mapping in mappings}

    def _eligibility_error(
        self, mapping: OnChainAssetMapping,
        decisions: Mapping[str, EligibilityDecision], now: datetime,
    ) -> Optional[str]:
        decision = decisions.get(mapping.asset_id)
        if not isinstance(decision, EligibilityDecision) or decision.status != "ELIGIBLE":
            return "BINANCE_SPOT_ELIGIBILITY_REQUIRED"
        if (decision.asset_id != mapping.asset_id or decision.symbol != mapping.binance_symbol
                or decision.source != BinanceListingEligibilityEngine.SOURCE
                or decision.identity_proof_status != "VERIFIED"
                or decision.identity_proof_source != "coingecko_coin_tickers"
                or not isinstance(decision.identity_proof_data_hash, str)
                or re.fullmatch(r"[0-9a-fA-F]{64}", decision.identity_proof_data_hash) is None
                or not isinstance(decision.eligible_pairs, tuple) or not decision.eligible_pairs
                or any(not isinstance(pair, str) or not pair.isalnum() or pair != pair.upper()
                       or not pair.startswith(mapping.binance_symbol)
                       or len(pair) <= len(mapping.binance_symbol)
                       for pair in decision.eligible_pairs)):
            return "BINANCE_SPOT_ELIGIBILITY_PROOF_INVALID"
        try:
            decision_time = _parse_timestamp(decision.verified_at)
            proof_verified = _parse_timestamp(decision.identity_proof_verified_at)
            proof_source = _parse_timestamp(decision.identity_proof_source_timestamp)
        except (TypeError, ValueError):
            return "BINANCE_SPOT_ELIGIBILITY_PROOF_INVALID"
        if ((now - decision_time).total_seconds() < -300
                or (now - decision_time).total_seconds() > self.eligibility_max_age_seconds
                or (now - proof_verified).total_seconds() < -300
                or (now - proof_verified).total_seconds() > self.identity_proof_max_age_seconds
                or (now - proof_source).total_seconds() < -300
                or (now - proof_source).total_seconds() > self.identity_proof_max_age_seconds):
            return "BINANCE_SPOT_ELIGIBILITY_STALE"
        observation = self.mapping_store.get_latest_accepted_observation(mapping.mapping_id)
        if observation is None:
            return "ONCHAIN_MAPPING_LACKS_ACCEPTED_SPOT_PROOF"
        validated = self.mapping_store.engine.validate(
            decision, mapping, observation, now=now.isoformat())
        if validated.status != "ACCEPTED":
            return validated.reason_code
        return None

    @staticmethod
    def _event_fingerprint(event: NormalizedTransferEvent) -> tuple:
        # scope and observed_at differ when the same transfer is discovered from
        # multiple monitored accounts. All economic/canonical identity must match.
        return (
            event.event_id, event.network_id, event.asset_id, event.mapping_id,
            event.transaction_hash, event.block_number, event.block_hash,
            event.event_index, event.from_address, event.to_address,
            event.amount_raw, event.decimals, event.block_time,
            tuple(event.from_addresses), event.from_addresses_complete,
            event.canonical_status,
        )

    def bind_ingestion_store(self, ingestion_store: OnChainIngestionStore) -> None:
        """Bind the canonical block journal required to verify each event's hash."""
        if not isinstance(ingestion_store, OnChainIngestionStore):
            raise ValueError("ingestion_store must be the canonical OnChainIngestionStore")
        self._ingestion_store = ingestion_store

    def aggregate(
        self,
        events: Iterable[NormalizedTransferEvent],
        eligibility_by_asset: Mapping[str, EligibilityDecision],
        *,
        now: Optional[datetime] = None,
    ) -> TransferAggregationResult:
        current = self._now(now)
        if not isinstance(self._ingestion_store, OnChainIngestionStore):
            raise ValueError("canonical ingestion store must be bound before aggregation")
        if not isinstance(eligibility_by_asset, Mapping):
            raise ValueError("current Binance eligibility decisions must be supplied by canonical asset ID")
        mappings = self._mappings()
        eligibility_cache: dict[str, Optional[str]] = {}
        unique: dict[tuple[str, str, str], NormalizedTransferEvent] = {}
        deduplicated = 0
        rejected: dict[str, int] = {}

        def reject(reason: str):
            rejected[reason] = rejected.get(reason, 0) + 1

        for event in events:
            if not isinstance(event, NormalizedTransferEvent):
                raise ValueError("aggregation input contains a non-normalized event")
            if event.canonical_status != "CANONICAL":
                reject("NON_CANONICAL_EVENT")
                continue
            mapping = mappings.get(event.mapping_id)
            if mapping is None:
                raise ValueError(f"event references an unknown or unverified mapping: {event.mapping_id}")
            if (event.asset_id != mapping.asset_id or event.network_id != mapping.network_id
                    or event.decimals != mapping.decimals):
                raise ValueError("event asset/network/decimal metadata conflicts with its verified mapping")
            if (event.provider not in NETWORK_PROVIDERS.get(event.network_id, frozenset())
                    or not isinstance(event.scope, str) or not event.scope.strip()
                    or not isinstance(event.event_id, str) or not event.event_id.strip()
                    or not isinstance(event.transaction_hash, str)
                    or not isinstance(event.to_address, str) or not event.to_address.strip()
                    or (event.from_address is not None and (not isinstance(event.from_address, str)
                        or not event.from_address.strip()))
                    or not isinstance(event.from_addresses_complete, bool)
                    or not isinstance(event.from_addresses, (tuple, list))
                    or any(not isinstance(address, str) or not address.strip()
                           for address in event.from_addresses)):
                raise ValueError("event provider, stable identity or transfer account evidence is invalid")
            identity_patterns = {
                "bitcoin-mainnet": (r"[0-9a-fA-F]{64}", r"[0-9a-fA-F]{64}", r"[0-9a-fA-F]{64}:\d+"),
                "ethereum-mainnet": (r"0x[0-9a-fA-F]{64}", r"0x[0-9a-fA-F]{64}", r"0x[0-9a-fA-F]{64}:\d+"),
                "bnb-smart-chain-mainnet": (r"0x[0-9a-fA-F]{64}", r"0x[0-9a-fA-F]{64}", r"0x[0-9a-fA-F]{64}:\d+"),
                "solana-mainnet": (r"[1-9A-HJ-NP-Za-km-z]{64,90}", r"[1-9A-HJ-NP-Za-km-z]{32,44}", r"[1-9A-HJ-NP-Za-km-z]{64,90}:(?:outer:\d+|inner:\d+:\d+)"),
                "xrpl-mainnet": (r"[0-9a-fA-F]{64}", r"[0-9a-fA-F]{64}", r"[0-9a-fA-F]{64}"),
            }
            tx_pattern, block_pattern, event_pattern = identity_patterns[event.network_id]
            if (re.fullmatch(tx_pattern, event.transaction_hash) is None
                    or re.fullmatch(block_pattern, event.block_hash) is None
                    or re.fullmatch(event_pattern, event.event_id) is None):
                raise ValueError("event transaction, block or event identity does not match its network format")
            if event.network_id == "xrpl-mainnet" and event.event_id.lower() != event.transaction_hash.lower():
                raise ValueError("XRPL Payment event identity must equal its transaction hash")
            if event.network_id in {"bitcoin-mainnet", "ethereum-mainnet", "bnb-smart-chain-mainnet"}:
                if event.event_id.rsplit(":", 1)[0].lower() != event.transaction_hash.lower():
                    raise ValueError("transaction-scoped event identity does not match transaction hash")
                if event.event_index != int(event.event_id.rsplit(":", 1)[1]):
                    raise ValueError("event index does not match the stable transaction event identity")
            if event.network_id == "solana-mainnet":
                if event.event_id.split(":", 1)[0] != event.transaction_hash:
                    raise ValueError("Solana instruction event identity does not match transaction signature")
                if event.event_index is not None:
                    raise ValueError("Solana instruction event index must remain null; trace coordinates are encoded in event_id")
            if (not isinstance(event.amount_raw, str) or len(event.amount_raw) > 256
                    or re.fullmatch(r"[0-9]+", event.amount_raw) is None
                    or int(event.amount_raw) <= 0
                    or isinstance(event.decimals, bool) or not isinstance(event.decimals, int)
                    or not 0 <= event.decimals <= 36
                    or isinstance(event.block_number, bool) or not isinstance(event.block_number, int)
                    or event.block_number < 0
                    or (event.event_index is not None and (isinstance(event.event_index, bool)
                        or not isinstance(event.event_index, int) or event.event_index < 0))):
                raise ValueError("event amount must be a positive integer base-unit string with valid decimals")
            try:
                block_time = _parse_timestamp(event.block_time)
                observed_at = _parse_timestamp(event.observed_at)
            except (TypeError, ValueError):
                raise ValueError("event timestamps must be timezone-aware ISO-8601") from None
            freshness = self.mapping_store.engine.freshness_limits_seconds.get(event.network_id)
            if freshness is None:
                reject("NETWORK_FRESHNESS_POLICY_MISSING")
                continue
            age = (current - block_time).total_seconds()
            if age < -300:
                reject("EVENT_FROM_FUTURE")
                continue
            if age > freshness:
                reject("EVENT_STALE")
                continue
            if (observed_at - current).total_seconds() > 300:
                reject("EVENT_OBSERVATION_FROM_FUTURE")
                continue
            persisted_event = self._ingestion_store.get_event(
                event.event_id, event.network_id, event.provider, event.scope)
            if persisted_event is None:
                reject("EVENT_NOT_PERSISTED")
                continue
            if persisted_event != event:
                raise ValueError("aggregation event payload differs from its persisted canonical record")
            journaled_hash = self._ingestion_store.get_block_hash(
                event.network_id, event.provider, event.scope, event.block_number)
            if journaled_hash is None:
                reject("CANONICAL_BLOCK_EVIDENCE_MISSING")
                continue
            if journaled_hash.lower() != event.block_hash.lower():
                reject("CANONICAL_BLOCK_HASH_MISMATCH")
                continue
            if mapping.mapping_id not in eligibility_cache:
                eligibility_cache[mapping.mapping_id] = self._eligibility_error(
                    mapping, eligibility_by_asset, current)
            eligibility_error = eligibility_cache[mapping.mapping_id]
            if eligibility_error:
                reject(eligibility_error)
                continue
            identity = (event.network_id, event.mapping_id, event.event_id)
            existing = unique.get(identity)
            if existing is not None:
                if self._event_fingerprint(existing) != self._event_fingerprint(event):
                    raise ValueError("conflicting duplicate transfer event across monitored account scopes")
                deduplicated += 1
                continue
            unique[identity] = event

        grouped: dict[tuple[str, str, str], list[NormalizedTransferEvent]] = {}
        for event in unique.values():
            grouped.setdefault((event.asset_id, event.network_id, event.mapping_id), []).append(event)

        summaries: list[NetworkTransferSummary] = []
        for (asset_id, network_id, mapping_id), rows in sorted(grouped.items()):
            mapping = mappings[mapping_id]
            total_raw = sum(int(row.amount_raw) for row in rows)
            with localcontext() as context:
                context.prec = max(80, len(str(total_raw)) + mapping.decimals + 8)
                total = Decimal(total_raw).scaleb(-mapping.decimals)
            threshold = self.minimum_amount_by_mapping[mapping_id]
            senders = set()
            for row in rows:
                if row.from_addresses_complete:
                    if row.from_addresses:
                        senders.update(address for address in row.from_addresses if address.strip())
                    elif isinstance(row.from_address, str) and row.from_address.strip():
                        senders.add(row.from_address)
            receivers = {row.to_address for row in rows if row.to_address.strip()}
            times = sorted(_parse_timestamp(row.block_time) for row in rows)
            summaries.append(NetworkTransferSummary(
                asset_id=asset_id, binance_symbol=mapping.binance_symbol,
                network_id=network_id, mapping_id=mapping_id,
                representation=mapping.representation, decimals=mapping.decimals,
                transfer_count=len(rows), total_amount=format(total.normalize(), "f"),
                minimum_amount=format(threshold.normalize(), "f"), threshold_met=total >= threshold,
                unique_source_address_count=len(senders), unique_destination_address_count=len(receivers),
                first_block_time=times[0].isoformat(), last_block_time=times[-1].isoformat(),
            ))

        by_asset: dict[str, list[NetworkTransferSummary]] = {}
        for summary in summaries:
            by_asset.setdefault(summary.asset_id, []).append(summary)
        assets = tuple(
            AssetTransferRollup(
                asset_id=asset_id, binance_symbol=rows[0].binance_symbol,
                network_count=len({row.network_id for row in rows}),
                observation_count=sum(row.transfer_count for row in rows),
                network_summaries=tuple(rows),
            )
            for asset_id, rows in sorted(by_asset.items())
        )
        return TransferAggregationResult(
            assets=assets, network_summaries=tuple(summaries),
            deduplicated_events=deduplicated, rejected_events=sum(rejected.values()),
            rejection_counts=tuple(sorted(rejected.items())),
            cross_network_total_amount=None,
        )

    def aggregate_store(
        self,
        ingestion_store: OnChainIngestionStore,
        eligibility_by_asset: Mapping[str, EligibilityDecision],
        *,
        now: Optional[datetime] = None,
    ) -> TransferAggregationResult:
        if not isinstance(ingestion_store, OnChainIngestionStore):
            raise ValueError("ingestion_store must be the canonical OnChainIngestionStore")
        self._ingestion_store = ingestion_store
        return self.aggregate(
            ingestion_store.list_all_events(canonical_only=True),
            eligibility_by_asset, now=now,
        )
