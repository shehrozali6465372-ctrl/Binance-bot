import unittest
from datetime import datetime, timedelta, timezone

from layer1.evidence_verification import EvidenceVerificationEngine
from layer1.foundation import EligibilityDecision
from layer1.onchain import (
    OnChainAssetMapping,
    OnChainIntelligenceEngine,
    OnChainObservation,
    OnChainValidationResult,
)


RECEIPT_KEY = b"test-only-onchain-receipt-key-32-bytes-minimum"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


class OnChainAcceptanceReceiptTests(unittest.TestCase):
    def setUp(self):
        self.key = RECEIPT_KEY
        self.eligibility = EligibilityDecision(
            status="ELIGIBLE",
            asset_id="coingecko:bitcoin",
            symbol="BTC",
            eligible_pairs=("BTCUSDT",),
            verified_at=(NOW - timedelta(minutes=2)).isoformat(),
            identity_proof_status="VERIFIED",
            identity_proof_source="coingecko_coin_tickers",
            identity_proof_verified_at=(NOW - timedelta(minutes=2)).isoformat(),
            identity_proof_source_timestamp=(NOW - timedelta(minutes=2)).isoformat(),
            identity_proof_data_hash="a" * 64,
        )
        self.mapping = OnChainAssetMapping(
            mapping_id="btc-mainnet-native-v1",
            asset_id="coingecko:bitcoin",
            binance_symbol="BTC",
            network_id="bitcoin-mainnet",
            network_family="UTXO",
            chain_id="bitcoin-mainnet",
            representation="NATIVE",
            contract_address=None,
            token_standard=None,
            decimals=8,
            mapping_status="VERIFIED",
            source_type="OFFICIAL_NETWORK",
            source_url="https://bitcoin.org/",
            verified_at=(NOW - timedelta(minutes=2)).isoformat(),
        )
        self.observation = OnChainObservation(
            observation_id="btc-block-900000-tx-1",
            mapping_id=self.mapping.mapping_id,
            asset_id=self.mapping.asset_id,
            network_id=self.mapping.network_id,
            chain_id=self.mapping.chain_id,
            provider="alchemy",
            endpoint_id="bitcoin-mainnet-rpc",
            observation_type="TRANSACTION",
            block_height=900000,
            block_hash="a" * 64,
            transaction_hash="b" * 64,
            block_time=(NOW - timedelta(minutes=1)).isoformat(),
            observed_at=NOW.isoformat(),
            finality="CONFIRMED",
            finality_reference="confirmations=6",
        )
        self.engine = OnChainIntelligenceEngine(
            freshness_limits_seconds={"bitcoin-mainnet": 86400},
            minimum_confirmations_by_network={"bitcoin-mainnet": 6},
            receipt_signing_key=self.key,
            receipt_key_id="test-key-v1",
        )

    def test_engine_without_receipt_signing_key_fails_closed(self):
        unsigned_engine = OnChainIntelligenceEngine(
            freshness_limits_seconds={"bitcoin-mainnet": 86400},
            minimum_confirmations_by_network={"bitcoin-mainnet": 6},
        )
        result = unsigned_engine.validate(self.eligibility, self.mapping, self.observation)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason_code, "ONCHAIN_RECEIPT_SIGNING_NOT_CONFIGURED")
        self.assertFalse(result.receipt_signature)

    def test_sqlite_store_refuses_unbound_observation_before_persistence(self):
        from layer1.onchain import OnChainStore
        store = OnChainStore(":memory:", engine=self.engine)
        try:
            with self.assertRaisesRegex(ValueError, "ONCHAIN_OBSERVATION_PROVENANCE_REQUIRED"):
                store.save_verified(self.eligibility, self.mapping, self.observation)
            self.assertIsNone(store.get_latest_accepted_observation(self.mapping.mapping_id))
            self.assertIsNone(store.get_observation(self.observation.observation_id))
        finally:
            store.close()

    def test_engine_signed_receipt_stays_untrusted_until_key_id_is_approved(self):
        forged = OnChainValidationResult(
            "ACCEPTED", "ONCHAIN_OBSERVATION_VERIFIED", "caller supplied",
            self.observation.observation_id, self.observation.asset_id,
            self.observation.mapping_id, self.observation.network_id,
            self.observation.provider,
        )
        untrusted = EvidenceVerificationEngine.evidence_from_onchain_observation(
            self.observation, forged, receipt_verification_key=self.key,
        )
        self.assertEqual(untrusted.source_status, "UNVERIFIED")
        self.assertFalse(untrusted.is_primary)

        signed = self.engine.validate(self.eligibility, self.mapping, self.observation)
        self.assertEqual(signed.status, "UNVERIFIED")
        self.assertEqual(signed.reason_code, "ONCHAIN_OBSERVATION_PROVENANCE_REQUIRED")
        self.assertFalse(signed.receipt_signature)
        verified = EvidenceVerificationEngine.evidence_from_onchain_observation(
            self.observation, signed, receipt_verification_key=self.key,
            receipt_verification_key_id="test-key-v1",
        )
        self.assertEqual(verified.source_status, "UNVERIFIED")
        self.assertFalse(verified.is_primary)
        self.assertIsNone(verified.source_authority_id)
        missing_key_id = EvidenceVerificationEngine.evidence_from_onchain_observation(
            self.observation, signed, receipt_verification_key=self.key,
        )
        self.assertEqual(missing_key_id.source_status, "UNVERIFIED")

        wrong_key = EvidenceVerificationEngine.evidence_from_onchain_observation(
            self.observation, signed, receipt_verification_key=b"x" * 40,
            receipt_verification_key_id="test-key-v1",
        )
        self.assertEqual(wrong_key.source_status, "UNVERIFIED")
        wrong_key_id = EvidenceVerificationEngine.evidence_from_onchain_observation(
            self.observation, signed, receipt_verification_key=self.key,
            receipt_verification_key_id="retired-key",
        )
        self.assertEqual(wrong_key_id.source_status, "UNVERIFIED")

        tampered_observation = OnChainObservation(
            **{**self.observation.__dict__, "transaction_hash": "c" * 64}
        )
        tampered = EvidenceVerificationEngine.evidence_from_onchain_observation(
            tampered_observation, signed, receipt_verification_key=self.key,
            receipt_verification_key_id="test-key-v1",
        )
        self.assertEqual(tampered.source_status, "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()


class OnChainReceiptPersistenceTests(unittest.TestCase):
    def test_unbound_observation_is_not_promoted_to_accepted_evidence(self):
        from layer1.evidence_verification import EvidenceVerificationEngine
        fixture = OnChainAcceptanceReceiptTests()
        fixture.setUp()
        signed = fixture.engine.validate(
            fixture.eligibility, fixture.mapping, fixture.observation,
        )
        self.assertEqual(signed.status, "UNVERIFIED")
        self.assertEqual(signed.reason_code, "ONCHAIN_OBSERVATION_PROVENANCE_REQUIRED")
        evidence = EvidenceVerificationEngine.evidence_from_onchain_observation(
            fixture.observation, signed,
            receipt_verification_key=fixture.key,
            receipt_verification_key_id="test-key-v1",
        )
        self.assertEqual(evidence.source_status, "UNVERIFIED")
        self.assertFalse(evidence.is_primary)

    def test_environment_configured_engine_without_allowlisted_key_stays_unsigned(self):
        import json
        import os
        from unittest.mock import patch

        env = {
            "ONCHAIN_RECEIPT_HMAC_KEYRING_JSON": json.dumps({"not-trusted-v1": RECEIPT_KEY.hex()}),
            "ONCHAIN_RECEIPT_ACTIVE_KEY_ID": "",
            "ONCHAIN_RECEIPT_TRUSTED_KEY_IDS": "",
        }
        with patch.dict(os.environ, env, clear=False):
            engine = OnChainIntelligenceEngine.from_env()
            self.assertIsNone(engine.receipt_signing_key)
            self.assertEqual(engine.receipt_key_id, "")


class OnChainReceiptRotationPersistenceTests(unittest.TestCase):
    def test_sqlite_store_does_not_persist_unbound_observation_for_key_rotation(self):
        import os
        import tempfile
        from layer1.onchain import OnChainStore

        fixture = OnChainAcceptanceReceiptTests()
        fixture.setUp()
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "onchain.sqlite3")
            original_store = OnChainStore(database_path, engine=fixture.engine)
            try:
                with self.assertRaisesRegex(ValueError, "ONCHAIN_OBSERVATION_PROVENANCE_REQUIRED"):
                    original_store.save_verified(
                        fixture.eligibility, fixture.mapping, fixture.observation,
                    )
            finally:
                original_store.close()
            rotated_store = OnChainStore(database_path, engine=fixture.engine)
            try:
                self.assertIsNone(
                    rotated_store.get_latest_accepted_observation(fixture.mapping.mapping_id)
                )
            finally:
                rotated_store.close()
