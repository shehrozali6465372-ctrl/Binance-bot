"""Regression tests for durable scheduled-run persistence and fail-closed quota checks."""
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import main


class ScheduledPersistenceSafetyTests(unittest.TestCase):
    def test_private_layer1_runtime_objects_are_excluded_from_durable_run_summary(self):
        private_registry = object()
        summary = {
            "observations": 2,
            "claim_verification_summary": {"claim_count": 3},
            "_claim_registry": private_registry,
        }

        persisted = main._layer1_run_summary_for_persistence(summary)

        self.assertEqual(
            persisted,
            {
                "observations": 2,
                "claim_verification_summary": {"claim_count": 3},
            },
        )
        self.assertNotIn("_claim_registry", persisted)

    def test_postgres_authorization_connection_loss_is_propagated_without_quota_release(self):
        import psycopg
        config = replace(main.CONFIG, persistence_backend="postgresql")
        error = psycopg.OperationalError("synthetic authorization connection loss")

        with self.assertRaises(psycopg.OperationalError) as raised:
            main._raise_if_postgres_connection_failure(config, error)

        self.assertIs(raised.exception, error)

    def test_sqlite_authorization_errors_keep_existing_blocked_cycle_behavior(self):
        config = replace(main.CONFIG, persistence_backend="sqlite")
        error = OSError("ordinary authorization validation error")

        self.assertIsNone(main._raise_if_postgres_connection_failure(config, error))

    def test_postgres_connection_loss_during_posted_hours_lookup_aborts_pipeline(self):
        """A failed PostgreSQL cooldown-history read must not become empty history."""
        import psycopg
        with tempfile.TemporaryDirectory() as tmp:
            config = replace(
                main.CONFIG, database_path=str(Path(tmp) / "agent.db"),
                dry_run=True, persistence_backend="postgresql",
                postgres_dsn="postgresql://test", max_daily_posts=6,
            )

            class BrokenDatabase:
                def get_today_post_count(self):
                    return 0

                def get_posted_hours_dict(self, hours):
                    raise psycopg.OperationalError("synthetic PostgreSQL history outage")

            class Publisher:
                db = BrokenDatabase()
                postgres_store = object()

            class EmptyScanner:
                def _universe(self):
                    return []

            with patch.object(main, "CONFIG", config), \
                 patch.object(main, "_verify_persistence_integrity", return_value=True), \
                 patch.object(main, "_retry_pending_push"), \
                 patch.object(main, "_load_post_history", return_value={}):
                with self.assertRaises(psycopg.OperationalError):
                    main._run_once_impl(
                        config, scanner=EmptyScanner(), announcement_engine=object(),
                        research=object(), generator=object(), publisher=Publisher(),
                        posted_symbols=set(),
                    )

    def test_postgres_layer1_persistence_connection_loss_propagates_to_scheduler(self):
        """A PostgreSQL Layer 1 persistence outage must not be recorded as an ordinary empty cycle."""
        import psycopg
        with tempfile.TemporaryDirectory() as tmp:
            config = replace(
                main.CONFIG, database_path=str(Path(tmp) / "agent.db"),
                dry_run=True, persistence_backend="postgresql",
                postgres_dsn="postgresql://test", max_daily_posts=6,
            )

            class Database:
                def get_today_post_count(self):
                    return 0

                def get_posted_hours_dict(self, hours):
                    return {}

            class Publisher:
                db = Database()
                postgres_store = object()

            class Scanner:
                def _universe(self):
                    return [object()]

            class HotSearch:
                def get_trending(self, force_refresh=False):
                    return []

            with patch.object(main, "CONFIG", config), \
                 patch.object(main, "_verify_persistence_integrity", return_value=True), \
                 patch.object(main, "_retry_pending_push"), \
                 patch.object(main, "_load_post_history", return_value={}), \
                 patch.object(main, "_persist_layer1_market_intelligence", side_effect=psycopg.OperationalError("synthetic Layer 1 database outage")):
                with self.assertRaises(psycopg.OperationalError):
                    main._run_once_impl(
                        config, scanner=Scanner(), announcement_engine=object(),
                        research=object(), generator=object(), publisher=Publisher(),
                        posted_symbols=set(), hot_search_engine=HotSearch(),
                    )

    def test_postgres_connection_loss_during_history_lookup_is_not_treated_as_empty_history(self):
        """A broken PostgreSQL connection must abort, not erase duplicate history."""
        import psycopg
        config = replace(
            main.CONFIG, post_interval=60, max_iterations=1, dry_run=True,
            persistence_backend="postgresql", postgres_dsn="postgresql://test",
        )

        closed = []

        class BrokenDatabase:
            def get_posted_symbols(self, hours):
                raise psycopg.OperationalError("synthetic connection loss")
            def close(self):
                closed.append("publisher_db")

        class FakeStore:
            def close(self):
                closed.append("postgres_store")

        class FakePublisher:
            def __init__(self, cfg, postgres_store=None):
                self.db = BrokenDatabase()
                self.postgres_store = postgres_store

        store = FakeStore()
        with patch.object(main, "CONFIG", config), \
             patch.object(main, "MarketScanner"), \
             patch.object(main, "BinanceAnnouncementEngine"), \
             patch.object(main, "HotSearchEngine"), \
             patch.object(main, "ResearchEngine"), \
             patch.object(main, "DeepSeekGenerator"), \
             patch.object(main, "_create_runtime_postgres_store", return_value=store), \
             patch.object(main, "PostPublisher", FakePublisher), \
             patch.object(main, "run_once") as run_once:
            with self.assertRaises(SystemExit):
                main.main_loop()
        run_once.assert_not_called()
        self.assertEqual(closed, ["publisher_db", "postgres_store"])

    def test_postgres_connection_loss_during_run_once_stops_and_closes_resources(self):
        import psycopg
        config = replace(
            main.CONFIG, post_interval=60, max_iterations=1, dry_run=True,
            persistence_backend="postgresql", postgres_dsn="postgresql://test",
        )
        closed = []

        class Database:
            def get_posted_symbols(self, hours):
                return set()
            def close(self):
                closed.append("publisher_db")

        class Store:
            def close(self):
                closed.append("postgres_store")

        class Publisher:
            def __init__(self, cfg, postgres_store=None):
                self.db = Database()

        with patch.object(main, "CONFIG", config), \
             patch.object(main, "MarketScanner"), \
             patch.object(main, "BinanceAnnouncementEngine"), \
             patch.object(main, "HotSearchEngine"), \
             patch.object(main, "ResearchEngine"), \
             patch.object(main, "DeepSeekGenerator"), \
             patch.object(main, "_create_runtime_postgres_store", return_value=Store()), \
             patch.object(main, "PostPublisher", Publisher), \
             patch.object(main, "run_once", side_effect=psycopg.OperationalError("synthetic connection loss")):
            with self.assertRaises(SystemExit):
                main.main_loop()
        self.assertEqual(closed, ["publisher_db", "postgres_store"])

    def test_main_loop_closes_postgres_store_when_publisher_initialization_fails(self):
        config = replace(
            main.CONFIG, persistence_backend="postgresql", postgres_dsn="postgresql://test",
        )
        closed = []

        class Store:
            def close(self):
                closed.append("postgres_store")

        with patch.object(main, "CONFIG", config), \
             patch.object(main, "MarketScanner"), \
             patch.object(main, "BinanceAnnouncementEngine"), \
             patch.object(main, "HotSearchEngine"), \
             patch.object(main, "ResearchEngine"), \
             patch.object(main, "DeepSeekGenerator"), \
             patch.object(main, "_create_runtime_postgres_store", return_value=Store()), \
             patch.object(main, "PostPublisher", side_effect=RuntimeError("publisher init failed")):
            with self.assertRaisesRegex(RuntimeError, "publisher init failed"):
                main.main_loop()
        self.assertEqual(closed, ["postgres_store"])

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
        self.assertIn('PUBLISHER_ENABLED: "0"', workflow)


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
        lease.run_id = "run-123"
        with self.assertRaisesRegex(RuntimeError, "current process cannot recover"):
            lease.recover_interrupted(
                "run-123", process_termination_confirmed=True,
                evidence="scheduler job verified terminated", recovered_by="operator",
            )
        lease.run_id = None
        self.assertTrue(lease.recover_interrupted(
            "run-123", process_termination_confirmed=True,
            evidence="scheduler job verified terminated", recovered_by="operator",
        ))
        self.assertEqual(len(store.calls), 1)
        self.assertEqual(store.calls[0]["expected_run_id"], "run-123")


    def test_one_shot_bootstrap_closes_postgres_resources_when_history_read_fails(self):
        """The scheduled entrypoint must release shared DB resources on bootstrap failure."""
        config = replace(
            main.CONFIG, post_interval=0, dry_run=True,
            persistence_backend="postgresql", postgres_dsn="postgresql://test",
        )
        closed = []

        class FakeStore:
            def close(self):
                closed.append("postgres")

        class FakeDatabase:
            def get_posted_symbols(self, hours):
                raise OSError("history database unavailable")

            def close(self):
                closed.append("publisher_db")

        class FakePublisher:
            def __init__(self, cfg, postgres_store=None):
                self.postgres_store = postgres_store
                self.db = FakeDatabase()

        store = FakeStore()
        with patch.object(main, "CONFIG", config), \
             patch.object(main, "MarketScanner"), \
             patch.object(main, "BinanceAnnouncementEngine"), \
             patch.object(main, "HotSearchEngine"), \
             patch.object(main, "ResearchEngine"), \
             patch.object(main, "DeepSeekGenerator"), \
             patch.object(main, "_create_runtime_postgres_store", return_value=store), \
             patch.object(main, "PostPublisher", FakePublisher), \
             patch.object(main, "run_once") as run_once:
            with self.assertRaises(SystemExit) as raised:
                main.main()

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(closed, ["publisher_db", "postgres"])
        run_once.assert_not_called()


    def _run_one_shot_with_postgres_lease(self, *, outcome=None, failure=None):
        config = replace(
            main.CONFIG, post_interval=0, dry_run=True,
            persistence_backend="postgresql", postgres_dsn="postgresql://test",
        )
        calls = []
        closed = []

        class FakeStore:
            def inspect_active_run_lease(self):
                return None

            def acquire_run_lease(self, context):
                calls.append(("acquire", context.run_id))

            def finish_run_lease(self, run_id, status, summary):
                calls.append(("finish", run_id, status, summary))

            def close(self):
                closed.append("postgres")

        class FakeDatabase:
            def get_posted_symbols(self, hours):
                self.hours = hours
                return set()

            def close(self):
                closed.append("publisher_db")

        class FakePublisher:
            def __init__(self, cfg, postgres_store=None):
                self.postgres_store = postgres_store
                self.db = FakeDatabase()

        store = FakeStore()
        with patch.object(main, "CONFIG", config), \
             patch.object(main, "MarketScanner"), \
             patch.object(main, "BinanceAnnouncementEngine"), \
             patch.object(main, "HotSearchEngine"), \
             patch.object(main, "ResearchEngine"), \
             patch.object(main, "DeepSeekGenerator"), \
             patch.object(main, "_create_runtime_postgres_store", return_value=store), \
             patch.object(main, "PostPublisher", FakePublisher), \
             patch.object(main, "_run_once_impl", side_effect=failure, return_value=outcome) as pipeline:
            if failure is None:
                main.main()
            else:
                with self.assertRaises(SystemExit) as raised:
                    main.main()
                self.assertEqual(raised.exception.code, 1)

        pipeline.assert_called_once()
        self.assertEqual(calls[0][0], "acquire")
        self.assertEqual(calls[1][0], "finish")
        self.assertEqual(calls[0][1], calls[1][1])
        self.assertEqual(closed, ["publisher_db", "postgres"])
        return calls

    def test_one_shot_entrypoint_acquires_and_finishes_postgres_run_lease_on_success(self):
        calls = self._run_one_shot_with_postgres_lease(outcome=True)
        self.assertEqual(calls[1][2], "SUCCEEDED")
        self.assertEqual(calls[1][3]["cycle_result"], "SUCCEEDED")

    def test_one_shot_entrypoint_finalizes_failed_postgres_run_lease_before_nonzero_exit(self):
        calls = self._run_one_shot_with_postgres_lease(
            failure=OSError("synthetic pipeline failure"),
        )
        self.assertEqual(calls[1][2], "FAILED")
        self.assertEqual(calls[1][3]["error_type"], "OSError")


    def test_one_shot_bootstrap_closes_postgres_store_when_publisher_initialization_fails(self):
        config = replace(
            main.CONFIG, post_interval=0, dry_run=True,
            persistence_backend="postgresql", postgres_dsn="postgresql://test",
        )
        closed = []

        class FakeStore:
            def close(self):
                closed.append("postgres")

        class BrokenPublisher:
            def __init__(self, cfg, postgres_store=None):
                raise OSError("publisher initialization failed")

        with patch.object(main, "CONFIG", config), \
             patch.object(main, "MarketScanner"), \
             patch.object(main, "BinanceAnnouncementEngine"), \
             patch.object(main, "HotSearchEngine"), \
             patch.object(main, "ResearchEngine"), \
             patch.object(main, "DeepSeekGenerator"), \
             patch.object(main, "_create_runtime_postgres_store", return_value=FakeStore()), \
             patch.object(main, "PostPublisher", BrokenPublisher):
            with self.assertRaises(SystemExit) as raised:
                main.main()

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(closed, ["postgres"])


    def test_scheduled_workflow_refuses_ephemeral_sqlite_without_git_history_writer(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "run_bot.yml").read_text(encoding="utf-8")
        self.assertIn('if [ "$PERSISTENCE_BACKEND" != "postgresql" ]', workflow)
        self.assertIn("tr -d '[:space:]'", workflow)
        self.assertIn("Scheduled run requires durable PostgreSQL; refusing ephemeral SQLite", workflow)

    def test_scheduled_workflow_rejects_whitespace_only_postgres_dsn(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "run_bot.yml").read_text(encoding="utf-8")
        self.assertIn("tr -d '[:space:]'", workflow)

    def test_scheduled_workflow_does_not_export_unclassified_runtime_artifacts(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "run_bot.yml").read_text(encoding="utf-8")
        self.assertNotIn("actions/upload-artifact", workflow)
        for sensitive_path in ("research/", "prompts/", "drafts/", "images/", "agent.db", "published_posts.jsonl"):
            self.assertNotIn(sensitive_path, workflow)

    def test_scheduled_workflow_has_no_repository_write_credentials(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "run_bot.yml").read_text(encoding="utf-8")
        self.assertIn("contents: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("GH_TOKEN:", workflow)
        self.assertIn("persist-credentials: false", workflow)



if __name__ == "__main__":
    unittest.main()
