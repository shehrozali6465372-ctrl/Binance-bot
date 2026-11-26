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

    def test_duplicate_json_key_ids_are_rejected_instead_of_last_value_wins(self):
        duplicate = (
            '{"current-v2":"' + TEST_KEY.hex() + '",'
            '"current-v2":"' + (b"z" * 32).hex() + '"}'
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            load_onchain_receipt_config_from_env({
                "ONCHAIN_RECEIPT_HMAC_KEYRING_JSON": duplicate,
                "ONCHAIN_RECEIPT_ACTIVE_KEY_ID": "current-v2",
                "ONCHAIN_RECEIPT_TRUSTED_KEY_IDS": "current-v2",
            })

    def test_keyring_hex_encoding_rejects_whitespace_and_non_hex_characters(self):
        for encoded in ("aa " * 32, "gg" * 32, "a" * 63):
            with self.subTest(encoded=encoded[:8]):
                with self.assertRaisesRegex(ValueError, "hex"):
                    load_onchain_receipt_config_from_env({
                        "ONCHAIN_RECEIPT_HMAC_KEYRING_JSON": '{"key-v1":"' + encoded + '"}',
                    })

    def test_short_or_malformed_key_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "shorter than 32 bytes"):
            load_onchain_receipt_config_from_env({
                "ONCHAIN_RECEIPT_HMAC_KEYRING_JSON": '{"bad-v1":"' + (b"x" * 16).hex() + '"}',
            })


if __name__ == "__main__":
    unittest.main()
