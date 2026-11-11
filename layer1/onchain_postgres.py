"""PostgreSQL persistence for Module 9.

The SQLite stores remain the default for local development and existing tests.
PostgreSQL is opt-in: callers must provide an explicit DSN and apply migrations
separately. No environment-variable fallback or automatic production migration
is performed here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Optional

from .onchain_ingestion import NormalizedTransferEvent, OnChainIngestionStore

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
                # These checked-in migrations contain ordinary DDL only; dollar-
                # quoted procedural blocks are intentionally not supported.
                for statement in source.split(";"):
                    if statement.strip():
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
    ) -> dict:
        if not isinstance(cursor_key, str) or not cursor_key.strip():
            raise ValueError("cursor_key must be a non-empty string")
        if expected_cursor is _UNSET:
            raise ValueError("PostgreSQL commits require the checkpoint snapshot in expected_cursor")
        if not isinstance(allow_recanonicalized, bool):
            raise ValueError("allow_recanonicalized must be boolean")
        network_id, provider, scope = self._identity(scope_identity)
        batch, blocks, slots = tuple(events), tuple(canonical_blocks), tuple(canonical_slots)
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

            for block in blocks:
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

            for slot in slots:
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

            self.conn.execute(
                """UPDATE layer1_onchain_ingestion_checkpoints
                   SET cursor_json=%s, revision=%s, updated_at=%s
                   WHERE cursor_key=%s""",
                (Jsonb(next_cursor), revision + 1, now, cursor_key),
            )
        return {"inserted": inserted, "duplicates": duplicates, "tombstoned": tombstoned}

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
        return len(rows)

    @staticmethod
    def _jsonb(value):
        _, Jsonb = _driver()
        return Jsonb(value)

    def close(self) -> None:
        self.conn.close()


class PostgresOnChainStore:
    """PostgreSQL counterpart of OnChainStore for verified mappings/observations."""

    def __init__(self, dsn: str, engine=None):
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("an explicit PostgreSQL DSN is required")
        psycopg, _ = _driver()
        from .onchain import OnChainIntelligenceEngine
        self.engine = engine or OnChainIntelligenceEngine()
        self.conn = psycopg.connect(dsn, autocommit=True)

    @staticmethod
    def _canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def save_verified(self, eligibility, mapping, observation) -> str:
        from dataclasses import asdict
        result = self.engine.validate(eligibility, mapping, observation)
        if result.status != "ACCEPTED":
            raise ValueError(f"only an ACCEPTED on-chain observation may be persisted: {result.reason_code}")
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
        from .onchain import OnChainObservation
        row = self.conn.execute(
            """SELECT payload_json FROM layer1_onchain_observations
               WHERE mapping_id=%s AND validation_json->>'status'='ACCEPTED'
               ORDER BY observed_at DESC LIMIT 1""",
            (mapping_id,),
        ).fetchone()
        return OnChainObservation(**row[0]) if row else None

    def get_observation(self, observation_id: str):
        from .onchain import OnChainObservation, OnChainValidationResult
        row = self.conn.execute(
            "SELECT payload_json, validation_json FROM layer1_onchain_observations WHERE observation_id=%s",
            (observation_id,),
        ).fetchone()
        return (OnChainObservation(**row[0]), OnChainValidationResult(**row[1])) if row else None

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
