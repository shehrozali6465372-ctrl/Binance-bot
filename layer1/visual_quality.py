"""Deterministic visual artifact and draft-pair validation for Module 20."""
from __future__ import annotations

import hashlib
import json
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024
MAX_DECODED_IMAGE_PIXELS = 2_000_000
FONT_REGISTRY = {
    "LIBERATION_SANS_BOLD": Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
}


def _valid_int_vector(value: Any, length: int, low: int = 0, high: int = 255) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == length
        and all(
            isinstance(item, int) and not isinstance(item, bool) and low <= item <= high
            for item in value
        )
    )


def _relative_luminance(rgb: tuple[int, int, int] | list[int]) -> float:
    channels = []
    for channel in rgb:
        value = channel / 255.0
        channels.append(
            value / 12.92 if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(foreground: tuple[int, int, int] | list[int],
                    background: tuple[int, int, int] | list[int]) -> float:
    first, second = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)),
        reverse=True,
    )
    return (first + 0.05) / (second + 0.05)


def _validate_rendered_text_pixels(
    image: Image.Image, item: dict[str, Any], expected_text: str,
) -> tuple[str, ...]:
    """Re-render the declared glyphs and prove their pixels exist in the final PNG."""
    reasons: list[str] = []
    font_id = item.get("font_id")
    font_path = FONT_REGISTRY.get(font_id) if isinstance(font_id, str) else None
    if font_path is None or not font_path.is_file():
        return ("TEXT_FONT_UNAVAILABLE_OR_UNAPPROVED",)
    try:
        font_bytes = font_path.read_bytes()
    except OSError:
        return ("TEXT_FONT_UNAVAILABLE_OR_UNAPPROVED",)
    expected_font_hash = hashlib.sha256(font_bytes).hexdigest()
    if item.get("font_sha256") != expected_font_hash:
        reasons.append("TEXT_FONT_HASH_MISMATCH")

    font_size = item.get("font_size_px")
    origin = item.get("origin_xy")
    fill = item.get("fill_rgb")
    box = item.get("bbox")
    if (
        isinstance(font_size, bool) or not isinstance(font_size, int) or font_size < 28
        or not _valid_int_vector(origin, 2, 0, max(image.size))
        or not _valid_int_vector(fill, 3)
        or not _valid_int_vector(box, 4, 0, max(image.size))
    ):
        return tuple(sorted(set(reasons + ["TEXT_OVERLAY_PIXEL_PROOF_METADATA_INVALID"])))
    try:
        font = ImageFont.truetype(str(font_path), font_size)
        mask = Image.new("L", image.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        expected_box = mask_draw.textbbox(tuple(origin), expected_text, font=font)
        if tuple(box) != tuple(expected_box):
            reasons.append("TEXT_OVERLAY_GEOMETRY_MISMATCH")
        mask_draw.text(tuple(origin), expected_text, font=font, fill=255)
        glyph_mask = mask.crop(tuple(box))
        image_crop = image.crop(tuple(box)).convert("RGB")
        mask_values = list(glyph_mask.get_flattened_data())
        actual_pixels = list(image_crop.get_flattened_data())
    except (OSError, ValueError, TypeError):
        return tuple(sorted(set(reasons + ["TEXT_OVERLAY_PIXEL_PROOF_UNAVAILABLE"])))

    core_indexes = [index for index, coverage in enumerate(mask_values) if coverage >= 220]
    outside_indexes = [index for index, coverage in enumerate(mask_values) if coverage == 0]
    if len(core_indexes) < max(20, len(expected_text) * 2) or not outside_indexes:
        return tuple(sorted(set(reasons + ["TEXT_OVERLAY_PIXEL_PROOF_UNAVAILABLE"])))

    def matches_fill(pixel):
        return max(abs(int(pixel[channel]) - fill[channel]) for channel in range(3)) <= 24

    core_matches = sum(1 for index in core_indexes if matches_fill(actual_pixels[index]))
    outside_matches = sum(1 for index in outside_indexes if matches_fill(actual_pixels[index]))
    if core_matches / len(core_indexes) < 0.90:
        reasons.append("TEXT_PIXELS_MISSING_OR_TAMPERED")
    if outside_matches / len(outside_indexes) > 0.05:
        reasons.append("TEXT_PIXEL_SHAPE_NOT_REPRODUCED")
    return tuple(sorted(set(reasons)))


def _validate_visual_overlay(
    overlay: Any, expected_labels: tuple[str, str], image: Image.Image | None,
) -> tuple[str, ...]:
    width, height = image.size if image is not None else (0, 0)
    reasons: list[str] = []
    if not isinstance(overlay, dict):
        return ("TEXT_OVERLAY_GEOMETRY_MISSING_OR_INVALID",)
    panel = overlay.get("background_panel")
    items = overlay.get("items")
    if not isinstance(panel, dict) or not isinstance(items, list) or len(items) != 2:
        return ("TEXT_OVERLAY_GEOMETRY_MISSING_OR_INVALID",)

    panel_box = panel.get("bbox")
    panel_fill = panel.get("fill_rgba")
    if (
        not _valid_int_vector(panel_box, 4, 0, max(width, height))
        or panel_box[0] >= panel_box[2] or panel_box[1] >= panel_box[3]
        or panel_box[2] > width or panel_box[3] > height
        or not _valid_int_vector(panel_fill, 4)
        or panel_fill[3] == 0
    ):
        return ("TEXT_OVERLAY_GEOMETRY_MISSING_OR_INVALID",)

    alpha = panel_fill[3] / 255.0
    # White is the brightest possible source pixel. Compositing against it
    # gives a conservative upper bound for the background luminance.
    worst_case_background = tuple(
        round(panel_fill[index] * alpha + 255 * (1.0 - alpha))
        for index in range(3)
    )
    boxes: list[tuple[int, int, int, int]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or item.get("text") != expected_labels[index]:
            reasons.append("UNEXPECTED_OR_UNPROVEN_TEXT_OVERLAY")
            continue
        box = item.get("bbox")
        if (
            not _valid_int_vector(box, 4, 0, max(width, height))
            or box[0] >= box[2] or box[1] >= box[3]
        ):
            reasons.append("TEXT_OVERLAY_GEOMETRY_MISSING_OR_INVALID")
            continue
        left, top, right, bottom = box
        if (
            right > width or bottom > height
            or left < panel_box[0] or top < panel_box[1]
            or right > panel_box[2] or bottom > panel_box[3]
        ):
            reasons.append("TEXT_OVERLAY_OUT_OF_BOUNDS")
        boxes.append((left, top, right, bottom))

        font_size = item.get("font_size_px")
        if (
            isinstance(font_size, bool) or not isinstance(font_size, int)
            or font_size < 28
        ):
            reasons.append("TEXT_OVERLAY_FONT_TOO_SMALL")
        text_fill = item.get("fill_rgb")
        if not _valid_int_vector(text_fill, 3):
            reasons.append("TEXT_OVERLAY_GEOMETRY_MISSING_OR_INVALID")
        elif _contrast_ratio(text_fill, worst_case_background) < 4.5:
            reasons.append("TEXT_OVERLAY_CONTRAST_INSUFFICIENT")

        if image is None:
            reasons.append("IMAGE_PIXEL_DATA_UNAVAILABLE")
        else:
            reasons.extend(_validate_rendered_text_pixels(image, item, expected_labels[index]))

    if len(boxes) == 2:
        first, second = boxes
        horizontal_overlap = max(first[0], second[0]) < min(first[2], second[2])
        vertical_overlap = max(first[1], second[1]) < min(first[3], second[3])
        if horizontal_overlap and vertical_overlap:
            reasons.append("TEXT_OVERLAY_BOXES_OVERLAP")
    return tuple(sorted(set(reasons)))


@dataclass(frozen=True)
class VisualValidationResult:
    status: str
    image_hash: str
    draft_hash: str
    reasons: tuple[str, ...]
    width: int
    height: int
    byte_length: int
    validation_version: str = "visual-quality-v3"


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
        decoded_image: Image.Image | None = None
        try:
            # Read at most the configured limit plus one byte. Decode and hash
            # this same snapshot so a replaced path cannot change the validated
            # bytes between hashing and image inspection.
            with path.open("rb") as image_file:
                image_bytes = image_file.read(MAX_IMAGE_BYTES + 1)
            byte_length = len(image_bytes)
            if not 0 < byte_length <= MAX_IMAGE_BYTES:
                reasons.append("IMAGE_SIZE_OUT_OF_SAFE_BOUNDS")
            else:
                image_hash = hashlib.sha256(image_bytes).hexdigest()
                with Image.open(BytesIO(image_bytes)) as check:
                    width, height = check.size
                    if width * height > MAX_DECODED_IMAGE_PIXELS:
                        reasons.append("IMAGE_PIXEL_COUNT_OUT_OF_SAFE_BOUNDS")
                    elif (width, height) != self.REQUIRED_DIMENSIONS:
                        reasons.append("IMAGE_DIMENSIONS_MISMATCH")
                    else:
                        check.verify()
                        with Image.open(BytesIO(image_bytes)) as image:
                            image.load()
                            if image.size != (width, height):
                                reasons.append("IMAGE_DIMENSIONS_CHANGED_DURING_DECODE")
                            if image.format != "PNG":
                                reasons.append("FINAL_IMAGE_MUST_BE_PNG")
                            if path.suffix.lower() != ".png":
                                reasons.append("FINAL_IMAGE_EXTENSION_MISMATCH")
                            decoded_image = image.convert("RGB")
        except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            reasons.append("IMAGE_MISSING_OR_UNDECODABLE")
        try:
            with sidecar.open("rb") as metadata_file:
                metadata_bytes = metadata_file.read(MAX_METADATA_BYTES + 1)
            if not 0 < len(metadata_bytes) <= MAX_METADATA_BYTES:
                raise ValueError("sidecar exceeds the metadata size limit")
            metadata = json.loads(metadata_bytes.decode("utf-8"))
            if not isinstance(metadata, dict):
                raise ValueError("sidecar must be an object")
        except (OSError, ValueError, json.JSONDecodeError, RecursionError):
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
            expected_labels = ("MARKET UPDATE", "$" + symbol.upper())
            if tuple(metadata.get("rendered_labels") or ()) != expected_labels:
                reasons.append("UNEXPECTED_OR_UNPROVEN_TEXT_OVERLAY")
            reasons.extend(_validate_visual_overlay(
                metadata.get("visual_overlay"), expected_labels, decoded_image,
            ))
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
