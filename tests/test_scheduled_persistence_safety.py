"""Regression tests for durable scheduled-run persistence and fail-closed quota checks."""
import os
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import main


class ScheduledPersistenceSafetyTests(unittest.TestCase):
    def test_quota_count_database_failure_blocks_instead_of_resetting_to_zero(self):
        class BrokenPostgresDatabase:
            def get_today_post_count(self):
                raise OSError("database unavailable")

        with self.assertRaisesRegex(RuntimeError, "daily publication count unavailable"):
            main._get_today_post_count(BrokenPostgresDatabase())

    def test_sqlite_quota_count_returns_persisted_utc_analytics_count(self):
        database = main.Database(":memory:")
        try:
            database.conn.execute(
                "INSERT INTO post_analytics(coin_symbol, created_at) VALUES (?, ?)",
                ("BTC", main.utc_now()),
            )
            self.assertEqual(main._get_today_post_count(database), 1)
        finally:
            database.close()

    def test_quota_count_rejects_invalid_database_result(self):
        class InvalidPostgresDatabase:
            def get_today_post_count(self):
                return -1

        with self.assertRaisesRegex(RuntimeError, "daily publication count unavailable"):
            main._get_today_post_count(InvalidPostgresDatabase())

    def test_live_github_actions_run_requires_postgresql_persistence(self):
        config = replace(
            main.CONFIG,
            dry_run=False,
            persistence_backend="sqlite",
            deepseek_api_key="configured-for-test",
            square_api_key="configured-for-test",
        )
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=False):
            with self.assertRaisesRegex(ValueError, "GitHub Actions live publishing requires PostgreSQL"):
                config.validate()

    def test_missing_provider_credentials_remain_the_first_live_mode_error(self):
        config = replace(
            main.CONFIG,
            dry_run=False,
            persistence_backend="sqlite",
            deepseek_api_key="",
            square_api_key="configured-for-test",
        )
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=False):
            with self.assertRaisesRegex(ValueError, "DEEPSEEK_API_KEY"):
                config.validate()

    def test_dry_run_github_actions_can_remain_sqlite_without_live_publishing(self):
        config = replace(main.CONFIG, dry_run=True, persistence_backend="sqlite")
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=False):
            config.validate()

    def test_scheduled_workflow_exposes_explicit_postgresql_backend_without_enabling_live_mode(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "run_bot.yml").read_text(encoding="utf-8")
        self.assertIn("PERSISTENCE_BACKEND: ${{ vars.PERSISTENCE_BACKEND || 'sqlite' }}", workflow)
        self.assertIn("POSTGRES_DSN: ${{ secrets.POSTGRES_DSN }}", workflow)
        self.assertIn('DRY_RUN: "1"', workflow)


    def test_sqlite_crashed_run_lease_requires_explicit_operator_recovery(self):
        import json
        import tempfile
        from layer1.foundation import AgentConfig, ConfigurationOrchestrator, RunLease

        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "lease-recovery.db")
            context = ConfigurationOrchestrator(
                AgentConfig(database_path=path),
            ).create_context({"case": "crash-recovery"})
            owner = RunLease(path)
            observer = RunLease(path)
            try:
                owner.acquire(context)
                active = observer.inspect_active()
                self.assertEqual(active["run_id"], context.run_id)
                self.assertEqual(active["status"], "RUNNING")

                with self.assertRaisesRegex(ValueError, "process termination confirmation"):
                    observer.recover_interrupted(
                        context.run_id, process_termination_confirmed=False,
                        evidence="scheduler job verified terminated", recovered_by="operator",
                    )
                with self.assertRaisesRegex(ValueError, "expected run ID"):
                    observer.recover_interrupted(
                        "another-run", process_termination_confirmed=True,
                        evidence="scheduler job verified terminated", recovered_by="operator",
                    )

                self.assertTrue(observer.recover_interrupted(
                    context.run_id, process_termination_confirmed=True,
                    evidence="scheduler job verified terminated", recovered_by="operator",
                ))
                self.assertIsNone(observer.inspect_active())
                row = observer.conn.execute(
                    "SELECT status, finished_at, summary_json FROM layer1_runs WHERE run_id=?",
                    (context.run_id,),
                ).fetchone()
                self.assertEqual(row[0], "INTERRUPTED")
                self.assertIsNotNone(row[1])
                summary = json.loads(row[2])
                self.assertEqual(summary["operator_recovery"]["recovered_by"], "operator")
                self.assertEqual(
                    summary["operator_recovery"]["evidence"],
                    "scheduler job verified terminated",
                )
            finally:
                observer.close()
                owner.close()

    def test_postgres_run_lease_recovery_requires_explicit_operator_confirmation(self):
        from layer1.publication_runtime import PostgresRunLease

        class FakeStore:
            def __init__(self):
                self.calls = []

            def inspect_active_run_lease(self):
                return None

            def acquire_run_lease(self, context):
                pass

            def finish_run_lease(self, run_id, status, summary):
                pass

            def recover_interrupted_run_lease(self, **kwargs):
                self.calls.append(kwargs)
                return True

        store = FakeStore()
        lease = PostgresRunLease(store)
        with self.assertRaisesRegex(ValueError, "process termination confirmation"):
            lease.recover_interrupted(
                "run-123", process_termination_confirmed=False,
                evidence="scheduler job verified terminated", recovered_by="operator",
            )
        self.assertTrue(lease.recover_interrupted(
            "run-123", process_termination_confirmed=True,
            evidence="scheduler job verified terminated", recovered_by="operator",
        ))
        self.assertEqual(len(store.calls), 1)
        self.assertEqual(store.calls[0]["expected_run_id"], "run-123")


if __name__ == "__main__":
    unittest.main()
