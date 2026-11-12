import os
import tempfile
import unittest
from datetime import datetime, timezone

from layer1.foundation import EligibilityDecision
from layer1.onchain import OnChainAssetMapping, OnChainIntelligenceEngine, OnChainObservation, OnChainStore
from layer1.onchain_ingestion import OnChainIngestionStore
from layer1.onchain_providers import BitcoinAddressTransaction, ProviderDataPage, ProviderTransportError
from layer1.onchain_bitcoin_worker import BitcoinAddressIngestionWorker

ADDRESS = "bc1q" + "a" * 38
TXID = "a" * 64
HASH = "b" * 64
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def history(txid=TXID, height=100, confirmations=8, block_hash=HASH):
    return BitcoinAddressTransaction(txid, confirmations, height, block_hash, 1794398400,
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
        return self.headers.get(height, {
            "number": height, "hash": HASH, "timestamp": 1794398400 + height,
        })

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
        self.mapping_store = OnChainStore(path, OnChainIntelligenceEngine(
            {"bitcoin-mainnet": 86400}, {"bitcoin-mainnet": 6}))
        self.ingestion_store = OnChainIngestionStore(path)
        self.mapping = OnChainAssetMapping(
            "bitcoin-native-v1", "coingecko:bitcoin", "BTC", "bitcoin-mainnet",
            "UTXO", "bitcoin-mainnet", "NATIVE", None, None, 8, "VERIFIED",
            "OFFICIAL_NETWORK", "https://bitcoin.org", "2026-11-11T10:00:00+00:00")
        stamp = NOW.isoformat()
        eligibility = EligibilityDecision(
            status="ELIGIBLE", asset_id="coingecko:bitcoin", symbol="BTC",
            eligible_pairs=("BTCUSDT",), verified_at=stamp,
            identity_proof_status="VERIFIED", identity_proof_source="coingecko_coin_tickers",
            identity_proof_verified_at=stamp, identity_proof_source_timestamp=stamp,
            identity_proof_data_hash="a" * 64)
        observation = OnChainObservation(
            "btc-map-proof", self.mapping.mapping_id, self.mapping.asset_id,
            "bitcoin-mainnet", "bitcoin-mainnet", "alchemy", "bitcoin-mainnet",
            "TRANSFER", 90, HASH, TXID, stamp, stamp, "CONFIRMED", "confirmations=8")
        self.mapping_store.save_verified(eligibility, self.mapping, observation)
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
        self.provider.headers[102] = {"number": 102, "hash": "e" * 64, "timestamp": 1794398502}
        self.provider.pages = {1: ((history("d" * 64, 102, 8, "e" * 64),), 1)}
        self.provider.details["d" * 64] = transaction(history("d" * 64, 102, 8, "e" * 64))
        result = self.worker.run_once()
        self.assertGreaterEqual(result["reorg_blocks_detected"], 1)
        self.assertEqual(self.ingestion_store.get_event(
            "d" * 64 + ":0", "bitcoin-mainnet", "alchemy", "address:" + ADDRESS).canonical_status,
            "CANONICAL")

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
            "number": 100, "hash": "e" * 64, "timestamp": 1794398400,
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


if __name__ == "__main__":
    unittest.main()
