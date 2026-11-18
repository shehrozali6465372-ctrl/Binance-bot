import os
import unittest
from datetime import datetime, timedelta, timezone


class PostgresEventLifecycleAdapterTests(unittest.TestCase):
    def test_adapter_requires_shared_publication_store_contract(self):
        from layer1.event_lifecycle_postgres import PostgresEventLifecycleStore
        with self.assertRaisesRegex(TypeError, "PostgreSQL publication store"):
            PostgresEventLifecycleStore(object())

    def test_adapter_does_not_close_shared_postgres_connection(self):
        from layer1.event_lifecycle_postgres import PostgresEventLifecycleStore

        class Connection:
            closed = False
            def execute(self, *args, **kwargs):
                return None
            def close(self):
                self.closed = True

        class Store:
            conn = Connection()
            def load_event_lifecycle(self, event_id):
                return None
            def sync_event_lifecycle_snapshot(self, connection, event_id):
                return None

        store = Store()
        PostgresEventLifecycleStore(store).close()
        self.assertFalse(store.conn.closed)


_EVENT_TEST_DSN = os.environ.get("TEST_POSTGRES_DSN")


@unittest.skipUnless(_EVENT_TEST_DSN, "TEST_POSTGRES_DSN is not configured")
class PostgresEventLifecycleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from psycopg.conninfo import conninfo_to_dict
        info = conninfo_to_dict(_EVENT_TEST_DSN)
        host = info.get("host", "")
        database = info.get("dbname") or info.get("database")
        allowed_host = os.environ.get("TEST_POSTGRES_ALLOWED_HOST", "").strip()
        if (database != "binance_onchain_test" or not allowed_host or host != allowed_host
                or info.get("sslmode") not in {"require", "verify-ca", "verify-full"}):
            raise RuntimeError(
                "event lifecycle PostgreSQL tests require binance_onchain_test on exact TEST_POSTGRES_ALLOWED_HOST with TLS"
            )
        from layer1.publication_postgres import apply_publication_postgres_migrations
        apply_publication_postgres_migrations(_EVENT_TEST_DSN)

    def setUp(self):
        import uuid
        from layer1.publication_postgres import PostgresPublicationStore
        from layer1.event_lifecycle_postgres import PostgresEventLifecycleStore
        self.owner = PostgresPublicationStore(_EVENT_TEST_DSN)
        self.store = PostgresEventLifecycleStore(self.owner)
        self.suffix = uuid.uuid4().hex
        self.asset_id = "coingecko:event-test-" + self.suffix
        self.source_id = "event-source-" + self.suffix
        self.event_id = None
        self.event_ids = []

    def tearDown(self):
        if self.event_id:
            self.event_ids.append(self.event_id)
        if self.event_ids:
            with self.owner.conn.transaction():
                self.owner.conn.execute("DELETE FROM layer1_event_transitions WHERE event_id = ANY(%s)", (self.event_ids,))
                self.owner.conn.execute("DELETE FROM layer1_event_revisions WHERE event_id = ANY(%s)", (self.event_ids,))
                self.owner.conn.execute("DELETE FROM layer1_event_lifecycle WHERE event_id = ANY(%s)", (self.event_ids,))
        self.owner.close()

    def _evidence(self, revision="a", title="Test listing", body="Listing details", observed_delta=0):
        from layer1.foundation import AnnouncementEvidence, utc_now
        observed = datetime.now(timezone.utc) + timedelta(seconds=observed_delta)
        published = observed - timedelta(minutes=5)
        return AnnouncementEvidence(
            self.source_id,
            "https://www.binance.com/en/support/announcement/" + self.suffix,
            "Binance", "listing", title, published.isoformat(), observed.isoformat(),
            (self.asset_id,), revision * 64, body=body,
        )

    def test_event_lifecycle_survives_fresh_process_reopen(self):
        import subprocess
        import sys
        from pathlib import Path
        from layer1.publication_postgres import PostgresPublicationStore
        from layer1.event_lifecycle_postgres import PostgresEventLifecycleStore

        initial = self.store.observe(self._evidence("a"), verification_state="VERIFIED")
        self.event_id = initial.event_id
        expected_history = self.store.history(self.event_id)
        self.owner.close()

        child = "\n".join((
            "import os, sys",
            "from layer1.publication_postgres import PostgresPublicationStore",
            "from layer1.event_lifecycle_postgres import PostgresEventLifecycleStore",
            "owner = PostgresPublicationStore(os.environ['TEST_POSTGRES_DSN'])",
            "try:",
            "    store = PostgresEventLifecycleStore(owner)",
            "    record = store.get(sys.argv[1])",
            "    assert record is not None and record.state == 'CONFIRMED'",
            "    assert [item['to_state'] for item in store.history(sys.argv[1])] == ['DISCOVERED', 'UNDER_VERIFICATION', 'CONFIRMED']",
            "finally:",
            "    owner.close()",
        ))
        result = subprocess.run(
            [sys.executable, "-c", child, self.event_id],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=os.environ.copy(), capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        self.owner = PostgresPublicationStore(_EVENT_TEST_DSN)
        self.store = PostgresEventLifecycleStore(self.owner)
        self.assertEqual(self.store.get(self.event_id), initial)
        self.assertEqual(self.store.history(self.event_id), expected_history)

    def test_bootstrap_imports_only_missing_sqlite_lifecycle_snapshots(self):
        import tempfile
        from pathlib import Path
        from layer1.event_lifecycle import EventLifecycleStore
        from layer1.foundation import Layer1Store

        temporary = tempfile.TemporaryDirectory()
        legacy = Layer1Store(str(Path(temporary.name) / "legacy.db"))
        try:
            legacy_store = EventLifecycleStore(legacy)
            record = legacy_store.observe(self._evidence("d"), verification_state="UNVERIFIED")
            self.event_ids.append(record.event_id)
            imported = self.store.bootstrap_sqlite_snapshots(legacy.conn)
            self.assertEqual(imported, (record.event_id,))
            self.assertEqual(self.store.get(record.event_id), record)
            self.assertEqual(self.store.bootstrap_sqlite_snapshots(legacy.conn), ())
        finally:
            legacy.close()
            temporary.cleanup()

    def test_postgres_sync_uses_semantic_paraphrase_and_status_change_classifier(self):
        from layer1.evidence_verification import EvidenceVerificationEngine

        engine = EvidenceVerificationEngine()
        first = self._evidence(
            "a", title="ABC Spot listing announced",
            body="Binance will list ABC on 2026-12-01. Trading starts at 08:00 UTC.",
        )
        first_evidence = engine.evidence_from_announcement(first)
        first_registry = engine.verify(engine._source_assertion_claims(first_evidence), first_evidence)
        initial = self.store.sync_announcements([first], first_registry)[0]
        self.event_id = initial.event_id
        self.assertEqual(initial.state, "CONFIRMED")

        paraphrase = self._evidence(
            "b", title=first.title,
            body="Binance is going to list ABC on 2026-12-01. Trading will begin at 08:00 UTC.",
            observed_delta=1,
        )
        paraphrase_evidence = engine.evidence_from_announcement(paraphrase)
        paraphrase_registry = engine.verify(
            engine._source_assertion_claims(paraphrase_evidence), paraphrase_evidence,
        )
        unchanged = self.store.sync_announcements([paraphrase], paraphrase_registry)[0]
        self.assertEqual(unchanged.state, "CONFIRMED")

        status_change = self._evidence(
            "c", title=first.title,
            body="Trading for ABC has been suspended at 08:00 UTC on 2026-12-01.",
            observed_delta=2,
        )
        status_evidence = engine.evidence_from_announcement(status_change)
        status_registry = engine.verify(
            engine._source_assertion_claims(status_evidence), status_evidence,
        )
        developing = self.store.sync_announcements([status_change], status_registry)[0]
        self.assertEqual(developing.state, "DEVELOPING")
        self.assertEqual(self.store.history(developing.event_id)[-1]["reason_code"], "MATERIAL_NEW_EVIDENCE")

    def test_postgres_event_lifecycle_persists_verified_transitions_and_material_revision(self):
        first = self._evidence("a")
        record = self.store.observe(first, verification_state="UNVERIFIED")
        self.event_id = record.event_id
        self.assertEqual(record.state, "UNDER_VERIFICATION")
        self.assertEqual([item["to_state"] for item in self.store.history(record.event_id)],
                         ["DISCOVERED", "UNDER_VERIFICATION"])

        verified = self.store.observe(first, verification_state="VERIFIED")
        self.assertEqual(verified.state, "CONFIRMED")
        self.assertEqual(len(self.store.history(record.event_id)), 3)

        changed = self._evidence("b", title="Test listing", body="Listing date moved", observed_delta=1)
        developing = self.store.observe(changed, verification_state="VERIFIED", materially_new=True)
        self.assertEqual(developing.state, "DEVELOPING")
        self.assertEqual(len(self.store.history(record.event_id)), 4)

        replay = self.store.observe(changed, verification_state="VERIFIED", materially_new=True)
        self.assertEqual(replay.state, "DEVELOPING")
        self.assertEqual(len(self.store.history(record.event_id)), 4)


    def test_postgres_non_material_revision_does_not_reopen_stale_event(self):
        initial = self.store.observe(self._evidence("a"), verification_state="VERIFIED")
        self.event_id = initial.event_id
        stale = self.store.mark_stale(
            initial.event_id, now=(datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat(),
            max_age_seconds=1,
        )
        revised = self._evidence("b", observed_delta=30)
        result = self.store.observe(
            revised, verification_state="VERIFIED", materially_new=False,
        )
        self.assertEqual(stale.state, "STALE")
        self.assertEqual(result.state, "STALE")
        self.assertEqual(
            [item["to_state"] for item in self.store.history(initial.event_id)],
            ["DISCOVERED", "UNDER_VERIFICATION", "CONFIRMED", "STALE"],
        )

    def test_postgres_non_material_revision_does_not_reopen_resolved_event(self):
        initial = self.store.observe(self._evidence("a"), verification_state="VERIFIED")
        self.event_id = initial.event_id
        resolved = self.store.observe(
            self._evidence("b"), verification_state="VERIFIED", resolved=True,
            resolution_evidence_id="evidence:explicit-resolution",
        )
        revised = self._evidence("c", observed_delta=30)
        result = self.store.observe(
            revised, verification_state="VERIFIED", materially_new=False,
        )
        self.assertEqual(resolved.state, "RESOLVED")
        self.assertEqual(result.state, "RESOLVED")
        self.assertEqual(
            [item["to_state"] for item in self.store.history(initial.event_id)],
            ["DISCOVERED", "UNDER_VERIFICATION", "CONFIRMED", "RESOLVED"],
        )


if __name__ == "__main__":
    unittest.main()
