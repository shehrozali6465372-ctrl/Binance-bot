"""Deterministic visual artifact and draft-pair validation for Module 20."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image


@dataclass(frozen=True)
class VisualValidationResult:
    status: str
    image_hash: str
    draft_hash: str
    reasons: tuple[str, ...]
    width: int
    height: int
    byte_length: int
    validation_version: str = "visual-quality-v1"


class VisualQualityEngine:
    """Validate the exact generated image, deterministic text overlay and draft pairing."""

    REQUIRED_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
    REQUIRED_DIMENSIONS = (1080, 1350)
    REQUIRED_LABELS = ("MARKET UPDATE",)

    def validate(
        self,
        image_path: str | Path,
        *,
        draft_content: str,
        symbol: str,
        asset_id: str,
        metadata_path: str | Path | None = None,
    ) -> VisualValidationResult:
        if not isinstance(draft_content, str) or not draft_content.strip():
            raise ValueError("visual QA requires the exact non-empty draft text")
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("visual QA requires the exact asset ticker")
        if not isinstance(asset_id, str) or not asset_id.startswith("coingecko:"):
            raise ValueError("visual QA requires a canonical asset identity")
        path = Path(image_path)
        sidecar = Path(metadata_path) if metadata_path else Path(str(path) + ".json")
        reasons: list[str] = []
        draft_hash = hashlib.sha256(draft_content.encode("utf-8")).hexdigest()
        image_hash = ""
        width = height = byte_length = 0
        metadata: dict[str, Any] = {}
        try:
            image_bytes = path.read_bytes()
            byte_length = len(image_bytes)
            image_hash = hashlib.sha256(image_bytes).hexdigest()
            with Image.open(path) as check:
                check.verify()
            with Image.open(path) as image:
                image.load()
                width, height = image.size
                if image.format != "PNG":
                    reasons.append("FINAL_IMAGE_MUST_BE_PNG")
                if (width, height) != self.REQUIRED_DIMENSIONS:
                    reasons.append("IMAGE_DIMENSIONS_MISMATCH")
            if not 0 < byte_length <= 10 * 1024 * 1024:
                reasons.append("IMAGE_SIZE_OUT_OF_SAFE_BOUNDS")
        except (OSError, ValueError):
            reasons.append("IMAGE_MISSING_OR_UNDECODABLE")
        try:
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                raise ValueError("sidecar must be an object")
        except (OSError, ValueError, json.JSONDecodeError):
            reasons.append("IMAGE_PROVENANCE_SIDECAR_MISSING_OR_INVALID")
        if metadata:
            if metadata.get("final_image_hash") != image_hash:
                reasons.append("FINAL_IMAGE_HASH_MISMATCH")
            if metadata.get("draft_hash") != draft_hash:
                reasons.append("DRAFT_IMAGE_PAIR_HASH_MISMATCH")
            if metadata.get("asset_id") != asset_id or metadata.get("symbol") != symbol.upper():
                reasons.append("CANONICAL_ASSET_IDENTITY_MISMATCH")
            if metadata.get("model") != self.REQUIRED_MODEL:
                reasons.append("UNAPPROVED_IMAGE_MODEL")
            prompt_hash = metadata.get("prompt_hash")
            if not isinstance(prompt_hash, str) or len(prompt_hash) != 64:
                reasons.append("IMAGE_PROMPT_PROVENANCE_MISSING")
            generation = metadata.get("generation_parameters")
            if (
                not isinstance(generation, dict)
                or isinstance(generation.get("width"), bool)
                or not isinstance(generation.get("width"), int)
                or isinstance(generation.get("height"), bool)
                or not isinstance(generation.get("height"), int)
                or not 256 <= generation.get("width", 0) <= 1920
                or not 256 <= generation.get("height", 0) <= 1920
                or generation.get("output_format") not in {"PNG", "JPEG", "WEBP"}
            ):
                reasons.append("IMAGE_GENERATION_PARAMETERS_INVALID")
            if tuple(metadata.get("dimensions") or ()) != self.REQUIRED_DIMENSIONS:
                reasons.append("PROVENANCE_DIMENSIONS_MISMATCH")
            if tuple(metadata.get("rendered_labels") or ()) != (
                "MARKET UPDATE", "$" + symbol.upper(),
            ):
                reasons.append("UNEXPECTED_OR_UNPROVEN_TEXT_OVERLAY")
            if metadata.get("chart_data_refs") not in ([], None):
                reasons.append("UNSOURCED_CHART_DATA_REFERENCE")
            if metadata.get("numeric_overlays") not in ([], None):
                reasons.append("UNPROVEN_NUMERIC_IMAGE_OVERLAY")
        else:
            reasons.append("IMAGE_PROVENANCE_UNAVAILABLE")
        return VisualValidationResult(
            status="PASS" if not reasons else "REJECT",
            image_hash=image_hash, draft_hash=draft_hash,
            reasons=tuple(sorted(set(reasons))),
            width=width, height=height, byte_length=byte_length,
        )
