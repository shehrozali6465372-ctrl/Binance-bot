import ast
import json
import time
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

import main
from datetime import datetime, timedelta, timezone

from layer1.foundation import (
    AgentConfig, AnnouncementEvidence, AnnouncementIntelligenceEngine,
    AssetIdentity, BinanceListingEligibilityEngine, CandidateDiscoveryFilteringEngine,
    ConfigurationOrchestrator, Layer1Store, MarketDataIntelligenceEngine, MarketObservation,
    RelevanceScoringEngine, RunLease, TrendSignal,
    TrendingNarrativeIntelligenceEngine,
)


def iso(delta_seconds=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)).isoformat()


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.payload


class AgentConfigShim:
    live_market_data = True
    http_timeout_seconds = 1


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

    def test_module1_live_mode_requires_generation_and_publisher_credentials(self):
        with self.assertRaisesRegex(ValueError, "GEMINI_API_KEY"):
            replace(main.CONFIG, dry_run=False, gemini_api_key="", square_api_key="configured").validate()
        with self.assertRaisesRegex(ValueError, "SQUARE_API_KEY"):
            replace(main.CONFIG, dry_run=False, gemini_api_key="configured", square_api_key="").validate()
        replace(main.CONFIG, dry_run=True, gemini_api_key="", square_api_key="").validate()

    def test_module1_boolean_environment_values_are_strict(self):
        self.assertTrue(main._parse_env_bool("DRY_RUN", "true", default=False))
        self.assertFalse(main._parse_env_bool("DRY_RUN", "0", default=True))
        with self.assertRaisesRegex(ValueError, "DRY_RUN"):
            main._parse_env_bool("DRY_RUN", "sometimes", default=True)
        with self.assertRaisesRegex(ValueError, "DRY_RUN"):
            AgentConfig.from_env({"DRY_RUN": "sometimes"})

    def test_module1_application_config_rejects_invalid_operational_limits(self):
        for changes in (
            {"max_daily_posts": 0},
            {"database_path": ""},
            {"publish_log_path": ""},
            {"min_cap_for_safety": 0},
            {"repetition_soft_hours": 1, "repetition_hard_hours": 2},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    replace(main.CONFIG, **changes).validate()

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
                    "quoteVolume": "1200000", "closeTime": int(time.time() * 1000)}
        engine = MarketDataIntelligenceEngine(fetch)
        result = engine.fetch_binance_24h("BTCUSDT", self.identity.asset_id)
        self.assertEqual(result.price, 65000)
        self.assertEqual(result.asset_id, self.identity.asset_id)
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ValueError):
            MarketDataIntelligenceEngine(lambda *_: {"symbol": "ETHUSDT"}).fetch_binance_24h(
                "BTCUSDT", self.identity.asset_id
            )

    def test_market_and_trend_evidence_rejects_future_timestamps(self):
        future = iso(3600)
        market = MarketObservation(self.identity.asset_id, "provider", "/market", future, price=10)
        with self.assertRaisesRegex(ValueError, "future"):
            market.validate()
        with self.assertRaisesRegex(ValueError, "future"):
            TrendSignal("BTC", "source", future).validate()

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
        eligible = engine.evaluate(self.identity, payload, verified_at=iso())
        self.assertEqual(eligible.status, "ELIGIBLE")
        self.assertEqual(eligible.eligible_pairs, ("BTCUSDT",))
        unavailable = engine.evaluate(self.identity, {})
        self.assertEqual(unavailable.status, "UNVERIFIED")
        inactive = engine.evaluate(self.identity, {"symbols": [
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
             "status": "BREAK", "isSpotTradingAllowed": True}
        ]}, verified_at=iso())
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
             "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True}]},
            verified_at=iso()
        )
        market = MarketObservation(self.identity.asset_id, "binance_spot", "/ticker", iso(), price=65000)
        builder = CandidateDiscoveryFilteringEngine()
        accepted = builder.build(self.identity, eligible, [market], [], [])
        self.assertEqual(accepted.state, "READY_FOR_RESEARCH")
        self.assertEqual(accepted.asset_id, self.identity.asset_id)
        rejected = builder.build(self.identity, eligible, [], [], [])
        self.assertEqual(rejected.state, "REJECTED")
        self.assertIn("no_source_backed_discovery_signal", rejected.rejection_reasons)

    def test_legacy_market_scanner_has_no_synthetic_or_sample_fallback(self):
        scanner = main.MarketScanner(AgentConfigShim())
        self.assertEqual(scanner._build_universe(), [])
        self.assertEqual(scanner._synthetic_history(100, 10), [])
        with patch("main._get_binance_listed", return_value={"BTC"}), patch("main.http_get_json", side_effect=RuntimeError("provider unavailable")):
            self.assertEqual(scanner._coingecko_universe(), [])

    def test_legacy_listing_check_fails_closed_without_static_allowlist(self):
        main._binance_listed_cache = None
        main._binance_listed_cache_time = 0
        with patch("main.urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertEqual(main._get_binance_listed(), set())

    def test_legacy_listing_snapshot_requires_fresh_server_time_and_quote_asset(self):
        payload = {"serverTime": int(time.time() * 1000), "symbols": [
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
             "status": "TRADING", "isSpotTradingAllowed": True},
            {"symbol": "BTCUSDC", "baseAsset": "BTC", "quoteAsset": "USDC",
             "status": "TRADING", "isSpotTradingAllowed": True},
        ]}
        main._binance_listed_cache = None
        with patch("main.urllib.request.urlopen", return_value=FakeHTTPResponse(payload)):
            self.assertEqual(main._get_binance_listed(), {"BTC"})
        stale = {**payload, "serverTime": int((time.time() - 3600) * 1000)}
        main._binance_listed_cache = None
        with patch("main.urllib.request.urlopen", return_value=FakeHTTPResponse(stale)):
            self.assertEqual(main._get_binance_listed(), set())

    def test_module1_iteration_failure_logs_redact_untrusted_exception_text(self):
        secret = "provider-token-super-secret"
        with self.assertLogs("agent", level="ERROR") as captured:
            main._log_iteration_failure(3, RuntimeError(f"request failed with {secret}"))
        output = "\n".join(captured.output)
        self.assertIn("RuntimeError", output)
        self.assertIn("redacted", output.lower())
        self.assertNotIn(secret, output)

    def test_run_once_rejects_invalid_config_before_database_or_candidate_processing(self):
        cfg = replace(main.CONFIG, database_path=self.db, max_daily_posts=0, dry_run=True)
        with patch("main._run_once_impl") as runtime:
            with self.assertRaisesRegex(ValueError, "MAX_DAILY_POSTS"):
                main.run_once(cfg, None, None, None, None, None, set())
            runtime.assert_not_called()
        self.assertFalse(os.path.exists(self.db))

    def test_run_once_blocks_execution_when_another_process_holds_lease(self):
        cfg = replace(main.CONFIG, database_path=self.db, dry_run=True)
        active = RunLease(self.db)
        active_context = ConfigurationOrchestrator(AgentConfig(database_path=self.db)).create_context()
        try:
            active.acquire(active_context)
            with patch("main._run_once_impl") as runtime:
                with self.assertRaisesRegex(RuntimeError, "lease already held"):
                    main.run_once(cfg, None, None, None, None, None, set())
                runtime.assert_not_called()
            self.assertEqual(active.inspect_active()["run_id"], active_context.run_id)
        finally:
            active.finish("INTERRUPTED", {"reason": "test cleanup"})
            active.close()

    def test_run_once_integrates_layer1_run_lease(self):
        cfg = replace(main.CONFIG, database_path=self.db, dry_run=True)
        previous_summary = main._LAYER1_LAST_SUMMARY

        def fake_runtime(*args):
            main._LAYER1_LAST_SUMMARY = {
                "provider_health": {"coingecko_market_data": "AVAILABLE"},
                "rejected_inputs": 1,
            }
            return True

        with patch("main._run_once_impl", side_effect=fake_runtime):
            self.assertTrue(main.run_once(cfg, None, None, None, None, None, set()))
        conn = sqlite3.connect(self.db)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM layer1_run_lease").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM layer1_runs WHERE status='SUCCEEDED'").fetchone()[0], 1)
            summary_json = conn.execute(
                "SELECT summary_json FROM layer1_runs WHERE status='SUCCEEDED'"
            ).fetchone()[0]
            summary = json.loads(summary_json)
            self.assertEqual(
                summary["layer1"]["provider_health"]["coingecko_market_data"], "AVAILABLE"
            )
            self.assertEqual(summary["layer1"]["rejected_inputs"], 1)
        finally:
            main._LAYER1_LAST_SUMMARY = previous_summary
            conn.close()
    def test_run_once_redacts_credentials_from_persisted_failure_summary(self):
        cfg = replace(main.CONFIG, database_path=self.db, dry_run=True)
        secret = "sk-live-super-secret-value"
        with patch("main._run_once_impl", side_effect=RuntimeError(f"provider rejected key {secret}")):
            with self.assertRaisesRegex(RuntimeError, "provider rejected"):
                main.run_once(cfg, None, None, None, None, None, set())
        conn = sqlite3.connect(self.db)
        try:
            summary_json = conn.execute(
                "SELECT summary_json FROM layer1_runs WHERE status='FAILED'"
            ).fetchone()[0]
            self.assertNotIn(secret, summary_json)
            self.assertIn("inspect secured runtime logs", summary_json)
        finally:
            conn.close()

    def test_run_once_surfaces_lease_finalization_failure_after_successful_runtime(self):
        cfg = replace(main.CONFIG, database_path=self.db, dry_run=True)
        with patch("main._run_once_impl", return_value=True), \
             patch("layer1.foundation.RunLease.finish", side_effect=OSError("database finalize failure")):
            with self.assertRaisesRegex(OSError, "database finalize failure"):
                main.run_once(cfg, None, None, None, None, None, set())
        conn = sqlite3.connect(self.db)
        try:
            self.assertEqual(conn.execute("SELECT status FROM layer1_runs").fetchone()[0], "RUNNING")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM layer1_run_lease").fetchone()[0], 1)
            # Simulate explicit operator recovery for test isolation only.
            conn.execute("DELETE FROM layer1_run_lease")
            conn.execute("UPDATE layer1_runs SET status='INTERRUPTED', finished_at=?", (iso(),))
            conn.commit()
        finally:
            conn.close()

    def test_run_once_preserves_primary_error_if_lease_finalization_also_fails(self):
        cfg = replace(main.CONFIG, database_path=self.db, dry_run=True)
        with patch("main._run_once_impl", side_effect=RuntimeError("primary runtime failure")), \
             patch("layer1.foundation.RunLease.finish", side_effect=OSError("database finalize failure")):
            with self.assertRaisesRegex(RuntimeError, "primary runtime failure"):
                main.run_once(cfg, None, None, None, None, None, set())

    def test_run_once_redacts_primary_and_finalization_errors_from_logs(self):
        cfg = replace(main.CONFIG, database_path=self.db, dry_run=True)
        primary_secret = "primary-provider-secret"
        database_secret = "database-connection-secret"
        with patch("main._run_once_impl", side_effect=RuntimeError(primary_secret)), \
             patch("layer1.foundation.RunLease.finish", side_effect=OSError(database_secret)):
            with self.assertLogs("agent", level="ERROR") as captured:
                with self.assertRaisesRegex(RuntimeError, primary_secret):
                    main.run_once(cfg, None, None, None, None, None, set())
        output = "\n".join(captured.output)
        self.assertIn("finalize", output.lower())
        self.assertNotIn(primary_secret, output)
        self.assertNotIn(database_secret, output)

    def test_run_once_preserves_process_exit_if_lease_finalization_also_fails(self):
        cfg = replace(main.CONFIG, database_path=self.db, dry_run=True)
        with patch("main._run_once_impl", side_effect=SystemExit(2)), \
             patch("layer1.foundation.RunLease.finish", side_effect=OSError("database finalize failure")):
            with self.assertRaises(SystemExit) as raised:
                main.run_once(cfg, None, None, None, None, None, set())
        self.assertEqual(raised.exception.code, 2)
        conn = sqlite3.connect(self.db)
        try:
            self.assertEqual(conn.execute("SELECT status FROM layer1_runs").fetchone()[0], "RUNNING")
            conn.execute("DELETE FROM layer1_run_lease")
            conn.execute("UPDATE layer1_runs SET status='INTERRUPTED', finished_at=?", (iso(),))
            conn.commit()
        finally:
            conn.close()

    def test_run_once_records_keyboard_interrupt_as_interrupted(self):
        cfg = replace(main.CONFIG, database_path=self.db, dry_run=True)
        with patch("main._run_once_impl", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                main.run_once(cfg, None, None, None, None, None, set())
        conn = sqlite3.connect(self.db)
        try:
            status = conn.execute("SELECT status FROM layer1_runs").fetchone()[0]
            self.assertEqual(status, "INTERRUPTED")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM layer1_run_lease").fetchone()[0], 0)
        finally:
            conn.close()

    def test_legacy_candidate_filter_requires_canonical_asset_identity(self):
        with patch("main._get_binance_listed", return_value={"BTC"}):
            accepted = main._passes_objective_filters(
                symbol="BTC", price=65000, change_24h=8, volume_ratio=2,
                market_cap=1_000_000_000, announcements=[], posted_hours_data={},
                asset_id="",
            )
            self.assertFalse(accepted)

    def test_legacy_announcement_bapi_is_disabled_without_network(self):
        engine = main.BinanceAnnouncementEngine()
        with patch("main.http_get_json") as fetch:
            self.assertEqual(engine.fetch_announcements(48), [])
        fetch.assert_not_called()

    def test_hot_search_does_not_invoke_synthetic_provider(self):
        engine = main.HotSearchEngine()
        with patch.object(engine, "_from_announcements", return_value=[]), patch.object(engine, "_from_coingecko_trending", return_value=[]), patch.object(engine, "_from_market_data", return_value=[]), patch.object(engine, "_synthetic_topics", side_effect=AssertionError("synthetic called")):
            self.assertEqual(engine.get_trending(force_refresh=True), [])

    def test_runtime_layer1_pipeline_persists_exact_exchange_pair_and_market_provenance(self):
        coin = main.Coin("BTC", "Bitcoin", 65000, 1.2, 1_000_000, 1.5, 1_200_000_000_000, [64000, 65000])
        coin.asset_id = "coingecko:bitcoin"
        coin.observed_at = iso()
        coin.market_data_source = "coingecko_markets"
        coin.provider_published_at = iso()
        coin.market_data_hash = "sha256:market-fixture"
        old_pairs = main._binance_spot_pairs_cache
        old_snapshot = main._binance_spot_snapshot_observed_at
        main._binance_spot_snapshot_observed_at = iso()
        main._binance_spot_pairs_cache = {"BTC": [{
            "symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
            "status": "TRADING", "isSpotTradingAllowed": True
        }]}
        try:
            trend = {
                "topic": "BTC", "source": "coingecko_trending",
                "source_item_id": "bitcoin", "asset_id": "coingecko:bitcoin",
                "observed_at": iso(), "rank": 1,
            }
            result = main._persist_layer1_market_intelligence([coin], self.db, [trend])
            self.assertEqual(result["observations"], 1)
            self.assertEqual(result["trends"], 1)
            self.assertEqual(result["candidates"], 1)
            self.assertEqual(result["ready_asset_ids"], ["coingecko:bitcoin"])
            self.assertEqual(result["provider_health"]["binance_spot_metadata"], "AVAILABLE")
            self.assertEqual(result["provider_health"]["coingecko_market_data"], "AVAILABLE")
            self.assertEqual(result["provider_health"]["coingecko_trending"], "AVAILABLE")
            self.assertEqual(
                result["provider_health"]["binance_announcements"],
                "UNAVAILABLE_NO_VERIFIED_DOCUMENTED_ADAPTER",
            )
            conn = sqlite3.connect(self.db)
            try:
                row = conn.execute("SELECT state, evidence_refs_json FROM layer1_candidates").fetchone()
                self.assertEqual(row[0], "READY_FOR_RESEARCH")
                self.assertIn("BTCUSDT", row[1])
                self.assertIn("coingecko:bitcoin", row[1])
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM layer1_trend_signals").fetchone()[0], 1)
                score = conn.execute("SELECT score, reason FROM layer1_candidate_scores").fetchone()
                self.assertEqual(score[0], 0.0)
                self.assertIn("deferred", score[1])
            finally:
                conn.close()
        finally:
            main._binance_spot_pairs_cache = old_pairs
            main._binance_spot_snapshot_observed_at = old_snapshot

    def test_layer1_store_persists_source_provenance_candidate_reasons_and_score_version(self):
        eligibility = BinanceListingEligibilityEngine().evaluate(
            self.identity, {"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC",
             "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True}]},
            verified_at=iso()
        )
        market = MarketObservation(self.identity.asset_id, "binance_spot", "/ticker", iso(), price=65000)
        candidate = CandidateDiscoveryFilteringEngine().build(self.identity, eligibility, [market], [], [])
        score = RelevanceScoringEngine().score(candidate, {
            "event_materiality": 80, "source_credibility": 90, "freshness": 100,
            "audience_relevance": 70, "novelty": 60,
        })
        store = Layer1Store(self.db)
        try:
            store.save_market(market)
            store.save_candidate(candidate)
            store.save_score(score)
            self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM layer1_market_observations").fetchone()[0], 1)
            row = store.conn.execute("SELECT state, evidence_refs_json FROM layer1_candidates WHERE candidate_id=?",
                                     (candidate.candidate_id,)).fetchone()
            self.assertEqual(row[0], "READY_FOR_RESEARCH")
            saved = store.conn.execute("SELECT score, score_version FROM layer1_candidate_scores WHERE candidate_id=?",
                                       (candidate.candidate_id,)).fetchone()
            self.assertEqual(saved[1], score.score_version)
            self.assertEqual(saved[0], score.score)
        finally:
            store.close()
    def test_module7_score_is_deterministic_explainable_and_never_overrides_hard_gate(self):
        eligibility = BinanceListingEligibilityEngine().evaluate(
            self.identity, {"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC",
             "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True}]},
            verified_at=iso()
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



    def test_config_hash_includes_safe_runtime_metadata_without_secrets(self):
        cfg = AgentConfig(database_path=self.db)
        orchestrator = ConfigurationOrchestrator(cfg)
        base = orchestrator.create_context({"model": "model-a", "api_key_configured": True})
        changed = orchestrator.create_context({"model": "model-b", "api_key_configured": True})
        self.assertNotEqual(base.config_hash, changed.config_hash)
        with self.assertRaises(ValueError):
            orchestrator.create_context({"unsafe": float("nan")})

    def test_run_lease_inspection_reports_orphaned_running_record_without_releasing_it(self):
        cfg = AgentConfig(database_path=self.db)
        context = ConfigurationOrchestrator(cfg).create_context()
        lease = RunLease(self.db)
        try:
            lease.acquire(context)
            # Simulate a process crash: close the connection without finish().
            lease.close()
            inspector = RunLease(self.db)
            try:
                active = inspector.inspect_active()
                self.assertEqual(active["run_id"], context.run_id)
                self.assertEqual(active["status"], "RUNNING")
                self.assertEqual(active["acquired_at"], context.started_at)
                self.assertEqual(
                    inspector.conn.execute("SELECT COUNT(*) FROM layer1_run_lease").fetchone()[0], 1
                )
                with self.assertRaisesRegex(RuntimeError, "lease already held"):
                    inspector.acquire(ConfigurationOrchestrator(cfg).create_context())
            finally:
                inspector.close()
        finally:
            # Test cleanup only; production code must not silently steal this lease.
            conn = sqlite3.connect(self.db)
            try:
                conn.execute("DELETE FROM layer1_run_lease WHERE lease_name='agent'")
                conn.execute("UPDATE layer1_runs SET status='INTERRUPTED', finished_at=? WHERE run_id=?",
                             (iso(), context.run_id))
                conn.commit()
            finally:
                conn.close()

    def test_run_lease_does_not_release_when_finish_status_is_invalid(self):
        cfg = AgentConfig(database_path=self.db)
        lease = RunLease(self.db)
        try:
            context = ConfigurationOrchestrator(cfg).create_context()
            lease.acquire(context)
            with self.assertRaises(ValueError):
                lease.finish("PUBLISHED")
            self.assertEqual(
                lease.conn.execute("SELECT COUNT(*) FROM layer1_run_lease").fetchone()[0], 1
            )
            lease.finish("FAILED")
        finally:
            lease.close()

    def test_module2_rejects_non_finite_history_and_negative_volume(self):
        with self.assertRaises(ValueError):
            MarketObservation(self.identity.asset_id, "provider", "/market", iso(),
                              price=10, history=(10, float("nan"))).validate()
        with self.assertRaisesRegex(ValueError, "volume_24h"):
            MarketObservation(self.identity.asset_id, "provider", "/market", iso(),
                              price=10, volume_24h=-1).validate()

    def test_module2_binance_adapter_requires_real_provider_timestamp(self):
        engine = MarketDataIntelligenceEngine(
            lambda *_: {"symbol": "BTCUSDT", "lastPrice": "65000",
                        "priceChangePercent": "1.5", "quoteVolume": "1200000"}
        )
        with self.assertRaisesRegex(ValueError, "closeTime"):
            engine.fetch_binance_24h("BTCUSDT", self.identity.asset_id)

    def test_module3_requires_fresh_snapshot_and_exact_quote_pair(self):
        engine = BinanceListingEligibilityEngine(("USDT",), max_snapshot_age_seconds=30)
        symbols = [{"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
                    "status": "TRADING", "isSpotTradingAllowed": True}]
        stale = engine.evaluate(self.identity, {"symbols": symbols}, verified_at=iso(-120))
        self.assertEqual(stale.status, "UNVERIFIED")
        missing_time = engine.evaluate(self.identity, {"symbols": symbols})
        self.assertEqual(missing_time.status, "UNVERIFIED")
        wrong_quote = engine.evaluate(
            self.identity,
            {"symbols": [{"symbol": "BTCUSDC", "baseAsset": "BTC", "quoteAsset": "USDC",
                          "status": "TRADING", "isSpotTradingAllowed": True}]},
            verified_at=iso(),
        )
        self.assertEqual(wrong_quote.status, "INELIGIBLE")

    def test_module4_requires_https_and_deduplicates_latest_source_revision(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            AnnouncementEvidence(
                "article", "http://www.binance.com/announcement", "Binance",
                "listing", "BTC listing", iso(), iso(), (self.identity.asset_id,)
            ).validate()
        older = AnnouncementEvidence(
            "article-1", "https://www.binance.com/en/support/announcement/example",
            "Binance", "listing", "BTC listing", iso(-120), iso(-120),
            (self.identity.asset_id,), "hash-old", updated_at=iso(-120)
        )
        newer = AnnouncementEvidence(
            "article-1", "https://www.binance.com/en/support/announcement/example",
            "Binance", "listing", "BTC listing updated", iso(-120), iso(),
            (self.identity.asset_id,), "hash-new", updated_at=iso()
        )
        results, status = AnnouncementIntelligenceEngine(lambda: [older, newer]).fetch()
        self.assertEqual(status, "AVAILABLE")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].content_hash, "hash-new")

    def test_module5_syndicated_trend_is_not_counted_as_independent_source(self):
        signals = [
            TrendSignal("AI", "source-a", iso(), 1, (self.identity.asset_id,), "item-a", "same-story"),
            TrendSignal("AI", "source-b", iso(), 2, (self.identity.asset_id,), "item-b", "same-story"),
            TrendSignal("AI", "source-c", iso(), 3, (self.identity.asset_id,), "item-c", "independent-story"),
        ]
        engine = TrendingNarrativeIntelligenceEngine()
        normalized = engine.normalize(signals)
        self.assertEqual(len(normalized), 3)
        self.assertEqual(engine.independent_source_count(normalized), 2)

    def test_module6_candidate_identity_changes_for_material_trend_item_and_rejects_mismatch(self):
        eligibility = BinanceListingEligibilityEngine().evaluate(
            self.identity, {"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC",
             "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True}]},
            verified_at=iso()
        )
        market = MarketObservation(self.identity.asset_id, "binance_spot", "/ticker", iso(), price=65000)
        builder = CandidateDiscoveryFilteringEngine()
        one = TrendSignal("AI", "source", iso(), 1, (self.identity.asset_id,), "item-1", "hash-1")
        two = TrendSignal("AI", "source", iso(), 1, (self.identity.asset_id,), "item-2", "hash-2")
        first = builder.build(self.identity, eligibility, [market], [], [one])
        second = builder.build(self.identity, eligibility, [market], [], [two])
        self.assertNotEqual(first.candidate_id, second.candidate_id)
        mismatched = builder.build(
            self.identity,
            type(eligibility)("ELIGIBLE", "different-canonical-id", "BTC", ("BTCUSDT",)),
            [market], [], []
        )
        self.assertEqual(mismatched.state, "REJECTED")
        self.assertIn("canonical_asset_identity_mismatch", mismatched.rejection_reasons)

    def test_module7_rejects_boolean_scores_and_ranks_deterministically(self):
        eligibility = BinanceListingEligibilityEngine().evaluate(
            self.identity, {"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC",
             "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True}]},
            verified_at=iso()
        )
        market = MarketObservation(self.identity.asset_id, "binance_spot", "/ticker", iso(), price=65000)
        candidate = CandidateDiscoveryFilteringEngine().build(self.identity, eligibility, [market], [], [])
        engine = RelevanceScoringEngine()
        with self.assertRaises(ValueError):
            engine.score(candidate, {
                "event_materiality": True, "source_credibility": 90, "freshness": 100,
                "audience_relevance": 70, "novelty": 60,
            })
        first = engine.score(candidate, {
            "event_materiality": 80, "source_credibility": 90, "freshness": 100,
            "audience_relevance": 70, "novelty": 60,
        })
        deferred = engine.score(candidate, {
            "event_materiality": None, "source_credibility": 90, "freshness": 100,
            "audience_relevance": 70, "novelty": 60,
        })
        self.assertEqual(engine.rank([deferred, first]), [first, deferred])



    def test_module6_stale_provider_update_is_not_refreshed_by_recent_observation(self):
        eligibility = BinanceListingEligibilityEngine().evaluate(
            self.identity, {"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC",
             "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True}]},
            verified_at=iso()
        )
        market = MarketObservation(
            self.identity.asset_id, "coingecko_markets", "/markets", iso(),
            price=65000, published_at=iso(-3600)
        )
        result = CandidateDiscoveryFilteringEngine().build(self.identity, eligibility, [market], [], [])
        self.assertEqual(result.state, "REJECTED")
        self.assertIn("market_observation_stale", result.rejection_reasons)

    def test_module6_stale_announcement_is_not_refreshed_by_recent_retrieval(self):
        eligibility = BinanceListingEligibilityEngine().evaluate(
            self.identity, {"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC",
             "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True}]},
            verified_at=iso()
        )
        event = AnnouncementEvidence(
            "old-event", "https://www.binance.com/en/support/announcement/old",
            "Binance", "listing", "Old BTC listing notice", iso(-900000), iso(),
            (self.identity.asset_id,)
        )
        result = CandidateDiscoveryFilteringEngine().build(self.identity, eligibility, [], [event], [])
        self.assertEqual(result.state, "REJECTED")
        self.assertIn("announcement_evidence_stale", result.rejection_reasons)

    def test_module4_future_event_time_is_valid_but_not_published_time(self):
        event = AnnouncementEvidence(
            "scheduled-event", "https://www.binance.com/en/support/announcement/scheduled",
            "Binance", "upgrade", "Scheduled network upgrade", iso(), iso(),
            (self.identity.asset_id,), event_at=iso(3600)
        )
        event.validate()

    def test_layer1_store_retains_announcement_revisions(self):
        older = AnnouncementEvidence(
            "revisioned-article", "https://www.binance.com/en/support/announcement/update",
            "Binance", "listing", "Listing notice", iso(-120), iso(-120),
            (self.identity.asset_id,), "revision-1", updated_at=iso(-120)
        )
        newer = AnnouncementEvidence(
            "revisioned-article", "https://www.binance.com/en/support/announcement/update",
            "Binance", "listing", "Listing notice amended", iso(-120), iso(),
            (self.identity.asset_id,), "revision-2", updated_at=iso()
        )
        store = Layer1Store(self.db)
        try:
            store.save_announcement(older)
            store.save_announcement(newer)
            self.assertEqual(
                store.conn.execute(
                    "SELECT COUNT(*) FROM layer1_announcement_revisions WHERE source_id='revisioned-article'"
                ).fetchone()[0], 2
            )
            latest = store.conn.execute(
                "SELECT payload_json FROM layer1_announcement_evidence WHERE source_id='revisioned-article'"
            ).fetchone()[0]
            self.assertIn("revision-2", latest)
        finally:
            store.close()

    def test_hot_search_preserves_same_topic_from_independent_sources(self):
        engine = main.HotSearchEngine()
        announcement = {
            "topic": "BTC", "source": "official-announcement",
            "source_item_id": "article-1", "rank": 1,
        }
        trending = {
            "topic": "BTC", "source": "coingecko-trending",
            "source_item_id": "bitcoin", "rank": 2,
        }
        with patch.object(engine, "_from_announcements", return_value=[announcement]), \
             patch.object(engine, "_from_coingecko_trending", return_value=[trending]), \
             patch.object(engine, "_from_market_data", return_value=[]):
            merged = engine.get_trending(force_refresh=True)
        self.assertEqual(len(merged), 2)
        self.assertEqual({item["source"] for item in merged},
                         {"official-announcement", "coingecko-trending"})

    def test_final_spot_revalidation_refreshes_and_checks_exact_pair(self):
        old_cache = main._binance_listed_cache
        old_cache_time = main._binance_listed_cache_time
        old_pairs = main._binance_spot_pairs_cache
        old_snapshot = main._binance_spot_snapshot_observed_at
        payload = {
            "serverTime": int(time.time() * 1000),
            "symbols": [{
                "symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
                "status": "TRADING", "isSpotTradingAllowed": True,
            }],
        }
        try:
            main._binance_listed_cache = {"OLD"}
            main._binance_listed_cache_time = time.time()
            with patch.dict(os.environ, {"BINANCE_ALLOWED_QUOTE_ASSETS": "USDT"}), \
                 patch("main.urllib.request.urlopen", return_value=FakeHTTPResponse(payload)) as fetch:
                self.assertTrue(main._revalidate_binance_spot_asset("BTC", "coingecko:bitcoin"))
                fetch.assert_called_once()
            with patch("main.urllib.request.urlopen") as fetch:
                self.assertFalse(main._revalidate_binance_spot_asset("BTC", "ticker-only"))
                fetch.assert_not_called()
        finally:
            main._binance_listed_cache = old_cache
            main._binance_listed_cache_time = old_cache_time
            main._binance_spot_pairs_cache = old_pairs
            main._binance_spot_snapshot_observed_at = old_snapshot



    def test_runtime_ast_keeps_layer1_gate_and_publisher_in_one_execution_path(self):
        with open(main.__file__, encoding="utf-8") as source_file:
            source = source_file.read()
        module = ast.parse(source)
        functions = {
            node.name: node for node in module.body if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("_run_once_impl", functions)
        self.assertIn("_persist_layer1_market_intelligence", functions)
        runtime = functions["_run_once_impl"]
        call_names = set()
        for node in ast.walk(runtime):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    call_names.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    call_names.add(node.func.attr)
        self.assertIn("_persist_layer1_market_intelligence", call_names)
        self.assertGreaterEqual(
            sum(
                1 for node in ast.walk(runtime)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_revalidate_binance_spot_asset"
            ),
            2,
        )
        self.assertIn("publish", call_names)


    def test_layer1_store_persists_rejected_input_reason_codes_idempotently(self):
        store = Layer1Store(self.db)
        try:
            observed_at = iso()
            details = {"error_type": "ValueError"}
            store.save_rejection(
                "BTC", "market_observation_invalid", "coingecko_markets",
                observed_at, details
            )
            store.save_rejection(
                "BTC", "market_observation_invalid", "coingecko_markets",
                observed_at, details
            )
            rows = store.conn.execute(
                "SELECT symbol, reason_code, source, details_json "
                "FROM layer1_candidate_rejections"
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0:3], ("BTC", "market_observation_invalid", "coingecko_markets"))
            self.assertIn("ValueError", rows[0][3])
        finally:
            store.close()

    def test_runtime_layer1_persists_missing_identity_and_invalid_market_rejections(self):
        old_pairs = main._binance_spot_pairs_cache
        old_snapshot = main._binance_spot_snapshot_observed_at
        main._binance_spot_pairs_cache = {}
        main._binance_spot_snapshot_observed_at = iso()
        missing = main.Coin("NOID", "No ID", 1, 0, 0, 1, 1000000, [])
        invalid = main.Coin("BTC", "Bitcoin", -1, 0, 0, 1, 1000000, [])
        invalid.asset_id = "coingecko:bitcoin"
        invalid.observed_at = iso()
        invalid.market_data_source = "coingecko_markets"
        invalid.provider_published_at = iso()
        invalid.market_data_hash = "fixture"
        try:
            result = main._persist_layer1_market_intelligence([missing, invalid], self.db, [])
            self.assertEqual(result["rejected_inputs"], 2)
            conn = sqlite3.connect(self.db)
            try:
                rows = conn.execute(
                    "SELECT reason_code FROM layer1_candidate_rejections ORDER BY reason_code"
                ).fetchall()
                self.assertEqual([row[0] for row in rows], [
                    "canonical_asset_id_missing_or_unsupported", "market_observation_invalid"
                ])
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM layer1_market_observations").fetchone()[0], 0)
            finally:
                conn.close()
        finally:
            main._binance_spot_pairs_cache = old_pairs
            main._binance_spot_snapshot_observed_at = old_snapshot

if __name__ == "__main__":
    unittest.main()
