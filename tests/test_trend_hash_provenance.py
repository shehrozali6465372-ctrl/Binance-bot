from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import main
from layer1.evidence_verification import EvidenceVerificationEngine
from layer1.foundation import Layer1Store, MarketObservation, TrendSignal


class TrendHashProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc).isoformat()
        self.engine = main.HotSearchEngine(SimpleNamespace(http_timeout_seconds=2))

    def test_coingecko_trending_producer_labels_its_parsed_item_hash(self):
        item = {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "score": 0}
        with patch("main.http_get_json", return_value={"coins": [{"item": item}]}):
            records = self.engine._from_coingecko_trending()

        self.assertEqual(len(records), 1)
        expected = hashlib.sha256(
            json.dumps(item, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(records[0]["content_hash"], expected)
        self.assertEqual(records[0]["content_hash_kind"], "CANONICAL_PARSED_PROVIDER_JSON_SHA256")

    def test_market_derived_trends_inherit_explicit_market_hash_contract(self):
        coin = SimpleNamespace(
            symbol="ABC", change_24h=8.0, turnover_ratio_pct=3.0,
            asset_id="coingecko:abc", market_data_hash="a" * 64,
            observed_at=self.now,
        )
        with patch("main.MarketScanner") as scanner:
            scanner.return_value._universe.return_value = [coin]
            records = self.engine._from_market_data()

        self.assertEqual({item["source"] for item in records}, {"market_gainer", "market_turnover"})
        self.assertTrue(all(
            item["content_hash_kind"] == "CANONICAL_PARSED_PROVIDER_JSON_SHA256"
            for item in records
        ))

    def test_market_derived_trends_do_not_invent_hash_kind_when_hash_absent(self):
        coin = SimpleNamespace(
            symbol="ABC", change_24h=8.0, turnover_ratio_pct=3.0,
            asset_id="coingecko:abc", market_data_hash="", observed_at=self.now,
        )
        with patch("main.MarketScanner") as scanner:
            scanner.return_value._universe.return_value = [coin]
            records = self.engine._from_market_data()

        self.assertTrue(records)
        self.assertTrue(all(item["content_hash_kind"] == "UNSPECIFIED" for item in records))

    def test_layer1_store_round_trips_typed_hash_contracts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Layer1Store(directory + "/layer1.db")
            try:
                market = MarketObservation(
                    asset_id="coingecko:abc", provider="provider-a", endpoint="/market",
                    observed_at=self.now, price=10.0, data_hash="b" * 64,
                    data_hash_kind="CANONICAL_PARSED_PROVIDER_JSON_SHA256",
                )
                trend = TrendSignal(
                    topic="ABC_TREND", source="coingecko_trending", observed_at=self.now,
                    asset_ids=("coingecko:abc",), source_item_id="abc", content_hash="c" * 64,
                    content_hash_kind="CANONICAL_PARSED_PROVIDER_JSON_SHA256",
                )
                store.save_market(market)
                store.save_trend(trend)
                self.assertEqual(store.iter_market_observations()[0].data_hash_kind,
                                 "CANONICAL_PARSED_PROVIDER_JSON_SHA256")
                self.assertEqual(store.iter_trend_signals()[0].content_hash_kind,
                                 "CANONICAL_PARSED_PROVIDER_JSON_SHA256")
                from layer1.layer1_postgres import _market, _trend
                self.assertEqual(_market(market.__dict__).data_hash_kind,
                                 "CANONICAL_PARSED_PROVIDER_JSON_SHA256")
                self.assertEqual(_trend(trend.__dict__).content_hash_kind,
                                 "CANONICAL_PARSED_PROVIDER_JSON_SHA256")
            finally:
                store.close()

    def test_legacy_persisted_market_and_trend_payloads_default_to_unspecified(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Layer1Store(directory + "/legacy.db")
            try:
                market = MarketObservation(
                    asset_id="coingecko:abc", provider="provider-a", endpoint="/market",
                    observed_at=self.now, price=10.0, data_hash="1" * 64,
                    data_hash_kind="CANONICAL_PARSED_PROVIDER_JSON_SHA256",
                )
                trend = TrendSignal(
                    topic="ABC_TREND", source="provider-a", observed_at=self.now,
                    asset_ids=("coingecko:abc",), source_item_id="abc", content_hash="2" * 64,
                    content_hash_kind="CANONICAL_PARSED_PROVIDER_JSON_SHA256",
                )
                store.save_market(market)
                store.save_trend(trend)
                market_key, market_json = store.conn.execute(
                    "SELECT observation_key,payload_json FROM layer1_market_observations"
                ).fetchone()
                trend_key, trend_json = store.conn.execute(
                    "SELECT signal_key,payload_json FROM layer1_trend_signals"
                ).fetchone()
                market_payload = json.loads(market_json)
                trend_payload = json.loads(trend_json)
                market_payload.pop("data_hash_kind")
                trend_payload.pop("content_hash_kind")
                store.conn.execute(
                    "UPDATE layer1_market_observations SET payload_json=? WHERE observation_key=?",
                    (json.dumps(market_payload), market_key),
                )
                store.conn.execute(
                    "UPDATE layer1_trend_signals SET payload_json=? WHERE signal_key=?",
                    (json.dumps(trend_payload), trend_key),
                )
                self.assertEqual(store.iter_market_observations()[0].data_hash_kind, "UNSPECIFIED")
                self.assertEqual(store.iter_trend_signals()[0].content_hash_kind, "UNSPECIFIED")
            finally:
                store.close()

    def test_layer1_market_intelligence_persists_trend_hash_kind_from_provider_record(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = directory + "/market.db"
            trend_record = {
                "asset_id": "coingecko:abc", "source": "coingecko_trending",
                "source_item_id": "abc", "observed_at": self.now, "topic": "ABC",
                "content_hash": "3" * 64,
                "content_hash_kind": "CANONICAL_PARSED_PROVIDER_JSON_SHA256",
            }
            with patch.dict("os.environ", {
                "ANNOUNCEMENT_DATABASE_URL": "",
                "BINANCE_ALLOWED_QUOTE_ASSETS": "USDT",
            }, clear=False):
                summary = main._persist_layer1_market_intelligence(
                    [], database_path, trend_records=[trend_record],
                )
            self.assertEqual(summary["trends"], 1)
            store = Layer1Store(database_path)
            try:
                loaded = store.iter_trend_signals()
                self.assertEqual(len(loaded), 1)
                self.assertEqual(
                    loaded[0].content_hash_kind,
                    "CANONICAL_PARSED_PROVIDER_JSON_SHA256",
                )
            finally:
                store.close()

    def test_one_shot_main_passes_the_constructed_hot_search_engine_to_run_once(self):
        config = SimpleNamespace(validate=lambda: None)
        publisher_db = SimpleNamespace(
            get_posted_symbols=lambda **kwargs: set(), close=lambda: None,
        )
        publisher = SimpleNamespace(db=publisher_db)
        with (
            patch.object(main, "CONFIG", config),
            patch.object(main, "MarketScanner"),
            patch.object(main, "BinanceAnnouncementEngine"),
            patch.object(main, "HotSearchEngine") as hot_search_factory,
            patch.object(main, "ResearchEngine"),
            patch.object(main, "DeepSeekGenerator"),
            patch.object(main, "_create_runtime_postgres_store", return_value=None),
            patch.object(main, "PostPublisher", return_value=publisher),
            patch.object(main, "run_once") as run_once,
        ):
            main.main()

        self.assertEqual(run_once.call_count, 1)
        self.assertIs(
            run_once.call_args.kwargs.get("hot_search_engine"),
            hot_search_factory.return_value,
        )

    def test_evidence_adapter_preserves_hash_contract_from_producer_record(self):
        market = MarketObservation(
            asset_id="coingecko:abc", provider="provider-a", endpoint="/market",
            observed_at=self.now, price=10.0, data_hash="d" * 64,
            data_hash_kind="CANONICAL_SELECTED_PROJECTION_SHA256",
        )
        trend = TrendSignal(
            topic="ABC_TREND", source="provider-a", observed_at=self.now,
            asset_ids=("coingecko:abc",), source_item_id="abc", content_hash="e" * 64,
            content_hash_kind="LOCAL_ASSERTION_FINGERPRINT_SHA256",
        )
        market_record = EvidenceVerificationEngine.evidence_from_market_observation(market)[0]
        trend_record = EvidenceVerificationEngine.evidence_from_trend_signal(trend)[0]
        self.assertEqual(market_record.content_hash_kind, "CANONICAL_SELECTED_PROJECTION_SHA256")
        self.assertEqual(trend_record.content_hash_kind, "LOCAL_ASSERTION_FINGERPRINT_SHA256")


if __name__ == "__main__":
    unittest.main()
