from __future__ import annotations

from pathlib import Path
from typing import Callable, cast

from runtime import proof_gate


validate_artifact_content = cast(
    Callable[[dict[str, object]], str | None],
    getattr(proof_gate, "_validate_artifact_content"),
)


def test_empty_file_is_blocked(tmp_path: Path) -> None:
    f = tmp_path / "empty.txt"
    _ = f.write_bytes(b"")

    result = validate_artifact_content({"path": str(f), "kind": "test_output"})

    assert result is not None
    assert "empty" in result.lower()


def test_nonempty_text_file_passes(tmp_path: Path) -> None:
    f = tmp_path / "results.txt"
    _ = f.write_text("5 passed, 0 failed\n")

    result = validate_artifact_content({"path": str(f), "kind": "test_output"})

    assert result is None


def test_valid_png_passes(tmp_path: Path) -> None:
    f = tmp_path / "screenshot.png"
    _ = f.write_bytes(b"\x89PNG\r\n\x1a\n" + (b"\x00" * 100))

    result = validate_artifact_content({"path": str(f), "kind": "screenshot"})

    assert result is None


def test_invalid_png_is_blocked(tmp_path: Path) -> None:
    f = tmp_path / "fake.png"
    _ = f.write_text("this is not a png")

    result = validate_artifact_content({"path": str(f), "kind": "screenshot"})

    assert result is not None
    assert "image" in result.lower() or "invalid" in result.lower()


def test_missing_path_returns_none() -> None:
    result = validate_artifact_content({"kind": "test_output"})

    assert result is None


def test_nonexistent_file_returns_none(tmp_path: Path) -> None:
    result = validate_artifact_content(
        {"path": str(tmp_path / "nonexistent.txt"), "kind": "test"}
    )

    assert result is None
