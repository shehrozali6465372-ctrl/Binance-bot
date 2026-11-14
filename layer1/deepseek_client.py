"""Direct official DeepSeek Chat Completions client.

This module deliberately has no third-party SDK dependency. It uses the existing
stdlib HTTP stack, validates response structure and never logs credentials or
provider response bodies.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Optional

LOGGER = logging.getLogger("agent.deepseek")
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


@dataclass(frozen=True)
class DeepSeekResponse:
    text: str
    model: str
    response_id: str
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]


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
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("DeepSeek API key is required")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("DeepSeek model must be non-empty")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive integer")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        if not isinstance(temperature, (int, float)) or isinstance(temperature, bool) or not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if not isinstance(top_p, (int, float)) or isinstance(top_p, bool) or not 0 < top_p <= 1:
            raise ValueError("top_p must be between 0 and 1")
        if not isinstance(base_url, str) or not base_url.startswith("https://"):
            raise ValueError("DeepSeek base URL must use HTTPS")
        self._api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = float(temperature)
        self.top_p = float(top_p)
        self.max_tokens = max_tokens
        self.base_url = base_url.rstrip("/")
        self._opener = opener

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
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                status = getattr(response, "status", 200)
                raw = response.read()
            if status != 200:
                LOGGER.warning("DeepSeek returned HTTP %s", status)
                return None
            decoded = json.loads(raw.decode("utf-8"))
            if not isinstance(decoded, Mapping):
                raise ValueError("DeepSeek response must be a JSON object")
            choices = decoded.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
                raise ValueError("DeepSeek response has no choices")
            message = choices[0].get("message")
            if not isinstance(message, Mapping):
                raise ValueError("DeepSeek response has no message")
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
                model=str(decoded.get("model") or self.model),
                response_id=str(decoded.get("id") or ""),
                prompt_tokens=count("prompt_tokens"),
                completion_tokens=count("completion_tokens"),
                total_tokens=count("total_tokens"),
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
