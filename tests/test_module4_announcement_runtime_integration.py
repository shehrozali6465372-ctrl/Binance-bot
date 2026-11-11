import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import main
from layer1.foundation import AnnouncementEvidence, AssetIdentityProof, Layer1Store


def make_coin(now):
    coin = main.Coin("BTC", "Bitcoin", 65000.0, 1.5, 1_000_000.0, 1.2, 1_000_000_000.0, [64000.0, 65000.0])
    coin.asset_id = "coingecko:bitcoin"
    coin.observed_at = now
    coin.provider_published_at = now
    coin.market_data_source = "coingecko_markets"
    coin.market_data_payload = {
        "id": "bitcoin", "symbol": "btc", "current_price": 65000.0,
        "price_change_percentage_24h": 1.5, "total_volume": 1_000_000.0,
        "market_cap": 1_000_000_000.0, "last_updated": now,
        "sparkline_in_7d": {"price": [64000.0, 65000.0]},
    }
    return coin


def proof_for(now):
    return AssetIdentityProof(
        "VERIFIED", "coingecko:bitcoin", "BTC", "USDT", "binance", "BTC/USDT",
        "test-only exact canonical ticker proof", "coingecko_coin_tickers",
        now, now, now, "d" * 64, {},
    )


def spot_snapshot(now):
    pair = {
        "symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
        "status": "TRADING", "isSpotTradingAllowed": True,
        "permissionSets": [["SPOT", "MARGIN"]],
    }
    return pair, {
        "serverTime": int(datetime.now(timezone.utc).timestamp() * 1000),
        "symbols": [pair],
    }


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
        coin = make_coin(now)
        pair, snapshot = spot_snapshot(now)

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
                patch.object(main, "_binance_spot_pairs_cache", {"BTC": [pair]}),
                patch.object(main, "_binance_spot_snapshot_observed_at", now),
                patch.object(main, "_binance_spot_exchange_info_snapshot", snapshot),
                patch("main._fetch_coingecko_binance_identity_proof", return_value=proof_for(now)),
                patch("layer1.announcement_importer.import_recent_binance_announcements", side_effect=fake_import),
                patch.object(main, "PostPublisher", side_effect=AssertionError("publisher must not be called")),
            ):
                summary = main._persist_layer1_market_intelligence([coin], database_path, [])

            self.assertEqual(summary["announcements"], 1)
            self.assertEqual(summary["provider_health"]["binance_announcements"], "PARTIAL_COVERAGE_NO_REPLAY")
            self.assertEqual(summary["announcement_coverage"], "OBSERVED_ONLY_NO_HISTORICAL_REPLAY")
            self.assertEqual(summary["announcement_revision_correlation_status"], "UNRESOLVED_NO_STABLE_PROVIDER_ID")
            self.assertEqual(summary["announcement_hints"][0]["type"], "new_listing")
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
                payload_row = store.conn.execute(
                    "SELECT payload_json FROM layer1_announcement_evidence WHERE source_id = ?",
                    (evidence.source_id,),
                ).fetchone()
                payload = json.loads(payload_row[0])
                self.assertEqual(payload["source_id_kind"], "payload_fingerprint")
                self.assertEqual(payload["source_url_kind"], "official_landing_page")
                self.assertEqual(payload["revision_correlation_status"], "UNRESOLVED_NO_STABLE_PROVIDER_ID")
                self.assertEqual(payload["raw_evidence_ref"], evidence.raw_evidence_ref)
            finally:
                store.close()

    def test_failed_optional_cms_import_degrades_without_blocking_market_pipeline(self):
        now = datetime.now(timezone.utc).isoformat()
        coin = make_coin(now)
        pair, snapshot = spot_snapshot(now)


        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "layer1-failed-import.sqlite")
            with (
                patch.dict(os.environ, {"ANNOUNCEMENT_DATABASE_URL": "postgresql://redacted.example/db"}),
                patch.object(main, "_binance_spot_pairs_cache", {"BTC": [pair]}),
                patch.object(main, "_binance_spot_snapshot_observed_at", now),
                patch.object(main, "_binance_spot_exchange_info_snapshot", snapshot),
                patch("main._fetch_coingecko_binance_identity_proof", return_value=proof_for(now)),
                patch(
                    "layer1.announcement_importer.import_recent_binance_announcements",
                    side_effect=RuntimeError("connection failed: postgresql://secret@host/db"),
                ),
                patch.object(main, "PostPublisher", side_effect=AssertionError("publisher must not be called")),
                self.assertLogs("agent", level="WARNING") as captured,
            ):
                summary = main._persist_layer1_market_intelligence([coin], database_path, [])
            self.assertNotIn("secret@host", "\n".join(captured.output))

            self.assertEqual(summary["provider_health"]["binance_announcements"], "DEGRADED_IMPORT_FAILED")
            self.assertEqual(summary["announcement_import_error_type"], "RuntimeError")
            self.assertEqual(summary["observations"], 1)
            self.assertEqual(summary["candidates"], 1)


if __name__ == "__main__":
    unittest.main()
