import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import main
from layer1.foundation import AnnouncementEvidence, Layer1Store


class AnnouncementLayer1IntegrationTests(unittest.TestCase):
    def test_imported_cms_evidence_reaches_candidate_evaluation_without_publishing(self):
        now = datetime.now(timezone.utc).isoformat()
        asset_id = "coingecko:bitcoin"
        evidence = AnnouncementEvidence(
            source_id="a" * 64,
            source_url="https://www.binance.com/en/support/announcement",
            publisher="Binance",
            event_type="listing",
            title="Binance announcement references Bitcoin (BTC)",
            published_at=now,
            observed_at=now,
            asset_ids=(asset_id,),
            content_hash="b" * 64,
        )
        evidence.validate()
        coin = SimpleNamespace(
            asset_id=asset_id,
            observed_at=now,
            market_data_source="coingecko_markets",
            symbol="BTC",
            name="Bitcoin",
            price=65000.0,
            change_24h=1.5,
            volume_24h=1000000.0,
            market_cap=1000000000.0,
            history=(),
            provider_published_at=now,
            market_data_hash="c" * 64,
        )
        pairs = [{
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "status": "TRADING",
            "isSpotTradingAllowed": True,
        }]

        def fake_import(database_url, candidates, store):
            self.assertEqual(database_url, "postgresql://redacted.example/db")
            self.assertEqual(candidates, [coin])
            store.save_announcement(evidence)
            return {
                "rows_read": 1,
                "evidence_saved": 1,
                "unmatched_rows": 0,
                "invalid_rows": 0,
                "by_asset_id": {asset_id: [evidence]},
            }

        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "layer1.sqlite")
            with (
                patch.dict(os.environ, {"ANNOUNCEMENT_DATABASE_URL": "postgresql://redacted.example/db"}),
                patch.object(main, "_binance_spot_pairs_cache", {"BTC": pairs}),
                patch.object(main, "_binance_spot_snapshot_observed_at", now),
                patch("layer1.announcement_importer.import_recent_binance_announcements", side_effect=fake_import),
                patch.object(main, "PostPublisher", side_effect=AssertionError("publisher must not be called")),
            ):
                summary = main._persist_layer1_market_intelligence([coin], database_path, [])

            self.assertEqual(summary["announcements"], 1)
            self.assertEqual(summary["provider_health"]["binance_announcements"], "AVAILABLE")
            self.assertEqual(summary["ready_asset_ids"], [asset_id])

            store = Layer1Store(database_path)
            try:
                row = store.conn.execute(
                    "SELECT evidence_refs_json FROM layer1_candidates WHERE asset_id = ?",
                    (asset_id,),
                ).fetchone()
                self.assertIsNotNone(row)
                evidence_refs = json.loads(row[0])
                self.assertEqual(evidence_refs["events"], [evidence.source_id])
                saved = store.conn.execute(
                    "SELECT COUNT(*) FROM layer1_announcement_evidence WHERE source_id = ?",
                    (evidence.source_id,),
                ).fetchone()[0]
                self.assertEqual(saved, 1)
            finally:
                store.close()

    def test_failed_optional_cms_import_degrades_without_blocking_market_pipeline(self):
        now = datetime.now(timezone.utc).isoformat()
        coin = SimpleNamespace(
            asset_id="coingecko:bitcoin",
            observed_at=now,
            market_data_source="coingecko_markets",
            symbol="BTC",
            name="Bitcoin",
            price=65000.0,
            change_24h=1.5,
            volume_24h=1000000.0,
            market_cap=1000000000.0,
            history=(),
            provider_published_at=now,
            market_data_hash="c" * 64,
        )
        pairs = [{
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "status": "TRADING",
            "isSpotTradingAllowed": True,
        }]

        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "layer1-failed-import.sqlite")
            with (
                patch.dict(os.environ, {"ANNOUNCEMENT_DATABASE_URL": "postgresql://redacted.example/db"}),
                patch.object(main, "_binance_spot_pairs_cache", {"BTC": pairs}),
                patch.object(main, "_binance_spot_snapshot_observed_at", now),
                patch(
                    "layer1.announcement_importer.import_recent_binance_announcements",
                    side_effect=RuntimeError("connection failed: postgresql://secret@host/db"),
                ),
                patch.object(main, "PostPublisher", side_effect=AssertionError("publisher must not be called")),
            ):
                summary = main._persist_layer1_market_intelligence([coin], database_path, [])

            self.assertEqual(summary["provider_health"]["binance_announcements"], "DEGRADED_IMPORT_FAILED")
            self.assertEqual(summary["announcement_import_error_type"], "RuntimeError")
            self.assertEqual(summary["observations"], 1)
            self.assertEqual(summary["candidates"], 1)


if __name__ == "__main__":
    unittest.main()
