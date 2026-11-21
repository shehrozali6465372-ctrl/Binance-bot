"""Isolated PostgreSQL acceptance for the real scheduled run entrypoint.

The test intentionally exercises the current no-candidate fail-closed branch.
It does not invent an opportunity policy or authorize publication.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main

_DSN = os.environ.get("TEST_POSTGRES_DSN")


@unittest.skipUnless(_DSN, "TEST_POSTGRES_DSN is not configured")
class ScheduledPostgresFailClosedAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.postgres_test_support import validate_postgres_test_target
        validate_postgres_test_target(
            _DSN, os.environ.get("TEST_POSTGRES_ALLOWED_HOST", "").strip(),
        )
        from layer1.publication_postgres import apply_publication_postgres_migrations
        apply_publication_postgres_migrations(_DSN)

    def test_real_run_once_persists_no_candidate_outcome_without_publisher_side_effects(self):
        from layer1.publication_postgres import PostgresPublicationStore

        with tempfile.TemporaryDirectory(prefix="scheduled-pg-acceptance-") as directory:
            config = replace(
                main.CONFIG,
                persistence_backend="postgresql",
                postgres_dsn=_DSN,
                database_path=str(Path(directory) / "legacy-must-not-be-used.sqlite"),
                publish_log_path=str(Path(directory) / "publish.log"),
                post_interval=0,
                max_iterations=1,
                dry_run=True,
                publisher_enabled=False,
                image_required=False,
                save_research_packages=False,
            )
            config.validate()
            store = PostgresPublicationStore(_DSN)
            before_runs = store.conn.execute(
                "SELECT COUNT(*) AS count FROM layer1_runs"
            ).fetchone()["count"]
            before_attempts = store.conn.execute(
                "SELECT COUNT(*) AS count FROM publication_attempts"
            ).fetchone()["count"]
            before_reservations = store.conn.execute(
                "SELECT COUNT(*) AS count FROM publication_quota_reservations"
            ).fetchone()["count"]

            class FakePublisherDatabase:
                def get_today_post_count(self):
                    return 0

                def get_posted_hours_dict(self, hours=72):
                    return {}

            class NetworkDisabledPublisher:
                def __init__(self):
                    self.db = FakePublisherDatabase()
                    self.postgres_store = store
                    self.publish_calls = 0

                def publish(self, *args, **kwargs):
                    self.publish_calls += 1
                    raise AssertionError("publisher transport must never be reached in this test")

            class EmptyScanner:
                def _universe(self):
                    return []

            publisher = NetworkDisabledPublisher()
            run_id = None
            try:
                with (
                    patch.object(main, "CONFIG", config),
                    patch.object(main, "_verify_persistence_integrity", return_value=True),
                    patch.object(main, "_retry_pending_push"),
                    patch.object(main, "_load_post_history", return_value={}),
                    patch("urllib.request.urlopen", side_effect=AssertionError("network access forbidden")),
                    patch.object(main, "http_get_json", side_effect=AssertionError("provider HTTP forbidden")),
                ):
                    outcome = main.run_once(
                        config, EmptyScanner(), SimpleNamespace(),
                        SimpleNamespace(), SimpleNamespace(), publisher, set(),
                        hot_search_engine=SimpleNamespace(get_trending=lambda **_: []),
                    )

                self.assertFalse(outcome)
                self.assertEqual(publisher.publish_calls, 0)
                self.assertFalse(Path(config.database_path).exists())
                self.assertFalse(Path(config.publish_log_path).exists())

                after_attempts = store.conn.execute(
                    "SELECT COUNT(*) AS count FROM publication_attempts"
                ).fetchone()["count"]
                after_reservations = store.conn.execute(
                    "SELECT COUNT(*) AS count FROM publication_quota_reservations"
                ).fetchone()["count"]
                self.assertEqual(after_attempts, before_attempts)
                self.assertEqual(after_reservations, before_reservations)

                run = store.conn.execute(
                    "SELECT run_id, status, summary_json FROM layer1_runs "
                    "ORDER BY started_at DESC LIMIT 1"
                ).fetchone()
                run_id = run["run_id"]
                self.assertEqual(run["status"], "NO_CANDIDATE_OR_BLOCKED")
                self.assertEqual(run["summary_json"]["cycle_result"], "NO_CANDIDATE_OR_BLOCKED")
                lease = store.conn.execute(
                    "SELECT COUNT(*) AS count FROM layer1_run_lease WHERE lease_name='agent'"
                ).fetchone()["count"]
                self.assertEqual(lease, 0, "completed run must release the singleton lease")
                self.assertEqual(
                    store.conn.execute(
                        "SELECT COUNT(*) AS count FROM layer1_runs WHERE run_id=%s", (run_id,),
                    ).fetchone()["count"],
                    before_runs + 1,
                )
            finally:
                if run_id:
                    store.conn.execute("DELETE FROM layer1_runs WHERE run_id=%s", (run_id,))
                store.close()


if __name__ == "__main__":
    unittest.main()
