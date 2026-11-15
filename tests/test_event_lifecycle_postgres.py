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


if __name__ == "__main__":
    unittest.main()
