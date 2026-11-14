import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from layer1.event_graph import (
    EventGraph,
    EventIntelligenceGraphEngine,
    GraphEntity,
    GraphRelationship,
)
from layer1.foundation import AnnouncementEvidence, Layer1Store, MarketObservation, TrendSignal
from layer1.onchain import OnChainObservation, OnChainValidationResult


def iso(delta_seconds=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)).isoformat()


def announcement(source_id="article-1", title="Binance lists ABC Spot trading",
                 published_delta=-60, updated_at=None, content_hash="a" * 64):
    source_url = (
        "https://www.binance.com/en/support/announcement"
        if len(source_id) == 64 else
        "https://www.binance.com/en/support/announcement/" + source_id
    )
    return AnnouncementEvidence(
        source_id=source_id,
        source_url=source_url,
        publisher="Binance",
        event_type="listing",
        title=title,
        published_at=iso(published_delta),
        observed_at=iso(),
        asset_ids=("coingecko:abc",),
        content_hash=content_hash,
        updated_at=updated_at,
    )


def market():
    return MarketObservation(
        asset_id="coingecko:abc", provider="binance_spot", endpoint="/ticker",
        observed_at=iso(), price=1.25, currency="USDT",
    )


def trend(source, source_item_id, content_hash="b" * 64):
    return TrendSignal(
        topic="ABC listing", source=source, observed_at=iso(), rank=1,
        asset_ids=("coingecko:abc",), source_item_id=source_item_id,
        content_hash=content_hash,
    )


def onchain_observation():
    return OnChainObservation(
        observation_id="obs-abc-1", mapping_id="mapping-abc-1",
        asset_id="coingecko:abc", network_id="ethereum-mainnet", chain_id="1",
        provider="alchemy", endpoint_id="eth-mainnet-read", observation_type="transfer",
        block_height=100, block_hash="0x" + "a" * 64,
        transaction_hash="0x" + "b" * 64, block_time=iso(-30), observed_at=iso(),
        finality="FINALIZED", finality_reference="finalized-block-100",
    )


class EventIntelligenceGraphTests(unittest.TestCase):
    def test_builds_stable_typed_relationships_with_evidence_for_all_required_entity_kinds(self):
        observation = onchain_observation()
        project = GraphEntity("project", "project:abc", iso(), {"name": "ABC Project"})
        engine = EventIntelligenceGraphEngine()

        graph = engine.build(
            announcements=[announcement()], markets=[market()], trends=[trend("provider-a", "item-1")],
            onchain_observations=[observation],
            onchain_validation_results=[OnChainValidationResult(
                "ACCEPTED", "ONCHAIN_OBSERVATION_ACCEPTED", "test validation",
                observation.observation_id, observation.asset_id, observation.mapping_id,
                observation.network_id, observation.provider,
            )],
            project_entities=[project],
        )

        graph.validate()
        json.dumps(graph.to_dict(), sort_keys=True)
        entity_types = {entity.entity_type for entity in graph.entities}
        self.assertTrue({
            "asset", "project", "announcement", "event", "source",
            "market_observation", "onchain_observation", "trend_signal",
        }.issubset(entity_types))
        self.assertTrue(graph.relationships)
        for relationship in graph.relationships:
            self.assertTrue(relationship.evidence_ids)
            self.assertTrue(set(relationship.evidence_ids).issubset({e.stable_id for e in graph.entities}))
        onchain_edge = next(r for r in graph.relationships if r.relationship_type == "OBSERVES_ASSET")
        self.assertEqual(onchain_edge.status, "CONFIRMED")

        unverified_graph = engine.build(onchain_observations=[observation])
        unverified_edge = next(
            r for r in unverified_graph.relationships if r.relationship_type == "OBSERVES_ASSET"
        )
        self.assertEqual(unverified_edge.status, "POSSIBLE")

    def test_project_relationship_requires_an_existing_evidence_entity(self):
        evidence = announcement()
        project = GraphEntity("project", "project:abc", iso(), {"name": "ABC Project"})
        announcement_node = GraphEntity(
            "announcement", evidence.source_id + "|" + evidence.content_hash, evidence.observed_at,
        )
        asset_node = GraphEntity("asset", "coingecko:abc", evidence.observed_at)
        project_link = GraphRelationship(
            project.stable_id, "RELATED_TO", asset_node.stable_id,
            (announcement_node.stable_id,), evidence.observed_at, 0.7, "POSSIBLE",
        )

        graph = EventIntelligenceGraphEngine().build(
            announcements=[evidence], project_entities=[project],
            additional_relationships=[project_link],
        )

        self.assertIn(project_link.relationship_id, {r.relationship_id for r in graph.relationships})
        graph.validate()

    def test_relationships_require_evidence_and_reject_unsupported_causal_edges(self):
        with self.assertRaisesRegex(ValueError, "evidence"):
            GraphRelationship(
                "entity:a", "RELATED_TO", "entity:b", (), iso(), 0.5, "POSSIBLE",
            )
        with self.assertRaisesRegex(ValueError, "causal"):
            GraphRelationship(
                "entity:a", "CAUSES", "entity:b", ("evidence:1",), iso(), 0.9, "CONFIRMED",
            )

    def test_identical_copied_reports_cluster_without_losing_source_ancestry(self):
        signals = [trend("provider-a", "article-a"), trend("provider-b", "article-b")]
        graph = EventIntelligenceGraphEngine().build(trends=signals)

        duplicate_clusters = [e for e in graph.entities if e.entity_type == "duplicate_cluster"]
        self.assertEqual(len(duplicate_clusters), 1)
        cluster = duplicate_clusters[0]
        membership = [r for r in graph.relationships
                      if r.relationship_type == "MEMBER_OF_DUPLICATE_CLUSTER" and r.target_id == cluster.stable_id]
        self.assertEqual(len(membership), 2)
        self.assertEqual(cluster.attributes["independent_content_count"], 1)
        source_nodes = [e for e in graph.entities if e.entity_type == "source"]
        self.assertEqual({e.entity_id for e in source_nodes}, {"provider:provider-a", "provider:provider-b"})
        self.assertEqual(sum(r.relationship_type == "PROVIDED_BY" for r in graph.relationships), 2)

    def test_accepted_module9_summary_reference_enters_graph_and_unqualified_summary_is_rejected(self):
        reference = {
            "summary_id": "7" * 64, "asset_id": "coingecko:abc",
            "network_id": "ethereum-mainnet", "mapping_id": "mapping-abc-1",
            "observed_at": iso(), "representation": "erc20", "decimals": 18,
            "transfer_count": 4, "total_amount": "125.0", "minimum_amount": "100.0",
            "first_block_time": iso(-120), "last_block_time": iso(-30), "threshold_met": True,
        }
        graph = EventIntelligenceGraphEngine().build(onchain_summary_refs=[reference])
        summary_nodes = [
            entity for entity in graph.entities
            if entity.entity_type == "onchain_observation"
            and entity.attributes.get("record_kind") == "canonical_transfer_aggregation_summary"
        ]
        self.assertEqual(len(summary_nodes), 1)
        self.assertEqual(summary_nodes[0].attributes["mapping_id"], "mapping-abc-1")
        with self.assertRaisesRegex(ValueError, "threshold-qualified"):
            EventIntelligenceGraphEngine().build(
                onchain_summary_refs=[{**reference, "threshold_met": False}]
            )

    def test_stable_provider_revisions_are_linked_but_fingerprint_revisions_are_not(self):
        first = announcement("stable-article", published_delta=-300,
                             updated_at=iso(-200), content_hash="c" * 64)
        second = announcement("stable-article", published_delta=-300,
                              updated_at=iso(-100), content_hash="d" * 64)
        fingerprint_a = announcement("e" * 64, "ABC listing announced", content_hash="f" * 64)
        fingerprint_b = announcement("1" * 64, "ABC listing details updated", content_hash="2" * 64)

        graph = EventIntelligenceGraphEngine().build(
            announcements=[first, second, fingerprint_a, fingerprint_b]
        )

        updates = [r for r in graph.relationships if r.relationship_type == "UPDATES"]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].status, "CONFIRMED")
        self.assertEqual(len(updates[0].evidence_ids), 2)

    def test_stable_provider_revision_links_old_event_to_updated_event(self):
        first = announcement(
            "stable-update", "Binance announces ABC Spot listing", -300,
            updated_at=iso(-200), content_hash="5" * 64,
        )
        second = announcement(
            "stable-update", "Binance updates ABC Spot listing schedule", -300,
            updated_at=iso(-100), content_hash="6" * 64,
        )

        graph = EventIntelligenceGraphEngine().build(announcements=[first, second])
        event_ids = {entity.stable_id for entity in graph.entities if entity.entity_type == "event"}
        event_updates = [
            relationship for relationship in graph.relationships
            if relationship.relationship_type == "UPDATES"
            and relationship.source_id in event_ids and relationship.target_id in event_ids
        ]

        self.assertEqual(len(event_updates), 1)
        self.assertEqual(event_updates[0].status, "CONFIRMED")
        self.assertEqual(len(event_updates[0].evidence_ids), 2)

    def test_distinct_event_fingerprints_remain_distinct(self):
        first = announcement("article-one", "Binance lists ABC Spot trading", -3600, content_hash="3" * 64)
        second = announcement("article-two", "Binance delists ABC Spot trading", -3500, content_hash="4" * 64)

        graph = EventIntelligenceGraphEngine().build(announcements=[first, second])

        events = [entity for entity in graph.entities if entity.entity_type == "event"]
        self.assertEqual(len(events), 2)
        self.assertNotEqual(events[0].stable_id, events[1].stable_id)

    def test_graph_rebuilds_deterministically_from_persisted_source_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Layer1Store(os.path.join(directory, "layer1.db"))
            try:
                store.save_announcement(announcement())
                store.save_market(market())
                store.save_trend(trend("provider-a", "item-1"))

                engine = EventIntelligenceGraphEngine()
                first = engine.rebuild_from_store(store)
                second = engine.rebuild_from_store(store)

                self.assertEqual(
                    [(e.stable_id, e.entity_type) for e in first.entities],
                    [(e.stable_id, e.entity_type) for e in second.entities],
                )
                self.assertEqual(
                    [(r.relationship_id, r.evidence_ids) for r in first.relationships],
                    [(r.relationship_id, r.evidence_ids) for r in second.relationships],
                )
            finally:
                store.close()

    def test_relationship_confidence_and_timestamps_are_bounded_and_explicit(self):
        with self.assertRaisesRegex(ValueError, "confidence"):
            GraphRelationship(
                "entity:a", "RELATED_TO", "entity:b", ("evidence:1",), iso(), 1.1, "POSSIBLE",
            )
        with self.assertRaisesRegex(ValueError, "timezone"):
            GraphRelationship(
                "entity:a", "RELATED_TO", "entity:b", ("evidence:1",),
                "2026-11-14T12:00:00", 0.5, "POSSIBLE",
            )

    def test_graph_validation_rejects_dangling_relationship_evidence(self):
        source = GraphEntity("source", "source:a", iso())
        target = GraphEntity("asset", "coingecko:abc", iso())
        edge = GraphRelationship(
            source.stable_id, "RELATED_TO", target.stable_id,
            ("missing:evidence",), iso(), 0.5, "POSSIBLE",
        )
        graph = EventGraph((source, target), (edge,))

        with self.assertRaisesRegex(ValueError, "evidence reference"):
            graph.validate()


if __name__ == "__main__":
    unittest.main()
