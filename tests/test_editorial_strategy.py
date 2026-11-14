import sqlite3
import unittest

from layer1.editorial_strategy import EditorialBriefStore, EditorialStrategyEngine
from tests.test_research_package import DeepResearchEngineTests


class EditorialStrategyEngineTests(unittest.TestCase):
    def setUp(self):
        helper = DeepResearchEngineTests()
        helper.setUp()
        self.package = helper.build()
        helper.tearDown()
        self.engine = EditorialStrategyEngine()
        self.conn = sqlite3.connect(":memory:")
        self.store = EditorialBriefStore(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_verified_announcement_selects_event_update_and_preserves_evidence_hierarchy(self):
        brief = self.engine.build(self.package)
        self.assertEqual(brief.status, "READY")
        self.assertEqual(brief.format, "EVENT_UPDATE")
        self.assertTrue(brief.approved_claim_ids)
        self.assertIn("confirmed event", brief.angle)
        self.assertIn("PROHIBITED_CLAIMS:", brief.render())

    def test_duplicate_angle_is_rejected_unless_material_update_is_explicit(self):
        first = self.store.save(self.engine.build(self.package))
        duplicate = self.engine.build(self.package, store=self.store)
        self.assertEqual(duplicate.status, "REJECT")
        from dataclasses import replace
        new_package = replace(
            self.package, package_id=self.package.research_key + ":2",
            package_hash="b" * 64,
        )
        material = self.engine.build(
            new_package, store=self.store, materially_new=True,
        )
        self.assertEqual(material.status, "READY")
        second = self.store.save(material)
        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)

    def test_incomplete_research_cannot_create_editorial_brief(self):
        from dataclasses import replace
        incomplete = replace(self.package, completeness="RESEARCH_MORE")
        with self.assertRaisesRegex(ValueError, "incomplete research"):
            self.engine.build(incomplete)

    def test_editorial_length_bounds_are_validated(self):
        with self.assertRaisesRegex(ValueError, "length bounds"):
            self.engine.build(self.package, min_words=200, max_words=100)


if __name__ == "__main__":
    unittest.main()
