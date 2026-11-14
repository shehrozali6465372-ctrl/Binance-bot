"""Evidence-traceable editorial brief selection and versioning (Module 16)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any

from layer1.research_package import ResearchPackage


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class EditorialBrief:
    event_id: str
    angle_id: str
    brief_id: str
    version: int
    research_package_id: str
    research_question: str
    format: str
    angle: str
    audience: str
    tone: str
    min_words: int
    max_words: int
    outline: tuple[str, ...]
    approved_claim_ids: tuple[str, ...]
    prohibited_claims: tuple[str, ...]
    uncertainty_notes: tuple[str, ...]
    status: str
    brief_hash: str
    policy_version: str

    def render(self) -> str:
        lines = [
            "<<<EDITORIAL_BRIEF_START>>>",
            "EDITORIAL_BRIEF_STATUS: " + self.status,
            "EDITORIAL_BRIEF_ID: " + self.brief_id,
            "EDITORIAL_BRIEF_VERSION: " + str(self.version),
            "EDITORIAL_FORMAT: " + self.format,
            "EDITORIAL_ANGLE: " + self.angle,
            "CENTRAL_QUESTION: " + self.research_question,
            "AUDIENCE: " + self.audience,
            "TONE: " + self.tone,
            f"LENGTH: {self.min_words}-{self.max_words} words",
            "OUTLINE:",
        ]
        lines.extend(f"{index + 1}. {item}" for index, item in enumerate(self.outline))
        lines.append("APPROVED_CLAIM_IDS: " + ",".join(self.approved_claim_ids))
        lines.append("PROHIBITED_CLAIMS:")
        lines.extend("- " + item for item in self.prohibited_claims) if self.prohibited_claims else lines.append("- None.")
        lines.append("UNCERTAINTY:")
        lines.extend("- " + item for item in self.uncertainty_notes) if self.uncertainty_notes else lines.append("- None recorded.")
        lines.append("BRIEF_HASH: " + self.brief_hash)
        lines.append("<<<EDITORIAL_BRIEF_END>>>")
        return "\n".join(lines)


class EditorialBriefStore:
    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("editorial brief store requires SQLite connection")
        self.connection = connection
        self.connection.execute("""
        CREATE TABLE IF NOT EXISTS editorial_brief_versions (
            event_id TEXT NOT NULL,
            angle_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            brief_id TEXT NOT NULL UNIQUE,
            research_package_id TEXT NOT NULL,
            brief_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(event_id, angle_id, version),
            UNIQUE(event_id, angle_id, brief_hash)
        )
        """)
        self.connection.commit()

    def has_angle(self, event_id: str, angle_id: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM editorial_brief_versions WHERE event_id=? AND angle_id=? LIMIT 1",
            (event_id, angle_id),
        ).fetchone() is not None

    def save(self, brief: EditorialBrief) -> EditorialBrief:
        if brief.status != "READY":
            raise ValueError("only a READY editorial brief may be persisted")
        with self.connection:
            existing = self.connection.execute(
                "SELECT version, brief_id FROM editorial_brief_versions "
                "WHERE event_id=? AND angle_id=? AND brief_hash=?",
                (brief.event_id, brief.angle_id, brief.brief_hash),
            ).fetchone()
            if existing:
                return replace(brief, version=existing[0], brief_id=existing[1])
            current = self.connection.execute(
                "SELECT COALESCE(MAX(version),0) FROM editorial_brief_versions "
                "WHERE event_id=? AND angle_id=?",
                (brief.event_id, brief.angle_id),
            ).fetchone()[0]
            version = int(current) + 1
            brief_id = _digest({
                "event_id": brief.event_id, "angle_id": brief.angle_id,
                "version": version, "brief_hash": brief.brief_hash,
            })
            saved = replace(brief, version=version, brief_id=brief_id)
            self.connection.execute(
                "INSERT INTO editorial_brief_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (saved.event_id, saved.angle_id, saved.version, saved.brief_id,
                 saved.research_package_id, saved.brief_hash,
                 json.dumps(asdict(saved), sort_keys=True, separators=(",", ":")),
                 datetime.now(timezone.utc).isoformat()),
            )
        return saved


class EditorialStrategyEngine:
    """Selects an evidence-matched angle; no generic breaking-news styling."""

    def build(
        self,
        package: ResearchPackage,
        *,
        event_id: str | None = None,
        store: EditorialBriefStore | None = None,
        materially_new: bool = False,
        audience: str = "Binance Square readers",
        tone: str = "analytical, accessible and cautious",
        min_words: int = 50,
        max_words: int = 180,
        policy_version: str = "editorial-policy-v1",
    ) -> EditorialBrief:
        if not isinstance(package, ResearchPackage):
            raise TypeError("editorial strategy requires a typed ResearchPackage")
        if package.completeness != "READY":
            raise ValueError("editorial brief cannot be built from incomplete research")
        if isinstance(min_words, bool) or isinstance(max_words, bool) or not 1 <= min_words <= max_words <= 1000:
            raise ValueError("editorial length bounds are invalid")
        if not audience.strip() or not tone.strip() or not policy_version.strip():
            raise ValueError("editorial audience, tone and policy version are required")

        keys = {str(item.get("claim_key") or "") for item in package.verified_facts}
        has_event = any(key.startswith("announcement.") for key in keys)
        has_onchain = any(key.startswith("onchain.") for key in keys)
        if has_event and any(state in {"CONFIRMED", "DEVELOPING"} for state in package.event_states):
            format_name = "EVENT_UPDATE"
            angle = "Explain the confirmed event, verified context and what remains unknown"
            outline = (
                "State the verified event and attribute the announcement to its source",
                "Explain the independently verified market context",
                "Separate confirmed details from unknown or unverified information",
                "Discuss risks, timing uncertainty and alternative explanations",
            )
        elif has_onchain:
            format_name = "ONCHAIN_CONTEXT"
            angle = "Explain the verified on-chain observation without inferring intent"
            outline = (
                "Describe the verified on-chain observation and its scope",
                "Explain the mapping and measurement limitations",
                "Compare with verified market context where available",
                "State what the data cannot establish",
            )
        else:
            format_name = "MARKET_MOVEMENT_EXPLAINER"
            angle = "Explain the verified market movement without inventing a catalyst"
            outline = (
                "State the verified market observations and data cutoff",
                "Explain the evidence-backed context and relevant changes",
                "Separate correlation from causation",
                "Describe uncertainty and material risks",
            )

        event_key = event_id or package.research_key
        angle_id = _digest({
            "event_id": event_key, "format": format_name,
            "question": package.research_question.casefold(),
        })
        duplicate = bool(store and store.has_angle(event_key, angle_id))
        if duplicate and not materially_new:
            status = "REJECT"
        else:
            status = "READY"
        prohibited = tuple(sorted({
            item["text"] for item in package.unknown_claims + package.disputed_claims
        }))
        uncertainty = tuple(sorted({
            item["text"] for item in package.inferences
        } | set(package.gaps)))
        approved_ids = tuple(sorted(item["claim_id"] for item in package.verified_facts))
        payload = {
            "event_id": event_key, "angle_id": angle_id,
            "research_package_id": package.package_id,
            "research_question": package.research_question,
            "format": format_name, "angle": angle, "audience": audience,
            "tone": tone, "min_words": min_words, "max_words": max_words,
            "outline": outline, "approved_claim_ids": approved_ids,
            "prohibited_claims": prohibited, "uncertainty_notes": uncertainty,
            "status": status, "policy_version": policy_version,
        }
        brief_hash = _digest(payload)
        return EditorialBrief(
            event_id=event_key, angle_id=angle_id,
            brief_id=brief_hash, version=0,
            research_package_id=package.package_id,
            research_question=package.research_question,
            format=format_name, angle=angle, audience=audience, tone=tone,
            min_words=min_words, max_words=max_words, outline=outline,
            approved_claim_ids=approved_ids, prohibited_claims=prohibited,
            uncertainty_notes=uncertainty, status=status,
            brief_hash=brief_hash, policy_version=policy_version,
        )
