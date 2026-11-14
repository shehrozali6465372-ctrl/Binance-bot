"""Deterministic relational event graph built from persisted evidence.

The graph is a derived, auditable view. It deliberately uses the existing SQLite
Layer1Store and does not require a graph database or an LLM to infer edges.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from layer1.foundation import (
    AnnouncementEvidence,
    MarketObservation,
    TrendSignal,
)
from layer1.onchain import OnChainObservation, OnChainValidationResult


ENTITY_TYPES = {
    "asset", "project", "announcement", "event", "source",
    "market_observation", "onchain_observation", "trend_signal",
    "duplicate_cluster",
}
RELATIONSHIP_TYPES = {
    "PUBLISHED_BY", "DESCRIBES_EVENT", "EVENT_REFERENCES_ASSET",
    "OBSERVED_FOR_ASSET", "PROVIDED_BY", "SIGNALS_ASSET_ATTENTION",
    "OBSERVES_ASSET", "UPDATES", "MEMBER_OF_DUPLICATE_CLUSTER",
    "RELATED_TO",
}
CAUSAL_RELATIONSHIP_TYPES = {"CAUSES", "CAUSED_BY", "CAUSAL", "LEADS_TO", "DRIVES"}


def _parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("graph timestamp must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("graph timestamp must be valid ISO-8601") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("graph timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_safe(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("graph attributes must be a mapping")
    try:
        encoded = json.dumps(dict(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
        decoded = json.loads(encoded)
    except (TypeError, ValueError):
        raise ValueError("graph attributes must be finite JSON-safe data") from None
    return decoded


@dataclass(frozen=True)
class GraphEntity:
    entity_type: str
    entity_id: str
    observed_at: str
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    @property
    def stable_id(self) -> str:
        return "graph:" + self.entity_type + ":" + _digest(self.entity_type + "|" + self.entity_id)

    def validate(self) -> None:
        if not isinstance(self.entity_type, str) or self.entity_type not in ENTITY_TYPES:
            raise ValueError("unsupported graph entity type")
        if not isinstance(self.entity_id, str) or not self.entity_id.strip():
            raise ValueError("graph entity ID is required")
        _parse_timestamp(self.observed_at)
        _json_safe(self.attributes)


@dataclass(frozen=True)
class GraphRelationship:
    """Typed evidence edge; confidence is a deterministic weight, not a probability."""

    source_id: str
    relationship_type: str
    target_id: str
    evidence_ids: tuple[str, ...]
    observed_at: str
    confidence: float
    status: str

    def __post_init__(self) -> None:
        self.validate()

    @property
    def relationship_id(self) -> str:
        payload = json.dumps({
            "source_id": self.source_id,
            "relationship_type": self.relationship_type,
            "target_id": self.target_id,
            "evidence_ids": sorted(self.evidence_ids),
        }, sort_keys=True, separators=(",", ":"))
        return _digest(payload)

    def validate(self) -> None:
        if not isinstance(self.relationship_type, str):
            raise ValueError("graph relationship type must be a string")
        if self.relationship_type in CAUSAL_RELATIONSHIP_TYPES:
            raise ValueError("causal relationship edges are prohibited without a causal evidence contract")
        if self.relationship_type not in RELATIONSHIP_TYPES:
            raise ValueError("unsupported graph relationship type")
        if not all(isinstance(value, str) and value.strip()
                   for value in (self.source_id, self.target_id)):
            raise ValueError("graph relationship endpoints are required")
        if (not isinstance(self.evidence_ids, tuple) or not self.evidence_ids
                or any(not isinstance(item, str) or not item.strip() for item in self.evidence_ids)
                or len(set(self.evidence_ids)) != len(self.evidence_ids)):
            raise ValueError("graph relationship evidence references are required and unique")
        _parse_timestamp(self.observed_at)
        if (isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float))
                or not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0):
            raise ValueError("graph relationship confidence must be finite and between 0 and 1")
        if self.status not in {"CONFIRMED", "POSSIBLE", "UNKNOWN"}:
            raise ValueError("graph relationship status is invalid")


@dataclass(frozen=True)
class EventGraph:
    entities: tuple[GraphEntity, ...]
    relationships: tuple[GraphRelationship, ...]
    duplicate_cluster_ids: tuple[str, ...] = ()

    def validate(self) -> None:
        entity_ids = [entity.stable_id for entity in self.entities]
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("graph contains duplicate stable entity IDs")
        entity_id_set = set(entity_ids)
        for entity in self.entities:
            entity.validate()
        relationship_ids = []
        for relationship in self.relationships:
            relationship.validate()
            if relationship.source_id not in entity_id_set or relationship.target_id not in entity_id_set:
                raise ValueError("graph relationship contains a dangling entity reference")
            if not set(relationship.evidence_ids).issubset(entity_id_set):
                raise ValueError("graph relationship contains a dangling evidence reference")
            relationship_ids.append(relationship.relationship_id)
        if len(relationship_ids) != len(set(relationship_ids)):
            raise ValueError("graph contains duplicate stable relationship IDs")
        known_clusters = {
            entity.stable_id for entity in self.entities if entity.entity_type == "duplicate_cluster"
        }
        if not set(self.duplicate_cluster_ids).issubset(known_clusters):
            raise ValueError("graph duplicate cluster reference is unresolved")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "entities": [
                {
                    "id": entity.stable_id,
                    "type": entity.entity_type,
                    "entity_id": entity.entity_id,
                    "observed_at": entity.observed_at,
                    "attributes": _json_safe(entity.attributes),
                }
                for entity in self.entities
            ],
            "relationships": [
                {
                    "id": relationship.relationship_id,
                    "source_id": relationship.source_id,
                    "type": relationship.relationship_type,
                    "target_id": relationship.target_id,
                    "evidence_ids": list(relationship.evidence_ids),
                    "observed_at": relationship.observed_at,
                    "confidence": relationship.confidence,
                    "status": relationship.status,
                }
                for relationship in self.relationships
            ],
            "duplicate_cluster_ids": list(self.duplicate_cluster_ids),
        }


class EventIntelligenceGraphEngine:
    """Build a reproducible relationship graph from validated source records."""

    def build(
        self,
        *,
        announcements: Sequence[AnnouncementEvidence] = (),
        markets: Sequence[MarketObservation] = (),
        trends: Sequence[TrendSignal] = (),
        onchain_observations: Sequence[OnChainObservation] = (),
        onchain_validation_results: Sequence[OnChainValidationResult] = (),
        onchain_summary_refs: Sequence[Mapping[str, Any]] = (),
        project_entities: Sequence[GraphEntity] = (),
        additional_relationships: Sequence[GraphRelationship] = (),
    ) -> EventGraph:
        entities: dict[str, GraphEntity] = {}
        relationships: dict[str, GraphRelationship] = {}
        duplicate_cluster_ids: set[str] = set()
        duplicate_members: dict[str, dict[str, GraphEntity]] = {}

        def add_entity(entity: GraphEntity) -> GraphEntity:
            entity.validate()
            existing = entities.get(entity.stable_id)
            if existing is not None:
                if existing.attributes != entity.attributes:
                    raise ValueError("conflicting graph entity payload for a stable ID")
                earliest = min(
                    _parse_timestamp(existing.observed_at),
                    _parse_timestamp(entity.observed_at),
                ).isoformat()
                entity = GraphEntity(entity.entity_type, entity.entity_id, earliest, entity.attributes)
            entities[entity.stable_id] = entity
            return entity

        def add_relationship(relationship: GraphRelationship) -> None:
            relationship.validate()
            previous = relationships.get(relationship.relationship_id)
            if previous is None or _parse_timestamp(relationship.observed_at) > _parse_timestamp(previous.observed_at):
                relationships[relationship.relationship_id] = relationship
            elif (_parse_timestamp(relationship.observed_at) == _parse_timestamp(previous.observed_at)
                  and (relationship.status, relationship.confidence) > (previous.status, previous.confidence)):
                relationships[relationship.relationship_id] = relationship

        def add_source(source_key: str, observed_at: str, kind: str) -> GraphEntity:
            normalized_name = source_key.split(":", 1)[-1]
            return add_entity(GraphEntity(
                "source", source_key, observed_at,
                {"name": normalized_name, "source_kind": kind},
            ))

        def add_asset(asset_id: str, observed_at: str) -> GraphEntity:
            return add_entity(GraphEntity(
                "asset", asset_id, observed_at, {"canonical_asset_id": asset_id},
            ))

        def add_duplicate_member(content_hash: str, member_key: str, member: GraphEntity) -> None:
            if content_hash and re.fullmatch(r"[0-9a-f]{64}", content_hash):
                duplicate_members.setdefault(content_hash, {})[member_key] = member

        for project in project_entities:
            if project.entity_type != "project":
                raise ValueError("project_entities may contain only project graph entities")
            add_entity(project)

        revision_groups: dict[str, list[tuple[AnnouncementEvidence, GraphEntity]]] = {}
        revision_event_ids: dict[str, dict[str, str]] = {}
        for evidence in announcements:
            evidence.validate()
            revision_key = evidence.content_hash or _digest(json.dumps(
                evidence.__dict__, sort_keys=True, separators=(",", ":"), default=list
            ))
            announcement = add_entity(GraphEntity(
                "announcement", evidence.source_id + "|" + revision_key,
                evidence.observed_at,
                {
                    "source_id": evidence.source_id,
                    "source_id_kind": evidence.source_id_kind,
                    "source_url": evidence.source_url,
                    "publisher": evidence.publisher,
                    "event_type": evidence.event_type,
                    "title": evidence.title,
                    "content_hash": evidence.content_hash,
                    "raw_evidence_ref": evidence.raw_evidence_ref,
                    "revision_correlation_status": evidence.revision_correlation_status,
                },
            ))
            publisher_key = "publisher:" + evidence.publisher.casefold()
            publisher = add_source(publisher_key, evidence.observed_at, "publisher")
            add_relationship(GraphRelationship(
                announcement.stable_id, "PUBLISHED_BY", publisher.stable_id,
                (announcement.stable_id,), evidence.observed_at, 1.0, "CONFIRMED",
            ))
            if evidence.source_id_kind == "provider_id":
                revision_groups.setdefault(evidence.source_id, []).append((evidence, announcement))
            for asset_id in evidence.asset_ids:
                asset = add_asset(asset_id, evidence.observed_at)
                event_id = evidence.canonical_event_id(asset_id)
                event_time = evidence.event_at or evidence.published_at
                event_day = _parse_timestamp(event_time).date().isoformat()
                canonical_event_type = {"new_listing": "listing"}.get(evidence.event_type, evidence.event_type)
                event = add_entity(GraphEntity(
                    "event", event_id, event_day + "T00:00:00+00:00",
                    {"asset_id": asset_id, "event_type": canonical_event_type},
                ))
                revision_event_ids.setdefault(announcement.stable_id, {})[asset_id] = event.stable_id
                add_relationship(GraphRelationship(
                    announcement.stable_id, "DESCRIBES_EVENT", event.stable_id,
                    (announcement.stable_id,), evidence.observed_at, 1.0, "CONFIRMED",
                ))
                add_relationship(GraphRelationship(
                    event.stable_id, "EVENT_REFERENCES_ASSET", asset.stable_id,
                    (announcement.stable_id,), evidence.observed_at, 1.0, "CONFIRMED",
                ))
            add_duplicate_member(evidence.content_hash, "announcement:" + evidence.source_id, announcement)

        for source_id, revisions in revision_groups.items():
            unique: dict[str, tuple[AnnouncementEvidence, GraphEntity]] = {
                node.stable_id: (evidence, node) for evidence, node in revisions
            }
            ordered = sorted(
                unique.values(),
                key=lambda pair: (
                    _parse_timestamp(pair[0].updated_at or pair[0].published_at),
                    _parse_timestamp(pair[0].observed_at),
                    pair[1].stable_id,
                ),
            )
            for (previous_evidence, previous_node), (current_evidence, current_node) in zip(ordered, ordered[1:]):
                if previous_node.stable_id == current_node.stable_id:
                    continue
                add_relationship(GraphRelationship(
                    previous_node.stable_id, "UPDATES", current_node.stable_id,
                    (previous_node.stable_id, current_node.stable_id),
                    current_evidence.observed_at, 1.0, "CONFIRMED",
                ))
                previous_events = revision_event_ids.get(previous_node.stable_id, {})
                current_events = revision_event_ids.get(current_node.stable_id, {})
                for asset_id in sorted(set(previous_events) & set(current_events)):
                    previous_event_id = previous_events[asset_id]
                    current_event_id = current_events[asset_id]
                    if previous_event_id != current_event_id:
                        add_relationship(GraphRelationship(
                            previous_event_id, "UPDATES", current_event_id,
                            (previous_node.stable_id, current_node.stable_id),
                            current_evidence.observed_at, 1.0, "CONFIRMED",
                        ))

        for observation in markets:
            observation.validate()
            observation_key = _digest("|".join((
                observation.asset_id, observation.provider, observation.endpoint,
                observation.observed_at, observation.data_hash,
            )))
            node = add_entity(GraphEntity(
                "market_observation", observation_key, observation.observed_at,
                {
                    "asset_id": observation.asset_id,
                    "provider": observation.provider,
                    "endpoint": observation.endpoint,
                    "currency": observation.currency,
                    "source_timestamp": observation.source_timestamp or observation.published_at,
                    "data_hash": observation.data_hash,
                },
            ))
            asset = add_asset(observation.asset_id, observation.observed_at)
            source = add_source(
                "provider:" + observation.provider.casefold(), observation.observed_at, "provider",
            )
            add_relationship(GraphRelationship(
                node.stable_id, "OBSERVED_FOR_ASSET", asset.stable_id,
                (node.stable_id,), observation.observed_at, 1.0, "CONFIRMED",
            ))
            add_relationship(GraphRelationship(
                node.stable_id, "PROVIDED_BY", source.stable_id,
                (node.stable_id,), observation.observed_at, 1.0, "CONFIRMED",
            ))

        for signal in trends:
            signal.validate()
            signal_key = _digest("|".join((
                signal.source, signal.source_item_id, signal.topic,
                signal.content_hash, signal.observed_at,
            )))
            node = add_entity(GraphEntity(
                "trend_signal", signal_key, signal.observed_at,
                {
                    "topic": signal.topic,
                    "source": signal.source,
                    "source_item_id": signal.source_item_id,
                    "content_hash": signal.content_hash,
                    "confidence_limit": "ATTENTION_ONLY_NOT_EVENT_PROOF",
                },
            ))
            source = add_source(
                "provider:" + signal.source.casefold(), signal.observed_at, "provider",
            )
            add_relationship(GraphRelationship(
                node.stable_id, "PROVIDED_BY", source.stable_id,
                (node.stable_id,), signal.observed_at, 1.0, "CONFIRMED",
            ))
            for asset_id in signal.asset_ids:
                asset = add_asset(asset_id, signal.observed_at)
                add_relationship(GraphRelationship(
                    node.stable_id, "SIGNALS_ASSET_ATTENTION", asset.stable_id,
                    (node.stable_id,), signal.observed_at, 0.5, "POSSIBLE",
                ))
            add_duplicate_member(signal.content_hash, "trend:" + signal.source + ":" + signal.source_item_id, node)

        validations_by_id: dict[str, OnChainValidationResult] = {}
        for result in onchain_validation_results:
            if not isinstance(result, OnChainValidationResult) or not result.observation_id:
                raise ValueError("on-chain validation inputs must be attributable Module 9 results")
            previous_result = validations_by_id.get(result.observation_id)
            if previous_result is not None and previous_result != result:
                raise ValueError("conflicting Module 9 validation results for one observation")
            validations_by_id[result.observation_id] = result
        for observation in onchain_observations:
            if not isinstance(observation, OnChainObservation):
                raise ValueError("on-chain graph inputs must be OnChainObservation records")
            if not observation.observation_id or not observation.asset_id or not observation.network_id:
                raise ValueError("on-chain graph observation identity is incomplete")
            _parse_timestamp(observation.observed_at)
            _parse_timestamp(observation.block_time)
            validation = validations_by_id.get(observation.observation_id)
            confirmed = bool(
                validation and validation.status == "ACCEPTED"
                and validation.asset_id == observation.asset_id
                and validation.mapping_id == observation.mapping_id
                and validation.network_id == observation.network_id
                and validation.provider == observation.provider
            )
            node = add_entity(GraphEntity(
                "onchain_observation", observation.network_id + ":" + observation.observation_id,
                observation.observed_at,
                {
                    "asset_id": observation.asset_id,
                    "network_id": observation.network_id,
                    "mapping_id": observation.mapping_id,
                    "provider": observation.provider,
                    "transaction_hash": observation.transaction_hash,
                    "block_height": observation.block_height,
                    "block_hash": observation.block_hash,
                    "finality": observation.finality,
                    "validation_status": "ACCEPTED" if confirmed else "NOT_VERIFIED_BY_MODULE9",
                },
            ))
            asset = add_asset(observation.asset_id, observation.observed_at)
            source = add_source(
                "provider:" + observation.provider.casefold(), observation.observed_at, "provider",
            )
            add_relationship(GraphRelationship(
                node.stable_id, "OBSERVES_ASSET", asset.stable_id,
                (node.stable_id,), observation.observed_at,
                1.0 if confirmed else 0.5, "CONFIRMED" if confirmed else "POSSIBLE",
            ))
            add_relationship(GraphRelationship(
                node.stable_id, "PROVIDED_BY", source.stable_id,
                (node.stable_id,), observation.observed_at, 1.0, "CONFIRMED",
            ))

        for summary in onchain_summary_refs:
            if not isinstance(summary, Mapping):
                raise ValueError("on-chain summary graph references must be mappings")
            required = ("summary_id", "asset_id", "network_id", "mapping_id", "observed_at")
            if not all(isinstance(summary.get(key), str) and summary.get(key).strip() for key in required):
                raise ValueError("on-chain summary graph reference identity is incomplete")
            if summary.get("threshold_met") is not True:
                raise ValueError("only threshold-qualified on-chain summaries may enter the graph")
            if (not re.fullmatch(r"[0-9a-f]{64}", summary["summary_id"])
                    or not summary["asset_id"].startswith("coingecko:")):
                raise ValueError("on-chain summary IDs and asset IDs must be canonical")
            decimals = summary.get("decimals")
            transfer_count = summary.get("transfer_count")
            if (isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 36
                    or isinstance(transfer_count, bool) or not isinstance(transfer_count, int)
                    or transfer_count <= 0):
                raise ValueError("on-chain summary decimals or transfer count is invalid")
            try:
                total_amount = Decimal(str(summary.get("total_amount")))
                minimum_amount = Decimal(str(summary.get("minimum_amount")))
            except (InvalidOperation, TypeError, ValueError):
                raise ValueError("on-chain summary amounts are invalid") from None
            if (not total_amount.is_finite() or not minimum_amount.is_finite()
                    or total_amount <= 0 or minimum_amount <= 0 or total_amount < minimum_amount):
                raise ValueError("on-chain summary amounts do not satisfy the explicit threshold")
            first_block_time = _parse_timestamp(summary.get("first_block_time"))
            last_block_time = _parse_timestamp(summary.get("last_block_time"))
            if first_block_time > last_block_time:
                raise ValueError("on-chain summary block-time range is invalid")
            _parse_timestamp(summary["observed_at"])
            node = add_entity(GraphEntity(
                "onchain_observation", "summary:" + summary["network_id"] + ":" + summary["summary_id"],
                summary["observed_at"],
                {
                    "record_kind": "canonical_transfer_aggregation_summary",
                    "asset_id": summary["asset_id"],
                    "network_id": summary["network_id"],
                    "mapping_id": summary["mapping_id"],
                    "representation": summary.get("representation", ""),
                    "decimals": summary.get("decimals"),
                    "transfer_count": summary.get("transfer_count"),
                    "total_amount": summary.get("total_amount"),
                    "minimum_amount": summary.get("minimum_amount"),
                    "first_block_time": summary.get("first_block_time", ""),
                    "last_block_time": summary.get("last_block_time", ""),
                    "threshold_met": True,
                },
            ))
            asset = add_asset(summary["asset_id"], summary["observed_at"])
            source = add_source("provider:module9_canonical_store", summary["observed_at"], "onchain_store")
            add_relationship(GraphRelationship(
                node.stable_id, "OBSERVES_ASSET", asset.stable_id,
                (node.stable_id,), summary["observed_at"], 1.0, "CONFIRMED",
            ))
            add_relationship(GraphRelationship(
                node.stable_id, "PROVIDED_BY", source.stable_id,
                (node.stable_id,), summary["observed_at"], 1.0, "CONFIRMED",
            ))

        for relationship in additional_relationships:
            add_relationship(relationship)

        for content_hash, members in sorted(duplicate_members.items()):
            distinct_sources = len(members)
            if distinct_sources < 2:
                continue
            observed_at = max(
                members.values(), key=lambda item: _parse_timestamp(item.observed_at)
            ).observed_at
            cluster = add_entity(GraphEntity(
                "duplicate_cluster", "content:" + content_hash, observed_at,
                {
                    "content_hash": content_hash,
                    "member_count": distinct_sources,
                    "independent_content_count": 1,
                    "cluster_basis": "exact_content_hash",
                    "independence_warning": "Identical content is one content lineage, not independent corroboration.",
                },
            ))
            duplicate_cluster_ids.add(cluster.stable_id)
            for member in members.values():
                add_relationship(GraphRelationship(
                    member.stable_id, "MEMBER_OF_DUPLICATE_CLUSTER", cluster.stable_id,
                    (member.stable_id,), member.observed_at, 1.0, "CONFIRMED",
                ))

        graph = EventGraph(
            entities=tuple(sorted(entities.values(), key=lambda item: (item.entity_type, item.stable_id))),
            relationships=tuple(sorted(relationships.values(), key=lambda item: item.relationship_id)),
            duplicate_cluster_ids=tuple(sorted(duplicate_cluster_ids)),
        )
        graph.validate()
        return graph

    def rebuild_from_store(
        self,
        store: Any,
        *,
        onchain_observations: Sequence[OnChainObservation] = (),
        onchain_validation_results: Sequence[OnChainValidationResult] = (),
        onchain_summary_refs: Sequence[Mapping[str, Any]] = (),
        project_entities: Sequence[GraphEntity] = (),
        additional_relationships: Sequence[GraphRelationship] = (),
    ) -> EventGraph:
        """Rebuild from the source records already persisted by Layer1Store.

        On-chain observations live in the dedicated Module 9 store, so callers
        supply those persisted records explicitly rather than inventing them.
        """
        connection = store.conn
        announcements = []
        for (payload,) in connection.execute(
            "SELECT payload_json FROM layer1_announcement_revisions "
            "ORDER BY source_id, first_seen_at, revision_key"
        ).fetchall():
            decoded = json.loads(payload)
            decoded["asset_ids"] = tuple(decoded.get("asset_ids") or ())
            announcements.append(AnnouncementEvidence(**decoded))

        markets = []
        for (payload,) in connection.execute(
            "SELECT payload_json FROM layer1_market_observations "
            "ORDER BY observed_at, provider, observation_key"
        ).fetchall():
            decoded = json.loads(payload)
            decoded["history"] = tuple(decoded.get("history") or ())
            markets.append(MarketObservation(**decoded))

        trends = []
        for (payload,) in connection.execute(
            "SELECT payload_json FROM layer1_trend_signals "
            "ORDER BY observed_at, signal_key"
        ).fetchall():
            decoded = json.loads(payload)
            decoded["asset_ids"] = tuple(decoded.get("asset_ids") or ())
            trends.append(TrendSignal(**decoded))

        return self.build(
            announcements=announcements,
            markets=markets,
            trends=trends,
            onchain_observations=onchain_observations,
            onchain_validation_results=onchain_validation_results,
            onchain_summary_refs=onchain_summary_refs,
            project_entities=project_entities,
            additional_relationships=additional_relationships,
        )
