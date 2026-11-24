"""Authenticated, durable receipts for trusted source-ingestion boundaries.

Receipts prove that a holder of an explicitly provisioned HMAC key attested to
an exact canonical payload. They do not independently prove that a provider
response was genuine; the trusted ingestion worker must bind the raw response
or its documented canonical projection into the payload before signing.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping


_RECEIPT_VERSION = 1
_DOMAIN = b"binance-square-w2e:source-ingestion-receipt:v1\x00"
_KEY_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_AUTHORITY_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def _validate_json_value(value: Any) -> None:
    if value is None or type(value) in (str, bool, int, float):
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("receipt payload object keys must be strings")
        for item in value.values():
            _validate_json_value(item)
        return
    raise ValueError("receipt payload contains a non-JSON value")


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("receipt payload must be a non-empty object")
    if any(not isinstance(key, str) for key in value):
        raise ValueError("receipt payload object keys must be strings")
    _validate_json_value(dict(value))
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
        decoded = json.loads(encoded)
    except (TypeError, ValueError, RecursionError):
        raise ValueError("receipt payload must be finite JSON") from None
    if not isinstance(decoded, dict):
        raise ValueError("receipt payload must be a JSON object")
    return encoded


def _signing_bytes(version: int, authority_id: str, key_id: str, payload_hash: str) -> bytes:
    envelope = {
        "version": version,
        "authority_id": authority_id,
        "key_id": key_id,
        "payload_hash": payload_hash,
    }
    return _DOMAIN + json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


@dataclass(frozen=True)
class SourceIngestionReceipt:
    version: int
    authority_id: str
    key_id: str
    payload_hash: str
    signature: str

    def validate(self) -> None:
        if type(self.version) is not int or self.version != _RECEIPT_VERSION:
            raise ValueError("unsupported source-ingestion receipt version")
        if not isinstance(self.authority_id, str) or not _AUTHORITY_ID.fullmatch(self.authority_id):
            raise ValueError("source-ingestion receipt authority ID is invalid")
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise ValueError("source-ingestion receipt key ID is invalid")
        if not isinstance(self.payload_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", self.payload_hash):
            raise ValueError("source-ingestion receipt payload hash is invalid")
        if not isinstance(self.signature, str) or not re.fullmatch(r"[a-f0-9]{64}", self.signature):
            raise ValueError("source-ingestion receipt signature is invalid")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SourceIngestionReceipt":
        if not isinstance(value, Mapping):
            raise ValueError("source-ingestion receipt must be an object")
        expected = {"version", "authority_id", "key_id", "payload_hash", "signature"}
        if set(value) != expected:
            raise ValueError("source-ingestion receipt fields are incomplete or unexpected")
        receipt = cls(**dict(value))
        receipt.validate()
        return receipt


def load_source_receipt_config_from_env() -> tuple[dict[str, bytes], frozenset[str], str]:
    """Load a provisioned HMAC keyring, explicit trust allowlist and active key.

    A verification-only keyring may omit the active signer. Any configured
    signer must exist in the keyring and be explicitly trusted; every trusted
    ID must resolve to a provisioned key. Malformed rotation policy fails closed.
    """
    trusted_raw = os.getenv("BINANCE_SOURCE_RECEIPT_TRUSTED_KEY_IDS", "").strip()
    current_key_id = os.getenv("BINANCE_SPOT_INGESTION_KEY_ID", "").strip()
    keyring_text = os.getenv("BINANCE_SOURCE_RECEIPT_HMAC_KEYRING_JSON", "").strip()
    keyring: dict[str, bytes] = {}
    if keyring_text:
        try:
            raw = json.loads(keyring_text)
        except (TypeError, ValueError):
            raise ValueError("source receipt keyring configuration is invalid") from None
        if not isinstance(raw, dict):
            raise ValueError("source receipt keyring must be a JSON object")
        for key_id, key_hex in raw.items():
            if (not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id)
                    or not isinstance(key_hex, str)):
                raise ValueError("source receipt keyring entry is invalid")
            try:
                key = bytes.fromhex(key_hex)
            except ValueError:
                raise ValueError("source receipt keyring entry is invalid") from None
            if len(key) < 32:
                raise ValueError("source receipt keyring key is shorter than 32 bytes")
            keyring[key_id] = key
    else:
        single_key_hex = os.getenv("BINANCE_SPOT_INGESTION_HMAC_KEY_HEX", "").strip()
        if single_key_hex and current_key_id:
            if not _KEY_ID.fullmatch(current_key_id):
                raise ValueError("source receipt active key ID is invalid")
            try:
                key = bytes.fromhex(single_key_hex)
            except ValueError:
                raise ValueError("source receipt signing key configuration is invalid") from None
            if len(key) < 32:
                raise ValueError("source receipt signing key is shorter than 32 bytes")
            keyring[current_key_id] = key

    trusted_values = [item.strip() for item in trusted_raw.split(",") if item.strip()]
    if any(not _KEY_ID.fullmatch(item) for item in trusted_values):
        raise ValueError("source receipt trusted key ID is invalid")
    if len(set(trusted_values)) != len(trusted_values):
        raise ValueError("source receipt trusted key IDs contain duplicates")
    trusted_ids = frozenset(trusted_values)
    if not trusted_ids.issubset(keyring):
        raise ValueError("source receipt trusted key IDs must exist in the keyring")
    if current_key_id:
        if not _KEY_ID.fullmatch(current_key_id):
            raise ValueError("source receipt active key ID is invalid")
        if current_key_id not in trusted_ids or current_key_id not in keyring:
            raise ValueError("source receipt active key must exist and be explicitly trusted")
    return keyring, trusted_ids, current_key_id




def load_cms_source_receipt_config_from_env() -> tuple[dict[str, bytes], frozenset[str]]:
    """Load the CMS worker's separate verification keyring and trust allowlist.

    This is verification-only: the Python importer must never mint CMS receipts
    or share the Binance Spot active signing key. Missing configuration yields
    an empty trust set so CMS records remain untrusted and are not persisted.
    """
    keyring_text = os.getenv("BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON", "").strip()
    trusted_raw = os.getenv("BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS", "").strip()
    if not keyring_text and not trusted_raw:
        return {}, frozenset()
    if not keyring_text or not trusted_raw:
        raise ValueError("CMS source receipt configuration is incomplete")

    def reject_duplicate_pairs(pairs):
        result = {}
        for key_id, key_hex in pairs:
            if key_id in result:
                raise ValueError("CMS source receipt keyring contains duplicate key IDs")
            result[key_id] = key_hex
        return result

    try:
        raw_keyring = json.loads(keyring_text, object_pairs_hook=reject_duplicate_pairs)
    except (TypeError, ValueError):
        raise ValueError("CMS source receipt keyring configuration is invalid") from None
    if not isinstance(raw_keyring, dict):
        raise ValueError("CMS source receipt keyring must be a JSON object")

    keyring: dict[str, bytes] = {}
    for key_id, key_hex in raw_keyring.items():
        if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id) or not isinstance(key_hex, str):
            raise ValueError("CMS source receipt keyring entry is invalid")
        try:
            key = bytes.fromhex(key_hex)
        except ValueError:
            raise ValueError("CMS source receipt keyring entry is invalid") from None
        if len(key) < 32:
            raise ValueError("CMS source receipt keyring key is shorter than 32 bytes")
        keyring[key_id] = key

    trusted_values = [item.strip() for item in trusted_raw.split(",") if item.strip()]
    if any(not _KEY_ID.fullmatch(item) for item in trusted_values):
        raise ValueError("CMS source receipt trusted key ID is invalid")
    if len(set(trusted_values)) != len(trusted_values):
        raise ValueError("CMS source receipt trusted key IDs contain duplicates")
    trusted_ids = frozenset(trusted_values)
    if not trusted_ids.issubset(keyring):
        raise ValueError("CMS source receipt trusted key IDs must exist in the keyring")
    return keyring, trusted_ids

def create_source_ingestion_receipt(
    payload: Mapping[str, Any], *, authority_id: str, key_id: str,
    signing_key: bytes,
) -> SourceIngestionReceipt:
    if not isinstance(authority_id, str) or not _AUTHORITY_ID.fullmatch(authority_id):
        raise ValueError("source-ingestion authority ID is invalid")
    if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id):
        raise ValueError("source-ingestion key ID is invalid")
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise ValueError("source-ingestion signing key must contain at least 32 bytes")
    payload_hash = hashlib.sha256(_canonical_json(payload)).hexdigest()
    signature = hmac.new(
        signing_key,
        _signing_bytes(_RECEIPT_VERSION, authority_id, key_id, payload_hash),
        hashlib.sha256,
    ).hexdigest()
    receipt = SourceIngestionReceipt(
        _RECEIPT_VERSION, authority_id, key_id, payload_hash, signature,
    )
    receipt.validate()
    return receipt


def verify_source_ingestion_receipt(
    receipt: SourceIngestionReceipt | Mapping[str, Any],
    payload: Mapping[str, Any], *,
    verification_keys: Mapping[str, bytes],
    expected_authority_id: str,
    trusted_key_ids: set[str] | frozenset[str],
) -> bool:
    """Verify durable receipt, exact payload binding, authority and key allowlist."""
    try:
        normalized = (
            receipt if isinstance(receipt, SourceIngestionReceipt)
            else SourceIngestionReceipt.from_dict(receipt)
        )
        normalized.validate()
        if normalized.authority_id != expected_authority_id:
            return False
        if normalized.key_id not in trusted_key_ids:
            return False
        key = verification_keys.get(normalized.key_id)
        if not isinstance(key, bytes) or len(key) < 32:
            return False
        payload_hash = hashlib.sha256(_canonical_json(payload)).hexdigest()
        if not hmac.compare_digest(payload_hash, normalized.payload_hash):
            return False
        expected = hmac.new(
            key,
            _signing_bytes(
                normalized.version, normalized.authority_id,
                normalized.key_id, normalized.payload_hash,
            ),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, normalized.signature)
    except (TypeError, ValueError, KeyError, RecursionError):
        return False
