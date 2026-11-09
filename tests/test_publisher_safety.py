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
