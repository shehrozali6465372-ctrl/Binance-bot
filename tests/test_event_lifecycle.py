import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from layer1.event_lifecycle import EventLifecycleStore
from layer1.foundation import AnnouncementEvidence, Layer1Store


def iso(delta=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta)).isoformat()


def evidence(revision="a", published=-300, updated=-200):
    return AnnouncementEvidence(
        source_id="stable-binance-article-123",
        source_url="https://www.binance.com/en/support/announcement/stable-binance-article-123",
        publisher="Binance",
        event_type="listing",
        title="Binance announces ABC Spot listing",
        published_at=iso(published),
        observed_at=iso(),
        asset_ids=("coingecko:abc",),
        content_hash=revision * 64,
        updated_at=iso(updated),
    )


class EventLifecycleStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "layer1.db")
        self.db = Layer1Store(self.path)
        self.store = EventLifecycleStore(self.db)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_first_observation_is_discovered_then_under_verification(self):
        item = evidence()
        record = self.store.observe(item, verification_state="UNVERIFIED")
        self.assertEqual(record.state, "UNDER_VERIFICATION")
        self.assertEqual(record.first_published_at, item.published_at)
        self.assertEqual(record.last_updated_at, item.updated_at)
        self.assertEqual([item["to_state"] for item in self.store.history(record.event_id)],
                         ["DISCOVERED", "UNDER_VERIFICATION"])

    def test_verified_evidence_confirms_and_duplicate_does_not_add_transition(self):
        item = evidence()
        first = self.store.observe(item, verification_state="UNVERIFIED")
        confirmed = self.store.observe(item, verification_state="VERIFIED")
        again = self.store.observe(item, verification_state="VERIFIED")
        self.assertEqual(confirmed.event_id, first.event_id)
        self.assertEqual(again.state, "CONFIRMED")
        self.assertEqual([row["to_state"] for row in self.store.history(first.event_id)],
                         ["DISCOVERED", "UNDER_VERIFICATION", "CONFIRMED"])

    def test_material_new_revision_moves_confirmed_event_to_developing(self):
        self.store.observe(evidence("a"), verification_state="VERIFIED")
        updated = evidence("b", published=-300, updated=-60)
        record = self.store.observe(
            updated, verification_state="CORROBORATED", materially_new=True,
        )
        self.assertEqual(record.state, "DEVELOPING")
        self.assertEqual(len(self.store.history(record.event_id)), 4)

    def test_non_material_revision_does_not_mark_event_developing(self):
        first = self.store.observe(evidence("a"), verification_state="VERIFIED")
        record = self.store.observe(
            evidence("b", published=-300, updated=-60),
            verification_state="VERIFIED", materially_new=False,
        )
        self.assertEqual(record.event_id, first.event_id)
        self.assertEqual(record.state, "CONFIRMED")

    def test_contradicted_event_is_disputed_and_only_material_new_evidence_reopens(self):
        first = self.store.observe(evidence("a"), verification_state="CONTRADICTED")
        self.assertEqual(first.state, "DISPUTED")
        duplicate = self.store.observe(evidence("a"), verification_state="VERIFIED")
        self.assertEqual(duplicate.state, "DISPUTED")
        reopened = self.store.observe(
            evidence("b", published=-300, updated=-30),
            verification_state="VERIFIED", materially_new=True,
        )
        self.assertEqual(reopened.state, "CONFIRMED")
        self.assertEqual(
            [row["to_state"] for row in self.store.history(first.event_id)],
            ["DISCOVERED", "UNDER_VERIFICATION", "DISPUTED",
             "UNDER_VERIFICATION", "CONFIRMED"],
        )

    def test_resolution_requires_explicit_verified_evidence(self):
        with self.assertRaisesRegex(ValueError, "resolution evidence"):
            self.store.observe(
                evidence(), verification_state="VERIFIED", resolved=True,
            )
        record = self.store.observe(
            evidence(), verification_state="VERIFIED", resolved=True,
            resolution_evidence_id="evidence:resolution-1",
        )
        self.assertEqual(record.state, "RESOLVED")

    def test_disputed_event_can_only_resolve_with_explicit_verified_resolution_evidence(self):
        disputed = self.store.observe(evidence("a"), verification_state="CONTRADICTED")
        with self.assertRaisesRegex(ValueError, "resolution evidence"):
            self.store.observe(
                evidence("b"), verification_state="VERIFIED", resolved=True,
            )
        resolved = self.store.observe(
            evidence("c"), verification_state="VERIFIED", resolved=True,
            resolution_evidence_id="evidence:independent-resolution",
        )
        self.assertEqual(resolved.event_id, disputed.event_id)
        self.assertEqual(resolved.state, "RESOLVED")

    def test_withdrawal_requires_explicit_verified_evidence(self):
        with self.assertRaisesRegex(ValueError, "withdrawal evidence"):
            self.store.observe(evidence(), verification_state="VERIFIED", withdrawn=True)
        record = self.store.observe(
            evidence(), verification_state="VERIFIED", withdrawn=True,
            resolution_evidence_id="evidence:withdrawal-1",
        )
        self.assertEqual(record.state, "WITHDRAWN")

    def test_stale_event_is_explicitly_marked_and_cannot_be_reopened_by_old_source(self):
        old = evidence()
        record = self.store.observe(old, verification_state="VERIFIED")
        stale = self.store.mark_stale(record.event_id, now=iso(1000), max_age_seconds=100)
        self.assertEqual(stale.state, "STALE")
        repeated = self.store.observe(old, verification_state="VERIFIED")
        self.assertEqual(repeated.state, "STALE")
        self.assertEqual(len(self.store.history(record.event_id)), 4)

    def test_sync_uses_claim_registry_and_splits_multi_asset_announcements(self):
        from layer1.evidence_verification import EvidenceVerificationEngine

        item = AnnouncementEvidence(
            source_id="stable-multi-asset-article",
            source_url="https://www.binance.com/en/support/announcement/stable-multi-asset-article",
            publisher="Binance", event_type="listing", title="ABC and XYZ Spot listing",
            published_at=iso(-120), observed_at=iso(), asset_ids=("coingecko:abc", "coingecko:xyz"),
            content_hash="c" * 64, updated_at=iso(-60),
        )
        engine = EvidenceVerificationEngine()
        source_evidence = engine.evidence_from_announcement(item)
        registry = engine.verify(engine._source_assertion_claims(source_evidence), source_evidence)
        records = self.store.sync_announcements([item], registry)
        self.assertEqual(len(records), 2)
        self.assertEqual({record.asset_id for record in records}, {"coingecko:abc", "coingecko:xyz"})
        self.assertEqual({record.state for record in records}, {"CONFIRMED"})

    def test_sync_stale_source_marks_event_stale(self):
        from layer1.evidence_verification import EvidenceVerificationEngine

        item = AnnouncementEvidence(
            source_id="stable-old-article",
            source_url="https://www.binance.com/en/support/announcement/stable-old-article",
            publisher="Binance", event_type="listing", title="ABC Spot listing",
            published_at=iso(-172800), observed_at=iso(), asset_ids=("coingecko:abc",),
            content_hash="d" * 64, updated_at=iso(-172800),
        )
        engine = EvidenceVerificationEngine()
        source_evidence = engine.evidence_from_announcement(item)
        registry = engine.verify(engine._source_assertion_claims(source_evidence), source_evidence)
        records = self.store.sync_announcements([item], registry)
        self.assertEqual(records[0].state, "STALE")

    def test_sync_unverified_announcement_does_not_confirm_event(self):
        from layer1.evidence_verification import EvidenceVerificationEngine

        item = evidence()
        engine = EvidenceVerificationEngine()
        registry = engine.verify((), engine.evidence_from_announcement(item))
        records = self.store.sync_announcements([item], registry)
        self.assertEqual(records[0].state, "UNDER_VERIFICATION")

    def test_restart_preserves_current_state_and_append_only_transition_history(self):
        record = self.store.observe(evidence(), verification_state="VERIFIED")
        self.db.close()
        self.db = Layer1Store(self.path)
        self.store = EventLifecycleStore(self.db)
        recovered = self.store.get(record.event_id)
        self.assertEqual(recovered.state, "CONFIRMED")
        self.assertEqual(len(self.store.history(record.event_id)), 3)

    def test_fingerprint_source_ids_do_not_get_false_revision_correlation(self):
        first = AnnouncementEvidence(
            source_id="1" * 64,
            source_url="https://www.binance.com/en/support/announcement",
            publisher="Binance", event_type="listing", title="ABC listing",
            published_at=iso(-300), observed_at=iso(), asset_ids=("coingecko:abc",),
            content_hash="a" * 64,
        )
        second = AnnouncementEvidence(
            source_id="2" * 64,
            source_url="https://www.binance.com/en/support/announcement",
            publisher="Binance", event_type="listing", title="ABC listing updated",
            published_at=iso(-300), observed_at=iso(), asset_ids=("coingecko:abc",),
            content_hash="b" * 64,
        )
        a = self.store.observe(first, verification_state="VERIFIED")
        b = self.store.observe(second, verification_state="VERIFIED")
        self.assertNotEqual(a.event_id, b.event_id)


if __name__ == "__main__":
    unittest.main()
