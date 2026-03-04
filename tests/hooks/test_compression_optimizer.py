# pyright: reportMissingImports=false
"""Tests for hooks/_compression_optimizer.py (Task 26)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import hooks._compression_optimizer as compression_optimizer


def _write_jsonl(path: Path, entries: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")


def _bucket(result: dict[str, object], key: str) -> list[str]:
    return cast(list[str], result.get(key, []))


def test_optimize_guidelines_creates_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(compression_optimizer, "get_feature_flag", lambda _name, default=False: True)
    feedback_path = tmp_path / "compression-feedback.jsonl"
    output_path = tmp_path / "compression-guidelines.json"
    _write_jsonl(
        feedback_path,
        [
            {"failed": True, "dropped_items": ["error_trace", "api_response"]},
            {"failed": False, "dropped_items": ["debug_log"]},
        ],
    )

    result = compression_optimizer.optimize_guidelines(str(feedback_path), str(output_path))

    assert output_path.exists()
    assert isinstance(result, dict)


def test_high_frequency_items_always_keep(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(compression_optimizer, "get_feature_flag", lambda _name, default=False: True)
    feedback_path = tmp_path / "compression-feedback.jsonl"
    output_path = tmp_path / "compression-guidelines.json"
    _write_jsonl(
        feedback_path,
        [
            {"failed": True, "dropped_items": ["stack_trace", "request_id"]},
            {"failed": True, "dropped_items": ["stack_trace"]},
            {"failed": True, "dropped_items": ["stack_trace", "token_usage"]},
            {"failed": False, "dropped_items": ["stack_trace"]},
        ],
    )

    result = compression_optimizer.optimize_guidelines(str(feedback_path), str(output_path))

    always_keep = _bucket(result, "always_keep")
    assert "stack_trace" in always_keep
    assert "request_id" not in always_keep


def test_low_frequency_items_prefer_keep(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(compression_optimizer, "get_feature_flag", lambda _name, default=False: True)
    feedback_path = tmp_path / "compression-feedback.jsonl"
    output_path = tmp_path / "compression-guidelines.json"
    _write_jsonl(
        feedback_path,
        [
            {"failed": True, "dropped_items": ["session_summary", "error_context"]},
            {"failed": True, "dropped_items": ["session_summary"]},
            {"failed": True, "dropped_items": ["decision_notes"]},
            {"failed": False, "dropped_items": ["tool_output", "decision_notes"]},
        ],
    )

    result = compression_optimizer.optimize_guidelines(str(feedback_path), str(output_path))

    prefer_keep = _bucket(result, "prefer_keep")
    assert "session_summary" in prefer_keep
    assert "decision_notes" in prefer_keep
    assert "tool_output" not in prefer_keep


def test_missing_feedback_file_no_crash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(compression_optimizer, "get_feature_flag", lambda _name, default=False: True)
    feedback_path = tmp_path / "compression-feedback.jsonl"
    output_path = tmp_path / "compression-guidelines.json"

    result = compression_optimizer.optimize_guidelines(str(feedback_path), str(output_path))

    assert result["always_keep"] == []
    assert result["prefer_keep"] == []
    assert result["compress_ok"] == []
    assert result["drop_ok"] == []
    assert output_path.exists()


def test_guidelines_json_structure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(compression_optimizer, "get_feature_flag", lambda _name, default=False: True)
    feedback_path = tmp_path / "compression-feedback.jsonl"
    output_path = tmp_path / "compression-guidelines.json"
    _write_jsonl(
        feedback_path,
        [
            {"failed": True, "dropped_items": ["error_context"]},
            {"failed": False, "dropped_items": ["token_details"]},
        ],
    )

    compression_optimizer.optimize_guidelines(str(feedback_path), str(output_path))

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert set(payload.keys()) == {
        "generated_at",
        "always_keep",
        "prefer_keep",
        "compress_ok",
        "drop_ok",
    }


def test_items_never_in_failures_are_compress_ok(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(compression_optimizer, "get_feature_flag", lambda _name, default=False: True)
    feedback_path = tmp_path / "compression-feedback.jsonl"
    output_path = tmp_path / "compression-guidelines.json"
    _write_jsonl(
        feedback_path,
        [
            {"failed": True, "dropped_items": ["critical_stack"]},
            {"failed": False, "dropped_items": ["verbose_trace", "extra_context"]},
            {"failed": False, "dropped_items": ["verbose_trace"]},
        ],
    )

    result = compression_optimizer.optimize_guidelines(str(feedback_path), str(output_path))

    compress_ok = _bucket(result, "compress_ok")
    assert "verbose_trace" in compress_ok
    assert "extra_context" in compress_ok
    assert "critical_stack" not in compress_ok
