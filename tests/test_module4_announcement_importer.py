import unittest
import json
from unittest.mock import patch
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from layer1.announcement_importer import import_recent_binance_announcements
from layer1.source_receipts import create_source_ingestion_receipt


NOW = datetime.now(timezone.utc).replace(microsecond=0)
PUBLISHED = NOW - timedelta(minutes=30)
CMS_TEST_KEY = b"cms-importer-test-key-material-at-least-thirty-two-bytes"
CMS_TEST_KEY_ID = "cms-importer-v1"


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
        title="Binance will list Example (BTC)", body="Support for BTC and ETH (ETH).",
        receipt=True, receipt_content_hash=None, receipt_title=None):
    published = PUBLISHED.isoformat(timespec="microseconds")
    observed = PUBLISHED.isoformat(timespec="microseconds")
    receipt_value = None
    if receipt:
        payload = {
            "authority_id": "binance_announcement_cms",
            "schema_version": "cms-announcement-normalized-v1",
            "topic": "com_announcement_en",
            "catalog_id": "48",
            "source_id": source_id,
            "content_hash": receipt_content_hash or content_hash,
            "catalog_name": "New Cryptocurrency Listing",
            "event_type": event_type,
            "title": receipt_title if receipt_title is not None else title,
            "body": body,
            "disclaimer": "Risk notice",
            "publisher": "Binance",
            "source_url": "https://www.binance.com/en/support/announcement",
            "published_at": published,
            "observed_at": observed,
        }
        receipt_value = create_source_ingestion_receipt(
            payload, authority_id="binance_announcement_cms",
            key_id=CMS_TEST_KEY_ID, signing_key=CMS_TEST_KEY,
        ).to_dict()
    return (
        source_id, content_hash, event_type, title, body, "Binance",
        "https://www.binance.com/en/support/announcement",
        PUBLISHED, PUBLISHED, "48", "New Cryptocurrency Listing", "Risk notice", receipt_value,
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
        content = workflow.read_text(encoding="utf-8")
        self.assertIn("pip install -r requirements-announcement-importer.txt", content)
        self.assertIn('DRY_RUN: "1"', content)
        self.assertIn("ANNOUNCEMENT_DATABASE_URL: ${{ secrets.ANNOUNCEMENT_DATABASE_URL }}", content)
        self.assertIn("BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON: ${{ secrets.BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON }}", content)
        self.assertIn("BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS: ${{ vars.BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS }}", content)
        self.assertNotIn("BINANCE_SOURCE_RECEIPT_HMAC_KEYRING_JSON", content)
        self.assertNotIn("secrets.BINANCE_ANNOUNCEMENT_DATABASE_URL", content)


class AnnouncementImporterTests(unittest.TestCase):
    def setUp(self):
        self.receipt_env = patch.dict("os.environ", {
            "BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON": json.dumps({CMS_TEST_KEY_ID: CMS_TEST_KEY.hex()}),
            "BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS": CMS_TEST_KEY_ID,
        }, clear=False)
        self.receipt_env.start()
        self.addCleanup(self.receipt_env.stop)
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
        self.assertEqual(result["untrusted_rows"], 0)
        self.assertEqual(result["unmatched_rows"], 0)
        self.assertEqual(len(self.store.saved), 1)
        self.assertEqual(self.store.saved[0].body, "Support for BTC and ETH (ETH).")
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
        self.assertEqual(self.connect_calls[0][1]["sslmode"], "verify-full")
        self.assertEqual(
            self.connect_calls[0][1]["options"],
            "-c default_transaction_read_only=on",
        )
        self.assertIn("SELECT", connection.fake_cursor.query.upper())
        self.assertIn("ingestion_receipt", connection.fake_cursor.query)
        self.assertIn("catalog_id", connection.fake_cursor.query)
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


    def test_missing_receipt_is_counted_untrusted_and_never_persisted(self):
        connect, _ = self.connector([row(receipt=False)])
        result = import_recent_binance_announcements(
            "postgresql://example.invalid/db", self.candidates, self.store,
            connect_factory=connect, now=NOW,
        )
        self.assertEqual(result["untrusted_rows"], 1)
        self.assertEqual(result["evidence_saved"], 0)
        self.assertEqual(self.store.saved, [])

    def test_payload_tampering_after_receipt_creation_is_rejected(self):
        connect, _ = self.connector([row(content_hash="c" * 64, receipt_content_hash="b" * 64)])
        result = import_recent_binance_announcements(
            "postgresql://example.invalid/db", self.candidates, self.store,
            connect_factory=connect, now=NOW,
        )
        self.assertEqual(result["untrusted_rows"], 1)
        self.assertEqual(result["evidence_saved"], 0)


    def test_row_title_tampering_is_rejected_even_when_receipt_and_content_hash_remain_unchanged(self):
        connect, _ = self.connector([row(
            title="Tampered listing title (BTC)",
            receipt_title="Original signed title (BTC)",
        )])
        result = import_recent_binance_announcements(
            "postgresql://example.invalid/db", self.candidates, self.store,
            connect_factory=connect, now=NOW,
        )
        self.assertEqual(result["untrusted_rows"], 1)
        self.assertEqual(result["evidence_saved"], 0)
        self.assertEqual(self.store.saved, [])

    def test_untrusted_receipt_key_is_rejected(self):
        from unittest.mock import patch
        connect, _ = self.connector([row()])
        with patch.dict("os.environ", {
            "BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON": json.dumps({CMS_TEST_KEY_ID: CMS_TEST_KEY.hex()}),
            "BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS": "different-key",
        }, clear=True):
            with self.assertRaisesRegex(ValueError, "trusted key IDs must exist in the keyring"):
                import_recent_binance_announcements(
                    "postgresql://example.invalid/db", self.candidates, self.store,
                    connect_factory=connect, now=NOW,
                )
        self.assertEqual(self.store.saved, [])

    def test_no_key_configuration_does_not_promote_any_cms_evidence(self):
        connect, _ = self.connector([row()])
        with patch.dict("os.environ", {}, clear=True):
            result = import_recent_binance_announcements(
                "postgresql://example.invalid/db", self.candidates, self.store,
                connect_factory=connect, now=NOW,
            )
        self.assertEqual(result["untrusted_rows"], 1)
        self.assertEqual(result["evidence_saved"], 0)
