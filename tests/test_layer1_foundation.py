import ast
import json
import inspect
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
    AssetIdentity, AssetIdentityProof, BinanceListingEligibilityEngine, CandidateDiscoveryFilteringEngine,
    CoinGeckoBinanceIdentityResolver,
    ConfigurationOrchestrator, Layer1Store, MarketDataIntelligenceEngine, MarketObservation,
    RelevanceScoringEngine, RunLease, TrendSignal, ProviderResponse, ProviderRequestError,
    TrendingNarrativeIntelligenceEngine,
)


def iso(delta_seconds=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)).isoformat()


def proof_for(identity, verified_at=None, source_timestamp=None):
    return AssetIdentityProof(
        "VERIFIED", identity.asset_id, identity.base_asset, identity.quote_asset,
        "binance", f"{identity.base_asset}/{identity.quote_asset}",
        "test-only exact CoinGecko ticker proof", "coingecko_coin_tickers",
        verified_at or iso(), source_timestamp or iso(), iso(), "a" * 64, {},
    )


def exchange_info(symbols, server_time=None):
    return {
        "serverTime": server_time if server_time is not None else int(datetime.now(timezone.utc).timestamp() * 1000),
        "symbols": symbols,
    }


def spot_pair(symbol="BTCUSDT", base="BTC", quote="USDT", status="TRADING",
              spot_allowed=True, permission_sets=None):
    return {
        "symbol": symbol, "baseAsset": base, "quoteAsset": quote,
        "status": status, "isSpotTradingAllowed": spot_allowed,
        "permissionSets": permission_sets if permission_sets is not None else [["SPOT", "MARGIN"]],
    }


def eligibility_for(identity):
    pair = spot_pair(symbol=identity.base_asset + identity.quote_asset,
                     base=identity.base_asset, quote=identity.quote_asset)
    return BinanceListingEligibilityEngine((identity.quote_asset,)).evaluate(
        identity, exchange_info([pair]), verified_at=iso(), identity_proof=proof_for(identity)
    )


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
        with self.assertRaisesRegex(ValueError, "DEEPSEEK_API_KEY"):
            replace(main.CONFIG, dry_run=False, deepseek_api_key="", square_api_key="configured").validate()
        with self.assertRaisesRegex(ValueError, "SQUARE_API_KEY"):
            replace(main.CONFIG, dry_run=False, deepseek_api_key="configured", square_api_key="").validate()
        replace(main.CONFIG, dry_run=True, deepseek_api_key="", square_api_key="").validate()

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
        result = engine.fetch_binance_24h(self.identity, "BTCUSDT")
        self.assertEqual(result.price, 65000)
        self.assertEqual(result.asset_id, self.identity.asset_id)
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ValueError):
            MarketDataIntelligenceEngine(lambda *_: {"symbol": "ETHUSDT"}).fetch_binance_24h(
                self.identity, "BTCUSDT"
            )

    def test_module2_market_observation_rejects_conflicting_field_availability(self):
        observation = MarketObservation(
            self.identity.asset_id, "provider", "/market", iso(), price=65000,
            field_availability={"price": "UNAVAILABLE"},
        )
        with self.assertRaisesRegex(ValueError, "availability conflicts"):
            observation.validate()

    def test_module2_freshness_thresholds_must_be_positive_integers(self):
        with self.assertRaisesRegex(ValueError, "positive integer seconds"):
            MarketDataIntelligenceEngine(lambda *_: {}, freshness_limits_seconds={"provider": {"price": 0}})

    def test_module2_cache_ttl_configuration_rejects_negative_values(self):
        with self.assertRaisesRegex(ValueError, "MARKET_DATA_CACHE_TTL_SECONDS"):
            replace(main.CONFIG, market_data_cache_ttl_seconds=-1).validate()
        replace(main.CONFIG, market_data_cache_ttl_seconds=0).validate()

    def test_module2_coingecko_universe_rejects_missing_required_metrics_instead_of_zero_filling(self):
        payload = [{
            "id": "bitcoin", "symbol": "btc", "name": "Bitcoin",
            "current_price": 65000, "price_change_percentage_24h": 1.5,
            "total_volume": None, "market_cap": 900000000,
            "last_updated": iso(), "sparkline_in_7d": {"price": [64000, 65000]},
        }]
        scanner = main.MarketScanner(AgentConfigShim())
        with patch("main._get_binance_listed", return_value={"BTC"}), \
             patch("main.market_data_http_get", return_value=ProviderResponse(payload)):
            self.assertEqual(scanner._coingecko_universe(), [])

    def test_module2_scanner_cache_uses_configured_ttl_without_refreshing_observation_time(self):
        scanner = main.MarketScanner(replace(main.CONFIG, live_market_data=True,
                                             market_data_cache_ttl_seconds=60))
        coin = main.Coin("BTC", "Bitcoin", 65000, 1, 100000, 1, 1000000, [])
        coin.observed_at = iso()
        original_cache = (main.MarketScanner._universe_cache, main.MarketScanner._cache_timestamp,
                          main.MarketScanner._cache_config_key)
        try:
            main.MarketScanner._universe_cache = None
            main.MarketScanner._cache_timestamp = 0
            main.MarketScanner._cache_config_key = None
            with patch.object(scanner, "_coingecko_universe", return_value=[coin]) as fetch, \
                 patch("main.time.time", side_effect=[1000, 1020, 1070]):
                first = scanner._universe()
                second = scanner._universe()
                third = scanner._universe()
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(first[0].observed_at, second[0].observed_at)
            self.assertEqual(second[0].observed_at, third[0].observed_at)
        finally:
            (main.MarketScanner._universe_cache, main.MarketScanner._cache_timestamp,
             main.MarketScanner._cache_config_key) = original_cache

    def test_module2_provider_http_error_is_normalized_without_exposing_body(self):
        error = main.urllib.error.HTTPError(
            "https://data-api.binance.vision/api/v3/ticker/24hr", 429,
            "rate limited", {"Retry-After": "9"}, None,
        )
        engine = MarketDataIntelligenceEngine(lambda *_: (_ for _ in ()).throw(error))
        with self.assertRaises(ProviderRequestError) as raised:
            engine.fetch_binance_24h(self.identity, "BTCUSDT")
        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.retry_after_seconds, 9)

    def test_module2_binance_adapter_requires_exact_canonical_asset_pair(self):
        engine = MarketDataIntelligenceEngine(lambda *_: {})
        with self.assertRaisesRegex(ValueError, "canonical base/quote"):
            engine.fetch_binance_24h(self.identity, "WBTCUSDT")

    def test_module2_binance_observation_separates_source_and_retrieval_time(self):
        now = iso()
        source_time = iso(-10)
        source_ms = int(datetime.fromisoformat(source_time).timestamp() * 1000)
        engine = MarketDataIntelligenceEngine(
            lambda *_: ProviderResponse({
                "symbol": "BTCUSDT", "lastPrice": "65000", "priceChangePercent": "1.5",
                "quoteVolume": "1200000", "closeTime": source_ms,
            }, headers={"X-MBX-USED-WEIGHT-1M": "12"}),
            clock=lambda: now,
        )
        observation = engine.fetch_binance_24h(self.identity, "BTCUSDT")
        self.assertEqual(observation.observed_at, now)
        self.assertIsNotNone(observation.source_timestamp)
        self.assertNotEqual(observation.observed_at, observation.source_timestamp)
        self.assertEqual(observation.field_availability["price"], "AVAILABLE")
        self.assertEqual(observation.field_provenance["price"], "binance_spot")
        self.assertEqual(observation.provider_metadata["used_weight_1m"], 12)
        self.assertRegex(observation.data_hash, r"^[0-9a-f]{64}$")

    def test_module2_coingecko_normalizer_uses_exact_coin_id_and_field_provenance(self):
        engine = MarketDataIntelligenceEngine(lambda *_: {})
        item = {
            "id": "bitcoin", "symbol": "btc", "current_price": 65000,
            "price_change_percentage_24h": 1.5, "total_volume": 1200000,
            "market_cap": 900000000, "last_updated": iso(-5),
            "sparkline_in_7d": {"price": [64000, 64500, 65000]},
        }
        observation = engine.normalize_coingecko_market(self.identity, item, observed_at=iso())
        self.assertEqual(observation.asset_id, self.identity.asset_id)
        self.assertEqual(observation.provider, "coingecko_markets")
        self.assertEqual(observation.field_availability["price"], "AVAILABLE")
        self.assertEqual(observation.field_provenance["price"], "coingecko_markets")
        self.assertEqual(len(observation.history), 3)
        with self.assertRaisesRegex(ValueError, "coin ID"):
            engine.normalize_coingecko_market(self.identity, {**item, "id": "wrapped-bitcoin"})
        with self.assertRaisesRegex(ValueError, "symbol"):
            engine.normalize_coingecko_market(self.identity, {**item, "symbol": "wbtc"})

    def test_module2_provider_429_exposes_retry_after_without_retrying(self):
        calls = []
        def fetch(*_):
            calls.append(1)
            return ProviderResponse(None, status_code=429, headers={"Retry-After": "12"})
        engine = MarketDataIntelligenceEngine(fetch)
        with self.assertRaises(ProviderRequestError) as raised:
            engine.fetch_binance_24h(self.identity, "BTCUSDT")
        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.retry_after_seconds, 12)
        self.assertEqual(len(calls), 1)

    def test_module2_cache_preserves_original_observation_timestamp(self):
        clock = [iso()]
        source_ms = int(datetime.fromisoformat(clock[0]).timestamp() * 1000)
        calls = []
        def fetch(*_):
            calls.append(1)
            return {"symbol": "BTCUSDT", "lastPrice": "65000", "priceChangePercent": "1.5",
                    "quoteVolume": "1200000", "closeTime": source_ms}
        engine = MarketDataIntelligenceEngine(fetch, cache_ttl_seconds=60, clock=lambda: clock[0])
        first = engine.fetch_binance_24h(self.identity, "BTCUSDT")
        original_observed_at = first.observed_at
        clock[0] = iso(10)
        second = engine.fetch_binance_24h(self.identity, "BTCUSDT")
        self.assertEqual(len(calls), 1)
        self.assertEqual(second.observed_at, original_observed_at)
        self.assertTrue(second.cache_hit)

    def test_module2_provider_disagreement_is_retained_not_averaged(self):
        first = MarketObservation(self.identity.asset_id, "binance_spot", "/ticker", iso(), price=100, currency="USDT")
        second = MarketObservation(self.identity.asset_id, "coingecko_markets", "/markets", iso(), price=110, currency="USDT", published_at=iso())
        discrepancies = MarketDataIntelligenceEngine.compare_observations([first, second], threshold_fraction=0.05)
        self.assertEqual(len(discrepancies), 1)
        self.assertEqual(discrepancies[0].asset_id, self.identity.asset_id)
        self.assertEqual(discrepancies[0].providers, ("binance_spot", "coingecko_markets"))
        self.assertEqual((first.price, second.price), (100, 110))
        normalized = MarketDataIntelligenceEngine(lambda *_: {}).normalize_coingecko_market(
            self.identity,
            {"id": "bitcoin", "symbol": "btc", "current_price": 101,
             "last_updated": iso(), "total_volume": 1, "market_cap": 1},
            currency="USDT",
        )
        self.assertEqual(normalized.currency, "USDT")

    def test_module2_unknown_provider_timestamp_is_not_current_candidate_evidence(self):
        market = MarketObservation(
            self.identity.asset_id, "provider", "/market", iso(), price=65000,
            freshness_by_field={"price": "UNKNOWN"},
        )
        eligibility = eligibility_for(self.identity)
        candidate = CandidateDiscoveryFilteringEngine().build(self.identity, eligibility, [market], [], [])
        self.assertEqual(candidate.state, "REJECTED")
        self.assertIn("no_source_backed_discovery_signal", candidate.rejection_reasons)

    def test_module2_stale_price_is_not_candidate_evidence_even_if_retrieved_recently(self):
        engine = MarketDataIntelligenceEngine(lambda *_: {})
        item = {
            "id": "bitcoin", "symbol": "btc", "current_price": 65000,
            "price_change_percentage_24h": 1.5, "total_volume": 1200000,
            "market_cap": 900000000, "last_updated": iso(-3600),
            "sparkline_in_7d": {"price": [64000, 64500, 65000]},
        }
        market = engine.normalize_coingecko_market(self.identity, item, observed_at=iso())
        eligibility = eligibility_for(self.identity)
        candidate = CandidateDiscoveryFilteringEngine().build(self.identity, eligibility, [market], [], [])
        self.assertEqual(market.freshness_by_field["price"], "STALE")
        self.assertEqual(candidate.state, "REJECTED")
        self.assertIn("market_observation_stale", candidate.rejection_reasons)

    def test_market_data_http_adapter_surfaces_429_retry_after_without_retrying(self):
        error = main.urllib.error.HTTPError(
            "https://api.coingecko.com/api/v3/coins/markets", 429, "rate limited",
            {"Retry-After": "17"}, None,
        )
        with patch("main.urllib.request.urlopen", side_effect=error) as urlopen:
            response = main.market_data_http_get("https://api.coingecko.com/api/v3/coins/markets", 5)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "17")
        urlopen.assert_called_once()

    def test_module2_coingecko_sparkline_freshness_is_unknown_without_its_own_timestamp(self):
        engine = MarketDataIntelligenceEngine(lambda *_: {})
        item = {
            "id": "bitcoin", "symbol": "btc", "current_price": 65000,
            "price_change_percentage_24h": 1.5, "total_volume": 1200000,
            "market_cap": 900000000, "last_updated": iso(-7 * 3600),
            "sparkline_in_7d": {"price": [64000, 64500, 65000]},
        }
        observation = engine.normalize_coingecko_market(self.identity, item, observed_at=iso())
        self.assertEqual(observation.freshness_by_field["price"], "STALE")
        self.assertEqual(observation.freshness_by_field["history"], "UNKNOWN")
        self.assertEqual(observation.provider_metadata["history_refresh_interval_seconds"], 21600)
        self.assertFalse(observation.provider_metadata["history_source_timestamp_available"])

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
        payload = exchange_info([
            spot_pair(),
            spot_pair(symbol="BTCUSDC", quote="USDC"),
            spot_pair(symbol="WBTCUSDT", base="WBTC"),
        ])
        eligible = engine.evaluate(self.identity, payload, verified_at=iso(), identity_proof=proof_for(self.identity))
        self.assertEqual(eligible.status, "ELIGIBLE")
        self.assertEqual(eligible.eligible_pairs, ("BTCUSDT",))
        unavailable = engine.evaluate(self.identity, {}, identity_proof=proof_for(self.identity))
        self.assertEqual(unavailable.status, "UNVERIFIED")
        inactive = engine.evaluate(self.identity, exchange_info([
            spot_pair(status="BREAK")
        ]), verified_at=iso(), identity_proof=proof_for(self.identity))
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
            (self.identity.asset_id,), "a" * 64
        )
        evidence.validate()

    def test_runtime_imports_official_announcements_before_objective_filtering(self):
        source = inspect.getsource(main._run_once_impl)
        self.assertNotIn("get_trending_announcements()", source)
        self.assertLess(
            source.index("_persist_layer1_market_intelligence("),
            source.index("_passes_objective_filters("),
        )

    def test_module4_cms_evidence_labels_fingerprints_and_retains_raw_reference(self):
        evidence = AnnouncementEvidence(
            "a" * 64, "https://www.binance.com/en/support/announcement", "Binance",
            "listing", "Binance lists Bitcoin (BTC)", iso(-30), iso(),
            (self.identity.asset_id,), "b" * 64,
        )
        evidence.validate()
        self.assertEqual(evidence.source_id_kind, "payload_fingerprint")
        self.assertEqual(evidence.source_url_kind, "official_landing_page")
        self.assertEqual(evidence.revision_correlation_status, "UNRESOLVED_NO_STABLE_PROVIDER_ID")
        self.assertEqual(
            evidence.raw_evidence_ref,
            "postgres:binance_announcement_events:content_hash:" + ("b" * 64),
        )
        self.assertIn("not a stable Binance article ID", evidence.revision_match_reason)

    def test_module4_fingerprint_revisions_choose_latest_observation_and_warn(self):
        source_id = "a" * 64
        first = AnnouncementEvidence(
            source_id, "https://www.binance.com/en/support/announcement", "Binance",
            "listing", "Binance lists Bitcoin (BTC)", iso(-60), iso(-30),
            (self.identity.asset_id,), "b" * 64,
        )
        latest = AnnouncementEvidence(
            source_id, "https://www.binance.com/en/support/announcement", "Binance",
            "listing", "Binance lists Bitcoin (BTC)", iso(-60), iso(),
            (self.identity.asset_id,), "c" * 64,
        )
        engine = AnnouncementIntelligenceEngine(lambda: [first, latest])
        selected, status = engine.fetch()
        self.assertEqual(status, "AVAILABLE")
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].content_hash, "c" * 64)
        self.assertEqual(engine.revision_correlation_status, "UNRESOLVED_NO_STABLE_PROVIDER_ID")
        self.assertGreaterEqual(len(engine.revision_warnings), 1)

    def test_module4_fingerprint_events_with_different_ids_are_not_merged(self):
        one = AnnouncementEvidence(
            "a" * 64, "https://www.binance.com/en/support/announcement", "Binance",
            "listing", "Binance lists Bitcoin (BTC)", iso(-60), iso(),
            (self.identity.asset_id,), "b" * 64,
        )
        two = AnnouncementEvidence(
            "c" * 64, "https://www.binance.com/en/support/announcement", "Binance",
            "listing", "Binance adds BTC Spot trading", iso(-55), iso(),
            (self.identity.asset_id,), "d" * 64,
        )
        selected, _ = AnnouncementIntelligenceEngine(lambda: [one, two]).fetch()
        self.assertEqual(len(selected), 2)
        self.assertEqual({item.source_id for item in selected}, {"a" * 64, "c" * 64})

    def test_module4_rejects_publisher_spoofing_on_an_official_binance_host(self):
        evidence = AnnouncementEvidence(
            "article-1", "https://www.binance.com/en/support/announcement/article-1",
            "Impersonator", "listing", "Binance lists Bitcoin (BTC)", iso(-30), iso(),
            (self.identity.asset_id,), "a" * 64,
        )
        with self.assertRaisesRegex(ValueError, "publisher does not match"):
            evidence.validate()

    def test_module4_announcement_evidence_cannot_bypass_module3_eligibility(self):
        event = AnnouncementEvidence(
            "article-1", "https://www.binance.com/en/support/announcement/article-1", "Binance",
            "listing", "Binance lists Bitcoin (BTC)", iso(-30), iso(),
            (self.identity.asset_id,), "a" * 64,
        )
        market = MarketObservation(self.identity.asset_id, "coingecko_markets", "/markets", iso(), price=65000)
        ineligible = eligibility_for(self.identity)
        ineligible = replace(ineligible, status="UNVERIFIED", reason="identity proof missing")
        candidate = CandidateDiscoveryFilteringEngine().build(
            self.identity, ineligible, [market], [event], []
        )
        self.assertEqual(candidate.state, "REJECTED")
        self.assertIn("binance_spot_eligibility_unverified", candidate.rejection_reasons)

    def test_module4_fingerprint_without_raw_evidence_reference_is_rejected(self):
        evidence = AnnouncementEvidence(
            "a" * 64, "https://www.binance.com/en/support/announcement/article-1", "Binance",
            "listing", "Binance lists Bitcoin (BTC)", iso(-30), iso(),
            (self.identity.asset_id,), "b" * 64,
            source_id_kind="payload_fingerprint", source_url_kind="official_landing_page",
            revision_correlation_status="UNRESOLVED_NO_STABLE_PROVIDER_ID",
            revision_match_reason="Provider ID is not stable; manual review required.",
        )
        with self.assertRaisesRegex(ValueError, "Postgres content-hash reference"):
            evidence.validate()

    def test_module5_rejects_bad_timestamps_and_deduplicates_same_source_item(self):
        engine = TrendingNarrativeIntelligenceEngine()
        one = TrendSignal("BTC", "coingecko", iso(), 1, (self.identity.asset_id,), "cg-1")
        two = TrendSignal("BTC", "coingecko", iso(), 2, (self.identity.asset_id,), "cg-1")
        self.assertEqual(len(engine.normalize([one, two])), 1)
        with self.assertRaises(ValueError):
            engine.normalize([TrendSignal("BTC", "source", "not-a-time")])

    def test_module5_clusters_normalized_topics_per_asset_and_counts_independent_content(self):
        signals = [
            TrendSignal("BTC_SURGE", "provider_a", iso(), 1, (self.identity.asset_id,), "article-a", "a" * 64),
            TrendSignal("btc surge", "provider_b", iso(), 2, (self.identity.asset_id,), "article-b", "a" * 64),
            TrendSignal("BTC_SURGE", "provider_c", iso(), 3, (self.identity.asset_id,), "article-c", "b" * 64),
            TrendSignal("BTC_SURGE", "provider_a", iso(-30), 4, (self.identity.asset_id,), "article-a", "a" * 64),
        ]
        engine = TrendingNarrativeIntelligenceEngine()
        normalized = engine.normalize(signals)
        self.assertEqual(len(normalized), 3)
        clusters = engine.cluster(normalized)
        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertEqual(cluster.topic_key, "btc surge")
        self.assertEqual(cluster.asset_ids, (self.identity.asset_id,))
        self.assertEqual(cluster.source_count, 3)
        self.assertEqual(cluster.independent_source_count, 2)
        self.assertEqual(cluster.signal_count, 3)
        self.assertEqual(cluster.confidence_limit, "ATTENTION_ONLY_NOT_EVENT_PROOF")

    def test_module5_does_not_merge_same_topic_across_different_assets(self):
        signals = [
            TrendSignal("BTC", "provider_a", iso(), 1, ("coingecko:bitcoin",), "item-1", "a" * 64),
            TrendSignal("btc", "provider_a", iso(), 1, ("coingecko:wrapped-bitcoin",), "item-1", "a" * 64),
        ]
        engine = TrendingNarrativeIntelligenceEngine()
        normalized = engine.normalize(signals)
        clusters = engine.cluster(normalized)
        self.assertEqual(len(normalized), 2)
        self.assertEqual(len(clusters), 2)
        self.assertEqual({cluster.asset_ids[0] for cluster in clusters},
                         {"coingecko:bitcoin", "coingecko:wrapped-bitcoin"})

    def test_module5_rejects_trend_signals_without_canonical_asset_or_provenance(self):
        with self.assertRaisesRegex(ValueError, "canonical CoinGecko IDs"):
            TrendSignal("BTC", "provider", iso(), 1, ("BTC",), "item-1", "a" * 64).validate()
        with self.assertRaisesRegex(ValueError, "provider item ID or content hash"):
            TrendSignal("BTC", "provider", iso(), 1, (self.identity.asset_id,), "", "").validate()
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            TrendSignal("BTC", "provider", iso(), 1, (self.identity.asset_id,), "item-1", "not-a-hash").validate()

    def test_module5_rejects_topic_with_no_normalizable_tokens(self):
        signal = TrendSignal("!!!", "provider", iso(), 1, (self.identity.asset_id,), "item-1", "a" * 64)
        with self.assertRaisesRegex(ValueError, "alphanumeric tokens"):
            TrendingNarrativeIntelligenceEngine().cluster([signal])

    def test_module5_missing_content_hash_does_not_claim_independent_corroboration(self):
        signals = [
            TrendSignal("BTC", "provider_a", iso(), 1, (self.identity.asset_id,), "item-a", ""),
            TrendSignal("btc", "provider_b", iso(), 2, (self.identity.asset_id,), "item-b", ""),
        ]
        cluster = TrendingNarrativeIntelligenceEngine().cluster(signals)[0]
        self.assertEqual(cluster.source_count, 2)
        self.assertEqual(cluster.independent_source_count, 1)

    def test_module5_cluster_persistence_and_candidate_reference(self):
        signals = [
            TrendSignal("BTC", "provider_a", iso(), 1, (self.identity.asset_id,), "item-a", "a" * 64),
            TrendSignal("BTC", "provider_b", iso(), 2, (self.identity.asset_id,), "item-b", "b" * 64),
        ]
        engine = TrendingNarrativeIntelligenceEngine()
        clusters = engine.cluster(signals)
        candidate = CandidateDiscoveryFilteringEngine().build(
            self.identity, eligibility_for(self.identity), [], [], signals
        )
        self.assertEqual(candidate.state, "READY_FOR_RESEARCH")
        self.assertEqual(candidate.trend_cluster_ids, (clusters[0].cluster_id,))
        store = Layer1Store(self.db)
        try:
            store.save_trend_cluster(clusters[0])
            store.save_candidate(candidate)
            row = store.conn.execute(
                "SELECT source_count, independent_source_count, signal_count, confidence_limit "
                "FROM layer1_trend_clusters WHERE cluster_id=?", (clusters[0].cluster_id,)
            ).fetchone()
            self.assertEqual(row, (2, 2, 2, "ATTENTION_ONLY_NOT_EVENT_PROOF"))
            payload = json.loads(store.conn.execute(
                "SELECT evidence_refs_json FROM layer1_candidates WHERE candidate_id=?",
                (candidate.candidate_id,),
            ).fetchone()[0])
            self.assertEqual(payload["trend_clusters"], [clusters[0].cluster_id])
        finally:
            store.close()

    def test_module6_same_asset_event_from_multiple_sources_is_one_candidate(self):
        eligibility = eligibility_for(self.identity)
        market = MarketObservation(self.identity.asset_id, "binance_spot", "/ticker", iso(), price=65000)
        first = AnnouncementEvidence(
            "source-article-1", "https://www.binance.com/en/support/announcement/article-1",
            "Binance", "listing", "Binance lists BTC/USDT Spot trading", iso(-3600), iso(),
            (self.identity.asset_id,), "a" * 64,
        )
        second = AnnouncementEvidence(
            "source-article-2", "https://www.binance.com/en/support/announcement/article-2",
            "Binance", "listing", "Binance lists BTC/USDT Spot trading", iso(-3590), iso(),
            (self.identity.asset_id,), "b" * 64,
        )
        builder = CandidateDiscoveryFilteringEngine()
        one_source = builder.build(self.identity, eligibility, [market], [first], [])
        both_sources = builder.build(self.identity, eligibility, [market], [first, second], [])
        self.assertEqual(one_source.candidate_id, both_sources.candidate_id)
        self.assertEqual(len(both_sources.event_cluster_ids), 1)
        self.assertEqual(set(both_sources.event_ids), {"source-article-1", "source-article-2"})
        store = Layer1Store(self.db)
        try:
            store.save_candidate(one_source)
            store.save_candidate(both_sources)
            evidence = json.loads(store.conn.execute(
                "SELECT evidence_refs_json FROM layer1_candidates WHERE candidate_id=?",
                (both_sources.candidate_id,),
            ).fetchone()[0])
            self.assertEqual(evidence["event_clusters"], list(both_sources.event_cluster_ids))
            self.assertEqual(set(evidence["events"]), {"source-article-1", "source-article-2"})
        finally:
            store.close()

    def test_module6_candidate_identity_stays_stable_when_eligibility_state_changes(self):
        eligible = eligibility_for(self.identity)
        unverified = replace(eligible, status="UNVERIFIED", reason="fresh proof unavailable")
        market = MarketObservation(self.identity.asset_id, "binance_spot", "/ticker", iso(), price=65000)
        event = AnnouncementEvidence(
            "listing-1", "https://www.binance.com/en/support/announcement/listing-1",
            "Binance", "listing", "Binance lists BTC/USDT Spot trading", iso(-3600), iso(),
            (self.identity.asset_id,), "a" * 64,
        )
        builder = CandidateDiscoveryFilteringEngine()
        accepted = builder.build(self.identity, eligible, [market], [event], [])
        rejected = builder.build(self.identity, unverified, [market], [event], [])
        self.assertEqual(accepted.candidate_id, rejected.candidate_id)
        self.assertEqual(accepted.state, "READY_FOR_RESEARCH")
        self.assertEqual(rejected.state, "REJECTED")
        store = Layer1Store(self.db)
        try:
            store.save_candidate(accepted)
            store.save_candidate(rejected)
            row = store.conn.execute(
                "SELECT state, evidence_refs_json FROM layer1_candidates WHERE candidate_id=?",
                (accepted.candidate_id,),
            ).fetchone()
            self.assertEqual(row[0], "REJECTED")
            evidence = json.loads(row[1])
            self.assertEqual(evidence["eligibility"]["status"], "UNVERIFIED")
        finally:
            store.close()

    def test_module6_new_material_event_creates_distinct_candidate_identity(self):
        eligibility = eligibility_for(self.identity)
        market = MarketObservation(self.identity.asset_id, "binance_spot", "/ticker", iso(), price=65000)
        listing = AnnouncementEvidence(
            "listing-1", "https://www.binance.com/en/support/announcement/listing-1",
            "Binance", "listing", "Binance lists BTC/USDT Spot trading", iso(-3600), iso(),
            (self.identity.asset_id,), "a" * 64,
        )
        delisting = AnnouncementEvidence(
            "delisting-1", "https://www.binance.com/en/support/announcement/delisting-1",
            "Binance", "delisting", "Binance delists BTC/USDT Spot trading", iso(-3590), iso(),
            (self.identity.asset_id,), "b" * 64,
        )
        builder = CandidateDiscoveryFilteringEngine()
        first = builder.build(self.identity, eligibility, [market], [listing], [])
        second = builder.build(self.identity, eligibility, [market], [delisting], [])
        self.assertNotEqual(first.candidate_id, second.candidate_id)
        self.assertNotEqual(first.event_cluster_ids, second.event_cluster_ids)

    def test_module6_trend_only_candidate_is_stable_when_same_content_gets_another_source(self):
        eligibility = eligibility_for(self.identity)
        market = MarketObservation(self.identity.asset_id, "binance_spot", "/ticker", iso(), price=65000)
        first = TrendSignal("BTC_SURGE", "provider_a", iso(), 1, (self.identity.asset_id,), "item-a", "a" * 64)
        syndicated = TrendSignal("btc surge", "provider_b", iso(), 2, (self.identity.asset_id,), "item-b", "a" * 64)
        builder = CandidateDiscoveryFilteringEngine()
        one = builder.build(self.identity, eligibility, [market], [], [first])
        two_sources = builder.build(self.identity, eligibility, [market], [], [first, syndicated])
        self.assertEqual(one.candidate_id, two_sources.candidate_id)
        self.assertEqual(one.trend_cluster_ids, two_sources.trend_cluster_ids)

    def test_module6_candidate_identity_is_stable_when_same_event_gets_more_trend_corroboration(self):
        eligibility = eligibility_for(self.identity)
        market = MarketObservation(self.identity.asset_id, "binance_spot", "/ticker", iso(), price=65000)
        event = AnnouncementEvidence(
            "listing-1", "https://www.binance.com/en/support/announcement/listing-1",
            "Binance", "listing", "Binance lists BTC/USDT Spot trading", iso(-3600), iso(),
            (self.identity.asset_id,), "a" * 64,
        )
        trend = TrendSignal("BTC", "provider_a", iso(), 1, (self.identity.asset_id,), "item-a", "b" * 64)
        builder = CandidateDiscoveryFilteringEngine()
        one = builder.build(self.identity, eligibility, [market], [event], [])
        corroborated = builder.build(self.identity, eligibility, [market], [event], [trend])
        self.assertEqual(one.candidate_id, corroborated.candidate_id)
        self.assertEqual(len(corroborated.trend_cluster_ids), 1)

    def test_module6_candidate_requires_eligibility_and_source_backed_signal(self):
        eligible = eligibility_for(self.identity)
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
        with patch("main._get_binance_listed", return_value={"BTC"}), patch("main.market_data_http_get", side_effect=RuntimeError("provider unavailable")):
            self.assertEqual(scanner._coingecko_universe(), [])

    def test_legacy_listing_check_fails_closed_without_static_allowlist(self):
        main._binance_listed_cache = None
        main._binance_listed_cache_time = 0
        with patch("main.market_data_http_get", side_effect=OSError("offline")):
            self.assertEqual(main._get_binance_listed(), set())

    def test_legacy_listing_snapshot_requires_fresh_server_time_and_quote_asset(self):
        payload = {"serverTime": int(time.time() * 1000), "symbols": [
            spot_pair(),
            spot_pair(symbol="BTCUSDC", quote="USDC"),
        ]}
        main._binance_listed_cache = None
        with patch("main.market_data_http_get", return_value=ProviderResponse(payload)):
            self.assertEqual(main._get_binance_listed(), {"BTC"})
        stale = {**payload, "serverTime": int((time.time() - 3600) * 1000)}
        main._binance_listed_cache = None
        with patch("main.market_data_http_get", return_value=ProviderResponse(stale)):
            self.assertEqual(main._get_binance_listed(), set())
        incomplete = {**payload, "symbols": [{k: v for k, v in payload["symbols"][0].items()
                                              if k != "permissionSets"}]}
        main._binance_listed_cache = None
        with patch("main.market_data_http_get", return_value=ProviderResponse(incomplete)):
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
        coin.market_data_provider_metadata = {"x-ratelimit-remaining-minute": "29"}
        coin.market_data_payload = {
            "id": "bitcoin", "symbol": "btc", "current_price": 65000,
            "price_change_percentage_24h": 1.2, "total_volume": 1_000_000,
            "market_cap": 1_200_000_000_000, "last_updated": coin.provider_published_at,
            "sparkline_in_7d": {"price": [64000, 65000]},
        }
        old_pairs = main._binance_spot_pairs_cache
        old_snapshot = main._binance_spot_snapshot_observed_at
        old_exchange_snapshot = main._binance_spot_exchange_info_snapshot
        current_pair = spot_pair()
        main._binance_spot_snapshot_observed_at = iso()
        main._binance_spot_pairs_cache = {"BTC": [current_pair]}
        main._binance_spot_exchange_info_snapshot = exchange_info([current_pair])
        try:
            trends = [
                {
                    "topic": "BTC", "source": "coingecko_trending",
                    "source_item_id": "bitcoin", "asset_id": "coingecko:bitcoin",
                    "observed_at": iso(), "rank": 1, "content_hash": "a" * 64,
                },
                {
                    "topic": "btc", "source": "news_feed_a",
                    "source_item_id": "article-1", "asset_id": "coingecko:bitcoin",
                    "observed_at": iso(), "rank": 2, "content_hash": "a" * 64,
                },
                {
                    "topic": "BTC", "source": "news_feed_b",
                    "source_item_id": "article-2", "asset_id": "coingecko:bitcoin",
                    "observed_at": iso(), "rank": 3, "content_hash": "b" * 64,
                },
                {
                    "topic": "btc", "source": "coingecko_trending",
                    "source_item_id": "bitcoin", "asset_id": "coingecko:bitcoin",
                    "observed_at": iso(-30), "rank": 4, "content_hash": "a" * 64,
                },
            ]
            with patch("main._fetch_coingecko_binance_identity_proof", return_value=proof_for(self.identity)):
                result = main._persist_layer1_market_intelligence([coin], self.db, trends)
            self.assertEqual(result["observations"], 1)
            self.assertEqual(result["market_analyses"], 1)
            self.assertEqual(result["market_analysis_partial"], 1)
            self.assertEqual(result["market_analysis_quality_flags"]["coingecko:bitcoin"],
                             ["HISTORY_BASELINE_24H_UNAVAILABLE"])
            self.assertEqual(result["trends"], 3)
            self.assertEqual(result["trend_clusters"], 1)
            self.assertEqual(result["trend_source_count"], 3)
            self.assertEqual(result["trend_independent_source_cluster_total"], 2)
            self.assertEqual(result["trend_independent_source_counts"]["coingecko:bitcoin"]["btc"], 2)
            self.assertEqual(result["candidates"], 1)
            self.assertEqual(result["ready_asset_ids"], ["coingecko:bitcoin"])
            self.assertEqual(result["provider_health"]["binance_spot_metadata"], "AVAILABLE")
            self.assertEqual(result["provider_health"]["coingecko_market_data"], "AVAILABLE")
            self.assertEqual(result["provider_health"]["coingecko_trending"], "AVAILABLE")
            self.assertEqual(
                result["provider_health"]["binance_announcements"],
                "UNAVAILABLE_MISSING_ANNOUNCEMENT_DATABASE_URL",
            )
            conn = sqlite3.connect(self.db)
            try:
                row = conn.execute("SELECT state, evidence_refs_json FROM layer1_candidates").fetchone()
                self.assertEqual(row[0], "READY_FOR_RESEARCH")
                self.assertIn("BTCUSDT", row[1])
                self.assertIn("coingecko:bitcoin", row[1])
                market_payload = json.loads(conn.execute(
                    "SELECT payload_json FROM layer1_market_observations"
                ).fetchone()[0])
                self.assertEqual(market_payload["field_availability"]["price"], "AVAILABLE")
                self.assertEqual(market_payload["field_provenance"]["price"], "coingecko_markets")
                self.assertEqual(market_payload["provider_metadata"]["x-ratelimit-remaining-minute"], "29")
                self.assertEqual(market_payload["source_timestamp"], coin.provider_published_at)
                self.assertEqual(market_payload["observed_at"], coin.observed_at)
                analysis_row = conn.execute(
                    "SELECT status, payload_json FROM layer1_market_analyses"
                ).fetchone()
                self.assertEqual(analysis_row[0], "PARTIAL")
                analysis_payload = json.loads(analysis_row[1])
                self.assertIsNone(analysis_payload["return_24h_pct"])
                self.assertIn("HISTORY_BASELINE_24H_UNAVAILABLE", analysis_payload["quality_flags"])
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM layer1_trend_signals").fetchone()[0], 3)
                cluster_row = conn.execute(
                    "SELECT source_count, independent_source_count, signal_count, confidence_limit "
                    "FROM layer1_trend_clusters"
                ).fetchone()
                self.assertEqual(cluster_row, (3, 2, 3, "ATTENTION_ONLY_NOT_EVENT_PROOF"))
                evidence_refs = json.loads(row[1])
                self.assertEqual(len(evidence_refs["trend_clusters"]), 1)
                score = conn.execute("SELECT score, reason FROM layer1_candidate_scores").fetchone()
                self.assertEqual(score[0], 0.0)
                self.assertIn("deferred", score[1])
            finally:
                conn.close()
            with patch("main._fetch_coingecko_binance_identity_proof", side_effect=AssertionError("cache miss")) as fetch:
                cached_result = main._persist_layer1_market_intelligence([coin], self.db, trends)
            fetch.assert_not_called()
            self.assertEqual(cached_result["identity_proof_requests"], 0)
            self.assertEqual(cached_result["identity_proof_cache_hits"], 1)
            self.assertEqual(cached_result["identity_proof_verified"], 1)
        finally:
            main._binance_spot_pairs_cache = old_pairs
            main._binance_spot_snapshot_observed_at = old_snapshot
            main._binance_spot_exchange_info_snapshot = old_exchange_snapshot

    def test_module3_does_not_spend_coin_ticker_requests_without_fresh_binance_snapshot(self):
        coin = main.Coin("BTC", "Bitcoin", 65000, 1.2, 1_000_000, 1.5, 1_200_000_000_000, [64000, 65000])
        coin.asset_id = "coingecko:bitcoin"
        coin.observed_at = iso()
        coin.provider_published_at = iso()
        coin.market_data_payload = {
            "id": "bitcoin", "symbol": "btc", "current_price": 65000,
            "price_change_percentage_24h": 1.2, "total_volume": 1_000_000,
            "market_cap": 1_200_000_000_000, "last_updated": coin.provider_published_at,
            "sparkline_in_7d": {"price": [64000, 65000]},
        }
        old_snapshot = main._binance_spot_snapshot_observed_at
        old_exchange_snapshot = main._binance_spot_exchange_info_snapshot
        main._binance_spot_snapshot_observed_at = None
        main._binance_spot_exchange_info_snapshot = None
        try:
            with patch("main._fetch_coingecko_binance_identity_proof", side_effect=AssertionError("must not call")) as fetch:
                result = main._persist_layer1_market_intelligence([coin], self.db, [])
            fetch.assert_not_called()
            self.assertEqual(result["identity_proof_requests"], 0)
            self.assertEqual(result["identity_proof_unverified"], 1)
            self.assertEqual(result["ready"], 0)
        finally:
            main._binance_spot_snapshot_observed_at = old_snapshot
            main._binance_spot_exchange_info_snapshot = old_exchange_snapshot

    def test_module3_identity_proof_request_budget_is_bounded_and_fail_closed(self):
        coins = []
        pairs = []
        for index in range(11):
            base = f"TST{index}"
            coin = main.Coin(base, f"Test {index}", 10, 1, 2_000_000, 1, 2_000_000, [9, 10])
            coin.asset_id = f"coingecko:test-coin-{index}"
            coin.observed_at = iso()
            coin.provider_published_at = iso()
            coin.market_data_payload = {
                "id": f"test-coin-{index}", "symbol": base.lower(), "current_price": 10,
                "price_change_percentage_24h": 1, "total_volume": 2_000_000,
                "market_cap": 2_000_000, "last_updated": coin.provider_published_at,
                "sparkline_in_7d": {"price": [9, 10]},
            }
            coins.append(coin)
            pairs.append(spot_pair(symbol=base + "USDT", base=base))
        old_pairs = main._binance_spot_pairs_cache
        old_snapshot = main._binance_spot_snapshot_observed_at
        old_exchange_snapshot = main._binance_spot_exchange_info_snapshot
        main._binance_spot_pairs_cache = {coin.symbol: [pair] for coin, pair in zip(coins, pairs)}
        main._binance_spot_snapshot_observed_at = iso()
        main._binance_spot_exchange_info_snapshot = exchange_info(pairs)
        try:
            def fake_proof(identity, timeout):
                return proof_for(identity)
            with patch("main._fetch_coingecko_binance_identity_proof", side_effect=fake_proof) as fetch:
                result = main._persist_layer1_market_intelligence(coins, self.db, [])
            self.assertEqual(fetch.call_count, 10)
            self.assertEqual(result["identity_proof_requests"], 10)
            self.assertEqual(result["identity_proof_verified"], 10)
            self.assertEqual(result["identity_proof_unverified"], 1)
            self.assertEqual(result["ready"], 10)
            self.assertEqual(result["rejected"], 1)
        finally:
            main._binance_spot_pairs_cache = old_pairs
            main._binance_spot_snapshot_observed_at = old_snapshot
            main._binance_spot_exchange_info_snapshot = old_exchange_snapshot

    def test_layer1_store_persists_identity_proof_cache_with_expiry(self):
        store = Layer1Store(self.db)
        try:
            proof = proof_for(self.identity)
            store.save_identity_proof(proof, ttl_seconds=600)
            cached = store.get_identity_proof(self.identity)
            self.assertIsNotNone(cached)
            self.assertEqual(cached.status, "VERIFIED")
            self.assertEqual(cached.data_hash, proof.data_hash)
            self.assertIsNone(store.get_identity_proof(self.identity, now=iso(3600)))
            self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM layer1_identity_proofs").fetchone()[0], 0)
        finally:
            store.close()

    def test_layer1_store_rejects_invalid_identity_proof_cache_ttl(self):
        store = Layer1Store(self.db)
        try:
            with self.assertRaisesRegex(ValueError, "positive integer"):
                store.save_identity_proof(proof_for(self.identity), ttl_seconds=0)
        finally:
            store.close()

    def test_layer1_store_persists_source_provenance_candidate_reasons_and_score_version(self):
        eligibility = eligibility_for(self.identity)
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
        eligibility = eligibility_for(self.identity)
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
            engine.fetch_binance_24h(self.identity, "BTCUSDT")

    def test_module3_requires_fresh_canonical_identity_proof(self):
        engine = BinanceListingEligibilityEngine(("USDT",))
        decision = engine.evaluate(self.identity, exchange_info([spot_pair()]), verified_at=iso())
        self.assertEqual(decision.status, "UNVERIFIED")
        self.assertIn("identity proof", decision.reason)

    def test_module3_permission_sets_and_exact_symbol_are_mandatory(self):
        engine = BinanceListingEligibilityEngine(("USDT",))
        proof = proof_for(self.identity)
        missing_permissions = engine.evaluate(
            self.identity, exchange_info([{k: v for k, v in spot_pair().items() if k != "permissionSets"}]),
            verified_at=iso(), identity_proof=proof,
        )
        self.assertEqual(missing_permissions.status, "UNVERIFIED")
        margin_only = engine.evaluate(
            self.identity, exchange_info([spot_pair(permission_sets=[["MARGIN"]])]),
            verified_at=iso(), identity_proof=proof,
        )
        self.assertEqual(margin_only.status, "INELIGIBLE")
        wrong_symbol = engine.evaluate(
            self.identity, exchange_info([spot_pair(symbol="WBTCUSDT")]),
            verified_at=iso(), identity_proof=proof,
        )
        self.assertEqual(wrong_symbol.status, "UNVERIFIED")
        eligible = engine.evaluate(
            self.identity, exchange_info([spot_pair()]), verified_at=iso(), identity_proof=proof
        )
        self.assertEqual(eligible.status, "ELIGIBLE")
        self.assertEqual(eligible.eligible_pairs, ("BTCUSDT",))
        mismatched_proof = AssetIdentityProof(
            "VERIFIED", "coingecko:wrapped-bitcoin", "BTC", "USDT", "binance", "BTC/USDT",
            "test mismatched identity", "coingecko_coin_tickers", iso(), iso(), iso(), "b" * 64, {},
        )
        rejected_identity = engine.evaluate(
            self.identity, exchange_info([spot_pair()]), verified_at=iso(), identity_proof=mismatched_proof
        )
        self.assertEqual(rejected_identity.status, "UNVERIFIED")

    def test_module3_coin_ticker_identity_proof_requires_fresh_last_fetch_timestamp(self):
        resolver = CoinGeckoBinanceIdentityResolver()
        ticker = {
            "coin_id": "bitcoin", "base": "BTC", "target": "USDT",
            "market": {"identifier": "binance"}, "is_stale": False,
            "is_anomaly": False, "last_fetch_at": iso(-3600), "timestamp": iso(-3600),
        }
        stale = resolver.resolve("coingecko:bitcoin", "BTC", "USDT", {"tickers": [ticker]}, verified_at=iso())
        self.assertEqual(stale.status, "UNVERIFIED")
        self.assertIn("stale", stale.reason.lower())
        fresh_ticker = {**ticker, "last_fetch_at": iso(), "timestamp": iso()}
        fresh = resolver.resolve("coingecko:bitcoin", "BTC", "USDT", {"tickers": [fresh_ticker]}, verified_at=iso())
        self.assertEqual(fresh.status, "VERIFIED")
        self.assertEqual(fresh.source, "coingecko_coin_tickers")

    def test_module3_exchange_info_requires_server_time_and_complete_permission_schema(self):
        engine = BinanceListingEligibilityEngine(("USDT",))
        proof = proof_for(self.identity)
        missing_server_time = engine.evaluate(
            self.identity, {"symbols": [spot_pair()]}, verified_at=iso(), identity_proof=proof
        )
        self.assertEqual(missing_server_time.status, "UNVERIFIED")
        missing_permission_sets = engine.evaluate(
            self.identity,
            exchange_info([{k: v for k, v in spot_pair().items() if k != "permissionSets"}]),
            verified_at=iso(), identity_proof=proof,
        )
        self.assertEqual(missing_permission_sets.status, "UNVERIFIED")
        mismatched_symbol = engine.evaluate(
            self.identity, exchange_info([spot_pair(symbol="WBTCUSDT")]),
            verified_at=iso(), identity_proof=proof,
        )
        self.assertEqual(mismatched_symbol.status, "UNVERIFIED")

    def test_module3_requires_fresh_snapshot_and_exact_quote_pair(self):
        engine = BinanceListingEligibilityEngine(("USDT",), max_snapshot_age_seconds=30)
        proof = proof_for(self.identity)
        symbols = [spot_pair()]
        stale = engine.evaluate(self.identity, exchange_info(symbols, int(datetime.now(timezone.utc).timestamp() * 1000) - 120000), verified_at=iso(-120), identity_proof=proof)
        self.assertEqual(stale.status, "UNVERIFIED")
        missing_time = engine.evaluate(self.identity, {"symbols": symbols}, identity_proof=proof)
        self.assertEqual(missing_time.status, "UNVERIFIED")
        wrong_quote = engine.evaluate(
            self.identity,
            exchange_info([spot_pair(symbol="BTCUSDC", quote="USDC")]),
            verified_at=iso(), identity_proof=proof,
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
            (self.identity.asset_id,), "a" * 64, updated_at=iso(-120)
        )
        newer = AnnouncementEvidence(
            "article-1", "https://www.binance.com/en/support/announcement/example",
            "Binance", "listing", "BTC listing updated", iso(-120), iso(),
            (self.identity.asset_id,), "b" * 64, updated_at=iso()
        )
        results, status = AnnouncementIntelligenceEngine(lambda: [older, newer]).fetch()
        self.assertEqual(status, "AVAILABLE")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].content_hash, "b" * 64)

    def test_module5_syndicated_trend_is_not_counted_as_independent_source(self):
        signals = [
            TrendSignal("AI", "source-a", iso(), 1, (self.identity.asset_id,), "item-a", ("a" * 64)),
            TrendSignal("AI", "source-b", iso(), 2, (self.identity.asset_id,), "item-b", ("a" * 64)),
            TrendSignal("AI", "source-c", iso(), 3, (self.identity.asset_id,), "item-c", ("b" * 64)),
        ]
        engine = TrendingNarrativeIntelligenceEngine()
        normalized = engine.normalize(signals)
        self.assertEqual(len(normalized), 3)
        self.assertEqual(engine.independent_source_count(normalized), 2)

    def test_module6_candidate_identity_changes_for_material_trend_item_and_rejects_mismatch(self):
        eligibility = eligibility_for(self.identity)
        market = MarketObservation(self.identity.asset_id, "binance_spot", "/ticker", iso(), price=65000)
        builder = CandidateDiscoveryFilteringEngine()
        one = TrendSignal("AI", "source", iso(), 1, (self.identity.asset_id,), "item-1", ("c" * 64))
        two = TrendSignal("AI", "source", iso(), 1, (self.identity.asset_id,), "item-2", ("d" * 64))
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
        eligibility = eligibility_for(self.identity)
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
        eligibility = eligibility_for(self.identity)
        market = MarketObservation(
            self.identity.asset_id, "coingecko_markets", "/markets", iso(),
            price=65000, published_at=iso(-3600)
        )
        result = CandidateDiscoveryFilteringEngine().build(self.identity, eligibility, [market], [], [])
        self.assertEqual(result.state, "REJECTED")
        self.assertIn("market_observation_stale", result.rejection_reasons)

    def test_module6_stale_announcement_is_not_refreshed_by_recent_retrieval(self):
        eligibility = eligibility_for(self.identity)
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
            (self.identity.asset_id,), "c" * 64, updated_at=iso(-120)
        )
        newer = AnnouncementEvidence(
            "revisioned-article", "https://www.binance.com/en/support/announcement/update",
            "Binance", "listing", "Listing notice amended", iso(-120), iso(),
            (self.identity.asset_id,), "d" * 64, updated_at=iso()
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
            self.assertIn("d" * 64, latest)
        finally:
            store.close()

    def test_hot_search_deduplication_keeps_same_topic_for_distinct_canonical_assets(self):
        engine = main.HotSearchEngine(None)
        topics = [
            {"topic": "BTC", "source": "provider", "source_item_id": "item-1", "asset_id": "coingecko:bitcoin", "rank": 1},
            {"topic": "BTC", "source": "provider", "source_item_id": "item-1", "asset_id": "coingecko:wrapped-bitcoin", "rank": 1},
        ]
        with patch.object(engine, "_from_announcements", return_value=[]), \
             patch.object(engine, "_from_coingecko_trending", return_value=topics), \
             patch.object(engine, "_from_market_data", return_value=[]):
            results = engine.get_trending(force_refresh=True)
        self.assertEqual(len(results), 2)
        self.assertEqual({item["asset_id"] for item in results},
                         {"coingecko:bitcoin", "coingecko:wrapped-bitcoin"})

    def test_hot_search_does_not_call_legacy_announcement_bapi_provider(self):
        engine = main.HotSearchEngine(None)
        with patch.object(engine, "_from_announcements", side_effect=AssertionError("legacy BAPI must not be called")) as legacy, \
             patch.object(engine, "_from_coingecko_trending", return_value=[]), \
             patch.object(engine, "_from_market_data", return_value=[]):
            engine.get_trending(force_refresh=True)
        legacy.assert_not_called()

    def test_hot_search_preserves_same_topic_from_independent_sources(self):
        engine = main.HotSearchEngine(None)
        coingecko = [{
            "topic": "BTC", "source": "coingecko_trending", "source_item_id": "bitcoin",
            "asset_id": "coingecko:bitcoin", "rank": 1,
        }]
        market = [{
            "topic": "BTC", "source": "market_gainer", "source_item_id": "coingecko:bitcoin",
            "asset_id": "coingecko:bitcoin", "rank": 2,
        }]
        with patch.object(engine, "_from_coingecko_trending", return_value=coingecko), \
             patch.object(engine, "_from_market_data", return_value=market):
            merged = engine.get_trending(force_refresh=True)
        self.assertEqual(len(merged), 2)
        self.assertEqual({item["source"] for item in merged}, {"coingecko_trending", "market_gainer"})

    def test_final_spot_revalidation_refreshes_and_checks_exact_pair(self):
        old_cache = main._binance_listed_cache
        old_cache_time = main._binance_listed_cache_time
        old_pairs = main._binance_spot_pairs_cache
        old_snapshot = main._binance_spot_snapshot_observed_at
        old_exchange_snapshot = main._binance_spot_exchange_info_snapshot
        payload = exchange_info([spot_pair()])
        ticker_payload = {"tickers": [{
            "coin_id": "bitcoin", "base": "BTC", "target": "USDT",
            "market": {"identifier": "binance"}, "is_stale": False,
            "is_anomaly": False, "last_fetch_at": iso(), "timestamp": iso(),
        }]}
        try:
            main._binance_listed_cache = {"OLD"}
            main._binance_listed_cache_time = time.time()
            with patch.dict(os.environ, {"BINANCE_ALLOWED_QUOTE_ASSETS": "USDT"}), \
                 patch("main.market_data_http_get", side_effect=[ProviderResponse(payload), ProviderResponse(ticker_payload)]) as fetch:
                self.assertTrue(main._revalidate_binance_spot_asset("BTC", "coingecko:bitcoin"))
                self.assertEqual(fetch.call_count, 2)
            stale_ticker_payload = {"tickers": [{**ticker_payload["tickers"][0], "last_fetch_at": iso(-3600)}]}
            with patch.dict(os.environ, {"BINANCE_ALLOWED_QUOTE_ASSETS": "USDT"}), \
                 patch("main.market_data_http_get", side_effect=[ProviderResponse(payload), ProviderResponse(stale_ticker_payload)]):
                self.assertFalse(main._revalidate_binance_spot_asset("BTC", "coingecko:bitcoin"))
            with patch("main.market_data_http_get") as fetch:
                self.assertFalse(main._revalidate_binance_spot_asset("BTC", "ticker-only"))
                fetch.assert_not_called()
        finally:
            main._binance_listed_cache = old_cache
            main._binance_listed_cache_time = old_cache_time
            main._binance_spot_pairs_cache = old_pairs
            main._binance_spot_snapshot_observed_at = old_snapshot
            main._binance_spot_exchange_info_snapshot = old_exchange_snapshot



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


class CanonicalAssetIdentityRegressionTests(unittest.TestCase):
    def test_coin_id_requires_exact_binance_market_ticker_proof(self):
        from layer1.foundation import CoinGeckoBinanceIdentityResolver
        resolver = CoinGeckoBinanceIdentityResolver()
        payload = {"tickers": [{
            "coin_id": "bitcoin", "base": "BTC", "target": "USDT",
            "market": {"identifier": "binance"},
            "is_stale": False, "is_anomaly": False,
            "last_fetch_at": iso(), "timestamp": iso(),
        }]}
        proof = resolver.resolve("coingecko:bitcoin", "BTC", "USDT", payload, verified_at=iso())
        self.assertEqual(proof.status, "VERIFIED")
        self.assertEqual(proof.exchange_id, "binance")
        self.assertEqual(proof.market_pair, "BTC/USDT")

    def test_symbol_only_or_wrong_coin_id_cannot_prove_asset_identity(self):
        from layer1.foundation import CoinGeckoBinanceIdentityResolver
        resolver = CoinGeckoBinanceIdentityResolver()
        payload = {"tickers": [{
            "coin_id": "wrapped-bitcoin", "base": "BTC", "target": "USDT",
            "market": {"identifier": "binance"},
            "is_stale": False, "is_anomaly": False,
            "last_fetch_at": iso(), "timestamp": iso(),
        }]}
        proof = resolver.resolve("coingecko:bitcoin", "BTC", "USDT", payload, verified_at=iso())
        self.assertEqual(proof.status, "UNVERIFIED")

    def test_stale_anomalous_or_non_binance_ticker_is_not_identity_proof(self):
        from layer1.foundation import CoinGeckoBinanceIdentityResolver
        resolver = CoinGeckoBinanceIdentityResolver()
        for ticker in (
            {"coin_id": "bitcoin", "base": "BTC", "target": "USDT", "market": {"identifier": "binance"}, "is_stale": True, "is_anomaly": False, "last_fetch_at": iso(), "timestamp": iso()},
            {"coin_id": "bitcoin", "base": "BTC", "target": "USDT", "market": {"identifier": "binance"}, "is_stale": False, "is_anomaly": True, "last_fetch_at": iso(), "timestamp": iso()},
            {"coin_id": "bitcoin", "base": "BTC", "target": "USDT", "market": {"identifier": "other-exchange"}, "is_stale": False, "is_anomaly": False, "last_fetch_at": iso(), "timestamp": iso()},
        ):
            proof = resolver.resolve("coingecko:bitcoin", "BTC", "USDT", {"tickers": [ticker]})
            self.assertEqual(proof.status, "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
