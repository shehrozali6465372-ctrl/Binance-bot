import unittest
from datetime import datetime, timezone

from layer1.content_verification import ContentVerificationEngine
from layer1.evidence_verification import Claim, EvidenceRecord, EvidenceVerificationEngine
from layer1.editorial_strategy import EditorialBrief, editorial_brief_payload_hash


from tests.evidence_fixtures import trusted_evidence_record
def now():
    return datetime.now(timezone.utc).isoformat()


class ContentVerificationEngineTests(unittest.TestCase):
    def setUp(self):
        self.asset_id = "coingecko:abc"
        timestamp = now()
        evidence = trusted_evidence_record(
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
        self.brief = self.make_brief((claim.claim_id,))

    def make_brief(self, approved_claim_ids, prohibited_claims=(), event_id="event:abc",
                   research_package_id="research:abc:1"):
        payload = {
            "event_id": event_id, "angle_id": "angle:abc",
            "research_package_id": research_package_id,
            "research_question": "Explain the verified ABC evidence",
            "format": "MARKET_MOVEMENT_EXPLAINER",
            "angle": "Explain only the approved evidence",
            "audience": "Binance Square readers",
            "tone": "analytical and cautious",
            "min_words": 20, "max_words": 120,
            "outline": ("State the verified evidence", "Explain uncertainty"),
            "approved_claim_ids": tuple(sorted(approved_claim_ids)),
            "prohibited_claims": tuple(sorted(prohibited_claims)),
            "uncertainty_notes": (),
            "status": "READY", "policy_version": "test-policy-v1",
        }
        brief_hash = editorial_brief_payload_hash(payload)
        return EditorialBrief(
            event_id=event_id, angle_id=payload["angle_id"],
            brief_id=brief_hash, version=1,
            research_package_id=research_package_id,
            research_question=payload["research_question"],
            format=payload["format"], angle=payload["angle"],
            audience=payload["audience"], tone=payload["tone"],
            min_words=payload["min_words"], max_words=payload["max_words"],
            outline=payload["outline"], approved_claim_ids=payload["approved_claim_ids"],
            prohibited_claims=payload["prohibited_claims"],
            uncertainty_notes=payload["uncertainty_notes"],
            status="READY", brief_hash=brief_hash, policy_version=payload["policy_version"],
        )

    def test_verified_fact_and_exact_ticker_pass(self):
        result = self.engine.validate(
            f"[[CLAIM:{self.registry.claims[0].claim_id}]]{self.registry.claims[0].text}.\n#ABC #Write2Earn",
            registry=self.registry, editorial_brief=self.brief, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.approved_claim_ids, (self.registry.claims[0].claim_id,))
        self.assertNotIn("[[CLAIM:", result.clean_content)
        self.assertIn(self.registry.claims[0].text, result.clean_content)

    def _source_assertion_registry(self):
        timestamp = now()
        evidence = trusted_evidence_record(
            source_id="binance-announcement-1", source_family="binance",
            source_kind="PRIMARY", publisher="Binance", subject=self.asset_id,
            claim_key="announcement.body",
            value="$ABC will list at 12:00 UTC",
            published_at=timestamp, observed_at=timestamp,
            asset_id=self.asset_id, is_primary=True, source_status="ACCEPTED",
        )
        claim = Claim(
            text="Detail: $ABC will list at 12:00 UTC",
            subject=self.asset_id, claim_key="announcement.body",
            value="$ABC will list at 12:00 UTC", observed_at=timestamp,
            evidence_ids=(evidence.evidence_id,), asset_id=self.asset_id,
            claim_type="SOURCE_ASSERTION",
        )
        registry = EvidenceVerificationEngine().verify((claim,), (evidence,))
        return registry, claim

    def test_source_assertion_without_named_publisher_attribution_is_rejected(self):
        registry, claim = self._source_assertion_registry()
        brief = self.make_brief((claim.claim_id,))
        result = self.engine.validate(
            f"[[CLAIM:{claim.claim_id}]]{claim.text}. #ABC",
            registry=registry, editorial_brief=brief, symbol="ABC",
            asset_id=self.asset_id, numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("SOURCE_ASSERTION_PUBLISHER_ATTRIBUTION_MISSING", result.reasons)

    def test_source_assertion_with_exact_supporting_publisher_attribution_passes(self):
        registry, claim = self._source_assertion_registry()
        brief = self.make_brief((claim.claim_id,))
        result = self.engine.validate(
            f"[[CLAIM:{claim.claim_id}]]According to Binance: {claim.text}. #ABC",
            registry=registry, editorial_brief=brief, symbol="ABC",
            asset_id=self.asset_id, numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.approved_claim_ids, (claim.claim_id,))

    def test_source_assertion_with_wrong_publisher_attribution_is_rejected(self):
        registry, claim = self._source_assertion_registry()
        brief = self.make_brief((claim.claim_id,))
        result = self.engine.validate(
            f"[[CLAIM:{claim.claim_id}]]According to CoinGecko: {claim.text}. #ABC",
            registry=registry, editorial_brief=brief, symbol="ABC",
            asset_id=self.asset_id, numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("SOURCE_ASSERTION_PUBLISHER_ATTRIBUTION_MISSING", result.reasons)

    def test_verified_claim_outside_editorial_allowlist_is_rejected(self):
        timestamp = now()
        extra_evidence = trusted_evidence_record(
            source_id="market-change-unapproved", source_family="coingecko",
            source_kind="PRIMARY", publisher="CoinGecko", subject=self.asset_id,
            claim_key="market.change_24h", value=2.0, published_at=timestamp,
            observed_at=timestamp, asset_id=self.asset_id, unit="percent",
            timeframe="24h", is_primary=True, source_status="ACCEPTED",
        )
        extra_claim = Claim(
            text="$ABC 24h change is +2.0%", subject=self.asset_id,
            claim_key="market.change_24h", value=2.0, observed_at=timestamp,
            evidence_ids=(extra_evidence.evidence_id,), asset_id=self.asset_id,
            unit="percent", timeframe="24h", claim_type="CONFIRMED_FACT",
        )
        registry = EvidenceVerificationEngine().verify(
            self.registry.claims + (extra_claim,),
            self.registry.evidence_records + (extra_evidence,),
        )
        result = self.engine.validate(
            f"[[CLAIM:{extra_claim.claim_id}]]{extra_claim.text}. #ABC",
            registry=registry, editorial_brief=self.brief, symbol="ABC",
            asset_id=self.asset_id, numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("CLAIM_NOT_APPROVED_BY_EDITORIAL_BRIEF", result.reasons)
        self.assertNotIn(extra_claim.claim_id, result.approved_claim_ids)

    def test_tampered_editorial_brief_is_rejected_before_claim_validation(self):
        from dataclasses import replace

        tampered = replace(self.brief, angle="unapproved angle")
        claim = self.registry.claims[0]
        with self.assertRaisesRegex(ValueError, "intact READY editorial brief"):
            self.engine.validate(
                f"[[CLAIM:{claim.claim_id}]]{claim.text}. #ABC",
                registry=self.registry, editorial_brief=tampered, symbol="ABC",
                asset_id=self.asset_id, numeric_validator=lambda _: True,
            )

    def test_factual_sentence_without_claim_attribution_is_rejected(self):
        result = self.engine.validate(
            "$ABC market price is 1.25 USD. #ABC #Write2Earn",
            registry=self.registry, editorial_brief=self.brief, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("FACTUAL_SENTENCE_MISSING_CLAIM_ATTRIBUTION", result.reasons)
        self.assertEqual(result.approved_claim_ids, ())

    def test_each_generated_post_sentence_maps_to_its_own_verified_claim(self):
        timestamp = now()
        price_claim = self.registry.claims[0]
        change_evidence = trusted_evidence_record(
            source_id="market-change-1", source_family="coingecko",
            source_kind="PRIMARY", publisher="CoinGecko", subject=self.asset_id,
            claim_key="market.change_24h", value=2.0, published_at=timestamp,
            observed_at=timestamp, asset_id=self.asset_id, unit="percent",
            timeframe="24h", is_primary=True, source_status="ACCEPTED",
        )
        change_claim = Claim(
            text="$ABC 24h change is +2.0%", subject=self.asset_id,
            claim_key="market.change_24h", value=2.0, observed_at=timestamp,
            evidence_ids=(change_evidence.evidence_id,), asset_id=self.asset_id,
            unit="percent", timeframe="24h", claim_type="CONFIRMED_FACT",
        )
        registry = EvidenceVerificationEngine().verify(
            (price_claim, change_claim),
            self.registry.evidence_records + (change_evidence,),
        )
        result = self.engine.validate(
            f"[[CLAIM:{price_claim.claim_id}]]{price_claim.text}. "
            f"[[CLAIM:{change_claim.claim_id}]]{change_claim.text}. #ABC #Write2Earn",
            registry=registry,
            editorial_brief=self.make_brief((price_claim.claim_id, change_claim.claim_id)),
            symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "PASS")
        self.assertEqual(
            result.approved_claim_ids,
            tuple(sorted((price_claim.claim_id, change_claim.claim_id))),
        )

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
            registry=registry, editorial_brief=self.brief, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("UNKNOWN_OR_UNVERIFIED_CLAIM_REFERENCE", result.reasons)
        self.assertIn("UNRESOLVED_ASSET_CLAIMS_REMAIN", result.reasons)

    def test_claim_marker_does_not_authorize_rewritten_sentence(self):
        claim = self.registry.claims[0]
        result = self.engine.validate(
            f"[[CLAIM:{claim.claim_id}]]$ABC price will surge after the announcement. #ABC",
            registry=self.registry, editorial_brief=self.brief, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("SENTENCE_DOES_NOT_MATCH_REFERENCED_CLAIM", result.reasons)
        self.assertEqual(result.approved_claim_ids, ())

    def test_verified_claim_from_another_asset_cannot_be_referenced(self):
        timestamp = now()
        foreign_evidence = trusted_evidence_record(
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
            registry=registry, editorial_brief=self.brief, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("UNKNOWN_OR_UNVERIFIED_CLAIM_REFERENCE", result.reasons)

    def test_unknown_claim_id_cannot_attribute_a_sentence(self):
        result = self.engine.validate(
            f"[[CLAIM:{'0' * 64}]]{self.registry.claims[0].text}. #ABC",
            registry=self.registry, editorial_brief=self.brief, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("UNKNOWN_OR_UNVERIFIED_CLAIM_REFERENCE", result.reasons)

    def test_digit_leading_binance_ticker_cashtag_is_recognized(self):
        asset_id = "coingecko:1inch"
        timestamp = now()
        evidence = trusted_evidence_record(
            source_id="oneinch-market-source", source_family="coingecko",
            source_kind="PRIMARY", publisher="CoinGecko", subject=asset_id,
            claim_key="market.price", value=1.25, published_at=timestamp,
            observed_at=timestamp, asset_id=asset_id, unit="USD",
            is_primary=True, source_status="ACCEPTED",
        )
        claim = Claim(
            text="$1INCH market price is 1.25 USD", subject=asset_id,
            claim_key="market.price", value=1.25, observed_at=timestamp,
            evidence_ids=(evidence.evidence_id,), asset_id=asset_id,
            unit="USD", claim_type="CONFIRMED_FACT",
        )
        registry = EvidenceVerificationEngine().verify((claim,), (evidence,))
        result = self.engine.validate(
            f"[[CLAIM:{claim.claim_id}]]{claim.text}. #1INCH #Write2Earn",
            registry=registry, editorial_brief=self.make_brief((claim.claim_id,)),
            symbol="1INCH", asset_id=asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.approved_claim_ids, (claim.claim_id,))

    def test_wrong_or_multiple_cashtags_fail(self):
        result = self.engine.validate(
            "$ABC and $XYZ are both discussed. #ABC",
            registry=self.registry, editorial_brief=self.brief, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertIn("CASHTAG_ASSET_IDENTITY_MISMATCH", result.reasons)

    def test_direct_trade_instruction_and_guarantee_fail(self):
        result = self.engine.validate(
            "You should buy now. $ABC guaranteed profit. #ABC",
            registry=self.registry, editorial_brief=self.brief, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertIn("PROHIBITED_TRADE_INSTRUCTION_OR_GUARANTEE", result.reasons)

    def test_numeric_guard_failure_blocks(self):
        result = self.engine.validate(
            "$ABC market update. #ABC",
            registry=self.registry, editorial_brief=self.brief, symbol="ABC", asset_id=self.asset_id,
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
            registry=registry, editorial_brief=self.brief, symbol="ABC", asset_id=self.asset_id,
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
            registry=registry, editorial_brief=self.brief, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "PASS")


    def test_successful_content_gate_exposes_verified_evidence_status_for_publication(self):
        claim = self.registry.claims[0]
        result = self.engine.validate(
            f"[[CLAIM:{claim.claim_id}]]{claim.text}. #ABC #Write2Earn",
            registry=self.registry, editorial_brief=self.brief, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.evidence_status, "VERIFIED")

    def test_rejected_content_gate_never_exposes_verified_evidence_status(self):
        result = self.engine.validate(
            "$ABC market price is 1.25 USD. #ABC #Write2Earn",
            registry=self.registry, editorial_brief=self.brief, symbol="ABC", asset_id=self.asset_id,
            numeric_validator=lambda _: True,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertEqual(result.evidence_status, "UNVERIFIED")


    def test_content_gate_rejects_manually_constructed_claim_registry(self):
        from layer1.evidence_verification import ClaimRegistry

        manual_registry = ClaimRegistry(
            claims=self.registry.claims,
            evidence_records=self.registry.evidence_records,
            results=self.registry.results,
            unresolved_issues=self.registry.unresolved_issues,
        )
        claim = self.registry.claims[0]
        with self.assertRaisesRegex(ValueError, "verifier-issued"):
            self.engine.validate(
                f"[[CLAIM:{claim.claim_id}]]{claim.text}. #ABC #Write2Earn",
                registry=manual_registry, editorial_brief=self.brief,
                symbol="ABC", asset_id=self.asset_id, numeric_validator=lambda _: True,
            )

    def test_content_gate_rejects_registry_mutated_after_verification(self):
        self.registry.results[0].source_lineage["tampered-source"] = "untrusted"
        claim = self.registry.claims[0]
        with self.assertRaisesRegex(ValueError, "changed after verification"):
            self.engine.validate(
                f"[[CLAIM:{claim.claim_id}]]{claim.text}. #ABC #Write2Earn",
                registry=self.registry, editorial_brief=self.brief,
                symbol="ABC", asset_id=self.asset_id, numeric_validator=lambda _: True,
            )


if __name__ == "__main__":
    unittest.main()
