import ast
import inspect
import os
import textwrap
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import main


class DeepSeekGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.config = replace(main.CONFIG, deepseek_api_key="unit-test-key")
        self.generator = main.DeepSeekGenerator(self.config)

    def test_config_reads_direct_deepseek_environment_without_gemini_aliases(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "env-test-key",
            "DEEPSEEK_MODEL": "deepseek-chat",
            "DRY_RUN": "1",
        }, clear=True):
            config = main.Config.from_env()

        self.assertEqual(config.deepseek_api_key, "env-test-key")
        self.assertEqual(config.deepseek_model, "deepseek-chat")
        self.assertTrue(config.dry_run)

    @patch("layer1.deepseek_client.DeepSeekClient")
    def test_decide_uses_deepseek_response_to_parse_rankings(self, client_class):
        client_class.return_value.chat.return_value = SimpleNamespace(
            text="RANK: 1\nCOIN: $ABC\nREASON: Fresh catalyst and strong liquidity.",
            model="deepseek-chat", prompt_tokens=12, completion_tokens=9, total_tokens=21,
        )

        rankings = self.generator.decide(["ABC research evidence"])

        self.assertEqual(rankings, [{
            "rank": 1,
            "symbol": "ABC",
            "reason": "Fresh catalyst and strong liquidity.",
        }])
        client_class.assert_called_once()
        client_class.return_value.chat.assert_called_once()

    @patch("layer1.deepseek_client.DeepSeekClient")
    def test_generate_returns_deepseek_post_text(self, client_class):
        expected = "$ABC has a fresh catalyst. #ABC #Write2Earn"
        client_class.return_value.chat.return_value = SimpleNamespace(
            text=expected, model="deepseek-chat", prompt_tokens=8,
            completion_tokens=10, total_tokens=18,
        )

        content = self.generator.generate({"symbol": "ABC"}, "ABC research evidence")

        self.assertEqual(content, expected)
        client_class.assert_called_once()
        client_class.return_value.chat.assert_called_once()

    @patch("layer1.deepseek_client.DeepSeekClient")
    def test_missing_api_key_fails_closed_for_decision_and_generation(self, client_class):
        generator = main.DeepSeekGenerator(replace(self.config, deepseek_api_key=""))

        self.assertEqual(generator.decide(["ABC research evidence"]), [])
        self.assertEqual(generator.generate({"symbol": "ABC"}, "ABC research evidence"), "")
        client_class.assert_not_called()

    @patch("layer1.deepseek_client.DeepSeekClient")
    def test_deepseek_failure_does_not_fall_back_to_another_ai_provider(self, client_class):
        client_class.return_value.chat.return_value = None
        with patch.object(main, "GeminiGenerator", create=True,
                          side_effect=AssertionError("legacy provider fallback is forbidden")) as legacy:
            self.assertEqual(self.generator.decide(["ABC research evidence"]), [])
            self.assertEqual(self.generator.generate({"symbol": "ABC"}, "ABC research evidence"), "")
        legacy.assert_not_called()
        self.assertEqual(client_class.call_count, 2)

    def test_failed_generation_returns_before_publisher_call_in_pipeline(self):
        source = textwrap.dedent(inspect.getsource(main._run_once_impl))
        tree = ast.parse(source)
        function = tree.body[0]
        guard_line = None
        publish_line = None
        for node in ast.walk(function):
            if isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
                if isinstance(node.test.operand, ast.Name) and node.test.operand.id == "content":
                    if any(isinstance(child, ast.Return) and isinstance(child.value, ast.Constant)
                           and child.value.value is False for child in node.body):
                        guard_line = node.lineno
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "publisher" and node.func.attr == "publish":
                    publish_line = node.lineno
        self.assertIsNotNone(guard_line, "empty generated content must fail closed")
        self.assertIsNotNone(publish_line, "pipeline must have an explicit publisher boundary")
        self.assertLess(guard_line, publish_line, "empty-content guard must precede publishing")


if __name__ == "__main__":
    unittest.main()
