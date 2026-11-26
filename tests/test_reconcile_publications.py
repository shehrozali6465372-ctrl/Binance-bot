import os
import unittest
from unittest.mock import patch


class FakePostgresStore:
    def __init__(self, attempt=None):
        self.attempt = attempt or {
            "id": 7, "status": "PUBLICATION_UNKNOWN", "remote_post_id": None,
            "share_link": None,
        }
        self.reconciliations = []

    def list_pending_attempts(self, limit=100):
        return [self.attempt]

    def get_attempt(self, attempt_id):
        return dict(self.attempt) if self.attempt["id"] == attempt_id else None

    def reconcile_attempt(self, **kwargs):
        self.reconciliations.append(kwargs)
        self.attempt.update({
            "status": kwargs["new_status"],
            "remote_post_id": kwargs.get("remote_post_id") or self.attempt.get("remote_post_id"),
            "share_link": kwargs.get("share_link") or self.attempt.get("share_link"),
        })


class ReconcilePublicationBackendTests(unittest.TestCase):
    def test_parser_defaults_to_sqlite_without_backend_environment(self):
        from scripts.reconcile_publications import build_parser
        with patch.dict(os.environ, {}, clear=True):
            args = build_parser().parse_args(["list"])
        self.assertEqual(args.backend, "sqlite")
        self.assertEqual(args.postgres_dsn, "")

    def test_parser_reads_explicit_postgres_environment(self):
        from scripts.reconcile_publications import build_parser
        with patch.dict(os.environ, {
            "PERSISTENCE_BACKEND": "postgresql",
            "POSTGRES_DSN": "postgresql://staging.example/binance_onchain_test",
        }, clear=True):
            args = build_parser().parse_args(["list"])
        self.assertEqual(args.backend, "postgresql")
        self.assertEqual(args.postgres_dsn, "postgresql://staging.example/binance_onchain_test")

    def test_postgres_backend_requires_dsn_and_never_falls_back_to_sqlite(self):
        from scripts import reconcile_publications as cli
        with patch.object(cli, "Database") as sqlite_database:
            with self.assertRaisesRegex(SystemExit, "PostgreSQL DSN"):
                cli._connect("ignored.db", backend="postgresql", postgres_dsn="")
        sqlite_database.assert_not_called()

    def test_default_backend_connects_to_sqlite(self):
        from scripts import reconcile_publications as cli
        sentinel = object()
        with patch.object(cli, "Database", return_value=sentinel) as factory:
            result = cli._connect("local-test.db")
        self.assertIs(result, sentinel)
        factory.assert_called_once_with("local-test.db")

    def test_postgres_backend_constructs_postgres_store(self):
        from scripts import reconcile_publications as cli
        sentinel = object()
        with patch.object(cli, "PostgresPublicationStore", return_value=sentinel) as factory:
            result = cli._connect("ignored.db", backend="postgresql", postgres_dsn="postgresql://staging")
        self.assertIs(result, sentinel)
        factory.assert_called_once_with("postgresql://staging")

    def test_postgres_list_and_show_use_store_read_methods(self):
        from scripts import reconcile_publications as cli
        store = FakePostgresStore()
        with patch.object(cli, "_print_row") as printer:
            cli.list_unresolved(store)
            cli.show_attempt(store, 7)
        self.assertEqual(printer.call_count, 2)
        with self.assertRaisesRegex(SystemExit, "id=999"):
            cli.show_attempt(store, 999)

    def test_postgres_confirm_published_uses_atomic_store_reconciliation(self):
        from scripts import reconcile_publications as cli
        store = FakePostgresStore()
        args = type("Args", (), {
            "action": "confirm-published", "attempt_id": 7,
            "operator": "operator-1", "note": "Verified in Creator Center",
            "evidence": "manual-check:creator-center", "remote_post_id": "remote-7",
            "share_link": "https://www.binance.com/square/post/remote-7",
        })()
        with patch.object(cli, "_print_row") as printer:
            cli.reconcile(store, args)
        self.assertEqual(len(store.reconciliations), 1)
        call = store.reconciliations[0]
        self.assertEqual(call["attempt_id"], 7)
        self.assertEqual(call["new_status"], "PUBLISHED_CONFIRMED")
        self.assertEqual(call["remote_post_id"], "remote-7")
        self.assertEqual(call["share_link"], "https://www.binance.com/square/post/remote-7")
        self.assertEqual(call["reconciled_by"], "operator-1")
        printer.assert_called_once()

    def test_postgres_confirm_failed_requires_explicit_no_post_acknowledgement(self):
        from scripts import reconcile_publications as cli
        store = FakePostgresStore()
        args = type("Args", (), {
            "action": "confirm-failed", "attempt_id": 7,
            "operator": "operator-1", "note": "No post found",
            "evidence": "manual-check:creator-center", "share_link": "",
            "confirm_no_post_created": False,
        })()
        with self.assertRaisesRegex(SystemExit, "confirm-no-post-created"):
            cli.reconcile(store, args)
        self.assertEqual(store.reconciliations, [])

    def test_postgres_reconciliation_rejects_conflicting_known_remote_id(self):
        from scripts import reconcile_publications as cli
        store = FakePostgresStore({
            "id": 7, "status": "PUBLICATION_UNKNOWN",
            "remote_post_id": "already-known", "share_link": None,
        })
        args = type("Args", (), {
            "action": "confirm-published", "attempt_id": 7,
            "operator": "operator-1", "note": "verified",
            "evidence": "manual-check", "remote_post_id": "different-id",
            "share_link": "",
        })()
        with self.assertRaisesRegex(ValueError, "conflicts"):
            cli.reconcile(store, args)
        self.assertEqual(store.reconciliations, [])


if __name__ == "__main__":
    unittest.main()
