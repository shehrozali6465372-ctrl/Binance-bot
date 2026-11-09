"""Read-only importer for documented Binance CMS announcement events.

The importer reads the worker's PostgreSQL ledger and writes validated evidence
into the existing Layer 1 SQLite store. It never calls the Square publisher.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence

from layer1.foundation import AnnouncementEvidence

# Ticker matching is deliberately conservative: only uppercase symbols in
# parentheses are accepted. Free-standing words are too ambiguous for identity.
_EXPLICIT_TICKER = re.compile(r"\(([A-Z0-9]{2,10})\)")
_CANONICAL_ASSET_ID = re.compile(r"^coingecko:[a-z0-9-]+$")

RECENT_ANNOUNCEMENTS_SQL = """
SELECT source_id, content_hash, event_type, title, body, publisher,
       source_url, published_at, observed_at
FROM (
    SELECT DISTINCT ON (source_id)
           source_id, content_hash, event_type, title, body, publisher,
           source_url, published_at, observed_at, inserted_at
    FROM binance_announcement_events
    WHERE published_at >= %s
      AND published_at <= %s
      AND topic = 'com_announcement_en'
      AND publisher = 'Binance'
    ORDER BY source_id, published_at DESC, observed_at DESC, inserted_at DESC
) AS latest
ORDER BY published_at DESC, source_id
LIMIT %s
"""


def _iso_utc(value: Any, field: str) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} is not a valid timestamp") from exc
    else:
        raise ValueError(f"{field} is not a timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _candidate_symbol_index(candidates: Sequence[Any]) -> tuple[dict[str, str], set[str]]:
    by_symbol: dict[str, set[str]] = defaultdict(set)
    for candidate in candidates:
        symbol = getattr(candidate, "symbol", "")
        asset_id = getattr(candidate, "asset_id", "")
        if (
            isinstance(symbol, str)
            and re.fullmatch(r"[A-Za-z0-9]{2,10}", symbol)
            and isinstance(asset_id, str)
            and _CANONICAL_ASSET_ID.fullmatch(asset_id)
        ):
            by_symbol[symbol.upper()].add(asset_id)
    ambiguous = {symbol for symbol, ids in by_symbol.items() if len(ids) != 1}
    unique = {symbol: next(iter(ids)) for symbol, ids in by_symbol.items() if len(ids) == 1}
    return unique, ambiguous


def _matched_asset_ids(title: str, body: str, symbol_index: Mapping[str, str],
                       ambiguous_symbols: set[str]) -> tuple[str, ...]:
    matches = set()
    for text in (title, body):
        for match in _EXPLICIT_TICKER.finditer(text):
            symbol = match.group(1)
            if symbol not in ambiguous_symbols and symbol in symbol_index:
                matches.add(symbol_index[symbol])
    return tuple(sorted(matches))


def import_recent_binance_announcements(
    database_url: str,
    candidates: Sequence[Any],
    store: Any,
    *,
    connect_factory: Callable[..., Any] | None = None,
    now: datetime | None = None,
    lookback_days: int = 7,
    max_rows: int = 250,
) -> dict[str, Any]:
    """Read recent CMS rows and persist only unambiguous candidate-linked evidence.

    The PostgreSQL connection requires TLS and uses a read-only default
    transaction. A custom connector can be injected by tests; no network is
    used by the test suite.
    """
    if not isinstance(database_url, str) or not database_url.strip():
        raise ValueError("announcement database URL is required")
    if isinstance(lookback_days, bool) or not isinstance(lookback_days, int) or not 1 <= lookback_days <= 30:
        raise ValueError("lookback_days must be between 1 and 30")
    if isinstance(max_rows, bool) or not isinstance(max_rows, int) or not 1 <= max_rows <= 1000:
        raise ValueError("max_rows must be between 1 and 1000")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must include a timezone")
    current = current.astimezone(timezone.utc)

    if connect_factory is None:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg is required when ANNOUNCEMENT_DATABASE_URL is configured") from exc
        connect_factory = psycopg.connect

    symbol_index, ambiguous_symbols = _candidate_symbol_index(candidates)
    result = {
        "rows_read": 0,
        "evidence_saved": 0,
        "unmatched_rows": 0,
        "invalid_rows": 0,
        "ambiguous_symbols": sorted(ambiguous_symbols),
        "by_asset_id": defaultdict(list),
    }
    connection = None
    cursor = None
    try:
        connection = connect_factory(
            database_url,
            connect_timeout=5,
            sslmode="require",
            options="-c default_transaction_read_only=on",
        )
        cursor = connection.cursor()
        cursor.execute(
            RECENT_ANNOUNCEMENTS_SQL,
            (current - timedelta(days=lookback_days), current + timedelta(minutes=5), max_rows),
        )
        rows = cursor.fetchall()
        result["rows_read"] = len(rows)

        for row in rows:
            try:
                (
                    source_id, content_hash, event_type, title, body, publisher,
                    source_url, published_at, observed_at,
                ) = row
                if not all(isinstance(value, str) and value.strip() for value in (
                    source_id, content_hash, event_type, title, publisher, source_url
                )):
                    raise ValueError("announcement identity or provenance is missing")
                if not isinstance(body, str):
                    raise ValueError("announcement body must be text")
                asset_ids = _matched_asset_ids(title, body, symbol_index, ambiguous_symbols)
                if not asset_ids:
                    result["unmatched_rows"] += 1
                    continue
                evidence = AnnouncementEvidence(
                    source_id=source_id,
                    source_url=source_url,
                    publisher=publisher,
                    event_type=event_type,
                    title=title,
                    published_at=_iso_utc(published_at, "published_at"),
                    observed_at=_iso_utc(observed_at, "observed_at"),
                    asset_ids=asset_ids,
                    content_hash=content_hash,
                )
                evidence.validate()
                store.save_announcement(evidence)
                result["evidence_saved"] += 1
                for asset_id in asset_ids:
                    result["by_asset_id"][asset_id].append(evidence)
            except (TypeError, ValueError, OverflowError):
                result["invalid_rows"] += 1
                continue
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    result["by_asset_id"] = dict(result["by_asset_id"])
    return result
