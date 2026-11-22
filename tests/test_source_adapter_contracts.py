from __future__ import annotations

import unittest
import hashlib
import json
from datetime import datetime, timezone
from layer1.evidence_verification import EvidenceRecord
from layer1.foundation import MarketObservation
from layer1.onchain import OnChainObservation, OnChainValidationResult


class SourceAdapterHashContractTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc).isoformat()
    def test_evidence_record_requires_sha256_format_when_content_hash_is_present(self):
        record = EvidenceRecord(
            source_id="source-1", source_family="provider-a", source_kind="MARKET",
            publisher="Provider A", subject="coingecko:abc", claim_key="market.price",
            value=10.0, published_at=self.now,
            observed_at=self.now, content_hash="sha256:not-hex",
        )
        with self.assertRaisesRegex(ValueError, "content_hash must be a lowercase SHA-256"):
            record.validate()

    def test_evidence_record_allows_absent_hash_for_sources_without_raw_payload(self):
        record = EvidenceRecord(
            source_id="onchain-observation-1", source_family="provider-a", source_kind="ONCHAIN",
            publisher="Provider A", subject="coingecko:abc", claim_key="onchain.transaction_hash",
            value="0x" + "1" * 64, published_at=self.now,
            observed_at=self.now, content_hash="",
        )
        record.validate()

    def test_market_observation_requires_sha256_format_when_data_hash_is_present(self):
        observation = MarketObservation(
            asset_id="coingecko:abc", provider="provider-a", endpoint="/market",
            observed_at=self.now, price=10.0,
            data_hash="sha256:not-hex",
        )
        with self.assertRaisesRegex(ValueError, "data_hash must be a lowercase SHA-256"):
            observation.validate()

    def test_onchain_observation_adapter_does_not_claim_raw_payload_hash(self):
        observation = OnChainObservation(
            observation_id="obs-1", mapping_id="mapping-1", asset_id="coingecko:abc",
            network_id="ethereum-mainnet", chain_id="1", provider="alchemy",
            endpoint_id="eth-mainnet-read", observation_type="transfer", block_height=10,
            block_hash="0x" + "a" * 64, transaction_hash="0x" + "b" * 64,
            block_time=self.now, observed_at=self.now, finality="FINALIZED",
            finality_reference="finalized-10",
        )
        accepted = OnChainValidationResult(
            "ACCEPTED", "ONCHAIN_OBSERVATION_VERIFIED", "fixture", "obs-1",
            "coingecko:abc", "mapping-1", "ethereum-mainnet", "alchemy",
        )
        from layer1.evidence_verification import EvidenceVerificationEngine
        record = EvidenceVerificationEngine.evidence_from_onchain_observation(observation, accepted)
        self.assertEqual(record.content_hash, "")
        self.assertEqual(record.lineage_id, "")
        self.assertEqual(record.source_family, "alchemy")

    def test_exchange_info_hash_is_a_canonical_projection_not_raw_response_hash(self):
        from layer1.evidence_verification import EvidenceVerificationEngine
        pair = {
            "symbol": "ABCUSDT", "baseAsset": "ABC", "quoteAsset": "USDT",
            "status": "TRADING", "isSpotTradingAllowed": True,
            "permissionSets": [["SPOT"]], "ignored_provider_field": "not-in-projection",
        }
        record = EvidenceVerificationEngine.evidence_from_binance_spot_pairs(
            "coingecko:abc", [pair], observed_at=self.now,
        )[0]
        canonical = {
            "symbol": "ABCUSDT", "baseAsset": "ABC", "quoteAsset": "USDT",
            "status": "TRADING", "isSpotTradingAllowed": True,
            "permissionSets": [["SPOT"]],
        }
        expected = hashlib.sha256(json.dumps(
            canonical, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        self.assertEqual(record.content_hash, expected)
        self.assertNotEqual(record.content_hash, hashlib.sha256(json.dumps(
            pair, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest())

    def test_market_observation_allows_absent_hash_when_source_does_not_supply_it(self):
        observation = MarketObservation(
            asset_id="coingecko:abc", provider="provider-a", endpoint="/market",
            observed_at=self.now, price=10.0,
        )
        observation.validate()
        self.assertEqual(observation.data_hash, "")


if __name__ == "__main__":
    unittest.main()
