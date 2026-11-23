import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

# Importing main must not require Pillow: image dependencies load only in live mode.
import main


class MainDryRunSafetyTests(unittest.TestCase):
    def test_dry_run_skips_image_generation_and_binance_upload(self):
        with patch("builtins.__import__", wraps=__import__) as importer:
            result = main._generate_image_list(
                SimpleNamespace(dry_run=True, square_api_key="test-key"),
                {"symbol": "BTC"},
            )

        self.assertEqual(result, [])
        self.assertFalse(
            any(call.args and call.args[0] == "image_engine" for call in importer.call_args_list)
        )
        self.assertNotIn("image_engine", sys.modules)

    def test_live_mode_generates_and_uploads_image(self):
        image_path = Path("/tmp/test-post-image.png")
        composer = Mock()
        composer.generate_post_image.return_value = image_path
        uploader = Mock()
        uploader.binance_media_upload.return_value = "https://cdn.example/image.png"
        fake_image_engine = types.ModuleType("image_engine")
        fake_image_engine.ImageComposer = Mock(return_value=composer)
        fake_image_engine.ImageUploader = Mock(return_value=uploader)

        with patch.dict(sys.modules, {"image_engine": fake_image_engine}):
            result = main._generate_image_list(
                SimpleNamespace(dry_run=False, square_api_key="test-key"),
                {"symbol": "BTC"},
            )

        self.assertEqual(result, ["https://cdn.example/image.png"])
        composer.generate_post_image.assert_called_once_with(coin={"symbol": "BTC"})
        uploader.binance_media_upload.assert_called_once_with(image_path, "test-key")

    def test_runtime_workflow_self_updater_is_absent(self):
        self.assertFalse(hasattr(main, "_maybe_update_workflow"))
        self.assertFalse(hasattr(main, "_NEW_WORKFLOW_B64"))


if __name__ == "__main__":
    unittest.main()
