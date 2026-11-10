import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from layer1.announcement_importer import import_recent_binance_announcements


NOW = datetime.now(timezone.utc).replace(microsecond=0)
PUBLISHED = NOW - timedelta(minutes=30)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.params = None
        self.closed = False

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, rows):
        self.fake_cursor = FakeCursor(rows)
        self.closed = False

    def cursor(self):
        return self.fake_cursor

    def close(self):
        self.closed = True


class FakeStore:
    def __init__(self):
        self.saved = []

    def save_announcement(self, evidence):
        self.saved.append(evidence)


def row(source_id="a" * 64, content_hash="b" * 64, event_type="listing",
        title="Binance will list Example (BTC)", body="Support for BTC and ETH (ETH)."):
    return (
        source_id, content_hash, event_type, title, body, "Binance",
        "https://www.binance.com/en/support/announcement",
        PUBLISHED, PUBLISHED,
    )


class AnnouncementImporterDependencyTests(unittest.TestCase):
    def test_optional_importer_runtime_declares_psycopg3(self):
        manifest = Path(__file__).resolve().parents[1] / "requirements-announcement-importer.txt"
        self.assertTrue(manifest.is_file(), "optional importer dependency manifest is missing")
        requirements = [
            line.split("#", 1)[0].strip().lower()
            for line in manifest.read_text(encoding="utf-8").splitlines()
        ]
        self.assertTrue(
            any(line.startswith("psycopg[binary]") for line in requirements),
            "the optional importer runtime must declare psycopg 3 with its binary extra",
        )

    def test_scheduled_agent_installs_optional_importer_dependencies(self):
        workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "run_bot.yml"
        self.assertIn(
            "pip install -r requirements-announcement-importer.txt",
            workflow.read_text(encoding="utf-8"),
            "the scheduled agent must install the optional importer driver",
        )


class AnnouncementImporterTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [
            SimpleNamespace(symbol="BTC", asset_id="coingecko:bitcoin"),
            SimpleNamespace(symbol="ETH", asset_id="coingecko:ethereum"),
        ]
        self.store = FakeStore()
        self.connection = FakeConnection([row()])
        self.connect_calls = []

    def connector(self, rows=None):
        connection = self.connection if rows is None else FakeConnection(rows)

        def connect(url, **kwargs):
            self.connect_calls.append((url, kwargs))
            return connection

        return connect, connection

    def test_imports_only_explicit_parenthesized_candidate_tickers(self):
        connect, connection = self.connector()
        result = import_recent_binance_announcements(
            "postgresql://example.invalid/db", self.candidates, self.store,
            connect_factory=connect, now=NOW,
        )

        self.assertEqual(result["rows_read"], 1)
        self.assertEqual(result["evidence_saved"], 1)
        self.assertEqual(result["unmatched_rows"], 0)
        self.assertEqual(len(self.store.saved), 1)
        self.assertEqual(
            self.store.saved[0].asset_ids,
            ("coingecko:bitcoin", "coingecko:ethereum"),
        )
        self.assertEqual(
            set(result["by_asset_id"]),
            {"coingecko:bitcoin", "coingecko:ethereum"},
        )
        self.assertTrue(connection.fake_cursor.closed)
        self.assertTrue(connection.closed)
        self.assertEqual(self.connect_calls[0][1]["sslmode"], "require")
        self.assertEqual(
            self.connect_calls[0][1]["options"],
            "-c default_transaction_read_only=on",
        )
        self.assertIn("SELECT", connection.fake_cursor.query.upper())
        self.assertNotRegex(
            connection.fake_cursor.query,
            r"(?im)^\s*(INSERT|UPDATE|DELETE|ALTER|DROP|CREATE)\b",
        )

    def test_free_standing_ticker_word_does_not_match(self):
        connect, _ = self.connector([
            row(title="Binance discusses BTC market activity", body="No parenthesized symbol.")
        ])
        result = import_recent_binance_announcements(
            "postgresql://example.invalid/db", self.candidates, self.store,
            connect_factory=connect, now=NOW,
        )
        self.assertEqual(result["evidence_saved"], 0)
        self.assertEqual(result["unmatched_rows"], 1)
        self.assertEqual(self.store.saved, [])

    def test_ambiguous_symbol_is_not_assigned_to_either_asset(self):
        candidates = self.candidates + [
            SimpleNamespace(symbol="BTC", asset_id="coingecko:wrapped-bitcoin")
        ]
        connect, _ = self.connector([row(title="Listing notice (BTC)", body="")])
        result = import_recent_binance_announcements(
            "postgresql://example.invalid/db", candidates, self.store,
            connect_factory=connect, now=NOW,
        )
        self.assertEqual(result["ambiguous_symbols"], ["BTC"])
        self.assertEqual(result["evidence_saved"], 0)
        self.assertEqual(result["unmatched_rows"], 1)

    def test_invalid_event_type_is_rejected(self):
        connect, _ = self.connector([row(event_type="made_up_event")])
        result = import_recent_binance_announcements(
            "postgresql://example.invalid/db", self.candidates, self.store,
            connect_factory=connect, now=NOW,
        )
        self.assertEqual(result["invalid_rows"], 1)
        self.assertEqual(result["evidence_saved"], 0)
        self.assertEqual(self.store.saved, [])

    def test_invalid_database_url_and_bounds_are_rejected_before_connect(self):
        connect, _ = self.connector([])
        with self.assertRaises(ValueError):
            import_recent_binance_announcements(
                "", self.candidates, self.store, connect_factory=connect, now=NOW
            )
        with self.assertRaises(ValueError):
            import_recent_binance_announcements(
                "postgresql://example.invalid/db", self.candidates, self.store,
                connect_factory=connect, now=NOW, max_rows=1001,
            )
        self.assertEqual(self.connect_calls, [])

    def test_query_is_limited_to_recent_window(self):
        connect, connection = self.connector([])
        import_recent_binance_announcements(
            "postgresql://example.invalid/db", self.candidates, self.store,
            connect_factory=connect, now=NOW, lookback_days=3, max_rows=50,
        )
        lower, upper, limit = connection.fake_cursor.params
        self.assertEqual(lower, NOW - timedelta(days=3))
        self.assertEqual(upper, NOW + timedelta(minutes=5))
        self.assertEqual(limit, 50)


if __name__ == "__main__":
    unittest.main()
