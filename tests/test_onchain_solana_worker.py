import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from layer1.foundation import EligibilityDecision
from layer1.onchain import OnChainAssetMapping, OnChainIntelligenceEngine
from tests.onchain_test_support import MappingStoreStub
from layer1.onchain_ingestion import OnChainIngestionStore
from layer1.onchain_providers import ProviderDataPage, ProviderTransportError, SolanaAddressTransaction
from layer1.onchain_solana_worker import SolanaAddressIngestionWorker
from tests.test_solana_normalization import MINT, WALLET, BLOCKHASH, SIGNATURE, rpc_tx

NOW = datetime.now(timezone.utc).replace(microsecond=0)
MAPPING_ID = "sol-usdc-v1"


def history(slot=300, signature=SIGNATURE):
    block_time = int(NOW.timestamp()) - 60
    raw = rpc_tx(slot=slot, signature=signature).raw
    raw["blockTime"] = block_time
    return SolanaAddressTransaction(signature, slot, block_time, raw, 17)


class FakeSolanaProvider:
    def __init__(self):
        self.finalized_slot = 310
        self.changed_hashes = {}
        self.block_signatures = {}
        self.pages = {None: ((history(),), "next"), "next": ((), None)}
        self.fail_token_once = None
        self.calls = []
        self.produced_slots = ()
        self.range_start = 0

    def fetch_solana_finalized_slot(self):
        return self.finalized_slot

    def fetch_solana_produced_slots(self, start_slot, end_slot):
        self.range_start = start_slot
        self.produced_slots = tuple(range(start_slot, end_slot + 1))
        return self.produced_slots

    def fetch_solana_block_header(self, slot):
        from tests.test_solana_normalization import b58encode
        parents = [candidate for candidate in self.produced_slots if candidate < slot]
        parent_slot = max(parents) if parents else self.range_start - 1
        signatures = self.block_signatures.get(slot)
        if signatures is None:
            signatures = [b58encode(bytes([index + 20]) * 64) for index in range(18)]
            signatures[17] = SIGNATURE
        return {
            "number": slot, "hash": self.changed_hashes.get(slot, BLOCKHASH),
            "timestamp": int(NOW.timestamp()) - 60,
            "parent_slot": parent_slot,
            "previous_block_hash": self.changed_hashes.get(parent_slot, BLOCKHASH),
            "transaction_signatures": tuple(signatures),
            "finality_reference": "commitment=finalized",
        }

    def fetch_solana_address_transactions(self, address, pagination_token=None, limit=100,
                                          slot_start=None, slot_end=None):
        self.calls.append((address, pagination_token, slot_start, slot_end))
        if self.fail_token_once is not None and self.fail_token_once == pagination_token:
            self.fail_token_once = "__failed__"
            raise ProviderTransportError("TIMEOUT", "temporary timeout")
        records, next_cursor = self.pages[pagination_token]
        invalid = [record.slot for record in records if not slot_start <= record.slot <= slot_end]
        if invalid:
            raise AssertionError(f"fake returned slots {invalid} outside range {slot_start}..{slot_end} token={pagination_token!r}")
        return ProviderDataPage("alchemy", "solana-mainnet", address, records,
                                next_cursor, finality_reference="commitment=finalized")


class SolanaAddressIngestionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self.tmp.name, "onchain.sqlite3")
        engine = OnChainIntelligenceEngine(
            {"solana-mainnet": 86400},
            receipt_signing_key=b"test-only-onchain-receipt-key-32-bytes-minimum",
            receipt_key_id="test-key-v1")
        self.ingestion_store = OnChainIngestionStore(path)
        stamp = NOW.isoformat()
        self.mapping = OnChainAssetMapping(
            MAPPING_ID, "coingecko:usd-coin", "USDC", "solana-mainnet",
            "SOLANA", "mainnet-beta", "TOKEN", MINT, "SPL_TOKEN", 6,
            "VERIFIED", "OFFICIAL_PROJECT", "https://solana.com",
            (NOW - timedelta(hours=2)).isoformat())
        self.mapping_store = MappingStoreStub(engine, self.mapping)
        self.provider = FakeSolanaProvider()
        self.worker = SolanaAddressIngestionWorker(
            self.provider, self.mapping_store, self.ingestion_store,
            monitored_addresses={MAPPING_ID: (WALLET,)},
            start_slots={MAPPING_ID: 300}, max_slots_per_run=5,
            page_size=100, reorg_lookback_slots=5, retry_attempts=1,
            sleep=lambda _: None, clock=lambda: NOW)

    def tearDown(self):
        self.ingestion_store.close()
        self.mapping_store.close()
        self.tmp.cleanup()

    def test_failed_transaction_is_skipped_without_blocking_valid_transactions_or_checkpoint(self):
        from tests.test_solana_normalization import b58encode
        failed_signature = b58encode(bytes([7]) * 64)
        failed_raw = rpc_tx(slot=300, signature=failed_signature,
                            err={"InstructionError": [0, "Custom"]}).raw
        failed_raw["transactionIndex"] = 18
        failed_raw["blockTime"] = int(NOW.timestamp()) - 60
        failed = SolanaAddressTransaction(
            failed_signature, 300, int(NOW.timestamp()) - 60, failed_raw, 18)
        valid = history(slot=300)
        signatures = [b58encode(bytes([index + 20]) * 64) for index in range(19)]
        signatures[17], signatures[18] = SIGNATURE, failed_signature
        self.provider.block_signatures[300] = signatures
        self.provider.pages = {None: ((failed, valid), None)}

        result = self.worker.run_once()

        events = self.ingestion_store.list_events("solana-mainnet", canonical_only=True)
        self.assertEqual(result["events_inserted"], 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].transaction_hash, SIGNATURE)
        self.assertEqual(self.ingestion_store.get_checkpoint(
            "alchemy:solana-mainnet:address:" + WALLET + ":mapping:" + MAPPING_ID)["next_slot"], 305)

    def test_rejects_transaction_index_not_bound_to_canonical_block_signature_order(self):
        record = history(slot=300)
        record = SolanaAddressTransaction(
            record.signature, record.slot, record.block_time, record.raw, 18)
        self.provider.pages = {None: ((record,), None)}

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "SOLANA_TRANSACTION_INDEX_MISMATCH")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:solana-mainnet:address:" + WALLET + ":mapping:" + MAPPING_ID))

    def test_rejects_solana_header_timestamp_outside_datetime_storage_range(self):
        original = self.provider.fetch_solana_block_header
        def oversized_time(slot):
            header = original(slot)
            if slot == 300:
                header["timestamp"] = 253402300800
            return header
        self.provider.fetch_solana_block_header = oversized_time

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:solana-mainnet:address:" + WALLET + ":mapping:" + MAPPING_ID))

    def test_rejects_solana_transaction_block_time_outside_datetime_storage_range(self):
        from dataclasses import replace
        record = history()
        record.raw["blockTime"] = 253402300800
        record = replace(record, block_time=253402300800)
        self.provider.pages = {None: ((record,), None)}
        original = self.provider.fetch_solana_block_header
        def unknown_canonical_time(slot):
            header = original(slot)
            if slot == 300:
                header["timestamp"] = None
            return header
        self.provider.fetch_solana_block_header = unknown_canonical_time

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "INVALID_SOLANA_TRANSACTION")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:solana-mainnet:address:" + WALLET + ":mapping:" + MAPPING_ID))

    def test_ingests_token_transfer_and_atomically_journals_produced_and_skipped_slots(self):
        self.provider.pages = {None: ((history(),), None)}
        result = self.worker.run_once()
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        events = self.ingestion_store.list_events("solana-mainnet", canonical_only=True)
        self.assertEqual(result["events_inserted"], 1)
        self.assertEqual(events[0].amount_raw, "1234567")
        self.assertEqual(events[0].scope, scope)
        self.assertEqual(events[0].event_id, SIGNATURE + ":outer:0")
        self.assertEqual(events[0].finality_snapshot.status, "FINALIZED")
        self.assertEqual(events[0].finality_snapshot.reference, "commitment=finalized")
        checkpoint = self.ingestion_store.get_checkpoint("alchemy:solana-mainnet:" + scope)
        self.assertEqual(checkpoint["next_slot"], 305)
        self.assertEqual(checkpoint["finalized_slot"], self.provider.finalized_slot)
        journal = self.ingestion_store.get_solana_slot_journal(
            "solana-mainnet", "alchemy", scope, 300, 304)
        self.assertEqual(set(journal), set(range(300, 305)))
        self.assertTrue(all(item["produced"] for item in journal.values()))

    def test_rejects_parent_slot_that_skips_an_intervening_produced_slot(self):
        original = self.provider.fetch_solana_block_header
        def broken_parent_slot(slot):
            header = original(slot)
            if slot == 302:
                header["parent_slot"] = 300
                header["previous_block_hash"] = original(300)["hash"]
            return header
        self.provider.fetch_solana_block_header = broken_parent_slot

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "SOLANA_PARENT_SLOT_MISMATCH")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:solana-mainnet:address:" + WALLET + ":mapping:" + MAPPING_ID))

    def test_rejects_finalized_slot_header_with_wrong_parent_block_hash(self):
        original = self.provider.fetch_solana_block_header
        def broken_parent(slot):
            header = original(slot)
            if slot == 301:
                header["previous_block_hash"] = "So11111111111111111111111111111111111111112"
            return header
        self.provider.fetch_solana_block_header = broken_parent
        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()
        self.assertEqual(error.exception.reason_code, "SOLANA_PARENT_HASH_MISMATCH")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:solana-mainnet:address:" + WALLET + ":mapping:" + MAPPING_ID))

    def test_rejects_first_solana_block_parent_hash_mismatch_against_external_parent(self):
        original = self.provider.fetch_solana_block_header
        def broken_first_parent(slot):
            header = original(slot)
            if slot == 300:
                header["previous_block_hash"] = "So11111111111111111111111111111111111111112"
            return header
        self.provider.fetch_solana_block_header = broken_first_parent

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "SOLANA_PARENT_HASH_MISMATCH")
        self.assertEqual(self.provider.calls, [])
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:solana-mainnet:address:" + WALLET + ":mapping:" + MAPPING_ID))

    def test_external_parent_with_unknown_time_can_still_anchor_child_hash(self):
        original = self.provider.fetch_solana_block_header
        def parent_without_time(slot):
            header = original(slot)
            if slot == 299:
                header["timestamp"] = None
            return header
        self.provider.fetch_solana_block_header = parent_without_time

        result = self.worker.run_once()

        self.assertEqual(result["events_inserted"], 1)
        self.assertEqual(self.ingestion_store.list_events("solana-mainnet", canonical_only=True)[0].event_id,
                         SIGNATURE + ":outer:0")

    def test_null_block_time_is_quarantined_then_replayed_when_time_becomes_available(self):
        from tests.test_solana_normalization import b58encode
        self.provider.finalized_slot = 304
        unrelated_signature = b58encode(bytes([9]) * 64)
        unrelated = history(slot=301, signature=unrelated_signature)
        self.provider.block_signatures[301] = (
            [b58encode(bytes([index + 30]) * 64) for index in range(18)]
        )
        self.provider.block_signatures[301][17] = unrelated_signature
        self.provider.pages = {None: ((unrelated, history()), None)}
        original = self.provider.fetch_solana_block_header
        unknown = {300}
        def variable_time(slot):
            header = original(slot)
            if slot in unknown:
                header["timestamp"] = None
            return header
        self.provider.fetch_solana_block_header = variable_time

        first = self.worker.run_once()
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        cursor_key = "alchemy:solana-mainnet:address:" + WALLET + ":mapping:" + MAPPING_ID
        checkpoint = self.ingestion_store.get_checkpoint(cursor_key)
        pending = self.ingestion_store.list_pending_solana_quarantine(
            "solana-mainnet", "alchemy", scope, limit=10)
        self.assertEqual(first["quarantined_transactions"], 1)
        self.assertEqual(checkpoint["next_slot"], 305)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["signature"], SIGNATURE)
        self.assertEqual(pending[0]["payload"]["raw"]["slot"], 300)
        self.assertEqual(len(pending[0]["source_page_id"]), 64)
        journal = self.ingestion_store.get_solana_slot_journal(
            "solana-mainnet", "alchemy", scope, 300, 300)
        self.assertTrue(journal[300]["produced"])
        self.assertIsNone(journal[300]["block_time"])
        first_events = self.ingestion_store.list_events("solana-mainnet", canonical_only=True)
        self.assertEqual(len(first_events), 1)
        self.assertEqual(first_events[0].transaction_hash, unrelated_signature)
        self.assertEqual(first_events[0].block_number, 301)

        unknown.clear()
        self.ingestion_store.conn.execute("""
            CREATE TRIGGER fail_solana_quarantine_replay
            BEFORE UPDATE OF status ON layer1_onchain_solana_quarantine
            WHEN NEW.status='REPLAYED'
            BEGIN SELECT RAISE(ABORT, 'injected quarantine replay failure'); END
        """)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "injected quarantine replay failure"):
            self.worker.run_once()
        # Event insertion, slot-time enrichment, replay status, and checkpoint
        # update are one transaction: an injected finalization failure rolls all
        # of them back, leaving the raw transaction pending for retry.
        self.assertEqual(len(self.ingestion_store.list_events("solana-mainnet", canonical_only=True)), 1)
        self.assertEqual(len(self.ingestion_store.list_pending_solana_quarantine(
            "solana-mainnet", "alchemy", scope, limit=10)), 1)
        rolled_back_journal = self.ingestion_store.get_solana_slot_journal(
            "solana-mainnet", "alchemy", scope, 300, 300)
        self.assertIsNone(rolled_back_journal[300]["block_time"])
        self.assertEqual(self.ingestion_store.get_checkpoint(cursor_key)["next_slot"], 305)
        self.ingestion_store.conn.execute("DROP TRIGGER fail_solana_quarantine_replay")

        second = self.worker.run_once()

        events = self.ingestion_store.list_events("solana-mainnet", canonical_only=True)
        self.assertEqual(second["quarantine_replayed"], 1)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event_id, SIGNATURE + ":outer:0")
        self.assertIsNotNone(events[0].block_time)
        self.assertEqual(events[1].transaction_hash, unrelated_signature)
        self.assertEqual(self.ingestion_store.list_pending_solana_quarantine(
            "solana-mainnet", "alchemy", scope, limit=10), [])
        pages = self.ingestion_store.list_ingestion_pages()
        self.assertEqual(len(pages), 2)
        self.assertEqual(len(self.ingestion_store.list_pending_page_acceptances()), 2)

    def test_quarantine_replay_detects_block_hash_change_even_when_new_time_is_unknown(self):
        self.provider.finalized_slot = 304
        self.provider.pages = {None: ((history(),), None)}
        original = self.provider.fetch_solana_block_header
        def unknown_original_time(slot):
            header = original(slot)
            if slot == 300:
                header["timestamp"] = None
            return header
        self.provider.fetch_solana_block_header = unknown_original_time
        self.worker.run_once()
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        pending_before = self.ingestion_store.list_pending_solana_quarantine(
            "solana-mainnet", "alchemy", scope, limit=10)
        self.assertEqual(len(pending_before), 1)

        self.provider.changed_hashes[300] = "So11111111111111111111111111111111111111112"
        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "SOLANA_QUARANTINE_BLOCK_HASH_MISMATCH")
        pending_after = self.ingestion_store.list_pending_solana_quarantine(
            "solana-mainnet", "alchemy", scope, limit=10)
        self.assertEqual(len(pending_after), 1)
        self.assertEqual(pending_after[0]["block_hash"], BLOCKHASH)

    def test_rejects_parent_slot_omitted_from_produced_slots_in_same_range(self):
        self.provider.fetch_solana_produced_slots = lambda start, end: (300, 302, 304)
        self.provider.produced_slots = (300, 302, 304)
        self.provider.range_start = 300
        original = self.provider.fetch_solana_block_header
        def missing_parent(slot):
            header = original(slot)
            if slot == 302:
                header["parent_slot"] = 301
                header["previous_block_hash"] = BLOCKHASH
            return header
        self.provider.fetch_solana_block_header = missing_parent
        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()
        self.assertEqual(error.exception.reason_code, "SOLANA_PARENT_SLOT_MISSING")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:solana-mainnet:address:" + WALLET + ":mapping:" + MAPPING_ID))

    def test_quarantine_rejects_boolean_raw_slot_before_persisting_pending_record(self):
        self.provider.finalized_slot = 1
        self.worker.start_slots[MAPPING_ID] = 1
        self.worker.max_slots_per_run = 1
        record = history(slot=1)
        record.raw["slot"] = True  # Python True == 1 must not satisfy protocol identity.
        self.provider.pages = {None: ((record,), None)}
        original = self.provider.fetch_solana_block_header
        def unknown_slot_time(slot):
            header = original(slot)
            if slot == 1:
                header["timestamp"] = None
            return header
        self.provider.fetch_solana_block_header = unknown_slot_time

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "SOLANA_SLOT_MISMATCH")
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        self.assertEqual(self.ingestion_store.list_pending_solana_quarantine(
            "solana-mainnet", "alchemy", scope, limit=10), [])

    def test_quarantine_rejects_raw_block_time_diverging_from_typed_history(self):
        self.provider.finalized_slot = 304
        record = history(slot=300)
        record.raw["blockTime"] = record.block_time + 1
        self.provider.pages = {None: ((record,), None)}
        original = self.provider.fetch_solana_block_header
        def unknown_slot_time(slot):
            header = original(slot)
            if slot == 300:
                header["timestamp"] = None
            return header
        self.provider.fetch_solana_block_header = unknown_slot_time

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "SOLANA_BLOCK_TIME_MISMATCH")
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        self.assertEqual(self.ingestion_store.list_pending_solana_quarantine(
            "solana-mainnet", "alchemy", scope, limit=10), [])

    def test_quarantine_rejects_transaction_without_explicit_execution_status(self):
        self.provider.finalized_slot = 304
        record = history(slot=300)
        record.raw["meta"].pop("err")
        self.provider.pages = {None: ((record,), None)}
        original = self.provider.fetch_solana_block_header
        def unknown_slot_time(slot):
            header = original(slot)
            if slot == 300:
                header["timestamp"] = None
            return header
        self.provider.fetch_solana_block_header = unknown_slot_time

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "INVALID_SOLANA_TRANSACTION")
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        self.assertEqual(self.ingestion_store.list_pending_solana_quarantine(
            "solana-mainnet", "alchemy", scope, limit=10), [])

    def test_signed_int64_max_slot_checkpoint_uses_terminal_exhaustion_marker(self):
        maximum = 0x7FFFFFFFFFFFFFFF
        self.worker.start_slots[MAPPING_ID] = maximum
        self.provider.finalized_slot = maximum
        self.provider.pages = {None: ((), None)}
        self.worker.max_slots_per_run = 1

        self.worker.run_once()

        cursor_key = self.worker._cursor_key(WALLET, MAPPING_ID)
        checkpoint = self.ingestion_store.get_checkpoint(cursor_key)
        self.assertEqual(checkpoint["next_slot"], maximum)
        self.assertIs(checkpoint["exhausted"], True)
        calls_after_completion = list(self.provider.calls)
        self.worker.run_once()
        self.assertEqual(self.provider.calls, calls_after_completion)

    def test_worker_rejects_finalized_slot_above_signed_int64(self):
        self.provider.finalized_slot = 2**63
        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()
        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")
        self.assertEqual(self.provider.calls, [])

    def test_worker_rejects_start_slot_above_signed_int64(self):
        with self.assertRaises(ValueError):
            SolanaAddressIngestionWorker(
                self.provider, self.mapping_store, self.ingestion_store,
                monitored_addresses={MAPPING_ID: (WALLET,)},
                start_slots={MAPPING_ID: 2**63}, max_slots_per_run=5,
                page_size=10, reorg_lookback_slots=0,
            )

    def test_rejects_persisted_solana_pagination_token_without_active_range(self):
        self.provider.pages = {None: ((), None)}
        cursor_key = self.worker._cursor_key(WALLET, MAPPING_ID)
        scope = self.worker._scope(WALLET, MAPPING_ID)
        checkpoint = {"mapping_id": MAPPING_ID, "network_id": "solana-mainnet",
                      "address": WALLET, "next_slot": 305, "from_slot": None,
                      "to_slot": None, "pagination_token": "next",
                      "seen_tokens": ["next"], "last_position": [300, 17],
                      "exhausted": False}
        self.ingestion_store.commit_page(
            cursor_key, checkpoint, (), expected_cursor=None,
            scope_identity=("solana-mainnet", "alchemy", scope),
        )

        with self.assertRaisesRegex(ValueError, "stored Solana checkpoint is malformed"):
            self.worker.run_once()

        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.ingestion_store.list_events("solana-mainnet"), [])

    def test_rejects_solana_pagination_token_missing_from_seen_history(self):
        cursor_key = self.worker._cursor_key(WALLET, MAPPING_ID)
        scope = self.worker._scope(WALLET, MAPPING_ID)
        checkpoint = {"mapping_id": MAPPING_ID, "network_id": "solana-mainnet",
                      "address": WALLET, "next_slot": 300, "from_slot": 300,
                      "to_slot": 304, "pagination_token": "next",
                      "seen_tokens": [], "last_position": None,
                      "exhausted": False}
        self.ingestion_store.commit_page(
            cursor_key, checkpoint, (), expected_cursor=None,
            scope_identity=("solana-mainnet", "alchemy", scope),
        )

        with self.assertRaisesRegex(ValueError, "stored Solana checkpoint is malformed"):
            self.worker.run_once()

        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.ingestion_store.list_events("solana-mainnet"), [])

    def test_rejects_solana_next_slot_outside_active_range(self):
        cursor_key = self.worker._cursor_key(WALLET, MAPPING_ID)
        scope = self.worker._scope(WALLET, MAPPING_ID)
        checkpoint = {"mapping_id": MAPPING_ID, "network_id": "solana-mainnet",
                      "address": WALLET, "next_slot": 305, "from_slot": 300,
                      "to_slot": 304, "pagination_token": "next",
                      "seen_tokens": ["next"], "last_position": None,
                      "exhausted": False}
        self.ingestion_store.commit_page(
            cursor_key, checkpoint, (), expected_cursor=None,
            scope_identity=("solana-mainnet", "alchemy", scope),
        )

        with self.assertRaisesRegex(ValueError, "stored Solana checkpoint is malformed"):
            self.worker.run_once()

        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.ingestion_store.list_events("solana-mainnet"), [])

    def test_page_cursor_resumes_after_provider_timeout_without_replaying_or_skipping(self):
        self.worker.run_once()  # first page is committed
        self.provider.fail_token_once = "next"
        with self.assertRaises(ProviderTransportError):
            self.worker.run_once()  # second page times out
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        cursor = self.ingestion_store.get_checkpoint("alchemy:solana-mainnet:" + scope)
        self.assertEqual(cursor["pagination_token"], "next")
        self.assertEqual(len(self.ingestion_store.list_events("solana-mainnet")), 1)
        self.worker.run_once()
        self.assertEqual(self.ingestion_store.get_checkpoint(
            "alchemy:solana-mainnet:" + scope)["next_slot"], 305)
        self.assertEqual(len(self.ingestion_store.list_events("solana-mainnet")), 1)

    def test_finalized_block_reorg_tombstones_and_replays_with_new_hash(self):
        self.provider.pages = {None: ((history(),), None)}
        self.worker.run_once()
        self.provider.changed_hashes[300] = "So11111111111111111111111111111111111111112"
        result = self.worker.run_once()
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        event = self.ingestion_store.get_event(
            SIGNATURE + ":outer:0", "solana-mainnet", "alchemy", scope)
        self.assertGreaterEqual(result["reorg_slots_detected"], 1)
        self.assertEqual(event.canonical_status, "CANONICAL")
        self.assertEqual(event.block_hash, "So11111111111111111111111111111111111111112")

    def test_reorg_during_active_page_range_restarts_from_first_page(self):
        self.worker.run_once()  # page 1 persists an opaque cursor
        self.provider.changed_hashes[300] = "So11111111111111111111111111111111111111112"
        self.worker.run_once()
        self.assertIsNone(self.provider.calls[-1][1])
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        event = self.ingestion_store.get_event(
            SIGNATURE + ":outer:0", "solana-mainnet", "alchemy", scope)
        self.assertEqual(event.block_hash, "So11111111111111111111111111111111111111112")
        self.assertEqual(event.canonical_status, "CANONICAL")

    def test_reorg_that_turns_a_previously_skipped_slot_into_a_produced_slot_rewinds(self):
        self.provider.pages = {None: ((), None)}
        produced = {300, 302, 304}
        def fetch_produced_slots(start, end):
            slots = tuple(slot for slot in range(start, end + 1) if slot in produced)
            self.provider.produced_slots = slots
            self.provider.range_start = start
            return slots
        self.provider.fetch_solana_produced_slots = fetch_produced_slots
        self.provider.produced_slots = (300, 302, 304)
        self.provider.range_start = 300
        self.worker.run_once()
        produced.add(301)
        result = self.worker.run_once()
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        self.assertGreaterEqual(result["reorg_slots_detected"], 1)
        journal = self.ingestion_store.get_solana_slot_journal(
            "solana-mainnet", "alchemy", scope, 300, 304)
        self.assertTrue(journal[301]["produced"])

    def test_reorg_that_removes_a_produced_slot_tombstones_its_events(self):
        self.provider.pages = {None: ((history(),), None)}
        self.worker.run_once()
        produced = {301, 302, 303, 304}
        self.provider.fetch_solana_produced_slots = lambda start, end: tuple(
            slot for slot in range(start, end + 1) if slot in produced)
        self.provider.produced_slots = (301, 302, 303, 304)
        self.provider.range_start = 300
        self.provider.pages = {None: ((), None)}
        result = self.worker.run_once()
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        event = self.ingestion_store.get_event(
            SIGNATURE + ":outer:0", "solana-mainnet", "alchemy", scope)
        self.assertGreaterEqual(result["reorg_slots_detected"], 1)
        self.assertEqual(event.canonical_status, "REORGED")

    def test_skipped_slot_is_journaled_without_fabricated_block_time(self):
        self.provider.pages = {None: ((), None)}
        self.provider.fetch_solana_produced_slots = lambda start, end: (300, 302, 304)
        self.provider.produced_slots = (300, 302, 304)
        self.provider.range_start = 300
        result = self.worker.run_once()
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        journal = self.ingestion_store.get_solana_slot_journal(
            "solana-mainnet", "alchemy", scope, 300, 304)
        self.assertFalse(journal[301]["produced"])
        self.assertIsNone(journal[301]["block_hash"])
        self.assertIsNone(journal[301]["block_time"])
        self.assertEqual(result["events_inserted"], 0)

    def test_pagination_page_must_continue_before_last_transaction_position(self):
        self.provider.pages = {
            None: ((history(slot=300),), "next"),
            "next": ((SolanaAddressTransaction(
                SIGNATURE, 300, 1794398400, rpc_tx(slot=300).raw, 18),), None),
        }
        self.worker.run_once()
        with self.assertRaises(ProviderTransportError):
            self.worker.run_once()
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        cursor = self.ingestion_store.get_checkpoint("alchemy:solana-mainnet:" + scope)
        self.assertEqual(cursor["pagination_token"], "next")

    def test_repeated_pagination_token_is_rejected_without_advancing_cursor(self):
        self.provider.pages = {
            None: ((history(),), "next"),
            "next": ((), "next"),
        }
        self.worker.run_once()
        with self.assertRaises(ProviderTransportError):
            self.worker.run_once()
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        cursor = self.ingestion_store.get_checkpoint("alchemy:solana-mainnet:" + scope)
        self.assertEqual(cursor["pagination_token"], "next")
        self.assertEqual(len(self.ingestion_store.list_events("solana-mainnet")), 1)

    def test_non_finalized_page_fails_without_checkpoint_advance(self):
        class NonFinalized(FakeSolanaProvider):
            def fetch_solana_address_transactions(inner, *args, **kwargs):
                page = super(NonFinalized, inner).fetch_solana_address_transactions(*args, **kwargs)
                return ProviderDataPage(page.provider, page.network_id, page.scope,
                                        page.records, page.next_cursor,
                                        finality_reference="commitment=confirmed")
        self.worker.provider = NonFinalized()
        with self.assertRaises(ProviderTransportError):
            self.worker.run_once()
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:solana-mainnet:" + scope))

    def test_provider_page_cannot_exceed_configured_page_size(self):
        from tests.test_solana_normalization import b58encode
        signatures = [b58encode(bytes([index + 1]) * 64) for index in range(18)]
        records = []
        for index in (17, 16):
            signature = signatures[index]
            raw = rpc_tx(slot=300, signature=signature,
                         err={"InstructionError": [0, "Custom"]}).raw
            raw["transactionIndex"] = index
            records.append(SolanaAddressTransaction(
                signature, 300, int(NOW.timestamp()) - 60, raw, index))
        self.provider.block_signatures[300] = signatures
        self.provider.pages = {None: (tuple(records), None)}
        self.worker.page_size = 1

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "PAGE_LIMIT_EXCEEDED")
        cursor_key = self.worker._cursor_key(WALLET, MAPPING_ID)
        self.assertIsNone(self.ingestion_store.get_checkpoint(cursor_key))
        self.assertEqual(self.ingestion_store.list_events("solana-mainnet"), [])


if __name__ == "__main__":
    unittest.main()
