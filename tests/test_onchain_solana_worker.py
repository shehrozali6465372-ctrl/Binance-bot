import os
import tempfile
import unittest
from datetime import datetime, timezone

from layer1.foundation import EligibilityDecision
from layer1.onchain import OnChainAssetMapping, OnChainIntelligenceEngine, OnChainObservation, OnChainStore
from layer1.onchain_ingestion import OnChainIngestionStore
from layer1.onchain_providers import ProviderDataPage, ProviderTransportError, SolanaAddressTransaction
from layer1.onchain_solana_worker import SolanaAddressIngestionWorker
from tests.test_solana_normalization import MINT, WALLET, BLOCKHASH, SIGNATURE, rpc_tx

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
MAPPING_ID = "sol-usdc-v1"


def history(slot=300, signature=SIGNATURE):
    raw = rpc_tx(slot=slot, signature=signature).raw
    return SolanaAddressTransaction(signature, slot, 1794398400, raw, 17)


class FakeSolanaProvider:
    def __init__(self):
        self.finalized_slot = 310
        self.changed_hashes = {}
        self.pages = {None: ((history(),), "next"), "next": ((), None)}
        self.fail_token_once = None
        self.calls = []

    def fetch_solana_finalized_slot(self):
        return self.finalized_slot

    def fetch_solana_produced_slots(self, start_slot, end_slot):
        return tuple(range(start_slot, end_slot + 1))

    def fetch_solana_block_header(self, slot):
        return {
            "number": slot, "hash": self.changed_hashes.get(slot, BLOCKHASH),
            "timestamp": 1794398400, "finality_reference": "commitment=finalized",
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
        self.mapping_store = OnChainStore(path, OnChainIntelligenceEngine(
            {"solana-mainnet": 86400}))
        self.ingestion_store = OnChainIngestionStore(path)
        stamp = NOW.isoformat()
        self.mapping = OnChainAssetMapping(
            MAPPING_ID, "coingecko:usd-coin", "USDC", "solana-mainnet",
            "SOLANA", "mainnet-beta", "TOKEN", MINT, "SPL_TOKEN", 6,
            "VERIFIED", "OFFICIAL_PROJECT", "https://solana.com",
            "2026-11-11T10:00:00+00:00")
        eligibility = EligibilityDecision(
            status="ELIGIBLE", asset_id="coingecko:usd-coin", symbol="USDC",
            eligible_pairs=("USDCUSDT",), verified_at=stamp,
            identity_proof_status="VERIFIED", identity_proof_source="coingecko_coin_tickers",
            identity_proof_verified_at=stamp, identity_proof_source_timestamp=stamp,
            identity_proof_data_hash="a" * 64)
        observation = OnChainObservation(
            "sol-map-proof", MAPPING_ID, "coingecko:usd-coin", "solana-mainnet",
            "mainnet-beta", "alchemy", "solana-mainnet", "TRANSFER", 290,
            BLOCKHASH, SIGNATURE, stamp, stamp, "FINALIZED", "commitment=finalized")
        self.mapping_store.save_verified(eligibility, self.mapping, observation)
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

    def test_ingests_token_transfer_and_atomically_journals_produced_and_skipped_slots(self):
        self.provider.pages = {None: ((history(),), None)}
        result = self.worker.run_once()
        scope = f"address:{WALLET}:mapping:{MAPPING_ID}"
        events = self.ingestion_store.list_events("solana-mainnet", canonical_only=True)
        self.assertEqual(result["events_inserted"], 1)
        self.assertEqual(events[0].amount_raw, "1234567")
        self.assertEqual(events[0].scope, scope)
        self.assertEqual(events[0].event_id, SIGNATURE + ":outer:0")
        self.assertEqual(self.ingestion_store.get_checkpoint(
            "alchemy:solana-mainnet:" + scope)["next_slot"], 305)
        journal = self.ingestion_store.get_solana_slot_journal(
            "solana-mainnet", "alchemy", scope, 300, 304)
        self.assertEqual(set(journal), set(range(300, 305)))
        self.assertTrue(all(item["produced"] for item in journal.values()))

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
        self.provider.fetch_solana_produced_slots = lambda start, end: tuple(
            slot for slot in range(start, end + 1) if slot in produced)
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


if __name__ == "__main__":
    unittest.main()
