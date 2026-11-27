import hashlib
import json
import os
import tempfile
import unittest

from layer1.onchain_ingestion import (
    NormalizedTransferEvent, OnChainFinalitySnapshot, OnChainIngestionStore,
    normalize_evm_transfer_log, normalize_bitcoin_transaction_outputs,
)
from layer1.onchain_providers import (
    AlchemyReadOnlyAdapter, BitcoinAddressTransaction, EvmTokenTransferLog,
    ProviderResponseReceipt, ReadOnlyJsonRpcTransport, _ACTIVE_PAGE_RECEIPTS,
    _capture_provider_run_receipts, drain_provider_run_receipts,
    _approved_endpoint_profile_sha256,
)


def captured_batch(*receipts):
    @_capture_provider_run_receipts
    def capture():
        _ACTIVE_PAGE_RECEIPTS.get().extend(receipts)
        return drain_provider_run_receipts()
    return capture()



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

    def test_sqlite_quarantine_rejects_boolean_raw_slot_alias(self):
        from tests.test_solana_normalization import BLOCKHASH, SIGNATURE
        scope = "address:wallet-test:mapping:sol-usdc-v1"
        with self.assertRaisesRegex(ValueError, "Solana quarantine transaction record is malformed"):
            self.store.commit_page(
                "solana:wallet-test", {"next_slot": 2}, (), expected_cursor=None,
                scope_identity=("solana-mainnet", "alchemy", scope),
                canonical_slots=({
                    "network_id": "solana-mainnet", "provider": "alchemy",
                    "scope": scope, "slot": 1, "produced": True,
                    "block_hash": BLOCKHASH, "block_time": None,
                },),
                solana_quarantine_records=({
                    "signature": SIGNATURE, "slot": 1, "transaction_index": 0,
                    "block_hash": BLOCKHASH,
                    "payload": {
                        "block_time": None, "raw": {"slot": True},
                        "observed_at": "2026-11-27T12:00:00+00:00",
                    },
                },),
            )

    def test_sqlite_quarantine_rejects_raw_block_time_mismatch(self):
        from tests.test_solana_normalization import BLOCKHASH, SIGNATURE
        scope = "address:wallet-test:mapping:sol-usdc-v1"
        with self.assertRaisesRegex(ValueError, "Solana quarantine transaction record is malformed"):
            self.store.commit_page(
                "solana:wallet-test", {"next_slot": 2}, (), expected_cursor=None,
                scope_identity=("solana-mainnet", "alchemy", scope),
                canonical_slots=({
                    "network_id": "solana-mainnet", "provider": "alchemy",
                    "scope": scope, "slot": 1, "produced": True,
                    "block_hash": BLOCKHASH, "block_time": None,
                },),
                solana_quarantine_records=({
                    "signature": SIGNATURE, "slot": 1, "transaction_index": 0,
                    "block_hash": BLOCKHASH,
                    "payload": {
                        "block_time": 100, "raw": {"slot": 1, "blockTime": 101},
                        "observed_at": "2026-11-27T12:00:00+00:00",
                    },
                },),
            )

    def test_sqlite_quarantine_rejects_missing_transaction_execution_status(self):
        from tests.test_solana_normalization import BLOCKHASH, SIGNATURE
        scope = "address:wallet-test:mapping:sol-usdc-v1"
        with self.assertRaisesRegex(ValueError, "Solana quarantine transaction record is malformed"):
            self.store.commit_page(
                "solana:wallet-test", {"next_slot": 2}, (), expected_cursor=None,
                scope_identity=("solana-mainnet", "alchemy", scope),
                canonical_slots=({
                    "network_id": "solana-mainnet", "provider": "alchemy",
                    "scope": scope, "slot": 1, "produced": True,
                    "block_hash": BLOCKHASH, "block_time": None,
                },),
                solana_quarantine_records=({
                    "signature": SIGNATURE, "slot": 1, "transaction_index": 0,
                    "block_hash": BLOCKHASH,
                    "payload": {
                        "block_time": None,
                        "raw": {"slot": 1, "transaction": {"signatures": [SIGNATURE], "message": {}}, "meta": {}},
                        "observed_at": "2026-11-27T12:00:00+00:00",
                    },
                },),
            )

    def test_finality_snapshot_rejects_boolean_version_and_wrong_network_policy(self):
        with self.assertRaisesRegex(ValueError, "identity is invalid"):
            OnChainFinalitySnapshot(
                version=True, network_id="bnb-smart-chain-mainnet",
                status="FINALIZED", reference="eth_getFinalizedHeader",
            )
        with self.assertRaisesRegex(ValueError, "Bitcoin finality snapshot"):
            OnChainFinalitySnapshot(
                version=1, network_id="bitcoin-mainnet",
                status="FINALIZED", reference="commitment=finalized",
            )

    def test_page_material_preserves_typed_chain_finality_snapshot(self):
        event = NormalizedTransferEvent(
            **{
                **self.event().__dict__,
                "finality_snapshot": OnChainFinalitySnapshot(
                    version=1, network_id="bnb-smart-chain-mainnet", status="FINALIZED",
                    reference="eth_getFinalizedHeader:verifiedValidatorNum=-3",
                ),
            }
        )
        key = "alchemy:bnb-smart-chain:finality-snapshot"
        self.store.commit_page(
            key, {"next_block": 101}, [event],
            expected_cursor=None,
            scope_identity=(event.network_id, event.provider, event.scope),
            canonical_blocks=({
                "network_id": event.network_id, "provider": event.provider,
                "scope": event.scope, "block_number": event.block_number,
                "block_hash": event.block_hash, "block_time": event.block_time,
            },),
        )
        page_id = self.store.conn.execute(
            "SELECT page_id FROM layer1_onchain_ingestion_pages WHERE cursor_key=?", (key,),
        ).fetchone()[0]
        raw = self.store.conn.execute(
            "SELECT page_material_json FROM layer1_onchain_ingestion_pages WHERE page_id=?",
            (page_id,),
        ).fetchone()[0]
        payload = json.loads(raw)["events"][0]["finality_snapshot"]
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["network_id"], event.network_id)
        self.assertEqual(payload["status"], "FINALIZED")
        self.assertEqual(payload["reference"], "eth_getFinalizedHeader:verifiedValidatorNum=-3")

    def test_page_events_and_checkpoint_commit_atomically_and_resume(self):
        cursor = {"from_block": 100, "to_block": 109, "next": "opaque"}
        result = self.store.commit_page("alchemy:bnb-smart-chain-mainnet:contract-1",
                                        cursor, [self.event()], expected_cursor=self.store.get_checkpoint("alchemy:bnb-smart-chain-mainnet:contract-1"))
        self.assertEqual(result, {"inserted": 1, "duplicates": 0, "tombstoned": 0})
        self.assertEqual(self.store.get_checkpoint("alchemy:bnb-smart-chain-mainnet:contract-1"), cursor)
        self.assertEqual(len(self.store.list_events("bnb-smart-chain-mainnet")), 1)

    def test_ingestion_store_rejects_caller_constructed_provider_receipt_tuple(self):
        key = "alchemy:bnb-smart-chain:contract-1"
        identity = ("bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40)
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
        )
        with self.assertRaisesRegex(ValueError, "captured provider receipt batch"):
            self.store.commit_page(
                key, {"next_block": 101}, [self.event()], expected_cursor=None,
                scope_identity=identity, provider_receipts=(receipt,),
            )
        self.assertIsNone(self.store.get_checkpoint(key))

    def test_new_page_commit_rejects_receipt_without_endpoint_profile_fingerprint(self):
        key = "alchemy:bnb-smart-chain:contract-1"
        identity = ("bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40)
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
        )
        with self.assertRaisesRegex(ValueError, "endpoint profile fingerprint"):
            self.store.commit_page(
                key, {"next_block": 101}, [self.event()], expected_cursor=None,
                scope_identity=identity, provider_receipts=captured_batch(receipt),
            )
        self.assertIsNone(self.store.get_checkpoint(key))

    def test_new_page_commit_rejects_fingerprint_outside_approved_provider_network_profile(self):
        key = "alchemy:bnb-smart-chain:contract-1"
        identity = ("bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40)
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="f" * 64,
        )
        with self.assertRaisesRegex(ValueError, "approved provider/network endpoint profile"):
            self.store.commit_page(
                key, {"next_block": 101}, [self.event()], expected_cursor=None,
                scope_identity=identity, provider_receipts=captured_batch(receipt),
            )
        self.assertIsNone(self.store.get_checkpoint(key))

    def test_provider_response_receipts_commit_atomically_and_survive_store_reopen(self):
        key = "alchemy:bnb-smart-chain:contract-1"
        identity = ("bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40)
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
            tls_peer_certificate_sha256="c" * 64,
        )
        database = os.path.join(self.tmp.name, "ingestion.sqlite3")
        self.store.commit_page(
            key, {"next_block": 101}, [self.event()], expected_cursor=None,
            scope_identity=identity, provider_receipts=captured_batch(receipt),
        )
        self.store.close()
        self.store = OnChainIngestionStore(database)
        saved = self.store.list_page_receipts(key)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0], receipt)

    def test_raw_provider_response_receipts_remain_bound_to_page_after_store_reopen(self):
        contract = "0x" + "3" * 40
        raw_responses = [
            b'{"jsonrpc":"2.0","id":1,"result":"0x1"}',
            (b'{"jsonrpc":"2.0","id":1,"result":{"number":"0x200","hash":"0x'
             + b'c' * 64 + b'"}}'),
            b'{"jsonrpc":"2.0","id":1,"result":[]}',
        ]
        consumed = []

        class Response:
            def __init__(self, raw):
                self.raw = raw
                self.headers = {"Content-Length": str(len(raw))}
                self.peer_certificate_sha256 = "d" * 64

            def __enter__(self): return self
            def __exit__(self, *args): return False
            def getcode(self): return 200
            def read(self, size=-1):
                if size < 0:
                    size = len(self.raw)
                chunk, self.raw = self.raw[:size], self.raw[size:]
                return chunk

        def opener(request, timeout):
            raw = raw_responses[len(consumed)]
            consumed.append(raw)
            return Response(raw)

        adapter = AlchemyReadOnlyAdapter(
            "test-key",
            transport_factory=lambda endpoint, timeout: ReadOnlyJsonRpcTransport(
                endpoint, timeout, opener=opener, max_response_bytes=4096,
            ),
        )
        page = adapter.fetch_ethereum_erc20_transfer_logs(contract, 256, 265)
        self.assertEqual(len(page.response_receipts), 3)
        self.assertEqual(
            [item.response_sha256 for item in page.response_receipts],
            [hashlib.sha256(raw).hexdigest() for raw in raw_responses],
        )
        cursor_key = f"alchemy:ethereum-mainnet:{contract}"
        scope_identity = ("ethereum-mainnet", "alchemy", contract)
        self.store.commit_page(
            cursor_key, {"next_block": 266}, [], expected_cursor=None,
            scope_identity=scope_identity,
            canonical_blocks=[{
                "network_id": "ethereum-mainnet", "provider": "alchemy",
                "scope": contract, "block_number": 512,
                "block_hash": "0x" + "c" * 64,
                "block_time": "2026-11-26T12:00:00+00:00",
            }],
            provider_receipts=captured_batch(*page.response_receipts),
        )
        database = os.path.join(self.tmp.name, "ingestion.sqlite3")
        self.store.close()
        self.store = OnChainIngestionStore(database)
        saved = self.store.list_page_receipts(cursor_key)
        self.assertEqual(saved, page.response_receipts)
        self.assertTrue(all(
            item.endpoint_profile_sha256 == _approved_endpoint_profile_sha256("alchemy", "ethereum-mainnet")
            for item in saved
        ))
        self.assertEqual([item.tls_peer_certificate_sha256 for item in saved], ["d" * 64] * 3)
        page_id = self.store.list_ingestion_pages()[0][1]
        material = self.store.get_page_acceptance_material(cursor_key, page_id)
        self.assertEqual(material["receipts"], [item.__dict__ for item in page.response_receipts])
        self.assertEqual(
            [item["response_sha256"] for item in material["receipts"]],
            [hashlib.sha256(raw).hexdigest() for raw in raw_responses],
        )

    def test_same_normalized_page_cannot_be_replayed_with_different_provider_receipts(self):
        key = "alchemy:bnb-smart-chain:contract-1"
        identity = ("bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40)
        first = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
        )
        substituted = ProviderResponseReceipt(
            **{**first.__dict__, "response_sha256": "c" * 64}
        )
        args = dict(
            cursor_key=key, next_cursor={"next_block": 101}, events=[self.event()],
            scope_identity=identity, expected_cursor=None,
        )
        self.store.commit_page(**args, provider_receipts=captured_batch(first))
        with self.assertRaisesRegex(RuntimeError, "checkpoint changed"):
            self.store.commit_page(**args, provider_receipts=captured_batch(substituted))
        self.assertEqual(self.store.get_checkpoint(key), {"next_block": 101})
        self.assertEqual(self.store.list_page_receipts(key), (first,))

    def test_list_page_receipts_rejects_sequence_gaps_even_when_receipt_digest_matches(self):
        key = "alchemy:bnb-smart-chain:receipt-sequence-gap"
        identity = ("bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40)
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
        )
        self.store.commit_page(
            key, {"next_block": 101}, [self.event()], expected_cursor=None,
            scope_identity=identity, provider_receipts=captured_batch(receipt),
        )
        page_id, payload = self.store.conn.execute(
            "SELECT page_id, receipts_json FROM layer1_onchain_ingestion_pages WHERE cursor_key=?",
            (key,),
        ).fetchone()
        tampered = json.loads(payload)
        tampered[0]["sequence"] = 2
        canonical = self.store._canonical(tampered)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.store.conn.execute(
            "UPDATE layer1_onchain_ingestion_pages SET receipts_json=?, receipt_sha256=? WHERE page_id=?",
            (canonical, digest, page_id),
        )
        with self.assertRaisesRegex(ValueError, "receipt sequence"):
            self.store.list_page_receipts(key)

    def test_persisted_provider_receipt_digest_detects_storage_tampering(self):
        key = "alchemy:bnb-smart-chain:contract-1"
        identity = ("bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40)
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
        )
        self.store.commit_page(
            key, {"next_block": 101}, [self.event()], scope_identity=identity,
            provider_receipts=captured_batch(receipt),
        expected_cursor=self.store.get_checkpoint(key))
        self.store.conn.execute(
            "UPDATE layer1_onchain_ingestion_pages SET receipts_json=? WHERE cursor_key=?",
            (json.dumps([{**receipt.__dict__, "response_sha256": "c" * 64}]), key),
        )
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.store.list_page_receipts(key)

    def test_receipt_rows_roll_back_with_event_and_checkpoint_on_failed_page(self):
        key = "alchemy:bnb-smart-chain:contract-1"
        identity = ("bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40)
        original = self.event()
        self.store.commit_page(key, {"next_block": 101}, [original], expected_cursor=None,
                               scope_identity=identity)
        conflict = NormalizedTransferEvent(**{**original.__dict__, "amount_raw": "999"})
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
        )
        with self.assertRaisesRegex(ValueError, "identity collision"):
            self.store.commit_page(
                key, {"next_block": 102}, [self.event(event_id="new"), conflict],
                expected_cursor={"next_block": 101}, scope_identity=identity,
                provider_receipts=captured_batch(receipt),
            )
        self.assertEqual(self.store.get_checkpoint(key), {"next_block": 101})
        self.assertEqual(self.store.list_page_receipts(key), ())
        self.assertIsNone(self.store.get_event("new", "bnb-smart-chain-mainnet"))

    def _commit_signable_page(self, *, with_receipts=True):
        from layer1.onchain import OnChainIntelligenceEngine
        key = "alchemy:bnb-smart-chain:contract-acceptance"
        identity = ("bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40)
        event = self.event()
        block = {
            "network_id": event.network_id, "provider": event.provider,
            "scope": event.scope, "block_number": event.block_number,
            "block_hash": event.block_hash, "block_time": event.block_time,
        }
        receipts = ()
        if with_receipts:
            receipts = (ProviderResponseReceipt(
                sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
                method="eth_getLogs", request_sha256="a" * 64,
                response_sha256="b" * 64, response_bytes=128, http_status=200,
                received_at="2026-11-26T12:00:00+00:00",
                endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
            ),)
        self.store.commit_page(
            key, {"next_block": 101}, [event], expected_cursor=None,
            scope_identity=identity, canonical_blocks=(block,),
            provider_receipts=captured_batch(*receipts) if with_receipts else None,
        )
        page_id = self.store.conn.execute(
            "SELECT page_id FROM layer1_onchain_ingestion_pages WHERE cursor_key=?", (key,),
        ).fetchone()[0]
        engine = OnChainIntelligenceEngine(
            receipt_signing_key=b"test-only-onchain-ingestion-page-key-32-bytes",
            receipt_key_id="ingestion-test-v1",
        )
        return key, page_id, event, engine

    def test_ingestion_page_acceptance_is_store_derived_persisted_and_reverified_after_reopen(self):
        from layer1.onchain import OnChainIntelligenceEngine
        key, page_id, event, engine = self._commit_signable_page()
        envelope = engine.sign_ingestion_page(self.store, key, page_id)
        self.assertEqual(envelope.page_id, page_id)
        self.assertEqual(envelope.key_id, "ingestion-test-v1")
        self.assertTrue(engine.verify_ingestion_page_acceptance(self.store, key, page_id))
        self.assertEqual(engine.sign_ingestion_page(self.store, key, page_id), envelope)

        database = os.path.join(self.tmp.name, "ingestion.sqlite3")
        self.store.close()
        self.store = OnChainIngestionStore(database)
        restarted_engine = OnChainIntelligenceEngine(
            receipt_signing_key=b"test-only-onchain-ingestion-page-key-32-bytes",
            receipt_key_id="ingestion-test-v1",
        )
        self.assertTrue(restarted_engine.verify_ingestion_page_acceptance(self.store, key, page_id))

    def test_page_acceptance_refuses_legacy_receipt_without_endpoint_profile_fingerprint(self):
        key, page_id, _, engine = self._commit_signable_page()
        row = self.store.conn.execute(
            "SELECT receipts_json FROM layer1_onchain_ingestion_pages WHERE page_id=?", (page_id,),
        ).fetchone()
        receipts = json.loads(row[0])
        for receipt in receipts:
            receipt.pop("endpoint_profile_sha256", None)
        receipts_json = self.store._canonical(receipts)
        digest = hashlib.sha256(receipts_json.encode("utf-8")).hexdigest()
        self.store.conn.execute(
            "UPDATE layer1_onchain_ingestion_pages SET receipts_json=?, receipt_sha256=? WHERE page_id=?",
            (receipts_json, digest, page_id),
        )
        self.store.conn.commit()

        with self.assertRaisesRegex(ValueError, "endpoint profile fingerprint"):
            engine.sign_ingestion_page(self.store, key, page_id)
        self.assertIsNone(self.store.get_page_acceptance(key, page_id))

    def test_ingestion_page_signer_rejects_pages_without_captured_receipts_and_forged_store(self):
        key, page_id, _, engine = self._commit_signable_page(with_receipts=False)
        with self.assertRaisesRegex(ValueError, "no complete captured provider receipt lineage"):
            engine.sign_ingestion_page(self.store, key, page_id)
        with self.assertRaises(TypeError):
            engine.sign_ingestion_page(object(), key, page_id)

    def test_pending_recovery_surfaces_unreceipted_evidence_pages_as_rejected(self):
        key, page_id, _, engine = self._commit_signable_page(with_receipts=False)
        self.assertEqual(self.store.list_pending_page_acceptances(), ((key, page_id),))
        result = engine.sign_pending_ingestion_pages(self.store)
        self.assertEqual(result, {"signed": 0, "pending": 1, "rejected": 1})
        self.assertIsNone(self.store.get_page_acceptance(key, page_id))

    def test_pending_recovery_does_not_queue_checkpoint_only_pages(self):
        key = "checkpoint-only-recovery"
        self.store.commit_page(key, {"next": 1}, (), expected_cursor=None)
        self.assertEqual(self.store.list_pending_page_acceptances(), ())

    def test_ingestion_page_signing_rechecks_canonical_evidence_atomically_before_persisting(self):
        import sqlite3
        from unittest.mock import patch

        key, page_id, event, engine = self._commit_signable_page()
        original_save = self.store.save_page_acceptance

        def reorg_between_validation_and_save(*args, **kwargs):
            # Model a second worker committing a canonical-chain change after
            # the signer read/validated page material but before envelope save.
            other = sqlite3.connect(os.path.join(self.tmp.name, "ingestion.sqlite3"), timeout=5)
            try:
                other.execute(
                    "UPDATE layer1_onchain_ingestion_blocks SET block_hash=? "
                    "WHERE network_id=? AND provider=? AND scope=? AND block_number=?",
                    ("0x" + "c" * 64, event.network_id, event.provider,
                     event.scope, event.block_number),
                )
                other.commit()
            finally:
                other.close()
            return original_save(*args, **kwargs)

        with patch.object(self.store, "save_page_acceptance", side_effect=reorg_between_validation_and_save):
            with self.assertRaisesRegex(ValueError, "canonical block evidence"):
                engine.sign_ingestion_page(self.store, key, page_id)

        self.assertIsNone(self.store.get_page_acceptance(key, page_id))
        self.assertEqual(self.store.list_pending_page_acceptances(), ((key, page_id),))

    def test_ingestion_page_acceptance_rejects_tampered_persisted_events_and_receipts(self):
        key, page_id, event, engine = self._commit_signable_page()
        engine.sign_ingestion_page(self.store, key, page_id)
        tampered_event = NormalizedTransferEvent(**{**event.__dict__, "amount_raw": "999"})
        self.store.conn.execute(
            "UPDATE layer1_onchain_transfer_events SET payload_json=? WHERE event_id=?",
            (self.store._canonical(tampered_event.__dict__), event.event_id),
        )
        self.assertFalse(engine.verify_ingestion_page_acceptance(self.store, key, page_id))

        # Restore the event, then tamper the raw provider receipt payload.
        self.store.conn.execute(
            "UPDATE layer1_onchain_transfer_events SET payload_json=? WHERE event_id=?",
            (self.store._canonical(event.__dict__), event.event_id),
        )
        self.store.conn.execute(
            "UPDATE layer1_onchain_ingestion_pages SET receipts_json=? WHERE page_id=?",
            (json.dumps([{"sequence": 1, "provider": "alchemy", "network_id": "bnb-smart-chain-mainnet", "method": "eth_getLogs", "request_sha256": "a" * 64, "response_sha256": "c" * 64, "response_bytes": 128, "http_status": 200, "received_at": "2026-11-26T12:00:00+00:00"}]), page_id),
        )
        self.assertFalse(engine.verify_ingestion_page_acceptance(self.store, key, page_id))

    def test_ingestion_page_acceptance_uses_existing_keyring_trust_and_rotation_rules(self):
        import json
        import os
        from unittest.mock import patch
        from layer1.onchain import OnChainIntelligenceEngine

        key, page_id, _, original_engine = self._commit_signable_page()
        original_engine.sign_ingestion_page(self.store, key, page_id)
        old_key = b"test-only-onchain-ingestion-page-key-32-bytes"
        new_key = b"test-only-next-onchain-ingestion-page-key-32-bytes"
        rotated_env = {
            "ONCHAIN_RECEIPT_HMAC_KEYRING_JSON": json.dumps({
                "ingestion-test-v1": old_key.hex(), "current-v2": new_key.hex(),
            }),
            "ONCHAIN_RECEIPT_ACTIVE_KEY_ID": "current-v2",
            "ONCHAIN_RECEIPT_TRUSTED_KEY_IDS": "ingestion-test-v1,current-v2",
        }
        with patch.dict(os.environ, rotated_env, clear=False):
            rotated = OnChainIntelligenceEngine.from_env()
            self.assertTrue(rotated.verify_ingestion_page_acceptance(self.store, key, page_id))
        revoked_env = {
            "ONCHAIN_RECEIPT_HMAC_KEYRING_JSON": json.dumps({"current-v2": new_key.hex()}),
            "ONCHAIN_RECEIPT_ACTIVE_KEY_ID": "current-v2",
            "ONCHAIN_RECEIPT_TRUSTED_KEY_IDS": "current-v2",
        }
        with patch.dict(os.environ, revoked_env, clear=False):
            revoked = OnChainIntelligenceEngine.from_env()
            self.assertFalse(revoked.verify_ingestion_page_acceptance(self.store, key, page_id))

    def test_pending_page_acceptance_recovery_signs_durable_pages_idempotently(self):
        key, page_id, _, engine = self._commit_signable_page()
        result = engine.sign_pending_ingestion_pages(self.store)
        self.assertEqual(result, {"signed": 1, "pending": 0, "rejected": 0})
        self.assertTrue(engine.verify_ingestion_page_acceptance(self.store, key, page_id))
        self.assertEqual(
            engine.sign_pending_ingestion_pages(self.store),
            {"signed": 0, "pending": 0, "rejected": 0},
        )

    def test_pending_page_recovery_isolates_malformed_receipt_and_signs_later_valid_page(self):
        import json
        key, malformed_page_id, event, engine = self._commit_signable_page()
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
        )
        block = {
            "network_id": event.network_id, "provider": event.provider,
            "scope": event.scope, "block_number": event.block_number,
            "block_hash": event.block_hash, "block_time": event.block_time,
        }
        self.store.commit_page(
            key, {"next_block": 102}, [event], expected_cursor={"next_block": 101},
            scope_identity=(event.network_id, event.provider, event.scope),
            canonical_blocks=(block,), provider_receipts=captured_batch(receipt),
        )
        valid_page_id = self.store.conn.execute(
            "SELECT page_id FROM layer1_onchain_ingestion_pages WHERE cursor_key=? AND page_id<>?",
            (key, malformed_page_id),
        ).fetchone()[0]
        malformed_json = self.store._canonical([None])
        malformed_digest = hashlib.sha256(malformed_json.encode("utf-8")).hexdigest()
        self.store.conn.execute(
            "UPDATE layer1_onchain_ingestion_pages SET receipts_json=?, receipt_sha256=? WHERE page_id=?",
            (malformed_json, malformed_digest, malformed_page_id),
        )
        self.store.conn.commit()

        result = engine.sign_pending_ingestion_pages(self.store)

        self.assertEqual(result, {"signed": 1, "pending": 1, "rejected": 1})
        self.assertIsNone(self.store.get_page_acceptance(key, malformed_page_id))
        self.assertIsNotNone(self.store.get_page_acceptance(key, valid_page_id))
        self.assertTrue(engine.verify_ingestion_page_acceptance(self.store, key, valid_page_id))

    def test_pending_page_recovery_isolates_invalid_json_receipt_payload(self):
        key, page_id, _, engine = self._commit_signable_page()
        malformed_json = "{"  # Deliberately invalid persisted JSON.
        malformed_digest = hashlib.sha256(malformed_json.encode("utf-8")).hexdigest()
        self.store.conn.execute(
            "UPDATE layer1_onchain_ingestion_pages SET receipts_json=?, receipt_sha256=? WHERE page_id=?",
            (malformed_json, malformed_digest, page_id),
        )
        self.store.conn.commit()

        result = engine.sign_pending_ingestion_pages(self.store)

        self.assertEqual(result, {"signed": 0, "pending": 1, "rejected": 1})
        self.assertIsNone(self.store.get_page_acceptance(key, page_id))

    def test_pending_page_recovery_rejects_receipt_object_missing_required_fields(self):
        key, page_id, _, engine = self._commit_signable_page()
        malformed_json = self.store._canonical([{}])
        malformed_digest = hashlib.sha256(malformed_json.encode("utf-8")).hexdigest()
        self.store.conn.execute(
            "UPDATE layer1_onchain_ingestion_pages SET receipts_json=?, receipt_sha256=? WHERE page_id=?",
            (malformed_json, malformed_digest, page_id),
        )
        self.store.conn.commit()

        result = engine.sign_pending_ingestion_pages(self.store)

        self.assertEqual(result, {"signed": 0, "pending": 1, "rejected": 1})
        self.assertIsNone(self.store.get_page_acceptance(key, page_id))

    def test_pending_page_acceptance_recovery_refuses_stale_canonical_event(self):
        key, page_id, event, engine = self._commit_signable_page()
        tampered = NormalizedTransferEvent(**{**event.__dict__, "amount_raw": "999"})
        self.store.conn.execute(
            "UPDATE layer1_onchain_transfer_events SET payload_json=? WHERE event_id=?",
            (self.store._canonical(tampered.__dict__), event.event_id),
        )
        result = engine.sign_pending_ingestion_pages(self.store)
        self.assertEqual(result, {"signed": 0, "pending": 1, "rejected": 1})
        self.assertFalse(engine.verify_ingestion_page_acceptance(self.store, key, page_id))

    def test_pending_page_acceptance_recovery_leaves_unsigned_pages_pending_without_key(self):
        _, _, _, _ = self._commit_signable_page()
        from layer1.onchain import OnChainIntelligenceEngine
        result = OnChainIntelligenceEngine().sign_pending_ingestion_pages(self.store)
        self.assertEqual(result, {"signed": 0, "pending": 1, "rejected": 0})

    def test_ingestion_page_signing_without_active_key_fails_closed(self):
        from layer1.onchain import OnChainIntelligenceEngine
        key, page_id, _, _ = self._commit_signable_page()
        unsigned = OnChainIntelligenceEngine()
        with self.assertRaisesRegex(ValueError, "signing is not configured"):
            unsigned.sign_ingestion_page(self.store, key, page_id)

    def test_ingestion_page_signer_does_not_accept_caller_supplied_observation_payload(self):
        key, page_id, _, engine = self._commit_signable_page()
        with self.assertRaises(TypeError):
            engine.sign_ingestion_page(self.store, key, page_id, observation={"forged": True})

    def test_page_acceptance_rejects_persisted_receipt_with_recomputed_unapproved_endpoint_fingerprint(self):
        key = "alchemy:bnb-smart-chain:contract-1"
        identity = ("bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40)
        block = {
            "network_id": identity[0], "provider": identity[1], "scope": identity[2],
            "block_number": 100, "block_hash": self.event().block_hash,
            "block_time": self.event().block_time,
        }
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id=identity[0],
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
        )
        self.store.commit_page(
            key, {"next_block": 101}, [self.event()], expected_cursor=None,
            scope_identity=identity, canonical_blocks=(block,),
            provider_receipts=captured_batch(receipt),
        )
        page_id = self.store.list_ingestion_pages()[0][1]
        tampered = [{**receipt.__dict__, "endpoint_profile_sha256": "f" * 64}]
        tampered_json = self.store._canonical(tampered)
        tampered_digest = hashlib.sha256(tampered_json.encode("utf-8")).hexdigest()
        self.store.conn.execute(
            "UPDATE layer1_onchain_ingestion_pages SET receipts_json=?, receipt_sha256=? WHERE page_id=?",
            (tampered_json, tampered_digest, page_id),
        )
        with self.assertRaisesRegex(ValueError, "approved provider/network endpoint profile"):
            self.store.get_page_acceptance_material(key, page_id)

    def test_provider_receipts_reject_malformed_or_wrong_scope_receipts(self):
        key = "alchemy:bnb-smart-chain:contract-1"
        identity = ("bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40)
        wrong_scope = ProviderResponseReceipt(
            sequence=1, provider="other", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
        )
        with self.assertRaisesRegex(ValueError, "receipt identity"):
            self.store.commit_page(
                key, {"next_block": 101}, [self.event()], expected_cursor=None,
                scope_identity=identity, provider_receipts=captured_batch(wrong_scope),
            )
        self.assertIsNone(self.store.get_checkpoint(key))

    def test_page_commit_requires_explicit_expected_checkpoint_snapshot(self):
        with self.assertRaisesRegex(ValueError, "expected_cursor"):
            self.store.commit_page("required-checkpoint", {"next_block": 101}, ())
        self.assertIsNone(self.store.get_checkpoint("required-checkpoint"))

    def test_replaying_old_page_with_its_stale_checkpoint_cannot_rewind_cursor(self):
        key = "monotonic-checkpoint"
        event = self.event()
        self.store.commit_page(key, {"next_block": 101}, [event], expected_cursor=None)
        self.store.commit_page(key, {"next_block": 102}, [], expected_cursor={"next_block": 101})
        with self.assertRaisesRegex(RuntimeError, "checkpoint changed"):
            self.store.commit_page(key, {"next_block": 101}, [event], expected_cursor=None)
        self.assertEqual(self.store.get_checkpoint(key), {"next_block": 102})

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
        self.store.commit_page(key, {"next_block": 101}, (), canonical_blocks=(first,), expected_cursor=self.store.get_checkpoint(key))
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
        self.store.commit_page(key, {"next_block": 101}, (), canonical_blocks=(block,), expected_cursor=self.store.get_checkpoint(key))
        changed_time = {**block, "block_time": "2026-11-11T12:01:00+00:00"}
        with self.assertRaisesRegex(ValueError, "timestamp conflict"):
            self.store.commit_page(key, {"next_block": 102}, (),
                                   expected_cursor={"next_block": 101},
                                   canonical_blocks=(changed_time,))
        self.assertEqual(self.store.get_checkpoint(key), {"next_block": 101})

    def test_replayed_page_is_idempotent_and_conflicting_event_identity_is_rejected(self):
        key = "alchemy:bnb-smart-chain-mainnet:contract-1"
        self.store.commit_page(key, {"next": "x"}, [self.event()], expected_cursor=self.store.get_checkpoint(key))
        result = self.store.commit_page(key, {"next": "x"}, [self.event()], expected_cursor=self.store.get_checkpoint(key))
        self.assertEqual(result["duplicates"], 1)
        changed = self.event()
        changed = NormalizedTransferEvent(**{**changed.__dict__, "amount_raw": "999"})
        with self.assertRaisesRegex(ValueError, "identity collision"):
            self.store.commit_page(key, {"next": "y"}, [changed], expected_cursor=self.store.get_checkpoint(key))
        self.assertEqual(self.store.get_checkpoint(key), {"next": "x"})

    def test_replayed_canonical_event_can_only_transition_monotonically_to_reorged(self):
        canonical = self.event(status="CANONICAL")
        self.store.commit_page("cursor", {"next": 1}, [canonical], expected_cursor=self.store.get_checkpoint("cursor"))
        tombstone = NormalizedTransferEvent(**{**canonical.__dict__, "canonical_status": "REORGED"})
        result = self.store.commit_page("cursor", {"next": 2}, [tombstone], expected_cursor=self.store.get_checkpoint("cursor"))
        self.assertEqual(result["tombstoned"], 1)
        self.assertEqual(self.store.get_event(canonical.event_id, canonical.network_id).canonical_status, "REORGED")
        self.assertEqual(self.store.list_events(canonical.network_id, canonical_only=True), [])
        # A later stale canonical page must not resurrect a tombstoned event.
        self.store.commit_page("cursor", {"next": 3}, [canonical], expected_cursor=self.store.get_checkpoint("cursor"))
        self.assertEqual(self.store.get_event(canonical.event_id, canonical.network_id).canonical_status, "REORGED")

    def test_removed_log_is_persisted_as_reorg_tombstone_not_active_transfer(self):
        removed = self.event(status="REORGED")
        self.store.commit_page("cursor", {"next": None}, [removed], expected_cursor=self.store.get_checkpoint("cursor"))
        saved = self.store.get_event(removed.event_id, removed.network_id)
        self.assertEqual(saved.canonical_status, "REORGED")
        self.assertEqual(self.store.list_events(removed.network_id, canonical_only=True), [])

    def test_canonical_block_reconciliation_marks_orphaned_events_reorged(self):
        event = self.event()
        self.store.commit_page("cursor", {"next": None}, [event], expected_cursor=self.store.get_checkpoint("cursor"))
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
        self.store.commit_page(key, {"next": "old"}, [first], expected_cursor=self.store.get_checkpoint(key))
        conflict = NormalizedTransferEvent(**{**first.__dict__, "amount_raw": "999"})
        second = self.event(event_id="second")
        with self.assertRaisesRegex(ValueError, "identity collision"):
            self.store.commit_page(key, {"next": "new"}, [second, conflict], expected_cursor=self.store.get_checkpoint(key))
        self.assertEqual(self.store.get_checkpoint(key), {"next": "old"})
        self.assertIsNone(self.store.get_event("second", "bnb-smart-chain-mainnet"))

    def test_invalid_amount_and_noncanonical_cursor_json_are_rejected(self):
        event = self.event()
        invalid = NormalizedTransferEvent(**{**event.__dict__, "amount_raw": "1.5"})
        with self.assertRaises(ValueError):
            self.store.commit_page("cursor", {"next": float("nan")}, [event], expected_cursor=self.store.get_checkpoint("cursor"))
        with self.assertRaises(ValueError):
            self.store.commit_page("cursor", {"next": None}, [invalid], expected_cursor=self.store.get_checkpoint("cursor"))



    def test_reorg_invalidates_signed_page_without_mutating_historical_signature(self):
        from layer1.onchain import OnChainIntelligenceEngine
        key, page_id, event, engine = self._commit_signable_page()
        envelope = engine.sign_ingestion_page(self.store, key, page_id)

        self.store.reconcile_block(
            event.network_id, event.block_number, "0x" + "c" * 64,
            provider=event.provider, scope=event.scope,
        )

        self.assertEqual(self.store.get_page_acceptance(key, page_id), {
            "cursor_key": envelope.cursor_key, "key_id": envelope.key_id,
            "payload_sha256": envelope.payload_sha256,
            "payload_json": self.store.get_page_acceptance(key, page_id)["payload_json"],
            "signature": envelope.signature,
        })
        self.assertFalse(engine.verify_ingestion_page_acceptance(self.store, key, page_id))
        queue = self.store.list_invalidated_page_acceptances()
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["page_id"], page_id)
        self.assertEqual(queue[0]["status"], "INVALIDATED")
        self.assertEqual(queue[0]["reason_code"], "CANONICAL_EVIDENCE_REORGED")
        self.assertEqual(queue[0]["payload_json"]["page_id"], page_id)
        self.assertTrue(queue[0]["accepted_at"])
        self.assertEqual(queue[0]["affected_evidence"][0]["canonical_block_hash"], event.block_hash)
        self.assertEqual(queue[0]["affected_evidence"][0]["current_canonical_hash"], "0x" + "c" * 64)

    def test_reorg_and_acceptance_invalidation_roll_back_atomically(self):
        from unittest.mock import patch
        key, page_id, event, engine = self._commit_signable_page()
        engine.sign_ingestion_page(self.store, key, page_id)
        with patch.object(self.store, "_invalidate_page_acceptances_for_reorg",
                          side_effect=RuntimeError("invalidation persistence failed")):
            with self.assertRaisesRegex(RuntimeError, "invalidation persistence failed"):
                self.store.reconcile_block(
                    event.network_id, event.block_number, "0x" + "c" * 64,
                    provider=event.provider, scope=event.scope,
                )
        self.assertEqual(
            self.store.get_event(event.event_id, event.network_id, event.provider, event.scope).canonical_status,
            "CANONICAL",
        )
        self.assertEqual(self.store.list_invalidated_page_acceptances(), ())
        self.assertTrue(engine.verify_ingestion_page_acceptance(self.store, key, page_id))

    def test_recanonicalized_block_only_page_invalidates_prior_signed_acceptance(self):
        from layer1.onchain import OnChainIntelligenceEngine
        key = "alchemy:bnb-smart-chain:block-only-reorg"
        identity = ("bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40)
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id=identity[0],
            method="eth_getBlockByNumber", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
        )
        first_block = {"network_id": identity[0], "provider": identity[1], "scope": identity[2],
                       "block_number": 100, "block_hash": "b" * 64,
                       "block_time": "2026-11-11T12:00:00+00:00"}
        self.store.commit_page(
            key, {"next_block": 101}, (), expected_cursor=None, scope_identity=identity,
            canonical_blocks=(first_block,), provider_receipts=captured_batch(receipt),
        )
        page_id = self.store.conn.execute(
            "SELECT page_id FROM layer1_onchain_ingestion_pages WHERE cursor_key=?", (key,),
        ).fetchone()[0]
        engine = OnChainIntelligenceEngine(
            receipt_signing_key=b"test-only-onchain-ingestion-page-key-32-bytes",
            receipt_key_id="ingestion-test-v1",
        )
        original = engine.sign_ingestion_page(self.store, key, page_id)
        second_block = {**first_block, "block_hash": "c" * 64}
        self.store.commit_page(
            key, {"next_block": 101}, (), expected_cursor={"next_block": 101},
            scope_identity=identity, canonical_blocks=(second_block,),
            provider_receipts=captured_batch(receipt), allow_recanonicalized=True,
        )
        invalidated = self.store.list_invalidated_page_acceptances()
        self.assertEqual([item["page_id"] for item in invalidated], [page_id])
        self.assertEqual(invalidated[0]["affected_evidence"][0]["canonical_block_hash"], "b" * 64)
        self.assertEqual(invalidated[0]["affected_evidence"][0]["current_canonical_hash"], "c" * 64)
        self.assertEqual(self.store.get_page_acceptance(key, page_id)["signature"], original.signature)
        self.assertFalse(engine.verify_ingestion_page_acceptance(self.store, key, page_id))

    def test_recanonicalized_solana_slot_only_page_invalidates_prior_signed_acceptance(self):
        from layer1.onchain import OnChainIntelligenceEngine
        key = "alchemy:solana:slot-only-reorg"
        identity = ("solana-mainnet", "alchemy", "program:11111111111111111111111111111111")
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id=identity[0],
            method="getBlock", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256=_approved_endpoint_profile_sha256("alchemy", identity[0]),
        )
        first_slot = {"network_id": identity[0], "provider": identity[1], "scope": identity[2],
                      "slot": 100, "produced": True, "block_hash": "b" * 64,
                      "block_time": "2026-11-11T12:00:00+00:00"}
        self.store.commit_page(
            key, {"next_slot": 101}, (), expected_cursor=None, scope_identity=identity,
            canonical_slots=(first_slot,), provider_receipts=captured_batch(receipt),
        )
        page_id = self.store.conn.execute(
            "SELECT page_id FROM layer1_onchain_ingestion_pages WHERE cursor_key=?", (key,),
        ).fetchone()[0]
        engine = OnChainIntelligenceEngine(
            receipt_signing_key=b"test-only-onchain-ingestion-page-key-32-bytes",
            receipt_key_id="ingestion-test-v1",
        )
        original = engine.sign_ingestion_page(self.store, key, page_id)
        second_slot = {**first_slot, "block_hash": "c" * 64}
        self.store.commit_page(
            key, {"next_slot": 101}, (), expected_cursor={"next_slot": 101},
            scope_identity=identity, canonical_slots=(second_slot,),
            provider_receipts=captured_batch(receipt), allow_recanonicalized=True,
        )
        invalidated = self.store.list_invalidated_page_acceptances()
        self.assertEqual([item["page_id"] for item in invalidated], [page_id])
        self.assertEqual(invalidated[0]["affected_evidence"][0]["kind"], "CANONICAL_SLOT")
        self.assertEqual(invalidated[0]["affected_evidence"][0]["canonical_block_hash"], "b" * 64)
        self.assertEqual(invalidated[0]["affected_evidence"][0]["current_canonical_hash"], "c" * 64)
        self.assertEqual(self.store.get_page_acceptance(key, page_id)["signature"], original.signature)
        self.assertFalse(engine.verify_ingestion_page_acceptance(self.store, key, page_id))

    def test_unscoped_reorg_reconciliation_invalidates_every_matching_signed_scope(self):
        from layer1.onchain import OnChainIntelligenceEngine
        engine = OnChainIntelligenceEngine(
            receipt_signing_key=b"test-only-onchain-ingestion-page-key-32-bytes",
            receipt_key_id="ingestion-test-v1",
        )
        page_ids = []
        for suffix in ("one", "two"):
            scope = f"contract:{suffix}"
            event = NormalizedTransferEvent(**{**self.event().__dict__, "scope": scope})
            identity = (event.network_id, event.provider, event.scope)
            block = {"network_id": event.network_id, "provider": event.provider,
                     "scope": event.scope, "block_number": event.block_number,
                     "block_hash": event.block_hash, "block_time": event.block_time}
            receipt = ProviderResponseReceipt(
                sequence=1, provider="alchemy", network_id=event.network_id,
                method="eth_getLogs", request_sha256="a" * 64,
                response_sha256="b" * 64, response_bytes=128, http_status=200,
                received_at="2026-11-26T12:00:00+00:00",
                endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
            )
            key = f"alchemy:bnb-smart-chain:unscoped-reorg-{suffix}"
            self.store.commit_page(
                key, {"next_block": 101}, [event], expected_cursor=None,
                scope_identity=identity, canonical_blocks=(block,),
                provider_receipts=captured_batch(receipt),
            )
            page_id = self.store.conn.execute(
                "SELECT page_id FROM layer1_onchain_ingestion_pages WHERE cursor_key=?", (key,),
            ).fetchone()[0]
            engine.sign_ingestion_page(self.store, key, page_id)
            page_ids.append(page_id)

        self.store.reconcile_block(self.event().network_id, 100, "0x" + "c" * 64)

        invalidated_ids = {item["page_id"] for item in self.store.list_invalidated_page_acceptances()}
        self.assertEqual(invalidated_ids, set(page_ids))

    def test_recanonicalized_block_commit_rolls_back_journal_and_checkpoint_if_invalidation_fails(self):
        from unittest.mock import patch
        key = "alchemy:bnb-smart-chain:block-only-rollback"
        identity = ("bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40)
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id=identity[0],
            method="eth_getBlockByNumber", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
        )
        old = {"network_id": identity[0], "provider": identity[1], "scope": identity[2],
               "block_number": 100, "block_hash": "b" * 64,
               "block_time": "2026-11-11T12:00:00+00:00"}
        self.store.commit_page(key, {"next_block": 101}, (), expected_cursor=None,
                               scope_identity=identity, canonical_blocks=(old,),
                               provider_receipts=captured_batch(receipt))
        with patch.object(self.store, "_invalidate_page_acceptances_for_reorg",
                          side_effect=RuntimeError("lifecycle write failed")):
            with self.assertRaisesRegex(RuntimeError, "lifecycle write failed"):
                self.store.commit_page(
                    key, {"next_block": 102}, (), expected_cursor={"next_block": 101},
                    scope_identity=identity, canonical_blocks=({**old, "block_hash": "c" * 64},),
                    provider_receipts=captured_batch(receipt), allow_recanonicalized=True,
                )
        self.assertEqual(self.store.get_block_hash(*identity, 100), "b" * 64)
        self.assertEqual(self.store.get_checkpoint(key), {"next_block": 101})

    def test_reorg_invalidation_is_idempotent_and_does_not_invalidate_unrelated_pages(self):
        from layer1.onchain import OnChainIntelligenceEngine
        key, page_id, event, engine = self._commit_signable_page()
        engine.sign_ingestion_page(self.store, key, page_id)
        self.store.reconcile_block(
            event.network_id, event.block_number, "0x" + "c" * 64,
            provider=event.provider, scope=event.scope,
        )
        first = self.store.list_invalidated_page_acceptances()
        self.store.reconcile_block(
            event.network_id, event.block_number, "0x" + "d" * 64,
            provider=event.provider, scope=event.scope,
        )
        second = self.store.list_invalidated_page_acceptances()
        self.assertEqual(len(first), 1)
        self.assertEqual(second, first)


class BitcoinOutputNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.txid = "a" * 64
        self.monitored = "1BoatSLRHtKNngkdXEeobR76b53LETtpyT"
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
                              {"next_block": 900001}, events, expected_cursor=store.get_checkpoint("alchemy:bitcoin-mainnet:address:" + self.monitored))
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

    def test_rejects_invalid_input_address_checksum(self):
        details = self.transaction()
        details["vin"][0]["addresses"] = ["1BoatSLRHtKNngkdXEeobR76b53LETtpyU"]
        with self.assertRaisesRegex(ValueError, "checksum-valid Bitcoin mainnet address"):
            self.normalize(transaction=details)

    def test_rejects_invalid_output_address_checksum(self):
        details = self.transaction()
        details["vout"][0]["addresses"] = ["1BoatSLRHtKNngkdXEeobR76b53LETtpyU"]
        with self.assertRaisesRegex(ValueError, "checksum-valid Bitcoin mainnet address"):
            self.normalize(transaction=details)

    def test_rejects_details_that_do_not_contain_the_monitored_address(self):
        details = self.transaction()
        details["vin"][0]["addresses"] = [self.source_two]
        details["vin"][1]["addresses"] = [self.source_two]
        details["vout"][0]["addresses"] = [self.source_two]
        details["vout"][1]["addresses"] = [self.source_two]
        with self.assertRaisesRegex(ValueError, "does not contain the monitored address"):
            self.normalize(transaction=details)

    def test_marks_event_reorged_when_independently_fetched_canonical_hash_differs(self):
        events = self.normalize(canonical_hash="e" * 64)
        self.assertTrue(all(event.canonical_status == "REORGED" for event in events))

    def test_requires_explicit_minimum_confirmation_threshold(self):
        with self.assertRaisesRegex(ValueError, "confirmation threshold"):
            self.normalize(history=self.history(confirmations=5))

    def test_rejects_boolean_or_float_block_height_in_transaction_details(self):
        from dataclasses import replace
        source = replace(self.history(), block_height=1, block_time=1)
        for value in (True, 1.0):
            with self.subTest(value=value):
                details = self.transaction()
                details["blockHeight"] = value
                details["blockTime"] = 1
                with self.assertRaisesRegex(ValueError, "transaction identity or block reference"):
                    self.normalize(history=source, transaction=details)

    def test_rejects_boolean_or_float_block_time_in_transaction_details(self):
        from dataclasses import replace
        source = replace(self.history(), block_height=1, block_time=1)
        for value in (True, 1.0):
            with self.subTest(value=value):
                details = self.transaction()
                details["blockHeight"] = 1
                details["blockTime"] = value
                with self.assertRaisesRegex(ValueError, "transaction identity or block reference"):
                    self.normalize(history=source, transaction=details)

    def test_rejects_raw_address_history_txid_that_diverges_from_typed_record(self):
        history = self.history()
        history.raw["txid"] = "f" * 64
        with self.assertRaises(ValueError):
            self.normalize(history=history)

    def test_rejects_raw_numeric_history_fields_using_boolean_integer_aliases(self):
        history = self.history(confirmations=8)
        raw = dict(history.raw, blockHeight=True)
        history = BitcoinAddressTransaction(
            history.txid, 8, 1, history.block_hash, history.block_time, "CONFIRMED", raw,
        )
        transaction = self.transaction()
        transaction.update({"blockHeight": 1, "confirmations": 8})
        with self.assertRaises(ValueError):
            self.normalize(history=history, transaction=transaction)

    def test_rejects_transaction_identity_or_block_reference_mismatch(self):
        details = self.transaction()
        details["txid"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "transaction identity"):
            self.normalize(transaction=details)

    def test_rejects_bitcoin_output_above_consensus_maximum_money(self):
        details = self.transaction()
        details["vout"][0]["value"] = "2100000000000001"
        with self.assertRaisesRegex(ValueError, "Bitcoin output value exceeds maximum money"):
            self.normalize(transaction=details)

    def test_rejects_total_bitcoin_outputs_above_consensus_maximum_money(self):
        details = self.transaction()
        details["vout"] = [
            {"n": 0, "value": "1200000000000000", "addresses": [self.destination_one], "isAddress": True},
            {"n": 1, "value": "900000000000001", "addresses": [self.destination_two], "isAddress": True},
        ]
        with self.assertRaisesRegex(ValueError, "Bitcoin transaction output total exceeds maximum money"):
            self.normalize(transaction=details)

    def test_rejects_bitcoin_output_index_above_uint32(self):
        details = self.transaction()
        details["vout"][0]["n"] = 4294967296
        with self.assertRaisesRegex(ValueError, "output index"):
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
