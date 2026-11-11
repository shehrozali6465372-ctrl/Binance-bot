"""Layer 1: Foundation & Market Intelligence.

Deterministic modular-monolith components for modules 1–7.
No synthetic data, ticker-only eligibility, or implicit publication authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence
from urllib.parse import urlparse


LAYER1_VERSION = "1.1.0"
SCORE_VERSION = "layer1-relevance-v1"
OFFICIAL_BINANCE_HOSTS = {"binance.com", "www.binance.com", "developers.binance.com"}
ALLOWED_ANNOUNCEMENT_TYPES = {
    "listing", "delisting", "suspension", "maintenance", "upgrade",
    "governance", "integration", "security_incident", "launch", "release", "other",
}


def _parse_env_bool(name: str, value: Optional[str], default: bool) -> bool:
    """Parse explicit boolean environment values without silently guessing."""
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be an explicit boolean (true/false)")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str, allow_future: bool = False) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps must include timezone")
    normalized = parsed.astimezone(timezone.utc)
    if not allow_future and normalized.timestamp() > time.time() + 300:
        raise ValueError("timestamp is more than 5 minutes in the future")
    return normalized


@dataclass(frozen=True)
class AgentConfig:
    database_path: str = "agent.db"
    http_timeout_seconds: int = 15
    market_data_ttl_seconds: int = 60
    eligibility_ttl_seconds: int = 300
    max_candidates: int = 50
    max_daily_posts: int = 6
    dry_run: bool = True
    allowed_quote_assets: tuple[str, ...] = ("USDT",)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> "AgentConfig":
        quotes = tuple(
            item.strip().upper()
            for item in environ.get("BINANCE_ALLOWED_QUOTE_ASSETS", "USDT").split(",")
            if item.strip()
        )
        cfg = cls(
            database_path=environ.get("DATABASE_PATH", "agent.db"),
            http_timeout_seconds=int(environ.get("HTTP_TIMEOUT_SECONDS", "15")),
            market_data_ttl_seconds=int(environ.get("MARKET_DATA_TTL_SECONDS", "60")),
            eligibility_ttl_seconds=int(environ.get("ELIGIBILITY_TTL_SECONDS", "300")),
            max_candidates=int(environ.get("MAX_CANDIDATES", "50")),
            max_daily_posts=int(environ.get("MAX_DAILY_POSTS", "6")),
            dry_run=_parse_env_bool("DRY_RUN", environ.get("DRY_RUN"), True),
            allowed_quote_assets=quotes,
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not isinstance(self.database_path, str) or not self.database_path.strip():
            raise ValueError("DATABASE_PATH must be non-empty")
        for name in ("http_timeout_seconds", "market_data_ttl_seconds", "eligibility_ttl_seconds",
                     "max_candidates", "max_daily_posts"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.dry_run, bool):
            raise ValueError("dry_run must be boolean")
        if not self.allowed_quote_assets or any(
            not isinstance(q, str) or not q or not q.isalnum() or q != q.upper()
            for q in self.allowed_quote_assets
        ):
            raise ValueError("quote assets must be non-empty uppercase alphanumeric symbols")
        if len(set(self.allowed_quote_assets)) != len(self.allowed_quote_assets):
            raise ValueError("quote assets must not contain duplicates")


@dataclass(frozen=True)
class RunContext:
    run_id: str
    started_at: str
    config_hash: str
    config: AgentConfig


class RunLease:
    """Persistent single-run lease; a stale lease is not silently stolen."""
    def __init__(self, database_path: str):
        from pathlib import Path
        Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(database_path, timeout=30, isolation_level=None)
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS layer1_run_lease (
            lease_name TEXT PRIMARY KEY, run_id TEXT NOT NULL, acquired_at TEXT NOT NULL
        )""")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS layer1_runs (
            run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
            status TEXT NOT NULL, config_hash TEXT NOT NULL, summary_json TEXT
        )""")
        self.run_id: Optional[str] = None

    def inspect_active(self) -> Optional[dict[str, str]]:
        """Return the current lease and run state without mutating recovery state.

        A RUNNING row may belong to a live process or a process that crashed.
        This method intentionally does not infer liveness from age and never
        releases or marks a lease complete.
        """
        row = self.conn.execute(
            "SELECT l.run_id, l.acquired_at, r.started_at, r.status, r.config_hash "
            "FROM layer1_run_lease AS l "
            "LEFT JOIN layer1_runs AS r ON r.run_id = l.run_id "
            "WHERE l.lease_name='agent'"
        ).fetchone()
        if row is None:
            return None
        return {
            "run_id": str(row[0]),
            "acquired_at": str(row[1]),
            "started_at": str(row[2] or ""),
            "status": str(row[3] or "MISSING_RUN_RECORD"),
            "config_hash": str(row[4] or ""),
        }

    def acquire(self, context: RunContext) -> None:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            existing = self.conn.execute(
                "SELECT run_id, acquired_at FROM layer1_run_lease WHERE lease_name='agent'"
            ).fetchone()
            if existing:
                raise RuntimeError(f"agent lease already held by run {existing[0]} since {existing[1]}")
            self.conn.execute(
                "INSERT INTO layer1_run_lease VALUES ('agent', ?, ?)",
                (context.run_id, context.started_at),
            )
            self.conn.execute(
                "INSERT INTO layer1_runs(run_id, started_at, status, config_hash) VALUES (?, ?, 'RUNNING', ?)",
                (context.run_id, context.started_at, context.config_hash),
            )
            self.conn.commit()
            self.run_id = context.run_id
        except Exception:
            self.conn.rollback()
            raise

    def finish(self, status: str, summary: Mapping[str, Any] | None = None) -> None:
        if not self.run_id:
            return
        allowed_statuses = {"SUCCEEDED", "NO_CANDIDATE_OR_BLOCKED", "FAILED", "INTERRUPTED"}
        if status not in allowed_statuses:
            raise ValueError(f"unsupported run status: {status}")
        encoded_summary = json.dumps(dict(summary or {}), sort_keys=True, allow_nan=False)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = self.conn.execute(
                "UPDATE layer1_runs SET finished_at=?, status=?, summary_json=? "
                "WHERE run_id=? AND status='RUNNING'",
                (utc_now(), status, encoded_summary, self.run_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("run record is missing or no longer RUNNING; refusing lease release")
            lease_cursor = self.conn.execute(
                "DELETE FROM layer1_run_lease WHERE lease_name='agent' AND run_id=?",
                (self.run_id,),
            )
            if lease_cursor.rowcount != 1:
                raise RuntimeError("run lease ownership was lost; refusing to mark run complete")
            self.conn.commit()
            self.run_id = None
        except Exception:
            self.conn.rollback()
            raise

    def close(self) -> None:
        self.conn.close()


class ConfigurationOrchestrator:
    def __init__(self, config: AgentConfig):
        config.validate()
        self.config = config

    def create_context(self, runtime_metadata: Optional[Mapping[str, Any]] = None) -> RunContext:
        safe_metadata = dict(runtime_metadata or {})
        try:
            config_json = json.dumps({
                "layer1": {
                    **self.config.__dict__,
                    "allowed_quote_assets": list(self.config.allowed_quote_assets),
                },
                "runtime": safe_metadata,
            }, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("runtime metadata must be finite JSON-compatible non-secret values") from exc
        return RunContext(
            run_id=str(uuid.uuid4()),
            started_at=utc_now(),
            config_hash=hashlib.sha256(config_json.encode()).hexdigest(),
            config=self.config,
        )


@dataclass(frozen=True)
class AssetIdentity:
    asset_id: str
    asset_name: str
    base_asset: str
    quote_asset: str


@dataclass(frozen=True)
class EligibilityDecision:
    status: str
    asset_id: str
    symbol: str
    eligible_pairs: tuple[str, ...] = ()
    reason: str = ""
    verified_at: str = ""
    source: str = "https://api.binance.com/api/v3/exchangeInfo"


class BinanceListingEligibilityEngine:
    """Exact Binance Spot pair eligibility against a fresh official metadata snapshot."""
    def __init__(self, allowed_quote_assets: Sequence[str] = ("USDT",), max_snapshot_age_seconds: int = 300):
        normalized = [str(q).upper() for q in allowed_quote_assets]
        if not normalized or len(set(normalized)) != len(normalized) or any(not q.isalnum() for q in normalized):
            raise ValueError("allowed quote assets must be unique uppercase alphanumeric symbols")
        if isinstance(max_snapshot_age_seconds, bool) or not isinstance(max_snapshot_age_seconds, int) or max_snapshot_age_seconds <= 0:
            raise ValueError("max_snapshot_age_seconds must be a positive integer")
        self.allowed_quotes = set(normalized)
        self.max_snapshot_age_seconds = max_snapshot_age_seconds

    def evaluate(self, identity: AssetIdentity, exchange_info: Mapping[str, Any],
                 verified_at: Optional[str] = None) -> EligibilityDecision:
        if not identity.asset_id or not identity.asset_name or not identity.base_asset:
            return EligibilityDecision("UNVERIFIED", identity.asset_id, identity.base_asset,
                                       reason="canonical asset identity incomplete")
        if identity.quote_asset not in self.allowed_quotes:
            return EligibilityDecision("UNVERIFIED", identity.asset_id, identity.base_asset,
                                       reason="requested quote asset is not allowed by configuration")
        if not isinstance(exchange_info, Mapping):
            return EligibilityDecision("UNVERIFIED", identity.asset_id, identity.base_asset,
                                       reason="exchangeInfo snapshot is not an object")
        snapshot_time = verified_at
        if not snapshot_time:
            server_time = exchange_info.get("serverTime")
            if isinstance(server_time, (int, float)) and not isinstance(server_time, bool):
                snapshot_time = datetime.fromtimestamp(float(server_time) / 1000.0, timezone.utc).isoformat()
        if not snapshot_time:
            return EligibilityDecision("UNVERIFIED", identity.asset_id, identity.base_asset,
                                       reason="exchangeInfo snapshot timestamp missing")
        try:
            normalized_snapshot_time = _parse_time(snapshot_time)
        except (TypeError, ValueError, OverflowError):
            return EligibilityDecision("UNVERIFIED", identity.asset_id, identity.base_asset,
                                       reason="exchangeInfo snapshot timestamp invalid")
        age_seconds = (datetime.now(timezone.utc) - normalized_snapshot_time).total_seconds()
        if age_seconds < -300 or age_seconds > self.max_snapshot_age_seconds:
            return EligibilityDecision("UNVERIFIED", identity.asset_id, identity.base_asset,
                                       reason="exchangeInfo snapshot is stale or clock-skewed",
                                       verified_at=normalized_snapshot_time.isoformat())
        symbols = exchange_info.get("symbols")
        if not isinstance(symbols, list) or not symbols:
            return EligibilityDecision("UNVERIFIED", identity.asset_id, identity.base_asset,
                                       reason="exchangeInfo symbols missing/empty",
                                       verified_at=normalized_snapshot_time.isoformat())
        matches = []
        for item in symbols:
            if not isinstance(item, dict):
                continue
            if (item.get("baseAsset") != identity.base_asset
                or item.get("quoteAsset") != identity.quote_asset
                or item.get("quoteAsset") not in self.allowed_quotes
                or item.get("status") != "TRADING"
                or item.get("isSpotTradingAllowed") is not True):
                continue
            pair = item.get("symbol")
            if isinstance(pair, str) and pair and pair.isalnum():
                matches.append(pair)
        if not matches:
            return EligibilityDecision("INELIGIBLE", identity.asset_id, identity.base_asset,
                                       reason="no active exact Spot pair for canonical base/quote identity",
                                       verified_at=normalized_snapshot_time.isoformat())
        return EligibilityDecision("ELIGIBLE", identity.asset_id, identity.base_asset,
                                   tuple(sorted(set(matches))), "active exact Binance Spot pair verified",
                                   normalized_snapshot_time.isoformat())


@dataclass(frozen=True)
class MarketObservation:
    asset_id: str
    provider: str
    endpoint: str
    observed_at: str
    price: Optional[float] = None
    currency: str = "USD"
    change_24h: Optional[float] = None
    volume_24h: Optional[float] = None
    market_cap: Optional[float] = None
    history: tuple[float, ...] = ()
    published_at: Optional[str] = None
    data_hash: str = ""

    def validate(self) -> None:
        if not all(isinstance(value, str) and value.strip() for value in
                   (self.asset_id, self.provider, self.endpoint, self.currency)):
            raise ValueError("market observation identity/provenance/currency missing")
        if not self.currency.isalnum() or self.currency != self.currency.upper():
            raise ValueError("market observation currency must be an uppercase asset/currency code")
        _parse_time(self.observed_at)
        if self.published_at:
            _parse_time(self.published_at)
        if self.provider == "coingecko_markets" and not self.published_at:
            raise ValueError("CoinGecko market observation is missing provider last_updated time")
        for name in ("price", "change_24h", "volume_24h", "market_cap"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            ):
                raise ValueError(f"invalid {name}")
        if self.price is not None and self.price <= 0:
            raise ValueError("price must be positive")
        for name in ("volume_24h", "market_cap"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative")
        if not isinstance(self.history, (tuple, list)):
            raise ValueError("history must be a sequence of provider observations")
        if any(
            isinstance(point, bool) or not isinstance(point, (int, float))
            or not math.isfinite(point) or point <= 0
            for point in self.history
        ):
            raise ValueError("history must contain finite positive provider observations")


class MarketDataIntelligenceEngine:
    """Normalizes provider payloads; caller supplies an approved documented adapter."""
    def __init__(self, fetch_json: Callable[[str, int], Any], timeout: int = 15):
        self.fetch_json = fetch_json
        self.timeout = timeout

    def fetch_binance_24h(self, symbol: str, asset_id: str, quote_asset: str = "USDT") -> MarketObservation:
        if not isinstance(symbol, str) or not symbol.isalnum() or not symbol.isupper() or not asset_id:
            raise ValueError("exact uppercase Binance symbol and canonical asset_id are required")
        if not isinstance(quote_asset, str) or not quote_asset.isalnum() or not quote_asset.isupper():
            raise ValueError("quote_asset must be an uppercase alphanumeric code")
        if not symbol.endswith(quote_asset):
            raise ValueError("Binance symbol does not end with the requested quote asset")
        url = f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={symbol}"
        payload = self.fetch_json(url, self.timeout)
        if not isinstance(payload, dict) or payload.get("symbol") != symbol:
            raise ValueError("Binance ticker response schema/symbol mismatch")
        close_time = payload.get("closeTime")
        if isinstance(close_time, bool) or not isinstance(close_time, (int, float)) or close_time <= 0:
            raise ValueError("Binance ticker response missing a valid provider closeTime")
        try:
            observed_at = datetime.fromtimestamp(float(close_time) / 1000, timezone.utc).isoformat()
            observation = MarketObservation(
                asset_id=asset_id, provider="binance_spot", endpoint=url, observed_at=observed_at,
                price=float(payload["lastPrice"]), currency=quote_asset,
                change_24h=float(payload["priceChangePercent"]),
                volume_24h=float(payload["quoteVolume"]),
            )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Binance ticker response contains missing or invalid required fields") from exc
        observation.validate()
        return observation


@dataclass(frozen=True)
class AnnouncementEvidence:
    source_id: str
    source_url: str
    publisher: str
    event_type: str
    title: str
    published_at: str
    observed_at: str
    asset_ids: tuple[str, ...] = ()
    content_hash: str = ""

    updated_at: Optional[str] = None
    event_at: Optional[str] = None

    def validate(self) -> None:
        parsed_url = urlparse(self.source_url)
        host = (parsed_url.hostname or "").lower()
        if not all(isinstance(value, str) and value.strip() for value in
                   (self.source_id, self.source_url, self.title, self.publisher)):
            raise ValueError("announcement identity/publisher/title/source URL missing")
        if (
            parsed_url.scheme != "https" or parsed_url.username or parsed_url.password
            or parsed_url.port not in (None, 443)
            or not any(host == allowed or host.endswith("." + allowed) for allowed in OFFICIAL_BINANCE_HOSTS)
        ):
            raise ValueError("announcement source is not an approved HTTPS Binance host")
        if self.event_type not in ALLOWED_ANNOUNCEMENT_TYPES:
            raise ValueError("unsupported announcement event type")
        if not isinstance(self.asset_ids, tuple) or any(not isinstance(item, str) or not item for item in self.asset_ids):
            raise ValueError("announcement asset identities must be non-empty canonical IDs")
        _parse_time(self.published_at)
        _parse_time(self.observed_at)
        if self.updated_at:
            updated = _parse_time(self.updated_at)
            if updated < _parse_time(self.published_at):
                raise ValueError("announcement updated_at cannot precede published_at")
        if self.event_at:
            _parse_time(self.event_at, allow_future=True)


class AnnouncementIntelligenceEngine:
    """Accepts evidence from a documented official adapter; no private BAPI scraping."""
    def __init__(self, official_source_adapter: Optional[Callable[[], Iterable[AnnouncementEvidence]]] = None):
        self.adapter = official_source_adapter

    def fetch(self) -> tuple[list[AnnouncementEvidence], str]:
        if self.adapter is None:
            return [], "UNAVAILABLE: no verified documented official announcement adapter configured"
        latest_by_source: dict[str, AnnouncementEvidence] = {}
        for item in self.adapter():
            item.validate()
            previous = latest_by_source.get(item.source_id)
            if previous is None:
                latest_by_source[item.source_id] = item
                continue
            previous_version = previous.updated_at or previous.published_at
            current_version = item.updated_at or item.published_at
            if _parse_time(current_version) > _parse_time(previous_version):
                latest_by_source[item.source_id] = item
            elif _parse_time(current_version) == _parse_time(previous_version) and item.content_hash != previous.content_hash:
                raise ValueError(f"conflicting announcement revisions for source_id={item.source_id}")
        return sorted(latest_by_source.values(), key=lambda item: (item.published_at, item.source_id)), "AVAILABLE"


@dataclass(frozen=True)
class TrendSignal:
    topic: str
    source: str
    observed_at: str
    rank: Optional[int] = None
    asset_ids: tuple[str, ...] = ()
    source_item_id: str = ""
    content_hash: str = ""

    def validate(self) -> None:
        if not isinstance(self.topic, str) or not self.topic.strip() or not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("trend topic/source missing")
        _parse_time(self.observed_at)
        if self.rank is not None and (
            isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank <= 0
        ):
            raise ValueError("trend rank must be a positive integer")
        if not isinstance(self.asset_ids, tuple) or any(not isinstance(item, str) or not item for item in self.asset_ids):
            raise ValueError("trend asset identities must be canonical non-empty IDs")
        if self.content_hash and not isinstance(self.content_hash, str):
            raise ValueError("trend content_hash must be a string")


class TrendingNarrativeIntelligenceEngine:
    """Only accepts sourced observations; preserves independent-source provenance."""
    def normalize(self, signals: Iterable[TrendSignal]) -> list[TrendSignal]:
        selected: dict[tuple[str, str, str], TrendSignal] = {}
        for signal in signals:
            signal.validate()
            key = (signal.topic.casefold(), signal.source.casefold(), signal.source_item_id)
            previous = selected.get(key)
            if previous is None:
                selected[key] = signal
                continue
            # For repeated observations of one provider item, keep its newest
            # version; rank is only a deterministic tie-breaker, not event proof.
            current_time = _parse_time(signal.observed_at)
            previous_time = _parse_time(previous.observed_at)
            if current_time > previous_time or (
                current_time == previous_time and (signal.rank or 10**9) < (previous.rank or 10**9)
            ):
                selected[key] = signal
        return sorted(selected.values(), key=lambda s: (s.rank or 10**9, s.topic.casefold(), s.source.casefold()))

    @staticmethod
    def independent_source_count(signals: Iterable[TrendSignal]) -> int:
        """Count independent source/content pairs, not copied syndication."""
        groups = set()
        for signal in signals:
            signal.validate()
            fingerprint = signal.content_hash or f"{signal.source.casefold()}:{signal.source_item_id}"
            groups.add(fingerprint)
        return len(groups)


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    asset_id: str
    event_ids: tuple[str, ...]
    eligibility: EligibilityDecision
    market_observation_ids: tuple[str, ...]
    trend_signal_ids: tuple[str, ...]
    state: str
    rejection_reasons: tuple[str, ...] = ()


class CandidateDiscoveryFilteringEngine:
    def __init__(self, max_market_age_seconds: int = 1800, max_event_age_seconds: int = 604800,
                 max_trend_age_seconds: int = 3600):
        self.max_market_age_seconds = max_market_age_seconds
        self.max_event_age_seconds = max_event_age_seconds
        self.max_trend_age_seconds = max_trend_age_seconds

    def build(self, identity: AssetIdentity, eligibility: EligibilityDecision,
              markets: Sequence[MarketObservation], events: Sequence[AnnouncementEvidence],
              trends: Sequence[TrendSignal]) -> Candidate:
        reasons = []
        if eligibility.asset_id != identity.asset_id:
            reasons.append("canonical_asset_identity_mismatch")
        if eligibility.status != "ELIGIBLE":
            reasons.append("binance_spot_eligibility_" + eligibility.status.lower())
        if not eligibility.eligible_pairs:
            reasons.append("binance_spot_exact_pair_missing")
        matching_markets = [m for m in markets if m.asset_id == identity.asset_id]
        matching_events = [e for e in events if identity.asset_id in e.asset_ids]
        matching_trends = [t for t in trends if identity.asset_id in t.asset_ids]

        valid_markets = []
        for item in matching_markets:
            try:
                item.validate()
                valid_markets.append(item)
            except (TypeError, ValueError):
                reasons.append("market_observation_invalid")
        valid_events = []
        for item in matching_events:
            try:
                item.validate()
                valid_events.append(item)
            except (TypeError, ValueError):
                reasons.append("announcement_evidence_invalid")
        valid_trends = []
        for item in matching_trends:
            try:
                item.validate()
                valid_trends.append(item)
            except (TypeError, ValueError):
                reasons.append("trend_signal_invalid")

        now = datetime.now(timezone.utc)
        fresh_markets = [
            m for m in valid_markets
            if (now - _parse_time(m.published_at or m.observed_at)).total_seconds()
            <= self.max_market_age_seconds
        ]
        fresh_events = [
            e for e in valid_events
            if (now - _parse_time(e.updated_at or e.published_at)).total_seconds()
            <= self.max_event_age_seconds
        ]
        fresh_trends = [
            t for t in valid_trends
            if (now - _parse_time(t.observed_at)).total_seconds() <= self.max_trend_age_seconds
        ]
        if valid_markets and not fresh_markets:
            reasons.append("market_observation_stale")
        if valid_events and not fresh_events:
            reasons.append("announcement_evidence_stale")
        if valid_trends and not fresh_trends:
            reasons.append("trend_signal_stale")
        matching_markets, matching_events, matching_trends = fresh_markets, fresh_events, fresh_trends
        if not matching_markets and not matching_events and not matching_trends:
            reasons.append("no_source_backed_discovery_signal")

        # Candidate identity is stable across repeated scans but changes when an
        # event's content/revision or a meaningful trend item changes.
        event_refs = sorted(
            f"{e.source_id}:{e.content_hash}:{e.updated_at or e.published_at}"
            for e in matching_events
        )
        market_refs = sorted(set(f"{m.provider}:{m.endpoint}:{m.currency}" for m in matching_markets))
        trend_refs = sorted(set(
            f"{t.topic.casefold()}:{t.source.casefold()}:{t.source_item_id}:{t.content_hash}"
            for t in matching_trends
        ))
        fingerprint = json.dumps(
            {"asset_id": identity.asset_id, "eligible_pairs": list(eligibility.eligible_pairs),
             "events": event_refs, "markets": market_refs, "trends": trend_refs},
            sort_keys=True, separators=(",", ":"),
        )
        cid = hashlib.sha256(fingerprint.encode()).hexdigest()
        return Candidate(cid, identity.asset_id, tuple(sorted(e.source_id for e in matching_events)),
                         eligibility, tuple(sorted(m.data_hash or m.endpoint for m in matching_markets)),
                         tuple(sorted(f"{t.source}:{t.source_item_id or t.topic}" for t in matching_trends)),
                         "READY_FOR_RESEARCH" if not reasons else "REJECTED",
                         tuple(sorted(set(reasons))))


@dataclass(frozen=True)
class RelevanceScore:
    candidate_id: str
    score: float
    components: Mapping[str, Optional[float]]
    score_version: str
    reason: str


class Layer1Store:
    """Auditable persistence for Modules 2, 4, 5, 6 and 7."""
    def __init__(self, database_path: str):
        from pathlib import Path
        Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(database_path, timeout=30)
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS layer1_market_observations (
            observation_key TEXT PRIMARY KEY, asset_id TEXT NOT NULL,
            provider TEXT NOT NULL, endpoint TEXT NOT NULL,
            observed_at TEXT NOT NULL, payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS layer1_announcement_evidence (
            source_id TEXT PRIMARY KEY, source_url TEXT NOT NULL, publisher TEXT NOT NULL,
            event_type TEXT NOT NULL, published_at TEXT NOT NULL, observed_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS layer1_announcement_revisions (
            source_id TEXT NOT NULL, revision_key TEXT NOT NULL,
            first_seen_at TEXT NOT NULL, payload_json TEXT NOT NULL,
            PRIMARY KEY(source_id, revision_key)
        );
        CREATE TABLE IF NOT EXISTS layer1_trend_signals (
            signal_key TEXT PRIMARY KEY, topic TEXT NOT NULL, source TEXT NOT NULL,
            observed_at TEXT NOT NULL, payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS layer1_candidates (
            candidate_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, state TEXT NOT NULL,
            rejection_reasons_json TEXT NOT NULL, evidence_refs_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS layer1_candidate_rejections (
            rejection_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, reason_code TEXT NOT NULL,
            source TEXT NOT NULL, source_observed_at TEXT, recorded_at TEXT NOT NULL,
            details_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS layer1_candidate_scores (
            candidate_id TEXT NOT NULL, score_version TEXT NOT NULL, score REAL NOT NULL,
            components_json TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(candidate_id, score_version)
        );
        """)

    def save_market(self, observation: MarketObservation) -> None:
        observation.validate()
        payload = json.dumps(observation.__dict__, sort_keys=True)
        key = hashlib.sha256(
            f"{observation.asset_id}|{observation.provider}|{observation.endpoint}|{observation.observed_at}".encode()
        ).hexdigest()
        self.conn.execute(
            "INSERT OR REPLACE INTO layer1_market_observations VALUES (?, ?, ?, ?, ?, ?)",
            (key, observation.asset_id, observation.provider, observation.endpoint,
             observation.observed_at, payload),
        )
        self.conn.commit()

    def save_announcement(self, evidence: AnnouncementEvidence) -> None:
        evidence.validate()
        payload = json.dumps(evidence.__dict__, sort_keys=True, allow_nan=False)
        revision_key = evidence.content_hash or hashlib.sha256(payload.encode()).hexdigest()
        self.conn.execute(
            "INSERT OR IGNORE INTO layer1_announcement_revisions VALUES (?, ?, ?, ?)",
            (evidence.source_id, revision_key, utc_now(), payload),
        )
        self.conn.execute(
            "INSERT INTO layer1_announcement_evidence VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source_id) DO UPDATE SET source_url=excluded.source_url, "
            "publisher=excluded.publisher, event_type=excluded.event_type, "
            "published_at=excluded.published_at, observed_at=excluded.observed_at, "
            "payload_json=excluded.payload_json",
            (evidence.source_id, evidence.source_url, evidence.publisher, evidence.event_type,
             evidence.published_at, evidence.observed_at, payload),
        )
        self.conn.commit()

    def save_trend(self, signal: TrendSignal) -> None:
        signal.validate()
        key = hashlib.sha256(
            f"{signal.source}|{signal.source_item_id}|{signal.topic}|{signal.content_hash}|{signal.observed_at}".encode()
        ).hexdigest()
        self.conn.execute(
            "INSERT OR REPLACE INTO layer1_trend_signals VALUES (?, ?, ?, ?, ?)",
            (key, signal.topic, signal.source, signal.observed_at,
             json.dumps(signal.__dict__, sort_keys=True)),
        )
        self.conn.commit()

    def save_candidate(self, candidate: Candidate) -> None:
        evidence = {
            "events": list(candidate.event_ids),
            "markets": list(candidate.market_observation_ids),
            "trends": list(candidate.trend_signal_ids),
            "eligibility": candidate.eligibility.__dict__,
        }
        self.conn.execute(
            "INSERT OR REPLACE INTO layer1_candidates VALUES (?, ?, ?, ?, ?, ?)",
            (candidate.candidate_id, candidate.asset_id, candidate.state,
             json.dumps(list(candidate.rejection_reasons)),
             json.dumps(evidence, sort_keys=True), utc_now()),
        )
        self.conn.commit()

    def save_rejection(
        self, symbol: str, reason_code: str, source: str,
        source_observed_at: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Persist a rejected raw input with a stable fingerprint and explicit reason."""
        if not all(
            isinstance(value, str) and value.strip()
            for value in (symbol, reason_code, source)
        ):
            raise ValueError("candidate rejection symbol/reason/source must be non-empty")
        payload = json.dumps(dict(details or {}), sort_keys=True, allow_nan=False)
        fingerprint = json.dumps(
            {
                "symbol": symbol.upper(),
                "reason_code": reason_code,
                "source": source,
                "source_observed_at": source_observed_at,
                "details": json.loads(payload),
            },
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
        rejection_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        self.conn.execute(
            "INSERT OR IGNORE INTO layer1_candidate_rejections "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rejection_id, symbol.upper(), reason_code, source,
             source_observed_at, utc_now(), payload),
        )
        self.conn.commit()

    def save_score(self, score: RelevanceScore) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO layer1_candidate_scores VALUES (?, ?, ?, ?, ?, ?)",
            (score.candidate_id, score.score_version, score.score,
             json.dumps(dict(score.components), sort_keys=True), score.reason, utc_now()),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


class RelevanceScoringEngine:
    """Explainable ranking only. It cannot authorize publication."""
    WEIGHTS = {"event_materiality": 0.30, "source_credibility": 0.25,
               "freshness": 0.20, "audience_relevance": 0.15, "novelty": 0.10}

    def score(self, candidate: Candidate, components: Mapping[str, Optional[float]]) -> RelevanceScore:
        if candidate.state != "READY_FOR_RESEARCH":
            return RelevanceScore(candidate.candidate_id, 0.0, dict(components), SCORE_VERSION,
                                  "hard-gated candidate is not eligible for ranking")
        if set(components) != set(self.WEIGHTS):
            raise ValueError("all score components must be explicitly supplied")
        if any(v is None for v in components.values()):
            return RelevanceScore(candidate.candidate_id, 0.0, dict(components), SCORE_VERSION,
                                  "missing score evidence; candidate deferred")
        if any(
            isinstance(v, bool) or not isinstance(v, (int, float))
            or not math.isfinite(float(v)) or not 0 <= float(v) <= 100
            for v in components.values()
        ):
            raise ValueError("score components must be finite numbers between 0 and 100")
        total = sum(float(components[k]) * self.WEIGHTS[k] for k in self.WEIGHTS)
        return RelevanceScore(candidate.candidate_id, round(total, 4), dict(components),
                              SCORE_VERSION, "weighted evidence-backed research-priority score")

    @staticmethod
    def rank(scores: Iterable[RelevanceScore]) -> list[RelevanceScore]:
        """Order research-priority scores deterministically; never grants publication authority."""
        materialized = list(scores)
        if any(not isinstance(item, RelevanceScore) for item in materialized):
            raise TypeError("rank accepts only RelevanceScore records")
        return sorted(materialized, key=lambda item: (-item.score, item.candidate_id))
