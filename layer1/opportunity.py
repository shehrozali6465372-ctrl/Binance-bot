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
        if not self.policy_version.strip():
            raise ValueError("opportunity policy version is required")
        if set(self.weights) != set(FACTOR_NAMES):
            raise ValueError("opportunity policy must define every named factor exactly once")
        values = list(self.weights.values())
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("opportunity weights must be finite non-negative numbers")
        if not math.isclose(sum(values), 1.0, rel_tol=0, abs_tol=1e-9):
            raise ValueError("opportunity weights must sum to 1.0")
        if not 0 <= self.defer_threshold < self.proceed_threshold <= 100:
            raise ValueError("opportunity thresholds must satisfy 0 <= defer < proceed <= 100")
        if isinstance(self.max_eligibility_age_seconds, bool) or not isinstance(self.max_eligibility_age_seconds, int) or self.max_eligibility_age_seconds <= 0:
            raise ValueError("eligibility age bound must be a positive integer")


@dataclass(frozen=True)
class OpportunityDecision:
    state: str
    score: Optional[float]
    reasons: tuple[str, ...]
    policy_version: str
    decision_id: str


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
        payload = {
            "state": state, "score": score, "reasons": reasons,
            "policy_version": policy_version,
            "eligibility_status": eligibility_status,
            "research_completeness": research_completeness,
            "event_state": event_state,
        }
        decision_id = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return OpportunityDecision(
            state=state, score=score, reasons=tuple(reasons),
            policy_version=policy_version, decision_id=decision_id,
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
            created_at TEXT NOT NULL
        )
        """)
        self.connection.commit()

    def save(self, research_package_id: str, decision: OpportunityDecision) -> str:
        if not research_package_id or not isinstance(decision, OpportunityDecision):
            raise ValueError("opportunity decision requires research package provenance")
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO opportunity_decisions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (decision.decision_id, research_package_id, decision.state,
                 decision.score, json.dumps(decision.reasons, separators=(",", ":")),
                 decision.policy_version, datetime.now(timezone.utc).isoformat()),
            )
        return decision.decision_id
