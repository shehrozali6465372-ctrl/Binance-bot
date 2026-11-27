import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from layer1.foundation import EligibilityDecision
from layer1.onchain import OnChainAssetMapping, OnChainIntelligenceEngine
from tests.onchain_test_support import MappingStoreStub
from layer1.onchain_ingestion import OnChainIngestionStore
from layer1.onchain_providers import (
    ProviderDataPage, ProviderHealthResult, ProviderTransportError,
    ProviderResponseReceipt, XrplAccountTransaction, _ACTIVE_PAGE_RECEIPTS,
    _approved_endpoint_profile_sha256,
)
from layer1.onchain_xrpl_worker import XrplIssuedCurrencyIngestionWorker

NOW = datetime.now(timezone.utc).replace(microsecond=0)
ACCOUNT = "rLNaPoKeeBjZe2qs6x52yVPZpZ8td4dc6w"
DESTINATION = "rf1BiGeXwwQoi8Z2ueFYTEXSwuJYfV2Jpn"
ISSUER = "rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq"
TX_HASH = "A" * 64
BLOCK_HASH = "B" * 64
MAPPING_ID = "xrpl-usd-v1"


def record(ledger=501, value="3.25", requested="100", tx_hash=TX_HASH, source=ACCOUNT, destination=DESTINATION, ledger_hash=BLOCK_HASH, close_time_iso=None):
    transaction = {"TransactionType": "Payment", "Account": source, "Destination": destination,
                   "Amount": {"currency": "USD", "issuer": ISSUER, "value": requested},
                   "Flags": 0x00020000}
    metadata = {"TransactionResult": "tesSUCCESS", "TransactionIndex": 4,
                "delivered_amount": {"currency": "USD", "issuer": ISSUER, "value": value}}
    if close_time_iso is None:
        close_time_iso = (NOW - timedelta(seconds=(502 - ledger) + 60)).isoformat().replace("+00:00", "Z")
    raw = {"validated": True, "hash": tx_hash, "ledger_index": ledger,
           "ledger_hash": ledger_hash, "close_time_iso": close_time_iso,
           "tx_json": transaction, "meta": metadata}
    return XrplAccountTransaction(
        tx_hash, ledger, close_time_iso, transaction, metadata, raw,
    )


class FakeXrplProvider:
    def __init__(self):
        self.head = 502
        self.changed_hashes = {}
        self.pages = {None: ((record(),), "page-2"), "page-2": ((), None)}
        self.calls = []
        self.fail_marker_once = None
        self.expire_marker_once = None

    def probe(self):
        return ProviderHealthResult("chainstack", "xrpl-mainnet", "AVAILABLE", NOW.isoformat(),
                                    self.head, BLOCK_HASH, finality="FINALIZED",
                                    finality_reference="validated_ledger=true")

    def fetch_ledger_header(self, index):
        return {"number": index, "hash": self.changed_hashes.get(index, BLOCK_HASH),
                "parent_hash": self.changed_hashes.get(index - 1, BLOCK_HASH),
                "timestamp": int(NOW.timestamp()) - (self.head - index) - 60,
                "finality_reference": "validated=true"}

    def fetch_account_transactions(self, account, ledger_index_min, ledger_index_max, marker=None, limit=200):
        self.calls.append((account, ledger_index_min, ledger_index_max, marker, limit))
        if marker is not None and marker == self.fail_marker_once:
            self.fail_marker_once = None
            raise ProviderTransportError("TIMEOUT", "temporary timeout")
        if marker is not None and marker == self.expire_marker_once:
            self.expire_marker_once = None
            raise ProviderTransportError("RPC_ERROR", "expired marker")
        records, next_marker = self.pages[marker]
        return ProviderDataPage("chainstack", "xrpl-mainnet", account, records,
                                next_marker, from_block=ledger_index_min,
                                to_block=ledger_index_max, finality_reference="validated=true")


class XrplIssuedCurrencyIngestionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self.tmp.name, "onchain.sqlite3")
        engine = OnChainIntelligenceEngine(
            {"xrpl-mainnet": 86400},
            receipt_signing_key=b"test-only-onchain-receipt-key-32-bytes-minimum",
            receipt_key_id="test-key-v1")
        self.ingestion_store = OnChainIngestionStore(path)
        stamp = NOW.isoformat()
        self.mapping = OnChainAssetMapping(
            MAPPING_ID, "coingecko:usd-coin", "USDC", "xrpl-mainnet", "XRPL", "xrpl-mainnet",
            "TOKEN", None, "XRPL_ISSUED_CURRENCY", 6, "VERIFIED", "OFFICIAL_PROJECT",
            "https://xrpl.org", (NOW - timedelta(hours=2)).isoformat(),
            issuer_address=ISSUER, issued_currency="USD")
        self.mapping_store = MappingStoreStub(engine, self.mapping)
        self.provider = FakeXrplProvider()
        self.worker = XrplIssuedCurrencyIngestionWorker(
            self.provider, self.mapping_store, self.ingestion_store,
            monitored_accounts={MAPPING_ID: (ACCOUNT,)}, start_ledgers={MAPPING_ID: 500},
            max_ledgers_per_run=3, page_size=10, max_pages_per_run=1,
            reorg_lookback_ledgers=3, retry_attempts=1, sleep=lambda _: None,
            clock=lambda: NOW)

    def tearDown(self):
        self.ingestion_store.close()
        self.mapping_store.close()
        self.tmp.cleanup()

    def test_rejects_monitored_account_with_invalid_classic_address_checksum(self):
        with self.assertRaisesRegex(ValueError, "checksum-valid classic XRPL account seeds"):
            XrplIssuedCurrencyIngestionWorker(
                self.provider, self.mapping_store, self.ingestion_store,
                monitored_accounts={MAPPING_ID: ("rBqiK7z9a7M8w2F7yQzvVJ5QJ8qQh2vKQ",)},
                start_ledgers={MAPPING_ID: 500}, max_ledgers_per_run=3,
            )

    def test_rejects_validated_head_above_uint32_before_scanning(self):
        self.provider.head = 0x100000000
        original = self.provider.fetch_ledger_header
        def valid_fixture_header(index):
            header = original(index)
            header["timestamp"] = int(NOW.timestamp()) - (502 - index) - 60
            return header
        self.provider.fetch_ledger_header = valid_fixture_header

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.ingestion_store.list_events("xrpl-mainnet"), [])

    def test_rejects_persisted_next_ledger_above_uint32_exhaustion_sentinel(self):
        key = f"chainstack:xrpl-mainnet:{ACCOUNT}:mapping:{MAPPING_ID}"
        checkpoint = {"mapping_id": MAPPING_ID, "account": ACCOUNT,
                      "next_ledger": 0x100000001, "range_start": None,
                      "range_end": None, "marker": None, "seen_markers": []}
        self.ingestion_store.commit_page(
            key, checkpoint, (), expected_cursor=None,
            scope_identity=("xrpl-mainnet", "chainstack", f"account:{ACCOUNT}:mapping:{MAPPING_ID}"),
        )

        with self.assertRaisesRegex(ValueError, "stored XRPL account checkpoint is malformed"):
            self.worker.run_once()

        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.ingestion_store.list_events("xrpl-mainnet"), [])

    def test_rejects_start_ledger_above_protocol_uint32_range(self):
        with self.assertRaisesRegex(ValueError, "start ledger mapping IDs and indexes are invalid"):
            XrplIssuedCurrencyIngestionWorker(
                self.provider, self.mapping_store, self.ingestion_store,
                monitored_accounts={MAPPING_ID: (ACCOUNT,)},
                start_ledgers={MAPPING_ID: 0x100000000},
                max_ledgers_per_run=3, retry_attempts=1,
            )

    def test_rejects_invalid_mapping_decimals_at_worker_boundary(self):
        from dataclasses import replace
        for decimals in (True, -1, 37, "6"):
            with self.subTest(decimals=decimals):
                with self.assertRaises(ValueError):
                    self.worker._validate_mapping(replace(self.mapping, decimals=decimals))

    def test_rejects_mapping_with_invalid_issuer_checksum(self):
        from dataclasses import replace
        invalid_mapping = replace(
            self.mapping, issuer_address="rBqiK7z9a7M8w2F7yQzvVJ5QJ8qQh2vKQ")
        with self.assertRaisesRegex(ValueError, "checksum-valid classic XRPL issuer address"):
            self.worker._validate_mapping(invalid_mapping)

    def test_rejects_mapping_with_reserved_xrp_hex_currency_code(self):
        from dataclasses import replace
        invalid_mapping = replace(
            self.mapping, issued_currency="0000000000000000000000005852500000000000")
        with self.assertRaisesRegex(ValueError, "verified issued-currency mapping"):
            self.worker._validate_mapping(invalid_mapping)

    def test_payment_source_and_destination_require_valid_classic_addresses(self):
        self.provider.pages = {None: ((record(destination="rBqiK7z9a7M8w2F7yQzvVJ5QJ8qQh2vKQ"),), None)}
        with self.assertRaisesRegex(ValueError, "checksum-valid classic addresses"):
            self.worker.run_once()
        self.assertEqual(self.ingestion_store.list_events("xrpl-mainnet"), [])

    def test_ingests_only_actual_delivered_issued_currency_payment(self):
        self.provider.pages = {None: ((record(),), None)}
        result = self.worker.run_once()
        scope = f"account:{ACCOUNT}:mapping:{MAPPING_ID}"
        events = self.ingestion_store.list_events("xrpl-mainnet", canonical_only=True)
        self.assertEqual(result["events_inserted"], 1)
        self.assertEqual(events[0].amount_raw, "3250000")
        self.assertEqual(events[0].scope, scope)
        self.assertEqual(events[0].event_id, TX_HASH.lower())
        self.assertEqual(events[0].block_hash, BLOCK_HASH.lower())
        self.assertEqual(events[0].finality_snapshot.status, "FINALIZED")
        self.assertEqual(events[0].finality_snapshot.reference, "validated=true")
        checkpoint = self.ingestion_store.get_checkpoint(
            f"chainstack:xrpl-mainnet:{ACCOUNT}:mapping:{MAPPING_ID}"
        )
        self.assertEqual(checkpoint["validated_head_height"], self.provider.head)
        self.assertEqual(checkpoint["finality_reference"], "validated=true")
        self.assertEqual(events[0].from_address, ACCOUNT)
        self.assertEqual(events[0].to_address, DESTINATION)

    def test_fixed_ledger_range_and_marker_resume_after_timeout(self):
        first = self.worker.run_once()
        self.assertEqual(first["pages_committed"], 1)
        key = f"chainstack:xrpl-mainnet:{ACCOUNT}:mapping:{MAPPING_ID}"
        checkpoint = self.ingestion_store.get_checkpoint(key)
        self.assertEqual(checkpoint["marker"], "page-2")
        self.provider.fail_marker_once = "page-2"
        with self.assertRaises(ProviderTransportError):
            self.worker.run_once()
        self.assertEqual(self.ingestion_store.get_checkpoint(key)["marker"], "page-2")
        self.worker.run_once()
        self.assertIsNone(self.ingestion_store.get_checkpoint(key)["marker"])
        self.assertEqual(self.ingestion_store.get_checkpoint(key)["next_ledger"], 503)
        self.assertEqual(self.provider.calls[0][1:4], (500, 502, None))
        self.assertEqual(self.provider.calls[1][1:4], (500, 502, "page-2"))

    def test_every_xrpl_pagination_page_repeats_head_and_canonical_header_receipts(self):
        class ReceiptProvider(FakeXrplProvider):
            @staticmethod
            def _capture(method):
                collector = _ACTIVE_PAGE_RECEIPTS.get()
                collector.append(ProviderResponseReceipt(
                    sequence=len(collector) + 1, provider="chainstack",
                    network_id="xrpl-mainnet", method=method,
                    request_sha256=("a" * 64), response_sha256=("b" * 64),
                    response_bytes=64, http_status=200,
                    received_at=NOW.isoformat(),
                    endpoint_profile_sha256=_approved_endpoint_profile_sha256("chainstack", "xrpl-mainnet"),
                ))

            def probe(self):
                self._capture("server_info")
                return super().probe()

            def fetch_ledger_header(self, index):
                self._capture("ledger")
                return super().fetch_ledger_header(index)

            def fetch_account_transactions(self, *args, **kwargs):
                self._capture("account_tx")
                return super().fetch_account_transactions(*args, **kwargs)

        provider = ReceiptProvider()
        worker = XrplIssuedCurrencyIngestionWorker(
            provider, self.mapping_store, self.ingestion_store,
            monitored_accounts={MAPPING_ID: (ACCOUNT,)}, start_ledgers={MAPPING_ID: 500},
            max_ledgers_per_run=3, page_size=10, max_pages_per_run=2,
            reorg_lookback_ledgers=0, retry_attempts=1, sleep=lambda _: None,
            clock=lambda: NOW,
        )
        result = worker.run_once()
        self.assertEqual(result["pages_committed"], 2)
        self.assertEqual(result["page_acceptances_signed"], 2)
        cursor_key = f"chainstack:xrpl-mainnet:{ACCOUNT}:mapping:{MAPPING_ID}"
        rows = self.ingestion_store.conn.execute(
            "SELECT page_id, receipts_json FROM layer1_onchain_ingestion_pages WHERE cursor_key=? ORDER BY created_at, page_id",
            (cursor_key,),
        ).fetchall()
        payloads = [(row[0], __import__("json").loads(row[1])) for row in rows]
        committed_pages = [(page_id, payload) for page_id, payload in payloads if payload]
        page_methods = [[item["method"] for item in payload] for _, payload in committed_pages]
        self.assertEqual(len(page_methods), 2)
        for page_id, _ in committed_pages:
            self.assertTrue(self.mapping_store.engine.verify_ingestion_page_acceptance(
                self.ingestion_store, cursor_key, page_id))
        for methods in page_methods:
            self.assertIn("server_info", methods)
            self.assertEqual(methods.count("ledger"), 4)
            self.assertIn("account_tx", methods)

    def test_expired_opaque_marker_restarts_same_fixed_range_from_first_page(self):
        self.worker.run_once()
        self.provider.expire_marker_once = "page-2"
        result = self.worker.run_once()
        self.assertEqual(result["markers_reset"], 1)
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            f"chainstack:xrpl-mainnet:{ACCOUNT}:mapping:{MAPPING_ID}")["marker"])
        self.worker.run_once()
        self.assertEqual(self.provider.calls[-1][3], None)

    def test_rejects_non_finite_provider_marker_as_controlled_provider_error(self):
        self.provider.pages = {None: ((record(),), float("nan"))}
        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()
        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            f"chainstack:xrpl-mainnet:{ACCOUNT}:mapping:{MAPPING_ID}")["marker"])

    def test_rejects_non_finite_persisted_marker_before_provider_page_request(self):
        self.worker.run_once()
        key = f"chainstack:xrpl-mainnet:{ACCOUNT}:mapping:{MAPPING_ID}"
        original_get_checkpoint = self.ingestion_store.get_checkpoint
        def corrupted_checkpoint(cursor_key):
            value = original_get_checkpoint(cursor_key)
            if cursor_key == key:
                value["marker"] = float("nan")
            return value
        self.ingestion_store.get_checkpoint = corrupted_checkpoint
        self.provider.calls.clear()
        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()
        self.assertEqual(error.exception.reason_code, "INVALID_CHECKPOINT")
        self.assertEqual(self.provider.calls, [])

    def test_repeated_pagination_marker_is_rejected(self):
        self.worker.max_pages_per_run = 2
        self.provider.pages = {None: ((record(),), "page-2"), "page-2": ((), "page-2")}
        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()
        self.assertEqual(error.exception.reason_code, "XRPL_MARKER_LOOP")
        checkpoint = self.ingestion_store.get_checkpoint(
            f"chainstack:xrpl-mainnet:{ACCOUNT}:mapping:{MAPPING_ID}")
        self.assertEqual(checkpoint["marker"], "page-2")

    def test_rejects_validated_ledger_with_wrong_parent_hash_before_account_page(self):
        original = self.provider.fetch_ledger_header
        def broken_parent(index):
            header = original(index)
            if index == 501:
                header["parent_hash"] = "C" * 64
            return header
        self.provider.fetch_ledger_header = broken_parent
        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()
        self.assertEqual(error.exception.reason_code, "XRPL_PARENT_HASH_MISMATCH")
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.ingestion_store.list_events("xrpl-mainnet"), [])

    def test_rejects_non_monotonic_validated_ledger_close_times(self):
        original = self.provider.fetch_ledger_header
        def non_monotonic_time(index):
            header = original(index)
            if index == 501:
                header["timestamp"] = original(500)["timestamp"]
            return header
        self.provider.fetch_ledger_header = non_monotonic_time

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "XRPL_LEDGER_TIME_NOT_MONOTONIC")
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.ingestion_store.list_events("xrpl-mainnet"), [])

    def test_rejects_first_ledger_parent_hash_mismatch_against_preceding_anchor(self):
        original = self.provider.fetch_ledger_header
        def broken_first_parent(index):
            header = original(index)
            if index == 500:
                header["parent_hash"] = "C" * 64
            return header
        self.provider.fetch_ledger_header = broken_first_parent

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "XRPL_PARENT_HASH_MISMATCH")
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.ingestion_store.list_events("xrpl-mainnet"), [])

    def test_validated_ledger_hash_change_tombstones_then_replays_event(self):
        self.provider.pages = {None: ((record(),), None)}
        self.worker.run_once()
        self.provider.changed_hashes[501] = "C" * 64
        self.provider.pages = {None: ((record(ledger_hash="C" * 64),), None)}
        result = self.worker.run_once()
        scope = f"account:{ACCOUNT}:mapping:{MAPPING_ID}"
        event = self.ingestion_store.get_event(TX_HASH.lower(), "xrpl-mainnet", "chainstack", scope)
        self.assertGreaterEqual(result["reorg_ledgers_detected"], 1)
        self.assertEqual(event.canonical_status, "CANONICAL")
        self.assertEqual(event.block_hash, ("C" * 64).lower())

    def test_rejects_xrpl_header_timestamp_outside_protocol_uint32_close_time_range(self):
        original = self.provider.fetch_ledger_header
        def out_of_range_header(index):
            header = original(index)
            if index == 502:
                header["timestamp"] = 253402300800
            return header
        self.provider.fetch_ledger_header = out_of_range_header
        impossible_close_time = "9999-12-31T23:59:59Z"
        self.provider.pages = {None: ((record(ledger=502, close_time_iso=impossible_close_time),), None)}

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.ingestion_store.list_events("xrpl-mainnet"), [])

    def test_transaction_close_time_must_match_independently_verified_ledger_header(self):
        # The account_tx record claims the same ledger hash/index but a different
        # ledger close time. The worker must not silently replace this evidence
        # with the timestamp from its separate ledger-header request.
        mismatched_time = (NOW - timedelta(seconds=60)).isoformat().replace("+00:00", "Z")
        self.provider.pages = {None: ((record(close_time_iso=mismatched_time),), None)}

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "XRPL_LEDGER_TIME_MISMATCH")
        self.assertEqual(self.ingestion_store.list_events("xrpl-mainnet"), [])
        checkpoint = self.ingestion_store.get_checkpoint(
            f"chainstack:xrpl-mainnet:{ACCOUNT}:mapping:{MAPPING_ID}")
        self.assertEqual(checkpoint["next_ledger"], 500)
        self.assertIsNone(checkpoint["marker"])

    def test_transaction_ledger_hash_mismatch_cannot_create_event_or_advance_checkpoint(self):
        self.provider.pages = {None: ((record(ledger_hash="C" * 64),), None)}
        with self.assertRaisesRegex(ValueError, "ledger hash"):
            self.worker.run_once()
        self.assertEqual(self.ingestion_store.list_events("xrpl-mainnet"), [])
        checkpoint = self.ingestion_store.get_checkpoint(
            f"chainstack:xrpl-mainnet:{ACCOUNT}:mapping:{MAPPING_ID}")
        self.assertEqual(checkpoint["next_ledger"], 500)
        self.assertIsNone(checkpoint["marker"])

    def test_account_side_evidence_must_match_payment_source_or_destination(self):
        self.provider.pages = {None: ((record(source=DESTINATION, destination=ISSUER),), None)}
        with self.assertRaisesRegex(ValueError, "not the payment source or destination"):
            self.worker.run_once()
        self.assertEqual(self.ingestion_store.list_events("xrpl-mainnet"), [])

    def test_unvalidated_record_does_not_advance_checkpoint(self):
        invalid = record()
        invalid = XrplAccountTransaction(invalid.transaction_hash, invalid.ledger_index,
                                         invalid.close_time_iso, invalid.transaction,
                                         invalid.metadata, {"validated": False, "hash": invalid.transaction_hash,
                                                           "ledger_index": invalid.ledger_index,
                                                           "close_time_iso": invalid.close_time_iso})
        self.provider.pages = {None: ((invalid,), None)}
        with self.assertRaisesRegex(ValueError, "validated-ledger proof"):
            self.worker.run_once()
        checkpoint = self.ingestion_store.get_checkpoint(
            f"chainstack:xrpl-mainnet:{ACCOUNT}:mapping:{MAPPING_ID}")
        self.assertEqual(checkpoint["next_ledger"], 500)
        self.assertIsNone(checkpoint["marker"])

    def test_reorg_during_active_marker_range_restarts_from_first_page(self):
        self.worker.run_once()  # page 1 committed with an opaque marker
        self.provider.changed_hashes[501] = "D" * 64
        self.provider.pages = {None: ((record(ledger_hash="D" * 64),), None)}
        self.worker.run_once()  # detects active-range hash change and restarts
        self.assertIsNone(self.provider.calls[-1][3])
        scope = f"account:{ACCOUNT}:mapping:{MAPPING_ID}"
        event = self.ingestion_store.get_event(TX_HASH.lower(), "xrpl-mainnet", "chainstack", scope)
        self.assertEqual(event.block_hash, ("D" * 64).lower())
        self.assertEqual(event.canonical_status, "CANONICAL")

    def test_malformed_partial_payment_without_delivered_amount_never_uses_requested_amount(self):
        invalid = record(requested="100")
        invalid.metadata.pop("delivered_amount")
        self.provider.pages = {None: ((invalid,), None)}
        with self.assertRaisesRegex(ValueError, "delivered_amount"):
            self.worker.run_once()
        self.assertEqual(self.ingestion_store.list_events("xrpl-mainnet"), [])

    def test_provider_page_cannot_exceed_configured_page_size(self):
        records = tuple(record(tx_hash=f"{index:064X}") for index in range(1, 12))
        self.provider.pages = {None: (records, None)}

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "PAGE_LIMIT_EXCEEDED")
        checkpoint = self.ingestion_store.get_checkpoint(
            self.worker._cursor_key(ACCOUNT, self.mapping))
        self.assertEqual(checkpoint["next_ledger"], 500)
        self.assertIsNone(checkpoint["marker"])
        self.assertEqual(self.ingestion_store.list_events("xrpl-mainnet"), [])


if __name__ == "__main__":
    unittest.main()
