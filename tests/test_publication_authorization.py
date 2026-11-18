import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from layer1.publication_authorization import PublicationAuthorizationEngine


def now():
    return datetime.now(timezone.utc).isoformat()


class PublicationAuthorizationEngineTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE post_analytics (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL)"
        )
        self.conn.execute(
            "CREATE TABLE posts (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, coin_symbol TEXT, content TEXT NOT NULL)"
        )
        self.conn.execute("""
            CREATE TABLE publication_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, idempotency_key TEXT NOT NULL UNIQUE,
                coin_symbol TEXT NOT NULL, content_hash TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        self.engine = PublicationAuthorizationEngine(self.conn)

    def tearDown(self):
        self.conn.close()

    def reserve(self, symbol="ABC", limit=3):
        return self.engine.reserve_daily_quota(symbol=symbol, daily_limit=limit)

    def authorize(self, reservation, **overrides):
        from layer1.content_generation import DraftStore
        visual_validation_version = overrides.pop(
            "visual_validation_version", "visual-quality-v2",
        )
        args = {
            "symbol": "ABC", "asset_id": "coingecko:abc",
            "content": "$ABC market update. #ABC",
            "image_hashes": [],
            "eligibility_snapshot_at": now(), "eligibility_max_age_seconds": 300,
            "event_state": "NO_EVENT", "evidence_status": "VERIFIED",
            "text_validation_status": "PASS", "visual_validation_status": "NOT_REQUIRED",
            "quota_reservation_id": reservation, "repetition_hard_hours": 12,
        }
        event_type = overrides.pop("event_type", "other")
        args.update(overrides)
        draft_hash = __import__("hashlib").sha256(args["content"].encode()).hexdigest()
        store = DraftStore(self.conn)
        research_id = "research:test:" + args["asset_id"]
        brief_id = "brief:test:" + draft_hash
        store.save_draft(
            args["content"], asset_id=args["asset_id"],
            research_package_id=research_id,
            editorial_brief_id=brief_id,
            approved_claim_ids=("a" * 64,),
        )
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS editorial_brief_versions (
                event_id TEXT NOT NULL, angle_id TEXT NOT NULL, version INTEGER NOT NULL,
                brief_id TEXT NOT NULL UNIQUE, research_package_id TEXT NOT NULL,
                brief_hash TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
            )
        """)
        self.conn.execute(
            "INSERT OR IGNORE INTO editorial_brief_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("event:test", "angle:test", 1, brief_id, research_id,
             "b" * 64, "{}", now()),
        )
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS layer1_event_lifecycle (
                event_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, state TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'other'
            )
        """)
        if args["event_state"] != "NO_EVENT":
            self.conn.execute(
                "INSERT OR REPLACE INTO layer1_event_lifecycle(event_id, asset_id, state, event_type) VALUES (?, ?, ?, ?)",
                ("event:test", args["asset_id"], args["event_state"], event_type),
            )
        self.conn.commit()
        store.save_text_validation(
            draft_hash=draft_hash, status=args["text_validation_status"],
            reasons=(), validation_version="content-verification-v1",
        )
        for image_hash in args["image_hashes"]:
            if not isinstance(image_hash, str) or len(image_hash) != 64 or any(
                character not in "0123456789abcdef" for character in image_hash
            ):
                continue
            store.save_visual_validation(
                draft_hash=draft_hash, image_hash=image_hash,
                status=args["visual_validation_status"], reasons=(),
                validation_version=visual_validation_version,
            )
        return self.engine.authorize(**args)

    def test_authorization_rejects_pass_from_an_obsolete_visual_validation_version(self):
        reservation = self.reserve()
        with self.assertRaisesRegex(ValueError, "current visual validation version"):
            self.authorize(
                reservation,
                image_hashes=["c" * 64],
                visual_validation_status="PASS",
                visual_validation_version="visual-quality-v1",
            )
        self.assertEqual(self.engine.quota_status(reservation), "RESERVED")

    def test_no_event_snapshot_cannot_bypass_existing_withdrawn_event(self):
        reservation = self.reserve()
        self.conn.execute("""
            CREATE TABLE layer1_event_lifecycle (
                event_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, state TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'other'
            )
        """)
        self.conn.execute(
            "INSERT INTO layer1_event_lifecycle(event_id, asset_id, state, event_type) VALUES (?, ?, ?, ?)",
            ("event:test", "coingecko:abc", "WITHDRAWN", "listing"),
        )
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, "EVENT_LIFECYCLE_STATE_MISMATCH"):
            self.authorize(reservation, event_state="NO_EVENT")

    def test_no_event_authorization_is_invalidated_if_its_event_lifecycle_appears(self):
        reservation = self.reserve()
        auth = self.authorize(reservation, event_state="NO_EVENT")
        self.conn.execute(
            "INSERT INTO layer1_event_lifecycle(event_id, asset_id, state, event_type) VALUES (?, ?, ?, ?)",
            ("event:test", "coingecko:abc", "WITHDRAWN", "listing"),
        )
        self.conn.commit()
        self.assertIn(
            "UNEXPECTED_PERSISTED_EVENT_FOR_NO_EVENT_AUTHORIZATION",
            self.engine.validate_persisted_event_binding(auth),
        )

    def test_authorization_binds_exact_editorial_event_and_revalidates_current_lifecycle(self):
        reservation = self.reserve()
        auth = self.authorize(reservation, event_state="CONFIRMED")
        self.assertEqual(auth.event_id, "event:test")
        self.assertTrue(auth.verify_integrity())
        self.assertEqual(self.engine.validate_persisted_event_binding(auth), ())

        self.conn.execute(
            "UPDATE layer1_event_lifecycle SET state='WITHDRAWN' WHERE event_id='event:test'"
        )
        self.conn.commit()
        self.assertIn(
            "EVENT_LIFECYCLE_CHANGED_AFTER_AUTHORIZATION",
            self.engine.validate_persisted_event_binding(auth),
        )

    def test_persisted_event_asset_mismatch_invalidates_authorization(self):
        reservation = self.reserve()
        auth = self.authorize(reservation, event_state="CONFIRMED")
        self.conn.execute(
            "UPDATE layer1_event_lifecycle SET asset_id='coingecko:other' WHERE event_id='event:test'"
        )
        self.conn.commit()
        self.assertIn(
            "EVENT_ASSET_IDENTITY_CHANGED",
            self.engine.validate_persisted_event_binding(auth),
        )

    def test_authorization_is_immutable_hash_bound_to_exact_payload(self):
        reservation = self.reserve()
        auth = self.authorize(reservation)
        self.assertTrue(auth.verify_integrity())
        self.assertTrue(auth.draft_id)
        self.assertEqual(auth.research_package_id, "research:test:coingecko:abc")
        self.assertEqual(auth.editorial_brief_id, "brief:test:" + auth.content_hash)
        self.assertEqual(auth.approved_claim_ids, ("a" * 64,))
        self.assertEqual(len(auth.draft_provenance_hash), 64)
        self.assertEqual(auth.validate_for_submission(
            symbol="ABC", asset_id="coingecko:abc",
            content="$ABC market update. #ABC", image_hashes=[],
        ), ())
        self.assertTrue(self.engine.quota_status(reservation) == "RESERVED")

    def test_authorization_requires_a_persisted_draft_and_approved_claim_provenance(self):
        from layer1.content_generation import DraftStore
        reservation = self.reserve()
        content = "$ABC unpersisted draft. #ABC"
        draft_hash = __import__("hashlib").sha256(content.encode()).hexdigest()
        DraftStore(self.conn).save_text_validation(
            draft_hash=draft_hash, status="PASS", reasons=(),
            validation_version="content-verification-v1",
        )
        with self.assertRaisesRegex(ValueError, "exact draft must be persisted"):
            self.engine.authorize(
                symbol="ABC", asset_id="coingecko:abc", content=content,
                image_hashes=[], eligibility_snapshot_at=now(),
                eligibility_max_age_seconds=300, event_state="NO_EVENT",
                evidence_status="VERIFIED", text_validation_status="PASS",
                visual_validation_status="NOT_REQUIRED",
                quota_reservation_id=reservation, repetition_hard_hours=12,
            )
        self.engine.mark_quota_status(reservation, "RELEASED")

    def test_changed_draft_asset_or_image_hash_is_rejected(self):
        reservation = self.reserve()
        auth = self.authorize(reservation)
        self.assertIn("DRAFT_CONTENT_CHANGED", auth.validate_for_submission(
            symbol="ABC", asset_id="coingecko:abc",
            content="$ABC changed. #ABC", image_hashes=[],
        ))
        self.assertIn("ASSET_IDENTITY_CHANGED", auth.validate_for_submission(
            symbol="XYZ", asset_id="coingecko:xyz",
            content="$ABC market update. #ABC", image_hashes=[],
        ))
        self.assertIn("IMAGE_ARTIFACT_CHANGED", auth.validate_for_submission(
            symbol="ABC", asset_id="coingecko:abc",
            content="$ABC market update. #ABC", image_hashes=["f" * 64],
        ))

    def test_stale_eligibility_event_state_and_expired_authorization_are_rejected(self):
        reservation = self.reserve()
        stale = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
        with self.assertRaisesRegex(ValueError, "SPOT_ELIGIBILITY_SNAPSHOT_STALE"):
            self.authorize(reservation, eligibility_snapshot_at=stale)
        self.engine.mark_quota_status(reservation, "RELEASED")

        reservation = self.reserve()
        with self.assertRaisesRegex(ValueError, "EVENT_STATE_NOT_PUBLISHABLE"):
            self.authorize(reservation, event_state="STALE")
        self.engine.mark_quota_status(reservation, "RELEASED")
        self.conn.execute("DELETE FROM layer1_event_lifecycle WHERE event_id='event:test'")
        self.conn.commit()

        reservation = self.reserve()
        auth = self.authorize(reservation, ttl_seconds=1)
        expired = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
        self.assertIn("AUTHORIZATION_EXPIRED", auth.validate_for_submission(
            symbol="ABC", asset_id="coingecko:abc",
            content="$ABC market update. #ABC", image_hashes=[], now=expired,
        ))

    def test_missing_evidence_text_visual_or_duplicate_gate_denies_authorization(self):
        reservation = self.reserve()
        with self.assertRaisesRegex(ValueError, "EVIDENCE_GATE_FAILED"):
            self.authorize(reservation, evidence_status="UNVERIFIED")
        self.engine.mark_quota_status(reservation, "RELEASED")
        reservation = self.reserve()
        with self.assertRaisesRegex(ValueError, "persisted text validation is not PASS"):
            self.authorize(reservation, text_validation_status="REJECT")
        self.engine.mark_quota_status(reservation, "RELEASED")
        reservation = self.reserve()
        with self.assertRaisesRegex(ValueError, "VISUAL_VALIDATION_FAILED"):
            self.authorize(
                reservation, visual_validation_status="REJECT",
                content="$ABC visual gate test. #ABC",
            )
        self.engine.mark_quota_status(reservation, "RELEASED")
        reservation = self.reserve()
        self.conn.execute(
            "INSERT INTO posts(created_at, coin_symbol, content) VALUES (?, ?, ?)",
            ((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), "ABC", "prior content"),
        )
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, "RECENT_POST_COOLDOWN"):
            self.authorize(reservation, content="$ABC duplicate gate test. #ABC")

    def test_image_authorization_requires_visual_pass_and_exact_hash(self):
        image_hash = "a" * 64
        reservation = self.reserve()
        auth = self.authorize(
            reservation, image_hashes=[image_hash], visual_validation_status="PASS",
        )
        self.assertEqual(auth.image_hashes, (image_hash,))
        self.assertEqual(auth.validate_for_submission(
            symbol="ABC", asset_id="coingecko:abc",
            content="$ABC market update. #ABC", image_hashes=[image_hash],
        ), ())

    def test_daily_quota_reservations_are_atomic_and_include_existing_analytics(self):
        first = self.reserve(limit=1)
        self.assertIsNotNone(first)
        self.assertIsNone(self.reserve(limit=1))
        self.engine.mark_quota_status(first, "RELEASED")
        self.conn.execute("INSERT INTO post_analytics(created_at) VALUES (?)", (now()[:10],))
        self.conn.commit()
        self.assertIsNone(self.reserve(limit=1))

    def test_quota_state_machine_rejects_illegal_transitions(self):
        reservation = self.reserve()
        with self.assertRaisesRegex(ValueError, "illegal quota reservation transition"):
            self.engine.mark_quota_status(reservation, "PUBLISHED_CONFIRMED")
        self.engine.mark_quota_status(reservation, "SUBMITTING")
        self.engine.mark_quota_status(reservation, "PUBLICATION_UNKNOWN")
        self.engine.mark_quota_status(reservation, "PUBLISHED_CONFIRMED")
        with self.assertRaisesRegex(ValueError, "illegal quota reservation transition"):
            self.engine.mark_quota_status(reservation, "RELEASED")

    def test_image_hashes_must_be_unique_sha256_hex_and_asset_identity_canonical(self):
        reservation = self.reserve()
        with self.assertRaisesRegex(ValueError, "unique"):
            self.authorize(
                reservation, image_hashes=["a" * 64, "a" * 64],
                visual_validation_status="PASS",
            )
        self.engine.mark_quota_status(reservation, "RELEASED")

        reservation = self.reserve()
        with self.assertRaisesRegex(ValueError, "SHA-256 hex"):
            self.authorize(
                reservation, image_hashes=["z" * 64],
                visual_validation_status="PASS",
            )
        self.engine.mark_quota_status(reservation, "RELEASED")

        reservation = self.reserve()
        with self.assertRaisesRegex(ValueError, "canonical asset identity"):
            self.authorize(reservation, asset_id="coingecko:")
        self.engine.mark_quota_status(reservation, "RELEASED")

    def test_authorization_cannot_be_created_with_another_symbols_quota(self):
        reservation = self.reserve(symbol="XYZ")
        with self.assertRaisesRegex(ValueError, "quota reservation is missing"):
            self.authorize(reservation)


    def test_unresolved_attempt_blocks_even_for_exceptional_event(self):
        reservation = self.reserve()
        self.conn.execute(
            "INSERT INTO publication_attempts(idempotency_key,coin_symbol,content_hash,status,created_at,updated_at) "
            "VALUES (?, ?, ?, 'PUBLICATION_UNKNOWN', ?, ?)",
            ("prior-attempt", "ABC", "b" * 64, now(), now()),
        )
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, "UNRESOLVED_PUBLICATION_ATTEMPT"):
            self.authorize(
                reservation, event_state="CONFIRMED", event_type="new_listing",
                content="$ABC exceptional listing update. #ABC",
            )

    def test_competing_active_quota_reservation_blocks_authorization(self):
        first = self.reserve()
        second = self.reserve()
        with self.assertRaisesRegex(ValueError, "COMPETING_ACTIVE_QUOTA_RESERVATION"):
            self.authorize(first)
        self.assertEqual(self.engine.quota_status(first), "RESERVED")
        self.assertEqual(self.engine.quota_status(second), "RESERVED")

    def test_exceptional_event_bypasses_recent_symbol_cooldown_only(self):
        reservation = self.reserve()
        self.conn.execute(
            "INSERT INTO posts(created_at, coin_symbol, content) VALUES (?, ?, ?)",
            ((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), "ABC", "prior content"),
        )
        self.conn.commit()
        auth = self.authorize(
            reservation, event_state="CONFIRMED", event_type="new_listing",
            content="$ABC verified new listing update. #ABC",
        )
        self.assertTrue(auth.duplicate_policy_passed)

    def test_duplicate_policy_is_rechecked_against_new_persisted_post(self):
        reservation = self.reserve()
        auth = self.authorize(reservation)
        self.conn.execute(
            "INSERT INTO posts(created_at, coin_symbol, content) VALUES (?, ?, ?)",
            ((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), "ABC", "later competing post"),
        )
        self.conn.commit()
        self.assertIn(
            "RECENT_POST_COOLDOWN",
            self.engine.validate_persisted_duplicate_policy(auth),
        )


if __name__ == "__main__":
    unittest.main()
