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
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
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
class AssetIdentityProof:
    status: str
    asset_id: str
    base_asset: str
    quote_asset: str
    exchange_id: str = "binance"
    market_pair: str = ""
    reason: str = ""
    source: str = "coingecko_coin_tickers"
    verified_at: str = ""
    source_timestamp: str = ""
    ticker_timestamp: str = ""
    data_hash: str = ""
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.status not in {"VERIFIED", "UNVERIFIED"}:
            raise ValueError("asset identity proof status is invalid")
        if not all(isinstance(value, str) and value.strip() for value in (
            self.asset_id, self.base_asset, self.quote_asset, self.exchange_id, self.source, self.reason
        )):
            raise ValueError("asset identity proof provenance is incomplete")
        if self.status == "VERIFIED":
            if self.source != "coingecko_coin_tickers":
                raise ValueError("verified asset identity proof source is not approved")
            if (not self.asset_id.startswith("coingecko:") or not self.base_asset.isalnum()
                    or self.base_asset != self.base_asset.upper() or not self.quote_asset.isalnum()
                    or self.quote_asset != self.quote_asset.upper() or self.exchange_id != "binance"):
                raise ValueError("verified asset identity proof canonical fields are invalid")
            if self.market_pair != f"{self.base_asset}/{self.quote_asset}" or not self.source_timestamp or not self.verified_at:
                raise ValueError("verified asset identity proof is missing exact pair/timestamps")
            if len(self.data_hash) != 64 or any(ch not in "0123456789abcdef" for ch in self.data_hash):
                raise ValueError("verified asset identity proof requires a SHA-256 payload hash")
            _parse_time(self.verified_at)
            _parse_time(self.source_timestamp)
        if not isinstance(self.provider_metadata, Mapping):
            raise ValueError("asset identity proof provider metadata must be a mapping")
        json.dumps(dict(self.provider_metadata), sort_keys=True, allow_nan=False)

    def is_fresh(self, max_age_seconds: int = 900, now: Optional[str] = None) -> bool:
        if self.status != "VERIFIED" or not self.source_timestamp:
            return False
        if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) or max_age_seconds <= 0:
            return False
        try:
            age = (_parse_time(now or utc_now()) - _parse_time(self.source_timestamp)).total_seconds()
            return -300 <= age <= max_age_seconds
        except (TypeError, ValueError, OverflowError):
            return False


class CoinGeckoBinanceIdentityResolver:
    """Prove a canonical CoinGecko ID maps to an exact, fresh Binance ticker."""
    def __init__(self, exchange_id: str = "binance"):
        if not isinstance(exchange_id, str) or not exchange_id.strip():
            raise ValueError("exchange_id must be non-empty")
        self.exchange_id = exchange_id.strip().lower()

    def _unverified(self, asset_id: str, base_asset: str, quote_asset: str,
                    reason: str, verified_at: str, source_timestamp: str = "",
                    data_hash: str = "", provider_metadata: Optional[Mapping[str, Any]] = None) -> AssetIdentityProof:
        return AssetIdentityProof(
            "UNVERIFIED", asset_id, base_asset, quote_asset, self.exchange_id,
            f"{base_asset}/{quote_asset}" if base_asset and quote_asset else "",
            reason, "coingecko_coin_tickers", verified_at, source_timestamp, "", data_hash,
            dict(provider_metadata or {}),
        )

    def resolve(self, asset_id: str, base_asset: str, quote_asset: str,
                tickers_payload: Mapping[str, Any], verified_at: Optional[str] = None,
                max_age_seconds: int = 900,
                provider_metadata: Optional[Mapping[str, Any]] = None) -> AssetIdentityProof:
        observed_at = verified_at or utc_now()
        try:
            _parse_time(observed_at)
        except (TypeError, ValueError, OverflowError):
            observed_at = utc_now()
        prefix = "coingecko:"
        if not isinstance(asset_id, str) or not asset_id.startswith(prefix) or not asset_id[len(prefix):]:
            return self._unverified(str(asset_id or "unknown"), str(base_asset or ""),
                                    str(quote_asset or ""), "unsupported or missing CoinGecko asset ID", observed_at)
        if (not isinstance(base_asset, str) or not base_asset.isalnum() or base_asset != base_asset.upper()
                or not isinstance(quote_asset, str) or not quote_asset.isalnum() or quote_asset != quote_asset.upper()):
            return self._unverified(asset_id, str(base_asset or ""), str(quote_asset or ""),
                                    "base/quote identity is invalid", observed_at)
        if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) or max_age_seconds <= 0:
            return self._unverified(asset_id, base_asset, quote_asset,
                                    "identity proof freshness limit is invalid", observed_at)
        if not isinstance(tickers_payload, Mapping) or not isinstance(tickers_payload.get("tickers"), list):
            return self._unverified(asset_id, base_asset, quote_asset,
                                    "CoinGecko tickers response schema invalid", observed_at)
        try:
            data_hash = hashlib.sha256(json.dumps(
                tickers_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")).hexdigest()
        except (TypeError, ValueError):
            return self._unverified(asset_id, base_asset, quote_asset,
                                    "CoinGecko tickers response is not canonical JSON", observed_at)
        coin_id = asset_id[len(prefix):]
        exact_pair_rows = []
        same_symbol_other_identity = False
        for ticker in tickers_payload["tickers"]:
            if not isinstance(ticker, Mapping):
                continue
            market = ticker.get("market")
            if not isinstance(market, Mapping):
                continue
            if (str(market.get("identifier", "")).lower() != self.exchange_id
                    or ticker.get("base") != base_asset or ticker.get("target") != quote_asset):
                continue
            if ticker.get("coin_id") != coin_id:
                same_symbol_other_identity = True
                continue
            exact_pair_rows.append(ticker)
        if not exact_pair_rows:
            reason = ("ticker base/quote matches but CoinGecko coin ID differs" if same_symbol_other_identity
                      else "no exact Binance ticker matches canonical CoinGecko ID and base/quote")
            return self._unverified(asset_id, base_asset, quote_asset, reason, observed_at,
                                    data_hash=data_hash, provider_metadata=provider_metadata)
        if len(exact_pair_rows) != 1:
            return self._unverified(asset_id, base_asset, quote_asset,
                                    "multiple exact Binance ticker rows make identity ambiguous", observed_at,
                                    data_hash=data_hash, provider_metadata=provider_metadata)
        ticker = exact_pair_rows[0]
        if ticker.get("is_stale") is not False or ticker.get("is_anomaly") is not False:
            return self._unverified(asset_id, base_asset, quote_asset,
                                    "exact Binance ticker is stale, anomalous or missing quality flags", observed_at,
                                    data_hash=data_hash, provider_metadata=provider_metadata)
        source_timestamp = ticker.get("last_fetch_at")
        if not isinstance(source_timestamp, str) or not source_timestamp.strip():
            return self._unverified(asset_id, base_asset, quote_asset,
                                    "exact Binance ticker is missing last_fetch_at", observed_at,
                                    data_hash=data_hash, provider_metadata=provider_metadata)
        try:
            age = (_parse_time(observed_at) - _parse_time(source_timestamp)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return self._unverified(asset_id, base_asset, quote_asset,
                                    "exact Binance ticker last_fetch_at is invalid", observed_at,
                                    source_timestamp=source_timestamp, data_hash=data_hash,
                                    provider_metadata=provider_metadata)
        if age < -300 or age > max_age_seconds:
            return self._unverified(asset_id, base_asset, quote_asset,
                                    "exact Binance ticker last_fetch_at is stale or clock-skewed", observed_at,
                                    source_timestamp=source_timestamp, data_hash=data_hash,
                                    provider_metadata=provider_metadata)
        ticker_timestamp = ticker.get("timestamp") or ""
        if ticker_timestamp:
            try:
                _parse_time(ticker_timestamp)
            except (TypeError, ValueError, OverflowError):
                return self._unverified(asset_id, base_asset, quote_asset,
                                        "exact Binance ticker timestamp is invalid", observed_at,
                                        source_timestamp=source_timestamp, data_hash=data_hash,
                                        provider_metadata=provider_metadata)
        proof = AssetIdentityProof(
            "VERIFIED", asset_id, base_asset, quote_asset, self.exchange_id,
            f"{base_asset}/{quote_asset}",
            "CoinGecko coin ID matches one fresh, non-anomalous Binance ticker",
            "coingecko_coin_tickers", observed_at, source_timestamp, ticker_timestamp,
            data_hash, dict(provider_metadata or {}),
        )
        proof.validate()
        return proof


@dataclass(frozen=True)
class EligibilityDecision:
    status: str
    asset_id: str
    symbol: str
    eligible_pairs: tuple[str, ...] = ()
    reason: str = ""
    verified_at: str = ""
    source: str = "https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT"
    identity_proof_status: str = "UNVERIFIED"
    identity_proof_source: str = ""
    identity_proof_verified_at: str = ""
    identity_proof_source_timestamp: str = ""
    identity_proof_reason: str = ""
    identity_proof_data_hash: str = ""


class BinanceListingEligibilityEngine:
    """Fail-closed exact Spot eligibility using Binance metadata and canonical ID proof."""
    SOURCE = "https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT"
    KNOWN_SYMBOL_STATUSES = {"TRADING", "HALT", "BREAK", "CANCEL_ONLY"}

    def __init__(self, allowed_quote_assets: Sequence[str] = ("USDT",),
                 max_snapshot_age_seconds: int = 300, max_identity_proof_age_seconds: int = 900):
        normalized = [str(q).upper() for q in allowed_quote_assets]
        if not normalized or len(set(normalized)) != len(normalized) or any(not q.isalnum() for q in normalized):
            raise ValueError("allowed quote assets must be unique uppercase alphanumeric symbols")
        if isinstance(max_snapshot_age_seconds, bool) or not isinstance(max_snapshot_age_seconds, int) or max_snapshot_age_seconds <= 0:
            raise ValueError("max_snapshot_age_seconds must be a positive integer")
        if isinstance(max_identity_proof_age_seconds, bool) or not isinstance(max_identity_proof_age_seconds, int) or max_identity_proof_age_seconds <= 0:
            raise ValueError("max_identity_proof_age_seconds must be a positive integer")
        self.allowed_quotes = set(normalized)
        self.max_snapshot_age_seconds = max_snapshot_age_seconds
        self.max_identity_proof_age_seconds = max_identity_proof_age_seconds

    @staticmethod
    def _decision(status: str, identity: AssetIdentity, reason: str,
                  verified_at: str = "", proof: Optional[AssetIdentityProof] = None,
                  eligible_pairs: tuple[str, ...] = ()) -> EligibilityDecision:
        proof = proof or AssetIdentityProof(
            "UNVERIFIED", identity.asset_id or "unknown", identity.base_asset or "UNKNOWN",
            identity.quote_asset or "UNKNOWN", reason="identity proof missing",
        )
        return EligibilityDecision(
            status, identity.asset_id, identity.base_asset, eligible_pairs, reason, verified_at,
            BinanceListingEligibilityEngine.SOURCE, proof.status, proof.source,
            proof.verified_at, proof.source_timestamp, proof.reason, proof.data_hash,
        )

    def evaluate(self, identity: AssetIdentity, exchange_info: Mapping[str, Any],
                 verified_at: Optional[str] = None,
                 identity_proof: Optional[AssetIdentityProof] = None) -> EligibilityDecision:
        if not isinstance(identity, AssetIdentity):
            return EligibilityDecision(
                "UNVERIFIED", "unknown", "", reason="canonical asset identity object is invalid",
                source=self.SOURCE,
            )
        if (not isinstance(identity.asset_id, str) or not identity.asset_id.startswith("coingecko:")
                or not isinstance(identity.asset_name, str) or not identity.asset_name.strip()
                or not isinstance(identity.base_asset, str) or not isinstance(identity.quote_asset, str)
                or not identity.base_asset.isalnum() or identity.base_asset != identity.base_asset.upper()
                or not identity.quote_asset.isalnum() or identity.quote_asset != identity.quote_asset.upper()):
            return self._decision("UNVERIFIED", identity, "canonical asset identity incomplete or invalid", proof=identity_proof)
        if identity.quote_asset not in self.allowed_quotes:
            return self._decision("UNVERIFIED", identity, "requested quote asset is not allowed by configuration", proof=identity_proof)
        if not isinstance(identity_proof, AssetIdentityProof):
            return self._decision("UNVERIFIED", identity, "canonical CoinGecko-to-Binance identity proof missing")
        try:
            identity_proof.validate()
        except (TypeError, ValueError):
            return self._decision("UNVERIFIED", identity, "canonical asset identity proof is invalid", proof=identity_proof)
        if identity_proof.status != "VERIFIED":
            return self._decision(
                "UNVERIFIED", identity,
                f"canonical asset identity proof unavailable: {identity_proof.reason}",
                proof=identity_proof,
            )
        if (identity_proof.asset_id != identity.asset_id
                or identity_proof.base_asset != identity.base_asset
                or identity_proof.quote_asset != identity.quote_asset
                or identity_proof.exchange_id != "binance"):
            return self._decision("UNVERIFIED", identity,
                                  "canonical asset identity proof does not match requested asset/pair",
                                  proof=identity_proof)
        if not identity_proof.is_fresh(self.max_identity_proof_age_seconds):
            return self._decision("UNVERIFIED", identity,
                                  "canonical asset identity proof source timestamp is stale",
                                  proof=identity_proof)
        if not isinstance(exchange_info, Mapping):
            return self._decision("UNVERIFIED", identity, "exchangeInfo snapshot is not an object", proof=identity_proof)
        server_time = exchange_info.get("serverTime")
        if isinstance(server_time, bool) or not isinstance(server_time, (int, float)) or server_time <= 0:
            return self._decision("UNVERIFIED", identity, "exchangeInfo serverTime missing or invalid", proof=identity_proof)
        try:
            server_timestamp = datetime.fromtimestamp(float(server_time) / 1000.0, timezone.utc).isoformat()
            normalized_snapshot_time = _parse_time(server_timestamp)
            retrieval_time = _parse_time(verified_at or utc_now())
        except (TypeError, ValueError, OverflowError):
            return self._decision("UNVERIFIED", identity, "exchangeInfo snapshot timestamp invalid", proof=identity_proof)
        server_age = (datetime.now(timezone.utc) - normalized_snapshot_time).total_seconds()
        retrieval_age = (datetime.now(timezone.utc) - retrieval_time).total_seconds()
        if (server_age < -300 or server_age > self.max_snapshot_age_seconds
                or retrieval_age < -300 or retrieval_age > self.max_snapshot_age_seconds
                or abs((retrieval_time - normalized_snapshot_time).total_seconds()) > 300):
            return self._decision("UNVERIFIED", identity, "exchangeInfo snapshot is stale or clock-skewed",
                                  normalized_snapshot_time.isoformat(), identity_proof)
        symbols = exchange_info.get("symbols")
        if not isinstance(symbols, list) or not symbols:
            return self._decision("UNVERIFIED", identity, "exchangeInfo symbols missing/empty", proof=identity_proof)
        seen_symbols = set()
        validated = []
        for item in symbols:
            if not isinstance(item, Mapping):
                return self._decision("UNVERIFIED", identity, "exchangeInfo contains a malformed symbol record", proof=identity_proof)
            pair, base, quote = item.get("symbol"), item.get("baseAsset"), item.get("quoteAsset")
            status, spot_allowed, permission_sets = (
                item.get("status"), item.get("isSpotTradingAllowed"), item.get("permissionSets")
            )
            if (not isinstance(pair, str) or not pair.isalnum() or pair != pair.upper()
                    or not isinstance(base, str) or not base.isalnum() or base != base.upper()
                    or not isinstance(quote, str) or not quote.isalnum() or quote != quote.upper()
                    or pair != base + quote
                    or not isinstance(status, str) or status not in self.KNOWN_SYMBOL_STATUSES
                    or not isinstance(spot_allowed, bool)
                    or not isinstance(permission_sets, list)):
                return self._decision("UNVERIFIED", identity, "exchangeInfo symbol schema/semantics incomplete", proof=identity_proof)
            if pair in seen_symbols:
                return self._decision("UNVERIFIED", identity, "exchangeInfo contains duplicate symbol records", proof=identity_proof)
            seen_symbols.add(pair)
            for group in permission_sets:
                if (not isinstance(group, list) or not group
                        or any(not isinstance(permission, str) or not permission for permission in group)):
                    return self._decision("UNVERIFIED", identity, "exchangeInfo permissionSets schema invalid", proof=identity_proof)
            validated.append((item, "SPOT" in {permission for group in permission_sets for permission in group}))
        matches = [(item, has_spot) for item, has_spot in validated
                   if item["baseAsset"] == identity.base_asset and item["quoteAsset"] == identity.quote_asset]
        if not matches:
            return self._decision("INELIGIBLE", identity,
                                  "no exact Binance Spot pair for canonical base/quote identity",
                                  normalized_snapshot_time.isoformat(), identity_proof)
        if len(matches) != 1:
            return self._decision("UNVERIFIED", identity, "multiple exact base/quote pairs are ambiguous",
                                  normalized_snapshot_time.isoformat(), identity_proof)
        item, has_spot_permission = matches[0]
        if (item["status"] != "TRADING" or item["isSpotTradingAllowed"] is not True
                or not has_spot_permission):
            return self._decision("INELIGIBLE", identity,
                                  "exact Binance pair is inactive or lacks applicable Spot permission",
                                  normalized_snapshot_time.isoformat(), identity_proof)
        return self._decision("ELIGIBLE", identity, "active exact Binance Spot pair and canonical identity verified",
                              normalized_snapshot_time.isoformat(), identity_proof, (item["symbol"],))


@dataclass(frozen=True)
class ProviderResponse:
    """Transport result from an approved HTTP adapter; never stores raw headers by default."""
    payload: Any
    status_code: int = 200
    headers: Mapping[str, str] = field(default_factory=dict)


class ProviderRequestError(RuntimeError):
    def __init__(self, provider: str, status_code: int, retry_after_seconds: Optional[int] = None):
        self.provider = provider
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        suffix = f"; retry_after_seconds={retry_after_seconds}" if retry_after_seconds is not None else ""
        super().__init__(f"{provider} request failed with HTTP {status_code}{suffix}")


@dataclass(frozen=True)
class MarketDataDiscrepancy:
    asset_id: str
    currency: str
    providers: tuple[str, ...]
    prices: tuple[float, ...]
    relative_deviation: float
    status: str = "REVIEW_REQUIRED"


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
    source_timestamp: Optional[str] = None
    field_availability: Mapping[str, str] = field(default_factory=dict)
    field_provenance: Mapping[str, str] = field(default_factory=dict)
    freshness_by_field: Mapping[str, str] = field(default_factory=dict)
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)
    cache_hit: bool = False

    def validate(self) -> None:
        if not all(isinstance(value, str) and value.strip() for value in
                   (self.asset_id, self.provider, self.endpoint, self.currency)):
            raise ValueError("market observation identity/provenance/currency missing")
        if not self.currency.isalnum() or self.currency != self.currency.upper():
            raise ValueError("market observation currency must be an uppercase asset/currency code")
        if not all(isinstance(value, Mapping) for value in (
            self.field_availability, self.field_provenance, self.freshness_by_field, self.provider_metadata
        )):
            raise ValueError("market observation metadata fields must be mappings")
        if not isinstance(self.data_hash, str) or not isinstance(self.cache_hit, bool):
            raise ValueError("market observation hash/cache metadata is invalid")
        _parse_time(self.observed_at)
        for timestamp_name in ("published_at", "source_timestamp"):
            timestamp = getattr(self, timestamp_name)
            if timestamp:
                _parse_time(timestamp)
        if self.provider == "coingecko_markets" and not (self.published_at or self.source_timestamp):
            raise ValueError("CoinGecko market observation is missing provider last_updated time")
        numeric_fields = ("price", "change_24h", "volume_24h", "market_cap")
        for name in numeric_fields:
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
        allowed_fields = set(numeric_fields) | {"history"}
        for field_name, availability in self.field_availability.items():
            if field_name not in allowed_fields or availability not in {"AVAILABLE", "UNAVAILABLE"}:
                raise ValueError("market field availability metadata is invalid")
            value = self.history if field_name == "history" else getattr(self, field_name)
            if (availability == "AVAILABLE") != (value is not None and (field_name != "history" or bool(value))):
                raise ValueError(f"market field availability conflicts with {field_name} value")
        for field_name, source in self.field_provenance.items():
            if field_name not in allowed_fields or not isinstance(source, str) or not source.strip():
                raise ValueError("market field provenance metadata is invalid")
        for field_name, source in self.field_provenance.items():
            if self.field_availability.get(field_name) == "AVAILABLE" and not source.strip():
                raise ValueError("available market field is missing provenance")
        for field_name, freshness in self.freshness_by_field.items():
            if field_name not in allowed_fields or freshness not in {"FRESH", "STALE", "UNKNOWN", "UNAVAILABLE"}:
                raise ValueError("market field freshness metadata is invalid")
            if freshness == "UNAVAILABLE" and self.field_availability.get(field_name) == "AVAILABLE":
                raise ValueError("market field freshness conflicts with available field data")
        try:
            json.dumps(dict(self.provider_metadata), sort_keys=True, allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError("market provider metadata must be JSON-safe") from None


class MarketDataIntelligenceEngine:
    """Approved-provider market normalizer with provenance, freshness and bounded caching."""
    DEFAULT_FRESHNESS_SECONDS = {
        "binance_spot": {"price": 300, "change_24h": 300, "volume_24h": 300},
        "coingecko_markets": {
            "price": 900, "change_24h": 900, "volume_24h": 900,
            "market_cap": 900,
        },
    }
    BINANCE_MARKET_DATA_BASE = "https://data-api.binance.vision"
    COINGECKO_MARKETS_ENDPOINT = "https://api.coingecko.com/api/v3/coins/markets"

    def __init__(self, fetch_json: Callable[[str, int], Any], timeout: int = 15,
                 cache_ttl_seconds: int = 0, clock: Callable[[], str] = utc_now,
                 monotonic: Callable[[], float] = time.monotonic,
                 freshness_limits_seconds: Optional[Mapping[str, Mapping[str, int]]] = None):
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
            raise ValueError("market data timeout must be a positive integer")
        if isinstance(cache_ttl_seconds, bool) or not isinstance(cache_ttl_seconds, int) or cache_ttl_seconds < 0:
            raise ValueError("market data cache TTL must be a non-negative integer")
        self.fetch_json = fetch_json
        self.timeout = timeout
        self.cache_ttl_seconds = cache_ttl_seconds
        self.clock = clock
        self.monotonic = monotonic
        self.freshness_limits_seconds = {
            provider: dict(fields) for provider, fields in self.DEFAULT_FRESHNESS_SECONDS.items()
        }
        if freshness_limits_seconds:
            for provider, fields in freshness_limits_seconds.items():
                normalized_fields = dict(fields)
                for field_name, seconds in normalized_fields.items():
                    if (not isinstance(field_name, str) or not field_name
                            or isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0):
                        raise ValueError("field freshness limits must be positive integer seconds")
                self.freshness_limits_seconds.setdefault(provider, {}).update(normalized_fields)
        self._observation_cache: dict[str, tuple[float, MarketObservation]] = {}
        self.last_provider_metadata: dict[str, Mapping[str, Any]] = {}

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> Optional[str]:
        target = name.casefold()
        for key, value in headers.items():
            if str(key).casefold() == target:
                return str(value)
        return None

    @staticmethod
    def _number(payload: Mapping[str, Any], name: str, required: bool = False) -> Optional[float]:
        value = payload.get(name)
        if value is None and not required:
            return None
        if isinstance(value, bool) or value is None:
            raise ValueError(f"provider field {name} is missing or invalid")
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"provider field {name} is missing or invalid") from exc
        if not math.isfinite(number):
            raise ValueError(f"provider field {name} is non-finite")
        return number

    def _fetch(self, provider: str, url: str) -> tuple[Any, Mapping[str, Any]]:
        try:
            raw = self.fetch_json(url, self.timeout)
        except Exception as exc:
            status_code = getattr(exc, "code", getattr(exc, "status_code", None))
            headers = getattr(exc, "headers", {}) or {}
            if isinstance(status_code, int):
                retry_after_raw = self._header(headers, "Retry-After") if isinstance(headers, Mapping) else None
                try:
                    retry_after = max(0, int(float(retry_after_raw))) if retry_after_raw is not None else None
                except (TypeError, ValueError, OverflowError):
                    retry_after = None
                raise ProviderRequestError(provider, status_code, retry_after) from None
            raise
        response = raw if isinstance(raw, ProviderResponse) else ProviderResponse(raw)
        retry_after_raw = self._header(response.headers, "Retry-After")
        try:
            retry_after = max(0, int(float(retry_after_raw))) if retry_after_raw is not None else None
        except (TypeError, ValueError, OverflowError):
            retry_after = None
        if response.status_code != 200:
            raise ProviderRequestError(provider, response.status_code, retry_after)
        metadata: dict[str, Any] = {"http_status": response.status_code}
        used_weight = self._header(response.headers, "X-MBX-USED-WEIGHT-1M")
        if used_weight is not None:
            try:
                metadata["used_weight_1m"] = int(used_weight)
            except ValueError:
                metadata["used_weight_1m"] = "UNPARSEABLE"
        if retry_after is not None:
            metadata["retry_after_seconds"] = retry_after
        self.last_provider_metadata[provider] = dict(metadata)
        return response.payload, metadata

    def _freshness(self, provider: str, fields: Sequence[str], source_timestamp: Optional[str],
                   availability: Mapping[str, str], now: str) -> dict[str, str]:
        if not source_timestamp:
            return {name: ("UNAVAILABLE" if availability.get(name) == "UNAVAILABLE" else "UNKNOWN")
                    for name in fields}
        source_time = _parse_time(source_timestamp)
        now_time = _parse_time(now)
        age = max(0.0, (now_time - source_time).total_seconds())
        limits = self.freshness_limits_seconds.get(provider, {})
        result = {}
        for name in fields:
            if availability.get(name) == "UNAVAILABLE":
                result[name] = "UNAVAILABLE"
                continue
            # CoinGecko documents a 6-hour sparkline refresh cadence but does not
            # return a per-sparkline timestamp. Never borrow last_updated for it.
            if provider == "coingecko_markets" and name == "history":
                result[name] = "UNKNOWN"
                continue
            limit = limits.get(name)
            result[name] = "UNKNOWN" if limit is None else ("FRESH" if age <= limit else "STALE")
        return result

    def fetch_binance_24h(self, identity: AssetIdentity, symbol: str) -> MarketObservation:
        if (not isinstance(identity, AssetIdentity) or not identity.asset_id
                or not identity.base_asset or not identity.quote_asset):
            raise ValueError("a complete canonical AssetIdentity is required")
        if (not isinstance(symbol, str) or not symbol.isalnum() or symbol != symbol.upper()
                or symbol != identity.base_asset + identity.quote_asset):
            raise ValueError("symbol must match the canonical base/quote identity exactly")
        cache_key = f"binance_spot:{identity.asset_id}:{symbol}"
        cached = self._observation_cache.get(cache_key)
        now_monotonic = self.monotonic()
        if cached and cached[0] > now_monotonic:
            return replace(cached[1], cache_hit=True)
        url = f"{self.BINANCE_MARKET_DATA_BASE}/api/v3/ticker/24hr?symbol={symbol}"
        payload, provider_metadata = self._fetch("binance_spot", url)
        if not isinstance(payload, Mapping) or payload.get("symbol") != symbol:
            raise ValueError("Binance ticker response schema/symbol mismatch")
        close_time = payload.get("closeTime")
        if isinstance(close_time, bool) or not isinstance(close_time, (int, float)) or close_time <= 0:
            raise ValueError("Binance ticker response missing a valid provider closeTime")
        try:
            source_timestamp = datetime.fromtimestamp(float(close_time) / 1000, timezone.utc).isoformat()
            observed_at = self.clock()
            values = {
                "price": self._number(payload, "lastPrice", required=True),
                "change_24h": self._number(payload, "priceChangePercent", required=True),
                "volume_24h": self._number(payload, "quoteVolume", required=True),
            }
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Binance ticker response contains missing or invalid required fields") from exc
        availability = {name: ("AVAILABLE" if value is not None else "UNAVAILABLE")
                        for name, value in values.items()}
        availability.update({"market_cap": "UNAVAILABLE", "history": "UNAVAILABLE"})
        provenance = {name: "binance_spot" for name in availability}
        freshness = self._freshness("binance_spot", tuple(availability), source_timestamp, availability, observed_at)
        data_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                              allow_nan=False).encode()).hexdigest()
        observation = MarketObservation(
            asset_id=identity.asset_id, provider="binance_spot", endpoint=url,
            observed_at=observed_at, price=values["price"], currency=identity.quote_asset,
            change_24h=values["change_24h"], volume_24h=values["volume_24h"],
            data_hash=data_hash, source_timestamp=source_timestamp,
            field_availability=availability, field_provenance=provenance,
            freshness_by_field=freshness, provider_metadata=provider_metadata,
        )
        observation.validate()
        if self.cache_ttl_seconds:
            self._observation_cache[cache_key] = (now_monotonic + self.cache_ttl_seconds, observation)
        return observation

    def normalize_coingecko_market(self, identity: AssetIdentity, item: Mapping[str, Any],
                                   observed_at: Optional[str] = None, currency: str = "USD",
                                   provider_metadata: Optional[Mapping[str, Any]] = None) -> MarketObservation:
        if not isinstance(identity, AssetIdentity) or not identity.asset_id.startswith("coingecko:"):
            raise ValueError("a CoinGecko canonical asset identity is required")
        if not isinstance(item, Mapping) or item.get("id") != identity.asset_id.split(":", 1)[1]:
            raise ValueError("CoinGecko coin ID does not match canonical asset identity")
        symbol = item.get("symbol")
        if not isinstance(symbol, str) or symbol.upper() != identity.base_asset:
            raise ValueError("CoinGecko symbol does not match canonical base asset")
        source_timestamp = item.get("last_updated")
        if not isinstance(source_timestamp, str) or not source_timestamp.strip():
            raise ValueError("CoinGecko market item is missing last_updated")
        if not isinstance(currency, str) or not currency.isalnum() or currency != currency.upper():
            raise ValueError("CoinGecko target currency must be uppercase alphanumeric")
        retrieval_time = observed_at or self.clock()
        _parse_time(retrieval_time)
        _parse_time(source_timestamp)
        values = {
            "price": self._number(item, "current_price"),
            "change_24h": self._number(item, "price_change_percentage_24h"),
            "volume_24h": self._number(item, "total_volume"),
            "market_cap": self._number(item, "market_cap"),
        }
        sparkline = item.get("sparkline_in_7d")
        raw_history = sparkline.get("price", []) if isinstance(sparkline, Mapping) else []
        if raw_history is None:
            raw_history = []
        if not isinstance(raw_history, list):
            raise ValueError("CoinGecko sparkline price data must be a list")
        history = tuple(self._number({"value": value}, "value", required=True) for value in raw_history)
        if any(point <= 0 for point in history):
            raise ValueError("CoinGecko sparkline values must be positive")
        availability = {name: ("AVAILABLE" if value is not None else "UNAVAILABLE")
                        for name, value in values.items()}
        availability["history"] = "AVAILABLE" if history else "UNAVAILABLE"
        provenance = {name: "coingecko_markets" for name in availability}
        freshness = self._freshness("coingecko_markets", tuple(availability), source_timestamp,
                                    availability, retrieval_time)
        data_hash = hashlib.sha256(json.dumps(item, sort_keys=True, separators=(",", ":"),
                                              allow_nan=False).encode()).hexdigest()
        observation = MarketObservation(
            asset_id=identity.asset_id, provider="coingecko_markets",
            endpoint=self.COINGECKO_MARKETS_ENDPOINT, observed_at=retrieval_time,
            price=values["price"], currency=currency, change_24h=values["change_24h"],
            volume_24h=values["volume_24h"], market_cap=values["market_cap"],
            history=history, published_at=source_timestamp, source_timestamp=source_timestamp,
            data_hash=data_hash, field_availability=availability,
            field_provenance=provenance, freshness_by_field=freshness,
            provider_metadata={
                **dict(provider_metadata or {}),
                "history_refresh_interval_seconds": 21600,
                "history_source_timestamp_available": False,
            },
        )
        observation.validate()
        return observation

    @staticmethod
    def compare_observations(observations: Sequence[MarketObservation],
                             threshold_fraction: float = 0.03) -> list[MarketDataDiscrepancy]:
        if (isinstance(threshold_fraction, bool) or not isinstance(threshold_fraction, (int, float))
                or not math.isfinite(threshold_fraction) or threshold_fraction < 0):
            raise ValueError("discrepancy threshold must be a finite non-negative fraction")
        grouped: dict[tuple[str, str], list[MarketObservation]] = {}
        now = datetime.now(timezone.utc)
        for item in observations:
            item.validate()
            freshness = item.freshness_by_field.get("price")
            if item.price is None or freshness in {"STALE", "UNKNOWN", "UNAVAILABLE"}:
                continue
            if freshness is None:
                source_time = _parse_time(item.source_timestamp or item.published_at or item.observed_at)
                if (now - source_time).total_seconds() > 300:
                    continue
            grouped.setdefault((item.asset_id, item.currency), []).append(item)
        discrepancies = []
        for (asset_id, currency), items in grouped.items():
            if len(items) < 2:
                continue
            low = min(float(item.price) for item in items)
            high = max(float(item.price) for item in items)
            midpoint = (low + high) / 2
            deviation = (high - low) / midpoint if midpoint else 0.0
            if deviation > threshold_fraction:
                ordered = sorted(items, key=lambda item: item.provider)
                discrepancies.append(MarketDataDiscrepancy(
                    asset_id, currency, tuple(item.provider for item in ordered),
                    tuple(float(item.price) for item in ordered), deviation,
                ))
        return discrepancies


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
            if m.price is not None
            and m.freshness_by_field.get("price") not in {"STALE", "UNKNOWN", "UNAVAILABLE"}
            and (now - _parse_time(m.source_timestamp or m.published_at or m.observed_at)).total_seconds()
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
    """Auditable persistence for market evidence, identity proofs and candidate decisions."""
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
        CREATE TABLE IF NOT EXISTS layer1_identity_proofs (
            asset_id TEXT NOT NULL, base_asset TEXT NOT NULL, quote_asset TEXT NOT NULL,
            exchange_id TEXT NOT NULL, status TEXT NOT NULL, expires_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY(asset_id, base_asset, quote_asset, exchange_id)
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

    def get_identity_proof(self, identity: AssetIdentity, now: Optional[str] = None) -> Optional[AssetIdentityProof]:
        row = self.conn.execute(
            "SELECT expires_at, payload_json FROM layer1_identity_proofs "
            "WHERE asset_id=? AND base_asset=? AND quote_asset=? AND exchange_id='binance'",
            (identity.asset_id, identity.base_asset, identity.quote_asset),
        ).fetchone()
        if row is None:
            return None
        try:
            expires_at = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
            current_time = datetime.fromisoformat(str(now or utc_now()).replace("Z", "+00:00"))
            if expires_at <= current_time:
                raise ValueError("identity proof cache expired")
            proof = AssetIdentityProof(**json.loads(row[1]))
            proof.validate()
            return proof
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            self.conn.execute(
                "DELETE FROM layer1_identity_proofs WHERE asset_id=? AND base_asset=? "
                "AND quote_asset=? AND exchange_id='binance'",
                (identity.asset_id, identity.base_asset, identity.quote_asset),
            )
            self.conn.commit()
            return None

    def save_identity_proof(self, proof: AssetIdentityProof, ttl_seconds: int) -> None:
        proof.validate()
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise ValueError("identity proof cache TTL must be a positive integer")
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
        payload = json.dumps(proof.__dict__, sort_keys=True, separators=(",", ":"), allow_nan=False)
        self.conn.execute(
            "INSERT INTO layer1_identity_proofs VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(asset_id, base_asset, quote_asset, exchange_id) DO UPDATE SET "
            "status=excluded.status, expires_at=excluded.expires_at, payload_json=excluded.payload_json",
            (proof.asset_id, proof.base_asset, proof.quote_asset, proof.exchange_id,
             proof.status, expires_at, payload),
        )
        self.conn.commit()

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
