"""Immutable, short-lived authorization for a single Binance Square publication attempt."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


def _draft_provenance_digest(
    draft_id: str, asset_id: str, content_hash: str,
    research_package_id: str, editorial_brief_id: str,
    approved_claim_ids: tuple[str, ...],
) -> str:
    payload = {
        "draft_id": draft_id, "asset_id": asset_id, "content_hash": content_hash,
        "research_package_id": research_package_id,
        "editorial_brief_id": editorial_brief_id,
        "approved_claim_ids": sorted(approved_claim_ids),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError("authorization timestamps must be ISO-8601") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("authorization timestamps must include timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class PublicationAuthorization:
    authorization_id: str
    symbol: str
    asset_id: str
    draft_id: str
    research_package_id: str
    editorial_brief_id: str
    event_id: str
    approved_claim_ids: tuple[str, ...]
    draft_provenance_hash: str
    content_hash: str
    image_hashes: tuple[str, ...]
    eligibility_snapshot_at: str
    eligibility_max_age_seconds: int
    event_state: str
    evidence_status: str
    text_validation_status: str
    visual_validation_status: str
    quota_reservation_id: str
    repetition_hard_hours: int
    duplicate_policy_passed: bool
    created_at: str
    expires_at: str

    def verify_integrity(self) -> bool:
        payload = asdict(self)
        supplied_id = payload.pop("authorization_id")
        expected = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return supplied_id == expected

    def validate_for_submission(
        self, *, symbol: str, asset_id: str, content: str,
        image_hashes: tuple[str, ...] | list[str], now: Optional[str] = None,
    ) -> tuple[str, ...]:
        reasons = []
        if symbol.upper() != self.symbol or asset_id != self.asset_id:
            reasons.append("ASSET_IDENTITY_CHANGED")
        if (
            not isinstance(self.draft_id, str) or not self.draft_id
            or not isinstance(self.research_package_id, str) or not self.research_package_id
            or not isinstance(self.editorial_brief_id, str) or not self.editorial_brief_id
            or not isinstance(self.event_id, str) or not self.event_id
            or not self.approved_claim_ids
        ):
            reasons.append("PERSISTED_DRAFT_PROVENANCE_MISSING")
        expected_provenance_hash = _draft_provenance_digest(
            self.draft_id, self.asset_id, self.content_hash,
            self.research_package_id, self.editorial_brief_id,
            self.approved_claim_ids,
        )
        if expected_provenance_hash != self.draft_provenance_hash:
            reasons.append("PERSISTED_DRAFT_PROVENANCE_TAMPERED")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if digest != self.content_hash:
            reasons.append("DRAFT_CONTENT_CHANGED")
        if tuple(sorted(image_hashes)) != self.image_hashes:
            reasons.append("IMAGE_ARTIFACT_CHANGED")
        current = _parse_time(now or datetime.now(timezone.utc).isoformat())
        if current >= _parse_time(self.expires_at):
            reasons.append("AUTHORIZATION_EXPIRED")
        if current < _parse_time(self.created_at):
            reasons.append("AUTHORIZATION_NOT_YET_VALID")
        eligibility_age = (current - _parse_time(self.eligibility_snapshot_at)).total_seconds()
        if eligibility_age < 0 or eligibility_age > self.eligibility_max_age_seconds:
            reasons.append("SPOT_ELIGIBILITY_SNAPSHOT_STALE")
        if self.event_state not in {"NO_EVENT", "CONFIRMED", "DEVELOPING"}:
            reasons.append("EVENT_STATE_NOT_PUBLISHABLE")
        if self.evidence_status != "VERIFIED":
            reasons.append("EVIDENCE_GATE_FAILED")
        if self.text_validation_status != "PASS":
            reasons.append("TEXT_VALIDATION_FAILED")
        expected_visual = "PASS" if self.image_hashes else "NOT_REQUIRED"
        if self.visual_validation_status != expected_visual:
            reasons.append("VISUAL_VALIDATION_FAILED")
        if not self.quota_reservation_id:
            reasons.append("QUOTA_NOT_RESERVED")
        if (isinstance(self.repetition_hard_hours, bool)
                or not isinstance(self.repetition_hard_hours, int)
                or not 1 <= self.repetition_hard_hours <= 168):
            reasons.append("DUPLICATE_POLICY_WINDOW_INVALID")
        if self.duplicate_policy_passed is not True:
            reasons.append("DUPLICATE_POLICY_FAILED")
        return tuple(sorted(set(reasons)))


class PublicationAuthorizationEngine:
    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("publication authorization requires the existing SQLite connection")
        self.connection = connection
        self.connection.execute("""
        CREATE TABLE IF NOT EXISTS publication_quota_reservations (
            reservation_id TEXT PRIMARY KEY,
            day_utc TEXT NOT NULL,
            symbol TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            authorization_id TEXT,
            attempt_id INTEGER
        )
        """)
        columns = {
            row[1] for row in self.connection.execute(
                "PRAGMA table_info(publication_quota_reservations)"
            ).fetchall()
        }
        if "attempt_id" not in columns:
            self.connection.execute(
                "ALTER TABLE publication_quota_reservations ADD COLUMN attempt_id INTEGER"
            )
        self.connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_publication_quota_attempt_unique "
            "ON publication_quota_reservations(attempt_id) WHERE attempt_id IS NOT NULL"
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_publication_quota_day_status "
            "ON publication_quota_reservations(day_utc, status)"
        )
        self.connection.commit()

    def reserve_daily_quota(
        self, *, symbol: str, daily_limit: int, now: Optional[str] = None,
    ) -> Optional[str]:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("quota reservation requires a symbol")
        if isinstance(daily_limit, bool) or not isinstance(daily_limit, int) or daily_limit < 1:
            raise ValueError("daily_limit must be a positive integer")
        timestamp = _parse_time(now or datetime.now(timezone.utc).isoformat())
        day = timestamp.date().isoformat()
        reservation_id = "quota:" + uuid.uuid4().hex
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            reservation_count = self.connection.execute(
                "SELECT COUNT(*) FROM publication_quota_reservations "
                "WHERE day_utc=? AND status IN "
                "('RESERVED','SUBMITTING','PUBLICATION_UNKNOWN','PUBLISHED_CONFIRMED')",
                (day,),
            ).fetchone()[0]
            try:
                analytics_count = self.connection.execute(
                    "SELECT COUNT(*) FROM post_analytics WHERE created_at >= ?",
                    (day,),
                ).fetchone()[0]
            except sqlite3.OperationalError:
                analytics_count = 0
            count = max(reservation_count, analytics_count)
            if count >= daily_limit:
                return None
            self.connection.execute(
                "INSERT INTO publication_quota_reservations "
                "(reservation_id, day_utc, symbol, status, created_at, updated_at) "
                "VALUES (?, ?, ?, 'RESERVED', ?, ?)",
                (reservation_id, day, symbol.upper(), timestamp.isoformat(), timestamp.isoformat()),
            )
        return reservation_id

    def authorize(
        self, *, symbol: str, asset_id: str, content: str,
        image_hashes: tuple[str, ...] | list[str],
        eligibility_snapshot_at: str, eligibility_max_age_seconds: int,
        event_state: str, evidence_status: str,
        text_validation_status: str, visual_validation_status: str,
        quota_reservation_id: str, repetition_hard_hours: int = 12,
        now: Optional[str] = None, ttl_seconds: int = 60,
    ) -> PublicationAuthorization:
        current = _parse_time(now or datetime.now(timezone.utc).isoformat())
        if not isinstance(content, str) or not content.strip():
            raise ValueError("authorization requires a non-empty exact draft")
        if (
            not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z0-9]{2,20}", symbol.strip())
            or not isinstance(asset_id, str)
            or not re.fullmatch(r"coingecko:[a-z0-9][a-z0-9-]{1,99}", asset_id)
        ):
            raise ValueError("authorization requires canonical asset identity")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 300:
            raise ValueError("authorization TTL must be between 1 and 300 seconds")
        if isinstance(eligibility_max_age_seconds, bool) or not isinstance(eligibility_max_age_seconds, int) or not 1 <= eligibility_max_age_seconds <= 600:
            raise ValueError("eligibility freshness bound must be between 1 and 600 seconds")
        if isinstance(repetition_hard_hours, bool) or not isinstance(repetition_hard_hours, int) or not 1 <= repetition_hard_hours <= 168:
            raise ValueError("repetition_hard_hours must be between 1 and 168")
        image_hashes = tuple(sorted(image_hashes))
        if len(set(image_hashes)) != len(image_hashes):
            raise ValueError("image hashes must be unique")
        if any(
            not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in image_hashes
        ):
            raise ValueError("image hashes must be SHA-256 hex digests")
        draft_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        try:
            persisted_draft = self.connection.execute(
                "SELECT draft_id, research_package_id, editorial_brief_id, "
                "approved_claim_ids_json, content FROM content_draft_versions "
                "WHERE content_hash=? AND asset_id=? ORDER BY version DESC LIMIT 1",
                (draft_hash, asset_id),
            ).fetchone()
        except sqlite3.OperationalError:
            raise ValueError("persisted draft provenance ledger is unavailable") from None
        if persisted_draft is None:
            raise ValueError("exact draft must be persisted with research and editorial provenance")
        if (
            persisted_draft[4] != content
            or not isinstance(persisted_draft[1], str) or not persisted_draft[1]
            or not isinstance(persisted_draft[2], str) or not persisted_draft[2]
        ):
            raise ValueError("persisted draft provenance does not match the authorized content")
        try:
            editorial_brief = self.connection.execute(
                "SELECT event_id, research_package_id FROM editorial_brief_versions "
                "WHERE brief_id=?",
                (persisted_draft[2],),
            ).fetchone()
        except sqlite3.OperationalError:
            raise ValueError("persisted editorial event provenance ledger is unavailable") from None
        if editorial_brief is None or editorial_brief[1] != persisted_draft[1]:
            raise ValueError("persisted editorial brief does not match the draft research package")
        event_id = editorial_brief[0]
        try:
            approved_claim_ids = json.loads(persisted_draft[3])
        except (TypeError, json.JSONDecodeError):
            raise ValueError("persisted draft approved-claim provenance is invalid") from None
        if (
            not isinstance(approved_claim_ids, list) or not approved_claim_ids
            or any(not isinstance(value, str) or not value for value in approved_claim_ids)
        ):
            raise ValueError("persisted draft requires approved claim references")
        text_validation = self.connection.execute(
            "SELECT status FROM content_draft_validation_results WHERE draft_hash=? "
            "ORDER BY created_at DESC, validation_id DESC LIMIT 1",
            (draft_hash,),
        ).fetchone()
        if text_validation is None or text_validation[0] != "PASS":
            raise ValueError("persisted text validation is not PASS for this exact draft hash")
        for image_hash in image_hashes:
            visual_validation = self.connection.execute(
                "SELECT status, validation_version FROM visual_validation_results "
                "WHERE draft_hash=? AND image_hash=? "
                "ORDER BY created_at DESC, validation_id DESC LIMIT 1",
                (draft_hash, image_hash),
            ).fetchone()
            if (
                visual_validation is None or visual_validation[0] != "PASS"
                or visual_validation[1] != "visual-quality-v2"
            ):
                raise ValueError(
                    "persisted visual validation is not PASS from the current visual validation version "
                    "for this exact draft/image pair"
                )
        approved_claim_ids = tuple(sorted(approved_claim_ids))
        research_package_id = persisted_draft[1]
        editorial_brief_id = persisted_draft[2]
        draft_provenance_hash = _draft_provenance_digest(
            persisted_draft[0], asset_id, draft_hash,
            research_package_id, editorial_brief_id, approved_claim_ids,
        )
        duplicate_reasons = self._duplicate_policy_reasons(
            symbol=symbol.upper(), asset_id=asset_id, event_id=event_id,
            event_state=event_state, content_hash=draft_hash,
            quota_reservation_id=quota_reservation_id, now=current,
            repetition_hard_hours=repetition_hard_hours,
        )
        if duplicate_reasons:
            raise ValueError("publication authorization denied: " + ",".join(duplicate_reasons))
        candidate = PublicationAuthorization(
            authorization_id="", symbol=symbol.upper(), asset_id=asset_id,
            draft_id=persisted_draft[0],
            research_package_id=research_package_id,
            editorial_brief_id=editorial_brief_id,
            event_id=event_id,
            approved_claim_ids=approved_claim_ids,
            draft_provenance_hash=draft_provenance_hash,
            content_hash=draft_hash, image_hashes=image_hashes,
            eligibility_snapshot_at=_parse_time(eligibility_snapshot_at).isoformat(),
            eligibility_max_age_seconds=eligibility_max_age_seconds,
            event_state=event_state, evidence_status=evidence_status,
            text_validation_status=text_validation_status,
            visual_validation_status=visual_validation_status,
            quota_reservation_id=quota_reservation_id,
            repetition_hard_hours=repetition_hard_hours,
            duplicate_policy_passed=True,
            created_at=current.isoformat(),
            expires_at=(current + timedelta(seconds=ttl_seconds)).isoformat(),
        )
        reasons = candidate.validate_for_submission(
            symbol=symbol, asset_id=asset_id, content=content,
            image_hashes=image_hashes, now=current.isoformat(),
        )
        reasons = tuple(sorted(set(reasons) | set(self.validate_persisted_event_binding(candidate))))
        if reasons:
            raise ValueError("publication authorization denied: " + ",".join(reasons))
        payload = asdict(candidate)
        payload.pop("authorization_id")
        authorization_id = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        authorized = PublicationAuthorization(
            **{**asdict(candidate), "authorization_id": authorization_id}
        )
        with self.connection:
            reservation = self.connection.execute(
                "SELECT symbol, day_utc, status FROM publication_quota_reservations "
                "WHERE reservation_id=?",
                (quota_reservation_id,),
            ).fetchone()
            if (reservation is None or reservation[2] != "RESERVED"
                    or reservation[0] != symbol.upper()
                    or reservation[1] != current.date().isoformat()):
                raise ValueError("quota reservation is missing, mismatched or no longer available")
            cursor = self.connection.execute(
                "UPDATE publication_quota_reservations SET authorization_id=?, updated_at=? "
                "WHERE reservation_id=? AND status='RESERVED'",
                (authorization_id, current.isoformat(), quota_reservation_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("quota reservation is missing or no longer available")
        return authorized


    @staticmethod
    def _is_exceptional_event(event_type: str) -> bool:
        return event_type in {"new_listing", "launchpool", "megadrop", "airdrop", "delisting"}

    def _duplicate_policy_reasons(
        self, *, symbol: str, asset_id: str, event_id: str, event_state: str,
        content_hash: str, quota_reservation_id: str, now: datetime,
        repetition_hard_hours: int, exclude_idempotency_key: Optional[str] = None,
    ) -> tuple[str, ...]:
        """Evaluate cooldown, exact duplicates, unresolved attempts and competing reservations."""
        reasons: list[str] = []
        exceptional = False
        try:
            if event_state != "NO_EVENT":
                event = self.connection.execute(
                    "SELECT asset_id,event_type,state FROM layer1_event_lifecycle WHERE event_id=?",
                    (event_id,),
                ).fetchone()
                if event is None or event["asset_id"] != asset_id or event["state"] != event_state:
                    reasons.append("EVENT_LIFECYCLE_CHANGED")
                else:
                    exceptional = (
                        self._is_exceptional_event(str(event["event_type"] or ""))
                        and event["state"] in {"CONFIRMED", "DEVELOPING"}
                    )
            cutoff = now - timedelta(hours=repetition_hard_hours)
            posts = self.connection.execute(
                "SELECT created_at,content FROM posts WHERE UPPER(COALESCE(coin_symbol,''))=? "
                "ORDER BY id DESC LIMIT 100",
                (symbol,),
            ).fetchall()
            attempts = self.connection.execute(
                "SELECT idempotency_key,status,content_hash,created_at FROM publication_attempts "
                "WHERE UPPER(coin_symbol)=? AND status IN "
                "('SUBMITTING','PUBLICATION_UNKNOWN','PUBLISHED_CONFIRMED') ORDER BY id DESC LIMIT 100",
                (symbol,),
            ).fetchall()
            reservations = self.connection.execute(
                "SELECT reservation_id FROM publication_quota_reservations "
                "WHERE UPPER(symbol)=? AND reservation_id<>? "
                "AND status IN ('RESERVED','SUBMITTING','PUBLICATION_UNKNOWN')",
                (symbol, quota_reservation_id),
            ).fetchall()
        except sqlite3.OperationalError:
            return ("DUPLICATE_LEDGER_UNAVAILABLE",)

        for row in posts:
            try:
                created = _parse_time(row["created_at"])
            except (TypeError, ValueError):
                reasons.append("DUPLICATE_LEDGER_TIMESTAMP_INVALID")
                continue
            prior_content = row["content"] if isinstance(row["content"], str) else ""
            if hashlib.sha256(prior_content.encode("utf-8")).hexdigest() == content_hash:
                reasons.append("DUPLICATE_CONTENT_ALREADY_PUBLISHED")
            if not exceptional and created >= cutoff:
                reasons.append("RECENT_POST_COOLDOWN")

        for row in attempts:
            if exclude_idempotency_key and row["idempotency_key"] == exclude_idempotency_key:
                continue
            if row["status"] in {"SUBMITTING", "PUBLICATION_UNKNOWN"}:
                reasons.append("UNRESOLVED_PUBLICATION_ATTEMPT")
                continue
            if row["content_hash"] == content_hash:
                reasons.append("DUPLICATE_CONTENT_ALREADY_PUBLISHED")
            try:
                created = _parse_time(row["created_at"])
            except (TypeError, ValueError):
                reasons.append("DUPLICATE_LEDGER_TIMESTAMP_INVALID")
                continue
            if not exceptional and created >= cutoff:
                reasons.append("RECENT_POST_COOLDOWN")

        if reservations:
            reasons.append("COMPETING_ACTIVE_QUOTA_RESERVATION")
        return tuple(sorted(set(reasons)))

    def validate_persisted_duplicate_policy(
        self, authorization: PublicationAuthorization, *,
        now: Optional[str] = None, exclude_idempotency_key: Optional[str] = None,
    ) -> tuple[str, ...]:
        current = _parse_time(now or datetime.now(timezone.utc).isoformat())
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            return self._duplicate_policy_reasons(
                symbol=authorization.symbol, asset_id=authorization.asset_id,
                event_id=authorization.event_id, event_state=authorization.event_state,
                content_hash=authorization.content_hash,
                quota_reservation_id=authorization.quota_reservation_id,
                now=current, repetition_hard_hours=authorization.repetition_hard_hours,
                exclude_idempotency_key=exclude_idempotency_key,
            )

    def validate_persisted_event_binding(
        self, authorization: PublicationAuthorization,
    ) -> tuple[str, ...]:
        """Recheck the exact immutable editorial-event link against current SQLite state."""
        reasons: list[str] = []
        try:
            brief = self.connection.execute(
                "SELECT event_id, research_package_id FROM editorial_brief_versions WHERE brief_id=?",
                (authorization.editorial_brief_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return ("EDITORIAL_EVENT_LEDGER_UNAVAILABLE",)
        if brief is None:
            return ("EDITORIAL_BRIEF_MISSING",)
        if brief[0] != authorization.event_id:
            reasons.append("EDITORIAL_EVENT_IDENTITY_CHANGED")
        if brief[1] != authorization.research_package_id:
            reasons.append("EDITORIAL_RESEARCH_PACKAGE_CHANGED")
        if authorization.event_state == "NO_EVENT":
            return tuple(sorted(set(reasons)))
        try:
            event = self.connection.execute(
                "SELECT asset_id, state FROM layer1_event_lifecycle WHERE event_id=?",
                (authorization.event_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return tuple(sorted(set(reasons) | {"EVENT_LIFECYCLE_LEDGER_UNAVAILABLE"}))
        if event is None:
            reasons.append("EVENT_LIFECYCLE_RECORD_MISSING")
        else:
            if event[0] != authorization.asset_id:
                reasons.append("EVENT_ASSET_IDENTITY_CHANGED")
            if event[1] != authorization.event_state:
                reasons.append("EVENT_LIFECYCLE_CHANGED_AFTER_AUTHORIZATION")
            if event[1] not in {"CONFIRMED", "DEVELOPING"}:
                reasons.append("EVENT_STATE_NOT_PUBLISHABLE")
        return tuple(sorted(set(reasons)))

    def bind_attempt(self, reservation_id: str, attempt_id: int) -> None:
        if isinstance(attempt_id, bool) or not isinstance(attempt_id, int) or attempt_id < 1:
            raise ValueError("publication attempt ID must be a positive integer")
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE publication_quota_reservations SET attempt_id=?, updated_at=? "
                "WHERE reservation_id=? AND status='RESERVED' AND attempt_id IS NULL",
                (attempt_id, datetime.now(timezone.utc).isoformat(), reservation_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("quota reservation cannot be bound to this publication attempt")

    def quota_status(self, reservation_id: str) -> Optional[str]:
        row = self.connection.execute(
            "SELECT status FROM publication_quota_reservations WHERE reservation_id=?",
            (reservation_id,),
        ).fetchone()
        return row[0] if row else None

    def mark_quota_status(self, reservation_id: str, status: str) -> None:
        allowed = {"SUBMITTING", "PUBLICATION_UNKNOWN", "PUBLISHED_CONFIRMED", "FAILED_CONFIRMED", "RELEASED"}
        if status not in allowed:
            raise ValueError("invalid quota reservation status")
        transitions = {
            "RESERVED": {"SUBMITTING", "RELEASED"},
            "SUBMITTING": {"PUBLICATION_UNKNOWN", "PUBLISHED_CONFIRMED", "FAILED_CONFIRMED"},
            "PUBLICATION_UNKNOWN": {"PUBLISHED_CONFIRMED", "FAILED_CONFIRMED"},
            "PUBLISHED_CONFIRMED": set(),
            "FAILED_CONFIRMED": set(),
            "RELEASED": set(),
        }
        with self.connection:
            row = self.connection.execute(
                "SELECT status FROM publication_quota_reservations WHERE reservation_id=?",
                (reservation_id,),
            ).fetchone()
            if row is None:
                raise ValueError("quota reservation not found")
            current = row[0]
            if status == current:
                return
            if status not in transitions.get(current, set()):
                raise ValueError("illegal quota reservation transition")
            self.connection.execute(
                "UPDATE publication_quota_reservations SET status=?, updated_at=? "
                "WHERE reservation_id=? AND status=?",
                (status, datetime.now(timezone.utc).isoformat(), reservation_id, current),
            )
