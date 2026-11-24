"""Versioned, evidence-linked deep research packages (Module 13)."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from layer1.evidence_verification import ClaimRegistry, SOURCE_KINDS


NONFACTUAL_TYPES = {"ESTIMATE", "ANALYST_INTERPRETATION", "HYPOTHESIS"}
EVENT_STATES = {
    "DISCOVERED", "UNDER_VERIFICATION", "CONFIRMED", "DEVELOPING",
    "RESOLVED", "STALE", "WITHDRAWN", "DISPUTED", "NO_EVENT",
}


def _render_untrusted_field(value: Any) -> str:
    """Keep source/config text on one line and neutralize package delimiters."""
    text = str(value)
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    return text.replace("<<<", "‹‹‹").replace(">>>", "›››").strip()


def _parse_time(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError("research cutoff and source times must be ISO-8601") from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("research cutoff and source times must include timezone")
    return result.astimezone(timezone.utc)


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


_RESEARCH_PACKAGE_CONTENT_FIELDS = frozenset({
    "asset_id", "symbol", "research_question", "cutoff_at", "completeness",
    "required_source_kinds", "source_coverage", "verified_facts", "inferences",
    "disputed_claims", "unknown_claims", "event_states", "gaps",
})
_RESEARCH_PACKAGE_IDENTITY_FIELDS = frozenset({
    "research_key", "package_id", "version", "package_hash",
})


def is_research_package_payload(payload: Any) -> bool:
    return isinstance(payload, dict) and _RESEARCH_PACKAGE_CONTENT_FIELDS.issubset(payload)


def research_package_payload_hash(payload: Mapping[str, Any]) -> str:
    """Hash typed research content or the complete canonical legacy JSON object.

    Typed packages exclude generated/storage identity fields. Legacy generic
    payloads have no such schema contract, so every supplied field is content
    and participates in the digest.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("research package payload must be an object")
    if is_research_package_payload(dict(payload)):
        canonical = {
            key: value for key, value in payload.items()
            if key not in _RESEARCH_PACKAGE_IDENTITY_FIELDS
        }
        return _hash(canonical)
    try:
        canonical = json.dumps(
            dict(payload), sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError):
        raise ValueError("research package payload must be finite JSON data") from None
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResearchPackage:
    research_key: str
    package_id: str
    version: int
    asset_id: str
    symbol: str
    research_question: str
    cutoff_at: str
    completeness: str
    required_source_kinds: tuple[str, ...]
    source_coverage: Mapping[str, Mapping[str, Any]]
    verified_facts: tuple[Mapping[str, Any], ...]
    inferences: tuple[Mapping[str, Any], ...]
    disputed_claims: tuple[Mapping[str, Any], ...]
    unknown_claims: tuple[Mapping[str, Any], ...]
    event_states: tuple[str, ...]
    gaps: tuple[str, ...]
    package_hash: str

    def render(self) -> str:
        lines = [
            "RESEARCH PACKAGE VERSION: " + str(self.version),
            "RESEARCH PACKAGE ID: " + self.package_id,
            "ASSET: $" + self.symbol + " (" + self.asset_id + ")",
            "RESEARCH QUESTION: " + _render_untrusted_field(self.research_question),
            "DATA CUTOFF: " + self.cutoff_at,
            "COMPLETENESS: " + self.completeness,
            "EVENT STATES: " + (", ".join(self.event_states) or "NO_EVENT"),
            "SOURCE COVERAGE:",
        ]
        for kind, data in sorted(self.source_coverage.items()):
            lines.append(
                f"- {kind}: {data['record_count']} accepted records; "
                f"families={','.join(data['source_families']) or 'none'}"
            )
        for heading, items in (
            ("WHAT IS VERIFIED", self.verified_facts),
            ("QUALIFIED INFERENCES", self.inferences),
            ("DISPUTED CLAIMS", self.disputed_claims),
            ("UNKNOWN / UNRESOLVED", self.unknown_claims),
        ):
            lines.append(heading + ":")
            if not items:
                lines.append("- None recorded.")
            for item in items:
                lines.append(
                    "- " + _render_untrusted_field(item["text"]) +
                    " (claim_id=" + str(item["claim_id"]) +
                    "; evidence_ids=" + ",".join(item["evidence_ids"]) + ")"
                )
        lines.append("RESEARCH GAPS:")
        lines.extend("- " + _render_untrusted_field(gap) for gap in self.gaps) if self.gaps else lines.append("- None.")
        lines.append("PACKAGE HASH: " + self.package_hash)
        return "\n".join(lines)


class DeepResearchEngine:
    """Builds reproducible research packages from a typed claim registry only."""

    def build(
        self,
        *,
        asset_id: str,
        symbol: str,
        research_question: str,
        cutoff_at: str,
        registry: ClaimRegistry,
        event_states: Sequence[str] = (),
        required_source_kinds: Sequence[str] = ("PRIMARY", "MARKET"),
    ) -> ResearchPackage:
        if not isinstance(registry, ClaimRegistry):
            raise TypeError("deep research requires a typed ClaimRegistry")
        registry.assert_verifier_issued_and_unchanged()
        if not isinstance(asset_id, str) or not asset_id.startswith("coingecko:"):
            raise ValueError("deep research requires canonical CoinGecko asset identity")
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("deep research requires an asset ticker")
        if not isinstance(research_question, str) or not research_question.strip():
            raise ValueError("research question must be event/candidate specific")
        cutoff = _parse_time(cutoff_at)
        if isinstance(event_states, (str, bytes)) or not isinstance(event_states, Sequence):
            raise ValueError("event lifecycle states must be a finite sequence")
        if any(not isinstance(value, str) or value not in EVENT_STATES for value in event_states):
            raise ValueError("event lifecycle states contain an unsupported state")
        states = tuple(sorted(set(event_states)))
        if isinstance(required_source_kinds, (str, bytes)) or not isinstance(required_source_kinds, Sequence):
            raise ValueError("required source kinds must be a finite sequence")
        if any(not isinstance(value, str) or value not in SOURCE_KINDS for value in required_source_kinds):
            raise ValueError("required source kinds contain an unsupported source kind")
        required = tuple(sorted(set(required_source_kinds)))

        result_by_id = {result.claim_id: result for result in registry.results}
        eligible_evidence = {}
        for record in registry.evidence_records:
            if record.asset_id not in {None, asset_id} or record.source_status != "ACCEPTED":
                continue
            # A canonical subject naming another asset is contradictory even
            # when a malformed record also carries this package's asset_id.
            if record.subject.startswith("coingecko:") and record.subject != asset_id:
                continue
            if (_parse_time(record.published_at) > cutoff or _parse_time(record.observed_at) > cutoff
                    or (record.updated_at and _parse_time(record.updated_at) > cutoff)):
                continue
            eligible_evidence[record.evidence_id] = record

        latest_by_scope = {}
        for claim in registry.claims:
            if claim.subject.startswith("coingecko:") and claim.subject != asset_id:
                continue
            if claim.asset_id is not None:
                if claim.asset_id != asset_id:
                    continue
            elif claim.subject != asset_id:
                continue
            observed = _parse_time(claim.observed_at)
            if observed > cutoff:
                continue
            scope = (claim.subject, claim.asset_id, claim.mapping_id, claim.claim_key, claim.timeframe)
            if claim.claim_key.startswith("announcement.") or claim.claim_key == "onchain.transaction_hash":
                scope += (claim.event_at,)
            current = latest_by_scope.get(scope)
            pair = (claim, result_by_id.get(claim.claim_id))
            if current is None or observed > current[0]:
                latest_by_scope[scope] = (observed, [pair])
            elif observed == current[0]:
                current[1].append(pair)
        selected = [pair for _, values in latest_by_scope.values() for pair in values]
        facts, inferences, disputed, unknown = [], [], [], []
        used_evidence_ids: set[str] = set()
        for claim, result in selected:
            supporting_ids = tuple(result.supporting_evidence_ids) if result else ()
            contradicting_ids = tuple(result.contradicting_evidence_ids) if result else ()
            eligible_supporting_ids = tuple(sorted(
                evidence_id for evidence_id in supporting_ids if evidence_id in eligible_evidence
            ))
            eligible_contradicting_ids = tuple(sorted(
                evidence_id for evidence_id in contradicting_ids if evidence_id in eligible_evidence
            ))
            eligible_ids = (
                eligible_contradicting_ids if result and result.state == "CONTRADICTED"
                else eligible_supporting_ids
            )
            eligible_result = bool(eligible_ids)
            used_evidence_ids.update(eligible_ids)
            item = {
                "claim_id": claim.claim_id,
                "text": claim.text,
                "evidence_ids": list(eligible_ids),
                "state": result.state if result else "UNVERIFIED",
                "claim_type": claim.claim_type,
                "claim_key": claim.claim_key,
                "event_at": claim.event_at,
                "unit": claim.unit,
                "timeframe": claim.timeframe,
            }
            if result and result.state in {"VERIFIED", "CORROBORATED"} and eligible_result:
                facts.append(item)
            elif result and result.state == "CONTRADICTED" and eligible_result:
                disputed.append(item)
            elif claim.claim_type in NONFACTUAL_TYPES:
                inferences.append(item)
            else:
                item["state"] = "UNVERIFIED"
                unknown.append(item)

        coverage_records = {}
        for evidence_id in sorted(used_evidence_ids):
            record = eligible_evidence.get(evidence_id)
            if record is None:
                continue
            group = coverage_records.setdefault(record.source_kind, {})
            group[record.evidence_id] = record.source_family
        source_coverage = {
            kind: {
                "record_count": len(records),
                "source_families": sorted(set(records.values())),
                "evidence_ids": sorted(records),
            }
            for kind, records in sorted(coverage_records.items())
        }
        gaps = []
        missing = sorted(set(required) - set(source_coverage))
        if missing:
            gaps.append("MISSING_REQUIRED_SOURCE_KINDS:" + ",".join(missing))
        if unknown:
            gaps.append("UNRESOLVED_FACTUAL_CLAIMS:" + str(len(unknown)))
        if disputed:
            gaps.append("CONTRADICTED_CLAIMS:" + str(len(disputed)))
        if not facts:
            gaps.append("NO_VERIFIED_FACTS")
        if "STALE" in states:
            gaps.append("EVENT_LIFECYCLE_STALE")
        if "WITHDRAWN" in states:
            gaps.append("EVENT_LIFECYCLE_WITHDRAWN")
        if "DISPUTED" in states:
            gaps.append("EVENT_LIFECYCLE_DISPUTED")

        if "WITHDRAWN" in states or "DISPUTED" in states or disputed:
            completeness = "REJECT"
        elif "STALE" in states:
            completeness = "DEFER"
        elif not facts or missing or unknown:
            completeness = "RESEARCH_MORE"
        else:
            completeness = "READY"

        payload = {
            "asset_id": asset_id, "symbol": symbol.upper(),
            "research_question": research_question.strip(), "cutoff_at": cutoff.isoformat(),
            "completeness": completeness, "required_source_kinds": required,
            "source_coverage": source_coverage, "verified_facts": facts,
            "inferences": inferences, "disputed_claims": disputed,
            "unknown_claims": unknown, "event_states": states, "gaps": sorted(gaps),
        }
        package_hash = _hash(payload)
        research_key = _hash({"asset_id": asset_id, "research_question": research_question.strip()})
        return ResearchPackage(
            research_key=research_key, package_id=research_key + ":pending",
            version=0, asset_id=asset_id, symbol=symbol.upper(),
            research_question=research_question.strip(), cutoff_at=cutoff.isoformat(),
            completeness=completeness, required_source_kinds=required,
            source_coverage=source_coverage, verified_facts=tuple(facts),
            inferences=tuple(inferences), disputed_claims=tuple(disputed),
            unknown_claims=tuple(unknown), event_states=states, gaps=tuple(sorted(gaps)),
            package_hash=package_hash,
        )


class ResearchPackageStore:
    """Append-only, idempotent version store for reproducible research inputs/outputs."""

    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("research package store requires SQLite connection")
        self.connection = connection
        self.connection.execute("""
        CREATE TABLE IF NOT EXISTS layer1_research_package_versions (
            research_key TEXT NOT NULL,
            version INTEGER NOT NULL,
            package_id TEXT NOT NULL UNIQUE,
            package_hash TEXT NOT NULL,
            cutoff_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(research_key, version),
            UNIQUE(research_key, package_hash)
        )
        """)
        self.connection.commit()

    def save(self, package: ResearchPackage) -> ResearchPackage:
        payload = asdict(package)
        if research_package_payload_hash(payload) != package.package_hash:
            raise ValueError("research package hash does not match canonical package payload")
        payload.pop("version")
        payload.pop("package_id")
        with self.connection:
            existing = self.connection.execute(
                "SELECT version, package_id FROM layer1_research_package_versions "
                "WHERE research_key=? AND package_hash=?",
                (package.research_key, package.package_hash),
            ).fetchone()
            if existing:
                return replace(package, version=existing[0], package_id=existing[1])
            current = self.connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM layer1_research_package_versions "
                "WHERE research_key=?",
                (package.research_key,),
            ).fetchone()[0]
            version = int(current) + 1
            package_id = package.research_key + ":" + str(version)
            stored = {**payload, "version": version, "package_id": package_id}
            self.connection.execute(
                "INSERT INTO layer1_research_package_versions "
                "(research_key, version, package_id, package_hash, cutoff_at, payload_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (package.research_key, version, package_id, package.package_hash,
                 package.cutoff_at, json.dumps(stored, sort_keys=True, separators=(",", ":")),
                 datetime.now(timezone.utc).isoformat()),
            )
        return replace(package, version=version, package_id=package_id)

    def load_latest(self, research_key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT package_hash,payload_json FROM layer1_research_package_versions "
            "WHERE research_key=? ORDER BY version DESC LIMIT 1",
            (research_key,),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[1])
        actual_hash = research_package_payload_hash(payload)
        if actual_hash != row[0]:
            raise ValueError("stored research package hash does not match canonical package payload")
        if is_research_package_payload(payload) and actual_hash != payload.get("package_hash"):
            raise ValueError("stored research package hash does not match canonical package payload")
        return payload
