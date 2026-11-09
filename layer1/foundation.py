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


LAYER1_VERSION = "1.0.0"
SCORE_VERSION = "layer1-relevance-v1"
OFFICIAL_BINANCE_HOSTS = {"binance.com", "www.binance.com", "developers.binance.com"}
ALLOWED_ANNOUNCEMENT_TYPES = {
    "listing", "delisting", "suspension", "maintenance", "upgrade",
    "governance", "integration", "security_incident", "launch", "release", "other",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include timezone")
    return parsed.astimezone(timezone.utc)


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
            dry_run=environ.get("DRY_RUN", "1").strip().lower() not in {"0", "false", "no"},
            allowed_quote_assets=quotes,
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not self.database_path.strip():
            raise ValueError("DATABASE_PATH must be non-empty")
        for name in ("http_timeout_seconds", "market_data_ttl_seconds", "eligibility_ttl_seconds",
                     "max_candidates", "max_daily_posts"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")
        if not self.allowed_quote_assets:
            raise ValueError("at least one allowed quote asset is required")
        if any(not q.isalnum() for q in self.allowed_quote_assets):
            raise ValueError("quote assets must be alphanumeric symbols")


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
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute(
                "UPDATE layer1_runs SET finished_at=?, status=?, summary_json=? WHERE run_id=?",
                (utc_now(), status, json.dumps(dict(summary or {}), sort_keys=True), self.run_id),
            )
            self.conn.execute(
                "DELETE FROM layer1_run_lease WHERE lease_name='agent' AND run_id=?",
                (self.run_id,),
            )
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

    def create_context(self) -> RunContext:
        config_json = json.dumps({
            **self.config.__dict__,
            "allowed_quote_assets": list(self.config.allowed_quote_assets),
        }, sort_keys=True, separators=(",", ":"))
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
    """Exact Binance Spot pair eligibility. No ticker allow-list fallback."""
    def __init__(self, allowed_quote_assets: Sequence[str] = ("USDT",)):
        self.allowed_quotes = {q.upper() for q in allowed_quote_assets}

    def evaluate(self, identity: AssetIdentity, exchange_info: Mapping[str, Any],
                 verified_at: Optional[str] = None) -> EligibilityDecision:
        if not identity.asset_id or not identity.asset_name or not identity.base_asset:
            return EligibilityDecision("UNVERIFIED", identity.asset_id, identity.base_asset,
                                       reason="canonical asset identity incomplete")
        symbols = exchange_info.get("symbols")
        if not isinstance(symbols, list) or not symbols:
            return EligibilityDecision("UNVERIFIED", identity.asset_id, identity.base_asset,
                                       reason="exchangeInfo symbols missing/empty")
        matches = []
        for item in symbols:
            if not isinstance(item, dict):
                continue
            if (item.get("baseAsset") != identity.base_asset
                or item.get("quoteAsset") not in self.allowed_quotes
                or item.get("status") != "TRADING"
                or item.get("isSpotTradingAllowed") is not True):
                continue
            pair = item.get("symbol")
            if isinstance(pair, str) and pair:
                matches.append(pair)
        if not matches:
            return EligibilityDecision("INELIGIBLE", identity.asset_id, identity.base_asset,
                                       reason="no active Spot pair in configured quote assets",
                                       verified_at=verified_at or utc_now())
        return EligibilityDecision("ELIGIBLE", identity.asset_id, identity.base_asset,
                                   tuple(sorted(set(matches))), "active Binance Spot pair verified",
                                   verified_at or utc_now())


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
        if not self.asset_id or not self.provider or not self.endpoint:
            raise ValueError("market observation identity/provenance missing")
        _parse_time(self.observed_at)
        if self.published_at:
            _parse_time(self.published_at)
        for name in ("price", "change_24h", "volume_24h", "market_cap"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError(f"invalid {name}")
        if self.price is not None and self.price <= 0:
            raise ValueError("price must be positive")
        if any(not isinstance(point, (int, float)) or point <= 0 for point in self.history):
            raise ValueError("history must contain actual positive numeric observations")


class MarketDataIntelligenceEngine:
    """Normalizes provider payloads; caller supplies an approved documented adapter."""
    def __init__(self, fetch_json: Callable[[str, int], Any], timeout: int = 15):
        self.fetch_json = fetch_json
        self.timeout = timeout

    def fetch_binance_24h(self, symbol: str, asset_id: str) -> MarketObservation:
        if not symbol or not asset_id:
            raise ValueError("exact symbol and canonical asset_id are required")
        url = f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={symbol}"
        payload = self.fetch_json(url, self.timeout)
        if not isinstance(payload, dict) or payload.get("symbol") != symbol:
            raise ValueError("Binance ticker response schema/symbol mismatch")
        close_time = payload.get("closeTime")
        observed_at = datetime.fromtimestamp(float(close_time) / 1000, timezone.utc).isoformat() if close_time else utc_now()
        observation = MarketObservation(
            asset_id=asset_id, provider="binance_spot", endpoint=url, observed_at=observed_at,
            price=float(payload["lastPrice"]), currency="USDT",
            change_24h=float(payload["priceChangePercent"]),
            volume_24h=float(payload["quoteVolume"]),
        )
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

    def validate(self) -> None:
        host = (urlparse(self.source_url).hostname or "").lower()
        if not self.source_id or not self.title or not self.publisher:
            raise ValueError("announcement identity/publisher/title missing")
        if not any(host == allowed or host.endswith("." + allowed) for allowed in OFFICIAL_BINANCE_HOSTS):
            raise ValueError("announcement source is not an approved official Binance host")
        if self.event_type not in ALLOWED_ANNOUNCEMENT_TYPES:
            raise ValueError("unsupported announcement event type")
        _parse_time(self.published_at)
        _parse_time(self.observed_at)


class AnnouncementIntelligenceEngine:
    """Accepts evidence from a documented official adapter; no private BAPI scraping."""
    def __init__(self, official_source_adapter: Optional[Callable[[], Iterable[AnnouncementEvidence]]] = None):
        self.adapter = official_source_adapter

    def fetch(self) -> tuple[list[AnnouncementEvidence], str]:
        if self.adapter is None:
            return [], "UNAVAILABLE: no verified documented official announcement adapter configured"
        results = []
        for item in self.adapter():
            item.validate()
            results.append(item)
        return results, "AVAILABLE"


@dataclass(frozen=True)
class TrendSignal:
    topic: str
    source: str
    observed_at: str
    rank: Optional[int] = None
    asset_ids: tuple[str, ...] = ()
    source_item_id: str = ""

    def validate(self) -> None:
        if not self.topic.strip() or not self.source.strip():
            raise ValueError("trend topic/source missing")
        _parse_time(self.observed_at)
        if self.rank is not None and self.rank <= 0:
            raise ValueError("trend rank must be positive")


class TrendingNarrativeIntelligenceEngine:
    """Only accepts sourced observations; static/synthetic narrative fixtures are rejected."""
    def normalize(self, signals: Iterable[TrendSignal]) -> list[TrendSignal]:
        selected: dict[tuple[str, str, str], TrendSignal] = {}
        for signal in signals:
            signal.validate()
            key = (signal.topic.casefold(), signal.source, signal.source_item_id)
            selected.setdefault(key, signal)
        return sorted(selected.values(), key=lambda s: (s.rank or 10**9, s.topic.casefold()))


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
        if eligibility.status != "ELIGIBLE":
            reasons.append("binance_spot_eligibility_" + eligibility.status.lower())
        matching_markets = [m for m in markets if m.asset_id == identity.asset_id]
        matching_events = [e for e in events if identity.asset_id in e.asset_ids]
        matching_trends = [t for t in trends if identity.asset_id in t.asset_ids]
        now = datetime.now(timezone.utc)
        fresh_markets = [m for m in matching_markets if (now - _parse_time(m.observed_at)).total_seconds() <= self.max_market_age_seconds]
        fresh_events = [e for e in matching_events if (now - _parse_time(e.observed_at)).total_seconds() <= self.max_event_age_seconds]
        fresh_trends = [t for t in matching_trends if (now - _parse_time(t.observed_at)).total_seconds() <= self.max_trend_age_seconds]
        if matching_markets and not fresh_markets:
            reasons.append("market_observation_stale")
        if matching_events and not fresh_events:
            reasons.append("announcement_evidence_stale")
        if matching_trends and not fresh_trends:
            reasons.append("trend_signal_stale")
        matching_markets, matching_events, matching_trends = fresh_markets, fresh_events, fresh_trends
        if not matching_markets and not matching_events and not matching_trends:
            reasons.append("no_source_backed_discovery_signal")
        if any(m.asset_id != identity.asset_id for m in matching_markets):
            reasons.append("canonical_asset_identity_mismatch")
        state = "READY_FOR_RESEARCH" if not reasons else "REJECTED"
        fingerprint = "|".join((identity.asset_id, ",".join(sorted(e.source_id for e in matching_events)),
                                ",".join(sorted(m.endpoint for m in matching_markets))))
        cid = hashlib.sha256(fingerprint.encode()).hexdigest()
        return Candidate(cid, identity.asset_id, tuple(sorted(e.source_id for e in matching_events)),
                         eligibility, tuple(sorted(m.data_hash or m.endpoint for m in matching_markets)),
                         tuple(sorted(f"{t.source}:{t.source_item_id or t.topic}" for t in matching_trends)),
                         state, tuple(reasons))


@dataclass(frozen=True)
class RelevanceScore:
    candidate_id: str
    score: float
    components: Mapping[str, Optional[float]]
    score_version: str
    reason: str


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
        if any(not 0 <= float(v) <= 100 for v in components.values()):
            raise ValueError("score components must be between 0 and 100")
        total = sum(float(components[k]) * self.WEIGHTS[k] for k in self.WEIGHTS)
        return RelevanceScore(candidate.candidate_id, round(total, 4), dict(components),
                              SCORE_VERSION, "weighted evidence-backed relevance score")
