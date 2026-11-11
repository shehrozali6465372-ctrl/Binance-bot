"""Durable, idempotent storage for normalized on-chain transfer pages.

The store deliberately owns persistence/checkpoint atomicity, not provider
pagination semantics. Callers must supply a stable provider event identity and
must only advance a cursor after a complete, validated page has been normalized.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from .onchain_providers import EvmTokenTransferLog


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
        CREATE TABLE IF NOT EXISTS layer1_onchain_ingestion_blocks (
            network_id TEXT NOT NULL, provider TEXT NOT NULL, scope TEXT NOT NULL,
            block_number INTEGER NOT NULL, block_hash TEXT NOT NULL, block_time TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(network_id, provider, scope, block_number)
        );
        """)

    @staticmethod
    def _canonical(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def _validate_event(cls, event: NormalizedTransferEvent) -> None:
        if not isinstance(event, NormalizedTransferEvent):
            raise ValueError("page contains an invalid normalized transfer event")
        text_fields = (
            event.event_id, event.network_id, event.provider, event.scope,
            event.asset_id, event.mapping_id, event.transaction_hash,
            event.block_hash, event.from_address, event.to_address,
            event.amount_raw, event.block_time, event.observed_at, event.provenance,
        )
        if any(not isinstance(value, str) or not value.strip() for value in text_fields):
            raise ValueError("normalized transfer event identity and provenance fields are required")
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
                    canonical_blocks: Iterable[dict] = ()) -> dict:
        if not isinstance(cursor_key, str) or not cursor_key.strip():
            raise ValueError("cursor_key must be a non-empty string")
        if not isinstance(allow_recanonicalized, bool):
            raise ValueError("allow_recanonicalized must be boolean")
        cursor_json = self._canonical(next_cursor)
        batch = tuple(events)
        blocks = tuple(canonical_blocks)
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
        now = datetime.now(timezone.utc).isoformat()
        inserted = duplicates = tombstoned = 0
        self.conn.execute("BEGIN IMMEDIATE")
        try:
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
                        incoming_payload = asdict(event)
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
            for block in blocks:
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

    def get_block_hash(self, network_id: str, provider: str, scope: str,
                       block_number: int) -> Optional[str]:
        row = self.conn.execute(
            """SELECT block_hash FROM layer1_onchain_ingestion_blocks
               WHERE network_id=? AND provider=? AND scope=? AND block_number=?""",
            (network_id, provider, scope, block_number),
        ).fetchone()
        return row[0] if row else None

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
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return len(rows)

    def close(self) -> None:
        self.conn.close()



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
    if not re.fullmatch(r"[0-9]+", event.amount_raw):
        raise ValueError("provider transfer amount must be an integer base-unit string")
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
