import unittest
from pathlib import Path
from unittest.mock import call


class PublicationPostgresStateMachineTests(unittest.TestCase):
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
        from psycopg.conninfo import conninfo_to_dict
        info = conninfo_to_dict(_TEST_PUBLICATION_DSN)
        host = info.get("host", "")
        database = info.get("dbname") or info.get("database")
        allowed_host = os.environ.get("TEST_POSTGRES_ALLOWED_HOST", "").strip()
        if (
            database != "binance_onchain_test"
            or not allowed_host
            or host != allowed_host
            or info.get("sslmode") not in {"require", "verify-ca", "verify-full"}
        ):
            raise RuntimeError(
                "publication PostgreSQL tests require binance_onchain_test on the exact "
                "TEST_POSTGRES_ALLOWED_HOST with TLS"
            )
        from layer1.publication_postgres import apply_publication_postgres_migrations
        apply_publication_postgres_migrations(_TEST_PUBLICATION_DSN)

    def setUp(self):
        from layer1.publication_postgres import PostgresPublicationStore
        self.store = PostgresPublicationStore(_TEST_PUBLICATION_DSN)
        self.attempt_ids = []
        self.reservation_ids = []

    def tearDown(self):
        with self.store.conn.transaction():
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
        import hashlib, json, os, uuid
        from datetime import datetime, timezone
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
                def read(self): return json.dumps({"code":"000000","data":{"id":"pg-integration-post-1","shareLink":"https://example.invalid/pg-integration-post-1"}}).encode()

            with tempfile.TemporaryDirectory() as tmp:
                config = dc_replace(main.CONFIG, database_path=str(Path(tmp) / "publisher.sqlite"),
                                    dry_run=False, square_api_key="test-key-not-real")
                publisher = main.PostPublisher(config, postgres_store=store)
                # The integration test exercises persistence only; do not create a local post artifact.
                publisher._save_locally = lambda *args, **kwargs: None
                try:
                    with patch("main._open_binance_publish_no_redirect", return_value=MockResponse()) as transport:
                        result = publisher.publish({"symbol":symbol,"asset_id":"coingecko:bitcoin"}, content, authorization=auth, image_hashes=[])
                    self.assertEqual(result.status, "PUBLISHED_CONFIRMED")
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
        from psycopg.conninfo import conninfo_to_dict
        from layer1.publication_postgres import PostgresPublicationStore, apply_publication_postgres_migrations

        dsn = os.environ["TEST_POSTGRES_DSN"]
        info = conninfo_to_dict(dsn)
        self.assertEqual(info.get("dbname") or info.get("database"), "binance_onchain_test")
        self.assertEqual(info.get("host"), os.environ.get("TEST_POSTGRES_ALLOWED_HOST"))
        self.assertIn(info.get("sslmode"), {"require", "verify-ca", "verify-full"})
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
