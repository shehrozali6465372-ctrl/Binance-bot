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
            text="$ABC market price is 1.25 USD", subject=self.asset_id,
            claim_key="market.price", value=1.25, observed_at=now(),
            evidence_ids=(evidence.evidence_id,), asset_id=self.asset_id,
            unit="USD", claim_type="CONFIRMED_FACT",
        )
        self.registry = EvidenceVerificationEngine().verify((claim,), (evidence,))
        self.engine = ContentVerificationEngine()

    def test_verified_fact_and_exact_ticker_pass(self):
        result = self.engine.validate(
            f"[[CLAIM:{self.registry.claims[0].claim_id}]]{self.registry.claims[0].text}.\n#ABC #Write2Earn",
            registry=self.registry, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.approved_claim_ids, (self.registry.claims[0].claim_id,))
        self.assertNotIn("[[CLAIM:", result.clean_content)
        self.assertIn(self.registry.claims[0].text, result.clean_content)

    def test_factual_sentence_without_claim_attribution_is_rejected(self):
        result = self.engine.validate(
            "$ABC market price is 1.25 USD. #ABC #Write2Earn",
            registry=self.registry, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("FACTUAL_SENTENCE_MISSING_CLAIM_ATTRIBUTION", result.reasons)
        self.assertEqual(result.approved_claim_ids, ())

    def test_generated_post_cannot_publish_a_causal_claim_with_only_market_field_evidence(self):
        evidence = self.registry.evidence_records[0]
        causal_claim = Claim(
            text="$ABC market price is 1.25 USD because Binance listed ABC",
            subject=self.asset_id, asset_id=self.asset_id,
            claim_key="market.price", value=1.25, unit="USD", timeframe="spot",
            observed_at=now(), evidence_ids=(evidence.evidence_id,), max_age_seconds=3600,
        )
        registry = EvidenceVerificationEngine().verify((causal_claim,), (evidence,))
        result = self.engine.validate(
            f"[[CLAIM:{causal_claim.claim_id}]]{causal_claim.text}. #ABC #Write2Earn",
            registry=registry, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("UNKNOWN_OR_UNVERIFIED_CLAIM_REFERENCE", result.reasons)
        self.assertIn("UNRESOLVED_ASSET_CLAIMS_REMAIN", result.reasons)

    def test_claim_marker_does_not_authorize_rewritten_sentence(self):
        claim = self.registry.claims[0]
        result = self.engine.validate(
            f"[[CLAIM:{claim.claim_id}]]$ABC price will surge after the announcement. #ABC",
            registry=self.registry, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("SENTENCE_DOES_NOT_MATCH_REFERENCED_CLAIM", result.reasons)
        self.assertEqual(result.approved_claim_ids, ())

    def test_verified_claim_from_another_asset_cannot_be_referenced(self):
        timestamp = now()
        foreign_evidence = EvidenceRecord(
            source_id="foreign-market-1", source_family="coingecko",
            source_kind="PRIMARY", publisher="CoinGecko", subject="coingecko:xyz",
            claim_key="market.price", value=2.0, published_at=timestamp,
            observed_at=timestamp, asset_id="coingecko:xyz", unit="USD",
            is_primary=True, source_status="ACCEPTED",
        )
        foreign_claim = Claim(
            text="$ABC market price is 2.00 USD", subject="coingecko:xyz",
            claim_key="market.price", value=2.0, observed_at=timestamp,
            evidence_ids=(foreign_evidence.evidence_id,), asset_id="coingecko:xyz",
            unit="USD", claim_type="CONFIRMED_FACT",
        )
        registry = EvidenceVerificationEngine().verify(
            self.registry.claims + (foreign_claim,),
            self.registry.evidence_records + (foreign_evidence,),
        )
        result = self.engine.validate(
            f"[[CLAIM:{foreign_claim.claim_id}]]{foreign_claim.text}. #ABC",
            registry=registry, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("UNKNOWN_OR_UNVERIFIED_CLAIM_REFERENCE", result.reasons)

    def test_unknown_claim_id_cannot_attribute_a_sentence(self):
        result = self.engine.validate(
            f"[[CLAIM:{'0' * 64}]]{self.registry.claims[0].text}. #ABC",
            registry=self.registry, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("UNKNOWN_OR_UNVERIFIED_CLAIM_REFERENCE", result.reasons)

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
            f"[[CLAIM:{self.registry.claims[0].claim_id}]]{self.registry.claims[0].text}. #ABC",
            registry=registry, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
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
            f"[[CLAIM:{self.registry.claims[0].claim_id}]]{self.registry.claims[0].text}. #ABC",
            registry=registry, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "PASS")


if __name__ == "__main__":
    unittest.main()
