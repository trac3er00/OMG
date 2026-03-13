"""OMG Natives — image: deterministic image info, compare, and OCR fallback."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from omg_natives._bindings import bind_function

try:
    from PIL import Image, ImageChops, ImageOps
except ImportError:  # pragma: no cover - exercised only when Pillow is missing
    Image = None
    ImageChops = None
    ImageOps = None


def _base_info(path: str) -> dict[str, Any]:
    p = Path(path)
    exists = p.exists()
    size_bytes = 0
    if exists:
        try:
            size_bytes = os.path.getsize(path)
        except OSError:
            pass
    return {
        "path": str(p),
        "size_bytes": size_bytes,
        "exists": exists,
        "extension": p.suffix,
    }


def _error(path: str, operation: str, message: str, *, error_code: str) -> dict[str, Any]:
    payload = _base_info(path)
    payload.update(
        {
            "status": "error",
            "operation": operation,
            "error_code": error_code,
            "message": message,
        }
    )
    return payload


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_pillow(path: str, operation: str) -> dict[str, Any] | None:
    if Image is None or ImageChops is None or ImageOps is None:
        return _error(path, operation, "Pillow is required for this operation", error_code="PILLOW_UNAVAILABLE")
    return None


def _open_rgb(path: str):
    with Image.open(path) as source:
        normalized = ImageOps.exif_transpose(source).convert("RGB")
    return normalized


def _average_hash(image_obj) -> str:
    grayscale = image_obj.convert("L").resize((8, 8))
    pixels = list(grayscale.tobytes())
    average = sum(pixels) / len(pixels)
    bits = "".join("1" if pixel >= average else "0" for pixel in pixels)
    return f"{int(bits, 2):016x}"


def _image_info(path: str) -> dict[str, Any]:
    payload = _base_info(path)
    payload.update({"status": "ok", "operation": "info"})
    if not payload["exists"]:
        return payload

    pillow_error = _require_pillow(path, "info")
    if pillow_error is not None:
        return payload

    try:
        with Image.open(path) as source:
            payload.update(
                {
                    "width": source.width,
                    "height": source.height,
                    "mode": source.mode,
                    "format": source.format or "",
                }
            )
    except OSError:
        payload.update({"width": 0, "height": 0, "mode": "", "format": ""})
    return payload


def _compare_images(path: str, other_path: str) -> dict[str, Any]:
    if not other_path:
        return _error(path, "compare", "other_path is required for compare", error_code="MISSING_OTHER_PATH")

    left_info = _base_info(path)
    right_info = _base_info(other_path)
    if not left_info["exists"]:
        return _error(path, "compare", f"input path does not exist: {path}", error_code="MISSING_INPUT")
    if not right_info["exists"]:
        return _error(path, "compare", f"input path does not exist: {other_path}", error_code="MISSING_INPUT")

    pillow_error = _require_pillow(path, "compare")
    if pillow_error is not None:
        return pillow_error

    left_image = _open_rgb(path)
    right_image = _open_rgb(other_path)

    original_left_size = list(left_image.size)
    original_right_size = list(right_image.size)
    if left_image.size != right_image.size:
        right_image = right_image.resize(left_image.size)

    diff = ImageChops.difference(left_image, right_image)
    diff_gray = diff.convert("L")
    diff_pixels = list(diff_gray.tobytes())
    changed_pixels = sum(1 for pixel in diff_pixels if pixel > 0)
    total_pixels = len(diff_pixels) or 1
    total_intensity = sum(diff_pixels)
    pixel_delta_ratio = changed_pixels / total_pixels
    similarity_score = 1.0 - (total_intensity / (255 * total_pixels))
    bbox = diff.getbbox()

    return {
        "status": "ok",
        "operation": "compare",
        "left_path": str(Path(path)),
        "right_path": str(Path(other_path)),
        "left_size": original_left_size,
        "right_size": original_right_size,
        "normalized_size": [left_image.width, left_image.height],
        "exact_hash_left": _sha256(path),
        "exact_hash_right": _sha256(other_path),
        "perceptual_hash_left": _average_hash(left_image),
        "perceptual_hash_right": _average_hash(right_image),
        "changed_pixels": changed_pixels,
        "total_pixels": total_pixels,
        "pixel_delta_ratio": round(pixel_delta_ratio, 6),
        "similarity_score": round(similarity_score, 6),
        "exact_match": bbox is None,
        "changed_bbox": list(bbox) if bbox else None,
    }


def _parse_tesseract_tsv(output: str) -> tuple[str, list[dict[str, Any]], float | None]:
    blocks: list[dict[str, Any]] = []
    for raw_line in output.splitlines()[1:]:
        fields = raw_line.split("\t")
        if len(fields) != 12:
            continue
        text = fields[11].strip()
        if not text:
            continue
        try:
            confidence = float(fields[10])
        except ValueError:
            confidence = -1.0
        blocks.append(
            {
                "text": text,
                "confidence": confidence,
                "bbox": {
                    "left": int(fields[6]),
                    "top": int(fields[7]),
                    "width": int(fields[8]),
                    "height": int(fields[9]),
                },
            }
        )

    confidences = [block["confidence"] for block in blocks if block["confidence"] >= 0]
    mean_confidence = round(sum(confidences) / len(confidences), 2) if confidences else None
    return " ".join(block["text"] for block in blocks), blocks, mean_confidence


def _ocr_image(path: str, *, language: str = "eng", psm: int = 6) -> dict[str, Any]:
    info = _base_info(path)
    if not info["exists"]:
        return _error(path, "ocr", f"input path does not exist: {path}", error_code="MISSING_INPUT")

    tesseract_path = shutil.which("tesseract")
    if tesseract_path is None:
        return _error(path, "ocr", "tesseract binary is not installed", error_code="TESSERACT_UNAVAILABLE")

    pillow_error = _require_pillow(path, "ocr")
    if pillow_error is not None:
        return pillow_error

    source_image = _open_rgb(path)
    preprocessed = source_image.convert("L").resize(
        (source_image.width * 2, source_image.height * 2)
    )
    preprocessed = preprocessed.point(lambda value: 255 if value > 180 else 0)

    with tempfile.NamedTemporaryFile(suffix=".png") as temp_file:
        preprocessed.save(temp_file.name)
        command = [
            tesseract_path,
            temp_file.name,
            "stdout",
            "--psm",
            str(psm),
            "-l",
            language,
            "tsv",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return _error(
            path,
            "ocr",
            completed.stderr.strip() or "tesseract OCR failed",
            error_code="TESSERACT_FAILED",
        )

    text, blocks, mean_confidence = _parse_tesseract_tsv(completed.stdout)
    return {
        "status": "ok",
        "operation": "ocr",
        "path": str(Path(path)),
        "tool": "tesseract",
        "language": language,
        "psm": psm,
        "text": text,
        "blocks": blocks,
        "mean_confidence": mean_confidence,
    }


def image(path: str, operation: str = "info", **kwargs: Any) -> dict[str, Any]:
    """Run deterministic image operations through the Python fallback.

    Operations:
    - ``"info"``: metadata for an image path
    - ``"compare"``: compare ``path`` against ``other_path``
    - ``"ocr"``: OCR extraction through the local ``tesseract`` binary
    """
    if operation == "info":
        return _image_info(path)
    if operation == "compare":
        return _compare_images(path, str(kwargs.get("other_path", "")))
    if operation == "ocr":
        return _ocr_image(
            path,
            language=str(kwargs.get("language", "eng")),
            psm=int(kwargs.get("psm", 6)),
        )
    return _error(path, operation, f"unsupported operation: {operation}", error_code="UNSUPPORTED_OPERATION")


# Self-register with the global binding registry
bind_function(
    name="image",
    rust_symbol="omg_natives::image::image",
    python_fallback=image,
    type_hints={
        "path": "str",
        "operation": "str",
        "other_path": "str",
        "language": "str",
        "psm": "int",
    },
)
