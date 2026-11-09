import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from layer1.foundation import (
    AgentConfig, AnnouncementEvidence, AnnouncementIntelligenceEngine,
    AssetIdentity, BinanceListingEligibilityEngine, CandidateDiscoveryFilteringEngine,
    ConfigurationOrchestrator, MarketDataIntelligenceEngine, MarketObservation,
    RelevanceScoringEngine, RunLease, TrendSignal,
    TrendingNarrativeIntelligenceEngine,
)


def iso(delta_seconds=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)).isoformat()


class Layer1FoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "agent.db")
        self.identity = AssetIdentity("coingecko:bitcoin", "Bitcoin", "BTC", "USDT")

    def tearDown(self):
        self.tmp.cleanup()

    def test_module1_config_validation_and_run_context(self):
        with self.assertRaises(ValueError):
            AgentConfig(http_timeout_seconds=0).validate()
        cfg = AgentConfig(database_path=self.db)
        context = ConfigurationOrchestrator(cfg).create_context()
        self.assertTrue(context.run_id)
        self.assertEqual(len(context.config_hash), 64)

    def test_module1_persistent_lease_blocks_overlapping_run_and_releases(self):
        cfg = AgentConfig(database_path=self.db)
        context = ConfigurationOrchestrator(cfg).create_context()
        first = RunLease(self.db)
        second = RunLease(self.db)
        try:
            first.acquire(context)
            with self.assertRaisesRegex(RuntimeError, "lease already held"):
                second.acquire(ConfigurationOrchestrator(cfg).create_context())
            first.finish("SUCCEEDED", {"candidates": 0})
            second_context = ConfigurationOrchestrator(cfg).create_context()
            second.acquire(second_context)
            second.finish("SUCCEEDED")
        finally:
            first.close()
            second.close()
        conn = sqlite3.connect(self.db)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM layer1_run_lease").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM layer1_runs WHERE status='SUCCEEDED'").fetchone()[0], 2)
        finally:
            conn.close()

    def test_module2_market_data_requires_exact_asset_and_real_provider_payload(self):
        calls = []
        def fetch(url, timeout):
            calls.append((url, timeout))
            return {"symbol": "BTCUSDT", "lastPrice": "65000", "priceChangePercent": "1.5",
                    "quoteVolume": "1200000"}
        engine = MarketDataIntelligenceEngine(fetch)
        result = engine.fetch_binance_24h("BTCUSDT", self.identity.asset_id)
        self.assertEqual(result.price, 65000)
        self.assertEqual(result.asset_id, self.identity.asset_id)
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ValueError):
            MarketDataIntelligenceEngine(lambda *_: {"symbol": "ETHUSDT"}).fetch_binance_24h(
                "BTCUSDT", self.identity.asset_id
            )

    def test_module2_rejects_synthetic_or_invalid_history_values(self):
        item = MarketObservation(self.identity.asset_id, "provider", "/market", iso(),
                                 price=10, history=(10, -1))
        with self.assertRaises(ValueError):
            item.validate()

    def test_module3_exact_spot_pair_and_quote_asset_gate(self):
        engine = BinanceListingEligibilityEngine(("USDT",))
        payload = {"symbols": [
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
             "status": "TRADING", "isSpotTradingAllowed": True},
            {"symbol": "BTCUSDC", "baseAsset": "BTC", "quoteAsset": "USDC",
             "status": "TRADING", "isSpotTradingAllowed": True},
            {"symbol": "WBTCUSDT", "baseAsset": "WBTC", "quoteAsset": "USDT",
             "status": "TRADING", "isSpotTradingAllowed": True},
            {"symbol": "BTCUSDT_240628", "baseAsset": "BTC", "quoteAsset": "USDT",
             "status": "TRADING", "isSpotTradingAllowed": False},
        ]}
        eligible = engine.evaluate(self.identity, payload)
        self.assertEqual(eligible.status, "ELIGIBLE")
        self.assertEqual(eligible.eligible_pairs, ("BTCUSDT",))
        unavailable = engine.evaluate(self.identity, {})
        self.assertEqual(unavailable.status, "UNVERIFIED")
        inactive = engine.evaluate(self.identity, {"symbols": [
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
             "status": "BREAK", "isSpotTradingAllowed": True}
        ]})
        self.assertEqual(inactive.status, "INELIGIBLE")

    def test_module4_rejects_unofficial_announcement_sources(self):
        bad = AnnouncementEvidence("1", "https://binance.example/api", "Binance",
                                   "listing", "BTC listing", iso(), iso(), (self.identity.asset_id,))
        with self.assertRaises(ValueError):
            bad.validate()
        unavailable, status = AnnouncementIntelligenceEngine().fetch()
        self.assertEqual(unavailable, [])
        self.assertTrue(status.startswith("UNAVAILABLE"))

    def test_module4_accepts_official_attributable_announcement(self):
        evidence = AnnouncementEvidence(
            "article-1", "https://www.binance.com/en/support/announcement/example",
            "Binance", "listing", "BTC Spot listing", iso(-30), iso(),
            (self.identity.asset_id,), "sha256:abc"
        )
        evidence.validate()

    def test_module5_rejects_bad_timestamps_and_deduplicates_same_source_item(self):
        engine = TrendingNarrativeIntelligenceEngine()
        one = TrendSignal("BTC", "coingecko", iso(), 1, (self.identity.asset_id,), "cg-1")
        two = TrendSignal("BTC", "coingecko", iso(), 2, (self.identity.asset_id,), "cg-1")
        self.assertEqual(len(engine.normalize([one, two])), 1)
        with self.assertRaises(ValueError):
            engine.normalize([TrendSignal("BTC", "source", "not-a-time")])

    def test_module6_candidate_requires_eligibility_and_source_backed_signal(self):
        eligible = BinanceListingEligibilityEngine().evaluate(
            self.identity, {"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC",
             "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True}]}
        )
        market = MarketObservation(self.identity.asset_id, "binance_spot", "/ticker", iso(), price=65000)
        builder = CandidateDiscoveryFilteringEngine()
        accepted = builder.build(self.identity, eligible, [market], [], [])
        self.assertEqual(accepted.state, "READY_FOR_RESEARCH")
        self.assertEqual(accepted.asset_id, self.identity.asset_id)
        rejected = builder.build(self.identity, eligible, [], [], [])
        self.assertEqual(rejected.state, "REJECTED")
        self.assertIn("no_source_backed_discovery_signal", rejected.rejection_reasons)

    def test_module7_score_is_deterministic_explainable_and_never_overrides_hard_gate(self):
        eligibility = BinanceListingEligibilityEngine().evaluate(
            self.identity, {"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC",
             "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True}]}
        )
        market = MarketObservation(self.identity.asset_id, "binance_spot", "/ticker", iso(), price=65000)
        candidate = CandidateDiscoveryFilteringEngine().build(self.identity, eligibility, [market], [], [])
        components = {"event_materiality": 80, "source_credibility": 90, "freshness": 100,
                      "audience_relevance": 70, "novelty": 60}
        engine = RelevanceScoringEngine()
        first = engine.score(candidate, components)
        second = engine.score(candidate, components)
        self.assertEqual(first.score, second.score)
        self.assertEqual(first.score_version, second.score_version)
        deferred = engine.score(candidate, {**components, "freshness": None})
        self.assertEqual(deferred.score, 0.0)
        self.assertIn("deferred", deferred.reason)
        ineligible = CandidateDiscoveryFilteringEngine().build(
            self.identity,
            type(eligibility)("INELIGIBLE", self.identity.asset_id, "BTC", reason="not listed"),
            [market], [], []
        )
        self.assertEqual(engine.score(ineligible, components).score, 0.0)


if __name__ == "__main__":
    unittest.main()
