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

    def test_sqlite_read_rejects_tampered_observation_even_when_status_remains_accepted(self):
        from layer1.onchain import OnChainStore
        store = OnChainStore(":memory:", engine=self.engine)
        try:
            self.assertEqual(
                store.save_verified(self.eligibility, self.mapping, self.observation),
                "INSERTED",
            )
            tampered = OnChainObservation(
                **{**self.observation.__dict__, "transaction_hash": "c" * 64}
            )
            store.conn.execute(
                "UPDATE layer1_onchain_observations SET payload_json=? WHERE observation_id=?",
                (store._canonical(tampered.__dict__), self.observation.observation_id),
            )
            store.conn.commit()
            recovered = store.get_observation(self.observation.observation_id)
            self.assertEqual(recovered[1].status, "UNVERIFIED")
            self.assertEqual(recovered[1].reason_code, "ONCHAIN_RECEIPT_INVALID")
            self.assertIsNone(store.get_latest_accepted_observation(self.mapping.mapping_id))
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
        self.assertEqual(signed.status, "ACCEPTED")
        self.assertTrue(signed.receipt_signature)
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
    def test_verified_receipt_is_carried_into_evidence_and_rechecked_on_restore(self):
        import json
        import os
        from dataclasses import replace
        from unittest.mock import patch

        from layer1.evidence_verification import (
            EvidenceRecord,
            _effective_evidence_primary,
            _effective_evidence_status,
            _restore_evidence_record_proof,
        )

        fixture = OnChainAcceptanceReceiptTests()
        fixture.setUp()
        env = {
            "ONCHAIN_RECEIPT_HMAC_KEYRING_JSON": json.dumps({"test-key-v1": fixture.key.hex()}),
            "ONCHAIN_RECEIPT_ACTIVE_KEY_ID": "test-key-v1",
            "ONCHAIN_RECEIPT_TRUSTED_KEY_IDS": "test-key-v1",
        }
        with patch.dict(os.environ, env, clear=False):
            configured_engine = OnChainIntelligenceEngine.from_env(
                freshness_limits_seconds={"bitcoin-mainnet": 86400},
                minimum_confirmations_by_network={"bitcoin-mainnet": 6},
            )
            self.assertEqual(configured_engine.receipt_signing_key, fixture.key)
            self.assertEqual(configured_engine.receipt_key_id, "test-key-v1")

            signed = fixture.engine.validate(
                fixture.eligibility, fixture.mapping, fixture.observation,
            )
            evidence = EvidenceVerificationEngine.evidence_from_onchain_observation(
                fixture.observation, signed,
                receipt_verification_key=fixture.key,
                receipt_verification_key_id="test-key-v1",
            )
            self.assertEqual(evidence.source_status, "ACCEPTED")
            self.assertTrue(evidence.is_primary)
            self.assertTrue(evidence.source_receipt)
            self.assertTrue(evidence.source_receipt_payload)

            restored = replace(evidence)
            _restore_evidence_record_proof(restored)
            self.assertEqual(_effective_evidence_status(restored), "ACCEPTED")
            self.assertTrue(_effective_evidence_primary(restored))

            tampered = replace(evidence, value="c" * 64)
            _restore_evidence_record_proof(tampered)
            self.assertEqual(_effective_evidence_status(tampered), "UNVERIFIED")
            self.assertFalse(_effective_evidence_primary(tampered))

            receipt = json.loads(evidence.source_receipt)
            receipt["signature"] = "0" * 64
            tampered_signature = replace(
                evidence, source_receipt=json.dumps(receipt, sort_keys=True, separators=(",", ":")),
            )
            _restore_evidence_record_proof(tampered_signature)
            self.assertEqual(_effective_evidence_status(tampered_signature), "UNVERIFIED")

            payload = json.loads(evidence.source_receipt_payload)
            payload["observation"]["transaction_hash"] = "d" * 64
            tampered_payload = replace(
                evidence, source_receipt_payload=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            )
            _restore_evidence_record_proof(tampered_payload)
            self.assertEqual(_effective_evidence_status(tampered_payload), "UNVERIFIED")

            tampered_group = replace(
                evidence, independence_group="onchain:attacker-selected-network:alchemy",
            )
            _restore_evidence_record_proof(tampered_group)
            self.assertEqual(_effective_evidence_status(tampered_group), "UNVERIFIED")

            tampered_event_time = replace(evidence, event_at=(NOW - timedelta(hours=2)).isoformat())
            _restore_evidence_record_proof(tampered_event_time)
            self.assertEqual(_effective_evidence_status(tampered_event_time), "UNVERIFIED")

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
    def test_sqlite_store_revalidates_previous_trusted_key_after_rotation(self):
        import json
        import os
        import tempfile
        from unittest.mock import patch

        from layer1.onchain import OnChainStore

        fixture = OnChainAcceptanceReceiptTests()
        fixture.setUp()
        new_key = b"test-only-next-onchain-receipt-key-32-bytes"
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "onchain.sqlite3")
            original_store = OnChainStore(database_path, engine=fixture.engine)
            try:
                self.assertEqual(
                    original_store.save_verified(
                        fixture.eligibility, fixture.mapping, fixture.observation,
                    ),
                    "INSERTED",
                )
            finally:
                original_store.close()

            env = {
                "ONCHAIN_RECEIPT_HMAC_KEYRING_JSON": json.dumps({
                    "test-key-v1": fixture.key.hex(),
                    "current-v2": new_key.hex(),
                }),
                "ONCHAIN_RECEIPT_ACTIVE_KEY_ID": "current-v2",
                "ONCHAIN_RECEIPT_TRUSTED_KEY_IDS": "test-key-v1,current-v2",
            }
            with patch.dict(os.environ, env, clear=False):
                rotated_engine = OnChainIntelligenceEngine.from_env(
                    freshness_limits_seconds={"bitcoin-mainnet": 86400},
                    minimum_confirmations_by_network={"bitcoin-mainnet": 6},
                )
                rotated_store = OnChainStore(database_path, engine=rotated_engine)
                try:
                    restored = rotated_store.get_observation(fixture.observation.observation_id)
                    self.assertEqual(restored[1].status, "ACCEPTED")
                    self.assertEqual(restored[1].receipt_key_id, "test-key-v1")
                    self.assertIsNotNone(
                        rotated_store.get_latest_accepted_observation(fixture.mapping.mapping_id)
                    )
                finally:
                    rotated_store.close()
