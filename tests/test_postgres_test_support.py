import unittest
from unittest.mock import patch


class _FakeResult:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return (self.value,)


class _FakeConnection:
    def __init__(self, database="binance_onchain_test", ssl_in_use=True):
        self.pgconn = type("PGConn", (), {"ssl_in_use": ssl_in_use})()
        self.database = database
        self.closed = False
        self.calls = []

    def execute(self, sql):
        self.calls.append(sql)
        return _FakeResult(self.database)

    def close(self):
        self.closed = True


class PostgresTestTargetGuardTests(unittest.TestCase):
    def test_remote_target_requires_exact_host_tls_and_channel_binding(self):
        from tests.postgres_test_support import validate_postgres_test_target

        dsn = (
            "postgresql://user:password@db.example.test/binance_onchain_test"
            "?sslmode=require&channel_binding=require"
        )
        connection = _FakeConnection()
        with patch("psycopg.connect", return_value=connection) as connect:
            validate_postgres_test_target(dsn, "db.example.test")
        self.assertTrue(connection.closed)
        self.assertEqual(connection.calls, ["SELECT current_database()"])
        self.assertEqual(connect.call_args.kwargs["options"], "-c default_transaction_read_only=on")

    def test_remote_target_rejects_connection_without_client_tls(self):
        from tests.postgres_test_support import validate_postgres_test_target

        dsn = "postgresql://user:password@db.example.test/binance_onchain_test?sslmode=require&channel_binding=require"
        connection = _FakeConnection(ssl_in_use=False)
        with patch("psycopg.connect", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "client TLS"):
                validate_postgres_test_target(dsn, "db.example.test")
        self.assertTrue(connection.closed)

    def test_remote_target_rejects_prefer_sslmode_before_connect(self):
        from tests.postgres_test_support import validate_postgres_test_target

        dsn = "postgresql://user:password@db.example.test/binance_onchain_test?sslmode=prefer&channel_binding=require"
        with patch("psycopg.connect") as connect:
            with self.assertRaisesRegex(RuntimeError, "must require TLS"):
                validate_postgres_test_target(dsn, "db.example.test")
        connect.assert_not_called()

    def test_remote_target_rejects_hostaddr_override_before_connect(self):
        from tests.postgres_test_support import validate_postgres_test_target

        dsn = "postgresql://user:password@db.example.test/binance_onchain_test?sslmode=require&channel_binding=require&hostaddr=127.0.0.1"
        with patch("psycopg.connect") as connect:
            with self.assertRaisesRegex(RuntimeError, "hostaddr"):
                validate_postgres_test_target(dsn, "db.example.test")
        connect.assert_not_called()

    def test_remote_target_rejects_missing_channel_binding_before_connect(self):
        from tests.postgres_test_support import validate_postgres_test_target

        dsn = "postgresql://user:password@db.example.test/binance_onchain_test?sslmode=require"
        with patch("psycopg.connect") as connect:
            with self.assertRaisesRegex(RuntimeError, "channel_binding=require"):
                validate_postgres_test_target(dsn, "db.example.test")
        connect.assert_not_called()

    def test_remote_target_rejects_wrong_database_identity(self):
        from tests.postgres_test_support import validate_postgres_test_target

        dsn = "postgresql://user:password@db.example.test/binance_onchain_test?sslmode=require&channel_binding=require"
        connection = _FakeConnection(database="postgres")
        with patch("psycopg.connect", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "connected database"):
                validate_postgres_test_target(dsn, "db.example.test")
        self.assertTrue(connection.closed)

    def test_remote_target_rejects_unallowlisted_host(self):
        from tests.postgres_test_support import validate_postgres_test_target

        dsn = "postgresql://user:password@other.example.test/binance_onchain_test?sslmode=require&channel_binding=require"
        with patch("psycopg.connect") as connect:
            with self.assertRaisesRegex(RuntimeError, "allowlist"):
                validate_postgres_test_target(dsn, "db.example.test")
        connect.assert_not_called()

    def test_localhost_target_does_not_require_remote_allowlist_or_tls(self):
        from tests.postgres_test_support import validate_postgres_test_target

        dsn = "postgresql://user:password@localhost/binance_onchain_test"
        connection = _FakeConnection(ssl_in_use=False)
        with patch("psycopg.connect", return_value=connection):
            validate_postgres_test_target(dsn, "")
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
