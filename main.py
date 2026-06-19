import json
import os
import signal
import logging
import sqlite3
import re
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


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
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            http_timeout_seconds=int(os.getenv("HTTP_TIMEOUT_SECONDS", "15")),
            gemini_temperature=float(os.getenv("GEMINI_TEMPERATURE", "0.9")),
            gemini_top_p=float(os.getenv("GEMINI_TOP_P", "0.95")),
            gemini_max_output_tokens=int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "512")),
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
) -> Any:
    return _http_json_with_retry("POST", url, timeout, payload=payload, headers=headers)


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
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
            last_error = exc
            if attempt >= retries - 1:
                break
            sleep_for = min(2 ** attempt, 8)
            LOGGER.warning("HTTP %s %s failed, retrying in %ss: %s", method, url, sleep_for, exc)
            time.sleep(sleep_for)
    assert last_error is not None
    raise last_error


# =========================
# DATA MODEL
# =========================


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


# =========================
# DATABASE LAYER
# =========================


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
            self._ensure_metric_post_id_column()

    def _ensure_metric_post_id_column(self) -> None:
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(metrics)").fetchall()}
        if "post_id" not in columns:
            with self.conn:
                self.conn.execute("ALTER TABLE metrics ADD COLUMN post_id INTEGER")

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


# =========================
# MARKET SCANNER
# =========================


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
        url = "https://api.binance.com/api/v3/ticker/24hr"
        payload = http_get_json(url, timeout=self.config.http_timeout_seconds)
        coins: List[Coin] = []

        ranked = sorted(
            [item for item in payload if str(item.get("symbol", "")).endswith("USDT")],
            key=lambda item: float(item.get("quoteVolume", 0) or 0),
            reverse=True,
        )[:12]

        for item in ranked:
            symbol = item.get("symbol", "")
            base_symbol = symbol[:-4]
            try:
                price = float(item.get("lastPrice", 0))
                change_24h = float(item.get("priceChangePercent", 0))
                volume_24h = float(item.get("quoteVolume", 0))
                volume_ratio = max(1.0, float(item.get("count", 0)) / 1000.0)
                market_cap = max(volume_24h * 10, price * 1e6)
                history = self._live_history(symbol) or self._synthetic_history(price, change_24h)
            except (TypeError, ValueError):
                continue

            coins.append(
                Coin(
                    base_symbol,
                    base_symbol,
                    price,
                    change_24h,
                    volume_24h,
                    volume_ratio,
                    market_cap,
                    history,
                )
            )

        return coins or self._build_universe()

    def _live_history(self, symbol: str) -> List[float]:
        url = f"https://api.binance.com/api/v3/klines?symbol={urllib.parse.quote(symbol)}&interval=1h&limit=24"
        candles = http_get_json(url, timeout=self.config.http_timeout_seconds)
        closes: List[float] = []
        for candle in candles:
            try:
                closes.append(float(candle[4]))
            except (TypeError, ValueError, IndexError):
                continue
        return closes

    def _synthetic_history(self, price: float, change_24h: float) -> List[float]:
        steps = 10
        if change_24h == 0:
            start = price
        else:
            start = price / (1 + change_24h / 100.0)
        return [round(start + (price - start) * (i / (steps - 1)), 8) for i in range(steps)]

    def _universe(self) -> List[Coin]:
        if self.config.live_market_data:
            with suppress(Exception):
                return self._live_universe()
        return self.universe

    def top_gainers(self, limit: int = 3) -> List[Dict[str, Any]]:
        universe = self._universe()
        return [c.as_dict() for c in sorted(universe, key=lambda c: c.change_24h, reverse=True)[:limit]]

    def top_losers(self, limit: int = 3) -> List[Dict[str, Any]]:
        universe = self._universe()
        return [c.as_dict() for c in sorted(universe, key=lambda c: c.change_24h)[:limit]]

    def volume_spikes(self, threshold: float = 1.75) -> List[Dict[str, Any]]:
        universe = self._universe()
        return [c.as_dict() for c in universe if c.volume_ratio >= threshold]


# =========================
# RESEARCH ENGINE
# =========================


class ResearchEngine:
    def analyze(self, coin: Dict[str, Any]) -> Dict[str, str]:
        change = float(coin.get("change_24h", 0))
        volume_ratio = float(coin.get("volume_ratio", 1))
        market_cap = float(coin.get("market_cap", 0))
        price = float(coin.get("price", 0))

        reason = (
            f"{coin.get('symbol')} is trending with {change:.1f}% 24h move "
            f"and {volume_ratio:.1f}x volume versus baseline."
        )

        if change >= 8:
            bull_case = "Strong momentum and aggressive participation suggest continuation if volume holds."
        elif change >= 0:
            bull_case = "Price is advancing with constructive flow; continuation is possible above the recent range."
        else:
            bull_case = "Oversold conditions can attract a bounce if sellers exhaust."

        if market_cap > 1e11:
            bear_case = "Large caps can still reverse quickly; upside may be slower and more range-bound."
        elif change < 0:
            bear_case = "Downtrend risk remains elevated until price reclaims prior resistance."
        else:
            bear_case = "Low conviction could fade if volume drops or broader market weakens."

        if price < 1:
            risk = "Penny-like pricing can create outsized percentage swings and wider slippage."
        elif volume_ratio < 1.2:
            risk = "Volume is not strong enough to confirm the move."
        else:
            risk = "Use a defined stop because momentum names can retrace sharply."

        return {
            "reason": reason,
            "bull_case": bull_case,
            "bear_case": bear_case,
            "risk": risk,
        }

    def score(self, coin: Dict[str, Any]) -> float:
        change = float(coin.get("change_24h", 0))
        volume_ratio = float(coin.get("volume_ratio", 1))
        market_cap = float(coin.get("market_cap", 0))
        momentum = max(-10.0, min(10.0, change))
        liquidity = min(10.0, volume_ratio * 3.0)
        cap_penalty = -2.0 if market_cap <= 0 else 0.0
        return momentum + liquidity + cap_penalty


# =========================
# TRADE SETUP ENGINE
# =========================


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


# =========================
# EMOTION ENGINE
# =========================


class EmotionEngine:
    @staticmethod
    def get_tone(coin: Dict[str, Any]) -> Dict[str, Any]:
        change = float(coin.get("change_24h", 0))
        vol = float(coin.get("volume_ratio", 1))

        if change > 5 and vol > 1.5:
            return {
                "persona": "FOMO Bull (پرجوش خریدار)",
                "hook_emoji": "🚀💥",
                "bull_emoji": "📈💎",
                "bear_emoji": "⚠️🧊",
                "risk_emoji": "🛑💀",
                "twist": "یہاں جوش ہے مگر خبردار! زیادہ لالچ نقصان دہ ہو سکتا ہے۔",
            }
        elif change < -3:
            return {
                "persona": "Panic Bear (خوفزدہ بیچنے والا)",
                "hook_emoji": "📉😨",
                "bull_emoji": "🕊️🍀",
                "bear_emoji": "🐻🔪",
                "risk_emoji": "🚨🩸",
                "twist": "خون بہہ رہا ہے، لیکن عقلمند لوگ خوف میں خریدتے ہیں۔ کیا آپ تیار ہیں؟",
            }
        else:
            return {
                "persona": "Cold Analyst (ٹھنڈا تجزیہ کار)",
                "hook_emoji": "🧐📊",
                "bull_emoji": "📈📐",
                "bear_emoji": "📉📐",
                "risk_emoji": "⚖️🛡️",
                "twist": "جذبات کو ایک طرف رکھو، صرف ڈیٹا بول رہا ہے۔",
            }


# =========================
# GEMINI GENERATOR
# =========================


class GeminiGenerator:
    def __init__(self, config: Config = CONFIG):
        self.config = config
        self.emotion = EmotionEngine()

    def _build_prompt(
        self,
        analysis: Dict[str, str],
        setup: Dict[str, str],
        coin: Dict[str, Any],
        memory_summary: Optional[Dict[str, Any]] = None,
        past_examples: Optional[List[str]] = None,
        tone: Optional[Dict[str, Any]] = None,
        keywords: Optional[List[str]] = None,
        chart_path: Optional[str] = None,
    ) -> str:
        symbol = coin.get("symbol", "COIN")
        name = coin.get("name", symbol)
        keyword_block = ", ".join(keywords) if keywords else "none"
        examples_text = "\n---\n".join(past_examples or []) if past_examples else "کوئی پچھلی مثال دستیاب نہیں، لیکن آپ ایک ماہر ہیں۔"
        tone = tone or self.emotion.get_tone(coin)
        memory_keywords = ", ".join([word for word, _ in (memory_summary or {}).get("top_keywords", [])[:8]]) or "none"
        memory_hashtags = ", ".join([tag for tag, _ in (memory_summary or {}).get("top_hashtags", [])[:5]]) or "none"
        return textwrap.dedent(
            f
            """
            آپ 20 سال کا تجربہ رکھنے والے وال اسٹریٹ کے Veteran ٹریڈر ہیں۔
            آپ کا موجودہ موڈ: {tone['persona']}

            **ماضی میں آپ کی وائرل ہونے والی پوسٹس کا انداز (ان سے سیکھیں اور بہتر بنائیں):**
            {examples_text}

            **اب موجودہ کرنسی {symbol} کے لیے بالکل
