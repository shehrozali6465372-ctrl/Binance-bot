import unittest
from pathlib import Path


class PostgresLayer1StoreContractTests(unittest.TestCase):
    def test_store_requires_an_application_owned_connection(self):
        from layer1.layer1_postgres import PostgresLayer1Store
        with self.assertRaisesRegex(ValueError, "application-owned PostgreSQL connection"):
            PostgresLayer1Store(None)
        with self.assertRaisesRegex(ValueError, "application-owned PostgreSQL connection"):
            PostgresLayer1Store(object())

    def test_close_does_not_close_the_shared_connection(self):
        from layer1.layer1_postgres import PostgresLayer1Store

        class Connection:
            closed = False
            def execute(self, *args, **kwargs):
                return None
            def close(self):
                self.closed = True

        connection = Connection()
        PostgresLayer1Store(connection).close()
        self.assertFalse(connection.closed)

    def test_layer1_migration_is_additive_and_covers_the_existing_store_contract(self):
        path = (Path(__file__).resolve().parents[1] / "layer1" / "migrations"
                / "publication_postgresql" / "0004_layer1_discovery_store.sql")
        self.assertTrue(path.exists(), "Layer1 PostgreSQL discovery migration must exist")
        sql = path.read_text(encoding="utf-8").upper()
        self.assertNotIn("DROP TABLE", sql)
        self.assertNotIn("TRUNCATE", sql)
        self.assertNotIn("DELETE FROM", sql)
        for table in (
            "LAYER1_MARKET_OBSERVATIONS", "LAYER1_MARKET_ANALYSES",
            "LAYER1_IDENTITY_PROOFS", "LAYER1_ANNOUNCEMENT_EVIDENCE",
            "LAYER1_ANNOUNCEMENT_REVISIONS", "LAYER1_TREND_SIGNALS",
            "LAYER1_TREND_CLUSTERS", "LAYER1_CANDIDATES",
            "LAYER1_CANDIDATE_REJECTIONS", "LAYER1_CANDIDATE_SCORES",
        ):
            self.assertIn("CREATE TABLE IF NOT EXISTS " + table, sql)


if __name__ == "__main__":
    unittest.main()
