import inspect
import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import main

from layer1.foundation import (
    AssetIdentity, CandidateDiscoveryFilteringEngine, EligibilityDecision,
    Layer1Store, MarketObservation, RelevanceScoringEngine,
)
from layer1.onchain_aggregation import NetworkTransferSummary, TransferAggregationResult

ASSET = "coingecko:bitcoin"
NOW = datetime.now(timezone.utc)


def decision(status="ELIGIBLE"):
    return EligibilityDecision(
        status, ASSET, "BTC", ("BTCUSDT",) if status == "ELIGIBLE" else (),
        verified_at=NOW.isoformat(),
        source="https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT",
        identity_proof_status="VERIFIED", identity_proof_source="coingecko_coin_tickers",
        identity_proof_verified_at=NOW.isoformat(), identity_proof_source_timestamp=NOW.isoformat(),
        identity_proof_data_hash="f" * 64,
    )


def summary(*, asset_id=ASSET, summary_id="a" * 64, threshold_met=True,
            total_amount="2.5", minimum_amount="1", last_block_time=None):
    last = last_block_time or (NOW - timedelta(minutes=2)).isoformat()
    last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    first = (last_dt - timedelta(minutes=3)).isoformat()
    return NetworkTransferSummary(
        summary_id=summary_id, asset_id=asset_id, binance_symbol="BTC",
        network_id="bitcoin-mainnet", mapping_id="btc-native-v1",
        representation="NATIVE", decimals=8, transfer_count=4,
        total_amount=total_amount, minimum_amount=minimum_amount,
        threshold_met=threshold_met, unique_source_address_count=2,
        unique_destination_address_count=4,
        first_block_time=first, last_block_time=last,
    )


def aggregation(*rows):
    return TransferAggregationResult(
        generated_at=NOW.isoformat(), assets=(), network_summaries=tuple(rows), deduplicated_events=0,
        rejected_events=0, rejection_counts=(),
    )


class OnChainCandidateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.identity = AssetIdentity(ASSET, "Bitcoin", "BTC", "USDT")
        self.eligibility = decision()
        self.market = MarketObservation(
            ASSET, "binance_spot", "/api/v3/ticker/price", NOW.isoformat(), price=65000,
        )
        self.builder = CandidateDiscoveryFilteringEngine()

    def test_qualified_onchain_summary_is_attached_as_corroboration_without_changing_candidate_identity(self):
        without = self.builder.build(self.identity, self.eligibility, [self.market], [], [])
        with_onchain = self.builder.build(
            self.identity, self.eligibility, [self.market], [], [],
            onchain_aggregation=aggregation(summary()),
        )
        self.assertEqual(without.candidate_id, with_onchain.candidate_id)
        self.assertEqual(without.state, with_onchain.state)
        self.assertEqual(with_onchain.onchain_transfer_summary_ids, ("a" * 64,))

    def test_onchain_only_does_not_create_a_discovery_candidate(self):
        candidate = self.builder.build(
            self.identity, self.eligibility, [], [], [],
            onchain_aggregation=aggregation(summary()),
        )
        self.assertEqual(candidate.state, "REJECTED")
        self.assertIn("no_source_backed_discovery_signal", candidate.rejection_reasons)
        self.assertEqual(candidate.onchain_transfer_summary_ids, ())

    def test_ineligible_binance_asset_cannot_receive_onchain_corroboration(self):
        candidate = self.builder.build(
            self.identity, decision("INELIGIBLE"), [self.market], [], [],
            onchain_aggregation=aggregation(summary()),
        )
        self.assertEqual(candidate.state, "REJECTED")
        self.assertEqual(candidate.onchain_transfer_summary_ids, ())

    def test_nonmatching_asset_and_below_threshold_summaries_are_not_attached(self):
        other_asset = summary(asset_id="coingecko:ethereum", summary_id="b" * 64)
        below_threshold = summary(summary_id="c" * 64, threshold_met=False, total_amount="0.5")
        candidate = self.builder.build(
            self.identity, self.eligibility, [self.market], [], [],
            onchain_aggregation=aggregation(other_asset, below_threshold),
        )
        self.assertEqual(candidate.onchain_transfer_summary_ids, ())

    def test_stale_or_future_onchain_summary_is_not_attached(self):
        stale = summary(last_block_time=(NOW - timedelta(days=2)).isoformat())
        future = summary(summary_id="d" * 64, last_block_time=(NOW + timedelta(hours=1)).isoformat())
        candidate = self.builder.build(
            self.identity, self.eligibility, [self.market], [], [],
            onchain_aggregation=aggregation(stale, future),
        )
        self.assertEqual(candidate.onchain_transfer_summary_ids, ())

    def test_stale_aggregation_or_spot_identity_proof_cannot_be_attached(self):
        stale_result = replace(aggregation(summary()), generated_at=(NOW - timedelta(minutes=10)).isoformat())
        stale_eligibility = replace(
            self.eligibility, verified_at=(NOW - timedelta(minutes=10)).isoformat())
        for result, current_eligibility in ((stale_result, self.eligibility),
                                            (aggregation(summary()), stale_eligibility)):
            candidate = self.builder.build(
                self.identity, current_eligibility, [self.market], [], [],
                onchain_aggregation=result,
            )
            self.assertEqual(candidate.onchain_transfer_summary_ids, ())

    def test_malformed_or_forged_aggregation_summary_fails_closed(self):
        with self.assertRaises(ValueError):
            self.builder.build(
                self.identity, self.eligibility, [self.market], [], [],
                onchain_aggregation={"threshold_met": True},
            )
        forged = summary(total_amount="0.5", minimum_amount="1", threshold_met=True)
        with self.assertRaisesRegex(ValueError, "threshold"):
            self.builder.build(
                self.identity, self.eligibility, [self.market], [], [],
                onchain_aggregation=aggregation(forged),
            )

    def test_summary_ids_are_persisted_as_auditable_candidate_evidence(self):
        candidate = self.builder.build(
            self.identity, self.eligibility, [self.market], [], [],
            onchain_aggregation=aggregation(summary()),
        )
        with tempfile.TemporaryDirectory() as directory:
            store = Layer1Store(os.path.join(directory, "layer1.sqlite3"))
            try:
                store.save_candidate(candidate)
                evidence = json.loads(store.conn.execute(
                    "SELECT evidence_refs_json FROM layer1_candidates WHERE candidate_id=?",
                    (candidate.candidate_id,),
                ).fetchone()[0])
                self.assertEqual(evidence["onchain_transfer_summaries"], ["a" * 64])
            finally:
                store.close()

    def test_main_pipeline_has_explicit_optional_aggregation_injection_and_rejects_invalid_input(self):
        self.assertIn("onchain_aggregation_by_asset", inspect.signature(main.run_once).parameters)
        self.assertIn("onchain_aggregation_by_asset", inspect.signature(main._persist_layer1_market_intelligence).parameters)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "invalid canonical asset/result pair"):
                main._persist_layer1_market_intelligence(
                    [], os.path.join(directory, "layer1.sqlite3"), [],
                    onchain_aggregation_by_asset={"not-a-canonical-id": object()},
                )

    def test_onchain_corroboration_does_not_change_relevance_score(self):
        without = self.builder.build(self.identity, self.eligibility, [self.market], [], [])
        with_onchain = self.builder.build(
            self.identity, self.eligibility, [self.market], [], [],
            onchain_aggregation=aggregation(summary()),
        )
        components = {
            "event_materiality": 70, "source_credibility": 80,
            "freshness": 90, "audience_relevance": 60, "novelty": 50,
        }
        engine = RelevanceScoringEngine()
        self.assertEqual(engine.score(without, components).score,
                         engine.score(with_onchain, components).score)


if __name__ == "__main__":
    unittest.main()
