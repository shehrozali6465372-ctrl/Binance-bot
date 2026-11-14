"""Deterministic pre-media content verification (Module 18)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from layer1.evidence_verification import ClaimRegistry


TRADE_INSTRUCTION_PATTERNS = (
    re.compile(r"\b(?:you should|we recommend|i recommend)\s+(?:buy|sell|short|long)\b", re.I),
    re.compile(r"\b(?:buy|sell|short|long)\s+(?:now|today|immediately|this coin|this token)\b", re.I),
    re.compile(r"\b(?:entry price|stop[- ]loss|take[- ]profit|price target)\b", re.I),
    re.compile(r"\bguaranteed\s+(?:profit|return|gain)\b", re.I),
    re.compile(r"\brisk[- ]free\b|\b100%\s+(?:sure|guaranteed)\b", re.I),
)


@dataclass(frozen=True)
class ContentVerificationResult:
    status: str
    draft_hash: str
    asset_id: str
    symbol: str
    approved_claim_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    validation_version: str = "content-verification-v1"


class ContentVerificationEngine:
    """Deterministic gate. It does not use an LLM to overrule failed checks."""

    def validate(
        self,
        content: str,
        *,
        registry: ClaimRegistry,
        symbol: str,
        asset_id: str,
        numeric_validator: Optional[Callable[[str], bool]] = None,
    ) -> ContentVerificationResult:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("content verification requires non-empty draft text")
        if not isinstance(registry, ClaimRegistry):
            raise TypeError("content verification requires a typed ClaimRegistry")
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z0-9]{2,20}", symbol.strip()):
            raise ValueError("content verification requires a valid asset ticker")
        if not isinstance(asset_id, str) or not asset_id.startswith("coingecko:"):
            raise ValueError("content verification requires canonical CoinGecko asset identity")

        symbol = symbol.upper()
        from datetime import datetime
        result_by_claim = {result.claim_id: result for result in registry.results}
        latest_by_scope = {}
        for claim in registry.claims:
            if claim.asset_id not in {None, asset_id}:
                continue
            scope = (
                claim.subject, claim.asset_id, claim.mapping_id,
                claim.claim_key, claim.timeframe,
            )
            if claim.claim_key.startswith("announcement.") or claim.claim_key == "onchain.transaction_hash":
                scope += (claim.event_at,)
            observed = datetime.fromisoformat(claim.observed_at.replace("Z", "+00:00"))
            current = latest_by_scope.get(scope)
            if current is None or observed > current[0]:
                latest_by_scope[scope] = (observed, [(claim, result_by_claim.get(claim.claim_id))])
            elif observed == current[0]:
                current[1].append((claim, result_by_claim.get(claim.claim_id)))
        scoped = [
            (claim, result)
            for _, latest_items in latest_by_scope.values()
            for claim, result in latest_items
        ]
        verified_pairs = [
            (claim, result) for claim, result in scoped
            if result is not None and result.state in {"VERIFIED", "CORROBORATED"}
        ]
        unresolved_pairs = [
            (claim, result) for claim, result in scoped
            if result is None or (
                result.state not in {"VERIFIED", "CORROBORATED"}
                and claim.claim_type not in {"ESTIMATE", "ANALYST_INTERPRETATION", "HYPOTHESIS"}
            )
        ]
        approved = tuple(sorted(claim.claim_id for claim, _ in verified_pairs))
        reasons: set[str] = set()
        if not approved:
            reasons.add("NO_VERIFIED_CLAIMS_FOR_CANONICAL_ASSET")
        if unresolved_pairs:
            reasons.add("UNRESOLVED_ASSET_CLAIMS_REMAIN")
        if any(result is not None and result.state == "CONTRADICTED"
               for _, result in unresolved_pairs):
            reasons.add("CONTRADICTED_ASSET_CLAIM")
        cashtags = {
            match.upper() for match in re.findall(r"\$([A-Za-z][A-Za-z0-9]{1,19})\b", content)
        }
        if cashtags != {symbol}:
            reasons.add("CASHTAG_ASSET_IDENTITY_MISMATCH")
        if any(pattern.search(content) for pattern in TRADE_INSTRUCTION_PATTERNS):
            reasons.add("PROHIBITED_TRADE_INSTRUCTION_OR_GUARANTEE")
        if numeric_validator is None or not numeric_validator(content):
            reasons.add("NUMERIC_CLAIM_GUARD_FAILED")
        return ContentVerificationResult(
            status="PASS" if not reasons else "REJECT",
            draft_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            asset_id=asset_id, symbol=symbol,
            approved_claim_ids=approved,
            reasons=tuple(sorted(reasons)),
        )
