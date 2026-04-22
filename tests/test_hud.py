"""Tests for HUD event emission."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.hud_events import emit_hud_event


class TestEmitHudEvent:
    """Tests for emit_hud_event function."""

    def test_emit_hud_event_creates_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify JSONL file is created when emitting an event."""
        monkeypatch.chdir(tmp_path)
        
        emit_hud_event("test_event", {"key": "value"})
        
        event_file = tmp_path / ".omg" / "state" / "hud-events.jsonl"
        assert event_file.exists(), "HUD events file should be created"

    def test_emit_hud_event_valid_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify each line in the event file is valid JSON."""
        monkeypatch.chdir(tmp_path)
        
        emit_hud_event("event_one", {"data": 1})
        emit_hud_event("event_two", {"data": 2})
        
        event_file = tmp_path / ".omg" / "state" / "hud-events.jsonl"
        lines = event_file.read_text().strip().split("\n")
        
        assert len(lines) == 2, "Should have 2 event lines"
        for line in lines:
            parsed = json.loads(line)  # Raises if invalid JSON
            assert isinstance(parsed, dict), "Each line should parse as dict"

    def test_hud_event_has_required_fields(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify event has type and data fields."""
        monkeypatch.chdir(tmp_path)
        
        emit_hud_event("my_event_type", {"payload": "test"})
        
        event_file = tmp_path / ".omg" / "state" / "hud-events.jsonl"
        event = json.loads(event_file.read_text().strip())
        
        assert "type" in event, "Event should have 'type' field"
        assert event["type"] == "my_event_type", "Event type should match"
        assert "data" in event, "Event should have 'data' field"
        assert event["data"] == {"payload": "test"}, "Event data should match"

    def test_emit_hud_event_appends(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify multiple events are appended to same file."""
        monkeypatch.chdir(tmp_path)
        
        emit_hud_event("first", {})
        emit_hud_event("second", {})
        emit_hud_event("third", {})
        
        event_file = tmp_path / ".omg" / "state" / "hud-events.jsonl"
        lines = event_file.read_text().strip().split("\n")
        
        assert len(lines) == 3, "Should have 3 appended events"
        types = [json.loads(line)["type"] for line in lines]
        assert types == ["first", "second", "third"], "Events should be in order"
