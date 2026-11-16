"""Static safety checks for the manual provider-verification workflow."""
from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "provider-verification.yml"


class ProviderVerificationWorkflowSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_is_manual_only(self):
        self.assertIn("on:\n  workflow_dispatch:", self.source)
        self.assertNotIn("\n  schedule:", self.source)
        self.assertNotIn("\n  push:", self.source)
        self.assertNotIn("\n  pull_request:", self.source)

    def test_checkout_uses_layer1_source_branch(self):
        self.assertIn("ref: layer-1/module9-onchain-continuation", self.source)

    def test_only_provider_credentials_are_injected(self):
        self.assertIn("DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}", self.source)
        self.assertIn("CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}", self.source)
        self.assertIn("DEEPSEEK_MODEL: ${{ vars.DEEPSEEK_MODEL }}", self.source)
        self.assertIn("CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}", self.source)
        for forbidden in ("SQUARE_API_KEY", "ANNOUNCEMENT_DATABASE_URL", "GH_TOKEN", "BINANCE_API_KEY"):
            self.assertNotIn(forbidden, self.source)

    def test_workflow_cannot_enter_publisher_or_scheduled_path(self):
        for forbidden in ("python main.py", "run_bot.yml", "published_posts", "upload-artifact", "actions/cache"):
            self.assertNotIn(forbidden, self.source)

    def test_deepseek_verification_accepts_any_valid_completion(self):
        self.assertIn("if result is None:", self.source)
        self.assertNotIn('result.text.strip() != "DEEPSEEK_PROVIDER_OK"', self.source)
        self.assertIn("Reply with a brief acknowledgment", self.source)

    def test_logs_never_print_credentials_or_generated_content(self):
        self.assertIn("logging.basicConfig(level=logging.WARNING", self.source)
        self.assertIn("sanitized validation categories", self.source)
        self.assertNotIn("print(os.environ", self.source)
        self.assertNotIn("print(result.text", self.source)
        self.assertNotIn("print(artifact", self.source)
        self.assertIn("set +x", self.source)

    def test_both_provider_checks_run_before_final_failure(self):
        self.assertIn("failed = False", self.source)
        self.assertEqual(self.source.count("sys.exit(1)"), 1)
        self.assertRegex(self.source, r"if failed:\s+sys\.exit\(1\)")

    def test_permissions_and_execution_are_bounded(self):
        self.assertIn("permissions:\n  contents: read", self.source)
        self.assertIn("timeout-minutes: 5", self.source)
        self.assertIn("max_retries=0", self.source)
        self.assertIn("timeout_seconds=20", self.source)
        self.assertIn("timeout_seconds=60", self.source)


if __name__ == "__main__":
    unittest.main()
