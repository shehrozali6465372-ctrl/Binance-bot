from __future__ import annotations

import unittest

from layer1.source_receipts import (
    SourceIngestionReceipt,
    create_source_ingestion_receipt,
    verify_source_ingestion_receipt, load_source_receipt_config_from_env,
    load_cms_source_receipt_config_from_env,
)


class SourceIngestionReceiptTests(unittest.TestCase):
    def setUp(self):
        self.key = b"test-only-source-ingestion-key-32-bytes"
        self.payload = {
            "authority_id": "binance_announcement_cms",
            "source_id": "cms-row-1",
            "endpoint": "postgres:binance_announcement_events",
            "observed_at": "2026-11-24T10:00:00+00:00",
            "response_hash": "a" * 64,
        }

    def test_receipt_authenticates_exact_canonical_payload(self):
        receipt = create_source_ingestion_receipt(
            self.payload, authority_id="binance_announcement_cms",
            key_id="test-cms-v1", signing_key=self.key,
        )
        self.assertIsInstance(receipt, SourceIngestionReceipt)
        self.assertTrue(verify_source_ingestion_receipt(
            receipt, self.payload,
            verification_keys={"test-cms-v1": self.key},
            expected_authority_id="binance_announcement_cms",
            trusted_key_ids={"test-cms-v1"},
        ))

    def test_payload_tampering_invalidates_receipt(self):
        receipt = create_source_ingestion_receipt(
            self.payload, authority_id="binance_announcement_cms",
            key_id="test-cms-v1", signing_key=self.key,
        )
        changed = {**self.payload, "response_hash": "b" * 64}
        self.assertFalse(verify_source_ingestion_receipt(
            receipt, changed,
            verification_keys={"test-cms-v1": self.key},
            expected_authority_id="binance_announcement_cms",
            trusted_key_ids={"test-cms-v1"},
        ))

    def test_unknown_or_unapproved_key_id_fails_closed(self):
        receipt = create_source_ingestion_receipt(
            self.payload, authority_id="binance_announcement_cms",
            key_id="test-cms-v1", signing_key=self.key,
        )
        self.assertFalse(verify_source_ingestion_receipt(
            receipt, self.payload,
            verification_keys={"test-cms-v1": self.key},
            expected_authority_id="binance_announcement_cms",
            trusted_key_ids=set(),
        ))
        self.assertFalse(verify_source_ingestion_receipt(
            receipt, self.payload,
            verification_keys={},
            expected_authority_id="binance_announcement_cms",
            trusted_key_ids={"test-cms-v1"},
        ))

    def test_wrong_authority_and_wrong_key_do_not_verify(self):
        receipt = create_source_ingestion_receipt(
            self.payload, authority_id="binance_announcement_cms",
            key_id="test-cms-v1", signing_key=self.key,
        )
        self.assertFalse(verify_source_ingestion_receipt(
            receipt, self.payload,
            verification_keys={"test-cms-v1": self.key},
            expected_authority_id="binance_spot_exchange_info",
            trusted_key_ids={"test-cms-v1"},
        ))
        self.assertFalse(verify_source_ingestion_receipt(
            receipt, self.payload,
            verification_keys={"test-cms-v1": b"x" * 32},
            expected_authority_id="binance_announcement_cms",
            trusted_key_ids={"test-cms-v1"},
        ))

    def test_signing_rejects_short_keys_and_invalid_key_ids(self):
        with self.assertRaises(ValueError):
            create_source_ingestion_receipt(
                self.payload, authority_id="binance_announcement_cms",
                key_id="test-cms-v1", signing_key=b"short",
            )
        with self.assertRaises(ValueError):
            create_source_ingestion_receipt(
                self.payload, authority_id="binance_announcement_cms",
                key_id="bad key id", signing_key=self.key,
            )


    def test_receipt_round_trips_through_json_compatible_storage(self):
        receipt = create_source_ingestion_receipt(
            self.payload, authority_id="binance_announcement_cms",
            key_id="test-cms-v1", signing_key=self.key,
        )
        restored = SourceIngestionReceipt.from_dict(receipt.to_dict())
        self.assertEqual(restored, receipt)
        self.assertTrue(verify_source_ingestion_receipt(
            restored.to_dict(), self.payload,
            verification_keys={"test-cms-v1": self.key},
            expected_authority_id="binance_announcement_cms",
            trusted_key_ids={"test-cms-v1"},
        ))

    def test_malformed_or_extra_receipt_fields_fail_closed(self):
        receipt = create_source_ingestion_receipt(
            self.payload, authority_id="binance_announcement_cms",
            key_id="test-cms-v1", signing_key=self.key,
        )
        malformed = {**receipt.to_dict(), "unexpected": "value"}
        self.assertFalse(verify_source_ingestion_receipt(
            malformed, self.payload,
            verification_keys={"test-cms-v1": self.key},
            expected_authority_id="binance_announcement_cms",
            trusted_key_ids={"test-cms-v1"},
        ))


    def test_payload_rejects_non_json_mapping_keys_and_tuple_values(self):
        with self.assertRaises(ValueError):
            create_source_ingestion_receipt(
                {"authority_id": "binance_announcement_cms", 1: "ambiguous"},
                authority_id="binance_announcement_cms", key_id="test-cms-v1",
                signing_key=self.key,
            )
        with self.assertRaises(ValueError):
            create_source_ingestion_receipt(
                {"authority_id": "binance_announcement_cms", "items": ("x",)},
                authority_id="binance_announcement_cms", key_id="test-cms-v1",
                signing_key=self.key,
            )


    def test_keyring_supports_rotation_and_keeps_old_trusted_keys_verifiable(self):
        import json
        from unittest.mock import patch
        old_key = b"previous-approved-source-key-material-32"
        current_key = b"current-approved-source-key-material-32"
        env = {
            "BINANCE_SOURCE_RECEIPT_HMAC_KEYRING_JSON": json.dumps({
                "spot-key-v1": old_key.hex(), "spot-key-v2": current_key.hex(),
            }),
            "BINANCE_SPOT_INGESTION_KEY_ID": "spot-key-v2",
            "BINANCE_SOURCE_RECEIPT_TRUSTED_KEY_IDS": "spot-key-v1,spot-key-v2",
            "BINANCE_SPOT_INGESTION_HMAC_KEY_HEX": "",
        }
        with patch.dict("os.environ", env, clear=False):
            keyring, trusted, active = load_source_receipt_config_from_env()
        self.assertEqual(keyring, {"spot-key-v1": old_key, "spot-key-v2": current_key})
        self.assertEqual(trusted, {"spot-key-v1", "spot-key-v2"})
        self.assertEqual(active, "spot-key-v2")
        old_receipt = create_source_ingestion_receipt(
            self.payload, authority_id="binance_announcement_cms",
            key_id="spot-key-v1", signing_key=old_key,
        )
        self.assertTrue(verify_source_ingestion_receipt(
            old_receipt, self.payload, verification_keys=keyring,
            expected_authority_id="binance_announcement_cms", trusted_key_ids=trusted,
        ))

    def test_keyring_rejects_duplicate_trusted_key_ids(self):
        import json
        from unittest.mock import patch
        key = b"duplicate-trust-key-material-at-least-32-bytes"
        env = {
            "BINANCE_SOURCE_RECEIPT_HMAC_KEYRING_JSON": json.dumps({"spot-v1": key.hex()}),
            "BINANCE_SPOT_INGESTION_KEY_ID": "spot-v1",
            "BINANCE_SOURCE_RECEIPT_TRUSTED_KEY_IDS": "spot-v1,spot-v1",
            "BINANCE_SPOT_INGESTION_HMAC_KEY_HEX": "",
        }
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaisesRegex(ValueError, "duplicates"):
                load_source_receipt_config_from_env()

    def test_active_signing_key_must_exist_and_be_explicitly_trusted(self):
        import json
        from unittest.mock import patch
        key = b"active-trust-key-material-at-least-32-bytes"
        cases = (
            ({"spot-v1": key.hex()}, "spot-v1", "", "explicitly trusted"),
            ({"spot-v1": key.hex()}, "missing-v2", "spot-v1", "explicitly trusted"),
        )
        for keyring, active, trusted, message in cases:
            with self.subTest(active=active, trusted=trusted):
                env = {
                    "BINANCE_SOURCE_RECEIPT_HMAC_KEYRING_JSON": json.dumps(keyring),
                    "BINANCE_SPOT_INGESTION_KEY_ID": active,
                    "BINANCE_SOURCE_RECEIPT_TRUSTED_KEY_IDS": trusted,
                    "BINANCE_SPOT_INGESTION_HMAC_KEY_HEX": "",
                }
                with patch.dict("os.environ", env, clear=True):
                    with self.assertRaisesRegex(ValueError, message):
                        load_source_receipt_config_from_env()

    def test_trusted_key_ids_must_exist_in_keyring(self):
        from unittest.mock import patch
        env = {
            "BINANCE_SOURCE_RECEIPT_TRUSTED_KEY_IDS": "missing-v1",
            "BINANCE_SPOT_INGESTION_HMAC_KEY_HEX": "",
        }
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaisesRegex(ValueError, "must exist in the keyring"):
                load_source_receipt_config_from_env()

    def test_keyring_rejects_short_or_malformed_keys_without_exposing_values(self):
        import json
        from unittest.mock import patch
        env = {
            "BINANCE_SOURCE_RECEIPT_HMAC_KEYRING_JSON": json.dumps({"spot-key-v1": "abcd"}),
            "BINANCE_SPOT_INGESTION_KEY_ID": "spot-key-v1",
            "BINANCE_SOURCE_RECEIPT_TRUSTED_KEY_IDS": "spot-key-v1",
        }
        with patch.dict("os.environ", env, clear=False):
            with self.assertRaisesRegex(ValueError, "shorter than 32 bytes"):
                load_source_receipt_config_from_env()


    def test_node_cms_worker_receipt_vector_is_verified_by_python_contract(self):
        payload = {
            "authority_id": "binance_announcement_cms",
            "schema_version": "cms-announcement-normalized-v1",
            "topic": "com_announcement_en",
            "catalog_id": "48",
            "source_id": "a" * 64,
            "content_hash": "b" * 64,
            "catalog_name": "New Cryptocurrency Listing",
            "event_type": "listing",
            "title": "Binance will list Example (EXM)",
            "body": "Official announcement body",
            "disclaimer": "Risk notice",
            "publisher": "Binance",
            "source_url": "https://www.binance.com/en/support/announcement",
            "published_at": "2026-11-23T23:00:00.000000+00:00",
            "observed_at": "2026-11-24T00:00:00.000000+00:00",
        }
        receipt = {
            "version": 1,
            "authority_id": "binance_announcement_cms",
            "key_id": "cms-key-v1",
            "payload_hash": "8bb92169d013274a44e6bdb269c174591fc561b97d2845e9677389ca57856b20",
            "signature": "aff3ba4db5d87ce89b6be773780d5a1833bd90f11411d2274517785c17243dfb",
        }
        key = b"cms-test-key-material-at-least-thirty-two-bytes"
        self.assertTrue(verify_source_ingestion_receipt(
            receipt, payload, verification_keys={"cms-key-v1": key},
            expected_authority_id="binance_announcement_cms", trusted_key_ids={"cms-key-v1"},
        ))


if __name__ == "__main__":
    unittest.main()


class CmsSourceReceiptConfigTests(unittest.TestCase):
    def test_cms_keyring_is_separate_and_supports_verification_only_configuration(self):
        import json
        from unittest.mock import patch
        old_key = b"cms-old-key-material-at-least-thirty-two-bytes"
        current_key = b"cms-current-key-material-at-least-thirty-two-bytes"
        env = {
            "BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON": json.dumps({
                "cms-v1": old_key.hex(), "cms-v2": current_key.hex(),
            }),
            "BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS": "cms-v1,cms-v2",
        }
        with patch.dict("os.environ", env, clear=True):
            keys, trusted = load_cms_source_receipt_config_from_env()
        self.assertEqual(keys, {"cms-v1": old_key, "cms-v2": current_key})
        self.assertEqual(trusted, {"cms-v1", "cms-v2"})

    def test_missing_cms_receipt_config_returns_empty_trust_not_a_default_key(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {}, clear=True):
            keys, trusted = load_cms_source_receipt_config_from_env()
        self.assertEqual(keys, {})
        self.assertEqual(trusted, frozenset())

    def test_partial_cms_receipt_config_fails_closed(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {"BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS": "cms-v1"}, clear=True):
            with self.assertRaisesRegex(ValueError, "CMS source receipt configuration is incomplete"):
                load_cms_source_receipt_config_from_env()

    def test_cms_keyring_rejects_duplicate_json_object_keys(self):
        from unittest.mock import patch
        key = b"cms-key-material-long-enough-for-receipts"
        duplicate_json = '{"cms-v1":"' + key.hex() + '","cms-v1":"' + key.hex() + '"}'
        with patch.dict("os.environ", {
            "BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON": duplicate_json,
            "BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS": "cms-v1",
        }, clear=True):
            with self.assertRaisesRegex(ValueError, "keyring configuration is invalid"):
                load_cms_source_receipt_config_from_env()

    def test_cms_trusted_ids_must_be_unique_and_provisioned(self):
        import json
        from unittest.mock import patch
        key = b"cms-key-material-long-enough-for-receipts"
        base = {"BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON": json.dumps({"cms-v1": key.hex()})}
        for trusted in ("cms-v1,cms-v1", "missing-v2"):
            with self.subTest(trusted=trusted), patch.dict("os.environ", {**base, "BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS": trusted}, clear=True):
                with self.assertRaises(ValueError):
                    load_cms_source_receipt_config_from_env()
