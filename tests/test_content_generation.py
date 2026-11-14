import sqlite3
import unittest

from layer1.content_generation import DraftStore


class DraftStoreTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.store = DraftStore(self.conn)
        self.args = {
            "asset_id": "coingecko:abc",
            "research_package_id": "research:abc:1",
            "editorial_brief_id": "brief:abc:1",
            "approved_claim_ids": ("claim-a", "claim-b"),
        }

    def tearDown(self):
        self.conn.close()

    def test_draft_is_persisted_before_validation_with_complete_provenance(self):
        draft = self.store.save_draft("$ABC market update.", **self.args)
        self.assertEqual(draft.version, 1)
        loaded = self.store.load_latest(draft.draft_key)
        self.assertEqual(loaded["content"], "$ABC market update.")
        self.assertEqual(loaded["research_package_id"], "research:abc:1")
        self.assertEqual(loaded["approved_claim_ids"], ["claim-a", "claim-b"])
        self.assertIsNone(self.store.latest_text_validation(draft.content_hash))

    def test_identical_draft_is_idempotent_and_revision_is_append_only(self):
        first = self.store.save_draft("$ABC market update.", **self.args)
        duplicate = self.store.save_draft("$ABC market update.", **self.args)
        second = self.store.save_draft("$ABC updated market context.", **self.args)
        self.assertEqual(first.draft_id, duplicate.draft_id)
        self.assertEqual(duplicate.version, 1)
        self.assertEqual(second.version, 2)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM content_draft_versions"
        ).fetchone()[0], 2)

    def test_identical_draft_hash_cannot_be_reused_with_changed_claim_provenance(self):
        self.store.save_draft("$ABC market update.", **self.args)
        with self.assertRaisesRegex(ValueError, "conflicting immutable"):
            self.store.save_draft(
                "$ABC market update.",
                **{**self.args, "approved_claim_ids": ("claim-a", "claim-c")},
            )
        with self.assertRaisesRegex(ValueError, "sequence"):
            self.store.save_draft(
                "$ABC another update.", **{**self.args, "approved_claim_ids": "claim-a"},
            )

    def test_text_validation_is_bound_to_exact_draft_hash(self):
        draft = self.store.save_draft("$ABC market update.", **self.args)
        self.store.save_text_validation(
            draft_hash=draft.content_hash, status="PASS", reasons=(),
            validation_version="content-verification-v1",
        )
        self.assertEqual(self.store.latest_text_validation(draft.content_hash), "PASS")
        changed_hash = "f" * 64
        self.assertIsNone(self.store.latest_text_validation(changed_hash))

    def test_validation_ledgers_reject_malformed_hashes_and_reason_strings(self):
        with self.assertRaisesRegex(ValueError, "invalid text validation"):
            self.store.save_text_validation(
                draft_hash="z" * 64, status="PASS", reasons=(),
                validation_version="v1",
            )
        with self.assertRaisesRegex(ValueError, "sequence of strings"):
            self.store.save_text_validation(
                draft_hash="a" * 64, status="PASS", reasons="not-a-list",
                validation_version="v1",
            )
        with self.assertRaisesRegex(ValueError, "invalid visual validation"):
            self.store.save_visual_validation(
                draft_hash="a" * 64, image_hash="x" * 64, status="PASS",
                reasons=(), validation_version="v1",
            )

    def test_visual_validation_is_bound_to_exact_draft_and_image_hashes(self):
        draft = self.store.save_draft("$ABC market update.", **self.args)
        image_hash = "a" * 64
        self.store.save_visual_validation(
            draft_hash=draft.content_hash, image_hash=image_hash,
            status="PASS", reasons=(), validation_version="visual-quality-v1",
        )
        self.assertEqual(self.store.visual_validation(draft.content_hash, image_hash), "PASS")
        self.assertIsNone(self.store.visual_validation(draft.content_hash, "b" * 64))
        self.assertIsNone(self.store.visual_validation("c" * 64, image_hash))

    def test_image_generation_artifact_is_persisted_with_hashes_and_parameters(self):
        metadata = {
            "provider": "cloudflare_workers_ai",
            "model": "@cf/black-forest-labs/flux-2-klein-4b",
            "request_id": "cf-ray-unit-test",
            "generated_at": "2026-11-14T00:00:00+00:00",
            "prompt_hash": "a" * 64,
            "generation_parameters": {"width": 1024, "height": 1024, "output_format": "PNG"},
            "source_image_hash": "b" * 64,
            "final_image_hash": "c" * 64,
            "draft_hash": "d" * 64,
            "asset_id": "coingecko:abc",
            "symbol": "ABC",
            "dimensions": [1080, 1350],
            "rendered_labels": ["MARKET UPDATE", "$ABC"],
            "chart_data_refs": [],
            "numeric_overlays": [],
        }
        artifact_id = self.store.save_image_artifact(metadata, image_path="/tmp/abc.png")
        duplicate_id = self.store.save_image_artifact(metadata, image_path="/tmp/abc.png")
        self.assertEqual(duplicate_id, artifact_id)
        with self.assertRaisesRegex(ValueError, "different immutable provenance"):
            self.store.save_image_artifact(
                {**metadata, "request_id": "different-request"}, image_path="/tmp/abc.png",
            )
        loaded = self.store.image_artifact("d" * 64, "c" * 64)
        self.assertEqual(loaded["artifact_id"], artifact_id)
        self.assertEqual(loaded["metadata"]["prompt_hash"], "a" * 64)
        self.assertEqual(loaded["metadata"]["generation_parameters"]["width"], 1024)

    def test_image_artifact_rejects_missing_or_invalid_hash_provenance(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.store.save_image_artifact({}, image_path="/tmp/abc.png")

    def test_rejected_validation_never_becomes_pass_for_another_draft(self):
        draft = self.store.save_draft("$ABC unsupported.", **self.args)
        self.store.save_text_validation(
            draft_hash=draft.content_hash, status="REJECT",
            reasons=("UNSUPPORTED_FACT",), validation_version="content-verification-v1",
        )
        self.assertEqual(self.store.latest_text_validation(draft.content_hash), "REJECT")


if __name__ == "__main__":
    unittest.main()
