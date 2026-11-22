"""PostgreSQL persistence primitives for publication safety (Module 21).

This backend is explicit opt-in: callers must supply a DSN and apply the
checked-in publication migration. It never reads environment variables or
changes the existing SQLite default publisher.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlsplit
from pathlib import Path
from typing import Optional


_QUOTA_TRANSITIONS = {
    "RESERVED": {"SUBMITTING", "RELEASED"},
    "SUBMITTING": {"PUBLICATION_UNKNOWN", "PUBLISHED_CONFIRMED", "FAILED_CONFIRMED"},
    "PUBLICATION_UNKNOWN": {"PUBLISHED_CONFIRMED", "FAILED_CONFIRMED"},
    "PUBLISHED_CONFIRMED": set(),
    "FAILED_CONFIRMED": set(),
    "RELEASED": set(),
}
_ATTEMPT_TRANSITIONS = {
    "SUBMITTING": {"PUBLICATION_UNKNOWN", "PUBLISHED_CONFIRMED", "FAILED_CONFIRMED"},
    "PUBLICATION_UNKNOWN": {"PUBLISHED_CONFIRMED", "FAILED_CONFIRMED"},
    "PUBLISHED_CONFIRMED": set(),
    "FAILED_CONFIRMED": set(),
}
_ACTIVE_QUOTA_STATES = (
    "RESERVED", "SUBMITTING", "PUBLICATION_UNKNOWN", "PUBLISHED_CONFIRMED",
)


def _quota_usage_count(reservation_count: int, untracked_analytics_count: int) -> int:
    """Count active reservations plus legacy analytics not mirrored by attempts."""
    values = (reservation_count, untracked_analytics_count)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
        raise ValueError("quota counts must be non-negative integers")
    return reservation_count + untracked_analytics_count


def validate_quota_transition(current: str, target: str) -> bool:
    """Return whether a quota transition is legal; same-state is idempotent."""
    if not isinstance(current, str) or not isinstance(target, str):
        return False
    return current == target or target in _QUOTA_TRANSITIONS.get(current, set())


def validate_attempt_transition(current: str, target: str) -> bool:
    """Return whether a publication-attempt transition is legal; terminal states stay terminal."""
    if not isinstance(current, str) or not isinstance(target, str):
        return False
    return current == target or target in _ATTEMPT_TRANSITIONS.get(current, set())


def validate_reconciliation_source_status(status: str) -> bool:
    """Only unresolved submission states may be resolved by an operator.

    SUBMITTING is included because a process can die after durable reservation
    but before it records whether the remote request was accepted. It must never
    be retried automatically; an operator must verify the remote outcome.
    """
    return isinstance(status, str) and status in {"SUBMITTING", "PUBLICATION_UNKNOWN"}


def validate_attempt_identity(existing: dict, symbol: str, content_hash: str) -> bool:
    """Reject reuse of one idempotency key for a different symbol or content digest."""
    if not isinstance(existing, dict):
        raise ValueError("existing publication attempt record is invalid")
    normalized_symbol = symbol.upper().strip() if isinstance(symbol, str) else ""
    if existing.get("coin_symbol") != normalized_symbol or existing.get("content_hash") != content_hash:
        raise ValueError("idempotency key is already bound to different publication content")
    return True


def validate_attempt_completion(
    *, current_status: str, target_status: str, existing_remote_id: str,
    existing_share_link: str, remote_post_id: str, share_link: str,
) -> bool:
    """Validate publication identity across unknown and terminal transitions."""
    if not validate_attempt_transition(current_status, target_status):
        raise ValueError("illegal publication attempt transition")
    values = (existing_remote_id, existing_share_link, remote_post_id, share_link)
    if any(not isinstance(value, str) for value in values):
        raise ValueError("publication identity fields must be strings")
    known_id = existing_remote_id.strip()
    supplied_id = remote_post_id.strip()
    known_link = existing_share_link.strip()
    supplied_link = share_link.strip()
    if known_id and supplied_id and known_id != supplied_id:
        raise ValueError("supplied remote post ID conflicts with the ID already recorded")
    if known_link and supplied_link and known_link != supplied_link:
        raise ValueError("supplied share link conflicts with the link already recorded")
    final_id = supplied_id or known_id
    final_link = supplied_link or known_link
    if target_status == "PUBLISHED_CONFIRMED" and not final_id:
        raise ValueError("confirmed publication requires a remote post ID with valid format")
    if target_status == "FAILED_CONFIRMED":
        if final_id:
            raise ValueError("cannot confirm failure while a remote post ID is recorded or supplied")
        if final_link:
            raise ValueError("cannot attach a share link to a confirmed failed publication")
    if target_status in {"PUBLICATION_UNKNOWN", "PUBLISHED_CONFIRMED"}:
        if final_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", final_id):
            raise ValueError("remote post ID has an invalid format")
        if final_link and not final_id:
            raise ValueError("share link cannot be recorded without a remote post ID")
        if final_link:
            try:
                parsed = urlsplit(final_link)
                match = re.fullmatch(r"/square/post/([A-Za-z0-9_-]{1,128})/?", parsed.path)
                valid = (parsed.scheme == "https" and parsed.hostname in {"www.binance.com", "binance.com"}
                         and parsed.port in (None, 443) and parsed.username is None and parsed.password is None
                         and not parsed.fragment and match is not None and match.group(1) == final_id)
            except (TypeError, ValueError):
                valid = False
            if not valid:
                raise ValueError("share link must be an HTTPS Binance Square post URL matching the remote post ID")
    return True


def _utc(value: Optional[str] = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, str):
        raise ValueError("timestamp must be ISO-8601")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("timestamp must be ISO-8601") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def verify_publication_postgres_migrations(dsn: str) -> tuple[str, ...]:
    """Verify the isolated Module 21 migration set without issuing DDL."""
    if not isinstance(dsn, str) or not dsn.strip():
        raise ValueError("an explicit PostgreSQL DSN is required")
    from .onchain_postgres import verify_postgres_migrations

    directory = Path(__file__).resolve().parent / "migrations" / "publication_postgresql"
    return verify_postgres_migrations(dsn, migrations_dir=str(directory))


def apply_publication_postgres_migrations(dsn: str) -> tuple[str, ...]:
    """Apply the isolated Module 21 migration set using the shared checksum runner."""
    if not isinstance(dsn, str) or not dsn.strip():
        raise ValueError("an explicit PostgreSQL DSN is required")
    from .onchain_postgres import apply_postgres_migrations

    directory = Path(__file__).resolve().parent / "migrations" / "publication_postgresql"
    return apply_postgres_migrations(dsn, migrations_dir=str(directory))


class PostgresPublicationStore:
    """Durable PostgreSQL quota, attempt and operator-reconciliation ledger.

    All state transitions are transactional and protected by row locks plus
    transaction-scoped advisory locks where a predicate spans multiple rows.
    """

    def __init__(self, dsn: str):
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("an explicit PostgreSQL DSN is required")
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                'PostgreSQL support requires the optional dependency: pip install "psycopg[binary]>=3.2,<4"'
            ) from exc
        self.conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
        self.conn.execute("SET TIME ZONE 'UTC'")

    def reserve_daily_quota(
        self, *, symbol: str, daily_limit: int, now: Optional[str] = None,
    ) -> Optional[str]:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("quota reservation requires a symbol")
        if isinstance(daily_limit, bool) or not isinstance(daily_limit, int) or daily_limit < 1:
            raise ValueError("daily_limit must be a positive integer")
        timestamp = _utc(now)
        day = timestamp.date()
        reservation_id = "quota:" + uuid.uuid4().hex
        with self.conn.transaction():
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                ("publication-quota:" + day.isoformat(),),
            )
            reservation_count = self.conn.execute(
                "SELECT COUNT(*) AS n FROM publication_quota_reservations "
                "WHERE day_utc=%s AND status = ANY(%s)",
                (day, list(_ACTIVE_QUOTA_STATES)),
            ).fetchone()["n"]
            # Analytics rows already represented by a durable publication attempt
            # are counted through that attempt's quota reservation. Count only
            # legacy/unlinked analytics here to avoid both under-counting disjoint
            # rows and double-counting the same confirmed publication.
            analytics_count = self.conn.execute(
                "SELECT COUNT(*) AS n FROM post_analytics pa "
                "WHERE pa.created_at::date=%s AND (pa.remote_post_id IS NULL OR NOT EXISTS ("
                "SELECT 1 FROM publication_attempts a WHERE a.remote_post_id=pa.remote_post_id))",
                (day,),
            ).fetchone()["n"]
            if _quota_usage_count(reservation_count, analytics_count) >= daily_limit:
                return None
            self.conn.execute(
                "INSERT INTO publication_quota_reservations "
                "(reservation_id,day_utc,symbol,status,created_at,updated_at) "
                "VALUES (%s,%s,%s,'RESERVED',%s,%s)",
                (reservation_id, day, symbol.upper(), timestamp, timestamp),
            )
        return reservation_id

    def mark_quota_status(self, reservation_id: str, status: str) -> None:
        if not isinstance(reservation_id, str) or not reservation_id.strip():
            raise ValueError("quota reservation ID is required")
        with self.conn.transaction():
            row = self.conn.execute(
                "SELECT status FROM publication_quota_reservations "
                "WHERE reservation_id=%s FOR UPDATE",
                (reservation_id,),
            ).fetchone()
            if row is None:
                raise ValueError("quota reservation not found")
            current = row["status"]
            if not validate_quota_transition(current, status):
                raise ValueError("illegal quota reservation transition")
            if current == status:
                return
            updated = self.conn.execute(
                "UPDATE publication_quota_reservations SET status=%s,updated_at=now() "
                "WHERE reservation_id=%s AND status=%s RETURNING reservation_id",
                (status, reservation_id, current),
            ).fetchone()
            if updated is None:
                raise RuntimeError("quota reservation changed during state transition")

    def bind_attempt(self, reservation_id: str, attempt_id: int) -> None:
        if isinstance(attempt_id, bool) or not isinstance(attempt_id, int) or attempt_id < 1:
            raise ValueError("publication attempt ID must be a positive integer")
        with self.conn.transaction():
            row = self.conn.execute(
                "UPDATE publication_quota_reservations SET attempt_id=%s,updated_at=now() "
                "WHERE reservation_id=%s AND status='RESERVED' AND attempt_id IS NULL "
                "RETURNING reservation_id",
                (attempt_id, reservation_id),
            ).fetchone()
            if row is None:
                raise ValueError("quota reservation cannot be bound to this publication attempt")

    def begin_authorized_attempt(self, *, authorization_id: str, idempotency_key: str, symbol: str, content_hash: str) -> Optional[dict]:
        if not _is_sha256(authorization_id): raise ValueError("authorization ID must be lowercase SHA-256")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip(): raise ValueError("idempotency key is required")
        if not isinstance(symbol, str) or not symbol.strip() or not _is_sha256(content_hash): raise ValueError("publication symbol and content hash are required")
        normalized_symbol = symbol.upper().strip()
        with self.conn.transaction():
            self.conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("publication-symbol:"+normalized_symbol,))
            auth = self.conn.execute("SELECT payload_json,quota_reservation_id,expires_at FROM publication_authorizations WHERE authorization_id=%s FOR SHARE", (authorization_id,)).fetchone()
            if auth is None: raise ValueError("persisted publication authorization not found")
            auth_payload = auth["payload_json"] if isinstance(auth["payload_json"], dict) else json.loads(auth["payload_json"])
            if auth["expires_at"] <= datetime.now(timezone.utc): raise ValueError("publication authorization has expired")
            if auth_payload.get("symbol") != normalized_symbol or auth_payload.get("content_hash") != content_hash:
                raise ValueError("publication attempt does not match its exact authorization")
            existing = self.conn.execute("SELECT * FROM publication_attempts WHERE idempotency_key=%s FOR UPDATE", (idempotency_key,)).fetchone()
            if existing:
                validate_attempt_identity(existing, normalized_symbol, content_hash)
                if existing["id"] is not None: return dict(existing)
            pending = self.conn.execute("SELECT * FROM publication_attempts WHERE coin_symbol=%s AND status IN ('SUBMITTING','PUBLICATION_UNKNOWN') ORDER BY id DESC LIMIT 1 FOR UPDATE", (normalized_symbol,)).fetchone()
            if pending: return dict(pending)
            quota = self.conn.execute("SELECT reservation_id,symbol,status,authorization_id FROM publication_quota_reservations WHERE reservation_id=%s FOR UPDATE", (auth["quota_reservation_id"],)).fetchone()
            if quota is None or quota["symbol"] != normalized_symbol or quota["status"] != "RESERVED" or quota["authorization_id"] != authorization_id:
                raise ValueError("authorization quota reservation is not exclusively bound and reserved")
            attempt = self.conn.execute("INSERT INTO publication_attempts (idempotency_key,coin_symbol,content_hash,status,created_at,updated_at) VALUES (%s,%s,%s,'SUBMITTING',now(),now()) RETURNING *", (idempotency_key,normalized_symbol,content_hash)).fetchone()
            self.conn.execute("UPDATE publication_quota_reservations SET status='SUBMITTING',attempt_id=%s,updated_at=now() WHERE reservation_id=%s", (attempt["id"],quota["reservation_id"]))
            return None


    @staticmethod
    def _exceptional_event_type(event_type: str) -> bool:
        return event_type in {"new_listing", "launchpool", "megadrop", "airdrop", "delisting"}

    def _duplicate_policy_reasons_in_transaction(
        self, *, symbol: str, asset_id: str, event_id: str, event_state: str,
        content_hash: str, quota_reservation_id: str, now: datetime,
        repetition_hard_hours: int, exclude_idempotency_key: Optional[str] = None,
    ) -> tuple[str, ...]:
        self.conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            ("publication-symbol:" + symbol.upper(),),
        )
        exceptional = False
        reasons = []
        event = self.conn.execute(
            "SELECT asset_id,event_type,state FROM layer1_event_lifecycle WHERE event_id=%s FOR SHARE",
            (event_id,),
        ).fetchone()
        if event_state == "NO_EVENT":
            if event is not None:
                reasons.append("EVENT_LIFECYCLE_STATE_MISMATCH")
        elif event is None or event["asset_id"] != asset_id or event["state"] != event_state:
            reasons.append("EVENT_LIFECYCLE_CHANGED")
        else:
            exceptional = (
                self._exceptional_event_type(str(event["event_type"] or ""))
                and event["state"] in {"CONFIRMED", "DEVELOPING"}
            )
        cutoff = now - __import__("datetime").timedelta(hours=repetition_hard_hours)
        posts = self.conn.execute(
            "SELECT created_at,content FROM posts WHERE UPPER(COALESCE(coin_symbol,''))=%s "
            "ORDER BY id DESC LIMIT 100",
            (symbol.upper(),),
        ).fetchall()
        attempts = self.conn.execute(
            "SELECT idempotency_key,status,content_hash,created_at FROM publication_attempts "
            "WHERE UPPER(coin_symbol)=%s AND status IN "
            "('SUBMITTING','PUBLICATION_UNKNOWN','PUBLISHED_CONFIRMED') ORDER BY id DESC LIMIT 100",
            (symbol.upper(),),
        ).fetchall()
        reservations = self.conn.execute(
            "SELECT reservation_id FROM publication_quota_reservations WHERE UPPER(symbol)=%s "
            "AND reservation_id<>%s AND status IN ('RESERVED','SUBMITTING','PUBLICATION_UNKNOWN')",
            (symbol.upper(), quota_reservation_id),
        ).fetchall()
        for row in posts:
            created = row["created_at"]
            if created.tzinfo is None:
                reasons.append("DUPLICATE_LEDGER_TIMESTAMP_INVALID")
                continue
            if hashlib.sha256(str(row["content"]).encode("utf-8")).hexdigest() == content_hash:
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
            created = row["created_at"]
            if created.tzinfo is None:
                reasons.append("DUPLICATE_LEDGER_TIMESTAMP_INVALID")
            elif not exceptional and created >= cutoff:
                reasons.append("RECENT_POST_COOLDOWN")
        if reservations:
            reasons.append("COMPETING_ACTIVE_QUOTA_RESERVATION")
        return tuple(sorted(set(reasons)))

    def validate_persisted_duplicate_policy(
        self, *, symbol: str, asset_id: str, event_id: str, event_state: str,
        content_hash: str, quota_reservation_id: str, now: Optional[datetime] = None,
        repetition_hard_hours: int = 12, exclude_idempotency_key: Optional[str] = None,
    ) -> tuple[str, ...]:
        if isinstance(repetition_hard_hours, bool) or not isinstance(repetition_hard_hours, int) or not 1 <= repetition_hard_hours <= 168:
            raise ValueError("repetition_hard_hours must be between 1 and 168")
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("duplicate policy clock must be timezone-aware")
        with self.conn.transaction():
            return self._duplicate_policy_reasons_in_transaction(
                symbol=symbol, asset_id=asset_id, event_id=event_id,
                event_state=event_state, content_hash=content_hash,
                quota_reservation_id=quota_reservation_id, now=current,
                repetition_hard_hours=repetition_hard_hours,
                exclude_idempotency_key=exclude_idempotency_key,
            )

    @contextmanager
    def authorized_submission_guard(
        self, *, authorization_id: str, idempotency_key: str, symbol: str, content_hash: str,
    ):
        """Hold event lifecycle serialization and provenance row locks through the POST.

        A row-level FOR SHARE lock cannot protect the NO_EVENT case because no row
        exists to lock. The event-scoped advisory lock also fences concurrent event
        insertion/update and remains held by this outer transaction while the caller
        performs the bounded HTTP request.
        """
        with self.conn.transaction():
            auth = self.conn.execute(
                "SELECT payload_json FROM publication_authorizations WHERE authorization_id=%s",
                (authorization_id,),
            ).fetchone()
            if auth is None:
                raise ValueError("persisted publication authorization not found")
            payload = auth["payload_json"] if isinstance(auth["payload_json"], dict) else json.loads(auth["payload_json"])
            event_id = payload.get("event_id")
            normalized_symbol = symbol.upper().strip() if isinstance(symbol, str) else ""
            if not normalized_symbol:
                raise ValueError("publication symbol is required")
            if not isinstance(event_id, str) or not event_id.strip():
                raise ValueError("persisted authorization event identity is invalid")
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("publication-symbol:" + normalized_symbol,),
            )
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("event-lifecycle:" + event_id,),
            )
            # Nested psycopg transaction becomes a savepoint. Locks acquired by
            # the validation remain held until this outer transaction exits.
            self.validate_authorized_attempt_before_submit(
                authorization_id=authorization_id, idempotency_key=idempotency_key,
                symbol=symbol, content_hash=content_hash,
            )
            yield

    def validate_authorized_attempt_before_submit(
        self, *, authorization_id: str, idempotency_key: str, symbol: str, content_hash: str,
    ) -> None:
        """Revalidate mutable provenance and lifecycle immediately before the network POST."""
        if not _is_sha256(authorization_id) or not _is_sha256(content_hash):
            raise ValueError("authorization and content digests are required")
        normalized_symbol = symbol.upper().strip() if isinstance(symbol, str) else ""
        with self.conn.transaction():
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("publication-symbol:" + normalized_symbol,),
            )
            auth = self.conn.execute(
                "SELECT payload_json,quota_reservation_id,expires_at FROM publication_authorizations "
                "WHERE authorization_id=%s FOR SHARE", (authorization_id,),
            ).fetchone()
            if auth is None or auth["expires_at"] <= datetime.now(timezone.utc):
                raise ValueError("persisted publication authorization is missing or expired")
            payload = auth["payload_json"] if isinstance(auth["payload_json"], dict) else json.loads(auth["payload_json"])
            if payload.get("symbol") != normalized_symbol or payload.get("content_hash") != content_hash:
                raise ValueError("attempt identity no longer matches persisted authorization")
            attempt = self.conn.execute(
                "SELECT id,status,coin_symbol,content_hash FROM publication_attempts "
                "WHERE idempotency_key=%s FOR UPDATE", (idempotency_key,),
            ).fetchone()
            if (attempt is None or attempt["status"] != "SUBMITTING"
                    or attempt["coin_symbol"] != normalized_symbol or attempt["content_hash"] != content_hash):
                raise ValueError("durable publication attempt is not in the submitting state")
            draft = self.conn.execute(
                "SELECT asset_id,content_hash,research_package_id,editorial_brief_id,approved_claim_ids_json "
                "FROM content_draft_versions WHERE draft_id=%s FOR SHARE", (payload["draft_id"],),
            ).fetchone()
            brief = self.conn.execute(
                "SELECT event_id,research_package_id FROM editorial_brief_versions WHERE brief_id=%s FOR SHARE",
                (payload["editorial_brief_id"],),
            ).fetchone()
            if (draft is None or brief is None or draft["asset_id"] != payload["asset_id"]
                    or draft["content_hash"] != content_hash
                    or draft["research_package_id"] != payload["research_package_id"]
                    or draft["editorial_brief_id"] != payload["editorial_brief_id"]
                    or brief["event_id"] != payload["event_id"]
                    or brief["research_package_id"] != payload["research_package_id"]):
                raise ValueError("draft/editorial provenance changed after authorization")
            claims = draft["approved_claim_ids_json"]
            if isinstance(claims, str): claims = json.loads(claims)
            if sorted(claims) != sorted(payload["approved_claim_ids"]):
                raise ValueError("approved claim provenance changed after authorization")
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("event-lifecycle:" + payload["event_id"],),
            )
            event = self.conn.execute(
                "SELECT asset_id,state FROM layer1_event_lifecycle WHERE event_id=%s FOR SHARE",
                (payload["event_id"],),
            ).fetchone()
            if payload["event_state"] == "NO_EVENT":
                if event is not None:
                    raise ValueError("event lifecycle exists for a NO_EVENT authorization")
            elif (event is None or event["asset_id"] != payload["asset_id"]
                    or event["state"] != payload["event_state"]
                    or event["state"] not in {"CONFIRMED", "DEVELOPING"}):
                raise ValueError("event lifecycle changed after authorization")
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (validation_advisory_lock_key(content_hash, None),),
            )
            for image_hash in sorted(set(payload["image_hashes"])):
                self.conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                    (validation_advisory_lock_key(content_hash, image_hash),),
                )
            text = self.conn.execute(
                "SELECT status FROM content_draft_validation_results WHERE draft_hash=%s "
                "ORDER BY created_at DESC,validation_id DESC LIMIT 1", (content_hash,),
            ).fetchone()
            if text is None or text["status"] != "PASS":
                raise ValueError("latest persisted text validation is no longer PASS")
            for image_hash in payload["image_hashes"]:
                artifact = self.conn.execute(
                    "SELECT 1 FROM image_generation_artifacts WHERE draft_hash=%s AND image_hash=%s",
                    (content_hash, image_hash),
                ).fetchone()
                visual = self.conn.execute(
                    "SELECT status,validation_version FROM visual_validation_results WHERE draft_hash=%s "
                    "AND image_hash=%s ORDER BY created_at DESC,validation_id DESC LIMIT 1",
                    (content_hash, image_hash),
                ).fetchone()
                if (artifact is None or visual is None or visual["status"] != "PASS"
                        or visual["validation_version"] != "visual-quality-v2"):
                    raise ValueError("latest persisted image artifact/visual validation is not publishable")
            quota = self.conn.execute(
                "SELECT status,authorization_id,attempt_id FROM publication_quota_reservations "
                "WHERE reservation_id=%s FOR UPDATE", (auth["quota_reservation_id"],),
            ).fetchone()
            if (quota is None or quota["status"] != "SUBMITTING"
                    or quota["authorization_id"] != authorization_id
                    or quota["attempt_id"] != attempt["id"]):
                raise ValueError("durable quota reservation is no longer bound to this attempt")
            duplicate_reasons = self._duplicate_policy_reasons_in_transaction(
                symbol=normalized_symbol, asset_id=payload["asset_id"],
                event_id=payload["event_id"], event_state=payload["event_state"],
                content_hash=content_hash, quota_reservation_id=auth["quota_reservation_id"],
                now=datetime.now(timezone.utc),
                repetition_hard_hours=payload["repetition_hard_hours"],
                exclude_idempotency_key=idempotency_key,
            )
            if duplicate_reasons:
                raise ValueError("persisted duplicate policy rejected submission: " + ",".join(duplicate_reasons))

    def finish_authorized_attempt(self, idempotency_key: str, status: str, *, post_id: str = "", share_link: str = "", http_status: Optional[int] = None, error: str = "") -> None:
        if status not in _ATTEMPT_TRANSITIONS: raise ValueError("invalid publication attempt status")
        with self.conn.transaction():
            attempt = self.conn.execute("SELECT id,status,remote_post_id,share_link FROM publication_attempts WHERE idempotency_key=%s FOR UPDATE", (idempotency_key,)).fetchone()
            if attempt is None: raise ValueError("publication attempt not found")
            validate_attempt_completion(
                current_status=attempt["status"], target_status=status,
                existing_remote_id=str(attempt["remote_post_id"] or ""),
                existing_share_link=str(attempt["share_link"] or ""),
                remote_post_id=post_id, share_link=share_link,
            )
            quota = self.conn.execute("SELECT reservation_id,status FROM publication_quota_reservations WHERE attempt_id=%s FOR UPDATE", (attempt["id"],)).fetchone()
            if quota is None: raise ValueError("publication attempt has no durable quota reservation")
            if not validate_quota_transition(quota["status"],status): raise ValueError("illegal quota reservation transition")
            self.conn.execute("UPDATE publication_attempts SET status=%s,remote_post_id=COALESCE(%s,remote_post_id),share_link=COALESCE(%s,share_link),http_status=COALESCE(%s,http_status),error=%s,updated_at=now() WHERE id=%s", (status,post_id or None,share_link or None,http_status,error[:1000] if error else None,attempt["id"]))
            self.conn.execute("UPDATE publication_quota_reservations SET status=%s,updated_at=now() WHERE reservation_id=%s", (status,quota["reservation_id"]))

    def begin_attempt(
        self, idempotency_key: str, symbol: str, content_hash: str,
    ) -> Optional[dict]:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency key is required")
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("publication symbol is required")
        if (not isinstance(content_hash, str) or len(content_hash) != 64
                or any(c not in "0123456789abcdef" for c in content_hash)):
            raise ValueError("content hash must be a lowercase SHA-256 digest")
        normalized_symbol = symbol.upper().strip()
        with self.conn.transaction():
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                ("publication-symbol:" + normalized_symbol,),
            )
            existing = self.conn.execute(
                "SELECT * FROM publication_attempts WHERE idempotency_key=%s FOR UPDATE",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                validate_attempt_identity(existing, normalized_symbol, content_hash)
                return dict(existing)
            pending = self.conn.execute(
                "SELECT * FROM publication_attempts WHERE coin_symbol=%s "
                "AND status IN ('SUBMITTING','PUBLICATION_UNKNOWN') ORDER BY id DESC LIMIT 1 FOR UPDATE",
                (normalized_symbol,),
            ).fetchone()
            if pending is not None:
                return dict(pending)
            inserted = self.conn.execute(
                "INSERT INTO publication_attempts "
                "(idempotency_key,coin_symbol,content_hash,status,created_at,updated_at) "
                "VALUES (%s,%s,%s,'SUBMITTING',now(),now()) "
                "ON CONFLICT (idempotency_key) DO NOTHING RETURNING *",
                (idempotency_key, normalized_symbol, content_hash),
            ).fetchone()
            if inserted is not None:
                return None
            existing = self.conn.execute(
                "SELECT * FROM publication_attempts WHERE idempotency_key=%s FOR UPDATE",
                (idempotency_key,),
            ).fetchone()
            if existing is None:
                raise RuntimeError("publication attempt insert conflict could not be resolved")
            validate_attempt_identity(existing, normalized_symbol, content_hash)
            return dict(existing)

    def finish_attempt(
        self, idempotency_key: str, status: str, *, post_id: str = "",
        share_link: str = "", http_status: Optional[int] = None, error: str = "",
    ) -> None:
        if not isinstance(status, str) or status not in _ATTEMPT_TRANSITIONS:
            raise ValueError("invalid publication attempt status")
        with self.conn.transaction():
            row = self.conn.execute(
                "SELECT status,remote_post_id,share_link FROM publication_attempts WHERE idempotency_key=%s FOR UPDATE",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                raise ValueError("publication attempt not found")
            current = row["status"]
            validate_attempt_completion(
                current_status=current, target_status=status,
                existing_remote_id=str(row["remote_post_id"] or ""),
                existing_share_link=str(row["share_link"] or ""),
                remote_post_id=post_id, share_link=share_link,
            )
            self.conn.execute(
                "UPDATE publication_attempts SET status=%s,"
                "remote_post_id=COALESCE(%s,remote_post_id),"
                "share_link=COALESCE(%s,share_link),"
                "http_status=COALESCE(%s,http_status),error=%s,updated_at=now() "
                "WHERE idempotency_key=%s",
                (status, post_id or None, share_link or None, http_status,
                 error[:1000] if error else None, idempotency_key),
            )

    def list_pending_attempts(self, limit: int = 100) -> list[dict]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows = self.conn.execute(
            "SELECT * FROM publication_attempts WHERE status IN "
            "('SUBMITTING','PUBLICATION_UNKNOWN') ORDER BY created_at,id LIMIT %s",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_attempt(self, attempt_id: int) -> Optional[dict]:
        if isinstance(attempt_id, bool) or not isinstance(attempt_id, int) or attempt_id < 1:
            raise ValueError("attempt_id must be a positive integer")
        row = self.conn.execute(
            "SELECT * FROM publication_attempts WHERE id=%s", (attempt_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def reconcile_attempt(
        self, *, attempt_id: int, new_status: str, reconciled_by: str,
        evidence: str, note: str, remote_post_id: str = "", share_link: str = "",
    ) -> None:
        if not isinstance(new_status, str) or new_status not in {"PUBLISHED_CONFIRMED", "FAILED_CONFIRMED"}:
            raise ValueError("reconciliation must resolve to a confirmed terminal state")
        if any(not isinstance(v, str) or not v.strip() for v in (reconciled_by, evidence, note)):
            raise ValueError("reconciliation requires operator, evidence and note")
        if isinstance(attempt_id, bool) or not isinstance(attempt_id, int) or attempt_id < 1:
            raise ValueError("attempt_id must be a positive integer")
        if not isinstance(remote_post_id, str) or not isinstance(share_link, str):
            raise ValueError("remote_post_id and share_link must be strings")
        reconciliation_id = uuid.uuid4().hex
        with self.conn.transaction():
            attempt = self.conn.execute(
                "SELECT id,status,remote_post_id,share_link FROM publication_attempts WHERE id=%s FOR UPDATE",
                (attempt_id,),
            ).fetchone()
            if attempt is None:
                raise ValueError("publication attempt not found")
            prior_status = attempt["status"]
            if not validate_reconciliation_source_status(prior_status):
                raise ValueError("only an unresolved publication attempt can be reconciled")
            if not validate_attempt_transition(prior_status, new_status):
                raise ValueError("illegal publication attempt reconciliation")
            existing_remote_id = str(attempt["remote_post_id"] or "")
            existing_share_link = str(attempt["share_link"] or "")
            if new_status == "FAILED_CONFIRMED" and existing_remote_id:
                raise ValueError("cannot confirm failure while a remote post ID is already recorded")
            if existing_remote_id and remote_post_id and existing_remote_id != remote_post_id:
                raise ValueError("supplied remote ID conflicts with the ID already stored in ledger")
            if new_status == "PUBLISHED_CONFIRMED" and not (remote_post_id.strip() or existing_remote_id):
                raise ValueError("confirmed publication requires the remote post ID")
            if existing_share_link and share_link and existing_share_link != share_link:
                raise ValueError("supplied share link conflicts with the link already stored in ledger")
            validate_attempt_completion(
                current_status=prior_status, target_status=new_status,
                existing_remote_id=existing_remote_id, existing_share_link=existing_share_link,
                remote_post_id=remote_post_id, share_link=share_link,
            )
            quota = self.conn.execute(
                "SELECT reservation_id,status FROM publication_quota_reservations "
                "WHERE attempt_id=%s FOR UPDATE",
                (attempt_id,),
            ).fetchone()
            if quota is None or quota["status"] not in {"SUBMITTING", "PUBLICATION_UNKNOWN"}:
                raise ValueError("matching active quota reservation is required for reconciliation")
            self.conn.execute(
                "UPDATE publication_attempts SET status=%s,remote_post_id=COALESCE(%s,remote_post_id),"
                "share_link=COALESCE(%s,share_link),reconciliation_note=%s,reconciliation_evidence=%s,reconciled_by=%s,"
                "reconciled_at=now(),updated_at=now() WHERE id=%s",
                (new_status, remote_post_id or None, share_link or None, note, evidence, reconciled_by, attempt_id),
            )
            self.conn.execute(
                "UPDATE publication_quota_reservations SET status=%s,updated_at=now() "
                "WHERE reservation_id=%s",
                (new_status, quota["reservation_id"]),
            )
            self.conn.execute(
                "INSERT INTO publication_reconciliation_events "
                "(reconciliation_id,attempt_id,prior_status,new_status,reconciled_by,evidence,note,created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,now())",
                (reconciliation_id, attempt_id, prior_status, new_status,
                 reconciled_by, evidence, note),
            )

    def observe_event_lifecycle(
        self, *, event_id: str, asset_id: str, source_id: str, event_type: str,
        revision_hash: str, first_published_at: str, first_observed_at: str,
        last_updated_at: str, effective_event_at: str, state: str,
        from_state: Optional[str], reason_code: str, evidence_refs: list[str], payload: dict,
    ) -> dict:
        return _observe_event_lifecycle(
            self, event_id=event_id, asset_id=asset_id, source_id=source_id,
            event_type=event_type, revision_hash=revision_hash,
            first_published_at=first_published_at, first_observed_at=first_observed_at,
            last_updated_at=last_updated_at, effective_event_at=effective_event_at,
            state=state, from_state=from_state, reason_code=reason_code,
            evidence_refs=evidence_refs, payload=payload,
        )

    def load_event_lifecycle(self, event_id: str) -> Optional[dict]:
        return _load_event_lifecycle(self, event_id)

    def sync_event_lifecycle_snapshot(self, sqlite_connection, event_id: str) -> None:
        """Import an exact SQLite lifecycle snapshot into the publication ledger.

        The foundation store remains SQLite, but this append-only mirror makes
        PostgreSQL authorization evaluate the same event identity and transition
        history. Existing PostgreSQL history must be an exact prefix; divergence
        fails closed rather than overwriting it.
        """
        event = sqlite_connection.execute(
            "SELECT event_id,asset_id,source_id,event_type,state,first_published_at,"
            "first_observed_at,last_updated_at,effective_event_at,latest_revision_hash,updated_at "
            "FROM layer1_event_lifecycle WHERE event_id=?", (event_id,),
        ).fetchone()
        if event is None:
            raise ValueError("SQLite event lifecycle snapshot is missing")
        revisions = sqlite_connection.execute(
            "SELECT revision_hash,source_published_at,source_updated_at,observed_at,evidence_ref,payload_json "
            "FROM layer1_event_revisions WHERE event_id=? ORDER BY observed_at,revision_hash", (event_id,),
        ).fetchall()
        transitions = sqlite_connection.execute(
            "SELECT from_state,to_state,reason_code,evidence_refs_json,transitioned_at "
            "FROM layer1_event_transitions WHERE event_id=? ORDER BY transition_id", (event_id,),
        ).fetchall()
        if not revisions or not transitions:
            raise ValueError("event lifecycle snapshot has no durable revision/transition history")
        with self.conn.transaction():
            self.conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("event-lifecycle:" + event_id,))
            current = self.conn.execute("SELECT * FROM layer1_event_lifecycle WHERE event_id=%s FOR UPDATE", (event_id,)).fetchone()
            identity = (event[1], event[2], event[3])
            if current is None:
                if transitions[0][0] is not None or transitions[0][1] != "DISCOVERED":
                    raise ValueError("event lifecycle history does not begin at DISCOVERED")
                self.conn.execute(
                    "INSERT INTO layer1_event_lifecycle (event_id,asset_id,source_id,event_type,state,first_published_at,first_observed_at,last_updated_at,effective_event_at,latest_revision_hash,updated_at) "
                    "VALUES (%s,%s,%s,%s,'DISCOVERED',%s,%s,%s,%s,%s,%s)",
                    (event_id, *identity, event[5], event[6], event[7], event[8], revisions[0][0], event[10]),
                )
                current_state = None
                existing_transitions = []
            else:
                if (current["asset_id"], current["source_id"], current["event_type"]) != identity:
                    raise ValueError("PostgreSQL event lifecycle identity conflicts with SQLite")
                rows = self.conn.execute(
                    "SELECT from_state,to_state,reason_code,evidence_refs_json,transitioned_at FROM layer1_event_transitions WHERE event_id=%s ORDER BY transition_id", (event_id,),
                ).fetchall()
                existing_transitions = []
                for row in rows:
                    refs = row["evidence_refs_json"] if isinstance(row["evidence_refs_json"], list) else json.loads(row["evidence_refs_json"])
                    existing_transitions.append((row["from_state"], row["to_state"], row["reason_code"], refs, row["transitioned_at"].isoformat()))
                current_state = current["state"]
            local_transitions = []
            for row in transitions:
                refs = json.loads(row[3]) if isinstance(row[3], str) else row[3]
                local_transitions.append((row[0], row[1], row[2], refs, _utc(row[4]).isoformat()))
            if existing_transitions != local_transitions[:len(existing_transitions)]:
                raise ValueError("PostgreSQL event transition history diverges from SQLite; refusing overwrite")
            for revision in revisions:
                payload = json.loads(revision[5]) if isinstance(revision[5], str) else revision[5]
                prior = self.conn.execute(
                    "SELECT payload_json FROM layer1_event_revisions WHERE event_id=%s AND revision_hash=%s FOR UPDATE",
                    (event_id, revision[0]),
                ).fetchone()
                if prior is not None:
                    saved = prior["payload_json"] if isinstance(prior["payload_json"], dict) else json.loads(prior["payload_json"])
                    if saved != payload:
                        raise ValueError("event revision identity conflicts across persistence backends")
                else:
                    self.conn.execute(
                        "INSERT INTO layer1_event_revisions (event_id,revision_hash,source_published_at,source_updated_at,observed_at,evidence_ref,payload_json) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)",
                        (event_id, revision[0], revision[1], revision[2], revision[3], revision[4], json.dumps(payload,sort_keys=True,separators=(",", ":"))),
                    )
            for transition in local_transitions[len(existing_transitions):]:
                if transition[0] != current_state:
                    raise ValueError("event lifecycle transition sequence is not contiguous")
                allowed = _EVENT_TRANSITIONS.get(current_state, set())
                if transition[1] not in allowed:
                    raise ValueError("event lifecycle snapshot contains an illegal transition")
                self.conn.execute(
                    "INSERT INTO layer1_event_transitions (event_id,from_state,to_state,reason_code,evidence_refs_json,transitioned_at) VALUES (%s,%s,%s,%s,%s::jsonb,%s)",
                    (event_id, transition[0], transition[1], transition[2], json.dumps(transition[3],separators=(",", ":")), transition[4]),
                )
                current_state = transition[1]
            if current_state != event[4]:
                raise ValueError("PostgreSQL event lifecycle final state does not match SQLite")
            self.conn.execute(
                "UPDATE layer1_event_lifecycle SET state=%s,last_updated_at=%s,effective_event_at=%s,latest_revision_hash=%s,updated_at=%s WHERE event_id=%s",
                (event[4], event[7], event[8], event[9], event[10], event_id),
            )

    def save_publication_authorization(self, authorization) -> str:
        from dataclasses import asdict
        if not hasattr(authorization, "verify_integrity") or not authorization.verify_integrity():
            raise ValueError("publication authorization integrity check failed")
        payload = json.loads(json.dumps(asdict(authorization), sort_keys=True, separators=(",", ":"), allow_nan=False))
        authorization_id = payload.get("authorization_id")
        if not _is_sha256(authorization_id):
            raise ValueError("publication authorization ID must be lowercase SHA-256")
        created_at = _utc(payload.get("created_at"))
        expires_at = _utc(payload.get("expires_at"))
        if expires_at <= created_at or (expires_at-created_at).total_seconds() > 300:
            raise ValueError("publication authorization expiry window is invalid")
        if not isinstance(payload.get("symbol"), str) or not payload["symbol"].strip():
            raise ValueError("publication authorization symbol is required")
        if not isinstance(payload.get("asset_id"), str) or not payload["asset_id"].startswith("coingecko:"):
            raise ValueError("publication authorization asset identity is invalid")
        if not _is_sha256(payload.get("content_hash")) or not _is_sha256(payload.get("draft_provenance_hash")):
            raise ValueError("publication authorization draft hashes are invalid")
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self.conn.transaction():
            brief = self.conn.execute(
                "SELECT event_id,research_package_id FROM editorial_brief_versions WHERE brief_id=%s FOR SHARE",
                (authorization.editorial_brief_id,),
            ).fetchone()
            draft = self.conn.execute(
                "SELECT draft_id,asset_id,content_hash,research_package_id,editorial_brief_id,approved_claim_ids_json FROM content_draft_versions WHERE draft_id=%s FOR SHARE",
                (authorization.draft_id,),
            ).fetchone()
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("event-lifecycle:" + authorization.event_id,),
            )
            if brief is None or brief["event_id"] != authorization.event_id or brief["research_package_id"] != authorization.research_package_id:
                raise ValueError("publication authorization editorial/event binding is missing or mismatched")
            if draft is None or draft["asset_id"] != authorization.asset_id or draft["content_hash"] != authorization.content_hash:
                raise ValueError("publication authorization exact draft binding is missing or mismatched")
            if draft["research_package_id"] != authorization.research_package_id or draft["editorial_brief_id"] != authorization.editorial_brief_id:
                raise ValueError("publication authorization draft provenance binding is mismatched")
            stored_claims = draft["approved_claim_ids_json"]
            if isinstance(stored_claims, str): stored_claims = json.loads(stored_claims)
            if tuple(sorted(stored_claims)) != tuple(sorted(authorization.approved_claim_ids)):
                raise ValueError("publication authorization approved-claim binding is mismatched")
            event = self.conn.execute(
                "SELECT asset_id,state FROM layer1_event_lifecycle WHERE event_id=%s FOR SHARE",
                (authorization.event_id,),
            ).fetchone()
            if authorization.event_state == "NO_EVENT":
                if event is not None:
                    raise ValueError("publication authorization declares NO_EVENT but a lifecycle record exists")
            elif (event is None or event["asset_id"] != authorization.asset_id
                    or event["state"] != authorization.event_state
                    or event["state"] not in {"CONFIRMED", "DEVELOPING"}):
                raise ValueError("publication authorization event lifecycle binding is no longer publishable")
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (validation_advisory_lock_key(authorization.content_hash, None),),
            )
            for image_hash in sorted(set(authorization.image_hashes)):
                self.conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                    (validation_advisory_lock_key(authorization.content_hash, image_hash),),
                )
            text_validation = self.conn.execute(
                "SELECT status FROM content_draft_validation_results WHERE draft_hash=%s ORDER BY created_at DESC,validation_id DESC LIMIT 1",
                (authorization.content_hash,),
            ).fetchone()
            if text_validation is None or text_validation["status"] != "PASS" or authorization.text_validation_status != "PASS":
                raise ValueError("publication authorization exact draft text validation is not PASS")
            for image_hash in authorization.image_hashes:
                artifact = self.conn.execute("SELECT 1 FROM image_generation_artifacts WHERE draft_hash=%s AND image_hash=%s", (authorization.content_hash,image_hash)).fetchone()
                visual = self.conn.execute("SELECT status,validation_version FROM visual_validation_results WHERE draft_hash=%s AND image_hash=%s ORDER BY created_at DESC,validation_id DESC LIMIT 1", (authorization.content_hash,image_hash)).fetchone()
                if artifact is None or visual is None or visual["status"] != "PASS" or visual["validation_version"] != "visual-quality-v2":
                    raise ValueError("publication authorization image artifact or current visual validation is missing")
            quota = self.conn.execute(
                "SELECT symbol,day_utc,status FROM publication_quota_reservations WHERE reservation_id=%s FOR UPDATE",
                (authorization.quota_reservation_id,),
            ).fetchone()
            if quota is None or quota["symbol"] != authorization.symbol or quota["day_utc"] != created_at.date() or quota["status"] != "RESERVED":
                raise ValueError("publication authorization quota reservation is missing or unavailable")
            existing = self.conn.execute("SELECT payload_json FROM publication_authorizations WHERE authorization_id=%s FOR UPDATE", (authorization_id,)).fetchone()
            if existing:
                stored = existing["payload_json"] if isinstance(existing["payload_json"], dict) else json.loads(existing["payload_json"])
                if stored != payload: raise ValueError("publication authorization ID is already bound to different immutable payload")
                return authorization_id
            self.conn.execute(
                "INSERT INTO publication_authorizations (authorization_id,draft_id,research_package_id,editorial_brief_id,event_id,asset_id,quota_reservation_id,payload_json,created_at,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)",
                (authorization_id,authorization.draft_id,authorization.research_package_id,authorization.editorial_brief_id,
                 authorization.event_id,authorization.asset_id,authorization.quota_reservation_id,payload_json,created_at,expires_at),
            )
            bound = self.conn.execute(
                "UPDATE publication_quota_reservations SET authorization_id=%s,updated_at=now() WHERE reservation_id=%s AND status='RESERVED' AND authorization_id IS NULL RETURNING reservation_id",
                (authorization_id,authorization.quota_reservation_id),
            ).fetchone()
            if bound is None:
                raise ValueError("quota reservation could not be exclusively bound to this authorization")
        return authorization_id

    def load_publication_authorization(self, authorization_id: str) -> Optional[dict]:
        if not _is_sha256(authorization_id): raise ValueError("authorization ID must be lowercase SHA-256")
        row = self.conn.execute("SELECT payload_json FROM publication_authorizations WHERE authorization_id=%s", (authorization_id,)).fetchone()
        if row is None: return None
        payload = row["payload_json"] if isinstance(row["payload_json"], dict) else json.loads(row["payload_json"])
        return payload

    def save_opportunity_decision(self, research_package_id: str, decision) -> str:
        validate_opportunity_decision_input(research_package_id, decision)
        from layer1.opportunity import _decision_digest
        expected_id = _decision_digest(
            state=decision.state, score=decision.score, reasons=decision.reasons,
            policy_version=decision.policy_version,
            input_snapshot_json=decision.input_snapshot_json,
        )
        if expected_id != decision.decision_id:
            raise ValueError("opportunity decision ID does not match its immutable input snapshot digest")
        reasons_json = json.dumps(list(decision.reasons), separators=(",", ":"), allow_nan=False)
        snapshot = json.loads(decision.input_snapshot_json)
        with self.conn.transaction():
            package = self.conn.execute(
                "SELECT package_id,payload_json FROM layer1_research_package_versions WHERE package_id=%s FOR SHARE",
                (research_package_id,),
            ).fetchone()
            if package is None:
                raise ValueError("opportunity decision research package does not exist")
            package_payload = package["payload_json"]
            if isinstance(package_payload, str):
                package_payload = json.loads(package_payload)
            if not isinstance(package_payload, dict):
                raise ValueError("opportunity decision research package payload is invalid")
            from layer1.opportunity import validate_opportunity_input_snapshot
            if snapshot["inputs"].get("schema_version") == 2:
                validate_opportunity_input_snapshot(
                    snapshot, expected_asset_id=package_payload.get("asset_id"),
                )
            existing = self.conn.execute(
                "SELECT research_package_id,state,score,reasons_json,policy_version,input_snapshot_json FROM opportunity_decisions WHERE decision_id=%s FOR UPDATE",
                (decision.decision_id,),
            ).fetchone()
            if existing:
                stored_reasons = existing["reasons_json"]
                stored_snapshot = existing["input_snapshot_json"]
                if isinstance(stored_reasons, str): stored_reasons = json.loads(stored_reasons)
                if isinstance(stored_snapshot, str): stored_snapshot = json.loads(stored_snapshot)
                if (existing["research_package_id"] != research_package_id or existing["state"] != decision.state
                        or existing["score"] != decision.score or stored_reasons != list(decision.reasons)
                        or existing["policy_version"] != decision.policy_version or stored_snapshot != snapshot):
                    raise ValueError("opportunity decision ID collision with different immutable payload")
                return decision.decision_id
            self.conn.execute(
                "INSERT INTO opportunity_decisions (decision_id,research_package_id,state,score,reasons_json,policy_version,created_at,input_snapshot_json) "
                "VALUES (%s,%s,%s,%s,%s::jsonb,%s,now(),%s::jsonb)",
                (decision.decision_id,research_package_id,decision.state,decision.score,reasons_json,decision.policy_version,
                 json.dumps(snapshot,sort_keys=True,separators=(",", ":"),allow_nan=False)),
            )
        return decision.decision_id

    def load_opportunity_decision(self, decision_id: str) -> Optional[dict]:
        if not _is_sha256(decision_id):
            raise ValueError("opportunity decision ID must be lowercase SHA-256")
        row = self.conn.execute(
            "SELECT decision_id,research_package_id,state,score,reasons_json,policy_version,input_snapshot_json,created_at FROM opportunity_decisions WHERE decision_id=%s",
            (decision_id,),
        ).fetchone()
        if row is None: return None
        reasons = row["reasons_json"] if isinstance(row["reasons_json"], list) else json.loads(row["reasons_json"])
        snapshot = row["input_snapshot_json"] if isinstance(row["input_snapshot_json"], dict) else json.loads(row["input_snapshot_json"])
        from layer1.opportunity import verify_opportunity_decision_digest
        verify_opportunity_decision_digest(
            decision_id=row["decision_id"], state=row["state"], score=row["score"],
            reasons=reasons, policy_version=row["policy_version"], input_snapshot=snapshot,
        )
        return {"decision_id":row["decision_id"],"research_package_id":row["research_package_id"],
                "state":row["state"],"score":row["score"],"reasons":reasons,"policy_version":row["policy_version"],
                "input_snapshot":snapshot,"created_at":row["created_at"].isoformat()}

    def save_image_artifact(self, metadata: dict, *, image_path: str) -> str:
        artifact = validate_image_artifact_input(metadata, image_path)
        artifact_id = hashlib.sha256(json.dumps(artifact, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
        metadata_json = json.dumps(metadata, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self.conn.transaction():
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("image-artifact:" + artifact["draft_hash"] + ":" + artifact["image_hash"],),
            )
            existing = self.conn.execute(
                "SELECT artifact_id,metadata_json,image_path FROM image_generation_artifacts WHERE draft_hash=%s AND image_hash=%s FOR UPDATE",
                (artifact["draft_hash"], artifact["image_hash"]),
            ).fetchone()
            if existing:
                stored_metadata = existing["metadata_json"]
                if isinstance(stored_metadata, str):
                    stored_metadata = json.loads(stored_metadata)
                if stored_metadata != metadata or existing["image_path"] != image_path:
                    raise ValueError("image artifact identity is immutable; conflicting provenance")
                return existing["artifact_id"]
            self.conn.execute(
                "INSERT INTO image_generation_artifacts (artifact_id,draft_hash,image_hash,asset_id,symbol,provider,model,request_id,generated_at,prompt_hash,generation_parameters_json,source_image_hash,image_path,metadata_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb)",
                (artifact_id, artifact["draft_hash"], artifact["image_hash"], artifact["asset_id"],
                 artifact["symbol"], artifact["provider"], artifact["model"], artifact["request_id"],
                 artifact["generated_at"], artifact["prompt_hash"],
                 json.dumps(artifact["generation_parameters"], sort_keys=True, separators=(",", ":")),
                 artifact["source_image_hash"], image_path, metadata_json),
            )
        return artifact_id

    def load_image_artifact(self, draft_hash: str, image_hash: str) -> Optional[dict]:
        if not _is_sha256(draft_hash) or not _is_sha256(image_hash):
            raise ValueError("draft and image hashes must be lowercase SHA-256")
        row = self.conn.execute(
            "SELECT artifact_id,metadata_json,image_path FROM image_generation_artifacts WHERE draft_hash=%s AND image_hash=%s",
            (draft_hash, image_hash),
        ).fetchone()
        if row is None:
            return None
        metadata = row["metadata_json"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return {"artifact_id": row["artifact_id"], "metadata": metadata, "image_path": row["image_path"]}

    def save_draft(
        self, content: str, *, asset_id: str, research_package_id: str,
        editorial_brief_id: str, approved_claim_ids,
    ):
        return _save_draft(
            self, content=content, asset_id=asset_id,
            research_package_id=research_package_id,
            editorial_brief_id=editorial_brief_id,
            approved_claim_ids=approved_claim_ids,
        )

    def load_latest_draft(self, draft_key: str) -> Optional[dict]:
        return _load_latest_draft(self, draft_key)

    def save_text_validation(self, *, draft_hash: str, status: str, reasons, validation_version: str) -> str:
        return _save_validation(self, draft_hash=draft_hash, image_hash=None, status=status,
                                reasons=reasons, validation_version=validation_version)

    def save_visual_validation(self, *, draft_hash: str, image_hash: str, status: str, reasons,
                               validation_version: str) -> str:
        return _save_validation(self, draft_hash=draft_hash, image_hash=image_hash, status=status,
                                reasons=reasons, validation_version=validation_version)

    def load_latest_text_validation(self, draft_hash: str) -> Optional[dict]:
        return _load_latest_validation(self, draft_hash=draft_hash, image_hash=None)

    def load_latest_visual_validation(self, draft_hash: str, image_hash: str) -> Optional[dict]:
        return _load_latest_validation(self, draft_hash=draft_hash, image_hash=image_hash)

    def save_claim_registry(self, registry) -> str:
        """Persist an immutable, append-only claim-verification snapshot."""
        from layer1.evidence_verification import ClaimRegistry

        if not isinstance(registry, ClaimRegistry):
            raise TypeError("claim registry persistence requires a typed ClaimRegistry")
        payload = registry.to_dict()
        payload_json = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        )
        # JSONB normalizes tuple-like JSON arrays to Python lists on readback.
        # Compare the canonical JSON representation, not the pre-serialization
        # Python container types, so identical snapshots remain idempotent.
        canonical_payload = json.loads(payload_json)
        verification_id = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        states = [result.state for result in registry.results]
        counts = {
            "claim_count": len(registry.claims),
            "verified_count": sum(state == "VERIFIED" for state in states),
            "corroborated_count": sum(state == "CORROBORATED" for state in states),
            "unresolved_count": len(registry.unresolved_issues),
        }
        with self.conn.transaction():
            existing = self.conn.execute(
                "SELECT payload_json,claim_count,verified_count,corroborated_count,unresolved_count "
                "FROM layer1_claim_verification_runs WHERE verification_id=%s FOR UPDATE",
                (verification_id,),
            ).fetchone()
            if existing is not None:
                stored_payload = existing["payload_json"]
                if isinstance(stored_payload, str):
                    stored_payload = json.loads(stored_payload)
                if stored_payload != canonical_payload or any(existing[key] != value for key, value in counts.items()):
                    raise ValueError("claim registry identity is immutable; conflicting payload reuse")
                return verification_id
            self.conn.execute(
                "INSERT INTO layer1_claim_verification_runs "
                "(verification_id,created_at,claim_count,verified_count,corroborated_count,unresolved_count,payload_json) "
                "VALUES (%s,now(),%s,%s,%s,%s,%s::jsonb)",
                (verification_id, counts["claim_count"], counts["verified_count"],
                 counts["corroborated_count"], counts["unresolved_count"], payload_json),
            )
        return verification_id

    def load_latest_claim_registry(self) -> Optional[dict]:
        """Load the newest persisted claim-verification snapshot."""
        row = self.conn.execute(
            "SELECT verification_id,payload_json FROM layer1_claim_verification_runs "
            "ORDER BY created_at DESC,verification_id DESC LIMIT 1",
        ).fetchone()
        if row is None:
            return None
        payload = row["payload_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return {"verification_id": row["verification_id"], "payload": payload}

    def save_research_package(
        self, *, research_key: str, package_hash: str, cutoff_at: str, payload: dict,
    ) -> dict:
        return _save_research_package(
            self, research_key=research_key, package_hash=package_hash,
            cutoff_at=cutoff_at, payload=payload,
        )

    def load_latest_research_package(self, research_key: str) -> Optional[dict]:
        return _load_latest_research_package(self, research_key)

    def save_editorial_brief(
        self, *, event_id: str, angle_id: str, research_package_id: str,
        brief_hash: str, payload: dict,
    ) -> dict:
        return _save_editorial_brief(
            self, event_id=event_id, angle_id=angle_id,
            research_package_id=research_package_id, brief_hash=brief_hash, payload=payload,
        )

    def load_latest_editorial_brief(self, event_id: str, angle_id: str) -> Optional[dict]:
        return _load_latest_editorial_brief(self, event_id, angle_id)

    def inspect_active_run_lease(self) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT l.run_id,l.acquired_at,r.started_at,r.status,r.config_hash "
            "FROM layer1_run_lease AS l LEFT JOIN layer1_runs AS r ON r.run_id=l.run_id "
            "WHERE l.lease_name='agent'"
        ).fetchone()
        if row is None:
            return None
        return {
            "run_id": str(row["run_id"]),
            "acquired_at": row["acquired_at"].isoformat(),
            "started_at": row["started_at"].isoformat(),
            "status": str(row["status"]),
            "config_hash": str(row["config_hash"]),
        }

    def acquire_run_lease(self, context) -> None:
        run_id = getattr(context, "run_id", None)
        config_hash = getattr(context, "config_hash", None)
        started_at = getattr(context, "started_at", None)
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run context requires a non-empty run_id")
        if not isinstance(config_hash, str) or len(config_hash) != 64 or any(c not in "0123456789abcdef" for c in config_hash):
            raise ValueError("run context requires a lowercase SHA-256 config_hash")
        started = _utc(started_at)
        with self.conn.transaction():
            # Lock the logical lease key even when no lease row exists yet.
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("layer1-run-lease:agent",),
            )
            existing = self.conn.execute(
                "SELECT run_id,acquired_at FROM layer1_run_lease WHERE lease_name='agent' FOR UPDATE"
            ).fetchone()
            if existing is not None:
                raise RuntimeError(
                    f"agent lease already held by run {existing['run_id']} since {existing['acquired_at']}"
                )
            self.conn.execute(
                "INSERT INTO layer1_runs(run_id,started_at,status,config_hash) VALUES (%s,%s,'RUNNING',%s)",
                (run_id, started, config_hash),
            )
            self.conn.execute(
                "INSERT INTO layer1_run_lease(lease_name,run_id,acquired_at) VALUES ('agent',%s,%s)",
                (run_id, started),
            )

    def recover_interrupted_run_lease(
        self, *, expected_run_id: str, process_termination_confirmed: bool,
        evidence: str, recovered_by: str,
    ) -> bool:
        """Operator-only recovery of a crashed run; never steals a lease by age."""
        if process_termination_confirmed is not True:
            raise ValueError("process termination confirmation is required")
        if not isinstance(expected_run_id, str) or not expected_run_id.strip():
            raise ValueError("expected run ID is required")
        if not isinstance(evidence, str) or len(evidence.strip()) < 12:
            raise ValueError("operator recovery evidence must be specific")
        if not isinstance(recovered_by, str) or not recovered_by.strip():
            raise ValueError("operator identity is required")
        import psycopg
        with self.conn.transaction():
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("layer1-run-lease:agent",),
            )
            lease = self.conn.execute(
                "SELECT run_id FROM layer1_run_lease WHERE lease_name='agent' FOR UPDATE"
            ).fetchone()
            if lease is None:
                return False
            if str(lease["run_id"]) != expected_run_id:
                raise ValueError("active lease does not match the expected run ID")
            run = self.conn.execute(
                "SELECT status,summary_json FROM layer1_runs WHERE run_id=%s FOR UPDATE",
                (expected_run_id,),
            ).fetchone()
            if run is None or run["status"] != "RUNNING":
                raise RuntimeError("run record is missing or not RUNNING; refusing recovery")
            summary = run["summary_json"]
            if isinstance(summary, str):
                summary = json.loads(summary) if summary else {}
            if summary is None:
                summary = {}
            if not isinstance(summary, dict):
                raise RuntimeError("existing run summary is invalid; refusing recovery")
            summary = dict(summary)
            summary["operator_recovery"] = {
                "recovered_by": recovered_by.strip(),
                "evidence": evidence.strip(),
                "process_termination_confirmed": True,
            }
            updated = self.conn.execute(
                "UPDATE layer1_runs SET finished_at=%s,status='INTERRUPTED',summary_json=%s "
                "WHERE run_id=%s AND status='RUNNING' RETURNING run_id",
                (_utc().isoformat(), psycopg.types.json.Jsonb(summary), expected_run_id),
            ).fetchone()
            if updated is None:
                raise RuntimeError("run state changed during operator recovery")
            deleted = self.conn.execute(
                "DELETE FROM layer1_run_lease WHERE lease_name='agent' AND run_id=%s RETURNING run_id",
                (expected_run_id,),
            ).fetchone()
            if deleted is None:
                raise RuntimeError("run lease ownership changed during operator recovery")
            return True

    def finish_run_lease(self, run_id: str, status: str, summary=None) -> None:
        allowed = {"SUCCEEDED", "NO_CANDIDATE_OR_BLOCKED", "FAILED", "INTERRUPTED"}
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id is required to finish a run lease")
        if status not in allowed:
            raise ValueError(f"unsupported run status: {status}")
        encoded = dict(summary or {})
        if not isinstance(encoded, dict):
            raise ValueError("run summary must be an object")
        try:
            json.dumps(encoded, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError("run summary must contain finite JSON data") from None
        import psycopg
        finished_at = _utc().isoformat()
        with self.conn.transaction():
            # Use the same lock order as acquire/recover so a terminal finish
            # cannot deadlock against operator recovery of the same lease.
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("layer1-run-lease:agent",),
            )
            updated = self.conn.execute(
                "UPDATE layer1_runs SET finished_at=%s,status=%s,summary_json=%s "
                "WHERE run_id=%s AND status='RUNNING' RETURNING run_id",
                (finished_at, status, psycopg.types.json.Jsonb(encoded), run_id),
            ).fetchone()
            if updated is None:
                raise RuntimeError("run record is missing or no longer RUNNING; refusing lease release")
            deleted = self.conn.execute(
                "DELETE FROM layer1_run_lease WHERE lease_name='agent' AND run_id=%s RETURNING run_id",
                (run_id,),
            ).fetchone()
            if deleted is None:
                raise RuntimeError("run lease ownership was lost; refusing to mark run complete")

    def close(self) -> None:
        self.conn.close()



def validate_research_package_input(
    research_key: str, package_hash: str, cutoff_at: str, payload,
) -> datetime:
    """Validate immutable research-package identity before any database write."""
    if not isinstance(research_key, str) or not research_key.strip():
        raise ValueError("research_key must be a non-empty string")
    if (not isinstance(package_hash, str) or len(package_hash) != 64
            or any(char not in "0123456789abcdef" for char in package_hash)):
        raise ValueError("package_hash must be a lowercase SHA-256 digest")
    if not isinstance(payload, dict):
        raise ValueError("research package payload must be a JSON object")
    try:
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("research package payload must be finite JSON data") from None
    try:
        return _utc(cutoff_at)
    except ValueError as exc:
        if "timezone" in str(exc):
            raise ValueError("cutoff_at must include timezone") from None
        raise ValueError("cutoff_at must be ISO-8601 with timezone") from None


def _save_research_package(
    store: PostgresPublicationStore, *, research_key: str, package_hash: str,
    cutoff_at: str, payload: dict,
) -> dict:
    cutoff = validate_research_package_input(research_key, package_hash, cutoff_at, payload)
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    with store.conn.transaction():
        store.conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            ("research-package:" + research_key,),
        )
        existing = store.conn.execute(
            "SELECT version,package_id,cutoff_at,payload_json FROM layer1_research_package_versions "
            "WHERE research_key=%s AND package_hash=%s FOR UPDATE",
            (research_key, package_hash),
        ).fetchone()
        if existing:
            stored_payload = existing["payload_json"]
            if isinstance(stored_payload, str):
                stored_payload = json.loads(stored_payload)
            if existing["cutoff_at"] != cutoff or stored_payload != payload:
                raise ValueError("research package identity is immutable; conflicting payload reuse")
            return {
                "research_key": research_key, "version": existing["version"],
                "package_id": existing["package_id"], "package_hash": package_hash,
                "cutoff_at": cutoff.isoformat(), "payload": stored_payload,
            }
        version = store.conn.execute(
            "SELECT COALESCE(MAX(version),0)+1 AS next_version "
            "FROM layer1_research_package_versions WHERE research_key=%s",
            (research_key,),
        ).fetchone()["next_version"]
        package_id = research_key + ":" + str(version)
        store.conn.execute(
            "INSERT INTO layer1_research_package_versions "
            "(research_key,version,package_id,package_hash,cutoff_at,payload_json,created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s::jsonb,now())",
            (research_key, version, package_id, package_hash, cutoff, payload_json),
        )
    return {
        "research_key": research_key, "version": version,
        "package_id": package_id, "package_hash": package_hash,
        "cutoff_at": cutoff.isoformat(), "payload": payload,
    }


def _load_latest_research_package(store: PostgresPublicationStore, research_key: str) -> Optional[dict]:
    if not isinstance(research_key, str) or not research_key.strip():
        raise ValueError("research_key must be a non-empty string")
    row = store.conn.execute(
        "SELECT research_key,version,package_id,package_hash,cutoff_at,payload_json "
        "FROM layer1_research_package_versions WHERE research_key=%s ORDER BY version DESC LIMIT 1",
        (research_key,),
    ).fetchone()
    if row is None:
        return None
    payload = row["payload_json"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {
        "research_key": row["research_key"], "version": row["version"],
        "package_id": row["package_id"], "package_hash": row["package_hash"],
        "cutoff_at": row["cutoff_at"].isoformat(), "payload": payload,
    }



def _validate_editorial_brief_input(event_id, angle_id, research_package_id, brief_hash, payload):
    for name, value in (("event_id", event_id), ("angle_id", angle_id), ("research_package_id", research_package_id)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(name + " must be a non-empty string")
    if (not isinstance(brief_hash, str) or len(brief_hash) != 64
            or any(char not in "0123456789abcdef" for char in brief_hash)):
        raise ValueError("brief_hash must be a lowercase SHA-256 digest")
    if not isinstance(payload, dict):
        raise ValueError("editorial brief payload must be a JSON object")
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("editorial brief payload must be finite JSON data") from None


def _save_editorial_brief(
    store, *, event_id, angle_id, research_package_id, brief_hash, payload,
):
    payload_json = _validate_editorial_brief_input(
        event_id, angle_id, research_package_id, brief_hash, payload,
    )
    with store.conn.transaction():
        lock_key = "editorial-brief:" + event_id + ":" + angle_id
        store.conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (lock_key,))
        existing = store.conn.execute(
            "SELECT version,brief_id,research_package_id,payload_json FROM editorial_brief_versions "
            "WHERE event_id=%s AND angle_id=%s AND brief_hash=%s FOR UPDATE",
            (event_id, angle_id, brief_hash),
        ).fetchone()
        if existing:
            stored = existing["payload_json"]
            if isinstance(stored, str):
                stored = json.loads(stored)
            if existing["research_package_id"] != research_package_id or stored != payload:
                raise ValueError("editorial brief identity is immutable; conflicting payload reuse")
            return {"event_id": event_id, "angle_id": angle_id, "version": existing["version"],
                    "brief_id": existing["brief_id"], "research_package_id": research_package_id,
                    "brief_hash": brief_hash, "payload": stored}
        version = store.conn.execute(
            "SELECT COALESCE(MAX(version),0)+1 AS next_version FROM editorial_brief_versions "
            "WHERE event_id=%s AND angle_id=%s", (event_id, angle_id),
        ).fetchone()["next_version"]
        brief_id = event_id + ":" + angle_id + ":" + str(version)
        store.conn.execute(
            "INSERT INTO editorial_brief_versions "
            "(event_id,angle_id,version,brief_id,research_package_id,brief_hash,payload_json,created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,now())",
            (event_id, angle_id, version, brief_id, research_package_id, brief_hash, payload_json),
        )
    return {"event_id": event_id, "angle_id": angle_id, "version": version,
            "brief_id": brief_id, "research_package_id": research_package_id,
            "brief_hash": brief_hash, "payload": payload}


def _load_latest_editorial_brief(store, event_id, angle_id):
    if any(not isinstance(v, str) or not v.strip() for v in (event_id, angle_id)):
        raise ValueError("event_id and angle_id are required")
    row = store.conn.execute(
        "SELECT event_id,angle_id,version,brief_id,research_package_id,brief_hash,payload_json "
        "FROM editorial_brief_versions WHERE event_id=%s AND angle_id=%s "
        "ORDER BY version DESC LIMIT 1", (event_id, angle_id),
    ).fetchone()
    if row is None:
        return None
    payload = row["payload_json"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {"event_id": row["event_id"], "angle_id": row["angle_id"],
            "version": row["version"], "brief_id": row["brief_id"],
            "research_package_id": row["research_package_id"],
            "brief_hash": row["brief_hash"], "payload": payload}


def _save_editorial_brief_method(self, **kwargs):
    return _save_editorial_brief(self, **kwargs)


def _load_latest_editorial_brief_method(self, event_id, angle_id):
    return _load_latest_editorial_brief(self, event_id, angle_id)



_EVENT_STATES = {"DISCOVERED", "UNDER_VERIFICATION", "CONFIRMED", "DEVELOPING", "RESOLVED", "STALE", "DISPUTED", "WITHDRAWN"}
_EVENT_TRANSITIONS = {
    None: {"DISCOVERED"}, "DISCOVERED": {"UNDER_VERIFICATION"},
    "UNDER_VERIFICATION": {"CONFIRMED", "RESOLVED", "STALE", "WITHDRAWN", "DISPUTED"},
    "CONFIRMED": {"DEVELOPING", "RESOLVED", "STALE", "WITHDRAWN", "DISPUTED"},
    "DEVELOPING": {"RESOLVED", "STALE", "WITHDRAWN", "DISPUTED"},
    "STALE": {"UNDER_VERIFICATION"}, "RESOLVED": {"UNDER_VERIFICATION"},
    "DISPUTED": {"UNDER_VERIFICATION", "RESOLVED", "WITHDRAWN"}, "WITHDRAWN": set(),
}
MAX_EVENT_REVISION_PAYLOAD_BYTES = 256 * 1024
MAX_EVENT_REVISION_DEPTH = 64
MAX_EVENT_REVISION_NODES = 10_000
MAX_EVENT_EVIDENCE_REFS = 100
MAX_EVENT_EVIDENCE_REF_LENGTH = 2048


def _validate_event_payload_bounds(payload: dict) -> None:
    pending = [(payload, 0)]
    approximate_bytes = 2
    visited_nodes = 0
    while pending:
        value, depth = pending.pop()
        visited_nodes += 1
        if visited_nodes > MAX_EVENT_REVISION_NODES or depth > MAX_EVENT_REVISION_DEPTH:
            raise ValueError("event revision payload exceeds structural limits")
        if isinstance(value, dict):
            if len(value) > MAX_EVENT_REVISION_NODES - visited_nodes:
                raise ValueError("event revision payload exceeds structural limits")
            for key, child in value.items():
                if not isinstance(key, str):
                    raise ValueError("event revision payload object keys must be strings")
                if len(key) > MAX_EVENT_REVISION_PAYLOAD_BYTES:
                    raise ValueError("event revision payload exceeds the 256 KiB limit")
                approximate_bytes += len(key.encode("utf-8")) + 4
                if approximate_bytes > MAX_EVENT_REVISION_PAYLOAD_BYTES:
                    raise ValueError("event revision payload exceeds the 256 KiB limit")
                pending.append((child, depth + 1))
        elif isinstance(value, (list, tuple)):
            if len(value) > MAX_EVENT_REVISION_NODES - visited_nodes:
                raise ValueError("event revision payload exceeds structural limits")
            approximate_bytes += len(value) * 2
            pending.extend((child, depth + 1) for child in value)
        elif isinstance(value, str):
            if len(value) > MAX_EVENT_REVISION_PAYLOAD_BYTES:
                raise ValueError("event revision payload exceeds the 256 KiB limit")
            approximate_bytes += len(value.encode("utf-8")) + 2
        elif value is None or isinstance(value, (bool, int, float)):
            approximate_bytes += 32
        else:
            raise ValueError("event revision payload contains a non-JSON value")
        if approximate_bytes > MAX_EVENT_REVISION_PAYLOAD_BYTES:
            raise ValueError("event revision payload exceeds the 256 KiB limit")


def validate_event_revision_payload(payload, evidence_refs) -> tuple[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("event revision payload must be a JSON object")
    if not isinstance(evidence_refs, (list, tuple)) or not evidence_refs:
        raise ValueError("event evidence references must be a non-empty list")
    if len(evidence_refs) > MAX_EVENT_EVIDENCE_REFS:
        raise ValueError("event evidence references contain too many entries")
    if any(not isinstance(ref, str) or not ref.strip() for ref in evidence_refs):
        raise ValueError("event evidence references must be non-empty strings")
    if any(len(ref) > MAX_EVENT_EVIDENCE_REF_LENGTH for ref in evidence_refs):
        raise ValueError("event evidence reference is too long")
    _validate_event_payload_bounds(payload)
    try:
        payload_json = json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
        refs_json = json.dumps(
            sorted(set(evidence_refs)), separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError):
        raise ValueError("event revision payload and evidence references must be finite JSON data") from None
    if len(payload_json.encode("utf-8")) > MAX_EVENT_REVISION_PAYLOAD_BYTES:
        raise ValueError("event revision payload exceeds the 256 KiB limit")
    return payload_json, refs_json


def validate_event_lifecycle_input(
    event_id, asset_id, source_id, event_type, revision_hash,
    first_published_at, first_observed_at, last_updated_at, effective_event_at,
    state, from_state, reason_code, evidence_refs,
) -> tuple[datetime, datetime, datetime, datetime]:
    for name, value in (("event_id", event_id), ("asset_id", asset_id), ("source_id", source_id), ("event_type", event_type), ("reason_code", reason_code)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(name + " must be a non-empty string")
    if not isinstance(revision_hash, str) or len(revision_hash) != 64 or any(c not in "0123456789abcdef" for c in revision_hash):
        raise ValueError("revision_hash must be a lowercase SHA-256 digest")
    if (not isinstance(state, str) or state not in _EVENT_STATES
            or (from_state is not None and not isinstance(from_state, str))
            or from_state not in _EVENT_TRANSITIONS):
        raise ValueError("invalid event lifecycle state or transition")
    if state not in _EVENT_TRANSITIONS[from_state]:
        raise ValueError("illegal event lifecycle transition")
    if not isinstance(evidence_refs, (list, tuple)) or not evidence_refs or any(not isinstance(v, str) or not v.strip() for v in evidence_refs):
        raise ValueError("event evidence references must be a non-empty finite list")
    try:
        return tuple(_utc(v) for v in (first_published_at, first_observed_at, last_updated_at, effective_event_at))
    except ValueError as exc:
        raise ValueError("event lifecycle timestamps must be ISO-8601 with timezone") from exc

def _observe_event_lifecycle(
    store, *, event_id, asset_id, source_id, event_type, revision_hash,
    first_published_at, first_observed_at, last_updated_at, effective_event_at,
    state, from_state, reason_code, evidence_refs, payload,
) -> dict:
    timestamps = validate_event_lifecycle_input(
        event_id, asset_id, source_id, event_type, revision_hash,
        first_published_at, first_observed_at, last_updated_at, effective_event_at,
        state, from_state, reason_code, evidence_refs,
    )
    payload_json, refs_json = validate_event_revision_payload(payload, evidence_refs)
    first_published, first_observed, last_updated, effective_event = timestamps
    with store.conn.transaction():
        store.conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("event-lifecycle:" + event_id,))
        current = store.conn.execute("SELECT * FROM layer1_event_lifecycle WHERE event_id=%s FOR UPDATE", (event_id,)).fetchone()
        if current is None:
            if from_state is not None or state != "DISCOVERED":
                raise ValueError("illegal event lifecycle transition: initial state must be DISCOVERED")
            store.conn.execute(
                "INSERT INTO layer1_event_lifecycle (event_id,asset_id,source_id,event_type,state,first_published_at,first_observed_at,last_updated_at,effective_event_at,latest_revision_hash,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (event_id, asset_id, source_id, event_type, state, first_published, first_observed, last_updated, effective_event, revision_hash, first_observed),
            )
        else:
            identity = (current["asset_id"], current["source_id"], current["event_type"])
            if identity != (asset_id, source_id, event_type):
                raise ValueError("event lifecycle identity is immutable")
            prior_revision = store.conn.execute("SELECT payload_json FROM layer1_event_revisions WHERE event_id=%s AND revision_hash=%s", (event_id, revision_hash)).fetchone()
            if prior_revision is not None:
                prior_payload = prior_revision["payload_json"]
                if isinstance(prior_payload, str): prior_payload = json.loads(prior_payload)
                if prior_payload != payload:
                    raise ValueError("event revision identity is immutable; conflicting payload reuse")
                if current["latest_revision_hash"] == revision_hash:
                    return {"event_id": event_id, "state": current["state"], "revision_hash": revision_hash, "replayed": True}
                raise ValueError("event revision already exists and cannot be replayed as a new transition")
            if current["state"] != from_state:
                raise ValueError("event lifecycle transition does not match current state")
            if current["state"] == "WITHDRAWN" and current["latest_revision_hash"] != revision_hash:
                raise ValueError("withdrawn event lifecycle is terminal")
            store.conn.execute(
                "UPDATE layer1_event_lifecycle SET state=%s,last_updated_at=%s,effective_event_at=%s,latest_revision_hash=%s,updated_at=%s WHERE event_id=%s",
                (state, last_updated, effective_event, revision_hash, first_observed, event_id),
            )
        existing = store.conn.execute(
            "SELECT source_published_at,source_updated_at,observed_at,evidence_ref,payload_json FROM layer1_event_revisions WHERE event_id=%s AND revision_hash=%s FOR UPDATE",
            (event_id, revision_hash),
        ).fetchone()
        if existing:
            saved = existing["payload_json"]
            if isinstance(saved, str): saved = json.loads(saved)
            if saved != payload:
                raise ValueError("event revision identity is immutable; conflicting payload reuse")
            replayed = True
        else:
            store.conn.execute(
                "INSERT INTO layer1_event_revisions (event_id,revision_hash,source_published_at,source_updated_at,observed_at,evidence_ref,payload_json) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)",
                (event_id, revision_hash, first_published, last_updated, first_observed, sorted(set(evidence_refs))[0], payload_json),
            )
            replayed = False
        if not replayed:
            store.conn.execute(
                "INSERT INTO layer1_event_transitions (event_id,from_state,to_state,reason_code,evidence_refs_json,transitioned_at) VALUES (%s,%s,%s,%s,%s::jsonb,%s)",
                (event_id, from_state, state, reason_code, refs_json, first_observed),
            )
    return {"event_id": event_id, "state": state if not replayed else (current["state"] if current else state), "revision_hash": revision_hash, "replayed": replayed}

def _load_event_lifecycle(store, event_id: str) -> Optional[dict]:
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("event_id is required")
    row = store.conn.execute("SELECT * FROM layer1_event_lifecycle WHERE event_id=%s", (event_id,)).fetchone()
    if row is None: return None
    revisions = store.conn.execute("SELECT revision_hash,source_published_at,source_updated_at,observed_at,evidence_ref,payload_json FROM layer1_event_revisions WHERE event_id=%s ORDER BY observed_at,revision_hash", (event_id,)).fetchall()
    history = store.conn.execute("SELECT from_state,to_state,reason_code,evidence_refs_json,transitioned_at FROM layer1_event_transitions WHERE event_id=%s ORDER BY transition_id", (event_id,)).fetchall()
    return {
        "event_id": row["event_id"], "asset_id": row["asset_id"], "source_id": row["source_id"], "event_type": row["event_type"], "state": row["state"],
        "first_published_at": row["first_published_at"].isoformat(), "first_observed_at": row["first_observed_at"].isoformat(), "last_updated_at": row["last_updated_at"].isoformat(), "effective_event_at": row["effective_event_at"].isoformat(), "latest_revision_hash": row["latest_revision_hash"],
        "revisions": [{"revision_hash": r["revision_hash"], "source_published_at": r["source_published_at"].isoformat(), "source_updated_at": r["source_updated_at"].isoformat() if r["source_updated_at"] else None, "observed_at": r["observed_at"].isoformat(), "evidence_ref": r["evidence_ref"], "payload": r["payload_json"] if isinstance(r["payload_json"], dict) else json.loads(r["payload_json"])} for r in revisions],
        "history": [{"from_state": h["from_state"], "to_state": h["to_state"], "reason_code": h["reason_code"], "evidence_refs": h["evidence_refs_json"] if isinstance(h["evidence_refs_json"], list) else json.loads(h["evidence_refs_json"]), "transitioned_at": h["transitioned_at"].isoformat()} for h in history],
    }


def validate_validation_input(draft_hash, image_hash, status, reasons, validation_version):
    from collections.abc import Sequence

    for name, value in (("draft_hash", draft_hash), ("image_hash", image_hash)):
        if value is None and name == "image_hash":
            continue
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("validation record has invalid " + name)
    if not isinstance(status, str) or status not in {"PASS", "NEEDS_REVISION", "REJECT"}:
        raise ValueError("validation status is invalid")
    if not isinstance(reasons, Sequence) or isinstance(reasons, (str, bytes)):
        raise ValueError("validation reasons must be a sequence of strings")
    if any(not isinstance(reason, str) or not reason.strip() for reason in reasons):
        raise ValueError("validation reasons must be non-empty strings")
    if not isinstance(validation_version, str) or not validation_version.strip():
        raise ValueError("validation version is required")
    normalized_reasons = sorted({reason.strip() for reason in reasons})
    payload = {"draft_hash": draft_hash, "status": status, "reasons": normalized_reasons,
               "version": validation_version.strip()}
    if image_hash is not None:
        payload["image_hash"] = image_hash
    validation_id = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return {"validation_id": validation_id, "draft_hash": draft_hash, "image_hash": image_hash,
            "status": status, "reasons": normalized_reasons,
            "validation_version": validation_version.strip()}


def _save_validation(store, *, draft_hash, image_hash, status, reasons, validation_version):
    record = validate_validation_input(draft_hash, image_hash, status, reasons, validation_version)
    table = "content_draft_validation_results" if image_hash is None else "visual_validation_results"
    columns = "validation_id,draft_hash,status,reasons_json,validation_version" if image_hash is None else "validation_id,draft_hash,image_hash,status,reasons_json,validation_version"
    values = (record["validation_id"], draft_hash, status,
              json.dumps(record["reasons"], separators=(",", ":"), ensure_ascii=False), validation_version.strip())
    if image_hash is not None:
        values = (record["validation_id"], draft_hash, image_hash, status, values[3], validation_version.strip())
    placeholders = "%s,%s,%s,%s,%s" if image_hash is None else "%s,%s,%s,%s,%s,%s"
    with store.conn.transaction():
        store.conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            (validation_advisory_lock_key(draft_hash, image_hash),),
        )
        store.conn.execute(
            f"INSERT INTO {table} ({columns},created_at) VALUES ({placeholders},now()) ON CONFLICT (validation_id) DO NOTHING",
            values,
        )
        row = store.conn.execute(
            f"SELECT {columns} FROM {table} WHERE validation_id=%s", (record["validation_id"],),
        ).fetchone()
        stored_reasons = row["reasons_json"] if isinstance(row["reasons_json"], list) else json.loads(row["reasons_json"])
        if (row["draft_hash"] != draft_hash or row["status"] != status
                or stored_reasons != record["reasons"] or row["validation_version"] != validation_version.strip()
                or (image_hash is not None and row["image_hash"] != image_hash)):
            raise ValueError("validation identity is immutable; conflicting payload")
    return record["validation_id"]


def _load_latest_validation(store, *, draft_hash, image_hash):
    if not isinstance(draft_hash, str) or len(draft_hash) != 64 or any(c not in "0123456789abcdef" for c in draft_hash):
        raise ValueError("validation record has invalid draft_hash")
    if image_hash is not None and (not isinstance(image_hash, str) or len(image_hash) != 64 or any(c not in "0123456789abcdef" for c in image_hash)):
        raise ValueError("validation record has invalid image_hash")
    if image_hash is None:
        row = store.conn.execute(
            "SELECT validation_id,draft_hash,status,reasons_json,validation_version,created_at FROM content_draft_validation_results WHERE draft_hash=%s ORDER BY created_at DESC,validation_id DESC LIMIT 1",
            (draft_hash,),
        ).fetchone()
    else:
        row = store.conn.execute(
            "SELECT validation_id,draft_hash,image_hash,status,reasons_json,validation_version,created_at FROM visual_validation_results WHERE draft_hash=%s AND image_hash=%s ORDER BY created_at DESC,validation_id DESC LIMIT 1",
            (draft_hash, image_hash),
        ).fetchone()
    if row is None:
        return None
    reasons = row["reasons_json"] if isinstance(row["reasons_json"], list) else json.loads(row["reasons_json"])
    return {"validation_id": row["validation_id"], "draft_hash": row["draft_hash"],
            "image_hash": row["image_hash"] if image_hash is not None else None,
            "status": row["status"], "reasons": reasons, "validation_version": row["validation_version"],
            "created_at": row["created_at"].isoformat()}


def _is_sha256(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def validation_advisory_lock_key(draft_hash: str, image_hash: Optional[str]) -> str:
    if not _is_sha256(draft_hash):
        raise ValueError("validation lock requires a lowercase draft SHA-256")
    if image_hash is None:
        scope = "text"
    elif _is_sha256(image_hash):
        scope = image_hash
    else:
        raise ValueError("validation lock requires a lowercase image SHA-256")
    return "publication-validation:" + draft_hash + ":" + scope


def validate_opportunity_decision_input(research_package_id: str, decision) -> None:
    from layer1.opportunity import OpportunityDecision, validate_opportunity_input_snapshot
    if not isinstance(research_package_id, str) or not research_package_id.strip():
        raise ValueError("opportunity decision requires a research package ID")
    if not isinstance(decision, OpportunityDecision):
        raise ValueError("opportunity decision payload is invalid")
    if (decision.state not in {"PROCEED", "RESEARCH_MORE", "DEFER", "REJECT"}
            or (decision.score is not None and (isinstance(decision.score, bool)
                or not isinstance(decision.score, (int, float)) or not math.isfinite(decision.score)
                or not 0 <= decision.score <= 100))
            or not isinstance(decision.policy_version, str) or not decision.policy_version.strip()
            or not isinstance(decision.reasons, tuple)
            or any(not isinstance(reason, str) or not reason.strip() for reason in decision.reasons)
            or not _is_sha256(decision.decision_id)):
        raise ValueError("opportunity decision payload is invalid")
    try:
        snapshot = json.loads(decision.input_snapshot_json)
    except (TypeError, json.JSONDecodeError):
        raise ValueError("opportunity decision input snapshot is invalid") from None
    validate_opportunity_input_snapshot(snapshot)
    json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)


def validate_image_artifact_input(metadata: dict, image_path: str) -> dict:
    required = {
        "provider", "model", "generated_at", "prompt_hash", "generation_parameters",
        "source_image_hash", "final_image_hash", "draft_hash", "asset_id", "symbol", "dimensions",
    }
    if not isinstance(metadata, dict) or not required.issubset(metadata):
        raise ValueError("image artifact metadata is incomplete")
    for name in ("prompt_hash", "source_image_hash", "final_image_hash", "draft_hash"):
        if not _is_sha256(metadata.get(name)):
            raise ValueError("image artifact " + name + " must be lowercase SHA-256")
    if metadata["provider"] != "cloudflare_workers_ai" or metadata["model"] != "@cf/black-forest-labs/flux-2-klein-4b":
        raise ValueError("image artifact provider/model is not approved")
    if not isinstance(metadata["asset_id"], str) or not metadata["asset_id"].startswith("coingecko:"):
        raise ValueError("image artifact requires canonical asset identity")
    if not isinstance(metadata["symbol"], str) or not metadata["symbol"].strip():
        raise ValueError("image artifact requires an asset symbol")
    params = metadata["generation_parameters"]
    if (not isinstance(params, dict) or isinstance(params.get("width"), bool) or not isinstance(params.get("width"), int)
            or isinstance(params.get("height"), bool) or not isinstance(params.get("height"), int)
            or not 256 <= params.get("width", 0) <= 1920 or not 256 <= params.get("height", 0) <= 1920
            or params.get("output_format") not in {"PNG", "JPEG", "WEBP"}):
        raise ValueError("image generation parameters are invalid")
    dimensions = metadata["dimensions"]
    if not isinstance(dimensions, list) or len(dimensions) != 2 or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in dimensions):
        raise ValueError("image artifact dimensions are invalid")
    if not isinstance(image_path, str) or not image_path.strip():
        raise ValueError("image artifact path is required")
    generated_at = _utc(metadata["generated_at"])
    payload = {
        "draft_hash": metadata["draft_hash"], "image_hash": metadata["final_image_hash"],
        "asset_id": metadata["asset_id"], "symbol": metadata["symbol"].upper(),
        "provider": metadata["provider"], "model": metadata["model"],
        "request_id": metadata.get("request_id"), "generated_at": generated_at.isoformat(),
        "prompt_hash": metadata["prompt_hash"], "generation_parameters": params,
        "source_image_hash": metadata["source_image_hash"], "image_path": image_path,
    }
    json.dumps(metadata, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return payload


def validate_draft_input(content, asset_id, research_package_id, editorial_brief_id, approved_claim_ids):
    from collections.abc import Sequence

    if not isinstance(content, str) or not content.strip():
        raise ValueError("draft content must be non-empty")
    if not isinstance(asset_id, str) or not asset_id.startswith("coingecko:"):
        raise ValueError("draft requires canonical asset identity")
    if any(not isinstance(value, str) or not value.strip() for value in (research_package_id, editorial_brief_id)):
        raise ValueError("draft requires research package and editorial brief IDs")
    if not isinstance(approved_claim_ids, Sequence) or isinstance(approved_claim_ids, (str, bytes)):
        raise ValueError("approved claim IDs must be a sequence of claim ID strings")
    if any(not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value) for value in approved_claim_ids):
        raise ValueError("draft requires lowercase SHA-256 claim IDs")
    claims = tuple(sorted(set(approved_claim_ids)))
    if not claims:
        raise ValueError("draft requires verified claim references")
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    draft_key = hashlib.sha256((asset_id + "|" + editorial_brief_id).encode("utf-8")).hexdigest()
    return content_hash, draft_key, claims


def _save_draft(store, *, content, asset_id, research_package_id, editorial_brief_id, approved_claim_ids):
    from .content_generation import DraftRecord

    content_hash, draft_key, claims = validate_draft_input(
        content, asset_id, research_package_id, editorial_brief_id, approved_claim_ids,
    )
    claims_json = json.dumps(list(claims), separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    with store.conn.transaction():
        store.conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("content-draft:" + draft_key,),
        )
        brief = store.conn.execute(
            "SELECT research_package_id FROM editorial_brief_versions WHERE brief_id=%s FOR SHARE",
            (editorial_brief_id,),
        ).fetchone()
        if brief is None:
            raise ValueError("persisted editorial brief not found for draft")
        if brief["research_package_id"] != research_package_id:
            raise ValueError("draft research package does not match its editorial brief binding")
        existing = store.conn.execute(
            "SELECT version,draft_id,created_at,research_package_id,editorial_brief_id,approved_claim_ids_json,content "
            "FROM content_draft_versions WHERE draft_key=%s AND content_hash=%s FOR UPDATE",
            (draft_key, content_hash),
        ).fetchone()
        if existing:
            stored_claims = existing["approved_claim_ids_json"]
            if isinstance(stored_claims, str):
                stored_claims = json.loads(stored_claims)
            if (existing["research_package_id"] != research_package_id
                    or existing["editorial_brief_id"] != editorial_brief_id
                    or tuple(stored_claims) != claims or existing["content"] != content):
                raise ValueError("draft identity is immutable; conflicting provenance or content reuse")
            return DraftRecord(
                draft_key=draft_key, draft_id=existing["draft_id"], version=existing["version"],
                asset_id=asset_id, content_hash=content_hash,
                research_package_id=research_package_id, editorial_brief_id=editorial_brief_id,
                approved_claim_ids=tuple(stored_claims), created_at=existing["created_at"].isoformat(),
            )
        version = store.conn.execute(
            "SELECT COALESCE(MAX(version),0)+1 AS next_version FROM content_draft_versions WHERE draft_key=%s",
            (draft_key,),
        ).fetchone()["next_version"]
        draft_id = hashlib.sha256((draft_key + "|" + str(version) + "|" + content_hash).encode("utf-8")).hexdigest()
        created_at = datetime.now(timezone.utc)
        store.conn.execute(
            "INSERT INTO content_draft_versions (draft_key,version,draft_id,asset_id,content_hash,research_package_id,editorial_brief_id,approved_claim_ids_json,content,created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)",
            (draft_key, version, draft_id, asset_id, content_hash, research_package_id,
             editorial_brief_id, claims_json, content, created_at),
        )
    return DraftRecord(
        draft_key=draft_key, draft_id=draft_id, version=version, asset_id=asset_id,
        content_hash=content_hash, research_package_id=research_package_id,
        editorial_brief_id=editorial_brief_id, approved_claim_ids=claims,
        created_at=created_at.isoformat(),
    )


def _load_latest_draft(store, draft_key: str) -> Optional[dict]:
    if not isinstance(draft_key, str) or not draft_key.strip():
        raise ValueError("draft_key is required")
    row = store.conn.execute(
        "SELECT draft_id,version,asset_id,content_hash,research_package_id,editorial_brief_id,approved_claim_ids_json,content,created_at "
        "FROM content_draft_versions WHERE draft_key=%s ORDER BY version DESC LIMIT 1",
        (draft_key,),
    ).fetchone()
    if row is None:
        return None
    claims = row["approved_claim_ids_json"]
    if isinstance(claims, str):
        claims = json.loads(claims)
    return {
        "draft_id": row["draft_id"], "version": row["version"], "asset_id": row["asset_id"],
        "content_hash": row["content_hash"], "research_package_id": row["research_package_id"],
        "editorial_brief_id": row["editorial_brief_id"], "approved_claim_ids": claims,
        "content": row["content"], "created_at": row["created_at"].isoformat(),
    }

[executed on device: localhost (bd830869-fbae-4825-ae7b-5044d6161090)]
