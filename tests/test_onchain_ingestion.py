import json
import os
import tempfile
import unittest

from layer1.onchain_ingestion import (
    NormalizedTransferEvent, OnChainIngestionStore, normalize_evm_transfer_log,
    normalize_bitcoin_transaction_outputs,
)
from layer1.onchain_providers import BitcoinAddressTransaction, EvmTokenTransferLog


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

    def test_expected_checkpoint_rejects_a_stale_worker_commit(self):
        key = "alchemy:bnb-smart-chain:contract-1"
        identity = ("bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40)
        self.store.commit_page(key, {"next_block": 101}, [self.event()],
                               expected_cursor=None, scope_identity=identity)
        with self.assertRaisesRegex(RuntimeError, "checkpoint changed"):
            self.store.commit_page(key, {"next_block": 102}, (),
                                   expected_cursor=None, scope_identity=identity)
        self.assertEqual(self.store.get_checkpoint(key), {"next_block": 101})

    def test_canonical_block_hash_conflict_fails_closed_and_preserves_checkpoint(self):
        key = "canonical-block"
        first = {
            "network_id": "bnb-smart-chain-mainnet", "provider": "alchemy",
            "scope": "contract:0x" + "1" * 40, "block_number": 100,
            "block_hash": "b" * 64, "block_time": "2026-11-11T12:00:00+00:00",
        }
        self.store.commit_page(key, {"next_block": 101}, (), canonical_blocks=(first,))
        conflicting = {**first, "block_hash": "c" * 64}
        with self.assertRaisesRegex(ValueError, "canonical block hash conflict"):
            self.store.commit_page(key, {"next_block": 102}, (),
                                   expected_cursor={"next_block": 101},
                                   canonical_blocks=(conflicting,))
        self.assertEqual(self.store.get_checkpoint(key), {"next_block": 101})
        self.assertEqual(self.store.get_block_hash(
            "bnb-smart-chain-mainnet", "alchemy", first["scope"], 100), "b" * 64)

    def test_canonical_block_timestamp_cannot_change_without_a_hash_change(self):
        key = "canonical-time"
        block = {
            "network_id": "bnb-smart-chain-mainnet", "provider": "alchemy",
            "scope": "contract:0x" + "1" * 40, "block_number": 100,
            "block_hash": "b" * 64, "block_time": "2026-11-11T12:00:00+00:00",
        }
        self.store.commit_page(key, {"next_block": 101}, (), canonical_blocks=(block,))
        changed_time = {**block, "block_time": "2026-11-11T12:01:00+00:00"}
        with self.assertRaisesRegex(ValueError, "timestamp conflict"):
            self.store.commit_page(key, {"next_block": 102}, (),
                                   expected_cursor={"next_block": 101},
                                   canonical_blocks=(changed_time,))
        self.assertEqual(self.store.get_checkpoint(key), {"next_block": 101})

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



class BitcoinOutputNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.txid = "a" * 64
        self.monitored = "bc1qexampleaddress0000000000000000000000000"
        self.source_one = "1BoatSLRHtKNngkdXEeobR76b53LETtpyT"
        self.source_two = "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy"
        self.destination_one = self.monitored
        self.destination_two = "1BitcoinEaterAddressDontSendf59kuE"

    def history(self, confirmations=8, block_hash="b" * 64):
        return BitcoinAddressTransaction(
            self.txid, confirmations, 900000, block_hash, 1794398340,
            "CONFIRMED", {"txid": self.txid},
        )

    def transaction(self):
        return {
            "txid": self.txid, "blockHeight": 900000, "blockHash": "b" * 64,
            "blockTime": 1794398340, "confirmations": 8,
            "vin": [
                {"txid": "c" * 64, "vout": 1, "addresses": [self.source_one],
                 "isAddress": True, "value": "100000"},
                {"txid": "d" * 64, "vout": 0, "addresses": [self.source_two],
                 "isAddress": True, "value": "50000"},
            ],
            "vout": [
                {"n": 0, "value": "120000", "addresses": [self.destination_one], "isAddress": True},
                {"n": 1, "value": "29000", "addresses": [self.destination_two], "isAddress": True},
                {"n": 2, "value": "1000", "addresses": [], "isAddress": False},
            ],
        }

    def normalize(self, history=None, transaction=None, canonical_hash="b" * 64):
        return normalize_bitcoin_transaction_outputs(
            history or self.history(), transaction or self.transaction(),
            asset_id="coingecko:bitcoin", mapping_id="bitcoin-native-v1",
            monitored_address=self.monitored, canonical_block_hash=canonical_hash,
            block_time="2026-11-11T12:00:00+00:00",
            observed_at="2026-11-11T12:00:01+00:00",
            minimum_confirmations=6,
        )

    def test_creates_one_stable_event_per_addressable_output_with_satoshi_amounts(self):
        events = self.normalize()
        self.assertEqual([event.event_id for event in events], [self.txid + ":0", self.txid + ":1"])
        self.assertEqual([event.amount_raw for event in events], ["120000", "29000"])
        self.assertEqual([event.to_address for event in events], [self.destination_one, self.destination_two])
        self.assertEqual(events[0].event_index, 0)
        self.assertEqual(events[0].decimals, 8)
        self.assertEqual(events[0].from_address, None)
        self.assertEqual(events[0].from_addresses, (self.source_one, self.source_two))
        self.assertTrue(events[0].from_addresses_complete)
        self.assertEqual(events[0].scope, "address:" + self.monitored)

    def test_bitcoin_output_events_round_trip_source_address_set_through_atomic_store(self):
        events = self.normalize()
        tmp = tempfile.TemporaryDirectory()
        store = OnChainIngestionStore(os.path.join(tmp.name, "bitcoin.sqlite3"))
        try:
            store.commit_page("alchemy:bitcoin-mainnet:address:" + self.monitored,
                              {"next_block": 900001}, events)
            saved = store.get_event(
                events[0].event_id, "bitcoin-mainnet", "alchemy",
                "address:" + self.monitored,
            )
            self.assertEqual(saved.from_addresses, (self.source_one, self.source_two))
            self.assertTrue(saved.from_addresses_complete)
            self.assertIsNone(saved.from_address)
        finally:
            store.close()
            tmp.cleanup()

    def test_coinbase_output_has_no_fabricated_sender_address(self):
        details = self.transaction()
        details["vin"] = [{"coinbase": "03abcd"}]
        events = self.normalize(transaction=details)
        self.assertIsNone(events[0].from_address)
        self.assertEqual(events[0].from_addresses, ())
        self.assertTrue(events[0].from_addresses_complete)

    def test_rejects_details_that_do_not_contain_the_monitored_address(self):
        details = self.transaction()
        details["vout"][0]["addresses"] = ["bc1qother000000000000000000000000000000"]
        with self.assertRaisesRegex(ValueError, "does not contain the monitored address"):
            self.normalize(transaction=details)

    def test_marks_event_reorged_when_independently_fetched_canonical_hash_differs(self):
        events = self.normalize(canonical_hash="e" * 64)
        self.assertTrue(all(event.canonical_status == "REORGED" for event in events))

    def test_requires_explicit_minimum_confirmation_threshold(self):
        with self.assertRaisesRegex(ValueError, "confirmation threshold"):
            self.normalize(history=self.history(confirmations=5))

    def test_rejects_transaction_identity_or_block_reference_mismatch(self):
        details = self.transaction()
        details["txid"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "transaction identity"):
            self.normalize(transaction=details)

    def test_rejects_duplicate_output_indexes(self):
        details = self.transaction()
        details["vout"][1]["n"] = 0
        with self.assertRaisesRegex(ValueError, "output index"):
            self.normalize(transaction=details)

    def test_marks_input_address_set_incomplete_when_provider_cannot_decode_an_input(self):
        details = self.transaction()
        details["vin"][1] = {"txid": "d" * 64, "vout": 0, "addresses": [], "isAddress": False, "value": "50000"}
        events = self.normalize(transaction=details)
        self.assertFalse(events[0].from_addresses_complete)
        self.assertIsNone(events[0].from_address)
        self.assertEqual(events[0].from_addresses, (self.source_one,))

if __name__ == "__main__":
    unittest.main()
