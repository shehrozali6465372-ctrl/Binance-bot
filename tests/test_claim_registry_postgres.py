"""PostgreSQL durability tests for the Module 11 claim registry."""
from __future__ import annotations

import os
import unittest
import uuid

_DSN = os.environ.get("TEST_POSTGRES_DSN")


@unittest.skipUnless(_DSN, "TEST_POSTGRES_DSN is not configured")
class ClaimRegistryPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from psycopg.conninfo import conninfo_to_dict
        info = conninfo_to_dict(_DSN)
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
                "claim registry PostgreSQL tests require binance_onchain_test "
                "on TEST_POSTGRES_ALLOWED_HOST with TLS"
            )
        from layer1.publication_postgres import apply_publication_postgres_migrations
        apply_publication_postgres_migrations(_DSN)

    def setUp(self):
        from layer1.publication_postgres import PostgresPublicationStore
        self.store = PostgresPublicationStore(_DSN)
        self.ids = []

    def tearDown(self):
        if self.ids:
            self.store.conn.execute(
                "DELETE FROM layer1_claim_verification_runs WHERE verification_id = ANY(%s)",
                (self.ids,),
            )
        self.store.close()

    def test_registry_snapshots_are_append_only_idempotent_and_load_latest(self):
        from layer1.evidence_verification import ClaimRegistry, ClaimVerificationResult

        first = ClaimRegistry(
            claims=(), evidence_records=(),
            results=(ClaimVerificationResult(
                claim_id="a" * 64, state="VERIFIED", evidence_ids=(),
                supporting_evidence_ids=(), contradicting_evidence_ids=(),
                independent_source_count=1, source_lineage={}, issues=(),
            ),),
            unresolved_issues=(),
        )
        second = ClaimRegistry(
            claims=(), evidence_records=(), results=(),
            unresolved_issues=({"issue": "UNRESOLVED_TEST"},),
        )
        first_id = self.store.save_claim_registry(first)
        self.ids.append(first_id)
        self.assertEqual(self.store.save_claim_registry(first), first_id)
        second_id = self.store.save_claim_registry(second)
        self.ids.append(second_id)

        rows = self.store.conn.execute(
            "SELECT claim_count,verified_count,corroborated_count,unresolved_count "
            "FROM layer1_claim_verification_runs WHERE verification_id=%s",
            (first_id,),
        ).fetchone()
        self.assertEqual(
            (rows["claim_count"], rows["verified_count"],
             rows["corroborated_count"], rows["unresolved_count"]),
            (0, 1, 0, 0),
        )
        self.assertEqual(
            self.store.conn.execute(
                "SELECT COUNT(*) AS n FROM layer1_claim_verification_runs "
                "WHERE verification_id = ANY(%s)",
                (self.ids,),
            ).fetchone()["n"],
            2,
        )
        latest = self.store.load_latest_claim_registry()
        self.assertEqual(latest["verification_id"], second_id)
        self.assertEqual(latest["payload"], second.to_dict())


if __name__ == "__main__":
    unittest.main()
