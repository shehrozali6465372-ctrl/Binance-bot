import unittest

from layer1.foundation import EligibilityDecision
from layer1.onchain import (
    OnChainAssetMapping,
    OnChainIntelligenceEngine,
    OnChainObservation,
    OnChainStore,
    NETWORK_PROVIDERS,
)


def eligible_decision(asset_id, symbol):
    return EligibilityDecision(
        status="ELIGIBLE", asset_id=asset_id, symbol=symbol,
        eligible_pairs=(f"{symbol}USDT",),
        verified_at="2026-11-11T12:00:00+00:00",
        identity_proof_status="VERIFIED",
        identity_proof_source="coingecko_coin_tickers",
        identity_proof_verified_at="2026-11-11T12:00:00+00:00",
        identity_proof_source_timestamp="2026-11-11T12:00:00+00:00",
        identity_proof_data_hash="a" * 64,
    )


class OnChainIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = OnChainIntelligenceEngine({
            "bitcoin-mainnet": 86400,
            "ethereum-mainnet": 86400,
            "solana-mainnet": 86400,
            "bnb-smart-chain-mainnet": 86400,
            "xrpl-mainnet": 86400,
        }, minimum_confirmations_by_network={"bitcoin-mainnet": 6})
        self.eligibility = eligible_decision("coingecko:bitcoin", "BTC")
        self.mapping = OnChainAssetMapping(
            mapping_id="btc-mainnet-native-v1",
            asset_id="coingecko:bitcoin",
            binance_symbol="BTC",
            network_id="bitcoin-mainnet",
            network_family="UTXO",
            chain_id="bitcoin-mainnet",
            representation="NATIVE",
            contract_address=None,
            token_standard=None,
            decimals=8,
            mapping_status="VERIFIED",
            source_type="OFFICIAL_NETWORK",
            source_url="https://bitcoin.org/",
            verified_at="2026-11-11T12:00:00+00:00",
        )
        self.observation = OnChainObservation(
            observation_id="btc-block-900000-tx-1",
            mapping_id=self.mapping.mapping_id,
            asset_id=self.mapping.asset_id,
            network_id=self.mapping.network_id,
            chain_id=self.mapping.chain_id,
            provider="alchemy",
            endpoint_id="bitcoin-mainnet-rpc",
            observation_type="TRANSACTION",
            block_height=900000,
            block_hash="a" * 64,
            transaction_hash="b" * 64,
            block_time="2026-11-11T11:59:00+00:00",
            observed_at="2026-11-11T12:00:00+00:00",
            finality="CONFIRMED",
            finality_reference="confirmations=6",
        )

    def test_accepts_exact_verified_native_mapping_for_eligible_asset(self):
        result = self.engine.validate(self.eligibility, self.mapping, self.observation)
        self.assertEqual(result.status, "ACCEPTED")
        self.assertEqual(result.reason_code, "ONCHAIN_OBSERVATION_VERIFIED")

    def test_rejects_forged_eligible_decision_without_identity_proof(self):
        forged = EligibilityDecision(
            status="ELIGIBLE", asset_id="coingecko:bitcoin", symbol="BTC",
            eligible_pairs=("BTCUSDT",),
        )
        result = self.engine.validate(forged, self.mapping, self.observation)
        self.assertEqual(result.status, "UNVERIFIED")
        self.assertEqual(result.reason_code, "BINANCE_SPOT_ELIGIBILITY_PROOF_INVALID")

    def test_rejects_asset_without_binance_spot_eligibility(self):
        decision = EligibilityDecision(status="INELIGIBLE", asset_id="coingecko:bitcoin", symbol="BTC")
        result = self.engine.validate(decision, self.mapping, self.observation)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason_code, "BINANCE_SPOT_ELIGIBILITY_REQUIRED")

    def test_rejects_same_ticker_when_canonical_asset_id_differs(self):
        wrong_asset = OnChainAssetMapping(**{
            **self.mapping.__dict__, "asset_id": "coingecko:bitcoin-cash",
        })
        result = self.engine.validate(self.eligibility, wrong_asset, self.observation)
        self.assertEqual(result.status, "UNVERIFIED")
        self.assertEqual(result.reason_code, "ASSET_IDENTITY_MISMATCH")

    def test_rejects_wrong_network_even_when_ticker_and_asset_id_match(self):
        wrong_network = OnChainObservation(**{
            **self.observation.__dict__, "network_id": "ethereum-mainnet", "chain_id": "1",
        })
        result = self.engine.validate(self.eligibility, self.mapping, wrong_network)
        self.assertEqual(result.status, "UNVERIFIED")
        self.assertEqual(result.reason_code, "NETWORK_MAPPING_MISMATCH")

    def test_rejects_unverified_mapping_provenance(self):
        unverified = OnChainAssetMapping(**{
            **self.mapping.__dict__, "mapping_status": "UNVERIFIED",
        })
        result = self.engine.validate(self.eligibility, unverified, self.observation)
        self.assertEqual(result.status, "UNVERIFIED")
        self.assertEqual(result.reason_code, "ASSET_MAPPING_NOT_VERIFIED")

    def test_bitcoin_requires_configured_confirmation_threshold(self):
        engine = OnChainIntelligenceEngine({"bitcoin-mainnet": 86400})
        result = engine.validate(self.eligibility, self.mapping, self.observation)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason_code, "BITCOIN_CONFIRMATION_THRESHOLD_NOT_CONFIGURED")

    def test_bitcoin_rejects_confirmation_count_below_threshold(self):
        shallow = OnChainObservation(**{
            **self.observation.__dict__, "finality_reference": "confirmations=2",
        })
        result = self.engine.validate(self.eligibility, self.mapping, shallow)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason_code, "BITCOIN_CONFIRMATIONS_INSUFFICIENT")

    def test_bitcoin_is_not_mislabeled_as_deterministically_finalized(self):
        mislabeled = OnChainObservation(**{
            **self.observation.__dict__, "finality": "FINALIZED",
        })
        result = self.engine.validate(self.eligibility, self.mapping, mislabeled)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason_code, "BITCOIN_CONFIRMATION_POLICY_REQUIRED")

    def test_pending_transaction_is_not_accepted_as_confirmed_evidence(self):
        pending = OnChainObservation(**{
            **self.observation.__dict__, "finality": "PENDING",
        })
        result = self.engine.validate(self.eligibility, self.mapping, pending)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason_code, "ONCHAIN_DATA_NOT_FINAL")

    def test_rejects_provider_not_approved_for_selected_network(self):
        wrong_provider = OnChainObservation(**{
            **self.observation.__dict__, "provider": "node-real",
        })
        result = self.engine.validate(self.eligibility, self.mapping, wrong_provider)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason_code, "PROVIDER_NOT_APPROVED_FOR_NETWORK")

    def test_native_asset_must_not_have_a_contract_address(self):
        invalid_native = OnChainAssetMapping(**{
            **self.mapping.__dict__, "contract_address": "0x" + "1" * 40,
        })
        result = self.engine.validate(self.eligibility, invalid_native, self.observation)
        self.assertEqual(result.status, "UNVERIFIED")
        self.assertEqual(result.reason_code, "NATIVE_ASSET_CONTRACT_CONFLICT")

    def test_rejects_block_and_transaction_hashes_with_wrong_network_format(self):
        malformed = OnChainObservation(**{
            **self.observation.__dict__, "transaction_hash": "0x" + "b" * 64,
        })
        result = self.engine.validate(self.eligibility, self.mapping, malformed)
        self.assertEqual(result.status, "UNVERIFIED")
        self.assertEqual(result.reason_code, "OBSERVATION_HASH_FORMAT_INVALID")

    def test_rejects_invalid_or_future_timestamps(self):
        invalid_time = OnChainObservation(**{
            **self.observation.__dict__, "observed_at": "2026-11-11T12:00:00",
        })
        result = self.engine.validate(self.eligibility, self.mapping, invalid_time)
        self.assertEqual(result.status, "UNVERIFIED")
        self.assertEqual(result.reason_code, "INVALID_OBSERVATION_TIMESTAMP")

    def test_solana_requires_finalized_commitment_semantics(self):
        sol_mapping = OnChainAssetMapping(**{
            **self.mapping.__dict__, "mapping_id": "sol-mainnet-native-v1",
            "asset_id": "coingecko:solana", "binance_symbol": "SOL",
            "network_id": "solana-mainnet", "network_family": "SOLANA",
            "chain_id": "mainnet-beta", "decimals": 9,
        })
        sol_observation = OnChainObservation(**{
            **self.observation.__dict__, "observation_id": "sol-finalized-1",
            "mapping_id": sol_mapping.mapping_id, "asset_id": sol_mapping.asset_id,
            "network_id": sol_mapping.network_id, "chain_id": sol_mapping.chain_id,
            "provider": "alchemy", "finality": "FINALIZED",
            "finality_reference": "commitment=confirmed",
            "block_hash": "A" * 43, "transaction_hash": "B" * 87,
        })
        eligibility = eligible_decision("coingecko:solana", "SOL")
        result = self.engine.validate(eligibility, sol_mapping, sol_observation)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason_code, "CHAIN_FINALITY_SEMANTICS_UNVERIFIED")

    def test_selected_provider_matrix_covers_all_five_requested_networks(self):
        self.assertEqual(NETWORK_PROVIDERS["bitcoin-mainnet"], frozenset({"alchemy"}))
        self.assertEqual(NETWORK_PROVIDERS["ethereum-mainnet"], frozenset({"alchemy"}))
        self.assertEqual(NETWORK_PROVIDERS["solana-mainnet"], frozenset({"alchemy"}))
        self.assertEqual(NETWORK_PROVIDERS["bnb-smart-chain-mainnet"], frozenset({"alchemy"}))
        self.assertEqual(NETWORK_PROVIDERS["xrpl-mainnet"], frozenset({"chainstack"}))

    def test_rejects_chain_id_that_does_not_match_configured_network(self):
        wrong_chain = OnChainAssetMapping(**{
            **self.mapping.__dict__, "chain_id": "1",
        })
        result = self.engine.validate(self.eligibility, wrong_chain, self.observation)
        self.assertEqual(result.status, "UNVERIFIED")
        self.assertEqual(result.reason_code, "NETWORK_METADATA_MISMATCH")

    def test_xrpl_issued_token_requires_exact_issuer_and_currency(self):
        xrpl_mapping = OnChainAssetMapping(**{
            **self.mapping.__dict__, "mapping_id": "xrpl-issued-token-v1",
            "asset_id": "coingecko:usd-coin", "binance_symbol": "USDC",
            "network_id": "xrpl-mainnet", "network_family": "XRPL",
            "chain_id": "xrpl-mainnet", "representation": "TOKEN",
            "token_standard": "XRPL_ISSUED_CURRENCY",
            "issuer_address": "rIssuerAddressExample",
            "issued_currency": "USD",
        })
        result = self.engine._validate_mapping(xrpl_mapping)
        self.assertIsNone(result)

    def test_xrpl_issued_token_without_issuer_currency_is_rejected(self):
        xrpl_mapping = OnChainAssetMapping(**{
            **self.mapping.__dict__, "mapping_id": "xrpl-issued-token-v1",
            "asset_id": "coingecko:usd-coin", "binance_symbol": "USDC",
            "network_id": "xrpl-mainnet", "network_family": "XRPL",
            "chain_id": "xrpl-mainnet", "representation": "TOKEN",
            "token_standard": "XRPL_ISSUED_CURRENCY",
        })
        result = self.engine._validate_mapping(xrpl_mapping)
        self.assertEqual(result.reason_code, "XRPL_ISSUER_CURRENCY_MAPPING_REQUIRED")

    def test_token_representation_requires_exact_contract_and_standard(self):
        token = OnChainAssetMapping(**{
            **self.mapping.__dict__, "representation": "TOKEN",
        })
        result = self.engine.validate(self.eligibility, token, self.observation)
        self.assertEqual(result.status, "UNVERIFIED")
        self.assertEqual(result.reason_code, "TOKEN_CONTRACT_MAPPING_REQUIRED")

    def test_persists_only_verified_observations_and_deduplicates_identical_evidence(self):
        result = self.engine.validate(self.eligibility, self.mapping, self.observation)
        store = OnChainStore(":memory:", engine=self.engine)
        try:
            self.assertEqual(store.save_verified(self.eligibility, self.mapping, self.observation), "INSERTED")
            self.assertEqual(store.save_verified(self.eligibility, self.mapping, self.observation), "DUPLICATE")
            restored = store.get_observation(self.observation.observation_id)
            self.assertIsNotNone(restored)
            self.assertEqual(restored[0], self.observation)
            self.assertEqual(restored[1], result)
        finally:
            store.close()

    def test_refuses_to_persist_unverified_observations(self):
        result = self.engine.validate(
            EligibilityDecision(status="INELIGIBLE", asset_id="coingecko:bitcoin", symbol="BTC"),
            self.mapping, self.observation,
        )
        store = OnChainStore(":memory:", engine=self.engine)
        try:
            with self.assertRaisesRegex(ValueError, "only an ACCEPTED"):
                store.save_verified(
                    EligibilityDecision(status="INELIGIBLE", asset_id="coingecko:bitcoin", symbol="BTC"),
                    self.mapping, self.observation,
                )
        finally:
            store.close()

    def test_missing_freshness_policy_fails_closed(self):
        engine = OnChainIntelligenceEngine(minimum_confirmations_by_network={"bitcoin-mainnet": 6})
        result = engine.validate(self.eligibility, self.mapping, self.observation)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason_code, "FRESHNESS_POLICY_NOT_CONFIGURED")

    def test_rejects_stale_block_observation(self):
        engine = OnChainIntelligenceEngine({"bitcoin-mainnet": 60}, minimum_confirmations_by_network={"bitcoin-mainnet": 6})
        result = engine.validate(self.eligibility, self.mapping, self.observation)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason_code, "ONCHAIN_OBSERVATION_STALE")

    def test_rejects_unsupported_network(self):
        unsupported = OnChainAssetMapping(**{
            **self.mapping.__dict__, "network_id": "dogecoin-mainnet",
            "chain_id": "dogecoin-mainnet",
        })
        result = self.engine.validate(self.eligibility, unsupported, self.observation)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason_code, "NETWORK_NOT_CONFIGURED")


if __name__ == "__main__":
    unittest.main()
