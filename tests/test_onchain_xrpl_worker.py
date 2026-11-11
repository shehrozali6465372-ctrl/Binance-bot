import os
import tempfile
import unittest
from datetime import datetime, timezone

from layer1.foundation import EligibilityDecision
from layer1.onchain import OnChainAssetMapping, OnChainIntelligenceEngine, OnChainObservation, OnChainStore
from layer1.onchain_ingestion import OnChainIngestionStore
from layer1.onchain_providers import ProviderDataPage, ProviderHealthResult, ProviderTransportError, XrplAccountTransaction
from layer1.onchain_xrpl_worker import XrplIssuedCurrencyIngestionWorker

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
ACCOUNT = "rLNaPoKeeBjZe2qs6x52yVPZpZ8td4dc6w"
DESTINATION = "rBqiK7z9a7M8w2F7yQzvVJ5QJ8qQh2vKQ"
ISSUER = "rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq"
TX_HASH = "A" * 64
BLOCK_HASH = "B" * 64
MAPPING_ID = "xrpl-usd-v1"


def record(ledger=501, value="3.25", requested="100", tx_hash=TX_HASH, source=ACCOUNT, destination=DESTINATION):
    return XrplAccountTransaction(
        tx_hash, ledger, "2026-11-11T12:00:00Z",
        {"TransactionType": "Payment", "Account": source, "Destination": destination,
         "Amount": {"currency": "USD", "issuer": ISSUER, "value": requested},
         "Flags": 0x00020000},
        {"TransactionResult": "tesSUCCESS", "TransactionIndex": 4,
         "delivered_amount": {"currency": "USD", "issuer": ISSUER, "value": value}},
        {"validated": True, "hash": tx_hash, "ledger_index": ledger},
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
                "timestamp": 1794398400, "finality_reference": "validated=true"}

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
        self.mapping_store = OnChainStore(path, OnChainIntelligenceEngine({"xrpl-mainnet": 86400}))
        self.ingestion_store = OnChainIngestionStore(path)
        stamp = NOW.isoformat()
        self.mapping = OnChainAssetMapping(
            MAPPING_ID, "coingecko:usd-coin", "USDC", "xrpl-mainnet", "XRPL", "xrpl-mainnet",
            "TOKEN", None, "XRPL_ISSUED_CURRENCY", 6, "VERIFIED", "OFFICIAL_PROJECT",
            "https://xrpl.org", "2026-11-11T10:00:00+00:00",
            issuer_address=ISSUER, issued_currency="USD")
        eligibility = EligibilityDecision(
            status="ELIGIBLE", asset_id="coingecko:usd-coin", symbol="USDC",
            eligible_pairs=("USDCUSDT",), verified_at=stamp,
            identity_proof_status="VERIFIED", identity_proof_source="coingecko_coin_tickers",
            identity_proof_verified_at=stamp, identity_proof_source_timestamp=stamp,
            identity_proof_data_hash="a" * 64)
        observation = OnChainObservation(
            "xrpl-map-proof", MAPPING_ID, "coingecko:usd-coin", "xrpl-mainnet", "xrpl-mainnet",
            "chainstack", "xrpl-mainnet", "TRANSFER", 499, BLOCK_HASH, TX_HASH,
            stamp, stamp, "FINALIZED", "validated_ledger=true")
        self.mapping_store.save_verified(eligibility, self.mapping, observation)
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

    def test_expired_opaque_marker_restarts_same_fixed_range_from_first_page(self):
        self.worker.run_once()
        self.provider.expire_marker_once = "page-2"
        result = self.worker.run_once()
        self.assertEqual(result["markers_reset"], 1)
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            f"chainstack:xrpl-mainnet:{ACCOUNT}:mapping:{MAPPING_ID}")["marker"])
        self.worker.run_once()
        self.assertEqual(self.provider.calls[-1][3], None)

    def test_repeated_pagination_marker_is_rejected(self):
        self.worker.max_pages_per_run = 2
        self.provider.pages = {None: ((record(),), "page-2"), "page-2": ((), "page-2")}
        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()
        self.assertEqual(error.exception.reason_code, "XRPL_MARKER_LOOP")
        checkpoint = self.ingestion_store.get_checkpoint(
            f"chainstack:xrpl-mainnet:{ACCOUNT}:mapping:{MAPPING_ID}")
        self.assertEqual(checkpoint["marker"], "page-2")

    def test_validated_ledger_hash_change_tombstones_then_replays_event(self):
        self.provider.pages = {None: ((record(),), None)}
        self.worker.run_once()
        self.provider.changed_hashes[501] = "C" * 64
        result = self.worker.run_once()
        scope = f"account:{ACCOUNT}:mapping:{MAPPING_ID}"
        event = self.ingestion_store.get_event(TX_HASH.lower(), "xrpl-mainnet", "chainstack", scope)
        self.assertGreaterEqual(result["reorg_ledgers_detected"], 1)
        self.assertEqual(event.canonical_status, "CANONICAL")
        self.assertEqual(event.block_hash, ("C" * 64).lower())

    def test_account_side_evidence_must_match_payment_source_or_destination(self):
        self.provider.pages = {None: ((record(source=DESTINATION, destination=ISSUER),), None)}
        with self.assertRaisesRegex(ValueError, "not the payment source or destination"):
            self.worker.run_once()
        self.assertEqual(self.ingestion_store.list_events("xrpl-mainnet"), [])

    def test_unvalidated_record_does_not_advance_checkpoint(self):
        invalid = record()
        invalid = XrplAccountTransaction(invalid.transaction_hash, invalid.ledger_index,
                                         invalid.close_time_iso, invalid.transaction,
                                         invalid.metadata, {"validated": False, "hash": invalid.transaction_hash, "ledger_index": invalid.ledger_index})
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


if __name__ == "__main__":
    unittest.main()
