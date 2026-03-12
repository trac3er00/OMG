from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from omg_natives.image import image


def _font(size: int = 64) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _write_text_image(path: Path, text: str) -> None:
    canvas = Image.new("RGB", (320, 160), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 40), text, fill="black", font=_font())
    canvas.save(path)


def _write_solid_image(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (64, 64), color).save(path)


def test_image_compare_operation_returns_metrics(tmp_path: Path) -> None:
    left = tmp_path / "left.png"
    right = tmp_path / "right.png"
    _write_solid_image(left, (255, 0, 0))
    _write_solid_image(right, (0, 0, 255))

    result = image(str(left), "compare", other_path=str(right))

    assert result["status"] == "ok"
    assert result["operation"] == "compare"
    assert result["left_path"] == str(left)
    assert result["right_path"] == str(right)
    assert result["pixel_delta_ratio"] > 0
    assert result["changed_pixels"] > 0
    assert "perceptual_hash_left" in result
    assert "perceptual_hash_right" in result


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract binary required")
def test_image_ocr_operation_extracts_text(tmp_path: Path) -> None:
    target = tmp_path / "ocr.png"
    _write_text_image(target, "OMG")

    result = image(str(target), "ocr")

    assert result["status"] == "ok"
    assert result["operation"] == "ocr"
    assert "OMG" in result["text"].upper()
    assert result["blocks"]
