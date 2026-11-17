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
            square_api_key="test-key-not-real",
            http_timeout_seconds=1,
        )
        self.publisher = main.PostPublisher(self.config)

    def tearDown(self):
        self.publisher.db.close()
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def test_dry_run_never_posts(self):
        dry = main.PostPublisher(replace(self.config, dry_run=True))
        try:
            with patch("main.urllib.request.urlopen") as urlopen:
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
        with patch("main.urllib.request.urlopen", return_value=response) as urlopen:
            first = self.publisher.publish({"symbol": "BTC"}, "same educational content")
            second = self.publisher.publish({"symbol": "BTC"}, "same educational content")

        self.assertEqual(first.status, "PUBLISHED_CONFIRMED")
        self.assertEqual(first.post_id, "remote-123")
        self.assertTrue(first.confirmed)
        self.assertEqual(second.status, "DUPLICATE_BLOCKED")
        self.assertFalse(second.confirmed)
        self.assertEqual(urlopen.call_count, 1)

    def test_ambiguous_timeout_blocks_changed_content_for_same_symbol(self):
        with patch("main.urllib.request.urlopen", side_effect=URLError("socket timeout")) as urlopen:
            first = self.publisher.publish({"symbol": "ETH"}, "first generated text")
            second = self.publisher.publish({"symbol": "ETH"}, "different regenerated text")

        self.assertEqual(first.status, "PUBLICATION_UNKNOWN")
        self.assertEqual(second.status, "PUBLICATION_UNKNOWN")
        self.assertEqual(urlopen.call_count, 1)

    def test_definitive_client_rejection_is_not_retried(self):
        response = FakeResponse({"code": "400001", "message": "Rejected"})
        from urllib.error import HTTPError
        error = HTTPError("https://example.invalid", 400, "Bad Request", {}, io.BytesIO(b""))
        with patch("main.urllib.request.urlopen", side_effect=error) as urlopen:
            first = self.publisher.publish({"symbol": "SOL"}, "rejected content")
            second = self.publisher.publish({"symbol": "SOL"}, "rejected content")

        self.assertEqual(first.status, "FAILED_CONFIRMED")
        self.assertEqual(second.status, "DUPLICATE_BLOCKED")
        self.assertEqual(urlopen.call_count, 1)

    def test_remote_acceptance_followed_by_local_persistence_failure_is_not_retried(self):
        response = FakeResponse({
            "code": "000000",
            "data": {"id": "remote-after-db-error", "shareLink": "https://example.invalid/post/remote-after-db-error"},
        })
        with patch("main.urllib.request.urlopen", return_value=response) as urlopen:
            with patch.object(self.publisher.db, "save_post", side_effect=sqlite3.OperationalError("disk full")):
                first = self.publisher.publish({"symbol": "XRP"}, "first content")
            second = self.publisher.publish({"symbol": "XRP"}, "regenerated content")

        self.assertEqual(first.status, "PUBLICATION_UNKNOWN")
        self.assertEqual(second.status, "PUBLICATION_UNKNOWN")
        self.assertEqual(urlopen.call_count, 1)
        row = self.publisher.db.conn.execute(
            "SELECT status, remote_post_id, share_link FROM publication_attempts WHERE coin_symbol = 'XRP'"
        ).fetchone()
        self.assertEqual(row["status"], "PUBLICATION_UNKNOWN")
        self.assertEqual(row["remote_post_id"], "remote-after-db-error")
        self.assertEqual(row["share_link"], "https://example.invalid/post/remote-after-db-error")

    def test_success_response_without_remote_id_is_unknown_and_not_retried(self):
        response = FakeResponse({"code": "000000", "data": {"shareLink": "https://example.invalid/no-id"}})
        with patch("main.urllib.request.urlopen", return_value=response) as urlopen:
            first = self.publisher.publish({"symbol": "ADA"}, "content without remote identity")
            second = self.publisher.publish({"symbol": "ADA"}, "regenerated content")

        self.assertEqual(first.status, "PUBLICATION_UNKNOWN")
        self.assertEqual(second.status, "PUBLICATION_UNKNOWN")
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
            with patch("main.urllib.request.urlopen") as urlopen:
                result = second.publish({"symbol": "LINK"}, "different regenerated content")
            self.assertEqual(result.status, "PUBLICATION_UNKNOWN")
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

    def test_operator_reconciliation_confirms_known_remote_id_without_network(self):
        key = self.publisher._idempotency_key("ATOM", "pending content", [])
        digest = main.hashlib.sha256(b"pending content").hexdigest()
        self.assertIsNone(self.publisher._begin_attempt(key, "ATOM", digest))
        import scripts.reconcile_publications as reconcile
        args = type("Args", (), {
            "action": "confirm-published", "attempt_id": 1,
            "operator": "test-operator", "note": "Verified in Creator Center",
            "evidence": "manual-check:creator-center/post/remote-atom",
            "remote_post_id": "remote-atom",
            "share_link": "https://www.binance.com/square/post/remote-atom",
        })()
        with patch("main.urllib.request.urlopen") as urlopen:
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
        with patch("main.urllib.request.urlopen") as urlopen:
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


if __name__ == "__main__":
    unittest.main()
