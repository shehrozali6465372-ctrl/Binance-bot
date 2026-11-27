"""Durable, idempotent storage for normalized on-chain transfer pages.

The store deliberately owns persistence/checkpoint atomicity, not provider
pagination semantics. Callers must supply a stable provider event identity and
must only advance a cursor after a complete, validated page has been normalized.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from decimal import Decimal, InvalidOperation, localcontext
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from .onchain_providers import (
    BitcoinAddressTransaction, EvmTokenTransferLog, SolanaAddressTransaction,
    CapturedProviderReceiptBatch, ProviderResponseReceipt, ProviderTransportError,
    _approved_endpoint_profile_sha256, _approved_endpoint_id,
    _is_valid_bitcoin_mainnet_address, _is_base58_pubkey, is_valid_xrpl_issued_currency_code,
    _solana_base58_decode,
)


_UNSET = object()
BITCOIN_MAX_MONEY_SATOSHIS = 2_100_000_000_000_000
BITCOIN_MAX_MONEY_SATOSHIS_TEXT = str(BITCOIN_MAX_MONEY_SATOSHIS)
UINT256_MAX_TEXT = str((1 << 256) - 1)


def _is_uint256_decimal(value: Any) -> bool:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]+", value) is None:
        return False
    canonical = value.lstrip("0") or "0"
    return (len(canonical) < len(UINT256_MAX_TEXT)
            or (len(canonical) == len(UINT256_MAX_TEXT) and canonical <= UINT256_MAX_TEXT))


@dataclass(frozen=True)
class OnChainFinalitySnapshot:
    """Worker-derived finality facts persisted with the exact normalized event.

    The snapshot is an application-attested interpretation of provider data,
    not a provider signature. Version 1 keeps Bitcoin confirmation semantics
    distinct from deterministic finalized-height networks.
    """
    version: int
    network_id: str
    status: str
    reference: str

    def __post_init__(self):
        if (isinstance(self.version, bool) or not isinstance(self.version, int)
                or self.version != 1
                or not isinstance(self.network_id, str) or self.network_id not in {
                    "bitcoin-mainnet", "ethereum-mainnet", "bnb-smart-chain-mainnet",
                    "solana-mainnet", "xrpl-mainnet",
                }
                or not isinstance(self.status, str)
                or not isinstance(self.reference, str) or not self.reference.strip()):
            raise ValueError("chain finality snapshot identity is invalid")
        if self.network_id == "bitcoin-mainnet":
            if (self.status != "CONFIRMED"
                    or re.fullmatch(r"confirmations-policy:min=[1-9][0-9]*", self.reference) is None):
                raise ValueError("Bitcoin finality snapshot must preserve its explicit confirmation policy")
        elif self.status != "FINALIZED":
            raise ValueError("deterministic finality snapshot must be FINALIZED")


@dataclass(frozen=True)
class NormalizedTransferEvent:
    event_id: str
    network_id: str
    provider: str
    scope: str
    asset_id: str
    mapping_id: str
    transaction_hash: str
    block_number: int
    block_hash: str
    event_index: Optional[int]
    from_address: str
    to_address: str
    amount_raw: str
    decimals: int
    block_time: str
    observed_at: str
    canonical_status: str
    provenance: str
    from_addresses: tuple[str, ...] = ()
    from_addresses_complete: bool = True
    finality_snapshot: Optional[OnChainFinalitySnapshot] = None

    def __post_init__(self):
        if isinstance(self.from_addresses, list):
            object.__setattr__(self, "from_addresses", tuple(self.from_addresses))
        if isinstance(self.finality_snapshot, dict):
            object.__setattr__(self, "finality_snapshot", OnChainFinalitySnapshot(**self.finality_snapshot))


class OnChainIngestionStore:
    """SQLite journal for event pages and their durable continuation cursors.

    Event identity is namespaced by network/provider/scope. A page's event rows
    and checkpoint move forward in one transaction: crashes cannot commit only
    one side. Replayed pages are idempotent; conflicting reuse of an identity
    fails closed. Reorgs are represented as retained REORGED tombstones.
    """

    _STATUSES = frozenset({"CANONICAL", "REORGED", "UNVERIFIED"})

    def __init__(self, database_path: str):
        Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(database_path, timeout=30)
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS layer1_onchain_ingestion_checkpoints (
            cursor_key TEXT PRIMARY KEY,
            cursor_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS layer1_onchain_transfer_events (
            network_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            scope TEXT NOT NULL,
            event_id TEXT NOT NULL,
            transaction_hash TEXT NOT NULL,
            block_number INTEGER NOT NULL,
            block_hash TEXT NOT NULL,
            canonical_status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            inserted_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(network_id, provider, scope, event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_onchain_transfer_block
            ON layer1_onchain_transfer_events(network_id, block_number, block_hash);
        CREATE INDEX IF NOT EXISTS idx_onchain_transfer_tx
            ON layer1_onchain_transfer_events(network_id, transaction_hash);
        CREATE TABLE IF NOT EXISTS layer1_onchain_ingestion_pages (
            page_id TEXT PRIMARY KEY,
            cursor_key TEXT NOT NULL,
            scope_identity_json TEXT,
            page_material_json TEXT NOT NULL,
            receipt_sha256 TEXT NOT NULL,
            receipts_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_onchain_ingestion_pages_cursor
            ON layer1_onchain_ingestion_pages(cursor_key, created_at, page_id);
        CREATE INDEX IF NOT EXISTS idx_onchain_ingestion_pages_scope_identity_parts
            ON layer1_onchain_ingestion_pages(
                (CASE WHEN json_valid(scope_identity_json) THEN json_extract(scope_identity_json, '$[0]') END),
                (CASE WHEN json_valid(scope_identity_json) THEN json_extract(scope_identity_json, '$[1]') END),
                (CASE WHEN json_valid(scope_identity_json) THEN json_extract(scope_identity_json, '$[2]') END)
            );
        CREATE TABLE IF NOT EXISTS layer1_onchain_ingestion_page_acceptances (
            page_id TEXT PRIMARY KEY REFERENCES layer1_onchain_ingestion_pages(page_id),
            cursor_key TEXT NOT NULL,
            key_id TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            signature TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS layer1_onchain_ingestion_page_acceptance_lifecycle (
            page_id TEXT PRIMARY KEY REFERENCES layer1_onchain_ingestion_page_acceptances(page_id),
            status TEXT NOT NULL CHECK (status = 'INVALIDATED'),
            reason_code TEXT NOT NULL CHECK (reason_code = 'CANONICAL_EVIDENCE_REORGED'),
            affected_evidence_json TEXT NOT NULL,
            invalidated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_onchain_page_acceptance_lifecycle_status
            ON layer1_onchain_ingestion_page_acceptance_lifecycle(status, invalidated_at, page_id);
        CREATE TABLE IF NOT EXISTS layer1_onchain_ingestion_blocks (
            network_id TEXT NOT NULL, provider TEXT NOT NULL, scope TEXT NOT NULL,
            block_number INTEGER NOT NULL, block_hash TEXT NOT NULL, block_time TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(network_id, provider, scope, block_number)
        );
        CREATE TABLE IF NOT EXISTS layer1_onchain_solana_slot_journal (
            network_id TEXT NOT NULL, provider TEXT NOT NULL, scope TEXT NOT NULL,
            slot INTEGER NOT NULL, produced INTEGER NOT NULL,
            block_hash TEXT, block_time TEXT, updated_at TEXT NOT NULL,
            PRIMARY KEY(network_id, provider, scope, slot)
        );
        CREATE TABLE IF NOT EXISTS layer1_onchain_solana_quarantine (
            network_id TEXT NOT NULL, provider TEXT NOT NULL, scope TEXT NOT NULL,
            signature TEXT NOT NULL, slot INTEGER NOT NULL, transaction_index INTEGER NOT NULL,
            block_hash TEXT NOT NULL, payload_json TEXT NOT NULL, source_page_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('PENDING', 'REPLAYED')),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(network_id, provider, scope, signature)
        );
        CREATE INDEX IF NOT EXISTS idx_solana_quarantine_pending
            ON layer1_onchain_solana_quarantine(network_id, provider, scope, status, slot, signature);
        """)

    @staticmethod
    def _canonical(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @staticmethod
    def _validate_acceptance_payload_matches_material(
        material: dict, cursor_key: str, page_id: str, key_id: str, payload_json: str,
    ) -> None:
        try:
            payload = json.loads(payload_json)
        except (TypeError, json.JSONDecodeError):
            raise ValueError("ingestion page acceptance payload is invalid JSON") from None
        if not isinstance(payload, dict) or OnChainIngestionStore._canonical(payload) != payload_json:
            raise ValueError("ingestion page acceptance payload is not canonical")
        if (
            payload.get("domain") != "BINANCE_SQUARE_W2E_ONCHAIN_INGESTION_PAGE_V1"
            or payload.get("receipt_version") != 1
            or payload.get("receipt_key_id") != key_id
            or payload.get("page_id") != page_id
            or payload.get("cursor_key") != cursor_key
            or payload.get("page_material") != material.get("page_material")
            or payload.get("receipts") != material.get("receipts")
            or payload.get("receipt_sha256") != material.get("receipt_sha256")
        ):
            raise ValueError("ingestion page acceptance snapshot no longer matches current canonical evidence")

    @classmethod
    def _validate_event(cls, event: NormalizedTransferEvent) -> None:
        if not isinstance(event, NormalizedTransferEvent):
            raise ValueError("page contains an invalid normalized transfer event")
        text_fields = (
            event.event_id, event.network_id, event.provider, event.scope,
            event.asset_id, event.mapping_id, event.transaction_hash,
            event.block_hash, event.to_address, event.amount_raw,
            event.block_time, event.observed_at, event.provenance,
        )
        if any(not isinstance(value, str) or not value.strip() for value in text_fields):
            raise ValueError("normalized transfer event identity and provenance fields are required")
        if event.from_address is not None and (
            not isinstance(event.from_address, str) or not event.from_address.strip()
        ):
            raise ValueError("from_address must be null or a non-empty address")
        if (not isinstance(event.from_addresses, (tuple, list))
                or any(not isinstance(address, str) or not address.strip()
                       for address in event.from_addresses)
                or len(set(event.from_addresses)) != len(event.from_addresses)):
            raise ValueError("from_addresses must contain unique non-empty source addresses")
        if not isinstance(event.from_addresses_complete, bool):
            raise ValueError("from_addresses_complete must be boolean")
        if (event.from_address is None and not event.from_addresses
                and event.network_id != "bitcoin-mainnet"):
            raise ValueError("non-Bitcoin transfer events require a source address")
        if (event.from_address is not None and event.from_addresses
                and (len(event.from_addresses) != 1 or event.from_address != event.from_addresses[0])):
            raise ValueError("from_address must match the single decoded from_addresses entry")
        if not re.fullmatch(r"[0-9]+", event.amount_raw):
            raise ValueError("amount_raw must be a non-negative integer base-unit string")
        if (isinstance(event.block_number, bool) or not isinstance(event.block_number, int)
                or event.block_number < 0):
            raise ValueError("block_number must be a non-negative integer")
        if (isinstance(event.decimals, bool) or not isinstance(event.decimals, int)
                or not 0 <= event.decimals <= 36):
            raise ValueError("decimals must be an integer from 0 to 36")
        if event.event_index is not None and (
            isinstance(event.event_index, bool) or not isinstance(event.event_index, int)
            or event.event_index < 0
        ):
            raise ValueError("event_index must be null or a non-negative integer")
        if not isinstance(event.canonical_status, str) or event.canonical_status not in cls._STATUSES:
            raise ValueError("canonical_status is not supported")
        if event.finality_snapshot is not None:
            if not isinstance(event.finality_snapshot, OnChainFinalitySnapshot):
                raise ValueError("normalized event finality snapshot is invalid")
            if event.finality_snapshot.network_id != event.network_id:
                raise ValueError("normalized event finality snapshot network does not match its event")
        for field in (event.block_time, event.observed_at):
            try:
                parsed = datetime.fromisoformat(field.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError("event timestamps must be timezone-aware ISO-8601") from None
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("event timestamps must be timezone-aware ISO-8601")

    def commit_page(self, cursor_key: str, next_cursor: Any,
                    events: Iterable[NormalizedTransferEvent], *,
                    allow_recanonicalized: bool = False,
                    canonical_blocks: Iterable[dict] = (),
                    canonical_slots: Iterable[dict] = (),
                    expected_cursor: Any = _UNSET,
                    scope_identity: Any = None,
                    provider_receipts: Optional[CapturedProviderReceiptBatch] = None,
                    provider_observations: Iterable[dict] = (),
                    solana_quarantine_records: Iterable[dict] = (),
                    solana_quarantine_replayed: Iterable[str] = ()) -> dict:
        if not isinstance(cursor_key, str) or not cursor_key.strip():
            raise ValueError("cursor_key must be a non-empty string")
        if expected_cursor is _UNSET:
            raise ValueError("SQLite commits require the checkpoint snapshot in expected_cursor")
        if not isinstance(allow_recanonicalized, bool):
            raise ValueError("allow_recanonicalized must be boolean")
        cursor_json = self._canonical(next_cursor)
        batch = tuple(events)
        blocks = tuple(canonical_blocks)
        slots = tuple(canonical_slots)
        quarantine_records = tuple(solana_quarantine_records)
        quarantine_replayed = tuple(solana_quarantine_replayed)
        anchor_observations = tuple(provider_observations)
        if provider_receipts is not None and (
            not isinstance(provider_receipts, CapturedProviderReceiptBatch)
            or not provider_receipts.is_collector_issued()
        ):
            raise ValueError("provider_receipts must be a captured provider receipt batch")
        receipts = provider_receipts.receipts if provider_receipts is not None else ()
        if any(item.sequence != index for index, item in enumerate(receipts, 1)):
            raise ValueError("provider response receipt sequence is invalid")
        if receipts and any(item.endpoint_profile_sha256 is None for item in receipts):
            raise ValueError("new provider receipts require an endpoint profile fingerprint")
        if receipts and scope_identity is None:
            raise ValueError("scope_identity is required when provider receipts are supplied")
        for event in batch:
            self._validate_event(event)
        for block in blocks:
            if (not isinstance(block, dict)
                    or not isinstance(block.get("network_id"), str) or not block["network_id"].strip()
                    or not isinstance(block.get("provider"), str) or not block["provider"].strip()
                    or not isinstance(block.get("scope"), str) or not block["scope"].strip()
                    or isinstance(block.get("block_number"), bool)
                    or not isinstance(block.get("block_number"), int) or block["block_number"] < 0
                    or not isinstance(block.get("block_hash"), str) or not block["block_hash"].strip()
                    or not isinstance(block.get("block_time"), str) or not block["block_time"].strip()):
                raise ValueError("canonical block checkpoint is malformed")
            try:
                parsed = datetime.fromisoformat(block["block_time"].replace("Z", "+00:00"))
            except ValueError:
                raise ValueError("canonical block time must be timezone-aware ISO-8601") from None
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("canonical block time must be timezone-aware ISO-8601")
        for slot in slots:
            if (not isinstance(slot, dict)
                    or slot.get("network_id") != "solana-mainnet"
                    or not isinstance(slot.get("provider"), str) or not slot["provider"].strip()
                    or not isinstance(slot.get("scope"), str) or not slot["scope"].strip()
                    or isinstance(slot.get("slot"), bool)
                    or not isinstance(slot.get("slot"), int) or slot["slot"] < 0
                    or not isinstance(slot.get("produced"), bool)):
                raise ValueError("canonical Solana slot journal record is malformed")
            if slot["produced"]:
                if not isinstance(slot.get("block_hash"), str) or not slot["block_hash"].strip():
                    raise ValueError("produced Solana slots require canonical block hash")
                if slot.get("block_time") is not None:
                    if not isinstance(slot.get("block_time"), str) or not slot["block_time"].strip():
                        raise ValueError("Solana slot block time must be null or timezone-aware ISO-8601")
                    try:
                        parsed = datetime.fromisoformat(slot["block_time"].replace("Z", "+00:00"))
                    except ValueError:
                        raise ValueError("Solana slot block time must be timezone-aware ISO-8601") from None
                    if parsed.tzinfo is None or parsed.utcoffset() is None:
                        raise ValueError("Solana slot block time must be timezone-aware ISO-8601")
            elif slot.get("block_hash") is not None or slot.get("block_time") is not None:
                raise ValueError("skipped Solana slots must not carry fabricated block hash or time")
        if anchor_observations and (scope_identity is None or not receipts):
            raise ValueError("provider observations require explicit scope identity and captured provider receipts")
        observation_ids = set()
        for item in anchor_observations:
            required_text = (
                "observation_id", "mapping_id", "asset_id", "network_id", "chain_id",
                "provider", "endpoint_id", "observation_type", "block_hash",
                "transaction_hash", "block_time", "observed_at", "finality",
                "finality_reference", "scope",
            )
            if (not isinstance(item, dict)
                    or any(not isinstance(item.get(field), str) or not item[field].strip()
                           for field in required_text)
                    or isinstance(item.get("block_height"), bool)
                    or not isinstance(item.get("block_height"), int)
                    or item["block_height"] <= 0
                    or item["observation_id"] in observation_ids):
                raise ValueError("provider observation page record is malformed or duplicated")
            observation_ids.add(item["observation_id"])
            expected_endpoint_id = _approved_endpoint_id(item["provider"], item["network_id"])
            if (item["network_id"], item["provider"], item["scope"]) != tuple(scope_identity):
                raise ValueError("provider observation identity does not match checkpoint scope_identity")
            if expected_endpoint_id is None or item["endpoint_id"] != expected_endpoint_id:
                raise ValueError("provider observation endpoint_id does not match the approved provider/network endpoint")
            if item["network_id"] == "solana-mainnet":
                slot = next((row for row in slots if row["slot"] == item["block_height"]), None)
                if (slot is None or not slot["produced"]
                        or slot.get("block_hash") != item["block_hash"]
                        or slot.get("block_time") != item["block_time"]):
                    raise ValueError("provider observation does not bind to canonical Solana slot evidence")
            else:
                block = next((row for row in blocks if row["block_number"] == item["block_height"]), None)
                if (block is None or block["block_hash"] != item["block_hash"]
                        or block["block_time"] != item["block_time"]):
                    raise ValueError("provider observation does not bind to canonical block evidence")
        if (quarantine_records or quarantine_replayed) and (
            scope_identity is None or not isinstance(scope_identity, (tuple, list))
            or len(scope_identity) != 3 or scope_identity[0] != "solana-mainnet"
        ):
            raise ValueError("Solana quarantine requires an explicit Solana scope identity")
        for record in quarantine_records:
            if (not isinstance(record, dict)
                    or isinstance(record.get("slot"), bool) or not isinstance(record.get("slot"), int)
                    or record["slot"] < 0
                    or isinstance(record.get("transaction_index"), bool)
                    or not isinstance(record.get("transaction_index"), int)
                    or record["transaction_index"] < 0
                    or not isinstance(record.get("signature"), str)
                    or re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{64,90}", record["signature"]) is None
                    or len(_solana_base58_decode(record["signature"])) != 64
                    or not isinstance(record.get("block_hash"), str)
                    or len(_solana_base58_decode(record["block_hash"])) != 32
                    or not isinstance(record.get("payload"), dict)
                    or not isinstance(record["payload"].get("raw"), dict)
                    or not isinstance(record["payload"]["raw"].get("transaction"), dict)
                    or not isinstance(record["payload"]["raw"].get("meta"), dict)
                    or "err" not in record["payload"]["raw"]["meta"]
                    or not isinstance(record["payload"]["raw"]["transaction"].get("signatures"), list)
                    or not record["payload"]["raw"]["transaction"]["signatures"]
                    or record["payload"]["raw"]["transaction"]["signatures"][0] != record["signature"]
                    or not isinstance(record["payload"]["raw"]["transaction"].get("message"), dict)
                    or isinstance(record["payload"]["raw"].get("slot"), bool)
                    or not isinstance(record["payload"]["raw"].get("slot"), int)
                    or record["payload"]["raw"].get("slot") != record["slot"]
                    or record["payload"]["raw"].get("signature") not in (None, record["signature"])
                    or ("blockTime" in record["payload"]["raw"] and (
                        (record["payload"]["raw"].get("blockTime") is not None and (
                            isinstance(record["payload"]["raw"].get("blockTime"), bool)
                            or not isinstance(record["payload"]["raw"].get("blockTime"), int)
                            or record["payload"]["raw"].get("blockTime") <= 0))
                        or record["payload"]["raw"].get("blockTime") != record["payload"].get("block_time")
                    ))
                    or not isinstance(record["payload"].get("observed_at"), str)
                    or record["payload"].get("block_time") is not None
                       and (isinstance(record["payload"].get("block_time"), bool)
                            or not isinstance(record["payload"].get("block_time"), int)
                            or record["payload"]["block_time"] <= 0)):
                raise ValueError("Solana quarantine transaction record is malformed")
            try:
                quarantine_observed_at = datetime.fromisoformat(record["payload"]["observed_at"].replace("Z", "+00:00"))
            except ValueError:
                raise ValueError("Solana quarantine observed_at must be timezone-aware ISO-8601") from None
            if quarantine_observed_at.tzinfo is None or quarantine_observed_at.utcoffset() is None:
                raise ValueError("Solana quarantine observed_at must be timezone-aware ISO-8601")
            if len(_solana_base58_decode(record["signature"])) != 64:
                raise ValueError("Solana quarantine signature must decode to 64 bytes")
        if (len({record["signature"] for record in quarantine_records}) != len(quarantine_records)
                or any(not isinstance(signature, str) or re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{64,90}", signature) is None
                       or len(_solana_base58_decode(signature)) != 64
                       for signature in quarantine_replayed)
                or len(set(quarantine_replayed)) != len(quarantine_replayed)):
            raise ValueError("Solana quarantine signatures are malformed or duplicated")
        if scope_identity is not None:
            if (not isinstance(scope_identity, (tuple, list)) or len(scope_identity) != 3
                    or any(not isinstance(part, str) or not part.strip() for part in scope_identity)):
                raise ValueError("scope_identity must be (network_id, provider, scope)")
            if any((event.network_id, event.provider, event.scope) != tuple(scope_identity) for event in batch):
                raise ValueError("event identity does not match checkpoint scope_identity")
            if any((block["network_id"], block["provider"], block["scope"]) != tuple(scope_identity)
                   for block in blocks):
                raise ValueError("canonical block identity does not match checkpoint scope_identity")
            if any((slot["network_id"], slot["provider"], slot["scope"]) != tuple(scope_identity)
                   for slot in slots):
                raise ValueError("canonical slot identity does not match checkpoint scope_identity")
        if scope_identity is not None and any(
            (item.network_id, item.provider) != (scope_identity[0], scope_identity[1])
            for item in receipts
        ):
            raise ValueError("provider receipt identity does not match checkpoint scope_identity")
        if receipts and any(
            _approved_endpoint_profile_sha256(item.provider, item.network_id) is None
            or item.endpoint_profile_sha256 != _approved_endpoint_profile_sha256(item.provider, item.network_id)
            for item in receipts
        ):
            raise ValueError("provider receipt fingerprint does not match the approved provider/network endpoint profile")
        now = datetime.now(timezone.utc).isoformat()
        inserted = duplicates = tombstoned = 0
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            if expected_cursor is not _UNSET:
                current = self.conn.execute(
                    "SELECT cursor_json FROM layer1_onchain_ingestion_checkpoints WHERE cursor_key=?",
                    (cursor_key,),
                ).fetchone()
                current_cursor = json.loads(current[0]) if current else None
                if current_cursor != expected_cursor:
                    raise RuntimeError("checkpoint changed before commit")
            for event in batch:
                payload_json = self._canonical(asdict(event))
                identity = (event.network_id, event.provider, event.scope, event.event_id)
                existing = self.conn.execute(
                    """SELECT payload_json, canonical_status
                       FROM layer1_onchain_transfer_events
                       WHERE network_id=? AND provider=? AND scope=? AND event_id=?""",
                    identity,
                ).fetchone()
                if existing:
                    if existing[0] != payload_json:
                        prior_payload = json.loads(existing[0])
                        incoming_payload = json.loads(payload_json)
                        prior_status = prior_payload.pop("canonical_status", None)
                        incoming_status = incoming_payload.pop("canonical_status", None)
                        if prior_payload != incoming_payload:
                            if allow_recanonicalized and prior_status == "REORGED" and incoming_status == "CANONICAL":
                                prior_core = dict(prior_payload)
                                incoming_core = dict(incoming_payload)
                                for field in ("block_number", "block_hash", "block_time", "observed_at"):
                                    prior_core.pop(field, None)
                                    incoming_core.pop(field, None)
                                if prior_core != incoming_core:
                                    raise ValueError("transfer event identity collision: re-included event payload differs")
                                self.conn.execute(
                                    """UPDATE layer1_onchain_transfer_events
                                       SET block_number=?, block_hash=?, canonical_status='CANONICAL',
                                           payload_json=?, updated_at=?
                                       WHERE network_id=? AND provider=? AND scope=? AND event_id=?""",
                                    (event.block_number, event.block_hash, payload_json, now, *identity),
                                )
                            else:
                                raise ValueError("transfer event identity collision: refusing conflicting event payload")
                        elif prior_status == "CANONICAL" and incoming_status == "REORGED":
                            tombstone_payload = dict(asdict(event))
                            self.conn.execute(
                                """UPDATE layer1_onchain_transfer_events
                                   SET canonical_status='REORGED', payload_json=?, updated_at=?
                                   WHERE network_id=? AND provider=? AND scope=? AND event_id=?""",
                                (self._canonical(tombstone_payload), now, *identity),
                            )
                        elif (prior_status != incoming_status and prior_status != "REORGED"
                              and incoming_status != "REORGED"):
                            raise ValueError("transfer event identity collision: refusing non-monotonic status change")
                    duplicates += 1
                    if event.canonical_status == "REORGED":
                        tombstoned += 1
                    continue
                self.conn.execute(
                    """INSERT INTO layer1_onchain_transfer_events
                       (network_id, provider, scope, event_id, transaction_hash,
                        block_number, block_hash, canonical_status, payload_json,
                        inserted_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (*identity, event.transaction_hash, event.block_number,
                     event.block_hash, event.canonical_status, payload_json, now, now),
                )
                inserted += 1
                if event.canonical_status == "REORGED":
                    tombstoned += 1
            reorg_changes: list[tuple[int, Optional[str]]] = []
            for block in blocks:
                prior = self.conn.execute(
                    """SELECT block_hash, block_time FROM layer1_onchain_ingestion_blocks
                       WHERE network_id=? AND provider=? AND scope=? AND block_number=?""",
                    (block["network_id"], block["provider"], block["scope"], block["block_number"]),
                ).fetchone()
                if prior and prior[0] == block["block_hash"] and prior[1] != block["block_time"]:
                    raise ValueError("canonical block journal timestamp conflict")
                if prior and prior[0] != block["block_hash"]:
                    active = self.conn.execute(
                        """SELECT 1 FROM layer1_onchain_transfer_events
                           WHERE network_id=? AND provider=? AND scope=? AND block_number=?
                             AND block_hash=? AND canonical_status='CANONICAL' LIMIT 1""",
                        (block["network_id"], block["provider"], block["scope"],
                         block["block_number"], prior[0]),
                    ).fetchone()
                    if not allow_recanonicalized or active:
                        raise ValueError("canonical block hash conflict")
                    reorg_changes.append((block["block_number"], block["block_hash"]))
                self.conn.execute(
                    """INSERT INTO layer1_onchain_ingestion_blocks
                       (network_id, provider, scope, block_number, block_hash, block_time, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(network_id, provider, scope, block_number) DO UPDATE SET
                         block_hash=excluded.block_hash, block_time=excluded.block_time,
                         updated_at=excluded.updated_at""",
                    (block["network_id"], block["provider"], block["scope"],
                     block["block_number"], block["block_hash"], block["block_time"], now),
                )
            for slot in slots:
                prior = self.conn.execute(
                    """SELECT produced, block_hash, block_time FROM layer1_onchain_solana_slot_journal
                       WHERE network_id=? AND provider=? AND scope=? AND slot=?""",
                    (slot["network_id"], slot["provider"], slot["scope"], slot["slot"]),
                ).fetchone()
                incoming = (int(slot["produced"]), slot.get("block_hash"), slot.get("block_time"))
                time_enrichment = bool(
                    prior and prior[:2] == incoming[:2]
                    and prior[2] is None and incoming[2] is not None
                )
                if prior and prior[:2] == incoming[:2] and prior[2] is not None and incoming[2] is None:
                    raise ValueError("canonical Solana slot time cannot regress to unknown")
                if prior and prior[:2] == incoming[:2] and prior[2] is not None and incoming[2] is not None and prior[2] != incoming[2]:
                    raise ValueError("canonical Solana slot timestamp conflict")
                if prior and prior != incoming and not time_enrichment:
                    active = self.conn.execute(
                        """SELECT 1 FROM layer1_onchain_transfer_events
                           WHERE network_id='solana-mainnet' AND provider=? AND scope=?
                             AND block_number=? AND block_hash IS ?
                             AND canonical_status='CANONICAL' LIMIT 1""",
                        (slot["provider"], slot["scope"], slot["slot"], prior[1]),
                    ).fetchone()
                    if not allow_recanonicalized or active:
                        raise ValueError("canonical Solana slot journal conflict")
                    reorg_changes.append((slot["slot"], slot.get("block_hash")))
                self.conn.execute(
                    """INSERT INTO layer1_onchain_solana_slot_journal
                       (network_id, provider, scope, slot, produced, block_hash, block_time, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(network_id, provider, scope, slot) DO UPDATE SET
                         produced=excluded.produced, block_hash=excluded.block_hash,
                         block_time=excluded.block_time, updated_at=excluded.updated_at""",
                    (slot["network_id"], slot["provider"], slot["scope"], slot["slot"],
                     int(slot["produced"]), slot.get("block_hash"), slot.get("block_time"), now),
                )
            if scope_identity is not None:
                scope_network_id, scope_provider, scope_name = scope_identity
                for changed_height, changed_hash in reorg_changes:
                    self._invalidate_page_acceptances_for_reorg(
                        scope_network_id, scope_provider, scope_name,
                        changed_height, changed_hash, now,
                    )
            # Bind the ordered provider response receipts to the exact normalized
            # page inputs. A retry with identical inputs is idempotent; a replay
            # that substitutes different response evidence fails closed.
            page_material = {
                "cursor_key": cursor_key,
                "expected_cursor": {"_unset": True} if expected_cursor is _UNSET else expected_cursor,
                "next_cursor": next_cursor,
                "scope_identity": list(scope_identity) if scope_identity is not None else None,
                "events": [asdict(event) for event in batch],
                "canonical_blocks": list(blocks),
                "canonical_slots": list(slots),
            }
            if quarantine_records:
                page_material["solana_quarantine_records"] = list(quarantine_records)
            if quarantine_replayed:
                page_material["solana_quarantine_replayed"] = list(quarantine_replayed)
            if anchor_observations:
                page_material["provider_observations"] = list(anchor_observations)
            page_id = hashlib.sha256(self._canonical(page_material).encode("utf-8")).hexdigest()
            receipts_payload = [asdict(item) for item in receipts]
            receipts_json = self._canonical(receipts_payload)
            receipt_sha256 = hashlib.sha256(receipts_json.encode("utf-8")).hexdigest()
            prior_page = self.conn.execute(
                "SELECT receipt_sha256 FROM layer1_onchain_ingestion_pages WHERE page_id=?",
                (page_id,),
            ).fetchone()
            if prior_page and prior_page[0] != receipt_sha256:
                raise ValueError("provider receipt replay conflict: page identity has different response evidence")
            if prior_page is None:
                self.conn.execute(
                    """INSERT INTO layer1_onchain_ingestion_pages
                       (page_id, cursor_key, scope_identity_json, page_material_json,
                        receipt_sha256, receipts_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (page_id, cursor_key,
                     self._canonical(list(scope_identity)) if scope_identity is not None else None,
                     self._canonical(page_material), receipt_sha256, receipts_json, now),
                )
            for record in quarantine_records:
                payload_json = self._canonical(record["payload"])
                identity = ("solana-mainnet", scope_identity[1], scope_identity[2], record["signature"])
                prior = self.conn.execute(
                    """SELECT slot, transaction_index, block_hash, payload_json, source_page_id
                       FROM layer1_onchain_solana_quarantine
                       WHERE network_id=? AND provider=? AND scope=? AND signature=?""",
                    identity,
                ).fetchone()
                expected = (record["slot"], record["transaction_index"], record["block_hash"], payload_json)
                if prior is not None and prior[:4] != expected:
                    raise ValueError("Solana quarantine transaction identity collision")
                if prior is None:
                    self.conn.execute(
                        """INSERT INTO layer1_onchain_solana_quarantine
                           (network_id, provider, scope, signature, slot, transaction_index,
                            block_hash, payload_json, source_page_id, status, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)""",
                        (*identity, record["slot"], record["transaction_index"],
                         record["block_hash"], payload_json, page_id, now, now),
                    )
            for signature in quarantine_replayed:
                result = self.conn.execute(
                    """UPDATE layer1_onchain_solana_quarantine SET status='REPLAYED', updated_at=?
                       WHERE network_id='solana-mainnet' AND provider=? AND scope=?
                         AND signature=? AND status='PENDING'""",
                    (now, scope_identity[1], scope_identity[2], signature),
                )
                if result.rowcount != 1:
                    raise ValueError("Solana quarantine replay does not reference one pending transaction")
            self.conn.execute(
                """INSERT INTO layer1_onchain_ingestion_checkpoints(cursor_key, cursor_json, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(cursor_key) DO UPDATE SET
                     cursor_json=excluded.cursor_json, updated_at=excluded.updated_at""",
                (cursor_key, cursor_json, now),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return {"inserted": inserted, "duplicates": duplicates, "tombstoned": tombstoned}

    def list_page_receipts(self, cursor_key: str) -> tuple[ProviderResponseReceipt, ...]:
        """Load persisted provider response receipts in ingestion-page order."""
        if not isinstance(cursor_key, str) or not cursor_key.strip():
            raise ValueError("cursor_key must be a non-empty string")
        rows = self.conn.execute(
            """SELECT page_id, page_material_json, receipt_sha256, receipts_json
               FROM layer1_onchain_ingestion_pages
               WHERE cursor_key=? ORDER BY created_at, page_id""",
            (cursor_key,),
        ).fetchall()
        result = []
        for page_id, page_material_json, expected_digest, receipts_json in rows:
            page_material = json.loads(page_material_json)
            page_digest = hashlib.sha256(
                self._canonical(page_material).encode("utf-8")
            ).hexdigest()
            if page_digest != page_id:
                raise ValueError("persisted provider page identity digest mismatch")
            payload = json.loads(receipts_json)
            canonical = self._canonical(payload)
            actual_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if actual_digest != expected_digest:
                raise ValueError("persisted provider receipt digest mismatch")
            if not isinstance(payload, list):
                raise ValueError("persisted provider receipt collection is malformed")
            receipts = tuple(ProviderResponseReceipt(**item) for item in payload)
            if any(item.sequence != index for index, item in enumerate(receipts, 1)):
                raise ValueError("persisted provider receipt sequence is invalid")
            result.extend(receipts)
        return tuple(result)

    def get_page_acceptance_material(self, cursor_key: str, page_id: str) -> dict:
        """Re-read and validate the committed page, its receipts and canonical evidence."""
        if not isinstance(cursor_key, str) or not cursor_key.strip() or not isinstance(page_id, str) or re.fullmatch(r"[a-f0-9]{64}", page_id) is None:
            raise ValueError("cursor_key and page_id are required")
        row = self.conn.execute(
            """SELECT cursor_key, page_material_json, receipt_sha256, receipts_json
               FROM layer1_onchain_ingestion_pages WHERE page_id=?""",
            (page_id,),
        ).fetchone()
        if row is None or row[0] != cursor_key:
            raise ValueError("persisted ingestion page does not match requested cursor/page identity")
        page_material = json.loads(row[1])
        if (page_material.get("cursor_key") != cursor_key
                or hashlib.sha256(self._canonical(page_material).encode("utf-8")).hexdigest() != page_id):
            raise ValueError("persisted provider page identity digest mismatch")
        receipts_payload = json.loads(row[3])
        receipts_json = self._canonical(receipts_payload)
        if hashlib.sha256(receipts_json.encode("utf-8")).hexdigest() != row[2]:
            raise ValueError("persisted provider receipt digest mismatch")
        receipts = tuple(ProviderResponseReceipt(**item) for item in receipts_payload)
        if not receipts or any(item.sequence != index for index, item in enumerate(receipts, 1)):
            raise ValueError("ingestion page has no complete captured provider receipt lineage")
        if any(
            item.endpoint_profile_sha256 is None
            or _approved_endpoint_profile_sha256(item.provider, item.network_id) is None
            or item.endpoint_profile_sha256 != _approved_endpoint_profile_sha256(item.provider, item.network_id)
            for item in receipts
        ):
            raise ValueError("persisted provider receipt lacks or mismatches the approved provider/network endpoint profile fingerprint")
        scope_identity = page_material.get("scope_identity")
        if (not isinstance(scope_identity, list) or len(scope_identity) != 3
                or any(not isinstance(value, str) or not value for value in scope_identity)
                or any((item.network_id, item.provider) != tuple(scope_identity[:2]) for item in receipts)):
            raise ValueError("persisted provider receipt scope identity is invalid")
        events = page_material.get("events")
        blocks = page_material.get("canonical_blocks")
        slots = page_material.get("canonical_slots")
        if not isinstance(events, list) or not isinstance(blocks, list) or not isinstance(slots, list):
            raise ValueError("persisted normalized event or canonical evidence collections are malformed")
        if not blocks and not slots:
            raise ValueError("ingestion page has no canonical block/slot evidence to bind")
        if any((block.get("network_id"), block.get("provider"), block.get("scope")) != tuple(scope_identity)
               for block in blocks):
            raise ValueError("persisted canonical block evidence crosses the page scope")
        if any((slot.get("network_id"), slot.get("provider"), slot.get("scope")) != tuple(scope_identity)
               for slot in slots):
            raise ValueError("persisted canonical slot evidence crosses the page scope")
        provider_observations = page_material.get("provider_observations", [])
        if not isinstance(provider_observations, list):
            raise ValueError("persisted provider observation collection is malformed")
        block_evidence = {
            (block["block_number"]): (block["block_hash"], block["block_time"])
            for block in blocks
        }
        for payload in events:
            event = NormalizedTransferEvent(**payload)
            self._validate_event(event)
            if (event.network_id, event.provider, event.scope) != tuple(scope_identity):
                raise ValueError("persisted normalized event crosses the page scope")
            if block_evidence.get(event.block_number) != (event.block_hash, event.block_time):
                raise ValueError("normalized event does not bind to its page canonical block evidence")
            persisted = self.get_event(event.event_id, event.network_id, event.provider, event.scope)
            if persisted != event or event.canonical_status != "CANONICAL":
                raise ValueError("persisted normalized event no longer matches the committed canonical page")
        slot_evidence = {
            slot["slot"]: (slot.get("produced"), slot.get("block_hash"), slot.get("block_time"))
            for slot in slots
        }
        observation_ids = set()
        for item in provider_observations:
            required_text = (
                "observation_id", "mapping_id", "asset_id", "network_id", "chain_id",
                "provider", "endpoint_id", "observation_type", "block_hash",
                "transaction_hash", "block_time", "observed_at", "finality",
                "finality_reference", "scope",
            )
            if (not isinstance(item, dict)
                    or any(not isinstance(item.get(field), str) or not item[field].strip()
                           for field in required_text)
                    or isinstance(item.get("block_height"), bool)
                    or not isinstance(item.get("block_height"), int)
                    or item["block_height"] <= 0
                    or item["observation_id"] in observation_ids
                    or (item["network_id"], item["provider"], item["scope"]) != tuple(scope_identity)):
                raise ValueError("persisted provider observation identity is malformed or outside page scope")
            observation_ids.add(item["observation_id"])
            expected_endpoint_id = _approved_endpoint_id(item["provider"], item["network_id"])
            if expected_endpoint_id is None or item["endpoint_id"] != expected_endpoint_id:
                raise ValueError("persisted provider observation endpoint_id does not match approved endpoint")
            if item["network_id"] == "solana-mainnet":
                if slot_evidence.get(item["block_height"]) != (
                    True, item["block_hash"], item["block_time"],
                ):
                    raise ValueError("persisted provider observation does not bind to canonical Solana slot evidence")
            elif block_evidence.get(item["block_height"]) != (
                item["block_hash"], item["block_time"],
            ):
                raise ValueError("persisted provider observation does not bind to canonical block evidence")
        for block in blocks:
            actual = self.conn.execute(
                """SELECT block_hash, block_time FROM layer1_onchain_ingestion_blocks
                   WHERE network_id=? AND provider=? AND scope=? AND block_number=?""",
                (block["network_id"], block["provider"], block["scope"], block["block_number"]),
            ).fetchone()
            if actual != (block["block_hash"], block["block_time"]):
                raise ValueError("persisted canonical block evidence no longer matches the committed page")
        for slot in slots:
            actual = self.conn.execute(
                """SELECT produced, block_hash, block_time FROM layer1_onchain_solana_slot_journal
                   WHERE network_id=? AND provider=? AND scope=? AND slot=?""",
                (slot["network_id"], slot["provider"], slot["scope"], slot["slot"]),
            ).fetchone()
            expected = (int(slot["produced"]), slot.get("block_hash"), slot.get("block_time"))
            if actual != expected and not (
                expected[0] == 1 and actual is not None
                and actual[0] == 1 and actual[1] == expected[1]
                and expected[2] is None and actual[2] is not None
            ):
                raise ValueError("persisted canonical Solana slot evidence no longer matches the committed page")
        for record in page_material.get("solana_quarantine_records", []):
            stored = self.conn.execute(
                """SELECT slot, transaction_index, block_hash, payload_json, source_page_id
                   FROM layer1_onchain_solana_quarantine
                   WHERE network_id=? AND provider=? AND scope=? AND signature=?""",
                (*scope_identity, record["signature"]),
            ).fetchone()
            expected = (record["slot"], record["transaction_index"], record["block_hash"],
                        self._canonical(record["payload"]), page_id)
            if stored is None or stored != expected:
                raise ValueError("persisted Solana quarantine record no longer matches its source page")
        for signature in page_material.get("solana_quarantine_replayed", []):
            stored = self.conn.execute(
                """SELECT status FROM layer1_onchain_solana_quarantine
                   WHERE network_id=? AND provider=? AND scope=? AND signature=?""",
                (*scope_identity, signature),
            ).fetchone()
            if stored is None or stored[0] != "REPLAYED":
                raise ValueError("persisted Solana quarantine replay is not finalized")
        return {
            "page_id": page_id, "cursor_key": cursor_key,
            "page_material": page_material, "receipts": receipts_payload,
            "receipt_sha256": row[2],
        }

    def save_page_acceptance(self, cursor_key: str, page_id: str, key_id: str,
                             payload_json: str, payload_sha256: str, signature: str) -> str:
        if (not isinstance(key_id, str) or re.fullmatch(r"[A-Za-z0-9._-]{1,128}", key_id) is None
                or not isinstance(payload_json, str) or not isinstance(payload_sha256, str)
                or re.fullmatch(r"[a-f0-9]{64}", payload_sha256) is None
                or not isinstance(signature, str) or re.fullmatch(r"[a-f0-9]{64}", signature) is None
                or hashlib.sha256(payload_json.encode("utf-8")).hexdigest() != payload_sha256
                or self._canonical(json.loads(payload_json)) != payload_json):
            raise ValueError("ingestion page acceptance envelope is malformed")
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            material = self.get_page_acceptance_material(cursor_key, page_id)
            self._validate_acceptance_payload_matches_material(
                material, cursor_key, page_id, key_id, payload_json,
            )
            envelope = (cursor_key, key_id, payload_sha256, payload_json, signature)
            prior = self.conn.execute(
                """SELECT cursor_key, key_id, payload_sha256, payload_json, signature
                   FROM layer1_onchain_ingestion_page_acceptances WHERE page_id=?""",
                (page_id,),
            ).fetchone()
            if prior is not None:
                if prior != envelope:
                    raise ValueError("ingestion page acceptance already exists with conflicting signer evidence")
                self.conn.commit()
                return "DUPLICATE"
            self.conn.execute(
                """INSERT INTO layer1_onchain_ingestion_page_acceptances
                   (page_id, cursor_key, key_id, payload_sha256, payload_json, signature, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (page_id, *envelope, now),
            )
            self.conn.commit()
            return "INSERTED"
        except Exception:
            self.conn.rollback()
            raise

    def list_ingestion_pages(self) -> tuple[tuple[str, str], ...]:
        """List durable page identities for downstream acceptance verification."""
        rows = self.conn.execute(
            "SELECT cursor_key, page_id FROM layer1_onchain_ingestion_pages ORDER BY created_at, page_id"
        ).fetchall()
        return tuple((cursor_key, page_id) for cursor_key, page_id in rows)

    @staticmethod
    def _page_material_requires_acceptance(page_material: Any) -> bool:
        """Whether a page contains provider-derived evidence that needs HMAC acceptance."""
        if not isinstance(page_material, dict):
            # Malformed persisted material must remain visible for rejection/review.
            return True
        return any(
            page_material.get(field, []) not in (None, [])
            for field in ("events", "canonical_blocks", "canonical_slots", "provider_observations",
                          "solana_quarantine_records", "solana_quarantine_replayed")
        )

    def list_pending_page_acceptances(self) -> tuple[tuple[str, str], ...]:
        rows = self.conn.execute(
            """SELECT p.cursor_key, p.page_id, p.page_material_json, p.receipts_json
               FROM layer1_onchain_ingestion_pages AS p
               LEFT JOIN layer1_onchain_ingestion_page_acceptances AS a ON a.page_id=p.page_id
               WHERE a.page_id IS NULL ORDER BY p.created_at, p.page_id"""
        ).fetchall()
        pending = []
        for cursor_key, page_id, page_material_json, receipts_json in rows:
            # Checkpoint-only commits intentionally have no provider evidence and
            # need no page acceptance. Every evidence-bearing page must be
            # visible to recovery even when its receipt batch is missing/empty.
            receipt_present = (
                not isinstance(receipts_json, str)
                or receipts_json.strip() not in ("", "[]")
            )
            try:
                page_material = json.loads(page_material_json)
            except (TypeError, ValueError):
                page_material = None
            if receipt_present or self._page_material_requires_acceptance(page_material):
                pending.append((cursor_key, page_id))
        return tuple(pending)

    def list_invalidated_page_acceptances(self) -> tuple[dict, ...]:
        """Return immutable signed envelopes with reorg invalidation evidence for operator review."""
        rows = self.conn.execute(
            """SELECT a.cursor_key, a.page_id, l.reason_code, l.affected_evidence_json,
                      l.invalidated_at, a.key_id, a.payload_sha256, a.signature,
                      a.payload_json, a.created_at
               FROM layer1_onchain_ingestion_page_acceptance_lifecycle AS l
               JOIN layer1_onchain_ingestion_page_acceptances AS a ON a.page_id=l.page_id
               WHERE l.status='INVALIDATED' ORDER BY l.invalidated_at, a.page_id"""
        ).fetchall()
        return tuple({
            "cursor_key": row[0], "page_id": row[1], "status": "INVALIDATED",
            "reason_code": row[2], "affected_evidence": json.loads(row[3]),
            "invalidated_at": row[4], "key_id": row[5],
            "payload_sha256": row[6], "signature": row[7],
            "payload_json": json.loads(row[8]), "accepted_at": row[9],
        } for row in rows)

    def _invalidate_page_acceptances_for_reorg(
        self, network_id: str, provider: Optional[str], scope: Optional[str], block_number: int,
        canonical_block_hash: str, invalidated_at: str,
    ) -> int:
        rows = self.conn.execute(
            """SELECT p.page_id, p.page_material_json
               FROM layer1_onchain_ingestion_pages AS p
               JOIN layer1_onchain_ingestion_page_acceptances AS a ON a.page_id=p.page_id
               LEFT JOIN layer1_onchain_ingestion_page_acceptance_lifecycle AS l ON l.page_id=p.page_id
               WHERE (CASE WHEN json_valid(p.scope_identity_json)
                            THEN json_extract(p.scope_identity_json, '$[0]') END)=?
                 AND (? IS NULL OR (CASE WHEN json_valid(p.scope_identity_json)
                                         THEN json_extract(p.scope_identity_json, '$[1]') END)=?)
                 AND (? IS NULL OR (CASE WHEN json_valid(p.scope_identity_json)
                                         THEN json_extract(p.scope_identity_json, '$[2]') END)=?)
                 AND l.page_id IS NULL""",
            (network_id, provider, provider, scope, scope),
        ).fetchall()
        invalidated = 0
        for page_id, material_json in rows:
            try:
                material = json.loads(material_json)
            except (TypeError, ValueError):
                continue
            affected = []
            for field, height_field, kind in (
                ("canonical_blocks", "block_number", "CANONICAL_BLOCK"),
                ("canonical_slots", "slot", "CANONICAL_SLOT"),
                ("events", "block_number", "TRANSFER_EVENT"),
                ("provider_observations", "block_height", "PROVIDER_OBSERVATION"),
            ):
                for item in material.get(field, []) if isinstance(material, dict) else []:
                    if (not isinstance(item, dict) or item.get("network_id") != network_id
                            or (provider is not None and item.get("provider") != provider)
                            or (scope is not None and item.get("scope") != scope)
                            or item.get(height_field) != block_number):
                        continue
                    old_hash = item.get("block_hash")
                    if old_hash is None and kind == "CANONICAL_SLOT":
                        old_hash = "SKIPPED"
                    if old_hash != canonical_block_hash:
                        affected.append({
                            "kind": kind, "network_id": network_id,
                            "provider": item.get("provider"), "scope": item.get("scope"),
                            "height": block_number,
                            "canonical_block_hash": old_hash,
                            "current_canonical_hash": canonical_block_hash,
                        })
            if affected:
                self.conn.execute(
                    """INSERT INTO layer1_onchain_ingestion_page_acceptance_lifecycle
                       (page_id, status, reason_code, affected_evidence_json, invalidated_at)
                       VALUES (?, 'INVALIDATED', 'CANONICAL_EVIDENCE_REORGED', ?, ?)
                       ON CONFLICT(page_id) DO NOTHING""",
                    (page_id, self._canonical(affected), invalidated_at),
                )
                invalidated += 1
        return invalidated

    def get_page_acceptance(self, cursor_key: str, page_id: str) -> Optional[dict]:
        row = self.conn.execute(
            """SELECT cursor_key, key_id, payload_sha256, payload_json, signature
               FROM layer1_onchain_ingestion_page_acceptances WHERE page_id=?""",
            (page_id,),
        ).fetchone()
        if row is None:
            return None
        if row[0] != cursor_key:
            raise ValueError("stored ingestion page acceptance belongs to a different cursor")
        return {"cursor_key": row[0], "key_id": row[1], "payload_sha256": row[2],
                "payload_json": row[3], "signature": row[4]}

    def get_checkpoint(self, cursor_key: str) -> Optional[Any]:
        row = self.conn.execute(
            "SELECT cursor_json FROM layer1_onchain_ingestion_checkpoints WHERE cursor_key=?",
            (cursor_key,),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def get_event(self, event_id: str, network_id: str, provider: Optional[str] = None,
                  scope: Optional[str] = None) -> Optional[NormalizedTransferEvent]:
        query = """SELECT payload_json FROM layer1_onchain_transfer_events
                   WHERE event_id=? AND network_id=?"""
        params: list[Any] = [event_id, network_id]
        if provider is not None:
            query += " AND provider=?"
            params.append(provider)
        if scope is not None:
            query += " AND scope=?"
            params.append(scope)
        rows = self.conn.execute(query, params).fetchall()
        if len(rows) > 1:
            raise ValueError("event identity is ambiguous; provider and scope are required")
        return NormalizedTransferEvent(**json.loads(rows[0][0])) if rows else None

    def list_events(self, network_id: str, canonical_only: bool = False) -> list[NormalizedTransferEvent]:
        query = """SELECT payload_json FROM layer1_onchain_transfer_events WHERE network_id=?"""
        params: list[Any] = [network_id]
        if canonical_only:
            query += " AND canonical_status='CANONICAL'"
        query += " ORDER BY block_number, transaction_hash, event_id"
        return [NormalizedTransferEvent(**json.loads(row[0]))
                for row in self.conn.execute(query, params).fetchall()]

    def list_all_events(self, canonical_only: bool = False) -> list[NormalizedTransferEvent]:
        """Return persisted events across configured networks in stable order."""
        query = "SELECT payload_json FROM layer1_onchain_transfer_events"
        if canonical_only:
            query += " WHERE canonical_status='CANONICAL'"
        query += " ORDER BY network_id, block_number, transaction_hash, event_id, scope"
        return [NormalizedTransferEvent(**json.loads(row[0]))
                for row in self.conn.execute(query).fetchall()]

    def get_block_hash(self, network_id: str, provider: str, scope: str,
                       block_number: int) -> Optional[str]:
        row = self.conn.execute(
            """SELECT block_hash FROM layer1_onchain_ingestion_blocks
               WHERE network_id=? AND provider=? AND scope=? AND block_number=?""",
            (network_id, provider, scope, block_number),
        ).fetchone()
        return row[0] if row else None

    def get_solana_slot_journal(self, network_id: str, provider: str, scope: str,
                                start_slot: int, end_slot: int) -> dict[int, dict]:
        if (not isinstance(network_id, str) or not isinstance(provider, str)
                or not isinstance(scope, str) or isinstance(start_slot, bool)
                or not isinstance(start_slot, int) or isinstance(end_slot, bool)
                or not isinstance(end_slot, int) or start_slot < 0 or end_slot < start_slot):
            raise ValueError("Solana slot journal query bounds are invalid")
        rows = self.conn.execute(
            """SELECT slot, produced, block_hash, block_time
               FROM layer1_onchain_solana_slot_journal
               WHERE network_id=? AND provider=? AND scope=? AND slot BETWEEN ? AND ?
               ORDER BY slot""",
            (network_id, provider, scope, start_slot, end_slot),
        ).fetchall()
        return {
            row[0]: {"produced": bool(row[1]), "block_hash": row[2], "block_time": row[3]}
            for row in rows
        }

    def list_pending_solana_quarantine(self, network_id: str, provider: str, scope: str,
                                       limit: int = 100) -> list[dict]:
        if (network_id != "solana-mainnet" or not isinstance(provider, str) or not provider.strip()
                or not isinstance(scope, str) or not scope.strip()
                or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000):
            raise ValueError("Solana quarantine query identity or limit is invalid")
        rows = self.conn.execute(
            """SELECT signature, slot, transaction_index, block_hash, payload_json, source_page_id
               FROM layer1_onchain_solana_quarantine
               WHERE network_id=? AND provider=? AND scope=? AND status='PENDING'
               ORDER BY slot, transaction_index, signature LIMIT ?""",
            (network_id, provider, scope, limit),
        ).fetchall()
        return [{"signature": row[0], "slot": row[1], "transaction_index": row[2],
                 "block_hash": row[3], "payload": json.loads(row[4]),
                 "source_page_id": row[5]} for row in rows]

    def reconcile_block(self, network_id: str, block_number: int,
                        canonical_block_hash: str, provider: Optional[str] = None,
                        scope: Optional[str] = None) -> int:
        """Tombstone events whose block hash disagrees with a verified canonical header.

        This method must only be called with a provider-verified canonical hash
        at a height covered by the caller's explicit reconciliation policy.
        """
        if not isinstance(network_id, str) or not network_id.strip():
            raise ValueError("network_id is required")
        if isinstance(block_number, bool) or not isinstance(block_number, int) or block_number < 0:
            raise ValueError("block_number must be a non-negative integer")
        if not isinstance(canonical_block_hash, str) or not canonical_block_hash.strip():
            raise ValueError("canonical_block_hash is required")
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            clauses = ["network_id=?", "block_number=?", "block_hash<>?", "canonical_status='CANONICAL'"]
            params = [network_id, block_number, canonical_block_hash]
            if provider is not None:
                clauses.append("provider=?")
                params.append(provider)
            if scope is not None:
                clauses.append("scope=?")
                params.append(scope)
            rows = self.conn.execute(
                """SELECT network_id, provider, scope, event_id, payload_json
                   FROM layer1_onchain_transfer_events WHERE """ + " AND ".join(clauses),
                params,
            ).fetchall()
            for row in rows:
                payload = json.loads(row[4])
                payload["canonical_status"] = "REORGED"
                self.conn.execute(
                    """UPDATE layer1_onchain_transfer_events
                       SET canonical_status='REORGED', payload_json=?, updated_at=?
                       WHERE network_id=? AND provider=? AND scope=? AND event_id=?""",
                    (self._canonical(payload), now, row[0], row[1], row[2], row[3]),
                )
            self._invalidate_page_acceptances_for_reorg(
                network_id, provider, scope, block_number,
                canonical_block_hash, now,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return len(rows)

    def close(self) -> None:
        self.conn.close()




def normalize_xrpl_payment(
    record,
    *,
    monitored_account: str,
    asset_id: str,
    mapping_id: str,
    issuer_address: str,
    issued_currency: str,
    decimals: int,
    canonical_ledger_hash: str,
    block_time: str,
    observed_at: str,
    scope: str,
) -> Optional[NormalizedTransferEvent]:
    """Normalize one validated XRPL issued-currency Payment.

    Only the metadata's delivered_amount is evidence of the amount received.
    The requested transaction Amount and RippleState balance deltas are never
    substituted for a missing delivered amount. The configured decimal scale
    must represent the delivered value exactly or normalization fails closed.
    """
    from .onchain_providers import XrplAccountTransaction, is_valid_xrpl_classic_address

    if not isinstance(record, XrplAccountTransaction):
        raise ValueError("record must be a validated XRPL account transaction")
    if not isinstance(record.raw, dict) or record.raw.get("validated") is not True:
        raise ValueError("XRPL transaction must have validated-ledger proof")
    if (not isinstance(record.transaction_hash, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", record.transaction_hash) is None
            or isinstance(record.ledger_index, bool) or not isinstance(record.ledger_index, int)
            or record.ledger_index <= 0
            or record.raw.get("hash") != record.transaction_hash
            or isinstance(record.raw.get("ledger_index"), bool)
            or not isinstance(record.raw.get("ledger_index"), int)
            or record.raw.get("ledger_index") != record.ledger_index):
        raise ValueError("XRPL transaction hash and validated ledger index do not match provider record identity")
    provider_ledger_hash = record.raw.get("ledger_hash")
    if (not isinstance(provider_ledger_hash, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", provider_ledger_hash) is None
            or not isinstance(canonical_ledger_hash, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", canonical_ledger_hash) is None
            or provider_ledger_hash.lower() != canonical_ledger_hash.lower()):
        raise ValueError("XRPL transaction ledger hash does not match the independently verified canonical ledger hash")
    if not isinstance(record.transaction, dict) or not isinstance(record.metadata, dict):
        raise ValueError("XRPL transaction and metadata must be objects")
    if (not isinstance(record.raw.get("tx_json"), dict)
            or not isinstance(record.raw.get("meta"), dict)
            or record.raw.get("tx_json") != record.transaction
            or record.raw.get("meta") != record.metadata):
        raise ValueError("XRPL raw transaction and metadata must match the typed provider record")
    if record.transaction.get("TransactionType") != "Payment":
        return None
    if record.metadata.get("TransactionResult") != "tesSUCCESS":
        return None
    if (not is_valid_xrpl_classic_address(monitored_account)
            or not isinstance(asset_id, str) or not asset_id.strip()
            or not isinstance(mapping_id, str) or not mapping_id.strip()
            or not is_valid_xrpl_classic_address(issuer_address)
            or not is_valid_xrpl_issued_currency_code(issued_currency)
            or isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 36):
        raise ValueError("XRPL mapping and monitored account scope are invalid")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", canonical_ledger_hash or ""):
        raise ValueError("canonical XRPL ledger hash must be 32-byte hex")
    source = record.transaction.get("Account")
    destination = record.transaction.get("Destination")
    if (not is_valid_xrpl_classic_address(source)
            or not is_valid_xrpl_classic_address(destination)):
        raise ValueError("XRPL Payment source and destination must be checksum-valid classic addresses")
    if monitored_account not in {source, destination}:
        raise ValueError("monitored account is not the payment source or destination")
    delivered = record.metadata.get("delivered_amount")
    if delivered == "unavailable" or not isinstance(delivered, dict):
        raise ValueError("XRPL Payment lacks an exact delivered_amount object")
    if (delivered.get("currency") != issued_currency
            or delivered.get("issuer") != issuer_address):
        return None
    value = delivered.get("value")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("XRPL delivered_amount value must be a decimal string")
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise ValueError("XRPL delivered_amount value is not a valid decimal") from None
    if not amount.is_finite() or amount <= 0:
        raise ValueError("XRPL delivered_amount must be a positive finite decimal")
    amount_tuple = amount.as_tuple()
    significant = list(amount_tuple.digits)
    exponent = amount_tuple.exponent
    while len(significant) > 1 and significant[-1] == 0:
        significant.pop()
        exponent += 1
    significant_digits = len(significant)
    adjusted_exponent = significant_digits + exponent - 1
    # XRPL normalizes the 16-digit mantissa to [10^15, 10^16-1] and
    # stores its exponent in [-96, 80]. The corresponding decimal adjusted
    # exponent is therefore [-81, 95].
    if significant_digits > 16 or not -81 <= adjusted_exponent <= 95:
        raise ValueError("XRPL delivered_amount is outside the issued-currency precision/range")
    with localcontext() as context:
        context.prec = max(80, significant_digits + decimals + 8)
        scaled = amount * (Decimal(10) ** decimals)
    if scaled != scaled.to_integral_value():
        raise ValueError("XRPL delivered_amount cannot be represented at the configured decimal scale")
    for timestamp in (block_time, observed_at):
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            raise ValueError("XRPL event timestamps must be timezone-aware ISO-8601") from None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("XRPL event timestamps must be timezone-aware ISO-8601")
    transaction_index = record.metadata.get("TransactionIndex")
    if transaction_index is not None and (
        isinstance(transaction_index, bool) or not isinstance(transaction_index, int)
        or transaction_index < 0
    ):
        raise ValueError("XRPL TransactionIndex must be a non-negative integer")
    return NormalizedTransferEvent(
        event_id=record.transaction_hash.lower(), network_id="xrpl-mainnet",
        provider="chainstack", scope=scope, asset_id=asset_id, mapping_id=mapping_id,
        transaction_hash=record.transaction_hash.lower(), block_number=record.ledger_index,
        block_hash=canonical_ledger_hash.lower(), event_index=transaction_index,
        from_address=source, to_address=destination,
        amount_raw=str(int(scaled)), decimals=decimals,
        block_time=datetime.fromisoformat(block_time.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(),
        observed_at=datetime.fromisoformat(observed_at.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(),
        canonical_status="CANONICAL", provenance="xrpl:validated:Payment:delivered_amount",
    )



def normalize_evm_transfer_log(event: EvmTokenTransferLog, *, asset_id: str,
                               mapping_id: str, expected_contract_address: str,
                               canonical_block_hash: str, decimals: int,
                               block_time: str, observed_at: str,
                               scope: str) -> NormalizedTransferEvent:
    """Normalize an EVM Transfer log using its canonical transaction/log identity.

    The provider adapter must already have checked the mapped contract and
    finalized range. A removed log is retained as a REORGED tombstone.
    """
    if not isinstance(event, EvmTokenTransferLog):
        raise ValueError("event must be a validated EVM token transfer log")
    if event.network_id not in {"ethereum-mainnet", "bnb-smart-chain-mainnet"}:
        raise ValueError("EVM transfer log network is not configured for Module 9")
    if not isinstance(expected_contract_address, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", expected_contract_address):
        raise ValueError("expected_contract_address must be an exact EVM contract address")
    if event.contract_address.lower() != expected_contract_address.lower():
        raise ValueError("transfer log contract does not match the verified asset mapping")
    expected_scope = f"contract:{expected_contract_address.lower()}"
    if scope != expected_scope:
        raise ValueError("transfer log scope must identify the exact mapped contract")
    if not isinstance(canonical_block_hash, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", canonical_block_hash):
        raise ValueError("canonical_block_hash must be an exact EVM block hash")
    if not isinstance(decimals, int) or isinstance(decimals, bool) or not 0 <= decimals <= 36:
        raise ValueError("decimals must be an integer from 0 to 36")
    if not _is_uint256_decimal(event.amount_raw):
        raise ValueError("provider transfer amount must be a uint256 base-unit integer string")
    return NormalizedTransferEvent(
        event_id=f"{event.transaction_hash.lower()}:{event.log_index}",
        network_id=event.network_id, provider="alchemy", scope=scope,
        asset_id=asset_id, mapping_id=mapping_id,
        transaction_hash=event.transaction_hash.lower(),
        block_number=event.block_number, block_hash=event.block_hash.lower(),
        event_index=event.log_index, from_address=event.from_address.lower(),
        to_address=event.to_address.lower(), amount_raw=event.amount_raw,
        decimals=decimals, block_time=block_time, observed_at=observed_at,
        canonical_status=("REORGED" if event.removed or event.block_hash.lower() != canonical_block_hash.lower()
                          else "CANONICAL"),
        provenance="eth_getLogs:ERC20.Transfer",
    )



def _solana_account_keys(message: dict, meta: dict) -> list[str]:
    keys = message.get("accountKeys")
    if not isinstance(keys, list) or not keys:
        raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana transaction static account keys are missing")
    static = []
    for item in keys:
        key = item.get("pubkey") if isinstance(item, dict) else item
        if not isinstance(key, str) or not key.strip() or len(_solana_base58_decode(key)) != 32:
            raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana transaction contains an invalid static account key")
        static.append(key)
    lookups = message.get("addressTableLookups", [])
    if not isinstance(lookups, list):
        raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana address table lookup metadata is malformed")
    expected_writable = expected_readonly = 0
    for lookup in lookups:
        if not isinstance(lookup, dict):
            raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana address table lookup entry is malformed")
        if not _is_base58_pubkey(lookup.get("accountKey")):
            raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana address table lookup account key is invalid")
        writable_indexes = lookup.get("writableIndexes")
        readonly_indexes = lookup.get("readonlyIndexes")
        if (not isinstance(writable_indexes, list) or not isinstance(readonly_indexes, list)
                or any(isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= 255
                       for index in writable_indexes + readonly_indexes)):
            raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana address table lookup indexes are malformed")
        expected_writable += len(writable_indexes)
        expected_readonly += len(readonly_indexes)
    loaded = meta.get("loadedAddresses")
    if loaded is None:
        if lookups:
            raise ProviderTransportError("SOLANA_LOADED_ADDRESSES_MISSING", "versioned Solana transaction is missing resolved lookup-table addresses")
        loaded = {"writable": [], "readonly": []}
    if not isinstance(loaded, dict):
        raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana loaded address metadata is malformed")
    writable, readonly = loaded.get("writable", []), loaded.get("readonly", [])
    if (not isinstance(writable, list) or not isinstance(readonly, list)
            or any(not isinstance(key, str) or not key.strip() or len(_solana_base58_decode(key)) != 32
                   for key in writable + readonly)
            or len(writable) != expected_writable or len(readonly) != expected_readonly):
        raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana loaded writable/readonly addresses are malformed or incomplete")
    return static + writable + readonly


def _solana_balance_evidence(meta: dict, account_index: int, mint: str) -> tuple[set[str], set[int], set[str]]:
    owners, decimal_values, mints = set(), set(), set()
    for field in ("preTokenBalances", "postTokenBalances"):
        balances = meta.get(field, [])
        if balances is None:
            continue
        if not isinstance(balances, list):
            raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", f"Solana {field} metadata is malformed")
        for balance in balances:
            if not isinstance(balance, dict):
                raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", f"Solana {field} entry is malformed")
            record_index = balance.get("accountIndex")
            if isinstance(record_index, bool) or not isinstance(record_index, int):
                raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana token balance accountIndex is invalid")
            if record_index != account_index:
                continue
            record_mint = balance.get("mint")
            if not isinstance(record_mint, str) or not record_mint:
                raise ProviderTransportError("SOLANA_TOKEN_MINT_EVIDENCE_MISSING", "Solana token balance lacks its mint")
            mints.add(record_mint)
            if record_mint != mint:
                continue
            owner = balance.get("owner")
            if owner is not None:
                if not isinstance(owner, str) or not owner or len(_solana_base58_decode(owner)) != 32:
                    raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana token balance owner address is invalid")
                owners.add(owner)
            ui = balance.get("uiTokenAmount")
            if not isinstance(ui, dict):
                raise ProviderTransportError("SOLANA_TOKEN_DECIMALS_MISSING", "Solana token balance lacks uiTokenAmount decimals")
            decimals = ui.get("decimals")
            if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 36:
                raise ProviderTransportError("SOLANA_TOKEN_DECIMALS_MISSING", "Solana token balance decimals are invalid")
            decimal_values.add(decimals)
    if len(mints) > 1:
        raise ProviderTransportError("SOLANA_TOKEN_MINT_CONFLICT", "one token account index has conflicting mint evidence")
    if len(owners) > 1:
        raise ProviderTransportError("SOLANA_TOKEN_OWNER_CONFLICT", "one token account index has conflicting owner evidence")
    if len(decimal_values) > 1:
        raise ProviderTransportError("SOLANA_TOKEN_DECIMALS_CONFLICT", "one token account has conflicting decimal evidence")
    return owners, decimal_values, mints


def normalize_solana_token_transfer_instructions(
    history: SolanaAddressTransaction, *, asset_id: str, mapping_id: str,
    mint: str, token_standard: str, decimals: int, monitored_address: str,
    canonical_block_hash: str, canonical_block_time: str, observed_at: str,
) -> tuple[NormalizedTransferEvent, ...]:
    """Extract only standard SPL Transfer / TransferChecked instructions.

    Static and lookup-table account indexes are resolved in Solana's canonical
    order. Inner CPI identities use their actual outer/inner trace coordinates.
    Balance metadata proves mint and monitored-owner scope; it never supplies
    synthetic transfer amounts.
    """
    if not isinstance(history, SolanaAddressTransaction):
        raise ValueError("Solana address history record is required")
    if any(not isinstance(value, str) or not value.strip() for value in (
        asset_id, mapping_id, mint, monitored_address, canonical_block_hash,
        canonical_block_time, observed_at,
    )):
        raise ValueError("Solana mapping, scope, canonical block and timestamp evidence are required")
    if token_standard != "SPL_TOKEN":
        raise ValueError("only the base SPL Token Program is supported; Token-2022 requires extension-aware decoding")
    if any(len(_solana_base58_decode(value)) != 32 for value in (mint, monitored_address, canonical_block_hash)):
        raise ValueError("Solana mint, monitored address and canonical blockhash must decode to 32 bytes")
    if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 36:
        raise ValueError("Solana token mapping decimals are invalid")
    program_id = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    try:
        canonical_time = datetime.fromisoformat(canonical_block_time.replace("Z", "+00:00"))
        observed_time = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Solana timestamps must be valid timezone-aware ISO-8601") from None
    if (canonical_time.tzinfo is None or canonical_time.utcoffset() is None
            or observed_time.tzinfo is None or observed_time.utcoffset() is None):
        raise ValueError("Solana timestamps must be timezone-aware")
    if (isinstance(history.slot, bool) or not isinstance(history.slot, int) or history.slot <= 0
            or not isinstance(history.signature, str)
            or not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{64,90}", history.signature)
            or len(_solana_base58_decode(history.signature)) != 64):
        raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana transaction signature or slot is invalid")
    raw = history.raw
    raw_slot = raw.get("slot") if isinstance(raw, dict) else None
    if (not isinstance(raw, dict) or isinstance(raw_slot, bool)
            or not isinstance(raw_slot, int) or raw_slot != history.slot):
        raise ProviderTransportError("SOLANA_SLOT_MISMATCH", "Solana full transaction does not match address-history slot")
    if raw.get("signature") not in (None, history.signature):
        raise ProviderTransportError("SOLANA_SIGNATURE_MISMATCH", "Solana full transaction signature does not match address history")
    raw_block_time = raw.get("blockTime")
    if "blockTime" in raw and (
            (raw_block_time is not None and (
                isinstance(raw_block_time, bool) or not isinstance(raw_block_time, int)
                or raw_block_time <= 0))
            or raw_block_time != history.block_time):
        raise ProviderTransportError(
            "SOLANA_BLOCK_TIME_MISMATCH",
            "Solana full transaction block time does not match the typed address-history record",
        )
    if history.block_time is not None:
        if isinstance(history.block_time, bool) or not isinstance(history.block_time, int) or history.block_time <= 0:
            raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana address-history block time is invalid")
        if int(canonical_time.timestamp()) != history.block_time:
            raise ProviderTransportError("SOLANA_BLOCK_TIME_MISMATCH", "Solana address-history block time differs from canonical block time")
    transaction, meta = raw.get("transaction"), raw.get("meta")
    if not isinstance(transaction, dict) or not isinstance(meta, dict):
        raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana full transaction and metadata are required")
    if "err" not in meta:
        raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana transaction metadata is missing explicit execution status")
    execution_error = meta["err"]
    if execution_error is not None:
        # TransactionError is serialized as a non-empty unit-variant string or
        # a single-key externally tagged object. Arbitrary JSON values must not
        # be mistaken for a valid failed-transaction status and silently skipped.
        if (isinstance(execution_error, str) and not execution_error.strip()) or (
            isinstance(execution_error, dict)
            and (len(execution_error) != 1
                 or any(not isinstance(key, str) or not key.strip() for key in execution_error))
        ) or not isinstance(execution_error, (str, dict)):
            raise ProviderTransportError(
                "INVALID_SOLANA_TRANSACTION", "Solana transaction execution status has an invalid error shape",
            )
        # Failed transactions are expected address-history entries, not malformed
        # provider pages. Skip them so one failed signature cannot stall the page
        # and prevent unrelated successful transactions from being checkpointed.
        return ()
    signatures = transaction.get("signatures")
    if not isinstance(signatures, list) or not signatures or signatures[0] != history.signature:
        raise ProviderTransportError("SOLANA_SIGNATURE_MISMATCH", "transaction message must carry the exact address-history signature")
    message = transaction.get("message")
    if not isinstance(message, dict):
        raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana compiled message is missing")
    keys = _solana_account_keys(message, meta)
    outer, inner_groups = message.get("instructions"), meta.get("innerInstructions", [])
    if not isinstance(outer, list) or not isinstance(inner_groups, list):
        raise ProviderTransportError("INVALID_SOLANA_TRANSACTION", "Solana outer/inner instruction arrays are malformed")
    groups = {}
    for group in inner_groups:
        if not isinstance(group, dict) or isinstance(group.get("index"), bool) or not isinstance(group.get("index"), int):
            raise ProviderTransportError("INVALID_SOLANA_INSTRUCTION", "Solana inner instruction trace group is malformed")
        parent = group["index"]
        if not 0 <= parent < len(outer) or parent in groups or not isinstance(group.get("instructions"), list):
            raise ProviderTransportError("INVALID_SOLANA_INSTRUCTION", "Solana inner instruction parent index is invalid or duplicated")
        groups[parent] = group["instructions"]

    events = []
    for outer_index, outer_instruction in enumerate(outer):
        traces = [("outer", outer_index, None, outer_instruction)]
        traces.extend(("inner", outer_index, inner_index, instruction)
                      for inner_index, instruction in enumerate(groups.get(outer_index, [])))
        for kind, parent_index, inner_index, instruction in traces:
            if not isinstance(instruction, dict):
                raise ProviderTransportError("INVALID_SOLANA_INSTRUCTION", "Solana compiled instruction is malformed")
            program_index, accounts, data = (
                instruction.get("programIdIndex"), instruction.get("accounts"), instruction.get("data")
            )
            if (isinstance(program_index, bool) or not isinstance(program_index, int)
                    or not 0 <= program_index < len(keys)
                    or not isinstance(accounts, list)
                    or any(isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(keys)
                           for index in accounts)
                    or not isinstance(data, str)):
                raise ProviderTransportError("INVALID_SOLANA_INSTRUCTION", "Solana instruction account/program indexes or data are malformed")
            if keys[program_index] != program_id:
                continue
            decoded = _solana_base58_decode(data)
            if not decoded:
                raise ProviderTransportError("INVALID_SOLANA_INSTRUCTION", "SPL Token instruction data is empty")
            opcode = decoded[0]
            if opcode not in (3, 12):
                continue
            expected_len, required_accounts = (9, 3) if opcode == 3 else (10, 4)
            if len(decoded) != expected_len or len(accounts) < required_accounts:
                raise ProviderTransportError("INVALID_SOLANA_TRANSFER", "SPL Token Transfer instruction data/accounts are malformed")
            amount = int.from_bytes(decoded[1:9], "little")
            if opcode == 12 and decoded[9] != decimals:
                raise ProviderTransportError("SOLANA_TOKEN_DECIMALS_MISMATCH", "TransferChecked decimals differ from verified asset mapping")
            source_index = accounts[0]
            if opcode == 12:
                mint_index, destination_index = accounts[1], accounts[2]
                if keys[mint_index] != mint:
                    continue
            else:
                destination_index = accounts[1]
            source_account, destination_account = keys[source_index], keys[destination_index]
            if source_account == destination_account:
                raise ProviderTransportError("INVALID_SOLANA_TRANSFER", "SPL Token transfer source and destination accounts are identical")
            source_owners, source_decimals, source_mints = _solana_balance_evidence(meta, source_index, mint)
            destination_owners, destination_decimals, destination_mints = _solana_balance_evidence(meta, destination_index, mint)
            if not source_mints or not destination_mints:
                raise ProviderTransportError("SOLANA_TOKEN_MINT_EVIDENCE_MISSING", "both token accounts require balance metadata proving their mint")
            if source_mints != destination_mints:
                raise ProviderTransportError("SOLANA_TOKEN_MINT_CONFLICT", "source and destination token-account mints disagree")
            if opcode == 12 and source_mints != {mint}:
                raise ProviderTransportError("SOLANA_TOKEN_MINT_MISMATCH", "TransferChecked balance metadata disagrees with its encoded mapped mint")
            if opcode == 3 and source_mints != {mint}:
                continue
            if (source_decimals and source_decimals != {decimals}) or (destination_decimals and destination_decimals != {decimals}):
                raise ProviderTransportError("SOLANA_TOKEN_DECIMALS_MISMATCH", "token account balance decimals differ from verified asset mapping")
            if monitored_address not in {source_account, destination_account} | source_owners | destination_owners:
                continue
            path = f"outer:{parent_index}" if kind == "outer" else f"inner:{parent_index}:{inner_index}"
            provenance = (
                f"alchemy:solana:{token_standard}:instruction={path};mint={mint};"
                f"source_owner={','.join(sorted(source_owners))};"
                f"destination_owner={','.join(sorted(destination_owners))};program={program_id}"
            )
            events.append(NormalizedTransferEvent(
                event_id=f"{history.signature}:{path}", network_id="solana-mainnet",
                provider="alchemy", scope=f"address:{monitored_address}:mapping:{mapping_id}",
                asset_id=asset_id, mapping_id=mapping_id,
                transaction_hash=history.signature, block_number=history.slot,
                block_hash=canonical_block_hash, event_index=None,
                from_address=source_account, to_address=destination_account,
                amount_raw=str(amount), decimals=decimals,
                block_time=canonical_time.astimezone(timezone.utc).isoformat(),
                observed_at=observed_time.astimezone(timezone.utc).isoformat(),
                canonical_status="CANONICAL", provenance=provenance,
            ))
    return tuple(events)


def normalize_bitcoin_transaction_outputs(
    history: BitcoinAddressTransaction,
    transaction: dict,
    *,
    asset_id: str,
    mapping_id: str,
    monitored_address: str,
    canonical_block_hash: str,
    block_time: str,
    observed_at: str,
    minimum_confirmations: int,
) -> tuple[NormalizedTransferEvent, ...]:
    """Normalize address-bearing Bitcoin outputs with stable txid:vout identity.

    Bitcoin transactions can consume many inputs and create many outputs. The
    source side is therefore represented as a set of input addresses, not an
    invented one-to-one sender. Outputs without exactly one decoded address
    are skipped rather than assigned a fabricated destination.
    """
    if not isinstance(history, BitcoinAddressTransaction):
        raise ValueError("history must be a validated Bitcoin address transaction")
    if not isinstance(transaction, dict):
        raise ValueError("Bitcoin transaction details must be an object")
    if not isinstance(asset_id, str) or not asset_id.strip() or not isinstance(mapping_id, str) or not mapping_id.strip():
        raise ValueError("Bitcoin asset and mapping identity are required")
    if not _is_valid_bitcoin_mainnet_address(monitored_address):
        raise ValueError("monitored_address must be a checksum-valid Bitcoin mainnet address")
    if (isinstance(minimum_confirmations, bool) or not isinstance(minimum_confirmations, int)
            or minimum_confirmations < 1):
        raise ValueError("minimum_confirmations must be a positive integer")
    if (isinstance(history.confirmations, bool) or not isinstance(history.confirmations, int)
            or history.finality != "CONFIRMED" or history.confirmations < minimum_confirmations):
        raise ValueError("Bitcoin transaction has not reached the configured confirmation threshold")
    if (not isinstance(history.raw, dict)
            or not isinstance(history.raw.get("txid"), str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", history.raw["txid"]) is None
            or not isinstance(history.txid, str)
            or history.raw["txid"].lower() != history.txid.lower()):
        raise ValueError("Bitcoin raw address-history transaction ID does not match its typed record")
    for raw_field, typed_value in (
        ("confirmations", history.confirmations),
        ("blockHeight", history.block_height),
        ("blockTime", history.block_time),
    ):
        if raw_field in history.raw:
            raw_value = history.raw[raw_field]
            if (isinstance(raw_value, bool) or not isinstance(raw_value, int)
                    or raw_value != typed_value):
                raise ValueError(f"Bitcoin raw address-history {raw_field} does not match its typed record")
    if "blockHash" in history.raw:
        raw_hash = history.raw["blockHash"]
        if (not isinstance(raw_hash, str) or not isinstance(history.block_hash, str)
                or raw_hash.lower() != history.block_hash.lower()):
            raise ValueError("Bitcoin raw address-history blockHash does not match its typed record")
    if (not isinstance(history.txid, str) or re.fullmatch(r"[0-9a-fA-F]{64}", history.txid) is None
            or isinstance(history.block_height, bool) or not isinstance(history.block_height, int)
            or history.block_height <= 0
            or not isinstance(history.block_hash, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", history.block_hash) is None
            or isinstance(history.block_time, bool) or not isinstance(history.block_time, int)
            or history.block_time <= 0):
        raise ValueError("confirmed Bitcoin history lacks a valid transaction/block identity")
    transaction_height = transaction.get("blockHeight")
    transaction_block_time = transaction.get("blockTime")
    if (not isinstance(transaction.get("txid"), str)
            or transaction["txid"].lower() != history.txid.lower()
            or isinstance(transaction_height, bool) or not isinstance(transaction_height, int)
            or transaction_height <= 0 or transaction_height != history.block_height
            or not isinstance(transaction.get("blockHash"), str)
            or transaction["blockHash"].lower() != history.block_hash.lower()
            or isinstance(transaction_block_time, bool)
            or not isinstance(transaction_block_time, int) or transaction_block_time <= 0
            or transaction_block_time != history.block_time):
        raise ValueError("Bitcoin transaction identity or block reference does not match address history")
    if (not isinstance(canonical_block_hash, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", canonical_block_hash) is None):
        raise ValueError("canonical Bitcoin block hash must be 32-byte hex")
    for field in (block_time, observed_at):
        try:
            parsed = datetime.fromisoformat(field.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Bitcoin event timestamps must be timezone-aware ISO-8601") from None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Bitcoin event timestamps must be timezone-aware ISO-8601")

    inputs = transaction.get("vin")
    outputs = transaction.get("vout")
    if (not isinstance(inputs, list) or not inputs or any(not isinstance(item, dict) for item in inputs)
            or not isinstance(outputs, list) or any(not isinstance(item, dict) for item in outputs)):
        raise ValueError("Bitcoin transaction requires non-empty vin and vout arrays")

    coinbase = bool(inputs) and all("coinbase" in item for item in inputs)
    input_addresses = set()
    input_addresses_complete = True
    for item in inputs:
        if "coinbase" in item:
            if not coinbase:
                raise ValueError("Bitcoin transaction mixes coinbase and ordinary inputs")
            continue
        addresses = item.get("addresses", [])
        is_address = item.get("isAddress", bool(addresses))
        if not isinstance(is_address, bool) or not isinstance(addresses, list):
            raise ValueError("Bitcoin input address metadata is malformed")
        if not is_address or not addresses:
            if addresses:
                raise ValueError("Bitcoin input address list conflicts with isAddress=false")
            if is_address:
                raise ValueError("Bitcoin input isAddress=true but no decoded address was supplied")
            input_addresses_complete = False
            continue
        if any(not _is_valid_bitcoin_mainnet_address(address) for address in addresses):
            raise ValueError("Bitcoin input contains a non-checksum-valid Bitcoin mainnet address")
        input_addresses.update(addresses)

    output_indexes = set()
    events = []
    total_output_value = 0
    for output in outputs:
        index = output.get("n")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= 0xFFFFFFFF:
            raise ValueError("Bitcoin output index must be a uint32 integer")
        if index in output_indexes:
            raise ValueError("Bitcoin transaction contains a duplicate output index")
        output_indexes.add(index)
        value = output.get("value")
        if not isinstance(value, str) or re.fullmatch(r"[0-9]+", value) is None:
            raise ValueError("Bitcoin output value must be an integer satoshi string")
        canonical_value = value.lstrip("0") or "0"
        if (len(canonical_value) > len(BITCOIN_MAX_MONEY_SATOSHIS_TEXT)
                or (len(canonical_value) == len(BITCOIN_MAX_MONEY_SATOSHIS_TEXT)
                    and canonical_value > BITCOIN_MAX_MONEY_SATOSHIS_TEXT)):
            raise ValueError("Bitcoin output value exceeds maximum money")
        total_output_value += int(canonical_value)
        if total_output_value > BITCOIN_MAX_MONEY_SATOSHIS:
            raise ValueError("Bitcoin transaction output total exceeds maximum money")
        addresses = output.get("addresses", [])
        is_address = output.get("isAddress", bool(addresses))
        if not isinstance(is_address, bool) or not isinstance(addresses, list):
            raise ValueError("Bitcoin output address metadata is malformed")
        if not is_address:
            if addresses:
                raise ValueError("Bitcoin output address list conflicts with isAddress=false")
            continue
        if not addresses:
            raise ValueError("Bitcoin output isAddress=true but no decoded address was supplied")
        if any(not _is_valid_bitcoin_mainnet_address(address) for address in addresses):
            raise ValueError("Bitcoin output contains a non-checksum-valid Bitcoin mainnet address")
        if len(addresses) != 1:
            continue
        destination = addresses[0]
        source_addresses = tuple(sorted(input_addresses))
        source_address = source_addresses[0] if input_addresses_complete and len(source_addresses) == 1 else None
        events.append(NormalizedTransferEvent(
            event_id=f"{history.txid.lower()}:{index}",
            network_id="bitcoin-mainnet", provider="alchemy",
            scope=f"address:{monitored_address}",
            asset_id=asset_id, mapping_id=mapping_id,
            transaction_hash=history.txid.lower(),
            block_number=history.block_height,
            block_hash=history.block_hash.lower(),
            event_index=index, from_address=source_address,
            to_address=destination, amount_raw=value, decimals=8,
            block_time=block_time, observed_at=observed_at,
            canonical_status=("CANONICAL" if history.block_hash.lower() == canonical_block_hash.lower()
                              else "REORGED"),
            provenance="alchemy_utxo:transaction:vout",
            from_addresses=source_addresses,
            from_addresses_complete=input_addresses_complete,
        ))
    involved_addresses = input_addresses | {
        address for output in outputs
        for address in output.get("addresses", [])
        if isinstance(address, str)
    }
    if monitored_address not in involved_addresses:
        raise ValueError("Bitcoin transaction does not contain the monitored address")
    return tuple(events)
