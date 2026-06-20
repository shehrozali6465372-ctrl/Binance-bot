import json
import os
import random
import logging
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


    def _coingecko_universe(self) -> List[Coin]:
        """Fallback to CoinGecko when Binance is blocked."""
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=volume_desc&per_page=15&sparkline=true&price_change_percentage=24h"
        try:
            payload = http_get_json(url, timeout=self.config.http_timeout_seconds)
        except Exception:
            return self._build_universe()

        coins: List[Coin] = []
        for item in payload:
            try:
                symbol = (item.get("symbol") or "").upper()
                name = item.get("name") or symbol
                price = float(item.get("current_price") or 0)
                change_24h = float(item.get("price_change_percentage_24h") or 0)
                volume_24h = float(item.get("total_volume") or 0)
                market_cap = float(item.get("market_cap") or 0)
                volume_ratio = min(max(0.5, volume_24h / max(market_cap, 1) * 100), 10.0)
                sparkline = item.get("sparkline_in_7d", {}).get("price", [])
                history = [float(p) for p in sparkline[-10:]] if sparkline else self._synthetic_history(price, change_24h)
            except (TypeError, ValueError, KeyError):
                continue
            coins.append(Coin(symbol, name, price, change_24h, volume_24h, volume_ratio, market_cap, history))

        return coins or self._build_universe()

    _universe_cache = None

    def _universe(self) -> List[Coin]:
        if MarketScanner._universe_cache is not None:
            return MarketScanner._universe_cache
        if self.config.live_market_data:
            with suppress(Exception):
                coins = self._coingecko_universe()
                MarketScanner._universe_cache = coins
                return coins
        MarketScanner._universe_cache = self.universe
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
                "hook_emoji": "Ã°Å¸Å¡â‚¬Ã°Å¸â€™Â¥",
                "bull_emoji": "Ã°Å¸â€œË†Ã°Å¸â€™Å½",
                "bear_emoji": "Ã¢Å¡ Ã¯Â¸ÂÃ°Å¸Â§Å ",
                "risk_emoji": "Ã°Å¸â€ºâ€˜Ã°Å¸â€™â‚¬",
                "twist": "Excitement is high, but be careful! Greed can be dangerous.",
            }
        elif change < -3:
            return {
                "persona": "Panic Bear",
                "hook_emoji": "Ã°Å¸â€œâ€°Ã°Å¸ËœÂ¨",
                "bull_emoji": "Ã°Å¸â€¢Å Ã¯Â¸ÂÃ°Å¸Ââ‚¬",
                "bear_emoji": "Ã°Å¸ÂÂ»Ã°Å¸â€Âª",
                "risk_emoji": "Ã°Å¸Å¡Â¨Ã°Å¸Â©Â¸",
                "twist": "Blood is in the water, but smart people buy fear. Are you ready?",
            }
        else:
            return {
                "persona": "Cold Analyst",
                "hook_emoji": "Ã°Å¸Â§ÂÃ°Å¸â€œÅ ",
                "bull_emoji": "Ã°Å¸â€œË†Ã°Å¸â€œÂ",
                "bear_emoji": "Ã°Å¸â€œâ€°Ã°Å¸â€œÂ",
                "risk_emoji": "Ã¢Å¡â€“Ã¯Â¸ÂÃ°Å¸â€ºÂ¡Ã¯Â¸Â",
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
        )

        if not self.config.gemini_api_key:
            LOGGER.warning("No GEMINI_API_KEY set; using template-based content")
            return self._template_content(analysis, setup, coin, tone, keywords)

        models_to_try = [
            self.config.gemini_model,
        ]
        # Deduplicate
        seen_models = set()
        models = []
        for m in models_to_try:
            if m not in seen_models:
                seen_models.add(m)
                models.append(m)

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
                resp = http_post_json(url, payload, timeout=self.config.http_timeout_seconds, retries=5)
                text = resp["candidates"][0]["content"]["parts"][0]["text"]
                if text and text.strip():
                    return text.strip()
            except Exception as exc:
                LOGGER.warning("Gemini model %s failed: %s", model, exc)
                continue

        LOGGER.warning("All Gemini models failed; falling back to template-based content")
        return self._template_content(analysis, setup, coin, tone, keywords)

    def _build_prompt(
        self,
        analysis: Dict[str, str],
        setup: Dict[str, str],
        coin: Dict[str, Any],
        memory_summary: Optional[Dict[str, Any]] = None,
        past_examples: Optional[List[str]] = None,
        tone: Optional[Dict[str, Any]] = None,
        keywords: Optional[List[str]] = None,
    ) -> str:
        symbol = coin.get("symbol", "COIN")
        keyword_block = ", ".join(keywords) if keywords else "none"
        examples_text = "\n---\n".join(past_examples or []) if past_examples else "No past examples available, but you are an expert."
        tone = tone or self.emotion.get_tone(coin)
        memory_keywords = ", ".join([word for word, _ in (memory_summary or {}).get("top_keywords", [])[:8]]) or "none"
        memory_hashtags = ", ".join([tag for tag, _ in (memory_summary or {}).get("top_hashtags", [])[:5]]) or "none"

        lines = [
            "You are a 20-year veteran Wall Street trader.",
            f"Your current mood: {tone['persona']}",
            "",
            "**Learn from your past viral posts and improve:**",
            f"{examples_text}",
            "",
            f"**Now write for {symbol} in the same human style, with emojis and depth.**",
            "Market Data:",
            f"- 24h Change: {coin.get('change_24h', 0):.2f}%",
            f"- Volume: {coin.get('volume_ratio', 1):.1f}x",
            f"- Analysis: {analysis['reason']}",
            f"- Bull Case: {analysis['bull_case']}",
            f"- Bear Case: {analysis['bear_case']}",
            f"- Risk: {analysis['risk']}",
            f"- Entry: {setup['entry']}",
            f"- Target 1: {setup['target1']}",
            f"- Target 2: {setup['target2']}",
            f"- Stop: {setup['stop']}",
            f"- Keywords: {keyword_block}",
        ]

        prompt = "\n".join(lines)
        return prompt

    def _template_content(self, analysis, setup, coin, tone=None, keywords=None) -> str:
        """Generate content using a template when Gemini API is unavailable."""
        symbol = coin.get("symbol", "COIN")
        name = coin.get("name", symbol)
        price = coin.get("price", 0)
        change = coin.get("change_24h", 0)
        vol_ratio = coin.get("volume_ratio", 1)
        emotion = tone or self.emotion.get_tone(coin)
        
        lines = [
            f"{emotion['hook_emoji']} {symbol} Update: {change:.1f}% in 24h!",
            "",
            f"${symbol} is currently trading at ${price:.4f} with a {change:+.1f}% change in the last 24 hours.",
            f"Volume is {vol_ratio:.1f}x the baseline, showing {'strong' if vol_ratio > 1.5 else 'moderate'} participation.",
            "",
            f"{emotion['bull_emoji']} **Bull Case:** {analysis.get('bull_case', 'Momentum is building.')}",
            f"{emotion['bear_emoji']} **Bear Case:** {analysis.get('bear_case', 'Stay cautious.')}",
            f"{emotion['risk_emoji']} **Risk:** {analysis.get('risk', 'Use proper risk management.')}",
            "",
            f"**Setup:**",
            f"  Entry: ${setup.get('entry', 'N/A')}",
            f"  Target 1: ${setup.get('target1', 'N/A')}",
            f"  Target 2: ${setup.get('target2', 'N/A')}",
            f"  Stop: ${setup.get('stop', 'N/A')}",
            "",
            f"{emotion['twist']}",
            "",
            f"#crypto #{symbol} #trading #altcoin #defi"
        ]
        return "\n".join(lines)


class PostPublisher:
    def __init__(self, config: Config = CONFIG):
        self.config = config
        self.db = Database(config.database_path)

    def publish(self, coin: Dict[str, Any], content: str) -> bool:
        if self.config.dry_run:
            LOGGER.info("[DRY-RUN] Would publish post for %s", coin.get("symbol"))
            self._save_locally(coin, content)
            return True

        published = self._try_square_api(coin, content)
        if not published:
            self._save_locally(coin, content)
        return True

    def _try_square_api(self, coin: Dict[str, Any], content: str) -> bool:
        """Publish to Binance Square via official Creator Center API."""
        square_key = self.config.square_api_key
        if not square_key:
            LOGGER.warning("No SQUARE_API_KEY set, saving locally")
            return False

        # Format content with symbol hashtags
        symbol = coin.get("symbol", "")
        body_text = content
        # Add symbol hashtag if not already present
        if symbol and f"#{symbol}" not in content:
            body_text = content + f"\n\n#{symbol}"

        payload = {
            "contentType": 1,
            "bodyTextOnly": body_text,
        }
        headers = {
            "X-Square-OpenAPI-Key": square_key,
            "Content-Type": "application/json",
            "clienttype": "binanceSkill",
        }

        url = "https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add"

        try:
            import requests as req_lib
            resp = req_lib.post(url, headers=headers, json=payload, timeout=self.config.http_timeout_seconds)
            LOGGER.info("Square API response: HTTP %d %s", resp.status_code, resp.text[:300])

            if resp.status_code != 200:
                LOGGER.warning("Square API returned HTTP %d", resp.status_code)
                return False

            data = resp.json()
            if data.get("code") == "000000":
                post_id = data.get("data", {}).get("id", "unknown")
                share_link = data.get("data", {}).get("shareLink", "")
                LOGGER.info("✅ Published to Square! ID: %s Link: %s", post_id, share_link)
                return True
            else:
                LOGGER.warning("Square API error [%s]: %s", data.get("code"), data.get("message"))
                return False
        except Exception as exc:
            LOGGER.warning("Square API request failed: %s", exc)
            return False

    def _save_locally(self, coin: Dict[str, Any], content: str) -> None:
        """Save post to local file when remote publish fails."""
        symbol = coin.get("symbol", "UNKNOWN")
        posts_dir = Path("posts")
        posts_dir.mkdir(parents=True, exist_ok=True)
        filename = f"post_{symbol}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"
        path = posts_dir / filename
        try:
            path.write_text(content)
            LOGGER.info("Saved post locally: %s", path)
        except Exception as e:
            LOGGER.error("Could not save locally: %s", e)


def main() -> None:
    config = CONFIG
    config.validate()

    scanner = MarketScanner(config)
    research = ResearchEngine()
    trade_setup = TradeSetup()
    generator = GeminiGenerator(config)
    publisher = PostPublisher(config)

    top_gainers = scanner.top_gainers(limit=3)
    top_losers = scanner.top_losers(limit=3)
    volume_spikes = scanner.volume_spikes(threshold=1.75)

    all_candidates = top_gainers + top_losers + volume_spikes

    seen = set()
    unique_candidates = []
    for coin in all_candidates:
        sym = coin.get("symbol")
        price = float(coin.get("price", 0) or 0)
        change = float(coin.get("change_24h", 0) or 0)
        # Skip coins with no price or extreme values
        if price <= 0:
            continue
        if abs(change) > 200:
            continue
        if sym in seen:
            continue
        seen.add(sym)
        unique_candidates.append(coin)

    scored = [(research.score(coin), coin) for coin in unique_candidates]
    scored.sort(key=lambda x: x[0], reverse=True)

    top_pick = scored[0][1] if scored else None
    if top_pick is None:
        LOGGER.info("No candidates found. Exiting.")
        return

    analysis = research.analyze(top_pick)
    setup = trade_setup.build(top_pick)

    LOGGER.info("Generating post for %s...", top_pick.get("symbol"))
    content = generator.generate(analysis=analysis, setup=setup, coin=top_pick)

    publisher.publish(top_pick, content)
    LOGGER.info("✅ Done - post generated for %s", top_pick.get("symbol"))


if __name__ == "__main__":
    main()
                    
