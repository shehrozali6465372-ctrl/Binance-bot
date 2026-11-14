import unittest
from datetime import datetime, timezone

from layer1.content_verification import ContentVerificationEngine
from layer1.evidence_verification import Claim, EvidenceRecord, EvidenceVerificationEngine


def now():
    return datetime.now(timezone.utc).isoformat()


class ContentVerificationEngineTests(unittest.TestCase):
    def setUp(self):
        self.asset_id = "coingecko:abc"
        timestamp = now()
        evidence = EvidenceRecord(
            source_id="market-source-1", source_family="coingecko",
            source_kind="PRIMARY", publisher="CoinGecko", subject=self.asset_id,
            claim_key="market.price", value=1.25, published_at=timestamp,
            observed_at=timestamp, asset_id=self.asset_id, unit="USD",
            is_primary=True, source_status="ACCEPTED",
        )
        claim = Claim(
            text="ABC market price is 1.25 USD", subject=self.asset_id,
            claim_key="market.price", value=1.25, observed_at=now(),
            evidence_ids=(evidence.evidence_id,), asset_id=self.asset_id,
            unit="USD", claim_type="CONFIRMED_FACT",
        )
        self.registry = EvidenceVerificationEngine().verify((claim,), (evidence,))
        self.engine = ContentVerificationEngine()

    def test_verified_fact_and_exact_ticker_pass(self):
        result = self.engine.validate(
            "ABC ($ABC) is trading at $1.25. #ABC",
            registry=self.registry, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "PASS")
        self.assertEqual(len(result.approved_claim_ids), 1)

    def test_wrong_or_multiple_cashtags_fail(self):
        result = self.engine.validate(
            "$ABC and $XYZ are both discussed. #ABC",
            registry=self.registry, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertIn("CASHTAG_ASSET_IDENTITY_MISMATCH", result.reasons)

    def test_direct_trade_instruction_and_guarantee_fail(self):
        result = self.engine.validate(
            "You should buy now. $ABC guaranteed profit. #ABC",
            registry=self.registry, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertIn("PROHIBITED_TRADE_INSTRUCTION_OR_GUARANTEE", result.reasons)

    def test_numeric_guard_failure_blocks(self):
        result = self.engine.validate(
            "$ABC market update. #ABC",
            registry=self.registry, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: False,
        )
        self.assertIn("NUMERIC_CLAIM_GUARD_FAILED", result.reasons)

    def test_unresolved_claim_for_same_asset_blocks(self):
        unresolved = Claim(
            text="An unsupported listing date", subject=self.asset_id,
            claim_key="announcement.date", value="2026-11-15",
            observed_at=now(), evidence_ids=(), asset_id=self.asset_id,
        )
        claims = self.registry.claims + (unresolved,)
        evidence = self.registry.evidence_records
        registry = EvidenceVerificationEngine().verify(claims, evidence)
        result = self.engine.validate(
            "$ABC update. #ABC", registry=registry, symbol="ABC",
            asset_id=self.asset_id, numeric_validator=lambda _: True,
        )
        self.assertIn("UNRESOLVED_ASSET_CLAIMS_REMAIN", result.reasons)

    def test_other_asset_unresolved_claim_does_not_poison_selected_asset(self):
        other = Claim(
            text="Unsupported other asset statement", subject="coingecko:xyz",
            claim_key="announcement.date", value="2026-11-15",
            observed_at=now(), evidence_ids=(), asset_id="coingecko:xyz",
        )
        registry = EvidenceVerificationEngine().verify(
            self.registry.claims + (other,), self.registry.evidence_records,
        )
        result = self.engine.validate(
            "$ABC update. #ABC", registry=registry, symbol="ABC",
            asset_id=self.asset_id, numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "PASS")


if __name__ == "__main__":
    unittest.main()
