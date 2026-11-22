import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
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

    def read(self, size=-1):
        return self.payload if size < 0 else self.payload[:size]


class PublisherSafetyTests(unittest.TestCase):
    def test_binance_publish_response_reader_is_bounded(self):
        read_sizes = []

        class OversizedResponse:
            def read(self, size=-1):
                read_sizes.append(size)
                return b"x" * size

        with self.assertRaisesRegex(ValueError, "Binance response exceeds the 1048576-byte limit"):
            main._read_bounded_binance_response(OversizedResponse())
        self.assertEqual(read_sizes, [1024 * 1024 + 1])

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
        self.publisher.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS layer1_event_lifecycle (
                event_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, state TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'other'
            )
        """)
        if event_state != "NO_EVENT":
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

    def test_oversized_binance_response_remains_unknown_and_non_retryable(self):
        class OversizedResponse:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, size=-1):
                return b"x" * size

        with patch("main._open_binance_publish_no_redirect", return_value=OversizedResponse()) as opener:
            result = self._publish({"symbol": "BND"}, "bounded response body test")
        self.assertEqual(result.status, "PUBLICATION_UNKNOWN")
        opener.assert_called_once()
        row = self.publisher.db.conn.execute(
            "SELECT status FROM publication_attempts WHERE coin_symbol=?", ("BND",),
        ).fetchone()
        self.assertEqual(row["status"], "PUBLICATION_UNKNOWN")
        retry = self._publish({"symbol": "BND"}, "different regenerated content")
        self.assertNotEqual(retry.status, "PUBLISHED_CONFIRMED")
        opener.assert_called_once()

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
        self.assertIn("EVENT_LIFECYCLE_CHANGED", result.error)
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
                self.in_submission_guard = False

            def begin_authorized_attempt(self, **kwargs):
                self.calls.append(("begin", kwargs))
                return None

            @contextmanager
            def authorized_submission_guard(self, **kwargs):
                self.calls.append(("preflight", kwargs))
                self.in_submission_guard = True
                try:
                    yield
                finally:
                    self.in_submission_guard = False

            def finish_authorized_attempt(self, key, status, **kwargs):
                self.calls.append(("finish", key, status, kwargs))

        store = FakePostgresStore()
        publisher = main.PostPublisher(self.config, postgres_store=store)
        response = FakeResponse({
            "code": "000000",
            "data": {"id": "pg-remote-1", "shareLink": "https://example.invalid/pg-remote-1"},
        })
        try:
            def guarded_open(*args, **kwargs):
                self.assertTrue(store.in_submission_guard)
                return response
            with patch("main._open_binance_publish_no_redirect", side_effect=guarded_open) as urlopen:
                result = publisher.publish(
                    coin, "postgres opt-in publisher content",
                    authorization=authorization, image_hashes=hashes,
                )
            self.assertEqual(result.status, "PUBLISHED_CONFIRMED")
            self.assertEqual(result.post_id, "pg-remote-1")
            self.assertEqual(urlopen.call_count, 1)
            self.assertFalse(store.in_submission_guard)
            self.assertEqual([call[0] for call in store.calls],
                             ["begin", "preflight", "finish", "finish"])
            self.assertEqual(store.calls[-2][2], "PUBLICATION_UNKNOWN")
            self.assertEqual(store.calls[-1][2], "PUBLISHED_CONFIRMED")
            self.assertEqual(publisher.db.conn.execute(
                "SELECT COUNT(*) FROM publication_attempts"
            ).fetchone()[0], 0)
        finally:
            publisher.db.close()


    def test_postgres_confirmed_publication_is_not_downgraded_by_local_history_write_failure(self):
        coin, authorization, hashes = self._authorization(
            {"symbol": "BTC"}, "postgres local history failure content",
        )

        class FakePostgresStore:
            def __init__(self):
                self.calls = []

            def begin_authorized_attempt(self, **kwargs):
                return None

            @contextmanager
            def authorized_submission_guard(self, **kwargs):
                self.calls.append(("preflight", kwargs))
                self.in_submission_guard = True
                try:
                    yield
                finally:
                    self.in_submission_guard = False

            def finish_authorized_attempt(self, key, status, **kwargs):
                self.calls.append(("finish", key, status, kwargs))

        store = FakePostgresStore()
        publisher = main.PostPublisher(self.config, postgres_store=store)
        publisher._save_locally = lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError("local history disk unavailable")
        )
        response = FakeResponse({
            "code": "000000",
            "data": {"id": "pg-remote-history-1", "shareLink": "https://example.invalid/pg-remote-history-1"},
        })
        try:
            with patch("main._open_binance_publish_no_redirect", return_value=response) as urlopen:
                result = publisher.publish(
                    coin, "postgres local history failure content",
                    authorization=authorization, image_hashes=hashes,
                )
            self.assertEqual(result.status, "PUBLISHED_CONFIRMED")
            self.assertEqual(result.post_id, "pg-remote-history-1")
            self.assertEqual(
                [call[2] for call in store.calls if call[0] == "finish"],
                ["PUBLICATION_UNKNOWN", "PUBLISHED_CONFIRMED"],
            )
            urlopen.assert_called_once()
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



    def test_postgres_duplicate_ledger_query_error_propagates_fail_closed(self):
        from contextlib import nullcontext
        from layer1.publication_postgres import PostgresPublicationStore

        class FakeConnection:
            def transaction(self):
                return nullcontext()

        store = object.__new__(PostgresPublicationStore)
        store.conn = FakeConnection()

        def query_failure(**kwargs):
            raise RuntimeError("duplicate ledger query failed")

        store._duplicate_policy_reasons_in_transaction = query_failure
        with self.assertRaisesRegex(RuntimeError, "duplicate ledger query failed"):
            store.validate_persisted_duplicate_policy(
                symbol="BTC", asset_id="coingecko:bitcoin", event_id="none",
                event_state="NO_EVENT", content_hash="a" * 64,
                quota_reservation_id="quota:test",
            )

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

            @contextmanager
            def authorized_submission_guard(self, **kwargs):
                self.calls.append(("preflight", kwargs))
                raise RuntimeError("DUPLICATE_LEDGER_UNAVAILABLE")
                yield

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


    def test_sqlite_confirmed_publication_is_not_downgraded_by_local_history_write_failure(self):
        coin, authorization, hashes = self._authorization(
            {"symbol": "LTC"}, "sqlite local history failure content",
        )
        self.publisher._save_locally = lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError("local history disk unavailable")
        )
        response = FakeResponse({
            "code": "000000",
            "data": {"id": "sqlite-remote-history-1", "shareLink": "https://example.invalid/sqlite-remote-history-1"},
        })
        with patch("main._open_binance_publish_no_redirect", return_value=response) as urlopen:
            result = self.publisher.publish(
                coin, "sqlite local history failure content",
                authorization=authorization, image_hashes=hashes,
            )
        self.assertEqual(result.status, "PUBLISHED_CONFIRMED")
        self.assertEqual(result.post_id, "sqlite-remote-history-1")
        row = self.publisher.db.conn.execute(
            "SELECT status, remote_post_id FROM publication_attempts WHERE coin_symbol='LTC'"
        ).fetchone()
        self.assertEqual(row["status"], "PUBLISHED_CONFIRMED")
        self.assertEqual(row["remote_post_id"], "sqlite-remote-history-1")
        urlopen.assert_called_once()


    def test_sqlite_attempt_and_quota_are_finalized_atomically_after_remote_confirmation(self):
        from layer1.publication_authorization import PublicationAuthorizationEngine

        coin, authorization, hashes = self._authorization(
            {"symbol": "DOGE"}, "sqlite quota finalization failure content",
        )
        original = PublicationAuthorizationEngine.mark_quota_status
        final_status_calls = []

        def fail_only_final_status(engine, reservation_id, status):
            if status == "PUBLISHED_CONFIRMED":
                final_status_calls.append(status)
                raise sqlite3.OperationalError("quota ledger temporarily unavailable")
            return original(engine, reservation_id, status)

        response = FakeResponse({
            "code": "000000",
            "data": {"id": "sqlite-remote-quota-1", "shareLink": "https://example.invalid/sqlite-remote-quota-1"},
        })
        with patch.object(
            PublicationAuthorizationEngine, "mark_quota_status",
            new=fail_only_final_status,
        ):
            with patch("main._open_binance_publish_no_redirect", return_value=response) as urlopen:
                result = self.publisher.publish(
                    coin, "sqlite quota finalization failure content",
                    authorization=authorization, image_hashes=hashes,
                )
        self.assertEqual(result.status, "PUBLISHED_CONFIRMED")
        self.assertEqual(result.post_id, "sqlite-remote-quota-1")
        attempt = self.publisher.db.conn.execute(
            "SELECT status FROM publication_attempts WHERE coin_symbol='DOGE'"
        ).fetchone()
        reservation = self.publisher.db.conn.execute(
            "SELECT status FROM publication_quota_reservations WHERE reservation_id=?",
            (authorization.quota_reservation_id,),
        ).fetchone()
        self.assertEqual(attempt["status"], "PUBLISHED_CONFIRMED")
        self.assertEqual(reservation["status"], "PUBLISHED_CONFIRMED")
        self.assertEqual(final_status_calls, [])
        urlopen.assert_called_once()

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
        legacy.execute("""
            CREATE TABLE publication_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idempotency_key TEXT NOT NULL UNIQUE,
                coin_symbol TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                remote_post_id TEXT UNIQUE,
                share_link TEXT,
                http_status INTEGER,
                error TEXT,
                reconciliation_note TEXT,
                reconciliation_evidence TEXT,
                reconciled_by TEXT,
                reconciled_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        legacy.execute(
            "INSERT INTO publication_attempts "
            "(idempotency_key,coin_symbol,content_hash,status,created_at,updated_at) "
            "VALUES ('legacy-attempt','BTC','legacy-hash','SUBMITTING','2026-01-01','2026-01-01')"
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
            attempt_columns = {
                item["name"] for item in migrated.conn.execute(
                    "PRAGMA table_info(publication_attempts)"
                ).fetchall()
            }
            self.assertIn("authorization_id", attempt_columns)
            legacy_attempt = migrated.conn.execute(
                "SELECT status,authorization_id FROM publication_attempts WHERE idempotency_key='legacy-attempt'"
            ).fetchone()
            self.assertEqual(legacy_attempt["status"], "SUBMITTING")
            self.assertIsNone(legacy_attempt["authorization_id"])
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
        self.publisher.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS layer1_event_lifecycle (
                event_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, state TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'other'
            )
        """)
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



    def test_sqlite_pre_submit_duplicate_ledger_failure_is_known_not_submitted(self):
        from layer1.publication_authorization import PublicationAuthorizationEngine

        coin, authorization, hashes = self._authorization(
            {"symbol": "AVAX"}, "sqlite pre-submit ledger failure content",
        )
        response = FakeResponse({
            "code": "000000",
            "data": {"id": "should-never-be-submitted", "shareLink": "https://example.invalid/should-never-be-submitted"},
        })
        with patch.object(
            PublicationAuthorizationEngine, "validate_persisted_duplicate_policy",
            side_effect=[(), sqlite3.OperationalError("duplicate ledger unavailable")],
        ):
            with patch("main._open_binance_publish_no_redirect", return_value=response) as urlopen:
                result = self.publisher.publish(
                    coin, "sqlite pre-submit ledger failure content",
                    authorization=authorization, image_hashes=hashes,
                )
        self.assertEqual(result.status, "FAILED_CONFIRMED")
        self.assertIn("no Binance request was sent", result.error)
        urlopen.assert_not_called()
        attempt = self.publisher.db.conn.execute(
            "SELECT status FROM publication_attempts WHERE coin_symbol='AVAX'"
        ).fetchone()
        reservation = self.publisher.db.conn.execute(
            "SELECT status FROM publication_quota_reservations WHERE reservation_id=?",
            (authorization.quota_reservation_id,),
        ).fetchone()
        self.assertEqual(attempt["status"], "FAILED_CONFIRMED")
        self.assertEqual(reservation["status"], "FAILED_CONFIRMED")

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


    def _attempt_with_bound_quota(self, symbol, content):
        from layer1.publication_authorization import PublicationAuthorizationEngine
        coin, authorization, hashes = self._authorization({"symbol": symbol}, content)
        key = self.publisher._idempotency_key(symbol, content, [])
        digest = main.hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.assertIsNone(self.publisher._begin_attempt(key, symbol, digest))
        attempt_id = self.publisher.db.conn.execute(
            "SELECT id FROM publication_attempts WHERE idempotency_key=?", (key,),
        ).fetchone()["id"]
        engine = PublicationAuthorizationEngine(self.publisher.db.conn)
        engine.bind_attempt(authorization.quota_reservation_id, attempt_id)
        engine.mark_quota_status(authorization.quota_reservation_id, "SUBMITTING")
        return key, authorization

    def test_authorization_engine_backfills_legacy_bound_attempt_identity(self):
        from layer1.publication_authorization import PublicationAuthorizationEngine
        key, authorization = self._attempt_with_bound_quota(
            "BACKFILL", "backfill legacy attempt authorization identity",
        )
        self.publisher.db.conn.execute(
            "UPDATE publication_attempts SET authorization_id=NULL WHERE idempotency_key=?",
            (key,),
        )
        self.publisher.db.conn.commit()
        PublicationAuthorizationEngine(self.publisher.db.conn)
        row = self.publisher.db.conn.execute(
            "SELECT authorization_id FROM publication_attempts WHERE idempotency_key=?",
            (key,),
        ).fetchone()
        self.assertEqual(row["authorization_id"], authorization.authorization_id)
        self.publisher._finish_attempt(key, "PUBLISHED_CONFIRMED", post_id="synthetic-backfill")
        attempt = self.publisher.db.conn.execute(
            "SELECT status FROM publication_attempts WHERE idempotency_key=?", (key,),
        ).fetchone()
        quota = self.publisher.db.conn.execute(
            "SELECT status FROM publication_quota_reservations WHERE reservation_id=?",
            (authorization.quota_reservation_id,),
        ).fetchone()
        self.assertEqual(attempt["status"], "PUBLISHED_CONFIRMED")
        self.assertEqual(quota["status"], "PUBLISHED_CONFIRMED")

    def test_finish_attempt_rolls_back_when_bound_quota_reservation_is_missing(self):
        key, authorization = self._attempt_with_bound_quota("MISS", "missing bound quota")
        self.publisher.db.conn.execute(
            "DELETE FROM publication_quota_reservations WHERE reservation_id=?",
            (authorization.quota_reservation_id,),
        )
        self.publisher.db.conn.commit()
        with self.assertRaisesRegex(RuntimeError, "exactly one bound quota reservation"):
            self.publisher._finish_attempt(key, "PUBLISHED_CONFIRMED", post_id="synthetic")
        row = self.publisher.db.conn.execute(
            "SELECT status FROM publication_attempts WHERE idempotency_key=?", (key,),
        ).fetchone()
        self.assertEqual(row["status"], "SUBMITTING")

    def test_finish_attempt_rolls_back_when_bound_quota_reservation_was_released(self):
        key, authorization = self._attempt_with_bound_quota("REL", "released bound quota")
        self.publisher.db.conn.execute(
            "UPDATE publication_quota_reservations SET status='RELEASED' WHERE reservation_id=?",
            (authorization.quota_reservation_id,),
        )
        self.publisher.db.conn.commit()
        with self.assertRaisesRegex(RuntimeError, "quota reservation state is inconsistent"):
            self.publisher._finish_attempt(key, "PUBLISHED_CONFIRMED", post_id="synthetic")
        row = self.publisher.db.conn.execute(
            "SELECT status FROM publication_attempts WHERE idempotency_key=?", (key,),
        ).fetchone()
        self.assertEqual(row["status"], "SUBMITTING")

    def test_finish_attempt_rejects_quota_authorization_identity_mismatch(self):
        key, authorization = self._attempt_with_bound_quota("IDENT", "wrong quota identity")
        self.publisher.db.conn.execute(
            "UPDATE publication_quota_reservations SET authorization_id='forged-authorization' "
            "WHERE reservation_id=?", (authorization.quota_reservation_id,),
        )
        self.publisher.db.conn.commit()
        with self.assertRaisesRegex(RuntimeError, "authorization identity does not match"):
            self.publisher._finish_attempt(key, "PUBLISHED_CONFIRMED", post_id="synthetic")
        row = self.publisher.db.conn.execute(
            "SELECT status FROM publication_attempts WHERE idempotency_key=?", (key,),
        ).fetchone()
        self.assertEqual(row["status"], "SUBMITTING")

    def test_finish_attempt_rejects_illegal_bound_quota_source_state(self):
        key, authorization = self._attempt_with_bound_quota("STATE", "illegal quota state")
        self.publisher.db.conn.execute(
            "UPDATE publication_quota_reservations SET status='RESERVED' WHERE reservation_id=?",
            (authorization.quota_reservation_id,),
        )
        self.publisher.db.conn.commit()
        with self.assertRaisesRegex(RuntimeError, "quota reservation state is inconsistent"):
            self.publisher._finish_attempt(key, "PUBLISHED_CONFIRMED", post_id="synthetic")
        row = self.publisher.db.conn.execute(
            "SELECT status FROM publication_attempts WHERE idempotency_key=?", (key,),
        ).fetchone()
        self.assertEqual(row["status"], "SUBMITTING")

    def test_sqlite_event_withdrawal_before_final_gate_blocks_network_post(self):
        coin, authorization, hashes = self._authorization(
            {"symbol": "WITHDRAW"}, "event withdrawal before final gate",
            event_state="CONFIRMED",
        )
        self.publisher.db.conn.execute(
            "UPDATE layer1_event_lifecycle SET state='WITHDRAWN' WHERE event_id=?",
            (authorization.event_id,),
        )
        self.publisher.db.conn.commit()
        with patch("main._open_binance_publish_no_redirect") as transport:
            result = self.publisher.publish(
                coin, "event withdrawal before final gate",
                authorization=authorization, image_hashes=hashes,
            )
        self.assertEqual(result.status, "FAILED_CONFIRMED")
        self.assertIn("EVENT_LIFECYCLE_CHANGED", result.error)
        transport.assert_not_called()

    def test_sqlite_no_event_insertion_before_final_gate_blocks_network_post(self):
        coin, authorization, hashes = self._authorization(
            {"symbol": "NOEVENT"}, "no-event insertion before final gate",
        )
        self.publisher.db.conn.execute(
            "INSERT INTO layer1_event_lifecycle(event_id,asset_id,state,event_type) "
            "VALUES (?, ?, 'CONFIRMED', 'listing')",
            (authorization.event_id, authorization.asset_id),
        )
        self.publisher.db.conn.commit()
        with patch("main._open_binance_publish_no_redirect") as transport:
            result = self.publisher.publish(
                coin, "no-event insertion before final gate",
                authorization=authorization, image_hashes=hashes,
            )
        self.assertEqual(result.status, "FAILED_CONFIRMED")
        self.assertIn("EVENT_LIFECYCLE_STATE_MISMATCH", result.error)
        transport.assert_not_called()

    def test_publish_does_not_escape_when_quota_binding_fails(self):
        from layer1.publication_authorization import PublicationAuthorizationEngine
        coin, authorization, hashes = self._authorization(
            {"symbol": "BINDFAIL"}, "quota bind failure stays fenced",
        )
        with patch.object(
            PublicationAuthorizationEngine, "bind_attempt",
            side_effect=ValueError("synthetic binding mismatch"),
        ):
            with patch("main._open_binance_publish_no_redirect") as transport:
                result = self.publisher.publish(
                    coin, "quota bind failure stays fenced",
                    authorization=authorization, image_hashes=hashes,
                )
        self.assertEqual(result.status, "FAILED_CONFIRMED")
        self.assertIn("no request was sent", result.error)
        transport.assert_not_called()
        attempt = self.publisher.db.conn.execute(
            "SELECT status FROM publication_attempts WHERE coin_symbol='BINDFAIL'"
        ).fetchone()
        reservation = self.publisher.db.conn.execute(
            "SELECT status,attempt_id FROM publication_quota_reservations WHERE reservation_id=?",
            (authorization.quota_reservation_id,),
        ).fetchone()
        self.assertEqual(attempt["status"], "SUBMITTING")
        self.assertEqual(reservation["status"], "RELEASED")
        self.assertIsNone(reservation["attempt_id"])

    def test_quota_attempt_binding_rejects_symbol_mismatch(self):
        from layer1.publication_authorization import PublicationAuthorizationEngine
        coin, authorization, hashes = self._authorization(
            {"symbol": "QUOTA"}, "quota symbol mismatch",
        )
        key = self.publisher._idempotency_key("OTHER", "different symbol", [])
        digest = main.hashlib.sha256(b"different symbol").hexdigest()
        self.assertIsNone(self.publisher._begin_attempt(key, "OTHER", digest))
        attempt_id = self.publisher.db.conn.execute(
            "SELECT id FROM publication_attempts WHERE idempotency_key=?", (key,),
        ).fetchone()["id"]
        engine = PublicationAuthorizationEngine(self.publisher.db.conn)
        with self.assertRaisesRegex(ValueError, "cannot be bound"):
            engine.bind_attempt(authorization.quota_reservation_id, attempt_id)
        reservation = self.publisher.db.conn.execute(
            "SELECT attempt_id,status FROM publication_quota_reservations WHERE reservation_id=?",
            (authorization.quota_reservation_id,),
        ).fetchone()
        self.assertIsNone(reservation["attempt_id"])
        self.assertEqual(reservation["status"], "RESERVED")

    def _publish_with_second_connection_write_at_transport(self, *, mutation):
        coin, authorization, hashes = self._authorization(
            {"symbol": "FENCE"}, "sqlite submission fence content " + mutation,
            event_state="CONFIRMED" if mutation == "withdraw" else "NO_EVENT",
        )
        second = sqlite3.connect(self.db_path, timeout=0.05)
        write_errors = []
        write_completed = []

        def competing_write(request, *, timeout):
            try:
                if mutation == "withdraw":
                    second.execute(
                        "UPDATE layer1_event_lifecycle SET state='WITHDRAWN' WHERE event_id=?",
                        (authorization.event_id,),
                    )
                elif mutation == "no_event_insert":
                    second.execute(
                        "INSERT INTO layer1_event_lifecycle(event_id,asset_id,state,event_type) "
                        "VALUES (?, ?, 'CONFIRMED', 'listing')",
                        (authorization.event_id, authorization.asset_id),
                    )
                elif mutation == "recent_post":
                    second.execute(
                        "INSERT INTO posts(created_at,coin_symbol,content) VALUES (?, ?, ?)",
                        (main.utc_now(), "FENCE", "competing recent post"),
                    )
                elif mutation == "competing_reservation":
                    second.execute(
                        "INSERT INTO publication_quota_reservations "
                        "(reservation_id,day_utc,symbol,status,created_at,updated_at) "
                        "VALUES ('competing-reservation','2026-11-22','FENCE','RESERVED',?,?)",
                        (main.utc_now(), main.utc_now()),
                    )
                second.commit()
                write_completed.append(True)
            except sqlite3.OperationalError as exc:
                write_errors.append(str(exc))
                second.rollback()
            return FakeResponse({
                "code": "000000",
                "data": {"id": "synthetic-fenced-post", "shareLink": "https://example.invalid/synthetic-fenced-post"},
            })

        try:
            with patch("main._open_binance_publish_no_redirect", side_effect=competing_write) as transport:
                result = self.publisher.publish(
                    coin, "sqlite submission fence content " + mutation,
                    authorization=authorization, image_hashes=hashes,
                )
            self.assertEqual(result.status, "PUBLISHED_CONFIRMED", result.error)
            transport.assert_called_once()
            self.assertEqual(write_completed, [], "concurrent SQLite writer must not cross the submission fence")
            self.assertEqual(len(write_errors), 1)
            self.assertIn("locked", write_errors[0].lower())
            if mutation == "withdraw":
                state = self.publisher.db.conn.execute(
                    "SELECT state FROM layer1_event_lifecycle WHERE event_id=?",
                    (authorization.event_id,),
                ).fetchone()[0]
                self.assertEqual(state, "CONFIRMED")
            elif mutation == "no_event_insert":
                event = self.publisher.db.conn.execute(
                    "SELECT 1 FROM layer1_event_lifecycle WHERE event_id=?",
                    (authorization.event_id,),
                ).fetchone()
                self.assertIsNone(event)
            elif mutation == "recent_post":
                count = self.publisher.db.conn.execute(
                    "SELECT COUNT(*) FROM posts WHERE coin_symbol='FENCE' AND content='competing recent post'"
                ).fetchone()[0]
                self.assertEqual(count, 0)
            elif mutation == "competing_reservation":
                row = self.publisher.db.conn.execute(
                    "SELECT 1 FROM publication_quota_reservations WHERE reservation_id='competing-reservation'"
                ).fetchone()
                self.assertIsNone(row)
        finally:
            second.close()

    def test_sqlite_submission_guard_caps_socket_timeout_at_fifteen_seconds(self):
        coin, authorization, hashes = self._authorization(
            {"symbol": "TIMEOUTCAP"}, "sqlite bounded submission timeout",
        )
        original_config = self.publisher.config
        self.publisher.config = replace(original_config, http_timeout_seconds=45)
        observed_timeouts = []

        def transport(request, *, timeout):
            observed_timeouts.append(timeout)
            return FakeResponse({
                "code": "000000",
                "data": {"id": "synthetic-timeout-cap", "shareLink": "https://example.invalid/synthetic-timeout-cap"},
            })

        try:
            with patch("main._open_binance_publish_no_redirect", side_effect=transport):
                result = self.publisher.publish(
                    coin, "sqlite bounded submission timeout",
                    authorization=authorization, image_hashes=hashes,
                )
            self.assertEqual(result.status, "PUBLISHED_CONFIRMED", result.error)
            self.assertEqual(observed_timeouts, [15])
        finally:
            self.publisher.config = original_config

    def test_sqlite_submission_guard_releases_before_response_body_read(self):
        coin, authorization, hashes = self._authorization(
            {"symbol": "BODYREAD"}, "sqlite response body outside write fence",
            event_state="CONFIRMED",
        )
        second = sqlite3.connect(self.db_path, timeout=0.05)
        writes = []

        class UpdatingResponse(FakeResponse):
            def read(inner_self, size=-1):
                second.execute(
                    "UPDATE layer1_event_lifecycle SET state='WITHDRAWN' WHERE event_id=?",
                    (authorization.event_id,),
                )
                second.commit()
                writes.append(True)
                return super(UpdatingResponse, inner_self).read(size)

        try:
            response = UpdatingResponse({
                "code": "000000",
                "data": {"id": "synthetic-body-read-post", "shareLink": "https://example.invalid/synthetic-body-read-post"},
            })
            with patch("main._open_binance_publish_no_redirect", return_value=response) as transport:
                result = self.publisher.publish(
                    coin, "sqlite response body outside write fence",
                    authorization=authorization, image_hashes=hashes,
                )
            self.assertEqual(result.status, "PUBLISHED_CONFIRMED", result.error)
            transport.assert_called_once()
            self.assertEqual(writes, [True])
            state = self.publisher.db.conn.execute(
                "SELECT state FROM layer1_event_lifecycle WHERE event_id=?",
                (authorization.event_id,),
            ).fetchone()[0]
            self.assertEqual(state, "WITHDRAWN")
        finally:
            second.close()

    def test_sqlite_submission_guard_serializes_event_withdrawal_through_transport(self):
        self._publish_with_second_connection_write_at_transport(mutation="withdraw")

    def test_sqlite_submission_guard_serializes_no_event_insertion_through_transport(self):
        self._publish_with_second_connection_write_at_transport(mutation="no_event_insert")

    def test_sqlite_submission_guard_serializes_recent_post_insertion_through_transport(self):
        self._publish_with_second_connection_write_at_transport(mutation="recent_post")

    def test_sqlite_submission_guard_serializes_competing_quota_reservation_through_transport(self):
        self._publish_with_second_connection_write_at_transport(mutation="competing_reservation")


if __name__ == "__main__":
    unittest.main()
