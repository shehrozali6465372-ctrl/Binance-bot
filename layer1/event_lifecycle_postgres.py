"""PostgreSQL-native event lifecycle state machine (Module 21).

Uses the existing publication PostgreSQL connection and the event lifecycle
tables from migration 0001. It preserves EventLifecycleStore's public behavior
without creating or writing a parallel SQLite lifecycle ledger.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from layer1.event_lifecycle import (
    ALLOWED_TRANSITIONS, TERMINAL_STATES, VERIFIED_STATES,
    EventLifecycleRecord, EventLifecycleStore, _time,
)
from layer1.foundation import AnnouncementEvidence


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


class PostgresEventLifecycleStore(EventLifecycleStore):
    """EventLifecycleStore-compatible state machine backed by PostgreSQL."""

    def __init__(self, publication_store: Any):
        required = ("load_event_lifecycle", "sync_event_lifecycle_snapshot")
        connection = getattr(publication_store, "conn", None)
        if (connection is None or not callable(getattr(connection, "execute", None))
                or any(not callable(getattr(publication_store, name, None)) for name in required)):
            raise TypeError("PostgreSQL publication store is required")
        self.store = publication_store
        self.conn = connection

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
            "(event_id,from_state,to_state,reason_code,evidence_refs_json,transitioned_at) "
            "VALUES (%s,%s,%s,%s,%s::jsonb,%s)",
            (event_id,from_state,to_state,reason_code,_json(list(evidence_refs)),transitioned_at),
        )
        self.conn.execute(
            "UPDATE layer1_event_lifecycle SET state=%s,updated_at=%s WHERE event_id=%s",
            (to_state,transitioned_at,event_id),
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
        if verification_state not in VERIFIED_STATES | {"UNVERIFIED","CONTRADICTED","STALE"}:
            raise ValueError("unsupported event evidence verification state")
        if not all(isinstance(value,bool) for value in (materially_new,resolved,withdrawn)):
            raise ValueError("event lifecycle flags must be booleans")
        if resolved and withdrawn:
            raise ValueError("event cannot be resolved and withdrawn in the same transition")
        if resolved and (verification_state not in VERIFIED_STATES or not resolution_evidence_id):
            raise ValueError("resolution evidence must be explicit and verified")
        if withdrawn and (verification_state not in VERIFIED_STATES or not resolution_evidence_id):
            raise ValueError("withdrawal evidence must be explicit and verified")
        if resolution_evidence_id is not None and (
            not isinstance(resolution_evidence_id,str) or not resolution_evidence_id.strip()
        ):
            raise ValueError("resolution evidence reference must be non-empty")
        for timestamp in (
            evidence.published_at,evidence.observed_at,
            evidence.updated_at or evidence.published_at,evidence.event_at or evidence.published_at,
        ):
            _time(timestamp)
        if len(evidence.asset_ids) != 1:
            raise ValueError("event lifecycle requires one exact canonical asset per record")

        asset_id=evidence.asset_ids[0]
        event_id=self.event_identity(evidence,asset_id)
        revision_hash=self._revision_hash(evidence)
        source_updated_at=evidence.updated_at or evidence.published_at
        effective_at=evidence.event_at or evidence.published_at
        evidence_refs=tuple(sorted(
            {evidence.raw_evidence_ref or "source:"+evidence.source_id+":revision:"+revision_hash}
            | ({resolution_evidence_id} if resolution_evidence_id else set())
        ))
        now=evidence.observed_at
        payload=_json(evidence.__dict__)

        with self.conn.transaction():
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("event-lifecycle:"+event_id,),
            )
            row=self.conn.execute(
                "SELECT * FROM layer1_event_lifecycle WHERE event_id=%s FOR UPDATE",
                (event_id,),
            ).fetchone()
            revision=self.conn.execute(
                "SELECT 1 FROM layer1_event_revisions WHERE event_id=%s AND revision_hash=%s",
                (event_id,revision_hash),
            ).fetchone()
            is_new_revision=revision is None
            skip_observation = False
            if row is None:
                self.conn.execute(
                    "INSERT INTO layer1_event_lifecycle "
                    "(event_id,asset_id,source_id,event_type,state,first_published_at,first_observed_at,"
                    "last_updated_at,effective_event_at,latest_revision_hash,updated_at) "
                    "VALUES (%s,%s,%s,%s,'DISCOVERED',%s,%s,%s,%s,%s,%s)",
                    (event_id,asset_id,evidence.source_id,evidence.event_type,evidence.published_at,
                     evidence.observed_at,source_updated_at,effective_at,revision_hash,now),
                )
                self._transition(event_id,None,"DISCOVERED","FIRST_SOURCE_OBSERVATION",evidence_refs,now)
                current_state="DISCOVERED"
            else:
                current_state=row["state"]
                if current_state=="WITHDRAWN":
                    skip_observation = True
                elif current_state in {"STALE","RESOLVED","DISPUTED"} and not is_new_revision:
                    skip_observation = True
                elif not is_new_revision and not (
                    current_state=="UNDER_VERIFICATION" and verification_state in VERIFIED_STATES
                ):
                    skip_observation = True
            if not skip_observation:
                if is_new_revision:
                    self.conn.execute(
                        "INSERT INTO layer1_event_revisions "
                        "(event_id,revision_hash,source_published_at,source_updated_at,observed_at,evidence_ref,payload_json) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)",
                        (event_id,revision_hash,evidence.published_at,evidence.updated_at,
                         evidence.observed_at,evidence_refs[0],payload),
                    )
                    if row is not None:
                        self.conn.execute(
                            "UPDATE layer1_event_lifecycle SET last_updated_at=%s,latest_revision_hash=%s,"
                            "effective_event_at=%s,updated_at=%s WHERE event_id=%s",
                            (source_updated_at,revision_hash,effective_at,now,event_id),
                        )
                if current_state=="DISCOVERED":
                    self._transition(event_id,current_state,"UNDER_VERIFICATION",
                                     "AWAITING_EVIDENCE_VERIFICATION",evidence_refs,now)
                    current_state="UNDER_VERIFICATION"
                if current_state in {"STALE","RESOLVED","DISPUTED"} and materially_new and verification_state in VERIFIED_STATES:
                    self._transition(event_id,current_state,"UNDER_VERIFICATION",
                                     "MATERIAL_NEW_EVIDENCE_REOPENED_EVENT",evidence_refs,now)
                    current_state="UNDER_VERIFICATION"
                if verification_state=="CONTRADICTED" and current_state in {"UNDER_VERIFICATION","CONFIRMED","DEVELOPING"}:
                    target,reason="DISPUTED","SOURCE_EVIDENCE_CONTRADICTED"
                elif verification_state=="STALE" and current_state in {"UNDER_VERIFICATION","CONFIRMED","DEVELOPING"}:
                    target,reason="STALE","SOURCE_EVIDENCE_STALE"
                elif resolved:
                    target,reason="RESOLVED","EXPLICIT_VERIFIED_RESOLUTION"
                elif withdrawn:
                    target,reason="WITHDRAWN","EXPLICIT_VERIFIED_WITHDRAWAL"
                elif verification_state in VERIFIED_STATES and current_state=="UNDER_VERIFICATION":
                    target,reason="CONFIRMED","EVIDENCE_VERIFIED"
                elif materially_new and verification_state in VERIFIED_STATES and current_state=="CONFIRMED":
                    target,reason="DEVELOPING","MATERIAL_NEW_EVIDENCE"
                else:
                    target,reason=None,""
                if target and target!=current_state:
                    self._transition(event_id,current_state,target,reason,evidence_refs,now)
        return self.get(event_id)

    def sync_announcements(
        self, announcements: tuple[AnnouncementEvidence,...] | list[AnnouncementEvidence],
        claim_registry: Any,
    ) -> list[EventLifecycleRecord]:
        from dataclasses import replace
        from layer1.evidence_verification import EvidenceVerificationEngine
        if not isinstance(announcements,(tuple,list)):
            raise TypeError("announcements must be a finite list or tuple")
        claims=tuple(getattr(claim_registry,"claims",()))
        results=tuple(getattr(claim_registry,"results",()))
        if len(claims)!=len(results):
            raise ValueError("claim registry claims/results are inconsistent")
        state_by_claim={claim.claim_id:result.state for claim,result in zip(claims,results)}
        verifier=EvidenceVerificationEngine()
        output=[]
        for announcement in announcements:
            announcement.validate()
            if not announcement.asset_ids:
                continue
            for asset_id in announcement.asset_ids:
                single_asset=replace(announcement,asset_ids=(asset_id,))
                source_evidence=verifier.evidence_from_announcement(single_asset)
                material_states=[]
                for item in source_evidence:
                    if item.claim_key not in {
                        "announcement.title","announcement.event_type","announcement.asset_id","announcement.freshness",
                    }:
                        continue
                    material_states.extend(
                        state_by_claim[claim.claim_id] for claim in claims
                        if item.evidence_id in claim.evidence_ids and claim.claim_id in state_by_claim
                    )
                if material_states and all(state in VERIFIED_STATES for state in material_states):
                    verification_state="VERIFIED"
                elif "CONTRADICTED" in material_states:
                    verification_state="CONTRADICTED"
                elif "STALE" in material_states:
                    verification_state="STALE"
                else:
                    verification_state="UNVERIFIED"
                event_id=self.event_identity(single_asset,asset_id)
                previous=self.conn.execute(
                    "SELECT r.payload_json FROM layer1_event_lifecycle e "
                    "JOIN layer1_event_revisions r ON r.event_id=e.event_id "
                    "AND r.revision_hash=e.latest_revision_hash WHERE e.event_id=%s",
                    (event_id,),
                ).fetchone()
                previous_payload=previous["payload_json"] if previous else None
                if isinstance(previous_payload,dict):
                    previous_payload=_json(previous_payload)
                elif previous_payload is not None and not isinstance(previous_payload,str):
                    previous_payload=_json(previous_payload)
                materially_new=self._has_material_event_change(previous_payload,single_asset)
                output.append(self.observe(single_asset,verification_state=verification_state,
                                           materially_new=materially_new))
        return output

    def mark_stale(self,event_id: str,*,now: str,max_age_seconds: int) -> EventLifecycleRecord:
        if not isinstance(event_id,str) or not event_id.strip():
            raise ValueError("event_id is required")
        if isinstance(max_age_seconds,bool) or not isinstance(max_age_seconds,int) or max_age_seconds<=0:
            raise ValueError("max_age_seconds must be a positive integer")
        current_time=_time(now)
        record=self.get(event_id)
        if record.state in TERMINAL_STATES | {"RESOLVED","STALE","DISPUTED"}:
            return record
        if (current_time-_time(record.last_updated_at)).total_seconds()<max_age_seconds:
            raise ValueError("event has not exceeded its freshness window")
        with self.conn.transaction():
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",("event-lifecycle:"+event_id,),
            )
            row=self.conn.execute(
                "SELECT state FROM layer1_event_lifecycle WHERE event_id=%s FOR UPDATE",(event_id,),
            ).fetchone()
            if row is None:
                raise KeyError("event lifecycle record not found")
            if row["state"] not in TERMINAL_STATES | {"RESOLVED","STALE","DISPUTED"}:
                self._transition(event_id,row["state"],"STALE","FRESHNESS_WINDOW_EXCEEDED",(),
                                 current_time.isoformat())
        return self.get(event_id)

    def get_for_source(self,asset_id: str,source_id: str) -> EventLifecycleRecord:
        if not isinstance(asset_id,str) or not asset_id.strip():
            raise ValueError("canonical asset_id is required")
        if not isinstance(source_id,str) or not source_id.strip():
            raise ValueError("exact event source_id is required")
        rows=self.conn.execute(
            "SELECT event_id FROM layer1_event_lifecycle WHERE asset_id=%s AND source_id=%s ORDER BY event_id",
            (asset_id,source_id),
        ).fetchall()
        if not rows:
            raise KeyError("event lifecycle record not found for exact asset/source")
        if len(rows)!=1:
            raise ValueError("event lifecycle source identity is ambiguous for this asset")
        return self.get(rows[0]["event_id"])

    def latest_for_asset(self,asset_id: str) -> Optional[EventLifecycleRecord]:
        if not isinstance(asset_id,str) or not asset_id.strip():
            raise ValueError("canonical asset_id is required")
        row=self.conn.execute(
            "SELECT event_id FROM layer1_event_lifecycle WHERE asset_id=%s "
            "ORDER BY last_updated_at DESC,event_id ASC LIMIT 1",(asset_id,),
        ).fetchone()
        return self.get(row["event_id"]) if row else None

    def get(self,event_id: str) -> EventLifecycleRecord:
        record=self.store.load_event_lifecycle(event_id)
        if record is None:
            raise KeyError("event lifecycle record not found")
        return EventLifecycleRecord(
            record["event_id"],record["asset_id"],record["source_id"],record["event_type"],record["state"],
            record["first_published_at"],record["first_observed_at"],record["last_updated_at"],
            record["effective_event_at"],record["latest_revision_hash"],
        )

    def history(self,event_id: str) -> list[dict[str,Any]]:
        if not isinstance(event_id,str) or not event_id.strip():
            raise ValueError("event_id is required")
        record=self.store.load_event_lifecycle(event_id)
        if record is None:
            raise KeyError("event lifecycle record not found")
        return list(record["history"])

    def bootstrap_sqlite_snapshots(self,sqlite_connection: Any) -> tuple[str,...]:
        """Import only lifecycle events absent from PostgreSQL; never overwrite PG authority."""
        if sqlite_connection is None or not callable(getattr(sqlite_connection,"execute",None)):
            raise TypeError("existing SQLite lifecycle connection is required for one-time bootstrap")
        exists=sqlite_connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='layer1_event_lifecycle'"
        ).fetchone()
        if exists is None:
            return ()
        event_rows=sqlite_connection.execute(
            "SELECT event_id FROM layer1_event_lifecycle ORDER BY event_id"
        ).fetchall()
        imported=[]
        for row in event_rows:
            event_id=row[0]
            if self.store.load_event_lifecycle(event_id) is None:
                self.store.sync_event_lifecycle_snapshot(sqlite_connection,event_id)
                imported.append(event_id)
        return tuple(imported)

    def close(self) -> None:
        """Compatibility no-op; connection is owned by PostgresPublicationStore."""
        return None
