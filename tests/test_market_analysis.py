import json
import unittest
from datetime import datetime, timedelta, timezone

from layer1.foundation import (
    Layer1Store,
    MarketAnalysisEngine,
    MarketObservation,
)


def iso_at(value):
    return value.astimezone(timezone.utc).isoformat()


def market_observation(asset_id, provider, observed_at, price, currency="USD",
                       volume=200.0, market_cap=1000.0, change_24h=7.5,
                       history=(), data_hash=None):
    available = {
        "price": "AVAILABLE",
        "change_24h": "AVAILABLE" if change_24h is not None else "UNAVAILABLE",
        "volume_24h": "AVAILABLE" if volume is not None else "UNAVAILABLE",
        "market_cap": "AVAILABLE" if market_cap is not None else "UNAVAILABLE",
        "history": "AVAILABLE" if history else "UNAVAILABLE",
    }
    provenance = {name: provider for name, status in available.items() if status == "AVAILABLE"}
    freshness = {name: ("FRESH" if status == "AVAILABLE" else "UNAVAILABLE")
                 for name, status in available.items()}
    return MarketObservation(
        asset_id=asset_id,
        provider=provider,
        endpoint=f"https://{provider}.example/markets",
        observed_at=iso_at(observed_at),
        price=price,
        currency=currency,
        change_24h=change_24h,
        volume_24h=volume,
        market_cap=market_cap,
        history=tuple(history),
        source_timestamp=iso_at(observed_at),
        published_at=iso_at(observed_at) if provider == "coingecko_markets" else None,
        data_hash=data_hash or ("a" * 64),
        field_availability=available,
        field_provenance=provenance,
        freshness_by_field=freshness,
    )


class MarketAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
        self.engine = MarketAnalysisEngine()

    def test_calculates_returns_only_from_comparable_timestamped_observations(self):
        current = market_observation("coingecko:bitcoin", "coingecko_markets", self.now, 110)
        one_hour = market_observation("coingecko:bitcoin", "coingecko_markets", self.now - timedelta(hours=1), 100)
        one_day = market_observation("coingecko:bitcoin", "coingecko_markets", self.now - timedelta(hours=24), 100)
        result = self.engine.analyze(current, [one_day, one_hour, current])
        self.assertAlmostEqual(result.return_1h_pct, 10.0)
        self.assertAlmostEqual(result.return_24h_pct, 10.0)
        self.assertAlmostEqual(result.volume_to_market_cap_ratio_pct, 20.0)
        self.assertEqual(result.provider_reported_change_24h_pct, 7.5)
        self.assertTrue(any("provider-reported" in fact for fact in result.facts))
        self.assertEqual(result.hypotheses, ())

    def test_untimestamped_sparkline_is_not_used_as_historical_price_series(self):
        current = market_observation(
            "coingecko:bitcoin", "coingecko_markets", self.now, 110,
            history=[100.0 + index for index in range(168)],
        )
        result = self.engine.analyze(current, [current])
        self.assertIsNone(result.return_1h_pct)
        self.assertIsNone(result.return_24h_pct)
        self.assertIn("HISTORY_BASELINE_24H_UNAVAILABLE", result.quality_flags)
        self.assertTrue(any("timestamped" in item for item in result.unknowns))

    def test_benchmark_relative_change_uses_same_provider_currency_and_window(self):
        current = market_observation("coingecko:ethereum", "coingecko_markets", self.now, 110)
        asset_baseline = market_observation(
            "coingecko:ethereum", "coingecko_markets", self.now - timedelta(hours=24), 100,
        )
        benchmark_current = market_observation("coingecko:bitcoin", "coingecko_markets", self.now, 105)
        benchmark_baseline = market_observation(
            "coingecko:bitcoin", "coingecko_markets", self.now - timedelta(hours=24), 100,
        )
        result = self.engine.analyze(
            current, [asset_baseline, current], benchmark_current=benchmark_current,
            benchmark_history=[benchmark_baseline, benchmark_current],
        )
        self.assertAlmostEqual(result.benchmark_return_24h_pct, 5.0)
        self.assertAlmostEqual(result.benchmark_relative_24h_pct, 5.0)
        self.assertEqual(result.benchmark_asset_id, "coingecko:bitcoin")

    def test_provider_conflict_is_detected_only_for_same_asset_and_currency(self):
        current = market_observation("coingecko:bitcoin", "coingecko_markets", self.now, 100)
        peer = market_observation("coingecko:bitcoin", "binance_spot", self.now, 110)
        result = self.engine.analyze(current, [current], peer_observations=[peer])
        self.assertIn("PROVIDER_PRICE_CONFLICT", result.quality_flags)

        mismatched_currency = market_observation(
            "coingecko:bitcoin", "binance_spot", self.now, 110, currency="USDT",
        )
        result = self.engine.analyze(current, [current], peer_observations=[mismatched_currency])
        self.assertNotIn("PROVIDER_PRICE_CONFLICT", result.quality_flags)
        self.assertTrue(any("same-currency" in item for item in result.unknowns))

    def test_history_gap_and_robust_outlier_are_flagged_not_silently_removed(self):
        times = [self.now - timedelta(hours=24 - index * 2) for index in range(13)]
        prices = [100.0] * 5 + [125.0] + [100.0] * 7
        observations = [
            market_observation("coingecko:bitcoin", "coingecko_markets", timestamp, price)
            for timestamp, price in zip(times, prices)
        ]
        current = market_observation("coingecko:bitcoin", "coingecko_markets", self.now, 100)
        result = self.engine.analyze(current, observations + [current])
        self.assertIn("HISTORY_GAP_OVER_2H", result.quality_flags)
        self.assertIn("POTENTIAL_PRICE_OUTLIER_REVIEW", result.quality_flags)

    def test_stale_peer_quote_is_not_used_for_provider_conflict(self):
        current = market_observation("coingecko:bitcoin", "coingecko_markets", self.now, 100)
        stale_peer = market_observation(
            "coingecko:bitcoin", "binance_spot", self.now - timedelta(minutes=20), 120,
        )
        result = self.engine.analyze(current, [current], peer_observations=[stale_peer])
        self.assertNotIn("PROVIDER_PRICE_CONFLICT", result.quality_flags)
        self.assertTrue(any("same-currency" not in item for item in result.unknowns))

    def test_missing_history_and_benchmark_never_become_zero_returns(self):
        current = market_observation("coingecko:bitcoin", "coingecko_markets", self.now, 100)
        result = self.engine.analyze(current, [current])
        self.assertIsNone(result.return_1h_pct)
        self.assertIsNone(result.return_24h_pct)
        self.assertIsNone(result.benchmark_return_24h_pct)
        self.assertIsNone(result.benchmark_relative_24h_pct)
        self.assertEqual(result.hypotheses, ())
        self.assertEqual(result.status, "PARTIAL")

    def test_store_round_trips_timestamped_history_and_analysis(self):
        store = Layer1Store(":memory:")
        try:
            current = market_observation("coingecko:bitcoin", "coingecko_markets", self.now, 110)
            baseline = market_observation(
                "coingecko:bitcoin", "coingecko_markets", self.now - timedelta(hours=24), 100,
                data_hash="b" * 64,
            )
            store.save_market(baseline)
            store.save_market(current)
            history = store.get_market_history("coingecko:bitcoin", "coingecko_markets", "USD")
            self.assertEqual(len(history), 2)
            self.assertLess(history[0].observed_at, history[1].observed_at)
            self.assertEqual(len(store.get_market_history("coingecko:bitcoin", currency="USD")), 2)
            self.assertEqual(store.get_market_history("coingecko:bitcoin", currency="USDT"), [])
            result = self.engine.analyze(current, history)
            store.save_market_analysis(result)
            row = store.conn.execute(
                "SELECT status, payload_json FROM layer1_market_analyses WHERE analysis_id=?",
                (result.analysis_id,),
            ).fetchone()
            self.assertEqual(row[0], result.status)
            self.assertEqual(json.loads(row[1])["asset_id"], "coingecko:bitcoin")
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
