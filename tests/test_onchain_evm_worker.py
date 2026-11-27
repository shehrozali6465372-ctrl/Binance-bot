import os
import tempfile
import unittest
from datetime import datetime, timezone
from layer1.foundation import EligibilityDecision
from layer1.onchain import OnChainAssetMapping, OnChainIntelligenceEngine
from tests.onchain_test_support import MappingStoreStub
from layer1.onchain_ingestion import OnChainIngestionStore
from layer1.onchain_providers import EvmTokenTransferLog, ProviderDataPage, ProviderTransportError
from layer1.onchain_evm_worker import EvmTransferIngestionWorker


CONTRACT = "0x" + "1" * 40
BLOCK_HASH = "0x" + "b" * 64
TX_HASH = "0x" + "a" * 64


def mapping(mapping_id="asset-bnb-v1", contract=CONTRACT, status="VERIFIED",
            network_id="bnb-smart-chain-mainnet", chain_id="56"):
    return OnChainAssetMapping(
        mapping_id=mapping_id, asset_id="coingecko:example", binance_symbol="EXAMPLE",
        network_id=network_id, network_family="EVM", chain_id=chain_id,
        representation="TOKEN", contract_address=contract, token_standard="ERC-20",
        decimals=18, mapping_status=status, source_type="OFFICIAL_PROJECT",
        source_url="https://example.org/token", verified_at="2026-11-11T12:00:00+00:00",
    )


class FakeProvider:
    def __init__(self):
        self.finalized_height = 109
        self.logs = []
        self.headers = {}
        self.fail_header_once = False
        self.log_calls = []

    def fetch_bnb_finalized_height(self):
        return self.finalized_height

    def fetch_bnb_erc20_transfer_logs(self, contract_address, from_block, to_block):
        self.log_calls.append((contract_address, from_block, to_block))
        return ProviderDataPage(
            "alchemy", "bnb-smart-chain-mainnet", contract_address,
            tuple(item for item in self.logs if from_block <= item.block_number <= to_block
                  and item.contract_address.lower() == contract_address.lower()),
            from_block=from_block, to_block=to_block, finalized_height=self.finalized_height,
            finality_reference="eth_getFinalizedHeader:verifiedValidatorNum=-3",
        )

    def fetch_bnb_block_header(self, block_number):
        if self.fail_header_once:
            self.fail_header_once = False
            raise ProviderTransportError("TIMEOUT", "provider request timed out")
        if block_number in self.headers:
            return self.headers[block_number]
        records = [item for item in self.logs if item.block_number == block_number]
        previous = self.headers.get(block_number - 1)
        parent_hash = previous["hash"] if previous is not None else BLOCK_HASH
        by_index = {item.transaction_index: item.transaction_hash.lower() for item in records}
        transaction_hashes = tuple(by_index[index] for index in range(max(by_index, default=-1) + 1))
        return {
            "number": block_number, "hash": BLOCK_HASH, "parent_hash": parent_hash,
            "timestamp": 1794398400 + block_number,
            "transaction_hashes": transaction_hashes,
        }


class EvmTransferIngestionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self.tmp.name, "onchain.sqlite3")
        engine = OnChainIntelligenceEngine(
            {"bnb-smart-chain-mainnet": 86400},
            receipt_signing_key=b"test-only-onchain-receipt-key-32-bytes-minimum",
            receipt_key_id="test-key-v1")
        self.ingestion_store = OnChainIngestionStore(path)
        verified_mapping = mapping()
        self.mapping_store = MappingStoreStub(engine, verified_mapping)
        self.provider = FakeProvider()
        self.provider.logs = [EvmTokenTransferLog(
            network_id="bnb-smart-chain-mainnet", contract_address=CONTRACT,
            from_address="0x" + "2" * 40, to_address="0x" + "3" * 40,
            amount_raw="12345678901234567890", block_number=109, block_hash=BLOCK_HASH,
            transaction_hash=TX_HASH, log_index=4, removed=False,
        )]
        self.worker = EvmTransferIngestionWorker(
            self.provider, self.mapping_store, self.ingestion_store,
            start_blocks={mapping().mapping_id: 100},
            max_blocks_per_run=10, reorg_lookback_blocks=2,
            retry_attempts=2, sleep=lambda _: None,
            clock=lambda: datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc),
        )

    def tearDown(self):
        self.ingestion_store.close()
        self.mapping_store.close()
        self.tmp.cleanup()

    def test_worker_rejects_invalid_mapping_decimals_before_ingestion(self):
        from dataclasses import replace
        for decimals in (True, -1, 37, "18"):
            with self.subTest(decimals=decimals):
                with self.assertRaises(ValueError):
                    self.worker._validate_mapping(replace(mapping(), decimals=decimals))

    def test_worker_rejects_non_erc20_mapping_standard(self):
        unsupported = mapping()
        unsupported = OnChainAssetMapping(**{
            **unsupported.__dict__, "token_standard": "ERC721",
        })
        with self.assertRaises(ValueError):
            self.worker._validate_mapping(unsupported)

    def test_rejects_erc20_amount_above_uint256_before_persistence(self):
        from dataclasses import replace
        self.provider.logs = [replace(
            self.provider.logs[0], amount_raw=str(1 << 256),
        )]

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT))
        self.assertEqual(self.ingestion_store.list_events("bnb-smart-chain-mainnet"), [])

    def test_rejects_malformed_transfer_address_at_worker_provider_boundary(self):
        from dataclasses import replace
        self.provider.logs = [replace(self.provider.logs[0], from_address=None)]

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT))
        self.assertEqual(self.ingestion_store.list_events("bnb-smart-chain-mainnet"), [])

    def test_rejects_boolean_log_index_at_worker_provider_boundary(self):
        from dataclasses import replace
        self.provider.logs = [replace(self.provider.logs[0], log_index=True)]

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT))
        self.assertEqual(self.ingestion_store.list_events("bnb-smart-chain-mainnet"), [])

    def test_ingests_only_verified_mapped_contract_logs_and_commits_bounded_checkpoint(self):
        result = self.worker.run_once()
        self.assertEqual(result["events_inserted"], 1)
        saved = self.ingestion_store.list_events("bnb-smart-chain-mainnet", canonical_only=True)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].event_id, TX_HASH + ":4")
        self.assertEqual(saved[0].amount_raw, "12345678901234567890")
        self.assertEqual(saved[0].finality_snapshot.status, "FINALIZED")
        self.assertEqual(saved[0].finality_snapshot.reference,
                         "eth_getFinalizedHeader:verifiedValidatorNum=-3")
        checkpoint = self.ingestion_store.get_checkpoint(
            "alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT
        )
        self.assertEqual(checkpoint["next_block"], 110)
        self.assertEqual(checkpoint["finality_reference"],
                         "eth_getFinalizedHeader:verifiedValidatorNum=-3")
        self.assertEqual(checkpoint["finalized_height"], self.provider.finalized_height)
        self.assertEqual(self.provider.log_calls, [(CONTRACT, 100, 109)])

    def test_rejects_block_timestamp_outside_datetime_storage_range_before_checkpoint(self):
        self.provider.headers[109] = {
            "number": 109, "hash": BLOCK_HASH, "parent_hash": BLOCK_HASH,
            "timestamp": 253402300800, "transaction_hashes": (TX_HASH,),
        }

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT))
        self.assertEqual(self.ingestion_store.list_events("bnb-smart-chain-mainnet"), [])

    def test_ethereum_requires_strictly_increasing_parent_timestamp(self):
        from layer1.onchain import OnChainIntelligenceEngine
        from tests.onchain_test_support import MappingStoreStub

        eth_mapping = mapping(network_id="ethereum-mainnet", chain_id="1")
        engine = OnChainIntelligenceEngine(
            {"ethereum-mainnet": 86400},
            receipt_signing_key=b"test-only-onchain-receipt-key-32-bytes-minimum",
            receipt_key_id="test-key-v1")
        mapping_store = MappingStoreStub(engine, eth_mapping)
        provider = FakeProvider()
        provider.logs = [EvmTokenTransferLog(
            network_id="ethereum-mainnet", contract_address=CONTRACT,
            from_address="0x" + "2" * 40, to_address="0x" + "3" * 40,
            amount_raw="9", block_number=109, block_hash=BLOCK_HASH,
            transaction_hash=TX_HASH, log_index=4, removed=False,
        )]
        provider.fetch_ethereum_finalized_height = provider.fetch_bnb_finalized_height
        def fetch_eth_logs(contract_address, from_block, to_block):
            return ProviderDataPage(
                "alchemy", "ethereum-mainnet", contract_address,
                tuple(item for item in provider.logs if from_block <= item.block_number <= to_block),
                from_block=from_block, to_block=to_block,
                finalized_height=provider.finalized_height,
                finality_reference="eth_getBlockByNumber:finalized",
            )
        provider.fetch_ethereum_erc20_transfer_logs = fetch_eth_logs
        provider.fetch_ethereum_block_header = provider.fetch_bnb_block_header
        provider.headers[108] = {
            "number": 108, "hash": BLOCK_HASH, "parent_hash": BLOCK_HASH,
            "timestamp": 1794398508, "transaction_hashes": (),
        }
        provider.headers[109] = {
            "number": 109, "hash": BLOCK_HASH, "parent_hash": BLOCK_HASH,
            "timestamp": 1794398508, "transaction_hashes": (TX_HASH,),
        }
        worker = EvmTransferIngestionWorker(
            provider, mapping_store, self.ingestion_store,
            start_blocks={eth_mapping.mapping_id: 100}, max_blocks_per_run=10,
            reorg_lookback_blocks=2, retry_attempts=2, sleep=lambda _: None,
            clock=lambda: datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc),
        )

        with self.assertRaises(ProviderTransportError) as error:
            worker.run_once()

        self.assertEqual(error.exception.reason_code, "EVM_BLOCK_TIMESTAMP_NOT_MONOTONIC")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:ethereum-mainnet:contract:" + CONTRACT))

    def test_accepts_equal_bnb_second_timestamps_when_millisecond_precision_is_not_exposed(self):
        self.provider.headers[108] = {
            "number": 108, "hash": BLOCK_HASH, "parent_hash": BLOCK_HASH,
            "timestamp": 1794398508, "transaction_hashes": (),
        }
        self.provider.headers[109] = {
            "number": 109, "hash": BLOCK_HASH, "parent_hash": BLOCK_HASH,
            "timestamp": 1794398508, "transaction_hashes": (TX_HASH,),
        }

        result = self.worker.run_once()

        self.assertEqual(result["events_inserted"], 1)
        self.assertEqual(self.ingestion_store.get_checkpoint(
            "alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT)["next_block"], 110)

    def test_rejects_non_monotonic_evm_header_timestamps_before_page_commit(self):
        self.provider.headers[108] = {
            "number": 108, "hash": BLOCK_HASH, "parent_hash": BLOCK_HASH,
            "timestamp": 1794398500, "transaction_hashes": (),
        }
        self.provider.headers[109] = {
            "number": 109, "hash": BLOCK_HASH, "parent_hash": BLOCK_HASH,
            "timestamp": 1794398499, "transaction_hashes": (TX_HASH,),
        }

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "EVM_BLOCK_TIMESTAMP_NOT_MONOTONIC")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT))
        self.assertEqual(self.ingestion_store.list_events("bnb-smart-chain-mainnet"), [])

    def test_rejects_duplicate_log_index_within_same_canonical_block(self):
        duplicate = EvmTokenTransferLog(
            network_id="bnb-smart-chain-mainnet", contract_address=CONTRACT,
            from_address="0x" + "4" * 40, to_address="0x" + "5" * 40,
            amount_raw="9", block_number=109, block_hash=BLOCK_HASH,
            transaction_hash="0x" + "c" * 64, log_index=4, removed=False,
            transaction_index=1,
        )
        self.provider.logs.append(duplicate)

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "DUPLICATE_EVM_LOG_INDEX")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT))
        self.assertEqual(self.ingestion_store.list_events("bnb-smart-chain-mainnet"), [])

    def test_rejects_log_transaction_index_that_disagrees_with_canonical_block_transactions(self):
        self.provider.headers[109] = {
            "number": 109, "hash": BLOCK_HASH, "parent_hash": BLOCK_HASH, "timestamp": 1794398509,
            "transaction_hashes": ("0x" + "f" * 64,),
        }

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "EVM_TRANSACTION_INDEX_MISMATCH")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT))
        self.assertEqual(self.ingestion_store.list_events("bnb-smart-chain-mainnet"), [])

    def test_rejects_log_transaction_index_outside_canonical_block_transaction_list(self):
        record = self.provider.logs[0]
        self.provider.logs = [EvmTokenTransferLog(
            network_id=record.network_id, contract_address=record.contract_address,
            from_address=record.from_address, to_address=record.to_address,
            amount_raw=record.amount_raw, block_number=record.block_number,
            block_hash=record.block_hash, transaction_hash=record.transaction_hash,
            log_index=record.log_index, removed=record.removed, transaction_index=1,
        )]
        self.provider.headers[109] = {
            "number": 109, "hash": BLOCK_HASH, "parent_hash": BLOCK_HASH, "timestamp": 1794398509,
            "transaction_hashes": (TX_HASH,),
        }

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "EVM_TRANSACTION_INDEX_MISMATCH")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT))

    def test_restart_resumes_from_durable_next_block_without_replaying_committed_range(self):
        self.worker.run_once()
        self.provider.finalized_height = 119
        self.provider.logs = []
        self.worker.run_once()
        self.assertEqual(self.provider.log_calls[-1], (CONTRACT, 110, 119))
        self.assertEqual(self.ingestion_store.get_checkpoint(
            "alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT
        )["next_block"], 120)

    def test_provider_timeout_retries_and_successfully_commits(self):
        self.provider.fail_header_once = True
        result = self.worker.run_once()
        self.assertEqual(result["events_inserted"], 1)
        self.assertEqual(self.ingestion_store.get_checkpoint(
            "alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT
        )["next_block"], 110)

    def test_failed_page_does_not_advance_checkpoint(self):
        self.provider.headers = {}
        # Fail both attempts for the first header.
        calls = {"count": 0}
        def always_fail(block_number):
            calls["count"] += 1
            raise ProviderTransportError("TIMEOUT", "provider request timed out")
        self.provider.fetch_bnb_block_header = always_fail
        with self.assertRaises(ProviderTransportError):
            self.worker.run_once()
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT
        ))
        self.assertGreaterEqual(calls["count"], 2)

    def test_reorg_lookback_tombstones_old_events_against_refetched_canonical_header(self):
        self.worker.run_once()
        self.provider.finalized_height = 119
        self.provider.headers[109] = {
            "number": 109, "hash": "0x" + "c" * 64, "parent_hash": BLOCK_HASH, "timestamp": 1794398509,
            "transaction_hashes": (TX_HASH,),
        }
        self.provider.logs = [EvmTokenTransferLog(
            network_id="bnb-smart-chain-mainnet", contract_address=CONTRACT,
            from_address="0x" + "2" * 40, to_address="0x" + "3" * 40,
            amount_raw="12345678901234567890", block_number=109,
            block_hash="0x" + "c" * 64, transaction_hash=TX_HASH,
            log_index=4, removed=False,
        )]
        second = self.worker.run_once()
        self.assertEqual(second["reorg_events_tombstoned"], 1)
        saved = self.ingestion_store.get_event(
            TX_HASH + ":4", "bnb-smart-chain-mainnet", "alchemy", "contract:" + CONTRACT
        )
        self.assertEqual(saved.canonical_status, "CANONICAL")
        self.assertEqual(saved.block_number, 109)
        self.assertEqual(saved.block_hash, "0x" + "c" * 64)
        self.assertEqual(len(self.ingestion_store.list_events(
            "bnb-smart-chain-mainnet", canonical_only=True
        )), 1)

    def test_reorg_in_previously_empty_block_is_detected_and_replayed(self):
        self.provider.logs = []
        self.worker.run_once()
        self.provider.finalized_height = 119
        self.provider.headers[109] = {
            "number": 109, "hash": "0x" + "d" * 64, "parent_hash": BLOCK_HASH, "timestamp": 1794398509,
            "transaction_hashes": ("0x" + "e" * 64,),
        }
        self.provider.logs = [EvmTokenTransferLog(
            network_id="bnb-smart-chain-mainnet", contract_address=CONTRACT,
            from_address="0x" + "2" * 40, to_address="0x" + "3" * 40,
            amount_raw="77", block_number=109, block_hash="0x" + "d" * 64,
            transaction_hash="0x" + "e" * 64, log_index=0, removed=False,
        )]
        result = self.worker.run_once()
        self.assertEqual(result["events_inserted"], 1)
        self.assertEqual(result["reorg_blocks_detected"], 1)
        saved = self.ingestion_store.get_event(
            "0x" + "e" * 64 + ":0", "bnb-smart-chain-mainnet", "alchemy",
            "contract:" + CONTRACT,
        )
        self.assertEqual(saved.canonical_status, "CANONICAL")
        self.assertEqual(saved.block_hash, "0x" + "d" * 64)
        self.assertEqual(self.ingestion_store.get_block_hash(
            "bnb-smart-chain-mainnet", "alchemy", "contract:" + CONTRACT, 109
        ), "0x" + "d" * 64)

    def test_rejects_discontinuous_parent_hashes_inside_fetched_finalized_range(self):
        self.provider.finalized_height = 101
        self.provider.logs = []
        self.worker.max_blocks_per_run = 2
        self.provider.headers = {
            100: {
                "number": 100, "hash": "0x" + "1" * 64,
                "parent_hash": "0x" + "0" * 64,
                "timestamp": 1794398500, "transaction_hashes": (),
            },
            101: {
                "number": 101, "hash": "0x" + "2" * 64,
                "parent_hash": "0x" + "3" * 64,
                "timestamp": 1794398501, "transaction_hashes": (),
            },
        }

        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()

        self.assertEqual(error.exception.reason_code, "EVM_PARENT_HASH_MISMATCH")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT))
        self.assertEqual(self.ingestion_store.list_events("bnb-smart-chain-mainnet"), [])

    def test_rejects_invalid_worker_bounds(self):
        with self.assertRaises(ValueError):
            EvmTransferIngestionWorker(
                self.provider, self.mapping_store, self.ingestion_store,
                start_blocks={mapping().mapping_id: 100},
                max_blocks_per_run=1001, reorg_lookback_blocks=2,
            )



class FakeEthereumProvider:
    def __init__(self):
        self.finalized_height = 265
        self.logs = [EvmTokenTransferLog(
            network_id="ethereum-mainnet", contract_address=CONTRACT,
            from_address="0x" + "2" * 40, to_address="0x" + "3" * 40,
            amount_raw="987654321", block_number=260, block_hash=BLOCK_HASH,
            transaction_hash="0x" + "d" * 64, log_index=9, removed=False,
        )]
        self.headers = {}
        self.log_calls = []

    def fetch_ethereum_finalized_height(self):
        return self.finalized_height

    def fetch_ethereum_block_header(self, block_number):
        if block_number in self.headers:
            return self.headers[block_number]
        records = [item for item in self.logs if item.block_number == block_number]
        previous = self.headers.get(block_number - 1)
        parent_hash = previous["hash"] if previous is not None else BLOCK_HASH
        by_index = {item.transaction_index: item.transaction_hash.lower() for item in records}
        transaction_hashes = tuple(by_index[index] for index in range(max(by_index, default=-1) + 1))
        return {
            "number": block_number, "hash": BLOCK_HASH, "parent_hash": parent_hash,
            "timestamp": 1794398400 + block_number,
            "transaction_hashes": transaction_hashes,
        }

    def fetch_ethereum_erc20_transfer_logs(self, contract_address, from_block, to_block):
        self.log_calls.append((contract_address, from_block, to_block))
        return ProviderDataPage(
            "alchemy", "ethereum-mainnet", contract_address,
            tuple(item for item in self.logs
                  if from_block <= item.block_number <= to_block
                  and item.contract_address.lower() == contract_address.lower()),
            from_block=from_block, to_block=to_block,
            finalized_height=self.finalized_height,
            finality_reference="eth_getBlockByNumber:finalized",
        )


class EthereumTransferIngestionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self.tmp.name, "ethereum.sqlite3")
        engine = OnChainIntelligenceEngine(
            {"ethereum-mainnet": 86400},
            receipt_signing_key=b"test-only-onchain-receipt-key-32-bytes-minimum",
            receipt_key_id="test-key-v1")
        self.ingestion_store = OnChainIngestionStore(path)
        self.asset_mapping = mapping(
            "asset-eth-v1", network_id="ethereum-mainnet", chain_id="1"
        )
        self.mapping_store = MappingStoreStub(engine, self.asset_mapping)
        self.provider = FakeEthereumProvider()
        self.worker = EvmTransferIngestionWorker(
            self.provider, self.mapping_store, self.ingestion_store,
            start_blocks={self.asset_mapping.mapping_id: 256},
            max_blocks_per_run=10, reorg_lookback_blocks=2,
            retry_attempts=2, sleep=lambda _: None,
            clock=lambda: datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc),
        )

    def tearDown(self):
        self.ingestion_store.close()
        self.mapping_store.close()
        self.tmp.cleanup()

    def test_ethereum_ingests_only_mapped_finalized_logs_with_stable_log_identity(self):
        result = self.worker.run_once()
        self.assertEqual(result["events_inserted"], 1)
        saved = self.ingestion_store.list_events("ethereum-mainnet", canonical_only=True)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].event_id, "0x" + "d" * 64 + ":9")
        self.assertEqual(saved[0].block_number, 260)
        self.assertEqual(saved[0].amount_raw, "987654321")
        self.assertEqual(self.provider.log_calls, [(CONTRACT, 256, 265)])
        self.assertEqual(self.ingestion_store.get_checkpoint(
            "alchemy:ethereum-mainnet:contract:" + CONTRACT
        )["next_block"], 266)

    def test_ethereum_rejects_page_with_wrong_finality_semantics_without_advancing_cursor(self):
        original = self.provider.fetch_ethereum_erc20_transfer_logs
        def wrong_finality(contract_address, from_block, to_block):
            page = original(contract_address, from_block, to_block)
            return ProviderDataPage(
                page.provider, page.network_id, page.scope, page.records,
                from_block=page.from_block, to_block=page.to_block,
                finalized_height=page.finalized_height,
                finality_reference="latest",
            )
        self.provider.fetch_ethereum_erc20_transfer_logs = wrong_finality
        with self.assertRaises(ProviderTransportError) as error:
            self.worker.run_once()
        self.assertEqual(error.exception.reason_code, "INVALID_PROVIDER_DATA")
        self.assertIsNone(self.ingestion_store.get_checkpoint(
            "alchemy:ethereum-mainnet:contract:" + CONTRACT
        ))

    def test_ethereum_restart_resumes_from_durable_checkpoint(self):
        self.worker.run_once()
        self.provider.finalized_height = 275
        self.provider.logs = []
        self.worker.run_once()
        self.assertEqual(self.provider.log_calls[-1], (CONTRACT, 266, 275))
        self.assertEqual(self.ingestion_store.get_checkpoint(
            "alchemy:ethereum-mainnet:contract:" + CONTRACT
        )["next_block"], 276)

    def test_ethereum_reorg_in_empty_block_rewinds_and_replays(self):
        self.provider.logs = []
        self.worker.run_once()
        self.provider.finalized_height = 275
        self.provider.headers[264] = {
            "number": 264, "hash": "0x" + "c" * 64, "parent_hash": BLOCK_HASH, "timestamp": 1794398664,
            "transaction_hashes": ("0x" + "e" * 64,),
        }
        self.provider.logs = [EvmTokenTransferLog(
            network_id="ethereum-mainnet", contract_address=CONTRACT,
            from_address="0x" + "2" * 40, to_address="0x" + "3" * 40,
            amount_raw="44", block_number=264, block_hash="0x" + "c" * 64,
            transaction_hash="0x" + "e" * 64, log_index=2, removed=False,
        )]
        result = self.worker.run_once()
        self.assertEqual(result["reorg_blocks_detected"], 1)
        self.assertEqual(result["events_inserted"], 1)
        saved = self.ingestion_store.get_event(
            "0x" + "e" * 64 + ":2", "ethereum-mainnet", "alchemy",
            "contract:" + CONTRACT,
        )
        self.assertEqual(saved.canonical_status, "CANONICAL")
        self.assertEqual(saved.block_hash, "0x" + "c" * 64)

if __name__ == "__main__":
    unittest.main()
