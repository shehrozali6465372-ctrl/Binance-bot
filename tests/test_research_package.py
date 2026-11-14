import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from layer1.evidence_verification import Claim, EvidenceRecord, EvidenceVerificationEngine
from layer1.research_package import DeepResearchEngine, ResearchPackageStore


def iso(delta=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta)).isoformat()


class DeepResearchEngineTests(unittest.TestCase):
    def setUp(self):
        self.asset_id = "coingecko:abc"
        self.timestamp = iso(-5)
        self.market = EvidenceRecord(
            source_id="market:abc:1", source_family="coingecko",
            source_kind="MARKET", publisher="CoinGecko", subject=self.asset_id,
            claim_key="market.price", value=1.25, unit="USD",
            published_at=self.timestamp, observed_at=self.timestamp,
            asset_id=self.asset_id, is_primary=True, source_status="ACCEPTED",
        )
        self.primary = EvidenceRecord(
            source_id="announcement:abc:1", source_family="binance",
            source_kind="PRIMARY", publisher="Binance", subject=self.asset_id,
            claim_key="announcement.event_type", value="listing",
            published_at=self.timestamp, observed_at=self.timestamp,
            asset_id=self.asset_id, is_primary=True, source_status="ACCEPTED",
        )
        self.claims = (
            Claim(
                text="ABC market price is 1.25 USD", subject=self.asset_id,
                claim_key="market.price", value=1.25, unit="USD",
                observed_at=self.timestamp, evidence_ids=(self.market.evidence_id,),
                asset_id=self.asset_id,
            ),
            Claim(
                text="Binance announced a listing", subject=self.asset_id,
                claim_key="announcement.event_type", value="listing",
                observed_at=self.timestamp, evidence_ids=(self.primary.evidence_id,),
                asset_id=self.asset_id, claim_type="SOURCE_ASSERTION",
            ),
        )
        self.registry = EvidenceVerificationEngine().verify(
            self.claims, (self.market, self.primary),
        )
        self.engine = DeepResearchEngine()

    def build(self, **kwargs):
        args = {
            "asset_id": self.asset_id, "symbol": "ABC",
            "research_question": "What did Binance announce for ABC?",
            "cutoff_at": iso(), "registry": self.registry,
            "event_states": ("CONFIRMED",),
            "required_source_kinds": ("PRIMARY", "MARKET"),
        }
        args.update(kwargs)
        return self.engine.build(**args)

    def test_complete_package_separates_facts_and_tracks_sources(self):
        package = self.build()
        self.assertEqual(package.completeness, "READY")
        self.assertEqual(len(package.verified_facts), 2)
        self.assertEqual(package.source_coverage["MARKET"]["record_count"], 1)
        self.assertEqual(package.source_coverage["PRIMARY"]["record_count"], 1)
        self.assertIn("DATA CUTOFF:", package.render())
        self.assertIn("evidence_ids=", package.render())

    def test_missing_required_source_class_leads_to_research_more(self):
        package = self.build(required_source_kinds=("PRIMARY", "MARKET", "ONCHAIN"))
        self.assertEqual(package.completeness, "RESEARCH_MORE")
        self.assertIn("MISSING_REQUIRED_SOURCE_KINDS:ONCHAIN", package.gaps)

    def test_unresolved_factual_claim_leads_to_research_more(self):
        unresolved = Claim(
            text="Unverified partnership announcement date", subject=self.asset_id,
            claim_key="announcement.date", value="2026-11-14",
            observed_at=iso(), evidence_ids=(), asset_id=self.asset_id,
        )
        registry = EvidenceVerificationEngine().verify(
            self.registry.claims + (unresolved,), self.registry.evidence_records,
        )
        package = self.build(registry=registry)
        self.assertEqual(package.completeness, "RESEARCH_MORE")
        self.assertIn("UNRESOLVED_FACTUAL_CLAIMS:1", package.gaps)

    def test_stale_event_defers_and_withdrawn_event_rejects(self):
        stale = self.build(event_states=("STALE",))
        withdrawn = self.build(event_states=("WITHDRAWN",))
        self.assertEqual(stale.completeness, "DEFER")
        self.assertEqual(withdrawn.completeness, "REJECT")

    def test_evidence_after_cutoff_is_not_counted(self):
        future = EvidenceRecord(
            source_id="future-market", source_family="coingecko",
            source_kind="MARKET", publisher="CoinGecko", subject=self.asset_id,
            claim_key="market.future", value=2.0, published_at=iso(300),
            observed_at=iso(300), asset_id=self.asset_id, is_primary=True,
            source_status="ACCEPTED",
        )
        registry = EvidenceVerificationEngine().verify(
            self.registry.claims, self.registry.evidence_records + (future,),
        )
        package = self.build(registry=registry, cutoff_at=iso())
        self.assertEqual(package.source_coverage["MARKET"]["record_count"], 1)
        self.assertNotIn(future.evidence_id, package.source_coverage["MARKET"]["evidence_ids"])

    def test_package_versions_are_append_only_and_idempotent(self):
        conn = sqlite3.connect(":memory:")
        try:
            store = ResearchPackageStore(conn)
            original_package = self.build()
            first = store.save(original_package)
            duplicate = store.save(original_package)
            second = store.save(self.build(cutoff_at=iso(1)))
            self.assertEqual(first.version, 1)
            self.assertEqual(duplicate.version, 1)
            self.assertEqual(first.package_id, duplicate.package_id)
            self.assertEqual(second.version, 2)
            self.assertEqual(store.load_latest(first.research_key)["version"], 2)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM layer1_research_package_versions"
            ).fetchone()[0], 2)
        finally:
            conn.close()

    def test_generic_question_and_noncanonical_identity_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "research question"):
            self.build(research_question=" ")
        with self.assertRaisesRegex(ValueError, "canonical"):
            self.build(asset_id="ABC")


if __name__ == "__main__":
    unittest.main()
