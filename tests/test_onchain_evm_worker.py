import os
import tempfile
import unittest
from datetime import datetime, timezone
from layer1.foundation import EligibilityDecision
from layer1.onchain import (
    OnChainAssetMapping, OnChainIntelligenceEngine, OnChainObservation, OnChainStore,
)
from layer1.onchain_ingestion import OnChainIngestionStore
from layer1.onchain_providers import EvmTokenTransferLog, ProviderDataPage, ProviderTransportError
from layer1.onchain_evm_worker import EvmTransferIngestionWorker


CONTRACT = "0x" + "1" * 40
BLOCK_HASH = "0x" + "b" * 64
TX_HASH = "0x" + "a" * 64


def mapping(mapping_id="asset-bnb-v1", contract=CONTRACT, status="VERIFIED"):
    return OnChainAssetMapping(
        mapping_id=mapping_id, asset_id="coingecko:example", binance_symbol="EXAMPLE",
        network_id="bnb-smart-chain-mainnet", network_family="EVM", chain_id="56",
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
        return self.headers.get(block_number, {
            "number": block_number, "hash": BLOCK_HASH,
            "timestamp": 1794398400 + block_number,
        })


class EvmTransferIngestionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self.tmp.name, "onchain.sqlite3")
        self.mapping_store = OnChainStore(
            path, OnChainIntelligenceEngine({"bnb-smart-chain-mainnet": 86400})
        )
        self.ingestion_store = OnChainIngestionStore(path)
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()
        eligibility = EligibilityDecision(
            status="ELIGIBLE", asset_id="coingecko:example", symbol="EXAMPLE",
            eligible_pairs=("EXAMPLEUSDT",), verified_at=timestamp,
            identity_proof_status="VERIFIED", identity_proof_source="coingecko_coin_tickers",
            identity_proof_verified_at=timestamp, identity_proof_source_timestamp=timestamp,
            identity_proof_data_hash="a" * 64,
        )
        verified_mapping = mapping()
        observation = OnChainObservation(
            observation_id="bnb-map-verification", mapping_id=verified_mapping.mapping_id,
            asset_id=verified_mapping.asset_id, network_id=verified_mapping.network_id,
            chain_id="56", provider="alchemy", endpoint_id="bnb-mainnet-rpc",
            observation_type="TRANSFER", block_height=100, block_hash=BLOCK_HASH,
            transaction_hash=TX_HASH, block_time=timestamp, observed_at=timestamp,
            finality="FINALIZED", finality_reference="eth_getFinalizedHeader",
        )
        self.mapping_store.save_verified(eligibility, verified_mapping, observation)
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

    def test_ingests_only_verified_mapped_contract_logs_and_commits_bounded_checkpoint(self):
        result = self.worker.run_once()
        self.assertEqual(result["events_inserted"], 1)
        saved = self.ingestion_store.list_events("bnb-smart-chain-mainnet", canonical_only=True)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].event_id, TX_HASH + ":4")
        self.assertEqual(saved[0].amount_raw, "12345678901234567890")
        self.assertEqual(self.ingestion_store.get_checkpoint(
            "alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT
        )["next_block"], 110)
        self.assertEqual(self.provider.log_calls, [(CONTRACT, 100, 109)])

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
            "number": 109, "hash": "0x" + "c" * 64, "timestamp": 1794398509,
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
            "number": 109, "hash": "0x" + "d" * 64, "timestamp": 1794398509,
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

    def test_rejects_invalid_worker_bounds(self):
        with self.assertRaises(ValueError):
            EvmTransferIngestionWorker(
                self.provider, self.mapping_store, self.ingestion_store,
                start_blocks={mapping().mapping_id: 100},
                max_blocks_per_run=1001, reorg_lookback_blocks=2,
            )


if __name__ == "__main__":
    unittest.main()
