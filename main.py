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
            self.conn.execute("""CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, coin_symbol TEXT, content TEXT NOT NULL, metadata TEXT)""")
            self.conn.execute("""CREATE TABLE IF NOT EXISTS metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, created_at TEXT NOT NULL, views INTEGER NOT NULL, traders INTEGER NOT NULL, FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE SET NULL)""")
            self.conn.execute("""CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, status TEXT NOT NULL, summary TEXT)""")
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
            cur = self.conn.execute("INSERT INTO posts (created_at, coin_symbol, content, metadata) VALUES (?, ?, ?, ?)", (utc_now(), coin_symbol, content, json.dumps(metadata, default=str)))
        return int(cur.lastrowid)

    def save_metrics(self, views: int, traders: int, post_id: Optional[int] = None) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO metrics (post_id, created_at, views, traders) VALUES (?, ?, ?, ?)", (post_id, utc_now(), int(views), int(traders)))

    def recent_posts(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.conn.execute("SELECT created_at, coin_symbol, content, metadata FROM posts ORDER BY id DESC LIMIT ?", (limit,))
        rows = []
        for row in cur.fetchall():
            rows.append({"created_at": row["created_at"], "coin_symbol": row["coin_symbol"], "content": row["content"], "metadata": json.loads(row["metadata"] or "{}")})
        return rows

    def save_run(self, status: str, summary: Dict[str, Any]) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO runs (created_at, status, summary) VALUES (?, ?, ?)", (utc_now(), status, json.dumps(summary, default=str)))

    def get_top_performers(self, limit: int = 2) -> List[str]:
        try:
            cur = self.conn.execute("""SELECT p.content FROM posts p JOIN metrics m ON m.post_id = p.id ORDER BY (COALESCE(m.views, 0) + COALESCE(m.traders, 0) * 5) DESC LIMIT ?""", (limit,))
            return [row["content"] for row in cur.fetchall()]
        except sqlite3.OperationalError:
            return []


class MarketScanner:
    def __init__(self, config: Config = CONFIG):
        self.config = config
        self.universe = self._build_universe()

    def _build_universe(self) -> List[Coin]:
        return [
            Coin("SOL", "Solana", 168.42, 11.2, 3.4e9, 2.7, 7.4e10, [154,158,161,165,168]),
            Coin("LINK", "Chainlink", 21.11, 8.7, 1.1e9, 2.1, 1.3e10, [19.1,19.8,20.2,20.6,21.1]),
            Coin("AAVE", "Aave", 112.55, 7.9, 5.2e8, 1.9, 1.7e9, [105,107,109,111,112]),
            Coin("DOGE", "Dogecoin", 0.184, 5.4, 2.8e9, 1.8, 2.7e10, [0.173,0.176,0.179,0.181,0.184]),
            Coin("ETH", "Ethereum", 3472.15, 3.1, 1.5e10, 1.3, 4.2e11, [3390,3410,3432,3451,3472]),
            Coin("BTC", "Bitcoin", 68241.0, 1.4, 2.4e10, 1.1, 1.3e12, [67120,67500,67980,68110,68241]),
            Coin("MKR", "Sky", 3892.2, -2.4, 2.1e8, 0.8, 3.4e9, [3990,3960,3925,3902,3892]),
            Coin("OP", "Optimism", 2.62, -4.8, 7.8e8, 1.4, 2.3e9, [2.79,2.74,2.69,2.65,2.62]),
            Coin("ARB", "Arbitrum", 0.79, -6.2, 9.2e8, 1.6, 3.1e9, [0.86,0.84,0.82,0.80,0.79]),
        ]

    def _live_universe(self) -> List[Coin]:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        payload = http_get_json(url, timeout=self.config.http_timeout_seconds)
        coins = []
        ranked = sorted([item for item in payload if str(item.get("symbol","")).endswith("USDT")], key=lambda i: float(i.get("quoteVolume",0) or 0), reverse=True)[:12]
        for item in ranked:
            symbol = item.get("symbol","")
            base = symbol[:-4]
            try:
                price = float(item.get("lastPrice",0))
                ch = float(item.get("priceChangePercent",0))
                vol = float(item.get("quoteVolume",0))
                vr = max(1.0, float(item.get("count",0))/1000.0)
                mc = max(vol*10, price*1e6)
                hist = self._live_history(symbol) or self._synthetic_history(price, ch)
                coins.append(Coin(base, base, price, ch, vol, vr, mc, hist))
            except:
                continue
        return coins or self._build_universe()

    def _live_history(self, symbol: str) -> List[float]:
        url = f"https://api.binance.com/api/v3/klines?symbol={urllib.parse.quote(symbol)}&interval=1h&limit=24"
        candles = http_get_json(url, timeout=self.config.http_timeout_seconds)
        return [float(c[4]) for c in candles if len(c)>4]

    def _synthetic_history(self, price: float, change_24h: float) -> List[float]:
        steps = 10
        start = price if change_24h==0 else price/(1+change_24h/100.0)
        return [round(start+(price-start)*(i/(steps-1)),8) for i in range(steps)]

    def _universe(self) -> List[Coin]:
        if self.config.live_market_data:
            with suppress(Exception):
                return self._live_universe()
        return self.universe

    def top_gainers(self, limit=3) -> List[Dict[str,Any]]:
        return [c.as_dict() for c in sorted(self._universe(), key=lambda c: c.change_24h, reverse=True)[:limit]]

    def top_losers(self, limit=3) -> List[Dict[str,Any]]:
        return [c.as_dict() for c in sorted(self._universe(), key=lambda c: c.change_24h)[:limit]]

    def volume_spikes(self, threshold=1.75) -> List[Dict[str,Any]]:
        return [c.as_dict() for c in self._universe() if c.volume_ratio >= threshold]


class ResearchEngine:
    def analyze(self, coin: Dict[str,Any]) -> Dict[str,str]:
        ch = float(coin.get("change_24h",0))
        vr = float(coin.get("volume_ratio",1))
        mc = float(coin.get("market_cap",0))
        pr = float(coin.get("price",0))
        reason = f"{coin.get('symbol')} is trending with {ch:.1f}% 24h move and {vr:.1f}x volume."
        if ch>=8: bull = "Strong momentum, continuation likely if volume holds."
        elif ch>=0: bull = "Constructive flow, possible continuation above range."
        else: bull = "Oversold bounce possible if sellers exhaust."
        if mc>1e11: bear = "Large cap can reverse, upside slower."
        elif ch<0: bear = "Downtrend risk until reclaim resistance."
        else: bear = "Low conviction may fade if volume drops."
        if pr<1: risk = "Penny-like pricing, wide slippage."
        elif vr<1.2: risk = "Volume not strong enough."
        else: risk = "Use defined stop, momentum can retrace."
        return {"reason":reason,"bull_case":bull,"bear_case":bear,"risk":risk}

    def score(self, coin: Dict[str,Any]) -> float:
        ch = float(coin.get("change_24h",0))
        vr = float(coin.get("volume_ratio",1))
        mc = float(coin.get("market_cap",0))
        return max(-10,min(10,ch)) + min(10,vr*3) + (-2 if mc<=0 else 0)


class TradeSetup:
    def build(self, coin: Dict[str,Any]) -> Dict[str,str]:
        p = float(coin.get("price",0))
        return {
            "entry": f"{p*1.002:.6f}".rstrip("0").rstrip("."),
            "target1": f"{p*1.08:.6f}".rstrip("0").rstrip("."),
            "target2": f"{p*1.16:.6f}".rstrip("0").rstrip("."),
            "stop": f"{p*0.94:.6f}".rstrip("0").rstrip("."),
        }


class EmotionEngine:
    @staticmethod
    def get_tone(coin: Dict[str,Any]) -> Dict[str,Any]:
        ch = float(coin.get("change_24h",0))
        vol = float(coin.get("volume_ratio",1))
        if ch>5 and vol>1.5:
            return {"persona":"FOMO Bull","hook_emoji":"🚀💥","bull_emoji":"📈💎","bear_emoji":"⚠️🧊","risk_emoji":"🛑💀","twist":"Excitement high, but greed is dangerous!"}
        elif ch<-3:
            return {"persona":"Panic Bear","hook_emoji":"📉😨","bull_emoji":"🕊️🍀","bear_emoji":"🐻🔪","risk_emoji":"🚨🩸","twist":"Blood in water, smart people buy fear."}
        else:
            return {"persona":"Cold Analyst","hook_emoji":"🧐📊","bull_emoji":"📈📐","bear_emoji":"📉📐","risk_emoji":"⚖️🛡️","twist":"Leave emotions, only data speaks."}


class GeminiGenerator:
    def __init__(self, config: Config = CONFIG):
        self.config = config
        self.emotion = EmotionEngine()

    def _build_prompt(self, analysis, setup, coin, memory_summary=None, past_examples=None, tone=None, keywords=None, chart_path=None) -> str:
        symbol = coin.get("symbol","COIN")
        tone = tone or self.emotion.get_tone(coin)
        keyword_block = ", ".join(keywords) if keywords else "none"
        examples_text = "\n---\n".join(past_examples or []) if past_examples else "No past examples, you are an expert."
        mk = ", ".join([w for w,_ in (memory_summary or {}).get("top_keywords",[])][:8]) or "none"
        mh = ", ".join([t for t,_ in (memory_summary or {}).get("top_hashtags",[])][:5]) or "none"
        lines = [
            "You are a veteran trader.",
            f"Mood: {tone['persona']}",
            f"Learn from past: {examples_text}",
            f"Write for {symbol} with emojis and depth.",
            f"24h Change: {coin.get('change_24h',0):.2f}%",
            f"Volume: {coin.get('volume_ratio',1):.1f}x",
            f"Analysis: {analysis['reason']}",
            f"Bull: {analysis['bull_case']}",
            f"Bear: {analysis['bear_case']}",
            f"Risk: {analysis['risk']}",
            f"Entry: {setup['entry']}",
            f"Target 1: {setup['target1']}",
            f"Target 2: {setup['target2']}",
            f"Stop: {setup['stop']}",
            f"Keywords: {keyword_block}",
            f"Memory Keywords: {mk}",
            f"Memory Hashtags: {mh}",
            "Add 3+ hashtags.",
            f"1. Hook with {tone['hook_emoji']}.",
            "2. Use 5+ emojis.",
            "3. Counter-trade suggestion.",
            f"4. Fear/greed: {tone['twist']}",
            "5. Emotional question at end.",
            f"💰 Entry: {setup['entry']}",
            f"🎯 Target 1: {setup['target1']}",
            f"🎯 Target 2: {setup['target2']}",
            f"🛑 Stop: {setup['stop']}",
        ]
        return "\n".join(lines)

    def generate(self, analysis, setup, coin, memory_summary=None, keywords=None, chart_path=None) -> Optional[str]:
        if not self.config.gemini_api_key:
            return self._fallback_template(analysis, setup, coin, self.emotion.get_tone(coin), keywords, chart_path)
        db = Database(self.config.database_path)
        try:
            past_examples = db.get_top_performers(2)
        finally:
            db.close()
        tone = self.emotion.get_tone(coin)
        model = urllib.parse.quote(self.config.gemini_model, safe="")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        prompt = self._build_prompt(analysis, setup, coin, memory_summary, past_examples, tone, keywords, chart_path)
        payload = {"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":self.config.gemini_temperature,"topP":self.config.gemini_top_p,"maxOutputTokens":self.config.gemini_max_output_tokens}}
        for attempt in range(3):
            try:
                resp = http_post_json(url, payload, timeout=self.config.http_timeout_seconds, headers={"x-goog-api-key": self.config.gemini_api_key})
                candidates = resp.get("candidates",[])
                for cand in candidates:
                    parts = (cand.get("content") or {}).get("parts",[])
                    text = "".join(p.get("text","") for p in parts if isinstance(p,dict)).strip()
                    if text:
                        text = self._inject_emojis(text, tone)
                        text = self._inject_hashtags(text, coin, keywords or [], tone)
                        return text
                LOGGER.warning("Gemini invalid response, retry %s/3", attempt+1)
            except Exception as e:
                LOGGER.warning("Gemini fail %s/3: %s", attempt+1, e)
            if attempt<2:
                time.sleep(min(2**attempt,4))
        return self._fallback_template(analysis, setup, coin, tone, keywords, chart_path)

    def _inject_emojis(self, text: str, tone: Dict[str,Any]) -> str:
        if "🚀" not in text: text = f"{tone['hook_emoji']} {text}"
        return text

    def _inject_hashtags(self, text, coin, keywords, tone) -> str:
        symbol = coin.get("symbol","COIN").upper()
        tags = [f"${symbol}", f"#{symbol}", "#Crypto"]
        return text.rstrip() + "\n\n" + " ".join(tags)

    def _fallback_template(self, analysis, setup, coin, tone, keywords=None, chart_path=None) -> str:
        symbol = coin.get("symbol","COIN")
        return f"{tone['hook_emoji']} {symbol} | Entry: {setup['entry']} | T1: {setup['target1']} | T2: {setup['target2']} | Stop: {setup['stop']} | {analysis['reason']}\n${symbol} #{symbol} #Crypto"
class ChartGenerator:
    def create(self, coin: Dict[str,Any]) -> str:
        symbol = coin.get("symbol","COIN")
        history = coin.get("history") or [0,0]
        chart_dir = Path("charts")
        chart_dir.mkdir(parents=True, exist_ok=True)
        path = chart_dir / f"{symbol.lower()}_{int(time.time())}.svg"
        w, h, m = 640, 320, 28
        mn, mx = min(history), max(history)
        if mn==mx: mn-=1; mx+=1
        def sx(i): return m + i*((w-2*m)/max(len(history)-1,1))
        def sy(p): return h - m - ((p-mn)/max(mx-mn,1e-9))*(h-2*m)
        pts = " ".join(f"{sx(i):.1f},{sy(p):.1f}" for i,p in enumerate(history))
        circ = "\n".join(f'<circle cx="{sx(i):.1f}" cy="{sy(p):.1f}" r="3" fill="#7dd3fc"/>' for i,p in enumerate(history))
        payload = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><rect width="100%" height="100%" rx="18" fill="#0f172a"/><text x="{m}" y="18" fill="#94a3b8" font-size="14">{symbol}</text><polyline fill="none" stroke="#38bdf8" stroke-width="3" points="{pts}"/>{circ}</svg>
"""
        path.write_text(payload, encoding="utf-8")
        return str(path)
