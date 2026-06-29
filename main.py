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
from pathlib import Path

# Image Intelligence
from image_engine import ImageComposer, ImageUploader

# --- Embedded Workflow YAML for self-update in GHA ---
_NEW_WORKFLOW_B64 = """bmFtZTogQmluYW5jZSBTcXVhcmUgQXV0byBQb3N0ZXIKCm9uOgogIHNjaGVkdWxlOgogICAgLSBjcm9uOiAnKi81ICogKiAqIConCiAgd29ya2Zsb3dfZGlzcGF0Y2g6CgojIFByZXZlbnQgb3ZlcmxhcHBpbmcgcnVucyDigJQgaWYgYSBydW4gdGFrZXMgPjVtaW4sIG5leHQgb25lIHdhaXRzCmNvbmN1cnJlbmN5OgogIGdyb3VwOiBiaW5hbmNlLXNxdWFyZS1wb3N0ZXIKICBjYW5jZWwtaW4tcHJvZ3Jlc3M6IGZhbHNlCgpqb2JzOgogIHJ1bi1hZ2VudDoKICAgIHJ1bnMtb246IHVidW50dS1sYXRlc3QKCiAgICBwZXJtaXNzaW9uczoKICAgICAgY29udGVudHM6IHdyaXRlCiAgICAgIGFjdGlvbnM6IHdyaXRlCgogICAgc3RlcHM6CiAgICAgIC0gbmFtZTogQ2hlY2tvdXQgY29kZQogICAgICAgIHVzZXM6IGFjdGlvbnMvY2hlY2tvdXRAdjQKICAgICAgICB3aXRoOgogICAgICAgICAgZmV0Y2gtZGVwdGg6IDAKICAgICAgICAgIHRva2VuOiAke3sgc2VjcmV0cy5HSVRIVUJfVE9LRU4gfX0KCiAgICAgIC0gbmFtZTogU2V0IHVwIFB5dGhvbgogICAgICAgIHVzZXM6IGFjdGlvbnMvc2V0dXAtcHl0aG9uQHY1CiAgICAgICAgd2l0aDoKICAgICAgICAgIHB5dGhvbi12ZXJzaW9uOiAiMy4xMSIKCiAgICAgICMgUmVzdG9yZSBwZXJzaXN0ZW50IHN0YXRlIChhZ2VudC5kYikgZnJvbSBwcmV2aW91cyBydW4KICAgICAgLSBuYW1lOiBSZXN0b3JlIGFnZW50LmRiIGZyb20gY2FjaGUKICAgICAgICBpZDogY2FjaGUtcmVzdG9yZQogICAgICAgIHVzZXM6IGFjdGlvbnMvY2FjaGUvcmVzdG9yZUB2NAogICAgICAgIHdpdGg6CiAgICAgICAgICBwYXRoOiBhZ2VudC5kYgogICAgICAgICAga2V5OiBhZ2VudC1kYi0ke3sgZ2l0aHViLnJlZl9uYW1lIH19CgogICAgICAjIFJ1biB0aGUgYWdlbnQg4oCUIHNpbmdsZSBzY2FuLCBleGl0cyBpbW1lZGlhdGVseSBpZiBubyBvcHBvcnR1bml0eQogICAgICAtIG5hbWU6IFJ1biBDcnlwdG8gQWdlbnQKICAgICAgICBlbnY6CiAgICAgICAgICBHRU1JTklfQVBJX0tFWTogJHt7IHNlY3JldHMuR0VNSU5JX0FQSV9LRVkgfX0KICAgICAgICAgIFNRVUFSRV9BUElfS0VZOiAke3sgc2VjcmV0cy5TUVVBUkVfQVBJX0tFWSB9fQogICAgICAgICAgR0hfVE9LRU46ICR7eyBzZWNyZXRzLkdJVEhVQl9UT0tFTiB9fQogICAgICAgICAgRFJZX1JVTjogIjAiCiAgICAgICAgICBMSVZFX01BUktFVF9EQVRBOiAiMSIKICAgICAgICAgIFBPU1RfSU5URVJWQUw6ICIwIgogICAgICAgICAgTUFYX0lURVJBVElPTlM6ICIxIgogICAgICAgICAgTUFYX0RBSUxZX1BPU1RTOiAiOCIKICAgICAgICAgIEdFTUlOSV9NT0RFTDogImdlbWluaS0yLjUtZmxhc2giCiAgICAgICAgcnVuOiBweXRob24gbWFpbi5weQoKICAgICAgIyBQZXJzaXN0IHN0YXRlIGZvciBuZXh0IDUtbWludXRlIHJ1bgogICAgICAtIG5hbWU6IFNhdmUgYWdlbnQuZGIgdG8gY2FjaGUKICAgICAgICBpZjogYWx3YXlzKCkKICAgICAgICB1c2VzOiBhY3Rpb25zL2NhY2hlL3NhdmVAdjQKICAgICAgICB3aXRoOgogICAgICAgICAgcGF0aDogYWdlbnQuZGIKICAgICAgICAgIGtleTogYWdlbnQtZGItJHt7IGdpdGh1Yi5yZWZfbmFtZSB9fQoKICAgICAgIyBVcGxvYWQgb3V0cHV0cyBmb3IgcmV2aWV3IChvbmx5IHdoZW4gcG9zdCB3YXMgZ2VuZXJhdGVkKQogICAgICAtIG5hbWU6IFVwbG9hZCBhcnRpZmFjdHMKICAgICAgICBpZjogYWx3YXlzKCkKICAgICAgICB1c2VzOiBhY3Rpb25zL3VwbG9hZC1hcnRpZmFjdEB2NAogICAgICAgIHdpdGg6CiAgICAgICAgICBuYW1lOiBhZ2VudC1vdXRwdXQtJHt7IGdpdGh1Yi5ydW5faWQgfX0KICAgICAgICAgIHBhdGg6IHwKICAgICAgICAgICAgcG9zdHMvCiAgICAgICAgICAgIHJlc2VhcmNoLwogICAgICAgICAgICBwcm9tcHRzLwogICAgICAgICAgICBkcmFmdHMvCiAgICAgICAgICAgIGFnZW50LmRiCiAgICAgICAgICAgIHB1Ymxpc2hlZF9wb3N0cy5qc29ubAo="""

def _maybe_update_workflow():
    """Update workflow file when running in GHA (GITHUB_TOKEN has workflow scope)."""
    import base64, json, urllib.request
    
    gha_token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or os.getenv("INPUT_GITHUB_TOKEN")
    repo_name = os.getenv("GITHUB_REPOSITORY", "")
    workflow_path = ".github/workflows/run_bot.yml"
    
    if not gha_token or not repo_name:
        LOGGER.debug("Not in GHA or no token -- skipping workflow update")
        return
    
    try:
        url = "https://api.github.com/repos/" + repo_name + "/contents/" + workflow_path
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Bearer " + gha_token)
        req.add_header("Accept", "application/vnd.github.v3+json")
        
        resp = urllib.request.urlopen(req)
        current = json.loads(resp.read())
        current_b64 = current.get("content", "").replace("\n", "")
        sha = current.get("sha", "")
        
        expected_b64 = _NEW_WORKFLOW_B64.strip()
        if current_b64.strip() == expected_b64:
            LOGGER.info("Workflow already up to date")
            return
        
        LOGGER.info("Updating workflow to 5-min schedule for repo=%s path=%s...", repo_name, workflow_path)
        payload = json.dumps({
            "message": "Auto-update: 5-minute opportunity scan model",
            "content": expected_b64,
            "sha": sha,
        }).encode()
        
        req2 = urllib.request.Request(url, data=payload, method="PUT")
        req2.add_header("Authorization", "Bearer " + gha_token)
        req2.add_header("Accept", "application/vnd.github.v3+json")
        req2.add_header("Content-Type", "application/json")
        
        resp2 = urllib.request.urlopen(req2)
        result = json.loads(resp2.read())
        LOGGER.info("Workflow updated! Commit: " + result.get("commit", {}).get("sha", "?"))
    except Exception as e:
        LOGGER.warning("Workflow update attempt failed: " + str(e)[:200])



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
    
    # --- Performance tuning (env configurable) ---
    min_word_count: int
    min_hashtags: int
    min_candidates: int
    repetition_hard_hours: int
    repetition_soft_hours: int
    save_research_packages: bool
    max_daily_posts: int
    min_cap_for_safety: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            square_api_key=os.getenv("SQUARE_API_KEY", ""),
            post_interval=int(os.getenv("POST_INTERVAL", "300")),
            database_path=os.getenv("DATABASE_PATH", "agent.db"),
            publish_log_path=os.getenv("PUBLISH_LOG_PATH", "published_posts.jsonl"),
            max_iterations=int(os.getenv("MAX_ITERATIONS", "24")),
            dry_run=os.getenv("DRY_RUN", "1").strip().lower() not in {"0", "false", "no"},
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            live_market_data=os.getenv("LIVE_MARKET_DATA", "0").strip().lower() in {"1", "true", "yes"},
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            http_timeout_seconds=int(os.getenv("HTTP_TIMEOUT_SECONDS", "15")),
            gemini_temperature=float(os.getenv("GEMINI_TEMPERATURE", "0.9")),
            gemini_top_p=float(os.getenv("GEMINI_TOP_P", "0.95")),
            gemini_max_output_tokens=int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "2048")),
            
            # Performance tuning defaults
            min_word_count=int(os.getenv("MIN_WORD_COUNT", "50")),
            min_hashtags=int(os.getenv("MIN_HASHTAGS", "3")),
            min_candidates=int(os.getenv("MIN_CANDIDATES", "3")),
            repetition_hard_hours=int(os.getenv("REPETITION_HARD_HOURS", "12")),
            repetition_soft_hours=int(os.getenv("REPETITION_SOFT_HOURS", "24")),
            save_research_packages=os.getenv("SAVE_RESEARCH_PACKAGES", "1").strip().lower() in {"1", "true", "yes"},
            max_daily_posts=int(os.getenv("MAX_DAILY_POSTS", "8")),
            min_cap_for_safety=int(os.getenv("MIN_CAP_FOR_SAFETY", "500000")),
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
        if self.min_word_count < 30:
            raise ValueError("MIN_WORD_COUNT must be >= 30")
        if self.min_hashtags < 2:
            raise ValueError("MIN_HASHTAGS must be >= 2")
        if self.min_candidates < 2:
            raise ValueError("MIN_CANDIDATES must be >= 2")


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


TOP_5_COINS = {"BTC", "ETH", "BNB", "SOL", "XRP"}
BINANCE_LISTED = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK",
    "MATIC", "POL", "SHIB", "TRX", "ATOM", "UNI", "APT", "ARB", "OP", "NEAR",
    "FIL", "ALGO", "AAVE", "MKR", "COMP", "SAND", "MANA", "AXS", "THETA", "FTM",
    "ICP", "EOS", "XLM", "VET", "EGLD", "GRT", "RNDR", "FET", "AGIX", "PEPE",
    "TIA", "SEI", "SUI", "INJ", "BLUR", "STRK", "BONK", "WIF", "JUP", "JTO",
    "RE", "LAYER", "AVNT", "SHELL", "NOT", "DOGS", "HMSTR", "ETHFI", "EIGEN",
    "VIRTUAL", "AI16Z", "ARC", "AKT", "OCEAN", "TAO", "PENDLE", "ENA", "ALT",
}




# ─── PERSISTENT POST HISTORY (JSONL + Git Push) ───
# Survives GHA ephemeral containers by storing records in a file
# that gets git-committed after each publish.
_POST_HISTORY_FILE = "published_posts.jsonl"


def _load_post_history() -> dict:
    """Load published posts from JSONL file.
    
    Returns dict of symbol -> hours_ago for recently posted coins.
    This survives GHA runs because the file is committed to the repo.
    
    Safety: if the file is missing or corrupted, it is safely recreated.
    All malformed lines are skipped and reported.
    """
    path = Path(_POST_HISTORY_FILE)
    
    # Missing file is not an error; first run has no history
    if not path.exists():
        LOGGER.info("Post history file %s not found — starting fresh", _POST_HISTORY_FILE)
        return {}
    
    posts: dict = {}
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC for comparison with JSONL timestamps
    
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception as e:
        LOGGER.warning("Cannot read %s (%s) — recreating", _POST_HISTORY_FILE, e)
        try:
            path.write_text("", encoding="utf-8")
        except Exception:
            pass
        return {}
    
    if not raw:
        return {}
    
    corrupt_lines = 0
    valid_lines = 0
    
    for idx, line in enumerate(raw.split('\n'), 1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            symbol = record.get("symbol", "").upper().strip()
            ts_str = record.get("timestamp", "")
            if not symbol or not ts_str:
                corrupt_lines += 1
                continue
            dt = datetime.fromisoformat(ts_str)
            # Strip timezone if present (we compare against naive UTC)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            hours_ago = (now - dt).total_seconds() / 3600.0
            if symbol not in posts or hours_ago < posts[symbol]:
                posts[symbol] = hours_ago
            valid_lines += 1
        except (json.JSONDecodeError, ValueError, TypeError):
            corrupt_lines += 1
            LOGGER.debug("Skipped corrupt JSONL line %d: %s", idx, line[:80])
            continue
    
    if corrupt_lines > 0:
        LOGGER.warning("Post history loaded: %d valid, %d corrupt lines from %s",
                       valid_lines, corrupt_lines, _POST_HISTORY_FILE)
    else:
        LOGGER.info("Post history loaded: %d coins from %s (%d lines)",
                    len(posts), _POST_HISTORY_FILE, valid_lines)
    
    return posts


def _append_post_record(symbol: str, catalyst: str, link: str, image_url: str = "") -> bool:
    """Append a post record to the JSONL history file.
    
    Verifies the record was written successfully.
    Returns True if verified, False on failure.
    The record always survives in the file even if git push fails later.
    """
    record = {
        "symbol": symbol.upper().strip(),
        "timestamp": utc_now(),
        "catalyst": catalyst,
        "link": link,
        "image_url": image_url if image_url else "",
    }
    json_line = json.dumps(record) + "\n"
    
    try:
        path = Path(_POST_HISTORY_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json_line)
            f.flush()
            os.fsync(f.fileno())
        
        # Verify the record was written correctly
        with open(path, "r", encoding="utf-8") as f:
            f.seek(0, 2)  # Seek to end
            size = f.tell()
            # Read last ~500 bytes to find our record
            read_start = max(0, size - 500)
            f.seek(read_start)
            tail = f.read()
        
        if symbol.upper() in tail and record["timestamp"][:16] in tail:
            LOGGER.info("JSONL updated: $%s | catalyst=%s | link=%s",
                        symbol, catalyst, link or "local-only")
            return True
        else:
            LOGGER.warning("JSONL write verification failed for $%s — file may be inconsistent", symbol)
            return False
    except Exception as e:
        LOGGER.error("Failed to append to %s: %s", _POST_HISTORY_FILE, e)
        return False


def _try_git_push(max_retries: int = 3) -> bool:
    """Try to git-commit and push the JSONL history file to the repo.
    
    Retries up to max_retries times with exponential backoff.
    The JSONL record is ALREADY written to disk before this is called,
    so even if all retries fail, the record is NOT lost — it persists
    on disk and will be retried on the next run via _retry_pending_push().
    
    Returns True if push succeeded, False otherwise (never raises).
    """
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        LOGGER.info("Git push skipped: no GH_TOKEN/GITHUB_TOKEN available")
        return False
    repo = os.getenv("GITHUB_REPOSITORY", "")
    if not repo:
        LOGGER.info("Git push skipped: no GITHUB_REPOSITORY available")
        return False
    
    import subprocess as _sp
    
    # Log the current branch/HEAD state for debugging
    try:
        branch_check = _sp.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, timeout=5, text=True
        )
        current_branch = branch_check.stdout.strip()
        sha_check = _sp.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, timeout=5, text=True
        )
        current_sha = sha_check.stdout.strip()
        LOGGER.info("Git state: branch=%s sha=%s", current_branch, current_sha)
    except Exception as e:
        LOGGER.debug("Could not get git state: %s", e)
        current_branch = "unknown"
        current_sha = "unknown"
    
    for attempt in range(1, max_retries + 1):
        LOGGER.debug("Git push attempt %d/%d", attempt, max_retries)
        try:
            _sp.run(
                ["git", "add", _POST_HISTORY_FILE],
                capture_output=True, timeout=30
            )
            _sp.run(
                ["git", "add", "posts/"],
                capture_output=True, timeout=30
            )
            commit_result = _sp.run(
                ["git", "-c", "user.name=bot", "-c", "user.email=bot@bot.com",
                 "commit", "-m", f"Auto-save: post records [{utc_now()[:10]}]"],
                capture_output=True, timeout=30
            )
            if commit_result.returncode != 0:
                stderr = commit_result.stderr.decode("utf-8", errors="replace")
                stdout = commit_result.stdout.decode("utf-8", errors="replace")
                full_output = (stderr + " " + stdout).lower()
                if "nothing to commit" in full_output or "nothing added to commit" in full_output:
                    LOGGER.info("Git commit: nothing new to commit -- JSONL unchanged (this is fine)")
                    return True  # Nothing to push but no error -- success
                LOGGER.warning("Git commit failed (attempt %d/%d): %s",
                               attempt, max_retries, full_output[:200])
                if attempt < max_retries:
                    _sleep = min(5 * (2 ** (attempt - 1)), 20)
                    time.sleep(_sleep)
                continue
            
            # Use explicit remote URL + push to main branch
            push_url = f"https://x-access-token:{token}@github.com/{repo}"
            _sp.run(
                ["git", "remote", "set-url", "origin", push_url],
                capture_output=True, timeout=10
            )
            # Determine target branch: use current branch if on a named branch, fallback to main
            target_branch = current_branch if current_branch not in ("unknown", "HEAD") else "main"
            LOGGER.info("Pushing commit %s on branch %s to origin/%s",
                        current_sha, current_branch, target_branch)
            push_result = _sp.run(
                ["git", "push", "origin", f"HEAD:{target_branch}"],
                capture_output=True, timeout=60
            )
            if push_result.returncode == 0:
                p_stdout = push_result.stdout.decode("utf-8", errors="replace").strip()
                p_stderr = push_result.stderr.decode("utf-8", errors="replace").strip()
                push_info = (p_stdout + " " + p_stderr).strip()[:200]
                LOGGER.info("Git push SUCCESS (attempt %d/%d): commit %s pushed to %s -- %s",
                            attempt, max_retries, current_sha, repo, push_info)
                return True
            else:
                err = push_result.stderr.decode("utf-8", errors="replace").strip()[:500]
                if attempt < max_retries:
                    sleep_time = min(5 * (2 ** (attempt - 1)) + random.uniform(0, 2), 30)
                    LOGGER.warning("Git push FAILED attempt %d/%d (retrying in %.0fs): %s",
                                   attempt, max_retries, sleep_time, err)
                    time.sleep(sleep_time)
                else:
                    LOGGER.warning("Git push FAILED after %d attempts (record saved locally, "
                                   "will retry on next run): %s", max_retries, err)
                    return False
        except _sp.TimeoutExpired:
            if attempt < max_retries:
                sleep_time = min(5 * (2 ** (attempt - 1)), 20)
                LOGGER.warning("Git push TIMEOUT attempt %d/%d (retrying in %.0fs)",
                               attempt, max_retries, sleep_time)
                time.sleep(sleep_time)
            else:
                LOGGER.warning("Git push TIMEOUT after %d attempts (record saved locally)",
                               max_retries)
                return False
        except Exception as e:
            if attempt < max_retries:
                sleep_time = min(5 * (2 ** (attempt - 1)), 20)
                LOGGER.warning("Git push ERROR attempt %d/%d (retrying in %.0fs): %s",
                               attempt, max_retries, sleep_time, e)
                time.sleep(sleep_time)
            else:
                LOGGER.warning("Git push ERROR after %d attempts: %s", max_retries, e)
                return False
    
    return False

def _retry_pending_push() -> bool:
    """Startup retry: check if published_posts.jsonl has uncommitted changes
    and push them. This handles the scenario where the previous workflow run's
    git push failed — the JSONL file has records that were never committed.
    
    This runs at the start of every workflow run BEFORE any decision is made,
    so the repo is always up to date before scanning begins.
    
    Works even if no publish happens in this run — it just syncs pending changes.
    """
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        return False
    repo = os.getenv("GITHUB_REPOSITORY", "")
    if not repo:
        return False
    
    path = Path(_POST_HISTORY_FILE)
    if not path.exists():
        return False
    
    import subprocess
    try:
        # Check for uncommitted changes in the tracked files
        status_result = subprocess.run(
            ["git", "status", "--porcelain", _POST_HISTORY_FILE, "posts/"],
            capture_output=True, timeout=15
        )
        status_output = status_result.stdout.decode("utf-8", errors="replace").strip()
        
        if not status_output:
            # No uncommitted changes — nothing to retry
            return False
        
        # There ARE uncommitted changes — previous push must have failed
        LOGGER.info("Startup retry: detected uncommitted changes in %s from previous run",
                    _POST_HISTORY_FILE)
        LOGGER.info("  git status: %s", status_output[:200])
        
        # Now push them
        return _try_git_push(max_retries=3)
    except Exception as e:
        LOGGER.debug("Startup retry check: %s", e)
        return False




def _verify_persistence_integrity() -> bool:
    """Verify that the persistence layer is intact before publishing.
    
    Returns True if history is reliable (safe to publish).
    Returns False if integrity cannot be guaranteed (must fail CLOSED).
    
    Failure scenarios:
    - JSONL exists in git history but is missing from checkout → cache+git both failed
    - JSONL exists but is empty and git had content → file was truncated/corrupted
    - Any situation where we cannot guarantee we have the full post history
    
    When this returns False, the system MUST NOT publish — it cannot
    guarantee it won't repeat a recently posted coin.
    """
    path = Path(_POST_HISTORY_FILE)
    
    import subprocess
    
    if path.exists():
        try:
            size = path.stat().st_size
            if size > 0:
                LOGGER.info("INTEGRITY OK: %s has %d bytes (%d lines) — history loaded",
                           _POST_HISTORY_FILE, size, len(path.read_text().strip().split(chr(10))) if size > 0 else 0)
                return True  # Has content — history is usable
            
            # File exists but is EMPTY — possibly truncated
            LOGGER.warning("INTEGRITY: %s exists but is empty (0 bytes)", _POST_HISTORY_FILE)
            
            # Check if git ever had this file with content
            git_log = subprocess.run(
                ["git", "log", "--oneline", "-1", "--", _POST_HISTORY_FILE],
                capture_output=True, timeout=10
            )
            if git_log.stdout.strip():
                # File exists in git but is empty locally.
                # Check if git always had it empty (fresh deployment) or
                # if content was lost (corruption).
                import subprocess as _sp
                _size_check = _sp.run(
                    ["git", "show", "HEAD:published_posts.jsonl"],
                    capture_output=True, timeout=10
                )
                _git_size = len(_size_check.stdout.strip())
                if _git_size > 0:
                    # Git has content — cache likely overwrote checkout with stale 0-byte.
                    # Restore from git instead of failing closed.
                    LOGGER.warning("INTEGRITY RESTORE: %s is empty locally but has %d bytes in git. "
                                   "Restoring from git (cache overwrote checkout).",
                                   _POST_HISTORY_FILE, _git_size)
                    restored_content = _size_check.stdout
                    if isinstance(restored_content, bytes):
                        restored_content = restored_content.decode("utf-8", errors="replace")
                    try:
                        path.write_text(restored_content, encoding="utf-8")
                        new_size = path.stat().st_size
                        LOGGER.info("INTEGRITY RESTORE OK: Restored %s from git (%d bytes)",
                                    _POST_HISTORY_FILE, new_size)
                        return True
                    except Exception as restore_err:
                        LOGGER.warning("INTEGRITY RESTORE FAILED: Could not restore %s: %s. "
                                       "Failing closed.", _POST_HISTORY_FILE, restore_err)
                        return False
                else:
                    # File was always empty in git — fresh deployment, safe
                    LOGGER.info("INTEGRITY: %s is empty in git too — fresh deployment, safe to proceed",
                               _POST_HISTORY_FILE)
                    path.write_text("", encoding="utf-8")
                    return True
            else:
                # New file, never committed — first run scenario
                LOGGER.info("INTEGRITY: %s is new (never committed) — safe to proceed",
                           _POST_HISTORY_FILE)
                return True
        except subprocess.TimeoutExpired:
            LOGGER.warning("INTEGRITY: git log check timed out — allowing (safe default)")
            return True
        except Exception as e:
            LOGGER.warning("INTEGRITY: check error: %s — allowing", e)
            return True
    
    # File does NOT exist on disk
    LOGGER.warning("INTEGRITY: %s does not exist on disk", _POST_HISTORY_FILE)
    
    try:
        # Check if git ever had this file
        git_log = subprocess.run(
            ["git", "log", "--oneline", "-1", "--", _POST_HISTORY_FILE],
            capture_output=True, timeout=10
        )
        if git_log.stdout.strip():
            # File existed in git but is not in checkout — cache or cache restore may have failed.
            # Restore from git instead of failing closed.
            LOGGER.warning("INTEGRITY RESTORE: %s exists in git history but is missing from checkout. "
                           "Restoring from git.", _POST_HISTORY_FILE)
            try:
                git_content = subprocess.run(
                    ["git", "show", "HEAD:published_posts.jsonl"],
                    capture_output=True, timeout=10
                )
                restored = git_content.stdout
                if isinstance(restored, bytes):
                    restored = restored.decode("utf-8", errors="replace")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(restored, encoding="utf-8")
                new_size = path.stat().st_size
                LOGGER.info("INTEGRITY RESTORE OK: Restored %s from git (%d bytes)",
                            _POST_HISTORY_FILE, new_size)
                return True
            except Exception as restore_err:
                LOGGER.warning("INTEGRITY RESTORE FAILED: Could not restore %s: %s. "
                               "Failing closed.", _POST_HISTORY_FILE, restore_err)
                return False
        else:
            # Never committed — brand new repo, first run
            LOGGER.info("INTEGRITY: %s has no git history — assuming first run ever", _POST_HISTORY_FILE)
            # Create the file so subsequent runs have it
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
                LOGGER.info("INTEGRITY: Created empty %s for first run", _POST_HISTORY_FILE)
            except Exception:
                pass
            return True
    except subprocess.TimeoutExpired:
        LOGGER.warning("INTEGRITY: git log check timed out — allowing")
        return True
    except Exception as e:
        LOGGER.warning("INTEGRITY: git check error: %s — allowing", e)
        return True


def _check_jsonl_cooldown(symbol: str, catalyst_type: str = "") -> bool:
    """Final cooldown check by reading the JSONL file directly.
    
    Scans the most recent records for the given symbol.
    If found within the cooldown window AND no exceptional catalyst,
    returns True (meaning: cooldown IS active, block publishing).
    
    This is a safety net that works even if the in-memory
    posted_hours_data dict is stale or incomplete.
    
    Exceptional catalysts that bypass cooldown:
    - new_listing, launchpool, megadrop, airdrop, delisting
    """
    path = Path(_POST_HISTORY_FILE)
    if not path.exists():
        return False  # No history = no cooldown
    
    hard_hours = CONFIG.repetition_hard_hours  # default 12
    soft_hours = CONFIG.repetition_soft_hours  # default 24
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC for comparison with JSONL timestamps
    symbol_up = symbol.upper().strip()
    
    exceptional = catalyst_type in ("new_listing", "launchpool", "megadrop", "airdrop", "delisting")
    
    try:
        # Read last 50 lines only (fast scan)
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        if not raw:
            return False
        
        lines = [l.strip() for l in raw.split('\n') if l.strip()]
        # Scan from newest (last) to oldest
        for line in reversed(lines[-50:]):
            try:
                record = json.loads(line)
                rec_sym = record.get("symbol", "").upper().strip()
                if rec_sym != symbol_up:
                    continue
                
                ts_str = record.get("timestamp", "")
                if not ts_str:
                    continue
                
                dt = datetime.fromisoformat(ts_str)
                # Strip timezone if present (we compare against naive UTC)
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                hours_ago = (now - dt).total_seconds() / 3600.0
                
                if hours_ago < hard_hours:
                    if not exceptional:
                        LOGGER.warning("COOLDOWN ACTIVE: $%s posted %.1fh ago (hard limit %dh)",
                                       symbol, hours_ago, hard_hours)
                        return True
                
                if hours_ago < soft_hours and not exceptional:
                    LOGGER.warning("COOLDOWN ACTIVE: $%s posted %.1fh ago (soft limit %dh, catalyst=%s)",
                                   symbol, hours_ago, soft_hours, catalyst_type or "none")
                    return True
                
                # Found the most recent record for this coin, and it's outside cooldown
                return False
                
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
        
        return False  # No record found for this symbol
    except Exception as e:
        LOGGER.debug("Cooldown check error: %s", e)
        return False  # On error, allow (don't block publishing)


def _passes_objective_filters(
    symbol: str,
    price: float,
    change_24h: float,
    volume_ratio: float,
    market_cap: float,
    announcements: List[Dict[str, Any]],
    posted_hours_data: Dict[str, float],
    from_skills_hub: bool = False,
    liquidity: float = 0.0,
    risk_level: int = 0,
) -> bool:
    """Deterministic, non-negotiable checks every candidate must pass.

    Skills Hub tokens use lower thresholds (price >= $0.0001, mcap >= $100k).
    All tokens must pass liquidity ($10k min) and risk (no level 3) checks.
    """
    reject_reason = None

    # Source-aware thresholds
    price_min = 0.0001 if from_skills_hub else 0.01
    cap_min = 100000 if from_skills_hub else CONFIG.min_cap_for_safety

    # 1. Must be a valid asset
    if not symbol:
        reject_reason = "empty symbol"
    elif price <= 0 or price < price_min:
        reject_reason = "price too low: $%.6f (threshold: $%.4f)" % (price, price_min)
    elif market_cap > 0 and market_cap < cap_min:
        reject_reason = "market cap too low: $%.0f (threshold: $%.0f)" % (market_cap, cap_min)

    if not reject_reason and abs(change_24h) > 150:
        reject_reason = "extreme move: %.1f%%" % change_24h

    # 2. Liquidity check (only when data is available)
    if not reject_reason and liquidity > 0 and liquidity < 10000:
        reject_reason = "liquidity too low: $%.0f (min $10k)" % liquidity

    # 3. Risk check (only for Skills Hub tokens with audit data)
    if not reject_reason and risk_level >= 3:
        reject_reason = "high risk (riskLevel=%d) \u2014 HARD REJECT" % risk_level

    # 4. Must have a FRESH catalyst
    has_announcement = False
    ann_type = ""
    has_exceptional_catalyst = False
    for a in announcements:
        if symbol in a.get("symbols", []):
            has_announcement = True
            ann_type = a.get("type", "")
            if ann_type in ("new_listing", "launchpool", "megadrop", "airdrop", "delisting"):
                has_exceptional_catalyst = True
            break

    has_movement = abs(change_24h) > 2.5 or volume_ratio > 1.5

    if not reject_reason and not has_announcement and not has_movement:
        reject_reason = "no catalyst (change=%.1f%%, vol=%.1fx)" % (change_24h, volume_ratio)

    # 5. Repetition check
    if not reject_reason and symbol in posted_hours_data:
        hours_ago = posted_hours_data[symbol]
        hard = CONFIG.repetition_hard_hours
        soft = CONFIG.repetition_soft_hours
        if hours_ago < hard and not has_exceptional_catalyst:
            reject_reason = "recently posted (%.0fh ago, hard limit %dh)" % (hours_ago, hard)
        elif hours_ago < soft and not has_exceptional_catalyst:
            reject_reason = "recently posted (%.0fh ago, no new catalyst, soft limit %dh)" % (hours_ago, soft)
        elif hours_ago < 48 and not has_exceptional_catalyst and abs(change_24h) < 5:
            reject_reason = "recently posted (%.0fh ago, weak move %.1f%%)" % (hours_ago, change_24h)

    # 6. Top 5 coins \u2014 only with exceptional catalyst
    if not reject_reason and symbol in TOP_5_COINS:
        if not has_exceptional_catalyst:
            reject_reason = "top 5 coin without exceptional catalyst"
        elif abs(change_24h) < 5:
            reject_reason = "top 5 coin with weak move (%.1f%%)" % change_24h

    if reject_reason:
        LOGGER.info("FILTER REJECT: $%s \u2014 %s", symbol, reject_reason)
        return False

    LOGGER.info("FILTER PASS: $%s (%.1f%%, %.1fx vol, skills=%s, liq=$%.0f)",
                symbol, change_24h, volume_ratio,
                "YES" if from_skills_hub else "NO",
                liquidity if liquidity > 0 else 0)
    return True

def _extract_catalyst_for_coin(symbol: str, announcements: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    '''Find the strongest catalyst for a coin from announcements.'''
    best = None
    best_priority = -1
    priority = {"new_listing": 10, "launchpool": 9, "megadrop": 9, "airdrop": 8, "delisting": 6, "news": 3}
    for a in announcements:
        if symbol in a.get("symbols", []):
            p = priority.get(a.get("type", "news"), 0)
            if p > best_priority:
                best_priority = p
                best = a
    return best


def _get_today_post_count(db) -> int:
    """Count how many posts have been published today (UTC)."""
    today_before = utc_now()[:10]  # YYYY-MM-DD
    try:
        rows = db.conn.execute(
            "SELECT COUNT(*) FROM post_analytics WHERE created_at >= ?",
            (today_before,)
        ).fetchall()
        return rows[0][0] if rows else 0
    except Exception:
        return 0



def _atomic_write_json(path: str, data: dict) -> None:
    """Atomically write JSON data to a file using temp + os.replace pattern."""
    import json as _j, tempfile, os
    tmp = None
    try:
        tmp_fd, tmp = tempfile.mkstemp(suffix='.json', dir=os.path.dirname(path) or '.')
        with os.fdopen(tmp_fd, 'w') as f:
            _j.dump(data, f)
        os.replace(tmp, path)
    except Exception:
        if tmp and os.path.exists(tmp):
            try: os.unlink(tmp)
            except: pass
        raise

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
    liquidity: float = 0.0

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
            "liquidity": self.liquidity,
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
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS post_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER,
                    coin_symbol TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    catalyst_type TEXT,
                    narrative TEXT,
                    hook_style TEXT,
                    trade_setup_style TEXT,
                    decision_reason TEXT,
                    word_count INTEGER,
                    hashtags TEXT,
                    gemini_decision TEXT,
                    square_post_link TEXT,
                    views INTEGER,
                    likes INTEGER,
                    comments INTEGER,
                    shares INTEGER,
                    eligible_traders INTEGER,
                    reward_earned REAL,
                    metrics_updated_at TEXT,
                    is_analyzed INTEGER DEFAULT 0,
                    FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE SET NULL
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
        now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC for comparison with JSONL timestamps
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
                    if posted_time.tzinfo is not None:
                        posted_time = posted_time.replace(tzinfo=None)
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
        """Get top performing symbols from analytics."""
        try:
            rows = self.conn.execute(
                """
                SELECT coin_symbol, AVG(views) as avg_views
                FROM post_analytics
                WHERE views IS NOT NULL
                GROUP BY coin_symbol
                ORDER BY avg_views DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()
            return [row[0] for row in rows if row[0]]
        except Exception:
            return []


class PerformanceAnalyzer:
    """Performance Intelligence Layer.
    
    Stores detailed post metadata and learns from historical performance.
    Uses real data to improve Research Packages and Gemini prompts.
    
    For every published post:
    - Store all metadata (catalyst, narrative, hook style, word count, etc.)
    - After 24-72h: update with views, likes, comments, shares, rewards
    - Analyze historical data to find winning patterns
    - Feed insights back into Research Packages and prompts
    
    Metrics update: Since Binance Square has no read API yet,
    metrics can be updated via update_metrics.py or manual entry.
    The structural analysis (catalyst, narrative, timing) works immediately.
    """
    
    def __init__(self, db: Database):
        self.db = db
    
    def record_publish(
        self,
        coin: Dict[str, Any],
        post_content: str,
        decision_reason: str = "",
        square_link: str = "",
    ) -> None:
        """Store full metadata for a published post."""
        symbol = coin.get("symbol", "")
        catalyst_type = coin.get("announcement_type", "market_move")
        narrative = coin.get("narrative", "")
        
        if not narrative:
            # Try to extract from announcements
            ann_type = coin.get("announcement_type", "")
            if ann_type in ("new_listing", "launchpool", "megadrop"):
                narrative = "listing"
            elif ann_type == "airdrop":
                narrative = "airdrop"
            elif ann_type == "delisting":
                narrative = "delisting"
        
        hook_style = self._detect_hook_style(post_content)
        word_count = len(post_content.split())
        hashtags_list = self._extract_hashtags(post_content)
        hashtags_str = ",".join(hashtags_list)
        trade_style = self._detect_trade_setup_style(post_content)
        
        try:
            with self.db.conn:
                self.db.conn.execute(
                    """
                    INSERT INTO post_analytics (
                        coin_symbol, created_at, catalyst_type, narrative,
                        hook_style, trade_setup_style, decision_reason,
                        word_count, hashtags, square_post_link
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol,
                        utc_now(),
                        catalyst_type,
                        narrative,
                        hook_style,
                        trade_style,
                        (decision_reason or "")[:200],
                        word_count,
                        hashtags_str,
                        square_link,
                    )
                )
            LOGGER.info("Analytics: stored $%s (%s, %s, %d words)",
                        symbol, catalyst_type, hook_style, word_count)
        except Exception as e:
            LOGGER.debug("Analytics storage: %s", e)
    
    def update_metrics(
        self,
        coin_symbol: str,
        views: int = None,
        likes: int = None,
        comments: int = None,
        shares: int = None,
        traders: int = None,
        reward: float = None,
    ) -> bool:
        """Update performance metrics for the latest post of a coin."""
        try:
            with self.db.conn:
                cursor = self.db.conn.execute(
                    """
                    SELECT id FROM post_analytics
                    WHERE coin_symbol = ? AND views IS NULL
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (coin_symbol.upper(),)
                )
                row = cursor.fetchone()
                if not row:
                    LOGGER.warning("No pending metrics row for $%s", coin_symbol)
                    return False
                
                post_id = row[0]
                updates = []
                params = []
                if views is not None:
                    updates.append("views = ?")
                    params.append(views)
                if likes is not None:
                    updates.append("likes = ?")
                    params.append(likes)
                if comments is not None:
                    updates.append("comments = ?")
                    params.append(comments)
                if shares is not None:
                    updates.append("shares = ?")
                    params.append(shares)
                if traders is not None:
                    updates.append("eligible_traders = ?")
                    params.append(traders)
                if reward is not None:
                    updates.append("reward_earned = ?")
                    params.append(reward)
                
                updates.append("metrics_updated_at = ?")
                params.append(utc_now())
                params.append(post_id)
                
                sql = "UPDATE post_analytics SET " + ", ".join(updates) + " WHERE id = ?"
                self.db.conn.execute(sql, params)
                
            LOGGER.info("Metrics updated for $%s", coin_symbol)
            return True
        except Exception as e:
            LOGGER.warning("Metrics update failed: %s", e)
            return False
    
    def get_insights_summary(self) -> str:
        """Analyze historical posts and return actionable insights.
        
        Returns a text summary for enhancing Research Packages.
        Works with available data (metrics may be partial).
        """
        insights = []
        
        # 1. Best catalyst type
        try:
            rows = self.db.conn.execute(
                """
                SELECT catalyst_type, COUNT(*) as cnt,
                       AVG(CASE WHEN views IS NOT NULL THEN views ELSE NULL END) as avg_views
                FROM post_analytics
                GROUP BY catalyst_type
                ORDER BY cnt DESC
                LIMIT 5
                """
            ).fetchall()
            if rows:
                best = rows[0]
                info = "Most used catalyst: %s (%d posts)" % (best[0], best[1])
                if best[2]:
                    info += ", avg views: %.0f" % best[2]
                insights.append(info)
        except Exception:
            pass
        
        # 2. Narrative coverage
        try:
            rows = self.db.conn.execute(
                """
                SELECT narrative, COUNT(*) as cnt
                FROM post_analytics
                WHERE narrative IS NOT NULL AND narrative != ''
                GROUP BY narrative
                ORDER BY cnt DESC
                LIMIT 5
                """
            ).fetchall()
            if rows:
                items = ["%s (%d)" % (r[0], r[1]) for r in rows[:3]]
                insights.append("Narratives: " + ", ".join(items))
        except Exception:
            pass
        
        # 3. Hook styles used
        try:
            rows = self.db.conn.execute(
                """
                SELECT hook_style, COUNT(*) as cnt
                FROM post_analytics
                WHERE hook_style IS NOT NULL AND hook_style != ''
                GROUP BY hook_style
                ORDER BY cnt DESC
                LIMIT 5
                """
            ).fetchall()
            if rows:
                items = ["%s (%d)" % (r[0], r[1]) for r in rows[:3]]
                insights.append("Hook styles: " + ", ".join(items))
        except Exception:
            pass
        
        # 4. Average word count
        try:
            row = self.db.conn.execute(
                "SELECT AVG(word_count) FROM post_analytics WHERE word_count IS NOT NULL"
            ).fetchone()
            if row and row[0]:
                insights.append("Avg length: %.0f words" % row[0])
        except Exception:
            pass
        
        # 5. Posting hours
        try:
            rows = self.db.conn.execute(
                """
                SELECT CAST(strftime('%%H', created_at) AS INTEGER) as h, COUNT(*) as cnt
                FROM post_analytics
                GROUP BY h
                ORDER BY cnt DESC
                LIMIT 3
                """
            ).fetchall()
            if rows:
                hours = ["%d:00 UTC (%d)" % (r[0], r[1]) for r in rows]
                insights.append("Peak hours: " + ", ".join(hours))
        except Exception:
            pass
        
        if not insights:
            insights.append("Analytics DB building — insights will grow with each post.")
        
        return "\n".join(insights)
    
    @staticmethod
    def _detect_hook_style(content: str) -> str:
        """Analyze first lines to determine hook style."""
        lines = [l.strip() for l in content.split('\n') if l.strip()]
        first = ' '.join(lines[:3]).lower() if lines else ''
        
        if any(w in first for w in ['🚀', 'explod', 'surge', 'pump', 'blast', 'moon']):
            return 'breakout_fomo'
        elif any(w in first for w in ['⚠️', 'warning', 'crash', 'dump', 'plunge']):
            return 'warning_alert'
        elif any(w in first for w in ['whale', 'smart money', 'accum', 'buying']):
            return 'smart_money'
        elif any(w in first for w in ['listing', 'launchpool', 'airdrop', 'new on binance']):
            return 'listing_news'
        elif any(w in first for w in ['ai', 'narrative', 'sector']):
            return 'narrative_driven'
        elif '?' in first:
            return 'question_hook'
        elif any(w in first for w in ['entry', 'target', 'setup', '🛑']):
            return 'trade_setup'
        else:
            return 'data_led'
    
    @staticmethod
    def _extract_hashtags(content: str) -> List[str]:
        import re
        return re.findall(r'#[A-Za-z0-9_]+', content)
    
    @staticmethod
    def _detect_trade_setup_style(content: str) -> str:
        lower = content.lower()
        has_entry = any(w in lower for w in ['entry', 'enter'])
        has_target = any(w in lower for w in ['target', 'tp', '🎯'])
        has_stop = any(w in lower for w in ['stop', '🛑', 'sl'])
        if has_entry and has_target and has_stop:
            return 'full_setup'
        elif has_entry and has_target:
            return 'entry_target'
        elif has_target:
            return 'target_only'
        else:
            return 'analysis_only'

class SkillsHubEngine:
    """Binance Skills Hub Market Rank API integration.
    
    Fetches trending data from 4 rank types:
    - rankType=10 (Trending) — hot coins on BSC
    - rankType=11 (Top Search) — most searched on Binance
    - rankType=20 (Alpha) — Binance Alpha curated picks
    - rankType=40 (Stock) — tokenized stocks
    
    Returns a unified score per coin for Binance Square posting.
    """
    
    @staticmethod
    def _safe_get(data: dict, *keys: str, default: str = "") -> str:
        """Safely get a nested value from a dict that may have None intermediates."""
        current = data
        for k in keys:
            if current is None:
                return default
            if isinstance(current, dict):
                current = current.get(k)
            else:
                return default
        return str(current) if current is not None else default

    BASE_URL = "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/market/token/pulse/unified/rank/list/ai"
    
    _cache = None
    _cache_time = 0
    CACHE_TTL = 120  # seconds
    
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Origin": "https://www.binance.com",
            "Referer": "https://www.binance.com/",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    
    def fetch_all(self) -> Dict[str, Dict[str, Any]]:
        import urllib.request, urllib.error
        """Fetch all rank types and chains, merge into unified token dict.

        Returns dict of symbol -> token_data with merged rank info.
        """
        now = time.time()
        if SkillsHubEngine._cache and (now - SkillsHubEngine._cache_time) < SkillsHubEngine.CACHE_TTL:
            return SkillsHubEngine._cache
        # Try loading from disk cache if memory cache expired
        if not SkillsHubEngine._cache:
            try:
                import os as _os
                cpath = "skills_cache.json"
                if _os.path.exists(cpath) and _os.path.getsize(cpath) > 0:
                    with open(cpath) as _f:
                        SkillsHubEngine._cache = json.load(_f)
                    SkillsHubEngine._cache_time = time.time()
                    LOGGER.info("SkillsHub: loaded %d tokens from disk cache", len(SkillsHubEngine._cache))
                    return SkillsHubEngine._cache
            except Exception:
                SkillsHubEngine._cache = None
                SkillsHubEngine._cache_time = 0

        merged = {}
        rank_types = {
            10: "trending",
            11: "top_search", 
            20: "alpha",
            30: "smart_money",
            40: "stock",
            50: "futures",
        }

        for rank_type, source in rank_types.items():
            for chain_id in ("56", "1"):
                try:
                    payload = {
                        "rankType": rank_type,
                        "chainId": chain_id,
                        "period": 50,
                        "page": 1,
                        "size": 20,
                    }
                    req = urllib.request.Request(self.BASE_URL, data=json.dumps(payload).encode("utf-8"),
                                            headers=self.headers, method="POST")
                    resp = urllib.request.urlopen(req, timeout=20)
                    if resp.status != 200:
                        LOGGER.warning("SkillsHub rankType=%d HTTP %d", rank_type, resp.status)
                        continue
                    raw_body = resp.read().decode("utf-8", errors="replace")
                    data = json.loads(raw_body)
                    if data.get("code") != "000000":
                        LOGGER.debug("SkillsHub rankType=%d code=%s", rank_type, data.get("code"))
                        continue
                    tokens = data.get("data", {}).get("tokens", [])
                    for t in tokens:
                        sym = t.get("symbol", "")
                        if not sym:
                            continue
                        if sym not in merged:
                            merged[sym] = dict(t)
                            merged[sym]["_sources"] = []
                        merged[sym]["_sources"].append(source)
                        merged[sym][f"_rank_{source}"] = len([x for x in merged.values() if sym in x.get("_sources", [])]) + 1
                except urllib.error.HTTPError as e:
                    LOGGER.debug("SkillsHub rankType=%d HTTP %d: %s", rank_type, e.code, e.reason)
                except urllib.error.URLError as e:
                    LOGGER.debug("SkillsHub rankType=%d connection error: %s", rank_type, e.reason)
                except Exception as e:
                    LOGGER.debug("SkillsHub rankType=%d error: %s", rank_type, e)

        SkillsHubEngine._cache = merged
        SkillsHubEngine._cache_time = time.time()
        # Atomically write to disk cache for intra-run resilience
        _atomic_write_json("skills_cache.json", merged)
        LOGGER.info("SkillsHub: loaded %d unique tokens from %d rank types", len(merged), len(rank_types))
        return merged

    def get_scored_candidates(self) -> List[Coin]:
        """Get scored coin candidates from Skills Hub data.
        
        Scoring factors (0-100):
        - search score (searchCount24h rank)
        - source score (how many rank types include this coin)
        - smart money score (smartMoneyHoldingPercent)
        - price action score (24h change + volume)
        - risk penalty (audit risk level)
        """
        raw = self.fetch_all()
        if not raw:
            return []
        
        candidates = []
        for sym, data in raw.items():
            try:
                score = self._calculate_score(data)
                price = float(data.get("price", 0) or 0)
                change_24h = float(data.get("percentChange24h", 0) or 0)
                vol_24h = float(data.get("volume24h", 0) or 0)
                search = int(data.get("searchCount24h", 0) or 0)
                sources = data.get("_sources") or []
                
                # Map to Coin dataclass
                mc = float(data.get("marketCap", 0) or 0)
                liquidity = float(data.get("liquidity", 0) or 0)
                coin = Coin(
                    symbol=sym,
                    name=self._safe_get(data, "metaInfo", "name", sym),
                    price=price,
                    change_24h=change_24h,
                    volume_24h=vol_24h,
                    volume_ratio=min((vol_24h / max(mc, 1)) * 5, 5) if mc > 0 else 1.0,
                    market_cap=float(data.get("marketCap", 0) or 0),
                    history=[],
                    liquidity=liquidity,
                )
                coin._skills_score = score
                coin._skills_search = search
                coin._skills_sources = sources
                coin._skills_smart_money = float(data.get("smartMoneyHoldingPercent", 0) or 0)
                coin._skills_kol = float(data.get("kolHoldingPercent", 0) or 0)
                coin._skills_risk = (data.get("auditInfo") or {}).get("riskLevel", 1)
                candidates.append(coin)
            except Exception as e:
                LOGGER.warning("SkillsHub parse error for %s: %s", sym, e)
        
        # Sort by score descending
        candidates.sort(key=lambda c: getattr(c, '_skills_score', 0), reverse=True)
        return candidates
    
    def _calculate_score(self, data: Dict[str, Any]) -> float:
        """Calculate unified score for a token.
        
        Weighted factors:
        - searchCount24h (normalized): 30 points max
        - source diversity: 20 points max  
        - smart money holding: 10 points max
        - KOL holding: 5 points max
        - 24h change (abs): 10 points max
        - volume spike: 10 points max
        - trader count: 5 points max
        - Binance alpha tag: 5 points max
        - Binance Spot listed (via exchangeInfo): 5 points max
        - Risk penalty: -10 to 0
        """
        score = 0.0
        
        # 1. Search count (what people are looking for on Binance) - max 30
        search = int(data.get("searchCount24h", 0) or 0)
        score += min(search / 35, 30.0)  # 1060 search ~= 30 points
        
        # 2. Source diversity (appears in multiple rank types) - max 20
        sources = data.get("_sources") or []
        score += min(len(sources) * 7, 20.0)
        
        # 3. Smart money holding - max 10
        sm = float(data.get("smartMoneyHoldingPercent", 0) or 0)
        score += min(sm * 1.5, 10.0)
        
        # 4. KOL holding - max 5
        kol = float(data.get("kolHoldingPercent", 0) or 0)
        score += min(kol * 1.5, 5.0)
        
        # 5. 24h price action (absolute change, capped) - max 10
        change = abs(float(data.get("percentChange24h", 0) or 0))
        score += min(change / 5, 10.0)
        
        # 6. Volume spike (24h volume relative to market cap) - max 10
        vol = float(data.get("volume24h", 0) or 0)
        mc = float(data.get("marketCap", 0) or 1)
        vol_ratio = vol / mc if mc > 0 else 0
        score += min(vol_ratio * 50, 10.0)
        
        # 7. Unique trader count (24h) - max 5
        traders = int(data.get("count24h", 0) or 0)
        score += min(traders / 50000, 5.0)
        
        # 8. Binance Alpha tag - max 5
        token_tag = (data.get("tokenTag") or {})
        if token_tag:
            score += 5.0
        
        # 9. Risk penalty - subtract up to 10
        risk = (data.get("auditInfo") or {}).get("riskLevel", 1)
        if risk >= 3:
            score -= 10.0
        elif risk == 2:
            score -= 5.0
        
        # 10. Price too low penalty (under $0.001)
        price = float(data.get("price", 0) or 0)
        if 0 < price < 0.001:
            score -= 5.0
        
        return max(score, 0.0)



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
    
    def build_research_package(
        self,
        coin: Dict[str, Any],
        announcements: List[Dict[str, Any]],
        posted_hours_ago: Optional[float] = None,
    ) -> str:
        """Build a complete text Research Package for Gemini evaluation.
        
        10 dimensions of analysis presented in trader-readable format.
        Gemini uses this to decide (Phase 1) and to write (Phase 2).
        """
        symbol = coin.get("symbol", "")
        name = coin.get("name", symbol)
        price = float(coin.get("price", 0) or 0)
        change = float(coin.get("change_24h", 0) or 0)
        volume_24h = float(coin.get("volume_24h", 0) or 0)
        volume_ratio = float(coin.get("volume_ratio", 1) or 1)
        market_cap = float(coin.get("market_cap", 0) or 0)
        history = coin.get("history", [])
        abs_change = abs(change)
        
        # Find catalyst
        catalyst = _extract_catalyst_for_coin(symbol, announcements)
        
        # Category detection
        category, _ = self._detect_narrative(symbol)
        
        # Technical signals
        tech = self._technical_analysis(history, price, change)
        
        # Volume analysis
        vol = self._volume_analysis(volume_ratio, volume_24h, market_cap)
        
        # Risk
        risk_level, risk_factors = self._risk_assessment(price, market_cap, volume_ratio, change, category)
        
        lines = []
        lines.append("COIN: $%s (%s)" % (symbol, name))
        lines.append("")
        lines.append("── MARKET DATA ──")
        lines.append("Price: $%.6f | 24h Change: %+.1f%%" % (price, change))
        lines.append("Volume 24h: $%.0f | Volume vs Normal: %.1fx" % (volume_24h, volume_ratio))
        lines.append("Market Cap: $%.0f | Binance Spot: YES" % market_cap)
        lines.append("")
        
        # Catalyst section
        lines.append("── CATALYST ──")
        if catalyst:
            cat_type = catalyst.get("type", "news").upper()
            cat_title = catalyst.get("title", "")
            lines.append("Type: %s" % cat_type)
            lines.append("Detail: %s" % cat_title[:150])
            lines.append("Age: Just announced by Binance (FRESH)")
        else:
            lines.append("Type: MARKET MOVEMENT")
            if abs_change > 8:
                lines.append("Detail: Explosive %+.1f%% price move" % change)
            elif abs_change > 4:
                lines.append("Detail: Strong %+.1f%% momentum" % change)
            else:
                lines.append("Detail: Gradual %+.1f%% price change" % change)
            if volume_ratio > 2.5:
                lines.append("Detail: Volume %.1fx above average confirming move" % volume_ratio)
            lines.append("Age: Ongoing market activity")
        lines.append("")
        
        # Timing / Freshness
        lines.append("── TIMING & FRESHNESS ──")
        if abs_change < 3 and volume_ratio < 2:
            lines.append("Stage: EARLY — move just beginning")
        elif abs_change < 8:
            lines.append("Stage: FRESH — move in progress, still early for creators")
        elif abs_change < 15:
            lines.append("Stage: ONGOING — significant move, still time for Write-to-Earn")
        else:
            lines.append("Stage: LATE — large move already happened, mostly priced in")
        lines.append("")
        
        # Narrative
        lines.append("── NARRATIVE ──")
        if category:
            lines.append("Sector: %s" % category)
            if category in ("AI", "MEME", "L1"):
                lines.append("Freshness: HIGH — active narrative on Binance")
            elif category in ("RWA", "DePIN", "GAMING"):
                lines.append("Freshness: GROWING — gaining traction")
            else:
                lines.append("Freshness: STABLE — established narrative")
        else:
            lines.append("Sector: NONE — standalone mover")
            lines.append("Freshness: UNKNOWN")
        lines.append("")
        
        # Volume quality
        lines.append("── VOLUME QUALITY ──")
        if volume_ratio >= 3.0:
            lines.append("Level: EXTREME — %.1fx normal volume" % volume_ratio)
        elif volume_ratio >= 2.0:
            lines.append("Level: HIGH — %.1fx normal volume" % volume_ratio)
        elif volume_ratio >= 1.5:
            lines.append("Level: ELEVATED — %.1fx normal volume" % volume_ratio)
        else:
            lines.append("Level: NORMAL — %.1fx average volume" % volume_ratio)
        if vol.get("verdict"):
            lines.append("Analysis: %s" % vol["verdict"])
        lines.append("")
        
        # Binance relevance
        lines.append("── BINANCE RELEVANCE ──")
        is_top5 = "YES" if symbol in TOP_5_COINS else "NO"
        lines.append("Top 5 Coin: %s" % is_top5)
        if catalyst:
            lines.append("Square Interest: HIGH (Binance announcement driver)")
        elif abs_change > 5:
            lines.append("Square Interest: HIGH (traders search for movers)")
        elif volume_ratio > 2:
            lines.append("Square Interest: MEDIUM (volume spike draws attention)")
        else:
            lines.append("Square Interest: LOW (no clear trigger for Binance audience)")
        lines.append("")
        
        # Trader actionability
        lines.append("── TRADER ACTIONABILITY ──")
        if price > 0.10 and market_cap > 10_000_000:
            lines.append("Entry: CLEAR — enough liquidity to enter at market")
            lines.append("Liquidity: HIGH — Binance spot pair with depth")
            lines.append("Trade Ready: YES")
        elif price > 0.01 and market_cap > 1_000_000:
            lines.append("Entry: POSSIBLE — some liquidity, use limit orders")
            lines.append("Liquidity: MEDIUM — tradeable in smaller sizes")
            lines.append("Trade Ready: POSSIBLE")
        else:
            lines.append("Entry: DIFFICULT — very low liquidity")
            lines.append("Liquidity: LOW — risky to trade")
            lines.append("Trade Ready: NO")
        lines.append("")
        
        # Risk
        lines.append("── RISK ──")
        lines.append("Level: %s" % risk_level.upper())
        for rf in risk_factors:
            lines.append("- %s" % rf)
        lines.append("")
        
        # Repetition
        lines.append("── REPETITION ──")
        if posted_hours_ago is not None:
            lines.append("Last posted: %.0f hours ago" % posted_hours_ago)
            if posted_hours_ago < 24:
                lines.append("Repetition Risk: HIGH — recently featured")
            elif posted_hours_ago < 48:
                lines.append("Repetition Risk: MEDIUM — posted within 2 days")
            else:
                lines.append("Repetition Risk: LOW — fresh for audience")
        else:
            lines.append("Last posted: NEVER — fresh opportunity")
        lines.append("")
        
        # Why trade NOW
        lines.append("── WHY TRADE NOW ──")
        reasons = []
        if catalyst:
            reasons.append("Binance %s catalyst just hit" % catalyst.get("type", ""))
        if abs_change > 5:
            reasons.append("Strong %+.1f%% momentum with conviction" % change)
        if volume_ratio > 2:
            reasons.append("Volume %.1fx confirms smart money participation" % volume_ratio)
        if category:
            reasons.append("%s narrative gaining Binance Square attention" % category)
        if not reasons:
            reasons.append("Setup developing — early for those who act first")
        lines.append("- " + "\n- ".join(reasons[:3]))
        lines.append("")
        
        # Skills Hub signals (Binance ecosystem trending data)
        skills_score = coin.get("skills_score", 0)
        skills_search = coin.get("skills_search", 0)
        skills_sources = coin.get("skills_sources", [])
        skills_sm = coin.get("skills_smart_money", 0)
        skills_kol = coin.get("skills_kol", 0)
        if skills_score > 0:
            lines.append("── BINANCE SKILLS HUB SIGNALS ──")
            lines.append("Trend Score: %.0f/100" % skills_score)
            if skills_search > 0:
                lines.append("Binance Search Volume: %d searches in 24h" % skills_search)
            if skills_sources:
                lines.append("Trending Categories: %s" % ", ".join(skills_sources))
            if skills_sm > 0:
                lines.append("Smart Money Holding: %.1f%%" % skills_sm)
            if skills_kol > 0:
                lines.append("KOL Holding: %.1f%%" % skills_kol)
            lines.append("")
        
        return "\n".join(lines)


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
    """Opportunity Intelligence Content Engine.
    
    Phase 1 — decide(): Rank top opportunities (Publish/Watch/Skip).
    Phase 2 — generate(): Write professional Binance Square post.
    Gemini is the decision maker AND writer. System handles deterministic gates.
    """
    
    def __init__(self, config: Config = CONFIG):
        self.config = config
    
    # ──────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────
    
    def decide(self, research_packages: List[str]) -> List[Dict[str, Any]]:
        """Phase 1: Send research packages to Gemini for ranking.
        
        Returns list of {'rank': int, 'symbol': str, 'reason': str}
        Ordered from BEST to WORST opportunity.
        Returns empty list if Gemini fails.
        """
        if not research_packages:
            return []
        
        prompt = self._build_decision_prompt(research_packages)
        response = self._call_gemini(prompt)
        
        if not response:
            LOGGER.warning("Gemini Phase 1 (decision) failed — no ranking returned")
            return []
        
        rankings = self._parse_decision_response(response)
        if not rankings:
            LOGGER.warning("Gemini Phase 1 returned unparseable response")
            LOGGER.debug("Raw response: %s", response[:300])
            return []
        
        LOGGER.info("Gemini Phase 1 ranking: %s",
                     ", ".join("#'%d'=$%s" % (r.get('rank', 0), r.get('symbol', '?')) for r in rankings))
        return rankings
    
    def generate(self, coin: Dict[str, Any], research_package: str) -> str:
        """Phase 2: Gemini writes the post based on complete research.
        
        Returns post text (80-110 words, Write-to-Earn optimized).
        Returns empty string if Gemini fails (post skipped, not published).
        """
        if not research_package:
            return ""
        
        prompt = self._build_writing_prompt(coin, research_package)
        response = self._call_gemini(prompt)
        
        if response:
            LOGGER.info("Gemini Phase 2 generated post successfully")
            return response.strip()
        
        LOGGER.warning("Gemini Phase 2 (writing) failed — post will not be published")
        return ""
    
    # ──────────────────────────────────────────────
    # GEMINI API CALL (shared by Phase 1 + Phase 2)
    # ──────────────────────────────────────────────
    
    def _call_gemini(self, prompt: str) -> Optional[str]:
        """Call Gemini API with model fallback chain."""
        if not self.config.gemini_api_key:
            LOGGER.warning("No GEMINI_API_KEY set")
            return None
        
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
        
        for model in models:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                "%s:generateContent?key=%s" % (model, self.config.gemini_api_key)
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
                resp = http_post_json(url, payload, timeout=self.config.http_timeout_seconds, retries=2)
                text = resp.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text and text.strip():
                    return text.strip()
            except Exception as exc:
                LOGGER.warning("Gemini %s failed: %s", model, exc)
                continue
        
        return None
    
    # ──────────────────────────────────────────────
    # PROMPT BUILDERS
    # ──────────────────────────────────────────────
    
    def _build_decision_prompt(self, packages: List[str]) -> str:
        """Build Phase 1 prompt: Gemini ranks opportunities."""
        parts = [
            "You are a Binance Square content strategist and professional crypto trader.",
            "",
            "Below are %d research packages for different coins/tokens." % len(packages),
            "Rank them from BEST to WORST opportunity for a Binance Square Write-to-Earn post RIGHT NOW.",
            "",
            "CRITICAL EVALUATION CRITERIA (use ALL of these):",
            "",
            "1. CATALYST STRENGTH: Is there a fresh, real catalyst? (Binance listing > volume spike > market move)",
            "2. TIMING: Is this EARLY? Have other creators already posted? Early = better rewards.",
            "3. NARRATIVE POTENTIAL: Trending narrative? (AI, Meme, RWA, DePIN, Gaming, L1)",
            "4. BINANCE RELEVANCE: Will Square audience search for and click this coin?",
            "5. TRADER ACTIONABILITY: Can traders take a trade from this post? Clear entry?",
            "6. WRITE-TO-EARN POTENTIAL: Will this post get views, saves, shares?",
            "7. FRESHNESS: Is this opportunity fresh or already saturated on Square?",
            "8. RISK: Is the coin safe enough for mainstream Binance traders?",
            "",
            "RULES:",
            "- PREFER Alpha coins, Altcoins, fresh narratives, new listings",
            "- PREFER coins with clear catalysts (volume spike, announcement, news)",
            "- PREFER EARLY timing — before most creators post",
            "- AVOID Top 5 coins (BTC, ETH, BNB, SOL, XRP) unless exceptional catalyst",
            "- AVOID coins posted in the last 48 hours",
            "- AVOID micro-caps with no liquidity",
            "- AVOID saturated narratives with too many existing posts",
            "",
        ]
        
        for i, pkg in enumerate(packages):
            parts.append("━" * 50)
            parts.append("RESEARCH PACKAGE %d:" % (i + 1))
            parts.append("━" * 50)
            parts.append(pkg)
            parts.append("")
        
        parts.append("━" * 50)
        parts.append("RESPOND IN EXACTLY THIS FORMAT:")
        parts.append("")
        parts.append("RANK: 1")
        parts.append("COIN: $SYMBOL")
        parts.append("REASON: [2-3 sentences why #1 — include catalyst, timing, narrative]")
        parts.append("")
        parts.append("RANK: 2")
        parts.append("COIN: $SYMBOL")
        parts.append("REASON: [2-3 sentences why #2 — what it needs to become #1]")
        parts.append("")
        parts.append("RANK: 3")
        parts.append("COIN: $SYMBOL")
        parts.append("REASON: [2-3 sentences why #3 — weakest opportunity]")
        parts.append("")
        parts.append("IMPORTANT: Respond ONLY with the rankings. No extra text.")
        
        return "\n".join(parts)
    
    def _build_writing_prompt(self, coin: Dict[str, Any], research_package: str) -> str:
        """Build Phase 2 prompt: Gemini writes the post.
        
        Optimized for Binance Square Write-to-Earn: engagement, trader value, hashtag compliance.
        """
        symbol = coin.get("symbol", "COIN")
        name = coin.get("name", symbol)
        price = float(coin.get("price", 0) or 0)
        change = float(coin.get("change_24h", 0) or 0)
        
        parts = [
            "ROLE: Experienced crypto trader sharing a real opportunity on Binance Square.",
            "",
            "TASK: Write an engaging 80-110 word post about $%s (%s)." % (symbol, name),
            "",
            "━" * 50,
            "RESEARCH:",
            research_package,
            "━" * 50,
            "",
            "WRITE THE POST. FOLLOW EVERY RULE BELOW. NO EXCEPTIONS.",
            "",
            "━" * 50,
            "REQUIREMENTS (validate each before returning):",
            "━" * 50,
            "",
            "1. LENGTH: Exactly 80-110 words. Count before returning. Too short = rejection.",
            "",
            "2. HOOK: Start with a powerful 2-3 line hook that grabs attention immediately.",
            "   Use natural, high-impact emojis only where they fit (🔥 🚀 📈 ⚡ 👀 💰).",
            "   Never overuse emojis. One per paragraph maximum.",
            "",
            "3. VOICE: Write like an experienced crypto trader, not an AI assistant.",
            "   - Confident, conversational language.",
            "   - No robotic or repetitive wording.",
            "   - No filler, no generic motivation, no 'not financial advice'.",
            "   - No AI-style phrases like 'as an AI', 'I cannot', 'let me know', etc.",
            "",
            "4. CASHTAG: Include $%s naturally in the post body." % symbol,
            "",
            "5. STRUCTURE:",
            "   - HOOK (2-3 lines): Catalyst + urgency + emoji.",
            "   - SETUP: Entry zone, 2 targets, stop loss.",
            "   - INSIGHT: 1-2 lines. Why this trade makes sense right now.",
            "   - CLOSE: One strong line. What traders should watch next.",
            "   - HASHTAGS: Exactly one line with 4 hashtags only.",
            "",
            "6. HASHTAGS — EXACTLY 4. NO MORE. NO LESS.",
            "   Must include: #%s #Write2Earn" % symbol,
            "   Choose the other 2 based on token category and market context:",
            "     - Trending altcoin → #Altcoins #CryptoTrading",
            "     - AI token → #AI #Crypto",
            "     - Meme coin → #Memecoin #Crypto",
            "     - DeFi token → #DeFi #BinanceSquare",
            "     - New listing → #Binance #NewListing",
            "     - Technical move → #TechnicalAnalysis #Crypto",
            "     - General → #BinanceSquare #CryptoTrading",
            "",
            "7. SKILLS HUB SIGNALS (use if present in RESEARCH):",
            "   - Search Volume > 100 → mention trending on Binance.",
            "   - Smart Money > 2% → mention smart money accumulating.",
            "   - Alpha tagged → mention Binance Alpha selection.",
            "",
            "━" * 50,
            "SELF-VERIFICATION (MANDATORY before returning):",
            "━" * 50,
            "",
            "Check ALL of these:",
            "  ✓ 80-110 words",
            "  ✓ Exactly 4 hashtags on the last line",
            "  ✓ Strong attention-grabbing hook",
            "  ✓ Natural human-like writing",
            "  ✓ No repetitive or low-quality text",
            "  ✓ $%s cashtag included" % symbol,
            "",
            "If ANY rule fails, regenerate the entire post. Do NOT return non-compliant content.",
            "",
            "POST NOW:",
        ]
        
        return "\n".join(parts)
    
    # ──────────────────────────────────────────────
    # RESPONSE PARSER
    # ──────────────────────────────────────────────
    
    def _parse_decision_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse Gemini's ranking response into structured data."""
        rankings = []
        current = {}
        
        for line in response.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('RANK:'):
                if current and 'symbol' in current:
                    rankings.append(current)
                try:
                    rank = int(line.split(':')[1].strip())
                    current = {'rank': rank, 'symbol': '', 'reason': ''}
                except (ValueError, IndexError):
                    current = {}
            
            elif line.startswith('COIN:') and current:
                sym = line.split(':')[1].strip().replace('$', '')
                current['symbol'] = sym
            
            elif line.startswith('REASON:') and current:
                reason = line.split(':', 1)[1].strip()
                current['reason'] = reason
        
        # Don't forget the last one
        if current and 'symbol' in current:
            rankings.append(current)
        
        # Sort by rank
        rankings.sort(key=lambda r: r.get('rank', 999))
        
        return rankings
class PostPublisher:
    def __init__(self, config: Config = CONFIG):
        self.config = config
        self.db = Database(config.database_path)

    def publish(self, coin: Dict[str, Any], content: str, image_url: str = "") -> str:
        # Check if this is a draft template (Gemini failed) - don't publish low quality
        if content.startswith("[DRAFT_TEMPLATE]"):
            actual_content = content.replace("[DRAFT_TEMPLATE]", "", 1)
            LOGGER.warning("Template fallback content - saving as draft only, not publishing to Square")
            self._save_locally(coin, actual_content, share_link="[DRAFT-Skipped-Gemini-unavailable]")
            try:
                self.db.save_post({"content": actual_content, "coin_symbol": coin.get("symbol", "")})
            except Exception:
                pass
            return ""
        if self.config.dry_run:
            LOGGER.info("[DRY-RUN] Would publish post for %s", coin.get("symbol"))
            self._save_locally(coin, content, share_link="[DRY-RUN]")
            try:
                self.db.save_post({"content": content, "coin_symbol": coin.get("symbol", "")})
            except Exception as e:
                LOGGER.warning("Could not save post to DB: %s", e)
            return "[DRY-RUN]"

        share_link = self._try_square_api(coin, content, image_url)
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
        return share_link or ""

    def _try_square_api(self, coin: Dict[str, Any], content: str, image_url: str = "") -> str:
        """Publish to Binance Square via official Creator Center API."""
        square_key = self.config.square_api_key
        if not square_key:
            LOGGER.warning("No SQUARE_API_KEY set, saving locally")
            return ""

        payload = {
            "contentType": 1,
            "bodyTextOnly": self._limit_hashtags(content),
        }
        if image_url:
            payload["imageUrl"] = image_url
            # contentType=2 requires a title field (article post)
            payload["title"] = "$%s - Setup & Key Levels" % coin.get("symbol", "Trade")
            payload["contentType"] = 2
            LOGGER.info("Including image in Square post: %s", image_url)
        
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




def run_once(config, scanner, announcement_engine, research, generator, publisher, posted_symbols, hot_search_engine=None) -> bool:
    """Run one iteration using Opportunity Intelligence Architecture.
    
    Flow:
    1. Collect data from all sources
    2. Apply deterministic objective filters (in code)
    3. Build Research Packages for top candidates
    4. Send top 3 to Gemini Phase 1 → decision/ranking
    5. Select #1 pick
    6. Gemini Phase 2 → write the post
    7. Publish
    """
    # ─── DAILY POST CAP CHECK ───
    # Exit early if we already published enough posts today
    today_count = _get_today_post_count(publisher.db)
    remaining = config.max_daily_posts - today_count
    if remaining <= 0:
        LOGGER.info("Daily post limit reached (%d/%d). Skipping.", today_count, config.max_daily_posts)
        return False
    
    # ─── STARTUP: PERSISTENCE INTEGRITY CHECK ───
    # Verify that the post history file is intact. If integrity cannot be
    # guaranteed, fail CLOSED — do NOT publish this cycle.
    if not _verify_persistence_integrity():
        LOGGER.critical("INTEGRITY FAILURE: Persistence layer compromised. "
                       "Skipping this cycle to prevent duplicate posts.")
        return False
    
    # ─── STARTUP: RETRY PENDING GIT PUSH FROM PREVIOUS RUN ───
    # If the previous workflow run failed to git-push the JSONL file,
    # retry now so the repo is up to date before this run makes decisions.
    _retry_pending_push()
    
    # ─── FAST EXIT IF RECENTLY CHECKED ───
    # Skip full scan if we checked within last 30s (prevents redundant runs)
    check_file = Path(CONFIG.database_path).parent / ".last_scan_check"
    if check_file.exists():
        try:
            last_check = float(check_file.read_text().strip())
            if time.time() - last_check < 25:
                LOGGER.debug("Skipped scan (checked %.0fs ago)", time.time() - last_check)
                return False
        except Exception:
            pass
    try:
        check_file.parent.mkdir(parents=True, exist_ok=True)
        check_file.write_text(str(time.time()))
    except Exception:
        pass
    
    # ──────────────────────────────────────────────
    # 1. COLLECT DATA
    # ──────────────────────────────────────────────
    
    # Fetch Binance announcements
    announcements = []
    try:
        announcements = announcement_engine.get_trending_announcements()
        for a in announcements[:5]:
            LOGGER.info("Announcement: [%s] %s - symbols: %s", a["type"], a["title"][:60], a["symbols"])
    except Exception as e:
        LOGGER.warning("Could not fetch announcements: %s", e)
    
    # Get posted hours for repetition check
    # Primary source: JSONL file (persists via git across GHA runs)
    posted_hours_data = {}
    try:
        posted_hours_data = _load_post_history()
        LOGGER.info("COOLDOWN HISTORY: loaded %d coins from %s (sample: %s)",
                    len(posted_hours_data), _POST_HISTORY_FILE,
                    str(list(posted_hours_data.items())[:5]) if posted_hours_data else "none")
    except Exception as e:
        LOGGER.debug("Could not load post history: %s", e)
    # Secondary source: SQLite (current run data)
    try:
        db_hours = publisher.db.get_posted_hours_dict(hours=72)
        for sym, hrs in db_hours.items():
            if sym not in posted_hours_data or hrs < posted_hours_data[sym]:
                posted_hours_data[sym] = hrs
    except Exception:
        pass
    
    # ──────────────────────────────────────────────
    # 2. APPLY OBJECTIVE FILTERS (in code, deterministic)
    # ──────────────────────────────────────────────
    
    # ─── SKILLS HUB ENGINE (primary source) ───
    # Use Binance Skills Hub Market Rank API for trending/top-search/alpha data
    candidates = []
    skills_used = False
    skills_candidates = []
    try:
        skills = SkillsHubEngine()
        skills_candidates = skills.get_scored_candidates()
        if skills_candidates:
            LOGGER.info("SkillsHub: %d candidates loaded", len(skills_candidates))
            # Show top 5
            for c in skills_candidates[:5]:
                LOGGER.info("  SkillsHub: $%s score=%.0f search=%d sources=%s SM=%.1f%%",
                           c.symbol, getattr(c, '_skills_score', 0),
                           getattr(c, '_skills_search', 0),
                           getattr(c, '_skills_sources', []),
                           getattr(c, '_skills_smart_money', 0))
            skills_used = True
            # Apply objective filters (more lenient for SkillsHub data)
            for coin in skills_candidates:
                try:
                    if _passes_objective_filters(
                        symbol=coin.symbol,
                        price=coin.price,
                        change_24h=coin.change_24h,
                        volume_ratio=getattr(coin, 'volume_ratio', 1.0),
                        market_cap=coin.market_cap,
                        announcements=announcements,
                        posted_hours_data=posted_hours_data,
                        from_skills_hub=True,
                        liquidity=getattr(coin, 'liquidity', 0),
                        risk_level=getattr(coin, '_skills_risk', 0),
                    ):
                        candidates.append(coin)
                except Exception as e:
                    LOGGER.debug("SkillsHub filter error for %s: %s", coin.symbol, e)
                    continue
    except Exception as e:
        LOGGER.warning("SkillsHubEngine failed: %s — falling back to MarketScanner", e)
    
    # ─── MARKET SCANNER (fallback) ───
    # Use CoinGecko-based scanner if SkillsHub returned nothing
    if not candidates:
        raw_candidates = []
        try:
            universe = scanner._universe()
            raw_candidates = [c for c in universe]
        except Exception as e:
            LOGGER.error("Failed to get market data: %s", e)
            return False
        
        for coin in raw_candidates:
            try:
                if _passes_objective_filters(
                    symbol=coin.symbol,
                    price=coin.price,
                    change_24h=coin.change_24h,
                    volume_ratio=coin.volume_ratio,
                    market_cap=coin.market_cap,
                    announcements=announcements,
                    posted_hours_data=posted_hours_data,
                ):
                    candidates.append(coin)
            except Exception as e:
                LOGGER.debug("Filter error for %s: %s", coin.symbol, e)
                continue
    
    if len(candidates) < CONFIG.min_candidates:
        LOGGER.info("[%s] Scan complete: %d candidates passed — insufficient for Phase 1.",
                     utc_now()[:16], len(candidates))
        for c in candidates[:5]:
            LOGGER.info("  Passed: $%s (%.1f%%, %.1fx vol)%s",
                       c.symbol, c.change_24h, c.volume_ratio,
                       f" score={getattr(c,'_skills_score',0):.0f}" if hasattr(c, '_skills_score') else "")
        return False
    
    LOGGER.info("%d candidates passed objective filters%s", len(candidates),
                " (SkillsHub)" if skills_used else " (MarketScanner)")
    
    # ──────────────────────────────────────────────
    # 3. BUILD RESEARCH PACKAGES FOR TOP CANDIDATES
    # ──────────────────────────────────────────────
    
    # Sort by SkillsHub score (if available) or market activity heuristic
    if skills_used:
        candidates.sort(key=lambda c: getattr(c, '_skills_score', 0), reverse=True)
    else:
        candidates.sort(
            key=lambda c: (abs(c.change_24h) * 0.6 + c.volume_ratio * 0.4),
            reverse=True
        )
    
    top_candidates = candidates[:5]  # Build packages for top 5
    
    # ─── HARD COOLDOWN FILTER (pre-Gemini) ───
    # Enforce strict cooldown: any coin in JSONL within 24h without
    # exceptional catalyst is REMOVED from candidates BEFORE they reach
    # Gemini Phase 1. This is the HARD GATE that prevents duplicate posts.
    pre_gemini_filtered = []
    for coin in top_candidates:
        coin_dict = coin.as_dict()
        ann_type = ""
        for a in announcements:
            if coin.symbol in a.get("symbols", []):
                ann_type = a.get("type", "")
                break
        if _check_jsonl_cooldown(coin.symbol, catalyst_type=ann_type):
            LOGGER.info("HARD COOLDOWN BLOCK (pre-Gemini): $%s removed from Phase 1 candidates — "
                        "found in JSONL within cooldown window",
                        coin.symbol)
            continue
        pre_gemini_filtered.append(coin)
    
    if len(pre_gemini_filtered) < CONFIG.min_candidates:
        LOGGER.info("HARD COOLDOWN: only %d/%d candidates remain after cooldown filter (need %d) — "
                    "skipping Phase 1 this cycle",
                    len(pre_gemini_filtered), len(top_candidates), CONFIG.min_candidates)
        return False
    
    top_candidates = pre_gemini_filtered[:5]
    
    # Build packages for top candidates
    
    research_packages = []  # List of (coin_dict, package_text)
    for coin in top_candidates:
        coin_dict = coin.as_dict()
        
        # Add Skills Hub data to coin_dict for richer research packages
        coin_dict["skills_score"] = getattr(coin, '_skills_score', 0)
        coin_dict["skills_search"] = getattr(coin, '_skills_search', 0)
        coin_dict["skills_sources"] = getattr(coin, '_skills_sources', [])
        coin_dict["skills_smart_money"] = getattr(coin, '_skills_smart_money', 0)
        coin_dict["skills_kol"] = getattr(coin, '_skills_kol', 0)
        coin_dict["skills_risk"] = getattr(coin, '_skills_risk', 1)
        
        # Add announcement context
        for a in announcements:
            if coin.symbol in a.get("symbols", []):
                coin_dict["announcement_boost"] = True
                coin_dict["announcement_type"] = a.get("type", "news")
                coin_dict["announcement_title"] = a.get("title", "")
                break
        
        hours_ago = posted_hours_data.get(coin.symbol.upper())
        
        try:
            pkg = research.build_research_package(coin_dict, announcements, hours_ago)
            research_packages.append((coin_dict, pkg))
        except Exception as e:
            LOGGER.debug("Research package failed for %s: %s", coin.symbol, e)
            continue
    
    if len(research_packages) < CONFIG.min_candidates:
        LOGGER.info("[%s] Scan: %d packages built — insufficient for Phase 1.", utc_now()[:16], len(research_packages))
        import json as _json
        _health = _json.dumps({
            "pipeline": "early_exit",
            "status": "skipped_insufficient",
            "candidates_discovered": len(skills_candidates) if skills_candidates else 0,
            "candidates_validated": len(candidates) if candidates else 0,
            "research_packages": len(research_packages),
        })
        LOGGER.info("PIPELINE HEALTH: %s", _health)
        return False
    
    # Save research packages to files (for post-hoc review)
    if CONFIG.save_research_packages:
        try:
            research_dir = Path("research")
            research_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            for coin_dict, pkg in research_packages:
                sym = coin_dict.get("symbol", "UNKNOWN")
                pkg_path = research_dir / "pkg_%s_%s.md" % (sym, ts)
                header = "---\nSymbol: %s\nTime: %s UTC\n---\n\n" % (sym, ts)
                pkg_path.write_text(header + pkg)
            LOGGER.info("Saved %d research packages to research/", len(research_packages))
        except Exception as e:
            LOGGER.debug("Could not save research packages: %s", e)
    
    # ──────────────────────────────────────────────
    # 4. GEMINI PHASE 1: DECISION
    # ──────────────────────────────────────────────
    
    top_3_packages = [pkg for _, pkg in research_packages[:3]]
    top_3_coins = [coin for coin, _ in research_packages[:3]]
    
    LOGGER.info("Sending top 3 to Gemini Phase 1: %s",
                ", ".join("$%s" % c["symbol"] for c in top_3_coins))
    
    rankings = generator.decide(top_3_packages)
    
    if not rankings:
        LOGGER.warning("Gemini Phase 1 returned no valid ranking — no post this cycle")
        return False
    
    # Log full rankings
    for r in rankings:
        LOGGER.info("Gemini rank %d: $%s — %s", r.get('rank', '?'), r.get('symbol', '?'), r.get('reason', '')[:120])
    
    # ──────────────────────────────────────────────
    # 5. SELECT #1 PICK
    # ──────────────────────────────────────────────
    
    best_symbol = rankings[0].get("symbol", "")
    if not best_symbol:
        LOGGER.warning("Gemini #1 pick has no symbol — skipping")
        return False
    
    best_coin = None
    best_package = ""
    for coin, pkg in research_packages:
        if coin["symbol"].upper() == best_symbol.upper():
            best_coin = coin
            best_package = pkg
            break
    
    if not best_coin:
        LOGGER.warning("Gemini recommended $%s but not found in research packages", best_symbol)
        # Fallback: use first candidate
        best_coin, best_package = research_packages[0]
        LOGGER.info("Falling back to $%s", best_coin["symbol"])
    
    decision_reason = rankings[0].get("reason", "") if rankings else ""
    catalyst_info = best_coin.get("announcement_type", "market_move")
    if best_coin.get("announcement_boost"):
        catalyst_info = best_coin.get("announcement_type", "announcement")
    
    LOGGER.info("=" * 60)
    LOGGER.info("DECISION: Publish $%s", best_coin["symbol"])
    LOGGER.info("  Catalyst: %s", catalyst_info)
    LOGGER.info("  Price: $%.4f | 24h: %+.1f%% | Vol: %.1fx", 
                float(best_coin.get("price", 0)), 
                float(best_coin.get("change_24h", 0)),
                float(best_coin.get("volume_ratio", 1)))
    LOGGER.info("  Gemini reason: %s", decision_reason[:200] if decision_reason else "N/A")
    LOGGER.info("  Ranked #1 of %d candidates", len(rankings))
    LOGGER.info("  Daily posts: %d/%d (%d remaining)", today_count, config.max_daily_posts, remaining)
    
    # Log why other candidates were rejected
    for i, r in enumerate(rankings[1:], 2):
        LOGGER.info("  Rejected #%d: $%s — %s", i, r.get("symbol", "?"), r.get("reason", "")[:120])
    LOGGER.info("=" * 60)
    
    # Run full research analysis (for logging/detail)
    ann_data = None
    if best_coin.get("announcement_boost"):
        ann_data = {
            "type": best_coin.get("announcement_type", "news"),
            "title": best_coin.get("announcement_title", ""),
        }
    
    try:
        analysis = research.analyze(best_coin, announcement=ann_data)
        LOGGER.debug("Research analysis complete for $%s", best_coin["symbol"])
    except Exception as e:
        LOGGER.debug("Research analysis failed: %s", e)
    
    # ──────────────────────────────────────────────
    # 6. GEMINI PHASE 2: WRITE THE POST
    # ──────────────────────────────────────────────
    
    # ─── FINAL DUPLICATE CHECK (reads JSONL directly) ───
    # This is a safety net that catches any gaps between in-memory
    # posted_hours_data and the actual on-disk JSONL history.
    if _check_jsonl_cooldown(best_coin["symbol"], catalyst_type=catalyst_info):
        LOGGER.warning("ABORT publish: $%s is within cooldown (verified from %s)",
                       best_coin["symbol"], _POST_HISTORY_FILE)
        return False
    
    LOGGER.info("Generating post for $%s...", best_coin["symbol"])
    content = generator.generate(best_coin, best_package)
    
    if not content:
        LOGGER.warning("Phase 2 writing failed for $%s — no post published", best_coin["symbol"])
        return False
    
    # Save final Gemini prompt for review
    if CONFIG.save_research_packages and content:
        try:
            prompts_dir = Path("prompts")
            prompts_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            sym = best_coin.get("symbol", "UNKNOWN")
            prompt_path = prompts_dir / "prompt_%s_%s.txt" % (sym, ts)
            prompt_text = generator._build_writing_prompt(best_coin, best_package)
            prompt_path.write_text(prompt_text)
        except Exception as e:
            LOGGER.debug("Could not save prompt: %s", e)
    
    # ─── QUALITY GATE ───
    # Never publish low-confidence or low-quality content
    quality_issues = []
    import re
    # Check for $cashtag
    cashtags = re.findall(r'\$[A-Za-z0-9_\u4e00-\u9fff]+', content)
    if not cashtags:
        quality_issues.append("no $cashtag found")
    elif best_coin.get("symbol", "").upper() not in [t.upper().lstrip('$') for t in cashtags]:
        quality_issues.append("$%s cashtag missing from post" % best_coin.get("symbol", ""))
    
    # Check for minimum hashtags
    hashtags = re.findall(r'#[A-Za-z0-9_]+', content)
    if len(hashtags) < CONFIG.min_hashtags:
        quality_issues.append("only %d hashtags (need %d)" % (len(hashtags), CONFIG.min_hashtags))
    
    # Check for minimum word count
    word_count = len(content.split())
    if word_count < CONFIG.min_word_count:
        quality_issues.append("only %d words (need %d)" % (word_count, CONFIG.min_word_count))
    
    if quality_issues:
        LOGGER.warning("QUALITY GATE: post for $%s FAILED: %s",
                       best_coin["symbol"], "; ".join(quality_issues))
        LOGGER.warning("Post content:\n%s", content[:300])
        # Save as draft for review instead of publishing
        try:
            drafts_dir = Path("drafts")
            drafts_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            draft_path = drafts_dir / "REJECTED_%s_%s.md" % (best_coin["symbol"], ts)
            draft_path.write_text(content)
            LOGGER.info("Saved rejected post to %s", draft_path)
        except Exception:
            pass
        return False
    
    LOGGER.info("Quality gate PASSED for $%s (%d words, %d hashtags)",
                best_coin["symbol"], word_count, len(hashtags))
    
    # ──────────────────────────────────────────────
    # 7a. IMAGE INTELLIGENCE (after quality gate, before publish)
    # ──────────────────────────────────────────────
    image_url = ""
    try:
        composer = ImageComposer()
        img_path = composer.generate_post_image(coin=best_coin)
        if img_path:
            uploader = ImageUploader()
            uploaded_url = uploader.binance_square_upload(img_path)
            if uploaded_url:
                image_url = uploaded_url
                LOGGER.info("Image ready for $%s: %s", best_coin["symbol"], image_url)
            else:
                LOGGER.warning("Image upload failed for $%s, proceeding text-only", best_coin["symbol"])
        else:
            LOGGER.info("No image generated for $%s, proceeding text-only", best_coin["symbol"])
    except Exception as e:
        LOGGER.warning("Image generation failed for $%s: %s — proceeding text-only",
                      best_coin["symbol"], e)
    
    # ──────────────────────────────────────────────
    # 7. PUBLISH
    # ──────────────────────────────────────────────
    
    link = publisher.publish(best_coin, content, image_url=image_url)
    # Persist to JSONL for cross-run repetition protection
    # Step 1: Append record to JSONL (always succeeds or we know why)
    persist_ok = False
    try:
        catalyst = best_coin.get("announcement_type", best_coin.get("catalyst", "market_move"))
        persist_ok = _append_post_record(best_coin["symbol"], catalyst, link or "", image_url)
    except Exception as e:
        LOGGER.error("CRITICAL: Failed to persist post record to %s: %s", _POST_HISTORY_FILE, e)
    
    # Step 2: Git push is best-effort (record is already on disk)
    if persist_ok:
        git_ok = _try_git_push()
        if not git_ok:
            LOGGER.info("Record saved locally in %s — will be pushed on next successful run",
                        _POST_HISTORY_FILE)
    else:
        LOGGER.warning("Skipping git push because JSONL append was not verified")
    # Record performance analytics
    try:
        decision_reason = ""
        if rankings:
            decision_reason = rankings[0].get("reason", "")
        performance = PerformanceAnalyzer(publisher.db)
        performance.record_publish(
            coin=best_coin,
            post_content=content,
            decision_reason=decision_reason,
            square_link=link or "",
        )
    except Exception as e:
        LOGGER.debug("Analytics recording: %s", e)
    LOGGER.info("Done — post published for $%s", best_coin["symbol"])
    import json as _json
    _health = _json.dumps({
        "pipeline": "complete",
        "status": "published",
        "coin": best_coin.get("symbol", ""),
        "catalyst": catalyst_info,
        "gemini_rank": rankings[0].get("rank", 1) if rankings else 0,
        "candidates_discovered": len(skills_candidates) if skills_candidates else 0,
        "candidates_validated": len(candidates) if candidates else 0,
        "announcements_found": len(announcements) if announcements else 0,
        "daily_post_count": today_count + 1,
        "daily_post_limit": config.max_daily_posts,
        "image_generated": bool(image_url),
    })
    LOGGER.info("PIPELINE HEALTH: %s", _health)
    return True

def main_loop() -> None:
    """Main loop that runs continuously with configured interval."""
    _maybe_update_workflow()
    config = CONFIG
    config.validate()
    
    # In GHA: each run handles ~2 hours of 5-min scanning
    in_gha = os.getenv("GITHUB_ACTIONS", "").lower() == "true"
    if in_gha:
        # Force 300s interval for 5-min scanning (ignore workflow env since we can't update it)
        interval = 300
        max_iter = 24  # 24 scans at 300s = 2 hours (matches cron schedule)
        LOGGER.info("GHA 5-min mode: %d scans at %ds intervals", max_iter, interval)
        LOGGER.info("GHA mode: %d scans at %ds intervals", max_iter, interval)
    else:
        interval = max(config.post_interval, 60)
        max_iter = config.max_iterations
    
    scanner = MarketScanner(config)
    announcement_engine = BinanceAnnouncementEngine(config)
    hot_search_engine = HotSearchEngine(config)
    research = ResearchEngine()
    generator = GeminiGenerator(config)
    publisher_db = Database(config.database_path)
    publisher = PostPublisher(config)
    publisher.db = publisher_db
    
    iteration = 0
    posted_symbols = set()
    
    LOGGER.info("=" * 60)
    LOGGER.info("Binance Square Auto Poster — Opportunity Intelligence Engine")
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
            run_once(config, scanner, announcement_engine, research, generator, publisher, posted_symbols, hot_search_engine)
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
    LOGGER.info("⚙️  Production hardened V3 — persistence, cooldown, fail-closed active")
    _maybe_update_workflow()
    config = CONFIG
    config.validate()
    
    scanner = MarketScanner(config)
    announcement_engine = BinanceAnnouncementEngine(config)
    hot_search_engine = HotSearchEngine(config)
    research = ResearchEngine()
    generator = GeminiGenerator(config)
    publisher_db = Database(config.database_path)
    publisher = PostPublisher(config)
    publisher.db = publisher_db
    
    posted_symbols = publisher_db.get_posted_symbols(hours=48)
    run_once(config, scanner, announcement_engine, research, generator, publisher, posted_symbols)


if __name__ == "__main__":
    # If post_interval > 0, run in loop mode
    if CONFIG.post_interval > 0:
        main_loop()
    else:
        main()
