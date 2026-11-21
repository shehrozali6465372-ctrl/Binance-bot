"""Failure-injection acceptance for PostgreSQL adapter transaction boundaries.

All writes are synthetic and isolated to the guarded binance_onchain_test database.
"""
import os
import unittest
import uuid

DSN = os.environ.get("TEST_POSTGRES_DSN")


def _install_failure_trigger(conn, table, suffix):
    from psycopg import sql
    trigger = "test_fail_" + suffix
    function = "test_fail_fn_" + suffix
    conn.execute(sql.SQL("CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected adapter failure'; END $$").format(sql.Identifier(function)))
    conn.execute(sql.SQL("CREATE TRIGGER {} BEFORE INSERT ON {} FOR EACH ROW EXECUTE FUNCTION {}()").format(sql.Identifier(trigger), sql.Identifier(table), sql.Identifier(function)))
    return trigger, function


def _remove_failure_trigger(conn, table, names):
    from psycopg import sql
    trigger, function = names
    conn.execute(sql.SQL("DROP TRIGGER IF EXISTS {} ON {}").format(sql.Identifier(trigger), sql.Identifier(table)))
    conn.execute(sql.SQL("DROP FUNCTION IF EXISTS {}()").format(sql.Identifier(function)))


@unittest.skipUnless(DSN, "TEST_POSTGRES_DSN is not configured")
class PostgresAdapterAtomicityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.postgres_test_support import validate_postgres_test_target
        validate_postgres_test_target(DSN, os.environ.get("TEST_POSTGRES_ALLOWED_HOST", "").strip())
        from layer1.publication_postgres import apply_publication_postgres_migrations
        apply_publication_postgres_migrations(DSN)

    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(DSN, autocommit=True)
        self.suffix = uuid.uuid4().hex

    def tearDown(self):
        self.conn.close()

    def test_claim_registry_insert_failure_leaves_no_partial_snapshot(self):
        import hashlib
        import json
        from psycopg.errors import RaiseException
        from layer1.evidence_verification import ClaimRegistry
        from layer1.publication_postgres import PostgresPublicationStore
        store = PostgresPublicationStore(DSN)
        registry = ClaimRegistry((), (), (), ())
        verification_id = hashlib.sha256(json.dumps(
            registry.to_dict(), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")).hexdigest()
        names = _install_failure_trigger(self.conn, "layer1_claim_verification_runs", self.suffix)
        try:
            with self.assertRaises(RaiseException):
                store.save_claim_registry(registry)
            self.assertIsNone(store.conn.execute(
                "SELECT 1 FROM layer1_claim_verification_runs WHERE verification_id=%s",
                (verification_id,),
            ).fetchone())
        finally:
            _remove_failure_trigger(self.conn, "layer1_claim_verification_runs", names)
            store.close()

    def test_announcement_second_write_failure_rolls_back_revision_insert(self):
        from psycopg.errors import RaiseException
        from layer1.foundation import AnnouncementEvidence, utc_now
        from layer1.layer1_postgres import PostgresLayer1Store
        from layer1.publication_postgres import PostgresPublicationStore
        owner = PostgresPublicationStore(DSN)
        layer1 = PostgresLayer1Store(owner.conn)
        source_id = "atomicity-source-" + self.suffix
        evidence = AnnouncementEvidence(
            source_id, "https://www.binance.com/en/support/announcement/" + self.suffix,
            "Binance", "listing", "Atomicity fixture", utc_now(), utc_now(), (), self.suffix[:64].ljust(64, "a"),
        )
        names = _install_failure_trigger(self.conn, "layer1_announcement_evidence", self.suffix)
        try:
            with self.assertRaises(RaiseException):
                layer1.save_announcement(evidence)
            self.assertIsNone(owner.conn.execute("SELECT 1 FROM layer1_announcement_revisions WHERE source_id=%s", (source_id,)).fetchone())
            self.assertIsNone(owner.conn.execute("SELECT 1 FROM layer1_announcement_evidence WHERE source_id=%s", (source_id,)).fetchone())
        finally:
            _remove_failure_trigger(self.conn, "layer1_announcement_evidence", names)
            with owner.conn.transaction():
                owner.conn.execute("DELETE FROM layer1_announcement_revisions WHERE source_id=%s", (source_id,))
                owner.conn.execute("DELETE FROM layer1_announcement_evidence WHERE source_id=%s", (source_id,))
            layer1.close()
            owner.close()

    def test_legacy_post_insert_failure_leaves_no_history_row(self):
        from psycopg.errors import RaiseException
        from layer1.legacy_postgres import PostgresLegacyDatabase
        from layer1.publication_postgres import PostgresPublicationStore
        owner = PostgresPublicationStore(DSN)
        db = PostgresLegacyDatabase(owner)
        token = "atomicity-" + self.suffix
        names = _install_failure_trigger(self.conn, "posts", self.suffix)
        try:
            with self.assertRaises(RaiseException):
                db.save_post({"content": "synthetic rollback fixture", "coin_symbol": "TST", "test_token": token})
            self.assertIsNone(owner.conn.execute("SELECT 1 FROM posts WHERE metadata->>'test_token'=%s", (token,)).fetchone())
        finally:
            _remove_failure_trigger(self.conn, "posts", names)
            owner.close()

    def test_verified_onchain_observation_failure_rolls_back_mapping_insert(self):
        from dataclasses import replace
        from psycopg.errors import RaiseException
        from layer1.onchain_postgres import PostgresOnChainStore
        from tests.test_onchain_intelligence import OnChainIntelligenceTests
        fixture = OnChainIntelligenceTests()
        fixture.setUp()
        mapping_id = "atomicity-mapping-" + self.suffix
        observation_id = "atomicity-observation-" + self.suffix
        mapping = replace(fixture.mapping, mapping_id=mapping_id)
        observation = replace(fixture.observation, observation_id=observation_id, mapping_id=mapping_id)
        store = PostgresOnChainStore(DSN, engine=fixture.engine)
        names = _install_failure_trigger(self.conn, "layer1_onchain_observations", self.suffix)
        try:
            with self.assertRaises(RaiseException):
                store.save_verified(fixture.eligibility, mapping, observation)
            self.assertIsNone(store.conn.execute("SELECT 1 FROM layer1_onchain_asset_mappings WHERE mapping_id=%s", (mapping_id,)).fetchone())
            self.assertIsNone(store.conn.execute("SELECT 1 FROM layer1_onchain_observations WHERE observation_id=%s", (observation_id,)).fetchone())
        finally:
            _remove_failure_trigger(self.conn, "layer1_onchain_observations", names)
            with store.conn.transaction():
                store.conn.execute("DELETE FROM layer1_onchain_observations WHERE observation_id=%s", (observation_id,))
                store.conn.execute("DELETE FROM layer1_onchain_asset_mappings WHERE mapping_id=%s", (mapping_id,))
            store.close()


if __name__ == "__main__":
    unittest.main()
