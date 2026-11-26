"""Fail-closed domain validation for Module 9 on-chain observations.

Provider transport is intentionally separate: this module does not make network
requests, infer token contracts, or treat provider reachability as data validity.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import urlparse

from .onchain_providers import is_valid_xrpl_classic_address, is_valid_xrpl_issued_currency_code

from .foundation import BinanceListingEligibilityEngine, EligibilityDecision
from .onchain_receipt_config import load_onchain_receipt_config_from_env


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
    scope: str = ""


@dataclass(frozen=True)
class OnChainObservationProvenance:
    """Immutable pointer to one exact provider observation in an accepted page."""
    cursor_key: str
    page_id: str
    observation_id: str

    def __post_init__(self):
        if (not isinstance(self.cursor_key, str) or not self.cursor_key.strip()
                or not isinstance(self.page_id, str)
                or re.fullmatch(r"[a-f0-9]{64}", self.page_id) is None
                or not isinstance(self.observation_id, str) or not self.observation_id.strip()):
            raise ValueError("on-chain observation provenance reference is invalid")


@dataclass(frozen=True)
class OnChainIngestionPageAcceptance:
    page_id: str
    cursor_key: str
    key_id: str
    payload_sha256: str
    signature: str


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
    receipt_version: int = 0
    receipt_key_id: str = ""
    observation_fingerprint: str = ""
    evidence_fingerprint: str = ""
    provenance_fingerprint: str = ""
    provenance_cursor_key: str = ""
    provenance_page_id: str = ""
    provenance_observation_id: str = ""
    receipt_signature: str = ""


class OnChainIntelligenceEngine:
    """Validate evidence only after Binance Spot eligibility and exact mapping.

    Freshness limits are deliberately mandatory configuration, not guessed
    constants. Limits must be calibrated against each network/provider cadence.
    """

    def __init__(self, freshness_limits_seconds: Optional[Mapping[str, int]] = None,
                 minimum_confirmations_by_network: Optional[Mapping[str, int]] = None,
                 receipt_signing_key: Optional[bytes] = None, receipt_key_id: str = ""):
        if receipt_signing_key is not None and (not isinstance(receipt_signing_key, bytes) or len(receipt_signing_key) < 32):
            raise ValueError("on-chain receipt signing key must contain at least 32 bytes")
        if receipt_signing_key is not None and (not isinstance(receipt_key_id, str) or not receipt_key_id.strip()):
            raise ValueError("a non-empty receipt key ID is required when receipt signing is enabled")
        if receipt_signing_key is not None and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", receipt_key_id.strip()) is None:
            raise ValueError("receipt key ID must be 1-128 safe identifier characters")
        self.receipt_signing_key = receipt_signing_key
        self.receipt_key_id = receipt_key_id.strip() if receipt_signing_key is not None else ""
        self.receipt_verification_keys = (
            {self.receipt_key_id: receipt_signing_key} if receipt_signing_key is not None else {}
        )
        self.trusted_receipt_key_ids = (
            frozenset({self.receipt_key_id}) if receipt_signing_key is not None else frozenset()
        )
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

    @classmethod
    def from_env(
        cls,
        freshness_limits_seconds: Optional[Mapping[str, int]] = None,
        minimum_confirmations_by_network: Optional[Mapping[str, int]] = None,
    ) -> "OnChainIntelligenceEngine":
        """Build an engine from explicitly provisioned Module 9 receipt keys.

        An empty environment keeps signing disabled. Malformed or partially
        trusted key configuration raises rather than silently selecting a key.
        """
        config = load_onchain_receipt_config_from_env()
        engine = cls(
            freshness_limits_seconds=freshness_limits_seconds,
            minimum_confirmations_by_network=minimum_confirmations_by_network,
            receipt_signing_key=config.active_signing_key,
            receipt_key_id=config.active_key_id,
        )
        engine.receipt_verification_keys = dict(config.keyring)
        engine.trusted_receipt_key_ids = config.trusted_key_ids
        return engine

    def verify_persisted_acceptance_receipt(
        self, observation: OnChainObservation, validation: OnChainValidationResult,
    ) -> bool:
        """Verify a stored receipt using its key ID, including trusted retired keys."""
        if (not isinstance(validation, OnChainValidationResult)
                or validation.receipt_key_id not in self.trusted_receipt_key_ids):
            return False
        key = self.receipt_verification_keys.get(validation.receipt_key_id)
        return self.verify_acceptance_receipt(
            observation, validation, key, validation.receipt_key_id,
        )

    @staticmethod
    def _ingestion_page_acceptance_payload(material: dict, key_id: str) -> dict:
        return {
            "domain": "BINANCE_SQUARE_W2E_ONCHAIN_INGESTION_PAGE_V1",
            "receipt_version": 1,
            "receipt_key_id": key_id,
            "page_id": material["page_id"],
            "cursor_key": material["cursor_key"],
            "page_material": material["page_material"],
            "receipts": material["receipts"],
            "receipt_sha256": material["receipt_sha256"],
        }

    @staticmethod
    def _require_ingestion_store(store):
        # Signing is deliberately restricted to the two first-party durable
        # adapters. Duck-typed caller objects cannot supply a forged page payload.
        from .onchain_ingestion import OnChainIngestionStore
        from .onchain_postgres import PostgresOnChainIngestionStore
        if type(store) not in (OnChainIngestionStore, PostgresOnChainIngestionStore):
            raise TypeError("ingestion page signing requires a first-party durable ingestion store")

    def sign_ingestion_page(self, ingestion_store, cursor_key: str,
                            page_id: str) -> OnChainIngestionPageAcceptance:
        """Sign only a page re-read and validated by a first-party durable store."""
        self._require_ingestion_store(ingestion_store)
        existing = ingestion_store.get_page_acceptance(cursor_key, page_id)
        if existing is not None:
            if self.verify_ingestion_page_acceptance(ingestion_store, cursor_key, page_id):
                return OnChainIngestionPageAcceptance(
                    page_id, cursor_key, existing["key_id"],
                    existing["payload_sha256"], existing["signature"],
                )
            raise ValueError("existing ingestion page acceptance is invalid or its signing key is no longer trusted")
        if (self.receipt_signing_key is None or not self.receipt_key_id
                or self.receipt_key_id not in self.trusted_receipt_key_ids):
            raise ValueError("trusted ingestion page signing is not configured")
        material = ingestion_store.get_page_acceptance_material(cursor_key, page_id)
        payload = self._ingestion_page_acceptance_payload(material, self.receipt_key_id)
        payload_json = self._canonical_receipt_json(payload).decode("utf-8")
        payload_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        signature = hmac.new(
            self.receipt_signing_key,
            b"BINANCE_SQUARE_W2E_ONCHAIN_INGESTION_PAGE_V1\0" + payload_json.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        ingestion_store.save_page_acceptance(
            cursor_key, page_id, self.receipt_key_id, payload_json,
            payload_sha256, signature,
        )
        return OnChainIngestionPageAcceptance(
            page_id, cursor_key, self.receipt_key_id, payload_sha256, signature,
        )

    def sign_pending_ingestion_pages(self, ingestion_store) -> dict:
        """Recover unsigned committed pages without trusting caller-supplied payloads."""
        self._require_ingestion_store(ingestion_store)
        pending = ingestion_store.list_pending_page_acceptances()
        if (self.receipt_signing_key is None or not self.receipt_key_id
                or self.receipt_key_id not in self.trusted_receipt_key_ids):
            return {"signed": 0, "pending": len(pending), "rejected": 0}
        signed = rejected = 0
        for cursor_key, page_id in pending:
            try:
                self.sign_ingestion_page(ingestion_store, cursor_key, page_id)
                signed += 1
            except (ValueError, TypeError, KeyError, AttributeError, IndexError):
                # Persisted page material is untrusted input. A malformed page
                # remains unsigned for operator review; isolate its failure so
                # later pending pages can still be recovered. Do not swallow
                # process-level failures or storage/connection errors.
                rejected += 1
        remaining = len(ingestion_store.list_pending_page_acceptances())
        return {"signed": signed, "pending": remaining, "rejected": rejected}

    def verify_ingestion_page_acceptance(self, ingestion_store, cursor_key: str,
                                        page_id: str) -> bool:
        """Re-read store material and verify a persisted page HMAC after restart."""
        try:
            self._require_ingestion_store(ingestion_store)
            material = ingestion_store.get_page_acceptance_material(cursor_key, page_id)
            envelope = ingestion_store.get_page_acceptance(cursor_key, page_id)
            if not isinstance(envelope, dict):
                return False
            key_id = envelope.get("key_id")
            if key_id not in self.trusted_receipt_key_ids:
                return False
            key = self.receipt_verification_keys.get(key_id)
            if not isinstance(key, bytes) or len(key) < 32:
                return False
            payload = self._ingestion_page_acceptance_payload(material, key_id)
            payload_json = self._canonical_receipt_json(payload).decode("utf-8")
            payload_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            if (envelope.get("cursor_key") != cursor_key
                    or envelope.get("payload_json") != payload_json
                    or envelope.get("payload_sha256") != payload_sha256):
                return False
            expected = hmac.new(
                key,
                b"BINANCE_SQUARE_W2E_ONCHAIN_INGESTION_PAGE_V1\0" + payload_json.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected, envelope.get("signature", ""))
        except (TypeError, ValueError, KeyError, AttributeError):
            return False

    def verify_observation_provenance(self, ingestion_store,
                                      provenance: OnChainObservationProvenance,
                                      mapping: OnChainAssetMapping,
                                      observation: OnChainObservation) -> bool:
        """Bind an anchor observation to its own immutable provider-page record.

        Transfer events are deliberately not treated as anchor observations:
        they are separate records with separate aggregation semantics.
        """
        try:
            self._require_ingestion_store(ingestion_store)
            if not isinstance(provenance, OnChainObservationProvenance):
                return False
            if not self.verify_ingestion_page_acceptance(
                ingestion_store, provenance.cursor_key, provenance.page_id,
            ):
                return False
            material = ingestion_store.get_page_acceptance_material(
                provenance.cursor_key, provenance.page_id,
            )
            page = material["page_material"]
            scope_identity = page.get("scope_identity")
            if (not isinstance(scope_identity, list) or len(scope_identity) != 3
                    or any(not isinstance(value, str) or not value for value in scope_identity)
                    or tuple(scope_identity) != (
                        observation.network_id, observation.provider, observation.scope,
                    )):
                return False
            rows = page.get("provider_observations", [])
            if not isinstance(rows, list):
                return False
            matches = [
                item for item in rows
                if isinstance(item, dict)
                and item.get("observation_id") == provenance.observation_id
            ]
            if len(matches) != 1:
                return False
            if self._canonical_receipt_json(matches[0]) != self._canonical_receipt_json(asdict(observation)):
                return False
            from .onchain_providers import _approved_endpoint_id
            expected_endpoint_id = _approved_endpoint_id(
                observation.provider, observation.network_id,
            )
            if (expected_endpoint_id is None or observation.endpoint_id != expected_endpoint_id
                    or observation.mapping_id != mapping.mapping_id
                    or observation.asset_id != mapping.asset_id
                    or observation.network_id != mapping.network_id
                    or observation.chain_id != mapping.chain_id
                    or observation.provider not in NETWORK_PROVIDERS.get(mapping.network_id, frozenset())
                    or observation.block_height <= 0):
                return False
            cursor = page.get("next_cursor")
            if not isinstance(cursor, dict):
                return False
            if observation.network_id == "bitcoin-mainnet":
                minimum = cursor.get("minimum_confirmations")
                tip = cursor.get("observed_tip_height")
                confirmations = tip - observation.block_height + 1 if isinstance(tip, int) and not isinstance(tip, bool) else -1
                if (isinstance(minimum, bool) or not isinstance(minimum, int) or minimum <= 0
                        or isinstance(tip, bool) or not isinstance(tip, int)
                        or confirmations < minimum
                        or observation.finality != "CONFIRMED"
                        or observation.finality_reference != f"confirmations={confirmations}"):
                    return False
            elif observation.network_id in {"ethereum-mainnet", "bnb-smart-chain-mainnet"}:
                finalized_height = cursor.get("finalized_height")
                reference = cursor.get("finality_reference")
                if (isinstance(finalized_height, bool) or not isinstance(finalized_height, int)
                        or observation.block_height > finalized_height
                        or not isinstance(reference, str) or not reference
                        or observation.finality != "FINALIZED"
                        or observation.finality_reference != reference):
                    return False
            elif observation.network_id == "solana-mainnet":
                finalized_slot = cursor.get("finalized_slot")
                if (isinstance(finalized_slot, bool) or not isinstance(finalized_slot, int)
                        or observation.block_height > finalized_slot
                        or observation.finality != "FINALIZED"
                        or observation.finality_reference != "commitment=finalized"):
                    return False
            elif observation.network_id == "xrpl-mainnet":
                validated_head = cursor.get("validated_head_height")
                if (isinstance(validated_head, bool) or not isinstance(validated_head, int)
                        or observation.block_height > validated_head
                        or observation.finality != "FINALIZED"
                        or observation.finality_reference != "validated_ledger=true"):
                    return False
            else:
                return False
            return True
        except (TypeError, ValueError, KeyError, AttributeError):
            return False

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
    def _canonical_receipt_json(value) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

    @staticmethod
    def _receipt_signature_payload(result: OnChainValidationResult) -> dict:
        return {
            "receipt_version": result.receipt_version,
            "receipt_key_id": result.receipt_key_id,
            "status": result.status,
            "reason_code": result.reason_code,
            "reason": result.reason,
            "observation_id": result.observation_id,
            "asset_id": result.asset_id,
            "mapping_id": result.mapping_id,
            "network_id": result.network_id,
            "provider": result.provider,
            "observation_fingerprint": result.observation_fingerprint,
            "evidence_fingerprint": result.evidence_fingerprint,
            "provenance_fingerprint": result.provenance_fingerprint,
            "provenance_cursor_key": result.provenance_cursor_key,
            "provenance_page_id": result.provenance_page_id,
            "provenance_observation_id": result.provenance_observation_id,
        }

    @classmethod
    def verify_acceptance_receipt(cls, observation: OnChainObservation,
                                  validation: OnChainValidationResult,
                                  verification_key: Optional[bytes],
                                  expected_key_id: Optional[str]) -> bool:
        if (not isinstance(verification_key, bytes) or len(verification_key) < 32
                or not isinstance(observation, OnChainObservation)
                or not isinstance(validation, OnChainValidationResult)
                or validation.status != "ACCEPTED" or type(validation.receipt_version) is not int
                or validation.receipt_version != 1
                or not isinstance(validation.receipt_key_id, str)
                or re.fullmatch(r"[A-Za-z0-9._-]{1,128}", validation.receipt_key_id) is None
                or not isinstance(expected_key_id, str)
                or re.fullmatch(r"[A-Za-z0-9._-]{1,128}", expected_key_id) is None
                or validation.receipt_key_id != expected_key_id
                or not re.fullmatch(r"[a-f0-9]{64}", validation.receipt_signature)
                or not re.fullmatch(r"[a-f0-9]{64}", validation.observation_fingerprint)
                or not re.fullmatch(r"[a-f0-9]{64}", validation.evidence_fingerprint)
                or not re.fullmatch(r"[a-f0-9]{64}", validation.provenance_fingerprint)
                or not isinstance(validation.provenance_cursor_key, str) or not validation.provenance_cursor_key
                or not re.fullmatch(r"[a-f0-9]{64}", validation.provenance_page_id)
                or not isinstance(validation.provenance_observation_id, str) or not validation.provenance_observation_id):
            return False
        if (validation.observation_id != observation.observation_id
                or validation.asset_id != observation.asset_id
                or validation.mapping_id != observation.mapping_id
                or validation.network_id != observation.network_id
                or validation.provider != observation.provider):
            return False
        observation_fingerprint = hashlib.sha256(
            cls._canonical_receipt_json(asdict(observation))
        ).hexdigest()
        if not hmac.compare_digest(observation_fingerprint, validation.observation_fingerprint):
            return False
        provenance_fingerprint = hashlib.sha256(cls._canonical_receipt_json({
            "cursor_key": validation.provenance_cursor_key,
            "page_id": validation.provenance_page_id,
            "observation_id": validation.provenance_observation_id,
        })).hexdigest()
        if not hmac.compare_digest(provenance_fingerprint, validation.provenance_fingerprint):
            return False
        expected = hmac.new(
            verification_key,
            cls._canonical_receipt_json(cls._receipt_signature_payload(validation)),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, validation.receipt_signature)

    def _signed_acceptance_result(self, eligibility: EligibilityDecision,
                                  mapping: OnChainAssetMapping,
                                  observation: OnChainObservation,
                                  provenance: OnChainObservationProvenance) -> OnChainValidationResult:
        if self.receipt_signing_key is None:
            return self._result(
                "UNAVAILABLE", "ONCHAIN_RECEIPT_SIGNING_NOT_CONFIGURED",
                "trusted acceptance receipt signing is not configured", mapping, observation,
            )
        observation_fingerprint = hashlib.sha256(
            self._canonical_receipt_json(asdict(observation))
        ).hexdigest()
        provenance_fingerprint = hashlib.sha256(
            self._canonical_receipt_json(asdict(provenance))
        ).hexdigest()
        evidence_fingerprint = hashlib.sha256(self._canonical_receipt_json({
            "eligibility": asdict(eligibility),
            "mapping": asdict(mapping),
            "observation": asdict(observation),
            "provenance": asdict(provenance),
        })).hexdigest()
        result = self._result("ACCEPTED", "ONCHAIN_OBSERVATION_VERIFIED",
                              "eligible asset, exact network mapping, provider, provenance, finality and freshness validated",
                              mapping, observation)
        result = replace(
            result, receipt_version=1, receipt_key_id=self.receipt_key_id,
            observation_fingerprint=observation_fingerprint,
            evidence_fingerprint=evidence_fingerprint,
            provenance_fingerprint=provenance_fingerprint,
            provenance_cursor_key=provenance.cursor_key,
            provenance_page_id=provenance.page_id,
            provenance_observation_id=provenance.observation_id,
        )
        signature = hmac.new(
            self.receipt_signing_key,
            self._canonical_receipt_json(self._receipt_signature_payload(result)),
            hashlib.sha256,
        ).hexdigest()
        return replace(result, receipt_signature=signature)

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
        try:
            parsed_url = urlparse(mapping.source_url)
            # Reject user-info URLs (for example https://official.example@attacker.example)
            # because they are routinely misread as belonging to the text before '@'.
            # This is syntax hardening only; it does not establish source authority.
            invalid_source_url = (
                parsed_url.scheme != "https"
                or not parsed_url.netloc
                or not parsed_url.hostname
                or parsed_url.username is not None
                or parsed_url.password is not None
            )
        except ValueError:
            invalid_source_url = True
        if invalid_source_url:
            return OnChainValidationResult("UNVERIFIED", "MAPPING_SOURCE_URL_INVALID", "mapping provenance must be an unambiguous HTTPS source URL without embedded credentials")
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
            if (mapping.contract_address is not None
                    or mapping.token_standard != "XRPL_ISSUED_CURRENCY"
                    or not is_valid_xrpl_classic_address(mapping.issuer_address)
                    or not is_valid_xrpl_issued_currency_code(currency)):
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
                 now: Optional[str] = None,
                 ingestion_store=None,
                 provenance: Optional[OnChainObservationProvenance] = None) -> OnChainValidationResult:
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
        if not self.receipt_signing_key or not self.receipt_key_id:
            return self._result(
                "UNAVAILABLE", "ONCHAIN_RECEIPT_SIGNING_NOT_CONFIGURED",
                "durable observation acceptance signing is not configured",
                mapping, observation,
            )
        if not self.verify_observation_provenance(
            ingestion_store, provenance, mapping, observation,
        ):
            return self._result(
                "UNVERIFIED", "ONCHAIN_OBSERVATION_PROVENANCE_REQUIRED",
                "observation must match an exact event in a signed, currently canonical ingestion page",
                mapping, observation,
            )
        return self._signed_acceptance_result(eligibility, mapping, observation, provenance)


class OnChainStore:
    """Additive SQLite persistence for verified mappings and observations.

    Duplicate observation IDs are idempotent only when their canonical payloads
    are identical; conflicting payloads are rejected rather than overwritten.
    """

    def __init__(self, database_path: str, engine: Optional[OnChainIntelligenceEngine] = None,
                 ingestion_store=None):
        Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.engine = engine or OnChainIntelligenceEngine()
        self.ingestion_store = ingestion_store
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
                      observation: OnChainObservation, *, ingestion_store=None,
                      provenance: Optional[OnChainObservationProvenance] = None) -> str:
        effective_ingestion_store = (
            ingestion_store if ingestion_store is not None else self.ingestion_store
        )
        result = self.engine.validate(
            eligibility, mapping, observation,
            ingestion_store=effective_ingestion_store, provenance=provenance,
        )
        if result.status != "ACCEPTED":
            raise ValueError(f"only an ACCEPTED on-chain observation may be persisted: {result.reason_code}")
        self.ingestion_store = effective_ingestion_store
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
            validation_record = OnChainValidationResult(**validation)
            mapping_row = self.conn.execute(
                "SELECT payload_json FROM layer1_onchain_asset_mappings WHERE mapping_id=?",
                (mapping_id,),
            ).fetchone()
            if mapping_row is None:
                continue
            mapping = OnChainAssetMapping(**json.loads(mapping_row[0]))
            provenance = OnChainObservationProvenance(
                validation_record.provenance_cursor_key,
                validation_record.provenance_page_id,
                validation_record.provenance_observation_id,
            )
            if (not self.engine.verify_persisted_acceptance_receipt(observation, validation_record)
                    or not self.engine.verify_observation_provenance(
                        self.ingestion_store, provenance, mapping, observation,
                    )):
                continue
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
        observation = OnChainObservation(**json.loads(row[0]))
        validation = OnChainValidationResult(**json.loads(row[1]))
        if validation.status == "ACCEPTED":
            mapping_row = self.conn.execute(
                "SELECT payload_json FROM layer1_onchain_asset_mappings WHERE mapping_id=?",
                (observation.mapping_id,),
            ).fetchone()
            mapping = OnChainAssetMapping(**json.loads(mapping_row[0])) if mapping_row else None
            try:
                provenance = OnChainObservationProvenance(
                    validation.provenance_cursor_key,
                    validation.provenance_page_id,
                    validation.provenance_observation_id,
                )
                valid = (
                    mapping is not None
                    and self.engine.verify_persisted_acceptance_receipt(observation, validation)
                    and self.engine.verify_observation_provenance(
                        self.ingestion_store, provenance, mapping, observation,
                    )
                )
            except (TypeError, ValueError):
                valid = False
            if not valid:
                validation = replace(
                    validation, status="UNVERIFIED",
                    reason_code="ONCHAIN_PROVENANCE_INVALID",
                    reason="persisted observation no longer matches its accepted canonical ingestion page",
                )
        return observation, validation

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
