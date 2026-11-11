import hashlib
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from layer1.foundation import (
    AssetIdentity, CandidateDiscoveryFilteringEngine, EligibilityDecision, MarketObservation,
)
from layer1.onchain import OnChainAssetMapping, OnChainIntelligenceEngine, OnChainObservation, OnChainStore
from layer1.onchain_ingestion import NormalizedTransferEvent, OnChainIngestionStore
from layer1.onchain_aggregation import OnChainTransferAggregator

NOW = datetime(2026, 11, 11, 17, 0, tzinfo=timezone.utc)
ASSET = "coingecko:bitcoin"
TX1 = "a" * 64
BLOCK = "b" * 64


def eligibility(stamp=None, **overrides):
    stamp = stamp or (NOW - timedelta(minutes=2)).isoformat()
    values = dict(
        status="ELIGIBLE", asset_id=ASSET, symbol="BTC", eligible_pairs=("BTCUSDT",),
        verified_at=stamp, source="https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT",
        identity_proof_status="VERIFIED", identity_proof_source="coingecko_coin_tickers",
        identity_proof_verified_at=stamp, identity_proof_source_timestamp=stamp,
        identity_proof_data_hash="a" * 64,
    )
    values.update(overrides)
    return EligibilityDecision(**values)


def mapping(network, mapping_id, decimals, representation="NATIVE"):
    common = dict(
        mapping_id=mapping_id, asset_id=ASSET, binance_symbol="BTC", network_id=network,
        mapping_status="VERIFIED", source_type="OFFICIAL_PROJECT",
        source_url="https://bitcoin.org/", verified_at=(NOW - timedelta(minutes=10)).isoformat(),
        decimals=decimals,
    )
    if network == "solana-mainnet":
        return OnChainAssetMapping(**common, network_family="SOLANA", chain_id="mainnet-beta",
                                   representation="TOKEN", contract_address="4" * 44,
                                   token_standard="SPL_TOKEN")
    if network == "bitcoin-mainnet":
        return OnChainAssetMapping(**common, network_family="UTXO", chain_id="bitcoin-mainnet",
                                   representation="NATIVE", contract_address=None, token_standard=None)
    if network == "ethereum-mainnet":
        return OnChainAssetMapping(**common, network_family="EVM", chain_id="1",
                                   representation="WRAPPED", contract_address="0x" + "1" * 40,
                                   token_standard="ERC20")
    raise AssertionError(network)


def observation(asset_mapping, suffix="1"):
    stamp = (NOW - timedelta(minutes=10)).isoformat()
    network = asset_mapping.network_id
    if network == "solana-mainnet":
        provider, finality, reference, tx_hash = "alchemy", "FINALIZED", "commitment=finalized", "2" * 88
        block_hash = "3" * 44
    elif network == "bitcoin-mainnet":
        provider, finality, reference, tx_hash = "alchemy", "CONFIRMED", "confirmations=6", "c" * 64
        block_hash = "d" * 64
    else:
        provider, finality, reference, tx_hash = "alchemy", "FINALIZED", "eth_getBlockByNumber:finalized", "0x" + "c" * 64
        block_hash = "0x" + "d" * 64
    return OnChainObservation(
        observation_id=f"{asset_mapping.mapping_id}-observation-{suffix}",
        mapping_id=asset_mapping.mapping_id, asset_id=asset_mapping.asset_id,
        network_id=network, chain_id=asset_mapping.chain_id, provider=provider,
        endpoint_id=network, observation_type="TRANSFER", block_height=100,
        block_hash=block_hash, transaction_hash=tx_hash, block_time=stamp,
        observed_at=stamp, finality=finality, finality_reference=reference,
    )


def event(mapping_obj, *, event_id, amount_raw, tx_hash=None, scope="account:one", status="CANONICAL", event_index=0):
    network = mapping_obj.network_id
    stamp = (NOW - timedelta(minutes=5)).isoformat()
    if network == "solana-mainnet":
        provider, block_hash, transaction_hash = "alchemy", "3" * 44, tx_hash or "2" * 88
    elif network == "bitcoin-mainnet":
        provider, block_hash = "alchemy", "d" * 64
        if isinstance(event_id, str) and __import__("re").fullmatch(r"[0-9a-fA-F]{64}:\d+", event_id):
            transaction_hash = tx_hash or event_id.rsplit(":", 1)[0]
        else:
            transaction_hash = tx_hash or hashlib.sha256(event_id.encode()).hexdigest()
            event_id = f"{transaction_hash}:0"
    elif network == "xrpl-mainnet":
        provider, block_hash, transaction_hash = "chainstack", "e" * 64, tx_hash or "c" * 64
    else:
        provider, block_hash, transaction_hash = "alchemy", "0x" + "d" * 64, tx_hash or "0x" + "c" * 64
    return NormalizedTransferEvent(
        event_id=event_id, network_id=network, provider=provider, scope=scope,
        asset_id=mapping_obj.asset_id, mapping_id=mapping_obj.mapping_id,
        transaction_hash=transaction_hash, block_number=100, block_hash=block_hash,
        event_index=event_index, from_address="sender-1", to_address="receiver-1",
        amount_raw=amount_raw, decimals=mapping_obj.decimals, block_time=stamp,
        observed_at=stamp, canonical_status=status, provenance="deterministic-test",
    )


class OnChainTransferAggregatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self.tmp.name, "onchain.sqlite3")
        self.mapping_store = OnChainStore(path, OnChainIntelligenceEngine(
            {"bitcoin-mainnet": 86400, "ethereum-mainnet": 86400, "solana-mainnet": 86400, "xrpl-mainnet": 86400},
            minimum_confirmations_by_network={"bitcoin-mainnet": 6}))
        self.ingestion_store = OnChainIngestionStore(path)
        self.btc = mapping("bitcoin-mainnet", "btc-native-v1", 8)
        self.wbtc = mapping("ethereum-mainnet", "wbtc-ethereum-v1", 18, "WRAPPED")
        self.sol = mapping("solana-mainnet", "sol-btc-v1", 8, "TOKEN")
        self.decision = eligibility()
        self.mapping_store.save_verified(self.decision, self.btc, observation(self.btc))
        self.mapping_store.save_verified(self.decision, self.wbtc, observation(self.wbtc))
        self.mapping_store.save_verified(self.decision, self.sol, observation(self.sol))
        self.aggregator = OnChainTransferAggregator(
            self.mapping_store,
            minimum_amount_by_mapping={"btc-native-v1": "0.75", "wbtc-ethereum-v1": "0.75", "sol-btc-v1": "0.75"},
            eligibility_max_age_seconds=300, identity_proof_max_age_seconds=900,
        )

    def bind_events(self, events, *, persist_events=True, persist_blocks=True):
        blocks = {}
        for row in events:
            blocks[(row.network_id, row.provider, row.scope, row.block_number)] = {
                "network_id": row.network_id, "provider": row.provider, "scope": row.scope,
                "block_number": row.block_number, "block_hash": row.block_hash,
                "block_time": row.block_time,
            }
        self.ingestion_store.commit_page(
            "test-block-journal", {"test": True}, tuple(events) if persist_events else (),
            canonical_blocks=tuple(blocks.values()) if persist_blocks else ())
        self.aggregator.bind_ingestion_store(self.ingestion_store)

    def tearDown(self):
        self.ingestion_store.close()
        self.mapping_store.close()
        self.tmp.cleanup()

    def test_groups_asset_across_networks_but_keeps_units_and_thresholds_network_specific(self):
        events = [
            event(self.btc, event_id="btc-out:0", amount_raw="100000000"),
            event(self.wbtc, event_id="0x" + "c" * 64 + ":1", amount_raw="500000000000000000", event_index=1),
        ]
        self.bind_events(events)
        result = self.aggregator.aggregate(events, {ASSET: self.decision}, now=NOW)
        self.assertEqual(len(result.assets), 1)
        self.assertEqual(result.assets[0].network_count, 2)
        by_network = {row.network_id: row for row in result.network_summaries}
        self.assertEqual(by_network["bitcoin-mainnet"].total_amount, "1")
        self.assertTrue(by_network["bitcoin-mainnet"].threshold_met)
        self.assertEqual(by_network["ethereum-mainnet"].total_amount, "0.5")
        self.assertFalse(by_network["ethereum-mainnet"].threshold_met)
        self.assertIsNone(result.cross_network_total_amount)
        self.assertEqual(len(result.qualifying_network_summaries), 1)
        self.assertEqual(len(result.qualifying_assets), 1)
        self.assertEqual(result.assets[0].observation_count, 2)
        self.assertRegex(result.network_summaries[0].summary_id, r"^[0-9a-f]{64}$")

    def test_deduplicates_same_xrpl_payment_across_account_scopes_but_not_distinct_evm_logs(self):
        xrpl = OnChainAssetMapping(
            "xrpl-btc-v1", ASSET, "BTC", "xrpl-mainnet", "XRPL", "xrpl-mainnet",
            "TOKEN", None, "XRPL_ISSUED_CURRENCY", 8, "VERIFIED", "OFFICIAL_PROJECT",
            "https://xrpl.org", (NOW - timedelta(minutes=10)).isoformat(),
            issuer_address="rIssuerExample", issued_currency="BTC")
        stamp = (NOW - timedelta(minutes=10)).isoformat()
        xrpl_obs = OnChainObservation("xrpl-proof", xrpl.mapping_id, ASSET, "xrpl-mainnet", "xrpl-mainnet",
            "chainstack", "xrpl-mainnet", "TRANSFER", 100, "e" * 64, "f" * 64,
            stamp, stamp, "FINALIZED", "validated_ledger=true")
        self.mapping_store.save_verified(self.decision, xrpl, xrpl_obs)
        aggregator = OnChainTransferAggregator(
            self.mapping_store,
            minimum_amount_by_mapping={"btc-native-v1": "0.1", "wbtc-ethereum-v1": "0.1", "sol-btc-v1": "0.1", "xrpl-btc-v1": "0.1"},
            eligibility_max_age_seconds=300, identity_proof_max_age_seconds=900)
        pay = event(xrpl, event_id="f" * 64, tx_hash="f" * 64, amount_raw="25000000")
        pay2 = NormalizedTransferEvent(**{**pay.__dict__, "scope": "account:two", "observed_at": NOW.isoformat()})
        evm1 = event(self.wbtc, event_id="0x" + "c" * 64 + ":1", amount_raw="100000000000000000", event_index=1)
        evm2 = event(self.wbtc, event_id="0x" + "c" * 64 + ":2", amount_raw="200000000000000000", event_index=2)
        self.bind_events([pay, pay2, evm1, evm2])
        aggregator.bind_ingestion_store(self.ingestion_store)
        result = aggregator.aggregate([pay, pay2, evm1, evm2], {ASSET: self.decision}, now=NOW)
        rows = {row.mapping_id: row for row in result.network_summaries}
        self.assertEqual(rows["xrpl-btc-v1"].transfer_count, 1)
        self.assertEqual(rows["xrpl-btc-v1"].total_amount, "0.25")
        self.assertEqual(rows["wbtc-ethereum-v1"].transfer_count, 2)
        self.assertEqual(rows["wbtc-ethereum-v1"].total_amount, "0.3")
        self.assertEqual(result.deduplicated_events, 1)

    def test_binance_spot_eligibility_is_mandatory_and_fresh(self):
        event_row = event(self.btc, event_id="btc-out:0", amount_raw="100000000")
        for decision in (
            EligibilityDecision("INELIGIBLE", ASSET, "BTC"),
            eligibility(identity_proof_status="UNVERIFIED"),
            eligibility(source="https://example.com/exchangeInfo"),
            eligibility(verified_at=(NOW - timedelta(hours=2)).isoformat()),
            eligibility(identity_proof_source_timestamp=(NOW - timedelta(hours=2)).isoformat()),
        ):
            with self.subTest(decision=decision):
                self.bind_events([event_row])
                result = self.aggregator.aggregate([event_row], {ASSET: decision}, now=NOW)
                self.assertEqual(result.network_summaries, ())
                self.assertGreaterEqual(result.rejected_events, 1)

    def test_missing_eligibility_decision_does_not_emit_a_signal(self):
        rows = [event(self.btc, event_id="btc-out:0", amount_raw="100000000")]
        self.bind_events(rows)
        result = self.aggregator.aggregate(rows, {}, now=NOW)
        self.assertEqual(result.network_summaries, ())
        self.assertEqual(result.rejected_events, 1)

    def test_noncanonical_events_are_excluded(self):
        rows = [event(self.btc, event_id="btc-out:0", amount_raw="100000000", status="REORGED")]
        self.bind_events(rows)
        result = self.aggregator.aggregate(rows, {ASSET: self.decision}, now=NOW)
        self.assertEqual(result.network_summaries, ())
        self.assertEqual(result.rejected_events, 1)

    def test_wrong_mapping_decimals_or_malformed_raw_amount_fail_closed(self):
        rows = [
            event(self.btc, event_id="bad-decimals", amount_raw="100000000").__class__(
                **{**event(self.btc, event_id="bad-decimals", amount_raw="100000000").__dict__, "decimals": 18}),
            event(self.btc, event_id="bad-raw", amount_raw="1.2"),
            NormalizedTransferEvent(**{**event(self.btc, event_id="wrong-asset", amount_raw="100").__dict__, "asset_id": "coingecko:other"}),
        ]
        for row in rows:
            with self.subTest(row=row.event_id):
                self.bind_events([row], persist_events=(row.amount_raw != "1.2"))
                with self.assertRaises(ValueError):
                    self.aggregator.aggregate([row], {ASSET: self.decision}, now=NOW)

    def test_thresholds_must_be_explicit_and_positive(self):
        with self.assertRaises(ValueError):
            OnChainTransferAggregator(self.mapping_store, minimum_amount_by_mapping={"btc-native-v1": "0.1"})
        with self.assertRaises(ValueError):
            OnChainTransferAggregator(self.mapping_store, minimum_amount_by_mapping={
                "btc-native-v1": "0", "wbtc-ethereum-v1": "0.1", "sol-btc-v1": "0.1"})
        with self.assertRaises(ValueError):
            OnChainTransferAggregator(self.mapping_store, minimum_amount_by_mapping={
                "btc-native-v1": "0.1", "wbtc-ethereum-v1": "0.1", "sol-btc-v1": "0.1", "unknown": "0.1"})

    def test_solana_instruction_identity_preserves_multiple_transfers_in_one_transaction(self):
        signature = "2" * 88
        first = event(self.sol, event_id=f"{signature}:outer:0", tx_hash=signature,
                      amount_raw="100000000", event_index=None)
        second = event(self.sol, event_id=f"{signature}:inner:1:0", tx_hash=signature,
                       amount_raw="200000000", event_index=None, scope="address:second")
        self.bind_events([first, second])
        result = self.aggregator.aggregate([first, second], {ASSET: self.decision}, now=NOW)
        sol = next(row for row in result.network_summaries if row.mapping_id == "sol-btc-v1")
        self.assertEqual(sol.transfer_count, 2)
        self.assertEqual(sol.total_amount, "3")
        self.assertEqual(result.deduplicated_events, 0)

    def test_malformed_network_event_identity_is_rejected(self):
        row = event(self.btc, event_id="well-formed", amount_raw="100000000")
        row = NormalizedTransferEvent(**{**row.__dict__, "event_id": "not-a-txid:vout"})
        self.bind_events([row])
        with self.assertRaisesRegex(ValueError, "identity does not match"):
            self.aggregator.aggregate([row], {ASSET: self.decision}, now=NOW)

    def test_transaction_event_index_must_match_stable_event_identity(self):
        row = event(self.btc, event_id="a" * 64 + ":0", amount_raw="100000000", event_index=1)
        self.bind_events([row])
        with self.assertRaisesRegex(ValueError, "event index does not match"):
            self.aggregator.aggregate([row], {ASSET: self.decision}, now=NOW)

    def test_incomplete_bitcoin_input_attribution_is_not_counted_as_one_sender(self):
        row = event(self.btc, event_id="a" * 64 + ":0", amount_raw="100000000")
        row = NormalizedTransferEvent(**{**row.__dict__, "from_address": None,
                                         "from_addresses": ("source-a", "source-b"),
                                         "from_addresses_complete": False})
        self.bind_events([row])
        result = self.aggregator.aggregate([row], {ASSET: self.decision}, now=NOW)
        self.assertEqual(result.network_summaries[0].unique_source_address_count, 0)

    def test_duplicate_event_with_conflicting_economic_payload_is_rejected(self):
        first = event(self.btc, event_id="same-id", amount_raw="100000000")
        conflicting = NormalizedTransferEvent(**{**first.__dict__, "scope": "account:two", "amount_raw": "200000000"})
        self.bind_events([first, conflicting])
        with self.assertRaisesRegex(ValueError, "conflicting duplicate"):
            self.aggregator.aggregate([first, conflicting], {ASSET: self.decision}, now=NOW)

    def test_unpersisted_in_memory_event_cannot_be_injected_into_aggregation(self):
        row = event(self.btc, event_id="not-stored", amount_raw="100000000")
        self.aggregator.bind_ingestion_store(self.ingestion_store)
        result = self.aggregator.aggregate([row], {ASSET: self.decision}, now=NOW)
        self.assertIn(("EVENT_NOT_PERSISTED", 1), result.rejection_counts)

    def test_missing_or_mismatched_canonical_block_journal_excludes_event(self):
        row = event(self.btc, event_id="journal-check", amount_raw="100000000")
        self.bind_events([row], persist_blocks=False)
        missing = self.aggregator.aggregate([row], {ASSET: self.decision}, now=NOW)
        self.assertIn(("CANONICAL_BLOCK_EVIDENCE_MISSING", 1), missing.rejection_counts)
        self.ingestion_store.commit_page("wrong-block", {"next": None}, (), canonical_blocks=(
            {"network_id": row.network_id, "provider": row.provider, "scope": row.scope,
             "block_number": row.block_number, "block_hash": "e" * 64,
             "block_time": row.block_time},
        ))
        mismatch = self.aggregator.aggregate([row], {ASSET: self.decision}, now=NOW)
        self.assertIn(("CANONICAL_BLOCK_HASH_MISMATCH", 1), mismatch.rejection_counts)

    def test_stale_or_future_events_are_excluded(self):
        stale = event(self.btc, event_id="stale", amount_raw="100000000")
        stale = NormalizedTransferEvent(**{**stale.__dict__, "block_time": (NOW - timedelta(days=2)).isoformat()})
        future = event(self.btc, event_id="future", amount_raw="100000000")
        future = NormalizedTransferEvent(**{**future.__dict__, "block_time": (NOW + timedelta(hours=1)).isoformat()})
        self.bind_events([stale, future])
        result = self.aggregator.aggregate([stale, future], {ASSET: self.decision}, now=NOW)
        self.assertEqual(result.network_summaries, ())
        self.assertEqual(result.rejected_events, 2)

    def test_real_aggregator_result_flows_into_candidate_as_non_scoring_corroboration(self):
        row = event(self.btc, event_id="end-to-end-btc", amount_raw="100000000")
        self.bind_events([row])
        current = datetime.now(timezone.utc)
        current_eligibility = eligibility(current.isoformat())
        result = self.aggregator.aggregate_store(
            self.ingestion_store, {ASSET: current_eligibility}, now=current)
        identity = AssetIdentity(ASSET, "Bitcoin", "BTC", "USDT")
        market = MarketObservation(ASSET, "binance_spot", "/ticker", current.isoformat(), price=65000)
        builder = CandidateDiscoveryFilteringEngine()
        base = builder.build(identity, current_eligibility, [market], [], [])
        corroborated = builder.build(
            identity, current_eligibility, [market], [], [], onchain_aggregation=result)
        self.assertEqual(base.candidate_id, corroborated.candidate_id)
        self.assertEqual(corroborated.state, "READY_FOR_RESEARCH")
        self.assertEqual(len(corroborated.onchain_transfer_summary_ids), 1)

    def test_aggregate_store_reads_only_canonical_events(self):
        good = event(self.btc, event_id="btc-out:0", amount_raw="100000000")
        bad = event(self.btc, event_id="btc-out:1", amount_raw="100000000", status="REORGED")
        self.ingestion_store.commit_page("cursor", {"next": None}, [good, bad], canonical_blocks=(
            {"network_id": good.network_id, "provider": good.provider, "scope": good.scope,
             "block_number": good.block_number, "block_hash": good.block_hash, "block_time": good.block_time},
            {"network_id": bad.network_id, "provider": bad.provider, "scope": bad.scope,
             "block_number": bad.block_number, "block_hash": bad.block_hash, "block_time": bad.block_time},
        ))
        result = self.aggregator.aggregate_store(self.ingestion_store, {ASSET: self.decision}, now=NOW)
        self.assertEqual(result.network_summaries[0].transfer_count, 1)


if __name__ == "__main__":
    unittest.main()
