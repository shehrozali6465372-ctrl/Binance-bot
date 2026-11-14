import base64
import hashlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from image_engine import (
    CloudflareImageArtifact, CloudflareWorkersAIImageGenerator, ImageComposer,
    ImageUploader, should_upload_image, upload_authorized_image,
)
from layer1.visual_quality import VisualQualityEngine


class FakeResponse:
    status = 200

    def __init__(self, body, content_type="application/json"):
        self.body = body
        self.headers = {"Content-Type": content_type, "cf-ray": "test-ray-123"}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def png_bytes():
    import io
    output = io.BytesIO()
    Image.new("RGB", (512, 512), "navy").save(output, format="PNG")
    return output.getvalue()


class CloudflareWorkersAIImageGeneratorTests(unittest.TestCase):
    def test_media_upload_requires_valid_authorization_for_exact_draft_and_image(self):
        class Authorization:
            def __init__(self, valid=True, reasons=()):
                self.valid = valid
                self.reasons = reasons
                self.checked = False

            def verify_integrity(self):
                return self.valid

            def validate_for_submission(self, **kwargs):
                self.checked = True
                self.kwargs = kwargs
                return self.reasons

        calls = []
        auth = Authorization()
        url = upload_authorized_image(
            authorization=auth, dry_run=False, image_path="/tmp/image.png",
            api_key="test-key", symbol="ABC", asset_id="coingecko:abc",
            content="verified content", image_hashes=["a" * 64],
            upload_fn=lambda path, key: calls.append((path, key)) or "https://bin.bnbstatic.com/image",
        )
        self.assertEqual(url, "https://bin.bnbstatic.com/image")
        self.assertTrue(auth.checked)
        self.assertEqual(auth.kwargs["image_hashes"], ["a" * 64])
        self.assertEqual(calls, [("/tmp/image.png", "test-key")])

    def test_binance_media_transport_refuses_http_redirects(self):
        from urllib.request import Request
        from image_engine import _NoRedirectHandler
        handler = _NoRedirectHandler()
        request = Request("https://bucket.s3.amazonaws.com/object.png?sig=opaque")
        self.assertIsNone(handler.redirect_request(
            request, None, 307, "Temporary Redirect", {}, "https://evil.example/object.png",
        ))

    def test_binance_presigned_storage_url_allowlist_rejects_ssrf_targets(self):
        valid = (
            "https://bucket.s3.amazonaws.com/object.png?X-Amz-Signature=opaque",
            "https://storage.binance.com/object.png?signature=opaque",
        )
        invalid = (
            "http://bucket.s3.amazonaws.com/object.png?sig=x",
            "https://evil.example/object.png?sig=x",
            "https://127.0.0.1/object.png?sig=x",
            "https://user:pass@bucket.s3.amazonaws.com/object.png?sig=x",
            "https://bucket.s3.amazonaws.com:8443/object.png?sig=x",
            "https://bucket.s3.amazonaws.com/object.png",
        )
        for value in valid:
            with self.subTest(value=value):
                self.assertTrue(ImageUploader._is_allowed_presigned_upload_url(value))
        for value in invalid:
            with self.subTest(value=value):
                self.assertFalse(ImageUploader._is_allowed_presigned_upload_url(value))

    def test_final_media_url_must_be_binance_cdn_host(self):
        class Authorization:
            def verify_integrity(self):
                return True
            def validate_for_submission(self, **kwargs):
                return ()
        with self.assertRaisesRegex(ValueError, "allowlisted Binance CDN"):
            upload_authorized_image(
                authorization=Authorization(), dry_run=False,
                image_path="/tmp/image.png", api_key="test-key",
                symbol="ABC", asset_id="coingecko:abc", content="verified",
                image_hashes=["a" * 64],
                upload_fn=lambda path, key: "https://evil.example/image.png",
            )

    def test_media_upload_fails_closed_without_authorization_or_on_hash_mismatch(self):
        calls = []
        upload = lambda path, key: calls.append((path, key)) or "https://binance.example/image"
        with self.assertRaisesRegex(ValueError, "authorization is required"):
            upload_authorized_image(
                authorization=None, dry_run=False, image_path="/tmp/image.png",
                api_key="test-key", symbol="ABC", asset_id="coingecko:abc",
                content="content", image_hashes=["a" * 64], upload_fn=upload,
            )
        class RejectedAuthorization:
            def verify_integrity(self):
                return True
            def validate_for_submission(self, **kwargs):
                return ("IMAGE_ARTIFACT_CHANGED",)
        with self.assertRaisesRegex(ValueError, "IMAGE_ARTIFACT_CHANGED"):
            upload_authorized_image(
                authorization=RejectedAuthorization(), dry_run=False,
                image_path="/tmp/image.png", api_key="test-key",
                symbol="ABC", asset_id="coingecko:abc", content="content",
                image_hashes=["b" * 64], upload_fn=upload,
            )
        self.assertEqual(calls, [])

    def test_media_upload_is_forbidden_in_dry_run(self):
        self.assertFalse(should_upload_image(dry_run=True, image_path="/tmp/image.png"))
        self.assertFalse(should_upload_image(dry_run=False, image_path=None))
        self.assertFalse(should_upload_image(dry_run=False, image_path=""))
        self.assertTrue(should_upload_image(dry_run=False, image_path="/tmp/image.png"))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name) / "generated.png"
        self.image_bytes = png_bytes()

    def tearDown(self):
        self.tmp.cleanup()

    def generator(self, opener):
        return CloudflareWorkersAIImageGenerator(
            api_token="test-token", account_id="81d020cda41d9d2ac3b1af88fbe286f4",
            opener=opener,
        )

    def test_multipart_direct_workers_ai_request_and_decodable_image(self):
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = request.data
            captured["timeout"] = timeout
            payload = json.dumps({
                "success": True,
                "result": {"image": base64.b64encode(self.image_bytes).decode("ascii")},
            }).encode()
            return FakeResponse(payload)

        result = self.generator(opener).generate(
            "Abstract crypto network illustration; no text or data.",
            self.output, width=512, height=512,
        )
        self.assertEqual(result.model, "@cf/black-forest-labs/flux-2-klein-4b")
        self.assertEqual(result.content_hash, hashlib.sha256(self.image_bytes).hexdigest())
        self.assertEqual((result.width, result.height), (512, 512))
        self.assertEqual(result.request_id, "test-ray-123")
        self.assertTrue(self.output.exists())
        self.assertIn("/ai/run/@cf/black-forest-labs/flux-2-klein-4b", captured["url"])
        self.assertIn("Bearer test-token", captured["headers"]["Authorization"])
        self.assertIn("multipart/form-data; boundary=", captured["headers"]["Content-type"])
        self.assertIn(b'name="prompt"', captured["body"])
        self.assertIn(b'name="width"', captured["body"])
        self.assertIn(b'name="height"', captured["body"])

    def test_missing_credentials_fail_before_network(self):
        generator = CloudflareWorkersAIImageGenerator(api_token="", account_id="")
        with patch("image_engine.urllib.request.urlopen") as opener:
            with self.assertRaisesRegex(ValueError, "credentials"):
                generator.generate("prompt", self.output)
        opener.assert_not_called()

    def test_api_failure_is_not_reported_as_image_success(self):
        payload = json.dumps({"success": False, "errors": [{"message": "model unavailable"}]}).encode()
        with self.assertRaisesRegex(RuntimeError, "Workers AI inference failed"):
            self.generator(lambda request, timeout: FakeResponse(payload)).generate("prompt", self.output)
        self.assertFalse(self.output.exists())

    def test_malformed_base64_is_rejected(self):
        payload = json.dumps({"success": True, "result": {"image": "not-base64!"}}).encode()
        with self.assertRaisesRegex(ValueError, "base64"):
            self.generator(lambda request, timeout: FakeResponse(payload)).generate("prompt", self.output)
        self.assertFalse(self.output.exists())

    def test_corrupt_image_bytes_are_rejected(self):
        payload = json.dumps({"success": True, "result": {
            "image": base64.b64encode(b"not-an-image").decode("ascii"),
        }}).encode()
        with self.assertRaisesRegex(ValueError, "decodable"):
            self.generator(lambda request, timeout: FakeResponse(payload)).generate("prompt", self.output)
        self.assertFalse(self.output.exists())

    def test_non_json_binary_image_response_is_supported(self):
        result = self.generator(
            lambda request, timeout: FakeResponse(self.image_bytes, "image/png")
        ).generate("prompt", self.output, width=512, height=512)
        self.assertEqual(result.format, "PNG")
        self.assertTrue(self.output.exists())


    def test_image_composer_uses_generic_ai_background_and_exact_draft_pair(self):
        import os
        old_cwd = os.getcwd()
        os.chdir(self.tmp.name)
        try:
            with patch("image_engine.CloudflareWorkersAIImageGenerator") as generator_class:
                def generate(prompt, output_path, width, height):
                    Image.new("RGB", (1024, 1024), "midnightblue").save(output_path, format="PNG")
                    return CloudflareImageArtifact(
                        path=Path(output_path), model=CloudflareWorkersAIImageGenerator.DEFAULT_MODEL,
                        content_hash=hashlib.sha256(Path(output_path).read_bytes()).hexdigest(),
                        byte_length=Path(output_path).stat().st_size, width=1024, height=1024,
                        format="PNG", request_id="cf-ray-compose",
                        generated_at="2026-11-14T00:00:00+00:00",
                    )
                generator_class.return_value.generate.side_effect = generate
                composer = ImageComposer()
                draft = "$ABC market update. #ABC #Write2Earn"
                path = composer.generate_post_image({
                    "symbol": "ABC", "asset_id": "coingecko:abc",
                    "price": 999999, "change_24h": 88, "volume_ratio": 12,
                    "entry": 100, "target1": 200, "stop": 50,
                }, draft_content=draft)
                self.assertIsNotNone(path)
                prompt = generator_class.return_value.generate.call_args.args[0]
                self.assertNotIn("ABC", prompt)
                self.assertNotIn("999999", prompt)
                self.assertNotIn("100", prompt)
                result = VisualQualityEngine().validate(
                    path, draft_content=draft, symbol="ABC", asset_id="coingecko:abc",
                )
                self.assertEqual(result.status, "PASS")
        finally:
            os.chdir(old_cwd)

    def test_dimensions_are_bounded_to_official_model_limits(self):
        with self.assertRaisesRegex(ValueError, "dimensions"):
            self.generator(lambda request, timeout: self.fail("must not call")).generate(
                "prompt", self.output, width=128, height=512,
            )
        with self.assertRaisesRegex(ValueError, "256 and 1920"):
            self.generator(lambda request, timeout: self.fail("must not call")).generate(
                "prompt", self.output, width=1921, height=512,
            )


if __name__ == "__main__":
    unittest.main()
