import json
import os
import tempfile
import unittest

from layer1.onchain_ingestion import (NormalizedTransferEvent, OnChainIngestionStore, normalize_evm_transfer_log)
from layer1.onchain_providers import EvmTokenTransferLog


class OnChainIngestionStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = OnChainIngestionStore(os.path.join(self.tmp.name, "ingestion.sqlite3"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def event(self, event_id="0x" + "a" * 64 + ":2", block_hash="0x" + "b" * 64,
              status="CANONICAL"):
        return NormalizedTransferEvent(
            event_id=event_id, network_id="bnb-smart-chain-mainnet",
            provider="alchemy", scope="contract:0x" + "1" * 40,
            asset_id="coingecko:example", mapping_id="example-bnb-v1",
            transaction_hash="0x" + "a" * 64, block_number=100,
            block_hash=block_hash, event_index=2,
            from_address="0x" + "2" * 40, to_address="0x" + "3" * 40,
            amount_raw="12345678901234567890", decimals=18,
            block_time="2026-11-11T12:00:00+00:00",
            observed_at="2026-11-11T12:00:01+00:00",
            canonical_status=status, provenance="eth_getLogs",
        )

    def test_page_events_and_checkpoint_commit_atomically_and_resume(self):
        cursor = {"from_block": 100, "to_block": 109, "next": "opaque"}
        result = self.store.commit_page("alchemy:bnb-smart-chain-mainnet:contract-1",
                                        cursor, [self.event()])
        self.assertEqual(result, {"inserted": 1, "duplicates": 0, "tombstoned": 0})
        self.assertEqual(self.store.get_checkpoint("alchemy:bnb-smart-chain-mainnet:contract-1"), cursor)
        self.assertEqual(len(self.store.list_events("bnb-smart-chain-mainnet")), 1)

    def test_replayed_page_is_idempotent_and_conflicting_event_identity_is_rejected(self):
        key = "alchemy:bnb-smart-chain-mainnet:contract-1"
        self.store.commit_page(key, {"next": "x"}, [self.event()])
        result = self.store.commit_page(key, {"next": "x"}, [self.event()])
        self.assertEqual(result["duplicates"], 1)
        changed = self.event()
        changed = NormalizedTransferEvent(**{**changed.__dict__, "amount_raw": "999"})
        with self.assertRaisesRegex(ValueError, "identity collision"):
            self.store.commit_page(key, {"next": "y"}, [changed])
        self.assertEqual(self.store.get_checkpoint(key), {"next": "x"})

    def test_replayed_canonical_event_can_only_transition_monotonically_to_reorged(self):
        canonical = self.event(status="CANONICAL")
        self.store.commit_page("cursor", {"next": 1}, [canonical])
        tombstone = NormalizedTransferEvent(**{**canonical.__dict__, "canonical_status": "REORGED"})
        result = self.store.commit_page("cursor", {"next": 2}, [tombstone])
        self.assertEqual(result["tombstoned"], 1)
        self.assertEqual(self.store.get_event(canonical.event_id, canonical.network_id).canonical_status, "REORGED")
        self.assertEqual(self.store.list_events(canonical.network_id, canonical_only=True), [])
        # A later stale canonical page must not resurrect a tombstoned event.
        self.store.commit_page("cursor", {"next": 3}, [canonical])
        self.assertEqual(self.store.get_event(canonical.event_id, canonical.network_id).canonical_status, "REORGED")

    def test_removed_log_is_persisted_as_reorg_tombstone_not_active_transfer(self):
        removed = self.event(status="REORGED")
        self.store.commit_page("cursor", {"next": None}, [removed])
        saved = self.store.get_event(removed.event_id, removed.network_id)
        self.assertEqual(saved.canonical_status, "REORGED")
        self.assertEqual(self.store.list_events(removed.network_id, canonical_only=True), [])

    def test_canonical_block_reconciliation_marks_orphaned_events_reorged(self):
        event = self.event()
        self.store.commit_page("cursor", {"next": None}, [event])
        changed = self.store.reconcile_block(event.network_id, 100, "0x" + "c" * 64)
        self.assertEqual(changed, 1)
        self.assertEqual(self.store.get_event(event.event_id, event.network_id).canonical_status, "REORGED")

    def test_evm_log_normalizer_uses_transaction_hash_and_log_index_and_keeps_removed_tombstone(self):
        raw = EvmTokenTransferLog(
            network_id="bnb-smart-chain-mainnet", contract_address="0x" + "1" * 40,
            from_address="0x" + "2" * 40, to_address="0x" + "3" * 40,
            amount_raw="123", block_number=100, block_hash="0x" + "b" * 64,
            transaction_hash="0x" + "a" * 64, log_index=7, removed=True,
        )
        normalized = normalize_evm_transfer_log(
            raw, asset_id="coingecko:example", mapping_id="example-bnb-v1",
            expected_contract_address="0x" + "1" * 40,
            canonical_block_hash="0x" + "b" * 64,
            decimals=18, block_time="2026-11-11T12:00:00+00:00",
            observed_at="2026-11-11T12:00:01+00:00",
            scope="contract:0x" + "1" * 40,
        )
        self.assertEqual(normalized.event_id, "0x" + "a" * 64 + ":7")
        self.assertEqual(normalized.canonical_status, "REORGED")
        self.assertEqual(normalized.amount_raw, "123")

    def test_evm_log_normalizer_rejects_wrong_contract_and_tombstones_noncanonical_block_hash(self):
        raw = EvmTokenTransferLog(
            network_id="bnb-smart-chain-mainnet", contract_address="0x" + "1" * 40,
            from_address="0x" + "2" * 40, to_address="0x" + "3" * 40,
            amount_raw="123", block_number=100, block_hash="0x" + "b" * 64,
            transaction_hash="0x" + "a" * 64, log_index=8, removed=False,
        )
        kwargs = dict(asset_id="coingecko:example", mapping_id="example-bnb-v1",
                      expected_contract_address="0x" + "1" * 40, decimals=18,
                      block_time="2026-11-11T12:00:00+00:00",
                      observed_at="2026-11-11T12:00:01+00:00",
                      scope="contract:0x" + "1" * 40)
        with self.assertRaisesRegex(ValueError, "does not match"):
            normalize_evm_transfer_log(raw, **{**kwargs, "expected_contract_address": "0x" + "4" * 40},
                                       canonical_block_hash="0x" + "b" * 64)
        reorged = normalize_evm_transfer_log(raw, **kwargs, canonical_block_hash="0x" + "c" * 64)
        self.assertEqual(reorged.canonical_status, "REORGED")

    def test_page_batch_rolls_back_all_events_and_checkpoint_on_identity_conflict(self):
        key = "alchemy:bnb-smart-chain:scope"
        first = self.event(event_id="first")
        self.store.commit_page(key, {"next": "old"}, [first])
        conflict = NormalizedTransferEvent(**{**first.__dict__, "amount_raw": "999"})
        second = self.event(event_id="second")
        with self.assertRaisesRegex(ValueError, "identity collision"):
            self.store.commit_page(key, {"next": "new"}, [second, conflict])
        self.assertEqual(self.store.get_checkpoint(key), {"next": "old"})
        self.assertIsNone(self.store.get_event("second", "bnb-smart-chain-mainnet"))

    def test_invalid_amount_and_noncanonical_cursor_json_are_rejected(self):
        event = self.event()
        invalid = NormalizedTransferEvent(**{**event.__dict__, "amount_raw": "1.5"})
        with self.assertRaises(ValueError):
            self.store.commit_page("cursor", {"next": float("nan")}, [event])
        with self.assertRaises(ValueError):
            self.store.commit_page("cursor", {"next": None}, [invalid])


if __name__ == "__main__":
    unittest.main()
