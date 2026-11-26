import unittest

from datetime import datetime, timedelta, timezone

from layer1.foundation import EligibilityDecision
from layer1.onchain import (
    OnChainAssetMapping,
    OnChainIntelligenceEngine,
    OnChainObservation,
    OnChainStore,
    NETWORK_PROVIDERS,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)


def eligible_decision(asset_id, symbol):
    proof_time = (NOW - timedelta(minutes=2)).isoformat()
    return EligibilityDecision(
        status="ELIGIBLE", asset_id=asset_id, symbol=symbol,
        eligible_pairs=(f"{symbol}USDT",),
        verified_at=proof_time,
        identity_proof_status="VERIFIED",
        identity_proof_source="coingecko_coin_tickers",
        identity_proof_verified_at=proof_time,
        identity_proof_source_timestamp=proof_time,
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
        }, minimum_confirmations_by_network={"bitcoin-mainnet": 6},
            receipt_signing_key=b"test-only-onchain-receipt-key-32-bytes-minimum",
            receipt_key_id="test-key-v1")
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
            verified_at=(NOW - timedelta(hours=2)).isoformat(),
        )
        self.observation = OnChainObservation(
            observation_id="btc-block-900000-tx-1",
            mapping_id=self.mapping.mapping_id,
            asset_id=self.mapping.asset_id,
            network_id=self.mapping.network_id,
            chain_id=self.mapping.chain_id,
            provider="alchemy",
            endpoint_id="alchemy:bitcoin-mainnet",
            observation_type="TRANSACTION",
            block_height=900000,
            block_hash="a" * 64,
            transaction_hash="b" * 64,
            block_time=(NOW - timedelta(minutes=1)).isoformat(),
            observed_at=NOW.isoformat(),
            finality="CONFIRMED",
            finality_reference="confirmations=6",
            scope="address:bc1qtest-anchor-scope",
        )

    def test_latest_observation_requires_live_page_revalidation_not_only_signed_pointer(self):
        from layer1.onchain import OnChainObservationProvenance
        store = OnChainStore(":memory:", engine=self.engine)
        try:
            provenance = OnChainObservationProvenance(
                cursor_key="bitcoin:btc:account", page_id="c" * 64,
                observation_id="btc-event-900000",
            )
            receipt = self.engine._signed_acceptance_result(
                self.eligibility, self.mapping, self.observation, provenance,
            )
            store.conn.execute(
                "INSERT INTO layer1_onchain_asset_mappings VALUES (?, ?, ?, ?)",
                (self.mapping.mapping_id, self.mapping.asset_id, self.mapping.network_id,
                 store._canonical(self.mapping.__dict__)),
            )
            store.conn.execute(
                "INSERT INTO layer1_onchain_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (self.observation.observation_id, self.observation.mapping_id,
                 self.observation.asset_id, self.observation.network_id,
                 self.observation.provider, self.observation.observed_at,
                 store._canonical(self.observation.__dict__),
                 store._canonical(receipt.__dict__)),
            )
            store.conn.commit()
            self.assertIsNone(store.get_latest_accepted_observation(self.mapping.mapping_id))
            recovered = store.get_observation(self.observation.observation_id)
            self.assertEqual(recovered[1].status, "UNVERIFIED")
            self.assertEqual(recovered[1].reason_code, "ONCHAIN_PROVENANCE_INVALID")
        finally:
            store.close()

    def test_distinct_signed_observation_page_survives_reopen_and_fails_after_reorg(self):
        import os
        import tempfile
        from layer1.onchain import OnChainStore
        from layer1.onchain_ingestion import OnChainIngestionStore
        from tests.onchain_test_support import seed_accepted_observation_page

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "onchain.sqlite3")
            ingestion = OnChainIngestionStore(path)
            store = OnChainStore(path, engine=self.engine, ingestion_store=ingestion)
            try:
                provenance = seed_accepted_observation_page(
                    ingestion, store, self.eligibility, self.mapping, self.observation,
                )
                self.assertEqual(
                    store.get_latest_accepted_observation(self.mapping.mapping_id),
                    self.observation,
                )
                store.close()
                ingestion.close()
                ingestion = OnChainIngestionStore(path)
                store = OnChainStore(path, engine=self.engine, ingestion_store=ingestion)
                self.assertEqual(
                    store.get_latest_accepted_observation(self.mapping.mapping_id),
                    self.observation,
                )
                cursor = ingestion.get_checkpoint(provenance.cursor_key)
                ingestion.commit_page(
                    provenance.cursor_key, cursor, (), expected_cursor=cursor,
                    scope_identity=(
                        self.observation.network_id, self.observation.provider,
                        self.observation.scope,
                    ),
                    allow_recanonicalized=True,
                    canonical_blocks=({
                        "network_id": self.observation.network_id,
                        "provider": self.observation.provider,
                        "scope": self.observation.scope,
                        "block_number": self.observation.block_height,
                        "block_hash": "f" * 64,
                        "block_time": self.observation.block_time,
                    },),
                )
                self.assertIsNone(
                    store.get_latest_accepted_observation(self.mapping.mapping_id)
                )
                recovered = store.get_observation(self.observation.observation_id)
                self.assertEqual(recovered[1].status, "UNVERIFIED")
                self.assertEqual(recovered[1].reason_code, "ONCHAIN_PROVENANCE_INVALID")
            finally:
                store.close()
                ingestion.close()

    def test_anchor_observation_endpoint_id_must_match_approved_provider_network(self):
        import os
        import tempfile
        from dataclasses import replace
        from layer1.onchain import OnChainStore
        from layer1.onchain_ingestion import OnChainIngestionStore
        from tests.onchain_test_support import seed_accepted_observation_page

        wrong_endpoint = replace(self.observation, endpoint_id="unapproved-endpoint-alias")
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "onchain.sqlite3")
            ingestion = OnChainIngestionStore(path)
            store = OnChainStore(path, engine=self.engine, ingestion_store=ingestion)
            try:
                with self.assertRaisesRegex(ValueError, "endpoint_id does not match"):
                    seed_accepted_observation_page(
                        ingestion, store, self.eligibility, self.mapping, wrong_endpoint,
                    )
                self.assertIsNone(
                    store.get_latest_accepted_observation(self.mapping.mapping_id)
                )
            finally:
                store.close()
                ingestion.close()

    def test_tampered_anchor_observation_page_material_is_rejected(self):
        import json
        import os
        import tempfile
        from layer1.onchain import OnChainStore
        from layer1.onchain_ingestion import OnChainIngestionStore
        from tests.onchain_test_support import seed_accepted_observation_page

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "onchain.sqlite3")
            ingestion = OnChainIngestionStore(path)
            store = OnChainStore(path, engine=self.engine, ingestion_store=ingestion)
            try:
                provenance = seed_accepted_observation_page(
                    ingestion, store, self.eligibility, self.mapping, self.observation,
                )
                page_row = ingestion.conn.execute(
                    "SELECT page_material_json FROM layer1_onchain_ingestion_pages WHERE page_id=?",
                    (provenance.page_id,),
                ).fetchone()
                page_material = json.loads(page_row[0])
                page_material["provider_observations"][0]["transaction_hash"] = "0" * 64
                ingestion.conn.execute(
                    "UPDATE layer1_onchain_ingestion_pages SET page_material_json=? WHERE page_id=?",
                    (ingestion._canonical(page_material), provenance.page_id),
                )
                ingestion.conn.commit()
                self.assertIsNone(
                    store.get_latest_accepted_observation(self.mapping.mapping_id)
                )
                recovered = store.get_observation(self.observation.observation_id)
                self.assertEqual(recovered[1].status, "UNVERIFIED")
                self.assertEqual(recovered[1].reason_code, "ONCHAIN_PROVENANCE_INVALID")
            finally:
                store.close()
                ingestion.close()

    def test_rejects_caller_constructed_observation_without_signed_page_provenance(self):
        result = self.engine.validate(self.eligibility, self.mapping, self.observation)
        self.assertEqual(result.status, "UNVERIFIED")
        self.assertEqual(result.reason_code, "ONCHAIN_OBSERVATION_PROVENANCE_REQUIRED")

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

    def test_rejects_mapping_source_url_with_deceptive_userinfo_host(self):
        deceptive = OnChainAssetMapping(**{
            **self.mapping.__dict__,
            "source_url": "https://bitcoin.org@attacker.example/source",
        })
        result = self.engine.validate(self.eligibility, deceptive, self.observation)
        self.assertEqual(result.status, "UNVERIFIED")
        self.assertEqual(result.reason_code, "MAPPING_SOURCE_URL_INVALID")

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
            "issuer_address": "rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq",
            "issued_currency": "USD",
        })
        result = self.engine._validate_mapping(xrpl_mapping)
        self.assertIsNone(result)

    def test_xrpl_issued_token_accepts_documented_nonstandard_160_bit_currency_code(self):
        currency = "444F4C4C415259444F4F00000000000000000000"
        mapping = OnChainAssetMapping(**{
            **self.mapping.__dict__, "mapping_id": "xrpl-valid-hex-currency-v1",
            "asset_id": "coingecko:usd-coin", "binance_symbol": "USDC",
            "network_id": "xrpl-mainnet", "network_family": "XRPL",
            "chain_id": "xrpl-mainnet", "representation": "TOKEN",
            "token_standard": "XRPL_ISSUED_CURRENCY",
            "issuer_address": "rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq", "issued_currency": currency,
        })
        self.assertIsNone(self.engine._validate_mapping(mapping))

    def test_xrpl_issued_token_rejects_invalid_classic_issuer_checksum(self):
        mapping = OnChainAssetMapping(**{
            **self.mapping.__dict__, "mapping_id": "xrpl-invalid-issuer-v1",
            "asset_id": "coingecko:usd-coin", "binance_symbol": "USDC",
            "network_id": "xrpl-mainnet", "network_family": "XRPL",
            "chain_id": "xrpl-mainnet", "representation": "TOKEN",
            "token_standard": "XRPL_ISSUED_CURRENCY",
            "issuer_address": "rBqiK7z9a7M8w2F7yQzvVJ5QJ8qQh2vKQ",
            "issued_currency": "USD",
        })
        result = self.engine._validate_mapping(mapping)
        self.assertEqual(result.reason_code, "XRPL_ISSUER_CURRENCY_MAPPING_REQUIRED")

    def test_xrpl_issued_token_rejects_reserved_xrp_or_malformed_currency_codes(self):
        for currency in ("XRP", "US", "USD ", "G" * 40):
            mapping = OnChainAssetMapping(**{
                **self.mapping.__dict__, "mapping_id": "xrpl-invalid-currency-v1",
                "asset_id": "coingecko:usd-coin", "binance_symbol": "USDC",
                "network_id": "xrpl-mainnet", "network_family": "XRPL",
                "chain_id": "xrpl-mainnet", "representation": "TOKEN",
                "token_standard": "XRPL_ISSUED_CURRENCY",
                "issuer_address": "rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq", "issued_currency": currency,
            })
            result = self.engine._validate_mapping(mapping)
            self.assertEqual(result.reason_code, "XRPL_ISSUER_CURRENCY_MAPPING_REQUIRED")

    def test_xrpl_issued_token_rejects_nonstandard_currency_with_reserved_zero_prefix(self):
        reserved_codes = (
            "0000000000000000000000005852500000000000",  # standard XRP encoded as 160-bit hex
            "0000000000000000000000000000000000000000",  # all-zero code
            "0000000000000000000000005553440000000000",  # standard USD encoded as hex
        )
        for currency in reserved_codes:
            with self.subTest(currency=currency):
                mapping = OnChainAssetMapping(**{
                    **self.mapping.__dict__, "mapping_id": "xrpl-reserved-hex-currency-v1",
                    "asset_id": "coingecko:usd-coin", "binance_symbol": "USDC",
                    "network_id": "xrpl-mainnet", "network_family": "XRPL",
                    "chain_id": "xrpl-mainnet", "representation": "TOKEN",
                    "token_standard": "XRPL_ISSUED_CURRENCY",
                    "issuer_address": "rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq", "issued_currency": currency,
                })
                result = self.engine._validate_mapping(mapping)
                self.assertEqual(result.reason_code, "XRPL_ISSUER_CURRENCY_MAPPING_REQUIRED")

    def test_xrpl_issued_token_rejects_nonstandard_three_character_punctuation(self):
        for currency in ("A/B", "U_D", "A:B"):
            with self.subTest(currency=currency):
                mapping = OnChainAssetMapping(**{
                    **self.mapping.__dict__, "mapping_id": "xrpl-invalid-standard-code-v1",
                    "asset_id": "coingecko:usd-coin", "binance_symbol": "USDC",
                    "network_id": "xrpl-mainnet", "network_family": "XRPL",
                    "chain_id": "xrpl-mainnet", "representation": "TOKEN",
                    "token_standard": "XRPL_ISSUED_CURRENCY",
                    "issuer_address": "rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq", "issued_currency": currency,
                })
                result = self.engine._validate_mapping(mapping)
                self.assertEqual(result.reason_code, "XRPL_ISSUER_CURRENCY_MAPPING_REQUIRED")

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

    def test_sqlite_save_verified_uses_constructor_bound_ingestion_store_by_default(self):
        import os
        import tempfile
        from layer1.onchain_ingestion import OnChainIngestionStore
        from tests.onchain_test_support import seed_accepted_observation_page

        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "onchain.sqlite3")
            ingestion = OnChainIngestionStore(database_path)
            store = OnChainStore(database_path, engine=self.engine, ingestion_store=ingestion)
            try:
                provenance = seed_accepted_observation_page(
                    ingestion, store, self.eligibility, self.mapping, self.observation,
                )
                self.assertEqual(
                    store.save_verified(
                        self.eligibility, self.mapping, self.observation,
                        provenance=provenance,
                    ),
                    "DUPLICATE",
                )
            finally:
                store.close()
                ingestion.close()

    def test_sqlite_store_refuses_observation_without_signed_page_provenance(self):
        store = OnChainStore(":memory:", engine=self.engine)
        try:
            with self.assertRaisesRegex(ValueError, "ONCHAIN_OBSERVATION_PROVENANCE_REQUIRED"):
                store.save_verified(self.eligibility, self.mapping, self.observation)
            self.assertIsNone(store.get_latest_accepted_observation(self.mapping.mapping_id))
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
