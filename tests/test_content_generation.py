import sqlite3
import unittest

from layer1.content_generation import DraftStore
from layer1.editorial_strategy import EditorialBrief, EditorialBriefStore, editorial_brief_payload_hash


class DraftStoreTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.brief_store = EditorialBriefStore(self.conn)
        brief_payload = {
            "event_id": "event:abc", "angle_id": "angle:abc",
            "research_package_id": "research:abc:1",
            "research_question": "Explain verified ABC context",
            "format": "MARKET_MOVEMENT_EXPLAINER", "angle": "Explain approved facts",
            "audience": "readers", "tone": "cautious",
            "min_words": 20, "max_words": 120,
            "outline": ("State facts",), "approved_claim_ids": ("a" * 64, "b" * 64),
            "prohibited_claims": (), "uncertainty_notes": (),
            "status": "READY", "policy_version": "test-v1",
        }
        brief_hash = editorial_brief_payload_hash(brief_payload)
        saved_brief = self.brief_store.save(EditorialBrief(
            event_id=brief_payload["event_id"], angle_id=brief_payload["angle_id"],
            brief_id=brief_hash, version=0,
            research_package_id=brief_payload["research_package_id"],
            research_question=brief_payload["research_question"],
            format=brief_payload["format"], angle=brief_payload["angle"],
            audience=brief_payload["audience"], tone=brief_payload["tone"],
            min_words=brief_payload["min_words"], max_words=brief_payload["max_words"],
            outline=brief_payload["outline"], approved_claim_ids=brief_payload["approved_claim_ids"],
            prohibited_claims=brief_payload["prohibited_claims"],
            uncertainty_notes=brief_payload["uncertainty_notes"], status="READY",
            brief_hash=brief_hash, policy_version=brief_payload["policy_version"],
        ))
        self.store = DraftStore(self.conn)
        self.args = {
            "asset_id": "coingecko:abc",
            "research_package_id": "research:abc:1",
            "editorial_brief_id": saved_brief.brief_id,
            "approved_claim_ids": ("a" * 64, "b" * 64),
        }

    def tearDown(self):
        self.conn.close()

    def test_draft_is_persisted_before_validation_with_complete_provenance(self):
        draft = self.store.save_draft("$ABC market update.", **self.args)
        self.assertEqual(draft.version, 1)
        loaded = self.store.load_latest(draft.draft_key)
        self.assertEqual(loaded["content"], "$ABC market update.")
        self.assertEqual(loaded["research_package_id"], "research:abc:1")
        self.assertEqual(loaded["approved_claim_ids"], ["a" * 64, "b" * 64])
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
        with self.assertRaisesRegex(ValueError, "not approved"):
            self.store.save_draft(
                "$ABC market update.",
                **{**self.args, "approved_claim_ids": ("a" * 64, "c" * 64)},
            )
        with self.assertRaisesRegex(ValueError, "sequence"):
            self.store.save_draft(
                "$ABC another update.", **{**self.args, "approved_claim_ids": "claim-a"},
            )

    def test_draft_store_rejects_verified_claim_ids_outside_editorial_allowlist(self):
        with self.assertRaisesRegex(ValueError, "not approved by the editorial brief"):
            self.store.save_draft(
                "$ABC unapproved claim.",
                **{**self.args, "approved_claim_ids": ("c" * 64,)},
            )

    def test_draft_rejects_malformed_claim_ids(self):
        for values in (("claim-not-a-digest",), ("A" * 64,), ("f" * 63,), ("f" * 65,)):
            with self.subTest(values=values):
                with self.assertRaisesRegex(ValueError, "SHA-256 claim IDs"):
                    self.store.save_draft(
                        "$ABC invalid provenance.",
                        **{**self.args, "approved_claim_ids": values},
                    )

    def test_text_validation_is_bound_to_exact_draft_hash(self):
        draft = self.store.save_draft("$ABC market update.", **self.args)
        self.store.save_text_validation(
            draft_hash=draft.content_hash, status="PASS", reasons=(),
            validation_version="content-verification-v2-claim-attribution",
            verification_result=__import__("tests.evidence_fixtures", fromlist=["verifier_issued_content_result"]).verifier_issued_content_result("$ABC market update."),
        )
        self.assertEqual(self.store.latest_text_validation(draft.content_hash), "PASS")
        changed_hash = "f" * 64
        self.assertIsNone(self.store.latest_text_validation(changed_hash))

    def test_public_text_validation_store_rejects_caller_asserted_pass(self):
        draft = self.store.save_draft("$ABC market update.", **self.args)
        with self.assertRaisesRegex(ValueError, "verifier-issued content result"):
            self.store.save_text_validation(
                draft_hash=draft.content_hash, status="PASS", reasons=(),
                validation_version="caller-forged-v1",
            )

    def test_public_text_validation_store_rejects_fabricated_or_mutated_result(self):
        import hashlib
        from dataclasses import replace
        from layer1.content_verification import ContentVerificationResult
        from tests.evidence_fixtures import verifier_issued_content_result

        content = "$ABC market update."
        draft_hash = hashlib.sha256(content.encode()).hexdigest()
        fabricated = ContentVerificationResult(
            status="PASS", draft_hash=draft_hash, asset_id="coingecko:abc", symbol="ABC",
            approved_claim_ids=("a" * 64,), reasons=(), clean_content=content,
        )
        with self.assertRaisesRegex(ValueError, "verifier-issued"):
            self.store.save_text_validation(
                draft_hash=draft_hash, status="PASS", reasons=(),
                validation_version=fabricated.validation_version,
                verification_result=fabricated,
            )
        issued = verifier_issued_content_result(content)
        tampered = replace(issued, clean_content="$ABC changed after verification.")
        with self.assertRaisesRegex(ValueError, "verifier-issued"):
            self.store.save_text_validation(
                draft_hash=draft_hash, status="PASS", reasons=(),
                validation_version=issued.validation_version,
                verification_result=tampered,
            )

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
            status="PASS", reasons=(), validation_version="visual-quality-v3",
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

    def test_latest_validation_uses_insertion_order_when_timestamps_tie(self):
        draft = self.store.save_draft("$ABC market update.", **self.args)
        tied_time = "2026-11-15T12:00:00+00:00"
        # Simulate two append-only decisions recorded at the same timestamp.
        # The lexically larger ID belongs to the older PASS; the later REJECT
        # must win even when timestamps collide.
        self.store.connection.executemany(
            "INSERT OR IGNORE INTO validation_sequence_ledger(sequence) VALUES (?)",
            [(1,), (2,)],
        )
        self.store.connection.executemany(
            "INSERT INTO content_draft_validation_results "
            "(validation_id,draft_hash,status,reasons_json,validation_version,created_at,validation_sequence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("f" * 64, draft.content_hash, "PASS", "[]", "v1", tied_time, 1),
                ("a" * 64, draft.content_hash, "REJECT", '["later rejection"]', "v1", tied_time, 2),
            ],
        )
        image_hash = "b" * 64
        self.store.connection.executemany(
            "INSERT INTO visual_validation_results "
            "(validation_id,draft_hash,image_hash,status,reasons_json,validation_version,created_at,validation_sequence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("f" * 64, draft.content_hash, image_hash, "PASS", "[]", "v1", tied_time, 1),
                ("a" * 64, draft.content_hash, image_hash, "REJECT", '["later rejection"]', "v1", tied_time, 2),
            ],
        )
        self.assertEqual(self.store.latest_text_validation(draft.content_hash), "REJECT")
        self.assertEqual(self.store.visual_validation(draft.content_hash, image_hash), "REJECT")

    def test_existing_sqlite_validation_rows_are_not_backfilled_with_fake_sequence(self):
        import sqlite3
        from layer1.content_generation import DraftStore
        connection = sqlite3.connect(":memory:")
        connection.execute("""CREATE TABLE content_draft_validation_results (
            validation_id TEXT PRIMARY KEY,draft_hash TEXT NOT NULL,status TEXT NOT NULL,
            reasons_json TEXT NOT NULL,validation_version TEXT NOT NULL,created_at TEXT NOT NULL
        )""")
        connection.execute("""CREATE TABLE visual_validation_results (
            validation_id TEXT PRIMARY KEY,draft_hash TEXT NOT NULL,image_hash TEXT NOT NULL,
            status TEXT NOT NULL,reasons_json TEXT NOT NULL,validation_version TEXT NOT NULL,
            created_at TEXT NOT NULL,UNIQUE(draft_hash,image_hash,validation_id)
        )""")
        connection.execute(
            "INSERT INTO content_draft_validation_results VALUES (?,?,?,?,?,?)",
            ("1" * 64, "a" * 64, "PASS", "[]", "v1", "2026-11-20T00:00:00+00:00"),
        )
        store = DraftStore(connection)
        sequence = connection.execute(
            "SELECT validation_sequence FROM content_draft_validation_results"
        ).fetchone()[0]
        self.assertIsNone(sequence)
        self.assertEqual(store.latest_text_validation("a" * 64), "PASS")
        connection.close()

    def test_validation_sequence_never_reuses_a_committed_value_after_record_deletion(self):
        import hashlib
        draft_content = "validation sequence fixture"
        draft_hash = hashlib.sha256(draft_content.encode()).hexdigest()
        first_id = self.store.save_text_validation(
            draft_hash=draft_hash, status="PASS", reasons=(),
            validation_version="content-verification-v2-claim-attribution",
            verification_result=__import__("tests.evidence_fixtures", fromlist=["verifier_issued_content_result"]).verifier_issued_content_result(draft_content),
        )
        first_sequence = self.store.connection.execute(
            "SELECT validation_sequence FROM content_draft_validation_results WHERE validation_id=?",
            (first_id,),
        ).fetchone()[0]
        self.store.connection.execute(
            "DELETE FROM content_draft_validation_results WHERE validation_id=?", (first_id,),
        )
        self.store.connection.commit()
        second_id = self.store.save_text_validation(
            draft_hash=draft_hash, status="REJECT", reasons=("later rejection",), validation_version="v2",
        )
        second_sequence = self.store.connection.execute(
            "SELECT validation_sequence FROM content_draft_validation_results WHERE validation_id=?",
            (second_id,),
        ).fetchone()[0]
        self.assertGreater(second_sequence, first_sequence)
        self.assertEqual(self.store.latest_text_validation(draft_hash), "REJECT")

    def test_ambiguous_tied_legacy_validation_rows_fail_closed(self):
        draft = self.store.save_draft("$ABC legacy chronology.", **self.args)
        tied_time = "2026-11-15T12:00:00+00:00"
        self.store.connection.executemany(
            "INSERT INTO content_draft_validation_results "
            "(validation_id,draft_hash,status,reasons_json,validation_version,created_at) "
            "VALUES (?,?,?,?,?,?)",
            [
                ("1" * 64, draft.content_hash, "PASS", "[]", "v1", tied_time),
                ("2" * 64, draft.content_hash, "REJECT", "[]", "v1", tied_time),
            ],
        )
        with self.assertRaisesRegex(ValueError, "chronology is ambiguous"):
            self.store.latest_text_validation(draft.content_hash)

    def test_rejected_validation_never_becomes_pass_for_another_draft(self):
        draft = self.store.save_draft("$ABC unsupported.", **self.args)
        self.store.save_text_validation(
            draft_hash=draft.content_hash, status="REJECT",
            reasons=("UNSUPPORTED_FACT",), validation_version="content-verification-v1",
        )
        self.assertEqual(self.store.latest_text_validation(draft.content_hash), "REJECT")


if __name__ == "__main__":
    unittest.main()
