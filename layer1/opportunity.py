"""Deterministic opportunity gate with explicit, externally approved policy (Module 14)."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Optional


FACTOR_NAMES = (
    "evidence_strength", "timeliness", "materiality",
    "audience_usefulness", "novelty", "risk_control",
)


def _time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError("opportunity timestamps must be ISO-8601") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("opportunity timestamps must include timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class OpportunityPolicy:
    policy_version: str
    weights: Mapping[str, float]
    proceed_threshold: float
    defer_threshold: float
    max_eligibility_age_seconds: int = 300

    def validate(self) -> None:
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("opportunity policy version is required")
        if set(self.weights) != set(FACTOR_NAMES):
            raise ValueError("opportunity policy must define every named factor exactly once")
        values = list(self.weights.values())
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("opportunity weights must be finite non-negative numbers")
        if not math.isclose(sum(values), 1.0, rel_tol=0, abs_tol=1e-9):
            raise ValueError("opportunity weights must sum to 1.0")
        thresholds = (self.proceed_threshold, self.defer_threshold)
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in thresholds
        ) or not 0 <= self.defer_threshold < self.proceed_threshold <= 100:
            raise ValueError("opportunity thresholds must be finite numbers satisfying 0 <= defer < proceed <= 100")
        if isinstance(self.max_eligibility_age_seconds, bool) or not isinstance(self.max_eligibility_age_seconds, int) or self.max_eligibility_age_seconds <= 0:
            raise ValueError("eligibility age bound must be a positive integer")


@dataclass(frozen=True)
class OpportunityDecision:
    state: str
    score: Optional[float]
    reasons: tuple[str, ...]
    policy_version: str
    decision_id: str
    input_snapshot_json: str = "{}"



_FACTOR_ASSESSMENT_STATUSES = frozenset({
    "READY", "MISSING", "STALE", "CONFLICTED", "UNVERIFIED",
})
_SUBFEATURE_AVAILABILITIES = frozenset({
    "AVAILABLE", "MISSING", "STALE", "CONFLICTED", "UNVERIFIED",
})
_SHA256_LENGTH = 64


def _required_text(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + " must be a non-empty string")
    return value


def _utc_timestamp(value, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(field + " must be a UTC ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(field + " must be a UTC ISO-8601 timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(field + " must be a UTC ISO-8601 timestamp")
    return parsed.astimezone(timezone.utc)


def _validate_v2_subfeature(subfeature, *, asset_id: str, cutoff: datetime) -> None:
    required = {
        "feature_key", "asset_id", "availability", "raw_value", "normalized_value",
        "unit", "source_refs", "source_payload_hashes", "provider_timestamp",
        "event_at", "event_time_semantics", "published_at", "updated_at",
        "observed_at", "window_start_at",
        "window_end_at", "transformation_id", "transformation_version",
        "baseline_id", "baseline_version", "source_dependency_group",
        "quality_flags", "missing_reason",
    }
    if not isinstance(subfeature, dict) or set(subfeature) != required:
        raise ValueError("factor subfeature provenance fields are incomplete or unknown")
    _required_text(subfeature["feature_key"], "subfeature feature_key")
    if subfeature["asset_id"] != asset_id:
        raise ValueError("factor subfeature asset identity does not match decision asset")
    availability = subfeature["availability"]
    if not isinstance(availability, str) or availability not in _SUBFEATURE_AVAILABILITIES:
        raise ValueError("factor subfeature availability is not supported")
    _required_text(subfeature["unit"], "subfeature unit")
    refs = subfeature["source_refs"]
    if (not isinstance(refs, list)
            or any(not isinstance(ref, str) or not ref.strip() for ref in refs)
            or len(refs) != len(set(refs))):
        raise ValueError("factor subfeature source references are invalid")
    if availability == "AVAILABLE" and not refs:
        raise ValueError("available factor subfeature requires at least one source reference")
    hashes = subfeature["source_payload_hashes"]
    if (not isinstance(hashes, list)
            or any(not isinstance(value, str) or len(value) != _SHA256_LENGTH
                   or any(char not in "0123456789abcdef" for char in value)
                   for value in hashes)
            or len(hashes) != len(set(hashes))):
        raise ValueError("factor subfeature source payload hashes must be lowercase SHA-256")
    flags = subfeature["quality_flags"]
    if (not isinstance(flags, list)
            or any(not isinstance(flag, str) or not flag.strip() for flag in flags)
            or len(flags) != len(set(flags))):
        raise ValueError("factor subfeature quality flags are invalid")
    event_at = subfeature["event_at"]
    event_semantics = subfeature["event_time_semantics"]
    if event_at is None:
        if event_semantics is not None:
            raise ValueError("factor subfeature event-time semantics require event_at")
    else:
        event_time = _utc_timestamp(event_at, "subfeature event_at")
        if event_time > cutoff and event_semantics != "SCHEDULED_FUTURE_EVENT":
            raise ValueError("future event_at requires explicit SCHEDULED_FUTURE_EVENT semantics")
        if event_time <= cutoff and (
            not isinstance(event_semantics, str)
            or event_semantics not in {"OBSERVED_EVENT_TIME", "SCHEDULED_FUTURE_EVENT"}
        ):
            raise ValueError("past event_at requires explicit event-time semantics")
    for field in ("provider_timestamp", "published_at", "updated_at", "observed_at"):
        value = subfeature[field]
        if field == "observed_at" and value is None:
            raise ValueError("factor subfeature observed_at is required")
        if value is not None and _utc_timestamp(value, "subfeature " + field) > cutoff:
            raise ValueError("factor subfeature source timestamp is after decision cutoff")
    start, end = subfeature["window_start_at"], subfeature["window_end_at"]
    if (start is None) != (end is None):
        raise ValueError("factor subfeature measurement window requires both boundaries")
    if start is not None:
        start_time = _utc_timestamp(start, "subfeature window_start_at")
        end_time = _utc_timestamp(end, "subfeature window_end_at")
        if start_time > end_time or end_time > cutoff:
            raise ValueError("factor subfeature measurement window is invalid for decision cutoff")
    for left, right, label in (
        ("transformation_id", "transformation_version", "transformation"),
        ("baseline_id", "baseline_version", "baseline"),
    ):
        first, second = subfeature[left], subfeature[right]
        if (first is None) != (second is None):
            raise ValueError("factor subfeature " + label + " ID/version must be supplied together")
        if first is not None:
            _required_text(first, "subfeature " + left)
            _required_text(second, "subfeature " + right)
    if subfeature["normalized_value"] is not None:
        if subfeature["transformation_id"] is None:
            raise ValueError("normalized factor subfeature requires transformation provenance")
        if subfeature["baseline_id"] is None:
            raise ValueError("normalized factor subfeature requires baseline provenance")
    dependency = subfeature["source_dependency_group"]
    if dependency is not None:
        _required_text(dependency, "subfeature source_dependency_group")
    missing_reason = subfeature["missing_reason"]
    if availability == "AVAILABLE":
        if subfeature["raw_value"] is None or missing_reason is not None:
            raise ValueError("available factor subfeature must have raw value and no missing reason")
    else:
        if subfeature["raw_value"] is not None or subfeature["normalized_value"] is not None:
            raise ValueError("unavailable factor subfeature cannot contain measured values")
        _required_text(missing_reason, "subfeature missing_reason")


def validate_opportunity_input_snapshot(snapshot, *, expected_asset_id=None) -> int:
    """Validate legacy v1 or strict v2 opportunity snapshot; return schema version.

    Legacy snapshots deliberately retain their original structural validation and
    digest semantics. New v2 snapshots must carry complete, point-in-time factor
    provenance. This validator does not approve factor values or scoring policy.
    """
    if not isinstance(snapshot, dict) or set(snapshot) != {"policy", "inputs"}:
        raise ValueError("opportunity decision input snapshot is invalid")
    inputs = snapshot["inputs"]
    try:
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("opportunity decision input snapshot is not finite JSON") from None
    # Historical digest code required only the outer keys; preserve even unusual
    # legacy `inputs` JSON values rather than retroactively invalidating old IDs.
    if not isinstance(inputs, dict):
        return 1
    version = inputs.get("schema_version")
    if version is None:
        if "factor_assessments" in inputs:
            raise ValueError("versioned factor assessments require schema_version")
        return 1
    if isinstance(version, bool) or not isinstance(version, int) or version not in (1, 2):
        raise ValueError("opportunity decision snapshot schema version is unsupported")
    if version == 1:
        if "factor_assessments" in inputs:
            raise ValueError("legacy schema cannot contain versioned factor assessments")
        return 1
    asset_id = _required_text(inputs.get("asset_id"), "opportunity snapshot asset_id")
    if expected_asset_id is not None and asset_id != expected_asset_id:
        raise ValueError("opportunity snapshot asset identity does not match expected asset")
    cutoff = _utc_timestamp(inputs.get("decision_cutoff_at"), "decision_cutoff_at")
    assessments = inputs.get("factor_assessments")
    if not isinstance(assessments, list) or len(assessments) != len(FACTOR_NAMES):
        raise ValueError("version 2 snapshot requires all six factors exactly once")
    seen = set()
    factor_required = {
        "factor_name", "assessment_status", "value", "rubric_version",
        "feature_pipeline_version", "source_contract_version", "subfeatures",
        "reason_codes", "evaluated_at", "decision_cutoff_at",
    }
    for factor in assessments:
        if not isinstance(factor, dict) or set(factor) != factor_required:
            raise ValueError("factor assessment fields are incomplete or unknown")
        name = factor["factor_name"]
        if name not in FACTOR_NAMES or name in seen:
            raise ValueError("factor assessments must contain each of the six factors exactly once")
        seen.add(name)
        status = factor["assessment_status"]
        if not isinstance(status, str) or status not in _FACTOR_ASSESSMENT_STATUSES:
            raise ValueError("factor assessment status is not approved for use")
        for field in ("rubric_version", "feature_pipeline_version", "source_contract_version"):
            _required_text(factor[field], "factor " + field)
        _utc_timestamp(factor["evaluated_at"], "factor evaluated_at")
        factor_cutoff = _utc_timestamp(factor["decision_cutoff_at"], "factor decision_cutoff_at")
        if factor_cutoff != cutoff:
            raise ValueError("factor decision cutoff does not match snapshot cutoff")
        reason_codes = factor["reason_codes"]
        if (not isinstance(reason_codes, list)
                or any(not isinstance(code, str) or not code.strip() for code in reason_codes)
                or len(reason_codes) != len(set(reason_codes))):
            raise ValueError("factor assessment reason codes are invalid")
        value = factor["value"]
        if status == "READY":
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not 0 <= value <= 100):
                raise ValueError("READY factor assessment requires a finite value from 0 to 100")
        else:
            if value is not None:
                raise ValueError("non-READY factor assessment cannot contain a numeric value")
            if not reason_codes:
                raise ValueError("non-READY factor assessment requires reason codes")
        subfeatures = factor["subfeatures"]
        if not isinstance(subfeatures, list) or not subfeatures:
            raise ValueError("factor assessment requires at least one subfeature")
        feature_keys = [
            item.get("feature_key") if isinstance(item, dict) else None
            for item in subfeatures
        ]
        if any(not isinstance(key, str) or not key.strip() for key in feature_keys) or len(feature_keys) != len(set(feature_keys)):
            raise ValueError("factor assessment subfeature keys must be unique non-empty identifiers")
        for subfeature in subfeatures:
            _validate_v2_subfeature(subfeature, asset_id=asset_id, cutoff=cutoff)
        if status == "READY" and any(
            item["availability"] != "AVAILABLE" for item in subfeatures
        ):
            raise ValueError("READY factor assessment cannot depend on unavailable subfeatures")
    if seen != set(FACTOR_NAMES):
        raise ValueError("version 2 snapshot requires all six factors exactly once")
    return 2

def _decision_digest(
    *, state: str, score: Optional[float], reasons: tuple[str, ...],
    policy_version: str, input_snapshot_json: str,
) -> str:
    try:
        snapshot = json.loads(input_snapshot_json)
    except (TypeError, json.JSONDecodeError):
        raise ValueError("opportunity decision input snapshot is invalid") from None
    validate_opportunity_input_snapshot(snapshot)
    payload = {
        "state": state,
        "score": score,
        "reasons": list(reasons),
        "policy_version": policy_version,
        "policy": snapshot["policy"],
        "inputs": snapshot["inputs"],
    }
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode()
    ).hexdigest()


def verify_opportunity_decision_digest(
    *, decision_id: str, state: str, score, reasons,
    policy_version: str, input_snapshot,
) -> bool:
    """Recompute a stored decision digest from a decoded SQLite/PostgreSQL record."""
    if (not isinstance(decision_id, str) or len(decision_id) != _SHA256_LENGTH
            or any(char not in "0123456789abcdef" for char in decision_id)):
        raise ValueError("opportunity decision ID must be lowercase SHA-256")
    if state not in {"PROCEED", "RESEARCH_MORE", "DEFER", "REJECT"}:
        raise ValueError("opportunity decision state is invalid for digest verification")
    if not isinstance(policy_version, str) or not policy_version.strip():
        raise ValueError("opportunity decision policy version is invalid for digest verification")
    if not isinstance(reasons, (list, tuple)) or any(
        not isinstance(reason, str) or not reason.strip() for reason in reasons
    ):
        raise ValueError("opportunity decision reasons are invalid for digest verification")
    if isinstance(score, bool):
        raise ValueError("opportunity decision score is invalid for digest verification")
    if score is not None:
        try:
            score = float(score)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("opportunity decision score is invalid for digest verification") from None
        if not math.isfinite(score) or not 0 <= score <= 100:
            raise ValueError("opportunity decision score is invalid for digest verification")
    if isinstance(input_snapshot, dict):
        try:
            input_snapshot_json = json.dumps(
                input_snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False,
            )
        except (TypeError, ValueError):
            raise ValueError("opportunity decision stored snapshot is invalid") from None
    elif isinstance(input_snapshot, str):
        input_snapshot_json = input_snapshot
    else:
        raise ValueError("opportunity decision stored snapshot is invalid")
    expected = _decision_digest(
        state=state, score=score, reasons=tuple(reasons),
        policy_version=policy_version, input_snapshot_json=input_snapshot_json,
    )
    if expected != decision_id:
        raise ValueError("opportunity decision stored payload digest mismatch")
    return True


class OpportunityEvaluationEngine:
    def evaluate(
        self, *,
        eligibility_status: str,
        eligibility_verified_at: str,
        research_completeness: str,
        event_state: str,
        contradiction_count: int,
        unresolved_critical_count: int,
        unsupported_causal_framing: bool,
        duplicate_angle: bool,
        materially_new: bool,
        factors: Optional[Mapping[str, float]],
        policy: Optional[OpportunityPolicy],
        now: Optional[str] = None,
        eligibility_max_age_seconds: int = 300,
        asset_id: str = "",
    ) -> OpportunityDecision:
        reasons = []
        score = None
        for name, value in (
            ("contradiction_count", contradiction_count),
            ("unresolved_critical_count", unresolved_critical_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(name + " must be a non-negative integer")
        for name, value in (
            ("unsupported_causal_framing", unsupported_causal_framing),
            ("duplicate_angle", duplicate_angle),
            ("materially_new", materially_new),
        ):
            if not isinstance(value, bool):
                raise ValueError(name + " must be a boolean")
        if not isinstance(eligibility_status, str) or not isinstance(research_completeness, str) or not isinstance(event_state, str):
            raise ValueError("opportunity gate states must be strings")
        if not isinstance(asset_id, str) or len(asset_id) > 256:
            raise ValueError("opportunity asset_id must be a string of at most 256 characters")
        if (
            isinstance(eligibility_max_age_seconds, bool)
            or not isinstance(eligibility_max_age_seconds, int)
            or eligibility_max_age_seconds <= 0
        ):
            raise ValueError("eligibility age bound must be a positive integer")
        if policy is not None:
            policy.validate()
        current = _time(now or datetime.now(timezone.utc).isoformat())
        verified = _time(eligibility_verified_at)
        if eligibility_status != "ELIGIBLE":
            reasons.append("BINANCE_SPOT_ELIGIBILITY_NOT_VERIFIED")
            state = "REJECT"
        elif research_completeness == "REJECT" or event_state in {"WITHDRAWN", "DISPUTED"}:
            reasons.append("RESEARCH_OR_EVENT_REJECTED")
            state = "REJECT"
        elif (current - verified).total_seconds() < 0 or (
            (current - verified).total_seconds() > (
                policy.max_eligibility_age_seconds if policy is not None
                else eligibility_max_age_seconds
            )
        ):
            reasons.append("BINANCE_SPOT_ELIGIBILITY_STALE")
            state = "DEFER"
        elif research_completeness == "DEFER" or event_state == "STALE":
            reasons.append("RESEARCH_OR_EVENT_STALE")
            state = "DEFER"
        elif research_completeness != "READY":
            reasons.append("RESEARCH_PACKAGE_NOT_COMPLETE")
            state = "RESEARCH_MORE"
        elif event_state not in {"NO_EVENT", "CONFIRMED", "DEVELOPING"}:
            reasons.append("EVENT_STATE_NOT_CONFIRMED")
            state = "DEFER"
        elif contradiction_count > 0:
            reasons.append("CONTRADICTED_EVIDENCE_PRESENT")
            state = "REJECT"
        elif unresolved_critical_count > 0:
            reasons.append("CRITICAL_EVIDENCE_UNRESOLVED")
            state = "RESEARCH_MORE"
        elif unsupported_causal_framing:
            reasons.append("CAUSAL_FRAMING_EXCEEDS_EVIDENCE")
            state = "RESEARCH_MORE"
        elif duplicate_angle and not materially_new:
            reasons.append("DUPLICATE_ANGLE_WITHOUT_MATERIAL_UPDATE")
            state = "REJECT"
        elif policy is None:
            reasons.append("APPROVED_OPPORTUNITY_SCORING_POLICY_NOT_CONFIGURED")
            state = "DEFER"
        else:
            policy.validate()
            if not isinstance(factors, Mapping) or set(factors) != set(FACTOR_NAMES):
                reasons.append("OPPORTUNITY_FACTORS_INCOMPLETE")
                state = "DEFER"
            else:
                invalid = [
                    name for name, value in factors.items()
                    if isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not 0 <= value <= 100
                ]
                if invalid:
                    reasons.append("OPPORTUNITY_FACTOR_OUT_OF_RANGE:" + ",".join(sorted(invalid)))
                    state = "DEFER"
                else:
                    score = round(sum(float(policy.weights[name]) * float(factors[name]) for name in FACTOR_NAMES), 6)
                    if score >= policy.proceed_threshold:
                        state = "PROCEED"
                        reasons.append("OPPORTUNITY_SCORE_ABOVE_PROCEED_THRESHOLD")
                    elif score >= policy.defer_threshold:
                        state = "DEFER"
                        reasons.append("OPPORTUNITY_SCORE_IN_DEFER_RANGE")
                    else:
                        state = "REJECT"
                        reasons.append("OPPORTUNITY_SCORE_BELOW_DEFER_THRESHOLD")
        policy_version = policy.policy_version if policy else "UNCONFIGURED"
        factor_snapshot = {}
        factor_keys = []
        if isinstance(factors, Mapping):
            factor_keys = sorted(str(key) for key in factors.keys())
            for name in FACTOR_NAMES:
                value = factors.get(name)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    factor_snapshot[name] = {"invalid_type": type(value).__name__}
                else:
                    factor_snapshot[name] = float(value)
        policy_snapshot = None
        if policy is not None:
            policy_snapshot = {
                "policy_version": policy.policy_version,
                "weights": {name: float(policy.weights[name]) for name in FACTOR_NAMES},
                "proceed_threshold": float(policy.proceed_threshold),
                "defer_threshold": float(policy.defer_threshold),
                "max_eligibility_age_seconds": policy.max_eligibility_age_seconds,
            }
        input_snapshot_json = json.dumps(
            {
                "policy": policy_snapshot,
                "inputs": {
                    "asset_id": asset_id,
                    "eligibility_status": eligibility_status,
                    "eligibility_verified_at": verified.isoformat(),
                    "effective_eligibility_max_age_seconds": (
                        policy.max_eligibility_age_seconds if policy is not None
                        else eligibility_max_age_seconds
                    ),
                    "research_completeness": research_completeness,
                    "event_state": event_state,
                    "contradiction_count": contradiction_count,
                    "unresolved_critical_count": unresolved_critical_count,
                    "unsupported_causal_framing": unsupported_causal_framing,
                    "duplicate_angle": duplicate_angle,
                    "materially_new": materially_new,
                    "factor_keys": factor_keys,
                    "factors": factor_snapshot,
                },
            },
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
        decision_id = _decision_digest(
            state=state, score=score, reasons=tuple(reasons),
            policy_version=policy_version,
            input_snapshot_json=input_snapshot_json,
        )
        return OpportunityDecision(
            state=state, score=score, reasons=tuple(reasons),
            policy_version=policy_version, decision_id=decision_id,
            input_snapshot_json=input_snapshot_json,
        )


class OpportunityDecisionStore:
    """Append-only opportunity decisions linked to exact research package IDs."""

    def __init__(self, connection):
        import sqlite3
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("opportunity decision store requires SQLite connection")
        self.connection = connection
        self.connection.execute("""
        CREATE TABLE IF NOT EXISTS opportunity_decisions (
            decision_id TEXT PRIMARY KEY,
            research_package_id TEXT NOT NULL,
            state TEXT NOT NULL,
            score REAL,
            reasons_json TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            input_snapshot_json TEXT NOT NULL DEFAULT '{}'
        )
        """)
        columns = {
            row[1] for row in self.connection.execute(
                "PRAGMA table_info(opportunity_decisions)"
            ).fetchall()
        }
        if "input_snapshot_json" not in columns:
            self.connection.execute(
                "ALTER TABLE opportunity_decisions ADD COLUMN input_snapshot_json TEXT NOT NULL DEFAULT '{}'"
            )
        self.connection.commit()

    def save(self, research_package_id: str, decision: OpportunityDecision) -> str:
        if (
            not isinstance(research_package_id, str) or not research_package_id.strip()
            or not isinstance(decision, OpportunityDecision)
            or not isinstance(decision.decision_id, str)
            or len(decision.decision_id) != 64
            or any(char not in "0123456789abcdef" for char in decision.decision_id)
        ):
            raise ValueError("opportunity decision requires valid research package provenance and decision ID")
        if (
            decision.state not in {"PROCEED", "RESEARCH_MORE", "DEFER", "REJECT"}
            or (
                decision.score is not None
                and (
                    isinstance(decision.score, bool)
                    or not isinstance(decision.score, (int, float))
                    or not math.isfinite(decision.score)
                    or not 0 <= decision.score <= 100
                )
            )
            or not isinstance(decision.policy_version, str)
            or not decision.policy_version.strip()
            or not isinstance(decision.reasons, tuple)
            or any(not isinstance(reason, str) or not reason.strip() for reason in decision.reasons)
        ):
            raise ValueError("opportunity decision payload is invalid")
        try:
            snapshot = json.loads(decision.input_snapshot_json)
            if not isinstance(snapshot, dict) or set(snapshot) != {"policy", "inputs"}:
                raise ValueError
            expected_id = _decision_digest(
                state=decision.state, score=decision.score,
                reasons=decision.reasons, policy_version=decision.policy_version,
                input_snapshot_json=decision.input_snapshot_json,
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            raise ValueError("opportunity decision input snapshot is invalid") from None
        if expected_id != decision.decision_id:
            raise ValueError("opportunity decision ID does not match its immutable input snapshot")
        reasons_json = json.dumps(decision.reasons, separators=(",", ":"))
        with self.connection:
            existing = self.connection.execute(
                "SELECT research_package_id, state, score, reasons_json, policy_version, input_snapshot_json "
                "FROM opportunity_decisions WHERE decision_id=?",
                (decision.decision_id,),
            ).fetchone()
            if existing is not None:
                if existing[0] != research_package_id:
                    raise ValueError("decision ID is already bound to a different research package")
                if (
                    existing[1] != decision.state
                    or existing[2] != decision.score
                    or existing[3] != reasons_json
                    or existing[4] != decision.policy_version
                    or existing[5] != decision.input_snapshot_json
                ):
                    raise ValueError("opportunity decision ID collision with different immutable payload")
                return decision.decision_id
            self.connection.execute(
                "INSERT INTO opportunity_decisions "
                "(decision_id, research_package_id, state, score, reasons_json, "
                "policy_version, created_at, input_snapshot_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (decision.decision_id, research_package_id, decision.state,
                 decision.score, reasons_json, decision.policy_version,
                 datetime.now(timezone.utc).isoformat(), decision.input_snapshot_json),
            )
        return decision.decision_id

[executed on device: localhost (bd830869-fbae-4825-ae7b-5044d6161090)]
