"""PostgreSQL integration tests for Module 9 durable on-chain storage.

Set TEST_POSTGRES_DSN to a dedicated database named binance_onchain_test.
Local databases are accepted by default. A remote test server requires an exact
TEST_POSTGRES_ALLOWED_HOST allowlist entry and TLS; other hosts are rejected.
"""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

TEST_DSN = os.environ.get("TEST_POSTGRES_DSN")


class PostgresAdapterContractTests(unittest.TestCase):
    def test_postgres_save_verified_defaults_to_constructor_bound_ingestion_store(self):
        from types import SimpleNamespace
        from layer1.onchain_postgres import PostgresOnChainStore

        class Engine:
            def __init__(self):
                self.ingestion_store = None

            def validate(self, eligibility, mapping, observation, *, ingestion_store=None,
                         provenance=None):
                self.ingestion_store = ingestion_store
                return SimpleNamespace(status="UNVERIFIED", reason_code="TEST_REJECTION")

        ingestion = object()
        engine = Engine()
        store = object.__new__(PostgresOnChainStore)
        store.engine = engine
        store.ingestion_store = ingestion
        with self.assertRaisesRegex(ValueError, "TEST_REJECTION"):
            store.save_verified(object(), object(), object(), provenance=object())
        self.assertIs(engine.ingestion_store, ingestion)

    def test_postgres_pending_query_surfaces_unreceipted_evidence_pages(self):
        from layer1.onchain_postgres import PostgresOnChainIngestionStore

        class Result:
            def fetchall(self):
                return [
                    ("cursor-events", "a" * 64, {"events": [{"event_id": "event-1"}]}, []),
                    ("cursor-checkpoint", "b" * 64, {"events": [], "canonical_blocks": [], "canonical_slots": []}, []),
                    ("cursor-invalid", "c" * 64, "malformed-shape", None),
                ]

        class Connection:
            def execute(self, query):
                self.query = query
                return Result()

        store = object.__new__(PostgresOnChainIngestionStore)
        store.conn = Connection()
        self.assertEqual(
            store.list_pending_page_acceptances(),
            (("cursor-events", "a" * 64), ("cursor-invalid", "c" * 64)),
        )

    def test_postgres_list_page_receipts_rejects_sequence_gaps_even_when_digest_matches(self):
        import hashlib
        from dataclasses import asdict
        from layer1.onchain_ingestion import OnChainIngestionStore
        from layer1.onchain_postgres import PostgresOnChainIngestionStore
        from layer1.onchain_providers import ProviderResponseReceipt

        receipt = ProviderResponseReceipt(
            sequence=2, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
        )
        page_material = {"cursor_key": "cursor"}
        page_id = hashlib.sha256(
            OnChainIngestionStore._canonical(page_material).encode("utf-8")
        ).hexdigest()
        payload = [asdict(receipt)]
        receipt_digest = hashlib.sha256(
            OnChainIngestionStore._canonical(payload).encode("utf-8")
        ).hexdigest()

        class Result:
            def fetchall(self):
                return [(page_id, page_material, receipt_digest, payload)]

        class Connection:
            def execute(self, query, params):
                self.query, self.params = query, params
                return Result()

        store = object.__new__(PostgresOnChainIngestionStore)
        store.conn = Connection()
        with self.assertRaisesRegex(ValueError, "receipt sequence"):
            store.list_page_receipts("cursor")

    def test_postgres_page_commit_rejects_omitted_checkpoint_snapshot_before_database_access(self):
        from layer1.onchain_postgres import PostgresOnChainIngestionStore
        store = object.__new__(PostgresOnChainIngestionStore)
        with self.assertRaisesRegex(ValueError, "expected_cursor"):
            store.commit_page("cursor", {"next": 1}, ())

    def test_postgres_new_page_commit_rejects_receipt_without_endpoint_profile_fingerprint(self):
        from layer1.onchain_postgres import PostgresOnChainIngestionStore
        from layer1.onchain_providers import (
            ProviderResponseReceipt, _ACTIVE_PAGE_RECEIPTS,
            _capture_provider_run_receipts, drain_provider_run_receipts,
        )
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
        )
        @_capture_provider_run_receipts
        def captured():
            _ACTIVE_PAGE_RECEIPTS.get().append(receipt)
            return drain_provider_run_receipts()
        store = object.__new__(PostgresOnChainIngestionStore)
        with self.assertRaisesRegex(ValueError, "endpoint profile fingerprint"):
            store.commit_page(
                "cursor", {"next": 1}, (), expected_cursor=None,
                scope_identity=("bnb-smart-chain-mainnet", "alchemy", "contract:test"),
                provider_receipts=captured(),
            )

    def test_postgres_new_page_commit_rejects_fingerprint_outside_approved_profile(self):
        from layer1.onchain_postgres import PostgresOnChainIngestionStore
        from layer1.onchain_providers import (
            ProviderResponseReceipt, _ACTIVE_PAGE_RECEIPTS,
            _capture_provider_run_receipts, drain_provider_run_receipts,
        )
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="f" * 64,
        )
        @_capture_provider_run_receipts
        def captured():
            _ACTIVE_PAGE_RECEIPTS.get().append(receipt)
            return drain_provider_run_receipts()
        store = object.__new__(PostgresOnChainIngestionStore)
        with self.assertRaisesRegex(ValueError, "approved provider/network endpoint profile"):
            store.commit_page(
                "cursor", {"next": 1}, (), expected_cursor=None,
                scope_identity=("bnb-smart-chain-mainnet", "alchemy", "contract:test"),
                provider_receipts=captured(),
            )

    def test_postgres_anchor_observation_page_rejects_unapproved_endpoint_id(self):
        from layer1.onchain_postgres import PostgresOnChainIngestionStore
        from layer1.onchain_providers import (
            ProviderResponseReceipt, _ACTIVE_PAGE_RECEIPTS,
            _approved_endpoint_profile_sha256, _capture_provider_run_receipts,
            drain_provider_run_receipts,
        )
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="get_anchor_observation", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256=_approved_endpoint_profile_sha256(
                "alchemy", "bnb-smart-chain-mainnet",
            ),
        )
        @_capture_provider_run_receipts
        def captured():
            _ACTIVE_PAGE_RECEIPTS.get().append(receipt)
            return drain_provider_run_receipts()
        observation = {
            "observation_id": "obs-1", "mapping_id": "mapping-1",
            "asset_id": "asset-1", "network_id": "bnb-smart-chain-mainnet",
            "chain_id": "56", "provider": "alchemy",
            "endpoint_id": "unapproved-endpoint-alias",
            "observation_type": "TRANSFER", "block_height": 100,
            "block_hash": "b" * 66, "transaction_hash": "a" * 66,
            "block_time": "2026-11-26T12:00:00+00:00",
            "observed_at": "2026-11-26T12:00:01+00:00",
            "finality": "FINALIZED",
            "finality_reference": "eth_getBlockByNumber:finalized",
            "scope": "contract:0x" + "1" * 40,
        }
        store = object.__new__(PostgresOnChainIngestionStore)
        with self.assertRaisesRegex(ValueError, "endpoint_id does not match"):
            store.commit_page(
                "cursor", {
                    "finalized_height": 100,
                    "finality_reference": "eth_getBlockByNumber:finalized",
                }, (), expected_cursor=None,
                scope_identity=(
                    "bnb-smart-chain-mainnet", "alchemy", observation["scope"],
                ),
                canonical_blocks=({
                    "network_id": "bnb-smart-chain-mainnet", "provider": "alchemy",
                    "scope": observation["scope"], "block_number": 100,
                    "block_hash": observation["block_hash"],
                    "block_time": observation["block_time"],
                },),
                provider_receipts=captured(),
                provider_observations=(observation,),
            )

    def test_postgres_adapters_and_migration_runner_are_available(self):
        from layer1.onchain_postgres import (
            PostgresOnChainIngestionStore, PostgresOnChainStore,
            StaleCheckpointError, CanonicalBlockConflict, apply_postgres_migrations,
        )
        self.assertTrue(callable(PostgresOnChainIngestionStore))
        self.assertTrue(callable(PostgresOnChainStore))
        self.assertTrue(issubclass(StaleCheckpointError, RuntimeError))
        self.assertTrue(issubclass(CanonicalBlockConflict, RuntimeError))
        self.assertTrue(callable(apply_postgres_migrations))


    def test_postgres_page_commit_rejects_naive_canonical_block_time_before_database_access(self):
        from layer1.onchain_postgres import PostgresOnChainIngestionStore

        class Connection:
            def transaction(self):
                raise AssertionError("database transaction must not start for invalid canonical block time")

        store = object.__new__(PostgresOnChainIngestionStore)
        store.conn = Connection()
        with self.assertRaisesRegex(ValueError, "timezone-aware ISO-8601"):
            store.commit_page(
                "cursor", {"next": 1}, (), expected_cursor=None,
                scope_identity=("ethereum-mainnet", "alchemy", "contract:0x" + "1" * 40),
                canonical_blocks=({
                    "network_id": "ethereum-mainnet", "provider": "alchemy",
                    "scope": "contract:0x" + "1" * 40, "block_number": 1,
                    "block_hash": "0x" + "a" * 64,
                    "block_time": "2026-11-27T12:00:00",
                },),
            )

    def test_postgres_page_commit_rejects_naive_produced_solana_slot_time_before_database_access(self):
        from layer1.onchain_postgres import PostgresOnChainIngestionStore

        class Connection:
            def transaction(self):
                raise AssertionError("database transaction must not start for invalid Solana slot time")

        store = object.__new__(PostgresOnChainIngestionStore)
        store.conn = Connection()
        with self.assertRaisesRegex(ValueError, "timezone-aware ISO-8601"):
            store.commit_page(
                "cursor", {"next": 1}, (), expected_cursor=None,
                scope_identity=("solana-mainnet", "alchemy", "address:" + "A" * 32),
                canonical_slots=({
                    "network_id": "solana-mainnet", "provider": "alchemy",
                    "scope": "address:" + "A" * 32, "slot": 1,
                    "produced": True, "block_hash": "B" * 32,
                    "block_time": "2026-11-27T12:00:00",
                },),
            )

    def test_postgres_contract_accepts_produced_slot_with_unknown_time_and_quarantine(self):
        from layer1.onchain_postgres import PostgresOnChainIngestionStore
        from tests.test_solana_normalization import BLOCKHASH, SIGNATURE

        class Connection:
            def transaction(self):
                raise AssertionError("validation passed; transaction boundary reached")

        store = object.__new__(PostgresOnChainIngestionStore)
        store.conn = Connection()
        scope = "address:wallet-test:mapping:sol-usdc-v1"
        with self.assertRaisesRegex(AssertionError, "transaction boundary reached"):
            store.commit_page(
                "cursor", {"next_slot": 2}, (), expected_cursor=None,
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
                        "raw": {"slot": 1, "transaction": {"signatures": [SIGNATURE], "message": {}}, "meta": {"err": None}},
                        "observed_at": "2026-11-27T12:00:00+00:00",
                    },
                },),
            )

    def test_postgres_contract_rejects_boolean_raw_slot_alias_in_quarantine(self):
        from layer1.onchain_postgres import PostgresOnChainIngestionStore
        from tests.test_solana_normalization import BLOCKHASH, SIGNATURE

        class Connection:
            def transaction(self):
                raise AssertionError("validation passed; transaction boundary reached")

        store = object.__new__(PostgresOnChainIngestionStore)
        store.conn = Connection()
        scope = "address:wallet-test:mapping:sol-usdc-v1"
        with self.assertRaisesRegex(ValueError, "Solana quarantine transaction record is malformed"):
            store.commit_page(
                "cursor", {"next_slot": 2}, (), expected_cursor=None,
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

    def test_postgres_contract_rejects_raw_block_time_mismatch_in_quarantine(self):
        from layer1.onchain_postgres import PostgresOnChainIngestionStore
        from tests.test_solana_normalization import BLOCKHASH, SIGNATURE

        class Connection:
            def transaction(self):
                raise AssertionError("validation passed; transaction boundary reached")

        store = object.__new__(PostgresOnChainIngestionStore)
        store.conn = Connection()
        scope = "address:wallet-test:mapping:sol-usdc-v1"
        with self.assertRaisesRegex(ValueError, "Solana quarantine transaction record is malformed"):
            store.commit_page(
                "cursor", {"next_slot": 2}, (), expected_cursor=None,
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

    def test_postgres_contract_rejects_missing_transaction_execution_status_in_quarantine(self):
        from layer1.onchain_postgres import PostgresOnChainIngestionStore
        from tests.test_solana_normalization import BLOCKHASH, SIGNATURE

        class Connection:
            def transaction(self):
                raise AssertionError("validation passed; transaction boundary reached")

        store = object.__new__(PostgresOnChainIngestionStore)
        store.conn = Connection()
        scope = "address:wallet-test:mapping:sol-usdc-v1"
        with self.assertRaisesRegex(ValueError, "Solana quarantine transaction record is malformed"):
            store.commit_page(
                "cursor", {"next_slot": 2}, (), expected_cursor=None,
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

    def test_solana_timestamp_quarantine_migration_relaxes_only_produced_slot_time(self):
        from pathlib import Path
        migration = Path("layer1/migrations/postgresql/0005_solana_timestamp_quarantine.sql").read_text()
        self.assertIn("solana_slot_journal_time_quarantine_check", migration)
        self.assertIn("produced = TRUE AND block_hash IS NOT NULL", migration)
        self.assertIn("layer1_onchain_solana_quarantine", migration)
        self.assertIn("REFERENCES layer1_onchain_ingestion_pages(page_id)", migration)


def _dedicated_local_test_dsn():
    if not TEST_DSN:
        return False
    from tests.postgres_test_support import validate_postgres_test_target
    validate_postgres_test_target(TEST_DSN, os.environ.get("TEST_POSTGRES_ALLOWED_HOST", "").strip())
    return True


@unittest.skipUnless(TEST_DSN, "TEST_POSTGRES_DSN is not configured")
class PostgresOnChainIngestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _dedicated_local_test_dsn():
            raise RuntimeError("PostgreSQL integration tests require a dedicated local test database")
        from layer1.onchain_postgres import apply_postgres_migrations
        apply_postgres_migrations(TEST_DSN)

    def setUp(self):
        import psycopg
        from layer1.onchain_postgres import PostgresOnChainIngestionStore
        self.conn = psycopg.connect(TEST_DSN, autocommit=True)
        self.conn.execute("""
            TRUNCATE TABLE
                layer1_onchain_observations,
                layer1_onchain_asset_mappings,
                layer1_onchain_transfer_events,
                layer1_onchain_ingestion_blocks,
                layer1_onchain_solana_slot_journal,
                layer1_onchain_ingestion_page_acceptances,
                layer1_onchain_ingestion_pages,
                layer1_onchain_ingestion_checkpoints
            RESTART IDENTITY CASCADE
        """)
        self.conn.close()
        self.store = PostgresOnChainIngestionStore(TEST_DSN)

    def tearDown(self):
        self.store.close()

    def event(self, event_id="event-1", block_hash="b" * 64, status="CANONICAL"):
        from layer1.onchain_ingestion import NormalizedTransferEvent
        return NormalizedTransferEvent(
            event_id=event_id, network_id="bnb-smart-chain-mainnet",
            provider="alchemy", scope="contract:0x" + "1" * 40,
            asset_id="coingecko:example", mapping_id="example-bnb-v1",
            transaction_hash="a" * 64, block_number=100, block_hash=block_hash,
            event_index=2, from_address="0x" + "2" * 40,
            to_address="0x" + "3" * 40, amount_raw="12345", decimals=18,
            block_time="2026-11-11T12:00:00+00:00",
            observed_at="2026-11-11T12:00:01+00:00",
            canonical_status=status, provenance="eth_getLogs",
        )

    @property
    def identity(self):
        return ("bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40)

    def commit(self, cursor, event=None, *, expected=None, blocks=(), slots=(), allow_recanonicalized=False):
        return self.store.commit_page(
            "alchemy:bnb:contract-1", cursor, [event] if event else (),
            expected_cursor=expected, scope_identity=self.identity,
            canonical_blocks=blocks, canonical_slots=slots,
            allow_recanonicalized=allow_recanonicalized,
        )

    def test_migrations_are_repeatable_and_create_required_storage(self):
        from layer1.onchain_postgres import apply_postgres_migrations
        apply_postgres_migrations(TEST_DSN)
        names = {
            row[0] for row in self.store.conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema()"
            ).fetchall()
        }
        self.assertTrue({
            "layer1_onchain_asset_mappings", "layer1_onchain_observations",
            "layer1_onchain_transfer_events", "layer1_onchain_ingestion_checkpoints",
            "layer1_onchain_ingestion_blocks", "layer1_onchain_solana_slot_journal",
            "layer1_onchain_ingestion_pages", "layer1_onchain_ingestion_page_acceptances",
        }.issubset(names))

    def test_provider_receipts_are_atomic_and_readable_after_store_reopen(self):
        from layer1.onchain_providers import (
            ProviderResponseReceipt, _ACTIVE_PAGE_RECEIPTS,
            _capture_provider_run_receipts, drain_provider_run_receipts,
        )
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
            tls_peer_certificate_sha256="c" * 64,
        )
        @_capture_provider_run_receipts
        def captured():
            _ACTIVE_PAGE_RECEIPTS.get().append(receipt)
            return drain_provider_run_receipts()
        self.store.commit_page(
            "alchemy:bnb:contract-1", {"next_block": 101}, [self.event()],
            expected_cursor=None, scope_identity=self.identity,
            provider_receipts=captured(),
        )
        self.store.close()
        from layer1.onchain_postgres import PostgresOnChainIngestionStore
        self.store = PostgresOnChainIngestionStore(TEST_DSN)
        self.assertEqual(self.store.list_page_receipts("alchemy:bnb:contract-1"), (receipt,))

    def test_ingestion_page_acceptance_is_signed_and_verified_after_store_reopen(self):
        from layer1.onchain import OnChainIntelligenceEngine
        from layer1.onchain_providers import (
            ProviderResponseReceipt, _ACTIVE_PAGE_RECEIPTS,
            _capture_provider_run_receipts, drain_provider_run_receipts,
        )
        event = self.event()
        block = {
            "network_id": event.network_id, "provider": event.provider,
            "scope": event.scope, "block_number": event.block_number,
            "block_hash": event.block_hash, "block_time": event.block_time,
        }
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
            tls_peer_certificate_sha256="c" * 64,
        )
        @_capture_provider_run_receipts
        def captured():
            _ACTIVE_PAGE_RECEIPTS.get().append(receipt)
            return drain_provider_run_receipts()
        cursor_key = "alchemy:bnb:contract-acceptance"
        self.store.commit_page(
            cursor_key, {"next_block": 101}, [event], expected_cursor=None,
            scope_identity=self.identity, canonical_blocks=(block,),
            provider_receipts=captured(),
        )
        page_id = self.store.conn.execute(
            "SELECT page_id FROM layer1_onchain_ingestion_pages WHERE cursor_key=%s",
            (cursor_key,),
        ).fetchone()[0]
        engine = OnChainIntelligenceEngine(
            receipt_signing_key=b"test-only-onchain-ingestion-page-key-32-bytes",
            receipt_key_id="postgres-ingestion-v1",
        )
        pending_result = engine.sign_pending_ingestion_pages(self.store)
        self.assertEqual(pending_result, {"signed": 1, "pending": 0, "rejected": 0})
        signed = engine.sign_ingestion_page(self.store, cursor_key, page_id)
        self.assertEqual(engine.sign_ingestion_page(self.store, cursor_key, page_id), signed)
        self.assertTrue(engine.verify_ingestion_page_acceptance(self.store, cursor_key, page_id))
        self.store.close()
        from layer1.onchain_postgres import PostgresOnChainIngestionStore
        self.store = PostgresOnChainIngestionStore(TEST_DSN)
        restarted_engine = OnChainIntelligenceEngine(
            receipt_signing_key=b"test-only-onchain-ingestion-page-key-32-bytes",
            receipt_key_id="postgres-ingestion-v1",
        )
        self.assertTrue(restarted_engine.verify_ingestion_page_acceptance(
            self.store, cursor_key, page_id,
        ))

    def test_page_signing_rechecks_canonical_evidence_before_persisting_acceptance(self):
        from unittest.mock import patch
        import psycopg
        from layer1.onchain import OnChainIntelligenceEngine
        from layer1.onchain_providers import (
            ProviderResponseReceipt, _ACTIVE_PAGE_RECEIPTS,
            _capture_provider_run_receipts, drain_provider_run_receipts,
        )

        event = self.event()
        block = {
            "network_id": event.network_id, "provider": event.provider,
            "scope": event.scope, "block_number": event.block_number,
            "block_hash": event.block_hash, "block_time": event.block_time,
        }
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id="bnb-smart-chain-mainnet",
            method="eth_getLogs", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=128, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
            endpoint_profile_sha256="ae9831d8c7fdd434108aa17b839f42f5c0ae1ce57069587a04bc0983e422252a",
            tls_peer_certificate_sha256="c" * 64,
        )
        @_capture_provider_run_receipts
        def captured():
            _ACTIVE_PAGE_RECEIPTS.get().append(receipt)
            return drain_provider_run_receipts()

        cursor_key = "alchemy:bnb:contract-acceptance-race"
        self.store.commit_page(
            cursor_key, {"next_block": 101}, [event], expected_cursor=None,
            scope_identity=self.identity, canonical_blocks=(block,),
            provider_receipts=captured(),
        )
        page_id = self.store.conn.execute(
            "SELECT page_id FROM layer1_onchain_ingestion_pages WHERE cursor_key=%s",
            (cursor_key,),
        ).fetchone()[0]
        engine = OnChainIntelligenceEngine(
            receipt_signing_key=b"test-only-onchain-ingestion-page-key-32-bytes",
            receipt_key_id="postgres-ingestion-race-v1",
        )
        original_save = self.store.save_page_acceptance

        def reorg_between_validation_and_save(*args, **kwargs):
            # Commit a concurrent canonical journal change after page material
            # was read, before the acceptance transaction acquires its locks.
            with psycopg.connect(TEST_DSN, autocommit=True) as other:
                other.execute(
                    """UPDATE layer1_onchain_ingestion_blocks SET block_hash=%s
                       WHERE network_id=%s AND provider=%s AND scope=%s AND block_number=%s""",
                    ("c" * 64, event.network_id, event.provider, event.scope, event.block_number),
                )
            return original_save(*args, **kwargs)

        with patch.object(self.store, "save_page_acceptance", side_effect=reorg_between_validation_and_save):
            with self.assertRaisesRegex(ValueError, "canonical block evidence"):
                engine.sign_ingestion_page(self.store, cursor_key, page_id)

        self.assertIsNone(self.store.get_page_acceptance(cursor_key, page_id))
        self.assertEqual(self.store.list_pending_page_acceptances(), ((cursor_key, page_id),))

    def test_verified_asset_mapping_and_observation_round_trip_idempotently(self):
        from layer1.onchain_postgres import PostgresOnChainStore
        from tests.test_onchain_intelligence import OnChainIntelligenceTests
        fixture = OnChainIntelligenceTests()
        fixture.setUp()
        store = PostgresOnChainStore(TEST_DSN, engine=fixture.engine)
        try:
            self.assertEqual(
                store.save_verified(fixture.eligibility, fixture.mapping, fixture.observation),
                "INSERTED",
            )
            self.assertEqual(
                store.save_verified(fixture.eligibility, fixture.mapping, fixture.observation),
                "DUPLICATE",
            )
            self.assertEqual(store.list_verified_mappings("bitcoin-mainnet"), [fixture.mapping])
            self.assertEqual(store.get_latest_accepted_observation(
                fixture.mapping.mapping_id), fixture.observation)
            self.assertEqual(store.get_observation(
                fixture.observation.observation_id)[0], fixture.observation)
        finally:
            store.close()

    def test_ingestion_checkpoint_and_event_survive_fresh_process_reopen(self):
        import subprocess
        import sys
        from pathlib import Path

        event_id = "fresh-process-event-" + os.urandom(8).hex()
        cursor_key = "fresh-process-cursor-" + os.urandom(8).hex()
        event = self.event(event_id=event_id)
        self.store.commit_page(
            cursor_key, {"next_block": 101, "test_marker": cursor_key}, [event],
            expected_cursor=None, scope_identity=self.identity,
        )
        self.store.close()

        child_code = "\n".join((
            "import os, sys",
            "from psycopg.conninfo import conninfo_to_dict",
            "from layer1.onchain_postgres import PostgresOnChainIngestionStore",
            "dsn = os.environ['TEST_POSTGRES_DSN']",
            "info = conninfo_to_dict(dsn)",
            "assert (info.get('dbname') or info.get('database')) == 'binance_onchain_test'",
            "assert info.get('host') == os.environ['TEST_POSTGRES_ALLOWED_HOST']",
            "assert info.get('host') in {'localhost', '127.0.0.1', '::1'} or info.get('sslmode') in {'require', 'verify-ca', 'verify-full'}",
            "store = PostgresOnChainIngestionStore(dsn)",
            "try:",
            "    cursor = store.get_checkpoint(sys.argv[1])",
            "    assert cursor == {'next_block': 101, 'test_marker': sys.argv[1]}, 'checkpoint did not survive reconnect'",
            "    event = store.get_event(sys.argv[2], 'bnb-smart-chain-mainnet', 'alchemy', 'contract:0x' + '1' * 40)",
            "    assert event is not None, 'transfer event did not survive reconnect'",
            "    assert event.amount_raw == '12345' and event.block_number == 100",
            "finally:",
            "    store.close()",
        ))
        try:
            result = subprocess.run(
                [sys.executable, "-c", child_code, cursor_key, event_id],
                cwd=str(Path(__file__).resolve().parents[1]),
                env=os.environ.copy(), capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            from layer1.onchain_postgres import PostgresOnChainIngestionStore
            self.store = PostgresOnChainIngestionStore(TEST_DSN)

    def test_verified_onchain_observation_survives_fresh_process_reopen(self):
        import subprocess
        import sys
        from pathlib import Path

        from layer1.onchain_postgres import PostgresOnChainStore
        from tests.test_onchain_intelligence import OnChainIntelligenceTests

        fixture = OnChainIntelligenceTests()
        fixture.setUp()
        suffix = os.urandom(8).hex()
        fixture.mapping = type(fixture.mapping)(**{
            **fixture.mapping.__dict__, "mapping_id": "fresh-process-mapping-" + suffix,
        })
        fixture.observation = type(fixture.observation)(**{
            **fixture.observation.__dict__,
            "observation_id": "fresh-process-observation-" + suffix,
            "mapping_id": fixture.mapping.mapping_id,
        })
        store = PostgresOnChainStore(TEST_DSN, engine=fixture.engine)
        self.assertEqual(
            store.save_verified(fixture.eligibility, fixture.mapping, fixture.observation),
            "INSERTED",
        )
        observation_id = fixture.observation.observation_id
        mapping_id = fixture.mapping.mapping_id
        store.close()

        child_code = "\n".join((
            "import os, sys",
            "from psycopg.conninfo import conninfo_to_dict",
            "from layer1.onchain_postgres import PostgresOnChainStore",
            "dsn = os.environ['TEST_POSTGRES_DSN']",
            "info = conninfo_to_dict(dsn)",
            "assert (info.get('dbname') or info.get('database')) == 'binance_onchain_test'",
            "assert info.get('host') == os.environ['TEST_POSTGRES_ALLOWED_HOST']",
            "assert info.get('host') in {'localhost', '127.0.0.1', '::1'} or info.get('sslmode') in {'require', 'verify-ca', 'verify-full'}",
            "from layer1.onchain import OnChainIntelligenceEngine",
            "receipt_key = b'test-only-onchain-receipt-key-32-bytes-minimum'",
            "engine = OnChainIntelligenceEngine(receipt_signing_key=receipt_key, receipt_key_id='test-key-v1')",
            "store = PostgresOnChainStore(dsn, engine=engine)",
            "try:",
            "    recovered = store.get_observation(sys.argv[1])",
            "    assert recovered is not None, 'verified on-chain observation missing after reconnect'",
            "    observation, validation = recovered",
            "    assert observation.observation_id == sys.argv[1]",
            "    assert observation.transaction_hash == 'b' * 64",
            "    assert validation.status == 'ACCEPTED'",
            "finally:",
            "    store.close()",
        ))
        result = subprocess.run(
            [sys.executable, "-c", child_code, observation_id],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=os.environ.copy(), capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        cleanup = PostgresOnChainStore(TEST_DSN)
        try:
            with cleanup.conn.transaction():
                cleanup.conn.execute(
                    "DELETE FROM layer1_onchain_observations WHERE observation_id=%s",
                    (observation_id,),
                )
                cleanup.conn.execute(
                    "DELETE FROM layer1_onchain_asset_mappings WHERE mapping_id=%s",
                    (mapping_id,),
                )
        finally:
            cleanup.close()

    def test_event_journal_and_checkpoint_commit_atomically(self):
        block = {
            "network_id": self.identity[0], "provider": self.identity[1],
            "scope": self.identity[2], "block_number": 100,
            "block_hash": "b" * 64, "block_time": "2026-11-11T12:00:00+00:00",
        }
        self.commit({"next_block": 101}, self.event(), blocks=(block,))
        self.assertEqual(self.store.get_checkpoint("alchemy:bnb:contract-1"), {"next_block": 101})
        self.assertEqual(self.store.get_block_hash(*self.identity, 100), "b" * 64)
        self.assertEqual(len(self.store.list_all_events()), 1)

    def test_failure_after_event_insert_rolls_back_event_journal_and_checkpoint(self):
        block = {
            "network_id": self.identity[0], "provider": self.identity[1],
            "scope": self.identity[2], "block_number": 100,
            "block_hash": "b" * 64, "block_time": "2026-11-11T12:00:00+00:00",
        }
        bad_block = {**block, "block_time": "not-a-timestamp"}
        from psycopg.errors import InvalidDatetimeFormat
        with self.assertRaises(InvalidDatetimeFormat):
            self.store.commit_page(
                "alchemy:bnb:contract-1", {"next_block": 101}, [self.event()],
                expected_cursor=None, scope_identity=self.identity,
                canonical_blocks=(bad_block,),
            )
        self.assertIsNone(self.store.get_event("event-1", self.identity[0], *self.identity[1:]))
        self.assertIsNone(self.store.get_checkpoint("alchemy:bnb:contract-1"))
        self.assertIsNone(self.store.get_block_hash(*self.identity, 100))

    def test_same_checkpoint_competing_workers_cannot_commit_overlapping_ranges(self):
        barrier = Barrier(2)
        def worker(next_value):
            from layer1.onchain_postgres import PostgresOnChainIngestionStore
            store = PostgresOnChainIngestionStore(TEST_DSN)
            try:
                barrier.wait()
                return store.commit_page(
                    "alchemy:bnb:contract-1",
                    {"from_block": 100, "to_block": 109, "next_block": next_value}, (),
                    expected_cursor=None, scope_identity=self.identity,
                )
            except Exception as exc:
                return exc
            finally:
                store.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, (110, 110)))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(sum(type(result).__name__ == "StaleCheckpointError" for result in results), 1)

    def test_concurrent_duplicate_event_insert_is_safe_after_checkpoint_conflict_retry(self):
        barrier = Barrier(2)
        def worker():
            from layer1.onchain_postgres import PostgresOnChainIngestionStore, StaleCheckpointError
            store = PostgresOnChainIngestionStore(TEST_DSN)
            try:
                barrier.wait()
                try:
                    return store.commit_page(
                        "alchemy:bnb:contract-1", {"next_block": 101}, [self.event()],
                        expected_cursor=None, scope_identity=self.identity,
                    )
                except StaleCheckpointError:
                    latest = store.get_checkpoint("alchemy:bnb:contract-1")
                    return store.commit_page(
                        "alchemy:bnb:contract-1", {"next_block": 102}, [self.event()],
                        expected_cursor=latest, scope_identity=self.identity,
                    )
            finally:
                store.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(sum(result["inserted"] for result in results), 1)
        self.assertEqual(sum(result["duplicates"] for result in results), 1)
        self.assertEqual(len(self.store.list_all_events()), 1)

    def test_concurrent_duplicate_event_retry_is_idempotent(self):
        first = self.commit({"next_block": 101}, self.event(), expected=None)
        self.assertEqual(first["inserted"], 1)
        duplicate = self.commit({"next_block": 102}, self.event(), expected={"next_block": 101})
        self.assertEqual(duplicate["duplicates"], 1)
        self.assertEqual(len(self.store.list_all_events()), 1)

    def test_canonical_block_hash_conflict_fails_closed(self):
        first = {
            "network_id": self.identity[0], "provider": self.identity[1],
            "scope": self.identity[2], "block_number": 100,
            "block_hash": "b" * 64, "block_time": "2026-11-11T12:00:00+00:00",
        }
        self.commit({"next_block": 101}, blocks=(first,), expected=None)
        conflict = {**first, "block_hash": "c" * 64}
        from layer1.onchain_postgres import CanonicalBlockConflict
        with self.assertRaisesRegex(CanonicalBlockConflict, "canonical block hash conflict"):
            self.commit({"next_block": 102}, blocks=(conflict,), expected={"next_block": 101})
        self.assertEqual(self.store.get_block_hash(*self.identity, 100), "b" * 64)

    def test_reconcile_block_requires_provider_and_scope_lock_identity(self):
        with self.assertRaisesRegex(ValueError, "requires explicit provider and scope"):
            self.store.reconcile_block(self.identity[0], 100, "c" * 64)

    def test_reorg_tombstone_and_recanonicalized_replay_are_atomic(self):
        first_block = {
            "network_id": self.identity[0], "provider": self.identity[1],
            "scope": self.identity[2], "block_number": 100,
            "block_hash": "b" * 64, "block_time": "2026-11-11T12:00:00+00:00",
        }
        self.commit({"next_block": 101}, self.event(), expected=None, blocks=(first_block,))
        self.store.reconcile_block(self.identity[0], 100, "c" * 64, provider=self.identity[1], scope=self.identity[2])
        new_event = self.event(block_hash="c" * 64)
        new_block = {**first_block, "block_hash": "c" * 64}
        self.commit({"next_block": 101}, new_event, expected={"next_block": 101},
                    blocks=(new_block,), allow_recanonicalized=True)
        self.assertEqual(self.store.get_event("event-1", self.identity[0], *self.identity[1:]).canonical_status, "CANONICAL")
        self.assertEqual(self.store.get_block_hash(*self.identity, 100), "c" * 64)

    def test_solana_slot_journal_rejects_non_solana_checkpoint_identity(self):
        slot = {
            "network_id": "solana-mainnet", "provider": "alchemy",
            "scope": self.identity[2], "slot": 50, "produced": True,
            "block_hash": "d" * 64, "block_time": "2026-11-11T12:00:00+00:00",
        }
        with self.assertRaisesRegex(ValueError, "outside checkpoint scope"):
            self.store.commit_page(
                "alchemy:bnb:contract-1", {"next_block": 101}, (),
                expected_cursor=None, scope_identity=self.identity,
                canonical_slots=(slot,),
            )

    def test_bitcoin_worker_and_aggregator_run_against_real_postgres_adapters(self):
        from datetime import datetime, timezone
        from layer1.onchain_aggregation import OnChainTransferAggregator
        from layer1.onchain_bitcoin_worker import BitcoinAddressIngestionWorker
        from layer1.onchain import OnChainIntelligenceEngine
        from layer1.onchain_postgres import PostgresOnChainStore
        from tests.test_onchain_acceptance_receipts import OnChainAcceptanceReceiptTests
        from tests.test_onchain_bitcoin_worker import (
            ADDRESS, FakeBitcoinProvider, history, transaction,
        )

        fixture = OnChainAcceptanceReceiptTests()
        fixture.setUp()
        mapping_store = PostgresOnChainStore(TEST_DSN, engine=fixture.engine)
        try:
            self.assertEqual(
                mapping_store.save_verified(
                    fixture.eligibility, fixture.mapping, fixture.observation,
                ),
                "INSERTED",
            )
            provider = FakeBitcoinProvider()
            record = history()
            provider.pages = {1: ((record,), 1)}
            provider.details = {record.txid: transaction(record)}
            worker = BitcoinAddressIngestionWorker(
                provider, mapping_store, self.store,
                monitored_addresses={fixture.mapping.mapping_id: (ADDRESS,)},
                start_blocks={fixture.mapping.mapping_id: 99},
                minimum_confirmations=6, max_blocks_per_run=5, page_size=1,
                reorg_lookback_blocks=2, retry_attempts=1, sleep=lambda _: None,
                clock=lambda: datetime.now(timezone.utc).replace(microsecond=0),
            )
            worker_result = worker.run_once()
            event = self.store.get_event(
                record.txid + ":0", "bitcoin-mainnet", "alchemy", "address:" + ADDRESS,
            )
            self.assertEqual(worker_result["events_inserted"], 1)
            self.assertIsNotNone(event)
            self.assertEqual(event.canonical_status, "CANONICAL")
            self.assertEqual(
                self.store.get_checkpoint("alchemy:bitcoin-mainnet:address:" + ADDRESS)["next_block"],
                104,
            )

            aggregator = OnChainTransferAggregator(
                mapping_store, minimum_amount_by_mapping={fixture.mapping.mapping_id: "0.0001"},
            )
            aggregator.bind_ingestion_store(self.store)
            aggregate = aggregator.aggregate(
                [event], {fixture.mapping.asset_id: fixture.eligibility},
                now=datetime.now(timezone.utc),
            )
            self.assertEqual(aggregate.deduplicated_events, 0)
            self.assertEqual(aggregate.rejected_events, 0)
            self.assertEqual(len(aggregate.network_summaries), 1)
            self.assertEqual(len(aggregate.qualifying_network_summaries), 1)
            self.assertTrue(aggregate.qualifying_network_summaries[0].threshold_met)
        finally:
            mapping_store.close()
            self.store.conn.execute("""
                TRUNCATE TABLE
                    layer1_onchain_observations,
                    layer1_onchain_asset_mappings,
                    layer1_onchain_transfer_events,
                    layer1_onchain_ingestion_blocks,
                    layer1_onchain_solana_slot_journal,
                    layer1_onchain_ingestion_checkpoints
                RESTART IDENTITY CASCADE
            """)

    def test_evm_worker_and_aggregator_run_against_real_postgres_adapters(self):
        from datetime import datetime, timezone
        from layer1.foundation import EligibilityDecision
        from layer1.onchain import OnChainIntelligenceEngine, OnChainObservation
        from layer1.onchain_aggregation import OnChainTransferAggregator
        from layer1.onchain_evm_worker import EvmTransferIngestionWorker
        from layer1.onchain_postgres import PostgresOnChainStore
        from tests.test_onchain_evm_worker import (
            BLOCK_HASH, CONTRACT, TX_HASH, FakeProvider, mapping,
        )
        from layer1.onchain_providers import EvmTokenTransferLog

        now = datetime.now(timezone.utc).replace(microsecond=0)
        stamp = now.isoformat()
        verified_mapping = mapping()
        eligibility = EligibilityDecision(
            status="ELIGIBLE", asset_id="coingecko:example", symbol="EXAMPLE",
            eligible_pairs=("EXAMPLEUSDT",), verified_at=stamp,
            identity_proof_status="VERIFIED", identity_proof_source="coingecko_coin_tickers",
            identity_proof_verified_at=stamp, identity_proof_source_timestamp=stamp,
            identity_proof_data_hash="a" * 64,
        )
        observation = OnChainObservation(
            observation_id="bnb-map-proof-pg", mapping_id=verified_mapping.mapping_id,
            asset_id=verified_mapping.asset_id, network_id=verified_mapping.network_id,
            chain_id="56", provider="alchemy", endpoint_id="bnb-mainnet-rpc",
            observation_type="TRANSFER", block_height=100, block_hash=BLOCK_HASH,
            transaction_hash=TX_HASH, block_time=stamp, observed_at=stamp,
            finality="FINALIZED", finality_reference="eth_getFinalizedHeader",
        )
        engine = OnChainIntelligenceEngine(
            freshness_limits_seconds={"bnb-smart-chain-mainnet": 30 * 86400},
            receipt_signing_key=b"test-only-onchain-receipt-key-32-bytes-minimum",
            receipt_key_id="test-key-v1",
        )
        mapping_store = PostgresOnChainStore(TEST_DSN, engine=engine)
        try:
            self.assertEqual(mapping_store.save_verified(eligibility, verified_mapping, observation), "INSERTED")
            provider = FakeProvider()
            provider.logs = [EvmTokenTransferLog(
                network_id="bnb-smart-chain-mainnet", contract_address=CONTRACT,
                from_address="0x" + "2" * 40, to_address="0x" + "3" * 40,
                amount_raw="12345678901234567890", block_number=109,
                block_hash=BLOCK_HASH, transaction_hash=TX_HASH, log_index=4, removed=False,
            )]
            worker = EvmTransferIngestionWorker(
                provider, mapping_store, self.store,
                start_blocks={verified_mapping.mapping_id: 100},
                max_blocks_per_run=10, reorg_lookback_blocks=2,
                retry_attempts=1, sleep=lambda _: None, clock=lambda: now,
            )
            result = worker.run_once()
            event = self.store.get_event(
                TX_HASH + ":4", verified_mapping.network_id, "alchemy",
                "contract:" + CONTRACT.lower(),
            )
            self.assertEqual(result["events_inserted"], 1)
            self.assertIsNotNone(event)
            self.assertEqual(event.canonical_status, "CANONICAL")
            self.assertEqual(
                self.store.get_checkpoint("alchemy:bnb-smart-chain-mainnet:contract:" + CONTRACT.lower())["next_block"],
                110,
            )
            aggregator = OnChainTransferAggregator(
                mapping_store, minimum_amount_by_mapping={verified_mapping.mapping_id: "0.1"},
            )
            aggregator.bind_ingestion_store(self.store)
            aggregate = aggregator.aggregate([event], {verified_mapping.asset_id: eligibility}, now=now)
            self.assertEqual(aggregate.rejected_events, 0)
            self.assertEqual(len(aggregate.qualifying_network_summaries), 1)
            self.assertTrue(aggregate.qualifying_network_summaries[0].threshold_met)
        finally:
            mapping_store.close()
            self.store.conn.execute("""
                TRUNCATE TABLE
                    layer1_onchain_observations,
                    layer1_onchain_asset_mappings,
                    layer1_onchain_transfer_events,
                    layer1_onchain_ingestion_blocks,
                    layer1_onchain_solana_slot_journal,
                    layer1_onchain_ingestion_checkpoints
                RESTART IDENTITY CASCADE
            """)

    def test_solana_worker_and_aggregator_run_against_real_postgres_adapters(self):
        from datetime import datetime, timedelta, timezone
        from layer1.foundation import EligibilityDecision
        from layer1.onchain import OnChainAssetMapping, OnChainIntelligenceEngine, OnChainObservation
        from layer1.onchain_aggregation import OnChainTransferAggregator
        from layer1.onchain_postgres import PostgresOnChainStore
        from layer1.onchain_solana_worker import SolanaAddressIngestionWorker
        from tests.test_onchain_solana_worker import FakeSolanaProvider, history
        from tests.test_solana_normalization import MINT, WALLET, BLOCKHASH, SIGNATURE

        now = datetime.now(timezone.utc).replace(microsecond=0)
        stamp = now.isoformat()
        mapping = OnChainAssetMapping(
            "pg-solana-usdc-v1", "coingecko:usd-coin", "USDC", "solana-mainnet",
            "SOLANA", "mainnet-beta", "TOKEN", MINT, "SPL_TOKEN", 6,
            "VERIFIED", "OFFICIAL_PROJECT", "https://solana.com",
            (now - timedelta(hours=2)).isoformat(),
        )
        eligibility = EligibilityDecision(
            status="ELIGIBLE", asset_id="coingecko:usd-coin", symbol="USDC",
            eligible_pairs=("USDCUSDT",), verified_at=stamp,
            identity_proof_status="VERIFIED", identity_proof_source="coingecko_coin_tickers",
            identity_proof_verified_at=stamp, identity_proof_source_timestamp=stamp,
            identity_proof_data_hash="a" * 64,
        )
        observation = OnChainObservation(
            "pg-solana-map-proof", mapping.mapping_id, mapping.asset_id, mapping.network_id,
            "mainnet-beta", "alchemy", "solana-mainnet", "TRANSFER", 290,
            BLOCKHASH, SIGNATURE, stamp, stamp, "FINALIZED", "commitment=finalized",
        )
        engine = OnChainIntelligenceEngine(
            freshness_limits_seconds={"solana-mainnet": 30 * 86400},
            receipt_signing_key=b"test-only-onchain-receipt-key-32-bytes-minimum",
            receipt_key_id="test-key-v1",
        )
        mapping_store = PostgresOnChainStore(TEST_DSN, engine=engine)
        try:
            self.assertEqual(mapping_store.save_verified(eligibility, mapping, observation), "INSERTED")
            provider = FakeSolanaProvider()
            provider.pages = {None: ((history(),), None)}
            worker = SolanaAddressIngestionWorker(
                provider, mapping_store, self.store,
                monitored_addresses={mapping.mapping_id: (WALLET,)},
                start_slots={mapping.mapping_id: 300}, max_slots_per_run=5,
                page_size=100, reorg_lookback_slots=5, retry_attempts=1,
                sleep=lambda _: None, clock=lambda: now,
            )
            result = worker.run_once()
            scope = f"address:{WALLET}:mapping:{mapping.mapping_id}"
            event = self.store.get_event(
                SIGNATURE + ":outer:0", "solana-mainnet", "alchemy", scope,
            )
            self.assertEqual(result["events_inserted"], 1)
            self.assertIsNotNone(event)
            self.assertEqual(event.canonical_status, "CANONICAL")
            journal = self.store.get_solana_slot_journal(
                "solana-mainnet", "alchemy", scope, 300, 304,
            )
            self.assertEqual(set(journal), set(range(300, 305)))
            self.assertTrue(all(item["produced"] for item in journal.values()))
            aggregator = OnChainTransferAggregator(
                mapping_store, minimum_amount_by_mapping={mapping.mapping_id: "1"},
            )
            aggregator.bind_ingestion_store(self.store)
            aggregate = aggregator.aggregate([event], {mapping.asset_id: eligibility}, now=now)
            self.assertEqual(aggregate.rejected_events, 0)
            self.assertEqual(len(aggregate.qualifying_network_summaries), 1)
            self.assertTrue(aggregate.qualifying_network_summaries[0].threshold_met)
        finally:
            mapping_store.close()
            self.store.conn.execute("""
                TRUNCATE TABLE
                    layer1_onchain_observations,
                    layer1_onchain_asset_mappings,
                    layer1_onchain_transfer_events,
                    layer1_onchain_ingestion_blocks,
                    layer1_onchain_solana_slot_journal,
                    layer1_onchain_ingestion_checkpoints
                RESTART IDENTITY CASCADE
            """)

    def test_xrpl_worker_and_aggregator_run_against_real_postgres_adapters(self):
        from datetime import datetime, timedelta, timezone
        from layer1.foundation import EligibilityDecision
        from layer1.onchain import OnChainAssetMapping, OnChainIntelligenceEngine, OnChainObservation
        from layer1.onchain_aggregation import OnChainTransferAggregator
        from layer1.onchain_postgres import PostgresOnChainStore
        from layer1.onchain_xrpl_worker import XrplIssuedCurrencyIngestionWorker
        from tests.test_onchain_xrpl_worker import (
            ACCOUNT, ISSUER, TX_HASH, BLOCK_HASH, FakeXrplProvider, record,
        )

        now = datetime.now(timezone.utc).replace(microsecond=0)
        stamp = now.isoformat()
        mapping = OnChainAssetMapping(
            "pg-xrpl-usdc-v1", "coingecko:usd-coin", "USDC", "xrpl-mainnet",
            "XRPL", "xrpl-mainnet", "TOKEN", None, "XRPL_ISSUED_CURRENCY", 6,
            "VERIFIED", "OFFICIAL_PROJECT", "https://xrpl.org",
            (now - timedelta(hours=2)).isoformat(), issuer_address=ISSUER, issued_currency="USD",
        )
        eligibility = EligibilityDecision(
            status="ELIGIBLE", asset_id="coingecko:usd-coin", symbol="USDC",
            eligible_pairs=("USDCUSDT",), verified_at=stamp,
            identity_proof_status="VERIFIED", identity_proof_source="coingecko_coin_tickers",
            identity_proof_verified_at=stamp, identity_proof_source_timestamp=stamp,
            identity_proof_data_hash="a" * 64,
        )
        observation = OnChainObservation(
            "pg-xrpl-map-proof", mapping.mapping_id, mapping.asset_id, mapping.network_id,
            "xrpl-mainnet", "chainstack", "xrpl-mainnet", "TRANSFER", 499,
            BLOCK_HASH, TX_HASH, stamp, stamp, "FINALIZED", "validated_ledger=true",
        )
        engine = OnChainIntelligenceEngine(
            freshness_limits_seconds={"xrpl-mainnet": 30 * 86400},
            receipt_signing_key=b"test-only-onchain-receipt-key-32-bytes-minimum",
            receipt_key_id="test-key-v1",
        )
        mapping_store = PostgresOnChainStore(TEST_DSN, engine=engine)
        try:
            self.assertEqual(mapping_store.save_verified(eligibility, mapping, observation), "INSERTED")
            provider = FakeXrplProvider()
            provider.pages = {None: ((record(),), None)}
            worker = XrplIssuedCurrencyIngestionWorker(
                provider, mapping_store, self.store,
                monitored_accounts={mapping.mapping_id: (ACCOUNT,)},
                start_ledgers={mapping.mapping_id: 500}, max_ledgers_per_run=3,
                page_size=10, max_pages_per_run=1, reorg_lookback_ledgers=3,
                retry_attempts=1, sleep=lambda _: None, clock=lambda: now,
            )
            result = worker.run_once()
            scope = f"account:{ACCOUNT}:mapping:{mapping.mapping_id}"
            event = self.store.get_event(TX_HASH.lower(), "xrpl-mainnet", "chainstack", scope)
            self.assertEqual(result["events_inserted"], 1)
            self.assertIsNotNone(event)
            self.assertEqual(event.canonical_status, "CANONICAL")
            aggregator = OnChainTransferAggregator(
                mapping_store, minimum_amount_by_mapping={mapping.mapping_id: "1"},
            )
            aggregator.bind_ingestion_store(self.store)
            aggregate = aggregator.aggregate([event], {mapping.asset_id: eligibility}, now=now)
            self.assertEqual(aggregate.rejected_events, 0)
            self.assertEqual(len(aggregate.qualifying_network_summaries), 1)
            self.assertTrue(aggregate.qualifying_network_summaries[0].threshold_met)
        finally:
            mapping_store.close()
            self.store.conn.execute("""
                TRUNCATE TABLE
                    layer1_onchain_observations,
                    layer1_onchain_asset_mappings,
                    layer1_onchain_transfer_events,
                    layer1_onchain_ingestion_blocks,
                    layer1_onchain_solana_slot_journal,
                    layer1_onchain_ingestion_checkpoints
                RESTART IDENTITY CASCADE
            """)

    def test_solana_slot_journal_persists_produced_state_consistently(self):
        slot = {
            "network_id": "solana-mainnet", "provider": "alchemy",
            "scope": "wallet:test", "slot": 50, "produced": True,
            "block_hash": "d" * 64, "block_time": "2026-11-11T12:00:00+00:00",
        }
        self.store.commit_page(
            "solana:wallet:test", {"next_slot": 51}, (),
            expected_cursor=None, scope_identity=("solana-mainnet", "alchemy", "wallet:test"),
            canonical_slots=(slot,),
        )
        saved = self.store.get_solana_slot_journal("solana-mainnet", "alchemy", "wallet:test", 50, 50)
        self.assertEqual(saved[50]["block_hash"], "d" * 64)


if __name__ == "__main__":
    unittest.main()


class PostgresInvalidationQueueContractTests(unittest.TestCase):
    def test_postgres_invalidated_page_queue_returns_immutable_signature_and_reason(self):
        from layer1.onchain_postgres import PostgresOnChainIngestionStore
        affected = [{"network_id": "bnb-smart-chain-mainnet", "block_number": 100,
                     "canonical_block_hash": "b" * 64, "current_canonical_hash": "c" * 64}]
        class Result:
            def fetchall(self):
                return [("cursor", "a" * 64, "CANONICAL_EVIDENCE_REORGED", affected,
                         "2026-11-27T00:00:00+00:00", "key-v1", "d" * 64, "e" * 64,
                         {"page_id": "a" * 64, "domain": "BINANCE_SQUARE_W2E_ONCHAIN_INGESTION_PAGE_V1"},
                         "2026-11-26T23:59:00+00:00")]
        class Connection:
            def execute(self, query):
                self.query = query
                return Result()
        store = object.__new__(PostgresOnChainIngestionStore)
        store.conn = Connection()
        item, = store.list_invalidated_page_acceptances()
        self.assertEqual(item["status"], "INVALIDATED")
        self.assertEqual(item["reason_code"], "CANONICAL_EVIDENCE_REORGED")
        self.assertEqual(item["signature"], "e" * 64)
        self.assertEqual(item["payload_json"]["page_id"], "a" * 64)
        self.assertEqual(item["accepted_at"], "2026-11-26T23:59:00+00:00")
        self.assertEqual(item["affected_evidence"], affected)


class PostgresRecanonicalizationInvalidationContractTests(unittest.TestCase):
    def test_postgres_recanonicalization_helper_persists_old_and_new_block_hashes(self):
        from layer1.onchain_postgres import PostgresOnChainIngestionStore
        identity = ["bnb-smart-chain-mainnet", "alchemy", "contract:0x" + "1" * 40]
        material = {"scope_identity": identity, "events": [], "canonical_blocks": [{
            "network_id": identity[0], "provider": identity[1], "scope": identity[2],
            "block_number": 100, "block_hash": "b" * 64,
            "block_time": "2026-11-11T12:00:00+00:00",
        }], "canonical_slots": []}
        class Result:
            def __init__(self, rows=()): self.rows = rows
            def fetchall(self): return self.rows
        class Connection:
            def __init__(self): self.insert = None
            def execute(self, query, params=()):
                if "SELECT p.page_id, p.page_material_json" in query:
                    self.selection = (query, params)
                    return Result([("page-id", material)])
                if "INSERT INTO layer1_onchain_ingestion_page_acceptance_lifecycle" in query:
                    self.insert = (query, params)
                    return Result()
                raise AssertionError("unexpected SQL in invalidation contract")
        store = object.__new__(PostgresOnChainIngestionStore)
        store.conn = Connection()
        store._jsonb = lambda value: value
        changed = store._invalidate_page_acceptances_for_reorg(
            identity[0], identity[1], identity[2], 100, "c" * 64,
        )
        self.assertEqual(changed, 1)
        query, params = store.conn.insert
        self.assertIn("CANONICAL_EVIDENCE_REORGED", query)
        self.assertEqual(params[0], "page-id")
        self.assertEqual(params[1][0]["canonical_block_hash"], "b" * 64)
        self.assertEqual(params[1][0]["current_canonical_hash"], "c" * 64)


class PostgresLegacyReceiptFingerprintAcceptanceTests(unittest.TestCase):
    def test_postgres_page_material_rejects_legacy_receipt_without_endpoint_profile_fingerprint(self):
        import hashlib
        from layer1.onchain_ingestion import OnChainIngestionStore
        from layer1.onchain_postgres import PostgresOnChainIngestionStore
        from layer1.onchain_providers import ProviderResponseReceipt
        identity = ["ethereum-mainnet", "alchemy", "contract:0x" + "1" * 40]
        material = {
            "cursor_key": "alchemy:ethereum:legacy-profile",
            "scope_identity": identity, "events": [], "canonical_blocks": [{
                "network_id": identity[0], "provider": identity[1], "scope": identity[2],
                "block_number": 10, "block_hash": "b" * 64,
                "block_time": "2026-11-11T12:00:00+00:00",
            }], "canonical_slots": [],
        }
        receipt = ProviderResponseReceipt(
            sequence=1, provider="alchemy", network_id=identity[0],
            method="eth_chainId", request_sha256="a" * 64,
            response_sha256="b" * 64, response_bytes=32, http_status=200,
            received_at="2026-11-26T12:00:00+00:00",
        )
        receipts = [receipt.__dict__]
        receipts_json = OnChainIngestionStore._canonical(receipts)
        receipt_digest = hashlib.sha256(receipts_json.encode("utf-8")).hexdigest()
        page_id = hashlib.sha256(OnChainIngestionStore._canonical(material).encode("utf-8")).hexdigest()
        class Result:
            def fetchone(self): return (material["cursor_key"], material, receipt_digest, receipts)
        class Connection:
            def execute(self, query, params): return Result()
        store = object.__new__(PostgresOnChainIngestionStore)
        store.conn = Connection()
        with self.assertRaisesRegex(ValueError, "endpoint profile fingerprint"):
            store.get_page_acceptance_material(material["cursor_key"], page_id)


class PostgresLatestObservationOrderingIntegrityTests(unittest.TestCase):
    def test_latest_accepted_observation_orders_by_signed_payload_timestamp(self):
        from dataclasses import asdict, replace
        from datetime import datetime
        from layer1.onchain import OnChainValidationResult
        from layer1.onchain_postgres import PostgresOnChainStore
        from tests.test_onchain_intelligence import OnChainIntelligenceTests

        fixture = OnChainIntelligenceTests()
        fixture.setUp()
        mapping = fixture.mapping
        older = fixture.observation
        newer = replace(
            older, observation_id=older.observation_id + "-newer",
            observed_at="2027-01-01T12:00:00+00:00",
        )
        # Simulate a corrupted denormalized SQL column: the older signed JSON
        # payload is made to sort ahead of the newer signed JSON payload.
        denormalized_sort_keys = {
            older.observation_id: "2027-12-31T00:00:00+00:00",
            newer.observation_id: "2020-01-01T00:00:00+00:00",
        }
        validation = OnChainValidationResult(
            status="ACCEPTED", reason_code="ACCEPTED", reason="fixture",
            observation_id=older.observation_id, asset_id=older.asset_id,
            mapping_id=older.mapping_id, network_id=older.network_id,
            provider=older.provider, provenance_cursor_key="cursor",
            provenance_page_id="a" * 64, provenance_observation_id=older.observation_id,
        )
        newer_validation = replace(
            validation, observation_id=newer.observation_id,
            provenance_observation_id=newer.observation_id,
        )
        malformed = replace(
            older, observation_id=older.observation_id + "-malformed",
            observed_at="not-an-iso-timestamp",
        )
        malformed_validation = replace(
            validation, observation_id=malformed.observation_id,
            provenance_observation_id=malformed.observation_id,
        )
        observation_rows = [
            (asdict(older), asdict(validation)),
            (asdict(newer), asdict(newer_validation)),
            (asdict(malformed), asdict(malformed_validation)),
        ]
        denormalized_sort_keys[malformed.observation_id] = "2030-01-01T00:00:00+00:00"

        class Result:
            def __init__(self, rows): self.rows = rows
            def fetchall(self): return self.rows
            def fetchone(self): return self.rows[0] if self.rows else None

        class Connection:
            def execute(self, query, params=()):
                if "FROM layer1_onchain_observations" in query:
                    if "payload_json->>'observed_at'" in query:
                        rows = sorted(
                            observation_rows,
                            key=lambda row: datetime.fromisoformat(row[0]["observed_at"].replace("Z", "+00:00")),
                            reverse=True,
                        )
                    else:
                        rows = sorted(
                            observation_rows,
                            key=lambda row: denormalized_sort_keys[row[0]["observation_id"]],
                            reverse=True,
                        )
                    return Result(rows)
                if "FROM layer1_onchain_asset_mappings" in query:
                    return Result([(asdict(mapping),)])
                raise AssertionError("unexpected SQL in latest-observation ordering test")

        class Engine:
            def verify_persisted_acceptance_receipt(self, observation, validation): return True
            def verify_observation_provenance(self, ingestion_store, provenance, mapping, observation): return True

        store = object.__new__(PostgresOnChainStore)
        store.conn = Connection()
        store.engine = Engine()
        store.ingestion_store = object()

        result = store.get_latest_accepted_observation(mapping.mapping_id)
        self.assertEqual(result.observation_id, newer.observation_id)


class PostgresMappingProjectionIntegrityTests(unittest.TestCase):
    def test_postgres_verified_mapping_list_rejects_denormalized_identity_mismatch(self):
        from dataclasses import asdict
        from layer1.onchain_postgres import PostgresOnChainStore
        from tests.test_onchain_intelligence import OnChainIntelligenceTests

        fixture = OnChainIntelligenceTests()
        fixture.setUp()
        mapping = fixture.mapping
        class Result:
            def fetchall(self):
                return [(mapping.mapping_id, mapping.asset_id, "ethereum-mainnet", asdict(mapping))]
        class Connection:
            def execute(self, query, params=()): return Result()
        class Engine:
            @staticmethod
            def _validate_mapping(value): return None
        store = object.__new__(PostgresOnChainStore)
        store.conn = Connection()
        store.engine = Engine()
        self.assertEqual(store.list_verified_mappings("ethereum-mainnet"), [])
