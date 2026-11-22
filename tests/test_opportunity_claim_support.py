from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import asdict

from layer1.evidence_verification import (
    Claim, EvidenceRecord, EvidenceVerificationEngine,
)


class FactorClaimSupportTests(unittest.TestCase):
    def setUp(self):
        self.asset = "coingecko:bitcoin"
        self.evidence = EvidenceRecord(
            source_id="official-listing:001", source_family="exchange-official",
            source_kind="PRIMARY", publisher="Example Exchange", subject=self.asset,
            claim_key="announcement.listing", value="listed",
            published_at="2026-11-21T10:00:00Z", observed_at="2026-11-21T10:01:00Z",
            asset_id=self.asset, content_hash="a" * 64,
            lineage_id="official-announcement:001", is_primary=True,
            source_status="ACCEPTED",
        )
        self.claim = Claim(
            text=f"Source assertion: {self.asset} announcement.listing = \"listed\"", subject=self.asset,
            claim_key="announcement.listing", value="listed",
            observed_at="2026-11-21T10:02:00Z", evidence_ids=(self.evidence.evidence_id,),
            asset_id=self.asset, claim_type="SOURCE_ASSERTION", impact="MEDIUM",
        )
        self.registry = EvidenceVerificationEngine().verify((self.claim,), (self.evidence,))
        self.payload = self.registry.to_dict()
        self.registry_id = hashlib.sha256(json.dumps(
            self.payload, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()

    def assess(self, factor_name="evidence_strength", refs=None, payload=None):
        from layer1.opportunity import validate_factor_claim_support
        return validate_factor_claim_support(
            factor_name=factor_name,
            claim_refs=[self.claim.claim_id],
            source_refs=[self.evidence.evidence_id] if refs is None else refs,
            registry_payload=self.payload if payload is None else payload,
            expected_asset_id=self.asset,
        )

    def test_accepts_claim_bound_to_same_asset_and_supporting_evidence(self):
        supported = self.assess()
        self.assertEqual(supported[0]["claim_id"], self.claim.claim_id)
        self.assertEqual(supported[0]["supporting_evidence_ids"], [self.evidence.evidence_id])

    def test_rejects_missing_claim_reference(self):
        from layer1.opportunity import validate_factor_claim_support
        with self.assertRaisesRegex(ValueError, "claim references are required"):
            validate_factor_claim_support(
                factor_name="evidence_strength", claim_refs=[],
                source_refs=[self.evidence.evidence_id], registry_payload=self.payload,
                expected_asset_id=self.asset,
            )

    def test_rejects_unverified_claim(self):
        payload = dict(self.payload)
        payload["results"] = [dict(self.payload["results"][0]) | {
            "state": "UNVERIFIED", "issues": ["fixture unresolved"],
        }]
        with self.assertRaisesRegex(ValueError, "not VERIFIED or CORROBORATED"):
            self.assess(payload=payload)

    def test_rejects_claim_without_source_reference_overlap(self):
        with self.assertRaisesRegex(ValueError, "does not support referenced factor evidence"):
            self.assess(refs=["f" * 64])

    def test_rejects_claim_for_another_asset(self):
        from dataclasses import replace
        payload = dict(self.payload)
        foreign = replace(self.claim, asset_id="coingecko:ethereum", subject="coingecko:ethereum")
        payload["claims"] = [asdict(foreign) | {"claim_id": foreign.claim_id}]
        payload["results"] = [dict(self.payload["results"][0]) | {"claim_id": foreign.claim_id}]
        from layer1.opportunity import validate_factor_claim_support
        with self.assertRaisesRegex(ValueError, "claim asset identity"):
            validate_factor_claim_support(
                factor_name="evidence_strength", claim_refs=[foreign.claim_id],
                source_refs=[self.evidence.evidence_id], registry_payload=payload,
                expected_asset_id=self.asset,
            )

    def test_rejects_inflated_independent_source_count(self):
        payload = dict(self.payload)
        payload["results"] = [dict(self.payload["results"][0]) | {
            "independent_source_count": 2,
        }]
        with self.assertRaisesRegex(ValueError, "independent-source count does not match"):
            self.assess(payload=payload)

    def test_rejects_contradicted_claim_even_if_supporting_ids_exist(self):
        payload = dict(self.payload)
        payload["results"] = [dict(self.payload["results"][0]) | {
            "state": "CONTRADICTED", "contradicting_evidence_ids": ["e" * 64],
        }]
        with self.assertRaisesRegex(ValueError, "not VERIFIED or CORROBORATED"):
            self.assess(payload=payload)

    def test_independence_groups_collapse_shared_family_lineage_and_payload(self):
        from layer1.opportunity import group_independent_evidence_records
        sibling = EvidenceRecord(
            source_id="syndicated-copy:002", source_family="exchange-official",
            source_kind="SECONDARY", publisher="Mirror", subject=self.asset,
            claim_key="announcement.listing", value="listed",
            published_at="2026-11-21T10:00:00Z", observed_at="2026-11-21T10:03:00Z",
            asset_id=self.asset, content_hash="b" * 64,
            lineage_id="mirror-copy:002", is_primary=False, source_status="ACCEPTED",
        )
        independent = EvidenceRecord(
            source_id="independent-source:003", source_family="independent-news",
            source_kind="SECONDARY", publisher="Independent News", subject=self.asset,
            claim_key="announcement.listing", value="listed",
            published_at="2026-11-21T10:00:00Z", observed_at="2026-11-21T10:04:00Z",
            asset_id=self.asset, content_hash="c" * 64,
            lineage_id="independent-report:003", is_primary=False, source_status="ACCEPTED",
        )
        groups = group_independent_evidence_records((self.evidence, sibling, independent))
        self.assertEqual(sorted(len(group) for group in groups), [1, 2])
        self.assertEqual({item.evidence_id for group in groups for item in group}, {
            self.evidence.evidence_id, sibling.evidence_id, independent.evidence_id,
        })

    def test_same_content_hash_collapses_even_across_different_source_families(self):
        from layer1.opportunity import group_independent_evidence_records
        copy_record = EvidenceRecord(
            source_id="republisher:004", source_family="different-family",
            source_kind="SECONDARY", publisher="Republisher", subject=self.asset,
            claim_key="announcement.listing", value="listed",
            published_at="2026-11-21T10:00:00Z", observed_at="2026-11-21T10:05:00Z",
            asset_id=self.asset, content_hash=self.evidence.content_hash,
            lineage_id="different-lineage", is_primary=False, source_status="ACCEPTED",
        )
        groups = group_independent_evidence_records((self.evidence, copy_record))
        self.assertEqual(len(groups), 1)


if __name__ == "__main__":
    unittest.main()
