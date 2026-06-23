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


def _fix_workflow_file() -> None:
    """Fix invisible Unicode chars in workflow file if running in GHA."""
    if not os.getenv("GITHUB_ACTIONS"):
        return
    wf_path = ".github/workflows/run_bot.yml"
    if not os.path.exists(wf_path):
        return
    with open(wf_path, "rb") as f:
        raw = f.read()
    # Check for U+200E (LEFT-TO-RIGHT MARK) - e2 80 8e in UTF-8
    if b"\xe2\x80\x8e" not in raw:
        return  # File is clean
    LOGGER.info("Fixing workflow file (removing invisible Unicode chars)")
    clean = raw.replace(b"\xe2\x80\x8e", b"")
    with open(wf_path, "wb") as f:
        f.write(clean)
    try:
        import subprocess
        subprocess.run(["git", "config", "user.name", "bot"], capture_output=True)
        subprocess.run(["git", "config", "user.email", "bot@bot.com"], capture_output=True)
        r = subprocess.run(["git", "add", wf_path, "&&", "git", "commit", "-m", "fix workflow file", "&&", "git", "push"], 
                         capture_output=True, text=True, timeout=30, shell=True)
        if r.returncode == 0:
            LOGGER.info("Workflow file fixed and pushed!")
        else:
            LOGGER.warning("Could not push fix: %s", r.stderr[:200])
    except Exception as e:
        LOGGER.warning("Could not fix workflow: %s", e)



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
                sleep_for = min(15 * (2 ** attempt) + random.uniform(0, 10), 90)
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
        _fix_workflow_file()
        self.path = path
        ensure_parent(self.path)
        # Try to restore database from previous GitHub Actions artifact
        if not os.path.exists(self.path) or os.path.getsize(self.path) < 100:
            self._restore_from_artifact()
        self.conn = sqlite3.connect(self.path, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _restore_from_artifact(self) -> None:
        """Download agent.db from the latest workflow artifact using GitHub API."""
        if not os.getenv("GITHUB_ACTIONS"):
            return
        runtime_token = os.getenv("ACTIONS_RUNTIME_TOKEN", "")
        gh_token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN", "")
        repo = os.getenv("GITHUB_REPOSITORY", "")
        api_token = gh_token or runtime_token
        if not api_token or not repo:
            LOGGER.info("No API token available for artifact restore (GITHUB_TOKEN not set in env)")
            return
        try:
            import urllib.request, zipfile, io, json as _json
            runs_url = f"https://api.github.com/repos/{repo}/actions/runs?status=success&per_page=5"
            req = urllib.request.Request(runs_url, headers={
                "Authorization": f"Bearer {api_token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "binance-bot"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                runs_data = _json.loads(resp.read().decode("utf-8"))
            LOGGER.info("Found %d workflow runs via API", len(runs_data.get("workflow_runs", [])))
            for run in runs_data.get("workflow_runs", []):
                run_id = run.get("id")
                event = run.get("event", "")
                if event not in ("workflow_dispatch", "schedule"):
                    continue
                art_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/artifacts"
                req2 = urllib.request.Request(art_url, headers={
                    "Authorization": f"Bearer {api_token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "binance-bot"
                })
                with urllib.request.urlopen(req2, timeout=15) as resp2:
                    art_data = _json.loads(resp2.read().decode("utf-8"))
                for artifact in art_data.get("artifacts", []):
                    if "agent-output" in artifact.get("name", ""):
                        dl_url = artifact.get("archive_download_url", "")
                        if not dl_url:
                            continue
                        req3 = urllib.request.Request(dl_url, headers={
                            "Authorization": f"Bearer {api_token}",
                            "User-Agent": "binance-bot"
                        })
                        with urllib.request.urlopen(req3, timeout=30) as resp3:
                            zip_data = io.BytesIO(resp3.read())
                            with zipfile.ZipFile(zip_data) as zf:
                                for name in zf.namelist():
                                    if name == "agent.db":
                                        db_bytes = zf.read(name)
                                        if len(db_bytes) > 100:
                                            with open(self.path, "wb") as f_out:
                                                f_out.write(db_bytes)
                                            LOGGER.info("Restored agent.db from run %s (%d bytes)", run_id, len(db_bytes))
                                            return
            LOGGER.info("No valid agent.db found in recent artifacts")
        except urllib.error.HTTPError as exc:
            LOGGER.info("Artifact API error: HTTP %d %s", exc.code, exc.reason)
        except Exception as exc:
            LOGGER.info("Artifact restore failed: %s", exc)
    def _count_posts_db(self, db_path: str) -> int:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = conn.execute("SELECT COUNT(*) FROM posts")
            count = cur.fetchone()[0]
            conn.close()
            return count
        except:
            return 0

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
            if posted and hours > 0:
                # Only keep symbols posted within the time window
                from datetime import datetime, timezone, timedelta
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                recent = set()
                cur2 = self.conn.execute(
                    "SELECT DISTINCT coin_symbol FROM posts WHERE created_at >= ?",
                    (cutoff.isoformat(),)
                )
                for row2 in cur2.fetchall():
                    if row2["coin_symbol"]:
                        recent.add(row2["coin_symbol"].upper())
                return recent
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

class PostedSymbolsTracker:
    """Track posted symbols across GHA runs using a JSON file committed to repo."""
    FILE_NAME = "posted_symbols.json"
    
    def __init__(self):
        self.file_path = Path(self.FILE_NAME)
        self.data = self._load()
    
    def _load(self) -> Dict[str, str]:
        """Load posted symbols with timestamps."""
        if self.file_path.exists():
            try:
                return json.loads(self.file_path.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}
    
    def save(self) -> None:
        """Save to file and commit+push if in GHA."""
        try:
            self.file_path.write_text(json.dumps(self.data, indent=2))
        except OSError as e:
            LOGGER.warning("Could not save posted symbols: %s", e)
            return
        # Commit and push if running in GitHub Actions
        if os.getenv("GITHUB_ACTIONS"):
            import subprocess
            try:
                subprocess.run(["git", "add", self.FILE_NAME],
                             capture_output=True, timeout=10)
                r = subprocess.run(["git", "diff", "--cached", "--quiet", self.FILE_NAME],
                                 capture_output=True, timeout=10)
                if r.returncode != 0:
                    subprocess.run(["git", "commit", "-m", f"update {self.FILE_NAME} [skip ci]"],
                                 capture_output=True, timeout=10,
                                 env={**os.environ, "GIT_AUTHOR_NAME": "bot", "GIT_AUTHOR_EMAIL": "bot@bot.com"})
                    push = subprocess.run(["git", "push"],
                                        capture_output=True, timeout=30)
                    if push.returncode == 0:
                        LOGGER.info("Pushed posted_symbols.json to repo")
                    else:
                        stderr = push.stderr.decode()[:200] if isinstance(push.stderr, bytes) else str(push.stderr)[:200]
                        LOGGER.warning("Could not push: %s", stderr)
            except Exception as e:
                LOGGER.warning("Git commit/push failed: %s", e)
    
    def mark_posted(self, symbol: str) -> None:
        """Mark a symbol as posted with current timestamp."""
        self.data[symbol.upper()] = utc_now()
        self.save()
    
    def get_posted_symbols(self, hours: int = 48) -> set:
        """Get symbols posted within the given hours."""
        if hours <= 0:
            return set()
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent = set()
        for sym, ts_str in self.data.items():
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts >= cutoff:
                    recent.add(sym)
            except (ValueError, TypeError):
                recent.add(sym)
        return recent

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
    """Fetch real Binance announcements - airdrops and delistings."""
    
    CATALOGS = {
        "airdrops": 128,
        "delistings": 161,
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
        # Find symbols in parentheses like (LAYER), (AVNT), (SHELL)
        paren_symbols = re.findall(r'\(([A-Z0-9]{2,10})\)', title)
        # Accept all parenthesized symbols - they are coin tickers in Binance announcements
        found = [s for s in paren_symbols if s.isalpha() and len(s) >= 2]
        # Also check standalone words for known major coins (second pass)
        known_coins = {"BTC","ETH","BNB","SOL","XRP","ADA","DOGE","AVAX","DOT","LINK",
                       "MATIC","SHIB","TRX","ATOM","UNI","APT","ARB","OP","NEAR","FIL",
                       "AAVE","MKR","PEPE","TIA","SEI","SUI","INJ","BONK","WIF","JUP",
                       "FET","AGIX","RNDR","THETA","EGLD","EOS","XLM","VET","ALGO",
                       "SAND","MANA","AXS","FTM","ICP","GRT","BLUR","STRK","JTO","RE"}
        words = title.upper().split()
        for w in words:
            w = w.strip(".,:;!?()[]{}")
            if w in known_coins and w not in found:
                found.append(w)
        return found

    def get_trending_announcements(self) -> List[Dict[str, Any]]:
        """Get announcements - only airdrops and delistings."""
        results = []
        
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
        
        return results




class ResearchEngine:

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

    CATEGORIES = {
        "AI": {"FET", "AGIX", "RNDR", "THETA", "GRT", "ICP", "AR", "OCEAN", "NMR"},
        "MEME": {"DOGE", "SHIB", "PEPE", "BONK", "WIF", "FLOKI", "MEME"},
        "DeFi": {"AAVE", "MKR", "COMP", "UNI", "CAKE", "CRV", "BAL", "SUSHI"},
        "L1": {"SOL", "ADA", "AVAX", "DOT", "NEAR", "APT", "SUI", "SEI", "INJ", "TIA"},
        "L2": {"MATIC", "POL", "ARB", "OP", "METIS"},
        "Exchange": {"BNB", "CRO", "LEO", "OKB", "GT"},
        "Gaming": {"AXS", "SAND", "MANA", "GALA", "ENJ"},
        "DePIN": {"FIL", "HNT", "IOTX"},
        "RWA": {"ONDO"},
        "BTC Ecosystem": {"STX", "ORDI"},
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
                "twist": "Use data to find the signal in the noise — the best trades are quiet before they explode.",
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
            os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
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
                resp = http_post_json(url, payload, timeout=self.config.http_timeout_seconds, retries=4)
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
            f"You are a 20-year veteran Wall Street crypto trader. Your current mood: {tone['persona']}.",
            f"{tone['twist']}",
            "",
            f"Write an engaging Binance Square post about ${symbol} ({name}). Sound human and exciting, NOT like AI.",
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
        parts.append("**Key Levels:**")
        parts.append(f"- Current support around ${setup.get('stop', '?')} and resistance near ${setup.get('target1', '?')}")
        
        if announcement:
            parts.append("")
            parts.append(f"**Binance Announcement:** {announcement.get('title', '')}")
        
        parts.append("")
        parts.append("**CRITICAL FORMAT RULES - FOLLOW ALL:**")
        parts.append("- FIRST SENTENCE MUST BE A STRONG HOOK: one sentence that grabs attention (bold price callout, surprising fact, or rhetorical question)")
        parts.append("- Include AT LEAST 3-4 emojis naturally throughout the post body (🔥🚀📈📊💎👀💡📉⚠️🛑✅)")
        parts.append("- Write 2-3 short punchy paragraphs, very concise (max 120 words total)")
        parts.append("- Cover these in order: (1) Hook about current price action, (2) Volume/momentum insight, (3) What to watch for next")
        parts.append("- Provide MARKET OBSERVATION only - talk about what the chart/volume shows, what traders are doing")
        parts.append(f"- END with exactly 3 relevant hashtags on the last line, first MUST be #{symbol}")
        parts.append("- Sound like an experienced crypto analyst sharing timely market insights - professional but engaging tone")
        parts.append("- You can mention price levels and market structure, but frame as observation not advice")
        parts.append("- Make every sentence deliver value - no fluff, no generic statements")
        parts.append("- Vary sentence structure between posts - do NOT start every post the same way")
        parts.append("- **IMPORTANT: Your post will be read by real crypto traders on Binance Square. Make it interesting and worth their time!**")
        
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
            # Bold prediction / Conviction style 
            hook_emoji = "🚀" if change >= 5 else ("🔥" if change <= -3 else "👀")
            price_action = "surge" if change > 0 else "drop"
            lines = [
                f"{hook_emoji} ${symbol} is painting a {'beautiful' if abs(change) > 5 else 'notable'} chart pattern right now! {change:+.1f}% with {vol_ratio:.1f}x volume - the market is waking up.",
                "",
                f"{analysis.get('reason', 'Momentum is building for this asset.')} Volume at {vol_ratio:.1f}x the average confirms {'strong participation' if vol_ratio > 1.5 else 'healthy activity'}.",
                "",
                f"📊 Price: ${price:.4f} | 24h Change: {change:+.1f}% | Volume Ratio: {vol_ratio:.1f}x",
                "",
                f"{'🎯 Key support forming near current levels - watch for continuation.' if change > 0 else '⚠️ Buyers need to step in soon to defend this zone.'}",
                f"{'💎 Smart money often accumulates during moves like this.' if vol_ratio > 1.5 else '⏳ Patience - let the setup develop before acting.'}",
                "",
                f"Keep {symbol} on your radar today {'traders' if abs_change > 3 else 'everyone'}!",
                f"#{symbol} #BinanceSquare #CryptoSignals",
            ]

        elif template_id == 1:
            # Educational / Market Update style
            direction_emoji = "📈" if change >= 0 else "📉"
            lines = [
                f"{direction_emoji} Quick ${symbol} Market Update - {change:+.1f}% in 24h!",
                "",
                f"📊 Price: ${price:.4f} | 24h Change: {change:+.1f}%",
                f"📋 Volume is running at {vol_ratio:.1f}x the average, which tells us there is {'strong 🔴' if vol_ratio > 1.5 else 'moderate'} interest at these levels.",
                "",
                f"{analysis.get('reason', 'Price is showing interesting movement.')}",
                "",
                f"🟢 On the upside: {analysis.get('bull_case', 'Structure remains positive.')}",
                f"🔴 The risk to consider: {analysis.get('risk', 'Always manage your position size.')}",
                "",
                f"📍 Key levels to watch:",
                f"  📊 Price: ${price:.4f}",
                f"  📈 Volume: {vol_ratio:.1f}x normal",
                f"  💰 Market Cap: ${market_cap:,.0f}",
                "",
                f"{'✅ The volume confirms the move - worth keeping on radar.' if vol_ratio > 1.5 else '⏳ Let the market prove itself before committing.'}",
                "",
                f"💡 **Key Insight:** {'Smart money moves during high volume - watch for the trend to confirm.' if abs_change > 5 else 'Patience and discipline beat emotion in trading.'}",
                f"⏰ {now_str}",
                f"#{symbol} #MarketUpdate #BinanceSquare",
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
            try:
                self.db.save_post({"content": content, "coin_symbol": coin.get("symbol", "")})
            except Exception as e:
                LOGGER.warning("Could not save post to DB: %s", e)
            return True

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
        """Publish to Binance Square via Node.js post-text.mjs script."""
        square_key = self.config.square_api_key
        if not square_key:
            LOGGER.warning("No SQUARE_API_KEY set, saving locally")
            return ""

        import subprocess, shlex, os
        
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "post-text.mjs")
        if not os.path.exists(script_path):
            LOGGER.warning("Node.js script not found at %s, falling back to direct API", script_path)
            return self._try_square_api_direct(coin, content)

        env = os.environ.copy()
        env["BINANCE_SQUARE_OPENAPI_KEY"] = square_key

        try:
            result = subprocess.run(
                ["node", script_path, "--text", content],
                capture_output=True, text=True, timeout=30,
                env=env
            )

            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if data.get("success"):
                    share_link = data.get("shareLink", "")
                    post_id = data.get("postId", "unknown")
                    LOGGER.info("Published via Node.js! ID: %s Link: %s", post_id, share_link)
                    return share_link
                else:
                    LOGGER.warning("Node.js script error: %s", data.get("message", data.get("error", "unknown")))
                    return ""
            else:
                stderr = result.stderr.strip()
                stdout = result.stdout.strip()
                LOGGER.warning("Node.js script failed (rc=%d): %s | %s", result.returncode, stdout[:300], stderr[:200])
                return ""
        except subprocess.TimeoutExpired:
            LOGGER.warning("Node.js script timed out")
            return ""
        except Exception as exc:
            LOGGER.warning("Node.js script error: %s", exc)
            return ""

    def _try_square_api_direct(self, coin: Dict[str, Any], content: str) -> str:
        """Fallback: Direct Square API call if Node.js script is unavailable."""
        square_key = self.config.square_api_key
        payload = {"contentType": 1, "bodyTextOnly": content}
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
            data = json.loads(resp_body)
            if data.get("code") == "000000":
                share_link = data.get("data", {}).get("shareLink", "")
                LOGGER.info("Published via direct API! Link: %s", share_link)
                return share_link
            else:
                LOGGER.warning("Direct API error [%s]: %s", data.get("code"), data.get("message"))
                return ""
        except Exception as exc:
            LOGGER.warning("Direct API failed: %s", exc)
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


def run_once(config, scanner, announcement_engine, research, trade_setup, generator, publisher, posted_symbols) -> bool:
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

    # Score candidates - penalize recently posted
    for coin in unique_candidates:
        change = abs(float(coin.get("change_24h", 0) or 0))
        vol_ratio = float(coin.get("volume_ratio", 1) or 1)
        # Cap volume ratio to avoid one coin dominating the score
        capped_vol = min(vol_ratio, 3.0)
        score = change * 0.6 + capped_vol * 10 * 0.3
        if coin.get("announcement_boost"):
            if abs(change) >= 0.5 or vol_ratio >= 0.8:
                score += 8
                if coin.get("announcement_type") == "new_listing":
                    score += 5
                elif coin.get("announcement_type") == "airdrop":
                    score += 3
            else:
                score += 2
        # Strong penalty for recently posted coins
        sym = coin.get("symbol", "")
        if sym in posted_symbols:
            score *= 0.1  # Almost eliminate repeats (but keep slight chance)
        # Add diversity noise - small random factor so same coins don't always win
        score += random.uniform(-1.5, 1.5)
        coin["_score"] = score

    unique_candidates.sort(key=lambda c: c.get("_score", 0), reverse=True)
    # Pick from top 3 with weighted randomness for diversity
    top_n = min(3, len(unique_candidates))
    weights = [max(0.1, unique_candidates[i].get("_score", 0)) for i in range(top_n)]
    total_w = sum(weights)
    if total_w > 0:
        weights = [w / total_w for w in weights]
        top_idx = random.choices(range(top_n), weights=weights, k=1)[0]
    else:
        top_idx = 0
    top_pick = unique_candidates[top_idx]
    # Extra diversity: if top pick was recently posted, try others
    if top_pick.get("symbol", "") in posted_symbols:
        for candidate in unique_candidates[:5]:
            if candidate.get("symbol", "") not in posted_symbols:
                top_pick = candidate
                break

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

    LOGGER.info("Generating post for %s...", top_pick.get("symbol"))
    content = generator.generate(analysis=analysis, setup=setup, coin=top_pick)

    publisher.publish(top_pick, content)
    # Track the posted symbol for cross-run persistence
    sym = top_pick.get("symbol", "")
    if sym and not content.startswith("[DRAFT_TEMPLATE]"):
        try:
            tracker = PostedSymbolsTracker()
            tracker.mark_posted(sym)
        except Exception as e:
            LOGGER.warning("Could not track posted symbol: %s", e)
    LOGGER.info("Done - post generated for %s", top_pick.get("symbol"))
    return True


def main_loop() -> None:
    """Main loop that runs continuously with configured interval."""
    config = CONFIG
    config.validate()
    
    interval = config.post_interval
    max_iter = config.max_iterations
    
    # In GitHub Actions, ensure at least 3 posts per run (every 2 hours)
    # This handles cases where GHA cron doesn't fire reliably
    if os.getenv("GITHUB_ACTIONS") and max_iter < 3:
        LOGGER.info("GHA detected: overriding max_iterations from %d to 3 for reliability", max_iter)
        max_iter = 3
    
    scanner = MarketScanner(config)
    announcement_engine = BinanceAnnouncementEngine(config)
    research = ResearchEngine()
    trade_setup = TradeSetup()
    generator = GeminiGenerator(config)
    publisher_db = Database(config.database_path)
    publisher = PostPublisher(config)
    publisher.db = publisher_db
    tracker = PostedSymbolsTracker()
    
    iteration = 0
    
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
            db_posted = publisher_db.get_posted_symbols(hours=48)
            tracker_posted = tracker.get_posted_symbols(hours=48)
            posted_symbols = db_posted | tracker_posted
        except Exception:
            try:
                posted_symbols = tracker.get_posted_symbols(hours=48)
            except Exception:
                posted_symbols = set()
        
        success = False
        try:
            success = run_once(config, scanner, announcement_engine, research, trade_setup, generator, publisher, posted_symbols)
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

    # After all iterations complete, trigger the next GHA run automatically
    if os.getenv("GITHUB_ACTIONS"):
        import subprocess
        try:
            result = subprocess.run(
                ["gh", "workflow", "run", "Binance Square Auto Poster"],
                capture_output=True, text=True, timeout=20
            )
            if result.returncode == 0:
                LOGGER.info("Automatically triggered next workflow run")
            else:
                LOGGER.warning("Could not trigger next run: %s", result.stderr[:200])
        except Exception as exc:
            LOGGER.warning("Self-trigger failed: %s", exc)







def main() -> None:
    """Single run mode - for cron/scheduled usage."""
    config = CONFIG
    config.validate()
    
    scanner = MarketScanner(config)
    announcement_engine = BinanceAnnouncementEngine(config)
    research = ResearchEngine()
    trade_setup = TradeSetup()
    generator = GeminiGenerator(config)
    publisher_db = Database(config.database_path)
    publisher = PostPublisher(config)
    publisher.db = publisher_db
    tracker = PostedSymbolsTracker()
    
    db_posted = publisher_db.get_posted_symbols(hours=48)
    tracker_posted = tracker.get_posted_symbols(hours=48)
    posted_symbols = db_posted | tracker_posted
    run_once(config, scanner, announcement_engine, research, trade_setup, generator, publisher, posted_symbols)


if __name__ == "__main__":
    # If post_interval > 0, run in loop mode
    if CONFIG.post_interval > 0:
        main_loop()
    else:
        main()
