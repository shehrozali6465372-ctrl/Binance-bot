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

from .onchain_providers import BitcoinAddressTransaction, EvmTokenTransferLog


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

    def __post_init__(self):
        if isinstance(self.from_addresses, list):
            object.__setattr__(self, "from_addresses", tuple(self.from_addresses))


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
    if not isinstance(monitored_address, str) or not monitored_address.strip() or any(ch.isspace() for ch in monitored_address):
        raise ValueError("monitored_address must be a non-empty Bitcoin address")
    if (isinstance(minimum_confirmations, bool) or not isinstance(minimum_confirmations, int)
            or minimum_confirmations < 1):
        raise ValueError("minimum_confirmations must be a positive integer")
    if (isinstance(history.confirmations, bool) or not isinstance(history.confirmations, int)
            or history.finality != "CONFIRMED" or history.confirmations < minimum_confirmations):
        raise ValueError("Bitcoin transaction has not reached the configured confirmation threshold")
    if (not isinstance(history.txid, str) or re.fullmatch(r"[0-9a-fA-F]{64}", history.txid) is None
            or isinstance(history.block_height, bool) or not isinstance(history.block_height, int)
            or history.block_height <= 0
            or not isinstance(history.block_hash, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", history.block_hash) is None
            or isinstance(history.block_time, bool) or not isinstance(history.block_time, int)
            or history.block_time <= 0):
        raise ValueError("confirmed Bitcoin history lacks a valid transaction/block identity")
    if (not isinstance(transaction.get("txid"), str)
            or transaction["txid"].lower() != history.txid.lower()
            or transaction.get("blockHeight") != history.block_height
            or not isinstance(transaction.get("blockHash"), str)
            or transaction["blockHash"].lower() != history.block_hash.lower()
            or transaction.get("blockTime") != history.block_time):
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
        if any(not isinstance(address, str) or not address.strip() or any(ch.isspace() for ch in address)
               for address in addresses):
            raise ValueError("Bitcoin input contains an invalid decoded address")
        input_addresses.update(addresses)

    output_indexes = set()
    events = []
    for output in outputs:
        index = output.get("n")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("Bitcoin output index must be a non-negative integer")
        if index in output_indexes:
            raise ValueError("Bitcoin transaction contains a duplicate output index")
        output_indexes.add(index)
        value = output.get("value")
        if not isinstance(value, str) or re.fullmatch(r"[0-9]+", value) is None:
            raise ValueError("Bitcoin output value must be an integer satoshi string")
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
        if len(addresses) != 1:
            continue
        destination = addresses[0]
        if not isinstance(destination, str) or not destination.strip() or any(ch.isspace() for ch in destination):
            raise ValueError("Bitcoin output destination address is invalid")
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
