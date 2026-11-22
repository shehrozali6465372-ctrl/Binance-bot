"""Evidence-backed claim verification with explicit provenance and fail-closed states.

This module is deterministic: LLM confidence is neither accepted nor used as evidence.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import urlparse

from layer1.foundation import AnnouncementEvidence, MarketObservation, TrendSignal
from layer1.onchain import OnChainObservation, OnChainValidationResult


CLAIM_STATES = {"VERIFIED", "CORROBORATED", "UNVERIFIED", "CONTRADICTED", "STALE"}
CLAIM_TYPES = {
    "CONFIRMED_FACT", "SOURCE_ASSERTION", "ESTIMATE",
    "ANALYST_INTERPRETATION", "HYPOTHESIS", "UNCLASSIFIED",
}
IMPACT_LEVELS = {"LOW", "MEDIUM", "HIGH"}
SOURCE_KINDS = {"PRIMARY", "SECONDARY", "MARKET", "ONCHAIN", "SOCIAL"}
SOURCE_STATUSES = {"ACCEPTED", "UNVERIFIED", "REJECTED", "STALE"}
_CAUSAL_RELATION_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\bbecause\b", r"\bdue\s+to\b", r"\bcaus(?:ed|es|ing)\b",
    r"\bdriven\s+by\b", r"\btriggered\s+by\b", r"\battributed\s+to\b",
    r"\bcontributed\s+to\b", r"\bboosted\s+by\b", r"\bfueled\s+by\b",
    r"\bthanks\s+to\b", r"\bled\s+to\b", r"\bleading\s+to\b", r"\bresulted\s+in\b",
    r"\bas\s+a\s+result\b", r"\bon\s+account\s+of\b",
    r"\btherefore\b", r"\bconsequently\b",
))
_COMPOUND_TEMPORAL_ACTION_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\b(?:before|after)\s+[a-z]+ing\b",
))
_COMPOUND_PARTICIPIAL_ACTION_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    # A comma followed by a second action/interpretive predicate is not covered
    # by the sentence splitter's finite-clause grammar. One typed field must
    # never certify both propositions. Keep this list explicit to avoid treating
    # non-predicate participles such as "including" as claims.
    r",\s*(?:(?:then|later|subsequently)\s+)?(?:rising|falling|increasing|decreasing|surging|dropping|gaining|losing|moving|trading|closing|opening|launching|listing|delisting|reaching|recording|reporting|announcing|confirming|reflecting|indicating|suggesting|triggering|causing|resulting|leading)\b",
))


def _timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("timestamp must be valid ISO-8601") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_claim_registry_payload(
    verification_id: str, payload: Mapping[str, Any], *, ensure_ascii: bool = True,
) -> bool:
    """Verify a persisted ClaimRegistry snapshot against its immutable digest.

    SQLite's historical writer uses json.dumps' ensure_ascii=True default;
    PostgreSQL's writer explicitly uses ensure_ascii=False. Callers must retain
    the serializer mode used by the corresponding store to preserve old IDs.
    """
    if (not isinstance(verification_id, str) or len(verification_id) != 64
            or any(char not in "0123456789abcdef" for char in verification_id)):
        raise ValueError("claim registry verification ID must be lowercase SHA-256")
    if not isinstance(payload, Mapping):
        raise ValueError("claim registry stored payload must be an object")
    try:
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=ensure_ascii, allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError):
        raise ValueError("claim registry stored payload is not finite JSON") from None
    if _digest(canonical) != verification_id:
        raise ValueError("claim registry stored payload digest mismatch")
    return True


def _scalar(value: Any) -> bool:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return not isinstance(value, bool) and math.isfinite(value)
    return isinstance(value, str)


def _value_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float, Decimal)) and isinstance(right, (int, float, Decimal)):
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except (InvalidOperation, ValueError):
            return False
    return left == right


def _same_optional_text(left: Optional[str], right: Optional[str]) -> bool:
    if left is None or right is None:
        return left is right
    return left.strip().casefold() == right.strip().casefold()


@dataclass(frozen=True)
class EvidenceRecord:
    source_id: str
    source_family: str
    source_kind: str
    publisher: str
    subject: str
    claim_key: str
    value: Any
    published_at: str
    observed_at: str
    asset_id: Optional[str] = None
    mapping_id: Optional[str] = None
    unit: Optional[str] = None
    timeframe: Optional[str] = None
    event_at: Optional[str] = None
    updated_at: Optional[str] = None
    source_url: Optional[str] = None
    content_hash: str = ""
    lineage_id: str = ""
    is_primary: bool = False
    source_status: str = "ACCEPTED"
    status_value: Optional[str] = None

    @property
    def evidence_id(self) -> str:
        payload = {
            "source_id": self.source_id, "source_family": self.source_family,
            "claim_key": self.claim_key, "subject": self.subject, "asset_id": self.asset_id,
            "mapping_id": self.mapping_id, "value": self.value, "unit": self.unit, "timeframe": self.timeframe,
            "event_at": self.event_at, "status_value": self.status_value,
            "published_at": self.published_at, "updated_at": self.updated_at,
            "observed_at": self.observed_at, "content_hash": self.content_hash,
            "lineage_id": self.lineage_id,
        }
        return _digest(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False))

    def validate(self) -> None:
        required = (
            self.source_id, self.source_family, self.source_kind, self.publisher,
            self.subject, self.claim_key, self.published_at, self.observed_at,
        )
        if any(not isinstance(value, str) or not value.strip() for value in required):
            raise ValueError("evidence identity, source and timestamps are required")
        if self.source_kind not in SOURCE_KINDS or self.source_status not in SOURCE_STATUSES:
            raise ValueError("evidence source kind/status is invalid")
        if not _scalar(self.value):
            raise ValueError("evidence value must be a finite JSON scalar")
        if not isinstance(self.is_primary, bool):
            raise ValueError("evidence primary-source flag must be boolean")
        for name in ("asset_id", "mapping_id", "unit", "timeframe", "status_value", "content_hash", "lineage_id"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"evidence {name} must be a string or unavailable")
        if self.source_url is not None and not isinstance(self.source_url, str):
            raise ValueError("evidence source URL must be a string or unavailable")
        if self.content_hash and not re.fullmatch(r"[0-9a-f]{64}", self.content_hash):
            raise ValueError("evidence content_hash must be a lowercase SHA-256 digest")
        _timestamp(self.published_at)
        _timestamp(self.observed_at)
        if self.updated_at:
            updated = _timestamp(self.updated_at)
            if updated < _timestamp(self.published_at):
                raise ValueError("evidence updated_at cannot precede published_at")
        if self.event_at:
            _timestamp(self.event_at)
        if self.source_url:
            parsed = urlparse(self.source_url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("evidence source URL must be attributable HTTPS")


@dataclass(frozen=True)
class Claim:
    text: str
    subject: str
    claim_key: str
    value: Any
    observed_at: str
    evidence_ids: tuple[str, ...] = ()
    asset_id: Optional[str] = None
    mapping_id: Optional[str] = None
    unit: Optional[str] = None
    timeframe: Optional[str] = None
    event_at: Optional[str] = None
    expected_status: Optional[str] = None
    claim_type: str = "CONFIRMED_FACT"
    impact: str = "MEDIUM"
    max_age_seconds: Optional[int] = None

    @property
    def claim_id(self) -> str:
        payload = {
            "text": self.text, "subject": self.subject, "asset_id": self.asset_id,
            "mapping_id": self.mapping_id, "claim_key": self.claim_key, "value": self.value, "unit": self.unit,
            "timeframe": self.timeframe, "event_at": self.event_at,
            "expected_status": self.expected_status, "observed_at": self.observed_at,
            "claim_type": self.claim_type, "impact": self.impact,
            "evidence_ids": sorted(self.evidence_ids), "max_age_seconds": self.max_age_seconds,
        }
        return _digest(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False))

    def validate(self) -> None:
        if any(not isinstance(value, str) or not value.strip()
               for value in (self.text, self.subject, self.claim_key, self.observed_at)):
            raise ValueError("claim text, subject, key and observation timestamp are required")
        if self.claim_type not in CLAIM_TYPES or self.impact not in IMPACT_LEVELS:
            raise ValueError("claim type or impact level is invalid")
        if not _scalar(self.value):
            raise ValueError("claim value must be a finite JSON scalar")
        if self.asset_id is not None and (
            not isinstance(self.asset_id, str) or not self.asset_id.strip()
        ):
            raise ValueError("claim asset identity must be a string or unavailable")
        for name in ("mapping_id", "unit", "timeframe", "event_at", "expected_status"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"claim {name} must be a string or unavailable")
        _timestamp(self.observed_at)
        if self.event_at:
            _timestamp(self.event_at)
        if (not isinstance(self.evidence_ids, tuple)
                or any(not isinstance(item, str) or not item.strip() for item in self.evidence_ids)
                or len(set(self.evidence_ids)) != len(self.evidence_ids)):
            raise ValueError("claim evidence IDs must be a unique tuple of non-empty strings")
        if self.max_age_seconds is not None and (
            isinstance(self.max_age_seconds, bool)
            or not isinstance(self.max_age_seconds, int) or self.max_age_seconds <= 0
        ):
            raise ValueError("claim max_age_seconds must be a positive integer or unavailable")


@dataclass(frozen=True)
class ClaimVerificationResult:
    claim_id: str
    state: str
    evidence_ids: tuple[str, ...]
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...]
    independent_source_count: int
    source_lineage: Mapping[str, str]
    issues: tuple[str, ...]


@dataclass(frozen=True)
class ClaimRegistry:
    claims: tuple[Claim, ...]
    evidence_records: tuple[EvidenceRecord, ...]
    results: tuple[ClaimVerificationResult, ...]
    unresolved_issues: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": [asdict(claim) | {"claim_id": claim.claim_id} for claim in self.claims],
            "evidence_records": [
                asdict(record) | {"evidence_id": record.evidence_id}
                for record in self.evidence_records
            ],
            "results": [asdict(result) for result in self.results],
            "unresolved_issues": [dict(issue) for issue in self.unresolved_issues],
        }


class EvidenceVerificationEngine:
    """Deterministic evidence linker and verifier; it never consumes model confidence."""

    @staticmethod
    def scope_registry_to_asset(registry: ClaimRegistry, asset_id: str) -> ClaimRegistry:
        """Return only one canonical asset's claims/evidence before drafting.

        Evidence from other assets is excluded even if a claim references it;
        that claim then remains unresolved rather than leaking cross-asset facts.
        """
        if not isinstance(registry, ClaimRegistry):
            raise TypeError("asset scoping requires a ClaimRegistry")
        if not isinstance(asset_id, str) or not re.fullmatch(r"coingecko:[a-z0-9][a-z0-9-]{1,99}", asset_id):
            raise ValueError("asset scoping requires a canonical CoinGecko asset ID")
        claims = tuple(
            claim for claim in registry.claims
            if claim.asset_id == asset_id or claim.subject == asset_id
        )
        claim_ids = {claim.claim_id for claim in claims}
        evidence = tuple(
            item for item in registry.evidence_records
            if item.asset_id == asset_id or item.subject == asset_id
        )
        results = tuple(
            result for result in registry.results if result.claim_id in claim_ids
        )
        unresolved = tuple(
            issue for issue in registry.unresolved_issues
            if issue.get("claim_id") in claim_ids
        )
        return ClaimRegistry(
            claims=claims, evidence_records=evidence,
            results=results, unresolved_issues=unresolved,
        )

    def verify(
        self,
        claims: Sequence[Claim],
        evidence_records: Sequence[EvidenceRecord],
    ) -> ClaimRegistry:
        evidence_by_id: dict[str, EvidenceRecord] = {}
        for evidence in evidence_records:
            evidence.validate()
            existing = evidence_by_id.get(evidence.evidence_id)
            if existing is not None and existing != evidence:
                raise ValueError("conflicting evidence payloads share one evidence ID")
            evidence_by_id[evidence.evidence_id] = evidence

        claim_ids: set[str] = set()
        results = []
        unresolved = []
        for claim in claims:
            claim.validate()
            if claim.claim_id in claim_ids:
                raise ValueError("duplicate claim ID in one registry")
            claim_ids.add(claim.claim_id)
            result = self._verify_one(claim, evidence_by_id)
            results.append(result)
            for issue in result.issues:
                unresolved.append({
                    "claim_id": result.claim_id, "state": result.state,
                    "issue": issue, "evidence_ids": list(result.evidence_ids),
                })

        return ClaimRegistry(
            claims=tuple(claims),
            evidence_records=tuple(sorted(evidence_by_id.values(), key=lambda item: item.evidence_id)),
            results=tuple(results), unresolved_issues=tuple(unresolved),
        )

    @staticmethod
    def _claim_text_mismatch(claim: Claim) -> Optional[str]:
        """Bind supported rendered claim text to its structured evidence fields.

        This is a bounded deterministic consistency check, not general semantic NLP.
        Unsupported source-assertion formats fail closed; arbitrary prose is never
        promoted to a source assertion merely because its structured fields match.
        """
        canonical_source_text = (
            f"Source assertion: {claim.subject} {claim.claim_key} = "
            f"{json.dumps(claim.value, ensure_ascii=False)}"
        )
        if claim.claim_type == "SOURCE_ASSERTION" and claim.text == canonical_source_text:
            return None
        if claim.claim_key in {"announcement.title", "announcement.body"}:
            # Exact Detail/source-payload binding is enforced with linked records
            # in _verify_one, where the source lineage is available.
            return None

        if claim.claim_key.startswith("market."):
            try:
                expected = Decimal(str(claim.value))
            except (InvalidOperation, TypeError, ValueError):
                return "VALUE_NOT_NUMERIC"
            if not expected.is_finite():
                return "VALUE_NOT_NUMERIC"

            metric_patterns = {
                "market.price": r"\bprice\b",
                "market.price_change": r"\bprice\b",
                "market.change_24h": r"\b(?:24h|24[- ]hour|daily)?\s*(?:change|return|performance)\b",
                "market.volume_24h": r"\bvolume\b",
                "market.market_cap": r"\bmarket\s+cap(?:italization)?\b",
            }
            metric_pattern = metric_patterns.get(claim.claim_key)
            if metric_pattern is None or not re.search(metric_pattern, claim.text, re.IGNORECASE):
                return "METRIC"
            if re.search(
                r"\b(?:not|never|no\s+longer|isn't|wasn't|aren't|weren't|doesn't|"
                r"didn't|don't|cannot|can't|won't|wouldn't|hasn't|haven't|hadn't)\b",
                claim.text, re.IGNORECASE,
            ):
                return "NEGATED"
            if re.search(
                r"\b(?:may|might|could|would|possibly|perhaps|potentially|likely|"
                r"unlikely|expected\s+to|projected\s+to|forecast\s+to|reportedly|"
                r"allegedly|apparently|seems\s+to|appears\s+to)\b",
                claim.text, re.IGNORECASE,
            ):
                return "MODAL_OR_UNCERTAIN"

            text = re.sub(
                r"\b\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+-]+Z?)?\b",
                " ", claim.text,
            )
            number_pattern = re.compile(
                r"(?<![A-Za-z0-9])(?P<symbol>[$€£])?\s*"
                r"(?P<number>[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
                r"(?P<percent>\s*%)?(?![A-Za-z0-9])"
            )
            matches = list(number_pattern.finditer(text))
            if not matches:
                return "VALUE_MISSING"

            precision = {
                "market.price": 6,
                "market.price_change": 1,
                "market.change_24h": 1,
                "market.volume_24h": 0,
                "market.market_cap": 0,
            }[claim.claim_key]
            try:
                expected_display = Decimal(format(float(expected), f".{precision}f"))
            except (OverflowError, ValueError):
                return "VALUE_NOT_NUMERIC"

            expected_unit = (claim.unit or "").strip().casefold()
            direction = None
            if claim.claim_key in {"market.price_change", "market.change_24h"}:
                positive_direction = re.search(
                    r"\b(?:up|rise|rises|rose|rising|increase|increases|increased|increasing|"
                    r"gain|gains|gained|gaining|higher|grew|growth|positive|surge|surged|"
                    r"surging|climb|climbed|rally|rallied|advance|advanced)\b",
                    claim.text, re.IGNORECASE,
                )
                negative_direction = re.search(
                    r"\b(?:down|fall|falls|fell|falling|decrease|decreases|decreased|"
                    r"decreasing|loss|lost|lower|drop|drops|dropped|dropping|decline|"
                    r"declines|declined|declining|negative|sink|sinks|sank|slip|slips|"
                    r"slipped|slide|slides|slid|dipped|dip|weakened|weakening)\b",
                    claim.text, re.IGNORECASE,
                )
                neutral_direction = re.search(
                    r"\b(?:flat|unchanged|no\s+change|remained\s+stable|stayed\s+stable)\b",
                    claim.text, re.IGNORECASE,
                )
                if neutral_direction and (positive_direction or negative_direction):
                    return "DIRECTION_AMBIGUOUS"
                if positive_direction:
                    direction = 1
                elif negative_direction:
                    direction = -1
                elif neutral_direction:
                    direction = 0
                if direction == 0 and expected != 0:
                    return "DIRECTION"
                if direction in {-1, 1} and (
                    expected == 0 or (1 if expected > 0 else -1) != direction
                ):
                    return "DIRECTION"

            for match in matches:
                raw_number = match.group("number").replace(",", "")
                try:
                    actual = Decimal(raw_number)
                except InvalidOperation:
                    return "VALUE_NOT_NUMERIC"
                if direction is not None:
                    explicit_sign = raw_number.startswith(("+", "-"))
                    if explicit_sign and (1 if actual > 0 else -1 if actual < 0 else 0) != direction:
                        return "DIRECTION"
                    if not explicit_sign and direction in {-1, 1}:
                        actual = abs(actual) * direction
                if actual != expected_display:
                    return "VALUE"
                explicit_unit = "percent" if match.group("percent") else ""
                suffix = re.match(r"\s*([A-Z][A-Z0-9]{1,9})\b", text[match.end():])
                if suffix:
                    explicit_unit = suffix.group(1).casefold()
                if match.group("symbol") and not explicit_unit:
                    explicit_unit = "currency_symbol"
                if explicit_unit:
                    if explicit_unit == "currency_symbol":
                        if expected_unit not in {"usd", "usdt"}:
                            return "UNIT"
                    elif explicit_unit == "percent":
                        if expected_unit not in {"percent", "%", "pct"}:
                            return "UNIT"
                    elif explicit_unit != expected_unit:
                        return "UNIT"
            return None

        if claim.claim_type not in {"SOURCE_ASSERTION", "CONFIRMED_FACT"}:
            return None
        if claim.claim_type == "CONFIRMED_FACT" and not claim.evidence_ids:
            return None

        expected_texts = None
        if claim.claim_key == "announcement.event_type" and isinstance(claim.value, str):
            expected_texts = {
                ("Type: " + claim.value).casefold(),
                ("Binance announced a " + claim.value).casefold(),
            }
        elif claim.claim_key == "announcement.freshness" and claim.value == "FRESH":
            expected_texts = {"Age: Just announced by Binance (FRESH)".casefold()}
        elif claim.claim_key == "binance_spot.eligible" and type(claim.value) is bool:
            expected_texts = {
                ("Binance Spot: YES" if claim.value else "Binance Spot: NO").casefold()
            }
        elif claim.claim_key == "publication.last_posted":
            if claim.value == "NO_RECORD_IN_LATEST_200":
                expected_texts = {"Last posted: NO RECORD IN LATEST 200 LOCAL POSTS".casefold()}
            elif type(claim.value) is int and claim.unit == "hours":
                expected_texts = {f"Last posted: {claim.value} hours ago".casefold()}
        elif claim.claim_key.startswith("trend.topic:") and isinstance(claim.value, str):
            if claim.claim_key == "trend.topic:" + _digest(claim.value.casefold())[:16]:
                expected_texts = {("Trend topic: " + claim.value).casefold()}
        elif claim.claim_key == "onchain.transfer_summary" and isinstance(claim.value, str):
            if re.fullmatch(r"[0-9a-fA-F]{64}", claim.value):
                expected_texts = {("On-chain transfer summary ID: " + claim.value).casefold()}

        if expected_texts is None:
            return "UNSUPPORTED_TEXT_FORMAT"
        return None if claim.text.casefold() in expected_texts else "TEXT"

    def _verify_one(
        self,
        claim: Claim,
        evidence_by_id: Mapping[str, EvidenceRecord],
    ) -> ClaimVerificationResult:
        issues: set[str] = set()
        claim_text_mismatch = self._claim_text_mismatch(claim)
        if claim_text_mismatch:
            issues.add("CLAIM_TEXT_STRUCTURED_VALUE_MISMATCH:" + claim_text_mismatch)
        linked = []
        missing = []
        for evidence_id in claim.evidence_ids:
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                missing.append(evidence_id)
            else:
                linked.append(evidence)
        if not claim.evidence_ids:
            issues.add("NO_EVIDENCE_LINKED")
        if missing:
            issues.add("MISSING_EVIDENCE_ID")

        # One typed field/value cannot verify a causal relation or several
        # independent propositions. The narrow exception is an explicitly
        # attributed announcement title/body whose exact source payload is linked.
        direct_announcement_assertion = (
            claim.claim_type == "SOURCE_ASSERTION"
            and claim.claim_key in {"announcement.title", "announcement.body"}
            and bool(linked)
            and all(
                evidence.claim_key == claim.claim_key
                and evidence.subject == claim.subject
                and evidence.asset_id == claim.asset_id
                and evidence.value == claim.value
                and evidence.source_status == "ACCEPTED"
                for evidence in linked
            )
        )
        if direct_announcement_assertion:
            exemplar = linked[0]
            expected_source_text = (
                f"Source assertion: {exemplar.subject} {exemplar.claim_key} = "
                f"{json.dumps(exemplar.value, ensure_ascii=False)}"
            )
            exact_detail_text = (
                claim.text.casefold() == ("Detail: " + str(exemplar.value)).casefold()
            )
            direct_announcement_assertion = (
                claim.text == expected_source_text or exact_detail_text
            )
        if (claim.claim_key in {"announcement.title", "announcement.body"}
                and not direct_announcement_assertion):
            issues.add("ANNOUNCEMENT_TEXT_EVIDENCE_MISMATCH")
        if (any(pattern.search(claim.text) for pattern in _CAUSAL_RELATION_PATTERNS)
                and not direct_announcement_assertion):
            issues.add("CAUSAL_RELATION_REQUIRES_DIRECT_SOURCE_ASSERTION")
        has_multiple_propositions = (
            len(split_atomic_claims(claim.text)) > 1
            or any(pattern.search(claim.text) for pattern in (
                *_COMPOUND_TEMPORAL_ACTION_PATTERNS,
                *_COMPOUND_PARTICIPIAL_ACTION_PATTERNS,
                *_COMPOUND_RELATIVE_CLAUSE_PATTERNS,
            ))
        )
        if has_multiple_propositions and not direct_announcement_assertion:
            issues.add("COMPOUND_CLAIM_REQUIRES_ATOMIC_EVIDENCE")

        event_scope = claim.event_at
        if event_scope is None and linked:
            event_scope = linked[0].event_at
        related = [
            evidence for evidence in evidence_by_id.values()
            if claim.evidence_ids
            and evidence.claim_key == claim.claim_key
            and evidence.subject == claim.subject
            and evidence.asset_id == claim.asset_id
            and evidence.mapping_id == claim.mapping_id
            and _same_optional_text(evidence.unit, claim.unit)
            and _same_optional_text(evidence.timeframe, claim.timeframe)
            and evidence.event_at == event_scope
            and evidence.source_status == "ACCEPTED"
            and self._temporal_state(claim, evidence) == (None, False)
        ]
        contradictions = [
            evidence for evidence in related
            if (not _value_equal(evidence.value, claim.value)
                or not _same_optional_text(evidence.unit, claim.unit)
                or (claim.expected_status is not None and evidence.status_value != claim.expected_status))
        ]

        supporting = []
        stale_ids = []
        temporal_or_field_mismatch = False
        for evidence in linked:
            temporal_issue, is_stale = self._temporal_state(claim, evidence)
            if temporal_issue:
                issues.add(temporal_issue)
            if is_stale:
                stale_ids.append(evidence.evidence_id)
                continue
            if temporal_issue:
                temporal_or_field_mismatch = True
                continue
            mismatch = self._field_mismatch(claim, evidence)
            if mismatch:
                temporal_or_field_mismatch = True
                issues.add("EVIDENCE_FIELD_MISMATCH:" + mismatch)
                if (evidence.claim_key == claim.claim_key and evidence.subject == claim.subject
                        and evidence.asset_id == claim.asset_id
                        and _same_optional_text(evidence.unit, claim.unit)
                        and _same_optional_text(evidence.timeframe, claim.timeframe)
                        and evidence.event_at == event_scope
                        and (not _value_equal(evidence.value, claim.value)
                             or (claim.expected_status is not None and evidence.status_value != claim.expected_status))
                        and evidence.source_status == "ACCEPTED"):
                    contradictions.append(evidence)
                continue
            if evidence.source_status != "ACCEPTED":
                issues.add("EVIDENCE_SOURCE_NOT_ACCEPTED:" + evidence.source_status)
                continue
            supporting.append(evidence)

        if claim.impact == "HIGH" and claim.max_age_seconds is None:
            issues.add("HIGH_IMPACT_FRESHNESS_POLICY_REQUIRED")
        if claim.claim_type in {"ESTIMATE", "ANALYST_INTERPRETATION", "HYPOTHESIS"}:
            issues.add("NON_FACTUAL_CLAIM_TYPE")
        if claim.claim_type == "UNCLASSIFIED":
            issues.add("CLAIM_TYPE_UNCLASSIFIED")

        supporting_by_id = {item.evidence_id: item for item in supporting}
        for evidence in related:
            if evidence.evidence_id not in supporting_by_id and self._field_mismatch(claim, evidence) is None:
                supporting_by_id[evidence.evidence_id] = evidence
        supporting = list(supporting_by_id.values())

        contradictions_by_id = {item.evidence_id: item for item in contradictions}
        if contradictions_by_id:
            issues.add("CONTRADICTORY_EVIDENCE")
        independent_count = self._independent_source_count(supporting)
        primary_available = any(item.is_primary for item in supporting)
        source_lineage = {
            item.evidence_id: self._lineage_key(item)
            for item in supporting + list(contradictions_by_id.values())
        }
        result_evidence_ids = tuple(sorted(
            set(claim.evidence_ids) | set(supporting_by_id) | set(contradictions_by_id)
        ))
        supporting_ids = tuple(sorted(supporting_by_id))
        contradicting_ids = tuple(sorted(contradictions_by_id))

        if contradictions_by_id:
            state = "CONTRADICTED"
        elif stale_ids and not supporting:
            state = "STALE"
        elif (not claim.evidence_ids or not supporting or missing or temporal_or_field_mismatch
              or claim_text_mismatch is not None
              or "ANNOUNCEMENT_TEXT_EVIDENCE_MISMATCH" in issues
              or "HIGH_IMPACT_FRESHNESS_POLICY_REQUIRED" in issues
              or "NON_FACTUAL_CLAIM_TYPE" in issues
              or "CLAIM_TYPE_UNCLASSIFIED" in issues
              or "CAUSAL_RELATION_REQUIRES_DIRECT_SOURCE_ASSERTION" in issues
              or "COMPOUND_CLAIM_REQUIRES_ATOMIC_EVIDENCE" in issues):
            state = "UNVERIFIED"
        elif claim.impact == "HIGH" and (not primary_available or independent_count < 2):
            issues.add("HIGH_IMPACT_EVIDENCE_THRESHOLD_NOT_MET")
            state = "UNVERIFIED"
        elif independent_count >= 2:
            state = "CORROBORATED"
        elif primary_available:
            state = "VERIFIED"
        elif claim.claim_type == "SOURCE_ASSERTION" and supporting:
            # One attributable secondary source verifies only that the source made this assertion;
            # the renderer and model prompt must preserve that attribution.
            state = "VERIFIED"
        else:
            state = "UNVERIFIED"
            issues.add("PRIMARY_OR_INDEPENDENT_EVIDENCE_REQUIRED")

        return ClaimVerificationResult(
            claim_id=claim.claim_id, state=state, evidence_ids=result_evidence_ids,
            supporting_evidence_ids=supporting_ids,
            contradicting_evidence_ids=contradicting_ids,
            independent_source_count=independent_count,
            source_lineage=source_lineage, issues=tuple(sorted(issues)),
        )

    @staticmethod
    def _field_mismatch(claim: Claim, evidence: EvidenceRecord) -> Optional[str]:
        for name, expected, actual in (
            ("claim_key", claim.claim_key, evidence.claim_key),
            ("subject", claim.subject, evidence.subject),
            ("asset_id", claim.asset_id, evidence.asset_id),
            ("mapping_id", claim.mapping_id, evidence.mapping_id),
            ("value", claim.value, evidence.value),
            ("unit", claim.unit, evidence.unit),
            ("timeframe", claim.timeframe, evidence.timeframe),
            ("event_at", claim.event_at, evidence.event_at),
            ("status", claim.expected_status, evidence.status_value),
        ):
            if name == "value":
                equal = _value_equal(expected, actual)
            elif name in {"unit", "timeframe"}:
                equal = _same_optional_text(expected, actual)
            elif name == "status" and expected is None:
                equal = True
            else:
                equal = expected == actual
            if not equal:
                return name
        return None

    @staticmethod
    def _temporal_state(claim: Claim, evidence: EvidenceRecord) -> tuple[Optional[str], bool]:
        cutoff = _timestamp(claim.observed_at)
        published = _timestamp(evidence.published_at)
        observed = _timestamp(evidence.observed_at)
        updated = _timestamp(evidence.updated_at) if evidence.updated_at else published
        if published > observed or observed > cutoff or updated > cutoff:
            return "EVIDENCE_AFTER_CLAIM_CUTOFF", False
        if evidence.source_status == "STALE":
            return "EVIDENCE_STALE", True
        if claim.max_age_seconds is not None:
            if (cutoff - updated).total_seconds() > claim.max_age_seconds:
                return "EVIDENCE_STALE", True
        return None, False

    @staticmethod
    def _lineage_key(evidence: EvidenceRecord) -> str:
        return evidence.lineage_id or (
            "content:" + evidence.content_hash if evidence.content_hash
            else "source-family:" + evidence.source_family
        )

    @classmethod
    def _independent_source_count(cls, evidence: Sequence[EvidenceRecord]) -> int:
        if not evidence:
            return 0
        parent = list(range(len(evidence)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: int, right: int) -> None:
            root_left, root_right = find(left), find(right)
            if root_left != root_right:
                parent[root_right] = root_left

        seen: dict[tuple[str, str], int] = {}
        for index, item in enumerate(evidence):
            tokens = []
            if item.lineage_id:
                tokens.append(("lineage", item.lineage_id))
            if item.content_hash:
                tokens.append(("content", item.content_hash))
            if item.source_family:
                tokens.append(("family", item.source_family))
            for token in tokens:
                previous = seen.get(token)
                if previous is None:
                    seen[token] = index
                else:
                    union(index, previous)
        return len({find(index) for index in range(len(evidence))})

    @staticmethod
    def evidence_from_announcement(item: AnnouncementEvidence) -> tuple[EvidenceRecord, ...]:
        item.validate()
        output = []
        for asset_id in item.asset_ids or (None,):
            common = {
                "source_id": item.source_id, "source_family": item.publisher.casefold(),
                "source_kind": "PRIMARY", "publisher": item.publisher,
                "subject": item.publisher, "published_at": item.published_at,
                "observed_at": item.observed_at, "asset_id": asset_id,
                "timeframe": item.event_type, "event_at": item.event_at or item.published_at,
                "updated_at": item.updated_at, "source_url": item.source_url,
                "content_hash": item.content_hash,
                "lineage_id": item.content_hash or item.source_id,
                "is_primary": True, "source_status": "ACCEPTED", "status_value": "PUBLISHED",
            }
            output.append(EvidenceRecord(**common, claim_key="announcement.title", value=item.title))
            if item.body.strip():
                output.append(EvidenceRecord(**common, claim_key="announcement.body", value=item.body))
            output.append(EvidenceRecord(**common, claim_key="announcement.event_type", value=item.event_type))
            updated_time = _timestamp(item.updated_at or item.published_at)
            observed_time = _timestamp(item.observed_at)
            age_seconds = (observed_time - updated_time).total_seconds()
            freshness_value = "UNVERIFIED" if age_seconds < 0 else ("FRESH" if age_seconds <= 86400 else "STALE")
            freshness_status = (
                "UNVERIFIED" if freshness_value == "UNVERIFIED"
                else "ACCEPTED" if freshness_value == "FRESH"
                else "STALE"
            )
            output.append(EvidenceRecord(
                **{
                    **common,
                    "source_id": item.source_id + ":freshness",
                    "subject": asset_id or item.publisher,
                    "source_status": freshness_status,
                    "status_value": freshness_value,
                },
                claim_key="announcement.freshness", value=freshness_value,
            ))
            if asset_id:
                output.append(EvidenceRecord(
                    **{**common, "subject": asset_id},
                    claim_key="announcement.asset_id", value=asset_id,
                ))
        return tuple(output)

    @staticmethod
    def evidence_from_binance_spot_pairs(
        asset_id: str,
        pairs: Sequence[Mapping[str, Any]],
        *,
        observed_at: str,
        allowed_quote_assets: Sequence[str] = ("USDT",),
    ) -> tuple[EvidenceRecord, ...]:
        """Adapt exact active pairs from the official Binance exchangeInfo snapshot."""
        _timestamp(observed_at)
        if not isinstance(asset_id, str) or not asset_id.startswith("coingecko:"):
            raise ValueError("Binance Spot evidence requires a canonical CoinGecko asset ID")
        if isinstance(pairs, (str, bytes)) or not isinstance(pairs, Sequence):
            raise ValueError("Binance exchangeInfo pairs must be a sequence of objects")
        if isinstance(allowed_quote_assets, (str, bytes)) or not isinstance(allowed_quote_assets, Sequence):
            raise ValueError("allowed quote assets must be a sequence")
        allowed = {item.strip().upper() for item in allowed_quote_assets if isinstance(item, str) and item.strip()}
        if not allowed:
            raise ValueError("at least one allowed quote asset is required")
        output = []
        seen = set()
        for pair in pairs:
            if not isinstance(pair, Mapping):
                raise ValueError("Binance exchangeInfo pair must be an object")
            base, quote, symbol = pair.get("baseAsset"), pair.get("quoteAsset"), pair.get("symbol")
            permissions = pair.get("permissionSets")
            permissions_valid = (
                isinstance(permissions, list) and bool(permissions)
                and all(
                    isinstance(group, list) and bool(group)
                    and all(isinstance(permission, str) and permission for permission in group)
                    for group in permissions
                )
                and any("SPOT" in group for group in permissions)
            )
            if (not isinstance(base, str) or not base.isalnum() or base != base.upper()
                    or not isinstance(quote, str) or not quote.isalnum() or quote not in allowed
                    or not isinstance(symbol, str) or symbol != base + quote
                    or pair.get("status") != "TRADING"
                    or pair.get("isSpotTradingAllowed") is not True
                    or not permissions_valid):
                continue
            if symbol in seen:
                raise ValueError("duplicate Binance Spot pair in eligibility evidence")
            seen.add(symbol)
            canonical = {
                "symbol": symbol, "baseAsset": base, "quoteAsset": quote,
                "status": "TRADING", "isSpotTradingAllowed": True,
                "permissionSets": permissions,
            }
            content_hash = _digest(json.dumps(canonical, sort_keys=True, separators=(",", ":")))
            output.append(EvidenceRecord(
                source_id=f"binance-exchange-info:{symbol}:{_digest(observed_at)[:16]}",
                source_family="binance_spot_exchange_info", source_kind="PRIMARY",
                publisher="Binance Spot exchangeInfo", subject=asset_id,
                claim_key="binance_spot.eligible", value=True,
                published_at=observed_at, updated_at=observed_at, observed_at=observed_at,
                asset_id=asset_id, timeframe="spot", event_at=observed_at,
                source_url="https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT",
                content_hash=content_hash, lineage_id=content_hash,
                is_primary=True, source_status="ACCEPTED", status_value="TRADING",
            ))
        if not output:
            raise ValueError("no active, permission-verified Binance Spot pair supports this asset")
        return tuple(output)

    @staticmethod
    def evidence_from_publication_history(
        asset_id: str,
        symbol: str,
        posted_hours_ago: Optional[float],
        *,
        observed_at: str,
    ) -> EvidenceRecord:
        """Record exactly what the local latest-200-post ledger reports for a symbol."""
        _timestamp(observed_at)
        if (not isinstance(asset_id, str) or not asset_id.startswith("coingecko:")
                or not isinstance(symbol, str) or not symbol.strip()):
            raise ValueError("publication-history evidence requires canonical asset and symbol")
        if posted_hours_ago is None:
            value: Any = "NO_RECORD_IN_LATEST_200"
            unit = None
            status_value = "NO_RECENT_RECORD"
        else:
            if (isinstance(posted_hours_ago, bool) or not isinstance(posted_hours_ago, (int, float))
                    or not math.isfinite(posted_hours_ago) or posted_hours_ago < 0):
                raise ValueError("posted_hours_ago must be a finite non-negative number or unavailable")
            value = int(round(posted_hours_ago))
            unit = "hours"
            status_value = "RECENT_RECORD"
        payload = f"{symbol.strip().upper()}|{value}|{observed_at}"
        return EvidenceRecord(
            source_id="local-publication-ledger:" + _digest(payload),
            source_family="local_publication_ledger", source_kind="PRIMARY",
            publisher="local publication ledger", subject=asset_id,
            claim_key="publication.last_posted", value=value,
            published_at=observed_at, updated_at=observed_at, observed_at=observed_at,
            asset_id=asset_id, unit=unit, timeframe="latest_200_posts",
            content_hash=_digest(payload), lineage_id="local-ledger:" + _digest(payload),
            is_primary=True, source_status="ACCEPTED", status_value=status_value,
        )

    @staticmethod
    def evidence_from_market_observation(item: MarketObservation) -> tuple[EvidenceRecord, ...]:
        item.validate()
        source_id = item.data_hash or _digest("|".join((item.provider, item.endpoint, item.observed_at)))
        published_at = item.source_timestamp or item.published_at or item.observed_at
        updated_at = item.source_timestamp or item.published_at
        is_primary = item.provider.casefold().startswith("binance_")
        fields = (
            ("price", item.price, item.currency, "spot"),
            ("change_24h", item.change_24h, "percent", "24h"),
            ("volume_24h", item.volume_24h, item.currency, "24h"),
            ("market_cap", item.market_cap, item.currency, "spot"),
        )
        output = []
        for name, value, unit, timeframe in fields:
            if value is None or item.field_availability.get(name) == "UNAVAILABLE":
                continue
            freshness = item.freshness_by_field.get(name)
            source_status = (
                "STALE" if freshness == "STALE"
                else "UNVERIFIED" if freshness == "UNKNOWN"
                else "ACCEPTED"
            )
            output.append(EvidenceRecord(
                source_id=source_id, source_family=item.provider, source_kind="MARKET",
                publisher=item.provider, subject=item.asset_id, claim_key="market." + name,
                value=value, published_at=published_at, updated_at=updated_at,
                observed_at=item.observed_at, asset_id=item.asset_id, unit=unit,
                timeframe=timeframe,
                event_at=_timestamp(published_at).isoformat(),
                content_hash=item.data_hash, lineage_id=item.data_hash or source_id,
                is_primary=is_primary,
                source_status=source_status, status_value=freshness or "OBSERVED",
            ))
        return tuple(output)

    @staticmethod
    def evidence_from_trend_signal(item: TrendSignal) -> tuple[EvidenceRecord, ...]:
        item.validate()
        # Gainer/volume topics are two derived views over the same MarketScanner
        # universe, not two independent publishers. Keep one dependency family
        # even when the upstream market observation omitted its content hash.
        market_derived = item.source in {"market_gainer", "market_volume"}
        source_family = "market_scanner_derived" if market_derived else item.source
        source_kind = "MARKET" if market_derived else "SOCIAL"
        return tuple(
            EvidenceRecord(
                source_id=item.source_item_id or item.content_hash,
                source_family=source_family, source_kind=source_kind, publisher=item.source,
                subject=asset_id,
                claim_key="trend.topic:" + _digest(item.topic.casefold())[:16], value=item.topic.strip().casefold(),
                published_at=item.observed_at, observed_at=item.observed_at,
                asset_id=asset_id, timeframe="current", content_hash=item.content_hash,
                lineage_id=item.content_hash, is_primary=False, source_status="ACCEPTED",
            )
            for asset_id in item.asset_ids
        )

    @staticmethod
    def evidence_from_onchain_observation(
        observation: OnChainObservation,
        validation: OnChainValidationResult,
    ) -> EvidenceRecord:
        if not isinstance(observation, OnChainObservation) or not isinstance(validation, OnChainValidationResult):
            raise ValueError("on-chain evidence adapter requires Module 9 observation and validation records")
        accepted = bool(
            validation.status == "ACCEPTED"
            and validation.observation_id == observation.observation_id
            and validation.asset_id == observation.asset_id
            and validation.mapping_id == observation.mapping_id
            and validation.network_id == observation.network_id
            and validation.provider == observation.provider
        )
        return EvidenceRecord(
            source_id=observation.observation_id, source_family=observation.provider,
            source_kind="ONCHAIN", publisher=observation.provider, subject=observation.asset_id,
            claim_key="onchain.transaction_hash", value=observation.transaction_hash,
            published_at=observation.block_time, observed_at=observation.observed_at,
            asset_id=observation.asset_id, mapping_id=observation.mapping_id,
            timeframe=observation.network_id, event_at=observation.block_time,
            source_status="ACCEPTED" if accepted else "UNVERIFIED",
            is_primary=accepted, status_value=observation.finality,
        )

    @staticmethod
    def evidence_from_onchain_summary(summary: Mapping[str, Any]) -> EvidenceRecord:
        required = ("summary_id", "asset_id", "network_id", "mapping_id", "observed_at",
                    "first_block_time", "last_block_time")
        if not isinstance(summary, Mapping) or not all(
            isinstance(summary.get(key), str) and summary.get(key).strip() for key in required
        ):
            raise ValueError("on-chain summary evidence identity is incomplete")
        if summary.get("threshold_met") is not True:
            raise ValueError("only threshold-qualified Module 9 summaries are evidence")
        if (not re.fullmatch(r"[0-9a-f]{64}", summary["summary_id"])
                or not summary["asset_id"].startswith("coingecko:")):
            raise ValueError("Module 9 summary identifiers are not canonical")
        decimals = summary.get("decimals")
        transfer_count = summary.get("transfer_count")
        if (isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 36
                or isinstance(transfer_count, bool) or not isinstance(transfer_count, int)
                or transfer_count <= 0):
            raise ValueError("Module 9 summary decimals or transfer count is invalid")
        try:
            total_amount = Decimal(str(summary.get("total_amount")))
            minimum_amount = Decimal(str(summary.get("minimum_amount")))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Module 9 summary amounts are invalid") from None
        if (not total_amount.is_finite() or not minimum_amount.is_finite()
                or total_amount <= 0 or minimum_amount <= 0 or total_amount < minimum_amount):
            raise ValueError("Module 9 summary amounts do not meet the explicit threshold")
        first_block_time = _timestamp(summary["first_block_time"])
        last_block_time = _timestamp(summary["last_block_time"])
        observed_at = _timestamp(summary["observed_at"])
        if first_block_time > last_block_time or last_block_time > observed_at:
            raise ValueError("Module 9 summary block-time range is invalid")
        return EvidenceRecord(
            source_id=summary["summary_id"], source_family="module9_canonical_store",
            source_kind="ONCHAIN", publisher="Module 9 canonical transfer aggregator",
            subject=summary["asset_id"], claim_key="onchain.transfer_summary",
            value=summary["summary_id"], published_at=summary["last_block_time"],
            updated_at=summary["observed_at"], observed_at=summary["observed_at"],
            asset_id=summary["asset_id"], mapping_id=summary["mapping_id"],
            timeframe=summary["network_id"], event_at=summary["last_block_time"], is_primary=True,
            source_status="ACCEPTED", status_value="THRESHOLD_MET",
        )

    @staticmethod
    def drafts_from_text(
        text: str, *, subject: str, asset_id: Optional[str], observed_at: str,
        impact: str = "MEDIUM", max_claims: int = 80,
    ) -> tuple[Claim, ...]:
        """Create unclassified sentence drafts; none can verify without structured evidence links."""
        if (not isinstance(subject, str) or not subject.strip()
                or isinstance(max_claims, bool) or not isinstance(max_claims, int) or max_claims < 1):
            raise ValueError("claim draft subject and positive max_claims are required")
        drafts = []
        seen = set()
        for sentence in split_atomic_claims(text):
            if sentence in seen:
                continue
            seen.add(sentence)
            drafts.append(Claim(
                text=sentence, subject=subject, asset_id=asset_id,
                claim_key="unclassified.research_sentence", value=sentence,
                observed_at=observed_at, evidence_ids=(), claim_type="UNCLASSIFIED",
                impact=impact,
            ))
            if len(drafts) >= max_claims:
                break
        return tuple(drafts)

    @staticmethod
    def append_asset_evidence_context(
        text: str,
        evidence_records: Sequence[EvidenceRecord],
        *,
        subject: str,
        asset_id: Optional[str],
    ) -> str:
        """Append bounded, source-backed trend/on-chain references for one exact asset."""
        if not isinstance(text, str) or not isinstance(subject, str) or not subject.strip():
            raise ValueError("research text and canonical subject are required")
        if asset_id is not None and (not isinstance(asset_id, str) or not asset_id.strip()):
            raise ValueError("asset_id must be canonical text or unavailable")
        matching = [
            item for item in evidence_records
            if item.subject == subject and item.asset_id == asset_id
            and item.source_status == "ACCEPTED"
        ]
        trend_topics = sorted({
            item.value for item in matching
            if item.claim_key.startswith("trend.topic:")
            and item.source_kind in {"SOCIAL", "MARKET"} and isinstance(item.value, str)
        })
        summary_ids = sorted({
            item.value for item in matching
            if item.claim_key == "onchain.transfer_summary"
            and item.source_kind == "ONCHAIN" and item.status_value == "THRESHOLD_MET"
            and item.source_id == item.value and isinstance(item.value, str)
            and re.fullmatch(r"[0-9a-f]{64}", item.value)
        })
        sections = []
        if trend_topics:
            sections.append(
                "── EVIDENCE-BACKED TREND SIGNALS ──\n"
                + "\n".join(f"Trend topic: {topic}" for topic in trend_topics)
            )
        if summary_ids:
            sections.append(
                "── VERIFIED ON-CHAIN SUMMARIES ──\n"
                + "\n".join(
                    f"On-chain transfer summary ID: {summary_id}" for summary_id in summary_ids
                )
            )
        if not sections:
            return text
        return text.rstrip() + "\n\n" + "\n\n".join(sections)

    def claims_from_research_package(
        self,
        text: str,
        evidence_records: Sequence[EvidenceRecord],
        *,
        subject: str,
        asset_id: Optional[str],
        observed_at: str,
        preferred_market_content_hash: Optional[str] = None,
        require_preferred_market_content_hash: bool = False,
        market_max_age_seconds: int = 900,
        max_claims: int = 120,
    ) -> tuple[Claim, ...]:
        """Extract package claims conservatively and link only exact typed source records.

        Unknown factual lines remain UNCLASSIFIED. Heuristic analysis is explicitly
        non-factual. No fuzzy entity/value matching or model-derived evidence is used.
        """
        if not isinstance(text, str) or not isinstance(subject, str) or not subject.strip():
            raise ValueError("research text and canonical subject are required")
        if asset_id is not None and (not isinstance(asset_id, str) or not asset_id.strip()):
            raise ValueError("asset_id must be canonical text or unavailable")
        if preferred_market_content_hash is not None and not re.fullmatch(r"[0-9a-f]{64}", preferred_market_content_hash):
            raise ValueError("preferred market content hash must be a lowercase SHA-256 digest")
        if not isinstance(require_preferred_market_content_hash, bool):
            raise ValueError("require_preferred_market_content_hash must be boolean")
        _timestamp(observed_at)
        if (isinstance(market_max_age_seconds, bool) or not isinstance(market_max_age_seconds, int)
                or market_max_age_seconds <= 0 or isinstance(max_claims, bool)
                or not isinstance(max_claims, int) or max_claims < 1):
            raise ValueError("positive market freshness and claim limits are required")

        field_specs = {
            "Price": ("market.price", r"\$([+-]?(?:\d+(?:\.\d*)?|\.\d+))", "USDT", "spot"),
            "24h Change": ("market.change_24h", r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))%", "percent", "24h"),
            "Volume 24h": ("market.volume_24h", r"\$([+-]?(?:\d+(?:\.\d*)?|\.\d+))", "USDT", "24h"),
            "Market Cap": ("market.market_cap", r"\$([+-]?(?:\d+(?:\.\d*)?|\.\d+))", "USDT", "spot"),
        }
        interpretation_prefixes = (
            "Stage:", "Sector:", "Freshness:", "Level:", "Analysis:", "Volume Signal Index:",
            "Top 5 Coin:", "Square Interest:", "Entry:", "Liquidity:",
            "Trade Ready:", "Risk:", "Repetition Risk:",
        )
        claims: list[Claim] = []
        seen: set[tuple[str, str]] = set()
        selected_announcement_lineage: Optional[str] = None
        selected_event_type: Optional[str] = None

        def append_claim(claim: Claim) -> None:
            identity = (claim.claim_key, claim.text)
            if identity not in seen and len(claims) < max_claims:
                seen.add(identity)
                claims.append(claim)

        for raw_line in text.splitlines():
            line = raw_line.strip()
            trend_match = re.fullmatch(r"Trend topic:\s*(.{1,160})", line, flags=re.IGNORECASE)
            if trend_match:
                topic = trend_match.group(1).strip().casefold()
                trend_key = "trend.topic:" + _digest(topic)[:16]
                candidates = [
                    item for item in evidence_records
                    if item.claim_key == trend_key and item.subject == subject
                    and item.asset_id == asset_id and item.value == topic
                    and item.source_kind in {"SOCIAL", "MARKET"} and item.source_status == "ACCEPTED"
                ]
                if candidates:
                    latest_observed = max(_timestamp(item.observed_at) for item in candidates)
                    linked = [
                        item for item in candidates
                        if _timestamp(item.observed_at) == latest_observed
                    ]
                    exemplar = linked[0]
                    append_claim(Claim(
                        text=line, subject=subject, asset_id=asset_id,
                        claim_key=trend_key, value=topic, timeframe=exemplar.timeframe,
                        event_at=exemplar.event_at, observed_at=observed_at,
                        claim_type="SOURCE_ASSERTION", impact="LOW",
                        evidence_ids=tuple(sorted(item.evidence_id for item in linked)),
                        max_age_seconds=86400,
                    ))
                else:
                    append_claim(Claim(
                        text=line, subject=subject, asset_id=asset_id,
                        claim_key=trend_key, value=topic, observed_at=observed_at,
                        claim_type="SOURCE_ASSERTION", impact="LOW", evidence_ids=(),
                        max_age_seconds=86400,
                    ))
                continue

            summary_match = re.fullmatch(
                r"On-chain transfer summary ID:\s*([0-9a-f]{64})", line, flags=re.IGNORECASE,
            )
            if summary_match:
                summary_id = summary_match.group(1)
                candidates = [
                    item for item in evidence_records
                    if item.claim_key == "onchain.transfer_summary"
                    and item.source_id == summary_id and item.value == summary_id
                    and item.subject == subject and item.asset_id == asset_id
                    and item.source_kind == "ONCHAIN" and item.source_status == "ACCEPTED"
                    and item.status_value == "THRESHOLD_MET"
                ]
                linked = tuple(sorted(item.evidence_id for item in candidates))
                exemplar = candidates[0] if candidates else None
                append_claim(Claim(
                    text=line, subject=subject, asset_id=asset_id,
                    mapping_id=exemplar.mapping_id if exemplar else None,
                    claim_key="onchain.transfer_summary", value=summary_id,
                    timeframe=exemplar.timeframe if exemplar else None,
                    event_at=exemplar.event_at if exemplar else None,
                    expected_status="THRESHOLD_MET", observed_at=observed_at,
                    claim_type="SOURCE_ASSERTION", impact="MEDIUM",
                    evidence_ids=linked, max_age_seconds=86400,
                ))
                continue
            if not line or line.startswith("COIN:") or (line.startswith("──") and line.endswith("──")):
                continue
            # Split multi-field lines and compound sentences before classification.
            segments = []
            for part in line.split("|"):
                part = part.strip()
                is_bullet = part.startswith(("-", "*", "•"))
                if part.startswith("Detail:"):
                    atoms = (part,)  # preserve exact source title for evidence matching
                else:
                    atoms = split_atomic_claims(part)
                segments.extend(("- " + atom) if is_bullet else atom for atom in atoms)
            for segment in segments:
                segment = segment.strip()
                if not segment.startswith("Detail:"):
                    segment = segment.rstrip(".!?").strip()
                matched_field = False
                for label, (claim_key, number_pattern, default_unit, default_timeframe) in field_specs.items():
                    match = re.fullmatch(rf"{re.escape(label)}:\s*{number_pattern}", segment)
                    if not match:
                        continue
                    matched_field = True
                    numeric_value = float(match.group(1))
                    related = [
                        item for item in evidence_records
                        if item.claim_key == claim_key and item.subject == subject
                        and item.asset_id == asset_id
                        and (not require_preferred_market_content_hash
                             or (preferred_market_content_hash is not None
                                 and item.content_hash == preferred_market_content_hash))
                        and item.source_status in {"ACCEPTED", "STALE", "UNVERIFIED"}
                    ]
                    claim_value: Any = numeric_value
                    if related:
                        latest_observed = max(_timestamp(item.observed_at) for item in related)
                        linked = [
                            item for item in related
                            if _timestamp(item.observed_at) == latest_observed
                        ]
                        exemplar = linked[0]
                        unit = exemplar.unit or default_unit
                        timeframe = exemplar.timeframe or default_timeframe
                        event_at = exemplar.event_at
                        evidence_ids = tuple(sorted(item.evidence_id for item in linked))
                        for item in linked:
                            try:
                                raw_number = float(item.value)
                                displayed = (
                                    f"{raw_number:.6f}" if label == "Price"
                                    else f"{raw_number:+.1f}" if label == "24h Change"
                                    else f"{raw_number:.0f}"
                                )
                            except (TypeError, ValueError, OverflowError):
                                continue
                            if displayed == match.group(1):
                                claim_value = item.value
                                break
                    else:
                        unit, timeframe, event_at, evidence_ids = default_unit, default_timeframe, None, ()
                    append_claim(Claim(
                        text=segment, subject=subject, asset_id=asset_id,
                        claim_key=claim_key, value=claim_value, unit=unit,
                        timeframe=timeframe, event_at=event_at, observed_at=observed_at,
                        claim_type="SOURCE_ASSERTION", impact="MEDIUM",
                        evidence_ids=evidence_ids, max_age_seconds=market_max_age_seconds,
                    ))
                    break
                if matched_field:
                    continue

                if segment == "Binance Spot: YES":
                    candidates = [
                        item for item in evidence_records
                        if item.claim_key == "binance_spot.eligible"
                        and item.subject == subject and item.asset_id == asset_id
                        and item.value is True and item.status_value == "TRADING"
                    ]
                    linked = tuple(sorted(item.evidence_id for item in candidates))
                    exemplar = candidates[0] if candidates else None
                    append_claim(Claim(
                        text=segment, subject=subject, asset_id=asset_id,
                        claim_key="binance_spot.eligible", value=True,
                        timeframe="spot", event_at=exemplar.event_at if exemplar else None,
                        expected_status="TRADING", observed_at=observed_at,
                        claim_type="SOURCE_ASSERTION", impact="MEDIUM",
                        evidence_ids=linked, max_age_seconds=900,
                    ))
                    continue

                if segment.startswith("Last posted:"):
                    no_recent = segment == "Last posted: NO RECORD IN LATEST 200 LOCAL POSTS"
                    hours_match = re.fullmatch(r"Last posted:\s*(\d+)\s+hours ago", segment)
                    if no_recent:
                        value, unit, status_value = "NO_RECORD_IN_LATEST_200", None, "NO_RECENT_RECORD"
                    elif hours_match:
                        value, unit, status_value = int(hours_match.group(1)), "hours", "RECENT_RECORD"
                    else:
                        value, unit, status_value = None, None, None
                    candidates = [
                        item for item in evidence_records
                        if item.claim_key == "publication.last_posted"
                        and item.subject == subject and item.asset_id == asset_id
                        and item.value == value and item.unit == unit
                        and item.timeframe == "latest_200_posts"
                        and item.status_value == status_value
                    ] if value is not None else []
                    linked = tuple(sorted(item.evidence_id for item in candidates))
                    exemplar = candidates[0] if candidates else None
                    append_claim(Claim(
                        text=segment, subject=subject, asset_id=asset_id,
                        claim_key="publication.last_posted", value=value if value is not None else segment,
                        unit=unit, timeframe="latest_200_posts" if value is not None else None,
                        expected_status=status_value, observed_at=observed_at,
                        claim_type="SOURCE_ASSERTION", impact="LOW",
                        evidence_ids=linked, max_age_seconds=900,
                    ))
                    continue

                if segment.startswith("Age:"):
                    if segment == "Age: Ongoing market activity":
                        append_claim(Claim(
                            text=segment, subject=subject, asset_id=asset_id,
                            claim_key="research.interpretation", value=segment,
                            observed_at=observed_at, claim_type="ANALYST_INTERPRETATION",
                            impact="LOW", evidence_ids=(),
                        ))
                        continue
                    candidates = [
                        item for item in evidence_records
                        if item.claim_key == "announcement.freshness"
                        and item.asset_id == asset_id
                        and selected_announcement_lineage is not None
                        and item.lineage_id == selected_announcement_lineage
                    ] if segment == "Age: Just announced by Binance (FRESH)" else []
                    linked = tuple(sorted(item.evidence_id for item in candidates))
                    exemplar = candidates[0] if candidates else None
                    append_claim(Claim(
                        text=segment, subject=exemplar.subject if exemplar else subject,
                        asset_id=asset_id, claim_key="announcement.freshness", value="FRESH",
                        timeframe=exemplar.timeframe if exemplar else None,
                        event_at=exemplar.event_at if exemplar else None,
                        expected_status="FRESH", observed_at=observed_at,
                        claim_type="SOURCE_ASSERTION", impact="MEDIUM",
                        evidence_ids=linked, max_age_seconds=86400,
                    ))
                    continue

                if segment.startswith(("Type:", "Detail:")):
                    raw_value = segment.split(":", 1)[1].strip()
                    field = "announcement.event_type" if segment.startswith("Type:") else "announcement.title"
                    if segment.startswith("Detail:"):
                        body_matches = [
                            item for item in evidence_records
                            if item.claim_key == "announcement.body" and item.asset_id == asset_id
                            and isinstance(item.value, str)
                            and item.value.strip().casefold() == raw_value.casefold()
                        ]
                        if body_matches:
                            field = "announcement.body"
                    if field == "announcement.event_type":
                        selected_event_type = raw_value.casefold()
                    if field == "announcement.event_type" and raw_value.casefold() == "market movement":
                        append_claim(Claim(
                            text=segment, subject=subject, asset_id=asset_id,
                            claim_key="research.interpretation", value=segment,
                            observed_at=observed_at, claim_type="ANALYST_INTERPRETATION",
                            impact="LOW", evidence_ids=(),
                        ))
                        continue
                    candidates = [
                        item for item in evidence_records
                        if item.claim_key == field and item.asset_id == asset_id
                        and isinstance(item.value, str)
                        and item.value.strip().casefold() == raw_value.casefold()
                    ]
                    if candidates:
                        latest_observed = max(_timestamp(item.observed_at) for item in candidates)
                        linked = [item for item in candidates if _timestamp(item.observed_at) == latest_observed]
                        exemplar = linked[0]
                        if field == "announcement.title":
                            selected_announcement_lineage = exemplar.lineage_id
                        append_claim(Claim(
                            text=segment, subject=exemplar.subject, asset_id=asset_id,
                            claim_key=field, value=exemplar.value, unit=exemplar.unit,
                            timeframe=exemplar.timeframe, event_at=exemplar.event_at,
                            expected_status=exemplar.status_value, observed_at=observed_at,
                            claim_type="SOURCE_ASSERTION", impact="HIGH" if "listing" in raw_value.casefold() else "MEDIUM",
                            evidence_ids=tuple(sorted(item.evidence_id for item in linked)),
                            max_age_seconds=86400,
                        ))
                    elif segment.startswith("Detail:") and selected_event_type == "market movement":
                        # These Detail lines are generated heuristic commentary only when
                        # the package explicitly identifies the section as MARKET MOVEMENT.
                        append_claim(Claim(
                            text=segment, subject=subject, asset_id=asset_id,
                            claim_key="research.interpretation", value=segment,
                            observed_at=observed_at, claim_type="ANALYST_INTERPRETATION",
                            impact="LOW", evidence_ids=(),
                        ))
                    elif segment.startswith("Detail:"):
                        # An unmatched announcement headline is factual, not analysis.
                        # Keep it unresolved unless an exact accepted source record matches.
                        append_claim(Claim(
                            text=segment, subject=subject, asset_id=asset_id,
                            claim_key=field, value=raw_value, observed_at=observed_at,
                            claim_type="UNCLASSIFIED", impact="MEDIUM", evidence_ids=(),
                            max_age_seconds=86400,
                        ))
                    else:
                        append_claim(Claim(
                            text=segment, subject=subject, asset_id=asset_id,
                            claim_key=field, value=raw_value, observed_at=observed_at,
                            claim_type="CONFIRMED_FACT", impact="HIGH" if "listing" in raw_value.casefold() else "MEDIUM",
                            evidence_ids=(), max_age_seconds=86400,
                        ))
                    continue

                if segment.startswith(("Volume vs Normal:",)):
                    append_claim(Claim(
                        text=segment, subject=subject, asset_id=asset_id,
                        claim_key="research.interpretation", value=segment,
                        observed_at=observed_at, claim_type="ANALYST_INTERPRETATION",
                        impact="LOW", evidence_ids=(),
                    ))
                    continue

                if segment.startswith(interpretation_prefixes):
                    append_claim(Claim(
                        text=segment, subject=subject, asset_id=asset_id,
                        claim_key="research.interpretation", value=segment,
                        observed_at=observed_at, claim_type="ANALYST_INTERPRETATION",
                        impact="LOW", evidence_ids=(),
                    ))
                    continue

                # Risk/WHY TRADE NOW bullet points are interpretations, not verified events.
                if segment.startswith("- ") and (
                    "── RISK " in text or "── WHY TRADE NOW " in text
                ):
                    append_claim(Claim(
                        text=segment[2:].strip(), subject=subject, asset_id=asset_id,
                        claim_key="research.interpretation", value=segment[2:].strip(),
                        observed_at=observed_at, claim_type="ANALYST_INTERPRETATION",
                        impact="LOW", evidence_ids=(),
                    ))
                    continue

                append_claim(Claim(
                    text=segment, subject=subject, asset_id=asset_id,
                    claim_key="unclassified.research_statement", value=segment,
                    observed_at=observed_at, claim_type="UNCLASSIFIED",
                    impact="MEDIUM", evidence_ids=(),
                ))
        return tuple(claims)

    def rebuild_from_store(
        self,
        store: Any,
        *,
        onchain_records: Sequence[tuple[OnChainObservation, OnChainValidationResult]] = (),
        onchain_summary_refs: Sequence[Mapping[str, Any]] = (),
    ) -> ClaimRegistry:
        required_reads = (
            "iter_announcement_revisions", "iter_market_observations", "iter_trend_signals",
        )
        if any(not callable(getattr(store, name, None)) for name in required_reads):
            raise TypeError("Layer1 persistence store is missing source-record read methods")
        evidence = []
        for announcement in store.iter_announcement_revisions():
            evidence.extend(self.evidence_from_announcement(announcement))
        for observation in store.iter_market_observations():
            evidence.extend(self.evidence_from_market_observation(observation))
        for signal in store.iter_trend_signals():
            evidence.extend(self.evidence_from_trend_signal(signal))
        for observation, validation in onchain_records:
            evidence.append(self.evidence_from_onchain_observation(observation, validation))
        for summary in onchain_summary_refs:
            evidence.append(self.evidence_from_onchain_summary(summary))
        claims = self._source_assertion_claims(evidence)
        return self.verify(claims, evidence)

    @staticmethod
    def _source_assertion_claims(evidence: Sequence[EvidenceRecord]) -> tuple[Claim, ...]:
        grouped: dict[str, list[EvidenceRecord]] = {}
        for item in evidence:
            key = json.dumps({
                "subject": item.subject, "asset_id": item.asset_id, "mapping_id": item.mapping_id,
                "claim_key": item.claim_key, "value": item.value, "unit": item.unit, "timeframe": item.timeframe,
                "event_at": item.event_at, "status_value": item.status_value,
            }, sort_keys=True, separators=(",", ":"), allow_nan=False)
            grouped.setdefault(key, []).append(item)
        claims = []
        for items in grouped.values():
            first = items[0]
            observed_at = max(items, key=lambda item: _timestamp(item.observed_at)).observed_at
            value_text = json.dumps(first.value, ensure_ascii=False)
            claims.append(Claim(
                text=f"Source assertion: {first.subject} {first.claim_key} = {value_text}",
                subject=first.subject, asset_id=first.asset_id, mapping_id=first.mapping_id,
                claim_key=first.claim_key, value=first.value, unit=first.unit, timeframe=first.timeframe,
                event_at=first.event_at, expected_status=first.status_value,
                observed_at=observed_at, claim_type="SOURCE_ASSERTION", impact="LOW",
                evidence_ids=tuple(sorted(item.evidence_id for item in items)),
            ))
        return tuple(sorted(claims, key=lambda item: item.claim_id))


_INDEPENDENT_CLAUSE_SUBJECT = (
    r"(?:the|this|that|these|those)\s+(?:token|asset|coin|company|exchange|price|volume|market|"
    r"listing|announcement|pair|network|protocol|project|team|source)"
    r"|(?:it|they|we|trading|volume|price|market)"
    r"|(?:[a-z][A-Za-z0-9.-]*['’]s\s+(?:price|volume|market\s+cap))"
    r"|(?:\$?[A-Z][A-Za-z0-9.-]*(?:['’]s)?(?:\s+[A-Za-z][A-Za-z0-9.-]*){0,2})"
)
_INDEPENDENT_CLAUSE_VERB = (
    r"(?:is|are|was|were|has|have|had|do|does|did|will|can|could|may|might|must|should|"
    r"announced|confirms?|confirmed|lists?|listed|delists?|delisted|launch(?:es|ed)?|"
    r"opens?|opened|closes?|closed|reports?|reported|files?|filed|approves?|approved|"
    r"rejects?|rejected|reaches?|reached|records?|recorded|posts?|posted|updates?|updated|"
    r"adds?|added|removes?|removed|began|ends?|ended|shows?|showed|saw|remains?|continues?|"
    r"pauses?|paused|suspends?|suspended|resumes?|resumed|rises?|rose|falls?|fell|"
    r"increases?|increased|decreases?|decreased|surges?|surged|drops?|dropped|gains?|gained|"
    r"loses?|lost|moves?|moved|trades?|traded|holds?|held|cuts?|cut|hits?|hit|changes?|changed)"
)

_COMPOUND_RELATIVE_CLAUSE_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    rf",\s*which\s+{_INDEPENDENT_CLAUSE_VERB}\b",
))
_INDEPENDENT_CLAUSE_START = re.compile(
    rf"^{_INDEPENDENT_CLAUSE_SUBJECT}\s+{_INDEPENDENT_CLAUSE_VERB}\b"
)
_FINITE_CLAUSE_VERB = re.compile(rf"\b{_INDEPENDENT_CLAUSE_VERB}\b", re.IGNORECASE)
_SHARED_SUBJECT_PREDICATE = re.compile(
    rf"^({_INDEPENDENT_CLAUSE_SUBJECT})\s+({_INDEPENDENT_CLAUSE_VERB})\b(.*)$",
    re.IGNORECASE,
)
_SHARED_SUBJECT_CONJUNCTION = re.compile(
    rf"(?:\s+(?:and|but)\s+(?:(?:then|also|later|subsequently)\s+)?|"
    rf"\s+(?:then|later|subsequently)\s+|"
    rf",\s*(?:then|later|subsequently)\s+)"
    rf"({_INDEPENDENT_CLAUSE_VERB})\b",
    re.IGNORECASE,
)


def _split_shared_subject_conjuncts(clause: str) -> tuple[str, ...]:
    """Expand a repeated predicate only when one explicit subject is recoverable."""
    prefix = _SHARED_SUBJECT_PREDICATE.match(clause)
    if not prefix:
        return (clause,)
    subject = prefix.group(1).strip()
    for match in _SHARED_SUBJECT_CONJUNCTION.finditer(clause, prefix.end(2)):
        left = clause[:match.start()].strip().rstrip(",; ")
        right_tail = clause[match.end():].strip()
        right = (subject + " " + match.group(1) + (" " + right_tail if right_tail else "")).strip()
        if not left or not right:
            continue
        return (
            _split_shared_subject_conjuncts(left)
            + _split_shared_subject_conjuncts(right)
        )
    return (clause,)


def _split_independent_conjuncts(clause: str) -> tuple[str, ...]:
    """Split only when both sides visibly contain an independent subject/verb clause.

    This deliberately leaves ambiguous elliptical constructions intact. Shared-subject
    predicates are expanded only when a recognized finite verb makes the second
    proposition explicit; the resulting claims still need independent evidence links.
    """
    for match in re.finditer(r"\s+(?:,\s*)?(?:and|but|while|whereas|as)\s+", clause, re.IGNORECASE):
        left = clause[:match.start()].strip().rstrip(",; ")
        right = clause[match.end():].strip()
        if not left or not right or not _FINITE_CLAUSE_VERB.search(left):
            continue
        if not _INDEPENDENT_CLAUSE_START.match(right):
            continue
        return _split_independent_conjuncts(left) + _split_independent_conjuncts(right)
    return _split_shared_subject_conjuncts(clause)


def split_atomic_claims(text: str) -> tuple[str, ...]:
    """Deterministic sentence/clause segmentation; it does not infer evidence or truth."""
    if not isinstance(text, str) or not text.strip():
        return ()
    output = []
    protected_period = "\uE000"
    abbreviation_pattern = re.compile(
        r"\b(?:e\.g|i\.e|etc|mr|mrs|ms|dr|prof|vs|approx|no|inc|corp|ltd|plc|llc|co)\.|"
        r"\b(?:[A-Za-z]\.){2,}",
        re.IGNORECASE,
    )
    for line in text.replace("\r", "\n").split("\n"):
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if not line or (line.startswith("──") and line.endswith("──")):
            continue
        # In a.m./p.m., protect only the internal period. The trailing period
        # may still be a real sentence boundary.
        line = re.sub(
            r"\b([ap])\.m\.",
            lambda match: match.group(1) + protected_period + "m.",
            line,
            flags=re.IGNORECASE,
        )
        line = abbreviation_pattern.sub(
            lambda match: match.group(0).replace(".", protected_period), line,
        )
        for part in re.split(r"(?<=[.!?])\s+|;\s*", line):
            normalized = part.replace(protected_period, ".").strip(" \t\"'")
            if normalized:
                output.extend(_split_independent_conjuncts(normalized))
    return tuple(output)


def render_claim_registry(registry: ClaimRegistry, *, asset_id: Optional[str] = None) -> str:
    """Render a bounded, explicit evidence register for a research-package consumer."""
    if not isinstance(registry, ClaimRegistry):
        return "CLAIM VERIFICATION REGISTER: unavailable; do not state unsupported claims as facts."
    claims_by_id = {claim.claim_id: claim for claim in registry.claims}
    all_selected = []
    for result in registry.results:
        claim = claims_by_id.get(result.claim_id)
        if claim is None or (asset_id and claim.asset_id not in {None, asset_id}):
            continue
        all_selected.append((claim, result))
    latest_by_scope: dict[tuple[Any, ...], tuple[datetime, list[tuple[Claim, ClaimVerificationResult]]]] = {}
    for claim, result in all_selected:
        scope: tuple[Any, ...] = (
            claim.subject, claim.asset_id, claim.mapping_id, claim.claim_key, claim.timeframe,
        )
        if claim.claim_key.startswith("announcement.") or claim.claim_key == "onchain.transaction_hash":
            scope += (claim.event_at,)
        observed_at = _timestamp(claim.observed_at)
        current = latest_by_scope.get(scope)
        if current is None or observed_at > current[0]:
            latest_by_scope[scope] = (observed_at, [(claim, result)])
        elif observed_at == current[0]:
            current[1].append((claim, result))
    selected = [
        item
        for _, latest_items in latest_by_scope.values()
        for item in latest_items
    ]
    historical_omitted = len(all_selected) - len(selected)
    verified = [(claim, result) for claim, result in selected
                if result.state in {"VERIFIED", "CORROBORATED"}]
    nonfactual = [(claim, result) for claim, result in selected
                  if result.state not in {"VERIFIED", "CORROBORATED"}
                  and claim.claim_type in {"ESTIMATE", "ANALYST_INTERPRETATION", "HYPOTHESIS"}]
    unresolved = [(claim, result) for claim, result in selected
                  if result.state not in {"VERIFIED", "CORROBORATED"}
                  and claim.claim_type not in {"ESTIMATE", "ANALYST_INTERPRETATION", "HYPOTHESIS"}]
    lines = [
        "<<<CLAIM_VERIFICATION_REGISTER_START>>>",
        f"VERIFIED_COUNT: {len(verified)}",
        f"UNRESOLVED_COUNT: {len(unresolved)}",
        f"QUALIFIED_NONFACTUAL_COUNT: {len(nonfactual)}",
        "CLAIM VERIFICATION REGISTER (deterministic; model confidence is not evidence)",
        "Coverage: exact structured market/announcement claims, persisted source assertions, and explicitly qualified analysis.",
        f"HISTORICAL_CLAIMS_OMITTED: {historical_omitted}",
        "VERIFIED / CORROBORATED CLAIMS:",
    ]
    if not verified:
        lines.append("- None. No factual claim is currently approved by this registry.")
    for claim, result in verified[:30]:
        attribution = "Attribute this as a source assertion." if claim.claim_type == "SOURCE_ASSERTION" else ""
        lines.append(
            f"- [{result.state}/{claim.claim_type}] {claim.text} "
            f"(claim ID: {claim.claim_id}; evidence IDs: {', '.join(result.supporting_evidence_ids)}) {attribution}".strip()
        )
    lines.append("QUALIFIED NON-FACTUAL ANALYSIS (not evidence; label explicitly as analysis/estimate):")
    if not nonfactual:
        lines.append("- None.")
    for claim, result in nonfactual[:30]:
        lines.append(f"- [{claim.claim_type}] {claim.text}")
    lines.append("UNRESOLVED / PROHIBITED AS FACT:")
    if not unresolved:
        lines.append("- None.")
    for claim, result in unresolved[:30]:
        issue_text = ", ".join(result.issues) or "No accepted evidence link"
        lines.append(f"- [{result.state}/{claim.claim_type}] {claim.text} (issues: {issue_text})")
    if len(unresolved) > 30:
        lines.append(f"- {len(unresolved) - 30} additional unresolved claims omitted from this prompt view.")
    lines.extend((
        "RULE: Use only VERIFIED or CORROBORATED claims as factual statements.",
        "Attribute SOURCE_ASSERTION claims to the named source; do not upgrade the source's assertion into independently established truth.",
        "Do not state UNVERIFIED, CONTRADICTED, STALE or UNCLASSIFIED claims as facts; any such unresolved claim blocks publication.",
        "QUALIFIED NON-FACTUAL ANALYSIS is not evidence: use it only when clearly labelled as analysis, estimate or hypothesis, and never convert it into a factual assertion.",
        "<<<CLAIM_VERIFICATION_REGISTER_END>>>",
    ))
    return "\n".join(lines)


class ClaimRegistryStore:
    """Append-only SQLite audit store for claim-verification snapshots."""

    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise ValueError("ClaimRegistryStore requires an existing SQLite connection")
        self.connection = connection
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS layer1_claim_verification_runs (
                verification_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                claim_count INTEGER NOT NULL,
                verified_count INTEGER NOT NULL,
                corroborated_count INTEGER NOT NULL,
                unresolved_count INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            )
        """)
        self.connection.commit()

    def save(self, registry: ClaimRegistry) -> str:
        payload = json.dumps(registry.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        verification_id = _digest(payload)
        states = [result.state for result in registry.results]
        created_at = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO layer1_claim_verification_runs "
                "(verification_id, created_at, claim_count, verified_count, corroborated_count, unresolved_count, payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    verification_id, created_at, len(registry.claims),
                    sum(state == "VERIFIED" for state in states),
                    sum(state == "CORROBORATED" for state in states),
                    len(registry.unresolved_issues), payload,
                ),
            )
        return verification_id

    def load_by_verification_id(self, verification_id: str) -> Optional[dict[str, Any]]:
        if (not isinstance(verification_id, str) or len(verification_id) != 64
                or any(char not in "0123456789abcdef" for char in verification_id)):
            raise ValueError("claim registry verification ID must be lowercase SHA-256")
        row = self.connection.execute(
            "SELECT verification_id, payload_json FROM layer1_claim_verification_runs "
            "WHERE verification_id=?",
            (verification_id,),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[1])
        verify_claim_registry_payload(row[0], payload, ensure_ascii=True)
        return {"verification_id": row[0], "payload": payload}

    def load_latest(self) -> Optional[dict[str, Any]]:
        row = self.connection.execute(
            "SELECT verification_id FROM layer1_claim_verification_runs "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return self.load_by_verification_id(row[0])
