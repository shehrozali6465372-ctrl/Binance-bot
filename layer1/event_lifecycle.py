"""Durable, deterministic lifecycle state for canonical source-backed events.

This store shares the existing Layer1Store SQLite connection. It is deliberately
conservative: a source observation alone cannot confirm, resolve, or withdraw an event.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from layer1.foundation import AnnouncementEvidence


VERIFIED_STATES = {"VERIFIED", "CORROBORATED"}
ACTIVE_STATES = {"DISCOVERED", "UNDER_VERIFICATION", "CONFIRMED", "DEVELOPING", "STALE", "DISPUTED"}
TERMINAL_STATES = {"WITHDRAWN"}
ALLOWED_TRANSITIONS = {
    "DISCOVERED": {"UNDER_VERIFICATION"},
    "UNDER_VERIFICATION": {"CONFIRMED", "RESOLVED", "STALE", "WITHDRAWN", "DISPUTED"},
    "CONFIRMED": {"DEVELOPING", "RESOLVED", "STALE", "WITHDRAWN", "DISPUTED"},
    "DEVELOPING": {"RESOLVED", "STALE", "WITHDRAWN", "DISPUTED"},
    "STALE": {"UNDER_VERIFICATION"},
    "RESOLVED": {"UNDER_VERIFICATION"},
    "DISPUTED": {"UNDER_VERIFICATION", "RESOLVED", "WITHDRAWN"},
    "WITHDRAWN": set(),
}


def _time(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("lifecycle timestamp is required")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("lifecycle timestamp must be ISO-8601") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("lifecycle timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EventLifecycleRecord:
    event_id: str
    asset_id: str
    source_id: str
    event_type: str
    state: str
    first_published_at: str
    first_observed_at: str
    last_updated_at: str
    effective_event_at: str
    latest_revision_hash: str


class EventLifecycleStore:
    """Append-only event transition history plus a transactionally maintained current state."""

    def __init__(self, layer1_store: Any):
        connection = getattr(layer1_store, "conn", None)
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("EventLifecycleStore requires an existing Layer1Store connection")
        self.conn = connection
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS layer1_event_lifecycle (
            event_id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            state TEXT NOT NULL,
            first_published_at TEXT NOT NULL,
            first_observed_at TEXT NOT NULL,
            last_updated_at TEXT NOT NULL,
            effective_event_at TEXT NOT NULL,
            latest_revision_hash TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS layer1_event_revisions (
            event_id TEXT NOT NULL,
            revision_hash TEXT NOT NULL,
            source_published_at TEXT NOT NULL,
            source_updated_at TEXT,
            observed_at TEXT NOT NULL,
            evidence_ref TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY(event_id, revision_hash),
            FOREIGN KEY(event_id) REFERENCES layer1_event_lifecycle(event_id)
        );
        CREATE TABLE IF NOT EXISTS layer1_event_transitions (
            transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            from_state TEXT,
            to_state TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            evidence_refs_json TEXT NOT NULL,
            transitioned_at TEXT NOT NULL,
            FOREIGN KEY(event_id) REFERENCES layer1_event_lifecycle(event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_layer1_event_state
            ON layer1_event_lifecycle(state, last_updated_at);
        CREATE INDEX IF NOT EXISTS idx_layer1_event_transition_history
            ON layer1_event_transitions(event_id, transition_id);
        """)
        self.conn.commit()

    @staticmethod
    def event_identity(evidence: AnnouncementEvidence, asset_id: str) -> str:
        evidence.validate()
        if asset_id not in evidence.asset_ids:
            raise ValueError("event identity requires an asset linked by the source evidence")
        # A provider-stable ID is the only safe revision lineage. Fingerprint IDs
        # remain separate so title edits cannot be guessed to be the same event.
        identity = "|".join((asset_id, evidence.event_type, evidence.source_id_kind, evidence.source_id))
        return "event:" + _digest(identity)

    @staticmethod
    def _revision_hash(evidence: AnnouncementEvidence) -> str:
        if evidence.content_hash:
            return evidence.content_hash
        return _digest(json.dumps({
            "source_id": evidence.source_id, "title": evidence.title,
            "published_at": evidence.published_at, "updated_at": evidence.updated_at,
        }, sort_keys=True, separators=(",", ":")))

    def _transition(
        self, event_id: str, from_state: Optional[str], to_state: str,
        reason_code: str, evidence_refs: tuple[str, ...], transitioned_at: str,
    ) -> None:
        if from_state is None:
            if to_state != "DISCOVERED":
                raise ValueError("illegal event lifecycle transition")
        elif to_state not in ALLOWED_TRANSITIONS.get(from_state, set()):
            raise ValueError("illegal event lifecycle transition")
        self.conn.execute(
            "INSERT INTO layer1_event_transitions "
            "(event_id, from_state, to_state, reason_code, evidence_refs_json, transitioned_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, from_state, to_state, reason_code,
             json.dumps(list(evidence_refs), separators=(",", ":")), transitioned_at),
        )
        self.conn.execute(
            "UPDATE layer1_event_lifecycle SET state=?, updated_at=? WHERE event_id=?",
            (to_state, transitioned_at, event_id),
        )

    def observe(
        self,
        evidence: AnnouncementEvidence,
        *,
        verification_state: str,
        materially_new: bool = False,
        resolved: bool = False,
        withdrawn: bool = False,
        resolution_evidence_id: Optional[str] = None,
    ) -> EventLifecycleRecord:
        evidence.validate()
        if verification_state not in VERIFIED_STATES | {"UNVERIFIED", "CONTRADICTED", "STALE"}:
            raise ValueError("unsupported event evidence verification state")
        if not isinstance(materially_new, bool) or not isinstance(resolved, bool) or not isinstance(withdrawn, bool):
            raise ValueError("event lifecycle flags must be booleans")
        if resolved and withdrawn:
            raise ValueError("event cannot be resolved and withdrawn in the same transition")
        if resolved and (verification_state not in VERIFIED_STATES or not resolution_evidence_id):
            raise ValueError("resolution evidence must be explicit and verified")
        if withdrawn and (verification_state not in VERIFIED_STATES or not resolution_evidence_id):
            raise ValueError("withdrawal evidence must be explicit and verified")
        if resolution_evidence_id is not None and (
            not isinstance(resolution_evidence_id, str) or not resolution_evidence_id.strip()
        ):
            raise ValueError("resolution evidence reference must be non-empty")
        for timestamp in (evidence.published_at, evidence.observed_at, evidence.updated_at or evidence.published_at,
                          evidence.event_at or evidence.published_at):
            _time(timestamp)

        asset_id = evidence.asset_ids[0] if len(evidence.asset_ids) == 1 else None
        if asset_id is None:
            raise ValueError("event lifecycle requires one exact canonical asset per record")
        event_id = self.event_identity(evidence, asset_id)
        revision_hash = self._revision_hash(evidence)
        source_updated_at = evidence.updated_at or evidence.published_at
        effective_at = evidence.event_at or evidence.published_at
        evidence_refs = tuple(sorted({evidence.raw_evidence_ref or
                                      "source:" + evidence.source_id + ":revision:" + revision_hash}
                                     | ({resolution_evidence_id} if resolution_evidence_id else set())))
        now = evidence.observed_at
        payload = json.dumps(evidence.__dict__, sort_keys=True, separators=(",", ":"), allow_nan=False)

        with self.conn:
            row = self.conn.execute(
                "SELECT * FROM layer1_event_lifecycle WHERE event_id=?", (event_id,)
            ).fetchone()
            is_new_revision = self.conn.execute(
                "SELECT 1 FROM layer1_event_revisions WHERE event_id=? AND revision_hash=?",
                (event_id, revision_hash),
            ).fetchone() is None
            if row is None:
                self.conn.execute(
                    "INSERT INTO layer1_event_lifecycle VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (event_id, asset_id, evidence.source_id, evidence.event_type, "DISCOVERED",
                     evidence.published_at, evidence.observed_at, source_updated_at,
                     effective_at, revision_hash, now),
                )
                self._transition(event_id, None, "DISCOVERED", "FIRST_SOURCE_OBSERVATION",
                                 evidence_refs, now)
                current_state = "DISCOVERED"
            else:
                current_state = row["state"] if isinstance(row, sqlite3.Row) else row[4]
                if current_state == "WITHDRAWN":
                    return self.get(event_id)
                if current_state in {"STALE", "RESOLVED", "DISPUTED"} and not is_new_revision:
                    return self.get(event_id)
                if not is_new_revision and not (current_state == "UNDER_VERIFICATION" and verification_state in VERIFIED_STATES):
                    return self.get(event_id)
            if is_new_revision:
                self.conn.execute(
                    "INSERT INTO layer1_event_revisions VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (event_id, revision_hash, evidence.published_at, evidence.updated_at,
                     evidence.observed_at, evidence_refs[0], payload),
                )
                if row is not None:
                    self.conn.execute(
                        "UPDATE layer1_event_lifecycle SET last_updated_at=?, latest_revision_hash=?, "
                        "effective_event_at=?, updated_at=? WHERE event_id=?",
                        (source_updated_at, revision_hash, effective_at, now, event_id),
                    )
            if current_state == "DISCOVERED":
                self._transition(event_id, current_state, "UNDER_VERIFICATION",
                                 "AWAITING_EVIDENCE_VERIFICATION", evidence_refs, now)
                current_state = "UNDER_VERIFICATION"
            if current_state in {"STALE", "RESOLVED", "DISPUTED"} and materially_new and verification_state in VERIFIED_STATES:
                self._transition(event_id, current_state, "UNDER_VERIFICATION",
                                 "MATERIAL_NEW_EVIDENCE_REOPENED_EVENT", evidence_refs, now)
                current_state = "UNDER_VERIFICATION"
            if verification_state == "CONTRADICTED" and current_state in {"UNDER_VERIFICATION", "CONFIRMED", "DEVELOPING"}:
                target = "DISPUTED"
                reason = "SOURCE_EVIDENCE_CONTRADICTED"
            elif verification_state == "STALE" and current_state in {"UNDER_VERIFICATION", "CONFIRMED", "DEVELOPING"}:
                target = "STALE"
                reason = "SOURCE_EVIDENCE_STALE"
            elif resolved:
                target = "RESOLVED"
                reason = "EXPLICIT_VERIFIED_RESOLUTION"
            elif withdrawn:
                target = "WITHDRAWN"
                reason = "EXPLICIT_VERIFIED_WITHDRAWAL"
            elif verification_state in VERIFIED_STATES and current_state in {"UNDER_VERIFICATION", "STALE", "RESOLVED"}:
                target = "CONFIRMED"
                reason = "EVIDENCE_VERIFIED"
            elif materially_new and verification_state in VERIFIED_STATES and current_state == "CONFIRMED":
                target = "DEVELOPING"
                reason = "MATERIAL_NEW_EVIDENCE"
            else:
                target = None
                reason = ""
            if target and target != current_state:
                self._transition(event_id, current_state, target, reason, evidence_refs, now)
            return self.get(event_id)

    @staticmethod
    def _normalized_material_text(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()

    @classmethod
    def _has_material_event_change(cls, previous_payload_json: Optional[str],
                                   evidence: AnnouncementEvidence) -> bool:
        """Compare source-stable event facts, not incidental revision metadata.

        Title, event type and announcement body capture source-visible changes;
        effective event time captures rescheduling. Body comparison is deliberately
        conservative: any normalized textual change is material, without claiming
        to understand its semantics. Content hashes, observation timestamps and
        source update timestamps alone do not prove a material event development.
        """
        if previous_payload_json is None:
            return False
        previous = json.loads(previous_payload_json)
        if cls._normalized_material_text(previous.get("title")) != cls._normalized_material_text(evidence.title):
            return True
        if cls._normalized_material_text(previous.get("event_type")) != cls._normalized_material_text(evidence.event_type):
            return True
        previous_body = cls._normalized_material_text(previous.get("body"))
        current_body = cls._normalized_material_text(evidence.body)
        if previous_body != current_body and (previous_body or current_body):
            return True
        old_event_at = previous.get("event_at")
        new_event_at = evidence.event_at
        if old_event_at is None and new_event_at is None:
            return False
        if old_event_at is None or new_event_at is None:
            return True
        return _time(old_event_at) != _time(new_event_at)

    def sync_announcements(
        self, announcements: tuple[AnnouncementEvidence, ...] | list[AnnouncementEvidence],
        claim_registry: Any,
    ) -> list[EventLifecycleRecord]:
        """Persist lifecycle observations using only Module 11's attributable verification results."""
        from dataclasses import replace
        from layer1.evidence_verification import EvidenceVerificationEngine

        if not isinstance(announcements, (tuple, list)):
            raise TypeError("announcements must be a finite list or tuple")
        claims = tuple(getattr(claim_registry, "claims", ()))
        results = tuple(getattr(claim_registry, "results", ()))
        if len(claims) != len(results):
            raise ValueError("claim registry claims/results are inconsistent")
        state_by_claim = {claim.claim_id: result.state for claim, result in zip(claims, results)}
        verifier = EvidenceVerificationEngine()
        output = []
        for announcement in announcements:
            announcement.validate()
            if not announcement.asset_ids:
                continue
            for asset_id in announcement.asset_ids:
                single_asset = replace(announcement, asset_ids=(asset_id,))
                source_evidence = verifier.evidence_from_announcement(single_asset)
                material_states = []
                for item in source_evidence:
                    if item.claim_key not in {
                        "announcement.title", "announcement.event_type",
                        "announcement.asset_id", "announcement.freshness",
                    }:
                        continue
                    linked_states = [
                        state_by_claim[claim.claim_id]
                        for claim in claims
                        if item.evidence_id in claim.evidence_ids and claim.claim_id in state_by_claim
                    ]
                    material_states.extend(linked_states)
                if material_states and all(state in VERIFIED_STATES for state in material_states):
                    verification_state = "VERIFIED"
                elif "CONTRADICTED" in material_states:
                    verification_state = "CONTRADICTED"
                elif "STALE" in material_states:
                    verification_state = "STALE"
                else:
                    verification_state = "UNVERIFIED"
                event_id = self.event_identity(single_asset, asset_id)
                previous_revision = self.conn.execute(
                    "SELECT r.payload_json FROM layer1_event_lifecycle AS e "
                    "JOIN layer1_event_revisions AS r "
                    "ON r.event_id=e.event_id AND r.revision_hash=e.latest_revision_hash "
                    "WHERE e.event_id=?", (event_id,),
                ).fetchone()
                previous_payload_json = previous_revision[0] if previous_revision else None
                materially_new = self._has_material_event_change(
                    previous_payload_json, single_asset,
                )
                output.append(self.observe(
                    single_asset, verification_state=verification_state,
                    materially_new=materially_new,
                ))
        return output

    def mark_stale(self, event_id: str, *, now: str, max_age_seconds: int) -> EventLifecycleRecord:
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id is required")
        if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) or max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be a positive integer")
        current_time = _time(now)
        record = self.get(event_id)
        if record.state in TERMINAL_STATES | {"RESOLVED", "STALE", "DISPUTED"}:
            return record
        last_updated = _time(record.last_updated_at)
        age = (current_time - last_updated).total_seconds()
        if age < max_age_seconds:
            raise ValueError("event has not exceeded its freshness window")
        with self.conn:
            self._transition(event_id, record.state, "STALE", "FRESHNESS_WINDOW_EXCEEDED", (),
                             current_time.isoformat())
        return self.get(event_id)

    @staticmethod
    def index_by_asset_source(
        records: list[EventLifecycleRecord] | tuple[EventLifecycleRecord, ...],
    ) -> dict[str, dict[str, dict[str, dict[str, str]]]]:
        """Index lifecycle records without collapsing distinct events for one asset."""
        if not isinstance(records, (list, tuple)):
            raise TypeError("event lifecycle records must be a finite list or tuple")
        indexed: dict[str, dict[str, dict[str, dict[str, str]]]] = {}
        for record in records:
            if not isinstance(record, EventLifecycleRecord):
                raise TypeError("event lifecycle index requires EventLifecycleRecord values")
            source_events = indexed.setdefault(record.asset_id, {}).setdefault(record.source_id, {})
            value = {"event_id": record.event_id, "state": record.state}
            previous = source_events.get(record.event_type)
            if previous is not None and previous != value:
                raise ValueError("conflicting lifecycle records share an asset/source/event type")
            source_events[record.event_type] = value
        return indexed

    def get_for_source(self, asset_id: str, source_id: str) -> EventLifecycleRecord:
        """Resolve one event by its exact asset/source identity; never fall back to latest."""
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ValueError("canonical asset_id is required")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("exact event source_id is required")
        rows = self.conn.execute(
            "SELECT event_id FROM layer1_event_lifecycle WHERE asset_id=? AND source_id=? "
            "ORDER BY event_id",
            (asset_id, source_id),
        ).fetchall()
        if not rows:
            raise KeyError("event lifecycle record not found for exact asset/source")
        if len(rows) != 1:
            raise ValueError("event lifecycle source identity is ambiguous for this asset")
        return self.get(rows[0][0])

    def latest_for_asset(self, asset_id: str) -> Optional[EventLifecycleRecord]:
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ValueError("canonical asset_id is required")
        row = self.conn.execute(
            "SELECT event_id FROM layer1_event_lifecycle WHERE asset_id=? "
            "ORDER BY last_updated_at DESC, event_id ASC LIMIT 1",
            (asset_id,),
        ).fetchone()
        return self.get(row[0]) if row else None

    def get(self, event_id: str) -> EventLifecycleRecord:
        row = self.conn.execute(
            "SELECT event_id, asset_id, source_id, event_type, state, first_published_at, "
            "first_observed_at, last_updated_at, effective_event_at, latest_revision_hash "
            "FROM layer1_event_lifecycle WHERE event_id=?", (event_id,),
        ).fetchone()
        if row is None:
            raise KeyError("event lifecycle record not found")
        return EventLifecycleRecord(*tuple(row))

    def history(self, event_id: str) -> list[dict[str, Any]]:
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id is required")
        rows = self.conn.execute(
            "SELECT from_state, to_state, reason_code, evidence_refs_json, transitioned_at "
            "FROM layer1_event_transitions WHERE event_id=? ORDER BY transition_id",
            (event_id,),
        ).fetchall()
        return [{
            "from_state": row[0], "to_state": row[1], "reason_code": row[2],
            "evidence_refs": json.loads(row[3]), "transitioned_at": row[4],
        } for row in rows]
