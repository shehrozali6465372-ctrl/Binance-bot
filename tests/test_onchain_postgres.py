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


def _dedicated_local_test_dsn():
    if not TEST_DSN:
        return False
    from psycopg.conninfo import conninfo_to_dict
    info = conninfo_to_dict(TEST_DSN)
    host = info.get("host", "")
    database = info.get("dbname") or info.get("database")
    hostaddr = info.get("hostaddr", "")
    local_host = host in {"localhost", "127.0.0.1", "::1"} or host.startswith("/")
    allowed_remote_host = os.environ.get("TEST_POSTGRES_ALLOWED_HOST", "").strip()
    remote_host_allowed = (
        bool(allowed_remote_host) and host == allowed_remote_host
        and info.get("sslmode") in {"require", "verify-ca", "verify-full"}
    )
    local_hostaddr = not hostaddr or hostaddr in {"127.0.0.1", "::1"}
    if (database != "binance_onchain_test" or not (local_host or remote_host_allowed)
            or not local_hostaddr or info.get("service")):
        raise RuntimeError(
            "TEST_POSTGRES_DSN must target binance_onchain_test on localhost or an exact "
            "TEST_POSTGRES_ALLOWED_HOST with TLS"
        )
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
        }.issubset(names))

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
