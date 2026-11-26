"""PostgreSQL persistence for Module 9.

The SQLite stores remain the default for local development and existing tests.
PostgreSQL is opt-in: callers must provide an explicit DSN and apply migrations
separately. No environment-variable fallback or automatic production migration
is performed here.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Optional

from .onchain_ingestion import NormalizedTransferEvent, OnChainIngestionStore
from .onchain_providers import (
    CapturedProviderReceiptBatch, ProviderResponseReceipt,
    _approved_endpoint_profile_sha256, _approved_endpoint_id,
)

_UNSET = object()
_MIGRATION_LOCK_ID = 7261938475621


class StaleCheckpointError(RuntimeError):
    """A worker attempted to commit from a checkpoint that another worker advanced."""


class CanonicalBlockConflict(RuntimeError):
    """A canonical block hash changed without an authorized, reconciled reorg."""


class CheckpointIdentityConflict(RuntimeError):
    """A cursor key or scope was reused for a different ingestion identity."""


def _driver():
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise RuntimeError(
            'PostgreSQL support requires the optional dependency: pip install "psycopg[binary]>=3.2,<4"'
        ) from exc
    return psycopg, Jsonb


def verify_postgres_migrations(dsn: str, migrations_dir: Optional[str] = None) -> tuple[str, ...]:
    """Verify the checked-in migration set using read-only database access.

    Runtime/application roles need only SELECT on the migration ledger. Schema
    creation and DDL remain an explicit, separately executed migrator task.
    """
    if not isinstance(dsn, str) or not dsn.strip():
        raise ValueError("an explicit PostgreSQL DSN is required")
    psycopg, _ = _driver()
    directory = Path(migrations_dir) if migrations_dir else (
        Path(__file__).resolve().parent / "migrations" / "postgresql"
    )
    files = sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        raise RuntimeError(f"no PostgreSQL migrations found in {directory}")
    verified: list[str] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        for path in files:
            version = path.name
            source = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(source.encode("utf-8")).hexdigest()
            prior = conn.execute(
                "SELECT checksum FROM layer1_schema_migrations WHERE version=%s",
                (version,),
            ).fetchone()
            if prior is None:
                raise RuntimeError(f"missing applied PostgreSQL migration: {version}")
            if prior[0] != checksum:
                raise RuntimeError(f"applied migration checksum changed: {version}")
            verified.append(version)
    return tuple(verified)


def _split_sql_statements(source: str) -> tuple[str, ...]:
    """Split ordinary PostgreSQL SQL without treating comments/quoted semicolons as delimiters.

    Dollar-quoted procedural blocks are intentionally unsupported by this
    migration runner; reject them rather than accidentally splitting their body.
    """
    import re

    if not isinstance(source, str):
        raise TypeError("migration source must be text")
    statements: list[str] = []
    buffer: list[str] = []
    index = 0
    state = "normal"
    block_depth = 0
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""

        if state == "line_comment":
            if char == "\n":
                buffer.append("\n")
                state = "normal"
            index += 1
            continue

        if state == "block_comment":
            if char == "/" and next_char == "*":
                block_depth += 1
                index += 2
                continue
            if char == "*" and next_char == "/":
                block_depth -= 1
                index += 2
                if block_depth == 0:
                    state = "normal"
                continue
            index += 1
            continue

        if state == "single_quote":
            buffer.append(char)
            if char == "'" and next_char == "'":
                buffer.append(next_char)
                index += 2
                continue
            if char == "'":
                state = "normal"
            index += 1
            continue

        if state == "double_quote":
            buffer.append(char)
            if char == '"' and next_char == '"':
                buffer.append(next_char)
                index += 2
                continue
            if char == '"':
                state = "normal"
            index += 1
            continue

        if char == "-" and next_char == "-":
            buffer.append(" ")
            state = "line_comment"
            index += 2
            continue
        if char == "/" and next_char == "*":
            buffer.append(" ")
            state = "block_comment"
            block_depth = 1
            index += 2
            continue
        if char == "'":
            buffer.append(char)
            state = "single_quote"
            index += 1
            continue
        if char == '"':
            buffer.append(char)
            state = "double_quote"
            index += 1
            continue
        if char == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", source[index:])
            if match:
                raise ValueError("dollar-quoted SQL blocks are not supported in migrations")
        if char == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer.clear()
            index += 1
            continue

        buffer.append(char)
        index += 1

    if state in {"single_quote", "double_quote", "block_comment"}:
        raise ValueError("migration SQL contains an unterminated quote or block comment")
    statement = "".join(buffer).strip()
    if statement:
        statements.append(statement)
    return tuple(statements)


def apply_postgres_migrations(dsn: str, migrations_dir: Optional[str] = None) -> tuple[str, ...]:
    """Apply checked-in SQL migrations atomically under a database advisory lock."""
    if not isinstance(dsn, str) or not dsn.strip():
        raise ValueError("an explicit PostgreSQL DSN is required")
    psycopg, _ = _driver()
    directory = Path(migrations_dir) if migrations_dir else (
        Path(__file__).resolve().parent / "migrations" / "postgresql"
    )
    files = sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        raise RuntimeError(f"no PostgreSQL migrations found in {directory}")
    applied: list[str] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK_ID,))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS layer1_schema_migrations (
                    version TEXT PRIMARY KEY,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            for path in files:
                version = path.name
                source = path.read_text(encoding="utf-8")
                checksum = hashlib.sha256(source.encode("utf-8")).hexdigest()
                prior = conn.execute(
                    "SELECT checksum FROM layer1_schema_migrations WHERE version=%s",
                    (version,),
                ).fetchone()
                if prior:
                    if prior[0] != checksum:
                        raise RuntimeError(f"applied migration checksum changed: {version}")
                    continue
                # Split only on SQL delimiters outside comments and quoted values.
                # Dollar-quoted procedural blocks are rejected by the splitter.
                for statement in _split_sql_statements(source):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO layer1_schema_migrations(version, checksum) VALUES (%s, %s)",
                    (version, checksum),
                )
                applied.append(version)
    return tuple(applied)


class PostgresOnChainIngestionStore:
    """Psycopg-backed implementation of the SQLite ingestion-store contract.

    Every commit requires the caller's checkpoint snapshot and the stable
    (network, provider, scope) identity. A transaction-scoped advisory lock
    serializes writers for a scope; a locked checkpoint row and compare-and-swap
    prevent a stale worker from committing a second overlapping page.
    """

    _STATUSES = OnChainIngestionStore._STATUSES

    def __init__(self, dsn: str):
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("an explicit PostgreSQL DSN is required")
        psycopg, _ = _driver()
        self.conn = psycopg.connect(dsn, autocommit=True)
        self.conn.execute("SET TIME ZONE 'UTC'")

    @staticmethod
    def _identity(value) -> tuple[str, str, str]:
        if (not isinstance(value, (tuple, list)) or len(value) != 3
                or any(not isinstance(part, str) or not part.strip() for part in value)):
            raise ValueError("scope_identity must be (network_id, provider, scope)")
        return tuple(value)

    @staticmethod
    def _event(payload: dict) -> NormalizedTransferEvent:
        payload = dict(payload)
        payload["from_addresses"] = tuple(payload.get("from_addresses") or ())
        return NormalizedTransferEvent(**payload)

    def commit_page(
        self, cursor_key: str, next_cursor: Any,
        events: Iterable[NormalizedTransferEvent], *,
        allow_recanonicalized: bool = False,
        canonical_blocks: Iterable[dict] = (),
        canonical_slots: Iterable[dict] = (),
        expected_cursor: Any = _UNSET,
        scope_identity: Any = None,
        provider_receipts: Optional[CapturedProviderReceiptBatch] = None,
        provider_observations: Iterable[dict] = (),
    ) -> dict:
        if not isinstance(cursor_key, str) or not cursor_key.strip():
            raise ValueError("cursor_key must be a non-empty string")
        if expected_cursor is _UNSET:
            raise ValueError("PostgreSQL commits require the checkpoint snapshot in expected_cursor")
        if not isinstance(allow_recanonicalized, bool):
            raise ValueError("allow_recanonicalized must be boolean")
        network_id, provider, scope = self._identity(scope_identity)
        batch, blocks, slots = tuple(events), tuple(canonical_blocks), tuple(canonical_slots)
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
        if any((item.network_id, item.provider) != (network_id, provider) for item in receipts):
            raise ValueError("provider receipt identity does not match checkpoint scope_identity")
        if receipts and any(
            _approved_endpoint_profile_sha256(item.provider, item.network_id) is None
            or item.endpoint_profile_sha256 != _approved_endpoint_profile_sha256(item.provider, item.network_id)
            for item in receipts
        ):
            raise ValueError("provider receipt fingerprint does not match the approved provider/network endpoint profile")
        for event in batch:
            OnChainIngestionStore._validate_event(event)
            if (event.network_id, event.provider, event.scope) != (network_id, provider, scope):
                raise ValueError("event identity does not match checkpoint scope_identity")
        for block in blocks:
            if (not isinstance(block, dict)
                    or (block.get("network_id"), block.get("provider"), block.get("scope")) != (network_id, provider, scope)
                    or isinstance(block.get("block_number"), bool)
                    or not isinstance(block.get("block_number"), int) or block["block_number"] < 0
                    or not isinstance(block.get("block_hash"), str) or not block["block_hash"].strip()
                    or not isinstance(block.get("block_time"), str) or not block["block_time"].strip()):
                raise ValueError("canonical block record is malformed or outside checkpoint scope")
        for slot in slots:
            if (not isinstance(slot, dict) or network_id != "solana-mainnet"
                    or slot.get("network_id") != network_id
                    or slot.get("provider") != provider or slot.get("scope") != scope
                    or isinstance(slot.get("slot"), bool) or not isinstance(slot.get("slot"), int)
                    or slot["slot"] < 0 or not isinstance(slot.get("produced"), bool)):
                raise ValueError("canonical Solana slot record is malformed or outside checkpoint scope")
            if slot["produced"]:
                if not isinstance(slot.get("block_hash"), str) or not slot["block_hash"].strip() or not isinstance(slot.get("block_time"), str) or not slot["block_time"].strip():
                    raise ValueError("produced Solana slots require block hash and time")
            elif slot.get("block_hash") is not None or slot.get("block_time") is not None:
                raise ValueError("skipped Solana slots must have null block hash and time")

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
                    or item["observation_id"] in observation_ids
                    or (item["network_id"], item["provider"], item["scope"]) != (network_id, provider, scope)):
                raise ValueError("provider observation record is malformed, duplicated or outside checkpoint scope")
            observation_ids.add(item["observation_id"])
            expected_endpoint_id = _approved_endpoint_id(item["provider"], item["network_id"])
            if expected_endpoint_id is None or item["endpoint_id"] != expected_endpoint_id:
                raise ValueError("provider observation endpoint_id does not match the approved provider/network endpoint")
            if network_id == "solana-mainnet":
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

        from psycopg.types.json import Jsonb
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        inserted = duplicates = tombstoned = 0
        identity_text = "\x1f".join((network_id, provider, scope))
        with self.conn.transaction():
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (identity_text,),
            )
            row = self.conn.execute(
                """SELECT cursor_key, cursor_json, revision
                   FROM layer1_onchain_ingestion_checkpoints
                   WHERE network_id=%s AND provider=%s AND scope=%s
                   FOR UPDATE""",
                (network_id, provider, scope),
            ).fetchone()
            if row is None:
                self.conn.execute(
                    """INSERT INTO layer1_onchain_ingestion_checkpoints
                       (cursor_key, network_id, provider, scope, cursor_json, revision)
                       VALUES (%s, %s, %s, %s, NULL, 0)""",
                    (cursor_key, network_id, provider, scope),
                )
                stored_cursor, revision = None, 0
            else:
                if row[0] != cursor_key:
                    raise CheckpointIdentityConflict("scope already belongs to a different cursor_key")
                stored_cursor, revision = row[1], row[2]
            if stored_cursor != expected_cursor:
                raise StaleCheckpointError(
                    f"checkpoint changed before commit (expected revision snapshot {expected_cursor!r})"
                )

            for event in batch:
                payload = event.__dict__.copy()
                payload["from_addresses"] = list(event.from_addresses)
                result = self.conn.execute(
                    """INSERT INTO layer1_onchain_transfer_events
                       (network_id, provider, scope, event_id, transaction_hash,
                        block_number, block_hash, canonical_status, payload_json,
                        inserted_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (network_id, provider, scope, event_id) DO NOTHING
                       RETURNING event_id""",
                    (network_id, provider, scope, event.event_id, event.transaction_hash,
                     event.block_number, event.block_hash, event.canonical_status,
                     Jsonb(payload), now, now),
                )
                if result.fetchone():
                    inserted += 1
                    if event.canonical_status == "REORGED":
                        tombstoned += 1
                    continue

                existing = self.conn.execute(
                    """SELECT payload_json, canonical_status
                       FROM layer1_onchain_transfer_events
                       WHERE network_id=%s AND provider=%s AND scope=%s AND event_id=%s
                       FOR UPDATE""",
                    (network_id, provider, scope, event.event_id),
                ).fetchone()
                prior_payload, prior_status = existing[0], existing[1]
                incoming_payload = dict(payload)
                prior_core, incoming_core = dict(prior_payload), dict(incoming_payload)
                prior_core.pop("canonical_status", None)
                incoming_core.pop("canonical_status", None)
                if prior_core != incoming_core:
                    if allow_recanonicalized and prior_status == "REORGED" and event.canonical_status == "CANONICAL":
                        for field in ("block_number", "block_hash", "block_time", "observed_at"):
                            prior_core.pop(field, None)
                            incoming_core.pop(field, None)
                        if prior_core != incoming_core:
                            raise ValueError("transfer event identity collision: re-included event payload differs")
                        self.conn.execute(
                            """UPDATE layer1_onchain_transfer_events
                               SET transaction_hash=%s, block_number=%s, block_hash=%s,
                                   canonical_status='CANONICAL', payload_json=%s, updated_at=%s
                               WHERE network_id=%s AND provider=%s AND scope=%s AND event_id=%s""",
                            (event.transaction_hash, event.block_number, event.block_hash,
                             Jsonb(payload), now, network_id, provider, scope, event.event_id),
                        )
                    else:
                        raise ValueError("transfer event identity collision: refusing conflicting event payload")
                elif prior_status == "CANONICAL" and event.canonical_status == "REORGED":
                    self.conn.execute(
                        """UPDATE layer1_onchain_transfer_events
                           SET canonical_status='REORGED', payload_json=%s, updated_at=%s
                           WHERE network_id=%s AND provider=%s AND scope=%s AND event_id=%s""",
                        (Jsonb(payload), now, network_id, provider, scope, event.event_id),
                    )
                elif prior_status != event.canonical_status and prior_status != "REORGED" and event.canonical_status != "REORGED":
                    raise ValueError("transfer event identity collision: refusing non-monotonic status change")
                duplicates += 1
                if event.canonical_status == "REORGED":
                    tombstoned += 1

            reorg_changes: list[tuple[int, Optional[str]]] = []
            for block in blocks:
                prior_block = self.conn.execute(
                    """SELECT block_hash FROM layer1_onchain_ingestion_blocks
                       WHERE network_id=%s AND provider=%s AND scope=%s AND block_number=%s
                       FOR UPDATE""",
                    (network_id, provider, scope, block["block_number"]),
                ).fetchone()
                result = self.conn.execute(
                    """INSERT INTO layer1_onchain_ingestion_blocks
                       (network_id, provider, scope, block_number, block_hash, block_time, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s::timestamptz,%s)
                       ON CONFLICT (network_id, provider, scope, block_number) DO UPDATE
                       SET block_hash=EXCLUDED.block_hash, block_time=EXCLUDED.block_time,
                           updated_at=EXCLUDED.updated_at
                       WHERE (layer1_onchain_ingestion_blocks.block_hash=EXCLUDED.block_hash
                              AND layer1_onchain_ingestion_blocks.block_time=EXCLUDED.block_time)
                          OR (%s AND layer1_onchain_ingestion_blocks.block_hash<>EXCLUDED.block_hash
                              AND NOT EXISTS (
                              SELECT 1 FROM layer1_onchain_transfer_events e
                              WHERE e.network_id=EXCLUDED.network_id
                                AND e.provider=EXCLUDED.provider AND e.scope=EXCLUDED.scope
                                AND e.block_number=EXCLUDED.block_number
                                AND e.block_hash=layer1_onchain_ingestion_blocks.block_hash
                                AND e.canonical_status='CANONICAL'
                          ))
                       RETURNING block_hash""",
                    (network_id, provider, scope, block["block_number"], block["block_hash"],
                     block["block_time"], now, allow_recanonicalized),
                )
                if result.fetchone() is None:
                    raise CanonicalBlockConflict("canonical block hash conflict")
                if prior_block is not None and prior_block[0] != block["block_hash"]:
                    reorg_changes.append((block["block_number"], block["block_hash"]))

            for slot in slots:
                prior_slot = self.conn.execute(
                    """SELECT produced, block_hash FROM layer1_onchain_solana_slot_journal
                       WHERE network_id=%s AND provider=%s AND scope=%s AND slot=%s
                       FOR UPDATE""",
                    (network_id, provider, scope, slot["slot"]),
                ).fetchone()
                result = self.conn.execute(
                    """INSERT INTO layer1_onchain_solana_slot_journal
                       (network_id, provider, scope, slot, produced, block_hash, block_time, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s::timestamptz,%s)
                       ON CONFLICT (network_id, provider, scope, slot) DO UPDATE
                       SET produced=EXCLUDED.produced, block_hash=EXCLUDED.block_hash,
                           block_time=EXCLUDED.block_time, updated_at=EXCLUDED.updated_at
                       WHERE (layer1_onchain_solana_slot_journal.produced=EXCLUDED.produced
                              AND layer1_onchain_solana_slot_journal.block_hash IS NOT DISTINCT FROM EXCLUDED.block_hash
                              AND layer1_onchain_solana_slot_journal.block_time IS NOT DISTINCT FROM EXCLUDED.block_time)
                          OR (%s AND (
                              layer1_onchain_solana_slot_journal.produced IS DISTINCT FROM EXCLUDED.produced
                              OR layer1_onchain_solana_slot_journal.block_hash IS DISTINCT FROM EXCLUDED.block_hash
                          ) AND NOT EXISTS (
                              SELECT 1 FROM layer1_onchain_transfer_events e
                              WHERE e.network_id=EXCLUDED.network_id AND e.provider=EXCLUDED.provider
                                AND e.scope=EXCLUDED.scope AND e.block_number=EXCLUDED.slot
                                AND e.canonical_status='CANONICAL'
                                AND e.block_hash IS NOT DISTINCT FROM layer1_onchain_solana_slot_journal.block_hash
                          ))
                       RETURNING slot""",
                    (slot["network_id"], provider, scope, slot["slot"], slot["produced"],
                     slot.get("block_hash"), slot.get("block_time"), now, allow_recanonicalized),
                )
                if result.fetchone() is None:
                    raise CanonicalBlockConflict("canonical Solana slot journal conflict")
                if prior_slot is not None and (
                    bool(prior_slot[0]) != bool(slot["produced"])
                    or prior_slot[1] != slot.get("block_hash")
                ):
                    reorg_changes.append((slot["slot"], slot.get("block_hash")))

            for changed_height, changed_hash in reorg_changes:
                self._invalidate_page_acceptances_for_reorg(
                    network_id, provider, scope, changed_height, changed_hash,
                )
            page_material = {
                "cursor_key": cursor_key,
                "expected_cursor": expected_cursor,
                "next_cursor": next_cursor,
                "scope_identity": [network_id, provider, scope],
                "events": [event.__dict__ for event in batch],
                "canonical_blocks": list(blocks),
                "canonical_slots": list(slots),
            }
            if anchor_observations:
                page_material["provider_observations"] = list(anchor_observations)
            page_id = hashlib.sha256(
                OnChainIngestionStore._canonical(page_material).encode("utf-8")
            ).hexdigest()
            receipts_payload = [item.__dict__ for item in receipts]
            receipts_json = OnChainIngestionStore._canonical(receipts_payload)
            receipt_sha256 = hashlib.sha256(receipts_json.encode("utf-8")).hexdigest()
            prior_page = self.conn.execute(
                "SELECT receipt_sha256 FROM layer1_onchain_ingestion_pages WHERE page_id=%s FOR UPDATE",
                (page_id,),
            ).fetchone()
            if prior_page and prior_page[0] != receipt_sha256:
                raise ValueError("provider receipt replay conflict: page identity has different response evidence")
            if prior_page is None:
                self.conn.execute(
                    """INSERT INTO layer1_onchain_ingestion_pages
                       (page_id, cursor_key, scope_identity, page_material_json,
                        receipt_sha256, receipts_json, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (page_id, cursor_key, Jsonb([network_id, provider, scope]),
                     Jsonb(page_material), receipt_sha256, Jsonb(receipts_payload), now),
                )
            self.conn.execute(
                """UPDATE layer1_onchain_ingestion_checkpoints
                   SET cursor_json=%s, revision=%s, updated_at=%s
                   WHERE cursor_key=%s""",
                (Jsonb(next_cursor), revision + 1, now, cursor_key),
            )
        return {"inserted": inserted, "duplicates": duplicates, "tombstoned": tombstoned}

    def list_page_receipts(self, cursor_key: str) -> tuple[ProviderResponseReceipt, ...]:
        if not isinstance(cursor_key, str) or not cursor_key.strip():
            raise ValueError("cursor_key must be a non-empty string")
        rows = self.conn.execute(
            """SELECT page_id, page_material_json, receipt_sha256, receipts_json
               FROM layer1_onchain_ingestion_pages
               WHERE cursor_key=%s ORDER BY created_at, page_id""",
            (cursor_key,),
        ).fetchall()
        result = []
        for page_id, page_material, expected_digest, payload in rows:
            canonical_page = OnChainIngestionStore._canonical(page_material)
            actual_page_digest = hashlib.sha256(canonical_page.encode("utf-8")).hexdigest()
            if actual_page_digest != page_id:
                raise ValueError("persisted provider page identity digest mismatch")
            canonical_receipts = OnChainIngestionStore._canonical(payload)
            actual_receipt_digest = hashlib.sha256(canonical_receipts.encode("utf-8")).hexdigest()
            if actual_receipt_digest != expected_digest:
                raise ValueError("persisted provider receipt digest mismatch")
            result.extend(ProviderResponseReceipt(**item) for item in payload)
        return tuple(result)

    def get_page_acceptance_material(self, cursor_key: str, page_id: str) -> dict:
        if (not isinstance(cursor_key, str) or not cursor_key.strip()
                or not isinstance(page_id, str) or re.fullmatch(r"[a-f0-9]{64}", page_id) is None):
            raise ValueError("cursor_key and page_id are required")
        row = self.conn.execute(
            """SELECT cursor_key, page_material_json, receipt_sha256, receipts_json
               FROM layer1_onchain_ingestion_pages WHERE page_id=%s""",
            (page_id,),
        ).fetchone()
        if row is None or row[0] != cursor_key:
            raise ValueError("persisted ingestion page does not match requested cursor/page identity")
        page_material, receipts_payload = row[1], row[3]
        if (page_material.get("cursor_key") != cursor_key
                or hashlib.sha256(OnChainIngestionStore._canonical(page_material).encode("utf-8")).hexdigest() != page_id):
            raise ValueError("persisted provider page identity digest mismatch")
        receipts_json = OnChainIngestionStore._canonical(receipts_payload)
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
            block["block_number"]: (block["block_hash"], block["block_time"])
            for block in blocks
        }
        for payload in events:
            event = NormalizedTransferEvent(**payload)
            OnChainIngestionStore._validate_event(event)
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
                   WHERE network_id=%s AND provider=%s AND scope=%s AND block_number=%s""",
                (block["network_id"], block["provider"], block["scope"], block["block_number"]),
            ).fetchone()
            actual_time = actual[1].isoformat() if actual else None
            if actual is None or (actual[0], actual_time) != (block["block_hash"], block["block_time"]):
                raise ValueError("persisted canonical block evidence no longer matches the committed page")
        for slot in slots:
            actual = self.conn.execute(
                """SELECT produced, block_hash, block_time FROM layer1_onchain_solana_slot_journal
                   WHERE network_id=%s AND provider=%s AND scope=%s AND slot=%s""",
                (slot["network_id"], slot["provider"], slot["scope"], slot["slot"]),
            ).fetchone()
            actual_time = actual[2].isoformat() if actual and actual[2] else None
            expected = (bool(slot["produced"]), slot.get("block_hash"), slot.get("block_time"))
            if actual is None or (actual[0], actual[1], actual_time) != expected:
                raise ValueError("persisted canonical Solana slot evidence no longer matches the committed page")
        return {"page_id": page_id, "cursor_key": cursor_key,
                "page_material": page_material, "receipts": receipts_payload,
                "receipt_sha256": row[2]}

    def save_page_acceptance(self, cursor_key: str, page_id: str, key_id: str,
                             payload_json: str, payload_sha256: str, signature: str) -> str:
        if (not isinstance(key_id, str) or re.fullmatch(r"[A-Za-z0-9._-]{1,128}", key_id) is None
                or not isinstance(payload_json, str) or not isinstance(payload_sha256, str)
                or re.fullmatch(r"[a-f0-9]{64}", payload_sha256) is None
                or not isinstance(signature, str) or re.fullmatch(r"[a-f0-9]{64}", signature) is None
                or hashlib.sha256(payload_json.encode("utf-8")).hexdigest() != payload_sha256
                or OnChainIngestionStore._canonical(json.loads(payload_json)) != payload_json):
            raise ValueError("ingestion page acceptance envelope is malformed")
        with self.conn.transaction():
            # Read the immutable page snapshot first without taking a row lock.
            # Then acquire evidence locks in the same table order as commit_page:
            # events -> canonical blocks -> Solana slots -> page row. This avoids
            # an event/block lock inversion with concurrent reorg ingestion.
            page = self.conn.execute(
                "SELECT cursor_key, page_material_json FROM layer1_onchain_ingestion_pages WHERE page_id=%s",
                (page_id,),
            ).fetchone()
            if page is None or page[0] != cursor_key:
                raise ValueError("ingestion page acceptance references an unknown page")
            page_material = page[1]
            for event in sorted(page_material.get("events", []), key=lambda item: item["event_id"]):
                self.conn.execute(
                    """SELECT event_id FROM layer1_onchain_transfer_events
                       WHERE event_id=%s AND network_id=%s AND provider=%s AND scope=%s FOR SHARE""",
                    (event["event_id"], event["network_id"], event["provider"], event["scope"]),
                ).fetchone()
            for block in sorted(page_material.get("canonical_blocks", []), key=lambda item: item["block_number"]):
                self.conn.execute(
                    """SELECT block_number FROM layer1_onchain_ingestion_blocks
                       WHERE network_id=%s AND provider=%s AND scope=%s AND block_number=%s FOR SHARE""",
                    (block["network_id"], block["provider"], block["scope"], block["block_number"]),
                ).fetchone()
            for slot in sorted(page_material.get("canonical_slots", []), key=lambda item: item["slot"]):
                self.conn.execute(
                    """SELECT slot FROM layer1_onchain_solana_slot_journal
                       WHERE network_id=%s AND provider=%s AND scope=%s AND slot=%s FOR SHARE""",
                    (slot["network_id"], slot["provider"], slot["scope"], slot["slot"]),
                ).fetchone()
            locked_page = self.conn.execute(
                "SELECT cursor_key, page_material_json FROM layer1_onchain_ingestion_pages WHERE page_id=%s FOR UPDATE",
                (page_id,),
            ).fetchone()
            if (locked_page is None or locked_page[0] != cursor_key
                    or OnChainIngestionStore._canonical(locked_page[1])
                    != OnChainIngestionStore._canonical(page_material)):
                raise ValueError("ingestion page material changed while acquiring acceptance locks")
            material = self.get_page_acceptance_material(cursor_key, page_id)
            OnChainIngestionStore._validate_acceptance_payload_matches_material(
                material, cursor_key, page_id, key_id, payload_json,
            )
            envelope = (cursor_key, key_id, payload_sha256, payload_json, signature)
            prior = self.conn.execute(
                """SELECT cursor_key, key_id, payload_sha256, payload_json, signature
                   FROM layer1_onchain_ingestion_page_acceptances WHERE page_id=%s FOR UPDATE""",
                (page_id,),
            ).fetchone()
            if prior is not None:
                prior = (*prior[:3], OnChainIngestionStore._canonical(prior[3]), prior[4])
                if prior != envelope:
                    raise ValueError("ingestion page acceptance already exists with conflicting signer evidence")
                return "DUPLICATE"
            self.conn.execute(
                """INSERT INTO layer1_onchain_ingestion_page_acceptances
                   (page_id, cursor_key, key_id, payload_sha256, payload_json, signature)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (page_id, cursor_key, key_id, payload_sha256,
                 self._jsonb(json.loads(payload_json)), signature),
            )
        return "INSERTED"

    def list_ingestion_pages(self) -> tuple[tuple[str, str], ...]:
        """List durable page identities for downstream acceptance verification."""
        rows = self.conn.execute(
            "SELECT cursor_key, page_id FROM layer1_onchain_ingestion_pages ORDER BY created_at, page_id"
        ).fetchall()
        return tuple((cursor_key, page_id) for cursor_key, page_id in rows)

    def list_pending_page_acceptances(self) -> tuple[tuple[str, str], ...]:
        rows = self.conn.execute(
            """SELECT p.cursor_key, p.page_id, p.page_material_json, p.receipts_json
               FROM layer1_onchain_ingestion_pages AS p
               LEFT JOIN layer1_onchain_ingestion_page_acceptances AS a ON a.page_id=p.page_id
               WHERE a.page_id IS NULL ORDER BY p.created_at, p.page_id"""
        ).fetchall()
        pending = []
        for cursor_key, page_id, page_material, receipts_payload in rows:
            receipt_present = receipts_payload not in (None, [])
            if (receipt_present
                    or OnChainIngestionStore._page_material_requires_acceptance(page_material)):
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
            "reason_code": row[2], "affected_evidence": row[3],
            "invalidated_at": row[4].isoformat() if hasattr(row[4], "isoformat") else row[4],
            "key_id": row[5], "payload_sha256": row[6], "signature": row[7],
            "payload_json": row[8],
            "accepted_at": row[9].isoformat() if hasattr(row[9], "isoformat") else row[9],
        } for row in rows)

    def _invalidate_page_acceptances_for_reorg(
        self, network_id: str, provider: str, scope: str, block_number: int,
        canonical_block_hash: str,
    ) -> int:
        rows = self.conn.execute(
            """SELECT p.page_id, p.page_material_json
               FROM layer1_onchain_ingestion_pages AS p
               JOIN layer1_onchain_ingestion_page_acceptances AS a ON a.page_id=p.page_id
               LEFT JOIN layer1_onchain_ingestion_page_acceptance_lifecycle AS l ON l.page_id=p.page_id
               WHERE p.scope_identity=%s AND l.page_id IS NULL FOR UPDATE OF p""",
            (self._jsonb([network_id, provider, scope]),),
        ).fetchall()
        invalidated = 0
        for page_id, material in rows:
            affected = []
            for field, height_field, kind in (
                ("canonical_blocks", "block_number", "CANONICAL_BLOCK"),
                ("canonical_slots", "slot", "CANONICAL_SLOT"),
                ("events", "block_number", "TRANSFER_EVENT"),
                ("provider_observations", "block_height", "PROVIDER_OBSERVATION"),
            ):
                for item in material.get(field, []) if isinstance(material, dict) else []:
                    if (not isinstance(item, dict) or item.get("network_id") != network_id
                            or item.get("provider") != provider or item.get("scope") != scope
                            or item.get(height_field) != block_number):
                        continue
                    old_hash = item.get("block_hash")
                    if old_hash is None and kind == "CANONICAL_SLOT":
                        old_hash = "SKIPPED"
                    if old_hash != canonical_block_hash:
                        affected.append({
                            "kind": kind, "network_id": network_id, "provider": provider,
                            "scope": scope, "height": block_number,
                            "canonical_block_hash": old_hash,
                            "current_canonical_hash": canonical_block_hash,
                        })
            if affected:
                self.conn.execute(
                    """INSERT INTO layer1_onchain_ingestion_page_acceptance_lifecycle
                       (page_id, status, reason_code, affected_evidence_json)
                       VALUES (%s, 'INVALIDATED', 'CANONICAL_EVIDENCE_REORGED', %s)
                       ON CONFLICT(page_id) DO NOTHING""",
                    (page_id, self._jsonb(affected)),
                )
                invalidated += 1
        return invalidated

    def get_page_acceptance(self, cursor_key: str, page_id: str) -> Optional[dict]:
        row = self.conn.execute(
            """SELECT cursor_key, key_id, payload_sha256, payload_json, signature
               FROM layer1_onchain_ingestion_page_acceptances WHERE page_id=%s""",
            (page_id,),
        ).fetchone()
        if row is None:
            return None
        if row[0] != cursor_key:
            raise ValueError("stored ingestion page acceptance belongs to a different cursor")
        return {"cursor_key": row[0], "key_id": row[1], "payload_sha256": row[2],
                "payload_json": OnChainIngestionStore._canonical(row[3]), "signature": row[4]}

    def get_checkpoint(self, cursor_key: str) -> Optional[Any]:
        row = self.conn.execute(
            "SELECT cursor_json FROM layer1_onchain_ingestion_checkpoints WHERE cursor_key=%s",
            (cursor_key,),
        ).fetchone()
        return row[0] if row else None

    def get_event(self, event_id: str, network_id: str, provider: Optional[str] = None,
                  scope: Optional[str] = None) -> Optional[NormalizedTransferEvent]:
        query = "SELECT payload_json FROM layer1_onchain_transfer_events WHERE event_id=%s AND network_id=%s"
        params: list[Any] = [event_id, network_id]
        if provider is not None:
            query += " AND provider=%s"
            params.append(provider)
        if scope is not None:
            query += " AND scope=%s"
            params.append(scope)
        rows = self.conn.execute(query, params).fetchall()
        if len(rows) > 1:
            raise ValueError("event identity is ambiguous; provider and scope are required")
        return self._event(rows[0][0]) if rows else None

    def list_events(self, network_id: str, canonical_only: bool = False) -> list[NormalizedTransferEvent]:
        query = "SELECT payload_json FROM layer1_onchain_transfer_events WHERE network_id=%s"
        params: list[Any] = [network_id]
        if canonical_only:
            query += " AND canonical_status='CANONICAL'"
        query += " ORDER BY block_number, transaction_hash, event_id"
        return [self._event(row[0]) for row in self.conn.execute(query, params).fetchall()]

    def list_all_events(self, canonical_only: bool = False) -> list[NormalizedTransferEvent]:
        query = "SELECT payload_json FROM layer1_onchain_transfer_events"
        if canonical_only:
            query += " WHERE canonical_status='CANONICAL'"
        query += " ORDER BY network_id, block_number, transaction_hash, event_id, scope"
        return [self._event(row[0]) for row in self.conn.execute(query).fetchall()]

    def get_block_hash(self, network_id: str, provider: str, scope: str,
                       block_number: int) -> Optional[str]:
        row = self.conn.execute(
            """SELECT block_hash FROM layer1_onchain_ingestion_blocks
               WHERE network_id=%s AND provider=%s AND scope=%s AND block_number=%s""",
            (network_id, provider, scope, block_number),
        ).fetchone()
        return row[0] if row else None

    def get_solana_slot_journal(self, network_id: str, provider: str, scope: str,
                                start_slot: int, end_slot: int) -> dict[int, dict]:
        rows = self.conn.execute(
            """SELECT slot, produced, block_hash, block_time
               FROM layer1_onchain_solana_slot_journal
               WHERE network_id=%s AND provider=%s AND scope=%s AND slot BETWEEN %s AND %s
               ORDER BY slot""",
            (network_id, provider, scope, start_slot, end_slot),
        ).fetchall()
        return {
            row[0]: {"produced": row[1], "block_hash": row[2],
                     "block_time": row[3].isoformat() if row[3] else None}
            for row in rows
        }

    def reconcile_block(self, network_id: str, block_number: int, canonical_block_hash: str,
                        provider: Optional[str] = None, scope: Optional[str] = None) -> int:
        if not isinstance(network_id, str) or not network_id.strip():
            raise ValueError("network_id is required")
        if isinstance(block_number, bool) or not isinstance(block_number, int) or block_number < 0:
            raise ValueError("block_number must be a non-negative integer")
        if not isinstance(canonical_block_hash, str) or not canonical_block_hash.strip():
            raise ValueError("canonical_block_hash is required")
        if provider is None or scope is None:
            raise ValueError("PostgreSQL reorg reconciliation requires explicit provider and scope")
        network_id, provider, scope = self._identity((network_id, provider, scope))
        clauses = ["network_id=%s", "block_number=%s", "block_hash<>%s", "canonical_status='CANONICAL'", "provider=%s", "scope=%s"]
        params: list[Any] = [network_id, block_number, canonical_block_hash, provider, scope]
        with self.conn.transaction():
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                ("\x1f".join((network_id, provider, scope)),),
            )
            rows = self.conn.execute(
                "SELECT provider, scope, event_id, payload_json FROM layer1_onchain_transfer_events WHERE "
                + " AND ".join(clauses) + " FOR UPDATE", params
            ).fetchall()
            for row in rows:
                payload = dict(row[3])
                payload["canonical_status"] = "REORGED"
                self.conn.execute(
                    """UPDATE layer1_onchain_transfer_events
                       SET canonical_status='REORGED', payload_json=%s, updated_at=now()
                       WHERE network_id=%s AND provider=%s AND scope=%s AND event_id=%s""",
                    (self._jsonb(payload), network_id, row[0], row[1], row[2]),
                )
            self._invalidate_page_acceptances_for_reorg(
                network_id, provider, scope, block_number, canonical_block_hash,
            )
        return len(rows)

    @staticmethod
    def _jsonb(value):
        _, Jsonb = _driver()
        return Jsonb(value)

    def close(self) -> None:
        self.conn.close()


class PostgresOnChainStore:
    """PostgreSQL counterpart of OnChainStore for verified mappings/observations."""

    def __init__(self, dsn: str, engine=None, ingestion_store=None):
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("an explicit PostgreSQL DSN is required")
        psycopg, _ = _driver()
        from .onchain import OnChainIntelligenceEngine
        self.engine = engine or OnChainIntelligenceEngine()
        self.ingestion_store = ingestion_store
        self.conn = psycopg.connect(dsn, autocommit=True)

    @staticmethod
    def _canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def save_verified(self, eligibility, mapping, observation, *, ingestion_store=None,
                      provenance=None) -> str:
        from dataclasses import asdict
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
        from psycopg.types.json import Jsonb
        mapping_payload = asdict(mapping)
        observation_payload = asdict(observation)
        validation_payload = asdict(result)
        with self.conn.transaction():
            mapping_insert = self.conn.execute(
                """INSERT INTO layer1_onchain_asset_mappings(mapping_id, asset_id, network_id, payload_json)
                   VALUES (%s,%s,%s,%s) ON CONFLICT (mapping_id) DO NOTHING
                   RETURNING mapping_id""",
                (mapping.mapping_id, mapping.asset_id, mapping.network_id, Jsonb(mapping_payload)),
            ).fetchone()
            if mapping_insert is None:
                existing = self.conn.execute(
                    "SELECT payload_json FROM layer1_onchain_asset_mappings WHERE mapping_id=%s FOR UPDATE",
                    (mapping.mapping_id,),
                ).fetchone()
                if existing is None or existing[0] != mapping_payload:
                    raise ValueError("mapping ID collision: refusing to overwrite different mapping content")

            observation_insert = self.conn.execute(
                """INSERT INTO layer1_onchain_observations
                   (observation_id, mapping_id, asset_id, network_id, provider, observed_at, payload_json, validation_json)
                   VALUES (%s,%s,%s,%s,%s,%s::timestamptz,%s,%s)
                   ON CONFLICT (observation_id) DO NOTHING
                   RETURNING observation_id""",
                (observation.observation_id, observation.mapping_id, observation.asset_id,
                 observation.network_id, observation.provider, observation.observed_at,
                 Jsonb(observation_payload), Jsonb(validation_payload)),
            ).fetchone()
            if observation_insert is None:
                prior = self.conn.execute(
                    "SELECT payload_json, validation_json FROM layer1_onchain_observations WHERE observation_id=%s FOR UPDATE",
                    (observation.observation_id,),
                ).fetchone()
                if prior != (observation_payload, validation_payload):
                    raise ValueError("observation ID collision: refusing to overwrite different evidence")
                return "DUPLICATE"
        return "INSERTED"

    def get_latest_accepted_observation(self, mapping_id: str):
        from .onchain import OnChainObservation, OnChainValidationResult
        rows = self.conn.execute(
            """SELECT payload_json, validation_json FROM layer1_onchain_observations
               WHERE mapping_id=%s AND validation_json->>'status'='ACCEPTED'
               ORDER BY observed_at DESC""",
            (mapping_id,),
        ).fetchall()
        from .onchain import OnChainAssetMapping, OnChainObservationProvenance
        for payload, validation_payload in rows:
            observation = OnChainObservation(**payload)
            validation = OnChainValidationResult(**validation_payload)
            mapping_row = self.conn.execute(
                "SELECT payload_json FROM layer1_onchain_asset_mappings WHERE mapping_id=%s",
                (mapping_id,),
            ).fetchone()
            if mapping_row is None:
                continue
            mapping = OnChainAssetMapping(**mapping_row[0])
            provenance = OnChainObservationProvenance(
                validation.provenance_cursor_key,
                validation.provenance_page_id,
                validation.provenance_observation_id,
            )
            if (self.engine.verify_persisted_acceptance_receipt(observation, validation)
                    and self.engine.verify_observation_provenance(
                        self.ingestion_store, provenance, mapping, observation,
                    )):
                return observation
        return None

    def get_observation(self, observation_id: str):
        from dataclasses import replace
        from .onchain import OnChainObservation, OnChainValidationResult
        row = self.conn.execute(
            "SELECT payload_json, validation_json FROM layer1_onchain_observations WHERE observation_id=%s",
            (observation_id,),
        ).fetchone()
        if row is None:
            return None
        observation = OnChainObservation(**row[0])
        validation = OnChainValidationResult(**row[1])
        if validation.status == "ACCEPTED":
            from .onchain import OnChainAssetMapping, OnChainObservationProvenance
            mapping_row = self.conn.execute(
                "SELECT payload_json FROM layer1_onchain_asset_mappings WHERE mapping_id=%s",
                (observation.mapping_id,),
            ).fetchone()
            try:
                mapping = OnChainAssetMapping(**mapping_row[0]) if mapping_row else None
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

    def list_verified_mappings(self, network_id: Optional[str] = None):
        from .onchain import OnChainAssetMapping
        query = "SELECT payload_json FROM layer1_onchain_asset_mappings"
        params = ()
        if network_id is not None:
            query += " WHERE network_id=%s"
            params = (network_id,)
        query += " ORDER BY mapping_id"
        mappings = []
        for (payload,) in self.conn.execute(query, params).fetchall():
            mapping = OnChainAssetMapping(**payload)
            if mapping.mapping_status == "VERIFIED" and self.engine._validate_mapping(mapping) is None:
                mappings.append(mapping)
        return mappings

    def close(self):
        self.conn.close()
