"""Disposable PostgreSQL round-trip acceptance for signed CMS announcement rows."""

from __future__ import annotations

import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from layer1.announcement_importer import import_recent_binance_announcements
from layer1.source_receipts import create_source_ingestion_receipt

TEST_DSN = os.getenv("TEST_POSTGRES_DSN", "").strip()
TEST_ALLOWED_HOST = os.getenv("TEST_POSTGRES_ALLOWED_HOST", "").strip()
CMS_KEY_ID = "cms-postgres-test-v1"
CMS_KEY = b"cms-postgres-integration-key-material-32-bytes"


class RecordingStore:
    def __init__(self):
        self.saved = []

    def save_announcement(self, evidence):
        self.saved.append(evidence)


@unittest.skipUnless(TEST_DSN, "TEST_POSTGRES_DSN is not configured; disposable PostgreSQL acceptance is skipped")
class AnnouncementImporterPostgresReceiptTests(unittest.TestCase):
    def setUp(self):
        from psycopg import connect
        from tests.postgres_test_support import validate_postgres_test_target

        # This guard must pass before this test creates a schema or writes any rows.
        validate_postgres_test_target(TEST_DSN, TEST_ALLOWED_HOST)
        self.connect = connect
        self.schema = "cms_receipt_it_" + uuid.uuid4().hex
        self.admin = connect(TEST_DSN, application_name="cms_receipt_importer_test_setup")
        self.addCleanup(self._cleanup_schema)
        self.admin.execute(f'CREATE SCHEMA "{self.schema}"')
        self.admin.execute(f'''
            CREATE TABLE "{self.schema}".binance_announcement_events (
                id BIGSERIAL PRIMARY KEY,
                source_id CHAR(64) NOT NULL,
                content_hash CHAR(64) NOT NULL UNIQUE,
                topic TEXT NOT NULL CHECK (topic = 'com_announcement_en'),
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                publisher TEXT NOT NULL,
                source_url TEXT NOT NULL,
                published_at TIMESTAMPTZ NOT NULL,
                observed_at TIMESTAMPTZ NOT NULL,
                catalog_id TEXT NOT NULL,
                catalog_name TEXT NOT NULL,
                disclaimer TEXT NOT NULL,
                raw_payload JSONB NOT NULL,
                ingestion_receipt JSONB,
                inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        ''')
        self.admin.commit()
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.published = self.now - timedelta(minutes=30)
        self.source_id = "a" * 64
        self.content_hash = "b" * 64
        self.payload = self._payload()
        self.receipt = create_source_ingestion_receipt(
            self.payload, authority_id="binance_announcement_cms",
            key_id=CMS_KEY_ID, signing_key=CMS_KEY,
        ).to_dict()
        self._insert_event(self.source_id, self.content_hash, self.receipt)
        self.candidates = [SimpleNamespace(symbol="BTC", asset_id="coingecko:bitcoin")]
        self.store = RecordingStore()
        self.keys = {CMS_KEY_ID: CMS_KEY}
        self.trusted = {CMS_KEY_ID}

    def _cleanup_schema(self):
        try:
            self.admin.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
            self.admin.commit()
        finally:
            self.admin.close()

    def _payload(self):
        timestamp = self.published.isoformat(timespec="microseconds")
        return {
            "authority_id": "binance_announcement_cms",
            "schema_version": "cms-announcement-normalized-v1",
            "topic": "com_announcement_en",
            "catalog_id": "48",
            "source_id": self.source_id,
            "content_hash": self.content_hash,
            "catalog_name": "New Cryptocurrency Listing",
            "event_type": "listing",
            "title": "Binance will list Example (BTC)",
            "body": "Official announcement body",
            "disclaimer": "Risk notice",
            "publisher": "Binance",
            "source_url": "https://www.binance.com/en/support/announcement",
            "published_at": timestamp,
            "observed_at": timestamp,
        }

    def _insert_event(self, source_id, content_hash, receipt):
        self.admin.execute(
            f'''INSERT INTO "{self.schema}".binance_announcement_events
               (source_id, content_hash, topic, event_type, title, body, publisher, source_url,
                published_at, observed_at, catalog_id, catalog_name, disclaimer, raw_payload, ingestion_receipt)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)''',
            (
                source_id, content_hash, "com_announcement_en", "listing",
                self.payload["title"], self.payload["body"], "Binance", self.payload["source_url"],
                self.published, self.published, "48", self.payload["catalog_name"],
                self.payload["disclaimer"], json.dumps(self.payload),
                json.dumps(receipt) if receipt is not None else None,
            ),
        )
        self.admin.commit()

    def _connect_read_only(self, url, **kwargs):
        from psycopg.conninfo import conninfo_to_dict
        options = kwargs["options"] + f" -c search_path={self.schema}"
        host = conninfo_to_dict(url).get("host", "")
        local_host = host in {"localhost", "127.0.0.1", "::1"} or host.startswith("/")
        connect_options = {
            "options": options,
            "application_name": "cms_receipt_importer_test_readonly",
        }
        if not local_host:
            connect_options["sslmode"] = kwargs["sslmode"]
        # The CI service uses local loopback PostgreSQL without TLS; remote test
        # targets keep the importer's verify-full requirement intact.
        return self.connect(url, **connect_options)

    def _import(self, store=None):
        return import_recent_binance_announcements(
            TEST_DSN, self.candidates, store or self.store,
            connect_factory=self._connect_read_only, now=self.now,
            receipt_verification_keys=self.keys,
            trusted_receipt_key_ids=self.trusted,
        )

    def test_postgres_jsonb_round_trip_verifies_receipt_and_rejects_legacy_null(self):
        self._insert_event("c" * 64, "d" * 64, None)
        result = self._import()
        self.assertEqual(result["rows_read"], 2)
        self.assertEqual(result["evidence_saved"], 1)
        self.assertEqual(result["untrusted_rows"], 1)
        self.assertEqual(len(self.store.saved), 1)
        self.assertEqual(self.store.saved[0].source_id, self.source_id)

    def test_postgres_row_tampering_invalidates_the_persisted_receipt(self):
        self.admin.execute(
            f'''UPDATE "{self.schema}".binance_announcement_events
                SET title = %s WHERE source_id = %s''',
            ("Tampered title (BTC)", self.source_id),
        )
        self.admin.commit()
        result = self._import()
        self.assertEqual(result["evidence_saved"], 0)
        self.assertEqual(result["untrusted_rows"], 1)
        self.assertEqual(self.store.saved, [])


if __name__ == "__main__":
    unittest.main()
