import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from layer1.event_lifecycle import EventLifecycleStore
from layer1.foundation import AnnouncementEvidence, Layer1Store
from tests.event_lifecycle_fixtures import test_receipted_announcement_registry


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

    def observe_verified(self, announcement):
        registry = test_receipted_announcement_registry(announcement)
        records = self.store.sync_announcements([announcement], registry)
        if len(records) != 1:
            raise AssertionError("single-asset verified test observation must produce exactly one record")
        return records[0]

    def test_event_lifecycle_store_can_own_a_separate_sqlite_connection(self):
        import sqlite3
        connection = sqlite3.connect(":memory:")
        try:
            store = EventLifecycleStore(connection)
            self.assertIs(store.conn, connection)
        finally:
            connection.close()

    def test_exact_source_lookup_does_not_confuse_two_events_for_same_asset(self):
        from dataclasses import replace

        first_evidence = evidence("a")
        second_evidence = replace(
            evidence("b", published=-120, updated=-60),
            source_id="stable-binance-article-456",
            source_url="https://www.binance.com/en/support/announcement/stable-binance-article-456",
            title="Binance announces ABC Launchpool",
            event_type="launch",
        )
        first = self.observe_verified(first_evidence)
        second = self.store.observe(second_evidence, verification_state="UNVERIFIED")

        self.assertEqual(first.asset_id, second.asset_id)
        self.assertNotEqual(first.event_id, second.event_id)
        self.assertEqual(self.store.latest_for_asset("coingecko:abc"), second)
        self.assertEqual(self.store.get_for_source("coingecko:abc", first.source_id), first)
        self.assertEqual(self.store.get_for_source("coingecko:abc", second.source_id), second)
        indexed = self.store.index_by_asset_source([first, second])
        self.assertEqual(
            indexed["coingecko:abc"][first.source_id][first.event_type]["event_id"],
            first.event_id,
        )
        self.assertEqual(
            indexed["coingecko:abc"][second.source_id][second.event_type]["event_id"],
            second.event_id,
        )

    def test_full_announcement_body_is_retained_in_revision_history(self):
        import json
        from dataclasses import replace

        item = replace(evidence(), body="Full source article body with exact terms and conditions.")
        record = self.store.observe(item, verification_state="UNVERIFIED")
        row = self.db.conn.execute(
            "SELECT payload_json FROM layer1_event_revisions WHERE event_id=?",
            (record.event_id,),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(json.loads(row[0])["body"], item.body)

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
        confirmed = self.observe_verified(item)
        again = self.observe_verified(item)
        self.assertEqual(confirmed.event_id, first.event_id)
        self.assertEqual(again.state, "CONFIRMED")
        self.assertEqual([row["to_state"] for row in self.store.history(first.event_id)],
                         ["DISCOVERED", "UNDER_VERIFICATION", "CONFIRMED"])

    def test_material_new_revision_moves_confirmed_event_to_developing(self):
        self.observe_verified(evidence("a"))
        from dataclasses import replace
        updated = replace(
            evidence("b", published=-300, updated=-60),
            title="Binance updates ABC Spot listing schedule",
            body="Trading will begin at 09:00 UTC instead of 08:00 UTC.",
        )
        record = self.observe_verified(updated)
        self.assertEqual(record.state, "DEVELOPING")
        self.assertEqual(len(self.store.history(record.event_id)), 4)

    def test_non_material_revision_does_not_mark_event_developing(self):
        first = self.observe_verified(evidence("a"))
        record = self.observe_verified(evidence("b", published=-300, updated=-60))
        self.assertEqual(record.event_id, first.event_id)
        self.assertEqual(record.state, "CONFIRMED")

    def test_contradicted_event_is_disputed_and_only_material_new_evidence_reopens(self):
        first = self.store.observe(evidence("a"), verification_state="CONTRADICTED")
        self.assertEqual(first.state, "DISPUTED")
        duplicate = self.observe_verified(evidence("a"))
        self.assertEqual(duplicate.state, "DISPUTED")
        from dataclasses import replace
        materially_new = replace(
            evidence("b", published=-300, updated=-30),
            title="Binance changes ABC listing schedule",
            body="Trading starts at 10:00 UTC.",
        )
        reopened = self.observe_verified(materially_new)
        self.assertEqual(reopened.state, "CONFIRMED")
        self.assertEqual(
            [row["to_state"] for row in self.store.history(first.event_id)],
            ["DISCOVERED", "UNDER_VERIFICATION", "DISPUTED",
             "UNDER_VERIFICATION", "CONFIRMED"],
        )

    def test_direct_api_rejects_caller_asserted_verified_state(self):
        with self.assertRaisesRegex(ValueError, "verifier-issued"):
            self.store.observe(evidence(), verification_state="VERIFIED")

    def test_sync_rejects_manually_reconstructed_claim_registry(self):
        from layer1.evidence_verification import ClaimRegistry

        item = evidence()
        trusted = test_receipted_announcement_registry(item)
        forged = ClaimRegistry(
            claims=trusted.claims, evidence_records=trusted.evidence_records,
            results=trusted.results, unresolved_issues=trusted.unresolved_issues,
        )
        with self.assertRaisesRegex(ValueError, "verifier-issued"):
            self.store.sync_announcements([item], forged)

    def test_sync_rejects_claim_registry_mutated_after_verification(self):
        from dataclasses import replace

        item = evidence()
        registry = test_receipted_announcement_registry(item)
        altered = (replace(registry.results[0], state="CONTRADICTED"),) + registry.results[1:]
        object.__setattr__(registry, "results", altered)
        with self.assertRaisesRegex(ValueError, "unchanged"):
            self.store.sync_announcements([item], registry)

    def test_direct_api_rejects_caller_asserted_resolution_and_withdrawal_evidence(self):
        for transition in (
            {"resolved": True, "resolution_evidence_id": "evidence:forged-resolution"},
            {"withdrawn": True, "resolution_evidence_id": "evidence:forged-withdrawal"},
        ):
            with self.subTest(transition=transition):
                with self.assertRaisesRegex(ValueError, "verifier-issued"):
                    self.store.observe(evidence(), verification_state="VERIFIED", **transition)

    def test_resolution_requires_verifier_issued_evidence_not_caller_string(self):
        with self.assertRaisesRegex(ValueError, "verifier-issued"):
            self.store.observe(evidence(), verification_state="VERIFIED", resolved=True)
        with self.assertRaisesRegex(ValueError, "verifier-issued"):
            self.store.observe(
                evidence(), verification_state="VERIFIED", resolved=True,
                resolution_evidence_id="evidence:resolution-1",
            )

    def test_disputed_event_cannot_be_resolved_by_caller_asserted_evidence_id(self):
        disputed = self.store.observe(evidence("a"), verification_state="CONTRADICTED")
        with self.assertRaisesRegex(ValueError, "verifier-issued"):
            self.store.observe(
                evidence("c"), verification_state="VERIFIED", resolved=True,
                resolution_evidence_id="evidence:independent-resolution",
            )
        current = self.store.get(disputed.event_id)
        self.assertEqual(current.state, "DISPUTED")

    def test_withdrawal_requires_verifier_issued_evidence_not_caller_string(self):
        with self.assertRaisesRegex(ValueError, "verifier-issued"):
            self.store.observe(evidence(), verification_state="VERIFIED", withdrawn=True)
        with self.assertRaisesRegex(ValueError, "verifier-issued"):
            self.store.observe(
                evidence(), verification_state="VERIFIED", withdrawn=True,
                resolution_evidence_id="evidence:withdrawal-1",
            )

    def test_stale_event_is_explicitly_marked_and_cannot_be_reopened_by_old_source(self):
        old = evidence()
        record = self.observe_verified(old)
        stale = self.store.mark_stale(record.event_id, now=iso(1000), max_age_seconds=100)
        self.assertEqual(stale.state, "STALE")
        repeated = self.observe_verified(old)
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
        registry = test_receipted_announcement_registry(item)
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
        registry = test_receipted_announcement_registry(item)
        records = self.store.sync_announcements([item], registry)
        self.assertEqual(records[0].state, "STALE")

    def test_sync_recognizes_verified_material_event_time_change(self):
        from layer1.evidence_verification import EvidenceVerificationEngine

        first = AnnouncementEvidence(
            source_id="stable-event-time-change",
            source_url="https://www.binance.com/en/support/announcement/stable-event-time-change",
            publisher="Binance", event_type="listing", title="ABC Spot listing",
            published_at=iso(-300), observed_at=iso(), asset_ids=("coingecko:abc",),
            content_hash="a" * 64, updated_at=iso(-200), event_at=iso(3600),
        )
        engine = EvidenceVerificationEngine()
        first_registry = test_receipted_announcement_registry(first)
        initial = self.store.sync_announcements([first], first_registry)[0]
        self.assertEqual(initial.state, "CONFIRMED")

        revised = AnnouncementEvidence(
            source_id=first.source_id, source_url=first.source_url,
            publisher=first.publisher, event_type=first.event_type, title=first.title,
            published_at=first.published_at, observed_at=iso(),
            asset_ids=first.asset_ids, content_hash="b" * 64,
            updated_at=iso(-30), event_at=iso(7200),
        )
        revised_registry = test_receipted_announcement_registry(revised)
        updated = self.store.sync_announcements([revised], revised_registry)[0]
        self.assertEqual(updated.state, "DEVELOPING")
        self.assertEqual(self.store.history(updated.event_id)[-1]["reason_code"],
                         "MATERIAL_NEW_EVIDENCE")

    def test_sync_recognizes_material_title_change_but_ignores_cosmetic_formatting(self):
        from layer1.evidence_verification import EvidenceVerificationEngine

        first = AnnouncementEvidence(
            source_id="stable-title-change", source_url="https://www.binance.com/en/support/announcement/stable-title-change",
            publisher="Binance", event_type="listing", title="ABC Spot listing announced",
            published_at=iso(-300), observed_at=iso(), asset_ids=("coingecko:abc",),
            content_hash="e" * 64, updated_at=iso(-200), event_at=iso(3600),
        )
        engine = EvidenceVerificationEngine()
        first_registry = test_receipted_announcement_registry(first)
        initial = self.store.sync_announcements([first], first_registry)[0]
        self.assertEqual(initial.state, "CONFIRMED")

        cosmetic = AnnouncementEvidence(
            source_id=first.source_id, source_url=first.source_url, publisher=first.publisher,
            event_type=first.event_type, title="  ABC SPOT listing announced!  ",
            published_at=first.published_at, observed_at=iso(), asset_ids=first.asset_ids,
            content_hash="f" * 64, updated_at=iso(-100), event_at=first.event_at,
        )
        cosmetic_registry = test_receipted_announcement_registry(cosmetic)
        unchanged = self.store.sync_announcements([cosmetic], cosmetic_registry)[0]
        self.assertEqual(unchanged.state, "CONFIRMED")

        material = AnnouncementEvidence(
            source_id=first.source_id, source_url=first.source_url, publisher=first.publisher,
            event_type=first.event_type, title="ABC Spot listing postponed to next week",
            published_at=first.published_at, observed_at=iso(), asset_ids=first.asset_ids,
            content_hash="1" * 64, updated_at=iso(-30), event_at=first.event_at,
        )
        material_registry = test_receipted_announcement_registry(material)
        updated = self.store.sync_announcements([material], material_registry)[0]
        self.assertEqual(updated.state, "DEVELOPING")
        self.assertEqual(self.store.history(updated.event_id)[-1]["reason_code"], "MATERIAL_NEW_EVIDENCE")

    def test_sync_semantic_body_paraphrase_does_not_mark_event_developing(self):
        from layer1.evidence_verification import EvidenceVerificationEngine

        first = AnnouncementEvidence(
            source_id="stable-semantic-paraphrase",
            source_url="https://www.binance.com/en/support/announcement/stable-semantic-paraphrase",
            publisher="Binance", event_type="listing", title="ABC Spot listing announced",
            published_at=iso(-300), observed_at=iso(), asset_ids=("coingecko:abc",),
            content_hash="a" * 64, updated_at=iso(-200), event_at=iso(3600),
            body="Binance will list ABC on 2026-12-01. Trading starts at 08:00 UTC.",
        )
        engine = EvidenceVerificationEngine()
        first_registry = test_receipted_announcement_registry(first)
        initial = self.store.sync_announcements([first], first_registry)[0]
        self.assertEqual(initial.state, "CONFIRMED")

        paraphrase = AnnouncementEvidence(
            source_id=first.source_id, source_url=first.source_url, publisher=first.publisher,
            event_type=first.event_type, title=first.title, published_at=first.published_at,
            observed_at=iso(), asset_ids=first.asset_ids, content_hash="b" * 64,
            updated_at=iso(-100), event_at=first.event_at,
            body="Binance is going to list ABC on 2026-12-01. Trading will begin at 08:00 UTC.",
        )
        revised_registry = test_receipted_announcement_registry(paraphrase)
        unchanged = self.store.sync_announcements([paraphrase], revised_registry)[0]
        self.assertEqual(unchanged.state, "CONFIRMED")
        self.assertEqual(self.store.history(unchanged.event_id)[-1]["reason_code"], "EVIDENCE_VERIFIED")

    def test_sync_detects_announcement_status_change_as_material(self):
        from layer1.evidence_verification import EvidenceVerificationEngine

        first = AnnouncementEvidence(
            source_id="stable-status-change",
            source_url="https://www.binance.com/en/support/announcement/stable-status-change",
            publisher="Binance", event_type="listing", title="ABC Spot listing",
            published_at=iso(-300), observed_at=iso(), asset_ids=("coingecko:abc",),
            content_hash="a" * 64, updated_at=iso(-200), event_at=iso(3600),
            body="Trading for ABC will start at 08:00 UTC on 2026-12-01.",
        )
        engine = EvidenceVerificationEngine()
        first_registry = test_receipted_announcement_registry(first)
        self.assertEqual(self.store.sync_announcements([first], first_registry)[0].state, "CONFIRMED")

        changed = AnnouncementEvidence(
            source_id=first.source_id, source_url=first.source_url, publisher=first.publisher,
            event_type=first.event_type, title=first.title, published_at=first.published_at,
            observed_at=iso(), asset_ids=first.asset_ids, content_hash="b" * 64,
            updated_at=iso(-100), event_at=first.event_at,
            body="Trading for ABC has been suspended at 08:00 UTC on 2026-12-01.",
        )
        changed_registry = test_receipted_announcement_registry(changed)
        updated = self.store.sync_announcements([changed], changed_registry)[0]
        self.assertEqual(updated.state, "DEVELOPING")
        self.assertEqual(self.store.history(updated.event_id)[-1]["reason_code"], "MATERIAL_NEW_EVIDENCE")

    def test_sync_detects_material_body_change_but_ignores_body_formatting(self):
        from layer1.evidence_verification import EvidenceVerificationEngine

        first = AnnouncementEvidence(
            source_id="stable-body-revision", source_url="https://www.binance.com/en/support/announcement/stable-body-revision",
            publisher="Binance", event_type="listing", title="ABC Spot listing",
            published_at=iso(-300), observed_at=iso(), asset_ids=("coingecko:abc",),
            content_hash="a" * 64, updated_at=iso(-200), event_at=iso(3600),
            body="Binance will list ABC on 2026-12-01. Trading starts at 08:00 UTC.",
        )
        engine = EvidenceVerificationEngine()
        first_registry = test_receipted_announcement_registry(first)
        self.assertEqual(self.store.sync_announcements([first], first_registry)[0].state, "CONFIRMED")

        cosmetic = AnnouncementEvidence(
            source_id=first.source_id, source_url=first.source_url, publisher=first.publisher,
            event_type=first.event_type, title=first.title, published_at=first.published_at,
            observed_at=iso(), asset_ids=first.asset_ids, content_hash="b" * 64,
            updated_at=iso(-100), event_at=first.event_at,
            body="  BINANCE will list ABC on 2026 12 01! Trading starts at 08:00 UTC.  ",
        )
        cosmetic_registry = test_receipted_announcement_registry(cosmetic)
        self.assertEqual(self.store.sync_announcements([cosmetic], cosmetic_registry)[0].state, "CONFIRMED")

        material = AnnouncementEvidence(
            source_id=first.source_id, source_url=first.source_url, publisher=first.publisher,
            event_type=first.event_type, title=first.title, published_at=first.published_at,
            observed_at=iso(), asset_ids=first.asset_ids, content_hash="c" * 64,
            updated_at=iso(-30), event_at=first.event_at,
            body="Binance will list ABC on 2026-12-08. Trading starts at 08:00 UTC.",
        )
        material_registry = test_receipted_announcement_registry(material)
        updated = self.store.sync_announcements([material], material_registry)[0]
        self.assertEqual(updated.state, "DEVELOPING")
        self.assertEqual(self.store.history(updated.event_id)[-1]["reason_code"], "MATERIAL_NEW_EVIDENCE")

    def test_sync_does_not_treat_content_hash_or_source_update_time_as_material_change(self):
        from layer1.evidence_verification import EvidenceVerificationEngine

        first = AnnouncementEvidence(
            source_id="stable-nonmaterial-revision",
            source_url="https://www.binance.com/en/support/announcement/stable-nonmaterial-revision",
            publisher="Binance", event_type="listing", title="ABC Spot listing",
            published_at=iso(-300), observed_at=iso(), asset_ids=("coingecko:abc",),
            content_hash="c" * 64, updated_at=iso(-200), event_at=iso(3600),
        )
        engine = EvidenceVerificationEngine()
        first_registry = test_receipted_announcement_registry(first)
        self.store.sync_announcements([first], first_registry)

        revised = AnnouncementEvidence(
            source_id=first.source_id, source_url=first.source_url,
            publisher=first.publisher, event_type=first.event_type, title=first.title,
            published_at=first.published_at, observed_at=iso(),
            asset_ids=first.asset_ids, content_hash="d" * 64,
            updated_at=iso(-30), event_at=first.event_at,
        )
        revised_registry = test_receipted_announcement_registry(revised)
        updated = self.store.sync_announcements([revised], revised_registry)[0]
        self.assertEqual(updated.state, "CONFIRMED")

    def test_sync_unverified_announcement_does_not_confirm_event(self):
        from layer1.evidence_verification import EvidenceVerificationEngine

        item = evidence()
        engine = EvidenceVerificationEngine()
        registry = engine.verify((), engine.evidence_from_announcement(item))
        records = self.store.sync_announcements([item], registry)
        self.assertEqual(records[0].state, "UNDER_VERIFICATION")

    def test_restart_preserves_current_state_and_append_only_transition_history(self):
        record = self.observe_verified(evidence())
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
        a = self.observe_verified(first)
        b = self.observe_verified(second)
        self.assertNotEqual(a.event_id, b.event_id)


    def test_non_material_revision_does_not_reopen_stale_event(self):
        from dataclasses import replace

        initial = self.observe_verified(evidence("a"))
        stale = self.store.mark_stale(initial.event_id, now=iso(10), max_age_seconds=1)
        revised = replace(evidence("b"), observed_at=iso(30))
        result = self.observe_verified(revised)
        self.assertEqual(stale.state, "STALE")
        self.assertEqual(result.state, "STALE")
        self.assertEqual(
            [row["to_state"] for row in self.store.history(initial.event_id)],
            ["DISCOVERED", "UNDER_VERIFICATION", "CONFIRMED", "STALE"],
        )

    def test_direct_api_cannot_create_resolved_terminal_event_from_caller_string(self):
        from dataclasses import replace

        initial = self.observe_verified(evidence("a"))
        with self.assertRaisesRegex(ValueError, "verifier-issued"):
            self.store.observe(
                evidence("b"), verification_state="VERIFIED", resolved=True,
                resolution_evidence_id="evidence:explicit-resolution",
            )
        revised = replace(evidence("c"), observed_at=iso(30))
        result = self.observe_verified(revised)
        self.assertEqual(result.state, "CONFIRMED")
        self.assertEqual(
            [row["to_state"] for row in self.store.history(initial.event_id)],
            ["DISCOVERED", "UNDER_VERIFICATION", "CONFIRMED"],
        )


if __name__ == "__main__":
    unittest.main()
