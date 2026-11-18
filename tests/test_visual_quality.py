import hashlib
import json
import tempfile
import unittest
import warnings
from unittest import mock
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
            "visual_overlay": {
                "background_panel": {
                    "bbox": [0, 960, 1080, 1350],
                    "fill_rgba": [5, 12, 24, 190],
                },
                "items": [
                    {"text": "MARKET UPDATE", "bbox": [350, 1020, 730, 1060],
                     "font_size_px": 42, "fill_rgb": [170, 195, 225]},
                    {"text": "$ABC", "bbox": [400, 1080, 680, 1170],
                     "font_size_px": 82, "fill_rgb": [255, 255, 255]},
                ],
            },
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


    def test_png_bytes_with_non_png_filename_are_rejected(self):
        mismatched_path = Path(self.tmp.name) / "asset.jpg"
        mismatched_sidecar = Path(str(mismatched_path) + ".json")
        mismatched_path.write_bytes(self.image_path.read_bytes())
        mismatched_sidecar.write_text(self.sidecar.read_text(encoding="utf-8"), encoding="utf-8")
        result = VisualQualityEngine().validate(
            mismatched_path, metadata_path=mismatched_sidecar,
            draft_content=self.draft, symbol=self.symbol, asset_id=self.asset_id,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("FINAL_IMAGE_EXTENSION_MISMATCH", result.reasons)

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

    def test_oversized_sidecar_fails_closed(self):
        self._write_sidecar(unused_metadata="x" * (1024 * 1024 + 1))
        result = VisualQualityEngine().validate(
            self.image_path, draft_content=self.draft,
            symbol=self.symbol, asset_id=self.asset_id,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("IMAGE_PROVENANCE_SIDECAR_MISSING_OR_INVALID", result.reasons)

    def test_missing_sidecar_fails_closed(self):
        self.sidecar.unlink()
        result = VisualQualityEngine().validate(
            self.image_path, draft_content=self.draft,
            symbol=self.symbol, asset_id=self.asset_id,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("IMAGE_PROVENANCE_SIDECAR_MISSING_OR_INVALID", result.reasons)

    def test_missing_deterministic_overlay_geometry_fails_closed(self):
        self._write_sidecar(visual_overlay=None)
        result = VisualQualityEngine().validate(
            self.image_path, draft_content=self.draft,
            symbol=self.symbol, asset_id=self.asset_id,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("TEXT_OVERLAY_GEOMETRY_MISSING_OR_INVALID", result.reasons)

    def test_clipped_or_overlapping_overlay_boxes_fail_closed(self):
        self._write_sidecar(visual_overlay={
            "background_panel": {"bbox": [0, 960, 1080, 1350], "fill_rgba": [5, 12, 24, 190]},
            "items": [
                {"text": "MARKET UPDATE", "bbox": [100, 1020, 980, 1060], "font_size_px": 42, "fill_rgb": [170, 195, 225]},
                {"text": "$ABC", "bbox": [900, 1080, 1100, 1170], "font_size_px": 82, "fill_rgb": [255, 255, 255]},
            ],
        })
        result = VisualQualityEngine().validate(
            self.image_path, draft_content=self.draft,
            symbol=self.symbol, asset_id=self.asset_id,
        )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("TEXT_OVERLAY_OUT_OF_BOUNDS", result.reasons)

        self._write_sidecar(visual_overlay={
            "background_panel": {"bbox": [0, 960, 1080, 1350], "fill_rgba": [5, 12, 24, 190]},
            "items": [
                {"text": "MARKET UPDATE", "bbox": [100, 1020, 700, 1120], "font_size_px": 42, "fill_rgb": [170, 195, 225]},
                {"text": "$ABC", "bbox": [350, 1080, 730, 1170], "font_size_px": 82, "fill_rgb": [255, 255, 255]},
            ],
        })
        result = VisualQualityEngine().validate(
            self.image_path, draft_content=self.draft,
            symbol=self.symbol, asset_id=self.asset_id,
        )
        self.assertIn("TEXT_OVERLAY_BOXES_OVERLAP", result.reasons)

    def test_oversized_image_is_rejected_without_unbounded_file_read(self):
        oversized_path = Path(self.tmp.name) / "oversized-file.png"
        with oversized_path.open("wb") as handle:
            handle.truncate(10 * 1024 * 1024 + 1)
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded read attempted")) as read_bytes:
            result = VisualQualityEngine().validate(
                oversized_path, draft_content=self.draft,
                symbol=self.symbol, asset_id=self.asset_id,
                metadata_path=self.sidecar,
            )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("IMAGE_SIZE_OUT_OF_SAFE_BOUNDS", result.reasons)
        read_bytes.assert_not_called()

    def test_image_pixel_limit_is_checked_before_decode(self):
        with mock.patch("layer1.visual_quality.MAX_DECODED_IMAGE_PIXELS", 100, create=True), mock.patch.object(
            Image.Image, "load", side_effect=AssertionError("pixel decode must not run"),
        ):
            result = VisualQualityEngine().validate(
                self.image_path, draft_content=self.draft,
                symbol=self.symbol, asset_id=self.asset_id,
                metadata_path=self.sidecar,
            )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("IMAGE_PIXEL_COUNT_OUT_OF_SAFE_BOUNDS", result.reasons)

    def test_decompression_bomb_image_is_rejected_without_raising(self):
        bomb_path = Path(self.tmp.name) / "bomb.png"
        Image.new("RGB", (20, 20), "black").save(bomb_path, format="PNG")
        with mock.patch.object(Image, "MAX_IMAGE_PIXELS", 100):
            result = VisualQualityEngine().validate(
                bomb_path, draft_content=self.draft,
                symbol=self.symbol, asset_id=self.asset_id,
                metadata_path=self.sidecar,
            )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("IMAGE_MISSING_OR_UNDECODABLE", result.reasons)

    def test_decompression_bomb_warning_is_rejected_when_warnings_are_errors(self):
        oversized_path = Path(self.tmp.name) / "oversized.png"
        Image.new("RGB", (11, 10), "black").save(oversized_path, format="PNG")
        with mock.patch.object(Image, "MAX_IMAGE_PIXELS", 100):
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                result = VisualQualityEngine().validate(
                    oversized_path, draft_content=self.draft,
                    symbol=self.symbol, asset_id=self.asset_id,
                    metadata_path=self.sidecar,
                )
        self.assertEqual(result.status, "REJECT")
        self.assertIn("IMAGE_MISSING_OR_UNDECODABLE", result.reasons)

    def test_low_contrast_or_unreadably_small_overlay_fails_closed(self):
        self._write_sidecar(visual_overlay={
            "background_panel": {"bbox": [0, 960, 1080, 1350], "fill_rgba": [5, 12, 24, 190]},
            "items": [
                {"text": "MARKET UPDATE", "bbox": [350, 1020, 730, 1060], "font_size_px": 42, "fill_rgb": [70, 74, 83]},
                {"text": "$ABC", "bbox": [400, 1080, 680, 1170], "font_size_px": 18, "fill_rgb": [255, 255, 255]},
            ],
        })
        result = VisualQualityEngine().validate(
            self.image_path, draft_content=self.draft,
            symbol=self.symbol, asset_id=self.asset_id,
        )
        self.assertIn("TEXT_OVERLAY_CONTRAST_INSUFFICIENT", result.reasons)
        self.assertIn("TEXT_OVERLAY_FONT_TOO_SMALL", result.reasons)


if __name__ == "__main__":
    unittest.main()
