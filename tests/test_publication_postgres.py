import unittest
from pathlib import Path
from unittest.mock import call


class PublicationPostgresStateMachineTests(unittest.TestCase):
    def test_daily_quota_counts_unmirrored_analytics_and_reservations_additively(self):
        from layer1.publication_postgres import _quota_usage_count

        self.assertEqual(_quota_usage_count(1, 7), 8)
        self.assertEqual(_quota_usage_count(3, 0), 3)
        self.assertEqual(_quota_usage_count(0, 7), 7)
        for invalid in (True, -1, 1.5, "1"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    _quota_usage_count(invalid, 0)

    def test_quota_state_machine_accepts_only_forward_transitions(self):
        from layer1.publication_postgres import validate_quota_transition

        self.assertTrue(validate_quota_transition("RESERVED", "SUBMITTING"))
        self.assertTrue(validate_quota_transition("SUBMITTING", "PUBLICATION_UNKNOWN"))
        self.assertTrue(validate_quota_transition("PUBLICATION_UNKNOWN", "PUBLISHED_CONFIRMED"))
        self.assertTrue(validate_quota_transition("RESERVED", "RELEASED"))
        self.assertFalse(validate_quota_transition("RELEASED", "RESERVED"))
        self.assertFalse(validate_quota_transition("PUBLISHED_CONFIRMED", "FAILED_CONFIRMED"))
        self.assertFalse(validate_quota_transition("SUBMITTING", "RELEASED"))

    def test_attempt_state_machine_never_reopens_terminal_attempts(self):
        from layer1.publication_postgres import validate_attempt_transition

        self.assertTrue(validate_attempt_transition("SUBMITTING", "PUBLICATION_UNKNOWN"))
        self.assertTrue(validate_attempt_transition("SUBMITTING", "FAILED_CONFIRMED"))
        self.assertTrue(validate_attempt_transition("PUBLICATION_UNKNOWN", "PUBLISHED_CONFIRMED"))
        self.assertFalse(validate_attempt_transition("PUBLISHED_CONFIRMED", "SUBMITTING"))
        self.assertFalse(validate_attempt_transition("FAILED_CONFIRMED", "PUBLICATION_UNKNOWN"))
        self.assertFalse(validate_attempt_transition("SUBMITTING", "RELEASED"))

    def test_interrupted_submitting_attempt_is_eligible_for_operator_reconciliation(self):
        from layer1.publication_postgres import validate_reconciliation_source_status

        self.assertTrue(validate_reconciliation_source_status("SUBMITTING"))
        self.assertTrue(validate_reconciliation_source_status("PUBLICATION_UNKNOWN"))
        self.assertFalse(validate_reconciliation_source_status("PUBLISHED_CONFIRMED"))
        self.assertFalse(validate_reconciliation_source_status("FAILED_CONFIRMED"))

    def test_invalid_or_unknown_states_are_rejected(self):
        from layer1.publication_postgres import validate_quota_transition, validate_attempt_transition

        self.assertFalse(validate_quota_transition("NOT_A_STATE", "RESERVED"))
        self.assertFalse(validate_quota_transition("RESERVED", "NOT_A_STATE"))
        self.assertFalse(validate_attempt_transition("NOT_A_STATE", "SUBMITTING"))
        self.assertFalse(validate_attempt_transition("SUBMITTING", "NOT_A_STATE"))

    def test_event_revision_payload_and_evidence_are_bounded(self):
        from layer1.publication_postgres import validate_event_revision_payload

        payload_json, refs_json = validate_event_revision_payload(
            {"headline": "Exchange announcement"}, ["source:announcement:123"],
        )
        self.assertIn("Exchange announcement", payload_json)
        self.assertEqual(refs_json, '["source:announcement:123"]')
        with self.assertRaisesRegex(ValueError, "payload exceeds"):
            validate_event_revision_payload({"body": "x" * (256 * 1024)}, ["source:1"])
        with self.assertRaisesRegex(ValueError, "too many"):
            validate_event_revision_payload({}, [f"source:{i}" for i in range(101)])
        with self.assertRaisesRegex(ValueError, "too long"):
            validate_event_revision_payload({}, ["x" * 2049])
        nested = current = {}
        for _ in range(1200):
            current["child"] = {}
            current = current["child"]
        with self.assertRaisesRegex(ValueError, "structural limits"):
            validate_event_revision_payload(nested, ["source:1"])


class PublicationPostgresMigrationTests(unittest.TestCase):
    def test_runtime_store_verifies_migrations_without_applying_them(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import main

        config = SimpleNamespace(persistence_backend="postgresql", postgres_dsn="postgresql://app:secret@example.invalid/db")
        store = object()
        with patch("layer1.publication_postgres.verify_publication_postgres_migrations", return_value=("0001_example.sql",)) as verify:
            with patch("layer1.publication_postgres.PostgresPublicationStore", return_value=store):
                with patch("layer1.publication_postgres.apply_publication_postgres_migrations") as apply:
                    self.assertIs(main._create_runtime_postgres_store(config), store)
        verify.assert_called_once_with(config.postgres_dsn)
        apply.assert_not_called()

    def test_runtime_migration_verifier_checks_all_expected_checksums_read_only(self):
        import hashlib
        import tempfile
        from unittest.mock import patch
        from layer1.onchain_postgres import verify_postgres_migrations

        with tempfile.TemporaryDirectory() as tmp:
            migration = Path(tmp) / "0001_example.sql"
            migration.write_text("CREATE TABLE example (id INTEGER);\n", encoding="utf-8")
            checksum = hashlib.sha256(migration.read_bytes()).hexdigest()
            with patch("layer1.onchain_postgres._driver") as driver:
                driver.return_value = (driver, None)
                connection = driver.connect.return_value.__enter__.return_value
                connection.execute.return_value.fetchone.return_value = (checksum,)
                self.assertEqual(
                    verify_postgres_migrations("postgresql://app:secret@example.invalid/db", tmp),
                    ("0001_example.sql",),
                )
                statements = [call.args[0] for call in connection.execute.call_args_list]
                self.assertEqual(len(statements), 1)
                self.assertEqual(statements[0], "SELECT checksum FROM layer1_schema_migrations WHERE version=%s")

    def test_runtime_migration_verifier_rejects_a_missing_migration(self):
        import tempfile
        from unittest.mock import patch
        from layer1.onchain_postgres import verify_postgres_migrations

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "0001_example.sql").write_text("SELECT 1;", encoding="utf-8")
            with patch("layer1.onchain_postgres._driver") as driver:
                driver.return_value = (driver, None)
                connection = driver.connect.return_value.__enter__.return_value
                connection.execute.return_value.fetchone.return_value = None
                with self.assertRaisesRegex(RuntimeError, "missing applied PostgreSQL migration"):
                    verify_postgres_migrations("postgresql://app:secret@example.invalid/db", tmp)
                self.assertEqual(connection.execute.call_count, 1)
                self.assertTrue(connection.execute.call_args.args[0].startswith("SELECT"))

    def test_runtime_migration_verifier_rejects_checksum_drift(self):
        import tempfile
        from unittest.mock import patch
        from layer1.onchain_postgres import verify_postgres_migrations

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "0001_example.sql").write_text("SELECT 2;", encoding="utf-8")
            with patch("layer1.onchain_postgres._driver") as driver:
                driver.return_value = (driver, None)
                connection = driver.connect.return_value.__enter__.return_value
                connection.execute.return_value.fetchone.return_value = ("wrong-checksum",)
                with self.assertRaisesRegex(RuntimeError, "applied migration checksum changed"):
                    verify_postgres_migrations("postgresql://app:secret@example.invalid/db", tmp)
                self.assertEqual(connection.execute.call_count, 1)
                self.assertTrue(connection.execute.call_args.args[0].startswith("SELECT"))

    def test_migration_is_additive_and_covers_publication_critical_records(self):
        path = Path(__file__).resolve().parents[1] / "layer1" / "migrations" / "publication_postgresql" / "0001_publication_storage.sql"
        sql = path.read_text(encoding="utf-8").upper()
        self.assertNotIn("DROP TABLE", sql)
        self.assertNotIn("TRUNCATE", sql)
        self.assertNotIn("DELETE FROM", sql)
        for table in (
            "LAYER1_EVENT_LIFECYCLE",
            "LAYER1_EVENT_REVISIONS",
            "LAYER1_EVENT_TRANSITIONS",
            "LAYER1_RESEARCH_PACKAGE_VERSIONS",
            "EDITORIAL_BRIEF_VERSIONS",
            "CONTENT_DRAFT_VERSIONS",
            "CONTENT_DRAFT_VALIDATION_RESULTS",
            "VISUAL_VALIDATION_RESULTS",
            "OPPORTUNITY_DECISIONS",
            "PUBLICATION_ATTEMPTS",
            "PUBLICATION_QUOTA_RESERVATIONS",
            "PUBLICATION_AUTHORIZATIONS",
            "PUBLICATION_RECONCILIATION_EVENTS",
        ):
            self.assertIn("CREATE TABLE IF NOT EXISTS " + table, sql)



    def test_additive_run_lease_migration_is_non_destructive(self):
        path = Path(__file__).resolve().parents[1] / "layer1" / "migrations" / "publication_postgresql" / "0003_layer1_run_lease.sql"
        self.assertTrue(path.exists(), "PostgreSQL run lease migration must be present")
        sql = path.read_text(encoding="utf-8").upper()
        self.assertNotIn("DROP TABLE", sql)
        self.assertNotIn("TRUNCATE", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS LAYER1_RUNS", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS LAYER1_RUN_LEASE", sql)

    def test_non_string_states_are_rejected_without_type_errors(self):
        from layer1.publication_postgres import validate_quota_transition, validate_attempt_transition

        self.assertFalse(validate_quota_transition(None, "RESERVED"))
        self.assertFalse(validate_quota_transition("RESERVED", None))
        self.assertFalse(validate_attempt_transition([], "SUBMITTING"))
        self.assertFalse(validate_attempt_transition("SUBMITTING", []))

    def test_store_requires_an_explicit_dsn_and_has_no_environment_fallback(self):
        from layer1.publication_postgres import PostgresPublicationStore

        with self.assertRaisesRegex(ValueError, "explicit PostgreSQL DSN"):
            PostgresPublicationStore("")


if __name__ == "__main__":
    unittest.main()

import hashlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier


_TEST_PUBLICATION_DSN = os.environ.get("TEST_POSTGRES_DSN")


@unittest.skipUnless(_TEST_PUBLICATION_DSN, "TEST_POSTGRES_DSN is not configured")
class PublicationPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.postgres_test_support import validate_postgres_test_target
        validate_postgres_test_target(
            _TEST_PUBLICATION_DSN, os.environ.get("TEST_POSTGRES_ALLOWED_HOST", "").strip()
        )
        from layer1.publication_postgres import apply_publication_postgres_migrations
        apply_publication_postgres_migrations(_TEST_PUBLICATION_DSN)

    def setUp(self):
        from layer1.publication_postgres import PostgresPublicationStore
        self.store = PostgresPublicationStore(_TEST_PUBLICATION_DSN)
        self.attempt_ids = []
        self.reservation_ids = []
        self.analytics_ids = []

    def tearDown(self):
        with self.store.conn.transaction():
            if self.analytics_ids:
                self.store.conn.execute(
                    "DELETE FROM post_analytics WHERE id = ANY(%s)",
                    (self.analytics_ids,),
                )
            if self.attempt_ids:
                self.store.conn.execute(
                    "DELETE FROM publication_reconciliation_events WHERE attempt_id = ANY(%s)",
                    (self.attempt_ids,),
                )
            if self.reservation_ids:
                self.store.conn.execute(
                    "DELETE FROM publication_quota_reservations WHERE reservation_id = ANY(%s)",
                    (self.reservation_ids,),
                )
            if self.attempt_ids:
                self.store.conn.execute(
                    "DELETE FROM publication_attempts WHERE id = ANY(%s)",
                    (self.attempt_ids,),
                )
        self.store.close()

    def test_closed_connection_fails_closed_and_new_store_recovers_durable_quota(self):
        """A closed DB session cannot be reused; a new store sees committed quota."""
        from datetime import datetime, timezone
        import psycopg
        from layer1.publication_postgres import PostgresPublicationStore

        timestamp = datetime(2098, 6, 15, 12, 0, tzinfo=timezone.utc)
        reservation_id = self.store.reserve_daily_quota(
            symbol="RECOVERY", daily_limit=5, now=timestamp.isoformat(),
        )
        self.assertIsNotNone(reservation_id)
        self.reservation_ids.append(reservation_id)

        # Model a lost client connection deterministically. The managed test DB
        # rejected pg_terminate_backend for this session, so this does not claim
        # a server-side failover or backend-kill drill.
        self.store.conn.close()
        with self.assertRaises(psycopg.OperationalError):
            self.store.conn.execute("SELECT 1")

        self.store = PostgresPublicationStore(_TEST_PUBLICATION_DSN)
        recovered = self.store.conn.execute(
            "SELECT status, symbol FROM publication_quota_reservations WHERE reservation_id=%s",
            (reservation_id,),
        ).fetchone()
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered["status"], "RESERVED")
        self.assertEqual(recovered["symbol"], "RECOVERY")

    def test_daily_quota_does_not_hide_unmirrored_reservations_behind_legacy_analytics(self):
        from datetime import datetime, timezone

        timestamp = datetime(2099, 1, 1, 12, 0, tzinfo=timezone.utc)
        for index in range(7):
            row = self.store.conn.execute(
                "INSERT INTO post_analytics (coin_symbol,created_at,remote_post_id) "
                "VALUES (%s,%s,NULL) RETURNING id",
                (f"LEGACY{index}", timestamp),
            ).fetchone()
            self.analytics_ids.append(row["id"])

        first = self.store.reserve_daily_quota(
            symbol="BTC", daily_limit=8, now=timestamp.isoformat(),
        )
        self.assertIsNotNone(first)
        self.reservation_ids.append(first)
        second = self.store.reserve_daily_quota(
            symbol="ETH", daily_limit=8, now=timestamp.isoformat(),
        )
        self.assertIsNone(second, "7 legacy analytics + 1 active reservation must exhaust an 8-post quota")

    def test_postgres_run_lease_serializes_competing_connections(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from layer1.foundation import AgentConfig, ConfigurationOrchestrator
        from layer1.publication_postgres import PostgresPublicationStore
        from layer1.publication_runtime import PostgresRunLease
        barrier = Barrier(2)
        contexts = [
            ConfigurationOrchestrator(AgentConfig(database_path="postgres-runtime-race.db")).create_context({"worker": i})
            for i in range(2)
        ]
        def contender(context):
            store = PostgresPublicationStore(_TEST_PUBLICATION_DSN)
            lease = PostgresRunLease(store)
            try:
                barrier.wait(timeout=10)
                lease.acquire(context)
                return ("ACQUIRED", context.run_id)
            except RuntimeError as exc:
                if "lease already held" not in str(exc):
                    raise
                return ("BLOCKED", context.run_id)
            finally:
                if lease.run_id:
                    lease.finish("INTERRUPTED", {"cleanup": True})
                store.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(contender, contexts))
        self.assertEqual(sorted(result[0] for result in results), ["ACQUIRED", "BLOCKED"])
        self.assertIsNone(self.store.inspect_active_run_lease())
        run_ids = [context.run_id for context in contexts]
        with self.store.conn.transaction():
            self.store.conn.execute("DELETE FROM layer1_run_lease WHERE run_id = ANY(%s)", (run_ids,))
            self.store.conn.execute("DELETE FROM layer1_runs WHERE run_id = ANY(%s)", (run_ids,))

    def test_postgres_run_lease_requires_explicit_operator_recovery_after_crash(self):
        from layer1.foundation import AgentConfig, ConfigurationOrchestrator
        from layer1.publication_runtime import PostgresRunLease

        context = ConfigurationOrchestrator(
            AgentConfig(database_path="postgres-runtime-recovery.db"),
        ).create_context({"case": "operator-crash-recovery"})
        owner = PostgresRunLease(self.store)
        observer = PostgresRunLease(self.store)
        try:
            owner.acquire(context)
            with self.assertRaisesRegex(ValueError, "process termination confirmation"):
                observer.recover_interrupted(
                    context.run_id, process_termination_confirmed=False,
                    evidence="scheduler job verified terminated", recovered_by="integration-operator",
                )
            with self.assertRaisesRegex(ValueError, "expected run ID"):
                observer.recover_interrupted(
                    "wrong-run-id", process_termination_confirmed=True,
                    evidence="scheduler job verified terminated", recovered_by="integration-operator",
                )
            self.assertTrue(observer.recover_interrupted(
                context.run_id, process_termination_confirmed=True,
                evidence="scheduler job verified terminated", recovered_by="integration-operator",
            ))
            self.assertIsNone(observer.inspect_active())
            row = self.store.conn.execute(
                "SELECT status,summary_json FROM layer1_runs WHERE run_id=%s",
                (context.run_id,),
            ).fetchone()
            self.assertEqual(row["status"], "INTERRUPTED")
            self.assertEqual(
                row["summary_json"]["operator_recovery"]["recovered_by"],
                "integration-operator",
            )
        finally:
            with self.store.conn.transaction():
                self.store.conn.execute(
                    "DELETE FROM layer1_run_lease WHERE run_id=%s", (context.run_id,),
                )
                self.store.conn.execute(
                    "DELETE FROM layer1_runs WHERE run_id=%s", (context.run_id,),
                )

    def test_postgres_run_lease_crash_recovery_survives_fresh_process(self):
        import subprocess
        import sys
        import tempfile
        import time
        from pathlib import Path

        # A worker process acquires the lease and then remains alive. The test
        # kills that OS process rather than gracefully closing its DB adapter.
        worker_code = "\n".join((
            "import os, sys, time",
            "from pathlib import Path",
            "from layer1.foundation import AgentConfig, ConfigurationOrchestrator",
            "from layer1.publication_postgres import PostgresPublicationStore",
            "from layer1.publication_runtime import PostgresRunLease",
            "store = PostgresPublicationStore(os.environ['TEST_POSTGRES_DSN'])",
            "context = ConfigurationOrchestrator(AgentConfig(database_path='killed-worker.db')).create_context({'case': 'os-killed-run-owner'})",
            "lease = PostgresRunLease(store)",
            "lease.acquire(context)",
            "Path(sys.argv[1]).write_text(context.run_id)",
            "while True: time.sleep(60)",
        ))
        with tempfile.TemporaryDirectory(prefix="binance-run-lease-kill-") as ready_dir:
            ready_file = Path(ready_dir) / "worker-ready"
            worker = subprocess.Popen(
                [sys.executable, "-c", worker_code, str(ready_file)],
                cwd=str(Path(__file__).resolve().parents[1]),
                env=os.environ.copy(), stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, text=True,
            )
            try:
                deadline = time.monotonic() + 30
                while not ready_file.exists() and worker.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.05)
                if not ready_file.exists():
                    error = worker.stderr.read() if worker.poll() is not None else "worker readiness timed out"
                    self.fail("lease-owning worker failed before readiness: " + error)
                run_id = ready_file.read_text().strip()
                self.assertTrue(run_id)
                worker.kill()
                worker.wait(timeout=10)
                self.assertNotEqual(worker.returncode, 0, "lease-owning worker was expected to be killed")
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait(timeout=10)
                if worker.stderr:
                    worker.stderr.close()

        child = "\n".join((
            "import os, sys",
            "from layer1.foundation import AgentConfig, ConfigurationOrchestrator",
            "from layer1.publication_postgres import PostgresPublicationStore",
            "from layer1.publication_runtime import PostgresRunLease",
            "run_id = sys.argv[1]",
            "store = PostgresPublicationStore(os.environ['TEST_POSTGRES_DSN'])",
            "try:",
            "    lease = PostgresRunLease(store)",
            "    active = lease.inspect_active()",
            "    assert active and active['run_id'] == run_id and active['status'] == 'RUNNING'",
            "    context = ConfigurationOrchestrator(AgentConfig(database_path='recovery-child.db')).create_context({'case': 'overlap'})",
            "    try:",
            "        lease.acquire(context)",
            "    except RuntimeError as exc:",
            "        assert 'lease already held' in str(exc)",
            "    else:",
            "        raise AssertionError('fresh process bypassed the active run lease')",
            "    assert lease.recover_interrupted(run_id, process_termination_confirmed=True, evidence='isolated test confirmed lease owner process was SIGKILLed', recovered_by='fresh-process-test-operator')",
            "    assert lease.inspect_active() is None",
            "    row = store.conn.execute('SELECT status,summary_json FROM layer1_runs WHERE run_id=%s', (run_id,)).fetchone()",
            "    assert row['status'] == 'INTERRUPTED'",
            "    assert row['summary_json']['operator_recovery']['recovered_by'] == 'fresh-process-test-operator'",
            "finally:",
            "    store.close()",
        ))
        try:
            result = subprocess.run(
                [sys.executable, "-c", child, run_id],
                cwd=str(Path(__file__).resolve().parents[1]),
                env=os.environ.copy(), capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNone(self.store.inspect_active_run_lease())
            row = self.store.conn.execute(
                "SELECT status,summary_json FROM layer1_runs WHERE run_id=%s", (run_id,),
            ).fetchone()
            self.assertEqual(row["status"], "INTERRUPTED")
            self.assertEqual(
                row["summary_json"]["operator_recovery"]["recovered_by"],
                "fresh-process-test-operator",
            )
        finally:
            with self.store.conn.transaction():
                self.store.conn.execute("DELETE FROM layer1_run_lease WHERE run_id=%s", (run_id,))
                self.store.conn.execute("DELETE FROM layer1_runs WHERE run_id=%s", (run_id,))

    def test_postgres_open_transaction_is_rolled_back_after_worker_process_kill(self):
        import json
        import subprocess
        import sys
        import tempfile
        import time
        import uuid
        from pathlib import Path

        suffix = uuid.uuid4().hex
        uncommitted_run_id = "test-open-tx-uncommitted:" + suffix
        committed_run_id = "test-open-tx-committed:" + suffix
        config_hash = "a" * 64
        worker = None
        self.store.conn.execute(
            "INSERT INTO layer1_runs (run_id,started_at,finished_at,status,config_hash,summary_json) "
            "VALUES (%s,now(),now(),'SUCCEEDED',%s,%s::jsonb)",
            (committed_run_id, config_hash, json.dumps({"case": "committed-control"})),
        )
        worker_code = "\n".join((
            "import json, os, sys, time",
            "from pathlib import Path",
            "import psycopg",
            "dsn = os.environ['TEST_POSTGRES_DSN']",
            "run_id, ready = sys.argv[1], Path(sys.argv[2])",
            "conn = psycopg.connect(dsn, autocommit=True)",
            "backend_pid = conn.execute('SELECT pg_backend_pid()').fetchone()[0]",
            "with conn.transaction():",
            "    conn.execute(\"INSERT INTO layer1_runs (run_id,started_at,status,config_hash,summary_json) VALUES (%s,now(),'RUNNING',%s,%s::jsonb)\", (run_id, 'b'*64, json.dumps({'case':'uncommitted-crash-test'})))",
            "    conn.execute(\"INSERT INTO layer1_run_lease (lease_name,run_id,acquired_at) VALUES ('agent',%s,now())\", (run_id,))",
            "    ready.write_text(json.dumps({'backend_pid': backend_pid}), encoding='utf-8')",
            "    while True: time.sleep(60)",
        ))
        child_code = "\n".join((
            "import json, os, sys, time",
            "import psycopg",
            "backend_pid, missing_run, committed_run = sys.argv[1:]",
            "conn = psycopg.connect(os.environ['TEST_POSTGRES_DSN'], autocommit=True)",
            "try:",
            "    deadline = time.monotonic() + 30",
            "    while time.monotonic() < deadline:",
            "        active = conn.execute('SELECT 1 FROM pg_stat_activity WHERE pid=%s', (int(backend_pid),)).fetchone()",
            "        if active is None: break",
            "        time.sleep(0.1)",
            "    else: raise AssertionError('killed worker PostgreSQL backend remains active')",
            "    run = conn.execute('SELECT run_id FROM layer1_runs WHERE run_id=%s', (missing_run,)).fetchone()",
            "    lease = conn.execute('SELECT run_id FROM layer1_run_lease WHERE run_id=%s', (missing_run,)).fetchone()",
            "    assert run is None, 'uncommitted run row survived process death'",
            "    assert lease is None, 'uncommitted lease row survived process death'",
            "    committed = conn.execute('SELECT status,summary_json FROM layer1_runs WHERE run_id=%s', (committed_run,)).fetchone()",
            "    assert committed is not None and committed[0] == 'SUCCEEDED'",
            "    assert committed[1]['case'] == 'committed-control'",
            "    orphan_leases = conn.execute('SELECT count(*) FROM layer1_run_lease l LEFT JOIN layer1_runs r ON r.run_id=l.run_id WHERE r.run_id IS NULL').fetchone()[0]",
            "    assert orphan_leases == 0, 'orphaned run lease remains after transaction rollback'",
            "finally: conn.close()",
        ))
        try:
            with tempfile.TemporaryDirectory(prefix="binance-open-tx-kill-") as tmp:
                ready_path = Path(tmp) / "worker-ready.json"
                worker = subprocess.Popen(
                    [sys.executable, "-c", worker_code, uncommitted_run_id, str(ready_path)],
                    cwd=str(Path(__file__).resolve().parents[1]),
                    env=os.environ.copy(), stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE, text=True,
                )
                deadline = time.monotonic() + 30
                while not ready_path.exists() and worker.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.05)
                if not ready_path.exists():
                    error = worker.stderr.read() if worker.poll() is not None else "worker readiness timed out"
                    self.fail("open-transaction worker failed before readiness: " + error)
                backend_pid = json.loads(ready_path.read_text(encoding="utf-8"))["backend_pid"]
                worker.kill()
                worker.wait(timeout=10)
                self.assertNotEqual(worker.returncode, 0, "open-transaction worker was expected to be killed")
                result = subprocess.run(
                    [sys.executable, "-c", child_code,
                     str(backend_pid), uncommitted_run_id, committed_run_id],
                    cwd=str(Path(__file__).resolve().parents[1]),
                    env=os.environ.copy(), capture_output=True, text=True, timeout=45,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            if worker is not None and worker.poll() is None:
                worker.kill()
                worker.wait(timeout=10)
            if worker is not None and worker.stderr:
                worker.stderr.close()
            with self.store.conn.transaction():
                self.store.conn.execute("DELETE FROM layer1_run_lease WHERE run_id = ANY(%s)", ([uncommitted_run_id, committed_run_id],))
                self.store.conn.execute("DELETE FROM layer1_runs WHERE run_id = ANY(%s)", ([uncommitted_run_id, committed_run_id],))

    def test_postgres_run_lease_is_durable_and_fences_overlapping_runs(self):
        from layer1.foundation import AgentConfig, ConfigurationOrchestrator
        from layer1.publication_runtime import PostgresRunLease
        config = AgentConfig(database_path="postgres-runtime-lease-test.db")
        first_context = ConfigurationOrchestrator(config).create_context({"case": "first"})
        second_context = ConfigurationOrchestrator(config).create_context({"case": "second"})
        first = PostgresRunLease(self.store)
        second = PostgresRunLease(self.store)
        try:
            first.acquire(first_context)
            active = second.inspect_active()
            self.assertEqual(active["run_id"], first_context.run_id)
            self.assertEqual(active["status"], "RUNNING")
            with self.assertRaisesRegex(RuntimeError, "lease already held"):
                second.acquire(second_context)
            first.finish("SUCCEEDED", {"integration": "run-lease"})
            self.assertIsNone(second.inspect_active())
            row = self.store.conn.execute(
                "SELECT status,summary_json FROM layer1_runs WHERE run_id=%s",
                (first_context.run_id,),
            ).fetchone()
            self.assertEqual(row["status"], "SUCCEEDED")
            self.assertEqual(row["summary_json"]["integration"], "run-lease")
        finally:
            if first.run_id:
                first.finish("INTERRUPTED", {"cleanup": True})
            with self.store.conn.transaction():
                self.store.conn.execute("DELETE FROM layer1_run_lease WHERE run_id = ANY(%s)",
                                        ([first_context.run_id, second_context.run_id],))
                self.store.conn.execute("DELETE FROM layer1_runs WHERE run_id = ANY(%s)",
                                        ([first_context.run_id, second_context.run_id],))

    @staticmethod
    def _hash(label):
        return hashlib.sha256(label.encode("utf-8")).hexdigest()

    def _new_attempt(self, symbol="TEST"):
        key = "test-publication:" + uuid.uuid4().hex
        content_hash = self._hash(key)
        self.assertIsNone(self.store.begin_attempt(key, symbol, content_hash))
        row = self.store.conn.execute(
            "SELECT id FROM publication_attempts WHERE idempotency_key=%s", (key,)
        ).fetchone()
        self.attempt_ids.append(row["id"])
        return key, row["id"], content_hash

    def test_confirmed_publication_requires_and_preserves_remote_identity(self):
        key, attempt_id, _ = self._new_attempt("IDENTITY")
        with self.assertRaisesRegex(ValueError, "requires a remote post ID"):
            self.store.finish_attempt(key, "PUBLISHED_CONFIRMED")
        self.assertEqual(self.store.get_attempt(attempt_id)["status"], "SUBMITTING")

        remote_id = "verified-post-" + uuid.uuid4().hex
        share_link = "https://www.binance.com/square/post/" + remote_id
        self.store.finish_attempt(
            key, "PUBLISHED_CONFIRMED", post_id=remote_id, share_link=share_link,
        )
        with self.assertRaisesRegex(ValueError, "conflicts with the ID"):
            self.store.finish_attempt(
                key, "PUBLISHED_CONFIRMED", post_id="replacement-post-id",
            )
        with self.assertRaisesRegex(ValueError, "conflicts with the link"):
            self.store.finish_attempt(
                key, "PUBLISHED_CONFIRMED", post_id=remote_id,
                share_link="https://www.binance.com/square/post/different-post",
            )
        stored = self.store.get_attempt(attempt_id)
        self.assertEqual(stored["remote_post_id"], remote_id)
        self.assertEqual(stored["share_link"], share_link)

    def test_idempotency_key_is_bound_to_exact_symbol_and_content_hash(self):
        key, _, content_hash = self._new_attempt()
        existing = self.store.begin_attempt(key, "TEST", content_hash)
        self.assertIsInstance(existing, dict)
        with self.assertRaisesRegex(ValueError, "different publication content"):
            self.store.begin_attempt(key, "TEST", self._hash("different"))

    def test_same_symbol_competing_workers_cannot_create_two_pending_attempts(self):
        barrier = Barrier(2)
        symbol = "RACE" + uuid.uuid4().hex[:8].upper()

        def worker(index):
            from layer1.publication_postgres import PostgresPublicationStore
            store = PostgresPublicationStore(_TEST_PUBLICATION_DSN)
            key = f"race:{symbol}:{index}"
            try:
                barrier.wait()
                return store.begin_attempt(key, symbol, self._hash(key))
            finally:
                store.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, (1, 2)))
        rows = self.store.conn.execute(
            "SELECT id FROM publication_attempts WHERE coin_symbol=%s "
            "AND status IN ('SUBMITTING','PUBLICATION_UNKNOWN')",
            (symbol,),
        ).fetchall()
        self.attempt_ids.extend(row["id"] for row in rows)
        self.assertEqual(len(rows), 1)
        self.assertEqual(sum(result is None for result in results), 1)
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)

    def test_concurrent_daily_quota_reservations_obey_one_limit(self):
        barrier = Barrier(2)
        from datetime import date, timedelta
        timestamp = (date(2099, 1, 1) + timedelta(days=uuid.uuid4().int % 3000)).isoformat() + "T12:00:00+00:00"
        symbol = "Q" + uuid.uuid4().hex[:9].upper()

        def worker():
            from layer1.publication_postgres import PostgresPublicationStore
            store = PostgresPublicationStore(_TEST_PUBLICATION_DSN)
            try:
                barrier.wait()
                return store.reserve_daily_quota(symbol=symbol, daily_limit=1, now=timestamp)
            finally:
                store.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            reservations = list(pool.map(lambda _: worker(), range(2)))
        self.reservation_ids.extend(value for value in reservations if value)
        self.assertEqual(sum(value is not None for value in reservations), 1)

    def test_crash_left_submitting_attempt_can_be_reconciled_without_retry(self):
        key, attempt_id, _ = self._new_attempt("CRASH")
        from datetime import date, timedelta
        future_time = (date(2099, 1, 1) + timedelta(days=uuid.uuid4().int % 3000)).isoformat() + "T12:00:00+00:00"
        reservation = self.store.reserve_daily_quota(
            symbol="CRASH", daily_limit=1, now=future_time,
        )
        self.assertIsNotNone(reservation)
        self.reservation_ids.append(reservation)
        self.store.bind_attempt(reservation, attempt_id)
        self.store.mark_quota_status(reservation, "SUBMITTING")

        # Simulate process death while the durable attempt is still SUBMITTING.
        self.store.close()
        from layer1.publication_postgres import PostgresPublicationStore
        self.store = PostgresPublicationStore(_TEST_PUBLICATION_DSN)
        recovered = next(row for row in self.store.list_pending_attempts() if row["id"] == attempt_id)
        self.assertEqual(recovered["status"], "SUBMITTING")
        duplicate = self.store.begin_attempt(key, "CRASH", self._hash(key))
        self.assertEqual(duplicate["id"], attempt_id)
        self.assertEqual(duplicate["status"], "SUBMITTING")

        self.store.reconcile_attempt(
            attempt_id=attempt_id, new_status="FAILED_CONFIRMED",
            reconciled_by="integration-test", evidence="isolated test evidence: remote absence verified",
            note="crash recovery; operator verified no remote post exists",
        )
        attempt = self.store.conn.execute(
            "SELECT status FROM publication_attempts WHERE id=%s", (attempt_id,)
        ).fetchone()
        quota = self.store.conn.execute(
            "SELECT status FROM publication_quota_reservations WHERE reservation_id=%s", (reservation,)
        ).fetchone()
        audit = self.store.conn.execute(
            "SELECT prior_status,new_status FROM publication_reconciliation_events WHERE attempt_id=%s",
            (attempt_id,),
        ).fetchone()
        self.assertEqual(attempt["status"], "FAILED_CONFIRMED")
        self.assertEqual(quota["status"], "FAILED_CONFIRMED")
        self.assertEqual((audit["prior_status"], audit["new_status"]),
                         ("SUBMITTING", "FAILED_CONFIRMED"))

    def test_unknown_publication_attempt_and_quota_reconcile_in_fresh_process(self):
        import subprocess
        import sys
        from pathlib import Path
        from datetime import date, timedelta
        from layer1.publication_postgres import PostgresPublicationStore

        key, attempt_id, content_hash = self._new_attempt("PROCESSRECOVERY")
        future_time = (date(2099, 1, 1) + timedelta(days=uuid.uuid4().int % 3000)).isoformat() + "T12:00:00+00:00"
        reservation = self.store.reserve_daily_quota(
            symbol="PROCESSRECOVERY", daily_limit=1, now=future_time,
        )
        self.assertIsNotNone(reservation)
        self.reservation_ids.append(reservation)
        self.store.bind_attempt(reservation, attempt_id)
        self.store.mark_quota_status(reservation, "SUBMITTING")
        self.store.finish_attempt(key, "PUBLICATION_UNKNOWN", error="simulated process interruption")
        self.store.mark_quota_status(reservation, "PUBLICATION_UNKNOWN")
        self.store.close()

        remote_id = "process-recovery-" + uuid.uuid4().hex
        share_link = "https://www.binance.com/square/post/" + remote_id
        child = "\n".join((
            "import os, sys",
            "from layer1.publication_postgres import PostgresPublicationStore",
            "dsn = os.environ['TEST_POSTGRES_DSN']",
            "attempt_id, reservation, key, symbol, content_hash, remote_id, share_link = sys.argv[1:]",
            "attempt_id = int(attempt_id)",
            "store = PostgresPublicationStore(dsn)",
            "try:",
            "    attempt = store.get_attempt(attempt_id)",
            "    assert attempt['status'] == 'PUBLICATION_UNKNOWN'",
            "    pending = [item for item in store.list_pending_attempts() if item['id'] == attempt_id]",
            "    assert len(pending) == 1",
            "    duplicate = store.begin_attempt(key, symbol, content_hash)",
            "    assert duplicate['id'] == attempt_id and duplicate['status'] == 'PUBLICATION_UNKNOWN'",
            "    quota = store.conn.execute('SELECT status,attempt_id FROM publication_quota_reservations WHERE reservation_id=%s', (reservation,)).fetchone()",
            "    assert quota['status'] == 'PUBLICATION_UNKNOWN' and quota['attempt_id'] == attempt_id",
            "    store.reconcile_attempt(attempt_id=attempt_id, new_status='PUBLISHED_CONFIRMED', reconciled_by='fresh-process-test-operator', evidence='isolated test fixture confirms synthetic remote identity', note='fresh-process unknown-outcome reconciliation', remote_post_id=remote_id, share_link=share_link)",
            "    attempt = store.get_attempt(attempt_id)",
            "    quota = store.conn.execute('SELECT status FROM publication_quota_reservations WHERE reservation_id=%s', (reservation,)).fetchone()",
            "    audit = store.conn.execute('SELECT COUNT(*) AS n FROM publication_reconciliation_events WHERE attempt_id=%s', (attempt_id,)).fetchone()",
            "    assert attempt['status'] == 'PUBLISHED_CONFIRMED' and attempt['remote_post_id'] == remote_id and attempt['share_link'] == share_link",
            "    assert quota['status'] == 'PUBLISHED_CONFIRMED' and audit['n'] == 1",
            "finally:",
            "    store.close()",
        ))
        try:
            result = subprocess.run(
                [sys.executable, "-c", child, str(attempt_id), reservation, key,
                 "PROCESSRECOVERY", content_hash, remote_id, share_link],
                cwd=str(Path(__file__).resolve().parents[1]),
                env=os.environ.copy(), capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            self.store = PostgresPublicationStore(_TEST_PUBLICATION_DSN)

        attempt = self.store.get_attempt(attempt_id)
        quota = self.store.conn.execute(
            "SELECT status FROM publication_quota_reservations WHERE reservation_id=%s",
            (reservation,),
        ).fetchone()
        audit = self.store.conn.execute(
            "SELECT COUNT(*) AS n FROM publication_reconciliation_events WHERE attempt_id=%s",
            (attempt_id,),
        ).fetchone()
        self.assertEqual(attempt["status"], "PUBLISHED_CONFIRMED")
        self.assertEqual(attempt["remote_post_id"], remote_id)
        self.assertEqual(quota["status"], "PUBLISHED_CONFIRMED")
        self.assertEqual(audit["n"], 1)

    def test_reconciliation_rejects_conflicting_known_remote_id_without_mutation(self):
        _, attempt_id, _ = self._new_attempt("CONFLICT")
        existing_id = "already-known-" + uuid.uuid4().hex
        self.store.conn.execute(
            "UPDATE publication_attempts SET remote_post_id=%s WHERE id=%s",
            (existing_id, attempt_id),
        )
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.store.reconcile_attempt(
                attempt_id=attempt_id, new_status="PUBLISHED_CONFIRMED",
                reconciled_by="integration-test", evidence="test evidence",
                note="attempt conflicting remote ID", remote_post_id="different-remote-id",
            )
        with self.assertRaisesRegex(ValueError, "remote post ID is already recorded"):
            self.store.reconcile_attempt(
                attempt_id=attempt_id, new_status="FAILED_CONFIRMED",
                reconciled_by="integration-test", evidence="test evidence",
                note="attempt contradictory failure confirmation",
            )
        attempt = self.store.get_attempt(attempt_id)
        self.assertEqual(attempt["status"], "SUBMITTING")
        self.assertEqual(attempt["remote_post_id"], existing_id)
        audit = self.store.conn.execute(
            "SELECT COUNT(*) AS n FROM publication_reconciliation_events WHERE attempt_id=%s",
            (attempt_id,),
        ).fetchone()
        self.assertEqual(audit["n"], 0)

    def test_unknown_attempt_reconciliation_updates_attempt_quota_and_audit_atomically(self):
        key, attempt_id, _ = self._new_attempt("RECON")
        from datetime import date, timedelta
        future_time = (date(2099, 1, 1) + timedelta(days=uuid.uuid4().int % 3000)).isoformat() + "T12:00:00+00:00"
        reservation = self.store.reserve_daily_quota(
            symbol="RECON", daily_limit=1, now=future_time,
        )
        self.assertIsNotNone(reservation)
        self.reservation_ids.append(reservation)
        self.store.bind_attempt(reservation, attempt_id)
        self.store.mark_quota_status(reservation, "SUBMITTING")
        self.store.finish_attempt(key, "PUBLICATION_UNKNOWN", error="test timeout")
        self.store.mark_quota_status(reservation, "PUBLICATION_UNKNOWN")

        # Simulate process death: close the connection and recover using a fresh
        # store instance. The pending record must survive and remain non-retryable.
        self.store.close()
        from layer1.publication_postgres import PostgresPublicationStore
        self.store = PostgresPublicationStore(_TEST_PUBLICATION_DSN)
        pending = self.store.list_pending_attempts()
        recovered = next(row for row in pending if row["id"] == attempt_id)
        self.assertEqual(recovered["status"], "PUBLICATION_UNKNOWN")
        duplicate = self.store.begin_attempt(key, "RECON", self._hash(key))
        self.assertEqual(duplicate["id"], attempt_id)
        self.assertEqual(duplicate["status"], "PUBLICATION_UNKNOWN")

        remote_id = "test-remote-" + uuid.uuid4().hex
        share_link = "https://www.binance.com/square/post/" + remote_id
        self.store.reconcile_attempt(
            attempt_id=attempt_id, new_status="PUBLISHED_CONFIRMED",
            reconciled_by="integration-test", evidence="isolated test evidence",
            note="confirmed by deterministic test fixture", remote_post_id=remote_id,
            share_link=share_link,
        )
        attempt = self.store.get_attempt(attempt_id)
        quota = self.store.conn.execute(
            "SELECT status FROM publication_quota_reservations WHERE reservation_id=%s",
            (reservation,),
        ).fetchone()
        audit = self.store.conn.execute(
            "SELECT COUNT(*) AS n FROM publication_reconciliation_events WHERE attempt_id=%s",
            (attempt_id,),
        ).fetchone()
        self.assertEqual(attempt["status"], "PUBLISHED_CONFIRMED")
        self.assertEqual(attempt["remote_post_id"], remote_id)
        self.assertEqual(attempt["share_link"], share_link)
        self.assertEqual(quota["status"], "PUBLISHED_CONFIRMED")
        self.assertEqual(audit["n"], 1)

class PublicationPostgresIdentityTests(unittest.TestCase):
    def test_validation_advisory_lock_scope_separates_text_and_image_pairs(self):
        from layer1.publication_postgres import validation_advisory_lock_key

        draft_hash = "a" * 64
        image_hash = "b" * 64
        self.assertEqual(
            validation_advisory_lock_key(draft_hash, None),
            "publication-validation:" + draft_hash + ":text",
        )
        self.assertEqual(
            validation_advisory_lock_key(draft_hash, image_hash),
            "publication-validation:" + draft_hash + ":" + image_hash,
        )
        self.assertNotEqual(
            validation_advisory_lock_key(draft_hash, None),
            validation_advisory_lock_key(draft_hash, image_hash),
        )

    def test_authorized_submission_guard_holds_event_lock_and_transaction_across_yield(self):
        from layer1.publication_postgres import PostgresPublicationStore
        from unittest.mock import patch

        class Transaction:
            def __init__(self, connection):
                self.connection = connection
            def __enter__(self):
                self.connection.depth += 1
            def __exit__(self, *args):
                self.connection.depth -= 1

        class Cursor:
            def fetchone(self):
                return {"payload_json": {"event_id": "event:guard-test"}}

        class Connection:
            depth = 0
            def __init__(self):
                self.statements = []
            def transaction(self):
                return Transaction(self)
            def execute(self, query, params):
                self.statements.append((query, params))
                return Cursor()

        store = object.__new__(PostgresPublicationStore)
        store.conn = Connection()
        with patch.object(store, "validate_authorized_attempt_before_submit") as validate:
            with store.authorized_submission_guard(
                authorization_id="a" * 64, idempotency_key="test-key",
                symbol="BTC", content_hash="b" * 64,
            ):
                self.assertEqual(store.conn.depth, 1)
                lock_keys = [params[0] for sql, params in store.conn.statements if "pg_advisory_xact_lock" in sql]
                self.assertEqual(lock_keys, ["publication-symbol:BTC", "event-lifecycle:event:guard-test"])
                validate.assert_called_once()
            self.assertEqual(store.conn.depth, 0)

    def test_attempt_completion_requires_remote_identity_and_prevents_terminal_identity_rewrite(self):
        from layer1.publication_postgres import validate_attempt_completion

        with self.assertRaisesRegex(ValueError, "requires a remote post ID"):
            validate_attempt_completion(
                current_status="SUBMITTING", target_status="PUBLISHED_CONFIRMED",
                existing_remote_id="", existing_share_link="", remote_post_id="", share_link="",
            )
        with self.assertRaisesRegex(ValueError, "cannot confirm failure while a remote post ID"):
            validate_attempt_completion(
                current_status="SUBMITTING", target_status="FAILED_CONFIRMED",
                existing_remote_id="", existing_share_link="", remote_post_id="unexpected-id", share_link="",
            )
        with self.assertRaisesRegex(ValueError, "conflicts with the ID"):
            validate_attempt_completion(
                current_status="PUBLISHED_CONFIRMED", target_status="PUBLISHED_CONFIRMED",
                existing_remote_id="original-id", existing_share_link="", remote_post_id="replacement-id", share_link="",
            )
        with self.assertRaisesRegex(ValueError, "conflicts with the link"):
            validate_attempt_completion(
                current_status="PUBLISHED_CONFIRMED", target_status="PUBLISHED_CONFIRMED",
                existing_remote_id="original-id", existing_share_link="https://www.binance.com/square/post/original-id",
                remote_post_id="original-id", share_link="https://www.binance.com/square/post/other-id",
            )
        self.assertTrue(validate_attempt_completion(
            current_status="SUBMITTING", target_status="PUBLISHED_CONFIRMED",
            existing_remote_id="", existing_share_link="", remote_post_id="post-123", share_link="",
        ))
        self.assertTrue(validate_attempt_completion(
            current_status="PUBLISHED_CONFIRMED", target_status="PUBLISHED_CONFIRMED",
            existing_remote_id="post-123", existing_share_link="", remote_post_id="post-123", share_link="",
        ))
        with self.assertRaisesRegex(ValueError, "conflicts with the ID"):
            validate_attempt_completion(
                current_status="PUBLICATION_UNKNOWN", target_status="PUBLICATION_UNKNOWN",
                existing_remote_id="accepted-id", existing_share_link="", remote_post_id="different-id", share_link="",
            )
        with self.assertRaisesRegex(ValueError, "share link must be an HTTPS Binance Square"):
            validate_attempt_completion(
                current_status="SUBMITTING", target_status="PUBLICATION_UNKNOWN",
                existing_remote_id="", existing_share_link="", remote_post_id="accepted-id",
                share_link="https://evil.example/square/post/accepted-id",
            )
        self.assertTrue(validate_attempt_completion(
            current_status="SUBMITTING", target_status="PUBLICATION_UNKNOWN",
            existing_remote_id="", existing_share_link="", remote_post_id="accepted-id",
            share_link="https://www.binance.com/square/post/accepted-id",
        ))

    def test_existing_idempotency_key_cannot_be_rebound_to_other_content(self):
        from layer1.publication_postgres import validate_attempt_identity

        existing = {"coin_symbol": "BTC", "content_hash": "a" * 64}
        self.assertTrue(validate_attempt_identity(existing, "btc", "a" * 64))
        with self.assertRaisesRegex(ValueError, "different publication content"):
            validate_attempt_identity(existing, "BTC", "b" * 64)
        with self.assertRaisesRegex(ValueError, "different publication content"):
            validate_attempt_identity(existing, "ETH", "a" * 64)


class PublicationPostgresResearchPackageTests(unittest.TestCase):
    def test_research_package_requires_valid_identity_and_timezone_cutoff(self):
        from layer1.publication_postgres import validate_research_package_input

        with self.assertRaisesRegex(ValueError, "research_key"):
            validate_research_package_input("", "a" * 64, "2026-01-01T00:00:00Z", {})
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            validate_research_package_input("asset:BTC", "bad", "2026-01-01T00:00:00Z", {})
        with self.assertRaisesRegex(ValueError, "timezone"):
            validate_research_package_input("asset:BTC", "a" * 64, "2026-01-01T00:00:00", {})
        with self.assertRaisesRegex(ValueError, "payload"):
            validate_research_package_input("asset:BTC", "a" * 64, "2026-01-01T00:00:00Z", [])

    @unittest.skipUnless(__import__("os").environ.get("TEST_POSTGRES_DSN"), "TEST_POSTGRES_DSN is not configured")
    def test_research_package_versions_are_append_only_and_idempotent(self):
        import hashlib
        import json
        import os
        import uuid
        from urllib.parse import urlsplit
        from layer1.publication_postgres import PostgresPublicationStore

        dsn = os.environ["TEST_POSTGRES_DSN"]
        info = urlsplit(dsn)
        self.assertEqual(info.hostname, os.environ.get("TEST_POSTGRES_ALLOWED_HOST"))
        self.assertEqual(info.path.lstrip("/"), "binance_onchain_test")
        store = PostgresPublicationStore(dsn)
        key = "test-research:" + uuid.uuid4().hex
        payload1 = {"asset_id": "coingecko:bitcoin", "symbol": "BTC", "facts": ["verified"]}
        payload2 = {"asset_id": "coingecko:bitcoin", "symbol": "BTC", "facts": ["verified", "second"]}
        hash1 = hashlib.sha256(json.dumps(payload1, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        hash2 = hashlib.sha256(json.dumps(payload2, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        try:
            first = store.save_research_package(research_key=key, package_hash=hash1, cutoff_at="2026-11-15T00:00:00Z", payload=payload1)
            replay = store.save_research_package(research_key=key, package_hash=hash1, cutoff_at="2026-11-15T00:00:00Z", payload=payload1)
            second = store.save_research_package(research_key=key, package_hash=hash2, cutoff_at="2026-11-15T01:00:00Z", payload=payload2)
            self.assertEqual(first["package_id"], replay["package_id"])
            self.assertEqual(first["version"], replay["version"])
            self.assertEqual((first["version"], second["version"]), (1, 2))
            self.assertEqual(store.load_latest_research_package(key)["payload"], payload2)
            with self.assertRaisesRegex(ValueError, "immutable"):
                store.save_research_package(research_key=key, package_hash=hash1, cutoff_at="2026-11-15T00:00:00Z", payload={"tampered": True})
        finally:
            store.conn.execute("DELETE FROM layer1_research_package_versions WHERE research_key=%s", (key,))
            store.close()


    @unittest.skipUnless(__import__("os").environ.get("TEST_POSTGRES_DSN"), "TEST_POSTGRES_DSN is not configured")
    def test_research_editorial_draft_validation_image_and_opportunity_survive_fresh_process(self):
        import hashlib
        import json
        import os
        import subprocess
        import sys
        import uuid
        from pathlib import Path
        from layer1.opportunity import OpportunityDecision, _decision_digest
        from layer1.publication_postgres import PostgresPublicationStore

        dsn = os.environ["TEST_POSTGRES_DSN"]
        store = PostgresPublicationStore(dsn)
        suffix = uuid.uuid4().hex
        research_key = "test-process-recovery-research:" + suffix
        event_id = "test-process-recovery-event:" + suffix
        angle_id = "fresh-process-angle"
        research_payload = {"asset_id": "coingecko:bitcoin", "symbol": "BTC", "facts": ["persisted"]}
        research_hash = hashlib.sha256(json.dumps(research_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        brief_payload = {"headline": "Fresh process persistence", "claims": ["claim-1"]}
        brief_hash = hashlib.sha256(json.dumps(brief_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        content = "BTC market update backed by persisted evidence " + suffix
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        image_hash = hashlib.sha256(("image:" + suffix).encode()).hexdigest()
        prompt_hash = hashlib.sha256(("prompt:" + suffix).encode()).hexdigest()
        source_hash = hashlib.sha256(("source:" + suffix).encode()).hexdigest()
        decision_snapshot = json.dumps({"policy": {"version": "process-test-v1"}, "inputs": {"quality": 0.91}}, sort_keys=True, separators=(",", ":"))
        reasons = ("PROCESS_RESTART_TEST",)
        decision_id = _decision_digest(state="PROCEED", score=91.0, reasons=reasons, policy_version="process-test-v1", input_snapshot_json=decision_snapshot)
        artifact_metadata = {
            "provider": "cloudflare_workers_ai", "model": "@cf/black-forest-labs/flux-2-klein-4b",
            "generated_at": "2026-11-18T00:00:00Z", "prompt_hash": prompt_hash,
            "generation_parameters": {"width": 1024, "height": 1024, "output_format": "PNG"},
            "source_image_hash": source_hash, "final_image_hash": image_hash,
            "draft_hash": content_hash, "asset_id": "coingecko:bitcoin", "symbol": "BTC",
            "dimensions": [1024, 1024], "request_id": "process-recovery-" + suffix,
        }
        try:
            research = store.save_research_package(research_key=research_key, package_hash=research_hash, cutoff_at="2026-11-18T00:00:00Z", payload=research_payload)
            brief = store.save_editorial_brief(event_id=event_id, angle_id=angle_id, research_package_id=research["package_id"], brief_hash=brief_hash, payload=brief_payload)
            draft = store.save_draft(content, asset_id="coingecko:bitcoin", research_package_id=research["package_id"], editorial_brief_id=brief["brief_id"], approved_claim_ids=["a" * 64])
            text_validation_id = store.save_text_validation(draft_hash=content_hash, status="PASS", reasons=["claim-backed"], validation_version="process-text-v1")
            visual_validation_id = store.save_visual_validation(draft_hash=content_hash, image_hash=image_hash, status="PASS", reasons=["legible"], validation_version="process-visual-v1")
            artifact_id = store.save_image_artifact(artifact_metadata, image_path="/tmp/fresh-process-image-fixture.png")
            decision = OpportunityDecision("PROCEED", 91.0, reasons, "process-test-v1", decision_id, decision_snapshot)
            store.save_opportunity_decision(research["package_id"], decision)
            draft_key = draft.draft_key
            store.close()

            child = "\n".join((
                "import os, sys",
                "from layer1.publication_postgres import PostgresPublicationStore",
                "store = PostgresPublicationStore(os.environ['TEST_POSTGRES_DSN'])",
                "research_key, event_id, angle_id, draft_key, content_hash, image_hash, decision_id, package_id, brief_id, draft_id, text_id, visual_id, artifact_id = sys.argv[1:]",
                "try:",
                "    research = store.load_latest_research_package(research_key)",
                "    brief = store.load_latest_editorial_brief(event_id, angle_id)",
                "    draft = store.load_latest_draft(draft_key)",
                "    text = store.load_latest_text_validation(content_hash)",
                "    visual = store.load_latest_visual_validation(content_hash, image_hash)",
                "    artifact = store.load_image_artifact(content_hash, image_hash)",
                "    decision = store.load_opportunity_decision(decision_id)",
                "    assert research and research['package_id'] == package_id and research['payload']['facts'] == ['persisted']",
                "    assert brief and brief['brief_id'] == brief_id and brief['payload']['headline'] == 'Fresh process persistence'",
                "    assert draft and draft['draft_id'] == draft_id and draft['content_hash'] == content_hash",
                "    assert text and text['validation_id'] == text_id and text['status'] == 'PASS'",
                "    assert visual and visual['validation_id'] == visual_id and visual['status'] == 'PASS'",
                "    assert artifact and artifact['artifact_id'] == artifact_id and artifact['metadata']['final_image_hash'] == image_hash",
                "    assert decision and decision['decision_id'] == decision_id and decision['research_package_id'] == package_id",
                "finally:",
                "    store.close()",
            ))
            result = subprocess.run(
                [sys.executable, "-c", child, research_key, event_id, angle_id, draft_key,
                 content_hash, image_hash, decision_id, research["package_id"], brief["brief_id"],
                 draft.draft_id, text_validation_id, visual_validation_id, artifact_id],
                cwd=str(Path(__file__).resolve().parents[1]), env=os.environ.copy(),
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            if store.conn.closed:
                store = PostgresPublicationStore(dsn)
            with store.conn.transaction():
                store.conn.execute("DELETE FROM content_draft_validation_results WHERE draft_hash=%s", (content_hash,))
                store.conn.execute("DELETE FROM visual_validation_results WHERE draft_hash=%s AND image_hash=%s", (content_hash, image_hash))
                store.conn.execute("DELETE FROM image_generation_artifacts WHERE draft_hash=%s AND image_hash=%s", (content_hash, image_hash))
                store.conn.execute("DELETE FROM opportunity_decisions WHERE research_package_id IN (SELECT package_id FROM layer1_research_package_versions WHERE research_key=%s)", (research_key,))
                store.conn.execute("DELETE FROM content_draft_versions WHERE editorial_brief_id IN (SELECT brief_id FROM editorial_brief_versions WHERE event_id=%s AND angle_id=%s)", (event_id, angle_id))
                store.conn.execute("DELETE FROM editorial_brief_versions WHERE event_id=%s AND angle_id=%s", (event_id, angle_id))
                store.conn.execute("DELETE FROM layer1_research_package_versions WHERE research_key=%s", (research_key,))
            store.close()


class PublicationPostgresEditorialBriefTests(unittest.TestCase):
    @unittest.skipUnless(__import__("os").environ.get("TEST_POSTGRES_DSN"), "TEST_POSTGRES_DSN is not configured")
    def test_editorial_brief_is_versioned_idempotent_and_research_bound(self):
        import hashlib
        import json
        import os
        import uuid
        from layer1.publication_postgres import PostgresPublicationStore

        store = PostgresPublicationStore(os.environ["TEST_POSTGRES_DSN"])
        research_key = "test-editorial-research:" + uuid.uuid4().hex
        event_id = "test-event:" + uuid.uuid4().hex
        angle_id = "test-angle"
        research_payload = {"symbol": "BTC", "source": "test-fixture"}
        research_hash = hashlib.sha256(json.dumps(research_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        brief_payload = {"headline": "Test angle", "claims": ["claim-1"]}
        brief_hash = hashlib.sha256(json.dumps(brief_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        try:
            research = store.save_research_package(research_key=research_key, package_hash=research_hash, cutoff_at="2026-11-15T00:00:00Z", payload=research_payload)
            first = store.save_editorial_brief(event_id=event_id, angle_id=angle_id, research_package_id=research["package_id"], brief_hash=brief_hash, payload=brief_payload)
            replay = store.save_editorial_brief(event_id=event_id, angle_id=angle_id, research_package_id=research["package_id"], brief_hash=brief_hash, payload=brief_payload)
            self.assertEqual(first["brief_id"], replay["brief_id"])
            self.assertEqual(first["version"], 1)
            self.assertEqual(store.load_latest_editorial_brief(event_id, angle_id)["payload"], brief_payload)
            with self.assertRaisesRegex(ValueError, "immutable"):
                store.save_editorial_brief(event_id=event_id, angle_id=angle_id, research_package_id=research["package_id"], brief_hash=brief_hash, payload={"tampered": True})
        finally:
            store.conn.execute("DELETE FROM editorial_brief_versions WHERE event_id=%s AND angle_id=%s", (event_id, angle_id))
            store.conn.execute("DELETE FROM layer1_research_package_versions WHERE research_key=%s", (research_key,))
            store.close()


class PublicationPostgresDraftTests(unittest.TestCase):
    def test_draft_input_requires_canonical_asset_and_sha256_claim_ids(self):
        from layer1.publication_postgres import validate_draft_input

        with self.assertRaisesRegex(ValueError, "canonical asset"):
            validate_draft_input("content", "BTC", "research:1", "brief:1", ["a"*64])
        with self.assertRaisesRegex(ValueError, "SHA-256 claim IDs"):
            validate_draft_input("content", "coingecko:btc", "research:1", "brief:1", ["claim-id"])

    @unittest.skipUnless(__import__("os").environ.get("TEST_POSTGRES_DSN"), "TEST_POSTGRES_DSN is not configured")
    def test_draft_versions_are_append_only_idempotent_and_fk_bound(self):
        import hashlib, json, os, uuid
        from layer1.publication_postgres import PostgresPublicationStore

        store = PostgresPublicationStore(os.environ["TEST_POSTGRES_DSN"])
        research_key = "test-draft-research:" + uuid.uuid4().hex
        event_id = "test-draft-event:" + uuid.uuid4().hex
        payload = {"symbol":"BTC", "source":"draft-test"}
        research_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        try:
            research = store.save_research_package(research_key=research_key, package_hash=research_hash, cutoff_at="2026-11-15T00:00:00Z", payload=payload)
            brief_payload = {"angle":"test"}
            brief_hash = hashlib.sha256(json.dumps(brief_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            brief = store.save_editorial_brief(event_id=event_id, angle_id="angle", research_package_id=research["package_id"], brief_hash=brief_hash, payload=brief_payload)
            claims = ["a"*64, "b"*64]
            first = store.save_draft("BTC market update", asset_id="coingecko:btc", research_package_id=research["package_id"], editorial_brief_id=brief["brief_id"], approved_claim_ids=claims)
            replay = store.save_draft("BTC market update", asset_id="coingecko:btc", research_package_id=research["package_id"], editorial_brief_id=brief["brief_id"], approved_claim_ids=claims)
            second = store.save_draft("BTC market update revised", asset_id="coingecko:btc", research_package_id=research["package_id"], editorial_brief_id=brief["brief_id"], approved_claim_ids=claims)
            self.assertEqual(first.draft_id, replay.draft_id)
            self.assertEqual((first.version, second.version), (1, 2))
            self.assertEqual(store.load_latest_draft(first.draft_key)["content"], "BTC market update revised")
            with self.assertRaisesRegex(ValueError, "immutable"):
                store.save_draft("BTC market update", asset_id="coingecko:btc", research_package_id=research["package_id"], editorial_brief_id=brief["brief_id"], approved_claim_ids=["c"*64])
        finally:
            store.conn.execute("DELETE FROM content_draft_versions WHERE editorial_brief_id IN (SELECT brief_id FROM editorial_brief_versions WHERE event_id=%s)", (event_id,))
            store.conn.execute("DELETE FROM editorial_brief_versions WHERE event_id=%s", (event_id,))
            store.conn.execute("DELETE FROM layer1_research_package_versions WHERE research_key=%s", (research_key,))
            store.close()

    @unittest.skipUnless(__import__("os").environ.get("TEST_POSTGRES_DSN"), "TEST_POSTGRES_DSN is not configured")
    def test_concurrent_draft_versions_are_serialized_without_lost_versions(self):
        import hashlib, json, os, uuid
        from concurrent.futures import ThreadPoolExecutor
        from layer1.publication_postgres import PostgresPublicationStore

        dsn = os.environ["TEST_POSTGRES_DSN"]
        research_key = "test-draft-race-research:" + uuid.uuid4().hex
        event_id = "test-draft-race-event:" + uuid.uuid4().hex
        payload = {"symbol": "BTC", "source": "draft-race-test"}
        research_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        stores = []
        cleanup = PostgresPublicationStore(dsn)
        try:
            research = cleanup.save_research_package(research_key=research_key, package_hash=research_hash, cutoff_at="2026-11-15T00:00:00Z", payload=payload)
            brief_payload = {"angle": "race"}
            brief_hash = hashlib.sha256(json.dumps(brief_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            brief = cleanup.save_editorial_brief(event_id=event_id, angle_id="angle", research_package_id=research["package_id"], brief_hash=brief_hash, payload=brief_payload)

            def save(content):
                store = PostgresPublicationStore(dsn)
                stores.append(store)
                return store.save_draft(content, asset_id="coingecko:btc", research_package_id=research["package_id"], editorial_brief_id=brief["brief_id"], approved_claim_ids=["d" * 64])

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(save, ("draft concurrent A", "draft concurrent B")))
            self.assertEqual(sorted(item.version for item in results), [1, 2])
            self.assertEqual(len({item.draft_id for item in results}), 2)
            latest = cleanup.load_latest_draft(results[0].draft_key)
            self.assertEqual(latest["version"], 2)
            self.assertIn(latest["content"], {"draft concurrent A", "draft concurrent B"})
        finally:
            for store in stores:
                store.close()
            cleanup.conn.execute("DELETE FROM content_draft_versions WHERE editorial_brief_id IN (SELECT brief_id FROM editorial_brief_versions WHERE event_id=%s)", (event_id,))
            cleanup.conn.execute("DELETE FROM editorial_brief_versions WHERE event_id=%s", (event_id,))
            cleanup.conn.execute("DELETE FROM layer1_research_package_versions WHERE research_key=%s", (research_key,))
            cleanup.close()

    def test_validation_input_normalization_and_hashing(self):
        from layer1.publication_postgres import validate_validation_input

        text = validate_validation_input("a" * 64, None, "PASS", [" clear ", "clear"], "text-v1")
        self.assertEqual(text["reasons"], ["clear"])
        self.assertEqual(len(text["validation_id"]), 64)
        visual = validate_validation_input("a" * 64, "b" * 64, "NEEDS_REVISION", [], "visual-v1")
        self.assertEqual(visual["image_hash"], "b" * 64)
        for args in (("bad", None, "PASS", [], "v1"), ("a"*64, None, "UNKNOWN", [], "v1"), ("a"*64, None, "PASS", "reason", "v1"), ("a"*64, None, "PASS", [""], "v1")):
            with self.assertRaises(ValueError):
                validate_validation_input(*args)

    @unittest.skipUnless(__import__("os").environ.get("TEST_POSTGRES_DSN"), "TEST_POSTGRES_DSN is not configured")
    def test_text_and_visual_validation_are_idempotent_and_queryable(self):
        import os
        from layer1.publication_postgres import PostgresPublicationStore

        store = PostgresPublicationStore(os.environ["TEST_POSTGRES_DSN"])
        draft_hash, image_hash = "e" * 64, "f" * 64
        try:
            text_id = store.save_text_validation(draft_hash=draft_hash, status="PASS", reasons=["claim-backed"], validation_version="text-v1")
            self.assertEqual(text_id, store.save_text_validation(draft_hash=draft_hash, status="PASS", reasons=["claim-backed"], validation_version="text-v1"))
            visual_id = store.save_visual_validation(draft_hash=draft_hash, image_hash=image_hash, status="PASS", reasons=["legible"], validation_version="visual-v1")
            self.assertEqual(visual_id, store.save_visual_validation(draft_hash=draft_hash, image_hash=image_hash, status="PASS", reasons=["legible"], validation_version="visual-v1"))
            self.assertEqual(store.load_latest_text_validation(draft_hash)["validation_id"], text_id)
            self.assertEqual(store.load_latest_visual_validation(draft_hash, image_hash)["validation_id"], visual_id)
            revised_id = store.save_text_validation(draft_hash=draft_hash, status="REJECT", reasons=["claim-backed"], validation_version="text-v2")
            self.assertNotEqual(revised_id, text_id)
            self.assertEqual(store.load_latest_text_validation(draft_hash)["status"], "REJECT")
        finally:
            store.conn.execute("DELETE FROM content_draft_validation_results WHERE draft_hash=%s", (draft_hash,))
            store.conn.execute("DELETE FROM visual_validation_results WHERE draft_hash=%s AND image_hash=%s", (draft_hash, image_hash))
            store.close()


class PublicationPostgresImageArtifactTests(unittest.TestCase):
    def test_image_artifact_input_rejects_unapproved_provider_and_bad_hashes(self):
        from layer1.publication_postgres import validate_image_artifact_input
        metadata = {
            "provider": "cloudflare_workers_ai", "model": "@cf/black-forest-labs/flux-2-klein-4b",
            "generated_at": "2026-11-15T00:00:00Z", "prompt_hash": "a"*64,
            "generation_parameters": {"width": 1024, "height": 1024, "output_format": "PNG"},
            "source_image_hash": "b"*64, "final_image_hash": "c"*64,
            "draft_hash": "d"*64, "asset_id": "coingecko:btc", "symbol": "BTC",
            "dimensions": [1024, 1024],
        }
        self.assertEqual(validate_image_artifact_input(metadata, "/tmp/test.png")["image_hash"], "c"*64)
        invalid = dict(metadata, provider="untrusted-provider")
        with self.assertRaisesRegex(ValueError, "provider/model"):
            validate_image_artifact_input(invalid, "/tmp/test.png")
        invalid = dict(metadata, prompt_hash="bad")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            validate_image_artifact_input(invalid, "/tmp/test.png")

    @unittest.skipUnless(__import__("os").environ.get("TEST_POSTGRES_DSN"), "TEST_POSTGRES_DSN is not configured")
    def test_image_artifact_persistence_is_idempotent_and_rejects_conflicts(self):
        import os
        from layer1.publication_postgres import PostgresPublicationStore
        store = PostgresPublicationStore(os.environ["TEST_POSTGRES_DSN"])
        metadata = {
            "provider": "cloudflare_workers_ai", "model": "@cf/black-forest-labs/flux-2-klein-4b",
            "generated_at": "2026-11-15T00:00:00Z", "prompt_hash": "a"*64,
            "generation_parameters": {"width": 1024, "height": 1024, "output_format": "PNG"},
            "source_image_hash": "b"*64, "final_image_hash": "c"*64,
            "draft_hash": "d"*64, "asset_id": "coingecko:btc", "symbol": "BTC",
            "dimensions": [1024, 1024], "request_id": "fixture-image-request",
        }
        try:
            first = store.save_image_artifact(metadata, image_path="/tmp/fixture-image.png")
            replay = store.save_image_artifact(metadata, image_path="/tmp/fixture-image.png")
            self.assertEqual(first, replay)
            self.assertEqual(store.load_image_artifact("d"*64, "c"*64)["artifact_id"], first)
            with self.assertRaisesRegex(ValueError, "immutable"):
                store.save_image_artifact(dict(metadata, request_id="tampered"), image_path="/tmp/fixture-image.png")
        finally:
            store.conn.execute("DELETE FROM image_generation_artifacts WHERE draft_hash=%s AND image_hash=%s", ("d"*64, "c"*64))
            store.close()


class PublicationPostgresOpportunityTests(unittest.TestCase):
    def test_opportunity_decision_input_validation_rejects_bad_identity(self):
        from layer1.publication_postgres import validate_opportunity_decision_input
        with self.assertRaisesRegex(ValueError, "research package"):
            validate_opportunity_decision_input("", None)
        with self.assertRaisesRegex(ValueError, "decision"):
            validate_opportunity_decision_input("package:1", object())

    def test_opportunity_decision_input_validation_rejects_malformed_v2_provenance(self):
        import json
        from layer1.opportunity import OpportunityDecision
        from layer1.publication_postgres import validate_opportunity_decision_input
        malformed = {
            "policy": None,
            "inputs": {
                "schema_version": 2,
                "asset_id": "coingecko:bitcoin",
                "decision_cutoff_at": "2026-11-21T12:00:00Z",
                "factor_assessments": [],
            },
        }
        decision = OpportunityDecision(
            "DEFER", None, ("PROVENANCE_MISSING",), "UNCONFIGURED",
            "a" * 64, json.dumps(malformed),
        )
        with self.assertRaisesRegex(ValueError, "all six factors"):
            validate_opportunity_decision_input("package:1", decision)

    def test_postgres_decision_loader_rejects_stored_digest_mismatch(self):
        from datetime import datetime, timezone
        from decimal import Decimal
        from layer1.opportunity import _decision_digest
        from layer1.publication_postgres import PostgresPublicationStore
        snapshot = {"policy": {"version": "legacy-v1"}, "inputs": {"factor": 0.9}}
        reasons = ["REPLAY_TEST"]
        decision_id = _decision_digest(
            state="PROCEED", score=90.0, reasons=tuple(reasons),
            policy_version="legacy-v1",
            input_snapshot_json='{"inputs":{"factor":0.9},"policy":{"version":"legacy-v1"}}',
        )
        row = {
            "decision_id": decision_id, "research_package_id": "package:1",
            "state": "PROCEED", "score": Decimal("90.0"), "reasons_json": reasons,
            "policy_version": "legacy-v1", "input_snapshot_json": snapshot,
            "created_at": datetime.now(timezone.utc),
        }

        class FakeConnection:
            def execute(self, query, params):
                return self
            def fetchone(self):
                return row

        store = object.__new__(PostgresPublicationStore)
        store.conn = FakeConnection()
        loaded = store.load_opportunity_decision(decision_id)
        self.assertEqual(loaded["decision_id"], decision_id)
        row["input_snapshot_json"] = {
            "policy": {"version": "legacy-v1"}, "inputs": {"factor": 0.8},
        }
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            store.load_opportunity_decision(decision_id)

    @unittest.skipUnless(__import__("os").environ.get("TEST_POSTGRES_DSN"), "TEST_POSTGRES_DSN is not configured")
    def test_versioned_factor_provenance_decision_roundtrips_in_postgres(self):
        import hashlib, json, os, uuid
        from layer1.opportunity import FACTOR_NAMES, OpportunityDecision, _decision_digest
        from layer1.publication_postgres import PostgresPublicationStore
        store = PostgresPublicationStore(os.environ["TEST_POSTGRES_DSN"])
        suffix = uuid.uuid4().hex
        research_key = "test-opportunity-v2:" + suffix
        asset_id = "coingecko:bitcoin"
        cutoff = "2026-11-21T12:00:00Z"
        factor_assessments = []
        for name in FACTOR_NAMES:
            factor_assessments.append({
                "factor_name": name, "assessment_status": "READY", "value": 72.5,
                "rubric_version": "fixture-only-unapproved-v1",
                "feature_pipeline_version": "fixture-pipeline-v1",
                "source_contract_version": "fixture-source-v1",
                "subfeatures": [{
                    "feature_key": name + ".fixture", "asset_id": asset_id,
                    "availability": "AVAILABLE", "raw_value": 10.0,
                    "normalized_value": 0.5, "unit": "fixture_unit",
                    "source_refs": ["evidence:" + name], "source_payload_hashes": ["a" * 64],
                    "provider_timestamp": "2026-11-21T11:59:00Z", "event_at": None,
                    "event_time_semantics": None, "published_at": "2026-11-21T11:58:00Z",
                    "updated_at": "2026-11-21T11:59:00Z", "observed_at": "2026-11-21T11:59:30Z",
                    "window_start_at": "2026-11-21T11:00:00Z", "window_end_at": "2026-11-21T11:59:00Z",
                    "transformation_id": "fixture-transform", "transformation_version": "1",
                    "baseline_id": "fixture-baseline", "baseline_version": "1",
                    "source_dependency_group": "fixture-source-family", "quality_flags": [],
                    "missing_reason": None,
                }],
                "reason_codes": [], "evaluated_at": cutoff, "decision_cutoff_at": cutoff,
            })
        snapshot_obj = {"policy": None, "inputs": {
            "schema_version": 2, "asset_id": asset_id,
            "decision_cutoff_at": cutoff, "factor_assessments": factor_assessments,
        }}
        snapshot = json.dumps(snapshot_obj, sort_keys=True, separators=(",", ":"))
        reasons = ("PROVENANCE_SCHEMA_ROUNDTRIP_TEST_ONLY",)
        decision_id = _decision_digest(
            state="DEFER", score=None, reasons=reasons,
            policy_version="UNCONFIGURED", input_snapshot_json=snapshot,
        )
        decision = OpportunityDecision("DEFER", None, reasons, "UNCONFIGURED", decision_id, snapshot)
        payload = {"asset_id": asset_id, "test": suffix}
        package_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        try:
            package = store.save_research_package(
                research_key=research_key, package_hash=package_hash,
                cutoff_at=cutoff, payload=payload,
            )
            import copy
            wrong_asset_snapshot = copy.deepcopy(snapshot_obj)
            wrong_asset_snapshot["inputs"]["asset_id"] = "coingecko:ethereum"
            for assessment in wrong_asset_snapshot["inputs"]["factor_assessments"]:
                for subfeature in assessment["subfeatures"]:
                    subfeature["asset_id"] = "coingecko:ethereum"
            wrong_asset_json = json.dumps(wrong_asset_snapshot, sort_keys=True, separators=(",", ":"))
            wrong_asset_id = _decision_digest(
                state="DEFER", score=None, reasons=reasons,
                policy_version="UNCONFIGURED", input_snapshot_json=wrong_asset_json,
            )
            wrong_asset_decision = OpportunityDecision(
                "DEFER", None, reasons, "UNCONFIGURED", wrong_asset_id, wrong_asset_json,
            )
            with self.assertRaisesRegex(ValueError, "asset identity"):
                store.save_opportunity_decision(package["package_id"], wrong_asset_decision)
            store.save_opportunity_decision(package["package_id"], decision)
            loaded = store.load_opportunity_decision(decision_id)
            self.assertEqual(loaded["input_snapshot"], snapshot_obj)
            self.assertEqual(loaded["state"], "DEFER")
        finally:
            store.conn.execute(
                "DELETE FROM opportunity_decisions WHERE research_package_id IN (SELECT package_id FROM layer1_research_package_versions WHERE research_key=%s)",
                (research_key,),
            )
            store.conn.execute("DELETE FROM layer1_research_package_versions WHERE research_key=%s", (research_key,))
            store.close()

    @unittest.skipUnless(__import__("os").environ.get("TEST_POSTGRES_DSN"), "TEST_POSTGRES_DSN is not configured")
    def test_opportunity_decision_is_research_bound_idempotent_and_immutable(self):
        import hashlib, json, os, uuid
        from layer1.opportunity import OpportunityDecision, _decision_digest
        from layer1.publication_postgres import PostgresPublicationStore
        store = PostgresPublicationStore(os.environ["TEST_POSTGRES_DSN"])
        research_key = "test-opportunity:" + uuid.uuid4().hex
        payload = {"asset_id": "coingecko:bitcoin", "facts": ["verified"]}
        package_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        try:
            package = store.save_research_package(research_key=research_key, package_hash=package_hash, cutoff_at="2026-11-15T00:00:00Z", payload=payload)
            snapshot = json.dumps({"policy": {"version": "test-v1"}, "inputs": {"factor": 0.9}}, sort_keys=True, separators=(",", ":"))
            reasons = ("TEST_POLICY",)
            decision_id = _decision_digest(state="PROCEED", score=90.0, reasons=reasons, policy_version="test-v1", input_snapshot_json=snapshot)
            decision = OpportunityDecision("PROCEED", 90.0, reasons, "test-v1", decision_id, snapshot)
            first = store.save_opportunity_decision(package["package_id"], decision)
            replay = store.save_opportunity_decision(package["package_id"], decision)
            self.assertEqual(first, replay)
            loaded = store.load_opportunity_decision(decision_id)
            self.assertEqual(loaded["research_package_id"], package["package_id"])
            self.assertEqual(loaded["input_snapshot"], json.loads(snapshot))
            store.conn.execute(
                "UPDATE opportunity_decisions SET input_snapshot_json=jsonb_set(input_snapshot_json,'{inputs,factor}','0.8'::jsonb) WHERE decision_id=%s",
                (decision_id,),
            )
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                store.load_opportunity_decision(decision_id)
            conflicting = OpportunityDecision("DEFER", 90.0, reasons, "test-v1", decision_id, snapshot)
            with self.assertRaisesRegex(ValueError, "digest|immutable"):
                store.save_opportunity_decision(package["package_id"], conflicting)
        finally:
            store.conn.execute("DELETE FROM opportunity_decisions WHERE research_package_id IN (SELECT package_id FROM layer1_research_package_versions WHERE research_key=%s)", (research_key,))
            store.conn.execute("DELETE FROM layer1_research_package_versions WHERE research_key=%s", (research_key,))
            store.close()


class PublicationPostgresAuthorizationTests(unittest.TestCase):
    @unittest.skipUnless(__import__("os").environ.get("TEST_POSTGRES_DSN"), "TEST_POSTGRES_DSN is not configured")
    def test_authorization_is_persisted_only_when_all_exact_provenance_is_present(self):
        import hashlib, json, os, subprocess, sys, uuid
        from datetime import datetime, timedelta, timezone
        from layer1.publication_postgres import PostgresPublicationStore
        from layer1.publication_runtime import PostgresPublicationAuthorizationEngine
        store = PostgresPublicationStore(os.environ["TEST_POSTGRES_DSN"])
        suffix = uuid.uuid4().hex
        research_key = "test-auth:" + suffix
        event_id = "test-auth-event:" + suffix
        now = datetime.now(timezone.utc).replace(microsecond=0)
        now_s = now.isoformat()
        symbol = "AUTH" + suffix[:8].upper()
        package_payload = {"asset_id":"coingecko:bitcoin","symbol":"BTC"}
        package_hash = hashlib.sha256(json.dumps(package_payload,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        brief_payload = {"angle":"auth-test"}
        brief_hash = hashlib.sha256(json.dumps(brief_payload,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        content = "BTC market update supported by verified source " + suffix + "."
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        claim_ids = ("e"*64,)
        reservation = None
        attempt_key = "test-authorized-attempt:" + suffix
        try:
            package = store.save_research_package(research_key=research_key,package_hash=package_hash,cutoff_at=now_s,payload=package_payload)
            brief = store.save_editorial_brief(event_id=event_id,angle_id="auth-angle",research_package_id=package["package_id"],brief_hash=brief_hash,payload=brief_payload)
            draft = store.save_draft(content,asset_id="coingecko:bitcoin",research_package_id=package["package_id"],editorial_brief_id=brief["brief_id"],approved_claim_ids=claim_ids)
            store.save_text_validation(draft_hash=content_hash,status="PASS",reasons=[],validation_version="text-v1")
            authorization_engine = PostgresPublicationAuthorizationEngine(store)
            reservation = authorization_engine.reserve_daily_quota(
                symbol=symbol, daily_limit=1, now=now_s,
            )
            self.assertIsNotNone(reservation)
            auth = authorization_engine.authorize(
                symbol=symbol, asset_id="coingecko:bitcoin", content=content,
                image_hashes=[], eligibility_snapshot_at=now_s,
                eligibility_max_age_seconds=300, event_state="NO_EVENT",
                evidence_status="VERIFIED", text_validation_status="PASS",
                visual_validation_status="NOT_REQUIRED",
                quota_reservation_id=reservation, repetition_hard_hours=12,
                now=now_s, ttl_seconds=60,
            )
            auth_id = auth.authorization_id
            store.conn.execute(
                "INSERT INTO posts(coin_symbol,content,created_at) VALUES (%s,%s,%s)",
                (symbol, "competing post", now - timedelta(hours=1)),
            )
            self.assertIn(
                "RECENT_POST_COOLDOWN",
                authorization_engine.validate_persisted_duplicate_policy(auth),
            )
            store.conn.execute("DELETE FROM posts WHERE coin_symbol=%s", (symbol,))
            self.assertEqual(store.save_publication_authorization(auth), auth_id)
            self.assertEqual(store.load_publication_authorization(auth_id)["draft_id"], draft.draft_id)

            # Verify the immutable authorization survives a genuinely separate
            # process and connection before the mocked publisher consumes it.
            store.close()
            child = "\n".join((
                "import os, sys",
                "from layer1.publication_authorization import PublicationAuthorization",
                "from layer1.publication_postgres import PostgresPublicationStore",
                "auth_id, draft_id, research_id, brief_id, content_hash, quota_id = sys.argv[1:]",
                "store = PostgresPublicationStore(os.environ['TEST_POSTGRES_DSN'])",
                "try:",
                "    payload = store.load_publication_authorization(auth_id)",
                "    assert payload and payload['draft_id'] == draft_id",
                "    authorization = PublicationAuthorization(**payload)",
                "    assert authorization.verify_integrity()",
                "    assert authorization.research_package_id == research_id",
                "    assert authorization.editorial_brief_id == brief_id",
                "    assert authorization.content_hash == content_hash",
                "    assert authorization.quota_reservation_id == quota_id",
                "finally:",
                "    store.close()",
            ))
            try:
                result = subprocess.run(
                    [sys.executable, "-c", child, auth_id, draft.draft_id,
                     package["package_id"], brief["brief_id"], content_hash, reservation],
                    cwd=str(Path(__file__).resolve().parents[1]), env=os.environ.copy(),
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            finally:
                store = PostgresPublicationStore(os.environ["TEST_POSTGRES_DSN"])

            # Exercise the actual publisher against the disposable PostgreSQL ledger;
            # the Binance transport is replaced with a deterministic local response.
            import tempfile
            from dataclasses import replace as dc_replace
            from unittest.mock import patch
            import main

            class MockResponse:
                status = 200
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def read(self, size=-1):
                    body = json.dumps({"code":"000000","data":{"id":"pg-integration-post-1","shareLink":"https://www.binance.com/square/post/pg-integration-post-1"}}).encode()
                    return body if size < 0 else body[:size]

            with tempfile.TemporaryDirectory() as tmp:
                config = dc_replace(main.CONFIG, database_path=str(Path(tmp) / "publisher.sqlite"),
                                    dry_run=False, publisher_enabled=True,
                                    square_api_key="test-key-not-real")
                publisher = main.PostPublisher(config, postgres_store=store)
                # The integration test exercises persistence only; do not create a local post artifact.
                publisher._save_locally = lambda *args, **kwargs: None
                try:
                    with patch("main._open_binance_publish_no_redirect", return_value=MockResponse()) as transport:
                        result = publisher.publish({"symbol":symbol,"asset_id":"coingecko:bitcoin"}, content, authorization=auth, image_hashes=[])
                    self.assertEqual(result.status, "PUBLISHED_CONFIRMED", result.error)
                    self.assertEqual(result.post_id, "pg-integration-post-1")
                    self.assertIsNotNone(result.local_post_id)
                    post_row=store.conn.execute(
                        "SELECT id,coin_symbol,content,metadata FROM posts WHERE id=%s",
                        (result.local_post_id,),
                    ).fetchone()
                    self.assertEqual(post_row["coin_symbol"],symbol)
                    self.assertEqual(post_row["metadata"]["remote_post_id"],"pg-integration-post-1")
                    transport.assert_called_once()
                    attempt_key = publisher._idempotency_key(symbol, content, [])
                    attempt = store.conn.execute("SELECT id,status FROM publication_attempts WHERE idempotency_key=%s",(attempt_key,)).fetchone()
                    quota_state = store.conn.execute("SELECT status,attempt_id,authorization_id FROM publication_quota_reservations WHERE reservation_id=%s",(reservation,)).fetchone()
                    self.assertEqual((attempt["status"],quota_state["status"],quota_state["attempt_id"],quota_state["authorization_id"]),("PUBLISHED_CONFIRMED","PUBLISHED_CONFIRMED",attempt["id"],auth_id))
                    # A second invocation is fenced by the persisted terminal attempt.
                    with patch("main._open_binance_publish_no_redirect") as second_transport:
                        duplicate = publisher.publish({"symbol":symbol,"asset_id":"coingecko:bitcoin"}, content, authorization=auth, image_hashes=[])
                    self.assertEqual(duplicate.status, "DUPLICATE_BLOCKED")
                    second_transport.assert_not_called()
                    self.assertIsNone(publisher.db.conn)
                    self.assertFalse(Path(config.database_path).exists())
                finally:
                    publisher.db.close()
        finally:
            if reservation:
                store.conn.execute("DELETE FROM publication_authorizations WHERE quota_reservation_id=%s",(reservation,))
                store.conn.execute("DELETE FROM publication_quota_reservations WHERE reservation_id=%s",(reservation,))
            store.conn.execute("DELETE FROM publication_attempts WHERE idempotency_key=%s",(attempt_key,))
            store.conn.execute("DELETE FROM post_analytics WHERE remote_post_id=%s",("pg-integration-post-1",))
            store.conn.execute("DELETE FROM posts WHERE metadata->>'remote_post_id'=%s",("pg-integration-post-1",))
            store.conn.execute("DELETE FROM content_draft_validation_results WHERE draft_hash=%s",(content_hash,))
            store.conn.execute("DELETE FROM content_draft_versions WHERE editorial_brief_id IN (SELECT brief_id FROM editorial_brief_versions WHERE event_id=%s)",(event_id,))
            store.conn.execute("DELETE FROM editorial_brief_versions WHERE event_id=%s",(event_id,))
            store.conn.execute("DELETE FROM layer1_research_package_versions WHERE research_key=%s",(research_key,))
            store.close()


class PublicationPostgresEventLifecycleTests(unittest.TestCase):
    @unittest.skipUnless(__import__("os").environ.get("TEST_POSTGRES_DSN"), "TEST_POSTGRES_DSN is not configured")
    def test_runtime_event_snapshot_mirror_is_append_only_and_idempotent(self):
        import json
        import os
        import sqlite3
        import uuid
        from tests.postgres_test_support import validate_postgres_test_target
        from layer1.publication_postgres import PostgresPublicationStore, apply_publication_postgres_migrations

        dsn = os.environ["TEST_POSTGRES_DSN"]
        validate_postgres_test_target(dsn, os.environ.get("TEST_POSTGRES_ALLOWED_HOST", "").strip())
        apply_publication_postgres_migrations(dsn)
        store = PostgresPublicationStore(dsn)
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        event_id = "runtime-event-mirror:" + uuid.uuid4().hex
        stamp = "2026-11-15T12:00:00+00:00"
        revision_hash = "a" * 64
        payload = {"title": "BTC listing", "body": "Source announcement body"}
        try:
            connection.executescript("""
                CREATE TABLE layer1_event_lifecycle (
                    event_id TEXT PRIMARY KEY, asset_id TEXT, source_id TEXT, event_type TEXT,
                    state TEXT, first_published_at TEXT, first_observed_at TEXT,
                    last_updated_at TEXT, effective_event_at TEXT, latest_revision_hash TEXT,
                    updated_at TEXT
                );
                CREATE TABLE layer1_event_revisions (
                    event_id TEXT, revision_hash TEXT, source_published_at TEXT,
                    source_updated_at TEXT, observed_at TEXT, evidence_ref TEXT, payload_json TEXT
                );
                CREATE TABLE layer1_event_transitions (
                    transition_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT,
                    from_state TEXT, to_state TEXT, reason_code TEXT,
                    evidence_refs_json TEXT, transitioned_at TEXT
                );
            """)
            connection.execute(
                "INSERT INTO layer1_event_lifecycle VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (event_id, "coingecko:bitcoin", "source-1", "listing", "UNDER_VERIFICATION",
                 stamp, stamp, stamp, stamp, revision_hash, stamp),
            )
            connection.execute(
                "INSERT INTO layer1_event_revisions VALUES (?,?,?,?,?,?,?)",
                (event_id, revision_hash, stamp, stamp, stamp, "evidence:source-1",
                 json.dumps(payload, sort_keys=True, separators=(",", ":"))),
            )
            connection.executemany(
                "INSERT INTO layer1_event_transitions (event_id,from_state,to_state,reason_code,evidence_refs_json,transitioned_at) VALUES (?,?,?,?,?,?)",
                [
                    (event_id, None, "DISCOVERED", "FIRST_SOURCE_OBSERVATION", '["evidence:source-1"]', stamp),
                    (event_id, "DISCOVERED", "UNDER_VERIFICATION", "AWAITING_EVIDENCE_VERIFICATION", '["evidence:source-1"]', stamp),
                ],
            )
            store.sync_event_lifecycle_snapshot(connection, event_id)
            store.sync_event_lifecycle_snapshot(connection, event_id)
            loaded = store.load_event_lifecycle(event_id)
            self.assertEqual(loaded["state"], "UNDER_VERIFICATION")
            self.assertEqual(len(loaded["revisions"]), 1)
            self.assertEqual([item["to_state"] for item in loaded["history"]], ["DISCOVERED", "UNDER_VERIFICATION"])
        finally:
            store.conn.execute("DELETE FROM layer1_event_transitions WHERE event_id=%s", (event_id,))
            store.conn.execute("DELETE FROM layer1_event_revisions WHERE event_id=%s", (event_id,))
            store.conn.execute("DELETE FROM layer1_event_lifecycle WHERE event_id=%s", (event_id,))
            connection.close()
            store.close()

    def test_event_lifecycle_input_validation_is_deterministic(self):
        from layer1.publication_postgres import validate_event_lifecycle_input

        with self.assertRaisesRegex(ValueError, "event_id"):
            validate_event_lifecycle_input("", "coingecko:btc", "source", "listing", "a"*64, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "DISCOVERED", None, "FIRST_SOURCE_OBSERVATION", ["evidence:1"])
        with self.assertRaisesRegex(ValueError, "transition"):
            validate_event_lifecycle_input("event:1", "coingecko:btc", "source", "listing", "a"*64, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "BAD_STATE", None, "FIRST_SOURCE_OBSERVATION", ["evidence:1"])
        for state, prior in (([], None), ("DISCOVERED", [])):
            with self.assertRaisesRegex(ValueError, "state or transition"):
                validate_event_lifecycle_input("event:1", "coingecko:btc", "source", "listing", "a"*64, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", state, prior, "FIRST_SOURCE_OBSERVATION", ["evidence:1"])

    @unittest.skipUnless(__import__("os").environ.get("TEST_POSTGRES_DSN"), "TEST_POSTGRES_DSN is not configured")
    def test_event_lifecycle_persists_revision_transition_and_duplicate_idempotently(self):
        import json, os, uuid
        from datetime import datetime, timezone
        from layer1.publication_postgres import PostgresPublicationStore

        store = PostgresPublicationStore(os.environ["TEST_POSTGRES_DSN"])
        event_id = "test-event-lifecycle:" + uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        stamp = now.isoformat()
        revision = "a" * 64
        try:
            first = store.observe_event_lifecycle(event_id=event_id, asset_id="coingecko:btc", source_id="test-source", event_type="listing", revision_hash=revision, first_published_at=stamp, first_observed_at=stamp, last_updated_at=stamp, effective_event_at=stamp, state="DISCOVERED", from_state=None, reason_code="FIRST_SOURCE_OBSERVATION", evidence_refs=["evidence:test-1"], payload={"title":"BTC listing"})
            replay = store.observe_event_lifecycle(event_id=event_id, asset_id="coingecko:btc", source_id="test-source", event_type="listing", revision_hash=revision, first_published_at=stamp, first_observed_at=stamp, last_updated_at=stamp, effective_event_at=stamp, state="DISCOVERED", from_state=None, reason_code="FIRST_SOURCE_OBSERVATION", evidence_refs=["evidence:test-1"], payload={"title":"BTC listing"})
            second = store.observe_event_lifecycle(event_id=event_id, asset_id="coingecko:btc", source_id="test-source", event_type="listing", revision_hash="b"*64, first_published_at=stamp, first_observed_at=stamp, last_updated_at=stamp, effective_event_at=stamp, state="UNDER_VERIFICATION", from_state="DISCOVERED", reason_code="AWAITING_EVIDENCE_VERIFICATION", evidence_refs=["evidence:test-2"], payload={"title":"BTC listing updated"})
            self.assertEqual(first["event_id"], replay["event_id"])
            self.assertTrue(replay["replayed"])
            self.assertEqual(second["state"], "UNDER_VERIFICATION")
            loaded = store.load_event_lifecycle(event_id)
            self.assertEqual(loaded["latest_revision_hash"], "b"*64)
            self.assertEqual(len(loaded["revisions"]), 2)
            self.assertEqual([item["to_state"] for item in loaded["history"]], ["DISCOVERED", "UNDER_VERIFICATION"])
            with self.assertRaisesRegex(ValueError, "immutable"):
                store.observe_event_lifecycle(event_id=event_id, asset_id="coingecko:btc", source_id="test-source", event_type="listing", revision_hash=revision, first_published_at=stamp, first_observed_at=stamp, last_updated_at=stamp, effective_event_at=stamp, state="DISCOVERED", from_state=None, reason_code="FIRST_SOURCE_OBSERVATION", evidence_refs=["evidence:test-1"], payload={"tampered":True})
            with self.assertRaisesRegex(ValueError, "transition"):
                store.observe_event_lifecycle(event_id=event_id, asset_id="coingecko:btc", source_id="test-source", event_type="listing", revision_hash="c"*64, first_published_at=stamp, first_observed_at=stamp, last_updated_at=stamp, effective_event_at=stamp, state="CONFIRMED", from_state="DISCOVERED", reason_code="EVIDENCE_VERIFIED", evidence_refs=["evidence:test-3"], payload={"title":"BTC listing"})
        finally:
            store.conn.execute("DELETE FROM layer1_event_transitions WHERE event_id=%s", (event_id,))
            store.conn.execute("DELETE FROM layer1_event_revisions WHERE event_id=%s", (event_id,))
            store.conn.execute("DELETE FROM layer1_event_lifecycle WHERE event_id=%s", (event_id,))
            store.close()

    @unittest.skipUnless(__import__("os").environ.get("TEST_POSTGRES_DSN"), "TEST_POSTGRES_DSN is not configured")
    def test_concurrent_event_transitions_from_same_state_are_serialized(self):
        import os, uuid
        from datetime import datetime, timezone
        from threading import Barrier
        from concurrent.futures import ThreadPoolExecutor
        from layer1.publication_postgres import PostgresPublicationStore

        store = PostgresPublicationStore(os.environ["TEST_POSTGRES_DSN"])
        event_id = "test-event-race:" + uuid.uuid4().hex
        stamp = datetime.now(timezone.utc).isoformat()
        base = dict(event_id=event_id, asset_id="coingecko:btc", source_id="test-race-source", event_type="listing", first_published_at=stamp, first_observed_at=stamp, last_updated_at=stamp, effective_event_at=stamp, evidence_refs=["evidence:race"], payload={"title":"BTC listing"})
        try:
            store.observe_event_lifecycle(**base, revision_hash="d"*64, state="DISCOVERED", from_state=None, reason_code="FIRST_SOURCE_OBSERVATION")
            barrier = Barrier(2)
            def transition(index):
                worker = PostgresPublicationStore(os.environ["TEST_POSTGRES_DSN"])
                try:
                    barrier.wait()
                    return worker.observe_event_lifecycle(**base, revision_hash=("e" if index == 1 else "f")*64, state="UNDER_VERIFICATION", from_state="DISCOVERED", reason_code="AWAITING_EVIDENCE_VERIFICATION")
                except ValueError as exc:
                    return exc
                finally:
                    worker.close()
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(transition, (1, 2)))
            self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
            self.assertEqual(sum(isinstance(result, ValueError) for result in results), 1)
            loaded = store.load_event_lifecycle(event_id)
            self.assertEqual(loaded["state"], "UNDER_VERIFICATION")
            self.assertEqual(len(loaded["history"]), 2)
            self.assertEqual(len(loaded["revisions"]), 2)
        finally:
            store.conn.execute("DELETE FROM layer1_event_transitions WHERE event_id=%s", (event_id,))
            store.conn.execute("DELETE FROM layer1_event_revisions WHERE event_id=%s", (event_id,))
            store.conn.execute("DELETE FROM layer1_event_lifecycle WHERE event_id=%s", (event_id,))
            store.close()

[executed on device: localhost (bd830869-fbae-4825-ae7b-5044d6161090)]
