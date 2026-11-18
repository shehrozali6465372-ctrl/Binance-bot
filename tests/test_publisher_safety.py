import io
import json
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import main


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class PublisherSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.db_path = str(Path(self.tmp.name) / "agent.db")
        self.config = replace(
            main.CONFIG,
            database_path=self.db_path,
            dry_run=False,
            publisher_enabled=True,
            square_api_key="test-key-not-real",
            http_timeout_seconds=1,
        )
        self.publisher = main.PostPublisher(self.config)

    def tearDown(self):
        self.publisher.db.close()
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def _authorization(self, coin, content, image_hashes=None, event_state="NO_EVENT"):
        from layer1.content_generation import DraftStore
        from layer1.publication_authorization import PublicationAuthorizationEngine
        coin = dict(coin)
        symbol = str(coin.get("symbol") or "").upper()
        coin.setdefault("asset_id", "coingecko:" + symbol.lower())
        hashes = list(image_hashes or [])
        engine = PublicationAuthorizationEngine(self.publisher.db.conn)
        reservation = engine.reserve_daily_quota(symbol=symbol, daily_limit=100)
        draft_hash = main.hashlib.sha256(content.encode("utf-8")).hexdigest()
        draft_store = DraftStore(self.publisher.db.conn)
        research_id = "research:test:" + coin["asset_id"]
        brief_id = "brief:test:" + draft_hash
        draft_store.save_draft(
            content, asset_id=coin["asset_id"],
            research_package_id=research_id,
            editorial_brief_id=brief_id,
            approved_claim_ids=("a" * 64,),
        )
        self.publisher.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS editorial_brief_versions (
                event_id TEXT NOT NULL, angle_id TEXT NOT NULL, version INTEGER NOT NULL,
                brief_id TEXT NOT NULL UNIQUE, research_package_id TEXT NOT NULL,
                brief_hash TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
            )
        """)
        self.publisher.db.conn.execute(
            "INSERT OR IGNORE INTO editorial_brief_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (("event:test" if event_state != "NO_EVENT" else "no-event:" + research_id),
             "angle:test", 1, brief_id, research_id, "b" * 64, "{}", main.utc_now()),
        )
        if event_state != "NO_EVENT":
            self.publisher.db.conn.execute("""
                CREATE TABLE IF NOT EXISTS layer1_event_lifecycle (
                    event_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, state TEXT NOT NULL,
                    event_type TEXT NOT NULL DEFAULT 'other'
                )
            """)
            self.publisher.db.conn.execute(
                "INSERT OR REPLACE INTO layer1_event_lifecycle(event_id, asset_id, state) VALUES (?, ?, ?)",
                ("event:test", coin["asset_id"], event_state),
            )
        self.publisher.db.conn.commit()
        draft_store.save_text_validation(
            draft_hash=draft_hash, status="PASS", reasons=(),
            validation_version="content-verification-v1",
        )
        for image_hash in hashes:
            draft_store.save_visual_validation(
                draft_hash=draft_hash, image_hash=image_hash,
                status="PASS", reasons=(), validation_version="visual-quality-v2",
            )
        auth = engine.authorize(
            symbol=symbol, asset_id=coin["asset_id"], content=content,
            image_hashes=hashes, eligibility_snapshot_at=main.utc_now(),
            eligibility_max_age_seconds=300, event_state=event_state,
            evidence_status="VERIFIED", text_validation_status="PASS",
            visual_validation_status="PASS" if hashes else "NOT_REQUIRED",
            quota_reservation_id=reservation,
            repetition_hard_hours=self.config.repetition_hard_hours,
        )
        return coin, auth, hashes

    def _publish(self, coin, content, image_list=None):
        try:
            coin, auth, hashes = self._authorization(coin, content)
        except ValueError as exc:
            return main.PublishResult(status="FAILED_CONFIRMED", error=str(exc))
        return self.publisher.publish(
            coin, content, image_list=image_list,
            authorization=auth, image_hashes=hashes,
        )

    def test_visual_validation_downgrade_after_authorization_blocks_before_network_post(self):
        image_hash = "c" * 64
        coin, authorization, hashes = self._authorization(
            {"symbol": "BTC"}, "visual version-bound content",
            image_hashes=[image_hash],
        )
        from layer1.content_generation import DraftStore
        DraftStore(self.publisher.db.conn).save_visual_validation(
            draft_hash=authorization.content_hash, image_hash=image_hash,
            status="PASS", reasons=(), validation_version="visual-quality-v1",
        )
        self.publisher.db.conn.execute(
            "UPDATE visual_validation_results SET created_at='9999-01-01T00:00:00+00:00' "
            "WHERE draft_hash=? AND image_hash=? AND validation_version='visual-quality-v1'",
            (authorization.content_hash, image_hash),
        )
        self.publisher.db.conn.commit()
        with patch("main._open_binance_publish_no_redirect") as urlopen:
            result = self.publisher.publish(
                coin, "visual version-bound content",
                authorization=authorization, image_hashes=hashes,
            )
        self.assertEqual(result.status, "FAILED_CONFIRMED")
        self.assertIn("current visual validation version", result.error)
        urlopen.assert_not_called()

    def test_lifecycle_change_after_authorization_blocks_before_network_post(self):
        coin, authorization, hashes = self._authorization(
            {"symbol": "BTC"}, "event-backed content", event_state="CONFIRMED",
        )
        original_begin = self.publisher._begin_attempt

        def reserve_then_withdraw(*args, **kwargs):
            result = original_begin(*args, **kwargs)
            self.publisher.db.conn.execute(
                "UPDATE layer1_event_lifecycle SET state='WITHDRAWN' WHERE event_id='event:test'"
            )
            self.publisher.db.conn.commit()
            return result

        with patch.object(self.publisher, "_begin_attempt", side_effect=reserve_then_withdraw):
            with patch("main._open_binance_publish_no_redirect") as urlopen:
                result = self.publisher.publish(
                    coin, "event-backed content", authorization=authorization,
                    image_hashes=hashes,
                )
        self.assertEqual(result.status, "FAILED_CONFIRMED")
        self.assertIn("EVENT_LIFECYCLE_CHANGED_AFTER_AUTHORIZATION", result.error)
        urlopen.assert_not_called()
        attempt = self.publisher.db.conn.execute(
            "SELECT status FROM publication_attempts WHERE coin_symbol='BTC'"
        ).fetchone()
        self.assertEqual(attempt["status"], "FAILED_CONFIRMED")

    def test_postgres_opt_in_publisher_uses_durable_store_and_never_sqlite_attempt_ledger(self):
        from dataclasses import asdict

        coin, authorization, hashes = self._authorization(
            {"symbol": "BTC"}, "postgres opt-in publisher content",
        )

        class FakePostgresStore:
            def __init__(self):
                self.calls = []
                self.payload = asdict(authorization)

            def begin_authorized_attempt(self, **kwargs):
                self.calls.append(("begin", kwargs))
                return None

            def validate_authorized_attempt_before_submit(self, **kwargs):
                self.calls.append(("preflight", kwargs))

            def finish_authorized_attempt(self, key, status, **kwargs):
                self.calls.append(("finish", key, status, kwargs))

        store = FakePostgresStore()
        publisher = main.PostPublisher(self.config, postgres_store=store)
        response = FakeResponse({
            "code": "000000",
            "data": {"id": "pg-remote-1", "shareLink": "https://example.invalid/pg-remote-1"},
        })
        try:
            with patch("main._open_binance_publish_no_redirect", return_value=response) as urlopen:
                result = publisher.publish(
                    coin, "postgres opt-in publisher content",
                    authorization=authorization, image_hashes=hashes,
                )
            self.assertEqual(result.status, "PUBLISHED_CONFIRMED")
            self.assertEqual(result.post_id, "pg-remote-1")
            self.assertEqual(urlopen.call_count, 1)
            self.assertEqual([call[0] for call in store.calls],
                             ["begin", "preflight", "finish", "finish"])
            self.assertEqual(store.calls[-2][2], "PUBLICATION_UNKNOWN")
            self.assertEqual(store.calls[-1][2], "PUBLISHED_CONFIRMED")
            self.assertEqual(publisher.db.conn.execute(
                "SELECT COUNT(*) FROM publication_attempts"
            ).fetchone()[0], 0)
        finally:
            publisher.db.close()

    def test_postgres_opt_in_publisher_blocks_existing_unknown_attempt_without_post(self):
        coin, authorization, hashes = self._authorization(
            {"symbol": "BTC"}, "postgres pending attempt content",
        )

        class PendingStore:
            def begin_authorized_attempt(self, **kwargs):
                return {"status": "PUBLICATION_UNKNOWN", "remote_post_id": "", "share_link": ""}

        publisher = main.PostPublisher(self.config, postgres_store=PendingStore())
        try:
            with patch("main._open_binance_publish_no_redirect") as urlopen:
                result = publisher.publish(
                    coin, "postgres pending attempt content",
                    authorization=authorization, image_hashes=hashes,
                )
            self.assertEqual(result.status, "PUBLICATION_UNKNOWN")
            urlopen.assert_not_called()
        finally:
            publisher.db.close()


    def test_postgres_pre_submit_ledger_failure_is_known_not_submitted_and_releases_quota(self):
        coin, authorization, hashes = self._authorization(
            {"symbol": "BTC"}, "postgres pre-submit ledger failure content",
        )

        class RejectingPreflightStore:
            def __init__(self):
                self.calls = []

            def begin_authorized_attempt(self, **kwargs):
                self.calls.append(("begin", kwargs))
                return None

            def validate_authorized_attempt_before_submit(self, **kwargs):
                self.calls.append(("preflight", kwargs))
                raise RuntimeError("DUPLICATE_LEDGER_UNAVAILABLE")

            def finish_authorized_attempt(self, key, status, **kwargs):
                self.calls.append(("finish", key, status, kwargs))

        store = RejectingPreflightStore()
        publisher = main.PostPublisher(self.config, postgres_store=store)
        try:
            with patch("main._open_binance_publish_no_redirect") as urlopen:
                result = publisher.publish(
                    coin, "postgres pre-submit ledger failure content",
                    authorization=authorization, image_hashes=hashes,
                )
            self.assertEqual(result.status, "FAILED_CONFIRMED")
            self.assertIn("pre-submit authorization failed", result.error.lower())
            urlopen.assert_not_called()
            self.assertEqual([call[0] for call in store.calls], ["begin", "preflight", "finish"])
            self.assertEqual(store.calls[-1][2], "FAILED_CONFIRMED")
        finally:
            publisher.db.close()

    def test_square_publish_transport_refuses_redirects(self):
        from urllib.request import Request
        handler = main._NoRedirectHTTPHandler()
        request = Request(main.PostPublisher.API_URL, data=b"{}", method="POST")
        self.assertIsNone(handler.redirect_request(
            request, None, 307, "Temporary Redirect", {},
            "https://evil.example/collect",
        ))

    def test_dry_run_never_posts(self):
        dry = main.PostPublisher(replace(self.config, dry_run=True))
        try:
            with patch("main._open_binance_publish_no_redirect") as urlopen:
                result = dry.publish({"symbol": "BTC"}, "educational content")
            self.assertEqual(result.status, "DRY_RUN")
            self.assertFalse(result.confirmed)
            urlopen.assert_not_called()
        finally:
            dry.db.close()

    def test_confirmed_post_is_submitted_once_and_duplicate_is_blocked(self):
        response = FakeResponse({
            "code": "000000",
            "data": {"id": "remote-123", "shareLink": "https://example.invalid/post/remote-123"},
        })
        with patch("main._open_binance_publish_no_redirect", return_value=response) as urlopen:
            first = self._publish({"symbol": "BTC"}, "same educational content")
            second = self._publish({"symbol": "BTC"}, "same educational content")

        self.assertEqual(first.status, "PUBLISHED_CONFIRMED")
        self.assertEqual(first.post_id, "remote-123")
        self.assertTrue(first.confirmed)
        self.assertEqual(second.status, "FAILED_CONFIRMED")
        self.assertIn("RECENT_POST_COOLDOWN", second.error)
        self.assertFalse(second.confirmed)
        self.assertEqual(urlopen.call_count, 1)

    def test_live_publisher_rechecks_exact_persisted_draft_claim_provenance(self):
        coin, authorization, hashes = self._authorization(
            {"symbol": "BTC"}, "immutable provenance test",
        )
        self.publisher.db.conn.execute(
            "UPDATE content_draft_versions SET approved_claim_ids_json=? WHERE draft_id=?",
            (json.dumps(["claim:tampered"]), authorization.draft_id),
        )
        self.publisher.db.conn.commit()
        with patch("main._open_binance_publish_no_redirect") as urlopen:
            result = self.publisher.publish(
                coin, "immutable provenance test",
                authorization=authorization, image_hashes=hashes,
            )
        self.assertEqual(result.status, "FAILED_CONFIRMED")
        self.assertIn("provenance", result.error)
        urlopen.assert_not_called()

    def test_live_publisher_blocks_missing_or_mismatched_authorization(self):
        with patch("main._open_binance_publish_no_redirect") as urlopen:
            missing = self.publisher.publish(
                {"symbol": "BTC", "asset_id": "coingecko:btc"},
                "no authorization",
            )
            coin, authorization, hashes = self._authorization(
                {"symbol": "BTC"}, "authorized draft",
            )
            changed = self.publisher.publish(
                coin, "changed after authorization",
                authorization=authorization, image_hashes=hashes,
            )
        self.assertEqual(missing.status, "FAILED_CONFIRMED")
        self.assertEqual(changed.status, "FAILED_CONFIRMED")
        urlopen.assert_not_called()

    def test_ambiguous_timeout_blocks_changed_content_for_same_symbol(self):
        with patch("main._open_binance_publish_no_redirect", side_effect=URLError("socket timeout")) as urlopen:
            first = self._publish({"symbol": "ETH"}, "first generated text")
            second = self._publish({"symbol": "ETH"}, "different regenerated text")

        self.assertEqual(first.status, "PUBLICATION_UNKNOWN")
        self.assertEqual(second.status, "FAILED_CONFIRMED")
        self.assertIn("UNRESOLVED_PUBLICATION_ATTEMPT", second.error)
        self.assertEqual(urlopen.call_count, 1)

    def test_definitive_client_rejection_is_not_retried(self):
        response = FakeResponse({"code": "400001", "message": "Rejected"})
        from urllib.error import HTTPError
        error = HTTPError("https://example.invalid", 400, "Bad Request", {}, io.BytesIO(b""))
        with patch("main._open_binance_publish_no_redirect", side_effect=error) as urlopen:
            first = self._publish({"symbol": "SOL"}, "rejected content")
            second = self._publish({"symbol": "SOL"}, "rejected content")

        self.assertEqual(first.status, "FAILED_CONFIRMED")
        self.assertEqual(second.status, "DUPLICATE_BLOCKED")
        self.assertEqual(urlopen.call_count, 1)

    def test_remote_acceptance_followed_by_local_persistence_failure_is_not_retried(self):
        response = FakeResponse({
            "code": "000000",
            "data": {"id": "remote-after-db-error", "shareLink": "https://example.invalid/post/remote-after-db-error"},
        })
        with patch("main._open_binance_publish_no_redirect", return_value=response) as urlopen:
            with patch.object(self.publisher.db, "save_post", side_effect=sqlite3.OperationalError("disk full")):
                first = self._publish({"symbol": "XRP"}, "first content")
            second = self._publish({"symbol": "XRP"}, "regenerated content")

        self.assertEqual(first.status, "PUBLICATION_UNKNOWN")
        self.assertEqual(second.status, "FAILED_CONFIRMED")
        self.assertIn("UNRESOLVED_PUBLICATION_ATTEMPT", second.error)
        self.assertEqual(urlopen.call_count, 1)
        row = self.publisher.db.conn.execute(
            "SELECT status, remote_post_id, share_link FROM publication_attempts WHERE coin_symbol = 'XRP'"
        ).fetchone()
        self.assertEqual(row["status"], "PUBLICATION_UNKNOWN")
        self.assertEqual(row["remote_post_id"], "remote-after-db-error")
        self.assertEqual(row["share_link"], "https://example.invalid/post/remote-after-db-error")

    def test_success_response_without_remote_id_is_unknown_and_not_retried(self):
        response = FakeResponse({"code": "000000", "data": {"shareLink": "https://example.invalid/no-id"}})
        with patch("main._open_binance_publish_no_redirect", return_value=response) as urlopen:
            first = self._publish({"symbol": "ADA"}, "content without remote identity")
            second = self._publish({"symbol": "ADA"}, "regenerated content")

        self.assertEqual(first.status, "PUBLICATION_UNKNOWN")
        self.assertEqual(second.status, "FAILED_CONFIRMED")
        self.assertIn("UNRESOLVED_PUBLICATION_ATTEMPT", second.error)
        self.assertEqual(urlopen.call_count, 1)

    def test_metrics_require_exact_remote_post_identity(self):
        analyzer = main.PerformanceAnalyzer(self.publisher.db)
        analyzer.record_publish(
            {"symbol": "DOGE"}, "educational post #DOGE",
            square_link="https://example.invalid/post/remote-doge",
            remote_post_id="remote-doge",
        )
        self.assertFalse(analyzer.update_metrics("DOGE", views=100, remote_post_id="wrong-id"))
        self.assertTrue(analyzer.update_metrics("DOGE", views=100, remote_post_id="remote-doge"))
        row = self.publisher.db.conn.execute(
            "SELECT views, remote_post_id FROM post_analytics WHERE coin_symbol = 'DOGE'"
        ).fetchone()
        self.assertEqual(row["views"], 100)
        self.assertEqual(row["remote_post_id"], "remote-doge")

    def test_schema_has_additive_ledger_and_remote_identity(self):
        columns = {
            row["name"] for row in self.publisher.db.conn.execute(
                "PRAGMA table_info(post_analytics)"
            ).fetchall()
        }
        self.assertIn("remote_post_id", columns)
        table = self.publisher.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='publication_attempts'"
        ).fetchone()
        self.assertIsNotNone(table)

    def test_existing_analytics_rows_survive_additive_migration(self):
        legacy_path = str(Path(self.tmp.name) / "legacy.db")
        legacy = sqlite3.connect(legacy_path)
        legacy.execute(
            "CREATE TABLE post_analytics (id INTEGER PRIMARY KEY, coin_symbol TEXT, created_at TEXT, views INTEGER)"
        )
        legacy.execute(
            "INSERT INTO post_analytics (id, coin_symbol, created_at, views) VALUES (1, 'BTC', '2026-01-01T00:00:00+00:00', 7)"
        )
        legacy.commit()
        legacy.close()

        migrated = main.Database(legacy_path)
        try:
            row = migrated.conn.execute(
                "SELECT id, coin_symbol, views FROM post_analytics WHERE id = 1"
            ).fetchone()
            columns = {
                item["name"] for item in migrated.conn.execute(
                    "PRAGMA table_info(post_analytics)"
                ).fetchall()
            }
            self.assertEqual((row["id"], row["coin_symbol"], row["views"]), (1, "BTC", 7))
            self.assertIn("remote_post_id", columns)
            ledger = migrated.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='publication_attempts'"
            ).fetchone()
            self.assertIsNotNone(ledger)
        finally:
            migrated.close()

    def test_second_database_connection_observes_unresolved_reservation(self):
        second = main.PostPublisher(self.config)
        try:
            key = self.publisher._idempotency_key("LINK", "reserved content", [])
            content_hash = main.hashlib.sha256(b"reserved content").hexdigest()
            self.assertIsNone(self.publisher._begin_attempt(key, "LINK", content_hash))
            with self.assertRaisesRegex(ValueError, "UNRESOLVED_PUBLICATION_ATTEMPT"):
                self._authorization({"symbol": "LINK"}, "different regenerated content")
            with patch("main._open_binance_publish_no_redirect") as urlopen:
                urlopen.assert_not_called()
        finally:
            second.db.close()

    def test_sqlite_backup_restore_preserves_publication_ledger(self):
        key = self.publisher._idempotency_key("AVAX", "backup content", [])
        content_hash = main.hashlib.sha256(b"backup content").hexdigest()
        self.assertIsNone(self.publisher._begin_attempt(key, "AVAX", content_hash))
        self.publisher._finish_attempt(
            key, "PUBLICATION_UNKNOWN", post_id="remote-backup-1",
            share_link="https://example.invalid/remote-backup-1", http_status=504,
            error="ambiguous gateway timeout",
        )
        backup_path = str(Path(self.tmp.name) / "backup.db")
        restored_path = str(Path(self.tmp.name) / "restored.db")
        backup = sqlite3.connect(backup_path)
        try:
            self.publisher.db.conn.backup(backup)
        finally:
            backup.close()
        restored = sqlite3.connect(backup_path)
        try:
            target = sqlite3.connect(restored_path)
            try:
                restored.backup(target)
            finally:
                target.close()
        finally:
            restored.close()
        check = main.Database(restored_path)
        try:
            row = check.conn.execute(
                "SELECT status, remote_post_id, share_link, http_status FROM publication_attempts WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            self.assertEqual(row["status"], "PUBLICATION_UNKNOWN")
            self.assertEqual(row["remote_post_id"], "remote-backup-1")
            self.assertEqual(row["share_link"], "https://example.invalid/remote-backup-1")
            self.assertEqual(row["http_status"], 504)
        finally:
            check.close()

    def test_operator_reconciliation_rejects_untrusted_or_mismatched_post_links(self):
        from scripts.reconcile_publications import _validate_reconciliation_identity
        self.assertEqual(
            _validate_reconciliation_identity(
                "remote-atom", "https://www.binance.com/square/post/remote-atom",
            ),
            "https://www.binance.com/square/post/remote-atom",
        )
        invalid_links = (
            "http://www.binance.com/square/post/remote-atom",
            "https://binance.com.evil.example/square/post/remote-atom",
            "https://user:pass@www.binance.com/square/post/remote-atom",
            "https://www.binance.com/square/post/different-id",
            "https://www.binance.com/profile/remote-atom",
        )
        for link in invalid_links:
            with self.subTest(link=link):
                with self.assertRaisesRegex(ValueError, "HTTPS Binance Square"):
                    _validate_reconciliation_identity("remote-atom", link)
        with self.assertRaisesRegex(ValueError, "remote post ID"):
            _validate_reconciliation_identity("remote atom", "")

    def test_operator_reconciliation_confirms_known_remote_id_without_network(self):
        from layer1.publication_authorization import PublicationAuthorizationEngine
        from layer1.content_generation import DraftStore
        quota = PublicationAuthorizationEngine(self.publisher.db.conn)
        reservation = quota.reserve_daily_quota(symbol="ATOM", daily_limit=6)
        draft_hash = main.hashlib.sha256(b"pending content").hexdigest()
        research_id = "research:test:coingecko:atom"
        brief_id = "brief:test:" + draft_hash
        DraftStore(self.publisher.db.conn).save_draft(
            "pending content", asset_id="coingecko:atom",
            research_package_id=research_id,
            editorial_brief_id=brief_id,
            approved_claim_ids=("a" * 64,),
        )
        self.publisher.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS editorial_brief_versions (
                event_id TEXT NOT NULL, angle_id TEXT NOT NULL, version INTEGER NOT NULL,
                brief_id TEXT NOT NULL UNIQUE, research_package_id TEXT NOT NULL,
                brief_hash TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
            )
        """)
        self.publisher.db.conn.execute(
            "INSERT INTO editorial_brief_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("no-event:" + research_id, "angle:test", 1, brief_id, research_id,
             "b" * 64, "{}", main.utc_now()),
        )
        self.publisher.db.conn.commit()
        DraftStore(self.publisher.db.conn).save_text_validation(
            draft_hash=draft_hash,
            status="PASS", reasons=(), validation_version="content-verification-v1",
        )
        auth = quota.authorize(
            symbol="ATOM", asset_id="coingecko:atom", content="pending content",
            image_hashes=[], eligibility_snapshot_at=main.utc_now(),
            eligibility_max_age_seconds=300, event_state="NO_EVENT",
            evidence_status="VERIFIED", text_validation_status="PASS",
            visual_validation_status="NOT_REQUIRED", quota_reservation_id=reservation,
            repetition_hard_hours=12,
        )
        key = self.publisher._idempotency_key("ATOM", "pending content", [])
        digest = main.hashlib.sha256(b"pending content").hexdigest()
        self.assertIsNone(self.publisher._begin_attempt(key, "ATOM", digest))
        attempt_id = self.publisher.db.conn.execute(
            "SELECT id FROM publication_attempts WHERE idempotency_key=?", (key,),
        ).fetchone()["id"]
        quota.bind_attempt(reservation, attempt_id)
        quota.mark_quota_status(reservation, "SUBMITTING")
        quota.mark_quota_status(reservation, "PUBLICATION_UNKNOWN")
        import scripts.reconcile_publications as reconcile
        args = type("Args", (), {
            "action": "confirm-published", "attempt_id": 1,
            "operator": "test-operator", "note": "Verified in Creator Center",
            "evidence": "manual-check:creator-center/post/remote-atom",
            "remote_post_id": "remote-atom",
            "share_link": "https://www.binance.com/square/post/remote-atom",
        })()
        with patch("main._open_binance_publish_no_redirect") as urlopen:
            reconcile.reconcile(self.publisher.db.conn, args)
        urlopen.assert_not_called()
        row = self.publisher.db.conn.execute(
            "SELECT status, remote_post_id, reconciled_by, reconciliation_note "
            "FROM publication_attempts WHERE id = 1"
        ).fetchone()
        self.assertEqual(row["status"], "PUBLISHED_CONFIRMED")
        self.assertEqual(row["remote_post_id"], "remote-atom")
        self.assertEqual(row["reconciled_by"], "test-operator")
        self.assertEqual(row["reconciliation_note"], "Verified in Creator Center")
        self.assertEqual(quota.quota_status(reservation), "PUBLISHED_CONFIRMED")

    def test_failed_reconciliation_requires_explicit_no_post_acknowledgement(self):
        key = self.publisher._idempotency_key("ETC", "ambiguous content", [])
        digest = main.hashlib.sha256(b"ambiguous content").hexdigest()
        self.assertIsNone(self.publisher._begin_attempt(key, "ETC", digest))
        import scripts.reconcile_publications as reconcile
        base = {
            "action": "confirm-failed", "attempt_id": 1,
            "operator": "test-operator", "note": "No post found after manual review",
            "evidence": "manual-check:creator-center/search-2026-11-09",
            "share_link": "", "confirm_no_post_created": False,
        }
        with self.assertRaises(SystemExit):
            reconcile.reconcile(self.publisher.db.conn, type("Args", (), base)())
        base["confirm_no_post_created"] = True
        with patch("main._open_binance_publish_no_redirect") as urlopen:
            reconcile.reconcile(self.publisher.db.conn, type("Args", (), base)())
        urlopen.assert_not_called()
        row = self.publisher.db.conn.execute(
            "SELECT status FROM publication_attempts WHERE id = 1"
        ).fetchone()
        self.assertEqual(row["status"], "FAILED_CONFIRMED")

    def test_cannot_reconcile_failed_when_remote_post_id_is_known(self):
        key = self.publisher._idempotency_key("NEAR", "accepted content", [])
        digest = main.hashlib.sha256(b"accepted content").hexdigest()
        self.assertIsNone(self.publisher._begin_attempt(key, "NEAR", digest))
        self.publisher._finish_attempt(
            key, "PUBLICATION_UNKNOWN", post_id="known-remote-near"
        )
        import scripts.reconcile_publications as reconcile
        args = type("Args", (), {
            "action": "confirm-failed", "attempt_id": 1,
            "operator": "test-operator", "note": "attempted contradiction",
            "evidence": "manual-check", "share_link": "",
            "confirm_no_post_created": True,
        })()
        with self.assertRaisesRegex(ValueError, "remote post ID is already recorded"):
            reconcile.reconcile(self.publisher.db.conn, args)

    def test_terminal_publication_state_cannot_be_reconciled_again(self):
        key = self.publisher._idempotency_key("XLM", "already done", [])
        digest = main.hashlib.sha256(b"already done").hexdigest()
        self.assertIsNone(self.publisher._begin_attempt(key, "XLM", digest))
        self.publisher._finish_attempt(key, "FAILED_CONFIRMED", error="definitive rejection")
        import scripts.reconcile_publications as reconcile
        args = type("Args", (), {
            "action": "confirm-published", "attempt_id": 1,
            "operator": "test-operator", "note": "incorrect attempt",
            "evidence": "manual-check", "remote_post_id": "remote-conflict",
            "share_link": "",
        })()
        with self.assertRaisesRegex(ValueError, "terminal"):
            reconcile.reconcile(self.publisher.db.conn, args)

    def test_legacy_node_script_cannot_issue_direct_publication(self):
        script = (Path(__file__).resolve().parents[1] / "scripts" / "post-text.mjs").read_text(encoding="utf-8")
        self.assertIn("Direct publishing is disabled", script)
        self.assertNotIn("content/add", script)
        self.assertNotIn("fetch(", script)

    def test_jsonl_keeps_remote_post_identity(self):
        original = main._POST_HISTORY_FILE
        try:
            main._POST_HISTORY_FILE = str(Path(self.tmp.name) / "published_posts.jsonl")
            ok = main._append_post_record(
                "BTC", "market_move", "https://example.invalid/p/1",
                remote_post_id="remote-123",
            )
            self.assertTrue(ok)
            record = json.loads(Path(main._POST_HISTORY_FILE).read_text().strip())
            self.assertEqual(record["remote_post_id"], "remote-123")
        finally:
            main._POST_HISTORY_FILE = original


    def test_live_config_requires_explicit_publisher_enablement(self):
        config = replace(
            self.config, publisher_enabled=False,
            deepseek_api_key="test-deepseek-key-not-real",
            persistence_backend="postgresql", postgres_dsn="postgresql://test.invalid/test",
        )
        with self.assertRaisesRegex(ValueError, "PUBLISHER_ENABLED"):
            config.validate()

    def test_publisher_kill_switch_defaults_off(self):
        with patch.dict(os.environ, {}, clear=True):
            config = main.Config.from_env()
        self.assertFalse(config.publisher_enabled)

    def test_disabled_publisher_blocks_before_authorization_or_network(self):
        config = replace(self.config, publisher_enabled=False)
        publisher = main.PostPublisher(config)
        try:
            with patch("main._open_binance_publish_no_redirect") as urlopen:
                result = publisher.publish({"symbol": "BTC"}, "must not leave the process")
            self.assertEqual(result.status, "PUBLISHER_DISABLED")
            urlopen.assert_not_called()
        finally:
            publisher.db.close()


    def test_recent_persisted_post_after_authorization_blocks_before_network_post(self):
        coin, authorization, hashes = self._authorization(
            {"symbol": "BTC"}, "late duplicate policy content",
        )
        self.publisher.db.conn.execute(
            "INSERT INTO posts(created_at, coin_symbol, content) VALUES (?, ?, ?)",
            ((main.datetime.now(main.timezone.utc) - __import__("datetime").timedelta(hours=1)).isoformat(),
             "BTC", "another post inserted after authorization"),
        )
        self.publisher.db.conn.commit()
        with patch("main._open_binance_publish_no_redirect") as urlopen:
            result = self.publisher.publish(
                coin, "late duplicate policy content",
                authorization=authorization, image_hashes=hashes,
            )
        self.assertEqual(result.status, "FAILED_CONFIRMED")
        self.assertIn("RECENT_POST_COOLDOWN", result.error)
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
