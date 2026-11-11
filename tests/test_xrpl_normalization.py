import unittest

from layer1.onchain_ingestion import normalize_xrpl_payment
from layer1.onchain_providers import XrplAccountTransaction


ACCOUNT = "rLNaPoKeeBjZe2qs6x52yVPZpZ8td4dc6w"
DESTINATION = "rBqiK7z9a7M8w2F7yQzvVJ5QJ8qQh2vKQ"
ISSUER = "rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq"
TX_HASH = "A" * 64
LEDGER_HASH = "B" * 64


class XrplPaymentNormalizationTests(unittest.TestCase):
    def record(self, *, tx=None, meta=None, ledger=500):
        transaction = {
            "TransactionType": "Payment", "Account": ACCOUNT,
            "Destination": DESTINATION, "Amount": {
                "currency": "USD", "issuer": ISSUER, "value": "12.345",
            },
        }
        transaction.update(tx or {})
        metadata = {"TransactionResult": "tesSUCCESS", "TransactionIndex": 2,
                    "delivered_amount": {"currency": "USD", "issuer": ISSUER, "value": "12.345"}}
        metadata.update(meta or {})
        if meta is not None and "delivered_amount" in meta and meta["delivered_amount"] is None:
            metadata.pop("delivered_amount", None)
        return XrplAccountTransaction(
            TX_HASH, ledger, "2026-11-11T12:00:00Z", transaction, metadata,
            {"validated": True, "hash": TX_HASH, "ledger_index": ledger},
        )

    def normalize(self, record=None, **overrides):
        args = dict(
            monitored_account=ACCOUNT, asset_id="coingecko:example", mapping_id="xrpl-usd-v1",
            issuer_address=ISSUER, issued_currency="USD", decimals=6,
            canonical_ledger_hash=LEDGER_HASH,
            block_time="2026-11-11T12:00:00+00:00",
            observed_at="2026-11-11T12:00:01+00:00",
            scope=f"issued:{ISSUER}:USD",
        )
        args.update(overrides)
        return normalize_xrpl_payment(record or self.record(), **args)

    def test_normalizes_validated_issued_currency_payment_using_delivered_amount(self):
        event = self.normalize()
        self.assertEqual(event.event_id, TX_HASH.lower())
        self.assertEqual(event.transaction_hash, TX_HASH.lower())
        self.assertEqual(event.block_number, 500)
        self.assertEqual(event.block_hash, LEDGER_HASH.lower())
        self.assertEqual(event.from_address, ACCOUNT)
        self.assertEqual(event.to_address, DESTINATION)
        self.assertEqual(event.amount_raw, "12345000")
        self.assertEqual(event.decimals, 6)
        self.assertEqual(event.canonical_status, "CANONICAL")
        self.assertIn("delivered_amount", event.provenance)

    def test_partial_payment_uses_delivered_amount_not_requested_amount(self):
        record = self.record(
            tx={"Flags": 0x00020000, "Amount": {"currency": "USD", "issuer": ISSUER, "value": "100"}},
            meta={"delivered_amount": {"currency": "USD", "issuer": ISSUER, "value": "3.25"}},
        )
        event = self.normalize(record)
        self.assertEqual(event.amount_raw, "3250000")

    def test_reserved_xrp_or_malformed_currency_mapping_is_rejected(self):
        for currency in ("XRP", "US", "USD ", "G" * 40):
            with self.subTest(currency=currency):
                with self.assertRaises(ValueError):
                    self.normalize(issued_currency=currency)

    def test_unrelated_currency_or_issuer_is_not_normalized(self):
        wrong_currency = self.record(meta={"delivered_amount": {
            "currency": "EUR", "issuer": ISSUER, "value": "12.345"}})
        wrong_issuer = self.record(meta={"delivered_amount": {
            "currency": "USD", "issuer": DESTINATION, "value": "12.345"}})
        self.assertIsNone(self.normalize(wrong_currency))
        self.assertIsNone(self.normalize(wrong_issuer))

    def test_non_payment_and_failed_payment_do_not_create_transfer_events(self):
        self.assertIsNone(self.normalize(self.record(tx={"TransactionType": "OfferCreate"})))
        self.assertIsNone(self.normalize(self.record(meta={"TransactionResult": "tecPATH_DRY"})))

    def test_missing_unavailable_or_malformed_delivered_amount_fails_closed(self):
        missing = self.record()
        missing.metadata.pop("delivered_amount")
        cases = [("missing", missing), ("unavailable", self.record(meta={"delivered_amount": "unavailable"})),
                 ("wrong-shape", self.record(meta={"delivered_amount": "12.345"})),
                 ("missing-value", self.record(meta={"delivered_amount": {"currency": "USD", "issuer": ISSUER}})),
                 ("nan", self.record(meta={"delivered_amount": {"currency": "USD", "issuer": ISSUER, "value": "NaN"}})),
                 ("zero", self.record(meta={"delivered_amount": {"currency": "USD", "issuer": ISSUER, "value": "0"}}))]
        for label, record in cases:
            with self.subTest(delivered=label):
                with self.assertRaises(ValueError):
                    self.normalize(record)

    def test_account_side_must_be_proven_by_payment_source_or_destination(self):
        with self.assertRaisesRegex(ValueError, "not the payment source or destination"):
            self.normalize(monitored_account=ISSUER)
        incoming = self.normalize(monitored_account=DESTINATION)
        self.assertEqual(incoming.to_address, DESTINATION)

    def test_amount_must_be_exactly_representable_at_configured_scale(self):
        with self.assertRaisesRegex(ValueError, "configured decimal scale"):
            self.normalize(self.record(meta={"delivered_amount": {
                "currency": "USD", "issuer": ISSUER, "value": "0.0000001"}}))

    def test_issued_currency_precision_and_exponent_bounds_are_enforced(self):
        too_precise = self.record(meta={"delivered_amount": {
            "currency": "USD", "issuer": ISSUER, "value": "1.12345678901234567"}})
        too_large = self.record(meta={"delivered_amount": {
            "currency": "USD", "issuer": ISSUER, "value": "1e96"}})
        too_small = self.record(meta={"delivered_amount": {
            "currency": "USD", "issuer": ISSUER, "value": "1e-82"}})
        for value in (too_precise, too_large, too_small):
            with self.assertRaisesRegex(ValueError, "precision/range"):
                self.normalize(value, decimals=18)

    def test_protocol_maximum_issued_amount_exponent_is_supported(self):
        record = self.record(meta={"delivered_amount": {
            "currency": "USD", "issuer": ISSUER, "value": "9999999999999999e80"}})
        event = self.normalize(record, decimals=0)
        self.assertEqual(event.amount_raw, str(9999999999999999 * (10 ** 80)))

    def test_trailing_zeroes_do_not_count_as_extra_significant_digits(self):
        record = self.record(meta={"delivered_amount": {
            "currency": "USD", "issuer": ISSUER, "value": "1.000000000000000000"}})
        event = self.normalize(record, decimals=6)
        self.assertEqual(event.amount_raw, "1000000")

    def test_high_scale_conversion_uses_exact_decimal_arithmetic(self):
        record = self.record(meta={"delivered_amount": {
            "currency": "USD", "issuer": ISSUER, "value": "1.234567890123456"}})
        event = self.normalize(record, decimals=18)
        self.assertEqual(event.amount_raw, "1234567890123456000")

    def test_raw_provider_hash_or_ledger_index_must_match_typed_record(self):
        record = self.record()
        record.raw["hash"] = "C" * 64
        with self.assertRaisesRegex(ValueError, "do not match"):
            self.normalize(record)
        record = self.record()
        record.raw["ledger_index"] = 499
        with self.assertRaisesRegex(ValueError, "do not match"):
            self.normalize(record)

    def test_malformed_transaction_identity_and_ledger_are_rejected(self):
        with self.assertRaises(ValueError):
            self.normalize(self.record(), canonical_ledger_hash="bad")
        bad = self.record()
        bad = XrplAccountTransaction("bad", 500, bad.close_time_iso, bad.transaction, bad.metadata, bad.raw)
        with self.assertRaises(ValueError):
            self.normalize(bad)


if __name__ == "__main__":
    unittest.main()
