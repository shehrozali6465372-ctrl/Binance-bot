import unittest

from layer1.onchain_receipt_config import load_onchain_receipt_config_from_env


TEST_KEY = b"test-only-onchain-receipt-key-32-bytes-minimum"


class OnChainReceiptConfigTests(unittest.TestCase):
    def test_loads_rotation_safe_keyring_and_explicit_trust_allowlist(self):
        config = load_onchain_receipt_config_from_env({
            "ONCHAIN_RECEIPT_HMAC_KEYRING_JSON": (
                '{"current-v2":"' + TEST_KEY.hex() + '",'
                '"previous-v1":"' + (b"p" * 32).hex() + '"}'
            ),
            "ONCHAIN_RECEIPT_ACTIVE_KEY_ID": "current-v2",
            "ONCHAIN_RECEIPT_TRUSTED_KEY_IDS": "current-v2,previous-v1",
        })
        self.assertEqual(config.active_key_id, "current-v2")
        self.assertEqual(config.active_signing_key, TEST_KEY)
        self.assertEqual(config.keyring["previous-v1"], b"p" * 32)
        self.assertEqual(config.trusted_key_ids, frozenset({"current-v2", "previous-v1"}))

    def test_empty_environment_keeps_receipt_signing_and_trust_disabled(self):
        config = load_onchain_receipt_config_from_env({})
        self.assertEqual(config.keyring, {})
        self.assertEqual(config.trusted_key_ids, frozenset())
        self.assertEqual(config.active_key_id, "")
        self.assertIsNone(config.active_signing_key)

    def test_active_key_must_be_present_and_explicitly_trusted(self):
        with self.assertRaisesRegex(ValueError, "active.*trusted"):
            load_onchain_receipt_config_from_env({
                "ONCHAIN_RECEIPT_HMAC_KEYRING_JSON": '{"current-v2":"' + TEST_KEY.hex() + '"}',
                "ONCHAIN_RECEIPT_ACTIVE_KEY_ID": "current-v2",
                "ONCHAIN_RECEIPT_TRUSTED_KEY_IDS": "",
            })

    def test_trusted_key_must_exist_in_keyring(self):
        with self.assertRaisesRegex(ValueError, "trusted key IDs.*keyring"):
            load_onchain_receipt_config_from_env({
                "ONCHAIN_RECEIPT_TRUSTED_KEY_IDS": "missing-v1",
            })

    def test_short_or_malformed_key_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "shorter than 32 bytes"):
            load_onchain_receipt_config_from_env({
                "ONCHAIN_RECEIPT_HMAC_KEYRING_JSON": '{"bad-v1":"' + (b"x" * 16).hex() + '"}',
            })


if __name__ == "__main__":
    unittest.main()
