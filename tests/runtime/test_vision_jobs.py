from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from runtime.vision_jobs import run_vision_job


def _write_color_image(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (48, 48), color).save(path)


def test_compare_job_expands_pairs_and_collects_artifacts(tmp_path: Path) -> None:
    left = tmp_path / "a.png"
    right = tmp_path / "b.png"
    _write_color_image(left, (255, 255, 255))
    _write_color_image(right, (0, 0, 0))

    payload = {"mode": "compare", "inputs": ["a.png", "b.png"]}
    result = run_vision_job(str(tmp_path), payload)

    assert result["status"] == "ok"
    assert result["job"]["mode"] == "compare"
    assert result["artifacts"]["compare_count"] == 1
    assert (tmp_path / result["artifacts"]["artifact_path"]).exists()


def test_compare_job_uses_cache_on_second_run(tmp_path: Path) -> None:
    left = tmp_path / "a.png"
    right = tmp_path / "b.png"
    _write_color_image(left, (255, 0, 0))
    _write_color_image(right, (0, 0, 255))

    payload = {"mode": "compare", "inputs": ["a.png", "b.png"]}
    first = run_vision_job(str(tmp_path), payload)
    second = run_vision_job(str(tmp_path), payload)

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second["cached"] is True


def test_compare_job_requires_two_inputs(tmp_path: Path) -> None:
    left = tmp_path / "a.png"
    _write_color_image(left, (255, 255, 255))

    payload = {"mode": "compare", "inputs": ["a.png"]}

    with pytest.raises(ValueError, match="at least two input files"):
        run_vision_job(str(tmp_path), payload)


def test_unimplemented_modes_fail_closed(tmp_path: Path) -> None:
    target = tmp_path / "a.png"
    _write_color_image(target, (255, 255, 255))

    payload = {"mode": "analyze", "inputs": ["a.png"]}

    with pytest.raises(ValueError, match="not implemented yet"):
        run_vision_job(str(tmp_path), payload)
