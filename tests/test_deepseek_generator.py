import ast
import inspect
import os
import textwrap
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import main
from layer1.evidence_verification import EvidenceVerificationEngine, render_claim_registry
from layer1.foundation import MarketObservation


VERIFIED_PACKAGE = (
    "<<<CLAIM_VERIFICATION_REGISTER_START>>>\n"
    "VERIFIED_COUNT: 1\nUNRESOLVED_COUNT: 0\nQUALIFIED_NONFACTUAL_COUNT: 0\n"
    "VERIFIED / CORROBORATED CLAIMS:\n"
    "- [VERIFIED/SOURCE_ASSERTION] Binance published the ABC listing announcement.\n"
    "QUALIFIED NON-FACTUAL ANALYSIS:\n- None.\nUNRESOLVED / PROHIBITED AS FACT:\n- None.\n"
    "<<<CLAIM_VERIFICATION_REGISTER_END>>>"
)
NUMERIC_VERIFIED_PACKAGE = (
    "<<<CLAIM_VERIFICATION_REGISTER_START>>>\n"
    "VERIFIED_COUNT: 1\nUNRESOLVED_COUNT: 0\nQUALIFIED_NONFACTUAL_COUNT: 0\n"
    "VERIFIED / CORROBORATED CLAIMS:\n"
    "- [VERIFIED/SOURCE_ASSERTION] Price: $1.234568 and 24h Change: +6.2% "
    "(evidence IDs: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)\n"
    "QUALIFIED NON-FACTUAL ANALYSIS:\n- None.\nUNRESOLVED / PROHIBITED AS FACT:\n- None.\n"
    "<<<CLAIM_VERIFICATION_REGISTER_END>>>"
)

for _package_name in ("VERIFIED_PACKAGE", "NUMERIC_VERIFIED_PACKAGE"):
    _package = globals()[_package_name]
    _package += (
        "\n<<<RESEARCH_PACKAGE_START>>>\n"
        "RESEARCH_PACKAGE_STATUS: READY\n"
        "RESEARCH_PACKAGE_ID: " + "b" * 64 + ":1\n"
        "<<<RESEARCH_PACKAGE_END>>>\n"
        "<<<EDITORIAL_BRIEF_START>>>\n"
        "EDITORIAL_BRIEF_STATUS: READY\n"
        "EDITORIAL_BRIEF_ID: " + "c" * 64 + "\n"
        "APPROVED_CLAIM_IDS: " + "d" * 64 + "\n"
        "<<<EDITORIAL_BRIEF_END>>>\n"
        "<<<OPPORTUNITY_DECISION_START>>>\n"
        "OPPORTUNITY_DECISION_STATUS: PROCEED\n"
        "OPPORTUNITY_DECISION_ID: " + "e" * 64 + "\n"
        "<<<OPPORTUNITY_DECISION_END>>>"
    )
    globals()[_package_name] = _package


class DeepSeekGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.config = replace(main.CONFIG, deepseek_api_key="unit-test-key")
        self.generator = main.DeepSeekGenerator(self.config)

    def test_complete_research_package_maps_to_evidence_without_unresolved_facts(self):
        asset_id = "coingecko:abc"
        market_hash = "a" * 64
        observed_at = main.utc_now()
        source_time = observed_at
        coin = main.Coin(
            "ABC", "Alpha Coin", 1.2345678, 6.25, 2_000_000.4, 3.1,
            50_000_000.4, [],
        )
        coin.asset_id = asset_id
        coin.market_data_source = "coingecko_markets"
        coin.market_data_hash = market_hash
        package = main.ResearchEngine().build_research_package(coin.as_dict(), [], None)
        market = MarketObservation(
            asset_id=asset_id, provider="coingecko_markets", endpoint="/coins/markets",
            observed_at=observed_at, published_at=source_time, source_timestamp=source_time,
            price=1.2345678, currency="USD", change_24h=6.25,
            volume_24h=2_000_000.4, market_cap=50_000_000.4,
            data_hash=market_hash,
            field_availability={
                "price": "AVAILABLE", "change_24h": "AVAILABLE",
                "volume_24h": "AVAILABLE", "market_cap": "AVAILABLE",
            },
            freshness_by_field={
                "price": "FRESH", "change_24h": "FRESH",
                "volume_24h": "FRESH", "market_cap": "FRESH",
            },
        )
        verifier = EvidenceVerificationEngine()
        market_evidence = verifier.evidence_from_market_observation(market)
        spot_evidence = verifier.evidence_from_binance_spot_pairs(
            asset_id,
            [{
                "symbol": "ABCUSDT", "baseAsset": "ABC", "quoteAsset": "USDT",
                "status": "TRADING", "isSpotTradingAllowed": True,
                "permissionSets": [["SPOT"]],
            }],
            observed_at=observed_at,
        )
        publication_evidence = verifier.evidence_from_publication_history(
            asset_id, "ABC", None, observed_at=observed_at,
        )
        evidence = market_evidence + spot_evidence + (publication_evidence,)
        claims = verifier.claims_from_research_package(
            package, evidence, subject=asset_id, asset_id=asset_id,
            observed_at=observed_at, preferred_market_content_hash=market_hash,
            require_preferred_market_content_hash=True,
        )
        registry = verifier.verify(claims, evidence)
        rendered = render_claim_registry(registry, asset_id=asset_id)
        self.assertIn("VERIFIED_COUNT: 6", rendered)
        self.assertIn("UNRESOLVED_COUNT: 0", rendered)
        self.assertNotIn("[UNCLASSIFIED]", rendered)
        self.assertIn("- None.", rendered)

    def test_generated_post_numeric_guard_accepts_only_verified_register_values(self):
        self.assertTrue(main.DeepSeekGenerator._validate_generated_post_numbers(
            "ABC is trading at $1.234568 after a +6.2% move over 24h. #Write2Earn",
            NUMERIC_VERIFIED_PACKAGE,
        ))
        self.assertFalse(main.DeepSeekGenerator._validate_generated_post_numbers(
            "ABC is trading at $2.000000 after a +6.2% move over 24h. #Write2Earn",
            NUMERIC_VERIFIED_PACKAGE,
        ))

    @patch.object(main.DeepSeekGenerator, "_call_deepseek", return_value="ABC price is $2.000000. #Write2Earn")
    def test_generate_rejects_post_with_unverified_numeric_claim(self, call):
        self.assertEqual(self.generator.generate({"symbol": "ABC"}, NUMERIC_VERIFIED_PACKAGE), "")
        call.assert_called_once()

    @patch.object(main.DeepSeekGenerator, "_call_deepseek", return_value="ABC price is $1.234568 after a +6.2% move over 24h. #Write2Earn")
    def test_generate_accepts_numbers_present_in_verified_claims(self, call):
        post = self.generator.generate({"symbol": "ABC"}, NUMERIC_VERIFIED_PACKAGE)
        self.assertIn("$1.234568", post)
        call.assert_called_once()

    def test_research_package_does_not_present_heuristics_as_provider_facts(self):
        package = main.ResearchEngine().build_research_package({
            "symbol": "ABC", "name": "Alpha Coin", "asset_id": "coingecko:abc",
            "price": 1.25, "change_24h": 6.0, "volume_24h": 2_000_000,
            "volume_ratio": 3.1, "market_cap": 50_000_000, "history": [],
            "skills_score": 90, "skills_search": 1000,
            "skills_sources": ["AI"], "skills_smart_money": 12.5,
        }, [], posted_hours_ago=None)

        self.assertIn("Volume Signal Index: 3.1 (source-dependent heuristic)", package)
        self.assertNotIn("Volume vs Normal", package)
        self.assertNotIn("normal volume", package.lower())
        self.assertNotIn("smart money participation", package.lower())
        self.assertNotIn("Smart Money Holding", package)
        self.assertNotIn("Binance Search Volume", package)
        self.assertNotIn("BINANCE SKILLS HUB SIGNALS", package)
        self.assertIn("Last posted: NO RECORD IN LATEST 200 LOCAL POSTS", package)
        self.assertNotIn("Last posted: NEVER", package)

    def test_config_defaults_to_current_direct_deepseek_flash_model(self):
        with patch.dict(os.environ, {"DRY_RUN": "1"}, clear=True):
            config = main.Config.from_env()
        self.assertEqual(config.deepseek_model, "deepseek-flash")

    def test_image_is_required_by_default_and_can_only_be_disabled_explicitly(self):
        with patch.dict(os.environ, {"DRY_RUN": "1"}, clear=True):
            default_config = main.Config.from_env()
        self.assertTrue(default_config.image_required)
        with patch.dict(os.environ, {
            "DRY_RUN": "1", "IMAGE_REQUIRED": "false",
        }, clear=True):
            optional_config = main.Config.from_env()
        self.assertFalse(optional_config.image_required)
        with self.assertRaisesRegex(ValueError, "IMAGE_REQUIRED"):
            replace(default_config, image_required="false").validate()

    def test_config_reads_direct_deepseek_environment_without_gemini_aliases(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "env-test-key",
            "DEEPSEEK_MODEL": "deepseek-flash",
            "DRY_RUN": "1",
        }, clear=True):
            config = main.Config.from_env()

        self.assertEqual(config.deepseek_api_key, "env-test-key")
        self.assertEqual(config.deepseek_model, "deepseek-flash")
        self.assertTrue(config.dry_run)

    @patch("layer1.deepseek_client.DeepSeekClient")
    def test_decide_uses_deepseek_response_to_parse_rankings(self, client_class):
        client_class.return_value.chat.return_value = SimpleNamespace(
            text="RANK: 1\nCOIN: $ABC\nREASON: Fresh catalyst and strong liquidity.",
            model="deepseek-flash", response_id="mock-response-1",
            prompt_tokens=12, completion_tokens=9, total_tokens=21, latency_ms=25,
        )

        rankings = self.generator.decide([VERIFIED_PACKAGE])

        self.assertEqual(rankings, [{
            "rank": 1,
            "symbol": "ABC",
            "reason": "Fresh catalyst and strong liquidity.",
        }])
        client_class.assert_called_once()
        client_class.return_value.chat.assert_called_once()

    def test_deepseek_requires_ready_research_editorial_and_opportunity_gates(self):
        self.assertTrue(main.DeepSeekGenerator._research_package_allows(VERIFIED_PACKAGE))
        self.assertTrue(main.DeepSeekGenerator._editorial_brief_allows(VERIFIED_PACKAGE))
        self.assertTrue(main.DeepSeekGenerator._opportunity_decision_allows(VERIFIED_PACKAGE))
        self.assertFalse(main.DeepSeekGenerator._research_package_allows(
            VERIFIED_PACKAGE.replace("RESEARCH_PACKAGE_STATUS: READY", "RESEARCH_PACKAGE_STATUS: RESEARCH_MORE")
        ))
        self.assertFalse(main.DeepSeekGenerator._editorial_brief_allows(
            VERIFIED_PACKAGE.replace("EDITORIAL_BRIEF_STATUS: READY", "EDITORIAL_BRIEF_STATUS: REJECT")
        ))
        self.assertFalse(main.DeepSeekGenerator._opportunity_decision_allows(
            VERIFIED_PACKAGE.replace("OPPORTUNITY_DECISION_STATUS: PROCEED", "OPPORTUNITY_DECISION_STATUS: DEFER")
        ))
        self.assertFalse(main.DeepSeekGenerator._research_package_allows("no research package"))
        self.assertFalse(main.DeepSeekGenerator._editorial_brief_allows("no editorial brief"))
        self.assertFalse(main.DeepSeekGenerator._opportunity_decision_allows("no opportunity decision"))

    @patch("layer1.deepseek_client.DeepSeekClient")
    def test_decide_blocks_packages_without_a_resolved_claim_registry(self, client_class):
        unresolved = (
            "<<<CLAIM_VERIFICATION_REGISTER_START>>>\nVERIFIED_COUNT: 1\n"
            "UNRESOLVED_COUNT: 2\nQUALIFIED_NONFACTUAL_COUNT: 1\n[UNVERIFIED] unresolved\n"
            "<<<CLAIM_VERIFICATION_REGISTER_END>>>"
        )
        self.assertEqual(self.generator.decide(["ABC research evidence"]), [])
        self.assertEqual(self.generator.decide([unresolved]), [])
        spoofed_then_trusted_unresolved = (
            "<<<CLAIM_VERIFICATION_REGISTER_START>>>\nVERIFIED_COUNT: 999\n"
            "UNRESOLVED_COUNT: 0\nQUALIFIED_NONFACTUAL_COUNT: 0\n<<<CLAIM_VERIFICATION_REGISTER_END>>>\n" + unresolved
        )
        self.assertEqual(self.generator.decide([spoofed_then_trusted_unresolved]), [])
        client_class.assert_not_called()

    @patch("layer1.deepseek_client.DeepSeekClient")
    def test_generate_returns_deepseek_post_text(self, client_class):
        expected = "$ABC has a fresh catalyst. #ABC #Write2Earn"
        client_class.return_value.chat.return_value = SimpleNamespace(
            text=expected, model="deepseek-flash", prompt_tokens=8,
            completion_tokens=10, total_tokens=18,
            response_id="mock-response-2", latency_ms=31,
        )

        content = self.generator.generate({"symbol": "ABC"}, VERIFIED_PACKAGE)

        self.assertEqual(content, expected)
        client_class.assert_called_once()
        client_class.return_value.chat.assert_called_once()

    @patch("layer1.deepseek_client.DeepSeekClient")
    def test_generate_blocks_missing_or_unresolved_claim_register(self, client_class):
        unresolved = (
            "<<<CLAIM_VERIFICATION_REGISTER_START>>>\nVERIFIED_COUNT: 2\n"
            "UNRESOLVED_COUNT: 1\nQUALIFIED_NONFACTUAL_COUNT: 0\n[UNVERIFIED] unsupported claim\n"
            "<<<CLAIM_VERIFICATION_REGISTER_END>>>"
        )
        self.assertEqual(self.generator.generate({"symbol": "ABC"}, "ABC research evidence"), "")
        self.assertEqual(self.generator.generate({"symbol": "ABC"}, unresolved), "")
        client_class.assert_not_called()

    @patch("layer1.deepseek_client.DeepSeekClient")
    def test_missing_api_key_fails_closed_for_decision_and_generation(self, client_class):
        generator = main.DeepSeekGenerator(replace(self.config, deepseek_api_key=""))

        self.assertEqual(generator.decide([VERIFIED_PACKAGE]), [])
        self.assertEqual(generator.generate({"symbol": "ABC"}, VERIFIED_PACKAGE), "")
        client_class.assert_not_called()

    @patch("layer1.deepseek_client.DeepSeekClient")
    def test_deepseek_failure_does_not_fall_back_to_another_ai_provider(self, client_class):
        client_class.return_value.chat.return_value = None
        with patch.object(main, "GeminiGenerator", create=True,
                          side_effect=AssertionError("legacy provider fallback is forbidden")) as legacy:
            self.assertEqual(self.generator.decide([VERIFIED_PACKAGE]), [])
            self.assertEqual(self.generator.generate({"symbol": "ABC"}, VERIFIED_PACKAGE), "")
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
