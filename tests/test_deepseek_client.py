import io
import json
import urllib.error
import unittest
from unittest.mock import patch

from layer1.deepseek_client import DeepSeekClient


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DeepSeekClientTests(unittest.TestCase):
    def _client(self, opener):
        return DeepSeekClient("test-secret", opener=opener)

    def test_sends_direct_api_request_and_extracts_text_and_usage(self):
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["payload"] = json.loads(request.data)
            captured["timeout"] = timeout
            return FakeResponse({
                "id": "response-1",
                "object": "chat.completion",
                "model": "deepseek-flash",
                "choices": [{"finish_reason": "stop", "message": {"content": "Evidence-backed draft"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            })

        result = self._client(opener).chat("Summarize evidence")
        self.assertEqual(result.text, "Evidence-backed draft")
        self.assertEqual(result.total_tokens, 18)
        self.assertEqual(result.response_id, "response-1")
        self.assertGreaterEqual(result.latency_ms, 0)
        self.assertEqual(captured["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(captured["payload"]["model"], "deepseek-flash")
        self.assertEqual(captured["payload"]["thinking"], {"type": "disabled"})
        self.assertEqual(captured["payload"]["stream"], False)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer test-secret")

    def test_missing_choices_returns_no_response_without_raising(self):
        client = self._client(lambda request, timeout: FakeResponse({
            "id": "response-1", "object": "chat.completion", "model": "deepseek-flash",
            "choices": [],
        }))
        self.assertIsNone(client.chat("prompt"))

    def test_empty_content_returns_no_response(self):
        client = self._client(lambda request, timeout: FakeResponse({
            "id": "response-1", "object": "chat.completion", "model": "deepseek-flash",
            "choices": [{"finish_reason": "stop", "message": {"content": " "}}],
        }))
        self.assertIsNone(client.chat("prompt"))

    def test_truncated_or_nonterminal_generation_is_rejected(self):
        for finish_reason in ("length", "content_filter", "tool_calls", "aborted", None):
            with self.subTest(finish_reason=finish_reason):
                client = self._client(lambda request, timeout: FakeResponse({
                    "id": "response-1", "object": "chat.completion", "model": "deepseek-flash",
                    "choices": [{
                        "finish_reason": finish_reason,
                        "message": {"content": "possibly truncated content"},
                    }],
                }))
                self.assertIsNone(client.chat("prompt"))

    def test_refusal_tool_calls_and_unexpected_model_are_rejected(self):
        refusal = self._client(lambda request, timeout: FakeResponse({
            "id": "response-1", "object": "chat.completion", "model": "deepseek-flash",
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": "cannot comply", "refusal": "policy"},
            }],
        }))
        self.assertIsNone(refusal.chat("prompt"))
        tool_call = self._client(lambda request, timeout: FakeResponse({
            "id": "response-1", "object": "chat.completion", "model": "deepseek-flash",
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": None, "tool_calls": [{"id": "tool-1"}]},
            }],
        }))
        self.assertIsNone(tool_call.chat("prompt"))
        wrong_model = self._client(lambda request, timeout: FakeResponse({
            "id": "response-1", "object": "chat.completion", "model": "unexpected-model",
            "choices": [{"finish_reason": "stop", "message": {"content": "content"}}],
        }))
        self.assertIsNone(wrong_model.chat("prompt"))

    def test_missing_response_identity_or_wrong_object_is_rejected(self):
        for payload in (
            {"object": "chat.completion", "model": "deepseek-flash",
             "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]},
            {"id": "response-1", "object": "unexpected", "model": "deepseek-flash",
             "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]},
        ):
            with self.subTest(payload=payload):
                self.assertIsNone(self._client(
                    lambda request, timeout: FakeResponse(payload)
                ).chat("prompt"))

    def test_transient_rate_limit_retries_with_bounded_backoff(self):
        attempts = []
        payload = {
            "id": "response-retry", "object": "chat.completion",
            "model": "deepseek-flash",
            "choices": [{"finish_reason": "stop", "message": {"content": "recovered"}}],
        }
        def opener(request, timeout):
            attempts.append(timeout)
            if len(attempts) == 1:
                raise urllib.error.HTTPError(
                    request.full_url, 429, "rate limited", {}, io.BytesIO(b""),
                )
            return FakeResponse(payload)
        client = DeepSeekClient(
            "test-secret", opener=opener, retry_backoff_seconds=0,
        )
        with patch("layer1.deepseek_client.time.sleep") as sleep:
            result = client.chat("prompt")
        self.assertEqual(result.text, "recovered")
        self.assertEqual(len(attempts), 2)
        sleep.assert_called_once_with(0.0)

    def test_non_transient_auth_error_is_not_retried(self):
        attempts = []
        def opener(request, timeout):
            attempts.append(1)
            raise urllib.error.HTTPError(
                request.full_url, 401, "unauthorized", {}, io.BytesIO(b""),
            )
        client = DeepSeekClient("test-secret", opener=opener)
        with patch("layer1.deepseek_client.time.sleep") as sleep:
            self.assertIsNone(client.chat("prompt"))
        self.assertEqual(len(attempts), 1)
        sleep.assert_not_called()

    def test_retry_configuration_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "max_retries"):
            DeepSeekClient("key", max_retries=4)
        with self.assertRaisesRegex(ValueError, "retry_backoff_seconds"):
            DeepSeekClient("key", retry_backoff_seconds=5.1)

    def test_non_official_https_proxy_and_unsupported_model_are_rejected(self):
        for endpoint in (
            "http://api.deepseek.com",
            "https://proxy.example.com",
            "https://api.deepseek.com/v1",
            "https://user:password@api.deepseek.com",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaisesRegex(ValueError, "official api.deepseek.com"):
                    DeepSeekClient("key", base_url=endpoint)
        with self.assertRaisesRegex(ValueError, "official model IDs"):
            DeepSeekClient("key", model="deepseek-chat")

    def test_secret_not_in_logged_transport_error(self):
        def opener(request, timeout):
            raise OSError("transport unavailable")
        with self.assertLogs("agent.deepseek", level="WARNING") as captured:
            self.assertIsNone(self._client(opener).chat("prompt"))
        output = "\n".join(captured.output)
        self.assertNotIn("test-secret", output)


if __name__ == "__main__":
    unittest.main()
