import json
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
                "model": "deepseek-chat",
                "choices": [{"message": {"content": "Evidence-backed draft"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            })

        result = self._client(opener).chat("Summarize evidence")
        self.assertEqual(result.text, "Evidence-backed draft")
        self.assertEqual(result.total_tokens, 18)
        self.assertEqual(captured["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(captured["payload"]["model"], "deepseek-chat")
        self.assertEqual(captured["payload"]["stream"], False)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer test-secret")

    def test_missing_choices_is_rejected(self):
        client = self._client(lambda request, timeout: FakeResponse({"choices": []}))
        with self.assertRaises(ValueError):
            client.chat("prompt")

    def test_empty_content_returns_no_response(self):
        client = self._client(lambda request, timeout: FakeResponse({
            "choices": [{"message": {"content": " "}}]
        }))
        self.assertIsNone(client.chat("prompt"))

    def test_non_https_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            DeepSeekClient("key", base_url="http://api.deepseek.com")

    def test_secret_not_in_logged_transport_error(self):
        def opener(request, timeout):
            raise OSError("transport unavailable")
        with self.assertLogs("agent.deepseek", level="WARNING") as captured:
            self.assertIsNone(self._client(opener).chat("prompt"))
        output = "\n".join(captured.output)
        self.assertNotIn("test-secret", output)


if __name__ == "__main__":
    unittest.main()
