import os
import unittest
import uuid


class PostgresLegacyDatabaseAdapterTests(unittest.TestCase):
    def test_adapter_requires_shared_postgres_store(self):
        from layer1.legacy_postgres import PostgresLegacyDatabase
        with self.assertRaisesRegex(TypeError, "PostgreSQL publication store"):
            PostgresLegacyDatabase(object())

    def test_adapter_close_does_not_close_shared_connection(self):
        from layer1.legacy_postgres import PostgresLegacyDatabase

        class Connection:
            closed = False
            def execute(self, *args, **kwargs):
                return None
            def close(self):
                self.closed = True

        class Store:
            conn = Connection()

        store = Store()
        PostgresLegacyDatabase(store).close()
        self.assertFalse(store.conn.closed)


_LEGACY_TEST_DSN = os.environ.get("TEST_POSTGRES_DSN")


@unittest.skipUnless(_LEGACY_TEST_DSN, "TEST_POSTGRES_DSN is not configured")
class PostgresLegacyDatabaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from psycopg.conninfo import conninfo_to_dict
        info = conninfo_to_dict(_LEGACY_TEST_DSN)
        host = info.get("host", "")
        database = info.get("dbname") or info.get("database")
        allowed_host = os.environ.get("TEST_POSTGRES_ALLOWED_HOST", "").strip()
        if (database != "binance_onchain_test" or not allowed_host or host != allowed_host
                or info.get("sslmode") not in {"require", "verify-ca", "verify-full"}):
            raise RuntimeError(
                "legacy PostgreSQL tests require binance_onchain_test on exact TEST_POSTGRES_ALLOWED_HOST with TLS"
            )
        from layer1.publication_postgres import apply_publication_postgres_migrations
        apply_publication_postgres_migrations(_LEGACY_TEST_DSN)

    def setUp(self):
        from layer1.publication_postgres import PostgresPublicationStore
        from layer1.legacy_postgres import PostgresLegacyDatabase
        self.owner = PostgresPublicationStore(_LEGACY_TEST_DSN)
        self.db = PostgresLegacyDatabase(self.owner)
        self.suffix = uuid.uuid4().hex
        self.symbol = ("T" + self.suffix[:9]).upper()
        self.remote_id = "legacy-test-" + self.suffix
        self.post_id = None
        self.run_status = "legacy-test-" + self.suffix

    def tearDown(self):
        with self.owner.conn.transaction():
            if self.post_id is not None:
                self.owner.conn.execute("DELETE FROM metrics WHERE post_id=%s", (self.post_id,))
                self.owner.conn.execute("DELETE FROM post_analytics WHERE post_id=%s", (self.post_id,))
                self.owner.conn.execute("DELETE FROM posts WHERE id=%s", (self.post_id,))
            self.owner.conn.execute("DELETE FROM runs WHERE status=%s", (self.run_status,))
        self.owner.close()

    def test_post_history_metrics_runs_and_performance_analysis_round_trip(self):
        from main import PostgresPerformanceAnalyzer
        post_id = self.db.save_post({
            "content": "A verified test post #BTC",
            "coin_symbol": self.symbol,
            "remote_post_id": self.remote_id,
            "test_token": self.suffix,
        })
        self.post_id = post_id
        self.assertIn(self.symbol, self.db.get_posted_symbols())
        self.assertEqual(self.db.get_post_count_for_symbol(self.symbol), 1)
        self.assertIn(self.symbol, self.db.get_posted_hours_dict())
        recent = self.db.recent_posts(10)
        self.assertEqual(recent[0]["metadata"]["test_token"], self.suffix)

        self.db.save_metrics(10, 2, post_id=post_id)
        self.assertEqual(
            self.owner.conn.execute("SELECT COUNT(*) AS cnt FROM metrics WHERE post_id=%s",
                                    (post_id,)).fetchone()["cnt"],
            1,
        )
        self.db.save_run(self.run_status, {"test_token": self.suffix})

        analyzer = PostgresPerformanceAnalyzer(self.db)
        analyzer.record_publish(
            coin={"symbol": self.symbol, "announcement_type": "market_move", "narrative": "integration"},
            post_content="A verified market update with #BTC",
            decision_reason="guarded integration test",
            square_link="https://www.binance.com/square/post/" + self.remote_id,
            remote_post_id=self.remote_id,
            local_post_id=post_id,
        )
        self.assertTrue(analyzer.update_metrics(
            self.symbol, views=123, likes=4, comments=2, shares=1, traders=8,
            reward=0.5, remote_post_id=self.remote_id,
        ))
        self.assertEqual(self.db.get_top_performers(5)[0], self.symbol)
        self.assertGreaterEqual(self.db.get_today_post_count(), 1)
        insights = analyzer.get_insights_summary()
        self.assertIn("Most used catalyst", insights)
        self.assertEqual(
            self.owner.conn.execute(
                "SELECT views FROM post_analytics WHERE remote_post_id=%s", (self.remote_id,)
            ).fetchone()["views"],
            123,
        )


if __name__ == "__main__":
    unittest.main()
