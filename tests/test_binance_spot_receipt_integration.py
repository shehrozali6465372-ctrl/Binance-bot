import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import main
from dataclasses import fields
from layer1.evidence_verification import (
    EvidenceRecord, EvidenceVerificationEngine, _effective_evidence_status,
    _restore_evidence_record_proof,
)
from layer1.foundation import ProviderResponse
from layer1.source_receipts import verify_source_ingestion_receipt


class BinanceSpotReceiptIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.original = (
            main._binance_listed_cache,
            main._binance_listed_cache_time,
            main._binance_spot_pairs_cache,
            main._binance_spot_snapshot_observed_at,
            main._binance_spot_exchange_info_snapshot,
            main._binance_spot_provider_metadata,
            main._binance_spot_provider_status,
        )
        main._binance_listed_cache = None
        main._binance_listed_cache_time = 0
        main._binance_spot_pairs_cache = {}
        main._binance_spot_snapshot_observed_at = None
        main._binance_spot_exchange_info_snapshot = None
        main._binance_spot_provider_metadata = {}
        main._binance_spot_provider_status = "NOT_REQUESTED"

    def tearDown(self):
        (
            main._binance_listed_cache,
            main._binance_listed_cache_time,
            main._binance_spot_pairs_cache,
            main._binance_spot_snapshot_observed_at,
            main._binance_spot_exchange_info_snapshot,
            main._binance_spot_provider_metadata,
            main._binance_spot_provider_status,
        ) = self.original

    def response(self):
        return ProviderResponse({
            "serverTime": int(datetime.now(timezone.utc).timestamp() * 1000),
            "symbols": [{
                "symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
                "status": "TRADING", "isSpotTradingAllowed": True,
                "permissionSets": [["SPOT", "MARGIN"]],
            }],
        })

    def test_fetch_boundary_receipt_is_carried_into_claim_evidence_and_verified(self):
        key = b"approved-binance-spot-key-material-32bytes"
        env = {
            "BINANCE_SPOT_INGESTION_HMAC_KEY_HEX": key.hex(),
            "BINANCE_SPOT_INGESTION_KEY_ID": "spot-key-v1",
            "BINANCE_SOURCE_RECEIPT_TRUSTED_KEY_IDS": "spot-key-v1",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "main.market_data_http_get", return_value=self.response()
        ):
            self.assertEqual(main._get_binance_listed(), {"BTC"})
            snapshot = main._binance_spot_exchange_info_snapshot
            self.assertIn("BTCUSDT", snapshot["source_receipts"])
            receipt_bundle = snapshot["source_receipts"]["BTCUSDT"]
            self.assertTrue(verify_source_ingestion_receipt(
                receipt_bundle["receipt"], receipt_bundle["payload"],
                verification_keys={"spot-key-v1": key},
                expected_authority_id="binance_spot_exchange_info",
                trusted_key_ids={"spot-key-v1"},
            ))
            evidence = EvidenceVerificationEngine().evidence_from_binance_spot_pairs(
                "coingecko:bitcoin", main._binance_spot_pairs_cache["BTC"],
                observed_at=main._binance_spot_snapshot_observed_at,
                expected_base_asset="BTC", allowed_quote_assets=("USDT",),
                source_receipts=snapshot["source_receipts"],
            )
        self.assertEqual(evidence[0].source_status, "ACCEPTED")
        self.assertEqual(evidence[0].source_authority_id, "binance_spot_exchange_info")
        self.assertEqual(evidence[0].source_receipt_key_id, "spot-key-v1")
        with patch.dict(os.environ, env, clear=False):
            serialized = {
                item.name: getattr(evidence[0], item.name)
                for item in fields(evidence[0]) if item.name != "_provenance_proof"
            }
            restored = EvidenceRecord(**json.loads(json.dumps(serialized)))
            _restore_evidence_record_proof(restored)
            self.assertEqual(_effective_evidence_status(restored), "ACCEPTED")

    def test_final_publication_revalidation_fails_closed_without_approved_receipt_key(self):
        env = {
            "BINANCE_ALLOWED_QUOTE_ASSETS": "USDT",
            "BINANCE_SPOT_INGESTION_HMAC_KEY_HEX": "",
            "BINANCE_SPOT_INGESTION_KEY_ID": "",
            "BINANCE_SOURCE_RECEIPT_TRUSTED_KEY_IDS": "",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "main.market_data_http_get", return_value=self.response()
        ) as fetch:
            self.assertFalse(main._revalidate_binance_spot_asset("BTC", "coingecko:bitcoin"))
            self.assertEqual(fetch.call_count, 1)

    def test_fetch_without_approved_key_never_mints_or_attaches_a_receipt(self):
        env = {
            "BINANCE_SPOT_INGESTION_HMAC_KEY_HEX": "",
            "BINANCE_SPOT_INGESTION_KEY_ID": "",
            "BINANCE_SOURCE_RECEIPT_TRUSTED_KEY_IDS": "",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "main.market_data_http_get", return_value=self.response()
        ):
            self.assertEqual(main._get_binance_listed(), {"BTC"})
            snapshot = main._binance_spot_exchange_info_snapshot
        self.assertEqual(snapshot["source_receipts"], {})


if __name__ == "__main__":
    unittest.main()
