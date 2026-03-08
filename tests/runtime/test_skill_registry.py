from __future__ import annotations

from pathlib import Path

import pytest

from runtime.skill_registry import compact_registry


def test_compact_registry_splits_active_and_pruned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    result = compact_registry(
        ["omg/control-plane", "omg/mcp-fabric", "playwright"],
        used=["omg/control-plane", "missing-skill"],
    )

    assert result["active"] == ["omg/control-plane"]
    assert result["pruned"] == ["omg/mcp-fabric", "playwright"]
    summary_metadata = result["summary_metadata"]
    assert isinstance(summary_metadata, dict)
    assert "omg/control-plane" in summary_metadata


def test_compact_registry_persists_compact_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    _ = compact_registry(["omg/control-plane", "omg/mcp-fabric"], used=["omg/control-plane"])

    output = tmp_path / ".omg" / "state" / "skill_registry" / "compact.json"
    assert output.exists()

    text = output.read_text(encoding="utf-8")
    assert '"active": [' in text
    assert '"omg/control-plane"' in text
    assert '"pruned": [' in text
    assert '"omg/mcp-fabric"' in text
    assert '"summary_metadata"' in text


def test_compact_registry_handles_empty_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    result = compact_registry([], used=[])
    assert result["active"] == []
    assert result["pruned"] == []
    assert result["summary_metadata"] == {}
