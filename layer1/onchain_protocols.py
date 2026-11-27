"""Structural storage contracts shared by SQLite and PostgreSQL Module 9 adapters.

These protocols describe the worker/aggregator boundary, not persistence
inheritance. PostgreSQL-specific concurrency requirements are explicit in the
worker-facing method signatures.
"""
from __future__ import annotations

import inspect
from collections.abc import Mapping as MappingABC
from typing import Any, Iterable, Mapping, Optional, Protocol

from .foundation import EligibilityDecision
from .onchain import OnChainAssetMapping, OnChainObservation
from .onchain_ingestion import NormalizedTransferEvent
from .onchain_providers import CapturedProviderReceiptBatch, ProviderResponseReceipt


class OnChainValidationEngineProtocol(Protocol):
    """Validation and per-network freshness policy required by aggregation."""

    freshness_limits_seconds: Mapping[str, int]

    def validate(
        self, eligibility: EligibilityDecision, mapping: OnChainAssetMapping,
        observation: OnChainObservation, *, now: Optional[str] = None,
        ingestion_store: Any = None, provenance: Any = None,
    ) -> Any: ...


class OnChainMappingStoreProtocol(Protocol):
    """Verified mapping and accepted-observation reads used by workers/aggregator."""

    engine: OnChainValidationEngineProtocol

    def list_verified_mappings(
        self, network_id: Optional[str] = None,
    ) -> list[OnChainAssetMapping]: ...

    def get_latest_accepted_observation(
        self, mapping_id: str,
    ) -> Optional[OnChainObservation]: ...

    def get_observation(self, observation_id: str) -> Any: ...


class OnChainIngestionStoreProtocol(Protocol):
    """Canonical ingestion journal/checkpoint operations used by Module 9."""

    def get_checkpoint(self, cursor_key: str) -> Optional[Any]: ...

    def commit_page(
        self,
        cursor_key: str,
        next_cursor: Any,
        events: Iterable[NormalizedTransferEvent],
        *,
        expected_cursor: Any,
        scope_identity: tuple[str, str, str],
        allow_recanonicalized: bool = False,
        canonical_blocks: Iterable[dict] = (),
        canonical_slots: Iterable[dict] = (),
        provider_receipts: Optional[CapturedProviderReceiptBatch] = None,
        provider_observations: Iterable[dict] = (),
        solana_quarantine_records: Iterable[dict] = (),
        solana_quarantine_replayed: Iterable[str] = (),
    ) -> dict: ...

    def list_page_receipts(
        self, cursor_key: str,
    ) -> tuple[ProviderResponseReceipt, ...]: ...

    def get_page_acceptance_material(self, cursor_key: str, page_id: str) -> dict: ...

    def save_page_acceptance(
        self, cursor_key: str, page_id: str, key_id: str,
        payload_json: str, payload_sha256: str, signature: str,
    ) -> str: ...

    def get_page_acceptance(self, cursor_key: str, page_id: str) -> Optional[dict]: ...

    def list_ingestion_pages(self) -> tuple[tuple[str, str], ...]: ...

    def list_pending_page_acceptances(self) -> tuple[tuple[str, str], ...]: ...

    def list_invalidated_page_acceptances(self) -> tuple[dict, ...]: ...

    def get_block_hash(
        self, network_id: str, provider: str, scope: str, block_number: int,
    ) -> Optional[str]: ...

    def reconcile_block(
        self, network_id: str, block_number: int, canonical_block_hash: str,
        *, provider: str, scope: str,
    ) -> int: ...

    def get_solana_slot_journal(
        self, network_id: str, provider: str, scope: str,
        start_slot: int, end_slot: int,
    ) -> dict[int, dict]: ...

    def list_pending_solana_quarantine(
        self, network_id: str, provider: str, scope: str, limit: int = 100,
    ) -> list[dict]: ...

    def get_event(
        self, event_id: str, network_id: str,
        provider: Optional[str] = None, scope: Optional[str] = None,
    ) -> Optional[NormalizedTransferEvent]: ...

    def list_all_events(
        self, canonical_only: bool = False,
    ) -> list[NormalizedTransferEvent]: ...


_MAPPING_METHODS = (
    "list_verified_mappings", "get_latest_accepted_observation", "get_observation",
)
_INGESTION_METHODS = (
    "get_checkpoint", "commit_page", "get_block_hash", "reconcile_block",
    "get_solana_slot_journal", "get_event", "list_all_events", "list_page_receipts",
    "get_page_acceptance_material", "save_page_acceptance", "get_page_acceptance",
    "list_pending_page_acceptances", "list_ingestion_pages",
)


def require_mapping_store(store: Any) -> None:
    """Fail early unless a store satisfies the mapping and validation contract."""
    if any(not callable(getattr(store, name, None)) for name in _MAPPING_METHODS):
        raise ValueError("mapping store does not satisfy the Module 9 mapping protocol")
    engine = getattr(store, "engine", None)
    if not callable(getattr(engine, "validate", None)):
        raise ValueError("mapping store does not expose a compatible validation engine")
    freshness_limits = getattr(engine, "freshness_limits_seconds", None)
    if not isinstance(freshness_limits, MappingABC) or not freshness_limits:
        raise ValueError("mapping store validation engine must expose freshness_limits_seconds")
    for network_id, seconds in freshness_limits.items():
        if (not isinstance(network_id, str) or not network_id.strip()
                or isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0):
            raise ValueError("mapping store freshness_limits_seconds must contain positive integer network limits")


def require_ingestion_store(store: Any) -> None:
    """Fail early unless every worker/aggregator call shape is supported."""
    if any(not callable(getattr(store, name, None)) for name in _INGESTION_METHODS):
        raise ValueError("ingestion store does not satisfy the Module 9 ingestion protocol")

    calls = {
        "get_checkpoint": (("cursor-key",), {}),
        "commit_page": (
            ("cursor-key", {}, ()),
            {
                "expected_cursor": None,
                "scope_identity": ("network", "provider", "scope"),
                "allow_recanonicalized": False,
                "canonical_blocks": (),
                "canonical_slots": (),
                "provider_receipts": None,
            },
        ),
        "get_page_acceptance_material": (("cursor", "a" * 64), {}),
        "save_page_acceptance": (("cursor", "a" * 64, "key-v1", "{}", "a" * 64, "b" * 64), {}),
        "get_page_acceptance": (("cursor", "a" * 64), {}),
        "list_pending_page_acceptances": ((), {}),
        "list_ingestion_pages": ((), {}),
        "get_block_hash": (("network", "provider", "scope", 1), {}),
        "reconcile_block": (
            ("network", 1, "canonical-hash"),
            {"provider": "provider", "scope": "scope"},
        ),
        "get_solana_slot_journal": (("network", "provider", "scope", 1, 2), {}),
        "get_event": (("event-id", "network", "provider", "scope"), {}),
        "list_all_events": ((), {"canonical_only": True}),
    }
    for method_name, (args, kwargs) in calls.items():
        try:
            inspect.signature(getattr(store, method_name)).bind(*args, **kwargs)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"ingestion store {method_name} signature does not support the complete worker/aggregator call contract: {exc}"
            ) from None
