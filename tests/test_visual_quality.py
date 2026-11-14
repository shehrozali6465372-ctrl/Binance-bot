import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from layer1.visual_quality import VisualQualityEngine


class VisualQualityEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.image_path = Path(self.tmp.name) / "asset.png"
        self.sidecar = Path(str(self.image_path) + ".json")
        Image.new("RGB", (1080, 1350), "navy").save(self.image_path, format="PNG")
        self.draft = "$ABC has an update. #ABC #Write2Earn"
        self.symbol = "ABC"
        self.asset_id = "coingecko:abc"
        self._write_sidecar()

    def tearDown(self):
        self.tmp.cleanup()

    def _write_sidecar(self, **overrides):
        image_bytes = self.image_path.read_bytes()
        metadata = {
            "provider": "cloudflare_workers_ai",
            "model": "@cf/black-forest-labs/flux-2-klein-4b",
            "request_id": "cf-ray-test",
            "generated_at": "2026-11-14T00:00:00+00:00",
            "prompt_hash": "b" * 64,
            "generation_parameters": {"width": 1024, "height": 1024, "output_format": "PNG"},
            "source_image_hash": "a" * 64,
            "final_image_hash": hashlib.sha256(image_bytes).hexdigest(),
            "draft_hash": hashlib.sha256(self.draft.encode()).hexdigest(),
            "asset_id": self.asset_id,
            "symbol": self.symbol,
            "dimensions": [1080, 1350],
            "rendered_labels": ["MARKET UPDATE", "$ABC"],
            "chart_data_refs": [],
            "numeric_overlays": [],
        }
        metadata.update(overrides)
        self.sidecar.write_text(json.dumps(metadata), encoding="utf-8")

    def test_exact_cloudflare_image_and_draft_pair_passes(self):
        result = VisualQualityEngine().validate(
            self.image_path, draft_content=self.draft,
            symbol=self.symbol, asset_id=self.asset_id,
        )
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.reasons, ())
        self.assertEqual((result.width, result.height), (1080, 1350))

    def test_changed_draft_invalidates_previous_image_approval(self):
        result = VisualQualityEngine().validate(
            self.image_path, draft_content=self.draft + " Changed.",
            symbol=self.symbol, asset_id=self.asset_id,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("DRAFT_IMAGE_PAIR_HASH_MISMATCH", result.reasons)

    def test_wrong_ticker_or_canonical_asset_fails(self):
        result = VisualQualityEngine().validate(
            self.image_path, draft_content=self.draft,
            symbol="XYZ", asset_id="coingecko:xyz",
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("CANONICAL_ASSET_IDENTITY_MISMATCH", result.reasons)

    def test_unsourced_chart_and_numeric_overlay_fail(self):
        self._write_sidecar(chart_data_refs=["missing:data"], numeric_overlays=["$123.45"])
        result = VisualQualityEngine().validate(
            self.image_path, draft_content=self.draft,
            symbol=self.symbol, asset_id=self.asset_id,
        )
        self.assertIn("UNSOURCED_CHART_DATA_REFERENCE", result.reasons)
        self.assertIn("UNPROVEN_NUMERIC_IMAGE_OVERLAY", result.reasons)

    def test_missing_prompt_hash_or_out_of_range_generation_parameters_fail(self):
        self._write_sidecar(
            prompt_hash="short",
            generation_parameters={"width": 2048, "height": 1024, "output_format": "PNG"},
        )
        result = VisualQualityEngine().validate(
            self.image_path, draft_content=self.draft,
            symbol=self.symbol, asset_id=self.asset_id,
        )
        self.assertIn("IMAGE_PROMPT_PROVENANCE_MISSING", result.reasons)
        self.assertIn("IMAGE_GENERATION_PARAMETERS_INVALID", result.reasons)

    def test_tampered_image_hash_fails(self):
        self._write_sidecar(final_image_hash="f" * 64)
        result = VisualQualityEngine().validate(
            self.image_path, draft_content=self.draft,
            symbol=self.symbol, asset_id=self.asset_id,
        )
        self.assertIn("FINAL_IMAGE_HASH_MISMATCH", result.reasons)

    def test_missing_sidecar_fails_closed(self):
        self.sidecar.unlink()
        result = VisualQualityEngine().validate(
            self.image_path, draft_content=self.draft,
            symbol=self.symbol, asset_id=self.asset_id,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("IMAGE_PROVENANCE_SIDECAR_MISSING_OR_INVALID", result.reasons)


if __name__ == "__main__":
    unittest.main()
