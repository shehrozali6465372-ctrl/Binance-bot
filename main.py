import json
import os
import random
import logging
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from image_engine import ImageIntelligenceEngine, ImageUploader


@dataclass(frozen=True)
class Config:
    gemini_api_key: str
    square_api_key: str
    post_interval: int
    database_path: str
    publish_log_path: str
    max_iterations: int
    dry_run: bool
    log_level: str
    live_market_data: bool
    gemini_model: str
    http_timeout_seconds: int
    gemini_temperature: float
    gemini_top_p: float
    gemini_max_output_tokens: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            square_api_key=os.getenv("SQUARE_API_KEY", ""),
            post_interval=int(os.getenv("POST_INTERVAL", "7200")),
            database_path=os.getenv("DATABASE_PATH", "agent.db"),
            publish_log_path=os.getenv("PUBLISH_LOG_PATH", "published_posts.jsonl"),
            max_iterations=int(os.getenv("MAX_ITERATIONS", "1")),
            dry_run=os.getenv("DRY_RUN", "1").strip().lower() not in {"0", "false", "no"},
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            live_market_data=os.getenv("LIVE_MARKET_DATA", "0").strip().lower() in {"1", "true", "yes"},
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            http_timeout_seconds=int(os.getenv("HTTP_TIMEOUT_SECONDS", "15")),
            gemini_temperature=float(os.getenv("GEMINI_TEMPERATURE", "0.9")),
            gemini_top_p=float(os.getenv("GEMINI_TOP_P", "0.95")),
            gemini_max_output_tokens=int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "2048")),
        )

    def validate(self) -> None:
        if self.post_interval < 0:
            raise ValueError("POST_INTERVAL must be >= 0")
        if self.max_iterations < 0:
            raise ValueError("MAX_ITERATIONS must be >= 0")
        if self.http_timeout_seconds <= 0:
            raise ValueError("HTTP_TIMEOUT_SECONDS must be > 0")
        if not (0.0 < self.gemini_temperature <= 2.0):
            raise ValueError("GEMINI_TEMPERATURE must be between 0 and 2")
        if not (0.0 < self.gemini_top_p <= 1.0):
            raise ValueError("GEMINI_TOP_P must be between 0 and 1")
        if self.gemini_max_output_tokens <= 0:
            raise ValueError("GEMINI_MAX_OUTPUT_TOKENS must be > 0")


CONFIG = Config.from_env()

logging.basicConfig(
    level=getattr(logging, CONFIG.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger("agent")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: str) -> None:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def http_get_json(url: str, timeout: int) -> Any:
    return _http_json_with_retry("GET", url, timeout)


def http_post_json(
    url: str,
    payload: Dict[str, Any],
    timeout: int,
    headers: Optional[Dict[str, str]] = None,
    retries: int = 3,
) -> Any:
    return _http_json_with_retry("POST", url, timeout, payload=payload, headers=headers, retries=retries)


def _http_json_with_retry(
    method: str,
    url: str,
    timeout: int,
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    retries: int = 3,
) -> Any:
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            request_headers = {"User-Agent": "codex-agent/1.0"}
            if headers:
                request_headers.update(headers)
            data = None
            if payload is not None:
                request_headers["Content-Type"] = "application/json"
                data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 451:
                LOGGER.warning("HTTP 451 %s %s blocked by geo-restriction, skipping retries", method, url)
                raise
            if exc.code == 429:
                sleep_for = min(2 ** attempt * 5 + random.uniform(0, 5), 60)
                LOGGER.warning("HTTP 429 %s %s rate limited (retrying in %ss, attempt %d/%d)", method, url, round(sleep_for, 1), attempt + 1, retries)
            else:
                sleep_for = min(2 ** attempt + random.uniform(0, 2), 30)
                LOGGER.warning("HTTP %d %s %s failed (retrying in %ss, attempt %d/%d)", exc.code, method, url, round(sleep_for, 1), attempt + 1, retries)
            last_error = exc
            if attempt >= retries - 1:
                break
            time.sleep(sleep_for)
        except (urllib.error.URLError, ValueError) as exc:
            last_error = exc
            if attempt >= retries - 1:
                break
            sleep_for = min(2 ** attempt + random.uniform(0, 2), 30)
            LOGGER.warning("HTTP %s %s failed (retrying in %ss, attempt %d/%d): %s", method, url, round(sleep_for, 1), attempt + 1, retries, exc)
            time.sleep(sleep_for)
    assert last_error is not None
    raise last_error


@dataclass
class Coin:
    symbol: str
    name: str
    price: float
    change_24h: float
    volume_24h: float
    volume_ratio: float
    market_cap: float
    history: List[float]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "price": self.price,
            "change_24h": self.change_24h,
            "volume_24h": self.volume_24h,
            "volume_ratio": self.volume_ratio,
            "market_cap": self.market_cap,
            "history": self.history,
        }


class Database:
    def __init__(self, path: str):
        self.path = path
        ensure_parent(self.path)
        self.conn = sqlite3.connect(self.path, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def close(self) -> None:
        with suppress(Exception):
            self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    coin_symbol TEXT,
                    content TEXT NOT NULL,
                    metadata TEXT
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER,
                    created_at TEXT NOT NULL,
                    views INTEGER NOT NULL,
                    traders INTEGER NOT NULL,
                    FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE SET NULL
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT
                )
                """
            )

    def save_post(self, post: Any) -> int:
        if isinstance(post, dict):
            content = post.get("content") or post.get("text") or ""
            metadata = {k: v for k, v in post.items() if k not in {"content", "text"}}
            coin_symbol = metadata.get("coin_symbol") or metadata.get("symbol")
        else:
            content = str(post)
            metadata = {}
            coin_symbol = None

        with self.conn:
            cur = self.conn.execute(
                """
                INSERT INTO posts (created_at, coin_symbol, content, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (utc_now(), coin_symbol, content, json.dumps(metadata, default=str)),
            )
        return int(cur.lastrowid)

    def save_metrics(self, views: int, traders: int, post_id: Optional[int] = None) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO metrics (post_id, created_at, views, traders)
                VALUES (?, ?, ?, ?)
                """,
                (post_id, utc_now(), int(views), int(traders)),
            )

    def recent_posts(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.conn.execute(
            "SELECT created_at, coin_symbol, content, metadata FROM posts ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = []
        for row in cur.fetchall():
            rows.append(
                {
                    "created_at": row["created_at"],
                    "coin_symbol": row["coin_symbol"],
                    "content": row["content"],
                    "metadata": json.loads(row["metadata"] or "{}"),
                }
            )
        return rows

    def get_posted_symbols(self, hours: int = 48) -> set:
        """Get symbols posted recently to avoid repetition."""
        try:
            cur = self.conn.execute(
                "SELECT coin_symbol, created_at FROM posts ORDER BY id DESC LIMIT 100"
            )
            posted = set()
            for row in cur.fetchall():
                if row["coin_symbol"]:
                    posted.add(row["coin_symbol"].upper())
            return posted
        except sqlite3.OperationalError:
            return set()

    def get_post_count_for_symbol(self, symbol: str, hours: int = 48) -> int:
        """Count how many times a symbol was posted recently."""
        try:
            cur = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM posts WHERE coin_symbol = ? ORDER BY id DESC LIMIT 50",
                (symbol.upper(),),
            )
            row = cur.fetchone()
            return row["cnt"] if row else 0
        except sqlite3.OperationalError:
            return 0

    def get_posted_hours_dict(self, hours: int = 72) -> Dict[str, float]:
        """Get dict of symbol -> hours_ago for recently posted coins."""
        now = datetime.now(timezone.utc)
        try:
            cur = self.conn.execute(
                "SELECT coin_symbol, created_at FROM posts WHERE created_at IS NOT NULL ORDER BY id DESC LIMIT 200"
            )
            result = {}
            for row in cur.fetchall():
                sym = row["coin_symbol"]
                if not sym:
                    continue
                try:
                    posted_time = datetime.fromisoformat(row["created_at"])
                    delta = (now - posted_time).total_seconds() / 3600.0
                    if sym.upper() not in result or delta < result[sym.upper()]:
                        result[sym.upper()] = delta
                except (ValueError, TypeError):
                    continue
            return result
        except sqlite3.OperationalError:
            return {}

    def save_run(self, status: str, summary: Dict[str, Any]) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO runs (created_at, status, summary)
                VALUES (?, ?, ?)
                """,
                (utc_now(), status, json.dumps(summary, default=str)),
            )

    def get_top_performers(self, limit: int = 2) -> List[str]:
        try:
            cur = self.conn.execute(
                """
                SELECT p.content
                FROM posts p
                JOIN metrics m ON m.post_id = p.id
                ORDER BY (COALESCE(m.views, 0) + COALESCE(m.traders, 0) * 5) DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [row["content"] for row in cur.fetchall()]
        except sqlite3.OperationalError:
            return []


class MarketScanner:
    def __init__(self, config: Config = CONFIG):
        self.config = config
        self.universe = self._build_universe()

    def _build_universe(self) -> List[Coin]:
        sample = [
            Coin("SOL", "Solana", 168.42, 11.2, 3.4e9, 2.7, 7.4e10, [154, 158, 161, 165, 168]),
            Coin("LINK", "Chainlink", 21.11, 8.7, 1.1e9, 2.1, 1.3e10, [19.1, 19.8, 20.2, 20.6, 21.1]),
            Coin("AAVE", "Aave", 112.55, 7.9, 5.2e8, 1.9, 1.7e9, [105, 107, 109, 111, 112]),
            Coin("DOGE", "Dogecoin", 0.184, 5.4, 2.8e9, 1.8, 2.7e10, [0.173, 0.176, 0.179, 0.181, 0.184]),
            Coin("ETH", "Ethereum", 3472.15, 3.1, 1.5e10, 1.3, 4.2e11, [3390, 3410, 3432, 3451, 3472]),
            Coin("BTC", "Bitcoin", 68241.0, 1.4, 2.4e10, 1.1, 1.3e12, [67120, 67500, 67980, 68110, 68241]),
            Coin("MKR", "Sky", 3892.2, -2.4, 2.1e8, 0.8, 3.4e9, [3990, 3960, 3925, 3902, 3892]),
            Coin("OP", "Optimism", 2.62, -4.8, 7.8e8, 1.4, 2.3e9, [2.79, 2.74, 2.69, 2.65, 2.62]),
            Coin("ARB", "Arbitrum", 0.79, -6.2, 9.2e8, 1.6, 3.1e9, [0.86, 0.84, 0.82, 0.80, 0.79]),
        ]
        return sample

    def _live_universe(self) -> List[Coin]:
        """Get live market data from CoinGecko (Binance API is geo-blocked from GHA)."""
        return self._coingecko_universe()

    def _synthetic_history(self, price: float, change_24h: float) -> List[float]:
        steps = 10
        if abs(change_24h) < 0.01:
            return [round(price, 8)] * steps
        start = price / (1 + change_24h / 100.0)
        return [round(start + (price - start) * (i / (steps - 1)), 8) for i in range(steps)]


    def _coingecko_universe(self) -> List[Coin]:
        """Get Binance-listed trending coins from CoinGecko."""
        # Coins listed on Binance (major pairs)
        BINANCE_LISTED = {
            "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK",
            "MATIC", "POL", "SHIB", "TRX", "ATOM", "UNI", "APT", "ARB", "OP", "NEAR",
            "FIL", "ALGO", "AAVE", "MKR", "COMP", "SAND", "MANA", "AXS", "THETA", "FTM",
            "ICP", "EOS", "XLM", "VET", "EGLD", "GRT", "RNDR", "FET", "AGIX", "PEPE",
            "TIA", "SEI", "SUI", "INJ", "BLUR", "STRK", "BONK", "WIF", "JUP", "JTO",
        }
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=volume_desc&per_page=50&sparkline=true&price_change_percentage=24h"
        try:
            payload = http_get_json(url, timeout=self.config.http_timeout_seconds)
        except Exception:
            return self._build_universe()

        coins: List[Coin] = []
        for item in payload:
            try:
                symbol = (item.get("symbol") or "").upper()
                if symbol not in BINANCE_LISTED:
                    continue
                name = item.get("name") or symbol
                price = float(item.get("current_price") or 0)
                change_24h = float(item.get("price_change_percentage_24h") or 0)
                volume_24h = float(item.get("total_volume") or 0)
                market_cap = float(item.get("market_cap") or 0)
                if price <= 0 or market_cap < 1_000_000:
                    continue
                if abs(change_24h) > 100:
                    continue
                volume_ratio = min(max(0.3, volume_24h / max(market_cap, 1) * 100), 10.0)
                sparkline = item.get("sparkline_in_7d", {}).get("price", [])
                history = [float(p) for p in sparkline[-10:]] if sparkline else self._synthetic_history(price, change_24h)
            except (TypeError, ValueError, KeyError):
                continue
            coins.append(Coin(symbol, name, price, change_24h, volume_24h, volume_ratio, market_cap, history))

        return coins or self._build_universe()

    _universe_cache = None
    _cache_timestamp = 0

    def _universe(self) -> List[Coin]:
        # Cache for 5 minutes to avoid hitting rate limits
        now = time.time()
        if MarketScanner._universe_cache is not None and (now - MarketScanner._cache_timestamp) < 300:
            return MarketScanner._universe_cache
        if self.config.live_market_data:
            with suppress(Exception):
                coins = self._coingecko_universe()
                MarketScanner._universe_cache = coins
                MarketScanner._cache_timestamp = now
                return coins
        MarketScanner._universe_cache = self.universe
        MarketScanner._cache_timestamp = now
        return MarketScanner._universe_cache

    def top_gainers(self, limit: int = 3) -> List[Dict[str, Any]]:
        universe = self._universe()
        return [c.as_dict() for c in sorted(universe, key=lambda c: c.change_24h, reverse=True)[:limit]]

    def top_losers(self, limit: int = 3) -> List[Dict[str, Any]]:
        universe = self._universe()
        return [c.as_dict() for c in sorted(universe, key=lambda c: c.change_24h)[:limit]]

    def volume_spikes(self, threshold: float = 1.75) -> List[Dict[str, Any]]:
        universe = self._universe()
        return [c.as_dict() for c in universe if c.volume_ratio >= threshold]



class BinanceAnnouncementEngine:
    """Fetch real Binance announcements - new listings, news, delistings, airdrops."""
    
    CATALOGS = {
        "new_listings": 48,
        "latest_news": 49,
        "delistings": 161,
        "airdrops": 128,
        "activities": 93,
    }
    
    def __init__(self, config: Config = CONFIG):
        self.config = config
        self.base_url = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
    
    def fetch_announcements(self, catalog_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch announcements from a specific catalog."""
        url = f"{self.base_url}?type=1&pageNo=1&pageSize={limit}&catalogId={catalog_id}"
        try:
            data = http_get_json(url, timeout=self.config.http_timeout_seconds)
            if data.get("code") == "000000":
                for cat in data.get("data", {}).get("catalogs", []):
                    if cat.get("catalogId") == catalog_id:
                        return cat.get("articles", [])
            return []
        except Exception:
            return []
    
    def extract_symbols(self, title: str) -> List[str]:
        """Extract coin symbols from announcement title."""
        import re
        # Find symbols in parentheses like (BTC), (ETH), (SOL)
        paren_symbols = re.findall(r'\(([A-Z0-9]{2,10})\)', title)
        # Find standalone symbols in title
        known_coins = {"BTC","ETH","BNB","SOL","XRP","ADA","DOGE","AVAX","DOT","LINK",
                       "MATIC","SHIB","TRX","ATOM","UNI","APT","ARB","OP","NEAR","FIL",
                       "AAVE","MKR","PEPE","TIA","SEI","SUI","INJ","BONK","WIF","JUP",
                       "FET","AGIX","RNDR","THETA","EGLD","EOS","XLM","VET","ALGO",
                       "SAND","MANA","AXS","FTM","ICP","GRT","BLUR","STRK","JTO","RE"}
        found = []
        for s in paren_symbols:
            if s in known_coins:
                found.append(s)
        # Also check words for known coins
        words = title.upper().split()
        for w in words:
            w = w.strip(".,:;!?()[]{}")
            if w in known_coins and w not in found:
                found.append(w)
        return found
    
    def get_trending_announcements(self) -> List[Dict[str, Any]]:
        """Get announcements and identify market-moving events."""
        results = []
        
        # Fetch new listings (most market-moving)
        listings = self.fetch_announcements(self.CATALOGS["new_listings"], limit=5)
        for art in listings:
            symbols = self.extract_symbols(art.get("title", ""))
            if symbols:
                ts = art.get("releaseDate", 0) / 1000
                results.append({
                    "type": "new_listing",
                    "title": art["title"],
                    "symbols": symbols,
                    "timestamp": ts,
                    "impact": "high",
                })
        
        # Fetch airdrops
        airdrops = self.fetch_announcements(self.CATALOGS["airdrops"], limit=5)
        for art in airdrops:
            symbols = self.extract_symbols(art.get("title", ""))
            if symbols:
                ts = art.get("releaseDate", 0) / 1000
                results.append({
                    "type": "airdrop",
                    "title": art["title"],
                    "symbols": symbols,
                    "timestamp": ts,
                    "impact": "high",
                })
        
        # Fetch delistings 
        delistings = self.fetch_announcements(self.CATALOGS["delistings"], limit=5)
        for art in delistings:
            symbols = self.extract_symbols(art.get("title", ""))
            if symbols:
                results.append({
                    "type": "delisting",
                    "title": art["title"],
                    "symbols": symbols,
                    "timestamp": art.get("releaseDate", 0) / 1000,
                    "impact": "negative",
                })
        
        # Fetch latest news
        news = self.fetch_announcements(self.CATALOGS["latest_news"], limit=5)
        for art in news:
            symbols = self.extract_symbols(art.get("title", ""))
            if symbols:
                results.append({
                    "type": "news",
                    "title": art["title"],
                    "symbols": symbols,
                    "timestamp": art.get("releaseDate", 0) / 1000,
                    "impact": "medium",
                })
        
        return results


class HotSearchEngine:
    """Binance Hot Search Intelligence Engine - multi-provider architecture.
    
    Provider 1: CoinGecko Trending API (free, no key required)
    Provider 2: Binance Announcements (existing data, extract trending topics)
    Provider 3: Market-derived trending (volume/price spikes)
    Provider 4: Synthetic narrative feed (hardcoded topic-to-coin mapping)
    
    Never breaks the pipeline - if all providers fail, returns empty data.
    """
    
    # Comprehensive topic-to-coin mapping
    TOPIC_COIN_MAP = {
        # AI & AI Agents
        "AI": ["FET", "AGIX", "RNDR", "NEAR", "GRT", "OCEAN", "TAO", "AKT"],
        "AGENT": ["FET", "AGIX", "VIRTUAL", "AI16Z", "ARC"],
        "AI Agent": ["FET", "AGIX", "VIRTUAL", "AI16Z", "ARC"],
        
        # Meme Coins
        "MEME": ["DOGE", "SHIB", "PEPE", "BONK", "WIF", "FLOKI", "MEME"],
        "DOGE": ["DOGE"],
        "PEPE": ["PEPE"],
        "SHIB": ["SHIB"],
        
        # Layer 1
        "L1": ["SOL", "AVAX", "ADA", "DOT", "APT", "SUI", "SEI", "INJ", "TIA", "NEAR"],
        "SOL": ["SOL"],
        "AVAX": ["AVAX"],
        "SUI": ["SUI"],
        "APT": ["APT"],
        
        # Layer 2
        "L2": ["ARB", "OP", "MATIC", "POL", "STRK", "METIS"],
        
        # DeFi
        "DeFi": ["AAVE", "MKR", "UNI", "LINK", "COMP", "CRV", "CAKE", "PENDLE"],
        "RWA": ["ONDO", "MKR", "COMP", "LINK", "POL", "CFG"],
        
        # Gaming / Metaverse
        "GAMING": ["AXS", "SAND", "MANA", "THETA", "ENJ", "GALA", "IMX"],
        "METAVERSE": ["SAND", "MANA", "AXS", "THETA"],
        
        # DePIN
        "DePIN": ["FIL", "ICP", "HNT", "MOBILE", "IOTX"],
        "INFRA": ["ICP", "FIL", "ALGO", "EOS", "XLM", "VET", "TRX", "HBAR"],
        
        # Exchange Tokens
        "EXCHANGE": ["BNB", "LEO", "OKB", "CRO", "GT"],
        "BNB": ["BNB"],
        
        # BTC Ecosystem
        "BTC": ["BTC", "BTCB", "STX"],
        "BITCOIN": ["BTC"],
        
        # ETF / Regulation
        "ETF": ["BTC", "ETH"],
        "REGULATION": ["BTC", "ETH", "XRP"],
        
        # Stablecoins
        "STABLE": ["USDT", "USDC", "DAI", "FDUSD"],
        
        # Specific narratives
        "AIRDROP": ["LAYER", "AVNT", "SHELL", "STRK", "ARB", "OP", "APT"],
        "LISTING": ["LAYER", "AVNT", "SHELL", "NOT", "DOGS", "HMSTR"],
        "RESTAKE": ["ETHFI", "EIGEN", "REZ"],
        "LIQUID": ["LDO", "SSV", "PRL"],
    }
    
    # Known narrative categories (for scoring)
    NARRATIVE_CATEGORIES = [
        "AI", "AGENT", "MEME", "L1", "L2", "DeFi", "RWA", "GAMING",
        "DePIN", "INFRA", "EXCHANGE", "BTC", "ETF", "AIRDROP", "LISTING"
    ]
    
    def __init__(self, config: "Config" = None):
        self.config = config
        self._cache = []
        self._cache_time = 0
        self._provider_status = {}  # Track which providers work
    
    def get_trending(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Get trending topics from all available providers. Returns merged, ranked list."""
        now = time.time()
        if not force_refresh and self._cache and (now - self._cache_time) < 300:
            return self._cache
        
        all_topics = []
        
        # Try Provider 1: Binance Announcements (always available)
        try:
            ann_topics = self._from_announcements()
            all_topics.extend(ann_topics)
            self._provider_status["announcements"] = len(ann_topics) > 0
        except Exception:
            self._provider_status["announcements"] = False
        
        # Try Provider 2: CoinGecko Trending
        try:
            cg_topics = self._from_coingecko_trending()
            all_topics.extend(cg_topics)
            self._provider_status["coingecko"] = len(cg_topics) > 0
        except Exception:
            self._provider_status["coingecko"] = False
        
        # Try Provider 3: Market-derived (uses existing MarketScanner data pattern)
        try:
            market_topics = self._from_market_data()
            all_topics.extend(market_topics)
            self._provider_status["market"] = len(market_topics) > 0
        except Exception:
            self._provider_status["market"] = False
        
        # Provider 4: Synthetic / narrative-based (always available as fallback)
        try:
            synth_topics = self._synthetic_topics()
            all_topics.extend(synth_topics)
            self._provider_status["synthetic"] = len(synth_topics) > 0
        except Exception:
            self._provider_status["synthetic"] = False
        
        # Merge and deduplicate by topic name
        seen_topics = set()
        merged = []
        for topic in all_topics:
            key = topic.get("topic", "").lower().strip()
            if key and key not in seen_topics:
                seen_topics.add(key)
                merged.append(topic)
        
        # Sort by rank (lower = better)
        merged.sort(key=lambda t: t.get("rank", 99))
        
        # Log provider status
        working = [k for k, v in self._provider_status.items() if v]
        LOGGER.info("HotSearch providers active: %s (%d topics)", 
                    ", ".join(working) if working else "NONE", len(merged))
        
        self._cache = merged
        self._cache_time = now
        return merged
    
    def _from_announcements(self) -> List[Dict[str, Any]]:
        """Extract trending topics from Binance announcements."""
        topics = []
        try:
            engine = BinanceAnnouncementEngine(self.config)
            announcements = engine.get_trending_announcements()
            
            # Group announcements by type for topic extraction
            topic_counts = {}
            for ann in announcements:
                ann_type = ann.get("type", "news")
                title = ann.get("title", "")
                symbols = ann.get("symbols", [])
                
                # Extract narrative from title
                title_lower = title.lower()
                for narrative in self.NARRATIVE_CATEGORIES:
                    if narrative.lower() in title_lower:
                        topic_counts[narrative] = topic_counts.get(narrative, 0) + 1
                
                # Also add individual symbols as topics if they appear
                for sym in symbols:
                    topic_counts[sym] = topic_counts.get(sym, 0) + 1
            
            for i, (topic, count) in enumerate(sorted(topic_counts.items(), key=lambda x: -x[1])):
                affected = self._topic_to_coins(topic)
                topics.append({
                    "topic": topic,
                    "rank": i + 1,
                    "trend_strength": min(10.0, count * 2.5),
                    "source": "announcement",
                    "affected_coins": affected,
                    "narrative": self._detect_narrative(topic),
                    "hot_search_score": min(10.0, 5.0 + count * 1.5),
                })
        except Exception:
            pass
        return topics
    
    def _from_coingecko_trending(self) -> List[Dict[str, Any]]:
        """Fetch trending coins from CoinGecko (no API key needed)."""
        topics = []
        try:
            data = http_get_json(
                "https://api.coingecko.com/api/v3/search/trending",
                timeout=self.config.http_timeout_seconds if self.config else 10
            )
            coins = data.get("coins", [])
            for i, entry in enumerate(coins[:15]):
                item = entry.get("item", {})
                symbol = (item.get("symbol", "") or "").upper()
                name = item.get("name", "")
                score = item.get("score", i)
                
                # CoinGecko score: 0 = most trending
                trend_strength = max(1.0, 10.0 - score * 0.7)
                affected = self._topic_to_coins(symbol) or [symbol]
                
                topics.append({
                    "topic": symbol,
                    "name": name,
                    "rank": i + 1,
                    "trend_strength": trend_strength,
                    "source": "coingecko_trending",
                    "affected_coins": [symbol],
                    "narrative": self._detect_narrative(symbol),
                    "hot_search_score": min(10.0, trend_strength),
                })
        except Exception:
            pass
        return topics
    
    def _from_market_data(self) -> List[Dict[str, Any]]:
        """Derive trending topics from market data patterns."""
        topics = []
        try:
            scanner = MarketScanner(self.config)
            universe = scanner._universe()
            
            if not universe:
                return topics
            
            # Top gainers
            gainers = sorted(universe, key=lambda c: c.change_24h, reverse=True)[:3]
            for i, coin in enumerate(gainers):
                if coin.change_24h > 3:
                    topics.append({
                        "topic": f"{coin.symbol}_SURGE",
                        "rank": i + 1,
                        "trend_strength": min(10.0, 5.0 + abs(coin.change_24h) * 0.3),
                        "source": "market_gainer",
                        "affected_coins": [coin.symbol],
                        "narrative": self._detect_narrative(coin.symbol),
                        "hot_search_score": min(10.0, 4.0 + abs(coin.change_24h) * 0.3),
                    })
            
            # Volume spikes
            high_vol = [c for c in universe if c.volume_ratio > 2.0]
            for i, coin in enumerate(high_vol[:3]):
                topics.append({
                    "topic": f"{coin.symbol}_VOLUME",
                    "rank": 10 + i + 1,
                    "trend_strength": min(10.0, 3.0 + coin.volume_ratio * 2),
                    "source": "market_volume",
                    "affected_coins": [coin.symbol],
                    "narrative": self._detect_narrative(coin.symbol),
                    "hot_search_score": min(10.0, 3.0 + coin.volume_ratio * 1.5),
                })
        except Exception:
            pass
        return topics
    
    def _synthetic_topics(self) -> List[Dict[str, Any]]:
        """Fallback synthetic topics based on known narratives (always available)."""
        # Return a diverse set of narrative-based topics
        base_topics = [
            ("AI", "Artificial Intelligence", 9.0, "AI"),
            ("MEME", "Meme Coin Season", 7.5, "MEME"),
            ("DeFi", "DeFi Renaissance", 7.0, "DeFi"),
            ("L1", "Layer 1 Rally", 7.5, "L1"),
            ("RWA", "Real World Assets", 6.5, "RWA"),
            ("GAMING", "Web3 Gaming", 6.0, "GAMING"),
            ("DePIN", "DePIN Infrastructure", 6.0, "DePIN"),
            ("ETF", "ETF Inflows", 8.0, "ETF"),
            ("AIRDROP", "Airdrop Season", 7.0, "AIRDROP"),
        ]
        topics = []
        for i, (topic, name, strength, narrative) in enumerate(base_topics):
            affected = self._topic_to_coins(topic)
            topics.append({
                "topic": topic,
                "name": name,
                "rank": i + 1,
                "trend_strength": strength,
                "source": "synthetic",
                "affected_coins": affected,
                "narrative": narrative,
                "hot_search_score": strength,
            })
        return topics
    
    def _topic_to_coins(self, topic: str) -> List[str]:
        """Map a topic to affected coin symbols."""
        topic_upper = topic.upper().strip()
        # Direct match
        if topic_upper in self.TOPIC_COIN_MAP:
            return self.TOPIC_COIN_MAP[topic_upper]
        # Partial match
        for key, coins in self.TOPIC_COIN_MAP.items():
            if key in topic_upper or topic_upper in key:
                return coins
        # If topic itself looks like a coin symbol
        if re.match(r'^[A-Z]{2,10}$', topic_upper):
            return [topic_upper]
        return []
    
    def _detect_narrative(self, symbol_or_topic: str) -> str:
        """Detect narrative category from symbol or topic."""
        s = symbol_or_topic.upper().strip()
        for narrative, coins in self.TOPIC_COIN_MAP.items():
            if s in coins or s == narrative:
                return narrative
        return "GENERAL"
    
    def get_hot_search_score(self, symbol: str) -> float:
        """Get hot search score for a specific coin symbol (0-10)."""
        trending = self.get_trending()
        symbol_upper = symbol.upper().strip()
        max_score = 0.0
        
        for topic in trending:
            affected = topic.get("affected_coins", [])
            if symbol_upper in [c.upper() for c in affected]:
                score = topic.get("hot_search_score", 0)
                if score > max_score:
                    max_score = score
            # Also check if topic name matches symbol
            if topic.get("topic", "").upper() == symbol_upper:
                score = topic.get("hot_search_score", 0)
                if score > max_score:
                    max_score = score
        
        return max_score
    
    def get_top_trending(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top trending topics (ranked by strength)."""
        trending = self.get_trending()
        return [t for t in trending if t.get("source") != "synthetic"][:limit] or trending[:limit]
    
    def get_narrative_summary(self) -> str:
        """Get a one-line summary of current narratives for prompt injection."""
        trending = self.get_trending()
        if not trending:
            return ""
        
        top = trending[:5]
        parts = []
        for t in top:
            topic = t.get("topic", "")
            strength = t.get("trend_strength", 5)
            coins = t.get("affected_coins", [])
            coin_str = ", ".join([f"${c}" for c in coins[:3]]) if coins else ""
            parts.append(f"{topic}:{strength:.0f}/10{ ' (' + coin_str + ')' if coin_str else ''}")
        
        return " | ".join(parts)


# CoinGecko trending endpoint has rate limits - cache aggressively
_HOT_CACHE = None
_HOT_CACHE_TS = 0

class ResearchEngine:
    """Multi-dimensional research engine: technical, narrative, risk, and market context."""

    # Coin categories / narratives
    CATEGORIES = {
        "AI": {"FET", "AGIX", "RNDR", "NEAR", "ARB", "OP", "GRT", "FET", "AGIX", "OCEAN", "TAO", "AKT"},
        "MEME": {"DOGE", "SHIB", "PEPE", "BONK", "WIF", "FLOKI", "MEME"},
        "L1": {"SOL", "AVAX", "ADA", "DOT", "APT", "SUI", "SEI", "INJ", "TIA", "NEAR"},
        "BTC": {"BTC", "STX", "ORDI", "SATS", "RUNE"},
        "DeFi": {"AAVE", "MKR", "UNI", "LINK", "COMP", "CRV", "CAKE"},
        "L2": {"ARB", "OP", "MATIC", "POL", "STRK"},
        "RWA": {"MKR", "COMP", "LINK", "POL"},
        "GAMING": {"AXS", "SAND", "MANA", "THETA", "ENJ", "GALA", "IMX"},
        "INFRA": {"ICP", "FIL", "ALGO", "EOS", "XLM", "VET", "TRX", "HBAR"},
        "EXCHANGE": {"BNB", "LEO", "OKB", "CRO"},
    }

    def analyze(self, coin: Dict[str, Any], announcement: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Full research analysis on a coin."""
        symbol = coin.get("symbol", "")
        price = float(coin.get("price", 0) or 0)
        change = float(coin.get("change_24h", 0) or 0)
        volume_ratio = float(coin.get("volume_ratio", 1) or 1)
        volume_24h = float(coin.get("volume_24h", 0) or 0)
        market_cap = float(coin.get("market_cap", 0) or 0)
        history = coin.get("history", [])
        abs_change = abs(change)
        
        # 1. Category / Narrative detection
        category, narrative = self._detect_narrative(symbol)
        
        # 2. Technical signals
        tech = self._technical_analysis(history, price, change)
        
        # 3. Volume analysis
        vol_analysis = self._volume_analysis(volume_ratio, volume_24h, market_cap)
        
        # 4. Risk assessment
        risk_level, risk_factors = self._risk_assessment(price, market_cap, volume_ratio, change, category)
        
        # 5. Market context
        context = self._market_context(change, volume_ratio, category)
        
        # 6. Generate reason text
        reason_parts = []
        
        if announcement:
            ann_type = announcement.get("type", "")
            ann_title = announcement.get("title", "")
            if ann_type == "new_listing":
                reason_parts.append(f"${symbol} was just LISTED on Binance!")
            elif ann_type == "airdrop":
                reason_parts.append(f"${symbol} has an active Binance airdrop campaign!")
            elif ann_type == "delisting":
                reason_parts.append(f"${symbol} is under delisting monitoring on Binance.")
            else:
                reason_parts.append(f"${symbol} trending on Binance announcements.")
        
        reason_parts.append(f"${symbol} is showing a {change:+.1f}% {'surge' if change > 0 else 'drop'} with {volume_ratio:.1f}x volume.")
        
        if tech.get("pattern"):
            reason_parts.append(f"Chart pattern: {tech['pattern']}.")
        
        if vol_analysis.get("verdict"):
            reason_parts.append(vol_analysis["verdict"])
        
        reason = " ".join(reason_parts)

        # 7. Bull case
        bull_parts = []
        if tech.get("trend") == "bullish":
            bull_parts.append(f"Technical structure is {'strong' if tech.get('strength', 0) > 0.6 else 'improving'}.")
        if vol_analysis.get("bullish"):
            bull_parts.append(vol_analysis["bullish"])
        if change > 5:
            bull_parts.append("Strong momentum suggests continuation potential.")
        elif change > 0:
            bull_parts.append("Gradual accumulation phase with constructive price action.")
        else:
            bull_parts.append("Oversold conditions historically attract dip-buyers.")
        if category:
            bull_parts.append(f"The {category} narrative is gaining traction.")
        bull_case = " ".join(bull_parts)

        # 8. Bear case
        bear_parts = []
        if tech.get("trend") == "bearish":
            bear_parts.append("Technical structure is weakening.")
        if vol_analysis.get("bearish"):
            bear_parts.append(vol_analysis["bearish"])
        if market_cap > 1e11:
            bear_parts.append("Large caps move slower; upside may be capped.")
        elif change < -5:
            bear_parts.append("Downtrend intact until price reclaims key resistance.")
        else:
            bear_parts.append("Momentum could fade if volume drops off.")
        bear_case = " ".join(bear_parts)

        # 9. Risk note
        if risk_level == "high":
            risk = f"⚠️ High Risk: {risk_factors[0] if risk_factors else 'Use strict position sizing.'}"
        elif risk_level == "medium":
            risk = f"⚡ Medium Risk: {risk_factors[0] if risk_factors else 'Manage position size carefully.'}"
        else:
            risk = f"✓ Low Risk: {risk_factors[0] if risk_factors else 'Established asset with good liquidity.'}"

        return {
            "reason": reason,
            "bull_case": bull_case,
            "bear_case": bear_case,
            "risk": risk,
            "technical": tech,
            "volume_analysis": vol_analysis,
            "category": category,
            "narrative": narrative,
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "context": context,
            "announcement": announcement,
        }

    def _detect_narrative(self, symbol: str) -> tuple:
        """Detect coin category and narrative."""
        symbol_upper = symbol.upper()
        for category, coins in self.CATEGORIES.items():
            if symbol_upper in coins:
                return category, f"{category} narrative"
        return "", ""

    def _technical_analysis(self, history: List[float], price: float, change: float) -> Dict[str, Any]:
        """Basic technical analysis from price history."""
        result = {
            "pattern": "",
            "trend": "neutral",
            "strength": 0.5,
            "volatility": "medium",
        }
        
        if len(history) >= 5:
            prices = history[-5:]
            # Simple trend detection
            if prices[-1] > prices[0] * 1.05:
                result["trend"] = "bullish"
                result["strength"] = min(1.0, (prices[-1] / prices[0] - 1) * 5)
                if change > 5:
                    result["pattern"] = "Breakout from recent range"
                else:
                    result["pattern"] = "Steady uptrend with higher lows"
            elif prices[-1] < prices[0] * 0.95:
                result["trend"] = "bearish"
                result["strength"] = min(1.0, abs(prices[-1] / prices[0] - 1) * 3)
                if change < -5:
                    result["pattern"] = "Sharp selloff with momentum"
                else:
                    result["pattern"] = "Gradual distribution phase"
            else:
                if abs(change) < 2:
                    result["pattern"] = "Consolidation / ranging"
                else:
                    result["pattern"] = "Slight bias " + ("up" if change > 0 else "down")
            
            # Volatility estimate
            max_move = max(prices) / min(prices) - 1 if min(prices) > 0 else 0.05
            result["volatility"] = "high" if max_move > 0.08 else ("medium" if max_move > 0.03 else "low")
        
        return result

    def _volume_analysis(self, volume_ratio: float, volume_24h: float, market_cap: float) -> Dict[str, Any]:
        """Analyze volume patterns."""
        result = {
            "bullish": "",
            "bearish": "",
            "verdict": "",
        }
        
        if volume_ratio > 2.0:
            result["bullish"] = "Volume is 2x+ normal - strong participation."
            result["verdict"] = "Volume spike confirms active interest."
        elif volume_ratio > 1.5:
            result["bullish"] = "Above-average volume supporting the move."
            result["verdict"] = "Volume above baseline - notable activity."
        elif volume_ratio < 0.5:
            result["bearish"] = "Volume drying up - low conviction."
            result["verdict"] = "Thin volume - move may lack sustainability."
        elif volume_ratio < 1.0:
            result["bearish"] = "Below-average volume - weak participation."
            result["verdict"] = "Volume lagging - wait for confirmation."
        else:
            result["verdict"] = "Volume at normal levels - healthy market."        
        # Liquidity check
        if market_cap > 0 and volume_24h / market_cap < 0.01:
            result["bearish"] += " Low liquidity relative to market cap."
        
        return result

    def _risk_assessment(self, price: float, market_cap: float, volume_ratio: float, change: float, category: str) -> tuple:
        """Assess risk level and factors."""
        risk_factors = []
        
        if price < 0.1:
            risk_factors.append("Micro-cap pricing - extreme volatility possible.")
        elif price < 1:
            risk_factors.append("Low price point - percentage swings amplify.")
        
        if market_cap > 0 and market_cap < 10_000_000:
            risk_factors.append("Small market cap - higher downside risk.")
        elif market_cap > 10_000_000_000:
            risk_factors.append("")  # No risk for large caps
        
        if volume_ratio < 0.8:
            risk_factors.append("Thin volume - slippage risk on entry/exit.")
        
        if abs(change) > 20:
            risk_factors.append("Extreme daily move - potential reversal.")
        
        if category == "MEME":
            risk_factors.append("Meme coins have higher volatility and lower fundamentals.")
        
        # Clean up empty strings
        risk_factors = [f for f in risk_factors if f]
        
        if not risk_factors:
            risk_factors.append("Standard market risk - use proper position sizing.")
        
        # Determine risk level
        risk_score = len(risk_factors)
        if price < 0.1:
            risk_score += 1
        if abs(change) > 15:
            risk_score += 1
        
        if risk_score >= 3:
            return "high", risk_factors
        elif risk_score >= 1:
            return "medium", risk_factors
        return "low", risk_factors

    def _market_context(self, change: float, volume_ratio: float, category: str) -> str:
        """Generate market context sentence."""
        if change > 8:
            return f"{'Sector momentum' if category else 'Market'} is strongly bullish."
        elif change > 3:
            return f"Positive price action with {'sector' if category else 'market'} participation."
        elif change > 0:
            return "Mild bullish bias - wait for volume confirmation."
        elif change > -3:
            return "Slight bearish pressure - holding key support levels."
        elif change > -8:
            return f"Bearish momentum in {'the ' + category + ' sector' if category else 'this asset'}."
        else:
            return "Strong selling pressure - watch for capitulation or reversal."

    def score(self, coin: Dict[str, Any], category: str = "") -> float:
        """Score a coin for trending/posting priority."""
        change = float(coin.get("change_24h", 0))
        volume_ratio = float(coin.get("volume_ratio", 1))
        market_cap = float(coin.get("market_cap", 0) or 0)
        price = float(coin.get("price", 0) or 0)
        
        market_score = max(-5.0, min(5.0, change)) * 0.3
        volume_score = min(5.0, volume_ratio * 1.5) * 0.3
        cap_score = min(3.0, market_cap / 1e11) * 0.2
        interest_score = (abs(change) / 10 + volume_ratio / 2) * 0.2
        
        # Category bonus
        cat_bonus = 0
        if category == "AI":
            cat_bonus = 2.0
        elif category == "MEME":
            cat_bonus = 1.5
        elif category == "L1":
            cat_bonus = 1.0
        
        total = market_score + volume_score + cap_score + interest_score + cat_bonus
        return max(0, total)


class TradeSetup:
    def build(self, coin: Dict[str, Any]) -> Dict[str, str]:
        price = float(coin.get("price", 0))
        entry = price * 1.002
        target1 = price * 1.08
        target2 = price * 1.16
        stop = price * 0.94

        return {
            "entry": f"{entry:.6f}".rstrip("0").rstrip("."),
            "target1": f"{target1:.6f}".rstrip("0").rstrip("."),
            "target2": f"{target2:.6f}".rstrip("0").rstrip("."),
            "stop": f"{stop:.6f}".rstrip("0").rstrip("."),
        }

class EmotionEngine:
    @staticmethod
    def get_tone(coin: Dict[str, Any]) -> Dict[str, Any]:
        change = float(coin.get("change_24h", 0))
        vol = float(coin.get("volume_ratio", 1))

        if change > 5 and vol > 1.5:
            return {
                "persona": "FOMO Bull",
                "hook_emoji": "\U0001f680\U0001f4a5",
                "bull_emoji": "\U0001f4c8\U0001f48e",
                "bear_emoji": "\u26a0\ufe0f",
                "risk_emoji": "\U0001f6e1\U0001f4b0",
                "pro_tip_emoji": "💡",
                "twist": "Excitement is high, but be careful! Greed can be dangerous.",
            }
        elif change < -3:
            return {
                "persona": "Panic Bear",
                "hook_emoji": "\U0001f525",
                "bull_emoji": "\U0001f6c8",
                "bear_emoji": "\U0001f43b",
                "risk_emoji": "\u26a0\ufe0f",
                "pro_tip_emoji": "💡",
                "twist": "Blood is in the water, but smart people buy fear. Are you ready?",
            }
        else:
            return {
                "persona": "Cold Analyst",
                "hook_emoji": "\U0001f9d0",
                "bull_emoji": "\U0001f4c8",
                "bear_emoji": "\U0001f4c9",
                "risk_emoji": "\u2696\ufe0f",
                "pro_tip_emoji": "💡",
                "twist": "Leave emotions aside, only data speaks.",
            }


class GeminiGenerator:
    def __init__(self, config: Config = CONFIG):
        self.config = config
        self.emotion = EmotionEngine()

    def generate(
        self,
        analysis: Dict[str, str],
        setup: Dict[str, str],
        coin: Dict[str, Any],
        memory_summary: Optional[Dict[str, Any]] = None,
        past_examples: Optional[List[str]] = None,
        tone: Optional[Dict[str, Any]] = None,
        keywords: Optional[List[str]] = None,
        hot_search: Optional[str] = None,
    ) -> str:
        """Build a prompt and call the Gemini API to generate a post."""
        prompt = self._build_prompt(
            analysis=analysis,
            setup=setup,
            coin=coin,
            memory_summary=memory_summary,
            past_examples=past_examples,
            tone=tone,
            keywords=keywords,
            hot_search=hot_search,
        )

        if not self.config.gemini_api_key:
            LOGGER.warning("No GEMINI_API_KEY set; using template-based content")
            return self._template_content(analysis, setup, coin, tone, keywords)

        models_to_try = [
            "gemini-2.5-flash",
            os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash",
        ]
        # Deduplicate
        seen_models = set()
        models = []
        for m in models_to_try:
            if m not in seen_models:
                seen_models.add(m)
                models.append(m)

        # Try Gemini API (fast: 1 attempt per model, then fallback to template)
        for model in models:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent"
                f"?key={self.config.gemini_api_key}"
            )

            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": self.config.gemini_temperature,
                    "topP": self.config.gemini_top_p,
                    "maxOutputTokens": self.config.gemini_max_output_tokens,
                },
            }

            try:
                resp = http_post_json(url, payload, timeout=self.config.http_timeout_seconds, retries=3)
                text = resp["candidates"][0]["content"]["parts"][0]["text"]
                if text and text.strip():
                    LOGGER.info("Gemini %s generated post successfully", model)
                    return text.strip()
            except Exception as exc:
                LOGGER.warning("Gemini %s failed: %s", model, exc)
                continue

        LOGGER.warning("Gemini API failed all models; will save draft locally only")
        content = self._template_content(analysis, setup, coin, tone, keywords)
        # Save draft locally but don't publish - quality wouldn't be good enough
        try:
            drafts_dir = Path("drafts")
            drafts_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            draft_path = drafts_dir / f"draft_{coin.get('symbol', 'UNKNOWN')}_{ts}.md"
            draft_path.write_text(f"# DRAFT - Template content (Gemini failed)\n\n" + content)
            LOGGER.info("Saved draft to %s", draft_path)
        except Exception:
            pass
        # Return template content but mark it so publisher knows not to publish
        return "[DRAFT_TEMPLATE]" + content

    def _build_prompt(
        self,
        analysis: Dict[str, str],
        setup: Dict[str, str],
        coin: Dict[str, Any],
        memory_summary: Optional[Dict[str, Any]] = None,
        past_examples: Optional[List[str]] = None,
        tone: Optional[Dict[str, Any]] = None,
        keywords: Optional[List[str]] = None,
        hot_search: Optional[str] = None,
    ) -> str:
        """Build a concise prompt for Gemini to generate a high-quality trading post."""
        symbol = coin.get("symbol", "COIN")
        name = coin.get("name", symbol)
        price = coin.get("price", 0)
        change = coin.get("change_24h", 0)
        vol_ratio = coin.get("volume_ratio", 1)
        market_cap = coin.get("market_cap", 0)
        tone = tone or self.emotion.get_tone(coin)
        
        # Extract context
        reason = analysis.get("reason", "") if isinstance(analysis, dict) else str(analysis)
        bull_case = analysis.get("bull_case", "") if isinstance(analysis, dict) else ""
        bear_case = analysis.get("bear_case", "") if isinstance(analysis, dict) else ""
        risk = analysis.get("risk", "") if isinstance(analysis, dict) else ""
        category = analysis.get("category", "") if isinstance(analysis, dict) else ""
        narrative = analysis.get("narrative", "") if isinstance(analysis, dict) else ""
        announcement = analysis.get("announcement") if isinstance(analysis, dict) else None
        
        # Build a clean, effective prompt
        parts = [
            f"You are a 20-year veteran Wall Street crypto trader. Your current mood: {tone['persona']}. {tone['twist']}",
            "",
            f"Write an engaging trading post about ${symbol} ({name}). Make it sound human, exciting, and NOT like AI.",
            "",
            "**Market Data:**",
            f"- Price: ${price:.4f} | 24h Change: {change:+.1f}% | Volume: {vol_ratio:.1f}x | Cap: ${market_cap:,.0f}",
        ]
        
        if category:
            parts.append(f"- Category: {category} ({narrative})")
        
        parts.append("")
        parts.append(f"**Analysis:** {reason}")
        parts.append(f"**Bull Case:** {bull_case}")
        parts.append(f"**Bear Case:** {bear_case}") 
        parts.append(f"**Risk:** {risk}")
        parts.append("")
        parts.append("**Trading Setup:**")
        parts.append(f"- Entry: ${setup['entry']}")
        parts.append(f"- Target 1: ${setup['target1']} | Target 2: ${setup['target2']}")
        parts.append(f"- Stop: ${setup['stop']}")
        
        
        if hot_search:
            parts.append("")
            parts.append("**Binance Hot Search Trends:**")
            parts.append(hot_search)
        
        if announcement:
            parts.append("")
            parts.append(f"**Binance Announcement:** {announcement.get('title', '')}")
        
        parts.append("")
        parts.append("**Requirements - FOLLOW STRICTLY:**")
        parts.append("- Write a compelling 3-paragraph post (250-500 words total)")
        parts.append("- Start with a strong hook/attention grabber")
        parts.append("- Include relevant emojis naturally (🚀🔥📈💎📊💡)")
        parts.append(f"- END with 5-7 hashtags on a new line, first one MUST be #{symbol}")
        parts.append("- Sound like a real, experienced trader sharing genuine insights")
        parts.append("- Include a specific pro tip or key insight in the last paragraph")
        parts.append("- Never use robotic phrases like 'In the current market' or 'As of now'")
        parts.append("- Mention specific numbers (price, %, volume) from the data")
        parts.append(f"- {tone['twist']}")
        
        return "\n".join(parts)

    def _template_content(self, analysis, setup, coin, tone=None, keywords=None) -> str:
        """Generate human-like trading post (not spammy)."""
        symbol = coin.get("symbol", "COIN")
        name = coin.get("name", symbol)
        price = coin.get("price", 0)
        change = coin.get("change_24h", 0)
        vol_ratio = coin.get("volume_ratio", 1)
        market_cap = coin.get("market_cap", 0)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        direction = "up" if change >= 0 else "down"

        # Check if there is a Binance announcement for this coin
        announcement = analysis.get("announcement") if isinstance(analysis, dict) else None
        has_announcement = announcement is not None
        ann_type = announcement.get("type", "") if has_announcement else ""
        ann_title = announcement.get("title", "") if has_announcement else ""

        # Extract enhanced research data
        coin_category = analysis.get("category", "") if isinstance(analysis, dict) else ""
        tech_pattern = analysis.get("technical", {}).get("pattern", "") if isinstance(analysis, dict) else ""
        tech_trend = analysis.get("technical", {}).get("trend", "") if isinstance(analysis, dict) else ""
        risk_level = analysis.get("risk_level", "") if isinstance(analysis, dict) else ""
        narrative = analysis.get("narrative", "") if isinstance(analysis, dict) else ""

        # Category-based hook modifiers
        category_hook = ""
        if coin_category == "AI":
            category_hook = "AI narrative is heating up! "
        elif coin_category == "MEME":
            category_hook = "Community momentum building! "
        elif coin_category == "DeFi":
            category_hook = "DeFi ecosystem growing! "
        elif coin_category == "L1":
            category_hook = "Layer 1 fundamentals strong! "

        # Pick template style - more variety with 6 styles
        template_id = random.randint(0, 7)
        abs_change = abs(change)
        direction_word = "surge" if change >= 5 else ("drop" if change <= -5 else ("uptick" if change > 0 else "dip"))
        excitement = "explosive" if abs_change > 8 else ("strong" if abs_change > 4 else "notable")
        has_high_volume = vol_ratio > 1.5

        if template_id == 0:
            # Bold prediction / Conviction style (like the example)
            lines = [
                f"Guys.. Listen Carefully,",
                "",
                f"${symbol} has just begun its path towards the target ${setup.get('target1', '?')}, and the play is unfolding precisely as anticipated.",
                f"The next target ${setup.get('target2', '?')} will also be smashed if momentum continues.",
                "",
                f"${symbol} is currently trading at ${price:.4f} with {change:+.1f}% in the last 24 hours and volume at {vol_ratio:.1f}x the baseline.",
                f"{analysis.get('reason', 'The momentum is still in favor of the current trend.')}",
                "",
                f"For those who missed the earlier signal - you can still participate. Just be careful during pullbacks and manage your risk properly.",
                f"So long as the structure remains {'bullish' if change >= 0 else 'intact'}, these targets remain valid.",
                "",
                f"{'Congratulations to everyone who caught this move early!' if abs_change > 3 else 'Patience is key in these market conditions.'}",
                "",
                f"\U0001f4a1 **Pro Tip:** {'Scale in gradually, do not go all-in at once. Use limit orders near the entry zone.' if vol_ratio > 1.5 else 'Wait for a pullback to the support zone before entering. Patience pays in trading.'}",
                f"\u23f0 {now_str}",
                f"#{symbol} #CryptoAnalysis #TradingSignals",
            ]

        elif template_id == 1:
            # Educational / Market Update style
            lines = [
                f"Quick ${symbol} Market Update for today,",
                "",
                f"Price: ${price:.4f} | 24h Change: {change:+.1f}%",
                f"Volume is running at {vol_ratio:.1f}x the average, which tells us there is {'strong' if vol_ratio > 1.5 else 'moderate'} interest at these levels.",
                "",
                f"{analysis.get('reason', 'Price is showing interesting movement.')}",
                "",
                f"On the upside: {analysis.get('bull_case', 'Structure remains positive.')}",
                f"The risk to consider: {analysis.get('risk', 'Always manage your position size.')}",
                "",
                f"Key levels to watch:",
                f"  Entry Zone: ${setup.get('entry', '?')}",
                f"  Target 1: ${setup.get('target1', '?')}",
                f"  Target 2: ${setup.get('target2', '?')}",
                f"  Stop: ${setup.get('stop', '?')}",
                "",
                f"{'The volume confirms the move - worth keeping on radar.' if vol_ratio > 1.5 else 'Let the market prove itself before committing.'}",
                "",
                f"\U0001f4a1 **Pro Tip:** {'Use limit orders instead of market orders for better entry pricing. Tighten your stop as price approaches target 1.' if abs_change > 5 else 'Position size matters more than entry price. Never risk more than 2% on a single trade.'}",
                f"\u23f0 {now_str}",
                f"#{symbol} #CryptoMarket #TradeSetup",
            ]

        elif template_id == 2:
            # Friendly / Conversational style
            lines = [
                f"Hey everyone, let us talk about ${symbol}.",
                "",
                f"${name} is showing some interesting price action today - currently at ${price:.4f} with a {change:+.1f}% move in the last 24 hours.",
                f"Trading volume is at {vol_ratio:.1f}x compared to normal, which suggests {'something is brewing' if vol_ratio > 1.5 else 'steady trading conditions'}.",
                "",
                f'{"Binance just announced: " + ann_title[:100] + "..." if has_announcement else ("Volume just spiked to " + str(round(vol_ratio, 1)) + "x the average - something big is happening." if has_high_volume else "Price is reacting to market conditions with a " + str(round(abs_change, 1)) + "% move.")}',
                "",
                f"Bull case: {analysis.get('bull_case', 'If momentum continues, we could see further upside.')}",
                f"Main risk: {analysis.get('risk', 'Be smart with your entries and exits.')}",
                "",
                f"My setup for this one:",
                f"  Look for entries near ${setup.get('entry', '?')}",
                f"  First target: ${setup.get('target1', '?')}",
                f"  Second target: ${setup.get('target2', '?')}",
                f"  Stop loss: ${setup.get('stop', '?')}",
                "",
                f"{'Volume confirms the move here.' if vol_ratio > 1.5 else 'Not forcing the trade - waiting for confirmation.'}",
                "",
                f"\U0001f4a1 **Pro Tip:** {'The best trades come from preparation, not impulse. Set your alerts near the entry zone and wait for the setup to play out.' if vol_ratio > 1.3 else 'Sometimes the best trade is no trade. Wait for volume confirmation before entering.'}",
                f"\u23f0 {now_str}",
                f"#{symbol} #CryptoInsights #TradingCommunity",
            ]

        elif template_id == 3:
            # Short / Punchy style
            lines = [
                f"${symbol} - {change:+.1f}% in 24h. Here is what I am watching.",
                "",
                f"Price: ${price:.4f} | Volume: {vol_ratio:.1f}x | Cap: ${market_cap:,.0f}",
                "",
                f"{analysis.get('reason', 'Price is moving with notable volume.')}",
                "",
                f"Bull: {analysis.get('bull_case', 'Momentum is on the side of buyers.')}",
                f"Risk: {analysis.get('risk', 'Always use a stop loss.')}",
                "",
                f"Setup: ${setup.get('entry', '?')} \u2192 ${setup.get('target1', '?')} | Stop: ${setup.get('stop', '?')}",
                "",
                f"{'This one has my attention.' if abs_change > 4 else 'Keeping it on the watchlist for now.'}",
                "",
                f"\U0001f4a1 **Pro Tip:** {'Always have a stop loss and stick to it. The market can move against you fast. Protect your capital first.' if abs_change > 3 else 'Use this time to study the chart patterns. When volume picks up, you will be ready to act.'}",
                f"\u23f0 {now_str}",
                f"#{symbol} #CryptoSignals #Altcoins",
            ]

        elif template_id == 4 or template_id == 6:
            # News / Event Driven style
            lines = [
                f"\U0001f4a5 " + ('OFFICIAL: $' + symbol + ' ' + ann_type.replace("_", " ").upper() + '!' if has_announcement else f'BREAKING: $' + symbol + ' is making moves!'),
                "",
                f'{"Binance just announced: " + ann_title[:100] + "..." if has_announcement else ("Volume just spiked to " + str(round(vol_ratio, 1)) + "x the average - something big is happening." if has_high_volume else "Price is reacting to market conditions with a " + str(round(abs_change, 1)) + "% move.")}',
                f"${symbol} currently at ${price:.4f} with {change:+.1f}% in 24h.",
                "",
                f"{analysis.get('reason', 'Notable price action with increasing interest.')}",
                "",
                f"Key levels to track:",
                f"\U0001f4c8 Entry: ${setup.get('entry', '?')}",
                f"\U0001f3af Target 1: ${setup.get('target1', '?')}",
                f"\U0001f3af Target 2: ${setup.get('target2', '?')}",
                f"\U0001f6d1 Stop: ${setup.get('stop', '?')}",
                "",
                f"Bull: {analysis.get('bull_case', 'Structure looks promising for the bulls.')}",
                f"Risk: {analysis.get('risk', 'Always have a plan before entering.')}",
                "",
                f"\U0001f4a1 **Pro Tip:** {excitement.capitalize()} moves often see a retest before continuation. Wait for the pullback to get a better entry.",
                f"\u23f0 {now_str}",
                f"#{symbol} #CryptoNews #MarketAlert #Trading",
            ]

        elif template_id == 5:
            # Attention-grabbing style with strong opinion
            lines = [
                f"\U0001f534 ALERT: ${symbol} just flashed a {'BULLISH' if change >= 0 else 'BEARISH'} signal.",
                "",
                f"The charts are showing a {'continuation pattern' if abs_change > 3 else 'potential reversal'} with {abs_change:.1f}% {'gains' if change >= 0 else 'losses'} in 24h.",
                f"${symbol} is at ${price:.4f} with {vol_ratio:.1f}x normal volume.",
                "",
                f"Here is the thing:",
                f"{analysis.get('reason', 'The numbers do not lie. This move has conviction behind it.')}",
                "",
                f"Bull case: {analysis.get('bull_case', 'If the volume sustains, we go higher.')}",
                f"Risk factor: {analysis.get('risk', 'Do not chase green candles.')}",
                "",
                f"My levels:",
                f"  \U0001f511 Entry: ${setup.get('entry', '?')}",
                f"  \U0001f4c8 TP1: ${setup.get('target1', '?')} / TP2: ${setup.get('target2', '?')}",
                f"  \U0001f6d1 SL: ${setup.get('stop', '?')}",
                "",
                f"\U0001f4a1 **Pro Tip:** {'Do not FOMO into a moving train. Identify the right entry during pullbacks.' if has_high_volume else 'Patience separates profitable traders from gamblers. Wait for your setup.'}",
                f"\u23f0 {now_str}",
                f"#{symbol} #CryptoAlerts #TradingSetup",
            ]

        elif template_id == 7:
            # Short punchy variant
            symbol = coin.get("symbol", "COIN")
            price = coin.get("price", 0)
            change = coin.get("change_24h", 0)
            vol_ratio = coin.get("volume_ratio", 1)
            abs_change = abs(change)
            lines = [
                "$" + symbol + " | " + "{:+.1f}%".format(change) + " | Vol: " + "{:.1f}x".format(vol_ratio),
                "",
                str(analysis.get("reason", "Price action is notable today.")) if isinstance(analysis, dict) else str(analysis),
                "",
                str(analysis.get("bull_case", "Structure favors buyers.")) if isinstance(analysis, dict) else "Bullish structure.",
                "⚠️ " + (str(analysis.get("risk", "Manage your risk.")) if isinstance(analysis, dict) else "Manage your risk."),
                "",
                "💡 " + (str(analysis.get("bear_case", "")) if isinstance(analysis, dict) else ""),
                "⏰ " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "#" + symbol + " #Crypto #Trading",
            ]


        return "\n".join(lines)


class PostPublisher:
    def __init__(self, config: Config = CONFIG):
        self.config = config
        self.db = Database(config.database_path)
        self.image_engine = ImageIntelligenceEngine(config)
        self.image_uploader = ImageUploader(config)

    def publish(self, coin: Dict[str, Any], content: str) -> bool:
        # Check if this is a draft template (Gemini failed) - don't publish low quality
        if content.startswith("[DRAFT_TEMPLATE]"):
            actual_content = content.replace("[DRAFT_TEMPLATE]", "", 1)
            LOGGER.warning("Template fallback content - saving as draft only, not publishing to Square")
            self._save_locally(coin, actual_content, share_link="[DRAFT-Skipped-Gemini-unavailable]")
            try:
                self.db.save_post({"content": actual_content, "coin_symbol": coin.get("symbol", "")})
            except Exception:
                pass
            return True
        if self.config.dry_run:
            LOGGER.info("[DRY-RUN] Would publish post for %s", coin.get("symbol"))
            self._save_locally(coin, content, share_link="[DRY-RUN]")
            self._generate_post_image(coin)
            try:
                self.db.save_post({"content": content, "coin_symbol": coin.get("symbol", "")})
            except Exception as e:
                LOGGER.warning("Could not save post to DB: %s", e)
            return True

        # Generate and upload image before posting
        self._generate_post_image(coin)
        
        share_link = self._try_square_api(coin, content)
        if share_link:
            LOGGER.info("\U0001f4e1 Published successfully with link: %s", share_link)
            self._save_locally(coin, content, share_link=share_link)
        else:
            LOGGER.warning("Square API failed, saving locally")
            self._save_locally(coin, content, share_link=None)
        # Save to database for tracking
        try:
            self.db.save_post({"content": content, "coin_symbol": coin.get("symbol", "")})
        except Exception as e:
            LOGGER.warning("Could not save post to database: %s", e)
        return True

    def _try_square_api(self, coin: Dict[str, Any], content: str) -> str:
        """Publish to Binance Square via official Creator Center API."""
        square_key = self.config.square_api_key
        if not square_key:
            LOGGER.warning("No SQUARE_API_KEY set, saving locally")
            return ""

        payload = {
            "contentType": 1,
            "bodyTextOnly": self._limit_hashtags(content),
        }
        
        # Append image URL as plain text link (Binance Square renders clickable URLs)
        if isinstance(coin, dict):
            image_url = coin.get("_image_url", "")
            if image_url:
                symbol = coin.get("symbol", "")
                payload["bodyTextOnly"] += "\n\n📊 Chart: " + image_url
                verified = coin.get("_image_verified", False)
                LOGGER.info("Added image link to post (verified=%s): %s", verified, image_url)
        headers = {
            "X-Square-OpenAPI-Key": square_key,
            "Content-Type": "application/json",
            "clienttype": "binanceSkill",
        }

        url = "https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add"

        try:
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=self.config.http_timeout_seconds) as resp:
                resp_body = resp.read().decode("utf-8", errors="replace")

            LOGGER.info("Square API response: HTTP %d %s", resp.status, resp_body[:300])
            data = json.loads(resp_body)

            if data.get("code") == "000000":
                post_id = data.get("data", {}).get("id", "unknown")
                share_link = data.get("data", {}).get("shareLink", "")
                LOGGER.info("Published to Square! ID: %s Link: %s", post_id, share_link)
                return share_link
            else:
                LOGGER.warning("Square API error [%s]: %s", data.get("code"), data.get("message"))
                return ""
        except Exception as exc:
            LOGGER.warning("Square API request failed: %s", exc)
            return ""

    def _save_locally(self, coin: Dict[str, Any], content: str, share_link: str = None) -> None:
        """Save post to local file with share link if available."""
        symbol = coin.get("symbol", "UNKNOWN")
        posts_dir = Path("posts")
        posts_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f"post_{symbol}_{ts}.md"
        path = posts_dir / filename
        try:
            header = f"---\nSymbol: {symbol}\nTime: {ts} UTC\n"
            if share_link:
                header += f"Square Link: {share_link}\n"
            header += "---\n\n"
            path.write_text(header + content)
            LOGGER.info("Saved post locally: %s (link: %s)", path, share_link or "N/A")
        except Exception as e:
            LOGGER.error("Could not save locally: %s", e)

    def _generate_post_image(self, coin: Dict[str, Any]) -> None:
        """Generate professional trading image for a post."""
        try:
            v5_data = coin.get("_v5", {})
            if not v5_data:
                v5_data = None
            
            analysis_data = coin.get("_analysis", {})
            if not analysis_data:
                analysis_data = self._build_analysis_for_image(coin)
            
            setup_data = coin.get("_setup", {})
            if not setup_data:
                from main import TradeSetup
                setup_data = TradeSetup().build(coin)
            
            # Generate image
            img_path = self.image_engine.generate(coin, analysis_data, setup_data, v5_data)
            
            # Try to upload image and get public URL
            if img_path:
                img_url, img_verified = self.image_uploader.upload(img_path)
                if img_url:
                    coin["_image_url"] = img_url
                    coin["_image_verified"] = img_verified
                    if img_verified:
                        LOGGER.info("Image URL verified for post: %s", img_url)
                    else:
                        LOGGER.info("Image URL (unverified): %s", img_url)
                else:
                    coin["_image_url"] = ""
                    coin["_image_verified"] = False
        except Exception as e:
            LOGGER.debug("Image generation skipped: %s", e)

    def _build_analysis_for_image(self, coin: Dict[str, Any]) -> Dict[str, Any]:
        """Build simple analysis dict for image generation when full analysis unavailable."""
        change = float(coin.get("change_24h", 0) or 0)
        return {
            "reason": f"{coin.get('symbol')} showing {change:+.1f}% move with notable volume.",
            "bull_case": "Bullish structure with momentum.",
            "bear_case": "Standard market risks apply.",
            "risk": "Use proper position sizing.",
            "category": coin.get("narrative", ""),
            "narrative": coin.get("narrative", ""),
        }

    @staticmethod
    def _limit_hashtags(content: str, max_tags: int = 5) -> str:
        """Limit hashtags in content to max_tags. Binance Square allows ~5 max."""
        import re
        # Extract all hashtags
        tags = re.findall(r'#[A-Za-z0-9_]+', content)
        if len(tags) <= max_tags:
            return content
        
        # Remove all hashtags from content
        text = re.sub(r'#[A-Za-z0-9_]+', '', content)
        # Clean up extra spaces
        text = re.sub(r' +', ' ', text).strip()
        # Keep only first max_tags hashtags
        keep_tags = tags[:max_tags]
        # Add back at the end
        return text + '\n' + ' '.join(keep_tags)




class ScoringEngineV5:
    """BINANCE SQUARE CREATOR AGENT V5 ELITE
    Reward-Optimized Scoring Engine (10/10)
    
    Selects the coin with highest probability of:
    - Binance Square visibility
    - Engagement & ranking
    - Creator rewards
    
    Final Score = Market(10) + Volume(10) + Technical(10) + Momentum(5) 
                + Narrative(15) + Announcement(15) + HotSearch(15) 
                + CrowdInterest(5) + CreatorOpportunity(10) + EngagementPrediction(5) 
                - RiskPenalty(0-20)
    
    Max = 100
    """
    
    # Announcement score mapping
    ANNOUNCEMENT_SCORES = {
        "new_listing": 15,
        "launchpool": 14,
        "megadrop": 14,
        "airdrop": 13,
        "delisting": 10,
        "news": 5,
    }
    
    # Narrative score mapping
    NARRATIVE_SCORES = {
        "AI": 15, "AGENT": 15,
        "MEME": 13,
        "L1": 12, "L2": 10,
        "DeFi": 11, "RWA": 12,
        "GAMING": 9, "DEPIN": 10,
        "INFRA": 8, "EXCHANGE": 7,
        "BTC": 12, "ETF": 13,
        "AIRDROP": 14, "LISTING": 15,
    }
    
    # Emergency override event types (always enter top candidates)
    EMERGENCY_EVENTS = {"new_listing", "launchpool", "megadrop", "airdrop"}
    
    def __init__(self, research: "ResearchEngine", hot_search: "HotSearchEngine" = None):
        self.research = research
        self.hot_search = hot_search
    
    def compute(
        self,
        coin: Dict[str, Any],
        announcement: Optional[Dict[str, Any]] = None,
        posted_hours_ago: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Compute full V5 score for a single coin candidate."""
        result = {
            "market_score": 0.0,
            "volume_score": 0.0,
            "technical_score": 0.0,
            "momentum_score": 0.0,
            "narrative_score": 0.0,
            "announcement_score": 0.0,
            "hot_search_score": 0.0,
            "crowd_interest_score": 0.0,
            "creator_opportunity_score": 0.0,
            "engagement_prediction_score": 0.0,
            "risk_penalty": 0.0,
            "final_score": 0.0,
            "emergency_override": False,
        }
        
        symbol = coin.get("symbol", "")
        price = float(coin.get("price", 0) or 0)
        change = float(coin.get("change_24h", 0) or 0)
        volume_ratio = float(coin.get("volume_ratio", 1) or 1)
        volume_24h = float(coin.get("volume_24h", 0) or 0)
        market_cap = float(coin.get("market_cap", 0) or 0)
        abs_change = abs(change)
        history = coin.get("history", [])
        
        # Detect narrative
        category, narrative_str = self.research._detect_narrative(symbol)
        
        # Run technical analysis
        tech = self.research._technical_analysis(history, price, change)
        
        # --------------------------------------------------
        # 1. MARKET SCORE (0-10)
        # --------------------------------------------------
        # Change contribution (0-7)
        if abs_change >= 15:
            market_score = 10.0
        elif abs_change >= 10:
            market_score = 8.0
        elif abs_change >= 8:
            market_score = 7.0
        elif abs_change >= 5:
            market_score = 5.0
        elif abs_change >= 3:
            market_score = 4.0
        elif abs_change >= 1.5:
            market_score = 2.0
        else:
            market_score = 0.0
        
        # Volatility bonus (0-3 extra)
        if tech.get("volatility") == "high":
            market_score = min(10.0, market_score + 2.0)
        elif tech.get("volatility") == "low":
            market_score = max(0.0, market_score - 1.0)
        
        result["market_score"] = round(market_score, 1)
        
        # --------------------------------------------------
        # 2. VOLUME SCORE (0-10)
        # --------------------------------------------------
        if volume_ratio >= 3.0:
            volume_score = 10.0
        elif volume_ratio >= 2.5:
            volume_score = 9.0
        elif volume_ratio >= 2.0:
            volume_score = 7.0
        elif volume_ratio >= 1.5:
            volume_score = 5.0
        elif volume_ratio >= 1.0:
            volume_score = 3.0
        else:
            volume_score = 1.0
        
        # Liquidity bonus (high market cap = more liquid)
        if market_cap > 1e9:
            volume_score = min(10.0, volume_score + 1.0)
        
        result["volume_score"] = round(volume_score, 1)
        
        # --------------------------------------------------
        # 3. TECHNICAL SCORE (0-10)
        # --------------------------------------------------
        tech_score = 5.0  # Default neutral
        pattern = tech.get("pattern", "")
        trend = tech.get("trend", "neutral")
        strength = tech.get("strength", 0.5)
        
        if trend == "bullish":
            tech_score = 5.0 + strength * 5.0
        elif trend == "bearish":
            tech_score = 5.0 - strength * 3.0
        
        # Pattern bonuses
        if "Breakout" in pattern:
            tech_score = min(10.0, tech_score + 2.0)
        elif "selloff" in pattern.lower():
            tech_score = max(0.0, tech_score - 1.0)
        elif "Consolidation" in pattern:
            tech_score = max(1.0, tech_score - 2.0)
        elif "uptrend" in pattern.lower() or "rally" in pattern.lower():
            tech_score = min(10.0, tech_score + 1.5)
        
        result["technical_score"] = round(tech_score, 1)
        
        # --------------------------------------------------
        # 4. MOMENTUM SCORE (0-5)
        # --------------------------------------------------
        momentum_score = 0.0
        
        # Breakout detection
        if "Breakout" in pattern:
            momentum_score += 2.0
        if "buyers" in str(tech.get("trend", "")).lower() or "bull" in str(tech.get("trend", "")).lower():
            momentum_score += 1.0
        
        # Change-based momentum
        if abs_change > 8:
            momentum_score += 1.5
        elif abs_change > 5:
            momentum_score += 1.0
        elif abs_change > 3:
            momentum_score += 0.5
        
        # Volume confirmation
        if volume_ratio > 2.0 and abs_change > 3:
            momentum_score += 1.0
        
        # Reversal potential
        if trend == "bearish" and abs_change > 5 and volume_ratio > 2.0:
            momentum_score += 1.5  # Potential reversal
        
        result["momentum_score"] = round(min(5.0, momentum_score), 1)
        
        # --------------------------------------------------
        # 5. NARRATIVE SCORE (0-15)
        # --------------------------------------------------
        narrative_score = 0.0
        if category and category in self.NARRATIVE_SCORES:
            narrative_score = self.NARRATIVE_SCORES[category]
        else:
            narrative_score = 3.0 if category else 1.0
        
        # Boost if announcement matches narrative
        if announcement and category:
            ann_type = announcement.get("type", "")
            if ann_type in ("new_listing", "airdrop") and category in ("AI", "MEME", "L1"):
                narrative_score = min(15.0, narrative_score + 2.0)
        
        result["narrative_score"] = round(narrative_score, 1)
        
        # --------------------------------------------------
        # 6. ANNOUNCEMENT SCORE (0-15)
        # --------------------------------------------------
        ann_score = 0.0
        ann_type = ""
        if announcement:
            ann_type = announcement.get("type", "news")
            ann_score = self.ANNOUNCEMENT_SCORES.get(ann_type, 5.0)
            
            # Flag emergency override
            if ann_type in self.EMERGENCY_EVENTS:
                result["emergency_override"] = True
        elif coin.get("announcement_boost"):
            raw_type = coin.get("announcement_type", "news")
            ann_score = self.ANNOUNCEMENT_SCORES.get(raw_type, 5.0)
            if raw_type in self.EMERGENCY_EVENTS:
                result["emergency_override"] = True
        
        result["announcement_score"] = round(ann_score, 1)
        
        # --------------------------------------------------
        # 7. HOT SEARCH SCORE (0-15)
        # --------------------------------------------------
        hs_score = 0.0
        if self.hot_search is not None:
            try:
                hs_raw = self.hot_search.get_hot_search_score(symbol)
                # Map 0-10 to 0-15
                hs_score = hs_raw * 1.5
            except Exception:
                pass
        else:
            # Fallback: narrative-based estimation
            if category and category in self.NARRATIVE_SCORES:
                hs_score = self.NARRATIVE_SCORES[category] * 0.7
        
        result["hot_search_score"] = round(hs_score, 1)
        
        # --------------------------------------------------
        # 8. CROWD INTEREST SCORE (0-5)
        # --------------------------------------------------
        crowd_score = 0.0
        
        # Derived from hot search + volume + narrative
        if hs_score > 10:
            crowd_score += 2.0
        if volume_ratio > 2.0:
            crowd_score += 1.0
        if abs_change > 5:
            crowd_score += 1.0
        if category in ("AI", "MEME", "L1"):
            crowd_score += 1.0
        if coin.get("announcement_boost"):
            crowd_score += 1.0
        
        result["crowd_interest_score"] = round(min(5.0, crowd_score), 1)
        
        # --------------------------------------------------
        # 9. CREATOR OPPORTUNITY SCORE (0-10)
        # --------------------------------------------------
        opp_score = 0.0
        
        # Narrative strength (0-3)
        if category:
            opp_score += min(3.0, self.NARRATIVE_SCORES.get(category, 1) / 5.0)
        
        # Search/trend potential (0-3)
        if hs_score > 7:
            opp_score += 3.0
        elif hs_score > 3:
            opp_score += 2.0
        else:
            opp_score += 0.5
        
        # Visibility potential (0-2)
        if market_cap > 1e9:
            opp_score += 1.0
        if volume_ratio > 1.5:
            opp_score += 1.0
        
        # Discussion potential (0-2)
        if abs_change > 5:
            opp_score += 1.0
        if announcement:
            opp_score += 1.0
        
        result["creator_opportunity_score"] = round(min(10.0, opp_score), 1)
        
        # --------------------------------------------------
        # 10. ENGAGEMENT PREDICTION SCORE (0-5)
        # --------------------------------------------------
        engage_score = 0.0
        
        # Predicted engagement based on:
        # - Change magnitude (people engage with big moves)
        engage_score += min(1.5, abs_change / 10.0)
        
        # - Volume (active discussion)
        engage_score += min(1.0, volume_ratio / 3.0)
        
        # - Narrative (trending topics get more engagement)
        if category and category in self.NARRATIVE_SCORES:
            engage_score += min(1.5, self.NARRATIVE_SCORES[category] / 10.0)
        
        # - Hot search (already searched = engaged)
        engage_score += min(1.0, hs_score / 15.0)
        
        result["engagement_prediction_score"] = round(min(5.0, engage_score), 1)
        
        # --------------------------------------------------
        # RISK PENALTY (0 to -20)
        # --------------------------------------------------
        risk_penalty = 0.0
        
        if price < 0.1:
            risk_penalty += 4.0
        elif price < 1.0:
            risk_penalty += 2.0
        
        if market_cap > 0:
            if market_cap < 10_000_000:
                risk_penalty += 5.0
            elif market_cap < 50_000_000:
                risk_penalty += 3.0
            elif market_cap < 200_000_000:
                risk_penalty += 1.0
        
        if volume_ratio < 0.8:
            risk_penalty += 3.0
        
        if abs_change > 20:
            risk_penalty += 3.0
        elif abs_change > 12:
            risk_penalty += 1.0
        
        if category == "MEME" and market_cap < 100_000_000:
            risk_penalty += 2.0
        
        result["risk_penalty"] = round(min(20.0, risk_penalty), 1)
        
        # --------------------------------------------------
        # FINAL SCORE CALCULATION
        # --------------------------------------------------
        final = (
            result["market_score"] * 1.0            # 10%
            + result["volume_score"] * 1.0          # 10%
            + result["technical_score"] * 1.0       # 10%
            + result["momentum_score"] * 1.0        # 5%  (max 5)
            + result["narrative_score"] * 1.0       # 15% (max 15)
            + result["announcement_score"] * 1.0    # 15% (max 15)
            + result["hot_search_score"] * 1.0      # 15% (max 15)
            + result["crowd_interest_score"] * 1.0  # 5%  (max 5)
            + result["creator_opportunity_score"] * 1.0  # 10% (max 10)
            + result["engagement_prediction_score"] * 1.0  # 5% (max 5)
            - result["risk_penalty"]
        )
        
        result["final_score"] = round(max(0.0, final), 1)
        
        return result



def run_once(config, scanner, announcement_engine, research, trade_setup, generator, publisher, posted_symbols, hot_search_engine=None) -> bool:
    """Run one iteration of post generation and publishing."""
    # Fetch Binance announcements
    announcements = []
    try:
        announcements = announcement_engine.get_trending_announcements()
        for a in announcements[:5]:
            LOGGER.info("Announcement: [%s] %s - symbols: %s", a["type"], a["title"][:60], a["symbols"])
    except Exception as e:
        LOGGER.warning("Could not fetch announcements: %s", e)

    # Get candidates from market data
    top_gainers = scanner.top_gainers(limit=7)
    top_losers = scanner.top_losers(limit=7)
    volume_spikes = scanner.volume_spikes(threshold=1.75)

    # Merge all candidates
    all_candidates = []
    for coin in top_gainers[:4]:
        all_candidates.append(coin)
    for coin in top_losers[:4]:
        if coin.get("symbol") not in [c.get("symbol") for c in all_candidates]:
            all_candidates.append(coin)
    for coin in volume_spikes[:4]:
        if coin.get("symbol") not in [c.get("symbol") for c in all_candidates]:
            all_candidates.append(coin)

    # Announcement priority boost
    for a in announcements:
        for sym in a.get("symbols", []):
            found = False
            for c in all_candidates:
                if c.get("symbol") == sym:
                    c["announcement_boost"] = True
                    c["announcement_type"] = a.get("type", "news")
                    c["announcement_title"] = a.get("title", "")
                    found = True
                    break
            if not found:
                universe = scanner._universe()
                for c in universe:
                    if c.symbol == sym:
                        coin_dict = c.as_dict()
                        coin_dict["announcement_boost"] = True
                        coin_dict["announcement_type"] = a.get("type", "news")
                        coin_dict["announcement_title"] = a.get("title", "")
                        all_candidates.append(coin_dict)
                        break

    # Filter and deduplicate
    seen = set()
    unique_candidates = []
    for coin in all_candidates:
        sym = coin.get("symbol")
        price = float(coin.get("price", 0) or 0)
        change = float(coin.get("change_24h", 0) or 0)
        market_cap = float(coin.get("market_cap", 0) or 0)
        volume_ratio = float(coin.get("volume_ratio", 1) or 1)

        if price <= 0 or price < 0.01:
            continue
        if abs(change) > 150:
            continue
        if market_cap > 0 and market_cap < 100000:
            continue
        if sym in seen:
            continue
        # Skip coins with no real movement unless they have an announcement
        if not coin.get("announcement_boost"):
            if abs(change) < 1.5 and volume_ratio < 0.8:
                continue
        seen.add(sym)
        unique_candidates.append(coin)

    if not unique_candidates:
        LOGGER.info("No candidates found.")
        return False

    # --------------------------------------------------
    # V5 ELITE SCORING ENGINE
    # --------------------------------------------------
    # Get posted hours dict for precision penalty
    posted_hours_data = {}
    try:
        if hasattr(publisher, 'db') and publisher.db is not None:
            posted_hours_data = publisher.db.get_posted_hours_dict(hours=72)
    except Exception:
        posted_hours_data = {}
    
    # Initialize V5 scoring engine
    v5_engine = ScoringEngineV5(research, hot_search_engine)
    
    # Calculate V5 scores for all candidates
    scored_candidates = []
    for coin in unique_candidates:
        sym = coin.get("symbol", "")
        
        # Build announcement data if present
        ann_data = None
        if coin.get("announcement_boost"):
            ann_data = {
                "type": coin.get("announcement_type", "news"),
                "title": coin.get("announcement_title", ""),
            }
        
        # Get hours ago if recently posted
        hours_ago = posted_hours_data.get(sym.upper(), None)
        
        # Compute V5 score
        score_result = v5_engine.compute(coin, announcement=ann_data, posted_hours_ago=hours_ago)
        
        # Apply post repetition penalty
        final = score_result["final_score"]
        if hours_ago is not None:
            if hours_ago < 24:
                final *= 0.2
                score_result["repetition_penalty"] = "CRITICAL (<24h)"
            elif hours_ago < 48:
                final *= 0.5
                score_result["repetition_penalty"] = "HIGH (<48h)"
            elif hours_ago < 72:
                final *= 0.7
                score_result["repetition_penalty"] = "MEDIUM (<72h)"
            else:
                score_result["repetition_penalty"] = "NONE"
        else:
            score_result["repetition_penalty"] = "NONE"
        
        score_result["final_score"] = round(final, 1)
        coin["_score"] = final
        coin["_v5"] = score_result
        coin["hot_search_score"] = score_result["hot_search_score"]
        scored_candidates.append((coin, score_result))
    
    # Sort by final score
    unique_candidates.sort(key=lambda c: c.get("_score", 0), reverse=True)
    top_pick = unique_candidates[0]
    
    # Log V5 score breakdown for top pick
    v5 = top_pick.get("_v5", {})
    LOGGER.info("V5 SCORE: %.1f/100 | Mkt=%.1f Vol=%.1f Tech=%.1f Mom=%.1f Narr=%.1f Ann=%.1f HS=%.1f Crowd=%.1f Opp=%.1f Eng=%.1f Risk=%.1f %s",
                top_pick.get("_score", 0),
                v5.get("market_score", 0),
                v5.get("volume_score", 0),
                v5.get("technical_score", 0),
                v5.get("momentum_score", 0),
                v5.get("narrative_score", 0),
                v5.get("announcement_score", 0),
                v5.get("hot_search_score", 0),
                v5.get("crowd_interest_score", 0),
                v5.get("creator_opportunity_score", 0),
                v5.get("engagement_prediction_score", 0),
                v5.get("risk_penalty", 0),
                v5.get("repetition_penalty", ""))
    
    LOGGER.info("Selected %s - change: %.1f%%, vol: %.1fx (score: %.1f)%s",
                top_pick.get("symbol"),
                float(top_pick.get("change_24h", 0) or 0),
                float(top_pick.get("volume_ratio", 1) or 1),
                top_pick.get("_score", 0),
                " [ANNOUNCEMENT: " + top_pick.get("announcement_type", "") + "]" if top_pick.get("announcement_boost") else "")

    ann_data = None
    if top_pick.get("announcement_boost"):
        ann_data = {
            "type": top_pick.get("announcement_type", "news"),
            "title": top_pick.get("announcement_title", ""),
        }
    analysis = research.analyze(top_pick, announcement=ann_data)
    setup = trade_setup.build(top_pick)
    
    # Store analysis and setup on coin for image generation
    top_pick["_analysis"] = analysis if isinstance(analysis, dict) else {}
    top_pick["_setup"] = setup

    # Get hot search context
    hot_search_str = None
    if hot_search_engine is not None:
        try:
            hs_narrative = hot_search_engine.get_narrative_summary()
            if hs_narrative:
                sym = top_pick.get("symbol", "")
                hs_score = top_pick.get("hot_search_score", 0)
                if hs_score > 0:
                    hot_search_str = f"${sym} is hot on Binance (score: {hs_score:.0f}/10). Current narratives: {hs_narrative}"
                else:
                    hot_search_str = f"Current trending narratives: {hs_narrative}"
                LOGGER.info("Hot search context: %s", hot_search_str[:120])
        except Exception as e:
            LOGGER.debug("Hot search context unavailable: %s", e)

    LOGGER.info("Generating post for %s...", top_pick.get("symbol"))
    content = generator.generate(analysis=analysis, setup=setup, coin=top_pick, hot_search=hot_search_str)

    publisher.publish(top_pick, content)
    LOGGER.info("Done - post generated for %s", top_pick.get("symbol"))
    return True


def main_loop() -> None:
    """Main loop that runs continuously with configured interval."""
    config = CONFIG
    config.validate()
    
    interval = config.post_interval
    max_iter = config.max_iterations
    
    scanner = MarketScanner(config)
    announcement_engine = BinanceAnnouncementEngine(config)
    hot_search_engine = HotSearchEngine(config)
    research = ResearchEngine()
    trade_setup = TradeSetup()
    generator = GeminiGenerator(config)
    publisher_db = Database(config.database_path)
    publisher = PostPublisher(config)
    publisher.db = publisher_db
    
    iteration = 0
    posted_symbols = set()
    
    LOGGER.info("=" * 60)
    LOGGER.info("Binance Square Auto Poster started")
    LOGGER.info("Interval: %d seconds (%.1f hours)", interval, interval / 3600)
    LOGGER.info("Max iterations: %s", "unlimited" if max_iter <= 0 else str(max_iter))
    LOGGER.info("Live market data: %s", config.live_market_data)
    LOGGER.info("Dry run: %s", config.dry_run)
    LOGGER.info("=" * 60)
    
    while True:
        iteration += 1
        LOGGER.info("--- Iteration %d ---", iteration)
        
        try:
            posted_symbols = publisher_db.get_posted_symbols(hours=48)
        except Exception:
            posted_symbols = set()
        
        try:
            run_once(config, scanner, announcement_engine, research, trade_setup, generator, publisher, posted_symbols, hot_search_engine)
        except Exception as e:
            LOGGER.error("Iteration %d failed: %s", iteration, e)
            import traceback
            LOGGER.error(traceback.format_exc())
        
        if 0 < max_iter <= iteration:
            LOGGER.info("Reached max_iterations=%d, stopping.", max_iter)
            break
        
        LOGGER.info("Waiting %d seconds (%.1f hours) until next post...", interval, interval / 3600)
        sleep_chunk = min(interval, 60)
        slept = 0
        while slept < interval:
            time.sleep(sleep_chunk)
            slept += sleep_chunk


def main() -> None:
    """Single run mode - for cron/scheduled usage."""
    config = CONFIG
    config.validate()
    
    scanner = MarketScanner(config)
    announcement_engine = BinanceAnnouncementEngine(config)
    hot_search_engine = HotSearchEngine(config)
    research = ResearchEngine()
    trade_setup = TradeSetup()
    generator = GeminiGenerator(config)
    publisher_db = Database(config.database_path)
    publisher = PostPublisher(config)
    publisher.db = publisher_db
    
    posted_symbols = publisher_db.get_posted_symbols(hours=48)
    run_once(config, scanner, announcement_engine, research, trade_setup, generator, publisher, posted_symbols)


if __name__ == "__main__":
    # If post_interval > 0, run in loop mode
    if CONFIG.post_interval > 0:
        main_loop()
    else:
        main()
