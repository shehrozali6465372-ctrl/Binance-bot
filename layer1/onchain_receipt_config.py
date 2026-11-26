"""Explicit, rotation-safe configuration for Module 9 acceptance receipts.

No key IDs or key material are trusted by default. This configuration only
loads operator-provisioned secrets; it does not create, persist, or rotate keys.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Mapping, Optional


_KEY_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_HEX_KEY = re.compile(r"^(?:[0-9a-fA-F]{2})+$")


class _DuplicateJsonKeyError(ValueError):
    pass


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError("duplicate JSON object key")
        result[key] = value
    return result


@dataclass(frozen=True)
class OnChainReceiptKeyConfig:
    keyring: Mapping[str, bytes]
    trusted_key_ids: frozenset[str]
    active_key_id: str

    @property
    def active_signing_key(self) -> Optional[bytes]:
        if not self.active_key_id:
            return None
        return self.keyring.get(self.active_key_id)


def load_onchain_receipt_config_from_env(
    environ: Optional[Mapping[str, str]] = None,
) -> OnChainReceiptKeyConfig:
    """Load the Module 9 keyring and independent explicit trusted-key allowlist.

    Environment variables:
      ONCHAIN_RECEIPT_HMAC_KEYRING_JSON: JSON object of key ID -> hex key.
      ONCHAIN_RECEIPT_ACTIVE_KEY_ID: key ID used for new signatures.
      ONCHAIN_RECEIPT_TRUSTED_KEY_IDS: comma-separated IDs accepted on replay.

    Previous keys may remain in the keyring and allowlist during rotation. A
    configured active key must be present and explicitly trusted. Partial or
    malformed configuration raises ValueError so callers can fail closed.
    """
    source = os.environ if environ is None else environ
    raw_keyring = str(source.get("ONCHAIN_RECEIPT_HMAC_KEYRING_JSON", "")).strip()
    active_key_id = str(source.get("ONCHAIN_RECEIPT_ACTIVE_KEY_ID", "")).strip()
    trusted_raw = str(source.get("ONCHAIN_RECEIPT_TRUSTED_KEY_IDS", "")).strip()

    keyring: dict[str, bytes] = {}
    if raw_keyring:
        try:
            parsed = json.loads(raw_keyring, object_pairs_hook=_unique_json_object)
        except _DuplicateJsonKeyError:
            raise ValueError("on-chain receipt keyring contains duplicate JSON key IDs") from None
        except (TypeError, ValueError):
            raise ValueError("on-chain receipt keyring configuration is invalid") from None
        if not isinstance(parsed, dict):
            raise ValueError("on-chain receipt keyring must be a JSON object")
        for key_id, encoded_key in parsed.items():
            if (not isinstance(key_id, str) or _KEY_ID.fullmatch(key_id) is None
                    or not isinstance(encoded_key, str)):
                raise ValueError("on-chain receipt keyring entry is invalid")
            if _HEX_KEY.fullmatch(encoded_key) is None:
                raise ValueError("on-chain receipt key must use contiguous even-length hexadecimal encoding")
            try:
                key = bytes.fromhex(encoded_key)
            except ValueError:
                raise ValueError("on-chain receipt keyring entry is invalid") from None
            if len(key) < 32:
                raise ValueError("on-chain receipt keyring key is shorter than 32 bytes")
            keyring[key_id] = key

    trusted_values = [item.strip() for item in trusted_raw.split(",") if item.strip()]
    if any(_KEY_ID.fullmatch(item) is None for item in trusted_values):
        raise ValueError("on-chain receipt trusted key ID is invalid")
    if len(set(trusted_values)) != len(trusted_values):
        raise ValueError("on-chain receipt trusted key IDs contain duplicates")
    trusted_ids = frozenset(trusted_values)
    if not trusted_ids.issubset(keyring):
        raise ValueError("on-chain receipt trusted key IDs must exist in the keyring")

    if active_key_id:
        if _KEY_ID.fullmatch(active_key_id) is None:
            raise ValueError("on-chain receipt active key ID is invalid")
        if active_key_id not in trusted_ids or active_key_id not in keyring:
            raise ValueError("on-chain receipt active key must exist and be explicitly trusted")
    # A verification-only keyring may intentionally omit an active signer.
    # Without an active ID, engine construction remains unsigned/fail-closed.

    return OnChainReceiptKeyConfig(
        keyring=keyring,
        trusted_key_ids=trusted_ids,
        active_key_id=active_key_id,
    )
