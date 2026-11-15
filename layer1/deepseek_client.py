"""Direct official DeepSeek Chat Completions client.

This module deliberately has no third-party SDK dependency. It uses the existing
stdlib HTTP stack, validates response structure and never logs credentials or
provider response bodies.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from dataclasses import dataclass
from typing import Any, Mapping, Optional

LOGGER = logging.getLogger("agent.deepseek")
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"
SUPPORTED_MODELS = frozenset({"deepseek-flash", "deepseek-v4-pro"})


@dataclass(frozen=True)
class DeepSeekResponse:
    text: str
    model: str
    response_id: str
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]
    latency_ms: int


class DeepSeekClient:
    """Minimal direct DeepSeek API client for deterministic text extraction."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        *,
        timeout_seconds: int = 30,
        temperature: float = 0.7,
        top_p: float = 1.0,
        max_tokens: int = 2048,
        base_url: str = DEFAULT_BASE_URL,
        opener=urllib.request.urlopen,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.25,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("DeepSeek API key is required")
        if not isinstance(model, str) or model not in SUPPORTED_MODELS:
            raise ValueError("DeepSeek model must be one of the currently documented official model IDs")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive integer")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        if not isinstance(temperature, (int, float)) or isinstance(temperature, bool) or not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if not isinstance(top_p, (int, float)) or isinstance(top_p, bool) or not 0 < top_p <= 1:
            raise ValueError("top_p must be between 0 and 1")
        parsed_base_url = urlsplit(base_url) if isinstance(base_url, str) else None
        if (
            parsed_base_url is None
            or parsed_base_url.scheme != "https"
            or parsed_base_url.hostname != "api.deepseek.com"
            or parsed_base_url.port not in (None, 443)
            or parsed_base_url.username is not None
            or parsed_base_url.password is not None
            or parsed_base_url.path not in ("", "/")
            or parsed_base_url.query
            or parsed_base_url.fragment
        ):
            raise ValueError("DeepSeek base URL must be the official api.deepseek.com HTTPS origin")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or not 0 <= max_retries <= 3:
            raise ValueError("max_retries must be between 0 and 3")
        if (
            isinstance(retry_backoff_seconds, bool)
            or not isinstance(retry_backoff_seconds, (int, float))
            or not 0 <= retry_backoff_seconds <= 5
        ):
            raise ValueError("retry_backoff_seconds must be between 0 and 5")
        self.max_retries = max_retries
        self.retry_backoff_seconds = float(retry_backoff_seconds)
        self._api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = float(temperature)
        self.top_p = float(top_p)
        self.max_tokens = max_tokens
        self.base_url = base_url.rstrip("/")
        self._opener = opener

    def _fetch(self, request) -> tuple[int, bytes] | None:
        transient_http = {408, 429, 500, 502, 503, 504}
        for attempt in range(self.max_retries + 1):
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    return getattr(response, "status", 200), response.read()
            except urllib.error.HTTPError as exc:
                if exc.code in transient_http and attempt < self.max_retries:
                    delay = self.retry_backoff_seconds * (2 ** attempt)
                    LOGGER.warning(
                        "Transient DeepSeek HTTP %s; bounded retry %s/%s",
                        exc.code, attempt + 1, self.max_retries,
                    )
                    time.sleep(delay)
                    continue
                LOGGER.warning("DeepSeek request failed with HTTP %s", exc.code)
                return None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt < self.max_retries:
                    delay = self.retry_backoff_seconds * (2 ** attempt)
                    LOGGER.warning(
                        "Transient DeepSeek transport failure (%s); bounded retry %s/%s",
                        type(exc).__name__, attempt + 1, self.max_retries,
                    )
                    time.sleep(delay)
                    continue
                LOGGER.warning("DeepSeek transport failure: %s", type(exc).__name__)
                return None
        return None

    def chat(self, prompt: str, *, system_prompt: str = "You are a careful research and editorial assistant.") -> Optional[DeepSeekResponse]:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be non-empty")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "thinking": {"type": "disabled"},
            "safety_check": {"level": "high"},
            "stream": False,
        }
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self._api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        started_at = time.perf_counter()
        try:
            fetched = self._fetch(request)
            if fetched is None:
                return None
            status, raw = fetched
            if status != 200:
                LOGGER.warning("DeepSeek returned HTTP %s", status)
                return None
            decoded = json.loads(raw.decode("utf-8"))
            if not isinstance(decoded, Mapping):
                raise ValueError("DeepSeek response must be a JSON object")
            if decoded.get("object") != "chat.completion":
                raise ValueError("DeepSeek response object type is invalid")
            response_id = decoded.get("id")
            if not isinstance(response_id, str) or not response_id.strip():
                raise ValueError("DeepSeek response ID is missing")
            response_model = decoded.get("model")
            if not isinstance(response_model, str) or response_model != self.model:
                raise ValueError("DeepSeek returned an unexpected model identifier")
            choices = decoded.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
                raise ValueError("DeepSeek response has no choices")
            choice = choices[0]
            if choice.get("finish_reason") != "stop":
                LOGGER.warning("DeepSeek generation did not finish normally: %s", choice.get("finish_reason"))
                return None
            message = choice.get("message")
            if not isinstance(message, Mapping):
                raise ValueError("DeepSeek response has no message")
            refusal = message.get("refusal")
            if refusal:
                LOGGER.warning("DeepSeek returned a refusal response")
                return None
            tool_calls = message.get("tool_calls")
            if tool_calls:
                LOGGER.warning("DeepSeek returned unexpected tool calls for a text-only request")
                return None
            text = message.get("content")
            if not isinstance(text, str) or not text.strip():
                return None
            usage = decoded.get("usage")
            if not isinstance(usage, Mapping):
                usage = {}
            def count(name: str) -> Optional[int]:
                value = usage.get(name)
                return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
            return DeepSeekResponse(
                text=text.strip(),
                model=response_model,
                response_id=response_id,
                prompt_tokens=count("prompt_tokens"),
                completion_tokens=count("completion_tokens"),
                total_tokens=count("total_tokens"),
                latency_ms=max(0, round((time.perf_counter() - started_at) * 1000)),
            )
        except urllib.error.HTTPError as exc:
            LOGGER.warning("DeepSeek request failed with HTTP %s", exc.code)
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            LOGGER.warning("DeepSeek transport failure: %s", type(exc).__name__)
            return None
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            LOGGER.warning("DeepSeek response validation failure: %s", type(exc).__name__)
            return None
