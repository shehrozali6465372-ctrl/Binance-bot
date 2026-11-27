import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from layer1.foundation import EligibilityDecision
from layer1.onchain import OnChainAssetMapping, OnChainIntelligenceEngine
from tests.onchain_test_support import MappingStoreStub
from layer1.onchain_ingestion import OnChainIngestionStore
from layer1.onchain_providers import (
    BitcoinAddressTransaction, ProviderDataPage, ProviderTransportError,
    ProviderResponseReceipt, _ACTIVE_PAGE_RECEIPTS, _approved_endpoint_profile_sha256,
)
from layer1.onchain_bitcoin_worker import BitcoinAddressIngestionWorker

ADDRESS = "1BoatSLRHtKNngkdXEeobR76b53LETtpyT"
TXID = "a" * 64
HASH = "b" * 64
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def history(txid=TXID, height=100, confirmations=8, block_hash=HASH):
    return BitcoinAddressTransaction(txid, confirmations, height, block_hash, int(NOW.timestamp()) - 600,
                                     "CONFIRMED", {"txid": txid})


def transaction(record):
    return {
        "txid": record.txid, "blockHeight": record.block_height,
        "blockHash": record.block_hash, "blockTime": record.block_time,
        "vin": [{"txid": "c" * 64, "vout": 0, "addresses": [ADDRESS], "isAddress": True}],
        "vout": [{"n": 0, "value": "12345", "addresses": [ADDRESS], "isAddress": True}],
    }


class FakeBitcoinProvider:
    def __init__(self):
        self.tip = 110
        self.pages = {}
        self.details = {}
        self.headers = {}
        self.fail_txid_once = None
        self.history_calls = []
        self.detail_calls = []

    def fetch_bitcoin_tip_height(self):
        return self.tip

    def fetch_bitcoin_block_header(self, height):
        if height in self.headers:
            return self.headers[height]
        previous = self.headers.get(height - 1)
        previous_block_hash = previous["hash"] if previous is not None else HASH
        return {
            "number": height, "hash": HASH,
            "previous_block_hash": previous_block_hash,
            "timestamp": int(NOW.timestamp()) - (110 - height) * 60,
        }

    def fetch_bitcoin_address_transactions(self, address, page, page_size, from_height, to_height):
        self.history_calls.append((address, page, from_height, to_height))
        records, total = self.pages.get(page, ((), 0))
        return ProviderDataPage("alchemy", "bitcoin-mainnet", address, tuple(records),
                                page + 1 if page < total else None, page, total)

    def fetch_bitcoin_transaction(self, txid):
        self.detail_calls.append(txid)
        if self.fail_txid_once == txid:
            self.fail_txid_once = None
            raise ProviderTransportError("TIMEOUT", "temporary timeout")
        return self.details[txid]


class BitcoinAddressIngestionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self.tmp.name, "onchain.sqlite3")
        engine = OnChainIntelligenceEngine(
            {"bitcoin-mainnet": 86400}, {"bitcoin-mainnet": 6},
            receipt_signing_key=b"test-only-onchain-receipt-key-32-bytes-minimum",
            receipt_key_id="test-key-v1")
        self.ingestion_store = OnChainIngestionStore(path)
        self.mapping = OnChainAssetMapping(
            "bitcoin-native-v1", "coingecko:bitcoin", "BTC", "bitcoin-mainnet",
            "UTXO", "bitcoin-mainnet", "NATIVE", None, None, 8, "VERIFIED",
            "OFFICIAL_NETWORK", "https://bitcoin.org", (NOW - timedelta(hours=2)).isoformat())
        self.mapping_store = MappingStoreStub(engine, self.mapping)
        self.provider = FakeBitcoinProvider()
        record = history()
        self.provider.pages = {1: ((record,), 2), 2: ((), 2)}
        self.provider.details = {TXID: transaction(record)}
        self.worker = BitcoinAddressIngestionWorker(
            self.provider, self.mapping_store, self.ingestion_store,
            monitored_addresses={self.mapping.mapping_id: (ADDRESS,)},
            start_blocks={self.mapping.mapping_id: 99},
            minimum_confirmations=6, max_blocks_per_run=5, page_size=1,
            reorg_lookback_blocks=2, retry_attempts=1, sleep=lambda _: None,
            clock=lambda: NOW)

    def tearDown(self):
        self.ingestion_store.close()
        self.mapping_store.close()
        self.tmp.cleanup()

    def test_rejects_nonempty_history_page_with_zero_total_pages_before_detail_fetch(self):
        record = history()
        self.provider.pages = {1: ((record,), 0)}
        self.provider.details[record.txid] = transaction(record)

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")
        self.assertEqual(self.provider.detail_calls, [])
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bitcoin-mainnet:address:" + ADDRESS))

    def test_rejects_malformed_history_txid_before_transaction_detail_request(self):
        from dataclasses import replace
        self.provider.pages = {1: ((replace(history(), txid=None),), 1)}

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")
        self.assertEqual(self.provider.detail_calls, [])
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bitcoin-mainnet:address:" + ADDRESS))
        self.assertEqual(self.ingestion_store.list_events("bitcoin-mainnet"), [])

    def test_rejects_monitored_address_seed_with_invalid_mainnet_checksum(self):
        with self.assertRaisesRegex(ValueError, "checksum-valid Bitcoin mainnet address seeds"):
            BitcoinAddressIngestionWorker(
                self.provider, self.mapping_store, self.ingestion_store,
                monitored_addresses={self.mapping.mapping_id: ("1BoatSLRHtKNngkdXEeobR76b53LETtpyU",)},
                start_blocks={self.mapping.mapping_id: 99},
                minimum_confirmations=6, max_blocks_per_run=5, page_size=1,
                reorg_lookback_blocks=2, retry_attempts=1, sleep=lambda _: None,
                clock=lambda: NOW)

    def test_accepts_valid_mainnet_bech32_seed(self):
        worker = BitcoinAddressIngestionWorker(
            self.provider, self.mapping_store, self.ingestion_store,
            monitored_addresses={self.mapping.mapping_id: ("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4",)},
            start_blocks={self.mapping.mapping_id: 99},
            minimum_confirmations=6, max_blocks_per_run=5, page_size=1,
            reorg_lookback_blocks=2, retry_attempts=1, sleep=lambda _: None,
            clock=lambda: NOW)
        self.assertEqual(worker.monitored_addresses[self.mapping.mapping_id],
                         ("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4",))

    def test_accepts_official_bip350_mainnet_taproot_bech32m_vector(self):
        address = "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0"
        worker = BitcoinAddressIngestionWorker(
            self.provider, self.mapping_store, self.ingestion_store,
            monitored_addresses={self.mapping.mapping_id: (address,)},
            start_blocks={self.mapping.mapping_id: 99},
            minimum_confirmations=6, max_blocks_per_run=5, page_size=1,
            reorg_lookback_blocks=2, retry_attempts=1, sleep=lambda _: None,
            clock=lambda: NOW)
        self.assertEqual(worker.monitored_addresses[self.mapping.mapping_id], (address,))

    def test_rejects_v1_witness_address_using_bech32_instead_of_bech32m(self):
        address = "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqh2y7hd"
        with self.assertRaisesRegex(ValueError, "checksum-valid Bitcoin mainnet address seeds"):
            BitcoinAddressIngestionWorker(
                self.provider, self.mapping_store, self.ingestion_store,
                monitored_addresses={self.mapping.mapping_id: (address,)},
                start_blocks={self.mapping.mapping_id: 99},
                minimum_confirmations=6, max_blocks_per_run=5, page_size=1,
                reorg_lookback_blocks=2, retry_attempts=1, sleep=lambda _: None,
                clock=lambda: NOW)

    def test_rejects_invalid_bech32_checksum(self):
        with self.assertRaisesRegex(ValueError, "checksum-valid Bitcoin mainnet address seeds"):
            BitcoinAddressIngestionWorker(
                self.provider, self.mapping_store, self.ingestion_store,
                monitored_addresses={self.mapping.mapping_id: ("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3tq",)},
                start_blocks={self.mapping.mapping_id: 99},
                minimum_confirmations=6, max_blocks_per_run=5, page_size=1,
                reorg_lookback_blocks=2, retry_attempts=1, sleep=lambda _: None,
                clock=lambda: NOW)

    def test_rejects_wrong_network_bech32_seed(self):
        with self.assertRaisesRegex(ValueError, "checksum-valid Bitcoin mainnet address seeds"):
            BitcoinAddressIngestionWorker(
                self.provider, self.mapping_store, self.ingestion_store,
                monitored_addresses={self.mapping.mapping_id: ("tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",)},
                start_blocks={self.mapping.mapping_id: 99},
                minimum_confirmations=6, max_blocks_per_run=5, page_size=1,
                reorg_lookback_blocks=2, retry_attempts=1, sleep=lambda _: None,
                clock=lambda: NOW)

    def test_ingests_outputs_and_scopes_events_to_explicit_monitored_address(self):
        first = self.worker.run_once()  # page 1 is durably checkpointed
        result = self.worker.run_once()  # page 2 completes the fixed block range
        saved = self.ingestion_store.list_events("bitcoin-mainnet", canonical_only=True)
        self.assertEqual(first["events_inserted"], 1)
        self.assertEqual(result["events_inserted"], 0)
        self.assertEqual(saved[0].event_id, TXID + ":0")
        self.assertEqual(saved[0].scope, "address:" + ADDRESS)
        self.assertEqual(saved[0].amount_raw, "12345")
        self.assertEqual(self.ingestion_store.get_checkpoint(
            "alchemy:bitcoin-mainnet:address:" + ADDRESS)["next_block"], 104)

    def test_skips_orphaned_history_rows_without_blocking_confirmed_page(self):
        confirmed = history()
        orphaned = BitcoinAddressTransaction("d" * 64, -1, 100, HASH,
                                              int(NOW.timestamp()) - 600,
                                              "ORPHANED", {"txid": "d" * 64})
        self.provider.pages = {1: ((orphaned, confirmed), 1)}
        self.provider.details = {TXID: transaction(confirmed)}
        self.worker.page_size = 3

        result = self.worker.run_once()

        saved = self.ingestion_store.list_events("bitcoin-mainnet", canonical_only=True)
        self.assertEqual(result["transactions_skipped_orphaned"], 1)
        self.assertEqual(result["events_inserted"], 1)
        self.assertEqual([row.event_id for row in saved], [TXID + ":0"])
        self.assertEqual(self.provider.detail_calls, [TXID])
        self.assertEqual(self.ingestion_store.get_checkpoint(
            "alchemy:bitcoin-mainnet:address:" + ADDRESS)["next_block"], 104)

    def test_transaction_detail_response_receipt_is_bound_to_signed_ingestion_page(self):
        class ReceiptProvider(FakeBitcoinProvider):
            @staticmethod
            def _capture(method):
                collector = _ACTIVE_PAGE_RECEIPTS.get()
                collector.append(ProviderResponseReceipt(
                    sequence=len(collector) + 1, provider="alchemy",
                    network_id="bitcoin-mainnet", method=method,
                    request_sha256="a" * 64, response_sha256="b" * 64,
                    response_bytes=128, http_status=200,
                    received_at=NOW.isoformat(),
                    endpoint_profile_sha256=_approved_endpoint_profile_sha256(
                        "alchemy", "bitcoin-mainnet"),
                ))

            def fetch_bitcoin_tip_height(self):
                self._capture("getblockcount")
                return super().fetch_bitcoin_tip_height()

            def fetch_bitcoin_block_header(self, height):
                self._capture("getblockhash")
                self._capture("getblockheader")
                return super().fetch_bitcoin_block_header(height)

            def fetch_bitcoin_address_transactions(self, *args, **kwargs):
                self._capture("GET api/v2/address")
                return super().fetch_bitcoin_address_transactions(*args, **kwargs)

            def fetch_bitcoin_transaction(self, txid):
                self._capture("GET api/v2/tx")
                return super().fetch_bitcoin_transaction(txid)

        provider = ReceiptProvider()
        record = history()
        provider.pages = {1: ((record,), 2)}
        provider.details = {TXID: transaction(record)}
        worker = BitcoinAddressIngestionWorker(
            provider, self.mapping_store, self.ingestion_store,
            monitored_addresses={self.mapping.mapping_id: (ADDRESS,)},
            start_blocks={self.mapping.mapping_id: 99}, minimum_confirmations=6,
            max_blocks_per_run=5, page_size=1, reorg_lookback_blocks=0,
            retry_attempts=1, sleep=lambda _: None, clock=lambda: NOW,
        )
        result = worker.run_once()
        self.assertEqual(result["pages_committed"], 1)
        cursor_key = "alchemy:bitcoin-mainnet:address:" + ADDRESS
        page_id, receipts_json = self.ingestion_store.conn.execute(
            "SELECT page_id, receipts_json FROM layer1_onchain_ingestion_pages WHERE cursor_key=?",
            (cursor_key,),
        ).fetchone()
        import json
        methods = [item["method"] for item in json.loads(receipts_json)]
        self.assertIn("GET api/v2/address", methods)
        self.assertIn("GET api/v2/tx", methods)
        event = self.ingestion_store.list_events("bitcoin-mainnet", canonical_only=True)[0]
        self.assertEqual(event.finality_snapshot.status, "CONFIRMED")
        self.assertEqual(event.finality_snapshot.reference, "confirmations-policy:min=6")
        checkpoint = self.ingestion_store.get_checkpoint(cursor_key)
        self.assertEqual(checkpoint["observed_tip_height"], provider.tip)
        self.assertEqual(checkpoint["minimum_confirmations"], 6)
        self.assertTrue(self.mapping_store.engine.verify_ingestion_page_acceptance(
            self.ingestion_store, cursor_key, page_id))

    def test_page_checkpoint_resumes_after_detail_timeout_without_skipping_page(self):
        self.provider.pages = {1: ((history(),), 2), 2: ((history("d" * 64),), 2)}
        self.provider.details["d" * 64] = transaction(history("d" * 64))
        self.provider.fail_txid_once = "d" * 64
        self.worker.run_once()  # first page is committed before page 2 is attempted
        self.provider.fail_txid_once = "d" * 64
        with self.assertRaises(ProviderTransportError):
            self.worker.run_once()
        cursor = self.ingestion_store.get_checkpoint("alchemy:bitcoin-mainnet:address:" + ADDRESS)
        self.assertEqual(cursor["page"], 2)
        self.assertEqual(cursor["from_block"], 99)
        self.assertEqual(len(self.ingestion_store.list_events("bitcoin-mainnet")), 1)
        self.worker.run_once()
        self.assertEqual(self.ingestion_store.get_checkpoint(
            "alchemy:bitcoin-mainnet:address:" + ADDRESS)["next_block"], 104)
        self.assertEqual(len(self.ingestion_store.list_events("bitcoin-mainnet")), 2)

    def test_empty_history_pages_still_commit_verified_block_hashes_and_advance(self):
        self.provider.pages = {1: ((), 0)}
        self.provider.details = {}
        result = self.worker.run_once()
        self.assertEqual(result["events_inserted"], 0)
        self.assertEqual(self.ingestion_store.get_checkpoint(
            "alchemy:bitcoin-mainnet:address:" + ADDRESS)["next_block"], 104)
        self.assertEqual(self.ingestion_store.get_block_hash(
            "bitcoin-mainnet", "alchemy", "address:" + ADDRESS, 99), HASH)

    def test_reorg_in_empty_block_is_detected_and_replayed(self):
        self.provider.pages = {1: ((), 0)}
        self.worker.run_once()
        self.provider.tip = 110
        self.provider.headers[102] = {
            "number": 102, "hash": "e" * 64, "previous_block_hash": HASH,
            "timestamp": int(NOW.timestamp()) - 600,
        }
        self.provider.pages = {1: ((history("d" * 64, 102, 8, "e" * 64),), 1)}
        self.provider.details["d" * 64] = transaction(history("d" * 64, 102, 8, "e" * 64))
        result = self.worker.run_once()
        self.assertGreaterEqual(result["reorg_blocks_detected"], 1)
        self.assertEqual(self.ingestion_store.get_event(
            "d" * 64 + ":0", "bitcoin-mainnet", "alchemy", "address:" + ADDRESS).canonical_status,
            "CANONICAL")

    def test_resumed_range_waits_when_tip_recedes_below_its_confirmation_safe_height(self):
        first = history()
        self.provider.pages = {1: ((first,), 2), 2: ((), 2)}
        self.worker.run_once()
        cursor_key = "alchemy:bitcoin-mainnet:address:" + ADDRESS
        checkpoint = self.ingestion_store.get_checkpoint(cursor_key)
        self.assertEqual(checkpoint["page"], 2)
        self.assertEqual((checkpoint["from_block"], checkpoint["to_block"]), (99, 103))

        late_record = history(txid="d" * 64, height=100, confirmations=6)
        self.provider.tip = 100  # minimum-confirmation safe height is now 95
        self.provider.pages[2] = ((late_record,), 2)
        self.provider.details[late_record.txid] = transaction(late_record)

        result = self.worker.run_once()

        self.assertEqual(result["events_inserted"], 0)
        self.assertEqual(self.provider.detail_calls, [first.txid])
        events = self.ingestion_store.list_events("bitcoin-mainnet")
        self.assertEqual([event.transaction_hash for event in events], [first.txid])
        self.assertEqual(self.ingestion_store.get_checkpoint(cursor_key)["page"], 2)

    def test_changed_provider_page_count_restarts_fixed_range_at_page_one(self):
        self.provider.pages = {1: ((history(),), 2), 2: ((), 2)}
        self.worker.run_once()
        self.provider.pages = {1: ((history(),), 3), 2: ((), 3), 3: ((), 3)}
        self.worker.run_once()
        self.assertEqual(self.provider.history_calls[-1][1], 1)
        cursor = self.ingestion_store.get_checkpoint("alchemy:bitcoin-mainnet:address:" + ADDRESS)
        self.assertEqual(cursor["page"], 2)
        self.assertEqual(cursor["total_pages"], 3)

    def test_reorg_inside_partially_paginated_range_restarts_from_page_one(self):
        self.provider.pages = {1: ((history(),), 2), 2: ((), 2)}
        self.worker.run_once()
        self.assertEqual(self.ingestion_store.get_checkpoint(
            "alchemy:bitcoin-mainnet:address:" + ADDRESS)["page"], 2)
        changed = history(TXID, 100, 8, "e" * 64)
        self.provider.headers[100] = {
            "number": 100, "hash": "e" * 64, "previous_block_hash": HASH,
            "timestamp": int(NOW.timestamp()) - (110 - 100) * 60,
        }
        self.provider.pages[1] = ((changed,), 2)
        self.provider.details[TXID] = transaction(changed)
        result = self.worker.run_once()
        self.assertEqual(self.provider.history_calls[-1][1], 1)
        self.assertGreaterEqual(result["reorg_blocks_detected"], 1)
        saved = self.ingestion_store.get_event(
            TXID + ":0", "bitcoin-mainnet", "alchemy", "address:" + ADDRESS)
        self.assertEqual(saved.block_hash, "e" * 64)
        self.assertEqual(saved.canonical_status, "CANONICAL")

    def test_confirmation_threshold_is_required_and_unconfirmed_records_are_not_normalized(self):
        with self.assertRaises(ValueError):
            BitcoinAddressIngestionWorker(
                self.provider, self.mapping_store, self.ingestion_store,
                monitored_addresses={self.mapping.mapping_id: (ADDRESS,)},
                start_blocks={self.mapping.mapping_id: 99}, minimum_confirmations=0,
                max_blocks_per_run=5, page_size=1, reorg_lookback_blocks=0)
        self.provider.pages = {1: ((history(confirmations=5),), 1)}
        with self.assertRaises(ProviderTransportError):
            self.worker.run_once()
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bitcoin-mainnet:address:" + ADDRESS))

    def test_provider_scope_mismatch_fails_without_checkpoint_advance(self):
        class WrongScope(FakeBitcoinProvider):
            def fetch_bitcoin_address_transactions(inner, address, page, page_size, from_height, to_height):
                return ProviderDataPage("alchemy", "bitcoin-mainnet", "wrong-address", (), None, 1, 0)
        self.worker.provider = WrongScope()
        with self.assertRaises(ProviderTransportError):
            self.worker.run_once()
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bitcoin-mainnet:address:" + ADDRESS))

    def test_rejects_address_history_block_time_that_diverges_from_canonical_header(self):
        record = history()
        record = BitcoinAddressTransaction(
            record.txid, record.confirmations, record.block_height, record.block_hash,
            record.block_time + 1, record.finality,
            {"txid": record.txid, "confirmations": record.confirmations,
             "blockHeight": record.block_height, "blockTime": record.block_time + 1,
             "blockHash": record.block_hash},
        )
        self.provider.pages = {1: ((record,), 1)}
        self.provider.details = {record.txid: transaction(record)}

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "BITCOIN_BLOCK_TIME_MISMATCH")
        self.assertEqual(self.provider.detail_calls, [])
        self.assertEqual(self.ingestion_store.list_events("bitcoin-mainnet"), [])
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bitcoin-mainnet:address:" + ADDRESS))

    def test_rejects_address_history_block_hash_that_diverges_from_canonical_header(self):
        record = history(block_hash="d" * 64)
        self.provider.pages = {1: ((record,), 1)}
        self.provider.details = {record.txid: transaction(record)}

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "BITCOIN_BLOCK_HASH_MISMATCH")
        self.assertEqual(self.provider.detail_calls, [])
        self.assertEqual(self.ingestion_store.list_events("bitcoin-mainnet"), [])
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bitcoin-mainnet:address:" + ADDRESS))

    def test_worker_rejects_canonical_header_timestamp_above_uint32(self):
        self.provider.pages = {1: ((), 0)}
        self.provider.headers = {
            height: {"number": height, "hash": HASH,
                     "previous_block_hash": HASH if height > 99 else HASH,
                     "timestamp": 2**32 if height == 99 else int(NOW.timestamp())}
            for height in range(99, 104)
        }
        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()
        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bitcoin-mainnet:address:" + ADDRESS))

    def test_rejects_discontinuous_bitcoin_block_headers_inside_fixed_range(self):
        self.provider.pages = {1: ((), 0)}
        self.provider.headers = {
            99: {"number": 99, "hash": "a" * 64, "timestamp": 1794398500,
                 "previous_block_hash": "b" * 64},
            100: {"number": 100, "hash": "c" * 64, "timestamp": 1794398560,
                  "previous_block_hash": "d" * 64},
        }
        self.worker.max_blocks_per_run = 2

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "BITCOIN_PARENT_HASH_MISMATCH")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bitcoin-mainnet:address:" + ADDRESS))
        self.assertEqual(self.ingestion_store.list_events("bitcoin-mainnet"), [])

    def test_initial_bitcoin_range_uses_previous_header_as_parent_anchor(self):
        self.provider.pages = {1: ((), 0)}
        self.provider.headers = {
            98: {"number": 98, "hash": "c" * 64,
                 "previous_block_hash": "b" * 64,
                 "timestamp": int(NOW.timestamp()) - 12 * 60},
            99: {"number": 99, "hash": HASH,
                 "previous_block_hash": "d" * 64,
                 "timestamp": int(NOW.timestamp()) - 11 * 60},
        }

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "BITCOIN_PARENT_HASH_MISMATCH")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bitcoin-mainnet:address:" + ADDRESS))
        self.assertIsNone(self.ingestion_store.get_block_hash(
            "bitcoin-mainnet", "alchemy", "address:" + ADDRESS, 99))

    def test_resumed_bitcoin_range_uses_previous_header_as_parent_anchor(self):
        self.provider.pages = {1: ((), 0)}
        self.worker.max_blocks_per_run = 2
        self.worker.reorg_lookback_blocks = 0
        self.worker.run_once()
        cursor_key = "alchemy:bitcoin-mainnet:address:" + ADDRESS
        self.assertEqual(self.ingestion_store.get_checkpoint(cursor_key)["next_block"], 101)
        self.provider.headers[100] = {
            "number": 100, "hash": "e" * 64, "previous_block_hash": HASH,
            "timestamp": 1794398560,
        }
        self.provider.headers[101] = {
            "number": 101, "hash": "f" * 64, "previous_block_hash": "d" * 64,
            "timestamp": 1794398620,
        }

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "BITCOIN_PARENT_HASH_MISMATCH")
        self.assertEqual(self.ingestion_store.get_checkpoint(cursor_key)["next_block"], 101)
        self.assertEqual(self.ingestion_store.list_events("bitcoin-mainnet"), [])

    def test_provider_page_cannot_exceed_configured_page_size(self):
        first = history(txid=TXID)
        second = history(txid="c" * 64)
        self.provider.pages = {1: ((first, second), 1)}
        self.provider.details = {first.txid: transaction(first), second.txid: transaction(second)}

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "PAGE_LIMIT_EXCEEDED")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bitcoin-mainnet:address:" + ADDRESS))
        self.assertEqual(self.ingestion_store.list_events("bitcoin-mainnet"), [])


if __name__ == "__main__":
    unittest.main()
