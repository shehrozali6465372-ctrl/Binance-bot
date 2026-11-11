"""Fail-closed domain validation for Module 9 on-chain observations.

Provider transport is intentionally separate: this module does not make network
requests, infer token contracts, or treat provider reachability as data validity.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import urlparse

from .foundation import BinanceListingEligibilityEngine, EligibilityDecision


NETWORK_METADATA = {
    "bitcoin-mainnet": {"family": "UTXO", "chain_id": "bitcoin-mainnet", "providers": frozenset({"alchemy"})},
    "ethereum-mainnet": {"family": "EVM", "chain_id": "1", "providers": frozenset({"alchemy"})},
    "solana-mainnet": {"family": "SOLANA", "chain_id": "mainnet-beta", "providers": frozenset({"alchemy"})},
    "bnb-smart-chain-mainnet": {"family": "EVM", "chain_id": "56", "providers": frozenset({"alchemy"})},
    "xrpl-mainnet": {"family": "XRPL", "chain_id": "xrpl-mainnet", "providers": frozenset({"chainstack"})},
}
NETWORK_PROVIDERS = {key: value["providers"] for key, value in NETWORK_METADATA.items()}
ALLOWED_MAPPING_SOURCES = frozenset({
    "OFFICIAL_PROJECT", "OFFICIAL_NETWORK", "OFFICIAL_REGISTRY",
})
ALLOWED_REPRESENTATIONS = frozenset({"NATIVE", "TOKEN", "WRAPPED", "BRIDGED", "DERIVATIVE"})
ALLOWED_FINALITY = frozenset({"FINALIZED", "CONFIRMED", "PENDING", "UNVERIFIED"})


def _parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class OnChainAssetMapping:
    mapping_id: str
    asset_id: str
    binance_symbol: str
    network_id: str
    network_family: str
    chain_id: str
    representation: str
    contract_address: Optional[str]
    token_standard: Optional[str]
    decimals: int
    mapping_status: str
    source_type: str
    source_url: str
    verified_at: str
    issuer_address: Optional[str] = None
    issued_currency: Optional[str] = None


@dataclass(frozen=True)
class OnChainObservation:
    observation_id: str
    mapping_id: str
    asset_id: str
    network_id: str
    chain_id: str
    provider: str
    endpoint_id: str
    observation_type: str
    block_height: int
    block_hash: str
    transaction_hash: str
    block_time: str
    observed_at: str
    finality: str
    finality_reference: str


@dataclass(frozen=True)
class OnChainValidationResult:
    status: str
    reason_code: str
    reason: str
    observation_id: str = ""
    asset_id: str = ""
    mapping_id: str = ""
    network_id: str = ""
    provider: str = ""


class OnChainIntelligenceEngine:
    """Validate evidence only after Binance Spot eligibility and exact mapping.

    Freshness limits are deliberately mandatory configuration, not guessed
    constants. Limits must be calibrated against each network/provider cadence.
    """

    def __init__(self, freshness_limits_seconds: Optional[Mapping[str, int]] = None,
                 minimum_confirmations_by_network: Optional[Mapping[str, int]] = None):
        limits = dict(freshness_limits_seconds or {})
        for network_id, seconds in limits.items():
            if network_id not in NETWORK_METADATA:
                raise ValueError(f"freshness policy references unsupported network: {network_id}")
            if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
                raise ValueError("freshness limits must be positive integer seconds")
        confirmations = dict(minimum_confirmations_by_network or {})
        for network_id, count in confirmations.items():
            if network_id != "bitcoin-mainnet":
                raise ValueError("confirmation-count policy is currently defined only for Bitcoin mainnet")
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise ValueError("minimum confirmations must be a positive integer")
        self.freshness_limits_seconds = limits
        self.minimum_confirmations_by_network = confirmations

    @staticmethod
    def _result(status: str, code: str, reason: str,
                mapping: Optional[OnChainAssetMapping] = None,
                observation: Optional[OnChainObservation] = None) -> OnChainValidationResult:
        return OnChainValidationResult(
            status=status,
            reason_code=code,
            reason=reason,
            observation_id=observation.observation_id if observation else "",
            asset_id=mapping.asset_id if mapping else (observation.asset_id if observation else ""),
            mapping_id=mapping.mapping_id if mapping else (observation.mapping_id if observation else ""),
            network_id=mapping.network_id if mapping else (observation.network_id if observation else ""),
            provider=observation.provider if observation else "",
        )

    @staticmethod
    def _validate_mapping(mapping: OnChainAssetMapping) -> Optional[OnChainValidationResult]:
        if not isinstance(mapping, OnChainAssetMapping):
            return OnChainValidationResult("UNVERIFIED", "INVALID_ASSET_MAPPING", "mapping object is invalid")
        required = (mapping.mapping_id, mapping.asset_id, mapping.binance_symbol,
                    mapping.network_id, mapping.network_family, mapping.chain_id)
        if any(not isinstance(value, str) or not value.strip() for value in required):
            return OnChainValidationResult("UNVERIFIED", "INVALID_ASSET_MAPPING", "mapping identity fields are incomplete")
        if not mapping.asset_id.startswith("coingecko:") or not mapping.binance_symbol.isalnum() or mapping.binance_symbol != mapping.binance_symbol.upper():
            return OnChainValidationResult("UNVERIFIED", "INVALID_ASSET_MAPPING", "canonical asset ID or Binance symbol is invalid")
        if mapping.network_id not in NETWORK_METADATA:
            return OnChainValidationResult("UNAVAILABLE", "NETWORK_NOT_CONFIGURED", "network is not configured for Module 9")
        network = NETWORK_METADATA[mapping.network_id]
        if mapping.network_family != network["family"] or mapping.chain_id != network["chain_id"]:
            return OnChainValidationResult("UNVERIFIED", "NETWORK_METADATA_MISMATCH", "network family or canonical chain ID does not match configured network metadata")
        if mapping.mapping_status != "VERIFIED":
            return OnChainValidationResult("UNVERIFIED", "ASSET_MAPPING_NOT_VERIFIED", "asset-to-network mapping is not verified")
        if not isinstance(mapping.source_type, str) or mapping.source_type not in ALLOWED_MAPPING_SOURCES:
            return OnChainValidationResult("UNVERIFIED", "MAPPING_SOURCE_NOT_TRUSTED", "mapping source is not an approved official source type")
        if not isinstance(mapping.source_url, str):
            return OnChainValidationResult("UNVERIFIED", "MAPPING_SOURCE_URL_INVALID", "mapping provenance must be an HTTPS source URL")
        parsed_url = urlparse(mapping.source_url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            return OnChainValidationResult("UNVERIFIED", "MAPPING_SOURCE_URL_INVALID", "mapping provenance must be an HTTPS source URL")
        if isinstance(mapping.decimals, bool) or not isinstance(mapping.decimals, int) or not 0 <= mapping.decimals <= 36:
            return OnChainValidationResult("UNVERIFIED", "INVALID_ASSET_DECIMALS", "asset decimals must be an integer from 0 to 36")
        if not isinstance(mapping.representation, str) or mapping.representation not in ALLOWED_REPRESENTATIONS:
            return OnChainValidationResult("UNVERIFIED", "INVALID_ASSET_REPRESENTATION", "asset representation is unsupported")
        if mapping.representation == "NATIVE":
            if (mapping.contract_address is not None or mapping.token_standard is not None
                    or mapping.issuer_address is not None or mapping.issued_currency is not None):
                return OnChainValidationResult("UNVERIFIED", "NATIVE_ASSET_CONTRACT_CONFLICT", "native assets must not declare a token contract, issuer or token standard")
        elif mapping.network_id == "xrpl-mainnet":
            currency = mapping.issued_currency
            valid_standard_currency = (
                isinstance(currency, str) and len(currency) == 3
                and all(0x21 <= ord(char) <= 0x7E for char in currency)
                and currency != "XRP"
            )
            valid_hex_currency = isinstance(currency, str) and re.fullmatch(r"[0-9a-fA-F]{40}", currency) is not None
            if (mapping.contract_address is not None
                    or mapping.token_standard != "XRPL_ISSUED_CURRENCY"
                    or not isinstance(mapping.issuer_address, str) or not mapping.issuer_address.strip()
                    or not (valid_standard_currency or valid_hex_currency)):
                return OnChainValidationResult("UNVERIFIED", "XRPL_ISSUER_CURRENCY_MAPPING_REQUIRED", "non-native XRPL assets require the exact issuer and a valid non-XRP 3-character or 160-bit hex currency code")
        elif (not isinstance(mapping.contract_address, str) or not mapping.contract_address.strip()
              or not isinstance(mapping.token_standard, str) or not mapping.token_standard.strip()
              or mapping.issuer_address is not None or mapping.issued_currency is not None):
            return OnChainValidationResult("UNVERIFIED", "TOKEN_CONTRACT_MAPPING_REQUIRED", "non-native assets on this network require an exact contract/mint and token standard, without XRPL issuer fields")
        try:
            verified_at = _parse_timestamp(mapping.verified_at)
            if verified_at.timestamp() > datetime.now(timezone.utc).timestamp() + 300:
                raise ValueError("mapping verification timestamp is in the future")
        except ValueError:
            return OnChainValidationResult("UNVERIFIED", "MAPPING_VERIFICATION_TIMESTAMP_INVALID", "mapping verification timestamp is invalid")
        return None


    def _validate_finality(self, network_id: str, observation: OnChainObservation):
        """Keep each chain's confirmation/finality semantics distinct."""
        if network_id == "bitcoin-mainnet":
            if observation.finality != "CONFIRMED":
                return ("UNAVAILABLE", "BITCOIN_CONFIRMATION_POLICY_REQUIRED",
                        "Bitcoin uses probabilistic confirmations, not deterministic finalized status")
            minimum = self.minimum_confirmations_by_network.get(network_id)
            if minimum is None:
                return ("UNAVAILABLE", "BITCOIN_CONFIRMATION_THRESHOLD_NOT_CONFIGURED",
                        "minimum Bitcoin confirmation threshold is not configured")
            match = re.fullmatch(r"confirmations=(\d+)", observation.finality_reference)
            if not match or int(match.group(1)) < minimum:
                return ("UNAVAILABLE", "BITCOIN_CONFIRMATIONS_INSUFFICIENT",
                        "Bitcoin transaction has not reached the configured confirmation threshold")
            return None
        expected = {
            "ethereum-mainnet": {"eth_getBlockByNumber:finalized"},
            "bnb-smart-chain-mainnet": {"eth_getFinalizedHeader", "eth_getBlockByNumber:finalized"},
            "solana-mainnet": {"commitment=finalized"},
            "xrpl-mainnet": {"validated_ledger=true"},
        }
        if observation.finality != "FINALIZED" or observation.finality_reference not in expected.get(network_id, set()):
            return ("UNAVAILABLE", "CHAIN_FINALITY_SEMANTICS_UNVERIFIED",
                    "observation does not carry the configured chain-specific finality proof")
        return None

    def validate(self, eligibility: EligibilityDecision,
                 mapping: OnChainAssetMapping,
                 observation: OnChainObservation,
                 now: Optional[str] = None) -> OnChainValidationResult:
        if not isinstance(eligibility, EligibilityDecision) or eligibility.status != "ELIGIBLE":
            return self._result("UNAVAILABLE", "BINANCE_SPOT_ELIGIBILITY_REQUIRED", "on-chain analysis requires a verified ELIGIBLE Binance Spot decision", mapping, observation)
        if (not isinstance(eligibility.asset_id, str) or not eligibility.asset_id.startswith("coingecko:")
                or not isinstance(eligibility.symbol, str) or not eligibility.symbol.isalnum()
                or eligibility.symbol != eligibility.symbol.upper()
                or eligibility.source != BinanceListingEligibilityEngine.SOURCE
                or eligibility.identity_proof_status != "VERIFIED"
                or not isinstance(eligibility.identity_proof_source, str) or not eligibility.identity_proof_source
                or not isinstance(eligibility.identity_proof_data_hash, str)
                or not re.fullmatch(r"[a-fA-F0-9]{64}", eligibility.identity_proof_data_hash)
                or not isinstance(eligibility.eligible_pairs, tuple) or not eligibility.eligible_pairs
                or any(not isinstance(pair, str) or not pair.isalnum() or pair != pair.upper()
                       or not pair.startswith(eligibility.symbol) or len(pair) <= len(eligibility.symbol)
                       for pair in eligibility.eligible_pairs)):
            return self._result("UNVERIFIED", "BINANCE_SPOT_ELIGIBILITY_PROOF_INVALID", "ELIGIBLE decision lacks a valid Binance source, canonical identity proof or exact eligible pair", mapping, observation)
        try:
            _parse_timestamp(eligibility.verified_at)
            _parse_timestamp(eligibility.identity_proof_verified_at)
            _parse_timestamp(eligibility.identity_proof_source_timestamp)
        except ValueError:
            return self._result("UNVERIFIED", "BINANCE_SPOT_ELIGIBILITY_PROOF_INVALID", "eligibility and identity proof timestamps must be valid timezone-aware values", mapping, observation)
        mapping_error = self._validate_mapping(mapping)
        if mapping_error:
            return self._result(mapping_error.status, mapping_error.reason_code, mapping_error.reason, mapping, observation)
        if (eligibility.asset_id != mapping.asset_id
                or eligibility.symbol != mapping.binance_symbol):
            return self._result("UNVERIFIED", "ASSET_IDENTITY_MISMATCH", "mapping does not match the exact Binance-eligible canonical asset and symbol", mapping, observation)
        if not isinstance(observation, OnChainObservation):
            return self._result("UNVERIFIED", "INVALID_ONCHAIN_OBSERVATION", "observation object is invalid", mapping)
        observation_text_fields = (
            observation.observation_id, observation.mapping_id, observation.asset_id,
            observation.network_id, observation.chain_id, observation.provider,
            observation.endpoint_id, observation.observation_type, observation.block_hash,
            observation.transaction_hash, observation.block_time, observation.observed_at,
            observation.finality, observation.finality_reference,
        )
        if any(not isinstance(value, str) or not value.strip() for value in observation_text_fields):
            return self._result("UNVERIFIED", "INVALID_ONCHAIN_OBSERVATION", "observation identity, provenance, block and transaction fields must be non-empty strings", mapping, observation)
        if (observation.mapping_id != mapping.mapping_id
                or observation.asset_id != mapping.asset_id):
            return self._result("UNVERIFIED", "ASSET_IDENTITY_MISMATCH", "observation does not match the exact verified mapping", mapping, observation)
        if (observation.network_id != mapping.network_id
                or observation.chain_id != mapping.chain_id):
            return self._result("UNVERIFIED", "NETWORK_MAPPING_MISMATCH", "observation network or chain ID does not match the verified mapping", mapping, observation)
        if observation.provider not in NETWORK_PROVIDERS[mapping.network_id]:
            return self._result("UNAVAILABLE", "PROVIDER_NOT_APPROVED_FOR_NETWORK", "provider is not approved for this configured network", mapping, observation)
        if (not isinstance(observation.endpoint_id, str) or not observation.endpoint_id.strip()
                or not isinstance(observation.observation_type, str) or not observation.observation_type.strip()
                or not isinstance(observation.finality_reference, str) or not observation.finality_reference.strip()):
            return self._result("UNVERIFIED", "OBSERVATION_PROVENANCE_INCOMPLETE", "endpoint, observation type and finality reference are required", mapping, observation)
        if (isinstance(observation.block_height, bool) or not isinstance(observation.block_height, int)
                or observation.block_height <= 0 or not observation.block_hash.strip()
                or not observation.transaction_hash.strip()):
            return self._result("UNVERIFIED", "OBSERVATION_BLOCK_OR_TRANSACTION_INVALID", "block height, block hash and transaction reference must be present and valid", mapping, observation)
        hash_patterns = {
            "bitcoin-mainnet": (r"[0-9a-fA-F]{64}", r"[0-9a-fA-F]{64}"),
            "ethereum-mainnet": (r"0x[0-9a-fA-F]{64}", r"0x[0-9a-fA-F]{64}"),
            "bnb-smart-chain-mainnet": (r"0x[0-9a-fA-F]{64}", r"0x[0-9a-fA-F]{64}"),
            "solana-mainnet": (r"[1-9A-HJ-NP-Za-km-z]{32,44}", r"[1-9A-HJ-NP-Za-km-z]{64,90}"),
            "xrpl-mainnet": (r"[0-9a-fA-F]{64}", r"[0-9a-fA-F]{64}"),
        }
        block_pattern, transaction_pattern = hash_patterns[mapping.network_id]
        if (not re.fullmatch(block_pattern, observation.block_hash)
                or not re.fullmatch(transaction_pattern, observation.transaction_hash)):
            return self._result("UNVERIFIED", "OBSERVATION_HASH_FORMAT_INVALID", "block or transaction identifier does not match the selected network format", mapping, observation)
        if observation.finality not in ALLOWED_FINALITY:
            return self._result("UNVERIFIED", "OBSERVATION_FINALITY_INVALID", "finality state is not recognized", mapping, observation)
        if observation.finality in {"PENDING", "UNVERIFIED"}:
            return self._result("UNAVAILABLE", "ONCHAIN_DATA_NOT_FINAL", "pending or unverified chain data cannot be accepted as corroborative evidence", mapping, observation)
        finality_error = self._validate_finality(mapping.network_id, observation)
        if finality_error:
            return self._result(finality_error[0], finality_error[1], finality_error[2], mapping, observation)
        try:
            block_time = _parse_timestamp(observation.block_time)
            observed_at = _parse_timestamp(observation.observed_at)
            current_time = _parse_timestamp(now) if now is not None else datetime.now(timezone.utc)
            if observed_at.timestamp() > current_time.timestamp() + 300 or block_time.timestamp() > observed_at.timestamp() + 300:
                raise ValueError("observation time is in the future")
        except ValueError:
            return self._result("UNVERIFIED", "INVALID_OBSERVATION_TIMESTAMP", "block and observation timestamps must be valid timezone-aware ISO-8601 values", mapping, observation)
        max_age = self.freshness_limits_seconds.get(mapping.network_id)
        if max_age is None:
            return self._result("UNAVAILABLE", "FRESHNESS_POLICY_NOT_CONFIGURED", "network freshness threshold has not been calibrated and configured", mapping, observation)
        if (current_time - block_time).total_seconds() > max_age:
            return self._result("UNAVAILABLE", "ONCHAIN_OBSERVATION_STALE", "block observation exceeds the configured network freshness threshold", mapping, observation)
        return self._result("ACCEPTED", "ONCHAIN_OBSERVATION_VERIFIED", "eligible asset, exact network mapping, provider, provenance, finality and freshness validated", mapping, observation)


class OnChainStore:
    """Additive SQLite persistence for verified mappings and observations.

    Duplicate observation IDs are idempotent only when their canonical payloads
    are identical; conflicting payloads are rejected rather than overwritten.
    """

    def __init__(self, database_path: str, engine: Optional[OnChainIntelligenceEngine] = None):
        Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.engine = engine or OnChainIntelligenceEngine()
        self.conn = sqlite3.connect(database_path, timeout=30)
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS layer1_onchain_asset_mappings (
            mapping_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, network_id TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS layer1_onchain_observations (
            observation_id TEXT PRIMARY KEY, mapping_id TEXT NOT NULL, asset_id TEXT NOT NULL,
            network_id TEXT NOT NULL, provider TEXT NOT NULL, observed_at TEXT NOT NULL,
            payload_json TEXT NOT NULL, validation_json TEXT NOT NULL,
            FOREIGN KEY(mapping_id) REFERENCES layer1_onchain_asset_mappings(mapping_id)
        );
        CREATE INDEX IF NOT EXISTS idx_layer1_onchain_asset_time
            ON layer1_onchain_observations(asset_id, observed_at);
        """)

    @staticmethod
    def _canonical(value) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def save_verified(self, eligibility: EligibilityDecision, mapping: OnChainAssetMapping,
                      observation: OnChainObservation) -> str:
        result = self.engine.validate(eligibility, mapping, observation)
        if result.status != "ACCEPTED":
            raise ValueError(f"only an ACCEPTED on-chain observation may be persisted: {result.reason_code}")
        mapping_json = self._canonical(mapping.__dict__)
        observation_json = self._canonical(observation.__dict__)
        validation_json = self._canonical(result.__dict__)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            existing_mapping = self.conn.execute(
                "SELECT payload_json FROM layer1_onchain_asset_mappings WHERE mapping_id=?",
                (mapping.mapping_id,),
            ).fetchone()
            if existing_mapping and existing_mapping[0] != mapping_json:
                raise ValueError("mapping ID collision: refusing to overwrite different mapping content")
            self.conn.execute(
                "INSERT OR IGNORE INTO layer1_onchain_asset_mappings VALUES (?, ?, ?, ?)",
                (mapping.mapping_id, mapping.asset_id, mapping.network_id, mapping_json),
            )
            existing_observation = self.conn.execute(
                "SELECT payload_json, validation_json FROM layer1_onchain_observations WHERE observation_id=?",
                (observation.observation_id,),
            ).fetchone()
            if existing_observation:
                if existing_observation != (observation_json, validation_json):
                    raise ValueError("observation ID collision: refusing to overwrite different evidence")
                self.conn.commit()
                return "DUPLICATE"
            self.conn.execute(
                "INSERT INTO layer1_onchain_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (observation.observation_id, observation.mapping_id, observation.asset_id,
                 observation.network_id, observation.provider, observation.observed_at,
                 observation_json, validation_json),
            )
            self.conn.commit()
            return "INSERTED"
        except Exception:
            self.conn.rollback()
            raise

    def get_latest_accepted_observation(self, mapping_id: str) -> Optional[OnChainObservation]:
        """Return the newest persisted observation accepted with full Spot proof."""
        if not isinstance(mapping_id, str) or not mapping_id.strip():
            raise ValueError("mapping_id must be a non-empty string")
        rows = self.conn.execute(
            """SELECT payload_json, validation_json FROM layer1_onchain_observations
               WHERE mapping_id=?""",
            (mapping_id,),
        ).fetchall()
        accepted = []
        for payload_json, validation_json in rows:
            validation = json.loads(validation_json)
            if validation.get("status") != "ACCEPTED":
                continue
            observation = OnChainObservation(**json.loads(payload_json))
            try:
                observed_at = _parse_timestamp(observation.observed_at)
            except ValueError:
                continue
            accepted.append((observed_at, observation))
        return max(accepted, key=lambda item: item[0])[1] if accepted else None

    def get_observation(self, observation_id: str) -> Optional[tuple[OnChainObservation, OnChainValidationResult]]:
        row = self.conn.execute(
            "SELECT payload_json, validation_json FROM layer1_onchain_observations WHERE observation_id=?",
            (observation_id,),
        ).fetchone()
        if row is None:
            return None
        return OnChainObservation(**json.loads(row[0])), OnChainValidationResult(**json.loads(row[1]))

    def list_verified_mappings(self, network_id: Optional[str] = None) -> list[OnChainAssetMapping]:
        """Return only previously accepted, verified asset mappings."""
        query = "SELECT payload_json FROM layer1_onchain_asset_mappings"
        params = ()
        if network_id is not None:
            query += " WHERE network_id=?"
            params = (network_id,)
        query += " ORDER BY mapping_id"
        mappings = []
        for (payload,) in self.conn.execute(query, params).fetchall():
            mapping = OnChainAssetMapping(**json.loads(payload))
            if mapping.mapping_status != "VERIFIED" or self.engine._validate_mapping(mapping) is not None:
                continue
            mappings.append(mapping)
        return mappings

    def close(self) -> None:
        self.conn.close()
