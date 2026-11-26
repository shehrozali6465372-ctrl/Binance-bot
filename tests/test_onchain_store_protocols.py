import inspect
import unittest

from layer1.onchain import OnChainAssetMapping, OnChainIntelligenceEngine
from layer1.onchain_postgres import PostgresOnChainIngestionStore, PostgresOnChainStore
from layer1.onchain_bitcoin_worker import BitcoinAddressIngestionWorker
from layer1.onchain_evm_worker import EvmTransferIngestionWorker
from layer1.onchain_solana_worker import SolanaAddressIngestionWorker
from layer1.onchain_xrpl_worker import XrplIssuedCurrencyIngestionWorker
from layer1.onchain_aggregation import OnChainTransferAggregator


TEST_KEY = b"test-only-onchain-receipt-key-32-bytes-minimum"


def postgres_shaped_stores(mapping=None):
    mapping_store = object.__new__(PostgresOnChainStore)
    mapping_store.engine = OnChainIntelligenceEngine(
        freshness_limits_seconds={"bitcoin-mainnet": 3600},
        receipt_signing_key=TEST_KEY, receipt_key_id="protocol-test-v1"
    )
    mapping_store.list_verified_mappings = lambda network_id=None: (
        [mapping] if mapping is not None else []
    )
    mapping_store.get_latest_accepted_observation = lambda mapping_id: None

    ingestion_store = object.__new__(PostgresOnChainIngestionStore)
    return mapping_store, ingestion_store


def btc_mapping():
    return OnChainAssetMapping(
        "btc-native-v1", "coingecko:bitcoin", "BTC", "bitcoin-mainnet",
        "UTXO", "bitcoin-mainnet", "NATIVE", None, None, 8, "VERIFIED",
        "OFFICIAL_NETWORK", "https://bitcoin.org",
        "2026-11-23T00:00:00+00:00",
    )


class OnChainStoreProtocolTests(unittest.TestCase):
    def setUp(self):
        self.mapping = btc_mapping()
        self.mapping_store, self.ingestion_store = postgres_shaped_stores(self.mapping)

    def test_actual_postgres_adapter_classes_satisfy_structural_protocols_without_connecting(self):
        from layer1.onchain_protocols import require_ingestion_store, require_mapping_store

        mapping_store = object.__new__(PostgresOnChainStore)
        mapping_store.engine = OnChainIntelligenceEngine(
            freshness_limits_seconds={"bitcoin-mainnet": 3600},
            receipt_signing_key=TEST_KEY, receipt_key_id="protocol-test-v1",
        )
        ingestion_store = object.__new__(PostgresOnChainIngestionStore)

        require_mapping_store(mapping_store)
        require_ingestion_store(ingestion_store)

    def test_bitcoin_worker_accepts_postgres_store_shapes_without_database_or_provider_io(self):
        worker = BitcoinAddressIngestionWorker(
            object(), self.mapping_store, self.ingestion_store,
            monitored_addresses={self.mapping.mapping_id: ("1BoatSLRHtKNngkdXEeobR76b53LETtpyT",)},
            start_blocks={self.mapping.mapping_id: 1}, minimum_confirmations=1,
            max_blocks_per_run=1, page_size=1, reorg_lookback_blocks=1,
            retry_attempts=1, sleep=lambda _: None,
        )
        self.assertIs(worker.mapping_store, self.mapping_store)
        self.assertIs(worker.ingestion_store, self.ingestion_store)

    def test_evm_worker_accepts_postgres_store_shapes_without_database_or_provider_io(self):
        worker = EvmTransferIngestionWorker(
            object(), self.mapping_store, self.ingestion_store,
            start_blocks={self.mapping.mapping_id: 1}, max_blocks_per_run=1,
            reorg_lookback_blocks=1, retry_attempts=1, sleep=lambda _: None,
        )
        self.assertIs(worker.mapping_store, self.mapping_store)
        self.assertIs(worker.ingestion_store, self.ingestion_store)

    def test_solana_worker_accepts_postgres_store_shapes_without_database_or_provider_io(self):
        worker = SolanaAddressIngestionWorker(
            object(), self.mapping_store, self.ingestion_store,
            monitored_addresses={self.mapping.mapping_id: ("Vote111111111111111111111111111111111111111",)},
            start_slots={self.mapping.mapping_id: 1}, max_slots_per_run=1,
            page_size=1, reorg_lookback_slots=1, retry_attempts=1,
            sleep=lambda _: None,
        )
        self.assertIs(worker.mapping_store, self.mapping_store)
        self.assertIs(worker.ingestion_store, self.ingestion_store)

    def test_xrpl_worker_accepts_postgres_store_shapes_without_database_or_provider_io(self):
        worker = XrplIssuedCurrencyIngestionWorker(
            object(), self.mapping_store, self.ingestion_store,
            monitored_accounts={self.mapping.mapping_id: ("rLNaPoKeeBjZe2qs6x52yVPZpZ8td4dc6w",)},
            start_ledgers={self.mapping.mapping_id: 1}, max_ledgers_per_run=1,
            page_size=1, max_pages_per_run=1, reorg_lookback_ledgers=1,
            retry_attempts=1, sleep=lambda _: None,
        )
        self.assertIs(worker.mapping_store, self.mapping_store)
        self.assertIs(worker.ingestion_store, self.ingestion_store)

    def test_aggregator_accepts_postgres_mapping_and_ingestion_store_shapes(self):
        aggregator = OnChainTransferAggregator(
            self.mapping_store,
            minimum_amount_by_mapping={self.mapping.mapping_id: "1"},
        )
        aggregator.bind_ingestion_store(self.ingestion_store)
        self.assertIs(aggregator.mapping_store, self.mapping_store)
        self.assertIs(aggregator._ingestion_store, self.ingestion_store)

    def test_rejects_mapping_store_missing_required_callable(self):
        broken = object()
        with self.assertRaisesRegex(ValueError, "mapping store"):
            BitcoinAddressIngestionWorker(
                object(), broken, self.ingestion_store,
                monitored_addresses={self.mapping.mapping_id: ("1BoatSLRHtKNngkdXEeobR76b53LETtpyT",)},
                start_blocks={self.mapping.mapping_id: 1}, minimum_confirmations=1,
                max_blocks_per_run=1, page_size=1, reorg_lookback_blocks=1,
            )

    def test_rejects_mapping_store_without_validation_engine(self):
        broken = object.__new__(PostgresOnChainStore)
        broken.list_verified_mappings = lambda network_id=None: [self.mapping]
        broken.get_latest_accepted_observation = lambda mapping_id: None
        with self.assertRaisesRegex(ValueError, "mapping store"):
            BitcoinAddressIngestionWorker(
                object(), broken, self.ingestion_store,
                monitored_addresses={self.mapping.mapping_id: ("1BoatSLRHtKNngkdXEeobR76b53LETtpyT",)},
                start_blocks={self.mapping.mapping_id: 1}, minimum_confirmations=1,
                max_blocks_per_run=1, page_size=1, reorg_lookback_blocks=1,
            )

    def test_rejects_ingestion_store_missing_required_callable(self):
        with self.assertRaisesRegex(ValueError, "ingestion store"):
            BitcoinAddressIngestionWorker(
                object(), self.mapping_store, object(),
                monitored_addresses={self.mapping.mapping_id: ("1BoatSLRHtKNngkdXEeobR76b53LETtpyT",)},
                start_blocks={self.mapping.mapping_id: 1}, minimum_confirmations=1,
                max_blocks_per_run=1, page_size=1, reorg_lookback_blocks=1,
            )

    def test_rejects_ingestion_store_without_mandatory_checkpoint_and_scope_keywords(self):
        class WeakIngestionStore:
            def get_checkpoint(self, *args): return None
            def commit_page(self, cursor_key, next_cursor, events): return {}
            def get_block_hash(self, *args): return None
            def reconcile_block(self, network_id, block_number, canonical_hash): return 0
            def get_solana_slot_journal(self, *args): return {}
            def get_event(self, *args): return None
            def list_all_events(self, canonical_only=False): return []
            def list_page_receipts(self, cursor_key): return ()
            def get_page_acceptance_material(self, cursor_key, page_id): return {}
            def save_page_acceptance(self, cursor_key, page_id, key_id, payload_json, payload_sha256, signature): return "INSERTED"
            def get_page_acceptance(self, cursor_key, page_id): return None
            def list_ingestion_pages(self): return ()
            def list_pending_page_acceptances(self): return ()

        with self.assertRaisesRegex(ValueError, "expected_cursor"):
            BitcoinAddressIngestionWorker(
                object(), self.mapping_store, WeakIngestionStore(),
                monitored_addresses={self.mapping.mapping_id: ("1BoatSLRHtKNngkdXEeobR76b53LETtpyT",)},
                start_blocks={self.mapping.mapping_id: 1}, minimum_confirmations=1,
                max_blocks_per_run=1, page_size=1, reorg_lookback_blocks=1,
            )

    def test_rejects_ingestion_store_missing_optional_commit_page_keywords_used_by_workers(self):
        class IncompleteIngestionStore:
            def get_checkpoint(self, cursor_key): return None
            def commit_page(self, cursor_key, next_cursor, events, *, expected_cursor, scope_identity, allow_recanonicalized=False, canonical_blocks=(), canonical_slots=()): return {}
            def get_block_hash(self, network_id, provider, scope, block_number): return None
            def reconcile_block(self, network_id, block_number, canonical_hash, *, provider, scope): return 0
            def get_solana_slot_journal(self, network_id, provider, scope, start_slot, end_slot): return {}
            def get_event(self, event_id, network_id, provider=None, scope=None): return None
            def list_all_events(self, canonical_only=False): return []
            def list_page_receipts(self, cursor_key): return ()
            def get_page_acceptance_material(self, cursor_key, page_id): return {}
            def save_page_acceptance(self, cursor_key, page_id, key_id, payload_json, payload_sha256, signature): return "INSERTED"
            def get_page_acceptance(self, cursor_key, page_id): return None
            def list_ingestion_pages(self): return ()
            def list_pending_page_acceptances(self): return ()

        with self.assertRaisesRegex(ValueError, "provider_receipts"):
            BitcoinAddressIngestionWorker(
                object(), self.mapping_store, IncompleteIngestionStore(),
                monitored_addresses={self.mapping.mapping_id: ("1BoatSLRHtKNngkdXEeobR76b53LETtpyT",)},
                start_blocks={self.mapping.mapping_id: 1}, minimum_confirmations=1,
                max_blocks_per_run=1, page_size=1, reorg_lookback_blocks=1,
            )

    def test_rejects_mapping_engine_without_network_freshness_policy(self):
        class IncompleteEngine:
            def validate(self, eligibility, mapping, observation, *, now=None):
                return None

        self.mapping_store.engine = IncompleteEngine()
        with self.assertRaisesRegex(ValueError, "freshness_limits_seconds"):
            BitcoinAddressIngestionWorker(
                object(), self.mapping_store, self.ingestion_store,
                monitored_addresses={self.mapping.mapping_id: ("1BoatSLRHtKNngkdXEeobR76b53LETtpyT",)},
                start_blocks={self.mapping.mapping_id: 1}, minimum_confirmations=1,
                max_blocks_per_run=1, page_size=1, reorg_lookback_blocks=1,
            )

    def test_protocol_requires_cursor_snapshot_and_scope_identity(self):
        from layer1.onchain_protocols import OnChainIngestionStoreProtocol
        signature = inspect.signature(OnChainIngestionStoreProtocol.commit_page)
        self.assertIs(signature.parameters["expected_cursor"].default, inspect.Parameter.empty)
        self.assertIs(signature.parameters["scope_identity"].default, inspect.Parameter.empty)

    def test_protocol_requires_provider_and_scope_for_reorg_reconciliation(self):
        from layer1.onchain_protocols import OnChainIngestionStoreProtocol
        signature = inspect.signature(OnChainIngestionStoreProtocol.reconcile_block)
        self.assertIs(signature.parameters["provider"].default, inspect.Parameter.empty)
        self.assertIs(signature.parameters["scope"].default, inspect.Parameter.empty)


if __name__ == "__main__":
    unittest.main()
